"""Testes do adapter REST → DB (U5 / Fase 3c — post-pivot).

Workflow real do COLETADB:
1. /coletadb/run -> manifest
2. /coletadb/file -> chunks
3. ingest_sx no tmp dir local (reusa machinery)

Crucial: garante **paridade funcional** com `ingest_sx` (CSV path).
Mesmo dataset baixado via REST -> mesmo DB que ingest_sx faria local.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from plugadvpl.coletadb_client import (
    BundleFile,
    ColetaDBClient,
    Manifest,
)
from plugadvpl.db import open_db
from plugadvpl.ingest_rest import ingest_via_rest
from plugadvpl.ingest_sx import ingest_sx

SX_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sx_synthetic"


def _build_manifest_from_csv_dir(csv_dir: Path) -> tuple[Manifest, dict[str, bytes]]:
    """Simula o servidor COLETADB: le os CSVs do dir + monta manifest + bytes."""
    files: list[BundleFile] = []
    contents: dict[str, bytes] = {}  # name -> bytes
    for csv_file in sorted(csv_dir.glob("*.csv")):
        # COLETADB emite com nome upper (SX3.csv), nossas fixtures sao lower.
        name_upper = csv_file.name.upper()
        data = csv_file.read_bytes()
        contents[name_upper] = data
        sha = hashlib.sha256(data).hexdigest()
        files.append(
            BundleFile(
                name=name_upper,
                path=f"\\temp\\fake-bundle\\{name_upper}",
                size_bytes=len(data),
                chunks=max(1, (len(data) + 4194303) // 4194304),
                sha256=sha,
            )
        )
    manifest = Manifest(
        bundle_id="fake-bundle-uuid",
        bundle_dir="\\temp\\fake-bundle\\",
        modo="enxuto",
        threshold=10,
        chunk_size=4194304,
        files=files,
    )
    return manifest, contents


def _build_mock_client(csv_dir: Path) -> ColetaDBClient:
    """Cliente mockado que entrega CSVs do ``csv_dir`` via protocolo bundle."""
    manifest, contents = _build_manifest_from_csv_dir(csv_dir)

    def mock_run(**kwargs: Any) -> Manifest:
        return manifest

    def mock_download_file(
        bundle_file: BundleFile, dest_path: Any, *,
        progress_callback: Any = None,
    ) -> int:
        # "Servidor" entrega bytes do CSV correspondente
        data = contents.get(bundle_file.name, b"")
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if progress_callback is not None:
            progress_callback(len(data), len(data))
        return len(data)

    client = mock.MagicMock(spec=ColetaDBClient)
    client.run = mock_run
    client.download_file = mock_download_file
    return client


class TestIngestViaRestBasic:
    def test_run_called_first(self, tmp_path: Path) -> None:
        """Antes de baixar arquivos, ingest_via_rest chama run() pra obter manifest."""
        client = _build_mock_client(SX_FIXTURES_DIR)
        original_run = client.run
        client.run = mock.MagicMock(side_effect=original_run)

        db_path = tmp_path / "index.db"
        ingest_via_rest(client, db_path)

        client.run.assert_called_once()

    def test_ingest_returns_counters(self, tmp_path: Path) -> None:
        client = _build_mock_client(SX_FIXTURES_DIR)
        db_path = tmp_path / "index.db"

        counters = ingest_via_rest(client, db_path)

        assert counters["files_total"] > 0
        assert counters["files_downloaded"] > 0
        assert counters["bytes_downloaded"] > 0
        assert "duration_ms" in counters
        assert "bundle_id" in counters
        assert counters["bundle_id"] == "fake-bundle-uuid"

    def test_skips_non_mvp_files(self, tmp_path: Path) -> None:
        """v0.13.0: plugin cobre todos os 21 CSVs do COLETADB. Arquivo
        com nome desconhecido (futuro/custom) deve ser pulado."""
        # Manifest com mix: 4 conhecidos + 2 NAO-MVP (placeholders)
        manifest = Manifest(
            bundle_id="x", bundle_dir="\\temp\\x\\", modo="enxuto", threshold=10,
            chunk_size=4194304,
            files=[
                BundleFile(name="SX2.csv", path="p1", size_bytes=10, chunks=1, sha256=""),
                BundleFile(name="SX3.csv", path="p2", size_bytes=10, chunks=1, sha256=""),
                BundleFile(name="XXA.csv", path="p3", size_bytes=10, chunks=1, sha256=""),
                BundleFile(name="JOBS.csv", path="p4", size_bytes=10, chunks=1, sha256=""),
                # Arquivos hipoteticos (nao no _MVP_TABLES): plugin pula
                BundleFile(name="FUTURE_TABLE.csv", path="p5", size_bytes=10, chunks=1, sha256=""),
                BundleFile(name="CUSTOM_X.csv", path="p6", size_bytes=10, chunks=1, sha256=""),
            ],
        )

        downloaded = []

        def mock_download(bf, dest, **kw):  # noqa: ARG001
            downloaded.append(bf.name)
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_text("X2_CHAVE,X2_NOME,X2_MODO,D_E_L_E_T_\n", encoding="cp1252")
            return 50

        client = mock.MagicMock(spec=ColetaDBClient)
        client.run = lambda **kw: manifest
        client.download_file = mock_download

        ingest_via_rest(client, tmp_path / "index.db")

        # 4 MVP baixados, 2 nao-MVP pulados
        assert set(downloaded) == {"SX2.csv", "SX3.csv", "XXA.csv", "JOBS.csv"}


class TestParidadeFuncional:
    """REST e CSV devem produzir DBs equivalentes pro mesmo dataset.

    Post-pivot ficou trivial: o adapter REST simplesmente baixa os CSVs e
    chama o mesmo ``ingest_sx``. Se os CSVs sao os mesmos, o DB e o mesmo.
    """

    @pytest.fixture
    def db_via_csv(self, tmp_path: Path) -> sqlite3.Connection:
        db = tmp_path / "via_csv.db"
        ingest_sx(SX_FIXTURES_DIR, db)
        return open_db(db)

    @pytest.fixture
    def db_via_rest(self, tmp_path: Path) -> sqlite3.Connection:
        db = tmp_path / "via_rest.db"
        client = _build_mock_client(SX_FIXTURES_DIR)
        ingest_via_rest(client, db)
        return open_db(db)

    def test_tabelas_table_identical(
        self,
        db_via_csv: sqlite3.Connection,
        db_via_rest: sqlite3.Connection,
    ) -> None:
        rows_csv = db_via_csv.execute(
            "SELECT codigo, nome, modo, custom FROM tabelas ORDER BY codigo"
        ).fetchall()
        rows_rest = db_via_rest.execute(
            "SELECT codigo, nome, modo, custom FROM tabelas ORDER BY codigo"
        ).fetchall()
        assert rows_csv == rows_rest

    def test_campos_table_identical(
        self,
        db_via_csv: sqlite3.Connection,
        db_via_rest: sqlite3.Connection,
    ) -> None:
        rows_csv = db_via_csv.execute(
            "SELECT tabela, campo, tipo, tamanho, decimal, titulo, descricao, "
            "validacao, inicializador, obrigatorio, custom "
            "FROM campos ORDER BY tabela, campo"
        ).fetchall()
        rows_rest = db_via_rest.execute(
            "SELECT tabela, campo, tipo, tamanho, decimal, titulo, descricao, "
            "validacao, inicializador, obrigatorio, custom "
            "FROM campos ORDER BY tabela, campo"
        ).fetchall()
        assert rows_csv == rows_rest

    def test_gatilhos_identical(
        self,
        db_via_csv: sqlite3.Connection,
        db_via_rest: sqlite3.Connection,
    ) -> None:
        rows_csv = db_via_csv.execute(
            "SELECT campo_origem, sequencia, campo_destino, regra "
            "FROM gatilhos ORDER BY campo_origem, sequencia"
        ).fetchall()
        rows_rest = db_via_rest.execute(
            "SELECT campo_origem, sequencia, campo_destino, regra "
            "FROM gatilhos ORDER BY campo_origem, sequencia"
        ).fetchall()
        assert rows_csv == rows_rest

    def test_all_tables_have_same_row_count(
        self,
        db_via_csv: sqlite3.Connection,
        db_via_rest: sqlite3.Connection,
    ) -> None:
        sx_tables = [
            "tabelas", "campos", "gatilhos", "parametros", "perguntas",
            "tabelas_genericas", "relacionamentos", "pastas",
            "consultas", "grupos_campo", "indices",
        ]
        for table in sx_tables:
            n_csv = db_via_csv.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            n_rest = db_via_rest.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert n_csv == n_rest, (
                f"Paridade falhou em '{table}': CSV={n_csv}, REST={n_rest}"
            )


class TestErrors:
    def test_404_on_run_propagates(self, tmp_path: Path) -> None:
        """Se /run falha, ingest aborta limpo (CSVs nao foram baixados)."""
        from plugadvpl.coletadb_client import ColetaDBError
        client = mock.MagicMock(spec=ColetaDBClient)
        client.run = mock.MagicMock(
            side_effect=ColetaDBError(
                "404", status=404, code="NOT_FOUND",
                hint="compilar COLETADB.tlpp",
            )
        )

        with pytest.raises(ColetaDBError):
            ingest_via_rest(client, tmp_path / "index.db")


class TestMetaTracking:
    def test_meta_tracks_rest_source_and_bundle_id(self, tmp_path: Path) -> None:
        """Meta deve registrar que o ultimo ingest foi via REST + bundle_id."""
        client = _build_mock_client(SX_FIXTURES_DIR)
        db_path = tmp_path / "index.db"
        ingest_via_rest(client, db_path)

        conn = open_db(db_path)
        try:
            source = conn.execute(
                "SELECT valor FROM meta WHERE chave='last_sx_source'"
            ).fetchone()
            bundle_id = conn.execute(
                "SELECT valor FROM meta WHERE chave='coletadb_bundle_id'"
            ).fetchone()
            assert source is not None and source[0] == "rest"
            assert bundle_id is not None and bundle_id[0] == "fake-bundle-uuid"
        finally:
            from plugadvpl.db import close_db
            close_db(conn)
