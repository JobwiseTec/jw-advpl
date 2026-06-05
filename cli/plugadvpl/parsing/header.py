"""Parser do *header doc* declarativo no topo de fontes ADVPL/TLPP.

Muitos fontes Protheus trazem um bloco de metadados no cabeçalho
(`Programa..: / Autor..: / Descrição..:`), distinto do Protheus.doc
(`/*/{Protheus.doc}*/`). Este módulo extrai esse bloco de forma tolerante a
variações de pontuação (`....:`, `:`), acentos e campos faltando/extras.

Validado contra bases reais: a cobertura varia muito por convenção do projeto
(de ~0% a ~40% dos fontes). Quando não há header reconhecível, retorna dict
vazio — no-op gracioso, o ingest simplesmente não grava a linha.

Decisões empíricas (de testar em base real):

- **Escopo no 1º bloco de comentário** (não o arquivo todo) — senão `Local x :=`
  do ADVPL casa como `label: valor` (o `:=` vira falso-positivo massivo).
- **Normalizar espaço ao redor de `/`** — `DESCRIÇÃO / OBJETIVO` deve casar com
  `DESCRICAO/OBJETIVO` (numa base real isso sozinho recuperou ~770 descrições).
- **Exigir >= 2 labels conhecidos** pra considerar header válido — derruba quase
  nada (6/811 numa base) e mata comentário comum com um `Nome:` solto.
"""

from __future__ import annotations

import re
import unicodedata

# label canônico (SEM acento, UPPER, sem espaço ao redor de '/') -> coluna
_KNOWN: dict[str, str] = {
    "PROGRAMA": "programa",
    "FONTE": "programa",
    "ROTINA": "programa",
    "FUNCAO": "programa",
    "NOME": "programa",
    "AUTOR": "autor",
    "ANALISTA": "autor",
    "DESENVOLVEDOR": "autor",
    "PROGRAMADOR": "autor",
    "CONSULTOR": "autor",
    "DATA": "data_criacao",
    "CRIACAO": "data_criacao",
    "DATA CRIACAO": "data_criacao",
    "DESCRICAO": "descricao",
    "OBJETIVO": "descricao",
    "DESCRICAO/OBJETIVO": "descricao",
    "DESC": "descricao",
    "FINALIDADE": "descricao",
    "DOC": "doc_origem",
    "DOC ORIGEM": "doc_origem",
    "DOCUMENTO": "doc_origem",
    "ORIGEM": "doc_origem",
    "GAP": "doc_origem",
    "CHAMADO": "doc_origem",
    "TICKET": "doc_origem",
    "SOLICITANTE": "solicitante",
    "CLIENTE": "solicitante",
    "REQUISITANTE": "solicitante",
    "USO": "uso",
    "EMPRESA": "uso",
    "PROJETO": "uso",
    "OBS": "observacao",
    "OBSERVACAO": "observacao",
    "OBSERVACOES": "observacao",
    "HISTORICO": "observacao",
}

# colunas canônicas, na ordem de schema/exibição (raw_header é extra)
FIELDS: tuple[str, ...] = (
    "programa",
    "autor",
    "data_criacao",
    "descricao",
    "doc_origem",
    "solicitante",
    "uso",
    "observacao",
)

_LABEL_RE = re.compile(
    r"^[ \t*#=/.\-]{0,8}([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ ./]{1,28}?)[ .]{0,12}:[ \t]*(\S.*)$"
)

_TOP_LIMIT = 1200  # bloco de header tem que começar no topo do arquivo (chars)
_MIN_LABELS = 2  # mínimo de labels conhecidos pra considerar header válido
_HEAD_LINES = 50  # janela do fallback de comentário-de-linha (//)
_VAL_MAX = 500  # truncamento de cada valor
_RAW_MAX = 2000  # truncamento do raw_header


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _first_comment_block(text: str) -> str:
    """Corpo do 1º bloco de comentário do topo (``/* */`` não-Protheus.doc, ou
    run de ``//``). String vazia se não houver."""
    for m in re.finditer(r"/\*(.*?)\*/", text, re.DOTALL):
        body = m.group(1)
        if body.startswith("/"):  # /*/ ... -> Protheus.doc, ignora
            continue
        if m.start() > _TOP_LIMIT:
            break
        return body
    # fallback: run de linhas // no topo (>= _MIN_LABELS linhas)
    out: list[str] = []
    for ln in text.splitlines()[:_HEAD_LINES]:
        s = ln.strip()
        if s.startswith("//"):
            out.append(s.lstrip("/").strip())
        elif s.startswith("#") or not s:
            continue
        else:
            break
    return "\n".join(out) if len(out) >= _MIN_LABELS else ""


def extract_header_doc(text: str) -> dict[str, str]:
    """Extrai o header declarativo de ``text`` (conteúdo já decodificado).

    Retorna dict com as colunas canônicas presentes + ``raw_header``. Dict
    **vazio** quando não há header reconhecível (< :data:`_MIN_LABELS` labels).
    """
    block = _first_comment_block(text)
    if not block:
        return {}
    fields: dict[str, str] = {}
    for line in block.splitlines():
        m = _LABEL_RE.match(line)
        if not m:
            continue
        raw, val = m.group(1), m.group(2).strip()
        if val.startswith("="):  # mata ADVPL ':=' residual
            continue
        norm = _strip_accents(raw).strip().rstrip(".").strip().upper()
        norm = re.sub(r"\s+", " ", norm)
        norm = re.sub(r"\s*/\s*", "/", norm)
        canon = _KNOWN.get(norm)
        if canon and canon not in fields:
            fields[canon] = val[:_VAL_MAX]
    if len(fields) < _MIN_LABELS:
        return {}
    fields["raw_header"] = block.strip()[:_RAW_MAX]
    return fields
