"""Gerador de blocos Protheus.doc (v0.17.0+).

Inverso do parser em ``parsing/protheus_doc.py``. Recebe metadata
estruturada (``DocSpec``) e produz string formatada
``/*/{Protheus.doc} <id> ... /*/`` pronta pra colar antes de uma
função ADVPL/TLPP.

Padrão oficial TOTVS:
https://github.com/totvs/tds-vscode/blob/master/docs/protheus-doc.md

Roundtrip garantido: ``extract_protheus_docs(generate_protheus_doc(spec))``
recupera ``spec`` (tags principais).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Param:
    """Parâmetro de função ADVPL.

    Convenção TOTVS: ``@param [nome], tipo, desc`` (colchetes = opcional).
    """

    name: str
    type: str = ""
    desc: str = ""
    optional: bool = False


@dataclass(frozen=True)
class Return:
    """Valor de retorno. ``@return tipo, desc``."""

    type: str = ""
    desc: str = ""


@dataclass(frozen=True)
class DocSpec:
    """Spec completo de um bloco Protheus.doc.

    Shape segue ``_empty_doc()`` em ``parsing/protheus_doc.py`` pra
    roundtrip extract→generate. Funcao é o único campo obrigatório.
    """

    funcao: str
    tipo: str = "function"
    summary: str | None = None
    author: str | None = None
    since: str | None = None
    version: str | None = None
    deprecated: bool = False
    deprecated_reason: str | None = None
    params: list[Param] = field(default_factory=list)
    returns: Return | None = None
    examples: list[str] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)
    see: list[str] = field(default_factory=list)
    todos: list[str] = field(default_factory=list)


def _is_set(value: str | None) -> bool:
    """Helper: trata None E string vazia como ausente."""
    return bool(value)


def _format_param(p: Param) -> str:
    name = f"[{p.name}]" if p.optional else p.name
    parts: list[str] = [name]
    if p.type:
        parts.append(p.type)
    if p.desc:
        parts.append(p.desc)
    return "@param " + ", ".join(parts)


def _format_return(r: Return) -> str:
    parts: list[str] = []
    if r.type:
        parts.append(r.type)
    if r.desc:
        parts.append(r.desc)
    if not parts:
        return "@return"
    return "@return " + ", ".join(parts)


def _format_history(h: dict[str, str]) -> str:
    parts = [h.get("date", ""), h.get("user", ""), h.get("desc", "")]
    parts = [p for p in parts if p]
    if not parts:
        return "@history"
    return "@history " + ", ".join(parts)


def _format_example(text: str, indent: str = "    ") -> list[str]:
    """Emite ``@example`` seguido das linhas do exemplo indentadas."""
    lines = [f"{indent}@example"]
    for raw_line in text.splitlines() or [""]:
        lines.append(f"{indent}    {raw_line}" if raw_line else f"{indent}    ")
    return lines


def _emit_metadata_lines(spec: DocSpec, indent: str) -> list[str]:
    """Linhas de @author/@since/@version/@deprecated."""
    lines: list[str] = []
    if _is_set(spec.author):
        lines.append(f"{indent}@author {spec.author}")
    if _is_set(spec.since):
        lines.append(f"{indent}@since {spec.since}")
    if _is_set(spec.version):
        lines.append(f"{indent}@version {spec.version}")
    if spec.deprecated:
        if _is_set(spec.deprecated_reason):
            lines.append(f"{indent}@deprecated {spec.deprecated_reason}")
        else:
            lines.append(f"{indent}@deprecated")
    return lines


def _emit_signature_lines(spec: DocSpec, indent: str) -> list[str]:
    """Linhas de @param (N vezes) + @return."""
    lines: list[str] = [f"{indent}{_format_param(p)}" for p in spec.params]
    if spec.returns is not None:
        lines.append(f"{indent}{_format_return(spec.returns)}")
    return lines


def _emit_trailer_lines(spec: DocSpec, indent: str) -> list[str]:
    """Linhas de @example, @history, @see, @todo (N vezes cada)."""
    lines: list[str] = []
    for ex in spec.examples:
        lines.extend(_format_example(ex, indent=indent))
    for h in spec.history:
        lines.append(f"{indent}{_format_history(h)}")
    for s in spec.see:
        lines.append(f"{indent}@see {s}")
    for t in spec.todos:
        lines.append(f"{indent}@todo {t}")
    return lines


def generate_protheus_doc(spec: DocSpec) -> str:
    """Gera bloco Protheus.doc completo.

    Formato:

    .. code-block:: text

        /*/{Protheus.doc} <funcao>
            <summary>

            @type <tipo>
            @author <author>
            ...
            @param <p1>
            @return <type>, <desc>
        /*/

    Tags são emitidas só quando o campo correspondente está definido
    (não-vazio). Ordem segue a convenção TOTVS: header → summary →
    metadata (type/author/since/version/deprecated) → params → return
    → examples → history → see → todos.
    """
    indent = "    "
    out: list[str] = [f"/*/{{Protheus.doc}} {spec.funcao}"]
    if _is_set(spec.summary):
        out.append(f"{indent}{spec.summary}")
        out.append("")
    out.append(f"{indent}@type {spec.tipo}")
    out.extend(_emit_metadata_lines(spec, indent))
    out.extend(_emit_signature_lines(spec, indent))
    out.extend(_emit_trailer_lines(spec, indent))
    out.append("/*/")
    return "\n".join(out)


# Index positions in ``'nome,tipo,desc'`` param spec split
_PARAM_SPEC_TYPE_IDX = 1
_PARAM_SPEC_DESC_IDX = 2


def _parse_param_spec(raw: str) -> Param:
    """Parseia ``'nome,tipo,desc'`` ou ``'[nome],tipo,desc'`` em ``Param``.

    Aceita até 3 campos separados por vírgula. Colchetes em volta do
    nome marcam o param como ``optional=True``.
    """
    parts = [p.strip() for p in raw.split(",", 2)]
    nome_raw = parts[0]
    optional = nome_raw.startswith("[") and nome_raw.endswith("]")
    nome = nome_raw[1:-1].strip() if optional else nome_raw
    tipo = parts[_PARAM_SPEC_TYPE_IDX] if len(parts) > _PARAM_SPEC_TYPE_IDX else ""
    desc = parts[_PARAM_SPEC_DESC_IDX] if len(parts) > _PARAM_SPEC_DESC_IDX else ""
    return Param(name=nome, type=tipo, desc=desc, optional=optional)


def _parse_return_spec(raw: str) -> Return:
    """Parseia ``'tipo,desc'`` em ``Return``."""
    parts = [p.strip() for p in raw.split(",", 1)]
    tipo = parts[0]
    desc = parts[1] if len(parts) > 1 else ""
    return Return(type=tipo, desc=desc)


def spec_from_cli_args(
    funcao: str,
    *,
    tipo: str = "function",
    summary: str | None = None,
    author: str | None = None,
    since: str | None = None,
    version: str | None = None,
    deprecated: str | None = None,
    params: list[str] | None = None,
    returns: str | None = None,
    examples: list[str] | None = None,
) -> DocSpec:
    """Constrói ``DocSpec`` a partir dos argumentos crus do CLI.

    Conversões:
    - ``params`` lista de strings ``'nome,tipo,desc'`` (ou ``'[nome],...'``)
    - ``returns`` string ``'tipo,desc'``
    - ``deprecated`` string vira ``deprecated=True`` + ``deprecated_reason=...``;
      ``None`` deixa ambos default (False/None).
    """
    param_objs: list[Param] = [_parse_param_spec(p) for p in (params or [])]
    return_obj: Return | None = _parse_return_spec(returns) if returns else None
    is_deprecated = deprecated is not None
    reason: str | None = deprecated if (deprecated and deprecated.strip()) else None

    return DocSpec(
        funcao=funcao,
        tipo=tipo,
        summary=summary,
        author=author,
        since=since,
        version=version,
        deprecated=is_deprecated,
        deprecated_reason=reason,
        params=param_objs,
        returns=return_obj,
        examples=examples or [],
    )


def spec_to_dict(spec: DocSpec) -> dict[str, Any]:
    """Serializa ``DocSpec`` em dict (pra ``--format json`` no CLI)."""
    return {
        "funcao": spec.funcao,
        "tipo": spec.tipo,
        "summary": spec.summary,
        "author": spec.author,
        "since": spec.since,
        "version": spec.version,
        "deprecated": spec.deprecated,
        "deprecated_reason": spec.deprecated_reason,
        "params": [
            {"name": p.name, "type": p.type, "desc": p.desc, "optional": p.optional}
            for p in spec.params
        ],
        "returns": (
            {"type": spec.returns.type, "desc": spec.returns.desc} if spec.returns else None
        ),
        "examples": list(spec.examples),
        "history": list(spec.history),
        "see": list(spec.see),
        "todos": list(spec.todos),
    }
