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
