"""Motor de mascaramento: tokeniza identificadores e redige segredos.

Stateless entre execuções; acumula contagem por tipo (sem o valor real) para
auditoria. A pseudonimização é **estável** (mesmo valor → mesmo token, via HMAC
com a chave da sessão) e **de mão única** (não há mapa para reverter — de
propósito: o dev consulta o valor real no fonte/sistema local).
"""

from __future__ import annotations

import base64
import functools
import hmac
import json
import re
from collections import Counter
from importlib import resources as ir
from typing import TYPE_CHECKING

from .brdocs import (
    CNPJ_RE,
    CPF_RE,
    EMAIL_RE,
    IPV4_RE,
    cnpj_check_digits,
    cpf_check_digits,
    reshape,
    valid_cnpj,
    valid_cpf,
    valid_ipv4,
)
from .buckets import is_financial_field, try_bucket

if TYPE_CHECKING:
    from collections.abc import Callable

    from .config import PrivacyConfig

_DIGITS_RE = re.compile(r"\D")
_TOKEN_LEN = 10
_DIGIT_KINDS = frozenset({"cpf", "cnpj"})
_CPF_BASE_DIGITS = 9
_CNPJ_BASE_DIGITS = 12


@functools.lru_cache(maxsize=1)
def _load_secret_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    """Carrega ``lookups/redact_patterns.json`` (mesmo catálogo do compile-parser)."""
    text = (
        ir.files("plugadvpl").joinpath("lookups/redact_patterns.json").read_text(encoding="utf-8")
    )
    return tuple((re.compile(e["pattern"]), e["replacement"]) for e in json.loads(text))


class Masker:
    """Aplica a política de mascaramento sobre texto / linhas de saída."""

    def __init__(self, cfg: PrivacyConfig) -> None:
        self.cfg = cfg
        self._secret_patterns: tuple[tuple[re.Pattern[str], str], ...] = (
            _load_secret_patterns() if cfg.redact_secrets else ()
        )
        self.counts: Counter[str] = Counter()

    def _label_token(self, value: str, kind: str) -> str:
        """``CNPJ_7F3A9C`` — token rotulado (claro que está mascarado)."""
        norm = _DIGITS_RE.sub("", value) if kind in _DIGIT_KINDS else value.strip().lower()
        digest = hmac.new(self.cfg.key, norm.encode("utf-8"), "sha256").digest()
        code = base64.b32encode(digest).decode("ascii").rstrip("=")[:_TOKEN_LEN]
        return f"{kind.upper()}_{code}"

    def _fpe_token(self, value: str, kind: str) -> str:
        """Token format-preserving: CPF/CNPJ fake **válido** de mesma forma.

        Preserva comprimento e pontuação → ``SubStr``/montagem de chave/DbSeek
        continuam fazendo sentido sobre o valor mascarado.
        """
        norm = _DIGITS_RE.sub("", value)
        seed = hmac.new(self.cfg.key, f"fpe:{norm}".encode(), "sha256").digest()
        pool = "".join(str(b % 10) for b in seed)
        if kind == "cpf":
            base = pool[:_CPF_BASE_DIGITS]
            full = base + cpf_check_digits(base)
        else:
            base = pool[:_CNPJ_BASE_DIGITS]
            full = base + cnpj_check_digits(base)
        return reshape(value, full)

    def _render_token(self, value: str, kind: str) -> str:
        if self.cfg.style == "fpe" and kind in _DIGIT_KINDS:
            return self._fpe_token(value, kind)
        return self._label_token(value, kind)

    def _sub_validated(
        self,
        text: str,
        rx: re.Pattern[str],
        kind: str,
        validator: Callable[[str], bool] | None,
    ) -> str:
        def _repl(match: re.Match[str]) -> str:
            raw = match.group(0)
            if validator is not None and not validator(raw):
                return raw
            self.counts[kind] += 1
            return self._render_token(raw, kind)

        return rx.sub(_repl, text)

    def mask_text(self, text: str) -> str:
        """Mascara um texto: segredos (irreversível) → identificadores (token)."""
        if not text:
            return text
        # 1) segredos primeiro (pra senha não acabar virando token)
        for rx, repl in self._secret_patterns:
            text, n = rx.subn(repl, text)
            if n:
                self.counts["secret"] += n
        # 2) identificadores — ordem importa: e-mail e CNPJ (14d) antes de CPF (11d)
        recs = self.cfg.recognizers
        if "email" in recs:
            text = self._sub_validated(text, EMAIL_RE, "email", None)
        if "cnpj" in recs:
            text = self._sub_validated(text, CNPJ_RE, "cnpj", valid_cnpj)
        if "cpf" in recs:
            text = self._sub_validated(text, CPF_RE, "cpf", valid_cpf)
        if "ip" in recs:
            text = self._sub_validated(text, IPV4_RE, "ip", valid_ipv4)
        return text

    def mask_value(self, value: object) -> object:
        """Mascara recursivamente strings dentro de str/list/dict; resto inalterado."""
        if isinstance(value, str):
            return self.mask_text(value)
        if isinstance(value, list):
            return [self.mask_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self.mask_value(v) for k, v in value.items()}
        return value

    def _mask_cell(self, column: str, value: object) -> object:
        # Bucketização ciente do campo (opt-in): só sobre colunas cujo NOME
        # indica valor financeiro -> faixa nomeada em vez do número exato.
        if self.cfg.bucketize and is_financial_field(column, self.cfg.financial_fields):
            bucketed = try_bucket(value)
            if bucketed is not None:
                self.counts["valor"] += 1
                return bucketed
        return self.mask_value(value)

    def mask_rows(self, rows: list[dict[str, object]]) -> list[dict[str, object]]:
        """Mascara cada célula, preservando chaves e estrutura. Colunas financeiras
        (com ``bucketize`` ligado) viram faixa nomeada em vez do valor exato.
        """
        return [{k: self._mask_cell(k, v) for k, v in row.items()} for row in rows]
