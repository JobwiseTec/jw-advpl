"""Unit tests for plugadvpl/migrate_tlpp.py + migrate_tlpp_diff.py (v0.18.0+)."""
from __future__ import annotations

from pathlib import Path

from plugadvpl.migrate_tlpp_diff import has_changes, unified_diff_text


class TestUnifiedDiffText:
    def test_returns_empty_when_identical(self) -> None:
        result = unified_diff_text("x\ny\n", "x\ny\n", "a.prw", "a.tlpp")
        assert result == ""

    def test_includes_headers_and_changes(self) -> None:
        result = unified_diff_text(
            "User Function X()\n", "function u_x()\n", "a.prw", "a.tlpp"
        )
        assert "--- a.prw" in result
        assert "+++ a.tlpp" in result
        assert "-User Function X()" in result
        assert "+function u_x()" in result


class TestHasChanges:
    def test_true_when_differ(self) -> None:
        assert has_changes("a", "b") is True

    def test_false_when_identical(self) -> None:
        assert has_changes("x", "x") is False


class TestMigrationDataclasses:
    def test_plan_default_idioms_false(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp import MigrationPlan

        plan = MigrationPlan(file_path=tmp_path / "a.prw", project_root=tmp_path)
        assert plan.enable_idioms is False
        assert plan.tlpp_version == (0, 0, 0)
        assert plan.allow_dirty is False
        assert plan.no_impact_check is False

    def test_report_aggregates_by_status(self) -> None:
        from plugadvpl.migrate_tlpp import MigrationReport
        from plugadvpl.migrate_tlpp_recipes import RecipeResult

        report = MigrationReport(
            file_path=Path("a.prw"),
            recipe_results=[
                RecipeResult(recipe_id="r1", status="ok"),
                RecipeResult(recipe_id="r2", status="ok"),
                RecipeResult(recipe_id="r3", status="nochange"),
                RecipeResult(recipe_id="r4", status="needs-review"),
            ],
        )
        assert report.counts() == {"ok": 2, "nochange": 1, "needs-review": 1}
