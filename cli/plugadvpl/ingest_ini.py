"""Ingest pipeline pra INIs Protheus — parse + grava no índice.

Diferente do ``ingest.py`` (fontes ADVPL), aqui o volume é baixo (5-20 INIs num
cliente típico) e a operação não exige paralelismo. Estratégia:

1. **Discovery** — auto-glob (``appserver*.ini``, ``dbaccess*.ini``, …) ou paths
   explícitos passados pelo usuário.
2. **Hash + mtime cache** — se o sha256 do arquivo bate com ``ini_files.hash`` E
   mtime_ns idem, pula re-ingest. Cache invalida em qualquer mudança.
3. **Upsert atômico** — DELETE em ``ini_sections``, ``ini_keys``, ``ini_audit_findings``
   por ``file_id`` (CASCADE limpa filhos), depois INSERT massivo.
4. **Retorna** o ``IngestResult`` com ``file_ids`` ingeridos pra o audit engine
   processar.

Exemplo:

>>> from pathlib import Path
>>> import sqlite3
>>> from plugadvpl.ingest_ini import ingest_ini_paths
>>> conn = sqlite3.connect("/path/to/index.db")
>>> result = ingest_ini_paths(conn, [Path("/srv/protheus/appserver.ini")])
>>> result.ingested
1
>>> result.skipped  # já estava em cache
0
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

from plugadvpl.parsing.ini import (
    ParsedIni,
    is_protheus_ini_filename,
    parse_ini_file,
)


@dataclass(slots=True)
class IngestResult:
    """Resultado consolidado de uma chamada de ingest."""

    ingested: int = 0
    skipped: int = 0  # cache hit (hash + mtime bateram)
    errors: list[tuple[Path, str]] = field(default_factory=list)
    file_ids: list[int] = field(default_factory=list)


# Globs default pra discovery (usadas quando o usuário não passa paths
# explícitos). Usa wildcards de ambos os lados pra capturar prefixos comuns
# de ambiente (``dev_appserver.ini``, ``prd_dbaccess.ini``, ``appserver_qa.ini``).
DEFAULT_GLOBS: tuple[str, ...] = (
    "*appserver*.ini",
    "*dbaccess*.ini",
    "*smartclient*.ini",
    "*tss*.ini",
    "*broker*.ini",
)


def discover_ini_paths(root: Path, globs: Iterable[str] = DEFAULT_GLOBS) -> list[Path]:
    """Encontra INIs Protheus em ``root`` (recursivo) usando globs default.

    Filtra também por ``is_protheus_ini_filename`` no fim pra evitar capturar
    INIs do Windows (``desktop.ini``) ou de outros sistemas.
    """
    found: set[Path] = set()
    for pattern in globs:
        for p in root.rglob(pattern):
            if p.is_file() and is_protheus_ini_filename(p.name):
                found.add(p.resolve())
    return sorted(found)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _delete_existing(conn: sqlite3.Connection, file_id: int) -> None:
    """Limpa filhos via CASCADE da FK. Mantém row em ini_files (upsert depois)."""
    # ini_sections / ini_keys / ini_audit_findings têm FK ON DELETE CASCADE
    # apontando pra ini_files; basta apagar essas 3 tabelas por file_id.
    conn.execute("DELETE FROM ini_sections WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM ini_keys WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM ini_audit_findings WHERE file_id = ?", (file_id,))


def _upsert_file_row(
    conn: sqlite3.Connection,
    caminho: str,
    arquivo: str,
    tipo: str,
    role: str,
    encoding: str,
    hash_: str,
    size_bytes: int,
    mtime_ns: int,
) -> int:
    """Insere ou atualiza ini_files retornando o id."""
    cur = conn.execute(
        "SELECT id, hash, mtime_ns FROM ini_files WHERE caminho = ?",
        (caminho,),
    )
    row = cur.fetchone()
    if row is None:
        cur = conn.execute(
            """
            INSERT INTO ini_files (
                caminho, arquivo, tipo, role, encoding,
                hash, size_bytes, mtime_ns, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (caminho, arquivo, tipo, role, encoding, hash_, size_bytes, mtime_ns),
        )
        return int(cur.lastrowid or 0)

    file_id = int(row[0])
    conn.execute(
        """
        UPDATE ini_files
        SET arquivo = ?, tipo = ?, role = ?, encoding = ?,
            hash = ?, size_bytes = ?, mtime_ns = ?, indexed_at = datetime('now')
        WHERE id = ?
        """,
        (arquivo, tipo, role, encoding, hash_, size_bytes, mtime_ns, file_id),
    )
    return file_id


def _insert_sections_and_keys(conn: sqlite3.Connection, file_id: int, parsed: ParsedIni) -> None:
    """Grava sections + keys em batch. Retorna mapa name_norm -> section_id
    pra resolver FK das keys."""
    sec_id_by_norm: dict[str, int] = {}
    for sec in parsed.sections:
        cur = conn.execute(
            """
            INSERT INTO ini_sections (
                file_id, name_raw, name_norm, commented,
                linha_inicio, linha_fim, comment_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                sec.name_raw,
                sec.name_norm,
                1 if sec.commented else 0,
                sec.linha_inicio,
                sec.linha_fim,
                sec.comment_text,
            ),
        )
        sec_id_by_norm[sec.name_norm] = int(cur.lastrowid or 0)

    if not parsed.keys:
        return

    key_rows = [
        (
            file_id,
            sec_id_by_norm.get(k.section_name.lower(), 0),
            k.key_name,
            k.key_name.lower(),
            k.value,
            k.linha,
            k.comment_inline,
            k.comment_above,
        )
        for k in parsed.keys
    ]
    conn.executemany(
        """
        INSERT INTO ini_keys (
            file_id, section_id, key_name, key_norm,
            value, linha, comment_inline, comment_above
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        key_rows,
    )


def ingest_one_ini(
    conn: sqlite3.Connection, path: Path, force: bool = False
) -> tuple[int | None, str]:
    """Ingere 1 INI. Retorna ``(file_id, status)`` onde status é
    ``'ingested' | 'skipped' | 'error:<msg>'``.

    Cache: pula se o sha256 + mtime_ns batem com a row existente em ``ini_files``.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"error:read_failed:{exc}"

    h = _hash_bytes(raw)
    mtime_ns = path.stat().st_mtime_ns
    size_bytes = len(raw)

    # Cache lookup
    if not force:
        cur = conn.execute(
            "SELECT id FROM ini_files WHERE caminho = ? AND hash = ? AND mtime_ns = ?",
            (str(path), h, mtime_ns),
        )
        row = cur.fetchone()
        if row is not None:
            return int(row[0]), "skipped"

    # Parse
    parsed = parse_ini_file(raw, filename=path.name)

    # Upsert file row
    file_id = _upsert_file_row(
        conn,
        caminho=str(path),
        arquivo=path.name,
        tipo=parsed.tipo,
        role=parsed.role,
        encoding=parsed.encoding_info.detected,
        hash_=h,
        size_bytes=size_bytes,
        mtime_ns=mtime_ns,
    )

    # Limpa filhos e re-insere
    _delete_existing(conn, file_id)
    _insert_sections_and_keys(conn, file_id, parsed)
    return file_id, "ingested"


def ingest_ini_paths(
    conn: sqlite3.Connection,
    paths: Iterable[Path],
    force: bool = False,
) -> IngestResult:
    """Ingere uma lista de paths. Commit explícito ao final.

    ``force=True`` desliga o cache de hash/mtime e re-grava sempre.
    """
    result = IngestResult()
    for p in paths:
        if not p.exists():
            result.errors.append((p, "not_found"))
            continue
        if not p.is_file():
            result.errors.append((p, "not_a_file"))
            continue
        try:
            file_id, status = ingest_one_ini(conn, p, force=force)
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
        elif status == "skipped":
            result.skipped += 1
            if file_id is not None:
                result.file_ids.append(file_id)
        else:
            result.errors.append((p, status))

    conn.commit()
    return result


__all__ = [
    "DEFAULT_GLOBS",
    "IngestResult",
    "discover_ini_paths",
    "ingest_ini_paths",
    "ingest_one_ini",
]
