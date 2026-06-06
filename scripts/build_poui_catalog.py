#!/usr/bin/env python3
"""Extrai o catálogo de componentes PO UI do SOURCE do po-angular (verificado).

Baixa os componentes-base do GitHub raw e extrai os bindings `p-` (@Input/@Output
em 3 formas: string-alias, object-alias, e signal input()/output()). Gera
`cli/plugadvpl/lookups/poui_componentes.json`.

Lição do ini-audit: catálogo é dado VERIFICADO da fonte, não inventado. Cada
entrada carrega `fonte` (o path no po-angular). Re-rodar atualiza o snapshot.

Uso: python scripts/build_poui_catalog.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "cli" / "plugadvpl" / "lookups" / "poui_componentes.json"
RAW = "https://raw.githubusercontent.com/po-ui/po-angular/master"
API = "https://api.github.com/repos/po-ui/po-angular/contents"

# 3 formas de binding p-:
#   @Input('p-x') / @Input("p-x")  +  prop (com set opcional)
#   @Input({ alias: 'p-x', ... })  +  prop
#   prop = input/output<T>({ alias: 'p-x' })
_DEC_STR = re.compile(r"@(Input|Output)\(\s*['\"](p-[\w-]+)['\"]\s*\)\s+(?:set\s+|get\s+)?(\w+)")
_DEC_OBJ = re.compile(
    r"@(Input|Output)\(\s*\{[^}]*?alias:\s*['\"](p-[\w-]+)['\"][^}]*?\}\s*\)\s+(?:set\s+|get\s+)?(\w+)"
)
# signal: prop = input<T>({alias:'p-x'}) OU input<T>(defaultValue, {alias:'p-x'})
# (o default antes do objeto de opções é comum — ex po-button: input<string>(undefined, {...})).
_SIGNAL = re.compile(
    r"(\w+)\s*=\s*(input|output)(?:\.required)?\s*<[^>]*>\s*\([^{]*\{[^}]*?alias:\s*['\"](p-[\w-]+)['\"]"
)


def _get_json(url: str) -> list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "plugadvpl-catalog"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _get_text(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "plugadvpl-catalog"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.URLError:
        return None


def _list_dirs(api_path: str) -> list[str]:
    data = _get_json(f"{API}/{api_path}")
    if not isinstance(data, list):
        return []
    return [e["name"] for e in data if e.get("type") == "dir"]


def _pacote_from_fonte(fonte: str) -> str:
    """Deriva o pacote npm do path no po-angular (#97).

    ``projects/ui/...`` -> ``@po-ui/ng-components`` (core);
    ``projects/templates/...`` -> ``@po-ui/ng-templates`` (po-page-*, login, ...).
    """
    if "/templates/" in fonte or fonte.startswith("projects/templates"):
        return "@po-ui/ng-templates"
    return "@po-ui/ng-components"


def _extract(text: str, componente: str, fonte: str) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    pacote = _pacote_from_fonte(fonte)

    def add(kind: str, binding: str, prop: str) -> None:
        key = (binding, kind)
        if key in seen:
            return
        seen.add(key)
        k = "input" if kind.lower() == "input" else "output"
        out.append(
            {
                "chave": f"{componente}:{k}:{binding}",  # PK sintética (seed single-col)
                "componente": componente,
                "kind": k,
                "binding": binding,
                "propriedade": prop,
                "fonte": fonte,
                "pacote": pacote,
            }
        )

    for m in _DEC_STR.finditer(text):
        add(m.group(1), m.group(2), m.group(3))
    for m in _DEC_OBJ.finditer(text):
        add(m.group(1), m.group(2), m.group(3))
    for m in _SIGNAL.finditer(text):
        add(m.group(2), m.group(3), m.group(1))
    return out


def main() -> None:
    # Componentes: projects/ui + projects/templates + subdirs de po-field.
    targets: list[tuple[str, str]] = []  # (componente, dir-path relativo ao repo)
    for proj in ("ui", "templates"):
        base = f"projects/{proj}/src/lib/components"
        for d in _list_dirs(base):
            targets.append((d, f"{base}/{d}"))
            if d == "po-field":
                for sub in _list_dirs(f"{base}/{d}"):
                    if sub.startswith("po-"):
                        targets.append((sub, f"{base}/{d}/{sub}"))

    print(f"componentes a varrer: {len(targets)}")
    catalogo: list[dict] = []
    ok = miss = 0
    for comp, dpath in sorted(targets):
        text = None
        for suffix in (f"{comp}-base.component.ts", f"{comp}.component.ts"):
            text = _get_text(f"{RAW}/{dpath}/{suffix}")
            if text:
                fonte = f"{dpath}/{suffix}"
                break
        if not text:
            miss += 1
            continue
        bindings = _extract(text, comp, fonte)
        if bindings:
            catalogo.extend(bindings)
            ok += 1

    catalogo.sort(key=lambda e: (e["componente"], e["kind"], e["binding"]))
    OUT.write_text(
        json.dumps(catalogo, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    comps = len({e["componente"] for e in catalogo})
    print(f"componentes com bindings: {ok} (sem fonte: {miss})")
    print(f"catálogo: {len(catalogo)} bindings de {comps} componentes -> {OUT.name}")
    if not catalogo:
        sys.exit("nenhum binding extraído")


if __name__ == "__main__":
    main()
