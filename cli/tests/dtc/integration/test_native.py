"""Testes de integração — requer FairCom DB instalado + servidor SQL rodando.

Pulados se FAIRCOM_HOME não estiver definido. Marcados como `integration`,
NÃO rodam no CI por padrão (rode com `pytest -m integration`).

Pré-requisitos para rodar:
  export FAIRCOM_HOME=~/faircom
  dtcat server start
"""

from __future__ import annotations

import pytest

from plugadvpl.dtc import faircom

pytestmark = pytest.mark.integration


def test_native_driver_loads(faircom_required: None) -> None:
    drv = faircom.load_native_driver()
    assert drv.apilevel == "2.0"


def test_can_connect_and_query(faircom_required: None) -> None:
    try:
        conn = faircom.connect()
    except Exception as e:
        pytest.fail(
            f"Não conseguiu conectar via driver nativo. "
            f"Servidor rodando? `dtcat server start`. Erro: {e}"
        )
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
    finally:
        conn.close()


def test_doctor_passes_when_env_complete(faircom_required: None) -> None:
    from rich.console import Console

    from plugadvpl.dtc.doctor import run_doctor

    console = Console(record=True)
    assert run_doctor(console) is True, "doctor reportou falha com ambiente completo"
