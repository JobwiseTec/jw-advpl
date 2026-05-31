"""Testes de plugadvpl.edit_prw — detecção e conversão CP1252 ↔ UTF-8."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.edit_prw import (
    UTF8_BOM,
    check_encoding,
    convert_and_save,
    detect_encoding,
    expected_encoding_for,
    read_as_utf8,
)


# --- expected_encoding_for --------------------------------------------------


class TestExpectedEncodingFor:
    def test_prw_is_cp1252(self) -> None:
        assert expected_encoding_for(Path("foo.prw")) == "cp1252"

    def test_prx_is_cp1252(self) -> None:
        assert expected_encoding_for(Path("foo.prx")) == "cp1252"

    def test_tlpp_is_utf8(self) -> None:
        assert expected_encoding_for(Path("foo.tlpp")) == "utf-8"

    def test_tlpp_ch_is_utf8(self) -> None:
        assert expected_encoding_for(Path("foo.tlpp.ch")) == "utf-8"

    def test_ch_is_utf8(self) -> None:
        assert expected_encoding_for(Path("foo.ch")) == "utf-8"

    def test_unknown_defaults_cp1252(self) -> None:
        assert expected_encoding_for(Path("foo.xyz")) == "cp1252"


# --- detect_encoding --------------------------------------------------------


class TestDetectEncoding:
    def test_bom_is_utf8(self) -> None:
        enc, has_bom, non_ascii = detect_encoding(UTF8_BOM + b"abc")
        assert enc == "utf-8"
        assert has_bom is True
        assert non_ascii == 0

    def test_ascii_only_is_cp1252(self) -> None:
        enc, has_bom, non_ascii = detect_encoding(b"User Function Foo()\nReturn\n")
        assert enc == "cp1252"
        assert has_bom is False
        assert non_ascii == 0

    def test_utf8_multibyte_no_bom(self) -> None:
        # 'á' em UTF-8 = 0xC3 0xA1, 'ç' = 0xC3 0xA7
        raw = "Função com Ação".encode("utf-8")
        enc, has_bom, non_ascii = detect_encoding(raw)
        assert enc == "utf-8"
        assert has_bom is False
        assert non_ascii > 0

    def test_cp1252_multibyte_no_bom(self) -> None:
        # 'á' em CP1252 = 0xE1 (single byte) — não decoda como UTF-8
        raw = "Função com Ação".encode("cp1252")
        enc, has_bom, non_ascii = detect_encoding(raw)
        assert enc == "cp1252"
        assert has_bom is False
        assert non_ascii > 0

    def test_invalid_utf8_falls_back_to_cp1252(self) -> None:
        # 0xE1 (CP1252 á) sozinho não forma sequência UTF-8 válida
        raw = b"abc\xe1def"
        enc, _, _ = detect_encoding(raw)
        assert enc == "cp1252"


# --- check_encoding ---------------------------------------------------------


class TestCheckEncoding:
    def test_prw_cp1252_matches(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("User Function Foo()\nReturn\n".encode("cp1252"))
        report = check_encoding(fp)
        assert report.expected_encoding == "cp1252"
        assert report.detected_encoding == "cp1252"
        assert report.match is True

    def test_prw_utf8_mismatch(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função()".encode("utf-8"))
        report = check_encoding(fp)
        assert report.expected_encoding == "cp1252"
        assert report.detected_encoding == "utf-8"
        assert report.match is False
        assert report.non_ascii_bytes > 0

    def test_tlpp_utf8_matches(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.tlpp"
        fp.write_bytes("Função()".encode("utf-8"))
        report = check_encoding(fp)
        assert report.match is True

    def test_to_dict_has_required_keys(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes(b"abc")
        report = check_encoding(fp)
        d = report.to_dict()
        for key in (
            "file", "extension", "expected_encoding", "detected_encoding",
            "has_bom", "match", "non_ascii_bytes",
        ):
            assert key in d


# --- read_as_utf8 -----------------------------------------------------------


class TestReadAsUtf8:
    def test_reads_cp1252_as_utf8_logical(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("cp1252"))
        assert read_as_utf8(fp) == "Função"

    def test_reads_utf8_with_bom(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes(UTF8_BOM + "Função".encode("utf-8"))
        assert read_as_utf8(fp) == "Função"


# --- convert_and_save -------------------------------------------------------


class TestConvertAndSave:
    def test_utf8_to_cp1252_creates_backup(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.prw"
        original = "Função()".encode("utf-8")
        fp.write_bytes(original)
        src, dst, bak = convert_and_save(fp)
        assert src == "utf-8"
        assert dst == "cp1252"
        assert bak is not None and bak.exists()
        assert bak.read_bytes() == original
        assert fp.read_bytes() == "Função()".encode("cp1252")

    def test_cp1252_to_utf8_explicit(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.tlpp"
        fp.write_bytes("Função".encode("cp1252"))
        src, dst, _ = convert_and_save(fp)
        assert src == "cp1252"
        assert dst == "utf-8"
        assert fp.read_bytes() == "Função".encode("utf-8")

    def test_no_backup_flag(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("utf-8"))
        _, _, bak = convert_and_save(fp, backup=False)
        assert bak is None
        assert not (tmp_path / "foo.prw.bak").exists()

    def test_explicit_from_and_to(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("abc".encode("cp1252"))
        src, dst, _ = convert_and_save(
            fp, from_encoding="cp1252", to_encoding="utf-8", backup=False,
        )
        assert (src, dst) == ("cp1252", "utf-8")

    def test_wrong_from_encoding_raises(self, tmp_path: Path) -> None:
        fp = tmp_path / "foo.prw"
        # bytes 0xFF nao decodifica como utf-8 strict
        fp.write_bytes(b"\xff\xfe\xfd")
        with pytest.raises(ValueError, match="Falha ao decodificar"):
            convert_and_save(fp, from_encoding="utf-8", backup=False)

    def test_timestamp_creates_bak_with_timestamp_suffix(
        self, tmp_path: Path
    ) -> None:
        """v0.18.0+: timestamp=True gera .bak.<YYYYMMDDHHMMSS>."""
        import re
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("utf-8"))
        _, _, bak = convert_and_save(fp, backup=True, timestamp=True)
        assert bak is not None
        assert re.search(r"\.bak\.\d{14}$", bak.name), (
            f"esperado .bak.<14 digits>, vi {bak.name}"
        )
        assert bak.exists()

    def test_timestamp_preserves_legacy_bak(self, tmp_path: Path) -> None:
        """v0.18.0+: timestamp=True NÃO sobrescreve .bak legado existente."""
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("utf-8"))
        # Cria .bak legado com conteúdo conhecido
        legacy = tmp_path / "foo.prw.bak"
        legacy.write_bytes(b"LEGACY-CONTENT")
        # Roda convert com timestamp
        _, _, bak = convert_and_save(fp, backup=True, timestamp=True)
        # Legacy preservado
        assert legacy.exists()
        assert legacy.read_bytes() == b"LEGACY-CONTENT"
        # bak retornado é .bak.<ts>, não o legado
        assert bak is not None
        assert bak != legacy

    def test_timestamp_false_keeps_legacy_behavior(self, tmp_path: Path) -> None:
        """v0.18.0+: default timestamp=False mantém .bak fixo (compat)."""
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("utf-8"))
        _, _, bak = convert_and_save(fp, backup=True)
        assert bak is not None
        assert bak.name == "foo.prw.bak"


# --- encode_cp1252_bytes ----------------------------------------------------


class TestEncodeBytes:
    def test_encodes_accented_chars_to_cp1252(self) -> None:
        from plugadvpl.edit_prw import encode_cp1252_bytes
        assert encode_cp1252_bytes("Função") == "Função".encode("cp1252")

    def test_replaces_non_encodable_chars(self) -> None:
        from plugadvpl.edit_prw import encode_cp1252_bytes
        # caractere 你 não existe em CP1252 → vira ?
        out = encode_cp1252_bytes("你")
        assert out == b"?"
