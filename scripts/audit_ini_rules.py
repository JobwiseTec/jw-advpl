#!/usr/bin/env python3
"""Meta-audit do catálogo `ini_rules`: prioriza regras que precisam de curadoria.

A base de 487 regras do `ini-audit` foi gerada em lote sem trilha de procedência
(ver `docs/ini-audit-kb-enrichment-design.md`) e continha valores fabricados.
Os campos `verificado`/`fonte` (migration 021) dão rastreabilidade; a curadoria
é incremental.

Este script é **read-only** — não altera nada. Ele lista, por PRIORIDADE DE
RISCO, as regras ainda não-verificadas mais suspeitas de terem valor fabricado,
pra a turma validar lotes contra o TDN e elevar `verificado=1`.

Prioridade = risco de finding errado:
  - P1 critical não-verificada  → pode marcar FORA DE CONFORMIDADE indevidamente
  - P2 warning  não-verificada
  - P3 info     não-verificada
Dentro de cada faixa, mais SINAIS de suspeita = mais acima na fila.

Sinais de suspeita (indícios de geração em lote / valor não-confiável):
  - descricao boilerplate genérica ("Configuração da seção [X]", "extraído da TDN")
  - fonte genérica (mesma URL/pageId compartilhada por >=5 regras)
  - fonte ausente
  - value_eq/value_in com expected vazio (presença basta — deveria ser key_present)

Uso:
    python scripts/audit_ini_rules.py [--severity critical|warning|info] [--top N] [--format md|text]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
RULES_PATH = ROOT / "cli" / "plugadvpl" / "lookups" / "ini_rules.json"

_GENERIC_DESC = (
    "configuração da seção",
    "configuracao da secao",
    "extraído da tdn",
    "extraido da tdn",
)
_SHARED_FONTE_MIN = 5  # fonte usada por >=N regras = genérica (não específica da chave)
_SEV_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _load_rules() -> list[dict]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _shared_fontes(rules: list[dict]) -> set[str]:
    counts = Counter(r.get("fonte", "") for r in rules if r.get("fonte", "").strip())
    return {f for f, n in counts.items() if n >= _SHARED_FONTE_MIN}


def _signals(rule: dict, shared: set[str]) -> list[str]:
    sig: list[str] = []
    desc = rule.get("descricao", "").lower()
    if any(p in desc for p in _GENERIC_DESC):
        sig.append("descricao-generica")
    fonte = rule.get("fonte", "").strip()
    if not fonte:
        sig.append("sem-fonte")
    elif fonte in shared:
        sig.append("fonte-generica")
    if (
        rule.get("detection_kind") in ("value_eq", "value_in")
        and not rule.get("expected", "").strip()
    ):
        sig.append("expected-vazio")
    return sig


def _priority(rule: dict, n_signals: int) -> tuple[int, int]:
    """Ordena: faixa de severidade primeiro, mais sinais primeiro (desc)."""
    return (_SEV_ORDER.get(rule.get("severidade", "info"), 3), -n_signals)


def _row(rule: dict, sig: list[str]) -> str:
    rid = rule["regra_id"]
    sec = rule.get("section_glob", "")
    key = rule.get("key_name", "")
    exp = rule.get("expected", "")
    return f"  {rid:34} [{sec}] {key}={exp!r}  sinais: {','.join(sig) or '-'}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--severity", choices=("critical", "warning", "info"))
    ap.add_argument("--top", type=int, default=20, help="quantas listar por faixa (default 20)")
    ap.add_argument("--format", choices=("text", "md"), default="text")
    args = ap.parse_args()

    # Saída robusta em qualquer terminal (Windows cp1252 incluso).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    rules = _load_rules()
    shared = _shared_fontes(rules)
    pool = [r for r in rules if int(r.get("verificado", 0)) == 0]
    if args.severity:
        pool = [r for r in pool if r.get("severidade") == args.severity]

    enriched = [(r, _signals(r, shared)) for r in pool]
    enriched.sort(key=lambda rs: _priority(rs[0], len(rs[1])))

    verif = sum(1 for r in rules if int(r.get("verificado", 0)) == 1)
    by_sev = Counter(r["severidade"] for r in pool)
    by_sig: Counter = Counter()
    for _, sig in enriched:
        by_sig.update(sig or ["sem-sinal"])

    h = "## " if args.format == "md" else "=== "
    print(f"{h}Meta-audit ini_rules — fila de curadoria ===")
    print(f"Total: {len(rules)} | verificadas: {verif} | a curar: {len(pool)}")
    print(
        "A curar por severidade: "
        + ", ".join(f"{s}={by_sev[s]}" for s in ("critical", "warning", "info") if by_sev[s])
    )
    print("Sinais no pool: " + ", ".join(f"{s}={n}" for s, n in by_sig.most_common()))
    print()

    # Faixa P1 (críticas) sempre listada inteira — são as de maior risco.
    crit = [(r, s) for r, s in enriched if r.get("severidade") == "critical"]
    if crit:
        print(f"{h}P1 — críticas não-verificadas ({len(crit)}) — VALIDAR PRIMEIRO ===")
        for r, sig in crit:
            print(_row(r, sig))
        print()

    rest = [(r, s) for r, s in enriched if r.get("severidade") != "critical"]
    if rest:
        print(f"{h}P2/P3 — top {args.top} por sinais ===")
        for r, sig in rest[: args.top]:
            print(_row(r, sig))
        if len(rest) > args.top:
            print(f"  ... +{len(rest) - args.top} (use --top N ou --severity warning)")


if __name__ == "__main__":
    main()
