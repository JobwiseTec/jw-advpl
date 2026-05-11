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
# Primeira letra restrita ao alfabeto Protheus válido (S/Z/N/Q/D) — alinhado com
# _is_valid_protheus_table; evita matches desperdiçados.
_ALIAS_ARROW_RE = re.compile(r"\b([SZQND][A-Z][0-9A-Z])\s*->", re.IGNORECASE)
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
# Method names devem começar com letra ou underscore (identificadores reais).
# Antes: `\w+:\w+` — aceitava `obj:9foo` (digit start) incorretamente.
_METHOD_OBJ_RE = re.compile(r"\b(\w+:[A-Za-z_]\w*)\s*\(", re.IGNORECASE)
_METHOD_SELF_RE = re.compile(r"::([A-Za-z_]\w*)\s*\(", re.IGNORECASE)

# Campos (alias->FIELD, Replace FIELD)
_FIELD_ARROW_RE = re.compile(r"\w{2,3}->([A-Z][A-Z0-9]_\w+)", re.IGNORECASE)
_FIELD_REPLACE_RE = re.compile(r"\bReplace\s+([A-Z][A-Z0-9]_\w+)", re.IGNORECASE)

# REST endpoints
# WSMETHOD clássico: "WSMETHOD GET clientes WSSERVICE Vendas"
_WSMETHOD_REST_RE = re.compile(
    r"^[ \t]*WSMETHOD[ \t]+(GET|POST|PUT|DELETE|PATCH)[ \t]+(\w+)[ \t]+WSSERVICE[ \t]+(\w+)",
    re.IGNORECASE | re.MULTILINE,
)
# Anotação TLPP: @Get("/api/path") em linha própria
_TLPP_ANNOTATION_RE = re.compile(
    r'^[ \t]*@(Get|Post|Put|Delete|Patch)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE | re.MULTILINE,
)

# HTTP outbound calls: HttpPost/HttpGet/HttpsPost/HttpsGet/MsAGetUrl
# Captura nome do método (preservando case) e URL literal do 1º argumento.
_HTTP_CALL_RE = re.compile(
    r'\b(HttpPost|HttpGet|HttpsPost|HttpsGet|MsAGetUrl)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# TLPP Namespace: "Namespace x.y.z"
_NAMESPACE_RE = re.compile(
    r"^[ \t]*Namespace[ \t]+([A-Za-z_][\w.]*)", re.IGNORECASE | re.MULTILINE
)

# WebService structures: WSSTRUCT / WSSERVICE / WSDATA / WSMETHOD
_WSSTRUCT_HEADER_RE = re.compile(r"^[ \t]*WSSTRUCT[ \t]+(\w+)", re.IGNORECASE | re.MULTILINE)
_WSSERVICE_HEADER_RE = re.compile(
    r"^[ \t]*WSSERVICE[ \t]+(\w+)", re.IGNORECASE | re.MULTILINE
)
_WSDATA_FIELD_RE = re.compile(
    r"^[ \t]*WSDATA[ \t]+(\w+)[ \t]+AS[ \t]+(\w+)", re.IGNORECASE | re.MULTILINE
)
_WSMETHOD_BARE_RE = re.compile(r"^[ \t]*WSMETHOD[ \t]+(\w+)", re.IGNORECASE | re.MULTILINE)
_WSMETHOD_FULL_RE = re.compile(
    r"\bWSMETHOD[ \t]+(\w+)[ \t]+WSRECEIVE[ \t]+(\w+)"
    r"[ \t]+WSSEND[ \t]+(\w+)[ \t]+WSSERVICE[ \t]+(\w+)",
    re.IGNORECASE,
)
_END_WSSTRUCT_RE = re.compile(
    r"^[ \t]*(?:ENDWSSTRUCT|END[ \t]+WSSTRUCT)", re.IGNORECASE | re.MULTILINE
)
_END_WSSERVICE_RE = re.compile(
    r"^[ \t]*(?:ENDWSSERVICE|END[ \t]+WSSERVICE)", re.IGNORECASE | re.MULTILINE
)
_WS_RESERVED = {
    "WSSTRUCT",
    "WSSERVICE",
    "WSMETHOD",
    "WSDATA",
    "WSRECEIVE",
    "WSSEND",
    "ENDWSSERVICE",
    "ENDWSSTRUCT",
}

# MVC hooks: bCommit/bCancel/bTudoOk/bLineOk/bPosVld/bPreVld/bWhen/bValid/bLoad
# Reconhecidos como atribuição (`:=` ou `=`) — o RHS é tipicamente um code block.
_MVC_HOOK_RE = re.compile(
    r"\b(bCommit|bCancel|bTudoOk|bLineOk|bPosVld|bPreVld|bWhen|bValid|bLoad)"
    r"\s*:?=\s*",
    re.IGNORECASE,
)

# #DEFINE preprocessor directive: capture nome + restante da linha como valor.
_DEFINE_RE = re.compile(r"^[ \t]*#DEFINE[ \t]+(\w+)[ \t]+(.+)$", re.IGNORECASE | re.MULTILINE)

# Log calls: FwLogMsg(...) e ConOut(...)
_FWLOGMSG_OPEN_RE = re.compile(r"\bFwLogMsg\s*\(", re.IGNORECASE)
_CONOUT_OPEN_RE = re.compile(r"\bConOut\s*\(", re.IGNORECASE)

# RpcSetEnv: abre call e captura argumentos crus até o fechamento balanceado.
# Args podem ser literais ("01") ou variáveis (cEmp). Parsing fino é feito em Python.
_RPCSETENV_OPEN_RE = re.compile(r"\bRpcSetEnv\s*\(", re.IGNORECASE)
# Reconhece token literal entre aspas (sem aspas escapadas — simples para MVP)
_QUOTED_ARG_RE = re.compile(r'^["\']([^"\']*)["\']$')


def _decode_bytes(raw: bytes) -> tuple[str, str]:
    """Decodifica bytes ADVPL aplicando a mesma estratégia de read_file.

    Separado para que parse_source possa hash dos bytes raw uma única vez sem
    re-encode (evita SHA-1 round-trip).
    """
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
    return _decode_bytes(file_path.read_bytes())


def _line_at(content: str, offset: int) -> int:
    """Retorna a linha 1-based do offset."""
    return content.count("\n", 0, offset) + 1


# --- Core extractors (recebem conteúdo já stripado) ---------------------------
#
# Cada extrator público é um wrapper fino que faz strip_advpl(...) e delega ao
# core _*_from_stripped. parse_source chama o strip apenas duas vezes (uma por
# modo) e reusa os resultados em todos os cores — economiza ~80% do tempo total
# (cf. C2 do code review).


def _extract_functions_from_stripped(stripped: str) -> list[dict[str, Any]]:
    """Core: extrai funções de conteúdo já stripado (modo strict)."""
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


def extract_functions(content: str) -> list[dict[str, Any]]:
    """Extrai todas as funções declaradas no fonte.

    Retorna lista de dicts com: nome, kind, classe, linha_inicio, _offset.
    Aplica strip_advpl primeiro para ignorar comentários e strings.
    """
    stripped = strip_advpl(content)
    return _extract_functions_from_stripped(stripped)


def _add_function_ranges(
    funcs: list[dict[str, Any]], content: str
) -> list[dict[str, Any]]:
    """Core: preenche linha_fim (não precisa de strip — só do raw para contagem)."""
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


def add_function_ranges(funcs: list[dict[str, Any]], content: str) -> list[dict[str, Any]]:
    """Preenche linha_fim para cada função baseado no offset da próxima.

    Padrão: fim = linha do header da próxima função - 1. Para a última,
    fim = última linha do arquivo.
    """
    return _add_function_ranges(funcs, content)


def _is_valid_protheus_table(name: str) -> bool:
    """Códigos válidos: 3 chars, [SZNQD] + letra + alfanumérico (SA1, ZA1, NDF, ...)."""
    if len(name) != _TABLE_CODE_LEN:
        return False
    return name[0] in "SZNQD" and name[1].isalpha()


def _extract_tables_from_stripped(
    stripped_keep_strings: str,
    stripped_strict: str,
) -> dict[str, list[str]]:
    """Core: extrai tabelas de duas variantes de strip.

    Patterns que precisam de argumento literal (DbSelectArea, xFilial, RecLock)
    rodam sobre stripped_keep_strings. Patterns que operam sobre código puro
    (alias->, RecLock via alias, dbAppend, dbDelete) rodam sobre stripped_strict
    para evitar falso-positivos de strings literais (C3 do code review).
    """
    read: set[str] = set()
    write: set[str] = set()
    reclock: set[str] = set()

    # Literal-arg patterns: usar variante que preserva strings
    for m in _DBSELECT_RE.finditer(stripped_keep_strings):
        read.add(m.group(1).upper())
    for m in _XFILIAL_RE.finditer(stripped_keep_strings):
        read.add(m.group(1).upper())
    for m in _RECLOCK_RE.finditer(stripped_keep_strings):
        t = m.group(1).upper()
        reclock.add(t)
        write.add(t)

    # Code-only patterns: usar variante que blank-a strings
    for m in _ALIAS_ARROW_RE.finditer(stripped_strict):
        read.add(m.group(1).upper())
    for m in _RECLOCK_ALIAS_RE.finditer(stripped_strict):
        t = m.group(1).upper()
        reclock.add(t)
        write.add(t)
    for m in _DBAPPEND_RE.finditer(stripped_strict):
        write.add(m.group(1).upper())
    for m in _DBDELETE_RE.finditer(stripped_strict):
        write.add(m.group(1).upper())

    return {
        "read": sorted(t for t in read if _is_valid_protheus_table(t)),
        "write": sorted(t for t in write if _is_valid_protheus_table(t)),
        "reclock": sorted(t for t in reclock if _is_valid_protheus_table(t)),
    }


def extract_tables(content: str) -> dict[str, list[str]]:
    """Extrai tabelas referenciadas, separadas por modo (read/write/reclock).

    'write' inclui reclock (todas as escritas). 'reclock' é subconjunto (apenas RecLock).
    """
    stripped_keep = strip_advpl(content, strip_strings=False)
    stripped_strict = strip_advpl(content, strip_strings=True)
    return _extract_tables_from_stripped(stripped_keep, stripped_strict)


def _extract_params_from_stripped(stripped_keep_strings: str) -> list[dict[str, Any]]:
    """Core: extrai MV_* de conteúdo strip mantendo strings."""
    by_name: dict[str, dict[str, Any]] = {}
    for m in _MV_READ_RE.finditer(stripped_keep_strings):
        nome = m.group(1).upper()
        default = m.group(2) or m.group(3) or ""
        entry = by_name.setdefault(nome, {"nome": nome, "modo": "read", "default_decl": ""})
        if default and not entry["default_decl"]:
            entry["default_decl"] = default
    for m in _MV_WRITE_RE.finditer(stripped_keep_strings):
        nome = m.group(1).upper()
        if nome in by_name:
            by_name[nome]["modo"] = "read_write"
        else:
            by_name[nome] = {"nome": nome, "modo": "write", "default_decl": ""}
    return list(by_name.values())


def extract_params(content: str) -> list[dict[str, Any]]:
    """Extrai usos de parâmetros MV_*. Retorna [{nome, modo, default_decl}].

    Usa strip_strings=False porque o nome do parâmetro vem em literal string.
    """
    return _extract_params_from_stripped(strip_advpl(content, strip_strings=False))


def _extract_perguntas_from_stripped(stripped_keep_strings: str) -> list[str]:
    """Core: extrai perguntas SX1 de strip mantendo strings."""
    return sorted({m.group(1).upper() for m in _PERGUNTE_RE.finditer(stripped_keep_strings)})


def extract_perguntas(content: str) -> list[str]:
    """Extrai grupos de perguntas SX1 referenciados (Pergunte, FWGetSX1)."""
    return _extract_perguntas_from_stripped(strip_advpl(content, strip_strings=False))


def _extract_includes_from_stripped(stripped_keep_strings: str) -> list[str]:
    """Core: extrai #Include paths."""
    return sorted({m.group(1) for m in _INCLUDE_RE.finditer(stripped_keep_strings)})


def extract_includes(content: str) -> list[str]:
    """Extrai paths de #Include declarados no fonte (preserva case do nome do header)."""
    return _extract_includes_from_stripped(strip_advpl(content, strip_strings=False))


def _extract_calls_user_func_from_stripped(stripped: str) -> list[dict[str, Any]]:
    """Core: extrai chamadas U_xxx de conteúdo strict-stripado."""
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


def extract_calls_user_func(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas a User Functions (U_xxx). Strip-first remove strings/comentários."""
    return _extract_calls_user_func_from_stripped(strip_advpl(content))


def _extract_calls_execauto_from_stripped(stripped: str) -> list[dict[str, Any]]:
    """Core: extrai chamadas MsExecAuto de strict-stripado."""
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


def extract_calls_execauto(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas MsExecAuto({|x,y,z| ROTINA(x,y,z)}, ...) capturando ROTINA."""
    return _extract_calls_execauto_from_stripped(strip_advpl(content))


def _extract_calls_execblock_from_stripped(
    stripped_keep_strings: str,
) -> list[dict[str, Any]]:
    """Core: extrai chamadas ExecBlock — nome de PE em string literal."""
    result: list[dict[str, Any]] = []
    for m in _EXECBLOCK_RE.finditer(stripped_keep_strings):
        result.append(
            {
                "destino": m.group(1).upper(),
                "tipo": "execblock",
                "linha_origem": _line_at(stripped_keep_strings, m.start()),
                "contexto": stripped_keep_strings[
                    max(0, m.start() - 30) : m.end() + 30
                ][:200],
            }
        )
    return result


def extract_calls_execblock(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas ExecBlock("PE_NAME", ...) — nome de PE em string literal."""
    return _extract_calls_execblock_from_stripped(strip_advpl(content, strip_strings=False))


def _extract_calls_fwloadmodel_from_stripped(
    stripped_keep_strings: str,
) -> list[dict[str, Any]]:
    """Core: extrai FWLoadModel — model id em string literal."""
    result: list[dict[str, Any]] = []
    for m in _FWLOADMODEL_RE.finditer(stripped_keep_strings):
        result.append(
            {
                "destino": m.group(1).upper(),
                "tipo": "fwloadmodel",
                "linha_origem": _line_at(stripped_keep_strings, m.start()),
                "contexto": stripped_keep_strings[
                    max(0, m.start() - 30) : m.end() + 30
                ][:200],
            }
        )
    return result


def extract_calls_fwloadmodel(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas FWLoadModel("MODEL_ID") — model id em string literal."""
    return _extract_calls_fwloadmodel_from_stripped(strip_advpl(content, strip_strings=False))


def _extract_calls_fwexecview_from_stripped(
    stripped_keep_strings: str,
) -> list[dict[str, Any]]:
    """Core: extrai FWExecView — 2º arg é o model id em string literal."""
    result: list[dict[str, Any]] = []
    for m in _FWEXECVIEW_RE.finditer(stripped_keep_strings):
        result.append(
            {
                "destino": m.group(1).upper(),
                "tipo": "fwexecview",
                "linha_origem": _line_at(stripped_keep_strings, m.start()),
                "contexto": stripped_keep_strings[
                    max(0, m.start() - 30) : m.end() + 30
                ][:200],
            }
        )
    return result


def extract_calls_fwexecview(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas FWExecView("Titulo", "MODEL_ID", ...) — captura o 2º arg."""
    return _extract_calls_fwexecview_from_stripped(strip_advpl(content, strip_strings=False))


def _extract_fields_ref_from_stripped(stripped: str) -> list[str]:
    """Core: extrai campos Protheus de strict-stripado."""
    fields: set[str] = set()
    for m in _FIELD_ARROW_RE.finditer(stripped):
        fields.add(m.group(1).upper())
    for m in _FIELD_REPLACE_RE.finditer(stripped):
        fields.add(m.group(1).upper())
    return sorted(fields)


def extract_fields_ref(content: str) -> list[str]:
    """Extrai nomes de campos Protheus referenciados (alias->FIELD ou Replace FIELD).

    Padrão XX_NOME (ex.: A1_NOME, C5_NUM, ZA1_FOO). Filtra por regex que exige
    primeira letra + alfanumérico + underscore + sufixo.
    """
    return _extract_fields_ref_from_stripped(strip_advpl(content))


def _extract_calls_method_from_stripped(stripped: str) -> list[dict[str, Any]]:
    """Core: extrai chamadas de método de strict-stripado."""
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


def extract_calls_method(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas de métodos (obj:method(...) e ::method(...)).

    Atenção: padrão tem MUITO false-positive (qualquer 'a:b(' casa). Preserva case
    do destino. Não tenta resolver classe — apenas registra o uso.
    """
    return _extract_calls_method_from_stripped(strip_advpl(content))


def _extract_rest_endpoints_from_stripped(
    stripped_keep_strings: str,
) -> list[dict[str, Any]]:
    """Core: extrai REST endpoints (WSMETHOD clássico + @Get/@Post TLPP)."""
    result: list[dict[str, Any]] = []
    # WSMETHOD clássico
    for m in _WSMETHOD_REST_RE.finditer(stripped_keep_strings):
        result.append(
            {
                "classe": m.group(3),
                "funcao": m.group(2),
                "verbo": m.group(1).upper(),
                "path": "",
                "annotation_style": "wsmethod_classico",
                "linha": _line_at(stripped_keep_strings, m.start()),
            }
        )
    # Anotação TLPP
    for m in _TLPP_ANNOTATION_RE.finditer(stripped_keep_strings):
        result.append(
            {
                "classe": "",
                "funcao": "",
                "verbo": m.group(1).upper(),
                "path": m.group(2),
                "annotation_style": "@verb_tlpp",
                "linha": _line_at(stripped_keep_strings, m.start()),
            }
        )
    return result


def extract_rest_endpoints(content: str) -> list[dict[str, Any]]:
    """Extrai REST endpoints declarados (WSMETHOD clássico e @Verb TLPP).

    Retorna lista de dicts: {classe, funcao, verbo, path, annotation_style, linha}.
    Usa strip_strings=False porque path do endpoint vem em literal string.
    """
    return _extract_rest_endpoints_from_stripped(strip_advpl(content, strip_strings=False))


_HTTP_METHOD_CANONICAL = {
    "httppost": "HttpPost",
    "httpget": "HttpGet",
    "httpspost": "HttpsPost",
    "httpsget": "HttpsGet",
    "msageturl": "MsAGetUrl",
}


def _extract_http_calls_from_stripped(
    stripped_keep_strings: str,
) -> list[dict[str, Any]]:
    """Core: extrai chamadas HTTP outbound (HttpPost/HttpGet/HttpsPost/HttpsGet/MsAGetUrl)."""
    result: list[dict[str, Any]] = []
    for m in _HTTP_CALL_RE.finditer(stripped_keep_strings):
        metodo_raw = m.group(1).lower()
        result.append(
            {
                "funcao": "",
                "linha": _line_at(stripped_keep_strings, m.start()),
                "metodo": _HTTP_METHOD_CANONICAL[metodo_raw],
                "url_literal": m.group(2),
            }
        )
    return result


def extract_http_calls(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas HTTP outbound (HttpPost/HttpGet/HttpsPost/HttpsGet/MsAGetUrl).

    Retorna lista de dicts: {funcao, linha, metodo, url_literal}.
    Usa strip_strings=False porque a URL é literal string.
    """
    return _extract_http_calls_from_stripped(strip_advpl(content, strip_strings=False))


def _split_top_level_args(args_text: str) -> list[str]:
    """Divide string de argumentos por vírgulas top-level (ignora vírgulas em strings/parens).

    Helper para parsing fino de chamadas onde precisamos mapear argumentos
    posicionais (RpcSetEnv, FwLogMsg, etc.). Não suporta strings com aspas
    escapadas — adequado para MVP onde literais ADVPL são simples.
    """
    parts: list[str] = []
    depth = 0
    in_quote: str | None = None
    current: list[str] = []
    for ch in args_text:
        if in_quote:
            current.append(ch)
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ('"', "'"):
            in_quote = ch
            current.append(ch)
            continue
        if ch in "([{":
            depth += 1
            current.append(ch)
            continue
        if ch in ")]}":
            depth -= 1
            current.append(ch)
            continue
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail or parts:
        parts.append(tail)
    return parts


def _arg_literal_or_empty(arg: str) -> str:
    """Retorna o conteúdo literal se arg for string entre aspas; senão "" (variável)."""
    m = _QUOTED_ARG_RE.match(arg)
    return m.group(1) if m else ""


def _capture_call_args(content: str, open_end: int) -> tuple[str, int] | None:
    """A partir do offset open_end (logo após '('), captura conteúdo até o ')' balanceado.

    Retorna (args_text, close_offset) ou None se não encontrou fechamento.
    """
    depth = 1
    in_quote: str | None = None
    i = open_end
    n = len(content)
    while i < n:
        ch = content[i]
        if in_quote:
            if ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return content[open_end:i], i
        i += 1
    return None


def _extract_env_openers_from_stripped(
    stripped_keep_strings: str,
) -> list[dict[str, Any]]:
    """Core: extrai chamadas RpcSetEnv. Variáveis (não literais) viram strings vazias."""
    result: list[dict[str, Any]] = []
    for m in _RPCSETENV_OPEN_RE.finditer(stripped_keep_strings):
        captured = _capture_call_args(stripped_keep_strings, m.end())
        if captured is None:
            continue
        args_text, _close = captured
        args = _split_top_level_args(args_text)
        # Posições: 1=empresa, 2=filial, 3=user, 4=pwd, 5=env, 6=modulo
        def get(i: int) -> str:
            return _arg_literal_or_empty(args[i]) if i < len(args) else ""

        result.append(
            {
                "funcao": "",
                "linha": _line_at(stripped_keep_strings, m.start()),
                "empresa": get(0),
                "filial": get(1),
                "environment": get(4),
                "modulo": get(5),
            }
        )
    return result


def extract_env_openers(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas RpcSetEnv com empresa/filial/environment/modulo.

    Retorna lista de dicts: {funcao, linha, empresa, filial, environment, modulo}.
    Argumentos que são variáveis (não literais) viram strings vazias.
    Usa strip_strings=False porque os valores vêm em literais.
    """
    return _extract_env_openers_from_stripped(strip_advpl(content, strip_strings=False))


def _extract_log_calls_from_stripped(
    stripped_keep_strings: str,
) -> list[dict[str, Any]]:
    """Core: extrai chamadas de log (FwLogMsg, ConOut).

    FwLogMsg("nivel", "msg", "service", "categoria", ...) → nível=arg0 literal,
    categoria=arg3 literal (4º arg). Variáveis viram strings vazias.
    ConOut("...") → nível="conout", categoria="".
    """
    result: list[dict[str, Any]] = []
    for m in _FWLOGMSG_OPEN_RE.finditer(stripped_keep_strings):
        captured = _capture_call_args(stripped_keep_strings, m.end())
        if captured is None:
            continue
        args_text, _close = captured
        args = _split_top_level_args(args_text)
        nivel = _arg_literal_or_empty(args[0]) if args else ""
        categoria = _arg_literal_or_empty(args[3]) if len(args) > 3 else ""
        result.append(
            {
                "funcao": "",
                "linha": _line_at(stripped_keep_strings, m.start()),
                "nivel": nivel,
                "categoria": categoria,
            }
        )
    for m in _CONOUT_OPEN_RE.finditer(stripped_keep_strings):
        result.append(
            {
                "funcao": "",
                "linha": _line_at(stripped_keep_strings, m.start()),
                "nivel": "conout",
                "categoria": "",
            }
        )
    return result


def extract_log_calls(content: str) -> list[dict[str, Any]]:
    """Extrai chamadas de log: FwLogMsg(nivel, msg, ...) e ConOut(...).

    Retorna lista de dicts: {funcao, linha, nivel, categoria}.
    Usa strip_strings=False porque níveis/categorias são literais.
    """
    return _extract_log_calls_from_stripped(strip_advpl(content, strip_strings=False))


def _extract_defines_from_stripped(
    stripped_keep_strings: str,
) -> list[dict[str, Any]]:
    """Core: extrai #DEFINE NOME valor — pega valor cumulativo até fim de linha."""
    result: list[dict[str, Any]] = []
    for m in _DEFINE_RE.finditer(stripped_keep_strings):
        result.append(
            {
                "nome": m.group(1),
                "valor": m.group(2).strip(),
                "linha": _line_at(stripped_keep_strings, m.start()),
            }
        )
    return result


def extract_defines(content: str) -> list[dict[str, Any]]:
    """Extrai diretivas #DEFINE NOME valor — valor pode ser literal string.

    Retorna lista de dicts: {nome, valor, linha}.
    Usa strip_strings=False porque defines podem ter literal string como valor.
    """
    return _extract_defines_from_stripped(strip_advpl(content, strip_strings=False))


_MVC_HOOK_CANONICAL = {
    "bcommit": "bCommit",
    "bcancel": "bCancel",
    "btudook": "bTudoOk",
    "blineok": "bLineOk",
    "bposvld": "bPosVld",
    "bprevld": "bPreVld",
    "bwhen": "bWhen",
    "bvalid": "bValid",
    "bload": "bLoad",
}


def _extract_mvc_hooks_from_stripped(stripped: str) -> list[dict[str, Any]]:
    """Core: extrai hooks MVC (bCommit/bCancel/...) atribuídos via := ou =.

    Retorna como chamadas com tipo='mvc_hook'; nome canonizado para destino.
    Roda sobre stripped_strict (strings removidas) para não capturar hooks
    declarados dentro de strings literais.
    """
    result: list[dict[str, Any]] = []
    for m in _MVC_HOOK_RE.finditer(stripped):
        nome = _MVC_HOOK_CANONICAL[m.group(1).lower()]
        result.append(
            {
                "destino": nome,
                "tipo": "mvc_hook",
                "linha_origem": _line_at(stripped, m.start()),
                "contexto": stripped[max(0, m.start() - 30) : m.end() + 30][:200],
            }
        )
    return result


def extract_mvc_hooks(content: str) -> list[dict[str, Any]]:
    """Extrai atribuições a hooks MVC (bCommit, bCancel, bTudoOk, bLineOk, etc.).

    Retorna lista no formato de chamadas: {destino, tipo='mvc_hook', linha_origem, contexto}.
    Strip-first remove strings/comentários.
    """
    return _extract_mvc_hooks_from_stripped(strip_advpl(content))


def _next_end_offset(content: str, start: int, end_re: re.Pattern[str]) -> int:
    """Encontra offset do próximo END a partir de start; senão end-of-content."""
    m = end_re.search(content, start)
    return m.start() if m else len(content)


def _extract_ws_structures_from_stripped(
    stripped_keep_strings: str,
) -> dict[str, list[dict[str, Any]]]:
    """Core: extrai WSSTRUCT/WSSERVICE/WSMETHOD com WSDATA fields.

    Mimetiza Protheus/backend/services/parser_source.py linhas 124-179.
    Lê WSDATA dentro da janela de cada struct/service (até próximo END).

    TODO MVP: parser não verifica aninhamento; structs declarados dentro de
    services podem ser duplicados — aceitável no MVP onde o foco é detecção.
    """
    result: dict[str, list[dict[str, Any]]] = {
        "ws_structs": [],
        "ws_services": [],
        "ws_methods": [],
    }

    # WSSTRUCT blocks
    for m in _WSSTRUCT_HEADER_RE.finditer(stripped_keep_strings):
        name = m.group(1)
        if name.upper() in _WS_RESERVED:
            continue
        end = _next_end_offset(stripped_keep_strings, m.end(), _END_WSSTRUCT_RE)
        body = stripped_keep_strings[m.end() : end]
        fields = [
            {"nome": fm.group(1), "tipo": fm.group(2)}
            for fm in _WSDATA_FIELD_RE.finditer(body)
        ]
        result["ws_structs"].append({"nome": name, "campos": fields})

    # WSSERVICE blocks (com WSMETHOD declarations e WSDATA fields)
    for m in _WSSERVICE_HEADER_RE.finditer(stripped_keep_strings):
        name = m.group(1)
        if name.upper() in _WS_RESERVED:
            continue
        end = _next_end_offset(stripped_keep_strings, m.end(), _END_WSSERVICE_RE)
        body = stripped_keep_strings[m.end() : end]
        metodos = [mm.group(1) for mm in _WSMETHOD_BARE_RE.finditer(body)]
        dados = [
            {"nome": dm.group(1), "tipo": dm.group(2)}
            for dm in _WSDATA_FIELD_RE.finditer(body)
        ]
        result["ws_services"].append({"nome": name, "metodos": metodos, "dados": dados})

    # WSMETHOD com full signature (receive/send/service)
    for m in _WSMETHOD_FULL_RE.finditer(stripped_keep_strings):
        result["ws_methods"].append(
            {
                "nome": m.group(1),
                "receive": m.group(2),
                "send": m.group(3),
                "service": m.group(4),
            }
        )

    return result


def extract_ws_structures(content: str) -> dict[str, list[dict[str, Any]]]:
    """Extrai WSSTRUCT/WSSERVICE/WSMETHOD declarações.

    Retorna: {ws_structs, ws_services, ws_methods}.
    ws_structs: [{nome, campos:[{nome, tipo}]}].
    ws_services: [{nome, metodos:[...], dados:[{nome, tipo}]}].
    ws_methods: [{nome, receive, send, service}].
    Usa strip_strings=False (declarações têm WSDATA tipo as String literais).
    """
    return _extract_ws_structures_from_stripped(strip_advpl(content, strip_strings=False))


def _extract_namespace_from_stripped(stripped: str) -> str:
    """Core: retorna primeiro match de `Namespace x.y.z`. String vazia se não houver."""
    m = _NAMESPACE_RE.search(stripped)
    return m.group(1) if m else ""


def extract_namespace(content: str) -> str:
    """Extrai a declaração TLPP `Namespace x.y.z`. Vazio se não houver.

    Strip-first remove strings/comentários (ignora namespace em literais).
    """
    return _extract_namespace_from_stripped(strip_advpl(content))


def _empty_result(file_path: Path, encoding: str) -> dict[str, Any]:
    """Resultado de parse_source para arquivos vazios."""
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


def parse_source(file_path: Path) -> dict[str, Any]:
    """Orquestra todas as extrações sobre um fonte. Retorna dict completo.

    Output:
        arquivo, caminho, encoding, lines_of_code, funcoes, tabelas_ref,
        parametros_uso, perguntas_uso, includes, chamadas, campos_ref, hash.

    Hash é SHA-1 dos bytes raw do arquivo (40 char hex). Usado para stale
    detection no ingest incremental (spec §11.2 #23). Hash direto dos bytes
    evita round-trip de decode/encode que poderia corromper o digest em
    arquivos com encoding ambíguo (cf. I7 do code review).

    Performance: strip_advpl é executado no máximo 2 vezes por arquivo (uma
    para strip_strings=True, outra para strip_strings=False) e todos os
    extratores compartilham essas duas variantes (cf. C2).
    """
    raw = file_path.read_bytes()
    content, encoding = _decode_bytes(raw)
    if not content:
        return _empty_result(file_path, encoding)

    stripped_strict = strip_advpl(content, strip_strings=True)
    stripped_keep_strings = strip_advpl(content, strip_strings=False)

    funcs = _extract_functions_from_stripped(stripped_strict)
    funcs = _add_function_ranges(funcs, content)

    return {
        "arquivo": file_path.name,
        "caminho": str(file_path),
        "encoding": encoding,
        "lines_of_code": content.count("\n") + (0 if content.endswith("\n") else 1),
        "funcoes": funcs,
        "tabelas_ref": _extract_tables_from_stripped(stripped_keep_strings, stripped_strict),
        "parametros_uso": _extract_params_from_stripped(stripped_keep_strings),
        "perguntas_uso": _extract_perguntas_from_stripped(stripped_keep_strings),
        "includes": _extract_includes_from_stripped(stripped_keep_strings),
        "chamadas": (
            _extract_calls_user_func_from_stripped(stripped_strict)
            + _extract_calls_execauto_from_stripped(stripped_strict)
            + _extract_calls_execblock_from_stripped(stripped_keep_strings)
            + _extract_calls_fwloadmodel_from_stripped(stripped_keep_strings)
            + _extract_calls_fwexecview_from_stripped(stripped_keep_strings)
            + _extract_calls_method_from_stripped(stripped_strict)
        ),
        "campos_ref": _extract_fields_ref_from_stripped(stripped_strict),
        # SHA-1 não é uso criptográfico — apenas content-addressed hash para stale detection.
        "hash": hashlib.sha1(raw).hexdigest() if raw else "",
    }
