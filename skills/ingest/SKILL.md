---
description: Indexa fontes ADVPL/TLPP do projeto em SQLite + FTS5
disable-model-invocation: true
arguments: [paths]
allowed-tools: [Bash]
---

# `/plugadvpl:ingest`

Indexa fontes ADVPL/TLPP (.prw, .prx, .tlpp, .apw) em `.plugadvpl/index.db`.

## Uso

```
/plugadvpl:ingest [paths...] [opcoes]
```

Quando `paths` for omitido, indexa o diretorio do projeto atual.

## Opcoes

- `--workers N` — numero de workers paralelos (default: auto-adaptativo segundo CPUs)
- `--no-content` — nao armazena conteudo bruto dos fontes (apenas metadados/AST)
- `--redact-secrets` — redige strings sensiveis (senhas, tokens) antes de indexar
- `--incremental`/`--no-incremental` — default `--incremental` (pula arquivos cujo `mtime` no DB ja eh >= ao do filesystem). `--no-incremental` re-parseia tudo.
- `--exclude <glob>` — ignora um glob na ingestao (repetivel). Soma com `.plugadvplignore`. Ex: `--exclude 'descontinuado/**' --exclude '**/poc-*'`.

## Controle de escopo: `.plugadvplignore` (#141)

Para manter pastas/arquivos fora do indice (ex: pasta `descontinuado/`, copias por cliente), crie um `.plugadvplignore` na **raiz do projeto** — committavel, sintaxe subconjunto do `.gitignore`:

```gitignore
# fontes mortos — nao indexar
descontinuado/
**/*_old.prw
clientes/**/v1/*.prw
```

Regras suportadas: `dir/` (diretorio e tudo abaixo, em qualquer nivel), `*.glob` (por basename em qualquer nivel), `a/**/b.prw` (path com `**` cruzando niveis). NAO suporta negacao `!`.

O filtro vale igual em `ingest`, `reindex` e `status`. Um re-`ingest` **remove do indice** (prune) os fontes que passaram a ser ignorados (best-effort por basename) e o resumo mostra `ignorados: N (removidos do indice: M)`. Resolve tambem colisao de basename causada por pasta duplicada.

## Execucao

```bash
uvx plugadvpl@0.37.0 ingest $ARGUMENTS
```

## Exemplos

- `/plugadvpl:ingest` — indexa todo o projeto (incremental por default)
- `/plugadvpl:ingest src/` — indexa apenas `src/`
- `/plugadvpl:ingest --workers 8` — usa 8 workers paralelos
- `/plugadvpl:ingest --redact-secrets --no-content` — modo seguro (compliance)
- `/plugadvpl:ingest --no-incremental` — reindex completo (use apos upgrade do binario com regras novas — veja secao abaixo)

## Pegadinha do `--incremental` apos upgrade do binario

`--incremental` re-parseia somente arquivos cujo `mtime` mudou. As **regras de lint** (e demais lookups: `funcoes_restritas`, `funcoes_nativas`, etc.) vivem dentro do **binario**, nao nos arquivos fonte.

Cenario tipico:

1. Voce roda `uv tool upgrade plugadvpl` e ganha v0.3.10 → v0.3.12 (regras novas: BP-008 expandida, PERF-005 com LastRec, MOD-004 com MsNewGetDados).
2. Roda `plugadvpl ingest --incremental`.
3. Como nenhum `.prw` foi tocado, **todos sao skipped**. As novas regras nao sao re-aplicadas em nenhum arquivo do indice.
4. `total_lint_findings` continua refletindo a versao antiga.

**v0.3.13 detecta esse cenario** comparando `lookup_bundle_hash` antes/depois de `seed_lookups`. Quando o hash mudou e ha arquivos `skipped`, imprime aviso amarelo em **stderr**:

```
⚠ Lookups (lint_rules/funcoes_restritas/...) mudaram desde o ultimo ingest.
  --incremental pulou 1990 arquivo(s) cujo mtime nao mudou — esses NAO foram re-avaliados contra as regras novas.
  Para cobrir todo o codebase com as regras atualizadas, rode:
      plugadvpl ingest --no-incremental
```

A acao correta e rodar `plugadvpl ingest --no-incremental` (mais lento, mas garante que todas as regras passem em todos os arquivos). Suprimivel com `--quiet`.

## Proximos passos sugeridos

- `/plugadvpl:status` — verifica contagem de fontes/simbolos indexados (mostra tambem `runtime_version` vs `plugadvpl_version`)
- Se viu o aviso de lookups divergentes acima → `plugadvpl ingest --no-incremental`
- `/plugadvpl:find <termo>` — pesquisa simbolos
- `/plugadvpl:arch <arquivo>` — visao arquitetural antes de Read
