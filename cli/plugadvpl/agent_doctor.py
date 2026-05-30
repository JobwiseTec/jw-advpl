"""Multi-agent files validator (v0.16.5+).

Valida formato dos arquivos gerados por plugadvpl init pra 5 agentes
(Claude, Codex/AGENTS.md, Cursor, Copilot, Gemini) sem precisar instalar
os agentes externos. Pretende cobrir gaps que nao temos validacao E2E
real (Cursor nao tem CLI validate; Copilot nao tem diagnose; Gemini nao
tem agent-side check via CLI).

Spec: docs/superpowers/specs/2026-05-30-multi-agent-v0165-improvements.md secao 3.3
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

# Keywords minimas que SKILL.md descriptions devem conter pra Gemini JIT activation
_ADVPL_KEYWORDS = ("ADVPL", "Protheus", "TLPP", ".prw", "SX", "dicionário", "dicionario")

# Regex pra detectar array YAML multi-line: `globs:\n  -` (linha seguinte comeca com `-`)
_GLOBS_ARRAY_RE = re.compile(r"globs:\s*\n\s*-", re.MULTILINE)
_APPLY_TO_ARRAY_RE = re.compile(r"applyTo:\s*\n\s*-", re.MULTILINE)


@dataclass(frozen=True)
class AgentCheck:
    """Resultado de check de um agente especifico."""

    name: str  # "claude_md", "cursor_rules", etc.
    status: Literal["ok", "missing", "fail", "warning"]
    detail: str

    def emoji(self) -> str:
        return {"ok": "OK", "missing": "--", "fail": "FAIL", "warning": "WARN"}[self.status]


@dataclass(frozen=True)
class DoctorReport:
    """Agregado de checks por todos agentes."""

    checks: list[AgentCheck]
    skills_without_keywords: list[str] = field(default_factory=list)

    def has_failures(self) -> bool:
        return any(c.status in ("fail", "warning") for c in self.checks)


def _check_fragment_file(f: Path, name: str, expected_version: str) -> AgentCheck:
    """Helper compartilhado pra CLAUDE.md / AGENTS.md."""
    if not f.exists():
        return AgentCheck(name, "missing", f"{f.name} ausente (rode init?)")
    content = f.read_text(encoding="utf-8", errors="replace")
    if "<!-- BEGIN plugadvpl -->" not in content:
        return AgentCheck(name, "fail", "Fragment BEGIN/END markers ausentes")
    m = re.search(r"<!--\s*plugadvpl-fragment-version:\s*([\w.+-]+)\s*-->", content)
    if not m:
        return AgentCheck(name, "fail", "Marker version ausente")
    found_version = m.group(1)
    if found_version != expected_version:
        return AgentCheck(
            name,
            "warning",
            f"Versao {found_version} (esperado {expected_version}) — rode init pra atualizar",
        )
    return AgentCheck(name, "ok", f"OK ({found_version})")


def check_claude_md(root: Path, expected_version: str) -> AgentCheck:
    """Verifica CLAUDE.md fragment + marker version."""
    return _check_fragment_file(root / "CLAUDE.md", "claude_md", expected_version)


def check_agents_md(root: Path, expected_version: str) -> AgentCheck:
    """Similar a check_claude_md mas pra AGENTS.md."""
    return _check_fragment_file(root / "AGENTS.md", "agents_md", expected_version)


def _extract_frontmatter(content: str) -> str | None:
    """Retorna conteudo entre os `---` do frontmatter (None se ausente/malformado)."""
    if not content.startswith("---\n"):
        return None
    fm_end = content.find("\n---\n", 4)
    if fm_end == -1:
        return None
    return content[4:fm_end]


def check_cursor_rules(root: Path, expected_version: str) -> AgentCheck:
    """Verifica .cursor/rules/plugadvpl-*.mdc — globs deve ser STRING (nao array)."""
    rules_dir = root / ".cursor" / "rules"
    if not rules_dir.exists():
        return AgentCheck(
            "cursor_rules", "missing", ".cursor/rules/ ausente (Cursor nao detectado?)"
        )
    files = sorted(rules_dir.glob("plugadvpl-*.mdc"))
    if not files:
        return AgentCheck("cursor_rules", "missing", "Nenhum plugadvpl-*.mdc em .cursor/rules/")
    failed: list[str] = []
    stale: list[str] = []
    for f in files:
        content = f.read_text(encoding="utf-8", errors="replace")
        fm = _extract_frontmatter(content)
        if fm is None:
            failed.append(f"{f.name}: frontmatter ausente/malformado")
            continue
        # globs deve ser string (nao array YAML). Detect 2 formas:
        # (a) inline single-line: `globs: -` (valor comeca com `-` apos `globs:`)
        # (b) multi-line: `globs:\n  -` (linha seguinte do `globs:` comeca com `-`)
        if _GLOBS_ARRAY_RE.search(fm + "\n"):
            failed.append(f"{f.name}: globs e array YAML (deve ser string com virgulas)")
            continue
        for line in fm.split("\n"):
            if line.startswith("globs:"):
                value = line[len("globs:") :].strip()
                if value.startswith("-"):
                    failed.append(f"{f.name}: globs e array YAML (deve ser string com virgulas)")
                break
        # Marker version
        m = re.search(r"<!--\s*plugadvpl-rule-version:\s*([\w.+-]+)\s*-->", content)
        if m and m.group(1) != expected_version:
            stale.append(f"{f.name}: versao {m.group(1)}")
    if failed:
        return AgentCheck("cursor_rules", "fail", f"{len(failed)} files: {'; '.join(failed[:3])}")
    if stale:
        return AgentCheck("cursor_rules", "warning", f"{len(stale)} stale: {'; '.join(stale[:3])}")
    noun = "local" if len(files) == 1 else "locais"
    return AgentCheck("cursor_rules", "ok", f"{len(files)} {noun} OK")


def check_copilot_instructions(root: Path, expected_version: str) -> AgentCheck:
    """Verifica .github/instructions/plugadvpl-*.instructions.md."""
    inst_dir = root / ".github" / "instructions"
    if not inst_dir.exists():
        return AgentCheck("copilot_instructions", "missing", ".github/instructions/ ausente")
    files = sorted(inst_dir.glob("plugadvpl-*.instructions.md"))
    if not files:
        return AgentCheck(
            "copilot_instructions", "missing", "Nenhum arquivo plugadvpl-* encontrado"
        )
    failed: list[str] = []
    stale: list[str] = []
    for f in files:
        content = f.read_text(encoding="utf-8", errors="replace")
        # applyTo deve ser string UNICA (nao array)
        if _APPLY_TO_ARRAY_RE.search(content):
            failed.append(f"{f.name}: applyTo e array YAML (deve ser string)")
            continue
        m_apply = re.search(r'applyTo:\s*(["\']?)([^"\'\n]+)\1', content)
        if not m_apply:
            failed.append(f"{f.name}: applyTo ausente")
            continue
        m_ver = re.search(r"<!--\s*plugadvpl-instructions-version:\s*([\w.+-]+)\s*-->", content)
        if m_ver and m_ver.group(1) != expected_version:
            stale.append(f"{f.name}: versao {m_ver.group(1)}")
    if failed:
        return AgentCheck("copilot_instructions", "fail", "; ".join(failed[:3]))
    if stale:
        return AgentCheck("copilot_instructions", "warning", f"{len(stale)} stale")
    return AgentCheck("copilot_instructions", "ok", f"{len(files)} instructions OK")


def check_gemini_skills(root: Path, expected_version: str) -> AgentCheck:
    """Verifica .gemini/skills/plugadvpl-*/SKILL.md frontmatter."""
    skills_dir = root / ".gemini" / "skills"
    if not skills_dir.exists():
        return AgentCheck("gemini_skills", "missing", ".gemini/skills/ ausente")
    skill_files = sorted(skills_dir.glob("plugadvpl-*/SKILL.md"))
    if not skill_files:
        return AgentCheck("gemini_skills", "missing", "Nenhuma skill plugadvpl-*/SKILL.md")
    failed: list[str] = []
    stale: list[str] = []
    for f in skill_files:
        content = f.read_text(encoding="utf-8", errors="replace")
        fm = _extract_frontmatter(content)
        if fm is None:
            failed.append(f"{f.parent.name}: frontmatter ausente/malformado")
            continue
        if "name:" not in fm:
            failed.append(f"{f.parent.name}: sem 'name' field")
            continue
        if "description:" not in fm:
            failed.append(f"{f.parent.name}: sem 'description' field")
            continue
        m_ver = re.search(r"<!--\s*plugadvpl-gemini-version:\s*([\w.+-]+)\s*-->", content)
        if m_ver and m_ver.group(1) != expected_version:
            stale.append(f"{f.parent.name}: versao {m_ver.group(1)}")
    if failed:
        return AgentCheck("gemini_skills", "fail", "; ".join(failed[:3]))
    if stale:
        return AgentCheck("gemini_skills", "warning", f"{len(stale)} stale")
    return AgentCheck("gemini_skills", "ok", f"{len(skill_files)} skills OK")


def check_skill_descriptions_keywords(skills_root: Path) -> list[str]:
    """Lista SKILL.md cujas description NAO contem keywords ADVPL/Protheus.

    Returns: lista de skill names (basename do dir) flagged, sorted.
    """
    flagged: list[str] = []
    for skill_md in skills_root.rglob("SKILL.md"):
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"^description:\s*(.+?)$", content, re.MULTILINE)
        if not m:
            continue
        desc = m.group(1)
        if not any(kw.lower() in desc.lower() for kw in _ADVPL_KEYWORDS):
            flagged.append(skill_md.parent.name)
    return sorted(flagged)


def run_checks(root: Path, expected_version: str) -> DoctorReport:
    """Executa todos checks. Retorna DoctorReport agregado."""
    checks = [
        check_claude_md(root, expected_version),
        check_agents_md(root, expected_version),
        check_cursor_rules(root, expected_version),
        check_copilot_instructions(root, expected_version),
        check_gemini_skills(root, expected_version),
    ]
    # Skills keywords check (se skills/ existe no root)
    skills_root = root / "skills"
    flagged: list[str] = []
    if skills_root.exists():
        flagged = check_skill_descriptions_keywords(skills_root)
    return DoctorReport(checks=checks, skills_without_keywords=flagged)
