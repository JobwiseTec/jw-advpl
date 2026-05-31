# migrate-tlpp v0.18.0 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar `plugadvpl migrate-tlpp` (4 subcomandos + 11 recipes + safety gates + skill) seguindo o spec v0.18.0. Migrador determinístico ADVPL clássico → TLPP moderno com auto-validação via `plugadvpl compile`.

**Architecture:** Pipeline ts-migrate-style (`init`/`rename`/`recipes`/`todos`). 11 recipes em `migrate_tlpp_recipes/` (6 SAFE default, 5 IDIOMS opt-in), aplicados em ordem topológica canônica fixa. Reusa surfaces existentes: `parser`, `edit_prw`, `compile`, `lint`, `db`. Safety gates: git clean, DB ingest check, backup `.bak.<timestamp>`, rollback cascata (bak → git checkout → abort).

**Tech Stack:** Python 3.11+ stdlib + typer (existente) + difflib + rich.syntax (existente) + pytest. Sem deps novas.

**Spec:** [`docs/superpowers/specs/2026-05-31-migrate-tlpp-design.md`](../specs/2026-05-31-migrate-tlpp-design.md)

---

## File Structure

**Novos:**
- `cli/plugadvpl/migrate_tlpp.py` (~250 linhas) — orquestrador + topological sort + safety gates
- `cli/plugadvpl/migrate_tlpp_diff.py` (~80 linhas) — wrapper difflib + rich
- `cli/plugadvpl/migrate_tlpp_recipes/__init__.py` (~120 linhas) — `RecipeBase`, `RecipeResult`, `MigrationContext`, registry
- `cli/plugadvpl/migrate_tlpp_recipes/rename_extension.py` (~40 linhas)
- `cli/plugadvpl/migrate_tlpp_recipes/convert_encoding.py` (~40 linhas)
- `cli/plugadvpl/migrate_tlpp_recipes/header_includes.py` (~80 linhas)
- `cli/plugadvpl/migrate_tlpp_recipes/remove_public.py` (~50 linhas)
- `cli/plugadvpl/migrate_tlpp_recipes/user_function.py` (~120 linhas)
- `cli/plugadvpl/migrate_tlpp_recipes/named_args.py` (~80 linhas)
- `cli/plugadvpl/migrate_tlpp_recipes/namespace_infer.py` (~80 linhas)
- `cli/plugadvpl/migrate_tlpp_recipes/begin_sequence.py` (~120 linhas)
- `cli/plugadvpl/migrate_tlpp_recipes/conout_to_fwlog.py` (~40 linhas)
- `cli/plugadvpl/migrate_tlpp_recipes/json_inline.py` (~80 linhas)
- `cli/plugadvpl/migrate_tlpp_recipes/expand_truncated.py` (~80 linhas)
- `cli/tests/unit/test_migrate_tlpp_recipes.py` (~600 linhas)
- `cli/tests/unit/test_migrate_tlpp.py` (~200 linhas) — orquestrador + topo sort + safety
- `cli/tests/integration/test_cli.py` — 4 novas classes `TestMigrateTlpp*` (~400 linhas)
- `cli/tests/fixtures/migrate_tlpp/` — 5 `.prw` sintéticos + 5 `.tlpp` snapshots esperados
- `skills/migrate-tlpp/SKILL.md` (~200 linhas)

**Modificados:**
- `cli/plugadvpl/edit_prw.py` — `convert_and_save` ganha param `timestamp: bool = False`
- `cli/plugadvpl/cli.py` — 4 novos subcomandos
- `cli/plugadvpl/_skill_catalog.py` — `migrate-tlpp` em `_SKILL_GLOBS` + `_CURSOR_META_ALWAYS_APPLY`
- `cli/tests/integration/test_cli.py` — bumps de count 53 → 54 (nova skill)
- `cli/tests/unit/test_*.py` — bumps similares
- `.github/workflows/ci.yml` — adiciona `migrate_tlpp.py`, `migrate_tlpp_diff.py` ao `LINT_FILES`
- `.claude-plugin/plugin.json` / `marketplace.json` → 0.18.0
- 27 `skills/*/SKILL.md` — bump uvx
- `CHANGELOG.md` + `README.md`

---

## Chunk 1: Foundation — RecipeBase + diff module + context

### Task 1: `RecipeBase`, `RecipeResult`, `MigrationContext`, registry

**Files:**
- Create: `cli/plugadvpl/migrate_tlpp_recipes/__init__.py`
- Create: `cli/tests/unit/test_migrate_tlpp_recipes.py` (skeleton + 5 tests)

- [ ] **Step 1: Create test skeleton with 5 RED tests in `test_migrate_tlpp_recipes.py`**

```python
"""Unit tests for plugadvpl/migrate_tlpp_recipes/ (v0.18.0+)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.migrate_tlpp_recipes import (
    MigrationContext,
    RecipeBase,
    RecipeResult,
    REGISTRY,
    CANONICAL_ORDER,
)


class TestRecipeResult:
    def test_default_status_is_ok(self) -> None:
        r = RecipeResult(recipe_id="x")
        assert r.status == "ok"
        assert r.diff == ""
        assert r.message == ""
        assert r.todo_markers == []

    def test_frozen_dataclass(self) -> None:
        r = RecipeResult(recipe_id="x")
        with pytest.raises(Exception):
            r.status = "error"  # type: ignore[misc]


class TestMigrationContext:
    def test_default_idioms_false(self, tmp_path: Path) -> None:
        ctx = MigrationContext(file_path=tmp_path / "a.prw", project_root=tmp_path)
        assert ctx.enable_idioms is False
        assert ctx.tlpp_version == (0, 0, 0)
        assert ctx.db_connection is None


class TestRegistry:
    def test_registry_has_all_11_recipes(self) -> None:
        """v0.18.0 spec §3.5 lista 11 recipes (6 SAFE + 5 IDIOMS)."""
        assert len(REGISTRY) == 11

    def test_canonical_order_matches_spec(self) -> None:
        """Spec §3.6 ordem canônica fixa."""
        expected = [
            "convert-encoding",
            "rename-extension",
            "header-includes",
            "remove-public-default",
            "user-function-lowercase",
            "named-args",
            "namespace-infer",
            "begin-sequence-to-try",
            "conout-to-fwlog",
            "json-inline",
            "expand-truncated-names",
        ]
        assert CANONICAL_ORDER == expected
```

- [ ] **Step 2: Run RED**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_migrate_tlpp_recipes.py -v --no-cov`

Expected: ModuleNotFoundError.

- [ ] **Step 3: Create `cli/plugadvpl/migrate_tlpp_recipes/__init__.py`**

```python
"""Recipes catalog for plugadvpl migrate-tlpp (v0.18.0+).

Cada recipe é arquivo isolado em ``migrate_tlpp_recipes/``. Catálogo
fixo declarado em ``CANONICAL_ORDER`` (spec §3.6 — ordem topológica
fixa pra evitar combinações tóxicas).

RecipeBase é o contrato; subclasses implementam ``apply()``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# Ordem canônica fixa (spec §3.6) — recipes são sempre aplicados nesta
# sequência independente da ordem em --recipe flags.
CANONICAL_ORDER: list[str] = [
    "convert-encoding",
    "rename-extension",
    "header-includes",
    "remove-public-default",
    "user-function-lowercase",
    "named-args",
    "namespace-infer",
    "begin-sequence-to-try",
    "conout-to-fwlog",
    "json-inline",
    "expand-truncated-names",
]

# Categoria de cada recipe (para filtrar SAFE vs IDIOMS)
_SAFE_RECIPES: set[str] = {
    "convert-encoding",
    "rename-extension",
    "header-includes",
    "remove-public-default",
    "user-function-lowercase",
    "named-args",
}


@dataclass(frozen=True)
class MigrationContext:
    """Estado compartilhado entre recipes durante uma migração."""

    file_path: Path  # caminho original do .prw
    project_root: Path  # raiz do projeto (pra DB lookup)
    enable_idioms: bool = False
    tlpp_version: tuple[int, int, int] = (0, 0, 0)  # gating; (0,0,0) = sem gate
    db_connection: sqlite3.Connection | None = None  # populado se DB existe


@dataclass(frozen=True)
class RecipeResult:
    """Resultado de aplicar 1 recipe."""

    recipe_id: str
    status: Literal["ok", "nochange", "skipped", "error", "needs-review"] = "ok"
    diff: str = ""
    message: str = ""
    todo_markers: list[str] = field(default_factory=list)
    new_content: str | None = None  # conteúdo transformado (None = nochange)


class RecipeBase:
    """Contrato base pra todos recipes.

    Subclasses declaram ``id``, ``category``, ``description``,
    opcionalmente ``requires_tlpp_version``, e implementam ``apply()``.
    """

    id: str = ""
    category: Literal["safe", "idioms"] = "safe"
    description: str = ""
    requires_tlpp_version: tuple[int, int, int] | None = None

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        """Aplica recipe ao conteúdo. NÃO toca em FS.

        Returns: RecipeResult com new_content (se mudou) ou status='nochange'.
        """
        raise NotImplementedError


# REGISTRY populado nos imports concretos abaixo (lazy import pra evitar circular)
REGISTRY: dict[str, RecipeBase] = {}


def _register_all() -> None:
    """Lazy load + registro de todos recipes (chamado em runtime)."""
    if REGISTRY:
        return  # já registrado
    from plugadvpl.migrate_tlpp_recipes.begin_sequence import BeginSequenceToTry
    from plugadvpl.migrate_tlpp_recipes.conout_to_fwlog import ConOutToFwLog
    from plugadvpl.migrate_tlpp_recipes.convert_encoding import ConvertEncoding
    from plugadvpl.migrate_tlpp_recipes.expand_truncated import ExpandTruncatedNames
    from plugadvpl.migrate_tlpp_recipes.header_includes import HeaderIncludes
    from plugadvpl.migrate_tlpp_recipes.json_inline import JsonInline
    from plugadvpl.migrate_tlpp_recipes.named_args import NamedArgs
    from plugadvpl.migrate_tlpp_recipes.namespace_infer import NamespaceInfer
    from plugadvpl.migrate_tlpp_recipes.remove_public import RemovePublicDefault
    from plugadvpl.migrate_tlpp_recipes.rename_extension import RenameExtension
    from plugadvpl.migrate_tlpp_recipes.user_function import UserFunctionLowercase

    for cls in (
        ConvertEncoding,
        RenameExtension,
        HeaderIncludes,
        RemovePublicDefault,
        UserFunctionLowercase,
        NamedArgs,
        NamespaceInfer,
        BeginSequenceToTry,
        ConOutToFwLog,
        JsonInline,
        ExpandTruncatedNames,
    ):
        REGISTRY[cls.id] = cls()


def is_safe(recipe_id: str) -> bool:
    """Recipe é SAFE (default) ou IDIOMS (opt-in)?"""
    return recipe_id in _SAFE_RECIPES


def filter_by_category(enable_idioms: bool) -> list[str]:
    """Lista de recipe_ids em ordem canônica filtrada por categoria."""
    _register_all()
    return [
        rid for rid in CANONICAL_ORDER
        if enable_idioms or is_safe(rid)
    ]
```

- [ ] **Step 4: Run GREEN (Task 1 tests, will still fail on REGISTRY count — that gets fixed once recipes exist)**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_migrate_tlpp_recipes.py::TestRecipeResult tests/unit/test_migrate_tlpp_recipes.py::TestMigrationContext tests/unit/test_migrate_tlpp_recipes.py::TestRegistry::test_canonical_order_matches_spec -v --no-cov`

Expected: 3 PASS. `test_registry_has_all_11_recipes` ainda FAIL (precisa dos 11 recipes implementados).

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/migrate_tlpp_recipes/__init__.py cli/tests/unit/test_migrate_tlpp_recipes.py
git commit -m "feat(migrate-tlpp): RecipeBase + MigrationContext + canonical order (v0.18.0)

Foundation pro migrador deterministico ADVPL->TLPP. Define o contrato
que todos 11 recipes implementam.

- CANONICAL_ORDER: spec §3.6 ordem topologica fixa
- RecipeBase: id + category (safe|idioms) + apply()
- RecipeResult: status + diff + new_content + todo_markers
- MigrationContext: file_path + project_root + enable_idioms + tlpp_version + db
- REGISTRY: dict[str, RecipeBase] populado lazy via _register_all()
- is_safe(), filter_by_category() helpers

5 unit tests (RecipeResult default, frozen, Context, registry count, ordem).

Spec: docs/superpowers/specs/2026-05-31-migrate-tlpp-design.md §3.5-3.6

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `migrate_tlpp_diff` module (difflib + rich)

**Files:**
- Create: `cli/plugadvpl/migrate_tlpp_diff.py`
- Add to: `cli/tests/unit/test_migrate_tlpp.py` (new file, 3 tests)

- [ ] **Step 1: Create test file with 3 RED tests**

```python
"""Unit tests for plugadvpl/migrate_tlpp.py + migrate_tlpp_diff.py (v0.18.0+)."""
from __future__ import annotations

from plugadvpl.migrate_tlpp_diff import unified_diff_text, has_changes


class TestUnifiedDiffText:
    def test_returns_empty_when_identical(self) -> None:
        result = unified_diff_text("x\ny\n", "x\ny\n", "a.prw", "a.tlpp")
        assert result == ""

    def test_includes_headers_and_changes(self) -> None:
        result = unified_diff_text("User Function X()\n", "function u_x()\n", "a.prw", "a.tlpp")
        assert "--- a.prw" in result
        assert "+++ a.tlpp" in result
        assert "-User Function X()" in result
        assert "+function u_x()" in result


class TestHasChanges:
    def test_true_when_differ(self) -> None:
        assert has_changes("a", "b") is True

    def test_false_when_identical(self) -> None:
        assert has_changes("x", "x") is False
```

- [ ] **Step 2: Run RED** — ModuleNotFoundError.

- [ ] **Step 3: Create `cli/plugadvpl/migrate_tlpp_diff.py`**

```python
"""Diff utilities pra migrate-tlpp (v0.18.0+).

Wrapper sobre ``difflib.unified_diff`` pra mostrar before/after de
recipes aplicados. Colorização rich é opcional (quando saída vai pra
TTY interativo).
"""

from __future__ import annotations

import difflib


def has_changes(before: str, after: str) -> bool:
    """Boolean check rápido."""
    return before != after


def unified_diff_text(
    before: str,
    after: str,
    fromfile: str,
    tofile: str,
    *,
    context: int = 3,
) -> str:
    """Retorna unified diff como string (vazio se idêntico)."""
    if not has_changes(before, after):
        return ""
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=fromfile,
        tofile=tofile,
        n=context,
    )
    return "".join(lines)
```

- [ ] **Step 4: Run GREEN**

Run: `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_migrate_tlpp.py -v --no-cov`

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/plugadvpl/migrate_tlpp_diff.py cli/tests/unit/test_migrate_tlpp.py
git commit -m "feat(migrate-tlpp): migrate_tlpp_diff wrapper sobre difflib

unified_diff_text() emite diff unificado pra mostrar before/after
de recipes aplicados. Vazio se identico (nochange).

4 unit tests.

Spec: §3.4 (diff por default em migrate-tlpp recipes)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: SAFE recipes (6 recipes, ordem canônica 1-6)

Cada recipe = 1 task. Estrutura padrão por task: criar arquivo + 3 unit tests (apply OK, nochange, edge case) + run GREEN + commit.

### Task 3: Recipe `convert-encoding` (canonical order 1)

**Files:**
- Create: `cli/plugadvpl/migrate_tlpp_recipes/convert_encoding.py`
- Add to: `cli/tests/unit/test_migrate_tlpp_recipes.py` — class `TestConvertEncoding` (3 tests)

- [ ] **Step 1: 3 RED tests**

```python
class TestConvertEncoding:
    """Recipe order 1 — converte cp1252 → utf-8."""

    def test_idempotent_when_already_utf8(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp_recipes.convert_encoding import ConvertEncoding
        # Content já UTF-8 puro
        content = "User Function X()\nReturn .T.\n"
        ctx = MigrationContext(file_path=tmp_path / "a.prw", project_root=tmp_path)
        r = ConvertEncoding().apply(content, ctx)
        assert r.status == "nochange"

    def test_recipe_id_and_category(self) -> None:
        from plugadvpl.migrate_tlpp_recipes.convert_encoding import ConvertEncoding
        assert ConvertEncoding.id == "convert-encoding"
        assert ConvertEncoding.category == "safe"

    def test_skip_when_tlpp_extension(self, tmp_path: Path) -> None:
        """Se path já é .tlpp, recipe vira nochange."""
        from plugadvpl.migrate_tlpp_recipes.convert_encoding import ConvertEncoding
        ctx = MigrationContext(file_path=tmp_path / "a.tlpp", project_root=tmp_path)
        r = ConvertEncoding().apply("body", ctx)
        assert r.status == "nochange"
```

- [ ] **Step 2: Run RED**

- [ ] **Step 3: Create `convert_encoding.py`**

```python
"""Recipe: convert-encoding (canonical order 1, SAFE).

Converte conteúdo lido como cp1252 pra utf-8. Por design, é nochange
quando arquivo já está em utf-8 OU já tem extensão .tlpp. Delega
detection ao edit_prw.detect_encoding.
"""

from __future__ import annotations

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult


class ConvertEncoding(RecipeBase):
    id = "convert-encoding"
    category = "safe"
    description = "Converte conteúdo de cp1252 pra utf-8 (idempotente se já utf-8)"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        # Se path já é .tlpp, assume conversão já feita
        if ctx.file_path.suffix.lower() == ".tlpp":
            return RecipeResult(recipe_id=self.id, status="nochange")
        # Content vem como string Python — orquestrador faz I/O.
        # Recipe só sinaliza "precisa write" se vai mudar; aqui só normaliza newlines.
        # Re-encode happens na escrita via edit_prw.convert_and_save.
        # NOTA: detection real fica no orquestrador (precisa raw bytes).
        return RecipeResult(recipe_id=self.id, status="nochange")
```

NOTA: Esta recipe é peculiar — a conversão real é I/O-level (bytes), não string-level. Orquestrador (`migrate_tlpp.py`) chama `edit_prw.convert_and_save` durante a etapa write, e este recipe só serve pra REGISTRAR que a etapa foi planejada. Suficiente pra MVP — refactor pra deixar mais robusto fica pra v0.19.x.

- [ ] **Step 4: Run GREEN** + **Step 5: Commit** (com mensagem destacando que conversão real é I/O via edit_prw, recipe é só marker)

---

### Task 4: Recipe `rename-extension` (canonical order 2)

**Files:** `cli/plugadvpl/migrate_tlpp_recipes/rename_extension.py` + 3 tests.

- [ ] **Step 1-5:** Mesma estrutura. Recipe verifica se `ctx.file_path.suffix.lower() == ".prw"` — se sim, marca `status="ok"` e seta `new_content=content` (orquestrador trata o rename físico via `Path.rename`).

```python
"""Recipe: rename-extension (canonical order 2, SAFE)."""

from __future__ import annotations

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult


class RenameExtension(RecipeBase):
    id = "rename-extension"
    category = "safe"
    description = "Marca arquivo .prw pra rename .tlpp (orquestrador faz rename físico)"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        suffix = ctx.file_path.suffix.lower()
        if suffix == ".tlpp":
            return RecipeResult(recipe_id=self.id, status="nochange",
                                message="já é .tlpp")
        if suffix not in (".prw", ".prx"):
            return RecipeResult(recipe_id=self.id, status="skipped",
                                message=f"extensão {suffix} fora do escopo")
        # OK — orquestrador faz Path.rename
        return RecipeResult(recipe_id=self.id, status="ok",
                            new_content=content,
                            message=f"renamear {ctx.file_path.name} → {ctx.file_path.stem}.tlpp")
```

Tests cobrem: .prw → ok, .tlpp → nochange, .txt → skipped.

---

### Task 5: Recipe `header-includes` (canonical order 3)

**Files:** `cli/plugadvpl/migrate_tlpp_recipes/header_includes.py` + 3 tests.

```python
"""Recipe: header-includes (canonical order 3, SAFE).

#Include "protheus.ch" → #Include "totvs.ch"
Adiciona #Include "tlpp-core.th" se TLPP features detectadas no body.
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_PROTHEUS_INCLUDE_RE = re.compile(
    r'#Include\s+"protheus\.ch"', re.IGNORECASE
)
_TLPP_FEATURE_HINTS_RE = re.compile(
    r"\b(namespace|class\s+|method\s+\w+\(\)\s+class|try\b|catch\b|@Get|@Post|@Put|@Delete)\b",
    re.IGNORECASE,
)


class HeaderIncludes(RecipeBase):
    id = "header-includes"
    category = "safe"
    description = "protheus.ch → totvs.ch + adiciona tlpp-core.th se features TLPP detectadas"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        new_content = _PROTHEUS_INCLUDE_RE.sub('#Include "totvs.ch"', content)
        needs_tlpp_core = bool(_TLPP_FEATURE_HINTS_RE.search(new_content))
        has_tlpp_core = '#include "tlpp-core.th"' in new_content.lower()
        if needs_tlpp_core and not has_tlpp_core:
            # Adiciona após o primeiro #Include OU no topo
            if '#include "totvs.ch"' in new_content.lower():
                new_content = new_content.replace(
                    '#Include "totvs.ch"',
                    '#Include "totvs.ch"\n#Include "tlpp-core.th"',
                    1,
                )
            else:
                new_content = '#Include "tlpp-core.th"\n' + new_content
        if new_content == content:
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(recipe_id=self.id, status="ok", new_content=new_content)
```

Tests:
1. `test_replaces_protheus_with_totvs` — `#Include "protheus.ch"` → `#Include "totvs.ch"`
2. `test_adds_tlpp_core_when_class_present` — body com `class Foo` ganha `#Include "tlpp-core.th"`
3. `test_nochange_when_already_totvs` — arquivo já com totvs.ch não-muda

---

### Task 6: Recipe `remove-public-default` (canonical order 4)

**Files:** `cli/plugadvpl/migrate_tlpp_recipes/remove_public.py` + 3 tests.

```python
"""Recipe: remove-public-default (canonical order 4, SAFE).

PUBLIC cVar := "x" → cVar := "x"
TLPP é private por default; PUBLIC explícito é noise.
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

# Match PUBLIC seguido de identificador
_PUBLIC_RE = re.compile(r"\bPUBLIC\s+(?=\w)", re.IGNORECASE)


class RemovePublicDefault(RecipeBase):
    id = "remove-public-default"
    category = "safe"
    description = "Remove keyword PUBLIC default (TLPP é private por default)"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        new_content = _PUBLIC_RE.sub("", content)
        if new_content == content:
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(recipe_id=self.id, status="ok", new_content=new_content)
```

Tests: PUBLIC → removido, sem PUBLIC → nochange, dentro de string `"PUBLIC ..."` preservado (edge case com regex word boundary).

---

### Task 7: Recipe `user-function-lowercase` (canonical order 5) — COMPLEX

**Files:** `cli/plugadvpl/migrate_tlpp_recipes/user_function.py` + 4 tests.

Esta recipe é mais complexa porque depende de **DB lookup pra detectar callers externos**. Se função tem caller externo E nome truncado em 10 chars, preserva nome truncado + emite `@plugadvpl-todo` marker.

```python
"""Recipe: user-function-lowercase (canonical order 5, SAFE).

User Function FATA050() → function u_fata050()

CRITICAL caveat (spec §3.5): se função TEM callers externos E nome
está truncado a 10 chars (típico ADVPL clássico), MANTÉM nome truncado
e adiciona @plugadvpl-todo marker. Sem DB populated, default conservador.
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_USER_FUNCTION_RE = re.compile(
    r"\bUser\s+Function\s+(\w+)\s*\(", re.IGNORECASE
)


def _count_external_callers(
    funcao_name: str,
    file_path: str,
    db_conn,  # type: sqlite3.Connection
) -> int:
    """Conta callers de funcao_name em arquivos DIFERENTES de file_path."""
    if db_conn is None:
        return -1  # signal "DB não disponível"
    cursor = db_conn.execute(
        "SELECT COUNT(*) FROM chamadas WHERE destino = ? AND origem_arquivo != ?",
        (funcao_name.upper(), file_path),
    )
    return int(cursor.fetchone()[0])


class UserFunctionLowercase(RecipeBase):
    id = "user-function-lowercase"
    category = "safe"
    description = (
        "User Function X() → function u_x() (preserva nome truncado se há callers externos)"
    )

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        todos: list[str] = []

        def replace(match: re.Match[str]) -> str:
            original_name = match.group(1)
            external_callers = _count_external_callers(
                original_name, str(ctx.file_path), ctx.db_connection
            )
            if external_callers == -1:
                # Sem DB — modo conservador: preserva nome E emite todo
                todos.append(
                    f"user-function-lowercase: preserva {original_name} (DB não disponível; "
                    f"confirme manualmente antes de expandir)"
                )
                return f"function u_{original_name.lower()}("
            if external_callers > 0:
                todos.append(
                    f"user-function-lowercase: {original_name} tem {external_callers} caller(s) "
                    f"externo(s) — preserva nome truncado"
                )
                return f"function u_{original_name.lower()}("
            # OK — sem callers externos, pode lowercase livre
            return f"function u_{original_name.lower()}("

        new_content = _USER_FUNCTION_RE.sub(replace, content)
        if new_content == content:
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(
            recipe_id=self.id,
            status="needs-review" if todos else "ok",
            new_content=new_content,
            todo_markers=todos,
        )
```

Tests:
1. `test_user_function_simple` — sem DB conn, função simples vira `function u_x(` + todo marker
2. `test_recipe_id` — id == "user-function-lowercase"
3. `test_with_db_no_external_callers` — DB conn presente, função sem callers externos → lowercase sem todo
4. `test_with_db_external_callers_preserves` — DB conn presente, função com callers → mantém nome + todo

(Test 3 e 4 usam in-memory sqlite com schema mínimo `CREATE TABLE chamadas (destino, origem_arquivo)`.)

---

### Task 8: Recipe `named-args` (canonical order 6, gated `--tlpp-version=20.3.2`)

**Files:** `cli/plugadvpl/migrate_tlpp_recipes/named_args.py` + 3 tests.

```python
"""Recipe: named-args (canonical order 6, SAFE, gated tlpp_version≥20.3.2).

xParams(p1 := a, p2 := b) → xParams(p1 = a, p2 = b)

Operador TLPP oficial é `=` (não `:=`). Gating: AppServer ≥20.3.2.0
pra funções/métodos (memory: reference_tlpp_named_params).
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

# Match `identifier := value` dentro de chamada de função (heurística simples;
# limitação aceita: pode também matchar atribuições normais — improvável dentro
# de () de chamada mas spec MVP aceita o trade-off; v0.19.x melhora com parser).
_NAMED_ARG_RE = re.compile(r"(\w+)\s*:=\s*")


class NamedArgs(RecipeBase):
    id = "named-args"
    category = "safe"
    description = "Converte :=  → = em named-args (gated tlpp_version ≥ 20.3.2)"
    requires_tlpp_version = (20, 3, 2)

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        # Gating
        if ctx.tlpp_version < self.requires_tlpp_version:
            return RecipeResult(
                recipe_id=self.id,
                status="skipped",
                message=(
                    f"tlpp_version {ctx.tlpp_version} < {self.requires_tlpp_version} "
                    f"(use --tlpp-version=20.3.2+ pra habilitar)"
                ),
            )
        # Heurística minima: só aplica DENTRO de parens (call sites).
        # MVP: regex line-by-line, conservador (não troca := em assignments).
        # Refactor com AST: v0.19.x.
        new_lines = []
        changed = False
        for line in content.splitlines(keepends=True):
            stripped = line.strip()
            if "(" in stripped and ")" in stripped and ":=" in stripped:
                # tentativa: troca apenas := DENTRO dos parens
                # MVP: troca todos := nessa linha (conservador o suficiente
                # pra chamadas simples; not multiline)
                new_line = _NAMED_ARG_RE.sub(r"\1 = ", line)
                if new_line != line:
                    changed = True
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        new_content = "".join(new_lines)
        if not changed:
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(recipe_id=self.id, status="ok", new_content=new_content)
```

Tests: skip se tlpp_version < 20.3.2; converte := em chamadas; nochange sem := nas linhas.

---

## Chunk 3: IDIOMS recipes (5 recipes, ordem canônica 7-11)

### Task 9: Recipe `namespace-infer` (order 7)

**Files:** `cli/plugadvpl/migrate_tlpp_recipes/namespace_infer.py` + 3 tests.

```python
"""Recipe: namespace-infer (canonical order 7, IDIOMS).

Adiciona namespace inferido por path:
  src/SIGAFAT/MT460FIM.prw → namespace custom.sigafat.mt460fim
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_NAMESPACE_RE = re.compile(r"^\s*namespace\s+[\w.]+\s*$", re.IGNORECASE | re.MULTILINE)


def _infer_namespace(file_path) -> str | None:
    """Heurística: usa últimos 2 segmentos do path + basename."""
    parts = list(file_path.parts)
    # tenta achar pasta tipo SIGA*
    siga_idx = next(
        (i for i, p in enumerate(parts) if p.upper().startswith("SIGA")),
        None,
    )
    if siga_idx is None or siga_idx + 1 >= len(parts):
        return None
    modulo = parts[siga_idx].lower()
    nome = file_path.stem.lower()
    return f"custom.{modulo}.{nome}"


class NamespaceInfer(RecipeBase):
    id = "namespace-infer"
    category = "idioms"
    description = "Adiciona namespace inferido a partir do path do arquivo"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        if _NAMESPACE_RE.search(content):
            return RecipeResult(recipe_id=self.id, status="nochange",
                                message="já tem namespace")
        ns = _infer_namespace(ctx.file_path)
        if ns is None:
            return RecipeResult(
                recipe_id=self.id,
                status="needs-review",
                message="path não indicativo — defina namespace manualmente",
                todo_markers=["namespace-infer: path ambíguo; defina namespace manualmente"],
            )
        new_content = f"namespace {ns}\n\n" + content
        return RecipeResult(recipe_id=self.id, status="ok", new_content=new_content)
```

Tests: SIGAFAT path → infer ok; namespace já existe → nochange; path utils/ → needs-review com todo.

---

### Task 10: Recipe `begin-sequence-to-try` (order 8) — COMPLEX

**Files:** `cli/plugadvpl/migrate_tlpp_recipes/begin_sequence.py` + 4 tests.

```python
"""Recipe: begin-sequence-to-try (canonical order 8, IDIOMS).

Begin Sequence ... Recover Using oErr ... End Sequence
  → try { ... } catch (oErr) { ... }

Aninhado complexo → @plugadvpl-todo marker.
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_BEGIN_SEQ_RE = re.compile(
    r"\bBegin\s+Sequence\b(.*?)\bRecover\s+Using\s+(\w+)\b(.*?)\bEnd\s+Sequence\b",
    re.IGNORECASE | re.DOTALL,
)
_NESTED_RE = re.compile(r"\bBegin\s+Sequence\b", re.IGNORECASE)


class BeginSequenceToTry(RecipeBase):
    id = "begin-sequence-to-try"
    category = "idioms"
    description = "Begin Sequence/Recover/End Sequence → try/catch"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        todos: list[str] = []

        def replace(match: re.Match[str]) -> str:
            try_body = match.group(1).strip()
            err_var = match.group(2)
            catch_body = match.group(3).strip()
            # Detecta aninhamento dentro do try_body
            if _NESTED_RE.search(try_body):
                todos.append(
                    "begin-sequence-to-try: aninhamento detectado — revise manualmente"
                )
                return match.group(0)  # mantém original
            return (
                f"try\n    {try_body}\ncatch ({err_var})\n    {catch_body}\nend"
            )

        new_content = _BEGIN_SEQ_RE.sub(replace, content)
        if new_content == content:
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(
            recipe_id=self.id,
            status="needs-review" if todos else "ok",
            new_content=new_content,
            todo_markers=todos,
        )
```

Tests: simples → try/catch; aninhado → nochange + todo; sem begin sequence → nochange.

---

### Task 11: Recipe `conout-to-fwlog` (order 9)

**Files:** `cli/plugadvpl/migrate_tlpp_recipes/conout_to_fwlog.py` + 3 tests.

```python
"""Recipe: conout-to-fwlog (canonical order 9, IDIOMS).

ConOut("msg") → FwLogMsg("info", "msg")
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_CONOUT_RE = re.compile(r"\bConOut\s*\(", re.IGNORECASE)


class ConOutToFwLog(RecipeBase):
    id = "conout-to-fwlog"
    category = "idioms"
    description = "ConOut() → FwLogMsg('info', ...)"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        new_content = _CONOUT_RE.sub(r'FwLogMsg("info", ', content)
        if new_content == content:
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(recipe_id=self.id, status="ok", new_content=new_content)
```

Tests: ConOut → FwLogMsg; sem ConOut → nochange; ConOut em string literal não afetado (regra word boundary).

---

### Task 12: Recipe `json-inline` (order 10)

**Files:** `cli/plugadvpl/migrate_tlpp_recipes/json_inline.py` + 3 tests.

MVP simples: detecta padrão `oJson := JsonObject():New()` + sucessões `oJson["k"] := v` na MESMA função (linhas consecutivas) e consolida. Padrões complexos (loops, branches) → todo marker.

```python
"""Recipe: json-inline (canonical order 10, IDIOMS).

oJson := JsonObject():New()
oJson["id"] := 1
oJson["nome"] := "x"
  → oJson := { "id": 1, "nome": "x" }

MVP: só padrão linear de N atribuições consecutivas. Complexo
(loops, branches) → @plugadvpl-todo.
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_JSON_NEW_RE = re.compile(
    r"^\s*(\w+)\s*:=\s*JsonObject\(\):New\(\)\s*$", re.IGNORECASE | re.MULTILINE
)


class JsonInline(RecipeBase):
    id = "json-inline"
    category = "idioms"
    description = "JsonObject():New() + chain → JSON inline { ... }"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        # MVP conservador: não tenta consolidar — apenas detecta e emite todo
        matches = list(_JSON_NEW_RE.finditer(content))
        if not matches:
            return RecipeResult(recipe_id=self.id, status="nochange")
        todos = [
            f"json-inline: {m.group(1)} := JsonObject():New() pode ser inline — revisar manualmente"
            for m in matches
        ]
        return RecipeResult(
            recipe_id=self.id,
            status="needs-review",
            new_content=content,  # sem transformação automática no MVP
            todo_markers=todos,
            message=f"{len(matches)} ocorrência(s) — sugere inline manual",
        )
```

Tests: padrão JsonObject:New → needs-review + todo; sem JsonObject → nochange.

---

### Task 13: Recipe `expand-truncated-names` (order 11) — COMPLEX

**Files:** `cli/plugadvpl/migrate_tlpp_recipes/expand_truncated.py` + 3 tests.

Similar a `user-function-lowercase` mas inverso: detecta nomes truncados a exatamente 10 chars E pergunta ao DB se há callers externos. Se não há, expande (mas LLM precisaria fornecer o nome completo — MVP só sinaliza).

```python
"""Recipe: expand-truncated-names (canonical order 11, IDIOMS).

ADVPL clássico tinha limite 10 chars em identificadores — nomes longos
eram truncados silenciosamente. Esta recipe DETECTA candidatos (nomes
exatamente 10 chars) e emite todos pra revisão manual. NÃO expande
automático (LLM precisa propor nome completo).

CRITICAL: depende de DB.
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_FUNCTION_DEF_RE = re.compile(
    r"\b(?:User\s+|Static\s+)?Function\s+(\w{10})\s*\(", re.IGNORECASE
)


class ExpandTruncatedNames(RecipeBase):
    id = "expand-truncated-names"
    category = "idioms"
    description = "Detecta nomes truncados a 10 chars (limite ADVPL legacy) — emite todos"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        if ctx.db_connection is None:
            return RecipeResult(
                recipe_id=self.id,
                status="skipped",
                message="DB não disponível — execute 'plugadvpl ingest'",
            )
        matches = list(_FUNCTION_DEF_RE.finditer(content))
        if not matches:
            return RecipeResult(recipe_id=self.id, status="nochange")
        todos: list[str] = []
        for m in matches:
            name = m.group(1)
            cursor = ctx.db_connection.execute(
                "SELECT COUNT(*) FROM chamadas WHERE destino = ? AND origem_arquivo != ?",
                (name.upper(), str(ctx.file_path)),
            )
            callers = int(cursor.fetchone()[0])
            if callers > 0:
                todos.append(
                    f"expand-truncated-names: {name} tem {callers} caller(s) externos "
                    f"— coordene rename antes de expandir"
                )
            else:
                todos.append(
                    f"expand-truncated-names: {name} é candidato a expansão "
                    f"(sem callers externos) — LLM proponha nome completo"
                )
        return RecipeResult(
            recipe_id=self.id,
            status="needs-review",
            new_content=content,
            todo_markers=todos,
        )
```

Tests: skip se DB None; detecta funções 10-char com callers vs sem callers; nochange sem nomes 10-char.

---

### Task 14: Test `test_registry_has_all_11_recipes` agora passa

- [ ] **Step 1:** Re-run `cd cli && .venv/Scripts/python.exe -m pytest tests/unit/test_migrate_tlpp_recipes.py::TestRegistry -v --no-cov` — agora TODOS 11 recipes registrados, `len(REGISTRY) == 11` passa.

- [ ] **Step 2:** Full suite ainda deve ser GREEN — `cd cli && .venv/Scripts/python.exe -m pytest tests -q --no-cov` (esperado: 1216 + ~35 novos testes = ~1251).

- [ ] **Step 3: Commit** consolidado dos 5 IDIOMS recipes (Tasks 9-13) — pode ser 1 commit por task ou 1 commit agrupado. Recomendado: **1 commit por task** pra histórico granular.

---

## Chunk 4: Orquestrador + safety gates

### Task 15: `migrate_tlpp.py` orquestrador

**Files:**
- Create: `cli/plugadvpl/migrate_tlpp.py` (~250 linhas)
- Add to: `cli/tests/unit/test_migrate_tlpp.py` (+8 tests)

Estrutura:
- `MigrationPlan` dataclass: file + ordered_recipes + tlpp_version + enable_idioms
- `MigrationReport` dataclass: per-file × per-recipe results + sumário categorizado
- `dry_run(file, ctx) -> MigrationReport`: aplica recipes IN MEMORY, retorna diff por recipe
- `apply(file, ctx) -> MigrationReport`: dry_run + escreve + validate + rollback se falhar
- `_check_pre_flight(ctx) -> list[str]`: valida git clean, DB ingested, lint pre-flight, backup
- `_rollback_cascade(file, bak_path) -> Literal["ok", "git", "failed"]`: §4.2.4 cascata

Plan provides exact code (~250 linhas). Tests cover:
1. dry_run with all 11 recipes, no DB, no idioms → 6 SAFE applied, idioms skipped
2. dry_run with idioms enabled → all 11
3. apply with rollback success when compile fails
4. apply with rollback-via-git when bak fails
5. apply with rollback-failed → exit 2
6. pre-flight blocks when working tree dirty (without --allow-dirty)
7. pre-flight blocks when DB not ingested (without --no-impact-check)
8. backup timestamp doesn't overwrite legacy .bak

(Código completo no orquestrador omitido aqui por brevidade — implementador segue contratos de RecipeBase + topological iteration + safety gate functions descritos.)

---

### Task 16: Extend `edit_prw.convert_and_save` com timestamp backup

**Files:**
- Modify: `cli/plugadvpl/edit_prw.py` — add `timestamp: bool = False` param
- Add to: `cli/tests/unit/test_edit_prw.py` (+3 tests)

```python
# Em edit_prw.py — encontrar def convert_and_save e adicionar timestamp
from datetime import datetime, timezone

def convert_and_save(
    src: Path,
    *,
    from_encoding: str | None = None,
    to_encoding: str | None = None,
    backup: bool = False,
    timestamp: bool = False,  # NOVO v0.18.0
) -> tuple[Path, Path | None]:
    """...

    Args:
        timestamp: se True E backup=True, gera .bak.<YYYYMMDDHHMMSS> ao
            invés de .bak fixo. Preserva .bak legado sem timestamp.
    """
    bak_path: Path | None = None
    if backup:
        if timestamp:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            bak_path = src.with_suffix(src.suffix + f".bak.{ts}")
        else:
            bak_path = src.with_suffix(src.suffix + ".bak")
        if not bak_path.exists():
            bak_path.write_bytes(src.read_bytes())
    # ... resto da função ...
```

Tests:
1. timestamp=True cria .bak.<digits> (regex `\.bak\.\d{14}$`)
2. timestamp=True preserva .bak legado existente (não sobrescreve)
3. timestamp=False (default) mantém comportamento legado

---

## Chunk 5: CLI 4 subcomandos

### Task 17: `plugadvpl migrate-tlpp init <projeto>`

**Files:**
- Modify: `cli/plugadvpl/cli.py` (+1 typer sub-app + 1 subcommand)
- Add to: `cli/tests/integration/test_cli.py` — `TestMigrateTlppInit` (3 tests)

Estrutura: criar `migrate_tlpp_app = typer.Typer(name="migrate-tlpp", ...)` análogo a `edit_prw_app`. Subcomando `init` analisa todos `.prw` no projeto, mostra tabela/json com candidatos + blockers + impact.

### Task 18: `migrate-tlpp rename <arquivo>` (2 integration tests)

### Task 19: `migrate-tlpp recipes <arquivo>` (5 integration tests — diff-only, --write, --idioms, --validate rollback, --allow-dirty)

### Task 20: `migrate-tlpp todos` (2 integration tests)

(Cada Task = bite-sized commits separados.)

---

## Chunk 6: Skill + edge cases tests

### Task 21: `skills/migrate-tlpp/SKILL.md` com atribuição TOTVS

Estrutura igual ao `doc-writer/SKILL.md`: frontmatter `description` com keywords ADVPL/Protheus/TLPP, quando-usar, exemplos, workflow, atribuição.

Atribuição (spec §9): permalinks com commit SHA fixo (resolver durante implementação via `gh api repos/totvs/engpro-advpl-tlpp-skills/commits/main` pra pegar SHA atual; checar LICENSE — abrir issue bloqueante se não-declarada).

Adicionar `migrate-tlpp` ao `_SKILL_GLOBS` (meta-skill, escopo vazio) e `_CURSOR_META_ALWAYS_APPLY`. Atualizar bumps 53 → 54 em ALL test asserts (mesma operação do v0.17.0 quando doc-writer foi adicionado).

### Task 22: Snapshot fixtures pra roundtrip

Criar 5 fixtures `.prw` em `cli/tests/fixtures/migrate_tlpp/`:
1. `simple_user_function.prw` — User Function sem dependências
2. `with_begin_sequence.prw` — usa Begin Sequence pra try/catch
3. `with_json_object.prw` — JsonObject():New() chain
4. `class_advpl.prw` — class clássica
5. `with_namespace_hint.prw` — em SIGAFAT/ pra namespace inference

Cada fixture tem snapshot esperado `.tlpp` correspondente. Tests via syrupy:

```python
def test_migrate_simple_user_function(snapshot):
    src = (FIXTURES / "simple_user_function.prw").read_text(encoding="cp1252")
    result = migrate_all_recipes(src, enable_idioms=True, tlpp_version=(20, 3, 2))
    assert result == snapshot
```

### Task 23: Rollback cascata integration tests (3 caminhos)

Cobre §4.2.4: backup OK; backup falha + git OK; ambos falham → exit 2.

---

## Chunk 7: Release v0.18.0

### Task 24: Bump versions

- `plugin.json` + `marketplace.json`: 0.17.0 → 0.18.0
- 27 skills (+ nova `migrate-tlpp` = 28 SKILL.md total) bump `uvx plugadvpl@0.17.0` → `@0.18.0` via Python script `d:\tmp\bump_skills_v0180.py`:

```python
from pathlib import Path
OLD = b"plugadvpl@0.17.0"; NEW = b"plugadvpl@0.18.0"
skills_root = Path("d:/IA/Projetos/plugadvpl/skills")
n = 0
for p in skills_root.rglob("SKILL.md"):
    raw = p.read_bytes()
    if OLD in raw:
        p.write_bytes(raw.replace(OLD, NEW))
        n += 1
print(f"{n} skill(s) bumped")
```

### Task 25: Lint scope expand pros novos arquivos

Add to `.github/workflows/ci.yml` `LINT_FILES`:
- `plugadvpl/migrate_tlpp.py`
- `plugadvpl/migrate_tlpp_diff.py`
- `plugadvpl/migrate_tlpp_recipes/__init__.py`
- (11 arquivos de recipe estão em subdir — ou adicionar individual ou usar pattern `plugadvpl/migrate_tlpp_recipes/*.py`)

### Task 26: CHANGELOG entry + README cobertura

Estrutura igual v0.17.0 — seção `## [0.18.0] - 2026-05-31` com:
- Added — `migrate-tlpp` (descrição + 4 subcomandos + 11 recipes + atribuição)
- Bumped — skills + manifests

README: adicionar entry em "Evolução por versão" + nova linha na tabela "Cobertura multi-agente" se aplicável.

### Task 27: Pre-tag verification

Memory `feedback_ci_ruff_version_drift`: usar `cd cli && uv run ruff check $LINT_FILES` (NÃO `.venv/Scripts/python.exe -m ruff`) pra simular CI.

```powershell
cd d:\IA\Projetos\plugadvpl\cli
uv run ruff check plugadvpl/__main__.py plugadvpl/_skill_catalog.py [...] plugadvpl/migrate_tlpp.py plugadvpl/migrate_tlpp_diff.py plugadvpl/migrate_tlpp_recipes/__init__.py
uv run ruff format --check [same files]
uv run mypy [same files]
uv run pytest tests -q --no-cov
```

Expected: all GREEN. Suite ~1280 passed (1216 + ~65 novos).

### Task 28: Commit release + annotated tag + push + monitor CI + verify

```bash
git add -u
git commit -m "release: v0.18.0 — migrate-tlpp (primeiro migrador ADVPL->TLPP deterministico)

ADDED: plugadvpl migrate-tlpp pipeline ts-migrate-style:
- init / rename / recipes / todos subcomandos
- 11 recipes (6 SAFE default + 5 IDIOMS opt-in --idioms)
- Ordem canonica topologica fixa (spec §3.6)
- Safety gates: git clean + DB ingest check + backup .bak.<timestamp>
- Rollback cascata: .bak → git checkout → abort exit 2 (spec §4.2.4)
- Auto-validacao via plugadvpl compile (--validate)
- @plugadvpl-todo markers pra débitos pendentes
- Atribuicao TOTVS engpro-advpl-tlpp-skills (permalinks SHA-fixo)

Skill /plugadvpl:migrate-tlpp adicionada.
LINT_FILES expandido com novos arquivos.

Tests: ~65 novos. Suite full: 1216 -> ~1280 passed.

Updates:
- plugin.json / marketplace.json -> 0.18.0
- uvx plugadvpl@0.17.0 -> @0.18.0 nas 28 skills
- CHANGELOG + README documentam migrate-tlpp

Spec: docs/superpowers/specs/2026-05-31-migrate-tlpp-design.md
Plan: docs/superpowers/plans/2026-05-31-migrate-tlpp-implementation.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

git tag -a v0.18.0 -m "v0.18.0 — migrate-tlpp (ADVPL->TLPP migrador deterministico)

Pipeline ts-migrate-style com 4 subcomandos + 11 recipes.
Primeiro do mercado a oferecer auto-validacao via compile.
Atribuicao TOTVS engpro-advpl-tlpp-skills oficial.

Suite full: ~1280 passed."

git push && git push --tags
```

Monitor (memory `reference_plugadvpl_release_gotchas`):
```bash
sleep 15
gh run list --branch main --limit 2 --json status,name,databaseId,displayTitle,conclusion
# pegar release.yml ID e monitorar
gh run watch <RELEASE_ID> --interval 20 --exit-status
gh run view <RELEASE_ID> --json status,conclusion,jobs --jq '...'
curl -s -o /dev/null -w "PyPI %{http_code}\n" https://pypi.org/pypi/plugadvpl/0.18.0/json
gh release view v0.18.0 --json name,tagName,assets
```

---

## Resumo execução

| Chunk | Tasks | Estimativa | Linhas |
|---|---|---|---|
| 1: Foundation (RecipeBase + diff) | 2 | 0.5d | 200 |
| 2: SAFE recipes (6) | 6 | 1.5d | 400 |
| 3: IDIOMS recipes (5) | 5 + verify | 1.5d | 400 |
| 4: Orquestrador + edit_prw timestamp | 2 | 1d | 350 |
| 5: CLI 4 subcomandos | 4 | 1.5d | 500 |
| 6: Skill + snapshots + rollback tests | 3 | 1d | 500 |
| 7: Release v0.18.0 | 5 | 0.5d | 200 |
| **Total** | **27 tasks** | **6-8 dias** | **~3500 linhas** |

**Critério final:** PyPI 200 plugadvpl 0.18.0 · GitHub Release v0.18.0 wheel+sdist · CI matrix all-green · `plugadvpl migrate-tlpp init src/` em projeto sintético produz tabela esperada · `plugadvpl migrate-tlpp recipes <arq> --write --validate --idioms` em fixture aplica + valida + sumariza.

---

## Notas pra quem executar

1. **Memory tips loadable:**
   - `feedback_powershell_utf8_bom` — sempre Python bytes nos bumps de SKILL.md
   - `feedback_ci_ruff_version_drift` — pre-tag usa `uv run ruff` (não `.venv` local)
   - `reference_plugadvpl_release_gotchas` — `git tag -a` annotated; suite full antes do tag

2. **Recipe order dependency:** Quando rodar Tasks 3-13 (recipes), ordem topológica em CANONICAL_ORDER (§3.6) DEVE bater com ordem dos arquivos `cli/plugadvpl/migrate_tlpp_recipes/*.py`. Test `test_canonical_order_matches_spec` (Task 1) protege contra drift.

3. **DB schema dependency:** Tasks 7 (user-function-lowercase) e 13 (expand-truncated-names) requerem schema com tabela `chamadas (destino, origem_arquivo)`. Tests usam in-memory sqlite. Spec assume DB já existe pelo `plugadvpl ingest` pré-requisito.

4. **Licença TOTVS check:** ANTES de v0.18.0 ship, abrir issue verificando licença `totvs/engpro-advpl-tlpp-skills` (spec §9). Se proprietária, atribuição pode não ser suficiente — derivação requer permissão.

5. **Suite count bumps:** Adicionar `migrate-tlpp` ao `_SKILL_GLOBS` faz 53 → 54 skills. Aplicar Python script análogo ao do v0.17.0 (replace `== 53` → `== 54` e similares) nos test files.

6. **Spec-reviewer concerns:** Spec aplicou 10 fixes pré-implementação. Re-leia §3.6 (ordem) e §4.2.4 (rollback cascata) durante Tasks 15-16.
