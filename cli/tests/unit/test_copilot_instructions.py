"""Unit tests for plugadvpl/copilot_instructions.py (v0.16.3+)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.copilot_instructions import CopilotTarget, detect_copilot


class TestDetectCopilot:
    def test_no_github_returns_false_false(self, tmp_path: Path) -> None:
        """Projeto sem .github/ → no-op."""
        project = tmp_path / "project"
        project.mkdir()
        result = detect_copilot(project)
        assert result == CopilotTarget(install_global=False, install_local=False)

    def test_with_github_returns_both_true(self, tmp_path: Path) -> None:
        """`.github/` no projeto → instala global + locais."""
        project = tmp_path / "project"
        (project / ".github").mkdir(parents=True)
        result = detect_copilot(project)
        assert result == CopilotTarget(install_global=True, install_local=True)


class TestRenderGlobalInstructions:
    def test_includes_version_marker(self) -> None:
        from plugadvpl.copilot_instructions import render_global_instructions
        result = render_global_instructions(version="0.16.3")
        assert "<!-- plugadvpl-instructions-version: 0.16.3 -->" in result

    def test_no_frontmatter(self) -> None:
        """Copilot global file é markdown plano — sem frontmatter ---."""
        from plugadvpl.copilot_instructions import render_global_instructions
        result = render_global_instructions(version="0.16.3")
        # Não começa com ---
        assert not result.startswith("---\n")

    def test_substitutes_version_in_body(self) -> None:
        """Body deve ter `uvx plugadvpl@<ver>` em vez de placeholder."""
        from plugadvpl.copilot_instructions import render_global_instructions
        result = render_global_instructions(version="0.16.3")
        assert "uvx plugadvpl@0.16.3" in result
        assert "__VERSION__" not in result


class TestRenderSkillInstructions:
    def test_includes_apply_to_as_string(self, tmp_path: Path) -> None:
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_instructions(
            target, version="0.16.3", globs=["**/*.prw", "**/*.tlpp"]
        )
        # Copilot espera applyTo como string única (com vírgulas), não array YAML
        assert 'applyTo: "**/*.prw,**/*.tlpp"' in result

    def test_empty_globs_uses_wildcard(self, tmp_path: Path) -> None:
        """Meta-skills (globs=[]) → applyTo: '**/*' (aplica sempre)."""
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "init"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_instructions(target, version="0.16.3", globs=[])
        assert 'applyTo: "**/*"' in result

    def test_includes_description_from_skill_frontmatter(self, tmp_path: Path) -> None:
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: Visao arquitetural\n---\nBody\n", encoding="utf-8"
        )
        result = render_skill_instructions(target, version="0.16.3", globs=[])
        assert "description: Visao arquitetural" in result

    def test_includes_version_and_skill_markers(self, tmp_path: Path) -> None:
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "callers"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_instructions(target, version="0.16.3", globs=[])
        assert "<!-- plugadvpl-instructions-version: 0.16.3 -->" in result
        assert "<!-- plugadvpl-skill: callers -->" in result

    def test_transforms_body_substitutions(self, tmp_path: Path) -> None:
        """Body deve transformar `/plugadvpl:X` → uvx (texto puro pro Copilot).

        v0.16.5: Copilot usa style='plain' — antes assumia `Bash:` prefix
        por engano (era falso-positivo herdado do Cursor).
        """
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\n"
            "Use `/plugadvpl:arch` antes de Read.\n",
            encoding="utf-8",
        )
        result = render_skill_instructions(target, version="0.16.3", globs=[])
        assert "uvx plugadvpl@0.16.3 arch" in result
        assert "/plugadvpl:arch" not in result

    def test_render_skill_instructions_emits_plain_text_command(self, tmp_path: Path) -> None:
        """v0.16.5 — Copilot deve receber texto puro, NÃO `Bash:` (Cursor MDC)."""
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\nUse `/plugadvpl:arch`.\n",
            encoding="utf-8",
        )
        result = render_skill_instructions(
            target, version="0.16.5", globs=["**/*.prw"]
        )
        # Plain style: command em texto, sem Bash:
        assert "uvx plugadvpl@0.16.5 arch" in result
        assert "Bash:" not in result
        assert "`Bash:" not in result


class TestInstallCopilotInstructions:
    def test_installs_global_and_locals_when_github_exists(
        self, tmp_path: Path
    ) -> None:
        """`.github/` no projeto → 1 global + 52 specifics gerados."""
        from plugadvpl.copilot_instructions import install_copilot_instructions
        project = tmp_path / "project"
        (project / ".github").mkdir(parents=True)
        result = install_copilot_instructions(project, version="0.16.3")
        assert result.installed_global is True
        assert result.installed_local_count == 54
        assert not result.errors
        # Files
        assert (project / ".github" / "copilot-instructions.md").exists()
        instructions = list(
            (project / ".github" / "instructions").glob("plugadvpl-*.instructions.md")
        )
        assert len(instructions) == 54

    def test_no_op_without_github(self, tmp_path: Path) -> None:
        from plugadvpl.copilot_instructions import install_copilot_instructions
        project = tmp_path / "project"
        project.mkdir()
        result = install_copilot_instructions(project, version="0.16.3")
        assert result.installed_global is False
        assert result.installed_local_count == 0
        assert not (project / ".github").exists()
