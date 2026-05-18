"""Tests do trace_query (Universo 4 / Feature A v0.5.0)."""
from __future__ import annotations

from plugadvpl.query import _detect_entity_type, _trace_sort_key


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


class TestSortPriority:
    """v0.5.1 (#5): edges informativos vem no topo do output."""

    def test_table_definition_before_other_u2(self) -> None:
        """table_definition tem priority 0 — vem antes de in_relationship etc."""
        hits = [
            {"universo": 2, "edge": "in_relationship", "arquivo": "", "linha": 0},
            {"universo": 2, "edge": "table_definition", "arquivo": "", "linha": 0},
            {"universo": 2, "edge": "trigger_on_table", "arquivo": "", "linha": 0},
        ]
        sorted_hits = sorted(hits, key=_trace_sort_key)
        assert sorted_hits[0]["edge"] == "table_definition"

    def test_n_fields_priority_high(self) -> None:
        """n_fields também é informativo — vem cedo no bloco U2."""
        hits = [
            {"universo": 2, "edge": "indexed_by", "arquivo": "", "linha": 0},
            {"universo": 2, "edge": "n_fields", "arquivo": "", "linha": 0},
        ]
        sorted_hits = sorted(hits, key=_trace_sort_key)
        assert sorted_hits[0]["edge"] == "n_fields"

    def test_field_definition_priority_in_u2_for_campo(self) -> None:
        """field_definition (SX3 do campo) vem antes de gatilhos/perguntes."""
        hits = [
            {"universo": 2, "edge": "trigger_origin", "arquivo": "", "linha": 0},
            {"universo": 2, "edge": "field_definition", "arquivo": "", "linha": 0},
            {"universo": 2, "edge": "in_pergunte", "arquivo": "", "linha": 0},
        ]
        sorted_hits = sorted(hits, key=_trace_sort_key)
        assert sorted_hits[0]["edge"] == "field_definition"

    def test_u1_before_u2_before_u3(self) -> None:
        """Universos mantêm ordem 1 < 2 < 3 (priority secundário)."""
        hits = [
            {"universo": 3, "edge": "via_execauto", "arquivo": "", "linha": 0},
            {"universo": 1, "edge": "calls", "arquivo": "", "linha": 0},
            {"universo": 2, "edge": "in_pergunte", "arquivo": "", "linha": 0},
        ]
        sorted_hits = sorted(hits, key=_trace_sort_key)
        unis = [h["universo"] for h in sorted_hits]
        assert unis == [1, 2, 3]
