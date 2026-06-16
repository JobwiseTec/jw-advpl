"""Testes da camada de privacidade (Fase 1 — mascaramento no egress).

Massa fictícia: CPF/CNPJ válidos de teste conhecidos, e-mail, senha hardcoded.
Verifica: (a) nada sensível sobrevive; (b) token estável; (c) segredo
irreversível; (d) checksum rejeita inválido; (e) desligado = sem efeito.
"""

from __future__ import annotations

from plugadvpl.privacy import PrivacyConfig, mask_for_egress
from plugadvpl.privacy.brdocs import valid_cnpj, valid_cpf
from plugadvpl.privacy.engine import Masker

# CPF/CNPJ de teste com dígitos verificadores corretos (sintéticos, públicos).
VALID_CPF = "111.444.777-35"
VALID_CNPJ = "11.222.333/0001-81"
INVALID_CPF = "111.444.777-00"  # mesmo corpo, DV errado


def _masker() -> Masker:
    return Masker(PrivacyConfig(enabled=True))


class TestChecksum:
    def test_valid_cpf(self) -> None:
        assert valid_cpf(VALID_CPF)
        assert valid_cpf("11144477735")

    def test_invalid_cpf_rejected(self) -> None:
        assert not valid_cpf(INVALID_CPF)
        assert not valid_cpf("111.111.111-11")  # sequência repetida

    def test_valid_cnpj(self) -> None:
        assert valid_cnpj(VALID_CNPJ)
        assert valid_cnpj("11222333000181")

    def test_invalid_cnpj_rejected(self) -> None:
        assert not valid_cnpj("11.222.333/0001-99")


class TestMaskText:
    def test_cpf_tokenized(self) -> None:
        out = _masker().mask_text(f"cliente CPF {VALID_CPF} ok")
        assert VALID_CPF not in out
        assert "11144477735" not in out
        assert "CPF_" in out

    def test_cnpj_tokenized(self) -> None:
        out = _masker().mask_text(f"matriz {VALID_CNPJ}")
        assert VALID_CNPJ not in out
        assert "CNPJ_" in out

    def test_email_tokenized(self) -> None:
        out = _masker().mask_text("contato fin@empresa.com.br aqui")
        assert "fin@empresa.com.br" not in out
        assert "EMAIL_" in out

    def test_invalid_cpf_not_touched(self) -> None:
        # checksum reprova → não vira token (evita falso-positivo)
        out = _masker().mask_text(f"codigo {INVALID_CPF}")
        assert INVALID_CPF in out

    def test_secret_redacted_irreversible(self) -> None:
        out = _masker().mask_text('cSenha := "Tr0ub4dor3"  // senha=Tr0ub4dor3')
        assert "Tr0ub4dor3" not in out
        assert "REDACTED" in out

    def test_structural_text_untouched(self) -> None:
        # nome de função/tabela/parâmetro NÃO é identificador → fica intacto
        text = "User Function FA040GRV() lê SE1 grava ZZ3 via MV_XPCOM01"
        assert _masker().mask_text(text) == text

    def test_token_stable_same_value(self) -> None:
        m = _masker()
        assert m.mask_text(VALID_CNPJ) == m.mask_text(VALID_CNPJ)

    def test_token_stable_across_maskers(self) -> None:
        # processos diferentes (mesma chave) → mesmo token
        a = Masker(PrivacyConfig(enabled=True))
        b = Masker(PrivacyConfig(enabled=True))
        assert a.mask_text(VALID_CPF) == b.mask_text(VALID_CPF)

    def test_distinct_values_distinct_tokens(self) -> None:
        m = _masker()
        assert m.mask_text(VALID_CPF) != m.mask_text("529.982.247-25")


class TestMaskRows:
    def test_structure_preserved_values_masked(self) -> None:
        rows = [{"arquivo": "ABC.prw", "linha": 42, "trecho": f"cCgc := '{VALID_CNPJ}'"}]
        masked, counts = mask_for_egress(rows, PrivacyConfig(enabled=True))
        assert masked[0]["arquivo"] == "ABC.prw"  # estrutura intacta
        assert masked[0]["linha"] == 42  # não-string intacto
        assert VALID_CNPJ not in str(masked[0]["trecho"])
        assert counts["cnpj"] == 1

    def test_nested_list_and_dict(self) -> None:
        rows = [{"tags": [f"cpf:{VALID_CPF}"], "meta": {"x": VALID_CNPJ}}]
        masked, _ = mask_for_egress(rows, PrivacyConfig(enabled=True))
        flat = str(masked)
        assert VALID_CPF not in flat
        assert VALID_CNPJ not in flat

    def test_audit_has_no_real_value(self) -> None:
        rows = [{"t": f"{VALID_CPF} {VALID_CNPJ}"}]
        _, counts = mask_for_egress(rows, PrivacyConfig(enabled=True))
        assert counts["cpf"] == 1
        assert counts["cnpj"] == 1
        # o Counter só tem tipos, nunca o valor
        assert VALID_CPF not in str(counts)


class TestDisabled:
    def test_disabled_config_default(self) -> None:
        assert PrivacyConfig().enabled is False

    def test_from_env_default_off(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("PLUGADVPL_PRIVACY", raising=False)
        assert PrivacyConfig.from_env().enabled is False

    def test_from_env_on(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("PLUGADVPL_PRIVACY", "1")
        assert PrivacyConfig.from_env().enabled is True

    def test_cli_override_wins(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("PLUGADVPL_PRIVACY", "1")
        assert PrivacyConfig.from_env(enabled_override=False).enabled is False


class TestDevKeyWarning:
    """dev_key_warning — aviso de chave-dev previsível (auditoria A4)."""

    def test_warns_when_enabled_with_dev_key(self) -> None:
        from plugadvpl.privacy import dev_key_warning

        cfg = PrivacyConfig(enabled=True)  # key default, key_explicit=False
        msg = dev_key_warning(cfg)
        assert msg is not None
        assert "PLUGADVPL_PRIVACY_KEY" in msg

    def test_silent_when_key_explicit(self) -> None:
        from plugadvpl.privacy import dev_key_warning

        cfg = PrivacyConfig(enabled=True, key=b"x" * 32, key_explicit=True)
        assert dev_key_warning(cfg) is None

    def test_silent_when_disabled(self) -> None:
        from plugadvpl.privacy import dev_key_warning

        assert dev_key_warning(PrivacyConfig(enabled=False)) is None
