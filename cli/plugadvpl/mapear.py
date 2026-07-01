"""Comando `mapear` — dossiê determinístico de uma rotina ADVPL + verificação.

Productiza a "receita determinística" do PoC de harness local (issue #173): em
vez de o modelo orquestrar `find -> arch -> callers -> callees` (frágil num LLM
pequeno), o *código* reúne tudo que o índice sabe da rotina e verifica cada
símbolo via ``verify-claims``. 100% determinístico, SEM LLM — serve de
fonte-de-verdade pra QUALQUER agente (Claude/Codex/Copilot/Gemini ou local).

A inteligência mora no índice; aqui não há narração nem inferência de domínio.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .query import arch, callees, callers, find_function
from .verify import verify_claims

if TYPE_CHECKING:
    import sqlite3
    from typing import Any

MAX_FUNCS_DETALHE = 10


def _dedupe(seq: list[Any]) -> list[Any]:
    """Remove duplicatas preservando ordem; descarta vazios/None."""
    return list(dict.fromkeys(x for x in seq if x))


def _label(row: dict[str, Any]) -> str:
    """Rótulo legível de uma linha de caller/callee (chaves variam por origem)."""
    nome = row.get("destino") or row.get("funcao") or row.get("nome") or row.get("origem") or "?"
    arquivo = row.get("arquivo")
    linha = row.get("linha")
    if arquivo and linha:
        return f"{nome} ({arquivo}:{linha})"
    return f"{nome} :{linha}" if linha else str(nome)


def _resolver(conn: sqlite3.Connection, codigo: str) -> tuple[str | None, str]:
    """`find_function` -> escolhe (match exato da função > primeiro) -> (arquivo, funcao)."""
    hits = find_function(conn, codigo)
    if not hits:
        return None, codigo
    exato = [h for h in hits if str(h.get("funcao", "")).lower() == codigo.lower()]
    esc = exato[0] if exato else hits[0]
    return esc.get("arquivo"), esc.get("funcao") or codigo


def coletar_dossie(
    conn: sqlite3.Connection,
    codigo: str,
    *,
    detalhe: bool = False,
    max_funcs: int = MAX_FUNCS_DETALHE,
) -> dict[str, Any]:
    """Reúne TUDO que o índice sabe da rotina ``codigo``. 100% determinístico."""
    arquivo, funcao = _resolver(conn, codigo)
    if not arquivo:
        return {"encontrado": False, "codigo": codigo}

    a = (arch(conn, arquivo) or [{}])[0]
    user_funcs = a.get("user_funcs") or []

    detalhe_funcoes: list[dict[str, Any]] = []
    if detalhe:
        for uf in user_funcs[:max_funcs]:
            chama = _dedupe([r.get("destino") or r.get("funcao") for r in callees(conn, uf)])[:12]
            detalhe_funcoes.append({"funcao": uf, "chama": chama})

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
            "callers": [_label(r) for r in callers(conn, funcao)],
            "callees": [_label(r) for r in callees(conn, funcao)],
        },
        "detalhe_funcoes": detalhe_funcoes,
    }


def verificar_dossie(conn: sqlite3.Connection, dossie: dict[str, Any]) -> dict[str, Any]:
    """Confirma os símbolos do dossiê contra o índice, separando dois casos:

    - ``funcoes_not_found``: função da rotina ausente do índice -> grave.
    - ``tabelas_fora_corpus``: tabela referenciada no CÓDIGO (vista pelo ``arch``)
      mas sem entrada no SX2 indexado -> **cobertura**, não erro (o ``arch`` vê
      a tabela no fonte; o ``verify-claims`` checa o dicionário — podem divergir).

    ``sx2_ingerido`` indica se há SX2 indexado (do contrário a ausência de
    tabela é só falta de dado dicionário, não dívida de cobertura).
    """
    funcs = _dedupe([dossie["funcao"], *dossie["funcoes"]["user_funcs"]])
    tabs = _dedupe(dossie["tabelas"]["read"] + dossie["tabelas"]["write"])
    claims = [{"id": f"fn:{f}", "kind": "function", "symbol": f} for f in funcs] + [
        {"id": f"tb:{t}", "kind": "table", "symbol": t} for t in tabs
    ]
    verdict = verify_claims(conn, claims)
    status = {(r["kind"], r["symbol"]): r["status"] for r in verdict["results"]}
    complete = set(verdict["coverage"]["complete_kinds"])
    return {
        "total": len(verdict["results"]),
        "exists": sum(1 for r in verdict["results"] if r["status"] in ("exists", "relation_holds")),
        "funcoes_not_found": [f for f in funcs if status.get(("function", f)) == "not_found"],
        "tabelas_fora_corpus": [t for t in tabs if status.get(("table", t)) == "not_found"],
        "sx2_ingerido": "table" in complete,
    }


def mapear(conn: sqlite3.Connection, codigo: str, *, detalhe: bool = False) -> dict[str, Any]:
    """Pipeline determinístico: dossiê -> verificação. Sem modelo, sem narração."""
    dossie = coletar_dossie(conn, codigo, detalhe=detalhe)
    if not dossie.get("encontrado"):
        return {"encontrado": False, "codigo": codigo}
    return {
        "encontrado": True,
        "dossie": dossie,
        "verificacao": verificar_dossie(conn, dossie),
    }


def _lista(xs: list[Any], vazio: str = "—") -> str:
    return ", ".join(str(x) for x in xs) if xs else vazio


def format_mapa(result: dict[str, Any]) -> str:
    """Renderiza o resultado de ``mapear`` como markdown determinístico.

    O bloco final é uma nota de honestidade: o verificador confirma SÍMBOLOS
    (função/tabela, closed-world), nunca o SENTIDO de negócio da rotina —
    afirmações de domínio precisam ser conferidas no fonte.
    """
    if not result.get("encontrado"):
        return f"❌ '{result.get('codigo')}' não encontrado no índice."

    d = result["dossie"]
    v = result["verificacao"]
    ident = d["identidade"]
    out: list[str] = [
        f"# Mapa — {d['funcao']}  ({d['arquivo']} · {ident['tipo']} · {ident['loc']} linhas)",
        "",
        f"**Identidade:** namespace `{ident['namespace'] or '—'}` · "
        f"capabilities: {_lista(ident['capabilities'])} · includes: {_lista(ident['includes'])}",
        "",
        "## Funções",
        f"- **user functions ({len(d['funcoes']['user_funcs'])}):** {_lista(d['funcoes']['user_funcs'])}",
        f"- total de funções: {d['funcoes']['total_funcoes']} · "
        f"pontos de entrada: {_lista(d['funcoes']['pontos_entrada'])}",
        "",
        "## Tabelas",
        f"- **lê:** {_lista(d['tabelas']['read'])}",
        f"- **grava:** {_lista(d['tabelas']['write'])}",
        f"- **reclock:** {_lista(d['tabelas']['reclock'])}",
        "",
        "## Integração",
        f"- **chamada por:** {_lista(d['grafo']['callers'])}",
        f"- **chama:** {_lista(d['grafo']['callees'])}",
        "",
        "## Verificação (closed-world no índice)",
        f"- **{v['exists']}/{v['total']}** símbolos confirmados",
    ]
    if v["funcoes_not_found"]:
        out.append(f"- ⚠ **funções ausentes do índice:** {_lista(v['funcoes_not_found'])}")
    if v["tabelas_fora_corpus"]:
        nota = "cobertura, não erro" if v["sx2_ingerido"] else "SX2 não ingerido"
        out.append(
            f"- (i) **tabelas no código fora do SX2 ({nota}):** {_lista(v['tabelas_fora_corpus'])}"
        )
    if d.get("detalhe_funcoes"):
        out += ["", "## Detalhe por função (o que cada uma chama)"]
        out += [f"- **{e['funcao']}:** {_lista(e['chama'])}" for e in d["detalhe_funcoes"]]
    out += [
        "",
        "> Mapa determinístico do índice — afirmações de **negócio/domínio NÃO são "
        "verificadas** (o verificador confere símbolo, não sentido); confirme no fonte.",
    ]
    return "\n".join(out)
