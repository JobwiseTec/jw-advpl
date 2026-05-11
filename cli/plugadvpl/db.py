"""Banco de dados SQLite — abertura, PRAGMAs, migrations, network share detection."""
from __future__ import annotations

import importlib.resources as ir
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Aplica todas as migrations da pasta ``migrations/`` em ordem alfabética.

    Migrations são arquivos ``.sql`` numerados (``001_initial.sql``,
    ``002_xxx.sql``, ...). Cada arquivo deve ser idempotente (usa
    ``CREATE TABLE IF NOT EXISTS`` etc.) para permitir reaplicação segura.

    Carrega via :mod:`importlib.resources` para funcionar igual em
    desenvolvimento (source tree) e em wheel instalado.
    """
    migrations_dir = ir.files("plugadvpl") / "migrations"
    sql_files = sorted(
        (f for f in migrations_dir.iterdir() if f.name.endswith(".sql")),
        key=lambda f: f.name,
    )
    for sql_file in sql_files:
        sql = sql_file.read_text(encoding="utf-8")
        conn.executescript(sql)
    conn.commit()


def init_meta(
    conn: sqlite3.Connection, *, project_root: str, cli_version: str
) -> None:
    """Grava as linhas obrigatórias em ``meta`` (idempotente via UPSERT).

    Linhas escritas:

    - ``schema_version``: :data:`SCHEMA_VERSION` (incrementa quando migrations rodam).
    - ``plugadvpl_version``: ``cli_version`` informado pelo chamador.
    - ``project_root``: caminho absoluto da raiz do projeto cliente.
    - ``encoding_policy``: ``'preserve'`` (default, cf. spec §4.2).
    """
    defaults: dict[str, str] = {
        "schema_version": SCHEMA_VERSION,
        "plugadvpl_version": cli_version,
        "project_root": project_root,
        "encoding_policy": "preserve",
    }
    for k, v in defaults.items():
        set_meta(conn, k, v)


def get_meta(conn: sqlite3.Connection, chave: str) -> str | None:
    """Retorna ``meta.valor`` para ``chave``, ou ``None`` se ausente."""
    row = conn.execute(
        "SELECT valor FROM meta WHERE chave=?", (chave,)
    ).fetchone()
    if row is None:
        return None
    valor: str = row[0]
    return valor


def set_meta(conn: sqlite3.Connection, chave: str, valor: str) -> None:
    """Insere ou atualiza ``meta[chave] = valor`` (UPSERT atômico + commit)."""
    conn.execute(
        "INSERT INTO meta (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
        (chave, valor),
    )
    conn.commit()


def close_db(conn: sqlite3.Connection) -> None:
    """Fecha conexão SQLite executando otimizações finais.

    Sequência (cf. spec §4.1, recomendação oficial SQLite >=3.46):

    1. ``PRAGMA optimize`` — coleta estatísticas e atualiza índices
       (https://sqlite.org/pragma.html#pragma_optimize).
    2. Se ``journal_mode == 'wal'``: ``PRAGMA wal_checkpoint(TRUNCATE)``
       — força sync e zera ``.db-wal`` para liberar disco.
    3. ``commit`` para garantir persistência.
    4. ``close`` em bloco ``finally`` mesmo se houver erro nas otimizações
       (evita vazar conexão).
    """
    try:
        conn.execute("PRAGMA optimize")
        mode_row = conn.execute("PRAGMA journal_mode").fetchone()
        if mode_row is not None and mode_row[0] == "wal":
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()
