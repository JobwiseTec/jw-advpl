---
description: Descobre a familia de fontes por prefixo de nome (tipo + LoC + capabilities + descricao do header) numa tabela
disable-model-invocation: true
arguments: [prefixo]
allowed-tools: [Bash]
---

# `/plugadvpl:family`

Lista todos os fontes da **mesma familia** (cujo basename comeca com o `prefixo`) numa tabela
estruturada — em vez de rodar `find` repetido. Por fonte mostra: `arquivo`, `source_type`, linhas,
`capabilities` e a **descricao do header doc** (quando o fonte tem cabecalho declarativo, vide #63).

Serve para **mapear um processo customizado** rapidamente: sistemas Protheus seguem convencao de
prefixo (ex.: `MOD120`, `MOD121`, `MOD122`...), e ver a familia inteira de uma vez acelera o
entendimento arquitetural.

## Uso

```
/plugadvpl:family <prefixo>
```

`prefixo` simples (`MOD12`) e ancorado no inicio. Aceita glob: `family "FAT*"`, `family "MOD*FIM"`.

`--include-tables` (#72) acrescenta `tables_read` (top-N por relevancia) e `tables_write` (com tag
`(mvc)`/`(execauto)`) por fonte — panorama do processo numa tela, sem rodar `arch` por fonte.
`--max-tables N` ajusta o top-N; `--custom-only` mostra so tabelas custom (`Z*`/`SZ*`).

## Execucao

```bash
uvx plugadvpl@0.34.0 --format md family $prefixo
uvx plugadvpl@0.34.0 --format md family $prefixo --include-tables
```

> A flag `--format` vem **antes** do subcomando (e global no callback). Use `--format md` (ou `json`).

## Exemplo

```
| arquivo     | source_type   | lines_of_code | capabilities      | descricao              |
| MOD120.prw  | mvc           | 850           | MVC, DIALOG       | Cadastro de Aprovadores|
| MOD121.prw  | mvc           | 1200          | MVC, DIALOG       | Cadastro de Regras     |
| MOD123.prw  | user_function | 2318          | MVC, DIALOG, PE   | Painel de Aprovacao    |
| MOD124.prw  | user_function | 320           |                   | Motor classico         |
```

## Proximos passos sugeridos

- `/plugadvpl:arch <arquivo> --include-header` — visao geral + header de cada fonte da familia
- `/plugadvpl:callers <arquivo>` — quem chama o fonte-pivot
- `find "MOD12*"` — o `find` tambem aceita glob agora (busca rapida sem a tabela estruturada)
