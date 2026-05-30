"""GitHub Copilot Instructions generator + installer pra plugadvpl init (v0.16.3+).

Detecta `.github/` no projeto e gera:
- `.github/copilot-instructions.md` (global, markdown plano, repo-wide)
- `.github/instructions/plugadvpl-<X>.instructions.md` (52 specifics com applyTo glob)

Fonte: skills/<X>/SKILL.md embarcadas (via _skill_catalog._SKILL_GLOBS).
Compartilha helpers com cursor_rules via plugadvpl._skill_catalog (DRY).

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from plugadvpl._skill_catalog import _parse_skill_md, _transform_body


@dataclass(frozen=True)
class CopilotTarget:
    """Decisão do detect_copilot: o que instalar."""

    install_global: bool   # .github/copilot-instructions.md
    install_local: bool    # .github/instructions/plugadvpl-*.instructions.md


def detect_copilot(project_root: Path) -> CopilotTarget:
    """Política simples: `.github/` no projeto → instala ambos.

    Menos conservador que detect_cursor — copilot-instructions.md é
    markdown inerte pra quem não usa Copilot (sem efeito colateral),
    e `.github/` é convenção amplamente adotada em projetos GitHub.
    """
    if (project_root / ".github").exists():
        return CopilotTarget(install_global=True, install_local=True)
    return CopilotTarget(install_global=False, install_local=False)


_GLOBAL_BODY_TEMPLATE = """# Convenções TOTVS Protheus (ADVPL/TLPP) + plugadvpl

Este repositório contém código TOTVS Protheus em **AdvPL** (`.prw`, `.prx`,
`.apw`) e **TLPP** (`.tlpp`). Se `.plugadvpl/index.db` existe no root, use
o índice via `uvx plugadvpl@__VERSION__ <subcomando>` ANTES de ler `.prw`/`.tlpp`
cru — economiza ~16x tokens.

## Tabela de decisão — qual comando rodar antes de Read

| Pergunta | Comando |
|---|---|
| "explique o fonte X" / "o que faz Y" | `uvx plugadvpl@__VERSION__ arch <arq>` |
| "onde está a função X?" | `uvx plugadvpl@__VERSION__ find <nome>` |
| "quem chama X?" | `uvx plugadvpl@__VERSION__ callers <funcao>` |
| "o que X chama?" | `uvx plugadvpl@__VERSION__ callees <funcao>` |
| "quem mexe na tabela SA1?" | `uvx plugadvpl@__VERSION__ tables SA1` |
| "onde MV_LOCALIZA é usado?" | `uvx plugadvpl@__VERSION__ param MV_LOCALIZA` |
| "achar 'RecLock' nos fontes" | `uvx plugadvpl@__VERSION__ grep RecLock` |
| "tem problemas no fonte X?" | `uvx plugadvpl@__VERSION__ lint <arq>` |

## Encoding — CRÍTICO

- `.prw`/`.prx` são **cp1252**. Read/Write/Edit comuns são UTF-8 — bytes acentuados viram `�`.
- Antes de editar `.prw`: `uvx plugadvpl@__VERSION__ edit-prw stage <arq>` (converte pra UTF-8 com backup).
- Depois de editar: `uvx plugadvpl@__VERSION__ edit-prw commit <arq>` (volta pra cp1252).
- `.tlpp` é UTF-8 nativo — sem stage/commit.

## Workflow padrão pra "explique o programa X"

1. `uvx plugadvpl@__VERSION__ find X` — descobre arquivo
2. `uvx plugadvpl@__VERSION__ arch <arq>` — visão arquitetural
3. `uvx plugadvpl@__VERSION__ callees X` — o que X chama
4. `uvx plugadvpl@__VERSION__ callers X` — quem chama X
5. Só depois, se necessário, leia o arquivo com offset/limit do `arch`
"""


def render_global_instructions(version: str) -> str:
    """Gera conteúdo de `.github/copilot-instructions.md` (global Copilot file).

    Markdown plano sem frontmatter (padrão Copilot). Marker de versão
    no topo. ~60 linhas no body — respeitando soft limit de ~2 páginas
    documentado pelo GitHub Copilot.
    """
    markers = f"<!-- plugadvpl-instructions-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return markers + body


def render_skill_instructions(
    skill_md_path: Path, version: str, globs: list[str]
) -> str:
    """Gera `.github/instructions/plugadvpl-<skill>.instructions.md`.

    Pipeline (similar a render_skill_rule do Cursor):
    1. Parse SKILL.md frontmatter (description)
    2. Body extraction
    3. _transform_body (slash→uvx + version normalize)
    4. Monta frontmatter Copilot:
       - applyTo (STRING com globs joined por vírgula; '**/*' se vazio)
       - description
    5. Markers de versão + skill

    Edge case: SKILL.md sem frontmatter → description fallback usa skill_name.
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    # applyTo é STRING única no Copilot (Cursor usa array)
    apply_to = ",".join(globs) if globs else "**/*"

    frontmatter = (
        "---\n"
        f'applyTo: "{apply_to}"\n'
        f"description: {description}\n"
        "---\n"
    )
    markers = (
        f"<!-- plugadvpl-instructions-version: {version} -->\n"
        f"<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )
    return frontmatter + markers + _transform_body(body, version)
