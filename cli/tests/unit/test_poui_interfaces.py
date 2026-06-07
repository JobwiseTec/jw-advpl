"""Testes da query poui_interfaces (migration 028 + seed, #96)."""

from __future__ import annotations

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.query import poui_interfaces as q_poui_interfaces


@pytest.fixture(scope="module")
def conn(tmp_path_factory: pytest.TempPathFactory):
    tmp = tmp_path_factory.mktemp("db")
    db_path = tmp / "test.db"
    c = open_db(db_path)
    apply_migrations(c)
    seed_lookups(c)
    yield c
    c.close()


class TestPouiInterfacesQuery:
    def test_sem_filtro_retorna_todas(self, conn) -> None:
        rows = q_poui_interfaces(conn)
        assert len(rows) > 1500

    def test_filtra_po_table_column(self, conn) -> None:
        rows = q_poui_interfaces(conn, interface="PoTableColumn")
        assert len(rows) == 18
        assert all(r["interface"] == "PoTableColumn" for r in rows)

    def test_filtro_case_insensitive(self, conn) -> None:
        lower = q_poui_interfaces(conn, interface="potablecolumn")
        exact = q_poui_interfaces(conn, interface="PoTableColumn")
        assert len(lower) == len(exact) == 18

    def test_type_traz_valores_enum(self, conn) -> None:
        rows = q_poui_interfaces(conn, interface="PoTableColumn")
        tipo = next(r for r in rows if r["propriedade"] == "type")
        assert "currency" in tipo["valores"]
        assert "money" not in tipo["valores"]  # erro clássico de IA
        assert len(tipo["valores"]) == 14

    def test_valores_e_lista(self, conn) -> None:
        rows = q_poui_interfaces(conn, interface="PoTableColumn")
        assert all(isinstance(r["valores"], list) for r in rows)

    def test_opcional_e_bool(self, conn) -> None:
        rows = q_poui_interfaces(conn, interface="PoTableColumn")
        assert all(isinstance(r["opcional"], bool) for r in rows)

    def test_extends_resolvido(self, conn) -> None:
        rows = {r["propriedade"]: r for r in q_poui_interfaces(conn, interface="PoPageAction")}
        assert rows["label"]["herdado_de"] == "PoDropdownAction"
        assert rows["kind"]["herdado_de"] == ""

    def test_schema_das_rows(self, conn) -> None:
        rows = q_poui_interfaces(conn, interface="PoTableColumn")
        for col in ("interface", "propriedade", "tipo", "opcional", "valores", "herdado_de"):
            assert col in rows[0], f"coluna ausente: {col}"

    def test_inexistente_vazio(self, conn) -> None:
        assert q_poui_interfaces(conn, interface="PoInexistenteXyz") == []

    def test_filtro_por_propriedade(self, conn) -> None:
        # #116: filtra por substring da propriedade (case-insensitive)
        rows = q_poui_interfaces(conn, interface="PoDynamicFormField", propriedade="maxlength")
        props = {r["propriedade"] for r in rows}
        assert "maxLength" in props
        assert all("maxlength" in r["propriedade"].lower() for r in rows)

    def test_filtro_propriedade_sem_interface(self, conn) -> None:
        # filtro de propriedade vale mesmo sem fixar a interface
        rows = q_poui_interfaces(conn, propriedade="maxLength")
        assert rows
        assert all("maxlength" in r["propriedade"].lower() for r in rows)
