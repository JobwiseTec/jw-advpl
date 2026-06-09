"""Camada de proteção de dados sensíveis (Fase 1) — mascaramento no *egress*.

Intercepta o conteúdo no ponto único de saída (``output.render``) e, quando
ligada (opt-in), troca:

- **identificadores** (CPF/CNPJ/e-mail/IP) por um *token estável* (HMAC) —
  mesmo valor → mesmo token, sem mapa em disco (pseudonimização de mão única);
- **segredos** (senha/token/connection string) por ``***REDACTED***`` —
  irreversível, reusando o catálogo ``lookups/redact_patterns.json``.

Desligada por padrão: ``PrivacyConfig.enabled is False`` → o output é idêntico
ao de hoje. Stateless entre execuções (cada comando é um processo efêmero) —
o "reset" entre sessões é de graça e nada é persistido.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from .config import PrivacyConfig, dev_key_warning
from .engine import Masker
from .injection import InjectionHit, flag_injection

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "InjectionHit",
    "Masker",
    "PrivacyConfig",
    "dev_key_warning",
    "flag_injection",
    "mask_for_egress",
]


def mask_for_egress(
    rows: Sequence[dict[str, object]],
    cfg: PrivacyConfig,
) -> tuple[list[dict[str, object]], Counter[str]]:
    """Mascara ``rows`` segundo ``cfg`` e devolve ``(linhas_mascaradas, contagem)``.

    ``contagem`` é um ``Counter`` por tipo de entidade (``cpf``/``cnpj``/...),
    para auditoria — **nunca** contém o valor real.
    """
    if not cfg.enabled:
        return list(rows), Counter()
    masker = Masker(cfg)
    masked = masker.mask_rows(list(rows))
    return masked, masker.counts
