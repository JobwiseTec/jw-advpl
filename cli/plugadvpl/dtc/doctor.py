"""Validação de pré-requisitos: FairCom DB, driver nativo, ctsqlimp, servidor."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from plugadvpl.dtc import faircom


def _check_python() -> tuple[bool, str]:
    ver = sys.version_info
    ok = ver >= (3, 11)
    return ok, f"Python {ver.major}.{ver.minor}.{ver.micro}"


def _check_native_parser() -> tuple[bool, str]:
    """O parser DODA nativo é embutido no dtcat — lê .dtc Protheus sem FairCom."""
    return True, "embutido (lê .dtc Protheus fixed-length sem FairCom)"


def _check_faircom(home: Path | None) -> tuple[bool, str]:
    if home is None:
        return (
            False,
            "FairCom DB não encontrado (defina FAIRCOM_HOME ou veja docs/setup-linux.md)",
        )
    return True, str(home)


def _check_native_lib(home: Path | None) -> tuple[bool, str]:
    if home is None:
        return False, "skipped (FairCom não encontrado)"
    lib = faircom.native_lib_path(home)
    if lib is None:
        return False, f"{faircom.native_lib_name()} não localizado dentro do FAIRCOM_HOME"
    return True, str(lib)


def _check_native_driver(home: Path | None) -> tuple[bool, str]:
    if home is None:
        return False, "skipped (FairCom não encontrado)"
    drv = faircom.native_driver_dir(home)
    if drv is None:
        return False, "driver Python nativo (pyctree) não localizado em drivers/python.sql"
    return True, str(drv)


def _check_server_binary(home: Path | None) -> tuple[bool, str]:
    if home is None:
        return False, "skipped (FairCom não encontrado)"
    binary = faircom.server_binary(home)
    if binary is None:
        return False, "binário do servidor (faircom/ctreesql) não localizado"
    return True, str(binary)


def _check_ctsqlimp(home: Path | None) -> tuple[bool, str]:
    if home is None:
        return False, "skipped (FairCom não encontrado)"
    tool = faircom.ctsqlimp_path(home)
    if tool is None:
        return False, "utilidade ctsqlimp não localizada em tools/"
    return True, str(tool)


def _check_ctinfo(home: Path | None) -> tuple[bool, str]:
    if home is None:
        return False, "skipped (FairCom não encontrado)"
    tool = faircom.ctinfo_path(home)
    if tool is None:
        return False, "utilidade ctinfo não localizada em tools/ (usada pelo parser DODA)"
    return True, str(tool)


def run_doctor(console: Console) -> bool:
    home = faircom.find_faircom_home()
    # Essenciais: bastam para ler/exportar .dtc Protheus (caminho zero-FairCom).
    essential = [
        ("Python ≥ 3.11", _check_python()),
        ("Parser DODA nativo (zero-FairCom)", _check_native_parser()),
    ]
    # Opcionais: só necessários para o fallback c-tree (arquivos sem assinatura
    # Protheus, variáveis, ou que dependam do índice). Ausência não é erro.
    optional = [
        ("FairCom DB instalado", _check_faircom(home)),
        ("Lib nativa do client SQL", _check_native_lib(home)),
        ("Driver Python nativo (pyctree)", _check_native_driver(home)),
        ("Utilidade ctinfo", _check_ctinfo(home)),
        ("Binário do servidor", _check_server_binary(home)),
        ("Utilidade ctsqlimp", _check_ctsqlimp(home)),
    ]
    table = Table(title="plugadvpl dtc doctor", show_lines=False)
    table.add_column("Check", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Detalhe", overflow="fold")

    all_ok = True
    for name, (ok, detail) in essential:
        status = "[green]OK[/]" if ok else "[red]FAIL[/]"
        table.add_row(name, status, detail)
        all_ok = all_ok and ok

    table.add_row("", "", "")
    table.add_row("[dim]— fallback c-tree (opcional) —[/]", "", "")
    for name, (ok, detail) in optional:
        status = "[green]OK[/]" if ok else "[yellow]opcional[/]"
        table.add_row(name, status, detail)

    console.print(table)
    if all_ok and not optional[0][1][0]:
        console.print(
            "\n[green]Pronto para ler/exportar .dtc Protheus sem o FairCom.[/]\n"
            "[dim]O FairCom só é necessário para o fallback c-tree (arquivos "
            "não-Protheus). Para instalá-lo, veja docs/setup-linux.md.[/]"
        )
    elif not all_ok:
        console.print(
            "\n[yellow]Ambiente incompleto. Para configurar, veja:[/]\n"
            "  Linux:   docs/setup-linux.md\n"
            "  Windows: docs/setup-windows.md\n"
            "  macOS:   docs/setup-macos.md"
        )
    return all_ok
