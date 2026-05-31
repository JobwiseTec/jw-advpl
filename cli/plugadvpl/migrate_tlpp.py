"""Orquestrador do plugadvpl migrate-tlpp (v0.18.0+).

Aplica recipes em ordem canônica topológica (spec §3.6), com
safety gates pre-flight (git clean, DB ingest check, backup),
auto-validação via compile, e rollback cascata em 3 níveis
(.bak → git checkout → abort exit 2).

Spec: docs/superpowers/specs/2026-05-31-migrate-tlpp-design.md
"""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from plugadvpl.migrate_tlpp_recipes import (
    REGISTRY,
    MigrationContext,
    RecipeResult,
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
                    "git working tree não está limpo. "
                    "Use --allow-dirty pra prosseguir."
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Sem git ou hangs — ignora (warning seria nice, sem bloqueio)
            pass

    # §4.1.3 — DB populated (CRITICAL pra caller detection)
    if not plan.no_impact_check:
        db_path = plan.project_root / ".plugadvpl" / "index.db"
        if not db_path.exists():
            errors.append(
                "DB .plugadvpl/index.db ausente. "
                "Execute 'plugadvpl ingest' antes "
                "OU use --no-impact-check "
                "(preserva nomes truncados; modo conservador)."
            )

    return errors


def _open_db(project_root: Path) -> sqlite3.Connection | None:
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
        # detect: utf-8 BOM → utf-8; senão utf-8 strict; senão cp1252
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
            recipe_results=[
                RecipeResult(
                    recipe_id="io",
                    status="error",
                    message=f"read failed: {e!r}",
                )
            ],
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
        except Exception as e:  # noqa: BLE001 — recipe não deve quebrar pipeline
            results.append(
                RecipeResult(
                    recipe_id=rid,
                    status="error",
                    message=f"{e!r}",
                )
            )

    return MigrationReport(
        file_path=plan.file_path,
        recipe_results=results,
        final_content=current_content if current_content != content else None,
    )
