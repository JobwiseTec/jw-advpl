# Aplicador de SXs — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um gerador determinístico (`plugadvpl gen-aplicador-sx`) que emite um `.prw` ADVPL estruturalmente idêntico — boilerplate byte-estável + `FSAtu*` por dicionário — para aplicar customizações de SX2/SX3/SIX/SX6/SX7/SX1/SXA/SX5 em modo exclusivo, no lugar de um RecLock ingênuo.

**Architecture:** Emissor Python puro (`cli/plugadvpl/aplicador_sx/`): `schema.py` (colunas + defaults + validação por tipo) → `emit.py` (monta cada `FSAtu*` + assembla o `.prw`) usando um template fixo empacotado (`boilerplate.prw.tmpl`). O comando lê um spec JSON, valida e emite. Mesmo spec → bytes idênticos (travado por snapshot golden + teste de determinismo). Skill `aplicador-sx` ensina o agente a montar o spec.

**Tech Stack:** Python 3.12, Typer (CLI), dataclasses, `importlib.resources` (lê o template empacotado), pytest + syrupy (snapshot golden). Saída em cp1252.

**Spec:** [docs/superpowers/specs/2026-06-16-aplicador-sx-design.md](../specs/2026-06-16-aplicador-sx-design.md)

**Princípios:** DRY, YAGNI, TDD (RED→GREEN→commit), commits frequentes. Tudo sintético (`ZXX`/`MV_X*`); **zero dado de cliente** em qualquer arquivo do repo.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `cli/plugadvpl/aplicador_sx/__init__.py` | Exporta `gen_prw(spec)`, `validate_spec(spec)`. |
| `cli/plugadvpl/aplicador_sx/schema.py` | Coluna de cada SX (`Col`), as 8 listas de colunas com defaults, `validate_spec`. Fonte da verdade dos campos. |
| `cli/plugadvpl/aplicador_sx/emit.py` | `emit_fsatu(tipo, entradas)`, `emit_prw(spec)` — monta o `.prw` (template + FSAtu*). |
| `cli/plugadvpl/aplicador_sx/boilerplate.prw.tmpl` | Template fixo (header, `User Function A{numero}`, `FSTProc` skeleton com slots, funções boilerplate `EscEmpresa`..`LeLog`). Sanitizado. |
| `cli/plugadvpl/cli.py` (modify) | `@app.command("gen-aplicador-sx")` — handler fino. |
| `skills/aplicador-sx/SKILL.md` (create) | Knowledge skill (cada campo + montar o spec). |
| `cli/plugadvpl/_skill_catalog.py` (modify) | `"aplicador-sx": _PRW` (ripple 72→73). |
| `agents/advpl-code-generator.md` (modify) | Passo: usar `gen-aplicador-sx` p/ customização de dicionário. |
| `.github/workflows/ci.yml` (modify) | `aplicador_sx/*.py` em `LINT_FILES`. |
| `cli/tests/unit/test_aplicador_sx_schema.py` (create) | Testes do schema/validação. |
| `cli/tests/unit/test_aplicador_sx_emit.py` (create) | Testes do emit por tipo + determinismo. |
| `cli/tests/unit/test_aplicador_sx_golden.py` (create) | Snapshot golden (spec completo → `.prw`) + lint do emitido. |
| `cli/tests/integration/test_cli.py` (modify) | `TestGenAplicadorSx` (comando e2e) + bump contagem 72→73. |

---

## Chunk 1: Espinha — package + schema(SX3) + emit boilerplate + SX3 + comando + golden mínimo

Estabelece o esqueleto e o **padrão** que os demais tipos repetem. SX3 é o tipo mais complexo (46 col), então serve de molde.

### Task 1.1: Package + `Col` + esqueleto do schema

**Files:**
- Create: `cli/plugadvpl/aplicador_sx/__init__.py`
- Create: `cli/plugadvpl/aplicador_sx/schema.py`
- Test: `cli/tests/unit/test_aplicador_sx_schema.py`

- [ ] **Step 1: Failing test** — `Col` e `SX3_COLS` existem e têm a forma certa.

```python
# test_aplicador_sx_schema.py
from plugadvpl.aplicador_sx.schema import Col, SX3_COLS

def test_sx3_tem_46_colunas_e_primeira_e_arquivo():
    assert len(SX3_COLS) == 46
    assert SX3_COLS[0].nome == "X3_ARQUIVO"
    assert SX3_COLS[0].chave == "alias"      # vem do spec
    assert SX3_COLS[0].obrig is True

def test_sx3_defaults_seguros():
    by = {c.nome: c for c in SX3_COLS}
    assert by["X3_PROPRI"].default == "U"
    assert by["X3_RESERV"].default == "xxxxxx x"
    assert by["X3_BROWSE"].default == "N"
    assert by["X3_CONTEXT"].default == "R"
```

- [ ] **Step 2: Run, verify FAIL** — `Run: cd cli && uv run pytest tests/unit/test_aplicador_sx_schema.py -q` → ImportError (módulo ausente).

- [ ] **Step 3: Minimal impl** — criar `__init__.py` (vazio por ora) e `schema.py`:

```python
# schema.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Col:
    nome: str            # nome da coluna SX (ex.: "X3_CAMPO")
    chave: str | None    # chave no spec JSON (ex.: "campo"); None = sempre default
    tipo: str            # 'C' | 'N' | 'L' | 'D'
    default: object = ""
    obrig: bool = False
    maxlen: int | None = None

# SX3 — 46 colunas. Defaults seguros p/ campo customizado (ver spec §6 e o guia de referência).
# chave=None significa "não vem do spec, usa default sempre".
SX3_COLS: list[Col] = [
    Col("X3_ARQUIVO", "alias",   "C", "",   obrig=True, maxlen=3),
    Col("X3_ORDEM",   "ordem",   "C", "01", maxlen=2),   # recalculado em runtime no ADVPL
    Col("X3_CAMPO",   "campo",   "C", "",   obrig=True, maxlen=10),
    Col("X3_TIPO",    "tipo",    "C", "C",  obrig=True, maxlen=1),
    Col("X3_TAMANHO", "tamanho", "N", 0),
    Col("X3_DECIMAL", "decimal", "N", 0),
    Col("X3_TITULO",  "titulo",  "C", "",   maxlen=30),
    Col("X3_TITSPA",  "titulo",  "C", "",   maxlen=30),   # espelha titulo se não vier titspa
    Col("X3_TITENG",  "titulo",  "C", "",   maxlen=30),
    Col("X3_DESCRIC", "descric", "C", "",   maxlen=50),
    Col("X3_DESCSPA", "descric", "C", "",   maxlen=50),
    Col("X3_DESCENG", "descric", "C", "",   maxlen=50),
    Col("X3_PICTURE", "picture", "C", "",   maxlen=20),
    Col("X3_VALID",   "valid",   "C", "",   maxlen=120),
    Col("X3_USADO",   "usado",   "C", "",   maxlen=256),  # 'todos' expande na máscara padrão (emit)
    Col("X3_RELACAO", "relacao", "C", "",   maxlen=80),
    Col("X3_F3",      "f3",      "C", "",    maxlen=10),
    Col("X3_NIVEL",   "nivel",   "N", 0),
    Col("X3_RESERV",  None,      "C", "xxxxxx x", maxlen=20),
    Col("X3_CHECK",   "check",   "C", "",    maxlen=120),
    Col("X3_TRIGGER", "trigger", "C", "",    maxlen=1),   # 'S' se trigger=True (emit converte)
    Col("X3_PROPRI",  None,      "C", "U",   maxlen=1),
    Col("X3_BROWSE",  "browse",  "C", "N",   maxlen=1),
    Col("X3_VISUAL",  None,      "C", "A",   maxlen=1),
    Col("X3_CONTEXT", None,      "C", "R",   maxlen=1),
    Col("X3_OBRIGAT", "obrigat", "C", "",    maxlen=16),
    Col("X3_VLDUSER", "vlduser", "C", "",    maxlen=120),
    Col("X3_CBOX",    "cbox",    "C", "",    maxlen=120),
    Col("X3_CBOXSPA", "cbox",    "C", "",    maxlen=120),
    Col("X3_CBOXENG", "cbox",    "C", "",    maxlen=120),
    Col("X3_PICTVAR", "pictvar", "C", "",    maxlen=20),
    Col("X3_WHEN",    "when",    "C", "",    maxlen=120),
    Col("X3_INIBRW",  "inibrw",  "C", "",    maxlen=60),
    Col("X3_GRPSXG",  "grpsxg",  "C", "",    maxlen=3),
    Col("X3_FOLDER",  "folder",  "C", "",    maxlen=2),
    Col("X3_CONDSQL", "condsql", "C", "",    maxlen=120),
    Col("X3_CHKSQL",  "chksql",  "C", "",    maxlen=120),
    Col("X3_IDXSRV",  "idxsrv",  "C", "",    maxlen=120),
    Col("X3_ORTOGRA", None,      "C", "N",   maxlen=1),
    Col("X3_TELA",    "tela",    "C", "",    maxlen=10),
    Col("X3_POSLGT",  None,      "C", "",    maxlen=16),
    Col("X3_IDXFLD",  None,      "C", "N",   maxlen=1),
    Col("X3_AGRUP",   "agrup",   "C", "",    maxlen=20),
    Col("X3_MODAL",   None,      "C", "",    maxlen=1),
    Col("X3_PYME",    None,      "C", "",    maxlen=1),
]
```

> Nota: alguns `chave` se repetem (X3_TITSPA/TITENG = `titulo`) porque o spec dá 1 valor e o emit
> espelha nos 3 idiomas se o usuário não fornecer variantes. O emit trata isso (Task 1.4).

- [ ] **Step 4: Run, verify PASS** — `cd cli && uv run pytest tests/unit/test_aplicador_sx_schema.py -q` → 2 passed.

- [ ] **Step 5: Commit** — `git add cli/plugadvpl/aplicador_sx/ cli/tests/unit/test_aplicador_sx_schema.py && git commit -m "feat(aplicador-sx): Col + SX3_COLS (schema dos 46 campos)"`

### Task 1.2: `validate_spec` (obrigatórios + tamanho + padrão de nome)

**Files:** Modify `schema.py`; Test `test_aplicador_sx_schema.py`.

- [ ] **Step 1: Failing test**

```python
from plugadvpl.aplicador_sx.schema import validate_spec

# validate_spec retorna (erros, warnings): erros bloqueiam; warnings só avisam.
def test_valida_campo_obrigatorio_ausente():
    erros, _w = validate_spec({"numero": "099999", "sx3": [{"tipo": "C", "tamanho": 6}]})
    assert any("alias" in e and "obrig" in e.lower() for e in erros)
    assert any("campo" in e for e in erros)

def test_valida_tamanho_estourado():
    erros, _w = validate_spec({"numero": "099999",
        "sx3": [{"alias": "ZXX", "campo": "ZXX_NOMEMUITOGRANDEX", "tipo": "C", "tamanho": 6}]})
    assert any("X3_CAMPO" in e and "10" in e for e in erros)

def test_spec_valido_sem_erros():
    erros, warns = validate_spec({"numero": "099999",
        "sx3": [{"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Cod"}]})
    assert erros == [] and warns == []

def test_numero_obrigatorio():
    erros, _w = validate_spec({"sx3": []})
    assert any("numero" in e for e in erros)
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Minimal impl** em `schema.py`:

```python
SX_COLS = {"sx3": SX3_COLS}  # cresce nas próximas tasks

def validate_spec(spec: dict) -> tuple[list[str], list[str]]:
    """Retorna (erros, warnings). Erros bloqueiam a emissão; warnings só avisam.

    O par (erros, warnings) já nasce aqui (não refatorar depois) porque o SX7
    sobre campo fora do spec é WARNING, não erro (spec §9).
    """
    erros: list[str] = []
    warnings: list[str] = []
    if not str(spec.get("numero", "")).strip():
        erros.append("'numero' é obrigatório (id do update).")
    for tipo, cols in SX_COLS.items():
        for i, entry in enumerate(spec.get(tipo, []) or []):
            for c in cols:
                if c.chave is None:
                    continue
                val = entry.get(c.chave)
                if c.obrig and (val is None or val == ""):
                    erros.append(f"{tipo}[{i}]: '{c.chave}' obrigatório ({c.nome}).")
                if c.maxlen and isinstance(val, str) and len(val) > c.maxlen:
                    erros.append(f"{tipo}[{i}]: '{c.chave}' excede {c.maxlen} chars ({c.nome}).")
    # SX7 (Task 3.2): gatilho sobre campo que não está no spec → WARNING (pode pré-existir).
    campos_spec = {e.get("campo") for e in (spec.get("sx3") or [])}
    for i, e in enumerate(spec.get("sx7", []) or []):
        if e.get("campo") and e["campo"] not in campos_spec:
            warnings.append(f"sx7[{i}]: campo '{e['campo']}' não está no spec (pode ser pré-existente).")
    return erros, warnings
```

> O bloco SX7 só dispara quando houver `sx7` no spec (Chunk 3); até lá fica inerte. Já deixá-lo
> aqui evita mudar a assinatura de `validate_spec` (e os testes do Chunk 1) lá no Chunk 3.

- [ ] **Step 4: Run, verify PASS** (4 passed).
- [ ] **Step 5: Commit** — `feat(aplicador-sx): validate_spec (obrigatórios + tamanho)`

### Task 1.3: Boilerplate template (extrair + sanitizar)

**Files:** Create `cli/plugadvpl/aplicador_sx/boilerplate.prw.tmpl`.

⚠️ **Confidencialidade:** extrair o boilerplate de UM exemplo canônico local (referência apenas) e **sanitizar** — remover qualquer nome/e-mail/path/prefixo de cliente, versão de ferramenta no `@obs`, títulos específicos. Resultado é genérico (framework puro). Não copiar nada que identifique cliente.

- [ ] **Step 1:** Criar o template com os slots `{numero}`, `{fsatu_calls}`, `{regua}`, `{fsatu_bodies}`. Conteúdo fixo:
  - `#INCLUDE "protheus.ch"` + `#DEFINE SIMPLES/DUPLAS` + `#DEFINE CSSBOTAO ...`
  - `User Function A{numero}(cEmpAmb, cFilAmb)` — `FormBatch` (avisos modo EXCLUSIVO + backup), checagem `MPDicInDB()`, modo interativo vs RPC, `MsNewProcess` chamando `FSTProc`.
  - `Static Function FSTProc(...)` — `RpcSetEnv` por empresa; `oProcess:SetRegua1({regua})`; `{fsatu_calls}` (slot); `__SetX31Mode(.F.)` + loop `X31UpdTable(aArqUpd)`.
  - `{fsatu_bodies}` (slot — as funções FSAtu* geradas entram aqui).
  - Funções boilerplate idênticas: `FSAtuHlp` (fixa/vazia), `EscEmpresa, MarcaTodos, InvSelecao, RetSelecao, MarcaMas, VerTodos, MyOpenSM0, LeLog`.

- [ ] **Step 2:** Validar manualmente que NÃO há token de cliente: `rg -i "marfrig|taura|wellington|d:\\\\clientes|MGF_" cli/plugadvpl/aplicador_sx/boilerplate.prw.tmpl` → **zero**.

- [ ] **Step 3: Commit** — `feat(aplicador-sx): template boilerplate fixo (sanitizado)`

> O template é texto ASCII+acentos PT. Política de encoding: armazenar o `.tmpl` em UTF-8; o emit
> converte a saída final p/ cp1252 (Task 1.7). Adicionar `*.tmpl text eol=lf` no `.gitattributes`.

### Task 1.4: `emit_fsatu` para SX3 (uma entrada → bloco `aAdd`)

**Files:** Create `emit.py`; Test `test_aplicador_sx_emit.py`.

- [ ] **Step 1: Failing test**

```python
from plugadvpl.aplicador_sx.emit import emit_aadd

def test_emit_aadd_sx3_campo_simples():
    linha = emit_aadd("sx3", {"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C",
                              "tamanho": 6, "titulo": "Codigo"})
    assert "aAdd( aSX3, {" in linha
    assert "'ZXX'" in linha              # X3_ARQUIVO
    assert "'ZXX_COD'" in linha          # X3_CAMPO
    assert "'U'" in linha                # X3_PROPRI default
    assert "'xxxxxx x'" in linha         # X3_RESERV default
    assert "//X3_CAMPO" in linha         # comentário de posição

def test_emit_aadd_sx3_titulo_espelha_3_idiomas():
    linha = emit_aadd("sx3", {"alias": "ZXX", "campo": "ZXX_X", "tipo": "C",
                              "tamanho": 1, "titulo": "Tit"})
    assert linha.count("'Tit'") == 3     # TITULO/TITSPA/TITENG

def test_emit_aadd_sx3_trigger_bool_vira_S():
    linha = emit_aadd("sx3", {"alias": "ZXX", "campo": "ZXX_X", "tipo": "C",
                              "tamanho": 1, "trigger": True})
    # X3_TRIGGER recebe 'S'
    assert "'S'" in linha.split("//X3_TRIGGER")[0].rsplit("aAdd", 1)[-1]

def test_mascara_usado_todos_tem_256_chars():
    # X3_USADO é máscara de 256 posições; tamanho errado = campo semanticamente quebrado.
    from plugadvpl.aplicador_sx.emit import _MASCARA_USADO_TODOS
    assert len(_MASCARA_USADO_TODOS) == 256
```

> O `_MASCARA_USADO_TODOS` deve ter **exatamente 256 chars** (ajustar a construção até o teste passar).

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Minimal impl** em `emit.py`:

```python
from __future__ import annotations
from .schema import SX_COLS, Col

def _valor_advpl(c: Col, entry: dict) -> str:
    raw = entry.get(c.chave) if c.chave else None
    val = raw if raw not in (None, "") else c.default
    # conversões especiais
    if c.nome == "X3_TRIGGER" and entry.get("trigger") is True:
        val = "S"
    if c.nome == "X3_USADO" and (raw == "todos" or (raw in (None, "") and entry.get("usado") == "todos")):
        val = _MASCARA_USADO_TODOS
    if c.tipo == "N":
        return str(int(val) if val != "" else 0)
    if c.tipo == "L":
        return ".T." if val in (True, ".T.", "S") else ".F."
    return "'" + str(val).replace("'", "") + "'"   # char: aspas simples, sem aspas internas

def emit_aadd(tipo: str, entry: dict) -> str:
    cols = SX_COLS[tipo]
    arr = "a" + tipo.upper()
    linhas = [f"aAdd( {arr}, {{ ;"]
    for i, c in enumerate(cols):
        sep = ";" if i < len(cols) - 1 else ""
        linhas.append(f"    {_valor_advpl(c, entry):<28}, {sep} //{c.nome}".rstrip())
    linhas.append(f"}} ) //fim {c.nome}")
    return "\n".join(linhas)

_MASCARA_USADO_TODOS = "x       " * 15 + "x x"  # 256-ish; ajustar p/ exatamente 256 chars
```

> Ajuste fino do `_MASCARA_USADO_TODOS` e do alinhamento são detalhe; o snapshot golden (Task 1.8)
> trava o formato final.

- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `feat(aplicador-sx): emit_aadd SX3 (entrada → bloco ADVPL)`

### Task 1.5: `emit_fsatu` (função FSAtuSX3 completa: aEstrut fixo + loop + aAdds)

**Files:** Modify `emit.py`; Test `test_aplicador_sx_emit.py`.

- [ ] **Step 1: Failing test** — `emit_fsatu("sx3", [entry, entry2])` retorna uma `Static Function FSAtuSX3()` contendo `aEstrut := {`, o laço de insert (`RecLock`, `FieldPut`, `dbCommit`, `MsUnLock`), o `aAdd( aArqUpd, ... )` e os 2 blocos `aAdd( aSX3,`. Assert nas substrings-chave.

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Impl** `emit_fsatu(tipo, entradas)` — concatena: header fixo da função + `aEstrut` (lista das colunas) + `aEval(aEstrut,...)` (FieldPos) + os `emit_aadd` + o laço de insert **fixo por tipo** (SX3 = só-insert com cálculo de ordem, ver spec §6). O laço fixo vem de um dict `LOOP_SXn` (string-molde) em `emit.py`.

- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `feat(aplicador-sx): emit_fsatu SX3 (função completa)`

### Task 1.6: `emit_prw` (assembla template + FSAtu* + FSTProc dinâmico)

**Files:** Modify `emit.py`, `__init__.py`; Test `test_aplicador_sx_emit.py`.

- [ ] **Step 1: Failing test**

```python
from plugadvpl.aplicador_sx import gen_prw

def test_gen_prw_estrutura_minima_sx3():
    prw = gen_prw({"numero": "099999",
        "sx3": [{"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Cod"}]})
    assert "User Function A099999(" in prw
    assert "Static Function FSTProc(" in prw
    assert "Static Function FSAtuSX3(" in prw
    assert "FSAtuSX3()" in prw                       # chamada no FSTProc
    assert "X31UpdTable(" in prw
    assert "Static Function MyOpenSM0(" in prw        # boilerplate presente

def test_gen_prw_so_chama_fsatu_dos_tipos_presentes():
    prw = gen_prw({"numero": "099999",
        "sx3": [{"alias": "ZXX", "campo": "ZXX_C", "tipo": "C", "tamanho": 1}]})
    assert "FSAtuSX2()" not in prw                    # sem sx2 no spec
```

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Impl** `emit_prw(spec)`:
  - lê o template via `importlib.resources.files("plugadvpl.aplicador_sx").joinpath("boilerplate.prw.tmpl").read_text("utf-8")`.
  - monta `fsatu_calls` (só dos tipos presentes, na ordem SX2,SX3,SIX,SX6,SX7,SX1,SXA,SX5) + `regua` = nº de seções.
  - monta `fsatu_bodies` = `\n\n`.join(emit_fsatu(t, spec[t]) for t presentes).
  - substitui os slots. Em `__init__.py`: `gen_prw = emit_prw`, e `validate_spec` reexportado.

- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `feat(aplicador-sx): emit_prw (assembla o .prw)`

### Task 1.7: Comando `gen-aplicador-sx`

**Files:** Modify `cli/plugadvpl/cli.py`; Test `cli/tests/integration/test_cli.py` (nova classe).

- [ ] **Step 1: Failing test** (CliRunner): `gen-aplicador-sx --spec <tmpfile.json> --out <out.prw>` → exit 0, arquivo criado em cp1252, contém `User Function A099999`. E `--spec` com obrigatório ausente → exit≠0 + erro de validação no stderr.

- [ ] **Step 2: Run, verify FAIL.**

- [ ] **Step 3: Impl** comando em `cli.py`:

```python
@app.command(name="gen-aplicador-sx")
def gen_aplicador_sx(
    ctx: typer.Context,
    spec: Annotated[str, typer.Option("--spec", help="Caminho do spec JSON (ou '-' p/ stdin).")],
    out: Annotated[str, typer.Option("--out", help="Arquivo .prw de saída (cp1252).")] = "",
) -> None:
    """Gera um 'aplicador de SXs' (.prw) a partir de um spec JSON. Determinístico, sem LLM."""
    from .aplicador_sx import gen_prw, validate_spec
    raw = sys.stdin.read() if spec == "-" else pathlib.Path(spec).read_text("utf-8")
    data = json.loads(raw)
    erros, warns = validate_spec(data)
    for w in warns:
        typer.echo(f"aviso: {w}", err=True)   # warnings não bloqueiam (ex.: SX7 sobre campo pré-existente)
    if erros:
        for e in erros:
            typer.echo(f"erro: {e}", err=True)
        raise typer.Exit(2)
    prw = gen_prw(data)
    if out:
        pathlib.Path(out).write_text(prw, encoding="cp1252", errors="replace")
        typer.echo(f"gerado: {out}")
    else:
        typer.echo(prw)
```

- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `feat(aplicador-sx): comando gen-aplicador-sx`

### Task 1.8: Snapshot golden + determinismo + lint do emitido

**Files:** Create `cli/tests/unit/test_aplicador_sx_golden.py`.

- [ ] **Step 1: Failing test**

```python
import json
from plugadvpl.aplicador_sx import gen_prw

_SPEC_SX3 = {"numero": "099999", "sx3": [
    {"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Codigo"},
    {"alias": "ZXX", "campo": "ZXX_DESC", "tipo": "C", "tamanho": 40, "titulo": "Descricao"},
]}

def test_golden_sx3(snapshot):
    assert gen_prw(_SPEC_SX3) == snapshot           # syrupy trava a estrutura

def test_determinismo_2x_identico():
    assert gen_prw(_SPEC_SX3) == gen_prw(_SPEC_SX3)

def test_emitido_passa_no_lint_sem_bp_sec():
    from plugadvpl.parsing.parser import add_function_ranges, extract_functions, extract_sql_embedado
    from plugadvpl.parsing.lint import lint_source
    prw = gen_prw(_SPEC_SX3)
    parsed = {"arquivo": "a099999.prw",
              "funcoes": add_function_ranges(extract_functions(prw), prw),
              "sql_embedado": extract_sql_embedado(prw)}
    findings = lint_source(parsed, prw)
    graves = [f for f in findings if f["regra_id"].split("-")[0] in ("PERF", "SQL", "MOD")]
    assert graves == [], graves     # BP/SEC suprimidos de propósito (spec §11)

def test_regua_bate_com_chamadas_fsatu():
    # SetRegua1(N) tem que casar com o nº de chamadas FSAtu* no FSTProc (não pode driftar).
    import re
    prw = gen_prw(_SPEC_SX3)
    chamadas = len(re.findall(r"^\s*FSAtu\w+\(\)\s*$", prw, re.M))   # só chamadas (defs têm "Static Function" antes)
    m = re.search(r"SetRegua1\(\s*(\d+)\s*\)", prw)
    assert m and int(m.group(1)) == chamadas

def test_zero_token_de_cliente():
    # o emitido só pode conter aliases sintéticos; nada de cliente.
    prw = gen_prw(_SPEC_SX3).lower()
    for tok in ("marfrig", "taura", "wellington", "mgf_", "d:\\clientes"):
        assert tok not in prw
```

- [ ] **Step 2: Run** → `cd cli && uv run pytest tests/unit/test_aplicador_sx_golden.py -q` — primeira vez gera o snapshot (`--snapshot-update`). Verificar o `.prw` gerado **à mão** (compila mentalmente; sem token de cliente).

- [ ] **Step 3:** Se `test_emitido_passa_no_lint` falhar, ajustar o boilerplate/emit até passar (ex.: `Then` acidental, escopo). Iterar.

- [ ] **Step 4: Run, verify PASS** (3 passed) + `git add` do `.ambr` do snapshot.
- [ ] **Step 5: Commit** — `test(aplicador-sx): golden snapshot + determinismo + lint do emitido`

---

## Chunk 2: Criação de tabela — SX2 + SIX

Repete o **padrão da Task 1.1/1.4/1.5** para cada tipo. Para cada um: (a) `SXn_COLS` no `schema.py` (colunas + defaults da spec §6) e registrar em `SX_COLS`; (b) `LOOP_SXn` (laço fixo) em `emit.py`; (c) testes de schema + emit; (d) estender o golden.

### Task 2.1: `SX2_COLS` (20 col) + loop insert/update-parcial
- Colunas e defaults: spec §6 (SX2). `X2_MODO/MODOEMP/MODOUN` default `'E'`. Update parcial só de `cCpoUpd` (`X2_ROTINA/UNICO/DISPLAY/SYSOBJ/USROBJ/POSLGT`). `X2_ARQUIVO` recebe sufixo de empresa **em runtime no ADVPL** (o array leva o alias; o laço monta `alias+cEmpAnt+"0"`).
- TDD: test_schema (20 col, defaults `E`) → test_emit (`emit_aadd("sx2",...)`) → loop `LOOP_SX2`.
- Commit por sub-passo.

### Task 2.2: `SIX_COLS` (10 col) + loop insert/update + drop se chave muda
- Colunas: spec §6 (SIX). 1ª ordem `'1'`; chave começa por `ALIAS_FILIAL` (validar no `validate_spec`). Loop: insert/update; se chave mudou → `TcInternal(60, RetSqlName(...)+"|"+...)`.
- Validação extra: SIX cuja chave não começa por `<alias>_FILIAL` → erro.
- TDD: schema → emit → loop → validação da chave.

### Task 2.3: Estender o golden p/ tabela do zero
- Spec golden ganha `sx2` (1 tabela ZXX) + `six` (índice ordem 1). Atualizar snapshot. Confirmar `FSAtuSX2`/`FSAtuSIX` no `.prw` + chamada no FSTProc + `regua` incrementado.
- Commit.

---

## Chunk 3: Demais dicionários — SX6 / SX7 / SX1 / SXA / SX5

Mesmo padrão (schema + loop + testes + golden) para cada. Detalhes por tipo (spec §6):

### Task 3.1: `SX6_COLS` (22 col) — só insert
- `X6_FIL` default `'  '` (global). Só insere (respeita valor existente). Descrição longa: o spec dá `descric`; emit quebra em `X6_DESCRIC/DESC1/DESC2` se > 50 (ou aceita `descric`/`desc1`/`desc2` explícitos). Loop: `dbSeek(fil+var)`; se não existe, insere.
- TDD: schema → emit → quebra de descrição → loop.

### Task 3.2: `SX7_COLS` (11 col) — insert; warning se campo fora do spec
- Colunas: `X7_CAMPO/SEQUENC/REGRA/CDOMIN/TIPO/SEEK/ALIAS/ORDEM/CHAVE/PROPRI/CONDIC`. Loop: insere checando o campo no SX3 (runtime). **Validação = WARNING** (não erro) se `campo` não está em nenhum `sx3` do spec (spec §9) — `validate_spec` separa erros de warnings; o comando imprime warnings em stderr mas não falha.
- TDD: schema → emit → `validate_spec` retorna warning (não erro) p/ campo externo.

> **Sem refactor:** a assinatura `validate_spec -> (erros, warnings)` e a lógica de warning do SX7
> já estão prontas desde a Task 1.2. Esta task só (a) adiciona `SX7_COLS` + `LOOP_SX7` e (b) o teste
> que confirma: campo fora do spec vira **warning** (não erro) e o emit gera a `FSAtuSX7`.

### Task 3.3: `SX1_COLS` (43 col) — insert por grupo+ordem
- Colunas: spec §6 (SX1), incluindo o bloco `X1_VAR01..05 + DEF/DEFSPA/DEFENG/CNT`. O spec aceita `opcoes: [{var, def, cnt}, ...]` (até 5) e o emit preenche os blocos 01..05. Loop: `dbSeek(grupo+ordem)`.
- TDD: schema → emit (incl. opções → blocos) → loop.

### Task 3.4: `SXA_COLS` (8 col) + `SX5_COLS` (6 col) — insert simples
- SXA: `XA_ALIAS/ORDEM/DESCRIC/DESCSPA/DESCENG/AGRUP/TIPO/PROPRI`. SX5: `X5_FILIAL/TABELA/CHAVE/DESCRI/DESCSPA/DESCENG`. Ambos insert simples.
- TDD: schema → emit → loop (compartilham um loop genérico de insert).

### Task 3.5: Golden completo (todos os 8 tipos)
- Spec golden final com 1+ entrada de cada tipo (tudo `ZXX`/`MV_X*`). Atualizar snapshot. Confirmar os 8 `FSAtu*` + `regua` = 8 + lint limpo. Teste de determinismo no spec completo.
- Commit.

---

## Chunk 4: Skill + integração no agente + ripple

### Task 4.1: Skill `aplicador-sx`
**Files:** Create `skills/aplicador-sx/SKILL.md`; Modify `cli/plugadvpl/_skill_catalog.py` (`"aplicador-sx": _PRW`).
- Conteúdo: o conceito (modo exclusivo, X31UpdTable), **cada campo de cada SX** (tabela por tipo, valores válidos, limites), como montar o spec JSON, e o comando `uvx plugadvpl@<ver> gen-aplicador-sx --spec ...`. Exemplos **sintéticos** (`ZXX`). uvx pin na versão atual.
- TDD/validação: `python scripts/validate_plugin.py` passa (skill wrapper presente).

### Task 4.2: Ripple de contagem 72→73
**Files:** Modify `cli/tests/unit/test_skill_catalog.py`, `test_cli.py`, `test_copilot_instructions.py`, `test_cursor_rules.py`, `test_gemini_skills.py`, `README.md`.
- `== 72` → `== 73` (replace_all por arquivo, via Python — ver memória do bump anterior). README `× 72`→`× 73`, "72 skills"→"73 skills".
- Run: `cd cli && uv run pytest tests/unit/test_skill_catalog.py tests/unit/test_gemini_skills.py tests/unit/test_cursor_rules.py tests/unit/test_copilot_instructions.py tests/integration/test_cli.py -q`.
- Commit.

### Task 4.3: Integração no `advpl-code-generator`
**Files:** Modify `agents/advpl-code-generator.md`.
- Passo novo: ao gerar customização de **dicionário** (campo/tabela/param/gatilho/pergunta), **montar o spec e chamar `gen-aplicador-sx`** em vez de `RecLock` ingênuo. Linkar a skill `aplicador-sx`.
- Commit.

### Task 4.4: LINT_FILES + suíte + PR
**Files:** Modify `.github/workflows/ci.yml` (add `plugadvpl/aplicador_sx/__init__.py`, `schema.py`, `emit.py`).
- Run ruff/mypy nos novos fontes (ver memórias: `ruff format --check` + drift). Run **suíte completa** (`> LOG; echo EXIT=$?`).
- Abrir PR `feat/aplicador-sx` → CI verde → merge. (Toca `.github/workflows` → merge via `--auto`.)

---

## Verificação final (antes do PR)

- [ ] `gen_prw(spec)` determinístico (golden + 2× idêntico).
- [ ] `.prw` emitido passa em `parse_source` + `lint` (sem PERF/SQL/MOD; BP/SEC suprimidos por design).
- [ ] **Zero token de cliente** em qualquer arquivo: `rg -i "marfrig|taura|wellington|MGF_|d:\\\\clientes" cli/plugadvpl/aplicador_sx skills/aplicador-sx docs/superpowers` → vazio.
- [ ] `validate_plugin.py` OK; contagem de skills 73 consistente.
- [ ] Suíte completa verde; ruff/mypy limpos nos novos fontes.
