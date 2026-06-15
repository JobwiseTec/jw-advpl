"""Integration tests para hooks/stop-verify.mjs (Stop hook — Fase 3 roadmap-ia).

Invoca o hook via node com um evento Stop no stdin e valida a decisão
(block/allow). Usa stub via PLUGADVPL_VERIFY_CMD para não depender do CLI/índice
reais. Skip quando node ausente.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_PATH = REPO_ROOT / "hooks" / "stop-verify.mjs"


def _node_available() -> bool:
    return shutil.which("node") is not None


pytestmark = pytest.mark.skipif(
    not _node_available() or not HOOK_PATH.exists(),
    reason="node ou hook ausente",
)


def _run(stdin_obj: dict, env_extra: dict | None = None) -> dict:
    env = {**os.environ}
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(  # noqa: S603 — hook interno, args conhecidos
        ["node", str(HOOK_PATH)],
        input=json.dumps(stdin_obj),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )
    out = result.stdout.strip()
    return json.loads(out) if out else {}


def _stub_verify(results: list[dict]) -> str:
    """PLUGADVPL_VERIFY_CMD que devolve um verdict canônico via `node -e`."""
    verdict_text = json.dumps({"results": results})
    script = "process.stdout.write(" + json.dumps(verdict_text) + ")"
    return json.dumps(["node", "-e", script])


def _transcript_with(text: str, tmp_path: Path) -> Path:
    line = {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": text}]}}
    p = tmp_path / "transcript.jsonl"
    p.write_text(json.dumps(line) + "\n", encoding="utf-8")
    return p


_CLAIMS = '<plugadvpl-claims>{"claims":[{"id":"c1","kind":"function","symbol":"FWLerExcel"}]}</plugadvpl-claims>'


def test_loop_guard_allows(tmp_path: Path) -> None:
    assert _run({"stop_hook_active": True, "transcript_path": "x"}) == {}


def test_no_claims_allows(tmp_path: Path) -> None:
    t = _transcript_with("Resposta conceitual sem simbolos.", tmp_path)
    assert _run({"transcript_path": str(t)}) == {}


def test_blocks_on_high_confidence_miss(tmp_path: Path) -> None:
    t = _transcript_with(f"Use {_CLAIMS}", tmp_path)
    env = {"PLUGADVPL_VERIFY_CMD": _stub_verify(
        [{"claim_id": "c1", "symbol": "FWLerExcel", "status": "not_found", "confidence": "high"}]
    )}
    out = _run({"transcript_path": str(t)}, env)
    assert out.get("decision") == "block"
    assert "FWLerExcel" in out.get("reason", "")


def test_allows_when_all_grounded(tmp_path: Path) -> None:
    t = _transcript_with(f"Use {_CLAIMS}", tmp_path)
    env = {"PLUGADVPL_VERIFY_CMD": _stub_verify(
        [{"claim_id": "c1", "symbol": "FWLerExcel", "status": "exists", "confidence": "high"}]
    )}
    assert _run({"transcript_path": str(t)}, env) == {}


def test_low_confidence_miss_does_not_block(tmp_path: Path) -> None:
    t = _transcript_with(f"Use {_CLAIMS}", tmp_path)
    env = {"PLUGADVPL_VERIFY_CMD": _stub_verify(
        [{"claim_id": "c1", "symbol": "FWLerExcel", "status": "not_found", "confidence": "low"}]
    )}
    assert _run({"transcript_path": str(t)}, env) == {}


def test_verify_failure_allows(tmp_path: Path) -> None:
    t = _transcript_with(f"Use {_CLAIMS}", tmp_path)
    env = {"PLUGADVPL_VERIFY_CMD": json.dumps(["nonexistent-bin-xyz-123"])}
    assert _run({"transcript_path": str(t)}, env) == {}
