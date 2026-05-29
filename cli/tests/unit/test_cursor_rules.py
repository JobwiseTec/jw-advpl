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

    def test_includes_globs_when_provided(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_rule(
            target, version="0.16.2", globs=["**/*.prw", "**/*.tlpp"]
        )
        assert "globs: **/*.prw, **/*.tlpp" in result

    def test_omits_globs_when_empty(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "init"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "globs:" not in result
        assert "alwaysApply: false" in result

    def test_includes_version_marker(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "<!-- plugadvpl-rule-version: 0.16.2 -->" in result

    def test_includes_skill_marker(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "callers"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "<!-- plugadvpl-skill: callers -->" in result

    def test_falls_back_when_no_frontmatter(self, tmp_path: Path) -> None:
        """SKILL.md sem frontmatter → description fallback usa nome da skill."""
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "grep"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("# Body only, no frontmatter\n", encoding="utf-8")
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "description: plugadvpl skill: grep" in result


class TestRenderGlobalRule:
    def test_always_apply_true(self) -> None:
        from plugadvpl.cursor_rules import render_global_rule
        result = render_global_rule(version="0.16.2")
        assert "alwaysApply: true" in result

    def test_no_globs_field(self) -> None:
        from plugadvpl.cursor_rules import render_global_rule
        result = render_global_rule(version="0.16.2")
        # Frontmatter não deve ter linha globs:
        lines = result.split("\n")
        frontmatter = []
        in_fm = False
        for line in lines:
            if line == "---":
                in_fm = not in_fm
                continue
            if in_fm:
                frontmatter.append(line)
        assert not any(line.startswith("globs:") for line in frontmatter)


class TestSkillGlobs:
    def test_has_52_skills(self) -> None:
        from plugadvpl.cursor_rules import _SKILL_GLOBS
        assert len(_SKILL_GLOBS) == 52

    def test_matches_actual_skill_dirs(self) -> None:
        """_SKILL_GLOBS deve bater com as skills embarcadas em skills/."""
        from plugadvpl.cursor_rules import _SKILL_GLOBS
        # Skills bundled no plugin (paths relativos ao repo root no dev tree)
        skills_dir = Path(__file__).resolve().parents[3] / "skills"
        if not skills_dir.exists():
            pytest.skip("dev tree only — skills/ não acessível neste contexto")
        actual = {p.name for p in skills_dir.iterdir() if (p / "SKILL.md").exists()}
        catalogued = set(_SKILL_GLOBS.keys())
        missing_in_constant = actual - catalogued
        extras_in_constant = catalogued - actual
        assert not missing_in_constant, (
            f"Skills sem entrada em _SKILL_GLOBS: {missing_in_constant}"
        )
        assert not extras_in_constant, (
            f"_SKILL_GLOBS tem entries inexistentes: {extras_in_constant}"
        )


class TestWriteRule:
    def test_writes_when_not_exists(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import _write_rule, WriteOutcome
        target = tmp_path / "plugadvpl-arch.mdc"
        outcome = _write_rule(target, "content with <!-- plugadvpl-rule-version: 0.16.2 -->")
        assert outcome == WriteOutcome.WRITTEN
        assert target.read_text(encoding="utf-8").startswith("content")

    def test_overwrites_when_marker_present(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import _write_rule, WriteOutcome
        target = tmp_path / "plugadvpl-arch.mdc"
        target.write_text(
            "old <!-- plugadvpl-rule-version: 0.15.0 -->", encoding="utf-8"
        )
        outcome = _write_rule(target, "new <!-- plugadvpl-rule-version: 0.16.2 -->")
        assert outcome == WriteOutcome.OVERWRITTEN
        assert "new" in target.read_text(encoding="utf-8")

    def test_skips_when_user_file_without_marker(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import _write_rule, WriteOutcome
        target = tmp_path / "plugadvpl-meu.mdc"
        target.write_text("my own rule, no marker", encoding="utf-8")
        outcome = _write_rule(target, "new content with marker")
        assert outcome == WriteOutcome.SKIPPED_USER_FILE
        # Preserva arquivo do user
        assert target.read_text(encoding="utf-8") == "my own rule, no marker"
