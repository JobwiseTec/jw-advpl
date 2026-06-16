"""Comando `mapear` — dossiê determinístico de uma rotina + verificação.

Productiza a "receita determinística" do PoC de harness local (issue #173),
SEM LLM: reúne tudo que o índice sabe de uma rotina (identidade, funções,
tabelas, grafo) e verifica cada símbolo via verify-claims, distinguindo
"fora do dicionário (cobertura)" de símbolo realmente ausente.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.mapear import coletar_dossie, format_mapa, mapear, verificar_dossie


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """Índice sintético: 1 rotina (ZROT) com funções, tabelas e grafo."""
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)

    # fonte com metadados de arch (read=SA1+ZX1, write=ZX1, 2 user funcs)
    c.execute(
        """
        INSERT INTO fontes
          (arquivo, caminho_relativo, source_type, tipo_arquivo, capabilities,
           lines_of_code, namespace, funcoes, user_funcs, pontos_entrada,
           tabelas_ref, write_tables, reclock_tables, includes)
        VALUES ('zrot.prw', 'src/zrot.prw', 'webservice', '.prw', ?,
                320, 'custom.fat', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            json.dumps(["REST_HANDLER"]),
            json.dumps(["ZROT", "ZROTGRAVA", "ZROTVALIDA"]),  # funcoes (total)
            json.dumps(["ZROTGRAVA", "ZROTVALIDA"]),  # user_funcs
            json.dumps([]),  # pontos_entrada
            json.dumps(["SA1", "ZX1"]),  # tabelas_ref (read)
            json.dumps(["ZX1"]),  # write_tables
            json.dumps(["ZX1"]),  # reclock_tables
            json.dumps(["TOTVS.CH", "RESTFUL.CH"]),  # includes
        ),
    )
    # chunks p/ find_function resolver — ZROT e ZROTGRAVA SIM; ZROTVALIDA NÃO
    # (simula user_func declarada no arch mas ausente do índice = ainda "not_found").
    for fn in ("ZROT", "ZROTGRAVA"):
        c.execute(
            "INSERT INTO fonte_chunks (id, arquivo, funcao, funcao_norm, tipo_simbolo) "
            "VALUES (?, 'zrot.prw', ?, ?, 'user_function')",
            (f"zrot.prw::{fn}", fn, fn),
        )
    # SX2: ZX1 é custom indexada; SA1 é padrão TOTVS (não indexada) -> cobertura
    c.execute("INSERT INTO tabelas (codigo, custom) VALUES ('ZX1', 1)")
    # grafo: ZROT chama FWLoadModel; ZOUTRA chama ZROT
    c.execute(
        "INSERT INTO chamadas_funcao "
        "(arquivo_origem, funcao_origem, linha_origem, tipo, destino, destino_norm) "
        "VALUES ('zrot.prw', 'ZROT', 10, 'call', 'FWLoadModel', 'FWLOADMODEL')"
    )
    c.execute(
        "INSERT INTO chamadas_funcao "
        "(arquivo_origem, funcao_origem, linha_origem, tipo, destino, destino_norm) "
        "VALUES ('outra.prw', 'ZOUTRA', 5, 'call', 'ZROT', 'ZROT')"
    )
    c.commit()
    return c


class TestColetarDossie:
    def test_resolve_simbolo_e_monta_identidade(self, conn: sqlite3.Connection) -> None:
        d = coletar_dossie(conn, "ZROT")
        assert d["encontrado"] is True
        assert d["funcao"] == "ZROT"
        assert d["arquivo"] == "zrot.prw"
        assert d["identidade"]["tipo"] == "webservice"
        assert d["identidade"]["loc"] == 320
        assert d["identidade"]["includes"] == ["TOTVS.CH", "RESTFUL.CH"]

    def test_tabelas_e_grafo(self, conn: sqlite3.Connection) -> None:
        d = coletar_dossie(conn, "ZROT")
        assert d["tabelas"]["read"] == ["SA1", "ZX1"]
        assert d["tabelas"]["write"] == ["ZX1"]
        # callees: ZROT -> FWLoadModel ; callers: ZOUTRA -> ZROT
        assert any("FWLoadModel" in c for c in d["grafo"]["callees"])
        assert any("ZOUTRA" in c for c in d["grafo"]["callers"])

    def test_funcoes_estrutura(self, conn: sqlite3.Connection) -> None:
        d = coletar_dossie(conn, "ZROT")
        assert d["funcoes"]["user_funcs"] == ["ZROTGRAVA", "ZROTVALIDA"]
        assert d["funcoes"]["total_funcoes"] == 3

    def test_simbolo_inexistente(self, conn: sqlite3.Connection) -> None:
        d = coletar_dossie(conn, "NAOEXISTE")
        assert d["encontrado"] is False
        assert d["codigo"] == "NAOEXISTE"

    def test_detalhe_expande_callees_por_funcao(self, conn: sqlite3.Connection) -> None:
        # sem detalhe: lista vazia; com detalhe: uma entrada por user_func
        assert coletar_dossie(conn, "ZROT")["detalhe_funcoes"] == []
        d = coletar_dossie(conn, "ZROT", detalhe=True)
        funcs = {e["funcao"] for e in d["detalhe_funcoes"]}
        assert {"ZROTGRAVA", "ZROTVALIDA"} <= funcs


class TestVerificarDossie:
    def test_separa_cobertura_de_simbolo_ausente(self, conn: sqlite3.Connection) -> None:
        v = verificar_dossie(conn, coletar_dossie(conn, "ZROT"))
        # SA1 usada no código mas fora do SX2 indexado -> cobertura (não erro)
        assert "SA1" in v["tabelas_fora_corpus"]
        assert "ZX1" not in v["tabelas_fora_corpus"]  # ZX1 está no SX2
        assert v["sx2_ingerido"] is True
        # ZROTVALIDA é user_func declarada mas ausente do índice -> grave
        assert "ZROTVALIDA" in v["funcoes_not_found"]
        assert "ZROT" not in v["funcoes_not_found"]

    def test_contagem_confirmados(self, conn: sqlite3.Connection) -> None:
        v = verificar_dossie(conn, coletar_dossie(conn, "ZROT"))
        # ZROT, ZROTGRAVA (funcs) + ZX1 (tabela) confirmados = 3
        assert v["exists"] >= 3
        assert v["total"] >= 4  # 3 funcs + 2 tabelas (dedupe)


class TestMapear:
    def test_combina_dossie_e_verificacao(self, conn: sqlite3.Connection) -> None:
        r = mapear(conn, "ZROT")
        assert r["encontrado"] is True
        assert r["dossie"]["funcao"] == "ZROT"
        assert "tabelas_fora_corpus" in r["verificacao"]

    def test_inexistente_curto_circuita(self, conn: sqlite3.Connection) -> None:
        r = mapear(conn, "NAOEXISTE")
        assert r["encontrado"] is False
        assert "dossie" not in r


class TestFormatMapa:
    def test_md_traz_identidade_tabelas_e_grafo(self, conn: sqlite3.Connection) -> None:
        md = format_mapa(mapear(conn, "ZROT"))
        assert "ZROT" in md
        assert "zrot.prw" in md
        assert "webservice" in md
        assert "320" in md
        assert "SA1" in md and "ZX1" in md
        assert "FWLoadModel" in md  # callee
        assert "ZOUTRA" in md  # caller

    def test_md_marca_cobertura_e_ausencia(self, conn: sqlite3.Connection) -> None:
        md = format_mapa(mapear(conn, "ZROT"))
        # 3 confirmados (ZROT, ZROTGRAVA, ZX1) de 5 símbolos
        assert "3/5" in md
        # SA1 marcada como cobertura; ZROTVALIDA como função ausente
        assert "SA1" in md
        assert "ZROTVALIDA" in md

    def test_md_tem_disclaimer_anti_alucinacao(self, conn: sqlite3.Connection) -> None:
        # a honestidade que prometi na issue: verifica símbolo, não sentido
        md = format_mapa(mapear(conn, "ZROT")).lower()
        assert "negócio" in md or "domínio" in md or "fonte" in md

    def test_md_inexistente(self, conn: sqlite3.Connection) -> None:
        md = format_mapa(mapear(conn, "NAOEXISTE"))
        assert "NAOEXISTE" in md
        assert "não encontr" in md.lower()
