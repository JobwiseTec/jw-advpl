"""CLI entry point — wrapper typer."""
from __future__ import annotations

import typer

from plugadvpl import __version__

app = typer.Typer(
    name="plugadvpl",
    help="Indexa fontes ADVPL/TLPP em SQLite + FTS5.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Imprime versão da CLI."""
    typer.echo(f"plugadvpl {__version__}")


def main() -> None:
    """Entry point para `plugadvpl` console_script."""
    app()


if __name__ == "__main__":
    main()
