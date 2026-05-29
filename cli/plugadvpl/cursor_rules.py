"""Cursor Rules generator + installer pra plugadvpl init (v0.16.2+).

Detecta Cursor instalado e gera .cursor/rules/*.mdc files que dão ao Cursor
o mesmo contexto que CLAUDE.md/AGENTS.md dão pro Claude Code: convenções
ADVPL/TLPP, comandos do plugadvpl, encoding cp1252, tabela de decisão, etc.

Single source: skills/<X>/SKILL.md embarcadas geram .mdc em runtime via
2 substituições de string. Falha aqui NUNCA quebra o init.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CursorTarget:
    """Decisão do detect_cursor: o que instalar e onde."""

    install_global: bool   # ~/.cursor/rules/plugadvpl.mdc
    install_local: bool    # <project>/.cursor/rules/plugadvpl-*.mdc


def detect_cursor(project_root: Path) -> CursorTarget:
    """Decide o que instalar baseado em sinais conservadores.

    Global se ``~/.cursor/`` existe OU ``shutil.which("cursor")`` retorna path.
    Local se ``<project_root>/.cursor/`` existe.

    Conservador de propósito: não instalar `.cursor/rules/` num projeto onde
    o usuário nunca abriu Cursor é uma decisão de produto (evita pegada
    não-solicitada).
    """
    install_global = False
    install_local = False

    try:
        home = Path.home()
        if (home / ".cursor").exists():
            install_global = True
    except RuntimeError:
        # Container minimalista sem home — tudo False.
        return CursorTarget(install_global=False, install_local=False)

    if not install_global and shutil.which("cursor") is not None:
        install_global = True

    if (project_root / ".cursor").exists():
        install_local = True

    return CursorTarget(install_global=install_global, install_local=install_local)


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_DESC_RE = re.compile(r"^description:\s*(.+?)\s*$", re.MULTILINE)
_SLASH_RE = re.compile(r"/plugadvpl:([a-z0-9-]+)")
_UVX_VER_RE = re.compile(r"uvx plugadvpl@[\w.+-]+")


def _transform_body(body: str, version: str) -> str:
    """Aplica as 2 substituições da §3.3 do spec, NESTA ORDEM:

    3a) `/plugadvpl:<X>` → `` `Bash: uvx plugadvpl@<ver> <X>` ``
    3b) `uvx plugadvpl@<qualquer>` → `uvx plugadvpl@<ver>`

    Ordem importa: 3a primeiro emite uvx correto; 3b depois normaliza
    qualquer ocorrência pré-existente (ex: `uvx plugadvpl@0.15.0`).
    """
    body = _SLASH_RE.sub(rf"`Bash: uvx plugadvpl@{version} \1`", body)
    body = _UVX_VER_RE.sub(f"uvx plugadvpl@{version}", body)
    return body


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


def render_skill_rule(
    skill_md_path: Path, version: str, globs: list[str]
) -> str:
    """Gera conteúdo MDC pra `.cursor/rules/plugadvpl-<nome>.mdc`.

    Pipeline:
    1. Parse YAML frontmatter da SKILL.md (extrai `description`).
    2. Extrai body.
    3. Substitui `/plugadvpl:<X>` → `Bash: uvx plugadvpl@<ver> <X>`.
    4. Normaliza `uvx plugadvpl@<qualquer-ver>` → `uvx plugadvpl@<ver>`.
    5. Monta MDC com frontmatter (description + globs + alwaysApply=false) +
       markers de versão e skill.

    Edge case: SKILL.md sem/malformed frontmatter → description fallback.
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    # Frontmatter MDC (linha globs omitida se vazia).
    frontmatter_lines = [f"description: {description}"]
    if globs:
        frontmatter_lines.append(f"globs: {', '.join(globs)}")
    frontmatter_lines.append("alwaysApply: false")
    frontmatter = "---\n" + "\n".join(frontmatter_lines) + "\n---\n"

    markers = (
        f"<!-- plugadvpl-rule-version: {version} -->\n"
        f"<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )

    return frontmatter + markers + _transform_body(body, version)


_GLOBAL_DESCRIPTION = (
    "Convenções TOTVS Protheus (ADVPL/TLPP) + plugadvpl — "
    "índice local, encoding cp1252, comandos uvx, tabela de decisão"
)

_GLOBAL_BODY_TEMPLATE = """# plugadvpl — convenções ADVPL/TLPP (rule global)

Este projeto/workspace pode conter código TOTVS Protheus em **AdvPL** (`.prw`, `.prx`,
`.apw`) e **TLPP** (`.tlpp`). Se houver `.plugadvpl/index.db` no root do projeto, use
o índice via comandos `uvx plugadvpl@__VERSION__ <subcomando>` ANTES de ler `.prw`/`.tlpp`
cru — economiza ~16x tokens.

## Tabela de decisão — qual comando rodar antes de Read

| Pergunta | Comando |
|---|---|
| "explique o fonte X" / "o que faz Y" | `Bash: uvx plugadvpl@__VERSION__ arch <arq>` |
| "onde está a função X?" | `Bash: uvx plugadvpl@__VERSION__ find <nome>` |
| "quem chama X?" | `Bash: uvx plugadvpl@__VERSION__ callers <funcao>` |
| "o que X chama?" | `Bash: uvx plugadvpl@__VERSION__ callees <funcao>` |
| "quem mexe na tabela SA1?" | `Bash: uvx plugadvpl@__VERSION__ tables SA1` |
| "onde MV_LOCALIZA é usado?" | `Bash: uvx plugadvpl@__VERSION__ param MV_LOCALIZA` |
| "achar 'RecLock' nos fontes" | `Bash: uvx plugadvpl@__VERSION__ grep RecLock` |
| "tem problemas no fonte X?" | `Bash: uvx plugadvpl@__VERSION__ lint <arq>` |

## Encoding — CRÍTICO

- `.prw`/`.prx` são **cp1252**. Read/Write/Edit comuns são UTF-8 — bytes acentuados viram `�`.
- Antes de editar `.prw`: `Bash: uvx plugadvpl@__VERSION__ edit-prw stage <arq>` (converte pra UTF-8 com backup).
- Depois de editar: `Bash: uvx plugadvpl@__VERSION__ edit-prw commit <arq>` (volta pra cp1252).
- `.tlpp` é UTF-8 nativo — sem stage/commit.

## Workflow padrão pra "explique o programa X"

1. `Bash: uvx plugadvpl@__VERSION__ find X` — descobre arquivo
2. `Bash: uvx plugadvpl@__VERSION__ arch <arq>` — visão arquitetural
3. `Bash: uvx plugadvpl@__VERSION__ callees X` — o que X chama
4. `Bash: uvx plugadvpl@__VERSION__ callers X` — quem chama X
5. Só depois, se necessário, Read do arquivo com offset/limit do `arch`
"""


def render_global_rule(version: str) -> str:
    """Gera conteúdo MDC pra ``~/.cursor/rules/plugadvpl.mdc`` (rule global).

    Sempre injetado em qualquer arquivo aberto (``alwaysApply: true``).
    Sem ``globs`` — vale pra qualquer arquivo do workspace.
    """
    frontmatter = (
        "---\n"
        f"description: {_GLOBAL_DESCRIPTION}\n"
        "alwaysApply: true\n"
        "---\n"
    )
    markers = f"<!-- plugadvpl-rule-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return frontmatter + markers + body
