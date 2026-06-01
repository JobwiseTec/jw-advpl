"""Testes de cli/plugadvpl/parsing/semantica.py (issue #27 — campos_semantica)."""
from __future__ import annotations

from plugadvpl.parsing.semantica import load_semantica_catalog, lookup_semantica

_CAT = [
    {
        "tabela": "SB6",
        "campo": "B6_CLIFOR",
        "discriminador": "B6_PODER3=R",
        "semantica": "Detentor (poder de terceiros), não o cliente da NF",
        "fonte": "TDN",
    },
    {
        "tabela": "SD2",
        "campo": "D2_NFORI",
        "discriminador": "D2_TIPO=D",
        "semantica": "Aponta para a NF de Remessa original",
        "fonte": "TDN",
    },
]


class TestLookupSemantica:
    def test_returns_entries_for_field(self) -> None:
        rows = lookup_semantica(_CAT, "B6_CLIFOR")
        assert len(rows) == 1
        assert rows[0]["discriminador"] == "B6_PODER3=R"

    def test_case_insensitive(self) -> None:
        assert len(lookup_semantica(_CAT, "b6_clifor")) == 1

    def test_unknown_field_returns_empty(self) -> None:
        assert lookup_semantica(_CAT, "A1_COD") == []


class TestLoadSemanticaCatalog:
    def test_loads_bundled_catalog(self) -> None:
        catalog = load_semantica_catalog()
        assert isinstance(catalog, list)
        campos = {c["campo"] for c in catalog}
        assert "B6_CLIFOR" in campos

    def test_entries_have_required_fields(self) -> None:
        for c in load_semantica_catalog():
            for field in ("tabela", "campo", "discriminador", "semantica", "fonte"):
                assert field in c
