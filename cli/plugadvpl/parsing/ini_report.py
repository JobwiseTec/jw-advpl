"""Relatório HTML self-contained do ``ini-audit`` (``--format html``).

Função pura: recebe os scores por arquivo + a lista de findings (já consultados
do índice) e devolve uma página HTML única (CSS inline, sem dependências) com
card de score/selo por INI, findings agrupados por severidade e os justificados
(``ok_with_note``) numa seção à parte.
"""

from __future__ import annotations

import html
from typing import Any

# (emoji, cor do texto, cor de fundo) por severidade.
_SEV_STYLE: dict[str, tuple[str, str, str]] = {
    "critical": ("\U0001f534", "#b42318", "#fde8e6"),
    "warning": ("\U0001f7e1", "#9a6700", "#fff3cd"),
    "info": ("\u2139\ufe0f", "#0f5fb3", "#e6f0fb"),
}

# (cor do texto, cor de fundo, rótulo) por selo de conformidade.
_BADGE_STYLE: dict[str, tuple[str, str, str]] = {
    "compliant": ("#0f7b3f", "#e6f4ea", "EM CONFORMIDADE"),
    "partial": ("#9a6700", "#fff3cd", "PARCIALMENTE CONFORME"),
    "non_compliant": ("#b42318", "#fde8e6", "FORA DE CONFORMIDADE"),
}

_STYLE = (
    "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f5f6f8;color:#1a1a1a}"
    ".wrap{max-width:1000px;margin:0 auto;padding:24px}"
    "header{background:#1f2937;color:#fff;padding:18px 22px;border-radius:10px}"
    "header h1{margin:0;font-size:17px}"
    ".card{display:flex;align-items:center;gap:18px;background:#fff;border-radius:10px;"
    "padding:16px 20px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}"
    ".score{font-size:38px;font-weight:700}"
    ".badge{display:inline-block;padding:5px 12px;border-radius:999px;font-weight:700;font-size:12px}"
    ".meta{font-size:12px;color:#555;margin-top:4px}"
    "h2{font-size:15px;margin:22px 0 8px}"
    "table{border-collapse:collapse;width:100%;font-size:13px;background:#fff;border-radius:8px;"
    "overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}"
    "th,td{border-bottom:1px solid #eee;padding:7px 10px;text-align:left;vertical-align:top}"
    "th{background:#f0f2f5}"
    ".sev{padding:2px 8px;border-radius:999px;font-weight:700;font-size:12px}"
    "code{background:#f0f2f5;padding:1px 5px;border-radius:4px;font-size:12px}"
    "pre{background:#1f2937;color:#e6edf3;padding:14px;border-radius:8px;overflow:auto;"
    "font-size:12px;line-height:1.45;max-height:420px;white-space:pre-wrap;word-break:break-word}"
    ".copybtn{background:#2563eb;color:#fff;border:0;padding:6px 13px;border-radius:6px;"
    "cursor:pointer;font-size:13px;margin-bottom:6px}"
    "footer{text-align:center;color:#888;font-size:12px;margin:26px 0 8px}"
)


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _findings_table(findings: list[dict[str, Any]]) -> str:
    rows: list[str] = [
        "<table><thead><tr><th>Sev</th><th>Seção</th><th>Chave</th>"
        "<th>Linha</th><th>Regra</th><th>Trecho</th><th>Como corrigir</th></tr></thead><tbody>"
    ]
    for f in findings:
        sev = str(f.get("severidade", "info"))
        emoji, fg, bg = _SEV_STYLE.get(sev, ("·", "#333", "#eee"))
        rows.append(
            "<tr>"
            f"<td><span class='sev' style='color:{fg};background:{bg}'>{emoji} {_esc(sev)}</span></td>"
            f"<td>{_esc(f.get('section'))}</td><td>{_esc(f.get('key'))}</td>"
            f"<td>{_esc(f.get('linha'))}</td><td><code>{_esc(f.get('regra_id'))}</code></td>"
            f"<td><code>{_esc(f.get('snippet'))}</code></td><td>{_esc(f.get('sugestao_fix'))}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def render_ini_audit_html(
    files: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> str:
    """Monta o relatório HTML a partir dos scores por arquivo + findings."""
    by_file: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        by_file.setdefault(str(f.get("arquivo")), []).append(f)

    out: list[str] = [
        "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Auditoria de INI Protheus</title>",
        f"<style>{_STYLE}</style></head><body><div class='wrap'>",
        "<header><h1>Auditoria de INI Protheus</h1></header>",
    ]

    if not files:
        out.append("<p><em>Nenhum INI auditado.</em></p></div></body></html>")
        return "\n".join(out)

    for idx, fl in enumerate(files):
        arquivo = str(fl.get("arquivo"))
        compliance = str(fl.get("compliance") or "")
        fg, bg, label = _BADGE_STYLE.get(compliance, ("#333", "#eee", compliance or "—"))
        score = fl.get("score")
        score_txt = f"{float(score):.1f}" if score is not None else "—"
        items = by_file.get(arquivo, [])
        active = [f for f in items if f.get("status") == "active"]
        notes = [f for f in items if f.get("status") == "ok_with_note"]

        out.append("<div class='card'>")
        out.append(f"<div class='score' style='color:{fg}'>{score_txt}</div>")
        out.append(
            f"<div><span class='badge' style='color:{fg};background:{bg}'>{_esc(label)}</span>"
            f"<div class='meta'>{_esc(arquivo)} · tipo <b>{_esc(fl.get('tipo'))}</b>"
            f" · papel <b>{_esc(fl.get('role'))}</b> · {len(active)} findings"
            f" · {len(notes)} justificados</div></div>"
        )
        out.append("</div>")

        crit = [f for f in active if f.get("severidade") == "critical"]
        warn = [f for f in active if f.get("severidade") == "warning"]
        info = [f for f in active if f.get("severidade") == "info"]
        for titulo, grupo in (
            ("\U0001f534 Críticos", crit),
            ("\U0001f7e1 Warnings", warn),
            ("\u2139\ufe0f Info", info),
        ):
            if grupo:
                out.append(f"<h2>{titulo} ({len(grupo)})</h2>")
                out.append(_findings_table(grupo))
        if notes:
            out.append(f"<h2>✅ Justificados / redundantes ({len(notes)})</h2>")
            out.append(_findings_table(notes))

        suggested = str(fl.get("suggested_ini") or "")
        if suggested.strip():
            sid = f"sug{idx}"
            out.append("<h2>🛠️ INI sugerido (correções preservando comentários)</h2>")
            out.append(f"<button class='copybtn' onclick=\"_cp('{sid}')\">📋 Copiar</button>")
            out.append(f"<pre id='{sid}'>{_esc(suggested)}</pre>")

    out.append("<footer>Gerado por plugadvpl ini-audit --format html</footer>")
    out.append(
        "<script>function _cp(id){const e=document.getElementById(id);"
        "navigator.clipboard.writeText(e.innerText)}</script>"
    )
    out.append("</div></body></html>")
    return "\n".join(out)


__all__ = ["render_ini_audit_html"]
