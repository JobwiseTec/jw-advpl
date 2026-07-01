"""Testes do modo pergunta-livre (`harness_chat.py`).

- Unit: mockam o chat do Ollama e o `run_plugadvpl` para testar o loop de
  tool-calling, a allowlist e a montagem de mensagens — sem rede nem subprocess.
- e2e: roda o loop contra Ollama + índice real (PLUGADVPL_TEST_ROOT/_SYMBOL; auto-skip).
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request

import pytest

import harness_chat as hc

TEST_ROOT = os.environ.get("PLUGADVPL_TEST_ROOT", "")
TEST_SYMBOL = os.environ.get("PLUGADVPL_TEST_SYMBOL", "")
TEST_MODEL = os.environ.get("PLUGADVPL_TEST_MODEL", "qwen2.5:7b")


# ==========================================================================
# unit — executa_ferramenta (allowlist)
# ==========================================================================
class TestExecutaFerramenta:
    def test_comando_permitido_chama_plugadvpl(self, monkeypatch) -> None:
        capturado = {}

        def _fake(subcmd, args, root, privacy=False):
            capturado["chamada"] = (subcmd, args, root)
            return {"rows": [{"a": 1}]}

        monkeypatch.setattr(hc, "run_plugadvpl", _fake)
        out = hc.executa_ferramenta("plugadvpl", {"comando": "find", "args": "ROT1"}, "/r")
        assert capturado["chamada"] == ("find", ["ROT1"], "/r")
        assert json.loads(out) == {"rows": [{"a": 1}]}

    def test_comando_fora_da_allowlist_bloqueado(self, monkeypatch) -> None:
        # nem chega a chamar run_plugadvpl
        chamou = {"v": False}
        monkeypatch.setattr(hc, "run_plugadvpl", lambda *a, **k: chamou.update(v=True))
        out = hc.executa_ferramenta("plugadvpl", {"comando": "ingest", "args": "x"}, "/r")
        assert "não permitido" in out and chamou["v"] is False

    def test_args_vazio_vira_lista_vazia(self, monkeypatch) -> None:
        capturado = {}
        monkeypatch.setattr(hc, "run_plugadvpl",
                            lambda s, a, r, **k: capturado.update(args=a) or {"rows": []})
        hc.executa_ferramenta("plugadvpl", {"comando": "family", "args": ""}, "/r")
        assert capturado["args"] == []

    def test_rm_arbitrario_nao_executa(self, monkeypatch) -> None:
        monkeypatch.setattr(hc, "run_plugadvpl", lambda *a, **k: {"rows": []})
        out = hc.executa_ferramenta("plugadvpl", {"comando": "rm -rf /", "args": ""}, "/r")
        assert "não permitido" in out

    def test_roteia_mapear_processo(self, monkeypatch) -> None:
        capturado = {}
        monkeypatch.setattr(hc, "mapear_processo",
                            lambda cod, root: capturado.update(cod=cod, root=root) or {"encontrado": True})
        out = hc.executa_ferramenta("mapear_processo", {"codigo": "ROT1"}, "/r")
        assert capturado == {"cod": "ROT1", "root": "/r"}
        assert json.loads(out) == {"encontrado": True}

    def test_mapear_sem_codigo(self) -> None:
        assert "codigo vazio" in hc.executa_ferramenta("mapear_processo", {}, "/r")

    def test_ferramenta_desconhecida(self) -> None:
        assert "desconhecida" in hc.executa_ferramenta("foo", {}, "/r")


# ==========================================================================
# unit — perguntar (loop de tool-calling)
# ==========================================================================
class TestPerguntar:
    def test_resposta_direta_sem_ferramenta(self, monkeypatch) -> None:
        monkeypatch.setattr(hc, "_chamar_ollama", lambda m, mod: {"content": "resposta final"})
        assert hc.perguntar("oi", "/r") == "resposta final"

    def test_uma_chamada_de_ferramenta_depois_responde(self, monkeypatch) -> None:
        # 1ª rodada pede ferramenta; 2ª rodada responde
        respostas = iter([
            {"tool_calls": [{"function": {"name": "plugadvpl",
                                          "arguments": {"comando": "find", "args": "X"}}}]},
            {"content": "achei X"},
        ])
        monkeypatch.setattr(hc, "_chamar_ollama", lambda m, mod: next(respostas))
        monkeypatch.setattr(hc, "run_plugadvpl", lambda *a, **k: {"rows": [{"arquivo": "X.prw"}]})
        assert hc.perguntar("cade X?", "/r") == "achei X"

    def test_resultado_da_ferramenta_vai_pro_contexto(self, monkeypatch) -> None:
        vistos: list[dict] = []
        respostas = iter([
            {"tool_calls": [{"function": {"name": "plugadvpl",
                                          "arguments": {"comando": "arch", "args": "X.prw"}}}]},
            {"content": "ok"},
        ])

        def _cap(messages, modelo):
            vistos.append([m.get("role") for m in messages])
            return next(respostas)

        monkeypatch.setattr(hc, "_chamar_ollama", _cap)
        monkeypatch.setattr(hc, "run_plugadvpl", lambda *a, **k: {"rows": [{"tipo": "ws"}]})
        hc.perguntar("o que e X?", "/r")
        # na 2ª chamada já existe uma mensagem role=tool no histórico
        assert "tool" in vistos[1]

    def test_erro_de_modelo_encerra(self, monkeypatch) -> None:
        monkeypatch.setattr(hc, "_chamar_ollama",
                            lambda m, mod: {"content": "(modelo indisponível: x)", "_erro": True})
        assert "indisponível" in hc.perguntar("oi", "/r")

    def test_teto_de_iteracoes(self, monkeypatch) -> None:
        # sempre pede ferramenta -> nunca responde -> bate no teto
        monkeypatch.setattr(hc, "_chamar_ollama",
                            lambda m, mod: {"tool_calls": [{"function": {"name": "plugadvpl",
                                "arguments": {"comando": "find", "args": "X"}}}]})
        monkeypatch.setattr(hc, "run_plugadvpl", lambda *a, **k: {"rows": []})
        assert "Limite de iterações" in hc.perguntar("loop?", "/r")


# ==========================================================================
# unit — _chamar_ollama (payload + erro)
# ==========================================================================
class TestChamarOllama:
    def test_payload_tem_tools_e_modelo(self, monkeypatch) -> None:
        capturado = {}

        class _Resp:
            def read(self):
                return json.dumps({"message": {"content": "ok"}}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _cap(req, timeout=None):
            capturado["req"] = req
            return _Resp()

        monkeypatch.setattr(hc.urllib.request, "urlopen", _cap)
        msg = hc._chamar_ollama([{"role": "user", "content": "x"}], "qwen2.5:7b")
        assert msg["content"] == "ok"
        payload = json.loads(capturado["req"].data.decode("utf-8"))
        assert payload["model"] == "qwen2.5:7b" and "tools" in payload

    def test_urlerror_vira_erro_estruturado(self, monkeypatch) -> None:
        def _raise(req, timeout=None):
            raise urllib.error.URLError("offline")

        monkeypatch.setattr(hc.urllib.request, "urlopen", _raise)
        msg = hc._chamar_ollama([], "qwen2.5:7b")
        assert msg.get("_erro") is True and "indisponível" in msg["content"]


# ==========================================================================
# e2e — loop real
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


requires_env = pytest.mark.skipif(
    not (_tem_indice() and TEST_SYMBOL and _ollama_up()),
    reason="defina PLUGADVPL_TEST_ROOT/_SYMBOL e tenha Ollama no ar",
)


@pytest.mark.e2e
@requires_env
def test_e2e_pergunta_real() -> None:
    """Pergunta aberta que exige consultar o índice — pipeline inteiro real."""
    resposta = hc.perguntar(f"Em qual arquivo está a rotina {TEST_SYMBOL}?", TEST_ROOT, TEST_MODEL)
    assert isinstance(resposta, str) and len(resposta) > 5
    assert "Limite de iterações" not in resposta
    # o modelo deve ter chegado ao símbolo via ferramenta
    assert TEST_SYMBOL.upper() in resposta.upper()
