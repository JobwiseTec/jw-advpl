"""Guardião do catálogo lookups/poui_interfaces.json (#96).

Invariantes:
1. Toda entrada tem as colunas obrigatórias.
2. `chave` == f"{interface_nome}:{propriedade}" (PK sintética reproduzível).
3. `valores` é JSON de lista de strings.
4. `opcional` ∈ {0, 1}.
5. `chave` única.
6. Ancoras verificadas contra a fonte: PoTableColumn tem 18 props e o `type`
   enumera exatamente os 14 valores; PoPageAction herda props de PoDropdownAction.
"""

from __future__ import annotations

import json
from importlib import resources as ir

import pytest


@pytest.fixture(scope="module")
def interfaces() -> list[dict]:
    text = (
        ir.files("plugadvpl").joinpath("lookups/poui_interfaces.json").read_text(encoding="utf-8")
    )
    return json.loads(text)


def test_campos_obrigatorios(interfaces: list[dict]) -> None:
    required = {
        "chave",
        "interface_nome",
        "propriedade",
        "tipo",
        "opcional",
        "valores",
        "herdado_de",
    }
    offenders = [i for i, e in enumerate(interfaces) if not required.issubset(e.keys())]
    assert not offenders, f"{len(offenders)} entradas sem campos obrigatórios: {offenders[:5]}"


def test_chave_pk_reproduzivel(interfaces: list[dict]) -> None:
    offenders = [
        f"{e.get('chave')!r} != {e.get('interface_nome')}:{e.get('propriedade')}"
        for e in interfaces
        if e.get("chave") != f"{e.get('interface_nome')}:{e.get('propriedade')}"
    ]
    assert not offenders, f"{len(offenders)} chaves inconsistentes: {offenders[:5]}"


def test_valores_e_json_lista(interfaces: list[dict]) -> None:
    offenders = []
    for e in interfaces:
        try:
            v = json.loads(e["valores"])
        except (json.JSONDecodeError, TypeError):
            offenders.append(e.get("chave"))
            continue
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            offenders.append(e.get("chave"))
    assert not offenders, f"{len(offenders)} entradas com `valores` inválido: {offenders[:5]}"


def test_opcional_binario(interfaces: list[dict]) -> None:
    offenders = [e.get("chave") for e in interfaces if e.get("opcional") not in (0, 1)]
    assert not offenders, f"{len(offenders)} entradas com `opcional` não-binário: {offenders[:5]}"


def test_chaves_unicas(interfaces: list[dict]) -> None:
    seen: set[str] = set()
    dupes = [k for e in interfaces if (k := e.get("chave", "")) in seen or seen.add(k)]
    assert not dupes, f"{len(dupes)} chaves duplicadas: {dupes[:5]}"


def test_quantidade_minima(interfaces: list[dict]) -> None:
    ifaces = {e["interface_nome"] for e in interfaces}
    assert len(interfaces) > 1500, f"catálogo suspeito — {len(interfaces)} props"
    assert len(ifaces) > 150, f"catálogo suspeito — {len(ifaces)} interfaces"


def test_ancora_po_table_column(interfaces: list[dict]) -> None:
    """PoTableColumn: 18 props e o `type` enumera os 14 valores conhecidos."""
    props = [e for e in interfaces if e["interface_nome"] == "PoTableColumn"]
    assert len(props) == 18, f"PoTableColumn deveria ter 18 props, tem {len(props)}"
    tipo = next((e for e in props if e["propriedade"] == "type"), None)
    assert tipo is not None
    vals = json.loads(tipo["valores"])
    assert vals == [
        "boolean",
        "currency",
        "date",
        "dateTime",
        "detail",
        "icon",
        "label",
        "link",
        "number",
        "string",
        "subtitle",
        "time",
        "cellTemplate",
        "columnTemplate",
    ], vals


def test_ancora_extends_resolvido(interfaces: list[dict]) -> None:
    """PoPageAction herda props de PoDropdownAction (ex.: `label`, `action`)."""
    pa = {e["propriedade"]: e for e in interfaces if e["interface_nome"] == "PoPageAction"}
    assert "label" in pa and "action" in pa, "PoPageAction sem props herdadas"
    assert pa["label"]["herdado_de"] == "PoDropdownAction", pa["label"]["herdado_de"]
    assert pa["kind"]["herdado_de"] == "", "kind é próprio de PoPageAction"
