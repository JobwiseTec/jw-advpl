"""Parser ADVPL — extrações por regex sobre conteúdo strip-first.

Portado e adaptado de Protheus/backend/services/parser_source.py
(parser de produção validado em 24.592 fontes padrão + 1.990 cliente real).
"""
from __future__ import annotations

from pathlib import Path

import chardet


def read_file(file_path: Path) -> tuple[str, str]:
    """Lê arquivo ADVPL e retorna (content, encoding_detected).

    Estratégia: tenta utf-8 strict primeiro (rejeita bytes cp1252 inválidos como utf-8 →
    falha cedo); só então tenta cp1252 (fast path para 99% dos fontes Protheus); finalmente
    chardet/latin-1.

    Por que utf-8 primeiro: cp1252 só tem 5 bytes indefinidos (0x81/8D/8F/90/9D), então
    cp1252 misdecoda silenciosamente bytes utf-8 multi-byte como sequência de chars latinos
    sem nunca lançar UnicodeDecodeError. utf-8 strict, ao contrário, rejeita bytes cp1252
    típicos (e.g. 'ã' = 0xE3 sozinho não forma sequência utf-8 válida).
    """
    raw = file_path.read_bytes()
    if not raw:
        return "", "cp1252"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        pass
    detected = chardet.detect(raw[:4096])
    encoding = detected.get("encoding") or "latin-1"
    try:
        return raw.decode(encoding), encoding
    except (UnicodeDecodeError, LookupError):
        return raw.decode("latin-1"), "latin-1"
