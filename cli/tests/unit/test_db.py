"""Testes de cli/plugadvpl/db.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.db import SCHEMA_VERSION, _is_network_share, open_db


class TestIsNetworkShare:
    def test_local_drive_windows(self) -> None:
        assert _is_network_share(Path("C:/Users/foo")) is False
        assert _is_network_share(Path("customizados-local")) is False

    def test_unc_path_windows(self) -> None:
        assert _is_network_share(Path(r"\\server\share\folder")) is True
        assert _is_network_share(Path("//server/share/folder")) is True

    def test_local_unix(self) -> None:
        assert _is_network_share(Path("/home/user/project")) is False
        assert _is_network_share(Path("/var/tmp")) is False


class TestOpenDb:
    def test_open_db_creates_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = open_db(db_path)
        assert db_path.exists()
        conn.close()

    def test_open_db_applies_pragmas(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = open_db(db_path)
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert conn.execute("PRAGMA temp_store").fetchone()[0] == 2   # MEMORY
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        finally:
            conn.close()

    def test_open_db_page_size_8192_on_new_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = open_db(db_path)
        try:
            assert conn.execute("PRAGMA page_size").fetchone()[0] == 8192
        finally:
            conn.close()

    def test_open_db_uses_delete_journal_on_network_share(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Forçar detecção como network share
        from plugadvpl import db as db_module
        monkeypatch.setattr(db_module, "_is_network_share", lambda _: True)

        db_path = tmp_path / "test.db"
        conn = open_db(db_path)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode in ("delete", "persist")
        finally:
            conn.close()


class TestApplyMigrations:
    def test_apply_migrations_creates_tables(self, tmp_path: Path) -> None:
        from plugadvpl.db import apply_migrations
        db_path = tmp_path / "test.db"
        conn = open_db(db_path)
        try:
            apply_migrations(conn)
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            expected_core = {
                "fontes", "fonte_chunks", "chamadas_funcao", "parametros_uso",
                "perguntas_uso", "operacoes_escrita", "sql_embedado", "funcao_docs",
                "rest_endpoints", "http_calls", "env_openers", "log_calls", "defines",
                "lint_findings", "fonte_tabela",
                "funcoes_nativas", "funcoes_restritas", "lint_rules", "sql_macros",
                "modulos_erp", "pontos_entrada_padrao",
                "meta", "ingest_progress",
            }
            missing = expected_core - tables
            assert not missing, f"Tabelas faltando: {missing}"
        finally:
            conn.close()

    def test_apply_migrations_creates_fts5(self, tmp_path: Path) -> None:
        from plugadvpl.db import apply_migrations
        db_path = tmp_path / "test.db"
        conn = open_db(db_path)
        try:
            apply_migrations(conn)
            # FTS5 aparece em sqlite_master como type='table' com sql que contém 'fts5'
            fts = list(conn.execute(
                "SELECT name FROM sqlite_master WHERE sql LIKE '%fts5%' AND type='table'"
            ))
            names = {r[0] for r in fts}
            assert "fonte_chunks_fts" in names
            assert "fonte_chunks_fts_tri" in names
        finally:
            conn.close()

    def test_apply_migrations_is_idempotent(self, tmp_path: Path) -> None:
        from plugadvpl.db import apply_migrations
        db_path = tmp_path / "test.db"
        conn = open_db(db_path)
        try:
            apply_migrations(conn)
            apply_migrations(conn)  # 2a vez nao pode dar erro
            count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            assert count > 20
        finally:
            conn.close()
