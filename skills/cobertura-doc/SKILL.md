---
description: Cobertura de Protheus.doc agregada por módulo — refactor priority pra documentação (Universo 4 Feature B, v0.6.0+)
disable-model-invocation: true
arguments: [filtros]
allowed-tools: [Bash]
---

# `/plugadvpl:cobertura-doc`

**Killer feature do v0.6.0** (Universo 4 — Qualidade & Métricas). Mostra
**% de funções com header Protheus.doc por módulo** — pra responder
"qual área está sem documentação?".

## Uso

```
/plugadvpl:cobertura-doc [--groupby modulo|source_type]
```

## O que mostra

| Campo | Significado |
|-------|-------------|
| `grupo` | Módulo (SIGAFAT/SIGACOM/etc) ou source_type (mvc/rest/cadastro/...) |
| `total` | N funções no grupo |
| `com_doc` | N funções com header Protheus.doc |
| `pct` | % cobertura (com_doc / total * 100) |

**Ordenado por `pct ASC`** — **pior cobertura primeiro** (refactor priority).

## Exemplos

```bash
# Cobertura por módulo (default — pós-backfill v0.6.0)
/plugadvpl:cobertura-doc
# Saída:
# grupo       | total | com_doc | pct
# SIGAFAT     | 1245  | 134     | 10.8
# SIGACOM     |  890  | 287     | 32.2
# _sem_grupo  |  120  |  45     | 37.5
# SIGAFIN     |  430  | 268     | 62.3

# Por tipo de fonte (mvc/rest/cadastro/etc) — fallback útil quando módulo não inferível
/plugadvpl:cobertura-doc --groupby source_type
```

## Sobre o módulo

`fontes.modulo` é populado no ingest via `infer_module()` (path-based +
routine-prefix do catálogo execauto). Quando módulo não inferível, fonte
cai no bucket `"_sem_grupo"`.

**Pra colher módulo após upgrade pro v0.6.0**: `plugadvpl ingest --no-incremental`.

## Cross-ref

- **`/plugadvpl:docs --orphans`** — lista funções sem header (drilldown)
- **`/plugadvpl:lint --regra BP-007`** — findings raw correspondentes
- **`/plugadvpl:docs <modulo>`** — todas funções documentadas de um módulo
- **`/plugadvpl:metrics`** — métricas individuais (CC/LOC/nesting) por função
