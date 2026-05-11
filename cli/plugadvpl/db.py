"""Banco de dados SQLite — abertura, PRAGMAs, migrations, network share detection."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1"


def _is_network_share(path: Path) -> bool:
    """Detecta se um path está em network share (SMB/CIFS/UNC).

    WAL não funciona em network filesystem (docs SQLite oficiais —
    https://sqlite.org/wal.html). Quando True, ``open_db`` usa
    ``journal_mode=DELETE`` em vez de WAL.

    Detecta:

    - UNC paths Windows: ``\\\\server\\share`` (backslash-backslash prefix).
    - POSIX-style UNC: ``//server/share`` (forward-slash prefix).
    - Mapped drives em Windows (Z: apontando para share) NÃO são detectados
      aqui por simplicidade — usuário recebe warning explícito se WAL falhar
      durante uso (SQLite retorna erro nesse caso).
    """
    s = str(path)
    return s.startswith("\\\\") or s.startswith("//")


def open_db(db_path: Path) -> sqlite3.Connection:
    """Abre/cria DB em ``db_path`` aplicando PRAGMAs corretos.

    Comportamento:

    - Em DB novo: aplica ``page_size=8192`` (só vale antes de qualquer
      CREATE TABLE — persiste no header).
    - Detecta network share via :func:`_is_network_share` no diretório-pai
      do DB. Se positivo, usa ``journal_mode=DELETE`` (rollback journal,
      compatível com SMB/CIFS). Caso contrário, usa
      ``journal_mode=WAL`` + ``journal_size_limit=64MiB``.
    - Sempre aplica: ``synchronous=NORMAL``, ``foreign_keys=ON``,
      ``temp_store=MEMORY``, ``mmap_size=256MiB``, ``cache_size=-20000``
      (~20MB), ``busy_timeout=5000`` (5s).

    Spec §4.1.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not db_path.exists()
    conn = sqlite3.connect(str(db_path))

    if is_new:
        conn.execute("PRAGMA page_size = 8192")

    if _is_network_share(db_path.parent):
        conn.execute("PRAGMA journal_mode = DELETE")
    else:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA journal_size_limit = 67108864")

    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA mmap_size = 268435456")
    conn.execute("PRAGMA cache_size = -20000")
    conn.execute("PRAGMA busy_timeout = 5000")

    return conn
