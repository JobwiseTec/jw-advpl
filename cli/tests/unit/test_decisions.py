"""Testes do extrator determinístico de pontos de decisão (relativização — passo 1)."""

from __future__ import annotations

from plugadvpl.parsing.decisions import extract_decisions

# Rotina real-ish de liberação de pedido (o caso "cliente bloqueado por limite").
ABCLIBPED = """\
User Function ABCLibPed( cCli, cLoja, nValPed )
    If SA1->A1_MSBLQL == "1"
        Return "BLOQUEADO"
    EndIf
    nSaldo := SA1->A1_LC - SA1->A1_SALDUP
    If ( nSaldo + nValPed ) > SA1->A1_LC
        If SuperGetMV("MV_X_LIBLIM") == "N"
            Return "BLOQUEADO"
        EndIf
    EndIf
Return "LIBERADO"
"""


class TestStatements:
    def test_if_campo_literal(self) -> None:
        ds = extract_decisions('If SA1->A1_MSBLQL == "1"')
        assert len(ds) == 1
        d = ds[0]
        assert d.kind == "if"
        assert len(d.comparisons) == 1
        c = d.comparisons[0]
        assert c.left == "SA1->A1_MSBLQL"
        assert c.op == "=="
        assert c.right == '"1"'
        assert c.left_kind == "field"
        assert c.right_kind == "literal"

    def test_elseif_e_while(self) -> None:
        ds = extract_decisions("ElseIf A1_EST == \"SP\"\nWhile nI < 10")
        assert [d.kind for d in ds] == ["elseif", "while"]

    def test_nao_decisao_ignorada(self) -> None:
        assert extract_decisions("nSaldo := A1_LC - A1_SALDUP") == []

    def test_else_if_com_espaco(self) -> None:
        ds = extract_decisions('Else If A1_TIPO == "F"')
        assert ds[0].kind == "elseif"


class TestOperadores:
    def test_todos_operadores(self) -> None:
        casos = {
            "A1_LC == 1": "==", "A1_LC != 1": "!=", "A1_LC <> 1": "<>",
            "A1_LC >= 1": ">=", "A1_LC <= 1": "<=", "A1_LC > 1": ">",
            "A1_LC < 1": "<", "A1_COD $ cLista": "$",
        }
        for cond, op in casos.items():
            ds = extract_decisions(f"If {cond}")
            assert ds[0].comparisons[0].op == op, cond

    def test_alias_arrow_nao_vira_operador(self) -> None:
        # SA1->A1_LC contém '>' que NÃO pode ser confundido com operador
        ds = extract_decisions("If SA1->A1_LC > SA1->A1_SALDUP")
        c = ds[0].comparisons[0]
        assert c.op == ">"
        assert c.left == "SA1->A1_LC"
        assert c.right == "SA1->A1_SALDUP"
        assert c.left_kind == "field"
        assert c.right_kind == "field"


class TestLogica:
    def test_and_or_split(self) -> None:
        ds = extract_decisions('If A1_EST == "SP" .And. A1_LC > 1000')
        comps = ds[0].comparisons
        assert len(comps) == 2
        assert comps[0].left == "A1_EST"
        assert comps[1].left == "A1_LC"

    def test_paren_respeitado_no_split(self) -> None:
        ds = extract_decisions('If ( A1_A == 1 .Or. A1_B == 2 ) .And. A1_C == 3')
        # split top-level: 2 cláusulas (o grupo entre parênteses + A1_C==3)
        comps = ds[0].comparisons
        assert len(comps) == 2
        assert comps[1].left == "A1_C"


class TestClassificacao:
    def test_kinds(self) -> None:
        ds = extract_decisions('If SuperGetMV("MV_X") == "N"')
        c = ds[0].comparisons[0]
        assert c.left_kind == "call"
        assert c.right_kind == "literal"

    def test_var_e_expr(self) -> None:
        ds = extract_decisions("If ( nSaldo + nValPed ) > SA1->A1_LC")
        c = ds[0].comparisons[0]
        assert c.left_kind == "expr"
        assert c.right_kind == "field"

    def test_const(self) -> None:
        ds = extract_decisions("If lAtivo == .T.")
        assert ds[0].comparisons[0].right_kind == "const"

    def test_numero_literal(self) -> None:
        ds = extract_decisions("If A1_LC > 50000")
        assert ds[0].comparisons[0].right_kind == "literal"


class TestComentario:
    def test_comentario_removido(self) -> None:
        ds = extract_decisions('If A1_MSBLQL == "1"  // bloqueio manual')
        c = ds[0].comparisons[0]
        assert "bloqueio" not in c.right
        assert c.right == '"1"'

    def test_barra_dentro_de_string_preservada(self) -> None:
        ds = extract_decisions('If A1_URL == "http://x"')
        assert ds[0].comparisons[0].right == '"http://x"'


class TestCasoReal:
    def test_abclibped(self) -> None:
        ds = extract_decisions(ABCLIBPED)
        # 3 decisões: (a) bloqueio manual, (b) estoura limite, (c) parâmetro
        assert len(ds) == 3
        assert ds[0].comparisons[0].left == "SA1->A1_MSBLQL"
        assert ds[1].comparisons[0].op == ">"
        assert ds[1].comparisons[0].right == "SA1->A1_LC"
        assert ds[2].comparisons[0].left_kind == "call"

    def test_campos_que_decidem(self) -> None:
        # quais CAMPOS decidem os branches (o valor do passo 1, sem registro)
        ds = extract_decisions(ABCLIBPED)
        campos = {
            c.left for d in ds for c in d.comparisons if c.left_kind == "field"
        } | {c.right for d in ds for c in d.comparisons if c.right_kind == "field"}
        assert "SA1->A1_MSBLQL" in campos
        assert "SA1->A1_LC" in campos


class TestDeterminismo:
    def test_mesma_saida_em_repeticoes(self) -> None:
        a = extract_decisions(ABCLIBPED)
        b = extract_decisions(ABCLIBPED)
        assert a == b  # dataclasses frozen -> igualdade estrutural estável

    def test_ordem_estavel(self) -> None:
        ds = extract_decisions(ABCLIBPED)
        assert [d.line for d in ds] == sorted(d.line for d in ds)
