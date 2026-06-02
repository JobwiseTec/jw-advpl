# `ini-audit` — Enriquecimento e Curadoria da Base de Conhecimento

**Status:** design **proposto** · pendente aprovação do autor (brainstorming)
**Release alvo:** a definir (provável v0.21.0)
**Audiência:** times que rodam `plugadvpl ini-audit` contra appserver/dbaccess/tss/broker/smartclient
**Origem:** investigação de 2026-06-02 — a PR #37 expôs o ruído de `info`-missing; ao puxar o fio, a base se revelou parcialmente **alucinada** (valores fabricados, inclusive 1 bug de segurança).

> Esse documento é a **spec** do enriquecimento. O plano de implementação (tarefas, ordem, TDD red→green) sai depois via `superpowers:writing-plans`, **após aprovação**. Nada de código antes do aceite.

---

## 1. Contexto e motivação

O `ini-audit` aplica um catálogo de **487 regras** (`cli/plugadvpl/lookups/ini_rules.json`) contra arquivos INI Protheus. A skill vende essas regras como *"487 regras de boas práticas **TDN-oficiais**"* com *"link TDN oficial"* no `sugestao_fix`.

A investigação mostrou que essa alegação **não se sustenta no dado**:

- As 487 regras nasceram num **único commit** (`64b1aeb`, #6), sem script gerador versionado e sem trilha pra fonte.
- O padrão denuncia geração em lote por LLM: `descricao` genérica repetida (*"Configuração da seção [X] do TSS Protheus (extraído da TDN)."*) e **valores `expected` fabricados**.
- A "fonte" existe só como **texto livre** dentro de `fix_guidance` (`Ref: https://tdn...`), não como campo estruturado — e pra TSS inteiro aponta pra **uma única** página genérica.

Resultado prático: o auditor **"inventa tag"** (flagueia chave/valor que não procede), e em pelo menos um caso **recomenda configuração insegura**. Isso queima confiança — o usuário não sabe quais findings respeitar.

---

## 2. Diagnóstico (evidência)

| # | Severidade | Achado | Evidência |
|---|---|---|---|
| 1 | 🔴 **Segurança** | `TSS-SSLCONFIGURE-SSL2`/`SSL3` recomendam **`=1`** (habilitar protocolo inseguro). A gêmea APP corretamente diz `=0` ("SSLv2 INSEGURO. Deve estar desabilitado"). Um TSS **seguro** (SSL2=0) é marcado **crítico → FORA DE CONFORMIDADE** e o fix manda **ligar**. | `expected='1'`, `fix_guidance='Recomendado: 1'`, `descricao` genérica "extraído da TDN" |
| 2 | 🔴 **Contradição** | `APP-GENERAL-MAXSTRINGSIZE`: `expected='1\|Maior\|Menor'` (enum sem sentido); o fix recomenda **`10`**, que nem está no enum → a regra reprova o valor que ela mesma recomenda. | `detection_kind=value_in`, `expected='1\|Maior\|Menor'`, fix "Recomendado: 10" |
| 3 | 🟠 **No-op** | **72 regras `range_check` (15%)** com `expected` **vazio** → `lo=hi=None` → `_evaluate_value` sempre retorna `True`. Decorativas: alegam checar range, não checam nada. | `ini_audit.py:341-346` |
| 4 | 🟠 **Falso-positivo** | **30 `key_present`** em seções **opcionais de feature** (`[Mail]`, `[FTP]`, `[SQLiteServer]`, `[WebApp]`, `[WebAgent]`...) → flagam "missing" pra feature que o cliente não usa. | amostra das 30 |
| 5 | 🟡 **Ruído** | **367 de 487 (75%) são `info`** — justo o que a PR #37 silenciou. Confirma que a #37 trata o **sintoma** (esconde info-missing), não a **causa** (regras não-verificadas). | distribuição por severidade |

**Causa-raiz comum:** ausência de **procedência estruturada** e de **status de verificação**. Sem isso não há como (a) confiar/filtrar por curado, (b) não-flagar chave condicional, (c) auditar a própria base, (d) corrigir em lote com rastreabilidade.

---

## 3. Objetivo

Tornar o catálogo **confiável e rastreável**, sem regredir a cobertura legítima:

1. **Procedência estruturada** — cada regra aponta pra fonte real (pageId/URL TDN) num campo próprio.
2. **Status de verificação** — distinguir regra **curada** (validada contra TDN/realidade) de **não-verificada** (a maioria hoje).
3. **Chaves condicionais** — marcar opcionais-de-feature pra não virarem "missing".
4. **Corrigir o dado quebrado** — bugs 1, 2, 3 acima.
5. **Processo de curadoria** — guard test + fluxo de validação em lote pela turma.

**Não-objetivo:** reescrever as 487 de uma vez (TDN bloqueia scrape — ver §6). A curadoria é incremental.

---

## 4. Mudanças de schema (`ini_rules`)

Migração nova (`021_ini_rules_proveniencia.sql`) adicionando colunas (todas com default seguro pra não quebrar seed atual):

| Campo | Tipo | Significado |
|---|---|---|
| `fonte` | TEXT `''` | URL/pageId TDN **estruturado** (substitui o `Ref:` solto no fix_guidance) |
| `verificado` | INTEGER `0` | `0`=não-verificada (default), `1`=curada/validada. Permite gate `--only-verified` |
| `condicional` | INTEGER `0` | `1`=chave opcional-de-feature → **nunca** vira finding de "missing" |
| `default_totvs` | TEXT `''` | valor default documentado pela TOTVS (contexto no relatório) |
| `versao_min` | TEXT `''` | versão Protheus mínima onde a chave existe (futuro: cruzar com build) |

- `ini_rules.json` ganha os 5 campos (seed). `db.py::_LOOKUP_FILES` já cobre o arquivo; só estende colunas.
- `SCHEMA_VERSION` 20 → 21; `docs/schema.md` atualizado.
- **Compat:** colunas com default → INIs já ingeridos não quebram; re-seed popula o que for curado.

### Decisão de comportamento (em aberto — ver §9)

Duas posturas possíveis pro `verificado`:
- **(a) Conservadora:** por default o audit **só roda regras `verificado=1`**; não-verificadas só com `--include-unverified`. Zero falso-positivo de cara, cobertura cresce com a curadoria.
- **(b) Transparente:** roda tudo, mas marca não-verificadas no output (`[não-verificada]`) e nunca deixa elas derrubarem o selo (só `verificado=1` pune score).

---

## 5. Mudanças na lógica do audit (`parsing/ini_audit.py`)

1. **Condicional não vira missing:** no ramo `key_row is None`, pular se `rule.condicional` (independe da severidade).
2. **Gate de verificação:** conforme decisão §4 — filtrar no `_load_rules_for_target` (postura a) ou anotar finding + isentar do score (postura b).
3. **`fonte` no output:** o relatório passa a mostrar `fonte` estruturada em vez de extrair do texto.

---

## 6. Viabilidade de fonte — por que curadoria, não scrape

A fonte autoritativa **existe** (a TOTVS documenta cada parâmetro de appserver/dbaccess no TDN), mas:

- **TDN (`tdn.totvs.com`) e Central de Atendimento bloqueiam fetch automatizado (HTTP 403).** Confirmado com 2 URLs.
- Logo, **não dá** pra gerar/validar regras com scrape. Enriquecer = **curadoria humana assistida**:
  - a turma valida lotes contra o TDN (acesso autenticado/manual),
  - ou colamos trechos do TDN aqui e eu estruturo,
  - regras viram `verificado=1` só após esse aceite.

---

## 7. Correções imediatas (quick-wins de dado — independem do schema novo)

Pequenas, alto valor, podem ser uma PR isolada antes da curadoria:

- **Bug 1 (segurança):** `TSS-SSLCONFIGURE-SSL2`/`SSL3` → `expected='0'` + `descricao`/`fix` corretos (alinhar com APP). *Crítico — sai primeiro.*
- **Bug 2:** `APP-GENERAL-MAXSTRINGSIZE` → `detection_kind=range_check` com range sensato (ex: `1..` ) ou remover o enum bogus; fix coerente.
- **Bug 3:** as **72 `range_check` vazias** → popular o range (quando souber) ou rebaixar pra `key_present`/remover. Decisão por regra na curadoria; no quick-win, no mínimo um **guard test** que proíbe `range_check` com `expected` vazio.

---

## 8. Processo de curadoria + guard test

Espelhar o `test_lint_catalog_consistency` (que já protege o catálogo de lint):

`test_ini_rules_consistency.py` falha o CI se:
- `range_check` com `expected` vazio;
- `value_in` com `expected` sem `|` (enum de 1 item) ou com tokens não-numéricos suspeitos;
- regra `critical`/`warning` **gêmea** (mesmo key_name em tipos diferentes) com `expected` **contraditório** (pega o caso SSL2);
- `verificado=1` sem `fonte` preenchida.

**Meta-audit script** (`scripts/audit_ini_rules.py`) que lista regras suspeitas por heurística (descricao genérica "extraído da TDN", expected vazio, etc.) → fila de curadoria priorizada.

---

## 9. Decisões em aberto (pra aprovação)

1. **Postura do `verificado`** — §4: **(a) conservadora** (só roda verificadas por default) ou **(b) transparente** (roda tudo, marca + isenta do score)? *Recomendo (b)* — não regride cobertura e é honesto no relatório.
2. **Quick-wins (§7) entram como PR própria já**, ou só dentro do esforço maior? *Recomendo PR própria já* — o bug de SSL é segurança.
3. **72 range vazias** — popular agora (precisa dado TDN da turma) ou rebaixar pra `key_present` por ora?
4. **Conjunto de campos (§4)** — os 5 servem? Cortar `versao_min`/`default_totvs` se for escopo demais pra v1?
5. **Release** — v0.21.0 carrega só schema+quick-wins, e curadoria pinga em releases seguintes?

---

## 10. Testes e riscos

- **Testes:** guard de consistência (§8); migração 021 idempotente; audit respeitando `condicional`/`verificado`; regressão dos bugs 1-3 (um INI seguro com SSL2=0 **não** pode mais virar crítico).
- **Risco — regressão de cobertura:** rebaixar/remover regras reduz findings; mitigado por (b) transparente + curadoria incremental.
- **Risco — esforço de curadoria:** 487 é muito; mitigado por priorização (meta-audit) + lotes pela turma. Não bloqueia o release de schema.
- **Risco — `fonte` duplicada/genérica:** a migração só **adiciona** o campo; a limpeza do `Ref:` solto no `fix_guidance` é parte da curadoria, não do schema.

---

## 11. Relação com a PR #37

Independente. A #37 (encoding + score: info/warning-missing) **sobe sozinha** como bugfix — inclusive **ajuda** aqui ao silenciar o ruído de info-missing enquanto a base não é curada. Este enriquecimento ataca a **causa**.
