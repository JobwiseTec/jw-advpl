"""Export de .dtc para CSV, JSON ou XLSX."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from rich.console import Console

from plugadvpl.dtc.reader import read_all


class ExportFormat(StrEnum):
    csv = "csv"
    json = "json"
    xlsx = "xlsx"


def _import_pandas():
    """Importa pandas (extra opcional 'dtc'). Mensagem amigavel se ausente."""
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "dtc export requer o extra 'dtc' (pandas + openpyxl), fora do install base.\n"
            "  uvx 'plugadvpl[dtc]' dtc export ...\n"
            "  (ou: pip install 'plugadvpl[dtc]')"
        ) from exc
    return pd


def _to_dataframe(columns: list[str], rows: list[tuple]):
    pd = _import_pandas()

    df = pd.DataFrame.from_records(rows, columns=columns)
    if df.empty:
        return df
    return df.map(_decode_cell)


def _decode_cell(v):
    if isinstance(v, bytes):
        try:
            s = v.decode("cp1252")
        except UnicodeDecodeError:
            s = v.decode("latin1", errors="replace")
        return s.rstrip()
    if isinstance(v, str):
        return v.rstrip()
    return v


def export_file(
    arquivo: Path,
    fmt: ExportFormat,
    output: Path | None,
    keep_deleted: bool = False,
    console: Console | None = None,
) -> Path:
    console = console or Console()

    if not arquivo.is_file():
        console.print(f"[red]Arquivo não encontrado:[/] {arquivo}")
        raise SystemExit(1)

    destino = output or arquivo.with_suffix(f".{fmt.value}")
    columns, rows = read_all(arquivo, keep_deleted=keep_deleted)
    df = _to_dataframe(columns, rows)

    if fmt is ExportFormat.csv:
        df.to_csv(destino, index=False, encoding="utf-8-sig")
    elif fmt is ExportFormat.json:
        df.to_json(destino, orient="records", force_ascii=False, indent=2, date_format="iso")
    elif fmt is ExportFormat.xlsx:
        df.to_excel(destino, index=False)
    else:
        raise ValueError(f"Formato não suportado: {fmt}")

    console.print(f"[green]✓[/] {arquivo.name} → {destino} ({len(df)} registros)")
    return destino
