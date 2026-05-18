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


class RuntimeConfigError(Exception):
    """Erro de validação do runtime.toml — mensagem clara, sem stacktrace ruidoso."""


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
    except (OSError, socket.timeout):
        return False


def _require(d: dict, section: str, key: str, src: Path) -> object:
    if section not in d or key not in d[section]:
        raise RuntimeConfigError(
            f"missing required key [{section}].{key} in {src}"
        )
    return d[section][key]


def _require_env(varname: str, ref: str) -> str:
    val = os.environ.get(varname)
    if val is None:
        raise RuntimeConfigError(
            f"env var {varname} (referenced by {ref}) is not set"
        )
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
    binary_str = str(_require(raw, "tds_ls", "binary", toml_path))
    binary = Path(binary_str)
    if not binary.is_file():
        raise RuntimeConfigError(f"advpls not found at {binary}")
    try:
        resolved = binary.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RuntimeConfigError(
            f"binary path resolution failed for {binary}: {exc}"
        ) from exc
    is_symlink = binary.is_symlink()
    tds_ls = TdsLsConfig(binary=resolved, binary_is_symlink=is_symlink)

    # appserver
    asv = raw.get("appserver", {})
    appserver = AppserverConfig(
        host=str(_require(raw, "appserver", "host", toml_path)),
        port=int(_require(raw, "appserver", "port", toml_path)),
        secure=bool(asv.get("secure", False)),
        build=str(_require(raw, "appserver", "build", toml_path)),
        environment=str(_require(raw, "appserver", "environment", toml_path)),
    )

    # auth
    auth_raw = raw.get("auth", {})
    user_env = str(_require(raw, "auth", "user_env", toml_path))
    password_env = str(_require(raw, "auth", "password_env", toml_path))
    _require_env(user_env, "auth.user_env")
    _require_env(password_env, "auth.password_env")
    aut_file_str = str(auth_raw.get("aut_file", "") or "")
    aut_file: Path | None = None
    if aut_file_str:
        aut_file = Path(aut_file_str)
        if not aut_file.is_file():
            raise RuntimeConfigError(f"aut_file not found: {aut_file}")
    auth = AuthConfig(user_env=user_env, password_env=password_env, aut_file=aut_file)

    # compile
    cmp_raw = raw.get("compile", {})
    compile_cfg = CompileConfig(
        recompile=bool(cmp_raw.get("recompile", True)),
        includes=tuple(Path(p) for p in cmp_raw.get("includes", [])),
        mode=str(cmp_raw.get("mode", "auto")),
        timeout_seconds=int(cmp_raw.get("timeout_seconds", 120)),
        include_warnings=bool(cmp_raw.get("include_warnings", True)),
    )

    # logging (optional section)
    log_raw = raw.get("logging", {})
    logging_cfg = LoggingConfig(
        log_to_file=str(log_raw.get("log_to_file", "") or ""),
        show_console_output=bool(log_raw.get("show_console_output", True)),
    )

    warn_remote = appserver.host not in {"127.0.0.1", "localhost", "::1"}
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


def render_template() -> str:
    """Retorna o conteúdo de template do runtime.toml com comentários explicativos.

    Usado por ``plugadvpl compile --init-config``. Sem efeito colateral.
    """
    raise NotImplementedError("será implementado nos próximos steps")


def init_gitignore_entry(root: Path) -> bool:
    """Garante ``.plugadvpl/runtime.toml`` no ``.gitignore`` (cria se ausente).

    Retorna True se adicionou linha, False se já estava lá ou se ``.gitignore``
    não existe (não cria arquivo novo só por isso — usuário pode preferir commitar).
    """
    raise NotImplementedError("será implementado nos próximos steps")
