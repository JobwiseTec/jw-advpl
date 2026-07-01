# Spec — SX completo + análises de chave/índice/integridade

> Brainstorming aprovado em 2026-06-15. Autor do contexto: Joni (mantenedor).
> 3 sub-projetos sequenciais (base→topo), 1 issue + 1 PR cada, TDD.

## Motivação

O índice SX do plugadvpl hoje é **incompleto**: faltam colunas-chave de SX2/SX3/SX9 que
travam análises de **chave única, integridade referencial e performance de índice**. Trazer
esses dados (fundação) destrava lints que pegam dívida técnica real: campos F3 órfãos, chaves
duplicadas, queries sem índice SIX, relacionamentos quebrados.

**Princípios** (herdados): determinístico/offline; só customizações do cliente (padrão TOTVS
fora por design/IP); saída JSON estruturada; TDD; reusa fixtures e o padrão de regras `SX-*`
cross-file existentes.

---

## Sub-projeto 1 — Ingestão SX completa *(fundação)* — Issue #1

Adicionar as colunas faltantes, mapear nos parsers, expor nas queries, atualizar o exporter.

### Colunas novas

| Tabela | Coluna (DB) | Origem SX | Semântica |
|--------|-------------|-----------|-----------|
| `tabelas` (SX2) | `unico` | X2_UNICO | expressão da chave única (anti-duplicidade) |
| `tabelas` (SX2) | `modo_unico` | X2_MODOUN | modo da unicidade (compart./exclusivo) |
| `tabelas` (SX2) | `modo_emp` | X2_MODOEMP | modo empresa (multi-empresa) |
| `campos` (SX3) | `ordem` | X3_ORDEM | ordem de exibição no browse/folder |
| `campos` (SX3) | `inibrw` | X3_INIBRW | inicializador de browse |
| `campos` (SX3) | `relacao` | X3_RELACAO | autofill por expressão/relação (distinto de X3_INIT) |
| `relacionamentos` (SX9) | `usa_filial` | X9_USEFIL | usa filial no relacionamento |
| `relacionamentos` (SX9) | `vincula_filial` | X9_VINFIL | vincula filial (pai/filho cross-filial) |
| `relacionamentos` (SX9) | `chave_estrangeira` | X9_CHVFOR | chave estrangeira do relacionamento |

> **Correção do review:** `campos.inicializador` = **X3_INIT** (com X3_RELACAO só como fallback legado em `parse_sx3`). Logo, em dumps modernos o **X3_RELACAO é perdido** — por isso adicionamos `relacao` como coluna própria (9 colunas no total: 3 SX2 + 3 SX3 + 3 SX9).

### Entregáveis
- **Migration** nova (`0NN_sx_extras.sql`): `ALTER TABLE` × 3 (tabelas/campos/relacionamentos), com `DEFAULT ''`.
- **Parsers** `parsing/sx_csv.py`: `parse_sx2`/`parse_sx3`/`parse_sx9` passam a extrair as colunas novas (case-insensitive no header do CSV; ausência → `''`).
- **Spec de ingest** `ingest_sx.py`: incluir as colunas novas nas listas de escrita.
- **Exporter** `docs/reference-impl/coletadb.tlpp`: adicionar X2_UNICO/MODOUN/MODOEMP, X3_ORDEM/INIBRW, X9_USEFIL/VINFIL/CHVFOR ao dump SX (hoje não exporta).
- **Exposição**: incluir os campos novos na saída JSON de `tables --catalog` / `trace` quando relevantes.
- **Migration de versão de schema** + bump SCHEMA_VERSION.

### Testes (TDD)
Por parser: CSV-fixture com as colunas novas → linhas gravadas com os valores; CSV sem as colunas → `''` (graceful). Integração: `ingest-sx` numa pasta-fixture popula as colunas.

---

## Sub-projeto 2 — Lints de integridade & chave — Issue #2

Regras cross-file no padrão `SX-*` (já existem 11). Requer SX1 ingerido; `SX-DUPKEY` usa `tabelas.unico`.

### Regras
1. **`SX-F3ORPHAN`** (warning) — `campos.f3` (X3_F3) preenchido mas a consulta SXB referenciada **não existe** em `consultas` → F3 quebra em runtime (tecla F3 sem retorno).
2. **`SX-DUPKEY`** (warning) — fonte grava (`RecLock(...,.T.)`/`DbAppend`) numa tabela com `tabelas.unico` definido **sem** checar a chave única antes (`DbSeek`/`ExistCpo`/query da chave) → risco de duplicar chave única.
3. **`SX-RELORFA`** (error) — `relacionamentos` (SX9) apontando para `tabela_destino`/campo inexistente no dicionário → relacionamento órfão.

### Comando
- **`plugadvpl rel <tabela>`** (+ skill): mostra **pais e filhos** via `relacionamentos` (usando `usa_filial`/`vincula_filial`/`chave_estrangeira`), e valida `ExistCpo` dos campos citados nas expressões. Saída JSON. (Alternativa: enriquecer `trace` em vez de comando novo — decidir na impl.)

### Testes (TDD)
Fixture SX + fonte sintético: F3 órfão dispara `SX-F3ORPHAN`; grava em tabela `unico` sem seek → `SX-DUPKEY`; SX9 p/ tabela inexistente → `SX-RELORFA`; `rel` lista pais/filhos corretos.

---

## Sub-projeto 3 — Cobertura de índice SIX *(performance)* — Issue #3

Cruzar SQL embarcado (`sql_embedado`) com índices SIX (`indices.chave`).

### Regra
- **`PERF-IDX`** (warning) — query (`BeginSql`/`TCQuery`) cujo **WHERE/JOIN filtra por colunas que não casam o início (campos-líderes) de nenhum índice SIX** da tabela → full scan provável. Sugere o índice existente que cobriria, ou alerta "sem índice".
- **Guard ao customizar** — quando o `advpl-code-generator`/sugestão gerar uma query, checar cobertura de índice antes de entregar (cruza com `advpl-embedded-sql`).

### Abordagem (decidida: A — heurística)
Extrair nomes de coluna do WHERE/JOIN do snippet de `sql_embedado` (heurístico, regex sobre `%table%`/aliases) e casar contra os campos-líderes de `indices.chave` (split por `+`). Leve, reusa dados existentes; sem parser SQL AST (frágil com macro-linguagem BeginSql).

### Testes (TDD)
Fixture: query filtrando por coluna coberta por índice → sem finding; filtrando por coluna sem índice → `PERF-IDX` sugerindo o índice mais próximo (ou alerta).

---

## Notas do review da spec (incorporadas — não esquecer na impl)

- **F3-órfão (SP2), decisão de interpretação:** `X3_F3` referencia uma consulta **SXB** (`consultas`), não SX9 diretamente. Há 2 checks distintos: (i) `X3_F3` aponta p/ SXB inexistente — **provavelmente já é a regra SX-011 existente** (verificar antes de duplicar); (ii) campo com `X3_F3` mas **sem relacionamento SX9** que ligue à tabela do F3 — é o que o usuário pediu literalmente ("F3 e não tem SX9"). **SP2 implementa (ii)**; conferir SX-011 p/ não duplicar (i).
- **SX-DUPKEY (SP2), precisão:** `tabelas.unico` (X2_UNICO) é uma **expressão ADVPL** (ex.: `A1_FILIAL+A1_COD`), não um flag. A regra é **function-local** (heurística intra-procedimento) e **warning/info, baixa precisão** — assume falso-positivo em `GetSx8Num`/numerador, `MsExecAuto`/MVC, e seek em outra função. Escopo: gravação em tabela com `unico` definido **sem** nenhum `DbSeek`/`ExistCpo`/query no mesmo escopo. Documentar a limitação.
- **PERF-IDX (SP3), normalização obrigatória (crux da precisão):** antes de casar colunas, **normalizar as macros do BeginSql** — `%notDel%`→ignorar (injeta `D_E_L_E_T_`), `%xfilial%`/`%exp:xfilial%`→ tratar **FILIAL como líder de índice** (senão falso-positivo em queries `xfilial+chave` perfeitamente indexadas), `%table:XXX%`→nome da tabela. Casar só o(s) **token(s) líder(es)** de `indices.chave` (split por `+`, **leftmost-prefix**; normalizar expressões tipo `DTOS(...)`). Resolver coluna→tabela em JOIN (alias). Sem isso vira ruído → começar **info-level**.
- **SX-RELORFA (SP2):** `tabela_destino` = X9_CDOM (limpo), mas o "campo" vive em `expressao_destino` (expressão) — parsear contra `campos` (mesma util de parsing de expressão usada por `rel` e DUPKEY; **construir uma vez e compartilhar**).
- **Escopo por regra:** F3ORPHAN/RELORFA = cross-file (dicionário); **DUPKEY = function-local**; PERF-IDX = por-query (`sql_embedado`). Define o desenho da fixture de teste.
- **SP2/SP3 não adicionam migration** (lints são read-side; resultados não persistem). Só **SP1 bumpa SCHEMA_VERSION**. SP3 na verdade **não depende de SP1** (usa `indices`/`sql_embedado` existentes) — pode ir antes do SP2 se conveniente.
- **Determinismo:** ordenar saídas das regras novas com chave estável (snapshot/CI). **Exporter parity:** teste que `coletadb.tlpp` emite os campos X2/X3/X9 novos (senão re-export perde os dados).

## Sequenciamento
1. **PR1 (fundação)** — Sub-projeto 1. Inclui esta spec. Fecha Issue #1.
2. **PR2 (integridade)** — Sub-projeto 2. Fecha Issue #2.
3. **PR3 (performance)** — Sub-projeto 3. Fecha Issue #3.

Cada PR: TDD (RED→GREEN), ruff/format/mypy clean, suíte full verde antes do próximo. Arquivos novos vão pro `LINT_FILES` do CI.

## Fora de escopo (anti-roadmap)
- Indexar padrão TOTVS (IP). Só customizações do cliente.
- Parser SQL AST completo (escolhemos heurística).
- Reescrever rotinas; o plugin **detecta/sugere**, não reescreve sozinho.
