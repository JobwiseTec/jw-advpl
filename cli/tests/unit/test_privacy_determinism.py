"""Garantia de DETERMINISMO do pipeline de mascaramento.

Requisito: mesmo input -> mesma saída, sempre. Tokenização (HMAC), bucketização e
classificação são puras e estáveis — entre execuções e entre instâncias. É o que
garante que a resposta após mascaramento/relativização não varie nem dê errado.
"""

from __future__ import annotations

from plugadvpl.privacy import PrivacyConfig, mask_for_egress
from plugadvpl.privacy.buckets import bucket, picture_class

ROWS = [
    {
        "arquivo": "ABC.prw",
        "linha": 42,
        "A1_CGC": "11.222.333/0001-81",
        "A1_CPF": "111.444.777-35",
        "A1_MAIL": "fin@empresa.com.br",
        "A1_MSBLQL": "2",
        "A1_LC": 50000,
        "A1_SALDUP": 51500,
        "trecho": 'cSenha := "Tr0ub4dor3"',
    }
]


def _cfg() -> PrivacyConfig:
    return PrivacyConfig(enabled=True, bucketize=True, style="label")


class TestPipelineDeterministico:
    def test_mesma_saida_em_repeticoes(self) -> None:
        a, ca = mask_for_egress(ROWS, _cfg())
        b, cb = mask_for_egress(ROWS, _cfg())
        assert a == b
        assert ca == cb

    def test_instancias_distintas_mesma_chave(self) -> None:
        # dois "processos" (instâncias) com a mesma chave -> tokens idênticos
        a, _ = mask_for_egress(ROWS, _cfg())
        b, _ = mask_for_egress(ROWS, _cfg())
        assert a[0]["A1_CGC"] == b[0]["A1_CGC"]
        assert a[0]["A1_CPF"] == b[0]["A1_CPF"]

    def test_idempotente_estruturalmente(self) -> None:
        # estrutura preservada e estável; não-sensível inalterado
        masked, _ = mask_for_egress(ROWS, _cfg())
        assert masked[0]["arquivo"] == "ABC.prw"
        assert masked[0]["linha"] == 42
        assert masked[0]["A1_MSBLQL"] == "2"

    def test_fpe_deterministico(self) -> None:
        cfg = PrivacyConfig(enabled=True, style="fpe")
        a, _ = mask_for_egress(ROWS, cfg)
        b, _ = mask_for_egress(ROWS, cfg)
        assert a == b


class TestFuncoesPuras:
    def test_bucket_deterministico(self) -> None:
        assert bucket(48000) == bucket(48000) == "~10k-100k"

    def test_picture_class_deterministico(self) -> None:
        for _ in range(3):
            assert picture_class("@E 999,999.99") == "money"
            assert picture_class("@E 999999.999") == "volume"
            assert picture_class("@E 99.99") == "rate"

    def test_style_label_vs_fpe_consistente(self) -> None:
        c_label = PrivacyConfig(enabled=True, style="label")
        c_fpe = PrivacyConfig(enabled=True, style="fpe")
        # cada estilo é estável consigo mesmo
        assert mask_for_egress(ROWS, c_label)[0] == mask_for_egress(ROWS, c_label)[0]
        assert mask_for_egress(ROWS, c_fpe)[0] == mask_for_egress(ROWS, c_fpe)[0]
