"""Guardião do catálogo lookups/poui_componentes.json.

Invariantes:
1. Toda entrada tem as colunas obrigatórias: chave, componente, kind, binding, propriedade.
2. `binding` começa com 'p-'.
3. `kind` ∈ {input, output}.
4. `chave` == f"{componente}:{kind}:{binding}" (PK sintética reproduzível).
"""

from __future__ import annotations

import json
from importlib import resources as ir

import pytest


@pytest.fixture(scope="module")
def componentes() -> list[dict]:
    """Carrega o catálogo via importlib.resources (funciona em dev-tree e wheel)."""
    text = (
        ir.files("plugadvpl").joinpath("lookups/poui_componentes.json").read_text(encoding="utf-8")
    )
    return json.loads(text)


def test_todas_entradas_tem_campos_obrigatorios(componentes: list[dict]) -> None:
    """Toda entrada deve ter as 5 colunas obrigatórias."""
    required = {"chave", "componente", "kind", "binding", "propriedade"}
    offenders = [
        i
        for i, e in enumerate(componentes)
        if not required.issubset(e.keys())
    ]
    assert not offenders, (
        f"{len(offenders)} entradas sem campos obrigatórios (índices): {offenders[:5]}"
    )


def test_binding_comeca_com_p_hifen(componentes: list[dict]) -> None:
    """Todo `binding` deve começar com 'p-' (convenção PO UI)."""
    offenders = [
        e.get("chave", f"idx:{i}")
        for i, e in enumerate(componentes)
        if not str(e.get("binding", "")).startswith("p-")
    ]
    assert not offenders, (
        f"{len(offenders)} entradas com binding sem prefixo 'p-': {offenders[:5]}"
    )


def test_kind_valido(componentes: list[dict]) -> None:
    """`kind` deve ser exatamente 'input' ou 'output'."""
    valid = {"input", "output"}
    offenders = [
        e.get("chave", f"idx:{i}")
        for i, e in enumerate(componentes)
        if e.get("kind") not in valid
    ]
    assert not offenders, (
        f"{len(offenders)} entradas com kind inválido: {offenders[:5]}"
    )


def test_chave_e_pk_sintetica_reproduzivel(componentes: list[dict]) -> None:
    """`chave` deve ser exatamente '{componente}:{kind}:{binding}'."""
    offenders = []
    for e in componentes:
        expected = f"{e.get('componente')}:{e.get('kind')}:{e.get('binding')}"
        if e.get("chave") != expected:
            offenders.append(f"{e.get('chave')!r} != {expected!r}")
    assert not offenders, (
        f"{len(offenders)} entradas com chave inconsistente: {offenders[:5]}"
    )


def test_quantidade_minima_de_bindings(componentes: list[dict]) -> None:
    """Catálogo deve ter pelo menos 900 bindings (sanidade do build_poui_catalog.py)."""
    assert len(componentes) > 900, (
        f"Catálogo suspeito — apenas {len(componentes)} bindings (esperado > 900)"
    )


def test_chaves_unicas(componentes: list[dict]) -> None:
    """Não deve haver `chave` duplicada no catálogo."""
    seen: set[str] = set()
    dupes: list[str] = []
    for e in componentes:
        k = e.get("chave", "")
        if k in seen:
            dupes.append(k)
        seen.add(k)
    assert not dupes, f"{len(dupes)} chaves duplicadas: {dupes[:5]}"
