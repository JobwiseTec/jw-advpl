"""Tests do trace_query (Universo 4 / Feature A v0.5.0)."""
from __future__ import annotations

from plugadvpl.query import _detect_entity_type


class TestAutoDetect:
    """Auto-detect tipo de entidade pra trace command."""

    def test_tabela_protheus_padrao(self) -> None:
        """SA1, SC5, SF2 — pattern [SZNQD]+letra+alfanum (3 chars)."""
        assert _detect_entity_type("SA1") == "tabela"
        assert _detect_entity_type("SC5") == "tabela"
        assert _detect_entity_type("ZA1") == "tabela"
        assert _detect_entity_type("ND0") == "tabela"

    def test_campo_protheus_padrao(self) -> None:
        """A1_COD, C5_NUM — pattern <letra><digit>_<nome>."""
        assert _detect_entity_type("A1_COD") == "campo"
        assert _detect_entity_type("C5_NUM") == "campo"
        assert _detect_entity_type("F2_DOC") == "campo"

    def test_funcao_fallback(self) -> None:
        """Identificadores sem padrão tabela/campo viram função."""
        assert _detect_entity_type("MaFisRef") == "funcao"
        assert _detect_entity_type("U_MyFn") == "funcao"
        assert _detect_entity_type("MATA410") == "funcao"
        assert _detect_entity_type("ValidaCampo") == "funcao"

    def test_ambiguous_uppercase_fallback_funcao(self) -> None:
        """4+ chars uppercase (rotinas TOTVS) NÃO viram tabela."""
        assert _detect_entity_type("FINA050") == "funcao"
        assert _detect_entity_type("MATA410") == "funcao"
