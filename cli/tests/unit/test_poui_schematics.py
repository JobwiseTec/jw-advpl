"""Testes da query poui_schematics + consistência do catálogo (#99)."""

from __future__ import annotations

import json
import sqlite3
from importlib import resources as ir
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.query import poui_schematics


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)
    yield c
    c.close()


class TestPouiSchematicsQuery:
    def test_lista_todos(self, conn: sqlite3.Connection) -> None:
        rows = poui_schematics(conn)
        assert len(rows) >= 13
        assert all(r["comando"].startswith("ng generate @po-ui/") for r in rows)

    def test_tem_dynamic_table(self, conn: sqlite3.Connection) -> None:
        gens = {r["generator"] for r in poui_schematics(conn)}
        assert "po-page-dynamic-table" in gens
        assert "po-page-login" in gens
        assert "sidemenu" in gens

    def test_filtro_por_caso_uso(self, conn: sqlite3.Connection) -> None:
        rows = poui_schematics(conn, filtro="login")
        assert rows
        assert any("login" in r["generator"] for r in rows)

    def test_filtro_por_generator(self, conn: sqlite3.Connection) -> None:
        rows = poui_schematics(conn, filtro="dynamic")
        assert all("dynamic" in r["generator"] or "dynamic" in r["caso_uso"] for r in rows)
        assert len(rows) >= 3

    def test_pacote_correto(self, conn: sqlite3.Connection) -> None:
        by_gen = {r["generator"]: r["pacote"] for r in poui_schematics(conn)}
        assert by_gen["po-page-dynamic-table"] == "@po-ui/ng-templates"
        assert by_gen["po-page-default"] == "@po-ui/ng-components"

    def test_schema_das_rows(self, conn: sqlite3.Connection) -> None:
        r = poui_schematics(conn)[0]
        for col in ("generator", "pacote", "comando", "gera", "caso_uso"):
            assert col in r, f"coluna ausente: {col}"


class TestPouiSchematicsCatalog:
    def test_catalogo_consistente(self) -> None:
        data = json.loads(
            ir.files("plugadvpl").joinpath("lookups/poui_schematics.json").read_text("utf-8")
        )
        assert len(data) >= 13
        validos = {"@po-ui/ng-components", "@po-ui/ng-templates"}
        for e in data:
            assert e["pacote"] in validos
            assert e["chave"] == f"{e['pacote']}:{e['generator']}"
            assert e["comando"] == f"ng generate {e['pacote']}:{e['generator']}"
            assert e["gera"] and e["caso_uso"]  # descrição curada presente
