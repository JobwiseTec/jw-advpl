"""Recipe: rename-extension (canonical order 2, SAFE).

Marca arquivo .prw/.prx pra rename .tlpp. O rename físico (Path.rename)
é feito pelo orquestrador na fase de write — esta recipe apenas sinaliza
intent e propaga o conteúdo inalterado.
"""

from __future__ import annotations

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult


class RenameExtension(RecipeBase):
    id = "rename-extension"
    category = "safe"
    description = "Marca arquivo .prw pra rename .tlpp (orquestrador faz rename físico)"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:
        suffix = ctx.file_path.suffix.lower()
        if suffix == ".tlpp":
            return RecipeResult(recipe_id=self.id, status="nochange", message="já é .tlpp")
        if suffix not in (".prw", ".prx"):
            return RecipeResult(
                recipe_id=self.id,
                status="skipped",
                message=f"extensão {suffix} fora do escopo",
            )
        # OK — orquestrador faz Path.rename
        return RecipeResult(
            recipe_id=self.id,
            status="ok",
            new_content=content,
            message=f"renomear {ctx.file_path.name} → {ctx.file_path.stem}.tlpp",
        )
