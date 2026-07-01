#!/usr/bin/env python3
"""Geração E correção de código ADVPL/TLPP, grounded em skill + verificada pelo plugadvpl.

Mesmo princípio do mapeamento (dossiê + verify-claims), agora para CÓDIGO: a qualidade
não vem da fé no modelo, vem de checagens determinísticas. Duas redes:

1. **Lint do plugadvpl** — regras BP/SEC/PERF/MOD (notação, doc, escopo, funções restritas).
2. **Guard de robustez** — sintaxe ADVPL inegociável (`If/EndIf`, `User Function`/`Return`,
   sem `Then`/`Function`/`EndFunction`) e, na correção, **preservação da assinatura**
   (não deixa o modelo renomear a função nem trocar os parâmetros).

Pipeline:  GERAR/CORRIGIR → LINT + GUARD → realimenta o modelo → repete até limpo ou teto.

Escopo honesto: "limpo" = passa no lint do plugadvpl + no guard de sintaxe. NÃO substitui
o compilador Protheus — é o portão de qualidade determinístico que o produto oferece.

Uso:  python3 gerar.py "<tarefa>"                      # gera código novo
      python3 gerar.py --corrigir <arq>                # só DIAGNOSTICA (dev decide)
      python3 gerar.py --corrigir <arq> --fix          # propõe a correção + DIFF (não grava)
      python3 gerar.py --corrigir <arq> --fix --write  # aplica no arquivo (explícito)

O dev está no controle: por padrão só lista os problemas; corrigir e gravar exigem
flags explícitas. Nada é alterado sem --write.
"""

from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import re
import subprocess
import urllib.request

from harness_local import OLLAMA_URL, TIMEOUT_LLM

REPO_SKILLS = "/opt/projetos/plugadvpl/skills"
SCRATCH = "/tmp/plugadvpl_gen"
ARQ_GEN = "GEN001.prw"
TIMEOUT_CMD = 120
MAX_ITER = 4

_FENCE = re.compile(r"```(?:advpl|tlpp|prw|x?base)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_RE_UFUNC = re.compile(r"(?i)\buser\s+function\s+(\w+)")
_RE_SFUNC = re.compile(r"(?i)\b(?:static|main)\s+function\s+(\w+)")
# .prw/.prx: compilador usa só os 10 primeiros chars do identificador.
# User Function: 'U_' consome 2 -> sobram 8 úteis no nome declarado.
_LIM_UFUNC_PRW = 8
_LIM_FUNC_PRW = 10

_REGRAS = (
    "REGRAS DE SINTAXE ADVPL (inegociáveis): 'User Function NOME()' ... 'Return' "
    "(NUNCA 'Function'/'EndFunction'); condicional 'If <cond>' ... 'EndIf' (NUNCA 'Then'); "
    "atribuição ':='; notação húngara (cCod/nVal/lOk/dData/aLista/oObj); mensagem com "
    "'MsgAlert'/'MsgInfo'; cabeçalho Protheus.doc; 'Local' no topo. Em .prw o nome da "
    "User Function tem no MÁXIMO 8 caracteres (o compilador só usa 10 chars e 'U_' consome 2)."
)

SYS_GERAR = (
    "Você é um gerador de código ADVPL/TLPP. Siga RIGOROSAMENTE as convenções da skill abaixo. "
    + _REGRAS + " Gere SÓ o código dentro de um bloco ```advpl, sem explicação.\n\n=== SKILL ===\n{skill}"
)

SYS_CORRIGIR = (
    "Você é um revisor de código ADVPL/TLPP. Corrija APENAS as violações apontadas, com o MÍNIMO "
    "de mudança. PROIBIDO renomear a função, alterar assinatura/parâmetros, mudar a lógica ou "
    "remover funcionalidade. " + _REGRAS
    + " Devolva SÓ o código corrigido dentro de um bloco ```advpl.\n\n=== SKILL ===\n{skill}"
)


def carregar_skill(nome: str, base: str = REPO_SKILLS) -> str:
    return (pathlib.Path(base) / nome / "SKILL.md").read_text(encoding="utf-8")


def extrair_codigo(texto: str) -> str:
    m = _FENCE.search(texto)
    return (m.group(1) if m else texto).strip()


def _ollama(messages: list[dict], modelo: str) -> str:
    payload = {"model": modelo, "stream": False, "options": {"temperature": 0.1}, "messages": messages}
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_LLM) as resp:
        return json.loads(resp.read()).get("message", {}).get("content", "")


def lintar(codigo: str, *, arquivo: str = ARQ_GEN, scratch: str = SCRATCH) -> list[dict]:
    """Grava o código (cp1252, encoding do .prw), indexa e roda o lint. Devolve findings."""
    d = pathlib.Path(scratch)
    d.mkdir(parents=True, exist_ok=True)
    (d / arquivo).write_text(codigo, encoding="cp1252", errors="replace")
    subprocess.run(["plugadvpl", "--root", str(d), "--quiet", "ingest"],
                   capture_output=True, text=True, timeout=TIMEOUT_CMD, check=False)
    proc = subprocess.run(["plugadvpl", "-f", "json", "--root", str(d), "lint", arquivo],
                          capture_output=True, text=True, timeout=TIMEOUT_CMD, check=False)
    try:
        return json.loads(proc.stdout).get("rows", [])
    except json.JSONDecodeError:
        return []


def guardrails(codigo: str, original: str | None = None, *, ext: str = ".prw") -> list[str]:
    """Checagens determinísticas de sintaxe/robustez que o lint não cobre.

    Sempre: proíbe 'Then', 'Function'/'EndFunction' isoladas (ADVPL usa User Function/Return).
    Em ``.prw``/``.prx``: aplica o **limite de 10 chars** do identificador (8 úteis na
    User Function, por causa do prefixo ``U_``). Em ``.tlpp`` esse limite NÃO existe.
    Com ``original``: exige que o nome da ``User Function`` seja preservado (anti-renome).
    """
    problemas: list[str] = []
    if re.search(r"(?i)\bthen\b", codigo):
        problemas.append("Remova 'Then' — em ADVPL é 'If <cond>' ... 'EndIf' (sem 'Then').")
    if re.search(r"(?i)\bendfunction\b", codigo):
        problemas.append("Use 'Return' no fim — não existe 'EndFunction' em ADVPL.")
    for ln in codigo.splitlines():
        tem_function = re.search(r"(?i)\bfunction\b", ln)
        ok_prefixado = re.search(r"(?i)\b(user|static|main|web)\s+function\b", ln)
        if tem_function and not ok_prefixado and not re.search(r"(?i)\b(endfunction|class)\b", ln):
            problemas.append("Declare como 'User Function' (não 'Function' isolada).")
            break

    # Limite de 10 chars — só ADVPL clássico (.prw/.prx); .tlpp não tem.
    if ext.lower() in (".prw", ".prx"):
        for nome in _RE_UFUNC.findall(codigo):
            if len(nome) > _LIM_UFUNC_PRW:
                problemas.append(
                    f"Nome '{nome}' tem {len(nome)} chars: em .prw a User Function deve ter "
                    f"≤ {_LIM_UFUNC_PRW} (o prefixo 'U_' + 10 do compilador). Encurte.")
                break
        for nome in _RE_SFUNC.findall(codigo):
            if len(nome) > _LIM_FUNC_PRW:
                problemas.append(
                    f"Nome '{nome}' tem {len(nome)} chars: em .prw o limite é {_LIM_FUNC_PRW}. Encurte.")
                break

    if original:
        m = _RE_UFUNC.search(original)
        if m and not re.search(r"(?i)\buser\s+function\s+" + re.escape(m.group(1)) + r"\b", codigo):
            problemas.append(f"NÃO renomeie a função: mantenha 'User Function {m.group(1)}'.")
    return problemas


def _feedback(findings: list[dict], guard: list[str]) -> str:
    partes = []
    if findings:
        partes.append("Violações do lint:\n" + "\n".join(
            f"- linha {f.get('linha')} [{f.get('regra_id')}/{f.get('severidade')}]: {f.get('sugestao_fix')}"
            for f in findings))
    if guard:
        partes.append("Problemas de sintaxe/robustez:\n" + "\n".join(f"- {g}" for g in guard))
    return ("Corrija TODOS os pontos abaixo e devolva só o código em ```advpl:\n\n"
            + "\n\n".join(partes))


def _resolver(messages: list[dict], modelo: str, max_iter: int,
              original: str | None, historico: list[dict]) -> tuple[str, list[dict], list[str]]:
    """Laço comum: gera/corrige → lint + guard → realimenta até limpo ou teto.

    Robustez: um modelo pequeno pode OSCILAR (consertar A e quebrar B). Por isso
    guardamos a MELHOR tentativa (menos problemas) e a devolvemos no fim — nunca uma
    iteração pior que outra já vista.
    """
    melhor: tuple[int, str, list[dict], list[str]] | None = None
    for _ in range(max_iter):
        resposta = _ollama(messages, modelo)
        codigo = extrair_codigo(resposta)
        findings = lintar(codigo)
        guard = guardrails(codigo, original)
        historico.append({"iteracao": len(historico),
                           "lint": [f.get("regra_id") for f in findings], "guard": guard})
        n = len(findings) + len(guard)
        if melhor is None or n < melhor[0]:
            melhor = (n, codigo, findings, guard)
        if n == 0:
            break
        messages += [{"role": "assistant", "content": resposta},
                     {"role": "user", "content": _feedback(findings, guard)}]
    return melhor[1], melhor[2], melhor[3]


def gerar_com_lint(tarefa: str, skill_nome: str = "advpl-fundamentals",
                   modelo: str = "qwen2.5-coder:7b", max_iter: int = MAX_ITER) -> dict:
    """Gera código novo e itera até passar no lint + guard."""
    messages = [{"role": "system", "content": SYS_GERAR.format(skill=carregar_skill(skill_nome))},
                {"role": "user", "content": tarefa}]
    historico: list[dict] = []
    codigo, findings, guard = _resolver(messages, modelo, max_iter, None, historico)
    return {"codigo": codigo, "limpo": not findings and not guard,
            "findings_finais": findings, "guard_finais": guard, "iteracoes": historico}


def corrigir_codigo(codigo: str, skill_nome: str = "advpl-fundamentals",
                    modelo: str = "qwen2.5-coder:7b", max_iter: int = MAX_ITER) -> dict:
    """Corrige código EXISTENTE preservando assinatura/comportamento. Não toca no que já está limpo."""
    findings = lintar(codigo)
    guard = guardrails(codigo)  # sem original: só sintaxe (o existente é a baseline)
    historico = [{"iteracao": 0, "lint": [f.get("regra_id") for f in findings], "guard": guard}]
    if not findings and not guard:
        return {"codigo": codigo, "limpo": True, "findings_finais": [], "guard_finais": [],
                "iteracoes": historico, "ja_estava_limpo": True}

    original = codigo
    messages = [
        {"role": "system", "content": SYS_CORRIGIR.format(skill=carregar_skill(skill_nome))},
        {"role": "user", "content":
            "Corrija o código ADVPL existente abaixo, preservando assinatura e comportamento.\n\n"
            f"CÓDIGO:\n```advpl\n{codigo}\n```\n\n" + _feedback(findings, guard)},
    ]
    codigo, findings, guard = _resolver(messages, modelo, max_iter, original, historico)
    return {"codigo": codigo, "limpo": not findings and not guard, "findings_finais": findings,
            "guard_finais": guard, "iteracoes": historico, "ja_estava_limpo": False}


def diagnosticar(codigo: str, *, ext: str = ".prw") -> dict:
    """Só DIAGNOSTICA: findings do lint + guard. NÃO chama o modelo, NÃO altera nada.

    É o passo que o dev vê ANTES de qualquer correção — quem decide é ele.
    """
    return {"lint": lintar(codigo), "guard": guardrails(codigo, ext=ext)}


def diff_unificado(original: str, novo: str, arquivo: str = "arquivo.prw") -> str:
    """Diff unificado (antes × depois) para o dev revisar antes de aplicar."""
    return "".join(difflib.unified_diff(
        original.splitlines(keepends=True), novo.splitlines(keepends=True),
        fromfile=f"a/{arquivo}", tofile=f"b/{arquivo}"))


def _print_diag(diag: dict) -> int:
    for f in diag["lint"]:
        print(f"  • linha {f.get('linha')} [{f.get('regra_id')}/{f.get('severidade')}] "
              f"{str(f.get('sugestao_fix', ''))[:90]}")
    for g in diag["guard"]:
        print(f"  • [guard] {g}")
    return len(diag["lint"]) + len(diag["guard"])


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera/corrige código ADVPL grounded em skill + verificado.")
    ap.add_argument("tarefa", nargs="?", help="descrição da tarefa (modo gerar)")
    ap.add_argument("--corrigir", metavar="ARQ", help="diagnostica um .prw existente (corrige só com --fix)")
    ap.add_argument("--fix", action="store_true", help="gera a correção e mostra o DIFF (sem isto, só diagnostica)")
    ap.add_argument("--write", action="store_true", help="grava a correção no arquivo (requer --fix)")
    ap.add_argument("--skill", default="advpl-fundamentals")
    ap.add_argument("--modelo", default="qwen2.5-coder:7b")
    ap.add_argument("--max-iter", type=int, default=MAX_ITER)
    args = ap.parse_args()

    # ---- modo CORRIGIR: dev no controle (diagnosticar → --fix diff → --write grava) ----
    if args.corrigir:
        arq = args.corrigir
        codigo = pathlib.Path(arq).read_text(encoding="cp1252", errors="replace")
        diag = diagnosticar(codigo)
        print(f"🔎 Diagnóstico de {pathlib.Path(arq).name}:")
        n = _print_diag(diag)
        if n == 0:
            print("✅ nada a corrigir — já passa no lint + guard.")
            return 0
        if not args.fix:
            print(f"\n{n} ponto(s). Diagnóstico apenas — rode com --fix para PROPOR a correção (com diff).")
            return 0
        r = corrigir_codigo(codigo, args.skill, args.modelo, args.max_iter)
        print("\n=== DIFF proposto (antes × depois) ===")
        print(diff_unificado(codigo, r["codigo"], pathlib.Path(arq).name) or "(sem mudança)")
        print("✅ proposta lint+guard-limpa" if r["limpo"]
              else f"⚠ resíduo na proposta: {len(r['findings_finais'])} lint + {len(r['guard_finais'])} guard")
        if args.write:
            pathlib.Path(arq).write_text(r["codigo"], encoding="cp1252", errors="replace")
            print(f"✏  gravado em {arq}")
        else:
            print("(prévia — nada gravado. Rode com --write para aplicar no arquivo.)")
        return 0

    # ---- modo GERAR ----
    if not args.tarefa:
        ap.error("informe a tarefa (gerar) ou use --corrigir <arquivo>")
    r = gerar_com_lint(args.tarefa, args.skill, args.modelo, args.max_iter)
    print("=" * 68)
    for it in r["iteracoes"]:
        lint = ", ".join(it["lint"]) or "—"
        guard = f" | guard: {len(it['guard'])}" if it["guard"] else ""
        print(f"  iteração {it['iteracao']}: lint [{lint}]{guard}")
    print("=" * 68)
    print(r["codigo"])
    print("=" * 68)
    print("✅ limpo (lint + guard)" if r["limpo"]
          else f"⚠ resíduo: {len(r['findings_finais'])} lint + {len(r['guard_finais'])} guard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
