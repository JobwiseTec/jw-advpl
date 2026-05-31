"""Unit tests for plugadvpl/migrate_tlpp.py + migrate_tlpp_diff.py (v0.18.0+)."""
from __future__ import annotations

import subprocess
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


class TestPreFlight:
    def test_blocks_when_dirty_git(self, tmp_path: Path, monkeypatch) -> None:
        """git status --porcelain non-empty + sem --allow-dirty → bloqueio."""
        from plugadvpl.migrate_tlpp import MigrationPlan, _check_pre_flight

        def fake_run(cmd, **kw):
            class R:
                returncode = 0
                stdout = b" M file.txt\n"

            return R()

        monkeypatch.setattr(subprocess, "run", fake_run)
        # cria DB pra não disparar erro de ingest também
        (tmp_path / ".plugadvpl").mkdir()
        (tmp_path / ".plugadvpl" / "index.db").write_bytes(b"")
        plan = MigrationPlan(file_path=tmp_path / "a.prw", project_root=tmp_path)
        errors = _check_pre_flight(plan)
        assert any("git" in e.lower() for e in errors)

    def test_allows_dirty_with_override(self, tmp_path: Path, monkeypatch) -> None:
        from plugadvpl.migrate_tlpp import MigrationPlan, _check_pre_flight

        def fake_run(cmd, **kw):
            class R:
                returncode = 0
                stdout = b" M file.txt\n"

            return R()

        monkeypatch.setattr(subprocess, "run", fake_run)
        plan = MigrationPlan(
            file_path=tmp_path / "a.prw",
            project_root=tmp_path,
            allow_dirty=True,
            no_impact_check=True,
        )
        errors = _check_pre_flight(plan)
        # git error não aparece com allow_dirty=True
        assert not any("working tree" in e.lower() for e in errors)

    def test_blocks_when_db_not_ingested(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Sem .plugadvpl/index.db + sem --no-impact-check → bloqueio."""
        from plugadvpl.migrate_tlpp import MigrationPlan, _check_pre_flight

        def fake_run(cmd, **kw):
            class R:
                returncode = 0
                stdout = b""

            return R()

        monkeypatch.setattr(subprocess, "run", fake_run)
        plan = MigrationPlan(
            file_path=tmp_path / "a.prw",
            project_root=tmp_path,
            allow_dirty=True,
        )
        errors = _check_pre_flight(plan)
        assert any("ingest" in e.lower() or "db" in e.lower() for e in errors)


class TestDryRun:
    def test_safe_only_skips_idioms(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp import MigrationPlan, dry_run

        f = tmp_path / "a.prw"
        f.write_text("User Function X()\nReturn .T.\n", encoding="cp1252")
        plan = MigrationPlan(
            file_path=f,
            project_root=tmp_path,
            enable_idioms=False,
            no_impact_check=True,
            allow_dirty=True,
        )
        report = dry_run(plan)
        # 6 SAFE recipes rodados; 5 IDIOMS não devem aparecer no report
        ids_executed = {r.recipe_id for r in report.recipe_results}
        idioms_ids = {
            "namespace-infer",
            "begin-sequence-to-try",
            "conout-to-fwlog",
            "json-inline",
            "expand-truncated-names",
        }
        assert not (ids_executed & idioms_ids)

    def test_idioms_enabled_runs_all_11(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp import MigrationPlan, dry_run

        f = tmp_path / "SIGAFAT" / "a.prw"
        f.parent.mkdir()
        f.write_text("User Function X()\nReturn .T.\n", encoding="cp1252")
        plan = MigrationPlan(
            file_path=f,
            project_root=tmp_path,
            enable_idioms=True,
            no_impact_check=True,
            allow_dirty=True,
        )
        report = dry_run(plan)
        assert len(report.recipe_results) == 11

    def test_topological_order_preserved(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp import MigrationPlan, dry_run
        from plugadvpl.migrate_tlpp_recipes import CANONICAL_ORDER

        f = tmp_path / "a.prw"
        f.write_text("body", encoding="cp1252")
        plan = MigrationPlan(
            file_path=f,
            project_root=tmp_path,
            enable_idioms=True,
            no_impact_check=True,
            allow_dirty=True,
        )
        report = dry_run(plan)
        ids_executed = [r.recipe_id for r in report.recipe_results]
        # ids_executed deve ser subsequência preservando ordem de CANONICAL_ORDER
        idx_map = [CANONICAL_ORDER.index(i) for i in ids_executed]
        assert idx_map == sorted(idx_map), "ordem violada"

    def test_selected_recipes_filters_but_keeps_order(
        self, tmp_path: Path
    ) -> None:
        """selected_recipes=['header-includes', 'rename-extension'] aplica os 2
        mas em ordem canônica (rename=2, header=3 → header DEPOIS rename)."""
        from plugadvpl.migrate_tlpp import MigrationPlan, dry_run

        f = tmp_path / "a.prw"
        f.write_text("body", encoding="cp1252")
        plan = MigrationPlan(
            file_path=f,
            project_root=tmp_path,
            no_impact_check=True,
            allow_dirty=True,
            selected_recipes=("header-includes", "rename-extension"),
        )
        report = dry_run(plan)
        ids = [r.recipe_id for r in report.recipe_results]
        assert ids == ["rename-extension", "header-includes"]
