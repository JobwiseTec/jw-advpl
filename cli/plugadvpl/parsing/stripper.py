"""Mini-tokenizer: substitui comentários e strings por espaços, preservando offsets.

Roda antes das regex de extração para evitar falso-positivos em código comentado
ou dentro de strings literais. Padrão da indústria (ProLeap COBOL faz idem).
"""
from __future__ import annotations


def strip_advpl(content: str) -> str:
    """Retorna content com comentários (// e /* */) e strings ("...", '...') substituídos por espaços.

    Preserva:
    - Tamanho total (len(out) == len(content))
    - Newlines e contagem de linhas
    - Offsets de tokens não-comentário (regex pode usar match.start() na saída e
      mapear de volta para a posição original sem ajuste)

    Limitações:
    - Macros `&var.` (substituição runtime) não são resolvidas — impossível estaticamente
    - Não detecta strings raw/multilinha (ADVPL não tem)
    """
    out: list[str] = []
    i, n = 0, len(content)
    state = "code"
    while i < n:
        c = content[i]
        if state == "code":
            if c == "/" and i + 1 < n and content[i + 1] == "/":
                state = "line_comment"
                out.append("  ")
                i += 2
                continue
            if c == "/" and i + 1 < n and content[i + 1] == "*":
                state = "block_comment"
                out.append("  ")
                i += 2
                continue
            if c == '"':
                state = "str_dq"
                out.append(" ")
                i += 1
                continue
            if c == "'":
                state = "str_sq"
                out.append(" ")
                i += 1
                continue
            out.append(c)
        elif state == "line_comment":
            if c == "\n":
                state = "code"
                out.append("\n")
            else:
                out.append(" ")
        elif state == "block_comment":
            if c == "*" and i + 1 < n and content[i + 1] == "/":
                state = "code"
                out.append("  ")
                i += 2
                continue
            out.append(" " if c != "\n" else "\n")
        elif state in ("str_dq", "str_sq"):
            quote = '"' if state == "str_dq" else "'"
            if c == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if c == quote:
                state = "code"
                out.append(" ")
            else:
                out.append(" " if c != "\n" else "\n")
        i += 1
    return "".join(out)
