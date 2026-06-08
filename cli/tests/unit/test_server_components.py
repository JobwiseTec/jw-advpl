"""Unit tests p/ plugadvpl/server_components.py (extração do coletadb.tlpp)."""

from __future__ import annotations

from pathlib import Path

from plugadvpl import server_components as sc


def _source_bytes() -> bytes:
    return sc._coletadb_bytes()


def test_version_parses_from_define() -> None:
    data = b'... #DEFINE CDB_VERSION      "1.2.0"\n...'
    assert sc.coletadb_version(data) == "1.2.0"


def test_version_none_when_absent() -> None:
    assert sc.coletadb_version(b"sem define aqui") is None


def test_bundled_source_is_lf_ascii() -> None:
    data = _source_bytes()
    assert data.count(b"\r") == 0, "coletadb.tlpp deve ser LF (sem CR)"
    assert all(b <= 0x7F for b in data), "coletadb.tlpp deve ser ASCII puro"
    assert sc.coletadb_version(data) is not None


def test_extract_writes_byte_identical(tmp_path: Path) -> None:
    result = sc.extract_coletadb(tmp_path)
    assert result.status == "written"
    written = (tmp_path / "coletadb.tlpp").read_bytes()
    assert written == _source_bytes()  # byte-idêntico (NÃO comparar EOL specifico)


def test_extract_unchanged_second_run(tmp_path: Path) -> None:
    sc.extract_coletadb(tmp_path)
    result = sc.extract_coletadb(tmp_path)
    assert result.status == "unchanged"


def test_extract_version_mismatch_keeps_existing(tmp_path: Path) -> None:
    target = tmp_path / "coletadb.tlpp"
    target.write_bytes(b'#DEFINE CDB_VERSION "0.9.9"\n// versao velha do cliente')
    result = sc.extract_coletadb(tmp_path, force=False)
    assert result.status == "version_mismatch"
    assert result.version_existing == "0.9.9"
    assert target.read_bytes().startswith(b'#DEFINE CDB_VERSION "0.9.9"')  # intacto


def test_extract_force_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "coletadb.tlpp"
    target.write_bytes(b'#DEFINE CDB_VERSION "0.9.9"\n')
    result = sc.extract_coletadb(tmp_path, force=True)
    assert result.status == "written"
    assert target.read_bytes() == _source_bytes()


def test_extract_creates_dest_dir(tmp_path: Path) -> None:
    dest = tmp_path / "novo" / "sub"
    result = sc.extract_coletadb(dest)
    assert result.status == "written"
    assert (dest / "coletadb.tlpp").exists()
