"""Descobre dados de AppServer (v0.8.11 + v0.8.12 network probe).

Dois caminhos:

1. **Network (v0.8.12)**: ``probe_appserver_network(host, port, binary)`` invoca
   ``advpls cli`` com action=validate — é o mesmo mecanismo que o TDS-VSCode
   usa por baixo. Não precisa de filesystem do servidor, funciona via TCP.
   Bônus: descobre também a flag ``secure`` (SSL/TLS) do AppServer.

2. **Log (v0.8.11)**: ``probe_appserver_log(path)`` parseia ``protheus.log``
   à procura da linha de boot. Fallback útil quando o AppServer não responde
   ao validate (versões Lobo Guara antigas, issue tds-vscode#390) ou quando
   o usuário só tem o log mas não o servidor up.

Ambos retornam dataclasses imutáveis. Sem efeito colateral além do subprocess
do advpls (network) e leitura de filesystem (log).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProbeResult:
    """Resultado do probe via ``protheus.log`` (caminho histórico)."""

    log_path: Path
    build: str  # ex.: "7.00.240223P" — vazio se não encontrou
    build_date: str  # ex.: "Oct 3 2025" — vazio se não encontrou
    lines_scanned: int


@dataclass(frozen=True)
class NetworkProbeResult:
    """Resultado do probe via ``advpls cli action=validate`` (TCP)."""

    host: str
    port: int
    build: str  # ex.: "7.00.240223P" — vazio se falhou
    secure: bool | None  # True/False detectado, None se advpls não reportou
    error: str  # mensagem clara se falhou; vazio se ok
    raw_output: str  # primeiros ~1KB do output do advpls (debug)


# Linha típica no protheus.log:
#   * TOTVS - Build 7.00.240223P - Oct 3 2025
# Variações observadas: prefixo pode ter timestamp/PID, "TOTVS" pode aparecer
# em maiúscula/mista. Regex tolera espaços extras.
_BUILD_LINE_RE = re.compile(
    r"TOTVS\s*-\s*Build\s+(?P<build>[\w.]+)\s*-\s*(?P<date>.+?)\s*$",
    re.IGNORECASE,
)

# Output do `advpls cli action=validate` (formato confirmado em
# totvs/tds-vscode src/protocolMessages.ts + tds-ls/TDS-cli-script.md):
#   "[LOG] Appserver detected with build version: 7.00.170117A and secure: 0"
# Variações: "build:" sozinho, "build version:", às vezes só no logToFile.
_VALIDATE_BUILD_RE = re.compile(
    r"build(?:\s+version)?\s*[:=]\s*([\w.]+)",
    re.IGNORECASE,
)
_VALIDATE_SECURE_RE = re.compile(
    r"secure\s*[:=]\s*(\d+|true|false)",
    re.IGNORECASE,
)

# Locais comuns onde protheus.log fica quando user aponta para a raíz do Protheus.
_LOG_SUBPATHS: tuple[str, ...] = (
    "log/protheus.log",
    "bin/Appserver/log/protheus.log",
    "bin/Appserver/protheus.log",
    "Appserver/log/protheus.log",
    "protheus.log",
)

# Regex pra detectar formato "host:port" (IPv4, hostname, FQDN).
# IPv6 não suportado por enquanto (precisaria [host]:port).
_HOST_PORT_RE = re.compile(r"^([\w.\-]+):(\d+)$")


def is_host_port(target: str) -> bool:
    """True se ``target`` parece "host:port" (e não é path filesystem existente).

    Casos:
    - ``"192.168.1.1:1234"`` → True
    - ``"hml.cliente.com:5025"`` → True
    - ``"localhost:1234"`` → True
    - ``"D:\\TOTVS\\protheus\\log\\protheus.log"`` → False (`port` parte não é digit)
    - ``"D:1234"`` → True regex mas False se existe como path (escape Win)
    """
    if not _HOST_PORT_RE.match(target):
        return False
    # Edge case windows: "D:1234" técnico match mas se filesystem path existe
    # (raro mas possível) prefere o filesystem.
    if Path(target).exists():
        return False
    return True


def _resolve_log_path(target: Path) -> Path | None:
    """Resolve caminho do protheus.log a partir de Path ambíguo.

    Aceita:
    - Path direto pro .log (foo/protheus.log)
    - Raiz da instalação Protheus (procura em subpaths comuns)
    """
    if target.is_file():
        return target
    if not target.is_dir():
        return None
    for sub in _LOG_SUBPATHS:
        cand = target / sub
        if cand.is_file():
            return cand
    return None


def probe_appserver_log(target: Path, max_lines: int = 5000) -> ProbeResult | None:
    """Parseia protheus.log à procura da linha "TOTVS - Build X - Date".

    A linha aparece no boot do AppServer — limitamos leitura a ``max_lines``
    primeiras linhas pra evitar varrer log de produção inteiro (pode ter GB).

    Returns:
        ProbeResult com build/build_date extraídos. None se log não encontrado.
        Se log existe mas não tem a linha, retorna ProbeResult com build="".
    """
    log_path = _resolve_log_path(target)
    if log_path is None:
        return None

    build = ""
    date = ""
    count = 0
    try:
        # CP1252 — protheus.log historicamente vem assim no Windows.
        # errors=replace pra não travar em bytes corrompidos de log antigo.
        with log_path.open("r", encoding="cp1252", errors="replace") as fh:
            for line in fh:
                count += 1
                if count > max_lines:
                    break
                m = _BUILD_LINE_RE.search(line)
                if m:
                    build = m.group("build").strip()
                    date = m.group("date").strip()
                    break
    except OSError:
        return ProbeResult(log_path=log_path, build="", build_date="", lines_scanned=count)

    return ProbeResult(log_path=log_path, build=build, build_date=date, lines_scanned=count)


def _parse_validate_output(combined: str) -> tuple[str, bool | None]:
    """Extrai (build, secure) do stdout/log do ``advpls cli action=validate``.

    Função pura: aceita qualquer string, retorna o primeiro match. Build vazio
    se não achou. ``secure``=None se não reportado (default seguro = False).
    """
    build_match = _VALIDATE_BUILD_RE.search(combined)
    build = build_match.group(1).strip() if build_match else ""

    secure: bool | None = None
    secure_match = _VALIDATE_SECURE_RE.search(combined)
    if secure_match:
        v = secure_match.group(1).lower()
        secure = v in ("1", "true")
    return build, secure


def _build_validate_ini(host: str, port: int, log_file: Path) -> str:
    """Gera conteúdo do INI ``[validate]`` pro advpls cli.

    Formato confirmado em totvs/tds-ls/TDS-cli-script.md. Action=validate
    é não-autenticado (não precisa de [auth] nem user/pass).
    """
    return (
        f"showConsoleOutput=true\n"
        f"logToFile={str(log_file).replace(chr(92), '/')}\n"
        f"\n"
        f"[validate]\n"
        f"action=validate\n"
        f"server={host}\n"
        f"port={port}\n"
    )


def probe_appserver_network(
    host: str,
    port: int,
    advpls_binary: Path,
    timeout: int = 20,
) -> NetworkProbeResult:
    """Invoca ``advpls cli`` com action=validate pra obter build via TCP.

    Mesmo mecanismo que o TDS-VSCode usa por baixo (LSP $totvsserver/validation
    → advpls cli action=validate). Não-autenticado, retorna apenas metadata
    pública do AppServer (build, secure).

    Args:
        host: IP ou hostname do AppServer.
        port: porta TCP (default Protheus: 1234).
        advpls_binary: path do advpls (use ``compile_doctor._detect_advpls``).
        timeout: segundos pra advpls responder. Default 20s (validate é rápido,
            mas DNS lento ou firewall lentíssimo justifica margem).

    Returns:
        NetworkProbeResult sempre — ``error`` preenchido se falhou,
        ``build`` preenchido se sucesso. Nunca lança exceção (pra facilitar
        composição em fluxos de doctor / auto-detect).
    """
    from plugadvpl.compile import _decode_advpls_output
    from plugadvpl.edit_prw import encode_cp1252_bytes

    tempdir = Path(tempfile.mkdtemp(prefix="plugadvpl-probe-"))
    if os.name == "posix":
        os.chmod(tempdir, 0o700)
    log_file = tempdir / "validate.log"
    ini_path = tempdir / "validate.ini"
    ini_content = _build_validate_ini(host, port, log_file)

    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(ini_path, flags, 0o600)
        try:
            os.write(fd, encode_cp1252_bytes(ini_content))
        finally:
            os.close(fd)

        try:
            proc = subprocess.run(
                [str(advpls_binary), "cli", str(ini_path)],
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return NetworkProbeResult(
                host=host, port=port, build="", secure=None,
                error=f"advpls timed out after {timeout}s probing {host}:{port}",
                raw_output="",
            )
        except FileNotFoundError as exc:
            return NetworkProbeResult(
                host=host, port=port, build="", secure=None,
                error=f"advpls binary not found at {advpls_binary}: {exc}",
                raw_output="",
            )

        stdout = _decode_advpls_output(proc.stdout)
        stderr = _decode_advpls_output(proc.stderr)
        log_text = ""
        if log_file.is_file():
            try:
                log_text = log_file.read_text(encoding="cp1252", errors="replace")
            except OSError:
                pass
        combined = "\n".join([stdout, stderr, log_text])

        build, secure = _parse_validate_output(combined)
        if not build:
            return NetworkProbeResult(
                host=host, port=port, build="", secure=secure,
                error=(
                    f"advpls returned no build (exit={proc.returncode}). "
                    f"AppServer pode estar down, em SSL sem flag, ou versão "
                    f"Lobo Guara antiga (issue tds-vscode#390)."
                ),
                raw_output=combined[:1000],
            )
        return NetworkProbeResult(
            host=host, port=port, build=build, secure=secure,
            error="", raw_output="",
        )
    finally:
        try:
            shutil.rmtree(tempdir, ignore_errors=True)
        except OSError:
            pass
