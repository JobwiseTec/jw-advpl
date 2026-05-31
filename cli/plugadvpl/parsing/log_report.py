"""Relatório HTML self-contained do ``log-diagnose`` (``--format html``).

Função pura: recebe o rótulo do(s) arquivo(s), os findings (já consultados do
índice, com ``snippet`` = trecho original), as métricas (memória/uptime) e —
opcionalmente — o resultado da correlação ``--link``, e devolve uma página HTML
única (CSS inline, sem dependências) com cards de severidade + métricas, bloco
de correlação console↔profile, resumo por categoria, tabela de findings com link
TDN/Oracle e o trecho original num expansível, e dicas de correção.
"""

from __future__ import annotations

import html
from typing import Any

_SEV: dict[str, tuple[str, str, str]] = {
    "critical": ("\U0001f534", "#b42318", "#fde8e6"),
    "warning": ("\U0001f7e1", "#9a6700", "#fff3cd"),
    "info": ("\u2139\ufe0f", "#0f5fb3", "#e6f0fb"),
}

_STYLE = """
  :root { font-family:-apple-system,"Segoe UI",Roboto,sans-serif; }
  body { margin:0; background:#f5f6f8; color:#1a1a1a; }
  .wrap { max-width:1060px; margin:0 auto; padding:24px; }
  header { background:#1f2937; color:#fff; padding:20px 24px; border-radius:10px; }
  header h1 { margin:0; font-size:18px; word-break:break-all; }
  .cards { display:flex; gap:14px; flex-wrap:wrap; margin:16px 0; }
  .card { background:#fff; border-radius:10px; padding:14px 18px; box-shadow:0 1px 3px rgba(0,0,0,.08); font-size:13px; }
  .card .big { font-size:26px; font-weight:700; }
  .sevwrap span { display:inline-block; padding:3px 9px; border-radius:999px; font-weight:700; font-size:12px; margin-right:6px; }
  .link-card { background:#eef6ff; border:1px solid #cfe3fb; border-radius:10px; padding:12px 16px; margin:14px 0; font-size:13px; line-height:1.6; }
  h2 { font-size:16px; margin:24px 0 10px; }
  table { width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.06); font-size:13px; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid #eee; vertical-align:top; }
  th { background:#f0f2f5; font-weight:600; }
  td.msg { font-family:ui-monospace, monospace; font-size:12px; }
  details { margin-top:4px; }
  summary { cursor:pointer; color:#2563eb; font-family:-apple-system,sans-serif; font-size:11px; }
  pre.orig { background:#1f2937; color:#e6edf3; padding:10px; border-radius:6px; margin:6px 0 2px;
    font-size:11px; line-height:1.4; white-space:pre-wrap; word-break:break-word; max-height:240px; overflow:auto; }
  .sev { padding:2px 8px; border-radius:999px; font-weight:700; font-size:12px; }
  code { background:#f0f2f5; padding:1px 5px; border-radius:4px; font-size:12px; }
  .tip { background:#fff; border-left:4px solid #2563eb; border-radius:6px; padding:10px 14px; margin:8px 0; font-size:13px; box-shadow:0 1px 3px rgba(0,0,0,.06); }
  .tip a { color:#2563eb; word-break:break-all; }
  a { color:#2563eb; }
  footer { text-align:center; color:#888; font-size:12px; margin:30px 0 10px; }
"""


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _ref_url(f: dict[str, Any]) -> str:
    """Deep-link Oracle pro ORA específico quando há ora_code; senão tdn_url."""
    ora = str(f.get("ora_code") or "").strip()
    if ora:
        return f"https://docs.oracle.com/error-help/db/{ora.lower()}/"
    return str(f.get("tdn_url") or "")


def render_log_diagnose_html(  # noqa: PLR0915
    file_label: str,
    total_events: int,
    findings: list[dict[str, Any]],
    metrics: dict[str, Any] | None = None,
    link: dict[str, Any] | None = None,
) -> str:
    """Monta o relatório a partir do rótulo do arquivo + findings + métricas."""
    metrics = metrics or {}
    by_sev = {"critical": 0, "warning": 0, "info": 0}
    by_cat: dict[str, int] = {}
    for f in findings:
        sev = str(f.get("severidade", "info"))
        by_sev[sev] = by_sev.get(sev, 0) + 1
        cat = str(f.get("categoria", "?"))
        by_cat[cat] = by_cat.get(cat, 0) + 1

    metric_bits: list[str] = []
    if metrics.get("uptime_seconds") is not None:
        metric_bits.append(f"Start Time: <b>{float(metrics['uptime_seconds']):.2f}s</b>")
    if metrics.get("memory_app_peak_mb"):
        metric_bits.append(f"Pico Memória: <b>{float(metrics['memory_app_peak_mb']):.1f} MB</b>")
    mos = metrics.get("memory_os_last")
    if mos:
        metric_bits.append(
            f"SO livre: <b>{float(mos['free_mb']):.0f}/{float(mos['physical_mb']):.0f} MB</b>"
        )
    metrics_line = " · ".join(metric_bits)

    enriched_thread = str((link or {}).get("thread") or "") if link and link.get("matched") else ""

    link_html = ""
    if link:
        st = "✅ correlacionado" if link.get("matched") else "⚠️ sem correlação"
        lm = link.get("metrics") or {}
        bits: list[str] = []
        if lm.get("memory_app_peak_mb"):
            bits.append(f"pico memória {float(lm['memory_app_peak_mb']):.1f} MB")
        if lm.get("uptime_seconds") is not None:
            bits.append(f"uptime {float(lm['uptime_seconds']):.2f}s")
        link_html = (
            "<div class='link-card'><b>🔗 Correlação console↔profile</b> — "
            f"{st} (por <code>{_esc(link.get('matched_by'))}</code>)<br>"
            f"Linkado: <code>{_esc(link.get('file'))}</code>"
            f" · env <b>{_esc(link.get('environment') or '—')}</b>"
            f" · thread <b>{_esc(link.get('thread') or '—')}</b> · Profile: {_esc(' | '.join(bits) or '—')}"
            + (f"<br>Stack: <code>{_esc(link.get('stack'))}</code>" if link.get("stack") else "")
            + f"<br>Findings enriquecidos: {link.get('enriched', 0)}</div>"
        )

    arows: list[str] = []
    for i, f in enumerate(findings, 1):
        sev = str(f.get("severidade", "info"))
        emoji, fg, bg = _SEV.get(sev, ("·", "#333", "#eee"))
        ref = _ref_url(f)
        ref_html = f"<a href='{_esc(ref)}' target='_blank'>ref</a>" if ref else ""
        linked = "🔗" if enriched_thread and str(f.get("thread_id")) == enriched_thread else ""
        original = str(f.get("snippet") or "")
        orig_html = (
            f"<details><summary>original</summary><pre class='orig'>{_esc(original)}</pre></details>"
            if original.strip() else ""
        )
        arows.append(
            f"<tr><td>{i}</td>"
            f"<td><span class='sev' style='color:{fg};background:{bg}'>{emoji} {_esc(sev)}</span></td>"
            f"<td>{_esc(f.get('categoria'))}</td><td>{_esc(str(f.get('timestamp') or '')[:19])}</td>"
            f"<td>{_esc(f.get('linha', '?'))}</td>"
            f"<td class='msg'>{_esc(str(f.get('message') or '')[:160])} {linked}{orig_html}</td>"
            f"<td>{ref_html}</td></tr>"
        )
    arows_html = "\n".join(arows) or "<tr><td colspan='7'>Sem findings classificados ✅</td></tr>"

    catrows = "\n".join(
        f"<tr><td>{_esc(c)}</td><td>{n}</td></tr>"
        for c, n in sorted(by_cat.items(), key=lambda x: -x[1])
    )

    seen: set[str] = set()
    tips: list[str] = []
    for f in findings:
        msg = str(f.get("message") or "")
        if msg in seen:
            continue
        seen.add(msg)
        tip = str(f.get("sugestao_fix") or "")
        if not tip:
            continue
        sev = str(f.get("severidade", "info"))
        emoji, fg, _bg = _SEV.get(sev, ("·", "#333", "#eee"))
        ref = _ref_url(f)
        ref_a = f"<br><a href='{_esc(ref)}' target='_blank'>🔗 {_esc(ref)}</a>" if ref else ""
        tips.append(
            f"<div class='tip'><b style='color:{fg}'>{emoji} [{_esc(f.get('categoria'))}] "
            f"{_esc(msg[:140])}</b><br>💡 {_esc(tip)}{ref_a}</div>"
        )
        if len(tips) >= 5:
            break
    tips_html = "\n".join(tips)

    metrics_card = f"<div class='card'>{metrics_line}</div>" if metrics_line else ""
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Log diagnose</title>
<style>{_STYLE}</style></head>
<body><div class="wrap">
<header><h1>Diagnóstico de Log Protheus — {_esc(file_label)}</h1></header>
<div class="cards">
  <div class="card"><div class="big">{len(findings)}</div>findings ({total_events} eventos)</div>
  <div class="card sevwrap">
    <span style="color:#b42318;background:#fde8e6">\U0001f534 {by_sev['critical']}</span>
    <span style="color:#9a6700;background:#fff3cd">\U0001f7e1 {by_sev['warning']}</span>
    <span style="color:#0f5fb3;background:#e6f0fb">\u2139\ufe0f {by_sev['info']}</span>
    <div style="margin-top:6px;color:#555">por severidade</div>
  </div>
  {metrics_card}
</div>
{link_html}
<h2>Resumo por categoria</h2>
<table><thead><tr><th>Categoria</th><th>Ocorrências</th></tr></thead><tbody>
{catrows}
</tbody></table>
<h2>Findings ({len(findings)})</h2>
<table><thead><tr><th>#</th><th>Sev</th><th>Categoria</th><th>Quando</th><th>Linha</th><th>Mensagem</th><th>Ref</th></tr></thead>
<tbody>
{arows_html}
</tbody></table>
{f'<h2>Dicas de correção</h2>{tips_html}' if tips_html else ''}
<footer>Gerado por plugadvpl log-diagnose --format html</footer>
</div></body></html>"""


__all__ = ["render_log_diagnose_html"]
