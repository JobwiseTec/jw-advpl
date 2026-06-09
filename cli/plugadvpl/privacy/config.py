"""Configuração da camada de privacidade (opt-in, default desligada).

Controle por variável de ambiente (sem acoplar ao ``runtime.toml`` estrito):

- ``PLUGADVPL_PRIVACY``           — liga (``1``/``true``/``on``/``sim``).
- ``PLUGADVPL_PRIVACY_KEY``       — chave HMAC (estabiliza os tokens entre os
  vários processos de uma sessão). Sem ela, usa uma chave-dev fixa (tokens
  estáveis, porém previsíveis — troque em produção).
- ``PLUGADVPL_PRIVACY_RECOGNIZERS`` — lista separada por vírgula
  (default ``cpf,cnpj,email``; ``ip`` é opt-in por causa de falso-positivo com
  números de versão/build).
- ``PLUGADVPL_PRIVACY_REDACT_SECRETS`` — redação de segredos (default ligada).

A flag global ``--privacy/--no-privacy`` da CLI sobrepõe a env var.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

_TRUTHY = frozenset({"1", "true", "on", "yes", "sim"})


def _load_financial_fields(path: str) -> frozenset[str]:
    """Carrega lista JSON de nomes de campo financeiro (gerada do SX3 via
    ``buckets.financial_fields_from_sx3``). Silencioso em erro de IO/parse.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    return frozenset(str(f).strip().upper() for f in data if str(f).strip())


_DEFAULT_RECOGNIZERS = ("cpf", "cnpj", "email")
# Chave-dev fixa: estabiliza tokens sem exigir setup. NÃO é segredo — em produção
# defina PLUGADVPL_PRIVACY_KEY para impedir reconstrução do valor a partir do token.
_DEV_KEY = b"plugadvpl-privacy-default-key-troque-em-producao"  # gitleaks:allow (chave-dev pública, não é segredo)


_VALID_STYLES = frozenset({"label", "fpe"})


@dataclass(frozen=True)
class PrivacyConfig:
    """Política imutável da camada de mascaramento.

    ``style`` controla a forma do token de CPF/CNPJ:

    - ``"label"`` (default): ``CNPJ_7F3A9C`` — claro que está mascarado;
    - ``"fpe"`` (format-preserving): um CPF/CNPJ **fake válido de mesma forma**
      (``47.913.620/0001-58``) — preserva comprimento/pontuação para lógica
      posicional (ex.: ``SubStr(cCgc, 1, 8)`` pega a raiz, montagem de chave).
    """

    enabled: bool = False
    recognizers: tuple[str, ...] = _DEFAULT_RECOGNIZERS
    redact_secrets: bool = True
    key: bytes = _DEV_KEY
    key_explicit: bool = False
    style: str = "label"
    bucketize: bool = False
    financial_fields: frozenset[str] = frozenset()
    scan_injection: bool = False

    @classmethod
    def from_env(cls, *, enabled_override: bool | None = None) -> PrivacyConfig:
        """Constrói a config a partir do ambiente. ``enabled_override`` (da flag
        CLI ``--privacy/--no-privacy``) tem prioridade sobre ``PLUGADVPL_PRIVACY``.
        """
        env = os.environ
        if enabled_override is None:
            enabled = env.get("PLUGADVPL_PRIVACY", "").strip().lower() in _TRUTHY
        else:
            enabled = enabled_override

        raw_recs = env.get("PLUGADVPL_PRIVACY_RECOGNIZERS", "").strip()
        recognizers = (
            tuple(r.strip().lower() for r in raw_recs.split(",") if r.strip())
            or _DEFAULT_RECOGNIZERS
        )
        redact = env.get("PLUGADVPL_PRIVACY_REDACT_SECRETS", "1").strip().lower() in _TRUTHY

        style = env.get("PLUGADVPL_PRIVACY_STYLE", "label").strip().lower()
        if style not in _VALID_STYLES:
            style = "label"

        bucketize = env.get("PLUGADVPL_PRIVACY_BUCKETIZE", "").strip().lower() in _TRUTHY

        fields_file = env.get("PLUGADVPL_PRIVACY_FIELDS_FILE", "").strip()
        financial_fields = _load_financial_fields(fields_file) if fields_file else frozenset()

        scan_injection = env.get("PLUGADVPL_INJECTION_SCAN", "").strip().lower() in _TRUTHY

        key_str = env.get("PLUGADVPL_PRIVACY_KEY", "").strip()
        if key_str:
            return cls(
                enabled=enabled,
                recognizers=recognizers,
                redact_secrets=redact,
                key=key_str.encode("utf-8"),
                key_explicit=True,
                style=style,
                bucketize=bucketize,
                financial_fields=financial_fields,
                scan_injection=scan_injection,
            )
        return cls(
            enabled=enabled,
            recognizers=recognizers,
            redact_secrets=redact,
            style=style,
            bucketize=bucketize,
            financial_fields=financial_fields,
            scan_injection=scan_injection,
        )


def dev_key_warning(cfg: PrivacyConfig) -> str | None:
    """Mensagem de aviso quando o mascaramento usa a chave-dev default.

    Tokens HMAC com chave pública são previsíveis: CPF/CNPJ podem ser
    reconstruídos por força bruta de dicionário (auditoria 2026-06-09, A4).
    Retorna ``None`` quando não há o que avisar (privacy off ou chave
    explícita via ``PLUGADVPL_PRIVACY_KEY``).
    """
    if not cfg.enabled or cfg.key_explicit:
        return None
    return (
        "WARNING: --privacy ativo com a chave-dev default — tokens de CPF/CNPJ "
        "são previsíveis (reconstruíveis por dicionário). Defina "
        "PLUGADVPL_PRIVACY_KEY com um valor secreto pra tokens não-reversíveis."
    )
