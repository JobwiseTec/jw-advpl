"""Geração do INI sugerido (corrigido) a partir do texto original + findings.

Função pura: recebe o conteúdo original do INI e a lista de itens a corrigir
(``section`` / ``key`` / ``expected``) e devolve o INI reescrito —
preservando comentários e formatação. Chave recomendada que diverge vira
``[CORRECAO]``; chave crítica ausente é injetada **dentro da seção existente**
(sem recriar a seção duplicada); só seções inexistentes viram bloco novo no fim.
O BOM herdado é removido (Protheus exige ANSI/CP1252 sem BOM).
"""

from __future__ import annotations

import re
from typing import Any

_SECTION_RE = re.compile(r"^\[(.+)\]$")
_KV_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*=\s*(.*)$")


def generate_suggested_ini(original_text: str, items: list[dict[str, Any]]) -> str:  # noqa: PLR0912, PLR0915 -- reescrita linha-a-linha preservando formatacao (classifica/aplica correcao/adicao/injecao); dividir espalharia o estado do parser
    """Reescreve o INI aplicando correções e injetando chaves faltantes.

    ``items``: ``[{"section": str, "key": str, "expected": str}, ...]`` —
    tipicamente os findings ativos critical/warning cuja regra tem ``expected``.
    """
    raw_lines = original_text.splitlines()

    # 1. Mapa de presença (seção_low, chave_low) -> True a partir do texto.
    present: set[tuple[str, str]] = set()
    cur: str | None = None
    for line in raw_lines:
        stripped = line.strip()
        m_sec = _SECTION_RE.match(stripped)
        if m_sec:
            cur = m_sec.group(1).lower()
            continue
        m_kv = _KV_RE.match(stripped)
        if m_kv and cur is not None:
            present.add((cur, m_kv.group(1).lower()))

    # 2. Classifica cada item: correção (chave existe) vs adição (ausente).
    corrections: dict[tuple[str, str], str] = {}
    additions: dict[str, list[tuple[str, str]]] = {}  # section_low -> [(key, expected)]
    add_section_name: dict[str, str] = {}  # section_low -> nome original (case)
    for it in items:
        section = str(it.get("section", ""))
        key = str(it.get("key", ""))
        expected = str(it.get("expected", ""))
        if not expected or not key:
            continue
        sec_low = section.lower()
        if (sec_low, key.lower()) in present:
            corrections[(sec_low, key.lower())] = expected
        else:
            additions.setdefault(sec_low, []).append((key, expected))
            add_section_name.setdefault(sec_low, section)

    # 3. Reescreve preservando o original.
    out: list[str] = []
    seen: set[str] = set()
    cur = None

    def _inject(section_low: str) -> None:
        adds = additions.pop(section_low, None)
        if not adds:
            return
        trailing: list[str] = []
        while out and (not out[-1].strip() or out[-1].strip().startswith((";", "#"))):
            trailing.append(out.pop())
        for key, expected in adds:
            out.append(f"{key}={expected}  ; [ADICIONADO] chave critica recomendada")
        out.extend(reversed(trailing))

    for line in raw_lines:
        stripped = line.strip()
        m_sec = _SECTION_RE.match(stripped)
        if m_sec:
            if cur is not None:
                _inject(cur.lower())
            cur = m_sec.group(1)
            seen.add(cur.lower())
            out.append(line)
            continue
        m_kv = _KV_RE.match(stripped)
        if m_kv and cur is not None:
            corr = corrections.get((cur.lower(), m_kv.group(1).lower()))
            if corr is not None:
                out.append(f"{m_kv.group(1)}={corr}  ; [CORRECAO] valor anterior: {m_kv.group(2)}")
                continue
        out.append(line)

    if cur is not None:
        _inject(cur.lower())

    # 4. Seções inexistentes no original → bloco novo no fim.
    leftover = [s for s in additions if s not in seen]
    if leftover:
        out.append("")
        out.append("; ============================================================")
        out.append("; SECOES/CHAVES OBRIGATORIAS ADICIONADAS PELO AUDITOR")
        out.append("; ============================================================")
        for sec_low in leftover:
            out.append(f"\n[{add_section_name.get(sec_low, sec_low)}]")
            for key, expected in additions[sec_low]:
                out.append(f"{key}={expected}  ; [ADICIONADO] chave critica recomendada")

    return "\n".join(out).lstrip("﻿")


__all__ = ["generate_suggested_ini"]
