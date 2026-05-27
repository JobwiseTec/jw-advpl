"""Ingest pipeline pra logs Protheus — parse + grava no índice.

Diferente do ``ingest.py`` (fontes ADVPL), aqui o volume típico é baixo (1-10
arquivos por análise) mas o tamanho de cada um pode ser grande (logs de produção
chegam fácil em 100 MB).

Estratégia:

1. **Discovery** — auto-glob (``*console*.log``, ``*error*.log``, …) ou paths
   explícitos.
2. **Hash + mtime cache** — se ``sha256(arquivo) + mtime`` baterem com
   ``log_files``, pula re-ingest.
3. **Upsert atômico** — DELETE em ``log_events``/``log_findings`` por
   ``file_id`` (CASCADE), depois INSERT massivo dos novos events.
4. **Retorna** ``IngestResult`` com ``file_ids`` pra o diagnose engine
   processar.

OBS: ``log_findings`` é limpo aqui mas só repopulado em ``log_diagnose.py``
(separa concern — ingest = dados crus; diagnose = derivado).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

from plugadvpl.parsing.log import (
    ParsedLog,
    is_protheus_log_filename,
    parse_log_file,
)

# Safety caps por evento na hora de gravar (proteção contra log corrompido com
# linha gigante, não como truncamento esperado). 32KB cobre THREAD ERROR + call
# stack com 50-100 frames + dump de variáveis sem perder info útil (review #3).
_HEADER_MAX_CHARS = 2000
_BODY_MAX_CHARS = 32_000


@dataclass(slots=True)
class LogIngestResult:
    """Sumário de uma chamada de ingest de logs."""

    ingested: int = 0
    skipped: int = 0
    errors: list[tuple[Path, str]] = field(default_factory=list)
    # ``warnings``: avisos não-fatais (log truncado em ``max_lines``, etc.).
    # Separado de ``errors`` porque o arquivo foi ingerido com sucesso parcial
    # e os events disponíveis ficam consultáveis (review #4).
    warnings: list[tuple[Path, str]] = field(default_factory=list)
    file_ids: list[int] = field(default_factory=list)


# Globs default pra discovery (auto-discover quando o usuário não passa paths).
DEFAULT_LOG_GLOBS: tuple[str, ...] = (
    "*console*.log",
    "*error*.log",
    "*profile*.log",
    "*compila*.log",
    "*appserver*.log",
)


def discover_log_paths(root: Path, globs: Iterable[str] = DEFAULT_LOG_GLOBS) -> list[Path]:
    """Encontra logs Protheus em ``root`` (recursivo)."""
    found: set[Path] = set()
    for pattern in globs:
        for p in root.rglob(pattern):
            if p.is_file() and is_protheus_log_filename(p.name):
                found.add(p.resolve())
    return sorted(found)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ts_iso(value: object) -> str:
    return value.isoformat() if value is not None else ""  # type: ignore[attr-defined]


def _delete_dependents(conn: sqlite3.Connection, file_id: int) -> None:
    """Limpa events + findings via CASCADE."""
    conn.execute("DELETE FROM log_events WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM log_findings WHERE file_id = ?", (file_id,))


def _upsert_file_row(
    conn: sqlite3.Connection,
    caminho: str,
    arquivo: str,
    parsed: ParsedLog,
    hash_: str,
    size_bytes: int,
    mtime_ns: int,
) -> int:
    """Insere ou atualiza ``log_files`` retornando o id."""
    cur = conn.execute(
        "SELECT id FROM log_files WHERE caminho = ?",
        (caminho,),
    )
    row = cur.fetchone()

    md = parsed.metadata
    metrics = parsed.metrics
    extra_json = json.dumps(md.extra, ensure_ascii=False) if md.extra else "{}"

    values = (
        caminho,
        arquivo,
        parsed.tipo,
        hash_,
        size_bytes,
        mtime_ns,
        parsed.encoding,
        len(parsed.events),
        _ts_iso(parsed.first_ts),
        _ts_iso(parsed.last_ts),
        md.environment,
        md.appserver,
        md.build,
        md.rpo_version,
        extra_json,
        metrics.memory_total_mb,
        metrics.memory_used_mb,
        metrics.memory_free_mb,
        metrics.start_time_s,
    )

    if row is None:
        cur = conn.execute(
            """
            INSERT INTO log_files (
                caminho, arquivo, tipo,
                hash, size_bytes, mtime_ns, encoding,
                total_events, first_ts, last_ts,
                environment, appserver, build, rpo_version,
                metadata_json,
                memory_total_mb, memory_used_mb, memory_free_mb, start_time_s,
                indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            values,
        )
        return int(cur.lastrowid or 0)

    file_id = int(row[0])
    conn.execute(
        """
        UPDATE log_files SET
            arquivo = ?, tipo = ?, hash = ?, size_bytes = ?, mtime_ns = ?, encoding = ?,
            total_events = ?, first_ts = ?, last_ts = ?,
            environment = ?, appserver = ?, build = ?, rpo_version = ?,
            metadata_json = ?,
            memory_total_mb = ?, memory_used_mb = ?, memory_free_mb = ?, start_time_s = ?,
            indexed_at = datetime('now')
        WHERE id = ?
        """,
        (*values[1:], file_id),
    )
    return file_id


def _insert_events(conn: sqlite3.Connection, file_id: int, parsed: ParsedLog) -> None:
    """Grava log_events em batch."""
    if not parsed.events:
        return
    rows = [
        (
            file_id,
            ev.line_number,
            _ts_iso(ev.timestamp),
            ev.thread_id or "",
            ev.header_line[:_HEADER_MAX_CHARS],
            ev.body[:_BODY_MAX_CHARS],
        )
        for ev in parsed.events
    ]
    conn.executemany(
        """
        INSERT INTO log_events (file_id, line_number, timestamp, thread_id, header_line, body)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def ingest_one_log(
    conn: sqlite3.Connection, path: Path, force: bool = False
) -> tuple[int | None, str, str | None]:
    """Ingere 1 log. Retorna ``(file_id, status, warning)``.

    - ``status``: ``'ingested' | 'skipped' | 'error:<msg>'``
    - ``warning``: ``None`` ou descrição de aviso não-fatal (ex.: log truncado
      em ``max_lines`` — review #4).
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"error:read_failed:{exc}", None

    h = _hash_bytes(raw)
    mtime_ns = path.stat().st_mtime_ns
    size_bytes = len(raw)

    if not force:
        cur = conn.execute(
            "SELECT id FROM log_files WHERE caminho = ? AND hash = ? AND mtime_ns = ?",
            (str(path), h, mtime_ns),
        )
        row = cur.fetchone()
        if row is not None:
            return int(row[0]), "skipped", None

    parsed = parse_log_file(raw, filename=path.name)

    file_id = _upsert_file_row(
        conn,
        caminho=str(path),
        arquivo=path.name,
        parsed=parsed,
        hash_=h,
        size_bytes=size_bytes,
        mtime_ns=mtime_ns,
    )
    _delete_dependents(conn, file_id)
    _insert_events(conn, file_id, parsed)

    warning = None
    if parsed.truncated_at_line is not None:
        warning = (
            f"truncated_at_line={parsed.truncated_at_line} "
            f"(log excedeu cap de tokenização — eventos após essa linha não foram processados)"
        )

    return file_id, "ingested", warning


def ingest_log_paths(
    conn: sqlite3.Connection,
    paths: Iterable[Path],
    force: bool = False,
) -> LogIngestResult:
    """Ingere uma lista de logs. Commit explícito ao final."""
    result = LogIngestResult()
    for p in paths:
        if not p.exists():
            result.errors.append((p, "not_found"))
            continue
        if not p.is_file():
            result.errors.append((p, "not_a_file"))
            continue
        try:
            file_id, status, warning = ingest_one_log(conn, p, force=force)
        except sqlite3.DatabaseError as exc:
            result.errors.append((p, f"db_error:{exc}"))
            continue
        except Exception as exc:
            result.errors.append((p, f"unexpected:{type(exc).__name__}:{exc}"))
            continue

        if status == "ingested":
            result.ingested += 1
            if file_id is not None:
                result.file_ids.append(file_id)
            if warning:
                result.warnings.append((p, warning))
        elif status == "skipped":
            result.skipped += 1
            if file_id is not None:
                result.file_ids.append(file_id)
        else:
            result.errors.append((p, status))

    conn.commit()
    return result


__all__ = [
    "DEFAULT_LOG_GLOBS",
    "LogIngestResult",
    "discover_log_paths",
    "ingest_log_paths",
    "ingest_one_log",
]
