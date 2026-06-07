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
from dataclasses import dataclass, field
from pathlib import Path

from plugadvpl._skill_catalog import (
    _SKILL_GLOBS,
    GEMINI_MARKER_PREFIX,
    WriteOutcome,
    _parse_skill_md,
    _skills_root,
    _transform_body,
    _write_managed_file,
)


@dataclass(frozen=True)
class GeminiTarget:
    """Decisão do detect_gemini: o que instalar."""

    install_global: bool  # ~/.gemini/GEMINI.md
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

## Precisão — pegadinhas que enganam o agente

- **Resultado vazio nem sempre é "limpo".** `lint <arq>` vazio = código OK, OU arquivo **não
  indexado** (o comando avisa), OU índice **desatualizado** após upgrade. Se atualizou o
  plugadvpl, rode `uvx plugadvpl@__VERSION__ ingest --no-incremental` antes de confiar em
  `lint`/`arch` (o `--incremental` default pula arquivos inalterados, sem reaplicar regras novas).
- **Listas grandes truncam no `table`/`md`.** Lista completa: `--format json` (nunca trunca) ou
  `--limit 0` **antes** do subcomando (`--limit` é flag global).
- **PO UI:** `poui-componentes <po-comp>` / `<PoInterface>` (+`<prop>` filtra) / `schematics`;
  `poui-bridge` (front↔back REST); `poui-lint` (erros de PO UI gerado). Consulte ANTES de gerar.

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


def render_skill_for_gemini(skill_md_path: Path, version: str) -> str:
    """Gera `.gemini/skills/plugadvpl-<X>/SKILL.md`.

    Frontmatter Gemini é mais simples que Cursor/Copilot: só `name` +
    `description`. Sem `applyTo`/`globs`/`alwaysApply` (Gemini usa JIT
    scan + skill activation por descrição).

    Pipeline:
    1. Parse SKILL.md original (extrai description)
    2. _transform_body (slash→uvx + normalize)
    3. Frontmatter Gemini: name=plugadvpl-<X>, description=<da SKILL.md>
    4. Markers gemini-version + skill

    Edge case: SKILL.md sem frontmatter → description fallback usa skill_name.
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    frontmatter = f"---\nname: plugadvpl-{skill_name}\ndescription: {description}\n---\n"
    markers = (
        f"<!-- plugadvpl-gemini-version: {version} -->\n<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )
    return frontmatter + markers + _transform_body(body, version, style="plain")


@dataclass(frozen=True)
class InstallResult:
    """Resumo do install_gemini_skills."""

    installed_global_home: bool  # ~/.gemini/GEMINI.md
    installed_project_md: bool  # <project>/GEMINI.md
    installed_skills_count: int  # 0..52 (.gemini/skills/)
    installed_agents_skills_count: int = 0  # 0..52 (.agents/skills/ — v0.16.5+ cross-agent)
    skipped_due_to_user_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.installed_global_home:
            parts.append("1 home")
        if self.installed_project_md:
            parts.append("1 projeto")
        if self.installed_skills_count:
            parts.append(f"{self.installed_skills_count} skills (.gemini/)")
        if self.installed_agents_skills_count:
            parts.append(f"{self.installed_agents_skills_count} skills (.agents/)")
        return (" + ".join(parts) + " instaladas") if parts else "nada instalado"


def _install_gemini_global_home(version: str) -> tuple[bool, list[str], list[str]]:
    """Helper: install ~/.gemini/GEMINI.md.

    Returns (installed_bool, skipped_list, errors_list).
    """
    skipped: list[str] = []
    errors: list[str] = []
    try:
        global_path = Path.home() / ".gemini" / "GEMINI.md"
        outcome = _write_managed_file(
            global_path,
            render_global_gemini_md(version),
            GEMINI_MARKER_PREFIX,
        )
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return (True, skipped, errors)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append("~/.gemini/GEMINI.md (home)")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {global_path}: permission/IO denied")
        return (False, skipped, errors)
    except Exception as e:
        errors.append(f"global home erro: {e!r}")
        return (False, skipped, errors)


def _install_gemini_project_md(
    project_root: Path, version: str
) -> tuple[bool, list[str], list[str]]:
    """Helper: install <project>/GEMINI.md (4º gêmeo)."""
    skipped: list[str] = []
    errors: list[str] = []
    try:
        target = project_root / "GEMINI.md"
        outcome = _write_managed_file(
            target,
            render_global_gemini_md(version),
            GEMINI_MARKER_PREFIX,
        )
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return (True, skipped, errors)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append("GEMINI.md (projeto)")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {target}: permission/IO denied")
        return (False, skipped, errors)
    except Exception as e:
        errors.append(f"project MD erro: {e!r}")
        return (False, skipped, errors)


def _install_one_gemini_skill(
    skill_name: str,
    skills_root: Path,
    target_dir: Path,
    version: str,
) -> tuple[bool, list[str], list[str]]:
    """Helper: install <project>/.gemini/skills/plugadvpl-<X>/SKILL.md.

    Note: cria directory por skill (Gemini espera diretório, não arquivo flat).
    """
    skipped: list[str] = []
    errors: list[str] = []
    try:
        skill_md_path = skills_root / skill_name / "SKILL.md"
        if not skill_md_path.exists():
            errors.append(f"skill {skill_name}: SKILL.md ausente")
            return (False, skipped, errors)
        content = render_skill_for_gemini(skill_md_path, version)
        target_path = target_dir / f"plugadvpl-{skill_name}" / "SKILL.md"
        outcome = _write_managed_file(target_path, content, GEMINI_MARKER_PREFIX)
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return (True, skipped, errors)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append(f"plugadvpl-{skill_name}/SKILL.md")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {target_path}: permission/IO denied")
        return (False, skipped, errors)
    except Exception as e:
        errors.append(f"skill {skill_name}: {e!r}")
        return (False, skipped, errors)


def install_gemini_skills(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write pras GEMINI.md + skills Gemini.

    Spec §3.5 da Fase 3 + v0.16.5 §3.6 (.agents/skills/ cross-agent). NUNCA
    propaga exception — try/except em cada bloco + helpers
    (_install_gemini_global_home, _install_gemini_project_md,
    _install_one_gemini_skill) pra manter PLR0912 ≤12.
    """
    skipped: list[str] = []
    errors: list[str] = []
    installed_global_home = False
    installed_project_md = False
    installed_skills_count = 0
    installed_agents_skills_count = 0

    try:
        target = detect_gemini(project_root)
    except Exception as e:
        errors.append(f"detect_gemini falhou: {e!r}")
        return InstallResult(False, False, 0, 0, [], errors)

    if target.install_global:
        ok, skp, err = _install_gemini_global_home(version)
        installed_global_home = ok
        skipped.extend(skp)
        errors.extend(err)

    if target.install_project:
        ok, skp, err = _install_gemini_project_md(project_root, version)
        installed_project_md = ok
        skipped.extend(skp)
        errors.extend(err)

        # Install skills locais
        skills_target_dir = project_root / ".gemini" / "skills"
        try:
            skills_root = _skills_root()
        except Exception as e:
            errors.append(f"_skills_root falhou: {e!r}")
            return InstallResult(
                installed_global_home,
                installed_project_md,
                installed_skills_count,
                installed_agents_skills_count,
                skipped,
                errors,
            )

        for skill_name in _SKILL_GLOBS:  # iter keys
            ok, skp, err = _install_one_gemini_skill(
                skill_name, skills_root, skills_target_dir, version
            )
            if ok:
                installed_skills_count += 1
            skipped.extend(skp)
            errors.extend(err)

        # v0.16.5 — Se .agents/skills/ existe no projeto, instalar lá também
        # (cross-agent standard emergente — Codex, Roo, etc., tem precedência
        # maior que .gemini/skills/. Instalar em ambos cobre interop multi-tool
        # sem breaking change).
        agents_skills_dir = project_root / ".agents" / "skills"
        if agents_skills_dir.exists():
            for skill_name in _SKILL_GLOBS:
                ok, skp, err = _install_one_gemini_skill(
                    skill_name, skills_root, agents_skills_dir, version
                )
                if ok:
                    installed_agents_skills_count += 1
                skipped.extend(skp)
                errors.extend(err)

    return InstallResult(
        installed_global_home=installed_global_home,
        installed_project_md=installed_project_md,
        installed_skills_count=installed_skills_count,
        installed_agents_skills_count=installed_agents_skills_count,
        skipped_due_to_user_files=skipped,
        errors=errors,
    )
