"""Recipe: expand-truncated-names (canonical order 11, IDIOMS).

ADVPL classico tinha limite 10 chars em identificadores - nomes
longos eram truncados silenciosamente. Esta recipe DETECTA candidatos
(funcoes com nome exatamente 10 chars) e emite todos pra revisao
manual. NAO expande automaticamente (LLM precisa propor nome completo
baseado em contexto/semantica).

CRITICAL: depende de DB (.plugadvpl/index.db) pra detectar callers
externos. Sem DB -> status=skipped.
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

_FUNCTION_DEF_RE = re.compile(
    r"\b(?:User\s+|Static\s+)?Function\s+(\w{10})\s*\(", re.IGNORECASE
)


class ExpandTruncatedNames(RecipeBase):
    id = "expand-truncated-names"
    category = "idioms"
    description = (
        "Detecta nomes truncados a 10 chars (limite ADVPL legacy) - emite todos"
    )

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        if ctx.db_connection is None:
            return RecipeResult(
                recipe_id=self.id,
                status="skipped",
                message="DB nao disponivel - execute 'plugadvpl ingest'",
            )
        matches = list(_FUNCTION_DEF_RE.finditer(content))
        if not matches:
            return RecipeResult(recipe_id=self.id, status="nochange")
        todos: list[str] = []
        for m in matches:
            name = m.group(1)
            cursor = ctx.db_connection.execute(
                "SELECT COUNT(*) FROM chamadas "
                "WHERE destino = ? AND origem_arquivo != ?",
                (name.upper(), str(ctx.file_path)),
            )
            callers = int(cursor.fetchone()[0])
            if callers > 0:
                todos.append(
                    f"expand-truncated-names: {name} tem {callers} caller(s) "
                    f"externos - coordene rename antes de expandir"
                )
            else:
                todos.append(
                    f"expand-truncated-names: {name} eh candidato a expansao "
                    f"(sem callers externos) - LLM proponha nome completo"
                )
        return RecipeResult(
            recipe_id=self.id,
            status="needs-review",
            new_content=content,
            todo_markers=todos,
        )
