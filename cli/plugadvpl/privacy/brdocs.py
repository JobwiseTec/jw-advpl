"""Reconhecedores brasileiros com validação de dígito verificador (checksum).

O checksum é o que dá precisão: elimina o falso-positivo de "qualquer 11 dígitos
vira CPF". Tudo aqui é stdlib (``re``), sem dependência pesada.
"""

from __future__ import annotations

import re

_CPF_LEN = 11
_CNPJ_LEN = 14
_IP_PARTS = 4
_IP_MAX = 255
_MOD = 11
_DV_MIN = 2

_NON_DIGIT = re.compile(r"\D")

# Lookarounds (?<!\d)/(?!\d) evitam casar substring de um número maior.
CPF_RE = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
CNPJ_RE = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IPV4_RE = re.compile(r"(?<![\d.])\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])")

_CNPJ_W1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_W2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _digits(raw: str) -> str:
    return _NON_DIGIT.sub("", raw)


def valid_cpf(raw: str) -> bool:
    """True se ``raw`` é um CPF com dígitos verificadores corretos."""
    d = _digits(raw)
    if len(d) != _CPF_LEN or len(set(d)) == 1:
        return False
    for size in (9, 10):
        total = sum(int(d[i]) * ((size + 1) - i) for i in range(size))
        check = (total * 10) % _MOD % 10
        if check != int(d[size]):
            return False
    return True


def valid_cnpj(raw: str) -> bool:
    """True se ``raw`` é um CNPJ com dígitos verificadores corretos."""
    d = _digits(raw)
    if len(d) != _CNPJ_LEN or len(set(d)) == 1:
        return False
    for weights, pos in ((_CNPJ_W1, 12), (_CNPJ_W2, 13)):
        total = sum(int(d[i]) * weights[i] for i in range(pos))
        rem = total % _MOD
        check = 0 if rem < _DV_MIN else _MOD - rem
        if check != int(d[pos]):
            return False
    return True


def valid_ipv4(raw: str) -> bool:
    """True se ``raw`` é um IPv4 com octetos 0..255."""
    parts = raw.split(".")
    if len(parts) != _IP_PARTS:
        return False
    return all(p.isdigit() and int(p) <= _IP_MAX for p in parts)


# --- geração de dígitos verificadores (para tokenização format-preserving) ---


def _cpf_dv(digits: str) -> int:
    size = len(digits)
    total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
    return (total * 10) % _MOD % 10


def cpf_check_digits(base9: str) -> str:
    """Dígitos verificadores (2) de um corpo de 9 dígitos de CPF."""
    dv1 = _cpf_dv(base9)
    dv2 = _cpf_dv(base9 + str(dv1))
    return f"{dv1}{dv2}"


def _cnpj_dv(digits: str, weights: tuple[int, ...]) -> int:
    total = sum(int(digits[i]) * weights[i] for i in range(len(digits)))
    rem = total % _MOD
    return 0 if rem < _DV_MIN else _MOD - rem


def cnpj_check_digits(base12: str) -> str:
    """Dígitos verificadores (2) de um corpo de 12 dígitos de CNPJ."""
    dv1 = _cnpj_dv(base12, _CNPJ_W1)
    dv2 = _cnpj_dv(base12 + str(dv1), _CNPJ_W2)
    return f"{dv1}{dv2}"


def reshape(template: str, new_digits: str) -> str:
    """Reaplica a pontuação de ``template`` sobre ``new_digits`` (preserva forma).

    Ex.: reshape("11.222.333/0001-81", "47913620000158") -> "47.913.620/0001-58".
    """
    out: list[str] = []
    it = iter(new_digits)
    for ch in template:
        out.append(next(it, "0") if ch.isdigit() else ch)
    return "".join(out)
