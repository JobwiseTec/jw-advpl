"""Testes do emitter do gera-script (ps1/sh/config + determinismo + seguranca)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from plugadvpl.gera_script import (
    CONFIG_NAME,
    PS1_NAME,
    SH_NAME,
    build_config,
    emit_config_json,
    emit_ps1,
    emit_sh,
)


def test_ps1_crlf_e_deterministico():
    a, b = emit_ps1(), emit_ps1()
    assert a == b
    assert "\r\n" in a
    # sem CR solto fora de CRLF
    assert a.replace("\r\n", "").count("\r") == 0


def test_sh_lf_e_shebang():
    sh = emit_sh()
    assert sh == emit_sh()
    assert sh.startswith("#!/usr/bin/env bash")
    assert "\r" not in sh


def test_sh_le_config_via_jq():
    sh = emit_sh()
    assert "command -v jq" in sh
    assert "jq -r" in sh


def test_scripts_tem_etapas_e_defrag():
    for txt in (emit_ps1(), emit_sh()):
        assert "patchApply" in txt
        assert "action=compile" in txt
        assert "defragRPO" in txt


def test_scripts_tem_leitura_dual_de_senha():
    # env var (preferido) E fallback de config
    ps1 = emit_ps1()
    assert "PROTHEUS_PASSWORD_ENV" in ps1
    assert "GetEnvironmentVariable" in ps1
    sh = emit_sh()
    assert "PROTHEUS_PASSWORD_ENV" in sh
    assert "PROTHEUS_PASSWORD" in sh


def test_scripts_nao_embutem_senha_literal():
    # o template NUNCA carrega uma senha de verdade
    for txt in (emit_ps1(), emit_sh()):
        assert "protheus123" not in txt
        assert "psw=protheus\n" not in txt  # so via variavel


def test_config_json_roundtrip_e_newline_final():
    cfg = build_config(secret="env")
    out = emit_config_json(cfg)
    assert out.endswith("\n")
    assert json.loads(out) == cfg


def test_nomes_dos_artefatos():
    assert PS1_NAME == "patch_e_compilacao.ps1"
    assert SH_NAME == "patch_e_compilacao.sh"
    assert CONFIG_NAME == "patch_e_compilacao_config.json"


@pytest.mark.parametrize("with_tq", [False, True])
def test_ps1_sem_escape_estilo_bash(with_tq):
    # PowerShell escapa com backtick, nao com '\'. Um '\$' no .ps1 e quase sempre
    # um bash-ism que quebra o PARSE inteiro (regressao pega no smoke da VM).
    assert "\\$" not in emit_ps1(with_tq=with_tq)


@pytest.mark.parametrize("with_tq", [False, True])
def test_ps1_e_ascii(with_tq):
    # PS 5.1 le .ps1 sem BOM como ANSI; um char nao-ASCII (ex.: em-dash) vira
    # aspa tipografica e o 5.1 a trata como delimitador de string -> quebra o
    # parse (regressao pega no smoke da VM). Mantemos o .ps1 100% ASCII.
    assert emit_ps1(with_tq=with_tq).isascii()


def test_fase_tq_presente_so_com_flag():
    for emit in (emit_ps1, emit_sh):
        assert "ETAPA 3: TROCA QUENTE" not in emit(with_tq=False)
        assert "{{TQ_PHASE}}" not in emit(with_tq=False)  # marker removido
        com_tq = emit(with_tq=True)
        assert "ETAPA 3: TROCA QUENTE" in com_tq
        assert "TQ_DEST_APO" in com_tq
        assert "TQ_RESTART_CMD" in com_tq  # restart p/ REST


@pytest.mark.parametrize("with_tq", [False, True])
@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh nao instalado")
def test_ps1_parseia_no_pwsh(tmp_path, with_tq):
    p = tmp_path / "s.ps1"
    p.write_text(emit_ps1(with_tq=with_tq), encoding="utf-8", newline="")
    script = (
        "$e=$null; "
        f"[void][System.Management.Automation.PSParser]::Tokenize("
        f"(Get-Content -Raw '{p}'), [ref]$e); "
        "if ($e.Count) { $e | ForEach-Object { Write-Error $_.Message }; exit 1 }"
    )
    r = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("with_tq", [False, True])
@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="bash de Windows (WSL/git-bash) nao lida com path C:\\; .sh e p/ Linux",
)
def test_sh_parseia_no_bash(tmp_path, with_tq):
    p = tmp_path / "s.sh"
    p.write_text(emit_sh(with_tq=with_tq), encoding="utf-8", newline="")
    r = subprocess.run(
        ["bash", "-n", str(p)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
