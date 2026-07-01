"""Fixtures compartilhadas entre testes."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def fake_faircom_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Cria um FAIRCOM_HOME fake com a estrutura real do FairCom DB v13.

    Inclui: binário do servidor, lib nativa do client SQL, driver Python nativo
    e a utilidade ctsqlimp — o suficiente para o `doctor` passar.
    """
    home = tmp_path / "faircom"
    server = home / "server"
    tools = home / "tools"
    drv = home / "drivers" / "python.sql"
    server.mkdir(parents=True)
    tools.mkdir(parents=True)
    drv.mkdir(parents=True)

    (server / "faircom").write_text("#!/bin/sh\necho stub\n")
    (server / "faircom").chmod(0o755)
    (server / "libctsqlapi.so").write_bytes(b"\x7fELF stub")
    (tools / "ctsqlimp").write_text("#!/bin/sh\necho stub\n")
    (tools / "ctsqlimp").chmod(0o755)
    (tools / "ctstop").write_text("#!/bin/sh\necho stub\n")
    (tools / "ctstop").chmod(0o755)
    (tools / "ctinfo.standalone").write_text("#!/bin/sh\necho stub\n")
    (tools / "ctinfo.standalone").chmod(0o755)
    (drv / "pyctree.py").write_text("# stub\n")
    (drv / "pyctsqlapi.py").write_text("# stub\n")

    monkeypatch.setenv("FAIRCOM_HOME", str(home))
    monkeypatch.delenv("CTREE_HOME", raising=False)
    return home


@pytest.fixture
def no_faircom(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Garante que nenhum FAIRCOM_HOME / pasta padrão exista."""
    monkeypatch.delenv("FAIRCOM_HOME", raising=False)
    monkeypatch.delenv("CTREE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))


@pytest.fixture
def isolated_pid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isola o PID file do server em tmp_path pra não vazar entre testes."""
    pid_file = tmp_path / ".dtcat" / "faircom.pid"
    monkeypatch.setattr("plugadvpl.dtc.server.PID_FILE", pid_file)
    return pid_file


@pytest.fixture
def sample_rows() -> tuple[list[str], list[tuple]]:
    """Synthetic (columns, rows) dataset emulando o resultado de um cursor."""
    columns = ["FIELD_CODE", "FIELD_LABEL", "FIELD_TYPE", "FIELD_SIZE", "D_E_L_E_T_"]
    rows = [
        ("CUST_ID    ", b"C\xf3digo", "C", 6, " "),
        ("CUST_NAME  ", b"Nome    ", "C", 30, " "),
        ("OLD_RECORD ", b"Antigo  ", "C", 10, "*"),
    ]
    return columns, rows


@pytest.fixture
def faircom_required() -> Iterator[None]:
    """Skipa o teste se FAIRCOM_HOME não estiver definido (integration/e2e)."""
    if not os.environ.get("FAIRCOM_HOME"):
        pytest.skip("FAIRCOM_HOME não definido — pulando teste de integração")
    yield
