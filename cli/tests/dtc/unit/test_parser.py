"""Testes do parser DODA direto (fixed-length)."""

from __future__ import annotations

import struct

from plugadvpl.dtc import parser
from plugadvpl.dtc.faircom import FieldDef, Layout


def _frame_layout() -> Layout:
    # soma do DODA = 18 (delete@0, recno@4, nome@8 len10)
    return Layout(
        record_length=18,
        is_fixed=True,
        fields=[
            FieldDef("D_E_L_E_T_E_D", 0, 1, "FSTRING"),
            FieldDef("R_E_C_N_O", 4, 4, "INT4U"),
            FieldDef("NOME", 8, 10, "FSTRING"),
        ],
    )


class TestRecordFrame:
    """Enquadramento físico via R_E_C_N_O — reclen pode ser > soma do DODA e o
    início dos dados pode não ser múltiplo do reclen (caso SQL Server)."""

    def _rec(self, reclen: int, recno: int, nome: bytes) -> bytes:
        b = bytearray(reclen)  # reclen FÍSICO (com padding além dos campos)
        b[0:1] = b" "
        b[4:8] = struct.pack("<I", recno)
        b[8:18] = nome.ljust(10)[:10]
        return bytes(b)

    def test_detects_padded_reclen_and_unaligned_start(self) -> None:
        layout = _frame_layout()
        phys = 24  # 18 de campos + 6 de padding por registro
        prefix = b"\xff" * 10  # data_start = 10 (não múltiplo de 24)
        data = prefix + b"".join(
            self._rec(phys, i, n) for i, n in [(1, b"A"), (2, b"B"), (3, b"C")]
        )

        data_start, reclen = parser.record_frame(data, layout)
        assert (data_start, reclen) == (10, 24)

        _cols, rows = parser.read_fixed(data, layout)
        assert [r[1] for r in rows] == [1, 2, 3]
        assert [r[2] for r in rows] == ["A", "B", "C"]

    def test_falls_back_to_doda_sum_without_recno(self) -> None:
        layout = Layout(
            record_length=8,
            is_fixed=True,
            fields=[FieldDef("D_E_L_E_T_E_D", 0, 1, "FSTRING"), FieldDef("X", 1, 4, "INT4U")],
        )
        # sem R_E_C_N_O → enquadra do offset 0 com a soma do DODA
        data_start, reclen = parser.record_frame(b"\x00" * 32, layout)
        assert (data_start, reclen) == (0, 8)


class TestDecodeValue:
    def test_fstring_decodes_cp1252_and_rstrips(self) -> None:
        assert parser.decode_value(b"Regi\xe3o   ", "FSTRING") == "Região"

    def test_int4u(self) -> None:
        assert parser.decode_value(struct.pack("<I", 4242), "INT4U") == 4242

    def test_int2_signed(self) -> None:
        assert parser.decode_value(struct.pack("<h", -7), "INT2") == -7

    def test_char_is_small_int(self) -> None:
        assert parser.decode_value(b"\x05", "CHAR") == 5

    def test_double(self) -> None:
        assert parser.decode_value(struct.pack("<d", 3.5), "DOUBLE") == 3.5

    def test_unknown_type_falls_back_to_text(self) -> None:
        assert parser.decode_value(b"abc ", "WEIRDTYPE") == "abc"


def _layout(reclen: int, fields: list[FieldDef]) -> Layout:
    return Layout(record_length=reclen, is_fixed=True, fields=fields)


class TestReadFixed:
    def _sample(self):
        # reclen=16: [0]=delete flag, [4:8]=recno int4u, [8:16]=nome fstring
        fields = [
            FieldDef("D_E_L_E_T_E_D", 0, 1, "FSTRING"),
            FieldDef("R_E_C_N_O", 4, 4, "INT4U"),
            FieldDef("NOME", 8, 8, "FSTRING"),
        ]
        layout = _layout(16, fields)

        def rec(flag: bytes, recno: int, nome: bytes) -> bytes:
            buf = bytearray(16)
            buf[0:1] = flag
            buf[4:8] = struct.pack("<I", recno)
            buf[8:16] = nome.ljust(8)[:8]
            return bytes(buf)

        header = b"\xff" * 16  # slot de header/livre → ignorado
        r1 = rec(b" ", 1, b"Joao")
        r2 = rec(b"*", 2, b"Maria")  # deletado
        r3 = rec(b" ", 3, b"Ana")
        return layout, header + r1 + r2 + r3

    def test_filters_deleted_by_default(self) -> None:
        layout, data = self._sample()
        cols, rows = parser.read_fixed(data, layout)
        assert cols == ["D_E_L_E_T_E_D", "R_E_C_N_O", "NOME"]
        assert [r[2] for r in rows] == ["Joao", "Ana"]  # Maria (deletada) fora
        assert [r[1] for r in rows] == [1, 3]

    def test_keep_deleted_includes_all(self) -> None:
        layout, data = self._sample()
        _, rows = parser.read_fixed(data, layout, keep_deleted=True)
        assert [r[2] for r in rows] == ["Joao", "Maria", "Ana"]

    def test_header_slot_is_skipped(self) -> None:
        layout, data = self._sample()
        _, rows = parser.read_fixed(data, layout, keep_deleted=True)
        assert len(rows) == 3  # header (0xff) descartado
