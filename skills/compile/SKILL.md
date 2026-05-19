---
description: Compila fonte ADVPL via plugadvpl (wrapper sobre advpls TOTVS)
disable-model-invocation: true
arguments: [fonte]
allowed-tools: [Bash]
---

# `/plugadvpl:compile`

Compila fonte ADVPL/TLPP via wrapper sobre o binário oficial `advpls` (TOTVS).
Devolve JSON estruturado pronto pra CI consumir.

## Uso

```
/plugadvpl:compile <fonte.prw> [--mode auto|appre|cli] [--includes <path>]
                               [--changed-since <git-ref>] [--no-warnings]
```

> ⚠️ Flags **antes** do nome do arquivo (convenção UNIX, `nargs=-1` variadic).

## Modos

- **`appre`** — pré-processador local (sem AppServer). Pega: include faltando, sintaxe básica, macro inválida. **Não pega**: erro semântico (`If` sem `EndIf`, tipo incompatível). Rápido (~60ms/fonte). Precisa do binário `advpls` + includes Protheus reais.
- **`cli`** — full compile via AppServer TCP. Pega tudo. Precisa de `runtime.toml` + credenciais via env var + AppServer rodando.
- **`auto`** (default) — `cli` se AppServer responde + `runtime.toml` válido; senão `appre`.

## Execução

```bash
uvx plugadvpl --format json compile --mode appre --includes "$PROTHEUS_INCLUDES" $ARGUMENTS
```

Onde `$PROTHEUS_INCLUDES` é a pasta com os `.ch` reais do Protheus
(`PRTOPDEF.CH`, `protheus.ch` etc.). Sem includes, falha com `C2090`.

## Pré-requisitos

Setup detalhado em [`docs/setup-compile.md`](docs/setup-compile.md). Resumo:

| Item | Onde obter | Necessário em |
|---|---|---|
| Binário `advpls` | Extensão TDS-VSCode (`.vsix` do Marketplace) | appre + cli |
| Includes Protheus (~1.100 `.ch`) | Instalação AppServer/SDK TOTVS | appre + cli |
| AppServer rodando | Servidor local ou VPS + SSH tunnel | cli |
| Credenciais env var | `PROTHEUS_USER` + `PROTHEUS_PASS` | cli |
| `runtime.toml` | `plugadvpl compile --init-config` | cli (não obrigatório no appre) |

## Schema do output JSON

```json
{
  "rows": [
    {
      "arquivo": "FOO.PRW",
      "ok": true,
      "mode": "appre",
      "duration_ms": 62,
      "exit_code": 0,
      "counts": {"error": 0, "warning": 0, "info": 0, "unknown": 0},
      "diagnostics": []
    }
  ],
  "next_steps": [...]
}
```

Cada `diagnostic` tem 7 campos: `severidade` (error|warning|info|unknown),
`arquivo`, `linha`, `coluna`, `mensagem`, `codigo` (ex: `C2090`), `raw`.

Bucket `__unmatched__` aparece se o advpls reportar diagnostic com arquivo
fora do `requested_files`.

## Exit codes

- `0` — sucesso (zero errors)
- `1` — error parseado OU subprocess falhou
- `2` — config/setup inválido (`runtime.toml` ausente em `--mode cli`, env var faltando, binário não encontrado)
- `130` — `Ctrl-C` (POSIX SIGINT)

## Troubleshooting rápido

| Sintoma | Causa | Fix |
|---|---|---|
| `Error C2090 File not found PRTOPDEF.CH` | Includes não chegaram ao advpls | Passar `--includes <pasta-Protheus>` |
| `advpls not found in PATH` | Binário não detectado | Setar `PLUGADVPL_ADVPLS_BINARY` ou `[tds_ls].binary` no `runtime.toml` |
| `nenhum fonte informado` (exit 2) | Flag depois do arquivo | Sempre `compile [OPTIONS] <fontes...>` |
| `appre` ignora `If` sem `EndIf` | `appre` é só pré-processador | Use `--mode cli` |

Guia completo de erros: [`docs/setup-compile.md` §Troubleshooting](docs/setup-compile.md#troubleshooting).
