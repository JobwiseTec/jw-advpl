"""Emitter determinístico do gera-script: templates fixos + config JSON montado.

O script (.ps1/.sh) é lógica **constante** (lê o config em runtime), então emiti-lo
é carregar o template e normalizar a quebra de linha (.ps1 = CRLF p/ Windows,
.sh = LF). O que varia por ambiente é só o config JSON (ver ``schema.build_config``).

Sem random, sem Date: a mesma entrada produz exatamente os mesmos bytes.
"""

from __future__ import annotations

import importlib.resources
import json

# Nomes canônicos dos artefatos gerados.
PS1_NAME = "patch_e_compilacao.ps1"
SH_NAME = "patch_e_compilacao.sh"
CONFIG_NAME = "patch_e_compilacao_config.json"

_PS1_TMPL = "patch_e_compilacao.ps1.tmpl"
_SH_TMPL = "patch_e_compilacao.sh.tmpl"
_TQ_PS1_TMPL = "tq_phase.ps1.tmpl"
_TQ_SH_TMPL = "tq_phase.sh.tmpl"

# Marker (linha própria) substituído pela fase TQ quando ``with_tq=True``,
# ou removido quando False. Mantém 1 template base + determinismo.
_TQ_MARKER = "# {{TQ_PHASE}}\n"


def _load_template(name: str) -> str:
    """Lê um template (UTF-8, LF) empacotado em ``plugadvpl/gera_script/templates``."""
    return (
        importlib.resources.files("plugadvpl.gera_script.templates")
        .joinpath(name)
        .read_text("utf-8")
    )


def _normalize(text: str, newline: str) -> str:
    """Normaliza qualquer quebra para ``newline`` (determinístico)."""
    unix = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline == "\n":
        return unix
    return unix.replace("\n", newline)


def _inject_tq(base: str, tq_tmpl: str, with_tq: bool) -> str:
    """Substitui o marker TQ pelo bloco da fase (se ``with_tq``) ou remove a linha."""
    replacement = _load_template(tq_tmpl) if with_tq else ""
    return base.replace(_TQ_MARKER, replacement)


def emit_ps1(with_tq: bool = False) -> str:
    """Conteúdo do .ps1 (CRLF — convenção Windows/PowerShell)."""
    base = _inject_tq(_load_template(_PS1_TMPL), _TQ_PS1_TMPL, with_tq)
    return _normalize(base, "\r\n")


def emit_sh(with_tq: bool = False) -> str:
    """Conteúdo do .sh (LF)."""
    base = _inject_tq(_load_template(_SH_TMPL), _TQ_SH_TMPL, with_tq)
    return _normalize(base, "\n")


def emit_config_json(config: dict[str, str]) -> str:
    """Serializa o config em JSON estável (UTF-8, indent 2, ordem do dict)."""
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"
