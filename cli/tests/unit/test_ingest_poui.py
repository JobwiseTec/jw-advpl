from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)
    yield c
    c.close()


def test_tabela_poui_projetos_existe(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(poui_projetos)")}
    assert {"caminho", "poui_version", "angular_major", "compativel", "pacotes_json"} <= cols


def _write_pkg(tmp_path: Path, content: str) -> Path:
    proj = tmp_path / "front"
    proj.mkdir(exist_ok=True)
    p = proj / "package.json"
    p.write_text(content, encoding="utf-8")
    return p


def test_ingest_persiste_projeto(conn: sqlite3.Connection, tmp_path: Path) -> None:
    from plugadvpl.ingest_poui import ingest_poui_dir

    _write_pkg(
        tmp_path,
        '{"dependencies": {"@angular/core": "^19.0.0", "@po-ui/ng-components": "21.18.0"}}',
    )
    res = ingest_poui_dir(conn, tmp_path)
    assert res.ingested == 1
    row = conn.execute(
        "SELECT poui_version, angular_major, compativel FROM poui_projetos"
    ).fetchone()
    assert row[0] == "21.18.0"
    assert row[1] == 19
    assert row[2] == 0  # incompatível (21 != 19)


def test_ingest_ignora_node_modules(conn: sqlite3.Connection, tmp_path: Path) -> None:
    from plugadvpl.ingest_poui import ingest_poui_dir

    nm = tmp_path / "node_modules" / "@po-ui" / "ng-components"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text('{"name": "@po-ui/ng-components"}', encoding="utf-8")
    res = ingest_poui_dir(conn, tmp_path)
    assert res.ingested == 0  # não varre node_modules


def test_ingest_nao_pula_por_ancestral_homonimo(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    from plugadvpl.ingest_poui import ingest_poui_dir

    # root sob uma pasta-ancestral chamada 'tmp' (em _SKIP_DIRS) NÃO pode
    # mascarar o projeto apontado diretamente — o skip é relativo a root.
    root = tmp_path / "tmp" / "myfront"
    root.mkdir(parents=True)
    (root / "package.json").write_text(
        '{"dependencies": {"@po-ui/ng-components": "21.18.0"}}', encoding="utf-8"
    )
    res = ingest_poui_dir(conn, root)
    assert res.ingested == 1


def test_ingest_cache_skip(conn: sqlite3.Connection, tmp_path: Path) -> None:
    from plugadvpl.ingest_poui import ingest_poui_dir

    _write_pkg(tmp_path, '{"dependencies": {"@po-ui/ng-components": "21.18.0"}}')
    ingest_poui_dir(conn, tmp_path)
    res2 = ingest_poui_dir(conn, tmp_path)
    assert res2.ingested == 0 and res2.skipped == 1


def test_tabela_poui_datasources_existe(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(poui_datasources)")}
    assert {"caminho", "linha", "verbo", "path_norm", "url_raw"} <= cols


def test_tabela_poui_componentes_uso_existe(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(poui_componentes_uso)")}
    assert {"caminho", "linha", "componente", "binding", "kind"} <= cols


def test_ingest_extrai_datasources(conn: sqlite3.Connection, tmp_path: Path) -> None:
    from plugadvpl.ingest_poui import ingest_poui_dir

    proj = tmp_path / "front"
    proj.mkdir()
    (proj / "package.json").write_text(
        '{"dependencies": {"@po-ui/ng-components": "15.0.0"}}', encoding="utf-8"
    )
    svc = proj / "src" / "app" / "services"
    svc.mkdir(parents=True)
    (svc / "pedido.service.ts").write_text(
        "getAll(){return this.http.get<X[]>('/pedidos');}", encoding="utf-8"
    )
    ingest_poui_dir(conn, tmp_path)
    rows = conn.execute(
        "SELECT verbo, path_norm FROM poui_datasources"
    ).fetchall()
    assert ("GET", "/pedidos") in rows


def test_ingest_extrai_template_usage(conn: sqlite3.Connection, tmp_path: Path) -> None:
    from plugadvpl.ingest_poui import ingest_poui_dir

    proj = tmp_path / "front"
    proj.mkdir()
    (proj / "package.json").write_text(
        '{"dependencies": {"@po-ui/ng-components": "21.0.0"}}', encoding="utf-8"
    )
    src = proj / "src"
    src.mkdir()
    (src / "app.component.html").write_text(
        "<po-button [p-label]='Salvar'></po-button>", encoding="utf-8"
    )
    ingest_poui_dir(conn, tmp_path)
    rows = conn.execute(
        "SELECT componente, binding, kind FROM poui_componentes_uso"
    ).fetchall()
    assert ("po-button", "p-label", "input") in rows


def test_poui_bridge_casa_front_e_back(conn: sqlite3.Connection) -> None:
    from plugadvpl.query import poui_bridge

    # back (rest_endpoints já existe no schema): rota TLPP @Get /pedidos
    conn.execute(
        "INSERT INTO rest_endpoints (arquivo, classe, funcao, verbo, path, annotation_style) "
        "VALUES ('PEDREST.tlpp', '', 'getPedidos', 'GET', '/pedidos', '@verb_tlpp')"
    )
    # front: chamada Angular casável
    conn.execute(
        "INSERT INTO poui_datasources (caminho, linha, verbo, url_raw, path_norm) "
        "VALUES ('src/app/services/pedido.service.ts', 10, 'GET', '/pedidos', '/pedidos')"
    )
    conn.commit()
    rows = poui_bridge(conn)
    assert len(rows) == 1
    b = rows[0]
    assert b["verbo"] == "GET"
    assert b["path"] == "/pedidos"
    assert b["back_arquivo"] == "PEDREST.tlpp"
    assert "pedido.service.ts" in b["front_arquivo"]


def test_poui_bridge_sufixo_e_verbo_opcional(conn: sqlite3.Connection) -> None:
    from plugadvpl.query import poui_bridge

    # back tem path completo com prefixo de base; front tem o curto + verbo
    # desconhecido (URL montada em variável -> verbo='').
    conn.execute(
        "INSERT INTO rest_endpoints (arquivo, classe, funcao, verbo, path, annotation_style) "
        "VALUES ('REST.tlpp', '', 'm', 'GET', '/api/v2/base/pedidos', '@verb_tlpp')"
    )
    conn.execute(
        "INSERT INTO poui_datasources (caminho, linha, verbo, url_raw, path_norm) "
        "VALUES ('p.service.ts', 5, '', '/pedidos', '/pedidos')"
    )
    conn.commit()
    rows = poui_bridge(conn)
    assert len(rows) == 1  # casa por sufixo, mesmo com verbo='' no front
    assert rows[0]["path"] == "/pedidos"


def test_query_poui_projetos(conn: sqlite3.Connection, tmp_path: Path) -> None:
    from plugadvpl.ingest_poui import ingest_poui_dir
    from plugadvpl.query import poui_projetos

    _write_pkg(
        tmp_path,
        '{"dependencies": {"@angular/core": "^21.0.0", "@po-ui/ng-components": "21.18.0"}}',
    )
    ingest_poui_dir(conn, tmp_path)
    rows = poui_projetos(conn)
    assert len(rows) == 1
    assert rows[0]["poui_version"] == "21.18.0"
    assert rows[0]["compativel"] == 1
    assert rows[0]["pacotes"] == ["@po-ui/ng-components"]
