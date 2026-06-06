"""Testes da query poui_iface_lint — regra POUI-IFACE (#96 passo 2)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.query import poui_iface_lint


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)
    yield c
    c.close()


def _ins(conn: sqlite3.Connection, iface: str, prop: str, valor: str = "") -> None:
    conn.execute(
        "INSERT INTO poui_iface_uso (caminho, linha, interface_nome, propriedade, valor) "
        "VALUES ('src/x.ts', 1, ?, ?, ?)",
        (iface, prop, valor),
    )
    conn.commit()


class TestPouiIfaceLint:
    def test_chave_inexistente_gera_finding(self, conn: sqlite3.Connection) -> None:
        _ins(conn, "PoTableColumn", "field")  # correto é `property`
        rows = poui_iface_lint(conn)
        assert len(rows) == 1
        assert rows[0]["regra"] == "POUI-IFACE"
        assert rows[0]["binding"] == "field"
        assert rows[0]["kind"] == "interface"

    def test_chave_valida_nao_gera_finding(self, conn: sqlite3.Connection) -> None:
        _ins(conn, "PoTableColumn", "property")
        assert poui_iface_lint(conn) == []

    def test_interface_desconhecida_nao_gera_finding(self, conn: sqlite3.Connection) -> None:
        _ins(conn, "PoCustomInexistente", "qualquer")
        assert poui_iface_lint(conn) == []

    def test_valor_fora_do_enum_gera_finding(self, conn: sqlite3.Connection) -> None:
        _ins(conn, "PoTableColumn", "type", "money")  # válido seria 'currency'
        rows = poui_iface_lint(conn)
        assert len(rows) == 1
        assert rows[0]["kind"] == "valor"
        assert "money" in rows[0]["mensagem"]
        assert "currency" in rows[0]["mensagem"]

    def test_valor_no_enum_nao_gera_finding(self, conn: sqlite3.Connection) -> None:
        _ins(conn, "PoTableColumn", "type", "currency")
        assert poui_iface_lint(conn) == []

    def test_valor_em_prop_sem_enum_nao_gera_finding(self, conn: sqlite3.Connection) -> None:
        # `property` não tem enum → não valida valor
        _ins(conn, "PoTableColumn", "property", "qualquer_coisa")
        assert poui_iface_lint(conn) == []

    def test_schema_das_rows(self, conn: sqlite3.Connection) -> None:
        _ins(conn, "PoTableColumn", "field")
        r = poui_iface_lint(conn)[0]
        for col in ("arquivo", "linha", "componente", "binding", "kind", "regra", "mensagem"):
            assert col in r, f"coluna ausente: {col}"
