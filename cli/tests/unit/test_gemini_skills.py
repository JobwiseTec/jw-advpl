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


class TestRenderGlobalGeminiMd:
    def test_includes_version_marker(self) -> None:
        from plugadvpl.gemini_skills import render_global_gemini_md
        result = render_global_gemini_md(version="0.16.4")
        assert "<!-- plugadvpl-gemini-version: 0.16.4 -->" in result

    def test_no_frontmatter(self) -> None:
        """GEMINI.md é markdown plano — sem frontmatter ---."""
        from plugadvpl.gemini_skills import render_global_gemini_md
        result = render_global_gemini_md(version="0.16.4")
        assert not result.startswith("---\n")

    def test_substitutes_version_in_body(self) -> None:
        from plugadvpl.gemini_skills import render_global_gemini_md
        result = render_global_gemini_md(version="0.16.4")
        assert "uvx plugadvpl@0.16.4" in result
        assert "__VERSION__" not in result


class TestRenderSkillForGemini:
    def test_includes_name_field(self, tmp_path: Path) -> None:
        """Frontmatter Gemini tem `name: plugadvpl-<X>` (skill_name com prefixo)."""
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "name: plugadvpl-arch" in result

    def test_includes_description_from_skill(self, tmp_path: Path) -> None:
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: Visao arquitetural\n---\nBody\n", encoding="utf-8"
        )
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "description: Visao arquitetural" in result

    def test_no_apply_to_field(self, tmp_path: Path) -> None:
        """Gemini não tem applyTo — confirmar AUSÊNCIA (vs Copilot)."""
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "applyTo:" not in result

    def test_includes_version_and_skill_markers(self, tmp_path: Path) -> None:
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "callers"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "<!-- plugadvpl-gemini-version: 0.16.4 -->" in result
        assert "<!-- plugadvpl-skill: callers -->" in result

    def test_falls_back_when_no_frontmatter(self, tmp_path: Path) -> None:
        """SKILL.md sem frontmatter → description fallback `plugadvpl skill: <name>`."""
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "grep"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("# Body only, no frontmatter\n", encoding="utf-8")
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "description: plugadvpl skill: grep" in result

    def test_transforms_body_substitutions(self, tmp_path: Path) -> None:
        """Body transforma `/plugadvpl:X` → uvx (texto puro pro Gemini).

        v0.16.5: Gemini usa style='plain' — antes assumia `Bash:` prefix
        por engano (era falso-positivo herdado do Cursor).
        """
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\n"
            "Use `/plugadvpl:arch` antes de Read.\n",
            encoding="utf-8",
        )
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "uvx plugadvpl@0.16.4 arch" in result
        assert "/plugadvpl:arch" not in result

    def test_render_skill_for_gemini_emits_plain_text_command(self, tmp_path: Path) -> None:
        """v0.16.5 — Gemini deve receber texto puro, NÃO `Bash:` (Cursor MDC)."""
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\nUse `/plugadvpl:arch`.\n",
            encoding="utf-8",
        )
        result = render_skill_for_gemini(target, version="0.16.5")
        # Plain style
        assert "uvx plugadvpl@0.16.5 arch" in result
        assert "Bash:" not in result
        assert "`Bash:" not in result


class TestInstallGeminiSkills:
    def test_installs_all_three_layers_when_signals_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """~/.gemini/ + .gemini/ projeto → home + project MD + 60 skills."""
        from plugadvpl.gemini_skills import install_gemini_skills
        fake_home = tmp_path / "home"
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".gemini").mkdir(parents=True)

        result = install_gemini_skills(project, version="0.16.4")

        assert result.installed_global_home is True
        assert result.installed_project_md is True
        assert result.installed_skills_count == 62
        assert not result.errors
        # Files exist
        assert (fake_home / ".gemini" / "GEMINI.md").exists()
        assert (project / "GEMINI.md").exists()
        skill_files = list(
            (project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md")
        )
        assert len(skill_files) == 62

    def test_no_op_without_signals(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from plugadvpl.gemini_skills import install_gemini_skills
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = install_gemini_skills(project, version="0.16.4")
        assert result.installed_global_home is False
        assert result.installed_project_md is False
        assert result.installed_skills_count == 0
        assert not (fake_home / ".gemini" / "GEMINI.md").exists()
        assert not (project / "GEMINI.md").exists()
        assert not (project / ".gemini").exists()

    def test_installs_to_agents_skills_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v0.16.5 — `.agents/skills/` no projeto → instala lá também (paralelo a .gemini/skills/)."""
        from plugadvpl.gemini_skills import install_gemini_skills
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".gemini").mkdir(parents=True)
        (project / ".agents" / "skills").mkdir(parents=True)

        result = install_gemini_skills(project, version="0.16.5")

        # Instala em ambos
        gemini_files = list(
            (project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md")
        )
        agents_files = list(
            (project / ".agents" / "skills").glob("plugadvpl-*/SKILL.md")
        )
        assert len(gemini_files) == 62
        assert len(agents_files) == 62
        assert result.installed_skills_count == 62
        assert result.installed_agents_skills_count == 62

    def test_no_install_to_agents_skills_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v0.16.5 — `.agents/skills/` NÃO existe → NÃO cria a pasta."""
        from plugadvpl.gemini_skills import install_gemini_skills
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".gemini").mkdir(parents=True)
        # Sem .agents/ no projeto

        result = install_gemini_skills(project, version="0.16.5")

        # .gemini/skills instala normal
        gemini_files = list(
            (project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md")
        )
        assert len(gemini_files) == 62
        # .agents/ NÃO foi criado
        assert not (project / ".agents").exists()
        assert result.installed_agents_skills_count == 0
