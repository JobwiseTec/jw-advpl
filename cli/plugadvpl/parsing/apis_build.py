"""Detecção de uso de método ausente numa build Protheus alvo (issue #26).

Catálogo `apis_por_build` (denylist): método não-catalogado = assume que existe.
Detecção resolve `oVar := Classe():New()` por função e só sinaliza
`oVar:Metodo(` quando a classe é confirmada — zero falso-positivo.
"""

from __future__ import annotations

import json
import re
from importlib import resources as ir
from typing import Any

from plugadvpl.parsing.parser import add_function_ranges, extract_functions
from plugadvpl.parsing.stripper import strip_advpl


def load_apis_catalog() -> list[dict[str, Any]]:
    """Carrega o catálogo apis_por_build do lookup embarcado (sem precisar de DB/ingest)."""
    raw = (
        ir.files("plugadvpl").joinpath("lookups", "apis_por_build.json").read_text(encoding="utf-8")
    )
    return json.loads(raw)


_DIGITS_RE = re.compile(r"\d+")

# oVar := Classe():New()  → liga var à classe (intra-função).
_NEW_RE = re.compile(r"\b(\w+)\s*:=\s*([A-Za-z_]\w*)\s*\(\s*\)\s*:\s*New\b", re.IGNORECASE)
# oVar:Metodo(  → chamada de método (colado, sem espaço antes do ':').
_CALL_RE = re.compile(r"\b(\w+):([A-Za-z_]\w*)\s*\(", re.IGNORECASE)


def _parse_build(build: str) -> list[int]:
    """Quebra '24.3.0.5' em [24, 3, 0, 5]. Componente não-numérico vira 0."""
    parts: list[int] = []
    for comp in str(build).split("."):
        m = _DIGITS_RE.match(comp.strip())
        parts.append(int(m.group()) if m else 0)
    return parts


def compare_builds(a: str, b: str) -> int:
    """Compara duas versões de build dotted-numeric. Retorna -1/0/1 (a<b / a==b / a>b)."""
    pa, pb = _parse_build(a), _parse_build(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    for x, y in zip(pa, pb, strict=True):
        if x < y:
            return -1
        if x > y:
            return 1
    return 0


def _outside_window(build_min: str | None, build_max: str | None, target: str) -> bool:
    """True se target cai FORA da janela [build_min, build_max] (NULL = sem limite)."""
    return bool(
        (build_min and compare_builds(target, build_min) < 0)
        or (build_max and compare_builds(target, build_max) > 0)
    )


def check_build(
    content: str, catalog: list[dict[str, Any]], target_build: str
) -> list[dict[str, Any]]:
    """Sinaliza `oVar:Metodo(` ausente na build alvo.

    Resolve `oVar := Classe():New()` por função (intra-função) e só sinaliza
    quando a classe é confirmada E (classe, metodo) está no catálogo E o
    target_build cai fora da janela [build_min, build_max]. Var não-resolvível
    → silêncio (zero falso-positivo).
    """
    cat_idx = {(str(c["classe"]).lower(), str(c["metodo"]).lower()): c for c in catalog}
    funcs = add_function_ranges(extract_functions(content), content)
    lines = strip_advpl(content).split("\n")
    findings: list[dict[str, Any]] = []
    for f in funcs:
        start = int(f.get("linha_inicio", 1))
        end = min(int(f.get("linha_fim", len(lines))), len(lines))
        var_class: dict[str, str] = {}
        for ln in range(start, end + 1):
            for m in _NEW_RE.finditer(lines[ln - 1]):
                var_class[m.group(1).lower()] = m.group(2)
        for ln in range(start, end + 1):
            for m in _CALL_RE.finditer(lines[ln - 1]):
                cls = var_class.get(m.group(1).lower())
                if cls is None:
                    continue
                cat = cat_idx.get((cls.lower(), m.group(2).lower()))
                if cat is None:
                    continue
                if _outside_window(cat.get("build_min"), cat.get("build_max"), target_build):
                    findings.append(
                        {
                            "linha": ln,
                            "funcao": f.get("nome", "") or "",
                            "classe": cat["classe"],
                            "metodo": cat["metodo"],
                            "var": m.group(1),
                            "target_build": target_build,
                            "nota": cat.get("nota") or "",
                        }
                    )
    return findings


def check_build_lint_rows(
    content: str, catalog: list[dict[str, Any]], target_build: str, arquivo: str
) -> list[dict[str, Any]]:
    """Converte os findings de :func:`check_build` para o shape de linha do lint.

    Mergeável no output do ``lint`` (mesmas chaves do ``lint_query``), com
    ``regra_id='BUILD-001'`` e severidade ``warning``. Não é uma regra do
    ``lint_rules.json`` — é o catálogo ``apis_por_build`` exposto via ``lint``.
    """
    rows: list[dict[str, Any]] = []
    for f in check_build(content, catalog, target_build):
        rows.append(
            {
                "arquivo": arquivo,
                "funcao": f.get("funcao", ""),
                "linha": f["linha"],
                "regra_id": "BUILD-001",
                "severidade": "warning",
                "snippet": f"{f['var']}:{f['metodo']}",
                "sugestao_fix": (
                    f"{f['classe']}:{f['metodo']} ausente na build {target_build}. {f['nota']}"
                ),
                "sonar_rules": "[]",
            }
        )
    return rows
