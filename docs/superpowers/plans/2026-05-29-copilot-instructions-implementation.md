# Copilot Instructions no `plugadvpl init` — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `plugadvpl init` detecta `.github/` no projeto e gera `.github/copilot-instructions.md` (global, repo-wide) + 52 `.github/instructions/plugadvpl-<X>.instructions.md` (locais com `applyTo` glob) derivadas das `SKILL.md` embarcadas.

**Architecture:** Refactor first: extrai helpers neutros de `cursor_rules.py` pra novo `_skill_catalog.py` (DRY pra multi-agente). Depois cria `copilot_instructions.py` espelhando `cursor_rules.py` mas com formato Copilot (`applyTo` string, sem `alwaysApply`, marker `instructions-version`). `init()` ganha flag `--no-copilot` + chamada após `install_cursor_rules`. `_check_fragment_staleness` estende com 3ª passada.

**Tech Stack:** Python 3.11+ (stdlib only — `pathlib`, `re`, `dataclasses`, `enum`, `importlib.resources`). Typer (existente). pytest + monkeypatch + `CliRunner`. Sem deps novas.

**Spec:** [`docs/superpowers/specs/2026-05-29-copilot-instructions-design.md`](../specs/2026-05-29-copilot-instructions-design.md)

---

## File Structure

**Arquivos novos:**
- `cli/plugadvpl/_skill_catalog.py` (~150 linhas) — extraído de cursor_rules: `_SKILL_GLOBS`, `_parse_skill_md`, `_transform_body`, `_skills_root`, `WriteOutcome`, `_write_managed_file`, `RULE_MARKER_PREFIX`, `INSTRUCTIONS_MARKER_PREFIX`, regex constants
- `cli/plugadvpl/copilot_instructions.py` (~200 linhas) — `CopilotTarget`, `detect_copilot`, `_GLOBAL_BODY_TEMPLATE`, `render_global_instructions`, `render_skill_instructions`, `InstallResult`, `install_copilot_instructions`
- `cli/tests/unit/test_skill_catalog.py` (~200 linhas) — testes movidos de test_cursor_rules.py + 1 novo
- `cli/tests/unit/test_copilot_instructions.py` (~250 linhas) — 11 unit tests

**Arquivos modificados:**
- `cli/plugadvpl/cursor_rules.py` — remove helpers movidos, importa do `_skill_catalog`, ajusta callers de `_write_rule` → `_write_managed_file(..., RULE_MARKER_PREFIX)`
- `cli/plugadvpl/cli.py` — `init()` ganha flag `--no-copilot` + chamada `install_copilot_instructions`; `_check_fragment_staleness` ganha 3ª passada
- `cli/tests/unit/test_cursor_rules.py` — remove testes movidos (TestSkillGlobs, TestRenderSkillRule parts? No — apenas helpers movidos), atualiza imports
- `cli/tests/integration/test_cli.py` — adiciona `TestInitCopilotInstructions` (6 tests) + 2 tests em TestStatus
- `.claude-plugin/plugin.json` + `marketplace.json` — bump 0.16.2 → 0.16.3
- `skills/*/SKILL.md` × N — bump `uvx plugadvpl@0.16.2` → `@0.16.3`
- `CHANGELOG.md` — entrada [0.16.3]
- `README.md` — entrada v0.16.3 no histórico + ajuste no Quick start

**Decisão Opção A vs B (TestWriteRule rename):** Plano usa **Opção A** — atualizar 3 testes em test_cursor_rules.py pra importar `_write_managed_file` de `_skill_catalog` e passar `marker_substring=RULE_MARKER_PREFIX`. Mais explícito, documenta a policy.

---

## Chunk 1: Refactor — extrai `_skill_catalog.py` (mantém Cursor verde)

### Task 1: Cria `_skill_catalog.py` com helpers movidos + 2 prefixos

**Files:**
- Create: `cli/plugadvpl/_skill_catalog.py`
- Modify: `cli/plugadvpl/cursor_rules.py` (remove movidos, importa)
- Modify: `cli/tests/unit/test_cursor_rules.py` (atualiza imports + path-mocks)
- Create: `cli/tests/unit/test_skill_catalog.py`

- [ ] **Step 1: Cria `cli/plugadvpl/_skill_catalog.py` com TODO o conteúdo neutro**

Conteúdo exato:

```python
"""Skill catalog + helpers neutros — compartilhados entre cursor_rules e
copilot_instructions (v0.16.3+).

Fonte canônica de:
- `_SKILL_GLOBS`: dict[str, list[str]] com 52 skills + seus globs
- Regex constants (frontmatter, description, slash, uvx version)
- Helpers puros: `_parse_skill_md`, `_transform_body`, `_skills_root`
- `WriteOutcome` enum + `_write_managed_file` (idempotência via marker)
- `RULE_MARKER_PREFIX` (Cursor) e `INSTRUCTIONS_MARKER_PREFIX` (Copilot) — DISTINTOS
  pra evitar falso-positivo entre os 2 agentes
"""
from __future__ import annotations

import enum
import re
from importlib import resources as ir
from pathlib import Path

# ---------------------------------------------------------------------------
# Marker prefixes — narrow por agente (NÃO unificar; spec §3.1)
# ---------------------------------------------------------------------------

RULE_MARKER_PREFIX = "<!-- plugadvpl-rule-version:"
INSTRUCTIONS_MARKER_PREFIX = "<!-- plugadvpl-instructions-version:"

# ---------------------------------------------------------------------------
# Skill catalog (spec §5)
# ---------------------------------------------------------------------------

_PRW = ["**/*.prw", "**/*.tlpp", "**/*.prx", "**/*.apw"]
_PRW_CSV = ["**/*.prw", "**/*.tlpp", "**/*.prx", "**/*.csv"]

_SKILL_GLOBS: dict[str, list[str]] = {
    # ADVPL/TLPP source skills
    "arch": _PRW,
    "find": _PRW,
    "callers": _PRW,
    "callees": _PRW,
    "lint": _PRW,
    "grep": _PRW,
    "compile": _PRW,
    "tq": _PRW,
    "edit-prw": _PRW,
    "deploy": _PRW,
    "hotspots": _PRW,
    "metrics": _PRW,
    "cobertura-doc": _PRW,
    "plugadvpl-index-usage": _PRW,
    # Knowledge / reference skills
    "advpl-advanced": _PRW,
    "advpl-code-review": _PRW,
    "advpl-debugging": _PRW,
    "advpl-dicionario-sx": _PRW,
    "advpl-dicionario-sx-validacoes": _PRW,
    "advpl-embedded-sql": _PRW,
    "advpl-encoding": _PRW,
    "advpl-fundamentals": _PRW,
    "advpl-jobs-rpc": _PRW,
    "advpl-matxfis": _PRW,
    "advpl-mvc": _PRW,
    "advpl-mvc-avancado": _PRW,
    "advpl-pontos-entrada": _PRW,
    "advpl-refactoring": _PRW,
    "advpl-tlpp": _PRW,
    "advpl-tlpp-named-params": _PRW,
    "advpl-web": _PRW,
    "advpl-webservice": _PRW,
    # SX dictionary skills (incluindo CSV)
    "tables": _PRW_CSV,
    "param": _PRW_CSV,
    "impacto": _PRW_CSV,
    "gatilho": _PRW_CSV,
    "ingest-sx": _PRW_CSV,
    "sx-status": _PRW_CSV,
    # Contexto específico
    "ini-audit": ["**/*.ini"],
    "log-diagnose": ["**/*.log"],
    # Meta-skills — sem escopo (consumer decide fallback: '**/*' pro Copilot, vazio pro Cursor)
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

# ---------------------------------------------------------------------------
# Frontmatter / body parsing
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Body transformations (slash → uvx + version normalize)
# ---------------------------------------------------------------------------

_SLASH_RE = re.compile(r"/plugadvpl:([a-z0-9-]+)")
_UVX_VER_RE = re.compile(r"uvx plugadvpl@[\w.+-]+")


def _transform_body(body: str, version: str) -> str:
    """Aplica 2 substituições, NESTA ORDEM:

    3a) `/plugadvpl:<X>` → `` `Bash: uvx plugadvpl@<ver> <X>` ``
    3b) `uvx plugadvpl@<qualquer>` → `uvx plugadvpl@<ver>`

    Ordem importa: 3a primeiro emite uvx correto; 3b depois normaliza.
    """
    body = _SLASH_RE.sub(rf"`Bash: uvx plugadvpl@{version} \1`", body)
    body = _UVX_VER_RE.sub(f"uvx plugadvpl@{version}", body)
    return body


# ---------------------------------------------------------------------------
# Skills directory resolution (dev tree vs wheel)
# ---------------------------------------------------------------------------


def _skills_root() -> Path:
    """Localiza skills/ tanto em dev tree quanto em wheel.

    Tenta importlib.resources primeiro; se a skill embarcada não existir
    (caso: dev tree onde skills/ não é packaged), cai pro repo root
    relativo ao __init__.py do plugadvpl.
    """
    try:
        test = ir.files("plugadvpl") / "skills"
        with ir.as_file(test) as resolved:
            if (resolved / "arch" / "SKILL.md").exists():
                return resolved
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        pass
    # Fallback dev tree
    import plugadvpl
    pkg_init = Path(plugadvpl.__file__).resolve()
    return pkg_init.parents[2] / "skills"


# ---------------------------------------------------------------------------
# File write policy (idempotência via marker)
# ---------------------------------------------------------------------------


class WriteOutcome(enum.Enum):
    """Resultado de tentar escrever um arquivo gerenciado."""

    WRITTEN = "written"
    OVERWRITTEN = "overwritten"
    SKIPPED_USER_FILE = "skipped_user_file"
    ERROR = "error"


def _write_managed_file(
    target_path: Path, content: str, marker_substring: str
) -> WriteOutcome:
    """Escreve ou skipa um arquivo seguindo a política de marker (spec §6.1).

    - Não existe → escreve (WRITTEN).
    - Existe + contém `marker_substring` → sobrescreve (OVERWRITTEN).
    - Existe sem marker → skipa (SKIPPED_USER_FILE), preserva arquivo.
    - PermissionError/OSError → ERROR.

    `marker_substring` é OBRIGATÓRIO (sem default) — caller passa
    `RULE_MARKER_PREFIX` (Cursor) ou `INSTRUCTIONS_MARKER_PREFIX` (Copilot).
    Distinto por agente evita falso-positivo (`<!-- plugadvpl-skill: -->`
    em body não confunde com marker de versão).
    """
    try:
        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            return WriteOutcome.WRITTEN
        existing = target_path.read_text(encoding="utf-8", errors="replace")
        if marker_substring in existing:
            target_path.write_text(content, encoding="utf-8")
            return WriteOutcome.OVERWRITTEN
        return WriteOutcome.SKIPPED_USER_FILE
    except OSError:
        return WriteOutcome.ERROR
```

- [ ] **Step 2: Remove os blocos movidos de `cli/plugadvpl/cursor_rules.py`**

Em `cli/plugadvpl/cursor_rules.py`, **DELETE** os seguintes blocos (porque agora vivem em `_skill_catalog.py`):

- Linha do `import enum` (não é mais necessário aqui — fica em `_skill_catalog`)
- O `_MARKER_PREFIX = "<!-- plugadvpl-rule-version:"` constante (substitui por import)
- Bloco `_FRONTMATTER_RE` + `_DESC_RE`
- Função `_parse_skill_md`
- Bloco `_SLASH_RE` + `_UVX_VER_RE` + função `_transform_body`
- Constantes `_PRW` + `_PRW_CSV` + dict inteiro `_SKILL_GLOBS`
- Função `_skills_root`
- Classe `WriteOutcome` + função `_write_rule`

**ADD** no topo do arquivo (após `from __future__ import annotations`):

```python
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from plugadvpl._skill_catalog import (
    RULE_MARKER_PREFIX,
    WriteOutcome,
    _parse_skill_md,
    _skills_root,
    _SKILL_GLOBS,
    _transform_body,
    _write_managed_file,
)
```

(Mantenha os imports `from importlib import resources as ir` se ainda forem usados — checar callers de `ir.files(...)` no `install_cursor_rules`. O `_skills_root` agora é usado via import, mas o `install_cursor_rules` pode ainda usar `ir.as_file()` no loop — verificar.)

- [ ] **Step 3: Atualiza calls a `_write_rule` → `_write_managed_file(..., RULE_MARKER_PREFIX)` em `cursor_rules.py`**

Em `cli/plugadvpl/cursor_rules.py`, find todas as chamadas `_write_rule(target_path, content)` e substitui por:

```python
_write_managed_file(target_path, content, RULE_MARKER_PREFIX)
```

Tipicamente 2 ocorrências: 1 dentro de `install_cursor_rules` pro global path, 1 dentro do loop de skills.

- [ ] **Step 4: Cria `cli/tests/unit/test_skill_catalog.py` com testes movidos + 1 novo**

```python
"""Unit tests for plugadvpl/_skill_catalog.py (refactor v0.16.3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl._skill_catalog import (
    INSTRUCTIONS_MARKER_PREFIX,
    RULE_MARKER_PREFIX,
    WriteOutcome,
    _parse_skill_md,
    _skills_root,
    _SKILL_GLOBS,
    _transform_body,
    _write_managed_file,
)


class TestSkillGlobs:
    def test_has_52_skills(self) -> None:
        assert len(_SKILL_GLOBS) == 52

    def test_matches_actual_skill_dirs(self) -> None:
        """_SKILL_GLOBS deve bater com as skills embarcadas em skills/."""
        skills_dir = Path(__file__).resolve().parents[3] / "skills"
        if not skills_dir.exists():
            pytest.skip("dev tree only — skills/ não acessível neste contexto")
        actual = {p.name for p in skills_dir.iterdir() if (p / "SKILL.md").exists()}
        catalogued = set(_SKILL_GLOBS.keys())
        missing = actual - catalogued
        extras = catalogued - actual
        assert not missing, f"Skills sem entrada em _SKILL_GLOBS: {missing}"
        assert not extras, f"_SKILL_GLOBS tem entries inexistentes: {extras}"


class TestParseSkillMd:
    def test_extracts_description_from_frontmatter(self, tmp_path: Path) -> None:
        text = (
            "---\n"
            "description: Visao arquitetural de um arquivo ADVPL/TLPP\n"
            "arguments: [arquivo]\n"
            "---\n"
            "# Body\n"
        )
        desc, body = _parse_skill_md(text)
        assert desc == "Visao arquitetural de um arquivo ADVPL/TLPP"
        assert body == "# Body\n"

    def test_falls_back_when_no_frontmatter(self) -> None:
        text = "# Body only, no frontmatter\n"
        desc, body = _parse_skill_md(text)
        assert desc == ""
        assert body == text


class TestTransformBody:
    def test_substitutes_slash_to_uvx(self) -> None:
        body = "Use `/plugadvpl:arch <arq>` antes de Read.\n"
        result = _transform_body(body, version="0.16.3")
        assert "`Bash: uvx plugadvpl@0.16.3 arch`" in result
        assert "/plugadvpl:arch" not in result

    def test_normalizes_old_uvx_version(self) -> None:
        body = "```bash\nuvx plugadvpl@0.15.0 --format md arch $arquivo\n```\n"
        result = _transform_body(body, version="0.16.3")
        assert "uvx plugadvpl@0.16.3" in result
        assert "uvx plugadvpl@0.15.0" not in result


class TestWriteManagedFile:
    def test_writes_when_not_exists(self, tmp_path: Path) -> None:
        target = tmp_path / "plugadvpl-arch.mdc"
        outcome = _write_managed_file(
            target,
            "content with <!-- plugadvpl-rule-version: 0.16.3 -->",
            RULE_MARKER_PREFIX,
        )
        assert outcome == WriteOutcome.WRITTEN
        assert target.read_text(encoding="utf-8").startswith("content")

    def test_overwrites_when_rule_marker_present(self, tmp_path: Path) -> None:
        target = tmp_path / "plugadvpl-arch.mdc"
        target.write_text(
            "old <!-- plugadvpl-rule-version: 0.15.0 -->", encoding="utf-8"
        )
        outcome = _write_managed_file(
            target,
            "new <!-- plugadvpl-rule-version: 0.16.3 -->",
            RULE_MARKER_PREFIX,
        )
        assert outcome == WriteOutcome.OVERWRITTEN
        assert "new" in target.read_text(encoding="utf-8")

    def test_skips_when_user_file_without_marker(self, tmp_path: Path) -> None:
        target = tmp_path / "plugadvpl-meu.mdc"
        target.write_text("my own rule, no marker", encoding="utf-8")
        outcome = _write_managed_file(
            target, "new content", RULE_MARKER_PREFIX
        )
        assert outcome == WriteOutcome.SKIPPED_USER_FILE
        assert target.read_text(encoding="utf-8") == "my own rule, no marker"

    def test_distinct_marker_does_not_match_other_agent(self, tmp_path: Path) -> None:
        """v0.16.3 — marker do Cursor (rule-version) não matcha policy do Copilot
        (instructions-version), evitando overwrite cross-agent."""
        target = tmp_path / "plugadvpl-arch.mdc"
        target.write_text(
            "cursor file <!-- plugadvpl-rule-version: 0.16.3 -->",
            encoding="utf-8",
        )
        # Tenta sobrescrever como se fosse arquivo Copilot
        outcome = _write_managed_file(
            target, "would overwrite", INSTRUCTIONS_MARKER_PREFIX
        )
        assert outcome == WriteOutcome.SKIPPED_USER_FILE
        # Preserva original — não confundiu os 2 markers
        assert "cursor file" in target.read_text(encoding="utf-8")
```

- [ ] **Step 5: Atualiza `cli/tests/unit/test_cursor_rules.py`**

Find `class TestSkillGlobs` (deve estar lá ainda) e REMOVE inteiramente (foi movida pra test_skill_catalog).

Find `class TestParseSkillMd` se existir lá — REMOVE (movida).

Find `class TestTransformBody` se existir — REMOVE (não tinha como classe, eram tests dentro de `TestRenderSkillRule`; deixa como estão — `render_skill_rule` ainda existe em cursor_rules).

Find `class TestWriteRule` — RENAME e REWRITE pra usar `_write_managed_file(..., RULE_MARKER_PREFIX)`:

```python
class TestWriteRuleCursorFacade:
    """Tests que cursor_rules.py ainda exporta corretamente — facade test.

    A lógica real está em test_skill_catalog.TestWriteManagedFile; aqui só
    garantimos que cursor_rules.py ainda permite acesso ao helper (via re-export
    ou import) e que callers internos do install_cursor_rules continuam funcionando.
    """
    def test_write_managed_file_is_importable_from_skill_catalog(self) -> None:
        from plugadvpl._skill_catalog import _write_managed_file, RULE_MARKER_PREFIX
        # Sanity import — testes detalhados em test_skill_catalog
        assert callable(_write_managed_file)
        assert RULE_MARKER_PREFIX.startswith("<!-- plugadvpl-rule-version")
```

OR (simpler — recomendado): **DELETE** `TestWriteRule` inteiramente (testes movidos pra test_skill_catalog.TestWriteManagedFile que tem cobertura equivalente + 1 a mais).

Outros tests em test_cursor_rules.py (TestDetectCursor, TestRenderSkillRule, TestRenderGlobalRule, TestInstallCursorRules) — mantém intactos. Eles testam comportamento de cursor_rules direto, não dos helpers movidos.

- [ ] **Step 6: Run tests refactor**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_skill_catalog.py tests/unit/test_cursor_rules.py -v --no-cov`

Expected: TestSkillCatalog tests pass (10) + remaining test_cursor_rules tests pass.

Run full suite:

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov`

Expected: 1097 - 3 (TestWriteRule removidos) + 10 (test_skill_catalog) = 1104 passed.

**If anything fails:** likely import cycle or missed call site. Read traceback carefully and check:
1. Did `cursor_rules.py` import all needed helpers?
2. Did integration tests in `test_cli.py` that monkeypatch `plugadvpl.cursor_rules.shutil.which` still work? (shutil stays in cursor_rules; OK)
3. Did `install_cursor_rules` still call `_write_managed_file` with correct prefix?

- [ ] **Step 7: Commit refactor**

```bash
git add cli/plugadvpl/_skill_catalog.py cli/plugadvpl/cursor_rules.py cli/tests/unit/test_skill_catalog.py cli/tests/unit/test_cursor_rules.py
git commit -m "refactor(cursor): extrai _skill_catalog.py compartilhado pra multi-agente

Move helpers neutros de cursor_rules.py pra cli/plugadvpl/_skill_catalog.py:
- _SKILL_GLOBS dict (52 skills + globs)
- _parse_skill_md, _transform_body, _skills_root
- WriteOutcome enum + _write_managed_file (renomeado de _write_rule)
- RULE_MARKER_PREFIX, INSTRUCTIONS_MARKER_PREFIX — DISTINTOS por agente

cursor_rules.py importa do _skill_catalog. Callers de _write_rule
substituidos por _write_managed_file(..., RULE_MARKER_PREFIX).

Tests movidos de test_cursor_rules.py pra test_skill_catalog.py.
+1 teste novo (test_distinct_marker_does_not_match_other_agent) garante
isolamento entre Cursor (rule-version) e Copilot (instructions-version)
markers.

Suite full: 1104 passed.

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md secao 3.1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: copilot_instructions.py — detect + render

### Task 2: `CopilotTarget` + `detect_copilot`

**Files:**
- Create: `cli/plugadvpl/copilot_instructions.py`
- Create: `cli/tests/unit/test_copilot_instructions.py`

- [ ] **Step 1: Cria test file com 2 RED tests**

`cli/tests/unit/test_copilot_instructions.py`:

```python
"""Unit tests for plugadvpl/copilot_instructions.py (v0.16.3+)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.copilot_instructions import CopilotTarget, detect_copilot


class TestDetectCopilot:
    def test_no_github_returns_false_false(self, tmp_path: Path) -> None:
        """Projeto sem .github/ → no-op."""
        project = tmp_path / "project"
        project.mkdir()
        result = detect_copilot(project)
        assert result == CopilotTarget(install_global=False, install_local=False)

    def test_with_github_returns_both_true(self, tmp_path: Path) -> None:
        """`.github/` no projeto → instala global + locais."""
        project = tmp_path / "project"
        (project / ".github").mkdir(parents=True)
        result = detect_copilot(project)
        assert result == CopilotTarget(install_global=True, install_local=True)
```

- [ ] **Step 2: Run RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_copilot_instructions.py -v --no-cov`

Expected: `ModuleNotFoundError: No module named 'plugadvpl.copilot_instructions'`.

- [ ] **Step 3: Cria `cli/plugadvpl/copilot_instructions.py` mínimo**

```python
"""GitHub Copilot Instructions generator + installer pra plugadvpl init (v0.16.3+).

Detecta `.github/` no projeto e gera:
- `.github/copilot-instructions.md` (global, markdown plano, repo-wide)
- `.github/instructions/plugadvpl-<X>.instructions.md` (52 specifics com applyTo glob)

Fonte: skills/<X>/SKILL.md embarcadas (via _skill_catalog._SKILL_GLOBS).
Compartilha helpers com cursor_rules via plugadvpl._skill_catalog (DRY).

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CopilotTarget:
    """Decisão do detect_copilot: o que instalar."""

    install_global: bool   # .github/copilot-instructions.md
    install_local: bool    # .github/instructions/plugadvpl-*.instructions.md


def detect_copilot(project_root: Path) -> CopilotTarget:
    """Política simples: `.github/` no projeto → instala ambos.

    Menos conservador que detect_cursor — copilot-instructions.md é
    markdown inerte pra quem não usa Copilot (sem efeito colateral),
    e `.github/` é convenção amplamente adotada em projetos GitHub.
    """
    if (project_root / ".github").exists():
        return CopilotTarget(install_global=True, install_local=True)
    return CopilotTarget(install_global=False, install_local=False)
```

- [ ] **Step 4: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_copilot_instructions.py -v --no-cov`

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/copilot_instructions.py cli/tests/unit/test_copilot_instructions.py
git commit -m "feat(copilot): detect_copilot + CopilotTarget (TDD red->green)

Modulo novo cli/plugadvpl/copilot_instructions.py com:
- CopilotTarget dataclass (install_global + install_local)
- detect_copilot(project_root) decisao simples:
  .github/ no projeto -> instala ambos

Menos conservador que detect_cursor por design — copilot-instructions.md
e markdown inerte sem .github/instructions detection adicional necessaria.

2 testes unit.

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md secao 3.3

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `render_global_instructions` (global Copilot file)

**Files:**
- Modify: `cli/plugadvpl/copilot_instructions.py` (add template + render)
- Modify: `cli/tests/unit/test_copilot_instructions.py` (add `TestRenderGlobalInstructions`)

- [ ] **Step 1: Add 3 RED tests no test_copilot_instructions.py**

```python
class TestRenderGlobalInstructions:
    def test_includes_version_marker(self) -> None:
        from plugadvpl.copilot_instructions import render_global_instructions
        result = render_global_instructions(version="0.16.3")
        assert "<!-- plugadvpl-instructions-version: 0.16.3 -->" in result

    def test_no_frontmatter(self) -> None:
        """Copilot global file é markdown plano — sem frontmatter ---."""
        from plugadvpl.copilot_instructions import render_global_instructions
        result = render_global_instructions(version="0.16.3")
        # Não começa com ---
        assert not result.startswith("---\n")

    def test_substitutes_version_in_body(self) -> None:
        """Body deve ter `uvx plugadvpl@<ver>` em vez de placeholder."""
        from plugadvpl.copilot_instructions import render_global_instructions
        result = render_global_instructions(version="0.16.3")
        assert "uvx plugadvpl@0.16.3" in result
        assert "__VERSION__" not in result
```

- [ ] **Step 2: Run RED**

Expected: 3 failures (ImportError em `render_global_instructions`).

- [ ] **Step 3: Implementa template + função em copilot_instructions.py**

Adicionar ao final do módulo:

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
"""


def render_global_instructions(version: str) -> str:
    """Gera conteúdo de `.github/copilot-instructions.md` (global Copilot file).

    Markdown plano sem frontmatter (padrão Copilot). Marker de versão
    no topo. ~60 linhas no body — respeitando soft limit de ~2 páginas
    documentado pelo GitHub Copilot.
    """
    markers = f"<!-- plugadvpl-instructions-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return markers + body
```

- [ ] **Step 4: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_copilot_instructions.py -v --no-cov`

Expected: 5 passed (2 detect + 3 render_global).

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/copilot_instructions.py cli/tests/unit/test_copilot_instructions.py
git commit -m "feat(copilot): render_global_instructions pra .github/copilot-instructions.md

Markdown plano (sem frontmatter — padrao Copilot) com marker
plugadvpl-instructions-version no topo. Body ~60 linhas (respeitando
soft limit ~2 paginas do Copilot docs).

Conteudo adaptado do Cursor _GLOBAL_BODY_TEMPLATE removendo prefixo
'Bash:' dos comandos (Copilot interpreta texto direto).

3 testes unit.

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md secao 4.1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `render_skill_instructions` (specifics com applyTo)

**Files:**
- Modify: `cli/plugadvpl/copilot_instructions.py`
- Modify: `cli/tests/unit/test_copilot_instructions.py`

- [ ] **Step 1: Add 5 RED tests**

```python
class TestRenderSkillInstructions:
    def test_includes_apply_to_as_string(self, tmp_path: Path) -> None:
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_instructions(
            target, version="0.16.3", globs=["**/*.prw", "**/*.tlpp"]
        )
        # Copilot espera applyTo como string única (com vírgulas), não array YAML
        assert 'applyTo: "**/*.prw,**/*.tlpp"' in result

    def test_empty_globs_uses_wildcard(self, tmp_path: Path) -> None:
        """Meta-skills (globs=[]) → applyTo: '**/*' (aplica sempre)."""
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "init"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_instructions(target, version="0.16.3", globs=[])
        assert 'applyTo: "**/*"' in result

    def test_includes_description_from_skill_frontmatter(self, tmp_path: Path) -> None:
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: Visao arquitetural\n---\nBody\n", encoding="utf-8"
        )
        result = render_skill_instructions(target, version="0.16.3", globs=[])
        assert "description: Visao arquitetural" in result

    def test_includes_version_and_skill_markers(self, tmp_path: Path) -> None:
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "callers"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text("---\ndescription: X\n---\nBody\n", encoding="utf-8")
        result = render_skill_instructions(target, version="0.16.3", globs=[])
        assert "<!-- plugadvpl-instructions-version: 0.16.3 -->" in result
        assert "<!-- plugadvpl-skill: callers -->" in result

    def test_transforms_body_substitutions(self, tmp_path: Path) -> None:
        """Body deve passar pelas mesmas substituições do Cursor."""
        from plugadvpl.copilot_instructions import render_skill_instructions
        skill_dir = tmp_path / "arch"
        skill_dir.mkdir()
        target = skill_dir / "SKILL.md"
        target.write_text(
            "---\ndescription: X\n---\n"
            "Use `/plugadvpl:arch` antes de Read.\n",
            encoding="utf-8",
        )
        result = render_skill_instructions(target, version="0.16.3", globs=[])
        assert "`Bash: uvx plugadvpl@0.16.3 arch`" in result
        assert "/plugadvpl:arch" not in result
```

- [ ] **Step 2: Run RED**

Expected: 5 failures (ImportError).

- [ ] **Step 3: Implementa em copilot_instructions.py**

Adiciona ao módulo (depois de `render_global_instructions`):

```python
from plugadvpl._skill_catalog import _parse_skill_md, _transform_body


def render_skill_instructions(
    skill_md_path: Path, version: str, globs: list[str]
) -> str:
    """Gera `.github/instructions/plugadvpl-<skill>.instructions.md`.

    Pipeline (similar a render_skill_rule do Cursor):
    1. Parse SKILL.md frontmatter (description)
    2. Body extraction
    3. _transform_body (slash→uvx + version normalize)
    4. Monta frontmatter Copilot:
       - applyTo (STRING com globs joined por vírgula; '**/*' se vazio)
       - description
    5. Markers de versão + skill

    Edge case: SKILL.md sem frontmatter → description fallback usa skill_name.
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    # applyTo é STRING única no Copilot (Cursor usa array)
    apply_to = ",".join(globs) if globs else "**/*"

    frontmatter = (
        "---\n"
        f'applyTo: "{apply_to}"\n'
        f"description: {description}\n"
        "---\n"
    )
    markers = (
        f"<!-- plugadvpl-instructions-version: {version} -->\n"
        f"<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )
    return frontmatter + markers + _transform_body(body, version)
```

- [ ] **Step 4: Run GREEN**

Expected: 10 passed (2 detect + 3 global + 5 skill).

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/copilot_instructions.py cli/tests/unit/test_copilot_instructions.py
git commit -m "feat(copilot): render_skill_instructions com applyTo string

Frontmatter Copilot:
- applyTo: 'glob1,glob2,...' (string com virgulas, NAO array YAML)
- description: <da SKILL.md>

Quando globs=[] (meta-skills): applyTo='**/*' (aplica sempre).

Body transformations identicas ao Cursor (_transform_body do _skill_catalog).
Markers: plugadvpl-instructions-version + plugadvpl-skill.

5 testes unit cobrindo applyTo formato, fallback description, markers,
e body substituicoes.

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md secao 4.2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: install_copilot_instructions orquestrador

### Task 5: `InstallResult` + `install_copilot_instructions`

**Files:**
- Modify: `cli/plugadvpl/copilot_instructions.py`
- Modify: `cli/tests/unit/test_copilot_instructions.py`

- [ ] **Step 1: Add 1 RED test (smoke end-to-end)**

```python
class TestInstallCopilotInstructions:
    def test_installs_global_and_locals_when_github_exists(
        self, tmp_path: Path
    ) -> None:
        """`.github/` no projeto → 1 global + 52 specifics gerados."""
        from plugadvpl.copilot_instructions import install_copilot_instructions
        project = tmp_path / "project"
        (project / ".github").mkdir(parents=True)
        result = install_copilot_instructions(project, version="0.16.3")
        assert result.installed_global is True
        assert result.installed_local_count == 52
        assert not result.errors
        # Files
        assert (project / ".github" / "copilot-instructions.md").exists()
        instructions = list(
            (project / ".github" / "instructions").glob("plugadvpl-*.instructions.md")
        )
        assert len(instructions) == 52

    def test_no_op_without_github(self, tmp_path: Path) -> None:
        from plugadvpl.copilot_instructions import install_copilot_instructions
        project = tmp_path / "project"
        project.mkdir()
        result = install_copilot_instructions(project, version="0.16.3")
        assert result.installed_global is False
        assert result.installed_local_count == 0
        assert not (project / ".github").exists()
```

- [ ] **Step 2: Run RED**

Expected: 2 failures (ImportError em `install_copilot_instructions`).

- [ ] **Step 3: Implementa orquestrador em copilot_instructions.py**

Adiciona ao final do módulo:

```python
from importlib import resources as ir

from plugadvpl._skill_catalog import (
    INSTRUCTIONS_MARKER_PREFIX,
    WriteOutcome,
    _SKILL_GLOBS,
    _skills_root,
    _write_managed_file,
)


@dataclass(frozen=True)
class InstallResult:
    """Resumo do install_copilot_instructions."""

    installed_global: bool
    installed_local_count: int               # 0..52
    skipped_due_to_user_files: list[str]
    errors: list[str]

    def summary(self) -> str:
        parts = []
        if self.installed_global:
            parts.append("1 global")
        if self.installed_local_count:
            parts.append(f"{self.installed_local_count} locais")
        return (" + ".join(parts) + " instaladas") if parts else "nada instalado"


def install_copilot_instructions(
    project_root: Path, version: str
) -> InstallResult:
    """Orquestra detect + render + write pras instructions Copilot.

    Spec §3.3 da Fase 2. NUNCA propaga exception — try/except em cada bloco,
    init nunca quebra por causa do Copilot.
    """
    skipped: list[str] = []
    errors: list[str] = []
    installed_global = False
    installed_local_count = 0

    try:
        target = detect_copilot(project_root)
    except Exception as e:  # noqa: BLE001
        errors.append(f"detect_copilot falhou: {e!r}")
        return InstallResult(False, 0, [], errors)

    if target.install_global:
        try:
            global_path = (
                project_root / ".github" / "copilot-instructions.md"
            )
            outcome = _write_managed_file(
                global_path,
                render_global_instructions(version),
                INSTRUCTIONS_MARKER_PREFIX,
            )
            if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
                installed_global = True
            elif outcome == WriteOutcome.SKIPPED_USER_FILE:
                skipped.append("copilot-instructions.md (global)")
            elif outcome == WriteOutcome.ERROR:
                errors.append(
                    f"falha ao escrever {global_path}: permission/IO denied"
                )
        except Exception as e:  # noqa: BLE001
            errors.append(f"global instructions erro: {e!r}")

    if target.install_local:
        instructions_dir = project_root / ".github" / "instructions"
        try:
            skills_root = _skills_root()
        except Exception as e:  # noqa: BLE001
            errors.append(f"_skills_root falhou: {e!r}")
            return InstallResult(
                installed_global=installed_global,
                installed_local_count=installed_local_count,
                skipped_due_to_user_files=skipped,
                errors=errors,
            )

        for skill_name, globs in _SKILL_GLOBS.items():
            try:
                resource = (
                    ir.files("plugadvpl") / "skills" / skill_name / "SKILL.md"
                )
                with ir.as_file(resource) as skill_md_path:
                    if not skill_md_path.exists():
                        # Fallback dev tree
                        skill_md_path = (
                            skills_root / skill_name / "SKILL.md"
                        )
                        if not skill_md_path.exists():
                            errors.append(
                                f"skill {skill_name}: SKILL.md ausente"
                            )
                            continue
                    content = render_skill_instructions(
                        skill_md_path, version, globs
                    )
                target_path = (
                    instructions_dir
                    / f"plugadvpl-{skill_name}.instructions.md"
                )
                outcome = _write_managed_file(
                    target_path, content, INSTRUCTIONS_MARKER_PREFIX
                )
                if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
                    installed_local_count += 1
                elif outcome == WriteOutcome.SKIPPED_USER_FILE:
                    skipped.append(
                        f"plugadvpl-{skill_name}.instructions.md"
                    )
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

- [ ] **Step 4: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_copilot_instructions.py -v --no-cov`

Expected: 12 passed (10 prev + 2 install).

Full suite: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov` — Expected: 1116 passed (1104 + 12 copilot tests).

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/copilot_instructions.py cli/tests/unit/test_copilot_instructions.py
git commit -m "feat(copilot): install_copilot_instructions + InstallResult orquestrador

Detecta + renderiza + escreve global + 52 locais.
NUNCA propaga exception — try/except top-level em cada bloco.
Usa INSTRUCTIONS_MARKER_PREFIX (distinto do Cursor RULE_MARKER_PREFIX).

Fallback dev tree no _skills_root igual cursor_rules.

2 testes integrados (smoke end-to-end + no-op sem .github).

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md secao 3.3

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 4: Integração com init + staleness

### Task 6: `--no-copilot` flag + chamada no `init`

**Files:**
- Modify: `cli/plugadvpl/cli.py` (`init` signature + corpo)
- Modify: `cli/tests/integration/test_cli.py` (classe `TestInitCopilotInstructions`)

- [ ] **Step 1: Add 4 RED tests em test_cli.py**

Em `cli/tests/integration/test_cli.py`, IMEDIATAMENTE antes de `class TestIngest:`, adicionar:

```python
class TestInitCopilotInstructions:
    """v0.16.3 — init detecta .github/ e gera Copilot instructions."""

    def test_skips_copilot_when_no_github(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem `.github/` no projeto → no-op pra Copilot."""
        fake_home = synthetic_project.parent / "fake_home_copilot"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert not (synthetic_project / ".github").exists()
        assert "Copilot instructions" not in result.stdout

    def test_installs_when_project_has_github(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.github/` no projeto → 1 global + 52 specifics."""
        fake_home = synthetic_project.parent / "fake_home_copilot2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".github").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        # Global
        assert (
            synthetic_project / ".github" / "copilot-instructions.md"
        ).exists()
        # Locals
        instructions = list(
            (synthetic_project / ".github" / "instructions").glob(
                "plugadvpl-*.instructions.md"
            )
        )
        assert len(instructions) == 52
        assert "Copilot instructions" in result.stdout

    def test_no_copilot_flag_skips(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`--no-copilot` desabilita mesmo com .github/ presente."""
        fake_home = synthetic_project.parent / "fake_home_copilot3"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".github").mkdir()
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "init", "--no-copilot"]
        )
        assert result.exit_code == 0
        assert not (
            synthetic_project / ".github" / "copilot-instructions.md"
        ).exists()
        assert not (synthetic_project / ".github" / "instructions").exists()
        assert "Copilot instructions" not in result.stdout

    def test_quiet_suppresses_copilot_message(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_copilot4"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".github").mkdir()
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "--quiet", "init"]
        )
        assert result.exit_code == 0
        assert "Copilot instructions" not in result.stdout
        # Rules ainda criadas
        instructions = list(
            (synthetic_project / ".github" / "instructions").glob(
                "plugadvpl-*.instructions.md"
            )
        )
        assert len(instructions) == 52
```

- [ ] **Step 2: Run RED**

Expected: 4 failures (`--no-copilot` flag inexistente OR install não é chamada).

- [ ] **Step 3: Modifica `init` em cli.py**

Em `cli/plugadvpl/cli.py`, find `@app.command()` do `init` (linha ~513). O signature atual tem `no_cursor: Annotated[bool, ...]`. ADD `no_copilot` na mesma forma:

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
) -> None:
```

Atualizar docstring:

```python
    """Cria ``./.plugadvpl/index.db``, escreve fragments em ``CLAUDE.md`` + ``AGENTS.md``, atualiza ``.gitignore``, e (se detectado) gera Cursor rules + Copilot instructions.

    v0.16.1: CLAUDE.md + AGENTS.md fragments.
    v0.16.2: Cursor rules nativos em `.cursor/rules/`.
    v0.16.3: Copilot instructions em `.github/copilot-instructions.md` +
    `.github/instructions/plugadvpl-*.instructions.md` quando `.github/`
    existe no projeto. Use `--no-copilot` pra desabilitar.
    """
```

Depois do bloco `if not no_cursor:` que já existe, ADICIONAR:

```python
    if not no_copilot:
        from plugadvpl.copilot_instructions import install_copilot_instructions
        copilot_result = install_copilot_instructions(root, __version__)
        if not ctx.obj["quiet"]:
            if copilot_result.installed_global or copilot_result.installed_local_count:
                typer.echo(
                    f"OK  Copilot instructions: {copilot_result.summary()}"
                )
            for warn in copilot_result.errors:
                typer.secho(
                    f"⚠  Copilot instructions: {warn}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            for skipped in copilot_result.skipped_due_to_user_files:
                typer.secho(
                    f"⚠  Copilot instructions: {skipped} já existe sem marker plugadvpl — não sobrescrevi",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
```

- [ ] **Step 4: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestInitCopilotInstructions -v --no-cov`

Expected: 4 passed.

Full suite: `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov`

Expected: 1120 passed (1116 + 4 init copilot tests). Existing TestInit já tem autouse fixture isolando Path.home (Task 9 do plano Cursor).

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cli.py cli/tests/integration/test_cli.py
git commit -m "feat(copilot): init grava Copilot instructions quando .github/ existe + flag --no-copilot

init() ganha 1 flag (--no-copilot) + 1 chamada install_copilot_instructions
apos install_cursor_rules. Mensagens 'OK Copilot instructions: ...' seguem
o padrao Cursor; warnings YELLOW em stderr.

Deteccao: `.github/` no projeto → instala (menos conservador que Cursor).

4 testes integration em TestInitCopilotInstructions (no github/com github/
--no-copilot/quiet).

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md secao 4

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Idempotência + preservação user files (integration)

**Files:**
- Modify: `cli/tests/integration/test_cli.py` (3 tests em TestInitCopilotInstructions)

- [ ] **Step 1: Add 3 tests no final de TestInitCopilotInstructions**

```python
    def test_idempotent_does_not_duplicate(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_copilot5"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".github").mkdir()
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        instructions = list(
            (synthetic_project / ".github" / "instructions").glob(
                "plugadvpl-*.instructions.md"
            )
        )
        assert len(instructions) == 52
        # Marker aparece uma vez por arquivo
        arch_content = (
            synthetic_project / ".github" / "instructions" / "plugadvpl-arch.instructions.md"
        ).read_text(encoding="utf-8")
        assert arch_content.count("<!-- plugadvpl-instructions-version:") == 1

    def test_overwrites_with_old_marker(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from plugadvpl import __version__
        fake_home = synthetic_project.parent / "fake_home_copilot6"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        instructions_dir = synthetic_project / ".github" / "instructions"
        instructions_dir.mkdir(parents=True)
        stale = instructions_dir / "plugadvpl-arch.instructions.md"
        stale.write_text(
            "stale <!-- plugadvpl-instructions-version: 0.15.0 -->",
            encoding="utf-8",
        )
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        new_content = stale.read_text(encoding="utf-8")
        assert "stale" not in new_content
        assert f"<!-- plugadvpl-instructions-version: {__version__} -->" in new_content

    def test_preserves_user_file_without_marker(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_copilot7"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        instructions_dir = synthetic_project / ".github" / "instructions"
        instructions_dir.mkdir(parents=True)
        user_file = instructions_dir / "plugadvpl-arch.instructions.md"
        user_file.write_text("my own file, no marker", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        # Preserva
        assert user_file.read_text(encoding="utf-8") == "my own file, no marker"
        # Warning
        assert "plugadvpl-arch.instructions.md" in (result.stderr or "")
        assert "sem marker plugadvpl" in (result.stderr or "")
```

- [ ] **Step 2: Run + Commit**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/integration/test_cli.py::TestInitCopilotInstructions -v --no-cov`

Expected: 7 passed (4 + 3).

Full suite: Expected: 1123 passed.

```bash
git add cli/tests/integration/test_cli.py
git commit -m "test(copilot): idempotencia + preservacao de user files no init

3 testes adicionais em TestInitCopilotInstructions cobrindo:
- idempotente (2 inits → 52 specifics + marker count == 1)
- sobrescreve com marker antigo (0.15.0 → versao atual)
- preserva user file sem marker + warning

7/7 verdes.

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md secao 6.1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Staleness de Copilot em `_check_fragment_staleness`

**Files:**
- Modify: `cli/plugadvpl/cli.py` (extende `_check_fragment_staleness`)
- Modify: `cli/tests/integration/test_cli.py` (2 tests em TestStatus)

- [ ] **Step 1: Add 2 RED tests em TestStatus**

```python
    def test_detects_stale_copilot_global(
        self, indexed_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.github/copilot-instructions.md` com marker old → status reporta."""
        fake_home = indexed_project.parent / "fake_home_copilot_status1"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        gh_dir = indexed_project / ".github"
        gh_dir.mkdir(parents=True, exist_ok=True)
        (gh_dir / "copilot-instructions.md").write_text(
            "stale <!-- plugadvpl-instructions-version: 0.15.0 -->",
            encoding="utf-8",
        )
        result = runner.invoke(
            app, ["--root", str(indexed_project), "status"]
        )
        combined = (result.stderr or "") + result.stdout
        assert "copilot-instructions.md" in combined
        assert "0.15.0" in combined

    def test_detects_stale_copilot_local(
        self, indexed_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = indexed_project.parent / "fake_home_copilot_status2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        instructions_dir = indexed_project / ".github" / "instructions"
        instructions_dir.mkdir(parents=True)
        (instructions_dir / "plugadvpl-arch.instructions.md").write_text(
            "stale <!-- plugadvpl-instructions-version: 0.15.0 -->",
            encoding="utf-8",
        )
        result = runner.invoke(
            app, ["--root", str(indexed_project), "status"]
        )
        combined = (result.stderr or "") + result.stdout
        assert "plugadvpl-arch.instructions.md" in combined
        assert "0.15.0" in combined
```

- [ ] **Step 2: Run RED**

Expected: 2 failures (function ignora Copilot files).

- [ ] **Step 3: Estende `_check_fragment_staleness` em cli.py**

Find `_check_fragment_staleness` function in `cli.py`. Adicionar uma 3ª passada **depois** da passada que verifica Cursor rules (a segunda passada adicionada na Task 12 do plano anterior).

Find o bloco que termina com `return None` e ANTES dele adicionar:

```python
    # 3. Copilot instructions (instructions-version)
    copilot_files: list[Path] = []
    copilot_global = root / ".github" / "copilot-instructions.md"
    if copilot_global.exists():
        copilot_files.append(copilot_global)
    copilot_dir = root / ".github" / "instructions"
    if copilot_dir.exists():
        copilot_files.extend(
            sorted(copilot_dir.glob("plugadvpl-*.instructions.md"))
        )

    inst_marker_re = re.compile(
        r"<!--\s*plugadvpl-instructions-version:\s*(\d+\.\d+\.\d+[\w.+-]*)\s*-->"
    )
    for cf in copilot_files:
        try:
            content = cf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = inst_marker_re.search(content)
        if m is None:
            continue
        inst_version = m.group(1)
        if inst_version != __version__:
            return f"{cf.name} foi gerado por plugadvpl {inst_version}"
```

- [ ] **Step 4: Run GREEN**

Expected: 2 passed.

Full suite: Expected: 1125 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/cli.py cli/tests/integration/test_cli.py
git commit -m "feat(status): detecta Copilot instructions desatualizadas (global + locais)

Estende _check_fragment_staleness pra cobrir 3a passada Copilot:
- .github/copilot-instructions.md (global)
- .github/instructions/plugadvpl-*.instructions.md (locais)

Reporta primeiro arquivo desatualizado. Marker plugadvpl-instructions-version
(distinto do Cursor plugadvpl-rule-version, evita confusao).

2 testes integration TestStatus.

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md secao 3.5

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 5: Release v0.16.3

### Task 9: Bump version + skills

**Files:**
- Modify: `.claude-plugin/plugin.json` (0.16.2 → 0.16.3)
- Modify: `.claude-plugin/marketplace.json` (0.16.2 → 0.16.3)
- Modify: `skills/*/SKILL.md` (bumps via Python script)

- [ ] **Step 1: Bump manifests**

Edit `.claude-plugin/plugin.json`: change `"version": "0.16.2"` → `"version": "0.16.3"`.
Edit `.claude-plugin/marketplace.json`: change `"version": "0.16.2"` → `"version": "0.16.3"`.

- [ ] **Step 2: Bump 26 skills via Python script**

Create `d:\tmp\bump_skills_v0163.py`:

```python
from pathlib import Path
OLD = "plugadvpl@0.16.2"; NEW = "plugadvpl@0.16.3"
skills_root = Path("d:/IA/Projetos/plugadvpl/skills")
n = 0
for p in skills_root.rglob("SKILL.md"):
    raw = p.read_bytes()
    if OLD.encode() in raw:
        p.write_bytes(raw.replace(OLD.encode(), NEW.encode()))
        n += 1
print(f"{n} skill(s) bumped")
```

Run: `& "C:\Users\jonil\AppData\Local\Programs\Python\Python312\python.exe" d:\tmp\bump_skills_v0163.py`

Expected: `26 skill(s) bumped`.

- [ ] **Step 3: Verifica full suite + ruff**

```powershell
Set-Location d:\IA\Projetos\plugadvpl\cli
& .venv\Scripts\python.exe -m pytest tests -q --no-cov
```
Expected: 1125 passed.

```powershell
& .venv\Scripts\python.exe -m ruff format --check plugadvpl\cli.py plugadvpl\cursor_rules.py plugadvpl\copilot_instructions.py plugadvpl\_skill_catalog.py
```
Expected: 4 files already formatted. Se reclamar: `& .venv\Scripts\python.exe -m ruff format plugadvpl\cli.py plugadvpl\cursor_rules.py plugadvpl\copilot_instructions.py plugadvpl\_skill_catalog.py`.

- [ ] **Step 4: NÃO commitar ainda — agregado na Task 11**

---

### Task 10: CHANGELOG + README

**Files:**
- Modify: `CHANGELOG.md` (entry v0.16.3)
- Modify: `README.md` (entry v0.16.3 + Quick start touch)

- [ ] **Step 1: CHANGELOG entry**

Em `CHANGELOG.md`, depois de `## [Unreleased]`, INSERT:

```markdown
## [0.16.3] - 2026-05-29

### Added — Copilot Instructions nativos no `plugadvpl init` (Fase 2 multi-agente)

`plugadvpl init` agora detecta `.github/` no projeto e gera:

- **1 arquivo global** em `.github/copilot-instructions.md` (markdown plano, repo-wide) — convenções ADVPL/TLPP, encoding cp1252, tabela de decisão, comandos `uvx`. Respeita soft limit de ~2 páginas documentado pelo Copilot.
- **52 arquivos específicos** em `.github/instructions/plugadvpl-<skill>.instructions.md` — uma por skill com frontmatter `applyTo` glob específico por contexto (string única, não array YAML como em Cursor MDC).

Single source: as 52 instructions são geradas em runtime a partir das `skills/<X>/SKILL.md` embarcadas no wheel (mesma fonte que Claude Code e Cursor consomem). Substituições idênticas (`/plugadvpl:<X>` → `` `Bash: uvx plugadvpl@0.16.3 <X>` ``).

Marker `<!-- plugadvpl-instructions-version: X.Y.Z -->` controla idempotência. **Distinto do Cursor (`plugadvpl-rule-version`)** — evita falso-positivo entre os 2 agentes. `plugadvpl status` detecta instructions desatualizadas.

**Flag:** `plugadvpl init --no-copilot` desabilita mesmo com `.github/` presente.

**Garantia:** falha de I/O em Copilot nunca quebra `init` — mesmo guarantee da Fase 1 Cursor.

Predecessor: v0.16.2 entregou Cursor Rules nativos (Fase 1). v0.16.3 completa Fase 2 cobrindo GitHub Copilot via mecanismo oficial `.github/copilot-instructions.md` + `.github/instructions/`.

### Changed — refactor `_skill_catalog.py` compartilhado (DRY multi-agente)

Helpers neutros movidos de `cli/plugadvpl/cursor_rules.py` pra novo `cli/plugadvpl/_skill_catalog.py`:

- `_SKILL_GLOBS` dict (52 skills + globs) — source-of-truth da lista canônica de skills
- `_parse_skill_md(text)` — parse YAML frontmatter
- `_transform_body(body, version)` — substituições slash→uvx + version normalize
- `_skills_root()` — dev tree vs wheel fallback
- `WriteOutcome` enum
- `_write_managed_file(target, content, marker_substring)` — renomeado de `_write_rule`; agora aceita `marker_substring` como param obrigatório (sem default — caller passa `RULE_MARKER_PREFIX` ou `INSTRUCTIONS_MARKER_PREFIX`)
- `RULE_MARKER_PREFIX` e `INSTRUCTIONS_MARKER_PREFIX` — **distintos** por agente pra evitar falso-positivo

`cursor_rules.py` importa do `_skill_catalog`. Comportamento Cursor 100% preservado (testes da Fase 1 continuam passando após ajustes mínimos de import).

### Changed — `_check_fragment_staleness()` cobre Copilot instructions

`plugadvpl status` agora detecta versão desatualizada em:
- `CLAUDE.md` (já cobria)
- `AGENTS.md` (v0.16.1)
- `~/.cursor/rules/plugadvpl.mdc` + `<project>/.cursor/rules/plugadvpl-*.mdc` (v0.16.2)
- **`.github/copilot-instructions.md`** + **`.github/instructions/plugadvpl-*.instructions.md`** (v0.16.3 — novo)

### Added — `plugadvpl.copilot_instructions` módulo

Novo módulo isolado (~200 linhas) com:
- `CopilotTarget` + `InstallResult` dataclasses
- `detect_copilot()` — `.github/` no projeto
- `render_global_instructions()` — markdown plano com marker
- `render_skill_instructions()` — frontmatter Copilot (`applyTo` string, `description`)
- `install_copilot_instructions()` — orquestrador top-level com same NEVER-propagate guarantee

Reusa `_skill_catalog` (DRY).

### Added — testes novos (TDD)

- 10 unit em `test_skill_catalog.py` (movidos + 1 novo `test_distinct_marker_does_not_match_other_agent`)
- 12 unit em `test_copilot_instructions.py` (detect/render/install)
- 7 integration em `TestInitCopilotInstructions` (init real com mocks)
- 2 integration em `TestStatus` (stale global + local)

Refactor: 3 tests removidos de `test_cursor_rules.py::TestWriteRule` (cobertura migrou pra `test_skill_catalog.py`).

Suite full: 1097 → 1125 passed.

### Bumped

- `uvx plugadvpl@0.16.2` → `uvx plugadvpl@0.16.3` nas 26 skills operacionais.
- `plugin.json` / `marketplace.json` → 0.16.3.
```

- [ ] **Step 2: README entry**

Em `README.md`, antes de `### v0.16.2 — Cursor Rules nativos no init`, INSERT:

```markdown
### v0.16.3 — Copilot Instructions nativos no `init` (Fase 2 multi-agente)

- **`plugadvpl init` agora detecta `.github/`** e gera `.github/copilot-instructions.md` (global, ≤2 pgs) + 52 `.github/instructions/plugadvpl-<X>.instructions.md` (specifics com `applyTo` glob)
- Refactor `_skill_catalog.py` compartilhado (DRY entre Cursor + Copilot); `_SKILL_GLOBS`, parse helpers, `_write_managed_file` neutros
- Markers **distintos por agente** (`plugadvpl-rule-version` Cursor vs `plugadvpl-instructions-version` Copilot) — sem falso-positivo cross-agent
- Flag `--no-copilot`; falha nunca quebra init (mesma guarantee Fase 1)
- `plugadvpl status` detecta Copilot stale (global ou local)
- 28 testes novos (TDD). Suite full: 1125 passed
```

E em "Quick start", trocar:

```markdown
/plugadvpl:init      # cria .plugadvpl/index.db, fragments CLAUDE.md + AGENTS.md, .gitignore (+ Cursor rules se detectado)
```

por:

```markdown
/plugadvpl:init      # cria .plugadvpl/index.db, fragments CLAUDE.md + AGENTS.md, .gitignore (+ Cursor rules + Copilot instructions se detectados)
```

- [ ] **Step 3: NÃO commitar — agregado na Task 11**

---

### Task 11: Release commit + tag + push + monitor CI

**Files:** todos modificados nas Tasks 9 + 10.

- [ ] **Step 1: Pre-flight verification**

```bash
cd /d/IA/Projetos/plugadvpl
git status --short
```

Expected ~30 files: 4 manifest/doc + 26 skills.

Suite full:
```powershell
Set-Location d:\IA\Projetos\plugadvpl\cli
& .venv\Scripts\python.exe -m pytest tests -q --no-cov
```
Expected: 1125 passed.

Ruff format check on CI-tracked files:
```powershell
& .venv\Scripts\python.exe -m ruff format --check plugadvpl\cli.py plugadvpl\cursor_rules.py plugadvpl\copilot_instructions.py plugadvpl\_skill_catalog.py
```

- [ ] **Step 2: Commit release agregado**

```bash
cd /d/IA/Projetos/plugadvpl
git add -u
git commit -m "release: v0.16.3 — Copilot Instructions + refactor _skill_catalog

Bump 0.16.2 -> 0.16.3 (patch — adicao compativel).

plugadvpl init agora detecta .github/ no projeto e gera:
- 1 global em .github/copilot-instructions.md (markdown plano, repo-wide)
- 52 specifics em .github/instructions/plugadvpl-<X>.instructions.md
  com applyTo glob (string unica — formato Copilot)

Refactor: helpers neutros (52 _SKILL_GLOBS, parse, transform, write)
movidos de cursor_rules.py pra _skill_catalog.py. Cursor preservado
(tests da Fase 1 verdes apos import path ajuste).

Markers DISTINTOS por agente (plugadvpl-rule-version vs
plugadvpl-instructions-version) evita falso-positivo cross-agent.

Mudancas:
- cli/plugadvpl/_skill_catalog.py (novo, ~150 linhas)
- cli/plugadvpl/copilot_instructions.py (novo, ~200 linhas)
- cli/plugadvpl/cursor_rules.py (refactor: importa de _skill_catalog)
- cli/plugadvpl/cli.py: init() ganha --no-copilot + chamada install;
  _check_fragment_staleness 3a passada Copilot
- 28 testes novos TDD; 3 movidos no refactor

Updates:
- plugin.json / marketplace.json -> 0.16.3
- uvx plugadvpl@0.16.2 -> @0.16.3 nas 26 skills operacionais
- CHANGELOG.md + README.md (secao v0.16.3)

Suite full: 1125 passed.

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md
Plan: docs/superpowers/plans/2026-05-29-copilot-instructions-implementation.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3: Tag annotated**

```bash
git tag -a v0.16.3 -m "v0.16.3 — Copilot Instructions nativos + refactor _skill_catalog (Fase 2 multi-agente)

plugadvpl init agora detecta .github/ e gera .github/copilot-instructions.md
(global) + 52 .github/instructions/plugadvpl-<X>.instructions.md (specifics
com applyTo glob).

Refactor _skill_catalog.py compartilha helpers entre Cursor e Copilot.
Markers distintos por agente.

Flag --no-copilot. Falha nunca quebra init.

Suite full: 1125 passed.

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md"
```

- [ ] **Step 4: Push**

```bash
git push && git push --tags
```

- [ ] **Step 5: Monitor CI**

```bash
sleep 15 && gh run list --branch main --limit 2 --json status,name,databaseId,displayTitle
```

Find CI run ID, then:
```bash
gh run watch <ID> --interval 20 --exit-status
```

**Possíveis flakes conhecidos:**
- Lint PLR0912 em `_check_fragment_staleness` — agora com 3ª passada, pode estourar 12 branches novamente. **Se aparecer:** extrai 3ª passada pra `_check_copilot_staleness` helper (similar ao que foi feito pra `_check_cursor_rules_staleness` na v0.16.2 release fix).
- Windows hook timeout — já em 30s desde v0.16.1.

- [ ] **Step 6: Verify release workflow**

```bash
gh run list --workflow release.yml --limit 2
```

Expected: `release: v0.16.3` com status `success`.

- [ ] **Step 7: Verify PyPI + GitHub Release**

```bash
gh release view v0.16.3 --json name,publishedAt,url,assets --jq '{name, publishedAt, url, assets: [.assets[].name]}'
curl -s https://pypi.org/pypi/plugadvpl/0.16.3/json -o /dev/null -w "PyPI %{http_code}\n"
```

Expected: PyPI 200; assets `plugadvpl-0.16.3-py3-none-any.whl` + `plugadvpl-0.16.3.tar.gz`.

- [ ] **Step 8: Smoke real opcional**

```bash
mkdir -p /tmp/copilot_smoke && cd /tmp/copilot_smoke && mkdir .github && uvx --refresh plugadvpl@0.16.3 init
```

Expected output includes:
```
OK  Copilot instructions: 1 global + 52 locais instaladas
```

And: `ls .github/instructions/ | wc -l` → 52.

---

## Resumo execução

| Chunk | Tasks | Linhas adicionadas |
|---|---|---|
| 1: Refactor _skill_catalog | 1 (Task 1, 7 steps) | ~400 (módulo novo) - ~150 (movidos) = ~250 líquido |
| 2: copilot_instructions render | 3 tasks (2-4) | ~250 |
| 3: install orquestrador | 1 task (5) | ~150 |
| 4: init integration + staleness | 3 tasks (6-8) | ~250 (testes) + ~40 (cli.py) |
| 5: Release | 3 tasks (9-11) | ~80 (CHANGELOG/README) |
| **Total** | **11 tasks** | **~1080** |

**Estimativa de tempo:** ~3-5h focadas (refactor reduz repetição vs Fase 1).

**Critério final:**
- `gh release view v0.16.3` → ✅
- PyPI `plugadvpl 0.16.3` → ✅
- Smoke `uvx plugadvpl@0.16.3 init` em projeto com `.github/` → cria 1 global + 52 specifics
- Suite full: 1125 passed em CI (13 jobs cross-platform verde)

---

## Notas pra quem executar

1. **Refactor é Chunk 1 atômico** — não comece nada do Chunk 2 antes do refactor estar GREEN. Cursor existente DEVE seguir funcionando após import path changes.
2. **Markers distintos é decisão de policy** — não unifique pra `<!-- plugadvpl-` mesmo se parecer DRY. Spec §3.1 explica.
3. **`importlib.resources` fallback** já documentado em cursor_rules.py — copy do helper `_skills_root` é literal (mesmo código).
4. **PLR0912 risk em `_check_fragment_staleness`** — depois de adicionar 3ª passada Copilot, pode estourar 12 branches. Mesma técnica de extrair helper `_check_copilot_staleness` se aparecer no CI.
5. **Memórias do projeto:**
   - `feedback_powershell_utf8_bom`: bumps via Python read_bytes/write_bytes (NÃO PowerShell Set-Content)
   - `reference_plugadvpl_release_gotchas`: sempre `git tag -a`, suite full sem `--ignore` antes de release
   - `feedback_readme_atualizar_em_releases`: README touch obrigatório

6. **CliRunner stderr caveat (Task 7 `test_preserves_user_file_without_marker`):**
   O teste verifica `result.stderr or ""` pra ver o warning. Isso depende do
   `runner` fixture ser inicializado com `mix_stderr=False` (Typer/Click).
   Antes de rodar Task 7 Step 1, **verifique** se o `runner` fixture em
   `cli/tests/integration/conftest.py` (ou `test_cli.py`) já tem
   `CliRunner(mix_stderr=False)`. Os testes da Fase 1 Cursor (Task 10 em
   `TestInitCursorRules::test_preserves_user_rule_without_marker`) já
   verificam stderr da mesma forma e estão verdes — provavelmente o fixture
   já está configurado. Se o teste passar vacuamente (warning não aparece
   mas assertion não falha), ajustar fixture ou assertion.
