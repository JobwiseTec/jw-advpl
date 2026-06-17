---
description: Consulta catalogo importado (ingest-tsv) - lista/filtra/agrega + decode X3_CBOX + cruza *_FUNCAO com fontes
disable-model-invocation: true
arguments: [alias]
allowed-tools: [Bash]
---

# `/plugadvpl:catalog`

Consulta o **conteudo** de uma tabela-catalogo importada via `ingest-tsv`. Determinístico, sem ir ao
banco — as 5 analises tipicas (distribuicao por filial/categoria, contar desativados, funcao mais comum,
cruzar funcao com fonte) viram invocacoes curtas.

## Uso

```
/plugadvpl:catalog <alias> [--filter "COL='X'"] [--group-by COL --count] [--decode-cbox] [--funcao-field COL --resolve-callers]
```

## Execucao

```bash
uvx plugadvpl@0.43.1 --format md catalog $alias --group-by ZT_TIPOREG --count --decode-cbox
```

## Exemplos

```bash
# distribuicao por filial
catalog regras --group-by ZT_FILIAL --count
# decodificado via X3_CBOX da tabela SX correlata
catalog regras --group-by ZT_TIPO --count --decode-cbox     # 1=Fiscal, 2=Financeiro, ...
# cruzar funcao do dump com o fonte que a define
catalog regras --funcao-field ZT_FUNCAO --resolve-callers   # U_MODxxx -> MODxxx.prw
# filtrar
catalog regras --filter "ZT_MSBLQL='2' AND ZT_FILIAL='01'"
```

## Filtro seguro

`COL OP 'VAL'` (OP: `= != > < >= <= LIKE`) unidos por `AND` **ou** `OR`. Aplicado em Python sobre os
registros — **a prova de SQL injection** (nunca vai pra query). Sintaxe invalida -> erro didatico.
