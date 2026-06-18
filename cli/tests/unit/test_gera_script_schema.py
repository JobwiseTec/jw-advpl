"""Testes do schema/montagem do config do gera-script."""

from __future__ import annotations

import pytest

from plugadvpl.compile_servers import Server
from plugadvpl.gera_script.schema import (
    DEFAULT_PASSWORD_ENV,
    PATH_FIELDS,
    SERVER_FIELDS,
    build_config,
    config_schema,
    example_config,
    remaining_placeholders,
)


def _server(**kw: object) -> Server:
    base: dict[str, object] = {
        "name": "qa-cmp",
        "host": "127.0.0.1",
        "port": 1234,
        "build": "7.00.231027P",
        "environments": ["protheus_cmp"],
        "default_environment": "protheus_cmp",
    }
    base.update(kw)
    return Server(**base)  # type: ignore[arg-type]


def test_sem_server_tudo_placeholder_modo_env():
    cfg = build_config(server=None, secret="env")
    # paths + conexao sao placeholders
    for f in (*PATH_FIELDS, *SERVER_FIELDS):
        assert cfg[f.key].startswith("<")
    # modo env: tem o NOME da env var, nao a senha
    assert cfg["PROTHEUS_PASSWORD_ENV"] == DEFAULT_PASSWORD_ENV
    assert "PROTHEUS_PASSWORD" not in cfg


def test_server_preenche_conexao_e_secure_numerico():
    cfg = build_config(server=_server(secure=False), secret="env")
    assert cfg["PROTHEUS_SERVER"] == "127.0.0.1"
    assert cfg["PROTHEUS_PORT"] == "1234"
    assert cfg["PROTHEUS_BUILD"] == "7.00.231027P"
    assert cfg["PROTHEUS_ENV"] == "protheus_cmp"
    # secure NUMERICO (0/1), nunca 'false'/'true'
    assert cfg["PROTHEUS_SECURE"] == "0"
    assert build_config(server=_server(secure=True))["PROTHEUS_SECURE"] == "1"


def test_modo_config_tem_senha_placeholder_e_nao_env():
    cfg = build_config(server=_server(), secret="config")
    assert cfg["PROTHEUS_PASSWORD"] == "<SENHA_COMPILACAO>"
    assert "PROTHEUS_PASSWORD_ENV" not in cfg


def test_modo_env_usa_password_env_do_server():
    cfg = build_config(server=_server(password_env="MINHA_VAR"), secret="env")
    assert cfg["PROTHEUS_PASSWORD_ENV"] == "MINHA_VAR"


def test_paths_override():
    cfg = build_config(paths={"BUILD_DIR": "/home/x/totvs/build"})
    assert cfg["BUILD_DIR"] == "/home/x/totvs/build"
    # os outros continuam placeholder
    assert cfg["FONTES_DIR"].startswith("<")


def test_secret_invalido_levanta():
    with pytest.raises(ValueError, match="secret"):
        build_config(secret="banana")


def test_remaining_placeholders():
    cfg = build_config(server=_server(), secret="env")
    falta = remaining_placeholders(cfg)
    # conexao preenchida; paths e user ainda placeholder
    assert "PROTHEUS_SERVER" not in falta
    assert "BUILD_DIR" in falta
    assert "PROTHEUS_USER" in falta


def test_nunca_grava_senha_real_no_config():
    # mesmo passando server, jamais aparece valor de senha (so nome de env var
    # ou placeholder). Nenhuma chave secreta com valor "real".
    for secret in ("env", "config"):
        cfg = build_config(server=_server(), secret=secret)
        if "PROTHEUS_PASSWORD" in cfg:
            assert cfg["PROTHEUS_PASSWORD"].startswith("<")


def test_example_e_schema_deterministicos():
    assert example_config() == example_config()
    assert config_schema() == config_schema()
    keys = {f["key"] for f in config_schema()}
    assert {"BASE_DIR_PATCHES", "PROTHEUS_SERVER", "PROTHEUS_PASSWORD"} <= keys


def test_tq_off_nao_adiciona_chaves():
    cfg = build_config(server=_server(), secret="env", tq=False)
    assert not any(k.startswith("TQ_") for k in cfg)


def test_tq_on_adiciona_chaves_e_rpo_default():
    cfg = build_config(server=_server(), secret="env", tq=True)
    assert {"TQ_DEST_APO", "TQ_CMP_RPO", "TQ_DEST_BIN", "TQ_RPO_FILES"} <= set(cfg)
    # RPO_FILES tem default (nao e placeholder); restart/healthcheck vazios (opcionais)
    assert cfg["TQ_RPO_FILES"] == "tttm120.rpo,custom.rpo"
    assert cfg["TQ_RESTART_CMD"] == ""
    assert cfg["TQ_HEALTHCHECK_URL"] == ""


def test_tq_placeholders_so_nos_paths_obrigatorios():
    cfg = build_config(secret="env", tq=True)
    falta = remaining_placeholders(cfg)
    assert {"TQ_DEST_APO", "TQ_CMP_RPO", "TQ_DEST_BIN"} <= set(falta)
    # default e opcionais NAO sao placeholder
    assert "TQ_RPO_FILES" not in falta
    assert "TQ_RESTART_CMD" not in falta


def test_schema_inclui_chaves_tq():
    keys = {f["key"] for f in config_schema()}
    assert {"TQ_DEST_APO", "TQ_RESTART_CMD", "TQ_HEALTHCHECK_URL"} <= keys
