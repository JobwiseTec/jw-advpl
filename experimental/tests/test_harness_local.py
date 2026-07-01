"""Testes do harness local (`harness_local.py`).

Estratégia:
- **Unit (TDD):** mockam `subprocess.run` e `urllib` para testar cada função em
  isolamento, sem tocar no plugadvpl real nem no Ollama. Determinísticos e rápidos.
- **e2e (marcados):** rodam contra um índice real informado por variável de ambiente
  (PLUGADVPL_TEST_ROOT/_SYMBOL) e/ou Ollama; *skipados* se o ambiente não estiver disponível.

Rodar:  uv run --no-project --with pytest pytest -v experimental/tests/
Só unit: ... -m "not e2e"      Só e2e: ... -m e2e
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import types
import urllib.error
import urllib.request

import pytest

import harness_local as hl

# e2e dirigido por ambiente — sem nenhum caminho/nome fixo no código.
TEST_ROOT = os.environ.get("PLUGADVPL_TEST_ROOT", "")
TEST_SYMBOL = os.environ.get("PLUGADVPL_TEST_SYMBOL", "")
TEST_MODEL = os.environ.get("PLUGADVPL_TEST_MODEL", "qwen2.5:7b")


# ==========================================================================
# helpers de mock
# ==========================================================================
def _fake_proc(stdout: str = "", stderr: str = "") -> types.SimpleNamespace:
    """Imita o retorno de subprocess.run (só os atributos que usamos)."""
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=0)


class _FakeResp:
    """Imita a resposta de urllib.urlopen (context manager com .read())."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *_: object) -> bool:
        return False


# ==========================================================================
# unit — _label
# ==========================================================================
class TestLabel:
    def test_destino_com_linha(self) -> None:
        assert hl._label({"destino": "oDlg:End", "linha": 149}) == "oDlg:End :149"

    def test_arquivo_e_linha(self) -> None:
        assert hl._label({"funcao": "U_X", "arquivo": "A.prw", "linha": 10}) == "U_X (A.prw:10)"

    def test_prioridade_de_chaves(self) -> None:
        # destino tem prioridade sobre funcao/nome/origem
        assert hl._label({"destino": "D", "funcao": "F", "nome": "N"}).startswith("D")

    def test_origem_fallback(self) -> None:
        assert hl._label({"origem": "Chamador"}) == "Chamador"

    def test_sem_chaves_conhecidas(self) -> None:
        assert hl._label({"x": 1}) == "?"


# ==========================================================================
# unit — run_plugadvpl
# ==========================================================================
class TestRunPlugadvpl:
    def test_json_valido(self, monkeypatch) -> None:
        monkeypatch.setattr(hl.subprocess, "run", lambda *a, **k: _fake_proc('{"rows":[{"a":1}]}'))
        assert hl.run_plugadvpl("find", ["X"], "/r") == {"rows": [{"a": 1}]}

    def test_stdout_vazio(self, monkeypatch) -> None:
        monkeypatch.setattr(hl.subprocess, "run", lambda *a, **k: _fake_proc("", "boom"))
        out = hl.run_plugadvpl("find", ["X"], "/r")
        assert out["rows"] == [] and out["_stderr"] == "boom"

    def test_json_invalido(self, monkeypatch) -> None:
        monkeypatch.setattr(hl.subprocess, "run", lambda *a, **k: _fake_proc("nao-e-json"))
        assert hl.run_plugadvpl("find", ["X"], "/r")["_erro"] == "JSON inválido"

    def test_binario_ausente(self, monkeypatch) -> None:
        def _raise(*a, **k):
            raise FileNotFoundError

        monkeypatch.setattr(hl.subprocess, "run", _raise)
        assert "não encontrado" in hl.run_plugadvpl("find", ["X"], "/r")["_erro"]

    def test_timeout(self, monkeypatch) -> None:
        def _raise(*a, **k):
            raise subprocess.TimeoutExpired(cmd="plugadvpl", timeout=60)

        monkeypatch.setattr(hl.subprocess, "run", _raise)
        assert "timeout" in hl.run_plugadvpl("arch", ["X"], "/r")["_erro"]

    def test_monta_comando_correto(self, monkeypatch) -> None:
        capturado = {}

        def _cap(cmd, **k):
            capturado["cmd"] = cmd
            return _fake_proc('{"rows":[]}')

        monkeypatch.setattr(hl.subprocess, "run", _cap)
        hl.run_plugadvpl("callers", ["U_X"], "/proj")
        cmd = capturado["cmd"]
        assert cmd[:5] == ["plugadvpl", "--format", "json", "--root", "/proj"]
        assert cmd[-2:] == ["callers", "U_X"]
        assert "--privacy" not in cmd

    def test_flag_privacy(self, monkeypatch) -> None:
        capturado = {}

        def _cap(cmd, **k):
            capturado["cmd"] = cmd
            return _fake_proc('{"rows":[]}')

        monkeypatch.setattr(hl.subprocess, "run", _cap)
        hl.run_plugadvpl("find", ["X"], "/r", privacy=True)
        assert "--privacy" in capturado["cmd"]


# ==========================================================================
# unit — localizar
# ==========================================================================
class TestLocalizar:
    def test_match_exato_tem_prioridade(self, monkeypatch) -> None:
        rows = {"rows": [{"arquivo": "A.prw", "funcao": "Outra"},
                         {"arquivo": "B.prw", "funcao": "Alvo"}]}
        monkeypatch.setattr(hl, "run_plugadvpl", lambda *a, **k: rows)
        assert hl.localizar("Alvo", "/r") == ("B.prw", "Alvo")

    def test_sem_exato_pega_primeiro(self, monkeypatch) -> None:
        rows = {"rows": [{"arquivo": "A.prw", "funcao": "Foo"}]}
        monkeypatch.setattr(hl, "run_plugadvpl", lambda *a, **k: rows)
        assert hl.localizar("Bar", "/r") == ("A.prw", "Foo")

    def test_vazio(self, monkeypatch) -> None:
        monkeypatch.setattr(hl, "run_plugadvpl", lambda *a, **k: {"rows": []})
        assert hl.localizar("X", "/r") == (None, "X")


# ==========================================================================
# unit — mapear_processo
# ==========================================================================
def _dispatch(canned: dict):
    """Fábrica de fake run_plugadvpl que despacha por subcomando."""

    def _fake(subcmd, args, root, privacy=False):
        return canned.get(subcmd, {"rows": []})

    return _fake


class TestMapearProcesso:
    def test_nao_encontrado(self, monkeypatch) -> None:
        monkeypatch.setattr(hl, "run_plugadvpl", _dispatch({"find": {"rows": []}}))
        f = hl.mapear_processo("X", "/r")
        assert f["encontrado"] is False and f["codigo"] == "X"

    def test_montagem_completa(self, monkeypatch) -> None:
        canned = {
            "find": {"rows": [{"arquivo": "X.prw", "funcao": "X"}]},
            "arch": {"rows": [{
                "source_type": "webservice", "lines_of_code": 100,
                "capabilities": ["WS-REST"], "tabelas_read": ["SX2"],
                "tabelas_write": [], "includes": ["TOTVS.CH"],
            }]},
            "callers": {"rows": []},
            "callees": {"rows": [{"destino": "oDlg:End", "linha": 149}]},
        }
        monkeypatch.setattr(hl, "run_plugadvpl", _dispatch(canned))
        f = hl.mapear_processo("X", "/r")
        assert f["encontrado"] is True
        assert f["arquivo"] == "X.prw" and f["tipo"] == "webservice" and f["loc"] == 100
        assert f["tabelas_read"] == ["SX2"] and f["tabelas_write"] == []
        assert f["callees"] == ["oDlg:End :149"] and f["callers"] == []

    def test_defaults_para_chaves_ausentes(self, monkeypatch) -> None:
        canned = {
            "find": {"rows": [{"arquivo": "Y.prw", "funcao": "Y"}]},
            "arch": {"rows": [{}]},  # arch pobre
        }
        monkeypatch.setattr(hl, "run_plugadvpl", _dispatch(canned))
        f = hl.mapear_processo("Y", "/r")
        assert f["capabilities"] == [] and f["tabelas_read"] == [] and f["includes"] == []

    def test_fallback_tipo_arquivo(self, monkeypatch) -> None:
        # sem source_type, usa tipo_arquivo
        canned = {
            "find": {"rows": [{"arquivo": "Z.prw", "funcao": "Z"}]},
            "arch": {"rows": [{"tipo_arquivo": "include"}]},
        }
        monkeypatch.setattr(hl, "run_plugadvpl", _dispatch(canned))
        assert hl.mapear_processo("Z", "/r")["tipo"] == "include"


# ==========================================================================
# unit (TDD) — cenário fixo (sintético): User Function/PE com caller, sem tabelas
# ==========================================================================
class TestMapearUserFunc:
    """Forma de uma User Function/PE pequena: tem caller, sem tabelas. Dados sintéticos."""

    CANNED = {
        "find": {"rows": [{"arquivo": "FNUSR1.prw", "funcao": "FNUSR1"}]},
        "arch": {"rows": [{
            "source_type": "user_function", "lines_of_code": 32,
            "capabilities": [], "tabelas_read": [], "tabelas_write": [],
            "includes": ["Protheus.ch"],
        }]},
        "callers": {"rows": [{
            "arquivo": "ENTRYPT.prw", "funcao": "ENTRYPT", "linha": 21,
            "tipo": "user_func", "is_self_call": False,
        }]},
        "callees": {"rows": []},
    }

    def test_montagem_fiel(self, monkeypatch) -> None:
        monkeypatch.setattr(hl, "run_plugadvpl", _dispatch(self.CANNED))
        f = hl.mapear_processo("FNUSR1", "/r")
        assert f["encontrado"] is True
        assert f["arquivo"] == "FNUSR1.prw" and f["tipo"] == "user_function"
        assert f["loc"] == 32 and f["includes"] == ["Protheus.ch"]
        assert f["tabelas_read"] == [] and f["tabelas_write"] == []
        assert f["callers"] == ["ENTRYPT (ENTRYPT.prw:21)"]
        assert f["callees"] == []

    def test_formatar_legivel(self, monkeypatch) -> None:
        monkeypatch.setattr(hl, "run_plugadvpl", _dispatch(self.CANNED))
        txt = hl.formatar_fatos(hl.mapear_processo("FNUSR1", "/r"))
        assert "FNUSR1.prw" in txt
        assert "ENTRYPT (ENTRYPT.prw:21)" in txt
        assert "Protheus.ch" in txt


# ==========================================================================
# unit (TDD) — cenário PESADO (sintético): MVC grande, 27 tabelas + capabilities
# ==========================================================================
class TestMapearMvcGrande:
    """Forma de um MVC grande: muitas tabelas lidas, várias gravadas, vários callers.
    Tabelas/funções 100% sintéticas — só exercita a montagem de listas grandes.
    """

    _READ = [f"T{i:02d}" for i in range(1, 28)]  # 27 tabelas sintéticas
    _WRITE = ["T01", "T06", "T19", "T20"]
    _CAPS = ["DIALOG", "EXEC_AUTO_CALLER", "MULTI_FILIAL", "MVC", "PARAMBOX", "PE", "TRANSACTION"]

    CANNED = {
        "find": {"rows": [{"arquivo": "FNMVC1.prw", "funcao": "FNMVC1"}]},
        "arch": {"rows": [{
            "source_type": "mvc", "lines_of_code": 5807, "capabilities": _CAPS,
            "tabelas_read": _READ, "tabelas_write": _WRITE,
            "includes": ["FWMVCDEF.CH", "TBICONN.CH", "TOTVS.CH"],
        }]},
        "callers": {"rows": [
            {"arquivo": "FNMVC1.prw", "funcao": "VWDEF", "linha": 496},
            {"arquivo": "FNMVC1.prw", "funcao": "CANC", "linha": 1623},
            {"arquivo": "FNMVC1.prw", "funcao": "PROC", "linha": 1939},
        ]},
        "callees": {"rows": [
            {"destino": "oBrw:SetAlias", "linha": 30, "tipo": "method"},
            {"destino": "oBrw:Activate", "linha": 46, "tipo": "method"},
        ]},
    }

    def test_montagem_pesada(self, monkeypatch) -> None:
        monkeypatch.setattr(hl, "run_plugadvpl", _dispatch(self.CANNED))
        f = hl.mapear_processo("FNMVC1", "/r")
        assert f["encontrado"] is True
        assert f["tipo"] == "mvc" and f["loc"] == 5807
        assert len(f["tabelas_read"]) == 27 and "T01" in f["tabelas_read"]
        assert f["tabelas_write"] == ["T01", "T06", "T19", "T20"]
        assert "MVC" in f["capabilities"] and "TRANSACTION" in f["capabilities"]
        assert "VWDEF (FNMVC1.prw:496)" in f["callers"]
        assert "oBrw:SetAlias :30" in f["callees"]

    def test_preserva_todas_as_tabelas(self, monkeypatch) -> None:
        # nenhuma tabela some na montagem (lista grande)
        monkeypatch.setattr(hl, "run_plugadvpl", _dispatch(self.CANNED))
        f = hl.mapear_processo("FNMVC1", "/r")
        assert set(f["tabelas_read"]) == set(self._READ)

    def test_formatar_lista_grande(self, monkeypatch) -> None:
        monkeypatch.setattr(hl, "run_plugadvpl", _dispatch(self.CANNED))
        txt = hl.formatar_fatos(hl.mapear_processo("FNMVC1", "/r"))
        assert "T27" in txt and "5807 linhas" in txt and "MVC" in txt


# ==========================================================================
# unit — formatar_fatos
# ==========================================================================
class TestFormatarFatos:
    def test_nao_encontrado(self) -> None:
        assert "não encontrado" in hl.formatar_fatos({"encontrado": False, "codigo": "X"})

    def test_listas_vazias_viram_tracinho(self) -> None:
        f = {"encontrado": True, "funcao": "X", "arquivo": "X.prw", "tipo": "ws",
             "loc": 10, "capabilities": [], "tabelas_read": [], "tabelas_write": [],
             "includes": [], "callers": [], "callees": []}
        txt = hl.formatar_fatos(f)
        assert "Grava tabelas:—" in txt and "Chamado por:  —" in txt

    def test_inclui_dados(self) -> None:
        f = {"encontrado": True, "funcao": "X", "arquivo": "X.prw", "tipo": "ws",
             "loc": 10, "capabilities": ["WS-REST"], "tabelas_read": ["SX2"],
             "tabelas_write": [], "includes": [], "callers": [], "callees": []}
        txt = hl.formatar_fatos(f)
        assert "SX2" in txt and "WS-REST" in txt and "X.prw" in txt


# ==========================================================================
# unit — narrar
# ==========================================================================
class TestNarrar:
    def _fatos(self) -> dict:
        return {"funcao": "X", "arquivo": "X.prw", "tipo": "ws", "loc": 10,
                "capabilities": [], "tabelas_read": ["SX2"], "tabelas_write": [],
                "includes": [], "callers": ["Y"], "callees": ["Z"]}

    def test_parseia_resposta(self, monkeypatch) -> None:
        body = json.dumps({"message": {"content": "resumo de teste"}}).encode()
        monkeypatch.setattr(hl.urllib.request, "urlopen", lambda req, timeout=None: _FakeResp(body))
        assert hl.narrar(self._fatos(), "qwen2.5:7b") == "resumo de teste"

    def test_payload_usa_rotulos_pt(self, monkeypatch) -> None:
        capturado = {}

        def _cap(req, timeout=None):
            capturado["req"] = req
            return _FakeResp(json.dumps({"message": {"content": "ok"}}).encode())

        monkeypatch.setattr(hl.urllib.request, "urlopen", _cap)
        hl.narrar(self._fatos(), "mistral-nemo:12b")
        payload = json.loads(capturado["req"].data.decode("utf-8"))
        assert payload["model"] == "mistral-nemo:12b"
        user = payload["messages"][1]["content"]
        # rótulos PT presentes; chaves cruas EN ausentes (a correção do bug)
        assert "quem_chama_esta_rotina" in user and "o_que_esta_rotina_chama" in user
        assert '"callers"' not in user and '"callees"' not in user

    def test_modelo_indisponivel(self, monkeypatch) -> None:
        def _raise(req, timeout=None):
            raise urllib.error.URLError("conexao recusada")

        monkeypatch.setattr(hl.urllib.request, "urlopen", _raise)
        assert "modelo indisponível" in hl.narrar(self._fatos(), "qwen2.5:7b")


# ==========================================================================
# e2e — caminho real (skip se ambiente ausente)
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
class TestE2EDeterministico:
    def test_find_real(self) -> None:
        d = hl.run_plugadvpl("find", [TEST_SYMBOL], TEST_ROOT)
        assert d.get("rows"), "find real deveria achar o símbolo de teste"

    def test_mapear_real(self) -> None:
        f = hl.mapear_processo(TEST_SYMBOL, TEST_ROOT)
        assert f["encontrado"] is True
        assert f["arquivo"] and f["tipo"]
        # estrutura coerente (sem afirmar nada específico do projeto)
        for chave in ("tabelas_read", "tabelas_write", "callers", "callees", "includes"):
            assert isinstance(f[chave], list)

    def test_simbolo_inexistente_real(self) -> None:
        assert hl.mapear_processo("ZZZ_NAO_EXISTE_999", TEST_ROOT)["encontrado"] is False


@pytest.mark.e2e
@requires_index
@requires_ollama
def test_e2e_narrar_modelo_real() -> None:
    """Roda o pipeline inteiro contra o Ollama de verdade (modelo via env)."""
    fatos = hl.mapear_processo(TEST_SYMBOL, TEST_ROOT)
    texto = hl.narrar(fatos, TEST_MODEL)
    assert isinstance(texto, str) and len(texto) > 20
    assert "modelo indisponível" not in texto
