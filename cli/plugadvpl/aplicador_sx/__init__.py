"""Aplicador de SXs: gerador determinístico de .prw de update de dicionários.

A partir de um spec JSON (numero + listas sx3/...), emite um .prw byte-estável
com boilerplate fixo + funções FSAtu* geradas. Sem LLM, sem random/Date.

Re-exports (preenchidos ao longo do Chunk 1):
- ``validate_spec``: valida o spec, retorna (erros, warnings).
- ``gen_prw``: monta o .prw final.
"""

from __future__ import annotations

from .emit import emit_prw as gen_prw
from .schema import validate_spec

__all__ = ["gen_prw", "validate_spec"]
