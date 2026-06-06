from __future__ import annotations

from plugadvpl.parsing.poui import extract_angular_http_calls, parse_poui_package_json


def test_detecta_poui_e_versao() -> None:
    pkg = """{
      "dependencies": {
        "@angular/core": "^21.0.3",
        "@po-ui/ng-components": "21.18.0",
        "@po-ui/ng-templates": "21.18.0"
      }
    }"""
    p = parse_poui_package_json(pkg)
    assert p is not None
    assert p.poui_version == "21.18.0"
    assert p.poui_major == 21
    assert p.poui_packages == ["@po-ui/ng-components", "@po-ui/ng-templates"]


def test_sem_poui_retorna_none() -> None:
    assert parse_poui_package_json('{"dependencies": {"@angular/core": "^21.0.0"}}') is None


def test_json_invalido_retorna_none() -> None:
    assert parse_poui_package_json("{ não é json }") is None


def test_angular_major_e_compativel() -> None:
    pkg = '{"dependencies": {"@angular/core": "^21.0.3", "@po-ui/ng-components": "21.18.0"}}'
    p = parse_poui_package_json(pkg)
    assert p is not None
    assert p.angular_major == 21
    assert p.compativel is True


def test_incompativel_poui_ahead_do_angular() -> None:
    # @po-ui 21 exige Angular 21, mas o projeto está em Angular 19 → incompatível.
    pkg = '{"dependencies": {"@angular/core": "^19.2.0", "@po-ui/ng-components": "21.18.0"}}'
    p = parse_poui_package_json(pkg)
    assert p is not None
    assert p.poui_major == 21
    assert p.angular_major == 19
    assert p.compativel is False


def test_sem_angular_core_assume_compativel() -> None:
    p = parse_poui_package_json('{"dependencies": {"@po-ui/ng-components": "20.13.1"}}')
    assert p is not None
    assert p.angular_major is None
    assert p.compativel is True


def test_dependencies_vence_peer_na_versao() -> None:
    # Pin real em dependencies não pode ser sobrescrito pelo range de peerDependencies.
    pkg = """{
      "dependencies": {"@po-ui/ng-components": "21.18.0"},
      "peerDependencies": {"@po-ui/ng-components": "^21.0.0"}
    }"""
    p = parse_poui_package_json(pkg)
    assert p is not None
    assert p.poui_version == "21.18.0"


def test_versao_nao_numerica_vira_major_none() -> None:
    p = parse_poui_package_json('{"dependencies": {"@po-ui/ng-components": "latest"}}')
    assert p is not None
    assert p.poui_major is None
    assert p.compativel is True  # sem major comparável → não flag


def test_http_call_literal_e_template() -> None:
    ts = """
    getPedidos() { return this.http.get<Pedido[]>('/pedidos'); }
    salvar(p) { return this.http.post(`${environment.api}/processar`, p); }
    del(id) { return this.http.delete(`${env.base}/pedidos/${id}`); }
    """
    calls = extract_angular_http_calls(ts)
    verbos = {(c["verbo"], c["path_norm"]) for c in calls}
    assert ("GET", "/pedidos") in verbos
    assert ("POST", "/processar") in verbos
    assert ("DELETE", "/pedidos") in verbos  # ${id} dinâmico é descartado do path_norm


def test_http_call_ignora_nao_http() -> None:
    assert extract_angular_http_calls("foo.get('/x'); array.post(1)") == []


def test_http_call_url_em_variavel_via_harvest() -> None:
    # Código real monta a URL numa variável; o path-literal está solto no arquivo.
    ts = """
    getAll() {
      const url = `${this.base}/v1/pedidos`;
      return this.http.get<any>(url, { headers });
    }
    """
    paths = {c["path_norm"] for c in extract_angular_http_calls(ts)}
    assert "/v1/pedidos" in paths  # colhido mesmo não sendo literal no http.get()


def test_harvest_ignora_import_relativo() -> None:
    # './model' (import) NÃO deve virar datasource; precisa de http + path /seg.
    ts = "import { X } from './pedido.model';\nthis.http.get(u);\nconst p = '/pedidos';"
    paths = {c["path_norm"] for c in extract_angular_http_calls(ts)}
    assert "/pedidos" in paths
    assert "/pedido" not in paths  # o import relativo não entra


def test_pohttpclientservice_harvest() -> None:
    # #100: PoHttpClientService com field fora do padrão `http` (escapa do pass-1);
    # a presença da classe habilita o pass-2 a colher o path REST.
    ts = (
        "import { PoHttpClientService } from '@po-ui/ng-http-client';\n"
        "class S { constructor(private poHttp: PoHttpClientService) {}\n"
        "  listar() { return this.poHttp.get('/api/v1/pedidos'); } }"
    )
    paths = {c["path_norm"] for c in extract_angular_http_calls(ts)}
    assert "/api/v1/pedidos" in paths


def test_pohttp_ausente_nao_colhe_path_solto() -> None:
    # sem http nem PoHttpClientService, path-literal solto NÃO vira datasource.
    ts = "class X { f() { const a = ['/nao/rest']; return a; } }"
    assert extract_angular_http_calls(ts) == []
