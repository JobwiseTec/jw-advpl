"""Unit tests for plugadvpl/agent_doctor.py (v0.16.5+)."""
from __future__ import annotations

from pathlib import Path

from plugadvpl.agent_doctor import (
    DoctorReport,
    check_claude_md,
    check_copilot_instructions,
    check_cursor_rules,
    check_gemini_skills,
    check_skill_descriptions_keywords,
    run_checks,
)


class TestCheckClaudeMd:
    def test_valid_claude_md(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text(
            "<!-- BEGIN plugadvpl -->\n"
            "<!-- plugadvpl-fragment-version: 0.16.5 -->\nBody\n"
            "<!-- END plugadvpl -->\n",
            encoding="utf-8",
        )
        result = check_claude_md(tmp_path, expected_version="0.16.5")
        assert result.status == "ok"

    def test_missing_claude_md(self, tmp_path: Path) -> None:
        result = check_claude_md(tmp_path, expected_version="0.16.5")
        assert result.status == "missing"


class TestCheckCursorRules:
    def test_valid_cursor_rules_directory(self, tmp_path: Path) -> None:
        rules_dir = tmp_path / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "plugadvpl-arch.mdc").write_text(
            "---\ndescription: X\nglobs: **/*.prw\nalwaysApply: false\n---\n"
            "<!-- plugadvpl-rule-version: 0.16.5 -->\nBody\n",
            encoding="utf-8",
        )
        result = check_cursor_rules(tmp_path, expected_version="0.16.5")
        assert result.status == "ok"
        assert "1 local" in result.detail

    def test_flags_cursor_globs_as_array(self, tmp_path: Path) -> None:
        """v0.16.5 — globs como array YAML é INCORRETO (deve ser string com vírgulas)."""
        rules_dir = tmp_path / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "plugadvpl-arch.mdc").write_text(
            "---\ndescription: X\nglobs:\n  - **/*.prw\nalwaysApply: false\n---\n"
            "<!-- plugadvpl-rule-version: 0.16.5 -->\nBody\n",
            encoding="utf-8",
        )
        result = check_cursor_rules(tmp_path, expected_version="0.16.5")
        assert result.status == "fail"
        assert "globs" in result.detail.lower()


class TestCheckCopilotInstructions:
    def test_valid_copilot_instructions(self, tmp_path: Path) -> None:
        inst_dir = tmp_path / ".github" / "instructions"
        inst_dir.mkdir(parents=True)
        (inst_dir / "plugadvpl-arch.instructions.md").write_text(
            '---\napplyTo: "**/*.prw"\ndescription: X\n---\n'
            "<!-- plugadvpl-instructions-version: 0.16.5 -->\nBody\n",
            encoding="utf-8",
        )
        result = check_copilot_instructions(tmp_path, expected_version="0.16.5")
        assert result.status == "ok"


class TestCheckGeminiSkills:
    def test_valid_gemini_skills(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".gemini" / "skills" / "plugadvpl-arch"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: plugadvpl-arch\ndescription: ADVPL arch\n---\n"
            "<!-- plugadvpl-gemini-version: 0.16.5 -->\nBody\n",
            encoding="utf-8",
        )
        result = check_gemini_skills(tmp_path, expected_version="0.16.5")
        assert result.status == "ok"


class TestKeywordsCheck:
    def test_flags_skill_without_advpl_keyword(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "myskill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A generic description\n---\nBody\n",
            encoding="utf-8",
        )
        flagged = check_skill_descriptions_keywords(tmp_path)
        assert "myskill" in flagged

    def test_does_not_flag_skill_with_advpl_keyword(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "myskill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: ADVPL Protheus stuff\n---\nBody\n",
            encoding="utf-8",
        )
        flagged = check_skill_descriptions_keywords(tmp_path)
        assert "myskill" not in flagged


class TestRunChecks:
    def test_run_all_checks_returns_report(self, tmp_path: Path) -> None:
        report = run_checks(tmp_path, expected_version="0.16.5")
        assert isinstance(report, DoctorReport)
        assert len(report.checks) >= 5  # CLAUDE, AGENTS, Cursor, Copilot, Gemini
