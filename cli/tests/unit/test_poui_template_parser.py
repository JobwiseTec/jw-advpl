"""Testes do parser de templates PO UI — extract_poui_template_usage (Fase 3b)."""

from __future__ import annotations

from plugadvpl.parsing.poui import extract_poui_template_usage


class TestExtractPouiTemplateUsage:
    def test_input_binding(self) -> None:
        html = "<po-button [p-label]='x'></po-button>"
        rows = extract_poui_template_usage(html)
        assert any(
            r["componente"] == "po-button" and r["binding"] == "p-label" and r["kind"] == "input"
            for r in rows
        )

    def test_output_binding(self) -> None:
        html = "<po-button (p-click)='fn()'></po-button>"
        rows = extract_poui_template_usage(html)
        assert any(
            r["componente"] == "po-button" and r["binding"] == "p-click" and r["kind"] == "output"
            for r in rows
        )

    def test_plain_attr_is_input(self) -> None:
        html = "<po-button p-kind='primary'></po-button>"
        rows = extract_poui_template_usage(html)
        assert any(r["binding"] == "p-kind" and r["kind"] == "input" for r in rows)

    def test_two_way_binding_is_input(self) -> None:
        html = "<po-table [(p-selected)]='sel'></po-table>"
        rows = extract_poui_template_usage(html)
        assert any(r["binding"] == "p-selected" and r["kind"] == "input" for r in rows)

    def test_multiple_bindings_single_tag(self) -> None:
        html = "<po-button [p-label]='x' (p-click)='f()' p-kind='d'>"
        rows = extract_poui_template_usage(html)
        bindings = {r["binding"] for r in rows}
        assert "p-label" in bindings
        assert "p-click" in bindings
        assert "p-kind" in bindings

    def test_line_number(self) -> None:
        html = "\n\n<po-button [p-label]='x'>"
        rows = extract_poui_template_usage(html)
        assert rows[0]["linha"] == 3

    def test_dedup(self) -> None:
        html = "<po-button [p-label]='x' [p-label]='y'>"
        rows = extract_poui_template_usage(html)
        count = sum(1 for r in rows if r["binding"] == "p-label")
        assert count == 1

    def test_non_po_tag_ignored(self) -> None:
        html = "<div [p-label]='x'></div>"
        rows = extract_poui_template_usage(html)
        assert rows == []

    def test_returns_required_keys(self) -> None:
        html = "<po-input [p-mask]='mask'>"
        rows = extract_poui_template_usage(html)
        assert rows
        for r in rows:
            assert {"componente", "binding", "kind", "linha"} <= r.keys()
