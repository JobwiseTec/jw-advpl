"""Recipe: begin-sequence-to-try (canonical order 8, IDIOMS).

Begin Sequence ... Recover Using oErr ... End Sequence
  -> try ... catch (oErr) ... end

Aninhamento (Begin Sequence dentro de outro Begin Sequence) eh
preservado intacto + emite @plugadvpl-todo marker pra revisao manual.
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
    description = "Begin Sequence/Recover/End Sequence -> try/catch"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        todos: list[str] = []

        def replace(match: re.Match[str]) -> str:
            try_body = match.group(1).strip()
            err_var = match.group(2)
            catch_body = match.group(3).strip()
            # Detecta aninhamento dentro do try_body
            if _NESTED_RE.search(try_body):
                todos.append(
                    "begin-sequence-to-try: aninhamento detectado - revise manualmente"
                )
                return match.group(0)  # mantém original
            return f"try\n    {try_body}\ncatch ({err_var})\n    {catch_body}\nend"

        new_content = _BEGIN_SEQ_RE.sub(replace, content)
        if new_content == content:
            if todos:
                # Tinha Begin Sequence aninhado mas nada foi convertido -
                # emite needs-review pra revisao manual.
                return RecipeResult(
                    recipe_id=self.id,
                    status="needs-review",
                    todo_markers=todos,
                )
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(
            recipe_id=self.id,
            status="needs-review" if todos else "ok",
            new_content=new_content,
            todo_markers=todos,
        )
