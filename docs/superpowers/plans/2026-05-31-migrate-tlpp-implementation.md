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

**CONTRATO IMPORTANTE (esclarecimento spec-reviewer):**

Esta recipe é peculiar — conversão real é I/O-level (bytes), não string-level. **Quem faz a decodificação cp1252 é o orquestrador** (Task 15c, função `dry_run`), que lê bytes raw E decodifica ANTES de chamar qualquer recipe. Esta recipe `convert-encoding` é apenas **marker** que sinaliza no `MigrationReport` que essa decodificação ocorreu como parte do pipeline canônico. Assim:
- Orquestrador `dry_run` lê `plan.file_path.read_bytes()`, decodifica (utf-8 com BOM > utf-8 > cp1252) e usa essa string como `current_content` inicial.
- Recipe `convert-encoding` é então invocada, mas retorna `nochange` porque a string já está em utf-8 in-memory.
- Quando recipe `rename-extension` rodar (order 2), orquestrador escreve `current_content` (já utf-8) em `.tlpp` (Task 15d, `_write_and_rename`) com encoding `utf-8`.

Net effect: o pipeline produz arquivo `.tlpp` em utf-8 mesmo com recipe `convert-encoding` retornando `nochange`. Suficiente pra MVP. Refactor pra recipe fazer transformação real fica pra v0.19.x.

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

## Chunk 4: Orquestrador + safety gates (expandido em 4 sub-tasks)

### Task 15a: Orquestrador — dataclasses `MigrationPlan` + `MigrationReport`

**Files:**
- Create: `cli/plugadvpl/migrate_tlpp.py` (skeleton; só dataclasses + imports)
- Add to: `cli/tests/unit/test_migrate_tlpp.py` (+2 tests)

- [ ] **Step 1: 2 RED tests**

```python
class TestMigrationDataclasses:
    def test_plan_default_idioms_false(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp import MigrationPlan
        plan = MigrationPlan(file_path=tmp_path / "a.prw", project_root=tmp_path)
        assert plan.enable_idioms is False
        assert plan.tlpp_version == (0, 0, 0)
        assert plan.allow_dirty is False
        assert plan.no_impact_check is False

    def test_report_aggregates_by_status(self) -> None:
        from plugadvpl.migrate_tlpp import MigrationReport
        from plugadvpl.migrate_tlpp_recipes import RecipeResult
        report = MigrationReport(
            file_path=Path("a.prw"),
            recipe_results=[
                RecipeResult(recipe_id="r1", status="ok"),
                RecipeResult(recipe_id="r2", status="ok"),
                RecipeResult(recipe_id="r3", status="nochange"),
                RecipeResult(recipe_id="r4", status="needs-review"),
            ],
        )
        assert report.counts() == {"ok": 2, "nochange": 1, "needs-review": 1}
```

- [ ] **Step 2: Create `cli/plugadvpl/migrate_tlpp.py` (skeleton)**

```python
"""Orquestrador do plugadvpl migrate-tlpp (v0.18.0+).

Aplica recipes em ordem canônica topológica (spec §3.6), com
safety gates pre-flight (git clean, DB ingest check, backup),
auto-validação via compile, e rollback cascata em 3 níveis
(.bak → git checkout → abort exit 2).

Spec: docs/superpowers/specs/2026-05-31-migrate-tlpp-design.md
"""

from __future__ import annotations

import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from plugadvpl.migrate_tlpp_recipes import (
    CANONICAL_ORDER,
    MigrationContext,
    RecipeResult,
    REGISTRY,
    _register_all,
    filter_by_category,
)

if TYPE_CHECKING:
    import sqlite3


@dataclass(frozen=True)
class MigrationPlan:
    """Spec do que migrar: arquivo + flags."""

    file_path: Path
    project_root: Path
    enable_idioms: bool = False
    tlpp_version: tuple[int, int, int] = (0, 0, 0)
    allow_dirty: bool = False
    no_impact_check: bool = False
    selected_recipes: tuple[str, ...] = ()  # vazio = todos os filtrados por category


@dataclass(frozen=True)
class MigrationReport:
    """Resultado agregado de aplicar todas recipes a 1 arquivo."""

    file_path: Path
    recipe_results: list[RecipeResult] = field(default_factory=list)
    final_content: str | None = None  # conteúdo após todas recipes
    rollback_used: Literal["none", "bak", "git", "failed"] = "none"
    compile_validated: bool = False

    def counts(self) -> dict[str, int]:
        return dict(Counter(r.status for r in self.recipe_results))

    def has_errors(self) -> bool:
        return any(r.status == "error" for r in self.recipe_results)

    def all_todos(self) -> list[str]:
        return [t for r in self.recipe_results for t in r.todo_markers]
```

- [ ] **Step 3: Run GREEN** — 2 PASS.

- [ ] **Step 4: Commit**

```bash
git add cli/plugadvpl/migrate_tlpp.py cli/tests/unit/test_migrate_tlpp.py
git commit -m "feat(migrate-tlpp): MigrationPlan + MigrationReport dataclasses

Foundation pro orquestrador. Plan = spec do que migrar; Report =
agregado de resultados das recipes.

2 unit tests. Commit parcial — pre-flight/apply/rollback vêm nas
Tasks 15b-15d.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 15b: Pre-flight gates (`_check_pre_flight`)

**Files:**
- Modify: `cli/plugadvpl/migrate_tlpp.py` (+ função `_check_pre_flight`)
- Add to: `cli/tests/unit/test_migrate_tlpp.py` (+3 tests)

- [ ] **Step 1: 3 RED tests**

```python
class TestPreFlight:
    def test_blocks_when_dirty_git(self, tmp_path: Path, monkeypatch) -> None:
        """git status --porcelain non-empty + sem --allow-dirty → bloqueio."""
        from plugadvpl.migrate_tlpp import MigrationPlan, _check_pre_flight
        # Mock git pra simular dirty
        def fake_run(cmd, **kw):
            class R: returncode = 0; stdout = b" M file.txt\n"
            return R()
        monkeypatch.setattr(subprocess, "run", fake_run)
        plan = MigrationPlan(file_path=tmp_path/"a.prw", project_root=tmp_path)
        errors = _check_pre_flight(plan)
        assert any("git" in e.lower() for e in errors)

    def test_allows_dirty_with_override(self, tmp_path: Path, monkeypatch) -> None:
        from plugadvpl.migrate_tlpp import MigrationPlan, _check_pre_flight
        def fake_run(cmd, **kw):
            class R: returncode = 0; stdout = b" M file.txt\n"
            return R()
        monkeypatch.setattr(subprocess, "run", fake_run)
        plan = MigrationPlan(file_path=tmp_path/"a.prw", project_root=tmp_path,
                             allow_dirty=True)
        errors = _check_pre_flight(plan)
        # git error não aparece com allow_dirty=True (pode ter outros — DB, etc)
        assert not any("working tree" in e.lower() for e in errors)

    def test_blocks_when_db_not_ingested(self, tmp_path: Path, monkeypatch) -> None:
        """Sem .plugadvpl/index.db + sem --no-impact-check → bloqueio."""
        from plugadvpl.migrate_tlpp import MigrationPlan, _check_pre_flight
        def fake_run(cmd, **kw):
            class R: returncode = 0; stdout = b""
            return R()
        monkeypatch.setattr(subprocess, "run", fake_run)
        plan = MigrationPlan(file_path=tmp_path/"a.prw", project_root=tmp_path)
        errors = _check_pre_flight(plan)
        assert any("ingest" in e.lower() or "db" in e.lower() for e in errors)
```

- [ ] **Step 2: Implementação em `migrate_tlpp.py`**

```python
# Adicionar após dataclasses


def _check_pre_flight(plan: MigrationPlan) -> list[str]:
    """Pre-flight gates (spec §4.1). Retorna lista de erros bloqueantes."""
    errors: list[str] = []

    # §4.1.1 — git working tree limpo
    if not plan.allow_dirty:
        try:
            r = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=plan.project_root,
                capture_output=True,
                timeout=10,
            )
            if r.stdout.strip():
                errors.append(
                    "git working tree não está limpo. Use --allow-dirty pra prosseguir."
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Sem git ou hangs — ignora (warning seria nice, sem bloqueio)
            pass

    # §4.1.3 — DB populated (CRITICAL pra caller detection)
    if not plan.no_impact_check:
        db_path = plan.project_root / ".plugadvpl" / "index.db"
        if not db_path.exists():
            errors.append(
                "DB .plugadvpl/index.db ausente. Execute 'plugadvpl ingest' antes "
                "OU use --no-impact-check (preserva nomes truncados; modo conservador)."
            )

    return errors
```

- [ ] **Step 3: Run GREEN + Commit**

```bash
git add cli/plugadvpl/migrate_tlpp.py cli/tests/unit/test_migrate_tlpp.py
git commit -m "feat(migrate-tlpp): _check_pre_flight gates (git clean + DB ingest)

Spec §4.1: bloqueio antes de qualquer write se:
- git working tree dirty (override: --allow-dirty)
- DB .plugadvpl/index.db ausente (override: --no-impact-check)

3 unit tests. Lint pre-flight (SEC-001/SEC-004) fica pra Task 15c
junto com apply (precisa orquestrador completo).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 15c: `dry_run` + `apply` + topological iteration

**Files:**
- Modify: `cli/plugadvpl/migrate_tlpp.py` (+ `dry_run`, `apply`, `_open_db`)
- Add to: `cli/tests/unit/test_migrate_tlpp.py` (+4 tests)

- [ ] **Step 1: 4 RED tests**

```python
class TestDryRun:
    def test_safe_only_skips_idioms(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp import MigrationPlan, dry_run
        f = tmp_path / "a.prw"
        f.write_text("User Function X()\nReturn .T.\n", encoding="cp1252")
        plan = MigrationPlan(
            file_path=f, project_root=tmp_path,
            enable_idioms=False, no_impact_check=True, allow_dirty=True,
        )
        report = dry_run(plan)
        # 6 SAFE recipes rodados; 5 IDIOMS não devem aparecer no report
        ids_executed = {r.recipe_id for r in report.recipe_results}
        idioms_ids = {"namespace-infer", "begin-sequence-to-try",
                      "conout-to-fwlog", "json-inline", "expand-truncated-names"}
        assert not (ids_executed & idioms_ids)

    def test_idioms_enabled_runs_all_11(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp import MigrationPlan, dry_run
        f = tmp_path / "SIGAFAT" / "a.prw"
        f.parent.mkdir()
        f.write_text("User Function X()\nReturn .T.\n", encoding="cp1252")
        plan = MigrationPlan(
            file_path=f, project_root=tmp_path,
            enable_idioms=True, no_impact_check=True, allow_dirty=True,
        )
        report = dry_run(plan)
        assert len(report.recipe_results) == 11

    def test_topological_order_preserved(self, tmp_path: Path) -> None:
        from plugadvpl.migrate_tlpp import MigrationPlan, dry_run
        from plugadvpl.migrate_tlpp_recipes import CANONICAL_ORDER
        f = tmp_path / "a.prw"
        f.write_text("body", encoding="cp1252")
        plan = MigrationPlan(
            file_path=f, project_root=tmp_path,
            enable_idioms=True, no_impact_check=True, allow_dirty=True,
        )
        report = dry_run(plan)
        ids_executed = [r.recipe_id for r in report.recipe_results]
        # ids_executed deve ser subsequência preservando ordem de CANONICAL_ORDER
        idx_map = [CANONICAL_ORDER.index(i) for i in ids_executed]
        assert idx_map == sorted(idx_map), "ordem violada"

    def test_selected_recipes_filters_but_keeps_order(self, tmp_path: Path) -> None:
        """selected_recipes=['header-includes', 'rename-extension'] aplica os 2
        mas em ordem canônica (rename=2, header=3 → header DEPOIS rename)."""
        from plugadvpl.migrate_tlpp import MigrationPlan, dry_run
        f = tmp_path / "a.prw"
        f.write_text("body", encoding="cp1252")
        plan = MigrationPlan(
            file_path=f, project_root=tmp_path,
            no_impact_check=True, allow_dirty=True,
            selected_recipes=("header-includes", "rename-extension"),  # ordem invertida no input
        )
        report = dry_run(plan)
        ids = [r.recipe_id for r in report.recipe_results]
        assert ids == ["rename-extension", "header-includes"]  # canônica preservada
```

- [ ] **Step 2: Implementação**

```python
# Adicionar após _check_pre_flight


def _open_db(project_root: Path) -> "sqlite3.Connection | None":
    """Abre DB read-only se existe."""
    import sqlite3
    db_path = project_root / ".plugadvpl" / "index.db"
    if not db_path.exists():
        return None
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return None


def _select_recipes(plan: MigrationPlan) -> list[str]:
    """Filtra + ordena topologicamente as recipes a executar."""
    _register_all()
    available = filter_by_category(plan.enable_idioms)
    if plan.selected_recipes:
        # Intersect mantendo ordem canônica de available
        selected = set(plan.selected_recipes)
        return [r for r in available if r in selected]
    return available


def dry_run(plan: MigrationPlan) -> MigrationReport:
    """Aplica recipes IN MEMORY (sem tocar FS). Retorna report com diffs."""
    db_conn = _open_db(plan.project_root)
    ctx = MigrationContext(
        file_path=plan.file_path,
        project_root=plan.project_root,
        enable_idioms=plan.enable_idioms,
        tlpp_version=plan.tlpp_version,
        db_connection=db_conn,
    )
    # Read raw bytes + decode cp1252 (caso especial pra convert-encoding;
    # recipe é só marker — orquestrador faz I/O)
    try:
        raw = plan.file_path.read_bytes()
        # detect: utf-8 BOM → utf-8; senão cp1252 (default Protheus)
        if raw.startswith(b"\xef\xbb\xbf"):
            content = raw.decode("utf-8-sig")
        else:
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                content = raw.decode("cp1252", errors="replace")
    except OSError as e:
        return MigrationReport(
            file_path=plan.file_path,
            recipe_results=[RecipeResult(
                recipe_id="io",
                status="error",
                message=f"read failed: {e!r}",
            )],
        )

    selected_ids = _select_recipes(plan)
    results: list[RecipeResult] = []
    current_content = content
    for rid in selected_ids:
        recipe = REGISTRY[rid]
        try:
            r = recipe.apply(current_content, ctx)
            results.append(r)
            if r.new_content is not None and r.status in ("ok", "needs-review"):
                current_content = r.new_content
        except Exception as e:
            results.append(RecipeResult(
                recipe_id=rid, status="error",
                message=f"{e!r}",
            ))

    return MigrationReport(
        file_path=plan.file_path,
        recipe_results=results,
        final_content=current_content if current_content != content else None,
    )
```

- [ ] **Step 3: Run GREEN + Commit**

```bash
git commit -m "feat(migrate-tlpp): dry_run + topological recipe iteration

Spec §3.5-3.6: recipes aplicados em ordem canonica fixa (CANONICAL_ORDER),
mesmo quando --recipe vem em ordem arbitraria. Selecao filtra mas
preserva ordem.

I/O: read bytes + decode cp1252 (default Protheus) ou utf-8 se BOM.
Decode acontece no orquestrador (caso especial pra convert-encoding;
spec §3.6 nota 1).

NEVER-propagate: exception em recipe vira status='error' sem matar
restantes.

4 unit tests. apply() + rollback vêm na Task 15d.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 15d: `apply` + rollback cascata `_rollback_cascade` (§4.2.4)

**Files:**
- Modify: `cli/plugadvpl/migrate_tlpp.py` (+ `apply`, `_rollback_cascade`, `_write_and_rename`)
- Add to: `cli/tests/unit/test_migrate_tlpp.py` (+4 tests)

- [ ] **Step 1: 4 RED tests**

```python
class TestApplyAndRollback:
    def test_apply_writes_tlpp_when_valid(self, tmp_path, monkeypatch) -> None:
        """Happy path: apply escreve .tlpp, valida compile=0, mantém."""
        from plugadvpl.migrate_tlpp import MigrationPlan, apply
        f = tmp_path / "a.prw"
        f.write_text("User Function X()\nReturn .T.\n", encoding="cp1252")
        # Mock compile pra retornar success
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._validate_via_compile",
            lambda p: True,
        )
        plan = MigrationPlan(
            file_path=f, project_root=tmp_path,
            no_impact_check=True, allow_dirty=True, tlpp_version=(20, 3, 2),
        )
        report = apply(plan, validate=True)
        # .tlpp existe; .prw foi renamed
        assert (tmp_path / "a.tlpp").exists()
        assert not f.exists()
        assert report.rollback_used == "none"
        assert report.compile_validated

    def test_rollback_via_bak_when_compile_fails(self, tmp_path, monkeypatch) -> None:
        """Compile fails → rollback restaura .prw de .bak.<timestamp>."""
        from plugadvpl.migrate_tlpp import MigrationPlan, apply
        original_content = "User Function X()\nReturn .T.\n"
        f = tmp_path / "a.prw"
        f.write_text(original_content, encoding="cp1252")
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._validate_via_compile",
            lambda p: False,  # compile falha
        )
        plan = MigrationPlan(
            file_path=f, project_root=tmp_path,
            no_impact_check=True, allow_dirty=True,
        )
        report = apply(plan, validate=True)
        # .prw voltou; .tlpp foi removido
        assert f.exists()
        assert not (tmp_path / "a.tlpp").exists()
        assert report.rollback_used == "bak"
        assert f.read_text(encoding="cp1252") == original_content

    def test_rollback_via_git_when_bak_missing(self, tmp_path, monkeypatch) -> None:
        """BAK deletado entre runs → fallback git checkout."""
        from plugadvpl.migrate_tlpp import MigrationPlan, apply
        # Simula git checkout funcionando, sem .bak
        def fake_git_restore(file_path, project_root):
            file_path.write_text("RESTORED VIA GIT", encoding="cp1252")
            return True
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._validate_via_compile", lambda p: False
        )
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._restore_via_git", fake_git_restore
        )
        # Não cria .bak (apply criaria, mas vamos forçar bak missing post-write)
        f = tmp_path / "a.prw"
        f.write_text("orig", encoding="cp1252")
        plan = MigrationPlan(
            file_path=f, project_root=tmp_path,
            no_impact_check=True, allow_dirty=True,
        )
        # apply normalmente cria .bak.timestamp; pra forçar bak missing, deletamos manualmente
        # Hack: monkeypatch _create_backup pra no-op
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._create_backup", lambda p: None
        )
        report = apply(plan, validate=True)
        assert report.rollback_used == "git"

    def test_rollback_failed_exit_2(self, tmp_path, monkeypatch) -> None:
        """Bak missing + git fails → exit code 2 (CRITICAL)."""
        import pytest
        import typer
        from plugadvpl.migrate_tlpp import MigrationPlan, apply
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._validate_via_compile", lambda p: False
        )
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._restore_via_git",
            lambda f, r: False,
        )
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._create_backup", lambda p: None
        )
        f = tmp_path / "a.prw"
        f.write_text("orig", encoding="cp1252")
        plan = MigrationPlan(
            file_path=f, project_root=tmp_path,
            no_impact_check=True, allow_dirty=True,
        )
        with pytest.raises(typer.Exit) as exc:
            apply(plan, validate=True)
        assert exc.value.exit_code == 2
```

- [ ] **Step 2: Implementação**

```python
# Adicionar após dry_run

import typer


def _create_backup(file_path: Path) -> Path | None:
    """Cria backup .bak.<YYYYMMDDHHMMSS>. Preserva .bak legado sem timestamp."""
    if not file_path.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    bak_path = file_path.with_suffix(file_path.suffix + f".bak.{ts}")
    if bak_path.exists():
        return bak_path  # já existe (run anterior no mesmo segundo) — não sobrescreve
    bak_path.write_bytes(file_path.read_bytes())
    return bak_path


def _find_oldest_bak(file_path: Path) -> Path | None:
    """Acha .bak.<timestamp> mais antigo OU .bak legado."""
    parent = file_path.parent
    base = file_path.name
    candidates = sorted(parent.glob(f"{base}.bak.*"))
    if candidates:
        return candidates[0]  # mais antigo (sort lexicográfico de timestamp = cronológico)
    legacy = file_path.with_suffix(file_path.suffix + ".bak")
    return legacy if legacy.exists() else None


def _restore_via_git(file_path: Path, project_root: Path) -> bool:
    """Tenta `git checkout HEAD -- <file>`. Returns True se OK."""
    try:
        r = subprocess.run(
            ["git", "checkout", "HEAD", "--", str(file_path)],
            cwd=project_root,
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _validate_via_compile(tlpp_path: Path) -> bool:
    """Roda plugadvpl compile <tlpp> em modo appre. True se exit=0."""
    from plugadvpl.compile import CompileRequest, run as compile_run
    from plugadvpl.runtime_config import RuntimeConfig
    try:
        req = CompileRequest(
            files=[tlpp_path],
            mode="appre",
            no_warnings=False,
        )
        # RuntimeConfig pode falhar se não setado; aceita ambos
        cfg = RuntimeConfig.load_or_default()
        result = compile_run(req, cfg, tlpp_path.parent)
        return result.exit_code == 0
    except Exception:
        return False


def _rollback_cascade(
    file_path: Path,
    tlpp_path: Path,
    bak_path: Path | None,
    project_root: Path,
) -> Literal["bak", "git", "failed"]:
    """Cascata §4.2.4: bak → git → abort."""
    # Tentativa primária: restore via bak
    if bak_path is None:
        bak_path = _find_oldest_bak(file_path)
    if bak_path and bak_path.exists():
        try:
            file_path.write_bytes(bak_path.read_bytes())
            if tlpp_path.exists() and tlpp_path != file_path:
                tlpp_path.unlink()
            return "bak"
        except OSError:
            pass

    # Fallback 1: git checkout
    if _restore_via_git(file_path, project_root):
        if tlpp_path.exists() and tlpp_path != file_path:
            try:
                tlpp_path.unlink()
            except OSError:
                pass
        return "git"

    # Fallback 2: abort
    return "failed"


def _write_and_rename(report: MigrationReport, plan: MigrationPlan) -> Path:
    """Aplica final_content + rename .prw → .tlpp (se rename-extension rodou).

    Retorna path final (.tlpp se rename ok, .prw se não).
    """
    if report.final_content is None:
        return plan.file_path  # nada mudou
    # Detecta se rename-extension rodou OK
    rename_ok = any(
        r.recipe_id == "rename-extension" and r.status == "ok"
        for r in report.recipe_results
    )
    target = (
        plan.file_path.with_suffix(".tlpp") if rename_ok else plan.file_path
    )
    target.write_text(report.final_content, encoding="utf-8")
    if rename_ok and plan.file_path != target and plan.file_path.exists():
        plan.file_path.unlink()
    return target


def apply(plan: MigrationPlan, *, validate: bool = False) -> MigrationReport:
    """Aplica recipes ao FS (com pre-flight, backup, validate, rollback)."""
    errors = _check_pre_flight(plan)
    if errors:
        return MigrationReport(
            file_path=plan.file_path,
            recipe_results=[RecipeResult(
                recipe_id="pre-flight",
                status="error",
                message="; ".join(errors),
            )],
        )

    # Backup ANTES de qualquer write
    bak_path = _create_backup(plan.file_path)

    # Dry run pra obter final_content
    report = dry_run(plan)
    if report.final_content is None:
        return report  # nada a aplicar

    # Write + rename
    target = _write_and_rename(report, plan)

    # Validate
    if validate:
        ok = _validate_via_compile(target)
        if not ok:
            # Rollback cascade
            outcome = _rollback_cascade(
                plan.file_path, target, bak_path, plan.project_root
            )
            new_report = MigrationReport(
                file_path=plan.file_path,
                recipe_results=report.recipe_results,
                final_content=None,
                rollback_used=outcome,
                compile_validated=False,
            )
            if outcome == "failed":
                typer.echo(
                    f"CRITICAL: rollback falhou. Arquivo em estado intermediário. "
                    f"Restaure manualmente de {bak_path} ou via git.",
                    err=True,
                )
                raise typer.Exit(code=2)
            return new_report
        return MigrationReport(
            file_path=target,
            recipe_results=report.recipe_results,
            final_content=report.final_content,
            rollback_used="none",
            compile_validated=True,
        )

    return MigrationReport(
        file_path=target,
        recipe_results=report.recipe_results,
        final_content=report.final_content,
        rollback_used="none",
        compile_validated=False,
    )
```

- [ ] **Step 3: Run GREEN + Commit**

Suite full pós-Task 15d: ~1262 passed (1216 + 37 SAFE/IDIOMS recipes + ~9 orquestrador).

```bash
git commit -m "feat(migrate-tlpp): apply + rollback cascata §4.2.4

Spec §4.2: validate via plugadvpl compile (modo appre); se falha,
rollback cascata em 3 niveis:
1. _restore via .bak.<timestamp> mais antigo
2. _restore_via_git checkout HEAD -- <file>
3. abort com typer.Exit(2) + mensagem CRITICAL

_create_backup nunca sobrescreve .bak legado (preserva).
_validate_via_compile reusa plugadvpl.compile.run em modo appre.

4 unit tests (happy + 3 rollback paths).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

---

### Task 16: Extend `edit_prw.convert_and_save` com timestamp backup

**Files:**
- Modify: `cli/plugadvpl/edit_prw.py` — add `timestamp: bool = False` param
- Add to: `cli/tests/unit/test_edit_prw.py` (+3 tests)

- [ ] **Step 0: PRE-READ + caller verification**

ANTES de Edit, rodar:
```
Read cli/plugadvpl/edit_prw.py — confirma assinatura atual de convert_and_save
Grep "convert_and_save\(" no repo inteiro — lista callers existentes
```

Importante porque novo param `timestamp` deve ser kwarg-only com default `False` pra preservar backward compat. Confirma que callers passam args posicionalmente OU por kwarg sem colidir.

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

## Chunk 5: CLI 4 subcomandos (typer sub-app)

### Task 17: Typer sub-app + `migrate-tlpp init <projeto>`

**Files:**
- Modify: `cli/plugadvpl/cli.py` (+ typer sub-app + `init` subcommand)
- Add to: `cli/tests/integration/test_cli.py` — `TestMigrateTlppInit` (3 tests)

- [ ] **Step 1: 3 RED integration tests**

```python
class TestMigrateTlppInit:
    """v0.18.0 — plugadvpl migrate-tlpp init analisa projeto sem tocar nada."""

    def test_init_lists_candidates_in_synthetic_project(
        self, synthetic_project: Path, runner: CliRunner,
    ) -> None:
        # Cria 2 .prw sintéticos
        (synthetic_project / "src").mkdir(exist_ok=True)
        (synthetic_project / "src" / "a.prw").write_text(
            "User Function A()\nReturn .T.\n", encoding="cp1252",
        )
        (synthetic_project / "src" / "b.prw").write_text(
            "User Function B()\nReturn .T.\n", encoding="cp1252",
        )
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "migrate-tlpp", "init", "src"],
        )
        assert result.exit_code == 0, result.stderr
        # output menciona 2 arquivos
        assert "a.prw" in result.stdout or "a.prw" in result.stderr
        assert "b.prw" in result.stdout or "b.prw" in result.stderr

    def test_init_format_json(
        self, synthetic_project: Path, runner: CliRunner,
    ) -> None:
        (synthetic_project / "src").mkdir(exist_ok=True)
        (synthetic_project / "src" / "a.prw").write_text(
            "body", encoding="cp1252",
        )
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "--format", "json",
                  "migrate-tlpp", "init", "src"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["total"] >= 1

    def test_init_does_not_modify_files(
        self, synthetic_project: Path, runner: CliRunner,
    ) -> None:
        (synthetic_project / "src").mkdir(exist_ok=True)
        f = synthetic_project / "src" / "a.prw"
        original = "User Function A()\nReturn .T.\n"
        f.write_text(original, encoding="cp1252")
        runner.invoke(
            app, ["--root", str(synthetic_project), "migrate-tlpp", "init", "src"],
        )
        # Read-only: arquivo intacto
        assert f.read_text(encoding="cp1252") == original
```

- [ ] **Step 2: Find spot em `cli.py` pra inserir typer sub-app**

Procurar onde `edit_prw_app` é criado (~linha 2960 em v0.18.0). Inserir DEPOIS:

```python
# ---------------------------------------------------------------------------
# migrate-tlpp (v0.18.0): migrador deterministico ADVPL clássico -> TLPP
# ---------------------------------------------------------------------------


migrate_tlpp_app = typer.Typer(
    name="migrate-tlpp",
    help="Migrador determinístico .prw → .tlpp (pipeline ts-migrate-style).",
    no_args_is_help=True,
)
app.add_typer(migrate_tlpp_app, name="migrate-tlpp")


def _parse_tlpp_version(s: str | None) -> tuple[int, int, int]:
    if not s:
        return (0, 0, 0)
    parts = s.split(".")
    return tuple(int(p) for p in parts[:3]) + (0,) * (3 - len(parts[:3]))  # type: ignore[return-value]


@migrate_tlpp_app.command("init")
def migrate_tlpp_init(
    ctx: typer.Context,
    pasta: Annotated[
        Path,
        typer.Argument(help="Pasta a analisar (recursivo). Default: root do projeto."),
    ] = Path("."),
    enable_idioms: Annotated[
        bool,
        typer.Option("--idioms", help="Inclui recipes IDIOMS na análise."),
    ] = False,
    tlpp_version: Annotated[
        str | None,
        typer.Option("--tlpp-version", help="Versão AppServer alvo (ex: 20.3.2)."),
    ] = None,
) -> None:
    """Analisa projeto e lista candidatos a migração sem tocar em nada.

    Output (table ou JSON via --format): arquivo, candidato, recipes que
    aplicariam, blockers de lint (SEC-001/SEC-004), impact (count callers
    externos via DB).
    """
    from plugadvpl.migrate_tlpp import MigrationPlan, dry_run
    root: Path = ctx.obj["root"]
    target_dir = pasta if pasta.is_absolute() else root / pasta
    if not target_dir.exists():
        typer.secho(f"Pasta não encontrada: {target_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    parsed_version = _parse_tlpp_version(tlpp_version)
    rows: list[dict] = []
    for prw_file in sorted(target_dir.rglob("*.prw")):
        plan = MigrationPlan(
            file_path=prw_file,
            project_root=root,
            enable_idioms=enable_idioms,
            tlpp_version=parsed_version,
            no_impact_check=True,  # init não escreve, OK skipar
            allow_dirty=True,
        )
        report = dry_run(plan)
        counts = report.counts()
        rows.append({
            "arquivo": str(prw_file.relative_to(root)),
            "recipes_ok": counts.get("ok", 0),
            "nochange": counts.get("nochange", 0),
            "needs_review": counts.get("needs-review", 0),
            "todos": len(report.all_todos()),
        })

    _render_from_ctx(
        ctx, rows,
        columns=["arquivo", "recipes_ok", "nochange", "needs_review", "todos"],
        title=f"Candidatos a migração em {target_dir.relative_to(root)}",
        next_steps=[
            "plugadvpl migrate-tlpp rename <arquivo>  # só rename + encoding",
            "plugadvpl migrate-tlpp recipes <arquivo>  # diff completo",
        ],
    )
```

- [ ] **Step 3: Run GREEN + Commit**

```bash
git commit -m "feat(cli): plugadvpl migrate-tlpp typer sub-app + init subcommand

Spec §3.4: init analisa pasta sem tocar nada, lista candidatos.
Reusa dry_run do orquestrador (Task 15c).

3 integration tests (lista em table, lista em JSON, read-only).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 18: `migrate-tlpp rename <arquivo>`

**Files:**
- Modify: `cli/plugadvpl/cli.py` (+ subcommand)
- Add to: `cli/tests/integration/test_cli.py` — `TestMigrateTlppRename` (2 tests)

- [ ] **Step 1: 2 RED tests** (rename diff-only sem `--write`, rename `--write` aplica + valida)

```python
class TestMigrateTlppRename:
    def test_rename_diff_only_without_write(self, synthetic_project, runner) -> None:
        f = synthetic_project / "a.prw"
        f.write_text("body", encoding="cp1252")
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "migrate-tlpp", "rename", "a.prw"],
        )
        assert result.exit_code == 0
        # diff só, .prw permanece
        assert f.exists()
        assert not (synthetic_project / "a.tlpp").exists()

    def test_rename_write_applies_rename_and_encoding(
        self, synthetic_project, runner, monkeypatch,
    ) -> None:
        # Validate=False default pra rename (mais conservador)
        f = synthetic_project / "a.prw"
        f.write_text("body", encoding="cp1252")
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "migrate-tlpp", "rename",
                  "a.prw", "--write", "--allow-dirty"],
        )
        assert result.exit_code == 0
        assert (synthetic_project / "a.tlpp").exists()
        assert not f.exists()
```

- [ ] **Step 2: Subcommand implementation**

```python
@migrate_tlpp_app.command("rename")
def migrate_tlpp_rename(
    ctx: typer.Context,
    arquivo: Annotated[Path, typer.Argument(help="Arquivo .prw a renomear.")],
    write: Annotated[
        bool, typer.Option("--write", help="Aplica rename (default: só diff).")
    ] = False,
    validate: Annotated[
        bool,
        typer.Option("--validate", help="Após write, valida via compile."),
    ] = False,
    allow_dirty: Annotated[
        bool,
        typer.Option("--allow-dirty", help="Permite working tree dirty."),
    ] = False,
) -> None:
    """Renomeia .prw → .tlpp + converte encoding cp1252 → utf-8.

    Subset conservador: aplica APENAS recipes `convert-encoding` e
    `rename-extension` (canonical order 1-2). Pra recipes completos
    use `migrate-tlpp recipes`.
    """
    from plugadvpl.migrate_tlpp import MigrationPlan, apply, dry_run
    root: Path = ctx.obj["root"]
    target_file = arquivo if arquivo.is_absolute() else root / arquivo
    plan = MigrationPlan(
        file_path=target_file,
        project_root=root,
        no_impact_check=True,  # rename não precisa DB
        allow_dirty=allow_dirty,
        selected_recipes=("convert-encoding", "rename-extension"),
    )
    if write:
        report = apply(plan, validate=validate)
    else:
        report = dry_run(plan)
    if report.final_content is not None and not write:
        from plugadvpl.migrate_tlpp_diff import unified_diff_text
        diff = unified_diff_text(
            target_file.read_text(encoding="cp1252", errors="replace"),
            report.final_content,
            str(target_file),
            str(target_file.with_suffix(".tlpp")),
        )
        typer.echo(diff)
    counts = report.counts()
    typer.secho(
        f"rename: ok={counts.get('ok', 0)} nochange={counts.get('nochange', 0)}",
        fg=typer.colors.GREEN, err=True,
    )
```

- [ ] **Step 3: Run GREEN + Commit**

---

### Task 19: `migrate-tlpp recipes <arquivo>` (mais complexo — 5 testes)

**Files:**
- Modify: `cli/plugadvpl/cli.py` (+ subcommand)
- Add to: `cli/tests/integration/test_cli.py` — `TestMigrateTlppRecipes` (5 tests)

- [ ] **Step 1: 5 RED tests**

```python
class TestMigrateTlppRecipes:
    def test_recipes_diff_only_default(self, synthetic_project, runner) -> None:
        f = synthetic_project / "a.prw"
        f.write_text("User Function X()\nReturn\n", encoding="cp1252")
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "migrate-tlpp", "recipes",
                  "a.prw", "--no-impact-check", "--allow-dirty"],
        )
        assert result.exit_code == 0
        # .prw intacto (sem --write)
        assert f.exists()
        assert not (synthetic_project / "a.tlpp").exists()

    def test_recipes_write_applies(self, synthetic_project, runner) -> None:
        f = synthetic_project / "a.prw"
        f.write_text("User Function X()\nReturn\n", encoding="cp1252")
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "migrate-tlpp", "recipes",
                  "a.prw", "--write", "--no-impact-check", "--allow-dirty"],
        )
        assert result.exit_code == 0
        # .tlpp criado
        assert (synthetic_project / "a.tlpp").exists()

    def test_recipes_idioms_runs_all_11(self, synthetic_project, runner) -> None:
        f = synthetic_project / "SIGAFAT" / "a.prw"
        f.parent.mkdir(exist_ok=True)
        f.write_text("User Function X()\nReturn\n", encoding="cp1252")
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "migrate-tlpp", "recipes",
                  "SIGAFAT/a.prw", "--idioms", "--no-impact-check", "--allow-dirty"],
        )
        assert result.exit_code == 0

    def test_recipes_validate_rollback_when_compile_fails(
        self, synthetic_project, runner, monkeypatch,
    ) -> None:
        f = synthetic_project / "a.prw"
        original = "User Function X()\nReturn\n"
        f.write_text(original, encoding="cp1252")
        # Mock _validate_via_compile pra retornar False (compile falha)
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._validate_via_compile", lambda p: False,
        )
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "migrate-tlpp", "recipes",
                  "a.prw", "--write", "--validate",
                  "--no-impact-check", "--allow-dirty"],
        )
        # Rollback restaura .prw
        assert f.exists()
        assert f.read_text(encoding="cp1252") == original

    def test_recipes_format_json(self, synthetic_project, runner) -> None:
        f = synthetic_project / "a.prw"
        f.write_text("body", encoding="cp1252")
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "--format", "json",
                  "migrate-tlpp", "recipes", "a.prw",
                  "--no-impact-check", "--allow-dirty"],
        )
        assert result.exit_code == 0
        # JSON output parseável
        payload = json.loads(result.stdout)
        assert "recipes" in payload or "rows" in payload
```

- [ ] **Step 2: Subcommand**

```python
@migrate_tlpp_app.command("recipes")
def migrate_tlpp_recipes(
    ctx: typer.Context,
    arquivo: Annotated[Path, typer.Argument()],
    write: Annotated[bool, typer.Option("--write")] = False,
    enable_idioms: Annotated[bool, typer.Option("--idioms")] = False,
    tlpp_version: Annotated[str | None, typer.Option("--tlpp-version")] = None,
    validate: Annotated[bool, typer.Option("--validate")] = False,
    allow_dirty: Annotated[bool, typer.Option("--allow-dirty")] = False,
    no_impact_check: Annotated[bool, typer.Option("--no-impact-check")] = False,
    recipe: Annotated[
        list[str] | None,
        typer.Option("--recipe", "-r", help="Recipe ID (repetível)."),
    ] = None,
) -> None:
    """Aplica recipes de transformação ADVPL → TLPP.

    Default: diff-only. --write aplica + opcionalmente --validate.
    """
    from plugadvpl.migrate_tlpp import MigrationPlan, apply, dry_run
    root: Path = ctx.obj["root"]
    target_file = arquivo if arquivo.is_absolute() else root / arquivo
    parsed_version = _parse_tlpp_version(tlpp_version)
    plan = MigrationPlan(
        file_path=target_file,
        project_root=root,
        enable_idioms=enable_idioms,
        tlpp_version=parsed_version,
        allow_dirty=allow_dirty,
        no_impact_check=no_impact_check,
        selected_recipes=tuple(recipe or ()),
    )
    if write:
        report = apply(plan, validate=validate)
    else:
        report = dry_run(plan)
    if report.final_content is not None and not write:
        from plugadvpl.migrate_tlpp_diff import unified_diff_text
        before = target_file.read_text(encoding="cp1252", errors="replace")
        diff = unified_diff_text(
            before, report.final_content,
            str(target_file), str(target_file.with_suffix(".tlpp")),
        )
        typer.echo(diff)
    # Sumário categorizado
    counts = report.counts()
    fmt = ctx.obj.get("format", "table") if ctx.obj else "table"
    if fmt == "json":
        import json as _json
        typer.echo(_json.dumps({
            "arquivo": str(target_file.relative_to(root)),
            "recipes": [
                {"id": r.recipe_id, "status": r.status, "message": r.message}
                for r in report.recipe_results
            ],
            "counts": counts,
            "todos": report.all_todos(),
            "rollback_used": report.rollback_used,
        }, ensure_ascii=False, indent=2))
    else:
        typer.secho(
            f"recipes: ok={counts.get('ok',0)} nochange={counts.get('nochange',0)} "
            f"needs-review={counts.get('needs-review',0)} error={counts.get('error',0)}",
            fg=typer.colors.GREEN if not report.has_errors() else typer.colors.RED,
            err=True,
        )
        if report.rollback_used != "none":
            typer.secho(f"⚠ rollback usado: {report.rollback_used}",
                       fg=typer.colors.YELLOW, err=True)
```

- [ ] **Step 3: Run GREEN + Commit**

---

### Task 20: `migrate-tlpp todos`

**Files:**
- Modify: `cli/plugadvpl/cli.py` (+ subcommand)
- Add to: `cli/tests/integration/test_cli.py` — `TestMigrateTlppTodos` (2 tests)

- [ ] **Step 1: 2 RED tests**

```python
class TestMigrateTlppTodos:
    def test_todos_empty_when_no_markers(self, synthetic_project, runner) -> None:
        (synthetic_project / "x.tlpp").write_text("function u_x()\nreturn .T.\n", encoding="utf-8")
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "migrate-tlpp", "todos"],
        )
        assert result.exit_code == 0
        assert "nenhum" in result.stdout.lower() or "0" in result.stdout

    def test_todos_lists_markers(self, synthetic_project, runner) -> None:
        (synthetic_project / "y.tlpp").write_text(
            "// @plugadvpl-todo:namespace-infer revise manualmente\n"
            "namespace x\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "migrate-tlpp", "todos"],
        )
        assert result.exit_code == 0
        assert "namespace-infer" in result.stdout
        assert "y.tlpp" in result.stdout
```

- [ ] **Step 2: Subcommand**

```python
import re as _re

_TODO_MARKER_RE = _re.compile(
    r"//\s*@plugadvpl-todo:([^\s]+)\s*(.*?)$", _re.MULTILINE,
)


@migrate_tlpp_app.command("todos")
def migrate_tlpp_todos(
    ctx: typer.Context,
    pasta: Annotated[Path, typer.Argument()] = Path("."),
) -> None:
    """Lista débitos `@plugadvpl-todo` pendentes em arquivos .tlpp."""
    root: Path = ctx.obj["root"]
    target_dir = pasta if pasta.is_absolute() else root / pasta
    rows: list[dict] = []
    for tlpp_file in sorted(target_dir.rglob("*.tlpp")):
        try:
            content = tlpp_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            m = _TODO_MARKER_RE.search(line)
            if m:
                rows.append({
                    "arquivo": str(tlpp_file.relative_to(root)),
                    "linha": line_no,
                    "recipe": m.group(1),
                    "mensagem": m.group(2).strip(),
                })
    if not rows:
        typer.secho("Nenhum débito @plugadvpl-todo encontrado.",
                   fg=typer.colors.GREEN, err=True)
        return
    _render_from_ctx(
        ctx, rows,
        columns=["arquivo", "linha", "recipe", "mensagem"],
        title=f"Débitos @plugadvpl-todo em {target_dir.relative_to(root)}",
    )
```

- [ ] **Step 3: Run GREEN + Commit**

(Cada Task 17-20 = 1 commit separado.)

---

## Chunk 6: Skill + edge cases tests

### Task 21: `skills/migrate-tlpp/SKILL.md` com atribuição TOTVS + bumps 53→54

**Step 0 (LICENSE check — BLOCKING):**

ANTES de qualquer trabalho na skill, rodar:
```bash
gh api repos/totvs/engpro-advpl-tlpp-skills/license --jq '.license.spdx_id'
gh api repos/totvs/engpro-advpl-tlpp-skills/commits/main --jq '.sha' | head -c 40
```

Se LICENSE retornar `null`/`NOASSERTION`/proprietária: **abortar implementation de Task 21** e abrir issue bloqueante. Se MIT/Apache/BSD: prosseguir e salvar SHA pro permalink.

**Step 1-3:** Estrutura igual ao `doc-writer/SKILL.md`: frontmatter `description` com keywords ADVPL/Protheus/TLPP, quando-usar, exemplos dos 4 subcomandos, workflow, atribuição com permalinks `<COMMIT-SHA>` resolvidos no Step 0.

**Step 4: Adicionar `migrate-tlpp` ao catálogo**

Em `cli/plugadvpl/_skill_catalog.py`:

```python
_SKILL_GLOBS: dict[str, list[str]] = {
    # ... existing entries ...
    "docs": [],
    "doc-writer": [],
    "migrate-tlpp": [],  # NOVO v0.18.0 — meta-skill
    "trace": [],
    # ... resto ...
}

_CURSOR_META_ALWAYS_APPLY: set[str] = {
    # ... existing ...
    "docs",
    "doc-writer",
    "migrate-tlpp",  # NOVO v0.18.0
}
```

**Step 5: Bumps 53 → 54 em test asserts (script verbatim)**

Criar `d:\tmp\bump_skill_count_v0180.py`:

```python
"""Bump skill count asserts 53 → 54 em test files (Python bytes — memory feedback_powershell_utf8_bom)."""
import re
from pathlib import Path

files = [
    'cli/tests/integration/test_cli.py',
    'cli/tests/unit/test_copilot_instructions.py',
    'cli/tests/unit/test_cursor_rules.py',
    'cli/tests/unit/test_gemini_skills.py',
    'cli/tests/unit/test_skill_catalog.py',
]

root = Path('d:/IA/Projetos/plugadvpl')
total = 0
for f in files:
    p = root / f
    content = p.read_text(encoding='utf-8')
    new = content
    new = re.sub(r'== 53\b', '== 54', new)
    new = re.sub(r'installed_local_count=53\b', 'installed_local_count=54', new)
    new = re.sub(r'installed_skills_count=53\b', 'installed_skills_count=54', new)
    new = re.sub(r'installed_agents_skills_count=53\b', 'installed_agents_skills_count=54', new)
    new = new.replace('53 skills', '54 skills')
    new = new.replace('test_has_53_skills', 'test_has_54_skills')
    new = new.replace('"53 locais"', '"54 locais"')
    if new != content:
        diff = sum(1 for a, b in zip(content.split('\n'), new.split('\n')) if a != b)
        p.write_text(new, encoding='utf-8', newline='\n')
        print(f'  {f}: {diff} linhas alteradas')
        total += diff
print(f'Total: {total} linhas')
```

Run via Python system: `"/c/Users/jonil/AppData/Local/Programs/Python/Python312/python.exe" d:/tmp/bump_skill_count_v0180.py`. Expected: ~30 linhas alteradas.

**Step 6: Run full suite + commit**

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

4. **Licença TOTVS check (BLOCKING):** Task 21 Step 0 verifica licença do `totvs/engpro-advpl-tlpp-skills`. Se proprietária ou NOASSERTION, **abortar Task 21** e abrir issue antes de prosseguir. Atribuição mesmo correta não substitui licença incompatível pra derivação.

5. **Suite count bumps:** Task 21 Step 5 inclui o script Python verbatim pra bump 53 → 54.

6. **Spec-reviewer concerns:** Spec aplicou 10 fixes pré-implementação. Re-leia §3.6 (ordem) e §4.2.4 (rollback cascata) durante Tasks 15c-15d.

7. **NÃO IMPLEMENTAR (spec §8 Out of Scope):** Os seguintes itens FICAM PARA v0.19.x+ e o subagent NÃO deve tentar implementar mesmo vendo gancho no código existente:
   - MVC `Static Function` + `StaticCall` cross-file → namespace (exige check appserver ≥12.1.2410)
   - Classes ADVPL clássicas → classes TLPP modernas com herança/interfaces
   - `WsRESTful WSMETHOD` → annotations `@Get`/`@Post`/`@Put`/`@Delete` (parser de URL mapping)
   - Tipagem opcional `as Type` (requer type inference; sem AST plugadvpl não suporta)
   - `Begin Transaction` → `try/finally` com commit/rollback (semântica não-trivial)
   - Cross-file refactor (mover funções entre namespaces baseado em uso)
   - Modo interativo `[y/n]` por recipe (preferimos batch + diff)

   Se subagent ver código relacionado (ex: `extract_rest_endpoints` no parser), USA pra detecção/análise mas NÃO transforma.

8. **Dependências entre chunks (sequencial obrigatório):**
   - Chunk 1 (foundation) precede Chunks 2-3 (recipes).
   - Chunks 2-3 precedem Chunk 4 (orquestrador usa REGISTRY populated).
   - Chunk 4 precede Chunk 5 (CLI chama dry_run/apply).
   - Chunk 6 (skill + snapshots) pode rodar em paralelo a Chunk 4 (sem dep crítica).
   - Chunk 7 (release) é último, depois de tudo verde.
