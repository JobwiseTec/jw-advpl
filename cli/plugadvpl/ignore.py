"""Matcher de padrões de exclusão na ingestão (.plugadvplignore + --exclude).

Subconjunto do .gitignore (issue #141). Suporta:
- ``dir/``           — diretório e tudo abaixo, em qualquer nível
- ``nome`` / ``*.x`` — match por basename em qualquer nível (sem ``/`` no padrão)
- ``a/**/b.prw``     — match do path relativo (com ``/``), ``**`` cruza níveis

NÃO suporta (fora de escopo desta fase): negação ``!``, classes ``[...]``.
Match sempre sobre path relativo à raiz com separador ``/`` (normalizado).
Sem dependência nova — usa ``fnmatch`` da stdlib.
"""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_IGNORE_FILENAME = ".plugadvplignore"


class IgnoreMatcher:
    """Decide se um path relativo deve ser ignorado na ingestão."""

    def __init__(self, patterns: list[str]) -> None:
        self._dir_patterns: list[str] = []  # 'descontinuado' (sem barra final)
        self._basename_patterns: list[str] = []  # '*_old.prw'
        self._path_patterns: list[str] = []  # 'a/**/b.prw'
        for raw in patterns:
            pat = raw.strip()
            if not pat or pat.startswith("#"):
                continue
            if pat.endswith("/"):
                self._dir_patterns.append(pat.rstrip("/"))
            elif "/" in pat:
                self._path_patterns.append(pat)
            else:
                self._basename_patterns.append(pat)

    @property
    def pattern_count(self) -> int:
        return len(self._dir_patterns) + len(self._basename_patterns) + len(self._path_patterns)

    def _norm(self, rel_path: str) -> str:
        return rel_path.replace("\\", "/").lstrip("/")  # \\ = UM backslash literal

    def matches(self, rel_path: str) -> bool:
        """True se o ARQUIVO em ``rel_path`` (relativo à raiz) deve ser ignorado."""
        if self.pattern_count == 0:
            return False
        norm = self._norm(rel_path)
        parts = norm.split("/")
        # dir/ — algum componente de diretório (todos menos o basename) casa
        dirs = parts[:-1]
        for dp in self._dir_patterns:
            if any(fnmatch.fnmatch(d, dp) for d in dirs):
                return True
        # basename
        base = parts[-1]
        for bp in self._basename_patterns:
            if fnmatch.fnmatch(base, bp):
                return True
        # path completo (** cruza níveis)
        return any(_path_match(norm, pp) for pp in self._path_patterns)

    def matches_dir(self, rel_dir: str) -> bool:
        """True se o DIRETÓRIO ``rel_dir`` casa um dir-pattern.

        Disponível como API (testada) para uso futuro; o ``scan`` NÃO usa este
        método — ele filtra arquivo a arquivo via :meth:`matches` para que o
        conjunto de ignorados (prune/contagem) seja capturado corretamente.
        """
        if not self._dir_patterns:
            return False
        norm = self._norm(rel_dir)
        parts = norm.split("/")
        return any(fnmatch.fnmatch(part, dp) for part in parts for dp in self._dir_patterns)


def _path_match(path: str, pattern: str) -> bool:
    """Match de path com suporte a ``**`` cruzando ``/``.

    ``fnmatch`` trata ``*`` como casando ``/`` também, então ``a/**/b`` e
    ``a/*/b`` se comportam de forma equivalente pro nosso uso (cobrir N níveis).
    Tornamos isso explícito normalizando ``**`` -> ``*``.
    """
    norm_pattern = pattern.replace("**", "*")
    return fnmatch.fnmatch(path, norm_pattern)


def load_ignore_file(root: Path) -> list[str]:
    """Lê ``<root>/.plugadvplignore`` e devolve as linhas. ``[]`` se ausente/ilegível."""
    f = root / _IGNORE_FILENAME
    if not f.is_file():
        return []
    try:
        return f.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
