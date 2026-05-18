"""Testes de plugadvpl.runtime_config (v0.8.0 Fase 1)."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from plugadvpl.runtime_config import (
    RuntimeConfig,
    RuntimeConfigError,
    init_gitignore_entry,
    load,
    render_template,
)


def _fake_advpls_binary(root: Path) -> Path:
    """Cria executável real (cross-platform) que serve como ``tds_ls.binary``.

    Linux/macOS: shell script ``#!/bin/sh\\nexit 0`` com mode 0o755.
    Windows: arquivo ``.bat`` (Path.is_file() aceita qualquer extensão).
    """
    if os.name == "nt":
        target = root / "fake_advpls.bat"
        target.write_text("@exit /b 0\r\n", encoding="cp1252")
    else:
        target = root / "fake_advpls"
        target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return target


def _write_minimal_toml(root: Path, **overrides: str) -> Path:
    """Helper: escreve runtime.toml com defaults sensatos + overrides."""
    cfg_dir = root / ".plugadvpl"
    cfg_dir.mkdir(exist_ok=True)
    binary_path = overrides.get("binary", str(_fake_advpls_binary(root)))
    # Path no TOML usa forward slash (TOML não escapa \ — em Windows D:\foo seria erro)
    binary_path_toml = binary_path.replace("\\", "/")
    content = f'''
[tds_ls]
binary = "{binary_path_toml}"

[appserver]
host = "127.0.0.1"
port = 1234
secure = false
build = "7.00.240223P"
environment = "P2510"

[auth]
user_env = "PROTHEUS_USER"
password_env = "PROTHEUS_PASS"
aut_file = ""

[compile]
recompile = true
includes = []
mode = "auto"
timeout_seconds = 120
include_warnings = true

[logging]
log_to_file = ""
show_console_output = true
'''
    toml_path = cfg_dir / "runtime.toml"
    toml_path.write_text(content, encoding="utf-8")
    return toml_path


class TestLoadAbsent:
    def test_returns_none_when_toml_missing(self, tmp_path: Path) -> None:
        """Sem runtime.toml → None (sem exceção). Modo appre funciona assim."""
        assert load(tmp_path) is None


class TestLoadValidComplete:
    def test_returns_dataclass_when_all_valid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        _write_minimal_toml(tmp_path)
        with patch("plugadvpl.runtime_config._tcp_ping", return_value=False):
            cfg = load(tmp_path)
        assert cfg is not None
        assert isinstance(cfg, RuntimeConfig)
        assert cfg.appserver.host == "127.0.0.1"
        assert cfg.appserver.port == 1234
        assert cfg.compile.mode == "auto"
        assert cfg.warn_remote_host is False
        assert cfg.appserver_reachable is False
