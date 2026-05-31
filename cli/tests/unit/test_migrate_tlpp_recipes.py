"""Unit tests for plugadvpl/migrate_tlpp_recipes/ (v0.18.0+)."""
from __future__ import annotations

import sqlite3
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


class TestHeaderIncludes:
    """Recipe order 3 — protheus.ch → totvs.ch + tlpp-core.th."""

    def test_replaces_protheus_with_totvs(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.header_includes import HeaderIncludes

        content = '#Include "protheus.ch"\n\nUser Function X()\nReturn\n'
        ctx = MigrationContext(file_path=tmp_path / "a.prw", project_root=tmp_path)
        r = HeaderIncludes().apply(content, ctx)
        assert r.status == "ok"
        assert r.new_content is not None
        assert '#Include "totvs.ch"' in r.new_content
        assert "protheus.ch" not in r.new_content

    def test_adds_tlpp_core_when_class_present(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.header_includes import HeaderIncludes

        content = '#Include "protheus.ch"\n\nclass Foo\n  method new() class Foo\nendclass\n'
        ctx = MigrationContext(file_path=tmp_path / "a.prw", project_root=tmp_path)
        r = HeaderIncludes().apply(content, ctx)
        assert r.status == "ok"
        assert r.new_content is not None
        assert "tlpp-core.th" in r.new_content

    def test_nochange_when_already_totvs(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.header_includes import HeaderIncludes

        content = '#Include "totvs.ch"\n\nUser Function X()\nReturn\n'
        ctx = MigrationContext(file_path=tmp_path / "a.prw", project_root=tmp_path)
        r = HeaderIncludes().apply(content, ctx)
        assert r.status == "nochange"


class TestRemovePublic:
    """Recipe order 4 — PUBLIC X → X."""

    def test_removes_public_keyword(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.remove_public import RemovePublicDefault

        content = 'PUBLIC cVar := "x"\nPUBLIC nVal := 42\n'
        ctx = MigrationContext(file_path=tmp_path / "a.prw", project_root=tmp_path)
        r = RemovePublicDefault().apply(content, ctx)
        assert r.status == "ok"
        assert r.new_content is not None
        assert "PUBLIC" not in r.new_content
        assert 'cVar := "x"' in r.new_content

    def test_nochange_without_public(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.remove_public import RemovePublicDefault

        content = 'Local cVar := "x"\nReturn\n'
        ctx = MigrationContext(file_path=tmp_path / "a.prw", project_root=tmp_path)
        r = RemovePublicDefault().apply(content, ctx)
        assert r.status == "nochange"

    def test_recipe_id_and_category(self) -> None:
        from plugadvpl.migrate_tlpp_recipes.remove_public import RemovePublicDefault

        assert RemovePublicDefault.id == "remove-public-default"
        assert RemovePublicDefault.category == "safe"


class TestUserFunctionLowercase:
    """Recipe order 5 — User Function X() → function u_x() (caller-aware)."""

    def test_user_function_simple_no_db(self, tmp_path: Path) -> None:
        """Sem DB conn — modo conservador: aplica lowercase + emite todo."""
        from plugadvpl.migrate_tlpp_recipes.user_function import UserFunctionLowercase

        content = "User Function FATA050()\nReturn .T.\n"
        ctx = MigrationContext(file_path=tmp_path / "FATA050.prw", project_root=tmp_path)
        r = UserFunctionLowercase().apply(content, ctx)
        assert r.status == "needs-review"
        assert r.new_content is not None
        assert "function u_fata050(" in r.new_content
        assert len(r.todo_markers) == 1
        assert "DB não disponível" in r.todo_markers[0]

    def test_recipe_id(self) -> None:
        from plugadvpl.migrate_tlpp_recipes.user_function import UserFunctionLowercase

        assert UserFunctionLowercase.id == "user-function-lowercase"
        assert UserFunctionLowercase.category == "safe"

    def test_with_db_no_external_callers(self, tmp_path: Path) -> None:
        """DB conn presente, função sem callers externos → lowercase sem todo."""
        from plugadvpl.migrate_tlpp_recipes.user_function import UserFunctionLowercase

        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE chamadas (destino TEXT, origem_arquivo TEXT)")
        # nenhum caller pra FATA050
        db.commit()

        file_path = tmp_path / "FATA050.prw"
        content = "User Function FATA050()\nReturn .T.\n"
        ctx = MigrationContext(
            file_path=file_path, project_root=tmp_path, db_connection=db
        )
        r = UserFunctionLowercase().apply(content, ctx)
        assert r.status == "ok"
        assert r.new_content is not None
        assert "function u_fata050(" in r.new_content
        assert r.todo_markers == []

    def test_with_db_external_callers_preserves(self, tmp_path: Path) -> None:
        """DB conn presente, função com callers externos → preserva + todo."""
        from plugadvpl.migrate_tlpp_recipes.user_function import UserFunctionLowercase

        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE chamadas (destino TEXT, origem_arquivo TEXT)")
        file_path = tmp_path / "FATA050.prw"
        # 2 callers em outros arquivos
        db.execute(
            "INSERT INTO chamadas VALUES (?, ?)",
            ("FATA050", str(tmp_path / "outro.prw")),
        )
        db.execute(
            "INSERT INTO chamadas VALUES (?, ?)",
            ("FATA050", str(tmp_path / "outro2.prw")),
        )
        db.commit()

        content = "User Function FATA050()\nReturn .T.\n"
        ctx = MigrationContext(
            file_path=file_path, project_root=tmp_path, db_connection=db
        )
        r = UserFunctionLowercase().apply(content, ctx)
        assert r.status == "needs-review"
        assert r.new_content is not None
        assert "function u_fata050(" in r.new_content
        assert len(r.todo_markers) == 1
        assert "2 caller" in r.todo_markers[0]


class TestNamedArgs:
    """Recipe order 6 — := → = em named-args, gated tlpp_version≥20.3.2."""

    def test_skip_when_version_below_gate(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.named_args import NamedArgs

        content = "Foo(p1 := 1, p2 := 2)\n"
        ctx = MigrationContext(
            file_path=tmp_path / "a.prw",
            project_root=tmp_path,
            tlpp_version=(20, 3, 1),
        )
        r = NamedArgs().apply(content, ctx)
        assert r.status == "skipped"
        assert "20.3.2" in r.message

    def test_converts_assignment_in_call(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.named_args import NamedArgs

        content = "Foo(p1 := 1, p2 := 2)\n"
        ctx = MigrationContext(
            file_path=tmp_path / "a.prw",
            project_root=tmp_path,
            tlpp_version=(20, 3, 2),
        )
        r = NamedArgs().apply(content, ctx)
        assert r.status == "ok"
        assert r.new_content is not None
        assert "p1 = 1" in r.new_content
        assert "p2 = 2" in r.new_content
        assert ":=" not in r.new_content

    def test_nochange_when_no_assignment_in_call(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.named_args import NamedArgs

        # := em assignment normal (sem parens) — fica intacto
        content = "Local cVar := 'x'\n"
        ctx = MigrationContext(
            file_path=tmp_path / "a.prw",
            project_root=tmp_path,
            tlpp_version=(20, 3, 2),
        )
        r = NamedArgs().apply(content, ctx)
        assert r.status == "nochange"
