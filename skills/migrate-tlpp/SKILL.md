---
description: Migrador determinístico ADVPL clássico (.prw cp1252) → TLPP moderno (.tlpp utf-8) com pipeline ts-migrate-style — 4 subcomandos (init/rename/recipes/todos), 11 recipes (6 SAFE default + 5 IDIOMS opt-in), ordem canônica fixa, safety gates (git clean + DB ingest), backup .bak.<timestamp>, rollback cascata (bak → git checkout → abort), auto-validação via plugadvpl compile (v0.18.0+)
disable-model-invocation: true
arguments: [subcommand + arquivo/pasta + flags]
allowed-tools: [Bash]
---

# `/plugadvpl:migrate-tlpp`

**Primeiro migrador ADVPL→TLPP determinístico do mercado** com auto-validação via compile. Pipeline `ts-migrate`-style: aplica recipes em ordem canônica topológica fixa, com safety gates pre-flight, backup automático, e rollback cascata em 3 níveis em caso de falha.

Saída em diff por default (preview); só escreve com `--write`. Emite `@plugadvpl-todo` markers pra débitos que precisam de revisão humana (renames cross-file, padrões aninhados, ambiguidade de namespace).

## Quando usar

- Migrar arquivo `.prw` (ADVPL clássico, cp1252) pra `.tlpp` (TLPP moderno, utf-8 + namespaces + try/catch + named-args).
- Auditar projeto inteiro pra ver o que é migrável sem mexer em nada (`init`).
- Conservador: só rename + encoding sem transformações de sintaxe (`rename`).
- Pipeline completo (recipes + safety gates + validate): `recipes`.
- Listar débitos pendentes em arquivos já migrados (`todos`).

**Não use** pra:
- Migrar `Static Function` cross-file → namespaces (v0.19.x).
- Converter `WsRESTful WSMETHOD` → annotations `@Get`/`@Post` (v0.19.x).
- Refactor de classes clássicas ADVPL → classes TLPP modernas (v0.19.x).
- Modo interativo `[y/n]` por recipe (preferir batch + diff + commit incremental).

## Uso

### Subcomandos

```
plugadvpl migrate-tlpp init <pasta>
    [--idioms] [--tlpp-version 20.3.2]
# Analisa pasta (read-only) e lista candidatos com counts por recipe.

plugadvpl migrate-tlpp rename <arquivo>
    [--write] [--validate] [--allow-dirty]
# Subset conservador — só recipes 1 (convert-encoding) + 2 (rename-extension).

plugadvpl migrate-tlpp recipes <arquivo>
    [--write] [--validate]
    [--idioms] [--tlpp-version 20.3.2]
    [--allow-dirty] [--no-impact-check]
    [--recipe <id>] (repetível)
# Pipeline completo de recipes.

plugadvpl migrate-tlpp todos [<pasta>]
# Lista @plugadvpl-todo pendentes em .tlpp.
```

## Exemplos

### 1) Auditar projeto sem tocar nada (init)

```bash
plugadvpl migrate-tlpp init src/
plugadvpl --format json migrate-tlpp init src/   # JSON pra script
plugadvpl migrate-tlpp init src/ --idioms        # inclui 5 IDIOMS na análise
```

Output (table): por arquivo → counts de `recipes_ok`, `nochange`, `needs_review`, `todos`.

### 2) Migração conservadora (só rename + encoding)

```bash
plugadvpl migrate-tlpp rename src/SIGAFAT/MT460FIM.prw          # diff-only
plugadvpl migrate-tlpp rename src/SIGAFAT/MT460FIM.prw --write  # aplica
```

Renomeia `.prw` → `.tlpp` + reescreve em utf-8. Sem mexer em código.

### 3) Pipeline completo de recipes (caso típico)

```bash
# Diff-only (default) — recomendado pra revisar antes
plugadvpl migrate-tlpp recipes src/SIGAFAT/MT460FIM.prw --no-impact-check --allow-dirty

# Apply + valida via compile
plugadvpl migrate-tlpp recipes src/SIGAFAT/MT460FIM.prw \
    --write --validate \
    --idioms --tlpp-version 20.3.2
```

Aplica 11 recipes (com `--idioms`) em ordem canônica, valida via `plugadvpl compile`, rollback automático se compile falhar.

### 4) Aplicar apenas recipes específicas

```bash
plugadvpl migrate-tlpp recipes src/x.prw \
    --recipe header-includes --recipe named-args \
    --write --tlpp-version 20.3.2
```

Mantém ordem canônica mesmo passando flags em ordem arbitrária.

### 5) Listar débitos pendentes

```bash
plugadvpl migrate-tlpp todos src/
plugadvpl --format json migrate-tlpp todos src/
```

Varre `.tlpp` procurando `// @plugadvpl-todo:<recipe> <mensagem>`.

## Workflow recomendado

1. **Ingest primeiro:** `plugadvpl ingest` popula `.plugadvpl/index.db` pra detectar callers externos (gating de `user-function-lowercase` e `expand-truncated-names`).
2. **Audit:** `plugadvpl migrate-tlpp init src/` (read-only; lista candidatos + scores).
3. **Stage no git:** trabalhe em branch dedicada, working tree clean (sem `--allow-dirty`).
4. **Preview por arquivo:** `plugadvpl migrate-tlpp recipes <arquivo>` (diff-only).
5. **Revise** os `@plugadvpl-todo` markers no diff.
6. **Apply + validate:** `plugadvpl migrate-tlpp recipes <arquivo> --write --validate`.
7. **Commit por arquivo** (rollback automático já protege; mas commit incremental ajuda em revisão humana).
8. **Pós-migração:** `plugadvpl migrate-tlpp todos src/` pra varrer débitos remanescentes.

## Convenções importantes

- **Default = SAFE.** Os 5 recipes IDIOMS (namespace-infer, begin-sequence-to-try, conout-to-fwlog, json-inline, expand-truncated-names) só rodam com `--idioms`.
- **Default = dry-run.** Sem `--write` o pipeline só emite diff + sumário (read-only).
- **`--validate` pede --write.** Validate roda `plugadvpl compile` no arquivo migrado e dispara rollback cascata se compile retornar exit != 0.
- **`--allow-dirty`** desativa o gate de git working tree limpo (use só em sandbox).
- **`--no-impact-check`** desativa o gate de DB ingested (modo conservador — `user-function-lowercase` preserva nomes truncados; `expand-truncated-names` skipa).
- **`--tlpp-version 20.3.2`** habilita recipes gated (atualmente só `named-args` exige AppServer ≥20.3.2.0).
- **Rollback cascata:** se `--validate` falhar, ordem de restore é (1) `.bak.<timestamp>` mais antigo, (2) `git checkout HEAD -- <file>`, (3) abort com exit 2 (CRITICAL).
- **`@plugadvpl-todo`** vai no `.tlpp` migrado como `// @plugadvpl-todo:<recipe-id> <mensagem>`. Use `migrate-tlpp todos` pra varrer depois.

## Execução

```bash
uvx plugadvpl@0.23.0 migrate-tlpp $ARGUMENTS
```

## Atribuição

Esta skill é derivada do material TOTVS oficial `engpro-advpl-tlpp-skills` (commit `8131443e23cdcf6c7b6e4c943756d98aa7d42f75`). Padrões de transformação ADVPL→TLPP, ordem canônica e blocking guardrails seguem referência:

- [advpl-to-tlpp-migration/SKILL.md (SHA-fixo)](https://github.com/totvs/engpro-advpl-tlpp-skills/blob/8131443e23cdcf6c7b6e4c943756d98aa7d42f75/skills/advpl-tlpp/advpl-to-tlpp-migration/SKILL.md)
- [tlpp-migration-patterns.md (SHA-fixo)](https://github.com/totvs/engpro-advpl-tlpp-skills/blob/8131443e23cdcf6c7b6e4c943756d98aa7d42f75/skills/advpl-tlpp/advpl-to-tlpp-migration/references/tlpp-migration-patterns.md)

Material TOTVS sob licença MIT (verificado em 2026-05-31); plugadvpl é MIT — derivação compatível confirmada.

## Links

- `/plugadvpl:docs` — agrega blocos Protheus.doc (útil pra revisar headers após migração).
- `/plugadvpl:arch` — extrai signature de funções (útil pra prever impacto de rename).
- `/plugadvpl:edit-prw` — manipulação segura de `.prw` cp1252 (use antes de Read/Edit manual).
- `/plugadvpl:compile` — usado internamente pelo `--validate` (auto-validação pós-migração).
- `/plugadvpl:ingest` — popula DB que destrava detection de callers externos.
