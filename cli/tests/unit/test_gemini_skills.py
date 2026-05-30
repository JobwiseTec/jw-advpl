"""Unit tests for plugadvpl/gemini_skills.py (v0.16.4+)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.gemini_skills import GeminiTarget, detect_gemini


class TestDetectGemini:
    def test_no_signals_returns_false_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem ~/.gemini/, sem gemini no PATH, sem .gemini/ no projeto → no-op."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_gemini(project)
        assert result == GeminiTarget(install_global=False, install_project=False)

    def test_home_gemini_dir_triggers_global_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`~/.gemini/` existe + sem .gemini/ projeto → só global=True (sinais INDEPENDENTES)."""
        fake_home = tmp_path / "home"
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_gemini(project)
        assert result.install_global is True
        assert result.install_project is False  # sinal global NÃO ativa project

    def test_project_gemini_dir_triggers_project_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.gemini/` no projeto + sem sinal home → só project=True."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".gemini").mkdir(parents=True)
        result = detect_gemini(project)
        assert result.install_global is False
        assert result.install_project is True

    def test_both_signals_returns_both_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = tmp_path / "home"
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".gemini").mkdir(parents=True)
        result = detect_gemini(project)
        assert result == GeminiTarget(install_global=True, install_project=True)

    def test_detect_gemini_in_path_triggers_global(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`shutil.which("gemini")` retorna path → install_global=True."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()  # sem .gemini/
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr(
            "plugadvpl.gemini_skills.shutil.which", lambda _: "/usr/local/bin/gemini"
        )
        project = tmp_path / "project"
        project.mkdir()
        result = detect_gemini(project)
        assert result.install_global is True
        assert result.install_project is False

    def test_handles_runtime_error_in_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Path.home() lança (container minimalista) → retorna (False, False)."""
        def boom() -> Path:
            raise RuntimeError("home unknown")
        monkeypatch.setattr(Path, "home", boom)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_gemini(project)
        assert result == GeminiTarget(install_global=False, install_project=False)
