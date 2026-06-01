"""Dicionário de semântica contextual de campos SX (issue #27).

Alguns campos têm significado não-óbvio que muda conforme um discriminador
(outro campo como TIPO/PODER3). Catálogo curado (lookups/campos_semantica.json),
só com semântica PADRÃO Protheus — sem termo de negócio de cliente.
"""
from __future__ import annotations

import json
from importlib import resources as ir
from typing import Any


def load_semantica_catalog() -> list[dict[str, Any]]:
    """Carrega o catálogo campos_semantica do lookup embarcado (sem precisar de DB/ingest)."""
    raw = (
        ir.files("plugadvpl")
        .joinpath("lookups", "campos_semantica.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(raw)


def lookup_semantica(catalog: list[dict[str, Any]], campo: str) -> list[dict[str, Any]]:
    """Retorna as entradas de semântica para um campo (match case-insensitive)."""
    alvo = campo.strip().upper()
    return [e for e in catalog if str(e.get("campo", "")).upper() == alvo]
