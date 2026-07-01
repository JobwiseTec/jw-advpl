# Fase 2 — Eval harness (golden Q&A + scoring determinístico + gate de regressão)

> **Objetivo:** um harness que mede objetivamente a qualidade da resposta para perguntas ADVPL, com um **piso determinístico de custo $0** (reusa o `verify-claims` da Fase 1) e um **juiz LLM opcional/offline** só onde o determinístico não alcança. Vira o **gate** que prova que qualquer mudança (Fases 3 e 4) ajuda — antes de shipar.
>
> **Ganho:** sem isto não há prova de ganho; toda a literatura trata o eval como **pré-requisito** para justificar custo. **Custo:** determinístico = $0 e byte-reprodutível; juiz = só opt-in.

---

## 1. Por que vem logo após a primitiva

A pesquisa é unânime: o eval é o **pré-requisito** para justificar qualquer custo extra, e o piso determinístico (schema/regex/exact-match/faithfulness) **filtra 30–60% das falhas de graça**, antes de invocar qualquer juiz ([FutureAGI](https://futureagi.com/blog/deterministic-llm-evaluation-metrics-2026/) · [LangWatch](https://langwatch.ai/blog/essential-llm-evaluation-metrics-for-ai-quality-control)). E o ativo mais valioso já nasce na Fase 1: **faithfulness de símbolo** (a resposta só cita símbolos que existem no índice) é computável determinísticamente via `verify-claims` — é a [faithfulness do RAGAS](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/) (claims suportadas / total) calculada contra o índice em vez de um LLM.

## 2. Contexto aderente — o que o plugadvpl JÁ tem

- **Infra de teste pronta**: `cli/tests/{unit,integration}/`, runner `pytest` via `uv`, fixtures `synthetic_project`/`indexed_project` + `CliRunner` ([cli/tests/integration/test_cli.py](../../cli/tests/integration/test_cli.py)), gerador de fontes sintéticos em `cli/tests/fixtures/`. → o golden set e o runner moram aqui, reusando o índice-fixture.
- **CI já existe** ([.github/workflows/ci.yml](../../.github/workflows/ci.yml)): jobs `lint-plugin`, `lint-code`, `test-cli` (matrix), `smoke-uvx`. → adicionamos um job `eval-gate` (determinístico) no mesmo arquivo.
- **`verify-claims` (Fase 1)** = o scorer de faithfulness. Não reimplementamos: importamos `verify.verify_claims`.
- **Saída JSON canônica** ([cli/plugadvpl/output.py](../../cli/plugadvpl/output.py)) → o scorecard sai em JSON, comparável contra baseline.

## 3. A melhoria proposta (design em 2 camadas)

A pergunta "a resposta ficou melhor?" tem dois níveis, e separá-los é o que mantém o custo baixo:

### Camada A — eval determinístico de grounding (no CI, $0, gate de regressão)
Mede se a **ferramenta entrega o material certo** e se uma resposta gravada é **fiel** ao índice. Roda em todo PR, byte-reprodutível, sem LLM.
- **Faithfulness de símbolo** (âncora): pega a resposta-canônica gravada de cada caso golden, extrai os símbolos citados e roda `verify-claims`; score = símbolos `exists` / símbolos citados. Regressão = score cai.
- **Exact-match** em perguntas categóricas (a função X existe? em qual arquivo?), com normalização de espaço/caixa.
- **Checks estruturais**: chaves obrigatórias presentes, strings proibidas ausentes (armadilhas de alucinação tipo `MsWord`/`FWLerExcel`), arquivo/linha citados batem.

### Camada B — eval da resposta do agente (opt-in, offline, NÃO no caminho padrão do CI)
Roda o LLM do host sobre o golden set e pontua a **resposta final real** — usado para validar as Fases 3/4 (mostrar que o fluxo grounded melhora a qualidade ponta-a-ponta). Custa tokens e é não-determinístico → roda manual/nightly, gated por flag, nunca bloqueia PR.
- **Faithfulness** da resposta gerada (determinístico, via `verify-claims`).
- **Helpfulness** (1–5) via **juiz LLM opcional** — só aqui entra modelo, com as travas da §5.

### Formato do golden set (YAML, no estilo sidecar do `ideias.md` B3)

```yaml
# evals/golden/mvc.yaml
- id: mvc-hook-moderno
  category: advpl-mvc
  question: "Como adicionar um hook de commit num cadastro MVC sem usar bCommit?"
  # checks determinísticos (Camada A):
  must_mention_symbols: ["FWModelEvent", "InstallEvent"]   # devem existir no índice/nativas
  must_not_mention: ["bCommit", "bTudoOk"]                  # armadilha: descontinuados
  expected_skill: advpl-mvc                                  # cruza com Fase 4 (routing eval)
  # rubrica opcional (Camada B, juiz):
  judge_rubric: "A resposta recomenda FWModelEvent+InstallEvent e desencoraja bCommit?"
```

## 4. Implementação com TDD (sub-fases)

**Pasta nova:** `evals/golden/*.yaml` (dados) + `cli/plugadvpl/eval/` (runner) ou `cli/tests/eval/`. Reusa `verify.py`.

### 2a — Schema + loader do golden set (RED→GREEN)
- **Teste** (`tests/unit/test_eval_loader.py`): carrega um YAML de exemplo; valida campos obrigatórios; rejeita caso malformado.
- **Impl**: loader + validador de schema (stdlib + PyYAML, já dependência? senão JSON).

### 2b — Scorers determinísticos
- **Testes**: dado um caso + resposta-canônica + índice-fixture → faithfulness=1.0 quando todos símbolos existem; <1.0 com símbolo inventado; exact-match e structural cobertos; armadilha `must_not_mention` falha quando a string aparece.
- **Impl**: `score_faithfulness(answer, conn)` (chama `verify_claims`), `score_exact_match`, `score_structural`. Sem LLM.

### 2c — Runner + scorecard + baseline + gate
- **Testes**: runner sobre golden-fixture → scorecard JSON (`{by_category, totals, per_case}`); comparação contra `evals/baseline.json` falha quando algum eixo cai abaixo do limiar; é estável em re-runs (determinístico).
- **Impl**: runner + `--update-baseline`; thresholds calibrados da distribuição do baseline (não chutados).

### 2d — Job de CI `eval-gate` (determinístico)
- **Impl**: job em [.github/workflows/ci.yml](../../.github/workflows/ci.yml) que roda a Camada A e falha em regressão. ⚠️ **Gotcha de credencial**: o token `gh` não tem escopo `workflow` para *mergear* PR que toca `.github/workflows/`; o `git push` do arquivo é OK, mas o merge sai por `gh pr merge --auto` (ver memória de release). Planejar o PR que adiciona o job com isso em mente.

### 2e — (opt-in) Eval da resposta do agente + juiz LLM
- **Testes**: harness do juiz com modelo **mockado** (determinístico no teste); valida parsing da nota, aplicação da rubrica, e que o caminho é **gated por flag** (default off).
- **Impl**: modo `--with-agent` (roda o host model) + `--with-judge` (juiz opcional). Travas da §5. Nunca no CI default.

## 5. Juiz LLM — só onde o determinístico não alcança (helpfulness)

Faithfulness já é coberta deterministicamente; o juiz fica só para **qualidade da explicação**. Travas obrigatórias (todas com evidência):
- **Modelo do juiz ≠ modelo gerador** (self-preference bias) ([Panickssery 2024, 2410.21819](https://arxiv.org/pdf/2410.21819); Anthropic recomenda o mesmo).
- **Position bias** → trocar ordem / múltiplas evidências; **verbosity bias** → win-rate controlado por tamanho ([taxonomia de vieses, 2410.02736](https://arxiv.org/pdf/2410.02736)).
- **Rubrica detalhada, saída restrita** (`correct`/`incorrect` ou 1–5), pedir-e-descartar o raciocínio, **temperatura 0** ([guia de avaliação Anthropic](https://platform.claude.com/docs/en/docs/build-with-claude/develop-tests)).
- **Mais barato ainda**: usar o classificador **HHEM** ou *Response Groundedness* do RAGAS no lugar de um juiz LLM quando der ([RAGAS](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)).
- **Juiz é advisory, nunca gate.** O CI trava só na Camada A determinística; nota do juiz é tendência ([LayerLens](https://layerlens.ai/blog/how-to-detect-llm-regression-in-production)).

## 6. Métricas

- **Determinísticas (gate primário):** faithfulness de símbolo (citados-no-índice / total), exact-match, pass-rate estrutural.
- **Code-flavored:** `pass@k` (estimador `1 − C(n−c,k)/C(n,k)`) — relevante se um dia validarmos ADVPL gerado executando; para Q&A, pass@1 exact-match é o análogo.
- **Juiz (advisory):** helpfulness 1–5, groundedness.

## 7. Custo & performance

- **Camada A:** $0 (sem LLM), sub-segundo, byte-reprodutível, roda em todo PR.
- **Camada B:** custa tokens só quando rodada manualmente/nightly com `--with-agent`/`--with-judge`. Fora do caminho padrão.
- **Tamanho do golden set:** começar **50–150** casos (cresce colhendo falhas reais), suficiente para sinal de regressão sem inflar o CI ([Maxim](https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide/), [TestQuality](https://testquality.com/llm-regression-testing-pipeline/)).

## 8. Pitfalls / decisões em aberto

1. **Não começar pelo juiz LLM** — caro e não-determinístico; o piso determinístico pega a maioria das regressões de graça.
2. **Self-preference**: nunca julgar com o mesmo modelo que gerou.
3. **Overfit / contaminação** do golden set; refrescar a partir de falhas reais de produção, não inventar tudo no início ([Anthropic: volume > qualidade por item](https://platform.claude.com/docs/en/docs/build-with-claude/develop-tests)).
4. **Flakiness do juiz não pode travar CI** — gate só na Camada A.
5. **Decisão em aberto**: a resposta-canônica da Camada A é gravada à mão por caso? Sugestão: gravar uma vez (snapshot revisado por humano) e versionar; o agente-real (Camada B) é o que valida que a resposta viva continua boa.

## 9. Definition of Done

- [ ] `evals/golden/*.yaml` com 50–150 casos (distribuição real + ~20 armadilhas de alucinação/decline).
- [ ] Scorers determinísticos (faithfulness via `verify-claims`, exact-match, estrutural) com testes.
- [ ] Runner + `evals/baseline.json` + gate de regressão; estável em re-run.
- [ ] Job `eval-gate` (Camada A) no CI, verde.
- [ ] Modo opt-in `--with-agent`/`--with-judge` com travas de viés, default off, fora do CI.
- [ ] Doc `docs/eval-harness.md` (como adicionar caso, como ler o scorecard).

## 10. Fontes

- [Anthropic — develop-tests (code/exact-match/LLM grading, rubrica, temp0, juiz ≠ gerador, volume > qualidade)](https://platform.claude.com/docs/en/docs/build-with-claude/develop-tests)
- [RAGAS — faithfulness = claims suportadas/total; HHEM e Response Groundedness mais baratos](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)
- [FutureAGI — "eval floor" determinístico ($0, todo request)](https://futureagi.com/blog/deterministic-llm-evaluation-metrics-2026/) · [LangWatch — determinístico filtra 30–60% das falhas](https://langwatch.ai/blog/essential-llm-evaluation-metrics-for-ai-quality-control)
- [Maxim — construção de golden dataset](https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide/) · [TestQuality — sizing 100–300 p/ gate](https://testquality.com/llm-regression-testing-pipeline/)
- [Self-preference bias (2410.21819)](https://arxiv.org/pdf/2410.21819) · [Taxonomia de vieses de juiz (2410.02736)](https://arxiv.org/pdf/2410.02736)
- [Galileo — gate de regressão + thresholds](https://galileo.ai/blog/building-an-effective-llm-evaluation-framework-from-scratch) · [LayerLens — não-determinismo (seeds/temp0/multi-run)](https://layerlens.ai/blog/how-to-detect-llm-regression-in-production)
