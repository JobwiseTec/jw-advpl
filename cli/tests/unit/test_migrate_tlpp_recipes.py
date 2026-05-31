"""Unit tests for plugadvpl/migrate_tlpp_recipes/ (v0.18.0+)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.migrate_tlpp_recipes import (
    CANONICAL_ORDER,
    REGISTRY,
    MigrationContext,
    RecipeResult,
)


class TestRecipeResult:
    def test_default_status_is_ok(self) -> None:
        r = RecipeResult(recipe_id="x")
        assert r.status == "ok"
        assert r.diff == ""
        assert r.message == ""
        assert r.todo_markers == []

    def test_frozen_dataclass(self) -> None:
        r = RecipeResult(recipe_id="x")
        with pytest.raises(Exception):
            r.status = "error"  # type: ignore[misc]


class TestMigrationContext:
    def test_default_idioms_false(self, tmp_path: Path) -> None:
        ctx = MigrationContext(file_path=tmp_path / "a.prw", project_root=tmp_path)
        assert ctx.enable_idioms is False
        assert ctx.tlpp_version == (0, 0, 0)
        assert ctx.db_connection is None


class TestRegistry:
    def test_registry_has_all_11_recipes(self) -> None:
        """v0.18.0 spec §3.5 lista 11 recipes (6 SAFE + 5 IDIOMS)."""
        from plugadvpl.migrate_tlpp_recipes import _register_all

        _register_all()
        assert len(REGISTRY) == 11

    def test_canonical_order_matches_spec(self) -> None:
        """Spec §3.6 ordem canônica fixa."""
        expected = [
            "convert-encoding",
            "rename-extension",
            "header-includes",
            "remove-public-default",
            "user-function-lowercase",
            "named-args",
            "namespace-infer",
            "begin-sequence-to-try",
            "conout-to-fwlog",
            "json-inline",
            "expand-truncated-names",
        ]
        assert CANONICAL_ORDER == expected
