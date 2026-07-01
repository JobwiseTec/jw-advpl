"""Leitor de .dtc (FairCom c-tree ISAM).

Caminho principal: parser DODA direto (fixed-length, sem servidor). Fallback:
registro via ctsqlimp + driver nativo, quando o parser não se aplica (arquivo
variável, sem DODA, ou que precise do índice c-tree).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from plugadvpl.dtc import faircom, parser


@dataclass
class Column:
    name: str
    type: str
    size: int
    nullable: bool


@dataclass
class DtcInfo:
    file: Path
    table: str
    columns: list[Column]
    row_count: int
    sample: list[dict]


# --- caminho c-tree (fallback) -------------------------------------------


@contextmanager
def _open_dtc(arquivo: Path) -> Iterator[tuple[object, str]]:
    """Registra o .dtc como tabela SQL (ctsqlimp), abre conexão e faz cleanup."""
    target, table = faircom.register_isam(arquivo)
    conn = faircom.connect()
    try:
        yield conn, table
    finally:
        try:
            conn.close()
        finally:
            faircom.unregister_isam(target, table)


def _columns_from_description(description) -> list[Column]:
    """Converte o cursor.description (DB-API 7-tuplas) em Column."""
    cols: list[Column] = []
    for d in description or []:
        type_code = d[1]
        type_name = getattr(type_code, "__name__", str(type_code))
        size = d[4] if len(d) > 4 and d[4] is not None else (d[3] or 0)
        nullable = bool(d[6]) if len(d) > 6 and d[6] is not None else True
        cols.append(Column(name=d[0], type=type_name, size=int(size or 0), nullable=nullable))
    return cols


def _columns_from_layout(layout: faircom.Layout) -> list[Column]:
    return [Column(name=f.name, type=f.ctype, size=f.length, nullable=True) for f in layout.fields]


# --- API pública ---------------------------------------------------------


def read_all(arquivo: Path, keep_deleted: bool = False) -> tuple[list[str], list[tuple]]:
    """Lê todos os registros de um .dtc. Retorna (columns, rows).

    Usa o parser DODA direto quando o arquivo tem assinatura Protheus
    (fixed-length + flag de delete no offset 0); senão cai pro caminho c-tree.
    """
    layout = faircom.extract_layout(arquivo)
    if layout is not None and layout.is_protheus:
        return parser.read_fixed(arquivo.read_bytes(), layout, keep_deleted=keep_deleted)

    with _open_dtc(arquivo) as (conn, table):
        cur = conn.cursor()
        if keep_deleted:
            cur.execute(f"SELECT * FROM {table}")
        else:
            cur.execute(f"SELECT * FROM {table} WHERE D_E_L_E_T_ <> '*' OR D_E_L_E_T_ IS NULL")
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return columns, rows


def read_info(arquivo: Path, sample: int, console: Console) -> DtcInfo:
    if not arquivo.is_file():
        console.print(f"[red]Arquivo não encontrado:[/] {arquivo}")
        raise SystemExit(1)

    layout = faircom.extract_layout(arquivo)
    if layout is not None and layout.is_protheus:
        cols = _columns_from_layout(layout)
        _, rows_all = parser.read_fixed(arquivo.read_bytes(), layout, keep_deleted=False)
        row_count = len(rows_all)
        names = [c.name for c in cols]
        rows = [dict(zip(names, r, strict=False)) for r in rows_all[:sample]]
        table = arquivo.stem
    else:
        with _open_dtc(arquivo) as (conn, tbl):
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            row_count = int(cur.fetchone()[0])
            cur.execute(f"SELECT * FROM {tbl}")
            cols = _columns_from_description(cur.description)
            names = [c.name for c in cols]
            rows = [dict(zip(names, row, strict=False)) for row in cur.fetchmany(sample)]
            table = tbl

    _render_info(arquivo, table, cols, row_count, rows, console)
    return DtcInfo(file=arquivo, table=table, columns=cols, row_count=row_count, sample=rows)


def _render_info(
    arquivo: Path,
    table: str,
    cols: list[Column],
    row_count: int,
    rows: list[dict],
    console: Console,
) -> None:
    console.print(f"\n[bold]Arquivo:[/] {arquivo}")
    console.print(f"[bold]Tabela:[/] {table}")
    console.print(f"[bold]Registros:[/] {row_count}\n")

    schema = Table(title="Schema", show_lines=False)
    schema.add_column("Campo", style="bold cyan")
    schema.add_column("Tipo")
    schema.add_column("Tamanho", justify="right")
    schema.add_column("Null", justify="center")
    for c in cols:
        schema.add_row(c.name, c.type, str(c.size), "Y" if c.nullable else "N")
    console.print(schema)

    if rows:
        sample_tbl = Table(title=f"Amostra ({len(rows)} registros)")
        for k in rows[0]:
            sample_tbl.add_column(k)
        for r in rows:
            sample_tbl.add_row(*(str(v) for v in r.values()))
        console.print(sample_tbl)
