"""Parser de INI Protheus — captura seções, chaves, comentários, encoding.

Porta a engine validada do ``env_manager.parse_ini`` (920 linhas) pro idioma
do plugadvpl: dataclasses tipadas em vez de dicts crus, sem state global, sem
acesso a YAML/regras. O audit (cruzar com ``ini_rules``) acontece em
``parsing/ini_audit.py``.

Particularidades de INI Protheus capturadas:

- **Seções comentadas** ``;[NomeSecao]`` — toda chave abaixo (até a próxima seção
  ativa) é considerada inativa, mesmo sem ``;`` no início da linha.
- **Merge case-insensitive** — ``[TSSTaskProc]`` e ``[tsstaskproc]`` são a mesma
  seção; preservamos a primeira ocorrência como ``name_raw``.
- **Encoding** — Protheus exige ANSI (Windows-1252). Detectamos BOM/UTF-16/UTF-8
  e emitimos warning. Decode com fallback ``utf-8 -> cp1252``.
- **Comentários** — capturamos comentários acima (``;`` ou ``#``) e inline (após
  ``;`` na mesma linha de uma chave) por chave. Detecta também o padrão TOTVS
  "comentário pós" — chave seguida de ``;CHAVE=valor exemplo`` na próxima linha.

Exemplo de uso:

>>> from pathlib import Path
>>> from plugadvpl.parsing.ini import parse_ini_file
>>> content = Path("/srv/protheus/appserver.ini").read_bytes()
>>> parsed = parse_ini_file(content, filename="appserver.ini")
>>> parsed.tipo, parsed.role
('appserver', 'standalone')
>>> len(parsed.sections), len(parsed.keys)
(12, 87)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# Dataclasses (estruturas retornadas pelo parser)
# =============================================================================


@dataclass(slots=True)
class IniKey:
    """1 par chave=valor dentro de uma seção."""
    section_name: str         # nome real da seção (case preservado)
    key_name: str             # case preservado
    value: str
    linha: int                # 1-based
    comment_inline: str = ""  # comentário na MESMA linha após ``;``
    comment_above: str = ""   # comentários nas linhas IMEDIATAMENTE acima


@dataclass(slots=True)
class IniSection:
    """Seção ``[Nome]`` ou ``;[Nome]`` (inativa)."""
    name_raw: str
    name_norm: str            # lowercase
    commented: bool = False
    linha_inicio: int = 0
    linha_fim: int = 0
    comment_text: str = ""    # comentários acima da declaração


@dataclass(slots=True)
class IniDirtyLine:
    """Linha que não casa o formato esperado (chave inválida, valor vazio onde não
    deveria, linha solta fora de seção, etc.)."""
    linha: int
    content: str
    reason: str


@dataclass(slots=True)
class IniEncodingInfo:
    detected: str = "unknown"        # ascii|utf-8|utf-8-bom|utf-16|cp1252|unknown
    has_bom: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedIni:
    filename: str
    tipo: str                                       # appserver|dbaccess|smartclient|tss|broker|custom
    role: str                                       # broker_http|slave_rest|... (14 possíveis)
    sections: list[IniSection]
    keys: list[IniKey]
    dirty_lines: list[IniDirtyLine]
    encoding_info: IniEncodingInfo
    # Mapas pra navegação rápida
    sections_by_name_norm: dict[str, IniSection] = field(default_factory=dict)


# =============================================================================
# Encoding
# =============================================================================


_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"


def analyze_encoding(content_bytes: bytes) -> IniEncodingInfo:
    info = IniEncodingInfo()
    if content_bytes.startswith(_UTF8_BOM):
        info.detected = "utf-8-bom"
        info.has_bom = True
        info.warnings.append(
            "Arquivo possui BOM UTF-8. Protheus requer ANSI (CP1252) — converter sem BOM."
        )
    elif content_bytes.startswith(_UTF16_LE_BOM) or content_bytes.startswith(_UTF16_BE_BOM):
        info.detected = "utf-16"
        info.has_bom = True
        info.warnings.append(
            "Arquivo em UTF-16. Protheus nao suporta — converter para ANSI/CP1252."
        )
    else:
        try:
            content_bytes.decode("ascii")
            info.detected = "ascii"
        except UnicodeDecodeError:
            try:
                content_bytes.decode("utf-8")
                info.detected = "utf-8"
                info.warnings.append(
                    "Arquivo em UTF-8 sem BOM. Protheus prefere ANSI (CP1252)."
                )
            except UnicodeDecodeError:
                info.detected = "cp1252"
    return info


def decode_ini_bytes(content_bytes: bytes) -> str:
    """Decode com fallback utf-8 → cp1252."""
    if content_bytes.startswith(_UTF8_BOM):
        return content_bytes[len(_UTF8_BOM):].decode("utf-8", errors="replace")
    try:
        return content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return content_bytes.decode("cp1252", errors="replace")


# =============================================================================
# Parser core
# =============================================================================


_SECTION_COMMENTED_RE = re.compile(r"^[;#]\s*\[(.+)\]")
_SECTION_RE = re.compile(r"^\[(.+)\]$")
_KEY_VALID_RE = re.compile(r"^[A-Za-z_][\w.]*$")
_COMMENT_KEY_RE = re.compile(r"^[;#]\s*([A-Za-z_]\w*)\s*=\s*(.*)")
_INLINE_COMMENT_RE = re.compile(r"^(.*?)\s+[;#]\s*(.+)$")

_ENV_KEY_INDICATORS = frozenset({
    "rootpath", "sourcepath", "rpodb", "rpoversion", "startpath",
})

_EMPTY_VALUE_OK_KEYS = frozenset({"memo", "trace", "debug", "x2_path", "mpp"})
_DB_OPTIONAL_EMPTY_KEYS = frozenset({"tablespace", "indexspace", "lobspace"})


def _is_environment_section(section: IniSection, all_keys: list[IniKey]) -> bool:
    keys_lower = {
        k.key_name.lower()
        for k in all_keys
        if k.section_name.lower() == section.name_norm
    }
    return bool(keys_lower & _ENV_KEY_INDICATORS)


def _env_section_count(sections: list[IniSection], keys: list[IniKey]) -> int:
    return sum(1 for s in sections if _is_environment_section(s, keys))


def _detect_ini_type(filename: str, sections: list[IniSection], keys: list[IniKey]) -> str:
    """tss > broker > dbaccess > appserver > smartclient > custom."""
    fname = filename.lower()
    section_names_norm = {s.name_norm for s in sections if not s.commented}
    all_keys_lower: set[str] = {k.key_name.lower() for k in keys}

    tss_section_markers = {"tsstaskproc", "ipc_distmail", "tssoffline", "ipc_smtp"}
    tss_key_markers = {"sped_savewsdl", "tsssecurity"}
    if (section_names_norm & tss_section_markers) or (
        "job_ws" in section_names_norm and (all_keys_lower & tss_key_markers)
    ):
        return "tss"

    has_balance = any(s.startswith("balance_") for s in section_names_norm)
    has_env = any(_is_environment_section(s, keys) for s in sections)
    if has_balance and not has_env:
        return "broker"

    if "appserver" in fname:
        return "appserver"
    if "dbaccess" in fname:
        return "dbaccess"
    if "smartclient" in fname:
        return "smartclient"

    if "dbaccess" in section_names_norm or "mssql" in section_names_norm \
            or "oracle" in section_names_norm:
        return "dbaccess"
    if "general" in section_names_norm and (
        "drivers" in section_names_norm or "licenseserver" in section_names_norm
    ):
        return "appserver"
    if "config" in section_names_norm and "drivers" in section_names_norm:
        return "smartclient"
    return "custom"


def _detect_ini_role(
    filename: str,
    sections: list[IniSection],
    keys: list[IniKey],
    ini_type: str,
) -> str:
    """14 roles possíveis. Lógica idêntica ao env_manager._detect_ini_role."""
    fname = filename.lower()
    section_names_norm = {s.name_norm for s in sections if not s.commented}

    if ini_type == "tss":
        return "tss"
    if ini_type == "dbaccess":
        # Mode na seção [General]
        for k in keys:
            if k.section_name.lower() == "general" and k.key_name.lower() == "mode":
                mv = k.value.lower().strip()
                if mv == "master":
                    return "dbaccess_master"
                if mv == "slave":
                    return "dbaccess_slave"
                break
        return "dbaccess_standalone"

    has_balance = any(s.startswith("balance_") for s in section_names_norm)
    has_env = any(_is_environment_section(s, keys) for s in sections)
    if has_balance and not has_env:
        if "balance_http" in section_names_norm:
            return "broker_http"
        if "balance_web_services" in section_names_norm:
            return "broker_rest" if "rest" in fname else "broker_soap"
        return "broker_http"

    has_onstart = "onstart" in section_names_norm
    has_httprest = "httprest" in section_names_norm
    has_httpjob = "httpjob" in section_names_norm

    if has_onstart and not has_httprest:
        jobs_val = ""
        for k in keys:
            if k.section_name.lower() == "onstart" and k.key_name.lower() == "jobs":
                jobs_val = k.value.lower()
                break
        ws_indicators = {"job_ws", "job_http", "httpjob"}
        job_names = {j.strip() for j in jobs_val.split(",") if j.strip()}
        if job_names and not (job_names & ws_indicators):
            return "job_server"

    if has_httprest and has_httpjob and "job_ws" not in section_names_norm:
        if "licenseclient" in section_names_norm:
            return "slave_rest"
        return "rest_server"

    ws_job_sections = {s for s in section_names_norm if s.startswith("job_ws") or s.startswith("job_")}
    host_port_sections = {s for s in section_names_norm if ":" in s}
    if ws_job_sections and host_port_sections and any("ws" in s for s in ws_job_sections):
        return "slave_ws"

    if "licenseclient" in section_names_norm and "webapp" in section_names_norm:
        if _env_section_count(sections, keys) <= 2:
            return "slave"

    if _env_section_count(sections, keys) >= 3:
        return "standalone_multi_env"
    return "standalone"


# =============================================================================
# Parser principal
# =============================================================================


def parse_ini_file(content: str | bytes, filename: str = "") -> ParsedIni:
    """Parseia INI Protheus.

    Aceita ``str`` (já decodificado) ou ``bytes`` (decoda com fallback utf-8 →
    cp1252). Sempre retorna ``ParsedIni`` mesmo que o arquivo esteja vazio.

    Comportamento dos comentários:
        - ``;[Section]``    — seção é marcada ``commented=True``; chaves abaixo
          são parseadas mas marcadas como ``;`` (não aparecem em ``keys``).
        - ``; comentário acima``  — anexado ao próximo IniKey/IniSection.
        - ``Key=Value ; inline`` — vira ``IniKey.comment_inline``.
        - ``;Key=valor_exemplo`` logo após uma chave ativa — anexado a
          ``comment_above`` da chave ativa (padrão TOTVS de documentar
          alternativas).
    """
    # Encoding info só faz sentido quando o caller entrega bytes brutos. Quando
    # a entrada é str já decodificada, o round-trip ``encode().analyze()`` sempre
    # retorna utf-8/ascii — informação sem valor diagnóstico. Skip neste caso
    # (review #5) e devolve placeholder ``"str"``.
    if isinstance(content, bytes):
        encoding_info = analyze_encoding(content)
        text = decode_ini_bytes(content)
    else:
        encoding_info = IniEncodingInfo(detected="str")
        text = content

    sections: list[IniSection] = []
    keys: list[IniKey] = []
    dirty: list[IniDirtyLine] = []
    sections_by_norm: dict[str, IniSection] = {}

    current_section: IniSection | None = None
    in_commented_section = False
    pending_comments: list[str] = []

    raw_lines = text.splitlines()

    for idx, line in enumerate(raw_lines):
        line_num = idx + 1
        stripped = line.strip()

        if not stripped:
            # linha em branco quebra a sequência de comentários pendentes
            pending_comments = []
            if current_section is not None:
                current_section.linha_fim = line_num
            continue

        # --- Seção comentada: ;[Section] ---
        m = _SECTION_COMMENTED_RE.match(stripped)
        if m:
            name = m.group(1).strip()
            norm = name.lower()
            existing = sections_by_norm.get(norm)
            if existing is None:
                sec = IniSection(
                    name_raw=name,
                    name_norm=norm,
                    commented=True,
                    linha_inicio=line_num,
                    linha_fim=line_num,
                    comment_text=" | ".join(pending_comments),
                )
                sections.append(sec)
                sections_by_norm[norm] = sec
                current_section = sec
            else:
                current_section = existing
            in_commented_section = True
            pending_comments = []
            continue

        # --- Seção ativa: [Section] ---
        m = _SECTION_RE.match(stripped)
        if m:
            name = m.group(1).strip()
            norm = name.lower()
            existing = sections_by_norm.get(norm)
            if existing is None:
                sec = IniSection(
                    name_raw=name,
                    name_norm=norm,
                    commented=False,
                    linha_inicio=line_num,
                    linha_fim=line_num,
                    comment_text=" | ".join(pending_comments),
                )
                sections.append(sec)
                sections_by_norm[norm] = sec
                current_section = sec
            else:
                # merge: mantém name_raw original mas atualiza linha_fim
                current_section = existing
                if existing.commented:
                    # achou versão ativa, "destrava"
                    existing.commented = False
            in_commented_section = False
            pending_comments = []
            continue

        # --- Linha fora de seção ---
        if current_section is None:
            if not stripped.startswith((";", "#")):
                dirty.append(IniDirtyLine(
                    linha=line_num,
                    content=stripped,
                    reason="Linha fora de qualquer secao. Sera ignorada pelo Protheus.",
                ))
            continue

        # --- Dentro de seção comentada: ignora chaves (só conta como inativa) ---
        if in_commented_section:
            current_section.linha_fim = line_num
            continue

        # --- Linha comentada que parece chave=valor (;KEY=valor) ---
        m = _COMMENT_KEY_RE.match(stripped)
        if m:
            # se for tipo ';KEY=valor exemplo', vira nota acima da próxima chave
            # ou nota inline da chave anterior (não tratamos aqui — _enrich abaixo)
            pending_comments.append(stripped.lstrip(";#").strip())
            continue

        # --- Linha 100% comentada ---
        if stripped.startswith((";", "#")):
            comment_text = stripped.lstrip(";#").strip()
            if comment_text:
                pending_comments.append(comment_text)
            continue

        # --- Linha de chave=valor ---
        if "=" in stripped:
            # Detecta inline comment ANTES de extrair valor: 'Key=Value ; nota'
            value_with_comment = stripped.partition("=")[2]
            inline_match = _INLINE_COMMENT_RE.match(value_with_comment)

            key_part, _, _ = stripped.partition("=")
            key = key_part.strip()

            if inline_match:
                value = inline_match.group(1).strip()
                inline_comment = inline_match.group(2).strip()
            else:
                value = value_with_comment.strip()
                inline_comment = ""

            if not _KEY_VALID_RE.match(key):
                dirty.append(IniDirtyLine(
                    linha=line_num,
                    content=stripped,
                    reason=f"Nome de chave invalido: '{key}'.",
                ))
                pending_comments = []
                continue

            # Detecta valor vazio (com exceções legítimas)
            sec_low = current_section.name_norm
            in_non_oracle_driver = sec_low.startswith(
                ("mssql/", "postgresql/", "db2/", "informix/")
            )
            is_empty_ok = (
                key.lower() in _EMPTY_VALUE_OK_KEYS
                or (key.lower() in _DB_OPTIONAL_EMPTY_KEYS and in_non_oracle_driver)
            )
            if not value and not is_empty_ok:
                dirty.append(IniDirtyLine(
                    linha=line_num,
                    content=stripped,
                    reason=f"Chave '{key}' com valor vazio.",
                ))

            keys.append(IniKey(
                section_name=current_section.name_raw,
                key_name=key,
                value=value,
                linha=line_num,
                comment_inline=inline_comment,
                comment_above=" | ".join(pending_comments),
            ))
            current_section.linha_fim = line_num
            pending_comments = []
        else:
            dirty.append(IniDirtyLine(
                linha=line_num,
                content=stripped,
                reason="Linha sem formato chave=valor.",
            ))
            pending_comments = []

    # === Detecção pós-parse ===
    tipo = _detect_ini_type(filename, sections, keys)
    role = _detect_ini_role(filename, sections, keys, tipo)

    # Enriquece comentários "pós" (até 12 linhas após cada chave ativa)
    _enrich_post_comments(raw_lines, keys, sections_by_norm)

    return ParsedIni(
        filename=filename,
        tipo=tipo,
        role=role,
        sections=sections,
        keys=keys,
        dirty_lines=dirty,
        encoding_info=encoding_info,
        sections_by_name_norm=sections_by_norm,
    )


def _enrich_post_comments(
    raw_lines: list[str],
    keys: list[IniKey],
    sections_by_norm: dict[str, IniSection],
) -> None:
    """Captura comentários que vêm APÓS a definição de uma chave (até 12 linhas
    ou até a próxima seção). Padrão TOTVS de documentar alternativas:

        ConsoleLog=1
        ; ConsoleLog=0  -- valor antigo, desativado em 2024
        ; ConsoleLog=2  -- modo verbose, performance ruim

    Anexa ao ``comment_above`` da chave ativa (efetivamente: 'context comments').
    """
    keys_by_loc: dict[tuple[str, str], IniKey] = {
        (k.section_name.lower(), k.key_name.lower()): k for k in keys
    }
    for idx, line in enumerate(raw_lines):
        stripped = line.strip()
        if _SECTION_RE.match(stripped) or _SECTION_COMMENTED_RE.match(stripped):
            continue
        if "=" not in stripped or stripped.startswith((";", "#")):
            continue
        key_part = stripped.partition("=")[0].strip()
        if not _KEY_VALID_RE.match(key_part):
            continue

        # acha a seção dessa linha (busca pra trás)
        sec_norm = None
        for j in range(idx, -1, -1):
            ls = raw_lines[j].strip()
            m = _SECTION_RE.match(ls)
            if m:
                sec_norm = m.group(1).strip().lower()
                break

        if sec_norm is None:
            continue

        target = keys_by_loc.get((sec_norm, key_part.lower()))
        if target is None or target.linha != idx + 1:
            continue

        # Captura até 12 linhas seguintes (ou até próxima seção/chave ativa)
        extras: list[str] = []
        for j in range(idx + 1, min(idx + 13, len(raw_lines))):
            lj = raw_lines[j].strip()
            if _SECTION_RE.match(lj) or _SECTION_COMMENTED_RE.match(lj):
                break
            mck = _COMMENT_KEY_RE.match(lj)
            if mck and mck.group(1).lower() == key_part.lower():
                rest = mck.group(2).strip()
                if rest:
                    extras.append(rest)
                continue
            if lj.startswith((";", "#")):
                cont = lj.lstrip(";#").strip()
                if cont and not _KEY_VALID_RE.match(cont.partition("=")[0].strip()):
                    extras.append(cont)
                continue
            # Linha não-comentário-não-vazia: para
            if lj:
                break

        if extras:
            existing = target.comment_above
            combined = (existing + " | " + " | ".join(extras)) if existing else " | ".join(extras)
            target.comment_above = combined


# =============================================================================
# Helpers públicos pra discovery
# =============================================================================


def is_protheus_ini_filename(name: str) -> bool:
    """Heurística pra discovery: o nome bate com algum padrão de INI Protheus.

    Aceita qualquer ``.ini`` cujo nome contenha um dos tokens-chave em qualquer
    posição (cobre ``appserver.ini``, ``dev_appserver.ini``, ``appserver_qa.ini``,
    ``prd-dbaccess.ini``, etc.). Falsos positivos potenciais são raros — o parser
    a jusante classifica e detecta o ``tipo`` final via ``_detect_ini_type``.
    """
    n = name.lower()
    if not n.endswith(".ini"):
        return False
    tokens = ("appserver", "dbaccess", "smartclient", "tss", "broker")
    return any(t in n for t in tokens)


__all__ = [
    "IniDirtyLine",
    "IniEncodingInfo",
    "IniKey",
    "IniSection",
    "ParsedIni",
    "analyze_encoding",
    "decode_ini_bytes",
    "is_protheus_ini_filename",
    "parse_ini_file",
]
