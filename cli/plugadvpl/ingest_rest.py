"""Pipeline REST → DB (U5 / Fase 3c — post-pivot).

Workflow real do COLETADB (bundle pattern):

1. POST /coletadb/run -> manifest com files[]
2. Pra cada file no manifest: loop POST /coletadb/file (chunks 4MB) ->
   reassembly local + verifica sha256
3. Chama ``ingest_sx`` no diretorio temp local -- REUSA toda machinery existente

Esse design e dramaticamente mais simples que a versao especulativa que tinha
adapter JSON->DB proprio. O servidor entrega CSV no mesmo formato do
Configurador, entao o ``ingest_sx`` consome direto sem normalize_* duplicado.
"""
from __future__ import annotations

import datetime as _dt
import shutil
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from plugadvpl import __version__ as _cli_version
from plugadvpl.db import (
    close_db,
    get_meta,
    init_meta,
    open_db,
    set_meta,
)
from plugadvpl.ingest_sx import ingest_sx as _ingest_sx_csv

if TYPE_CHECKING:
    from plugadvpl.coletadb_client import ColetaDBClient, Manifest


# Tabelas que o plugin ingere via REST. v0.12.0 (migration 013) estendeu
# pra cobrir XXA/XAM/XAL (SX extras LGPD/dominios) + RECORD_COUNTS
# (inventario fisico DBMS via UPDATE em tabelas.num_rows). MPMENU/SCHEDULES/
# JOBS ainda ficam pra Universos 6/8 (releases futuras).
_MVP_TABLES: frozenset[str] = frozenset({
    "SIX", "SX1", "SX2", "SX3", "SX5",
    "SX6", "SX7", "SX9", "SXA", "SXB", "SXG",
    # v0.12.0 — extras (migration 013)
    "XXA", "XAL", "XAM", "RECORD_COUNTS",
})


def _iso_now() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_mvp_table(name: str) -> bool:
    """``True`` se ``name`` (ex: 'SX3.csv', 'RECORD_COUNTS.csv') esta nos
    tipos cobertos pelo plugin (atualmente 11 SX padrao + 3 SX extras + 1
    inventario)."""
    if not name.lower().endswith(".csv"):
        return False
    stem = name[:-4].upper()  # 'SX3' ou 'RECORD_COUNTS'
    return stem in _MVP_TABLES


def ingest_via_rest(
    client: ColetaDBClient,
    db_path: Path,
    *,
    modo: str = "enxuto",
    threshold: int = 10,
    base_dir: str = "",
    ini_dir: str = "",
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    """Pipeline REST → DB.

    1. Chama ``/coletadb/run`` -> manifest
    2. Baixa cada arquivo SX do bundle em chunks pro tmp local
    3. Chama ``ingest_sx`` no tmp dir (reusa machinery existente)
    4. Cleanup do tmp

    Args:
        client: instancia ja configurada do :class:`ColetaDBClient`.
        db_path: caminho do SQLite (criado se nao existir).
        modo: ``"enxuto"`` (so tabelas com >= threshold rows) ou ``"completo"``.
        threshold: minimo de rows pra tabela contar como ativa.
        base_dir: pasta no SERVIDOR onde bundle e gerado (vazio = default do
            servidor, ex: ``\\temp\\``).
        ini_dir: pasta dos appserver*.ini no SERVIDOR (vazio = default).
        progress_callback: opcional, ``(filename, written, total)`` por chunk.

    Returns:
        Counters do ingest, incluindo bundle_id e modo.

    Raises:
        :class:`ColetaDBError` se /run/file falhar.
    """
    from plugadvpl.coletadb_client import Manifest as _Manifest  # noqa: F401

    start_time = time.time()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Fase 1: run -> manifest
    manifest: Manifest = client.run(
        modo=modo, threshold=threshold,
        base_dir=base_dir, ini_dir=ini_dir,
    )

    counters: dict[str, Any] = {
        "bundle_id": manifest.bundle_id,
        "bundle_dir": manifest.bundle_dir,
        "modo": manifest.modo,
        "threshold": manifest.threshold,
        "files_total": len(manifest.files),
        "files_downloaded": 0,
        "files_skipped": 0,
        "bytes_downloaded": 0,
        "duration_ms": 0,
        "ingest_counters": {},
    }

    # Fase 2: download dos arquivos SX em tmp local
    tmp_root = Path(tempfile.mkdtemp(prefix="plugadvpl-coletadb-"))
    try:
        for f in manifest.files:
            if not _is_mvp_table(f.name):
                counters["files_skipped"] += 1
                continue
            local_path = tmp_root / f.name.lower()  # ingest_sx procura case-insensitive
            written = client.download_file(
                f, local_path,
                progress_callback=(
                    (lambda w, t, _n=f.name: progress_callback(_n, w, t))
                    if progress_callback is not None else None
                ),
            )
            counters["files_downloaded"] += 1
            counters["bytes_downloaded"] += written

        # Fase 3: ingest_sx no tmp dir (reusa toda machinery)
        sx_counters = _ingest_sx_csv(tmp_root, db_path)
        counters["ingest_counters"] = sx_counters

        # Fase 4: meta especifica de REST
        conn = open_db(db_path)
        try:
            # Preserva project_root se ja existe (ingest_sx ja faz isso)
            existing_root = get_meta(conn, "project_root")
            if not existing_root:
                init_meta(
                    conn,
                    project_root=str(db_path.parent.parent),
                    cli_version=_cli_version,
                )
            set_meta(conn, "last_sx_source", "rest")
            set_meta(conn, "coletadb_bundle_id", manifest.bundle_id)
            set_meta(conn, "coletadb_bundle_dir", manifest.bundle_dir)
            set_meta(conn, "coletadb_modo", manifest.modo)
            set_meta(conn, "last_sx_ingest_at", _iso_now())
        finally:
            close_db(conn)

        counters["duration_ms"] = int((time.time() - start_time) * 1000)
        return counters
    finally:
        # Cleanup do tmp local
        try:
            shutil.rmtree(tmp_root, ignore_errors=True)
        except Exception:  # pragma: no cover - cleanup best-effort
            pass
