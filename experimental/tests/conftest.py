"""Configuração de testes do harness local.

- Coloca o diretório dos módulos no ``sys.path`` (import direto).
- Registra o marker ``e2e``.
- Expõe root/símbolo de teste via variável de ambiente — assim os e2e rodam
  contra QUALQUER projeto indexado, sem nenhum caminho ou nome fixo no código:

    PLUGADVPL_TEST_ROOT=/caminho/do/projeto  (precisa ter .plugadvpl/)
    PLUGADVPL_TEST_SYMBOL=NomeDeUmaRotina    (símbolo existente no índice)

  Sem essas variáveis, os e2e que dependem de índice/símbolo são *skipados*.
"""

from __future__ import annotations

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_ROOT = os.environ.get("PLUGADVPL_TEST_ROOT", "")
TEST_SYMBOL = os.environ.get("PLUGADVPL_TEST_SYMBOL", "")


def tem_indice() -> bool:
    """True se há um projeto indexado utilizável para e2e (via env, sem nada fixo)."""
    return bool(TEST_ROOT) and shutil.which("plugadvpl") is not None \
        and os.path.isdir(os.path.join(TEST_ROOT, ".plugadvpl"))


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers", "e2e: ponta-a-ponta — usa PLUGADVPL_TEST_ROOT/_SYMBOL e/ou Ollama reais"
    )
