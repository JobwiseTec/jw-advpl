"""Diagnose engine — Stage 2 do pipeline de log.

Itera ``log_events`` em ordem reversa (mais recente primeiro), aplica
``log_rules`` ordenadas por ``priority``, e grava ``log_findings`` com
correction tip cruzada de ``log_tips``.

Estratégia espelha ``env_manager.parse_log.analyze_events_reverse``:

    Stage 2 (bottom-up, short-circuit):
        - Inverte lista de eventos (recentes primeiro)
        - Pra cada evento: aplica is_noise → skip; testa ALERT_RULES por priority
        - Primeiro match vence (não cumulativo por evento)
        - Curta-circuita quando atinge max_findings ou janela --since

Janela ``--since`` aceita ``"30m"`` / ``"24h"`` / ``"7d"`` e é calculada
RELATIVAMENTE ao último timestamp encontrado no log (não ao wall clock).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from plugadvpl.parsing.log import RE_NOISE_PATTERNS


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(slots=True)
class _CompiledRule:
    rule_id: str
    category: str
    severidade: str
    pattern: re.Pattern[str]
    message_template: str
    priority: int


@dataclass(slots=True)
class _CompiledTip:
    tip_id: str
    category: str
    pattern: re.Pattern[str]
    tip_text: str
    tdn_url: str


@dataclass(slots=True)
class DiagnoseResult:
    files_analyzed: int = 0
    findings_total: int = 0
    by_severity: dict[str, int] = None  # type: ignore[assignment]
    by_category: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.by_severity is None:
            self.by_severity = {"critical": 0, "warning": 0, "info": 0}
        if self.by_category is None:
            self.by_category = {}


# =============================================================================
# Helpers
# =============================================================================


def _compile_flags(case_insensitive: int, multiline: int) -> int:
    flags = 0
    if case_insensitive:
        flags |= re.IGNORECASE
    if multiline:
        flags |= re.MULTILINE
    return flags


_PLACEHOLDER_RE = re.compile(r"\{(\d+)\}")


def _format_message(template: str, m: re.Match[str]) -> str:
    """Substitui placeholders ``{0}/{1}/{2}/...`` pelos capture groups.

    Usa ``re.sub`` em passada única (review #6): se o capture do grupo N contém
    literalmente ``{K}`` em texto, o substitute sequencial corromperia. Com um
    callback de regex, cada ``{N}`` é resolvido pelo valor original do grupo N
    SEM passar pela substituição da próxima iteração.
    """
    def _sub(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if idx == 0:
            return m.group(0)
        try:
            grp = m.group(idx)
        except IndexError:
            return ""
        return (grp or "").strip()

    return _PLACEHOLDER_RE.sub(_sub, template)[:200]


def _load_rules(
    conn: sqlite3.Connection, severity_filter: set[str] | None = None,
) -> list[_CompiledRule]:
    """Carrega + compila regras ativas, ordenadas por priority.

    Se ``severity_filter`` for fornecido, a SQL já restringe ao subconjunto
    desejado — evita que uma rule de severidade não-pedida case primeiro
    no loop reverso e curto-circuite uma rule de prioridade mais baixa que
    casaria com a severidade certa (review do Joni #1).
    """
    sql = (
        "SELECT rule_id, category, severidade, pattern, message_template, "
        "       case_insensitive, multiline, priority "
        "FROM log_rules "
        "WHERE status = 'active'"
    )
    params: list[str] = []
    if severity_filter:
        placeholders = ", ".join("?" * len(severity_filter))
        sql += f" AND severidade IN ({placeholders})"
        params.extend(sorted(severity_filter))
    sql += " ORDER BY priority"

    cur = conn.execute(sql, params)
    compiled: list[_CompiledRule] = []
    for row in cur.fetchall():
        rule_id, category, severidade, pattern, template, ci, ml, prio = row
        try:
            pat = re.compile(pattern, _compile_flags(ci, ml))
        except re.error as exc:
            # Regex inválida no catálogo é bug de catálogo, não do log auditado.
            # Pula a rule (skip não falha o batch); avisa em stderr pra não
            # poluir stdout quando o usuário usa --format json (review #2).
            import sys
            print(
                f"WARN: regex inválida em rule {rule_id}: {exc}", file=sys.stderr,
            )  # noqa: T201
            continue
        compiled.append(_CompiledRule(
            rule_id=rule_id,
            category=category,
            severidade=severidade,
            pattern=pat,
            message_template=template,
            priority=int(prio),
        ))
    return compiled


def _load_tips(conn: sqlite3.Connection) -> list[_CompiledTip]:
    """Carrega + compila tips."""
    cur = conn.execute(
        "SELECT tip_id, category, pattern, tip_text, tdn_url, case_insensitive "
        "FROM log_tips ORDER BY priority"
    )
    compiled: list[_CompiledTip] = []
    for row in cur.fetchall():
        tip_id, cat, pat_str, text, url, ci = row
        try:
            pat = re.compile(pat_str, re.IGNORECASE if ci else 0)
        except re.error:
            continue
        compiled.append(_CompiledTip(
            tip_id=tip_id, category=cat, pattern=pat,
            tip_text=text, tdn_url=url or "",
        ))
    return compiled


def _load_category_fallbacks(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """Mapa category → (fallback_tip, tdn_url)."""
    cur = conn.execute("SELECT category_id, fallback_tip, tdn_url FROM log_categories")
    return {row[0]: (row[1] or "", row[2] or "") for row in cur.fetchall()}


def _is_noise(line: str) -> bool:
    return any(p.search(line) for p in RE_NOISE_PATTERNS)


def _parse_since(since: str) -> timedelta | None:
    """Converte '24h'/'7d'/'30m'/'15s' em timedelta."""
    m = re.match(r"^(\d+)([smhd])$", since.lower().strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(seconds=n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit])


def _find_tip(
    tips: list[_CompiledTip],
    fallbacks: dict[str, tuple[str, str]],
    category: str,
    text: str,
) -> tuple[str, str]:
    """Acha a tip mais específica pra (category, text). Cai pra fallback se
    nenhum pattern bate."""
    for tip in tips:
        if tip.category != category:
            continue
        if tip.pattern.search(text):
            return tip.tip_text, tip.tdn_url
    return fallbacks.get(category, ("", ""))


# =============================================================================
# Engine principal
# =============================================================================


# Regex pra capturar username/computer quando aparecem (enrich)
_RE_THREAD_FINISHED = re.compile(
    r"Thread finished\s*\((\w+),\s*([\w-]+)\)", re.MULTILINE
)
_RE_ERROR_ENDING_THREAD = re.compile(
    r"Error ending thread\s*\((\w+),\s*([\w-]+)\)", re.MULTILINE
)
_RE_ORA_CODE = re.compile(r"(ORA-\d+)", re.IGNORECASE)


def diagnose_one_file(
    conn: sqlite3.Connection,
    file_id: int,
    since: str | None = None,
    severity_filter: list[str] | None = None,
    max_findings: int = 1000,
) -> int:
    """Stage 2: re-aplica log_rules em log_events do file_id.

    Apaga findings antigos (rebuild atômico) e re-insere. Retorna count
    de findings criados.
    """
    sev_set = set(severity_filter) if severity_filter else None
    rules = _load_rules(conn, severity_filter=sev_set)
    if not rules:
        return 0
    tips = _load_tips(conn)
    fallbacks = _load_category_fallbacks(conn)

    # Limpa findings antigos
    conn.execute("DELETE FROM log_findings WHERE file_id = ?", (file_id,))

    # Calcula cutoff de --since usando o ÚLTIMO timestamp do log (idem env_manager)
    cutoff: datetime | None = None
    if since:
        delta = _parse_since(since)
        if delta:
            cur = conn.execute("SELECT last_ts FROM log_files WHERE id = ?", (file_id,))
            row = cur.fetchone()
            if row and row[0]:
                try:
                    last_ts = datetime.fromisoformat(row[0])
                    cutoff = last_ts - delta
                except ValueError:
                    cutoff = None

    # Carrega events em ordem reversa (mais recentes primeiro)
    cur = conn.execute(
        """
        SELECT id, line_number, timestamp, thread_id, header_line, body
        FROM log_events
        WHERE file_id = ?
        ORDER BY id DESC
        """,
        (file_id,),
    )

    findings_batch: list[tuple] = []
    for ev_row in cur:
        ev_id, line_num, ts_iso, thread_id, header, body = ev_row

        # Janela --since
        if cutoff is not None and ts_iso:
            try:
                ev_ts = datetime.fromisoformat(ts_iso)
                # Normaliza tz pra comparação se houver mistura
                if ev_ts.tzinfo is None and cutoff.tzinfo is not None:
                    ev_ts = ev_ts.replace(tzinfo=cutoff.tzinfo)
                elif ev_ts.tzinfo is not None and cutoff.tzinfo is None:
                    ev_ts = ev_ts.replace(tzinfo=None)
                if ev_ts < cutoff:
                    continue
            except ValueError:
                pass

        if _is_noise(header):
            continue

        full_text = header + ("\n" + body if body else "")

        # Aplica rules na ordem de priority. Quando ``sev_set`` está setado,
        # ``_load_rules`` já restringiu a query — não precisamos re-checar aqui.
        for rule in rules:
            m = rule.pattern.search(full_text)
            if not m:
                continue

            message = _format_message(rule.message_template, m)
            snippet = (header[:500] + ("\n" + body[:500] if body else ""))[:1000]
            tip_text, tdn_url = _find_tip(tips, fallbacks, rule.category, full_text)

            # Enrich: username/computer + ORA code
            username = computer = ""
            tf = _RE_THREAD_FINISHED.search(full_text)
            if tf:
                username, computer = tf.group(1), tf.group(2)
            else:
                eet = _RE_ERROR_ENDING_THREAD.search(full_text)
                if eet:
                    username, computer = eet.group(1), eet.group(2)

            ora_code = ""
            ora = _RE_ORA_CODE.search(full_text)
            if ora:
                ora_code = ora.group(1)

            findings_batch.append((
                file_id, ev_id, line_num, ts_iso or "", thread_id or "",
                rule.severidade, rule.category, rule.rule_id,
                message, snippet, tip_text, tdn_url,
                username, computer, ora_code, "active",
            ))
            break  # short-circuit: 1 finding por evento

        if len(findings_batch) >= max_findings:
            break

    if findings_batch:
        conn.executemany(
            """
            INSERT INTO log_findings (
                file_id, event_id, line_number, timestamp, thread_id,
                severity, category, rule_id, message, snippet,
                correction_tip, tdn_url, username, computer_name, ora_code, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            findings_batch,
        )

    return len(findings_batch)


def diagnose_files(
    conn: sqlite3.Connection,
    file_ids: Sequence[int],
    since: str | None = None,
    severity_filter: list[str] | None = None,
    max_findings: int = 1000,
) -> DiagnoseResult:
    """Re-diagnose de todos os ``file_ids`` retornando sumário consolidado."""
    result = DiagnoseResult()
    for fid in file_ids:
        count = diagnose_one_file(
            conn, fid, since=since, severity_filter=severity_filter,
            max_findings=max_findings,
        )
        result.files_analyzed += 1
        result.findings_total += count

    if file_ids:
        cur = conn.execute(
            """
            SELECT severity, COUNT(*) FROM log_findings
            WHERE file_id IN ({}) AND status = 'active'
            GROUP BY severity
            """.format(",".join("?" * len(file_ids))),
            list(file_ids),
        )
        for sev, cnt in cur.fetchall():
            if sev in result.by_severity:
                result.by_severity[sev] = int(cnt)

        cur = conn.execute(
            """
            SELECT category, COUNT(*) FROM log_findings
            WHERE file_id IN ({}) AND status = 'active'
            GROUP BY category
            """.format(",".join("?" * len(file_ids))),
            list(file_ids),
        )
        for cat, cnt in cur.fetchall():
            result.by_category[cat] = int(cnt)

    conn.commit()
    return result


__all__ = ["DiagnoseResult", "diagnose_files", "diagnose_one_file"]
