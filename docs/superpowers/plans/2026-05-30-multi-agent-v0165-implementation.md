# Multi-agente v0.16.5 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Endereçar 8 gaps multi-agente identificados em research pós-shipping da v0.16.4: fix funcional crítico `_transform_body`, descriptions audit, `doctor --check-agents` comando novo, Cursor meta-skills always-apply, Cursor global experimental warning, Gemini `.agents/skills/`, Codex `.codex/config.toml`, README cobertura.

**Architecture:** Mudanças refletem em `_skill_catalog.py` (+style param + meta-always-apply set), `cursor_rules.py`/`copilot_instructions.py`/`gemini_skills.py` (call style explícito), novo módulo `agent_doctor.py`, novo módulo `codex_config.py`, `cli.py` (--no-codex flag + doctor --check-agents wiring). Edição manual de até 52 SKILL.md descriptions auditadas via script.

**Tech Stack:** Python 3.11+ stdlib only. Typer (existente). pytest + monkeypatch + CliRunner. Sem deps novas.

**Spec:** [`docs/superpowers/specs/2026-05-30-multi-agent-v0165-improvements.md`](../specs/2026-05-30-multi-agent-v0165-improvements.md)

---

## File Structure

**Arquivos novos:**
- `cli/plugadvpl/agent_doctor.py` (~200 linhas) — valida formato dos arquivos gerados por todos 5 agentes; sem dep de agente instalado
- `cli/plugadvpl/codex_config.py` (~120 linhas) — `CodexTarget`, `detect_codex`, `render_codex_config`, `install_codex_config`
- `cli/tests/unit/test_agent_doctor.py` (~250 linhas) — 10 unit tests
- `cli/tests/unit/test_codex_config.py` (~150 linhas) — 5 unit tests
- `d:\tmp\audit_skill_descriptions.py` (one-off script) — flagga SKILL.md sem keywords

**Arquivos modificados:**
- `cli/plugadvpl/_skill_catalog.py` — `_transform_body` ganha `style` param + `_CURSOR_META_ALWAYS_APPLY` set
- `cli/plugadvpl/cursor_rules.py` — passar `style="cursor"`, ajustar `render_skill_rule` pra usar `_CURSOR_META_ALWAYS_APPLY`, mensagem "experimental" no summary global
- `cli/plugadvpl/copilot_instructions.py` — passar `style="plain"` (default mas explícito)
- `cli/plugadvpl/gemini_skills.py` — passar `style="plain"`, detectar e instalar em `.agents/skills/` quando existir
- `cli/plugadvpl/cli.py` — flag `--no-codex` + chamada `install_codex_config`; flag `--check-agents` em `doctor`
- `cli/tests/unit/test_skill_catalog.py` — +3 tests pra `_transform_body` style param
- `cli/tests/unit/test_cursor_rules.py` — +2 tests (cursor style assertion + meta always apply)
- `cli/tests/unit/test_copilot_instructions.py` — +1 test (plain style)
- `cli/tests/unit/test_gemini_skills.py` — +2 tests (plain style + .agents/skills/)
- `cli/tests/integration/test_cli.py` — `TestInitCodexConfig` (5) + `TestDoctorCheckAgents` (3) + `TestInitMultiAgent` (1)
- `skills/<X>/SKILL.md` — auditar e editar descriptions (manual, after audit script)
- `.claude-plugin/plugin.json` + `marketplace.json` — bump 0.16.4 → 0.16.5
- `skills/*/SKILL.md` × 26 — bump `uvx plugadvpl@0.16.4` → `@0.16.5`
- `CHANGELOG.md` — entry [0.16.5]
- `README.md` — seção "Cobertura multi-agente" + smoke guide + ajuste Quick start

---

## Chunk 1: Fix CRÍTICO — `_transform_body` style param

### Task 1: `_transform_body` ganha `style` param

**Files:**
- Modify: `cli/plugadvpl/_skill_catalog.py` (estende função existente)
- Modify: `cli/tests/unit/test_skill_catalog.py` (+3 tests)

- [ ] **Step 1: Add 3 RED tests in test_skill_catalog.py**

Encontrar a classe `TestTransformBody` existente. ADD 3 novos testes:

```python
    def test_cursor_style_emits_bash_prefix(self) -> None:
        """style='cursor' → backtick + 'Bash:' prefix (MDC syntax)."""
        body = "Use `/plugadvpl:arch` antes de Read.\n"
        result = _transform_body(body, version="0.16.5", style="cursor")
        assert "`Bash: uvx plugadvpl@0.16.5 arch`" in result
        assert "/plugadvpl:arch" not in result

    def test_plain_style_emits_text(self) -> None:
        """style='plain' → texto puro (Copilot/Gemini)."""
        body = "Use `/plugadvpl:arch` antes de Read.\n"
        result = _transform_body(body, version="0.16.5", style="plain")
        assert "uvx plugadvpl@0.16.5 arch" in result
        assert "Bash:" not in result
        assert "`Bash:" not in result
        assert "/plugadvpl:arch" not in result

    def test_default_style_is_plain(self) -> None:
        """Sem param style → default 'plain' (safer, conservador)."""
        body = "Use `/plugadvpl:arch` antes de Read.\n"
        result = _transform_body(body, version="0.16.5")  # no style arg
        assert "uvx plugadvpl@0.16.5 arch" in result
        assert "Bash:" not in result
```

- [ ] **Step 2: Run RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_skill_catalog.py::TestTransformBody -v --no-cov`

Expected: 3 failures — `TypeError: _transform_body() got an unexpected keyword argument 'style'` ou `AssertionError` (porque a impl atual emite `Bash:` sempre).

- [ ] **Step 3: Modify `_transform_body` in `_skill_catalog.py`**

Find existing function (~linha 100). Replace COMPLETA:

```python
from typing import Literal

def _transform_body(
    body: str, version: str, style: Literal["cursor", "plain"] = "plain"
) -> str:
    """Aplica 2 substituições NESTA ORDEM:

    3a) `/plugadvpl:<X>` → comando substituído (formato por agente)
    3b) `uvx plugadvpl@<qualquer>` → `uvx plugadvpl@<ver>`

    Args:
        body: conteúdo a transformar.
        version: versão runtime (substitui placeholders).
        style: "cursor" emite `` `Bash: uvx plugadvpl@<ver> <X>` `` (MDC syntax);
               "plain" emite `uvx plugadvpl@<ver> <X>` (texto puro pro Copilot/Gemini).
               Default "plain" (safer; Copilot/Gemini interpretam Bash: como literal).

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

`Literal` import: adicionar `from typing import Literal` no topo do arquivo (se ainda não tem).

- [ ] **Step 4: Run GREEN — 3 NEW tests pass**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_skill_catalog.py::TestTransformBody -v --no-cov`

Expected: 5 passed (2 prev + 3 new).

**MAS pode quebrar tests existentes de Cursor/Copilot/Gemini que ASSUMEM `Bash:` prefix.**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov`

Expected: várias falhas em test_cursor_rules.py + test_copilot_instructions.py + test_gemini_skills.py (porque callers ainda não passam style explícito; default mudou de "cursor implícito" pra "plain").

**Anote os números de failures.** Vai endereçar nas Tasks 2-4.

- [ ] **Step 5: Commit (commit parcial — failures esperadas até Tasks 2-4)**

```bash
git add cli/plugadvpl/_skill_catalog.py cli/tests/unit/test_skill_catalog.py
git commit -m "feat(catalog): _transform_body ganha style param (cursor/plain)

Spec v0.16.5 gap CRITICO #1: separar formato de comando por agente.
- style='cursor' emite \`Bash: uvx ...\` (MDC syntax, Cursor only)
- style='plain' emite uvx ... (texto puro, Copilot/Gemini)
- Default 'plain' (safer; Copilot/Gemini interpretam Bash: como literal)

3 testes novos em TestTransformBody.

COMMIT PARCIAL: callers Cursor/Copilot/Gemini ainda nao passam style
explicito — failures esperadas. Endereco em Tasks 2-4.

Spec: docs/superpowers/specs/2026-05-30-multi-agent-v0165-improvements.md secao 3.1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `cursor_rules` passa `style="cursor"` + test stricter

**Files:**
- Modify: `cli/plugadvpl/cursor_rules.py`
- Modify: `cli/tests/unit/test_cursor_rules.py` (+1 test stricter)

- [ ] **Step 1: Add 1 stricter test in test_cursor_rules.py (TestRenderSkillRule class)**

```python
    def test_render_skill_rule_uses_cursor_style_explicit(self, tmp_path: Path) -> None:
        """v0.16.5 — verifica output REAL contém literal `Bash: uvx plugadvpl@`.

        Antes do gap fix v0.16.5, Cursor compartilhava `_transform_body` que
        sempre emitia `Bash:`. Agora `_transform_body` default é 'plain'.
        cursor_rules.render_skill_rule DEVE passar style='cursor' explícito.
        Esta assertion bloqueia regressão: se alguém remover style="cursor",
        o output muda pra texto puro e o teste falha.
        """
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\nUse `/plugadvpl:arch`.\n",
            encoding="utf-8",
        )
        result = render_skill_rule(
            target, version="0.16.5", globs=["**/*.prw"]
        )
        # Strict assertion: literal Bash: prefix must appear
        assert "`Bash: uvx plugadvpl@0.16.5 arch`" in result
```

- [ ] **Step 2: Run** — Expected: este teste novo já deve passar SE a implementação atual ainda emite `Bash:` (porque era o default antigo). Mas após Task 1 default mudou — provavelmente FALHA agora.

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestRenderSkillRule::test_render_skill_rule_uses_cursor_style_explicit -v --no-cov`

Expected: FAIL (output não tem `Bash:` porque cursor_rules ainda não passa style).

- [ ] **Step 3: Modify `cli/plugadvpl/cursor_rules.py` — `render_skill_rule`**

Find `render_skill_rule` function. Na linha que chama `_transform_body(body, version)`, mudar pra:

```python
    return frontmatter + markers + _transform_body(body, version, style="cursor")
```

- [ ] **Step 4: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py -v --no-cov`

Expected: todos passam (incluindo testes pre-existentes que assumiam `Bash:`).

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cursor_rules.py cli/tests/unit/test_cursor_rules.py
git commit -m "feat(cursor): render_skill_rule passa style='cursor' explicito

Apos _transform_body ganhar style param (Task 1), cursor_rules precisa
opt-in explicitamente em style='cursor' pra manter formato MDC com
\`Bash:\` prefix.

+1 teste stricter (test_render_skill_rule_uses_cursor_style_explicit)
valida output REAL contendo literal 'Bash: uvx plugadvpl@' — bloqueia
regressao mock-passing.

Spec: docs/superpowers/specs/2026-05-30-multi-agent-v0165-improvements.md secao 3.1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `copilot_instructions` style="plain" + assertion

**Files:**
- Modify: `cli/plugadvpl/copilot_instructions.py`
- Modify: `cli/tests/unit/test_copilot_instructions.py`

- [ ] **Step 1: Add 1 test pra TestRenderSkillInstructions**

```python
    def test_render_skill_instructions_emits_plain_text_command(self, tmp_path: Path) -> None:
        """v0.16.5 — Copilot deve receber texto puro, NÃO `Bash:` (Cursor MDC)."""
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\nUse `/plugadvpl:arch`.\n",
            encoding="utf-8",
        )
        result = render_skill_instructions(
            target, version="0.16.5", globs=["**/*.prw"]
        )
        # Plain style: command em texto, sem Bash:
        assert "uvx plugadvpl@0.16.5 arch" in result
        assert "Bash:" not in result
        assert "`Bash:" not in result
```

- [ ] **Step 2: Run RED** — pode passar SE copilot já estava usando style=plain default. Pode falhar se ainda emite Bash:.

- [ ] **Step 3: Modify `copilot_instructions.py` — `render_skill_instructions`**

Find call `_transform_body(body, version)`. Adicionar explicito:

```python
    return frontmatter + markers + _transform_body(body, version, style="plain")
```

(Mesmo que default seja "plain", explicit > implicit pra clareza.)

- [ ] **Step 4: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_copilot_instructions.py -v --no-cov`

Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/copilot_instructions.py cli/tests/unit/test_copilot_instructions.py
git commit -m "feat(copilot): render_skill_instructions passa style='plain' explicito

Copilot interpreta \`Bash: uvx ...\` como string literal, nao como
comando sugerido. Texto puro 'uvx plugadvpl@X.Y.Z arch' eh canon.

+1 teste assertion stricter (test_render_skill_instructions_emits_plain_text_command).

Spec: docs/superpowers/specs/2026-05-30-multi-agent-v0165-improvements.md secao 3.1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `gemini_skills` style="plain" + assertion

**Files:**
- Modify: `cli/plugadvpl/gemini_skills.py`
- Modify: `cli/tests/unit/test_gemini_skills.py`

- [ ] **Step 1: Add 1 test pra TestRenderSkillForGemini**

```python
    def test_render_skill_for_gemini_emits_plain_text_command(self, tmp_path: Path) -> None:
        """v0.16.5 — Gemini deve receber texto puro, NÃO `Bash:` (Cursor MDC)."""
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\nUse `/plugadvpl:arch`.\n",
            encoding="utf-8",
        )
        result = render_skill_for_gemini(target, version="0.16.5")
        # Plain style
        assert "uvx plugadvpl@0.16.5 arch" in result
        assert "Bash:" not in result
        assert "`Bash:" not in result
```

- [ ] **Step 2: Run RED** — pode passar/falhar similar a Task 3.

- [ ] **Step 3: Modify `gemini_skills.py` — `render_skill_for_gemini`**

Find call `_transform_body(body, version)`. Adicionar explicit:

```python
    return frontmatter + markers + _transform_body(body, version, style="plain")
```

- [ ] **Step 4: Run GREEN + full suite**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov`

Expected: 1154 passed (1151 + 3 transform_body + 1 cursor + 1 copilot + 1 gemini = +6 actually... but some may have been already counted; expected ~1157).

Se quebraram tests existentes em test_cursor_rules.py (TestRenderSkillRule existentes que checavam `Bash:`), eles devem AINDA passar porque cursor_rules agora passa style="cursor" explícito.

Se quebraram tests existentes em test_copilot_instructions.py ou test_gemini_skills.py que checavam `Bash:` no body (era falso-positivo), AGORA quebram corretamente — esses tests precisam ser ajustados:

- Buscar em test_copilot_instructions.py: `"\`Bash:"` ou `"Bash: uvx"` — se aparece como assertion, ajustar pra `"uvx plugadvpl@"` (texto puro) ou remover assertion errada.
- Mesma busca em test_gemini_skills.py.

Após ajustar (se necessário), re-run suite. Expected: 1157+ passed, zero falhas.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/gemini_skills.py cli/tests/unit/test_gemini_skills.py
# Se ajustou testes de copilot/gemini existentes, também adicionar:
# git add cli/tests/unit/test_copilot_instructions.py cli/tests/unit/test_gemini_skills.py
git commit -m "feat(gemini): render_skill_for_gemini passa style='plain' explicito

Gemini interpreta \`Bash: uvx ...\` como string literal igual Copilot.
Texto puro eh canon.

+1 teste assertion stricter. Se algum teste existente assumiu Bash:
no body por engano, foi ajustado pra refletir comportamento correto.

Suite full: 1157+ passed (gap CRITICO #1 fechado em todos 3 agentes).

Spec: docs/superpowers/specs/2026-05-30-multi-agent-v0165-improvements.md secao 3.1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: Cursor meta-skills + experimental warning

### Task 5: `_CURSOR_META_ALWAYS_APPLY` set + render lógica

**Files:**
- Modify: `cli/plugadvpl/_skill_catalog.py` (add constant)
- Modify: `cli/plugadvpl/cursor_rules.py` (render_skill_rule lógica)
- Modify: `cli/tests/unit/test_cursor_rules.py` (+2 tests)

- [ ] **Step 1: Add 2 RED tests in test_cursor_rules.py TestRenderSkillRule**

```python
    def test_meta_skill_has_always_apply_true(self, tmp_path: Path) -> None:
        """v0.16.5 — Meta-skills (init, ingest, etc.) ganham alwaysApply: true."""
        from plugadvpl.cursor_rules import render_skill_rule
        # Skill 'init' está em _CURSOR_META_ALWAYS_APPLY
        skill_dir = tmp_path / "init"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        # globs vazio (init é meta sem escopo)
        result = render_skill_rule(target, version="0.16.5", globs=[])
        assert "alwaysApply: true" in result
        # E NÃO tem `globs:` (não tem escopo)
        # Pode ter dentro do body comments, mas no frontmatter NÃO
        lines = result.split("\n")
        in_fm = False
        fm_lines = []
        for line in lines:
            if line == "---":
                in_fm = not in_fm
                continue
            if in_fm:
                fm_lines.append(line)
        assert not any(line.startswith("globs:") for line in fm_lines)

    def test_non_meta_skill_without_globs_has_always_apply_false(self, tmp_path: Path) -> None:
        """v0.16.5 — Non-meta skill sem globs mantém alwaysApply: false (Manual only)."""
        from plugadvpl.cursor_rules import render_skill_rule
        # Skill name fictícia que NÃO está em _CURSOR_META_ALWAYS_APPLY
        skill_dir = tmp_path / "experimental-feature"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_rule(target, version="0.16.5", globs=[])
        assert "alwaysApply: false" in result
```

- [ ] **Step 2: Run RED** — Expected: 2 failures (`alwaysApply: true` não aparece pra init; provavelmente comportamento atual emite `false` pra TODAS sem globs).

- [ ] **Step 3: Add constant in `_skill_catalog.py`**

Find `_SKILL_GLOBS` dict. ADD imediatamente após:

```python
# v0.16.5 — Meta-skills sem glob específico mas que carregam contexto
# transversal. Cursor deve sempre injetá-las (alwaysApply: true) em vez
# de relegar pra "Manual only" mode (que exige @plugadvpl-init explícito).
_CURSOR_META_ALWAYS_APPLY: set[str] = {
    "init", "ingest", "status", "doctor", "help",
    "workflow", "trace", "setup", "ingest-protheus",
    "reindex", "execauto", "docs",
}
```

- [ ] **Step 4: Update `render_skill_rule` in `cursor_rules.py`**

Find import de `_skill_catalog`. Adicionar `_CURSOR_META_ALWAYS_APPLY` na lista de imports.

Encontrar lógica do frontmatter em `render_skill_rule`. Atual provavelmente:

```python
frontmatter = "---\n"
frontmatter += f"description: {description}\n"
if globs:
    frontmatter += f"globs: {', '.join(globs)}\n"
frontmatter += "alwaysApply: false\n"
frontmatter += "---\n"
```

Replace com:

```python
skill_name = skill_md_path.parent.name
is_meta_always = skill_name in _CURSOR_META_ALWAYS_APPLY and not globs
always_apply = "true" if is_meta_always else "false"

frontmatter = "---\n"
frontmatter += f"description: {description}\n"
if globs:
    frontmatter += f"globs: {', '.join(globs)}\n"
frontmatter += f"alwaysApply: {always_apply}\n"
frontmatter += "---\n"
```

- [ ] **Step 5: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py -v --no-cov`

Expected: todos passam (testes existentes não-meta sem globs ainda emitem `false`; novo teste meta init emite `true`).

Full suite: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov` — Expected: 1159+ passed.

- [ ] **Step 6: Commit**

```bash
git add cli/plugadvpl/_skill_catalog.py cli/plugadvpl/cursor_rules.py cli/tests/unit/test_cursor_rules.py
git commit -m "feat(cursor): meta-skills ganham alwaysApply: true (12 skills transversais)

Spec v0.16.5 gap #4: meta-skills (init/ingest/status/doctor/help/workflow/
trace/setup/ingest-protheus/reindex/execauto/docs) viravam 'Manual only'
no Cursor (precisa @plugadvpl-init explicito). Sao contexto transversal
e devem sempre estar disponiveis.

+constante _CURSOR_META_ALWAYS_APPLY em _skill_catalog.py com 12 nomes.
+2 testes (meta init alwaysApply=true; non-meta sem globs alwaysApply=false).

Spec: secao 3.4

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Cursor global experimental warning

**Files:**
- Modify: `cli/plugadvpl/cursor_rules.py` (`InstallResult.summary()`)
- Modify: `cli/tests/unit/test_cursor_rules.py` (+1 test)

- [ ] **Step 1: Add 1 test**

```python
class TestCursorInstallResultSummary:
    def test_global_marked_experimental(self) -> None:
        """v0.16.5 — global mark com '(experimental)' pra sinalizar incerteza
        docs Cursor sobre ~/.cursor/rules/."""
        from plugadvpl.cursor_rules import InstallResult
        r = InstallResult(
            installed_global=True,
            installed_local_count=52,
            skipped_due_to_user_files=[],
            errors=[],
        )
        assert "global (experimental)" in r.summary()
        assert "52 locais" in r.summary()
```

- [ ] **Step 2: Run RED** — falha (summary atual não tem "experimental").

- [ ] **Step 3: Modify `cursor_rules.InstallResult.summary()`**

Find `def summary(self) -> str:` em `InstallResult`. Replace:

```python
    def summary(self) -> str:
        """String curta pra `init` printar.

        v0.16.5: rotula 'global' como '(experimental)' — Cursor docs oficial
        não confirma que ~/.cursor/rules/ é lido (User Rules globais são
        UI-only, Cursor Settings → Rules). Mantemos por compat futura
        mas sinalizamos a incerteza pro user.
        """
        parts = []
        if self.installed_global:
            parts.append("1 global (experimental)")
        if self.installed_local_count:
            parts.append(f"{self.installed_local_count} locais")
        return (" + ".join(parts) + " instaladas") if parts else "nada instalado"
```

- [ ] **Step 4: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py -v --no-cov`

Expected: novo teste passa. Testes existentes podem precisar ajuste se assumiam exact match "1 global +" (substring "1 global" ainda funciona). Verificar.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cursor_rules.py cli/tests/unit/test_cursor_rules.py
git commit -m "feat(cursor): rotula global rule como '(experimental)' no summary

Spec v0.16.5 gap #5: Cursor docs oficial nao confirma que
~/.cursor/rules/ eh lido (User Rules globais sao UI-only via
Settings → Rules). Mantemos o arquivo por compat futura mas o
output do init sinaliza a incerteza pro user:

OK  Cursor rules: 1 global (experimental) + 52 locais instaladas

+1 teste.

Spec: secao 3.5

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: Gemini `.agents/skills/` interop

### Task 7: Detectar e instalar em `.agents/skills/`

**Files:**
- Modify: `cli/plugadvpl/gemini_skills.py`
- Modify: `cli/tests/unit/test_gemini_skills.py` (+2 tests)

- [ ] **Step 1: Add 2 RED tests in TestInstallGeminiSkills**

```python
    def test_installs_to_agents_skills_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v0.16.5 — `.agents/skills/` no projeto → instala lá também (paralelo a .gemini/skills/)."""
        from plugadvpl.gemini_skills import install_gemini_skills
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".gemini").mkdir(parents=True)
        (project / ".agents" / "skills").mkdir(parents=True)

        result = install_gemini_skills(project, version="0.16.5")

        # Instala em ambos
        gemini_files = list(
            (project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md")
        )
        agents_files = list(
            (project / ".agents" / "skills").glob("plugadvpl-*/SKILL.md")
        )
        assert len(gemini_files) == 52
        assert len(agents_files) == 52

    def test_no_install_to_agents_skills_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v0.16.5 — `.agents/skills/` NÃO existe → NÃO cria a pasta."""
        from plugadvpl.gemini_skills import install_gemini_skills
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".gemini").mkdir(parents=True)
        # Sem .agents/ no projeto

        result = install_gemini_skills(project, version="0.16.5")

        # .gemini/skills instala normal
        gemini_files = list(
            (project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md")
        )
        assert len(gemini_files) == 52
        # .agents/ NÃO foi criado
        assert not (project / ".agents").exists()
```

- [ ] **Step 2: Run RED** — Expected 2 failures (atual impl só instala em .gemini/skills/).

- [ ] **Step 3: Modify `install_gemini_skills` em `gemini_skills.py`**

Find `install_gemini_skills` function. Após o loop que instala em `.gemini/skills/`, ADD um segundo loop similar pra `.agents/skills/`:

```python
    # Existing code: install em .gemini/skills/ (não mexer)
    ...

    # v0.16.5 — Se .agents/skills/ existe no projeto, instalar lá tambem
    # (cross-agent standard emergente; tem precedência maior que .gemini/skills/
    # mas instalar em ambos é safer pra user que quer interop multi-tool).
    agents_skills_dir = project_root / ".agents" / "skills"
    if target.install_project and agents_skills_dir.exists():
        for skill_name in _SKILL_GLOBS:
            ok, skp, err = _install_one_gemini_skill(
                skill_name, skills_root, agents_skills_dir, version
            )
            if ok:
                installed_skills_count += 1
            skipped.extend(skp)
            errors.extend(err)
```

Atenção: `installed_skills_count` agora pode chegar a 104 (52+52). Pra evitar inflação, criar campo novo no `InstallResult`:

```python
@dataclass(frozen=True)
class InstallResult:
    installed_global_home: bool
    installed_project_md: bool
    installed_skills_count: int                                    # 0..52 (.gemini/skills/)
    installed_agents_skills_count: int = 0                         # 0..52 (.agents/skills/ se existe)
    skipped_due_to_user_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.installed_global_home:
            parts.append("1 home")
        if self.installed_project_md:
            parts.append("1 projeto")
        if self.installed_skills_count:
            parts.append(f"{self.installed_skills_count} skills (.gemini/)")
        if self.installed_agents_skills_count:
            parts.append(f"{self.installed_agents_skills_count} skills (.agents/)")
        return (" + ".join(parts) + " instaladas") if parts else "nada instalado"
```

E atualizar caller pra incrementar `installed_agents_skills_count` separadamente.

- [ ] **Step 4: Run GREEN**

Expected: 2 passed em TestInstallGeminiSkills. Suite full: 1161+.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/gemini_skills.py cli/tests/unit/test_gemini_skills.py
git commit -m "feat(gemini): instala tambem em .agents/skills/ quando existe (interop)

Spec v0.16.5 gap #6: .agents/skills/ eh cross-agent standard emergente
(Codex, Roo, etc) com precedencia maior que .gemini/skills/. Instalar
em ambos quando ambos existem da cobertura interop sem breaking change.

InstallResult ganha installed_agents_skills_count separado pra nao
inflar contagem nem ambiguar 52+52 vs 52.

+2 testes (with/without .agents/skills/).

Spec: secao 3.6

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 4: Codex .codex/config.toml

### Task 8: `codex_config.py` módulo + integração init

**Files:**
- Create: `cli/plugadvpl/codex_config.py`
- Create: `cli/tests/unit/test_codex_config.py`
- Modify: `cli/plugadvpl/cli.py` (--no-codex flag + chamada)
- Modify: `cli/tests/integration/test_cli.py` (TestInitCodexConfig × 5)

- [ ] **Step 1: Create `cli/tests/unit/test_codex_config.py` com 5 RED tests**

```python
"""Unit tests for plugadvpl/codex_config.py (v0.16.5+)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.codex_config import CodexTarget, detect_codex, render_codex_config, install_codex_config


class TestDetectCodex:
    def test_no_signals_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem .codex/ no projeto, sem 'codex' no PATH → no-op."""
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_codex(project)
        assert result == CodexTarget(install_config=False)

    def test_codex_dir_in_project_triggers_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.codex/` no projeto → install_config=True."""
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".codex").mkdir(parents=True)
        result = detect_codex(project)
        assert result.install_config is True

    def test_codex_in_path_triggers_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`codex` no PATH → install_config=True."""
        monkeypatch.setattr(
            "plugadvpl.codex_config.shutil.which", lambda _: "/usr/local/bin/codex"
        )
        project = tmp_path / "project"
        project.mkdir()
        result = detect_codex(project)
        assert result.install_config is True


class TestRenderCodexConfig:
    def test_includes_version_marker(self) -> None:
        result = render_codex_config(version="0.16.5")
        assert "# plugadvpl-codex-version: 0.16.5" in result

    def test_substitutes_version(self) -> None:
        result = render_codex_config(version="0.16.5")
        assert "__VERSION__" not in result
        assert "0.16.5" in result
```

- [ ] **Step 2: Run RED** — ModuleNotFoundError.

- [ ] **Step 3: Create `cli/plugadvpl/codex_config.py`**

```python
"""OpenAI Codex CLI per-project config generator (v0.16.5+).

Detecta Codex (.codex/ no projeto OU 'codex' no PATH) e gera
.codex/config.toml mínimo com defaults comentados. Codex já lê AGENTS.md
automaticamente (gerado pelo plugadvpl init via _write_agent_fragment).
Este config é opt-in pra customizações futuras.

Spec: docs/superpowers/specs/2026-05-30-multi-agent-v0165-improvements.md secao 3.7
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from plugadvpl._skill_catalog import WriteOutcome, _write_managed_file

CODEX_MARKER_PREFIX = "# plugadvpl-codex-version:"


@dataclass(frozen=True)
class CodexTarget:
    """Decisão do detect_codex: instalar config.toml ou no-op."""

    install_config: bool


def detect_codex(project_root: Path) -> CodexTarget:
    """Detection conservadora: `.codex/` no projeto OU 'codex' no PATH."""
    if (project_root / ".codex").exists():
        return CodexTarget(install_config=True)
    if shutil.which("codex") is not None:
        return CodexTarget(install_config=True)
    return CodexTarget(install_config=False)


_CODEX_CONFIG_TEMPLATE = """# .codex/config.toml — Codex CLI per-project config
#
# Gerado por plugadvpl init. Edite livremente — marker abaixo controla
# regeneração; remova-o pra preservar customizações manuais.
# Docs: https://developers.openai.com/codex/cli/configuration
#
# plugadvpl-codex-version: __VERSION__

[project]
# Codex carrega AGENTS.md automaticamente (gerado também pelo plugadvpl init).
# Para ler arquivos adicionais como contexto:
# project_doc_fallback_filenames = ["CLAUDE.md"]

[skills]
# Codex lê SKILL.md compatíveis cross-tool. Nossas skills/plugadvpl-*/SKILL.md
# funcionam diretamente — Codex faz auto-discovery quando habilitado.
# enabled = true
"""


def render_codex_config(version: str) -> str:
    """Gera conteúdo de .codex/config.toml com marker."""
    return _CODEX_CONFIG_TEMPLATE.replace("__VERSION__", version)


@dataclass(frozen=True)
class InstallResult:
    """Resumo do install_codex_config."""

    installed: bool
    skipped_due_to_user_file: bool = False
    error: str | None = None

    def summary(self) -> str:
        if self.installed:
            return ".codex/config.toml instalado"
        if self.skipped_due_to_user_file:
            return ".codex/config.toml já existe sem marker (preservado)"
        return "nada instalado"


def install_codex_config(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write. NUNCA propaga exception."""
    try:
        target = detect_codex(project_root)
    except Exception as e:  # noqa: BLE001
        return InstallResult(installed=False, error=f"detect_codex falhou: {e!r}")

    if not target.install_config:
        return InstallResult(installed=False)

    try:
        config_path = project_root / ".codex" / "config.toml"
        content = render_codex_config(version)
        outcome = _write_managed_file(config_path, content, CODEX_MARKER_PREFIX)
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return InstallResult(installed=True)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            return InstallResult(installed=False, skipped_due_to_user_file=True)
        return InstallResult(installed=False, error=f"falha ao escrever {config_path}")
    except Exception as e:  # noqa: BLE001
        return InstallResult(installed=False, error=f"install_codex_config erro: {e!r}")
```

- [ ] **Step 4: Run GREEN unit**

Expected: 5 passed.

- [ ] **Step 5: Wire em `cli.py::init`**

Find init function. Add flag `no_codex`:

```python
    no_codex: Annotated[
        bool,
        typer.Option(
            "--no-codex",
            help="Não instala .codex/config.toml mesmo se Codex detectado.",
        ),
    ] = False,
```

After `if not no_gemini:` block, add:

```python
    if not no_codex:
        from plugadvpl.codex_config import install_codex_config
        codex_result = install_codex_config(root, __version__)
        if not ctx.obj["quiet"]:
            if codex_result.installed:
                typer.echo(f"OK  Codex: {codex_result.summary()}")
            if codex_result.error:
                typer.secho(
                    f"⚠  Codex: {codex_result.error}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            if codex_result.skipped_due_to_user_file:
                typer.secho(
                    f"⚠  Codex: .codex/config.toml existe sem marker — preservado",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
```

- [ ] **Step 6: Add integration tests `TestInitCodexConfig` (5)**

Em `test_cli.py`, antes de `TestIngest`, ADD:

```python
class TestInitCodexConfig:
    """v0.16.5 — init grava .codex/config.toml quando Codex detectado."""

    def test_no_op_without_codex_signal(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_codex1"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert not (synthetic_project / ".codex").exists()
        assert "Codex:" not in result.stdout

    def test_installs_when_project_has_codex_dir(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_codex2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        (synthetic_project / ".codex").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert (synthetic_project / ".codex" / "config.toml").exists()
        assert "Codex:" in result.stdout

    def test_no_codex_flag_skips(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_codex3"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        (synthetic_project / ".codex").mkdir()
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "init", "--no-codex"]
        )
        assert result.exit_code == 0
        assert not (synthetic_project / ".codex" / "config.toml").exists()

    def test_idempotent(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_codex4"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        (synthetic_project / ".codex").mkdir()
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        content = (synthetic_project / ".codex" / "config.toml").read_text(encoding="utf-8")
        # Marker aparece UMA vez
        assert content.count("plugadvpl-codex-version:") == 1

    def test_preserves_user_file_without_marker(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_codex5"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        codex_dir = synthetic_project / ".codex"
        codex_dir.mkdir()
        user_config = codex_dir / "config.toml"
        user_config.write_text("# my own config, no marker", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        # Preserva
        assert user_config.read_text(encoding="utf-8") == "# my own config, no marker"
```

Também atualizar `TestInit._isolate_cursor_home` autouse fixture pra mockar `codex_config.shutil.which`:

```python
monkeypatch.setattr(
    "plugadvpl.codex_config.shutil.which", lambda _: None
)
```

- [ ] **Step 7: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov`

Expected: 1166+ passed.

- [ ] **Step 8: Commit**

```bash
git add cli/plugadvpl/codex_config.py cli/tests/unit/test_codex_config.py cli/plugadvpl/cli.py cli/tests/integration/test_cli.py
git commit -m "feat(codex): .codex/config.toml minimo no init + flag --no-codex

Spec v0.16.5 gap #7: Codex CLI usa .codex/config.toml per-project.
Geramos template minimo com defaults comentados + marker plugadvpl-codex-version.

Codex CLI ja le AGENTS.md (gerado pelo init via _write_agent_fragment).
Este config eh opt-in pra customizacoes futuras (project_doc_fallback_filenames, etc.).

5 unit tests + 5 integration tests TestInitCodexConfig.

Spec: secao 3.7

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 5: Doctor --check-agents

### Task 9: `agent_doctor.py` módulo + CLI flag

**Files:**
- Create: `cli/plugadvpl/agent_doctor.py`
- Create: `cli/tests/unit/test_agent_doctor.py`
- Modify: `cli/plugadvpl/cli.py` (doctor --check-agents flag)
- Modify: `cli/tests/integration/test_cli.py` (TestDoctorCheckAgents × 3)

- [ ] **Step 1: Create `cli/tests/unit/test_agent_doctor.py` com 10 RED tests**

```python
"""Unit tests for plugadvpl/agent_doctor.py (v0.16.5+)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.agent_doctor import (
    AgentCheck,
    DoctorReport,
    check_claude_md,
    check_agents_md,
    check_cursor_rules,
    check_copilot_instructions,
    check_gemini_skills,
    check_skill_descriptions_keywords,
    run_checks,
)


class TestCheckClaudeMd:
    def test_valid_claude_md(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text(
            "<!-- BEGIN plugadvpl -->\n"
            "<!-- plugadvpl-fragment-version: 0.16.5 -->\nBody\n"
            "<!-- END plugadvpl -->\n",
            encoding="utf-8",
        )
        result = check_claude_md(tmp_path, expected_version="0.16.5")
        assert result.status == "ok"

    def test_missing_claude_md(self, tmp_path: Path) -> None:
        result = check_claude_md(tmp_path, expected_version="0.16.5")
        assert result.status == "missing"


class TestCheckCursorRules:
    def test_valid_cursor_rules_directory(self, tmp_path: Path) -> None:
        rules_dir = tmp_path / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "plugadvpl-arch.mdc").write_text(
            "---\ndescription: X\nglobs: **/*.prw\nalwaysApply: false\n---\n"
            "<!-- plugadvpl-rule-version: 0.16.5 -->\nBody\n",
            encoding="utf-8",
        )
        result = check_cursor_rules(tmp_path, expected_version="0.16.5")
        assert result.status == "ok"
        assert "1 local" in result.detail

    def test_flags_cursor_globs_as_array(self, tmp_path: Path) -> None:
        """v0.16.5 — globs como array YAML é INCORRETO (deve ser string com vírgulas)."""
        rules_dir = tmp_path / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "plugadvpl-arch.mdc").write_text(
            "---\ndescription: X\nglobs:\n  - **/*.prw\nalwaysApply: false\n---\n"
            "<!-- plugadvpl-rule-version: 0.16.5 -->\nBody\n",
            encoding="utf-8",
        )
        result = check_cursor_rules(tmp_path, expected_version="0.16.5")
        assert result.status == "fail"
        assert "globs" in result.detail.lower()


class TestCheckCopilotInstructions:
    def test_valid_copilot_instructions(self, tmp_path: Path) -> None:
        inst_dir = tmp_path / ".github" / "instructions"
        inst_dir.mkdir(parents=True)
        (inst_dir / "plugadvpl-arch.instructions.md").write_text(
            '---\napplyTo: "**/*.prw"\ndescription: X\n---\n'
            "<!-- plugadvpl-instructions-version: 0.16.5 -->\nBody\n",
            encoding="utf-8",
        )
        result = check_copilot_instructions(tmp_path, expected_version="0.16.5")
        assert result.status == "ok"


class TestCheckGeminiSkills:
    def test_valid_gemini_skills(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".gemini" / "skills" / "plugadvpl-arch"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: plugadvpl-arch\ndescription: ADVPL arch\n---\n"
            "<!-- plugadvpl-gemini-version: 0.16.5 -->\nBody\n",
            encoding="utf-8",
        )
        result = check_gemini_skills(tmp_path, expected_version="0.16.5")
        assert result.status == "ok"


class TestKeywordsCheck:
    def test_flags_skill_without_advpl_keyword(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "myskill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A generic description\n---\nBody\n",
            encoding="utf-8",
        )
        flagged = check_skill_descriptions_keywords(tmp_path)
        assert "myskill" in flagged

    def test_does_not_flag_skill_with_advpl_keyword(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "myskill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: ADVPL Protheus stuff\n---\nBody\n",
            encoding="utf-8",
        )
        flagged = check_skill_descriptions_keywords(tmp_path)
        assert "myskill" not in flagged


class TestRunChecks:
    def test_run_all_checks_returns_report(self, tmp_path: Path) -> None:
        report = run_checks(tmp_path, expected_version="0.16.5")
        assert isinstance(report, DoctorReport)
        assert len(report.checks) >= 5  # CLAUDE, AGENTS, Cursor, Copilot, Gemini
```

- [ ] **Step 2: Run RED** — ModuleNotFoundError.

- [ ] **Step 3: Create `cli/plugadvpl/agent_doctor.py`**

```python
"""Multi-agent files validator (v0.16.5+).

Valida formato dos arquivos gerados por plugadvpl init pra 5 agentes
(Claude, Codex/AGENTS.md, Cursor, Copilot, Gemini) sem precisar instalar
os agentes externos. Pretende cobrir gaps que não temos validação E2E
real (Cursor não tem CLI validate; Copilot não tem diagnose; Gemini não
tem agent-side check via CLI).

Spec: docs/superpowers/specs/2026-05-30-multi-agent-v0165-improvements.md secao 3.3
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# Keywords mínimas que SKILL.md descriptions devem conter pra Gemini JIT activation
_ADVPL_KEYWORDS = ("ADVPL", "Protheus", "TLPP", ".prw", "SX", "dicionário", "dicionario")


@dataclass(frozen=True)
class AgentCheck:
    """Resultado de check de um agente específico."""

    name: str  # "claude_md", "cursor_rules", etc.
    status: Literal["ok", "missing", "fail", "warning"]
    detail: str

    def emoji(self) -> str:
        return {"ok": "✅", "missing": "—", "fail": "❌", "warning": "⚠️"}[self.status]


@dataclass(frozen=True)
class DoctorReport:
    """Agregado de checks por todos agentes."""

    checks: list[AgentCheck]
    skills_without_keywords: list[str] = field(default_factory=list)

    def has_failures(self) -> bool:
        return any(c.status in ("fail", "warning") for c in self.checks)


def check_claude_md(root: Path, expected_version: str) -> AgentCheck:
    """Verifica CLAUDE.md fragment + marker version."""
    f = root / "CLAUDE.md"
    if not f.exists():
        return AgentCheck("claude_md", "missing", "CLAUDE.md ausente (rode init?)")
    content = f.read_text(encoding="utf-8", errors="replace")
    if "<!-- BEGIN plugadvpl -->" not in content:
        return AgentCheck("claude_md", "fail", "Fragment BEGIN/END markers ausentes")
    m = re.search(r"<!--\s*plugadvpl-fragment-version:\s*([\w.+-]+)\s*-->", content)
    if not m:
        return AgentCheck("claude_md", "fail", "Marker version ausente")
    found_version = m.group(1)
    if found_version != expected_version:
        return AgentCheck(
            "claude_md", "warning",
            f"Versão {found_version} (esperado {expected_version}) — rode init pra atualizar"
        )
    return AgentCheck("claude_md", "ok", f"OK ({found_version})")


def check_agents_md(root: Path, expected_version: str) -> AgentCheck:
    """Similar a check_claude_md mas pra AGENTS.md."""
    f = root / "AGENTS.md"
    if not f.exists():
        return AgentCheck("agents_md", "missing", "AGENTS.md ausente (rode init?)")
    content = f.read_text(encoding="utf-8", errors="replace")
    if "<!-- BEGIN plugadvpl -->" not in content:
        return AgentCheck("agents_md", "fail", "Fragment markers ausentes")
    m = re.search(r"<!--\s*plugadvpl-fragment-version:\s*([\w.+-]+)\s*-->", content)
    if not m:
        return AgentCheck("agents_md", "fail", "Marker version ausente")
    found = m.group(1)
    if found != expected_version:
        return AgentCheck("agents_md", "warning", f"Versão {found} (esperado {expected_version})")
    return AgentCheck("agents_md", "ok", f"OK ({found})")


def check_cursor_rules(root: Path, expected_version: str) -> AgentCheck:
    """Verifica .cursor/rules/plugadvpl-*.mdc — globs deve ser STRING (não array)."""
    rules_dir = root / ".cursor" / "rules"
    if not rules_dir.exists():
        return AgentCheck("cursor_rules", "missing", ".cursor/rules/ ausente (Cursor não detectado?)")
    files = sorted(rules_dir.glob("plugadvpl-*.mdc"))
    if not files:
        return AgentCheck("cursor_rules", "missing", "Nenhum plugadvpl-*.mdc em .cursor/rules/")
    failed = []
    stale = []
    for f in files:
        content = f.read_text(encoding="utf-8", errors="replace")
        # Frontmatter check
        if not content.startswith("---\n"):
            failed.append(f"{f.name}: sem frontmatter")
            continue
        # globs deve ser string (não array YAML)
        fm_end = content.find("\n---\n", 4)
        if fm_end == -1:
            failed.append(f"{f.name}: frontmatter malformado")
            continue
        fm = content[4:fm_end]
        if "globs:" in fm:
            # Buscar linha com "globs:"
            for line in fm.split("\n"):
                if line.startswith("globs:"):
                    value = line[len("globs:"):].strip()
                    if value.startswith("-"):  # array YAML marker
                        failed.append(f"{f.name}: globs é array YAML (deve ser string com vírgulas)")
                    break
        # Marker version
        m = re.search(r"<!--\s*plugadvpl-rule-version:\s*([\w.+-]+)\s*-->", content)
        if m and m.group(1) != expected_version:
            stale.append(f"{f.name}: versão {m.group(1)}")
    if failed:
        return AgentCheck("cursor_rules", "fail", f"{len(failed)} files: {'; '.join(failed[:3])}")
    if stale:
        return AgentCheck("cursor_rules", "warning", f"{len(stale)} stale: {'; '.join(stale[:3])}")
    return AgentCheck("cursor_rules", "ok", f"{len(files)} locais OK")


def check_copilot_instructions(root: Path, expected_version: str) -> AgentCheck:
    """Verifica .github/instructions/plugadvpl-*.instructions.md."""
    inst_dir = root / ".github" / "instructions"
    if not inst_dir.exists():
        return AgentCheck("copilot_instructions", "missing", ".github/instructions/ ausente")
    files = sorted(inst_dir.glob("plugadvpl-*.instructions.md"))
    if not files:
        return AgentCheck("copilot_instructions", "missing", "Nenhum arquivo plugadvpl-* encontrado")
    failed = []
    stale = []
    for f in files:
        content = f.read_text(encoding="utf-8", errors="replace")
        # applyTo deve ser string ÚNICA (não array)
        m_apply = re.search(r'applyTo:\s*(["\']?)([^"\'\n]+)\1', content)
        if not m_apply:
            # Verificar se é array
            if re.search(r"applyTo:\s*\n\s*-", content):
                failed.append(f"{f.name}: applyTo é array YAML (deve ser string)")
                continue
        m_ver = re.search(r"<!--\s*plugadvpl-instructions-version:\s*([\w.+-]+)\s*-->", content)
        if m_ver and m_ver.group(1) != expected_version:
            stale.append(f"{f.name}: versão {m_ver.group(1)}")
    if failed:
        return AgentCheck("copilot_instructions", "fail", "; ".join(failed[:3]))
    if stale:
        return AgentCheck("copilot_instructions", "warning", f"{len(stale)} stale")
    return AgentCheck("copilot_instructions", "ok", f"{len(files)} instructions OK")


def check_gemini_skills(root: Path, expected_version: str) -> AgentCheck:
    """Verifica .gemini/skills/plugadvpl-*/SKILL.md frontmatter."""
    skills_dir = root / ".gemini" / "skills"
    if not skills_dir.exists():
        return AgentCheck("gemini_skills", "missing", ".gemini/skills/ ausente")
    skill_files = sorted(skills_dir.glob("plugadvpl-*/SKILL.md"))
    if not skill_files:
        return AgentCheck("gemini_skills", "missing", "Nenhuma skill plugadvpl-*/SKILL.md")
    failed = []
    stale = []
    for f in skill_files:
        content = f.read_text(encoding="utf-8", errors="replace")
        if not content.startswith("---\n"):
            failed.append(f"{f.parent.name}: sem frontmatter")
            continue
        fm_end = content.find("\n---\n", 4)
        if fm_end == -1:
            failed.append(f"{f.parent.name}: frontmatter malformado")
            continue
        fm = content[4:fm_end]
        if "name:" not in fm:
            failed.append(f"{f.parent.name}: sem 'name' field")
        if "description:" not in fm:
            failed.append(f"{f.parent.name}: sem 'description' field")
        m_ver = re.search(r"<!--\s*plugadvpl-gemini-version:\s*([\w.+-]+)\s*-->", content)
        if m_ver and m_ver.group(1) != expected_version:
            stale.append(f"{f.parent.name}: versão {m_ver.group(1)}")
    if failed:
        return AgentCheck("gemini_skills", "fail", "; ".join(failed[:3]))
    if stale:
        return AgentCheck("gemini_skills", "warning", f"{len(stale)} stale")
    return AgentCheck("gemini_skills", "ok", f"{len(skill_files)} skills OK")


def check_skill_descriptions_keywords(skills_root: Path) -> list[str]:
    """Lista SKILL.md cujas description NÃO contém keywords ADVPL/Protheus.

    Returns: lista de skill names (basename do dir) flagged.
    """
    flagged = []
    for skill_md in skills_root.rglob("SKILL.md"):
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"^description:\s*(.+?)$", content, re.MULTILINE)
        if not m:
            continue
        desc = m.group(1)
        if not any(kw.lower() in desc.lower() for kw in _ADVPL_KEYWORDS):
            flagged.append(skill_md.parent.name)
    return sorted(flagged)


def run_checks(root: Path, expected_version: str) -> DoctorReport:
    """Executa todos checks. Retorna DoctorReport agregado."""
    checks = [
        check_claude_md(root, expected_version),
        check_agents_md(root, expected_version),
        check_cursor_rules(root, expected_version),
        check_copilot_instructions(root, expected_version),
        check_gemini_skills(root, expected_version),
    ]
    # Skills keywords check (se skills/ existe no root)
    skills_root = root / "skills"
    flagged = []
    if skills_root.exists():
        flagged = check_skill_descriptions_keywords(skills_root)
    return DoctorReport(checks=checks, skills_without_keywords=flagged)
```

- [ ] **Step 4: Run GREEN unit** — 10 passed.

- [ ] **Step 5: Wire `--check-agents` flag em `cli.py doctor command`**

Find `doctor` command (`@app.command()` def doctor). Adicionar flag:

```python
@app.command()
def doctor(
    ctx: typer.Context,
    check_agents: Annotated[
        bool,
        typer.Option(
            "--check-agents",
            help="Valida formato dos arquivos gerados pra todos 5 agentes (CLAUDE.md, AGENTS.md, Cursor, Copilot, Gemini).",
        ),
    ] = False,
    # ... outras flags existentes
) -> None:
    """... existing docstring ..."""
    root: Path = ctx.obj["root"]
    if check_agents:
        from plugadvpl.agent_doctor import run_checks
        report = run_checks(root, expected_version=__version__)
        for check in report.checks:
            typer.echo(f"{check.emoji()}  {check.name}: {check.detail}")
        if report.skills_without_keywords:
            typer.echo(
                f"\n⚠️  {len(report.skills_without_keywords)} skill(s) sem keywords ADVPL/Protheus:"
            )
            for name in report.skills_without_keywords[:10]:
                typer.echo(f"     - {name}")
            if len(report.skills_without_keywords) > 10:
                typer.echo(f"     ... e mais {len(report.skills_without_keywords) - 10}")
        # Exit code: 1 se há failures críticas
        if any(c.status == "fail" for c in report.checks):
            raise typer.Exit(code=1)
        return
    # ... resto da doctor function existente
```

- [ ] **Step 6: Add 3 integration tests `TestDoctorCheckAgents`**

```python
class TestDoctorCheckAgents:
    """v0.16.5 — plugadvpl doctor --check-agents valida arquivos gerados."""

    def test_reports_all_green_after_init(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Após init completo com .cursor/, .github/, .gemini/ — todos green."""
        fake_home = synthetic_project.parent / "fake_home_doctor1"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        (synthetic_project / ".github").mkdir()
        (synthetic_project / ".gemini").mkdir()
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "doctor", "--check-agents"]
        )
        assert result.exit_code == 0
        assert "claude_md" in result.stdout
        assert "✅" in result.stdout  # algum check passou

    def test_reports_missing_when_no_init(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem init → CLAUDE.md/AGENTS.md ausentes."""
        fake_home = synthetic_project.parent / "fake_home_doctor2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "doctor", "--check-agents"]
        )
        # Exit 0 (missing != fail)
        assert result.exit_code == 0
        assert "missing" in result.stdout.lower() or "—" in result.stdout

    def test_exit_code_1_on_fail(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLAUDE.md sem fragment markers → check fails, exit 1."""
        fake_home = synthetic_project.parent / "fake_home_doctor3"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        (synthetic_project / "CLAUDE.md").write_text(
            "# Custom CLAUDE.md without plugadvpl fragment\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "doctor", "--check-agents"]
        )
        assert result.exit_code == 1
```

- [ ] **Step 7: Run GREEN + full suite**

Expected: 1179+ passed.

- [ ] **Step 8: Commit**

```bash
git add cli/plugadvpl/agent_doctor.py cli/plugadvpl/cli.py cli/tests/unit/test_agent_doctor.py cli/tests/integration/test_cli.py
git commit -m "feat(doctor): plugadvpl doctor --check-agents valida 5 agentes

Spec v0.16.5 gap #3: agentes externos (Cursor, Copilot, Gemini) nao tem
CLI oficial pra validar formato dos arquivos gerados (cursor validate-rules,
gh copilot diagnose — nenhum existe). Implementamos validacao local que
checa frontmatter parseavel, marker version, formato canonico (globs/applyTo
string vs array), keywords ADVPL nas descriptions.

Novo modulo agent_doctor.py (~250 linhas):
- AgentCheck/DoctorReport dataclasses
- check_claude_md, check_agents_md, check_cursor_rules,
  check_copilot_instructions, check_gemini_skills,
  check_skill_descriptions_keywords
- run_checks orchestrator

CLI: plugadvpl doctor --check-agents
- Exit 0 se all green/missing
- Exit 1 se algum check fail
- Output emoji-tagged + skill keywords flagged list

10 unit tests + 3 integration tests.

Spec: secao 3.3

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 6: Descriptions audit + manual edit

### Task 10: Auditar 52 descriptions e editar as flagged

**Files:**
- Create: `d:\tmp\audit_skill_descriptions.py` (one-off script — NÃO commit)
- Modify: `skills/<X>/SKILL.md` × N (manual edit das flagged)

- [ ] **Step 1: Create audit script `d:\tmp\audit_skill_descriptions.py`**

```python
"""One-off audit: list SKILL.md sem keywords ADVPL/Protheus.

NÃO automatiza fix — apenas reporta. Editar manual depois.
"""
from pathlib import Path
import re

KEYWORDS = ("ADVPL", "Protheus", "TLPP", ".prw", "SX", "dicionário", "dicionario")

skills_root = Path("d:/IA/Projetos/plugadvpl/skills")
flagged = []
total = 0
for skill_md in sorted(skills_root.rglob("SKILL.md")):
    total += 1
    content = skill_md.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^description:\s*(.+?)$", content, re.MULTILINE)
    if not m:
        flagged.append((skill_md.parent.name, "<no description>"))
        continue
    desc = m.group(1)
    if not any(kw.lower() in desc.lower() for kw in KEYWORDS):
        flagged.append((skill_md.parent.name, desc[:80]))

print(f"Total SKILL.md scanned: {total}")
print(f"Flagged (sem keywords ADVPL/Protheus): {len(flagged)}")
print()
for name, desc in flagged:
    print(f"  - {name}: {desc}")
```

Run: `& "C:\Users\jonil\AppData\Local\Programs\Python\Python312\python.exe" d:\tmp\audit_skill_descriptions.py`

Output esperado: lista de skills flagged. Threshold: ≥40 das 52 (~77%) devem passar pra accept.

- [ ] **Step 2: Edit manually each flagged SKILL.md**

Pra CADA skill flagged no output do Step 1:
- Read `d:\IA\Projetos\plugadvpl\skills\<name>\SKILL.md`
- Edit linha `description:` no frontmatter pra adicionar pelo menos 1 keyword
- Exemplos de adições mínimas:
  - `Pesquisa simbolos (funcoes, classes, metodos) no indice plugadvpl` → `Pesquisa simbolos ADVPL/TLPP (funcoes, classes, metodos) no indice plugadvpl`
  - `Roda lint plugadvpl em um arquivo (13 regras MVP)` → `Roda lint ADVPL/.prw via plugadvpl em um arquivo (13 regras MVP)`
  - `Lista usos de uma tabela ERP (...)` → `Lista usos de uma tabela ERP Protheus (...)`

**Skips OK:** Meta-skills genuinamente genéricas (`init`, `help`, `setup`) NÃO precisam de keywords — são meta-comandos de plugadvpl. Documentar quais foram skipadas.

- [ ] **Step 3: Re-run audit + count**

Run script again. Expected: ≥40 das 52 pass (or document skips).

- [ ] **Step 4: Run full suite (regressão)**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov`

Expected: 1179+ passed (changes em SKILL.md afetam test_lint_catalog_consistency.py? Verificar — esse teste já existe e cobre estrutura, não description content).

- [ ] **Step 5: Commit**

Lista de skills editadas pode ser longa. Commit message lista as keywords adicionadas:

```bash
git add skills/
git commit -m "docs(skills): audit descriptions com keywords ADVPL/Protheus (Gemini JIT activation)

Spec v0.16.5 gap #2: Gemini ativa skills via matching semantico da
description. Varias descriptions genericas (find, lint, callers, grep,
etc.) sem keywords ADVPL/Protheus/TLPP impedem JIT activation correta.

Auditadas 52 SKILL.md via script. <N> editadas pra incluir pelo menos
1 de: ADVPL, Protheus, TLPP, .prw, SX. Meta-skills (init, help, setup)
intencionalmente skipadas (sao meta-comandos generality).

Threshold accept: ≥40/52 pass audit (descriptions com keyword).
Atual: <X>/52 com keyword.

Spec: secao 3.2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 7: TestInitMultiAgent + release

### Task 11: `TestInitMultiAgent` smoke test

**Files:**
- Modify: `cli/tests/integration/test_cli.py` (+1 test)

- [ ] **Step 1: Add 1 test em test_cli.py**

```python
class TestInitMultiAgent:
    """v0.16.5 — init completo com 5 agentes detectados não conflita."""

    def test_init_with_all_5_agents_detected(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Init com .cursor/, .github/, .gemini/, .codex/ no projeto +
        ~/.cursor/, ~/.gemini/ no home → todos 5 agentes instalados."""
        fake_home = synthetic_project.parent / "fake_home_multi"
        (fake_home / ".cursor" / "rules").mkdir(parents=True)
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        (synthetic_project / ".github").mkdir()
        (synthetic_project / ".gemini").mkdir()
        (synthetic_project / ".codex").mkdir()

        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])

        assert result.exit_code == 0
        # Claude Code
        assert (synthetic_project / "CLAUDE.md").exists()
        # Codex/AGENTS.md
        assert (synthetic_project / "AGENTS.md").exists()
        # Cursor
        assert (synthetic_project / ".cursor" / "rules").exists()
        cursor_files = list((synthetic_project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(cursor_files) == 52
        # Copilot
        assert (synthetic_project / ".github" / "copilot-instructions.md").exists()
        copilot_files = list((synthetic_project / ".github" / "instructions").glob("plugadvpl-*.instructions.md"))
        assert len(copilot_files) == 52
        # Gemini
        assert (synthetic_project / "GEMINI.md").exists()
        gemini_files = list((synthetic_project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md"))
        assert len(gemini_files) == 52
        # Codex
        assert (synthetic_project / ".codex" / "config.toml").exists()
```

- [ ] **Step 2: Run + Commit**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestInitMultiAgent -v --no-cov`

Expected: 1 passed.

```bash
git add cli/tests/integration/test_cli.py
git commit -m "test(init): TestInitMultiAgent smoke — todos 5 agentes sem conflito

Spec v0.16.5 critério #1: validar que init com 5 sinais ativos instala
todos sem corromper algum no caminho. Smoke end-to-end:
- CLAUDE.md (Claude Code)
- AGENTS.md (Codex e padrão multi-agente)
- .cursor/rules/plugadvpl-*.mdc × 52 (Cursor)
- .github/copilot-instructions.md + .github/instructions/*.instructions.md × 52 (Copilot)
- ~/.gemini/GEMINI.md + GEMINI.md projeto + .gemini/skills/*/SKILL.md × 52 (Gemini)
- .codex/config.toml (Codex)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: README + CHANGELOG + bump + release

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `.claude-plugin/plugin.json` (0.16.4 → 0.16.5)
- Modify: `.claude-plugin/marketplace.json` (0.16.4 → 0.16.5)
- Modify: `skills/*/SKILL.md` × 26 (uvx version bump)

- [ ] **Step 1: Bump manifests**

Edit `.claude-plugin/plugin.json`: `"version": "0.16.4"` → `"version": "0.16.5"`.
Edit `.claude-plugin/marketplace.json`: `"version": "0.16.4"` → `"version": "0.16.5"`.

- [ ] **Step 2: Bump skills via script**

`d:\tmp\bump_skills_v0165.py`:
```python
from pathlib import Path
OLD = "plugadvpl@0.16.4"; NEW = "plugadvpl@0.16.5"
skills_root = Path("d:/IA/Projetos/plugadvpl/skills")
n = 0
for p in skills_root.rglob("SKILL.md"):
    raw = p.read_bytes()
    if OLD.encode() in raw:
        p.write_bytes(raw.replace(OLD.encode(), NEW.encode()))
        n += 1
print(f"{n} skill(s) bumped")
```

Run: `& "C:\Users\jonil\AppData\Local\Programs\Python\Python312\python.exe" d:\tmp\bump_skills_v0165.py`

Expected: `26 skill(s) bumped`.

- [ ] **Step 3: CHANGELOG entry**

Em `CHANGELOG.md`, após `## [Unreleased]`, INSERT:

```markdown
## [0.16.5] - 2026-05-30

### Fixed — `_transform_body` agora respeita formato por agente (CRÍTICO)

Antes da v0.16.5, `_transform_body` em `_skill_catalog.py` substituía `/plugadvpl:<X>` por `` `Bash: uvx plugadvpl@<ver> <X>` `` (sintaxe MDC Cursor-específica) em **todos** os agentes. Copilot e Gemini interpretavam isso como string literal, não como sugestão de comando — perdiam ~50% do valor das 52 skills.

Agora `_transform_body` aceita param `style: Literal["cursor", "plain"]`:
- `style="cursor"` (Cursor opt-in) — emite `` `Bash: uvx ...` `` (MDC syntax)
- `style="plain"` (default; Copilot/Gemini) — emite `uvx plugadvpl@<ver> <X>` (texto puro)

Todos callers atualizados: `cursor_rules.render_skill_rule` passa `style="cursor"`; `copilot_instructions.render_skill_instructions` e `gemini_skills.render_skill_for_gemini` passam `style="plain"`.

### Added — `plugadvpl doctor --check-agents` valida 5 agentes

Novo subcomando que valida formato dos arquivos gerados pra todos 5 agentes (Claude, Codex/AGENTS.md, Cursor, Copilot, Gemini) **sem precisar instalar os agentes**. Nenhum agente externo tem CLI oficial de validação — preenchemos o gap.

Checks:
- CLAUDE.md e AGENTS.md: fragment markers + version
- Cursor: `.cursor/rules/plugadvpl-*.mdc` frontmatter parseável, `globs` é STRING (não array), version
- Copilot: `.github/instructions/plugadvpl-*.instructions.md` `applyTo` é STRING (não array), version
- Gemini: `.gemini/skills/plugadvpl-*/SKILL.md` frontmatter `name`+`description`, version
- Keywords: 52 SKILL.md descriptions têm "ADVPL"/"Protheus"/"TLPP"/".prw"/"SX"

Output emoji-tagged. Exit code 1 se algum check fail.

### Added — Cursor meta-skills com `alwaysApply: true`

12 meta-skills transversais (init, ingest, status, doctor, help, workflow, trace, setup, ingest-protheus, reindex, execauto, docs) viravam "Manual only" no Cursor (precisavam `@plugadvpl-init` explícito). Agora ganham `alwaysApply: true` automaticamente.

### Added — Gemini `.agents/skills/` cross-agent install

Quando projeto tem `.agents/skills/` (cross-agent standard emergente, precedência maior que `.gemini/skills/`), Gemini install duplica nas duas pastas. `InstallResult` ganha campo `installed_agents_skills_count` separado.

### Added — Codex `.codex/config.toml` mínimo

Codex CLI usa `.codex/config.toml` per-project. Quando detectado (`.codex/` no projeto OU `codex` no PATH), `init` gera template mínimo com defaults comentados + marker `# plugadvpl-codex-version: X.Y.Z`. Flag `--no-codex` desabilita.

Codex já lê AGENTS.md (gerado pelo init via fragment writer). Este config é opt-in pra customizações futuras.

### Audited — 52 SKILL.md descriptions com keywords ADVPL/Protheus

Gemini ativa skills via matching semântico da `description`. Descrições genéricas sem keywords (find, lint, callers, grep, etc.) impediam JIT activation. Auditadas e editadas pra incluir pelo menos 1 keyword de: ADVPL, Protheus, TLPP, .prw, SX. Meta-skills genuinamente genéricas (init, help, setup) intencionalmente skipadas. Threshold accept: ≥40/52 pass.

### Changed — Cursor global rule rotulada como "(experimental)"

`OK Cursor rules: 1 global (experimental) + 52 locais instaladas`. Cursor docs oficial não confirma que `~/.cursor/rules/` é lido (User Rules globais são UI-only via Settings → Rules). Mantemos o código por compat futura mas sinalizamos a incerteza.

### Added — 30+ testes novos

- 3 em TestTransformBody (`_skill_catalog`)
- 4 em test_cursor_rules (style + meta_always_apply + experimental + cursor style assertion)
- 1 em test_copilot_instructions (plain style)
- 2 em test_gemini_skills (plain style + .agents/skills/)
- 5 em test_codex_config
- 10 em test_agent_doctor
- 5 em TestInitCodexConfig
- 3 em TestDoctorCheckAgents
- 1 em TestInitMultiAgent

Suite full: 1151 → ~1185 passed.

### Bumped

- `uvx plugadvpl@0.16.4` → `uvx plugadvpl@0.16.5` nas 26 skills.
- `plugin.json` / `marketplace.json` → 0.16.5.
```

- [ ] **Step 4: README entry + seção multi-agente**

Em `README.md`, find `### v0.16.4 — Gemini CLI native skills`. INSERT BEFORE it:

```markdown
### v0.16.5 — Multi-agente post-research improvements

- **CRITICAL FIX**: `_transform_body` agora respeita formato por agente (Cursor MDC `Bash:` vs Copilot/Gemini texto puro). Antes v0.16.5, Copilot e Gemini recebiam sintaxe Cursor-específica e interpretavam como string literal — perdiam 50% do valor das 52 skills.
- **`plugadvpl doctor --check-agents`**: comando novo valida formato dos arquivos gerados pra todos 5 agentes sem precisar instalar Cursor/Copilot/Gemini (nenhum tem CLI oficial de validação).
- **Cursor**: 12 meta-skills transversais ganham `alwaysApply: true` (antes ficavam "Manual only" no Cursor).
- **Gemini**: detecta e instala em `.agents/skills/` (cross-agent standard emergente) quando existe.
- **Codex**: `.codex/config.toml` mínimo gerado quando detectado.
- **52 SKILL.md descriptions auditadas** pra incluir keywords ADVPL/Protheus (Gemini JIT activation).
- 30+ testes novos. Suite: 1151 → ~1185 passed

```

Adicionar também seção **"Cobertura multi-agente"** após "Por que plugadvpl":

```markdown
## Cobertura multi-agente

`plugadvpl init` gera contexto nativo pra **5 agentes IA**:

| Agente | Arquivo(s) gerado(s) | Detecção |
|---|---|---|
| **Claude Code** | `CLAUDE.md` (fragment versionado) | sempre |
| **Codex** + AGENTS.md ecosystem | `AGENTS.md` (gêmeo idêntico) | sempre |
| **Cursor** | `.cursor/rules/plugadvpl-*.mdc` × 52 | `.cursor/` no projeto |
| **GitHub Copilot** | `.github/copilot-instructions.md` + `.github/instructions/plugadvpl-*.instructions.md` × 52 | `.github/` no projeto |
| **Gemini CLI** | `GEMINI.md` + `.gemini/skills/plugadvpl-*/SKILL.md` × 52 | `~/.gemini/` ou `gemini` no PATH ou `.gemini/` no projeto |
| **+ Codex CLI** (extra) | `.codex/config.toml` | `.codex/` ou `codex` no PATH |

### Smoke test manual por agente

Como nenhum agente externo tem CLI oficial de validação, use:

```bash
# Validação local (sem precisar instalar agentes):
plugadvpl doctor --check-agents
```

Para validação end-to-end real:
- **Cursor**: abrir projeto, abrir `.prw`, ver painel de contexto no Chat (régua no rodapé) mostrar rules carregadas
- **Copilot (VSCode)**: Menu "..." no Chat → "Show Agent Debug Logs" mostra contexto injetado
- **Copilot (GitHub.com)**: PR no repo onde `.github/copilot-instructions.md` foi gerado — code review deve mencionar ADVPL/cp1252
- **Gemini CLI**: `gemini` → `/memory show` (lista GEMINI.md concatenado) + `/skills list` (lista plugadvpl-*)
- **Claude Code**: `/plugadvpl:arch <arq>` funciona via slash command + fragment do CLAUDE.md sempre injetado
```

- [ ] **Step 5: Verify pre-release**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov` → Expected: 1185+ passed.

Run: `cd cli && .venv/Scripts/python.exe -m ruff format --check plugadvpl\` and `ruff check plugadvpl\` (gap aprendido da v0.16.4).

- [ ] **Step 6: Commit release agregado**

```bash
cd /d/IA/Projetos/plugadvpl
git add -u
git commit -m "release: v0.16.5 — multi-agente improvements (8 gaps pós-research)

Bump 0.16.4 -> 0.16.5 (patch — adições compatíveis + 1 fix funcional CRÍTICO).

CRITICAL FIX:
- _transform_body style param (cursor=Bash backticks, plain=texto puro)
  resolve gap onde Copilot/Gemini interpretavam '\`Bash: uvx ...\`' como
  string literal (perdiam 50% do valor das 52 skills)

ADDED:
- plugadvpl doctor --check-agents: valida formato dos 5 agentes sem
  precisar instalar Cursor/Copilot/Gemini (nenhum tem CLI oficial)
- Cursor: 12 meta-skills com alwaysApply: true (init/ingest/status/etc.)
- Cursor: global marcado como (experimental) — docs nao confirma ~/.cursor/rules/
- Gemini: instala em .agents/skills/ tambem (cross-agent standard)
- Codex: .codex/config.toml minimo + flag --no-codex
- Auditadas 52 SKILL.md descriptions com keywords ADVPL/Protheus

CHANGED:
- README ganha secao 'Cobertura multi-agente' + smoke test guide
- CHANGELOG documenta cada gap

Tests: 30+ novos (3 transform_body + 4 cursor + 1 copilot + 2 gemini +
5 codex + 10 agent_doctor + 8 init integration + 1 multi-agent smoke).
Suite full: 1151 → ~1185 passed.

Updates:
- plugin.json / marketplace.json -> 0.16.5
- uvx plugadvpl@0.16.4 -> @0.16.5 nas 26 skills

Spec: docs/superpowers/specs/2026-05-30-multi-agent-v0165-improvements.md
Plan: docs/superpowers/plans/2026-05-30-multi-agent-v0165-implementation.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7: Tag + push**

```bash
git tag -a v0.16.5 -m "v0.16.5 — Multi-agente improvements (8 gaps pós-research)

CRITICAL FIX: _transform_body respeita formato por agente
(Cursor MDC Bash vs Copilot/Gemini plain text).

Added: doctor --check-agents, Cursor meta alwaysApply, Cursor
experimental warning, Gemini .agents/skills/, Codex .codex/config.toml,
descriptions audit keywords ADVPL/Protheus, README cobertura.

Suite full: 1185+ passed."

git push && git push --tags
```

- [ ] **Step 8: Monitor CI + verify release**

```bash
sleep 15 && gh run list --branch main --limit 2 --json status,name,databaseId,displayTitle
```

Watch CI run. Lessons learned v0.16.4: rodar `ruff check` antes (não só `ruff format --check`) pra pegar PLR0912.

```bash
gh run watch <ID> --interval 20 --exit-status
gh run list --workflow release.yml --limit 2  # Expected: release v0.16.5 success
gh release view v0.16.5 --json name,assets --jq '{name, assets: [.assets[].name]}'
curl -s https://pypi.org/pypi/plugadvpl/0.16.5/json -o /dev/null -w "PyPI %{http_code}\n"
```

Expected: PyPI 200, GitHub release v0.16.5 publicada com whl + tar.gz.

---

## Resumo execução

| Chunk | Tasks | Linhas |
|---|---|---|
| 1: `_transform_body` style param | 4 (Tasks 1-4) | ~200 |
| 2: Cursor meta + experimental | 2 (Tasks 5-6) | ~150 |
| 3: Gemini .agents/skills/ | 1 (Task 7) | ~100 |
| 4: Codex .codex/config.toml | 1 (Task 8) | ~300 |
| 5: doctor --check-agents | 1 (Task 9) | ~500 |
| 6: Descriptions audit | 1 (Task 10) | ~52 SKILL.md edits |
| 7: Release | 2 (Tasks 11-12) | ~200 |
| **Total** | **12 tasks** | **~1500** |

**Estimativa de tempo:** 4-7h focadas. Tasks 1-4 acopladas (transform_body fix afeta 3 módulos). Task 10 (audit) é a mais demorada manual.

**Critério final:**
- `gh release view v0.16.5` → ✅
- PyPI `plugadvpl 0.16.5` → ✅
- `plugadvpl doctor --check-agents` em projeto pós-init lista 5 agentes verdes
- Suite full: ~1185 passed em CI

---

## Notas pra quem executar

1. **Tasks 1-4 são acopladas** — Task 1 muda default de `_transform_body` pra `plain`; Tasks 2-4 fazem callers Cursor/Copilot/Gemini ficarem explícitos. Não commitar Task 1 sozinha sem fazer 2-4 logo (suite quebrada interim).

2. **Lint check pré-release** (lição v0.16.4): rodar `ruff check` (não só format) pra pegar PLR0912 antes do commit de release. CI lint scope inclui módulos novos `agent_doctor.py` e `codex_config.py`.

3. **Task 10 (audit)** é trabalho manual concentrado — talvez 30-60min de edits cuidadosos em ~20 SKILL.md. Não trivialize.

4. **Memórias projeto:**
   - `feedback_powershell_utf8_bom`: bumps via Python read_bytes/write_bytes
   - `reference_plugadvpl_release_gotchas`: git tag -a anotada; suite full pré-release
   - `feedback_readme_atualizar_em_releases`: README touch obrigatório
   - v0.16.4 PLR0912 lesson: rodar `ruff check` no pré-release

5. **Gemini dual install (Task 7)**: testar ambos `.gemini/skills/` E `.agents/skills/` populated quando ambos dirs existem.

6. **Cursor TestRenderSkillRule tests existentes** (Task 2): podem precisar ajuste se alguns assumiam comportamento default antigo. Geralmente OK porque cursor_rules agora passa `style="cursor"` explícito.
