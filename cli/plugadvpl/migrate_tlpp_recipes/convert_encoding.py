"""Recipe: convert-encoding (canonical order 1, SAFE).

Converte conteúdo lido como cp1252 pra utf-8. Por design, é nochange
quando arquivo já está em utf-8 OU já tem extensão .tlpp. Delega
detection ao edit_prw.detect_encoding.

CONTRATO (esclarecimento spec-reviewer):

Esta recipe é peculiar — conversão real é I/O-level (bytes), não
string-level. **Quem faz a decodificação cp1252 é o orquestrador**
(Task 15c, ``dry_run``), que lê bytes raw E decodifica ANTES de
chamar qualquer recipe. Esta recipe ``convert-encoding`` é apenas
**marker** que sinaliza no ``MigrationReport`` que essa decodificação
ocorreu como parte do pipeline canônico.

Net effect: o pipeline produz arquivo ``.tlpp`` em utf-8 mesmo com
recipe ``convert-encoding`` retornando ``nochange``. Suficiente pra
MVP. Refactor pra recipe fazer transformação real fica pra v0.19.x.
"""

from __future__ import annotations

from plugadvpl.migrate_tlpp_recipes import MigrationContext, RecipeBase, RecipeResult


class ConvertEncoding(RecipeBase):
    id = "convert-encoding"
    category = "safe"
    description = "Converte conteúdo de cp1252 pra utf-8 (idempotente se já utf-8)"

    def apply(self, content: str, ctx: MigrationContext) -> RecipeResult:  # noqa: ARG002
        # Se path já é .tlpp, assume conversão já feita
        if ctx.file_path.suffix.lower() == ".tlpp":
            return RecipeResult(recipe_id=self.id, status="nochange")
        # Content vem como string Python — orquestrador faz I/O.
        # Recipe só sinaliza "precisa write" se vai mudar; aqui só normaliza newlines.
        # Re-encode happens na escrita via edit_prw.convert_and_save.
        # NOTA: detection real fica no orquestrador (precisa raw bytes).
        return RecipeResult(recipe_id=self.id, status="nochange")
