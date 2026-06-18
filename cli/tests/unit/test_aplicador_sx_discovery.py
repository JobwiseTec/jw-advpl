"""Descoberta do spec p/ IAs: example_spec() + spec_schema() (auto-descrição do CLI)."""

from __future__ import annotations

from plugadvpl.aplicador_sx import example_spec, gen_prw, spec_schema, validate_spec

_TIPOS = ("sx2", "sx3", "six", "sx6", "sx7", "sx1", "sxa", "sx5")


def test_example_spec_e_valido_e_gera():
    # o exemplo tem que passar na validação (sem erros) e gerar um .prw real.
    spec = example_spec()
    erros, _ = validate_spec(spec)
    assert erros == []
    prw = gen_prw(spec)
    assert "User Function A" in prw


def test_example_spec_cobre_os_8_tipos():
    spec = example_spec()
    assert "numero" in spec
    for tipo in _TIPOS:
        assert spec.get(tipo), f"exemplo sem seção {tipo}"


def test_example_spec_deterministico():
    assert example_spec() == example_spec()


def test_spec_schema_lista_chaves_por_tipo():
    sch = spec_schema()
    for tipo in _TIPOS:
        assert tipo in sch
    # sx3: 'campo' e 'alias' são obrigatórios; 'tipo' presente
    chaves_sx3 = {c["chave"]: c for c in sch["sx3"]}
    assert chaves_sx3["campo"]["obrigatorio"] is True
    assert chaves_sx3["alias"]["obrigatorio"] is True
    # sx1: a chave especial 'opcoes' aparece (não é coluna física)
    assert any(c["chave"] == "opcoes" for c in sch["sx1"])


def test_spec_schema_sem_chave_duplicada():
    # colunas espelhadas (titulo->TITULO/TITSPA/TITENG) viram 1 chave só.
    for tipo, cols in spec_schema().items():
        chaves = [c["chave"] for c in cols]
        assert len(chaves) == len(set(chaves)), f"{tipo} tem chave duplicada"
