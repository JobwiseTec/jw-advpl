"""Parser de projetos PO UI (frontend Angular TOTVS). Funções puras, zero I/O.

Detecta a família @po-ui/* no package.json e deriva versão + major do Angular
exigido. Ver docs/poui-pesquisa-e-plano.md (Fase 1).
Fase 2: extrai chamadas HttpClient Angular (verbo+path) para cruzamento REST.
Fase 3b: extrai uso de componentes <po-*> + bindings p-* de templates HTML.
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

# Template component usage extraction (Fase 3b)
# Tag <po-*>: captura nome + blob de atributos (lazy, sem cruzar '>').
_PO_TAG_RE = re.compile(r"<(po-[\w-]+)((?:[^>])*?)/?>", re.DOTALL)
# Atributo p-* com prefixo opcional: [(, [, ( → kind; sem prefixo → input.
_PO_ATTR_RE = re.compile(r"(\[\(|\[|\()?\s*(p-[\w-]+)")

# Import de pacote @po-ui/* num .ts (#97). `from '@po-ui/ng-components'` etc.
_POUI_IMPORT_RE = re.compile(r"""from\s+['"](@po-ui/[\w-]+)['"]""")


def extract_poui_imports(content: str) -> list[dict[str, object]]:
    """Pacotes ``@po-ui/*`` importados num ``.ts``. Funções puras, zero I/O.

    Returns:
        Lista de dicts ``{pacote, linha}`` (dedup por pacote — 1ª ocorrência).
    """
    seen: set[str] = set()
    out: list[dict[str, object]] = []
    for m in _POUI_IMPORT_RE.finditer(content):
        pacote = m.group(1)
        if pacote in seen:
            continue
        seen.add(pacote)
        out.append({"pacote": pacote, "linha": content.count("\n", 0, m.start()) + 1})
    return out


# Interface usage extraction (#96 passo 2)
# Anotação de tipo `: PoX` / `: PoX[]` / `: Array<PoX>` seguida de `= [` ou `= {`.
# Exigir o `=` antes do literal evita capturar corpo de função (`): PoX[] {`).
_IFACE_ANNOT_RE = re.compile(r":\s*(?:Array\s*<\s*)?(Po[A-Z]\w+)\s*>?\s*(?:\[\])?\s*=\s*(?=[\[{])")
# Chave de objeto: identificador seguido de `:` (não `::`, não membro `.x`).
_OBJ_KEY_RE = re.compile(r"([A-Za-z_]\w*)\s*:(?!:)")
# Valor string logo após `chave:` (p/ checar enum, ex.: type: 'currency').
_KEY_STR_VAL_RE = re.compile(r"\s*:\s*['\"]([\w-]+)['\"]")


def _skip_string(content: str, i: int) -> int:
    """``content[i]`` abre uma string; retorna o índice após a aspa de fechamento."""
    q = content[i]
    i += 1
    n = len(content)
    while i < n:
        if content[i] == "\\":
            i += 2
            continue
        if content[i] == q:
            return i + 1
        i += 1
    return n


def _skip_comment(content: str, i: int, n: int) -> int:
    """``content[i:i+2]`` é ``//`` ou ``/*``; retorna o índice após o comentário."""
    if content[i + 1] == "/":
        j = content.find("\n", i)
        return n if j == -1 else j
    j = content.find("*/", i)
    return n if j == -1 else j + 2


def _maybe_key(content: str, i: int, stack: list[str], base_is_array: bool) -> bool:
    """A chave em ``i`` está no nível direto do literal anotado?"""
    if not stack or stack[-1] != "{":
        return False
    depth_ok = len(stack) == (2 if base_is_array else 1)
    return depth_ok and (content[i].isalpha() or content[i] == "_") and content[i - 1] not in "._"


def _scan_iface_literal(content: str, start: int) -> list[tuple[str, str, int]]:
    """Varre o literal (`[`/`{`) em ``start`` e colhe as chaves DIRETAS dos objetos.

    "Direta" = chave do objeto que pertence ao literal anotado, não de objetos
    aninhados (ex.: em ``[{a, b, detail: {c}}]`` colhe ``a, b, detail``, não ``c``).
    Respeita strings/comentários. Retorna ``[(chave, valor, linha)]`` (``valor``
    só preenchido quando o valor é string literal — usado p/ checar enum).
    """
    out: list[tuple[str, str, int]] = []
    base_is_array = content[start] == "["
    stack: list[str] = []
    i, n = start, len(content)
    while i < n:
        c = content[i]
        if c in "'\"`":
            i = _skip_string(content, i)
        elif c == "/" and i + 1 < n and content[i + 1] in "/*":
            i = _skip_comment(content, i, n)
        elif c in "{[(":
            stack.append(c)
            i += 1
        elif c in "}])":
            if stack:
                stack.pop()
            if not stack:
                return out
            i += 1
        elif _maybe_key(content, i, stack, base_is_array) and (m := _OBJ_KEY_RE.match(content, i)):
            val_m = _KEY_STR_VAL_RE.match(content, m.end() - 1)
            out.append((m.group(1), val_m.group(1) if val_m else "", content.count("\n", 0, i) + 1))
            i = m.end()
        else:
            i += 1
    return out


def extract_poui_iface_usage(content: str) -> list[dict[str, object]]:
    """Uso de interfaces de config PO UI em ``.ts``: chaves de object-literals tipados.

    Captura ``name: PoX[] = [ {…} ]`` / ``name: PoX = { … }`` / ``Array<PoX>`` e,
    para cada objeto direto do literal, cada chave usada (+ valor string quando
    houver, p/ checar enum como ``type: 'currency'``). Funções puras, zero I/O.

    Returns:
        Lista de dicts ``{interface, propriedade, valor, linha}`` (dedup por tupla).
    """
    seen: set[tuple[str, str, str, int]] = set()
    out: list[dict[str, object]] = []
    for m in _IFACE_ANNOT_RE.finditer(content):
        interface = m.group(1)
        for prop, valor, linha in _scan_iface_literal(content, m.end()):
            key = (interface, prop, valor, linha)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {"interface": interface, "propriedade": prop, "valor": valor, "linha": linha}
            )
    return out


def extract_poui_template_usage(content: str) -> list[dict[str, object]]:
    """Extrai uso de componentes ``<po-*>`` + bindings ``p-*`` de templates HTML.

    Para cada tag ``<po-X>``: ``componente`` = tag name; para cada atributo
    ``p-*`` no blob de atributos: ``kind`` = ``"output"`` se o prefixo for
    exatamente ``(``, senão ``"input"`` (inclui ``[``, ``[(``, plain).
    Dedup por (componente, binding, kind, linha).

    Returns:
        Lista de dicts com ``{componente, binding, kind, linha}``.
    """
    seen: set[tuple[str, str, str, int]] = set()
    out: list[dict[str, object]] = []
    for tag in _PO_TAG_RE.finditer(content):
        componente = tag.group(1)
        blob = tag.group(2)
        linha = content.count("\n", 0, tag.start()) + 1
        for attr in _PO_ATTR_RE.finditer(blob):
            prefix = attr.group(1) or ""
            binding = attr.group(2)
            kind = "output" if prefix == "(" else "input"
            key = (componente, binding, kind, linha)
            if key in seen:
                continue
            seen.add(key)
            out.append({"componente": componente, "binding": binding, "kind": kind, "linha": linha})
    return out


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
