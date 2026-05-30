"""Unit tests for plugadvpl/codex_config.py (v0.16.5+)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.codex_config import (
    CodexTarget,
    detect_codex,
    install_codex_config,
    render_codex_config,
)


class TestDetectCodex:
    def test_no_signals_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem .codex/ no projeto, sem 'codex' no PATH → no-op."""
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_codex(project)
        assert result == CodexTarget(install_config=False)

    def test_codex_dir_in_project_triggers_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.codex/` no projeto → install_config=True."""
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".codex").mkdir(parents=True)
        result = detect_codex(project)
        assert result.install_config is True

    def test_codex_in_path_triggers_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`codex` no PATH → install_config=True."""
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: "/usr/local/bin/codex")
        project = tmp_path / "project"
        project.mkdir()
        result = detect_codex(project)
        assert result.install_config is True


class TestRenderCodexConfig:
    def test_includes_version_marker(self) -> None:
        result = render_codex_config(version="0.16.5")
        assert "# plugadvpl-codex-version: 0.16.5" in result

    def test_substitutes_version(self) -> None:
        result = render_codex_config(version="0.16.5")
        assert "__VERSION__" not in result
        assert "0.16.5" in result


class TestInstallCodexConfig:
    """Smoke test for the install_codex_config orchestrator (unit level)."""

    def test_no_op_without_signal(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = install_codex_config(project, version="0.16.5")
        assert result.installed is False
        assert result.error is None
