"""Parser direto de arquivos ISAM fixed-length, guiado pelo DODA.

Caminho PRINCIPAL de leitura do dtcat: lê os registros diretamente do layout
físico (offsets/tipos/tamanhos extraídos pelo ctinfo), sem precisar do servidor
SQL nem do índice c-tree. Cobre o caso real mais comum — arquivos exportados de
aplicativos c-tree (ex.: rotinas tipo APSDU), que vêm como dados puros, sem o
índice (cujo caminho no IFIL aponta para o servidor de origem).
"""

from __future__ import annotations

import struct

from plugadvpl.dtc.faircom import Layout

# Tipos c-tree tratados como texto (decodificados em cp1252). Inclui as variantes
# de string fixa/variável que o Protheus pode gerar conforme a versão/tabela
# (ex.: 4STRING em campos memo). Campos memo costumam ter tamanho 0 no registro
# fixo (conteúdo fica fora dele).
_TEXT_TYPES = {
    "FSTRING", "STRING", "PSTRING", "FPSTRING", "2STRING", "F2STRING",
    "4STRING", "F4STRING", "VARYING",
}  # fmt: skip
# Tipos c-tree de ponto flutuante (IEEE). DFLOAT (8 bytes) é o tipo dos campos
# numéricos do Protheus; SFLOAT (4 bytes) o de precisão simples.
_FLOAT_TYPES = {"FLOAT", "IEEEDBL", "DOUBLE", "MONEY", "DFLOAT", "SFLOAT", "EFLOAT"}


def decode_value(raw: bytes, ctype: str):
    """Decodifica uma célula bruta conforme o tipo c-tree do DODA."""
    t = ctype.upper()
    if t in _TEXT_TYPES:
        return raw.decode("cp1252", "replace").rstrip()
    if t in _FLOAT_TYPES:
        if len(raw) == 8:
            return struct.unpack("<d", raw)[0]
        if len(raw) == 4:
            return struct.unpack("<f", raw)[0]
        return raw.decode("cp1252", "replace").rstrip()
    if t.startswith("INT") or t in ("CHAR", "UCHAR"):
        signed = not (t.endswith("U") or t == "UCHAR")
        return int.from_bytes(raw, "little", signed=signed)
    # tipo não mapeado → texto, sem perder o dado
    return raw.decode("cp1252", "replace").rstrip()


def _recno_field(layout: Layout):
    for f in layout.fields:
        if f.name.replace("_", "").upper() == "RECNO":
            return f
    return None


def record_frame(data: bytes, layout: Layout) -> tuple[int, int]:
    """Descobre o início dos dados e o tamanho FÍSICO do registro.

    O tamanho do registro no arquivo pode ser maior que a soma dos campos do
    DODA (padding por registro) e o início dos dados pode não ser múltiplo dele
    — isso varia entre versões/bancos do Protheus. Para ser robusto, deduz os
    dois pela sequência de ``R_E_C_N_O`` (1, 2, 3, …): acha o registro de
    ``R_E_C_N_O == 1`` e mede o passo até ``R_E_C_N_O == 2``.

    Cai para ``(0, record_length do DODA)`` quando não há R_E_C_N_O/delete ou só
    há um registro sem como medir o passo.
    """
    guess = layout.record_length
    delf = layout.delete_field
    recf = _recno_field(layout)
    if guess <= 0 or delf is None or recf is None:
        return 0, max(guess, 1)

    do, ro, rl = delf.offset, recf.offset, recf.length

    def flag_ok(s: int) -> bool:
        return s + do < len(data) and data[s + do : s + do + 1] in (b" ", b"*")

    def recno(s: int) -> int | None:
        if s + ro + rl > len(data):
            return None
        try:
            return int(decode_value(data[s + ro : s + ro + rl], recf.ctype))
        except (ValueError, TypeError):
            return None

    limit = len(data) - guess
    first_single: int | None = None
    s = 0
    while s <= limit:
        if flag_ok(s) and recno(s) == 1:
            hi = min(s + guess * 4, len(data) - rl)
            s2 = s + guess  # reclen físico >= soma dos campos
            while s2 <= hi:
                if flag_ok(s2) and recno(s2) == 2:
                    return s, s2 - s
                s2 += 1
            if first_single is None:
                first_single = s
        s += 1
    if first_single is not None:
        return first_single, guess
    return 0, guess


def read_fixed(
    data: bytes, layout: Layout, keep_deleted: bool = False
) -> tuple[list[str], list[tuple]]:
    """Lê todos os registros de um buffer fixed-length conforme o ``layout``.

    Enquadra os registros via :func:`record_frame` (início e tamanho físico
    deduzidos da sequência de R_E_C_N_O) e descarta slots livres/lixo pelo byte
    de soft-delete (válido só quando é espaço ``' '`` ou asterisco ``'*'``).
    """
    fields = layout.fields
    cols = [f.name for f in fields]
    delf = layout.delete_field
    data_start, reclen = record_frame(data, layout)

    rows: list[tuple] = []
    off = data_start
    n = len(data)
    while off + reclen <= n:
        rec = data[off : off + reclen]
        if delf is not None:
            flag = rec[delf.offset : delf.offset + 1]
            if flag not in (b" ", b"*"):
                off += reclen
                continue  # slot livre / lixo
            if not keep_deleted and flag == b"*":
                off += reclen
                continue  # registro logicamente excluído
        rows.append(
            tuple(decode_value(rec[f.offset : f.offset + f.length], f.ctype) for f in fields)
        )
        off += reclen
    return cols, rows
