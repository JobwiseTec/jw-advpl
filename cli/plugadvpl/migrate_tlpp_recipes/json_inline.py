"""Recipe: json-inline (canonical order 10, IDIOMS).

oJson := JsonObject():New()
oJson[\"id\"] := 1
oJson[\"nome\"] := \"x\"
  -> oJson := { \"id\": 1, \"nome\": \"x\" }

MVP conservador: nao tenta consolidar automaticamente (padroes
complexos com loops/branches podem produzir resultado errado).
Apenas DETECTA padrao JsonObject():New() e emite todo pra revisao
manual / LLM.
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_JSON_NEW_RE = re.compile(
    r"^\s*(?:Local|Static|Public|Private|var)?\s*(\w+)\s*:=\s*"
    r"JsonObject\(\)\s*:\s*New\(\)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


class JsonInline(RecipeBase):
    id = "json-inline"
    category = "idioms"
    description = "JsonObject():New() + chain -> JSON inline { ... }"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        matches = list(_JSON_NEW_RE.finditer(content))
        if not matches:
            return RecipeResult(recipe_id=self.id, status="nochange")
        todos = [
            f"json-inline: {m.group(1)} := JsonObject():New() pode ser inline - "
            f"revisar manualmente"
            for m in matches
        ]
        return RecipeResult(
            recipe_id=self.id,
            status="needs-review",
            new_content=content,  # sem transformacao automatica no MVP
            todo_markers=todos,
            message=f"{len(matches)} ocorrencia(s) - sugere inline manual",
        )
