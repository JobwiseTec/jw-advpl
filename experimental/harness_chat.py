#!/usr/bin/env python3
"""Harness local — modo PERGUNTA LIVRE (tool-calling) sobre o plugadvpl.

Diferente de ``harness_local.mapear_processo`` (receita FIXA), aqui o modelo
*orquestra* as consultas: ele decide quais comandos rodar para responder uma
pergunta aberta ("qual o impacto de mudar X?", "quem grava na SA1?").

Segurança por desenho:
- **Allowlist** de subcomandos read-only — o modelo nunca roda shell arbitrário.
- Sem ``shell=True``; comando montado como lista (ver ``harness_local.run_plugadvpl``).
- Teto de iterações para um modelo pequeno não entrar em loop.

Uso:  python3 harness_chat.py "qual o impacto de mudar NOMEFUNC?" [--root ...] [--modelo ...]
Requisitos: plugadvpl no PATH · Ollama em localhost:11434 · zero deps (stdlib).
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

from harness_local import OLLAMA_URL, TIMEOUT_LLM, mapear_processo, run_plugadvpl

# Só subcomandos de LEITURA. Nada fora daqui é executado.
COMANDOS_PERMITIDOS = frozenset(
    {"find", "grep", "arch", "callers", "callees", "tables", "param", "family"}
)
MAX_ITER = 6

SYSTEM = (
    "Você é um analista de código ADVPL/Protheus. Responda SEMPRE em português. "
    "Investigue com as ferramentas antes de afirmar — nunca invente símbolos, "
    "funções ou tabelas. Para entender o que uma rotina FAZ (seu tipo, as tabelas "
    "que lê/grava, quem a chama e o que ela chama), prefira `mapear_processo(codigo)` "
    "— ela já reúne tudo de forma confiável. Use `plugadvpl` apenas para buscas "
    "pontuais: quem USA uma tabela (tables), quem usa um parâmetro MV_* (param), "
    "ou uma busca textual (find). Fundamente cada conclusão na saída real; se o "
    "índice não provar, diga 'não encontrado'. Com evidência suficiente, responda direto."
)

FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "mapear_processo",
            "description": (
                "Mapeia uma rotina/função ADVPL e retorna tudo de uma vez: tipo do "
                "fonte, tabelas LIDAS, tabelas GRAVADAS, includes, quem chama e o que "
                "ela chama. USE ISTO para entender o que uma rotina faz."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {"type": "string", "description": "nome da função/rotina, ex.: NOMEFUNC"},
                },
                "required": ["codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plugadvpl",
            "description": (
                "Consulta pontual no índice. comando: find (busca por nome/texto), "
                "tables (quem USA a tabela T, ex.: tables SA1), param (quem usa MV_*), "
                "family (família por prefixo), callers/callees (grafo), arch (estrutura "
                "de um fonte pelo nome do ARQUIVO, ex.: arch NOMEFUNC.prw)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {"type": "string", "enum": sorted(COMANDOS_PERMITIDOS)},
                    "args": {"type": "string", "description": "argumentos, ex.: 'SA1' ou 'NOMEFUNC.prw'"},
                },
                "required": ["comando", "args"],
            },
        },
    },
]


def executa_ferramenta(nome: str, call_args: dict, root: str) -> str:
    """Despacha a ferramenta pedida pelo modelo. Allowlist no `plugadvpl`."""
    if nome == "mapear_processo":
        codigo = str(call_args.get("codigo", "")).strip()
        if not codigo:
            return json.dumps({"_erro": "codigo vazio"}, ensure_ascii=False)
        return json.dumps(mapear_processo(codigo, root), ensure_ascii=False)[:6000]
    if nome == "plugadvpl":
        comando = str(call_args.get("comando", "")).strip()
        args = str(call_args.get("args", "")).strip()
        if comando not in COMANDOS_PERMITIDOS:
            return json.dumps({"_erro": f"comando '{comando}' não permitido"}, ensure_ascii=False)
        resultado = run_plugadvpl(comando, args.split() if args else [], root)
        return json.dumps(resultado, ensure_ascii=False)[:6000]
    return json.dumps({"_erro": f"ferramenta '{nome}' desconhecida"}, ensure_ascii=False)


def _chamar_ollama(messages: list[dict], modelo: str) -> dict:
    """Uma rodada de chat com tools. Devolve a mensagem do assistente (ou erro)."""
    payload = {
        "model": modelo,
        "stream": False,
        "options": {"temperature": 0.0},
        "messages": messages,
        "tools": FERRAMENTAS,
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_LLM) as resp:
            return json.loads(resp.read()).get("message", {})
    except urllib.error.URLError as e:
        return {"content": f"(modelo indisponível: {e})", "_erro": True}


def perguntar(pergunta: str, root: str, modelo: str = "qwen2.5:7b") -> str:
    """Loop de tool-calling: pergunta -> ferramentas -> resposta fundamentada."""
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": pergunta},
    ]
    for _ in range(MAX_ITER):
        msg = _chamar_ollama(messages, modelo)
        messages.append(msg)
        if msg.get("_erro"):
            return msg.get("content", "(erro)")
        chamadas = msg.get("tool_calls")
        if not chamadas:
            return msg.get("content", "(resposta vazia)").strip()
        for ch in chamadas:
            fn = ch.get("function", {})
            resultado = executa_ferramenta(fn.get("name", ""), fn.get("arguments", {}), root)
            messages.append({"role": "tool", "content": resultado})
    return "Limite de iterações atingido — refine a pergunta."


def main() -> int:
    ap = argparse.ArgumentParser(description="Pergunta livre sobre código ADVPL (plugadvpl + LLM local).")
    ap.add_argument("pergunta", help="pergunta em linguagem natural")
    ap.add_argument("--root", default=".", help="raiz do projeto ADVPL (com .plugadvpl/)")
    ap.add_argument("--modelo", default="qwen2.5:7b", help="modelo Ollama")
    args = ap.parse_args()

    print(f"❓ {args.pergunta}\n")
    print(perguntar(args.pergunta, args.root, args.modelo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
