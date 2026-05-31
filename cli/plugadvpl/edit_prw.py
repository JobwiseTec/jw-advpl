"""Conversão CP1252 ↔ UTF-8 para fontes ADVPL/TLPP (v0.7.0 Fase 0 #5).

Comando ``plugadvpl edit-prw`` com 3 sub-comandos:

- ``check`` — detecta encoding e reporta divergência com a extensão esperada.
- ``open``  — imprime conteúdo em UTF-8 puro (edição em qualquer editor moderno).
- ``save``  — converte ``--from <enc>`` para ``--to <enc>`` (default infere ambas
  por extensão e detecção). Cria backup ``<file>.bak`` antes de gravar
  (a menos que ``--no-backup``).

Default por extensão:
    .prw / .prx → cp1252
    .tlpp / .tlpp.ch / .ch → utf-8

Estratégia de detecção:
    1. BOM UTF-8 (EF BB BF) → utf-8
    2. ASCII puro (sem byte ≥ 0x80) → cp1252 (ASCII é subset)
    3. Decode UTF-8 strict ok + tem byte ≥ 0x80 → utf-8
    4. Fallback cp1252
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

UTF8_BOM = b"\xef\xbb\xbf"
_ASCII_HIGH_BIT = 0x80  # primeiro byte non-ASCII; usado pra heurística cp1252 vs utf-8

_PRW_EXTS = (".prw", ".prx")
_TLPP_EXTS = (".tlpp", ".tlpp.ch", ".ch")


@dataclass(frozen=True)
class EncodingReport:
    """Resultado de :func:`check_encoding`."""

    file: str
    extension: str
    expected_encoding: str
    detected_encoding: str
    has_bom: bool
    match: bool
    non_ascii_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "extension": self.extension,
            "expected_encoding": self.expected_encoding,
            "detected_encoding": self.detected_encoding,
            "has_bom": self.has_bom,
            "match": self.match,
            "non_ascii_bytes": self.non_ascii_bytes,
        }


def expected_encoding_for(path: Path) -> str:
    """Retorna o encoding "esperado" para a extensão do arquivo.

    Convenção TOTVS:
        .prw/.prx  → cp1252 (compilador AppServer legado)
        .tlpp/.ch  → utf-8 (TLPP moderno + headers)
    """
    name = path.name.lower()
    if name.endswith(".tlpp.ch"):
        return "utf-8"
    suffix = path.suffix.lower()
    if suffix in _PRW_EXTS:
        return "cp1252"
    if suffix in _TLPP_EXTS:
        return "utf-8"
    # Default conservador: cp1252 (padrão Protheus histórico)
    return "cp1252"


def encode_cp1252_bytes(text: str) -> bytes:
    """Encode string para CP1252 bytes (errors='replace').

    Função pura — reusada por compile.py para gerar .ini do advpls.
    """
    return text.encode("cp1252", errors="replace")


def detect_encoding(raw: bytes) -> tuple[str, bool, int]:
    """Detecta encoding via heurística determinística.

    Retorna (encoding, has_bom, non_ascii_count). Não usa chardet — a regra
    é simples o suficiente pra ser exata:

    1. BOM EF BB BF → utf-8 (sempre)
    2. Sem byte ≥ 0x80 → cp1252 (ASCII é subset, escolhe default)
    3. Decode UTF-8 strict ok + multi-byte presente → utf-8
    4. Fallback → cp1252
    """
    has_bom = raw.startswith(UTF8_BOM)
    payload = raw[len(UTF8_BOM) :] if has_bom else raw
    non_ascii = sum(1 for b in payload if b >= _ASCII_HIGH_BIT)

    if has_bom:
        return "utf-8", True, non_ascii
    if non_ascii == 0:
        return "cp1252", False, 0
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError:
        return "cp1252", False, non_ascii
    return "utf-8", False, non_ascii


def check_encoding(path: Path) -> EncodingReport:
    """Lê arquivo e produz :class:`EncodingReport` (sem efeitos colaterais)."""
    raw = path.read_bytes()
    expected = expected_encoding_for(path)
    detected, has_bom, non_ascii = detect_encoding(raw)
    return EncodingReport(
        file=str(path),
        extension=path.suffix.lower() or path.name.lower(),
        expected_encoding=expected,
        detected_encoding=detected,
        has_bom=has_bom,
        match=(detected == expected),
        non_ascii_bytes=non_ascii,
    )


def read_as_utf8(path: Path) -> str:
    """Lê arquivo em qualquer encoding suportado e devolve string UTF-8 lógica.

    Ideal para edição em editor moderno: leitura tolerante, escrita determinística.
    Erros de decode usam ``errors='replace'`` para não derrubar a leitura.
    """
    raw = path.read_bytes()
    detected, has_bom, _ = detect_encoding(raw)
    payload = raw[len(UTF8_BOM) :] if has_bom else raw
    if detected == "utf-8":
        return payload.decode("utf-8", errors="replace")
    return payload.decode("cp1252", errors="replace")


def convert_and_save(
    path: Path,
    *,
    to_encoding: str | None = None,
    from_encoding: str | None = None,
    backup: bool = True,
    timestamp: bool = False,
) -> tuple[str, str, Path | None]:
    """Converte arquivo de ``from_encoding`` para ``to_encoding`` e grava in-place.

    Args:
        path: arquivo a converter.
        to_encoding: encoding de destino. Default = ``expected_encoding_for(path)``.
        from_encoding: encoding de origem. Default = ``detect_encoding(raw)[0]``.
        backup: se True (default), cria backup antes de gravar.
        timestamp: v0.18.0+ — se True E ``backup=True``, cria
            ``<path>.bak.<YYYYMMDDHHMMSS>`` ao invés de ``<path>.bak`` fixo.
            Preserva ``.bak`` legado existente (não sobrescreve).

    Returns:
        Tupla ``(from_used, to_used, backup_path_or_None)``.

    Raises:
        ValueError: se ``from_encoding`` informado não decodificar o arquivo.
        FileNotFoundError: se ``path`` não existir.
    """
    raw = path.read_bytes()
    has_bom = raw.startswith(UTF8_BOM)
    payload = raw[len(UTF8_BOM) :] if has_bom else raw

    src = from_encoding or detect_encoding(raw)[0]
    dst = to_encoding or expected_encoding_for(path)

    try:
        text = payload.decode(src)
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Falha ao decodificar {path.name} como {src}: {exc}. "
            f"Re-tente com --from explicito (cp1252 ou utf-8)."
        ) from exc

    # Em ADVPL CP1252, o BOM nao deve ser preservado. Em UTF-8 destino, omitimos
    # BOM (compatibilidade com tooling Linux/macOS e parser do plugin).
    out_bytes = text.encode(dst, errors="replace")

    backup_path: Path | None = None
    if backup:
        if timestamp:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            backup_path = path.with_suffix(path.suffix + f".bak.{ts}")
        else:
            backup_path = path.with_suffix(path.suffix + ".bak")
        if not backup_path.exists():
            backup_path.write_bytes(raw)

    path.write_bytes(out_bytes)
    return src, dst, backup_path
