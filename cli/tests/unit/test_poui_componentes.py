"""Testes da query poui_componentes (migration 024 + seed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.query import poui_componentes as q_poui_componentes


@pytest.fixture(scope="module")
def conn(tmp_path_factory: pytest.TempPathFactory):
    """DB temporário com migrations + seed aplicados (módulo-scoped para performance)."""
    tmp = tmp_path_factory.mktemp("db")
    db_path = tmp / "test.db"
    c = open_db(db_path)
    apply_migrations(c)
    seed_lookups(c)
    yield c
    c.close()


class TestPouiComponentesQuery:
    def test_sem_filtro_retorna_todos(self, conn) -> None:
        rows = q_poui_componentes(conn)
        assert len(rows) > 900

    def test_filtra_po_table(self, conn) -> None:
        rows = q_poui_componentes(conn, componente="po-table")
        assert len(rows) > 0
        assert all(r["componente"] == "po-table" for r in rows)

    def test_filtro_case_insensitive(self, conn) -> None:
        lower = q_poui_componentes(conn, componente="po-table")
        upper = q_poui_componentes(conn, componente="PO-TABLE")
        assert len(lower) == len(upper)
        assert len(lower) > 0

    def test_po_table_tem_p_columns(self, conn) -> None:
        rows = q_poui_componentes(conn, componente="po-table")
        bindings = {r["binding"] for r in rows}
        assert "p-columns" in bindings

    def test_po_table_tem_inputs_e_outputs(self, conn) -> None:
        rows = q_poui_componentes(conn, componente="po-table")
        kinds = {r["kind"] for r in rows}
        assert "input" in kinds
        assert "output" in kinds

    def test_schema_das_rows(self, conn) -> None:
        rows = q_poui_componentes(conn, componente="po-table")
        assert rows, "po-table deve ter ao menos 1 binding"
        r = rows[0]
        for col in ("componente", "kind", "binding", "propriedade"):
            assert col in r, f"coluna ausente: {col}"

    def test_ordenacao(self, conn) -> None:
        rows = q_poui_componentes(conn, componente="po-table")
        # Deve estar ordenado por componente, kind, binding
        for i in range(len(rows) - 1):
            a, b = rows[i], rows[i + 1]
            key_a = (a["componente"], a["kind"], a["binding"])
            key_b = (b["componente"], b["kind"], b["binding"])
            assert key_a <= key_b, f"ordenação errada: {key_a} > {key_b}"

    def test_componente_inexistente_retorna_vazio(self, conn) -> None:
        rows = q_poui_componentes(conn, componente="po-inexistente-xyz")
        assert rows == []
