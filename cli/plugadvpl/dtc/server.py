"""Gerência do servidor FairCom DB local (start / stop / status)."""

from __future__ import annotations

import os
import platform
import signal
import subprocess
from pathlib import Path

from rich.console import Console

from plugadvpl.dtc import faircom

PID_FILE = Path.home() / ".dtcat" / "faircom.pid"


def _ctstop_path(home: Path) -> Path | None:
    name = "ctstop.exe" if platform.system() == "Windows" else "ctstop"
    for sub in ("tools", "bin"):
        p = home / sub / name
        if p.is_file():
            return p
    return None


def server_start(console: Console) -> None:
    if PID_FILE.exists():
        pid = PID_FILE.read_text().strip()
        console.print(
            f"[yellow]Já existe um PID file ({pid}).[/] Use 'plugadvpl dtc server status'."
        )
        return
    home = faircom.find_faircom_home()
    binary = faircom.server_binary(home) if home else None
    if binary is None:
        console.print(
            "[red]Binário do servidor FairCom não encontrado.[/] Rode 'plugadvpl dtc doctor'."
        )
        raise SystemExit(1)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [str(binary)],
        cwd=binary.parent,  # o servidor resolve caminhos relativos a partir daqui
        env=faircom.subprocess_env(home),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    console.print(f"[green]Servidor FairCom iniciado[/] (pid {proc.pid})")


def server_stop(console: Console) -> None:
    if not PID_FILE.exists():
        console.print("[yellow]Sem PID file — server não foi iniciado pelo dtcat.[/]")
        return
    pid = int(PID_FILE.read_text().strip())
    home = faircom.find_faircom_home()
    ctstop = _ctstop_path(home) if home else None
    try:
        if ctstop is not None:
            # shutdown limpo: ctstop -AUTO <user> <pwd> <server>@<host>
            p = faircom.conn_params()
            subprocess.run(
                [
                    str(ctstop),
                    "-AUTO",
                    p["user"],
                    p["password"],
                    f"{faircom.server_name()}@{p['host']}",
                ],
                env=faircom.subprocess_env(home),
                capture_output=True,
                text=True,
                check=False,
            )
            console.print(f"[green]Servidor FairCom encerrado[/] (ctstop, pid {pid})")
        elif platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False)
            console.print(f"[green]Servidor FairCom encerrado[/] (pid {pid})")
        else:
            os.kill(pid, signal.SIGTERM)
            console.print(f"[green]Servidor FairCom encerrado[/] (pid {pid})")
    except ProcessLookupError:
        console.print(f"[yellow]Processo {pid} não estava rodando.[/]")
    finally:
        PID_FILE.unlink(missing_ok=True)


def server_status(console: Console) -> None:
    if not PID_FILE.exists():
        console.print("[red]●[/] parado (sem PID file)")
        return
    pid = int(PID_FILE.read_text().strip())
    if _pid_alive(pid):
        console.print(f"[green]●[/] rodando (pid {pid})")
    else:
        console.print(f"[yellow]●[/] PID file aponta {pid} mas processo não existe — limpando.")
        PID_FILE.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    try:
        if platform.system() == "Windows":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, check=False
            )
            return str(pid) in out.stdout
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
