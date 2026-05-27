---
description: Encadeia compile → tq → smoke num único flow guiado. Use quando o usuário pede "deploya esse fonte", "compila e restarta", ou termina edit-prw e quer ver o efeito no AppServer.
disable-model-invocation: true
arguments: [fonte ou opções]
allowed-tools: [Bash]
---

# `/plugadvpl:deploy`

Orquestra o ciclo completo de dev: **compila o fonte, restarta o AppServer e (opcionalmente) confere se o REST voltou**. Não é um subcomando novo — é um wrapper instrutivo sobre [`/plugadvpl:compile`](../compile/SKILL.md) + [`/plugadvpl:tq`](../tq/SKILL.md) que evita o usuário ter que lembrar os 3 passos e os encadeamentos com `&&`.

## Quando usar

- Acabou de editar um `.prw`/`.tlpp` e quer ver no AppServer.
- Terminou um ciclo `edit-prw` e precisa publicar.
- Roda smoke contra um endpoint REST e o AppServer subiu antes do REST estar pronto.

## Quando NÃO usar

- Só compilar sem restartar → use [`/plugadvpl:compile`](../compile/SKILL.md).
- Só restartar (já compilou em outra janela) → use [`/plugadvpl:tq`](../tq/SKILL.md).
- Deploy PROD-grade com rollback automático e versionamento de RPO → **não existe** no plugin. Foi descartado conscientemente ([issue #5 comment](https://github.com/JoniPraia/plugadvpl/issues/5#issuecomment-4553802738)). Pra esse caso, escreva um `restart_cmd` que faça o rollback dentro do próprio cmd (ex: `restart-com-fallback.bat` que detecta falha e restaura RPO anterior).

## Workflow (3 passos)

### Passo 1 — Pré-flight

Verifique que tanto `compile` quanto `tq` estão configurados:

```bash
plugadvpl --format json compile --doctor
plugadvpl compile --list-servers
```

O server alvo precisa ter `restart_cmd` setado. Se aparecer vazio, configure antes:

```bash
plugadvpl compile --set-restart-cmd <server> --cmd "<cmd do restart>"
```

Ex. Windows: `"cmd.exe /c gaps\\restart-totvs.bat"`
Ex. Linux: `"sudo systemctl restart totvs-appserver12"`

### Passo 2 — Compile + restart encadeados

```bash
plugadvpl compile --use-server <server> --all-envs <fonte> && \
plugadvpl tq --use-server <server>
```

Importante:

- O `&&` garante que **só restarta se compilar limpo**. Compile com erro aborta o flow, AppServer fica intacto.
- `--all-envs` é recomendado quando o server tem múltiplos environments (típico: `protheus` + `protheus_rest`) — RPO sai sincronizado entre eles.
- Se o REST do AppServer roda numa porta diferente do TCP do `advpls`, passe `--port` no `tq`:
  ```bash
  plugadvpl tq --use-server Local --port 8019
  ```

### Passo 3 — Smoke (opcional)

Se tem endpoint REST custom pra testar, valide depois do `tq` voltar:

```bash
curl -s http://<host>:<port>/rest/<endpoint> | jq .
```

Se quebrou:
1. Confere `console.log` do AppServer (path em `appserver.ini` → `[General].ConsoleFile`).
2. `plugadvpl log-diagnose <console.log>` pra rodar a KB de 93 correction tips.

## Padrões de erro

| Sinal | Provável causa | Fix |
|---|---|---|
| `compile` exit 1 com `C2xxx` | erro de sintaxe / include faltando | `/plugadvpl:compile` mostra diagnóstico, edita fonte e repete |
| `tq` exit 1 com `restart_exit_code != 0` | `restart_cmd` falhou (permissão, path errado) | rode o cmd manual pra ver erro completo |
| `tq` exit 1 com `healthcheck timeout` | AppServer demorou pra subir / porta REST diferente | aumente `--timeout` ou ajuste `--port` |
| smoke 500 mas `tq` ok | bug no fonte que compilou mas estoura em runtime | `log-diagnose` no `console.log` |

## Exemplo completo

Cenário real: ajustar `coletadb.tlpp`, publicar nos 2 envs, validar `/rest/coletadb/ping`:

```bash
# 1. Compile + restart
plugadvpl compile --use-server Local --all-envs docs/reference-impl/coletadb.tlpp && \
plugadvpl tq --use-server Local --port 8019

# 2. Smoke
curl -s http://127.0.0.1:8019/rest/coletadb/ping
```

Se o smoke der 200, deploy ok. Qualquer fail anterior aborta a cadeia.

## Skills relacionadas

- [`/plugadvpl:compile`](../compile/SKILL.md) — passo 1 isolado
- [`/plugadvpl:tq`](../tq/SKILL.md) — passo 2 isolado
- [`/plugadvpl:edit-prw`](../edit-prw/SKILL.md) — fluxo de edição antes do deploy (preserva encoding CP1252)
- [`/plugadvpl:log-diagnose`](../log-diagnose/SKILL.md) — troubleshoot pós-deploy
