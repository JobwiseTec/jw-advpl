"""Cliente HTTP do COLETADB — consome o contrato REST descrito em
``docs/coletadb-contract.md``.

Stdlib only (``urllib.request``) — sem dep nova. Padrao espelhado de
:mod:`plugadvpl.compile_installer` que ja usa ``urllib`` pra download
da extensao TDS-VSCode.

Cobertura:

- ``health()`` — probe + descoberta de versao
- ``list_tables()`` — metadata (row_count, last_modified)
- ``get_dump(tables, ...)`` — bulk com paginacao automatica
- Auth: bearer ou basic
- Retry exponencial em 5xx
- Erros tipados: :class:`ColetaDBError`

Nao implementa Fase 4c (auto-install do COLETADB) — esse fica pro
``plugadvpl.compile`` ser invocado pelo CLI quando ``health()`` retornar
404, fora do escopo desta classe.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_S = 30
DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_BACKOFF_S = 2.0
DEFAULT_PAGINATE_LIMIT = 10_000


@dataclass(frozen=True)
class HealthResponse:
    """Resposta canonical de ``GET /health``."""

    version: str
    protheus_build: str
    protheus_environment: str
    exposed_tables: list[str]
    extras: list[str] = field(default_factory=list)


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
        endpoint: base URL (ex: ``http://protheus:8181/rest/coletadb``).
            Trailing slash e tolerado.
        token: bearer token (quando ``auth_method='bearer'``).
        user/password: credenciais (quando ``auth_method='basic'``).
        auth_method: ``'bearer'`` (default) ou ``'basic'``.
        timeout_s: timeout por request.
        retry_count: tentativas em caso de 5xx (default 3).
        retry_backoff_s: base do backoff exponencial (default 2s -> 2, 4, 8).
        paginate_limit: limit query param em paginacao (default 10_000).
        extra_headers: dict de headers adicionais (ex: tenant id).
    """

    def __init__(
        self,
        *,
        endpoint: str,
        token: str | None = None,
        user: str | None = None,
        password: str | None = None,
        auth_method: Literal["bearer", "basic"] = "bearer",
        timeout_s: float = DEFAULT_TIMEOUT_S,
        retry_count: int = DEFAULT_RETRY_COUNT,
        retry_backoff_s: float = DEFAULT_RETRY_BACKOFF_S,
        paginate_limit: int = DEFAULT_PAGINATE_LIMIT,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._token = token
        self._user = user
        self._password = password
        self._auth_method = auth_method
        self._timeout_s = timeout_s
        self._retry_count = max(1, retry_count)
        self._retry_backoff_s = max(0.0, retry_backoff_s)
        self._paginate_limit = max(1, paginate_limit)
        self._extra_headers = dict(extra_headers or {})

    # ---------------------------------------------------------------------
    # API publica
    # ---------------------------------------------------------------------

    def health(self) -> HealthResponse:
        """``GET /health`` — probe + descoberta de versao."""
        data = self._get_json("/health")
        return HealthResponse(
            version=data.get("version", ""),
            protheus_build=data.get("protheus_build", ""),
            protheus_environment=data.get("protheus_environment", ""),
            exposed_tables=list(data.get("exposed_tables", [])),
            extras=list(data.get("extras", [])),
        )

    def list_tables(self) -> list[dict[str, Any]]:
        """``GET /tables`` — metadata por tabela."""
        data = self._get_json("/tables")
        return list(data.get("tables", []))

    def get_dump(
        self,
        tables: list[str],
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        """``GET /dump?tables=...`` — bulk de uma ou mais tabelas.

        Em caso de paginacao (``has_more=True``), faz loop seguindo
        ``next_offset`` ate consumir tudo. Concatena rows de cada pagina.

        Retorna ``{table_name: {row_count, rows}}``.
        """
        if not tables:
            return {}
        effective_limit = limit if limit is not None else self._paginate_limit
        params = {
            "tables": ",".join(tables),
            "offset": str(offset),
            "limit": str(effective_limit),
        }
        accumulated: dict[str, dict[str, Any]] = {}
        current_offset = offset
        while True:
            params["offset"] = str(current_offset)
            data = self._get_json("/dump", params=params)
            tables_data = data.get("tables", {})
            has_more = False
            next_offset = None
            for table_name, table_payload in tables_data.items():
                if table_name not in accumulated:
                    accumulated[table_name] = {
                        "row_count": table_payload.get("row_count", 0),
                        "rows": [],
                    }
                accumulated[table_name]["rows"].extend(
                    table_payload.get("rows", [])
                )
                # has_more pode estar em qualquer tabela; se uma diz True,
                # ainda precisamos buscar mais.
                if table_payload.get("has_more", False):
                    has_more = True
                    next_offset = table_payload.get("next_offset", current_offset + effective_limit)
            if not has_more or next_offset is None:
                break
            current_offset = int(next_offset)
        return accumulated

    def get_table(self, name: str) -> dict[str, Any]:
        """``GET /table/{nome}`` — atalho pra uma tabela so."""
        data = self._get_json(f"/table/{name}")
        return data

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------

    def _build_url(self, path: str, params: dict[str, str] | None = None) -> str:
        path = path if path.startswith("/") else f"/{path}"
        url = self._endpoint + path
        if params:
            from urllib.parse import urlencode
            url += "?" + urlencode(params)
        return url

    def _auth_header(self) -> dict[str, str]:
        if self._auth_method == "bearer" and self._token:
            return {"Authorization": f"Bearer {self._token}"}
        if self._auth_method == "basic" and self._user is not None:
            cred = f"{self._user}:{self._password or ''}".encode("utf-8")
            encoded = base64.b64encode(cred).decode("ascii")
            return {"Authorization": f"Basic {encoded}"}
        return {}

    def _get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """GET + JSON parse com retry exponencial em 5xx/URLError."""
        url = self._build_url(path, params)
        headers = {
            "Accept": "application/json",
            **self._auth_header(),
            **self._extra_headers,
        }
        last_exc: Exception | None = None
        for attempt in range(self._retry_count):
            try:
                req = Request(url, headers=headers, method="GET")
                with urlopen(req, timeout=self._timeout_s) as resp:
                    body = resp.read()
                    return json.loads(body.decode("utf-8"))
            except HTTPError as exc:
                last_exc = exc
                if exc.code == 401:
                    raise ColetaDBError(
                        f"401 Unauthorized em {url} — token invalido ou expirado",
                        status=401, code="UNAUTHORIZED",
                        hint="Atualize o token com 'ingest-protheus --set-token <server>'",
                    ) from exc
                if exc.code == 403:
                    raise ColetaDBError(
                        f"403 Forbidden em {url} — sem permissao",
                        status=403, code="FORBIDDEN",
                        hint="Confirme escopo do token com o admin do AppServer",
                    ) from exc
                if exc.code == 404:
                    raise ColetaDBError(
                        f"404 Not Found em {url} — COLETADB pode nao estar instalado no AppServer",
                        status=404, code="NOT_FOUND",
                        hint=(
                            "1) Confirme URL em [coletadb] do runtime.toml; "
                            "2) Peca ao TI compilar COLETADB.tlpp no AppServer; "
                            "3) Em release futura, '--install-server-component' fara isso automatico"
                        ),
                    ) from exc
                if 500 <= exc.code < 600:
                    # 5xx: retry com backoff exponencial
                    if attempt < self._retry_count - 1:
                        sleep_for = self._retry_backoff_s * (2**attempt)
                        time.sleep(sleep_for)
                        continue
                    raise ColetaDBError(
                        f"{exc.code} server error em {url} apos {self._retry_count} tentativas",
                        status=exc.code, code="SERVER_ERROR",
                    ) from exc
                # Outros codes (400, 429, etc) — sem retry
                raise ColetaDBError(
                    f"HTTP {exc.code} em {url}",
                    status=exc.code,
                ) from exc
            except URLError as exc:
                last_exc = exc
                if attempt < self._retry_count - 1:
                    sleep_for = self._retry_backoff_s * (2**attempt)
                    time.sleep(sleep_for)
                    continue
                raise ColetaDBError(
                    f"Conectividade falhou em {url}: {exc.reason}",
                    code="CONNECTION_ERROR",
                    hint=(
                        "1) Confirme que AppServer esta rodando; "
                        "2) Verifique VPN/firewall; "
                        "3) Teste com 'ingest-protheus --check'"
                    ),
                ) from exc
        # Defensive — nunca deve chegar aqui (raises acima cobrem todas as branches)
        raise ColetaDBError(
            f"Falha desconhecida em {url}: {last_exc}",
        )
