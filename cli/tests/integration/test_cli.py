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
        b'Namespace api\nUser Function WSReg()\n  HttpPost("http://api.foo/x", oJson)\nReturn\n'
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
        self,
        indexed_project: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
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
            "version",
            "init",
            "ingest",
            "reindex",
            "status",
            "find",
            "callers",
            "callees",
            "tables",
            "param",
            "arch",
            "lint",
            "doctor",
            "grep",
            "ingest-sx",
            "impacto",
            "gatilho",
            "sx-status",
        ):
            assert cmd in result.stdout


class TestMapearCommand:
    """`mapear` — dossiê determinístico + verificação (issue #173, sem LLM)."""

    def test_md_produz_dossie_com_verificacao(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        r = runner.invoke(
            app, ["--root", str(indexed_project), "--format", "md", "mapear", "WSReg"]
        )
        assert r.exit_code == 0, r.stderr or r.stdout
        out = r.stdout
        assert "WSReg" in out
        assert "Tabelas" in out
        assert "Verificação" in out

    def test_json_estruturado(self, indexed_project: Path, runner: CliRunner) -> None:
        r = runner.invoke(
            app, ["--root", str(indexed_project), "--format", "json", "mapear", "WSReg"]
        )
        assert r.exit_code == 0, r.stderr or r.stdout
        data = json.loads(r.stdout)
        assert data["encontrado"] is True
        assert data["dossie"]["funcao"].upper() == "WSREG"
        assert "verificacao" in data

    def test_inexistente_nao_quebra(self, indexed_project: Path, runner: CliRunner) -> None:
        r = runner.invoke(
            app, ["--root", str(indexed_project), "--format", "md", "mapear", "NAOEXISTE_XYZ"]
        )
        assert r.exit_code == 0
        assert "não encontr" in r.stdout.lower()


class TestInit:
    @pytest.fixture(autouse=True)
    def _isolate_cursor_home(
        self,
        tmp_path_factory: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Isola Path.home pra cada teste do TestInit (v0.16.2+; v0.16.4 add gemini).

        Sem isso, init() chama install_cursor_rules() / install_gemini_skills()
        que detectam ~/.cursor/ ou ~/.gemini/ real do dev rodando localmente —
        escreveria rules/skills no home do dev (side-effect, não falha de teste,
        mas poluente). Aponta Path.home pra tmp diretório limpo e neutraliza
        shutil.which em ambos modulos.
        """
        fake_home = tmp_path_factory.mktemp("isolated_home_init")
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        # v0.16.5 — também mockar codex_config pra TestInit não acidentalmente
        # disparar install se dev tiver `codex` no PATH.
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)

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

    def test_init_is_idempotent(self, synthetic_project: Path, runner: CliRunner) -> None:
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

    def test_init_agents_md_is_idempotent(self, synthetic_project: Path, runner: CliRunner) -> None:
        """Segundo init não duplica fragment no AGENTS.md."""
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        content = (synthetic_project / "AGENTS.md").read_text(encoding="utf-8")
        assert content.count("<!-- BEGIN plugadvpl -->") == 1

    def test_init_fragment_has_no_unresolved_placeholders(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        """O body do fragment não pode vazar placeholders __X__ pro CLAUDE.md."""
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        content = (synthetic_project / "CLAUDE.md").read_text(encoding="utf-8")
        assert "__SLASH_NS__" not in content
        assert "__VERSION__" not in content

    def test_init_slash_namespace_env_override(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PLUGADVPL_SLASH_NS reescreve o namespace dos slash commands (fork/rebrand)."""
        monkeypatch.setenv("PLUGADVPL_SLASH_NS", "jw-advpl")
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        content = (synthetic_project / "CLAUDE.md").read_text(encoding="utf-8")
        assert "/jw-advpl:arch" in content
        assert "/jw-advpl:find" in content
        assert "/plugadvpl:" not in content


class TestInitCursorRules:
    """v0.16.2 — init detecta Cursor e gera .cursor/rules/*.mdc."""

    def test_skips_cursor_when_no_signals(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
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
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
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
        assert len(rules) == 73
        assert "Cursor rules" in result.stdout

    def test_no_cursor_flag_skips_everything(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`init --no-cursor` → zero efeito mesmo com sinais presentes."""
        fake_home = synthetic_project.parent / "fake_home"
        (fake_home / ".cursor" / "rules").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        (synthetic_project / ".cursor").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init", "--no-cursor"])
        assert result.exit_code == 0
        assert not (synthetic_project / ".cursor" / "rules").exists()
        assert not (fake_home / ".cursor" / "rules" / "plugadvpl.mdc").exists()
        assert "Cursor rules" not in result.stdout

    def test_quiet_suppresses_cursor_message(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "--quiet", "init"])
        assert result.exit_code == 0
        assert "Cursor rules" not in result.stdout
        # Verifica que rules foram criadas mesmo em quiet
        rules = list((synthetic_project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(rules) == 73

    def test_idempotent_does_not_duplicate(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dois inits seguidos → mesmo conteúdo, sem duplicar."""
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        rules = list((synthetic_project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(rules) == 73
        # Conteúdo da rule deve ter marker da versão atual (não duplicado)
        arch_content = (synthetic_project / ".cursor" / "rules" / "plugadvpl-arch.mdc").read_text(
            encoding="utf-8"
        )
        assert arch_content.count("<!-- plugadvpl-rule-version:") == 1

    def test_overwrites_rule_with_old_marker(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule com marker `0.15.0` → init sobrescreve pra versão atual."""
        from plugadvpl import __version__

        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        rules_dir = synthetic_project / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        # Plant rule fingida com marker antigo
        stale = rules_dir / "plugadvpl-arch.mdc"
        stale.write_text(
            "stale content <!-- plugadvpl-rule-version: 0.15.0 -->",
            encoding="utf-8",
        )
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        new_content = stale.read_text(encoding="utf-8")
        assert "stale content" not in new_content  # foi sobrescrita
        assert f"<!-- plugadvpl-rule-version: {__version__} -->" in new_content

    def test_preserves_user_rule_without_marker(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule plugadvpl-meu.mdc sem marker (user file) → preserva + warning."""
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        rules_dir = synthetic_project / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        # Usuário criou rule com nome conflitante — sem marker
        user_rule = rules_dir / "plugadvpl-arch.mdc"
        user_rule.write_text("my own rule, no marker here", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        # Preserva o conteúdo original
        assert user_rule.read_text(encoding="utf-8") == "my own rule, no marker here"
        # Warning sai em stderr
        assert "plugadvpl-arch.mdc" in (result.stderr or "")
        assert "sem marker plugadvpl" in (result.stderr or "")

    def test_handles_permission_error_in_global(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """~/.cursor/rules/ não-gravável → warning, init exit 0."""
        fake_home = synthetic_project.parent / "fake_home"
        (fake_home / ".cursor" / "rules").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        # Patcha _write_managed_file pra simular ERROR no global path
        from plugadvpl import cursor_rules as cr

        original = cr._write_managed_file

        def fake_write(path: Path, content: str, marker: str) -> cr.WriteOutcome:
            if "plugadvpl.mdc" in str(path) and "rules" in str(path.parent):
                if path.parent == fake_home / ".cursor" / "rules":
                    return cr.WriteOutcome.ERROR
            return original(path, content, marker)

        monkeypatch.setattr(cr, "_write_managed_file", fake_write)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0  # init NÃO quebra
        assert "Cursor rules:" in (result.stderr or "") or "Cursor rules:" in result.stdout

    def test_handles_skill_md_missing(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Skill embarcada ausente → warning, init exit 0, outras skills continuam."""
        # Edge case raro: wheel corrompido. Testa só que init não quebra.
        fake_home = synthetic_project.parent / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0


class TestInitCopilotInstructions:
    """v0.16.3 — init detecta .github/ e gera Copilot instructions."""

    def test_skips_copilot_when_no_github(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem `.github/` no projeto → no-op pra Copilot."""
        fake_home = synthetic_project.parent / "fake_home_copilot"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert not (synthetic_project / ".github").exists()
        assert "Copilot instructions" not in result.stdout

    def test_installs_when_project_has_github(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.github/` no projeto → 1 global + 52 specifics."""
        fake_home = synthetic_project.parent / "fake_home_copilot2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".github").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        # Global
        assert (synthetic_project / ".github" / "copilot-instructions.md").exists()
        # Locals
        instructions = list(
            (synthetic_project / ".github" / "instructions").glob("plugadvpl-*.instructions.md")
        )
        assert len(instructions) == 73
        assert "Copilot instructions" in result.stdout

    def test_no_copilot_flag_skips(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`--no-copilot` desabilita mesmo com .github/ presente."""
        fake_home = synthetic_project.parent / "fake_home_copilot3"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".github").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init", "--no-copilot"])
        assert result.exit_code == 0
        assert not (synthetic_project / ".github" / "copilot-instructions.md").exists()
        assert not (synthetic_project / ".github" / "instructions").exists()
        assert "Copilot instructions" not in result.stdout

    def test_quiet_suppresses_copilot_message(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_copilot4"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".github").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "--quiet", "init"])
        assert result.exit_code == 0
        assert "Copilot instructions" not in result.stdout
        # Rules ainda criadas
        instructions = list(
            (synthetic_project / ".github" / "instructions").glob("plugadvpl-*.instructions.md")
        )
        assert len(instructions) == 73

    def test_idempotent_does_not_duplicate(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_copilot5"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        (synthetic_project / ".github").mkdir()
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        instructions = list(
            (synthetic_project / ".github" / "instructions").glob("plugadvpl-*.instructions.md")
        )
        assert len(instructions) == 73
        # Marker aparece uma vez por arquivo
        arch_content = (
            synthetic_project / ".github" / "instructions" / "plugadvpl-arch.instructions.md"
        ).read_text(encoding="utf-8")
        assert arch_content.count("<!-- plugadvpl-instructions-version:") == 1

    def test_overwrites_with_old_marker(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from plugadvpl import __version__

        fake_home = synthetic_project.parent / "fake_home_copilot6"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        instructions_dir = synthetic_project / ".github" / "instructions"
        instructions_dir.mkdir(parents=True)
        stale = instructions_dir / "plugadvpl-arch.instructions.md"
        stale.write_text(
            "stale <!-- plugadvpl-instructions-version: 0.15.0 -->",
            encoding="utf-8",
        )
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        new_content = stale.read_text(encoding="utf-8")
        assert "stale" not in new_content
        assert f"<!-- plugadvpl-instructions-version: {__version__} -->" in new_content

    def test_preserves_user_file_without_marker(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_copilot7"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        instructions_dir = synthetic_project / ".github" / "instructions"
        instructions_dir.mkdir(parents=True)
        user_file = instructions_dir / "plugadvpl-arch.instructions.md"
        user_file.write_text("my own file, no marker", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        # Preserva
        assert user_file.read_text(encoding="utf-8") == "my own file, no marker"
        # Warning
        assert "plugadvpl-arch.instructions.md" in (result.stderr or "")
        assert "sem marker plugadvpl" in (result.stderr or "")


class TestInitGeminiSkills:
    """v0.16.4 — init detecta Gemini e gera GEMINI.md + skills."""

    def test_skips_gemini_when_no_signals(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem ~/.gemini/, sem gemini PATH, sem .gemini/ projeto → no-op."""
        fake_home = synthetic_project.parent / "fake_home_gemini"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert not (synthetic_project / "GEMINI.md").exists()
        assert not (synthetic_project / ".gemini").exists()
        assert "Gemini skills" not in result.stdout

    def test_installs_when_project_has_gemini_dir(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.gemini/` no projeto → project MD + 60 skills."""
        fake_home = synthetic_project.parent / "fake_home_gemini2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        (synthetic_project / ".gemini").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert (synthetic_project / "GEMINI.md").exists()
        skill_files = list((synthetic_project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md"))
        assert len(skill_files) == 73
        assert "Gemini skills" in result.stdout

    def test_installs_global_home_when_home_has_gemini(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`~/.gemini/` mockado → ~/.gemini/GEMINI.md criado."""
        fake_home = synthetic_project.parent / "fake_home_gemini3"
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        # Sem .gemini/ no projeto — só global trigger
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert (fake_home / ".gemini" / "GEMINI.md").exists()
        # Project NÃO recebe nada (sinais independentes)
        assert not (synthetic_project / "GEMINI.md").exists()

    def test_no_gemini_flag_skips_everything(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_gemini4"
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        (synthetic_project / ".gemini").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init", "--no-gemini"])
        assert result.exit_code == 0
        assert not (synthetic_project / "GEMINI.md").exists()
        assert not (fake_home / ".gemini" / "GEMINI.md").exists()
        assert "Gemini skills" not in result.stdout

    def test_quiet_suppresses_message(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_gemini5"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        (synthetic_project / ".gemini").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "--quiet", "init"])
        assert result.exit_code == 0
        assert "Gemini skills" not in result.stdout
        skill_files = list((synthetic_project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md"))
        assert len(skill_files) == 73

    def test_idempotent_does_not_duplicate(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_gemini6"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        (synthetic_project / ".gemini").mkdir()
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        skill_files = list((synthetic_project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md"))
        assert len(skill_files) == 73
        arch_content = (
            synthetic_project / ".gemini" / "skills" / "plugadvpl-arch" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert arch_content.count("<!-- plugadvpl-gemini-version:") == 1

    def test_overwrites_with_old_marker(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from plugadvpl import __version__

        fake_home = synthetic_project.parent / "fake_home_gemini7"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        skills_dir = synthetic_project / ".gemini" / "skills" / "plugadvpl-arch"
        skills_dir.mkdir(parents=True)
        stale = skills_dir / "SKILL.md"
        stale.write_text(
            "stale <!-- plugadvpl-gemini-version: 0.15.0 -->",
            encoding="utf-8",
        )
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        new_content = stale.read_text(encoding="utf-8")
        assert "stale" not in new_content
        assert f"<!-- plugadvpl-gemini-version: {__version__} -->" in new_content

    def test_preserves_user_file_without_marker(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_gemini8"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        skills_dir = synthetic_project / ".gemini" / "skills" / "plugadvpl-arch"
        skills_dir.mkdir(parents=True)
        user_file = skills_dir / "SKILL.md"
        user_file.write_text("my own skill, no marker", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert user_file.read_text(encoding="utf-8") == "my own skill, no marker"
        assert "plugadvpl-arch/SKILL.md" in (result.stderr or "")
        assert "sem marker plugadvpl" in (result.stderr or "")


class TestInitCodexConfig:
    """v0.16.5 — init grava .codex/config.toml quando Codex detectado."""

    def test_no_op_without_codex_signal(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_codex1"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert not (synthetic_project / ".codex").exists()
        assert "Codex:" not in result.stdout

    def test_installs_when_project_has_codex_dir(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_codex2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        (synthetic_project / ".codex").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert (synthetic_project / ".codex" / "config.toml").exists()
        assert "Codex:" in result.stdout

    def test_no_codex_flag_skips(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_codex3"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        (synthetic_project / ".codex").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init", "--no-codex"])
        assert result.exit_code == 0
        assert not (synthetic_project / ".codex" / "config.toml").exists()

    def test_idempotent(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_codex4"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        (synthetic_project / ".codex").mkdir()
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        content = (synthetic_project / ".codex" / "config.toml").read_text(encoding="utf-8")
        # Marker aparece UMA vez
        assert content.count("plugadvpl-codex-version:") == 1

    def test_preserves_user_file_without_marker(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_codex5"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        codex_dir = synthetic_project / ".codex"
        codex_dir.mkdir()
        user_config = codex_dir / "config.toml"
        user_config.write_text("# my own config, no marker", encoding="utf-8")
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        # Preserva
        assert user_config.read_text(encoding="utf-8") == "# my own config, no marker"


class TestInitCodexFirstClass:
    """v0.38.0 — Codex first-class: init instala skills nativas + --codex-only."""

    def test_codex_only_installs_codex_skips_others(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_cfc1"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_skills.shutil.which", lambda _: None)
        (synthetic_project / ".codex").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init", "--codex-only"])
        assert result.exit_code == 0, result.stderr or result.stdout
        assert (synthetic_project / "AGENTS.md").exists()  # Codex usa AGENTS.md
        assert not (synthetic_project / "CLAUDE.md").exists()  # pulado no codex-only
        agents = list((synthetic_project / ".agents" / "skills").glob("plugadvpl-*/SKILL.md"))
        assert agents
        # outros agentes pulados
        assert not (synthetic_project / ".cursor").exists()
        assert not (synthetic_project / "GEMINI.md").exists()
        # ignore patterns gravados
        ign = (synthetic_project / ".plugadvplignore").read_text(encoding="utf-8")
        assert ".agents/skills/**" in ign
        assert ".codex/**" in ign

    def test_init_default_installs_codex_skills_when_detected(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_cfc2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_skills.shutil.which", lambda _: None)
        (synthetic_project / ".codex").mkdir()
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0, result.stderr or result.stdout
        assert (synthetic_project / "CLAUDE.md").exists()  # default mantém CLAUDE.md
        agents = list((synthetic_project / ".agents" / "skills").glob("plugadvpl-*/SKILL.md"))
        codex = list((synthetic_project / ".codex" / "skills").glob("plugadvpl-*/SKILL.md"))
        assert agents and codex

    def test_no_codex_signal_no_skills(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = synthetic_project.parent / "fake_home_cfc3"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_skills.shutil.which", lambda _: None)
        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])
        assert result.exit_code == 0
        assert not (synthetic_project / ".agents").exists()


class TestDoctorCheckAgents:
    """v0.16.5 — plugadvpl doctor --check-agents valida arquivos gerados."""

    def test_reports_all_green_after_init(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Apos init completo com .cursor/, .github/, .gemini/ — todos green."""
        fake_home = synthetic_project.parent / "fake_home_doctor1"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        (synthetic_project / ".github").mkdir()
        (synthetic_project / ".gemini").mkdir()
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        result = runner.invoke(
            app,
            ["--root", str(synthetic_project), "doctor", "--check-agents"],
        )
        assert result.exit_code == 0, result.stderr
        assert "claude_md" in result.stdout
        assert "OK" in result.stdout  # algum check passou

    def test_reports_missing_when_no_init(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Sem init -> CLAUDE.md/AGENTS.md ausentes (exit 0, missing != fail)."""
        fake_home = synthetic_project.parent / "fake_home_doctor2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        result = runner.invoke(
            app,
            ["--root", str(synthetic_project), "doctor", "--check-agents"],
        )
        assert result.exit_code == 0, result.stderr
        assert "missing" in result.stdout.lower() or "--" in result.stdout

    def test_exit_code_1_on_fail(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLAUDE.md sem fragment markers -> check fails, exit 1."""
        fake_home = synthetic_project.parent / "fake_home_doctor3"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        (synthetic_project / "CLAUDE.md").write_text(
            "# Custom CLAUDE.md without plugadvpl fragment\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            ["--root", str(synthetic_project), "doctor", "--check-agents"],
        )
        assert result.exit_code == 1


class TestInitMultiAgent:
    """v0.16.5 — init completo com 5 agentes detectados não conflita."""

    def test_init_with_all_5_agents_detected(
        self, synthetic_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Init com .cursor/, .github/, .gemini/, .codex/ no projeto +
        ~/.cursor/, ~/.gemini/ no home → todos 5 agentes instalados."""
        fake_home = synthetic_project.parent / "fake_home_multi"
        (fake_home / ".cursor" / "rules").mkdir(parents=True)
        (fake_home / ".gemini").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("plugadvpl.cursor_rules.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.gemini_skills.shutil.which", lambda _: None)
        monkeypatch.setattr("plugadvpl.codex_config.shutil.which", lambda _: None)
        (synthetic_project / ".cursor").mkdir()
        (synthetic_project / ".github").mkdir()
        (synthetic_project / ".gemini").mkdir()
        (synthetic_project / ".codex").mkdir()

        result = runner.invoke(app, ["--root", str(synthetic_project), "init"])

        assert result.exit_code == 0
        # Claude Code
        assert (synthetic_project / "CLAUDE.md").exists()
        # Codex/AGENTS.md
        assert (synthetic_project / "AGENTS.md").exists()
        # Cursor
        assert (synthetic_project / ".cursor" / "rules").exists()
        cursor_files = list((synthetic_project / ".cursor" / "rules").glob("plugadvpl-*.mdc"))
        assert len(cursor_files) == 73
        # Copilot
        assert (synthetic_project / ".github" / "copilot-instructions.md").exists()
        copilot_files = list(
            (synthetic_project / ".github" / "instructions").glob("plugadvpl-*.instructions.md")
        )
        assert len(copilot_files) == 73
        # Gemini
        assert (synthetic_project / "GEMINI.md").exists()
        gemini_files = list((synthetic_project / ".gemini" / "skills").glob("plugadvpl-*/SKILL.md"))
        assert len(gemini_files) == 73
        # Codex
        assert (synthetic_project / ".codex" / "config.toml").exists()


class TestDocWriter:
    """v0.17.0 — plugadvpl doc-writer <funcao> gera bloco Protheus.doc."""

    def test_minimal_invocation_emits_block(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["--root", str(synthetic_project), "doc-writer", "MyFunc"])
        assert result.exit_code == 0, result.stderr
        assert "/*/{Protheus.doc} MyFunc" in result.stdout
        assert "@type function" in result.stdout
        # Bloco fecha
        assert result.stdout.rstrip().endswith("/*/")

    def test_full_metadata_via_flags(self, synthetic_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "doc-writer",
                "CalcICMS",
                "--type",
                "user_function",
                "--author",
                "Joao Silva",
                "--summary",
                "Calcula ICMS conforme TES.",
                "--since",
                "2026-05",
                "-p",
                "cTES,character,codigo TES",
                "-p",
                "[nValor],numeric,valor base opcional",
                "--return",
                "numeric,valor do ICMS",
            ],
        )
        assert result.exit_code == 0, result.stderr
        out = result.stdout
        assert "@type user_function" in out
        assert "@author Joao Silva" in out
        assert "@since 2026-05" in out
        assert "Calcula ICMS conforme TES." in out
        assert "@param cTES, character, codigo TES" in out
        assert "@param [nValor], numeric, valor base opcional" in out
        assert "@return numeric, valor do ICMS" in out

    def test_json_format(self, synthetic_project: Path, runner: CliRunner) -> None:
        """--format json emite spec_to_dict() ao invés do bloco markdown."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "--format",
                "json",
                "doc-writer",
                "X",
                "--author",
                "Joao",
                "-p",
                "n,numeric,idx",
            ],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["funcao"] == "X"
        assert payload["author"] == "Joao"
        assert len(payload["params"]) == 1
        assert payload["params"][0]["name"] == "n"

    def test_deprecated_with_reason(self, synthetic_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "doc-writer",
                "OldFunc",
                "--deprecated",
                "Use NovaFunc no lugar",
            ],
        )
        assert result.exit_code == 0, result.stderr
        assert "@deprecated Use NovaFunc no lugar" in result.stdout


class TestIngest:
    def test_ingest_after_init(self, synthetic_project: Path, runner: CliRunner) -> None:
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
        result = runner.invoke(app, ["--root", str(indexed_project), "ingest"])
        assert result.exit_code == 0
        assert "regras/lookups" in result.stderr
        assert "--no-incremental" in result.stderr
        assert "ingest" in result.stderr

    def test_ingest_incremental_warns_when_plugadvpl_version_changed(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """0.30.1 — regra de lint nova pode ser código puro (sem mudar o lookup
        bundle). Detectamos upgrade do plugadvpl comparando meta.plugadvpl_version,
        e avisamos igual (arquivos pulados não reanalisados)."""
        db = indexed_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            # simula índice gravado por uma versão antiga (sem tocar o lookup hash)
            conn.execute("UPDATE meta SET valor='0.1.0' WHERE chave='plugadvpl_version'")
            conn.commit()
        finally:
            conn.close()

        result = runner.invoke(app, ["--root", str(indexed_project), "ingest"])
        assert result.exit_code == 0
        assert "atualizado" in result.stderr
        assert "v0.1.0" in result.stderr
        assert "--no-incremental" in result.stderr

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

        result = runner.invoke(app, ["--root", str(indexed_project), "ingest", "--no-incremental"])
        assert result.exit_code == 0
        assert "--no-incremental" not in result.stderr  # sem aviso

    def test_ingest_incremental_no_warning_when_hash_unchanged(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """Caso normal: nada mudou → sem aviso amarelo."""
        result = runner.invoke(app, ["--root", str(indexed_project), "ingest"])
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

        result = runner.invoke(app, ["--root", str(indexed_project), "--quiet", "ingest"])
        assert result.exit_code == 0
        assert "Lookups" not in result.stderr


class TestFind:
    def test_find_function(self, indexed_project: Path, runner: CliRunner) -> None:
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
    def test_callers_of_fata050(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "--format", "json", "callers", "FATA050"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert any(r["arquivo"] == "MATA010.prw" for r in payload["rows"])


class TestTables:
    def test_tables_sc5(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "--format", "json", "tables", "SC5"],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert any(r["arquivo"] == "FATA050.prw" for r in payload["rows"])


class TestParam:
    def test_param_mv_localiza(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            [
                "--root",
                str(indexed_project),
                "--format",
                "json",
                "param",
                "MV_LOCALIZA",
            ],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert any(r["arquivo"] == "MATA010.prw" for r in payload["rows"])


class TestArch:
    def test_arch_fata050(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            [
                "--root",
                str(indexed_project),
                "--format",
                "json",
                "arch",
                "FATA050.prw",
            ],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["rows"][0]["arquivo"] == "FATA050.prw"

    def test_arch_missing_exits_1(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "arch", "naoexiste.prw"],
        )
        assert result.exit_code == 1


class TestStatus:
    def test_status_reports_indexed_files(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--root", str(indexed_project), "--format", "json", "status"])
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["rows"][0]["total_arquivos"] == "3"

    def test_status_includes_runtime_version(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """v0.3.12: status sempre traz `runtime_version` = __version__ do binário."""
        result = runner.invoke(app, ["--root", str(indexed_project), "--format", "json", "status"])
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
            r"<!-- plugadvpl-fragment-version: [^>]+ -->\n?",
            "",
            content,
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
            conn.execute("UPDATE meta SET valor='0.0.1-old' WHERE chave='plugadvpl_version'")
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

    def test_detects_stale_cursor_global_rule(
        self, indexed_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule global com marker old → status reporta arquivo + versão antiga."""
        fake_home = indexed_project.parent / "fake_home_status"
        rules_dir = fake_home / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "plugadvpl.mdc").write_text(
            "old <!-- plugadvpl-rule-version: 0.15.0 -->", encoding="utf-8"
        )
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        # Mensagem inclui o nome do arquivo e a versão antiga
        combined = (result.stderr or "") + result.stdout
        assert "plugadvpl.mdc" in combined
        assert "0.15.0" in combined

    def test_detects_stale_cursor_local_rule(
        self, indexed_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rule local com marker old → status reporta."""
        fake_home = indexed_project.parent / "fake_home_status2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        rules_dir = indexed_project / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "plugadvpl-arch.mdc").write_text(
            "old <!-- plugadvpl-rule-version: 0.15.0 -->", encoding="utf-8"
        )
        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        combined = (result.stderr or "") + result.stdout
        assert "plugadvpl-arch.mdc" in combined
        assert "0.15.0" in combined

    def test_status_warning_suppressed_by_quiet(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        """`--quiet` suprime o aviso (consistente com a política das outras decorações)."""
        db = indexed_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            conn.execute("UPDATE meta SET valor='0.0.1-old' WHERE chave='plugadvpl_version'")
            conn.commit()
        finally:
            conn.close()

        result = runner.invoke(app, ["--root", str(indexed_project), "--quiet", "status"])
        assert result.exit_code == 0
        assert "0.0.1-old" not in result.stderr

    def test_detects_stale_copilot_global(
        self, indexed_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.github/copilot-instructions.md` com marker old → status reporta."""
        fake_home = indexed_project.parent / "fake_home_copilot_status1"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        gh_dir = indexed_project / ".github"
        gh_dir.mkdir(parents=True, exist_ok=True)
        (gh_dir / "copilot-instructions.md").write_text(
            "stale <!-- plugadvpl-instructions-version: 0.15.0 -->",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        combined = (result.stderr or "") + result.stdout
        assert "copilot-instructions.md" in combined
        assert "0.15.0" in combined

    def test_detects_stale_copilot_local(
        self, indexed_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = indexed_project.parent / "fake_home_copilot_status2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        instructions_dir = indexed_project / ".github" / "instructions"
        instructions_dir.mkdir(parents=True)
        (instructions_dir / "plugadvpl-arch.instructions.md").write_text(
            "stale <!-- plugadvpl-instructions-version: 0.15.0 -->",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        combined = (result.stderr or "") + result.stdout
        assert "plugadvpl-arch.instructions.md" in combined
        assert "0.15.0" in combined

    def test_detects_stale_gemini_home(
        self, indexed_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`~/.gemini/GEMINI.md` com marker old → status reporta."""
        fake_home = indexed_project.parent / "fake_home_gemini_status1"
        gemini_dir = fake_home / ".gemini"
        gemini_dir.mkdir(parents=True)
        (gemini_dir / "GEMINI.md").write_text(
            "stale <!-- plugadvpl-gemini-version: 0.15.0 -->",
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        combined = (result.stderr or "") + result.stdout
        assert "GEMINI.md" in combined
        assert "0.15.0" in combined

    def test_detects_stale_gemini_project(
        self, indexed_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`<project>/GEMINI.md` com marker old → status reporta."""
        fake_home = indexed_project.parent / "fake_home_gemini_status2"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        (indexed_project / "GEMINI.md").write_text(
            "stale <!-- plugadvpl-gemini-version: 0.15.0 -->",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        combined = (result.stderr or "") + result.stdout
        assert "GEMINI.md" in combined
        assert "0.15.0" in combined

    def test_detects_stale_gemini_skill(
        self, indexed_project: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_home = indexed_project.parent / "fake_home_gemini_status3"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        skills_dir = indexed_project / ".gemini" / "skills" / "plugadvpl-arch"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "stale <!-- plugadvpl-gemini-version: 0.15.0 -->",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["--root", str(indexed_project), "status"])
        combined = (result.stderr or "") + result.stdout
        assert "SKILL.md" in combined
        assert "0.15.0" in combined


class TestDoctor:
    def test_doctor_returns_diagnostics(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--root", str(indexed_project), "--format", "json", "doctor"])
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
            b"Function U_Sample(cArg as character)\n"
            b"Return\n"
            b"\n"
            b"static function helperA()\n"
            b"Return\n"
            b"\n"
            b"Static Function HelperB()\n"
            b"Return\n"
            b"\n"
            b"function helperC()\n"
            b"Return\n"
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
            b"User Function FnAtiva()\n"
            b"Return\n"
            b"\n"
            b"/*\n"
            b"Static Function FnComentada()\n"
            b"   Return\n"
            b"Return\n"
            b"*/\n"
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
            b"User Function FnA()\nReturn\n/*\nStatic Function FnAOld()\nReturn\n*/\n"
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        result = runner.invoke(
            app,
            [
                "--root",
                str(src),
                "--format",
                "json",
                "doctor",
                "--check-funcs",
                "--detail",
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
                f"User Function {nome}()\n".encode()
                + b"Return\n"
                + b"/*\n"
                + f"Static Function {nome}Old()\nReturn\n".encode()
                + b"*/\n"
            )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        result = runner.invoke(
            app,
            [
                "--root",
                str(src),
                "--format",
                "json",
                "doctor",
                "--check-funcs",
                "--detail",
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
    def test_grep_fts_default(self, indexed_project: Path, runner: CliRunner) -> None:
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
    def test_lint_global(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--root", str(indexed_project), "--format", "json", "lint"])
        assert result.exit_code == 0, result.stderr
        # Pode estar vazio mas tem que retornar JSON válido.
        json.loads(result.stdout)

    def test_lint_arquivo_nao_indexado_avisa(self, tmp_path: Path, runner: CliRunner) -> None:
        """#118: lint num arquivo fora do índice AVISA (não parece 'limpo')."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "ZZUI.prw").write_bytes(b"User Function ZZUI()\nReturn\n")
        runner.invoke(app, ["--root", str(src), "ingest"])
        # arquivo que não existe no índice -> aviso em stderr
        r = runner.invoke(app, ["--root", str(src), "--format", "md", "lint", "inexistente.tlpp"])
        assert "não está no índice" in r.stderr
        # arquivo indexado -> SEM aviso
        r2 = runner.invoke(app, ["--root", str(src), "--format", "md", "lint", "ZZUI.prw"])
        assert "não está no índice" not in r2.stderr

    def test_lint_target_build_includes_build001(self, tmp_path: Path, runner: CliRunner) -> None:
        """--target-build inclui findings BUILD-001 (método ausente na build) via
        catálogo apis_por_build, resolvendo oVar := Classe():New() por função."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "ZZUI.prw").write_bytes(
            b"User Function ZZUI()\n"
            b"  Local oBrowse := FWMarkBrowse():New()\n"
            b'  oBrowse:SetBlkBackColor({|| "RED"})\n'
            b"Return\n"
        )
        runner.invoke(app, ["--root", str(src), "ingest"])
        # projeto fresco, sem build configurado: nenhum BUILD-001
        r0 = runner.invoke(app, ["--root", str(src), "--format", "json", "lint"])
        assert not [r for r in json.loads(r0.stdout)["rows"] if r.get("regra_id") == "BUILD-001"]
        # com a flag: BUILD-001 na linha certa
        result = runner.invoke(
            app,
            ["--root", str(src), "--format", "json", "lint", "--target-build", "24.3.0.5"],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        build = [r for r in rows if r.get("regra_id") == "BUILD-001"]
        assert len(build) == 1, f"esperado 1 BUILD-001, rows={rows}"
        assert build[0]["linha"] == 3

    def test_lint_target_build_persists_to_meta(self, tmp_path: Path, runner: CliRunner) -> None:
        """--target-build persiste em meta; lint subsequente (sem flag) reaproveita."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "ZZUI.prw").write_bytes(
            b"User Function ZZUI()\n"
            b"  Local oBrowse := FWMarkBrowse():New()\n"
            b'  oBrowse:SetBlkBackColor({|| "RED"})\n'
            b"Return\n"
        )
        runner.invoke(app, ["--root", str(src), "ingest"])
        # 1a vez: com a flag -> BUILD-001 + persiste em meta
        r1 = runner.invoke(
            app,
            ["--root", str(src), "--format", "json", "lint", "--target-build", "24.3.0.5"],
        )
        assert r1.exit_code == 0, r1.stderr
        assert [f for f in json.loads(r1.stdout)["rows"] if f.get("regra_id") == "BUILD-001"]
        # 2a vez: SEM a flag -> ainda BUILD-001 (lido do meta.target_build)
        r2 = runner.invoke(app, ["--root", str(src), "--format", "json", "lint"])
        assert r2.exit_code == 0, r2.stderr
        assert [f for f in json.loads(r2.stdout)["rows"] if f.get("regra_id") == "BUILD-001"], (
            "build-check deveria rodar automaticamente a partir de meta.target_build"
        )

    def test_callers_flags_is_self_call(self, tmp_path: Path, runner: CliRunner) -> None:
        """v0.3.18 — Bug #12 do QA report: `callers <nome>` misturava
        callsites externos com self-calls (FwLoadModel('X') dentro de X.prw)
        sem distincao. Agora cada row tem `is_self_call: bool` baseado em
        `funcao_origem == nome` OR `basename(arquivo_origem) == nome`."""
        src = tmp_path / "src"
        src.mkdir()
        # Self-call: dentro de SelfCall.prw, funcao SelfCall chama propria via FwLoadModel.
        (src / "SelfCall.prw").write_bytes(
            b'#include "totvs.ch"\n'
            b"User Function SelfCall()\n"
            b'  Local oModel := FwLoadModel("SelfCall")\n'
            b"Return\n"
        )
        # External: outro fonte chama SelfCall.
        (src / "Caller.prw").write_bytes(
            b'#include "totvs.ch"\nUser Function Caller()\n  U_SelfCall()\nReturn\n'
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

    def test_arch_flags_tabelas_via_execauto(self, tmp_path: Path, runner: CliRunner) -> None:
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
            b"User Function ExecAutoCaller()\n"
            b'  Local aCab := {{"C5_NUM", "001", Nil}}\n'
            b'  Local aIt  := {{{"C6_NUM", "001", Nil}}}\n'
            b"  Private lMsErroAuto := .F.\n"
            b"  MsExecAuto({|x,y,z| MATA410(x,y,z)}, aCab, aIt, 3)\n"
            b"  If lMsErroAuto\n"
            b"    MostraErro()\n"
            b"  EndIf\n"
            b"Return\n"
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
            / "fixtures"
            / "synthetic"
            / "reclock_alias_dup_trigger.prw"
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
            b"User Function WfSalNeg()\n"
            b'  Local oWF := TWFProcess():New("SALNEG", "Saldo Negativo")\n'
            b"  oWF:bReturn := {|o| U_WfRetSN(o)}\n"
            b"  oWF:Start()\n"
            b"Return\n"
        )
        # 2) schedule (SchedDef)
        (src / "FATR020.prw").write_bytes(
            b"User Function FATR020()\n"
            b"Return\n"
            b"\n"
            b"Static Function SchedDef()\n"
            b'  Local a := { "R", "FAT020", "SF2", {1,2}, "Faturamento" }\n'
            b"Return a\n"
        )
        # 3) multi-trigger: job_standalone + mail_send no mesmo fonte
        (src / "JobAviso.prw").write_bytes(
            b"Main Function JobAviso()\n"
            b'  RpcSetEnv("01","01",,,"FAT","JobAviso")\n'
            b'  While !File("/stop_aviso.flg")\n'
            b'    MailAuto("a@x", "b@y", "Aviso", "msg", {})\n'
            b"    Sleep(60000)\n"
            b"  EndDo\n"
            b"  RpcClearEnv()\n"
            b"Return\n"
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        return src

    def test_workflow_lists_all_kinds(self, triggers_project: Path, runner: CliRunner) -> None:
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

    def test_workflow_filter_by_kind(self, triggers_project: Path, runner: CliRunner) -> None:
        """`--kind job_standalone` retorna só jobs daemon."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(triggers_project),
                "--format",
                "json",
                "workflow",
                "--kind",
                "job_standalone",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["kind"] == "job_standalone"
        assert rows[0]["target"] == "JobAviso"

    def test_workflow_filter_by_arquivo(self, triggers_project: Path, runner: CliRunner) -> None:
        """`--arquivo JobAviso.prw` retorna 2 triggers (job + mail) do multi-source."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(triggers_project),
                "--format",
                "json",
                "workflow",
                "--arquivo",
                "JobAviso.prw",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        kinds = {r["kind"] for r in rows}
        assert kinds == {"job_standalone", "mail_send"}, (
            f"esperado job+mail no mesmo fonte, recebido {kinds}"
        )

    def test_workflow_filter_by_target(self, triggers_project: Path, runner: CliRunner) -> None:
        """`--target FAT020` (pergunte SX1) localiza o schedule."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(triggers_project),
                "--format",
                "json",
                "workflow",
                "--target",
                "FAT020",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["kind"] == "schedule"

    def test_workflow_rejects_invalid_kind(self, triggers_project: Path, runner: CliRunner) -> None:
        """v0.4.4 (UX #4): --kind invalido rejeitado com mensagem clara."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(triggers_project),
                "workflow",
                "--kind",
                "tipoinexistente",
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
            b"User Function WfA()\n"
            b'   oWF := TWFProcess():New("CONFLITO", "Workflow A")\n'
            b"   oWF:Start()\n"
            b"Return\n"
        )
        (src / "WfB.prw").write_bytes(
            b"User Function WfB()\n"
            b'   oWF := TWFProcess():New("CONFLITO", "Workflow B (diferente)")\n'
            b"   oWF:Start()\n"
            b"Return\n"
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

    def test_workflow_persisted_in_db(self, triggers_project: Path) -> None:
        """Sanity check: execution_triggers tabela existe e tem rows do ingest."""
        db = triggers_project / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM execution_triggers").fetchone()[0]
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
            b"User Function ABCCOMBO()\n"
            b"   MsExecAuto({|x,y,z| MATA410(x,y,z)}, aCab, aIt, 3)\n"
            b"Return\n"
        )
        # FINA050 inclusao — SE2.
        (src / "ABCFIN50.prw").write_bytes(
            b"User Function ABCFIN50()\n   MsExecAuto({|x,y| FINA050(x,y)}, aArr, 3)\nReturn\n"
        )
        # Dynamic — &(cVar).
        (src / "ABCDYN.prw").write_bytes(
            b"User Function ABCDYN()\n"
            b"   MsExecAuto({|x,y,z| &(cRot).(x,y,z)}, aCab, aIt, 3)\n"
            b"Return\n"
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        return src

    def test_execauto_lists_all(self, execauto_project: Path, runner: CliRunner) -> None:
        """Sem filtro: lista as 3 chamadas (MATA410, FINA050, dynamic)."""
        result = runner.invoke(
            app, ["--root", str(execauto_project), "--format", "json", "execauto"]
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 3
        routines = {r["routine"] or "(dynamic)" for r in rows}
        assert routines == {"MATA410", "FINA050", "(dynamic)"}

    def test_execauto_filter_by_routine(self, execauto_project: Path, runner: CliRunner) -> None:
        """`--routine MATA410` retorna só a chamada com SC5/SC6."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(execauto_project),
                "--format",
                "json",
                "execauto",
                "--routine",
                "MATA410",
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

    def test_execauto_filter_by_modulo(self, execauto_project: Path, runner: CliRunner) -> None:
        """`--modulo SIGAFIN` localiza só FINA050."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(execauto_project),
                "--format",
                "json",
                "execauto",
                "--modulo",
                "SIGAFIN",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["routine"] == "FINA050"

    def test_execauto_filter_dynamic_only(self, execauto_project: Path, runner: CliRunner) -> None:
        """`--dynamic` retorna só calls não-resolvíveis."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(execauto_project),
                "--format",
                "json",
                "execauto",
                "--dynamic",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["routine"] == "(dynamic)"

    def test_execauto_filter_op_inc(self, execauto_project: Path, runner: CliRunner) -> None:
        """`--op inc` retorna só inclusões (op_code=3)."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(execauto_project),
                "--format",
                "json",
                "execauto",
                "--op",
                "inc",
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
                "--root",
                str(execauto_project),
                "--format",
                "json",
                "arch",
                "ABCCOMBO.prw",
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
                "--root",
                str(execauto_project),
                "--format",
                "json",
                "arch",
                "ABCDYN.prw",
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
                "--root",
                str(execauto_project),
                "execauto",
                "--modulo",
                "SIGAINEXISTENTE",
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
                "--root",
                str(execauto_project),
                "execauto",
                "--arquivo",
                "NAOEXISTE.prw",
            ],
        )
        assert result.exit_code == 0
        assert "ingest --no-incremental" not in (result.stderr or ""), (
            f"filtro com valor inexistente NAO deve sugerir reingest "
            f"(estava sugerindo desnecessariamente). stderr: {result.stderr!r}"
        )

    def test_execauto_rejects_invalid_op(self, execauto_project: Path, runner: CliRunner) -> None:
        """v0.4.4 (UX #4): --op invalida deve ser rejeitada com mensagem
        clara antes de chegar na query (vs antes que retornava vazio sem
        aviso).
        """
        result = runner.invoke(
            app,
            [
                "--root",
                str(execauto_project),
                "execauto",
                "--op",
                "invalida",
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
            b"/*/{Protheus.doc} MT460FIM\n"
            b"Ponto de Entrada apos faturamento.\n"
            b"@type user function\n"
            b"@author Fernando Vernier\n"
            b"@since 18/10/2025\n"
            b"@version 2.0\n"
            b'@param cNumNF, character, "Numero da NF"\n'
            b'@return logical, ".T. se sucesso"\n'
            b"/*/\n"
            b"User Function MT460FIM(cNumNF)\n"
            b"Return .T.\n"
        )
        # 2) Deprecated
        (src / "MT460OLD.tlpp").write_bytes(
            b"/*/{Protheus.doc} MT460OLD\n"
            b"Versao antiga do PE.\n"
            b"@type user function\n"
            b"@author Joao\n"
            b"@deprecated Use MT460FIM no lugar\n"
            b"/*/\n"
            b"User Function MT460OLD()\n"
            b"Return\n"
        )
        # 3) Órfão (sem doc) — gera BP-007.
        (src / "MT460NEW.tlpp").write_bytes(
            b'User Function MT460NEW()\n   ConOut("sem doc")\nReturn\n'
        )
        runner.invoke(app, ["--root", str(tmp_path / "src"), "init"])
        runner.invoke(app, ["--root", str(tmp_path / "src"), "ingest"])
        return tmp_path / "src"

    def test_docs_lists_all(self, docs_project: Path, runner: CliRunner) -> None:
        """Sem filtro: lista 2 docs (MT460FIM + MT460OLD; órfão NÃO aparece aqui)."""
        result = runner.invoke(app, ["--root", str(docs_project), "--format", "json", "docs"])
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 2
        funcs = {r["funcao"] for r in rows}
        assert funcs == {"MT460FIM", "MT460OLD"}

    def test_docs_filter_by_modulo(self, docs_project: Path, runner: CliRunner) -> None:
        """Path `src/SIGAFAT/...` infere SIGAFAT."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(docs_project),
                "--format",
                "json",
                "docs",
                "SIGAFAT",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 2
        for r in rows:
            assert r["modulo"] == "SIGAFAT"

    def test_docs_filter_deprecated(self, docs_project: Path, runner: CliRunner) -> None:
        """`--deprecated` retorna só MT460OLD."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(docs_project),
                "--format",
                "json",
                "docs",
                "--deprecated",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["funcao"] == "MT460OLD"
        assert rows[0]["deprecated"] == "sim"

    def test_docs_filter_author(self, docs_project: Path, runner: CliRunner) -> None:
        """`--author Fernando` LIKE match localiza só MT460FIM."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(docs_project),
                "--format",
                "json",
                "docs",
                "--author",
                "Fernando",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert len(rows) == 1
        assert rows[0]["funcao"] == "MT460FIM"

    def test_docs_show_renders_markdown(self, docs_project: Path, runner: CliRunner) -> None:
        """`--show MT460FIM` retorna Markdown estruturado."""
        result = runner.invoke(app, ["--root", str(docs_project), "docs", "--show", "MT460FIM"])
        assert result.exit_code == 0, result.stderr
        out = result.stdout
        assert "## MT460FIM" in out
        assert "SIGAFAT" in out
        assert "Fernando Vernier" in out
        assert "### Parâmetros" in out
        assert "cNumNF" in out
        assert "### Retorno" in out

    def test_docs_show_not_found_exits_1(self, docs_project: Path, runner: CliRunner) -> None:
        """`--show <inexistente>` retorna exit 1."""
        result = runner.invoke(
            app, ["--root", str(docs_project), "docs", "--show", "FnInexistente"]
        )
        assert result.exit_code == 1

    def test_docs_orphans_lists_bp007(self, docs_project: Path, runner: CliRunner) -> None:
        """`--orphans` lista funções sem header (cross-ref BP-007)."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(docs_project),
                "--format",
                "json",
                "docs",
                "--orphans",
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
            b"/*/{Protheus.doc} HomFn\nDoc do A.\n@author Anna\n/*/\n"
            b"User Function HomFn()\nReturn\n"
        )
        (src / "FnB.prw").write_bytes(
            b"/*/{Protheus.doc} HomFn\nDoc do B.\n@author Beto\n/*/\n"
            b"User Function HomFn()\nReturn\n"
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])

        # Sem --arquivo: aviso em stderr + mostra primeiro alfabeticamente
        result = runner.invoke(app, ["--root", str(src), "docs", "--show", "HomFn"])
        assert result.exit_code == 0
        assert "2 fontes" in result.stderr or "Aviso" in result.stderr
        assert "Anna" in result.stdout  # FnA.prw vem antes alfabeticamente

        # Com --arquivo FnB.prw: mostra o do Beto
        result2 = runner.invoke(
            app, ["--root", str(src), "docs", "--show", "HomFn", "--arquivo", "FnB.prw"]
        )
        assert result2.exit_code == 0
        assert "Beto" in result2.stdout

    def test_docs_show_ws_constructs_end_to_end(self, tmp_path: Path, runner: CliRunner) -> None:
        """v0.4.4 (BUG #2): docs --funcao e --show funcionam pra
        WSSTRUCT/WSSERVICE/WSMETHOD (antes ficavam órfãos)."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "MyWS.tlpp").write_bytes(
            b"/*/{Protheus.doc} WSXDATA\n@type property\n/*/\n"
            b"WSSTRUCT WSXDATA\n"
            b"   WSDATA cId AS STRING\n"
            b"ENDWSSTRUCT\n"
            b"\n"
            b"/*/{Protheus.doc} MyWS\n@type class\n/*/\n"
            b'WSSERVICE MyWS DESCRIPTION "Servico"\n'
            b"\n"
            b"/*/{Protheus.doc} GravData\n@type method\n/*/\n"
            b'WSMETHOD GravData DESCRIPTION "Grava" WSSERVICE MyWS\n'
            b"   Local lOk := .T.\n"
            b"Return lOk\n"
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
        r = runner.invoke(app, ["--root", str(src), "docs", "--show", "GravData"])
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
            b"/*/{Protheus.doc} U_MyCmp\n"
            b"Helper que toca SA1 via ExecAuto.\n"
            b"@type user function\n@author Tester\n"
            b"/*/\n"
            b"User Function U_MyCmp()\n"
            b"   Local aCab := {}\n"
            b"   MsExecAuto({|x,y,z| MATA410(x,y,z)}, aCab, {}, 3)\n"
            b'   dbSelectArea("SA1")\n'
            b'   SA1->A1_COD := "001"\n'
            b"Return\n"
        )
        # Fonte que chama U_MyCmp
        (src / "Caller.prw").write_bytes(b"User Function CallerFn()\n   U_MyCmp()\nReturn\n")
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

    def test_trace_funcao_via_execauto(self, trace_project: Path, runner: CliRunner) -> None:
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

    def test_trace_filter_universo(self, trace_project: Path, runner: CliRunner) -> None:
        """--universo 3 limita a hits do Universo 3 (workflow/execauto/docs)."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(trace_project),
                "--format",
                "json",
                "trace",
                "U_MyCmp",
                "--universo",
                "3",
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
                    i
                    for i, r in enumerate(u2)
                    if r["edge"] not in ("table_definition", "n_fields", "field_definition")
                ]
                if outras_u2:
                    assert tdef_idx < min(outras_u2), (
                        f"table_definition (idx={tdef_idx}) deve vir antes "
                        f"de outras edges U2 (min idx={min(outras_u2)})"
                    )

    def test_trace_tipo_override(self, trace_project: Path, runner: CliRunner) -> None:
        """--tipo força quando auto-detect erra."""
        # SA1 vira tabela por default; com --tipo funcao, busca como função
        result = runner.invoke(
            app,
            [
                "--root",
                str(trace_project),
                "trace",
                "SA1",
                "--tipo",
                "funcao",
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

    def test_trace_invalid_universo_rejected(self, trace_project: Path, runner: CliRunner) -> None:
        """--universo com valor inválido sai com erro amigável."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(trace_project),
                "trace",
                "U_MyCmp",
                "--universo",
                "abc",
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
        (src / "Simple.prw").write_bytes(b"User Function SimpleFn(cArg)\n   Return Nil\n")
        # ComplexFn: CC alta (5+), nesting 3+
        (src / "Complex.prw").write_bytes(
            b"/*/{Protheus.doc} U_ComplexFn\nHelper.\n@type user function\n/*/\n"
            b"User Function ComplexFn(cArg, nVal)\n"
            b"   Local i, j\n"
            b'   If cArg == "A"\n'
            b"      For i := 1 To 10\n"
            b"         If i % 2 == 0\n"
            b"            For j := 1 To 5\n"
            b"               If j > 3\n"
            b'                  ConOut("aa")\n'
            b"               EndIf\n"
            b"            Next j\n"
            b"         EndIf\n"
            b"      Next i\n"
            b'   ElseIf cArg == "B"\n'
            b'      ConOut("b")\n'
            b"   EndIf\n"
            b"Return Nil\n"
        )
        # CallerFn: chama SimpleFn 3x e ComplexFn 2x → hotspots
        (src / "Caller.prw").write_bytes(
            b"User Function CallerFn()\n"
            b'   U_SimpleFn("x")\n'
            b'   U_SimpleFn("y")\n'
            b'   U_SimpleFn("z")\n'
            b'   U_ComplexFn("A", 1)\n'
            b'   U_ComplexFn("B", 2)\n'
            b"Return\n"
        )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        return src

    def test_metrics_lists_all_functions(self, metrics_project: Path, runner: CliRunner) -> None:
        """metrics lista todas as funções com cc/loc/nesting."""
        result = runner.invoke(app, ["--root", str(metrics_project), "--format", "json", "metrics"])
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

    def test_metrics_filter_min_cc(self, metrics_project: Path, runner: CliRunner) -> None:
        """--min-cc 5 retorna só ComplexFn (SimpleFn CC=1, CallerFn CC=1)."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(metrics_project),
                "--format",
                "json",
                "metrics",
                "--min-cc",
                "5",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        funcs = {r["funcao"] for r in rows}
        assert "ComplexFn" in funcs
        assert "SimpleFn" not in funcs

    def test_metrics_sort_loc(self, metrics_project: Path, runner: CliRunner) -> None:
        """--sort loc retorna ComplexFn primeiro (mais linhas)."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(metrics_project),
                "--format",
                "json",
                "metrics",
                "--sort",
                "loc",
            ],
        )
        assert result.exit_code == 0, result.stderr
        rows = json.loads(result.stdout)["rows"]
        assert rows[0]["funcao"] == "ComplexFn"

    def test_hotspots_method_dedup_warning(self, tmp_path: Path, runner: CliRunner) -> None:
        """v0.6.1 (bug #1): hotspots emite warning quando detecta múltiplas
        variáveis VAR:METODO compartilhando o mesmo método (provavelmente
        mesma classe acessada via vars diferentes — ex: TPrinter:Say via
        oPrint/oPrn/oPrinter).
        """
        src = tmp_path / "src"
        src.mkdir()
        # 3 fontes que chamam TPrinter:Say via vars com nomes diferentes
        (src / "FnA.prw").write_bytes(
            b"User Function FnA()\n"
            b"   Local oPrint := TPrinter():New()\n"
            b'   oPrint:Say(1, "x")\n'
            b'   oPrint:Say(2, "y")\n'
            b"Return\n"
        )
        (src / "FnB.prw").write_bytes(
            b'User Function FnB()\n   Local oPrn := TPrinter():New()\n   oPrn:Say(1, "x")\nReturn\n'
        )
        (src / "FnC.prw").write_bytes(
            b"User Function FnC()\n"
            b"   Local oPrinter := TPrinter():New()\n"
            b'   oPrinter:Say(1, "x")\n'
            b"Return\n"
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

    def test_hotspots_ranks_simplefn_top(self, metrics_project: Path, runner: CliRunner) -> None:
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

    def test_cobertura_doc_returns_pct(self, metrics_project: Path, runner: CliRunner) -> None:
        """cobertura-doc: 1 de 3 funcs com doc = 33%."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(metrics_project),
                "--format",
                "json",
                "cobertura-doc",
                "--groupby",
                "source_type",
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
    def test_query_without_db_exits_2(self, synthetic_project: Path, runner: CliRunner) -> None:
        # Sem init nem ingest, find deve falhar com saída amigável.
        result = runner.invoke(app, ["--root", str(synthetic_project), "find", "FATA050"])
        assert result.exit_code == 2


class TestReindex:
    def test_reindex_single_file(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            [
                "--root",
                str(indexed_project),
                "--format",
                "json",
                "reindex",
                "FATA050.prw",
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
        result = runner.invoke(app, ["edit-prw", "check", str(tmp_path / "naoexiste.prw")])
        assert result.exit_code == 2


class TestEditPrwSave:
    def test_converts_utf8_to_cp1252_and_makes_backup(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("utf-8"))
        result = runner.invoke(app, ["--format", "json", "edit-prw", "save", str(fp)])
        assert result.exit_code == 0
        assert fp.read_bytes() == "Função".encode("cp1252")
        assert (tmp_path / "foo.prw.bak").exists()
        assert (tmp_path / "foo.prw.bak").read_bytes() == "Função".encode("utf-8")

    def test_no_backup_flag(self, tmp_path: Path, runner: CliRunner) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("utf-8"))
        result = runner.invoke(app, ["edit-prw", "save", str(fp), "--no-backup"])
        assert result.exit_code == 0
        assert not (tmp_path / "foo.prw.bak").exists()

    def test_explicit_to_utf8(self, tmp_path: Path, runner: CliRunner) -> None:
        fp = tmp_path / "foo.prw"
        fp.write_bytes("Função".encode("cp1252"))
        result = runner.invoke(app, ["edit-prw", "save", str(fp), "--to", "utf-8", "--no-backup"])
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
        original_bytes = 'User Function Foo()\n  ConOut("Função")\nReturn'.encode("cp1252")
        fp.write_bytes(original_bytes)

        result = runner.invoke(app, ["edit-prw", "stage", str(fp)])
        assert result.exit_code == 0, result.output
        # Após stage: bytes 0xC3 0xA7 (utf-8) em vez de 0xE7 (cp1252)
        staged = fp.read_bytes()
        assert b"\xc3\xa7" in staged  # 'ç' utf-8
        assert b"\xe7" not in staged  # 'ç' cp1252 não está mais

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

    def test_clean_removes_baks_in_folder(self, tmp_path: Path, runner: CliRunner) -> None:
        (tmp_path / "a.prw.bak").write_bytes(b"old")
        (tmp_path / "b.tlpp.bak").write_bytes(b"old")
        (tmp_path / "c.txt.bak").write_bytes(b"unrelated - nao deve sumir")
        result = runner.invoke(app, ["edit-prw", "clean", str(tmp_path), "--yes"])
        assert result.exit_code == 0, result.output
        assert not (tmp_path / "a.prw.bak").exists()
        assert not (tmp_path / "b.tlpp.bak").exists()
        # .txt.bak não é de fonte ADVPL — preservado
        assert (tmp_path / "c.txt.bak").exists()

    def test_clean_dry_run_keeps_files(self, tmp_path: Path, runner: CliRunner) -> None:
        (tmp_path / "a.prw.bak").write_bytes(b"x")
        result = runner.invoke(app, ["edit-prw", "clean", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
        assert (tmp_path / "a.prw.bak").exists()
        assert "dry-run" in result.output

    def test_clean_empty_folder_no_error(self, tmp_path: Path, runner: CliRunner) -> None:
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


class TestMigrateTlppInit:
    """v0.18.0 — plugadvpl migrate-tlpp init analisa projeto sem tocar nada."""

    def test_init_lists_candidates_in_synthetic_project(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        # Cria 2 .prw sintéticos
        (synthetic_project / "src").mkdir(exist_ok=True)
        (synthetic_project / "src" / "a.prw").write_text(
            "User Function A()\nReturn .T.\n",
            encoding="cp1252",
        )
        (synthetic_project / "src" / "b.prw").write_text(
            "User Function B()\nReturn .T.\n",
            encoding="cp1252",
        )
        result = runner.invoke(
            app,
            ["--root", str(synthetic_project), "migrate-tlpp", "init", "src"],
        )
        assert result.exit_code == 0, result.stderr
        # output menciona 2 arquivos
        assert "a.prw" in result.stdout or "a.prw" in result.stderr
        assert "b.prw" in result.stdout or "b.prw" in result.stderr

    def test_init_format_json(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        (synthetic_project / "src").mkdir(exist_ok=True)
        (synthetic_project / "src" / "a.prw").write_text(
            "body",
            encoding="cp1252",
        )
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "--format",
                "json",
                "migrate-tlpp",
                "init",
                "src",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["total"] >= 1

    def test_init_does_not_modify_files(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        (synthetic_project / "src").mkdir(exist_ok=True)
        f = synthetic_project / "src" / "a.prw"
        original = "User Function A()\nReturn .T.\n"
        f.write_text(original, encoding="cp1252")
        runner.invoke(
            app,
            ["--root", str(synthetic_project), "migrate-tlpp", "init", "src"],
        )
        # Read-only: arquivo intacto
        assert f.read_text(encoding="cp1252") == original


class TestMigrateTlppRename:
    """v0.18.0 — plugadvpl migrate-tlpp rename: subset conservador (convert + rename)."""

    def test_rename_diff_only_without_write(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        f = synthetic_project / "a.prw"
        f.write_text("body", encoding="cp1252")
        result = runner.invoke(
            app,
            ["--root", str(synthetic_project), "migrate-tlpp", "rename", "a.prw"],
        )
        assert result.exit_code == 0
        # diff so, .prw permanece
        assert f.exists()
        assert not (synthetic_project / "a.tlpp").exists()

    def test_rename_write_applies_rename_and_encoding(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        # Validate=False default pra rename (mais conservador)
        f = synthetic_project / "a.prw"
        f.write_text("body", encoding="cp1252")
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "migrate-tlpp",
                "rename",
                "a.prw",
                "--write",
                "--allow-dirty",
            ],
        )
        assert result.exit_code == 0
        assert (synthetic_project / "a.tlpp").exists()
        assert not f.exists()


class TestMigrateTlppRecipes:
    """v0.18.0 — plugadvpl migrate-tlpp recipes: pipeline completo."""

    def test_recipes_diff_only_default(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        f = synthetic_project / "a.prw"
        f.write_text("User Function X()\nReturn\n", encoding="cp1252")
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "migrate-tlpp",
                "recipes",
                "a.prw",
                "--no-impact-check",
                "--allow-dirty",
            ],
        )
        assert result.exit_code == 0
        # .prw intacto (sem --write)
        assert f.exists()
        assert not (synthetic_project / "a.tlpp").exists()

    def test_recipes_write_applies(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        f = synthetic_project / "a.prw"
        f.write_text("User Function X()\nReturn\n", encoding="cp1252")
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "migrate-tlpp",
                "recipes",
                "a.prw",
                "--write",
                "--no-impact-check",
                "--allow-dirty",
            ],
        )
        assert result.exit_code == 0
        # .tlpp criado
        assert (synthetic_project / "a.tlpp").exists()

    def test_recipes_idioms_runs_all_11(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        f = synthetic_project / "SIGAFAT" / "a.prw"
        f.parent.mkdir(exist_ok=True)
        f.write_text("User Function X()\nReturn\n", encoding="cp1252")
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "migrate-tlpp",
                "recipes",
                "SIGAFAT/a.prw",
                "--idioms",
                "--no-impact-check",
                "--allow-dirty",
            ],
        )
        assert result.exit_code == 0

    def test_recipes_validate_rollback_when_compile_fails(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        f = synthetic_project / "a.prw"
        original = "User Function X()\nReturn\n"
        f.write_text(original, encoding="cp1252")
        # Mock _validate_via_compile pra retornar False (compile falha)
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._validate_via_compile",
            lambda _p: False,
        )
        runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "migrate-tlpp",
                "recipes",
                "a.prw",
                "--write",
                "--validate",
                "--no-impact-check",
                "--allow-dirty",
            ],
        )
        # Rollback restaura .prw
        assert f.exists()
        assert f.read_text(encoding="cp1252") == original

    def test_recipes_format_json(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        f = synthetic_project / "a.prw"
        f.write_text("body", encoding="cp1252")
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "--format",
                "json",
                "migrate-tlpp",
                "recipes",
                "a.prw",
                "--no-impact-check",
                "--allow-dirty",
            ],
        )
        assert result.exit_code == 0
        # JSON output parseavel
        payload = json.loads(result.stdout)
        assert "recipes" in payload or "rows" in payload


class TestMigrateTlppTodos:
    """v0.18.0 — plugadvpl migrate-tlpp todos: lista @plugadvpl-todo em .tlpp."""

    def test_todos_empty_when_no_markers(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        (synthetic_project / "x.tlpp").write_text(
            "function u_x()\nreturn .T.\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            ["--root", str(synthetic_project), "migrate-tlpp", "todos"],
        )
        assert result.exit_code == 0
        assert (
            "nenhum" in result.stdout.lower()
            or "0" in result.stdout
            or "nenhum" in result.stderr.lower()
        )

    def test_todos_lists_markers(
        self,
        synthetic_project: Path,
        runner: CliRunner,
    ) -> None:
        (synthetic_project / "y.tlpp").write_text(
            "// @plugadvpl-todo:namespace-infer revise manualmente\nnamespace x\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            ["--root", str(synthetic_project), "migrate-tlpp", "todos"],
        )
        assert result.exit_code == 0
        # rich table renderiza em stderr (output.py:err_console); aceita ambos
        combined = result.stdout + (result.stderr or "")
        assert "namespace-infer" in combined
        assert "y.tlpp" in combined


class TestMigrateTlppRollbackCascade:
    """v0.18.0 — cascata de rollback (spec §4.2.4) ponta-a-ponta via CLI.

    Cobre os 3 caminhos quando ``--validate`` falha:
    1. ``.bak.<timestamp>`` mais antigo restaura `.prw` (caminho default).
    2. Bak ausente -> ``git checkout HEAD -- <file>`` (fallback 1).
    3. Bak ausente + git falha -> ``typer.Exit(code=2)`` (CRITICAL).
    """

    def test_rollback_via_bak_when_compile_fails(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Compile fails -> rollback via .bak.<timestamp> restaura .prw."""
        f = synthetic_project / "rb1.prw"
        original = "User Function RB1()\nReturn .T.\n"
        f.write_text(original, encoding="cp1252")
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._validate_via_compile",
            lambda _p: False,
        )
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "migrate-tlpp",
                "recipes",
                "rb1.prw",
                "--write",
                "--validate",
                "--no-impact-check",
                "--allow-dirty",
            ],
        )
        # .prw restaurado pelo .bak.<ts>; .tlpp removido
        assert f.exists()
        assert f.read_text(encoding="cp1252") == original
        assert not (synthetic_project / "rb1.tlpp").exists()
        # exit_code != 2 (rollback bem-sucedido via bak)
        assert result.exit_code != 2

    def test_rollback_via_git_when_bak_missing(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bak ausente -> fallback git checkout funciona, exit != 2."""
        f = synthetic_project / "rb2.prw"
        f.write_text("User Function RB2()\nReturn\n", encoding="cp1252")
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._validate_via_compile",
            lambda _p: False,
        )
        # Forca _create_backup retornar None (sem bak)
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._create_backup",
            lambda _p: None,
        )

        # Fake git restore: escreve conteudo "restored" no .prw
        def fake_git_restore(file_path: Path, _project_root: Path) -> bool:
            file_path.write_text("RESTORED VIA GIT", encoding="cp1252")
            return True

        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._restore_via_git",
            fake_git_restore,
        )
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "migrate-tlpp",
                "recipes",
                "rb2.prw",
                "--write",
                "--validate",
                "--no-impact-check",
                "--allow-dirty",
            ],
        )
        # Git restore aplicado; exit != 2 (cascade nao chegou no abort)
        assert result.exit_code != 2

    def test_rollback_failed_exit_2(
        self,
        synthetic_project: Path,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bak missing + git falha -> typer.Exit(code=2) propagado pelo runner."""
        f = synthetic_project / "rb3.prw"
        f.write_text("User Function RB3()\nReturn\n", encoding="cp1252")
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._validate_via_compile",
            lambda _p: False,
        )
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._create_backup",
            lambda _p: None,
        )
        monkeypatch.setattr(
            "plugadvpl.migrate_tlpp._restore_via_git",
            lambda _f, _r: False,
        )
        result = runner.invoke(
            app,
            [
                "--root",
                str(synthetic_project),
                "migrate-tlpp",
                "recipes",
                "rb3.prw",
                "--write",
                "--validate",
                "--no-impact-check",
                "--allow-dirty",
            ],
        )
        # CRITICAL: cascata exauriu -> exit 2 propagado
        assert result.exit_code == 2


class TestIngestPoui:
    def test_reporta_incompativel(self, runner: CliRunner, tmp_path: Path) -> None:
        proj = tmp_path / "front"
        proj.mkdir()
        (proj / "package.json").write_text(
            '{"dependencies": {"@angular/core": "^19.0.0", "@po-ui/ng-components": "21.18.0"}}',
            encoding="utf-8",
        )
        # o comando bootstrapa o DB sozinho — NÃO precisa de `init` prévio.
        result = runner.invoke(app, ["--root", str(tmp_path), "ingest-poui", str(tmp_path)])
        assert result.exit_code == 0
        combined = (result.stderr or "") + result.stdout
        assert "21.18.0" in combined
        assert "NAO" in combined or "19" in combined  # compativel=NAO ou angular major 19


class TestPouiComponentes:
    def test_lista_todos_sem_filtro(self, runner: CliRunner, tmp_path: Path) -> None:
        """poui-componentes sem argumento lista todos os bindings (>900)."""
        result = runner.invoke(
            app,
            ["--root", str(tmp_path), "--format", "json", "--limit", "0", "poui-componentes"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)["rows"]
        assert len(data) > 900

    def test_filtra_po_table_mostra_p_columns(self, runner: CliRunner, tmp_path: Path) -> None:
        """poui-componentes po-table deve conter p-columns."""
        result = runner.invoke(
            app, ["--root", str(tmp_path), "--format", "json", "poui-componentes", "po-table"]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)["rows"]
        bindings = {r["binding"] for r in data}
        assert "p-columns" in bindings

    def test_componente_inexistente_retorna_vazio(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["--root", str(tmp_path), "--format", "json", "poui-componentes", "po-nao-existe"]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)["rows"]
        assert data == []


class TestPouiLintCmd:
    def test_poui_lint_mostra_finding(self, runner: CliRunner, tmp_path: Path) -> None:
        """poui-lint deve retornar finding POUI-PROP para binding inexistente."""
        import json

        proj = tmp_path / "front"
        (proj / "src").mkdir(parents=True)
        (proj / "package.json").write_text(
            '{"dependencies": {"@po-ui/ng-components": "21.0.0"}}', encoding="utf-8"
        )
        (proj / "src" / "app.html").write_text(
            "<po-button p-fake='x'></po-button>", encoding="utf-8"
        )
        runner.invoke(app, ["--root", str(tmp_path), "ingest-poui", str(tmp_path)])
        result = runner.invoke(app, ["--root", str(tmp_path), "--format", "json", "poui-lint"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        rows = data["rows"] if isinstance(data, dict) else data
        assert any(r["regra"] == "POUI-PROP" and "p-fake" in r["alvo"] for r in rows)

    def test_poui_lint_iface_mostra_finding(self, runner: CliRunner, tmp_path: Path) -> None:
        """poui-lint deve retornar finding POUI-IFACE para chave/valor de interface inválido."""
        import json

        proj = tmp_path / "front"
        (proj / "src").mkdir(parents=True)
        (proj / "package.json").write_text(
            '{"dependencies": {"@po-ui/ng-components": "21.0.0"}}', encoding="utf-8"
        )
        (proj / "src" / "app.component.ts").write_text(
            "x: PoTableColumn[] = [ { field: 'a', type: 'money' } ];", encoding="utf-8"
        )
        runner.invoke(app, ["--root", str(tmp_path), "ingest-poui", str(tmp_path)])
        result = runner.invoke(app, ["--root", str(tmp_path), "--format", "json", "poui-lint"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        rows = data["rows"] if isinstance(data, dict) else data
        regras = {r["regra"] for r in rows}
        assert "POUI-IFACE" in regras
        assert any("field" in r["alvo"] for r in rows)  # chave inexistente
        assert any("money" in r["mensagem"] for r in rows)  # valor fora do enum

    def test_poui_lint_sem_findings_retorna_vazio(self, runner: CliRunner, tmp_path: Path) -> None:
        """poui-lint sem dados de ingest deve retornar lista vazia."""
        import json

        result = runner.invoke(app, ["--root", str(tmp_path), "--format", "json", "poui-lint"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        rows = data["rows"] if isinstance(data, dict) else data
        assert rows == []


class TestPouiBridge:
    def test_bridge_lista_match(self, runner: CliRunner, tmp_path: Path) -> None:
        # Front: projeto POUI com 1 service chamando /pedidos
        proj = tmp_path / "front"
        (proj / "src").mkdir(parents=True)
        (proj / "package.json").write_text(
            '{"dependencies": {"@po-ui/ng-components": "15.0.0"}}', encoding="utf-8"
        )
        (proj / "src" / "p.service.ts").write_text(
            "f(){return this.http.get('/pedidos');}", encoding="utf-8"
        )
        # Back: fonte TLPP com @Get /pedidos
        (tmp_path / "PEDREST.tlpp").write_text(
            '@Get("/pedidos")\nMethod getPed() Class P\nReturn\nEndMethod\n', encoding="utf-8"
        )
        # ingere os dois lados no MESMO índice, depois cruza
        runner.invoke(app, ["--root", str(tmp_path), "ingest-poui", str(proj)])
        runner.invoke(app, ["--root", str(tmp_path), "ingest"])
        result = runner.invoke(app, ["--root", str(tmp_path), "poui-bridge"])
        assert result.exit_code == 0
        out = (result.stderr or "") + result.stdout
        assert "/pedidos" in out and "PEDREST" in out


class TestWriteEmptyAlert:
    """#65: alerta proativo quando 'tables --mode write' vazio mas há reads."""

    @pytest.fixture
    def proj_readonly(self, tmp_path: Path, runner: CliRunner) -> Path:
        """3 fontes que LEEM SXA, nenhum grava."""
        src = tmp_path / "src"
        src.mkdir()
        for i in range(3):
            (src / f"ABCRD{i}.prw").write_bytes(
                f'User Function ABCRD{i}()\n  DbSelectArea("SXA")\n'
                f'  DbSeek(xFilial("SXA"))\n  cN := SXA->XA_DESCRI\nReturn\n'.encode()
            )
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        return src

    def test_alerta_quando_write_vazio_com_reads(
        self, proj_readonly: Path, runner: CliRunner
    ) -> None:
        r = runner.invoke(app, ["--root", str(proj_readonly), "tables", "SXA", "--mode", "write"])
        assert r.exit_code == 0
        assert "mas 0x" in (r.stderr or "") and "SXA" in (r.stderr or "")

    def test_no_hints_silencia(self, proj_readonly: Path, runner: CliRunner) -> None:
        r = runner.invoke(
            app, ["--root", str(proj_readonly), "tables", "SXA", "--mode", "write", "--no-hints"]
        )
        assert "mas 0x" not in (r.stderr or "")

    def test_sem_alerta_quando_ha_write(self, indexed_project: Path, runner: CliRunner) -> None:
        # SC5 tem write clássico (RecLock) no synthetic_project -> sem alerta
        r = runner.invoke(app, ["--root", str(indexed_project), "tables", "SC5", "--mode", "write"])
        assert "mas 0x" not in (r.stderr or "")


class TestCatalogCommands:
    """#75: ingest-tsv + catalog via CLI."""

    @pytest.fixture
    def proj_catalog(self, tmp_path: Path, runner: CliRunner) -> tuple[Path, Path]:
        src = tmp_path / "src"
        src.mkdir()
        (src / "ABCFN1.prw").write_bytes(b"User Function ABCFN1()\nReturn .T.\n")
        runner.invoke(app, ["--root", str(src), "init"])
        runner.invoke(app, ["--root", str(src), "ingest"])
        tsv = tmp_path / "dump.tsv"
        tsv.write_bytes(
            b"ZT_COD\tZT_TIPO\tZT_FUNCAO\n001\t1\tU_ABCFN1\n002\t1\tU_ABCFN1\n003\t2\t.F.\n"
        )
        r = runner.invoke(app, ["--root", str(src), "ingest-tsv", str(tsv), "--as", "regras"])
        assert r.exit_code == 0, r.stderr or r.stdout
        return src, tsv

    def test_ingest_tsv_e_group_count(
        self, proj_catalog: tuple[Path, Path], runner: CliRunner
    ) -> None:
        src, _ = proj_catalog
        r = runner.invoke(
            app,
            [
                "--root",
                str(src),
                "--format",
                "json",
                "catalog",
                "regras",
                "--group-by",
                "ZT_TIPO",
                "--count",
            ],
        )
        assert r.exit_code == 0
        assert '"count": 2' in r.stdout and '"ZT_TIPO": "1"' in r.stdout

    def test_resolve_callers_cli(self, proj_catalog: tuple[Path, Path], runner: CliRunner) -> None:
        src, _ = proj_catalog
        r = runner.invoke(
            app,
            [
                "--root",
                str(src),
                "--format",
                "json",
                "catalog",
                "regras",
                "--funcao-field",
                "ZT_FUNCAO",
                "--resolve-callers",
            ],
        )
        assert "ABCFN1.prw" in r.stdout

    def test_filtro_invalido_exit2(
        self, proj_catalog: tuple[Path, Path], runner: CliRunner
    ) -> None:
        src, _ = proj_catalog
        r = runner.invoke(
            app, ["--root", str(src), "catalog", "regras", "--filter", "DROP TABLE x"]
        )
        assert r.exit_code == 2

    def test_alias_inexistente_exit1(
        self, proj_catalog: tuple[Path, Path], runner: CliRunner
    ) -> None:
        src, _ = proj_catalog
        r = runner.invoke(app, ["--root", str(src), "catalog", "naoexiste"])
        assert r.exit_code == 1

    def test_status_lista_catalogo(
        self, proj_catalog: tuple[Path, Path], runner: CliRunner
    ) -> None:
        src, _ = proj_catalog
        r = runner.invoke(app, ["--root", str(src), "status"])
        assert "regras" in (r.stderr or "") and "3 linhas" in (r.stderr or "")


def test_coletadb_command_writes_file(tmp_path: Path, runner: CliRunner) -> None:
    r = runner.invoke(app, ["--root", str(tmp_path), "coletadb"])
    assert r.exit_code == 0, r.stderr or r.stdout
    out = tmp_path / "coletadb.tlpp"
    assert out.exists()
    data = out.read_bytes()
    assert data.count(b"\r") == 0
    assert "1.2.0" in (r.stdout + r.stderr)


def test_coletadb_dest_option(tmp_path: Path, runner: CliRunner) -> None:
    dest = tmp_path / "fontes"
    dest.mkdir()
    r = runner.invoke(app, ["--root", str(tmp_path), "coletadb", "--dest", str(dest)])
    assert r.exit_code == 0, r.stderr or r.stdout
    assert (dest / "coletadb.tlpp").exists()


def test_coletadb_version_mismatch_needs_force(tmp_path: Path, runner: CliRunner) -> None:
    (tmp_path / "coletadb.tlpp").write_bytes(b'#DEFINE CDB_VERSION "0.9.9"\n')
    r = runner.invoke(app, ["--root", str(tmp_path), "coletadb"])
    assert r.exit_code == 1
    assert "--force" in (r.stderr + r.stdout)
    r2 = runner.invoke(app, ["--root", str(tmp_path), "coletadb", "--force"])
    assert r2.exit_code == 0, r2.stderr or r2.stdout
    assert b"1.2.0" in (tmp_path / "coletadb.tlpp").read_bytes()


def test_coletadb_unparseable_existing_shows_desconhecida(
    tmp_path: Path, runner: CliRunner
) -> None:
    # Arquivo existente sem #DEFINE CDB_VERSION → versao nao parseavel; a
    # mensagem deve dizer "desconhecida", nunca "vNone".
    (tmp_path / "coletadb.tlpp").write_bytes(b"// arquivo sem define de versao\n")
    r = runner.invoke(app, ["--root", str(tmp_path), "coletadb"])
    assert r.exit_code == 1
    out = r.stderr + r.stdout
    assert "desconhecida" in out
    assert "None" not in out


def test_init_coletadb_flag_extracts(tmp_path: Path, runner: CliRunner) -> None:
    r = runner.invoke(app, ["--root", str(tmp_path), "init", "--coletadb"])
    assert r.exit_code == 0, r.stderr or r.stdout
    assert (tmp_path / "coletadb.tlpp").exists()


def test_init_without_flag_does_not_extract(tmp_path: Path, runner: CliRunner) -> None:
    r = runner.invoke(app, ["--root", str(tmp_path), "init"])
    assert r.exit_code == 0, r.stderr or r.stdout
    assert not (tmp_path / "coletadb.tlpp").exists()


class TestIngestExcludeCli:
    """CLI: --exclude + .plugadvplignore na ingestão (issue #141)."""

    def test_exclude_flag_and_summary(self, tmp_path: Path, runner: CliRunner) -> None:
        (tmp_path / "ativo").mkdir()
        (tmp_path / "ativo" / "A.prw").write_text("User Function A()\nReturn\n", encoding="utf-8")
        (tmp_path / "descontinuado").mkdir()
        (tmp_path / "descontinuado" / "B.prw").write_text(
            "User Function B()\nReturn\n", encoding="utf-8"
        )

        r0 = runner.invoke(app, ["--root", str(tmp_path), "init"])
        assert r0.exit_code == 0, r0.stderr or r0.stdout
        r = runner.invoke(app, ["--root", str(tmp_path), "ingest", "--exclude", "descontinuado/**"])
        assert r.exit_code == 0, r.stderr or r.stdout
        assert "ignorados" in (r.stderr + r.stdout)

        db = tmp_path / ".plugadvpl" / "index.db"
        conn = sqlite3.connect(db)
        try:
            rows = {row[0] for row in conn.execute("SELECT arquivo FROM fontes")}
        finally:
            conn.close()
        assert rows == {"A.prw"}


class TestIngestRespectsDb:
    """Bug fix: `ingest` deve respeitar `--db` (antes escrevia em <root>/.plugadvpl)."""

    def test_ingest_writes_to_custom_db(
        self, synthetic_project: Path, runner: CliRunner, tmp_path: Path
    ) -> None:
        custom = tmp_path / "custom_idx.db"
        runner.invoke(app, ["--root", str(synthetic_project), "--db", str(custom), "init"])
        r = runner.invoke(app, ["--root", str(synthetic_project), "--db", str(custom), "ingest"])
        assert r.exit_code == 0
        # o índice custom deve estar populado...
        conn = sqlite3.connect(custom)
        try:
            n = conn.execute("SELECT count(*) FROM fontes").fetchone()[0]
        finally:
            conn.close()
        assert n > 0
        # ...e o local default NÃO deve ter sido criado.
        assert not (synthetic_project / ".plugadvpl" / "index.db").exists()


class TestGroundingFragment:
    """Fase 3 roadmap-ia: o fragment instrui o agente a emitir o bloco de claims."""

    def test_fragment_has_claims_block_instruction(
        self, synthetic_project: Path, runner: CliRunner
    ) -> None:
        runner.invoke(app, ["--root", str(synthetic_project), "init"])
        content = (synthetic_project / "CLAUDE.md").read_text(encoding="utf-8")
        assert "plugadvpl-claims" in content


class TestVerifyClaims:
    """Fase 1 roadmap-ia: comando `verify-claims` (verificador determinístico)."""

    def test_stdin_batch_returns_verdict_json(
        self, indexed_project: Path, runner: CliRunner
    ) -> None:
        payload = json.dumps({"claims": [{"id": "c1", "kind": "function", "symbol": "FWLerExcel"}]})
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "--format", "json", "verify-claims", "--stdin"],
            input=payload,
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "coverage" in data
        by = {r["claim_id"]: r for r in data["results"]}
        # FWLerExcel é alucinação clássica -> não existe no índice.
        assert by["c1"]["status"] == "not_found"

    def test_short_form_single_claim(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            [
                "--root",
                str(indexed_project),
                "--format",
                "json",
                "verify-claims",
                "--kind",
                "function",
                "--symbol",
                "FWLerExcel",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["results"][0]["status"] == "not_found"

    def test_empty_stdin_is_graceful(self, indexed_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(
            app,
            ["--root", str(indexed_project), "--format", "json", "verify-claims", "--stdin"],
            input="",
        )
        assert result.exit_code == 0
        assert json.loads(result.stdout)["results"] == []


class TestGenAplicadorSx:
    """`gen-aplicador-sx` — gera .prw aplicador de SXs a partir de spec JSON."""

    def test_gera_prw_de_spec_valido(self, tmp_path: Path, runner: CliRunner) -> None:
        spec = tmp_path / "spec.json"
        spec.write_text(
            json.dumps(
                {
                    "numero": "099999",
                    "sx3": [
                        {
                            "alias": "ZXX",
                            "campo": "ZXX_COD",
                            "tipo": "C",
                            "tamanho": 6,
                            "titulo": "Cod",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        out = tmp_path / "a099999.prw"
        result = runner.invoke(app, ["gen-aplicador-sx", "--spec", str(spec), "--out", str(out)])
        assert result.exit_code == 0, result.stderr or result.stdout
        assert out.exists()
        conteudo = out.read_text(encoding="cp1252")
        assert "User Function A099999" in conteudo

    def test_example_imprime_spec_valido_e_geravel(self, runner: CliRunner) -> None:
        # descoberta p/ IAs: --example imprime um spec pronto, sem precisar de --spec.
        result = runner.invoke(app, ["gen-aplicador-sx", "--example"])
        assert result.exit_code == 0, result.stderr or result.stdout
        spec = json.loads(result.stdout)
        assert spec["numero"] and spec["sx3"]
        gen = runner.invoke(app, ["gen-aplicador-sx", "--spec", "-"], input=result.stdout)
        assert gen.exit_code == 0
        assert "User Function A" in gen.stdout

    def test_schema_imprime_chaves_por_tipo(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["gen-aplicador-sx", "--schema"])
        assert result.exit_code == 0, result.stderr or result.stdout
        sch = json.loads(result.stdout)
        assert {"sx2", "sx3", "six", "sx6", "sx7", "sx1", "sxa", "sx5"} <= set(sch)

    def test_sem_spec_nem_flag_erro_orienta(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["gen-aplicador-sx"])
        assert result.exit_code == 2
        assert "--example" in (result.stderr or result.stdout)

    def test_spec_com_erro_de_validacao_sai_nao_zero(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        spec = tmp_path / "spec.json"
        # falta 'campo' (obrigatório) -> erro de validação.
        spec.write_text(
            json.dumps({"numero": "099999", "sx3": [{"alias": "ZXX", "tipo": "C", "tamanho": 6}]}),
            encoding="utf-8",
        )
        out = tmp_path / "a099999.prw"
        result = runner.invoke(app, ["gen-aplicador-sx", "--spec", str(spec), "--out", str(out)])
        assert result.exit_code != 0
        assert "erro:" in (result.stderr or result.stdout)
