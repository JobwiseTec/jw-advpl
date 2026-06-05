---
description: Auditar arquivos INI Protheus (appserver, dbaccess, smartclient, tss, broker) contra 487 regras de boas práticas TDN-oficiais.
disable-model-invocation: true
arguments: [paths]
allowed-tools: [Bash]
---

# `/plugadvpl:ini-audit`

Audita arquivos INI Protheus em um único comando: ingere os INIs no índice, classifica `tipo` (appserver/dbaccess/smartclient/tss/broker) e `role` (14 possíveis: broker_http, slave_rest, dbaccess_master, …), e aplica o catálogo de 487 regras filtradas por tipo + role.

## Uso

```
/plugadvpl:ini-audit [paths] [--severity critical|warning|info] [--regra <id>] [--show-ok-with-note]
```

## Opções principais

- `--severity <nivel>` — só findings da severidade indicada
- `--regra <id>` — só uma regra específica (ex: `APP-GENERAL-MAXSTRINGSIZE`)
- `--arquivo <nome>` — filtra por basename do INI
- `--show-ok-with-note` — inclui findings onde o cliente documentou justificativa (`; intencional: …`, `; cliente exige …`)
- `--force` — re-ingere mesmo se hash+mtime baterem (ignora cache)
- `--no-audit` — só faz ingest, sem rodar regras

## Discovery

Sem args, faz auto-discover em `--root` via globs:

```
*appserver*.ini  *dbaccess*.ini  *smartclient*.ini  *tss*.ini  *broker*.ini
```

Cobre prefixos comuns de ambiente: `dev_appserver.ini`, `prd-dbaccess.ini`, `appserver_qa.ini`, etc.

## Execução

```bash
uvx plugadvpl@0.24.0 --format md ini-audit $ARGUMENTS
```

> **Para agente IA:** prefira `--format md` ou `--format json` — o default `table` trunca colunas em terminais estreitos. Flags `--format`/`--quiet`/`--limit` são GLOBAIS e vêm ANTES do subcomando.

## O que detecta (8 detection_kinds × 487 regras)

- **value_eq** — valor recomendado pra chave (equivalência booleana suportada: `1` == `true` == `yes` == `sim`)
- **value_in** — valor entre opções aceitas (enum)
- **value_neq** — valor NÃO pode ser X (deprecado, inseguro)
- **range_check** — integer dentro de range `min..max`
- **key_present** — chave obrigatória existe?
- **key_missing** — chave deve estar AUSENTE (deprecada)
- **regex** — valor casa padrão regex

Filtro por tipo+role: regras `APP-*` só aplicam a INIs `tipo=appserver`, `DBA-*` só a `tipo=dbaccess`, etc. Cada regra pode ainda restringir por role específico (ex: regra que só aplica a `slave_rest`).

## Status dos findings

| Status | Quando |
|---|---|
| `active` | Finding em aberto (não-conforme + sem justificativa) |
| `ok_with_note` | Não-conforme MAS o cliente documentou justificativa em comentário (`; intencional: ...`, `; cliente exige ...`, `; aprovado em ...`). Não aparece no default — use `--show-ok-with-note` |
| `suppressed` | Reservado (futuro) |

## Exemplos

- `/plugadvpl:ini-audit` — auto-discover + audit completo do projeto
- `/plugadvpl:ini-audit /srv/protheus/` — auto-discover dentro de um path
- `/plugadvpl:ini-audit appserver_prd.ini` — 1 arquivo específico
- `/plugadvpl:ini-audit --severity critical` — só críticos (geralmente 1-5 findings; vale a pena olhar)
- `/plugadvpl:ini-audit --regra APP-GENERAL-MAXSTRINGSIZE` — 1 regra específica em todos os INIs
- `/plugadvpl:ini-audit --arquivo dbaccess_master.ini --severity warning` — combinando filtros

## Saída

Para cada finding:

- arquivo + tipo + role
- section + key + linha
- regra_id (formato `<TIPO>-<SECTION>-<KEY>`)
- severidade
- snippet da linha problemática
- `sugestao_fix` com valor recomendado + link TDN oficial

## Próximos passos típicos

- `/plugadvpl:ini-audit --regra <REGRA> --format json` — drill-down numa regra específica pra mapear todas as ocorrências
- Editar o INI (mantendo encoding CP1252) e rodar novamente — cache (hash+mtime) é invalidado automaticamente
- `/plugadvpl:status` — confirma que os INIs estão no índice
