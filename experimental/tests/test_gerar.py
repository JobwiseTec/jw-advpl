"""Testes da geração/correção de código com lint + guard (`gerar.py`).

Foco no GUARD determinístico (a rede de robustez) e no laço que devolve a melhor
tentativa. Unit mockam Ollama/lint; e2e tocam o plugadvpl real (auto-skip).
"""

from __future__ import annotations

import os
import shutil
import urllib.error
import urllib.request

import pytest

import gerar as g


# ==========================================================================
# unit — extrair_codigo
# ==========================================================================
class TestExtrairCodigo:
    def test_bloco_advpl(self) -> None:
        assert g.extrair_codigo("ola\n```advpl\nUser Function X()\n```\nfim") == "User Function X()"

    def test_sem_bloco_devolve_texto(self) -> None:
        assert g.extrair_codigo("Return .T.") == "Return .T."

    def test_bloco_generico(self) -> None:
        assert g.extrair_codigo("```\ncode\n```") == "code"


# ==========================================================================
# unit — guardrails (a rede de robustez)
# ==========================================================================
class TestGuardrails:
    def test_codigo_ok(self) -> None:
        assert g.guardrails("User Function XYZVal()\n  Return .T.") == []

    def test_proibe_then(self) -> None:
        assert any("Then" in p for p in g.guardrails("If x Then\n EndIf"))

    def test_proibe_endfunction(self) -> None:
        assert any("EndFunction" in p or "Return" in p for p in g.guardrails("Function X()\nEndFunction"))

    def test_proibe_function_isolada(self) -> None:
        assert any("User Function" in p for p in g.guardrails("Function Foo()\n Return"))

    def test_user_function_aceita(self) -> None:
        # 'User Function' não dispara a regra de 'Function isolada'
        probs = g.guardrails("User Function XYZVal()\n Return")
        assert not any("isolada" in p for p in probs)

    def test_limite_10_chars_prw_userfunc(self) -> None:
        # nome de 9 chars > 8 úteis -> flagra em .prw
        probs = g.guardrails("User Function XYZValClie()\n Return", ext=".prw")
        assert any("chars" in p for p in probs)

    def test_nome_curto_ok_prw(self) -> None:
        assert g.guardrails("User Function XYZVal()\n Return", ext=".prw") == []

    def test_tlpp_sem_limite_de_nome(self) -> None:
        # em .tlpp o limite de 10 NÃO se aplica
        codigo = "User Function NomeBemLongoQueEmPrwQuebraria()\n Return"
        assert g.guardrails(codigo, ext=".tlpp") == []

    def test_static_function_limite_10(self) -> None:
        assert any("10" in p for p in g.guardrails("Static Function NomeComMaisDe10()\n Return", ext=".prw"))

    def test_preserva_assinatura(self) -> None:
        original = "User Function ValidaCli(cCod)\n Return .T."
        renomeado = "User Function OutroNome(cCod)\n Return .T."
        assert any("renomeie" in p for p in g.guardrails(renomeado, original))

    def test_assinatura_preservada_ok(self) -> None:
        original = "User Function ValidaX(cCod)\n Return .T."
        corrigido = "User Function ValidaX(cCod)\n Local lOk := .T.\n Return lOk"
        assert not any("renomeie" in p for p in g.guardrails(corrigido, original))


# ==========================================================================
# unit — _feedback
# ==========================================================================
class TestFeedback:
    def test_inclui_lint_e_guard(self) -> None:
        fb = g._feedback([{"linha": 1, "regra_id": "BP-007", "severidade": "info", "sugestao_fix": "doc"}],
                         ["Remova 'Then'"])
        assert "BP-007" in fb and "Then" in fb


# ==========================================================================
# unit — laço devolve a MELHOR tentativa
# ==========================================================================
class TestMelhorTentativa:
    def test_retorna_iteracao_com_menos_problemas(self, monkeypatch) -> None:
        # 3 respostas: A(2 problemas) → B(1) → C(2). Nenhuma chega a 0. Melhor = B.
        respostas = iter(["```advpl\nA\n```", "```advpl\nB\n```", "```advpl\nC\n```"])
        monkeypatch.setattr(g, "_ollama", lambda m, mod: next(respostas))
        monkeypatch.setattr(g, "carregar_skill", lambda n: "SKILL")
        monkeypatch.setattr(g, "guardrails", lambda c, o=None, ext=".prw": [])
        finds = {"A": [{"regra_id": "a"}, {"regra_id": "b"}], "B": [{"regra_id": "c"}],
                 "C": [{"regra_id": "d"}, {"regra_id": "e"}]}
        monkeypatch.setattr(g, "lintar", lambda c, **k: finds[c])
        r = g.gerar_com_lint("tarefa", max_iter=3)
        assert r["codigo"] == "B"
        assert r["limpo"] is False

    def test_para_quando_limpo(self, monkeypatch) -> None:
        respostas = iter(["```advpl\nSUJO\n```", "```advpl\nLIMPO\n```"])
        monkeypatch.setattr(g, "_ollama", lambda m, mod: next(respostas))
        monkeypatch.setattr(g, "carregar_skill", lambda n: "SKILL")
        monkeypatch.setattr(g, "guardrails", lambda c, o=None, ext=".prw": [])
        monkeypatch.setattr(g, "lintar", lambda c, **k: [] if c == "LIMPO" else [{"regra_id": "x"}])
        r = g.gerar_com_lint("t", max_iter=5)
        assert r["codigo"] == "LIMPO" and r["limpo"] is True
        assert len(r["iteracoes"]) == 2  # parou ao limpar (não rodou as 5)


# ==========================================================================
# unit — corrigir_codigo
# ==========================================================================
class TestCorrigir:
    def test_ja_limpo_nao_chama_modelo(self, monkeypatch) -> None:
        monkeypatch.setattr(g, "lintar", lambda c, **k: [])
        monkeypatch.setattr(g, "guardrails", lambda c, o=None, ext=".prw": [])
        monkeypatch.setattr(g, "_ollama", lambda m, mod: pytest.fail("não devia chamar o modelo"))
        r = g.corrigir_codigo("User Function XY()\n Return")
        assert r["limpo"] and r["ja_estava_limpo"] is True

    def test_corrige_e_preserva(self, monkeypatch) -> None:
        # original sujo (BP-007); modelo devolve versão limpa preservando o nome
        monkeypatch.setattr(g, "carregar_skill", lambda n: "SKILL")
        monkeypatch.setattr(g, "_ollama", lambda m, mod: "```advpl\nUser Function XY()\n Return .T.\n```")
        chamadas = {"n": 0}

        def _lint(c, **k):
            chamadas["n"] += 1
            return [{"linha": 1, "regra_id": "BP-007", "severidade": "info", "sugestao_fix": "doc"}] \
                if chamadas["n"] == 1 else []

        monkeypatch.setattr(g, "lintar", _lint)
        r = g.corrigir_codigo("User Function XY()\n Return .T.")
        assert r["ja_estava_limpo"] is False and r["limpo"] is True


# ==========================================================================
# unit — diagnosticar / diff (fluxo dev-no-controle)
# ==========================================================================
class TestDiagnosticarEDiff:
    def test_diagnosticar_nao_chama_modelo(self, monkeypatch) -> None:
        monkeypatch.setattr(g, "lintar", lambda c, **k: [{"regra_id": "BP-007"}])
        monkeypatch.setattr(g, "_ollama", lambda m, mod: pytest.fail("diagnóstico não pode chamar o modelo"))
        diag = g.diagnosticar("User Function XY()\n Return")
        assert diag["lint"] == [{"regra_id": "BP-007"}]
        assert isinstance(diag["guard"], list)

    def test_diagnosticar_inclui_guard(self, monkeypatch) -> None:
        # 'Then' é problema de guard, não de lint
        monkeypatch.setattr(g, "lintar", lambda c, **k: [])
        diag = g.diagnosticar("If x Then\n EndIf")
        assert any("Then" in p for p in diag["guard"])

    def test_diff_mostra_antes_depois(self) -> None:
        d = g.diff_unificado("Local a := 1\n", "Local lA := 1\n", "X.prw")
        assert "-Local a := 1" in d and "+Local lA := 1" in d

    def test_diff_vazio_quando_igual(self) -> None:
        assert g.diff_unificado("igual\n", "igual\n") == ""


# ==========================================================================
# e2e — lint real do plugadvpl
# ==========================================================================
_HAS_PLUG = shutil.which("plugadvpl") is not None
requires_plug = pytest.mark.skipif(not _HAS_PLUG, reason="plugadvpl ausente")


def _ollama_up() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
    except (urllib.error.URLError, OSError):
        return False
    return True


@pytest.mark.e2e
@requires_plug
def test_e2e_lint_real_pega_violacao() -> None:
    # código sem header Protheus.doc -> lint real deve apontar BP-007
    findings = g.lintar("User Function ABCfn()\n    Return .T.\n", scratch="/tmp/gen_e2e_test")
    regras = {f.get("regra_id") for f in findings}
    assert "BP-007" in regras


@pytest.mark.e2e
@requires_plug
@pytest.mark.skipif(not _ollama_up(), reason="Ollama offline")
def test_e2e_gerar_produz_advpl_valido() -> None:
    # pipeline real: devolve código não-vazio e registra as iterações
    r = g.gerar_com_lint("Crie uma User Function XYZ que retorna .T.", max_iter=2)
    assert isinstance(r["codigo"], str) and len(r["codigo"]) > 0
    assert r["iteracoes"], "deveria registrar ao menos uma iteração"
