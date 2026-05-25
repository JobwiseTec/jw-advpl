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

### 2. `plugadvpl compile --set-restart-cmd <server> "<cmd>"` — nova flag

Mesma família das outras `--set-credentials`/`--set-*`. Implementação:

```python
@app.command("compile")
def compile_cmd(
    # ...
    set_restart_cmd: Annotated[
        tuple[str, str] | None,
        typer.Option(
            "--set-restart-cmd",
            help='Configura restart_cmd do server: --set-restart-cmd <nome> "<cmd>"',
        ),
    ] = None,
    # ...
):
    if set_restart_cmd:
        server_name, cmd = set_restart_cmd
        _handle_set_restart_cmd(server_name, cmd)
        return
```

`_handle_set_restart_cmd(server_name, cmd)`:
1. Busca server no registry.
2. Erra com mensagem clara se não existir.
3. Reescreve o `Server` com `restart_cmd=cmd`.
4. Salva o registry.
5. Echo de confirmação: `restart_cmd setado pra '<server>': '<cmd>'`.

**Tem CSV-edge-case:** typer aceita tuple[str, str] via 2 positional args. Validar isso na implementação — pode ser que precise duas flags ou um único arg `"<nome>:<cmd>"`. Decidir no PR.

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

Fluxo:

```
1. Valida --use-server passado (erro estruturado se vazio)
2. Resolve server via compile_servers.get_server(use_server)
3. Valida server.restart_cmd não vazio → erro com hint:
   "Configure: plugadvpl compile --set-restart-cmd <name> '<cmd>'"
4. Se --dry-run: imprime restart_cmd + healthcheck plan + return 0
5. Pre-flight: TCP ping inicial (informativo, registra was_up=True/False)
6. Executa restart_cmd via subprocess.run(shell=True)
   - timeout = timeout + 10s pra dar margem
7. Se exit_code != 0:
   - Imprime restart_cmd + stderr capturado
   - Return TqResult(ok=False, error=...) com exit_code 1
8. Se --no-healthcheck: return TqResult(ok=True) sem loop
9. Healthcheck loop:
   - start_ts = monotonic()
   - while monotonic() - start_ts < timeout:
     - sleep(1s)
     - try: socket.create_connection((host, port), timeout=2)
       - http_status = quick GET pra "/" via httplib
       - if status in {200, 401, 404}: break, healthy=True
   - if !healthy: return TqResult(ok=False, error="healthcheck timeout") com exit_code 1
10. Render table/JSON + return TqResult(ok=True)
```

### 4. `cli/plugadvpl/tq.py` — módulo novo

```python
"""Troca Quente (MVP local) — restart + healthcheck do AppServer."""

import socket
import subprocess
import time
from dataclasses import dataclass, asdict
from typing import Literal

from plugadvpl.compile_servers import Server


HealthcheckStatus = Literal["up", "timeout", "skipped"]


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
    was_up_before: bool
    error: str  # vazio se ok=True


def run_tq(
    server: Server,
    timeout_s: int = 60,
    no_healthcheck: bool = False,
) -> TqResult:
    """Executa restart_cmd + healthcheck. Pure function, sem side effects além
    do subprocess + socket."""
    # ... implementação ...


def _tcp_ping(host: str, port: int, timeout: float = 2.0) -> bool:
    """Tenta abrir socket TCP. Retorna True se conectou + recebeu algo HTTP-like."""
    # ... implementação ...
```

`run_tq` é a função core, pure-ish (deterministic dado server + tempo de execução).

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
plugadvpl compile --set-restart-cmd Local "cmd.exe /c gaps\\restart-totvs.bat"
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

### JSON (`--format json`)

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
  "was_up_before": true,
  "error": ""
}
```

Schema estável, consumível por CI/agentes.

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

Mock `subprocess.run` + `socket.create_connection`. Casos:

1. **happy path** — restart_cmd ok + healthcheck ok no 3º ping
2. **restart_cmd vazio** — server sem restart_cmd → TqResult.ok=False, error apropriado
3. **restart exit non-zero** — subprocess retorna exit=1 → TqResult.ok=False, captura stderr
4. **healthcheck timeout** — todos os pings falham → TqResult.ok=False, healthcheck_status="timeout"
5. **--no-healthcheck** — pula loop, retorna ok=True direto pós-restart
6. **--dry-run** — não executa restart_cmd, retorna preview

### Integration (`cli/tests/integration/test_cli_tq.py`)

Via `CliRunner`. Casos:

1. **tq sem --use-server** — exit 2 + mensagem
2. **tq com server não existente** — exit 2 + hint
3. **tq com server sem restart_cmd** — exit 2 + hint pro `--set-restart-cmd`
4. **tq --dry-run com server válido** — exit 0 + preview impresso
5. **compile --set-restart-cmd grava no registry corretamente** — read back confere
6. **tq --format json** — output válido + schema esperado

### Smoke real (manual, não automatizado)

Documentado em `gaps/local-test-env.md`:

```bash
# Setup uma vez
plugadvpl compile --set-restart-cmd Local "cmd.exe /c D:\\IA\\Projetos\\plugadvpl\\gaps\\restart-totvs.bat"

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
| `cli/plugadvpl/tq.py` | **NOVO** — `run_tq()` + `_tcp_ping()` + `TqResult` |
| `cli/tests/unit/test_tq.py` | **NOVO** — 6 casos unit |
| `cli/tests/integration/test_cli_tq.py` | **NOVO** — 6 casos integration |
| `skills/tq/SKILL.md` | **NOVO** — wrapper slash command |
| `commands/tq.md` | **NOVO** — claude code slash command file (se padrão exigir) |
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

- `restart_cmd` field + `--set-restart-cmd` handler: ~30min
- `tq.py` core (run_tq, _tcp_ping, TqResult): ~1h
- Subcomando CLI + flag parsing: ~30min
- 12 testes (6 unit + 6 integration): ~1h
- Skill + slash command + README + CHANGELOG: ~30min
- Smoke real validation: ~30min

**Total: ~3-4h**.

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
