#!/usr/bin/env python3
"""Harness local — mapeia um processo ADVPL com receita determinística + narrativa por LLM local.

Princípio (a tese do projeto): a ACURÁCIA vem do plugadvpl (índice determinístico);
o modelo local (via Ollama) SÓ escreve o resumo em cima dos fatos já coletados.
Assim o resultado é correto e completo *independente* do modelo — um modelo fraco
pode escrever um texto mais simples, mas nunca inventa nem deixa incompleto, porque
quem orquestra é o código, não o modelo.

Uso:
    python3 harness_local.py <CODIGO> [--root <projeto>] [--modelo <nome>] [--privacy]

Requisitos: `plugadvpl` no PATH · Ollama em localhost:11434 · zero deps (só stdlib).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
TIMEOUT_CMD = 60       # segundos por comando plugadvpl
TIMEOUT_LLM = 180      # segundos pra resposta do modelo

SYSTEM = (
    "Você é um analista de código ADVPL/Protheus. Receberá FATOS já extraídos de "
    "um índice determinístico (não invente nada além deles). Escreva, em português, "
    "um resumo claro e curto do que a rotina faz: seu papel, as tabelas que lê/grava "
    "e como se conecta a outras. Se um dado vier vazio, apenas omita — não especule."
)


# --------------------------------------------------------------------------
# camada determinística — plugadvpl (a parte que NÃO depende do modelo)
# --------------------------------------------------------------------------
def run_plugadvpl(subcmd: str, args: list[str], root: str, *, privacy: bool = False) -> dict:
    """Roda um subcomando do plugadvpl em JSON e devolve o dict (ou erro estruturado)."""
    cmd = ["plugadvpl", "--format", "json", "--root", root, "--limit", "0"]
    if privacy:
        cmd.append("--privacy")
    cmd += [subcmd, *args]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT_CMD, check=False
        )
    except subprocess.TimeoutExpired:
        return {"_erro": f"timeout em '{subcmd}'", "rows": []}
    except FileNotFoundError:
        return {"_erro": "binário 'plugadvpl' não encontrado no PATH", "rows": []}
    saida = proc.stdout.strip()
    if not saida:
        return {"rows": [], "_stderr": proc.stderr.strip()[:200]}
    try:
        return json.loads(saida)
    except json.JSONDecodeError:
        return {"_erro": "JSON inválido", "rows": []}


def _label(row: dict) -> str:
    """Extrai um rótulo legível de uma linha de caller/callee (chaves variam)."""
    nome = row.get("destino") or row.get("funcao") or row.get("nome") or row.get("origem") or "?"
    arquivo = row.get("arquivo")
    linha = row.get("linha")
    sufixo = f" ({arquivo}:{linha})" if arquivo and linha else (f" :{linha}" if linha else "")
    return f"{nome}{sufixo}"


def localizar(codigo: str, root: str) -> tuple[str | None, str]:
    """`find` -> escolhe a melhor linha (função exata > primeira) -> (arquivo, função)."""
    d = run_plugadvpl("find", [codigo], root)
    rows = d.get("rows", [])
    if not rows:
        return None, codigo
    exato = [r for r in rows if str(r.get("funcao", "")).lower() == codigo.lower()]
    escolha = exato[0] if exato else rows[0]
    return escolha.get("arquivo"), escolha.get("funcao") or codigo


def mapear_processo(codigo: str, root: str, *, privacy: bool = False) -> dict:
    """RECEITA FIXA: junta os fatos determinísticos de um processo. Sem modelo aqui."""
    arquivo, funcao = localizar(codigo, root)
    if not arquivo:
        return {"encontrado": False, "codigo": codigo}

    arch = run_plugadvpl("arch", [arquivo], root, privacy=privacy)
    a = (arch.get("rows") or [{}])[0]
    callers = run_plugadvpl("callers", [funcao], root, privacy=privacy)
    callees = run_plugadvpl("callees", [funcao], root, privacy=privacy)

    return {
        "encontrado": True,
        "codigo": codigo,
        "funcao": funcao,
        "arquivo": arquivo,
        "tipo": a.get("source_type") or a.get("tipo_arquivo"),
        "capabilities": a.get("capabilities") or [],
        "loc": a.get("lines_of_code"),
        "tabelas_read": a.get("tabelas_read") or [],
        "tabelas_write": a.get("tabelas_write") or [],
        "includes": a.get("includes") or [],
        "callers": [_label(r) for r in callers.get("rows", [])],
        "callees": [_label(r) for r in callees.get("rows", [])],
    }


# --------------------------------------------------------------------------
# apresentação determinística — os FATOS (sempre exatos, qualquer modelo)
# --------------------------------------------------------------------------
def formatar_fatos(f: dict) -> str:
    """Bloco de fatos formatado por código (não passa pelo modelo)."""
    if not f.get("encontrado"):
        return f"❌ '{f['codigo']}' não encontrado no índice."

    def lista(xs: list, vazio: str = "—") -> str:
        return ", ".join(map(str, xs)) if xs else vazio

    return "\n".join(
        [
            f"📍 Processo: {f['funcao']}  —  fonte {f['arquivo']} ({f['tipo']}, {f['loc']} linhas)",
            f"   Capabilities: {lista(f['capabilities'])}",
            f"   Lê tabelas:   {lista(f['tabelas_read'])}",
            f"   Grava tabelas:{lista(f['tabelas_write'])}",
            f"   Includes:     {lista(f['includes'])}",
            f"   Chamado por:  {lista(f['callers'])}",
            f"   Chama:        {lista(f['callees'])}",
        ]
    )


# --------------------------------------------------------------------------
# camada do modelo — narrativa (a única parte que depende do modelo)
# --------------------------------------------------------------------------
def narrar(fatos: dict, modelo: str) -> str:
    """Pede ao modelo local UM resumo em cima dos fatos. Não orquestra, só narra."""
    # Rótulos EXPLÍCITOS em português: um modelo pequeno confunde callers/callees
    # em inglês. Desambiguar aqui melhora a narrativa sem tocar nos fatos.
    fatos_pt = {
        "nome_da_rotina": fatos.get("funcao"),
        "fonte": fatos.get("arquivo"),
        "tipo": fatos.get("tipo"),
        "linhas_de_codigo": fatos.get("loc"),
        "capabilities": fatos.get("capabilities"),
        "tabelas_lidas": fatos.get("tabelas_read"),
        "tabelas_gravadas": fatos.get("tabelas_write"),
        "includes": fatos.get("includes"),
        "quem_chama_esta_rotina": fatos.get("callers"),
        "o_que_esta_rotina_chama": fatos.get("callees"),
    }
    payload = {
        "model": modelo,
        "stream": False,
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "FATOS:\n" + json.dumps(fatos_pt, ensure_ascii=False, indent=2)},
        ],
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_LLM) as resp:
            data = json.loads(resp.read())
        return data.get("message", {}).get("content", "(resposta vazia)").strip()
    except urllib.error.URLError as e:
        return f"(modelo indisponível: {e})"


def main() -> int:
    ap = argparse.ArgumentParser(description="Mapeia um processo ADVPL (plugadvpl + LLM local).")
    ap.add_argument("codigo", help="função, fonte ou símbolo a mapear (ex.: U_ZDAEDI03)")
    ap.add_argument("--root", default=".", help="raiz do projeto ADVPL (com .plugadvpl/)")
    ap.add_argument("--modelo", default="qwen2.5:7b", help="modelo Ollama p/ a narrativa")
    ap.add_argument("--privacy", action="store_true", help="liga o mascaramento do plugadvpl")
    args = ap.parse_args()

    fatos = mapear_processo(args.codigo, args.root, privacy=args.privacy)
    print("=" * 70)
    print(formatar_fatos(fatos))                    # determinístico — sempre exato
    print("=" * 70)
    if fatos.get("encontrado"):
        print(f"\n🧠 Resumo ({args.modelo}):\n")
        print(narrar(fatos, args.modelo))           # narrativa do modelo
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
