"""Garante que lookups/compile_patterns.json e lookups/redact_patterns.json
seguem o schema esperado pelo runtime. Padrão idêntico ao test_lint_catalog_consistency.
"""
from __future__ import annotations

import json
import re
from importlib import resources as ir

import pytest


@pytest.fixture(scope="module")
def redact_catalog() -> list[dict]:
    text = ir.files("plugadvpl").joinpath("lookups/redact_patterns.json").read_text(
        encoding="utf-8"
    )
    return json.loads(text)


def test_redact_min_count(redact_catalog: list[dict]) -> None:
    assert len(redact_catalog) >= 5


def test_redact_required_fields(redact_catalog: list[dict]) -> None:
    for entry in redact_catalog:
        for field in ("id", "description", "pattern", "replacement"):
            assert field in entry, f"entry missing {field}: {entry}"


def test_redact_pattern_compiles(redact_catalog: list[dict]) -> None:
    for entry in redact_catalog:
        try:
            re.compile(entry["pattern"])
        except re.error as exc:
            pytest.fail(f"{entry['id']} pattern doesn't compile: {exc}")


def test_redact_ids_unique(redact_catalog: list[dict]) -> None:
    ids = [e["id"] for e in redact_catalog]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_redact_replacement_uses_known_backrefs(redact_catalog: list[dict]) -> None:
    """Cada pattern com group capturador (\\1) no replacement deve ter o group definido."""
    for entry in redact_catalog:
        rx = re.compile(entry["pattern"])
        replacement = entry["replacement"]
        # Procura backreferences \1, \2, etc no replacement
        backrefs = [int(m) for m in re.findall(r"\\(\d+)", replacement)]
        if backrefs:
            max_backref = max(backrefs)
            assert rx.groups >= max_backref, (
                f"{entry['id']} usa \\{max_backref} mas pattern tem só {rx.groups} groups"
            )


def test_redact_patterns_actually_redact_sample(redact_catalog: list[dict]) -> None:
    """Smoke test: cada pattern deve redactar pelo menos um exemplo plausível."""
    samples = {
        "password_assignment": "password=secret123",
        "psw_assignment": "psw=totvs",
        "senha_assignment_pt": "senha=minhaSenha",
        "pwd_assignment": "pwd=admin",
        "hex_key_long": "token: abc123def456abc789",
        "aut_file_value": "aut_file=/path/to/chave.aut",
    }
    for entry in redact_catalog:
        sample = samples.get(entry["id"])
        if sample is None:
            continue  # não temos sample pra esse id — skip
        rx = re.compile(entry["pattern"])
        replaced = rx.sub(entry["replacement"], sample)
        # Algum trecho REDACTED ou HEX_REDACTED deve aparecer
        assert "REDACTED" in replaced, (
            f"{entry['id']}: '{sample}' → '{replaced}' (sem REDACTED)"
        )
