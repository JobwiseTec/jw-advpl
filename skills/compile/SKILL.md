---
description: Compila fonte ADVPL via plugadvpl (wrapper sobre advpls TOTVS). Workflow guiado pelo agente.
disable-model-invocation: true
arguments: [fonte]
allowed-tools: [Bash]
---

# `/plugadvpl:compile`

> 🤖 **Para o agente**: este skill tem um **workflow obrigatório de 4 passos**.
> NUNCA tente compilar direto. Sempre rode `--doctor` primeiro.

## Workflow obrigatório

### Passo 1 — Diagnóstico (sempre primeiro)

```bash
plugadvpl --format json compile --doctor
```

Output traz `status` (`ready` | `needs_setup`) e `next_actions` (lista ordenada do que falta).

### Passo 2 — Se `needs_setup`: processar cada `next_action`

Para cada item em `next_actions`, agir conforme `action`:

#### `set_advpls_binary`
- **Se `candidates` não-vazio**: mostre candidates ao usuário e pergunte qual usar
- **Se vazio**: peça o path do `advpls.exe`. Se usuário não tem, ofereça baixar:
  ```powershell
  # Windows
  Invoke-WebRequest "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/TOTVS/vsextensions/tds-vscode/latest/vspackage" -OutFile tds-vscode.vsix
  Expand-Archive tds-vscode.vsix -DestinationPath tds-vscode/
  # advpls fica em: tds-vscode/extension/node_modules/@totvs/tds-ls/bin/windows/advpls.exe
  ```
  ```bash
  # Linux/macOS — ajuste 'linux'→'mac' se macOS
  curl -L -o tds.vsix "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/TOTVS/vsextensions/tds-vscode/latest/vspackage"
  unzip -q tds.vsix -d tds-vscode/
  chmod +x tds-vscode/extension/node_modules/@totvs/tds-ls/bin/linux/advpls
  ```
- **Salvar**: `export PLUGADVPL_ADVPLS_BINARY=<path>` OU editar `[tds_ls].binary` no `runtime.toml`

#### `set_includes`
- **Se `candidates` não-vazio**: mostre ao usuário ("Detectei estas pastas com PRTOPDEF.CH e protheus.ch, qual usar?")
- **Se vazio**: peça o path da pasta `Include/` Protheus. Se usuário não tem (sem AppServer/SDK), informe que `--mode appre` não funciona — apenas `--mode cli` (que compila no AppServer remoto)
- **Salvar**: passar via `--includes <path>` nas próximas execuções OU editar `[compile].includes = ["<path>"]` no `runtime.toml`

#### `create_runtime_toml`
- Rode: `plugadvpl compile --init-config`
- Edite `<root>/.plugadvpl/runtime.toml` preenchendo:
  - `[tds_ls].binary` — path do advpls
  - `[appserver]` — host, port, build, environment do AppServer alvo
  - `[auth]` — `user_env`/`password_env` (nome das env vars, NUNCA valor)
  - `[compile].includes` — pasta com includes
- Mostre o conteúdo final ao usuário pra confirmação ANTES de gravar

#### `set_env_var`
- **Se `secret: true`** (PROTHEUS_PASS): **NUNCA** logue valor. Oriente:
  ```bash
  $env:PROTHEUS_PASS = "<sua-senha>"   # PowerShell
  export PROTHEUS_PASS='<sua-senha>'   # bash
  ```
- **Se `secret: false`** (PROTHEUS_USER): pode pedir valor direto ao user
- Em CI use secrets (GitHub Actions / GitLab CI variables)

#### `start_appserver`
- Não temos controle programático. Informe ao usuário:
  - Local: iniciar `appserver.exe` na pasta Protheus
  - Remoto: subir SSH tunnel `ssh -L 1234:localhost:1234 user@host -N` + `host = "127.0.0.1"` no `runtime.toml`

### Passo 3 — Re-rodar `--doctor` até `status = "ready"`

```bash
plugadvpl --format json compile --doctor
```

Loop: cada vez que resolver um `next_action`, re-rode pra confirmar e ver se sobrou mais alguma coisa.

### Passo 4 — Compilar

Quando `status: "ready"`, o `mode_supported` diz quais modos funcionam:

- **Só `appre`** (sem AppServer): `plugadvpl compile --mode appre --includes <pasta> FONTE.PRW`
- **Inclui `cli`**: pode escolher `--mode cli` (full compile semântico) ou `--mode appre` (rápido)

**Convenção crítica**: flags `--xxx` **SEMPRE antes** do nome do arquivo (positional variadic).

```bash
# ✅ Certo
plugadvpl --format json compile --mode appre --includes "D:\Protheus\Include" MEUFONTE.PRW

# ❌ Errado (typer consome --mode como nome de arquivo)
plugadvpl compile MEUFONTE.PRW --mode appre
```

## Quando NÃO usar este skill

- Para entender erros de **lint** (não-compile): use `/plugadvpl:lint`
- Para visão arquitetural ANTES de compilar: `/plugadvpl:arch <arquivo>`
- Para descobrir quem chama uma função: `/plugadvpl:callers <funcao>`

## Schema do output de `compile` (não `--doctor`)

```json
{
  "rows": [
    {"arquivo", "ok", "mode", "duration_ms", "exit_code",
     "counts": {"error", "warning", "info", "unknown"},
     "diagnostics": [{"severidade", "arquivo", "linha", "coluna",
                      "mensagem", "codigo", "raw"}]}
  ],
  "next_steps": [...]
}
```

Bucket `__unmatched__` aparece se advpls reportar arquivo fora do `requested_files`.

## Exit codes

- `0` — sucesso (zero errors)
- `1` — error parseado OU subprocess falhou
- `2` — config/setup inválido OU `--doctor` retornou `needs_setup`
- `130` — `Ctrl-C` (POSIX SIGINT)

## Modos — limitações importantes

| Modo | Pega | NÃO pega |
|---|---|---|
| `appre` | sintaxe básica, `#include` faltando, macro inválida, define duplicado | erros semânticos (`If` sem `EndIf`, tipo incompatível, função inexistente) |
| `cli` | tudo (pré-processador + semântica + binding) — full compile | nada relevante |

Pra usuário aprender ADVPL via plugin, `appre` já entrega 60% do valor (`C2090`/`C2006`/`C2090` família). Pra CI rigoroso, exigir `cli`.

## Documentação completa

[`docs/setup-compile.md`](docs/setup-compile.md) — guia passo-a-passo de
instalação (binário, includes, AppServer, CI YAML pronto, SSH tunnel,
6 troubleshooting comuns).
