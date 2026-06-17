"""Golden snapshot + determinismo + lint do .prw emitido pelo aplicador de SXs."""

from __future__ import annotations

from plugadvpl.aplicador_sx import gen_prw

_SPEC_SX3 = {
    "numero": "099999",
    "sx3": [
        {"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Codigo"},
        {"alias": "ZXX", "campo": "ZXX_DESC", "tipo": "C", "tamanho": 40, "titulo": "Descricao"},
    ],
}

# Tabela do zero: SX2 (1 tabela) + SX3 (2 campos) + SIX (1 indice de filial).
_SPEC_TABELA = {
    "numero": "099998",
    "sx2": [{"alias": "ZXX", "nome": "Cadastro X"}],
    "sx3": [
        {"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Codigo"},
        {"alias": "ZXX", "campo": "ZXX_DESC", "tipo": "C", "tamanho": 40, "titulo": "Descricao"},
    ],
    "six": [
        {
            "alias": "ZXX",
            "ordem": "1",
            "chave": "ZXX_FILIAL+ZXX_COD",
            "descricao": "Filial+Cod",
        }
    ],
}


# Spec completo: 1+ entrada de CADA um dos 8 tipos (sintetico ZXX / MV_X*).
_SPEC_COMPLETO = {
    "numero": "099997",
    "sx2": [{"alias": "ZXX", "nome": "Cadastro X"}],
    "sx3": [
        {"alias": "ZXX", "campo": "ZXX_FILIAL", "tipo": "C", "tamanho": 2, "titulo": "Filial"},
        {"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Codigo"},
        {"alias": "ZXX", "campo": "ZXX_DESC", "tipo": "C", "tamanho": 40, "titulo": "Descricao"},
    ],
    "six": [
        {
            "alias": "ZXX",
            "ordem": "1",
            "chave": "ZXX_FILIAL+ZXX_COD",
            "descricao": "Filial+Cod",
        }
    ],
    "sx6": [
        {
            "var": "MV_XCUST1",
            "tipo": "C",
            "conteudo": "1",
            "descric": "Parametro custom X",
        }
    ],
    "sx7": [
        {
            "campo": "ZXX_COD",
            "sequenc": "001",
            "cdomin": "ZXX_DESC",
            "regra": "Posicione('ZXX',1,xFilial('ZXX')+M->ZXX_COD,'ZXX_DESC')",
        }
    ],
    "sx1": [
        {
            "grupo": "ZXXPRG",
            "ordem": "01",
            "pergunta": "Tipo de processamento?",
            "variavel": "MV_X0",
            "tipo": "N",
            "opcoes": [
                {"var": "MV_PAR01", "def": "Sintetico", "cnt": "1"},
                {"var": "MV_PAR02", "def": "Analitico", "cnt": "2"},
            ],
        }
    ],
    "sxa": [{"alias": "ZXX", "ordem": "01", "descricao": "Cadastrais"}],
    "sx5": [{"tabela": "ZX", "chave": "01", "descricao": "Item generico X"}],
}


def test_golden_sx3(snapshot):
    assert gen_prw(_SPEC_SX3) == snapshot


def test_golden_tabela(snapshot):
    assert gen_prw(_SPEC_TABELA) == snapshot


def test_golden_completo(snapshot):
    assert gen_prw(_SPEC_COMPLETO) == snapshot


def test_determinismo_2x_identico():
    assert gen_prw(_SPEC_SX3) == gen_prw(_SPEC_SX3)
    assert gen_prw(_SPEC_TABELA) == gen_prw(_SPEC_TABELA)
    assert gen_prw(_SPEC_COMPLETO) == gen_prw(_SPEC_COMPLETO)


def test_completo_tem_8_fsatu_defs_e_8_calls():
    import re

    prw = gen_prw(_SPEC_COMPLETO)
    tipos = ("SX2", "SX3", "SIX", "SX6", "SX7", "SX1", "SXA", "SX5")
    # 8 defs FSAtu* (uma por tipo)
    for t in tipos:
        assert f"Static Function FSAtu{t}(" in prw
    # 8 chamadas FSAtu*() no FSTProc, na ordem canonica
    idxs = [prw.index(f"FSAtu{t}()") for t in tipos]
    assert idxs == sorted(idxs)
    # SetRegua1 = 8 FSAtu* + FSAtuHlp = 9
    m = re.search(r"SetRegua1\(\s*(\d+)\s*\)", prw)
    assert m and int(m.group(1)) == 9


def test_completo_advpl_bem_formado():
    # Verifica que cada Static Function FSAtu* gerada esta bem formada:
    # If/EndIf e For/Next balanceados e termina em Return. As FSAtu* geradas nao
    # usam ternario `If(` (so blocos `If <cond>`/EndIf), entao a contagem e exata.
    import re

    from plugadvpl.aplicador_sx.emit import emit_fsatu

    tipos = {
        "sx2": _SPEC_COMPLETO["sx2"],
        "sx3": _SPEC_COMPLETO["sx3"],
        "six": _SPEC_COMPLETO["six"],
        "sx6": _SPEC_COMPLETO["sx6"],
        "sx7": _SPEC_COMPLETO["sx7"],
        "sx1": _SPEC_COMPLETO["sx1"],
        "sxa": _SPEC_COMPLETO["sxa"],
        "sx5": _SPEC_COMPLETO["sx5"],
    }
    for tipo, entradas in tipos.items():
        fn = emit_fsatu(tipo, entradas)
        assert len(re.findall(r"\bIf\b", fn)) == len(re.findall(r"\bEndIf\b", fn)), tipo
        assert len(re.findall(r"\bFor\b", fn)) == len(re.findall(r"\bNext\b", fn)), tipo
        assert fn.rstrip().endswith("Return NIL"), tipo
        # aAdd bem formado: abre e fecha o mesmo numero de blocos
        assert fn.count("aAdd( aSX") + fn.count("aAdd( aSIX") >= len(entradas), tipo


def _parse_and_lint(prw: str) -> list[dict]:
    from plugadvpl.parsing.lint import lint_source
    from plugadvpl.parsing.parser import (
        add_function_ranges,
        extract_functions,
        extract_sql_embedado,
    )

    parsed = {
        "arquivo": "aplicador.prw",
        "funcoes": add_function_ranges(extract_functions(prw), prw),
        "sql_embedado": extract_sql_embedado(prw),
    }
    return lint_source(parsed, prw)


def test_emitido_passa_no_lint_sem_bp_sec():
    for spec in (_SPEC_SX3, _SPEC_TABELA, _SPEC_COMPLETO):
        findings = _parse_and_lint(gen_prw(spec))
        graves = [f for f in findings if f["regra_id"].split("-")[0] in ("PERF", "SQL", "MOD")]
        assert graves == [], graves


def test_regua_bate_com_chamadas_fsatu():
    import re

    for spec in (_SPEC_SX3, _SPEC_TABELA, _SPEC_COMPLETO):
        prw = gen_prw(spec)
        chamadas = len(re.findall(r"^\s*FSAtu\w+\(\)\s*$", prw, re.M))
        m = re.search(r"SetRegua1\(\s*(\d+)\s*\)", prw)
        assert m and int(m.group(1)) == chamadas


def test_tabela_inclui_fsatu_sx2_six_e_calls():
    prw = gen_prw(_SPEC_TABELA)
    # defs das tres funcoes FSAtu*
    assert "Static Function FSAtuSX2(" in prw
    assert "Static Function FSAtuSX3(" in prw
    assert "Static Function FSAtuSIX(" in prw
    # chamadas no FSTProc, na ordem canonica (sx2, sx3, six)
    assert prw.index("FSAtuSX2()") < prw.index("FSAtuSX3()") < prw.index("FSAtuSIX()")
    # SetRegua1 incrementada: 3 FSAtu* + FSAtuHlp = 4
    import re

    m = re.search(r"SetRegua1\(\s*(\d+)\s*\)", prw)
    assert m and int(m.group(1)) == 4


def test_zero_token_de_cliente():
    for spec in (_SPEC_SX3, _SPEC_TABELA, _SPEC_COMPLETO):
        prw = gen_prw(spec).lower()
        for tok in ("marfrig", "taura", "wellington", "ernani", "forastieri", "mgf_", "expordic"):
            assert tok not in prw
        assert "d:\\clientes" not in prw
