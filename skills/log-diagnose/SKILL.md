---
description: Diagnosticar logs Protheus (console.log, error.log, profile.log, compila.log) — 19 alert rules + 93 correction tips com URL TDN oficial.
disable-model-invocation: true
arguments: [paths]
allowed-tools: [Bash]
---

# `/plugadvpl:log-diagnose`

Diagnostica arquivos de log Protheus em um único comando. Pipeline em 2 estágios:

1. **Stage 1 (top-down)** — quebra o log em **eventos** delimitados por 1 dos 4 formatos de header reconhecidos (ISO+thread, THREAD ERROR PT-BR, `[DD/MM HH:MM:SS]`, `[SEVERITY]`).
2. **Stage 2 (bottom-up, short-circuit)** — aplica 19 alert rules em ordem reversa (eventos MAIS RECENTES primeiro), enriquece findings com **correction tip + URL TDN oficial** vindos do catálogo de 93 tips.

## Uso

```
/plugadvpl:log-diagnose [paths] [--severity critical|warning|info] [--category CAT] [--rule RULE] [--since 30m|24h|7d]
```

## Opções principais

- `--severity <nivel>` — só findings da severidade indicada
- `--category <cat>` — uma das 12 categorias (`database`, `thread_error`, `rpo`, `network`, `connection`, `service`, `rest_api`, `compilation`, `authentication`, `shutdown`, `lifecycle`, `application`)
- `--rule <id>` — só uma rule específica (ex: `LOG-DB-ORA`, `LOG-THREAD-ERROR`)
- `--arquivo <nome>` — filtra por basename do log
- `--since <janela>` — relativa ao **último timestamp do log**, não ao wall clock (ex: `24h` = últimas 24h dentro do log)
- `--max-findings N` — cap (default 1000)
- `--force` — re-ingere mesmo se hash+mtime baterem (ignora cache)
- `--no-diagnose` — só faz ingest (sem rodar match)

## Discovery

Sem args, auto-discover em `--root` via globs:

```
*console*.log  *error*.log  *profile*.log  *compila*.log  *appserver*.log
```

Cobre prefixos comuns: `dev_console.log`, `prd-error.log`, `compila.log`, etc.

## Execução

```bash
uvx plugadvpl@0.44.0 --format md log-diagnose $ARGUMENTS
```

> **Para agente IA:** prefira `--format md` ou `--format json` — o default `table` trunca colunas em terminais estreitos. Flags `--format`/`--quiet`/`--limit` são GLOBAIS e vêm ANTES do subcomando.

## Formatos de header reconhecidos

| # | Padrão | Exemplo |
|---|---|---|
| 1 | ISO 8601 + thread_id | `2026-05-21T08:15:00.123-03:00 1648\| ...` |
| 2 | THREAD ERROR PT-BR | `THREAD ERROR ([31716], TIRETPIN, THIS)   06/05/2026   22:42:06` |
| 3 | Timestamp PT-BR isolado | `[06/05/2026 22:42:06] ...` |
| 4 | Severity bracket | `[ERROR] AppServer fail to start` |

Cada evento começa com 1 desses headers; linhas subsequentes viram body (preserva `THREAD ERROR + stacktrace` e dumps SQL multi-linha intactos).

## Categorias e severidade default

| Categoria | Severidade típica | Sinais |
|---|---|---|
| `database` | critical | `ORA-xxx`, `Error - TOPCONN`, `Ctree Error` |
| `thread_error` | critical | `THREAD ERROR (...)`, type mismatch, array bounds |
| `rpo` | critical | `CheckAuth ERROR`, `EMPTY RPO`, `function not found` |
| `compilation` | critical | `ARQ.PRW(N) Cxxx Syntax Error` |
| `service` | critical | `HTTP Server fail to start`, `Server shutdown` |
| `rest_api` | critical | `Error 500`, `Fail to write response` |
| `network` | warning | `SSL timeout`, `TLS init error` |
| `connection` | warning | inactivity timeout, `Error ending thread` |
| `authentication` | warning | `LogonUser code 1326/1327/1331` |
| `shutdown` | warning | `Closing connections.. Retry N` |
| `application` | warning | `[WARNING]` genérico |
| `lifecycle` | info | `Server is running`, `in shutdown` |

## Exemplos

- `/plugadvpl:log-diagnose` — auto-discover + diagnose completo
- `/plugadvpl:log-diagnose /var/log/protheus/` — diretório explícito
- `/plugadvpl:log-diagnose console.log error.log` — múltiplos arquivos
- `/plugadvpl:log-diagnose --severity critical --since 24h` — críticos das últimas 24h dentro do log
- `/plugadvpl:log-diagnose --category database` — só erros de banco
- `/plugadvpl:log-diagnose --rule LOG-DB-ORA --format json` — todas as ORA-xxx em JSON

## Saída

Para cada finding:

- arquivo + tipo (console/error/profile/compile) + linha + timestamp + thread_id
- severidade + categoria + rule_id
- mensagem extraída
- `sugestao_fix` (correction tip da KB TDN, com URL oficial quando aplicável)
- enrichments: `ora_code` (quando ORA-xxx aparece), `usuario` + `host` (quando Thread finished/Error ending thread)

## Próximos passos típicos

- `/plugadvpl:log-diagnose --rule <REGRA> --format json` — drill-down em 1 padrão
- `/plugadvpl:log-diagnose --category thread_error --format md` — todas as THREAD ERROR
- Após corrigir, rode novamente — cache (hash+mtime) invalida automaticamente
