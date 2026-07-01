#!/usr/bin/env python3
"""Harness ESPECIALISTA no plugadvpl — usa as ferramentas com maestria, sem inventar.

Sabe escolher o comando certo do plugadvpl para cada pergunta e fecha com uma
VERIFICAÇÃO determinística: extrai os símbolos da resposta e checa via
``verify-claims`` (tabela é closed-world → tabela inventada é flagrada).

Princípio: a inteligência de QUALIDADE vem das ferramentas determinísticas; o
modelo só orquestra e narra o que elas provam. Se o índice não prova, é "não consta".

Uso:  python3 harness_expert.py "<pergunta>" [--root ...] [--modelo ...]
Requisitos: plugadvpl no PATH · Ollama em localhost:11434 · zero deps (stdlib).
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request

from dossie import coletar_dossie, verificar_claims
from harness_local import OLLAMA_URL, TIMEOUT_LLM, run_plugadvpl

MAX_ITER = 8

# Catálogo de ferramentas read-only + QUANDO usar cada uma (a "expertise").
COMANDOS = {
    "find": "localiza função/arquivo/texto no índice — use pra achar ONDE algo está",
    "grep": "busca textual de um padrão/trecho no código",
    "arch": "estrutura de UM fonte (funções, tabelas lidas/gravadas, includes) — passe o ARQUIVO, ex.: X.prw",
    "callers": "quem CHAMA uma função (impacto / quem usa)",
    "callees": "o que uma função chama",
    "tables": "quem USA uma tabela T — busca reversa, ex.: tables SA1",
    "param": "quem usa um parâmetro MV_* (ex.: param MV_LJCONT)",
    "family": "família de fontes por prefixo (tipo, LoC, capabilities)",
    "semantica": "semântica/comportamento de um campo SX (ex.: A1_MSBLQL)",
    "lint": "achados de qualidade de um fonte (regras BP/SEC/PERF)",
}

SYSTEM = (
    "Você é um especialista no plugadvpl — um índice determinístico de código ADVPL/Protheus. "
    "Responda SEMPRE em português, fundamentando CADA afirmação na saída real das ferramentas. "
    "NUNCA invente função, tabela, campo ou parâmetro; se o índice não provar, diga 'não consta'. "
    "Escolha a ferramenta certa: para entender o que uma ROTINA faz, prefira `mapear_processo`; "
    "para consultas pontuais use `plugadvpl` com o comando adequado. Investigue antes de concluir e "
    "cite os nomes EXATOS retornados pelas ferramentas."
)

FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "mapear_processo",
            "description": ("Mapa completo de uma rotina: tipo, tabelas lidas/gravadas, funções, "
                            "quem a chama e o que ela chama. Use para 'o que a rotina X faz'."),
            "parameters": {"type": "object",
                           "properties": {"codigo": {"type": "string", "description": "nome da rotina/função"}},
                           "required": ["codigo"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plugadvpl",
            "description": "Consulta pontual no índice. Comandos disponíveis: "
                           + " | ".join(f"{k}: {v}" for k, v in COMANDOS.items()),
            "parameters": {"type": "object", "properties": {
                "comando": {"type": "string", "enum": sorted(COMANDOS)},
                "args": {"type": "string", "description": "argumentos (ex.: 'SA1', 'A1_MSBLQL', 'X.prw')"},
            }, "required": ["comando", "args"]},
        },
    },
]

_NAO_TABELA = frozenset({"MVC", "SQL", "API", "PDF", "CSV", "XML", "ERP", "RPC", "NF", "UF", "TLP", "SOA"})
_TOKEN_TABELA = re.compile(r"\b[A-Z][A-Z0-9]{2}\b")


def executar(nome: str, call_args: dict, root: str) -> str:
    """Despacha a ferramenta. Allowlist no `plugadvpl`; `mapear_processo` = dossiê determinístico."""
    if nome == "mapear_processo":
        cod = str(call_args.get("codigo", "")).strip()
        if not cod:
            return json.dumps({"_erro": "codigo vazio"}, ensure_ascii=False)
        return json.dumps(coletar_dossie(cod, root), ensure_ascii=False)[:6000]
    if nome == "plugadvpl":
        cmd = str(call_args.get("comando", "")).strip()
        args = str(call_args.get("args", "")).strip()
        if cmd not in COMANDOS:
            return json.dumps({"_erro": f"comando '{cmd}' não permitido"}, ensure_ascii=False)
        return json.dumps(run_plugadvpl(cmd, args.split() if args else [], root), ensure_ascii=False)[:6000]
    return json.dumps({"_erro": f"ferramenta '{nome}' desconhecida"}, ensure_ascii=False)


def auditar(texto: str, root: str) -> dict:
    """Verifica os tokens com cara de TABELA citados na resposta (closed-world).

    ``not_found`` numa tabela = símbolo que o índice prova NÃO existir → alucinação.
    """
    cand = sorted({t for t in _TOKEN_TABELA.findall(texto) if t not in _NAO_TABELA})
    if not cand:
        return {"tabelas_checadas": [], "alucinadas": []}
    res = verificar_claims([{"kind": "table", "symbol": t} for t in cand], root)
    aluc = [r["symbol"] for r in res if r.get("status") == "not_found"]
    return {"tabelas_checadas": cand, "alucinadas": aluc}


def _chat(messages: list[dict], modelo: str) -> dict:
    payload = {"model": modelo, "stream": False, "options": {"temperature": 0.0},
               "messages": messages, "tools": FERRAMENTAS}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_LLM) as resp:
            return json.loads(resp.read()).get("message", {})
    except urllib.error.URLError as e:
        return {"content": f"(modelo indisponível: {e})", "_erro": True}


def perguntar(pergunta: str, root: str, modelo: str = "qwen2.5:7b", max_iter: int = MAX_ITER) -> dict:
    """Loop especialista: escolhe ferramentas → responde grounded → audita a resposta."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": pergunta}]
    ferramentas_usadas: list[str] = []
    for _ in range(max_iter):
        msg = _chat(messages, modelo)
        messages.append(msg)
        if msg.get("_erro"):
            return {"resposta": msg.get("content", ""), "ferramentas": ferramentas_usadas,
                    "auditoria": {"tabelas_checadas": [], "alucinadas": []}}
        chamadas = msg.get("tool_calls")
        if not chamadas:
            resposta = msg.get("content", "").strip()
            return {"resposta": resposta, "ferramentas": ferramentas_usadas,
                    "auditoria": auditar(resposta, root)}
        for ch in chamadas:
            fn = ch.get("function", {})
            ferramentas_usadas.append(fn.get("name", "?"))
            messages.append({"role": "tool",
                             "content": executar(fn.get("name", ""), fn.get("arguments", {}), root)})
    return {"resposta": "Limite de iterações atingido — refine a pergunta.",
            "ferramentas": ferramentas_usadas, "auditoria": {"tabelas_checadas": [], "alucinadas": []}}


def main() -> int:
    ap = argparse.ArgumentParser(description="Harness especialista no plugadvpl (grounded + verificado).")
    ap.add_argument("pergunta")
    ap.add_argument("--root", default=".")
    ap.add_argument("--modelo", default="qwen2.5:7b")
    args = ap.parse_args()

    r = perguntar(args.pergunta, args.root, args.modelo)
    print(f"❓ {args.pergunta}\n")
    print(r["resposta"])
    print(f"\n🔧 ferramentas usadas: {', '.join(r['ferramentas']) or '—'}")
    au = r["auditoria"]
    if au["alucinadas"]:
        print(f"⚠ ALUCINAÇÃO: tabelas citadas que não existem: {', '.join(au['alucinadas'])}")
    elif au["tabelas_checadas"]:
        print(f"✅ {len(au['tabelas_checadas'])} tabela(s) citada(s) — todas confirmadas no índice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
