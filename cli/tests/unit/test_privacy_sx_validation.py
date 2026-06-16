"""Validação da bucketização contra padrões REAIS de SX3/SX7 das bases.

Os casos abaixo são sintéticos mas derivados dos padrões reais observados nos
dicionários SX dos projetos (campos PADRÃO TOTVS, públicos — sem nome de cliente
nem tabela custom). Cada cliente tem ~30 casos: campos de valor (devem ser
classificados financeiros) e não-valor (devem ser mantidos).

Conclusão medida em SX3 real: a heurística por NOME pega ~66% dos campos
monetários; a via SX3-backed (X3_TIPO='N' com decimais) bate ~100%. Ambas testadas.
"""

from __future__ import annotations

import pytest

from plugadvpl.privacy import PrivacyConfig, mask_for_egress
from plugadvpl.privacy.buckets import financial_fields_from_sx3, is_financial_field

# (campo PADRÃO TOTVS, é_valor_financeiro?) — heurística por nome
FISCAL_NFE = [
    ("F2_VALMERC", True), ("F2_VALICM", True), ("F2_VALIPI", True), ("F2_VALIRRF", True),
    ("F2_VALBRUT", True), ("F2_FRETE", True), ("F2_SEGURO", True), ("F2_DESPESA", True),
    ("F2_BASEICM", True), ("D2_TOTAL", True), ("D2_PRCVEN", True), ("D2_VALIPI", True),
    ("D2_VALICM", True), ("D2_BASEICM", True), ("D1_TOTAL", True), ("D1_SEGURO", True),
    ("D1_FRETE", True), ("D1_VALICM", True), ("D1_DESPESA", True), ("F1_VALBRUT", True),
    ("F2_DOC", False), ("F2_SERIE", False), ("F2_CLIENTE", False), ("D2_ITEM", False),
    ("D2_QUANT", False), ("D2_TES", False), ("D1_COD", False), ("A1_CGC", False),
    ("A1_INSCR", False), ("D2_GRADE", False),
]

FINANCEIRO_TITULOS = [
    ("E1_VALOR", True), ("E1_SALDO", True), ("E1_JUROS", True), ("E1_MULTA", True),
    ("E1_DESCONT", True), ("E1_VLCRUZ", True), ("E1_VLREAL", True), ("E2_VALOR", True),
    ("E2_VALJUR", True), ("E2_SALDO", True), ("C6_VALOR", True), ("C6_PRCVEN", True),
    ("C6_VALDESC", True), ("D1_TOTAL", True), ("A1_LC", True), ("A1_SALDUP", True),
    ("A1_LCFIN", True), ("E5_VALOR", True), ("F2_VALMERC", True), ("D2_TOTAL", True),
    ("A1_COD", False), ("A1_NOME", False), ("A1_CGC", False), ("A1_EMAIL", False),
    ("E1_PREFIXO", False), ("E1_NUM", False), ("E1_TIPO", False), ("C6_PRODUTO", False),
    ("C6_QUANT", False), ("E1_VENCTO", False),
]

CONTRATOS = [
    ("CNB_VLTOT", True), ("CN9_VLTOT", True), ("CNA_VLTOT", True), ("CNB_VLUNIT", True),
    ("E1_VALOR", True), ("E1_SALDO", True), ("E3_VALOR", True), ("E3_BASE", True),
    ("E3_COMIS", True), ("E3_VLBASE", True), ("E1_VLCRUZ", True), ("A1_LC", True),
    ("A1_SALDUP", True), ("E1_JUROS", True), ("E1_MULTA", True), ("CNB_PRCUNI", True),
    ("CNB_TOTAL", True), ("E3_VLTOT", True), ("CNA_PRCTOT", True), ("E1_DESCONT", True),
    ("CN9_NUMERO", False), ("CN9_CLIENTE", False), ("CNB_PRODUTO", False), ("CNB_ITEM", False),
    ("CNB_QUANT", False), ("CN9_SITUAC", False), ("A1_MSBLQL", False), ("A1_CGC", False),
    ("E1_PREFIXO", False), ("CN9_TPCTO", False),
]


class TestFiscalNfe:
    @pytest.mark.parametrize(("campo", "esperado"), FISCAL_NFE)
    def test_classificacao(self, campo: str, esperado: bool) -> None:
        assert is_financial_field(campo) is esperado


class TestFinanceiroTitulos:
    @pytest.mark.parametrize(("campo", "esperado"), FINANCEIRO_TITULOS)
    def test_classificacao(self, campo: str, esperado: bool) -> None:
        assert is_financial_field(campo) is esperado


class TestContratos:
    @pytest.mark.parametrize(("campo", "esperado"), CONTRATOS)
    def test_classificacao(self, campo: str, esperado: bool) -> None:
        assert is_financial_field(campo) is esperado


SX3_SAMPLE = [
    {"X3_CAMPO": "D2_QUANT", "X3_TIPO": "N", "X3_DECIMAL": "2"},
    {"X3_CAMPO": "F2_VALIRRF", "X3_TIPO": "N", "X3_DECIMAL": "2"},
    {"X3_CAMPO": "A1_LC", "X3_TIPO": "N", "X3_DECIMAL": "2"},
    {"X3_CAMPO": "A1_COD", "X3_TIPO": "C", "X3_DECIMAL": "0"},
    {"X3_CAMPO": "E1_VENCTO", "X3_TIPO": "D", "X3_DECIMAL": "0"},
    {"X3_CAMPO": "C6_ITEM", "X3_TIPO": "C", "X3_DECIMAL": "0"},
]


class TestSX3Backed:
    """A via exata: classificar pela verdade do dicionário (X3_TIPO='N' + decimais)."""

    def test_extrai_so_campos_de_valor(self) -> None:
        fields = financial_fields_from_sx3(SX3_SAMPLE)
        assert fields == frozenset({"D2_QUANT", "F2_VALIRRF", "A1_LC"})

    def test_sx3_pega_o_que_heuristica_perde(self) -> None:
        # D2_QUANT (quantidade) a heurística NÃO pega; via SX3 (N+decimais) pega
        fields = financial_fields_from_sx3(SX3_SAMPLE)
        assert not is_financial_field("D2_QUANT")  # heurística
        assert is_financial_field("D2_QUANT", fields)  # SX3-backed

    def test_char_e_data_nao_entram(self) -> None:
        fields = financial_fields_from_sx3(SX3_SAMPLE)
        assert "A1_COD" not in fields
        assert "E1_VENCTO" not in fields


class TestBucketizeEndToEnd:
    def test_registro_misto_heuristica(self) -> None:
        cfg = PrivacyConfig(enabled=True, bucketize=True)
        rows = [{
            "A1_CGC": "11.222.333/0001-81",
            "A1_MSBLQL": "2",
            "A1_LC": 50000,
            "A1_SALDUP": 51500,
            "linha": 42,
        }]
        masked, counts = mask_for_egress(rows, cfg)
        assert "11.222.333" not in str(masked[0]["A1_CGC"])
        assert masked[0]["A1_MSBLQL"] == "2"
        assert masked[0]["A1_LC"] == "~10k-100k"
        assert masked[0]["A1_SALDUP"] == "~10k-100k"
        assert masked[0]["linha"] == 42
        assert counts["valor"] == 2

    def test_registro_sx3_backed(self) -> None:
        # com o set do SX3, até quantidade (N+decimais) é bucketizada
        fields = frozenset({"A1_LC", "A1_SALDUP", "D2_QUANT"})
        cfg = PrivacyConfig(enabled=True, bucketize=True, financial_fields=fields)
        rows = [{"A1_LC": 50000, "A1_SALDUP": 51500, "D2_QUANT": 1500, "C6_PRODUTO": "ABC123"}]
        masked, _ = mask_for_egress(rows, cfg)
        assert masked[0]["A1_LC"] == "~10k-100k"
        assert masked[0]["D2_QUANT"] == "~1k-10k"
        assert masked[0]["C6_PRODUTO"] == "ABC123"  # não-valor mantido

    def test_string_monetaria_ptbr(self) -> None:
        cfg = PrivacyConfig(enabled=True, bucketize=True)
        rows = [{"D2_TOTAL": "1.234.567,89"}]
        masked, _ = mask_for_egress(rows, cfg)
        assert masked[0]["D2_TOTAL"] == "~1M-10M"


class TestSX7Gatilhos:
    """Gatilhos SX7 (X7_REGRA/X7_CHAVE) — expressões com campo/chave; o valor real
    do campo não está no fonte, então a regra fica estrutural (intacta). Só literal
    sensível embutido é mascarado.
    """

    def test_regra_gatilho_referencia_campo_intacta(self) -> None:
        # X7_CHAVE típico: xFilial + campo + If(...) — sem literal sensível
        rule = 'xFilial("SA2")+M->A5_FORNECE+If(nModulo==17,EicRetLoja("M"),"")'
        assert is_financial_field("A5_FORNECE") is False  # campo de chave, não valor
        cfg = PrivacyConfig(enabled=True, bucketize=True)
        masked, _ = mask_for_egress([{"X7_CHAVE": rule}], cfg)
        assert masked[0]["X7_CHAVE"] == rule  # estrutura da regra intacta

    def test_regra_com_cnpj_literal_mascarado(self) -> None:
        rule = 'If(A1_CGC=="11.222.333/0001-81",.T.,.F.)'
        cfg = PrivacyConfig(enabled=True)
        masked, _ = mask_for_egress([{"X7_REGRA": rule}], cfg)
        assert "11.222.333/0001-81" not in str(masked[0]["X7_REGRA"])
        assert "A1_CGC==" in str(masked[0]["X7_REGRA"])


# Campos de PEDIDO/PRODUTO/ESTOQUE (padrão TOTVS) — valores e não-valores.
PEDIDO_PRODUTO = [
    ("C6_VALOR", True), ("C6_PRCVEN", True), ("C6_PRUNIT", True), ("C6_VALDESC", True),
    ("B1_PRV1", True), ("B1_PRV2", True), ("B1_UPRC", True), ("B1_CUSTD", True),
    ("B1_CUSTO", True), ("D1_VUNIT", True), ("D2_PRUNIT", True), ("B2_VATU1", True),
    ("B2_VATU2", True), ("D2_TOTAL", True), ("D2_PRCVEN", True), ("C6_VALICM", True),
    ("C6_QUANT", False), ("D2_PESO", False), ("D2_IPI", False), ("B1_PICM", False),
    ("D1_ALIQICM", False), ("C6_PRODUTO", False), ("C6_ITEM", False), ("B1_DESC", False),
    ("C6_NUM", False), ("B1_COD", False), ("B2_LOCAL", False), ("C6_TES", False),
]


class TestPedidoProduto:
    """Valores de pedido/produto/estoque — a heurística melhorada (prefixo PRV/PRU
    + tokens UNIT/UPRC/VATU/CUST) cobre os padrões comuns; nomes idiossincráticos
    (ZDSC/ABAT/CM) precisam da via SX3 por PICTURE (ver TestSX3PictureMoney).
    """

    @pytest.mark.parametrize(("campo", "esperado"), PEDIDO_PRODUTO)
    def test_classificacao(self, campo: str, esperado: bool) -> None:
        assert is_financial_field(campo) is esperado


# SX3 com PICTURE: dinheiro tem agrupamento de milhar (vírgula); alíquota/peso não.
SX3_PIC = [
    {"X3_CAMPO": "C6_VALOR", "X3_TIPO": "N", "X3_DECIMAL": "2", "X3_PICTURE": "@E 999,999,999.99"},
    {"X3_CAMPO": "C5_ZDSCECO", "X3_TIPO": "N", "X3_DECIMAL": "2", "X3_PICTURE": "@E 9,999,999.99"},
    {"X3_CAMPO": "B2_CM3", "X3_TIPO": "N", "X3_DECIMAL": "2", "X3_PICTURE": "@E 999,999,999.99"},
    {"X3_CAMPO": "C6_ABATISS", "X3_TIPO": "N", "X3_DECIMAL": "2", "X3_PICTURE": "@E 99,999,999.99"},
    {"X3_CAMPO": "D2_IPI", "X3_TIPO": "N", "X3_DECIMAL": "2", "X3_PICTURE": "@E 99.99"},
    {"X3_CAMPO": "D2_PESO", "X3_TIPO": "N", "X3_DECIMAL": "3", "X3_PICTURE": "@E 999999.999"},
    {"X3_CAMPO": "C6_QUANT", "X3_TIPO": "N", "X3_DECIMAL": "2", "X3_PICTURE": "@E 999999.99"},
]


class TestSX3Categories:
    """Classificação por PICTURE em money/volume/rate — escolha do que proteger.

    money (com vírgula) = R$; volume (grande sem vírgula) = peso/quantidade/estoque;
    rate (pequeno) = alíquota/percentual público.
    """

    def test_picture_class(self) -> None:
        from plugadvpl.privacy.buckets import picture_class

        assert picture_class("@E 999,999,999.99") == "money"
        assert picture_class("@E 999999.999") == "volume"
        assert picture_class("@E 99.99") == "rate"

    def test_so_dinheiro(self) -> None:
        money = financial_fields_from_sx3(SX3_PIC, categories=("money",))
        assert money == frozenset({"C6_VALOR", "C5_ZDSCECO", "B2_CM3", "C6_ABATISS"})

    def test_dinheiro_e_volume_inclui_peso_qtd(self) -> None:
        # protege R$ E peso/quantidade (volume de negócio), excluindo alíquota
        vol = financial_fields_from_sx3(SX3_PIC, categories=("money", "volume"))
        assert "D2_PESO" in vol
        assert "C6_QUANT" in vol
        assert "C6_VALOR" in vol
        assert "D2_IPI" not in vol  # alíquota (rate) fora

    def test_broad_inclui_tudo_numerico(self) -> None:
        allnum = financial_fields_from_sx3(SX3_PIC)  # default: todos N+decimais
        for c in ("C6_VALOR", "D2_PESO", "C6_QUANT", "D2_IPI"):
            assert c in allnum

    def test_picture_pega_o_que_o_nome_perde(self) -> None:
        money = financial_fields_from_sx3(SX3_PIC, categories=("money",))
        # ZDSC/ABAT/CM: heurística por nome NÃO pega; PICTURE pega
        assert not is_financial_field("C5_ZDSCECO")
        assert not is_financial_field("C6_ABATISS")
        assert "C5_ZDSCECO" in money
        assert "C6_ABATISS" in money
