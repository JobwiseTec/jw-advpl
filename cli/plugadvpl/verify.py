"""Fase 1 do roadmap-ia — `verify-claims` (verificador determinístico).

Recebe os símbolos que uma resposta afirmou (funções, tabelas, campos SX3,
parâmetros ``MV_*``, arestas de chamada, gatilhos) e devolve um verdict JSON
por claim — ``exists`` / ``not_found`` / ``relation_holds`` / ``relation_absent``
/ ``unsupported_kind`` — por set-membership exata contra o índice, com um bloco
honesto de cobertura.

Ver docs/roadmap-ia/01-verify-claims.md. É um *sound external verifier* no
sentido do LLM-Modulo: só afirma o que o índice prova; ``not_found`` é mundo
aberto por padrão (não significa "alucinado").
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from .db import get_meta

if TYPE_CHECKING:
    import sqlite3
    from typing import Any

_CLAIMS_BLOCK_RE = re.compile(r"<plugadvpl-claims>\s*(.*?)\s*</plugadvpl-claims>", re.DOTALL)


def extract_claims(text: str) -> list[dict[str, Any]]:
    """Extrai a lista de claims do bloco ``<plugadvpl-claims>{...}</...>`` de uma
    resposta. O último bloco vence (asserção mais recente). Tolerante: bloco
    ausente ou malformado retorna ``[]`` (nunca quebra o fluxo do agente).
    """
    matches = _CLAIMS_BLOCK_RE.findall(text or "")
    if not matches:
        return []
    try:
        data = json.loads(matches[-1])
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    claims = data.get("claims", [])
    return claims if isinstance(claims, list) else []


def _norm_func(symbol: str) -> str:
    """Normaliza nome de função para casar com ``fonte_chunks.funcao_norm``.

    Uppercase + trim + remove o prefixo de chamada ``U_`` (a definição de uma
    User Function não carrega ``U_``; só a chamada). Mesma semântica de
    ``query.py``.
    """
    s = symbol.strip().upper()
    return s[2:] if s.startswith("U_") else s


def _check_function(conn: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    norm = _norm_func(symbol)
    # 1. customer — definida no fonte indexado
    if conn.execute("SELECT 1 FROM fonte_chunks WHERE funcao_norm = ? LIMIT 1", (norm,)).fetchone():
        return {
            "status": "exists",
            "namespace_scope": "customer",
            "evidence": {"table": "fonte_chunks"},
            "note": "definida no fonte indexado",
        }
    # 2. nativa TOTVS
    if conn.execute(
        "SELECT 1 FROM funcoes_nativas WHERE UPPER(nome) = ? LIMIT 1", (norm,)
    ).fetchone():
        return {
            "status": "exists",
            "namespace_scope": "native",
            "evidence": {"table": "funcoes_nativas"},
            "note": "função nativa TOTVS",
        }
    # 3. restrita
    if conn.execute(
        "SELECT 1 FROM funcoes_restritas WHERE UPPER(nome) = ? LIMIT 1", (norm,)
    ).fetchone():
        return {
            "status": "exists",
            "namespace_scope": "restricted",
            "evidence": {"table": "funcoes_restritas"},
            "note": "função restrita",
        }
    return {
        "status": "not_found",
        "namespace_scope": "unknown",
        "evidence": {},
        "note": "não encontrada em fonte/nativas/restritas (mundo aberto: pode ser cobertura)",
    }


def _check_table(conn: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT custom FROM tabelas WHERE UPPER(codigo) = ? LIMIT 1", (symbol.strip().upper(),)
    ).fetchone()
    if row:
        scope = "customer" if row[0] else "standard"
        return {
            "status": "exists",
            "namespace_scope": scope,
            "evidence": {"table": "tabelas"},
            "note": "tabela no dicionário SX2",
        }
    return {
        "status": "not_found",
        "namespace_scope": "unknown",
        "evidence": {},
        "note": "ausente no SX2 (só customizações do cliente são indexadas)",
    }


def _check_field(conn: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT tabela, custom FROM campos WHERE UPPER(campo) = ? LIMIT 1",
        (symbol.strip().upper(),),
    ).fetchone()
    if row:
        scope = "customer" if row[1] else "standard"
        return {
            "status": "exists",
            "namespace_scope": scope,
            "evidence": {"table": "campos", "tabela": row[0]},
            "note": "campo no dicionário SX3",
        }
    return {
        "status": "not_found",
        "namespace_scope": "unknown",
        "evidence": {},
        "note": "ausente no SX3 (só customizações do cliente são indexadas)",
    }


def _check_param(conn: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    norm = symbol.strip().upper()
    if conn.execute(
        "SELECT 1 FROM parametros WHERE UPPER(variavel) = ? LIMIT 1", (norm,)
    ).fetchone():
        return {
            "status": "exists",
            "namespace_scope": "dictionary",
            "evidence": {"table": "parametros"},
            "note": "parâmetro no dicionário SX6",
        }
    return {
        "status": "not_found",
        "namespace_scope": "unknown",
        "evidence": {},
        "note": "ausente no SX6 (parâmetros padrão TOTVS não são indexados)",
    }


def _check_call_edge(conn: sqlite3.Connection, claim: dict[str, Any]) -> dict[str, Any]:
    caller = _norm_func(str(claim.get("caller", "")))
    callee = _norm_func(str(claim.get("callee", "")))
    display = f"{claim.get('caller', '')}→{claim.get('callee', '')}"
    if conn.execute(
        "SELECT 1 FROM chamadas_funcao WHERE UPPER(funcao_origem) = ? AND destino_norm = ? LIMIT 1",
        (caller, callee),
    ).fetchone():
        return {
            "status": "relation_holds",
            "confidence": "medium",
            "symbol": display,
            "evidence": {"table": "chamadas_funcao"},
            "note": "aresta de chamada indexada",
        }
    # grafo de chamadas é esparso (macro/ExecBlock não capturados) → nunca cravar.
    return {
        "status": "relation_absent",
        "confidence": "low",
        "symbol": display,
        "evidence": {},
        "note": "aresta não indexada; call graph é esparso (inconclusivo)",
    }


def _check_trigger(conn: sqlite3.Connection, claim: dict[str, Any]) -> dict[str, Any]:
    field = str(claim.get("field", claim.get("symbol", ""))).strip().upper()
    if conn.execute(
        "SELECT 1 FROM gatilhos WHERE UPPER(campo_origem) = ? LIMIT 1", (field,)
    ).fetchone():
        return {
            "status": "relation_holds",
            "confidence": "medium",
            "symbol": field,
            "evidence": {"table": "gatilhos"},
            "note": "gatilho SX7 indexado",
        }
    return {
        "status": "relation_absent",
        "confidence": "low",
        "symbol": field,
        "evidence": {},
        "note": "sem gatilho SX7 para o campo (dicionário pode estar parcial)",
    }


def _coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    corpora = ["fontes", "funcoes_nativas", "funcoes_restritas"]
    symbol_count = conn.execute("SELECT count(*) FROM fonte_chunks").fetchone()[0]
    # Um kind de dicionário é "completo" (para customizações do cliente) quando o
    # SX correspondente foi ingerido. Proxy: a tabela tem ao menos 1 linha.
    complete_kinds: list[str] = []
    for kind, tbl in (("table", "tabelas"), ("field", "campos"), ("param", "parametros")):
        if conn.execute(f"SELECT 1 FROM {tbl} LIMIT 1").fetchone():
            complete_kinds.append(kind)
            if tbl not in corpora:
                corpora.append(tbl)
    return {
        "corpora": corpora,
        "scope": "closed-world-over-indexed",
        "symbol_count": symbol_count,
        "complete_kinds": complete_kinds,
    }


def _index_version(conn: sqlite3.Connection) -> str:
    return "advpl-idx-schema" + (get_meta(conn, "schema_version") or "0")


def verify_claims(conn: sqlite3.Connection, claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Verifica cada claim contra o índice. Verdict por claim (nunca por resposta)."""
    coverage = _coverage(conn)
    complete = set(coverage["complete_kinds"])
    results: list[dict[str, Any]] = []
    for claim in claims:
        kind = claim.get("kind", "")
        cid = claim.get("id", "")
        symbol = claim.get("symbol", "")
        if kind == "function":
            verdict = _check_function(conn, symbol)
        elif kind == "table":
            verdict = _check_table(conn, symbol)
        elif kind == "field":
            verdict = _check_field(conn, symbol)
        elif kind == "param":
            verdict = _check_param(conn, symbol)
        elif kind == "call_edge":
            verdict = _check_call_edge(conn, claim)
        elif kind == "trigger":
            verdict = _check_trigger(conn, claim)
        else:
            verdict = {
                "status": "unsupported_kind",
                "evidence": {},
                "note": f"kind '{kind}' ainda não adjudicado",
            }
        verdict["confidence"] = _confidence(kind, symbol, verdict, complete)
        results.append({"claim_id": cid, "kind": kind, "symbol": symbol, **verdict})
    return {
        "index_version": _index_version(conn),
        "coverage": coverage,
        "results": results,
    }


# Prefixos reservados ao framework/nativas TOTVS. Uma função AUSENTE com um
# desses prefixos alega ser nativa mas não está no catálogo → alucinação provável
# (ex.: FWLerExcel, MsRetXls). Ninguém nomeia função customer assim (usa U_/prefixo).
_FRAMEWORK_PREFIXES = ("FW", "MS", "TC", "PCO", "AP")


def _confidence(kind: str, symbol: str, verdict: dict[str, Any], complete: set[str]) -> str:
    """Calibra confiança: cai em MISS, não em HIT.

    - field/table: miss de símbolo customer (prefixo Z) em corpus completo → high.
    - function: miss com prefixo de framework (FW/MS/...) → high (alega nativehood);
      miss com prefixo ``U_`` → low (provável customer não-indexado); senão medium.
    """
    if "confidence" in verdict:  # relações já decidem (sparse graph)
        return str(verdict["confidence"])
    status = verdict["status"]
    if status in ("exists", "relation_holds"):
        return "high"
    if status == "not_found":
        su = symbol.strip().upper()
        if kind in ("field", "table"):
            customer = su.startswith("Z")
            return "high" if (kind in complete and customer) else "medium"
        if kind == "function":
            if su.startswith("U_"):
                return "low"
            if any(su.startswith(p) for p in _FRAMEWORK_PREFIXES):
                return "high"
    return "medium"
