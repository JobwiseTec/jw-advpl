"""Recipes catalog for plugadvpl migrate-tlpp (v0.18.0+).

Cada recipe é arquivo isolado em ``migrate_tlpp_recipes/``. Catálogo
fixo declarado em ``CANONICAL_ORDER`` (spec §3.6 — ordem topológica
fixa pra evitar combinações tóxicas).

RecipeBase é o contrato; subclasses implementam ``apply()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

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
    return [rid for rid in CANONICAL_ORDER if enable_idioms or is_safe(rid)]
