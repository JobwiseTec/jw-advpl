---
description: Trace agregado cross-universo — campo/função/tabela com TODAS as referências (fontes + SX + workflow/execauto/docs) em uma chamada (Universo 4 Feature A, v0.5.0+)
disable-model-invocation: true
arguments: [entidade]
allowed-tools: [Bash]
---

# `/plugadvpl:trace`

**Killer feature do v0.5.0** (Universo 4 — Trace Unificado). Substitui o workflow manual de **5 comandos** (`impacto` + `gatilho` + `tables` + `callers` + `execauto`) por **1 comando** que agrega TUDO que toca a entidade — atravessando os 3 universos do plugin.

## Por quê

Antes do v0.5.0, pra responder "estou mudando o campo `A1_COD`, o que quebra?" precisava:

```bash
plugadvpl impacto A1_COD --depth 3       # SX3/SX7/SX1 + fontes
plugadvpl gatilho A1_COD                 # cadeia SX7 origem↔destino
plugadvpl tables SA1 --mode write        # quem escreve na tabela
plugadvpl callers <funcoes-do-A1>        # quem chama
plugadvpl execauto --modulo SIGAFIN      # se A1 é tocado via execauto
# ~3-5k tokens de output, correlação mental
```

Agora:

```bash
plugadvpl trace A1_COD                   # ~800 tokens, tudo agregado
```

## Uso

```
/plugadvpl:trace <entidade> [--tipo campo|funcao|tabela]
                           [--depth 1..3] [--universo 1,2,3]
                           [--max-per-edge N]
```

## Auto-detect de tipo

| Padrão da entrada | Detectado como |
|-------------------|----------------|
| `SA1`, `SC5`, `ZA1`, `ND0` (3 chars [SZNQD]+letra+alfanum) | **tabela** |
| `A1_COD`, `C5_NUM` (letra+dígito+_+nome) | **campo** |
| Qualquer outro (`MaFisRef`, `U_MyFn`, `MATA410`, `FINA050`) | **funcao** |

Override: `--tipo campo` (ou `funcao`/`tabela`) força quando a heurística erra.

## Opções

- `[entidade]` — obrigatório (campo/função/tabela). Auto-detect por regex
- `--tipo` / `-t` — força tipo quando auto-detect ambíguo
- `--depth` / `-d` — profundidade BFS (1..3, default 2). Aplica em gatilhos transitivos
- `--universo` / `-u` — filtra (`1`=fontes, `2`=SX, `3`=workflow/execauto/docs). Múltiplos: `'1,2'`
- `--max-per-edge` — limite de hits por aresta (default 20). Cap defensivo

## Execução

```bash
uvx plugadvpl@0.5.1 --format md trace $ARGUMENTS
```

## Saída — schema unificado

Cada hit é uma **aresta** entre a entidade-alvo e algo. Schema flat:

| Campo | Significado |
|-------|-------------|
| `universo`  | 1 (fontes), 2 (SX), 3 (workflow/execauto/docs) |
| `edge`      | tipo de relação (vide §Edges abaixo) |
| `arquivo`   | basename (quando aplicável) |
| `funcao`    | função-pai do hit |
| `linha`     | linha do hit |
| `alvo`      | entidade encontrada do outro lado da aresta |
| `contexto`  | detalhe livre (ex.: `"X3_VALID"`, `"op=3 inclusao"`, `"DEPRECATED"`) |
| `snippet`   | trecho relevante (truncado a 120 chars) |

## Edges por tipo de entidade

### Campo (`A1_COD`)
- **U1**: `references_field` (fonte cita o campo em código)
- **U2**: `field_definition` (registro SX3 do campo) | `trigger_origin` / `trigger_target` (SX7) | `in_pergunte` (SX1) | `in_relationship` (SX9) | `in_consulta` (SXB) | `in_grupo_sxg` (SXG)

### Função (`MaFisRef`)
- **U1**: `defined_in` (arquivo onde declarada) | `called_by` (callers) | `calls` (callees)
- **U2**: `validates_field` (função usada em X3_VALID/INIT/WHEN/VLDUSER)
- **U3**: `via_execauto` (rotina chamada por MsExecAuto) | `triggered_by_workflow`/`schedule`/`job`/`mail`/`callback` (target de execution_trigger) | `documented_in` (Protheus.doc)

### Tabela (`SC5`)
- **U1**: `reads` / `writes` / `reclock` (fonte_tabela)
- **U2**: `table_definition` (SX2) | `n_fields` (count campos SX3) | `indexed_by` (SIX) | `in_relationship` (SX9) | `trigger_on_table` (SX7)
- **U3**: `touched_via_execauto` (tables_resolved de MsExecAuto) | `documented_in` (`@table` em Protheus.doc)

## Exemplos

- `/plugadvpl:trace A1_COD` — auto-detect campo, todos universos, depth 2
- `/plugadvpl:trace SC5` — auto-detect tabela
- `/plugadvpl:trace MaFisRef --universo 1,3` — só fontes + rastreabilidade (skip SX)
- `/plugadvpl:trace MATA410` — auto-detect função (FINA*/MATA* não são tabela)
- `/plugadvpl:trace SA1 --tipo funcao` — força função (se há fonte chamado SA1)
- `/plugadvpl:trace A1_FILIAL --max-per-edge 5` — campo super-comum, limita explosão
- `/plugadvpl:trace U_MyFn --depth 3` — profundidade maior em gatilhos

## Casos de uso

1. **"Estou alterando A1_COD, o que quebra?"**
   `/plugadvpl:trace A1_COD` retorna SX3 + SX7 (gatilhos) + SX1 (perguntes) + relacionamentos + consultas + fontes que tocam + jobs/workflows que chamam funções que tocam

2. **"Quem cria registros na SC5?"**
   `/plugadvpl:trace SC5 --universo 1,3` — writes diretos + via MsExecAuto

3. **"MyFn é morta ou está em uso?"**
   `/plugadvpl:trace MyFn` — se `called_by` vier vazio + 0 triggers, é candidata a remoção

4. **"Quem usa o índice SIX 3 de SC5?"**
   `/plugadvpl:trace SC5` lista índices; cruzar com fontes que fazem `DbOrderNickName`

5. **"Função X aparece em validações SX?"**
   `/plugadvpl:trace X --universo 2` — só edges `validates_field`

## Cross-ref com outras features

- **`/plugadvpl:impacto <campo>`** — versão profunda/detalhada SX (depth 3, mais SX-focused)
- **`/plugadvpl:gatilho <campo>`** — só cadeia SX7 (origem↔destino)
- **`/plugadvpl:tables <T>`** — só fonte_tabela com modos read/write/reclock
- **`/plugadvpl:callers <funcao>`** — só U1 callers (sem U2/U3)
- **`/plugadvpl:arch <fonte>`** — visão de UM arquivo (não atravessa universos)

`trace` é **agregador** — quando precisa do detalhe de um pedaço, vai pra ferramenta específica.

## Limitações conhecidas

- **Não traça macro substitution** (`&cVar`). Mesma limitação dos universos.
- **Não detecta DDL dinâmico** (`FW_AlterTable`).
- **MVP só 3 tipos** (campo/funcao/tabela). Bonus (parametro MV_*, pergunte SX1, arquivo, rotina) em release dot futura.
- **Snapshot do índice** — pra ver mudanças recentes, `plugadvpl ingest --no-incremental` antes.

## Próximos passos sugeridos

- `/plugadvpl:impacto <campo>` — quando trace de campo retornar muitas U2 hits e precisa drilldown
- `/plugadvpl:arch <fonte>` — pra cada U1 hit relevante (workflow + tabelas + lint)
- `/plugadvpl:execauto --routine X` — quando trace de função retornar `via_execauto`
