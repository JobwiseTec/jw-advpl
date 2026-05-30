# Multi-agente v0.16.5 — Improvements pós-research (8 gaps)

**Data:** 2026-05-30
**Versão alvo:** v0.16.5 (patch — adições compatíveis + fix funcional crítico)
**Predecessor:** v0.16.4 entregou Gemini CLI (Fase 3), completando 5 agentes nativos (Claude, Codex, Cursor, Copilot, Gemini). Research pós-shipping com WebFetch oficial dos docs de cada agente identificou 8 gaps acionáveis.

**Research sources:**
- Cursor: https://docs.cursor.com/context/rules
- Copilot: https://docs.github.com/en/copilot/customizing-copilot/adding-repository-custom-instructions-for-github-copilot + VSCode docs
- Gemini: https://geminicli.com/docs + GitHub `google-gemini/gemini-cli`
- Codex/AGENTS.md: https://agents.md/ (Linux Foundation AAIF spec) + Codex CLI docs

---

## 1. Problema

v0.16.4 entregou 5 agentes nativos com 87 testes cobrindo formato dos arquivos gerados. Mas:

1. **Gap funcional CRÍTICO em Copilot e Gemini:** `_transform_body` em `_skill_catalog.py` emite `` `Bash: uvx plugadvpl@<ver> <X>` `` (sintaxe MDC Cursor-específica). Copilot e Gemini interpretam isso como string literal, não comando sugerido. **Perdem ~50% do valor das 52 skills.**

2. **Gap de discoverability Gemini:** Gemini ativa skills por matching semântico de `description`. Várias descriptions atuais (find, lint, callers, grep) são genéricas, **sem keywords ADVPL/Protheus/TLPP/.prw**. JIT activation falha.

3. **Gap de validação:** Nenhum agente externo tem CLI oficial pra validar formato. Não temos `doctor` subcomando pra inspecionar arquivos gerados.

4. **Gap em Cursor global:** `~/.cursor/rules/plugadvpl.mdc` pode ser no-op (docs oficial diz "User Rules" globais são UI-only, não arquivos).

5. **Gap UX Cursor meta-skills:** 12 meta-skills (init/ingest/status/doctor/etc.) viram "Manual only" no Cursor (precisa `@plugadvpl-init` explícito). Deviam ser `alwaysApply: true`.

6. **Gap interop Gemini:** `.agents/skills/` (cross-agent standard emergente) tem **precedência maior** que `.gemini/skills/`. Projetos que usam essa convenção não recebem nossas skills.

7. **Gap Codex:** Falta `.codex/config.toml` mínimo (Codex usa per-project, analogia a `.claude/settings.json`).

8. **Gap documentação:** README não documenta cobertura 5 agentes nem smoke test manual.

**Objetivo:** Endereçar todos os 8 gaps numa única release patch, com testes adequados.

---

## 2. Decisões de produto

| # | Decisão | Justificativa |
|---|---|---|
| 1 | **Fix CRÍTICO**: `_transform_body` ganha param `style: Literal["cursor", "plain"]` | Cursor body usa backtick MDC; Copilot/Gemini usam texto plano. Default `plain` (mais conservador); Cursor passa `style="cursor"`. |
| 2 | **Auditar 52 descriptions** com keywords | Garantir cada description tem pelo menos 1 de: ADVPL, Protheus, TLPP, .prw, SX, dicionário. |
| 3 | **`plugadvpl doctor --check-agents`** | Comando novo que valida formato dos arquivos gerados sem precisar instalar agentes externos. |
| 4 | **Cursor: meta-skills `alwaysApply: true`** | 12 skills meta marcadas explícitamente. Lista fixa em `_skill_catalog.py`. |
| 5 | **Cursor global: documentar limitação** | Manter código mas mensagem `OK Cursor rules: 1 global (experimental — Cursor docs não confirmam ~/.cursor/rules/ ainda) + 52 locais`. |
| 6 | **Gemini: detectar `.agents/skills/`** | Se `<project>/.agents/skills/` existe, instalar lá também (paralelo a `.gemini/skills/`). |
| 7 | **Codex: gerar `.codex/config.toml`** | Mínimo (~15 linhas comentadas). Idempotente via marker. |
| 8 | **README**: seção "Cobertura multi-agente" + smoke guide | Documenta os 5 agentes + como validar manual. |

---

## 3. Arquitetura

### 3.1 Fix #1 — `_transform_body` ganha `style` param

Em `cli/plugadvpl/_skill_catalog.py`:

```python
def _transform_body(
    body: str, version: str, style: Literal["cursor", "plain"] = "plain"
) -> str:
    """Aplica 2 substituições NESTA ORDEM:

    3a) `/plugadvpl:<X>` → comando substituído (formato por agente)
    3b) `uvx plugadvpl@<qualquer>` → `uvx plugadvpl@<ver>`

    Args:
        style: "cursor" emite ` `Bash: uvx plugadvpl@<ver> <X>` ` (MDC syntax);
               "plain" emite `uvx plugadvpl@<ver> <X>` (texto puro pro Copilot/Gemini).

    Cursor MDC interpreta backticks + Bash: como hint de comando inline;
    Copilot/Gemini interpretam só texto puro.
    """
    if style == "cursor":
        body = _SLASH_RE.sub(rf"`Bash: uvx plugadvpl@{version} \1`", body)
    else:  # plain
        body = _SLASH_RE.sub(rf"uvx plugadvpl@{version} \1", body)
    body = _UVX_VER_RE.sub(f"uvx plugadvpl@{version}", body)
    return body
```

**Callers atualizados:**
- `cursor_rules.render_skill_rule` → `_transform_body(body, version, style="cursor")`
- `copilot_instructions.render_skill_instructions` → `_transform_body(body, version, style="plain")` (default, mas explicito)
- `gemini_skills.render_skill_for_gemini` → `_transform_body(body, version, style="plain")`

Default é `plain` (safer) — só Cursor opta in.

### 3.2 Fix #2 — Auditar 52 descriptions

Não é mudança de código — é edição manual de 52 SKILL.md headers garantindo keywords. Skills com gaps confirmados (sample):

- `find/SKILL.md`: `description: Pesquisa simbolos (funcoes, classes, metodos) no indice plugadvpl` → adicionar "ADVPL/TLPP"
- `lint/SKILL.md`: `description: Roda lint plugadvpl em um arquivo (13 regras MVP)` → adicionar "ADVPL/.prw"
- `tables/SKILL.md`: `description: Lista usos de uma tabela ERP (...)` → `tabela ERP Protheus`
- ... (auditar todas 52)

**Estratégia:** script Python que lista descriptions atuais + flag se NÃO contém pelo menos 1 keyword target. Editar manualmente as flagged. **Não automatizar edição** (risco de quebrar nuance). Script é só checker.

### 3.3 Fix #3 — `plugadvpl doctor --check-agents`

Novo subcomando do `doctor` (ou flag): valida formato dos arquivos gerados sem precisar instalar agentes.

**Verificações por agente:**

| Agente | Validação |
|---|---|
| CLAUDE.md / AGENTS.md | Existe + tem marker `<!-- plugadvpl-fragment-version: ... -->` + versão matches `__version__` |
| Cursor | `.cursor/rules/plugadvpl-*.mdc` count, frontmatter parseável, `globs` é STRING (não array), `alwaysApply` presente, marker version |
| Copilot | `.github/copilot-instructions.md` global existe; `.github/instructions/plugadvpl-*.instructions.md` count, `applyTo` é STRING, marker version |
| Gemini | `~/.gemini/GEMINI.md` ou `<project>/GEMINI.md` existe; `.gemini/skills/plugadvpl-*/SKILL.md` count, frontmatter `name`+`description`, marker version |
| Keywords | Cada SKILL.md description contém pelo menos 1 de: ADVPL, Protheus, TLPP, .prw, SX (skills meta-only podem skipar) |

**Output:** tabela com agente / count / status (✅/⚠️/❌) + lista de issues.

**Implementação:** novo módulo `cli/plugadvpl/agent_doctor.py` ou estender `cli/plugadvpl/doctor.py` se existir. Flag `--check-agents` em `plugadvpl doctor`.

### 3.4 Fix #4 — Cursor meta-skills `alwaysApply: true`

Em `_skill_catalog.py`, adicionar set explícito de meta-skills que querem `alwaysApply: true`:

```python
# Meta-skills sem glob específico, mas que carregam contexto transversal —
# Cursor deve sempre injetá-las (alwaysApply: true) em vez de relegar pra
# "Manual only" mode.
_CURSOR_META_ALWAYS_APPLY = {
    "init", "ingest", "status", "doctor", "help",
    "workflow", "trace", "setup", "ingest-protheus",
    "reindex", "execauto", "docs",
}
```

Em `cursor_rules.render_skill_rule`, ajustar lógica:

```python
skill_name = skill_md_path.parent.name
always_apply = skill_name in _CURSOR_META_ALWAYS_APPLY

if globs:
    # Skill com glob específico — alwaysApply: false, glob attach
    ...
elif always_apply:
    # Meta-skill — alwaysApply: true, sem globs (sempre carregada)
    ...
else:
    # Manual only — alwaysApply: false, sem globs
    ...
```

### 3.5 Fix #5 — Cursor global experimental warning

Em `cursor_rules.install_cursor_rules`, ajustar `InstallResult.summary()` quando `installed_global=True`:

```python
def summary(self) -> str:
    parts = []
    if self.installed_global:
        parts.append("1 global (experimental)")  # antes era só "1 global"
    if self.installed_local_count:
        parts.append(f"{self.installed_local_count} locais")
    return (" + ".join(parts) + " instaladas") if parts else "nada instalado"
```

Adicionar comentário no módulo explicando: "User Rules globais do Cursor são UI-only (Settings → Rules); `~/.cursor/rules/*.mdc` arquivos podem não ser lidos. Mantemos por compat futura e doc."

### 3.6 Fix #6 — Gemini `.agents/skills/`

Em `gemini_skills.py`, estender `install_gemini_skills` pra detectar `.agents/skills/` no projeto:

```python
def install_gemini_skills(project_root: Path, version: str) -> InstallResult:
    # ... existing detection
    if target.install_project:
        # Existing: install em .gemini/skills/
        ...
        # NEW: se .agents/skills/ existe, instalar lá TAMBÉM (paralelo)
        agents_dir = project_root / ".agents" / "skills"
        if agents_dir.exists():
            for skill_name in _SKILL_GLOBS:
                ok, skp, err = _install_one_gemini_skill(
                    skill_name, skills_root, agents_dir, version
                )
                # ... merge
```

**Decisão:** Instalar em AMBOS quando ambos existem (não substituir). Usuário decide qual usar via gitignore/symlink.

### 3.7 Fix #7 — Codex `.codex/config.toml`

Novo helper em `cli.py` ou novo módulo `cli/plugadvpl/codex_config.py`:

```python
_CODEX_CONFIG_TEMPLATE = """# .codex/config.toml — Codex CLI per-project config
# Gerado por plugadvpl init. Edite livremente — marker abaixo controla
# regeneração; remova-o pra preservar customizações.
# Docs: https://developers.openai.com/codex/cli/configuration

# plugadvpl-codex-version: __VERSION__

[project]
# Codex carrega AGENTS.md automaticamente (gerado também pelo plugadvpl init).
# Pra ler arquivos adicionais como context:
# project_doc_fallback_filenames = ["CLAUDE.md"]

[skills]
# Codex lê SKILL.md compatíveis cross-tool. Nossas skills/plugadvpl-*/SKILL.md
# funcionam diretamente — Codex faz auto-discovery.
# enabled = true
"""


def install_codex_config(project_root: Path, version: str) -> InstallResult:
    """Gera .codex/config.toml mínimo se Codex detectado.

    Detection: .codex/ existe no projeto OU `codex` no PATH.
    """
    ...
```

Marker em comment TOML: `# plugadvpl-codex-version: 0.16.5`. Idempotência via mesmo `_write_managed_file` mas com `marker_substring="# plugadvpl-codex-version:"`.

Flag nova: `--no-codex`. Init chama após Gemini.

### 3.8 Fix #8 — README documentação

Adicionar seção "Cobertura multi-agente" no README (após "Por que plugadvpl") com:
- Tabela 5 agentes (igual ao CHANGELOG v0.16.4)
- Smoke test manual guide por agente (5 mini-snippets)

Atualizar Quick start mencionando todos 5 agentes.

---

## 4. Erro handling

Mesma garantia spec §7 das Fases 1-3: **NEVER propagates**. Cada novo helper (codex_config, agent_doctor) tem top-level try/except. `init` exit code permanece 0 mesmo com falha.

---

## 5. Testes

### 5.1 Unit tests

**`test_skill_catalog.py`** (estende):
- `test_transform_body_cursor_style_emits_bash_prefix` — `style="cursor"` → backticks + `Bash:`
- `test_transform_body_plain_style_emits_text` — `style="plain"` → texto puro
- `test_transform_body_default_is_plain` — sem param → plain (safer default)

**`test_cursor_rules.py`** (estende):
- `test_render_skill_rule_uses_cursor_style` — verifica `Bash:` no body
- `test_meta_skill_init_has_always_apply_true` — meta-skill ganha `alwaysApply: true`
- `test_non_meta_skill_has_always_apply_false` — não-meta mantém false

**`test_copilot_instructions.py`** (estende):
- `test_render_skill_instructions_uses_plain_style` — verifica SEM `Bash:` no body, comando texto puro

**`test_gemini_skills.py`** (estende):
- `test_render_skill_for_gemini_uses_plain_style` — verifica SEM `Bash:` no body
- `test_install_uses_agents_skills_when_present` — `.agents/skills/` no projeto → instala lá

**`test_codex_config.py`** (novo, ~5 testes):
- `test_no_codex_signal_no_op`
- `test_codex_dir_triggers_install`
- `test_codex_in_path_triggers_install`
- `test_idempotent`
- `test_preserves_user_file_without_marker`

**`test_agent_doctor.py`** (novo, ~10 testes):
- `test_validates_claude_md`
- `test_validates_agents_md`
- `test_validates_cursor_globs_is_string`
- `test_flags_cursor_globs_as_array_invalid`
- `test_validates_copilot_apply_to_is_string`
- `test_validates_gemini_frontmatter_minimal`
- `test_flags_missing_keywords`
- `test_reports_count_mismatch`
- ... (etc.)

### 5.2 Integration tests

**`test_cli.py`** (estende):
- `TestInitCodexConfig` (5 tests): no-op without signal, install with .codex/, --no-codex flag, idempotent, preserve user file
- `TestDoctorCheckAgents` (3 tests): all green, flag missing keyword, flag invalid format
- `TestInitMultiAgent`: novo teste validando que init completo com TODOS sinais ativos instala 5 agentes sem conflito

### 5.3 Smoke audit script

Pre-flight da Task 2 (descriptions audit): script Python que reporta quais SKILL.md não têm keywords. NÃO automatizar fix (manual edit).

**Total estimado:** ~30 testes novos. Suite alvo: 1151 → ~1181.

---

## 6. Tamanho e impacto

| Item | Estimativa |
|---|---|
| `_skill_catalog.py` (style param) | +20 linhas |
| `cursor_rules.py` (meta_always_apply + style) | +30 linhas |
| `copilot_instructions.py` (style="plain") | ~2 linhas |
| `gemini_skills.py` (style="plain" + .agents/skills/) | +30 linhas |
| `codex_config.py` (novo módulo) | ~120 linhas |
| `agent_doctor.py` (novo módulo) | ~200 linhas |
| `cli.py` (--no-codex flag + doctor --check-agents) | +25 linhas |
| Testes novos | ~30 testes (~500 linhas) |
| SKILL.md descriptions audit | 52 arquivos potencialmente editados (~3-5 linhas cada) |
| README + CHANGELOG | ~50 linhas |

**Release:** v0.16.5 (patch — adições compatíveis + 1 fix funcional crítico).

**Risco:** baixo-médio. Mudança no `_transform_body` style afeta **todos os arquivos gerados** — testes precisam validar que Cursor continua com Bash: e Copilot/Gemini agora sem Bash:.

---

## 7. Critérios de sucesso

1. ✅ `plugadvpl doctor --check-agents` lista 5 agentes + status de cada.
2. ✅ Cursor `.mdc` files mantêm `Bash:` prefix; Copilot/Gemini files agora têm comando texto puro.
3. ✅ 12 meta-skills no Cursor ganham `alwaysApply: true`.
4. ✅ Cursor global mensagem mostra "(experimental)".
5. ✅ `.agents/skills/` no projeto → Gemini instala lá também.
6. ✅ Codex detectado → `.codex/config.toml` gerado.
7. ✅ 52 SKILL.md auditadas e descriptions com keywords ADVPL/Protheus quando aplicável.
8. ✅ README documenta 5 agentes + smoke guide.
9. ✅ Suite full: 1151 → ~1181 (zero regressão Fases 1-3).
10. ✅ CI verde, PyPI + GitHub release publicados.

---

## 8. Out of scope (v0.17+)

| Item | Por quê |
|---|---|
| Copilot `name:` field (VSCode UX hover) | Cosmético; v0.17 |
| Copilot `excludeAgent: code-review` | Estratégia per-skill; análise futura |
| Gemini `.geminiignore` auto-gerado | Útil mas opcional |
| AGENTS.md frontmatter v1.1 | Spec ainda proposal (Linux Foundation issue #135) |
| `agents/openai.yaml` per skill (MCP deps) | Só se publicar plugin Codex no marketplace |
| Continue.dev `.continue/rules/` | Continue lê AGENTS.md; cobertura ok |
| Smoke tests end-to-end automatizados (instalar agentes em CI) | Custo alto, retorno baixo |

---

## 9. Histórico

- 2026-05-30: design inicial baseado em 4 research reports paralelos (Cursor, Copilot, Gemini, Codex). 8 gaps identificados, todos acionáveis em v0.16.5.
