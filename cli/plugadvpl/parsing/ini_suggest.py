"""Geração do INI sugerido (corrigido) a partir do texto original + findings.

Função pura: recebe o conteúdo original do INI, a lista de itens a corrigir
(``section`` / ``key`` / ``expected`` / ``severidade``) e as chaves não
reconhecidas, e devolve o INI reescrito — preservando comentários e formatação.

Regras (idênticas ao motor de referência):

* **Correção** — chave presente cujo valor diverge do recomendado (severidade
  ``critical`` **ou** ``warning``) vira ``; [CORRECAO]``.
* **Adição** — apenas chave **crítica** ausente é injetada **dentro da seção
  existente** (sem recriar a seção duplicada); seção inexistente vira bloco novo
  no fim. Chave ``warning`` ausente **não** é injetada.
* **Revisão** — chave não reconhecida (fora do catálogo) é **comentada** com
  ``; [REVISAR]``, sem removê-la.

O BOM herdado é removido (Protheus exige ANSI/CP1252 sem BOM).
"""

from __future__ import annotations

import re
from typing import Any

_SECTION_RE = re.compile(r"^\[(.+)\]$")
_KV_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*=\s*(.*)$")


def generate_suggested_ini(  # noqa: PLR0912, PLR0915 -- reescrita linha-a-linha preservando formatacao (classifica/aplica correcao/adicao/comenta-unknown/injecao); dividir espalharia o estado do parser
    original_text: str,
    items: list[dict[str, Any]],
    unknown_keys: list[dict[str, Any]] | None = None,
) -> str:
    """Reescreve o INI aplicando correções, comentando chaves não reconhecidas
    e injetando chaves críticas faltantes.

    ``items``: ``[{"section": str, "key": str, "expected": str,
    "severidade": str, "descricao": str}, ...]`` — findings ativos
    critical/warning. Severidade ausente assume ``critical`` (compat). Só
    ``critical`` ausente é injetada; ``warning`` ausente é descartada.
    ``descricao`` (opcional) vai no comentário ``[ADICIONADO]``.

    ``unknown_keys``: ``[{"section": str, "key_name": str}, ...]`` — chaves fora
    do catálogo, que serão comentadas com ``; [REVISAR]``.
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

    # Chaves não reconhecidas → comentar com [REVISAR] (case-insensitive).
    unknown_set: set[tuple[str, str]] = set()
    for uk in unknown_keys or []:
        usec = str(uk.get("section", ""))
        ukey = str(uk.get("key_name") or uk.get("key") or "")
        if ukey:
            unknown_set.add((usec.lower(), ukey.lower()))

    # 2. Classifica cada item: correção (chave existe, qualquer severidade) vs
    #    adição (ausente — só injeta se for CRÍTICA; warning ausente é descartado).
    corrections: dict[tuple[str, str], str] = {}
    # section_low -> [(key, expected, descricao)]
    additions: dict[str, list[tuple[str, str, str]]] = {}
    add_section_name: dict[str, str] = {}  # section_low -> nome original (case)
    for it in items:
        section = str(it.get("section", ""))
        key = str(it.get("key", ""))
        expected = str(it.get("expected", ""))
        severidade = str(it.get("severidade", "critical")).lower()
        descricao = str(it.get("descricao", ""))
        if not expected or not key:
            continue
        sec_low = section.lower()
        if (sec_low, key.lower()) in present:
            corrections[(sec_low, key.lower())] = expected
        elif severidade == "critical":
            additions.setdefault(sec_low, []).append((key, expected, descricao))
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
        for key, expected, descricao in adds:
            out.append(f"{key}={expected}  ; [ADICIONADO] {descricao}".rstrip())
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
            key_pair = (cur.lower(), m_kv.group(1).lower())
            corr = corrections.get(key_pair)
            if corr is not None:
                out.append(f"{m_kv.group(1)}={corr}  ; [CORRECAO] valor anterior: {m_kv.group(2)}")
                continue
            if key_pair in unknown_set:
                out.append(f";{m_kv.group(1)}={m_kv.group(2)}  ; [REVISAR] chave nao reconhecida")
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
            for key, expected, descricao in additions[sec_low]:
                out.append(f"{key}={expected}  ; [ADICIONADO] {descricao}".rstrip())

    return "\n".join(out).lstrip("﻿")


__all__ = ["generate_suggested_ini"]
