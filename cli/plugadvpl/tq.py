"""Troca Quente (MVP local) — restart + healthcheck do AppServer.

Spec: docs/superpowers/specs/2026-05-25-plugadvpl-tq-mvp-design.md
"""

from __future__ import annotations

import http.client
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Literal

from plugadvpl.compile_servers import Server


HealthcheckStatus = Literal["up", "timeout", "skipped", "not_run"]


@dataclass(frozen=True)
class TqResult:
    """Resultado estruturado de `run_tq`."""

    ok: bool
    server_name: str
    restart_cmd: str
    restart_exit_code: int
    restart_duration_ms: int
    restart_stderr: str
    healthcheck_status: HealthcheckStatus
    healthcheck_attempts: int
    healthcheck_duration_ms: int
    total_duration_ms: int
    error: str = ""


def _http_probe(host: str, port: int, timeout: float = 2.0) -> tuple[bool, int]:
    """Tenta `GET /` via http.client.

    Retorna ``(is_up, status_code)``:
    - ``is_up=True`` E ``status_code in {200, 401, 404}`` significa AppServer
      respondeu HTTP — sinal canônico de "tá vivo"
    - ``is_up=False`` E ``status_code=0`` significa socket falhou (connection
      refused / timeout)
    - ``is_up=True`` E ``status_code >= 500`` significa porta abriu mas REST
      framework quebrou — caller decide se considera up

    Não levanta exceção — todos os erros viram ``(False, 0)``.
    """
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        try:
            conn.request("GET", "/")
            resp = conn.getresponse()
            return (True, resp.status)
        finally:
            conn.close()
    except (socket.timeout, ConnectionRefusedError, OSError):
        return (False, 0)


def run_tq(
    server: Server,
    timeout_s: int = 60,
    no_healthcheck: bool = False,
    port_override: int = 0,
) -> TqResult:
    """Executa ``restart_cmd`` + healthcheck. Function pure-ish: só side
    effects são ``subprocess.run`` + sockets do healthcheck."""
    start_total = time.monotonic()

    if not server.restart_cmd:
        return TqResult(
            ok=False,
            server_name=server.name,
            restart_cmd="",
            restart_exit_code=-1,
            restart_duration_ms=0,
            restart_stderr="",
            healthcheck_status="not_run",
            healthcheck_attempts=0,
            healthcheck_duration_ms=0,
            total_duration_ms=0,
            error=f"server '{server.name}' sem restart_cmd. Configure: "
            f"plugadvpl compile --set-restart-cmd {server.name} --cmd '<comando>'",
        )

    # Restart
    restart_start = time.monotonic()
    try:
        proc = subprocess.run(
            server.restart_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_s + 10,
        )
        restart_exit = proc.returncode
        restart_stderr = (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        restart_exit = -2
        restart_stderr = f"restart_cmd timeout após {timeout_s + 10}s"
    restart_dur_ms = int((time.monotonic() - restart_start) * 1000)

    if restart_exit != 0:
        return TqResult(
            ok=False,
            server_name=server.name,
            restart_cmd=server.restart_cmd,
            restart_exit_code=restart_exit,
            restart_duration_ms=restart_dur_ms,
            restart_stderr=restart_stderr,
            healthcheck_status="not_run",
            healthcheck_attempts=0,
            healthcheck_duration_ms=0,
            total_duration_ms=int((time.monotonic() - start_total) * 1000),
            error=f"restart_cmd falhou (exit={restart_exit}): {restart_stderr or '(sem stderr)'}",
        )

    # Healthcheck
    if no_healthcheck:
        return TqResult(
            ok=True,
            server_name=server.name,
            restart_cmd=server.restart_cmd,
            restart_exit_code=0,
            restart_duration_ms=restart_dur_ms,
            restart_stderr=restart_stderr,
            healthcheck_status="skipped",
            healthcheck_attempts=0,
            healthcheck_duration_ms=0,
            total_duration_ms=int((time.monotonic() - start_total) * 1000),
        )

    hc_start = time.monotonic()
    attempts = 0
    healthy = False
    hc_port = port_override if port_override > 0 else server.port
    while (time.monotonic() - hc_start) < timeout_s:
        time.sleep(1)
        attempts += 1
        is_up, status = _http_probe(server.host, hc_port, timeout=2.0)
        if is_up and status in {200, 401, 404}:
            healthy = True
            break
    hc_dur_ms = int((time.monotonic() - hc_start) * 1000)

    if not healthy:
        return TqResult(
            ok=False,
            server_name=server.name,
            restart_cmd=server.restart_cmd,
            restart_exit_code=0,
            restart_duration_ms=restart_dur_ms,
            restart_stderr=restart_stderr,
            healthcheck_status="timeout",
            healthcheck_attempts=attempts,
            healthcheck_duration_ms=hc_dur_ms,
            total_duration_ms=int((time.monotonic() - start_total) * 1000),
            error=f"healthcheck timeout após {timeout_s}s ({attempts} tentativas)",
        )

    return TqResult(
        ok=True,
        server_name=server.name,
        restart_cmd=server.restart_cmd,
        restart_exit_code=0,
        restart_duration_ms=restart_dur_ms,
        restart_stderr=restart_stderr,
        healthcheck_status="up",
        healthcheck_attempts=attempts,
        healthcheck_duration_ms=hc_dur_ms,
        total_duration_ms=int((time.monotonic() - start_total) * 1000),
    )
