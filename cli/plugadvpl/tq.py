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
) -> TqResult:
    """Executa ``restart_cmd`` + healthcheck. Function pure-ish: só side
    effects são ``subprocess.run`` + sockets do healthcheck."""
    raise NotImplementedError  # TDD nas Tasks 5+
