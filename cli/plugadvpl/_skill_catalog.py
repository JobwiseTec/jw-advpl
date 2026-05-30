"""Skill catalog + helpers neutros — compartilhados entre cursor_rules e
copilot_instructions (v0.16.3+).

Fonte canônica de:
- `_SKILL_GLOBS`: dict[str, list[str]] com 52 skills + seus globs
- Regex constants (frontmatter, description, slash, uvx version)
- Helpers puros: `_parse_skill_md`, `_transform_body`, `_skills_root`
- `WriteOutcome` enum + `_write_managed_file` (idempotência via marker)
- `RULE_MARKER_PREFIX` (Cursor) e `INSTRUCTIONS_MARKER_PREFIX` (Copilot) — DISTINTOS
  pra evitar falso-positivo entre os 2 agentes
"""

from __future__ import annotations

import enum
import re
from importlib import resources as ir
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Marker prefixes — narrow por agente (NÃO unificar; spec §3.1)
# ---------------------------------------------------------------------------

RULE_MARKER_PREFIX = "<!-- plugadvpl-rule-version:"
INSTRUCTIONS_MARKER_PREFIX = "<!-- plugadvpl-instructions-version:"
GEMINI_MARKER_PREFIX = "<!-- plugadvpl-gemini-version:"

# ---------------------------------------------------------------------------
# Skill catalog (spec §5)
# ---------------------------------------------------------------------------

_PRW = ["**/*.prw", "**/*.tlpp", "**/*.prx", "**/*.apw"]
_PRW_CSV = ["**/*.prw", "**/*.tlpp", "**/*.prx", "**/*.csv"]

_SKILL_GLOBS: dict[str, list[str]] = {
    # ADVPL/TLPP source skills
    "arch": _PRW,
    "find": _PRW,
    "callers": _PRW,
    "callees": _PRW,
    "lint": _PRW,
    "grep": _PRW,
    "compile": _PRW,
    "tq": _PRW,
    "edit-prw": _PRW,
    "deploy": _PRW,
    "hotspots": _PRW,
    "metrics": _PRW,
    "cobertura-doc": _PRW,
    "plugadvpl-index-usage": _PRW,
    # Knowledge / reference skills
    "advpl-advanced": _PRW,
    "advpl-code-review": _PRW,
    "advpl-debugging": _PRW,
    "advpl-dicionario-sx": _PRW,
    "advpl-dicionario-sx-validacoes": _PRW,
    "advpl-embedded-sql": _PRW,
    "advpl-encoding": _PRW,
    "advpl-fundamentals": _PRW,
    "advpl-jobs-rpc": _PRW,
    "advpl-matxfis": _PRW,
    "advpl-mvc": _PRW,
    "advpl-mvc-avancado": _PRW,
    "advpl-pontos-entrada": _PRW,
    "advpl-refactoring": _PRW,
    "advpl-tlpp": _PRW,
    "advpl-tlpp-named-params": _PRW,
    "advpl-web": _PRW,
    "advpl-webservice": _PRW,
    # SX dictionary skills (incluindo CSV)
    "tables": _PRW_CSV,
    "param": _PRW_CSV,
    "impacto": _PRW_CSV,
    "gatilho": _PRW_CSV,
    "ingest-sx": _PRW_CSV,
    "sx-status": _PRW_CSV,
    # Contexto específico
    "ini-audit": ["**/*.ini"],
    "log-diagnose": ["**/*.log"],
    # Meta-skills — sem escopo
    "init": [],
    "ingest": [],
    "status": [],
    "doctor": [],
    "reindex": [],
    "help": [],
    "workflow": [],
    "execauto": [],
    "docs": [],
    "trace": [],
    "setup": [],
    "ingest-protheus": [],
}

# v0.16.5 — Meta-skills sem glob específico mas que carregam contexto
# transversal. Cursor deve sempre injetá-las (alwaysApply: true) em vez
# de relegar pra "Manual only" mode (que exige @plugadvpl-init explícito).
_CURSOR_META_ALWAYS_APPLY: set[str] = {
    "init", "ingest", "status", "doctor", "help",
    "workflow", "trace", "setup", "ingest-protheus",
    "reindex", "execauto", "docs",
}

# ---------------------------------------------------------------------------
# Frontmatter / body parsing
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_DESC_RE = re.compile(r"^description:\s*(.+?)\s*$", re.MULTILINE)


def _parse_skill_md(skill_md_text: str) -> tuple[str, str]:
    """Extrai (description, body) de uma SKILL.md.

    Retorna fallback `("", body inteiro)` se não houver frontmatter parseável.
    """
    m = _FRONTMATTER_RE.match(skill_md_text)
    if m is None:
        return ("", skill_md_text)
    frontmatter, body = m.group(1), m.group(2)
    desc_match = _DESC_RE.search(frontmatter)
    description = desc_match.group(1) if desc_match else ""
    return (description, body)


# ---------------------------------------------------------------------------
# Body transformations (slash → uvx + version normalize)
# ---------------------------------------------------------------------------

_SLASH_RE = re.compile(r"/plugadvpl:([a-z0-9-]+)")
_UVX_VER_RE = re.compile(r"uvx plugadvpl@[\w.+-]+")


def _transform_body(body: str, version: str, style: Literal["cursor", "plain"] = "plain") -> str:
    """Aplica 2 substituições NESTA ORDEM:

    3a) `/plugadvpl:<X>` → comando substituído (formato por agente)
    3b) `uvx plugadvpl@<qualquer>` → `uvx plugadvpl@<ver>`

    Args:
        body: conteúdo a transformar.
        version: versão runtime (substitui placeholders).
        style: "cursor" emite `` `Bash: uvx plugadvpl@<ver> <X>` `` (MDC syntax);
               "plain" emite `uvx plugadvpl@<ver> <X>` (texto puro pro Copilot/Gemini).
               Default "plain" (safer; Copilot/Gemini interpretam Bash: como literal).

    Cursor MDC interpreta backticks + Bash: como hint de comando inline;
    Copilot/Gemini interpretam só texto puro.
    """
    if style == "cursor":
        body = _SLASH_RE.sub(rf"`Bash: uvx plugadvpl@{version} \1`", body)
    else:  # plain
        body = _SLASH_RE.sub(rf"uvx plugadvpl@{version} \1", body)
    body = _UVX_VER_RE.sub(f"uvx plugadvpl@{version}", body)
    return body


# ---------------------------------------------------------------------------
# Skills directory resolution (dev tree vs wheel)
# ---------------------------------------------------------------------------


def _skills_root() -> Path:
    """Localiza skills/ tanto em dev tree quanto em wheel.

    Tenta importlib.resources primeiro; se a skill embarcada não existir
    (caso: dev tree onde skills/ não é packaged), cai pro repo root
    relativo ao __init__.py do plugadvpl.
    """
    try:
        test = ir.files("plugadvpl") / "skills"
        with ir.as_file(test) as resolved:
            if (resolved / "arch" / "SKILL.md").exists():
                return resolved
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        pass
    # Fallback dev tree
    import plugadvpl

    pkg_init = Path(plugadvpl.__file__).resolve()
    return pkg_init.parents[2] / "skills"


# ---------------------------------------------------------------------------
# File write policy (idempotência via marker)
# ---------------------------------------------------------------------------


class WriteOutcome(enum.Enum):
    """Resultado de tentar escrever um arquivo gerenciado."""

    WRITTEN = "written"
    OVERWRITTEN = "overwritten"
    SKIPPED_USER_FILE = "skipped_user_file"
    ERROR = "error"


def _write_managed_file(target_path: Path, content: str, marker_substring: str) -> WriteOutcome:
    """Escreve ou skipa um arquivo seguindo a política de marker (spec §6.1).

    - Não existe → escreve (WRITTEN).
    - Existe + contém `marker_substring` → sobrescreve (OVERWRITTEN).
    - Existe sem marker → skipa (SKIPPED_USER_FILE), preserva arquivo.
    - PermissionError/OSError → ERROR.

    `marker_substring` é OBRIGATÓRIO (sem default) — caller passa
    `RULE_MARKER_PREFIX` (Cursor) ou `INSTRUCTIONS_MARKER_PREFIX` (Copilot).
    Distinto por agente evita falso-positivo (`<!-- plugadvpl-skill: -->`
    em body não confunde com marker de versão).
    """
    try:
        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            return WriteOutcome.WRITTEN
        existing = target_path.read_text(encoding="utf-8", errors="replace")
        if marker_substring in existing:
            target_path.write_text(content, encoding="utf-8")
            return WriteOutcome.OVERWRITTEN
        return WriteOutcome.SKIPPED_USER_FILE
    except OSError:
        return WriteOutcome.ERROR
