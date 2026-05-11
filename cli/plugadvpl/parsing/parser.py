"""Parser ADVPL — extrações por regex sobre conteúdo strip-first.

Portado e adaptado de Protheus/backend/services/parser_source.py
(parser de produção validado em 24.592 fontes padrão + 1.990 cliente real).
"""
from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any

import chardet

from plugadvpl.parsing.stripper import strip_advpl

if TYPE_CHECKING:
    from pathlib import Path

# Códigos de tabela Protheus têm exatamente 3 chars (SA1, ZA1, NDF, etc).
_TABLE_CODE_LEN = 3

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

# Tabelas Protheus
_DBSELECT_RE = re.compile(r'DbSelectArea\s*\(\s*["\'](\w{2,3})["\']', re.IGNORECASE)
_XFILIAL_RE = re.compile(
    r'(?:xFilial|FwxFilial|Posicione|MsSeek|dbSetOrder|ChkFile)\s*\(\s*["\'](\w{2,3})["\']',
    re.IGNORECASE,
)
_ALIAS_ARROW_RE = re.compile(r"\b([SZQNDM][A-Z][0-9A-Z])\s*->", re.IGNORECASE)
_RECLOCK_RE = re.compile(r'RecLock\s*\(\s*["\'](\w{2,3})["\']', re.IGNORECASE)
_RECLOCK_ALIAS_RE = re.compile(r"(\w{2,3})\s*->\s*\(\s*RecLock", re.IGNORECASE)
_DBAPPEND_RE = re.compile(r"(\w{2,3})\s*->\s*\(\s*dbAppend", re.IGNORECASE)
_DBDELETE_RE = re.compile(r"(\w{2,3})\s*->\s*\(\s*dbDelete", re.IGNORECASE)

# MV_* parâmetros
# Default arg pode estar em posição 2 (GetNewPar(nome, default)) ou posição 3
# (SuperGetMV(nome, lUseDef, default)). Grupo 2: default em pos 2 (sem vírgula extra),
# Grupo 3: default em pos 3 (vírgula+arg+vírgula+string).
_MV_READ_RE = re.compile(
    r'(?:SuperGetMV|GetMv|GetNewPar|GetMVDef|FWMVPar)\s*\(\s*["\'](MV_\w+)["\']'
    r'(?:'
    r'\s*,\s*["\']([^"\']*)["\']\s*\)'  # default na pos 2: ("MV_X", "default")
    r'|'
    r'\s*,\s*[^,)]+\s*,\s*["\']([^"\']*)["\']'  # default na pos 3: ("MV_X", lDef, "default")
    r')?',
    re.IGNORECASE,
)
_MV_WRITE_RE = re.compile(
    r'(?:PutMV|PutMvFil)\s*\(\s*["\'](MV_\w+)["\']',
    re.IGNORECASE,
)

# Perguntas SX1
_PERGUNTE_RE = re.compile(
    r'(?:Pergunte|FWGetSX1)\s*\(\s*["\'](\w+)["\']',
    re.IGNORECASE,
)

# Includes
_INCLUDE_RE = re.compile(r'^\s*#Include\s+["\']([^"\']+)["\']', re.IGNORECASE | re.MULTILINE)

# Calls
_CALL_U_RE = re.compile(r"\bU_(\w+)\s*\(", re.IGNORECASE)
_EXECAUTO_RE = re.compile(
    r"MsExecAuto\s*\(\s*\{\s*\|[^|]*\|\s*(\w+)\s*\(",
    re.IGNORECASE,
)
_EXECBLOCK_RE = re.compile(r'ExecBlock\s*\(\s*["\'](\w+)["\']', re.IGNORECASE)
_FWLOADMODEL_RE = re.compile(r'FWLoadModel\s*\(\s*["\'](\w+)["\']', re.IGNORECASE)
_FWEXECVIEW_RE = re.compile(r'FWExecView\s*\([^,)]+,\s*["\'](\w+)["\']', re.IGNORECASE)
_METHOD_OBJ_RE = re.compile(r"\b(\w+:\w+)\s*\(", re.IGNORECASE)
_METHOD_SELF_RE = re.compile(r"::(\w+)\s*\(", re.IGNORECASE)

# Campos (alias->FIELD, Replace FIELD)
_FIELD_ARROW_RE = re.compile(r"\w{2,3}->([A-Z][A-Z0-9]_\w+)", re.IGNORECASE)
_FIELD_REPLACE_RE = re.compile(r"\bReplace\s+([A-Z][A-Z0-9]_\w+)", re.IGNORECASE)


def read_file(file_path: Path) -> tuple[str, str]:
    """Lê arquivo ADVPL e retorna (content, encoding_detected).

    Estratégia:
    1. ASCII-only → reporta "cp1252" (default Protheus, ASCII é subconjunto)
    2. UTF-8 strict válido (tem multi-byte chars) → "utf-8"
    3. cp1252 (fast path para 99% dos fontes Protheus com chars latinos)
    4. chardet/latin-1 fallback

    Por que utf-8 antes de cp1252 (após ASCII check): cp1252 só tem 5 bytes indefinidos
    (0x81/8D/8F/90/9D), então cp1252 misdecoda silenciosamente bytes utf-8 multi-byte
    como sequência de chars latinos. utf-8 strict rejeita bytes cp1252 típicos (e.g.
    'ã' = 0xE3 sozinho não forma sequência utf-8 válida).
    """
    raw = file_path.read_bytes()
    if not raw:
        return "", "cp1252"
    # ASCII-only: padrão Protheus é cp1252; ASCII é subset, então reporta cp1252.
    if raw.isascii():
        return raw.decode("ascii"), "cp1252"
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


def _is_valid_protheus_table(name: str) -> bool:
    """Códigos válidos: 3 chars, [SZNQD] + letra + alfanumérico (SA1, ZA1, NDF, ...)."""
    if len(name) != _TABLE_CODE_LEN:
        return False
    return name[0] in "SZNQD" and name[1].isalpha()


def extract_tables(content: str) -> dict[str, list[str]]:
    """Extrai tabelas referenciadas, separadas por modo (read/write/reclock).

    'write' inclui reclock (todas as escritas). 'reclock' é subconjunto (apenas RecLock).
    Usa strip_strings=False porque precisamos ler argumentos literais ("SA1", 'ZA1').
    Comentários são removidos para evitar capturar tabelas em código comentado.
    """
    stripped = strip_advpl(content, strip_strings=False)
    read: set[str] = set()
    write: set[str] = set()
    reclock: set[str] = set()

    for m in _DBSELECT_RE.finditer(stripped):
        read.add(m.group(1).upper())
    for m in _XFILIAL_RE.finditer(stripped):
        read.add(m.group(1).upper())
    for m in _ALIAS_ARROW_RE.finditer(stripped):
        read.add(m.group(1).upper())

    for m in _RECLOCK_RE.finditer(stripped):
        t = m.group(1).upper()
        reclock.add(t)
        write.add(t)
    for m in _RECLOCK_ALIAS_RE.finditer(stripped):
        t = m.group(1).upper()
        reclock.add(t)
        write.add(t)
    for m in _DBAPPEND_RE.finditer(stripped):
        write.add(m.group(1).upper())
    for m in _DBDELETE_RE.finditer(stripped):
        write.add(m.group(1).upper())

    return {
        "read": sorted(t for t in read if _is_valid_protheus_table(t)),
        "write": sorted(t for t in write if _is_valid_protheus_table(t)),
        "reclock": sorted(t for t in reclock if _is_valid_protheus_table(t)),
    }


def extract_params(content: str) -> list[dict[str, Any]]:
    """Extrai usos de parâmetros MV_*. Retorna [{nome, modo, default_decl}].

    Usa strip_strings=False porque o nome do parâmetro vem em literal string.
    """
    stripped = strip_advpl(content, strip_strings=False)
    by_name: dict[str, dict[str, Any]] = {}
    for m in _MV_READ_RE.finditer(stripped):
        nome = m.group(1).upper()
        default = m.group(2) or m.group(3) or ""
        entry = by_name.setdefault(nome, {"nome": nome, "modo": "read", "default_decl": ""})
        if default and not entry["default_decl"]:
            entry["default_decl"] = default
    for m in _MV_WRITE_RE.finditer(stripped):
        nome = m.group(1).upper()
        if nome in by_name:
            by_name[nome]["modo"] = "read_write"
        else:
            by_name[nome] = {"nome": nome, "modo": "write", "default_decl": ""}
    return list(by_name.values())


def extract_perguntas(content: str) -> list[str]:
    """Extrai grupos de perguntas SX1 referenciados (Pergunte, FWGetSX1)."""
    stripped = strip_advpl(content, strip_strings=False)
    return sorted({m.group(1).upper() for m in _PERGUNTE_RE.finditer(stripped)})


def extract_includes(content: str) -> list[str]:
    """Extrai paths de #Include declarados no fonte (preserva case do nome do header)."""
    stripped = strip_advpl(content, strip_strings=False)
    return sorted({m.group(1) for m in _INCLUDE_RE.finditer(stripped)})


def extract_calls_user_func(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas a User Functions (U_xxx). Strip-first remove strings/comentários."""
    stripped = strip_advpl(content)
    result: list[dict[str, Any]] = []
    for m in _CALL_U_RE.finditer(stripped):
        result.append(
            {
                "destino": m.group(1).upper(),
                "tipo": "user_func",
                "linha_origem": _line_at(stripped, m.start()),
                "contexto": stripped[max(0, m.start() - 30) : m.end() + 30][:200],
            }
        )
    return result


def extract_calls_execauto(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas MsExecAuto({|x,y,z| ROTINA(x,y,z)}, ...) capturando ROTINA."""
    stripped = strip_advpl(content)
    result: list[dict[str, Any]] = []
    for m in _EXECAUTO_RE.finditer(stripped):
        result.append(
            {
                "destino": m.group(1).upper(),
                "tipo": "execauto",
                "linha_origem": _line_at(stripped, m.start()),
                "contexto": stripped[max(0, m.start() - 30) : m.end() + 30][:200],
            }
        )
    return result


def extract_calls_execblock(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas ExecBlock("PE_NAME", ...) — nome de PE em string literal."""
    stripped = strip_advpl(content, strip_strings=False)
    result: list[dict[str, Any]] = []
    for m in _EXECBLOCK_RE.finditer(stripped):
        result.append(
            {
                "destino": m.group(1).upper(),
                "tipo": "execblock",
                "linha_origem": _line_at(stripped, m.start()),
                "contexto": stripped[max(0, m.start() - 30) : m.end() + 30][:200],
            }
        )
    return result


def extract_calls_fwloadmodel(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas FWLoadModel("MODEL_ID") — model id em string literal."""
    stripped = strip_advpl(content, strip_strings=False)
    result: list[dict[str, Any]] = []
    for m in _FWLOADMODEL_RE.finditer(stripped):
        result.append(
            {
                "destino": m.group(1).upper(),
                "tipo": "fwloadmodel",
                "linha_origem": _line_at(stripped, m.start()),
                "contexto": stripped[max(0, m.start() - 30) : m.end() + 30][:200],
            }
        )
    return result


def extract_calls_fwexecview(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas FWExecView("Titulo", "MODEL_ID", ...) — captura o 2º arg."""
    stripped = strip_advpl(content, strip_strings=False)
    result: list[dict[str, Any]] = []
    for m in _FWEXECVIEW_RE.finditer(stripped):
        result.append(
            {
                "destino": m.group(1).upper(),
                "tipo": "fwexecview",
                "linha_origem": _line_at(stripped, m.start()),
                "contexto": stripped[max(0, m.start() - 30) : m.end() + 30][:200],
            }
        )
    return result


def parse_source(file_path: Path) -> dict[str, Any]:
    """Orquestra todas as extrações sobre um fonte. Retorna dict completo.

    Output:
        arquivo, caminho, encoding, lines_of_code, funcoes, tabelas_ref,
        parametros_uso, perguntas_uso, includes, chamadas, campos_ref, hash.

    Hash é SHA-1 dos bytes decodificados (40 char hex). Usado para stale
    detection no ingest incremental (spec §11.2 #23).
    """
    content, encoding = read_file(file_path)
    if not content:
        return {
            "arquivo": file_path.name,
            "caminho": str(file_path),
            "encoding": encoding,
            "lines_of_code": 0,
            "funcoes": [],
            "tabelas_ref": {"read": [], "write": [], "reclock": []},
            "parametros_uso": [],
            "perguntas_uso": [],
            "includes": [],
            "chamadas": [],
            "campos_ref": [],
            "hash": "",
        }

    funcs = extract_functions(content)
    funcs = add_function_ranges(funcs, content)

    return {
        "arquivo": file_path.name,
        "caminho": str(file_path),
        "encoding": encoding,
        "lines_of_code": content.count("\n") + 1,
        "funcoes": funcs,
        "tabelas_ref": extract_tables(content),
        "parametros_uso": extract_params(content),
        "perguntas_uso": extract_perguntas(content),
        "includes": extract_includes(content),
        "chamadas": (
            extract_calls_user_func(content)
            + extract_calls_execauto(content)
            + extract_calls_execblock(content)
            + extract_calls_fwloadmodel(content)
            + extract_calls_fwexecview(content)
            + extract_calls_method(content)
        ),
        "campos_ref": extract_fields_ref(content),
        # SHA-1 não é uso criptográfico — apenas content-addressed hash para stale detection.
        "hash": hashlib.sha1(content.encode(encoding, errors="replace")).hexdigest(),
    }


def extract_fields_ref(content: str) -> list[str]:
    """Extrai nomes de campos Protheus referenciados (alias->FIELD ou Replace FIELD).

    Padrão XX_NOME (ex.: A1_NOME, C5_NUM, ZA1_FOO). Filtra por regex que exige
    primeira letra + alfanumérico + underscore + sufixo.
    """
    stripped = strip_advpl(content)
    fields: set[str] = set()
    for m in _FIELD_ARROW_RE.finditer(stripped):
        fields.add(m.group(1).upper())
    for m in _FIELD_REPLACE_RE.finditer(stripped):
        fields.add(m.group(1).upper())
    return sorted(fields)


def extract_calls_method(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas de métodos (obj:method(...) e ::method(...)).

    Atenção: padrão tem MUITO false-positive (qualquer 'a:b(' casa). Preserva case
    do destino. Não tenta resolver classe — apenas registra o uso.
    """
    stripped = strip_advpl(content)
    result: list[dict[str, Any]] = []
    for m in _METHOD_OBJ_RE.finditer(stripped):
        result.append(
            {
                "destino": m.group(1),
                "tipo": "method",
                "linha_origem": _line_at(stripped, m.start()),
                "contexto": stripped[max(0, m.start() - 30) : m.end() + 30][:200],
            }
        )
    for m in _METHOD_SELF_RE.finditer(stripped):
        result.append(
            {
                "destino": f"::{m.group(1)}",
                "tipo": "method",
                "linha_origem": _line_at(stripped, m.start()),
                "contexto": stripped[max(0, m.start() - 30) : m.end() + 30][:200],
            }
        )
    return result
