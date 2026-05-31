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


class TestConvertEncoding:
    """Recipe order 1 — converte cp1252 → utf-8 (marker no MVP)."""

    def test_idempotent_when_already_utf8(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.convert_encoding import ConvertEncoding

        content = "User Function X()\nReturn .T.\n"
        ctx = MigrationContext(file_path=tmp_path / "a.prw", project_root=tmp_path)
        r = ConvertEncoding().apply(content, ctx)
        assert r.status == "nochange"

    def test_recipe_id_and_category(self) -> None:
        from plugadvpl.migrate_tlpp_recipes.convert_encoding import ConvertEncoding

        assert ConvertEncoding.id == "convert-encoding"
        assert ConvertEncoding.category == "safe"

    def test_skip_when_tlpp_extension(self, tmp_path: Path) -> None:
        """Se path já é .tlpp, recipe vira nochange."""
        from plugadvpl.migrate_tlpp_recipes.convert_encoding import ConvertEncoding

        ctx = MigrationContext(file_path=tmp_path / "a.tlpp", project_root=tmp_path)
        r = ConvertEncoding().apply("body", ctx)
        assert r.status == "nochange"


class TestRenameExtension:
    """Recipe order 2 — marca .prw pra rename .tlpp."""

    def test_prw_returns_ok_with_content(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.rename_extension import RenameExtension

        ctx = MigrationContext(file_path=tmp_path / "FATA050.prw", project_root=tmp_path)
        r = RenameExtension().apply("body", ctx)
        assert r.status == "ok"
        assert r.new_content == "body"
        assert "FATA050" in r.message

    def test_tlpp_returns_nochange(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.rename_extension import RenameExtension

        ctx = MigrationContext(file_path=tmp_path / "a.tlpp", project_root=tmp_path)
        r = RenameExtension().apply("body", ctx)
        assert r.status == "nochange"

    def test_unknown_extension_returns_skipped(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.rename_extension import RenameExtension

        ctx = MigrationContext(file_path=tmp_path / "a.txt", project_root=tmp_path)
        r = RenameExtension().apply("body", ctx)
        assert r.status == "skipped"
