"""Schema do config do gera-script + montagem determinística a partir de um Server.

O artefato gerado por ``gera-script`` é um par (script + config JSON). O script é
lógica constante (lê o config em runtime); este módulo descreve e **monta** o
config: conexão vinda de ``--use-server`` (registry), paths como placeholder
(a máquina-cliente o plugadvpl não conhece) e a senha conforme o modo de segredo.

Sem random, sem Date: a mesma entrada produz exatamente os mesmos bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plugadvpl.compile_servers import Server

# Prefixo de placeholder. O script gerado aborta se um valor obrigatório ainda
# começa com este caractere ("não preenchido").
PLACEHOLDER_PREFIX = "<"

# Env var default que guarda a senha (mesma convenção do registry de servidores).
DEFAULT_PASSWORD_ENV = "PROTHEUS_PASS"


@dataclass(frozen=True)
class Field:
    """Descreve uma chave do config JSON gerado."""

    key: str
    source: str  # 'server' | 'path' | 'user' | 'secret'
    placeholder: str
    secret: bool = False


# Ordem canônica das chaves no config (determinística).
PATH_FIELDS: list[Field] = [
    Field("BASE_DIR_PATCHES", "path", "<CAMINHO_BASE_DOS_PATCHES>"),
    Field("BUILD_DIR", "path", "<CAMINHO_DO_BUILD_DIR>"),
    Field("FONTES_DIR", "path", "<CAMINHO_DA_PASTA_DE_FONTES>"),
    Field("INCLUDE_DIR", "path", "<CAMINHO_DOS_INCLUDES>"),
    Field("LOG_DIR", "path", "<CAMINHO_DOS_LOGS>"),
]

SERVER_FIELDS: list[Field] = [
    Field("PROTHEUS_SERVER", "server", "<HOST_OU_IP_DO_APPSERVER>"),
    Field("PROTHEUS_PORT", "server", "<PORTA_DO_APPSERVER>"),
    Field("PROTHEUS_SECURE", "server", "<0_OU_1>"),
    Field("PROTHEUS_BUILD", "server", "<BUILD_DO_APPSERVER>"),
    Field("PROTHEUS_ENV", "server", "<NOME_DO_ENVIRONMENT>"),
]

USER_FIELD = Field("PROTHEUS_USER", "user", "<USUARIO_COMPILACAO>")
PASSWORD_FIELD = Field("PROTHEUS_PASSWORD", "secret", "<SENHA_COMPILACAO>", secret=True)
PASSWORD_ENV_FIELD = Field("PROTHEUS_PASSWORD_ENV", "secret", DEFAULT_PASSWORD_ENV, secret=True)

# Chaves da fase TQ (Troca Quente) — só entram no config com --tq.
# DEST_APO/CMP_RPO/DEST_BIN são placeholders (paths do destino, o user preenche);
# RPO_FILES tem default; RESTART_CMD/HEALTHCHECK_URL são opcionais (vazio = pula).
TQ_FIELDS: list[Field] = [
    Field("TQ_DEST_APO", "tq", "<CAMINHO_APO_DO_DESTINO>"),
    Field("TQ_CMP_RPO", "tq", "<CAMINHO_RPO_DE_COMPILACAO>"),
    Field("TQ_DEST_BIN", "tq", "<CAMINHO_BIN_APPSERVER_DESTINO>"),
    Field("TQ_RPO_FILES", "tq", "tttm120.rpo,custom.rpo"),
    Field("TQ_RESTART_CMD", "tq", ""),
    Field("TQ_HEALTHCHECK_URL", "tq", ""),
]

SECRET_MODES = ("env", "config")


def _server_values(server: Server | None) -> dict[str, str]:
    """Valores de conexão a partir do Server (ou vazio se None)."""
    if server is None:
        return {}
    return {
        "PROTHEUS_SERVER": str(server.host),
        "PROTHEUS_PORT": str(server.port),
        # secure NUMÉRICO (0/1) — 'true'/'false' derruba o advpls com [ERROR] stoi.
        "PROTHEUS_SECURE": "1" if server.secure else "0",
        "PROTHEUS_BUILD": str(server.build),
        "PROTHEUS_ENV": str(server.default_environment or ""),
    }


def build_config(
    server: Server | None = None,
    secret: str = "env",
    paths: dict[str, str] | None = None,
    tq: bool = False,
) -> dict[str, str]:
    """Monta o dict do config JSON (ordem canônica, determinístico).

    - conexão: do ``server`` se houver, senão placeholder;
    - paths: do dict ``paths`` (override) se houver, senão placeholder;
    - senha: ``env`` → grava só o NOME da env var (``PROTHEUS_PASSWORD_ENV``);
             ``config`` → grava placeholder em ``PROTHEUS_PASSWORD``;
    - ``tq``: adiciona as chaves da fase Troca Quente (destino + RPO + restart).
    """
    if secret not in SECRET_MODES:
        msg = f"secret invalido: {secret!r} (use 'env' ou 'config')"
        raise ValueError(msg)

    paths = paths or {}
    srv = _server_values(server)
    cfg: dict[str, str] = {}

    for f in PATH_FIELDS:
        cfg[f.key] = paths.get(f.key, f.placeholder)
    for f in SERVER_FIELDS:
        cfg[f.key] = srv.get(f.key, f.placeholder)
    cfg[USER_FIELD.key] = USER_FIELD.placeholder

    if secret == "config":
        cfg[PASSWORD_FIELD.key] = PASSWORD_FIELD.placeholder
    else:  # env
        env_name = server.password_env if server is not None else DEFAULT_PASSWORD_ENV
        cfg[PASSWORD_ENV_FIELD.key] = env_name or DEFAULT_PASSWORD_ENV

    if tq:
        for f in TQ_FIELDS:
            cfg[f.key] = paths.get(f.key, f.placeholder)

    return cfg


def remaining_placeholders(config: dict[str, str]) -> list[str]:
    """Chaves cujo valor ainda é placeholder (começam com ``<``)."""
    return [k for k, v in config.items() if v.startswith(PLACEHOLDER_PREFIX)]


def example_config() -> dict[str, str]:
    """Config de exemplo (100% placeholder, modo env). Determinístico."""
    return build_config(server=None, secret="env")


def config_schema() -> list[dict[str, object]]:
    """Descreve as chaves do config por origem (machine-readable p/ IAs)."""
    out: list[dict[str, object]] = []
    for f in (
        *PATH_FIELDS,
        *SERVER_FIELDS,
        USER_FIELD,
        PASSWORD_FIELD,
        PASSWORD_ENV_FIELD,
        *TQ_FIELDS,
    ):
        out.append(
            {
                "key": f.key,
                "source": f.source,
                "placeholder": f.placeholder,
                "secret": f.secret,
            }
        )
    return out
