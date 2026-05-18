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

    def test_campo_3_chars_before_underscore(self) -> None:
        """v0.5.1 (#1): campos com 3 chars antes do '_' (módulos Comex/GFE).

        Antes: regex exigia exatamente 2 chars. Falha em EE7_ZSUBEX,
        DAI_NFISCA, EEC_PREEMB.
        """
        assert _detect_entity_type("EE7_ZSUBEX") == "campo"
        assert _detect_entity_type("DAI_NFISCA") == "campo"
        assert _detect_entity_type("EEC_PREEMB") == "campo"
        assert _detect_entity_type("GV4_XMEMB") == "campo"
        # 2 chars continua casando
        assert _detect_entity_type("A1_COD") == "campo"

    def test_tabela_modulos_non_standard_via_fallback_regex(self) -> None:
        """v0.5.1 (#2 fallback): regex aceita prefixo ampliado quando
        entidade não está no índice (sem lookup-first DB).

        EE7/DA3/GV4/EEC/CCH/C09 são tabelas TOTVS válidas mas começam
        com letras diferentes de [SZNQD]. Regex relaxado pra 3 chars
        ASCII uppercase quando primeiro char é letra.
        """
        # Sem conn, é só regex fallback — esses devem virar 'tabela'
        # quando passados sem outras pistas:
        assert _detect_entity_type("EE7") == "tabela"
        assert _detect_entity_type("DA3") == "tabela"
        assert _detect_entity_type("DAI") == "tabela"
        assert _detect_entity_type("GV4") == "tabela"
        assert _detect_entity_type("EEC") == "tabela"
        assert _detect_entity_type("CCH") == "tabela"
