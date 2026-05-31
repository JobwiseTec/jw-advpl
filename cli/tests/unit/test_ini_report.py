"""Testes de cli/plugadvpl/parsing/ini_report.py (renderer HTML do ini-audit)."""
from __future__ import annotations

from typing import Any

from plugadvpl.parsing.ini_report import render_ini_audit_html


def _report(**comp_over: Any) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "filename": "appserver.ini", "ini_type": "appserver", "ini_role": "standalone",
        "encoding_info": {"detected": "cp1252", "has_bom": False, "warnings": []},
        "meta": {"total_sections": 3, "total_commented_sections": 1, "total_keys": 10,
                 "total_commented": 0, "total_dirty_lines": 2},
        "commented_sections": [{"section": "OldEnv", "line": 12}],
        "dirty_lines": [{"line": 5, "content": "lixo solto", "reason": "fora de seção"}],
    }
    comp: dict[str, Any] = {
        "score": 72.0, "compliance_status": "partial", "compliance_label": "PARCIALMENTE CONFORME",
        "summary": {"ok": 8, "mismatch": 2, "missing": 1, "intentional": 1,
                    "unknown_keys": 0, "total_rules": 12},
        "findings": [], "unknown_keys": [], "suggested_ini": "",
    }
    comp.update(comp_over)
    return {"parsed": parsed, "comp": comp}


class TestRenderIniAuditHtml:
    def test_valid_self_contained_with_scorecard(self) -> None:
        html = render_ini_audit_html([_report()])
        assert html.startswith("<!DOCTYPE html>")
        assert html.rstrip().endswith("</html>")
        assert "<style>" in html
        assert "72.0" in html
        assert "PARCIALMENTE CONFORME" in html
        assert "Regras avaliadas:" in html

    def test_criticals_and_warnings_tables(self) -> None:
        comp = {
            "findings": [
                {"section": "General", "key_name": "MaxStringSize", "severity": "critical",
                 "status": "active", "current_value": "100", "recommended_value": "10",
                 "description": "compat XML"},
                {"section": "TCP", "key_name": "Port", "severity": "warning",
                 "status": "active", "current_value": "1", "recommended_value": "2"},
            ],
        }
        html = render_ini_audit_html([_report(**comp)])
        assert "🔴 Críticos (1)" in html
        assert "🟡 Warnings (1)" in html
        assert "MaxStringSize" in html
        assert "Recomendado" in html

    def test_missing_current_value_shows_placeholder(self) -> None:
        comp = {"findings": [
            {"section": "JOB_WS", "key_name": "Main", "severity": "critical",
             "status": "active", "current_value": None, "recommended_value": "WS_START",
             "description": "obrigatório"},
        ]}
        html = render_ini_audit_html([_report(**comp)])
        assert "&lt;missing&gt;" in html

    def test_ok_with_note_section(self) -> None:
        comp = {"findings": [
            {"section": "DBAccess", "key_name": "Server", "severity": "info",
             "status": "ok_with_note", "current_value": None,
             "comment": "Seção alternativa redundante"},
        ]}
        html = render_ini_audit_html([_report(**comp)])
        assert "Justificados" in html
        assert "redundante" in html

    def test_encoding_banner(self) -> None:
        rep = _report()
        rep["parsed"]["encoding_info"] = {
            "detected": "utf-8-bom", "has_bom": True,
            "warnings": ["Arquivo possui BOM UTF-8."],
        }
        html = render_ini_audit_html([rep])
        assert "warn-banner" in html
        assert "BOM UTF-8" in html

    def test_unknown_commented_dirty_sections(self) -> None:
        comp = {"unknown_keys": [
            {"section": "General", "key_name": "tomate", "value": "1",
             "reason": "typo ou obsoleta"},
        ]}
        html = render_ini_audit_html([_report(**comp)])
        assert "Chaves não reconhecidas" in html
        assert "tomate" in html
        assert "Seções comentadas" in html
        assert "Linhas malformadas" in html

    def test_suggested_ini_with_copy_button(self) -> None:
        comp = {"suggested_ini": "[General]\nMaxStringSize=10  ; [CORRECAO] valor anterior: 100\n"}
        html = render_ini_audit_html([_report(**comp)])
        assert "INI sugerido" in html
        assert "copybtn" in html
        assert "_cp(" in html
        assert "[CORRECAO]" in html

    def test_empty_reports_placeholder(self) -> None:
        html = render_ini_audit_html([])
        assert "Nenhum INI auditado" in html
        assert html.rstrip().endswith("</html>")

    def test_escapes_html(self) -> None:
        comp = {"findings": [
            {"section": "General", "key_name": "X", "severity": "critical", "status": "active",
             "current_value": "<script>XSS</script>", "recommended_value": "1", "description": "d"},
        ]}
        html = render_ini_audit_html([_report(**comp)])
        assert "<script>XSS" not in html
        assert "&lt;script&gt;XSS&lt;/script&gt;" in html

    def test_escapes_html_multi_vector_xss(self) -> None:
        """Regression: nenhum dos vetores XSS comuns deve vazar em qualquer campo."""
        comp = {"findings": [
            {
                "section": "<svg onload=alert('s')>",
                "key_name": "a&b<c>d",
                "severity": "critical",
                "status": "active",
                "current_value": "<img src=x onerror=alert(1)>",
                "recommended_value": "javascript:alert(2)",
                "description": "</td><td>injected",
            },
        ], "unknown_keys": [
            {"section": "<x>", "key_name": "y", "value": "<z>", "reason": "<w>"},
        ]}
        html = render_ini_audit_html([_report(**comp)])
        # Nenhum vetor raw deve sobreviver fora de contexto escaped
        assert "<svg onload=" not in html
        assert "<img src=x onerror=" not in html
        # O <script> que aparece é APENAS o template do clipboard (legítimo)
        assert html.count("<script>") == 1  # o template <script>function _cp</script>
        # </td> injetado não pode escapar célula
        assert "</td><td>injected" not in html
        assert "&lt;/td&gt;&lt;td&gt;injected" in html
        # &amp; usado pra escapar literais
        assert "a&amp;b&lt;c&gt;d" in html
