"""Testes do harness especialista (`harness_expert.py`).

Unit: mockam Ollama / plugadvpl / verify-claims — testam dispatch, allowlist,
auditoria anti-alucinação e o loop. e2e: pergunta real + auditoria real (auto-skip).
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request

import pytest

import harness_expert as he

TEST_ROOT = os.environ.get("PLUGADVPL_TEST_ROOT", "")
TEST_SYMBOL = os.environ.get("PLUGADVPL_TEST_SYMBOL", "")
TEST_MODEL = os.environ.get("PLUGADVPL_TEST_MODEL", "qwen2.5:7b")


# ==========================================================================
# unit — executar (dispatch + allowlist)
# ==========================================================================
class TestExecutar:
    def test_plugadvpl_comando_permitido(self, monkeypatch) -> None:
        cap = {}
        monkeypatch.setattr(he, "run_plugadvpl",
                            lambda s, a, r: cap.update(sub=s, args=a) or {"rows": [1]})
        out = he.executar("plugadvpl", {"comando": "tables", "args": "SA1"}, "/r")
        assert cap == {"sub": "tables", "args": ["SA1"]}
        assert json.loads(out) == {"rows": [1]}

    def test_plugadvpl_comando_negado(self, monkeypatch) -> None:
        monkeypatch.setattr(he, "run_plugadvpl", lambda *a, **k: pytest.fail("não devia rodar"))
        assert "não permitido" in he.executar("plugadvpl", {"comando": "ingest", "args": ""}, "/r")

    def test_mapear_processo_usa_dossie(self, monkeypatch) -> None:
        cap = {}
        monkeypatch.setattr(he, "coletar_dossie",
                            lambda c, r: cap.update(cod=c) or {"encontrado": True, "funcao": c})
        out = he.executar("mapear_processo", {"codigo": "FOO"}, "/r")
        assert cap["cod"] == "FOO" and json.loads(out)["funcao"] == "FOO"

    def test_ferramenta_desconhecida(self) -> None:
        assert "desconhecida" in he.executar("xpto", {}, "/r")


# ==========================================================================
# unit — auditar (anti-alucinação)
# ==========================================================================
class TestAuditar:
    def test_sem_tokens_de_tabela(self, monkeypatch) -> None:
        monkeypatch.setattr(he, "verificar_claims", lambda c, r: pytest.fail("não devia chamar"))
        assert he.auditar("texto sem tabelas", "/r") == {"tabelas_checadas": [], "alucinadas": []}

    def test_ignora_siglas(self, monkeypatch) -> None:
        monkeypatch.setattr(he, "verificar_claims", lambda c, r: pytest.fail("não devia chamar"))
        assert he.auditar("É um MVC com API e SQL.", "/r")["tabelas_checadas"] == []

    def test_flagra_tabela_inexistente(self, monkeypatch) -> None:
        monkeypatch.setattr(he, "verificar_claims", lambda c, r: [
            {"symbol": "SA1", "status": "exists"},
            {"symbol": "QQQ", "status": "not_found"},
        ])
        out = he.auditar("Usa SA1 e QQQ.", "/r")
        assert out["tabelas_checadas"] == ["QQQ", "SA1"]
        assert out["alucinadas"] == ["QQQ"]


# ==========================================================================
# unit — perguntar (loop)
# ==========================================================================
class TestPerguntar:
    def test_responde_e_audita(self, monkeypatch) -> None:
        # 1 chamada de ferramenta, depois responde
        respostas = iter([
            {"tool_calls": [{"function": {"name": "plugadvpl",
                                          "arguments": {"comando": "find", "args": "X"}}}]},
            {"content": "A rotina usa a tabela SA1."},
        ])
        monkeypatch.setattr(he, "_chat", lambda m, mod: next(respostas))
        monkeypatch.setattr(he, "run_plugadvpl", lambda *a, **k: {"rows": [{"arquivo": "X.prw"}]})
        monkeypatch.setattr(he, "verificar_claims", lambda c, r: [{"symbol": "SA1", "status": "exists"}])
        r = he.perguntar("o que usa X?", "/r")
        assert "SA1" in r["resposta"]
        assert r["ferramentas"] == ["plugadvpl"]
        assert r["auditoria"]["alucinadas"] == []

    def test_resposta_direta(self, monkeypatch) -> None:
        monkeypatch.setattr(he, "_chat", lambda m, mod: {"content": "resposta"})
        monkeypatch.setattr(he, "verificar_claims", lambda c, r: [])
        assert he.perguntar("oi", "/r")["resposta"] == "resposta"

    def test_erro_de_modelo(self, monkeypatch) -> None:
        monkeypatch.setattr(he, "_chat", lambda m, mod: {"content": "(modelo indisponível: x)", "_erro": True})
        assert "indisponível" in he.perguntar("oi", "/r")["resposta"]

    def test_registra_ferramenta_mapear(self, monkeypatch) -> None:
        respostas = iter([
            {"tool_calls": [{"function": {"name": "mapear_processo", "arguments": {"codigo": "FOO"}}}]},
            {"content": "pronto"},
        ])
        monkeypatch.setattr(he, "_chat", lambda m, mod: next(respostas))
        monkeypatch.setattr(he, "coletar_dossie", lambda c, r: {"encontrado": True})
        monkeypatch.setattr(he, "verificar_claims", lambda c, r: [])
        assert he.perguntar("o que faz FOO?", "/r")["ferramentas"] == ["mapear_processo"]


# ==========================================================================
# e2e — pergunta real
# ==========================================================================
def _ollama_up() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
    except (urllib.error.URLError, OSError):
        return False
    return True


def _tem_indice() -> bool:
    return bool(TEST_ROOT) and shutil.which("plugadvpl") is not None \
        and os.path.isdir(os.path.join(TEST_ROOT, ".plugadvpl"))


@pytest.mark.e2e
@pytest.mark.skipif(not (_tem_indice() and TEST_SYMBOL), reason="defina PLUGADVPL_TEST_ROOT/_SYMBOL")
@pytest.mark.skipif(not _ollama_up(), reason="Ollama offline")
def test_e2e_pergunta_real_sem_alucinacao() -> None:
    r = he.perguntar(f"Em qual arquivo está a rotina {TEST_SYMBOL}?", TEST_ROOT, TEST_MODEL)
    assert isinstance(r["resposta"], str) and len(r["resposta"]) > 5
    assert r["auditoria"]["alucinadas"] == [], "não pode citar tabela inexistente"
