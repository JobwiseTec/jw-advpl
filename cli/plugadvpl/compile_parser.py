"""Parser de saída do advpls. Função pura (sem subprocess, sem fs).

Spec: docs/fase1/compile-design.md §7.8, §8.

Estratégia:
- Aplica regex patterns de lookups/compile_patterns.json em ordem (`ordem` ASC).
- Linhas não-classificadas viram Diagnostic(severidade='unknown').
- Normaliza Diagnostic.arquivo via Path.resolve() vs requested_files.
- Aplica redact_patterns.json em Diagnostic.raw antes de devolver.
"""
from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass
from importlib import resources as ir
from pathlib import Path


@dataclass(frozen=True)
class Diagnostic:
    severidade: str          # error | warning | info | unknown
    arquivo: str
    linha: int
    coluna: int
    mensagem: str
    codigo: str
    raw: str

    def to_dict(self) -> dict[str, object]:
        return {
            "severidade": self.severidade,
            "arquivo": self.arquivo,
            "linha": self.linha,
            "coluna": self.coluna,
            "mensagem": self.mensagem,
            "codigo": self.codigo,
            "raw": self.raw,
        }


_PT_SEVERIDADE_MAP = {"erro": "error", "aviso": "warning", "info": "info"}


@functools.lru_cache(maxsize=1)
def _load_patterns() -> list[dict[str, object]]:
    """Carrega compile_patterns.json e ordena por (ordem ASC, índice no JSON).

    Tie-break determinístico: dois patterns com mesma ``ordem`` mantêm a ordem
    em que aparecem no JSON (vence o primeiro). Bug evitado: NÃO usar
    ``raw.index(p)`` durante o sort — é O(n²) e retorna índice da posição
    corrente, não original, quebrando o tie-break.
    """
    text = ir.files("plugadvpl").joinpath("lookups/compile_patterns.json").read_text(
        encoding="utf-8"
    )
    raw = json.loads(text)
    indexed = list(enumerate(raw))
    indexed.sort(key=lambda t: (int(t[1].get("ordem", 999)), t[0]))
    return [p for _, p in indexed]


@functools.lru_cache(maxsize=1)
def _load_redact_patterns() -> list[tuple[re.Pattern[str], str]]:
    text = ir.files("plugadvpl").joinpath("lookups/redact_patterns.json").read_text(
        encoding="utf-8"
    )
    out: list[tuple[re.Pattern[str], str]] = []
    for entry in json.loads(text):
        out.append((re.compile(entry["pattern"]), entry["replacement"]))
    return out


def _redact(text: str, patterns: list[tuple[re.Pattern[str], str]]) -> str:
    for rx, repl in patterns:
        text = rx.sub(repl, text)
    return text


def _classify_severity(raw_value: str, fixed: str | None) -> str:
    if fixed:
        return fixed
    low = raw_value.lower()
    return _PT_SEVERIDADE_MAP.get(low, low)


def _normalize_arquivo(
    arquivo_raw: str, requested_resolved: dict[Path, Path]
) -> tuple[str, bool]:
    """Tenta casar arquivo_raw com requested. Retorna (nome_final, is_unmatched)."""
    if not arquivo_raw:
        return "", False
    try:
        candidate = Path(arquivo_raw).resolve()
    except (OSError, RuntimeError):
        return arquivo_raw, True
    if candidate in requested_resolved:
        return str(requested_resolved[candidate]), False
    for req_resolved, req_original in requested_resolved.items():
        if req_resolved.name.lower() == candidate.name.lower():
            return str(req_original), False
    return arquivo_raw, True


def parse_diagnostics(
    stdout: str,
    stderr: str,
    mode: str,
    requested_files: list[Path],
) -> tuple[list[Diagnostic], list[Diagnostic]]:
    """Parseia output do advpls.

    Returns:
        ``(matched, unmatched)`` onde:

        - ``matched`` contém TODAS as linhas relevantes para os arquivos
          solicitados, incluindo:
            * diagnostics estruturados (error/warning/info) com arquivo em
              ``requested_files``
            * linhas que NENHUM pattern reconheceu, viram
              ``Diagnostic(severidade='unknown', arquivo='', linha=0, raw=<linha>)``.
              Nunca silencia.
        - ``unmatched`` contém APENAS diagnostics estruturados cujo arquivo
          NÃO bate com nenhum requested_file após ``Path.resolve()``. Vão
          para bucket ``__unmatched__`` no resultado final.
    """
    patterns = _load_patterns()
    compiled = [(p, re.compile(str(p["pattern"]))) for p in patterns]
    redact = _load_redact_patterns()

    matched: list[Diagnostic] = []
    unmatched: list[Diagnostic] = []
    # Resolve mesmo se arquivo não existir (caso comum: usuário passou
    # foo.prw como path que não está no cwd atual do teste).
    requested_resolved: dict[Path, Path] = {}
    for p in requested_files:
        try:
            requested_resolved[p.resolve()] = p
        except (OSError, RuntimeError):
            requested_resolved[Path(str(p))] = p

    for line in (stdout + "\n" + stderr).splitlines():
        if not line.strip():
            continue
        hit = False
        for entry, rx in compiled:
            m = rx.match(line)
            if not m:
                continue
            groups = m.groupdict()
            sev_group_name = entry.get("severidade_group") or ""
            sev_raw = groups.get(str(sev_group_name), "") if sev_group_name else ""
            sev_raw = sev_raw or ""
            fixed = entry.get("severidade_fixed")
            severidade = _classify_severity(
                sev_raw, fixed if isinstance(fixed, str) else None
            )
            arquivo_raw = groups.get("arquivo", "") or ""
            linha = int(groups.get("linha") or 0)
            coluna = int(groups.get("coluna") or 0)
            mensagem = groups.get("mensagem", "") or ""

            arquivo_final, is_unmatched = _normalize_arquivo(
                arquivo_raw, requested_resolved
            )

            diag = Diagnostic(
                severidade=severidade,
                arquivo=arquivo_final,
                linha=linha,
                coluna=coluna,
                mensagem=_redact(mensagem, redact),
                codigo="",
                raw=_redact(line, redact),
            )
            if is_unmatched:
                unmatched.append(diag)
            else:
                matched.append(diag)
            hit = True
            break

        if not hit:
            matched.append(
                Diagnostic(
                    severidade="unknown",
                    arquivo="",
                    linha=0,
                    coluna=0,
                    mensagem=_redact(line.strip(), redact),
                    codigo="",
                    raw=_redact(line, redact),
                )
            )

    return matched, unmatched
