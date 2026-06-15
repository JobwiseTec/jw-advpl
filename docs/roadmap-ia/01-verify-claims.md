# Fase 1 — `plugadvpl verify-claims` (verificador determinístico / "sound verifier")

> **Objetivo:** um comando determinístico que recebe os símbolos que uma resposta afirmou (funções, tabelas, campos SX3, parâmetros `MV_*`, arestas de chamada, gatilhos) e devolve um **verdict JSON** dizendo, por símbolo, se ele **existe / não-encontrado / a relação vale**, com um bloco honesto de **cobertura**.
>
> **Ganho:** anti-alucinação barata e robusta — é o "PyPI/npm check" do ADVPL. **Custo:** ~0 tokens (1 chamada, saída compacta) e lookups SQLite sub-ms. É a primitiva que as Fases 2 e 3 reusam.

---

## 1. Por que esta é a Fase 1

A pesquisa aponta o verificador externo **sólido e determinístico** como a maior alavanca de qualidade ([LLM-Modulo, Kambhampati ICML 2024](https://proceedings.mlr.press/v235/kambhampati24a.html) · [2402.08115](https://arxiv.org/abs/2402.08115)). Alucinação de símbolo é justamente o erro que um lookup de set-membership pega de graça: o estudo de *package hallucination* mediu **5,2% (comercial) a 21,7% (open-source)** de pacotes inventados verificando contra PyPI/npm ([Spracklen et al., USENIX Security 2025](https://arxiv.org/abs/2406.10279)); a taxonomia de *code-API hallucination* mostra que **>50% das falhas invocam APIs inexistentes** e que a detecção canônica é literalmente **"index lookup: checar se o nome existe no índice"** ([2407.09726](https://arxiv.org/html/2407.09726v1)). O índice SQLite do plugadvpl **é** esse registro para ADVPL — então construir a primitiva de verificação primeiro destrava tudo.

## 2. Contexto aderente — o que o plugadvpl JÁ tem (e vamos reusar)

Não precisamos de tabela nova. O índice já guarda todos os tipos de símbolo que queremos verificar:

| `kind` do claim | Onde já está no índice | Coluna-chave de match |
|---|---|---|
| `function` (definida no fonte) | `fonte_chunks` | `funcao_norm` (nome normalizado, case-insensitive), `tipo_simbolo` |
| `function` (nativa TOTVS) | lookup `funcoes_nativas` (~1000+) | nome |
| `function` (restrita) | lookup `funcoes_restritas` | nome |
| `table` (SX2) | `tabelas` / `fonte_tabela` | prefixo/alias |
| `field` (SX3) | `campos` | nome do campo |
| `param` (`MV_*`) | `parametros_uso` (+ SX6 quando ingerido) | `parametro` |
| `call_edge` (A chama B) | `chamadas_funcao` | `arquivo_origem`/`funcao_origem` → `destino_norm` |
| `trigger` (SX7) | `gatilhos` | campo/tabela |

Infra que reusamos como molde:
- **Dispatch CLI** em [cli/plugadvpl/cli.py](../../cli/plugadvpl/cli.py) (Typer, `@app.command()`, flag global `--format json`).
- **Funções de query** em [cli/plugadvpl/query.py](../../cli/plugadvpl/query.py) (`find_any`, `q_callers`, `q_callees`, `tables_query`, `param_query`) — o `verify-claims` é uma query a mais, no mesmo padrão.
- **Render JSON** em [cli/plugadvpl/output.py](../../cli/plugadvpl/output.py) — mas atenção: o envelope padrão é `{rows, total, shown, truncated}`. O verdict tem forma própria (ver §4); vamos emitir um payload dedicado, não o envelope de linhas.
- **Schema/migrations** em [cli/plugadvpl/db.py](../../cli/plugadvpl/db.py) + `cli/plugadvpl/migrations/*.sql` (read-only aqui — não criamos tabela).
- **Normalização de identificador**: o parser já normaliza nomes (`funcao_norm`, `destino_norm`). Reusar a MESMA normalização é crítico (ver pitfall do truncamento 10 vs 250 chars).

## 3. A melhoria proposta (design)

Um comando `plugadvpl verify-claims` que:
1. recebe um lote de claims (JSON via stdin — ergonômico para o agente e batch-friendly);
2. resolve cada claim contra o índice por **set-membership exata** (sem fuzzy);
3. devolve um verdict **por claim** (nunca um verdict por resposta) + um bloco `coverage` honesto.

### Contrato — entrada

```json
{
  "claims": [
    {"id": "c1", "kind": "function", "symbol": "FWFormStruct"},
    {"id": "c2", "kind": "field",    "symbol": "ZX1_STATUS"},
    {"id": "c3", "kind": "param",    "symbol": "MV_LOJA"},
    {"id": "c4", "kind": "call_edge","caller": "U_ZEXAPROV", "callee": "FWLoadModel"},
    {"id": "c5", "kind": "trigger",  "table": "ZX1", "field": "ZX1_CLIENTE"}
  ]
}
```

### Contrato — saída (verdict)

```json
{
  "index_version": "advpl-idx-2026.06.14",
  "coverage": {
    "corpora": ["fontes", "sx2", "sx3", "sx6", "sx7", "call-edges", "funcoes_nativas"],
    "scope": "closed-world-over-indexed",
    "symbol_count": 184213,
    "complete_kinds": ["table", "field", "param"]
  },
  "results": [
    {"claim_id": "c1", "kind": "function", "symbol": "FWFormStruct",
     "status": "exists", "confidence": "high", "namespace_scope": "native",
     "evidence": {"source": "funcoes_nativas"}, "note": "função nativa TOTVS"},
    {"claim_id": "c2", "kind": "field", "symbol": "ZX1_STATUS",
     "status": "exists", "confidence": "high",
     "evidence": {"table": "campos", "tabela": "ZX1"}, "note": "campo customer no SX3"},
    {"claim_id": "c4", "kind": "call_edge", "symbol": "U_ZEXAPROV→FWLoadModel",
     "status": "relation_absent", "confidence": "low",
     "note": "aresta não indexada; call graph é esparso (macro/ExecBlock não capturados)"}
  ]
}
```

### Enum de `status` (5 valores, puramente mecânicos)

`exists` · `not_found` · `relation_holds` · `relation_absent` · `unsupported_kind` (o índice não sabe adjudicar esse tipo — impede o checker de fingir autoridade). Interpretação fica no `note`, nunca no `status`.

### `confidence` é proxy de **cobertura**, não probabilidade

Regra de ouro: **confiança cai em MISS, não em HIT.** Um `not_found` num corpus sabidamente completo para aquele tipo é significativo; um `not_found` num corpus parcial não prova quase nada.

### Matriz de completude (o campo de maior valor)

| `kind` | Corpus | Completo para… | `not_found` significa | confidence em miss |
|---|---|---|---|---|
| `table` / `field` / `param` | SX2/SX3/SX6 (dicionário ingerido) | **customizações do cliente** (padrão TOTVS é ignorado por design) | provável alucinação **se** for símbolo customer (`Z*`/prefixo cliente); senão pode ser padrão TOTVS não-ingerido | `high` p/ símbolo customer, `medium` senão |
| `function` | `fonte_chunks` + `funcoes_nativas` + `funcoes_restritas` | fontes indexados + nativas catalogadas | provável alucinação **se** não casa nativa nem restrita nem fonte | `medium` |
| `call_edge` / `trigger` | `chamadas_funcao` / `gatilhos` | esparso (estático não pega macro/`ExecBlock`/dinâmico) | **inconclusivo** | `low` (nunca cravar "alucinação") |

### Política de "não encontrado" (mundo aberto por padrão)

`not_found` **≠ "alucinado"**. Set-membership sobre índice incompleto é [Closed-World Assumption](https://en.wikipedia.org/wiki/Closed-world_assumption), que é **insólida** quando o índice é parcial. Então:
- **Default = linguagem de mundo aberto.** Só elevamos para um flag mais forte quando o corpus é *known-complete* para aquele kind (SX2/SX3 para símbolo customer qualificam; call-edges não).
- **Viés para falso-negativo** (deixar passar uma alucinação) sobre **falso-positivo** (chamar de fake um símbolo real). Um checker que grita lobo em toda `U_*` de cliente é ignorado.
- **Sempre enviar `coverage`** pra o consumidor (agente) não super-interpretar um gap como mentira.

Backing teórico: `verify-claims` é exatamente um *sound model-based critic* do LLM-Modulo ([2402.01817](https://arxiv.org/abs/2402.01817)); soundness exige conservadorismo — só afirmar o que o índice prova. Para relações (arestas/gatilhos) o molde é *Entity Grounding + Relation Preservation* sobre o grafo ([HalluGraph, 2512.01659](https://arxiv.org/html/2512.01659v1)).

## 4. Implementação com TDD (sub-fases)

Padrão do repo: teste primeiro → função pura → wiring CLI → integração. Tudo determinístico → unit-testável sem LLM. Fixtures: `synthetic_project`/`indexed_project` + `CliRunner` em [cli/tests/integration/test_cli.py](../../cli/tests/integration/test_cli.py); unit em [cli/tests/unit/](../../cli/tests/unit/).

**Módulo novo:** `cli/plugadvpl/verify.py` (função pura `verify_claims(conn, claims: list[dict]) -> dict`). Nenhuma migration.

### 1a — Contrato + esqueleto (RED→GREEN)
- **Teste** (`tests/unit/test_verify.py`): `verify_claims(conn, [])` devolve `{"index_version", "coverage", "results": []}` com `coverage.corpora` derivado das tabelas presentes.
- **Impl**: monta `coverage` lendo metadados do índice (contagem de símbolos, kinds completos); `results=[]`.

### 1b — Checkers de existência por kind (function/table/field/param)
- **Testes** contra um índice-fixture com símbolos conhecidos:
  - `ZX1_STATUS` (campo customer presente) → `exists/high`.
  - `ZX1_INEXISTENTE` (campo customer ausente) → `not_found/high` (SX3 completo p/ customer).
  - `FWFormStruct` (nativa) → `exists/high, namespace_scope=native`.
  - `MsWord` (alucinação clássica, já catalogada nas skills) → `not_found/medium`.
- **Impl**: um resolver por kind reusando a normalização do parser (`funcao_norm`). Função primeiro tenta fonte → nativa → restrita.

### 1c — Checkers de relação (call_edge, trigger)
- **Testes**: aresta presente em `chamadas_funcao` → `relation_holds/medium`; ausente → `relation_absent/low` (nunca `high`); `trigger` em `gatilhos` análogo.
- **Impl**: queries sobre `chamadas_funcao`/`gatilhos`; confidence travada em `low` para `relation_absent`.

### 1d — Cobertura + calibração de confiança + matriz de completude
- **Testes**: símbolo customer (`Z*`) ausente em SX3 → `high`; símbolo não-customer ausente → `medium`; `complete_kinds` reflete o que foi ingerido (se SX não ingerido, `table/field/param` saem de `complete_kinds`).
- **Impl**: a matriz da §3 vira tabela de decisão; `complete_kinds` calculado do estado do índice.

### 1e — Wiring CLI + stdin (integração)
- **Teste** (`tests/integration/test_cli.py::TestVerifyClaims`): `echo '{"claims":[...]}' | plugadvpl --root … --format json verify-claims --stdin` → JSON com `results` por claim; exit 0; sem vazar PII (respeitar `--privacy`).
- **Impl**: `@app.command("verify-claims")` lê stdin JSON, chama `verify_claims`, emite via um render dedicado (não o envelope de linhas). Suporta também forma curta `verify-claims --kind function --symbol FWFormStruct` para 1 claim.

### 1f — Skill + doc de contrato
- `docs/verify-claims-contract.md` (espelha §3, MIT) e nota na skill de índice ([plugadvpl-index-usage](../../skills/plugadvpl-index-usage/SKILL.md)) — usado pela Fase 3.

## 5. Custo & performance

- **Tokens:** 1 chamada de ferramenta; entrada = lista de nomes; saída = JSON compacto (status por claim). Ordens de magnitude mais barato que reler fontes. Nada de LLM no comando.
- **CPU/IO:** lookups indexados em SQLite (igual aos comandos `find`/`callers` atuais) — sub-ms por claim; lote de dezenas de claims em poucos ms.
- **Infra:** zero. Nenhuma dependência nova, nenhuma migration, offline/byte-idêntico preservado.

## 6. Pitfalls / decisões em aberto

1. **Nunca emitir "alucinado" de um miss seco** (erro de CWA) → usar `not_found` + `coverage`.
2. **Verdict por claim, não por resposta** — senão perde granularidade e o alvo do re-prompt (Fase 3).
3. **Match fuzzy reportado como `exists` destrói a soundness** — manter exato; near-match só no `note`.
4. **Normalização**: `.prw` trunca identificador em 10 chars, `.tlpp` em 250; prefixo `U_`/cliente. Usar a MESMA normalização do parser, senão geramos miss falso. (Reusar `funcao_norm`/`destino_norm`.)
5. **Grafos esparsos** (`chamadas_funcao`, `gatilhos`) não são autoritativos para `relation_absent` → travar em `low`.
6. **Decisão em aberto** (resolver na Fase 2 com dados do eval): qual o limiar exato de `confidence` por kind, e como o agente deve tratar `not_found/medium` — flag, silêncio, ou nota "verifique manualmente". O eval mede a taxa de falso-positivo por cobertura e calibra.

## 7. Definition of Done

- [ ] `cli/plugadvpl/verify.py` com `verify_claims(conn, claims)` puro, 100% determinístico.
- [ ] Cobertura de teste por kind (function/table/field/param/call_edge/trigger), incluindo casos de alucinação (`MsWord`, `FWLerExcel`) e de cobertura (símbolo customer ausente vs padrão TOTVS).
- [ ] `@app.command("verify-claims")` com `--stdin` (lote) e forma curta; `--format json`; respeita `--privacy`.
- [ ] Bloco `coverage` + `complete_kinds` + política de mundo aberto implementados e testados.
- [ ] `docs/verify-claims-contract.md` publicado.
- [ ] Suite verde no CI (unit + integration), sem dependência nova.

## 8. Fontes

- [Spracklen et al., USENIX Security 2025 — package hallucination (5,2–21,7%) verificado vs PyPI/npm](https://arxiv.org/abs/2406.10279)
- [Slopsquatting — repetibilidade da alucinação; registry check como mitigação](https://en.wikipedia.org/wiki/Slopsquatting) · [HelpNetSecurity (~19,7% agregado)](https://www.helpnetsecurity.com/2025/04/14/package-hallucination-slopsquatting-malicious-code/) · [Socket.dev](https://socket.dev/blog/slopsquatting-how-ai-hallucinations-are-fueling-a-new-class-of-supply-chain-attacks)
- [Code-API hallucination taxonomy — "index lookup" como gate; >50% das falhas são APIs inexistentes](https://arxiv.org/html/2407.09726v1)
- [HalluGraph — Entity Grounding + Relation Preservation sobre KG](https://arxiv.org/html/2512.01659v1)
- [LLM-Modulo — verificadores externos sólidos + back-prompting](https://arxiv.org/abs/2402.01817) · [PMLR](https://proceedings.mlr.press/v235/kambhampati24a.html)
- [Closed-World Assumption — base da política "not-found ≠ false"](https://en.wikipedia.org/wiki/Closed-world_assumption)
