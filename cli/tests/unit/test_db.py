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
