"""CLI entry point — typer app expondo 13 subcomandos.

Subcomandos (além de ``version``):

1. ``init``     — cria DB + escreve fragment ``CLAUDE.md`` + atualiza ``.gitignore``.
2. ``ingest``   — wrapper de :func:`plugadvpl.ingest.ingest`.
3. ``reindex``  — re-ingest de UM arquivo (filtra ``scan_sources``).
4. ``status``   — meta + contadores.
5. ``find``     — busca composta: function -> file -> FTS.
6. ``callers``  — quem chama ``F``.
7. ``callees``  — quem ``F`` chama.
8. ``tables``   — quem usa a tabela ``T`` (read|write|reclock).
9. ``param``    — quem usa o parâmetro ``MV_*``.
10. ``arch``    — resumo arquitetural de UM fonte.
11. ``lint``    — lint findings (filtros opcionais).
12. ``doctor``  — diagnósticos do índice.
13. ``grep``    — FTS5 main / trigram-like / identifier.

Opções globais (callback ``main_callback``): ``--root``, ``--format``, ``--quiet``,
``--db``, ``--limit``, ``--offset``, ``--compact``, ``--no-next-steps``.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, TypeVar, cast

import typer

from plugadvpl import __version__
from plugadvpl.catalog import catalog_list
from plugadvpl.catalog import catalog_query as q_catalog
from plugadvpl.catalog import ingest_tsv as do_ingest_tsv
from plugadvpl.db import (
    apply_migrations,
    close_db,
    get_meta,
    init_meta,
    open_db,
    seed_lookups,
    set_meta,
)
from plugadvpl.ingest import PARSER_VERSION, _write_parsed
from plugadvpl.ingest import ingest as do_ingest
from plugadvpl.ingest_ini import (
    DEFAULT_GLOBS as INI_DEFAULT_GLOBS,
)
from plugadvpl.ingest_ini import (
    discover_ini_paths,
    ingest_ini_paths,
)
from plugadvpl.ingest_log import (
    DEFAULT_LOG_GLOBS,
    discover_log_paths,
    ingest_log_paths,
)
from plugadvpl.ingest_poui import ingest_poui_dir
from plugadvpl.ingest_rest import ingest_via_rest as do_ingest_via_rest
from plugadvpl.ingest_sx import ingest_sx as do_ingest_sx
from plugadvpl.output import render
from plugadvpl.parsing import apis_build as apis_build_module
from plugadvpl.parsing import lint as lint_module
from plugadvpl.parsing import semantica as semantica_module
from plugadvpl.parsing.ini import parse_ini_file
from plugadvpl.parsing.ini_audit import audit_files as ini_audit_files
from plugadvpl.parsing.ini_known_keys import detect_unknown_keys
from plugadvpl.parsing.ini_report import render_ini_audit_html
from plugadvpl.parsing.ini_suggest import generate_suggested_ini
from plugadvpl.parsing.log import extract_header_metadata, scan_metrics
from plugadvpl.parsing.log_diagnose import diagnose_files as log_diagnose_files
from plugadvpl.parsing.log_report import render_log_diagnose_html
from plugadvpl.parsing.parser import parse_source
from plugadvpl.query import (
    arch as q_arch,
)
from plugadvpl.query import (
    callees as q_callees,
)
from plugadvpl.query import (
    callers as q_callers,
)
from plugadvpl.query import (
    cobertura_doc_query,
    doctor_diagnostics,
    doctor_func_count_check,
    execauto_calls_query,
    execauto_top_modulos,
    execution_triggers_duplicates,
    execution_triggers_query,
    find_any,
    fonte_indexada,
    gatilho_query,
    grep_fts,
    hotspots_query,
    impacto_query,
    ini_audit_fix_items,
    ini_audit_query,
    ini_audit_scores,
    ini_findings_enriched,
    ini_rules_keys,
    lint_query,
    log_diagnose_query,
    log_report_files,
    log_report_findings,
    metrics_query,
    param_query,
    protheus_doc_homonyms,
    protheus_doc_show,
    protheus_docs_orphans,
    protheus_docs_query,
    protheus_docs_top_modulos,
    render_pdoc_markdown,
    stale_files,
    sx_status,
    tables_query,
    trace_query,
)
from plugadvpl.query import (
    family as q_family,
)
from plugadvpl.query import (
    poui_bridge as q_poui_bridge,
)
from plugadvpl.query import (
    poui_componentes as q_poui_componentes,
)
from plugadvpl.query import (
    poui_iface_lint as q_poui_iface_lint,
)
from plugadvpl.query import (
    poui_import_lint as q_poui_import_lint,
)
from plugadvpl.query import (
    poui_interfaces as q_poui_interfaces,
)
from plugadvpl.query import (
    poui_lint as q_poui_lint,
)
from plugadvpl.query import (
    poui_projetos as q_poui_projetos,
)
from plugadvpl.query import (
    poui_schematics as q_poui_schematics,
)
from plugadvpl.query import (
    poui_version_lint as q_poui_version_lint,
)
from plugadvpl.query import (
    status as q_status,
)
from plugadvpl.query import (
    tables_catalog as q_tables_catalog,
)
from plugadvpl.scan import scan_sources

if TYPE_CHECKING:
    from collections.abc import Callable

    from plugadvpl.compile_servers import Server
    from plugadvpl.runtime_config import RuntimeConfig
    from plugadvpl.tq import TqResult

_T = TypeVar("_T")


app = typer.Typer(
    name="plugadvpl",
    help="Indexa fontes ADVPL/TLPP em SQLite + FTS5 para análise por LLM.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


class OutputFormat(StrEnum):
    """Formatos de saída suportados pelo renderer global."""

    json = "json"
    table = "table"
    md = "md"
    html = "html"


class GrepMode(StrEnum):
    """Modos do subcomando ``grep``."""

    fts = "fts"
    literal = "literal"
    identifier = "identifier"


class TableMode(StrEnum):
    """Modos do filtro ``--mode`` em ``tables``.

    ``write`` é abrangente (#61): inclui ``write_mvc``/``write_execauto``. Os dois
    últimos existem como filtro explícito quando se quer só gravação MVC/ExecAuto.
    """

    read = "read"
    write = "write"
    reclock = "reclock"
    write_mvc = "write_mvc"
    write_execauto = "write_execauto"


# v0.4.4 (UX #4): Enums pros filtros enumeráveis dos comandos Universo 3.
# Typer rejeita valores fora do enum antes de chegar na query (com mensagem
# clara listando as opções válidas) — substitui o comportamento antigo de
# silenciosamente retornar vazio em `--op invalida` / `--kind tipoinexistente`.


class WorkflowKind(StrEnum):
    """Kinds do comando ``workflow`` (Universo 3 Feature A)."""

    workflow = "workflow"
    wf_callback = "wf_callback"  # v0.4.6 (F): WFPrepEnv standalone separado
    schedule = "schedule"
    job_standalone = "job_standalone"
    mail_send = "mail_send"


class ExecAutoOp(StrEnum):
    """Operações do filtro ``--op`` em ``execauto`` (Universo 3 Feature B)."""

    inc = "inc"
    alt = "alt"
    exc = "exc"


# v0.5.0 (Universo 4 / Feature A): tipo do `trace` quando auto-detect erra.
# v0.5.3 (A.2): +3 entidades — arquivo/parametro/pergunte.
class TraceTipo(StrEnum):
    """Tipos de entidade aceitos pelo ``trace`` (Universo 4 Feature A)."""

    campo = "campo"
    funcao = "funcao"
    tabela = "tabela"
    arquivo = "arquivo"
    parametro = "parametro"
    pergunte = "pergunte"


# ---------------------------------------------------------------------------
# Callback global — popula ctx.obj com flags compartilhadas.
# ---------------------------------------------------------------------------


def _version_callback(value: bool) -> None:
    """Eager callback de ``--version``/`-V`: imprime e sai antes de exigir subcomando."""
    if value:
        typer.echo(f"plugadvpl {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: Annotated[  # noqa: ARG001 -- callback eager: handler em _version_callback, parametro nao e lido aqui
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Mostra a versão do binário e sai.",
        ),
    ] = False,
    root: Annotated[
        Path,
        typer.Option("--root", "-r", help="Raiz do projeto cliente."),
    ] = Path(),
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Formato de saída."),
    ] = OutputFormat.table,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suprime mensagens decorativas."),
    ] = False,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Caminho explícito do DB (default: <root>/.plugadvpl/index.db)."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Máximo de linhas por output. 0 = sem limite."),
    ] = 20,
    offset: Annotated[
        int,
        typer.Option("--offset", help="Pular N linhas antes do limit."),
    ] = 0,
    compact: Annotated[
        bool,
        typer.Option("--compact", help="Output compacto (sem indent JSON / linhas table)."),
    ] = False,
    no_next_steps: Annotated[
        bool,
        typer.Option("--no-next-steps", help="Desliga sugestões de próximo comando."),
    ] = False,
    privacy: Annotated[
        bool | None,
        typer.Option(
            "--privacy/--no-privacy",
            help="Mascara dados sensíveis (CPF/CNPJ/e-mail/segredo) na saída. "
            "Default: variável de ambiente PLUGADVPL_PRIVACY.",
        ),
    ] = None,
) -> None:
    """Opções globais aplicadas a todos os subcomandos via ``ctx.obj``."""
    from .privacy import PrivacyConfig

    ctx.ensure_object(dict)
    resolved_root = root.resolve()
    ctx.obj["root"] = resolved_root
    ctx.obj["format"] = format.value
    ctx.obj["quiet"] = quiet
    ctx.obj["db"] = db.resolve() if db else (resolved_root / ".plugadvpl" / "index.db")
    ctx.obj["limit"] = limit
    ctx.obj["offset"] = offset
    ctx.obj["compact"] = compact
    ctx.obj["next_steps_enabled"] = not no_next_steps
    ctx.obj["privacy"] = PrivacyConfig.from_env(enabled_override=privacy)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _open_ro(db_path: Path) -> sqlite3.Connection:
    """Abre o DB em modo read-only (URI ``mode=ro``).

    Para subcomandos puramente de leitura (``find``, ``callers``, etc.), evita
    qualquer hot-write no índice. Se o arquivo não existir, mostra mensagem
    amigável e sai com código 2.
    """
    if not db_path.exists():
        typer.secho(
            f"Erro: índice não encontrado em {db_path}.\n"
            "Rode 'plugadvpl init' e 'plugadvpl ingest' primeiro.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    uri = f"file:{db_path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _render_from_ctx(
    ctx: typer.Context,
    rows: list[dict[str, object]],
    *,
    columns: list[str] | None = None,
    title: str | None = None,
    next_steps: list[str] | None = None,
) -> None:
    """Wrapper que injeta as flags globais (``format``/``limit``/...) no render."""
    obj = ctx.obj
    render(
        rows,
        format=obj["format"],
        columns=columns,
        title=None if obj["quiet"] else title,
        limit=obj["limit"],
        offset=obj["offset"],
        compact=obj["compact"],
        next_steps=next_steps if obj["next_steps_enabled"] else None,
        privacy=obj.get("privacy"),
    )


def _mask_text_if_privacy(ctx: typer.Context, text: str) -> str:
    """Mascara um texto cru (ex.: relatório HTML montado fora do ``render``)
    quando a camada de privacidade está ligada. Cobre os caminhos que NÃO
    passam por ``_render_from_ctx`` — ini-audit/log-diagnose ``--format html``.
    """
    priv = ctx.obj.get("privacy")
    if priv is not None and priv.enabled:
        from .privacy import Masker

        return Masker(priv).mask_text(text)
    return text


def _with_ro_db(
    ctx: typer.Context,
    fn: Callable[[sqlite3.Connection], _T],
) -> _T:
    """Boilerplate: abre RO, executa ``fn(conn)``, fecha. Retorna o que ``fn``
    retornar (genérico em ``_T`` — handler decide a forma do payload)."""
    conn = _open_ro(ctx.obj["db"])
    try:
        return fn(conn)
    finally:
        conn.close()


def _augment_with_caminho(ctx: typer.Context, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """v0.4.6 (D): adiciona ``caminho`` (relativo) em cada row pra distinguir
    fontes homônimos. Coluna não aparece em table display (mantém layout
    enxuto) mas vai pro JSON — útil pra agente IA evitar ambiguidade
    quando basename colide entre subdiretórios."""
    if not rows:
        return rows
    arquivos = {r["arquivo"] for r in rows if r.get("arquivo")}
    if not arquivos:
        return rows
    placeholders = ",".join("?" * len(arquivos))
    sql = f"SELECT arquivo, caminho_relativo FROM fontes WHERE arquivo IN ({placeholders})"

    def _fetch(c: sqlite3.Connection) -> dict[str, str]:
        return {row[0]: row[1] or "" for row in c.execute(sql, list(arquivos))}

    mapping = _with_ro_db(ctx, _fetch)
    for r in rows:
        r["caminho"] = mapping.get(r.get("arquivo", ""), "")
    return rows


def _empty_result_hints(
    filters_applied: bool,
    *,
    table_label: str,
    extra_when_filtered: list[str] | None = None,
) -> list[str]:
    """Sugestões para resultado vazio (v0.4.4 UX #3).

    Diferencia 2 cenários:

    - ``filters_applied=True``: filtro semanticamente vazio (ex.: --arquivo
      inexistente) → sugere verificar o filtro, NÃO sugere reingest caro.
    - ``filters_applied=False``: tabela realmente vazia → sugere reingest.

    Args:
        filters_applied: True se o usuário passou pelo menos 1 filtro.
        table_label: rótulo amigável da tabela (ex.: "triggers", "calls").
        extra_when_filtered: hints adicionais úteis quando filtrado
            (ex.: ``--dynamic`` pra execauto).
    """
    if filters_applied:
        hints = [
            "Filtro retornou vazio. Verifique se os argumentos batem com o índice:",
            "  plugadvpl find <termo>           # confirma nome",
            "  plugadvpl status                  # ver contadores",
        ]
        if extra_when_filtered:
            hints.extend(extra_when_filtered)
        return hints
    return [
        f"Nenhum {table_label} no índice. Rode:",
        "  plugadvpl ingest --no-incremental",
    ]


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Imprime versão da CLI."""
    typer.echo(f"plugadvpl {__version__}")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

_CLAUDE_FRAGMENT_BEGIN = "<!-- BEGIN plugadvpl -->"
_CLAUDE_FRAGMENT_END = "<!-- END plugadvpl -->"
# v0.3.23 (#1 do QA round 3): marker de versão dentro do fragment.
# `_write_claude_md_fragment` substitui `__VERSION__` por `__version__` real
# na hora de gravar; `_check_fragment_staleness` (em status) le este marker
# pra detectar fragments gerados por versoes antigas e avisar o usuario.
# v0.4.6 (J): regex restrita ao formato SemVer/PEP440 (X.Y.Z + opcional trailing
# safe chars: dev/rc/pre/build). Antes era \d.+-\\S* que permitia qualquer
# non-whitespace, incluindo conteudo malicioso/corrompido em fragment editado a mao.
# Aceita: 0.4.5, 0.4.5-rc1, 0.4.5+build.123, 0.1.1.dev2+ga... (setuptools-scm dev).
_CLAUDE_FRAGMENT_VERSION_MARKER_RE = re.compile(
    r"<!--\s*plugadvpl-fragment-version:\s*(\d+\.\d+\.\d+[\w.+-]*)\s*-->"
)
_CLAUDE_FRAGMENT_BODY = """<!-- plugadvpl-fragment-version: __VERSION__ -->
## Plugadvpl — índice ADVPL local (LEIA ANTES de qualquer Read em .prw/.tlpp)

Este projeto possui um índice SQLite em `.plugadvpl/index.db` com metadados extraídos
de TODOS os fontes ADVPL/TLPP do projeto: funções, tabelas referenciadas (read/write/reclock),
campos, parâmetros MV_*, perguntas SX1, call graph (U_*, ExecBlock, MsExecAuto, FWLoadModel,
FWExecView, métodos), SQL embarcado, includes, capabilities (MVC/JOB/REST/PE/...) e lint findings.

### REGRA DURA — SEM EXCEÇÃO

**Antes de chamar `Read` em qualquer `.prw`/`.tlpp`/`.prx`, você DEVE rodar primeiro
um comando do plugadvpl** (via `Bash plugadvpl ...` ou `/plugadvpl:*` se houver slash).
Fontes Protheus têm tipicamente 1.000-10.000 linhas; lê-los inteiros queima contexto e
produz respostas vagas. O índice te dá o resumo em ~200 tokens em vez de 10.000.

Só leia o `.prw` cru depois de localizar a faixa de linhas exata via índice
(ex: `Read FATA050.prw` com offset/limit baseados em `linha_inicio`/`linha_fim` que
o `arch` retorna).

### Tabela de decisão — qual comando usar para qual pergunta

| Pergunta do usuário                                         | Rode PRIMEIRO                                  |
|-------------------------------------------------------------|------------------------------------------------|
| "explique o fonte X" / "o que faz Y"                        | `plugadvpl arch <arq>`                         |
| "onde está a função X?" / "tem um programa ABCTAC12, ..."   | `plugadvpl find <nome>`                        |
| "quais fontes chamam X?" / "quem usa X?"                    | `plugadvpl callers <funcao>`                   |
| "o que X chama por dentro?" / "quais dependências de X?"    | `plugadvpl callees <funcao>`                   |
| "quem mexe na tabela SA1?" / "quem grava em SC5?"           | `plugadvpl tables SA1` (ou `--write/--reclock`)|
| "quais parâmetros MV_* X usa?" / "onde MV_LOCALIZA é usado?"| `plugadvpl param MV_LOCALIZA`                  |
| "achar fonte com 'RecLock' / 'BeginSql' / etc"              | `plugadvpl grep <termo>` (modos `-m fts\\|literal\\|identifier`)      |
| "tem problemas / boas práticas neste fonte?"                | `plugadvpl lint [arq] [--severity critical]`   |
| "essa função é nativa do Protheus?"                         | `plugadvpl native <nome>`                      |
| "posso usar StaticCall / função X?"                         | `plugadvpl restricted <nome>`                  |

### Workflow padrão para "explique o programa X"

Quando o usuário pedir para explicar/analisar um programa (ex: "tenho um programa ABCTAC12,
quais fontes chama, parâmetros, etc"):

1. `plugadvpl find ABCTAC12` — descobre em qual arquivo está
2. `plugadvpl arch <arquivo encontrado>` — visão geral (capabilities, funções, tabelas, includes)
3. `plugadvpl callees ABCTAC12` — o que ele chama (call graph saindo)
4. `plugadvpl callers ABCTAC12` — quem chama ele (call graph entrando)
5. `plugadvpl tables <tabela_principal>` — para cada tabela relevante, ver outros que tocam
6. `plugadvpl param <MV_X>` — para cada MV_* relevante, ver o uso global
7. **Só depois**, se ainda restar dúvida, ler com `Read <arquivo>` usando os ranges de linha
   identificados (ex: `linha_inicio`/`linha_fim` de uma função específica do `arch`).

Sintetize o que encontrar nos passos 1-6 num parágrafo: o que faz + dependências + impacto.
**NUNCA pule direto para `Read` do `.prw` inteiro.**

### Como rodar

- **Sempre disponível** (CLI Python, basta `uv` instalado):
  `Bash -> plugadvpl <subcomando> ...` ou `uvx plugadvpl@<versão> <subcomando> ...`
- **Se o plugin Claude Code estiver instalado** (recomendado para UX):
  use os slash commands `/plugadvpl:arch`, `/plugadvpl:find`, etc.

Para ver versão / status do índice: `plugadvpl status`. Para ver todos os comandos:
`plugadvpl --help`.

### Output format — IMPORTANTE para agentes IA

A flag global `--format` aceita 3 valores e **vem ANTES do subcomando** (é do callback):

- `--format table` (default) — Rich em **stderr**, **trunca** colunas em terminais
  estreitos (você vê `ar...`, `ti...`, `ca...`). OK para humano interativo.
- `--format md` — Markdown em **stdout**, **sem truncamento**. **Recomendado para Claude/agentes IA**: limpo, parseável visualmente, vai pro stdout.
- `--format json` — JSON em **stdout**, sem truncamento. Use para parsing programático (jq, scripts).

Padrões inválidos comuns (não tente):

- `plugadvpl arch X --json` → flag `--json` **não existe**. Correto: `plugadvpl --format json arch X`.
- `$env:COLUMNS=400; plugadvpl ...` → workaround frágil; mistura sintaxe PS/Bash. Correto: `--format md`.
- Posicionar `--format` depois do subcomando funciona em alguns casos mas é frágil — **sempre** antes do subcomando.

### Encoding — ⚠️ CRÍTICO para Edit/Write em .prw cp1252

Fontes legados são `cp1252` (`.prw`/`.prx`). TLPP moderno (`.tlpp`) é `utf-8`.

**🚨 PERIGO**: Read/Edit tools do Claude Code são **UTF-8 only**. Quando lêem `.prw`
cp1252, bytes acentuados (0x80-0xFF) viram `�` (U+FFFD). Se você fizer `Edit` nessa
visão, o `Edit` regrava o arquivo **inteiro** em UTF-8 — incluindo os `�` no lugar
dos acentos não-editados. **Acentos não-editados ficam corrompidos.**

**Workflow obrigatório pra editar `.prw` cp1252 com Claude (Caminho A — stage/commit)**:

```bash
# 1. ANTES de Read/Edit — converte cp1252 -> utf-8 (cria .bak com original)
plugadvpl edit-prw stage <fonte.prw>

# 2. Agora Read mostra acentos certos. Edit/Write operam sem perda.

# 3. DEPOIS das edições — volta pra cp1252 (acentos novos viram bytes corretos)
plugadvpl edit-prw commit <fonte.prw>
```

Alternativas em `skills/edit-prw/SKILL.md` e `skills/advpl-encoding/SKILL.md`.

Quando NÃO precisa stage/commit: `.tlpp` (utf-8 nativo), `.prw` que `edit-prw check`
mostra `utf-8`, edição via PowerShell/script externo, arquivo ASCII puro sem acentos.

### Manutenção do índice

- `plugadvpl status [--check-stale]` — ver totais e arquivos desatualizados
- `plugadvpl reindex <arq>` — após editar um fonte
- `plugadvpl ingest --incremental` — ingest novamente arquivos modificados (default)
- `plugadvpl doctor` — diagnósticos (encoding suspeito, FTS5, órfãos)
"""


@app.command()
def init(
    ctx: typer.Context,
    no_cursor: Annotated[
        bool,
        typer.Option(
            "--no-cursor",
            help="Não instala Cursor rules mesmo se Cursor for detectado (~/.cursor/ ou .cursor/ no projeto).",
        ),
    ] = False,
    no_copilot: Annotated[
        bool,
        typer.Option(
            "--no-copilot",
            help="Não instala Copilot instructions mesmo se `.github/` for detectado.",
        ),
    ] = False,
    no_gemini: Annotated[
        bool,
        typer.Option(
            "--no-gemini",
            help="Não instala Gemini skills mesmo se Gemini for detectado (~/.gemini/, gemini no PATH, ou .gemini/ no projeto).",
        ),
    ] = False,
    no_codex: Annotated[
        bool,
        typer.Option(
            "--no-codex",
            help="Não instala .codex/config.toml mesmo se Codex for detectado (.codex/ no projeto ou codex no PATH).",
        ),
    ] = False,
) -> None:
    """Cria ``./.plugadvpl/index.db``, escreve fragments em ``CLAUDE.md`` + ``AGENTS.md``, atualiza ``.gitignore``, e (se detectado) gera Cursor rules + Copilot instructions + Gemini skills.

    v0.16.1: ``CLAUDE.md`` + ``AGENTS.md`` fragments.
    v0.16.2: Cursor rules nativos em ``.cursor/rules/``.
    v0.16.3: Copilot instructions em ``.github/copilot-instructions.md`` +
    ``.github/instructions/plugadvpl-*.instructions.md`` quando ``.github/``
    existe no projeto. Use ``--no-copilot`` pra desabilitar.
    v0.16.4: Gemini skills em ``~/.gemini/GEMINI.md`` + ``<project>/GEMINI.md`` +
    ``.gemini/skills/plugadvpl-*/SKILL.md`` quando Gemini é detectado.
    Use ``--no-gemini`` pra desabilitar.
    v0.16.5: ``.codex/config.toml`` mínimo quando Codex CLI é detectado
    (``.codex/`` no projeto ou ``codex`` no PATH). Use ``--no-codex`` pra desabilitar.
    """
    root: Path = ctx.obj["root"]
    db_path: Path = ctx.obj["db"]
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        init_meta(conn, project_root=str(root), cli_version=__version__)
        seed_lookups(conn)
    finally:
        close_db(conn)

    _write_agent_fragment(root, "CLAUDE.md")
    _write_agent_fragment(root, "AGENTS.md")
    _add_to_gitignore(root, ".plugadvpl/")

    if not ctx.obj["quiet"]:
        typer.echo(f"OK  DB criado em {db_path}")
        typer.echo("OK  CLAUDE.md + AGENTS.md atualizados (fragment plugadvpl, idênticos)")
        typer.echo("OK  .plugadvpl/ adicionado ao .gitignore")

    quiet = ctx.obj["quiet"]
    if not no_cursor:
        _install_cursor_for_init(root, quiet)
    if not no_copilot:
        _install_copilot_for_init(root, quiet)
    if not no_gemini:
        _install_gemini_for_init(root, quiet)
    if not no_codex:
        _install_codex_for_init(root, quiet)


def _install_cursor_for_init(root: Path, quiet: bool) -> None:
    """Helper extraido de init() pra manter PLR0912 <=12 com 3 agentes."""
    from plugadvpl.cursor_rules import install_cursor_rules

    cursor_result = install_cursor_rules(root, __version__)
    if quiet:
        return
    if cursor_result.installed_global or cursor_result.installed_local_count:
        typer.echo(f"OK  Cursor rules: {cursor_result.summary()}")
    for warn in cursor_result.errors:
        typer.secho(f"⚠  Cursor rules: {warn}", fg=typer.colors.YELLOW, err=True)
    for skipped in cursor_result.skipped_due_to_user_files:
        typer.secho(
            f"⚠  Cursor rules: {skipped} já existe sem marker plugadvpl — não sobrescrevi",
            fg=typer.colors.YELLOW,
            err=True,
        )


def _install_copilot_for_init(root: Path, quiet: bool) -> None:
    """Helper extraido de init() pra manter PLR0912 <=12 com 3 agentes."""
    from plugadvpl.copilot_instructions import install_copilot_instructions

    copilot_result = install_copilot_instructions(root, __version__)
    if quiet:
        return
    if copilot_result.installed_global or copilot_result.installed_local_count:
        typer.echo(f"OK  Copilot instructions: {copilot_result.summary()}")
    for warn in copilot_result.errors:
        typer.secho(
            f"⚠  Copilot instructions: {warn}",
            fg=typer.colors.YELLOW,
            err=True,
        )
    for skipped in copilot_result.skipped_due_to_user_files:
        typer.secho(
            f"⚠  Copilot instructions: {skipped} já existe sem marker plugadvpl — não sobrescrevi",
            fg=typer.colors.YELLOW,
            err=True,
        )


def _install_gemini_for_init(root: Path, quiet: bool) -> None:
    """Helper extraido de init() pra manter PLR0912 <=12 com 3 agentes."""
    from plugadvpl.gemini_skills import install_gemini_skills

    gemini_result = install_gemini_skills(root, __version__)
    if quiet:
        return
    if (
        gemini_result.installed_global_home
        or gemini_result.installed_project_md
        or gemini_result.installed_skills_count
    ):
        typer.echo(f"OK  Gemini skills: {gemini_result.summary()}")
    for warn in gemini_result.errors:
        typer.secho(
            f"⚠  Gemini skills: {warn}",
            fg=typer.colors.YELLOW,
            err=True,
        )
    for skipped in gemini_result.skipped_due_to_user_files:
        typer.secho(
            f"⚠  Gemini skills: {skipped} já existe sem marker plugadvpl — não sobrescrevi",
            fg=typer.colors.YELLOW,
            err=True,
        )


def _install_codex_for_init(root: Path, quiet: bool) -> None:
    """Helper extraido de init() pra manter PLR0912 baixo com Codex (v0.16.5)."""
    from plugadvpl.codex_config import install_codex_config

    codex_result = install_codex_config(root, __version__)
    if quiet:
        return
    if codex_result.installed:
        typer.echo(f"OK  Codex: {codex_result.summary()}")
    if codex_result.error:
        typer.secho(
            f"⚠  Codex: {codex_result.error}",
            fg=typer.colors.YELLOW,
            err=True,
        )
    if codex_result.skipped_due_to_user_file:
        typer.secho(
            "⚠  Codex: .codex/config.toml já existe sem marker plugadvpl — não sobrescrevi",
            fg=typer.colors.YELLOW,
            err=True,
        )


_CURSOR_RULE_MARKER_RE = re.compile(
    r"<!--\s*plugadvpl-rule-version:\s*(\d+\.\d+\.\d+[\w.+-]*)\s*-->"
)


def _check_cursor_rules_staleness(root: Path) -> str | None:
    """Verifica Cursor rules (global ~/.cursor + locais <project>/.cursor)."""
    cursor_files: list[Path] = []
    try:
        home_global = Path.home() / ".cursor" / "rules" / "plugadvpl.mdc"
        if home_global.exists():
            cursor_files.append(home_global)
    except RuntimeError:
        pass
    local_rules_dir = root / ".cursor" / "rules"
    if local_rules_dir.exists():
        cursor_files.extend(sorted(local_rules_dir.glob("plugadvpl-*.mdc")))

    for cf in cursor_files:
        try:
            content = cf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = _CURSOR_RULE_MARKER_RE.search(content)
        if m is None:
            continue  # arquivo sem marker — não é nosso, skip
        rule_version = m.group(1)
        if rule_version != __version__:
            return f"{cf.name} foi gerado por plugadvpl {rule_version}"
    return None


def _check_copilot_instructions_staleness(root: Path) -> str | None:
    """Detecta Copilot instructions desatualizadas.

    Cobre `.github/copilot-instructions.md` (global) e
    `.github/instructions/plugadvpl-*.instructions.md` (locais).
    Retorna mensagem do primeiro arquivo desatualizado, ou None.

    Marker é `<!-- plugadvpl-instructions-version: X.Y.Z -->` —
    distinto do Cursor `rule-version`, evita falso-positivo cross-agent.
    """
    copilot_files: list[Path] = []
    copilot_global = root / ".github" / "copilot-instructions.md"
    if copilot_global.exists():
        copilot_files.append(copilot_global)
    copilot_dir = root / ".github" / "instructions"
    if copilot_dir.exists():
        copilot_files.extend(sorted(copilot_dir.glob("plugadvpl-*.instructions.md")))

    inst_marker_re = re.compile(
        r"<!--\s*plugadvpl-instructions-version:\s*(\d+\.\d+\.\d+[\w.+-]*)\s*-->"
    )
    for cf in copilot_files:
        try:
            content = cf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = inst_marker_re.search(content)
        if m is None:
            continue
        inst_version = m.group(1)
        if inst_version != __version__:
            return f"{cf.name} foi gerado por plugadvpl {inst_version}"
    return None


def _check_gemini_staleness(root: Path) -> str | None:
    """Detecta Gemini files desatualizados.

    Cobre `~/.gemini/GEMINI.md` (global), `<project>/GEMINI.md` (projeto),
    e `<project>/.gemini/skills/plugadvpl-*/SKILL.md` (specifics).
    Retorna mensagem do primeiro arquivo desatualizado, ou None.

    Marker é `<!-- plugadvpl-gemini-version: X.Y.Z -->` — distinto do
    Cursor `rule-version`, Copilot `instructions-version`, e
    fragment-version do CLAUDE.md/AGENTS.md. Evita falso-positivo cross-agent.
    """
    gemini_files: list[Path] = []
    try:
        home_global = Path.home() / ".gemini" / "GEMINI.md"
        if home_global.exists():
            gemini_files.append(home_global)
    except RuntimeError:
        pass
    project_md = root / "GEMINI.md"
    if project_md.exists():
        gemini_files.append(project_md)
    skills_dir = root / ".gemini" / "skills"
    if skills_dir.exists():
        # Glob recursivo: .gemini/skills/plugadvpl-<X>/SKILL.md
        gemini_files.extend(sorted(skills_dir.glob("plugadvpl-*/SKILL.md")))

    marker_re = re.compile(r"<!--\s*plugadvpl-gemini-version:\s*(\d+\.\d+\.\d+[\w.+-]*)\s*-->")
    for gf in gemini_files:
        try:
            content = gf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = marker_re.search(content)
        if m is None:
            continue
        v = m.group(1)
        if v != __version__:
            return f"{gf.name} foi gerado por plugadvpl {v}"
    return None


def _check_fragment_staleness(root: Path) -> str | None:
    """Retorna mensagem descritiva se algum fragment plugadvpl está desatualizado.

    v0.3.23: marker `<!-- plugadvpl-fragment-version: X.Y.Z -->` em CLAUDE.md.
    v0.16.1: estende pra AGENTS.md.
    v0.16.2: estende pra Cursor rules (global em ~/.cursor/rules/plugadvpl.mdc
    e locais em <project>/.cursor/rules/plugadvpl-*.mdc).
    v0.16.3: estende pra Copilot instructions
    (`.github/copilot-instructions.md` global e
    `.github/instructions/plugadvpl-*.instructions.md` locais).
    v0.16.4: estende pra Gemini skills (`~/.gemini/GEMINI.md` global,
    `<project>/GEMINI.md` projeto, e
    `<project>/.gemini/skills/plugadvpl-*/SKILL.md` specifics).

    Reporta o primeiro arquivo desatualizado encontrado. None se todos OK ou
    se nenhum dos arquivos existe (caso fresh sem init ainda).
    """
    # 1. CLAUDE.md + AGENTS.md (fragment-version)
    for filename in ("CLAUDE.md", "AGENTS.md"):
        target = root / filename
        if not target.exists():
            continue
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _CLAUDE_FRAGMENT_BEGIN not in content or _CLAUDE_FRAGMENT_END not in content:
            continue
        start = content.index(_CLAUDE_FRAGMENT_BEGIN)
        end = content.index(_CLAUDE_FRAGMENT_END) + len(_CLAUDE_FRAGMENT_END)
        fragment = content[start:end]
        m = _CLAUDE_FRAGMENT_VERSION_MARKER_RE.search(fragment)
        if m is None:
            return f"{filename} é de versão pré-v0.3.23 (sem marker de versionamento)"
        fragment_version = m.group(1)
        if fragment_version != __version__:
            return f"{filename} foi gerado por plugadvpl {fragment_version}"

    # 2. Cursor rules (rule-version)
    cursor_msg = _check_cursor_rules_staleness(root)
    if cursor_msg is not None:
        return cursor_msg

    # 3. Copilot instructions (instructions-version)
    copilot_msg = _check_copilot_instructions_staleness(root)
    if copilot_msg is not None:
        return copilot_msg

    # 4. Gemini skills (gemini-version)
    gemini_msg = _check_gemini_staleness(root)
    if gemini_msg is not None:
        return gemini_msg

    return None


def _write_agent_fragment(root: Path, filename: str) -> None:
    """Escreve/atualiza idempotentemente a região ``BEGIN/END plugadvpl`` em ``filename``.

    v0.3.23: substitui `__VERSION__` no body por `__version__` real do binario
    pra que o `status` consiga detectar fragment desatualizado depois.

    v0.16.1: parametrizado pra suportar múltiplos agentes — Claude Code lê
    ``CLAUDE.md``; Cursor/GitHub Copilot/Codex leem ``AGENTS.md``. Conteúdo do
    fragment é idêntico, só o arquivo destino muda.
    """
    target = root / filename
    body_with_version = _CLAUDE_FRAGMENT_BODY.replace("__VERSION__", __version__)
    fragment = _CLAUDE_FRAGMENT_BEGIN + "\n" + body_with_version + _CLAUDE_FRAGMENT_END + "\n"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        if _CLAUDE_FRAGMENT_BEGIN in content and _CLAUDE_FRAGMENT_END in content:
            content = re.sub(
                re.escape(_CLAUDE_FRAGMENT_BEGIN) + r".*?" + re.escape(_CLAUDE_FRAGMENT_END),
                fragment.rstrip("\n"),
                content,
                flags=re.DOTALL,
            )
        else:
            sep = "" if content.endswith("\n") else "\n"
            content = content + sep + "\n" + fragment
        target.write_text(content, encoding="utf-8")
    else:
        target.write_text(fragment, encoding="utf-8")


def _add_to_gitignore(root: Path, line: str) -> None:
    """Adiciona ``line`` em ``.gitignore`` se ainda não existir.

    Não cria ``.gitignore`` se ainda não existe (evita poluir projetos sem git).
    """
    gi = root / ".gitignore"
    if not gi.exists():
        return
    existing = gi.read_text(encoding="utf-8")
    if line in existing.splitlines():
        return
    sep = "" if existing.endswith("\n") or not existing else "\n"
    with gi.open("a", encoding="utf-8") as f:
        f.write(sep + line + "\n")


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


@app.command()
def ingest(
    ctx: typer.Context,
    workers: Annotated[
        int | None,
        typer.Option(
            "--workers",
            "-w",
            help="N workers (0 = single-thread; None = adaptive).",
        ),
    ] = None,
    incremental: Annotated[
        bool,
        typer.Option(
            "--incremental/--no-incremental",
            help="Pula arquivos cujo mtime no DB é >= ao filesystem.",
        ),
    ] = True,
    no_content: Annotated[
        bool,
        typer.Option("--no-content", help="Não persiste corpo dos chunks (apenas metadata)."),
    ] = False,
    redact_secrets: Annotated[
        bool,
        typer.Option("--redact-secrets", help="Mascara URLs com credenciais e tokens hex."),
    ] = False,
) -> None:
    """Indexa todos os fontes em ``--root`` (scan -> parse -> SQLite -> FTS5 rebuild)."""
    root: Path = ctx.obj["root"]
    counters = do_ingest(
        root,
        workers=workers,
        incremental=incremental,
        no_content=no_content,
        redact_secrets=redact_secrets,
    )

    summary: dict[str, object] = {
        "arquivos_total": counters["arquivos_total"],
        "ok": counters["arquivos_ok"],
        "skipped": counters["arquivos_skipped"],
        "failed": counters["arquivos_failed"],
        "chunks": counters["chunks"],
        "chamadas": counters["chamadas"],
        "lint_findings": counters["lint_findings"],
        "duration_ms": counters["duration_ms"],
    }
    _render_from_ctx(
        ctx,
        [summary],
        title="Ingest summary",
        next_steps=[
            "plugadvpl status",
            "plugadvpl find <termo>",
        ],
    )

    # v0.3.13 — pegadinha do --incremental após bump de lookups: arquivos pulados
    # NÃO são re-avaliados contra regras de lint novas. Detectamos via mudança no
    # lookup_bundle_hash + qualquer arquivo skipped + modo incremental.
    if (
        incremental
        and counters.get("lookup_hash_changed")
        and counters["arquivos_skipped"] > 0
        and not ctx.obj["quiet"]
    ):
        skipped = counters["arquivos_skipped"]
        typer.secho(
            f"\n⚠ Lookups (lint_rules/funcoes_restritas/...) mudaram desde o último ingest.\n"
            f"  --incremental pulou {skipped} arquivo(s) cujo mtime não mudou — "
            f"esses NÃO foram re-avaliados contra as regras novas.\n"
            f"  Para cobrir todo o codebase com as regras atualizadas, rode:\n"
            f"      plugadvpl ingest --no-incremental",
            fg=typer.colors.YELLOW,
            err=True,
        )


# ---------------------------------------------------------------------------
# reindex
# ---------------------------------------------------------------------------


@app.command()
def reindex(
    ctx: typer.Context,
    arq: Annotated[str, typer.Argument(help="Basename ou caminho relativo do arquivo.")],
) -> None:
    """Re-ingest de UM arquivo. Útil após edição manual.

    Implementação: chama :func:`plugadvpl.ingest.ingest` apontando para o
    diretório que contém o arquivo, com ``incremental=False`` para forçar
    reescrita.
    """
    root: Path = ctx.obj["root"]
    candidates = scan_sources(root)
    target = next((p for p in candidates if p.name.lower() == arq.lower()), None)
    if target is None:
        # tenta resolver como path direto
        candidate = (root / arq).resolve()
        if candidate.exists():
            target = candidate
    if target is None or not target.exists():
        typer.secho(f"Arquivo '{arq}' não encontrado em {root}.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    # Force-write apenas do alvo via _write_parsed em conexão direta.
    db_path: Path = ctx.obj["db"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = open_db(db_path)
    counters: dict[str, int] = {
        "arquivos_total": 1,
        "arquivos_ok": 0,
        "arquivos_skipped": 0,
        "arquivos_failed": 0,
        "chunks": 0,
        "chamadas": 0,
        "params": 0,
        "lint_findings": 0,
    }
    try:
        apply_migrations(conn)
        init_meta(conn, project_root=str(root), cli_version=__version__)
        seed_lookups(conn)
        set_meta(conn, "parser_version", PARSER_VERSION)
        try:
            parsed = parse_source(target)
            content = target.read_text(encoding=parsed.get("encoding", "cp1252"), errors="replace")
            findings = lint_module.lint_source(parsed, content)
            _write_parsed(
                conn,
                root,
                target,
                parsed,
                content,
                findings,
                counters,
                no_content=False,
                redact_secrets=False,
            )
        except Exception as exc:
            counters["arquivos_failed"] += 1
            typer.secho(f"Falha ao reindexar {target.name}: {exc}", fg=typer.colors.RED, err=True)
        # Rebuild FTS para refletir mudança.
        conn.execute("INSERT INTO fonte_chunks_fts(fonte_chunks_fts) VALUES('rebuild')")
        conn.execute("INSERT INTO fonte_chunks_fts_tri(fonte_chunks_fts_tri) VALUES('rebuild')")
        conn.commit()
    finally:
        close_db(conn)

    _render_from_ctx(
        ctx,
        [
            {
                "arquivo": target.name,
                "ok": counters["arquivos_ok"],
                "failed": counters["arquivos_failed"],
                "chunks": counters["chunks"],
                "chamadas": counters["chamadas"],
                "lint_findings": counters["lint_findings"],
            }
        ],
        title=f"Reindex {target.name}",
        next_steps=[f"plugadvpl arch {target.name}"],
    )


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@app.command()
def status(
    ctx: typer.Context,
    check_stale: Annotated[
        bool,
        typer.Option("--check-stale", help="Compara mtime do filesystem com DB."),
    ] = False,
) -> None:
    """Mostra estado do índice (versões, contadores, opcionalmente arquivos stale)."""
    root: Path = ctx.obj["root"]
    rows = _with_ro_db(ctx, lambda c: q_status(c, str(root), __version__))
    _render_from_ctx(ctx, rows, title="Status do índice")

    # #75: catálogos importados via ingest-tsv (se houver).
    if not ctx.obj["quiet"]:
        cats = _with_ro_db(ctx, catalog_list)
        if cats:
            typer.secho("\nCatálogos (ingest-tsv):", err=True)
            for cat in cats:
                sx = f" ↔ SX {cat['sx_table']}" if cat["sx_table"] else ""
                typer.secho(f"  {cat['alias']}: {cat['row_count']} linhas{sx}", err=True)

    # Aviso de divergência runtime ↔ índice — fecha o gap "binário foi atualizado
    # via uv tool upgrade mas o status ainda mostra a versão antiga gravada".
    if rows and not ctx.obj["quiet"]:
        runtime = rows[0].get("runtime_version")
        stored = rows[0].get("plugadvpl_version")
        if runtime and stored and runtime != stored:
            typer.secho(
                f"\n⚠ Índice criado com plugadvpl {stored}, binário atual é {runtime}.\n"
                f"  Rode 'plugadvpl ingest --incremental' para atualizar o índice "
                f"com regras/parsers da versão nova.",
                fg=typer.colors.YELLOW,
                err=True,
            )

        # v0.3.23 (#1 do QA round 3): aviso quando o fragment do CLAUDE.md ficou
        # pra trás do binário (gerado por init de versão antiga). Consulta o
        # arquivo, extrai o marker `<!-- plugadvpl-fragment-version: X.Y.Z -->`,
        # e compara com __version__. Marker ausente também avisa (fragments
        # pre-v0.3.23 não tinham versionamento).
        fragment_state = _check_fragment_staleness(root)
        if fragment_state is not None:
            typer.secho(
                f"\n⚠ Fragment do CLAUDE.md {fragment_state}, binário atual é {__version__}.\n"
                f"  Rode 'plugadvpl init' para regenerar o fragment com a versão atual\n"
                f"  (sobrescreve só a região BEGIN/END plugadvpl; resto do CLAUDE.md preservado).",
                fg=typer.colors.YELLOW,
                err=True,
            )

    if check_stale:
        try:
            files = scan_sources(root)
            fs_state = {f.name: f.stat().st_mtime_ns for f in files if f.exists()}
        except OSError as exc:
            typer.secho(f"Erro ao escanear filesystem: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from exc
        stale = _with_ro_db(ctx, lambda c: stale_files(c, fs_state))
        _render_from_ctx(
            ctx,
            stale,
            columns=["arquivo", "estado", "db_mtime", "fs_mtime"],
            title="Arquivos stale/novos/deletados",
            next_steps=[f"plugadvpl ingest --root {root}"] if stale else None,
        )


# ---------------------------------------------------------------------------
# find
# ---------------------------------------------------------------------------


@app.command()
def find(
    ctx: typer.Context,
    termo: Annotated[str, typer.Argument(help="Nome de função, fragmento de arquivo ou texto.")],
) -> None:
    """Busca composta: tenta função -> arquivo -> conteúdo (FTS)."""

    rows = _with_ro_db(ctx, lambda c: find_any(c, termo))
    _render_from_ctx(
        ctx,
        rows,
        title=f"Resultados para '{termo}'",
        next_steps=(
            [
                f"plugadvpl arch {rows[0].get('arquivo', '<arq>')}",
                f"plugadvpl callers {termo}",
            ]
            if rows
            else None
        ),
    )


@app.command()
def family(
    ctx: typer.Context,
    prefixo: Annotated[str, typer.Argument(help="Prefixo do basename (ex: MOD12) ou glob (FAT*).")],
    include_tables: Annotated[
        bool,
        typer.Option(
            "--include-tables",
            help="Acrescenta colunas tables_read (top-N) e tables_write (com tag mvc/execauto).",
        ),
    ] = False,
    max_tables: Annotated[
        int,
        typer.Option("--max-tables", help="Top-N de reads por fonte (default 3)."),
    ] = 3,
    custom_only: Annotated[
        bool,
        typer.Option("--custom-only", help="Só tabelas custom (Z*/SZ*); esconde padrão TOTVS."),
    ] = False,
) -> None:
    """Descobre a família de fontes por prefixo de nome (tipo + LoC + capabilities + descrição).

    Com ``--include-tables`` (#72): mostra também as tabelas lidas/gravadas de cada
    fonte — panorama do processo inteiro numa tela, sem rodar ``arch`` por fonte.
    """

    rows = _with_ro_db(
        ctx,
        lambda c: q_family(
            c,
            prefixo,
            include_tables=include_tables,
            max_tables=max_tables,
            custom_only=custom_only,
        ),
    )
    if not rows:
        typer.secho(f"Nenhum fonte com prefixo '{prefixo}'.", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1)
    _render_from_ctx(
        ctx,
        rows,
        title=f"Família '{prefixo}' ({len(rows)} fontes)",
        next_steps=[f"plugadvpl arch {rows[0]['arquivo']} --include-header"],
    )


# ---------------------------------------------------------------------------
# callers / callees
# ---------------------------------------------------------------------------


@app.command()
def callers(
    ctx: typer.Context,
    funcao: Annotated[str, typer.Argument(help="Nome da função alvo.")],
) -> None:
    """Lista quem chama ``funcao`` (lookup em ``chamadas_funcao``)."""

    rows = _with_ro_db(ctx, lambda c: q_callers(c, funcao))
    _render_from_ctx(
        ctx,
        rows,
        title=f"Callers de {funcao}",
        next_steps=[f"plugadvpl find {funcao}"] if not rows else None,
    )


@app.command()
def callees(
    ctx: typer.Context,
    funcao: Annotated[str, typer.Argument(help="Nome da função (ou basename de fonte).")],
) -> None:
    """Lista quem ``funcao`` chama (lookup em ``chamadas_funcao``)."""

    rows = _with_ro_db(ctx, lambda c: q_callees(c, funcao))
    _render_from_ctx(
        ctx,
        rows,
        title=f"Callees de {funcao}",
        next_steps=[f"plugadvpl callers {rows[0]['destino']}"] if rows else None,
    )


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------


# #65: só alerta "write vazio mas há reads" quando há reads suficientes (evita ruído).
_MIN_READS_FOR_HINT = 3


@app.command()
def tables(
    ctx: typer.Context,
    tabela: Annotated[str, typer.Argument(help="Nome da tabela ADVPL (ex: SA1, SC5, ZA1).")],
    mode: Annotated[
        TableMode | None,
        typer.Option(
            "--mode",
            "-m",
            help="Filtra por modo. 'write' é abrangente (inclui write_mvc/write_execauto).",
        ),
    ] = None,
    catalog: Annotated[
        bool,
        typer.Option(
            "--catalog",
            help="Catálogo de campos (tipo, título, X3_CBOX decodificado, discriminadores) em vez de uso.",
        ),
    ] = False,
    no_hints: Annotated[
        bool,
        typer.Option("--no-hints", help="Silencia o alerta proativo de 'write' vazio."),
    ] = False,
) -> None:
    """Lista quem usa a tabela ``T`` (lookup em ``fonte_tabela``).

    Com ``--catalog`` (#64): mostra o **catálogo de campos** (do dicionário SX3)
    com o ``X3_CBOX`` decodificado — os valores aceitos de cada discriminador.
    """

    if catalog:
        rows = _with_ro_db(ctx, lambda c: q_tables_catalog(c, tabela))
        if not rows:
            typer.secho(
                f"Tabela '{tabela.upper()}' não está no dicionário SX indexado "
                "(rode 'plugadvpl ingest-sx').",
                fg=typer.colors.YELLOW,
                err=True,
            )
            raise typer.Exit(code=1)
        _render_from_ctx(
            ctx,
            rows,
            title=f"Catálogo de campos: {tabela.upper()} ({len(rows)} campos)",
            next_steps=[f"plugadvpl tables {tabela.upper()} --mode write"],
        )
        return

    modo = mode.value if mode else None
    rows = _with_ro_db(ctx, lambda c: tables_query(c, tabela, modo))
    # #65: alerta proativo — 'write' vazio mas a tabela é lida em vários fontes
    # costuma ser mantenedor invisível, não tabela read-only. Só stderr (stdout
    # intacto → determinismo). Como #61 já cobre MVC/ExecAuto, o que sobra é
    # read-only genuíno OU padrão de gravação ainda não detectado.
    if modo == "write" and not rows and not no_hints:
        n_read = len(_with_ro_db(ctx, lambda c: tables_query(c, tabela, "read")))
        if n_read >= _MIN_READS_FOR_HINT:
            t = tabela.upper()
            typer.secho(
                f"\n⚠ Tabela {t} aparece {n_read}x como 'read' mas 0x como gravação "
                "(write/write_mvc/write_execauto).\n"
                "   Provável: (1) tabela read-only de catálogo; ou (2) mantenedor "
                "ainda não detectado pela análise estática.\n"
                f'   Investigue: plugadvpl grep "FWLoadModel.*{t}" -m identifier',
                fg=typer.colors.YELLOW,
                err=True,
            )
    _render_from_ctx(
        ctx,
        rows,
        title=f"Uso da tabela {tabela.upper()}" + (f" ({modo})" if modo else ""),
        next_steps=[f"plugadvpl arch {rows[0]['arquivo']}"] if rows else None,
    )


# ---------------------------------------------------------------------------
# param
# ---------------------------------------------------------------------------


@app.command()
def param(
    ctx: typer.Context,
    parametro: Annotated[str, typer.Argument(help="Nome do parâmetro (ex: MV_LOCALIZA).")],
) -> None:
    """Lista quem usa o parâmetro ``MV_*``."""

    rows = _with_ro_db(ctx, lambda c: param_query(c, parametro))
    _render_from_ctx(
        ctx,
        rows,
        title=f"Uso de {parametro.upper()}",
    )


# ---------------------------------------------------------------------------
# arch
# ---------------------------------------------------------------------------


@app.command()
def arch(
    ctx: typer.Context,
    arquivo: Annotated[str, typer.Argument(help="Basename do fonte (ex: FATA050.prw).")],
    include_header: Annotated[
        bool,
        typer.Option(
            "--include-header",
            help="Anexa o header doc declarativo (Programa/Autor/Descrição) do topo do fonte.",
        ),
    ] = False,
) -> None:
    """Resumo arquitetural de UM fonte (capabilities + funções + tabelas + includes)."""

    rows = _with_ro_db(ctx, lambda c: q_arch(c, arquivo, include_header=include_header))
    if not rows:
        typer.secho(
            f"Arquivo '{arquivo}' não encontrado no índice.", fg=typer.colors.YELLOW, err=True
        )
        raise typer.Exit(code=1)
    next_steps = [
        f"plugadvpl callees {arquivo}",
        f"plugadvpl lint {arquivo}",
    ]
    # Cross-link (P3): sugere a família pelo prefixo alfabético do nome.
    fam = re.match(r"^[A-Za-z]{3,}", arquivo)
    if fam:
        next_steps.append(f"plugadvpl family {fam.group(0)}   # outros fontes da família")
    _render_from_ctx(ctx, rows, title=f"Arquitetura: {arquivo}", next_steps=next_steps)


@app.command()
def diagnose(
    ctx: typer.Context,
    arquivo: Annotated[str, typer.Argument(help="Fonte ADVPL (path ou basename).")],
    record: Annotated[
        str | None,
        typer.Option("--record", help="Registro JSON, ex.: '{\"A1_LC\": 50000}'."),
    ] = None,
    record_file: Annotated[
        Path | None,
        typer.Option("--record-file", help="Arquivo JSON com o registro."),
    ] = None,
    fields_file: Annotated[
        Path | None,
        typer.Option("--fields-file", help="JSON de campos financeiros (SX3) p/ relativizar."),
    ] = None,
) -> None:
    """Avalia os pontos de decisão de um fonte contra um registro: desfecho EXATO +
    explicação relativizada (números sensíveis viram razão, ex.: 'saldo ~103% de limite')."""
    from .privacy.diagnose import diagnose as run_diagnose

    root: Path = ctx.obj["root"]
    cand = Path(arquivo) if Path(arquivo).is_absolute() else root / arquivo
    if not cand.exists():
        matches = sorted(root.rglob(arquivo))
        if not matches:
            typer.secho(f"Fonte '{arquivo}' não encontrado.", fg=typer.colors.YELLOW, err=True)
            raise typer.Exit(code=1)
        cand = matches[0]
    data = cand.read_bytes()
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        source = data.decode("cp1252", errors="replace")

    raw_record: dict[str, object] = {}
    financial: frozenset[str] = frozenset()
    try:
        if record_file is not None:
            raw_record = json.loads(record_file.read_text(encoding="utf-8"))
        elif record:
            raw_record = json.loads(record)
        if fields_file is not None:
            loaded = json.loads(fields_file.read_text(encoding="utf-8"))
            financial = frozenset(str(f).strip().upper() for f in loaded if str(f).strip())
    except (json.JSONDecodeError, OSError) as exc:
        typer.secho(f"Entrada inválida: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    results = run_diagnose(source, raw_record, financial_fields=financial)
    rows: list[dict[str, object]] = [
        {"linha": d.line, "condicao": d.condition, "explicacao": c.explain}
        for d in results
        for c in d.comparisons
    ]
    if not rows:
        typer.secho("Nenhum ponto de decisão encontrado.", fg=typer.colors.YELLOW, err=True)
    _render_from_ctx(ctx, rows, columns=["linha", "explicacao"], title=f"Diagnóstico: {cand.name}")


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------


def _lint_build_check_rows(
    root: Path,
    arquivo: str | None,
    severity: str | None,
    regra: str | None,
    target_build: str,
) -> list[dict[str, object]]:
    """Roda o check de build (catálogo ``apis_por_build``) nos fontes do ``root``
    e devolve rows ``BUILD-001`` no shape do lint, filtradas por severidade/regra."""
    catalog = apis_build_module.load_apis_catalog()
    if arquivo:
        cand = root / arquivo
        paths = [cand] if cand.exists() else sorted(root.rglob(arquivo))
    else:
        paths = sorted(p for ext in ("*.prw", "*.prx", "*.tlpp", "*.apw") for p in root.rglob(ext))
    out: list[dict[str, object]] = []
    for p in paths:
        try:
            data = p.read_bytes()
        except OSError:
            continue
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            content = data.decode("cp1252", errors="replace")
        out.extend(apis_build_module.check_build_lint_rows(content, catalog, target_build, p.name))
    if severity:
        out = [r for r in out if r["severidade"] == severity]
    if regra:
        out = [r for r in out if str(r["regra_id"]).upper() == regra.upper()]
    return out


@app.command()
def lint(
    ctx: typer.Context,
    arquivo: Annotated[str | None, typer.Argument(help="Filtra por arquivo (opcional).")] = None,
    severity: Annotated[
        str | None,
        typer.Option("--severity", "-s", help="Filtra por severidade (critical|error|warning)."),
    ] = None,
    regra: Annotated[
        str | None,
        typer.Option("--regra", help="Filtra por regra_id (ex: BP-001 ou SX-001)."),
    ] = None,
    cross_file: Annotated[
        bool,
        typer.Option(
            "--cross-file",
            help=(
                "Recalcula e grava findings cross-file SX-001..SX-011 "
                "(requer ingest + ingest-sx prévios)."
            ),
        ),
    ] = False,
    target_build: Annotated[
        str | None,
        typer.Option(
            "--target-build",
            help=(
                "Build Protheus alvo (ex: 24.3.0.5). Quando passado, inclui findings "
                "BUILD-001 (método FW*/Ms* ausente na build) via catálogo apis_por_build."
            ),
        ),
    ] = None,
) -> None:
    """Lista lint findings (filtros por arquivo/severidade/regra; ``--cross-file`` reavalia SX-*).

    Com ``--target-build`` inclui também findings ``BUILD-001`` (uso de método
    ausente na build alvo) — lê os fontes do ``--root`` ao vivo.
    """
    if cross_file:
        # Modo write: precisa de conexão writable, recompute e persiste.
        db_path: Path = ctx.obj["db"]
        if not db_path.exists():
            typer.secho(
                f"Erro: índice não encontrado em {db_path}.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        conn = open_db(db_path)
        try:
            apply_migrations(conn)
            findings = lint_module.lint_cross_file(conn)
            n = lint_module.persist_cross_file_findings(conn, findings)
        finally:
            close_db(conn)
        if not ctx.obj["quiet"]:
            typer.secho(
                f"OK  {n} findings cross-file gravados (SX-001..SX-011).",
                err=True,
            )

    # Resolve build alvo: a flag persiste em meta.target_build; sem flag, lê de lá
    # (configurar uma vez -> build-check roda automático no lint seguinte, inclusive
    # multi-agente). Build é a RELEASE Protheus (ex: 24.3.0.5), não a build do AppServer.
    effective_build = target_build
    if target_build:
        db_path = ctx.obj["db"]
        if db_path.exists():
            conn = open_db(db_path)
            try:
                set_meta(conn, "target_build", target_build)
                conn.commit()
            finally:
                close_db(conn)
    else:
        effective_build = _with_ro_db(ctx, lambda c: get_meta(c, "target_build"))

    rows = _with_ro_db(ctx, lambda c: lint_query(c, arquivo, severity, regra))

    # #118: "sem findings" é ambíguo — arquivo limpo OU nem indexado. Se o alvo
    # não está no índice, avisa (em vez de parecer "revisado e OK").
    if arquivo and not _with_ro_db(ctx, lambda c: fonte_indexada(c, arquivo)):
        typer.secho(
            f"AVISO: '{arquivo}' não está no índice — o lint NÃO analisou esse arquivo. "
            f"Rode 'plugadvpl ingest' (ou confira o caminho/nome). "
            f"'sem findings' aqui significa NÃO-ANALISADO, não 'limpo'.",
            fg=typer.colors.YELLOW,
            err=True,
        )

    if effective_build:
        build_rows = _lint_build_check_rows(
            ctx.obj["root"], arquivo, severity, regra, effective_build
        )
        rows = sorted(
            [*rows, *build_rows],
            key=lambda r: (str(r["arquivo"]), int(r["linha"])),
        )

    _render_from_ctx(
        ctx,
        rows,
        title="Lint findings",
        next_steps=[f"plugadvpl arch {rows[0]['arquivo']}"] if rows else None,
    )


@app.command(name="check-build")
def check_build(
    ctx: typer.Context,
    arquivo: Annotated[str, typer.Argument(help="Fonte ADVPL/TLPP a verificar.")],
    target_build: Annotated[
        str,
        typer.Option("--target-build", "-b", help="Build Protheus alvo (ex: 24.3.0.5)."),
    ],
) -> None:
    """Sinaliza uso de método FW*/Ms* ausente na build alvo (catálogo ``apis_por_build``).

    Resolve ``oVar := Classe():New()`` por função e só reporta ``oVar:Metodo(``
    quando a classe é confirmada no catálogo e o build alvo cai fora da janela de
    disponibilidade — zero falso-positivo. Não precisa de índice (lê o catálogo
    embarcado + o fonte direto).
    """
    path = Path(arquivo)
    if not path.exists():
        typer.secho(f"Erro: arquivo não encontrado: {arquivo}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    data = path.read_bytes()
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        content = data.decode("cp1252", errors="replace")

    catalog = apis_build_module.load_apis_catalog()
    findings = apis_build_module.check_build(content, catalog, target_build)
    rows: list[dict[str, object]] = [
        {
            "arquivo": path.name,
            "linha": f["linha"],
            "destino": f"{f['var']}:{f['metodo']}",
            "classe": f["classe"],
            "ausente_em": target_build,
            "nota": f["nota"],
        }
        for f in findings
    ]
    _render_from_ctx(
        ctx,
        rows,
        columns=["arquivo", "linha", "destino", "classe", "ausente_em", "nota"],
        title=f"Métodos ausentes na build {target_build}",
    )


@app.command()
def semantica(
    ctx: typer.Context,
    campo: Annotated[str, typer.Argument(help="Campo SX (ex: B6_CLIFOR).")],
) -> None:
    """Mostra a semântica contextual de um campo SX (catálogo ``campos_semantica``).

    Alguns campos têm significado que muda conforme um discriminador
    (TIPO/PODER3/STATUS). Lê o catálogo embarcado (só semântica padrão Protheus,
    sem termo de cliente) — não precisa de índice.
    """
    catalog = semantica_module.load_semantica_catalog()
    rows: list[dict[str, object]] = [
        {
            "campo": e["campo"],
            "tabela": e["tabela"],
            "discriminador": e.get("discriminador") or "(sempre)",
            "semantica": e["semantica"],
            "fonte": e.get("fonte", ""),
        }
        for e in semantica_module.lookup_semantica(catalog, campo)
    ]
    _render_from_ctx(
        ctx,
        rows,
        columns=["campo", "tabela", "discriminador", "semantica", "fonte"],
        title=f"Semântica de {campo.strip().upper()}",
    )


@app.command(name="poui-componentes")
def poui_componentes(
    ctx: typer.Context,
    alvo: Annotated[
        str | None,
        typer.Argument(
            help=(
                "Componente (ex: po-table) → bindings `p-*`; interface (ex: PoTableColumn) "
                "→ propriedades; `schematics` → generators `ng generate`. Omita p/ listar todos."
            )
        ),
    ] = None,
    filtro: Annotated[
        str | None,
        typer.Argument(
            help=(
                "Filtra por substring: propriedade (interface) ou binding (componente). "
                "Ex.: `poui-componentes PoDynamicFormField maxLength`."
            )
        ),
    ] = None,
) -> None:
    """Referência PO UI verificada (po-angular): bindings, interfaces e schematics.

    Consulta os catálogos embarcados — não precisa de índice de projeto. Use
    antes de escrever Angular para não inventar atributo/chave/valor:

    - ``poui-componentes po-table`` → bindings `p-*` que o componente aceita.
    - ``poui-componentes PoTableColumn`` → propriedades do objeto de config
      (com valores válidos quando enumerados, ex.: o `type` ∈ 14 valores).
    - ``poui-componentes PoDynamicFormField maxLength`` → filtra por propriedade.
    - ``poui-componentes schematics`` → generators oficiais (`ng generate
      @po-ui/...`) por caso-de-uso — prefira gerar a tela ao montá-la à mão.

    Alvo iniciando com maiúscula (``Po...``) = interface; ``schematics`` = generators.
    O catálogo é grande: use `--limit 0` ANTES do subcomando (ou `--format json`,
    que nunca trunca) para ver tudo.
    """
    db_path: Path = ctx.obj["db"]
    is_schematics = alvo is not None and alvo.lower() in ("schematics", "schematic", "scaffold")
    is_interface = not is_schematics and alvo is not None and alvo[:1].isupper()
    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        seed_lookups(conn)
        if is_schematics:
            srows = q_poui_schematics(conn, filtro=filtro)
        elif is_interface:
            irows = q_poui_interfaces(conn, interface=alvo, propriedade=filtro)
        else:
            rows = q_poui_componentes(conn, componente=alvo, binding=filtro)
    finally:
        close_db(conn)

    if is_schematics:
        _render_from_ctx(
            ctx,
            srows,
            columns=["caso_uso", "comando", "gera", "pacote"],
            title="Schematics PO UI — ng generate @po-ui/... (prefira ao código à mão)",
        )
        return

    if is_interface:
        display = [
            {
                "interface": r["interface"],
                "propriedade": r["propriedade"],
                "tipo": r["tipo"],
                "opcional": "sim" if r["opcional"] else "NÃO",
                "valores": ", ".join(r["valores"]) if r["valores"] else "",
                "herdado_de": r["herdado_de"],
            }
            for r in irows
        ]
        _render_from_ctx(
            ctx,
            display,
            columns=["interface", "propriedade", "tipo", "opcional", "valores", "herdado_de"],
            title=f"Interface PO UI — {alvo}",
        )
        return

    title = f"Bindings PO UI — {alvo}" if alvo else "Catálogo PO UI — todos os componentes"
    _render_from_ctx(
        ctx,
        rows,
        columns=["componente", "kind", "binding", "propriedade", "pacote"],
        title=title,
    )


# ---------------------------------------------------------------------------
# ini-audit
# ---------------------------------------------------------------------------


_COMPLIANCE_LABELS = {
    "compliant": "EM CONFORMIDADE",
    "partial": "PARCIALMENTE CONFORME",
    "non_compliant": "FORA DE CONFORMIDADE",
}
_ENV_INDICATOR_KEYS = frozenset({"rootpath", "sourcepath", "rpodb", "rpoversion", "startpath"})


def _render_ini_audit_html(
    conn: sqlite3.Connection,
    arquivo: str | None,
    file_ids: list[int] | None = None,
) -> str:
    """Monta o relatório HTML do ini-audit: re-parseia cada INI (encoding,
    seções comentadas, linhas malformadas) e combina com score/findings/INI
    sugerido do índice — cobrindo todas as seções do relatório.

    ``file_ids`` escopa o relatório aos arquivos auditados nesta execução."""
    rules_keys = ini_rules_keys(conn)
    reports: list[dict[str, Any]] = []
    for sc in ini_audit_scores(conn, arquivo, file_ids):
        try:
            raw = Path(str(sc["caminho"])).read_bytes()
        except OSError:
            raw = b""
        # Passa BYTES pro parser: só assim ele detecta o encoding real
        # (ascii/cp1252/utf-8-bom). Com str ele devolve placeholder "str".
        parsed_obj = parse_ini_file(raw, filename=str(sc["arquivo"]))
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("cp1252", errors="replace")

        sections_map: dict[str, dict[str, str]] = {
            sec.name_raw: {} for sec in parsed_obj.sections if not sec.commented
        }
        for k in parsed_obj.keys:
            sections_map.setdefault(k.section_name, {})[k.key_name] = k.value
        env_names = {
            sec
            for sec, kv in sections_map.items()
            if any(key.lower() in _ENV_INDICATOR_KEYS for key in kv)
        }

        active = [s for s in parsed_obj.sections if not s.commented]
        commented = [s for s in parsed_obj.sections if s.commented]
        parsed = {
            "filename": parsed_obj.filename or sc["arquivo"],
            "ini_type": parsed_obj.tipo,
            "ini_role": parsed_obj.role,
            "encoding_info": {
                "detected": parsed_obj.encoding_info.detected,
                "has_bom": parsed_obj.encoding_info.has_bom,
                "warnings": list(parsed_obj.encoding_info.warnings),
            },
            "meta": {
                "total_sections": len(active),
                "total_commented_sections": len(commented),
                "total_keys": len(parsed_obj.keys),
                "total_commented": 0,
                "total_dirty_lines": len(parsed_obj.dirty_lines),
            },
            "commented_sections": [
                {"section": s.name_raw, "line": s.linha_inicio} for s in commented
            ],
            "dirty_lines": [
                {"line": d.linha, "content": d.content, "reason": d.reason}
                for d in parsed_obj.dirty_lines
            ],
        }

        findings = ini_findings_enriched(conn, int(sc["id"]))
        for f in findings:
            f["current_value"] = sections_map.get(str(f["section"]), {}).get(str(f["key_name"]))

        unknown = detect_unknown_keys(sections_map, parsed_obj.tipo, env_names, rules_keys)
        try:
            summ = json.loads(str(sc.get("summary_json") or "{}"))
        except (json.JSONDecodeError, TypeError):
            summ = {}
        summ["unknown_keys"] = len(unknown)

        fix_items = ini_audit_fix_items(conn, int(sc["id"]))
        suggested = (
            generate_suggested_ini(content, fix_items, unknown)
            if ((fix_items or unknown) and content)
            else ""
        )

        comp = {
            "score": sc["score"],
            "compliance_status": sc["compliance"],
            "compliance_label": _COMPLIANCE_LABELS.get(
                str(sc["compliance"]), str(sc["compliance"])
            ),
            "summary": summ,
            "findings": findings,
            "unknown_keys": unknown,
            "suggested_ini": suggested,
        }
        reports.append({"parsed": parsed, "comp": comp})
    return render_ini_audit_html(reports)


@app.command(name="ini-audit")
def ini_audit(  # noqa: PLR0912, PLR0915 -- typer command com varios filtros mutuamente exclusivos (severity/role/category/file/...) + branch de --format html; split viraria boilerplate de wrappers
    ctx: typer.Context,
    paths: Annotated[
        list[str] | None,
        typer.Argument(
            help=(
                "Caminhos de INI (arquivos ou diretórios). Sem args, auto-discover "
                f"em ``--root`` via globs: {', '.join(INI_DEFAULT_GLOBS)}."
            ),
        ),
    ] = None,
    severity: Annotated[
        str | None,
        typer.Option("--severity", "-s", help="Filtra severidade (critical|warning|info)."),
    ] = None,
    regra: Annotated[
        str | None,
        typer.Option("--regra", help="Filtra por regra_id (ex: APP-GENERAL-MAXSTRINGSIZE)."),
    ] = None,
    arquivo: Annotated[
        str | None,
        typer.Option("--arquivo", help="Filtra por basename do INI."),
    ] = None,
    show_ok_with_note: Annotated[
        bool,
        typer.Option(
            "--show-ok-with-note",
            help="Inclui findings em que o cliente documentou justificativa nos comentários.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Re-ingere mesmo se hash+mtime baterem (ignora cache)."),
    ] = False,
    no_audit: Annotated[
        bool,
        typer.Option(
            "--no-audit",
            help="Só faz ingest dos INIs (popula ini_files/sections/keys) sem rodar regras.",
        ),
    ] = False,
) -> None:
    """Auditar arquivos INI Protheus contra 487 regras de boas práticas TDN-oficiais.

    Pipeline ``ingest -> audit`` num único comando: parseia o INI, grava em DB
    (cache via hash+mtime), aplica regras filtradas por tipo+role, e lista os
    findings em formato configurável (``--format table|json|md``).

    Exemplos:
        plugadvpl ini-audit                                       # auto-discover em --root
        plugadvpl ini-audit /srv/protheus/appserver*.ini          # paths específicos
        plugadvpl ini-audit -s critical                           # só críticos
        plugadvpl ini-audit --regra APP-GENERAL-MAXSTRINGSIZE     # 1 regra específica
        plugadvpl ini-audit --show-ok-with-note                   # inclui justificados
    """
    obj = ctx.obj
    db_path: Path = obj["db"]
    root: Path = obj["root"]

    # 1. Resolve paths
    if paths:
        ini_paths: list[Path] = []
        for s in paths:
            p = Path(s).expanduser().resolve()
            if p.is_dir():
                ini_paths.extend(discover_ini_paths(p))
            elif p.is_file():
                ini_paths.append(p)
            else:
                # Pode ser glob não-expandido (shell escapou)
                expanded = list(Path().glob(s)) or list(root.glob(s))
                ini_paths.extend(q.resolve() for q in expanded if q.is_file())
    else:
        ini_paths = discover_ini_paths(root)

    if not ini_paths:
        typer.secho(
            f"Nenhum INI Protheus encontrado em {root} (globs: {', '.join(INI_DEFAULT_GLOBS)}).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=0)

    # 2. Ingest (write — abre conn full)
    if not db_path.exists():
        typer.secho(
            f"Erro: índice não encontrado em {db_path}. Rode `plugadvpl init` primeiro.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        seed_lookups(conn)  # idempotente; garante 487 regras + 14 roles
        ing_res = ingest_ini_paths(conn, ini_paths, force=force)

        if not obj["quiet"]:
            typer.secho(
                f"Ingest: {ing_res.ingested} novos, {ing_res.skipped} em cache, "
                f"{len(ing_res.errors)} erros.",
                err=True,
            )
            for path, reason in ing_res.errors:
                typer.secho(f"  ERROR {path}: {reason}", fg=typer.colors.RED, err=True)

        if no_audit:
            raise typer.Exit(code=0)

        # 3. Audit
        if ing_res.file_ids:
            audit_res = ini_audit_files(conn, ing_res.file_ids)
            if not obj["quiet"]:
                sev = audit_res.by_severity
                typer.secho(
                    f"Audit: {audit_res.findings_total} findings "
                    f"(critical={sev.get('critical', 0)}, "
                    f"warning={sev.get('warning', 0)}, "
                    f"info={sev.get('info', 0)}).",
                    err=True,
                )
                for fid in ing_res.file_ids:
                    score_val = audit_res.score_by_file.get(fid)
                    if score_val is None:
                        continue
                    comp = audit_res.compliance_by_file.get(fid, "")
                    arq_row = conn.execute(
                        "SELECT arquivo FROM ini_files WHERE id = ?", (fid,)
                    ).fetchone()
                    arq_name = arq_row[0] if arq_row is not None else str(fid)
                    typer.secho(f"  Score {arq_name}: {score_val:.1f} ({comp}).", err=True)
    finally:
        close_db(conn)

    # 4. Render (RO)
    # --format html: relatório rico (score/selo + findings agrupados). Os
    # justificados (ok_with_note) entram sempre no HTML, numa seção própria.
    if ctx.obj["format"] == "html":
        report = _with_ro_db(
            ctx,
            lambda c: _render_ini_audit_html(c, arquivo, ing_res.file_ids),
        )
        typer.echo(_mask_text_if_privacy(ctx, report))
        return

    rows = _with_ro_db(
        ctx,
        lambda c: ini_audit_query(
            c,
            arquivo=arquivo,
            severity=severity,
            regra_id=regra,
            show_ok_with_note=show_ok_with_note,
        ),
    )
    _render_from_ctx(
        ctx,
        rows,
        columns=[
            "arquivo",
            "tipo",
            "role",
            "section",
            "key",
            "linha",
            "regra_id",
            "severidade",
            "snippet",
        ],
        title="Audit INI findings",
        next_steps=(
            [f"plugadvpl ini-audit --arquivo {rows[0]['arquivo']} --regra {rows[0]['regra_id']}"]
            if rows
            else None
        ),
    )


# ---------------------------------------------------------------------------
# log-diagnose
# ---------------------------------------------------------------------------


def _read_log_text(caminho: str) -> str:
    data = Path(caminho).read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _compute_log_link(
    conn: sqlite3.Connection,
    main_file_ids: list[int],
    linked_path: Path,
) -> dict[str, Any]:
    """Ingere o arquivo linkado e correlaciona com os logs principais por
    ``environment::thread`` (fallback ``thread`` → ``environment``). Devolve o
    contexto do linkado (env/thread/métricas/stack) + ``matched_by`` + nº de
    findings enriquecidos (mesma thread)."""
    ingest_log_paths(conn, [linked_path])
    content = _read_log_text(str(linked_path))
    meta = extract_header_metadata(content)
    metr = scan_metrics(content)

    metrics: dict[str, Any] = {}
    if metr.start_time_s:
        metrics["uptime_seconds"] = float(metr.start_time_s)
    if metr.memory_resident_mb:
        metrics["memory_app_peak_mb"] = float(metr.memory_resident_mb)
    if metr.memory_total_mb and metr.memory_free_mb:
        metrics["memory_os_last"] = {
            "physical_mb": float(metr.memory_total_mb),
            "free_mb": float(metr.memory_free_mb),
            "used_mb": float(metr.memory_used_mb or 0),
        }
    stack = meta.extra.get("callstack", "") or meta.extra.get("stack", "")

    main_env = ""
    main_threads: set[str] = set()
    if main_file_ids:
        ph = ",".join("?" * len(main_file_ids))
        env_row = conn.execute(
            f"SELECT environment FROM log_files WHERE id IN ({ph}) AND environment != '' LIMIT 1",
            list(main_file_ids),
        ).fetchone()
        main_env = str(env_row[0]) if env_row else ""
        for (tid,) in conn.execute(
            f"SELECT DISTINCT thread_id FROM log_findings WHERE file_id IN ({ph})",
            list(main_file_ids),
        ):
            if tid:
                main_threads.add(str(tid))

    if (
        meta.environment
        and meta.thread
        and meta.thread in main_threads
        and (not main_env or main_env == meta.environment)
    ):
        matched_by = "environment::thread"
    elif meta.thread and meta.thread in main_threads:
        matched_by = "thread"
    elif main_env and meta.environment and main_env == meta.environment:
        matched_by = "environment"
    else:
        matched_by = "none"

    enriched = 0
    if meta.thread and matched_by in ("environment::thread", "thread") and main_file_ids:
        ph = ",".join("?" * len(main_file_ids))
        enriched = int(
            conn.execute(
                f"SELECT COUNT(*) FROM log_findings WHERE file_id IN ({ph}) AND thread_id = ?",
                [*main_file_ids, meta.thread],
            ).fetchone()[0]
        )

    return {
        "file": linked_path.name,
        "environment": meta.environment,
        "thread": meta.thread,
        "metrics": metrics,
        "stack": stack,
        "matched": matched_by != "none",
        "matched_by": matched_by,
        "enriched": enriched,
    }


def _render_log_diagnose_html(
    conn: sqlite3.Connection,
    arquivo: str | None,
    severity: str | None,
    category: str | None,
    rule: str | None,
    link_info: dict[str, Any] | None,
) -> str:
    """Monta o relatório HTML do log-diagnose (findings + correlação)."""
    findings = log_report_findings(conn, arquivo, severity, category, rule)
    files = log_report_files(conn, arquivo)
    label = ", ".join(str(f["arquivo"]) for f in files) or (arquivo or "(logs)")
    total = sum(int(f.get("total_events") or 0) for f in files)
    return render_log_diagnose_html(label, total, findings, metrics={}, link=link_info)


# ---------------------------------------------------------------------------
# log-diagnose (command)
# ---------------------------------------------------------------------------


@app.command(name="log-diagnose")
def log_diagnose(  # noqa: PLR0912, PLR0915 -- typer command com filtros (severity/tipo/file/since/...) + branch de --link e --format html; cada branch e validacao independente
    ctx: typer.Context,
    paths: Annotated[
        list[str] | None,
        typer.Argument(
            help=(
                "Caminhos de logs Protheus (arquivos ou diretórios). Sem args, auto-discover "
                f"em ``--root`` via globs: {', '.join(DEFAULT_LOG_GLOBS)}."
            ),
        ),
    ] = None,
    severity: Annotated[
        str | None,
        typer.Option("--severity", "-s", help="Filtra severidade (critical|warning|info)."),
    ] = None,
    category: Annotated[
        str | None,
        typer.Option(
            "--category",
            "-c",
            help="Filtra categoria (database|thread_error|rpo|network|connection|service|rest_api|"
            "compilation|authentication|shutdown|lifecycle|application).",
        ),
    ] = None,
    rule: Annotated[
        str | None,
        typer.Option("--rule", help="Filtra por rule_id (ex: LOG-DB-ORA)."),
    ] = None,
    arquivo: Annotated[
        str | None,
        typer.Option("--arquivo", help="Filtra por basename do log."),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            help="Janela temporal relativa ao último timestamp do log "
            "(30m, 24h, 7d). Cuidado: é relativo ao log, não ao wall clock.",
        ),
    ] = None,
    max_findings: Annotated[
        int,
        typer.Option("--max-findings", help="Limite de findings por arquivo (default 1000)."),
    ] = 1000,
    force: Annotated[
        bool,
        typer.Option("--force", help="Re-ingere mesmo se hash+mtime baterem (ignora cache)."),
    ] = False,
    no_diagnose: Annotated[
        bool,
        typer.Option(
            "--no-diagnose",
            help="Só faz ingest (popula log_files/events) sem rodar match.",
        ),
    ] = False,
    link: Annotated[
        str | None,
        typer.Option(
            "--link",
            help="Arquivo oposto (console/profile) para correlacionar por "
            "environment::thread (cross-link console↔profile).",
        ),
    ] = None,
) -> None:
    """Diagnosticar logs Protheus (console.log/error.log/profile.log/compila.log).

    Pipeline em 2 estágios num único comando:
      Stage 1 — tokenize_events: quebra log em eventos delimitados por 1 dos
                  4 formatos de header (ISO+thread, THREAD ERROR PT-BR, [DD/MM
                  HH:MM:SS], [SEVERITY]).
      Stage 2 — diagnose: aplica catálogo de regras em ordem reversa (mais
                  recente primeiro), enriquece com correction tip da base de
                  92+ tips com URL TDN oficial.

    Exemplos:
        plugadvpl log-diagnose                                    # auto-discover
        plugadvpl log-diagnose /var/log/protheus/                 # diretório
        plugadvpl log-diagnose --severity critical --since 24h    # últimas 24h críticos
        plugadvpl log-diagnose --category database                # só database
        plugadvpl log-diagnose --rule LOG-DB-ORA                  # uma regra específica
    """
    obj = ctx.obj
    db_path: Path = obj["db"]
    root: Path = obj["root"]

    # 1. Resolve paths
    if paths:
        log_paths: list[Path] = []
        for s in paths:
            p = Path(s).expanduser().resolve()
            if p.is_dir():
                log_paths.extend(discover_log_paths(p))
            elif p.is_file():
                log_paths.append(p)
            else:
                expanded = list(Path().glob(s)) or list(root.glob(s))
                log_paths.extend(q.resolve() for q in expanded if q.is_file())
    else:
        log_paths = discover_log_paths(root)

    if not log_paths:
        typer.secho(
            f"Nenhum log Protheus encontrado em {root} (globs: {', '.join(DEFAULT_LOG_GLOBS)}).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=0)

    # 2. Ingest (write — conn full)
    if not db_path.exists():
        typer.secho(
            f"Erro: índice não encontrado em {db_path}. Rode `plugadvpl init` primeiro.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    link_info: dict[str, Any] | None = None
    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        seed_lookups(conn)  # idempotente; garante regras + tips + categorias seedadas
        ing_res = ingest_log_paths(conn, log_paths, force=force)

        if not obj["quiet"]:
            warn_count = len(ing_res.warnings)
            typer.secho(
                f"Ingest: {ing_res.ingested} novos, {ing_res.skipped} em cache, "
                f"{len(ing_res.errors)} erros"
                + (f", {warn_count} warnings" if warn_count else "")
                + ".",
                err=True,
            )
            for path, reason in ing_res.errors:
                typer.secho(f"  ERROR {path}: {reason}", fg=typer.colors.RED, err=True)
            for path, reason in ing_res.warnings:
                typer.secho(f"  WARN  {path}: {reason}", fg=typer.colors.YELLOW, err=True)

        if no_diagnose:
            raise typer.Exit(code=0)

        # 3. Diagnose
        if ing_res.file_ids:
            sev_filter = [severity] if severity else None
            diag_res = log_diagnose_files(
                conn,
                ing_res.file_ids,
                since=since,
                severity_filter=sev_filter,
                max_findings=max_findings,
            )
            if not obj["quiet"]:
                sev = diag_res.by_severity
                typer.secho(
                    f"Diagnose: {diag_res.findings_total} findings "
                    f"(critical={sev.get('critical', 0)}, "
                    f"warning={sev.get('warning', 0)}, "
                    f"info={sev.get('info', 0)}).",
                    err=True,
                )

            if link:
                link_path = Path(link)
                if not link_path.exists():
                    typer.secho(
                        f"Arquivo de link não encontrado: {link_path}",
                        fg=typer.colors.RED,
                        err=True,
                    )
                    raise typer.Exit(code=2)
                link_info = _compute_log_link(conn, list(ing_res.file_ids), link_path)
                if not obj["quiet"]:
                    typer.secho(
                        f"Link: {link_info['matched_by']} — {link_info['enriched']} findings "
                        f"na thread {link_info['thread'] or '—'}.",
                        err=True,
                    )
    finally:
        close_db(conn)

    # 4. Render (RO)
    if ctx.obj["format"] == "html":
        report = _with_ro_db(
            ctx,
            lambda c: _render_log_diagnose_html(c, arquivo, severity, category, rule, link_info),
        )
        typer.echo(_mask_text_if_privacy(ctx, report))
        return

    rows = _with_ro_db(
        ctx,
        lambda c: log_diagnose_query(
            c,
            arquivo=arquivo,
            severity=severity,
            category=category,
            rule_id=rule,
        ),
    )
    _render_from_ctx(
        ctx,
        rows,
        columns=[
            "arquivo",
            "log_tipo",
            "linha",
            "timestamp",
            "severidade",
            "categoria",
            "rule_id",
            "message",
        ],
        title="Log diagnose findings",
        next_steps=(
            [f"plugadvpl log-diagnose --rule {rows[0]['rule_id']} --format json"] if rows else None
        ),
    )


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

# v0.16.5: limite de skills listadas no output de `doctor --check-agents`.
# Acima disso, mostra "... e mais N" pra evitar flood em projetos grandes.
_DOCTOR_MAX_SKILLS_LISTED = 10


@app.command()
def doctor(
    ctx: typer.Context,
    check_funcs: Annotated[
        bool,
        typer.Option(
            "--check-funcs",
            help="v0.4.6 (B): compara grep vs parser por arquivo (slow — re-le fontes). "
            "v0.4.7: classifica em real_bug (parser perdeu funcao em codigo) vs "
            "commented_out (funcao dentro de /* */, intencional).",
        ),
    ] = False,
    detail: Annotated[
        bool,
        typer.Option(
            "--detail",
            help="v0.4.7: com --check-funcs, expande pra row-per-file (sem truncagem). "
            "Cada fonte com discrepancia vira 1 row com arquivo/grep_raw/grep_code/parser/classificacao.",
        ),
    ] = False,
    check_agents: Annotated[
        bool,
        typer.Option(
            "--check-agents",
            help="v0.16.5: valida formato dos arquivos gerados pra todos 5 agentes "
            "(CLAUDE.md, AGENTS.md, Cursor, Copilot, Gemini) sem precisar instalar "
            "os agentes externos.",
        ),
    ] = False,
) -> None:
    """Diagnósticos do índice (encoding, órfãos, FTS sync, lookups)."""

    if check_agents:
        from plugadvpl.agent_doctor import run_checks

        root: Path = ctx.obj["root"]
        report = run_checks(root, expected_version=__version__)
        for check in report.checks:
            typer.echo(f"{check.emoji()}  {check.name}: {check.detail}")
        if report.skills_without_keywords:
            typer.echo(
                f"\nWARN  {len(report.skills_without_keywords)} skill(s) sem keywords ADVPL/Protheus:"
            )
            for name in report.skills_without_keywords[:_DOCTOR_MAX_SKILLS_LISTED]:
                typer.echo(f"     - {name}")
            if len(report.skills_without_keywords) > _DOCTOR_MAX_SKILLS_LISTED:
                remainder = len(report.skills_without_keywords) - _DOCTOR_MAX_SKILLS_LISTED
                typer.echo(f"     ... e mais {remainder}")
        if any(c.status == "fail" for c in report.checks):
            raise typer.Exit(code=1)
        return

    rows = _with_ro_db(ctx, doctor_diagnostics)
    if check_funcs:
        root2: Path = ctx.obj["root"]
        rows.extend(_with_ro_db(ctx, lambda c: doctor_func_count_check(c, root2, detail=detail)))
    _render_from_ctx(
        ctx,
        rows,
        columns=["check", "status", "count", "detail"],
        title="Doctor — saúde do índice",
        next_steps=(
            ["plugadvpl ingest --no-incremental"]
            if any(r.get("status") in {"error", "warn"} for r in rows)
            else None
        ),
    )


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


@app.command()
def grep(
    ctx: typer.Context,
    pattern: Annotated[str, typer.Argument(help="Padrão de busca.")],
    mode: Annotated[
        GrepMode,
        typer.Option("--mode", "-m", help="Modo: fts (default), literal, identifier."),
    ] = GrepMode.fts,
) -> None:
    """Busca textual no conteúdo dos chunks (FTS5 / LIKE / identifier)."""

    limit = ctx.obj["limit"] or 50
    try:
        rows = _with_ro_db(ctx, lambda c: grep_fts(c, pattern, mode=mode.value, limit=limit))
    except sqlite3.OperationalError as exc:
        # v0.4.4 (BUG #1): FTS5 rejeita caracteres como `/`, `(`, `)`. Antes
        # propagava traceback completo vazando paths internos. Agora mensagem
        # amigável + sugestão de modo alternativo.
        if mode == GrepMode.fts and "fts5" in str(exc).lower():
            typer.echo(
                f"Padrão FTS5 inválido: {pattern!r}.\n"
                f"FTS5 não aceita caracteres como '/', '(', ')', '[', ']'. "
                f"Operadores válidos: '+', '*', '\"frase\"', 'OR', 'AND', 'NEAR'.\n"
                f"Alternativas:\n"
                f"  plugadvpl grep {pattern!r} -m literal      (substring exata via LIKE)\n"
                f"  plugadvpl grep <termo> -m identifier        (busca por símbolo)",
                err=True,
            )
            raise typer.Exit(code=2) from exc
        raise
    _render_from_ctx(
        ctx,
        rows,
        title=f"Grep ({mode.value}): {pattern}",
        next_steps=[f"plugadvpl arch {rows[0]['arquivo']}"] if rows else None,
    )


# ---------------------------------------------------------------------------
# v0.3.0 — Universo 2: ingest-sx, impacto, gatilho, sx-status
# ---------------------------------------------------------------------------


@app.command(name="ingest-sx")
def ingest_sx_cmd(
    ctx: typer.Context,
    csv_dir: Annotated[
        Path,
        typer.Argument(
            help="Pasta com CSVs SX (sx1.csv, sx2.csv, ..., sxg.csv) exportados via Configurador -> Misc -> Exportar Dicionario.",
        ),
    ],
    workers: Annotated[
        int,
        typer.Option(
            "--workers",
            "-w",
            help="Reservado para futuro paralelismo. Atualmente não usado (parser é I/O bound + executemany single-thread).",
        ),
    ] = 0,
) -> None:
    """Indexa o Dicionário SX a partir de CSVs (Universo 2)."""
    _ = workers  # explicitly unused; kept for symmetry with `ingest`
    db_path: Path = ctx.obj["db"]
    if not csv_dir.exists() or not csv_dir.is_dir():
        typer.secho(
            f"Pasta CSV inválida: {csv_dir}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    counters = do_ingest_sx(csv_dir.resolve(), db_path)
    summary_rows: list[dict[str, object]] = [
        {
            "tabela": tabela,
            "rows": counters["per_table"].get(tabela, 0),
        }
        for tabela in (
            "tabelas",
            "campos",
            "indices",
            "gatilhos",
            "parametros",
            "perguntas",
            "tabelas_genericas",
            "relacionamentos",
            "pastas",
            "consultas",
            "grupos_campo",
        )
    ]
    summary_rows.append(
        {
            "tabela": "_TOTAL",
            "rows": counters["total_rows"],
        }
    )
    if not ctx.obj["quiet"]:
        typer.secho(
            f"OK  {counters['csvs_ok']}/{counters['csvs_total']} CSVs ingeridos "
            f"({counters['csvs_skipped']} pulados, {counters.get('csvs_failed', 0)} falhos) "
            f"em {counters['duration_ms']}ms",
            err=True,
        )
    _render_from_ctx(
        ctx,
        summary_rows,
        title="Ingest SX — rows por tabela",
        next_steps=[
            "plugadvpl impacto A1_COD",
            "plugadvpl gatilho A1_COD",
        ],
    )


@app.command(name="ingest-tsv")
def ingest_tsv_cmd(
    ctx: typer.Context,
    arquivo: Annotated[
        Path,
        typer.Argument(help="Dump TSV/CSV de tabela-catálogo (exportado do Oracle/SQL/DBeaver)."),
    ],
    alias: Annotated[
        str, typer.Option("--as", help="Nome lógico do catálogo (ex: catalogo_regras).")
    ],
    encoding: Annotated[
        str | None,
        typer.Option("--encoding", help="Override de encoding (cp1252|utf-8). Auto se omitido."),
    ] = None,
    delimiter: Annotated[
        str | None,
        typer.Option("--delimiter", help="Override de delimiter (tab|csv). Auto se omitido."),
    ] = None,
) -> None:
    """Importa um dump TSV/CSV de tabela-catálogo (Z*/X*) pro índice (#75).

    Fecha o gap do *conteúdo* das tabelas-catálogo. Depois, consulte com ``catalog``.
    """
    db_path: Path = ctx.obj["db"]
    if not arquivo.exists() or not arquivo.is_file():
        typer.secho(f"Arquivo inválido: {arquivo}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        meta = do_ingest_tsv(conn, arquivo.resolve(), alias, encoding=encoding, delimiter=delimiter)
    finally:
        close_db(conn)
    if not ctx.obj["quiet"]:
        if meta["overwritten"]:
            typer.secho(f"⚠ Catálogo '{alias}' já existia — sobrescrito.", fg="yellow", err=True)
        sx_msg = f" · cruza com SX '{meta['sx_table']}'" if meta["sx_table"] else ""
        typer.secho(
            f"OK  {meta['rows']} linhas importadas em '{alias}' ({meta['columns']} colunas, "
            f"{meta['encoding']}/{meta['delimiter']}){sx_msg}",
            err=True,
        )
    _render_from_ctx(
        ctx,
        [
            {
                "alias": alias,
                "rows": meta["rows"],
                "columns": meta["columns"],
                "sx_table": meta["sx_table"] or "",
            }
        ],
        title=f"Catálogo importado: {alias}",
        next_steps=[
            f"plugadvpl catalog {alias} --limit 20",
            f"plugadvpl catalog {alias} --group-by <COL> --count",
        ],
    )


@app.command()
def catalog(
    ctx: typer.Context,
    alias: Annotated[str, typer.Argument(help="Nome do catálogo (o --as do ingest-tsv).")],
    filter_expr: Annotated[
        str | None,
        typer.Option(
            "--filter", help="Filtro seguro: COL OP 'VAL' [AND/OR ...] (= != > < >= <= LIKE)."
        ),
    ] = None,
    group_by: Annotated[
        str | None,
        typer.Option(
            "--group-by", help="Agrupa por coluna(s), separadas por vírgula. Use com --count."
        ),
    ] = None,
    count: Annotated[bool, typer.Option("--count", help="Conta registros por grupo.")] = False,
    decode_cbox: Annotated[
        bool,
        typer.Option("--decode-cbox", help="Decoda valores via X3_CBOX da tabela SX correlata."),
    ] = False,
    funcao_field: Annotated[
        str | None,
        typer.Option(
            "--funcao-field", help="Coluna com nome de função ADVPL (p/ --resolve-callers)."
        ),
    ] = None,
    resolve_callers: Annotated[
        bool,
        typer.Option("--resolve-callers", help="Cruza --funcao-field com os fontes indexados."),
    ] = False,
) -> None:
    """Consulta um catálogo importado (#75): lista / filtra / agrega / cruza com fontes."""
    try:
        rows = _with_ro_db(
            ctx,
            lambda c: q_catalog(
                c,
                alias,
                filter_expr=filter_expr,
                group_by=group_by,
                count=count,
                decode_cbox=decode_cbox,
                funcao_field=funcao_field,
                resolve_callers=resolve_callers,
            ),
        )
    except ValueError as exc:  # filtro inválido
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    if not rows and not _with_ro_db(
        ctx, lambda c: any(m["alias"] == alias for m in catalog_list(c))
    ):
        typer.secho(
            f"Catálogo '{alias}' não encontrado (rode 'plugadvpl ingest-tsv <arq> --as {alias}').",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)
    _render_from_ctx(ctx, rows, title=f"Catálogo: {alias}")


@app.command(name="ingest-poui")
def ingest_poui_cmd(
    ctx: typer.Context,
    caminho: Annotated[str, typer.Argument(help="Diretório raiz do projeto PO UI")],
) -> None:
    """Ingere projeto(s) PO UI: detecta @po-ui/* + Angular exigido e flag de compatibilidade."""
    db_path: Path = ctx.obj["db"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        seed_lookups(conn)  # idempotente
        res = ingest_poui_dir(conn, Path(caminho))
        rows = q_poui_projetos(conn)
    finally:
        close_db(conn)
    linhas = [
        {
            "arquivo": r["caminho"],
            "poui": r["poui_version"],
            "angular": r["angular_major"],
            "compativel": "sim" if r["compativel"] else "NAO",
            "pacotes": ", ".join(r["pacotes"]),
        }
        for r in rows
    ]
    if not ctx.obj.get("quiet"):
        typer.secho(f"PO UI: {res.ingested} ingerido(s), {res.skipped} cache", err=True)
    _render_from_ctx(
        ctx,
        linhas,
        columns=["arquivo", "poui", "angular", "compativel", "pacotes"],
        title="PO UI projetos",
    )


@app.command(name="poui-bridge")
def poui_bridge(ctx: typer.Context) -> None:
    """Cruza datasources POUI (front Angular) com rotas REST do Protheus (back TLPP)."""
    db_path: Path = ctx.obj["db"]
    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        rows = q_poui_bridge(conn)
    finally:
        close_db(conn)
    linhas = [
        {
            "verbo": r["verbo"],
            "path": r["path"],
            "front": f"{r['front_arquivo']}:{r['front_linha']}",
            "back": f"{r['back_arquivo']} ({r['back_funcao']})",
        }
        for r in rows
    ]
    _render_from_ctx(
        ctx,
        linhas,
        columns=["verbo", "path", "front", "back"],
        title="POUI ↔ Protheus (ponte REST)",
    )


@app.command(name="poui-lint")
def poui_lint_cmd(ctx: typer.Context) -> None:
    """Lint PO UI: bindings `p-*` (POUI-PROP), interfaces `.ts` (POUI-IFACE) e import (POUI-IMPORT).

    - **POUI-PROP**: binding `p-*` em template `<po-*>` que não existe no catálogo.
    - **POUI-IFACE**: chave ou valor de objeto `.ts` tipado `Po*` inválido
      (ex.: `field` em vez de `property`, `type: 'money'` em vez de `'currency'`).
    - **POUI-IMPORT**: componente usado cujo pacote não é importado no projeto
      (ex.: `<po-page-dynamic-table>` de `@po-ui/ng-templates` sem importar o pacote).
    - **POUI-VERSION**: projeto num major PO UI diferente do catálogo embarcado
      (aviso — os findings acima podem divergir entre majors).

    Requer ``ingest-poui`` prévia (popula ``poui_componentes_uso``,
    ``poui_iface_uso`` e ``poui_imports``)."""
    db_path: Path = ctx.obj["db"]
    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        rows = (
            q_poui_lint(conn)
            + q_poui_iface_lint(conn)
            + q_poui_import_lint(conn)
            + q_poui_version_lint(conn)
        )
    finally:
        close_db(conn)
    rows.sort(key=lambda r: (r["arquivo"], r["linha"], r["regra"]))
    linhas = [
        {
            "arquivo": r["arquivo"],
            "linha": r["linha"],
            "regra": r["regra"],
            "alvo": f"{r['componente']}.{r['binding']}" if r["binding"] else r["componente"],
            "mensagem": r["mensagem"],
        }
        for r in rows
    ]
    _render_from_ctx(
        ctx,
        linhas,
        columns=["arquivo", "linha", "regra", "alvo", "mensagem"],
        title="POUI lint — POUI-PROP + POUI-IFACE + POUI-IMPORT",
    )


@app.command(name="ingest-protheus")
def ingest_protheus_cmd(
    ctx: typer.Context,
    endpoint: Annotated[
        str,
        typer.Option(
            "--endpoint",
            help="URL base REST do Protheus (ex: http://protheus:8181/rest)",
        ),
    ] = "",
    user: Annotated[
        str,
        typer.Option(
            "--user",
            help="User pra HTTP Basic auth. Fallback: env var PROTHEUS_USER.",
        ),
    ] = "",
    password: Annotated[
        str,
        typer.Option(
            "--password",
            help="Password pra HTTP Basic auth. Fallback: env var PROTHEUS_PASS.",
        ),
    ] = "",
    modo: Annotated[
        str,
        typer.Option(
            "--modo",
            help="'enxuto' (so tabelas com >= threshold rows) ou 'completo'.",
        ),
    ] = "enxuto",
    threshold: Annotated[
        int,
        typer.Option(
            "--threshold",
            help="Min de rows pra tabela contar como ativa (modo enxuto).",
        ),
    ] = 10,
    base_dir: Annotated[
        str,
        typer.Option(
            "--base-dir",
            help="Pasta NO SERVIDOR onde bundle e criado (vazio = default do servidor).",
        ),
    ] = "",
    ini_dir: Annotated[
        str,
        typer.Option(
            "--ini-dir",
            help="Pasta NO SERVIDOR dos appserver*.ini (vazio = DescobreRootPath).",
        ),
    ] = "",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="So roda /coletadb/run e mostra manifest, nao baixa nem ingere.",
        ),
    ] = False,
    timeout_run_s: Annotated[
        float,
        typer.Option("--timeout-run", help="Timeout do /coletadb/run em segundos."),
    ] = 300.0,
    timeout_file_s: Annotated[
        float,
        typer.Option("--timeout-file", help="Timeout do /coletadb/file (por chunk)."),
    ] = 60.0,
) -> None:
    """Indexa dicionario SX via REST API do COLETADB (Universo 5).

    Workflow: POST /coletadb/run -> manifest; POST /coletadb/file em loop
    pra baixar cada CSV em chunks de 4MB; chama ingest_sx no tmp local.

    Auth via HTTP Basic (AppServer Security=1). Reusa o MESMO user/senha
    do compile (env vars PROTHEUS_USER/PROTHEUS_PASS ou flags --user/--password).

    Convive com `ingest-sx` — quem nao tem COLETADB instalado continua
    usando CSV exportado do Configurador.
    """
    import os

    from plugadvpl.coletadb_client import ColetaDBClient, ColetaDBError

    if not endpoint:
        typer.secho(
            "--endpoint obrigatorio. Ex: --endpoint http://protheus:8181/rest",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    effective_user = user or os.environ.get("PROTHEUS_USER", "")
    effective_pass = password or os.environ.get("PROTHEUS_PASS", "")
    if not effective_user:
        typer.secho(
            "Auth obrigatoria: passe --user/--password ou defina "
            "PROTHEUS_USER/PROTHEUS_PASS (mesmas creds do compile).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if modo not in ("enxuto", "completo"):
        typer.secho(
            f"--modo deve ser 'enxuto' ou 'completo' (recebido: {modo!r})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    client = ColetaDBClient(
        endpoint=endpoint,
        user=effective_user,
        password=effective_pass,
        timeout_run_s=timeout_run_s,
        timeout_file_s=timeout_file_s,
    )

    db_path: Path = ctx.obj["db"]

    if dry_run:
        try:
            manifest = client.run(
                modo=modo,
                threshold=threshold,
                base_dir=base_dir,
                ini_dir=ini_dir,
            )
        except ColetaDBError as exc:
            typer.secho(f"FAIL: {exc}", fg=typer.colors.RED, err=True)
            if exc.hint:
                typer.secho(f"hint: {exc.hint}", fg=typer.colors.YELLOW, err=True)
            raise typer.Exit(code=1) from exc
        rows = [
            {
                "file": f.name,
                "size_bytes": f.size_bytes,
                "chunks": f.chunks,
                "sha256_short": f.sha256[:16] + "..." if f.sha256 else "",
            }
            for f in manifest.files
        ]
        _render_from_ctx(
            ctx,
            rows,
            title=(
                f"COLETADB manifest — bundle_id={manifest.bundle_id} "
                f"modo={manifest.modo} files={len(manifest.files)}"
            ),
        )
        return

    try:
        counters = do_ingest_via_rest(
            client,
            db_path,
            modo=modo,
            threshold=threshold,
            base_dir=base_dir,
            ini_dir=ini_dir,
        )
    except ColetaDBError as exc:
        typer.secho(f"FAIL: {exc}", fg=typer.colors.RED, err=True)
        if exc.hint:
            typer.secho(f"hint: {exc.hint}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1) from exc

    ingest_inner = counters.get("ingest_counters", {})
    summary_rows: list[dict[str, object]] = [
        {
            "tabela": tabela,
            "rows": ingest_inner.get("per_table", {}).get(tabela, 0),
        }
        for tabela in (
            "tabelas",
            "campos",
            "indices",
            "gatilhos",
            "parametros",
            "perguntas",
            "tabelas_genericas",
            "relacionamentos",
            "pastas",
            "consultas",
            "grupos_campo",
        )
    ]
    summary_rows.append(
        {"tabela": "_TOTAL", "rows": ingest_inner.get("total_rows", 0)},
    )

    if not ctx.obj["quiet"]:
        mb = counters.get("bytes_downloaded", 0) / (1024 * 1024)
        typer.secho(
            f"OK {counters['files_downloaded']} arquivos baixados "
            f"({mb:.1f}MB, {counters.get('files_skipped', 0)} non-MVP pulados) "
            f"em {counters['duration_ms']}ms — bundle {counters['bundle_id'][:16]}",
            err=True,
        )
    _render_from_ctx(
        ctx,
        summary_rows,
        title=f"Ingest REST — rows por tabela (bundle {counters['bundle_id'][:8]})",
        next_steps=[
            "plugadvpl impacto A1_COD",
            "plugadvpl gatilho A1_COD",
        ],
    )


@app.command()
def impacto(
    ctx: typer.Context,
    campo: Annotated[
        str,
        typer.Argument(help="Nome do campo SX3 (ex: A1_COD)."),
    ],
    depth: Annotated[
        int,
        typer.Option(
            "--depth",
            "-d",
            min=1,
            max=3,
            help="Profundidade da cadeia de gatilhos SX7 (1..3).",
        ),
    ] = 1,
) -> None:
    """Cruza referencias a um campo: fontes <-> SX3 (VALID/WHEN/INIT) <-> SX7 <-> SX1.

    Killer feature do v0.3.0. Em segundos: para um campo arbitrário, lista TODA
    a cadeia de impacto (fontes que mencionam, validações que dependem,
    gatilhos que disparam, perguntas SX1 que referenciam).
    """
    rows = _with_ro_db(ctx, lambda c: impacto_query(c, campo, depth=depth))
    columns = ["tipo", "local", "contexto", "severidade"]
    _render_from_ctx(
        ctx,
        rows,
        columns=columns,
        title=f"Impacto de {campo.upper()} (depth={depth})",
        next_steps=(
            [
                f"plugadvpl gatilho {campo}",
                f"plugadvpl tables {campo.split('_')[0] if '_' in campo else campo}",
            ]
            if rows
            else None
        ),
    )


@app.command()
def gatilho(
    ctx: typer.Context,
    campo: Annotated[
        str,
        typer.Argument(help="Nome do campo SX3 (ex: A1_COD)."),
    ],
    depth: Annotated[
        int,
        typer.Option(
            "--depth",
            "-d",
            min=1,
            max=3,
            help="Profundidade da cadeia (1..3). Default 3.",
        ),
    ] = 3,
) -> None:
    """Lista cadeia de gatilhos SX7 originados/destinados ao campo."""
    rows = _with_ro_db(ctx, lambda c: gatilho_query(c, campo, depth=depth))
    columns = ["nivel", "via", "origem", "sequencia", "destino", "regra", "tipo"]
    _render_from_ctx(
        ctx,
        rows,
        columns=columns,
        title=f"Cadeia de gatilhos SX7 — {campo.upper()} (depth={depth})",
        next_steps=[f"plugadvpl impacto {campo}"] if rows else None,
    )


@app.command(name="sx-status")
def sx_status_cmd(ctx: typer.Context) -> None:
    """Mostra contadores por tabela do Dicionário SX (após ``ingest-sx``)."""
    rows = _with_ro_db(ctx, sx_status)
    _render_from_ctx(
        ctx,
        rows,
        title="Status do Dicionário SX",
        next_steps=(
            ["plugadvpl ingest-sx <pasta-csv>"]
            if rows and not rows[0].get("sx_ingerido")
            else ["plugadvpl impacto A1_COD"]
        ),
    )


# ---------------------------------------------------------------------------
# v0.4.0 — Universo 3 (Rastreabilidade) Feature A: workflow
# ---------------------------------------------------------------------------


@app.command()
def workflow(
    ctx: typer.Context,
    kind: Annotated[
        WorkflowKind | None,
        typer.Option(
            "--kind",
            "-k",
            help="Filtra por tipo: workflow|schedule|job_standalone|mail_send",
            case_sensitive=False,
        ),
    ] = None,
    target: Annotated[
        str | None,
        typer.Option("--target", "-t", help="Filtra por nome alvo (callback/Main/pergunte)."),
    ] = None,
    arquivo: Annotated[
        str | None,
        typer.Option("--arquivo", "-a", help="Filtra por arquivo (basename)."),
    ] = None,
    duplicates: Annotated[
        bool,
        typer.Option(
            "--duplicates",
            help="v0.4.6 (K): lista targets (process_id/Main/pergunte) compartilhados "
            "entre 2+ fontes — detecta erros de design (mesmo Process ID reusado).",
        ),
    ] = False,
) -> None:
    """Lista execution_triggers indexados (Universo 3 / Feature A).

    Detecta 4 mecanismos canônicos TOTVS de "execução não-direta":

    - ``workflow``       — TWFProcess / MsWorkflow / WFPrepEnv (callbacks)
    - ``schedule``       — Static Function SchedDef() (configurador SIGACFG)
    - ``job_standalone`` — Main Function + RpcSetEnv (daemon ONSTART)
    - ``mail_send``      — MailAuto / SEND MAIL UDC / TMailManager

    Sem filtros: lista tudo. Com ``--kind`` mostra só uma categoria.
    Com ``--duplicates`` mostra apenas targets em conflito.
    """
    if duplicates:
        dup_rows = _with_ro_db(
            ctx,
            lambda c: execution_triggers_duplicates(c, kind=kind),
        )
        display_dup = [
            {
                "kind": r["kind"],
                "target": r["target"],
                "count": r["count"],
                "arquivos": ", ".join(r["arquivos"]),
            }
            for r in dup_rows
        ]
        _render_from_ctx(
            ctx,
            display_dup,
            columns=["kind", "target", "count", "arquivos"],
            title=f"Workflow targets duplicados{f' (kind={kind})' if kind else ''}",
            next_steps=(
                [f"plugadvpl workflow --target {dup_rows[0]['target']}"] if dup_rows else None
            ),
        )
        return
    rows = _with_ro_db(
        ctx,
        lambda c: execution_triggers_query(c, kind=kind, target=target, arquivo=arquivo),
    )
    # Renderiza só os campos top-level; metadata fica em JSON.
    display_rows = [
        {
            "arquivo": r["arquivo"],
            "funcao": r["funcao"],
            "linha": r["linha"],
            "kind": r["kind"],
            "target": r["target"],
            "snippet": (r["snippet"] or "")[:80],
        }
        for r in rows
    ]
    _augment_with_caminho(ctx, display_rows)  # v0.4.6 (D)
    _render_from_ctx(
        ctx,
        display_rows,
        columns=["arquivo", "funcao", "linha", "kind", "target", "snippet"],
        title=(
            "Execution triggers"
            + (f" (kind={kind})" if kind else "")
            + (f" (target={target})" if target else "")
            + (f" (arquivo={arquivo})" if arquivo else "")
        ),
        next_steps=(
            # v0.4.6 (I): dedupe preservando ordem (set comprehension não garante).
            [
                f"plugadvpl find {t}"
                for t in dict.fromkeys(r["target"] for r in rows[:3] if r["target"])
            ]
            if rows
            else _empty_result_hints(
                bool(kind or target or arquivo),
                table_label="execution trigger",
            )
        ),
    )


# ---------------------------------------------------------------------------
# v0.4.1 — Universo 3 (Rastreabilidade) Feature B: execauto
# ---------------------------------------------------------------------------


@app.command()
def execauto(
    ctx: typer.Context,
    routine: Annotated[
        str | None,
        typer.Option("--routine", "-r", help="Filtra por rotina TOTVS (MATA410, FINA050, ...)."),
    ] = None,
    modulo: Annotated[
        str | None,
        typer.Option("--modulo", "-m", help="Filtra por módulo (SIGAFAT, SIGACOM, SIGAFIN, ...)."),
    ] = None,
    arquivo: Annotated[
        str | None,
        typer.Option("--arquivo", "-a", help="Filtra por arquivo (basename, case-insensitive)."),
    ] = None,
    op: Annotated[
        ExecAutoOp | None,
        typer.Option(
            "--op",
            "-o",
            help="Filtra por operação: inc|alt|exc (op_code 3/4/5).",
            case_sensitive=False,
        ),
    ] = None,
    dynamic: Annotated[
        bool | None,
        typer.Option(
            "--dynamic/--no-dynamic",
            help="--dynamic só não-resolvíveis; --no-dynamic só resolvidas; default: ambos.",
        ),
    ] = None,
    op_dynamic: Annotated[
        bool | None,
        typer.Option(
            "--op-dynamic/--no-op-dynamic",
            help="v0.4.6 (C): --op-dynamic só calls com op_code via variável/expressão; "
            "--no-op-dynamic só com literal; default: ambos.",
        ),
    ] = None,
) -> None:
    """Lista chamadas MsExecAuto resolvidas (Universo 3 / Feature B).

    Resolve a indireção do codeblock ``{|args| Rotina(args)}`` e cruza com o
    catálogo TOTVS pra inferir tabelas tocadas, módulo, e tipo de operação
    (inclusão/alteração/exclusão).

    Sem filtros: lista todas as chamadas. Use ``--routine MATA410`` pra ver
    quem inclui Pedido de Venda; ``--dynamic`` pra revisar calls não-resolvíveis.
    """
    rows = _with_ro_db(
        ctx,
        lambda c: execauto_calls_query(
            c,
            routine=routine,
            modulo=modulo,
            arquivo=arquivo,
            op=op,
            dynamic=dynamic,
            op_dynamic=op_dynamic,
        ),
    )
    display_rows = [
        {
            "arquivo": r["arquivo"],
            "funcao": r["funcao"],
            "linha": r["linha"],
            "routine": r["routine"] or "(dynamic)",
            "module": r["module"] or "",
            "op": r["op_label"]
            or (
                str(r["op_code"])
                if r["op_code"] is not None
                else ("(var)" if r["op_dynamic"] else "")
            ),
            "tabelas": ",".join(r["tables_resolved"]),
            "snippet": (r["snippet"] or "")[:80],
        }
        for r in rows
    ]
    _augment_with_caminho(ctx, display_rows)  # v0.4.6 (D)
    _render_from_ctx(
        ctx,
        display_rows,
        columns=["arquivo", "funcao", "linha", "routine", "module", "op", "tabelas", "snippet"],
        title=(
            "ExecAuto calls"
            + (f" (routine={routine})" if routine else "")
            + (f" (modulo={modulo})" if modulo else "")
            + (f" (arquivo={arquivo})" if arquivo else "")
            + (f" (op={op})" if op else "")
            + (" (dynamic)" if dynamic else "")
        ),
        next_steps=(
            # v0.4.6 (I): dedupe preservando ordem (set não garante).
            [f"plugadvpl arch {arq}" for arq in dict.fromkeys(r["arquivo"] for r in rows[:3])]
            if rows
            else _empty_result_hints(
                bool(routine or modulo or arquivo or op or dynamic is not None),
                table_label="execauto call",
                extra_when_filtered=[
                    *_execauto_modulo_hints(ctx, modulo),
                    "  plugadvpl execauto --dynamic     # ver calls não-resolvíveis",
                ],
            )
        ),
    )


def _execauto_modulo_hints(ctx: typer.Context, modulo_filter: str | None) -> list[str]:
    """v0.4.6 (E): se filtro --modulo X foi usado e nao deu match, sugere
    os top-5 modulos disponiveis no indice."""
    if not modulo_filter:
        return []
    available = _with_ro_db(ctx, lambda c: execauto_top_modulos(c, 5))
    if not available:
        return []
    return [f"  Módulos disponíveis: {', '.join(available)}"]


# ---------------------------------------------------------------------------
# v0.4.2 — Universo 3 (Rastreabilidade) Feature C: docs
# ---------------------------------------------------------------------------


@app.command()
def docs(
    ctx: typer.Context,
    modulo: Annotated[
        str | None,
        typer.Argument(
            help="Módulo TOTVS pra filtrar (SIGAFAT, SIGACOM, ...). Sem valor: lista tudo."
        ),
    ] = None,
    author: Annotated[
        str | None,
        typer.Option("--author", help="Filtra por autor (LIKE %valor%, case-insensitive)."),
    ] = None,
    funcao: Annotated[
        str | None,
        typer.Option("--funcao", "-f", help="Filtra por nome de função (exact match)."),
    ] = None,
    arquivo: Annotated[
        str | None,
        typer.Option("--arquivo", "-a", help="Filtra por arquivo (basename)."),
    ] = None,
    deprecated: Annotated[
        bool | None,
        typer.Option("--deprecated/--no-deprecated", help="Só @deprecated / só ativos / ambos."),
    ] = None,
    tipo: Annotated[
        str | None,
        typer.Option("--tipo", "-t", help="Filtra por @type (function, method, class, ...)."),
    ] = None,
    show: Annotated[
        str | None,
        typer.Option("--show", help="Mostra doc completo de uma função em Markdown estruturado."),
    ] = None,
    orphans: Annotated[
        bool,
        typer.Option(
            "--orphans", help="Lista funções SEM Protheus.doc (cross-ref BP-007 do lint)."
        ),
    ] = False,
) -> None:
    """Catálogo de Protheus.doc agregado (Universo 3 / Feature C).

    Sem args: lista todos os blocos indexados. Com ``[modulo]``: filtra por
    módulo (path-inferido). Use ``--show <funcao>`` pra ver o bloco completo
    formatado em Markdown. Use ``--orphans`` pra ver funções sem header.
    """
    if show:
        # v0.4.3 (I2): com homônimos, --arquivo desambiguar; sem --arquivo,
        # avisa em stderr e mostra o primeiro alfabeticamente.
        homonyms = _with_ro_db(ctx, lambda c: protheus_doc_homonyms(c, show))
        if not homonyms:
            typer.echo(f"Nenhum Protheus.doc encontrado pra função '{show}'.", err=True)
            raise typer.Exit(code=1)
        if len(homonyms) > 1 and not arquivo:
            typer.echo(
                f"Aviso: '{show}' tem doc em {len(homonyms)} fontes: "
                f"{', '.join(homonyms)}. Mostrando '{homonyms[0]}'. "
                f"Use --arquivo <nome> pra escolher.",
                err=True,
            )
        d = _with_ro_db(ctx, lambda c: protheus_doc_show(c, show, arquivo=arquivo))
        if d is None:
            typer.echo(
                f"Nenhum Protheus.doc encontrado pra '{show}' em '{arquivo}'.",
                err=True,
            )
            raise typer.Exit(code=1)
        typer.echo(render_pdoc_markdown(d))
        return

    if orphans:
        rows = _with_ro_db(ctx, protheus_docs_orphans)
        _render_from_ctx(
            ctx,
            rows,
            columns=["arquivo", "funcao", "linha", "snippet"],
            title="Funções sem Protheus.doc (BP-007)",
            next_steps=(
                [f"plugadvpl find {r['funcao']}" for r in rows[:3] if r.get("funcao")]
                if rows
                else ["plugadvpl lint --regra BP-007  # ver findings raw"]
            ),
        )
        return

    rows = _with_ro_db(
        ctx,
        lambda c: protheus_docs_query(
            c,
            modulo=modulo,
            author=author,
            funcao=funcao,
            arquivo=arquivo,
            deprecated=deprecated,
            tipo=tipo,
        ),
    )
    display_rows = [
        {
            "arquivo": r["arquivo"],
            "funcao": r["funcao"] or r["funcao_id"] or "",
            "modulo": r["module_inferido"] or "",
            "tipo": r["tipo"] or "",
            "author": r["author"] or "",
            "since": r["since"] or "",
            "deprecated": "sim" if r["deprecated"] else "",
            "summary": (r["summary"] or "").replace("\n", " ")[:80],
        }
        for r in rows
    ]
    _augment_with_caminho(ctx, display_rows)  # v0.4.6 (D)
    _render_from_ctx(
        ctx,
        display_rows,
        columns=["arquivo", "funcao", "modulo", "tipo", "author", "since", "deprecated", "summary"],
        title=(
            "Protheus.doc"
            + (f" (modulo={modulo})" if modulo else "")
            + (f" (author={author})" if author else "")
            + (" (deprecated)" if deprecated else "")
        ),
        next_steps=(
            [f"plugadvpl docs --show {r['funcao']}" for r in rows[:3] if r.get("funcao")]
            if rows
            else _empty_result_hints(
                bool(modulo or author or funcao or arquivo or deprecated is not None or tipo),
                table_label="Protheus.doc",
                extra_when_filtered=[
                    *_docs_modulo_hints(ctx, modulo),
                    "  plugadvpl docs --orphans         # funções sem header (BP-007)",
                ],
            )
        ),
    )


def _docs_modulo_hints(ctx: typer.Context, modulo_filter: str | None) -> list[str]:
    """v0.4.6 (E): se filtro [modulo] foi usado e não deu match, sugere
    os top-5 módulos disponíveis no índice de protheus_docs."""
    if not modulo_filter:
        return []
    available = _with_ro_db(ctx, lambda c: protheus_docs_top_modulos(c, 5))
    if not available:
        return []
    return [f"  Módulos disponíveis: {', '.join(available)}"]


# ---------------------------------------------------------------------------
# v0.5.0 — Universo 4 (Trace unificado) Feature A: trace
# ---------------------------------------------------------------------------


@app.command()
def trace(
    ctx: typer.Context,
    entidade: Annotated[
        str,
        typer.Argument(
            help="Entidade a rastrear: campo (A1_COD), função (MaFisRef) ou tabela (SC5)."
        ),
    ],
    tipo: Annotated[
        TraceTipo | None,
        typer.Option(
            "--tipo",
            "-t",
            help=(
                "Força tipo de entidade. Aceita: campo, funcao, tabela, "
                "arquivo (.prw/.tlpp), parametro (MV_*/ABC_*/etc), pergunte "
                "(SX1). Default: auto-detect."
            ),
            case_sensitive=False,
        ),
    ] = None,
    depth: Annotated[
        int,
        typer.Option(
            "--depth",
            "-d",
            help="Profundidade de BFS (1..3, default 2). Aplica em campo (gatilhos transitivos).",
        ),
    ] = 2,
    universo: Annotated[
        str | None,
        typer.Option(
            "--universo",
            "-u",
            help="Filtra universos (1=fontes, 2=SX, 3=workflow/execauto/docs). Múltiplos: '1,2'.",
        ),
    ] = None,
    max_per_edge: Annotated[
        int,
        typer.Option(
            "--max-per-edge",
            help="Limite de hits por tipo de aresta (default 20). Evita explosão em entidades comuns.",
        ),
    ] = 20,
) -> None:
    """Trace agregado cross-universo (Universo 4 / Feature A).

    Atravessa fontes (U1) + dicionário SX (U2) + rastreabilidade
    (U3: workflow/execauto/protheus_doc) e devolve em uma única lista todas
    as arestas que tocam a entidade-alvo.

    Substitui o workflow manual de 5 comandos:
    `impacto` + `gatilho` + `tables` + `callers` + `execauto` → `trace`.
    """
    # Parse --universo "1,2" -> [1, 2]
    universos: list[int] | None = None
    if universo:
        try:
            universos = sorted({int(x.strip()) for x in universo.split(",") if x.strip()})
            universos = [u for u in universos if u in (1, 2, 3)]
        except ValueError:
            typer.echo(
                f"--universo aceita lista de 1/2/3 (ex: '1,2'). Valor inválido: {universo!r}",
                err=True,
            )
            raise typer.Exit(code=2) from None

    tipo_str = tipo.value if tipo else None
    rows = _with_ro_db(
        ctx,
        lambda c: trace_query(
            c,
            entidade,
            tipo=tipo_str,
            depth=depth,
            universos=universos,
            max_per_edge=max_per_edge,
        ),
    )
    # v0.5.1 (#2): para display, usa lookup-first também (mesma classificação
    # que trace_query usou internamente).
    tipo_detected = tipo_str or _with_ro_db(ctx, lambda c: _detect_entity_type_db(c, entidade))
    title_parts = [f"Trace de '{entidade}' (tipo={tipo_detected})"]
    if universos:
        title_parts.append(f"universos={','.join(map(str, universos))}")
    if depth != 2:  # noqa: PLR2004 -- default semantico do trace; ver _DEFAULT_DEPTH em query.py
        title_parts.append(f"depth={depth}")

    _render_from_ctx(
        ctx,
        rows,
        columns=["universo", "edge", "arquivo", "funcao", "linha", "alvo", "contexto", "snippet"],
        title=" | ".join(title_parts),
        next_steps=(
            _trace_next_steps(rows, tipo_detected) if rows else _trace_empty_hints(ctx, entidade)
        ),
    )


def _trace_empty_hints(ctx: typer.Context, entidade: str) -> list[str]:
    """v0.5.1 (#3): hint inteligente quando trace retorna vazio.

    Antes: sempre sugeria ``ingest --no-incremental``. Em índice populado
    (caso comum), isso induzia reingest caro pra typo. Agora: detecta se
    índice tem dados e sugere ``find``/``grep`` (caso typo) ou reingest
    (caso índice realmente vazio).
    """
    n_fontes = _with_ro_db(ctx, lambda c: c.execute("SELECT COUNT(*) FROM fontes").fetchone()[0])
    if n_fontes > 0:
        return [
            f"Nenhum hit para '{entidade}' — pode ser typo. Verifique o nome:",
            f"  plugadvpl find {entidade}            # busca em fontes/SX",
            f"  plugadvpl grep {entidade} -m identifier   # match por simbolo",
        ]
    return [
        "Indice vazio. Rode:",
        "  plugadvpl ingest --no-incremental",
    ]


def _trace_next_steps(rows: list[dict[str, Any]], tipo: str) -> list[str]:  # noqa: PLR0911 -- next-step por tipo de entidade (file/function/table/...); cada return e match curto
    """v0.5.0+: sugere próximo comando baseado no tipo detectado."""
    if tipo == "campo":
        return ["  plugadvpl impacto <campo>   # análise detalhada SX (depth maior)"]
    if tipo == "funcao":
        fns = {r["arquivo"] for r in rows[:3] if r.get("arquivo")}
        return [f"  plugadvpl arch {arq}" for arq in fns][:3]
    if tipo == "tabela":
        return [f"  plugadvpl tables {rows[0]['alvo']} --mode write  # detalhe write"]
    if tipo == "arquivo":
        # v0.5.3 (A.2): arch dá visão consolidada, lint detalhe
        return [
            f"  plugadvpl arch {rows[0]['arquivo']}    # capabilities/tabelas detalhado",
            f"  plugadvpl lint --arquivo {rows[0]['arquivo']}   # findings completos",
        ]
    if tipo == "parametro":
        return ["  plugadvpl param <MV_*>     # uso detalhado por fonte"]
    if tipo == "pergunte":
        return ["  plugadvpl impacto <campo>  # se pergunte referencia campo SX3"]
    return []


# Import lazy do _detect_entity_type / _detect_entity_type_db (declarados em query.py).
from plugadvpl.query import _detect_entity_type_db  # noqa: E402

# ---------------------------------------------------------------------------
# v0.6.0 — Universo 4 (Qualidade & Métricas) Feature B
# ---------------------------------------------------------------------------


class MetricsSort(StrEnum):
    """Campos de sort do comando ``metrics`` (Universo 4 Feature B)."""

    cc = "cc"
    loc = "loc"
    nesting = "nesting"
    calls = "calls"
    params = "params"


class CoberturaGroupBy(StrEnum):
    """Agrupamento do comando ``cobertura-doc``."""

    modulo = "modulo"
    source_type = "source_type"


@app.command()
def metrics(
    ctx: typer.Context,
    arquivo: Annotated[
        str | None,
        typer.Argument(help="Filtra por arquivo (basename, case-insensitive). Sem valor: todos."),
    ] = None,
    min_cc: Annotated[
        int,
        typer.Option("--min-cc", help="Filtra funções com CC >= N (default 0 = sem filtro)."),
    ] = 0,
    min_loc: Annotated[
        int,
        typer.Option("--min-loc", help="Filtra funções com LOC >= N (default 0)."),
    ] = 0,
    sort: Annotated[
        MetricsSort,
        typer.Option(
            "--sort", "-s", help="Ordem desc: cc|loc|nesting|calls|params.", case_sensitive=False
        ),
    ] = MetricsSort.cc,
) -> None:
    """Métricas por função (Universo 4 / Feature B).

    Complexidade ciclomática (McCabe), LOC, profundidade aninhamento,
    fan-out (n_calls_out) e contagem de parâmetros — uma row por função
    indexada.

    Use ``--min-cc 10`` pra ver só funções complexas (candidatas refactor).
    Use ``--sort loc`` pra ranking por tamanho.
    """
    rows = _with_ro_db(
        ctx,
        lambda c: metrics_query(
            c,
            arquivo=arquivo,
            min_cc=min_cc,
            min_loc=min_loc,
            sort=sort.value,
        ),
    )
    # v0.6.0: mantém schema completo no dict (JSON consumer); columns
    # filtra display tabular.
    display_rows = [
        {
            "arquivo": r["arquivo"],
            "funcao": r["funcao"],
            "linha": r["linha_inicio"],
            "loc": r["loc"],
            "cc": r["cc"],
            "nesting": r["nesting"],
            "n_calls_out": r["n_calls_out"],
            "params_count": r["params_count"],
            "has_doc": r["has_doc"],
        }
        for r in rows
    ]
    _render_from_ctx(
        ctx,
        display_rows,
        columns=[
            "arquivo",
            "funcao",
            "linha",
            "loc",
            "cc",
            "nesting",
            "n_calls_out",
            "params_count",
            "has_doc",
        ],
        title=(
            "Métricas"
            + (f" (arquivo={arquivo})" if arquivo else "")
            + (f" (cc>={min_cc})" if min_cc else "")
            + (f" (loc>={min_loc})" if min_loc else "")
            + f" sort={sort.value}"
        ),
        next_steps=(
            [f"plugadvpl arch {rows[0]['arquivo']}    # contexto do fonte top"]
            if rows
            else ["plugadvpl ingest --no-incremental  # se esperava métricas"]
        ),
    )


@app.command()
def hotspots(
    ctx: typer.Context,
    n: Annotated[
        int,
        typer.Option("--n", help="Top-N funções (default 20)."),
    ] = 20,
    no_natives: Annotated[
        bool,
        typer.Option(
            "--no-natives/--with-natives",
            help="--no-natives (default): exclui funções TOTVS nativas (ConOut/RecLock/etc) pra refactor priority. --with-natives: inclui.",
        ),
    ] = True,
    tipo: Annotated[
        str | None,
        typer.Option(
            "--tipo", "-t", help="Filtra tipo de chamada: user_func|method|execauto|execblock."
        ),
    ] = None,
) -> None:
    """Top-N funções mais chamadas no projeto (Universo 4 / Feature B).

    Refactor priority: funções com `n_calls` alto são bons candidatos pra
    revisão (mudança aqui impacta muito código). Filtra nativas TOTVS
    por default — sem filtro top-20 vira `RecLock`/`ConOut`/`DbSelectArea`.
    """
    rows = _with_ro_db(
        ctx,
        lambda c: hotspots_query(c, n=n, excluir_nativas=no_natives, tipo=tipo),
    )
    # v0.6.1 (bug #1): detector de method dedup — emite warning quando vê
    # múltiplos `VAR:METODO` com mesmo sufixo `:METODO`. Sintoma típico de
    # mesma classe (TPrinter:Say) acessada via vars com nomes diferentes
    # (oPrint/oPrn/oPrinter). Type inference real ficaria muito caro;
    # warning informa sem agregar erroneamente.
    _warn_hotspot_method_dedup(rows)
    _render_from_ctx(
        ctx,
        rows,
        columns=["destino", "n_calls", "n_arquivos", "n_callsites"],
        title=(
            f"Hotspots top-{n}"
            + (" (sem nativas)" if no_natives else " (com nativas)")
            + (f" tipo={tipo}" if tipo else "")
        ),
        next_steps=(
            [f"plugadvpl callers {rows[0]['destino']}    # callsites detalhados"] if rows else None
        ),
    )


def _warn_hotspot_method_dedup(rows: list[dict[str, Any]]) -> None:
    """v0.6.1 (bug #1): detecta agrupamentos prováveis de mesma classe.

    Agrupa rows por sufixo `:METODO`. Se >= 2 rows compartilham sufixo,
    emite warning em stderr (typer.echo err=True) listando-os e somando
    n_calls combinado.
    """
    from collections import defaultdict

    by_method: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        dest = r.get("destino") or ""
        if ":" not in dest:
            continue
        method = dest.rsplit(":", 1)[-1].upper()
        by_method[method].append(r)
    groups = [(m, lst) for m, lst in by_method.items() if len(lst) >= 2]  # noqa: PLR2004 -- min pra ser duplicate group
    if not groups:
        return
    for method, items in groups:
        labels = ", ".join(f"{r['destino']} ({r['n_calls']})" for r in items)
        total = sum(r["n_calls"] for r in items)
        typer.echo(
            f"Aviso: '{labels}' compartilham método ':{method}' — "
            f"provavelmente mesma classe via vars distintas. Soma efetiva: ~{total}.",
            err=True,
        )


@app.command(name="cobertura-doc")
def cobertura_doc(
    ctx: typer.Context,
    groupby: Annotated[
        CoberturaGroupBy,
        typer.Option(
            "--groupby",
            "-g",
            help="Agrupar por: modulo (default) ou source_type.",
            case_sensitive=False,
        ),
    ] = CoberturaGroupBy.modulo,
) -> None:
    """Cobertura de Protheus.doc agregada (Universo 4 / Feature B).

    Mostra % de funções com header Protheus.doc por módulo (default) ou
    por source_type (mvc/rest/cadastro/relatorio/outro).

    Ordenado por pct asc — **pior cobertura primeiro** (refactor priority).
    """
    rows = _with_ro_db(
        ctx,
        lambda c: cobertura_doc_query(c, groupby=groupby.value),
    )
    _render_from_ctx(
        ctx,
        rows,
        columns=["grupo", "total", "com_doc", "pct"],
        title=f"Cobertura Protheus.doc (por {groupby.value})",
        next_steps=(
            [
                "plugadvpl docs --orphans            # funções sem header",
                "plugadvpl lint --regra BP-007       # raw findings",
            ]
            if rows
            else [
                # v0.6.1 (UX #3): hint quando tabela vazia (consistente com `metrics`).
                "plugadvpl ingest --no-incremental    # popular fonte_metrics (schema v10+)",
                "plugadvpl docs --orphans              # lista bruta de funções sem header",
                "plugadvpl lint --regra BP-007         # findings de header faltando",
            ]
        ),
    )


# ---------------------------------------------------------------------------
# doc-writer (v0.17.0): gera bloco Protheus.doc pra função
# ---------------------------------------------------------------------------


@app.command(name="doc-writer")
def doc_writer_cmd(
    ctx: typer.Context,
    funcao: Annotated[
        str,
        typer.Argument(help="Nome da função/método/classe ADVPL/TLPP."),
    ],
    tipo: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help=(
                "Valor de @type: function (default), user_function, method, "
                "class, property. Convenção TOTVS."
            ),
        ),
    ] = "function",
    summary: Annotated[
        str | None,
        typer.Option(
            "--summary",
            "-s",
            help="Descrição curta (aparece logo abaixo do header).",
        ),
    ] = None,
    author: Annotated[
        str | None,
        typer.Option("--author", "-a", help="@author"),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="@since (ex: '2026-05-30' ou '12.1.2210')."),
    ] = None,
    version: Annotated[
        str | None,
        typer.Option("--version", help="@version"),
    ] = None,
    deprecated: Annotated[
        str | None,
        typer.Option(
            "--deprecated",
            help=(
                "Motivo da depreciação. Vazio (sem valor) marca como deprecated "
                "sem reason; ausente = não deprecated."
            ),
        ),
    ] = None,
    params: Annotated[
        list[str] | None,
        typer.Option(
            "--param",
            "-p",
            help=(
                "Param spec: 'nome,tipo,desc' (repetível). Use [nome] pra "
                "marcar opcional, ex: '[nIdx],numeric,indice opcional'."
            ),
        ),
    ] = None,
    returns: Annotated[
        str | None,
        typer.Option(
            "--return",
            "-r",
            help="Return spec: 'tipo,desc' (ex: 'logical,True se sucesso').",
        ),
    ] = None,
    examples: Annotated[
        list[str] | None,
        typer.Option(
            "--example",
            "-e",
            help="Exemplo de uso (repetível). Aceita multi-linha via \\n.",
        ),
    ] = None,
) -> None:
    """Gera bloco ``/*/{Protheus.doc} ... /*/`` pra função ADVPL/TLPP.

    Imprime no stdout pronto pra colar antes da declaração da função.
    Padrão oficial TOTVS, roundtrip-compatible com ``plugadvpl docs``.

    Exemplos:

    .. code-block:: bash

        # Mínimo
        plugadvpl doc-writer MinhaFunc

        # Completo
        plugadvpl doc-writer CalcICMS --type user_function \\
            --author "Joao Silva" --since 2026-05 \\
            --summary "Calcula ICMS conforme TES informada." \\
            -p "cTES,character,codigo TES" \\
            -p "[nValor],numeric,valor base (opcional)" \\
            --return "numeric,valor do ICMS calculado" \\
            --example "nIcms := U_CalcICMS('501', 1000)"

    Para depois aplicar no fonte: redirecione e edite manualmente, ou
    use ``plugadvpl edit-prw stage`` antes de manipular .prw cp1252.
    """
    from plugadvpl.doc_writer import (
        generate_protheus_doc,
        spec_from_cli_args,
        spec_to_dict,
    )

    spec = spec_from_cli_args(
        funcao=funcao,
        tipo=tipo,
        summary=summary,
        author=author,
        since=since,
        version=version,
        deprecated=deprecated,
        params=params,
        returns=returns,
        examples=examples,
    )

    fmt = ctx.obj.get("format", "table") if ctx.obj else "table"
    if fmt == "json":
        import json

        typer.echo(json.dumps(spec_to_dict(spec), ensure_ascii=False, indent=2))
    else:
        typer.echo(generate_protheus_doc(spec))


# ---------------------------------------------------------------------------
# edit-prw (v0.7.0 Fase 0 #5): converte CP1252 <-> UTF-8
# ---------------------------------------------------------------------------


edit_prw_app = typer.Typer(
    name="edit-prw",
    help="Detecta/converte encoding de fontes ADVPL (.prw=cp1252) e TLPP (.tlpp=utf-8).",
    no_args_is_help=True,
)
app.add_typer(edit_prw_app, name="edit-prw")


@edit_prw_app.command("check")
def edit_prw_check(
    ctx: typer.Context,
    arquivo: Annotated[Path, typer.Argument(help="Caminho do fonte a inspecionar.")],
) -> None:
    """Reporta encoding detectado vs esperado pela extensão. Exit 1 se divergir."""

    from plugadvpl.edit_prw import check_encoding

    if not arquivo.exists():
        typer.secho(f"Arquivo nao encontrado: {arquivo}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    report = check_encoding(arquivo)
    _render_from_ctx(
        ctx,
        [report.to_dict()],
        columns=[
            "file",
            "extension",
            "expected_encoding",
            "detected_encoding",
            "has_bom",
            "match",
            "non_ascii_bytes",
        ],
        title=f"edit-prw check {arquivo.name}",
    )
    if not report.match:
        raise typer.Exit(code=1)


@edit_prw_app.command("open")
def edit_prw_open(
    arquivo: Annotated[Path, typer.Argument(help="Caminho do fonte a imprimir como UTF-8.")],
) -> None:
    """Imprime conteudo em UTF-8 puro (auto-detecta encoding de origem)."""

    from plugadvpl.edit_prw import read_as_utf8

    if not arquivo.exists():
        typer.secho(f"Arquivo nao encontrado: {arquivo}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    text = read_as_utf8(arquivo)
    # Escreve direto em UTF-8 pra evitar transcoding do typer/console.
    sys.stdout.buffer.write(text.encode("utf-8"))


@edit_prw_app.command("save")
def edit_prw_save(
    ctx: typer.Context,
    arquivo: Annotated[Path, typer.Argument(help="Caminho do fonte a converter in-place.")],
    from_encoding: Annotated[
        str | None,
        typer.Option("--from", help="Encoding de origem (default: auto-detect)."),
    ] = None,
    to_encoding: Annotated[
        str | None,
        typer.Option("--to", help="Encoding de destino (default: por extensao)."),
    ] = None,
    no_backup: Annotated[
        bool,
        typer.Option("--no-backup", help="Nao criar arquivo .bak antes de gravar."),
    ] = False,
) -> None:
    """Converte arquivo in-place. Default: auto-detecta origem + destino pela extensao."""

    from plugadvpl.edit_prw import convert_and_save

    if not arquivo.exists():
        typer.secho(f"Arquivo nao encontrado: {arquivo}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    try:
        src, dst, bak = convert_and_save(
            arquivo,
            to_encoding=to_encoding,
            from_encoding=from_encoding,
            backup=not no_backup,
        )
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    _render_from_ctx(
        ctx,
        [
            {
                "file": str(arquivo),
                "from": src,
                "to": dst,
                "backup": str(bak) if bak else "",
            }
        ],
        columns=["file", "from", "to", "backup"],
        title=f"edit-prw save {arquivo.name}",
    )


@edit_prw_app.command("stage")
def edit_prw_stage(
    ctx: typer.Context,  # noqa: ARG001 -- typer commands declaram ctx por convencao mesmo quando nao consomem o estado
    arquivo: Annotated[
        Path, typer.Argument(help="Fonte .prw cp1252 a converter para UTF-8 antes de editar.")
    ],
    no_backup: Annotated[
        bool,
        typer.Option("--no-backup", help="Nao criar arquivo .bak com bytes originais."),
    ] = False,
) -> None:
    """Converte .prw cp1252 → utf-8 ANTES de editar com Claude/IDE moderna.

    Workflow seguro pra editar .prw com Claude Code (Read/Edit tools são
    UTF-8 only — leem bytes cp1252 como '?' e perdem acentos não-editados):

      plugadvpl edit-prw stage FOO.PRW   # cp1252 -> utf-8 (com .bak)
      # ... agora Claude pode Read/Edit normalmente, acentos preservados
      plugadvpl edit-prw commit FOO.PRW  # utf-8 -> cp1252 (volta ao original)
    """
    from plugadvpl.edit_prw import convert_and_save

    if not arquivo.exists():
        typer.secho(f"Arquivo nao encontrado: {arquivo}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    try:
        _src, _dst, bak = convert_and_save(
            arquivo,
            from_encoding="cp1252",
            to_encoding="utf-8",
            backup=not no_backup,
        )
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(
        f"\n✓ Staged: {arquivo} agora em utf-8 (acentos preservados)\n"
        f"  Backup cp1252 original: {bak}\n"
        f"  Edite normalmente com Read/Edit do Claude. Depois:\n"
        f"    plugadvpl edit-prw commit {arquivo.name}",
        fg=typer.colors.GREEN,
    )


@edit_prw_app.command("commit")
def edit_prw_commit(
    ctx: typer.Context,  # noqa: ARG001 -- typer convencao
    arquivo: Annotated[
        Path,
        typer.Argument(help="Fonte .prw em UTF-8 (após stage) a converter de volta para cp1252."),
    ],
    no_backup: Annotated[
        bool,
        typer.Option("--no-backup", help="Nao criar arquivo .bak."),
    ] = False,
) -> None:
    """Converte .prw utf-8 → cp1252 DEPOIS de editar (reverso de stage).

    Reverte a conversão temporária feita por `stage`. O arquivo volta ao
    encoding cp1252 esperado pelo compilador appserver legado, com acentos
    novos (digitados durante a edição) corretamente convertidos pra bytes
    cp1252.
    """
    from plugadvpl.edit_prw import convert_and_save

    if not arquivo.exists():
        typer.secho(f"Arquivo nao encontrado: {arquivo}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    try:
        _src, _dst, bak = convert_and_save(
            arquivo,
            from_encoding="utf-8",
            to_encoding="cp1252",
            backup=not no_backup,
        )
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(
        f"\n✓ Committed: {arquivo} volta em cp1252 (pronto pra compilar)\n"
        f"  Backup utf-8 intermediário: {bak}",
        fg=typer.colors.GREEN,
    )


@edit_prw_app.command("clean")
def edit_prw_clean(
    ctx: typer.Context,  # noqa: ARG001 -- typer convencao
    target: Annotated[
        Path,
        typer.Argument(help="Pasta (varre recursivamente) OU arquivo .prw específico."),
    ] = Path(),
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Pula confirmação antes de remover."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Lista o que removeria sem deletar."),
    ] = False,
) -> None:
    """Remove arquivos .bak deixados por stage/commit anteriores.

    v0.8.11 fix bug 4: ciclo stage→edit→commit cria 2 .bak por fonte e
    eles se acumulam em pastas com muitas edições. Este comando faz a
    limpeza em lote (dry-run por padrão se você quiser ver antes).

    Procura: <fonte>.prw.bak, <fonte>.prx.bak, <fonte>.tlpp.bak.
    """
    if not target.exists():
        typer.secho(f"Path não existe: {target}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    baks: list[Path]
    if target.is_file():
        # Modo single-file: limpa o .bak do arquivo apontado (se houver)
        bak = target.with_suffix(target.suffix + ".bak")
        baks = [bak] if bak.is_file() else []
    else:
        baks = sorted(
            p
            for p in target.rglob("*.bak")
            if p.is_file()
            and any(
                p.name.lower().endswith(ext + ".bak")
                for ext in (".prw", ".prx", ".tlpp", ".tlpp.ch", ".ch")
            )
        )

    if not baks:
        typer.secho(f"Nenhum .bak encontrado em {target}.", fg=typer.colors.GREEN)
        return

    total_bytes = sum(p.stat().st_size for p in baks)
    typer.echo("\n=== edit-prw clean ===")
    typer.echo(f"  candidatos: {len(baks)} arquivo(s), {total_bytes:,} bytes")
    for p in baks[:20]:
        typer.echo(f"    {p}")
    if len(baks) > 20:  # noqa: PLR2004 -- cap de display; mostra primeiros 20 + sumario
        typer.echo(f"    ... ({len(baks) - 20} a mais)")

    if dry_run:
        typer.secho("\n(dry-run — nada foi removido)", fg=typer.colors.YELLOW)
        return

    if not yes and not typer.confirm(f"\nRemover {len(baks)} .bak(s)?", default=False):
        typer.echo("Cancelado.")
        raise typer.Exit(code=0)

    removed = 0
    failed: list[tuple[Path, str]] = []
    for p in baks:
        try:
            p.unlink()
            removed += 1
        except OSError as exc:
            failed.append((p, str(exc)))

    typer.secho(f"\n✓ Removidos {removed}/{len(baks)} .bak(s).", fg=typer.colors.GREEN)
    if failed:
        typer.secho(f"  Falhas: {len(failed)}", fg=typer.colors.YELLOW)
        for p, err in failed[:10]:
            typer.echo(f"    {p}: {err}")


# ---------------------------------------------------------------------------
# migrate-tlpp (v0.18.0): migrador deterministico ADVPL classico -> TLPP
# ---------------------------------------------------------------------------


migrate_tlpp_app = typer.Typer(
    name="migrate-tlpp",
    help="Migrador determinístico .prw → .tlpp (pipeline ts-migrate-style).",
    no_args_is_help=True,
)
app.add_typer(migrate_tlpp_app, name="migrate-tlpp")


def _parse_tlpp_version(s: str | None) -> tuple[int, int, int]:
    """Parseia '20.3.2' -> (20, 3, 2). None/'' -> (0, 0, 0)."""
    if not s:
        return (0, 0, 0)
    parts = s.split(".")
    nums = [int(p) for p in parts[:3]]
    while len(nums) < 3:  # noqa: PLR2004 -- semver tem 3 niveis (major.minor.patch)
        nums.append(0)
    return (nums[0], nums[1], nums[2])


@migrate_tlpp_app.command("init")
def migrate_tlpp_init(
    ctx: typer.Context,
    pasta: Annotated[
        Path,
        typer.Argument(help="Pasta a analisar (recursivo). Default: root do projeto."),
    ] = Path(),
    enable_idioms: Annotated[
        bool,
        typer.Option("--idioms", help="Inclui recipes IDIOMS na análise."),
    ] = False,
    tlpp_version: Annotated[
        str | None,
        typer.Option("--tlpp-version", help="Versão AppServer alvo (ex: 20.3.2)."),
    ] = None,
) -> None:
    """Analisa projeto e lista candidatos a migração sem tocar em nada.

    Output (table ou JSON via --format): arquivo, candidato, recipes que
    aplicariam, blockers de lint (SEC-001/SEC-004), impact (count callers
    externos via DB).
    """
    from plugadvpl.migrate_tlpp import MigrationPlan, dry_run

    root: Path = ctx.obj["root"]
    target_dir = pasta if pasta.is_absolute() else root / pasta
    if not target_dir.exists():
        typer.secho(f"Pasta não encontrada: {target_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    parsed_version = _parse_tlpp_version(tlpp_version)
    rows: list[dict[str, object]] = []
    for prw_file in sorted(target_dir.rglob("*.prw")):
        plan = MigrationPlan(
            file_path=prw_file,
            project_root=root,
            enable_idioms=enable_idioms,
            tlpp_version=parsed_version,
            no_impact_check=True,  # init nao escreve, OK skipar
            allow_dirty=True,
        )
        report = dry_run(plan)
        counts = report.counts()
        rows.append(
            {
                "arquivo": str(prw_file.relative_to(root)),
                "recipes_ok": counts.get("ok", 0),
                "nochange": counts.get("nochange", 0),
                "needs_review": counts.get("needs-review", 0),
                "todos": len(report.all_todos()),
            }
        )

    fmt = ctx.obj.get("format", "table") if ctx.obj else "table"
    if fmt == "json":
        import json as _json

        typer.echo(
            _json.dumps(
                {"total": len(rows), "rows": rows},
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    _render_from_ctx(
        ctx,
        rows,
        columns=["arquivo", "recipes_ok", "nochange", "needs_review", "todos"],
        title=f"Candidatos a migração em {target_dir.relative_to(root) if target_dir.is_relative_to(root) else target_dir}",
        next_steps=[
            "plugadvpl migrate-tlpp rename <arquivo>  # so rename + encoding",
            "plugadvpl migrate-tlpp recipes <arquivo>  # diff completo",
        ],
    )


@migrate_tlpp_app.command("rename")
def migrate_tlpp_rename(
    ctx: typer.Context,
    arquivo: Annotated[Path, typer.Argument(help="Arquivo .prw a renomear.")],
    write: Annotated[
        bool,
        typer.Option("--write", help="Aplica rename (default: só diff)."),
    ] = False,
    validate: Annotated[
        bool,
        typer.Option("--validate", help="Após write, valida via compile."),
    ] = False,
    allow_dirty: Annotated[
        bool,
        typer.Option("--allow-dirty", help="Permite working tree dirty."),
    ] = False,
) -> None:
    """Renomeia .prw → .tlpp + converte encoding cp1252 → utf-8.

    Subset conservador: aplica APENAS recipes ``convert-encoding`` e
    ``rename-extension`` (canonical order 1-2). Pra recipes completos
    use ``migrate-tlpp recipes``.
    """
    from plugadvpl.migrate_tlpp import MigrationPlan, apply, dry_run

    root: Path = ctx.obj["root"]
    target_file = arquivo if arquivo.is_absolute() else root / arquivo
    plan = MigrationPlan(
        file_path=target_file,
        project_root=root,
        no_impact_check=True,  # rename nao precisa DB
        allow_dirty=allow_dirty,
        selected_recipes=("convert-encoding", "rename-extension"),
    )
    report = apply(plan, validate=validate) if write else dry_run(plan)
    if report.final_content is not None and not write:
        from plugadvpl.migrate_tlpp_diff import unified_diff_text

        diff = unified_diff_text(
            target_file.read_text(encoding="cp1252", errors="replace"),
            report.final_content,
            str(target_file),
            str(target_file.with_suffix(".tlpp")),
        )
        typer.echo(diff)
    counts = report.counts()
    typer.secho(
        f"rename: ok={counts.get('ok', 0)} nochange={counts.get('nochange', 0)}",
        fg=typer.colors.GREEN,
        err=True,
    )


@migrate_tlpp_app.command("recipes")
def migrate_tlpp_recipes(
    ctx: typer.Context,
    arquivo: Annotated[Path, typer.Argument(help="Arquivo .prw a migrar.")],
    write: Annotated[
        bool,
        typer.Option("--write", help="Aplica recipes ao FS (default: só diff)."),
    ] = False,
    enable_idioms: Annotated[
        bool,
        typer.Option("--idioms", help="Inclui recipes IDIOMS (opt-in)."),
    ] = False,
    tlpp_version: Annotated[
        str | None,
        typer.Option("--tlpp-version", help="Versão AppServer alvo (ex: 20.3.2)."),
    ] = None,
    validate: Annotated[
        bool,
        typer.Option("--validate", help="Após write, valida via compile."),
    ] = False,
    allow_dirty: Annotated[
        bool,
        typer.Option("--allow-dirty", help="Permite working tree dirty."),
    ] = False,
    no_impact_check: Annotated[
        bool,
        typer.Option("--no-impact-check", help="Pula gate de DB ingest."),
    ] = False,
    recipe: Annotated[
        list[str] | None,
        typer.Option("--recipe", "-r", help="Recipe ID (repetível)."),
    ] = None,
) -> None:
    """Aplica recipes de transformação ADVPL → TLPP.

    Default: diff-only. ``--write`` aplica + opcionalmente ``--validate``.
    """
    from plugadvpl.migrate_tlpp import MigrationPlan, apply, dry_run

    root: Path = ctx.obj["root"]
    target_file = arquivo if arquivo.is_absolute() else root / arquivo
    parsed_version = _parse_tlpp_version(tlpp_version)
    plan = MigrationPlan(
        file_path=target_file,
        project_root=root,
        enable_idioms=enable_idioms,
        tlpp_version=parsed_version,
        allow_dirty=allow_dirty,
        no_impact_check=no_impact_check,
        selected_recipes=tuple(recipe or ()),
    )
    report = apply(plan, validate=validate) if write else dry_run(plan)
    if report.final_content is not None and not write:
        from plugadvpl.migrate_tlpp_diff import unified_diff_text

        before = target_file.read_text(encoding="cp1252", errors="replace")
        diff = unified_diff_text(
            before,
            report.final_content,
            str(target_file),
            str(target_file.with_suffix(".tlpp")),
        )
        typer.echo(diff)

    # Sumario categorizado
    counts = report.counts()
    fmt = ctx.obj.get("format", "table") if ctx.obj else "table"
    if fmt == "json":
        import json as _json

        rel_arquivo = (
            str(target_file.relative_to(root))
            if target_file.is_relative_to(root)
            else str(target_file)
        )
        typer.echo(
            _json.dumps(
                {
                    "arquivo": rel_arquivo,
                    "recipes": [
                        {"id": r.recipe_id, "status": r.status, "message": r.message}
                        for r in report.recipe_results
                    ],
                    "counts": counts,
                    "todos": report.all_todos(),
                    "rollback_used": report.rollback_used,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        typer.secho(
            f"recipes: ok={counts.get('ok', 0)} nochange={counts.get('nochange', 0)} "
            f"needs-review={counts.get('needs-review', 0)} error={counts.get('error', 0)}",
            fg=typer.colors.GREEN if not report.has_errors() else typer.colors.RED,
            err=True,
        )
        if report.rollback_used != "none":
            typer.secho(
                f"⚠ rollback usado: {report.rollback_used}",
                fg=typer.colors.YELLOW,
                err=True,
            )


_TODO_MARKER_RE = re.compile(
    r"//\s*@plugadvpl-todo:(\S+)\s*(.*?)$",
    re.MULTILINE,
)


@migrate_tlpp_app.command("todos")
def migrate_tlpp_todos(
    ctx: typer.Context,
    pasta: Annotated[
        Path,
        typer.Argument(help="Pasta a varrer (recursivo). Default: root."),
    ] = Path(),
) -> None:
    """Lista débitos ``@plugadvpl-todo`` pendentes em arquivos .tlpp."""
    root: Path = ctx.obj["root"]
    target_dir = pasta if pasta.is_absolute() else root / pasta
    rows: list[dict[str, object]] = []
    for tlpp_file in sorted(target_dir.rglob("*.tlpp")):
        try:
            content = tlpp_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            m = _TODO_MARKER_RE.search(line)
            if m:
                rows.append(
                    {
                        "arquivo": str(tlpp_file.relative_to(root))
                        if tlpp_file.is_relative_to(root)
                        else str(tlpp_file),
                        "linha": line_no,
                        "recipe": m.group(1),
                        "mensagem": m.group(2).strip(),
                    }
                )
    if not rows:
        typer.secho(
            "Nenhum débito @plugadvpl-todo encontrado.",
            fg=typer.colors.GREEN,
        )
        return
    _render_from_ctx(
        ctx,
        rows,
        columns=["arquivo", "linha", "recipe", "mensagem"],
        title=(
            f"Débitos @plugadvpl-todo em "
            f"{target_dir.relative_to(root) if target_dir.is_relative_to(root) else target_dir}"
        ),
    )


# ---------------------------------------------------------------------------
# compile (v0.8.0 Fase 1): wrapper sobre advpls
# ---------------------------------------------------------------------------


compile_app = typer.Typer(
    name="compile",
    help="Compila fontes ADVPL via advpls (modos appre local + cli full).",
    # NAO usar no_args_is_help=True junto com invoke_without_command=True
    # — typer mostra help antes do callback, quebrando o teste que espera
    # exit 2 + "nenhum fonte informado".
    invoke_without_command=True,
)
app.add_typer(compile_app, name="compile")


@compile_app.callback()
def compile_callback(  # noqa: PLR0911, PLR0912, PLR0915 -- typer command dispatcher: --doctor / --install / --list-servers / --add-server / --remove-server / --import-tds / --probe / --set-credentials / --clear-credentials / --explain-config / --set-restart-cmd / --mark-prod / --no-prod / --all-envs ; cada um e um handler curto, mas a soma estoura limits. Split viraria 14 sub-commands typer com duplicacao de options globais
    ctx: typer.Context,
    files: Annotated[list[Path] | None, typer.Argument(help="Fontes a compilar.")] = None,
    mode: Annotated[str, typer.Option("--mode", help="auto|appre|cli")] = "auto",
    changed_since: Annotated[
        str | None, typer.Option("--changed-since", help="Git ref para git diff")
    ] = None,
    no_warnings: Annotated[bool, typer.Option("--no-warnings", help="Filtra warnings")] = False,
    timeout: Annotated[
        int, typer.Option("--timeout", help="Timeout do subprocess em segundos")
    ] = 120,
    no_security_warning: Annotated[
        bool, typer.Option("--no-security-warning", help="Suprime warning host remoto")
    ] = False,
    includes: Annotated[
        list[Path],
        typer.Option(
            "--includes",
            "-I",
            help="Override includes (repita: --includes A --includes B)",
        ),
    ] = [],  # noqa: B006 -- typer Annotated nao aceita default_factory; lista vazia e safe pois nunca mutada
    init_config: Annotated[
        bool, typer.Option("--init-config", help="Gera template runtime.toml")
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Sobrescreve config existente")] = False,
    doctor: Annotated[
        bool,
        typer.Option(
            "--doctor",
            help="Pre-flight check do ambiente (advpls + includes + AppServer)",
        ),
    ] = False,
    install_advpls: Annotated[
        bool,
        typer.Option(
            "--install-advpls",
            help="Instala advpls em ~/.plugadvpl/advpls/ (interativo: copia ou baixa)",
        ),
    ] = False,
    list_servers_flag: Annotated[
        bool,
        typer.Option(
            "--list-servers", help="Lista AppServers cadastrados (~/.plugadvpl/servers.json)"
        ),
    ] = False,
    add_server_flag: Annotated[
        bool,
        typer.Option("--add-server", help="Cadastra novo AppServer (interativo)"),
    ] = False,
    remove_server_name: Annotated[
        str,
        typer.Option("--remove-server", help="Remove server cadastrado por nome"),
    ] = "",
    import_tds_servers: Annotated[
        bool,
        typer.Option(
            "--import-tds-servers", help="Importa servers do TDS-VSCode (~/.totvsls/servers.json)"
        ),
    ] = False,
    use_server: Annotated[
        str,
        typer.Option(
            "--use-server", help="Compila usando server do registry (sobrescreve [appserver])"
        ),
    ] = "",
    probe_appserver: Annotated[
        str,
        typer.Option(
            "--probe-appserver",
            help="Descobre build do AppServer via protheus.log (path do .log ou raiz Protheus)",
        ),
    ] = "",
    set_credentials_for: Annotated[
        str,
        typer.Option(
            "--set-credentials",
            help="Salva user+pass do server no cofre do OS (Win Credential Manager / macOS Keychain / Linux Secret Service)",
        ),
    ] = "",
    set_restart_cmd: Annotated[
        str,
        typer.Option(
            "--set-restart-cmd",
            help="Nome do server pra configurar restart_cmd (use junto com --cmd)",
        ),
    ] = "",
    cmd_value: Annotated[
        str,
        typer.Option(
            "--cmd",
            help='Comando shell pro restart (use com --set-restart-cmd). Ex: "cmd.exe /c restart.bat"',
        ),
    ] = "",
    mark_prod: Annotated[
        str,
        typer.Option(
            "--mark-prod",
            help="Marca server como produção (tq vai exigir --confirm-prod). Use --no-prod pra desfazer",
        ),
    ] = "",
    no_prod: Annotated[
        str,
        typer.Option(
            "--no-prod",
            help="Remove flag is_prod do server (desfaz --mark-prod)",
        ),
    ] = "",
    clear_credentials_for: Annotated[
        str,
        typer.Option(
            "--clear-credentials",
            help="Remove credenciais do server do cofre do OS",
        ),
    ] = "",
    explain_config: Annotated[
        bool,
        typer.Option(
            "--explain-config",
            help="Mostra de onde vem cada campo (flag/runtime.toml/registry/keyring/env/auto-detect)",
        ),
    ] = False,
    use_environment: Annotated[
        str,
        typer.Option("--use-environment", help="Override do environment do server (opcional)"),
    ] = "",
    all_envs: Annotated[
        bool,
        typer.Option(
            "--all-envs",
            help="Compila pra TODOS os environments do --use-server (RPO sync entre envs)",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Pula confirmações interativas (use com cuidado em --install-advpls)",
        ),
    ] = False,
) -> None:
    """Compila fontes ADVPL via wrapper sobre advpls."""
    if ctx.invoked_subcommand is not None:
        return

    obj = ctx.obj
    root: Path = obj["root"]

    if init_config:
        _handle_init_config(root, force)
        return

    if doctor:
        _handle_doctor(ctx, root)
        return

    if install_advpls:
        _handle_install_advpls(yes=yes)
        return

    if list_servers_flag:
        _handle_list_servers(ctx)
        return

    if add_server_flag:
        _handle_add_server()
        return

    if remove_server_name:
        _handle_remove_server(remove_server_name)
        return

    if import_tds_servers:
        _handle_import_tds_servers(yes=yes)
        return

    if probe_appserver:
        _handle_probe_appserver(probe_appserver)
        return

    if set_credentials_for:
        _handle_set_credentials(set_credentials_for)
        return

    if set_restart_cmd:
        if not cmd_value:
            typer.secho(
                "--set-restart-cmd requer --cmd '<comando>'",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        _handle_set_restart_cmd(set_restart_cmd, cmd_value)
        return

    if mark_prod:
        _handle_set_is_prod(mark_prod, True)
        return

    if no_prod:
        _handle_set_is_prod(no_prod, False)
        return

    if clear_credentials_for:
        _handle_clear_credentials(clear_credentials_for)
        return

    if explain_config:
        _handle_explain_config(ctx, root, use_server, use_environment)
        return

    if not files:
        typer.secho("nenhum fonte informado", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    # v0.8.8 fix bug 1: typer com positional variadic (list[Path]) consome
    # flags posteriores como elementos do `files`. Resultado catastrófico:
    # `compile FOO.PRW --mode cli --includes <dir>` faz mode/includes
    # virarem None silenciosamente e cai em --mode auto → appre sem includes.
    # Detecta isso e erra com mensagem útil ANTES de chamar o compile.
    suspicious_flags = {
        "--mode",
        "--includes",
        "-I",
        "--changed-since",
        "--no-warnings",
        "--timeout",
        "--no-security-warning",
        "--use-server",
        "--use-environment",
        "--all-envs",
        "--format",
        "-f",
        "--init-config",
        "--force",
        "--doctor",
        "--install-advpls",
        "--list-servers",
        "--add-server",
        "--remove-server",
        "--import-tds-servers",
        "--yes",
        "-y",
        "--probe-appserver",
        "--set-credentials",
        "--clear-credentials",
        "--explain-config",
        "--set-restart-cmd",
        "--cmd",
        "--mark-prod",
        "--no-prod",
    }
    misplaced = [str(f) for f in files if str(f) in suspicious_flags]
    if misplaced:
        typer.secho(
            f"\nERRO: flag(s) {misplaced} apareceu(ram) APÓS o(s) nome(s) "
            "de arquivo.\n"
            "  Typer/Click com positional variadic consome flags como nomes "
            "de arquivo (silenciosamente).\n"
            "  Convenção UNIX: flags `--xxx` SEMPRE antes do positional.\n"
            "\n"
            "  ❌ ERRADO: plugadvpl compile FOO.PRW --mode cli --includes <dir>\n"
            "  ✓ CERTO:  plugadvpl compile --mode cli --includes <dir> FOO.PRW",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    from plugadvpl.compile import CompileRequest
    from plugadvpl.compile import run as compile_run
    from plugadvpl.runtime_config import RuntimeConfigError
    from plugadvpl.runtime_config import load as load_runtime_config

    try:
        runtime_cfg = load_runtime_config(root)
    except RuntimeConfigError as exc:
        typer.secho(f"runtime config error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    # v0.13.2: --all-envs exige --use-server e é incompatível com --use-environment
    if all_envs:
        if not use_server:
            typer.secho(
                "--all-envs requer --use-server <nome>",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        if use_environment:
            typer.secho(
                "--all-envs e --use-environment são mutuamente exclusivos",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)

    # --use-server: sobrescreve [appserver] do runtime.toml com server do registry global
    srv = None
    if use_server:
        from plugadvpl.compile_servers import get_server

        srv = get_server(use_server)
        if srv is None:
            typer.secho(
                f"server '{use_server}' não cadastrado. Liste com: "
                f"plugadvpl compile --list-servers",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        if not all_envs:
            runtime_cfg = _apply_server_override(
                runtime_cfg,
                srv,
                use_environment,
                requested_mode=mode,
            )

    if mode == "cli" and runtime_cfg is None and not all_envs:
        typer.secho(
            f"runtime.toml required for cli mode at {root}/.plugadvpl/runtime.toml. "
            "Run: plugadvpl compile --init-config OU passe --use-server <nome>",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    request = CompileRequest(
        files=files,
        mode=cast("Literal['auto', 'appre', 'cli']", mode),
        no_warnings=no_warnings,
        timeout_seconds=timeout,
        no_security_warning=no_security_warning,
        includes_override=includes if includes else None,
        changed_since=changed_since,
    )

    # --all-envs: itera os environments cadastrados no server e roda compile
    # por env, anotando linha com a coluna "env". Exit code = max dos envs.
    if all_envs:
        assert srv is not None
        if len(srv.environments) < 2:  # noqa: PLR2004 -- --all-envs so faz sentido com 2+ envs; com 1 degenera pra compile unico
            typer.secho(
                f"AVISO: server '{srv.name}' só tem {len(srv.environments)} env "
                f"({srv.environments}) — --all-envs degenera pra compile único.",
                fg=typer.colors.YELLOW,
            )
        all_rows: list[dict[str, object]] = []
        worst_exit = 0
        mode_used_first = "?"
        next_steps: list[str] = []
        for env_name in srv.environments:
            try:
                env_runtime_cfg = _apply_server_override(
                    runtime_cfg,
                    srv,
                    env_name,
                    requested_mode=mode,
                )
            except typer.Exit:
                # _apply_server_override já printou erro estruturado
                raise
            try:
                env_result = compile_run(request, runtime_cfg=env_runtime_cfg, root=root)
            except KeyboardInterrupt as exc:
                typer.secho("interrupted", fg=typer.colors.YELLOW, err=True)
                raise typer.Exit(code=130) from exc
            if mode_used_first == "?":
                mode_used_first = str(env_result.summary.get("mode_used", "?"))
                next_steps = list(env_result.next_steps)
            for row in env_result.rows:
                annotated = dict(row)
                annotated["env"] = env_name
                all_rows.append(annotated)
            worst_exit = max(worst_exit, env_result.exit_code)

        _render_from_ctx(
            ctx,
            all_rows,
            columns=["env", "arquivo", "ok", "mode", "duration_ms", "exit_code"],
            title=f"compile --all-envs ({mode_used_first}) — {len(srv.environments)} envs",
            next_steps=next_steps,
        )
        raise typer.Exit(code=worst_exit)

    try:
        result = compile_run(request, runtime_cfg=runtime_cfg, root=root)
    except KeyboardInterrupt as exc:
        typer.secho("interrupted", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=130) from exc

    _render_from_ctx(
        ctx,
        result.rows,
        columns=["arquivo", "ok", "mode", "duration_ms", "exit_code"],
        title=f"compile ({result.summary.get('mode_used', '?')})",
        next_steps=result.next_steps,
    )

    raise typer.Exit(code=result.exit_code)


@app.command("tq")
def tq_cmd(
    ctx: typer.Context,
    use_server: Annotated[
        str,
        typer.Option("--use-server", help="Server do registry (~/.plugadvpl/servers.json)"),
    ] = "",
    port_override: Annotated[
        int,
        typer.Option(
            "--port",
            help="Override da porta pro healthcheck (default usa server.port; útil quando REST está em porta diferente do TCP do advpls)",
        ),
    ] = 0,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Timeout do healthcheck em segundos (default 60)"),
    ] = 60,
    no_healthcheck: Annotated[
        bool,
        typer.Option("--no-healthcheck", help="Só executa restart_cmd, pula healthcheck"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Mostra o que faria, não executa"),
    ] = False,
    confirm_prod: Annotated[
        bool,
        typer.Option(
            "--confirm-prod",
            help="Confirma intenção de restartar AppServer marcado como PROD (via --mark-prod no compile)",
        ),
    ] = False,
) -> None:
    """Restart do AppServer + healthcheck (Troca Quente MVP local)."""
    from dataclasses import asdict

    from plugadvpl.compile_servers import get_server
    from plugadvpl.tq import run_tq

    if not use_server:
        typer.secho("--use-server obrigatório", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    srv = get_server(use_server)
    if srv is None:
        typer.secho(
            f"Server '{use_server}' não cadastrado.\n  Liste: plugadvpl compile --list-servers",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if not srv.restart_cmd:
        typer.secho(
            f"Server '{use_server}' sem restart_cmd. Configure:\n"
            f"  plugadvpl compile --set-restart-cmd {use_server} --cmd '<comando>'",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if srv.is_prod and not confirm_prod and not dry_run:
        typer.secho(
            f"Server '{use_server}' está marcado como PROD.\n"
            f"  Pra prosseguir mesmo assim: plugadvpl tq --use-server {use_server} --confirm-prod\n"
            f"  Pra desmarcar: plugadvpl compile --no-prod {use_server}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    hc_port = port_override if port_override > 0 else srv.port

    if dry_run:
        rows = [
            {
                "server": srv.name,
                "host": f"{srv.host}:{hc_port}",
                "restart_cmd": srv.restart_cmd,
                "healthcheck": "skipped" if no_healthcheck else f"GET / (timeout {timeout}s)",
                "dry_run": True,
            }
        ]
        _render_from_ctx(
            ctx,
            rows,
            columns=["server", "host", "restart_cmd", "healthcheck", "dry_run"],
            title=f"tq --dry-run ({srv.name})",
            next_steps=[f"plugadvpl tq --use-server {srv.name}  # roda de verdade"],
        )
        raise typer.Exit(code=0)

    result = run_tq(
        srv,
        timeout_s=timeout,
        no_healthcheck=no_healthcheck,
        port_override=port_override,
    )
    rows = [asdict(result)]
    _render_from_ctx(
        ctx,
        rows,
        columns=[
            "ok",
            "server_name",
            "restart_exit_code",
            "restart_duration_ms",
            "healthcheck_status",
            "healthcheck_attempts",
            "total_duration_ms",
            "error",
        ],
        title=f"tq ({srv.name})",
        next_steps=_tq_hints(result, srv, hc_port, timeout),
    )
    raise typer.Exit(code=0 if result.ok else 1)


def _tq_hints(result: TqResult, srv: Server, hc_port: int, timeout_s: int) -> list[str]:
    """Sugestões acionáveis quando tq falha. Vazio quando result.ok."""
    if result.ok:
        return []
    if result.healthcheck_status == "timeout":
        return [
            f"healthcheck timeout em {srv.host}:{hc_port} após {timeout_s}s",
            "verifique console.log do AppServer — build pode estar demorando ou erro de boot",
            f"--port {hc_port} aponta pra porta REST correta? (server.port={srv.port})",
            f"build lento? aumente --timeout {timeout_s} → --timeout {timeout_s * 2}",
        ]
    if result.restart_exit_code not in (0, -1):
        return [
            "restart_cmd falhou — rode o comando manualmente pra ver o erro completo:",
            f"  {srv.restart_cmd}",
            "verifique permissão de execução e PATH (cmd absoluto evita ambiguidade)",
        ]
    return []


def _handle_list_servers(ctx: typer.Context) -> None:
    """Lista servers cadastrados em ~/.plugadvpl/servers.json."""
    from plugadvpl.compile_servers import default_server, list_servers, registry_path

    servers = list_servers()
    if not servers:
        typer.secho(
            f"Nenhum server cadastrado em {registry_path()}.\n"
            "  --add-server: cadastra interativo\n"
            "  --import-tds-servers: importa do TDS-VSCode (se já usa)",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=0)

    default = default_server()
    default_name = default.name if default else ""
    rows: list[dict[str, object]] = []
    for s in servers:
        flags = []
        if s.name == default_name:
            flags.append("*")
        if s.is_prod:
            flags.append("PROD")
        suffix = (" " + " ".join(flags)) if flags else ""
        rows.append(
            {
                "name": s.name + suffix,
                "host": s.host,
                "port": s.port,
                "build": s.build or "(MISSING)",
                "envs": ",".join(s.environments) or "(none)",
                "default_env": s.default_environment,
                "user_env": s.user_env,
                "includes_count": len(s.includes),
            }
        )
    _render_from_ctx(
        ctx,
        rows,
        columns=[
            "name",
            "host",
            "port",
            "build",
            "envs",
            "default_env",
            "user_env",
            "includes_count",
        ],
        title="AppServers cadastrados (* = default, PROD = is_prod)",
        next_steps=[f"plugadvpl compile --use-server {servers[0].name} <fonte>"],
    )


def _handle_add_server() -> None:
    """Cadastra novo server interativo em ~/.plugadvpl/servers.json."""
    from plugadvpl.compile_servers import Server, add_server, registry_path

    typer.echo("\n=== Cadastro de novo AppServer ===")
    typer.echo(f"Será gravado em: {registry_path()}\n")

    name = typer.prompt("Nome (ex: 'dev-local', 'hml-cliente')").strip()
    if not name:
        typer.secho("Nome obrigatório.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    host = typer.prompt("Host", default="127.0.0.1").strip()
    port = typer.prompt("Port", type=int, default=1234)
    secure = typer.confirm("HTTPS/TLS?", default=False)
    build = typer.prompt("Build (ex: 7.00.240223P)").strip()
    envs_raw = typer.prompt("Environments (separados por vírgula, ex: 'P2510,TEST,PROD')").strip()
    envs = [e.strip() for e in envs_raw.split(",") if e.strip()]
    if not envs:
        typer.secho("Pelo menos 1 environment é obrigatório.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    default_env = typer.prompt("Default environment", default=envs[0]).strip()
    if default_env not in envs:
        typer.secho(
            f"'{default_env}' não está na lista {envs}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    user_env = typer.prompt("Nome da env var de USUÁRIO", default="PROTHEUS_USER").strip()
    password_env = typer.prompt(
        "Nome da env var de SENHA (NUNCA valor literal!)",
        default="PROTHEUS_PASS",
    ).strip()
    notes = typer.prompt("Notas (opcional)", default="").strip()
    make_default = typer.confirm(
        "Marcar como server DEFAULT do registry?",
        default=False,
    )

    server = Server(
        name=name,
        host=host,
        port=port,
        build=build,
        environments=envs,
        default_environment=default_env,
        user_env=user_env,
        password_env=password_env,
        secure=secure,
        notes=notes,
    )
    add_server(server, make_default=make_default)
    typer.secho(
        f"\n✓ Cadastrado: '{name}' em {registry_path()}",
        fg=typer.colors.GREEN,
    )
    typer.echo(
        f"\nPara compilar usando este server:\n"
        f"  export {user_env}=<usuário>\n"
        f"  export {password_env}=<senha>\n"
        f"  plugadvpl compile --use-server {name} --mode cli <fonte.prw>"
    )


def _handle_remove_server(name: str) -> None:
    """Remove server do registry."""
    from plugadvpl.compile_servers import registry_path, remove_server

    if remove_server(name):
        typer.secho(f"✓ Removido: '{name}' de {registry_path()}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"Server '{name}' não encontrado.", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1)


def _handle_import_tds_servers(yes: bool) -> None:
    """Importa servers do TDS-VSCode (~/.totvsls/servers.json)."""
    from plugadvpl.compile_servers import (
        add_server,
        import_from_tds_vscode,
        tds_vscode_servers_path,
    )

    path = tds_vscode_servers_path()
    if not path.is_file():
        typer.secho(
            f"TDS-VSCode servers.json não encontrado em {path}.\n"
            f"Você usa TDS-VSCode? Se sim, cadastre ao menos 1 server lá primeiro.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)

    imported = import_from_tds_vscode()
    if not imported:
        typer.secho(
            f"Nenhum server encontrado em {path}.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=0)

    typer.echo(f"\n=== Servers em {path} ===")
    for s in imported:
        envs = ",".join(s.environments) or "(none)"
        typer.echo(f"  {s.name} — {s.host}:{s.port} build={s.build} envs={envs}")

    if not yes and not typer.confirm(
        f"\nImportar {len(imported)} server(s) pra registry plugadvpl?",
        default=True,
    ):
        typer.echo("Cancelado.")
        raise typer.Exit(code=0)

    for s in imported:
        add_server(s)
    typer.secho(
        f"\n✓ Importados {len(imported)} server(s). Veja com: plugadvpl compile --list-servers",
        fg=typer.colors.GREEN,
    )


def _handle_probe_appserver(target_str: str) -> None:
    """Descobre build do AppServer. Auto-detecta entre 2 modos.

    v0.8.11 (log): parseia protheus.log local.
    v0.8.12 (network): invoca ``advpls cli action=validate`` — mesmo
        mecanismo que o TDS-VSCode usa (LSP $totvsserver/validation).
    """
    from plugadvpl.compile_probe import is_host_port

    if is_host_port(target_str):
        host, _, port_str = target_str.rpartition(":")
        _probe_via_network(host=host, port=int(port_str))
        return

    target = Path(target_str)
    if not target.exists():
        typer.secho(
            f"Path não existe e não parece host:port: {target_str}\n"
            f"\n"
            f"  Use UM de:\n"
            f"    plugadvpl compile --probe-appserver 127.0.0.1:1234   (network)\n"
            f"    plugadvpl compile --probe-appserver D:/TOTVS/protheus  (log)\n",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    _probe_via_log(target)


def _probe_via_network(host: str, port: int) -> None:
    """Network probe via ``advpls cli action=validate`` (v0.8.12)."""
    from plugadvpl.compile_doctor import _detect_advpls
    from plugadvpl.compile_probe import probe_appserver_network

    typer.echo("\n=== probe-appserver (modo network) ===")
    typer.echo(f"  alvo: {host}:{port}\n")

    typer.echo("  [1/3] Localizando binário advpls...")
    binary = _detect_advpls()
    if binary is None:
        typer.secho(
            "        ✗ advpls não encontrado.\n"
            "        Instale com: plugadvpl compile --install-advpls",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    typer.echo(f"        ✓ {binary}\n")

    typer.echo("  [2/3] Gerando INI [validate] em tempdir e invocando advpls cli...")
    typer.echo("        (mesmo mecanismo que o TDS-VSCode usa via LSP)")
    result = probe_appserver_network(host, port, binary)

    if not result.build:
        typer.secho("        ✗ Probe falhou.\n", fg=typer.colors.RED)
        typer.secho(f"  Erro: {result.error}", fg=typer.colors.RED, err=True)
        if result.raw_output:
            typer.echo("\n  Output parcial do advpls (primeiros 1KB):")
            for line in result.raw_output.splitlines()[:15]:
                typer.echo(f"    | {line}")
        typer.echo(
            f"\n  Troubleshooting:\n"
            f"    • AppServer em {host}:{port} está rodando?\n"
            f"      Teste TCP: Test-NetConnection {host} -Port {port}  (PowerShell)\n"
            f"      Ou:        nc -zv {host} {port}                     (bash)\n"
            f"    • Se está em SSL/TLS, advpls precisa de --secure (TODO).\n"
            f"    • Para AppServers Lobo Guara antigos (≤19.3.0.5), o validate\n"
            f"      pode não funcionar (issue tds-vscode#390). Use o fallback log:\n"
            f"      plugadvpl compile --probe-appserver <path-pra-protheus.log>"
        )
        raise typer.Exit(code=1)

    typer.echo("        ✓ AppServer respondeu\n")
    typer.echo("  [3/3] Parseando resposta...")
    typer.secho(f"        ✓ build:  {result.build}", fg=typer.colors.GREEN)
    if result.secure is not None:
        secure_label = "SSL/TLS habilitado" if result.secure else "TCP plano"
        typer.echo(f"        ✓ secure: {result.secure}  ({secure_label})")

    typer.echo("")
    typer.secho("=== Pronto pra cadastrar o server ===", fg=typer.colors.GREEN)
    typer.echo(
        f"\nOpção 1 (interativo) — pula o prompt de build:\n"
        f"  plugadvpl compile --add-server\n"
        f"  # quando perguntar Build, cole: {result.build}\n"
        f"  # quando perguntar HTTPS/TLS, responda: "
        f"{'sim' if result.secure else 'não'}\n"
        f"\n"
        f"Opção 2 (manual) — edite ~/.plugadvpl/servers.json:\n"
        f'  {{"host": "{host}", "port": {port}, "build": "{result.build}", '
        f'"secure": {str(bool(result.secure)).lower()}, ...}}'
    )


def _probe_via_log(target: Path) -> None:
    """Log probe parseia ``protheus.log`` (v0.8.11 — fallback offline)."""
    from plugadvpl.compile_probe import probe_appserver_log

    typer.echo("\n=== probe-appserver (modo log) ===")
    typer.echo(f"  alvo: {target}\n")

    typer.echo("  [1/2] Procurando protheus.log...")
    result = probe_appserver_log(target)
    if result is None:
        typer.secho(
            f"        ✗ protheus.log não encontrado.\n"
            f"\n"
            f"  Procuramos em (relativo a {target}):\n"
            f"    log/protheus.log\n"
            f"    bin/Appserver/log/protheus.log\n"
            f"    bin/Appserver/protheus.log\n"
            f"    protheus.log\n"
            f"\n"
            f"  Se o log está em outro lugar, aponte direto pro arquivo:\n"
            f"    plugadvpl compile --probe-appserver <caminho-completo>/protheus.log\n"
            f"\n"
            f"  Ou tente o modo network (mais robusto):\n"
            f"    plugadvpl compile --probe-appserver <host>:<port>",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo(f"        ✓ {result.log_path}\n")

    typer.echo(f"  [2/2] Parseando primeiras {result.lines_scanned} linhas...")
    if not result.build:
        typer.secho(
            "        ✗ Linha 'TOTVS - Build X - Date' não encontrada.\n"
            "\n"
            "  Possíveis causas:\n"
            "    • AppServer nunca foi iniciado (log vazio de boot)\n"
            "    • Log foi truncado (linha de boot ficou fora das primeiras 5000)\n"
            "    • Versão muito antiga do Protheus com formato diferente\n"
            "\n"
            "  Alternativa: tente o modo network:\n"
            "    plugadvpl compile --probe-appserver <host>:<port>",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    typer.secho(f"        ✓ build:      {result.build}", fg=typer.colors.GREEN)
    typer.echo(f"        ✓ build_date: {result.build_date}")
    typer.echo("")
    typer.secho("=== Pronto pra cadastrar o server ===", fg=typer.colors.GREEN)
    typer.echo(
        f"\nOpção 1 (interativo):\n"
        f"  plugadvpl compile --add-server\n"
        f"  # quando perguntar Build, cole: {result.build}\n"
        f"\n"
        f"Opção 2 (runtime.toml):\n"
        f'  [appserver].build = "{result.build}"'
    )


def _handle_set_credentials(server_name: str) -> None:
    """Salva user+senha do server no cofre nativo do OS (v0.9.0)."""
    from plugadvpl.compile_servers import get_server
    from plugadvpl.credentials import (
        KEYRING_SERVICE,
        keyring_available,
        set_credentials_in_keyring,
    )

    srv = get_server(server_name)
    if srv is None:
        typer.secho(
            f"Server '{server_name}' não cadastrado.\n"
            f"  Liste: plugadvpl compile --list-servers\n"
            f"  Cadastre: plugadvpl compile --add-server",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if not keyring_available():
        typer.secho(
            "\nERRO: cofre do OS não disponível neste sistema.\n"
            "  Possíveis causas:\n"
            "    • Linux server sem D-Bus / sem gnome-keyring / sem kwallet\n"
            "    • SSH sem forwarding de DBUS_SESSION_BUS_ADDRESS\n"
            "  Use env vars como fallback:\n"
            f"    export {srv.user_env}=<usuário>\n"
            f"    export {srv.password_env}=<senha>",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    typer.echo("\n=== Salvar credenciais no cofre do OS ===")
    typer.echo(f"  Server: {server_name} ({srv.host}:{srv.port})")
    typer.echo(f"  Cofre service: {KEYRING_SERVICE}")
    typer.echo(f"  Cofre key (user): {server_name}:user")
    typer.echo(f"  Cofre key (pass): {server_name}:password\n")

    user = typer.prompt(f"Usuário Protheus para {server_name}").strip()
    if not user:
        typer.secho("Usuário não pode ser vazio.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    password = typer.prompt(
        "Senha (não será ecoada)",
        hide_input=True,
        confirmation_prompt=True,
    )
    if not password:
        typer.secho("Senha não pode ser vazia.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    try:
        set_credentials_in_keyring(server_name, user, password)
    except RuntimeError as exc:
        typer.secho(f"\nERRO ao gravar no cofre: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho(
        f"\n✓ Credenciais salvas no cofre do OS pra server '{server_name}'.\n"
        f"  Próximas chamadas com `--use-server {server_name}` resolvem\n"
        f"  user+pass automaticamente — sem precisar exportar env var.\n"
        f"\n"
        f"  Para remover: plugadvpl compile --clear-credentials {server_name}",
        fg=typer.colors.GREEN,
    )


def _handle_set_restart_cmd(server_name: str, cmd: str) -> None:
    """Grava o restart_cmd no server do registry global (v0.14)."""
    from dataclasses import replace

    from plugadvpl.compile_servers import (
        ServersRegistry,
        get_server,
        load_registry,
        save_registry,
    )

    srv = get_server(server_name)
    if srv is None:
        typer.secho(
            f"Server '{server_name}' não cadastrado.\n"
            f"  Liste: plugadvpl compile --list-servers\n"
            f"  Cadastre: plugadvpl compile --add-server",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    new_srv = replace(srv, restart_cmd=cmd)
    registry = load_registry()
    new_servers = [new_srv if s.name == server_name else s for s in registry.servers]
    save_registry(ServersRegistry(default=registry.default, servers=new_servers))

    typer.secho(
        f"restart_cmd setado pra '{server_name}': {cmd!r}",
        fg=typer.colors.GREEN,
    )


def _handle_set_is_prod(server_name: str, is_prod: bool) -> None:
    """Marca/desmarca server como produção (v0.15)."""
    from dataclasses import replace

    from plugadvpl.compile_servers import (
        ServersRegistry,
        get_server,
        load_registry,
        save_registry,
    )

    srv = get_server(server_name)
    if srv is None:
        typer.secho(
            f"Server '{server_name}' não cadastrado.\n  Liste: plugadvpl compile --list-servers",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    new_srv = replace(srv, is_prod=is_prod)
    registry = load_registry()
    new_servers = [new_srv if s.name == server_name else s for s in registry.servers]
    save_registry(ServersRegistry(default=registry.default, servers=new_servers))

    label = "PROD" if is_prod else "não-PROD"
    typer.secho(
        f"server '{server_name}' marcado como {label}",
        fg=typer.colors.YELLOW if is_prod else typer.colors.GREEN,
    )


def _handle_clear_credentials(server_name: str) -> None:
    """Remove credenciais do server do cofre (v0.9.0)."""
    from plugadvpl.credentials import clear_credentials_from_keyring, keyring_available

    if not keyring_available():
        typer.secho(
            "Cofre do OS não disponível — nada para limpar.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=0)

    removed_user, removed_pwd = clear_credentials_from_keyring(server_name)
    if not (removed_user or removed_pwd):
        typer.secho(
            f"Nenhuma credencial encontrada no cofre para '{server_name}'.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=0)

    typer.secho(
        f"✓ Credenciais removidas do cofre para '{server_name}'.\n"
        f"  (user removido: {removed_user}, password removido: {removed_pwd})",
        fg=typer.colors.GREEN,
    )


def _handle_explain_config(
    ctx: typer.Context,
    root: Path,
    use_server: str,
    use_environment: str,  # noqa: ARG001 -- reservado pra explicar override de env (v0.10+); call sites passam, handler ainda nao consome
) -> None:
    """Mostra de onde vem cada campo da config resolvida (v0.9.0).

    Atende ao gap "ordem de precedência sem doc" reportado pelo usuário.
    Saída JSON-friendly (consumível por agente IA) com format=json.
    """
    from plugadvpl.compile_servers import default_server, get_server
    from plugadvpl.credentials import keyring_available, resolve_credentials
    from plugadvpl.runtime_config import RuntimeConfigError
    from plugadvpl.runtime_config import load as load_runtime_config

    out: dict[str, object] = {
        "resolution_order": [
            "1. CLI flag (--use-server NAME, --use-environment ENV)",
            "2. runtime.toml (<root>/.plugadvpl/runtime.toml)",
            "3. Registry global (~/.plugadvpl/servers.json) — pelo nome do server",
            "4. Keyring do OS (Win Cred Mgr / macOS Keychain / Linux Secret Service)",
            "5. Env vars (nome configurado em [auth].user_env / password_env)",
            "6. Auto-detect (advpls em PATH ou pasta interna ~/.plugadvpl/advpls/)",
        ],
        "fields": {},
        "credentials": {},
    }
    fields = out["fields"]
    assert isinstance(fields, dict)

    # runtime.toml
    runtime_cfg = None
    try:
        runtime_cfg = load_runtime_config(root)
    except RuntimeConfigError as exc:
        fields["runtime_toml"] = {"loaded": False, "error": str(exc)}
    else:
        if runtime_cfg is not None:
            fields["runtime_toml"] = {
                "loaded": True,
                "path": str(runtime_cfg.source_path),
                "appserver_host": runtime_cfg.appserver.host,
                "appserver_port": runtime_cfg.appserver.port,
                "appserver_build": runtime_cfg.appserver.build,
                "appserver_reachable": runtime_cfg.appserver_reachable,
                "tds_ls_binary": str(runtime_cfg.tds_ls.binary),
                "auth_user_env": runtime_cfg.auth.user_env,
                "auth_password_env": runtime_cfg.auth.password_env,
            }
        else:
            fields["runtime_toml"] = {"loaded": False, "reason": "file_not_found"}

    # Server escolhido (--use-server explícito OU default do registry)
    server = None
    if use_server:
        server = get_server(use_server)
        fields["server"] = {
            "source": "cli_flag",
            "name": use_server,
            "found": server is not None,
        }
    else:
        server = default_server()
        fields["server"] = {
            "source": "registry_default",
            "name": server.name if server else None,
            "found": server is not None,
        }

    if server is not None:
        s_dict = fields["server"]
        assert isinstance(s_dict, dict)
        s_dict.update(
            {
                "host": server.host,
                "port": server.port,
                "build": server.build,
                "environments": server.environments,
                "default_environment": server.default_environment,
                "user_env": server.user_env,
                "password_env": server.password_env,
                "includes_count": len(server.includes),
                "secure": server.secure,
            }
        )
        # Credenciais
        creds = resolve_credentials(server.name, server.user_env, server.password_env)
        out["credentials"] = creds.to_safe_dict()
    else:
        out["credentials"] = {
            "user": "<no server selected>",
            "password": "<no server selected>",
            "keyring_available": keyring_available(),
        }

    # Output respeita --format json/md/table (passado em obj["format"])
    from plugadvpl.output import render

    render(
        rows=[out],
        format=ctx.obj["format"],
        title="plugadvpl compile --explain-config",
        next_steps=[],
    )


def _apply_server_override(  # noqa: PLR0912, PLR0915 -- merge de override (server registry + flags) com varias regras de precedencia; cada branch e uma fonte de config
    runtime_cfg: RuntimeConfig | None,
    server: Server,
    env_override: str = "",
    requested_mode: str = "auto",
) -> RuntimeConfig | None:
    """Constrói runtime_cfg com [appserver] vindo do registry global.

    Se runtime_cfg=None, cria um do zero usando defaults (modo "compile sem
    runtime.toml mas com --use-server"). Se runtime_cfg existe, sobrescreve
    apenas [appserver] e [auth] preservando [tds_ls]/[compile]/[logging].

    Args:
        requested_mode: ``"auto"``, ``"appre"`` ou ``"cli"``. Se ``"appre"``
            explícito, pula validação de credenciais (appre é só
            pré-processador local, não conecta no AppServer).
    """
    from plugadvpl.compile_servers import Server
    from plugadvpl.runtime_config import (
        AppserverConfig,
        AuthConfig,
        CompileConfig,
        LoggingConfig,
        RuntimeConfig,
        TdsLsConfig,
        _tcp_ping,
    )

    assert isinstance(server, Server)

    # v0.8.8 fix bug 4: valida que o server tem TODOS os campos preenchidos
    # ANTES de tentar compilar. Antes: --import-tds-servers ou --add-server
    # podia gravar server com build="" e quebrava silenciosamente depois
    # (advpls recebe build vazio, falha na auth sem mensagem útil).
    missing: list[str] = []
    if not server.host:
        missing.append("host")
    if not server.port:
        missing.append("port")
    if not server.build:
        missing.append("build (versão do AppServer, ex: 7.00.240223P)")
    if not server.environments:
        missing.append("environments (lista, ex: ['P2510'])")
    if not server.default_environment:
        missing.append("default_environment")
    if missing:
        typer.secho(
            f"\nERRO: server '{server.name}' está incompleto. Faltam: {', '.join(missing)}\n"
            f"  Rode `plugadvpl compile --add-server` pra recadastrar OU edite\n"
            f"  ~/.plugadvpl/servers.json manualmente preenchendo esses campos.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    # v0.9.1: credenciais só são exigidas se vai conectar no AppServer (mode=cli).
    # Em mode=appre (pré-processador local), advpls não autentica.
    # Em mode=auto, validamos pra ser conservador — se appserver_reachable
    # cair pra appre depois, o build_ini_script nem é chamado mesmo.
    needs_credentials = requested_mode != "appre"

    # v0.9.0: credenciais via env OU keyring do sistema (Win Credential Manager
    # / macOS Keychain / Linux Secret Service). Resolve em camadas, falha clara
    # se nenhuma fonte tem ambos.
    from plugadvpl.credentials import resolve_credentials

    creds = resolve_credentials(server.name, server.user_env, server.password_env)
    if needs_credentials and not creds.is_complete:
        missing_parts: list[str] = []
        if not creds.user:
            missing_parts.append("user")
        if not creds.password:
            missing_parts.append("password")
        kr_hint = (
            (
                f"    plugadvpl compile --set-credentials {server.name}\n"
                f"    # prompt seguro (senha NÃO ecoada), salva no cofre do OS\n"
            )
            if creds.keyring_available
            else (
                "    # keyring backend não disponível neste sistema —\n"
                "    # use env vars (próxima opção)\n"
            )
        )
        typer.secho(
            f"\nERRO: server '{server.name}' sem credencial ({', '.join(missing_parts)}).\n"
            f"\n"
            f"  Opção A — keyring (recomendado, persiste no cofre do OS):\n"
            f"{kr_hint}"
            f"\n"
            f"  Opção B — env vars (uso pontual, CI/CD):\n"
            f'    $env:{server.user_env} = "<usuário>"     # PowerShell\n'
            f'    $env:{server.password_env} = "<senha>"\n'
            f"    # OU:\n"
            f"    export {server.user_env}=<usuário>      # bash/zsh\n"
            f"    export {server.password_env}=<senha>",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    # Se vieram do keyring, injeta em os.environ pra `compile._build_ini_script`
    # ler como se fossem env. Mutação é só pro processo CLI (não vaza pra shell).
    # Em mode=appre creds podem estar vazias — não injeta nada nesse caso.
    import os as _os

    if creds.user and creds.user_source == "keyring":
        _os.environ[server.user_env] = creds.user
    if creds.password and creds.password_source == "keyring":
        _os.environ[server.password_env] = creds.password

    env = env_override or server.default_environment
    if env not in server.environments:
        typer.secho(
            f"Environment '{env}' não está em {server.environments}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    new_appserver = AppserverConfig(
        host=server.host,
        port=server.port,
        secure=server.secure,
        build=server.build,
        environment=env,
    )
    new_auth = AuthConfig(
        user_env=server.user_env,
        password_env=server.password_env,
        aut_file=None,
    )

    if runtime_cfg is None:
        # Sem runtime.toml: tds_ls/compile/logging vêm de defaults sensatos
        from plugadvpl.compile_doctor import _detect_advpls

        binary = _detect_advpls()
        if binary is None:
            typer.secho(
                "advpls não detectado. Rode: plugadvpl compile --install-advpls",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        tds_ls = TdsLsConfig(binary=binary.resolve(), binary_is_symlink=False)
        # v0.8.11 bug 1: usa includes do server (vindos do TDS-VSCode via
        # buildVersion/includes) quando o server tem essa info.
        includes_from_server = tuple(Path(p) for p in server.includes)
        compile_cfg = CompileConfig(
            recompile=True,
            includes=includes_from_server,
            mode="cli",
            timeout_seconds=120,
            include_warnings=True,
        )
        logging_cfg = LoggingConfig(log_to_file="", show_console_output=True)
        warn_remote = server.host not in {"127.0.0.1", "localhost", "::1"}
        reachable = _tcp_ping(server.host, server.port)
        return RuntimeConfig(
            tds_ls=tds_ls,
            appserver=new_appserver,
            auth=new_auth,
            compile=compile_cfg,
            logging=logging_cfg,
            warn_remote_host=warn_remote,
            appserver_reachable=reachable,
            source_path=Path("<--use-server>"),
        )

    # Com runtime.toml: sobrescreve só appserver/auth, re-pinga TCP
    assert isinstance(runtime_cfg, RuntimeConfig)
    warn_remote = server.host not in {"127.0.0.1", "localhost", "::1"}
    reachable = _tcp_ping(server.host, server.port)
    return RuntimeConfig(
        tds_ls=runtime_cfg.tds_ls,
        appserver=new_appserver,
        auth=new_auth,
        compile=runtime_cfg.compile,
        logging=runtime_cfg.logging,
        warn_remote_host=warn_remote,
        appserver_reachable=reachable,
        source_path=runtime_cfg.source_path,
    )


def _handle_install_advpls(yes: bool) -> None:  # noqa: PLR0912, PLR0915 -- handler interativo do --install-advpls (detecta TDS, decide copy vs download, confirma cada acao); fluxo conversacional natural
    """Install/replace advpls em ~/.plugadvpl/advpls/. Interativo.

    Sempre explica o que vai fazer ANTES + pede confirmação (unless --yes).
    Não toca em filesystem antes do user confirmar cada operação.
    """
    from plugadvpl.compile_installer import (
        execute_copy,
        execute_download,
        install_dir,
        installed_binary_path,
        is_installed,
        plan_copy,
        plan_download,
    )

    # 1. Estado atual
    target = installed_binary_path()
    typer.echo("\n=== plugadvpl install-advpls ===")
    typer.echo(f"Pasta interna: {install_dir()}")
    if is_installed():
        size_mb = target.stat().st_size // (1024 * 1024)
        typer.echo(f"Status: JÁ INSTALADO em {target} ({size_mb} MB)")
        if not yes and not typer.confirm(
            "Já existe. Quer SUBSTITUIR (vai sobrescrever)?",
            default=False,
        ):
            typer.echo("Cancelado. Nada foi alterado.")
            raise typer.Exit(code=0)
    else:
        typer.echo(f"Status: NÃO instalado (esperado em {target})")

    # 2. Escolher source
    typer.echo("\nDe onde obter o advpls?")
    typer.echo("  (1) Copiar de um path local (você informa onde está)")
    typer.echo("  (2) Baixar do Marketplace VSCode público (~118MB)")
    typer.echo("  (3) Cancelar")

    if yes:
        typer.secho(
            "ERROR: --yes requer escolha não-interativa, mas --install-advpls "
            "sempre pergunta a fonte. Rode sem --yes ou contribua flag "
            "--install-source={copy|download} no plugin.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    choice = typer.prompt("Escolha 1/2/3", type=int)
    if choice == 3:  # noqa: PLR2004 -- ID de opcao no prompt interativo (1/2/3)
        typer.echo("Cancelado.")
        raise typer.Exit(code=0)
    if choice not in (1, 2):
        typer.secho("Opção inválida.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    # 3. Construir plano
    if choice == 1:
        src_str = typer.prompt(
            "Path do advpls (ex: D:/IA/Tools/tds-vscode/extracted/extension/"
            "node_modules/@totvs/tds-ls/bin/windows/advpls.exe)"
        )
        src_path = Path(src_str)
        if not src_path.is_file():
            typer.secho(
                f"Arquivo não existe: {src_path}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        plan = plan_copy(src_path)
    else:
        plan = plan_download()

    # 4. Mostrar plano + confirmar
    typer.echo("\n=== PLANO DE INSTALAÇÃO ===")
    typer.echo(plan.description)
    typer.echo(f"\nTamanho estimado: ~{plan.estimated_size_mb} MB")
    typer.echo(f"Precisa de rede: {'sim' if plan.needs_network else 'não'}")
    typer.echo()

    if not typer.confirm("Confirma e prossegue?", default=True):
        typer.echo("Cancelado. Nada foi feito.")
        raise typer.Exit(code=0)

    # 5. Executar
    def _progress(msg: str) -> None:
        typer.echo(f"  ... {msg}")

    typer.echo("\nExecutando...")
    if plan.action == "copy":
        result = execute_copy(plan, progress=_progress)
    else:
        result = execute_download(plan, progress=_progress)

    if not result.ok:
        typer.secho(f"\nFALHOU: {result.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    size_mb = result.bytes_written // (1024 * 1024)
    typer.secho(
        f"\n✓ Instalado: {result.binary_path} ({size_mb} MB)",
        fg=typer.colors.GREEN,
    )
    typer.echo(
        "\nPróximos passos:\n"
        "  plugadvpl compile --doctor    # confirma detecção\n"
        "  plugadvpl compile --mode appre --includes <pasta> <fonte.prw>"
    )


def _handle_doctor(ctx: typer.Context, root: Path) -> None:
    """Pre-flight check do ambiente compile. Saída JSON estruturada pra agente."""
    from plugadvpl.compile_doctor import run_doctor
    from plugadvpl.runtime_config import RuntimeConfigError
    from plugadvpl.runtime_config import load as load_runtime_config

    try:
        runtime_cfg = load_runtime_config(root)
    except RuntimeConfigError as exc:
        typer.secho(f"runtime config error: {exc}", fg=typer.colors.YELLOW, err=True)
        runtime_cfg = None

    result = run_doctor(root, runtime_cfg)
    _render_from_ctx(
        ctx,
        [result.to_dict()],
        title=f"compile doctor — {result.status}",
    )
    # Exit 0 se ready, 1 se precisa setup (agente decide)
    raise typer.Exit(code=0 if result.status == "ready" else 1)


def _handle_init_config(root: Path, force: bool) -> None:
    from plugadvpl.runtime_config import init_gitignore_entry, render_template

    cfg_dir = root / ".plugadvpl"
    cfg_dir.mkdir(exist_ok=True)
    target = cfg_dir / "runtime.toml"
    if target.exists() and not force:
        typer.secho(
            f"{target} already exists. Use --force to overwrite.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)
    target.write_text(render_template(), encoding="utf-8")
    added = init_gitignore_entry(root)
    typer.echo(f"created: {target}")
    if added:
        typer.echo("added to .gitignore: .plugadvpl/runtime.toml")


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


_GLOBAL_FLAGS = {
    "--root",
    "-r",
    "--db",
    "--format",
    "-f",
    "--limit",
    "--offset",
    "--compact",
    "--quiet",
    "-q",
    "--no-next-steps",
    "--version",
    "-V",
}

# v0.3.22 (#18 do QA round 2): flags scoped a subcomando especifico.
# Caso inverso de #2: usuario poe flag de subcomando ANTES do subcomando
# (`plugadvpl --workers 8 ingest`) e Click responde "No such option" cru
# sem dica. Detectamos e sugerimos posicao correta.
_SUBCOMMAND_FLAGS = {
    # ingest
    "--workers",
    "-w",
    "--no-content",
    "--redact-secrets",
    "--incremental",
    "--no-incremental",
    # status
    "--check-stale",
    # lint
    "--severity",
    "--rule",
    "--cross-file",
    # gatilho/impacto
    "--depth",
    # tables
    "--mode",
    "-m",
    "--read",
    "--write",
    "--reclock",
}


def main() -> None:
    """Entry point para console_script ``plugadvpl``."""
    # Defense layer: força stdout/stderr para UTF-8 em Windows. Sem isto, qualquer
    # caractere fora do cp1252 (default do console PS 5.1/cmd.exe) crasha com
    # UnicodeEncodeError quando o Rich renderiza help ou output. errors='replace'
    # garante que mesmo se algo escapar, vira '?' em vez de tombar.
    if sys.platform == "win32":
        import contextlib

        for stream in (sys.stdout, sys.stderr):
            with contextlib.suppress(AttributeError, ValueError, io.UnsupportedOperation):
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    # v0.3.15 (#2 do QA report): hint quando usuário põe flag global APÓS
    # subcomando. Click reporta "No such option: --limit" sem dica de que a
    # flag existe mas no escopo errado. Detectamos a chamada misplaced e
    # adicionamos uma linha amarela orientando posicionamento correto.
    misplaced = _detect_misplaced_flag(sys.argv[1:])
    try:
        app()
    except SystemExit as exit_:
        if misplaced and exit_.code not in (0, None):
            flag, subcmd, scope = misplaced
            if scope == "global":
                typer.secho(
                    f"\nDica: '{flag}' eh uma flag GLOBAL — vem ANTES do subcomando.\n"
                    f"  Errado:  plugadvpl {subcmd} {flag} ...\n"
                    f"  Correto: plugadvpl {flag} ... {subcmd}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            else:  # scope == "subcommand"
                typer.secho(
                    f"\nDica: '{flag}' eh uma flag de SUBCOMANDO — vem DEPOIS do subcomando.\n"
                    f"  Errado:  plugadvpl {flag} ... {subcmd}\n"
                    f"  Correto: plugadvpl {subcmd} {flag} ...",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
        raise


def _detect_misplaced_flag(
    argv: list[str],
) -> tuple[str, str, str] | None:
    """Detecta flag em posicao errada. Retorna (flag, subcomando, scope).

    Dois cenarios:
      - scope="global": flag global aparece DEPOIS do subcomando.
      - scope="subcommand": flag scoped aparece ANTES do subcomando.
    """
    subcmd: str | None = None
    skip_next = False
    pre_subcmd_misplaced: tuple[str, str] | None = None  # (flag, ?)
    for tok in argv:
        if skip_next:
            skip_next = False
            continue
        if subcmd is None:
            if tok.startswith("-"):
                # Pode ser flag global no escopo certo (antes do subcmd) que
                # aceita valor. Pula o próximo token se a flag tipicamente o exige.
                if tok in _GLOBAL_FLAGS and tok not in {
                    "--compact",
                    "--quiet",
                    "-q",
                    "--no-next-steps",
                    "--version",
                    "-V",
                }:
                    skip_next = True
                # v0.3.22: flag de subcomando aparecendo antes — registramos
                # mas precisamos do subcmd pra sugerir corretamente.
                elif tok in _SUBCOMMAND_FLAGS and pre_subcmd_misplaced is None:
                    pre_subcmd_misplaced = (tok, "")
                    # Pula valor da flag (heuristica: a maioria aceita valor).
                    if tok not in {
                        "--no-content",
                        "--redact-secrets",
                        "--incremental",
                        "--no-incremental",
                        "--check-stale",
                        "--cross-file",
                        "--read",
                        "--write",
                        "--reclock",
                    }:
                        skip_next = True
                continue
            subcmd = tok
            if pre_subcmd_misplaced:
                return (pre_subcmd_misplaced[0], subcmd, "subcommand")
            continue
        if tok in _GLOBAL_FLAGS:
            return (tok, subcmd, "global")
    return None


# Alias retrocompat (testes antigos podem importar este nome).
_detect_misplaced_global_flag = _detect_misplaced_flag


if __name__ == "__main__":
    main()
    sys.exit(0)
