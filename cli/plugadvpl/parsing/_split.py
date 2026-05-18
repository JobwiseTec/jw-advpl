"""Helper compartilhado pra split de args top-level (v0.4.6 G).

Antes esse split estava duplicado em ``triggers.py``, ``execauto.py``,
``protheus_doc.py`` com pequenas diferenças (strings respeitadas ou não,
``max_parts`` ou não). Unificado aqui pra eliminar drift.
"""
from __future__ import annotations


def split_top_level_commas(s: str, max_parts: int = -1) -> list[str]:
    """Split de ``s`` por vírgulas top-level.

    Ignora vírgulas dentro de ``()``, ``{}``, ``[]`` e dentro de strings
    literais (``"..."``, ``'...'``). Respeitar strings é seguro mesmo
    quando o caller passa conteúdo já stripado (sem strings reais), porque
    não há aspas pra abrir state.

    Args:
        s: conteúdo a fatiar.
        max_parts: número máximo de partes (>= 1). Se atingido, o resto
            volta como última parte sem mais splits. ``-1`` (default) =
            sem limite.
    """
    parts: list[str] = []
    depth_paren = depth_brace = depth_bracket = 0
    in_str: str | None = None
    last = 0
    count = 0
    for i, c in enumerate(s):
        if in_str:
            if c == in_str:
                in_str = None
            continue
        if c in ("'", '"'):
            in_str = c
        elif c == "(":
            depth_paren += 1
        elif c == ")":
            depth_paren -= 1
        elif c == "{":
            depth_brace += 1
        elif c == "}":
            depth_brace -= 1
        elif c == "[":
            depth_bracket += 1
        elif c == "]":
            depth_bracket -= 1
        elif (
            c == ","
            and depth_paren == 0
            and depth_brace == 0
            and depth_bracket == 0
        ):
            parts.append(s[last:i])
            last = i + 1
            count += 1
            if max_parts > 0 and count >= max_parts - 1:
                break
    parts.append(s[last:])
    return parts
