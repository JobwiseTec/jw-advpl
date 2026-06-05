"""Testes do motor de relativização (diagnose) — foco em EXATIDÃO e determinismo.

O desfecho (VERDADEIRO/FALSO) tem que ser exato sobre os valores reais; só a
exibição dos números sensíveis vira razão. Nunca pode dar resultado errado.
"""

from __future__ import annotations

import pytest

from plugadvpl.privacy.diagnose import diagnose

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


class TestCenarioReal:
    def test_bloqueia(self) -> None:
        rec = {
            "A1_MSBLQL": "2", "A1_LC": 50000, "A1_SALDUP": 28500,
            "nSaldo": 21500, "nValPed": 30000, "MV_X_LIBLIM": "N",
        }
        res = diagnose(ABCLIBPED, rec)
        assert len(res) == 3
        assert res[0].comparisons[0].outcome is False  # bloqueio manual? não
        assert res[1].comparisons[0].outcome is True  # 51500 > 50000
        assert res[2].comparisons[0].outcome is True  # MV_X_LIBLIM = N

    def test_libera(self) -> None:
        rec = {"A1_MSBLQL": "2", "A1_LC": 50000, "nSaldo": 1000, "nValPed": 5000}
        res = diagnose(ABCLIBPED, rec)
        assert res[1].comparisons[0].outcome is False  # 6000 > 50000 -> não


class TestExatidao:
    @pytest.mark.parametrize(
        ("op", "left", "right", "esperado"),
        [
            (">", 51500, 50000, True), (">", 50000, 50000, False), (">", 49999, 50000, False),
            ("<", 1, 2, True), (">=", 50000, 50000, True), ("<=", 50000, 50001, True),
            ("==", 5, 5, True), ("!=", 5, 6, True), ("<>", 5, 5, False),
        ],
    )
    def test_operadores_exatos(self, op: str, left: int, right: int, esperado: bool) -> None:
        res = diagnose(f"If A1_VALOR {op} A1_LC", {"A1_VALOR": left, "A1_LC": right})
        assert res[0].comparisons[0].outcome is esperado

    def test_boundary_exato(self) -> None:
        # igual -> ">" é FALSO; +1 -> VERDADEIRO (sem erro de fronteira)
        assert diagnose("If A1_SALDUP > A1_LC", {"A1_SALDUP": 50000, "A1_LC": 50000})[
            0
        ].comparisons[0].outcome is False
        assert diagnose("If A1_SALDUP > A1_LC", {"A1_SALDUP": 50001, "A1_LC": 50000})[
            0
        ].comparisons[0].outcome is True

    def test_expr_aritmetica_exata(self) -> None:
        # (saldo + pedido) calculado exato
        res = diagnose("If ( nSaldo + nValPed ) > A1_LC", {
            "nSaldo": 21500, "nValPed": 28500, "A1_LC": 50000,
        })
        assert res[0].comparisons[0].outcome is False  # 50000 > 50000 -> não


class TestRelativizacao:
    def test_razao_nao_vaza_valor(self) -> None:
        res = diagnose("If A1_SALDUP > A1_LC", {"A1_SALDUP": 51500, "A1_LC": 50000})
        c = res[0].comparisons[0]
        assert c.outcome is True
        assert "103%" in c.explain
        assert "51500" not in c.explain  # valor real NÃO aparece
        assert "50000" not in c.explain
        assert "VERDADEIRO" in c.explain

    def test_flag_mostra_valor(self) -> None:
        # status não é sensível -> mostrado para a IA raciocinar
        c = diagnose('If A1_MSBLQL == "1"', {"A1_MSBLQL": "2"})[0].comparisons[0]
        assert c.outcome is False
        assert "A1_MSBLQL=2" in c.explain

    def test_campo_financeiro_via_sx3(self) -> None:
        # campo idiossincrático: vira financeiro pelo set SX3 -> relativiza
        res = diagnose(
            "If ZZ_X > A1_LC", {"ZZ_X": 51500, "A1_LC": 50000},
            financial_fields=frozenset({"ZZ_X"}),
        )
        c = res[0].comparisons[0]
        assert c.outcome is True
        assert "103%" in c.explain
        assert "51500" not in c.explain


class TestNaoChuta:
    def test_campo_ausente_outcome_none(self) -> None:
        res = diagnose("If A1_LC > 1000", {})
        assert res[0].comparisons[0].outcome is None

    def test_getmv_ausente_none(self) -> None:
        res = diagnose('If SuperGetMV("MV_X") == "S"', {})
        assert res[0].comparisons[0].outcome is None

    def test_getmv_resolvido(self) -> None:
        res = diagnose('If SuperGetMV("MV_X") == "S"', {"MV_X": "S"})
        assert res[0].comparisons[0].outcome is True

    def test_call_desconhecida_none(self) -> None:
        res = diagnose("If AlgumaFunc() > A1_LC", {"A1_LC": 50000})
        assert res[0].comparisons[0].outcome is None


class TestDeterminismo:
    def test_mesma_saida(self) -> None:
        rec = {"A1_SALDUP": 51500, "A1_LC": 50000, "A1_MSBLQL": "2"}
        assert diagnose(ABCLIBPED, rec) == diagnose(ABCLIBPED, rec)

    def test_ordem_estavel(self) -> None:
        res = diagnose(ABCLIBPED, {"A1_LC": 50000})
        assert [d.line for d in res] == sorted(d.line for d in res)
