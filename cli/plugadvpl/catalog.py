"""Importa dump TSV/CSV de tabela-catálogo (Z*/X*) pro índice e faz cross-query (#75).

Fecha o gap do *conteúdo* das tabelas-catálogo: o ``tables --catalog`` (#64) dá o
schema + X3_CBOX; aqui entram as N regras catalogadas (filter/group-by/count +
decode de cbox + cruzamento de ``*_FUNCAO`` com os fontes indexados).

Storage **row-JSON** (1 linha/registro, colunas em JSON) — schema arbitrário sem
``ALTER TABLE`` por dump; agregação em Python (dumps típicos ~250x12). O ``--filter``
é parseado por um mini-parser **seguro** (aplicado em Python, sem SQL injection).
"""

from __future__ import annotations

import collections
import csv
import datetime as _dt
import json
import operator
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from plugadvpl.parsing.parser import _decode_bytes
from plugadvpl.query import _decode_cbox

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable

_CMP = {">": operator.gt, "<": operator.lt, ">=": operator.ge, "<=": operator.le}

_DELIM_NAMES = {"tab": "\t", "csv": ",", "\t": "\t", ",": ","}
_REV_DELIM = {"\t": "tab", ",": "csv"}
_DEFAULT_LIMIT = 20


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _sniff_delimiter(header_line: str) -> str:
    """``\\t`` se o header tem tabs; senão ``,``."""
    return "\t" if header_line.count("\t") > 0 else ","


def parse_tabular(
    raw: bytes, *, encoding: str | None = None, delimiter: str | None = None
) -> tuple[list[str], list[dict[str, str]], str, str]:
    """Parseia bytes tabulares → (colunas, linhas-dict, encoding, delimiter).

    Encoding auto (cp1252/utf-8/utf-8-bom) via :func:`_decode_bytes`, override por
    ``encoding``. Delimiter sniffed (``\\t`` vs ``,``), override por ``delimiter``
    (``tab``/``csv``).
    """
    if encoding:
        text = raw.decode(encoding, errors="replace")
        enc = encoding
    else:
        text, enc = _decode_bytes(raw)
    lines = text.splitlines()
    if not lines:
        return [], [], enc, delimiter or "tab"
    delim = _DELIM_NAMES.get(delimiter or "", "") or _sniff_delimiter(lines[0])
    reader = csv.reader(lines, delimiter=delim)
    all_rows = list(reader)
    if not all_rows:
        return [], [], enc, _REV_DELIM[delim]
    columns = [c.strip() for c in all_rows[0]]
    rows: list[dict[str, str]] = []
    for raw_row in all_rows[1:]:
        if not any(cell.strip() for cell in raw_row):
            continue  # pula linha em branco
        rows.append(
            {columns[i]: (raw_row[i] if i < len(raw_row) else "") for i in range(len(columns))}
        )
    return columns, rows, enc, _REV_DELIM[delim]


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #
def _resolve_sx_table(conn: sqlite3.Connection, alias: str, source_file: str) -> str | None:
    """Tabela SX correlata: basename do arquivo (ou alias) que bate com ``campos``."""
    candidatos = {Path(source_file).stem.upper(), alias.upper()}
    for cand in candidatos:
        if len(cand) == 3:  # noqa: PLR2004 — código de tabela Protheus tem 3 chars
            row = conn.execute("SELECT 1 FROM campos WHERE tabela = ? LIMIT 1", (cand,)).fetchone()
            if row:
                return cand
    return None


def ingest_tsv(
    conn: sqlite3.Connection,
    path: Path,
    alias: str,
    *,
    encoding: str | None = None,
    delimiter: str | None = None,
) -> dict[str, Any]:
    """Importa ``path`` como catálogo ``alias`` (full-overwrite). Retorna metadados."""
    raw = path.read_bytes()
    columns, rows, enc, delim = parse_tabular(raw, encoding=encoding, delimiter=delimiter)
    existed = bool(conn.execute("SELECT 1 FROM catalog_meta WHERE alias = ?", (alias,)).fetchone())
    conn.execute("DELETE FROM catalog_data WHERE alias = ?", (alias,))
    conn.execute("DELETE FROM catalog_meta WHERE alias = ?", (alias,))
    sx_table = _resolve_sx_table(conn, alias, str(path))
    conn.executemany(
        "INSERT INTO catalog_data (alias, row_id, row_json) VALUES (?, ?, ?)",
        [(alias, i + 1, json.dumps(row, ensure_ascii=False)) for i, row in enumerate(rows)],
    )
    conn.execute(
        """
        INSERT INTO catalog_meta
            (alias, source_file, sx_table, columns_json, row_count, ingested_at, encoding, delimiter)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alias,
            str(path),
            sx_table,
            json.dumps(columns, ensure_ascii=False),
            len(rows),
            _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            enc,
            delim,
        ),
    )
    conn.commit()
    return {
        "alias": alias,
        "rows": len(rows),
        "columns": len(columns),
        "encoding": enc,
        "delimiter": delim,
        "sx_table": sx_table,
        "overwritten": existed,
    }


def catalog_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Lista os catálogos ingeridos (p/ ``status``)."""
    try:
        rows = conn.execute(
            "SELECT alias, row_count, sx_table, source_file FROM catalog_meta ORDER BY alias"
        ).fetchall()
    except Exception:
        return []
    return [
        {"alias": a, "row_count": n, "sx_table": sx or "", "source_file": sf}
        for a, n, sx, sf in rows
    ]


# --------------------------------------------------------------------------- #
# Filtro seguro
# --------------------------------------------------------------------------- #
_FILTER_TERM = re.compile(r"^\s*(\w+)\s*(>=|<=|!=|=|>|<|LIKE)\s*'?([^']*)'?\s*$", re.IGNORECASE)


def _make_pred(col: str, op: str, val: str) -> Callable[[dict[str, str]], bool]:
    def pred(row: dict[str, str]) -> bool:
        cell = row.get(col, "")
        if op == "=":
            return cell == val
        if op == "!=":
            return cell != val
        if op == "LIKE":
            return val.strip("%").lower() in cell.lower()
        # comparações de ordem: numérico se ambos numéricos, senão string
        try:
            a: float | str = float(cell)
            b: float | str = float(val)
        except ValueError:
            a, b = cell, val
        return bool(_CMP[op](a, b))

    return pred


def _parse_filter(expr: str) -> Callable[[dict[str, str]], bool]:
    """Parser SEGURO de ``COL OP 'VAL'`` unidos por ``AND``/``OR`` (aplicado em Python).

    Levanta ``ValueError`` em sintaxe inválida (à prova de injeção — nunca vai pra SQL).
    """
    expr = expr.strip()
    if re.search(r"\bOR\b", expr, re.IGNORECASE) and not re.search(r"\bAND\b", expr, re.IGNORECASE):
        parts = re.split(r"\s+OR\s+", expr, flags=re.IGNORECASE)
        combine = any
    else:
        parts = re.split(r"\s+AND\s+", expr, flags=re.IGNORECASE)
        combine = all
    preds = []
    for part in parts:
        m = _FILTER_TERM.match(part)
        if not m:
            msg = f"filtro inválido: {part!r} — use COL OP 'VAL' (OP: = != > < >= <= LIKE)"
            raise ValueError(msg)
        preds.append(_make_pred(m.group(1), m.group(2).upper(), m.group(3)))
    return lambda row: combine(p(row) for p in preds)


# --------------------------------------------------------------------------- #
# Query
# --------------------------------------------------------------------------- #
def _cbox_maps(
    conn: sqlite3.Connection, sx_table: str | None, cols: list[str]
) -> dict[str, dict[str, str]]:
    """Para cada coluna, o mapa code→label do X3_CBOX (se ``sx_table`` conhecida)."""
    if not sx_table:
        return {}
    maps: dict[str, dict[str, str]] = {}
    for col in cols:
        row = conn.execute(
            "SELECT cbox FROM campos WHERE tabela = ? AND campo = ? AND cbox != ''",
            (sx_table, col),
        ).fetchone()
        if row:
            decoded = _decode_cbox(row[0])
            maps[col] = dict(item.split("=", 1) for item in decoded.split(", ") if "=" in item)
    return maps


def _load_rows(conn: sqlite3.Connection, alias: str) -> list[dict[str, str]]:
    return [
        json.loads(r[0])
        for r in conn.execute(
            "SELECT row_json FROM catalog_data WHERE alias = ? ORDER BY row_id", (alias,)
        ).fetchall()
    ]


def catalog_query(
    conn: sqlite3.Connection,
    alias: str,
    *,
    filter_expr: str | None = None,
    group_by: str | None = None,
    count: bool = False,
    decode_cbox: bool = False,
    funcao_field: str | None = None,
    resolve_callers: bool = False,
) -> list[dict[str, Any]]:
    """Consulta o catálogo ``alias``. Modos: lista / group-by+count / resolve-callers.

    Retorna ``[]`` se o alias não existe (caller trata). ``filter_expr`` é aplicado
    antes de qualquer agregação.
    """
    meta = conn.execute("SELECT sx_table FROM catalog_meta WHERE alias = ?", (alias,)).fetchone()
    if meta is None:
        return []
    sx_table = meta[0]
    rows = _load_rows(conn, alias)
    if filter_expr:
        pred = _parse_filter(filter_expr)
        rows = [r for r in rows if pred(r)]

    if funcao_field and resolve_callers:
        return _resolve_callers(conn, rows, funcao_field)
    if group_by and count:
        return _group_count(conn, rows, group_by, sx_table, decode_cbox)
    return rows


def _group_count(
    conn: sqlite3.Connection,
    rows: list[dict[str, str]],
    group_by: str,
    sx_table: str | None,
    decode_cbox: bool,
) -> list[dict[str, Any]]:
    cols = [c.strip() for c in group_by.split(",")]
    maps = _cbox_maps(conn, sx_table, cols) if decode_cbox else {}
    counter: collections.Counter[tuple[str, ...]] = collections.Counter()
    for row in rows:
        counter[tuple(row.get(c, "") for c in cols)] += 1
    out: list[dict[str, Any]] = []
    for key, n in counter.most_common():
        d: dict[str, Any] = {}
        for i, col in enumerate(cols):
            val = key[i]
            if decode_cbox and col in maps and val in maps[col]:
                val = f"{val}={maps[col][val]}"
            d[col] = val if val else "(vazio)"
        d["count"] = n
        out.append(d)
    return out


def _normalize_funcao_expr(raw: str) -> str:
    """Nome da função de uma expressão de chamada, sem argumentos (#78).

    ``U_MODxxx("88")`` / ``U_MODxxx( 88, .T. )`` → ``U_MODxxx``; nome puro fica
    igual; literal (``.F.``/``.T.``/número/vazio) volta como veio (não resolve).
    """
    call = re.match(r"\s*([A-Za-z_]\w*)\s*\(", raw)  # nome seguido de '('
    if call:
        return call.group(1)
    bare = re.fullmatch(r"\s*([A-Za-z_]\w*)\s*", raw)  # nome puro, sem parênteses
    return bare.group(1) if bare else raw.strip()


def _resolve_callers(
    conn: sqlite3.Connection, rows: list[dict[str, str]], funcao_field: str
) -> list[dict[str, Any]]:
    """Conta no dump por **nome de função** (normalizado, sem args) + acha o fonte
    que o define. Argumentos distintos (``U_X("88")`` vs ``U_X("89")``) somam no
    mesmo nome (#78); a visão por argumento fica em ``--group-by <COL> --count``."""
    counter: collections.Counter[str] = collections.Counter()
    for row in rows:
        counter[_normalize_funcao_expr(row.get(funcao_field, ""))] += 1
    out: list[dict[str, Any]] = []
    for funcao, n in counter.most_common():
        fonte = _find_source(conn, funcao) if funcao else ""
        out.append(
            {
                funcao_field: funcao or "(vazio)",
                "fonte": fonte or "(literal/não-resolvido)",
                "count_no_dump": n,
            }
        )
    return out


def _find_source(conn: sqlite3.Connection, funcao: str) -> str:
    """Fonte que define ``funcao`` (lookup em fonte_chunks, normaliza U_)."""
    norm = funcao.upper().removeprefix("U_")
    if not re.match(r"^\w+$", norm):  # literal tipo .F. / expressão — não é função
        return ""
    row = conn.execute(
        "SELECT arquivo FROM fonte_chunks WHERE funcao_norm = ? LIMIT 1", (norm,)
    ).fetchone()
    return row[0] if row else ""
