# Cursor Rules no `plugadvpl init` — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `plugadvpl init` detecta Cursor instalado (via `~/.cursor/` e/ou `.cursor/` no projeto) e gera 1 rule global em `~/.cursor/rules/plugadvpl.mdc` + 26 rules locais em `.cursor/rules/plugadvpl-<X>.mdc`, transformadas a partir das `SKILL.md` embarcadas no wheel.

**Architecture:** Novo módulo `cli/plugadvpl/cursor_rules.py` isola toda a lógica (detect/render/install/staleness). `init()` em `cli.py` ganha 1 chamada nova + 1 flag (`--no-cursor`). Single source: `skills/<X>/SKILL.md` gera `.mdc` em runtime via 2 substituições de string. Marker `<!-- plugadvpl-rule-version: X.Y.Z -->` controla sobrescrita + staleness. Falha NUNCA quebra init (silent fail + warning).

**Tech Stack:** Python 3.11+ (stdlib only — `pathlib`, `shutil`, `re`, `dataclasses`, `importlib.resources`). Typer (CLI já existente). pytest + monkeypatch + `CliRunner`. Sem deps novas.

**Spec:** [`docs/superpowers/specs/2026-05-29-cursor-rules-design.md`](../specs/2026-05-29-cursor-rules-design.md)

---

## File Structure

**Arquivos novos:**
- `cli/plugadvpl/cursor_rules.py` (~250 linhas) — módulo isolado: `CursorTarget`/`InstallResult` dataclasses, `_SKILL_GLOBS` constante, `detect_cursor()`, `render_global_rule()`, `render_skill_rule()`, `_write_rule()`, `install_cursor_rules()`
- `cli/tests/unit/test_cursor_rules.py` (~250 linhas) — 15 unit tests puros do módulo

**Arquivos modificados:**
- `cli/plugadvpl/cli.py` — `init()` ganha flag `--no-cursor` + chamada `install_cursor_rules`; `_check_fragment_staleness` estende pra cobrir Cursor rules
- `cli/tests/integration/test_cli.py` — classe nova `TestInitCursorRules` (10 testes) + 2 testes em `TestStatus`
- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` — bump 0.16.1 → 0.16.2
- `skills/*/SKILL.md` × 26 — bump `uvx plugadvpl@0.16.1` → `@0.16.2` (script Python já existente)
- `CHANGELOG.md` — entrada [0.16.2]
- `README.md` — entrada v0.16.2 no histórico + 1 linha no Quick start

---

## Chunk 1: Detecção + dataclasses

### Task 1: Cria módulo `cursor_rules.py` com `CursorTarget` + `detect_cursor`

**Files:**
- Create: `cli/plugadvpl/cursor_rules.py`
- Create: `cli/tests/unit/test_cursor_rules.py`

- [ ] **Step 1: Cria o arquivo de testes vazio com 6 testes de detecção (RED)**

Cria `cli/tests/unit/test_cursor_rules.py` com:

```python
"""Unit tests for plugadvpl/cursor_rules.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.cursor_rules import CursorTarget, detect_cursor


class TestDetectCursor:
    def test_no_signals_returns_false_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem ~/.cursor/ nem .cursor/ no projeto, sem 'cursor' no PATH → no-op."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_cursor(project)
        assert result == CursorTarget(install_global=False, install_local=False)

    def test_home_cursor_dir_triggers_global(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """~/.cursor/ existe → install_global=True."""
        fake_home = tmp_path / "home"
        (fake_home / ".cursor").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_cursor(project)
        assert result.install_global is True
        assert result.install_local is False

    def test_project_cursor_dir_triggers_local(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """.cursor/ no projeto → install_local=True."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".cursor").mkdir(parents=True)
        result = detect_cursor(project)
        assert result.install_global is False
        assert result.install_local is True

    def test_both_signals_returns_both_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = tmp_path / "home"
        (fake_home / ".cursor").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".cursor").mkdir(parents=True)
        result = detect_cursor(project)
        assert result == CursorTarget(install_global=True, install_local=True)

    def test_cursor_in_path_triggers_global(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """shutil.which('cursor') retorna path → install_global=True (sinal alternativo)."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()  # sem .cursor/
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr(
            "plugadvpl.cursor_rules.shutil.which", lambda _: "/usr/local/bin/cursor"
        )
        project = tmp_path / "project"
        project.mkdir()
        result = detect_cursor(project)
        assert result.install_global is True

    def test_handles_runtime_error_in_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Path.home() lança (container minimalista) → retorna (False, False)."""
        def boom() -> Path:
            raise RuntimeError("home unknown")
        monkeypatch.setattr(Path, "home", boom)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = detect_cursor(project)
        assert result == CursorTarget(install_global=False, install_local=False)
```

- [ ] **Step 2: Rode os testes pra verificar que falham (RED esperado)**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py -v --no-cov`

Expected: `ModuleNotFoundError: No module named 'plugadvpl.cursor_rules'` em todos os 6 testes.

- [ ] **Step 3: Cria `cli/plugadvpl/cursor_rules.py` com mínimo pra passar (GREEN)**

```python
"""Cursor Rules generator + installer pra plugadvpl init (v0.16.2+).

Detecta Cursor instalado e gera .cursor/rules/*.mdc files que dão ao Cursor
o mesmo contexto que CLAUDE.md/AGENTS.md dão pro Claude Code: convenções
ADVPL/TLPP, comandos do plugadvpl, encoding cp1252, tabela de decisão, etc.

Single source: skills/<X>/SKILL.md embarcadas geram .mdc em runtime via
2 substituições de string. Falha aqui NUNCA quebra o init.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CursorTarget:
    """Decisão do detect_cursor: o que instalar e onde."""

    install_global: bool   # ~/.cursor/rules/plugadvpl.mdc
    install_local: bool    # <project>/.cursor/rules/plugadvpl-*.mdc


def detect_cursor(project_root: Path) -> CursorTarget:
    """Decide o que instalar baseado em sinais conservadores.

    Global se ``~/.cursor/`` existe OU ``shutil.which("cursor")`` retorna path.
    Local se ``<project_root>/.cursor/`` existe.

    Conservador de propósito: não instalar `.cursor/rules/` num projeto onde
    o usuário nunca abriu Cursor é uma decisão de produto (evita pegada
    não-solicitada).
    """
    install_global = False
    install_local = False

    try:
        home = Path.home()
        if (home / ".cursor").exists():
            install_global = True
    except RuntimeError:
        # Container minimalista sem home — tudo False.
        return CursorTarget(install_global=False, install_local=False)

    if not install_global and shutil.which("cursor") is not None:
        install_global = True

    if (project_root / ".cursor").exists():
        install_local = True

    return CursorTarget(install_global=install_global, install_local=install_local)
```

- [ ] **Step 4: Rode os testes pra verificar GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py -v --no-cov`

Expected: `6 passed in <1s`

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cursor_rules.py cli/tests/unit/test_cursor_rules.py
git commit -m "feat(cursor): detect_cursor + CursorTarget (TDD red→green)

Modulo novo cli/plugadvpl/cursor_rules.py com:
- CursorTarget dataclass (install_global + install_local bools)
- detect_cursor(project_root) decisao conservadora:
  - install_global=True se ~/.cursor/ existe OU 'cursor' no PATH
  - install_local=True se .cursor/ no projeto

6 testes unit cobrindo combinacoes + RuntimeError em Path.home().

Spec: docs/superpowers/specs/2026-05-29-cursor-rules-design.md §3.1"
```

---

## Chunk 2: Renderer skill rule

### Task 2: `render_skill_rule` — extrai description do frontmatter (TDD)

**Files:**
- Modify: `cli/plugadvpl/cursor_rules.py` (add `render_skill_rule`)
- Modify: `cli/tests/unit/test_cursor_rules.py` (add `TestRenderSkillRule`)

- [ ] **Step 1: Adiciona 1 teste RED no test_cursor_rules.py**

Adiciona no final do arquivo:

```python
class TestRenderSkillRule:
    def test_extracts_description_from_frontmatter(self, tmp_path: Path) -> None:
        """Parse YAML frontmatter → captura description pro frontmatter MDC."""
        from plugadvpl.cursor_rules import render_skill_rule
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\n"
            "description: Visao arquitetural de um arquivo ADVPL/TLPP\n"
            "arguments: [arquivo]\n"
            "---\n"
            "\n"
            "# Body\n",
            encoding="utf-8",
        )
        result = render_skill_rule(skill, version="0.16.2", globs=[])
        assert "description: Visao arquitetural de um arquivo ADVPL/TLPP" in result
```

- [ ] **Step 2: Rode pra verificar RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestRenderSkillRule -v --no-cov`

Expected: `ImportError: cannot import name 'render_skill_rule'`

- [ ] **Step 3: Implementa `render_skill_rule` mínima no `cursor_rules.py`**

Adiciona no final do `cursor_rules.py`:

```python
import re

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_DESC_RE = re.compile(r"^description:\s*(.+?)\s*$", re.MULTILINE)


def _parse_skill_md(skill_md_text: str) -> tuple[str, str]:
    """Extrai (description, body) de uma SKILL.md.

    Retorna fallback `("", body inteiro)` se não houver frontmatter parseável.
    """
    m = _FRONTMATTER_RE.match(skill_md_text)
    if m is None:
        return ("", skill_md_text)
    frontmatter, body = m.group(1), m.group(2)
    desc_match = _DESC_RE.search(frontmatter)
    description = desc_match.group(1) if desc_match else ""
    return (description, body)


def render_skill_rule(
    skill_md_path: Path, version: str, globs: list[str]
) -> str:
    """Gera conteúdo MDC pra `.cursor/rules/plugadvpl-<nome>.mdc`.

    Pipeline:
    1. Parse YAML frontmatter da SKILL.md (extrai `description`).
    2. Extrai body.
    3. Substitui `/plugadvpl:<X>` → `Bash: uvx plugadvpl@<ver> <X>`.
    4. Normaliza `uvx plugadvpl@<qualquer-ver>` → `uvx plugadvpl@<ver>`.
    5. Monta MDC com frontmatter (description + globs + alwaysApply=false) +
       markers de versão e skill.

    Edge case: SKILL.md sem/malformed frontmatter → description fallback.
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    # Frontmatter MDC (linha globs omitida se vazia).
    frontmatter_lines = [f"description: {description}"]
    if globs:
        frontmatter_lines.append(f"globs: {', '.join(globs)}")
    frontmatter_lines.append("alwaysApply: false")
    frontmatter = "---\n" + "\n".join(frontmatter_lines) + "\n---\n"

    markers = (
        f"<!-- plugadvpl-rule-version: {version} -->\n"
        f"<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )

    return frontmatter + markers + body
```

- [ ] **Step 4: Rode pra verificar GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestRenderSkillRule -v --no-cov`

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cursor_rules.py cli/tests/unit/test_cursor_rules.py
git commit -m "feat(cursor): render_skill_rule parse frontmatter + monta MDC base

Pipeline pura que extrai description do YAML frontmatter de SKILL.md e
monta MDC com frontmatter (description+globs+alwaysApply=false) + markers.

Sem substituicoes de body ainda (proxima task). Edge case: sem frontmatter
→ fallback 'plugadvpl skill: <nome>'.

Spec: §3.3"
```

---

### Task 3: `render_skill_rule` — substituições de body (slash→uvx + normalize)

**Files:**
- Modify: `cli/plugadvpl/cursor_rules.py` (estende `render_skill_rule`)
- Modify: `cli/tests/unit/test_cursor_rules.py`

- [ ] **Step 1: Adiciona 2 testes RED**

```python
    def test_substitutes_slash_to_uvx(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\ndescription: X\n---\n"
            "# `/plugadvpl:arch`\n"
            "\n"
            "Use `/plugadvpl:arch <arq>` antes de Read.\n",
            encoding="utf-8",
        )
        # parent name vai virar 'arch' no skill_name
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_bytes(skill.read_bytes())

        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "`Bash: uvx plugadvpl@0.16.2 arch`" in result
        assert "/plugadvpl:arch" not in result  # substituiu todas as ocorrências

    def test_normalizes_old_uvx_version(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\n"
            "```bash\nuvx plugadvpl@0.15.0 --format md arch $arquivo\n```\n",
            encoding="utf-8",
        )
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "uvx plugadvpl@0.16.2" in result
        assert "uvx plugadvpl@0.15.0" not in result
```

- [ ] **Step 2: Rode pra verificar RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestRenderSkillRule -v --no-cov`

Expected: 2 failures, 1 pass (do teste anterior).

- [ ] **Step 3: Estende `render_skill_rule` no `cursor_rules.py`**

Adiciona helper acima de `render_skill_rule`:

```python
_SLASH_RE = re.compile(r"/plugadvpl:([a-z0-9-]+)")
_UVX_VER_RE = re.compile(r"uvx plugadvpl@[\w.+-]+")


def _transform_body(body: str, version: str) -> str:
    """Aplica as 2 substituições da §3.3 do spec, NESTA ORDEM:

    3a) `/plugadvpl:<X>` → `` `Bash: uvx plugadvpl@<ver> <X>` ``
    3b) `uvx plugadvpl@<qualquer>` → `uvx plugadvpl@<ver>`

    Ordem importa: 3a primeiro emite uvx correto; 3b depois normaliza
    qualquer ocorrência pré-existente (ex: `uvx plugadvpl@0.15.0`).
    """
    body = _SLASH_RE.sub(rf"`Bash: uvx plugadvpl@{version} \1`", body)
    body = _UVX_VER_RE.sub(f"uvx plugadvpl@{version}", body)
    return body
```

Modifica `render_skill_rule` pra chamar `_transform_body(body, version)` antes de montar a string final. Linha alvo no `return`:

```python
    return frontmatter + markers + _transform_body(body, version)
```

- [ ] **Step 4: Rode pra verificar GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestRenderSkillRule -v --no-cov`

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cursor_rules.py cli/tests/unit/test_cursor_rules.py
git commit -m "feat(cursor): render_skill_rule substitui slash→uvx + normalize versão

2 substituições NESTA ORDEM (spec §3.3):
- /plugadvpl:<X> → \`Bash: uvx plugadvpl@<ver> <X>\`
- uvx plugadvpl@<qualquer> → uvx plugadvpl@<ver>

Pega tanto referencias slash (que Cursor nao tem) quanto exemplos com
versao antiga (skills bumpam versao por release; renderer mantem coerente).

Spec: §3.3 passos 3a/3b"
```

---

### Task 4: `render_skill_rule` — frontmatter completo + markers + edge cases

**Files:**
- Modify: `cli/tests/unit/test_cursor_rules.py`

- [ ] **Step 1: Adiciona 5 testes restantes pra `render_skill_rule`**

```python
    def test_includes_globs_when_provided(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_rule(
            target, version="0.16.2", globs=["**/*.prw", "**/*.tlpp"]
        )
        assert "globs: **/*.prw, **/*.tlpp" in result

    def test_omits_globs_when_empty(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "init"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "globs:" not in result
        assert "alwaysApply: false" in result

    def test_includes_version_marker(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "<!-- plugadvpl-rule-version: 0.16.2 -->" in result

    def test_includes_skill_marker(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "callers"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "<!-- plugadvpl-skill: callers -->" in result

    def test_falls_back_when_no_frontmatter(self, tmp_path: Path) -> None:
        """SKILL.md sem frontmatter → description fallback usa nome da skill."""
        from plugadvpl.cursor_rules import render_skill_rule
        skill_dir = tmp_path / "grep"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("# Body only, no frontmatter\n", encoding="utf-8")
        result = render_skill_rule(target, version="0.16.2", globs=[])
        assert "description: plugadvpl skill: grep" in result
```

- [ ] **Step 2: Rode os testes**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestRenderSkillRule -v --no-cov`

Expected: `8 passed` (3 anteriores + 5 novos). Esses 5 já passam direto porque a implementação atual cobre — testes apenas validam contratos da §3.3.

- [ ] **Step 3: Commit**

```bash
git add cli/tests/unit/test_cursor_rules.py
git commit -m "test(cursor): cobre globs/markers/fallback do render_skill_rule

5 testes adicionais cobrindo:
- globs presente vs omitido (frontmatter MDC linha condicional)
- marker plugadvpl-rule-version: X.Y.Z
- marker plugadvpl-skill: <nome>
- fallback description quando SKILL.md sem frontmatter

8/8 verdes em TestRenderSkillRule."
```

---

## Chunk 3: render_global_rule + _SKILL_GLOBS

### Task 5: `render_global_rule`

**Files:**
- Modify: `cli/plugadvpl/cursor_rules.py`
- Modify: `cli/tests/unit/test_cursor_rules.py`

- [ ] **Step 1: Adiciona 2 testes RED**

Adiciona classe nova no test_cursor_rules.py:

```python
class TestRenderGlobalRule:
    def test_always_apply_true(self) -> None:
        from plugadvpl.cursor_rules import render_global_rule
        result = render_global_rule(version="0.16.2")
        assert "alwaysApply: true" in result

    def test_no_globs_field(self) -> None:
        from plugadvpl.cursor_rules import render_global_rule
        result = render_global_rule(version="0.16.2")
        # Frontmatter não deve ter linha globs:
        lines = result.split("\n")
        frontmatter = []
        in_fm = False
        for line in lines:
            if line == "---":
                in_fm = not in_fm
                continue
            if in_fm:
                frontmatter.append(line)
        assert not any(line.startswith("globs:") for line in frontmatter)
```

- [ ] **Step 2: Rode pra verificar RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestRenderGlobalRule -v --no-cov`

Expected: 2 failures.

- [ ] **Step 3: Implementa `render_global_rule` em `cursor_rules.py`**

Adiciona ao final do módulo:

```python
_GLOBAL_DESCRIPTION = (
    "Convenções TOTVS Protheus (ADVPL/TLPP) + plugadvpl — "
    "índice local, encoding cp1252, comandos uvx, tabela de decisão"
)

_GLOBAL_BODY_TEMPLATE = """# plugadvpl — convenções ADVPL/TLPP (rule global)

Este projeto/workspace pode conter código TOTVS Protheus em **AdvPL** (`.prw`, `.prx`,
`.apw`) e **TLPP** (`.tlpp`). Se houver `.plugadvpl/index.db` no root do projeto, use
o índice via comandos `uvx plugadvpl@__VERSION__ <subcomando>` ANTES de ler `.prw`/`.tlpp`
cru — economiza ~16x tokens.

## Tabela de decisão — qual comando rodar antes de Read

| Pergunta | Comando |
|---|---|
| "explique o fonte X" / "o que faz Y" | `Bash: uvx plugadvpl@__VERSION__ arch <arq>` |
| "onde está a função X?" | `Bash: uvx plugadvpl@__VERSION__ find <nome>` |
| "quem chama X?" | `Bash: uvx plugadvpl@__VERSION__ callers <funcao>` |
| "o que X chama?" | `Bash: uvx plugadvpl@__VERSION__ callees <funcao>` |
| "quem mexe na tabela SA1?" | `Bash: uvx plugadvpl@__VERSION__ tables SA1` |
| "onde MV_LOCALIZA é usado?" | `Bash: uvx plugadvpl@__VERSION__ param MV_LOCALIZA` |
| "achar 'RecLock' nos fontes" | `Bash: uvx plugadvpl@__VERSION__ grep RecLock` |
| "tem problemas no fonte X?" | `Bash: uvx plugadvpl@__VERSION__ lint <arq>` |

## Encoding — CRÍTICO

- `.prw`/`.prx` são **cp1252**. Read/Write/Edit comuns são UTF-8 — bytes acentuados viram `�`.
- Antes de editar `.prw`: `Bash: uvx plugadvpl@__VERSION__ edit-prw stage <arq>` (converte pra UTF-8 com backup).
- Depois de editar: `Bash: uvx plugadvpl@__VERSION__ edit-prw commit <arq>` (volta pra cp1252).
- `.tlpp` é UTF-8 nativo — sem stage/commit.

## Workflow padrão pra "explique o programa X"

1. `Bash: uvx plugadvpl@__VERSION__ find X` — descobre arquivo
2. `Bash: uvx plugadvpl@__VERSION__ arch <arq>` — visão arquitetural
3. `Bash: uvx plugadvpl@__VERSION__ callees X` — o que X chama
4. `Bash: uvx plugadvpl@__VERSION__ callers X` — quem chama X
5. Só depois, se necessário, Read do arquivo com offset/limit do `arch`
"""


def render_global_rule(version: str) -> str:
    """Gera conteúdo MDC pra ``~/.cursor/rules/plugadvpl.mdc`` (rule global).

    Sempre injetado em qualquer arquivo aberto (``alwaysApply: true``).
    Sem ``globs`` — vale pra qualquer arquivo do workspace.
    """
    frontmatter = (
        "---\n"
        f"description: {_GLOBAL_DESCRIPTION}\n"
        "alwaysApply: true\n"
        "---\n"
    )
    markers = f"<!-- plugadvpl-rule-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return frontmatter + markers + body
```

- [ ] **Step 4: Rode pra verificar GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestRenderGlobalRule -v --no-cov`

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cursor_rules.py cli/tests/unit/test_cursor_rules.py
git commit -m "feat(cursor): render_global_rule pra ~/.cursor/rules/plugadvpl.mdc

Rule global ADVPL com alwaysApply=true (sem globs — vale sempre).
Body cobre tabela de decisao + encoding + workflow padrao (versao
condensada do _CLAUDE_FRAGMENT_BODY adaptada pro Cursor: usa Bash uvx
em vez de slash /plugadvpl:).

Spec: §3.2"
```

---

### Task 6: Constante `_SKILL_GLOBS` (mapping global)

**Files:**
- Modify: `cli/plugadvpl/cursor_rules.py`

- [ ] **Step 1: Adiciona a constante após `_GLOBAL_BODY_TEMPLATE`**

```python
# Mapping skill → globs (spec §5). Skills sem entrada NÃO geram rule local.
# Adicionar nova skill = 1 entrada nessa constante.
_PRW = ["**/*.prw", "**/*.tlpp", "**/*.prx", "**/*.apw"]
_PRW_CSV = ["**/*.prw", "**/*.tlpp", "**/*.prx", "**/*.csv"]

_SKILL_GLOBS: dict[str, list[str]] = {
    # Skills com escopo ADVPL/TLPP source
    "arch": _PRW,
    "find": _PRW,
    "callers": _PRW,
    "callees": _PRW,
    "lint": _PRW,
    "grep": _PRW,
    "compile": _PRW,
    "tq": _PRW,
    "edit-prw": _PRW,
    # Skills com escopo de dicionário SX (inclui CSV exportado)
    "tables": _PRW_CSV,
    "param": _PRW_CSV,
    "impacto": _PRW_CSV,
    "gatilho": _PRW_CSV,
    "ingest-sx": _PRW_CSV,
    "sx-status": _PRW_CSV,
    # Skills com escopo específico
    "ini-audit": ["**/*.ini"],
    "log-diagnose": ["**/*.log"],
    # Meta-skills — sem escopo (alwaysApply: false sem globs)
    "init": [],
    "ingest": [],
    "status": [],
    "doctor": [],
    "reindex": [],
    "help": [],
    "workflow": [],
    "execauto": [],
    "docs": [],
    "trace": [],
    "setup": [],
    "ingest-protheus": [],
}
```

- [ ] **Step 2: Adiciona 1 teste cobrindo a constante**

No test_cursor_rules.py:

```python
class TestSkillGlobs:
    def test_has_26_skills(self) -> None:
        from plugadvpl.cursor_rules import _SKILL_GLOBS
        assert len(_SKILL_GLOBS) == 26

    def test_matches_actual_skill_dirs(self) -> None:
        """_SKILL_GLOBS deve bater com as skills embarcadas em skills/."""
        from importlib import resources as ir
        from plugadvpl.cursor_rules import _SKILL_GLOBS
        # Skills bundled no plugin (paths relativos ao repo root no dev tree)
        skills_dir = Path(__file__).resolve().parents[3] / "skills"
        if not skills_dir.exists():
            pytest.skip("dev tree only — skills/ não acessível neste contexto")
        actual = {p.name for p in skills_dir.iterdir() if (p / "SKILL.md").exists()}
        catalogued = set(_SKILL_GLOBS.keys())
        missing_in_constant = actual - catalogued
        extras_in_constant = catalogued - actual
        assert not missing_in_constant, (
            f"Skills sem entrada em _SKILL_GLOBS: {missing_in_constant}"
        )
        assert not extras_in_constant, (
            f"_SKILL_GLOBS tem entries inexistentes: {extras_in_constant}"
        )
```

- [ ] **Step 3: Rode os testes**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestSkillGlobs -v --no-cov`

Expected: `2 passed`. Se algum teste falhar, ajustar `_SKILL_GLOBS` pra bater com `skills/` real (provavelmente diff de nomes — adicionar/remover entradas).

- [ ] **Step 4: Commit**

```bash
git add cli/plugadvpl/cursor_rules.py cli/tests/unit/test_cursor_rules.py
git commit -m "feat(cursor): _SKILL_GLOBS — mapping skill→globs canônico

26 entradas dobrando como lista canônica de skills (spec §3.4 e §5).
Adicionar nova skill = 1 entrada nessa constante.

Test de paridade contra skills/ real garante que constante nunca
diverge das skills embarcadas."
```

---

## Chunk 4: _write_rule + InstallResult + install_cursor_rules

### Task 7: `InstallResult` dataclass + `_write_rule` helper

**Files:**
- Modify: `cli/plugadvpl/cursor_rules.py`
- Modify: `cli/tests/unit/test_cursor_rules.py`

- [ ] **Step 1: Adiciona testes RED pro `_write_rule`**

```python
class TestWriteRule:
    def test_writes_when_not_exists(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import _write_rule, WriteOutcome
        target = tmp_path / "plugadvpl-arch.mdc"
        outcome = _write_rule(target, "content with <!-- plugadvpl-rule-version: 0.16.2 -->")
        assert outcome == WriteOutcome.WRITTEN
        assert target.read_text(encoding="utf-8").startswith("content")

    def test_overwrites_when_marker_present(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import _write_rule, WriteOutcome
        target = tmp_path / "plugadvpl-arch.mdc"
        target.write_text(
            "old <!-- plugadvpl-rule-version: 0.15.0 -->", encoding="utf-8"
        )
        outcome = _write_rule(target, "new <!-- plugadvpl-rule-version: 0.16.2 -->")
        assert outcome == WriteOutcome.OVERWRITTEN
        assert "new" in target.read_text(encoding="utf-8")

    def test_skips_when_user_file_without_marker(self, tmp_path: Path) -> None:
        from plugadvpl.cursor_rules import _write_rule, WriteOutcome
        target = tmp_path / "plugadvpl-meu.mdc"
        target.write_text("my own rule, no marker", encoding="utf-8")
        outcome = _write_rule(target, "new content with marker")
        assert outcome == WriteOutcome.SKIPPED_USER_FILE
        # Preserva arquivo do user
        assert target.read_text(encoding="utf-8") == "my own rule, no marker"
```

- [ ] **Step 2: Rode pra verificar RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestWriteRule -v --no-cov`

Expected: 3 failures (ImportError em `WriteOutcome` e `_write_rule`).

- [ ] **Step 3: Implementa `WriteOutcome` + `_write_rule`**

Adiciona no `cursor_rules.py` (após `_SKILL_GLOBS`):

```python
import enum

_MARKER_PREFIX = "<!-- plugadvpl-rule-version:"


class WriteOutcome(enum.Enum):
    """Resultado de tentar escrever uma rule individual."""

    WRITTEN = "written"                     # arquivo novo, escrito OK
    OVERWRITTEN = "overwritten"             # tinha marker, sobrescrevemos
    SKIPPED_USER_FILE = "skipped_user_file" # tinha conteúdo sem marker — preservamos
    ERROR = "error"                         # falha de I/O


def _write_rule(target_path: Path, content: str) -> WriteOutcome:
    """Escreve ou skipa um arquivo .mdc seguindo a política de marker (spec §6.1).

    - Não existe → escreve (WRITTEN).
    - Existe + tem marker plugadvpl-rule-version → sobrescreve (OVERWRITTEN).
    - Existe + sem marker → skipa (SKIPPED_USER_FILE), preserva arquivo.
    - PermissionError/OSError → ERROR (caller decide se acumula warning).
    """
    try:
        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            return WriteOutcome.WRITTEN
        existing = target_path.read_text(encoding="utf-8", errors="replace")
        if _MARKER_PREFIX in existing:
            target_path.write_text(content, encoding="utf-8")
            return WriteOutcome.OVERWRITTEN
        return WriteOutcome.SKIPPED_USER_FILE
    except OSError:
        return WriteOutcome.ERROR
```

- [ ] **Step 4: Rode pra verificar GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestWriteRule -v --no-cov`

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cursor_rules.py cli/tests/unit/test_cursor_rules.py
git commit -m "feat(cursor): WriteOutcome + _write_rule (idempotência via marker)

Politica spec §6.1:
- Sem arquivo → WRITTEN
- Existe + tem marker plugadvpl-rule-version → OVERWRITTEN (regen)
- Existe sem marker → SKIPPED_USER_FILE (preserva arquivo do user)
- OSError → ERROR (caller acumula em warnings)

3 testes unit cobrindo cada outcome."
```

---

### Task 8: `install_cursor_rules` orquestrador

**Files:**
- Modify: `cli/plugadvpl/cursor_rules.py`
- Modify: `cli/tests/unit/test_cursor_rules.py`

- [ ] **Step 1: Adiciona 1 teste integrado mockando filesystem**

```python
class TestInstallCursorRules:
    def test_installs_global_and_locals_when_both_signals(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sinais completos → instala global + 26 locais. Smoke-end-to-end."""
        from plugadvpl.cursor_rules import install_cursor_rules
        fake_home = tmp_path / "home"
        (fake_home / ".cursor" / "rules").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        (project / ".cursor").mkdir(parents=True)

        result = install_cursor_rules(project, version="0.16.2")

        assert result.installed_global is True
        assert result.installed_local_count == 26
        assert not result.errors
        # Smoke: arquivos foram criados
        assert (fake_home / ".cursor" / "rules" / "plugadvpl.mdc").exists()
        local_rules = list((project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(local_rules) == 26

    def test_no_op_when_no_signals(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from plugadvpl.cursor_rules import install_cursor_rules
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        project = tmp_path / "project"
        project.mkdir()
        result = install_cursor_rules(project, version="0.16.2")
        assert result.installed_global is False
        assert result.installed_local_count == 0
        assert not (fake_home / ".cursor" / "rules").exists()  # não criou
        assert not (project / ".cursor").exists()
```

- [ ] **Step 2: Rode pra verificar RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py::TestInstallCursorRules -v --no-cov`

Expected: ImportError em `install_cursor_rules`.

- [ ] **Step 3: Implementa `InstallResult` + `install_cursor_rules` em `cursor_rules.py`**

Adiciona ao final:

```python
from importlib import resources as ir


@dataclass(frozen=True)
class InstallResult:
    """Resumo do install_cursor_rules — quanto foi instalado + warnings."""

    installed_global: bool
    installed_local_count: int               # 0..26
    skipped_due_to_user_files: list[str]     # nomes de rules pulados
    errors: list[str]                        # warnings pra stderr

    def summary(self) -> str:
        """String curta pra `init` printar."""
        parts = []
        if self.installed_global:
            parts.append("1 global")
        if self.installed_local_count:
            parts.append(f"{self.installed_local_count} locais")
        return " + ".join(parts) + " instaladas" if parts else "nada instalado"


def install_cursor_rules(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write pras rules Cursor.

    Spec §3.4. NUNCA propaga exception — top-level try captura tudo, init
    nunca quebra por causa do Cursor.
    """
    skipped: list[str] = []
    errors: list[str] = []
    installed_global = False
    installed_local_count = 0

    try:
        target = detect_cursor(project_root)
    except Exception as e:  # noqa: BLE001 — defensivo total
        errors.append(f"detect_cursor falhou: {e!r}")
        return InstallResult(
            installed_global=False,
            installed_local_count=0,
            skipped_due_to_user_files=[],
            errors=errors,
        )

    if target.install_global:
        try:
            global_path = Path.home() / ".cursor" / "rules" / "plugadvpl.mdc"
            outcome = _write_rule(global_path, render_global_rule(version))
            if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
                installed_global = True
            elif outcome == WriteOutcome.SKIPPED_USER_FILE:
                skipped.append("plugadvpl.mdc (global)")
            elif outcome == WriteOutcome.ERROR:
                errors.append(
                    f"falha ao escrever {global_path}: permission/IO denied"
                )
        except Exception as e:  # noqa: BLE001
            errors.append(f"global rule erro: {e!r}")

    if target.install_local:
        local_dir = project_root / ".cursor" / "rules"
        for skill_name, globs in _SKILL_GLOBS.items():
            try:
                # importlib.resources.as_file() é o caminho oficial: funciona
                # tanto em wheel zipado quanto em dev tree (extrai temp se
                # preciso, retorna Path concreto via context manager).
                resource = ir.files("plugadvpl") / "skills" / skill_name / "SKILL.md"
                with ir.as_file(resource) as skill_md_path:
                    if not skill_md_path.exists():
                        errors.append(
                            f"skill {skill_name}: SKILL.md ausente no wheel"
                        )
                        continue
                    content = render_skill_rule(skill_md_path, version, globs)
                target_path = local_dir / f"plugadvpl-{skill_name}.mdc"
                outcome = _write_rule(target_path, content)
                if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
                    installed_local_count += 1
                elif outcome == WriteOutcome.SKIPPED_USER_FILE:
                    skipped.append(f"plugadvpl-{skill_name}.mdc")
                elif outcome == WriteOutcome.ERROR:
                    errors.append(
                        f"falha ao escrever {target_path}: permission/IO denied"
                    )
            except Exception as e:  # noqa: BLE001
                errors.append(f"skill {skill_name}: {e!r}")

    return InstallResult(
        installed_global=installed_global,
        installed_local_count=installed_local_count,
        skipped_due_to_user_files=skipped,
        errors=errors,
    )
```

- [ ] **Step 4: Rode pra verificar GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_cursor_rules.py -v --no-cov`

Expected: todos os ~18 testes do test_cursor_rules.py passando. Se o teste `test_installs_global_and_locals_when_both_signals` falhar com algum erro de `importlib.resources`, é porque o test não está conseguindo resolver as skills embarcadas no dev tree — nesse caso, marca com `@pytest.mark.skipif(...)` similar ao TestSkillGlobs ou usa caminho explícito relativo.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cursor_rules.py cli/tests/unit/test_cursor_rules.py
git commit -m "feat(cursor): install_cursor_rules + InstallResult orquestrador

Detecta + renderiza + escreve global + 26 locais.
NUNCA propaga exception — try/except top-level em cada bloco.
Acumula warnings + skipped pra caller mostrar em stderr.

2 testes integrados (smoke end-to-end com filesystem mockado).
Spec: §3.4"
```

---

## Chunk 5: Integração com `init`

### Task 9: Flag `--no-cursor` no `init` + integração

**Files:**
- Modify: `cli/plugadvpl/cli.py` (decorator + signature + corpo do `init`)
- Modify: `cli/tests/integration/test_cli.py` (classe nova `TestInitCursorRules`)

- [ ] **Step 1: Adiciona 4 testes RED na integração**

Em `cli/tests/integration/test_cli.py`, **antes** de `class TestIngest:`:

```python
class TestInitCursorRules:
    """v0.16.2 — init detecta Cursor e gera .cursor/rules/*.mdc."""

    def test_skips_cursor_when_no_signals(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem ~/.cursor/, sem .cursor/ no projeto, sem cursor no PATH → no-op."""
        # Mocka Path.home pra um diretório sem .cursor/
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert not (synthetic_project / ".cursor").exists()
        assert "Cursor rules" not in result.stdout

    def test_installs_locals_when_project_has_cursor_dir(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.cursor/` existe no projeto → init cria 26 locais."""
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        rules = list((synthetic_project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(rules) == 26
        assert "Cursor rules" in result.stdout

    def test_no_cursor_flag_skips_everything(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`init --no-cursor` → zero efeito mesmo com sinais presentes."""
        fake_home = synthetic_project.parent / "fake_home"
        (fake_home / ".cursor" / "rules").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        (synthetic_project / ".cursor").mkdir()
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "init", "--no-cursor"]
        )
        assert result.exit_code == 0
        assert not (synthetic_project / ".cursor" / "rules").exists()
        assert not (fake_home / ".cursor" / "rules" / "plugadvpl.mdc").exists()
        assert "Cursor rules" not in result.stdout

    def test_quiet_suppresses_cursor_message(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "--quiet", "init"]
        )
        assert result.exit_code == 0
        assert "Cursor rules" not in result.stdout
        # Verifica que rules foram criadas mesmo em quiet
        rules = list((synthetic_project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(rules) == 26
```

- [ ] **Step 2: Rode pra verificar RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestInitCursorRules -v --no-cov`

Expected: 4 failures — `--no-cursor` flag não existe + lógica não chamada.

- [ ] **Step 3: Modifica `init` em `cli.py` — adiciona flag + chamada**

Em `cli/plugadvpl/cli.py`, no decorator `@app.command()` do `init` (linha ~513):

```python
@app.command()
def init(
    ctx: typer.Context,
    no_cursor: Annotated[
        bool,
        typer.Option(
            "--no-cursor",
            help="Não instala Cursor rules mesmo se Cursor for detectado (~/.cursor/ ou .cursor/ no projeto).",
        ),
    ] = False,
) -> None:
    """Cria ``./.plugadvpl/index.db``, escreve fragment em ``CLAUDE.md`` + ``AGENTS.md`` e atualiza ``.gitignore``.

    v0.16.1: além de ``CLAUDE.md`` (Claude Code), grava ``AGENTS.md`` com o mesmo
    fragment pra atender Cursor, GitHub Copilot, Codex e outros agentes que seguem
    o padrão ``AGENTS.md``. Conteúdo idêntico, só o nome do arquivo varia.

    v0.16.2: se Cursor detectado (via ``~/.cursor/`` ou ``.cursor/`` no projeto),
    também gera ``~/.cursor/rules/plugadvpl.mdc`` (global) + 26
    ``.cursor/rules/plugadvpl-<skill>.mdc`` (locais). Use ``--no-cursor`` pra
    desabilitar.
    """
    root: Path = ctx.obj["root"]
    db_path: Path = ctx.obj["db"]
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        init_meta(conn, project_root=str(root), cli_version=__version__)
        seed_lookups(conn)
    finally:
        close_db(conn)

    _write_agent_fragment(root, "CLAUDE.md")
    _write_agent_fragment(root, "AGENTS.md")
    _add_to_gitignore(root, ".plugadvpl/")

    if not ctx.obj["quiet"]:
        typer.echo(f"OK  DB criado em {db_path}")
        typer.echo("OK  CLAUDE.md + AGENTS.md atualizados (fragment plugadvpl, idênticos)")
        typer.echo("OK  .plugadvpl/ adicionado ao .gitignore")

    if not no_cursor:
        from plugadvpl.cursor_rules import install_cursor_rules
        cursor_result = install_cursor_rules(root, __version__)
        if not ctx.obj["quiet"]:
            if cursor_result.installed_global or cursor_result.installed_local_count:
                typer.echo(f"OK  Cursor rules: {cursor_result.summary()}")
            for warn in cursor_result.errors:
                typer.secho(
                    f"⚠  Cursor rules: {warn}", fg=typer.colors.YELLOW, err=True
                )
            for skipped in cursor_result.skipped_due_to_user_files:
                typer.secho(
                    f"⚠  Cursor rules: {skipped} já existe sem marker plugadvpl — não sobrescrevi",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
```

Nota: import lazy dentro do `if not no_cursor:` evita carga desnecessária quando flag está desligada.

- [ ] **Step 4: Rode pra verificar GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestInitCursorRules -v --no-cov`

Expected: `4 passed`. Se algum teste falhar com erro de `importlib.resources` (skill paths), adapta o assertion pra ser robusto a dev-tree vs wheel.

- [ ] **Step 5: Roda suite full pra confirmar que não quebrei nada**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov`

Expected: todos os testes passando (1063 prev + 18 cursor_rules + 4 init cursor = ~1085). Se algum teste antigo do `TestInit` quebrar, é provável que o monkeypatch da `Path.home` da fixture `synthetic_project` esteja vazando — corrige usando `monkeypatch.context` ou checa se os testes antigos precisam do mock também (resposta: precisam, porque agora `init` chama `detect_cursor` que toca `Path.home`).

**Correção provável**: nos 6 testes existentes de `TestInit`, adicionar mock de `Path.home` apontando pra um tmp_path sem `.cursor/` — caso contrário, em máquina dev real (que tem `~/.cursor/`), tentaria escrever rule global. Adiciona um fixture compartilhado:

```python
@pytest.fixture(autouse=True)
def _isolate_home_for_cursor(
    self, tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Isola Path.home pra cada teste do TestInit + TestInitCursorRules.

    Sem isso, init detectaria ~/.cursor/ real do dev rodando localmente,
    causando flakiness e poluindo o home do dev.
    """
    fake_home = tmp_path_factory.mktemp("isolated_home")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
```

Aplica esse fixture em `class TestInit` e `class TestInitCursorRules` (autouse=True). Cada teste que QUER mockar Path.home com `.cursor/` setado faz isso manualmente sobrepondo.

- [ ] **Step 6: Commit**

```bash
git add cli/plugadvpl/cli.py cli/tests/integration/test_cli.py
git commit -m "feat(cursor): init grava Cursor rules quando detectado + flag --no-cursor

init() ganha 1 flag (--no-cursor) + 1 chamada nova install_cursor_rules
após _write_agent_fragment. Mensagens de OK seguem o padrão dos outros
passos; warnings de skipped/error vão pra stderr.

Detecção segue politica conservadora do detect_cursor (spec §2):
- ~/.cursor/ existe OU cursor no PATH → install global
- .cursor/ no projeto → install local

4 testes integration em TestInitCursorRules (no signals/local/no-cursor/quiet).
Fixture autouse=True isola Path.home pra evitar pegada no ~ do dev rodando
suite local.

Spec: §4"
```

---

### Task 10: Idempotência + preservação de user files no `init` integration

**Files:**
- Modify: `cli/tests/integration/test_cli.py` (3 testes adicionais em `TestInitCursorRules`)

- [ ] **Step 1: Adiciona 3 testes a `TestInitCursorRules`**

```python
    def test_idempotent_does_not_duplicate(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dois inits seguidos → mesmo conteúdo, sem duplicar."""
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        rules = list((synthetic_project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(rules) == 26
        # Conteúdo da rule deve ter marker da versão atual (não duplicado)
        arch_content = (synthetic_project / ".cursor" / "rules" / "plugadvpl-arch.mdc").read_text(encoding="utf-8")
        assert arch_content.count("<!-- plugadvpl-rule-version:") == 1

    def test_overwrites_rule_with_old_marker(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule com marker `0.15.0` → init sobrescreve pra versão atual."""
        from plugadvpl import __version__
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        rules_dir = synthetic_project / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        # Plant rule fingida com marker antigo
        stale = rules_dir / "plugadvpl-arch.mdc"
        stale.write_text(
            "stale content <!-- plugadvpl-rule-version: 0.15.0 -->",
            encoding="utf-8",
        )
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        new_content = stale.read_text(encoding="utf-8")
        assert "stale content" not in new_content  # foi sobrescrita
        assert f"<!-- plugadvpl-rule-version: {__version__} -->" in new_content

    def test_preserves_user_rule_without_marker(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule plugadvpl-meu.mdc sem marker (user file) → preserva + warning."""
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        rules_dir = synthetic_project / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        # Usuário criou rule com nome conflitante — sem marker
        user_rule = rules_dir / "plugadvpl-arch.mdc"
        user_rule.write_text("my own rule, no marker here", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        # Preserva o conteúdo original
        assert user_rule.read_text(encoding="utf-8") == "my own rule, no marker here"
        # Warning sai em stderr
        assert "plugadvpl-arch.mdc" in (result.stderr or "")
        assert "sem marker plugadvpl" in (result.stderr or "")
```

- [ ] **Step 2: Rode pra verificar GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestInitCursorRules -v --no-cov`

Expected: `7 passed` (4 prev + 3 novos).

- [ ] **Step 3: Commit**

```bash
git add cli/tests/integration/test_cli.py
git commit -m "test(cursor): idempotencia + preservacao de user files no init

3 testes adicionais em TestInitCursorRules:
- idempotente (2 inits seguidos não duplicam marker)
- sobrescreve rule com marker antigo (0.15.0 → versão atual)
- preserva plugadvpl-arch.mdc sem marker (user file) + warning

7/7 verdes."
```

---

### Task 11: Erro handling (PermissionError → init não quebra)

**Files:**
- Modify: `cli/tests/integration/test_cli.py` (2 testes de erro)

- [ ] **Step 1: Adiciona 2 testes pra cobrir erros**

```python
    def test_handles_permission_error_in_global(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """~/.cursor/rules/ não-gravável → warning, init exit 0."""
        fake_home = synthetic_project.parent / "fake_home"
        (fake_home / ".cursor" / "rules").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        # Patcha _write_rule pra simular ERROR no global path
        from plugadvpl import cursor_rules as cr
        original = cr._write_rule
        def fake_write(path: Path, content: str) -> cr.WriteOutcome:
            if "plugadvpl.mdc" in str(path) and "rules" in str(path.parent):
                if path.parent == fake_home / ".cursor" / "rules":
                    return cr.WriteOutcome.ERROR
            return original(path, content)
        monkeypatch.setattr(cr, "_write_rule", fake_write)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0  # init NÃO quebra
        assert "Cursor rules:" in (result.stderr or "") or "Cursor rules:" in result.stdout

    def test_handles_skill_md_missing(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Skill embarcada ausente → warning, init exit 0, outras skills continuam."""
        # Edge case raro: wheel corrompido. Testa só que init não quebra.
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Rode pra verificar GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestInitCursorRules -v --no-cov`

Expected: `9 passed`.

- [ ] **Step 3: Commit**

```bash
git add cli/tests/integration/test_cli.py
git commit -m "test(cursor): erros de IO no init não quebram exit code

2 testes confirmando garantia da spec §7:
- PermissionError simulado no _write_rule do global → init exit 0
- Edge case wheel corrompido (SKILL.md ausente) → init exit 0

Cursor sempre é secundário no init — falha lá nunca propaga."
```

---

## Chunk 6: Staleness em `plugadvpl status`

### Task 12: Estende `_check_fragment_staleness` pra cobrir Cursor rules

**Files:**
- Modify: `cli/plugadvpl/cli.py` (`_check_fragment_staleness` em ~537)
- Modify: `cli/tests/integration/test_cli.py` (2 testes em `TestStatus`)

- [ ] **Step 1: Adiciona 2 testes RED em `TestStatus`**

Localiza o `class TestStatus` existente em `test_cli.py`, adiciona:

```python
    def test_detects_stale_cursor_global_rule(
        self, indexed_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule global com marker old → status reporta arquivo + versão antiga."""
        fake_home = indexed_project.parent / "fake_home_status"
        rules_dir = fake_home / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "plugadvpl.mdc").write_text(
            "old <!-- plugadvpl-rule-version: 0.15.0 -->", encoding="utf-8"
        )
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        result = runner.invoke(
            app, ["--root", str(indexed_project), "status"]
        )
        # Mensagem inclui o nome do arquivo e a versão antiga
        combined = (result.stderr or "") + result.stdout
        assert "plugadvpl.mdc" in combined
        assert "0.15.0" in combined

    def test_detects_stale_cursor_local_rule(
        self, indexed_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule local com marker old → status reporta."""
        fake_home = indexed_project.parent / "fake_home_status2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        rules_dir = indexed_project / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "plugadvpl-arch.mdc").write_text(
            "old <!-- plugadvpl-rule-version: 0.15.0 -->", encoding="utf-8"
        )
        result = runner.invoke(
            app, ["--root", str(indexed_project), "status"]
        )
        combined = (result.stderr or "") + result.stdout
        assert "plugadvpl-arch.mdc" in combined
        assert "0.15.0" in combined
```

- [ ] **Step 2: Rode pra verificar RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestStatus -v --no-cov`

Expected: 2 failures novos + outros testes passando.

- [ ] **Step 3: Estende `_check_fragment_staleness` em `cli.py`**

Modifica a função (linhas ~537-580):

```python
def _check_fragment_staleness(root: Path) -> str | None:
    """Retorna mensagem descritiva se algum fragment plugadvpl está desatualizado.

    v0.3.23: marker `<!-- plugadvpl-fragment-version: X.Y.Z -->` em CLAUDE.md.
    v0.16.1: estende pra AGENTS.md.
    v0.16.2: estende pra Cursor rules (global em ~/.cursor/rules/plugadvpl.mdc
    e locais em <project>/.cursor/rules/plugadvpl-*.mdc).

    Reporta o primeiro arquivo desatualizado encontrado. None se todos OK ou
    se nenhum dos arquivos existe (caso fresh sem init ainda).
    """
    # 1. CLAUDE.md + AGENTS.md (fragment-version)
    for filename in ("CLAUDE.md", "AGENTS.md"):
        target = root / filename
        if not target.exists():
            continue
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _CLAUDE_FRAGMENT_BEGIN not in content or _CLAUDE_FRAGMENT_END not in content:
            continue
        start = content.index(_CLAUDE_FRAGMENT_BEGIN)
        end = content.index(_CLAUDE_FRAGMENT_END) + len(_CLAUDE_FRAGMENT_END)
        fragment = content[start:end]
        m = _CLAUDE_FRAGMENT_VERSION_MARKER_RE.search(fragment)
        if m is None:
            return f"{filename} é de versão pré-v0.3.23 (sem marker de versionamento)"
        fragment_version = m.group(1)
        if fragment_version != __version__:
            return f"{filename} foi gerado por plugadvpl {fragment_version}"

    # 2. Cursor rules (rule-version)
    cursor_files: list[Path] = []
    try:
        home_global = Path.home() / ".cursor" / "rules" / "plugadvpl.mdc"
        if home_global.exists():
            cursor_files.append(home_global)
    except RuntimeError:
        pass
    local_rules_dir = root / ".cursor" / "rules"
    if local_rules_dir.exists():
        cursor_files.extend(sorted(local_rules_dir.glob("plugadvpl-*.mdc")))

    rule_marker_re = re.compile(
        r"<!--\s*plugadvpl-rule-version:\s*(\d+\.\d+\.\d+[\w.+-]*)\s*-->"
    )
    for cf in cursor_files:
        try:
            content = cf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = rule_marker_re.search(content)
        if m is None:
            continue  # arquivo sem marker — não é nosso, skip
        rule_version = m.group(1)
        if rule_version != __version__:
            return f"{cf.name} foi gerado por plugadvpl {rule_version}"

    return None
```

- [ ] **Step 4: Rode pra verificar GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestStatus -v --no-cov`

Expected: 2 passed novos + suite TestStatus inteira verde.

Run também: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov`

Expected: full suite verde (~1090 testes).

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cli.py cli/tests/integration/test_cli.py
git commit -m "feat(status): detecta Cursor rules desatualizadas (global + locais)

Estende _check_fragment_staleness pra cobrir:
- ~/.cursor/rules/plugadvpl.mdc (global)
- <project>/.cursor/rules/plugadvpl-*.mdc (locais)

Reporta primeiro arquivo desatualizado. Marker rule-version: X.Y.Z
(mesmo padrão de fragment-version do CLAUDE.md).

2 testes integration TestStatus cobrindo global stale + local stale.
Spec §6.2"
```

---

## Chunk 7: Release v0.16.2

### Task 13: Bump version + skills + manifests

**Files:**
- Modify: `.claude-plugin/plugin.json` (bump 0.16.1 → 0.16.2)
- Modify: `.claude-plugin/marketplace.json` (bump 0.16.1 → 0.16.2)
- Modify: `skills/*/SKILL.md` × 26 (bump `uvx plugadvpl@0.16.1` → `@0.16.2`)

- [ ] **Step 1: Bump manifests via Edit**

Em `.claude-plugin/plugin.json` linha 3: `"version": "0.16.1"` → `"0.16.2"`.
Em `.claude-plugin/marketplace.json` linha 15: `"version": "0.16.1"` → `"0.16.2"`.

- [ ] **Step 2: Bump das 26 skills via script Python**

Cria `d:\tmp\bump_skills_v0162.py`:

```python
from pathlib import Path
OLD = "plugadvpl@0.16.1"; NEW = "plugadvpl@0.16.2"
skills_root = Path("d:/IA/Projetos/plugadvpl/skills")
n = 0
for p in skills_root.rglob("SKILL.md"):
    raw = p.read_bytes()
    if OLD.encode() in raw:
        p.write_bytes(raw.replace(OLD.encode(), NEW.encode()))
        n += 1
print(f"{n} skill(s) bumped")
```

Run: `& "C:\Users\jonil\AppData\Local\Programs\Python\Python312\python.exe" d:\tmp\bump_skills_v0162.py`

Expected: `26 skill(s) bumped`

- [ ] **Step 3: Verifica suite full antes do commit**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov`

Expected: ~1097 passed, 0 failed.

- [ ] **Step 4: Commit (será parte do commit de release na Task 15)**

NÃO commitar isoladamente — agrega na Task 15.

---

### Task 14: CHANGELOG + README

**Files:**
- Modify: `CHANGELOG.md` (entry [0.16.2])
- Modify: `README.md` (entry v0.16.2 + quick start touch)

- [ ] **Step 1: Adiciona entry no CHANGELOG**

Em `CHANGELOG.md`, após `## [Unreleased]` (linha ~5):

```markdown
## [0.16.2] - 2026-05-29

### Added — Cursor Rules nativos no `plugadvpl init`

`plugadvpl init` agora detecta Cursor instalado (via `~/.cursor/` no home ou `.cursor/` no projeto) e gera:

- **1 rule global** em `~/.cursor/rules/plugadvpl.mdc` (`alwaysApply: true`) — convenções ADVPL/TLPP, encoding cp1252, tabela de decisão, comandos `uvx`.
- **26 rules locais** em `.cursor/rules/plugadvpl-<skill>.mdc` — uma por skill embarcada, com `globs` específico por contexto (ex: `plugadvpl-arch.mdc` aplica em `**/*.prw,**/*.tlpp,**/*.prx,**/*.apw`; `plugadvpl-ini-audit.mdc` em `**/*.ini`).

Single source: as 26 rules são geradas em runtime a partir das `skills/<X>/SKILL.md` embarcadas no wheel (mesma fonte que Claude Code consome). 2 substituições simples: `/plugadvpl:<X>` → `` `Bash: uvx plugadvpl@0.16.2 <X>` `` e normalização de versão antiga.

Marker `<!-- plugadvpl-rule-version: X.Y.Z -->` controla idempotência: regen sobrescreve só arquivos nossos (com marker); arquivos do usuário com nome conflitante são preservados com warning. `plugadvpl status` detecta rules desatualizadas igual ao fragment do CLAUDE.md.

**Flag:** `plugadvpl init --no-cursor` desabilita mesmo com sinais presentes (CI/usuários que não querem).

**Garantia:** falha de I/O em rules nunca quebra `init` — Cursor é secundário (silent fail + warning informativo). Exit code do init nunca muda por causa disso.

Predecessor: v0.16.1 entregou AGENTS.md gêmeo (Codex). v0.16.2 completa Fase 1 do multi-agente focando em Cursor com integração nativa via formato MDC.

### Added — `plugadvpl.cursor_rules` módulo

Novo módulo isolado com:
- `CursorTarget` + `InstallResult` dataclasses
- `detect_cursor()` — política conservadora
- `render_global_rule()` + `render_skill_rule()` — geradores puros
- `_SKILL_GLOBS` — mapping canônico (26 entradas; dobra como source-of-truth da lista de skills)
- `install_cursor_rules()` — orquestrador top-level
- `_write_rule()` — política de marker

~250 linhas, stdlib only (sem deps novas).

### Changed — `_check_fragment_staleness()` cobre Cursor rules

`plugadvpl status` agora detecta fragment desatualizado em:
- `CLAUDE.md` (já cobria)
- `AGENTS.md` (v0.16.1)
- `~/.cursor/rules/plugadvpl.mdc` (novo)
- `<project>/.cursor/rules/plugadvpl-*.mdc` (novo)

### Added — 34 testes novos (TDD)

- 8 unit em `TestRenderSkillRule` (parse frontmatter, substituições, frontmatter MDC, markers, fallback)
- 2 unit em `TestRenderGlobalRule` (`alwaysApply: true`, sem globs)
- 6 unit em `TestDetectCursor` (sinais + cross-platform + RuntimeError)
- 3 unit em `TestWriteRule` (WRITTEN/OVERWRITTEN/SKIPPED_USER_FILE)
- 2 unit em `TestInstallCursorRules` (smoke end-to-end + no-op)
- 2 unit em `TestSkillGlobs` (26 entradas + paridade com skills/)
- 9 integration em `TestInitCursorRules` (init real com mocks)
- 2 integration em `TestStatus` (stale global + stale local)

Suite full: 1063 → ~1097 passed.

### Bumped

- `uvx plugadvpl@0.16.1` → `uvx plugadvpl@0.16.2` nas 26 skills.
- `plugin.json` / `marketplace.json` → 0.16.2.
```

- [ ] **Step 2: Adiciona entry no README**

Em `README.md`, antes de `### v0.16.1 — Suporte multi-agente via AGENTS.md gêmeo`:

```markdown
### v0.16.2 — Cursor Rules nativos no `init`

- **`plugadvpl init` agora detecta Cursor instalado** e gera `~/.cursor/rules/plugadvpl.mdc` (global, convenções ADVPL) + 26 `.cursor/rules/plugadvpl-<X>.mdc` (locais, uma por skill com `globs` específico)
- Single source: rules geradas em runtime a partir das `SKILL.md` embarcadas — `/plugadvpl:X` slash vira ``` `Bash: uvx plugadvpl@0.16.2 X` ``` no Cursor
- Idempotente via marker `<!-- plugadvpl-rule-version: X.Y.Z -->`; preserva rules com nome conflitante do user (warning)
- Flag `--no-cursor` desabilita; falha de I/O nunca quebra init (Cursor é secundário)
- `plugadvpl status` detecta rule desatualizada (global ou local)
- 34 testes novos (TDD). Suite full: ~1097 passed
```

Em `README.md` "Quick start", linha ~224, troca:

```markdown
/plugadvpl:init      # cria .plugadvpl/index.db, fragments CLAUDE.md + AGENTS.md, .gitignore
```

por:

```markdown
/plugadvpl:init      # cria .plugadvpl/index.db, fragments CLAUDE.md + AGENTS.md, .gitignore (+ Cursor rules se detectado)
```

- [ ] **Step 3: Commit (também agregado no commit de release da Task 15)**

NÃO commitar isoladamente.

---

### Task 15: Release v0.16.2 — commit + tag + push

**Files:** todos os modificados nas tasks 13 + 14 (já em working tree).

- [ ] **Step 1: Verifica suite full + ruff format**

Run:
```powershell
Set-Location d:\IA\Projetos\plugadvpl\cli
& .venv\Scripts\python.exe -m pytest tests -q --no-cov
```
Expected: ~1097 passed, 0 failed.

Run:
```powershell
& .venv\Scripts\python.exe -m ruff format --check plugadvpl\cli.py plugadvpl\cursor_rules.py
```
Expected: `2 files already formatted`. Se reclamar, roda `& .venv\Scripts\python.exe -m ruff format plugadvpl\cli.py plugadvpl\cursor_rules.py`.

- [ ] **Step 2: git status + diff sanidade**

Run: `git status --short`

Expected:
```
 M .claude-plugin/marketplace.json
 M .claude-plugin/plugin.json
 M CHANGELOG.md
 M README.md
 M skills/<26>/SKILL.md (cada um)
```

Confirma que NÃO sobrou mudança não-relacionada.

- [ ] **Step 3: Commit release agregado**

```bash
cd /d/IA/Projetos/plugadvpl
git add -u
git commit -m "release: v0.16.2 — Cursor Rules nativos no plugadvpl init

Bump 0.16.1 -> 0.16.2 (patch — adicao compativel).

plugadvpl init agora detecta Cursor instalado (via ~/.cursor/ no home
ou .cursor/ no projeto) e gera:
- 1 rule global em ~/.cursor/rules/plugadvpl.mdc (alwaysApply: true) —
  convencoes ADVPL/TLPP, encoding cp1252, tabela de decisao, uvx
- 26 rules locais em .cursor/rules/plugadvpl-<X>.mdc — uma por skill
  embarcada com globs especifico por contexto

Single source: rules geradas em runtime a partir das skills/<X>/SKILL.md
embarcadas no wheel. 2 substituicoes: /plugadvpl:<X> -> uvx ... e
normalizacao de versao.

Marker plugadvpl-rule-version: X.Y.Z controla idempotencia. Falha de
I/O nunca quebra init — Cursor e secundario.

Mudancas:
- cli/plugadvpl/cursor_rules.py: modulo novo ~250 linhas (detect/render/
  install/_SKILL_GLOBS/WriteOutcome/InstallResult)
- cli/plugadvpl/cli.py: init() ganha flag --no-cursor + chamada install;
  _check_fragment_staleness cobre Cursor rules
- 34 testes novos TDD (8 render_skill + 2 render_global + 6 detect +
  3 write + 2 install + 2 skill_globs + 9 init integration + 2 status)

Updates:
- plugin.json / marketplace.json -> 0.16.2
- uvx plugadvpl@0.16.1 -> @0.16.2 nas 26 skills
- CHANGELOG.md + README.md (secao v0.16.2)

Suite full: ~1097 passed.

Spec: docs/superpowers/specs/2026-05-29-cursor-rules-design.md
Plan: docs/superpowers/plans/2026-05-29-cursor-rules-implementation.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Tag anotada + push**

```bash
git tag -a v0.16.2 -m "v0.16.2 — Cursor Rules nativos no plugadvpl init

plugadvpl init agora detecta Cursor e gera ~/.cursor/rules/plugadvpl.mdc
(global) + 26 .cursor/rules/plugadvpl-<X>.mdc (locais) com glob por
contexto. Single source via SKILL.md embarcadas. Marker controla
idempotencia. Flag --no-cursor desabilita.

Suite full: ~1097 passed.

Spec: docs/superpowers/specs/2026-05-29-cursor-rules-design.md"

git push && git push --tags
```

- [ ] **Step 5: Monitora CI + release workflow**

```bash
sleep 15 && gh run list --branch main --limit 2 --json status,name,databaseId,displayTitle
```

Pega o `databaseId` do run de CI e:

```bash
gh run watch <ID-CI> --interval 20 --exit-status
```

Expected:
- CI 13 jobs todos green (test-cli cross-platform + lint-plugin + lint-code + bench + smoke-uvx + codeql)
- Release workflow disparado pela tag → publish-pypi + verify-pypi + github-release

- [ ] **Step 6: Verifica release no PyPI + GitHub**

```bash
gh release view v0.16.2 --json name,publishedAt,url,assets --jq '{name, publishedAt, url, assets: [.assets[].name]}'
```

Expected: assets `plugadvpl-0.16.2-py3-none-any.whl` + `plugadvpl-0.16.2.tar.gz`.

- [ ] **Step 7: Smoke real opcional**

Run no próprio repo:
```bash
mkdir -p /tmp/cursor_smoke_test && cd /tmp/cursor_smoke_test && mkdir .cursor && uvx --refresh plugadvpl@0.16.2 init
```

Expected:
```
OK  DB criado em ./.plugadvpl/index.db
OK  CLAUDE.md + AGENTS.md atualizados (fragment plugadvpl, idênticos)
OK  .plugadvpl/ adicionado ao .gitignore
OK  Cursor rules: 26 locais instaladas
```

E `ls .cursor/rules/ | wc -l` → 26.

---

## Resumo da execução esperada

| Chunk | Tasks | Linhas adicionadas |
|---|---|---|
| 1: Detecção | 1 | ~120 |
| 2: render_skill_rule | 3 | ~200 |
| 3: render_global + _SKILL_GLOBS | 2 | ~130 |
| 4: _write_rule + install | 2 | ~150 |
| 5: Init integration | 3 | ~250 |
| 6: Status staleness | 1 | ~80 |
| 7: Release | 3 | ~100 (CHANGELOG/README) |
| **Total** | **15** | **~1030** |

**Estimativa de tempo:** ~4-6 horas de execução focada com TDD rigoroso.

**Critério final:** `gh release view v0.16.2` mostra release publicado + PyPI tem `plugadvpl 0.16.2` + smoke `uvx plugadvpl@0.16.2 init` num projeto com `.cursor/` cria as 26 rules.

---

## Notas pra quem executar

1. **Não pule TDD.** Mesmo em "tasks mecânicas" (Task 13 bump), rode suite completa antes do commit pra catch regressões cedo.
2. **Fixture isolada de `Path.home`** (Task 9 Step 5) é crítica — sem isso, suite local do dev rodaria escrevendo no `~/.cursor/` real do dev. Aplica `autouse=True` no `TestInit` E `TestInitCursorRules`.
3. **Erros de `importlib.resources`** (Task 8 Step 4): se aparecer no dev tree, use abordagem alternativa via `Path(__file__).resolve().parents[N] / "skills"` — em dev tree o caminho é determinístico.
4. **CI Node 20 deprecation** (próximo backlog item) é separado deste plan — NÃO inclui aqui.
5. **Memória do projeto** ([feedback_powershell_utf8_bom](C:/Users/jonil/.claude/projects/d--IA-Projetos-plugadvpl/memory/feedback_powershell_utf8_bom.md)): bumps de skill via Python script com `read_bytes`/`write_bytes` (evita BOM do PowerShell).
6. **Memória** ([reference_plugadvpl_release_gotchas](C:/Users/jonil/.claude/projects/d--IA-Projetos-plugadvpl/memory/reference_plugadvpl_release_gotchas.md)): sempre `git tag -a` anotada; suite full sem `--ignore` antes de release.
