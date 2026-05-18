"""Garante que docs/exec-contract.md e docs/examples/uexec.prw existem,
têm header MIT e mencionam o contrato canônico (v0.7.0 Fase 0 #7).
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs" / "exec-contract.md"
IMPL = REPO_ROOT / "docs" / "examples" / "uexec.prw"


def test_exec_contract_doc_exists() -> None:
    assert DOC.is_file(), f"esperava encontrar {DOC}"


def test_uexec_reference_impl_exists() -> None:
    assert IMPL.is_file(), f"esperava encontrar {IMPL}"


def test_uexec_reference_has_mit_header() -> None:
    text = IMPL.read_text(encoding="utf-8")
    assert "MIT License" in text, "uexec.prw deve declarar MIT License no header"


def test_exec_contract_mentions_post_uexec_route() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "POST /rest/uexec" in text
    assert "function" in text and "args" in text


def test_exec_contract_warns_production_use() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    # disclaimer canonico: menciona DEV + CI (evita match em "produção" com cedilha).
    assert "dev" in text and "ci" in text
    assert "anti-pattern" in text or "anti-padrao" in text or "aviso" in text


def test_uexec_uses_encode_utf8_and_decode_utf8() -> None:
    """Reference impl deve aplicar boundary de encoding nos dois lados."""
    text = IMPL.read_text(encoding="utf-8")
    assert "DecodeUtf8" in text
    assert "EncodeUtf8" in text


def test_uexec_validates_u_prefix() -> None:
    """Whitelist minima: rejeita funcao sem prefixo U_."""
    text = IMPL.read_text(encoding="utf-8")
    assert "U_" in text and "function" in text.lower()
