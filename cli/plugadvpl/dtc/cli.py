"""CLI entrypoint do dtcat."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from plugadvpl.dtc import __version__
from plugadvpl.dtc.doctor import run_doctor
from plugadvpl.dtc.exporter import ExportFormat, export_file
from plugadvpl.dtc.reader import read_info
from plugadvpl.dtc.server import server_start, server_status, server_stop

# Força saída UTF-8: consoles Windows legados usam cp1252/cp850 e quebrariam
# (UnicodeEncodeError) nos glyphs do rich — ✓, →, ≥, ●, — usados na UI.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        with contextlib.suppress(OSError, ValueError):  # stream sem reconfigure
            _reconfigure(encoding="utf-8")

app = typer.Typer(
    name="dtcat",
    help="Leitor/exporter de .dtc (FairCom c-tree ISAM) standalone.",
    no_args_is_help=True,
    add_completion=False,
)
server_app = typer.Typer(help="Gerencia o c-tree Server local.", no_args_is_help=True)
app.add_typer(server_app, name="server")

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"dtc engine (dtcat) {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    """dtcat — leitor/exporter de .dtc standalone."""


@app.command()
def doctor() -> None:
    """Valida pré-requisitos: FairCom, driver nativo, ctsqlimp, servidor."""
    ok = run_doctor(console)
    raise typer.Exit(code=0 if ok else 1)


@app.command()
def info(
    arquivo: Annotated[Path, typer.Argument(help="Caminho do .dtc")],
    sample: Annotated[int, typer.Option(help="Quantos registros amostrar")] = 5,
) -> None:
    """Mostra schema + count + amostra de um .dtc."""
    read_info(arquivo, sample=sample, console=console)


@app.command()
def export(
    arquivo: Annotated[Path, typer.Argument(help="Caminho do .dtc")],
    fmt: Annotated[
        ExportFormat, typer.Option("--format", "-f", help="csv | json | xlsx")
    ] = ExportFormat.csv,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Arquivo destino (padrão: mesmo nome + extensão)"),
    ] = None,
    keep_deleted: Annotated[
        bool, typer.Option("--keep-deleted", help="Incluir registros marcados como D_E_L_E_T_")
    ] = False,
) -> None:
    """Exporta um .dtc para CSV, JSON ou XLSX."""
    export_file(arquivo, fmt=fmt, output=output, keep_deleted=keep_deleted, console=console)


@app.command()
def batch(
    pasta: Annotated[Path, typer.Argument(help="Pasta com .dtc")],
    fmt: Annotated[ExportFormat, typer.Option("--format", "-f")] = ExportFormat.csv,
    output: Annotated[Path, typer.Option("--output", "-o", help="Pasta destino")] = Path("./out"),
) -> None:
    """Exporta todos os .dtc de uma pasta."""
    if not pasta.is_dir():
        console.print(f"[red]Pasta não encontrada:[/] {pasta}")
        raise typer.Exit(code=1)
    output.mkdir(parents=True, exist_ok=True)
    arquivos = sorted(set(pasta.glob("*.dtc")) | set(pasta.glob("*.DTC")))
    if not arquivos:
        console.print(f"[yellow]Nenhum .dtc encontrado em {pasta}[/]")
        raise typer.Exit(code=1)
    console.print(f"Processando [bold]{len(arquivos)}[/] arquivo(s)...")
    for arq in arquivos:
        destino = output / f"{arq.stem}.{fmt.value}"
        export_file(arq, fmt=fmt, output=destino, console=console)
    console.print(f"[green]Concluído:[/] {output}")


@server_app.command("start")
def server_start_cmd() -> None:
    """Inicia o c-tree Server local em background."""
    server_start(console)


@server_app.command("stop")
def server_stop_cmd() -> None:
    """Para o c-tree Server local."""
    server_stop(console)


@server_app.command("status")
def server_status_cmd() -> None:
    """Mostra o status do c-tree Server local."""
    server_status(console)


if __name__ == "__main__":
    app()
