#!/usr/bin/env python3
"""Catálogo dos schematics oficiais do PO UI (`ng generate @po-ui/...`) — #99.

Lista os generators de ``projects/{ui,templates}/schematics/ng-generate`` do
po-angular (verificado da fonte) e combina com uma descrição/caso-de-uso curados,
para que a IA recomende o schematic certo em vez de montar a tela à mão (e errar).

Gera ``cli/plugadvpl/lookups/poui_schematics.json``.

Uso: python scripts/build_poui_schematics.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "cli" / "plugadvpl" / "lookups" / "poui_schematics.json"
API = "https://api.github.com/repos/po-ui/po-angular/contents"

# Pacote por projeto do monorepo.
_PACOTE = {"ui": "@po-ui/ng-components", "templates": "@po-ui/ng-templates"}

# Caso-de-uso curado por generator (o source não carrega descrição).
_CASOS: dict[str, tuple[str, str]] = {
    # generator: (o que gera, quando usar)
    "po-page-dynamic-table": (
        "listagem CRUD dinâmica (grid + filtros + ações) a partir de serviço/metadados",
        "tela de consulta/listagem de um cadastro com paginação e ações",
    ),
    "po-page-dynamic-edit": (
        "formulário dinâmico de cadastro/edição (create/update) a partir de fields",
        "tela de inclusão/alteração de um registro",
    ),
    "po-page-dynamic-detail": (
        "tela de detalhe/visualização dinâmica (somente leitura)",
        "exibir um registro em modo leitura",
    ),
    "po-page-dynamic-search": (
        "busca avançada dinâmica com filtros e disclaimers",
        "tela de pesquisa avançada (advanced filter)",
    ),
    "po-page-login": ("tela de login", "autenticação de usuário"),
    "po-page-blocked-user": ("tela de usuário bloqueado", "fluxo de bloqueio de conta"),
    "po-page-change-password": ("tela de troca de senha", "fluxo de alterar/expirar senha"),
    "po-page-job-scheduler": (
        "agendador de tarefas/jobs (po-page-job-scheduler)",
        "configurar execução agendada de processos",
    ),
    "po-page-default": (
        "página base com header, breadcrumb e actions",
        "esqueleto de página padrão (estática)",
    ),
    "po-page-detail": ("página de detalhe (estática)", "detalhe sem dinamismo de metadados"),
    "po-page-edit": ("página de edição (estática)", "formulário de edição manual"),
    "po-page-list": ("página de listagem (estática)", "listagem manual (sem dynamic-table)"),
    "sidemenu": ("menu lateral (po-menu) com itens", "estrutura de navegação/menu do app"),
}


def _list_dirs(api_path: str) -> list[str]:
    try:
        req = urllib.request.Request(
            f"{API}/{api_path}", headers={"User-Agent": "plugadvpl-schem"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []
    return [e["name"] for e in data if isinstance(data, list) and e.get("type") == "dir"]


def main() -> None:
    catalogo: list[dict] = []
    faltando: list[str] = []
    for proj, pacote in _PACOTE.items():
        for gen in _list_dirs(f"projects/{proj}/schematics/ng-generate"):
            gera, caso = _CASOS.get(gen, ("", ""))
            if not gera:
                faltando.append(gen)  # generator novo sem descrição curada
            catalogo.append(
                {
                    "chave": f"{pacote}:{gen}",
                    "generator": gen,
                    "pacote": pacote,
                    "comando": f"ng generate {pacote}:{gen}",
                    "gera": gera,
                    "caso_uso": caso,
                }
            )
    catalogo.sort(key=lambda e: (e["pacote"], e["generator"]))
    OUT.write_text(
        json.dumps(catalogo, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    print(f"schematics: {len(catalogo)} -> {OUT.name}")
    if faltando:
        print(f"AVISO: generators sem descrição curada (atualize _CASOS): {faltando}")
    if not catalogo:
        sys.exit("nenhum schematic listado")


if __name__ == "__main__":
    main()
