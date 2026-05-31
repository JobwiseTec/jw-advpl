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
