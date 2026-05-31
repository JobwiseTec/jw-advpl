"""Recipe: conout-to-fwlog (canonical order 9, IDIOMS).

ConOut("msg") -> FwLogMsg("info", "msg")

FwLogMsg eh log estruturado moderno (com nivel/categoria), substituto
do ConOut clássico. Word boundary evita matchar ConOut dentro de
strings literais ou comentarios.
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_CONOUT_RE = re.compile(r"\bConOut\s*\(", re.IGNORECASE)


class ConOutToFwLog(RecipeBase):
    id = "conout-to-fwlog"
    category = "idioms"
    description = "ConOut() -> FwLogMsg('info', ...)"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:  # noqa: ARG002
        new_content = _CONOUT_RE.sub('FwLogMsg("info", ', content)
        if new_content == content:
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(recipe_id=self.id, status="ok", new_content=new_content)
