---
description: Troca Quente (MVP local) — restart do AppServer Protheus + healthcheck HTTP. Use quando precisar restartar o AppServer após `compile` e esperar voltar pra testar.
disable-model-invocation: true
arguments: [opcoes]
allowed-tools: [Bash]
---

# `/plugadvpl:tq`

Executa o `restart_cmd` configurado pro server (registry global) e espera o AppServer voltar via healthcheck HTTP (GET `/` retornando 200/401/404).

MVP pra testes locais — não faz versionamento de RPO, edição de `.ini` ou rollback. Esse escopo PROD-grade foi descartado conscientemente; quem precisa de rollback escreve um `restart_cmd` que faça isso ([análise completa na issue #5](https://github.com/JoniPraia/plugadvpl/issues/5#issuecomment-4553802738)).

Pra encadear `compile → tq → smoke` num passo só, use [`/plugadvpl:deploy`](../deploy/SKILL.md).

## Pré-requisito

Server cadastrado com `restart_cmd` configurado:

```bash
plugadvpl compile --set-restart-cmd Local --cmd "cmd.exe /c gaps\\restart-totvs.bat"
```

## Uso

```
/plugadvpl:tq --use-server <nome>
/plugadvpl:tq --use-server <nome> --timeout 120
/plugadvpl:tq --use-server <nome> --no-healthcheck
/plugadvpl:tq --use-server <nome> --dry-run
```

## Argumentos

- `--use-server NAME` — nome do server no registry. **Obrigatório**.
- `--port N` — override da porta pro healthcheck. Default usa `server.port`, mas se o REST do AppServer roda em porta diferente do TCP do `advpls` (caso típico: TCP=1234, REST=8019), passe o `--port`.
- `--timeout N` — timeout do healthcheck em segundos (default 60).
- `--no-healthcheck` — só roda o `restart_cmd`, pula o loop de healthcheck.
- `--dry-run` — mostra o que faria sem executar.
- `--confirm-prod` — obrigatório quando o server está marcado como produção (via `plugadvpl compile --mark-prod <server>`). Evita restart acidental em PROD.

## Execucao

```bash
uvx plugadvpl@0.28.0 tq $ARGUMENTS
```

## Encadeamento típico

Depois de compilar pra vários envs com `--all-envs`, restartar:

```bash
plugadvpl compile --use-server Local --all-envs <fonte> && \
plugadvpl tq --use-server Local
```

## Erros comuns

- **`--use-server obrigatório`** — passe `--use-server <nome>`
- **`server '<nome>' não cadastrado`** — registry vazio ou nome errado. Rode `plugadvpl compile --list-servers`
- **`server '<nome>' sem restart_cmd`** — configure: `plugadvpl compile --set-restart-cmd <nome> --cmd "<cmd>"`
- **`restart_cmd falhou (exit=N)`** — o shell command retornou non-zero; verifique stderr no output
- **`healthcheck timeout`** — AppServer não voltou em N segundos. Aumente `--timeout` ou verifique manualmente
