# `plugadvpl tq` — Troca Quente (MVP local) — Design

**Status:** Approved (brainstorming session 2026-05-25)
**Issue:** [#5](https://github.com/JoniPraia/plugadvpl/issues/5) — escopo cortado pro MVP local
**Próximo passo:** plano de implementação (writing-plans)

---

## Contexto

Hoje, depois de `plugadvpl compile`, o usuário ainda precisa rodar manualmente o `restart-totvs.bat` (ou equivalente Linux: `systemctl restart totvs-appserver12`) e esperar o AppServer voltar antes de testar. Isso bateu real durante o smoke do `coletadb.tlpp` v1.0.3 — várias iterações de "edita .tlpp → compile → restart manual → curl pra ver se subiu" e cada restart manual quebra o flow do agente.

A issue #5 propõe a feature completa de Troca Quente: promote de RPO versionado, edição de `appserver.ini`, healthcheck, rollback, lock file, `--confirm-prod`, sub-plugin `plugadvpl-ops` separado. ~10 dias de trabalho.

Este spec corta o escopo radical pro **MVP útil pra testar coisas localmente** — só restart + healthcheck. O resto fica pra issue #5 quando precisar do TQ robusto pra produção.

## Decisões (brainstorming 2026-05-25)

1. **Escopo:** MVP local testing. Sem versionamento, sem `.ini` editing, sem PROD-safety, sem sub-plugin separado.
2. **Ações:** restart + healthcheck. `--all-envs` já resolve a parte de copiar RPO pros múltiplos envs.
3. **Storage do `restart_cmd`:** campo novo em `Server` dataclass de `~/.plugadvpl/servers.json`. Cada server tem o seu cmd.
4. **Healthcheck:** TCP ping na porta do server (HTTP 200/401/404 = up). Mesma estratégia do `until curl ...` que já provou funcionar no smoke do coletadb.
5. **CLI:** subcomando standalone `plugadvpl tq`. Vive no core (sem sub-plugin separado).

## Componentes

### 1. `Server.restart_cmd` — novo campo

Adicionar à dataclass `Server` em `cli/plugadvpl/compile_servers.py`:

```python
@dataclass(frozen=True)
class Server:
    # ... campos existentes ...
    restart_cmd: str = ""    # v0.14: shell command pra restart do AppServer
```

- Vazio = não configurado → `plugadvpl tq` aborta com hint pro `--set-restart-cmd`.
- Persistido no JSON do registry — fica disponível pra qualquer projeto no mesmo `host:user`.
- Lido por `tq.py` via `compile_servers.get_server(name).restart_cmd`.

### 2. `plugadvpl compile --set-restart-cmd <server>` + `--cmd "<command>"` — duas flags coordenadas

Optei por **2 flags separadas** em vez de `tuple[str, str]` (que é não-padrão e cria UX ambígua). Padrão consistente com outras "--set-*" do compile:

```python
@app.command("compile")
def compile_cmd(
    # ...
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
            help='Comando shell (usado com --set-restart-cmd). Ex: "cmd.exe /c restart.bat"',
        ),
    ] = "",
    # ...
):
    if set_restart_cmd:
        if not cmd_value:
            typer.secho("--set-restart-cmd requer --cmd '<comando>'", fg=RED, err=True)
            raise typer.Exit(2)
        _handle_set_restart_cmd(set_restart_cmd, cmd_value)
        return
```

Uso:

```bash
plugadvpl compile --set-restart-cmd Local --cmd "cmd.exe /c gaps\\restart-totvs.bat"
plugadvpl compile --set-restart-cmd dev-linux --cmd "sudo systemctl restart totvs-appserver12"
```

`_handle_set_restart_cmd(server_name, cmd)`:
1. Busca server no registry via `get_server(server_name)`.
2. Erra com mensagem clara se não existir + lista servers via `--list-servers`.
3. Reescreve o `Server` (dataclass frozen — uso `replace(server, restart_cmd=cmd)`).
4. Persiste o registry via `save_registry()`.
5. Echo de confirmação: `restart_cmd setado pra '<server>': '<cmd>'`.

Adicionar `--set-restart-cmd` + `--cmd` à lista `suspicious_flags` no `compile` pra catch positional reordering errors.

### 3. `plugadvpl tq` — novo subcomando

```python
@app.command("tq")
def tq_cmd(
    ctx: typer.Context,
    use_server: Annotated[str, typer.Option("--use-server", help="Server do registry")] = "",
    timeout: Annotated[int, typer.Option("--timeout", help="Timeout do healthcheck em segundos")] = 60,
    no_healthcheck: Annotated[bool, typer.Option("--no-healthcheck", help="Só executa restart_cmd, pula healthcheck")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Mostra o que faria, não executa")] = False,
) -> None:
    """Restart do AppServer + healthcheck (Troca Quente — MVP local)."""
    # ...
```

> **Formato de saída:** o `tq` honra `--format json` do contexto global do CLI (mesmo
> padrão de `compile` e `ingest-protheus`). Não é flag local do `tq` — herda da
> opção root `plugadvpl --format json tq ...`. Render via `_render_from_ctx`.

Fluxo:

```
1. Valida --use-server passado (erro estruturado se vazio)
2. Resolve server via compile_servers.get_server(use_server)
3. Valida server.restart_cmd não vazio → erro com hint:
   "Configure: plugadvpl compile --set-restart-cmd <name> --cmd '<cmd>'"
4. Se --dry-run: imprime restart_cmd + healthcheck plan + return 0
5. Executa restart_cmd via subprocess.run(shell=True)
   - timeout = timeout + 10s pra dar margem
6. Se exit_code != 0:
   - Imprime restart_cmd + stderr capturado
   - Return TqResult(ok=False, error=...) com exit_code 1
7. Se --no-healthcheck: return TqResult(ok=True, healthcheck_status="skipped") sem loop
8. Healthcheck loop:
   - start_ts = monotonic()
   - attempts = 0
   - while monotonic() - start_ts < timeout:
     - sleep(1s) (exceto na primeira iteração)
     - attempts += 1
     - is_up, status = _http_probe(host, port, timeout=2.0)
     - se is_up E status in {200, 401, 404}: healthy=True, break
   - se !healthy: return TqResult(ok=False, healthcheck_status="timeout", error=...)
9. Render table/JSON + return TqResult(ok=True, healthcheck_status="up")
```

### 4. `cli/plugadvpl/tq.py` — módulo novo

```python
"""Troca Quente (MVP local) — restart + healthcheck do AppServer."""

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
    error: str  # vazio se ok=True


def run_tq(
    server: Server,
    timeout_s: int = 60,
    no_healthcheck: bool = False,
) -> TqResult:
    """Executa restart_cmd + healthcheck. Pure-ish: sem side effects além
    do subprocess (restart_cmd) + socket/http (healthcheck)."""
    # ... implementação ...


def _http_probe(host: str, port: int, timeout: float = 2.0) -> tuple[bool, int]:
    """Tenta GET / via http.client.HTTPConnection.

    Retorna (is_up, status_code):
    - is_up=True E status_code in {200, 401, 404} significa AppServer respondeu HTTP
    - is_up=False E status_code=0 significa socket falhou (TCP refused / timeout)
    - is_up=True E status_code 5xx significa porta abriu mas REST quebrou (raro)

    O caller checa o status pra decidir healthy vs not.
    """
    # ... implementação ...
```

`run_tq` é a função core, pure-ish (deterministic dado server + tempo de execução). `_http_probe` faz tanto o TCP connect quanto o HTTP GET — não há `_tcp_ping` separado.

Por que HTTP e não só TCP: na build 7.00.240223P observamos que a porta abre alguns segundos antes do REST estar pronto (processo iniciou mas WSRESTFUL ainda carregando). `200/401/404` é a prova real de "AppServer respondeu HTTP" — TCP-only daria false positive cedo demais.

### 5. Skill `skills/tq/SKILL.md` — wrapper Claude Code

Padrão dos outros wrappers:

```markdown
---
description: Restart do AppServer Protheus + healthcheck (Troca Quente local)
disable-model-invocation: true
arguments: [opcoes]
allowed-tools: [Bash]
---

# `/plugadvpl:tq`

Executa o `restart_cmd` configurado pro server e espera o AppServer voltar
(TCP ping na porta REST). MVP pra teste local — não faz versionamento, edição
de .ini ou rollback (issue #5 cobre a versão completa pra prod).

## Pré-requisito

Server cadastrado COM `restart_cmd` configurado:

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

## Execucao

\`\`\`bash
uvx plugadvpl@<versão-recente> tq $ARGUMENTS
\`\`\`
```

## Output

### Tabela (default)

```
tq (Local) → cmd.exe /c gaps\restart-totvs.bat
┌────────────┬────────┐
│ key        │ value  │
├────────────┼────────┤
│ ok         │ True   │
│ restart    │ 2341ms │
│ healthcheck│ up     │
│ attempts   │ 17     │
│ total      │ 18.2s  │
└────────────┴────────┘
```

### JSON (`plugadvpl --format json tq ...`)

```json
{
  "ok": true,
  "server_name": "Local",
  "restart_cmd": "cmd.exe /c gaps\\restart-totvs.bat",
  "restart_exit_code": 0,
  "restart_duration_ms": 2341,
  "restart_stderr": "",
  "healthcheck_status": "up",
  "healthcheck_attempts": 17,
  "healthcheck_duration_ms": 15876,
  "total_duration_ms": 18217,
  "error": ""
}
```

Schema estável, consumível por CI/agentes. `healthcheck_status` ∈ `{up, timeout, skipped, not_run}`.

## Erros estruturados

| Cenário | exit_code | error |
|---|---|---|
| `--use-server` não passado | 2 | "--use-server obrigatório" |
| Server não cadastrado | 2 | "server '<nome>' não cadastrado" |
| `restart_cmd` vazio | 2 | "server '<nome>' sem restart_cmd. Configure: plugadvpl compile --set-restart-cmd ..." |
| restart_cmd exit non-zero | 1 | "restart_cmd falhou (exit=N): <stderr>" |
| healthcheck timeout | 1 | "healthcheck timeout após <N>s" |

## Testes

### Unit (`cli/tests/unit/test_tq.py`)

Mock `subprocess.run` + `http.client.HTTPConnection`. Casos:

1. **happy path** — restart_cmd ok + healthcheck retorna (True, 200) no 3º ping → TqResult.ok=True, healthcheck_status="up", attempts=3
2. **restart_cmd vazio** — `run_tq(server_sem_cmd)` → TqResult.ok=False, error contém "restart_cmd"
3. **restart exit non-zero** — `subprocess.run` mock retorna `returncode=1` + stderr → TqResult.ok=False, restart_stderr capturado
4. **healthcheck timeout** — todos `_http_probe` retornam (False, 0) → TqResult.ok=False, healthcheck_status="timeout", attempts >= timeout/sleep_interval
5. **healthcheck false positive guard** — `_http_probe` retorna (True, 503) → não considera up, continua tentando
6. **--no-healthcheck** — `run_tq(server, no_healthcheck=True)` → ok=True, healthcheck_status="skipped", attempts=0

Total: 6 unit tests.

### Integration (`cli/tests/integration/test_cli_tq.py`)

Via `CliRunner`. Casos:

1. **tq sem --use-server** — exit 2 + mensagem "--use-server obrigatório"
2. **tq com server não existente** — exit 2 + hint pra `--list-servers`
3. **tq com server sem restart_cmd** — exit 2 + hint pro `--set-restart-cmd ... --cmd ...`
4. **tq --dry-run com server válido** — exit 0 + preview impresso (restart_cmd + healthcheck plan), sem chamar subprocess
5. **compile --set-restart-cmd + --cmd grava no registry** — exec o set, depois `get_server` confere `restart_cmd` populado
6. **compile --set-restart-cmd sem --cmd** — exit 2 + mensagem clara
7. **--format json no tq** — `plugadvpl --format json tq --use-server X --dry-run` produz JSON parseável com chaves esperadas

Total: 7 integration tests.

### Smoke real (manual, não automatizado)

Documentado em `gaps/local-test-env.md`:

```bash
# Setup uma vez
plugadvpl compile --set-restart-cmd Local --cmd "cmd.exe /c D:\\IA\\Projetos\\plugadvpl\\gaps\\restart-totvs.bat"

# Validação
plugadvpl compile --use-server Local --all-envs docs/reference-impl/coletadb.tlpp
plugadvpl tq --use-server Local
# espera ~15-20s
# verifica HTTP 200 em http://localhost:8019/rest
```

## Arquivos afetados

| Path | Mudança |
|---|---|
| `cli/plugadvpl/compile_servers.py` | Adiciona `restart_cmd: str = ""` ao `Server` |
| `cli/plugadvpl/cli.py` | Adiciona handler `--set-restart-cmd` ao `compile`; adiciona subcomando `tq` |
| `cli/plugadvpl/tq.py` | **NOVO** — `run_tq()` + `_http_probe()` + `TqResult` |
| `cli/tests/unit/test_tq.py` | **NOVO** — 6 casos unit |
| `cli/tests/integration/test_cli_tq.py` | **NOVO** — 7 casos integration |
| `skills/tq/SKILL.md` | **NOVO** — slash command wrapper (padrão skill-as-command do projeto, `disable-model-invocation: true`). NÃO há diretório `commands/` separado neste projeto |
| `CHANGELOG.md` | Entry em `[Unreleased]` |
| `README.md` | Adiciona `tq` à tabela "Runtime ADVPL — edit + compile"; ajusta seção "Próximas entregas" pra refletir que MVP foi entregue |

## Backwards compatibility

- Servers existentes sem `restart_cmd` continuam funcionando — o campo é opcional, default `""`.
- `--set-restart-cmd` é flag nova, não muda nenhum comportamento existente do `compile`.
- Schema JSON do `tq` é nova superficie, não conflita com nada.

## O que NÃO entra (vs issue #5 original)

| Feature | Por que cortou |
|---|---|
| Promote de RPO versionado (`apo/<env>/rpo_versions/<ts>/`) | `--all-envs` já copia pros 2 envs. Pra MVP local, histórico não importa |
| Update de `appserver.ini` (`RPOCustom=`) | Não muda nessa estratégia — RPO sobrescreve o ativo |
| Lock file (`~/.plugadvpl/locks/<env>.lock`) | Local, 1 dev — sem concorrência |
| `--confirm-prod` + `is_prod` em servers.json | Local, sem PROD |
| `--list-versions` + `--rollback` | Sem versionamento, sem rollback |
| `deploys_history` table no schema SQLite | Sem auditoria pra MVP |
| Sub-plugin `plugadvpl-ops` separado | Adiciona scaffold (pyproject, CI, release pipeline) que não justifica pro MVP. Migra depois se issue #5 completa entrar |
| Chaos tests (força falha em cada step) | Sem rollback, sem chaos test que faz sentido |
| Agent `advpl-deploy-orchestrator` | Pode vir em release separado se justificar |

Issue #5 fica aberta — documenta que TQ "completo" virá em v0.15+ quando precisar.

## Esforço estimado

- `restart_cmd` field em `Server` + `--set-restart-cmd` + `--cmd` handler + validação suspicious_flags: ~45min
- `tq.py` core (`run_tq`, `_http_probe`, `TqResult`): ~1.5h
- Subcomando CLI + render_from_ctx integration: ~30min
- 13 testes (6 unit + 7 integration) com mocks pra subprocess + http.client: ~1.5h
- Skill + README + CHANGELOG entries: ~45min
- Smoke real validation contra base local: ~30min

**Total: ~5h**.

Ajustado pra cima do estimate original (3-4h) considerando que mocks de subprocess + `http.client.HTTPConnection` pra 6 unit cases dão mais trabalho que reconheci na primeira passada.

## Riscos

| Risco | Mitigação |
|---|---|
| `subprocess.run(shell=True)` em Windows tem cotações estranhas | Documentar exemplo bom no `--set-restart-cmd` help; testar com `cmd.exe /c ...` no smoke |
| Healthcheck false positive (porta abre mas AppServer ainda inicializa) | HTTP status check (não só TCP) — `200/401/404` significa AppServer respondeu |
| Healthcheck false negative (AppServer demora > 60s) | Timeout configurável via `--timeout` |
| User configurou `restart_cmd` errado, `tq` derruba o servidor | Documentação clara: `--dry-run` mostra o cmd antes; user valida visualmente |
| Server tem N envs mas restart_cmd reinicia o AppServer inteiro | OK por design — local restart é do processo todo, não por-env |

## Próximas iterações (não pra este MVP)

- **v0.15:** issue #5 completa (sub-plugin `plugadvpl-ops`, promote versionado, .ini editing, rollback, lock file, PROD safety)
- **Após v0.15:** agent `advpl-deploy-orchestrator` que orquestra `compile --all-envs && tq && smoke`
- **Bonus:** flag `plugadvpl compile --then-tq` chamando o `tq` pós-compile no mesmo fluxo

## Validação de aprovação

✅ Brainstorming session 2026-05-25 — usuário aprovou:

- Escopo: "Local testing (recomendado)"
- Ações: "Restart + healthcheck (MÍNIMO)"
- Storage cmd: "Campo novo em servers.json (recomendado)"
- Healthcheck: "TCP ping na porta REST (recomendado)"
- Interface CLI: "Subcomando standalone `plugadvpl tq` (recomendado)"
- Design completo apresentado e aprovado verbalmente ("pode seguir")
