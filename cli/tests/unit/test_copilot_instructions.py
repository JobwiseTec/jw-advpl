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
