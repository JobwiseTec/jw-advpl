# Spec — `plugadvpl migrate-tlpp` (migrador ADVPL clássico → TLPP moderno)

**Data:** 2026-05-31 · **Versão alvo:** v0.18.0 · **Estado:** Draft (aguarda aprovação)

**Decisões consolidadas via brainstorm:** MVP completo (SAFE + IDIOMS, sem MVC StaticCall) · Pipeline ts-migrate-style (4 subcomandos) · Reusar material TOTVS oficial + atribuir.

---

## 1. Problema

Migração de código ADVPL clássico (`.prw`, `User Function X()`, `Local cVar`, `Begin Sequence`) pra TLPP moderno (`.tlpp`, `function u_x()`, classes/namespaces/annotations, `try/catch`, tipagem opcional) é hoje **100% manual** no ecossistema TOTVS:

- **TOTVS oficial:** tem skill knowledge `engpro-advpl-tlpp-skills/skills/advpl-tlpp/advpl-to-tlpp-migration/SKILL.md` (15 passos + 9.5KB de diffs em `tlpp-migration-patterns.md`) — mas é LLM-guided, sem auto-fix executável.
- **tds-vscode:** sem refactor/code-action ADVPL→TLPP.
- **Sonar TOTVS:** sem regra "use TLPP equivalent".
- **`advpls` CLI:** sem `--migrate` / `--upgrade` / `--fix`.
- **Comunidade:** padrão dominante é "Strangler Fig" gradual (TOTVS endossa: "não há urgência"). Maioria dos repos vive com `.prw` + `.tlpp` lado-a-lado.
- **Único competidor:** [`thalysjuvenal/advpl-specialist`](https://github.com/thalysjuvenal/advpl-specialist) (155★) com comando `/advpl-specialist:migrate` — mas é **AI-driven** (LLM faz, sem regex/AST, não-reproduzível).

**Posicionamento plugadvpl:** seremos **os primeiros com migrador determinístico, reproduzível, com auto-validação via `plugadvpl compile`** — ortogonal e complementar ao knowledge oficial TOTVS (reusamos e atribuímos), superior ao concorrente AI-driven em garantias de equivalência semântica.

---

## 2. Decisões consolidadas

### 2.1 Escopo MVP: SAFE + IDIOMS (sem MVC StaticCall)

| Categoria | Recipes incluídos no MVP | Excluído do MVP |
|---|---|---|
| **SAFE (mecânico, default)** | rename `.prw`→`.tlpp` · encoding cp1252→utf-8 · `User Function X()` → `function u_x()` (preservando truncamento se chamada externa detectada) · `:=` → `=` em named-args (se appserver ≥20.3.2.0) · remover `PUBLIC` default · header `protheus.ch` → `totvs.ch`/`tlpp-core.th` | — |
| **IDIOMS (judgment, opt-in `--idioms`)** | `Begin Sequence ... End Sequence` → `try/catch` · namespace inferido por path do arquivo · `ConOut` → `FwLogMsg` · `JsonObject():New()` chain → JSON inline `{ "id": "x" }` · expansão de nomes truncados se SEM caller externo | MVC `Static Function StaticCall` → `namespace.func()` (perigoso, exige check de appserver ≥12.1.2410; v0.19.x) |

### 2.2 UX: pipeline ts-migrate-style (4 subcomandos)

```
plugadvpl migrate-tlpp init <projeto>     # analisa, gera report, não toca em nada
plugadvpl migrate-tlpp rename <arquivo>   # só rename + encoding (mais conservador)
plugadvpl migrate-tlpp recipes <arquivo>  # aplica transformações (diff por default; --write aplica)
plugadvpl migrate-tlpp todos              # lista débitos `@plugadvpl-todo` pendentes no projeto
```

Cada subcomando é etapa independente — user controla granularidade. Idioma familiar pra quem usou `ts-migrate`/`jscodeshift`.

### 2.3 Material TOTVS: reusar + atribuir

Nossos recipes implementam **exatamente os 15 passos da skill oficial TOTVS** (`engpro-advpl-tlpp-skills/skills/advpl-tlpp/advpl-to-tlpp-migration/SKILL.md`), com atribuição explícita na `skills/migrate-tlpp/SKILL.md` (link externo + crédito). Garante alinhamento + zero risco de divergência semântica + good citizenship no ecossistema TOTVS.

---

## 3. Arquitetura

### 3.1 Módulos novos

- **`cli/plugadvpl/migrate_tlpp.py`** (~250 linhas) — orquestrador. Carrega recipes, aplica em ordem, coleta resultados, gera diff/sumário.
- **`cli/plugadvpl/migrate_tlpp_recipes/`** (pacote novo) — cada recipe é arquivo Python isolado, testável, com ID estável. Estrutura inicial:
  ```
  migrate_tlpp_recipes/
    __init__.py           # registry + RecipeBase
    rename_extension.py   # SAFE: .prw → .tlpp
    convert_encoding.py   # SAFE: cp1252 → utf-8 (delega pra edit_prw)
    user_function.py      # SAFE: User Function X() → function u_x()
    named_args.py         # SAFE: := → = em chamadas (gated por --tlpp-version)
    remove_public.py      # SAFE: PUBLIC default → omitir (TLPP private por default)
    header_includes.py    # SAFE: protheus.ch → totvs.ch + tlpp-core.th
    begin_sequence.py     # IDIOMS: Begin Sequence/End Sequence → try/catch
    namespace_infer.py    # IDIOMS: adiciona namespace baseado em path
    conout_to_fwlog.py    # IDIOMS: ConOut → FwLogMsg
    json_inline.py        # IDIOMS: JsonObject():New() chain → {"id":"x"}
    expand_truncated.py   # IDIOMS: nomes truncados em 10c → nome completo (se sem caller externo)
  ```

- **`cli/plugadvpl/migrate_tlpp_diff.py`** (~80 linhas) — wrapper sobre `difflib.unified_diff` com colorização opcional via `rich.syntax.Syntax`. Output via streams: stderr (decorativo/rich) ou stdout (diff puro pra piping).

### 3.2 Surfaces reusados (do report interno)

| Surface existente | Como migrate-tlpp usa |
|---|---|
| `parsing/parser.py::extract_functions` | Detecta `User Function`, `Static Function`, `Method` — input pra recipes |
| `parsing/parser.py::extract_namespace` | Confirma se arquivo já tem namespace (idempotência) |
| `parsing/parser.py::extract_rest_endpoints` | Detecta `WSMETHOD` legado → candidato a `@Get/@Post` |
| `edit_prw.py::convert_and_save` | Rename + encoding atômico com backup `.bak` automático |
| `compile.py::run` (modo `appre`) | **Safety gate** — valida `.tlpp` gerado antes de marcar como sucesso |
| `parsing/lint.py` (BP-001/002/005, SEC-001, MOD-001/002, WS-001/002/003) | Pre-flight: bloqueia migração se SEC-001 (RpcSetEnv em WSRESTFUL) ou SEC-004 (creds hardcoded) presentes |
| `db.py` tabela `chamadas` | Impact analyzer: lista callers da função migrada |
| `output.py::render` | Sumário final em JSON/table/md |
| `skills/advpl-tlpp/` + `advpl-tlpp-named-params/` | Knowledge base existente — skill `migrate-tlpp` faz cross-link |

### 3.3 RecipeBase (contrato interno)

```python
from dataclasses import dataclass
from typing import Literal
from pathlib import Path

@dataclass(frozen=True)
class RecipeResult:
    recipe_id: str
    status: Literal["ok", "nochange", "skipped", "error", "needs-review"]
    diff: str = ""              # unified diff before→after (vazio se nochange)
    message: str = ""           # descrição humana
    todo_markers: list[str] = field(default_factory=list)  # débitos gerados

class RecipeBase:
    id: str                     # estável, kebab-case (ex: "user-function-lowercase")
    category: Literal["safe", "idioms"]
    description: str            # 1 linha
    requires_tlpp_version: tuple[int, int, int] | None = None  # ex: (20, 3, 2)

    def apply(self, content: str, file_path: Path, ctx: MigrationContext) -> RecipeResult:
        ...
```

### 3.4 CLI detalhado

#### `plugadvpl migrate-tlpp init <projeto>`

Analisa todos os `.prw`/`.prx` no projeto, NÃO toca em nada. Output (JSON ou table):

| arquivo | candidato | recipes_que_aplicariam | blockers (lint) | impact (callers externos) |
|---|---|---|---|---|
| src/SIGAFAT/MT460FIM.prw | sim | 6 recipes | nenhum | 2 callers em outros .prw |
| src/SIGAFIN/AXCAD001.prw | parcial | 4 recipes | SEC-001 RpcSetEnv → bloqueado | 0 |
| src/utils/lib.prw | sim | 8 recipes | nenhum | 12 callers (alta importância) |

Flags: `--format json|table|md` (default table), `--idioms` (inclui idioms na análise), `--tlpp-version 20.3.2` (filtra recipes compatíveis).

#### `plugadvpl migrate-tlpp rename <arquivo>`

Apenas rename + encoding (`SAFE-rename` recipe + `SAFE-encoding`). Não toca em conteúdo de código. **Já cria backup** via `edit_prw.convert_and_save(backup=True)`. Útil pra equipes que querem migrar **encoding e extensão** primeiro, código depois (Strangler Fig amigável).

Flags: `--write` (default false = só mostra rename target + diff de encoding); `--validate` (após write, roda `compile` em modo `appre` no `.tlpp` resultante — mesma semântica de `recipes --validate`).

#### `plugadvpl migrate-tlpp recipes <arquivo>`

Aplica recipes de transformação. Sem `--write`, mostra diff unificado. Com `--write`, aplica e roda `compile` se `--validate`.

Flags principais:
- `--write` — aplica (default: diff-only)
- `--idioms` — habilita recipes IDIOMS além de SAFE
- `--recipe <id>` — aplica recipe específico (repetível); sem flag aplica all
- `--tlpp-version <X.Y.Z>` — gating de recipes (named-args ≥20.3.2.0, classes via `New()` ≥24.3.1.0)
- `--validate` — após write, roda `plugadvpl compile <novo.tlpp>` em modo `appre`; se falhar, rollback automático via backup
- `--allow-dirty` — permite working tree dirty no git (default exige clean)
- `--format json|table|md` — formato do sumário

Sumário final categorizado (jscodeshift-style):

```
plugadvpl migrate-tlpp recipes src/ --write --idioms

✓ Working tree limpo. Backup .bak criado por arquivo.
✓ rename-extension          5 ok    0 nochange  0 skipped  0 error
✓ convert-encoding          5 ok    0 nochange  0 skipped  0 error
✓ user-function-lowercase   5 ok    0 nochange  0 skipped  0 error
✓ named-args                3 ok    2 skipped (appserver <20.3.2.0)
⚠ begin-sequence-to-try     4 ok    1 needs-review (aninhado complexo)
✗ namespace-infer           4 ok    1 error (arquivo sem path indicativo)

Total: 5 arquivos · 6 recipes · 26 transformações · 1 needs-review · 1 error
@plugadvpl-todo markers: 2

Próximos passos:
  - plugadvpl migrate-tlpp todos               # lista débitos
  - plugadvpl compile src/                     # valida tudo
  - git diff                                   # revisa antes de commit
```

#### `plugadvpl migrate-tlpp todos`

Varre todo o projeto procurando markers `// @plugadvpl-todo:` em `.tlpp` gerados (ou `// @plugadvpl-todo:` se TLPP usar `//`; precisamos confirmar) e lista débitos pendentes.

Output:
```
src/SIGAFAT/MT460FIM.tlpp:42  begin-sequence-to-try: bloco aninhado dentro de bloco — revisar manualmente
src/utils/lib.tlpp:108        namespace-infer: path utils/ é ambíguo — defina namespace manualmente
```

### 3.5 Recipes detalhados (MVP)

#### SAFE (default, sempre aplicam)

| Recipe ID | Transformação | Risco | Reusa |
|---|---|---|---|
| `rename-extension` | `arquivo.prw` → `arquivo.tlpp` (renomeia arquivo no FS) | Nenhum (rename atômico via `Path.rename`) | `edit_prw` |
| `convert-encoding` | cp1252 → utf-8, BOM-less | Nenhum (backup `.bak` automático) | `edit_prw.convert_and_save` |
| `user-function-lowercase` | `User Function FATA050()` → `function u_fata050()` | Baixo. Se `FATA050` chamada por outro arquivo, mantém nome (truncado a 10 chars original); senão expande | parser `extract_functions` + DB `chamadas` |
| `named-args` (gated `--tlpp-version=20.3.2+`) | `XYZ(p1 := a, p2 := b)` em callsites → `XYZ(p1=a, p2=b)` | Médio. Só callsites onde **caller** é TLPP (em chamadas ADVPL→ADVPL, mantém `:=`) | parser + analise tipo arquivo |
| `remove-public-default` | `PUBLIC cVar` → `cVar` (TLPP private por default) | Baixo. Só `Local`/`Static` mantém kw; `PUBLIC` explícito vira default | regex |
| `header-includes` | `#Include "protheus.ch"` → `#Include "totvs.ch"` + `#Include "tlpp-core.th"` se TLPP recursos detectados | Nenhum | regex |

#### IDIOMS (opt-in `--idioms`)

| Recipe ID | Transformação | Risco | Estratégia |
|---|---|---|---|
| `begin-sequence-to-try` | `Begin Sequence ... Recover ... End Sequence` → `try { } catch (e) { }` | Médio. Se aninhado profundamente, gera `@plugadvpl-todo` | tokenizer + match balanceado |
| `namespace-infer` | Adiciona `namespace custom.<modulo>.<nome>` baseado em path do arquivo (`src/SIGAFAT/MT460FIM.prw` → `custom.sigafat.mt460fim`) | Médio. Se path não indicativo, gera `@plugadvpl-todo` | parser + heurística path |
| `conout-to-fwlog` | `ConOut("msg")` → `FwLogMsg("info", "msg")` | Baixo. Wrapper trivial | regex |
| `json-inline` | `oJson := JsonObject():New(); oJson["id"] := 1` → `oJson := { "id": 1 }` | Médio. Só padrões simples; chains com loops geram `@plugadvpl-todo` | parser AST-ish |
| `expand-truncated-names` | `FATA050ENVKAFKA` (clipped pelos 10c em ADVPL) → nome completo em TLPP | Médio. Só se função NÃO tem caller externo (DB query) | DB `chamadas` cross-file |

### 3.6 Ordem canônica de aplicação (recipes orquestradas topologicamente)

Recipes têm dependências implícitas — orquestrador **IGNORA ordem em que vêm via `--recipe` repeats** e aplica sempre na ordem fixa abaixo (topological sort). Fixes CRITICAL identificados pelo spec-reviewer:

| # | Recipe | Por que essa posição |
|---|---|---|
| 1 | `convert-encoding` | DEVE ser primeiro: lê cp1252 e converte. Se feito depois de `rename`, `edit_prw` assume utf-8 pela extensão `.tlpp` → mojibake nos acentos. |
| 2 | `rename-extension` | Imediatamente após encoding (parou de ser cp1252) |
| 3 | `header-includes` | Antes de `namespace-infer` (que pode depender de quais includes existem) |
| 4 | `remove-public-default` | Independente; cedo pra reduzir ruído nas etapas seguintes |
| 5 | `user-function-lowercase` | Antes de `expand-truncated-names` (que valida callers; lowercase não afeta calls) |
| 6 | `named-args` | Independente; antes de modificações estruturais |
| 7 | `namespace-infer` | Depois de `header-includes`; antes de mudanças em corpo de função |
| 8 | `begin-sequence-to-try` | Antes de `conout-to-fwlog` (que vai recolher ConOuts dentro de catches) |
| 9 | `conout-to-fwlog` | Depois de try/catch resolvido — captura ConOut em handlers de erro corretamente |
| 10 | `json-inline` | Cosmetico tardio; precisa que JsonObject chains estejam isolados |
| 11 | `expand-truncated-names` | **Último** — consulta DB `chamadas` (que ainda referencia nome antigo); só seguro após todos outros recipes terem estabilizado o arquivo |

`migrate-tlpp recipes --recipe X --recipe Y` aplica X e Y na ordem canônica acima, NÃO na ordem dos flags.

### 3.7 Convivência com workflow `edit-prw` existente

`migrate-tlpp` delega internamente a `edit_prw.convert_and_save` pra encoding. Cenários:

| Estado antes de `migrate-tlpp recipes` | Comportamento |
|---|---|
| `.prw` em cp1252 (estado normal) | Roda recipe `convert-encoding` normalmente |
| `.prw` já em utf-8 (user fez `edit-prw stage` antes e esqueceu de commit) | Detecta via BOM/heurística; **pula** `convert-encoding` com status `nochange`; continua restantes |
| `.prw.bak` órfão de `edit-prw stage` anterior | Preserva; cria backup `.bak.<timestamp>` (não sobrescreve) |
| Working tree dirty (user editou mas não committou) | Bloqueia sem `--allow-dirty`; com flag, prossegue mas warning explícito |

Workflows compostos válidos:
1. `edit-prw stage <arq>` → user edita manual → `edit-prw commit <arq>` → `migrate-tlpp recipes <arq> --write` (caso normal).
2. `migrate-tlpp recipes <arq> --write --validate` → revisar diff → `git commit` (caso direto).

---

## 4. Safety gates + erro handling

### 4.1 Pre-flight (antes de qualquer write)

1. **Git working tree limpo** — `git status --porcelain` deve estar vazio. Override: `--allow-dirty` (warning explícito).
2. **Backup `.bak.<YYYYMMDDHHMMSS>`** — via `edit_prw.convert_and_save(backup=True, timestamp=True)` (extensão nova; `edit_prw` precisa ser estendido pra suportar timestamp). Se `.bak` legado sem timestamp já existir, preservar — NÃO sobrescrever. Rollback (§4.2) sempre usa o `.bak.*` MAIS ANTIGO disponível pra evitar restaurar versão já parcialmente migrada de re-run anterior.
3. **DB `chamadas` populado (CRITICAL)** — recipes `user-function-lowercase` e `expand-truncated-names` dependem de DB pra evitar quebrar chamadas externas silenciosamente. Se `db.is_ingested()` for `False`, comportamento:
   - **Default (conservador):** aborta com mensagem `Execute 'plugadvpl ingest' antes de migrar` + exit code 3.
   - **Override `--no-impact-check`:** prossegue, mas `expand-truncated-names` vira `skipped` e `user-function-lowercase` **sempre preserva nome truncado** (gera `@plugadvpl-todo: expandir nome após confirmar manualmente`). Warning loud no stderr.
4. **Lint pre-flight** — se arquivo tem `SEC-001` (RpcSetEnv em WSRESTFUL) ou `SEC-004` (hardcoded credentials), **rejeita migração** (status `skipped` com razão). Esses padrões são incompatíveis com TLPP ou precisam human review primeiro.
5. **Caller detection (`user-function-lowercase`)** — após DB confirmado populado, antes de expandir nome truncado, consulta DB `chamadas` pra ver se função é chamada por outro arquivo. Se sim, mantém nome truncado e gera `@plugadvpl-todo: expandir nome após coordenar com callers` no header da função.

### 4.2 Post-flight (após write, se `--validate`)

1. Roda `compile.run(CompileRequest(files=[novo.tlpp], mode="appre"))` automaticamente.
2. Se `exit_code != 0`, **rollback automático** restaurando o `.bak.<timestamp>` MAIS ANTIGO E renomeando `.tlpp` de volta pra `.prw`. Recipe vira status `error` com razão.
3. Se `exit_code == 0`, recipe é `ok` confirmado. Backup `.bak.*` mantido (user remove manual se quiser).

### 4.2.4 Rollback que falha (defesa em profundidade)

Cenários: `.bak.*` deletado pelo user entre runs, FS read-only, permissão negada na restauração.

Cascata de fallbacks:
1. **Tentativa primária:** restore via `.bak.<timestamp>` mais antigo + `Path.rename` reverso `.tlpp` → `.prw`.
2. **Fallback 1 — git:** se primary falhar, tenta `git checkout HEAD -- <path>` (motivo de exigir working tree limpo em §4.1.1; user pode usar `--allow-dirty` mas sabe que perdeu safety).
3. **Fallback 2 — abort loud:** se ambos falharem, exit code **2** com mensagem `CRITICAL: rollback falhou; arquivo está em estado intermediário. Restaure manualmente de <lista de paths tentados>`.

Test em integration cobre os 3 caminhos.

### 4.3 NEVER-propagate

Padrão estabelecido nas Fases multi-agente (v0.16.x): top-level `try/except` em todo subcomando `migrate-tlpp`. Falha catastrófica nunca quebra outras invocações; `init`/`status` continuam funcionando.

### 4.4 Markers de débito `@plugadvpl-todo`

**Sintaxe TLPP confirmada:** TLPP moderno aceita `//` line comments em qualquer coluna (per spec TL++, complementa o `*` legacy ADVPL que exige column 1). Markers usam `//` consistentemente.

Quando recipe não consegue 100%, INSERE comentário no código TLPP gerado:

```
// @plugadvpl-todo:begin-sequence-to-try aninhamento complexo - revisar manualmente
try
    // código convertido aqui
catch (e)
    ConOut(e:Description)
end
```

Test snapshot obrigatório: arquivo `.tlpp` com markers `//` PASSA `plugadvpl compile <arq>` em modo `appre`. Bloqueia regressão de marker syntax errada.

`plugadvpl migrate-tlpp todos` varre todos `@plugadvpl-todo` no projeto e lista pra resolver iterativamente. NÃO bloqueia migração.

---

## 5. Tests (estimativa ~50 novos)

### Unit (~35)
- `test_migrate_tlpp_recipes.py` — 3 tests por recipe × 11 recipes = ~33 (cobre transformação OK + nochange + edge case)
- `test_migrate_tlpp_diff.py` — 2 tests (diff vazio quando nochange, diff colorizado quando muda)

### Integration (~15)
- `TestMigrateTlppInit` — 3 tests (projeto sintético com mix, output table/json, filtro `--idioms`)
- `TestMigrateTlppRename` — 2 tests (rename + encoding, sem write é diff-only)
- `TestMigrateTlppRecipes` — 5 tests (SAFE only, SAFE+IDIOMS, `--write` aplica + valida, `--validate` rollback se compile falha, `--allow-dirty` override)
- `TestMigrateTlppTodos` — 2 tests (lista vazios em projeto sem markers, lista com markers)
- `TestMigrateTlppRoundtrip` — 3 tests (migrate + compile + revert = idempotente; idempotência sob 2x runs; backup `.bak` correto)

### Snapshots (~5)
- 5 fixtures `.prw` reais sintéticos cobrindo padrões típicos (User Function simples, Static Function com Begin Sequence, classe ADVPL, WSMETHOD, JsonObject chain). Snapshot do `.tlpp` resultante via syrupy.

---

## 6. Tamanho estimado

| Componente | Linhas (~) |
|---|---|
| `cli/plugadvpl/migrate_tlpp.py` (orquestrador) | 250 |
| `cli/plugadvpl/migrate_tlpp_diff.py` | 80 |
| `cli/plugadvpl/migrate_tlpp_recipes/` (11 recipes + base) | 800 |
| `cli/plugadvpl/cli.py` (4 subcommands wiring) | 250 |
| `cli/tests/unit/test_migrate_tlpp_*.py` | 600 |
| `cli/tests/integration/test_cli.py` (4 classes) | 400 |
| `cli/tests/fixtures/migrate_tlpp/*.prw` + snapshots | 300 |
| `skills/migrate-tlpp/SKILL.md` | 200 |
| `docs/superpowers/plans/2026-05-31-migrate-tlpp-implementation.md` | 600 |
| `CHANGELOG.md` + `README.md` (entry + cobertura) | 80 |
| **Total** | **~3500 linhas** |

**Cronograma:** ~6-8 dias focados (1 dia spec + plan + reviewer; 3 dias recipes + unit tests; 1-2 dias CLI + integration tests; 1 dia rollback-of-rollback tests + edge cases; 1 dia release polish). Estimativa ajustada (era 4-5) — recipes ADVPL/TLPP têm edge cases que regex puro não cobre, baseline v0.17.0 (~880 linhas em 1 dia) extrapolada com penalty pra complexidade de parsing.

---

## 7. Critérios de sucesso

1. `plugadvpl migrate-tlpp init src/` lista candidatos + blockers + impact em < 5s pra projeto de 100 `.prw`.
2. `plugadvpl migrate-tlpp recipes <arq> --write --validate --idioms` aplica recipes, valida compile, faz rollback automático se quebra, gera sumário categorizado.
3. Roundtrip: `git revert HEAD` (working tree limpo, caso primário) OU restore via `.bak.<timestamp>` (fallback caso `--allow-dirty`) restauram 100% do `.prw` original. Git é primary, `.bak` é defesa em profundidade (§4.2.4).
4. Markers `@plugadvpl-todo` são listáveis via `migrate-tlpp todos` e legíveis pra LLM resolver iterativamente.
5. Atribuição TOTVS oficial na skill — link pra `engpro-advpl-tlpp-skills/skills/advpl-tlpp/advpl-to-tlpp-migration/SKILL.md` + crédito.
6. Suite full: 1216 → ~1266 passed (+50 testes novos).
7. Lint scope (issue #17): novos arquivos (`migrate_tlpp.py`, `migrate_tlpp_diff.py`, `migrate_tlpp_recipes/*.py`) adicionados ao `LINT_FILES` desde início.

---

## 8. Out of scope (v0.18.0, fica pra futuro)

- **MVC `StaticCall` → namespace** (perigoso, exige check appserver ≥12.1.2410; v0.19.x).
- **Classes ADVPL → classes TLPP modernas** (com modificadores, herança, interfaces — complexo, v0.19.x ou v0.20.x).
- **`@Get`/`@Post` annotations em WSRESTFUL** (precisa parser mais profundo de URL mapping; v0.19.x).
- **Tipagem opcional** (`as Type`) — exige type inference real, não temos AST; v0.20.x.
- **Migração `Begin Transaction` → `try/finally` com commit/rollback** (semântica não-trivial; v0.19.x).
- **Cross-file refactor** (mover funções pra namespaces baseado em uso) — exige cross-file AST; v0.21.x+.
- **Integração interativa** (pergunta ao user a cada recipe `[y/n]`) — preferimos modo batch + diff (estilo Unix).

---

## 9. Atribuição + licença

**Pré-requisito antes de v0.18.0 ship:** confirmar licença do material `totvs/engpro-advpl-tlpp-skills`. Spec assume compatibilidade até verificação; abrir issue bloqueante na fase de planning.

Crédito explícito no `skills/migrate-tlpp/SKILL.md` (usar **permalinks com commit SHA fixo**, não `tree/main`):

> Implementação dos 15 passos canônicos descritos pela **TOTVS Engenharia de Produto** em [engpro-advpl-tlpp-skills/skills/advpl-tlpp/advpl-to-tlpp-migration](https://github.com/totvs/engpro-advpl-tlpp-skills/blob/<COMMIT-SHA>/skills/advpl-tlpp/advpl-to-tlpp-migration/SKILL.md). Padrões de transformação derivados de [tlpp-migration-patterns.md](https://github.com/totvs/engpro-advpl-tlpp-skills/blob/<COMMIT-SHA>/skills/advpl-tlpp/advpl-to-tlpp-migration/references/tlpp-migration-patterns.md). Material TOTVS sob licença `<X verificada em <data>>`; plugadvpl é MIT — derivação compatível confirmada. plugadvpl adiciona auto-fix executável, diff/dry-run UX, validação via `plugadvpl compile`, e impact analyzer reverso via DB.

Resolver `<COMMIT-SHA>` e `<X>` durante implementação (LICENSE check + git ls-remote no commit atual da main TOTVS).

---

## 10. Histórico de decisões

- **2026-05-31 (manhã):** Research multi-modal (4 agents paralelos: TOTVS oficial, comunidade, padrões cross-language, surfaces internas). Decisões consolidadas via brainstorm: MVP completo (SAFE + IDIOMS, sem MVC) · pipeline ts-migrate-style · reusar material TOTVS + atribuir. Spec escrito.
- **2026-05-31 (tarde):** Spec-reviewer encontrou 3 CRITICAL + 3 IMPORTANT + 4 NIT. Fixes aplicados:
  - §3.6 Ordem canônica de aplicação (11 recipes topologicamente sorted) — fix CRITICAL combinações tóxicas.
  - §3.7 Convivência com `edit-prw` workflow.
  - §4.1.2 Backup `.bak.<timestamp>` (não sobrescreve `.bak` legado).
  - §4.1.3 Pre-flight de DB `chamadas` populado (CRITICAL — caller detection silently breaks).
  - §4.2.4 Rollback-of-rollback via git checkout fallback + abort loud (exit code 2).
  - §4.4 Confirmação `//` como marker syntax válido em TLPP moderno + snapshot test obrigatório.
  - §6 Estimativa ajustada 4-5 → 6-8 dias (penalty pra parsing complexity).
  - §7 critério 3 reescrito (git primary, `.bak` fallback).
  - §3.4 `--validate` adicionado a `rename` (era só `recipes`).
  - §9 Permalinks com commit SHA + verificação de licença bloqueante.
- **Pendente:** user approval → plan implementation MD → subagent-driven-development → release v0.18.0.

---

**Próximos passos:** spec-reviewer → fixes → user approval → writing-plans skill → implementação.
