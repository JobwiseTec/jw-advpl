from __future__ import annotations

from plugadvpl.parsing.poui import parse_poui_package_json


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
