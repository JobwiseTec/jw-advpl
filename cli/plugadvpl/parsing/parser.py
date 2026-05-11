"""Parser ADVPL — extrações por regex sobre conteúdo strip-first.

Portado e adaptado de Protheus/backend/services/parser_source.py
(parser de produção validado em 24.592 fontes padrão + 1.990 cliente real).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import chardet

from plugadvpl.parsing.stripper import strip_advpl

# Regexes pre-compilados em module-level (workers do ProcessPool podem importar).
# Usa [ \t]* (não \s*) para indentação para que MULTILINE ^ não cruze newlines.
_FUNCTION_RE = re.compile(
    r"^[ \t]*(?:(Static|User|Main)[ \t]+)?Function[ \t]+(\w+)",
    re.IGNORECASE | re.MULTILINE,
)
_WSMETHOD_RE = re.compile(
    r"^[ \t]*WSMETHOD[ \t]+(GET|POST|PUT|DELETE)?[ \t]*(\w+)[ \t]+WS(?:RECEIVE|SEND|SERVICE)",
    re.IGNORECASE | re.MULTILINE,
)
_METHOD_RE = re.compile(
    r"^[ \t]*METHOD[ \t]+(\w+)[ \t]*\([^)]*\)[ \t]*CLASS[ \t]+(\w+)",
    re.IGNORECASE | re.MULTILINE,
)


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


def _line_at(content: str, offset: int) -> int:
    """Retorna a linha 1-based do offset."""
    return content.count("\n", 0, offset) + 1


def extract_functions(content: str) -> list[dict[str, Any]]:
    """Extrai todas as funções declaradas no fonte.

    Retorna lista de dicts com: nome, kind, classe, linha_inicio, _offset.
    Aplica strip_advpl primeiro para ignorar comentários e strings.
    """
    stripped = strip_advpl(content)
    result: list[dict[str, Any]] = []

    for m in _FUNCTION_RE.finditer(stripped):
        kind_raw = (m.group(1) or "function").lower()
        kind = {
            "user": "user_function",
            "static": "static_function",
            "main": "main_function",
            "function": "function",
        }[kind_raw]
        result.append(
            {
                "nome": m.group(2),
                "kind": kind,
                "classe": "",
                "linha_inicio": _line_at(stripped, m.start()),
                "_offset": m.start(),
            }
        )

    for m in _WSMETHOD_RE.finditer(stripped):
        result.append(
            {
                "nome": m.group(2),
                "kind": "ws_method",
                "classe": "",
                "linha_inicio": _line_at(stripped, m.start()),
                "_offset": m.start(),
            }
        )

    for m in _METHOD_RE.finditer(stripped):
        result.append(
            {
                "nome": m.group(1),
                "kind": "method",
                "classe": m.group(2),
                "linha_inicio": _line_at(stripped, m.start()),
                "_offset": m.start(),
            }
        )

    result.sort(key=lambda f: int(f["_offset"]))
    return result


def add_function_ranges(funcs: list[dict[str, Any]], content: str) -> list[dict[str, Any]]:
    """Preenche linha_fim para cada função baseado no offset da próxima.

    Padrão: fim = linha do header da próxima função - 1. Para a última,
    fim = última linha do arquivo.
    """
    if not funcs:
        return funcs
    # Conta linhas: número de newlines (se acaba em \n) ou +1 (se não acaba em \n).
    total_lines = content.count("\n") if content.endswith("\n") else content.count("\n") + 1
    for i, f in enumerate(funcs):
        if i + 1 < len(funcs):
            next_line = funcs[i + 1]["linha_inicio"]
            f["linha_fim"] = max(f["linha_inicio"], next_line - 1)
        else:
            f["linha_fim"] = total_lines
        f.pop("_offset", None)
    return funcs
