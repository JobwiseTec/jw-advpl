"""Fase 1 do roadmap-ia — verify-claims (verificador determinístico / sound verifier).

Ver docs/roadmap-ia/01-verify-claims.md.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """Índice-fixture com símbolos controlados em cada corpus."""
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)  # carrega funcoes_nativas/restritas reais (não usadas nas asserções)

    # fonte-pai (FK de fonte_chunks.arquivo -> fontes.arquivo, com foreign_keys=ON)
    c.execute("INSERT INTO fontes (arquivo, caminho_relativo) VALUES ('a.prw', 'a.prw')")
    # função definida no fonte (customer)
    c.execute(
        "INSERT INTO fonte_chunks (id, arquivo, funcao, funcao_norm, tipo_simbolo) "
        "VALUES ('a.prw::ZMYFUNC', 'a.prw', 'ZMYFUNC', 'ZMYFUNC', 'user_function')"
    )
    # nativa + restrita controladas (nomes inventados p/ não colidir com o bundle real)
    c.execute("INSERT INTO funcoes_nativas (nome, categoria) VALUES ('ZNativeTest', 'test')")
    c.execute("INSERT INTO funcoes_restritas (nome, categoria) VALUES ('ZRestrTest', 'test')")
    # SX2/SX3/SX6 (customizações do cliente)
    c.execute("INSERT INTO tabelas (codigo, custom) VALUES ('ZX1', 1)")
    c.execute(
        "INSERT INTO campos (tabela, campo, custom, proprietario) VALUES ('ZX1', 'ZX1_STATUS', 1, 'U')"
    )
    c.execute("INSERT INTO parametros (variavel) VALUES ('MV_ZTEST')")
    # aresta de chamada (ZMYFUNC -> FWLoadModel) e gatilho SX7 em ZX1_CLIENTE
    c.execute(
        "INSERT INTO chamadas_funcao (arquivo_origem, funcao_origem, tipo, destino, destino_norm) "
        "VALUES ('a.prw', 'ZMYFUNC', 'call', 'FWLoadModel', 'FWLOADMODEL')"
    )
    c.execute("INSERT INTO gatilhos (campo_origem, sequencia, custom) VALUES ('ZX1_CLIENTE', '001', 1)")
    c.commit()
    return c


def _by_id(verdict: dict[str, Any]) -> dict[str, Any]:
    return {r["claim_id"]: r for r in verdict["results"]}


class TestEnvelope:
    def test_empty_claims_returns_envelope(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        out = verify_claims(conn, [])
        assert out["results"] == []
        assert "coverage" in out
        assert "index_version" in out


class TestFunctionExistence:
    def test_function_defined_in_source_exists(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "ZMYFUNC"}]))
        assert r["c1"]["status"] == "exists"
        assert r["c1"]["namespace_scope"] == "customer"

    def test_user_function_prefix_is_normalized(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        # U_ZMYFUNC é a forma de CHAMADA; a definição é ZMYFUNC (prefixo U_ removido).
        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "U_ZMYFUNC"}]))
        assert r["c1"]["status"] == "exists"

    def test_match_is_case_insensitive(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "zmyfunc"}]))
        assert r["c1"]["status"] == "exists"

    def test_native_function_exists_with_scope(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "ZNativeTest"}]))
        assert r["c1"]["status"] == "exists"
        assert r["c1"]["namespace_scope"] == "native"

    def test_restricted_function_exists_with_scope(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "ZRestrTest"}]))
        assert r["c1"]["status"] == "exists"
        assert r["c1"]["namespace_scope"] == "restricted"

    def test_unknown_function_is_not_found(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        # FWLerExcel é uma alucinação clássica (não existe no Protheus).
        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "FWLerExcel"}]))
        assert r["c1"]["status"] == "not_found"

    def test_claim_id_is_echoed(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        out = verify_claims(conn, [{"id": "xyz", "kind": "function", "symbol": "ZMYFUNC"}])
        assert out["results"][0]["claim_id"] == "xyz"


class TestTableExistence:
    def test_known_table_exists(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "table", "symbol": "ZX1"}]))
        assert r["c1"]["status"] == "exists"

    def test_table_match_is_case_insensitive(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "table", "symbol": "zx1"}]))
        assert r["c1"]["status"] == "exists"

    def test_unknown_table_not_found(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "table", "symbol": "Z9Z"}]))
        assert r["c1"]["status"] == "not_found"


class TestFieldExistence:
    def test_known_field_exists(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "field", "symbol": "ZX1_STATUS"}]))
        assert r["c1"]["status"] == "exists"

    def test_unknown_field_not_found(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "field", "symbol": "ZX1_NOPE"}]))
        assert r["c1"]["status"] == "not_found"


class TestParamExistence:
    def test_known_param_exists(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "param", "symbol": "MV_ZTEST"}]))
        assert r["c1"]["status"] == "exists"

    def test_unknown_param_not_found(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "param", "symbol": "MV_NOPE"}]))
        assert r["c1"]["status"] == "not_found"


class TestCallEdgeRelation:
    def test_existing_edge_relation_holds(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [
            {"id": "c1", "kind": "call_edge", "caller": "ZMYFUNC", "callee": "FWLoadModel"}
        ]))
        assert r["c1"]["status"] == "relation_holds"

    def test_caller_callee_normalized(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        # caller minúsculo + callee com prefixo U_ de chamada normalizam.
        r = _by_id(verify_claims(conn, [
            {"id": "c1", "kind": "call_edge", "caller": "zmyfunc", "callee": "U_FWLoadModel"}
        ]))
        assert r["c1"]["status"] == "relation_holds"

    def test_absent_edge_is_relation_absent_low_conf(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [
            {"id": "c1", "kind": "call_edge", "caller": "ZMYFUNC", "callee": "NadaAqui"}
        ]))
        assert r["c1"]["status"] == "relation_absent"
        assert r["c1"]["confidence"] == "low"


class TestTriggerRelation:
    def test_existing_trigger_relation_holds(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "trigger", "field": "ZX1_CLIENTE"}]))
        assert r["c1"]["status"] == "relation_holds"

    def test_absent_trigger_is_relation_absent_low_conf(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "trigger", "field": "ZX1_STATUS"}]))
        assert r["c1"]["status"] == "relation_absent"
        assert r["c1"]["confidence"] == "low"


class TestUnsupportedKind:
    def test_unknown_kind_is_unsupported(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "banana", "symbol": "x"}]))
        assert r["c1"]["status"] == "unsupported_kind"


class TestFunctionMissConfidence:
    """Calibração de confiança em not_found de função (Fase 1 refinada)."""

    def test_framework_prefix_miss_is_high(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        # FWLerExcel: prefixo FW (alega ser framework) + ausente -> alucinação provável.
        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "FWLerExcel"}]))
        assert r["c1"]["status"] == "not_found"
        assert r["c1"]["confidence"] == "high"

    def test_ms_prefix_miss_is_high(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "MsRetXls"}]))
        assert r["c1"]["confidence"] == "high"

    def test_user_function_miss_is_low(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        # U_ -> provável customer não-indexado -> baixa confiança (não bloquear).
        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "U_NaoIndexada"}]))
        assert r["c1"]["status"] == "not_found"
        assert r["c1"]["confidence"] == "low"

    def test_plain_name_miss_is_medium(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        # Sem prefixo de framework nem U_ -> inconclusivo (medium).
        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "GeraDocx"}]))
        assert r["c1"]["confidence"] == "medium"


class TestExtractClaims:
    """Fase 3: extração do bloco <plugadvpl-claims> de uma resposta."""

    def test_extracts_claims_from_block(self) -> None:
        from plugadvpl.verify import extract_claims

        text = (
            'bla <plugadvpl-claims>{"claims":[{"id":"c1","kind":"function",'
            '"symbol":"X"}]}</plugadvpl-claims> fim'
        )
        assert extract_claims(text) == [{"id": "c1", "kind": "function", "symbol": "X"}]

    def test_no_block_returns_empty(self) -> None:
        from plugadvpl.verify import extract_claims

        assert extract_claims("sem bloco aqui") == []

    def test_malformed_block_returns_empty(self) -> None:
        from plugadvpl.verify import extract_claims

        assert extract_claims("<plugadvpl-claims>{nao eh json}</plugadvpl-claims>") == []

    def test_last_block_wins(self) -> None:
        from plugadvpl.verify import extract_claims

        text = (
            '<plugadvpl-claims>{"claims":[{"id":"a"}]}</plugadvpl-claims> '
            '<plugadvpl-claims>{"claims":[{"id":"b"}]}</plugadvpl-claims>'
        )
        assert extract_claims(text)[0]["id"] == "b"


class TestCoverageAndConfidence:
    def test_complete_kinds_includes_dict_kinds_when_ingested(
        self, conn: sqlite3.Connection
    ) -> None:
        from plugadvpl.verify import verify_claims

        ck = verify_claims(conn, [])["coverage"]["complete_kinds"]
        assert "field" in ck
        assert "table" in ck

    def test_complete_kinds_empty_without_sx(self, tmp_path: Path) -> None:
        from plugadvpl.verify import verify_claims

        c = open_db(tmp_path / "bare.db")
        apply_migrations(c)
        assert verify_claims(c, [])["coverage"]["complete_kinds"] == []

    def test_hit_is_high_confidence(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        # "confiança cai em MISS, não em HIT": um match exato é alta confiança.
        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "function", "symbol": "ZMYFUNC"}]))
        assert r["c1"]["confidence"] == "high"

    def test_missing_customer_field_in_complete_kind_is_high(
        self, conn: sqlite3.Connection
    ) -> None:
        from plugadvpl.verify import verify_claims

        # ZX1_NOPE: campo customer (prefixo Z), SX3 completo p/ customer -> miss significativo.
        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "field", "symbol": "ZX1_NOPE"}]))
        assert r["c1"]["status"] == "not_found"
        assert r["c1"]["confidence"] == "high"

    def test_missing_standard_field_is_medium(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.verify import verify_claims

        # A1_NOPE: campo padrão TOTVS (não indexado por design) -> miss inconclusivo.
        r = _by_id(verify_claims(conn, [{"id": "c1", "kind": "field", "symbol": "A1_NOPE"}]))
        assert r["c1"]["status"] == "not_found"
        assert r["c1"]["confidence"] == "medium"
