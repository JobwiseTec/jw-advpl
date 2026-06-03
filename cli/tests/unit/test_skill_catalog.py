"""Unit tests for plugadvpl/_skill_catalog.py (refactor v0.16.3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl._skill_catalog import (
    INSTRUCTIONS_MARKER_PREFIX,
    RULE_MARKER_PREFIX,
    WriteOutcome,
    _parse_skill_md,
    _skills_root,
    _SKILL_GLOBS,
    _transform_body,
    _write_managed_file,
)


class TestSkillGlobs:
    def test_has_59_skills(self) -> None:
        assert len(_SKILL_GLOBS) == 59

    def test_matches_actual_skill_dirs(self) -> None:
        """_SKILL_GLOBS deve bater com as skills embarcadas em skills/."""
        skills_dir = Path(__file__).resolve().parents[3] / "skills"
        if not skills_dir.exists():
            pytest.skip("dev tree only — skills/ não acessível neste contexto")
        actual = {p.name for p in skills_dir.iterdir() if (p / "SKILL.md").exists()}
        catalogued = set(_SKILL_GLOBS.keys())
        missing = actual - catalogued
        extras = catalogued - actual
        assert not missing, f"Skills sem entrada em _SKILL_GLOBS: {missing}"
        assert not extras, f"_SKILL_GLOBS tem entries inexistentes: {extras}"


class TestParseSkillMd:
    def test_extracts_description_from_frontmatter(self) -> None:
        text = (
            "---\n"
            "description: Visao arquitetural de um arquivo ADVPL/TLPP\n"
            "arguments: [arquivo]\n"
            "---\n"
            "# Body\n"
        )
        desc, body = _parse_skill_md(text)
        assert desc == "Visao arquitetural de um arquivo ADVPL/TLPP"
        assert body == "# Body\n"

    def test_falls_back_when_no_frontmatter(self) -> None:
        text = "# Body only, no frontmatter\n"
        desc, body = _parse_skill_md(text)
        assert desc == ""
        assert body == text


class TestTransformBody:
    def test_substitutes_slash_to_uvx(self) -> None:
        body = "Use `/plugadvpl:arch <arq>` antes de Read.\n"
        result = _transform_body(body, version="0.16.3")
        # v0.16.5: default style mudou pra 'plain' (Copilot/Gemini-safe).
        assert "uvx plugadvpl@0.16.3 arch" in result
        assert "/plugadvpl:arch" not in result

    def test_normalizes_old_uvx_version(self) -> None:
        body = "```bash\nuvx plugadvpl@0.15.0 --format md arch $arquivo\n```\n"
        result = _transform_body(body, version="0.16.3")
        assert "uvx plugadvpl@0.16.3" in result
        assert "uvx plugadvpl@0.15.0" not in result

    def test_cursor_style_emits_bash_prefix(self) -> None:
        """style='cursor' → backtick + 'Bash:' prefix (MDC syntax)."""
        body = "Use `/plugadvpl:arch` antes de Read.\n"
        result = _transform_body(body, version="0.16.5", style="cursor")
        assert "`Bash: uvx plugadvpl@0.16.5 arch`" in result
        assert "/plugadvpl:arch" not in result

    def test_plain_style_emits_text(self) -> None:
        """style='plain' → texto puro (Copilot/Gemini)."""
        body = "Use `/plugadvpl:arch` antes de Read.\n"
        result = _transform_body(body, version="0.16.5", style="plain")
        assert "uvx plugadvpl@0.16.5 arch" in result
        assert "Bash:" not in result
        assert "`Bash:" not in result
        assert "/plugadvpl:arch" not in result

    def test_default_style_is_plain(self) -> None:
        """Sem param style → default 'plain' (safer, conservador)."""
        body = "Use `/plugadvpl:arch` antes de Read.\n"
        result = _transform_body(body, version="0.16.5")  # no style arg
        assert "uvx plugadvpl@0.16.5 arch" in result
        assert "Bash:" not in result


class TestWriteManagedFile:
    def test_writes_when_not_exists(self, tmp_path: Path) -> None:
        target = tmp_path / "plugadvpl-arch.mdc"
        outcome = _write_managed_file(
            target,
            "content with <!-- plugadvpl-rule-version: 0.16.3 -->",
            RULE_MARKER_PREFIX,
        )
        assert outcome == WriteOutcome.WRITTEN
        assert target.read_text(encoding="utf-8").startswith("content")

    def test_overwrites_when_rule_marker_present(self, tmp_path: Path) -> None:
        target = tmp_path / "plugadvpl-arch.mdc"
        target.write_text(
            "old <!-- plugadvpl-rule-version: 0.15.0 -->", encoding="utf-8"
        )
        outcome = _write_managed_file(
            target,
            "new <!-- plugadvpl-rule-version: 0.16.3 -->",
            RULE_MARKER_PREFIX,
        )
        assert outcome == WriteOutcome.OVERWRITTEN
        assert "new" in target.read_text(encoding="utf-8")

    def test_skips_when_user_file_without_marker(self, tmp_path: Path) -> None:
        target = tmp_path / "plugadvpl-meu.mdc"
        target.write_text("my own rule, no marker", encoding="utf-8")
        outcome = _write_managed_file(
            target, "new content", RULE_MARKER_PREFIX
        )
        assert outcome == WriteOutcome.SKIPPED_USER_FILE
        assert target.read_text(encoding="utf-8") == "my own rule, no marker"

    def test_distinct_marker_does_not_match_other_agent(self, tmp_path: Path) -> None:
        """v0.16.3 — marker do Cursor (rule-version) não matcha policy do Copilot
        (instructions-version), evitando overwrite cross-agent."""
        target = tmp_path / "plugadvpl-arch.mdc"
        target.write_text(
            "cursor file <!-- plugadvpl-rule-version: 0.16.3 -->",
            encoding="utf-8",
        )
        # Tenta sobrescrever como se fosse arquivo Copilot
        outcome = _write_managed_file(
            target, "would overwrite", INSTRUCTIONS_MARKER_PREFIX
        )
        assert outcome == WriteOutcome.SKIPPED_USER_FILE
        # Preserva original — não confundiu os 2 markers
        assert "cursor file" in target.read_text(encoding="utf-8")
