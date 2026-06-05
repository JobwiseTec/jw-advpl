"""Ingest pipeline: scan -> parse (parallel) -> write SQLite + FTS5 rebuild.

Orquestrador do MVP. Em arquivos pequenos (<200) roda single-thread; acima
distribui parsing entre workers (ProcessPoolExecutor) e centraliza escrita
em SQLite numa thread única (SQLite não suporta writers paralelos).

Estratégia de upsert por arquivo:
- DELETE em todas as tabelas dependentes WHERE arquivo=? (replace atômico).
- INSERT OR REPLACE em fontes (PK = arquivo).
- INSERT em massa (executemany) nas tabelas dependentes.

FTS5 é rebuildado uma vez ao final (mais barato do que insert-by-insert
para batch grande).
"""

from __future__ import annotations

import datetime as _dt
import json
import multiprocessing as mp
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING, Any

from plugadvpl import __version__ as _cli_version
from plugadvpl.db import (
    apply_migrations,
    close_db,
    get_meta,
    init_meta,
    open_db,
    seed_lookups,
    set_meta,
)
from plugadvpl.parsing import lint as lint_module
from plugadvpl.parsing.execauto import (
    extract_execauto_calls,
)
from plugadvpl.parsing.execauto import (
    serialize_tables as serialize_execauto_tables,
)
from plugadvpl.parsing.metrics import extract_function_metrics
from plugadvpl.parsing.parser import parse_source
from plugadvpl.parsing.protheus_doc import (
    extract_protheus_docs,
    infer_module,
)
from plugadvpl.parsing.protheus_doc import (
    serialize_json as serialize_pdoc_json,
)
from plugadvpl.parsing.triggers import (
    extract_execution_triggers,
)
from plugadvpl.parsing.triggers import (
    serialize_metadata as serialize_trigger_metadata,
)
from plugadvpl.scan import scan_sources_full

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

PARSER_VERSION = "p1.0.0"

# Threshold para escolha automática do modo de execução. Abaixo, o overhead de
# spawn/IPC do ProcessPool ultrapassa o ganho do paralelismo.
_PARALLEL_THRESHOLD = 200

# Heurística para skip de paralelo quando workers foi explicitado (>1) mas o
# universo é pequeno demais para amortizar overhead.
_PARALLEL_MIN_FILES = 50

# Default workers cap quando não informado pelo chamador.
_DEFAULT_WORKERS_CAP = 8

# Chunksize do pool.map — balanceia overhead de IPC vs latência.
_POOL_CHUNKSIZE = 20

# Limite de prints de erro para não poluir stderr em ingest grande quebrado.
_MAX_ERROR_PRINTS = 5

# Tipos de função que NÃO viram chunk (ficam apenas em chamadas_funcao).
_NON_CHUNK_KINDS = frozenset({"mvc_hook"})

# Regex para redact secrets — URLs com user:pass, tokens hex >=40 chars.
_REDACT_URL_RE = re.compile(r"https?://[^:\s/@]+:[^@\s]+@", re.IGNORECASE)
_REDACT_TOKEN_RE = re.compile(r"\b[a-f0-9]{40,}\b", re.IGNORECASE)


def _iso_now() -> str:
    """Timestamp ISO-8601 UTC sem microssegundos (compatível com SQLite datetime)."""
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


_SIGNATURE_PARENS_RE = re.compile(r"\(([^)]*)\)")


def _count_signature_params(assinatura: str) -> int:
    """v0.6.0 (Feature B): conta parâmetros na assinatura da função.

    Naïve: pega conteúdo entre o primeiro `(` e o primeiro `)` matching,
    splita por vírgula top-level. Ignora ``Class X``/``As Y`` na cauda.
    Retorna 0 se sem parens ou parens vazios.
    """
    if not assinatura:
        return 0
    m = _SIGNATURE_PARENS_RE.search(assinatura)
    if not m:
        return 0
    args = m.group(1).strip()
    if not args:
        return 0
    # Naïve comma count — signatures ADVPL raramente têm parens aninhados.
    return args.count(",") + 1


def _redact(text: str) -> str:
    """Mascara segredos óbvios em snippets/contextos quando ``redact_secrets`` está ativo."""
    text = _REDACT_URL_RE.sub("https://[REDACTED]@", text)
    return _REDACT_TOKEN_RE.sub("[REDACTED]", text)


def _decide_workers(requested: int | None, num_files: int) -> int:
    """Decide número efetivo de workers.

    - ``requested == 0``: explicit single-thread.
    - ``num_files < _PARALLEL_THRESHOLD``: single-thread (overhead não compensa).
    - ``requested is None``: ``min(_DEFAULT_WORKERS_CAP, cpu_count)``.
    - caso contrário: ``requested``.
    """
    if requested == 0:
        return 0
    if num_files < _PARALLEL_THRESHOLD:
        return 0
    if requested is None:
        return min(_DEFAULT_WORKERS_CAP, os.cpu_count() or 1)
    return requested


def _normalize_destino(destino: str) -> str:
    """Forma normalizada para lookup case-insensitive: uppercase, sem prefixo ``U_``."""
    norm = destino.upper()
    if norm.startswith("U_"):
        norm = norm[2:]
    return norm


def _parse_worker(
    args: tuple[Path, bool],
) -> tuple[Path, dict[str, Any] | None, str | None, list[dict[str, Any]] | None, str | None]:
    """Worker do ProcessPool: parse + lint do arquivo. Retorna tupla pickle-safe.

    Não toca SQLite. Em caso de erro, retorna (fp, None, None, None, msg).
    O parâmetro ``redact_secrets`` é aplicado pelo writer (não aqui) para
    garantir snippets crus consistentes entre serial e paralelo.
    """
    fp, _redact_flag = args
    try:
        parsed = parse_source(fp)
        content = fp.read_text(encoding=parsed.get("encoding", "cp1252"), errors="replace")
        findings = lint_module.lint_source(parsed, content)
        return (fp, parsed, content, findings, None)
    except Exception as exc:  # worker boundary — qualquer falha vira registro de erro
        return (fp, None, None, None, str(exc))


def _delete_dependents(conn: sqlite3.Connection, arquivo: str) -> None:
    """Remove rows dependentes de ``arquivo`` em todas as tabelas filho.

    Tabelas com FK ON DELETE CASCADE (fonte_chunks, fonte_tabela) seriam limpas
    automaticamente quando ``fontes`` é deletado, mas usamos REPLACE em fontes
    (que NÃO dispara CASCADE no SQLite) — então limpamos explicitamente.
    """
    # chamadas_funcao usa coluna arquivo_origem em vez de arquivo.
    for table in (
        "fonte_chunks",
        "fonte_tabela",
        "parametros_uso",
        "perguntas_uso",
        "operacoes_escrita",
        "sql_embedado",
        "rest_endpoints",
        "http_calls",
        "env_openers",
        "log_calls",
        "defines",
        "lint_findings",
        "execution_triggers",  # v0.4.0 — Universo 3 Feature A
        "execauto_calls",  # v0.4.1 — Universo 3 Feature B
        "protheus_docs",  # v0.4.2 — Universo 3 Feature C
        "fonte_metrics",  # v0.6.0 — Universo 4 Feature B
        "fonte_header_doc",  # v0.23.0 (#63) — header doc declarativo
    ):
        conn.execute(f"DELETE FROM {table} WHERE arquivo=?", (arquivo,))
    conn.execute("DELETE FROM chamadas_funcao WHERE arquivo_origem=?", (arquivo,))


def _write_parsed(  # noqa: PLR0912, PLR0915 — escrita verbosa: 12 tabelas dependentes
    conn: sqlite3.Connection,
    root: Path,
    fp: Path,
    parsed: dict[str, Any],
    content: str,
    findings: list[dict[str, Any]],
    counters: dict[str, int],
    no_content: bool,
    redact_secrets: bool,
) -> None:
    """Escreve um fonte parseado em todas as tabelas dependentes.

    Estratégia: DELETE WHERE arquivo=? em filhos, REPLACE em fontes. Tudo
    dentro da transação aberta pelo caller — caller faz commit.
    """
    arquivo = parsed["arquivo"]
    try:
        caminho_relativo = fp.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        # fp não está sob root (não esperado no fluxo normal — defensivo).
        caminho_relativo = fp.as_posix()
    tipo_arquivo = fp.suffix.lower().lstrip(".")

    # Stat para mtime/size (necessário para incremental).
    try:
        st = fp.stat()
        mtime_ns = st.st_mtime_ns
        size_bytes = st.st_size
    except OSError:
        mtime_ns = 0
        size_bytes = 0

    _delete_dependents(conn, arquivo)

    # Tabelas referenciadas: dict {read, write, reclock} -> JSON.
    tabelas_ref = parsed.get("tabelas_ref", {}) or {}

    # Listas de funcoes/user_funcs/pontos_entrada (nomes simples).
    funcoes_list = parsed.get("funcoes", []) or []
    funcoes_nomes = sorted({f["nome"] for f in funcoes_list if f.get("nome")})
    user_funcs = sorted({f["nome"] for f in funcoes_list if f.get("kind") == "user_function"})

    # v0.3.16: pontos_entrada agora vem do parser (combina regex de nome +
    # PARAMIXB body scan, fix #6/#10 do QA report). Antes era recomputado
    # aqui só com regex.
    pontos_entrada = parsed.get("pontos_entrada", []) or []

    # Calls auxiliares para fontes.calls_u / calls_execblock
    chamadas_list = parsed.get("chamadas", []) or []
    calls_u = sorted({c["destino"] for c in chamadas_list if c.get("tipo") == "user_func"})
    calls_execblock = sorted({c["destino"] for c in chamadas_list if c.get("tipo") == "execblock"})

    # UPSERT na tabela fontes (REPLACE atômico via INSERT OR REPLACE).
    conn.execute(
        """
        INSERT OR REPLACE INTO fontes (
            arquivo, caminho, caminho_relativo, tipo, modulo,
            funcoes, user_funcs, pontos_entrada, tabelas_ref, write_tables,
            includes, calls_u, calls_execblock, fields_ref, lines_of_code,
            hash, source_type, capabilities, ws_structures, encoding,
            reclock_tables, mtime_ns, size_bytes, indexed_at, namespace,
            tipo_arquivo, parser_version
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?
        )
        """,
        (
            arquivo,
            str(fp),
            caminho_relativo,
            "custom",
            # v0.6.0 (Feature B): backfill modulo via infer_module (path-based
            # + routine-prefix fallback). Antes era hardcoded "". Permite
            # cobertura-doc agrupar por modulo e qualquer comando filtrar.
            infer_module(caminho_relativo, funcoes_nomes[0] if funcoes_nomes else None) or "",
            json.dumps(funcoes_nomes, ensure_ascii=False),
            json.dumps(user_funcs, ensure_ascii=False),
            json.dumps(pontos_entrada, ensure_ascii=False),
            json.dumps(tabelas_ref.get("read", []), ensure_ascii=False),
            json.dumps(tabelas_ref.get("write", []), ensure_ascii=False),
            json.dumps(parsed.get("includes", []), ensure_ascii=False),
            json.dumps(calls_u, ensure_ascii=False),
            json.dumps(calls_execblock, ensure_ascii=False),
            json.dumps(parsed.get("campos_ref", []), ensure_ascii=False),
            int(parsed.get("lines_of_code", 0)),
            parsed.get("hash", ""),
            parsed.get("source_type", "outro"),
            json.dumps(parsed.get("capabilities", []), ensure_ascii=False),
            json.dumps(parsed.get("ws_structures", {}), ensure_ascii=False),
            parsed.get("encoding", ""),
            json.dumps(tabelas_ref.get("reclock", []), ensure_ascii=False),
            mtime_ns,
            size_bytes,
            _iso_now(),
            parsed.get("namespace", ""),
            tipo_arquivo,
            PARSER_VERSION,
        ),
    )

    # fonte_chunks — uma row por função (skip mvc_hook que não vira chunk real).
    lines = content.splitlines()
    chunk_rows: list[tuple[Any, ...]] = []
    # v0.9.2 (QA PERF #3): body_for_metrics separado de chunk_content. Modo
    # --no-content esconde o conteúdo do DB mas as métricas (CC/nesting/LOC)
    # ainda precisam do corpo real — antes eram computadas em "" silenciosamente.
    body_by_chunk_id: dict[str, str] = {}
    for f in funcoes_list:
        kind = f.get("kind", "function")
        if kind in _NON_CHUNK_KINDS:
            continue
        nome = f.get("nome", "")
        ini = int(f.get("linha_inicio", 1))
        fim = int(f.get("linha_fim", ini))
        # Assinatura = primeira linha do header (best-effort)
        assinatura = lines[ini - 1].strip() if 1 <= ini <= len(lines) else ""
        body_for_metrics = "\n".join(lines[ini - 1 : fim])
        if no_content:
            chunk_content = ""
        else:
            chunk_content = body_for_metrics
            if redact_secrets:
                chunk_content = _redact(chunk_content)
        chunk_id = f"{arquivo}::{nome}@{ini}"
        body_by_chunk_id[chunk_id] = body_for_metrics
        chunk_rows.append(
            (
                # ID inclui linha_inicio para distinguir funções com mesmo nome no
                # mesmo arquivo (Static + User, redefinições, overloads).
                chunk_id,
                arquivo,
                nome,
                nome.upper().strip(),
                kind,
                f.get("classe", "") or "",
                ini,
                fim,
                assinatura[:500],
                chunk_content,
                "",
            )
        )
        counters["chunks"] += 1
    if chunk_rows:
        # INSERT OR REPLACE: idempotente; se mesmo (arquivo, funcao, linha) reaparece
        # após reindex, substitui em vez de levantar UNIQUE constraint.
        conn.executemany(
            """
            INSERT OR REPLACE INTO fonte_chunks (
                id, arquivo, funcao, funcao_norm, tipo_simbolo, classe,
                linha_inicio, linha_fim, assinatura, content, modulo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            chunk_rows,
        )
        # v0.6.0 (Feature B): popula fonte_metrics (CC + nesting + LOC + params).
        # n_calls_out e has_doc ficam 0 aqui; UPDATE final no fim do _ingest_one
        # depois que chamadas_funcao e protheus_docs estão populados.
        metric_rows: list[tuple[Any, ...]] = []
        for chunk in chunk_rows:
            chunk_id, arq_c, fn_c, _norm, _kind, _classe, ini_c, fim_c, assin, _cont, _mod = chunk
            # v0.9.2 (QA PERF #3): usa body_for_metrics (corpo real) em vez de
            # cont (vazio em --no-content). Antes: métricas viravam CC=1
            # silenciosamente em modo privacy.
            body = body_by_chunk_id.get(chunk_id, "")
            mets = extract_function_metrics(body)
            params_count = _count_signature_params(assin or "")
            loc = max(0, int(fim_c or 0) - int(ini_c or 0) + 1)
            metric_rows.append(
                (
                    chunk_id,
                    arq_c,
                    fn_c,
                    ini_c,
                    fim_c,
                    loc,
                    mets["cc"],
                    mets["nesting"],
                    0,  # n_calls_out — UPDATE no fim
                    params_count,
                    0,  # has_doc — UPDATE no fim
                )
            )
        conn.executemany(
            """
            INSERT OR REPLACE INTO fonte_metrics (
                id, arquivo, funcao, linha_inicio, linha_fim,
                loc, cc, nesting, n_calls_out, params_count, has_doc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            metric_rows,
        )

    # fonte_tabela — normaliza tabelas_ref em rows (arquivo, tabela, modo).
    ft_rows: list[tuple[str, str, str]] = []
    seen_ft: set[tuple[str, str, str]] = set()
    for modo in ("read", "write", "reclock"):
        for tabela in tabelas_ref.get(modo, []) or []:
            key = (arquivo, tabela, modo)
            if key in seen_ft:
                continue
            seen_ft.add(key)
            ft_rows.append(key)
    # #61: gravação via MVC — o fonte com o ModelDef é o mantenedor (tabela master
    # via FWFormStruct(1,'X')). Pula tabelas já vistas como write/reclock clássico
    # (a detecção tradicional já as cobre; write_mvc serve pro que ela perde).
    classic_write = set(tabelas_ref.get("write", []) or []) | set(
        tabelas_ref.get("reclock", []) or []
    )
    for tabela in parsed.get("mvc_write_tables", []) or []:
        if tabela in classic_write:
            continue
        key = (arquivo, tabela, "write_mvc")
        if key in seen_ft:
            continue
        seen_ft.add(key)
        ft_rows.append(key)
    if ft_rows:
        conn.executemany(
            "INSERT INTO fonte_tabela (arquivo, tabela, modo) VALUES (?, ?, ?)",
            ft_rows,
        )

    # fonte_header_doc — metadata declarativa do cabeçalho (#63). Só grava quando
    # o parser reconheceu header (>= 2 labels). raw_header omitido em --no-content
    # (é trecho cru do fonte). Campos estruturados são metadata, gravados sempre.
    header = parsed.get("header_doc") or {}
    if header:
        conn.execute(
            """
            INSERT INTO fonte_header_doc (
                arquivo, programa, autor, data_criacao, descricao,
                doc_origem, solicitante, uso, observacao, raw_header
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                arquivo,
                header.get("programa"),
                header.get("autor"),
                header.get("data_criacao"),
                header.get("descricao"),
                header.get("doc_origem"),
                header.get("solicitante"),
                header.get("uso"),
                header.get("observacao"),
                None if no_content else header.get("raw_header"),
            ),
        )

    # chamadas_funcao
    # v0.3.15 (#8 do QA report): resolver `funcao_origem` via lookup nos chunks.
    # Antes ficava string vazia em todos os 30k+ registros, quebrando `callees`.
    # Range list ordenada por linha_inicio; pra cada call, escolhemos o chunk
    # MAIS INTERNO (menor range) que contém linha_origem — handle de nested
    # methods/static functions dentro de Class.
    chunk_ranges: list[tuple[int, int, str]] = sorted(
        (
            int(f.get("linha_inicio", 1)),
            int(f.get("linha_fim", int(f.get("linha_inicio", 1)))),
            f.get("nome", ""),
        )
        for f in funcoes_list
        if f.get("kind", "function") not in _NON_CHUNK_KINDS
    )

    def _resolve_funcao_origem(linha: int) -> str:
        """Acha a função que contém ``linha`` (chunk mais interno). '' se nenhuma."""
        if linha <= 0:
            return ""
        best: tuple[int, str] | None = None  # (range_size, nome)
        for ini, fim, nome in chunk_ranges:
            if ini <= linha <= fim:
                size = fim - ini
                if best is None or size < best[0]:
                    best = (size, nome)
        return best[1] if best else ""

    cf_rows: list[tuple[Any, ...]] = []
    for c in chamadas_list:
        destino = c.get("destino", "")
        contexto = c.get("contexto", "") or ""
        if redact_secrets and contexto:
            contexto = _redact(contexto)
        linha_origem = int(c.get("linha_origem", 0))
        cf_rows.append(
            (
                arquivo,
                _resolve_funcao_origem(linha_origem),
                linha_origem,
                c.get("tipo", ""),
                destino,
                _normalize_destino(destino),
                None,
                None,
                contexto[:500],
            )
        )
        counters["chamadas"] += 1
    if cf_rows:
        conn.executemany(
            """
            INSERT INTO chamadas_funcao (
                arquivo_origem, funcao_origem, linha_origem, tipo, destino,
                destino_norm, arquivo_destino, funcao_destino, contexto
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            cf_rows,
        )

    # parametros_uso
    pu_rows: list[tuple[Any, ...]] = []
    for p in parsed.get("parametros_uso", []) or []:
        pu_rows.append(
            (
                arquivo,
                p.get("nome", ""),
                p.get("modo", "read"),
                p.get("default_decl", "") or "",
            )
        )
        counters["params"] += 1
    if pu_rows:
        conn.executemany(
            "INSERT INTO parametros_uso (arquivo, parametro, modo, default_decl) "
            "VALUES (?, ?, ?, ?)",
            pu_rows,
        )

    # perguntas_uso
    pgu_rows = [(arquivo, g) for g in parsed.get("perguntas_uso", []) or []]
    if pgu_rows:
        conn.executemany(
            "INSERT INTO perguntas_uso (arquivo, grupo) VALUES (?, ?)",
            pgu_rows,
        )

    # sql_embedado
    sqle_rows: list[tuple[Any, ...]] = []
    for s in parsed.get("sql_embedado", []) or []:
        snippet = s.get("snippet", "") or ""
        if redact_secrets and snippet:
            snippet = _redact(snippet)
        sqle_rows.append(
            (
                arquivo,
                s.get("funcao", "") or "",
                int(s.get("linha", 0)),
                s.get("operacao", "select"),
                json.dumps(s.get("tabelas", []), ensure_ascii=False),
                snippet,
            )
        )
    if sqle_rows:
        conn.executemany(
            """
            INSERT INTO sql_embedado (
                arquivo, funcao, linha, operacao, tabelas, snippet
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            sqle_rows,
        )

    # rest_endpoints
    rest_rows: list[tuple[Any, ...]] = []
    for ep in parsed.get("rest_endpoints", []) or []:
        rest_rows.append(
            (
                arquivo,
                ep.get("classe", "") or "",
                ep.get("funcao", "") or "",
                ep.get("verbo", "") or "",
                ep.get("path", "") or "",
                ep.get("annotation_style", "") or "",
            )
        )
    if rest_rows:
        conn.executemany(
            """
            INSERT INTO rest_endpoints (
                arquivo, classe, funcao, verbo, path, annotation_style
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            rest_rows,
        )

    # http_calls
    hc_rows: list[tuple[Any, ...]] = []
    for h in parsed.get("http_calls", []) or []:
        url = h.get("url_literal", "") or ""
        if redact_secrets and url:
            url = _redact(url)
        hc_rows.append(
            (
                arquivo,
                h.get("funcao", "") or "",
                int(h.get("linha", 0)),
                h.get("metodo", ""),
                url,
            )
        )
    if hc_rows:
        conn.executemany(
            """
            INSERT INTO http_calls (
                arquivo, funcao, linha, metodo, url_literal
            ) VALUES (?, ?, ?, ?, ?)
            """,
            hc_rows,
        )

    # env_openers
    env_rows: list[tuple[Any, ...]] = []
    for e in parsed.get("env_openers", []) or []:
        env_rows.append(
            (
                arquivo,
                e.get("funcao", "") or "",
                int(e.get("linha", 0)),
                e.get("empresa", "") or "",
                e.get("filial", "") or "",
                e.get("environment", "") or "",
                e.get("modulo", "") or "",
            )
        )
    if env_rows:
        conn.executemany(
            """
            INSERT INTO env_openers (
                arquivo, funcao, linha, empresa, filial, environment, modulo
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            env_rows,
        )

    # log_calls
    log_rows: list[tuple[Any, ...]] = []
    for log in parsed.get("log_calls", []) or []:
        log_rows.append(
            (
                arquivo,
                log.get("funcao", "") or "",
                int(log.get("linha", 0)),
                log.get("nivel", "") or "",
                log.get("categoria", "") or "",
            )
        )
    if log_rows:
        conn.executemany(
            "INSERT INTO log_calls (arquivo, funcao, linha, nivel, categoria) "
            "VALUES (?, ?, ?, ?, ?)",
            log_rows,
        )

    # defines
    def_rows: list[tuple[Any, ...]] = []
    for d in parsed.get("defines", []) or []:
        def_rows.append(
            (
                arquivo,
                d.get("nome", ""),
                d.get("valor", "") or "",
                int(d.get("linha", 0)),
            )
        )
    if def_rows:
        conn.executemany(
            "INSERT INTO defines (arquivo, nome, valor, linha) VALUES (?, ?, ?, ?)",
            def_rows,
        )

    # lint_findings
    lint_rows: list[tuple[Any, ...]] = []
    for f in findings:
        snippet = f.get("snippet", "") or ""
        if redact_secrets and snippet:
            snippet = _redact(snippet)
        lint_rows.append(
            (
                arquivo,
                f.get("funcao", "") or "",
                int(f.get("linha", 0)),
                f.get("regra_id", ""),
                f.get("severidade", "warning"),
                snippet,
                f.get("sugestao_fix", "") or "",
            )
        )
        counters["lint_findings"] += 1
    if lint_rows:
        conn.executemany(
            """
            INSERT INTO lint_findings (
                arquivo, funcao, linha, regra_id, severidade, snippet, sugestao_fix
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            lint_rows,
        )

    # v0.4.0 (Universo 3 Feature A): execution_triggers
    triggers = extract_execution_triggers(content)
    if triggers:
        trigger_rows: list[tuple[Any, ...]] = []
        for t in triggers:
            linha = int(t.get("linha", 0))
            funcao = _resolve_funcao_origem(linha)
            trigger_rows.append(
                (
                    arquivo,
                    funcao,
                    linha,
                    t.get("kind", ""),
                    t.get("target", "") or "",
                    serialize_trigger_metadata(t.get("metadata", {})),
                    (t.get("snippet", "") or "")[:500],
                )
            )
        conn.executemany(
            """
            INSERT INTO execution_triggers (
                arquivo, funcao, linha, kind, target, metadata_json, snippet
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            trigger_rows,
        )
        counters["execution_triggers"] = counters.get("execution_triggers", 0) + len(trigger_rows)

    # v0.4.1 (Universo 3 Feature B): execauto_calls
    execauto = extract_execauto_calls(content)
    if execauto:
        execauto_rows: list[tuple[Any, ...]] = []
        for c in execauto:
            linha = int(c.get("linha", 0))
            funcao = _resolve_funcao_origem(linha)
            execauto_rows.append(
                (
                    arquivo,
                    funcao,
                    linha,
                    c.get("routine"),
                    c.get("module"),
                    c.get("routine_type"),
                    c.get("op_code"),
                    c.get("op_label"),
                    serialize_execauto_tables(c.get("tables_resolved", []) or []),
                    1 if c.get("dynamic_call") else 0,
                    c.get("arg_count"),
                    (c.get("snippet", "") or "")[:500],
                    1 if c.get("op_dynamic") else 0,  # v0.4.6 (C)
                )
            )
        conn.executemany(
            """
            INSERT INTO execauto_calls (
                arquivo, funcao, linha, routine, module, routine_type,
                op_code, op_label, tables_resolved_json, dynamic_call,
                arg_count, snippet, op_dynamic
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            execauto_rows,
        )
        counters["execauto_calls"] = counters.get("execauto_calls", 0) + len(execauto_rows)

        # #61: tabelas tocadas via MsExecAuto são gravação indireta — surface no
        # fonte_tabela como write_execauto (a detecção clássica também as perde).
        # Pula as já vistas como write/reclock clássico.
        classic_w = {
            t.upper()
            for t in (tabelas_ref.get("write", []) or []) + (tabelas_ref.get("reclock", []) or [])
        }
        ea_tables = sorted(
            {t.upper() for c in execauto for t in (c.get("tables_resolved") or [])} - classic_w
        )
        if ea_tables:
            conn.executemany(
                "INSERT OR IGNORE INTO fonte_tabela (arquivo, tabela, modo) VALUES (?, ?, ?)",
                [(arquivo, t, "write_execauto") for t in ea_tables],
            )

    # v0.4.2 (Universo 3 Feature C): protheus_docs
    # Usa o caminho relativo pra inferência de módulo (path-based regex).
    pdocs = extract_protheus_docs(content, arquivo=caminho_relativo)
    if pdocs:
        pdoc_rows: list[tuple[Any, ...]] = []
        for d in pdocs:
            pdoc_rows.append(
                (
                    arquivo,
                    d.get("funcao"),
                    d.get("funcao_id"),
                    d.get("tipo"),
                    d.get("module_inferido"),
                    int(d.get("linha_bloco_inicio") or 0),
                    int(d.get("linha_bloco_fim") or 0),
                    d.get("linha_funcao"),
                    d.get("summary"),
                    d.get("description"),
                    d.get("author"),
                    d.get("since"),
                    d.get("version"),
                    1 if d.get("deprecated") else 0,
                    d.get("deprecated_reason"),
                    d.get("language"),
                    serialize_pdoc_json(d.get("params")),
                    serialize_pdoc_json(d.get("returns")),
                    serialize_pdoc_json(d.get("examples")),
                    serialize_pdoc_json(d.get("history")),
                    serialize_pdoc_json(d.get("see")),
                    serialize_pdoc_json(d.get("tables")),
                    serialize_pdoc_json(d.get("todos")),
                    serialize_pdoc_json(d.get("obs")),
                    serialize_pdoc_json(d.get("links")),
                    serialize_pdoc_json(d.get("raw_tags")),
                )
            )
        conn.executemany(
            """
            INSERT INTO protheus_docs (
                arquivo, funcao, funcao_id, tipo, module_inferido,
                linha_bloco_inicio, linha_bloco_fim, linha_funcao,
                summary, description, author, since, version,
                deprecated, deprecated_reason, language,
                params_json, returns_json, examples_json, history_json,
                see_json, tables_json, todos_json, obs_json, links_json,
                raw_tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            pdoc_rows,
        )
        counters["protheus_docs"] = counters.get("protheus_docs", 0) + len(pdoc_rows)

    # v0.6.0 (Feature B): batch UPDATE de fonte_metrics com n_calls_out e has_doc
    # agora que chamadas_funcao e protheus_docs estão populados pra este arquivo.
    conn.execute(
        """
        UPDATE fonte_metrics
        SET n_calls_out = COALESCE((
            SELECT COUNT(*) FROM chamadas_funcao cf
            WHERE cf.arquivo_origem = fonte_metrics.arquivo
              AND upper(cf.funcao_origem) = upper(fonte_metrics.funcao)
        ), 0)
        WHERE arquivo = ?
        """,
        (arquivo,),
    )
    conn.execute(
        """
        UPDATE fonte_metrics
        SET has_doc = CASE WHEN EXISTS (
            SELECT 1 FROM protheus_docs pd
            WHERE pd.arquivo = fonte_metrics.arquivo
              AND (pd.funcao = fonte_metrics.funcao COLLATE NOCASE
                   OR pd.funcao_id = fonte_metrics.funcao COLLATE NOCASE)
        ) THEN 1 ELSE 0 END
        WHERE arquivo = ?
        """,
        (arquivo,),
    )

    counters["arquivos_ok"] += 1


def _ingest_serial(
    conn: sqlite3.Connection,
    files: list[Path],
    root: Path,
    counters: dict[str, int],
    no_content: bool,
    redact_secrets: bool,
) -> None:
    """Single-thread: parse + write inline. Commits a cada 50 arquivos."""
    error_prints = 0
    for i, fp in enumerate(files, 1):
        try:
            parsed = parse_source(fp)
            content = fp.read_text(encoding=parsed.get("encoding", "cp1252"), errors="replace")
            findings = lint_module.lint_source(parsed, content)
            _write_parsed(
                conn,
                root,
                fp,
                parsed,
                content,
                findings,
                counters,
                no_content,
                redact_secrets,
            )
        except Exception as exc:  # engolimos para continuar batch
            counters["arquivos_failed"] += 1
            if error_prints < _MAX_ERROR_PRINTS:
                print(f"WARN: falha em {fp.name}: {exc}", file=sys.stderr)
                error_prints += 1
        if i % 50 == 0:
            conn.commit()
    conn.commit()


def _ingest_parallel(
    conn: sqlite3.Connection,
    files: list[Path],
    root: Path,
    counters: dict[str, int],
    workers: int,
    no_content: bool,
    redact_secrets: bool,
) -> None:
    """ProcessPool: workers parseiam + lintam em paralelo, writer único faz INSERTs."""
    method = "fork" if sys.platform.startswith("linux") else "spawn"
    ctx = mp.get_context(method)
    error_prints = 0

    args_list = [(fp, redact_secrets) for fp in files]
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        # v0.9.5 (QA PERF 2026-05-18 #4): iterar direto sobre pool.map em vez
        # de materializar list(...) antes do primeiro write. Reduz pico de RAM
        # em monorepos grandes (5-10k fontes) sem alterar a ordem dos commits
        # — pool.map preserva ordem do args_list (ao contrário de as_completed).
        # Cada chunk fica disponível incremental e é escrito pelo writer
        # single-thread enquanto outros workers continuam parseando.
        iterator = pool.map(_parse_worker, args_list, chunksize=_POOL_CHUNKSIZE)
        for i, (fp, parsed, content, findings, error) in enumerate(iterator, 1):
            if error or parsed is None or content is None or findings is None:
                counters["arquivos_failed"] += 1
                if error_prints < _MAX_ERROR_PRINTS:
                    print(f"WARN: falha em {fp.name}: {error}", file=sys.stderr)
                    error_prints += 1
                continue
            try:
                _write_parsed(
                    conn,
                    root,
                    fp,
                    parsed,
                    content,
                    findings,
                    counters,
                    no_content,
                    redact_secrets,
                )
            except Exception as exc:  # writer-side falha = registro contável
                counters["arquivos_failed"] += 1
                counters["arquivos_ok"] = max(0, counters["arquivos_ok"])  # safe
                if error_prints < _MAX_ERROR_PRINTS:
                    print(f"WARN: write falhou em {fp.name}: {exc}", file=sys.stderr)
                    error_prints += 1
            if i % 50 == 0:
                conn.commit()
    conn.commit()


def ingest(
    root: Path,
    *,
    workers: int | None = None,
    incremental: bool = True,
    no_content: bool = False,
    redact_secrets: bool = False,
) -> dict[str, Any]:
    """Pipeline completo: scan -> parse -> write -> FTS5 rebuild.

    Args:
        root: raiz do projeto cliente (contém ``.prw``/``.tlpp``/...).
        workers: ``0`` = single-thread; ``None`` = adaptive (single-thread se
            <200 arquivos, senão ProcessPool com ``min(8, cpu_count)``); ``N`` =
            ProcessPool com N workers (clamp para 0 se universo <200).
        incremental: se True, pula arquivos cujo ``mtime_ns`` no DB já é >=
            o atual no FS (default True).
        no_content: se True, persiste ``fonte_chunks.content = ''`` (apenas
            metadata — útil para reduzir DB size).
        redact_secrets: se True, regex-mask URLs com credenciais e tokens
            hex >=40 chars em snippets/contextos antes de gravar.

    Returns:
        Dict com counters: ``arquivos_total``, ``arquivos_ok``,
        ``arquivos_skipped``, ``arquivos_failed``, ``chunks``, ``chamadas``,
        ``params``, ``lint_findings``, ``duration_ms``, e (v0.3.13)
        ``lookup_hash_changed`` (bool — True se o bundle de lookups mudou
        desde o ingest anterior, sinaliza pegadinha do ``--incremental``)
        + ``previous_lookup_hash`` (str | None).
    """
    start_time = time.time()

    db_path = root / ".plugadvpl" / "index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        init_meta(conn, project_root=str(root), cli_version=_cli_version)
        # Captura o hash ANTES de seed_lookups sobrescrever — permite detectar
        # se o bundle de lookups (lint_rules, funcoes_restritas, ...) mudou
        # entre a versão do binário antiga (que gravou o índice) e a atual.
        previous_lookup_hash = get_meta(conn, "lookup_bundle_hash")
        seed_lookups(conn)
        current_lookup_hash = get_meta(conn, "lookup_bundle_hash")
        set_meta(conn, "parser_version", PARSER_VERSION)
        set_meta(conn, "cli_version", _cli_version)

        scan_result = scan_sources_full(root)
        all_files = scan_result.files

        # v0.9.5 (QA PERF 2026-05-18 #2): avisa quando ha basenames duplicados
        # em diretorios distintos (ex: mod1/MATA010.prw vs mod2/MATA010.prw).
        # Schema usa basename como PK — sem o aviso, o segundo era silenciosamente
        # descartado. Persiste contagem em meta pra doctor surfacing.
        if scan_result.collisions:
            n_coll = len(scan_result.collisions)
            extra = sum(len(v) - 1 for v in scan_result.collisions.values())
            print(
                f"WARN: {n_coll} basenames com colisao em pastas distintas "
                f"({extra} fontes ignorados). Use 'plugadvpl doctor' pra listar.",
                file=sys.stderr,
            )
            set_meta(
                conn,
                "basename_collisions",
                json.dumps(
                    {k: [str(p) for p in v] for k, v in scan_result.collisions.items()},
                    ensure_ascii=False,
                ),
            )
        else:
            # Limpa meta antigo quando a colisao foi resolvida (rename/delete).
            set_meta(conn, "basename_collisions", "")

        # Stale filter (incremental).
        if incremental:
            already: dict[str, int] = {
                row[0]: int(row[1] or 0)
                for row in conn.execute("SELECT arquivo, mtime_ns FROM fontes")
            }
            files_to_parse: list[Path] = []
            for f in all_files:
                try:
                    cur_mtime = f.stat().st_mtime_ns
                except OSError:
                    continue
                if f.name not in already or cur_mtime > already[f.name]:
                    files_to_parse.append(f)
        else:
            files_to_parse = list(all_files)

        effective_workers = _decide_workers(workers, len(files_to_parse))

        counters: dict[str, Any] = {
            "arquivos_total": len(all_files),
            "arquivos_ok": 0,
            "arquivos_skipped": len(all_files) - len(files_to_parse),
            "arquivos_failed": 0,
            "chunks": 0,
            "chamadas": 0,
            "params": 0,
            "lint_findings": 0,
            "execution_triggers": 0,  # v0.4.0
            "execauto_calls": 0,  # v0.4.1
            "protheus_docs": 0,  # v0.4.2
            "duration_ms": 0,
            # v0.3.13: caller (CLI) usa esses campos pra detectar a pegadinha do
            # `--incremental` após `uv tool upgrade` — quando lookup_bundle muda
            # mas os arquivos pulados não foram re-avaliados contra as regras novas.
            "lookup_hash_changed": (
                previous_lookup_hash is not None and previous_lookup_hash != current_lookup_hash
            ),
            "previous_lookup_hash": previous_lookup_hash,
        }

        if effective_workers <= 1 or len(files_to_parse) < _PARALLEL_MIN_FILES:
            _ingest_serial(
                conn,
                files_to_parse,
                root,
                counters,
                no_content,
                redact_secrets,
            )
        else:
            _ingest_parallel(
                conn,
                files_to_parse,
                root,
                counters,
                effective_workers,
                no_content,
                redact_secrets,
            )

        # FTS5 rebuild — uma única vez ao final, mais barato do que insert-by-insert.
        conn.execute("INSERT INTO fonte_chunks_fts(fonte_chunks_fts) VALUES('rebuild')")
        conn.execute("INSERT INTO fonte_chunks_fts_tri(fonte_chunks_fts_tri) VALUES('rebuild')")
        conn.commit()

        # Update meta totals — refletem o estado final do DB.
        for table, key in (
            ("fontes", "total_arquivos"),
            ("fonte_chunks", "total_chunks"),
            ("chamadas_funcao", "total_chamadas"),
            ("lint_findings", "total_lint_findings"),
            ("execution_triggers", "total_execution_triggers"),  # v0.4.0
            ("execauto_calls", "total_execauto_calls"),  # v0.4.1
            ("protheus_docs", "total_protheus_docs"),  # v0.4.2
        ):
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            set_meta(conn, key, str(n))
        set_meta(conn, "indexed_at", _iso_now())

        counters["duration_ms"] = int((time.time() - start_time) * 1000)
        return counters
    finally:
        close_db(conn)
