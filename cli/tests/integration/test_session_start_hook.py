"""Integration tests para hooks/session-start.mjs (SessionStart hook do plugin).

Invoca o hook via node e valida output JSON. Usa skip quando node não estiver
disponível (CI roda node, mas dev local pode rodar pytest sem node instalado).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_PATH = REPO_ROOT / "hooks" / "session-start.mjs"


def _node_available() -> bool:
    return shutil.which("node") is not None


def _run_hook(project_dir: Path) -> dict:
    """Roda o hook com CLAUDE_PROJECT_DIR=project_dir e retorna output JSON (ou {})."""
    result = subprocess.run(  # noqa: S603 — testing internal hook with known args
        ["node", str(HOOK_PATH)],
        capture_output=True,
        text=True,
        timeout=10,
        env={
            "CLAUDE_PROJECT_DIR": str(project_dir),
            "PATH": os.environ.get("PATH", ""),
        },
        check=False,
    )
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


pytestmark = pytest.mark.skipif(
    not _node_available() or not HOOK_PATH.exists(),
    reason="node ou hook ausente — integração não aplicável",
)


class TestSessionStartHookAuxiliaryDirs:
    """Hook NÃO deve detectar fontes em pastas auxiliares (gaps, docs, tests, etc).

    Essas convenções de pasta indicam fixtures/documentação/exemplos, não um
    projeto Protheus real. Disparar o setup do plugin nesses casos é ruído.
    """

    def test_ignores_gaps_folder(self, tmp_path: Path) -> None:
        """gaps/ é pasta de trabalho local — não conta como projeto ADVPL."""
        (tmp_path / "gaps").mkdir()
        (tmp_path / "gaps" / "foo.prw").write_text("// fixture\n")
        output = _run_hook(tmp_path)
        assert output == {}, (
            f"hook deveria ser silent quando fontes estão só em gaps/, "
            f"mas emitiu: {output}"
        )

    def test_ignores_docs_folder(self, tmp_path: Path) -> None:
        """docs/ contém exemplos/reference impl, não código de produção."""
        (tmp_path / "docs" / "examples").mkdir(parents=True)
        (tmp_path / "docs" / "examples" / "demo.prw").write_text("// example\n")
        output = _run_hook(tmp_path)
        assert output == {}

    def test_ignores_tests_folder(self, tmp_path: Path) -> None:
        """tests/ contém fixtures de teste, não código de produção."""
        (tmp_path / "tests" / "fixtures").mkdir(parents=True)
        (tmp_path / "tests" / "fixtures" / "sample.prw").write_text("// fixture\n")
        output = _run_hook(tmp_path)
        assert output == {}


class TestSessionStartHookRealProject:
    """Hook DEVE detectar fontes em pastas comuns de projeto Protheus."""

    def test_detects_source_in_root(self, tmp_path: Path) -> None:
        """Fonte no root é projeto real — emite sugestão."""
        (tmp_path / "FATA050.prw").write_text("User Function FATA050()\nReturn\n")
        output = _run_hook(tmp_path)
        assert output != {}
        assert "Projeto ADVPL detectado" in output["hookSpecificOutput"]["additionalContext"]

    def test_detects_source_in_customizado(self, tmp_path: Path) -> None:
        """Pasta tipo `customizado/` é projeto Protheus padrão — emite sugestão."""
        (tmp_path / "customizado").mkdir()
        (tmp_path / "customizado" / "ABCFAT001.prw").write_text("// real source\n")
        output = _run_hook(tmp_path)
        assert output != {}
        assert "Projeto ADVPL detectado" in output["hookSpecificOutput"]["additionalContext"]
