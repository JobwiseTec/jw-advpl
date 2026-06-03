"""Parser de projetos PO UI (frontend Angular TOTVS). Funções puras, zero I/O.

Detecta a família @po-ui/* no package.json e deriva versão + major do Angular
exigido. Ver docs/poui-pesquisa-e-plano.md (Fase 1).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_POUI_DEP_RE = re.compile(r"^@po-ui/")
_MAJOR_RE = re.compile(r"(\d+)")


@dataclass(slots=True)
class PouiProject:
    poui_version: str = ""
    poui_major: int | None = None
    poui_packages: list[str] = field(default_factory=list)
    angular_version: str = ""
    angular_major: int | None = None
    compativel: bool = True


def _major(version: str) -> int | None:
    """Major de um range npm: '^21.18.0' -> 21, '~20.1.0' -> 20, '' -> None."""
    m = _MAJOR_RE.search(version or "")
    return int(m.group(1)) if m else None


def parse_poui_package_json(content: str) -> PouiProject | None:
    """Detecta projeto PO UI no package.json. None se não houver dep @po-ui/*."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    # Precedência: `dependencies` vence (pin real, ex "21.18.0") sobre dev/peer
    # (que carregam ranges como "^21" e sobrescreveriam a versão exata).
    deps: dict[str, str] = {}
    for key in ("peerDependencies", "devDependencies", "dependencies"):
        d = data.get(key)
        if isinstance(d, dict):
            deps.update({k: str(v) for k, v in d.items()})
    poui = {k: v for k, v in deps.items() if _POUI_DEP_RE.match(k)}
    if not poui:
        return None
    packages = sorted(poui)
    ver_raw = poui.get("@po-ui/ng-components") or poui[packages[0]]
    ang_ver = deps.get("@angular/core", "")
    poui_major = _major(ver_raw)
    ang_major = _major(ang_ver)
    compat = poui_major == ang_major if (poui_major and ang_major) else True
    return PouiProject(
        poui_version=ver_raw,
        poui_major=poui_major,
        poui_packages=packages,
        angular_version=ang_ver,
        angular_major=ang_major,
        compativel=compat,
    )
