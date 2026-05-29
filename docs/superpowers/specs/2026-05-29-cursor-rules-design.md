# Cursor Rules nativos no `plugadvpl init` — Design

**Data:** 2026-05-29
**Versão alvo:** v0.16.2 (patch — adição compatível)
**Predecessor:** v0.16.1 entregou AGENTS.md gêmeo (cobre Codex que já lê AGENTS.md). Este spec ataca a próxima fase: **Cursor com integração nativa via `.cursor/rules/*.mdc`**.
**Fora de escopo deste spec:** GitHub Copilot (fase separada), distribuição via marketplaces externos, MCP server.

---

## 1. Problema

O plugadvpl é um plugin Claude Code + CLI Python. A v0.16.1 entregou `AGENTS.md` gêmeo do `CLAUDE.md` — Codex CLI (que lê AGENTS.md nativamente) passou a funcionar com nossas convenções.

**Mas Cursor e GitHub Copilot não consomem AGENTS.md como mecanismo primário.** Cursor tem seu próprio formato: `.cursor/rules/*.mdc` com frontmatter YAML, escopo por glob, e injeção contextual condicional. Sem rules nativas, o usuário Cursor abre um projeto Protheus sem nenhum contexto do plugadvpl — nem sabe que existe um índice consultável, nem que `.prw` é cp1252, nem qual comando rodar antes de `Read`.

**Objetivo:** com 1 `plugadvpl init`, o usuário Cursor deve ter contexto equivalente ao Claude Code — comandos, convenções, encoding, tabela de decisão — entregue no idioma nativo do Cursor (Rules, não fragment markdown).

---

## 2. Decisões de produto (fixadas no brainstorming)

| # | Decisão | Justificativa |
|---|---|---|
| 1 | **Cursor primeiro, Copilot depois** (2 specs separados) | Mecanismos bem diferentes; tentar os dois juntos diluiria foco. Copilot tem fase 2 própria. |
| 2 | **Nível de integração: alto** (comandos nativos) | Skills viram rules .mdc reais com escopo, não só convenções em texto livre. |
| 3 | **Cobertura: global + projeto** | 1 rule global em `~/.cursor/rules/plugadvpl.mdc` + 26 locais em `.cursor/rules/plugadvpl-<X>.mdc`. |
| 4 | **UX: tudo automático no `plugadvpl init`** | Detecção de Cursor + instalação sem perguntar. Zero friction. Erro silent fail. |
| 5 | **Fonte de verdade: `SKILL.md` gera `.mdc` em runtime** | Single source. Sem duplicação no repo. Transformação no client side. |
| 6 | **Detecção conservadora** | Só age com sinal explícito de Cursor (`~/.cursor/` existe ou `.cursor/` existe no projeto). |
| 7 | **Flag `--no-cursor`** | Escape válvula pra CI/usuários que não querem. |

---

## 3. Arquitetura

Quatro componentes em novo módulo `cli/plugadvpl/cursor_rules.py`:

### 3.1 `detect_cursor(project_root: Path) → CursorTarget`

Decide o que instalar e onde. Retorna dataclass frozen:

```python
@dataclass(frozen=True)
class CursorTarget:
    install_global: bool   # ~/.cursor/rules/plugadvpl.mdc
    install_local: bool    # <project>/.cursor/rules/plugadvpl-*.mdc
```

**Regras de detecção:**

| Sinal | Decisão |
|---|---|
| `Path.home() / ".cursor"` existe | `install_global = True` |
| `shutil.which("cursor")` retorna path | `install_global = True` (sinal alternativo) |
| `<project_root>/.cursor/` existe | `install_local = True` |
| Nenhum sinal | `CursorTarget(False, False)` → no-op |

**Por que conservador:** instalar `.cursor/rules/` num projeto onde o usuário nunca abriu Cursor seria intrusivo (pegada não-solicitada). Local só age quando há intent claro (`.cursor/` já existe). Global age quando Cursor já é usado em qualquer escopo da máquina.

**Cross-platform:** `pathlib.Path` + `shutil.which` cobrem Windows/macOS/Linux sem ramificações por SO.

**Erro handling:**
- `Path.home()` lança `RuntimeError` (container minimalista) → retorna `CursorTarget(False, False)`. Sem warning — é comportamento esperado.
- `shutil.which("cursor")` retorna `None` silenciosamente — comportamento padrão.

### 3.2 `render_global_rule(version: str) → str`

Gera conteúdo do `~/.cursor/rules/plugadvpl.mdc` (rule global ADVPL).

**Frontmatter:** `alwaysApply: true`, sem `globs` (vale sempre em projeto Protheus).

**Body:** reaproveita o body atual do `_CLAUDE_FRAGMENT_BODY` (já em `cli.py`, descreve tabela de decisão, encoding, workflow padrão, etc.), aplicando as mesmas substituições da §3.4 (slash → uvx, normalização de versão).

### 3.3 `render_skill_rule(skill_md_path: Path, version: str, globs: list[str]) → str`

Gera conteúdo de uma rule por skill. Pipeline puro:

**Inputs:**
- `skill_md_path`: caminho do `skills/<X>/SKILL.md` embarcado no wheel (via `importlib.resources`)
- `version`: versão runtime (`plugadvpl.__version__`)
- `globs`: lista de patterns (vem do mapping da §5; pode ser `[]`)

**Pipeline:**

1. **Parse YAML frontmatter** (formato já existente em todas as 26 SKILL.md):
   ```yaml
   ---
   description: Visao arquitetural de um arquivo ADVPL/TLPP
   disable-model-invocation: true
   arguments: [arquivo]
   allowed-tools: [Bash]
   ---
   ```
   Extrai só `description` (campo único necessário pro MDC).

2. **Extrai body** (tudo após o `---` de fechamento do frontmatter).

3. **Transformar body** com 2 substituições, **nesta ordem**:

   | Passo | De | Para |
   |---|---|---|
   | 3a | `/plugadvpl:<X>` | `` `Bash: uvx plugadvpl@<ver> <X>` `` |
   | 3b | `uvx plugadvpl@<qualquer-versão>` | `uvx plugadvpl@<ver>` |

   Ordem importa: 3a primeiro porque emite `uvx plugadvpl@<ver>` correto. 3b depois normaliza qualquer ocorrência pré-existente de versão antiga (ex: `uvx plugadvpl@0.15.0` literal em exemplo).

   Resto intocado (cabeçalhos, exemplos, tabelas, blocos de código).

4. **Montar MDC final:**
   ```mdc
   ---
   description: <da SKILL.md>
   globs: <joined por vírgula, omitido se vazio>
   alwaysApply: false
   ---
   <!-- plugadvpl-rule-version: <ver> -->
   <!-- plugadvpl-skill: <nome> -->

   <body transformado>
   ```

**Edge cases:**
- SKILL.md sem frontmatter → `description = "plugadvpl skill: <nome>"`.
- Frontmatter malformado → mesma fallback.
- Substituições usam string replaces literais (não regex multi-line) — simples e robusto.

### 3.4 `install_cursor_rules(project_root: Path, version: str) → InstallResult`

Orquestra: detecta, renderiza, escreve.

```python
@dataclass(frozen=True)
class InstallResult:
    installed_global: bool
    installed_local_count: int       # 0..26
    skipped_due_to_user_files: list[str]  # nomes de rules pulados (sem marker)
    errors: list[str]                # warnings pra mostrar em stderr

    def summary(self) -> str:
        # "1 global + 26 locais instaladas" / "26 locais (global skipped)" / etc.
```

**Algoritmo:**
1. `target = detect_cursor(project_root)`
2. Se `target.install_global`: chama `_write_rule(global_path, render_global_rule(ver))`, captura erros.
3. Se `target.install_local`: itera **`_SKILL_GLOBS.keys()`** (a constante da §5 dobra como lista canônica de skills — adicionar nova skill = 1 entrada nessa constante), pra cada nome:
   - Resolve caminho do `SKILL.md` via `importlib.resources.files("plugadvpl") / "skills" / nome / "SKILL.md"`
   - `_write_rule(local_path, render_skill_rule(skill_md, ver, _SKILL_GLOBS[nome]))`, captura erros
4. Retorna `InstallResult` com tudo agregado.

### 3.5 `_write_rule(target_path: Path, content: str) → WriteOutcome`

Helper interno que aplica a política de idempotência da §6:

- Não existe → escreve.
- Existe com marker `<!-- plugadvpl-rule-version: -->` → sobrescreve (nosso arquivo).
- Existe sem marker → skip + adiciona ao `skipped_due_to_user_files`.
- `PermissionError`/`OSError` → adiciona ao `errors`.

Retorna enum `{written, overwritten, skipped_user_file, error}`.

---

## 4. Integração com `init`

Em `cli/plugadvpl/cli.py::init()`, **uma chamada nova** (ordem após `_write_agent_fragment`):

```python
_write_agent_fragment(root, "CLAUDE.md")
_write_agent_fragment(root, "AGENTS.md")
_add_to_gitignore(root, ".plugadvpl/")

if not no_cursor:
    cursor_result = install_cursor_rules(root, __version__)
    if not ctx.obj["quiet"]:
        if cursor_result.installed_global or cursor_result.installed_local_count:
            typer.echo(f"OK  Cursor rules: {cursor_result.summary()}")
        for warn in cursor_result.errors:
            typer.secho(f"⚠  Cursor rules: {warn}", fg=typer.colors.YELLOW, err=True)
        for skipped in cursor_result.skipped_due_to_user_files:
            typer.secho(
                f"⚠  Cursor rules: {skipped} já existe sem marker plugadvpl — não sobrescrevi",
                fg=typer.colors.YELLOW, err=True,
            )
```

**Nova flag:** `--no-cursor: bool` no `init` (default False). Quando True, pula tudo de Cursor.

**Garantia:** init NUNCA falha por causa de Cursor. Exit code sempre 0 se as etapas core (DB, lookups, fragments, gitignore) tiverem sucesso. Cursor é mensagem extra opcional.

---

## 5. Mapping de globs por skill

Decisão de design — define onde cada rule é "auto-aplicada" (Cursor injeta a rule quando arquivo casa). Skills sem glob são `alwaysApply: false` sem `globs:` → só aplicam quando user mention explícito (`@plugadvpl-X`).

| Skill | `globs:` |
|---|---|
| `arch`, `find`, `callers`, `callees`, `lint`, `grep` | `**/*.prw, **/*.tlpp, **/*.prx, **/*.apw` |
| `tables`, `param`, `impacto`, `gatilho`, `ingest-sx`, `sx-status` | `**/*.prw, **/*.tlpp, **/*.prx, **/*.csv` |
| `compile`, `tq`, `edit-prw` | `**/*.prw, **/*.tlpp, **/*.prx, **/*.apw` |
| `ini-audit` | `**/*.ini` |
| `log-diagnose` | `**/*.log` |
| `init`, `ingest`, `status`, `doctor`, `reindex`, `help`, `workflow`, `execauto`, `docs`, `trace`, `setup`, `ingest-protheus` | _(vazio — meta-skills sem escopo de arquivo)_ |

O mapping vive em `cursor_rules.py` como constante `_SKILL_GLOBS: dict[str, list[str]]`. Adicionar/editar é mudança de constante.

---

## 6. Idempotência, upgrade, staleness

### 6.1 Marker decide sobrescrita

Cada arquivo `plugadvpl-*.mdc` começa com:
```
<!-- plugadvpl-rule-version: <ver> -->
```

No `init`:
- **Não existe** → escreve.
- **Existe + tem marker** → sobrescreve sem perguntar (é nosso arquivo).
- **Existe + sem marker** → skip + warning ("rule plugadvpl-arch.mdc existe sem marker plugadvpl — não vou sobrescrever").

**Trade-off conhecido (documentado no README):**
- User editou rule à mão → perde a edição no próximo init. Mesmo padrão do fragment CLAUDE.md.
- User criou rule com nome conflitante → preservada (marker ausente).

### 6.2 Staleness no `plugadvpl status`

Estende `_check_fragment_staleness` em `cli.py` pra também checar:
- `~/.cursor/rules/plugadvpl.mdc` (global)
- `<project>/.cursor/rules/plugadvpl-*.mdc` (todas as locais — glob simples)

Reporta o primeiro arquivo com marker `!= __version__`. Output exemplo:
```
⚠  rule plugadvpl-arch.mdc foi gerada por plugadvpl 0.16.1
```

### 6.3 Skills removidas em upgrade futuro

Se uma versão futura remover uma skill, a rule órfã fica em `.cursor/rules/`. **Init nunca deleta arquivos** (segurança). Cleanup é responsabilidade futura de `plugadvpl doctor`. **Out of scope deste MVP.**

### 6.4 User deleta uma rule de propósito

Init recria no próximo run. Documentar: "pra desabilitar sem deletar, edite `alwaysApply: false` ou mude `globs` pra padrão que nunca casa". Workaround aceitável; init é canal de instalação intencional.

---

## 7. Erro handling

**Princípio: Cursor é secundário no init.** Falha aí NUNCA bloqueia init (prioridade #1 é Claude/AGENTS.md/DB).

| Categoria | Origem | Tratamento |
|---|---|---|
| **Detecção** | `Path.home()` lança RuntimeError; `shutil.which` retorna None | No-op silencioso (não é erro). |
| **Escrita** | `PermissionError`, `OSError` em `~/.cursor/` ou `<project>/.cursor/` | `errors.append(msg)` → warning em stderr. Skip aquela rule, continua. |
| **Parse SKILL.md** | Frontmatter ausente/malformado | Fallback `description = "plugadvpl skill: <nome>"`. Gera rule mesmo assim. |
| **Catch-all** | Exception inesperada em `install_cursor_rules` | `try/except Exception` no topo. `errors.append(repr(e))`. Init segue. |

**Garantias:**
- Exit code do `init` nunca muda por causa de Cursor.
- Mensagens "OK" funcionam como antes — Cursor é linha extra opcional.
- Modo `--quiet`: suprime warnings de Cursor também (consistente).

**Output exemplos:**

Com Cursor detectado + tudo OK:
```
OK  DB criado em ./.plugadvpl/index.db
OK  CLAUDE.md + AGENTS.md atualizados (fragment plugadvpl, idênticos)
OK  .plugadvpl/ adicionado ao .gitignore
OK  Cursor rules: 1 global + 26 locais instaladas
```

Sem Cursor:
```
OK  DB criado em ./.plugadvpl/index.db
OK  CLAUDE.md + AGENTS.md atualizados (fragment plugadvpl, idênticos)
OK  .plugadvpl/ adicionado ao .gitignore
```

Cursor com perm denied no global:
```
OK  DB criado em ./.plugadvpl/index.db
OK  CLAUDE.md + AGENTS.md atualizados (fragment plugadvpl, idênticos)
OK  .plugadvpl/ adicionado ao .gitignore
OK  Cursor rules: 26 locais instaladas
⚠  Cursor rules: falha ao escrever ~/.cursor/rules/plugadvpl.mdc: Permission denied
```

---

## 8. Testes

Padrão TDD igual ao resto. Dois níveis + 2 staleness.

### 8.1 Unit tests — `cli/tests/unit/test_cursor_rules.py` (novo, puros, sem CLI)

| Teste | Cobre |
|---|---|
| `test_detect_cursor_no_signals_returns_false_false` | Sem `~/.cursor/`, sem `.cursor/` no projeto |
| `test_detect_cursor_with_home_dir_returns_global_true` | `~/.cursor/` mockado via `monkeypatch.setattr(Path, "home", ...)` |
| `test_detect_cursor_with_project_dir_returns_local_true` | `.cursor/` criado em `tmp_path` |
| `test_detect_cursor_with_both_returns_both_true` | Ambos sinais |
| `test_detect_cursor_handles_runtime_error_in_home` | `Path.home` lança → (False, False) |
| `test_render_skill_rule_extracts_description_from_frontmatter` | Parse YAML `description:` |
| `test_render_skill_rule_falls_back_when_no_frontmatter` | SKILL.md sem `---` |
| `test_render_skill_rule_substitutes_slash_to_uvx` | `/plugadvpl:arch` → `` `Bash: uvx plugadvpl@<ver> arch` `` |
| `test_render_skill_rule_normalizes_old_uvx_version` | `uvx plugadvpl@0.16.0` → `uvx plugadvpl@<ver>` |
| `test_render_skill_rule_includes_globs_when_provided` | Frontmatter MDC tem `globs:` |
| `test_render_skill_rule_omits_globs_when_empty` | Sem `globs:` no frontmatter |
| `test_render_skill_rule_includes_version_marker` | `<!-- plugadvpl-rule-version: X.Y.Z -->` |
| `test_render_skill_rule_includes_skill_marker` | `<!-- plugadvpl-skill: arch -->` |
| `test_render_global_rule_always_apply_true` | `alwaysApply: true` |
| `test_render_global_rule_no_globs` | Sem `globs:` |

### 8.2 Integration tests — `cli/tests/integration/test_cli.py::TestInitCursorRules` (classe nova)

| Teste | Cobre |
|---|---|
| `test_init_creates_cursor_rules_when_signals_present` | `tmp_path/.cursor/` existe → init cria 26 `plugadvpl-*.mdc` |
| `test_init_skips_cursor_rules_when_no_signals` | Sem sinais → nada em `.cursor/` |
| `test_init_creates_global_rule_when_home_has_cursor` | `Path.home` mockado → cria global |
| `test_init_cursor_rules_idempotent` | Dois inits → não duplica, marker é da versão atual |
| `test_init_overwrites_cursor_rule_with_old_marker` | Marker `0.15.0` → init sobrescreve pra `__version__` |
| `test_init_preserves_user_rule_without_marker` | `plugadvpl-meu.mdc` sem marker → NÃO sobrescreve + warning |
| `test_init_no_cursor_flag_skips_everything` | `init --no-cursor` → zero efeito em `.cursor/` |
| `test_init_quiet_suppresses_cursor_message` | `init --quiet` → sem linha "Cursor rules" |
| `test_init_handles_permission_error_in_global` | `~/.cursor/rules/` readonly → warning, init exit 0 |
| `test_init_handles_permission_error_in_local` | `.cursor/rules/` readonly → warning, init exit 0 |

### 8.3 Status tests — em `TestStatus` existente

| Teste | Cobre |
|---|---|
| `test_status_detects_stale_cursor_global_rule` | Global com marker old → status reporta |
| `test_status_detects_stale_cursor_local_rule` | Local com marker old → status reporta |

**Cobertura esperada:** ~95% do módulo `cursor_rules.py` + branches importantes do `init` integrado.

**Total:** ~25 testes novos. Adiciona ~2-3s na suite (estimativa baseada em testes integration similares).

---

## 9. Out of scope (não entra no MVP v0.16.2)

| Item | Por quê | Quando |
|---|---|---|
| Copilot, Codex avançado | Cursor primeiro. Cada um vira spec próprio. | Specs futuros |
| MCP server | Distribuição via init é suficiente | — |
| Cursor Rules marketplace publish | Init no projeto cobre adoção orgânica | Pós-validação adoção |
| `plugadvpl doctor` check de rules órfãs | Skills removidas em upgrade são raras | Versão futura |
| Sincronização bi-direcional (user edita .mdc → SKILL.md) | Owner do conteúdo é Claude side | — |
| Globs configuráveis por usuário | Lookup table fixo cobre 80% | — |
| Instalar global sem sinal de Cursor | Conservador respeitoso | — |
| Custom rules por cliente/projeto | Não é nosso papel; user cria sem prefixo | — |
| Interactive preview/confirm antes de escrever | "Tudo automático no init" (decisão produto) | — |
| Lint formal de MDC gerado | Confiar no parse do Cursor | Smoke manual no PR |

---

## 10. Tamanho e impacto

| Item | Estimativa |
|---|---|
| Módulo novo `cli/plugadvpl/cursor_rules.py` | ~250 linhas |
| `init` em `cli.py` | +5 linhas + flag `--no-cursor` |
| `_check_fragment_staleness` em `cli.py` | +15 linhas (cobre rules) |
| Testes novos | ~400 linhas |
| README | +1 parágrafo no Quick start + entrada v0.16.2 no histórico |
| CHANGELOG | 1 entrada |
| Bump skills `uvx plugadvpl@0.16.1 → @0.16.2` | mecânico (26 arquivos) |

**Release alvo:** v0.16.2 (patch — adição compatível, zero breaking).

**Risco:** baixo. Feature opt-out via `--no-cursor`. Silent fail garante zero regressão pro fluxo Claude/AGENTS.md. Cursor é gravy on top.

---

## 11. Critérios de sucesso

Considerar entregue quando:

1. ✅ `plugadvpl init` num projeto com `~/.cursor/` e `.cursor/` presentes cria global + 26 locais sem prompt.
2. ✅ Init num projeto sem sinais de Cursor não toca em `.cursor/` (zero pegada).
3. ✅ `plugadvpl status` reporta rule desatualizada com nome do arquivo + versão antiga.
4. ✅ Rule sem marker (user file) é preservada com warning, init continua.
5. ✅ `init --no-cursor` é zero-op pra Cursor.
6. ✅ Erro de permissão não quebra init — exit code 0, warning informativo.
7. ✅ Suite full: 1063 → ~1090 testes (+27 = 15 unit + 10 integration + 2 staleness), zero regressão.
8. ✅ Smoke manual no Cursor real: abrir projeto Protheus pós-init, verificar que rule global injeta convenções e rule `plugadvpl-arch.mdc` aparece quando user abre `.prw`.

---

## 12. Histórico

- 2026-05-29: design inicial, brainstorming aprovado (cenário Cursor dev Protheus, nível alto, decomposição Cursor-first, escopo global+projeto, UX automático, fonte SKILL.md gera .mdc). 8 seções de design validadas com usuário, recomendação A aprovada.
