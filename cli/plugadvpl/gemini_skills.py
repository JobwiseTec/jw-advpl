"""Google Gemini CLI native skills generator + installer (v0.16.4+).

Detecta Gemini instalado (~/.gemini/ no home OU 'gemini' no PATH OU .gemini/
no projeto) e gera:
- ~/.gemini/GEMINI.md (global home — só se ~/.gemini/ existe)
- <project>/GEMINI.md (4º gêmeo CLAUDE.md + AGENTS.md + GEMINI.md)
- <project>/.gemini/skills/plugadvpl-<X>/SKILL.md (52 specifics)

Sinais SÃO independentes — sinal global (~/.gemini/ ou gemini PATH) NÃO
ativa project install (consistente com Cursor policy).

Reusa _skill_catalog (DRY com cursor_rules + copilot_instructions).

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeminiTarget:
    """Decisão do detect_gemini: o que instalar."""

    install_global: bool   # ~/.gemini/GEMINI.md
    install_project: bool  # <project>/GEMINI.md + .gemini/skills/plugadvpl-*/SKILL.md


def detect_gemini(project_root: Path) -> GeminiTarget:
    """Decide o que instalar baseado em sinais conservadores e INDEPENDENTES.

    Global se ``~/.gemini/`` existe OU ``shutil.which("gemini")`` retorna path.
    Project se ``<project_root>/.gemini/`` existe.

    Conservador de propósito — sinal global NÃO ativa project install (evita
    pegada não-solicitada em projeto onde Gemini nunca foi usado especificamente).
    """
    install_global = False
    install_project = False

    try:
        home = Path.home()
        if (home / ".gemini").exists():
            install_global = True
    except RuntimeError:
        # Container minimalista sem home — tudo False.
        return GeminiTarget(install_global=False, install_project=False)

    if not install_global and shutil.which("gemini") is not None:
        install_global = True

    if (project_root / ".gemini").exists():
        install_project = True

    return GeminiTarget(install_global=install_global, install_project=install_project)


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

## Skills locais

Este projeto tem `.gemini/skills/plugadvpl-*/SKILL.md` com instruções
específicas por subcomando. Use `/memory show` pra ver todas carregadas.
"""


def render_global_gemini_md(version: str) -> str:
    """Gera conteúdo de GEMINI.md (global home ou projeto root).

    Markdown plano com marker plugadvpl-gemini-version no topo. ~80 linhas
    no body — Gemini concatena GEMINI.md hierarquicamente, então enxuto.
    """
    markers = f"<!-- plugadvpl-gemini-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return markers + body
