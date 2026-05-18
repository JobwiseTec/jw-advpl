"""Orquestrador do plugadvpl compile (v0.8.0 Fase 1).

Único módulo que toca subprocess + filesystem. Demais (runtime_config,
compile_parser) são funções puras. Spec: docs/fase1/compile-design.md §5, §7.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from plugadvpl.compile_parser import Diagnostic, parse_diagnostics

if TYPE_CHECKING:
    from plugadvpl.runtime_config import RuntimeConfig


@dataclass(frozen=True)
class CompileRequest:
    files: list[Path]
    mode: Literal["auto", "appre", "cli"]
    no_warnings: bool
    timeout_seconds: int | None
    no_security_warning: bool
    includes_override: list[Path] | None
    changed_since: str | None


@dataclass(frozen=True)
class CompileResult:
    rows: list[dict[str, object]]
    summary: dict[str, object]
    next_steps: list[str]
    exit_code: int


@dataclass(frozen=True)
class ResolvedFiles:
    valid_files: list[Path]
    missing: list[Path]
    rejected_ext: list[Path]


_VALID_EXTS = (".prw", ".prx", ".tlpp", ".tlpp.ch")


def resolve_files(
    files: list[Path], changed_since: str | None, root: Path
) -> ResolvedFiles:
    if changed_since:
        files = _resolve_changed_since(changed_since, root)
    valid: list[Path] = []
    missing: list[Path] = []
    rejected: list[Path] = []
    for f in files:
        name = f.name.lower()
        ok_ext = any(name.endswith(ext) for ext in _VALID_EXTS)
        if not ok_ext:
            rejected.append(f)
            continue
        if not f.exists():
            missing.append(f)
            continue
        valid.append(f)
    return ResolvedFiles(valid_files=valid, missing=missing, rejected_ext=rejected)


def _resolve_changed_since(ref: str, root: Path) -> list[Path]:
    """git diff --name-only <ref> filtrado por extensões."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", ref, "--", "*.prw", "*.prx", "*.tlpp"],
            cwd=root, capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"--changed-since requires a git repository at {root}: {exc.stderr.strip()}"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError("git not found in PATH") from exc
    return [root / line for line in proc.stdout.splitlines() if line.strip()]


def pick_mode(requested: str, runtime_cfg: RuntimeConfig | None) -> str:
    if requested in ("cli", "appre"):
        return requested
    if runtime_cfg is not None and runtime_cfg.appserver_reachable:
        return "cli"
    return "appre"


_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"


def _decode_advpls_output(raw: bytes) -> str:
    """Decodifica saída do advpls tratando BOM UTF-16 (PowerShell/WinSrv) e fallback CP1252."""
    if raw.startswith(_UTF16_LE_BOM):
        return raw[len(_UTF16_LE_BOM):].decode("utf-16-le", errors="replace")
    if raw.startswith(_UTF16_BE_BOM):
        return raw[len(_UTF16_BE_BOM):].decode("utf-16-be", errors="replace")
    if raw.startswith(_UTF8_BOM):
        raw = raw[len(_UTF8_BOM):]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _resolve_advpls(runtime_cfg: RuntimeConfig | None) -> Path:
    # Test hook + escape hatch (não documentado publicamente — só CI/testes).
    env_override = os.environ.get("PLUGADVPL_ADVPLS_BINARY")
    if env_override:
        return Path(env_override)
    if runtime_cfg is not None:
        return runtime_cfg.tds_ls.binary
    found = shutil.which("advpls") or shutil.which("advpls.exe")
    if not found:
        raise RuntimeError(
            "advpls not found in PATH. Set tds_ls.binary in runtime.toml or "
            "install tds-vscode extension."
        )
    return Path(found)


def _build_appre_args(binary: Path, includes: list[Path], files: list[Path]) -> list[str]:
    args: list[str] = [str(binary), "appre"]
    for inc in includes:
        args.append(f"-I{inc}")
    args.extend(str(f) for f in files)
    return args


def _build_timeout_result(files: list[Path], timeout: int | None, mode: str) -> CompileResult:
    rows: list[dict[str, object]] = []
    for f in files:
        rows.append({
            "arquivo": str(f), "ok": False, "mode": mode,
            "duration_ms": (timeout or 0) * 1000, "exit_code": 124,
            "counts": {"error": 1, "warning": 0, "info": 0, "unknown": 0},
            "diagnostics": [{
                "severidade": "error", "arquivo": str(f), "linha": 0, "coluna": 0,
                "mensagem": f"compile timeout after {timeout}s",
                "codigo": "", "raw": "",
            }],
        })
    summary: dict[str, object] = {
        "total_files": len(files), "ok": 0, "failed": len(files),
        "total_errors": len(files), "total_warnings": 0,
        "mode_used": mode, "appserver_reachable": False,
        "runtime_config_loaded": False, "output_truncated": False,
    }
    return CompileResult(rows=rows, summary=summary, next_steps=[], exit_code=1)


def _build_next_steps(rows: list[dict[str, object]], mode: str) -> list[str]:
    _ = mode  # reservado p/ contextualizar próximos passos por modo (Task 5+)
    if all(r["ok"] for r in rows):
        return []
    failed_files = [
        str(r["arquivo"]) for r in rows
        if not r["ok"] and r["arquivo"] != "__unmatched__"
    ]
    steps: list[str] = []
    if failed_files:
        steps.append(f"plugadvpl arch {failed_files[0]}   # contexto arquitetural")
    steps.append("plugadvpl compile <file> --no-warnings   # filtra warnings")
    return steps


def run(request: CompileRequest, runtime_cfg: RuntimeConfig | None, root: Path) -> CompileResult:
    resolved = resolve_files(request.files, request.changed_since, root)
    files = resolved.valid_files
    mode = pick_mode(request.mode, runtime_cfg)
    binary = _resolve_advpls(runtime_cfg)

    if mode == "appre":
        includes = (
            request.includes_override
            if request.includes_override is not None
            else (list(runtime_cfg.compile.includes) if runtime_cfg else [])
        )
        args = _build_appre_args(binary, includes, files)
    else:
        # modo cli implementado na Task 5
        raise NotImplementedError("modo cli implementado na Task 5")

    start = time.monotonic()
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = proc.communicate(timeout=request.timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return _build_timeout_result(files, request.timeout_seconds, mode)

    stdout = _decode_advpls_output(stdout_bytes)
    stderr = _decode_advpls_output(stderr_bytes)
    duration_ms = int((time.monotonic() - start) * 1000)
    matched, unmatched = parse_diagnostics(
        stdout=stdout, stderr=stderr, mode=mode, requested_files=files,
    )

    # group diagnostics by file
    by_file: dict[str, list[Diagnostic]] = {str(f): [] for f in files}
    for d in matched:
        if d.arquivo in by_file:
            by_file[d.arquivo].append(d)
        else:
            by_file.setdefault("__unknown__", []).append(d)

    rows: list[dict[str, object]] = []
    for fpath, diags in by_file.items():
        counts = {
            "error": sum(1 for d in diags if d.severidade == "error"),
            "warning": sum(1 for d in diags if d.severidade == "warning"),
            "info": sum(1 for d in diags if d.severidade == "info"),
            "unknown": sum(1 for d in diags if d.severidade == "unknown"),
        }
        rows.append({
            "arquivo": fpath,
            "ok": counts["error"] == 0,
            "mode": mode,
            "duration_ms": duration_ms,
            "exit_code": proc.returncode,
            "counts": counts,
            "diagnostics": [d.to_dict() for d in diags],
        })

    if unmatched:
        rows.append({
            "arquivo": "__unmatched__",
            "ok": False,
            "mode": mode,
            "duration_ms": duration_ms,
            "exit_code": proc.returncode,
            "counts": {
                "error": sum(1 for d in unmatched if d.severidade == "error"),
                "warning": 0, "info": 0, "unknown": 0,
            },
            "diagnostics": [d.to_dict() for d in unmatched],
        })

    total_errors = 0
    total_warnings = 0
    for r in rows:
        counts_obj = r["counts"]
        if isinstance(counts_obj, dict):
            total_errors += int(counts_obj.get("error", 0) or 0)
            total_warnings += int(counts_obj.get("warning", 0) or 0)
    failed = sum(1 for r in rows if not r["ok"])
    exit_code = 1 if total_errors > 0 else 0

    summary: dict[str, object] = {
        "total_files": len(files),
        "ok": len(files) - sum(1 for r in rows if r["arquivo"] in [str(f) for f in files] and not r["ok"]),
        "failed": failed,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "mode_used": mode,
        "appserver_reachable": runtime_cfg.appserver_reachable if runtime_cfg else False,
        "runtime_config_loaded": runtime_cfg is not None,
        "output_truncated": False,
    }
    next_steps = _build_next_steps(rows, mode)
    return CompileResult(rows=rows, summary=summary, next_steps=next_steps, exit_code=exit_code)
