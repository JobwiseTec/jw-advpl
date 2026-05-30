# Gemini CLI Skills no `plugadvpl init` — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `plugadvpl init` detecta Gemini CLI (via `~/.gemini/`, `gemini` no PATH, ou `.gemini/` no projeto) e gera `~/.gemini/GEMINI.md` (global home se sinal home), `<project>/GEMINI.md` (4º gêmeo) + 52 `.gemini/skills/plugadvpl-<X>/SKILL.md` (specifics).

**Architecture:** Novo módulo `cli/plugadvpl/gemini_skills.py` espelhando `copilot_instructions.py` (Fase 2). Reusa `_skill_catalog.py` (DRY com Cursor/Copilot). Apenas +1 constante (`GEMINI_MARKER_PREFIX`) em `_skill_catalog.py`. `init()` ganha flag `--no-gemini` + chamada após Copilot. `_check_fragment_staleness` ganha 4ª passada Gemini via helper paralelo.

**Tech Stack:** Python 3.11+ (stdlib only — `pathlib`, `shutil`, `re`, `dataclasses`, `enum`). Typer (existente). pytest + monkeypatch + `CliRunner`. Sem deps novas.

**Spec:** [`docs/superpowers/specs/2026-05-30-gemini-skills-design.md`](../specs/2026-05-30-gemini-skills-design.md)

---

## File Structure

**Arquivos novos:**
- `cli/plugadvpl/gemini_skills.py` (~220 linhas) — `GeminiTarget`, `detect_gemini`, `_GLOBAL_BODY_TEMPLATE`, `render_global_gemini_md`, `render_skill_for_gemini`, `InstallResult`, `install_gemini_skills`, helpers internos
- `cli/tests/unit/test_gemini_skills.py` (~300 linhas) — 17 unit tests

**Arquivos modificados:**
- `cli/plugadvpl/_skill_catalog.py` — +1 constante `GEMINI_MARKER_PREFIX`
- `cli/plugadvpl/cli.py` — `init()` ganha flag `--no-gemini` + chamada `install_gemini_skills`; novo helper `_check_gemini_staleness` chamado por `_check_fragment_staleness`
- `cli/tests/integration/test_cli.py` — classe nova `TestInitGeminiSkills` (8 tests) + 3 tests em `TestStatus`
- `.claude-plugin/plugin.json` + `marketplace.json` — bump 0.16.3 → 0.16.4
- `skills/*/SKILL.md` × 26 — bump `uvx plugadvpl@0.16.3` → `@0.16.4`
- `CHANGELOG.md` — entry [0.16.4]
- `README.md` — entry v0.16.4 + ajuste Quick start

---

## Chunk 1: Constant + detect_gemini

### Task 1: Adiciona `GEMINI_MARKER_PREFIX` + cria `gemini_skills.py` com `GeminiTarget` + `detect_gemini`

**Files:**
- Modify: `cli/plugadvpl/_skill_catalog.py` (add 1 constant)
- Create: `cli/plugadvpl/gemini_skills.py`
- Create: `cli/tests/unit/test_gemini_skills.py`

- [ ] **Step 1: Adiciona constante em `_skill_catalog.py`**

Find the block around `RULE_MARKER_PREFIX` and `INSTRUCTIONS_MARKER_PREFIX` in `_skill_catalog.py`. ADD a 3rd marker constant right below:

```python
RULE_MARKER_PREFIX = "<!-- plugadvpl-rule-version:"
INSTRUCTIONS_MARKER_PREFIX = "<!-- plugadvpl-instructions-version:"
GEMINI_MARKER_PREFIX = "<!-- plugadvpl-gemini-version:"
```

- [ ] **Step 2: Cria `cli/tests/unit/test_gemini_skills.py` com 6 RED tests de detection**

```python
"""Unit tests for plugadvpl/gemini_skills.py (v0.16.4+)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.gemini_skills import GeminiTarget, detect_gemini


class TestDetectGemini:
    def test_no_signals_returns_false_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem ~/.gemini/, sem gemini no PATH, sem .gemini/ no projeto → no-op."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_gemini(project)
        assert result == GeminiTarget(install_global=False, install_project=False)

    def test_home_gemini_dir_triggers_global_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`~/.gemini/` existe + sem .gemini/ projeto → só global=True (sinais INDEPENDENTES)."""
        fake_home = tmp_path / "home"
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_gemini(project)
        assert result.install_global is True
        assert result.install_project is False  # sinal global NÃO ativa project

    def test_project_gemini_dir_triggers_project_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.gemini/` no projeto + sem sinal home → só project=True."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".gemini").mkdir(parents=True)
        result = detect_gemini(project)
        assert result.install_global is False
        assert result.install_project is True

    def test_both_signals_returns_both_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = tmp_path / "home"
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".gemini").mkdir(parents=True)
        result = detect_gemini(project)
        assert result == GeminiTarget(install_global=True, install_project=True)

    def test_detect_gemini_in_path_triggers_global(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`shutil.which("gemini")` retorna path → install_global=True."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()  # sem .gemini/
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr(
            "plugadvpl.gemini_skills.shutil.which", lambda _: "/usr/local/bin/gemini"
        )
        project = tmp_path / "project"
        project.mkdir()
        result = detect_gemini(project)
        assert result.install_global is True
        assert result.install_project is False

    def test_handles_runtime_error_in_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Path.home() lança (container minimalista) → retorna (False, False)."""
        def boom() -> Path:
            raise RuntimeError("home unknown")
        monkeypatch.setattr(Path, "home", boom)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_gemini(project)
        assert result == GeminiTarget(install_global=False, install_project=False)
```

- [ ] **Step 3: Run RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_gemini_skills.py -v --no-cov`

Expected: `ModuleNotFoundError: No module named 'plugadvpl.gemini_skills'` em todos os 6 testes.

- [ ] **Step 4: Cria `cli/plugadvpl/gemini_skills.py` minimal (Task 1 só faz detect)**

```python
"""Google Gemini CLI native skills generator + installer (v0.16.4+).

Detecta Gemini instalado (~/.gemini/ no home OU 'gemini' no PATH OU .gemini/
no projeto) e gera:
- ~/.gemini/GEMINI.md (global home — só se ~/.gemini/ existe)
- <project>/GEMINI.md (4º gêmeo CLAUDE.md + AGENTS.md + GEMINI.md)
- <project>/.gemini/skills/plugadvpl-<X>/SKILL.md (52 specifics)

Sinais SÃO independentes — sinal global (~/.gemini/ ou gemini PATH) NÃO
ativa project install (consistente com Cursor policy).

Reusa _skill_catalog (DRY com cursor_rules + copilot_instructions).

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeminiTarget:
    """Decisão do detect_gemini: o que instalar."""

    install_global: bool   # ~/.gemini/GEMINI.md
    install_project: bool  # <project>/GEMINI.md + .gemini/skills/plugadvpl-*/SKILL.md


def detect_gemini(project_root: Path) -> GeminiTarget:
    """Decide o que instalar baseado em sinais conservadores e INDEPENDENTES.

    Global se ``~/.gemini/`` existe OU ``shutil.which("gemini")`` retorna path.
    Project se ``<project_root>/.gemini/`` existe.

    Conservador de propósito — sinal global NÃO ativa project install (evita
    pegada não-solicitada em projeto onde Gemini nunca foi usado especificamente).
    """
    install_global = False
    install_project = False

    try:
        home = Path.home()
        if (home / ".gemini").exists():
            install_global = True
    except RuntimeError:
        # Container minimalista sem home — tudo False.
        return GeminiTarget(install_global=False, install_project=False)

    if not install_global and shutil.which("gemini") is not None:
        install_global = True

    if (project_root / ".gemini").exists():
        install_project = True

    return GeminiTarget(install_global=install_global, install_project=install_project)
```

- [ ] **Step 5: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_gemini_skills.py -v --no-cov`

Expected: `6 passed`.

Full suite: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov` — Expected: 1129 passed (1123 + 6).

- [ ] **Step 6: Commit**

```bash
git add cli/plugadvpl/_skill_catalog.py cli/plugadvpl/gemini_skills.py cli/tests/unit/test_gemini_skills.py
git commit -m "feat(gemini): GeminiTarget + detect_gemini + GEMINI_MARKER_PREFIX (TDD red->green)

Modulo novo cli/plugadvpl/gemini_skills.py com:
- GeminiTarget dataclass (install_global + install_project)
- detect_gemini(project_root) — sinais INDEPENDENTES:
  - install_global=True se ~/.gemini/ existe OU 'gemini' no PATH
  - install_project=True SE .gemini/ no projeto (sinal global NAO ativa)

_skill_catalog.py ganha constante GEMINI_MARKER_PREFIX distinta dos 3
markers existentes (rule/instructions/fragment).

6 testes unit cobrindo combinacoes + RuntimeError em Path.home.

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md secao 3.1-3.2
Plan: docs/superpowers/plans/2026-05-30-gemini-skills-implementation.md Task 1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: Renderers (global MD + skill)

### Task 2: `render_global_gemini_md`

**Files:**
- Modify: `cli/plugadvpl/gemini_skills.py` (add template + render)
- Modify: `cli/tests/unit/test_gemini_skills.py` (add `TestRenderGlobalGeminiMd`)

- [ ] **Step 1: Add 3 RED tests at END of test_gemini_skills.py**

```python
class TestRenderGlobalGeminiMd:
    def test_includes_version_marker(self) -> None:
        from plugadvpl.gemini_skills import render_global_gemini_md
        result = render_global_gemini_md(version="0.16.4")
        assert "<!-- plugadvpl-gemini-version: 0.16.4 -->" in result

    def test_no_frontmatter(self) -> None:
        """GEMINI.md é markdown plano — sem frontmatter ---."""
        from plugadvpl.gemini_skills import render_global_gemini_md
        result = render_global_gemini_md(version="0.16.4")
        assert not result.startswith("---\n")

    def test_substitutes_version_in_body(self) -> None:
        from plugadvpl.gemini_skills import render_global_gemini_md
        result = render_global_gemini_md(version="0.16.4")
        assert "uvx plugadvpl@0.16.4" in result
        assert "__VERSION__" not in result
```

- [ ] **Step 2: Run RED** — Expected 3 failures (ImportError).

- [ ] **Step 3: Implement in `gemini_skills.py` — ADD at end**

```python
_GLOBAL_BODY_TEMPLATE = """# Convenções TOTVS Protheus (ADVPL/TLPP) + plugadvpl

Este repositório contém código TOTVS Protheus em **AdvPL** (`.prw`, `.prx`,
`.apw`) e **TLPP** (`.tlpp`). Se `.plugadvpl/index.db` existe no root, use
o índice via `uvx plugadvpl@__VERSION__ <subcomando>` ANTES de ler `.prw`/`.tlpp`
cru — economiza ~16x tokens.

## Tabela de decisão — qual comando rodar antes de Read

| Pergunta | Comando |
|---|---|
| "explique o fonte X" / "o que faz Y" | `uvx plugadvpl@__VERSION__ arch <arq>` |
| "onde está a função X?" | `uvx plugadvpl@__VERSION__ find <nome>` |
| "quem chama X?" | `uvx plugadvpl@__VERSION__ callers <funcao>` |
| "o que X chama?" | `uvx plugadvpl@__VERSION__ callees <funcao>` |
| "quem mexe na tabela SA1?" | `uvx plugadvpl@__VERSION__ tables SA1` |
| "onde MV_LOCALIZA é usado?" | `uvx plugadvpl@__VERSION__ param MV_LOCALIZA` |
| "achar 'RecLock' nos fontes" | `uvx plugadvpl@__VERSION__ grep RecLock` |
| "tem problemas no fonte X?" | `uvx plugadvpl@__VERSION__ lint <arq>` |

## Encoding — CRÍTICO

- `.prw`/`.prx` são **cp1252**. Read/Write/Edit comuns são UTF-8 — bytes acentuados viram `�`.
- Antes de editar `.prw`: `uvx plugadvpl@__VERSION__ edit-prw stage <arq>` (converte pra UTF-8 com backup).
- Depois de editar: `uvx plugadvpl@__VERSION__ edit-prw commit <arq>` (volta pra cp1252).
- `.tlpp` é UTF-8 nativo — sem stage/commit.

## Workflow padrão pra "explique o programa X"

1. `uvx plugadvpl@__VERSION__ find X` — descobre arquivo
2. `uvx plugadvpl@__VERSION__ arch <arq>` — visão arquitetural
3. `uvx plugadvpl@__VERSION__ callees X` — o que X chama
4. `uvx plugadvpl@__VERSION__ callers X` — quem chama X
5. Só depois, se necessário, leia o arquivo com offset/limit do `arch`

## Skills locais

Este projeto tem `.gemini/skills/plugadvpl-*/SKILL.md` com instruções
específicas por subcomando. Use `/memory show` pra ver todas carregadas.
"""


def render_global_gemini_md(version: str) -> str:
    """Gera conteúdo de GEMINI.md (global home ou projeto root).

    Markdown plano com marker plugadvpl-gemini-version no topo. ~80 linhas
    no body — Gemini concatena GEMINI.md hierarquicamente, então enxuto.
    """
    markers = f"<!-- plugadvpl-gemini-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return markers + body
```

- [ ] **Step 4: Run GREEN** — Expected `3 passed` em TestRenderGlobalGeminiMd. Full suite: 1132 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/gemini_skills.py cli/tests/unit/test_gemini_skills.py
git commit -m "feat(gemini): render_global_gemini_md (markdown plano com marker)

Conteudo adaptado do Copilot _GLOBAL_BODY_TEMPLATE. Mesmo padrao:
markdown plano, sem frontmatter, marker plugadvpl-gemini-version no topo.
Body ~80 linhas (Gemini concatena GEMINI.md hierarquicamente — enxuto).

3 testes unit (marker, sem frontmatter, version substituida).

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md secao 3.3
Plan: docs/superpowers/plans/2026-05-30-gemini-skills-implementation.md Task 2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `render_skill_for_gemini`

**Files:**
- Modify: `cli/plugadvpl/gemini_skills.py`
- Modify: `cli/tests/unit/test_gemini_skills.py`

- [ ] **Step 1: Add 6 RED tests at END of test_gemini_skills.py**

```python
class TestRenderSkillForGemini:
    def test_includes_name_field(self, tmp_path: Path) -> None:
        """Frontmatter Gemini tem `name: plugadvpl-<X>` (skill_name com prefixo)."""
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "name: plugadvpl-arch" in result

    def test_includes_description_from_skill(self, tmp_path: Path) -> None:
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: Visao arquitetural\n---\nBody\n", encoding="utf-8"
        )
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "description: Visao arquitetural" in result

    def test_no_apply_to_field(self, tmp_path: Path) -> None:
        """Gemini não tem applyTo — confirmar AUSÊNCIA (vs Copilot)."""
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "applyTo:" not in result

    def test_includes_version_and_skill_markers(self, tmp_path: Path) -> None:
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "callers"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "<!-- plugadvpl-gemini-version: 0.16.4 -->" in result
        assert "<!-- plugadvpl-skill: callers -->" in result

    def test_falls_back_when_no_frontmatter(self, tmp_path: Path) -> None:
        """SKILL.md sem frontmatter → description fallback `plugadvpl skill: <name>`."""
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "grep"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("# Body only, no frontmatter\n", encoding="utf-8")
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "description: plugadvpl skill: grep" in result

    def test_transforms_body_substitutions(self, tmp_path: Path) -> None:
        """Body passa pelas mesmas substituições do Cursor/Copilot."""
        from plugadvpl.gemini_skills import render_skill_for_gemini
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\n"
            "Use `/plugadvpl:arch` antes de Read.\n",
            encoding="utf-8",
        )
        result = render_skill_for_gemini(target, version="0.16.4")
        assert "`Bash: uvx plugadvpl@0.16.4 arch`" in result
        assert "/plugadvpl:arch" not in result
```

- [ ] **Step 2: Run RED** — Expected 6 failures (ImportError).

- [ ] **Step 3: Implement — ADD imports + function in gemini_skills.py**

ADD at top imports block:

```python
from plugadvpl._skill_catalog import _parse_skill_md, _transform_body
```

ADD function at end of module (após `render_global_gemini_md`):

```python
def render_skill_for_gemini(skill_md_path: Path, version: str) -> str:
    """Gera `.gemini/skills/plugadvpl-<X>/SKILL.md`.

    Frontmatter Gemini é mais simples que Cursor/Copilot: só `name` +
    `description`. Sem `applyTo`/`globs`/`alwaysApply` (Gemini usa JIT
    scan + skill activation por descrição).

    Pipeline:
    1. Parse SKILL.md original (extrai description)
    2. _transform_body (slash→uvx + normalize)
    3. Frontmatter Gemini: name=plugadvpl-<X>, description=<da SKILL.md>
    4. Markers gemini-version + skill

    Edge case: SKILL.md sem frontmatter → description fallback usa skill_name.
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    frontmatter = (
        "---\n"
        f"name: plugadvpl-{skill_name}\n"
        f"description: {description}\n"
        "---\n"
    )
    markers = (
        f"<!-- plugadvpl-gemini-version: {version} -->\n"
        f"<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )
    return frontmatter + markers + _transform_body(body, version)
```

- [ ] **Step 4: Run GREEN** — Expected `6 passed`. Suite: 1138 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/gemini_skills.py cli/tests/unit/test_gemini_skills.py
git commit -m "feat(gemini): render_skill_for_gemini (frontmatter name+description)

Frontmatter Gemini mais simples que Cursor/Copilot:
- name: plugadvpl-<X> (Gemini espera nome unico)
- description: <da SKILL.md original>
- SEM applyTo/globs/alwaysApply (Gemini nao tem esses conceitos)

Body transformations identicas (_transform_body do _skill_catalog).
Markers gemini-version + skill.

6 testes unit cobrindo name, description, ausencia applyTo, markers,
fallback, body substituicoes.

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md secao 3.4
Plan: docs/superpowers/plans/2026-05-30-gemini-skills-implementation.md Task 3

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: install_gemini_skills orquestrador

### Task 4: `InstallResult` + `install_gemini_skills` (com 3 helpers internos)

**Files:**
- Modify: `cli/plugadvpl/gemini_skills.py`
- Modify: `cli/tests/unit/test_gemini_skills.py`

- [ ] **Step 1: Add 2 RED tests**

```python
class TestInstallGeminiSkills:
    def test_installs_all_three_layers_when_signals_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """~/.gemini/ + .gemini/ projeto → home + project MD + 52 skills."""
        from plugadvpl.gemini_skills import install_gemini_skills
        fake_home = tmp_path / "home"
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".gemini").mkdir(parents=True)

        result = install_gemini_skills(project, version="0.16.4")

        assert result.installed_global_home is True
        assert result.installed_project_md is True
        assert result.installed_skills_count == 52
        assert not result.errors
        # Files exist
        assert (fake_home / ".gemini" / "GEMINI.md").exists()
        assert (project / "GEMINI.md").exists()
        skill_files = list(
            (project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md")
        )
        assert len(skill_files) == 52

    def test_no_op_without_signals(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from plugadvpl.gemini_skills import install_gemini_skills
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = install_gemini_skills(project, version="0.16.4")
        assert result.installed_global_home is False
        assert result.installed_project_md is False
        assert result.installed_skills_count == 0
        assert not (fake_home / ".gemini" / "GEMINI.md").exists()
        assert not (project / "GEMINI.md").exists()
        assert not (project / ".gemini").exists()
```

- [ ] **Step 2: Run RED** — Expected 2 failures.

- [ ] **Step 3: Implement — ADD imports + `InstallResult` + orquestrador + 3 helpers**

ADD to imports block:

```python
from dataclasses import dataclass, field

from plugadvpl._skill_catalog import (
    GEMINI_MARKER_PREFIX,
    WriteOutcome,
    _SKILL_GLOBS,
    _skills_root,
    _write_managed_file,
)
```

(Consolidate with existing imports — already has `_parse_skill_md, _transform_body` from Task 3.)

ADD at end of module:

```python
@dataclass(frozen=True)
class InstallResult:
    """Resumo do install_gemini_skills."""

    installed_global_home: bool                                    # ~/.gemini/GEMINI.md
    installed_project_md: bool                                     # <project>/GEMINI.md
    installed_skills_count: int                                    # 0..52
    skipped_due_to_user_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.installed_global_home:
            parts.append("1 home")
        if self.installed_project_md:
            parts.append("1 projeto")
        if self.installed_skills_count:
            parts.append(f"{self.installed_skills_count} skills")
        return (" + ".join(parts) + " instaladas") if parts else "nada instalado"


def _install_gemini_global_home(version: str) -> tuple[bool, list[str], list[str]]:
    """Helper: install ~/.gemini/GEMINI.md.

    Returns (installed_bool, skipped_list, errors_list).
    """
    skipped: list[str] = []
    errors: list[str] = []
    try:
        global_path = Path.home() / ".gemini" / "GEMINI.md"
        outcome = _write_managed_file(
            global_path,
            render_global_gemini_md(version),
            GEMINI_MARKER_PREFIX,
        )
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return (True, skipped, errors)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append("~/.gemini/GEMINI.md (home)")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {global_path}: permission/IO denied")
        return (False, skipped, errors)
    except Exception as e:  # noqa: BLE001 — defensivo total
        errors.append(f"global home erro: {e!r}")
        return (False, skipped, errors)


def _install_gemini_project_md(
    project_root: Path, version: str
) -> tuple[bool, list[str], list[str]]:
    """Helper: install <project>/GEMINI.md (4º gêmeo)."""
    skipped: list[str] = []
    errors: list[str] = []
    try:
        target = project_root / "GEMINI.md"
        outcome = _write_managed_file(
            target,
            render_global_gemini_md(version),
            GEMINI_MARKER_PREFIX,
        )
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return (True, skipped, errors)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append("GEMINI.md (projeto)")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {target}: permission/IO denied")
        return (False, skipped, errors)
    except Exception as e:  # noqa: BLE001
        errors.append(f"project MD erro: {e!r}")
        return (False, skipped, errors)


def _install_one_gemini_skill(
    skill_name: str,
    skills_root: Path,
    target_dir: Path,
    version: str,
) -> tuple[bool, list[str], list[str]]:
    """Helper: install <project>/.gemini/skills/plugadvpl-<X>/SKILL.md.

    Note: cria directory por skill (Gemini espera diretório, não arquivo flat).
    """
    skipped: list[str] = []
    errors: list[str] = []
    try:
        skill_md_path = skills_root / skill_name / "SKILL.md"
        if not skill_md_path.exists():
            errors.append(f"skill {skill_name}: SKILL.md ausente")
            return (False, skipped, errors)
        content = render_skill_for_gemini(skill_md_path, version)
        target_path = target_dir / f"plugadvpl-{skill_name}" / "SKILL.md"
        outcome = _write_managed_file(target_path, content, GEMINI_MARKER_PREFIX)
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return (True, skipped, errors)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append(f"plugadvpl-{skill_name}/SKILL.md")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {target_path}: permission/IO denied")
        return (False, skipped, errors)
    except Exception as e:  # noqa: BLE001
        errors.append(f"skill {skill_name}: {e!r}")
        return (False, skipped, errors)


def install_gemini_skills(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write pras GEMINI.md + skills Gemini.

    Spec §3.5 da Fase 3. NUNCA propaga exception — try/except em cada bloco
    + helpers (_install_gemini_global_home, _install_gemini_project_md,
    _install_one_gemini_skill) pra manter PLR0912 ≤12.
    """
    skipped: list[str] = []
    errors: list[str] = []
    installed_global_home = False
    installed_project_md = False
    installed_skills_count = 0

    try:
        target = detect_gemini(project_root)
    except Exception as e:  # noqa: BLE001
        errors.append(f"detect_gemini falhou: {e!r}")
        return InstallResult(False, False, 0, [], errors)

    if target.install_global:
        ok, skp, err = _install_gemini_global_home(version)
        installed_global_home = ok
        skipped.extend(skp)
        errors.extend(err)

    if target.install_project:
        ok, skp, err = _install_gemini_project_md(project_root, version)
        installed_project_md = ok
        skipped.extend(skp)
        errors.extend(err)

        # Install skills locais
        skills_target_dir = project_root / ".gemini" / "skills"
        try:
            skills_root = _skills_root()
        except Exception as e:  # noqa: BLE001
            errors.append(f"_skills_root falhou: {e!r}")
            return InstallResult(
                installed_global_home,
                installed_project_md,
                installed_skills_count,
                skipped,
                errors,
            )

        for skill_name in _SKILL_GLOBS:  # iter keys
            ok, skp, err = _install_one_gemini_skill(
                skill_name, skills_root, skills_target_dir, version
            )
            if ok:
                installed_skills_count += 1
            skipped.extend(skp)
            errors.extend(err)

    return InstallResult(
        installed_global_home=installed_global_home,
        installed_project_md=installed_project_md,
        installed_skills_count=installed_skills_count,
        skipped_due_to_user_files=skipped,
        errors=errors,
    )
```

- [ ] **Step 4: Run GREEN** — Expected `2 passed`. Full suite: 1140 passed.

If test `test_installs_all_three_layers_when_signals_present` fails with `installed_skills_count == 0`, the issue is `_skills_root()` not resolving in dev tree — same gotcha as Cursor/Copilot. Should be handled by `_skills_root()` itself (which falls back to dev tree resolution).

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/gemini_skills.py cli/tests/unit/test_gemini_skills.py
git commit -m "feat(gemini): install_gemini_skills + InstallResult orquestrador

Detecta + renderiza + escreve home + project MD + 52 skills.
NUNCA propaga exception — try/except em cada bloco.
Usa GEMINI_MARKER_PREFIX (distinto de rule/instructions/fragment).

3 helpers internos pra manter complexidade:
- _install_gemini_global_home (~/.gemini/GEMINI.md)
- _install_gemini_project_md (<project>/GEMINI.md, 4o gemeo)
- _install_one_gemini_skill (.gemini/skills/plugadvpl-<X>/SKILL.md)

Gemini espera directory-per-skill (nao file flat).

2 testes integrados (smoke + no-op).

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md secao 3.5
Plan: docs/superpowers/plans/2026-05-30-gemini-skills-implementation.md Task 4

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 4: Init integration + staleness

### Task 5: Flag `--no-gemini` + chamada no `init`

**Files:**
- Modify: `cli/plugadvpl/cli.py`
- Modify: `cli/tests/integration/test_cli.py` (NEW class `TestInitGeminiSkills`)

- [ ] **Step 1: Add 5 RED tests in test_cli.py**

IMMEDIATELY before `class TestIngest:` (after existing TestInitCopilotInstructions), ADD:

```python
class TestInitGeminiSkills:
    """v0.16.4 — init detecta Gemini e gera GEMINI.md + skills."""

    def test_skips_gemini_when_no_signals(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem ~/.gemini/, sem gemini PATH, sem .gemini/ projeto → no-op."""
        fake_home = synthetic_project.parent / "fake_home_gemini"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert not (synthetic_project / "GEMINI.md").exists()
        assert not (synthetic_project / ".gemini").exists()
        assert "Gemini skills" not in result.stdout

    def test_installs_when_project_has_gemini_dir(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.gemini/` no projeto → project MD + 52 skills."""
        fake_home = synthetic_project.parent / "fake_home_gemini2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        (synthetic_project / ".gemini").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert (synthetic_project / "GEMINI.md").exists()
        skill_files = list(
            (synthetic_project / ".gemini" / "skills").glob(
                "plugadvpl-*/SKILL.md"
            )
        )
        assert len(skill_files) == 52
        assert "Gemini skills" in result.stdout

    def test_installs_global_home_when_home_has_gemini(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`~/.gemini/` mockado → ~/.gemini/GEMINI.md criado."""
        fake_home = synthetic_project.parent / "fake_home_gemini3"
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        # Sem .gemini/ no projeto — só global trigger
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert (fake_home / ".gemini" / "GEMINI.md").exists()
        # Project NÃO recebe nada (sinais independentes)
        assert not (synthetic_project / "GEMINI.md").exists()

    def test_no_gemini_flag_skips_everything(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_gemini4"
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        (synthetic_project / ".gemini").mkdir()
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "init", "--no-gemini"]
        )
        assert result.exit_code == 0
        assert not (synthetic_project / "GEMINI.md").exists()
        assert not (fake_home / ".gemini" / "GEMINI.md").exists()
        assert "Gemini skills" not in result.stdout

    def test_quiet_suppresses_message(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_gemini5"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        (synthetic_project / ".gemini").mkdir()
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "--quiet", "init"]
        )
        assert result.exit_code == 0
        assert "Gemini skills" not in result.stdout
        # Skills criadas mesmo em quiet
        skill_files = list(
            (synthetic_project / ".gemini" / "skills").glob(
                "plugadvpl-*/SKILL.md"
            )
        )
        assert len(skill_files) == 52
```

Note: `monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)` é adicionado em CADA teste pra cobrir o caso de Gemini estar no PATH do dev. O fixture autouse `_isolate_cursor_home` na classe `TestInit` (de v0.16.2) NÃO cobre gemini_skills — Tests novos de Gemini precisam mockar explicitamente.

- [ ] **Step 2: Run RED** — Expected 5 failures (--no-gemini missing OR install_gemini_skills not called).

- [ ] **Step 3a: Extend `TestInit` autouse fixture pra cobrir `gemini_skills.shutil.which`**

Find `class TestInit:` in `cli/tests/integration/test_cli.py`. The autouse fixture `_isolate_cursor_home` (added in v0.16.2 release fix, extended in v0.16.3 if needed) mocks `Path.home` + `cursor_rules.shutil.which`. Pra v0.16.4, **proativamente** estender pra também mockar `gemini_skills.shutil.which` — evita pegada no PATH real do dev se ele tem `gemini` instalado.

Find the existing fixture and ADD a third `monkeypatch.setattr` line:

```python
@pytest.fixture(autouse=True)
def _isolate_cursor_home(
    self, tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Isola Path.home pra cada teste do TestInit (v0.16.2+; v0.16.4 add gemini)."""
    fake_home = tmp_path_factory.mktemp("isolated_home_init")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(
        "plugadvpl.cursor_rules.shutil.which", lambda _: None
    )
    monkeypatch.setattr(
        "plugadvpl.gemini_skills.shutil.which", lambda _: None
    )
```

Run TestInit existing tests pra confirmar não quebrou:

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestInit -v --no-cov`

Expected: 6 passed.

- [ ] **Step 3b: Modify `init` in `cli/plugadvpl/cli.py`**

Find existing signature with `no_cursor` and `no_copilot`. ADD `no_gemini`:

```python
@app.command()
def init(
    ctx: typer.Context,
    no_cursor: Annotated[
        bool,
        typer.Option(
            "--no-cursor",
            help="Não instala Cursor rules mesmo se Cursor for detectado.",
        ),
    ] = False,
    no_copilot: Annotated[
        bool,
        typer.Option(
            "--no-copilot",
            help="Não instala Copilot instructions mesmo se `.github/` for detectado.",
        ),
    ] = False,
    no_gemini: Annotated[
        bool,
        typer.Option(
            "--no-gemini",
            help="Não instala Gemini skills mesmo se Gemini for detectado (~/.gemini/, gemini no PATH, ou .gemini/ no projeto).",
        ),
    ] = False,
) -> None:
```

Update docstring:

```python
    """Cria ``./.plugadvpl/index.db``, escreve fragments em ``CLAUDE.md`` + ``AGENTS.md``, atualiza ``.gitignore``, e (se detectado) gera Cursor rules + Copilot instructions + Gemini skills.

    v0.16.1: CLAUDE.md + AGENTS.md fragments.
    v0.16.2: Cursor rules nativos em `.cursor/rules/`.
    v0.16.3: Copilot instructions em `.github/copilot-instructions.md` +
    `.github/instructions/`.
    v0.16.4: Gemini skills em `~/.gemini/GEMINI.md` + `<project>/GEMINI.md`
    + `.gemini/skills/plugadvpl-*/SKILL.md` quando Gemini detectado.
    Use `--no-gemini` pra desabilitar.
    """
```

AFTER `if not no_copilot:` block, ADD:

```python
    if not no_gemini:
        from plugadvpl.gemini_skills import install_gemini_skills
        gemini_result = install_gemini_skills(root, __version__)
        if not ctx.obj["quiet"]:
            if (
                gemini_result.installed_global_home
                or gemini_result.installed_project_md
                or gemini_result.installed_skills_count
            ):
                typer.echo(f"OK  Gemini skills: {gemini_result.summary()}")
            for warn in gemini_result.errors:
                typer.secho(
                    f"⚠  Gemini skills: {warn}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            for skipped in gemini_result.skipped_due_to_user_files:
                typer.secho(
                    f"⚠  Gemini skills: {skipped} já existe sem marker plugadvpl — não sobrescrevi",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
```

- [ ] **Step 4: Run GREEN** — Expected 5 passed (TestInitGeminiSkills) + 6 passed (TestInit, autouse fixture estendido em Step 3a). Full suite: 1145 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cli.py cli/tests/integration/test_cli.py
git commit -m "feat(gemini): init grava Gemini skills quando detectado + flag --no-gemini

init() ganha 1 flag (--no-gemini) + 1 chamada install_gemini_skills
apos install_copilot_instructions. Mensagens 'OK Gemini skills: ...'
seguem o padrao Cursor/Copilot; warnings YELLOW em stderr.

Deteccao: sinais INDEPENDENTES — ~/.gemini/ ou gemini PATH ativa global;
.gemini/ no projeto ativa project (sinal global NAO ativa project).

5 testes integration em TestInitGeminiSkills + fixture autouse de
TestInit extendida pra mockar gemini_skills.shutil.which (evita pegada
no PATH real do dev).

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md secao 3.6
Plan: docs/superpowers/plans/2026-05-30-gemini-skills-implementation.md Task 5

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Idempotência + preservação user files (tests only)

**Files:**
- Modify: `cli/tests/integration/test_cli.py` (add 3 tests to `TestInitGeminiSkills`)

- [ ] **Step 1: Add 3 tests at end of TestInitGeminiSkills**

```python
    def test_idempotent_does_not_duplicate(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_gemini6"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        (synthetic_project / ".gemini").mkdir()
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        skill_files = list(
            (synthetic_project / ".gemini" / "skills").glob(
                "plugadvpl-*/SKILL.md"
            )
        )
        assert len(skill_files) == 52
        arch_content = (
            synthetic_project
            / ".gemini" / "skills" / "plugadvpl-arch" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert arch_content.count("<!-- plugadvpl-gemini-version:") == 1

    def test_overwrites_with_old_marker(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from plugadvpl import __version__
        fake_home = synthetic_project.parent / "fake_home_gemini7"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        skills_dir = synthetic_project / ".gemini" / "skills" / "plugadvpl-arch"
        skills_dir.mkdir(parents=True)
        stale = skills_dir / "SKILL.md"
        stale.write_text(
            "stale <!-- plugadvpl-gemini-version: 0.15.0 -->",
            encoding="utf-8",
        )
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        new_content = stale.read_text(encoding="utf-8")
        assert "stale" not in new_content
        assert f"<!-- plugadvpl-gemini-version: {__version__} -->" in new_content

    def test_preserves_user_file_without_marker(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_gemini8"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        skills_dir = synthetic_project / ".gemini" / "skills" / "plugadvpl-arch"
        skills_dir.mkdir(parents=True)
        user_file = skills_dir / "SKILL.md"
        user_file.write_text("my own skill, no marker", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        # Preserva
        assert user_file.read_text(encoding="utf-8") == "my own skill, no marker"
        # Warning
        assert "plugadvpl-arch/SKILL.md" in (result.stderr or "")
        assert "sem marker plugadvpl" in (result.stderr or "")
```

- [ ] **Step 2: Run + Commit**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestInitGeminiSkills -v --no-cov`

Expected: 8 passed (5 + 3).

Full suite: 1148 passed.

```bash
git add cli/tests/integration/test_cli.py
git commit -m "test(gemini): idempotencia + preservacao de user files no init

3 testes adicionais em TestInitGeminiSkills:
- idempotente (2 inits → 52 skills + marker count == 1)
- sobrescreve com marker antigo (0.15.0 → versao atual)
- preserva user file sem marker + warning

8/8 verdes (5 + 3).

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md secao 5
Plan: docs/superpowers/plans/2026-05-30-gemini-skills-implementation.md Task 6

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Staleness Gemini em `_check_fragment_staleness` (helper + 3 tests)

**Files:**
- Modify: `cli/plugadvpl/cli.py` (add `_check_gemini_staleness` helper + chain in `_check_fragment_staleness`)
- Modify: `cli/tests/integration/test_cli.py` (3 tests em `TestStatus`)

- [ ] **Step 1: Add 3 RED tests in `TestStatus`**

```python
    def test_detects_stale_gemini_home(
        self, indexed_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`~/.gemini/GEMINI.md` com marker old → status reporta."""
        fake_home = indexed_project.parent / "fake_home_gemini_status1"
        gemini_dir = fake_home / ".gemini"
        gemini_dir.mkdir(parents=True)
        (gemini_dir / "GEMINI.md").write_text(
            "stale <!-- plugadvpl-gemini-version: 0.15.0 -->",
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        result = runner.invoke(
            app, ["--root", str(indexed_project), "status"]
        )
        combined = (result.stderr or "") + result.stdout
        assert "GEMINI.md" in combined
        assert "0.15.0" in combined

    def test_detects_stale_gemini_project(
        self, indexed_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`<project>/GEMINI.md` com marker old → status reporta."""
        fake_home = indexed_project.parent / "fake_home_gemini_status2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        (indexed_project / "GEMINI.md").write_text(
            "stale <!-- plugadvpl-gemini-version: 0.15.0 -->",
            encoding="utf-8",
        )
        result = runner.invoke(
            app, ["--root", str(indexed_project), "status"]
        )
        combined = (result.stderr or "") + result.stdout
        assert "GEMINI.md" in combined
        assert "0.15.0" in combined

    def test_detects_stale_gemini_skill(
        self, indexed_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`<project>/.gemini/skills/plugadvpl-arch/SKILL.md` stale → status reporta."""
        fake_home = indexed_project.parent / "fake_home_gemini_status3"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        skills_dir = indexed_project / ".gemini" / "skills" / "plugadvpl-arch"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "stale <!-- plugadvpl-gemini-version: 0.15.0 -->",
            encoding="utf-8",
        )
        result = runner.invoke(
            app, ["--root", str(indexed_project), "status"]
        )
        combined = (result.stderr or "") + result.stdout
        assert "SKILL.md" in combined
        assert "0.15.0" in combined
```

- [ ] **Step 2: Run RED** — Expected 3 failures.

- [ ] **Step 3: Extend `_check_fragment_staleness` in cli.py**

Find existing `_check_fragment_staleness` function. Existing structure:
- `_check_fragment_staleness` (main) calls `_check_cursor_rules_staleness` + `_check_copilot_instructions_staleness`

ADD a parallel helper `_check_gemini_staleness(root)` and chain in main:

```python
def _check_gemini_staleness(root: Path) -> str | None:
    """Detecta Gemini files desatualizados.

    Cobre `~/.gemini/GEMINI.md` (global), `<project>/GEMINI.md` (projeto),
    e `<project>/.gemini/skills/plugadvpl-*/SKILL.md` (specifics).
    Retorna mensagem do primeiro arquivo desatualizado, ou None.

    Marker é `<!-- plugadvpl-gemini-version: X.Y.Z -->` — distinto do
    Cursor `rule-version`, Copilot `instructions-version`, e
    fragment-version do CLAUDE.md/AGENTS.md. Evita falso-positivo cross-agent.
    """
    gemini_files: list[Path] = []
    try:
        home_global = Path.home() / ".gemini" / "GEMINI.md"
        if home_global.exists():
            gemini_files.append(home_global)
    except RuntimeError:
        pass
    project_md = root / "GEMINI.md"
    if project_md.exists():
        gemini_files.append(project_md)
    skills_dir = root / ".gemini" / "skills"
    if skills_dir.exists():
        # Glob recursivo: .gemini/skills/plugadvpl-<X>/SKILL.md
        gemini_files.extend(sorted(skills_dir.glob("plugadvpl-*/SKILL.md")))

    marker_re = re.compile(
        r"<!--\s*plugadvpl-gemini-version:\s*(\d+\.\d+\.\d+[\w.+-]*)\s*-->"
    )
    for gf in gemini_files:
        try:
            content = gf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = marker_re.search(content)
        if m is None:
            continue
        v = m.group(1)
        if v != __version__:
            return f"{gf.name} foi gerado por plugadvpl {v}"
    return None
```

Then in `_check_fragment_staleness`, find where it currently calls `_check_copilot_instructions_staleness` and chain `_check_gemini_staleness` AFTER it (before `return None`):

```python
    # 4. Gemini skills (gemini-version)
    gemini_msg = _check_gemini_staleness(root)
    if gemini_msg is not None:
        return gemini_msg

    return None
```

- [ ] **Step 4: Run GREEN** — Expected 3 passed.

Full suite: 1151 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cli.py cli/tests/integration/test_cli.py
git commit -m "feat(status): detecta Gemini files desatualizados (home + projeto + skills)

Helper novo _check_gemini_staleness cobre 4a passada:
- ~/.gemini/GEMINI.md (global home)
- <project>/GEMINI.md (4o gemeo no projeto)
- <project>/.gemini/skills/plugadvpl-*/SKILL.md (specifics, glob recursivo)

Reporta primeiro arquivo desatualizado. Marker plugadvpl-gemini-version
distinto dos outros 3 (rule/instructions/fragment).

_check_fragment_staleness delega ao helper (mantem PLR0912 ≤12 mesmo
com 4a passada adicionada).

3 testes integration TestStatus.

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md secao 3.7
Plan: docs/superpowers/plans/2026-05-30-gemini-skills-implementation.md Task 7

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 5: Release v0.16.4

### Task 8: Bump version + skills

**Files:**
- Modify: `.claude-plugin/plugin.json` (0.16.3 → 0.16.4)
- Modify: `.claude-plugin/marketplace.json` (0.16.3 → 0.16.4)
- Modify: `skills/*/SKILL.md` × ~26 (bumps via Python script)

- [ ] **Step 1: Bump manifests**

Edit `.claude-plugin/plugin.json`: `"version": "0.16.3"` → `"version": "0.16.4"`.
Edit `.claude-plugin/marketplace.json`: `"version": "0.16.3"` → `"version": "0.16.4"`.

- [ ] **Step 2: Bump skills via Python script**

Create `d:\tmp\bump_skills_v0164.py`:

```python
from pathlib import Path
OLD = "plugadvpl@0.16.3"; NEW = "plugadvpl@0.16.4"
skills_root = Path("d:/IA/Projetos/plugadvpl/skills")
n = 0
for p in skills_root.rglob("SKILL.md"):
    raw = p.read_bytes()
    if OLD.encode() in raw:
        p.write_bytes(raw.replace(OLD.encode(), NEW.encode()))
        n += 1
print(f"{n} skill(s) bumped")
```

Run: `& "C:\Users\jonil\AppData\Local\Programs\Python\Python312\python.exe" d:\tmp\bump_skills_v0164.py`

Expected: `26 skill(s) bumped`.

- [ ] **Step 3: Verify pre-flight**

Suite: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov` → 1151 passed.

Ruff format check: `& .venv\Scripts\python.exe -m ruff format --check plugadvpl\cli.py plugadvpl\cursor_rules.py plugadvpl\copilot_instructions.py plugadvpl\_skill_catalog.py plugadvpl\gemini_skills.py`

If reclamation: `& .venv\Scripts\python.exe -m ruff format plugadvpl\<files>`.

- [ ] **Step 4: NÃO commitar — agregado na Task 10**

---

### Task 9: CHANGELOG + README

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: CHANGELOG entry**

Em `CHANGELOG.md`, após `## [Unreleased]`, INSERT:

```markdown
## [0.16.4] - 2026-05-30

### Added — Gemini CLI native skills no `plugadvpl init` (Fase 3 multi-agente)

`plugadvpl init` agora detecta Gemini CLI (via `~/.gemini/`, `gemini` no PATH, ou `.gemini/` no projeto) e gera:

- **`~/.gemini/GEMINI.md`** (global home) — convenções ADVPL/TLPP machine-wide quando `~/.gemini/` existe ou `gemini` está no PATH.
- **`<project>/GEMINI.md`** (4º gêmeo, junto com CLAUDE.md + AGENTS.md já existentes) — necessário porque Gemini CLI não lê AGENTS.md por padrão.
- **52 arquivos** em `.gemini/skills/plugadvpl-<skill>/SKILL.md` — uma por skill com frontmatter Gemini (`name: plugadvpl-<X>` + `description`). Frontmatter mais simples que Cursor/Copilot — Gemini usa JIT scan + activation por descrição.

Detection conservadora com **sinais INDEPENDENTES**: sinal global (`~/.gemini/` ou `gemini` PATH) ativa apenas global home; sinal de project (`.gemini/` no projeto) ativa apenas project. Consistente com Cursor policy — evita pegada não-solicitada.

Single source: as 52 SKILL.md específicas são geradas em runtime a partir das `skills/<X>/SKILL.md` embarcadas no wheel (mesma fonte que Claude Code, Cursor e Copilot consomem). Substituições idênticas (`/plugadvpl:<X>` → `` `Bash: uvx plugadvpl@0.16.4 <X>` ``).

Marker `<!-- plugadvpl-gemini-version: X.Y.Z -->` controla idempotência. **Distinto dos 3 markers existentes** (`plugadvpl-rule-version`, `plugadvpl-instructions-version`, `plugadvpl-fragment-version`) — evita falso-positivo cross-agent. `plugadvpl status` detecta GEMINI.md ou skill desatualizadas.

**Flag:** `plugadvpl init --no-gemini` desabilita mesmo com sinais presentes.

**Garantia:** falha de I/O em Gemini nunca quebra `init` — mesmo NEVER-propagate das Fases 1/2.

**Estrutura de skill por diretório:** Gemini espera `<skills_dir>/<name>/SKILL.md` (não arquivo flat). O orquestrador cria `.gemini/skills/plugadvpl-<X>/` antes de escrever SKILL.md.

Predecessor: v0.16.3 entregou Copilot Instructions (Fase 2). v0.16.4 completa Fase 3 cobrindo Gemini CLI via mecanismo oficial GEMINI.md + `.gemini/skills/`.

### Changed — `_skill_catalog.py` ganha `GEMINI_MARKER_PREFIX`

Adição mínima (+1 constante) pra cobrir o terceiro marker distinto:
- `RULE_MARKER_PREFIX` (Cursor, v0.16.2)
- `INSTRUCTIONS_MARKER_PREFIX` (Copilot, v0.16.3)
- `GEMINI_MARKER_PREFIX` (Gemini, v0.16.4 — novo)

### Changed — `_check_fragment_staleness()` cobre Gemini files

`plugadvpl status` agora detecta versão desatualizada em:
- `CLAUDE.md` + `AGENTS.md` (v0.16.1)
- Cursor rules (`~/.cursor/rules/plugadvpl.mdc` + `<project>/.cursor/rules/plugadvpl-*.mdc`, v0.16.2)
- Copilot instructions (`.github/copilot-instructions.md` + `.github/instructions/plugadvpl-*.instructions.md`, v0.16.3)
- **Gemini files** (`~/.gemini/GEMINI.md` + `<project>/GEMINI.md` + `.gemini/skills/plugadvpl-*/SKILL.md`, v0.16.4 — novo)

Helper `_check_gemini_staleness` paralelo ao Cursor/Copilot helpers (mantém PLR0912 ≤12).

### Added — `plugadvpl.gemini_skills` módulo

Novo módulo isolado (~220 linhas) com:
- `GeminiTarget` + `InstallResult` dataclasses (frozen, mutable fields com `default_factory=list`)
- `detect_gemini()` — política conservadora, sinais independentes
- `render_global_gemini_md()` — markdown plano com marker
- `render_skill_for_gemini()` — frontmatter Gemini (`name` + `description` apenas)
- `install_gemini_skills()` — orquestrador top-level NEVER-propagate
- Helpers `_install_gemini_global_home` + `_install_gemini_project_md` + `_install_one_gemini_skill` (PLR0912 preempt)

Reusa `_skill_catalog` (DRY).

### Added — 28 testes novos (TDD)

- 17 unit em `test_gemini_skills.py` (6 detect + 3 render_global + 6 render_skill + 2 install)
- 8 integration em `TestInitGeminiSkills` (no signals/project only/home only/--no-gemini/quiet + idempotency + overwrite + preserve)
- 3 integration em `TestStatus` (stale home + project + skill)

Suite full: 1123 → 1151 passed.

### Bumped

- `uvx plugadvpl@0.16.3` → `uvx plugadvpl@0.16.4` nas 26 skills operacionais.
- `plugin.json` / `marketplace.json` → 0.16.4.

### Multi-agente status (v0.16.4)

Plugadvpl agora cobre nativamente **4 agentes IA**:

| Agente | Mecanismo | Versão entregue |
|---|---|---|
| Claude Code | `CLAUDE.md` fragment | v0.1.x |
| Codex CLI | `AGENTS.md` gêmeo | v0.16.1 |
| Cursor | `.cursor/rules/*.mdc` (Cursor Rules) | v0.16.2 |
| GitHub Copilot | `.github/copilot-instructions.md` + `.github/instructions/*.instructions.md` | v0.16.3 |
| **Gemini CLI** | **`GEMINI.md` + `.gemini/skills/<X>/SKILL.md`** | **v0.16.4 (novo)** |

Cada agente recebe convenções globais + 52 skills específicas no formato nativo.
```

- [ ] **Step 2: README entry**

Em `README.md`, find `### v0.16.3 — Copilot Instructions nativos no init` (around line 700). INSERT BEFORE it:

```markdown
### v0.16.4 — Gemini CLI native skills no `init` (Fase 3 multi-agente)

- **`plugadvpl init` agora detecta Gemini CLI** (~/.gemini/, gemini PATH, ou .gemini/ projeto) e gera `~/.gemini/GEMINI.md` (global) + `<project>/GEMINI.md` (4º gêmeo) + 52 `.gemini/skills/plugadvpl-<X>/SKILL.md` (specifics com frontmatter `name` + `description`)
- Sinais detection **INDEPENDENTES** — global signal NÃO ativa project install (consistente com Cursor)
- Marker `plugadvpl-gemini-version` distinto dos 3 anteriores — `_check_fragment_staleness` ganha 4ª passada
- Flag `--no-gemini`; falha nunca quebra init
- **Multi-agente completo: Claude + Codex + Cursor + Copilot + Gemini** (5 agentes nativos)
- 28 testes novos (TDD). Suite full: 1151 passed

```

ALSO update Quick start. Find the existing line:
```
/plugadvpl:init      # cria .plugadvpl/index.db, fragments CLAUDE.md + AGENTS.md, .gitignore (+ Cursor rules + Copilot instructions se detectados)
```

Replace with:
```
/plugadvpl:init      # cria .plugadvpl/index.db, fragments CLAUDE.md + AGENTS.md + (Cursor rules / Copilot instructions / Gemini skills se detectados), .gitignore
```

- [ ] **Step 3: NÃO commitar — agregado na Task 10**

---

### Task 10: Release commit + tag + push + monitor

**Files:** todos modificados nas Tasks 8 + 9.

- [ ] **Step 1: Pre-flight**

```bash
cd /d/IA/Projetos/plugadvpl
git status --short
```

Expected ~30 files: 4 manifest/doc + 26 skills.

Suite + ruff format check final.

- [ ] **Step 2: Commit release**

```bash
cd /d/IA/Projetos/plugadvpl
git add -u
git commit -m "release: v0.16.4 — Gemini CLI native skills (Fase 3 multi-agente)

Bump 0.16.3 -> 0.16.4 (patch — adicao compativel).

plugadvpl init agora detecta Gemini CLI (via ~/.gemini/, gemini PATH,
ou .gemini/ projeto) e gera:
- ~/.gemini/GEMINI.md (global home — apenas se sinal home presente)
- <project>/GEMINI.md (4o gemeo CLAUDE.md + AGENTS.md + GEMINI.md)
- 52 .gemini/skills/plugadvpl-<X>/SKILL.md (specifics com frontmatter
  Gemini name + description)

Detection conservadora com sinais INDEPENDENTES — global signal nao
ativa project install (consistente com Cursor policy).

Marker plugadvpl-gemini-version distinto dos 3 anteriores
(rule/instructions/fragment), evita falso-positivo cross-agent.

Single source: SKILL.md embarcadas geram skills via render_skill_for_gemini.
Reusa _skill_catalog.py (DRY com cursor_rules + copilot_instructions).

Mudancas:
- cli/plugadvpl/_skill_catalog.py: +constante GEMINI_MARKER_PREFIX
- cli/plugadvpl/gemini_skills.py: novo modulo ~220 linhas (detect/render/
  install/helpers PLR0912-preempt)
- cli/plugadvpl/cli.py: init() ganha --no-gemini + chamada install;
  _check_fragment_staleness 4a passada Gemini via helper paralelo
- 28 testes novos TDD (17 unit + 8 init integration + 3 status)

Updates:
- plugin.json / marketplace.json -> 0.16.4
- uvx plugadvpl@0.16.3 -> @0.16.4 nas 26 skills operacionais
- CHANGELOG.md + README.md (secao v0.16.4 + multi-agente status 5 agentes)

Suite full: 1151 passed.

Multi-agente status (v0.16.4): Claude + Codex + Cursor + Copilot + Gemini.

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md
Plan: docs/superpowers/plans/2026-05-30-gemini-skills-implementation.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3: Tag annotated**

```bash
git tag -a v0.16.4 -m "v0.16.4 — Gemini CLI native skills (Fase 3 multi-agente)

plugadvpl init detecta Gemini e gera ~/.gemini/GEMINI.md (global) +
<project>/GEMINI.md (4o gemeo) + 52 .gemini/skills/plugadvpl-<X>/SKILL.md
(specifics).

Sinais detection independentes. Marker plugadvpl-gemini-version distinto.
Flag --no-gemini. Falha nunca quebra init.

Multi-agente completo: Claude + Codex + Cursor + Copilot + Gemini.

Suite full: 1151 passed.

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md"
```

- [ ] **Step 4: Push**

```bash
git push && git push --tags
```

- [ ] **Step 5: Monitor CI**

```bash
sleep 15 && gh run list --branch main --limit 2 --json status,name,databaseId,displayTitle
```

Find CI run ID for "release: v0.16.4", then:

```bash
gh run watch <ID> --interval 20 --exit-status
```

**Possíveis flakes conhecidos:**
- PLR0912 em `_check_fragment_staleness` — NÃO esperado (helper pattern mantém complexidade abaixo)
- Windows hook test timeout — já 30s desde v0.16.1
- Ruff format — corrigido no pre-flight

Se CI falhar: STOP e reporta.

- [ ] **Step 6: Verify release workflow**

```bash
gh run list --workflow release.yml --limit 2
```

Expected: `release: v0.16.4` com `success`.

- [ ] **Step 7: Verify PyPI + GitHub Release**

```bash
gh release view v0.16.4 --json name,publishedAt,url,assets --jq '{name, publishedAt, url, assets: [.assets[].name]}'
curl -s https://pypi.org/pypi/plugadvpl/0.16.4/json -o /dev/null -w "PyPI %{http_code}\n"
```

Expected: PyPI 200; assets `plugadvpl-0.16.4-py3-none-any.whl` + `plugadvpl-0.16.4.tar.gz`.

---

## Resumo execução

| Chunk | Tasks | Linhas estimadas |
|---|---|---|
| 1: Detect + constante | 1 | ~150 |
| 2: Renderers | 2 (Task 2, 3) | ~250 |
| 3: Install orquestrador | 1 (Task 4) | ~250 |
| 4: Init integration + idempotency + staleness | 3 (Task 5, 6, 7) | ~300 |
| 5: Release | 3 (Task 8, 9, 10) | ~100 |
| **Total** | **10 tasks** | **~1050** |

**Estimativa de tempo:** ~3-5h focadas (pattern paralelo à Fase 2 já validado).

**Critério final:**
- `gh release view v0.16.4` → ✅
- PyPI `plugadvpl 0.16.4` → ✅
- Smoke `uvx plugadvpl@0.16.4 init` num projeto com `.gemini/` → cria GEMINI.md + 52 skills
- Suite full: 1151 passed em CI (13 jobs cross-platform verde)

---

## Notas pra quem executar

1. **Constante em `_skill_catalog.py` é trivial mas crítica** — `GEMINI_MARKER_PREFIX` precisa ser DISTINTA das outras 2 marker prefixes. Não unifique.
2. **Gemini frontmatter é mais simples** — só `name` + `description`. NÃO inclua `applyTo`/`globs`/`alwaysApply` (Gemini não tem).
3. **Directory-per-skill** — Gemini espera `.gemini/skills/<name>/SKILL.md`, não `.gemini/skills/<name>.md`. O `_install_one_gemini_skill` cria a pasta antes do `_write_managed_file`.
4. **PLR0912 helper pattern** — siga o mesmo padrão que Copilot Task 5 fix usou. Não inline tudo no orquestrador.
5. **Autouse fixture extensão** — `TestInit` em `cli/tests/integration/test_cli.py` tem fixture autouse que mockou `cursor_rules.shutil.which`. Estender pra também mockar `gemini_skills.shutil.which` (Task 5 Step 4 documenta).
6. **Memórias do projeto:**
   - `feedback_powershell_utf8_bom`: bumps via Python read_bytes/write_bytes (NÃO PowerShell Set-Content)
   - `reference_plugadvpl_release_gotchas`: sempre `git tag -a`, suite full sem `--ignore` antes de release; release.yml já fixed na v0.16.2 (--sdist + --wheel separados)
   - `feedback_readme_atualizar_em_releases`: README touch obrigatório
