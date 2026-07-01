"""gera-script: gerador determinístico de script de patch+compilação Protheus.

Forja (na máquina do dev) um script ``.ps1``/``.sh`` autossuficiente + um config
JSON pré-preenchido, para um operador humano rodar na base do cliente **sem**
plugadvpl nem IA. Conexão vem de ``--use-server`` (registry); paths viram
placeholder; senha via env var (default) ou config. Determinístico, sem LLM.

Re-exports:
- ``build_config`` / ``example_config`` / ``config_schema`` / ``remaining_placeholders``
- ``emit_ps1`` / ``emit_sh`` / ``emit_config_json``
- nomes dos artefatos: ``PS1_NAME`` / ``SH_NAME`` / ``CONFIG_NAME``
"""

from __future__ import annotations

from .emit import (
    CONFIG_NAME,
    PS1_NAME,
    SH_NAME,
    emit_config_json,
    emit_ps1,
    emit_sh,
)
from .schema import (
    SECRET_MODES,
    build_config,
    config_schema,
    example_config,
    remaining_placeholders,
)

__all__ = [
    "CONFIG_NAME",
    "PS1_NAME",
    "SECRET_MODES",
    "SH_NAME",
    "build_config",
    "config_schema",
    "emit_config_json",
    "emit_ps1",
    "emit_sh",
    "example_config",
    "remaining_placeholders",
]
