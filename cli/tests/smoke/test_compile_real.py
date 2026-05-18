"""Smoke tests — só rodam se PLUGADVPL_SMOKE=1. Requerem advpls real.

Critério de aprovação (spec §11.5):
- Cobrir >=3 famílias de erro distintas
- >=1 fixture pt-BR + >=1 en
- Todas sanitizadas (sem credencial / cliente / empresa)
- Smoke local Windows + VPS via SSH tunnel ambos passam

Loop iterativo: cada output real coletado vira fixture sanitizada em
tests/fixtures/compile_outputs/ + teste unit do parser. Reforça
compile_patterns.json a cada bug encontrado em uso real.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

SKIP_REASON = "smoke tests skipped — set PLUGADVPL_SMOKE=1 to run"
pytestmark = pytest.mark.skipif(
    os.environ.get("PLUGADVPL_SMOKE") != "1", reason=SKIP_REASON
)


@pytest.mark.smoke
def test_compile_appre_clean_source(tmp_path: Path) -> None:
    """Verifica que compile appre num fonte limpo retorna exit 0."""
    foo = tmp_path / "FOO_CLEAN.prw"
    foo.write_text(
        "User Function FooClean()\n"
        "Return .T.\n",
        encoding="cp1252",
    )
    from plugadvpl.compile import CompileRequest, run
    request = CompileRequest(
        files=[foo], mode="appre", no_warnings=False,
        timeout_seconds=30, no_security_warning=True,
        includes_override=None, changed_since=None,
    )
    result = run(request, runtime_cfg=None, root=tmp_path)
    assert result.exit_code == 0, f"output: {result.rows}"


@pytest.mark.smoke
def test_compile_appre_with_syntax_error(tmp_path: Path) -> None:
    """Verifica que compile appre num fonte com erro de sintaxe retorna >=1 error."""
    foo = tmp_path / "FOO_BROKEN.prw"
    foo.write_text(
        "User Function FooBroken()\n"
        "  If .T.\n"  # ENDIF faltando
        "Return\n",
        encoding="cp1252",
    )
    from plugadvpl.compile import CompileRequest, run
    request = CompileRequest(
        files=[foo], mode="appre", no_warnings=False,
        timeout_seconds=30, no_security_warning=True,
        includes_override=None, changed_since=None,
    )
    result = run(request, runtime_cfg=None, root=tmp_path)
    assert result.exit_code == 1
    assert result.summary["total_errors"] >= 1
