"""Relatório HTML self-contained do ``ini-audit`` (``--format html``).

Função pura: recebe, por arquivo, o ``parsed`` (re-parse do INI: tipo/papel/
encoding/seções comentadas/linhas malformadas) e o ``comp`` (score + findings +
unknown_keys + INI sugerido vindos do índice) e devolve uma página HTML única
(CSS inline, sem dependências) com header+meta, banner de encoding, card de
score/selo, tabelas de Críticos/Warnings/justificados, chaves não-reconhecidas,
seções comentadas, linhas malformadas e o INI sugerido com botão copiar.
"""

from __future__ import annotations

import html
from typing import Any

_BADGE_COLORS: dict[str, tuple[str, str]] = {
    "compliant": ("#0f7b3f", "#e6f4ea"),
    "partial": ("#9a6700", "#fff3cd"),
    "non_compliant": ("#b42318", "#fde8e6"),
}

_STYLE = """
  body { font-family:-apple-system,"Segoe UI",Roboto,sans-serif; margin:0; background:#f5f6f8; color:#1a1a1a; }
  .wrap { max-width:1000px; margin:0 auto; padding:24px; }
  header { background:#1f2937; color:#fff; padding:20px 24px; border-radius:10px; margin-top:18px; }
  header h1 { margin:0 0 6px; font-size:18px; word-break:break-all; }
  header .meta { font-size:13px; opacity:.85; }
  .scorecard { display:flex; align-items:center; gap:20px; background:#fff; border-radius:10px;
    padding:20px 24px; margin:16px 0; box-shadow:0 1px 3px rgba(0,0,0,.08); }
  .score { font-size:44px; font-weight:700; }
  .badge { display:inline-block; padding:6px 14px; border-radius:999px; font-weight:700; font-size:13px; }
  .counts { font-size:13px; color:#555; margin-top:6px; }
  .counts b { color:#1a1a1a; }
  .warn-banner { background:#fde8e6; color:#b42318; padding:10px 14px; border-radius:8px; margin:10px 0; font-size:14px; }
  h2 { font-size:16px; margin:26px 0 10px; }
  table { width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden;
    box-shadow:0 1px 3px rgba(0,0,0,.06); font-size:13px; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid #eee; vertical-align:top; }
  th { background:#f0f2f5; font-weight:600; }
  td.cmt { color:#555; font-style:italic; }
  ul { background:#fff; border-radius:8px; padding:12px 12px 12px 34px; box-shadow:0 1px 3px rgba(0,0,0,.06); font-size:13px; }
  li { margin:4px 0; }
  code { background:#f0f2f5; padding:1px 5px; border-radius:4px; font-size:12px; }
  pre { background:#1f2937; color:#e6edf3; padding:16px; border-radius:8px; overflow:auto;
    font-size:12px; line-height:1.45; max-height:520px; white-space:pre-wrap; word-break:break-word; }
  .copybtn { background:#2563eb; color:#fff; border:0; padding:7px 14px; border-radius:6px;
    cursor:pointer; font-size:13px; margin-bottom:8px; }
  footer { text-align:center; color:#888; font-size:12px; margin:30px 0 10px; }
"""


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _rows(findings: list[dict[str, Any]], cols: list[str]) -> str:
    out: list[str] = []
    for f in findings:
        tds = ""
        for c in cols:
            val = f.get(c)
            if c == "current_value" and not val:
                val = "<missing>"
            tds += f"<td>{_esc(val)}</td>"
        out.append(f"<tr>{tds}</tr>")
    return "\n".join(out)


def _file_block(parsed: dict[str, Any], comp: dict[str, Any], idx: int) -> str:
    enc = parsed.get("encoding_info", {})
    m = parsed.get("meta", {})
    status = str(comp.get("compliance_status", ""))
    fg, bg = _BADGE_COLORS.get(status, ("#333", "#eee"))
    s = comp.get("summary", {})
    findings = comp.get("findings", [])
    crit = [
        f for f in findings if f.get("severity") == "critical" and f.get("status") != "ok_with_note"
    ]
    warn = [
        f for f in findings if f.get("severity") == "warning" and f.get("status") != "ok_with_note"
    ]
    note = [f for f in findings if f.get("status") == "ok_with_note"]

    out: list[str] = ["<header>"]
    out.append(f"<h1>Auditoria de INI Protheus — {_esc(parsed.get('filename'))}</h1>")
    out.append(
        f"<div class='meta'>Tipo: <b>{_esc(parsed.get('ini_type'))}</b> · "
        f"Papel: <b>{_esc(parsed.get('ini_role'))}</b> · "
        f"Encoding: <b>{_esc(enc.get('detected'))}</b> (BOM={_esc(enc.get('has_bom'))}) · "
        f"Seções: {m.get('total_sections', 0)} ativas / {m.get('total_commented_sections', 0)} comentadas · "
        f"Chaves: {m.get('total_keys', 0)} / {m.get('total_commented', 0)} comentadas · "
        f"Dirty: {m.get('total_dirty_lines', 0)}</div></header>"
    )

    for w in enc.get("warnings", []):
        out.append(f"<div class='warn-banner'>⚠️ {_esc(w)}</div>")

    score = float(comp.get("score", 0.0))
    out.append("<div class='scorecard'>")
    out.append(f"<div class='score' style='color:{fg}'>{score:.1f}</div>")
    out.append(
        f"<div><span class='badge' style='color:{fg};background:{bg}'>"
        f"{_esc(comp.get('compliance_label'))}</span>"
        f"<div class='counts'>OK: <b>{s.get('ok', 0)}</b> · Mismatch: <b>{s.get('mismatch', 0)}</b> · "
        f"Missing: <b>{s.get('missing', 0)}</b> · Intencional: <b>{s.get('intentional', 0)}</b> · "
        f"Unknown: <b>{s.get('unknown_keys', 0)}</b> · "
        f"Regras avaliadas: <b>{s.get('total_rules', 0)}</b></div></div></div>"
    )

    if crit:
        out.append(f"<h2>🔴 Críticos ({len(crit)})</h2>")
        out.append(
            "<table><thead><tr><th>Seção</th><th>Chave</th><th>Atual</th>"
            "<th>Recomendado</th><th>Detalhe</th></tr></thead><tbody>"
            + _rows(
                crit, ["section", "key_name", "current_value", "recommended_value", "description"]
            )
            + "</tbody></table>"
        )
    if warn:
        out.append(f"<h2>🟡 Warnings ({len(warn)})</h2>")
        out.append(
            "<table><thead><tr><th>Seção</th><th>Chave</th><th>Atual</th>"
            "<th>Recomendado</th></tr></thead><tbody>"
            + _rows(warn, ["section", "key_name", "current_value", "recommended_value"])
            + "</tbody></table>"
        )
    if note:
        nrows = "\n".join(
            f"<tr><td>{_esc(f.get('section'))}</td><td>{_esc(f.get('key_name'))}</td>"
            f"<td>{_esc(f.get('current_value'))}</td>"
            f"<td class='cmt'>{_esc((f.get('comment') or '')[:160])}</td></tr>"
            for f in note
        )
        out.append(f"<h2>\u2139\ufe0f Justificados / redundantes (ok_with_note) ({len(note)})</h2>")
        out.append(
            "<table><thead><tr><th>Seção</th><th>Chave</th><th>Valor</th>"
            f"<th>Nota</th></tr></thead><tbody>{nrows}</tbody></table>"
        )

    unk = comp.get("unknown_keys") or []
    if unk:
        urows = "\n".join(
            f"<li><code>[{_esc(u.get('section'))}].{_esc(u.get('key_name'))}</code> = "
            f"<code>{_esc(u.get('value'))}</code> — {_esc(u.get('reason'))}</li>"
            for u in unk
        )
        out.append(f"<h2>🔍 Chaves não reconhecidas ({len(unk)})</h2><ul>{urows}</ul>")

    csec = parsed.get("commented_sections") or []
    if csec:
        crows = "\n".join(
            f"<li><code>;[{_esc(c.get('section'))}]</code> (linha {_esc(c.get('line'))})</li>"
            for c in csec
        )
        out.append(f"<h2>🗨️ Seções comentadas ({len(csec)})</h2><ul>{crows}</ul>")

    dirty = parsed.get("dirty_lines") or []
    if dirty:
        drows = "\n".join(
            f"<li>linha {_esc(d.get('line'))}: <code>{_esc(str(d.get('content') or '')[:80])}</code> → "
            f"{_esc(d.get('reason'))}</li>"
            for d in dirty
        )
        out.append(f"<h2>🚮 Linhas malformadas ({len(dirty)})</h2><ul>{drows}</ul>")

    suggested = str(comp.get("suggested_ini") or "")
    if suggested.strip():
        sid = f"sug{idx}"
        out.append("<h2>🛠️ INI sugerido (correções preservando comentários)</h2>")
        out.append(f"<button class='copybtn' onclick=\"_cp('{sid}')\">📋 Copiar</button>")
        out.append(f"<pre id='{sid}'>{_esc(suggested)}</pre>")

    return "\n".join(out)


def render_ini_audit_html(reports: list[dict[str, Any]]) -> str:
    """``reports``: lista de ``{'parsed': {...}, 'comp': {...}}`` (1 por INI)."""
    out: list[str] = [
        "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Auditoria de INI Protheus</title>",
        f"<style>{_STYLE}</style></head><body><div class='wrap'>",
    ]
    if not reports:
        out.append("<p><em>Nenhum INI auditado.</em></p></div></body></html>")
        return "\n".join(out)
    for idx, rep in enumerate(reports):
        out.append(_file_block(rep.get("parsed", {}), rep.get("comp", {}), idx))
    out.append("<footer>Gerado por plugadvpl ini-audit --format html</footer>")
    out.append(
        "<script>function _cp(id){const e=document.getElementById(id);"
        "navigator.clipboard.writeText(e.innerText)}</script>"
    )
    out.append("</div></body></html>")
    return "\n".join(out)


__all__ = ["render_ini_audit_html"]
