"""Testes da query poui_version_lint — regra POUI-VERSION (#98)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.query import poui_catalog_meta, poui_version_lint


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)
    yield c
    c.close()


def _projeto(conn: sqlite3.Connection, caminho: str, poui_major: int) -> None:
    conn.execute(
        "INSERT INTO poui_projetos (caminho, poui_version, poui_major, angular_version, "
        "angular_major, compativel, pacotes_json, hash, mtime_ns) "
        "VALUES (?, ?, ?, '0', 0, 1, '[]', 'h', 0)",
        (caminho, f"{poui_major}.0.0", poui_major),
    )
    conn.commit()


class TestPouiCatalogMeta:
    def test_meta_tem_major(self, conn: sqlite3.Connection) -> None:
        meta = poui_catalog_meta(conn)
        assert meta.get("poui_major")  # seedado do lookup
        assert meta["poui_major"].isdigit()


class TestPouiVersionLint:
    def test_major_diferente_gera_warning(self, conn: sqlite3.Connection) -> None:
        cat_major = int(poui_catalog_meta(conn)["poui_major"])
        _projeto(conn, "/proj/package.json", cat_major - 6)  # major bem diferente
        rows = poui_version_lint(conn)
        assert len(rows) == 1
        assert rows[0]["regra"] == "POUI-VERSION"
        assert rows[0]["kind"] == "warning"
        assert f"v{cat_major - 6}" in rows[0]["mensagem"]

    def test_major_igual_nao_gera_warning(self, conn: sqlite3.Connection) -> None:
        cat_major = int(poui_catalog_meta(conn)["poui_major"])
        _projeto(conn, "/proj/package.json", cat_major)
        assert poui_version_lint(conn) == []

    def test_sem_projeto_vazio(self, conn: sqlite3.Connection) -> None:
        assert poui_version_lint(conn) == []

    def test_um_warning_por_projeto(self, conn: sqlite3.Connection) -> None:
        cat_major = int(poui_catalog_meta(conn)["poui_major"])
        _projeto(conn, "/projA/package.json", cat_major - 1)
        _projeto(conn, "/projB/package.json", cat_major - 2)
        _projeto(conn, "/projC/package.json", cat_major)  # igual: sem warning
        rows = poui_version_lint(conn)
        assert len(rows) == 2

    def test_schema_das_rows(self, conn: sqlite3.Connection) -> None:
        cat_major = int(poui_catalog_meta(conn)["poui_major"])
        _projeto(conn, "/proj/package.json", cat_major - 1)
        r = poui_version_lint(conn)[0]
        for col in ("arquivo", "linha", "componente", "binding", "kind", "regra", "mensagem"):
            assert col in r, f"coluna ausente: {col}"
