---
description: Importa dump TSV/CSV de tabela-catalogo (Z*/X*) pro indice (o conteudo das regras catalogadas)
disable-model-invocation: true
arguments: [arquivo]
allowed-tools: [Bash]
---

# `/plugadvpl:ingest-tsv`

Importa um dump tabular (TSV/CSV exportado do Oracle/SQL Server/DBeaver) de uma **tabela-catalogo**
(Z*/X* — cadastros pluggable de regras de negocio) pro indice, sob um alias.

Fecha o gap do **conteudo**: o `tables --catalog` (#64) da o *schema* + X3_CBOX; este traz as **N regras
catalogadas** pra cross-query nativa via `catalog`.

## Uso

```
/plugadvpl:ingest-tsv <arquivo> --as <alias>
```

Encoding (cp1252/utf-8/utf-8-bom) e delimiter (tab/csv) sao **auto-detectados**; override com
`--encoding` / `--delimiter`. Se o nome do arquivo bate com uma tabela do dicionario SX (ex.: `SZT.tsv`),
cruza automatico pra habilitar o `--decode-cbox` no `catalog`.

## Execucao

```bash
uvx plugadvpl@0.44.0 ingest-tsv $arquivo --as catalogo_regras
```

## Proximos passos sugeridos

- `/plugadvpl:catalog <alias> --group-by <COL> --count` — distribuicao
- `/plugadvpl:catalog <alias> --funcao-field <COL> --resolve-callers` — cruza funcao do dump com fonte indexado
