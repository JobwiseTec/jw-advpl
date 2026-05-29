"""Integration tests do typer CLI (plugadvpl/cli.py).

Usamos ``typer.testing.CliRunner`` para invocar subcomandos contra um
diretório temporário com 3 fontes ADVPL sintéticos. Cada teste cobre
1 subcomando ponta-a-ponta (parser -> DB -> render).
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from plugadvpl import __version__
from plugadvpl.cli import app


@pytest.fixture
def synthetic_project(tmp_path: Path) -> Path:
    """Cria 3 fontes ADVPL em ``tmp_path/src``."""
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
        b"Namespace api\n"
        b"User Function WSReg()\n"
        b'  HttpPost("http://api.foo/x", oJson)\n'
        b"Return\n"
    )
    return src


@pytest.fixture
def runner() -> CliRunner:
    """Click >=8.2 já separa stdout/stderr por padrão."""
    return CliRunner()


@pytest.fixture
def indexed_project(synthetic_project: Path, runner: CliRunner) -> Path:
    """Project já passou por ``init`` + ``ingest``."""
    r1 = runner.invoke(app, ["--root", str(synthetic_project), "init"])
    assert r1.exit_code == 0, r1.stderr or r1.stdout
    r2 = runner.invoke(app, ["--root", str(synthetic_project), "ingest"])
    assert r2.exit_code == 0, r2.stderr or r2.stdout
    return synthetic_project


class TestVersion:
    def test_version_subcommand(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_version_global_flag_long(self, runner: CliRunner) -> None:
        """v0.3.12: `plugadvpl --version` (eager, padrão UNIX) — funciona sem subcomando."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_version_global_flag_short(self, runner: CliRunner) -> None:
        """v0.3.12: short `-V` também (não conflita com `-v` se algum subcomando usar)."""
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert __version__ in result.stdout


class TestGlobalFlagPositioning:
    def test_misplaced_global_flag_shows_helpful_hint(
        self, indexed_project: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """v0.3.15 — Bug #2 do QA report: usuario rodava
        `plugadvpl status --limit 20` e recebia "No such option: --limit"
        sem indicacao de que a flag eh global e precisa vir antes do
        subcomando. Agora `main()` detecta o caso comum e adiciona hint
        amarelo em stderr APOS o erro do click.

        Testamos via main() (nao runner.invoke) porque o wrapper da hint
        vive em main(), nao em app — o runner bypassa main()."""
        from plugadvpl.cli import main as cli_main

        monkeypatch.setattr(
            "sys.argv",
            ["plugadvpl", "--root", str(indexed_project), "status", "--limit", "20"],
        )
        with pytest.raises(SystemExit) as exc_info:
            cli_main()
        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        # Hint vai pra stderr APOS o erro nativo do click.
        assert "--limit" in captured.err
        assert "global" in captured.err.lower() or "antes" in captured.err.lower()

    def test_misplaced_subcommand_flag_shows_inverse_hint(
        self,
        indexed_project: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """v0.3.22 — Bug #18 do QA round 2: caso inverso. Usuario roda
        `plugadvpl --workers 8 ingest` (achando que --workers eh global)
        e recebe `No such option: --workers` cru. Agora detectamos e
        sugerimos posicionar DEPOIS do subcomando."""
        from plugadvpl.cli import main as cli_main

        monkeypatch.setattr(
            "sys.argv",
            ["plugadvpl", "--root", str(indexed_project), "--workers", "8", "ingest"],
        )
        with pytest.raises(SystemExit) as exc_info:
            cli_main()
        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert "--workers" in captured.err
        assert "subcomando" in captured.err.lower() or "depois" in captured.err.lower()


class TestHelp:
    def test_help_lists_all_subcommands(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # 14 comandos do MVP + 4 novos do v0.3.0 (ingest-sx, impacto, gatilho, sx-status) = 18.
        for cmd in (
            "version", "init", "ingest", "reindex", "status",
            "find", "callers", "callees", "tables", "param",
            "arch", "lint", "doctor", "grep",
            "ingest-sx", "impacto", "gatilho", "sx-status",
        ):
            assert cmd in result.stdout


class TestInit:
    @pytest.fixture(autouse=True)
    def _isolate_cursor_home(
        self, tmp_path_factory: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Isola Path.home pra cada teste do TestInit (v0.16.2+).

        Sem isso, init() chama install_cursor_rules() que detecta ~/.cursor/
        real do dev rodando localmente — escreveria rules em ~/.cursor/rules/
        do dev (side-effect, não falha de teste, mas poluente). Aponta
        Path.home pra tmp diretório limpo e neutraliza shutil.which.
        """
        fake_home = tmp_path_factory.mktemp("isolated_home_init")
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr(
            "plugadvpl.cursor_rules.shutil.which", lambda _: None
        )

    def test_init_creates_db_and_claude_md(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0, result.stderr or result.stdout
        db = synthetic_project / ".plugadvpl" / "index.db"
        assert db.exists()
        claude_md = synthetic_project / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text(encoding="utf-8")
        assert "<!-- BEGIN plugadvpl -->" in content
        assert "<!-- END plugadvpl -->" in content

    def test_init_is_idempotent(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        claude_md = synthetic_project / "CLAUDE.md"
        content = claude_md.read_text(encoding="utf-8")
        # Não deve duplicar o fragment.
        assert content.count("<!-- BEGIN plugadvpl -->") == 1

    def test_init_updates_gitignore_when_exists(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        gi = synthetic_project / ".gitignore"
        gi.write_text("*.pyc\n", encoding="utf-8")
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert ".plugadvpl/" in gi.read_text(encoding="utf-8")

    def test_init_creates_agents_md_for_multi_agent(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        """v0.16.1 — init escreve AGENTS.md gêmeo do CLAUDE.md.

        AGENTS.md é o padrão usado por Cursor, GitHub Copilot, Codex e outros
        agentes que não consomem CLAUDE.md. Conteúdo idêntico — apenas o nome
        muda pra atender cada plataforma.
        """
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0, result.stderr or result.stdout
        agents_md = synthetic_project / "AGENTS.md"
        assert agents_md.exists()
        content = agents_md.read_text(encoding="utf-8")
        assert "<!-- BEGIN plugadvpl -->" in content
        assert "<!-- END plugadvpl -->" in content

    def test_init_agents_md_fragment_mirrors_claude_md(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        """Fragment de plugadvpl em CLAUDE.md e AGENTS.md devem ser idênticos."""
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        claude = (synthetic_project / "CLAUDE.md").read_text(encoding="utf-8")
        agents = (synthetic_project / "AGENTS.md").read_text(encoding="utf-8")
        # Extrai a janela BEGIN..END de cada arquivo e compara.
        def _fragment(text: str) -> str:
            start = text.index("<!-- BEGIN plugadvpl -->")
            end = text.index("<!-- END plugadvpl -->") + len("<!-- END plugadvpl -->")
            return text[start:end]
        assert _fragment(claude) == _fragment(agents)

    def test_init_agents_md_is_idempotent(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        """Segundo init não duplica fragment no AGENTS.md."""
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        content = (synthetic_project / "AGENTS.md").read_text(encoding="utf-8")
        assert content.count("<!-- BEGIN plugadvpl -->") == 1


class TestInitCursorRules:
    """v0.16.2 — init detecta Cursor e gera .cursor/rules/*.mdc."""

    def test_skips_cursor_when_no_signals(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem ~/.cursor/, sem .cursor/ no projeto, sem cursor no PATH → no-op."""
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert not (synthetic_project / ".cursor").exists()
        assert "Cursor rules" not in result.stdout

    def test_installs_locals_when_project_has_cursor_dir(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.cursor/` existe no projeto → init cria 52 locais."""
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        rules = list((synthetic_project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(rules) == 52
        assert "Cursor rules" in result.stdout

    def test_no_cursor_flag_skips_everything(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`init --no-cursor` → zero efeito mesmo com sinais presentes."""
        fake_home = synthetic_project.parent / "fake_home"
        (fake_home / ".cursor" / "rules").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        (synthetic_project / ".cursor").mkdir()
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "init", "--no-cursor"]
        )
        assert result.exit_code == 0
        assert not (synthetic_project / ".cursor" / "rules").exists()
        assert not (fake_home / ".cursor" / "rules" / "plugadvpl.mdc").exists()
        assert "Cursor rules" not in result.stdout

    def test_quiet_suppresses_cursor_message(
        self, synthetic_project: Path, runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "--quiet", "init"]
        )
        assert result.exit_code == 0
        assert "Cursor rules" not in result.stdout
        # Verifica que rules foram criadas mesmo em quiet
        rules = list((synthetic_project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(rules) == 52


class TestIngest:
    def test_ingest_after_init(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "--format", "json", "ingest"]
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["total"] == 1  # 1 summary row
        assert payload["rows"][0]["ok"] == 3

    def test_ingest_incremental_warns_when_lookups_changed(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """v0.3.13 — pegadinha do feedback real: após `uv tool upgrade` com novas
        regras de lint, `ingest --incremental` pula arquivos cujo mtime não mudou
        e essas regras NÃO são re-aplicadas. Avisa em stderr orientando
        `--no-incremental`. Simulamos forçando um lookup_bundle_hash antigo."""
        db = indexed_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                "UPDATE meta SET valor='hash-from-old-version' WHERE chave='lookup_bundle_hash'"
            )
            conn.commit()
        finally:
            conn.close()

        # Re-ingest incremental — todos os 3 arquivos têm mtime antigo, serão skipped.
        result = runner.invoke(
            app, ["--root", str(indexed_project), "ingest"]
        )
        assert result.exit_code == 0
        assert "Lookups" in result.stderr
        assert "--no-incremental" in result.stderr
        assert "ingest" in result.stderr

    def test_ingest_no_incremental_no_warning_even_with_hash_change(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """Em --no-incremental tudo é re-parseado de qualquer jeito → não há
        pegadinha pra avisar."""
        db = indexed_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                "UPDATE meta SET valor='hash-from-old-version' WHERE chave='lookup_bundle_hash'"
            )
            conn.commit()
        finally:
            conn.close()

        result = runner.invoke(
            app, ["--root", str(indexed_project), "ingest", "--no-incremental"]
        )
        assert result.exit_code == 0
        assert "--no-incremental" not in result.stderr  # sem aviso

    def test_ingest_incremental_no_warning_when_hash_unchanged(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """Caso normal: nada mudou → sem aviso amarelo."""
        result = runner.invoke(
            app, ["--root", str(indexed_project), "ingest"]
        )
        assert result.exit_code == 0
        assert "Lookups" not in result.stderr

    def test_ingest_warning_suppressed_by_quiet(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """`--quiet` suprime o aviso de divergência de lookups (consistente com
        a política de outras decorações)."""
        db = indexed_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                "UPDATE meta SET valor='hash-from-old-version' WHERE chave='lookup_bundle_hash'"
            )
            conn.commit()
        finally:
            conn.close()

        result = runner.invoke(
            app, ["--root", str(indexed_project), "--quiet", "ingest"]
        )
        assert result.exit_code == 0
        assert "Lookups" not in result.stderr


class TestFind:
    def test_find_function(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "--format", "json", "find", "FATA050"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        # Pode ter múltiplos chunks (header + main); pelo menos 1.
        assert payload["total"] >= 1
        assert any("FATA050" in (r.get("arquivo") or "") for r in payload["rows"])


class TestCallers:
    def test_callers_of_fata050(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "--format", "json", "callers", "FATA050"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert any(r["arquivo"] == "MATA010.prw" for r in payload["rows"])


class TestTables:
    def test_tables_sc5(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "--format", "json", "tables", "SC5"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert any(r["arquivo"] == "FATA050.prw" for r in payload["rows"])


class TestParam:
    def test_param_mv_localiza(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            [
                "--root", str(indexed_project), "--format", "json",
                "param", "MV_LOCALIZA",
            ],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert any(r["arquivo"] == "MATA010.prw" for r in payload["rows"])


class TestArch:
    def test_arch_fata050(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            [
                "--root", str(indexed_project), "--format", "json",
                "arch", "FATA050.prw",
            ],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["rows"][0]["arquivo"] == "FATA050.prw"

    def test_arch_missing_exits_1(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "arch", "naoexiste.prw"],
        )
        assert result.exit_code == 1


class TestStatus:
    def test_status_reports_indexed_files(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app, ["--root", str(indexed_project), "--format", "json", "status"]
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["rows"][0]["total_arquivos"] == "3"

    def test_status_includes_runtime_version(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """v0.3.12: status sempre traz `runtime_version` = __version__ do binário."""
        result = runner.invoke(
            app, ["--root", str(indexed_project), "--format", "json", "status"]
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["rows"][0]["runtime_version"] == __version__

    def test_status_warns_when_claude_md_fragment_is_stale(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """v0.3.23 — Bug #1 do QA round 3: usuario com projeto init'd numa
        versao antiga (ex: v0.3.0) tem fragment do CLAUDE.md desatualizado
        (cita `--fts/--literal/--identifier` em vez de `-m fts|literal|identifier`).
        Status agora detecta marker de versao no fragment e avisa quando
        nao bate com runtime_version, orientando re-rodar `init`."""
        # Simula fragment de versao antiga: re-grava CLAUDE.md com marker velho.
        claude_md = indexed_project / "CLAUDE.md"
        content = claude_md.read_text(encoding="utf-8")
        # Substitui o marker pra versao antiga.
        content = re.sub(
            r"<!-- plugadvpl-fragment-version: [^>]+ -->",
            "<!-- plugadvpl-fragment-version: 0.0.1-old -->",
            content,
        )
        claude_md.write_text(content, encoding="utf-8")

        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        assert result.exit_code == 0
        assert "fragment" in result.stderr.lower()
        assert "0.0.1-old" in result.stderr or "init" in result.stderr.lower()

    def test_status_no_fragment_warning_when_marker_matches(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """Marker fresh do init recente — nao avisa."""
        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        assert result.exit_code == 0
        assert "fragment" not in result.stderr.lower()

    def test_status_warns_when_claude_md_has_no_fragment_marker(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """Fragment pre-v0.3.23 nao tem marker. Status deve avisar tambem."""
        claude_md = indexed_project / "CLAUDE.md"
        content = claude_md.read_text(encoding="utf-8")
        # Remove marker simulando fragment antigo (sem versionamento).
        content = re.sub(
            r"<!-- plugadvpl-fragment-version: [^>]+ -->\n?", "", content,
        )
        claude_md.write_text(content, encoding="utf-8")

        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        assert result.exit_code == 0
        assert "fragment" in result.stderr.lower()

    def test_status_warns_when_binary_diverges_from_index(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """v0.3.12: feedback real (índice 0.2.0, binário 0.3.11) → aviso amarelo
        em stderr orientando `ingest --incremental`. Simulamos forçando um valor
        antigo em meta.plugadvpl_version."""
        # Adultera o meta direto via sqlite — simula índice criado em versão antiga.
        db = indexed_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                "UPDATE meta SET valor='0.0.1-old' WHERE chave='plugadvpl_version'"
            )
            conn.commit()
        finally:
            conn.close()

        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        assert result.exit_code == 0
        # Aviso vai pra stderr (não polui stdout JSON quando rodado com --format json).
        assert "0.0.1-old" in result.stderr
        assert "ingest --incremental" in result.stderr

    def test_status_no_warning_when_versions_match(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """Sem divergência: nenhum aviso amarelo poluindo stderr."""
        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        assert result.exit_code == 0
        assert "ingest --incremental" not in result.stderr

    def test_status_warning_suppressed_by_quiet(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """`--quiet` suprime o aviso (consistente com a política das outras decorações)."""
        db = indexed_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                "UPDATE meta SET valor='0.0.1-old' WHERE chave='plugadvpl_version'"
            )
            conn.commit()
        finally:
            conn.close()

        result = runner.invoke(
            app, ["--root", str(indexed_project), "--quiet", "status"]
        )
        assert result.exit_code == 0
        assert "0.0.1-old" not in result.stderr


class TestDoctor:
    def test_doctor_returns_diagnostics(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app, ["--root", str(indexed_project), "--format", "json", "doctor"]
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        checks = {r["check"] for r in payload["rows"]}
        assert "fts_sync" in checks

    def test_doctor_check_funcs_regex_matches_tlpp_bare_function(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.4.8: detector aceita TLPP `Function` puro (sem prefixo) — antes
        regex exigia (Static|User|Main) e contava menos que o parser,
        gerando funcs_real_bug FALSO POSITIVO (parser correto, detector erra).

        Repro: 1 fonte com 4 declaracoes (cobertura case + bare):
          1. Bare `Function U_X(...)` (TLPP-style)
          2. lowercase `static function Y()`
          3. CamelCase `Static Function Z()`
          4. lowercase `function W()`
        Parser pega todas 4. Detector deve pegar 4 tambem -> 0 real_bug.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "Sample.tlpp").write_bytes(
            b'Function U_Sample(cArg as character)\n'
            b'Return\n'
            b'\n'
            b'static function helperA()\n'
            b'Return\n'
            b'\n'
            b'Static Function HelperB()\n'
            b'Return\n'
            b'\n'
            b'function helperC()\n'
            b'Return\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        result = runner.invoke(
            app,
            ["--root", str(src), "--format", "json", "doctor", "--check-funcs"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        checks = {r["check"]: r for r in payload["rows"]}
        # ZERO funcs_real_bug — detector reconhece as 4 declaracoes (parser tb)
        assert checks["funcs_real_bug"]["count"] == 0, (
            f"detector ainda perde fn. detail={checks['funcs_real_bug']['detail']!r}"
        )

    def test_doctor_check_funcs_classifies_commented_vs_real_bug(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.4.7: doctor --check-funcs classifica discrepancias em 2 buckets:
        - funcs_real_bug: parser perdeu funcao que esta em CODE (parser bug)
        - funcs_commented_out: funcao dentro de /* */ (intencional, ok)

        Antes (v0.4.6): single check 'funcs_count_match' warn-ava por commenting-
        out (false alarm). Agora separa pra usuario ver claramente o que eh bug.
        """
        src = tmp_path / "src"
        src.mkdir()
        # 1 funcao ativa + 1 funcao comentada (commenting-out intencional).
        # Parser corretamente ignora a comentada -> nao eh bug.
        (src / "Sample.prw").write_bytes(
            b'User Function FnAtiva()\n'
            b'Return\n'
            b'\n'
            b'/*\n'
            b'Static Function FnComentada()\n'
            b'   Return\n'
            b'Return\n'
            b'*/\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        result = runner.invoke(
            app,
            ["--root", str(src), "--format", "json", "doctor", "--check-funcs"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        checks = {r["check"]: r for r in payload["rows"]}
        # Deve ter 2 checks novos
        assert "funcs_real_bug" in checks
        assert "funcs_commented_out" in checks
        # 0 real bugs (parser nao perdeu nada que esta em CODE)
        assert checks["funcs_real_bug"]["status"] == "ok"
        assert checks["funcs_real_bug"]["count"] == 0
        # 1 commented-out
        assert checks["funcs_commented_out"]["count"] >= 1
        assert checks["funcs_commented_out"]["status"] == "info"

    def test_doctor_check_funcs_detail_table_friendly_fields(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.4.9: rows funcs_detail tem count + detail string preenchidos
        pra render table mostrar info util (nao colunas vazias).

        Antes: table renderer so conhecia 4 colunas (check/status/count/detail)
        e as rows detail tinham count/detail vazios pq dados estavam em
        arquivo/grep_raw/grep_code/parser/classificacao. JSON OK, table inutil.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "FnA.prw").write_bytes(
            b'User Function FnA()\nReturn\n'
            b'/*\nStatic Function FnAOld()\nReturn\n*/\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        result = runner.invoke(
            app,
            [
                "--root", str(src), "--format", "json",
                "doctor", "--check-funcs", "--detail",
            ],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        detail_rows = [r for r in payload["rows"] if r.get("check") == "funcs_detail"]
        assert detail_rows
        for r in detail_rows:
            # Colunas estruturais (pra JSON) continuam
            assert "arquivo" in r
            assert "grep_raw" in r
            assert "classificacao" in r
            # NOVAS: count + detail (pra table render)
            assert "count" in r, f"row detail sem count: {r}"
            assert "detail" in r, f"row detail sem detail: {r}"
            # count = delta (raw - parser)
            assert r["count"] == r["grep_raw"] - r["parser"]
            # detail string deve conter arquivo + classificacao
            assert r["arquivo"] in r["detail"]
            assert r["classificacao"] in r["detail"]

    def test_doctor_check_funcs_detail_returns_row_per_file(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.4.7: --check-funcs --detail expande pra row-per-file
        (sugerido pelo reporter no adendo da bug report). Permite --limit
        global navegar lista completa sem truncagem em 10."""
        src = tmp_path / "src"
        src.mkdir()
        # Cria 3 fontes com commenting-out cada
        for nome in ("FnA", "FnB", "FnC"):
            (src / f"{nome}.prw").write_bytes(
                f'User Function {nome}()\n'.encode()
                + b'Return\n'
                + b'/*\n'
                + f'Static Function {nome}Old()\nReturn\n'.encode()
                + b'*/\n'
            )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        result = runner.invoke(
            app,
            [
                "--root", str(src), "--format", "json",
                "doctor", "--check-funcs", "--detail",
            ],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        # detail mode: rows por fonte com discrepancia (check='funcs_detail')
        detail_rows = [r for r in payload["rows"] if r.get("check") == "funcs_detail"]
        assert len(detail_rows) == 3, (
            f"esperado 3 rows (1 por fonte), recebi {len(detail_rows)}: {detail_rows}"
        )
        # Cada row deve ter arquivo, grep_raw, grep_code, parser, classificacao
        for r in detail_rows:
            assert "arquivo" in r
            assert "grep_raw" in r
            assert "grep_code" in r
            assert "parser" in r
            assert r.get("classificacao") == "commented_out"


class TestGrep:
    def test_grep_fts_default(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "--format", "json", "grep", "RecLock"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["total"] >= 1

    def test_grep_fts_invalid_syntax_friendly_error(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """v0.4.4 (BUG #1): padrão FTS5-inválido (com `/`, `(`, etc) NÃO deve
        crashar com traceback completo — deve mostrar mensagem amigável em
        stderr com sugestão de modo alternativo.
        """
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "grep", "//.*MsExecAuto", "-m", "fts"],
        )
        # Exit != 0 mas SEM traceback
        assert result.exit_code != 0
        combined = (result.stdout or "") + (result.stderr or "")
        assert "Traceback" not in combined, "esperado mensagem amigável, não traceback"
        assert "FTS5" in combined or "fts" in combined.lower()
        # Sugere modo alternativo
        assert "literal" in combined or "identifier" in combined


class TestLint:
    def test_lint_global(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app, ["--root", str(indexed_project), "--format", "json", "lint"]
        )
        assert result.exit_code == 0, result.stderr
        # Pode estar vazio mas tem que retornar JSON válido.
        json.loads(result.stdout)

    def test_callers_flags_is_self_call(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.3.18 — Bug #12 do QA report: `callers <nome>` misturava
        callsites externos com self-calls (FwLoadModel('X') dentro de X.prw)
        sem distincao. Agora cada row tem `is_self_call: bool` baseado em
        `funcao_origem == nome` OR `basename(arquivo_origem) == nome`."""
        src = tmp_path / "src"
        src.mkdir()
        # Self-call: dentro de SelfCall.prw, funcao SelfCall chama propria via FwLoadModel.
        (src / "SelfCall.prw").write_bytes(
            b'#include "totvs.ch"\n'
            b'User Function SelfCall()\n'
            b'  Local oModel := FwLoadModel("SelfCall")\n'
            b'Return\n'
        )
        # External: outro fonte chama SelfCall.
        (src / "Caller.prw").write_bytes(
            b'#include "totvs.ch"\n'
            b'User Function Caller()\n'
            b'  U_SelfCall()\n'
            b'Return\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        result = runner.invoke(
            app,
            ["--root", str(src), "--format", "json", "callers", "SelfCall"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        rows = payload["rows"]
        # Esperado: 1 self (FwLoadModel) + 1 external (U_SelfCall)
        self_calls = [r for r in rows if r.get("is_self_call") is True]
        external = [r for r in rows if r.get("is_self_call") is False]
        assert len(self_calls) >= 1, f"esperado >=1 self_call, rows={rows}"
        assert len(external) >= 1, f"esperado >=1 external, rows={rows}"
        # Self deve vir de SelfCall.prw; external de Caller.prw.
        assert all("SelfCall" in r["arquivo"] for r in self_calls)
        assert all("Caller" in r["arquivo"] for r in external)

    def test_arch_flags_tabelas_via_execauto(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.3.18 — Bug #11 do QA report: programas que usam MsExecAuto
        delegam acesso a tabelas pra rotina chamada — `tabelas_*` do parser
        ficam vazias mesmo o programa "tocando" SC5/SC6/SF4 etc. Sem flag,
        usuario tira conclusao errada confiando so na lista. Agora `arch`
        expoe `tabelas_via_execauto: bool` quando `EXEC_AUTO_CALLER` esta
        em capabilities."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "ExecAutoCaller.prw").write_bytes(
            b'#include "totvs.ch"\n'
            b'User Function ExecAutoCaller()\n'
            b'  Local aCab := {{"C5_NUM", "001", Nil}}\n'
            b'  Local aIt  := {{{"C6_NUM", "001", Nil}}}\n'
            b'  Private lMsErroAuto := .F.\n'
            b'  MsExecAuto({|x,y,z| MATA410(x,y,z)}, aCab, aIt, 3)\n'
            b'  If lMsErroAuto\n'
            b'    MostraErro()\n'
            b'  EndIf\n'
            b'Return\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        result = runner.invoke(
            app,
            ["--root", str(src), "--format", "json", "arch", "ExecAutoCaller.prw"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        row = payload["rows"][0]
        assert "EXEC_AUTO_CALLER" in row["capabilities"], (
            f"Caso de teste deve ter EXEC_AUTO_CALLER. caps={row['capabilities']}"
        )
        assert row.get("tabelas_via_execauto") is True, (
            f"Esperado tabelas_via_execauto=True quando EXEC_AUTO_CALLER, "
            f"recebido {row.get('tabelas_via_execauto')!r}"
        )

    def test_arch_no_execauto_flag_when_no_capability(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """Caso negativo: fonte sem MsExecAuto deve ter tabelas_via_execauto=False."""
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "--format", "json", "arch", "FATA050.prw"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        row = payload["rows"][0]
        assert row.get("tabelas_via_execauto") is False

    def test_lint_findings_no_duplicates_alias_reclock(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.3.18 — Bug #9 do QA report: BP-001 reportava o mesmo RecLock
        2x quando vinha em forma `<alias>->(RecLock(...))` — casava com
        AMBOS _RECLOCK_OPEN_RE (literal) E _RECLOCK_VIA_ALIAS_RE (alias).
        Fixture forca o cenario; teste assegura unicidade no DB."""
        src = tmp_path / "src"
        src.mkdir()
        fixture = (
            Path(__file__).parent.parent
            / "fixtures" / "synthetic" / "reclock_alias_dup_trigger.prw"
        )
        (src / "ZH3DupTrigger.prw").write_bytes(fixture.read_bytes())
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        db = src / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            dups = conn.execute(
                """
                SELECT arquivo, linha, regra_id, COUNT(*) AS n
                FROM lint_findings
                WHERE regra_id='BP-001'
                GROUP BY arquivo, linha, regra_id
                HAVING n > 1
                """
            ).fetchall()
        finally:
            conn.close()
        assert dups == [], (
            f"BP-001 duplicado em (arquivo, linha): {dups}. "
            "ZH3->(RecLock(...)) deveria gerar 1 finding, nao 2."
        )


class TestWorkflow:
    """v0.4.0 — Universo 3 / Feature A: comando `workflow` lista execution_triggers."""

    @pytest.fixture
    def triggers_project(self, tmp_path: Path, runner: CliRunner) -> Path:
        """Projeto com 4 fontes cobrindo cada kind + 1 multi-trigger."""
        src = tmp_path / "src"
        src.mkdir()
        # 1) workflow (TWFProcess)
        (src / "WFSalNeg.prw").write_bytes(
            b'User Function WfSalNeg()\n'
            b'  Local oWF := TWFProcess():New("SALNEG", "Saldo Negativo")\n'
            b'  oWF:bReturn := {|o| U_WfRetSN(o)}\n'
            b'  oWF:Start()\n'
            b'Return\n'
        )
        # 2) schedule (SchedDef)
        (src / "FATR020.prw").write_bytes(
            b'User Function FATR020()\n'
            b'Return\n'
            b'\n'
            b'Static Function SchedDef()\n'
            b'  Local a := { "R", "FAT020", "SF2", {1,2}, "Faturamento" }\n'
            b'Return a\n'
        )
        # 3) multi-trigger: job_standalone + mail_send no mesmo fonte
        (src / "JobAviso.prw").write_bytes(
            b'Main Function JobAviso()\n'
            b'  RpcSetEnv("01","01",,,"FAT","JobAviso")\n'
            b'  While !File("/stop_aviso.flg")\n'
            b'    MailAuto("a@x", "b@y", "Aviso", "msg", {})\n'
            b'    Sleep(60000)\n'
            b'  EndDo\n'
            b'  RpcClearEnv()\n'
            b'Return\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        return src

    def test_workflow_lists_all_kinds(
        self, triggers_project: Path, runner: CliRunner
    ) -> None:
        """Sem filtro: lista os 4 kinds (workflow/schedule/job_standalone/mail_send)."""
        result = runner.invoke(
            app, ["--root", str(triggers_project), "--format", "json", "workflow"]
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        kinds = {r["kind"] for r in rows}
        assert kinds == {"workflow", "schedule", "job_standalone", "mail_send"}, (
            f"esperado os 4 kinds, recebido {kinds}"
        )

    def test_workflow_filter_by_kind(
        self, triggers_project: Path, runner: CliRunner
    ) -> None:
        """`--kind job_standalone` retorna só jobs daemon."""
        result = runner.invoke(
            app,
            [
                "--root", str(triggers_project), "--format", "json",
                "workflow", "--kind", "job_standalone",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["kind"] == "job_standalone"
        assert rows[0]["target"] == "JobAviso"

    def test_workflow_filter_by_arquivo(
        self, triggers_project: Path, runner: CliRunner
    ) -> None:
        """`--arquivo JobAviso.prw` retorna 2 triggers (job + mail) do multi-source."""
        result = runner.invoke(
            app,
            [
                "--root", str(triggers_project), "--format", "json",
                "workflow", "--arquivo", "JobAviso.prw",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        kinds = {r["kind"] for r in rows}
        assert kinds == {"job_standalone", "mail_send"}, (
            f"esperado job+mail no mesmo fonte, recebido {kinds}"
        )

    def test_workflow_filter_by_target(
        self, triggers_project: Path, runner: CliRunner
    ) -> None:
        """`--target FAT020` (pergunte SX1) localiza o schedule."""
        result = runner.invoke(
            app,
            [
                "--root", str(triggers_project), "--format", "json",
                "workflow", "--target", "FAT020",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["kind"] == "schedule"

    def test_workflow_rejects_invalid_kind(
        self, triggers_project: Path, runner: CliRunner
    ) -> None:
        """v0.4.4 (UX #4): --kind invalido rejeitado com mensagem clara."""
        result = runner.invoke(
            app,
            [
                "--root", str(triggers_project),
                "workflow", "--kind", "tipoinexistente",
            ],
        )
        assert result.exit_code != 0
        combined = (result.stdout or "") + (result.stderr or "")
        # Mensagem deve listar opcoes validas
        assert "workflow" in combined.lower() and "schedule" in combined.lower()

    def test_workflow_duplicates_detects_shared_target(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.4.6 (K): --duplicates lista targets compartilhados entre
        fontes diferentes (vitoria do plugin: detecta erros de design
        onde dev reusou Process ID/Main name por engano).
        """
        src = tmp_path / "src"
        src.mkdir()
        # 2 fontes com mesmo process_id 'CONFLITO' (real bug pattern)
        (src / "WfA.prw").write_bytes(
            b'User Function WfA()\n'
            b'   oWF := TWFProcess():New("CONFLITO", "Workflow A")\n'
            b'   oWF:Start()\n'
            b'Return\n'
        )
        (src / "WfB.prw").write_bytes(
            b'User Function WfB()\n'
            b'   oWF := TWFProcess():New("CONFLITO", "Workflow B (diferente)")\n'
            b'   oWF:Start()\n'
            b'Return\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        result = runner.invoke(
            app,
            ["--root", str(src), "--format", "json", "workflow", "--duplicates"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) >= 1
        # row deve conter target compartilhado + count >= 2
        conflito = next((r for r in rows if r["target"] == "CONFLITO"), None)
        assert conflito is not None, f"esperado target CONFLITO em rows={rows}"
        assert conflito["count"] >= 2
        assert "WfA.prw" in conflito["arquivos"]
        assert "WfB.prw" in conflito["arquivos"]

    def test_workflow_persisted_in_db(
        self, triggers_project: Path
    ) -> None:
        """Sanity check: execution_triggers tabela existe e tem rows do ingest."""
        db = triggers_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM execution_triggers"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count >= 4, f"esperado >=4 triggers, encontrado {count}"


class TestExecauto:
    """v0.4.1 — Universo 3 / Feature B: comando `execauto` lista chamadas resolvidas."""

    @pytest.fixture
    def execauto_project(self, tmp_path: Path, runner: CliRunner) -> Path:
        """Projeto com 3 fontes cobrindo MATA410 (inc), FINA050 (inc), e dynamic."""
        src = tmp_path / "src"
        src.mkdir()
        # MATA410 inclusao — SC5/SC6 + secundarias.
        (src / "ABCCOMBO.prw").write_bytes(
            b'User Function ABCCOMBO()\n'
            b'   MsExecAuto({|x,y,z| MATA410(x,y,z)}, aCab, aIt, 3)\n'
            b'Return\n'
        )
        # FINA050 inclusao — SE2.
        (src / "ABCFIN50.prw").write_bytes(
            b'User Function ABCFIN50()\n'
            b'   MsExecAuto({|x,y| FINA050(x,y)}, aArr, 3)\n'
            b'Return\n'
        )
        # Dynamic — &(cVar).
        (src / "ABCDYN.prw").write_bytes(
            b'User Function ABCDYN()\n'
            b'   MsExecAuto({|x,y,z| &(cRot).(x,y,z)}, aCab, aIt, 3)\n'
            b'Return\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        return src

    def test_execauto_lists_all(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """Sem filtro: lista as 3 chamadas (MATA410, FINA050, dynamic)."""
        result = runner.invoke(
            app, ["--root", str(execauto_project), "--format", "json", "execauto"]
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 3
        routines = {r["routine"] or "(dynamic)" for r in rows}
        assert routines == {"MATA410", "FINA050", "(dynamic)"}

    def test_execauto_filter_by_routine(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """`--routine MATA410` retorna só a chamada com SC5/SC6."""
        result = runner.invoke(
            app,
            [
                "--root", str(execauto_project), "--format", "json",
                "execauto", "--routine", "MATA410",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["routine"] == "MATA410"
        assert rows[0]["module"] == "SIGAFAT"
        assert "SC5" in rows[0]["tabelas"]
        assert "SC6" in rows[0]["tabelas"]
        assert rows[0]["op"] == "inclusao"

    def test_execauto_filter_by_modulo(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """`--modulo SIGAFIN` localiza só FINA050."""
        result = runner.invoke(
            app,
            [
                "--root", str(execauto_project), "--format", "json",
                "execauto", "--modulo", "SIGAFIN",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["routine"] == "FINA050"

    def test_execauto_filter_dynamic_only(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """`--dynamic` retorna só calls não-resolvíveis."""
        result = runner.invoke(
            app,
            [
                "--root", str(execauto_project), "--format", "json",
                "execauto", "--dynamic",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["routine"] == "(dynamic)"

    def test_execauto_filter_op_inc(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """`--op inc` retorna só inclusões (op_code=3)."""
        result = runner.invoke(
            app,
            [
                "--root", str(execauto_project), "--format", "json",
                "execauto", "--op", "inc",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        # Todas as 3 fixtures usam op=3, então 3 rows
        assert len(rows) == 3
        for r in rows:
            assert r["op"] == "inclusao"

    def test_arch_exposes_tabelas_via_execauto_resolvidas(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """v0.4.1 enrichment: `arch` mostra tabelas inferidas via ExecAuto."""
        result = runner.invoke(
            app,
            [
                "--root", str(execauto_project), "--format", "json",
                "arch", "ABCCOMBO.prw",
            ],
        )
        assert result.exit_code == 0, result.stderr
        row = json.loads(result.stdout)["rows"][0]
        # Bool antigo continua
        assert row.get("tabelas_via_execauto") is True
        # Novo campo: lista de tabelas resolvidas
        resolved = row.get("tabelas_via_execauto_resolvidas", [])
        assert "SC5" in resolved
        assert "SC6" in resolved

    def test_arch_resolved_empty_when_dynamic_only(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """Fonte com só call dynamic → resolved = []."""
        result = runner.invoke(
            app,
            [
                "--root", str(execauto_project), "--format", "json",
                "arch", "ABCDYN.prw",
            ],
        )
        assert result.exit_code == 0, result.stderr
        row = json.loads(result.stdout)["rows"][0]
        assert row.get("tabelas_via_execauto_resolvidas", []) == []

    def test_execauto_empty_modulo_suggests_available_modules(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """v0.4.6 (E): --modulo SIGAINEXISTENTE NAO existe no indice deve
        sugerir os modulos disponiveis nos next_steps.
        """
        result = runner.invoke(
            app,
            [
                "--root", str(execauto_project),
                "execauto", "--modulo", "SIGAINEXISTENTE",
            ],
        )
        assert result.exit_code == 0
        stderr = result.stderr or ""
        # Stderr (next_steps) deve mencionar modulos reais (SIGAFAT/SIGAFIN
        # estao no fixture execauto_project)
        assert "SIGAFAT" in stderr or "SIGAFIN" in stderr, (
            f"esperado sugestao de modulos disponiveis. stderr={stderr!r}"
        )

    def test_execauto_empty_with_filter_does_not_suggest_ingest(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """v0.4.4 (UX #3): filtro vazio (--arquivo inexistente) NAO deve sugerir
        ingest --no-incremental. Deve sugerir verificar o filtro.

        next_steps sao impressos em stderr (LLM hints).
        """
        result = runner.invoke(
            app,
            [
                "--root", str(execauto_project),
                "execauto", "--arquivo", "NAOEXISTE.prw",
            ],
        )
        assert result.exit_code == 0
        assert "ingest --no-incremental" not in (result.stderr or ""), (
            f"filtro com valor inexistente NAO deve sugerir reingest "
            f"(estava sugerindo desnecessariamente). stderr: {result.stderr!r}"
        )

    def test_execauto_rejects_invalid_op(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """v0.4.4 (UX #4): --op invalida deve ser rejeitada com mensagem
        clara antes de chegar na query (vs antes que retornava vazio sem
        aviso).
        """
        result = runner.invoke(
            app,
            [
                "--root", str(execauto_project),
                "execauto", "--op", "invalida",
            ],
        )
        # Typer Enum violation → exit code 2 e mensagem listando opcoes
        assert result.exit_code != 0
        combined = (result.stdout or "") + (result.stderr or "")
        assert "invalida" in combined.lower() or "invalid" in combined.lower()
        # Mensagem deve listar opcoes validas
        assert "inc" in combined.lower()

    def test_execauto_json_includes_caminho_relativo(
        self, execauto_project: Path, runner: CliRunner
    ) -> None:
        """v0.4.6 (D): JSON output inclui caminho_relativo pra distinguir
        fontes homonimos em pastas diferentes (ambiguidade basename).
        """
        result = runner.invoke(
            app,
            ["--root", str(execauto_project), "--format", "json", "execauto"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert rows
        assert "caminho" in rows[0], (
            f"esperado 'caminho' (relativo) no JSON output. row keys: {list(rows[0])}"
        )

    def test_execauto_persisted_in_db(self, execauto_project: Path) -> None:
        """Sanity: tabela execauto_calls existe e tem rows."""
        db = execauto_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM execauto_calls").fetchone()[0]
        finally:
            conn.close()
        assert count == 3


class TestDocs:
    """v0.4.2 — Universo 3 / Feature C: comando `docs` agrega Protheus.doc."""

    @pytest.fixture
    def docs_project(self, tmp_path: Path, runner: CliRunner) -> Path:
        """Projeto com 3 fontes: 1 doc completo, 1 deprecated, 1 órfão (sem doc)."""
        src = tmp_path / "src" / "SIGAFAT"
        src.mkdir(parents=True)
        # 1) Doc completo
        (src / "MT460FIM.tlpp").write_bytes(
            b'/*/{Protheus.doc} MT460FIM\n'
            b'Ponto de Entrada apos faturamento.\n'
            b'@type user function\n'
            b'@author Fernando Vernier\n'
            b'@since 18/10/2025\n'
            b'@version 2.0\n'
            b'@param cNumNF, character, "Numero da NF"\n'
            b'@return logical, ".T. se sucesso"\n'
            b'/*/\n'
            b'User Function MT460FIM(cNumNF)\n'
            b'Return .T.\n'
        )
        # 2) Deprecated
        (src / "MT460OLD.tlpp").write_bytes(
            b'/*/{Protheus.doc} MT460OLD\n'
            b'Versao antiga do PE.\n'
            b'@type user function\n'
            b'@author Joao\n'
            b'@deprecated Use MT460FIM no lugar\n'
            b'/*/\n'
            b'User Function MT460OLD()\n'
            b'Return\n'
        )
        # 3) Órfão (sem doc) — gera BP-007.
        (src / "MT460NEW.tlpp").write_bytes(
            b'User Function MT460NEW()\n'
            b'   ConOut("sem doc")\n'
            b'Return\n'
        )
        runner.invoke(app, ["--root", str(tmp_path / "src"), "init"])
        runner.invoke(app, ["--root", str(tmp_path / "src"), "ingest"])
        return tmp_path / "src"

    def test_docs_lists_all(
        self, docs_project: Path, runner: CliRunner
    ) -> None:
        """Sem filtro: lista 2 docs (MT460FIM + MT460OLD; órfão NÃO aparece aqui)."""
        result = runner.invoke(
            app, ["--root", str(docs_project), "--format", "json", "docs"]
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 2
        funcs = {r["funcao"] for r in rows}
        assert funcs == {"MT460FIM", "MT460OLD"}

    def test_docs_filter_by_modulo(
        self, docs_project: Path, runner: CliRunner
    ) -> None:
        """Path `src/SIGAFAT/...` infere SIGAFAT."""
        result = runner.invoke(
            app,
            [
                "--root", str(docs_project), "--format", "json",
                "docs", "SIGAFAT",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 2
        for r in rows:
            assert r["modulo"] == "SIGAFAT"

    def test_docs_filter_deprecated(
        self, docs_project: Path, runner: CliRunner
    ) -> None:
        """`--deprecated` retorna só MT460OLD."""
        result = runner.invoke(
            app,
            [
                "--root", str(docs_project), "--format", "json",
                "docs", "--deprecated",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["funcao"] == "MT460OLD"
        assert rows[0]["deprecated"] == "sim"

    def test_docs_filter_author(
        self, docs_project: Path, runner: CliRunner
    ) -> None:
        """`--author Fernando` LIKE match localiza só MT460FIM."""
        result = runner.invoke(
            app,
            [
                "--root", str(docs_project), "--format", "json",
                "docs", "--author", "Fernando",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["funcao"] == "MT460FIM"

    def test_docs_show_renders_markdown(
        self, docs_project: Path, runner: CliRunner
    ) -> None:
        """`--show MT460FIM` retorna Markdown estruturado."""
        result = runner.invoke(
            app, ["--root", str(docs_project), "docs", "--show", "MT460FIM"]
        )
        assert result.exit_code == 0, result.stderr
        out = result.stdout
        assert "## MT460FIM" in out
        assert "SIGAFAT" in out
        assert "Fernando Vernier" in out
        assert "### Parâmetros" in out
        assert "cNumNF" in out
        assert "### Retorno" in out

    def test_docs_show_not_found_exits_1(
        self, docs_project: Path, runner: CliRunner
    ) -> None:
        """`--show <inexistente>` retorna exit 1."""
        result = runner.invoke(
            app, ["--root", str(docs_project), "docs", "--show", "FnInexistente"]
        )
        assert result.exit_code == 1

    def test_docs_orphans_lists_bp007(
        self, docs_project: Path, runner: CliRunner
    ) -> None:
        """`--orphans` lista funções sem header (cross-ref BP-007)."""
        result = runner.invoke(
            app,
            [
                "--root", str(docs_project), "--format", "json",
                "docs", "--orphans",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        # MT460NEW deve aparecer como órfão
        funcs = {r["funcao"] for r in rows}
        assert "MT460NEW" in funcs

    def test_docs_show_homonym_warns_and_supports_arquivo(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.4.3 (I2): 2 fontes com mesma funcao -> --show avisa em stderr
        e --arquivo desambiguar."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "FnA.prw").write_bytes(
            b'/*/{Protheus.doc} HomFn\nDoc do A.\n@author Anna\n/*/\n'
            b'User Function HomFn()\nReturn\n'
        )
        (src / "FnB.prw").write_bytes(
            b'/*/{Protheus.doc} HomFn\nDoc do B.\n@author Beto\n/*/\n'
            b'User Function HomFn()\nReturn\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])

        # Sem --arquivo: aviso em stderr + mostra primeiro alfabeticamente
        result = runner.invoke(
            app, ["--root", str(src), "docs", "--show", "HomFn"]
        )
        assert result.exit_code == 0
        assert "2 fontes" in result.stderr or "Aviso" in result.stderr
        assert "Anna" in result.stdout  # FnA.prw vem antes alfabeticamente

        # Com --arquivo FnB.prw: mostra o do Beto
        result2 = runner.invoke(
            app, ["--root", str(src), "docs", "--show", "HomFn", "--arquivo", "FnB.prw"]
        )
        assert result2.exit_code == 0
        assert "Beto" in result2.stdout

    def test_docs_show_ws_constructs_end_to_end(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.4.4 (BUG #2): docs --funcao e --show funcionam pra
        WSSTRUCT/WSSERVICE/WSMETHOD (antes ficavam órfãos)."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "MyWS.tlpp").write_bytes(
            b'/*/{Protheus.doc} WSXDATA\n@type property\n/*/\n'
            b'WSSTRUCT WSXDATA\n'
            b'   WSDATA cId AS STRING\n'
            b'ENDWSSTRUCT\n'
            b'\n'
            b'/*/{Protheus.doc} MyWS\n@type class\n/*/\n'
            b'WSSERVICE MyWS DESCRIPTION "Servico"\n'
            b'\n'
            b'/*/{Protheus.doc} GravData\n@type method\n/*/\n'
            b'WSMETHOD GravData DESCRIPTION "Grava" WSSERVICE MyWS\n'
            b'   Local lOk := .T.\n'
            b'Return lOk\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])

        # --funcao pra cada um dos 3 deve retornar 1 row
        for nome in ("WSXDATA", "MyWS", "GravData"):
            r = runner.invoke(
                app,
                ["--root", str(src), "--format", "json", "docs", "--funcao", nome],
            )
            assert r.exit_code == 0, r.stderr
            rows = json.loads(r.stdout)["rows"]
            assert len(rows) == 1, f"esperado 1 row pra {nome}, recebi {len(rows)}"

        # --show formatado
        r = runner.invoke(
            app, ["--root", str(src), "docs", "--show", "GravData"]
        )
        assert r.exit_code == 0, r.stderr
        assert "## GravData" in r.stdout
        assert "@type method" in r.stdout

    def test_docs_persisted_in_db(self, docs_project: Path) -> None:
        """Sanity: tabela protheus_docs existe e tem 2 rows."""
        db = docs_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM protheus_docs").fetchone()[0]
        finally:
            conn.close()
        assert count == 2


class TestTrace:
    """v0.5.0 (Universo 4 / Feature A): trace cross-universo."""

    @pytest.fixture
    def trace_project(self, tmp_path: Path, runner: CliRunner) -> Path:
        """Projeto cobrindo as 3 entidades + cross-universo."""
        src = tmp_path / "src"
        src.mkdir()
        # Fonte que define função, tem Protheus.doc, e chama MsExecAuto MATA410
        (src / "MyCmp.prw").write_bytes(
            b'/*/{Protheus.doc} U_MyCmp\n'
            b'Helper que toca SA1 via ExecAuto.\n'
            b'@type user function\n@author Tester\n'
            b'/*/\n'
            b'User Function U_MyCmp()\n'
            b'   Local aCab := {}\n'
            b'   MsExecAuto({|x,y,z| MATA410(x,y,z)}, aCab, {}, 3)\n'
            b'   dbSelectArea("SA1")\n'
            b'   SA1->A1_COD := "001"\n'
            b'Return\n'
        )
        # Fonte que chama U_MyCmp
        (src / "Caller.prw").write_bytes(
            b'User Function CallerFn()\n'
            b'   U_MyCmp()\n'
            b'Return\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        return src

    def test_trace_funcao_returns_called_by_and_doc(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """trace de funcao retorna called_by (U1) + documented_in (U3)."""
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "--format", "json", "trace", "U_MyCmp"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        edges = {r["edge"] for r in rows}
        assert "called_by" in edges, f"esperado called_by; edges={edges}"
        assert "documented_in" in edges, f"esperado documented_in; edges={edges}"
        # called_by deve apontar pra Caller.prw
        cb_rows = [r for r in rows if r["edge"] == "called_by"]
        assert any("Caller.prw" in r["arquivo"] for r in cb_rows)

    def test_trace_funcao_via_execauto(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """trace de MATA410 (rotina TOTVS) retorna via_execauto da chamada."""
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "--format", "json", "trace", "MATA410"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        edges = {r["edge"] for r in rows}
        assert "via_execauto" in edges
        via = [r for r in rows if r["edge"] == "via_execauto"]
        assert any("MyCmp.prw" in r["arquivo"] for r in via)

    def test_trace_tabela_returns_reads_and_writes(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """trace SA1 retorna edges reads/writes (U1)."""
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "--format", "json", "trace", "SA1"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        edges = {r["edge"] for r in rows}
        # MyCmp.prw faz DbSelectArea("SA1") + SA1->A1_COD := ...
        assert "reads" in edges or "writes" in edges, f"edges={edges}"

    def test_trace_tabela_via_execauto_inferred(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """trace SC5 (tabela primária de MATA410) detecta touched_via_execauto."""
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "--format", "json", "trace", "SC5"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        edges = {r["edge"] for r in rows}
        assert "touched_via_execauto" in edges, f"edges={edges}"

    def test_trace_filter_universo(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """--universo 3 limita a hits do Universo 3 (workflow/execauto/docs)."""
        result = runner.invoke(
            app,
            [
                "--root", str(trace_project), "--format", "json",
                "trace", "U_MyCmp", "--universo", "3",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert all(r["universo"] == 3 for r in rows), (
            f"esperado só U3, recebi universos={[r['universo'] for r in rows]}"
        )

    def test_trace_table_definition_first_in_output(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """v0.5.1 (#5): table_definition vem no TOPO do output quando
        tipo=tabela (descrição oficial primeiro, antes da lista de reads/writes).

        Antes aparecia no fim de 100+ rows, perdida. Sort priority puxa
        edges informativos (table_definition, n_fields, field_definition)
        pro topo do bloco U2.
        """
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "--format", "json", "trace", "SA1"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        # Pega rows U2 (onde table_definition vive)
        u2 = [r for r in rows if r["universo"] == 2]
        if u2:
            # Primeiro row de U2 deve ser table_definition se existir
            tdef_idx = next(
                (i for i, r in enumerate(u2) if r["edge"] == "table_definition"),
                None,
            )
            if tdef_idx is not None:
                # table_definition deve vir antes de qualquer in_*/indexed_by/trigger_on_table
                outras_u2 = [
                    i for i, r in enumerate(u2)
                    if r["edge"] not in ("table_definition", "n_fields", "field_definition")
                ]
                if outras_u2:
                    assert tdef_idx < min(outras_u2), (
                        f"table_definition (idx={tdef_idx}) deve vir antes "
                        f"de outras edges U2 (min idx={min(outras_u2)})"
                    )

    def test_trace_tipo_override(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """--tipo força quando auto-detect erra."""
        # SA1 vira tabela por default; com --tipo funcao, busca como função
        result = runner.invoke(
            app,
            [
                "--root", str(trace_project),
                "trace", "SA1", "--tipo", "funcao",
            ],
        )
        assert result.exit_code == 0
        # SA1 nao eh funcao definida; resultado provavelmente vazio (mas exit 0)

    def test_trace_arquivo_aggregates_arch_doc_execauto(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """v0.5.3 (A.2): trace de arquivo agrega arch_summary + defines_function
        + has_protheus_doc + calls_execauto."""
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "--format", "json", "trace", "MyCmp.prw"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        edges = {r["edge"] for r in rows}
        # MyCmp.prw tem Protheus.doc + chama MsExecAuto MATA410 + define U_MyCmp
        assert "arch_summary" in edges or "defines_function" in edges, f"edges={edges}"
        assert "calls_execauto" in edges, f"edges={edges}"
        assert "has_protheus_doc" in edges, f"edges={edges}"

    def test_trace_arquivo_auto_detect_by_extension(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """trace MyCmp.prw deve detectar como tipo=arquivo automaticamente."""
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "trace", "MyCmp.prw"],
        )
        assert result.exit_code == 0
        # Title menciona tipo=arquivo
        out = (result.stdout or "") + (result.stderr or "")
        assert "tipo=arquivo" in out, f"out={out[:300]!r}"

    def test_trace_contexto_dict_structured_in_json(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """v0.5.2 (#4): JSON output inclui contexto_dict (chave/valor
        estruturado) alem da string contexto. Consumidor programatico evita
        parse manual de 'tabela=EE7 tipo=C(3) ...'.

        Aditivo: contexto (string) inalterado pra nao quebrar consumers
        existentes; contexto_dict (dict) novo.
        """
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "--format", "json", "trace", "U_MyCmp"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert rows
        # Todas as rows tem o campo (mesmo que dict vazio)
        for r in rows:
            assert "contexto" in r, f"contexto (string) ausente: {r}"
            assert "contexto_dict" in r, f"contexto_dict ausente: {r}"
            assert isinstance(r["contexto_dict"], dict)
        # Pelo menos uma row com contexto estruturado (defined_in tem 'kind')
        defined = [r for r in rows if r["edge"] == "defined_in"]
        assert defined
        # defined_in tem contexto tipo "user_function" — pode ser dict {"kind": "user_function"}
        # ou string atomic. Se for atomic, dict pode ser {} ou {"text": "user_function"}.
        # Aqui só confirma que o campo existe — formato exato fica a critério do collector.

    def test_trace_contexto_dict_table_render_unchanged(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """Render table NAO mostra contexto_dict — só a coluna contexto string.
        Backward compat: layout default igual ao v0.5.1."""
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "trace", "U_MyCmp"],
        )
        assert result.exit_code == 0
        # 'contexto_dict' NAO deve aparecer no header da tabela
        assert "contexto_dict" not in (result.stdout or "")

    def test_trace_defined_in_alvo_is_funcao_name(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """v0.5.1 (#6): edge 'defined_in' tem alvo = nome do simbolo,
        nao redundante = arquivo. Outras edges usam alvo semanticamente
        diferente; defined_in fica consistente com a coluna funcao
        (mas alvo deve ser o nome do simbolo definido).
        """
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "--format", "json", "trace", "U_MyCmp"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        defined = [r for r in rows if r["edge"] == "defined_in"]
        assert defined, f"esperado pelo menos 1 row defined_in. edges={[r['edge'] for r in rows]}"
        for r in defined:
            assert r["alvo"] != r["arquivo"], (
                f"defined_in.alvo NAO deve ser igual a arquivo (redundante). row={r}"
            )
            # alvo deve ser o nome da funcao (case-insensitive)
            assert "MYCMP" in r["alvo"].upper(), (
                f"alvo deveria conter nome da funcao. alvo={r['alvo']!r}"
            )

    def test_trace_typo_in_populated_index_suggests_find_not_reingest(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """v0.5.1 (#3): typo em indice populado sugere find/grep, NAO reingest.

        Antes: 'Nenhum hit. Rode plugadvpl ingest --no-incremental'
        induzia reingest caro (varre 2k+ fontes) sem necessidade. Correto:
        sugerir find/grep pra confirmar nome (provavel typo).
        """
        result = runner.invoke(
            app,
            ["--root", str(trace_project), "trace", "TYPOFOOXYZ"],
        )
        assert result.exit_code == 0
        stderr = result.stderr or ""
        # NAO deve sugerir reingest (indice tem fontes)
        assert "ingest --no-incremental" not in stderr, (
            f"typo em indice populado nao deve sugerir reingest. stderr={stderr!r}"
        )
        # DEVE sugerir find ou grep
        assert "find" in stderr or "grep" in stderr, (
            f"esperado sugestao find/grep. stderr={stderr!r}"
        )

    def test_trace_invalid_universo_rejected(
        self, trace_project: Path, runner: CliRunner
    ) -> None:
        """--universo com valor inválido sai com erro amigável."""
        result = runner.invoke(
            app,
            [
                "--root", str(trace_project),
                "trace", "U_MyCmp", "--universo", "abc",
            ],
        )
        assert result.exit_code != 0
        assert "--universo" in (result.stderr or "")


class TestQualidadeMetricas:
    """v0.6.0 (Universo 4 / Feature B): metrics + hotspots + cobertura-doc."""

    @pytest.fixture
    def metrics_project(self, tmp_path: Path, runner: CliRunner) -> Path:
        """Projeto com função simples + complexa + função muito chamada."""
        src = tmp_path / "src"
        src.mkdir()
        # SimpleFn: CC=1, sem nesting
        (src / "Simple.prw").write_bytes(
            b'User Function SimpleFn(cArg)\n'
            b'   Return Nil\n'
        )
        # ComplexFn: CC alta (5+), nesting 3+
        (src / "Complex.prw").write_bytes(
            b'/*/{Protheus.doc} U_ComplexFn\nHelper.\n@type user function\n/*/\n'
            b'User Function ComplexFn(cArg, nVal)\n'
            b'   Local i, j\n'
            b'   If cArg == "A"\n'
            b'      For i := 1 To 10\n'
            b'         If i % 2 == 0\n'
            b'            For j := 1 To 5\n'
            b'               If j > 3\n'
            b'                  ConOut("aa")\n'
            b'               EndIf\n'
            b'            Next j\n'
            b'         EndIf\n'
            b'      Next i\n'
            b'   ElseIf cArg == "B"\n'
            b'      ConOut("b")\n'
            b'   EndIf\n'
            b'Return Nil\n'
        )
        # CallerFn: chama SimpleFn 3x e ComplexFn 2x → hotspots
        (src / "Caller.prw").write_bytes(
            b'User Function CallerFn()\n'
            b'   U_SimpleFn("x")\n'
            b'   U_SimpleFn("y")\n'
            b'   U_SimpleFn("z")\n'
            b'   U_ComplexFn("A", 1)\n'
            b'   U_ComplexFn("B", 2)\n'
            b'Return\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        return src

    def test_metrics_lists_all_functions(
        self, metrics_project: Path, runner: CliRunner
    ) -> None:
        """metrics lista todas as funções com cc/loc/nesting."""
        result = runner.invoke(
            app, ["--root", str(metrics_project), "--format", "json", "metrics"]
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        funcs = {r["funcao"]: r for r in rows}
        assert "SimpleFn" in funcs
        assert "ComplexFn" in funcs
        assert "CallerFn" in funcs
        # SimpleFn: baseline
        assert funcs["SimpleFn"]["cc"] == 1
        assert funcs["SimpleFn"]["nesting"] == 0
        # ComplexFn: muito mais alto
        assert funcs["ComplexFn"]["cc"] >= 5
        assert funcs["ComplexFn"]["nesting"] >= 3
        # has_doc populado
        assert funcs["ComplexFn"]["has_doc"] is True
        assert funcs["SimpleFn"]["has_doc"] is False

    def test_metrics_filter_min_cc(
        self, metrics_project: Path, runner: CliRunner
    ) -> None:
        """--min-cc 5 retorna só ComplexFn (SimpleFn CC=1, CallerFn CC=1)."""
        result = runner.invoke(
            app,
            [
                "--root", str(metrics_project), "--format", "json",
                "metrics", "--min-cc", "5",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        funcs = {r["funcao"] for r in rows}
        assert "ComplexFn" in funcs
        assert "SimpleFn" not in funcs

    def test_metrics_sort_loc(
        self, metrics_project: Path, runner: CliRunner
    ) -> None:
        """--sort loc retorna ComplexFn primeiro (mais linhas)."""
        result = runner.invoke(
            app,
            [
                "--root", str(metrics_project), "--format", "json",
                "metrics", "--sort", "loc",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert rows[0]["funcao"] == "ComplexFn"

    def test_hotspots_method_dedup_warning(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """v0.6.1 (bug #1): hotspots emite warning quando detecta múltiplas
        variáveis VAR:METODO compartilhando o mesmo método (provavelmente
        mesma classe acessada via vars diferentes — ex: TPrinter:Say via
        oPrint/oPrn/oPrinter).
        """
        src = tmp_path / "src"
        src.mkdir()
        # 3 fontes que chamam TPrinter:Say via vars com nomes diferentes
        (src / "FnA.prw").write_bytes(
            b'User Function FnA()\n'
            b'   Local oPrint := TPrinter():New()\n'
            b'   oPrint:Say(1, "x")\n'
            b'   oPrint:Say(2, "y")\n'
            b'Return\n'
        )
        (src / "FnB.prw").write_bytes(
            b'User Function FnB()\n'
            b'   Local oPrn := TPrinter():New()\n'
            b'   oPrn:Say(1, "x")\n'
            b'Return\n'
        )
        (src / "FnC.prw").write_bytes(
            b'User Function FnC()\n'
            b'   Local oPrinter := TPrinter():New()\n'
            b'   oPrinter:Say(1, "x")\n'
            b'Return\n'
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        result = runner.invoke(
            app,
            ["--root", str(src), "hotspots", "--tipo", "method"],
        )
        assert result.exit_code == 0
        stderr = result.stderr or ""
        # Deve mencionar warning de :SAY ambiguo (3 vars distintas)
        assert "SAY" in stderr.upper(), (
            f"esperado warning mencionando :SAY no stderr. stderr={stderr!r}"
        )

    def test_hotspots_ranks_simplefn_top(
        self, metrics_project: Path, runner: CliRunner
    ) -> None:
        """hotspots: SimpleFn chamada 3x, ComplexFn 2x → SimpleFn primeiro."""
        result = runner.invoke(
            app, ["--root", str(metrics_project), "--format", "json", "hotspots"]
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        # Top deve incluir SimpleFn com n_calls>=3
        top = {r["destino"]: r["n_calls"] for r in rows}
        assert "SIMPLEFN" in top
        assert top["SIMPLEFN"] >= 3

    def test_cobertura_doc_returns_pct(
        self, metrics_project: Path, runner: CliRunner
    ) -> None:
        """cobertura-doc: 1 de 3 funcs com doc = 33%."""
        result = runner.invoke(
            app,
            [
                "--root", str(metrics_project), "--format", "json",
                "cobertura-doc", "--groupby", "source_type",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert rows
        # Pelo menos um grupo deve ter com_doc=1 (ComplexFn) de total>=3
        total_com_doc = sum(r["com_doc"] for r in rows)
        total_funcs = sum(r["total"] for r in rows)
        assert total_com_doc >= 1
        assert total_funcs >= 3


class TestMissingDb:
    def test_query_without_db_exits_2(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        # Sem init nem ingest, find deve falhar com saída amigável.
        result = runner.invoke(
            app, ["--root", str(synthetic_project), "find", "FATA050"]
        )
        assert result.exit_code == 2


class TestReindex:
    def test_reindex_single_file(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app,
            [
                "--root", str(indexed_project), "--format", "json",
                "reindex", "FATA050.prw",
            ],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["rows"][0]["arquivo"] == "FATA050.prw"
        assert payload["rows"][0]["ok"] == 1


# --- v0.7.0 Fase 0 #5: edit-prw -------------------------------------------


class TestEditPrwCheck:
    def test_prw_cp1252_exits_0(self, tmp_path: Path, runner: CliRunner) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("cp1252"))
        result = runner.invoke(app, ["--format", "json", "edit-prw", "check", str(fp)])
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["rows"][0]["match"] is True

    def test_prw_utf8_exits_1(self, tmp_path: Path, runner: CliRunner) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("utf-8"))
        result = runner.invoke(app, ["--format", "json", "edit-prw", "check", str(fp)])
        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["rows"][0]["match"] is False
        assert payload["rows"][0]["detected_encoding"] == "utf-8"

    def test_missing_file_exits_2(self, tmp_path: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app, ["edit-prw", "check", str(tmp_path / "naoexiste.prw")]
        )
        assert result.exit_code == 2


class TestEditPrwSave:
    def test_converts_utf8_to_cp1252_and_makes_backup(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("utf-8"))
        result = runner.invoke(
            app, ["--format", "json", "edit-prw", "save", str(fp)]
        )
        assert result.exit_code == 0
        assert fp.read_bytes() == "Função".encode("cp1252")
        assert (tmp_path / "foo.prw.bak").exists()
        assert (tmp_path / "foo.prw.bak").read_bytes() == "Função".encode("utf-8")

    def test_no_backup_flag(self, tmp_path: Path, runner: CliRunner) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("utf-8"))
        result = runner.invoke(
            app, ["edit-prw", "save", str(fp), "--no-backup"]
        )
        assert result.exit_code == 0
        assert not (tmp_path / "foo.prw.bak").exists()

    def test_explicit_to_utf8(self, tmp_path: Path, runner: CliRunner) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("cp1252"))
        result = runner.invoke(
            app, ["edit-prw", "save", str(fp), "--to", "utf-8", "--no-backup"]
        )
        assert result.exit_code == 0
        assert fp.read_bytes() == "Função".encode("utf-8")


class TestEditPrwOpen:
    def test_prints_cp1252_as_utf8(self, tmp_path: Path, runner: CliRunner) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("cp1252"))
        result = runner.invoke(app, ["edit-prw", "open", str(fp)])
        assert result.exit_code == 0
        # CliRunner captura stdout em bytes via mix_stderr; conteudo logico esta certo
        assert "Função" in result.stdout


class TestEditPrwStageCommit:
    """v0.8.9: aliases stage (cp1252→utf-8 antes de editar) +
    commit (utf-8→cp1252 depois). Workflow seguro pra editar .prw com Claude."""

    def test_stage_then_commit_roundtrip_preserves_bytes(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        fp = tmp_path / "foo.prw"
        original_bytes = "User Function Foo()\n  ConOut(\"Função\")\nReturn".encode("cp1252")
        fp.write_bytes(original_bytes)

        result = runner.invoke(app, ["edit-prw", "stage", str(fp)])
        assert result.exit_code == 0, result.output
        # Após stage: bytes 0xC3 0xA7 (utf-8) em vez de 0xE7 (cp1252)
        staged = fp.read_bytes()
        assert b"\xc3\xa7" in staged  # 'ç' utf-8
        assert b"\xe7" not in staged   # 'ç' cp1252 não está mais

        result2 = runner.invoke(app, ["edit-prw", "commit", str(fp)])
        assert result2.exit_code == 0, result2.output
        # Round-trip: bytes voltam ao original
        committed = fp.read_bytes()
        assert committed == original_bytes

    def test_stage_creates_backup(self, tmp_path: Path, runner: CliRunner) -> None:
        fp = tmp_path / "foo.prw"
        original = "Função".encode("cp1252")
        fp.write_bytes(original)
        result = runner.invoke(app, ["edit-prw", "stage", str(fp)])
        assert result.exit_code == 0
        bak = tmp_path / "foo.prw.bak"
        assert bak.exists()
        assert bak.read_bytes() == original


class TestEditPrwClean:
    """v0.8.11 fix bug 4: edit-prw clean remove .bak acumulado."""

    def test_clean_removes_baks_in_folder(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        (tmp_path / "a.prw.bak").write_bytes(b"old")
        (tmp_path / "b.tlpp.bak").write_bytes(b"old")
        (tmp_path / "c.txt.bak").write_bytes(b"unrelated - nao deve sumir")
        result = runner.invoke(app, ["edit-prw", "clean", str(tmp_path), "--yes"])
        assert result.exit_code == 0, result.output
        assert not (tmp_path / "a.prw.bak").exists()
        assert not (tmp_path / "b.tlpp.bak").exists()
        # .txt.bak não é de fonte ADVPL — preservado
        assert (tmp_path / "c.txt.bak").exists()

    def test_clean_dry_run_keeps_files(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        (tmp_path / "a.prw.bak").write_bytes(b"x")
        result = runner.invoke(
            app, ["edit-prw", "clean", str(tmp_path), "--dry-run"]
        )
        assert result.exit_code == 0
        assert (tmp_path / "a.prw.bak").exists()
        assert "dry-run" in result.output

    def test_clean_empty_folder_no_error(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["edit-prw", "clean", str(tmp_path), "--yes"])
        assert result.exit_code == 0
        assert "Nenhum .bak" in result.output

    def test_clean_single_file(self, tmp_path: Path, runner: CliRunner) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes(b"src")
        bak = tmp_path / "foo.prw.bak"
        bak.write_bytes(b"old")
        result = runner.invoke(app, ["edit-prw", "clean", str(fp), "--yes"])
        assert result.exit_code == 0
        assert not bak.exists()
        assert fp.exists()  # fonte original preservada
