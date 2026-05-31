"""Recipe: user-function-lowercase (canonical order 5, SAFE).

User Function FATA050() → function u_fata050()

CRITICAL caveat (spec §3.5): se função TEM callers externos E nome
está truncado a 10 chars (típico ADVPL clássico), MANTÉM nome truncado
e adiciona @plugadvpl-todo marker. Sem DB populated, default conservador.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

if TYPE_CHECKING:
    import sqlite3

_USER_FUNCTION_RE = re.compile(r"\bUser\s+Function\s+(\w+)\s*\(", re.IGNORECASE)


def _count_external_callers(
    funcao_name: str,
    file_path: str,
    db_conn: sqlite3.Connection | None,
) -> int:
    """Conta callers de funcao_name em arquivos DIFERENTES de file_path.

    Retorna -1 se DB não está disponível (signal pro caller).
    """
    if db_conn is None:
        return -1
    cursor = db_conn.execute(
        "SELECT COUNT(*) FROM chamadas WHERE destino = ? AND origem_arquivo != ?",
        (funcao_name.upper(), file_path),
    )
    return int(cursor.fetchone()[0])


class UserFunctionLowercase(RecipeBase):
    id = "user-function-lowercase"
    category = "safe"
    description = (
        "User Function X() → function u_x() (preserva nome truncado se há callers externos)"
    )

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        todos: list[str] = []

        def replace(match: re.Match[str]) -> str:
            original_name = match.group(1)
            external_callers = _count_external_callers(
                original_name, str(ctx.file_path), ctx.db_connection
            )
            if external_callers == -1:
                # Sem DB — modo conservador: preserva nome E emite todo
                todos.append(
                    f"user-function-lowercase: preserva {original_name} "
                    f"(DB não disponível; confirme manualmente antes de expandir)"
                )
                return f"function u_{original_name.lower()}("
            if external_callers > 0:
                todos.append(
                    f"user-function-lowercase: {original_name} tem "
                    f"{external_callers} caller(s) externo(s) — preserva nome truncado"
                )
                return f"function u_{original_name.lower()}("
            # OK — sem callers externos, pode lowercase livre
            return f"function u_{original_name.lower()}("

        new_content = _USER_FUNCTION_RE.sub(replace, content)
        if new_content == content:
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(
            recipe_id=self.id,
            status="needs-review" if todos else "ok",
            new_content=new_content,
            todo_markers=todos,
        )
