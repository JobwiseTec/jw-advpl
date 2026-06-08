# Spec — coletadb no wheel + hook de adoção (2026-06-08)

> **Status:** design aprovado (brainstorming). Próximo passo: writing-plans.
> **Escopo:** duas features pequenas e independentes + um fix de 1 linha.
> **Princípios herdados do projeto:** determinístico; opt-in com default desligado
> = byte-idêntico; fonte única (sem cópia duplicada que dê drift); skill-por-comando.

---

## 1. Contexto e problema

Dois problemas distintos, ambos sobre **onboarding/adoção** do plugadvpl:

### Problema 1 — a IA não usa o plugin mesmo instalado
Há relatos de usuários que instalam o plugin e a IA (Claude Code) continua lendo
`.prw`/`.tlpp` cru, sem consultar o índice — "como se não mudasse nada". Hoje
existem dois mecanismos, mas com um buraco em cada:

- **`plugadvpl init`** escreve a "REGRA DURA — SEM EXCEÇÃO" no `CLAUDE.md` +
  `AGENTS.md` ([cli.py:488-596](../../../cli/plugadvpl/cli.py)). **Mas** só existe
  se o usuário **rodar `init`** — quem instala o plugin pela marketplace e não
  roda `init` nunca recebe a regra.
- **SessionStart hook** ([hooks/session-start.mjs](../../../hooks/session-start.mjs))
  injeta contexto quando falta `uv`, falta índice, ou índice está
  velho. **Mas** quando o índice **existe e está saudável** ele faz `emit(null)`
  (silêncio) — então naquela sessão **nada relembra** a IA a usar o plugin.

### Problema 2 — o `coletadb.tlpp` não chega ao usuário
O `coletadb.tlpp` (componente servidor que dumpa o dicionário SX no Protheus)
**não vai junto com o plugin**. Ele só existe no repo em
[docs/reference-impl/coletadb.tlpp](../../reference-impl/coletadb.tlpp); o wheel
(`uvx plugadvpl`) e o plugin da marketplace **não o incluem**.

Consequência real observada: como não há cópia canônica entregue pelo plugin,
usuários (e IAs) **caçam** o arquivo onde acham — e pegam uma **versão antiga**.
Foi o que aconteceu: uma cópia **v1.0.0** (anterior ao recurso "salvar na estação
do cliente"), que "não abria" e foi corrigida na mão mexendo numa variável. O
fonte atual do repo já é **v1.2.0** e já tem o recurso — o problema foi puramente
**drift de versão por falta de uma fonte oficial empacotada**.

Além disso, há um **bug menor de consistência**: o cabeçalho do arquivo está com
`| Versao: 1.0.0 |` ([coletadb.tlpp:17](../../reference-impl/coletadb.tlpp#L17)),
desatualizado em relação ao `#DEFINE CDB_VERSION "1.2.0"`
([coletadb.tlpp:90](../../reference-impl/coletadb.tlpp#L90)).

---

## 2. Objetivos

- **A.** Quando o índice existe e está saudável, o SessionStart hook passa a
  injetar um **lembrete curto e imperativo toda sessão** (hoje fica mudo) para a
  IA consultar o índice antes de ler fontes. É o lever mais forte porque
  independe de skill discovery e de o usuário ter rodado `init`.
- **B.** **Empacotar** o `coletadb.tlpp` no wheel e expor:
  - comando `plugadvpl coletadb` (extrai para a raiz do projeto / `--dest`);
  - flag `plugadvpl init --coletadb` (atalho no setup);
  - skill `/plugadvpl:coletadb`.
  Resultado: a versão extraída **sempre casa com a versão do plugadvpl instalado**
  (sem caça, sem cópia velha).
- **C.** Corrigir o version stamp do `coletadb.tlpp` (`Versao: 1.0.0` → `1.2.0`).

## 3. Não-objetivos (YAGNI / fora de escopo)

- **NÃO** adicionar "salvar na estação do cliente" no COLETADB — **já existe**
  (v1.1.0/v1.2.0: checkbox "Salvar na estacao (cliente)" + picker local
  `GETF_LOCALHARD` + `CpyS2T` + envio zipado).
- **NÃO** mexer no fluxo REST `ingest-protheus` nem no `coletadb_client.py`.
- **NÃO** cobrir adoção em Cursor/Copilot/Gemini/Codex — a dor é o Claude Code;
  os outros agentes já recebem instruções via `init`. O hook é exclusivo do
  Claude Code (é hook de plugin Claude Code).
- **NÃO** auto-rodar `init` nem escrever `CLAUDE.md` no install do plugin —
  plugins Claude Code não executam código arbitrário de instalação no repo do
  usuário. O hook é o canal legítimo para reforço por sessão.
- **NÃO** auto-extrair o `coletadb.tlpp` em todo `init` (despejaria o arquivo na
  maioria dos projetos, que nunca usam coletadb). Extração é **opt-in**.

---

## 4. Parte A — Hook reforça toda sessão

### 4.1 Mudança
Arquivo: `hooks/session-start.mjs`. No `main()`, o ramo final (DB existe, não
stale, sem version drift) hoje chama `emit(null)`. Passa a chamar
`emit(REMINDER)` com um texto curto e imperativo, extraído para uma **constante
nomeada** no topo do módulo (ex.: `HEALTHY_REMINDER`).

### 4.2 Conteúdo do lembrete (rascunho, ~400 chars)
> Projeto Protheus com índice plugadvpl ativo neste diretório. Antes de
> `Read`/`Grep` em `.prw`/`.tlpp`/`.prx`, consulte o índice PRIMEIRO:
> `plugadvpl arch <arq>` (visão geral), `find <nome>`, `callers`/`callees`,
> `tables <T>`, `param <MV_>`, `lint`. Leia o fonte cru só depois de localizar a
> faixa de linhas exata (10-50× menos contexto). Use o plugadvpl para todo
> trabalho ADVPL/TLPP.

### 4.3 Opt-out
Env var `PLUGADVPL_HOOK_QUIET` (valor truthy: `1`/`true`/`on`/`sim`): quando
setada, o ramo saudável volta a ficar **silencioso** (preserva o comportamento de
hoje para quem já internalizou / acha repetitivo). Os avisos de **problema**
(sem `uv`, falta índice, stale, drift) continuam emitindo independente do opt-out.

### 4.4 Invariantes
- Os demais ramos (`sem uv`, `sem índice`, `stale`, `drift`) ficam **idênticos**.
- O hook continua **fail-silent** em qualquer erro (nunca quebra a sessão).
- Respeita o `ADDITIONAL_CONTEXT_LIMIT` (truncamento já existente).
- Só dispara quando há fontes ADVPL detectados (gate já existente).

### 4.5 Teste
`hooks/` não tem teste automatizado hoje. Adicionar um **smoke-test Node
standalone** (sem framework — script `.mjs` rodável por `node`), ex.
`hooks/session-start.test.mjs`, que:
1. cria um diretório temporário com um `.prw` e um `.plugadvpl/index.db` falso;
2. roda o hook forçando o ramo saudável (stub do `checkStaleViaCli`, ou
   refatorando-o para ser injetável) e assere que `HEALTHY_REMINDER` aparece no
   `additionalContext`;
3. roda com `PLUGADVPL_HOOK_QUIET=1` e assere saída vazia (silêncio).
Se o stub do shell-out for inviável, no mínimo exportar `HEALTHY_REMINDER` e
testar a montagem do payload de forma isolada. Documentar limitação no README do
hook.

### 4.6 Critérios de aceite (Parte A)
- [ ] Sessão nova num projeto ADVPL com índice saudável injeta o lembrete.
- [ ] `PLUGADVPL_HOOK_QUIET=1` silencia o lembrete saudável; avisos de problema
      seguem.
- [ ] Demais ramos byte-idênticos ao comportamento atual.
- [ ] Smoke-test passa.

---

## 5. Parte B — `coletadb.tlpp` no wheel + comando

### 5.1 Empacotamento (fonte única, sem cópia)
Fonte de verdade continua [docs/reference-impl/coletadb.tlpp](../../reference-impl/coletadb.tlpp).
Adicionar `force-include` em `cli/pyproject.toml`
(`[tool.hatch.build.targets.wheel]`), espelhando o padrão de `skills/`:

```toml
force-include = { "../skills" = "plugadvpl/skills", "../docs/reference-impl/coletadb.tlpp" = "plugadvpl/server_components/coletadb.tlpp" }
```

- Mesma ressalva do `skills/`: build precisa do **checkout** (monorepo). O
  `release.yml` já faz `uv build --sdist` e `--wheel` **separadamente** a partir
  da fonte; mas o `release-rc.yml` usa `uv build` **encadeado**
  (sdist → wheel-from-sdist). Como o force-include vive em `../`, validar
  **os dois** caminhos (ver R1).
- **Verificar** que o `uv build` (sdist + wheel) não dá "Duplicate filename"
  (caminho destino é novo, fora do auto-include do package — risco baixo).

### 5.2 Resolver dev/wheel (`server_components.py`)
Novo módulo `cli/plugadvpl/server_components.py`, espelhando `_skills_root()`
([_skill_catalog.py:189-207](../../../cli/plugadvpl/_skill_catalog.py#L189-L207)):

- `_coletadb_source() -> Path`: tenta `ir.files("plugadvpl") / "server_components"
  / "coletadb.tlpp"` (via `ir.as_file`); se não existir (dev tree), cai pro
  repo-root `parents[2] / "docs" / "reference-impl" / "coletadb.tlpp"`.
- `coletadb_version(data: bytes) -> str | None`: extrai do
  `#DEFINE CDB_VERSION "X.Y.Z"` (regex), **não** do cabeçalho `Versao:`.
- `extract_coletadb(dest_dir: Path, *, force: bool) -> ExtractResult`:
  - lê os **bytes** da fonte (cópia byte-a-byte). **A fonte é LF + ASCII puro**
    (0 bytes CR, 0 não-ASCII), normalizada por `.gitattributes`
    (`*.tlpp text eol=lf`). O `.tlpp` compila no Protheus com LF sem problema;
    ASCII puro elimina qualquer questão de encoding. Objetivo: **byte-identidade**
    com a fonte empacotada — **não** um EOL específico;
  - alvo = `dest_dir / "coletadb.tlpp"`;
  - se não existe → escreve (`write_bytes`);
  - se existe e **mesma versão** → no-op idempotente (`status="unchanged"`);
  - se existe e versão difere e **não** `force` → não sobrescreve
    (`status="version_mismatch"`, reporta as duas versões);
  - se `force` → sobrescreve;
  - retorna `(status, path, version_bundled, version_existing)`.

### 5.3 Comando `plugadvpl coletadb`
Em `cli.py`, novo `@app.command()`:
- Args/opções: `--dest PATH` (default = `ctx.obj["root"]`), `--force`.
- Chama `extract_coletadb`. Saída (respeitando `--quiet`):
  - sucesso/idempotente: caminho + versão extraída + os 3 passos de compilação
    (copiar pro RPO custom → compilar via TDS-VSCode ou `plugadvpl compile` →
    `[HTTPV11]`/`[HTTPURI]` no `appserver.ini`) + nota apontando
    `plugadvpl ingest-protheus` como consumidor;
  - `version_mismatch`: mensagem clara ("já existe coletadb.tlpp vX; bundle é vY;
    use `--force` para trocar").
- Saída estruturada passa pelo funil `_render_from_ctx`/`output.render` quando
  fizer sentido (consistência com os outros comandos), ou `typer.echo` direto
  para a parte de "next steps".

### 5.4 Flag `init --coletadb`
Em `init`, nova opção `--coletadb` (default `False`). Quando setada, após criar o
DB e os fragments, chama o mesmo helper de extração (`extract_coletadb(root,
force=False)`) e ecoa o resultado. Default desligado ⇒ `init` byte-idêntico.

### 5.5 Skill `/plugadvpl:coletadb`
Nova `skills/coletadb/SKILL.md` (wrapper, `disable-model-invocation: true`,
`allowed-tools: [Bash]`, uvx pin `uvx plugadvpl@<versão> coletadb`). Descreve:
extrai o componente servidor COLETADB (versão casada com o plugin) pra raiz;
quando usar (antes de compilar pra usar `ingest-protheus` ao vivo); aponta
`ingest-protheus`.

### 5.6 Chores conhecidos (mecânicos)
- Skill count **66 → 67** em **24** asserts `== 66` (`test_cli.py` ×12,
  `test_gemini_skills.py` ×7, `test_copilot_instructions.py` ×2,
  `test_cursor_rules.py` ×2, `test_skill_catalog.py` ×1).
- **README — contagens:** linha ~911 "27 knowledge + 39 slash command
  wrappers" (coletadb é wrapper → **40**, total **67**) **e** linha ~950
  "Total: 66 skills" → 67. Atualizar ambas. **Atenção:** a linha ~624 tem uma
  **3ª contagem já defasada** ("33 command wrappers + 21 knowledge skills" — rot
  pré-existente, inconsistente independente desta mudança); como ela diz "1 por
  subcomando do CLI" e estamos adicionando um subcomando, revisar/corrigir
  oportunisticamente ou marcar fora de escopo no plano.
- Entrada **obrigatória** no catálogo `_SKILL_GLOBS`
  (`_SKILL_GLOBS["coletadb"] = []`, estilo meta-skill como `setup`/`init`) →
  `len(_SKILL_GLOBS)` 66→67. `test_skill_catalog.py::test_matches_actual_skill_dirs`
  exige match **exato** com os dirs em disco (sem isso a suíte quebra).
- Fix-in-passing: o docstring de [_skill_catalog.py](../../../cli/plugadvpl/_skill_catalog.py)
  diz "65 skills" (desatualizado vs 66 atual) — atualizar para 67 ao mexer.
- `validate_plugin.py` (skill-por-comando + uvx-pin) deve passar com o novo
  comando/skill.
- `scripts/bump_marketplace_version.py` já cobre o pin uvx da SKILL nova.

### 5.7 Teste (Parte B)
- **Unit** (`server_components.py`):
  - bytes extraídos idênticos à fonte (`docs/reference-impl/coletadb.tlpp`);
  - `coletadb_version` parseia `1.2.0`;
  - skip-se-igual (`unchanged`); `version_mismatch` sem `force`; overwrite com
    `force`; **byte-idêntico** à fonte empacotada (a fonte é LF/ASCII — assert
    byte-equality; **não** assert CRLF).
- **Integração** (`test_cli.py`): comando `coletadb` num dir temp escreve o
  arquivo; `init --coletadb` idem; `init` sem a flag **não** cria o arquivo.

### 5.8 Critérios de aceite (Parte B)
- [ ] `uvx plugadvpl coletadb` (e `/plugadvpl:coletadb`) escreve
      `coletadb.tlpp` na raiz, com a versão casada ao plugin, imprimindo a versão.
- [ ] `init --coletadb` faz o mesmo; `init` puro não cria o arquivo.
- [ ] Re-rodar é idempotente; versão divergente exige `--force`.
- [ ] Arquivo extraído é **byte-idêntico** à fonte empacotada (LF/ASCII).
- [ ] `validate_plugin.py` e a suíte passam (skill count atualizado).

---

## 6. Parte C — fix do version stamp

[coletadb.tlpp:17](../../reference-impl/coletadb.tlpp#L17):
`| Versao: 1.0.0 |` → `| Versao: 1.2.0 |` (alinha com `CDB_VERSION`).
Mudança de comentário; **não** altera comportamento do fonte. Manter o arquivo
**ASCII puro / LF** (como está hoje; `.gitattributes` força `eol=lf`).

**Fix-in-passing opcional:** o próprio cabeçalho diz "Encoding ANSI
(Windows-1252), CRLF" ([coletadb.tlpp:21](../../reference-impl/coletadb.tlpp#L21))
— também inexato vs os bytes reais (ASCII/LF). Se for mexer no header, corrigir
para "ASCII / LF" (strings já são "sem acentos pra portabilidade", então ANSI vs
ASCII é irrelevante na prática).

### 6.1 Critério de aceite (Parte C)
- [ ] Cabeçalho `Versao:` bate com `CDB_VERSION` (1.2.0); arquivo segue ASCII/LF
      (byte-idêntico ao que `.gitattributes` mantém).

---

## 7. Componentes e fluxo de dados

```
INSTALL (marketplace / uvx)
   └─ wheel inclui: CLI + skills + server_components/coletadb.tlpp   (Parte B)

SESSÃO (Claude Code)
   └─ SessionStart hook  ── índice saudável ─► injeta lembrete       (Parte A)
                          └─ (PLUGADVPL_HOOK_QUIET=1 ⇒ silêncio)

SETUP do projeto
   ├─ plugadvpl init [--coletadb] ── cria DB, fragments, (opcional) extrai
   └─ plugadvpl coletadb [--dest .] ── extrai coletadb.tlpp (versão do plugin)
                                          │
                                          ▼  dev: docs/reference-impl/  | wheel: plugadvpl/server_components/
                                       server_components._coletadb_source()
```

## 8. Tratamento de erro

- **Hook:** fail-silent total (`try/catch` já existente). Opt-out nunca quebra.
- **Extração:** `--dest` inexistente/sem permissão → erro claro, exit ≠ 0;
  recurso empacotado ausente (não deveria ocorrer) → erro explicando reinstalar;
  `version_mismatch` sem `--force` → mensagem orientando, exit ≠ 0 (ou 0 com
  aviso — decidir no plano; preferência: exit ≠ 0 para script detectar).
- **Encoding/EOL:** sempre `read_bytes`/`write_bytes` (cópia byte-a-byte). Nunca
  `read_text`/`write_text` no `.tlpp` (transcodificaria ou normalizaria EOL). A
  fonte é LF/ASCII; o alvo é **byte-identidade** com a fonte empacotada, não um
  EOL específico.

## 9. Determinismo e opt-in

- `coletadb` / `init --coletadb`: opt-in; `init` puro inalterado (byte-idêntico).
- Extração é determinística (bytes da fonte empacotada).
- Hook Parte A **muda o default** do ramo saudável (de silêncio para lembrete) —
  decisão explícita do usuário; `PLUGADVPL_HOOK_QUIET=1` restaura o silêncio.
  Não afeta a saída de nenhum comando do CLI (determinismo do CLI intacto).

## 10. Riscos e questões abertas

- **R1 — build force-include do `.tlpp`:** confirmar que sdist+wheel buildam sem
  "Duplicate filename" e que o arquivo aparece em `plugadvpl/server_components/`
  no wheel. Validar **os dois** caminhos de CI: `release.yml` (sdist/wheel
  separados) **e** `release-rc.yml` (`uv build` encadeado = wheel-from-sdist, que
  é justamente o que o comentário do `pyproject.toml` alerta para o `../skills`).
  (Mitig.: rodar ambos local antes do release; conferir o conteúdo do wheel.)
- **R2 — teste do hook:** sem infra JS; o shell-out a `plugadvpl status` dificulta
  o teste do ramo saudável. (Mitig.: refatorar `checkStaleViaCli` para injeção
  ou testar montagem do payload isoladamente.)
- **R3 — ruído do lembrete por sessão:** mitigado pelo gate de fontes ADVPL +
  `PLUGADVPL_HOOK_QUIET`. Texto curto (~400 chars).
- **Q1 — exit code do `version_mismatch`:** ≠ 0 (script-friendly) vs 0 com aviso.
  Preferência: ≠ 0. Decidir no plano.

## 11. Critérios de aceite globais

- [ ] Suíte completa verde (`pytest`), incluindo skill count 67 e
      `validate_plugin.py`.
- [ ] `ruff` + `mypy` limpos nos arquivos novos/alterados.
- [ ] README/CHANGELOG atualizados (entrada de release + skill count).
- [ ] Sem nomes de cliente em qualquer artefato (fixtures/docs/output genéricos).
