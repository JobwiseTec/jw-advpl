"""Testes da query poui_lint — regra POUI-PROP (Fase 3b)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)
    yield c
    c.close()


class TestPouiLint:
    def test_binding_fora_catalogo_gera_finding(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.query import poui_lint

        # po-button está no catálogo (seed), p-fake não
        conn.execute(
            "INSERT INTO poui_componentes_uso (caminho, linha, componente, binding, kind) "
            "VALUES ('src/app.html', 1, 'po-button', 'p-fake', 'input')"
        )
        conn.commit()
        rows = poui_lint(conn)
        assert len(rows) == 1
        r = rows[0]
        assert r["regra"] == "POUI-PROP"
        assert r["binding"] == "p-fake"
        assert r["componente"] == "po-button"

    def test_binding_no_catalogo_nao_gera_finding(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.query import poui_lint

        # p-kind existe em po-button (seed tem isso)
        conn.execute(
            "INSERT INTO poui_componentes_uso (caminho, linha, componente, binding, kind) "
            "VALUES ('src/app.html', 1, 'po-button', 'p-kind', 'input')"
        )
        conn.commit()
        rows = poui_lint(conn)
        assert rows == []

    def test_componente_desconhecido_nao_gera_finding(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.query import poui_lint

        # po-custom não está no catálogo → componente custom → sem finding
        conn.execute(
            "INSERT INTO poui_componentes_uso (caminho, linha, componente, binding, kind) "
            "VALUES ('src/app.html', 1, 'po-custom', 'p-x', 'input')"
        )
        conn.commit()
        rows = poui_lint(conn)
        assert rows == []

    def test_schema_das_rows(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.query import poui_lint

        conn.execute(
            "INSERT INTO poui_componentes_uso (caminho, linha, componente, binding, kind) "
            "VALUES ('src/app.html', 5, 'po-button', 'p-nao-existe-xpto', 'input')"
        )
        conn.commit()
        rows = poui_lint(conn)
        assert rows
        r = rows[0]
        for col in ("arquivo", "linha", "componente", "binding", "kind", "regra", "mensagem"):
            assert col in r, f"coluna ausente: {col}"
