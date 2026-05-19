"""Testes de plugadvpl.runtime_config (v0.8.0 Fase 1)."""
from __future__ import annotations

import json
import os
import stat
import tomllib
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
    # Path no TOML usa forward slash (TOML não escapa \ — em Windows D:\foo seria erro).
    # json.dumps cuida do escaping seguro de aspas, controle chars, etc.
    binary_path_toml = json.dumps(binary_path.replace("\\", "/"))
    content = f'''
[tds_ls]
binary = {binary_path_toml}

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


class TestLoadInvalid:
    def test_malformed_toml_raises(self, tmp_path: Path) -> None:
        cfg_dir = tmp_path / ".plugadvpl"
        cfg_dir.mkdir()
        (cfg_dir / "runtime.toml").write_text("not = valid = toml = at = all", encoding="utf-8")
        with pytest.raises(RuntimeConfigError, match="invalid TOML"):
            load(tmp_path)

    def test_missing_section_raises(self, tmp_path: Path) -> None:
        cfg_dir = tmp_path / ".plugadvpl"
        cfg_dir.mkdir()
        (cfg_dir / "runtime.toml").write_text("[appserver]\nhost = '127.0.0.1'\n", encoding="utf-8")
        # Sem [tds_ls] → falha em _require_section antes de chegar em qualquer key.
        with pytest.raises(RuntimeConfigError, match=r"missing required section \[tds_ls\]"):
            load(tmp_path)

    def test_binary_missing_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "x")
        monkeypatch.setenv("PROTHEUS_PASS", "y")
        _write_minimal_toml(tmp_path, binary="/nope/advpls.exe")
        with pytest.raises(RuntimeConfigError, match="advpls not found"):
            load(tmp_path)

    def test_env_var_missing_does_not_raise_v0_8_11(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v0.8.11 bug 3: env var faltando NÃO falha mais no load.

        Validação migrou pra compile._build_ini_script (só cli mode precisa).
        appre mode roda sem env vars de auth.
        """
        monkeypatch.delenv("PROTHEUS_USER", raising=False)
        monkeypatch.delenv("PROTHEUS_PASS", raising=False)
        _write_minimal_toml(tmp_path)
        with patch("plugadvpl.runtime_config._tcp_ping", return_value=False):
            cfg = load(tmp_path)
        assert cfg is not None
        # Nomes preservados pra validação downstream
        assert cfg.auth.user_env == "PROTHEUS_USER"
        assert cfg.auth.password_env == "PROTHEUS_PASS"

    def test_auth_section_completely_omitted_ok_v0_8_11(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v0.8.11 bug 3: [auth] inteiro pode ser omitido (defaults PROTHEUS_*).

        Caso real: user só vai compilar em mode=appre e não tem AppServer.
        """
        toml_path = _write_minimal_toml(tmp_path)
        full = toml_path.read_text(encoding="utf-8")
        # Remove o bloco [auth] inteiro
        stripped = full.replace(
            '[auth]\nuser_env = "PROTHEUS_USER"\n'
            'password_env = "PROTHEUS_PASS"\naut_file = ""\n',
            "",
        )
        toml_path.write_text(stripped, encoding="utf-8")
        with patch("plugadvpl.runtime_config._tcp_ping", return_value=False):
            cfg = load(tmp_path)
        assert cfg is not None
        assert cfg.auth.user_env == "PROTHEUS_USER"
        assert cfg.auth.password_env == "PROTHEUS_PASS"
        assert cfg.auth.aut_file is None

    def test_aut_file_missing_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "x")
        monkeypatch.setenv("PROTHEUS_PASS", "y")
        toml_path = _write_minimal_toml(tmp_path)
        toml = toml_path.read_text(encoding="utf-8").replace(
            'aut_file = ""', 'aut_file = "/nope/chave.aut"'
        )
        toml_path.write_text(toml, encoding="utf-8")
        with pytest.raises(RuntimeConfigError, match="aut_file not found"):
            load(tmp_path)


class TestLoadFlags:
    def test_warn_remote_host_true_for_remote(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "x")
        monkeypatch.setenv("PROTHEUS_PASS", "y")
        toml_path = _write_minimal_toml(tmp_path)
        toml = toml_path.read_text(encoding="utf-8").replace(
            'host = "127.0.0.1"', 'host = "187.77.46.221"'
        )
        toml_path.write_text(toml, encoding="utf-8")
        with patch("plugadvpl.runtime_config._tcp_ping", return_value=False):
            cfg = load(tmp_path)
        assert cfg is not None
        assert cfg.warn_remote_host is True

    def test_appserver_reachable_set_by_ping(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "x")
        monkeypatch.setenv("PROTHEUS_PASS", "y")
        _write_minimal_toml(tmp_path)
        with patch("plugadvpl.runtime_config._tcp_ping", return_value=True):
            cfg = load(tmp_path)
        assert cfg is not None
        assert cfg.appserver_reachable is True


class TestRenderTemplate:
    def test_template_has_all_sections(self) -> None:
        text = render_template()
        for section in ["[tds_ls]", "[appserver]", "[auth]", "[compile]", "[logging]"]:
            assert section in text

    def test_template_is_valid_toml(self) -> None:
        parsed = tomllib.loads(render_template())
        assert "tds_ls" in parsed
        assert "appserver" in parsed
        assert "auth" in parsed
        assert "compile" in parsed


class TestInitGitignore:
    def test_adds_line_when_gitignore_exists(self, tmp_path: Path) -> None:
        gi = tmp_path / ".gitignore"
        gi.write_text("*.pyc\n", encoding="utf-8")
        assert init_gitignore_entry(tmp_path) is True
        assert ".plugadvpl/runtime.toml" in gi.read_text(encoding="utf-8")

    def test_idempotent(self, tmp_path: Path) -> None:
        gi = tmp_path / ".gitignore"
        gi.write_text(".plugadvpl/runtime.toml\n", encoding="utf-8")
        assert init_gitignore_entry(tmp_path) is False

    def test_no_gitignore_returns_false(self, tmp_path: Path) -> None:
        assert init_gitignore_entry(tmp_path) is False
        assert not (tmp_path / ".gitignore").exists()
