#!/usr/bin/env python3
"""Compara modelos locais no loop de geração/correção de código (gerar.py).

Roda a MESMA tarefa de geração e a MESMA correção em cada modelo e mede:
iterações até limpar, se ficou lint+guard-clean, problemas residuais e tempo.
Serve pra decidir o trade-off robustez × velocidade (ex.: coder:7b vs coder:14b).

Uso:  python3 comparar_modelos.py [modelo1 modelo2 ...]
      (default: qwen2.5-coder:7b  qwen2.5-coder:14b)
"""

from __future__ import annotations

import json
import sys
import time

import gerar

TAREFA = (
    "Crie uma User Function (prefixo de cliente XYZ, fonte .prw) que recebe um código de "
    "cliente, valida se não está vazio e exibe um alerta quando o código for inválido."
)

CODIGO_RUIM = (
    "User Function ValidaCli(cod)\n"
    "    Local resultado := .F.\n"
    '    resultado := AllTrim(cod) != ""\n'
    "    If resultado\n"
    '        MsgInfo("Cliente valido")\n'
    "    EndIf\n"
    "Return resultado\n"
)


def _metrica(r: dict, dt: float) -> dict:
    return {
        "iters": len(r["iteracoes"]),
        "limpo": r["limpo"],
        "lint_final": len(r["findings_finais"]),
        "guard_final": len(r["guard_finais"]),
        "seg": round(dt, 1),
    }


def rodar(modelo: str) -> dict:
    t = time.time()
    g = gerar.gerar_com_lint(TAREFA, modelo=modelo)
    dtg = time.time() - t
    t = time.time()
    c = gerar.corrigir_codigo(CODIGO_RUIM, modelo=modelo)
    dtc = time.time() - t
    return {
        "gerar": _metrica(g, dtg),
        "corrigir": _metrica(c, dtc),
        "codigo_gerar": g["codigo"],
        "codigo_corrigir": c["codigo"],
    }


def main() -> int:
    modelos = sys.argv[1:] or ["qwen2.5-coder:7b", "qwen2.5-coder:14b"]
    res: dict[str, dict] = {}
    for m in modelos:
        print(f"... rodando {m} (gerar + corrigir)", flush=True)
        try:
            res[m] = rodar(m)
        except Exception as e:  # noqa: BLE001 — comparação não deve abortar por 1 modelo
            print(f"   ERRO em {m}: {e}", flush=True)

    print("\n=== COMPARAÇÃO — gerar | corrigir ===")
    cab = f"{'modelo':<22}{'g.iters':>8}{'g.limpo':>8}{'g.seg':>7}{'c.iters':>9}{'c.limpo':>8}{'c.seg':>7}"
    print(cab)
    print("-" * len(cab))
    for m, r in res.items():
        g, c = r["gerar"], r["corrigir"]
        print(f"{m:<22}{g['iters']:>8}{str(g['limpo']):>8}{g['seg']:>7}"
              f"{c['iters']:>9}{str(c['limpo']):>8}{c['seg']:>7}")

    with open("/tmp/comparacao_modelos.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("\nresultados (com código gerado) salvos em /tmp/comparacao_modelos.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
