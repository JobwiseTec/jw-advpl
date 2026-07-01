#!/usr/bin/env python3
"""Mapa COMPLETO de uma rotina ADVPL — dossiê do .db + narração grounded + verificação.

Objetivo: aproximar o harness LOCAL da qualidade do harness de nuvem, atacando a
alucinação por dois lados:

1. **Completude (grounding):** o dossiê reúne *tudo* que o índice sabe da rotina —
   identidade, todas as funções, tabelas lidas/gravadas, grafo de chamadas e o que
   cada função interna chama. Sem lacuna, o modelo não precisa inventar.
2. **Verificação:** cada símbolo é checado contra o índice via ``verify-claims``.
   Tabela é *closed-world* → se o modelo citar uma que não existe, é flagrada.

Pipeline:  RECUPERAR (dossiê) → NARRAR (grounded) → VERIFICAR (verify-claims)

Uso:  python3 dossie.py <CODIGO> [--root ...] [--modelo ...]
Requisitos: plugadvpl no PATH · Ollama em localhost:11434 · zero deps (stdlib).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.error
import urllib.request

from harness_local import OLLAMA_URL, TIMEOUT_LLM, _label, run_plugadvpl

MAX_FUNCS_DETALHE = 10   # nº de user functions cujo "o que chama" é detalhado
TIMEOUT_CMD = 90

SYSTEM_DOSSIE = (
    "Você é um analista de código ADVPL/Protheus. Recebe um DOSSIÊ extraído de um "
    "índice determinístico do código-fonte. Escreva, em português, um MAPA COMPLETO "
    "do funcionamento da rotina, organizado em seções: 1) Identidade, 2) Estrutura "
    "(funções), 3) Dados (tabelas lidas e gravadas), 4) Integração (quem a chama e o "
    "que ela chama). REGRAS ABSOLUTAS: (a) use SOMENTE o que está no dossiê; (b) NÃO "
    "infira o domínio de negócio nem o que cada tabela armazena se isso não estiver no "
    "dossiê; (c) se algo não constar, escreva 'não consta no índice'; (d) cite os nomes "
    "EXATOS de funções e tabelas. Seja completo e organizado — não resuma."
)

# Tokens de 3 letras que parecem tabela mas são siglas comuns na prosa (não verificar).
_NAO_TABELA = frozenset(
    {"MVC", "SQL", "API", "PDF", "CSV", "XML", "ADV", "TLP", "ERP", "RPC", "REST", "SOA"}
)
_TOKEN_TABELA = re.compile(r"\b[A-Z][A-Z0-9]{2}\b")


def _dedupe(seq: list) -> list:
    """Remove duplicatas preservando ordem; descarta vazios."""
    return list(dict.fromkeys(x for x in seq if x))


# --------------------------------------------------------------------------
# RECUPERAR — monta o dossiê completo a partir do índice (.db)
# --------------------------------------------------------------------------
def coletar_dossie(codigo: str, root: str, *, max_funcs: int = MAX_FUNCS_DETALHE) -> dict:
    """Reúne TUDO que o índice sabe da rotina ``codigo``. 100% determinístico."""
    achados = run_plugadvpl("find", [codigo], root).get("rows", [])
    if not achados:
        return {"encontrado": False, "codigo": codigo}
    exato = [r for r in achados if str(r.get("funcao", "")).lower() == codigo.lower()]
    esc = exato[0] if exato else achados[0]
    arquivo = esc.get("arquivo")
    funcao = esc.get("funcao") or codigo

    a = (run_plugadvpl("arch", [arquivo], root).get("rows") or [{}])[0]
    callers = run_plugadvpl("callers", [funcao], root).get("rows", [])
    callees = run_plugadvpl("callees", [funcao], root).get("rows", [])
    user_funcs = a.get("user_funcs") or []

    # Detalhe por função: o que cada user function interna chama (completude real).
    detalhe = []
    for uf in user_funcs[:max_funcs]:
        ce = run_plugadvpl("callees", [uf], root).get("rows", [])
        chama = _dedupe([r.get("destino") or r.get("funcao") for r in ce])[:12]
        detalhe.append({"funcao": uf, "chama": chama})

    return {
        "encontrado": True,
        "codigo": codigo,
        "funcao": funcao,
        "arquivo": arquivo,
        "identidade": {
            "tipo": a.get("source_type") or a.get("tipo_arquivo"),
            "loc": a.get("lines_of_code"),
            "namespace": a.get("namespace"),
            "capabilities": a.get("capabilities") or [],
            "includes": a.get("includes") or [],
        },
        "funcoes": {
            "user_funcs": user_funcs,
            "total_funcoes": len(a.get("funcoes") or []),
            "pontos_entrada": a.get("pontos_entrada") or [],
        },
        "tabelas": {
            "read": a.get("tabelas_read") or [],
            "write": a.get("tabelas_write") or [],
            "reclock": a.get("tabelas_reclock") or [],
            "via_execauto": a.get("tabelas_via_execauto_resolvidas") or [],
        },
        "grafo": {
            "callers": [_label(r) for r in callers],
            "callees": [_label(r) for r in callees],
        },
        "detalhe_funcoes": detalhe,
        "_funcs_detalhadas": min(len(user_funcs), max_funcs),
        "_funcs_total": len(user_funcs),
    }


# --------------------------------------------------------------------------
# VERIFICAR — checa símbolos contra o índice (anti-alucinação)
# --------------------------------------------------------------------------
def verificar_claims(claims: list[dict], root: str) -> list[dict]:
    """Roda ``verify-claims --stdin`` em lote e devolve os ``results``."""
    if not claims:
        return []
    try:
        proc = subprocess.run(
            ["plugadvpl", "-f", "json", "--root", root, "verify-claims", "--stdin"],
            input=json.dumps({"claims": claims}),
            capture_output=True, text=True, timeout=TIMEOUT_CMD, check=False,
        )
        return json.loads(proc.stdout).get("results", [])
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def verificar_dossie(dossie: dict, root: str) -> dict:
    """Confirma os símbolos do dossiê contra o índice, separando dois casos:

    - ``funcoes_not_found``: função da rotina ausente no índice → seria grave.
    - ``tabelas_fora_corpus``: tabela referenciada no CÓDIGO (vista pelo ``arch``)
      mas sem entrada no dicionário SX2 indexado → é **cobertura**, não erro.
    """
    funcs = _dedupe([dossie["funcao"], *dossie["funcoes"]["user_funcs"]])
    tabs = _dedupe(dossie["tabelas"]["read"] + dossie["tabelas"]["write"])
    claims = (
        [{"kind": "function", "symbol": f} for f in funcs]
        + [{"kind": "table", "symbol": t} for t in tabs]
    )
    res = verificar_claims(claims, root)
    status = {(r.get("kind"), r.get("symbol")): r.get("status") for r in res}
    funcoes_nf = [f for f in funcs if status.get(("function", f)) == "not_found"]
    tabelas_fora = [t for t in tabs if status.get(("table", t)) == "not_found"]
    exists = sum(1 for r in res if r.get("status") in ("exists", "relation_holds"))
    return {
        "total": len(res),
        "exists": exists,
        "funcoes_not_found": funcoes_nf,
        "tabelas_fora_corpus": tabelas_fora,
    }


def auditar_narrativa(texto: str, dossie: dict, root: str) -> dict:
    """Procura tabelas citadas na narrativa que NÃO estão no dossiê e verifica.

    Tabela é closed-world no ``verify-claims`` → ``not_found`` = inventada pelo modelo.
    """
    conhecidas = (
        set(dossie["tabelas"]["read"])
        | set(dossie["tabelas"]["write"])
        | set(dossie["tabelas"]["via_execauto"])
    )
    cand = sorted(
        {t for t in _TOKEN_TABELA.findall(texto) if t not in _NAO_TABELA and t not in conhecidas}
    )
    if not cand:
        return {"suspeitos": [], "alucinados": []}
    res = verificar_claims([{"kind": "table", "symbol": t} for t in cand], root)
    alucinados = [r["symbol"] for r in res if r.get("status") == "not_found"]
    return {"suspeitos": cand, "alucinados": alucinados}


# --------------------------------------------------------------------------
# NARRAR — modelo descreve o dossiê (grounded)
# --------------------------------------------------------------------------
def narrar_dossie(dossie: dict, modelo: str) -> str:
    """Pede ao modelo um mapa completo, restrito ao dossiê."""
    payload = {
        "model": modelo,
        "stream": False,
        "options": {"temperature": 0.1},
        "messages": [
            {"role": "system", "content": SYSTEM_DOSSIE},
            {"role": "user",
             "content": "DOSSIÊ (extraído do índice):\n" + json.dumps(dossie, ensure_ascii=False, indent=2)},
        ],
    }
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_LLM) as resp:
            return json.loads(resp.read()).get("message", {}).get("content", "").strip()
    except urllib.error.URLError as e:
        return f"(modelo indisponível: {e})"


def mapear_completo(codigo: str, root: str, modelo: str = "qwen2.5:7b") -> dict:
    """Pipeline inteiro: dossiê → narração grounded → verificação."""
    dossie = coletar_dossie(codigo, root)
    if not dossie.get("encontrado"):
        return {"encontrado": False, "codigo": codigo}
    verif = verificar_dossie(dossie, root)
    narrativa = narrar_dossie(dossie, modelo)
    auditoria = auditar_narrativa(narrativa, dossie, root)
    return {
        "encontrado": True,
        "dossie": dossie,
        "narrativa": narrativa,
        "verificacao_dossie": verif,
        "auditoria_narrativa": auditoria,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Mapa completo de uma rotina (dossiê + grounded + verify).")
    ap.add_argument("codigo")
    ap.add_argument("--root", default=".")
    ap.add_argument("--modelo", default="qwen2.5:7b")
    ap.add_argument("--json", action="store_true", help="imprime o resultado bruto em JSON")
    args = ap.parse_args()

    r = mapear_completo(args.codigo, args.root, args.modelo)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    if not r.get("encontrado"):
        print(f"❌ '{args.codigo}' não encontrado.")
        return 1
    d, v, au = r["dossie"], r["verificacao_dossie"], r["auditoria_narrativa"]
    print(f"📍 {d['funcao']} — {d['arquivo']} ({d['identidade']['tipo']}, {d['identidade']['loc']} linhas)")
    print(f"   funções: {d['_funcs_total']} user (detalhadas {d['_funcs_detalhadas']}) | "
          f"tabelas: {len(d['tabelas']['read'])} lidas, {len(d['tabelas']['write'])} gravadas")
    print(f"\n🧠 Mapa ({args.modelo}):\n{r['narrativa']}")
    print(f"\n🔒 Verificação: {v['exists']}/{v['total']} símbolos confirmados no índice")
    if v["funcoes_not_found"]:
        print(f"   ⚠ funções não encontradas: {', '.join(v['funcoes_not_found'])}")
    if v["tabelas_fora_corpus"]:
        print(f"   ℹ tabelas no código sem dicionário SX2 (cobertura, não erro): "
              f"{', '.join(v['tabelas_fora_corpus'])}")
    if au["alucinados"]:
        print(f"⚠ ALUCINAÇÃO: tabelas citadas que NÃO existem: {', '.join(au['alucinados'])}")
    else:
        print("✅ Nenhuma tabela inventada na narrativa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
