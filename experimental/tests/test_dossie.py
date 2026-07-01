"""Testes do mapa completo (`dossie.py`) — dossiê + grounded + verificação.

- Unit (TDD): mockam plugadvpl, verify-claims e Ollama; testam a montagem do
  dossiê, a verificação e a auditoria anti-alucinação em isolamento.
- e2e: pipeline real via PLUGADVPL_TEST_ROOT/_SYMBOL + Ollama (auto-skip sem env).
"""

from __future__ import annotations

import json
import os
import shutil
import types
import urllib.error
import urllib.request

import pytest

import dossie as ds

TEST_ROOT = os.environ.get("PLUGADVPL_TEST_ROOT", "")
TEST_SYMBOL = os.environ.get("PLUGADVPL_TEST_SYMBOL", "")
TEST_MODEL = os.environ.get("PLUGADVPL_TEST_MODEL", "qwen2.5:7b")


def _dispatch(canned: dict):
    def _fake(subcmd, args, root, privacy=False):
        # callees de uma user function específica: chave "callees:<func>"
        if subcmd == "callees" and args and f"callees:{args[0]}" in canned:
            return canned[f"callees:{args[0]}"]
        return canned.get(subcmd, {"rows": []})

    return _fake


# ==========================================================================
# unit — coletar_dossie
# ==========================================================================
class TestColetarDossie:
    CANNED = {
        "find": {"rows": [{"arquivo": "FNMVC1.prw", "funcao": "FNMVC1"}]},
        "arch": {"rows": [{
            "source_type": "mvc", "lines_of_code": 5807,
            "capabilities": ["MVC", "TRANSACTION"], "includes": ["TOTVS.CH"],
            "funcoes": ["a"] * 82, "user_funcs": ["UF1", "UF2", "UF3"],
            "pontos_entrada": ["PE1"],
            "tabelas_read": ["TA1", "TA2", "TA3"], "tabelas_write": ["TA2", "TA3"],
            "tabelas_reclock": [], "tabelas_via_execauto_resolvidas": ["TA2"],
        }]},
        "callers": {"rows": [{"arquivo": "FNMVC1.prw", "funcao": "VWDEF", "linha": 496}]},
        "callees": {"rows": [{"destino": "oBrw:Activate", "linha": 46}]},
        "callees:UF1": {"rows": [{"destino": "FwFormStruct", "linha": 100}]},
        "callees:UF2": {"rows": [{"destino": "MsExecAuto", "linha": 200}]},
    }

    def test_nao_encontrado(self, monkeypatch) -> None:
        monkeypatch.setattr(ds, "run_plugadvpl", _dispatch({"find": {"rows": []}}))
        assert ds.coletar_dossie("X", "/r") == {"encontrado": False, "codigo": "X"}

    def test_montagem_completa(self, monkeypatch) -> None:
        monkeypatch.setattr(ds, "run_plugadvpl", _dispatch(self.CANNED))
        d = ds.coletar_dossie("FNMVC1", "/r")
        assert d["encontrado"] and d["arquivo"] == "FNMVC1.prw"
        assert d["identidade"]["tipo"] == "mvc" and d["identidade"]["loc"] == 5807
        assert d["funcoes"]["total_funcoes"] == 82
        assert d["funcoes"]["user_funcs"] == ["UF1", "UF2", "UF3"]
        assert d["tabelas"]["read"] == ["TA1", "TA2", "TA3"]
        assert d["grafo"]["callers"] == ["VWDEF (FNMVC1.prw:496)"]

    def test_detalhe_por_funcao(self, monkeypatch) -> None:
        monkeypatch.setattr(ds, "run_plugadvpl", _dispatch(self.CANNED))
        d = ds.coletar_dossie("FNMVC1", "/r")
        por_func = {x["funcao"]: x["chama"] for x in d["detalhe_funcoes"]}
        assert por_func["UF1"] == ["FwFormStruct"]
        assert por_func["UF2"] == ["MsExecAuto"]

    def test_cap_de_funcoes_detalhadas(self, monkeypatch) -> None:
        monkeypatch.setattr(ds, "run_plugadvpl", _dispatch(self.CANNED))
        d = ds.coletar_dossie("FNMVC1", "/r", max_funcs=2)
        assert d["_funcs_detalhadas"] == 2 and d["_funcs_total"] == 3
        assert len(d["detalhe_funcoes"]) == 2


# ==========================================================================
# unit — verificar_claims / verificar_dossie
# ==========================================================================
class TestVerificacao:
    def _fake_proc(self, results):
        return types.SimpleNamespace(
            stdout=json.dumps({"results": results}), stderr="", returncode=0
        )

    def test_verificar_claims_parseia(self, monkeypatch) -> None:
        capturado = {}

        def _run(cmd, **k):
            capturado["cmd"] = cmd
            capturado["input"] = k.get("input")
            return self._fake_proc([{"symbol": "SC5", "status": "exists"}])

        monkeypatch.setattr(ds.subprocess, "run", _run)
        out = ds.verificar_claims([{"kind": "table", "symbol": "SC5"}], "/r")
        assert out == [{"symbol": "SC5", "status": "exists"}]
        assert "verify-claims" in capturado["cmd"] and "--stdin" in capturado["cmd"]
        assert json.loads(capturado["input"])["claims"][0]["symbol"] == "SC5"

    def test_verificar_claims_vazio_nao_chama(self, monkeypatch) -> None:
        chamou = {"v": False}
        monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: chamou.update(v=True))
        assert ds.verificar_claims([], "/r") == [] and chamou["v"] is False

    def test_verificar_dossie_separa_funcao_de_tabela(self, monkeypatch) -> None:
        # função inexistente seria grave; tabela fora do dicionário é só cobertura
        monkeypatch.setattr(ds, "verificar_claims", lambda claims, root: [
            {"kind": "function", "symbol": "FNMVC1", "status": "exists"},
            {"kind": "table", "symbol": "TA1", "status": "exists"},
            {"kind": "table", "symbol": "TZ9", "status": "not_found"},
        ])
        dossie = {"funcao": "FNMVC1", "funcoes": {"user_funcs": []},
                  "tabelas": {"read": ["TA1", "TZ9"], "write": []}}
        v = ds.verificar_dossie(dossie, "/r")
        assert v["exists"] == 2
        assert v["funcoes_not_found"] == []          # nenhuma função sumiu
        assert v["tabelas_fora_corpus"] == ["TZ9"]   # tabela code-only (cobertura)


# ==========================================================================
# unit — auditar_narrativa (a rede anti-alucinação)
# ==========================================================================
class TestAuditarNarrativa:
    DOSSIE = {"tabelas": {"read": ["TA1", "TA2"], "write": ["TX1"], "via_execauto": []}}

    def test_sem_tabela_nova(self, monkeypatch) -> None:
        # só cita tabelas conhecidas -> nada a auditar
        monkeypatch.setattr(ds, "verificar_claims", lambda c, r: pytest.fail("não devia chamar"))
        out = ds.auditar_narrativa("Lê TA1 e TA2, grava TX1.", self.DOSSIE, "/r")
        assert out == {"suspeitos": [], "alucinados": []}

    def test_ignora_siglas_comuns(self, monkeypatch) -> None:
        monkeypatch.setattr(ds, "verificar_claims", lambda c, r: pytest.fail("não devia chamar"))
        out = ds.auditar_narrativa("É um MVC que usa SQL e API.", self.DOSSIE, "/r")
        assert out["suspeitos"] == []

    def test_flagra_tabela_inventada(self, monkeypatch) -> None:
        # modelo citou TZ9 (inventada) e TB5 (existe mas fora do dossiê)
        monkeypatch.setattr(ds, "verificar_claims", lambda c, r: [
            {"symbol": "TB5", "status": "exists"},
            {"symbol": "TZ9", "status": "not_found"},
        ])
        out = ds.auditar_narrativa("Também usa TB5 e a tabela TZ9.", self.DOSSIE, "/r")
        assert out["suspeitos"] == ["TB5", "TZ9"]
        assert out["alucinados"] == ["TZ9"]


# ==========================================================================
# unit — narrar_dossie / mapear_completo
# ==========================================================================
class TestNarrarEPipeline:
    def test_narrar_grounding_no_prompt(self, monkeypatch) -> None:
        capturado = {}

        class _Resp:
            def read(self):
                return json.dumps({"message": {"content": "mapa"}}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _cap(req, timeout=None):
            capturado["req"] = req
            return _Resp()

        monkeypatch.setattr(ds.urllib.request, "urlopen", _cap)
        out = ds.narrar_dossie({"funcao": "X"}, "qwen2.5:7b")
        assert out == "mapa"
        payload = json.loads(capturado["req"].data.decode("utf-8"))
        # grounding presente no system prompt
        assert "SOMENTE o que está no dossiê" in payload["messages"][0]["content"]

    def test_narrar_modelo_offline(self, monkeypatch) -> None:
        def _raise(req, timeout=None):
            raise urllib.error.URLError("x")

        monkeypatch.setattr(ds.urllib.request, "urlopen", _raise)
        assert "indisponível" in ds.narrar_dossie({"funcao": "X"}, "m")

    def test_mapear_completo_orquestra(self, monkeypatch) -> None:
        monkeypatch.setattr(ds, "coletar_dossie",
                            lambda c, r: {"encontrado": True, "funcao": c, "x": 1})
        monkeypatch.setattr(ds, "verificar_dossie", lambda d, r: {"exists": 3, "total": 3, "not_found": []})
        monkeypatch.setattr(ds, "narrar_dossie", lambda d, m: "o mapa")
        monkeypatch.setattr(ds, "auditar_narrativa", lambda t, d, r: {"suspeitos": [], "alucinados": []})
        out = ds.mapear_completo("FNX", "/r")
        assert out["narrativa"] == "o mapa" and out["verificacao_dossie"]["exists"] == 3

    def test_mapear_completo_nao_encontrado(self, monkeypatch) -> None:
        monkeypatch.setattr(ds, "coletar_dossie", lambda c, r: {"encontrado": False, "codigo": c})
        assert ds.mapear_completo("X", "/r") == {"encontrado": False, "codigo": "X"}


# ==========================================================================
# e2e — pipeline real
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


requires_index = pytest.mark.skipif(
    not (_tem_indice() and TEST_SYMBOL), reason="defina PLUGADVPL_TEST_ROOT e PLUGADVPL_TEST_SYMBOL")
requires_ollama = pytest.mark.skipif(not _ollama_up(), reason="Ollama offline")


@pytest.mark.e2e
@requires_index
class TestE2EDossie:
    def test_coletar_dossie_real(self) -> None:
        d = ds.coletar_dossie(TEST_SYMBOL, TEST_ROOT)
        assert d["encontrado"] and d["identidade"]["tipo"]
        assert d["_funcs_total"] >= 0
        assert isinstance(d["tabelas"]["read"], list)

    def test_verificar_dossie_real(self) -> None:
        d = ds.coletar_dossie(TEST_SYMBOL, TEST_ROOT)
        v = ds.verificar_dossie(d, TEST_ROOT)
        # TODAS as funções da rotina existem no índice (seria grave se não)
        assert v["funcoes_not_found"] == []
        # tabelas fora do corpus são code-only (sem SX2) — cobertura, não erro
        assert v["exists"] == v["total"] - len(v["tabelas_fora_corpus"])


@pytest.mark.e2e
@requires_index
@requires_ollama
def test_e2e_mapear_completo_sem_alucinacao() -> None:
    """Pipeline inteiro real: o modelo grounded NÃO deve inventar tabela."""
    r = ds.mapear_completo(TEST_SYMBOL, TEST_ROOT, TEST_MODEL)
    assert r["encontrado"] is True
    assert len(r["narrativa"]) > 80
    assert r["auditoria_narrativa"]["alucinados"] == []
