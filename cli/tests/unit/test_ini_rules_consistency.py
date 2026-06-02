"""Guardião do catálogo lookups/ini_rules.json (espelha test_lint_catalog_consistency).

A base de 487 regras do `ini-audit` foi gerada em lote (commit #6) sem trilha de
procedência e continha valores fabricados. Estes invariantes impedem que dado
quebrado volte ao catálogo:

1. `range_check` SEM range real (`..`) é no-op silencioso — `_evaluate_value`
   sempre retorna True (ini_audit.py). Proibido.
2. Regras `critical` `value_eq` na MESMA (seção, chave) NÃO podem recomendar
   valores contraditórios — pegava o bug TSS-SSL2/SSL3='1' (ligar protocolo
   inseguro) divergindo do APP-SSL2='0'.
3. `value_in` não pode MISTURAR token numérico com texto — pegava o enum bogus
   `MaxStringSize='1|Maior|Menor'`.
"""

from __future__ import annotations

import json
from collections import defaultdict
from importlib import resources as ir

import pytest


@pytest.fixture(scope="module")
def rules() -> list[dict]:
    text = ir.files("plugadvpl").joinpath("lookups/ini_rules.json").read_text(encoding="utf-8")
    return json.loads(text)


def test_range_check_tem_range_real(rules: list[dict]) -> None:
    """range_check sem `..` no expected é decorativo (sempre passa)."""
    offenders = [
        r["regra_id"]
        for r in rules
        if r.get("detection_kind") == "range_check" and ".." not in r.get("expected", "")
    ]
    assert not offenders, (
        f"{len(offenders)} regras range_check sem range real (expected sem '..'): "
        f"{offenders[:10]}{'...' if len(offenders) > 10 else ''}"
    )


def test_sem_gemeas_criticas_contraditorias(rules: list[dict]) -> None:
    """critical value_eq na mesma (seção, chave) deve recomendar o MESMO valor."""
    by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in rules:
        if r.get("severidade") == "critical" and r.get("detection_kind") == "value_eq":
            exp = r.get("expected", "").strip()
            if exp:
                by_key[(r["section_glob"].lower(), r["key_name"].lower())].add(exp)
    conflicts = {k: v for k, v in by_key.items() if len(v) > 1}
    assert not conflicts, (
        "Regras critical value_eq contraditórias na mesma (seção, chave): "
        + "; ".join(f"{sec}/{key}={sorted(vals)}" for (sec, key), vals in conflicts.items())
    )


def test_value_in_nao_mistura_numerico_e_texto(rules: list[dict]) -> None:
    """value_in com tokens parte-número parte-texto denuncia enum fabricado."""
    offenders = []
    for r in rules:
        if r.get("detection_kind") != "value_in":
            continue
        toks = [t.strip() for t in r.get("expected", "").split("|") if t.strip()]
        num = [t for t in toks if t.isdigit()]
        txt = [t for t in toks if not t.isdigit()]
        if num and txt:
            offenders.append(f"{r['regra_id']}={r.get('expected')!r}")
    assert not offenders, f"value_in mistura número e texto: {offenders}"


def test_value_in_tem_pelo_menos_duas_opcoes(rules: list[dict]) -> None:
    """value_in com 1 token só deveria ser value_eq."""
    offenders = [
        r["regra_id"]
        for r in rules
        if r.get("detection_kind") == "value_in"
        and len([t for t in r.get("expected", "").split("|") if t.strip()]) < 2
    ]
    assert not offenders, f"value_in com <2 opções (use value_eq): {offenders}"
