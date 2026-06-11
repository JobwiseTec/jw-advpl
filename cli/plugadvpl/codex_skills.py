"""OpenAI Codex CLI native skills generator + installer (v0.38.0+).

Instala as skills do plugadvpl como skills NATIVAS do Codex. Diretórios
(verificado na doc oficial OpenAI Codex, jun/2026):
- ``<project>/.agents/skills/plugadvpl-<X>/SKILL.md`` — CANÔNICO (open agent
  skills standard; Codex faz auto-discovery)
- ``<project>/.codex/skills/plugadvpl-<X>/SKILL.md`` — legado experimental
  (dez/2025); instalado também por compat com versões antigas do Codex
- ``~/.agents/skills/plugadvpl-<X>/SKILL.md`` — global, SÓ se ``~/.agents``
  já existe (nunca cria home; blindado contra erro de permissão)

SKILL.md exige frontmatter ``name`` + ``description`` (open agent skills
standard — o mesmo do Claude Code, interoperável).

Este módulo é DONO de ``.agents/skills`` (gemini_skills.py cedeu o cross-write
pra evitar colisão de marker). Reusa ``_skill_catalog`` (DRY).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from plugadvpl._skill_catalog import (
    _SKILL_GLOBS,
    CODEX_SKILL_MARKER_PREFIX,
    WriteOutcome,
    _parse_skill_md,
    _skills_root,
    _transform_body,
    _write_managed_file,
)


@dataclass(frozen=True)
class CodexSkillsTarget:
    """Decisão do detect_codex_skills."""

    install_project: bool  # .agents/skills + .codex/skills no projeto
    install_global: bool  # ~/.agents/skills (só se ~/.agents já existe)


def detect_codex_skills(project_root: Path) -> CodexSkillsTarget:
    """Detection conservadora.

    Project se ``.codex/`` OU ``.agents/`` no projeto OU ``codex`` no PATH.
    Global apenas se ``~/.agents/`` já existe (nunca cria home).
    """
    install_project = (project_root / ".codex").exists() or (project_root / ".agents").exists()
    if not install_project and shutil.which("codex") is not None:
        install_project = True

    install_global = False
    try:
        if (Path.home() / ".agents").exists():
            install_global = True
    except RuntimeError:
        install_global = False

    return CodexSkillsTarget(install_project=install_project, install_global=install_global)


def render_skill_for_codex(skill_md_path: Path, version: str) -> str:
    """Gera o conteúdo de ``.agents/skills/plugadvpl-<X>/SKILL.md`` pro Codex.

    Frontmatter ``name`` + ``description`` (open agent skills standard).
    Pipeline: parse SKILL.md → frontmatter → marker codex-skill →
    ``_transform_body`` (slash→uvx + normalize + links [[plugadvpl-*]]).
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    frontmatter = f"---\nname: plugadvpl-{skill_name}\ndescription: {description}\n---\n"
    markers = (
        f"<!-- plugadvpl-codex-skill-version: {version} -->"
        f"\n<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )
    return frontmatter + markers + _transform_body(body, version, style="plain")


@dataclass(frozen=True)
class InstallResult:
    """Resumo do install_codex_skills."""

    installed_agents_count: int = 0  # .agents/skills (canônico)
    installed_codex_count: int = 0  # .codex/skills (legado)
    installed_global_count: int = 0  # ~/.agents/skills
    skipped_due_to_user_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.installed_agents_count:
            parts.append(f"{self.installed_agents_count} skills (.agents/)")
        if self.installed_codex_count:
            parts.append(f"{self.installed_codex_count} skills (.codex/)")
        if self.installed_global_count:
            parts.append(f"{self.installed_global_count} skills (~/.agents/)")
        return (" + ".join(parts) + " instaladas") if parts else "nada instalado"


def _install_one_codex_skill(
    skill_name: str, skills_root: Path, target_dir: Path, version: str
) -> tuple[bool, list[str], list[str]]:
    """Escreve ``<target_dir>/plugadvpl-<X>/SKILL.md``. Nunca propaga exceção.

    Returns (installed_bool, skipped_list, errors_list).
    """
    skipped: list[str] = []
    errors: list[str] = []
    try:
        skill_md_path = skills_root / skill_name / "SKILL.md"
        if not skill_md_path.exists():
            errors.append(f"skill {skill_name}: SKILL.md ausente")
            return (False, skipped, errors)
        content = render_skill_for_codex(skill_md_path, version)
        target_path = target_dir / f"plugadvpl-{skill_name}" / "SKILL.md"
        outcome = _write_managed_file(target_path, content, CODEX_SKILL_MARKER_PREFIX)
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return (True, skipped, errors)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append(f"plugadvpl-{skill_name}/SKILL.md ({target_dir.name})")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {target_path}: permission/IO denied")
        return (False, skipped, errors)
    except Exception as e:  # blindagem: nunca derruba o init
        errors.append(f"skill {skill_name} ({target_dir.name}): {e!r}")
        return (False, skipped, errors)


def _install_into_dir(
    skills_root: Path, target_dir: Path, version: str
) -> tuple[int, list[str], list[str]]:
    """Instala todas as skills em ``target_dir``. Returns (count, skipped, errors)."""
    count = 0
    skipped: list[str] = []
    errors: list[str] = []
    for skill_name in _SKILL_GLOBS:
        ok, skp, err = _install_one_codex_skill(skill_name, skills_root, target_dir, version)
        if ok:
            count += 1
        skipped.extend(skp)
        errors.extend(err)
    return (count, skipped, errors)


def install_codex_skills(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write. NUNCA propaga exceção."""
    skipped: list[str] = []
    errors: list[str] = []
    agents_count = codex_count = global_count = 0

    try:
        target = detect_codex_skills(project_root)
    except Exception as e:
        return InstallResult(errors=[f"detect_codex_skills falhou: {e!r}"])

    if not target.install_project:
        return InstallResult()

    try:
        skills_root = _skills_root()
    except Exception as e:
        return InstallResult(errors=[f"_skills_root falhou: {e!r}"])

    # Canônico (.agents/skills) + legado (.codex/skills)
    agents_count, skp, err = _install_into_dir(
        skills_root, project_root / ".agents" / "skills", version
    )
    skipped.extend(skp)
    errors.extend(err)
    codex_count, skp, err = _install_into_dir(
        skills_root, project_root / ".codex" / "skills", version
    )
    skipped.extend(skp)
    errors.extend(err)

    # Global (~/.agents/skills) — só se ~/.agents já existe
    if target.install_global:
        try:
            global_dir = Path.home() / ".agents" / "skills"
            global_count, skp, err = _install_into_dir(skills_root, global_dir, version)
            skipped.extend(skp)
            errors.extend(err)
        except Exception as e:
            errors.append(f"global ~/.agents/skills erro: {e!r}")

    return InstallResult(
        installed_agents_count=agents_count,
        installed_codex_count=codex_count,
        installed_global_count=global_count,
        skipped_due_to_user_files=skipped,
        errors=errors,
    )
