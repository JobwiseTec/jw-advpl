"""Testes do adapter REST → DB (U5 / Fase 3c).

Crucial: garante **paridade funcional** com `ingest_sx` (CSV path).
Mesmo dataset ingerido via REST deve produzir DB identico ao ingerido
via CSV.

Estrategia:
- Carrega fixtures CSV existentes (cli/tests/fixtures/sx_synthetic/)
- Constroi JSON response equivalente (mesmas linhas)
- Ingere via REST (com client mockado)
- Compara DB resultante com DB ingerido via CSV
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from plugadvpl.coletadb_client import ColetaDBClient, HealthResponse
from plugadvpl.db import open_db
from plugadvpl.ingest_rest import ingest_via_rest
from plugadvpl.ingest_sx import ingest_sx
from plugadvpl.parsing.sx_csv import _read_csv

SX_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sx_synthetic"


def _csv_to_rows(csv_path: Path) -> list[dict[str, str]]:
    """Le um CSV SX e retorna list[dict] com chaves do header (X3_*/X2_*/etc).

    Reusa ``_read_csv`` da sx_csv pra garantir paridade exata de encoding
    detection — sem isso, o mock leria com encoding diferente do CSV path
    e a comparacao de DB falharia por mojibake espurio.
    """
    if not csv_path.exists():
        return []
    return _read_csv(csv_path)


# Mapeamento CSV → "tabela protheus" no JSON. Espelha o que o
# COLETADB.tlpp emitiria.
_CSV_TO_PROTHEUS_TABLE = {
    "sx1.csv": "SX1",
    "sx2.csv": "SX2",
    "sx3.csv": "SX3",
    "sx5.csv": "SX5",
    "sx6.csv": "SX6",
    "sx7.csv": "SX7",
    "sx9.csv": "SX9",
    "sxa.csv": "SXA",
    "sxb.csv": "SXB",
    "sxg.csv": "SXG",
    "six.csv": "SIX",
}


def _build_mock_client(csv_dir: Path) -> ColetaDBClient:
    """Constroi um ColetaDBClient com mock que serve as fixtures CSV como JSON."""

    def mock_health() -> HealthResponse:
        return HealthResponse(
            version="1.0.0",
            protheus_build="test-build",
            protheus_environment="TST",
            exposed_tables=list(_CSV_TO_PROTHEUS_TABLE.values()),
            extras=[],
        )

    def mock_get_dump(tables: list[str], **kwargs: Any) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for protheus_table in tables:
            # Encontra o csv correspondente
            csv_name = next(
                (c for c, t in _CSV_TO_PROTHEUS_TABLE.items() if t == protheus_table),
                None,
            )
            if csv_name is None:
                continue
            csv_path = csv_dir / csv_name
            rows = _csv_to_rows(csv_path)
            result[protheus_table] = {
                "row_count": len(rows),
                "rows": rows,
            }
        return result

    client = mock.MagicMock(spec=ColetaDBClient)
    client.health = mock_health
    client.get_dump = mock_get_dump
    return client


class TestIngestViaRestBasic:
    def test_health_check_called_first(self, tmp_path: Path) -> None:
        """Antes do dump, ingest_via_rest chama health() pra validar conectividade."""
        client = _build_mock_client(SX_FIXTURES_DIR)
        client.health = mock.MagicMock(side_effect=client.health)

        db_path = tmp_path / "index.db"
        ingest_via_rest(client, db_path)

        client.health.assert_called_once()

    def test_ingest_returns_counters(self, tmp_path: Path) -> None:
        client = _build_mock_client(SX_FIXTURES_DIR)
        db_path = tmp_path / "index.db"

        counters = ingest_via_rest(client, db_path)

        assert counters["tables_total"] > 0
        assert counters["tables_ok"] > 0
        assert counters["total_rows"] > 0
        assert "per_table" in counters
        assert "duration_ms" in counters

    def test_filter_tables(self, tmp_path: Path) -> None:
        """Apenas tabelas listadas em --tables sao baixadas."""
        client = _build_mock_client(SX_FIXTURES_DIR)
        client.get_dump = mock.MagicMock(side_effect=client.get_dump)

        db_path = tmp_path / "index.db"
        ingest_via_rest(client, db_path, tables=["SX2", "SX3"])

        # get_dump foi chamado com tables=["SX2","SX3"] (em alguma ordem)
        called_with = client.get_dump.call_args
        called_tables = set(called_with[0][0]) if called_with[0] else set(called_with[1].get("tables", []))
        assert called_tables == {"SX2", "SX3"}


class TestParidadeFuncional:
    """Critical: REST e CSV devem produzir DBs identicos pro mesmo dataset.

    Esse e o critério de aceitação #2 da spec.
    """

    @pytest.fixture
    def db_via_csv(self, tmp_path: Path) -> sqlite3.Connection:
        """Ingere via CSV e retorna conexao com o DB resultante."""
        db = tmp_path / "via_csv.db"
        ingest_sx(SX_FIXTURES_DIR, db)
        return open_db(db)

    @pytest.fixture
    def db_via_rest(self, tmp_path: Path) -> sqlite3.Connection:
        """Ingere via REST (mock) e retorna conexao com o DB resultante."""
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
        """Sanity check: cada tabela SX tem o mesmo numero de rows em ambos os DBs."""
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
    def test_404_on_health_raises(self, tmp_path: Path) -> None:
        """Se health() falha, ingest aborta antes de tentar dump."""
        from plugadvpl.coletadb_client import ColetaDBError
        client = mock.MagicMock(spec=ColetaDBClient)
        client.health = mock.MagicMock(
            side_effect=ColetaDBError(
                "404", status=404, code="NOT_FOUND", hint="install COLETADB",
            )
        )

        db_path = tmp_path / "index.db"
        with pytest.raises(ColetaDBError):
            ingest_via_rest(client, db_path)

        # DB nem foi criado (abortou cedo)
        # (ou criado mas vazio — qualquer um e ok)
