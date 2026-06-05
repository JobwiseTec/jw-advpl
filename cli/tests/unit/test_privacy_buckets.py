"""Testes da bucketização ciente do campo (Fase 2.1).

Valor financeiro vira FAIXA nomeada (ex.: 48000 -> "~10k-100k"); número
estrutural (linha/cc/loc) é mantido; identificador continua tokenizado.
Opt-in (``bucketize``), desligado por padrão.
"""

from __future__ import annotations

from plugadvpl.privacy import PrivacyConfig, mask_for_egress
from plugadvpl.privacy.buckets import bucket, is_financial_field, try_bucket

CNPJ = "11.222.333/0001-81"


def _cfg() -> PrivacyConfig:
    return PrivacyConfig(enabled=True, bucketize=True)


class TestBucketFunction:
    def test_faixas(self) -> None:
        assert bucket(500) == "~<1k"
        assert bucket(5000) == "~1k-10k"
        assert bucket(48000) == "~10k-100k"
        assert bucket(250000) == "~100k-1M"
        assert bucket(5_000_000) == "~1M-10M"
        assert bucket(50_000_000) == "~10M-100M"
        assert bucket(500_000_000) == "~>=100M"

    def test_zero_e_negativo(self) -> None:
        assert bucket(0) == "~0"
        assert bucket(-48000) == "~-10k-100k"


class TestCampoFinanceiro:
    def test_positivos(self) -> None:
        for c in ("A1_LC", "ZZ3_VLBASE", "C5_VALBRUT", "A1_SALDUP", "E1_SALDO", "B1_PRECO"):
            assert is_financial_field(c), c

    def test_negativos(self) -> None:
        for c in ("linha", "A1_COD", "A1_NOME", "A1_EST", "funcao", "arquivo", "ZZ3_STATUS"):
            assert not is_financial_field(c), c


class TestTryBucket:
    def test_int_float(self) -> None:
        assert try_bucket(48000) == "~10k-100k"
        assert try_bucket(48000.50) == "~10k-100k"

    def test_string_plain(self) -> None:
        assert try_bucket("48000") == "~10k-100k"

    def test_string_ptbr(self) -> None:
        assert try_bucket("48.000,50") == "~10k-100k"

    def test_string_decimal(self) -> None:
        assert try_bucket("48000.50") == "~10k-100k"

    def test_nao_numerico(self) -> None:
        assert try_bucket("ABC") is None
        assert try_bucket("") is None

    def test_bool_nao_e_numero(self) -> None:
        assert try_bucket(True) is None


class TestColunaConsciente:
    def test_coluna_financeira_bucketizada(self) -> None:
        rows = [{"A1_LC": 50000, "linha": 42}]
        masked, counts = mask_for_egress(rows, _cfg())
        assert masked[0]["A1_LC"] == "~10k-100k"
        assert masked[0]["linha"] == 42  # estrutural mantido
        assert counts["valor"] == 1

    def test_numero_estrutural_mantido(self) -> None:
        rows = [{"linha": 42, "cc": 352, "loc": 1654}]
        masked, _ = mask_for_egress(rows, _cfg())
        assert masked[0] == {"linha": 42, "cc": 352, "loc": 1654}

    def test_identificador_ainda_tokenizado(self) -> None:
        rows = [{"A1_CGC": CNPJ, "A1_LC": 50000}]
        masked, _ = mask_for_egress(rows, _cfg())
        assert CNPJ not in str(masked[0]["A1_CGC"])
        assert masked[0]["A1_LC"] == "~10k-100k"

    def test_string_em_coluna_financeira(self) -> None:
        rows = [{"E1_VALOR": "1.234.567,89"}]
        masked, _ = mask_for_egress(rows, _cfg())
        assert masked[0]["E1_VALOR"] == "~1M-10M"

    def test_bucketize_off_mantem_numeros(self) -> None:
        rows = [{"A1_LC": 50000}]
        masked, _ = mask_for_egress(rows, PrivacyConfig(enabled=True, bucketize=False))
        assert masked[0]["A1_LC"] == 50000

    def test_privacy_off_nao_bucketiza(self) -> None:
        rows = [{"A1_LC": 50000}]
        masked, _ = mask_for_egress(rows, PrivacyConfig(enabled=False, bucketize=True))
        assert masked[0]["A1_LC"] == 50000


class TestFromEnv:
    def test_default_off(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("PLUGADVPL_PRIVACY_BUCKETIZE", raising=False)
        assert PrivacyConfig.from_env().bucketize is False

    def test_on(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("PLUGADVPL_PRIVACY_BUCKETIZE", "1")
        assert PrivacyConfig.from_env(enabled_override=True).bucketize is True
