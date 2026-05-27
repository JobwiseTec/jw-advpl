"""Ingest pipeline para o Universo 2 — Dicionário SX exportado em CSV.

Pattern espelhado de :mod:`plugadvpl.ingest`: abre DB, aplica migrations, parseia
cada CSV via :mod:`plugadvpl.parsing.sx_csv` e grava em batches via
``executemany(INSERT OR REPLACE ...)``. Idempotente — rodar 2x produz o mesmo
estado final.

Inputs: diretório com os CSVs (busca case-insensitive por ``sx1.csv``, ``sx2.csv``,
``six.csv``, ``sxa.csv``, ..., ``sxg.csv``). Arquivos faltantes são pulados sem
falhar (counter ``csvs_skipped`` reflete).

Output: counters dict com ``csvs_total/ok/skipped``, ``total_rows``, ``duration_ms``
e ``per_table`` (rows por tabela SQL).
"""

from __future__ import annotations

import datetime as _dt
import sys
import time
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
from plugadvpl.parsing import sx_csv

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable
    from pathlib import Path

# Nome canonical do CSV → (parser, target_table, columns_in_order).
# Ordem importa: tabelas com PK que outros referenciam vêm primeiro
# (sx2 antes de sx3, sx3 antes de sx7/sxb, sx2 antes de sx9...).
_SX_INGEST_PLAN: list[tuple[str, str, list[str]]] = [
    ("sx2.csv", "tabelas", ["codigo", "nome", "modo", "custom"]),
    (
        "sx3.csv",
        "campos",
        [
            "tabela",
            "campo",
            "tipo",
            "tamanho",
            "decimal",
            "titulo",
            "descricao",
            "validacao",
            "inicializador",
            "obrigatorio",
            "custom",
            "f3",
            "cbox",
            "vlduser",
            "when_expr",
            "proprietario",
            "browse",
            "trigger_flag",
            "visual",
            "context",
            "folder",
            "grpsxg",
        ],
    ),
    (
        "six.csv",
        "indices",
        [
            "tabela",
            "ordem",
            "chave",
            "descricao",
            "proprietario",
            "f3",
            "nickname",
            "showpesq",
            "custom",
        ],
    ),
    (
        "sx7.csv",
        "gatilhos",
        [
            "campo_origem",
            "sequencia",
            "campo_destino",
            "regra",
            "tipo",
            "tabela",
            "condicao",
            "proprietario",
            "seek",
            "alias",
            "ordem",
            "chave",
            "custom",
        ],
    ),
    (
        "sx6.csv",
        "parametros",
        [
            "filial",
            "variavel",
            "tipo",
            "descricao",
            "conteudo",
            "proprietario",
            "custom",
            "validacao",
            "init",
        ],
    ),
    (
        "sx1.csv",
        "perguntas",
        [
            "grupo",
            "ordem",
            "pergunta",
            "variavel",
            "tipo",
            "tamanho",
            "decimal",
            "f3",
            "validacao",
            "conteudo_padrao",
        ],
    ),
    ("sx5.csv", "tabelas_genericas", ["filial", "tabela", "chave", "descricao", "custom"]),
    (
        "sx9.csv",
        "relacionamentos",
        [
            "tabela_origem",
            "identificador",
            "tabela_destino",
            "expressao_origem",
            "expressao_destino",
            "proprietario",
            "condicao_sql",
            "custom",
        ],
    ),
    ("sxa.csv", "pastas", ["alias", "ordem", "descricao", "proprietario", "agrupamento"]),
    ("sxb.csv", "consultas", ["alias", "tipo", "sequencia", "coluna", "descricao", "conteudo"]),
    (
        "sxg.csv",
        "grupos_campo",
        ["grupo", "descricao", "tamanho_max", "tamanho_min", "tamanho", "total_campos"],
    ),
    # v0.12.0 — migration 013 (SX extras emitidos pelo COLETADB.tlpp)
    (
        "xxa.csv",
        "dominios",
        [
            "dominio",
            "cod_dominio",
            "sequencia",
            "descricao",
            "descricao_es",
            "descricao_en",
            "tipo",
        ],
    ),
    (
        "xal.csv",
        "classificacoes_lgpd",
        [
            "filial",
            "classificacao_id",
            "descricao",
            "tipo",
            "proprietario",
            "custom",
        ],
    ),
    (
        "xam.csv",
        "anonimizacao_campos",
        [
            "filial",
            "classificacao",
            "anonimizar",
            "justificativa",
            "campo",
            "modulo",
            "classificacao_id",
            "alias",
            "identificador",
            "proprietario",
            "justificativa2",
            "em_uso",
            "custom",
        ],
    ),
    # v0.13.0 — migration 014 (Universo 6 — Workflow)
    (
        "schedules.csv",
        "schedules",
        [
            "codigo",
            "rotina",
            "empresa_filial",
            "environment",
            "modulo",
            "status",
            "tipo_recorrencia",
            "detalhe_recorrencia",
            "execucoes_dia",
            "intervalo_hh_mm",
            "data_fim_recorrencia",
            "hora_inicio",
            "data_criacao",
            "ultima_execucao",
            "ultima_hora",
            "recorrencia_raw",
        ],
    ),
    (
        "jobs.csv",
        "jobs",
        [
            "arquivo",
            "sessao",
            "rotina_main",
            "refresh_rate",
            "parametros",
        ],
    ),
    # v0.13.0 — migration 015 (Universo 8 — Menus)
    (
        "mpmenu_menu.csv",
        "mpmenu_menu",
        [
            "id",
            "nome",
            "versao",
            "modulo",
            "md5_arquivo",
            "is_default",
            "arquivo_menu",
        ],
    ),
    (
        "mpmenu_function.csv",
        "mpmenu_function",
        [
            "id",
            "funcao",
            "is_default",
        ],
    ),
    (
        "mpmenu_item.csv",
        "mpmenu_item",
        [
            "id",
            "id_menu",
            "id_pai",
            "ordem",
            "item_id_legado",
            "tp_menu",
            "status",
            "id_funcao",
            "res_name",
            "tipo",
            "tabelas",
            "acesso",
            "proprietario",
            "modulo",
            "is_default",
        ],
    ),
    (
        "mpmenu_i18n.csv",
        "mpmenu_i18n",
        [
            "parent_tipo",
            "parent_id",
            "idioma",
            "descricao",
            "is_default",
        ],
    ),
    (
        "mpmenu_key_words.csv",
        "mpmenu_key_words",
        [
            "id_item",
            "idioma",
            "palavras_chave",
            "is_default",
        ],
    ),
    (
        "mpmenu_rw.csv",
        "mpmenu_rw",
        [
            "idioma",
            "descricao",
            "is_default",
        ],
    ),
]

# Mapeamento de nome de arquivo → função de parsing (resolvida por nome).
_PARSER_BY_FILE: dict[str, Callable[[Path], list[dict[str, Any]]]] = {
    "sx1.csv": sx_csv.parse_sx1,
    "sx2.csv": sx_csv.parse_sx2,
    "sx3.csv": sx_csv.parse_sx3,
    "sx5.csv": sx_csv.parse_sx5,
    "sx6.csv": sx_csv.parse_sx6,
    "sx7.csv": sx_csv.parse_sx7,
    "sx9.csv": sx_csv.parse_sx9,
    "sxa.csv": sx_csv.parse_sxa,
    "sxb.csv": sx_csv.parse_sxb,
    "sxg.csv": sx_csv.parse_sxg,
    "six.csv": sx_csv.parse_six,
    # v0.12.0 — extras
    "xxa.csv": sx_csv.parse_xxa,
    "xal.csv": sx_csv.parse_xal,
    "xam.csv": sx_csv.parse_xam,
    # v0.13.0 — Universo 6 (Workflow)
    "schedules.csv": sx_csv.parse_schedules,
    "jobs.csv": sx_csv.parse_jobs,
    # v0.13.0 — Universo 8 (Menus)
    "mpmenu_menu.csv": sx_csv.parse_mpmenu_menu,
    "mpmenu_function.csv": sx_csv.parse_mpmenu_function,
    "mpmenu_item.csv": sx_csv.parse_mpmenu_item,
    "mpmenu_i18n.csv": sx_csv.parse_mpmenu_i18n,
    "mpmenu_key_words.csv": sx_csv.parse_mpmenu_key_words,
    "mpmenu_rw.csv": sx_csv.parse_mpmenu_rw,
}

_BATCH_SIZE = 1000

# Mapa tabela → colunas PK (espelha as migrations 001 + 002 + 004). Usado pra
# detectar dedup silencioso (linhas do CSV que colidem na PK e são sobrescritas
# por INSERT OR REPLACE). v0.3.14.
_PK_COLS_BY_TABLE: dict[str, tuple[str, ...]] = {
    "tabelas": ("codigo",),
    "campos": ("tabela", "campo"),
    "indices": ("tabela", "ordem"),
    "gatilhos": ("campo_origem", "sequencia"),
    "parametros": ("filial", "variavel"),
    "perguntas": ("grupo", "ordem"),
    "tabelas_genericas": ("filial", "tabela", "chave"),
    "relacionamentos": ("tabela_origem", "identificador", "tabela_destino"),
    "pastas": ("alias", "ordem"),
    "consultas": ("alias", "tipo", "sequencia", "coluna"),  # v0.3.14: +tipo
    "grupos_campo": ("grupo",),
    # v0.12.0 — migration 013
    "dominios": ("dominio", "cod_dominio", "sequencia"),
    "classificacoes_lgpd": ("filial", "classificacao_id"),
    "anonimizacao_campos": ("filial", "alias", "campo"),
    # v0.13.0 — migration 014 (Workflow)
    "schedules": ("codigo",),
    "jobs": ("arquivo", "sessao"),
    # v0.13.0 — migration 015 (Menus)
    "mpmenu_menu": ("id",),
    "mpmenu_function": ("id",),
    "mpmenu_item": ("id",),
    "mpmenu_i18n": ("parent_tipo", "parent_id", "idioma"),
    "mpmenu_key_words": ("id_item", "idioma"),
    "mpmenu_rw": ("idioma",),
}

# Mapa CSV → meta.* counter (apenas para os que importam para o usuário/skill).
_META_KEY_BY_TABLE: dict[str, str] = {
    "tabelas": "total_sx_tabelas",
    "campos": "total_sx_campos",
    "indices": "total_sx_indices",
    "gatilhos": "total_sx_gatilhos",
    "parametros": "total_sx_parametros",
    "perguntas": "total_sx_perguntas",
    "tabelas_genericas": "total_sx_tabelas_genericas",
    "relacionamentos": "total_sx_relacionamentos",
    "pastas": "total_sx_pastas",
    "consultas": "total_sx_consultas",
    "grupos_campo": "total_sx_grupos_campo",
    # v0.12.0 — migration 013
    "dominios": "total_sx_dominios",
    "classificacoes_lgpd": "total_sx_classificacoes_lgpd",
    "anonimizacao_campos": "total_sx_anonimizacao_campos",
    # v0.13.0 — migrations 014/015
    "schedules": "total_workflow_schedules",
    "jobs": "total_workflow_jobs",
    "mpmenu_menu": "total_menus",
    "mpmenu_function": "total_menu_functions",
    "mpmenu_item": "total_menu_items",
    "mpmenu_i18n": "total_menu_i18n",
    "mpmenu_key_words": "total_menu_key_words",
    "mpmenu_rw": "total_menu_rw",
}


def _iso_now() -> str:
    """Timestamp ISO-8601 UTC (mesmo formato usado em :mod:`plugadvpl.ingest`)."""
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_file_ci(directory: Path, name: str) -> Path | None:
    """Localiza ``name`` em ``directory`` ignorando case (Windows-friendly)."""
    exact = directory / name
    if exact.exists():
        return exact
    name_lower = name.lower()
    try:
        for f in directory.iterdir():
            if f.name.lower() == name_lower:
                return f
    except OSError:
        return None
    return None


def _build_insert_sql(table: str, columns: list[str]) -> str:
    """``INSERT OR REPLACE INTO <table> (cols) VALUES (?, ?, ...)`` para executemany."""
    cols_sql = ", ".join(columns)
    placeholders = ", ".join("?" * len(columns))
    return f"INSERT OR REPLACE INTO {table} ({cols_sql}) VALUES ({placeholders})"


def _bulk_insert(
    conn: sqlite3.Connection,
    table: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> int:
    """Insere ``rows`` em batches de :data:`_BATCH_SIZE` via executemany. Retorna count."""
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


# Prefix de 3 chars usado pra mapear nome físico de tabela DBMS → alias Protheus
# (ex: "SA1010" -> "SA1"). Usado no agrupador de RECORD_COUNTS.csv.
_PROTHEUS_ALIAS_LEN = 3
# Prefixes ignorados em RECORD_COUNTS (tabelas system do MSSQL/TOPCONN/etc).
_NON_PROTHEUS_PREFIXES = ("MP_", "SYS", "TOP", "TPH")


def _init_counters() -> dict[str, Any]:
    """Estrutura inicial do dict de counters retornado por ``ingest_sx``."""
    return {
        "csvs_total": len(_SX_INGEST_PLAN),
        "csvs_ok": 0,
        "csvs_skipped": 0,
        "csvs_failed": 0,
        "total_rows": 0,
        "per_table": {},
        "duration_ms": 0,
    }


def _seed_meta_on_first_ingest(conn: sqlite3.Connection, csv_dir: Path) -> None:
    """Inicializa meta apenas no primeiro ingest (não sobrescreve project_root real).

    v0.3.15 (#13 QA): rodar `ingest-sx` direto (sem `init`/`ingest` antes) precisa
    de meta seed, mas sobrescrever ``project_root`` com ``csv_dir`` quebra o
    projeto. Só seta quando ausente; cli_version sempre atualiza.
    """
    if not get_meta(conn, "project_root"):
        init_meta(conn, project_root=str(csv_dir), cli_version=_cli_version)
    else:
        set_meta(conn, "cli_version", _cli_version)


def _ingest_one_csv_from_plan(
    conn: sqlite3.Connection,
    csv_dir: Path,
    csv_name: str,
    table: str,
    columns: list[str],
    counters: dict[str, Any],
    progress_callback: Callable[[str, int], None] | None,
) -> None:
    """Processa um CSV do plano: parse + bulk_insert + dedup PK + callbacks.

    Atualiza ``counters`` in-place; erros em 1 CSV não derrubam o batch (boundary).
    """
    file_path = _find_file_ci(csv_dir, csv_name)
    if file_path is None:
        counters["csvs_skipped"] += 1
        counters["per_table"][table] = 0
        if progress_callback is not None:
            progress_callback(csv_name, 0)
        return

    parser = _PARSER_BY_FILE[csv_name]
    try:
        rows = parser(file_path)
        # v0.3.14: contar PKs distintas ANTES do bulk_insert. Quando
        # `distinct < len(rows)`, sabemos exatamente quantas linhas o
        # INSERT OR REPLACE silenciosamente sobrescreveu (sintoma do bug
        # da SXB com PK incompleta; agora detectado pra qualquer tabela).
        pk_cols = _PK_COLS_BY_TABLE.get(table, ())
        distinct = (
            len({tuple(r.get(c, "") for c in pk_cols) for r in rows}) if pk_cols else len(rows)
        )
        csv_rows = _bulk_insert(conn, table, columns, rows)
        conn.commit()
        # v0.3.21 (#15 QA round 2): per_table guarda numero REAL de rows
        # sobreviventes no DB (distinct PKs). Antes guardava csv_rows
        # processado e gerava discrepância com sx-status.
        counters["per_table"][table] = distinct
        counters["total_rows"] += distinct
        counters["csvs_ok"] += 1
        if progress_callback is not None:
            progress_callback(csv_name, distinct)
        # Aviso de dedup quando linhas do CSV colidiram na PK.
        lost = csv_rows - distinct
        if lost > 0:
            print(
                f"WARN: tabela '{table}': {csv_rows} linhas CSV "
                f"→ {distinct} distintas após PK dedup "
                f"({lost} duplicada(s) na PK {pk_cols} foram sobrescrita(s)).",
                file=sys.stderr,
            )
    except Exception as exc:  # boundary: erro em 1 CSV não derruba o batch
        counters["csvs_failed"] += 1
        counters["per_table"][table] = 0
        print(f"WARN: falha ao ingerir {csv_name}: {exc}", file=sys.stderr)


def _update_grupos_campo_count(conn: sqlite3.Connection, counters: dict[str, Any]) -> None:
    """Atualiza ``grupos_campo.total_campos`` via JOIN em ``campos.grpsxg``.

    Só faz sentido se ambas as tabelas têm rows (no-op silencioso senão).
    """
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


def _update_record_counts_from_csv(
    conn: sqlite3.Connection, csv_dir: Path, counters: dict[str, Any]
) -> None:
    """v0.12.0: ``RECORD_COUNTS.csv`` opcional — atualiza ``tabelas.num_rows``.

    Inventário físico do DBMS. Match por prefix de 3 chars do nome físico
    (ex: ``SA1010`` → alias ``SA1``). Soma multi-empresa. Pula tabelas system
    (MP_, SYS, TOP, TPH).
    """
    record_counts_file = _find_file_ci(csv_dir, "record_counts.csv")
    if record_counts_file is None:
        return
    try:
        rc_rows = sx_csv.parse_record_counts(record_counts_file)
        # Agrega por prefix de 3 chars (alias Protheus). Soma multi-empresa.
        by_alias: dict[str, int] = {}
        for rc in rc_rows:
            tn = rc["table_name"]
            if len(tn) < _PROTHEUS_ALIAS_LEN:
                continue
            alias = tn[:_PROTHEUS_ALIAS_LEN].upper()
            if alias.startswith(_NON_PROTHEUS_PREFIXES):
                continue
            by_alias[alias] = by_alias.get(alias, 0) + rc["num_rows"]
        updated = 0
        for alias, total in by_alias.items():
            cur = conn.execute(
                "UPDATE tabelas SET num_rows = ? WHERE upper(codigo) = ?",
                (total, alias),
            )
            updated += cur.rowcount
        conn.commit()
        counters["record_counts_updated"] = updated
        counters["record_counts_aliases"] = len(by_alias)
    except Exception as exc:  # boundary
        print(f"WARN: falha ao processar RECORD_COUNTS.csv: {exc}", file=sys.stderr)
        counters["record_counts_updated"] = 0


def _finalize_meta(conn: sqlite3.Connection, csv_dir: Path) -> None:
    """Refresh dos counters de meta (refletem estado final do DB) + timestamp."""
    for table, key in _META_KEY_BY_TABLE.items():
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        set_meta(conn, key, str(n))
    set_meta(conn, "last_sx_ingest_at", _iso_now())
    set_meta(conn, "sx_csv_dir", str(csv_dir))


def ingest_sx(
    csv_dir: Path,
    db_path: Path,
    *,
    progress_callback: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    """Pipeline completo: para cada CSV SX em ``csv_dir``, parse + insert no DB.

    Args:
        csv_dir: diretório contendo os CSVs (``sx1.csv``, ``sx2.csv``, ...).
            Lookup é case-insensitive (``SX2.csv`` também funciona).
        db_path: caminho do SQLite (criado se não existir; migrations aplicadas).
        progress_callback: opcional, chamado com ``(csv_name, rows_inserted)``
            após cada CSV concluído. Útil para CLI Rich progress bar.

    Returns:
        ``{csvs_total, csvs_ok, csvs_skipped, total_rows, duration_ms,
        per_table: {tabela: rows, ...}}``.

        Exemplo:

        .. code-block:: python

            counters = ingest_sx(Path("/d/Clientes/CSV"), Path("./.plugadvpl/index.db"))
            print(counters["per_table"]["campos"])  # → 80123
    """
    start_time = time.time()
    csv_dir = csv_dir.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    counters = _init_counters()
    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        _seed_meta_on_first_ingest(conn, csv_dir)
        seed_lookups(conn)

        for csv_name, table, columns in _SX_INGEST_PLAN:
            _ingest_one_csv_from_plan(
                conn,
                csv_dir,
                csv_name,
                table,
                columns,
                counters,
                progress_callback,
            )

        _update_grupos_campo_count(conn, counters)
        _update_record_counts_from_csv(conn, csv_dir, counters)
        _finalize_meta(conn, csv_dir)

        counters["duration_ms"] = int((time.time() - start_time) * 1000)
        return counters
    finally:
        close_db(conn)
