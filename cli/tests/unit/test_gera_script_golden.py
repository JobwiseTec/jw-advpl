"""Golden snapshot + determinismo do gera-script (ps1/sh/config estáveis)."""

from __future__ import annotations

from plugadvpl.compile_servers import Server
from plugadvpl.gera_script import build_config, emit_config_json, emit_ps1, emit_sh


def _server() -> Server:
    return Server(
        name="qa-cmp",
        host="127.0.0.1",
        port=1234,
        build="7.00.231027P",
        environments=["protheus_cmp"],
        default_environment="protheus_cmp",
    )


def test_golden_ps1(snapshot):
    assert emit_ps1() == snapshot


def test_golden_sh(snapshot):
    assert emit_sh() == snapshot


def test_golden_config_env(snapshot):
    assert emit_config_json(build_config(server=_server(), secret="env")) == snapshot


def test_golden_config_secret(snapshot):
    assert emit_config_json(build_config(server=_server(), secret="config")) == snapshot


def test_golden_ps1_tq(snapshot):
    assert emit_ps1(with_tq=True) == snapshot


def test_golden_sh_tq(snapshot):
    assert emit_sh(with_tq=True) == snapshot


def test_golden_config_tq(snapshot):
    assert emit_config_json(build_config(server=_server(), secret="env", tq=True)) == snapshot
