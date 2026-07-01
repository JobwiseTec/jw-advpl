"""Testes do parser DODA nativo (zero-FairCom).

Constrói blocos DODA sintéticos em memória — com o mesmo layout binário dos
arquivos reais do Protheus — e valida que ``parse_doda_native`` reconstrói o
Layout (offsets calculados por alinhamento, tipos e tamanhos) sem depender do
FairCom instalado.
"""

from __future__ import annotations

import struct
from pathlib import Path

from plugadvpl.dtc import faircom

# Códigos de tipo c-tree (ctport.h) usados nos arquivos reais do Protheus.
FSTRING = 144
INT4U = 59
INT2 = 33
CHAR = 16


def _build_doda(fields: list[tuple[str, int, int]], gap: int = 0) -> bytes:
    """Monta um bloco DODA: cabeçalho (N,N) + array (len,type) + pool de nomes.

    ``fields`` = lista de ``(nome, tamanho, codigo_de_tipo)`` na ordem do registro.
    """
    n = len(fields)
    header = struct.pack("<II", n, n)
    arr = b"".join(struct.pack("<HH", length, code) for _, length, code in fields)
    pool = b""
    for name, _, _ in fields:
        nb = name.encode("cp1252")
        pool += bytes([len(nb) + 2]) + nb + b"\x00"
    # `gap`: bytes entre o array e o pool — algumas versões do APSDU não "colam"
    # o pool no array (ex.: Protheus/Postgres). O locator deve tolerar isso.
    return header + arr + b"\x00" * gap + pool


def _write(tmp_path: Path, doda: bytes, prefix: bytes = b"\x00" * 32) -> Path:
    """Grava um .dtc sintético: lixo de header + DODA (+ folga no fim)."""
    arquivo = tmp_path / "synthetic.dtc"
    arquivo.write_bytes(prefix + doda + b"\x00" * 16)
    return arquivo


class TestTypeHelpers:
    def test_ctype_name_known_codes(self) -> None:
        assert faircom._ctype_name(FSTRING) == "FSTRING"
        assert faircom._ctype_name(INT4U) == "INT4U"
        assert faircom._ctype_name(INT2) == "INT2"
        assert faircom._ctype_name(CHAR) == "CHAR"

    def test_ctype_name_unknown_falls_back(self) -> None:
        assert faircom._ctype_name(999) == "CT999"

    def test_field_align_scalars(self) -> None:
        assert faircom._field_align(INT2) == 2  # 33 & 7 = 1 -> 2
        assert faircom._field_align(INT4U) == 4  # 59 & 7 = 3 -> 4
        assert faircom._field_align(103) == 8  # DFLOAT, 103 & 7 = 7 -> 8

    def test_field_align_text_is_one(self) -> None:
        assert faircom._field_align(FSTRING) == 1  # família de texto
        assert faircom._field_align(CHAR) == 1
        assert faircom._field_align(146) == 1  # STRING (variável) também 1


DFLOAT = 103  # CT_DFLOAT — campos numéricos do Protheus (double 8 bytes)


class TestCrossVersionVariants:
    """Layouts diferem entre versões/bancos do Protheus (Oracle, Postgres, ...).

    O locator precisa achar o DODA mesmo quando o pool de nomes não "cola" no
    array (gap), e tratar campos DFLOAT (numéricos).
    """

    def test_handles_gap_between_array_and_pool(self, tmp_path: Path) -> None:
        # variante estilo APSDU/Postgres: há bytes entre o array e o pool
        doda = _build_doda(
            [
                ("D_E_L_E_T_E_D", 1, FSTRING),
                ("R_E_C_N_O", 4, INT4U),
                ("E5_VALOR", 8, DFLOAT),
            ],
            gap=4,
        )
        layout = faircom.parse_doda_native(_write(tmp_path, doda))
        assert layout is not None and layout.is_protheus
        assert [f.name for f in layout.fields] == ["D_E_L_E_T_E_D", "R_E_C_N_O", "E5_VALOR"]
        # offsets com alinhamento: delete@0, recno@4 (INT4U), valor@8 (DFLOAT align 8)
        assert [f.offset for f in layout.fields] == [0, 4, 8]
        assert layout.fields[2].ctype == "DFLOAT"
        assert layout.record_length == 16

    def test_dfloat_value_roundtrips(self, tmp_path: Path) -> None:
        from plugadvpl.dtc import parser

        doda = _build_doda(
            [
                ("D_E_L_E_T_E_D", 1, FSTRING),
                ("R_E_C_N_O", 4, INT4U),
                ("E5_VALOR", 8, DFLOAT),
            ]
        )
        layout = faircom.parse_doda_native(_write(tmp_path, doda))
        reclen = layout.record_length

        def rec(valor: float) -> bytes:
            b = bytearray(reclen)
            b[0:1] = b" "
            b[4:8] = struct.pack("<I", 1)
            b[8:16] = struct.pack("<d", valor)
            return bytes(b)

        cols, rows = parser.read_fixed(b"\xff" * reclen + rec(1234.56), layout)
        assert cols[2] == "E5_VALOR"
        assert rows[0][2] == 1234.56


class TestParseDodaNative:
    def test_parses_protheus_layout(self, tmp_path: Path) -> None:
        doda = _build_doda(
            [
                ("D_E_L_E_T_E_D", 1, FSTRING),
                ("R_E_C_N_O", 4, INT4U),
                ("X3_CAMPO", 10, FSTRING),
                ("X3_TAMANHO", 2, INT2),
            ]
        )
        layout = faircom.parse_doda_native(_write(tmp_path, doda))

        assert layout is not None
        assert layout.is_protheus
        assert [f.name for f in layout.fields] == [
            "D_E_L_E_T_E_D",
            "R_E_C_N_O",
            "X3_CAMPO",
            "X3_TAMANHO",
        ]
        assert [f.ctype for f in layout.fields] == ["FSTRING", "INT4U", "FSTRING", "INT2"]
        assert [f.length for f in layout.fields] == [1, 4, 10, 2]

    def test_alignment_inserts_padding(self, tmp_path: Path) -> None:
        # D_E_L_E_T_E_D (len 1) deixa 3 bytes de padding antes do INT4U alinhado a 4.
        doda = _build_doda(
            [
                ("D_E_L_E_T_E_D", 1, FSTRING),
                ("R_E_C_N_O", 4, INT4U),
                ("X3_CAMPO", 10, FSTRING),
                ("X3_TAMANHO", 2, INT2),
            ]
        )
        layout = faircom.parse_doda_native(_write(tmp_path, doda))

        assert [f.offset for f in layout.fields] == [0, 4, 8, 18]
        assert layout.record_length == 20

    def test_none_without_delete_anchor(self, tmp_path: Path) -> None:
        doda = _build_doda([("R_E_C_N_O", 4, INT4U), ("CAMPO", 10, FSTRING)])
        assert faircom.parse_doda_native(_write(tmp_path, doda)) is None

    def test_none_when_delete_not_at_offset_zero(self, tmp_path: Path) -> None:
        # delete existe, mas não no offset 0 → não é assinatura Protheus.
        doda = _build_doda(
            [
                ("R_E_C_N_O", 4, INT4U),
                ("D_E_L_E_T_E_D", 1, FSTRING),
            ]
        )
        assert faircom.parse_doda_native(_write(tmp_path, doda)) is None

    def test_roundtrip_reads_records(self, tmp_path: Path) -> None:
        from plugadvpl.dtc import parser

        doda = _build_doda(
            [
                ("D_E_L_E_T_E_D", 1, FSTRING),
                ("R_E_C_N_O", 4, INT4U),
                ("NOME", 8, FSTRING),
            ]
        )
        layout = faircom.parse_doda_native(_write(tmp_path, doda))
        assert layout is not None
        reclen = layout.record_length

        def full_rec(flag: bytes, recno: int, nome: bytes) -> bytes:
            b = bytearray(reclen)
            b[0:1] = flag
            b[4:8] = struct.pack("<I", recno)
            b[8 : 8 + 8] = nome.ljust(8)[:8]
            return bytes(b)

        data = b"\xff" * reclen + full_rec(b" ", 1, b"Joao") + full_rec(b"*", 2, b"Maria")
        cols, rows = parser.read_fixed(data, layout, keep_deleted=False)
        assert cols == ["D_E_L_E_T_E_D", "R_E_C_N_O", "NOME"]
        assert [r[1] for r in rows] == [1]
        assert [r[2] for r in rows] == ["Joao"]


class TestExtractLayoutPrefersNative:
    def test_native_path_skips_ctinfo(self, tmp_path: Path, mocker) -> None:
        doda = _build_doda(
            [
                ("D_E_L_E_T_E_D", 1, FSTRING),
                ("R_E_C_N_O", 4, INT4U),
            ]
        )
        arquivo = _write(tmp_path, doda)
        # se o nativo resolver, o ctinfo nem deve ser chamado
        boom = mocker.patch(
            "plugadvpl.dtc.faircom._extract_layout_ctinfo",
            side_effect=AssertionError("ctinfo não deveria ser usado"),
        )
        layout = faircom.extract_layout(arquivo)
        assert layout is not None and layout.is_protheus
        boom.assert_not_called()

    def test_falls_back_to_ctinfo_when_native_fails(self, tmp_path: Path, mocker) -> None:
        arquivo = tmp_path / "nao_protheus.dtc"
        arquivo.write_bytes(b"\x00" * 64)  # sem DODA Protheus
        sentinel = object()
        ctinfo = mocker.patch("plugadvpl.dtc.faircom._extract_layout_ctinfo", return_value=sentinel)
        assert faircom.extract_layout(arquivo) is sentinel
        ctinfo.assert_called_once()
