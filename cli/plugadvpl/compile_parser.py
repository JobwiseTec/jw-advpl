"""Parser de saída do advpls. Função pura (sem subprocess, sem fs).

Spec: docs/fase1/compile-design.md §7.8, §8.

Estratégia:
- Aplica regex patterns de lookups/compile_patterns.json em ordem (`ordem` ASC).
- Linhas não-classificadas viram Diagnostic(severidade='unknown').
- Normaliza Diagnostic.arquivo via Path.resolve() vs requested_files.
- Aplica redact_patterns.json em Diagnostic.raw antes de devolver.
"""
from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass
from importlib import resources as ir
from pathlib import Path


@dataclass(frozen=True)
class Diagnostic:
    severidade: str          # error | warning | info | unknown
    arquivo: str
    linha: int
    coluna: int
    mensagem: str
    codigo: str
    raw: str

    def to_dict(self) -> dict[str, object]:
        return {
            "severidade": self.severidade,
            "arquivo": self.arquivo,
            "linha": self.linha,
            "coluna": self.coluna,
            "mensagem": self.mensagem,
            "codigo": self.codigo,
            "raw": self.raw,
        }


def parse_diagnostics(
    stdout: str,
    stderr: str,
    mode: str,
    requested_files: list[Path],
) -> tuple[list[Diagnostic], list[Diagnostic]]:
    """Parseia output do advpls.

    Returns:
        ``(matched, unmatched)`` onde:

        - ``matched`` contém TODAS as linhas relevantes para os arquivos
          solicitados, incluindo:
            * diagnostics estruturados (error/warning/info) com arquivo em
              ``requested_files``
            * linhas que NENHUM pattern reconheceu, viram
              ``Diagnostic(severidade='unknown', arquivo='', linha=0, raw=<linha>)``.
              Nunca silencia.
        - ``unmatched`` contém APENAS diagnostics estruturados cujo arquivo
          NÃO bate com nenhum requested_file após ``Path.resolve()``. Vão
          para bucket ``__unmatched__`` no resultado final.
    """
    raise NotImplementedError("será implementado nos próximos steps")
