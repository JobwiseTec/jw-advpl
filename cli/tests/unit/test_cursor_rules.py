"""Unit tests for plugadvpl/cursor_rules.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.cursor_rules import CursorTarget, detect_cursor


class TestDetectCursor:
    def test_no_signals_returns_false_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem ~/.cursor/ nem .cursor/ no projeto, sem 'cursor' no PATH → no-op."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_cursor(project)
        assert result == CursorTarget(install_global=False, install_local=False)

    def test_home_cursor_dir_triggers_global(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """~/.cursor/ existe → install_global=True."""
        fake_home = tmp_path / "home"
        (fake_home / ".cursor").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_cursor(project)
        assert result.install_global is True
        assert result.install_local is False

    def test_project_cursor_dir_triggers_local(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """.cursor/ no projeto → install_local=True."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".cursor").mkdir(parents=True)
        result = detect_cursor(project)
        assert result.install_global is False
        assert result.install_local is True

    def test_both_signals_returns_both_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = tmp_path / "home"
        (fake_home / ".cursor").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".cursor").mkdir(parents=True)
        result = detect_cursor(project)
        assert result == CursorTarget(install_global=True, install_local=True)

    def test_cursor_in_path_triggers_global(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """shutil.which('cursor') retorna path → install_global=True (sinal alternativo)."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()  # sem .cursor/
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr(
            "plugadvpl.cursor_rules.shutil.which", lambda _: "/usr/local/bin/cursor"
        )
        project = tmp_path / "project"
        project.mkdir()
        result = detect_cursor(project)
        assert result.install_global is True

    def test_handles_runtime_error_in_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Path.home() lança (container minimalista) → retorna (False, False)."""
        def boom() -> Path:
            raise RuntimeError("home unknown")
        monkeypatch.setattr(Path, "home", boom)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_cursor(project)
        assert result == CursorTarget(install_global=False, install_local=False)


class TestRenderSkillRule:
    def test_extracts_description_from_frontmatter(self, tmp_path: Path) -> None:
        """Parse YAML frontmatter → captura description pro frontmatter MDC."""
        from plugadvpl.cursor_rules import render_skill_rule
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\n"
            "description: Visao arquitetural de um arquivo ADVPL/TLPP\n"
            "arguments: [arquivo]\n"
            "---\n"
            "\n"
            "# Body\n",
            encoding="utf-8",
        )
        result = render_skill_rule(skill, version="0.16.2", globs=[])
        assert "description: Visao arquitetural de um arquivo ADVPL/TLPP" in result

    def test_substitutes_slash_to_uvx(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\n"
            "# `/plugadvpl:arch`\n"
            "\n"
            "Use `/plugadvpl:arch <arq>` antes de Read.\n",
            encoding="utf-8",
        )
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "`Bash: uvx plugadvpl@0.16.2 arch`" in result
        assert "/plugadvpl:arch" not in result  # substituiu todas as ocorrências

    def test_normalizes_old_uvx_version(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\n"
            "```bash\nuvx plugadvpl@0.15.0 --format md arch $arquivo\n```\n",
            encoding="utf-8",
        )
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "uvx plugadvpl@0.16.2" in result
        assert "uvx plugadvpl@0.15.0" not in result
