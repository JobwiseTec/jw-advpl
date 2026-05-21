"""Pipeline REST → DB (U5 / Fase 3c).

Adapter espelhado de :mod:`plugadvpl.ingest_sx` que substitui leitura
de CSV por chamada REST via :class:`plugadvpl.coletadb_client.ColetaDBClient`.

Reusa:
- Normalizers de :mod:`plugadvpl.parsing.sx_csv` (refactored em Fase 3a)
- Bulk insert + meta logic compartilhada via funcoes utilitarias de
  :mod:`plugadvpl.ingest_sx`

Garante **paridade funcional**: o DB resultante deste pipeline e
bit-identico ao produzido pelo ``ingest_sx`` rodado contra o CSV
equivalente. Esse e o criterio de aceitacao #2 da spec U5.
"""
from __future__ import annotations

import datetime as _dt
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

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
from plugadvpl.parsing import sx_csv

if TYPE_CHECKING:
    from pathlib import Path

    from plugadvpl.coletadb_client import ColetaDBClient


@dataclass(frozen=True)
class _SXTablePlan:
    """Plano de ingest pra uma tabela SX via REST.

    Espelha ``_SX_INGEST_PLAN`` do :mod:`plugadvpl.ingest_sx` mas usa
    nomes das tabelas Protheus (como o COLETADB emite) ao inves de
    nomes de CSV.
    """

    protheus_table: str  # "SX1", "SX2", ... "SIX"
    db_table: str        # "tabelas", "campos", ... "indices"
    columns: list[str]   # colunas do schema SQL
    normalizer: Callable[[list[dict[str, str]]], list[dict[str, Any]]]


# Ordem espelha _SX_INGEST_PLAN do ingest_sx (PKs referenciadas antes).
_SX_REST_PLAN: list[_SXTablePlan] = [
    _SXTablePlan(
        protheus_table="SX2", db_table="tabelas",
        columns=["codigo", "nome", "modo", "custom"],
        normalizer=sx_csv.normalize_sx2_rows,
    ),
    _SXTablePlan(
        protheus_table="SX3", db_table="campos",
        columns=[
            "tabela", "campo", "tipo", "tamanho", "decimal",
            "titulo", "descricao", "validacao", "inicializador", "obrigatorio",
            "custom", "f3", "cbox", "vlduser", "when_expr",
            "proprietario", "browse", "trigger_flag", "visual", "context",
            "folder", "grpsxg",
        ],
        normalizer=sx_csv.normalize_sx3_rows,
    ),
    _SXTablePlan(
        protheus_table="SIX", db_table="indices",
        columns=[
            "tabela", "ordem", "chave", "descricao", "proprietario",
            "f3", "nickname", "showpesq", "custom",
        ],
        normalizer=sx_csv.normalize_six_rows,
    ),
    _SXTablePlan(
        protheus_table="SX7", db_table="gatilhos",
        columns=[
            "campo_origem", "sequencia", "campo_destino", "regra", "tipo",
            "tabela", "condicao", "proprietario", "seek", "alias",
            "ordem", "chave", "custom",
        ],
        normalizer=sx_csv.normalize_sx7_rows,
    ),
    _SXTablePlan(
        protheus_table="SX6", db_table="parametros",
        columns=[
            "filial", "variavel", "tipo", "descricao", "conteudo",
            "proprietario", "custom", "validacao", "init",
        ],
        normalizer=sx_csv.normalize_sx6_rows,
    ),
    _SXTablePlan(
        protheus_table="SX1", db_table="perguntas",
        columns=[
            "grupo", "ordem", "pergunta", "variavel", "tipo",
            "tamanho", "decimal", "f3", "validacao", "conteudo_padrao",
        ],
        normalizer=sx_csv.normalize_sx1_rows,
    ),
    _SXTablePlan(
        protheus_table="SX5", db_table="tabelas_genericas",
        columns=["filial", "tabela", "chave", "descricao", "custom"],
        normalizer=sx_csv.normalize_sx5_rows,
    ),
    _SXTablePlan(
        protheus_table="SX9", db_table="relacionamentos",
        columns=[
            "tabela_origem", "identificador", "tabela_destino",
            "expressao_origem", "expressao_destino", "proprietario",
            "condicao_sql", "custom",
        ],
        normalizer=sx_csv.normalize_sx9_rows,
    ),
    _SXTablePlan(
        protheus_table="SXA", db_table="pastas",
        columns=["alias", "ordem", "descricao", "proprietario", "agrupamento"],
        normalizer=sx_csv.normalize_sxa_rows,
    ),
    _SXTablePlan(
        protheus_table="SXB", db_table="consultas",
        columns=["alias", "tipo", "sequencia", "coluna", "descricao", "conteudo"],
        normalizer=sx_csv.normalize_sxb_rows,
    ),
    _SXTablePlan(
        protheus_table="SXG", db_table="grupos_campo",
        columns=["grupo", "descricao", "tamanho_max", "tamanho_min", "tamanho", "total_campos"],
        normalizer=sx_csv.normalize_sxg_rows,
    ),
]

# Mapa tabela DB → colunas PK (copia de ingest_sx; usado pra detectar dedup).
_PK_COLS_BY_TABLE: dict[str, tuple[str, ...]] = {
    "tabelas":            ("codigo",),
    "campos":             ("tabela", "campo"),
    "indices":            ("tabela", "ordem"),
    "gatilhos":           ("campo_origem", "sequencia"),
    "parametros":         ("filial", "variavel"),
    "perguntas":          ("grupo", "ordem"),
    "tabelas_genericas":  ("filial", "tabela", "chave"),
    "relacionamentos":    ("tabela_origem", "identificador", "tabela_destino"),
    "pastas":             ("alias", "ordem"),
    "consultas":          ("alias", "tipo", "sequencia", "coluna"),
    "grupos_campo":       ("grupo",),
}

_META_KEY_BY_TABLE: dict[str, str] = {
    "tabelas":            "total_sx_tabelas",
    "campos":             "total_sx_campos",
    "indices":            "total_sx_indices",
    "gatilhos":           "total_sx_gatilhos",
    "parametros":         "total_sx_parametros",
    "perguntas":          "total_sx_perguntas",
    "tabelas_genericas":  "total_sx_tabelas_genericas",
    "relacionamentos":    "total_sx_relacionamentos",
    "pastas":             "total_sx_pastas",
    "consultas":          "total_sx_consultas",
    "grupos_campo":       "total_sx_grupos_campo",
}

_BATCH_SIZE = 1000


def _iso_now() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_insert_sql(table: str, columns: list[str]) -> str:
    cols_sql = ", ".join(columns)
    placeholders = ", ".join("?" * len(columns))
    return f"INSERT OR REPLACE INTO {table} ({cols_sql}) VALUES ({placeholders})"


def _bulk_insert(
    conn: Any,
    table: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> int:
    """Insere ``rows`` em batches via executemany. Espelha ingest_sx._bulk_insert."""
    if not rows:
        return 0
    sql = _build_insert_sql(table, columns)
    inserted = 0
    batch: list[tuple[Any, ...]] = []
    for row in rows:
        batch.append(tuple(row.get(c, "") for c in columns))
        if len(batch) >= _BATCH_SIZE:
            conn.executemany(sql, batch)
            inserted += len(batch)
            batch = []
    if batch:
        conn.executemany(sql, batch)
        inserted += len(batch)
    return inserted


def ingest_via_rest(
    client: ColetaDBClient,
    db_path: Path,
    *,
    tables: list[str] | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    """Pipeline REST → DB.

    Args:
        client: instancia ja configurada do :class:`ColetaDBClient`.
        db_path: caminho do SQLite (criado se nao existir).
        tables: filtra quais tabelas Protheus baixar (default: todas as
            no plano padrao).
        progress_callback: opcional, ``(table_name, rows_inserted)`` por tabela.

    Returns:
        ``{tables_total, tables_ok, tables_skipped, total_rows, duration_ms,
           per_table, coletadb_version, protheus_build}``.

    Raises:
        :class:`ColetaDBError` se health/dump falhar (aborta antes de
        gravar qualquer coisa no DB).
    """
    start_time = time.time()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # health() chama antes de tocar o DB. Se falhar, aborta limpo.
    health = client.health()

    # Filtra plano
    plan = _SX_REST_PLAN
    if tables:
        wanted = {t.upper() for t in tables}
        plan = [p for p in plan if p.protheus_table.upper() in wanted]

    requested_tables = [p.protheus_table for p in plan]

    counters: dict[str, Any] = {
        "tables_total": len(plan),
        "tables_ok": 0,
        "tables_skipped": 0,
        "tables_failed": 0,
        "total_rows": 0,
        "per_table": {},
        "duration_ms": 0,
        "coletadb_version": health.version,
        "protheus_build": health.protheus_build,
    }

    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        # Mesmo padrao do ingest_sx: nao sobrescrever project_root se ja existe
        existing_root = get_meta(conn, "project_root")
        if not existing_root:
            init_meta(conn, project_root=str(db_path.parent.parent), cli_version=_cli_version)
        else:
            set_meta(conn, "cli_version", _cli_version)
        seed_lookups(conn)

        # Bulk download (cliente faz paginacao internamente se necessario)
        dump = client.get_dump(requested_tables)

        for table_plan in plan:
            protheus_table = table_plan.protheus_table
            db_table = table_plan.db_table
            table_dump = dump.get(protheus_table)
            if table_dump is None:
                counters["tables_skipped"] += 1
                counters["per_table"][db_table] = 0
                if progress_callback is not None:
                    progress_callback(protheus_table, 0)
                continue

            raw_rows = table_dump.get("rows", [])
            try:
                normalized = table_plan.normalizer(raw_rows)

                pk_cols = _PK_COLS_BY_TABLE.get(db_table, ())
                distinct = (
                    len({tuple(r.get(c, "") for c in pk_cols) for r in normalized})
                    if pk_cols else len(normalized)
                )
                inserted = _bulk_insert(conn, db_table, table_plan.columns, normalized)
                conn.commit()

                counters["per_table"][db_table] = distinct
                counters["total_rows"] += distinct
                counters["tables_ok"] += 1
                if progress_callback is not None:
                    progress_callback(protheus_table, distinct)

                lost = inserted - distinct
                if lost > 0:
                    print(
                        f"WARN: tabela '{db_table}' (Protheus '{protheus_table}'): "
                        f"{inserted} linhas REST → {distinct} distintas apos PK dedup "
                        f"({lost} duplicada(s) na PK {pk_cols} foram sobrescrita(s)).",
                        file=sys.stderr,
                    )
            except Exception as exc:
                counters["tables_failed"] += 1
                counters["per_table"][db_table] = 0
                print(
                    f"WARN: falha ao normalizar/inserir '{protheus_table}': {exc}",
                    file=sys.stderr,
                )

        # Pos-processamento: grupos_campo.total_campos via JOIN em campos.grpsxg
        if (
            counters["per_table"].get("grupos_campo", 0) > 0
            and counters["per_table"].get("campos", 0) > 0
        ):
            conn.execute(
                """
                UPDATE grupos_campo
                SET total_campos = (
                    SELECT COUNT(*) FROM campos
                    WHERE campos.grpsxg = grupos_campo.grupo
                )
                """
            )
            conn.commit()

        # Atualiza meta com totais
        for table, key in _META_KEY_BY_TABLE.items():
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            set_meta(conn, key, str(n))
        set_meta(conn, "last_sx_ingest_at", _iso_now())
        set_meta(conn, "last_sx_source", "rest")
        set_meta(conn, "coletadb_version", health.version)
        set_meta(conn, "protheus_build", health.protheus_build)

        counters["duration_ms"] = int((time.time() - start_time) * 1000)
        return counters
    finally:
        close_db(conn)
