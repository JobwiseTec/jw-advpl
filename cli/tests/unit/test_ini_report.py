"""Testes de cli/plugadvpl/parsing/ini_report.py (renderer HTML do ini-audit)."""
from __future__ import annotations

from typing import Any

from plugadvpl.parsing.ini_report import render_ini_audit_html


def _file(arquivo: str, score: float, compliance: str) -> dict[str, Any]:
    return {
        "arquivo": arquivo, "tipo": "appserver", "role": "standalone",
        "score": score, "compliance": compliance,
    }


def _finding(arquivo: str, sev: str, status: str = "active", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "arquivo": arquivo, "tipo": "appserver", "role": "standalone",
        "section": "General", "key": "K1", "linha": 1, "regra_id": "X-1",
        "severidade": sev, "snippet": "[General] K1=x", "sugestao_fix": "ajuste K1",
        "status": status,
    }
    base.update(kw)
    return base


class TestRenderIniAuditHtml:
    def test_valid_self_contained_html(self) -> None:
        html = render_ini_audit_html(
            [_file("appserver.ini", 72.0, "partial")],
            [_finding("appserver.ini", "critical")],
        )
        assert html.startswith("<!DOCTYPE html>")
        assert html.rstrip().endswith("</html>")
        assert "<style>" in html  # CSS inline (self-contained)
        assert "72.0" in html
        assert "PARCIALMENTE CONFORME" in html

    def test_groups_by_severity(self) -> None:
        html = render_ini_audit_html(
            [_file("a.ini", 50.0, "non_compliant")],
            [
                _finding("a.ini", "critical"),
                _finding("a.ini", "warning"),
                _finding("a.ini", "info"),
            ],
        )
        assert "Críticos (1)" in html
        assert "Warnings (1)" in html
        assert "Info (1)" in html

    def test_ok_with_note_separate_section(self) -> None:
        html = render_ini_audit_html(
            [_file("a.ini", 100.0, "compliant")],
            [_finding("a.ini", "warning", status="ok_with_note")],
        )
        assert "Justificados" in html
        # ok_with_note não conta como finding ativo no resumo
        assert "0 findings" in html
        assert "1 justificados" in html

    def test_empty_files_placeholder(self) -> None:
        html = render_ini_audit_html([], [])
        assert "Nenhum INI auditado" in html
        assert html.rstrip().endswith("</html>")

    def test_escapes_html_in_snippet(self) -> None:
        html = render_ini_audit_html(
            [_file("a.ini", 40.0, "non_compliant")],
            [_finding("a.ini", "critical", snippet="<script>alert(1)</script>")],
        )
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
