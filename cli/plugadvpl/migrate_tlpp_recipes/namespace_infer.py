"""Recipe: namespace-infer (canonical order 7, IDIOMS).

Adiciona namespace inferido por path:
  src/SIGAFAT/MT460FIM.prw -> namespace custom.sigafat.mt460fim

Se path nao tem segmento SIGA*, emite needs-review + todo (LLM
precisa propor namespace manualmente).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

if TYPE_CHECKING:
    from pathlib import Path

_NAMESPACE_RE = re.compile(r"^\s*namespace\s+[\w.]+\s*$", re.IGNORECASE | re.MULTILINE)


def _infer_namespace(file_path: Path) -> str | None:
    """Heuristica: usa pasta SIGA* + basename como namespace.

    Ex: src/SIGAFAT/MT460FIM.prw -> custom.sigafat.mt460fim
    Returns None se path nao tem indicio SIGA*.
    """
    parts = list(file_path.parts)
    siga_idx = next(
        (i for i, p in enumerate(parts) if p.upper().startswith("SIGA")),
        None,
    )
    if siga_idx is None:
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
            return RecipeResult(recipe_id=self.id, status="nochange", message="ja tem namespace")
        ns = _infer_namespace(ctx.file_path)
        if ns is None:
            return RecipeResult(
                recipe_id=self.id,
                status="needs-review",
                message="path nao indicativo - defina namespace manualmente",
                todo_markers=["namespace-infer: path ambiguo; defina namespace manualmente"],
            )
        new_content = f"namespace {ns}\n\n" + content
        return RecipeResult(recipe_id=self.id, status="ok", new_content=new_content)
