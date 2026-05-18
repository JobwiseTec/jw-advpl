# Universo 4 — Feature A: Trace Unificado

> **Status:** spec — aguardando aprovação
> **Versão alvo:** v0.5.0 (abre Universo 4)
> **Schema bump:** nenhum (só agregação de queries existentes + alguns JOINs novos)
> **Pré-requisito:** v0.4.9 entregue
> **Time estimate:** ~5h

## 1. Problema

Hoje, pra responder "estou mudando o campo `A1_COD`, o que quebra?", o usuário roda 4-5 comandos diferentes:

```bash
plugadvpl impacto A1_COD --depth 3       # SX3/SX7/SX1 + fontes
plugadvpl gatilho A1_COD                 # cadeia SX7 origem↔destino
plugadvpl tables SA1 --mode write        # quem escreve na tabela
plugadvpl callers <funcoes-do-A1>        # quem chama
plugadvpl execauto --modulo SIGAFIN      # se A1 é tocado via execauto
```

Cada um cobre **um pedaço da rastreabilidade**. O usuário tem que correlacionar mentalmente o output dos 5. Pra função e tabela, situação igual.

**Pergunta-alvo do v0.5.0:**
> "Liste **tudo** que toca `<entidade>` — cross-universo (fontes + SX + workflow/execauto/docs) em **um comando só**."

## 2. Escopo MVP (v0.5.0)

### Inclui — 3 tipos de entidade

| Tipo | Exemplos | Comando |
|------|----------|---------|
| **Campo SX3** | `A1_COD`, `C5_NUM` | `plugadvpl trace A1_COD` |
| **Função** | `MaFisRef`, `U_MyFn`, `MATA410` | `plugadvpl trace MaFisRef` |
| **Tabela** | `SC5`, `SA1`, `ZA1` | `plugadvpl trace SC5` |

### Auto-detecção de tipo

Regex de auto-detect (ordem):
1. `^[A-Z][A-Z0-9]\d` ou Protheus-pattern (3 chars, [SZNQD]+letra+alfanum) → **tabela**
2. `^[A-Z]\d_\w+` ou matches `SELECT prefix FROM campos WHERE nome=?` → **campo**
3. Fallback: → **função**

Override explícito: `--tipo campo|funcao|tabela`.

### Não inclui (defer release dot)

- `parametro:MV_*` — `param_query` existe; cruzamento com `SX6.validacao` precisa nova query
- `pergunte:GRUPO` — análogo
- `arquivo:X.prw` — `arch` já agrega, trace seria reuso direto
- `rotina:MATA410` — já tem `execauto --routine`
- Outras entidades (índice SIX, consulta SXB, etc.)

## 3. Comando + flags

```
plugadvpl trace <entidade>
                [--tipo campo|funcao|tabela]
                [--depth 1..3]                    # default 2 (igual impacto)
                [--universo 1,2,3]                # filtra; default todos
                [--max-per-edge N]                # default 20
```

## 4. Schema de saída unificado

Cada hit do trace é uma **aresta** entre a entidade-alvo e algo. Schema flat:

```python
{
    "universo": 1 | 2 | 3,
    "edge": str,           # tipo de relação (vide §4.1)
    "arquivo": str,        # quando aplicável (basename)
    "funcao": str,         # quando aplicável
    "linha": int,          # quando aplicável
    "alvo": str,           # entidade encontrada do outro lado da aresta
    "contexto": str,       # detalhe livre ("X3_VALID", "op=3 inclusao", "@deprecated", etc.)
    "snippet": str,        # truncado pra display
}
```

### 4.1 Tipos de aresta (`edge`)

| Edge | Universo | Quando aparece |
|------|----------|----------------|
| `calls` | 1 | Função-alvo chama outra (callees) |
| `called_by` | 1 | Outra função chama a alvo (callers) |
| `reads` | 1 | Fonte lê tabela (`fonte_tabela.modo=read`) |
| `writes` | 1 | Fonte escreve tabela (`fonte_tabela.modo=write`) |
| `reclock` | 1 | Fonte faz RecLock na tabela |
| `uses_param` | 1 | Função usa MV_* (cruz com parametros_uso) |
| `defined_in` | 1 | Função declarada em arquivo |
| `validates_field` | 2 | Função aparece em X3_VALID/INIT/WHEN |
| `field_definition` | 2 | Campo SX3 (cabeçalho + flags principais) |
| `trigger_origin` | 2 | SX7 onde campo é origem |
| `trigger_target` | 2 | SX7 onde campo é destino |
| `in_pergunte` | 2 | Campo aparece em SX1 |
| `in_relationship` | 2 | Tabela em SX9 (origem/destino) |
| `indexed_by` | 2 | Tabela tem índice SIX cobrindo o campo |
| `in_consulta` | 2 | Campo em SXB consulta F3 |
| `in_grupo_sxg` | 2 | Campo em grupo SXG |
| `triggered_by_workflow` | 3 | Função é callback de TWFProcess |
| `triggered_by_schedule` | 3 | Função tem SchedDef |
| `triggered_by_job` | 3 | Função é Main de daemon |
| `via_execauto` | 3 | Função é rotina chamada por MsExecAuto |
| `touched_via_execauto` | 3 | Tabela aparece em execauto_calls.tables_resolved |
| `documented_in` | 3 | Função tem Protheus.doc; ou campo aparece em `protheus_docs.tables` |

## 5. Algoritmo (por tipo de entrada)

### 5.1 `_trace_campo(conn, campo, depth)`

1. **Universo 1 — fontes**
   - Já existe `_impacto_fontes(conn, campo, max_per_kind)` → reaproveita.
   - Edge: `references_field`
2. **Universo 2 — SX**
   - `_impacto_sx3(conn, campo)` → edge `field_definition`
   - `_impacto_sx7_chain(conn, campo, depth)` → edges `trigger_origin` / `trigger_target`
   - `_impacto_sx1(conn, campo)` → edge `in_pergunte`
   - **NOVO:** SELECT em `relacionamentos` WHERE `campo_origem`/`campo_destino` LIKE → edge `in_relationship`
   - **NOVO:** SELECT em `consultas` WHERE `coluna` LIKE → edge `in_consulta`
   - **NOVO:** SELECT em `campos` WHERE `nome=campo` retorna `grpsxg` → JOIN `grupos_campo` → edge `in_grupo_sxg`
3. **Universo 3 — docs**
   - **NOVO:** SELECT em `protheus_docs` WHERE `tables_json LIKE '%"' || tabela_do_campo || '"%'` + pós-filtro Python → edge `documented_in`

### 5.2 `_trace_funcao(conn, funcao)`

1. **Universo 1**
   - `callers(funcao)` → edges `called_by`
   - `callees(funcao)` → edges `calls`
   - `find_function(funcao)` → edge `defined_in`
2. **Universo 2**
   - **NOVO:** SELECT em `campos` WHERE `validacao` LIKE `%funcao%` OR `init_browse` LIKE OR `when` LIKE OR `vld_user` LIKE → edge `validates_field`
3. **Universo 3**
   - `execauto_calls_query(routine=funcao)` → edge `via_execauto`
   - `execution_triggers_query(target=funcao)` → edges `triggered_by_workflow`/`schedule`/`job`/`callback` (separa por `kind`)
   - `protheus_doc_show(funcao)` → edge `documented_in` (resumo + metadata)

### 5.3 `_trace_tabela(conn, tabela)`

1. **Universo 1**
   - `tables_query(tabela)` → edges `reads`/`writes`/`reclock` (separar por modo)
   - **NOVO:** SELECT em `operacoes_escrita` WHERE `tabela=?` → edge `writes` (DML detalhado)
   - **NOVO:** SELECT em `sql_embedado` WHERE `tabelas LIKE '%tabela%'` → edge `sql_reads`
2. **Universo 2**
   - SELECT em `tabelas` WHERE `nome=?` → edge `table_definition`
   - SELECT em `campos` WHERE `tabela=?` (count) → edge `n_fields`
   - SELECT em `indices` WHERE `tabela=?` → edge `indexed_by`
   - SELECT em `relacionamentos` WHERE `tabela_origem=?` OR `tabela_destino=?` → edge `in_relationship`
   - SELECT em `gatilhos` WHERE `tabela=?` → edge `trigger_on_table`
3. **Universo 3**
   - **NOVO:** SELECT em `execauto_calls` WHERE `tables_resolved_json LIKE '%"tabela"%'` + pós-filtro → edge `touched_via_execauto`
   - **NOVO:** SELECT em `protheus_docs` WHERE `tables_json LIKE '%"tabela"%'` + pós-filtro → edge `documented_in`

## 6. Edge cases

| # | Caso | Comportamento |
|---|------|---------------|
| 1 | Entidade não existe no índice | Exit 0 com `(sem resultados)` + sugestão de typo (find similar) |
| 2 | Função homônima entre fontes | Lista todas as ocorrências, agrupadas por `arquivo` |
| 3 | Auto-detect ambíguo (ex.: `SA1` é tabela mas pode ser variável) | Default por regex; sugere `--tipo` se zero hits |
| 4 | Profundidade > 3 | Cap em 3 (mesma política de `impacto`) |
| 5 | Campo de tabela compartilhada (`A1_FILIAL`) | `max_per_edge` limita explosão |
| 6 | Função `U_X` chamada como `U_X(...)` E `X(...)` | Já tratado por `destino_norm` em `chamadas_funcao` |
| 7 | Tabela ausente no SX (só em fontes) | Edges Universo 1 retornam; Universo 2 retorna 0; OK |

## 7. Plano de implementação (TDD)

### Fase 1 — Schema entity + collectors (~2h)
- `cli/plugadvpl/query.py`:
  - `_detect_entity_type(value: str) -> str` (helpers para auto-detect)
  - `_trace_campo(conn, campo, depth, max_per_edge) -> list[dict]`
  - `_trace_funcao(conn, funcao, max_per_edge) -> list[dict]`
  - `_trace_tabela(conn, tabela, max_per_edge) -> list[dict]`
  - `trace_query(conn, entidade, *, tipo=None, depth=2, universos=None, max_per_edge=20) -> list[dict]`

### Fase 2 — CLI + skill (~1h)
- `cli/plugadvpl/cli.py`:
  - `@app.command() def trace(...)` com `--tipo`/`--depth`/`--universo`/`--max-per-edge`
- `skills/trace/SKILL.md`

### Fase 3 — Tests (~1.5h)
- `cli/tests/unit/test_trace.py`:
  - Auto-detect (3 cases)
  - Edge schema consistency (campos sempre populados)
- `cli/tests/integration/test_cli.py::TestTrace`:
  - Fixture com 1 campo SX3 + 2 fontes + 1 workflow callback
  - Trace campo retorna >= 3 edges (universo 1+2+3)
  - Trace função retorna callers/callees/doc
  - Trace tabela retorna reads/writes + execauto + indices

### Fase 4 — Release v0.5.0 (~30min)
- Bump skills/plugin.json/marketplace.json
- CHANGELOG entry com fechamento do "antes precisava 5 cmds, agora 1"
- Final sweep + commit + tag + push

## 8. Decisões a aprovar

### 8.1 Escopo MVP — só 3 tipos (campo/função/tabela)?
**Recomendação:** sim. Cobre 80% dos use cases. Bonus entities (param/pergunte/arquivo/rotina) em release dot futura.

### 8.2 Schema flat (1 dict por aresta) vs grafo aninhado
**Recomendação:** flat. Razões:
- Compatível com `--format json` consumido por Claude (cada hit = uma row)
- Filtros `--limit` global funcionam naturalmente
- Sort/group por `edge` ou `universo` trivial
- Grafo aninhado seria mais elegante mas dobra complexidade de display

### 8.3 Auto-detect vs `--tipo` sempre obrigatório
**Recomendação:** auto-detect com fallback. Razões:
- 90% das chamadas são óbvias por padrão de nome
- `--tipo` continua disponível pra casos ambíguos
- UX igual a `git checkout <branch-or-file>` — heurístico, com override

### 8.4 Depth default
**Recomendação:** 2. Consistente com `impacto`/`gatilho`. Profundidade 1 = só direto; 2 = direto + 1 hop; 3 = caro.

### 8.5 Versão: v0.5.0 (major bump) vs v0.4.10
**Recomendação:** **v0.5.0**. Abre Universo 4. Sem schema migration nem breaking change, mas marca novo tema.

### 8.6 Filtro `--universo`
**Recomendação:** sim, valor enum (`1`, `2`, `3` ou múltiplos). Útil pra debug + casos onde usuário só quer ver SX.

## 9. Trade-offs e o que NÃO faz

- **Não é grafo navegável.** Cada call do trace é uma snapshot. Pra "atravessar" (function → caller → caller of caller), usuário roda múltiplas vezes. Grafo interativo seria UI separada.
- **Não detecta DDL dinâmico** (`FW_AlterTable`, `TcAlter`). Limitação herdada dos universos.
- **Não traça através de macro substitution** (`&cVar`). Mesma limitação do parser.
- **Não persistence** — não cria nova tabela cache do trace. Cada chamada calcula do zero (mas é rápido: queries indexadas).

## 10. Sucesso

Métricas pós-release:

| KPI | Antes (5 comandos) | Depois (`trace`) |
|-----|---------------------|------------------|
| Comandos pra "impacto completo de campo" | 5 | 1 |
| Tokens consumidos por Claude | ~3-5k (5 outputs) | ~800 (1 output) |
| Falsos negativos por esquecimento de comando | comum | zero |

## 11. Fontes (research interno)

- `cli/plugadvpl/query.py` — inventário de queries reaproveitáveis (70%)
- `cli/plugadvpl/migrations/{001,002,005,006,007}.sql` — schema das tabelas
- Vide notas do agente research (gap analysis: ~30% queries novas, todas filtros JSON LIKE)

---

## Perguntas pra aprovar antes de codar

1. **MVP 3 tipos** (campo/função/tabela) ok? *(rec: sim)*
2. **Schema flat** (1 row por aresta) vs grafo? *(rec: flat)*
3. **Auto-detect** + override `--tipo`? *(rec: sim)*
4. **Versão v0.5.0** (abre Universo 4)? *(rec: sim)*
5. **`--universo` filter** (1/2/3 multi)? *(rec: sim)*
6. **`--depth` default 2**? *(rec: sim, max 3)*
