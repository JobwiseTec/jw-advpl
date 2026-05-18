"""Testes de plugadvpl.compile_parser (v0.8.0 Fase 1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.compile_parser import Diagnostic, parse_diagnostics


FIXTURES = Path(__file__).parent.parent / "fixtures" / "compile_outputs"
