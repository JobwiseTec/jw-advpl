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


def load(root: Path) -> RuntimeConfig | None:
    """Carrega ``<root>/.plugadvpl/runtime.toml`` ou retorna None se ausente.

    Raises:
        RuntimeConfigError: TOML malformado, campo obrigatório ausente, env var
            não setada, binary inexistente, etc.
    """
    toml_path = root / ".plugadvpl" / "runtime.toml"
    if not toml_path.is_file():
        return None
    raise NotImplementedError("parse será no próximo step")


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
