"""Unit de codex_skills — suporte Codex first-class (v0.38.0)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.codex_skills import (
    detect_codex_skills,
    install_codex_skills,
    render_skill_for_codex,
)


class TestDetect:
    def test_project_when_dot_codex(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        (tmp_path / ".codex").mkdir()
        assert detect_codex_skills(tmp_path).install_project is True

    def test_project_when_dot_agents(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        (tmp_path / ".agents").mkdir()
        assert detect_codex_skills(tmp_path).install_project is True

    def test_no_project_when_neither(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.setattr("plugadvpl.codex_skills.shutil.which", lambda _: None)
        assert detect_codex_skills(tmp_path).install_project is False

    def test_global_only_if_home_agents_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home = tmp_path / "home"
        (home / ".agents").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: home)
        assert detect_codex_skills(tmp_path).install_global is True

    def test_no_global_when_home_agents_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        (tmp_path / ".codex").mkdir()
        assert detect_codex_skills(tmp_path).install_global is False


class TestRender:
    def test_frontmatter_name_description_marker_and_link(self, tmp_path: Path) -> None:
        sk = tmp_path / "advpl-encoding"
        sk.mkdir()
        (sk / "SKILL.md").write_text(
            "---\ndescription: Enc ADVPL\n---\nCorpo [[advpl-tlpp]].\n", encoding="utf-8"
        )
        out = render_skill_for_codex(sk / "SKILL.md", "0.38.0")
        assert "name: plugadvpl-advpl-encoding" in out
        assert "description: Enc ADVPL" in out
        assert "plugadvpl-codex-skill-version: 0.38.0" in out
        assert "[[plugadvpl-advpl-tlpp]]" in out  # link reescrito via _transform_body


class TestInstall:
    def test_writes_agents_and_codex(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        (tmp_path / ".codex").mkdir()
        r = install_codex_skills(tmp_path, "0.38.0")
        assert r.installed_agents_count > 0
        assert r.installed_codex_count > 0
        agents = list((tmp_path / ".agents" / "skills").glob("plugadvpl-*/SKILL.md"))
        codex = list((tmp_path / ".codex" / "skills").glob("plugadvpl-*/SKILL.md"))
        assert agents and codex
        # frontmatter name presente num exemplo
        sample = agents[0].read_text(encoding="utf-8")
        assert "name: plugadvpl-" in sample

    def test_global_written_when_home_agents_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home = tmp_path / "home"
        (home / ".agents").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: home)
        (tmp_path / ".codex").mkdir()
        r = install_codex_skills(tmp_path, "0.38.0")
        assert r.installed_global_count > 0
        assert list((home / ".agents" / "skills").glob("plugadvpl-*/SKILL.md"))

    def test_noop_when_not_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.setattr("plugadvpl.codex_skills.shutil.which", lambda _: None)
        r = install_codex_skills(tmp_path, "0.38.0")
        assert r.installed_agents_count == 0
        assert r.installed_codex_count == 0
