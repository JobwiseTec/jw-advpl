"""Testes de cli/plugadvpl/parsing/log_report.py (renderer HTML do log-diagnose)."""
from __future__ import annotations

from typing import Any

from plugadvpl.parsing.log_report import render_log_diagnose_html


def _finding(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "arquivo": "console.log", "linha": 100, "timestamp": "2026-03-06T22:48:20",
        "thread_id": "31716", "severidade": "critical", "categoria": "database",
        "rule_id": "LOG-DB-ORA", "message": "ORA-00904: invalid identifier",
        "snippet": "THREAD ERROR ... ORA-00904 ...", "sugestao_fix": "Verificar coluna",
        "tdn_url": "", "ora_code": "ORA-00904",
    }
    base.update(over)
    return base


class TestRenderLogDiagnoseHtml:
    def test_valid_self_contained_with_cards(self) -> None:
        html = render_log_diagnose_html("console.log", 1000, [_finding()])
        assert html.startswith("<!DOCTYPE html>")
        assert html.rstrip().endswith("</html>")
        assert "<style>" in html
        assert "Diagnóstico de Log Protheus — console.log" in html
        assert "por severidade" in html
        assert "1000 eventos" in html

    def test_severity_and_category_summary(self) -> None:
        findings = [_finding(), _finding(severidade="warning", categoria="connection")]
        html = render_log_diagnose_html("c.log", 10, findings)
        assert "Resumo por categoria" in html
        assert "database" in html
        assert "connection" in html

    def test_oracle_deeplink(self) -> None:
        html = render_log_diagnose_html("c.log", 10, [_finding(ora_code="ORA-00933")])
        assert "https://docs.oracle.com/error-help/db/ora-00933/" in html

    def test_tdn_url_when_no_ora(self) -> None:
        html = render_log_diagnose_html(
            "c.log", 10,
            [_finding(ora_code="", tdn_url="https://tdn.totvs.com/x", categoria="thread_error")],
        )
        assert "https://tdn.totvs.com/x" in html

    def test_original_excerpt_expandable(self) -> None:
        html = render_log_diagnose_html("c.log", 10, [_finding(snippet="LINHA ORIGINAL DO ERRO")])
        assert "<details><summary>original</summary>" in html
        assert "LINHA ORIGINAL DO ERRO" in html

    def test_correction_tips(self) -> None:
        html = render_log_diagnose_html("c.log", 10, [_finding(sugestao_fix="Reiniciar serviço")])
        assert "Dicas de correção" in html
        assert "Reiniciar serviço" in html

    def test_link_correlation_block(self) -> None:
        link = {
            "file": "profile.log", "environment": "PRD", "thread": "31716",
            "metrics": {"memory_app_peak_mb": 4096.0, "uptime_seconds": 88.3},
            "stack": "ABCEST73", "matched": True, "matched_by": "environment::thread",
            "enriched": 1,
        }
        html = render_log_diagnose_html("c.log", 10, [_finding(thread_id="31716")], link=link)
        assert "Correlação console" in html
        assert "environment::thread" in html
        assert "4096" in html
        assert "ABCEST73" in html
        assert "🔗" in html  # finding na thread enriquecida marcado

    def test_no_match_link_graceful(self) -> None:
        link = {"file": "p.log", "environment": "", "thread": "9999", "metrics": {},
                "stack": "", "matched": False, "matched_by": "none", "enriched": 0}
        html = render_log_diagnose_html("c.log", 10, [_finding()], link=link)
        assert "sem correlação" in html

    def test_metrics_card(self) -> None:
        metrics = {"uptime_seconds": 42.5, "memory_app_peak_mb": 2048.0}
        html = render_log_diagnose_html("c.log", 10, [_finding()], metrics=metrics)
        assert "Start Time" in html
        assert "2048.0 MB" in html

    def test_empty_findings(self) -> None:
        html = render_log_diagnose_html("c.log", 0, [])
        assert "Sem findings classificados" in html
        assert html.rstrip().endswith("</html>")

    def test_escapes_html(self) -> None:
        html = render_log_diagnose_html("c.log", 10, [_finding(message="<script>XSS</script>")])
        assert "<script>XSS" not in html
        assert "&lt;script&gt;XSS" in html

    def test_escapes_html_multi_vector_xss(self) -> None:
        """Regression: vetores XSS em múltiplos campos (snippet, file_label,
        link.environment, link.stack) — todos devem passar por html.escape()."""
        finding = _finding(
            message="<img src=x onerror=alert(1)>",
            snippet="</pre><script>orig</script>",
            categoria="<svg onload=alert('c')>",
            sugestao_fix="<a href='javascript:alert(1)'>click</a>",
        )
        link = {
            "file": "<x>.log", "environment": "<env>", "thread": "<t>",
            "metrics": {}, "stack": "</code><script>s</script>",
            "matched": True, "matched_by": "<m>",
            "enriched": 1,
        }
        out = render_log_diagnose_html(
            "<title-injection></h1>",
            10,
            [finding],
            link=link,
        )
        # Nenhum vetor raw deve sobreviver
        assert "<img src=x onerror=" not in out
        assert "<svg onload=" not in out
        assert "<a href='javascript:" not in out
        assert "</title-injection></h1>" not in out
        assert "</pre><script>orig" not in out
        assert "</code><script>s" not in out
        # Escaped forms presentes
        assert "&lt;img src=x onerror=alert(1)&gt;" in out
        assert "&lt;svg onload=" in out
        assert "&lt;env&gt;" in out

    def test_ora_code_in_deeplink_is_lowercased(self) -> None:
        """ora_code 'ORA-00904' vira 'ora-00904' no URL (formato Oracle docs)."""
        out = render_log_diagnose_html("c.log", 10, [_finding(ora_code="ORA-00942")])
        assert "https://docs.oracle.com/error-help/db/ora-00942/" in out
        # Versão maiúscula NÃO vaza no path
        assert "/ORA-00942/" not in out
