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

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:  # noqa: ARG002
        new_content = _PUBLIC_RE.sub("", content)
        if new_content == content:
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(recipe_id=self.id, status="ok", new_content=new_content)
