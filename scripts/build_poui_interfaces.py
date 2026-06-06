#!/usr/bin/env python3
"""Extrai o catálogo de INTERFACES de config PO UI do SOURCE do po-angular.

Companion do ``build_poui_catalog.py`` (que pega os bindings ``p-*`` do template).
Aqui pegamos o **objeto de configuração** que vai dentro do binding — onde a IA
mais erra: ``PoTableColumn`` (18 props, ``type`` ∈ 14 valores documentados),
``PoDynamicFormField`` (107 props), ``PoPageAction``, ``PoComboOption``, etc.

Varre todos os ``*.interface.ts`` do repo (via git tree API), extrai cada
``export interface Po… { … }``, suas propriedades (nome, tipo, opcional) e os
valores válidos quando enumerados (união TS de string-literais OU lista JSDoc
``Valores válidos: - `x`:``). Resolve ``extends`` (mescla props herdadas). Gera
``cli/plugadvpl/lookups/poui_interfaces.json``.

Lição do ini-audit/catálogo: dado VERIFICADO da fonte, não inventado. Cada linha
carrega ``fonte`` (path no po-angular). Re-rodar atualiza o snapshot.

Uso: python scripts/build_poui_interfaces.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "cli" / "plugadvpl" / "lookups" / "poui_interfaces.json"
RAW = "https://raw.githubusercontent.com/po-ui/po-angular/master"
TREE = "https://api.github.com/repos/po-ui/po-angular/git/trees/master?recursive=1"

_IFACE_OPEN = re.compile(r"export\s+interface\s+(Po\w+)\b([^\{]*)\{")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")
_PROP = re.compile(r"^\s*(?:readonly\s+)?([A-Za-z_]\w*)\s*(\?)?\s*:\s*(.+?)\s*$", re.DOTALL)
# JSDoc `/** ... */` imediatamente seguido da propriedade que ele documenta.
_DOC_PROP = re.compile(r"/\*\*(.*?)\*/\s*(?:readonly\s+)?(\w+)\s*\??\s*:", re.DOTALL)
# Item de lista de valores no JSDoc: ``- `valor`:``
_DOC_ENUM_ITEM = re.compile(r"-\s*`([\w-]+)`\s*:")
_DOC_ENUM_HDR = re.compile(r"valores\s+(?:v[áa]lidos|permitidos|poss[íi]veis)", re.IGNORECASE)


def _get_json(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "plugadvpl-iface"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _get_text(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "plugadvpl-iface"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.URLError:
        return None


def _slice_body(text: str, open_brace_idx: int) -> str:
    """Corpo entre ``{`` (em open_brace_idx) e seu ``}`` balanceado."""
    depth = 0
    for i in range(open_brace_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_idx + 1 : i]
    return text[open_brace_idx + 1 :]


def _split_props(body: str) -> list[str]:
    """Quebra o corpo (sem comentários) em segmentos de propriedade (``;`` top-level)."""
    segs: list[str] = []
    depth = 0
    cur: list[str] = []
    for c in body:
        if c in "{<([":
            depth += 1
        elif c in "}>)]":
            depth = max(0, depth - 1)
        if c in ";\n" and depth == 0:
            seg = "".join(cur).strip()
            if seg:
                segs.append(seg)
            cur = []
            continue
        cur.append(c)
    seg = "".join(cur).strip()
    if seg:
        segs.append(seg)
    return segs


def _union_values(tipo: str) -> list[str]:
    """União pura de string-literais TS → valores; senão []."""
    parts = [p.strip() for p in tipo.strip().rstrip(";").split("|")]
    if len(parts) < 2:
        return []
    vals: list[str] = []
    for p in parts:
        m = re.fullmatch(r"""['"]([\w-]+)['"]""", p)
        if not m:
            return []
        vals.append(m.group(1))
    return vals


def _jsdoc_enum(doc: str) -> list[str]:
    """Valores enumerados num bloco JSDoc com cabeçalho ``Valores válidos:``."""
    if not _DOC_ENUM_HDR.search(doc):
        return []
    vals: list[str] = []
    for m in _DOC_ENUM_ITEM.finditer(doc):
        if m.group(1) not in vals:
            vals.append(m.group(1))
    return vals


def _parse_extends(clause: str) -> list[str]:
    m = re.search(r"extends\s+([\w\s,<>]+)$", clause.strip())
    if not m:
        return []
    # remove genéricos e pega só nomes Po*
    raw = re.sub(r"<[^>]*>", "", m.group(1))
    return [x.strip() for x in raw.split(",") if x.strip().startswith("Po")]


def _parse_interfaces(text: str, fonte: str) -> dict[str, dict]:
    """Mapa interface_nome → {extends, fonte, props: {prop: row-sem-chave}}."""
    out: dict[str, dict] = {}
    for mo in _IFACE_OPEN.finditer(text):
        nome, clause = mo.group(1), mo.group(2)
        raw_body = _slice_body(text, mo.end() - 1)
        enum_doc = {
            m.group(2): vals
            for m in _DOC_PROP.finditer(raw_body)
            if (vals := _jsdoc_enum(m.group(1)))
        }
        clean = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", raw_body))
        props: dict[str, dict] = {}
        for seg in _split_props(clean):
            head = seg.split(":", 1)[0]
            if "(" in head or "[" in head:
                continue  # método ou index-signature
            m = _PROP.match(seg)
            if not m:
                continue
            prop, opt, tipo = m.group(1), bool(m.group(2)), re.sub(r"\s+", " ", m.group(3)).strip()
            tipo = tipo.rstrip(";").strip()
            valores = _union_values(tipo) or enum_doc.get(prop, [])
            props[prop] = {
                "propriedade": prop,
                "tipo": tipo[:200],
                "opcional": 1 if opt else 0,
                "valores": valores,
            }
        out[nome] = {"extends": _parse_extends(clause), "fonte": fonte, "props": props}
    return out


def _resolve(
    name: str, ifaces: dict[str, dict], stack: frozenset[str]
) -> dict[str, tuple[dict, str]]:
    """Props efetivas de ``name`` (próprias + herdadas). Valor: (row, herdado_de)."""
    if name not in ifaces or name in stack:
        return {}
    info = ifaces[name]
    eff: dict[str, tuple[dict, str]] = {}
    for parent in info["extends"]:
        for prop, (row, _src) in _resolve(parent, ifaces, stack | {name}).items():
            eff[prop] = (row, parent)  # origem imediata do herdado
    for prop, row in info["props"].items():
        eff[prop] = (row, "")  # própria sobrescreve herdada
    return eff


def main() -> None:
    tree = _get_json(TREE)
    if not isinstance(tree, dict) or "tree" not in tree:
        sys.exit("falha ao listar a árvore do repo po-angular")
    paths = [
        e["path"]
        for e in tree["tree"]
        if e.get("type") == "blob"
        and e["path"].endswith(".interface.ts")
        and "/samples/" not in e["path"]
        and "/projects/app/" not in e["path"]
    ]
    print(f"arquivos *.interface.ts a varrer: {len(paths)}")

    ifaces: dict[str, dict] = {}
    miss = 0
    for path in sorted(paths):
        text = _get_text(f"{RAW}/{path}")
        if not text:
            miss += 1
            continue
        for nome, info in _parse_interfaces(text, path).items():
            ifaces.setdefault(nome, info)  # 1ª definição vence (estável)

    catalogo: list[dict] = []
    for nome in sorted(ifaces):
        fonte = ifaces[nome]["fonte"]
        for prop, (row, herdado) in sorted(_resolve(nome, ifaces, frozenset()).items()):
            catalogo.append(
                {
                    "chave": f"{nome}:{prop}",
                    "interface_nome": nome,
                    "propriedade": prop,
                    "tipo": row["tipo"],
                    "opcional": row["opcional"],
                    "valores": json.dumps(row["valores"], ensure_ascii=False),
                    "herdado_de": herdado,
                    "fonte": fonte,
                }
            )

    OUT.write_text(
        json.dumps(catalogo, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    n_if = len({e["interface_nome"] for e in catalogo})
    n_enum = len({e["interface_nome"] for e in catalogo if e["valores"] != "[]"})
    print(f"interfaces: {n_if} | propriedades: {len(catalogo)} | com enum: {n_enum}")
    print(f"sem fonte: {miss} -> {OUT.name}")
    if not catalogo:
        sys.exit("nenhuma interface extraída")


if __name__ == "__main__":
    main()
