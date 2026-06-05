"""Testes de plugadvpl/query.py — funções de consulta sobre DB ingerido."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugadvpl.ingest import ingest
from plugadvpl.query import (
    _glob_to_like,
    _writable_expected,
    arch,
    callees,
    callers,
    doctor_diagnostics,
    family,
    find_any,
    find_file,
    find_function,
    grep_fts,
    header_doc,
    lint_query,
    param_query,
    stale_files,
    status,
    tables_query,
)


class TestWritableExpected:
    """Valor gravável no INI sugerido a partir do ``expected`` do catálogo."""

    def test_scalar_expected_passes_through(self) -> None:
        assert _writable_expected("1", "qualquer guidance") == "1"

    def test_empty_expected_without_recomendado_is_placeholder(self) -> None:
        """Obrigatória sem valor canônico nem ``Recomendado:`` → ``<CONFIGURAR>``
        (a chave crítica é injetada como placeholder)."""
        assert _writable_expected("", "Ref: https://tdn.totvs.com/x") == "<CONFIGURAR>"

    def test_empty_expected_uses_recomendado_when_present(self) -> None:
        """Obrigatória sem ``expected`` mas com ``Recomendado: X`` no guidance
        (ex. caminho de certificado) usa esse valor."""
        out = _writable_expected(
            "", "Recomendado: C:\\TSS\\certs\\000001_all.pem | Chave OBRIGATÓRIA."
        )
        assert out == "C:\\TSS\\certs\\000001_all.pem"

    def test_value_in_uses_recomendado_from_guidance(self) -> None:
        """``expected`` com ``|`` é conjunto value_in (não gravável); usa o
        ``Recomendado:`` do fix_guidance."""
        out = _writable_expected(
            "1|Maior|Menor",
            "Recomendado: 10 | Valores aceitos: 1, Maior, Menor | Chave OBRIGATÓRIA.",
        )
        assert out == "10"

    def test_value_in_without_recomendado_falls_back_to_placeholder(self) -> None:
        assert _writable_expected("a|b|c", "sem recomendacao aqui") == "<CONFIGURAR>"

    def test_recomendado_trailing_period_stripped(self) -> None:
        """Guidance é texto livre; ``Recomendado: 10.`` (com ponto final) não pode
        virar valor ``10.`` no INI — a pontuação de fim de frase é removida."""
        out = _writable_expected(
            "",
            "Chave que define o tamanho máximo de string (MB). Recomendado: 10. | Ref: x",
        )
        assert out == "10"

    def test_recomendado_only_punctuation_falls_back(self) -> None:
        """Se sobra só pontuação após limpar, cai no placeholder."""
        assert _writable_expected("", "Recomendado: . | Ref: x") == "<CONFIGURAR>"


@pytest.fixture
def db_with_three_sources(tmp_path: Path) -> tuple[Path, sqlite3.Connection]:
    """Ingere 3 fontes sintéticos e retorna ``(root, conn)``.

    Fontes:

    - ``FATA050.prw`` — usa RecLock em SC5 (write/reclock).
    - ``MATA010.prw`` — chama FATA050 + SuperGetMV(MV_LOCALIZA).
    - ``WSReg.tlpp`` — WS com HttpPost.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "FATA050.prw").write_bytes(
        b"User Function FATA050()\n"
        b'  DbSelectArea("SC5")\n'
        b'  RecLock("SC5", .T.)\n'
        b'  Replace C5_NUM With "001"\n'
        b"  MsUnlock()\n"
        b"Return .T.\n"
    )
    (src / "MATA010.prw").write_bytes(
        b"User Function MATA010()\n"
        b'  Local cMV := SuperGetMV("MV_LOCALIZA", .F., "")\n'
        b"  U_FATA050()\n"
        b"Return\n"
    )
    (src / "WSReg.tlpp").write_bytes(
        b'Namespace api\nUser Function WSReg()\n  HttpPost("http://api.foo/x", oJson)\nReturn\n'
    )
    ingest(src, workers=0)
    conn = sqlite3.connect(str(src / ".plugadvpl" / "index.db"))
    return src, conn


class TestHeaderDocIngest:
    """Integração #63: ingest popula fonte_header_doc e arch anexa com flag."""

    @pytest.fixture
    def db_with_header(self, tmp_path: Path) -> sqlite3.Connection:
        src = tmp_path / "src"
        src.mkdir()
        # fonte COM header declarativo (nomes ficticios)
        (src / "ABC0001.prw").write_bytes(
            b"/*\n"
            b"Programa............: ABC0001\n"
            b"Autor...............: Fulano de Tal\n"
            b"Descricao/Objetivo..: Rotina exemplo\n"
            b"Uso.................: Empresa Exemplo\n"
            b"*/\n"
            b"User Function ABC0001()\nReturn\n"
        )
        # fonte SEM header
        (src / "ABC0002.prw").write_bytes(b"User Function ABC0002()\n  Local nX := 1\nReturn\n")
        ingest(src, workers=0)
        return sqlite3.connect(str(src / ".plugadvpl" / "index.db"))

    def test_header_doc_populado(self, db_with_header: sqlite3.Connection) -> None:
        h = header_doc(db_with_header, "ABC0001.prw")
        assert h["programa"] == "ABC0001"
        assert h["autor"] == "Fulano de Tal"
        assert h["descricao"] == "Rotina exemplo"
        assert h["uso"] == "Empresa Exemplo"

    def test_fonte_sem_header_retorna_vazio(self, db_with_header: sqlite3.Connection) -> None:
        assert header_doc(db_with_header, "ABC0002.prw") == {}

    def test_arch_sem_flag_nao_inclui_header(self, db_with_header: sqlite3.Connection) -> None:
        rows = arch(db_with_header, "ABC0001.prw")
        assert "header_doc" not in rows[0]

    def test_arch_com_flag_inclui_header(self, db_with_header: sqlite3.Connection) -> None:
        rows = arch(db_with_header, "ABC0001.prw", include_header=True)
        assert rows[0]["header_doc"]["autor"] == "Fulano de Tal"


class TestGlobToLike:
    def test_estrela_vira_porcento(self) -> None:
        assert _glob_to_like("MOD12*") == "MOD12%"

    def test_interrogacao_vira_underscore(self) -> None:
        assert _glob_to_like("A?B") == "A_B"

    def test_sem_glob_retorna_none(self) -> None:
        assert _glob_to_like("plain") is None

    def test_escapa_curinga_literal(self) -> None:
        assert _glob_to_like("a%b*") == "a\\%b%"


class TestFamilyAndGlob:
    """#62: comando family + glob no find."""

    @pytest.fixture
    def db_family(self, tmp_path: Path) -> sqlite3.Connection:
        src = tmp_path / "src"
        src.mkdir()
        (src / "ABC100.prw").write_bytes(
            b"/*\nPrograma: ABC100\nDescricao: Cadastro base\n*/\nUser Function ABC100()\nReturn\n"
        )
        (src / "ABC101.prw").write_bytes(b"User Function ABC101()\nReturn\n")
        (src / "ABC102.prw").write_bytes(b"User Function ABC102()\nReturn\n")
        (src / "XYZ900.prw").write_bytes(b"User Function XYZ900()\nReturn\n")
        ingest(src, workers=0)
        return sqlite3.connect(str(src / ".plugadvpl" / "index.db"))

    def test_family_por_prefixo(self, db_family: sqlite3.Connection) -> None:
        nomes = sorted(r["arquivo"] for r in family(db_family, "ABC"))
        assert nomes == ["ABC100.prw", "ABC101.prw", "ABC102.prw"]

    def test_family_join_descricao_do_header(self, db_family: sqlite3.Connection) -> None:
        rows = family(db_family, "ABC100")
        assert rows[0]["descricao"] == "Cadastro base"

    def test_family_sem_header_descricao_vazia(self, db_family: sqlite3.Connection) -> None:
        rows = family(db_family, "ABC101")
        assert rows[0]["descricao"] == ""

    def test_family_inclui_source_type_e_loc(self, db_family: sqlite3.Connection) -> None:
        rows = family(db_family, "ABC100")
        assert rows[0]["source_type"] == "user_function"
        assert rows[0]["lines_of_code"] > 0

    def test_family_glob(self, db_family: sqlite3.Connection) -> None:
        assert len(family(db_family, "ABC10*")) == 3

    def test_family_glob_question_e_match_exato(self, db_family: sqlite3.Connection) -> None:
        # 'ABC10?' = ABC10 + 1 char (match exato): nao casa 'ABC100.prw' (tem .prw)
        assert family(db_family, "ABC10?") == []

    def test_family_prefixo_inexistente(self, db_family: sqlite3.Connection) -> None:
        assert family(db_family, "ZZZ") == []

    def test_find_file_glob_ancorado(self, db_family: sqlite3.Connection) -> None:
        rows = find_file(db_family, "ABC10*")
        assert len(rows) == 3
        assert all(r["arquivo"].startswith("ABC10") for r in rows)

    def test_find_file_glob_question(self, db_family: sqlite3.Connection) -> None:
        assert len(find_file(db_family, "ABC10?.prw")) == 3

    def test_find_file_substring_sem_glob(self, db_family: sqlite3.Connection) -> None:
        assert len(find_file(db_family, "ABC")) == 3


class TestFindFunction:
    def test_finds_user_function_case_insensitive(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = find_function(conn, "fata050")
        assert len(rows) >= 1
        assert rows[0]["arquivo"] == "FATA050.prw"
        assert rows[0]["funcao"].upper() == "FATA050"

    def test_returns_empty_when_unknown(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        assert find_function(conn, "Inexistente9999") == []


class TestFindFile:
    def test_finds_by_basename_fragment(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = find_file(conn, "WSReg")
        assert any(r["arquivo"] == "WSReg.tlpp" for r in rows)


class TestFindAny:
    def test_composed_strategy_prefers_function(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = find_any(conn, "FATA050")
        # Função tem prioridade — kind=function.
        assert rows
        assert rows[0]["_kind"] == "function"


class TestCallers:
    def test_callers_of_fata050(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = callers(conn, "FATA050")
        assert any(r["arquivo"] == "MATA010.prw" for r in rows)


class TestCallees:
    def test_callees_of_file(self, db_with_three_sources: tuple[Path, sqlite3.Connection]) -> None:
        _, conn = db_with_three_sources
        # `funcao_origem` está vazio no MVP — fallback via basename.
        rows = callees(conn, "MATA010.prw")
        destinos = {r["destino"] for r in rows}
        assert "FATA050" in destinos

    def test_callees_resolves_innermost_chunk_with_nested_methods(self, tmp_path: Path) -> None:
        """v0.3.22 — Bug #19 do QA round 2: docstring v0.3.15 fala de
        "chunk MAIS INTERNO em caso de nesting (Class > Method > Static)"
        mas test era happy-path. Aqui forcamos cenario com 2 funcoes
        adjacentes — Method da classe + Static helper — e validamos que
        chamadas em cada uma sao corretamente atribuidas.
        """
        from plugadvpl.db import apply_migrations, init_meta, open_db, seed_lookups
        from plugadvpl.ingest import ingest as do_ingest
        from plugadvpl.query import callees as cq

        src = tmp_path / "AbcA.prw"
        src.write_text(
            "Method M1() Class A\n"  # 1
            "    Local x := U_ExtA()\n"  # 2 — chamada DENTRO de M1
            "Return\n"  # 3
            "\n"  # 4
            "Static Function helper()\n"  # 5
            "    Local y := U_ExtB()\n"  # 6 — chamada DENTRO de helper
            "Return\n",  # 7
            encoding="cp1252",
        )
        do_ingest(tmp_path, workers=0)

        db = tmp_path / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(str(db))
        try:
            # callees("M1") deve achar U_ExtA (chamada na linha 2 dentro de M1).
            rows_m1 = cq(conn, "M1")
            destinos_m1 = {r["destino"].upper() for r in rows_m1}
            assert "EXTA" in destinos_m1, (
                f"callees('M1') deveria achar U_ExtA. destinos={destinos_m1}"
            )
            # callees("helper") deve achar U_ExtB (chamada na linha 6 dentro de helper).
            rows_h = cq(conn, "helper")
            destinos_h = {r["destino"].upper() for r in rows_h}
            assert "EXTB" in destinos_h, (
                f"callees('helper') deveria achar U_ExtB. destinos={destinos_h}"
            )
            # E validamos isolamento: M1 NAO deve chamar U_ExtB e vice-versa.
            assert "EXTB" not in destinos_m1
            assert "EXTA" not in destinos_h
        finally:
            conn.close()

    def test_callees_by_function_name_works(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        """v0.3.15 — Bug #8 do QA report: ingest deixava funcao_origem='' em
        TODOS os 30k+ registros, então `callees <nome_funcao>` retornava vazio
        sempre. A função-pai deve ser resolvida via lookup em fonte_chunks
        (qual chunk contém linha_origem).

        Fixture: MATA010 contém uma função MATA010 que chama FATA050. Buscar
        callees de MATA010 (por nome de função, NÃO por basename) deve retornar
        FATA050."""
        _, conn = db_with_three_sources
        rows = callees(conn, "MATA010")  # nome da função, sem .prw
        destinos = {r["destino"] for r in rows}
        assert "FATA050" in destinos, (
            f"callees('MATA010') deveria achar FATA050. "
            f"Encontrou: {destinos}. Provavelmente funcao_origem ainda esta vazio."
        )


class TestTablesQuery:
    def test_query_table_sc5_returns_fata050(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = tables_query(conn, "SC5")
        assert any(r["arquivo"] == "FATA050.prw" for r in rows)

    def test_filter_by_mode_write(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = tables_query(conn, "SC5", modo="write")
        # Quem escreve em SC5 ⇒ pelo menos FATA050.
        assert all(r["modo"] == "write" for r in rows)


class TestParamQuery:
    def test_param_mv_localiza(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = param_query(conn, "MV_LOCALIZA")
        assert any(r["arquivo"] == "MATA010.prw" for r in rows)


class TestArch:
    def test_arch_returns_summary_dict(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = arch(conn, "FATA050.prw")
        assert len(rows) == 1
        a = rows[0]
        assert a["arquivo"] == "FATA050.prw"
        # SC5 deve aparecer em alguma lista de tabelas.
        tabs = a["tabelas_read"] + a["tabelas_write"] + a["tabelas_reclock"]
        assert "SC5" in tabs

    def test_arch_missing_file_returns_empty(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        assert arch(conn, "naoexiste.prw") == []


class TestLintQuery:
    def test_lint_all(self, db_with_three_sources: tuple[Path, sqlite3.Connection]) -> None:
        _, conn = db_with_three_sources
        rows = lint_query(conn)
        # Pode estar vazio em fontes simples; só deve retornar list.
        assert isinstance(rows, list)

    def test_lint_filter_by_file(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = lint_query(conn, arquivo="FATA050.prw")
        assert all(r["arquivo"] == "FATA050.prw" for r in rows)

    def test_lint_query_exposes_sonar_rules_when_populated(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        """Finding deve trazer sonar_rules como lista parseada da regra correspondente."""
        import json

        _, conn = db_with_three_sources
        conn.execute(
            "UPDATE lint_rules SET sonar_rules = ? WHERE regra_id = ?",
            (json.dumps(["BG1000"]), "BP-001"),
        )
        conn.execute(
            "INSERT INTO lint_findings "
            "(arquivo, funcao, linha, regra_id, severidade, snippet, sugestao_fix) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("FAKE.prw", "FakeFn", 1, "BP-001", "critical", "snip", "fix"),
        )
        conn.commit()
        rows = lint_query(conn, regra_id="BP-001")
        finding = next(r for r in rows if r["arquivo"] == "FAKE.prw")
        assert finding["sonar_rules"] == ["BG1000"]

    def test_lint_query_returns_empty_list_when_sonar_rules_unset(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        """Regra sem mapeamento Sonar deve aparecer como sonar_rules=[], não None nem ''."""
        _, conn = db_with_three_sources
        conn.execute(
            "INSERT INTO lint_findings "
            "(arquivo, funcao, linha, regra_id, severidade, snippet, sugestao_fix) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("FAKE2.prw", "FakeFn", 1, "BP-002", "critical", "snip", "fix"),
        )
        conn.commit()
        rows = lint_query(conn, regra_id="BP-002")
        finding = next(r for r in rows if r["arquivo"] == "FAKE2.prw")
        assert finding["sonar_rules"] == []


class TestStatus:
    def test_status_has_versions(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        src, conn = db_with_three_sources
        rows = status(conn, str(src))
        assert len(rows) == 1
        s = rows[0]
        assert s["plugadvpl_version"]
        assert s["total_arquivos"] == "3"

    def test_status_runtime_version_field_when_passed(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        """v0.3.12: status expõe runtime_version (binário rodando AGORA) — chave
        sempre presente quando o caller passa, e fica `None` se não passar (back-compat)."""
        src, conn = db_with_three_sources
        rows_with = status(conn, str(src), runtime_version="0.3.12")
        assert rows_with[0]["runtime_version"] == "0.3.12"
        rows_without = status(conn, str(src))
        assert "runtime_version" in rows_without[0]
        assert rows_without[0]["runtime_version"] is None

    def test_status_runtime_version_diverges_from_stored(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        """Caso real do feedback: índice gravado em 0.2.0, binário atual 0.3.11.
        O query devolve os dois lados — o aviso amarelo é responsabilidade da CLI."""
        src, conn = db_with_three_sources
        # db_with_three_sources grava plugadvpl_version via init_meta — vamos forçar
        # algo antigo pra simular upgrade do binário sem reingest.
        from plugadvpl.db import set_meta

        set_meta(conn, "plugadvpl_version", "0.2.0")
        rows = status(conn, str(src), runtime_version="0.3.11")
        s = rows[0]
        assert s["plugadvpl_version"] == "0.2.0"
        assert s["runtime_version"] == "0.3.11"
        # Divergência detectável pelo caller via comparação simples.
        assert s["runtime_version"] != s["plugadvpl_version"]


class TestStaleFiles:
    def test_stale_detection(
        self,
        db_with_three_sources: tuple[Path, sqlite3.Connection],
    ) -> None:
        src, conn = db_with_three_sources
        # Simula mtime maior no filesystem — todos viram stale.
        fs_state = {
            f.name: f.stat().st_mtime_ns + 10_000_000_000
            for f in (src / "FATA050.prw", src / "MATA010.prw", src / "WSReg.tlpp")
        }
        rows = stale_files(conn, fs_state)
        assert all(r["estado"] in {"stale", "new", "deleted"} for r in rows)
        assert any(r["estado"] == "stale" for r in rows)

    def test_stale_detects_new(
        self,
        db_with_three_sources: tuple[Path, sqlite3.Connection],
    ) -> None:
        _, conn = db_with_three_sources
        fs_state = {"NovoArquivo.prw": 99999}
        rows = stale_files(conn, fs_state)
        # Os 3 do DB viram "deleted" + NovoArquivo "new".
        assert any(r["arquivo"] == "NovoArquivo.prw" and r["estado"] == "new" for r in rows)
        assert any(r["estado"] == "deleted" for r in rows)


class TestDoctor:
    def test_doctor_returns_4_checks(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = doctor_diagnostics(conn)
        checks = {r["check"] for r in rows}
        assert {
            "encoding_missing",
            "orphan_chunks",
            "fts_sync",
            "lookups_loaded",
            "basename_collisions",
        }.issubset(checks)
        # Após ingest limpo, fts_sync deve estar ok.
        fts = next(r for r in rows if r["check"] == "fts_sync")
        assert fts["status"] == "ok"
        # Após ingest sem colisao, basename_collisions deve estar ok.
        coll = next(r for r in rows if r["check"] == "basename_collisions")
        assert coll["status"] == "ok"
        assert coll["count"] == 0

    def test_doctor_basename_collision_warn_v0_9_5(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        """v0.9.5 (QA PERF 2026-05-18 #2): com meta basename_collisions
        populado, doctor reporta status=warn com contagem e exemplos."""
        import json as _json

        _, conn = db_with_three_sources
        conn.execute(
            "UPDATE meta SET valor=? WHERE chave='basename_collisions'",
            (
                _json.dumps(
                    {
                        "mata010.prw": ["/mod1/MATA010.prw", "/mod2/MATA010.prw"],
                        "fata050.prw": [
                            "/cli/FATA050.prw",
                            "/std/FATA050.prw",
                            "/bkp/FATA050.prw",
                        ],
                    }
                ),
            ),
        )
        conn.commit()
        rows = doctor_diagnostics(conn)
        coll = next(r for r in rows if r["check"] == "basename_collisions")
        assert coll["status"] == "warn"
        assert coll["count"] == 2
        # detail menciona as duas chaves
        assert "mata010.prw" in coll["detail"]


class TestGrep:
    def test_grep_fts_finds_token(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = grep_fts(conn, "RecLock", mode="fts", limit=20)
        assert any(r["arquivo"] == "FATA050.prw" for r in rows)

    def test_grep_literal_substring(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = grep_fts(conn, "C5_NUM", mode="literal", limit=20)
        assert any(r["arquivo"] == "FATA050.prw" for r in rows)

    def test_grep_identifier_strips_u_prefix(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        _, conn = db_with_three_sources
        rows = grep_fts(conn, "U_FATA050", mode="identifier", limit=20)
        # 'FATA050' (sem U_) deve aparecer no conteúdo de MATA010 ou FATA050.
        assert any("FATA050" in (r["snippet"] or "").upper() for r in rows)

    def test_grep_literal_uses_trigram_v0_9_2(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        """v0.9.2 (QA PERF #1): pattern >=3 chars passa pelo trigram FTS
        pré-filtro + LIKE confirmador. Resultado equivalente ao LIKE puro
        anterior, mas com I/O drasticamente menor em bases grandes.

        Assertion mínima: o caminho novo continua retornando o mesmo match.
        """
        _, conn = db_with_three_sources
        rows = grep_fts(conn, "C5_NUM", mode="literal", limit=20)
        assert any(r["arquivo"] == "FATA050.prw" for r in rows)
        # Snippet deve conter o pattern (LIKE pós-filtro garante exact substring)
        assert all("C5_NUM" in (r["snippet"] or "") for r in rows)

    def test_grep_literal_short_pattern_fallback_v0_9_2(
        self, db_with_three_sources: tuple[Path, sqlite3.Connection]
    ) -> None:
        """v0.9.2: pattern <3 chars não usa trigram (não há trigrams nesse
        tamanho); faz LIKE puro sem erro."""
        _, conn = db_with_three_sources
        # Pattern de 1-2 chars deve funcionar (cair no else do branch)
        rows = grep_fts(conn, "If", mode="literal", limit=5)
        # Não estoura erro; pode achar ou não — o que importa é não crashear
        assert isinstance(rows, list)
