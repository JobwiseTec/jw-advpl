# `plugadvpl tq` MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar subcomando `plugadvpl tq` que executa `restart_cmd` configurado no server + healthcheck HTTP até AppServer voltar, automatizando o passo manual que estava sendo feito com `cmd /c restart-totvs.bat` + curl loop.

**Architecture:** Campo novo `restart_cmd` em `Server` dataclass do registry global. Comando `plugadvpl compile --set-restart-cmd <server> --cmd "<cmd>"` configura. Subcomando `plugadvpl tq --use-server <name>` executa restart via `subprocess.run(shell=True)` + healthcheck via `http.client.HTTPConnection` GET `/` esperando status 200/401/404. Reusa `_render_from_ctx` pra tabela/JSON.

**Tech Stack:** Python 3.11+, Typer (CLI), `subprocess`, `http.client`, `socket`, pytest, `CliRunner`. Sem deps novas.

**Spec:** [`docs/superpowers/specs/2026-05-25-plugadvpl-tq-mvp-design.md`](../specs/2026-05-25-plugadvpl-tq-mvp-design.md)

---

## File Structure

**Arquivos novos:**
- `cli/plugadvpl/tq.py` — módulo `run_tq()`, `_http_probe()`, `TqResult` (responsabilidade única: lógica de restart+healthcheck pure-ish)
- `cli/tests/unit/test_tq.py` — 6 casos unit do core (mock subprocess + http.client)
- `cli/tests/integration/test_cli_tq.py` — 7 casos integration via `CliRunner`
- `skills/tq/SKILL.md` — slash command wrapper

**Arquivos modificados:**
- `cli/plugadvpl/compile_servers.py` — adiciona 1 campo (`restart_cmd: str = ""`) na `Server` dataclass
- `cli/plugadvpl/cli.py` — 2 flags novas (`--set-restart-cmd`, `--cmd`) no `compile`, handler `_handle_set_restart_cmd`, novo `@app.command("tq")`, atualiza `suspicious_flags`
- `CHANGELOG.md` — entry sob `[Unreleased]`
- `README.md` — adiciona `tq` à tabela "Runtime ADVPL — edit + compile"; ajusta "Próximas entregas" pra refletir entrega

---

## Chunk 1: Implementação

### Task 1: Adiciona `restart_cmd` ao `Server` dataclass

**Files:**
- Modify: `cli/plugadvpl/compile_servers.py:23-37`
- Test: `cli/tests/unit/test_compile_servers.py` (suite existente cobre roundtrip JSON)

- [ ] **Step 1: Adiciona campo `restart_cmd` ao dataclass**

Edita `cli/plugadvpl/compile_servers.py:23-37`. Procura o bloco `@dataclass(frozen=True) class Server:` e adiciona `restart_cmd: str = ""` ANTES do `includes` (que é o último com default factory):

```python
@dataclass(frozen=True)
class Server:
    """Cadastro de um AppServer Protheus."""

    name: str
    host: str
    port: int
    build: str
    environments: list[str]
    default_environment: str
    user_env: str = "PROTHEUS_USER"
    password_env: str = "PROTHEUS_PASS"
    secure: bool = False
    notes: str = ""
    restart_cmd: str = ""  # v0.14: shell command pra restart do AppServer (Troca Quente)
    includes: list[str] = field(default_factory=list)  # v0.8.11: vem do TDS-VSCode
```

- [ ] **Step 2: Roda suite full pra garantir backwards-compat**

Run: `cd cli && uv run pytest --tb=short -q 2>&1 | tail -5`
Expected: `1028 passed, 2 skipped, 6 deselected` (baseline atual em 2026-05-25). Se algum teste de `test_compile_servers.py` quebrar, é porque o registry JSON antigo não tem o campo — `Server(**raw)` espera `restart_cmd` mas o JSON tem só `includes`. Solução: NÃO é problema pra default (`Server(name=..., includes=[...])` funciona com default `restart_cmd=""`), mas se quebrar, verificar o `load_registry` em compile_servers.py:67 (`Server(**s)`) — pode precisar `Server(**s, restart_cmd=s.get("restart_cmd", ""))` ou usar try/except.

- [ ] **Step 3: Commit**

```bash
git add cli/plugadvpl/compile_servers.py
git commit -m "feat(tq): adiciona campo restart_cmd ao Server dataclass

Campo novo opcional (default '') no registry global de servers.
Backwards-compat: servers existentes sem o campo continuam funcionando.
Base pra v0.14 plugadvpl tq (restart + healthcheck do AppServer)."
```

---

### Task 2: Handler `--set-restart-cmd` + `--cmd` no `compile`

**Files:**
- Modify: `cli/plugadvpl/cli.py` (procurar `compile` command + adicionar flags + handler)
- Test: `cli/tests/integration/test_cli_compile.py` (adiciona classe `TestSetRestartCmd`)

- [ ] **Step 1: Adiciona as 2 opções typer ao `compile_cmd`**

Procura em `cli/plugadvpl/cli.py` a opção `set_credentials_for` (~ linha 2916) e adiciona DEPOIS dela e ANTES de `clear_credentials_for`:

```python
    set_restart_cmd: Annotated[
        str,
        typer.Option(
            "--set-restart-cmd",
            help="Nome do server pra configurar restart_cmd (use junto com --cmd)",
        ),
    ] = "",
    cmd_value: Annotated[
        str,
        typer.Option(
            "--cmd",
            help='Comando shell pro restart (use com --set-restart-cmd). Ex: "cmd.exe /c restart.bat"',
        ),
    ] = "",
```

- [ ] **Step 2: Adiciona handler check no corpo do `compile_cmd`**

Procura `if clear_credentials_for:` (~ linha 2988) e adiciona ANTES:

```python
    if set_restart_cmd:
        if not cmd_value:
            typer.secho(
                "--set-restart-cmd requer --cmd '<comando>'",
                fg=typer.colors.RED, err=True,
            )
            raise typer.Exit(code=2)
        _handle_set_restart_cmd(set_restart_cmd, cmd_value)
        return
```

- [ ] **Step 3: Adiciona flags em `suspicious_flags`**

Procura o set `suspicious_flags` (~ linha 3014) e adiciona `--set-restart-cmd` e `--cmd`:

```python
    suspicious_flags = {
        # ... existentes ...
        "--set-credentials", "--clear-credentials", "--explain-config",
        "--set-restart-cmd", "--cmd",
    }
```

- [ ] **Step 4: Adiciona função `_handle_set_restart_cmd`**

Adiciona DEPOIS de `_handle_set_credentials` (procurar `def _handle_set_credentials` ~ linha 3457). Cole no fim, logo antes da próxima função:

```python
def _handle_set_restart_cmd(server_name: str, cmd: str) -> None:
    """Grava o restart_cmd no server do registry global (v0.14)."""
    from dataclasses import replace
    from plugadvpl.compile_servers import (
        ServersRegistry,
        get_server,
        load_registry,
        save_registry,
    )

    srv = get_server(server_name)
    if srv is None:
        typer.secho(
            f"Server '{server_name}' não cadastrado.\n"
            f"  Liste: plugadvpl compile --list-servers\n"
            f"  Cadastre: plugadvpl compile --add-server",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=2)

    new_srv = replace(srv, restart_cmd=cmd)
    registry = load_registry()
    new_servers = [new_srv if s.name == server_name else s for s in registry.servers]
    save_registry(ServersRegistry(default=registry.default, servers=new_servers))

    typer.secho(
        f"restart_cmd setado pra '{server_name}': {cmd!r}",
        fg=typer.colors.GREEN,
    )
```

- [ ] **Step 5: Adiciona 3 testes integration**

Cria/abre `cli/tests/integration/test_cli_compile.py`. Procura `class TestAllEnvs:` e adiciona ANTES dele:

```python
class TestSetRestartCmd:
    """v0.14: --set-restart-cmd grava restart_cmd no server do registry."""

    def test_set_restart_cmd_happy_path(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server, get_server
        add_server(Server(
            name="local-dev", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["env_a"], default_environment="env_a",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--set-restart-cmd", "local-dev",
                  "--cmd", "echo restart"],
        )
        assert result.exit_code == 0, result.output
        srv = get_server("local-dev")
        assert srv is not None
        assert srv.restart_cmd == "echo restart"

    def test_set_restart_cmd_without_cmd_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="x", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["env_a"], default_environment="env_a",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--set-restart-cmd", "x"],
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "--cmd" in combined

    def test_set_restart_cmd_unknown_server_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--set-restart-cmd", "ghost",
                  "--cmd", "echo x"],
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "ghost" in combined and "não cadastrado" in combined
```

- [ ] **Step 6: Run os 3 testes — esperado: 3 PASS (handler implementado em Step 4)**

Run: `cd cli && uv run pytest tests/integration/test_cli_compile.py::TestSetRestartCmd -v --tb=short 2>&1 | tail -15`

Se algum falhar, debugar `_handle_set_restart_cmd` ou as flags `--set-restart-cmd`/`--cmd` no `compile_cmd`.

- [ ] **Step 7: Roda suite full pra garantir nada quebrou**

Run: `cd cli && uv run pytest --tb=short -q 2>&1 | tail -5`
Expected: `1031 passed` (1028 baseline + 3 novos).

- [ ] **Step 8: Commit**

```bash
git add cli/plugadvpl/cli.py cli/tests/integration/test_cli_compile.py
git commit -m "feat(tq): adiciona --set-restart-cmd + --cmd no compile

Flags coordenadas no plugadvpl compile pra gravar restart_cmd no
server do registry global ~/.plugadvpl/servers.json.

Uso:
  plugadvpl compile --set-restart-cmd Local --cmd 'cmd /c restart.bat'

Validações: --set-restart-cmd sem --cmd erra (exit 2), server
não cadastrado erra com hint pra --list-servers.

3 testes integration novos cobrindo happy + ambos os erros."
```

---

### Task 3: Cria módulo `tq.py` com `TqResult` dataclass (skeleton)

**Files:**
- Create: `cli/plugadvpl/tq.py`

- [ ] **Step 1: Cria o módulo com a dataclass + skeleton das funções**

Cria `cli/plugadvpl/tq.py` com o conteúdo:

```python
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
    raise NotImplementedError  # TDD na Task 4


def run_tq(
    server: Server,
    timeout_s: int = 60,
    no_healthcheck: bool = False,
) -> TqResult:
    """Executa ``restart_cmd`` + healthcheck. Function pure-ish: só side
    effects são ``subprocess.run`` + sockets do healthcheck."""
    raise NotImplementedError  # TDD nas Tasks 5+
```

- [ ] **Step 2: Roda suite pra garantir import limpo**

Run: `cd cli && uv run python -c "from plugadvpl.tq import TqResult, run_tq, _http_probe; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add cli/plugadvpl/tq.py
git commit -m "feat(tq): cria modulo tq.py com TqResult dataclass (skeleton)

run_tq e _http_probe sao stubs com NotImplementedError -- TDD nas
proximas tasks. TqResult dataclass fechada com 11 campos."
```

---

### Task 4: TDD `_http_probe` — caso happy path

**Files:**
- Create: `cli/tests/unit/test_tq.py`
- Modify: `cli/plugadvpl/tq.py` (implementa `_http_probe`)

- [ ] **Step 1: Escreve o teste failing**

Cria `cli/tests/unit/test_tq.py` com:

```python
"""Testes unit do modulo plugadvpl.tq — restart + healthcheck."""
from __future__ import annotations

import subprocess
from unittest import mock

import pytest

from plugadvpl.compile_servers import Server
from plugadvpl.tq import TqResult, _http_probe, run_tq


def _make_server(name: str = "test-srv", restart_cmd: str = "echo restart") -> Server:
    """Server de teste com defaults razoáveis."""
    return Server(
        name=name,
        host="127.0.0.1",
        port=8019,
        build="7.00.240223P",
        environments=["env_a"],
        default_environment="env_a",
        restart_cmd=restart_cmd,
    )


class TestHttpProbe:
    """_http_probe(host, port) -> (is_up, status_code)."""

    def test_returns_true_status_for_200_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AppServer respondendo HTTP 200 → (True, 200)."""
        fake_conn = mock.MagicMock()
        fake_conn.getresponse.return_value = mock.MagicMock(status=200)

        def fake_http_connection(host, port, timeout):  # noqa: ARG001
            return fake_conn

        monkeypatch.setattr(
            "plugadvpl.tq.http.client.HTTPConnection", fake_http_connection
        )
        is_up, status = _http_probe("127.0.0.1", 8019, timeout=2.0)
        assert is_up is True
        assert status == 200
```

- [ ] **Step 2: Roda o teste — espera FAIL com NotImplementedError**

Run: `cd cli && uv run pytest tests/unit/test_tq.py::TestHttpProbe::test_returns_true_status_for_200_response -v --tb=short 2>&1 | tail -10`
Expected: `FAILED` com `NotImplementedError`

- [ ] **Step 3: Implementa `_http_probe`**

Edita `cli/plugadvpl/tq.py`. Substitui o corpo de `_http_probe` (que tem `raise NotImplementedError`) por:

```python
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
```

- [ ] **Step 4: Roda o teste — espera PASS**

Run: `cd cli && uv run pytest tests/unit/test_tq.py::TestHttpProbe::test_returns_true_status_for_200_response -v --tb=short 2>&1 | tail -5`
Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/tq.py cli/tests/unit/test_tq.py
git commit -m "feat(tq): implementa _http_probe (TDD: 200 response)

GET / via http.client.HTTPConnection. Captura status code real
do AppServer pra distinguir 'porta abre + REST pronto' (200/401/
404) de 'porta abre mas framework quebrou' (5xx). Exceptions
viram (False, 0) -- caller trata uniforme."
```

---

### Task 5: TDD `_http_probe` — caso connection refused

**Files:**
- Modify: `cli/tests/unit/test_tq.py`

- [ ] **Step 1: Adiciona teste**

Append em `TestHttpProbe`:

```python
    def test_returns_false_when_connection_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AppServer down (TCP refused) → (False, 0)."""
        def raise_refused(*args, **kwargs):  # noqa: ARG001
            raise ConnectionRefusedError("nope")
        monkeypatch.setattr(
            "plugadvpl.tq.http.client.HTTPConnection", raise_refused
        )
        is_up, status = _http_probe("127.0.0.1", 8019)
        assert is_up is False
        assert status == 0
```

- [ ] **Step 2: Roda — espera PASS (lógica já cobre via try/except)**

Run: `cd cli && uv run pytest tests/unit/test_tq.py::TestHttpProbe -v --tb=short 2>&1 | tail -10`
Expected: ambos passam.

- [ ] **Step 3: Commit**

```bash
git add cli/tests/unit/test_tq.py
git commit -m "test(tq): cobre _http_probe com connection refused

Confirma que ConnectionRefusedError vira (False, 0) sem propagar.
Caller no run_tq pode tratar uniforme 'AppServer ainda down'."
```

---

### Task 6: TDD `run_tq` — happy path

**Files:**
- Modify: `cli/plugadvpl/tq.py` (implementa `run_tq`)
- Modify: `cli/tests/unit/test_tq.py`

- [ ] **Step 1: Adiciona teste happy path**

Append em `cli/tests/unit/test_tq.py` (depois do `TestHttpProbe`):

```python
class TestRunTq:
    """run_tq(server, timeout_s, no_healthcheck) -> TqResult."""

    def test_happy_path_restart_then_healthcheck_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """restart_cmd exit 0 + healthcheck retorna 200 no 3o ping → ok=True."""
        srv = _make_server(restart_cmd="echo restart")

        # Mock subprocess.run pra exit_code=0
        fake_run = mock.MagicMock(return_value=mock.MagicMock(
            returncode=0, stderr=""
        ))
        monkeypatch.setattr("plugadvpl.tq.subprocess.run", fake_run)

        # Mock _http_probe: 2 falhas + 1 sucesso
        probe_calls = [(False, 0), (False, 0), (True, 200)]
        probe_iter = iter(probe_calls)
        monkeypatch.setattr(
            "plugadvpl.tq._http_probe",
            lambda *a, **kw: next(probe_iter),
        )
        # Mock time.sleep pra não esperar de verdade
        monkeypatch.setattr("plugadvpl.tq.time.sleep", lambda s: None)

        result = run_tq(srv, timeout_s=60)
        assert result.ok is True
        assert result.healthcheck_status == "up"
        assert result.healthcheck_attempts == 3
        assert result.restart_exit_code == 0
        assert result.error == ""
```

- [ ] **Step 2: Roda — espera FAIL (NotImplementedError)**

Run: `cd cli && uv run pytest tests/unit/test_tq.py::TestRunTq::test_happy_path_restart_then_healthcheck_up -v --tb=short 2>&1 | tail -10`
Expected: FAILED `NotImplementedError`

- [ ] **Step 3: Implementa `run_tq`**

Substitui o `raise NotImplementedError` de `run_tq` em `cli/plugadvpl/tq.py`:

```python
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
    while (time.monotonic() - hc_start) < timeout_s:
        time.sleep(1)
        attempts += 1
        is_up, status = _http_probe(server.host, server.port, timeout=2.0)
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
```

- [ ] **Step 4: Roda happy path — espera PASS**

Run: `cd cli && uv run pytest tests/unit/test_tq.py::TestRunTq::test_happy_path_restart_then_healthcheck_up -v --tb=short 2>&1 | tail -5`
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/tq.py cli/tests/unit/test_tq.py
git commit -m "feat(tq): implementa run_tq happy path (TDD)

Orquestra subprocess.run(restart_cmd) + healthcheck loop com
_http_probe ate timeout. Retorna TqResult estruturado com
duracoes em ms, attempts do healthcheck, exit_code do restart.

Cobre happy path: restart exit 0 + probe retorna 200 -> ok=True."
```

---

### Task 7: TDD `run_tq` — restart_cmd vazio

- [ ] **Step 1: Adiciona teste**

Append em `TestRunTq` (cli/tests/unit/test_tq.py):

```python
    def test_empty_restart_cmd_returns_error_without_subprocess(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Server com restart_cmd vazio nao roda subprocess, retorna ok=False."""
        srv = _make_server(restart_cmd="")
        fake_run = mock.MagicMock()
        monkeypatch.setattr("plugadvpl.tq.subprocess.run", fake_run)

        result = run_tq(srv, timeout_s=60)
        assert result.ok is False
        assert "sem restart_cmd" in result.error
        assert "--set-restart-cmd" in result.error
        assert result.healthcheck_status == "not_run"
        fake_run.assert_not_called()
```

- [ ] **Step 2: Roda — espera PASS (já coberto)**

Run: `cd cli && uv run pytest tests/unit/test_tq.py::TestRunTq -v --tb=short 2>&1 | tail -10`
Expected: ambos passam.

- [ ] **Step 3: Commit**

```bash
git add cli/tests/unit/test_tq.py
git commit -m "test(tq): cobre run_tq com restart_cmd vazio

Server sem cmd configurado -> error com hint pra --set-restart-cmd,
sem invocar subprocess. healthcheck_status=not_run."
```

---

### Task 8: TDD `run_tq` — restart exit non-zero

- [ ] **Step 1: Adiciona teste**

Append em `TestRunTq`:

```python
    def test_restart_exit_non_zero_captures_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Restart cmd que falha -> ok=False com stderr capturado."""
        srv = _make_server(restart_cmd="false")
        fake_run = mock.MagicMock(return_value=mock.MagicMock(
            returncode=1, stderr="boom\n"
        ))
        monkeypatch.setattr("plugadvpl.tq.subprocess.run", fake_run)

        # Healthcheck nao deve ser chamado
        probe_mock = mock.MagicMock()
        monkeypatch.setattr("plugadvpl.tq._http_probe", probe_mock)

        result = run_tq(srv, timeout_s=60)
        assert result.ok is False
        assert result.restart_exit_code == 1
        assert result.restart_stderr == "boom"
        assert result.healthcheck_status == "not_run"
        assert "exit=1" in result.error
        probe_mock.assert_not_called()
```

- [ ] **Step 2: Roda — espera PASS (já coberto)**

Run: `cd cli && uv run pytest tests/unit/test_tq.py -v --tb=short 2>&1 | tail -10`
Expected: 4 passes.

- [ ] **Step 3: Commit**

```bash
git add cli/tests/unit/test_tq.py
git commit -m "test(tq): cobre run_tq com restart_cmd exit non-zero

Subprocess retorna exit=1 + stderr -> ok=False, stderr capturado,
healthcheck nem roda."
```

---

### Task 9: TDD `run_tq` — healthcheck timeout

- [ ] **Step 1: Adiciona teste**

Append em `TestRunTq`:

```python
    def test_healthcheck_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Todos os probes retornam (False, 0) -> timeout."""
        srv = _make_server(restart_cmd="echo ok")
        fake_run = mock.MagicMock(return_value=mock.MagicMock(
            returncode=0, stderr=""
        ))
        monkeypatch.setattr("plugadvpl.tq.subprocess.run", fake_run)
        monkeypatch.setattr(
            "plugadvpl.tq._http_probe",
            lambda *a, **kw: (False, 0),
        )
        monkeypatch.setattr("plugadvpl.tq.time.sleep", lambda s: None)

        # Mock time.monotonic pra avancar 0, 1, 2, ..., 61 segundos
        ts = [0.0]
        def fake_mono():
            ts[0] += 1.0
            return ts[0]
        monkeypatch.setattr("plugadvpl.tq.time.monotonic", fake_mono)

        result = run_tq(srv, timeout_s=3)
        assert result.ok is False
        assert result.healthcheck_status == "timeout"
        assert "healthcheck timeout" in result.error
        assert result.healthcheck_attempts >= 1
```

- [ ] **Step 2: Roda — espera PASS**

Run: `cd cli && uv run pytest tests/unit/test_tq.py::TestRunTq::test_healthcheck_timeout -v --tb=short 2>&1 | tail -10`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add cli/tests/unit/test_tq.py
git commit -m "test(tq): cobre run_tq com healthcheck timeout

Todos os probes (False, 0) + monotonic avancando -> ok=False,
healthcheck_status=timeout, error contem 'healthcheck timeout'."
```

---

### Task 10: TDD `run_tq` — healthcheck 5xx false positive guard

- [ ] **Step 1: Adiciona teste**

Append em `TestRunTq`:

```python
    def test_healthcheck_5xx_does_not_count_as_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Status 503 nao conta como up -- continua tentando ate timeout."""
        srv = _make_server(restart_cmd="echo ok")
        monkeypatch.setattr("plugadvpl.tq.subprocess.run",
                            mock.MagicMock(return_value=mock.MagicMock(returncode=0, stderr="")))
        # _http_probe sempre (True, 503) — porta abre mas REST quebrou
        monkeypatch.setattr(
            "plugadvpl.tq._http_probe",
            lambda *a, **kw: (True, 503),
        )
        monkeypatch.setattr("plugadvpl.tq.time.sleep", lambda s: None)
        ts = [0.0]
        def fake_mono():
            ts[0] += 1.0
            return ts[0]
        monkeypatch.setattr("plugadvpl.tq.time.monotonic", fake_mono)

        result = run_tq(srv, timeout_s=3)
        assert result.ok is False
        assert result.healthcheck_status == "timeout"
```

- [ ] **Step 2: Roda — espera PASS**

Run: `cd cli && uv run pytest tests/unit/test_tq.py::TestRunTq::test_healthcheck_5xx_does_not_count_as_up -v --tb=short 2>&1 | tail -5`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add cli/tests/unit/test_tq.py
git commit -m "test(tq): cobre healthcheck false positive guard (5xx)

Porta abre mas REST framework retorna 503 -> nao considera up,
continua tentando ate timeout. Pega o caso real onde AppServer
inicia processo mas WSRESTFUL ainda nao carregou."
```

---

### Task 11: TDD `run_tq` — `--no-healthcheck`

- [ ] **Step 1: Adiciona teste**

Append em `TestRunTq`:

```python
    def test_no_healthcheck_skips_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """no_healthcheck=True -> nao chama _http_probe nem time.sleep."""
        srv = _make_server(restart_cmd="echo ok")
        monkeypatch.setattr("plugadvpl.tq.subprocess.run",
                            mock.MagicMock(return_value=mock.MagicMock(returncode=0, stderr="")))
        probe_mock = mock.MagicMock()
        sleep_mock = mock.MagicMock()
        monkeypatch.setattr("plugadvpl.tq._http_probe", probe_mock)
        monkeypatch.setattr("plugadvpl.tq.time.sleep", sleep_mock)

        result = run_tq(srv, timeout_s=60, no_healthcheck=True)
        assert result.ok is True
        assert result.healthcheck_status == "skipped"
        assert result.healthcheck_attempts == 0
        probe_mock.assert_not_called()
        sleep_mock.assert_not_called()
```

- [ ] **Step 2: Roda — espera PASS**

Run: `cd cli && uv run pytest tests/unit/test_tq.py::TestRunTq::test_no_healthcheck_skips_loop -v --tb=short 2>&1 | tail -5`
Expected: PASSED.

- [ ] **Step 3: Roda suite full pra garantir sanidade**

Run: `cd cli && uv run pytest --tb=short -q 2>&1 | tail -5`
Expected: `1039 passed` (1031 + 8 testes novos do tq.py: 2 do _http_probe + 6 do run_tq).

- [ ] **Step 4: Commit**

```bash
git add cli/tests/unit/test_tq.py
git commit -m "test(tq): cobre --no-healthcheck que pula o loop

run_tq(server, no_healthcheck=True) -> ok=True direto pos-restart,
nao chama _http_probe nem time.sleep. healthcheck_status=skipped."
```

---

### Task 12: Adiciona subcomando `plugadvpl tq` ao CLI

**Files:**
- Modify: `cli/plugadvpl/cli.py` (adiciona `@app.command("tq")` no final, antes da última função)
- Test: já tem unit; integration vem na Task 13

- [ ] **Step 1: Localiza o lugar pra inserir**

Use a tool **Grep** com pattern `^@app\.command|^def _handle_set_restart_cmd` em `cli/plugadvpl/cli.py` pra ver os anchors do arquivo. O `@app.command("tq")` vai bem ANTES da última função `_handle_*` (logo após `_handle_set_restart_cmd` da Task 2).

- [ ] **Step 2: Adiciona a definição do comando**

Insere em `cli/plugadvpl/cli.py` (antes da última `_handle_*` função, busque posição sensata). Cole:

```python
@app.command("tq")
def tq_cmd(
    ctx: typer.Context,
    use_server: Annotated[
        str,
        typer.Option("--use-server", help="Server do registry (~/.plugadvpl/servers.json)"),
    ] = "",
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Timeout do healthcheck em segundos (default 60)"),
    ] = 60,
    no_healthcheck: Annotated[
        bool,
        typer.Option("--no-healthcheck", help="Só executa restart_cmd, pula healthcheck"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Mostra o que faria, não executa"),
    ] = False,
) -> None:
    """Restart do AppServer + healthcheck (Troca Quente MVP local)."""
    from dataclasses import asdict
    from plugadvpl.compile_servers import get_server
    from plugadvpl.tq import run_tq

    if not use_server:
        typer.secho("--use-server obrigatório", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    srv = get_server(use_server)
    if srv is None:
        typer.secho(
            f"Server '{use_server}' não cadastrado.\n"
            f"  Liste: plugadvpl compile --list-servers",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=2)

    if not srv.restart_cmd:
        typer.secho(
            f"Server '{use_server}' sem restart_cmd. Configure:\n"
            f"  plugadvpl compile --set-restart-cmd {use_server} --cmd '<comando>'",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=2)

    if dry_run:
        rows = [{
            "server": srv.name,
            "host": f"{srv.host}:{srv.port}",
            "restart_cmd": srv.restart_cmd,
            "healthcheck": "skipped" if no_healthcheck else f"GET / (timeout {timeout}s)",
            "dry_run": True,
        }]
        _render_from_ctx(
            ctx, rows,
            columns=["server", "host", "restart_cmd", "healthcheck", "dry_run"],
            title=f"tq --dry-run ({srv.name})",
            next_steps=[f"plugadvpl tq --use-server {srv.name}  # roda de verdade"],
        )
        raise typer.Exit(code=0)

    result = run_tq(srv, timeout_s=timeout, no_healthcheck=no_healthcheck)
    rows = [asdict(result)]
    _render_from_ctx(
        ctx, rows,
        columns=[
            "ok", "server_name", "restart_exit_code", "restart_duration_ms",
            "healthcheck_status", "healthcheck_attempts", "total_duration_ms",
            "error",
        ],
        title=f"tq ({srv.name})",
        next_steps=[],
    )
    raise typer.Exit(code=0 if result.ok else 1)
```

- [ ] **Step 3: Verifica que `plugadvpl tq --help` funciona**

Run: `cd cli && uv run plugadvpl tq --help 2>&1 | head -20`
Expected: ajuda do comando aparece com 4 opções (`--use-server`, `--timeout`, `--no-healthcheck`, `--dry-run`).

- [ ] **Step 4: Commit**

```bash
git add cli/plugadvpl/cli.py
git commit -m "feat(tq): adiciona subcomando plugadvpl tq

Wire do CLI ao run_tq. Validacoes: --use-server obrigatorio,
server precisa existir, restart_cmd precisa estar configurado.
--dry-run mostra preview sem executar. Render via _render_from_ctx
honra --format json/yaml do CLI root."
```

---

### Task 13: Integration tests do subcomando `tq`

**Files:**
- Create: `cli/tests/integration/test_cli_tq.py`

- [ ] **Step 1: Cria arquivo de teste com 4 casos validation (sem mock subprocess)**

Cria `cli/tests/integration/test_cli_tq.py`:

```python
"""Testes integration do subcomando plugadvpl tq."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from plugadvpl.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


class TestTqValidations:
    """Erros estruturados antes de qualquer side-effect."""

    def test_tq_without_use_server_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = runner.invoke(app, ["--root", str(tmp_path), "tq"])
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "--use-server" in combined

    def test_tq_with_unknown_server_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq", "--use-server", "ghost"]
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "ghost" in combined and "não cadastrado" in combined

    def test_tq_server_without_restart_cmd_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="no-cmd", host="127.0.0.1", port=1234,
            build="7.00.240223P", environments=["env_a"],
            default_environment="env_a",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq", "--use-server", "no-cmd"]
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "sem restart_cmd" in combined
        assert "--set-restart-cmd no-cmd --cmd" in combined


class TestTqDryRun:
    """--dry-run nao executa subprocess, so imprime preview."""

    def test_dry_run_with_valid_server(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="dev", host="127.0.0.1", port=1234,
            build="7.00.240223P", environments=["env_a"],
            default_environment="env_a",
            restart_cmd="echo restart",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq",
                  "--use-server", "dev", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        combined = (result.stdout or "") + (result.stderr or "")
        assert "echo restart" in combined
        assert "dry_run" in combined.lower() or "dry-run" in combined.lower()


class TestTqJsonOutput:
    """--format json honra schema documentado."""

    def test_dry_run_json_output_has_expected_keys(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="dev", host="127.0.0.1", port=1234,
            build="7.00.240223P", environments=["env_a"],
            default_environment="env_a",
            restart_cmd="echo restart",
        ))
        result = runner.invoke(
            app, ["--format", "json", "--root", str(tmp_path), "tq",
                  "--use-server", "dev", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        # Output deve conter um JSON parseável
        out = result.stdout or ""
        # Extrai o JSON (pode ter linhas antes/depois)
        json_start = out.find("{")
        json_end = out.rfind("}")
        if json_start == -1 or json_end == -1:
            json_start = out.find("[")
            json_end = out.rfind("]")
        assert json_start != -1, f"Sem JSON no output: {out!r}"
        payload = json.loads(out[json_start:json_end + 1])
        # Aceita lista de rows ou dict
        if isinstance(payload, list):
            payload = payload[0]
        elif "rows" in payload:
            payload = payload["rows"][0]
        assert payload.get("server") == "dev" or payload.get("server_name") == "dev"
```

- [ ] **Step 2: Roda os 5 testes — espera todos PASS**

Run: `cd cli && uv run pytest tests/integration/test_cli_tq.py -v --tb=short 2>&1 | tail -15`
Expected: 5 passes.

- [ ] **Step 3: Roda suite full**

Run: `cd cli && uv run pytest --tb=short -q 2>&1 | tail -5`
Expected: `1044 passed` (1039 + 5 integration tests novos do tq).

- [ ] **Step 4: Commit**

```bash
git add cli/tests/integration/test_cli_tq.py
git commit -m "test(tq): 5 integration tests do subcomando

Cobre validacoes (sem --use-server, server inexistente,
sem restart_cmd), --dry-run, --format json output."
```

---

### Task 14: Skill `skills/tq/SKILL.md`

**Files:**
- Create: `skills/tq/SKILL.md`

- [ ] **Step 1: Cria a skill seguindo o padrão de `skills/ingest-protheus/SKILL.md`**

Cria `skills/tq/SKILL.md`:

```markdown
---
description: Troca Quente (MVP local) — restart do AppServer Protheus + healthcheck HTTP. Use quando precisar restartar o AppServer após `compile` e esperar voltar pra testar.
disable-model-invocation: true
arguments: [opcoes]
allowed-tools: [Bash]
---

# `/plugadvpl:tq`

Executa o `restart_cmd` configurado pro server (registry global) e espera o AppServer voltar via healthcheck HTTP (GET `/` retornando 200/401/404).

MVP pra testes locais — não faz versionamento de RPO, edição de `.ini` ou rollback. A versão completa pra produção fica pra [issue #5](https://github.com/JoniPraia/plugadvpl/issues/5).

## Pré-requisito

Server cadastrado com `restart_cmd` configurado:

\`\`\`bash
plugadvpl compile --set-restart-cmd Local --cmd "cmd.exe /c gaps\\restart-totvs.bat"
\`\`\`

## Uso

\`\`\`
/plugadvpl:tq --use-server <nome>
/plugadvpl:tq --use-server <nome> --timeout 120
/plugadvpl:tq --use-server <nome> --no-healthcheck
/plugadvpl:tq --use-server <nome> --dry-run
\`\`\`

## Argumentos

- `--use-server NAME` — nome do server no registry. **Obrigatório**.
- `--timeout N` — timeout do healthcheck em segundos (default 60).
- `--no-healthcheck` — só roda o `restart_cmd`, pula o loop de healthcheck.
- `--dry-run` — mostra o que faria sem executar.

## Execucao

\`\`\`bash
uvx plugadvpl@0.13.1 tq $ARGUMENTS
\`\`\`

## Encadeamento típico

Depois de compilar pra vários envs com `--all-envs`, restartar:

\`\`\`bash
plugadvpl compile --use-server Local --all-envs <fonte> && \\
plugadvpl tq --use-server Local
\`\`\`

## Erros comuns

- **`--use-server obrigatório`** — passe `--use-server <nome>`
- **`server '<nome>' não cadastrado`** — registry vazio ou nome errado. Rode `plugadvpl compile --list-servers`
- **`server '<nome>' sem restart_cmd`** — configure: `plugadvpl compile --set-restart-cmd <nome> --cmd "<cmd>"`
- **`restart_cmd falhou (exit=N)`** — o shell command retornou non-zero; verifique stderr no output
- **`healthcheck timeout`** — AppServer não voltou em N segundos. Aumente `--timeout` ou verifique manualmente
```

- [ ] **Step 2: Commit**

```bash
git add skills/tq/SKILL.md
git commit -m "feat(tq): adiciona skill /plugadvpl:tq

Slash command wrapper seguindo padrao do projeto (skill-as-command,
disable-model-invocation). Documenta pre-requisito (--set-restart-cmd),
uso, encadeamento tipico com --all-envs, erros comuns."
```

---

### Task 15: README + CHANGELOG

**Files:**
- Modify: `README.md` (tabela "Runtime ADVPL — edit + compile" + seção "Próximas entregas" + "Evolução por versão")
- Modify: `CHANGELOG.md` (entry sob `[Unreleased]`)

- [ ] **Step 1: Adiciona linhas `tq` e `--set-restart-cmd` na tabela de runtime**

Use a tool **Grep** em `README.md` com pattern `--all-envs` pra localizar a linha exata. Daí use **Edit** pra adicionar 2 linhas NOVAS DEPOIS dessa linha (preserva contexto anterior pra Edit não ambíguo):

`old_string`:
```markdown
| `/plugadvpl:compile --all-envs` | Compila pra **todos** os environments do `--use-server` (RPO sync entre envs — ex: `protheus` + `protheus_rest`) |
```

`new_string` (mesma linha + 2 novas):
```markdown
| `/plugadvpl:compile --all-envs` | Compila pra **todos** os environments do `--use-server` (RPO sync entre envs — ex: `protheus` + `protheus_rest`) |
| `/plugadvpl:compile --set-restart-cmd <server> --cmd "<cmd>"` | Configura o `restart_cmd` do server no registry global (consumido pelo `tq`) |
| `/plugadvpl:tq --use-server <nome>` | Restart do AppServer + healthcheck HTTP (Troca Quente MVP local). Encadeia bem com `compile --all-envs` |
```

- [ ] **Step 2: Atualiza seção "Próximas entregas"**

Procura `### Próximas entregas` no README. Substitui o bullet do `plugadvpl-ops` por:

```markdown
- **Sub-plugin `plugadvpl-ops`** (planejado) — `apply-patch` (aplicar `.PTM` via advpls, idempotente com backup). Issue [#4](https://github.com/JoniPraia/plugadvpl/issues/4). O `tq` (Troca Quente) MVP já está entregue como `plugadvpl tq` no core; versão robusta pra produção (versionamento + .ini editing + rollback) fica pra issue [#5](https://github.com/JoniPraia/plugadvpl/issues/5) quando justificar
- **`sx-drift`** — compara dicionário SX local vs estado atual do AppServer via REST, mostra drift por tabela/campo
```

- [ ] **Step 3: Adiciona seção "Em desenvolvimento" se já existir, ou cria entry v0.14**

Procura a seção `## Evolução por versão` no README. Atualiza o bloco "Em desenvolvimento (unreleased)" pra incluir o tq:

```markdown
### Em desenvolvimento (unreleased)

- **`plugadvpl compile --all-envs`** — compila pra todos os environments do `--use-server` em sequência (já mergeado em main)
- **`plugadvpl tq`** — Troca Quente MVP local: restart do AppServer (via `restart_cmd` configurado no server) + healthcheck HTTP. Resolve o passo manual que ainda existia depois do `compile --all-envs` (rodar `restart-totvs.bat` + curl loop). Issue [#5](https://github.com/JoniPraia/plugadvpl/issues/5) — escopo cortado pra MVP, versão robusta pra produção fica pra v0.15+
- **`plugadvpl compile --set-restart-cmd <server> --cmd "<cmd>"`** — flag nova no compile pra configurar o `restart_cmd` no registry global (consumido pelo `plugadvpl tq`)
```

- [ ] **Step 4: Adiciona entry no CHANGELOG**

Edita `CHANGELOG.md`. Procura `## [Unreleased]` e adiciona ANTES dos blocos existentes:

```markdown
### Added — `plugadvpl tq` (Troca Quente MVP local)

Restart do AppServer Protheus + healthcheck HTTP, automatizando o passo
manual que ainda existia depois do `compile --all-envs` (`restart-totvs.bat`
+ curl loop até voltar). Tipicamente usado encadeado:

```bash
plugadvpl compile --use-server Local --all-envs <fonte> && \
plugadvpl tq --use-server Local
```

Componentes:

- Campo novo `restart_cmd` no `Server` dataclass do registry global. Default
  `""`, backwards-compat com servers existentes.
- `plugadvpl compile --set-restart-cmd <server> --cmd "<cmd>"` — flag nova
  pra configurar o cmd no registry. Validação: `--set-restart-cmd` sem
  `--cmd` erra com mensagem clara.
- `plugadvpl tq` — novo subcomando. Flags: `--use-server`, `--timeout`
  (default 60s), `--no-healthcheck`, `--dry-run`.
- Healthcheck via `http.client.HTTPConnection` (GET `/`) considera AppServer
  up só quando responde HTTP 200/401/404. TCP-only daria false positive
  cedo demais (porta abre antes do REST estar pronto na build 7.00.x).
- 5xx no healthcheck NÃO conta como up — continua tentando até timeout.

13 testes novos (8 unit no `tq.py` + 5 integration do subcomando)
mais 3 integration do `--set-restart-cmd` (já no `test_cli_compile.py`).
Total 16 testes adicionados. Spec e plano em `docs/superpowers/specs/`
e `docs/superpowers/plans/`.

Escopo MVP cortou versionamento de RPO, edição de `appserver.ini` e
rollback automático — fica pra issue [#5](https://github.com/JoniPraia/plugadvpl/issues/5)
quando precisar da versão robusta pra produção.
```

- [ ] **Step 5: Run suite full final**

Run: `cd cli && uv run pytest --tb=short -q 2>&1 | tail -5`
Expected: `1044 passed` (mesmo do final da Task 13 — README/CHANGELOG não mudam testes).

- [ ] **Step 6: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs(tq): atualiza README + CHANGELOG pra plugadvpl tq

README: adiciona tq + --set-restart-cmd na tabela 'Runtime ADVPL',
atualiza 'Proximas entregas' (tq MVP entregue, plugadvpl-ops fica so
com apply-patch), bloco 'Em desenvolvimento' lista tq + --all-envs.

CHANGELOG: entry detalhada sob [Unreleased] documentando componentes,
escopo MVP vs issue #5 completa, testes novos (6 unit + 5 integration)."
```

---

### Task 16: Smoke real opcional (manual)

> **NÃO automatizado.** Documenta os comandos pra validação manual contra base local. Skip se não quiser smoke ao vivo.

**Pré-requisito:** AppServer local rodando em `http://127.0.0.1:8019`.

- [ ] **Step 1: Configura restart_cmd**

```bash
plugadvpl compile --set-restart-cmd Local --cmd "cmd.exe /c D:\\IA\\Projetos\\plugadvpl\\gaps\\restart-totvs.bat"
```

Expected: `restart_cmd setado pra 'Local': 'cmd.exe /c ...'`

- [ ] **Step 2: Dry-run pra confirmar config**

```bash
plugadvpl tq --use-server Local --dry-run
```

Expected: tabela mostrando `restart_cmd: cmd.exe /c ...` + `dry_run: True`. Exit 0. Sem restart real.

- [ ] **Step 3: Execução real**

```bash
plugadvpl tq --use-server Local
```

Expected: tabela mostrando `ok: True`, `restart_exit_code: 0`, `healthcheck_status: up`, `healthcheck_attempts: 15-20`, `total_duration_ms: ~15000-20000`. Exit 0. AppServer voltou.

- [ ] **Step 4: Validação via curl**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -u admin:admin http://127.0.0.1:8019/rest
```

Expected: HTTP 200/401/404 — algum status REST válido.

---

## Verificação final

- [ ] **Suite full verde:** `cd cli && uv run pytest --tb=short -q 2>&1 | tail -5` → `1044 passed`
- [ ] **Help do tq aparece:** `plugadvpl tq --help` mostra 4 flags
- [ ] **Help do compile mostra --set-restart-cmd:** `plugadvpl compile --help | grep restart`
- [ ] **README tem `tq` na tabela de runtime + atualiza Próximas entregas**
- [ ] **CHANGELOG `[Unreleased]` tem entry do tq**
- [ ] **Skill `skills/tq/SKILL.md` existe**
- [ ] **Smoke real (opcional)** passou contra base local

## Estimativa de tempo

Total: ~5h conforme spec. Distribuição:

- Tasks 1-2 (server field + flags compile): ~45min
- Task 3 (skeleton tq.py): ~10min
- Tasks 4-11 (TDD do tq.py — 6 testes): ~2h (15min por ciclo)
- Task 12 (subcomando CLI): ~30min
- Task 13 (integration tests): ~45min
- Tasks 14-15 (skill + docs): ~45min
- Task 16 (smoke real opcional): ~15min

---

## Skills relevantes pra execução

- @superpowers:test-driven-development — write test first, watch fail, implement minimal, watch pass
- @superpowers:executing-plans (se sem subagents) ou @superpowers:subagent-driven-development (se tiver)
- @superpowers:verification-before-completion — rode pytest E confirme número antes de marcar task como done
- @plugadvpl:advpl-encoding — se mexer em `.prw`/`.tlpp`, NÃO se aplica aqui (só Python)
