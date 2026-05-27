"""Carrega e valida ``<root>/.plugadvpl/runtime.toml``. Compartilhado com Fases 2-4.

Schema documentado em ``docs/fase1/compile-design.md`` §6.

Convenções:
- Credenciais NUNCA são valores literais no TOML — só nome de env var.
- Função ``load()`` é pura: recebe Path, devolve dataclass imutável ou None.
- Validações falham com ``RuntimeConfigError`` (mensagem clara apontando a chave).
"""

from __future__ import annotations

import os
import socket
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast


class RuntimeConfigError(Exception):
    """Erro de validação do runtime.toml — mensagem clara, sem stacktrace ruidoso."""


_LOCAL_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class TdsLsConfig:
    binary: Path
    binary_is_symlink: bool


@dataclass(frozen=True)
class AppserverConfig:
    host: str
    port: int
    secure: bool
    build: str
    environment: str


@dataclass(frozen=True)
class AuthConfig:
    user_env: str
    password_env: str
    aut_file: Path | None


@dataclass(frozen=True)
class CompileConfig:
    recompile: bool
    includes: tuple[Path, ...]
    mode: str
    timeout_seconds: int
    include_warnings: bool


@dataclass(frozen=True)
class LoggingConfig:
    log_to_file: str
    show_console_output: bool


@dataclass(frozen=True)
class RuntimeConfig:
    tds_ls: TdsLsConfig
    appserver: AppserverConfig
    auth: AuthConfig
    compile: CompileConfig
    logging: LoggingConfig
    warn_remote_host: bool
    appserver_reachable: bool
    source_path: Path


def _tcp_ping(host: str, port: int, timeout: float = 1.0) -> bool:
    """Tenta conectar TCP. True se responde dentro do timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


def _require_section(d: dict[str, object], section: str, src: Path) -> dict[str, object]:
    """Retorna d[section] se for dict, erro claro caso contrário."""
    if section not in d:
        raise RuntimeConfigError(f"missing required section [{section}] in {src}")
    val = d[section]
    if not isinstance(val, dict):
        raise RuntimeConfigError(
            f"[{section}] in {src} must be a TOML table, got {type(val).__name__}"
        )
    return val


def _require_key(section_dict: dict[str, object], key: str, src: Path, section_name: str) -> object:
    """Valida que key existe no dict da seção; erro com path do TOML se ausente."""
    if key not in section_dict:
        raise RuntimeConfigError(f"missing required key [{section_name}].{key} in {src}")
    return section_dict[key]


def _require_env(varname: str, ref: str) -> str:
    val = os.environ.get(varname)
    if val is None:
        raise RuntimeConfigError(f"env var {varname} (referenced by {ref}) is not set")
    return val


def load(root: Path) -> RuntimeConfig | None:
    """Carrega ``<root>/.plugadvpl/runtime.toml`` ou retorna None se ausente.

    Raises:
        RuntimeConfigError: TOML malformado, campo obrigatório ausente, env var
            não setada, binary inexistente, etc.
    """
    toml_path = root / ".plugadvpl" / "runtime.toml"
    if not toml_path.is_file():
        return None
    try:
        raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeConfigError(f"invalid TOML in {toml_path}: {exc}") from exc

    # tds_ls
    tds_raw = _require_section(raw, "tds_ls", toml_path)
    binary_str = str(_require_key(tds_raw, "binary", toml_path, "tds_ls"))
    binary = Path(binary_str)
    if not binary.is_file():
        raise RuntimeConfigError(f"advpls not found at {binary}")
    # resolve(strict=True) detecta symlinks quebrados / loops mesmo após is_file() OK
    try:
        resolved = binary.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RuntimeConfigError(f"binary path resolution failed for {binary}: {exc}") from exc
    is_symlink = binary.is_symlink()
    tds_ls = TdsLsConfig(binary=resolved, binary_is_symlink=is_symlink)

    # appserver
    asv = _require_section(raw, "appserver", toml_path)
    appserver = AppserverConfig(
        host=str(_require_key(asv, "host", toml_path, "appserver")),
        port=int(cast("int", _require_key(asv, "port", toml_path, "appserver"))),
        secure=bool(asv.get("secure", False)),
        build=str(_require_key(asv, "build", toml_path, "appserver")),
        environment=str(_require_key(asv, "environment", toml_path, "appserver")),
    )

    # auth — v0.8.11 bug 3: seção OPCIONAL agora. Só é exigida no modo cli
    # (onde a authsantion contra AppServer é real). Validação das env vars
    # também sai daqui — quem precisa é o builder do .ini em compile.py.
    auth_raw_obj = raw.get("auth", {})
    auth_raw: dict[str, object] = auth_raw_obj if isinstance(auth_raw_obj, dict) else {}
    user_env = str(auth_raw.get("user_env", "PROTHEUS_USER"))
    password_env = str(auth_raw.get("password_env", "PROTHEUS_PASS"))
    aut_file_str = str(auth_raw.get("aut_file", ""))
    aut_file: Path | None = None
    if aut_file_str:
        aut_file = Path(aut_file_str)
        if not aut_file.is_file():
            raise RuntimeConfigError(f"aut_file not found: {aut_file}")
    auth = AuthConfig(user_env=user_env, password_env=password_env, aut_file=aut_file)

    # compile
    cmp_raw = _require_section(raw, "compile", toml_path)
    includes_raw = cmp_raw.get("includes", [])
    if not isinstance(includes_raw, list):
        raise RuntimeConfigError(
            f"[compile].includes in {toml_path} must be an array, got {type(includes_raw).__name__}"
        )
    compile_cfg = CompileConfig(
        recompile=bool(cmp_raw.get("recompile", True)),
        includes=tuple(Path(str(p)) for p in includes_raw),
        mode=str(cmp_raw.get("mode", "auto")),
        timeout_seconds=int(cast("int", cmp_raw.get("timeout_seconds", 120))),
        include_warnings=bool(cmp_raw.get("include_warnings", True)),
    )

    # logging (optional section)
    log_raw_obj = raw.get("logging", {})
    log_raw: dict[str, object] = log_raw_obj if isinstance(log_raw_obj, dict) else {}
    logging_cfg = LoggingConfig(
        log_to_file=str(log_raw.get("log_to_file", "") or ""),
        show_console_output=bool(log_raw.get("show_console_output", True)),
    )

    warn_remote = appserver.host not in _LOCAL_HOSTS
    reachable = _tcp_ping(appserver.host, appserver.port)

    return RuntimeConfig(
        tds_ls=tds_ls,
        appserver=appserver,
        auth=auth,
        compile=compile_cfg,
        logging=logging_cfg,
        warn_remote_host=warn_remote,
        appserver_reachable=reachable,
        source_path=toml_path,
    )


_TEMPLATE = """\
# .plugadvpl/runtime.toml — NÃO commitar valores de credencial
# Gerado por `plugadvpl compile --init-config`.

[tds_ls]
# Caminho para advpls. Windows típico: D:/TOTVS/protheus/bin/Appserver/advpls.exe
# ou da extensão tds-vscode.
binary = "D:/TOTVS/protheus/bin/Appserver/advpls.exe"

[appserver]
# RECOMENDAÇÃO: host = "127.0.0.1" + SSH tunnel.
# `ssh -L 1234:localhost:1234 user@vps -N`
host = "127.0.0.1"
port = 1234
secure = false
build = "7.00.240223P"
environment = "P2510"

[auth]
# OPCIONAL — só necessário para mode = "cli" (conexão real ao AppServer).
# Para mode = "appre" (pré-processador local) pode ser omitido inteiramente.
# Convenção: NUNCA valor literal. Sempre nome da env var.
# export PROTHEUS_USER=admin / export PROTHEUS_PASS='senha'
user_env = "PROTHEUS_USER"
password_env = "PROTHEUS_PASS"
aut_file = ""

[compile]
recompile = true
includes = [
    "D:/TOTVS/protheus/includes",
]
mode = "auto"            # auto | appre | cli
timeout_seconds = 120
include_warnings = true

[logging]
log_to_file = ""
show_console_output = true
"""


def render_template() -> str:
    """Retorna o conteúdo de template do runtime.toml com comentários explicativos.

    Usado por ``plugadvpl compile --init-config``. Sem efeito colateral.
    """
    return _TEMPLATE


def init_gitignore_entry(root: Path) -> bool:
    """Garante ``.plugadvpl/runtime.toml`` no ``.gitignore`` (se existir).

    Retorna True se adicionou linha, False se já estava lá ou se ``.gitignore``
    não existe (NÃO cria arquivo novo — usuário pode preferir commitar).
    """
    gi = root / ".gitignore"
    if not gi.is_file():
        return False
    text = gi.read_text(encoding="utf-8")
    needle = ".plugadvpl/runtime.toml"
    if needle in text:
        return False
    suffix = "" if text.endswith("\n") else "\n"
    gi.write_text(text + suffix + needle + "\n", encoding="utf-8")
    return True
