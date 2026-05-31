"""Diff utilities pra migrate-tlpp (v0.18.0+).

Wrapper sobre ``difflib.unified_diff`` pra mostrar before/after de
recipes aplicados. Colorização rich é opcional (quando saída vai pra
TTY interativo).
"""

from __future__ import annotations

import difflib


def has_changes(before: str, after: str) -> bool:
    """Boolean check rápido."""
    return before != after


def unified_diff_text(
    before: str,
    after: str,
    fromfile: str,
    tofile: str,
    *,
    context: int = 3,
) -> str:
    """Retorna unified diff como string (vazio se idêntico)."""
    if not has_changes(before, after):
        return ""
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=fromfile,
        tofile=tofile,
        n=context,
    )
    return "".join(lines)
