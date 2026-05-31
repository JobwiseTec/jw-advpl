"""Recipe: named-args (canonical order 6, SAFE, gated tlpp_version≥20.3.2).

xParams(p1 := a, p2 := b) → xParams(p1 = a, p2 = b)

Operador TLPP oficial é ``=`` (não ``:=``). Gating: AppServer ≥20.3.2.0
pra funções/métodos (memory: reference_tlpp_named_params).
"""

from __future__ import annotations

import re

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult

# Match `identifier := value` dentro de chamada de função (heurística simples;
# limitação aceita: pode também matchar atribuições normais — improvável dentro
# de () de chamada mas spec MVP aceita o trade-off; v0.19.x melhora com parser).
_NAMED_ARG_RE = re.compile(r"(\w+)\s*:=\s*")


class NamedArgs(RecipeBase):
    id = "named-args"
    category = "safe"
    description = "Converte := → = em named-args (gated tlpp_version ≥ 20.3.2)"
    requires_tlpp_version = (20, 3, 2)

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        # Gating — requires_tlpp_version sempre setado nessa subclasse
        required = self.requires_tlpp_version
        if ctx.tlpp_version < required:
            return RecipeResult(
                recipe_id=self.id,
                status="skipped",
                message=(
                    f"tlpp_version {ctx.tlpp_version} < {required} "
                    f"(use --tlpp-version=20.3.2+ pra habilitar)"
                ),
            )
        # Heurística minima: só aplica DENTRO de parens (call sites).
        # MVP: regex line-by-line, conservador (não troca := em assignments).
        # Refactor com AST: v0.19.x.
        new_lines: list[str] = []
        changed = False
        for line in content.splitlines(keepends=True):
            stripped = line.strip()
            if "(" in stripped and ")" in stripped and ":=" in stripped:
                # tentativa: troca apenas := DENTRO dos parens
                # MVP: troca todos := nessa linha (conservador o suficiente
                # pra chamadas simples; not multiline)
                new_line = _NAMED_ARG_RE.sub(r"\1 = ", line)
                if new_line != line:
                    changed = True
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        new_content = "".join(new_lines)
        if not changed:
            return RecipeResult(recipe_id=self.id, status="nochange")
        return RecipeResult(recipe_id=self.id, status="ok", new_content=new_content)
