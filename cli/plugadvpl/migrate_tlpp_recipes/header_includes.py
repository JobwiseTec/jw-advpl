"""Recipe: header-includes (canonical order 3, SAFE).

#Include "protheus.ch" → #Include "totvs.ch"
Adiciona #Include "tlpp-core.th" se TLPP features detectadas no body.
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_PROTHEUS_INCLUDE_RE = re.compile(r'#Include\s+"protheus\.ch"', re.IGNORECASE)
_TLPP_FEATURE_HINTS_RE = re.compile(
    r"\b(namespace|class\s+|method\s+\w+\(\)\s+class|try\b|catch\b|@Get|@Post|@Put|@Delete)\b",
    re.IGNORECASE,
)


class HeaderIncludes(RecipeBase):
    id = "header-includes"
    category = "safe"
    description = "protheus.ch → totvs.ch + adiciona tlpp-core.th se features TLPP detectadas"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:  # noqa: ARG002
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
