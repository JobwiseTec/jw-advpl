"""Cursor Rules generator + installer pra plugadvpl init (v0.16.2+).

Detecta Cursor instalado e gera .cursor/rules/*.mdc files que dão ao Cursor
o mesmo contexto que CLAUDE.md/AGENTS.md dão pro Claude Code: convenções
ADVPL/TLPP, comandos do plugadvpl, encoding cp1252, tabela de decisão, etc.

Single source: skills/<X>/SKILL.md embarcadas geram .mdc em runtime via
2 substituições de string. Falha aqui NUNCA quebra o init.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from plugadvpl._skill_catalog import (
    _CURSOR_META_ALWAYS_APPLY,
    _SKILL_GLOBS,
    RULE_MARKER_PREFIX,
    WriteOutcome,
    _parse_skill_md,
    _skills_root,
    _transform_body,
    _write_managed_file,
)


@dataclass(frozen=True)
class CursorTarget:
    """Decisão do detect_cursor: o que instalar e onde."""

    install_global: bool  # ~/.cursor/rules/plugadvpl.mdc
    install_local: bool  # <project>/.cursor/rules/plugadvpl-*.mdc


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


def render_skill_rule(skill_md_path: Path, version: str, globs: list[str]) -> str:
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

    # v0.16.5 — Meta-skills sem globs ganham alwaysApply: true pra evitar
    # virar "Manual only" no Cursor. Demais (mesmo sem globs) ficam false.
    is_meta_always = skill_name in _CURSOR_META_ALWAYS_APPLY and not globs
    always_apply = "true" if is_meta_always else "false"

    # Frontmatter MDC (linha globs omitida se vazia).
    frontmatter_lines = [f"description: {description}"]
    if globs:
        frontmatter_lines.append(f"globs: {', '.join(globs)}")
    frontmatter_lines.append(f"alwaysApply: {always_apply}")
    frontmatter = "---\n" + "\n".join(frontmatter_lines) + "\n---\n"

    markers = (
        f"<!-- plugadvpl-rule-version: {version} -->\n<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )

    return frontmatter + markers + _transform_body(body, version, style="cursor")


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
    frontmatter = f"---\ndescription: {_GLOBAL_DESCRIPTION}\nalwaysApply: true\n---\n"
    markers = f"<!-- plugadvpl-rule-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return frontmatter + markers + body


@dataclass(frozen=True)
class InstallResult:
    """Resumo do install_cursor_rules — quanto foi instalado + warnings."""

    installed_global: bool
    installed_local_count: int  # 0..52
    skipped_due_to_user_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """String curta pra `init` printar.

        v0.16.5: rotula 'global' como '(experimental)' — Cursor docs oficial
        não confirma que ~/.cursor/rules/ é lido (User Rules globais são
        UI-only, Cursor Settings → Rules). Mantemos por compat futura
        mas sinalizamos a incerteza pro user.
        """
        parts = []
        if self.installed_global:
            parts.append("1 global (experimental)")
        if self.installed_local_count:
            parts.append(f"{self.installed_local_count} locais")
        return (" + ".join(parts) + " instaladas") if parts else "nada instalado"


def _install_global_rule(version: str, skipped: list[str], errors: list[str]) -> bool:
    """Escreve ~/.cursor/rules/plugadvpl.mdc. NUNCA propaga exception."""
    try:
        global_path = Path.home() / ".cursor" / "rules" / "plugadvpl.mdc"
        outcome = _write_managed_file(global_path, render_global_rule(version), RULE_MARKER_PREFIX)
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return True
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append("plugadvpl.mdc (global)")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {global_path}: permission/IO denied")
    except Exception as e:
        errors.append(f"global rule erro: {e!r}")
    return False


def _install_one_local_rule(
    skill_name: str,
    globs: list[str],
    skills_root: Path,
    local_dir: Path,
    version: str,
    skipped: list[str],
    errors: list[str],
) -> bool:
    """Escreve uma rule local `.cursor/rules/plugadvpl-<X>.mdc`."""
    try:
        skill_md_path = skills_root / skill_name / "SKILL.md"
        if not skill_md_path.exists():
            errors.append(f"skill {skill_name}: SKILL.md ausente no wheel")
            return False
        content = render_skill_rule(skill_md_path, version, globs)
        target_path = local_dir / f"plugadvpl-{skill_name}.mdc"
        outcome = _write_managed_file(target_path, content, RULE_MARKER_PREFIX)
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return True
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append(f"plugadvpl-{skill_name}.mdc")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {target_path}: permission/IO denied")
    except Exception as e:
        errors.append(f"skill {skill_name}: {e!r}")
    return False


def install_cursor_rules(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write pras rules Cursor.

    Spec §3.4. NUNCA propaga exception — top-level try captura tudo, init
    nunca quebra por causa do Cursor.
    """
    skipped: list[str] = []
    errors: list[str] = []
    installed_global = False
    installed_local_count = 0

    try:
        target = detect_cursor(project_root)
    except Exception as e:
        errors.append(f"detect_cursor falhou: {e!r}")
        return InstallResult(
            installed_global=False,
            installed_local_count=0,
            skipped_due_to_user_files=[],
            errors=errors,
        )

    if target.install_global:
        installed_global = _install_global_rule(version, skipped, errors)

    if target.install_local:
        local_dir = project_root / ".cursor" / "rules"
        try:
            skills_root = _skills_root()
        except Exception as e:
            errors.append(f"_skills_root falhou: {e!r}")
            return InstallResult(
                installed_global=installed_global,
                installed_local_count=installed_local_count,
                skipped_due_to_user_files=skipped,
                errors=errors,
            )
        for skill_name, globs in _SKILL_GLOBS.items():
            if _install_one_local_rule(
                skill_name, globs, skills_root, local_dir, version, skipped, errors
            ):
                installed_local_count += 1

    return InstallResult(
        installed_global=installed_global,
        installed_local_count=installed_local_count,
        skipped_due_to_user_files=skipped,
        errors=errors,
    )
