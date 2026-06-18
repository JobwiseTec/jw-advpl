"""Helpers do parser de SX CSV: detecção de campo custom + encoding determinístico."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.parsing import sx_csv
from plugadvpl.parsing.sx_csv import _detect_encoding, _is_custom_field


@pytest.mark.parametrize(
    "campo,esperado",
    [
        ("A1_XCUST", True),  # X — clássico
        ("A1_YBOLETO", True),  # Y — range de cliente
        ("A1_ZZPMAGI", True),  # Z — custom moderno (alinha com tabela Z*)
        ("ADL_ZNMVEN", True),  # Z em alias de 3 letras
        ("A1_COD", False),  # standard
        ("A1_NOME", False),  # standard
        ("A1_", False),  # 2ª parte vazia
        ("SEMUNDERSCORE", False),  # sem '_'
    ],
)
def test_is_custom_field_reconhece_x_y_z(campo: str, esperado: bool) -> None:
    # campo custom = 2ª parte começa com letra do range de cliente (X/Y/Z), análogo
    # ao detector de TABELA custom (Z*/SZ*/Q*). Antes só reconhecia 'X'.
    assert _is_custom_field(campo) is esperado


def test_detect_encoding_cp1252_deterministico_mesmo_com_chardet_errado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # chardet "mente" dizendo cp1250 (acontece em amostras curtas) — o detector deve
    # resolver cp1252 deterministicamente, sem confiar no chardet.
    monkeypatch.setattr(
        sx_csv.chardet, "detect", lambda _b: {"encoding": "cp1250", "confidence": 0.6}
    )
    f = tmp_path / "sx3.csv"
    f.write_bytes("Código,Descrição,Relação,Início\n".encode("cp1252"))
    assert _detect_encoding(f) == "cp1252"


def test_detect_encoding_utf8_estrito(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sx_csv.chardet, "detect", lambda _b: {"encoding": "cp1250", "confidence": 0.6}
    )
    f = tmp_path / "x.csv"
    f.write_bytes("Código,Função,Razão\n".encode())
    assert _detect_encoding(f) == "utf-8"


def test_detect_encoding_bom_utf8(tmp_path: Path) -> None:
    f = tmp_path / "x.csv"
    f.write_bytes(b"\xef\xbb\xbfCod,Desc\n")
    assert _detect_encoding(f) == "utf-8-sig"


def test_detect_encoding_ascii_reporta_cp1252(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ASCII é subset de cp1252 (canonical Protheus); não deve reportar 'ascii'.
    monkeypatch.setattr(
        sx_csv.chardet, "detect", lambda _b: {"encoding": "ascii", "confidence": 1.0}
    )
    f = tmp_path / "x.csv"
    f.write_bytes(b"COD,DESC,NOME\n")
    assert _detect_encoding(f) == "cp1252"
