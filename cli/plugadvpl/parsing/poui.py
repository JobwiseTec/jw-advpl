"""Parser de projetos PO UI (frontend Angular TOTVS). Funções puras, zero I/O.

Detecta a família @po-ui/* no package.json e deriva versão + major do Angular
exigido. Ver docs/poui-pesquisa-e-plano.md (Fase 1).
Fase 2: extrai chamadas HttpClient Angular (verbo+path) para cruzamento REST.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_POUI_DEP_RE = re.compile(r"^@po-ui/")
_MAJOR_RE = re.compile(r"(\d+)")

# Chamada HttpClient Angular: this.http.get<T>('url') / http.post(`...`) etc.
# Captura verbo + 1º argumento string/template literal.
_HTTP_CALL_RE = re.compile(
    r"\bhttp\s*\.\s*(get|post|put|delete|patch)\s*(?:<[^>]*>)?\s*\(\s*([`'\"])(.*?)\2",
    re.IGNORECASE | re.DOTALL,
)
# Segmento de path "/palavra" — ignora interpolação ${...} e querystring.
_PATH_SEG_RE = re.compile(r"/[A-Za-z][\w-]*")
# Uso de HttpClient no arquivo (verbo), p/ saber se vale colher path-literals.
_HTTP_USAGE_RE = re.compile(r"\bhttp\s*\.\s*(get|post|put|delete|patch)\b", re.IGNORECASE)
# Literal de path REST: começa com / (ou ${...}/) — exclui import relativo (./x).
_REST_PATH_LITERAL_RE = re.compile(r"[`'\"]((?:\$\{[^}]*\})?/[A-Za-z][^`'\"]*)[`'\"]")


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


def _path_norm(url: str) -> str:
    """Normaliza a URL pro path casável com rest_endpoints.path.

    Tira interpolação `${...}`, host e querystring; devolve os segmentos
    estáticos `/a/b` (o último segmento dinâmico tipo `/${id}` some)."""
    sem_interp = re.sub(r"\$\{[^}]*\}", "", url)
    segs = _PATH_SEG_RE.findall(sem_interp)
    return "".join(segs) if segs else ""


def extract_angular_http_calls(content: str) -> list[dict[str, object]]:
    """Chamadas REST HttpClient num fonte Angular .ts. Funções puras.

    Híbrido (código real costuma montar a URL numa variável, não literal):

    * **Pass 1** — `http.VERB('/literal')`: verbo preciso + path do literal.
    * **Pass 2** — se o arquivo usa HttpClient, colhe path-literals REST soltos
      (`'/pedidos'`, `` `${base}/filiais` ``) que não casaram no pass 1, com verbo
      best-effort (o único verbo do arquivo, ou '' se houver mistura). Cobre o
      caso `http.get(fullUrl)` onde `fullUrl` é montado à parte.
    """
    out: list[dict[str, object]] = []
    seen_vp: set[tuple[str, str]] = set()  # (verbo, path) — pass 1 (mesmo path, verbos ≠)
    seen_path: set[str] = set()  # paths já capturados — pass 2 não re-colhe
    # Pass 1: verbo preciso quando o path é literal no próprio http.VERB(...).
    for m in _HTTP_CALL_RE.finditer(content):
        verbo = m.group(1).upper()
        path = _path_norm(m.group(3))
        if not path or (verbo, path) in seen_vp:
            continue
        seen_vp.add((verbo, path))
        seen_path.add(path)
        out.append(
            {
                "verbo": verbo,
                "url": m.group(3),
                "path_norm": path,
                "linha": content.count("\n", 0, m.start()) + 1,
            }
        )
    # Pass 2: URL em variável — colhe path-literals do arquivo (se usa HttpClient).
    verbos = {m.group(1).upper() for m in _HTTP_USAGE_RE.finditer(content)}
    if verbos:
        verbo_default = next(iter(verbos)) if len(verbos) == 1 else ""
        for m in _REST_PATH_LITERAL_RE.finditer(content):
            raw = m.group(1)
            path = _path_norm(raw)
            if not path or path in seen_path:
                continue
            seen_path.add(path)
            out.append(
                {
                    "verbo": verbo_default,
                    "url": raw,
                    "path_norm": path,
                    "linha": content.count("\n", 0, m.start()) + 1,
                }
            )
    return out
