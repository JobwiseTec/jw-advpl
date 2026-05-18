# Universo 4 — Feature B: Qualidade & Métricas

> **Status:** spec — aguardando aprovação
> **Versão alvo:** v0.6.0 (segunda feature do Universo 4)
> **Schema bump:** v9 → v10 (tabela nova `fonte_metrics` + backfill `fontes.modulo`)
> **Pré-requisito:** v0.5.4 entregue
> **Time estimate:** ~4-5h

## 1. Problema

Hoje o plugin **não responde** perguntas básicas de qualidade:
- "Quais funções são mais **complexas** (refactor priority)?"
- "Quais são as **hot-paths** do projeto (top funções chamadas)?"
- "Qual a **cobertura de documentação** Protheus.doc por módulo?"

Lint pega bugs específicos (BP/SEC/PERF), mas não há **ranking** ou
**agregação** que ajude o usuário a decidir POR ONDE COMEÇAR num refactor.

## 2. Escopo MVP (v0.6.0)

### Inclui — 3 comandos novos

| Comando | Função |
|---------|--------|
| **`metrics [arquivo]`** | Lista funções com complexidade ciclomática, LOC, profundidade aninhamento, fan-out (calls). Filtros `--min-cc N`, `--min-loc N`, `--sort cc\|loc\|nesting\|calls`. |
| **`hotspots`** | Top-N funções mais chamadas (refactor priority). Filtros `--n 20`, `--no-natives` (exclui `ConOut`/`RecLock`/etc), `--tipo function\|method`. |
| **`cobertura-doc`** | % funções com Protheus.doc agrupado por módulo / `source_type`. Atalho consolidado pro lint BP-007. |

### Schema novo — `fonte_metrics`

Tabela cache (ingest popula, queries não recomputam):

```sql
CREATE TABLE fonte_metrics (
  id            TEXT PRIMARY KEY,        -- mesmo id de fonte_chunks
  arquivo       TEXT NOT NULL,
  funcao        TEXT,
  linha_inicio  INTEGER NOT NULL,
  linha_fim     INTEGER NOT NULL,
  loc           INTEGER NOT NULL,        -- linha_fim - linha_inicio + 1
  cc            INTEGER NOT NULL DEFAULT 1,  -- complexidade ciclomática
  nesting       INTEGER NOT NULL DEFAULT 0,  -- max depth de blocos
  n_calls_out   INTEGER NOT NULL DEFAULT 0,  -- fan-out
  params_count  INTEGER NOT NULL DEFAULT 0,
  has_doc       INTEGER NOT NULL DEFAULT 0,  -- 1 se tem Protheus.doc
  FOREIGN KEY (id) REFERENCES fonte_chunks(id) ON DELETE CASCADE
);

CREATE INDEX idx_metrics_arquivo ON fonte_metrics(arquivo);
CREATE INDEX idx_metrics_cc ON fonte_metrics(cc DESC);  -- top-N rápido
CREATE INDEX idx_metrics_loc ON fonte_metrics(loc DESC);
```

### Bloqueador identificado pela pesquisa: `fontes.modulo` vazio

A pesquisa revelou que **`fontes.modulo` é sempre `""`** (hardcoded em
`ingest.py:253`). Único módulo confiável vive em `protheus_docs.module_inferido`.

Pra `cobertura-doc` agregar por módulo, **vou também fazer backfill** do
campo na mesma release — reaproveita `infer_module()` que já existe em
`parsing/protheus_doc.py` (path-based + routine-prefix do catálogo execauto).

**Benefício colateral**: outros comandos (`workflow --kind`, `execauto --modulo`,
filtros `--modulo` em `find`/`callers`) ganham agrupamento por módulo robusto.

### Não inclui (defer release dot)

- **Histórico temporal de métricas** (delta entre ingests) — exige índice histórico, escopo bem maior
- **Coupling/cohesion** (LCOM/CBO) — análise OO mais profunda, ADVPL raramente justifica
- **Test coverage** — ADVPL legado raramente tem testes; complementaria mas é nicho
- **Métricas por classe** (vs por função) — TLPP tem classes; pode entrar em v0.6.1

## 3. Algoritmos

### 3.1 Complexidade Ciclomática

McCabe simplificado pra ADVPL:

```python
_CC_DECISION_RE = re.compile(
    r"\b(If|ElseIf|While|For|Case|Catch|IIf)\b",
    re.IGNORECASE,
)
# Por função (escopo via fonte_chunks.linha_inicio..linha_fim):
# CC = 1 + count(matches no body stripado)
```

**Decisões:**
- `Else` NÃO conta (não adiciona path no fluxo)
- `Do Case` = +1 base; cada `Case` interno = +1 (espelha if/elseif)
- `Try/Catch` = +1 por catch
- `IIf()` ternário = +1 (caminho condicional inline)
- `EndIf`/`EndCase`/`Next`/`EndDo` = closers, ignorar

**Uso `strip_advpl(strict=True)`** pra evitar matches em strings/comments.

### 3.2 Profundidade de Aninhamento

Stack-based scan pelo body da função:

```python
_OPENERS = re.compile(r"\b(If|While|For|Do\s+Case|Try|Begin\s+Sequence|Begin\s+Transaction)\b", re.IGNORECASE)
_CLOSERS = re.compile(r"\b(EndIf|EndDo|Next|EndCase|End\s*Try|End\s+Sequence|End\s+Transaction)\b", re.IGNORECASE)
# Track max(depth) durante varredura linear
```

### 3.3 Fan-out (n_calls_out)

```sql
SELECT arquivo_origem, funcao_origem, COUNT(*) AS n
FROM chamadas_funcao GROUP BY arquivo_origem, funcao_origem
```

Já indexado, baixo custo.

### 3.4 Hotspots

```sql
SELECT destino_norm, COUNT(*) AS n_calls,
       COUNT(DISTINCT arquivo_origem) AS n_arquivos,
       COUNT(DISTINCT arquivo_origem || '::' || funcao_origem) AS n_callsites
FROM chamadas_funcao
WHERE destino_norm NOT IN (SELECT upper(nome) FROM funcoes_nativas)
GROUP BY destino_norm
ORDER BY n_calls DESC LIMIT ?
```

Filtro de nativas via `WHERE NOT IN funcoes_nativas` (já existe lookup com ~7k rows).

### 3.5 Cobertura-doc

Pós-backfill de `fontes.modulo`:

```sql
SELECT f.modulo, COUNT(*) AS total,
       SUM(fm.has_doc) AS com_doc,
       ROUND(100.0 * SUM(fm.has_doc) / COUNT(*), 1) AS pct
FROM fonte_metrics fm
JOIN fontes f ON f.arquivo = fm.arquivo
WHERE f.modulo IS NOT NULL AND f.modulo != ''
GROUP BY f.modulo
ORDER BY pct ASC
```

Quando módulo não inferível, agrupa como `"_sem_modulo"`.

## 4. Plano de implementação (TDD)

### Fase 1 — Schema + backfill (~1h)
- Migration `010_universo4_metrics.sql`: cria `fonte_metrics`
- Schema v9 → v10
- Backfill `fontes.modulo` via `infer_module()` (reaproveita helper de protheus_doc)
- Bump `SCHEMA_VERSION` + populate ingest

### Fase 2 — Extractors de CC + nesting (~1.5h)
- `cli/plugadvpl/parsing/metrics.py` (módulo novo):
  - `compute_cyclomatic_complexity(body: str) -> int`
  - `compute_max_nesting(body: str) -> int`
- TDD red→green com cases sintéticos cobrindo cada keyword

### Fase 3 — Ingest wire (~30min)
- Após cada `fonte_chunk` ingerido, computa métricas e insere em `fonte_metrics`
- Reaproveita `content` já salvo no chunk

### Fase 4 — Queries (~30min)
- `metrics_query(conn, *, arquivo=None, min_cc=0, min_loc=0, sort='cc')`
- `hotspots_query(conn, *, n=20, excluir_nativas=True, tipo=None)`
- `cobertura_doc_query(conn, *, groupby='modulo')`

### Fase 5 — CLI + skills (~45min)
- 3 comandos novos
- 3 skills MD
- Update `arch` pra incluir métricas da função (cross-ref)

### Fase 6 — Tests + release (~30min)
- Unit tests pra CC/nesting (edge cases)
- Integration tests pros 3 comandos
- Bump version, CHANGELOG, commit + tag + push

**Total estimado:** ~5h.

## 5. Decisões a aprovar

### 5.1 Schema novo (tabela `fonte_metrics`) vs computar on-demand
**Recomendação:** **tabela nova**.
- ✅ Performance pra ranking cross-file (top-N CC sem varrer todos os fontes)
- ✅ Hotspots e cobertura-doc viram queries triviais
- ✅ Cache invalidado naturalmente via DELETE CASCADE quando re-ingest
- ❌ Mais 1 tabela (vale tradeoff)

### 5.2 Backfill `fontes.modulo` na mesma release
**Recomendação:** **sim**.
- Resolve bloqueador pra cobertura-doc agregar por módulo (`source_type` é fraco fallback)
- Beneficia outras features (`workflow --kind`, `execauto --modulo`)
- Reaproveita `infer_module()` existente — zero código novo, só wire no ingest
- Schema bump mas migration trivial (1 query UPDATE)

### 5.3 Hotspots: filtrar nativas por default
**Recomendação:** **sim, opt-out via `--no-natives=false`**.
- Sem filtro, top-20 fica dominado por `RecLock`/`DbSelectArea`/`ConOut` — sem valor pra refactor priority
- Lookup `funcoes_nativas` já existe (~7k rows indexadas)

### 5.4 Cobertura-doc: groupby default
**Recomendação:** **`modulo`** (após backfill). Com fallback `source_type` se `--groupby=source_type` for passado explicitamente. Bucket `"_sem_modulo"` quando módulo NULL.

### 5.5 CC counting: incluir `Else`?
**Recomendação:** **não**. Padrão McCabe — `Else` não adiciona path. `ElseIf` sim.

### 5.6 Versão: v0.6.0 (minor bump)
**Recomendação:** **v0.6.0**. Schema migration + nova tabela = minor. Sem breaking change (todos os comandos antigos continuam).

## 6. Edge cases

| # | Caso | Comportamento |
|---|------|---------------|
| 1 | Função com `Return Nil` apenas | CC=1, LOC=1. Sem filter `--min-cc 2` ou `--min-loc 3`, aparece com ruído |
| 2 | Função gigante (1000+ linhas) | Computado normalmente; cap defensivo no display via `--limit` global |
| 3 | Função homônima no mesmo fonte | `fonte_chunks.id` inclui linha — métricas separadas |
| 4 | `tipo_simbolo='header'` (não é função real) | Skip no ingest de métricas |
| 5 | Hotspot de método (`oObj:Save`) vs função global | Ambos contam; filtro `--tipo` separa |
| 6 | Cobertura: fonte sem SX e sem path inferível | Bucket `"_sem_modulo"` |
| 7 | Macro substitution (`&cVar`) na chamada | Mesma limitação dos outros universos — não conta |

## 7. Comparação com features existentes

| Feature | Status atual | Como complementa B |
|---------|--------------|---------------------|
| `lint` | Pega bugs específicos | B agrega por arquivo/severidade pra ranking |
| `arch` | Visão por fonte (capabilities, tabelas) | B adiciona métricas no mesmo output |
| `docs --orphans` | Lista funções sem header | B agrega % por módulo |
| `callers <funcao>` | Detalhe de UM caller | `hotspots` retorna o ranking inverso |

## 8. Comando exemplos (esperado pós-implementação)

```bash
# Top-10 funções mais complexas do projeto
plugadvpl metrics --sort cc --limit 10

# Funções gigantes (> 300 linhas) — candidatas de refactor
plugadvpl metrics --min-loc 300 --sort loc

# Hotspots ignorando nativas
plugadvpl hotspots --n 20

# Hotspots só de user functions (exclui métodos)
plugadvpl hotspots --tipo function

# Cobertura de doc por módulo (ordem ascendente — pior primeiro)
plugadvpl cobertura-doc
# Saída esperada:
# modulo    | total | com_doc | pct
# SIGAFAT   | 1245  | 134     | 10.8
# SIGACOM   |  890  | 287     | 32.2
# _sem_modulo |  120 |  45     | 37.5

# Métricas de um fonte específico (cross-ref com arch)
plugadvpl metrics ABCCOM01.prw
```

## 9. Fontes (research interno)

- `cli/plugadvpl/parsing/parser.py` — extractors atuais, `_add_function_ranges`
- `cli/plugadvpl/parsing/lint.py` — `_PERF004_LOOP_KW_RE` (única regex de controle de fluxo hoje)
- `cli/plugadvpl/parsing/protheus_doc.py` — `infer_module()` (reuso pro backfill)
- `cli/plugadvpl/migrations/001_initial.sql` — schema base
- `cli/plugadvpl/migrations/007_universo3_protheus_docs.sql` — único `module_inferido` hoje
- `cli/plugadvpl/lookups/funcoes_nativas.json` — allowlist pra hotspots

---

## Perguntas pra aprovar antes de codar

1. **Tabela `fonte_metrics`** vs on-demand? *(rec: tabela)*
2. **Backfill `fontes.modulo`** na mesma release? *(rec: sim, reuso `infer_module()`)*
3. **Hotspots filtra nativas por default**? *(rec: sim)*
4. **Cobertura-doc agrupa por `modulo` default**? *(rec: sim, post-backfill)*
5. **CC inclui `Else`**? *(rec: não — padrão McCabe)*
6. **Versão v0.6.0**? *(rec: sim, minor bump por schema migration)*
