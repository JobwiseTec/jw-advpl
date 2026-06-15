"""Sub-projeto 2 (spec SX completo) — lints de integridade & chave.

SX-012 (RELORFA): SX9 aponta pra tabela custom inexistente.
SX-013 (DUPKEY): grava em tabela com chave única (X2_UNICO) sem seek no escopo.
Ver docs/superpowers/specs/2026-06-15-sx-completo-chave-indice-design.md.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.parsing.lint import lint_cross_file


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)
    return c


def _ids(findings: list[dict], rid: str) -> list[dict]:
    return [f for f in findings if f["regra_id"] == rid]


class TestSx012RelacionamentoOrfao:
    def test_custom_destino_inexistente_e_finding(self, conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO tabelas (codigo, custom) VALUES ('ZX1', 1)")
        conn.execute(
            "INSERT INTO relacionamentos (tabela_origem, identificador, tabela_destino) "
            "VALUES ('ZX1', '001', 'ZX2')"  # ZX2 é custom (Z*) e NÃO está em tabelas
        )
        conn.commit()
        f = _ids(lint_cross_file(conn, rules=["SX-012"]), "SX-012")
        assert any("ZX2" in r["snippet"] for r in f)

    def test_destino_padrao_totvs_nao_e_flagado(self, conn: sqlite3.Connection) -> None:
        # SA1 é padrão TOTVS (não indexado por design) -> NÃO é órfão.
        conn.execute("INSERT INTO tabelas (codigo, custom) VALUES ('ZX1', 1)")
        conn.execute(
            "INSERT INTO relacionamentos (tabela_origem, identificador, tabela_destino) "
            "VALUES ('ZX1', '001', 'SA1')"
        )
        conn.commit()
        assert _ids(lint_cross_file(conn, rules=["SX-012"]), "SX-012") == []

    def test_destino_custom_existente_ok(self, conn: sqlite3.Connection) -> None:
        conn.executemany(
            "INSERT INTO tabelas (codigo, custom) VALUES (?, 1)", [("ZX1",), ("ZX2",)]
        )
        conn.execute(
            "INSERT INTO relacionamentos (tabela_origem, identificador, tabela_destino) "
            "VALUES ('ZX1', '001', 'ZX2')"
        )
        conn.commit()
        assert _ids(lint_cross_file(conn, rules=["SX-012"]), "SX-012") == []


class TestSx013DupKey:
    """SX-013 (info, conservador): RecLock add a tabela com chave única sem seek/numerador."""

    def _setup(self, conn: sqlite3.Connection, funcao: str, content: str) -> None:
        conn.execute("INSERT OR IGNORE INTO fontes (arquivo, caminho_relativo) VALUES ('a.prw','a.prw')")
        conn.execute(
            "INSERT OR IGNORE INTO tabelas (codigo, custom, unico) VALUES ('ZX1', 1, 'ZX1_FILIAL+ZX1_NUM')"
        )
        conn.execute(
            "INSERT INTO fonte_chunks (id, arquivo, funcao, funcao_norm, tipo_simbolo, content) "
            "VALUES (?, 'a.prw', ?, ?, 'user_function', ?)",
            (f"a.prw::{funcao}", funcao, funcao.upper(), content),
        )
        conn.commit()

    def test_reclock_add_sem_seek_e_finding(self, conn: sqlite3.Connection) -> None:
        self._setup(conn, "GRAVABAD", "RecLock('ZX1', .T.)\nReplace ZX1_NUM With '1'\nMsUnlock()")
        f = _ids(lint_cross_file(conn, rules=["SX-013"]), "SX-013")
        assert any("ZX1" in r["snippet"] for r in f)

    def test_com_seek_nao_flagga(self, conn: sqlite3.Connection) -> None:
        self._setup(conn, "GRAVAOK", "DbSeek(xFilial('ZX1')+cNum)\nRecLock('ZX1', .T.)\nMsUnlock()")
        assert _ids(lint_cross_file(conn, rules=["SX-013"]), "SX-013") == []

    def test_com_getsx8num_nao_flagga(self, conn: sqlite3.Connection) -> None:
        self._setup(conn, "GRAVANUM", "cN := GetSx8Num('ZX1')\nRecLock('ZX1', .T.)\nMsUnlock()")
        assert _ids(lint_cross_file(conn, rules=["SX-013"]), "SX-013") == []

    def test_tabela_sem_unico_nao_flagga(self, conn: sqlite3.Connection) -> None:
        # ZX9 sem unico definido -> fora do escopo do SX-013.
        conn.execute("INSERT OR IGNORE INTO fontes (arquivo, caminho_relativo) VALUES ('a.prw','a.prw')")
        conn.execute("INSERT INTO tabelas (codigo, custom) VALUES ('ZX9', 1)")
        conn.execute(
            "INSERT INTO fonte_chunks (id, arquivo, funcao, funcao_norm, tipo_simbolo, content) "
            "VALUES ('a.prw::G2', 'a.prw', 'G2', 'G2', 'user_function', \"RecLock('ZX9', .T.)\")"
        )
        conn.commit()
        assert _ids(lint_cross_file(conn, rules=["SX-013"]), "SX-013") == []
