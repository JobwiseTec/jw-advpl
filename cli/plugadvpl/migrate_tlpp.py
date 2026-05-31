"""Orquestrador do plugadvpl migrate-tlpp (v0.18.0+).

Aplica recipes em ordem canônica topológica (spec §3.6), com
safety gates pre-flight (git clean, DB ingest check, backup),
auto-validação via compile, e rollback cascata em 3 níveis
(.bak → git checkout → abort exit 2).

Spec: docs/superpowers/specs/2026-05-31-migrate-tlpp-design.md
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from plugadvpl.migrate_tlpp_recipes import RecipeResult


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
