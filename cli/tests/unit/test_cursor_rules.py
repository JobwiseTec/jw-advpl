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
        # v0.16.5 — usa nome NÃO-meta pra preservar semântica do teste
        # (verifica que globs vazios omitem a linha; alwaysApply: false default).
        # Meta-skills (init, ingest, etc.) agora ganham alwaysApply: true —
        # vide test_meta_skill_has_always_apply_true.
        skill_dir = tmp_path / "some-non-meta-skill"
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

    def test_render_skill_rule_uses_cursor_style_explicit(self, tmp_path: Path) -> None:
        """v0.16.5 — verifica output REAL contém literal `Bash: uvx plugadvpl@`.

        Antes do gap fix v0.16.5, Cursor compartilhava `_transform_body` que
        sempre emitia `Bash:`. Agora `_transform_body` default é 'plain'.
        cursor_rules.render_skill_rule DEVE passar style='cursor' explícito.
        Esta assertion bloqueia regressão: se alguém remover style="cursor",
        o output muda pra texto puro e o teste falha.
        """
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\nUse `/plugadvpl:arch`.\n",
            encoding="utf-8",
        )
        result = render_skill_rule(
            target, version="0.16.5", globs=["**/*.prw"]
        )
        # Strict assertion: literal Bash: prefix must appear
        assert "`Bash: uvx plugadvpl@0.16.5 arch`" in result

    def test_meta_skill_has_always_apply_true(self, tmp_path: Path) -> None:
        """v0.16.5 — Meta-skills (init, ingest, etc.) ganham alwaysApply: true."""
        from plugadvpl.cursor_rules import render_skill_rule
        # Skill 'init' está em _CURSOR_META_ALWAYS_APPLY
        skill_dir = tmp_path / "init"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        # globs vazio (init é meta sem escopo)
        result = render_skill_rule(target, version="0.16.5", globs=[])
        assert "alwaysApply: true" in result
        # E NÃO tem `globs:` (não tem escopo)
        # Pode ter dentro do body comments, mas no frontmatter NÃO
        lines = result.split("\n")
        in_fm = False
        fm_lines = []
        for line in lines:
            if line == "---":
                in_fm = not in_fm
                continue
            if in_fm:
                fm_lines.append(line)
        assert not any(line.startswith("globs:") for line in fm_lines)

    def test_non_meta_skill_without_globs_has_always_apply_false(self, tmp_path: Path) -> None:
        """v0.16.5 — Non-meta skill sem globs mantém alwaysApply: false (Manual only)."""
        from plugadvpl.cursor_rules import render_skill_rule
        # Skill name fictícia que NÃO está em _CURSOR_META_ALWAYS_APPLY
        skill_dir = tmp_path / "experimental-feature"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_rule(target, version="0.16.5", globs=[])
        assert "alwaysApply: false" in result


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


class TestCursorInstallResultSummary:
    def test_global_marked_experimental(self) -> None:
        """v0.16.5 — global mark com '(experimental)' pra sinalizar incerteza
        docs Cursor sobre ~/.cursor/rules/."""
        from plugadvpl.cursor_rules import InstallResult
        r = InstallResult(
            installed_global=True,
            installed_local_count=57,
            skipped_due_to_user_files=[],
            errors=[],
        )
        assert "global (experimental)" in r.summary()
        assert "57 locais" in r.summary()


class TestInstallCursorRules:
    def test_installs_global_and_locals_when_both_signals(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sinais completos → instala global + 52 locais. Smoke-end-to-end."""
        from plugadvpl.cursor_rules import install_cursor_rules
        fake_home = tmp_path / "home"
        (fake_home / ".cursor" / "rules").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".cursor").mkdir(parents=True)

        result = install_cursor_rules(project, version="0.16.2")

        assert result.installed_global is True
        assert result.installed_local_count == 62
        assert not result.errors
        # Smoke: arquivos foram criados
        assert (fake_home / ".cursor" / "rules" / "plugadvpl.mdc").exists()
        local_rules = list((project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(local_rules) == 62

    def test_no_op_when_no_signals(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from plugadvpl.cursor_rules import install_cursor_rules
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = install_cursor_rules(project, version="0.16.2")
        assert result.installed_global is False
        assert result.installed_local_count == 0
        assert not (fake_home / ".cursor" / "rules").exists()  # não criou
        assert not (project / ".cursor").exists()
