"""Testes do parser extract_poui_imports e da query poui_import_lint (#97)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.parsing.poui import extract_poui_imports
from plugadvpl.query import poui_import_lint


class TestExtractPouiImports:
    def test_pega_pacotes(self) -> None:
        src = (
            "import { PoModule } from '@po-ui/ng-components';\n"
            "import { PoTemplatesModule } from '@po-ui/ng-templates';\n"
        )
        pacotes = {i["pacote"] for i in extract_poui_imports(src)}
        assert pacotes == {"@po-ui/ng-components", "@po-ui/ng-templates"}

    def test_dedup(self) -> None:
        src = (
            "import { A } from '@po-ui/ng-components';\n"
            "import { B } from '@po-ui/ng-components';\n"
        )
        assert len(extract_poui_imports(src)) == 1

    def test_ignora_outros_imports(self) -> None:
        src = "import { Component } from '@angular/core';"
        assert extract_poui_imports(src) == []

    def test_linha(self) -> None:
        src = "x\n\nimport { A } from '@po-ui/ng-templates';"
        assert extract_poui_imports(src)[0]["linha"] == 3


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)
    yield c
    c.close()


def _projeto(conn: sqlite3.Connection, pkg_path: str) -> None:
    conn.execute(
        "INSERT INTO poui_projetos (caminho, poui_version, poui_major, angular_version, "
        "angular_major, compativel, pacotes_json, hash, mtime_ns) "
        "VALUES (?, '21.0.0', 21, '21.0.0', 21, 1, '[]', 'h', 0)",
        (pkg_path,),
    )


def _uso(conn: sqlite3.Connection, html: str, comp: str) -> None:
    conn.execute(
        "INSERT INTO poui_componentes_uso (caminho, linha, componente, binding, kind) "
        "VALUES (?, 1, ?, 'p-x', 'input')",
        (html, comp),
    )


def _import(conn: sqlite3.Connection, ts: str, pacote: str) -> None:
    conn.execute(
        "INSERT INTO poui_imports (caminho, linha, pacote) VALUES (?, 1, ?)", (ts, pacote)
    )


class TestPouiImportLint:
    def test_pacote_faltando_gera_finding(self, conn: sqlite3.Connection) -> None:
        _projeto(conn, "/proj/package.json")
        _uso(conn, "/proj/src/a.html", "po-page-dynamic-table")  # ng-templates
        _import(conn, "/proj/src/a.module.ts", "@po-ui/ng-components")  # falta ng-templates
        conn.commit()
        rows = poui_import_lint(conn)
        assert len(rows) == 1
        assert rows[0]["regra"] == "POUI-IMPORT"
        assert rows[0]["componente"] == "po-page-dynamic-table"
        assert "@po-ui/ng-templates" in rows[0]["mensagem"]

    def test_pacote_importado_nao_gera_finding(self, conn: sqlite3.Connection) -> None:
        _projeto(conn, "/proj/package.json")
        _uso(conn, "/proj/src/a.html", "po-page-dynamic-table")
        _import(conn, "/proj/src/a.module.ts", "@po-ui/ng-templates")
        conn.commit()
        assert poui_import_lint(conn) == []

    def test_componente_custom_nao_gera_finding(self, conn: sqlite3.Connection) -> None:
        _projeto(conn, "/proj/package.json")
        _uso(conn, "/proj/src/a.html", "po-custom-inexistente")
        conn.commit()
        assert poui_import_lint(conn) == []

    def test_um_finding_por_projeto_componente(self, conn: sqlite3.Connection) -> None:
        _projeto(conn, "/proj/package.json")
        _uso(conn, "/proj/src/a.html", "po-page-dynamic-table")
        _uso(conn, "/proj/src/b.html", "po-page-dynamic-table")  # mesmo comp, 2 usos
        conn.commit()
        assert len(poui_import_lint(conn)) == 1

    def test_escopo_por_projeto(self, conn: sqlite3.Connection) -> None:
        # proj A importa ng-templates; proj B não. Só B deve gerar finding.
        _projeto(conn, "/projA/package.json")
        _projeto(conn, "/projB/package.json")
        _uso(conn, "/projA/src/a.html", "po-page-dynamic-table")
        _import(conn, "/projA/src/a.module.ts", "@po-ui/ng-templates")
        _uso(conn, "/projB/src/b.html", "po-page-dynamic-table")
        conn.commit()
        rows = poui_import_lint(conn)
        assert len(rows) == 1
        assert rows[0]["arquivo"].startswith("/projB")
