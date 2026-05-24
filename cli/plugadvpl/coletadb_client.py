"""Cliente HTTP do COLETADB — consome o contrato bundle-pattern descrito em
``docs/coletadb-contract.md``.

Protocolo real (validado contra ``gaps/COLETADB.tlpp`` em 2026-05-21):

- ``POST /coletadb/run`` -> servidor gera CSVs em ``base_dir`` + retorna manifest
- ``POST /coletadb/file`` -> cliente baixa bytes em chunks de 4MB

Auth: HTTP Basic via ``Security=1`` do AppServer (reusa mesmo user/senha do
compile via ``credentials.py``). Sem bearer tokens.

Stdlib only (``urllib.request``) — sem dep nova. Pattern espelha
:mod:`plugadvpl.compile_installer`.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_RUN_S = 300.0      # /run pode demorar (gera CSV do dicionario)
DEFAULT_TIMEOUT_FILE_S = 60.0      # /file le 4MB de disk
DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_BACKOFF_S = 2.0
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB, casa com CDB_API_CHUNK do servidor


@dataclass(frozen=True)
class BundleFile:
    """Um arquivo do bundle gerado pelo /run."""

    name: str          # "SX3.csv"
    path: str          # full path NO SERVIDOR (usado em /file)
    size_bytes: int
    chunks: int
    sha256: str        # legado v1.0.x — preenchido só quando hash_algo=sha256
    # v1.0.3+ — hash com algoritmo dinâmico
    hash: str = ""     # hex lower; vazio se nenhuma função existe na build
    hash_algo: str = ""    # "sha256" | "sha1" | "md5" | ""
    hash_partial: bool = False  # True quando arquivo > 64KB e build trunca MemoRead


@dataclass(frozen=True)
class Manifest:
    """Resposta de ``POST /coletadb/run``."""

    bundle_id: str
    bundle_dir: str
    modo: str
    threshold: int
    chunk_size: int
    files: list[BundleFile] = field(default_factory=list)


class ColetaDBError(Exception):
    """Erro estruturado do cliente. Wrappa HTTPError/URLError com hint pro usuario."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.hint = hint


class ColetaDBClient:
    """Cliente do COLETADB. Stateless — pode ser instanciado por chamada.

    Args:
        endpoint: base URL (ex: ``http://protheus:8181/rest``).
            Trailing slash e tolerado. NAO inclui ``/coletadb`` — os
            endpoints sao ``{endpoint}/coletadb/run`` e ``/coletadb/file``.
        user/password: credenciais HTTP Basic (validadas pelo AppServer
            via ``Security=1``).
        timeout_run_s: timeout do ``/run`` (gera CSVs, pode demorar).
        timeout_file_s: timeout do ``/file`` (chunk de 4MB).
        retry_count: tentativas em caso de 5xx (default 3).
        retry_backoff_s: base do backoff exponencial.
        chunk_size: bytes por chunk no /file (default 4MB).
    """

    def __init__(
        self,
        *,
        endpoint: str,
        user: str,
        password: str,
        timeout_run_s: float = DEFAULT_TIMEOUT_RUN_S,
        timeout_file_s: float = DEFAULT_TIMEOUT_FILE_S,
        retry_count: int = DEFAULT_RETRY_COUNT,
        retry_backoff_s: float = DEFAULT_RETRY_BACKOFF_S,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._user = user
        self._password = password
        self._timeout_run_s = timeout_run_s
        self._timeout_file_s = timeout_file_s
        self._retry_count = max(1, retry_count)
        self._retry_backoff_s = max(0.0, retry_backoff_s)
        self._chunk_size = max(1, chunk_size)

    # ---------------------------------------------------------------------
    # API publica
    # ---------------------------------------------------------------------

    def run(
        self,
        *,
        modo: str = "enxuto",
        threshold: int = 10,
        base_dir: str = "",
        ini_dir: str = "",
    ) -> Manifest:
        """``POST /coletadb/run`` — gera bundle no servidor + retorna manifest."""
        body: dict[str, Any] = {"modo": modo, "threshold": threshold}
        if base_dir:
            body["base_dir"] = base_dir
        if ini_dir:
            body["ini_dir"] = ini_dir
        data = self._post_json("/coletadb/run", body, timeout=self._timeout_run_s)
        files = [
            BundleFile(
                name=f.get("name", ""),
                path=f.get("path", ""),
                size_bytes=int(f.get("size_bytes", 0)),
                chunks=int(f.get("chunks", 0)),
                sha256=f.get("sha256", ""),
                hash=f.get("hash", ""),
                hash_algo=f.get("hash_algo", ""),
                hash_partial=bool(f.get("hash_partial", False)),
            )
            for f in data.get("files", [])
        ]
        return Manifest(
            bundle_id=data.get("bundle_id", ""),
            bundle_dir=data.get("bundle_dir", ""),
            modo=data.get("modo", modo),
            threshold=int(data.get("threshold", threshold)),
            chunk_size=int(data.get("chunk_size", self._chunk_size)),
            files=files,
        )

    def download_file(
        self,
        bundle_file: BundleFile,
        dest_path: Any,  # Path or str (avoid pathlib import in client module hot path)
        *,
        progress_callback: Any = None,  # Callable[[int, int], None] | None
    ) -> int:
        """Baixa ``bundle_file`` em chunks pra ``dest_path`` + verifica hash.

        Retorna bytes baixados. Loop interno faz ``POST /coletadb/file`` em
        sequencia, incrementando ``offset`` ate consumir o arquivo todo.

        Verificacao de hash (v1.0.3+):
          - ``hash`` + ``hash_algo`` populados -> usa algoritmo correto
            (sha256/sha1/md5)
          - ``sha256`` legado populado (v1.0.x) -> usa sha256
          - Nenhum dos dois preenchido -> pula validacao com warning silencioso
          - ``hash_partial=True`` -> hasheia so primeiros 65535 bytes (match
            do MemoRead truncado do server). Resto do arquivo nao e validado.
        """
        from pathlib import Path
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        total_written = 0

        with dest.open("wb") as f:
            offset = 0
            while True:
                payload = {
                    "path": bundle_file.path,
                    "offset": offset,
                    "limit": self._chunk_size,
                }
                chunk_bytes, headers = self._post_bytes(
                    "/coletadb/file", payload, timeout=self._timeout_file_s,
                )
                if not chunk_bytes:
                    break
                f.write(chunk_bytes)
                total_written += len(chunk_bytes)
                if progress_callback is not None:
                    progress_callback(total_written, bundle_file.size_bytes)

                # Para o loop quando atingimos o tamanho esperado.
                # X-Total-Size header e fonte de verdade — confirma EOF.
                total_size = int(headers.get("X-Total-Size", "0") or "0")
                if total_size > 0 and offset + len(chunk_bytes) >= total_size:
                    break
                # Defesa contra loop infinito: se o servidor retornou menos
                # bytes que pedimos, e provavelmente EOF.
                if len(chunk_bytes) < self._chunk_size:
                    break
                offset += len(chunk_bytes)

        # Verifica integridade — escolhe algoritmo a partir do manifest
        self._verify_hash(bundle_file, dest)
        return total_written

    @staticmethod
    def _verify_hash(bundle_file: BundleFile, dest_path: Any) -> None:
        """Verifica integridade do download contra hash do manifest.

        Preferencia: hash+hash_algo (v1.0.3+) -> sha256 legado (v1.0.x).
        Em hash_partial=True, hasheia so os primeiros 65535 bytes pra casar
        com MemoRead truncado do server (build sem streaming).
        """
        # Determina algoritmo e hash esperado
        algo = (bundle_file.hash_algo or "").lower()
        expected = bundle_file.hash
        if not expected:
            # Fallback pra campo legado sha256 (v1.0.x)
            expected = bundle_file.sha256
            if expected:
                algo = "sha256"
        if not expected or not algo:
            # Servidor nao emitiu hash (build sem funcao disponivel) — pula
            return

        if algo not in {"sha256", "sha1", "md5"}:
            # Algoritmo desconhecido — registra warning silencioso e pula
            return

        hasher = hashlib.new(algo)
        from pathlib import Path
        dest = Path(dest_path)
        # Se hash_partial, server so hasheou os primeiros 65535 bytes
        # (MemoRead truncado). Cliente faz o mesmo pra casar.
        max_bytes = 65535 if bundle_file.hash_partial else None
        bytes_read = 0
        with dest.open("rb") as f:
            while True:
                chunk_size = 65536
                if max_bytes is not None:
                    chunk_size = min(chunk_size, max_bytes - bytes_read)
                    if chunk_size <= 0:
                        break
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
                bytes_read += len(chunk)

        actual = hasher.hexdigest()
        if actual.lower() != expected.lower():
            partial_note = " (partial — primeiros 65535B)" if bundle_file.hash_partial else ""
            raise ColetaDBError(
                f"{algo} mismatch em {bundle_file.name}{partial_note}: "
                f"esperado {expected[:16]}..., "
                f"obtido {actual[:16]}...",
                code=f"{algo.upper()}_MISMATCH",
                hint="Arquivo corrompido durante transfer. Tente rodar novamente.",
            )

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------

    def _auth_header(self) -> dict[str, str]:
        cred = f"{self._user}:{self._password}".encode("utf-8")
        encoded = base64.b64encode(cred).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}

    def _build_url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return self._endpoint + path

    @staticmethod
    def _extract_error_msg(exc: HTTPError) -> str:
        """Le body de um HTTPError e extrai mensagem util pro usuario.

        Smoke test (2026-05-23) mostrou que o server pode retornar JSON
        estruturado tipo ``{"error":"campo X obrigatorio"}`` em respostas
        4xx/5xx — silenciar isso esconde a causa real. Tenta parse JSON,
        fallback pra texto truncado. Se tudo falha, retorna ``exc.reason``.
        """
        try:
            body = exc.read()
        except Exception:  # pragma: no cover - HTTPError sem body legivel
            return exc.reason or ""
        if not body:
            return exc.reason or ""
        try:
            parsed = json.loads(body.decode("utf-8"))
            if isinstance(parsed, dict):
                err = parsed.get("error") or parsed.get("message")
                if err:
                    return str(err)
                # Sem chave conhecida — devolve compactado
                return json.dumps(parsed, ensure_ascii=False)[:500]
        except (ValueError, UnicodeDecodeError):
            pass
        try:
            text = body.decode("utf-8", errors="replace").strip()
            return text[:500] if text else (exc.reason or "")
        except Exception:  # pragma: no cover
            return exc.reason or ""

    def _post_with_retry(
        self,
        url: str,
        body_bytes: bytes,
        headers: dict[str, str],
        timeout: float,
    ) -> tuple[bytes, dict[str, str]]:
        """POST com retry exponencial. Retorna (response_bytes, response_headers)."""
        last_exc: Exception | None = None
        for attempt in range(self._retry_count):
            try:
                req = Request(url, data=body_bytes, headers=headers, method="POST")
                with urlopen(req, timeout=timeout) as resp:
                    resp_body = resp.read()
                    resp_headers = {k: v for k, v in resp.headers.items()}
                    return resp_body, resp_headers
            except HTTPError as exc:
                last_exc = exc
                server_msg = self._extract_error_msg(exc)
                if exc.code == 401:
                    raise ColetaDBError(
                        f"401 Unauthorized em {url} — user/senha invalidos"
                        + (f" (server: {server_msg})" if server_msg else ""),
                        status=401, code="UNAUTHORIZED",
                        hint="Confira credenciais do Protheus (mesmas do compile)",
                    ) from exc
                if exc.code == 403:
                    raise ColetaDBError(
                        f"403 Forbidden em {url} — sem permissao"
                        + (f" (server: {server_msg})" if server_msg else ""),
                        status=403, code="FORBIDDEN",
                    ) from exc
                if exc.code == 404:
                    raise ColetaDBError(
                        f"404 Not Found em {url} — endpoint nao encontrado"
                        + (f" (server: {server_msg})" if server_msg else ""),
                        status=404, code="NOT_FOUND",
                        hint=(
                            "1) Confirme URL em [coletadb] do runtime.toml; "
                            "2) Peca ao TI compilar COLETADB.tlpp no AppServer; "
                            "3) Confirme [HTTPV11]/[HTTPURI] habilitados no appserver.ini"
                        ),
                    ) from exc
                if exc.code == 416:
                    # 416 Range Not Satisfiable: offset alem do EOF — sinal de fim
                    # de download. Cliente deve tratar como "fim normal", nao erro.
                    # Para isso, lemos o body e retornamos pra caller decidir.
                    try:
                        body = exc.read()
                    except Exception:  # pragma: no cover
                        body = b""
                    return body, {"X-Total-Size": "0"}
                if exc.code == 422:
                    raise ColetaDBError(
                        f"422 em {url}: {server_msg or exc.reason}",
                        status=422, code="VALIDATION_ERROR",
                    ) from exc
                if 500 <= exc.code < 600:
                    if attempt < self._retry_count - 1:
                        time.sleep(self._retry_backoff_s * (2**attempt))
                        continue
                    raise ColetaDBError(
                        f"{exc.code} server error em {url} apos {self._retry_count} tentativas"
                        + (f" (server: {server_msg})" if server_msg else ""),
                        status=exc.code, code="SERVER_ERROR",
                    ) from exc
                # Outros codes — sem retry. Inclui body do server pra debug
                # (smoke test mostrou que 400 do REST framework Protheus tem
                # mensagem util tipo "Accept type not supported").
                raise ColetaDBError(
                    f"HTTP {exc.code} em {url}: {server_msg or exc.reason}",
                    status=exc.code,
                ) from exc
            except URLError as exc:
                last_exc = exc
                if attempt < self._retry_count - 1:
                    time.sleep(self._retry_backoff_s * (2**attempt))
                    continue
                raise ColetaDBError(
                    f"Conectividade falhou em {url}: {exc.reason}",
                    code="CONNECTION_ERROR",
                    hint=(
                        "1) Confirme que AppServer esta rodando; "
                        "2) Verifique VPN/firewall; "
                        "3) Confirme porta REST configurada em [HTTPV11]"
                    ),
                ) from exc
        # Defensive
        raise ColetaDBError(f"Falha desconhecida em {url}: {last_exc}")

    def _post_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        timeout: float,
    ) -> dict[str, Any]:
        """POST + JSON response. Usado pelo /run e por outras chamadas que
        retornam JSON estruturado."""
        url = self._build_url(path)
        body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            **self._auth_header(),
        }
        resp_bytes, _ = self._post_with_retry(url, body_bytes, headers, timeout)
        try:
            return json.loads(resp_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ColetaDBError(
                f"Response do {path} nao e JSON valido: {exc}",
                code="INVALID_RESPONSE",
            ) from exc

    def _post_bytes(
        self,
        path: str,
        body: dict[str, Any],
        *,
        timeout: float,
    ) -> tuple[bytes, dict[str, str]]:
        """POST + binary response. Usado pelo /file (octet-stream).

        Smoke test contra Protheus build 7.00.240223P (2026-05-23) mostrou
        que o REST framework do AppServer rejeita ``Accept: application/octet-stream``
        com HTTP 400 *antes* de chegar no WSMETHOD (sem trace no log do
        AppServer). Curl manual com ``Accept: */*`` funciona. Usamos */*
        aqui — server e responsabilidade de setar Content-Type correto
        (octet-stream pra binario, application/json pra erros).
        """
        url = self._build_url(path)
        body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "*/*",
            **self._auth_header(),
        }
        return self._post_with_retry(url, body_bytes, headers, timeout)
