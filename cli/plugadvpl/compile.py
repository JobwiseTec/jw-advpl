"""Orquestrador do plugadvpl compile (v0.8.0 Fase 1).

Único módulo que toca subprocess + filesystem. Demais (runtime_config,
compile_parser) são funções puras. Spec: docs/fase1/compile-design.md §5, §7.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from plugadvpl.compile_parser import Diagnostic, parse_diagnostics
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
    raise NotImplementedError("implementado em Step 4.3")


def run(request: CompileRequest, runtime_cfg: RuntimeConfig | None, root: Path) -> CompileResult:
    """Entry point — orquestra todas as etapas e devolve resultado."""
    raise NotImplementedError("modo appre vem no Step 4.5; cli na Task 5")
