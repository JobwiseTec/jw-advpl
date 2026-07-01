# Fase 4 — Endurecimento do dispatch (descrições/triggers + tabela de decisão + routing-eval)

> **Objetivo:** garantir que, para qualquer pergunta ADVPL, o **skill/subagent certo** seja escolhido de forma consistente — afiando as `description`/`when_to_use` (a "rota" de verdade), mantendo uma tabela de decisão fina só para os clusters que colidem, e travando isso com um **routing-eval** no CI.
>
> **Ganho:** consistência na seleção (a maior fonte de resposta ruim "silenciosa" hoje). **Custo:** $0 em runtime — a seleção o modelo já faz; só editamos texto e adicionamos um eval determinístico.

---

## 1. Por que isto importa (e por que é barato)

No Claude Code/Agent SDK **a `description` É o roteador**: o modelo pré-carrega só `name`+`description` (~100 tokens/skill) e casa a tarefa contra essas strings; o corpo do `SKILL.md` carrega só no trigger ([Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview); [equipping-agents](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)). "A description é crítica para a seleção: o Claude a usa para escolher a Skill certa entre 100+" ([best-practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)). Ou seja: o ganho de consistência sai **de editar texto**, sem custo de runtime — e a pesquisa diz para **não** colocar roteador semântico/LLM quando a intenção já está disponível no call site (que é o nosso caso): roteamento estático é "sub-ms, determinístico e trivial de depurar" ([TrueFoundry](https://www.truefoundry.com/blog/llm-routing-cost-quality-aware-model-selection); [n8n](https://blog.n8n.io/llm-routing/)).

## 2. Contexto aderente — o que o plugadvpl JÁ tem (e já faz bem)

- **~70 skills** com frontmatter `description` ([skills/](../../skills/)), catálogo + validação em [cli/plugadvpl/_skill_catalog.py](../../cli/plugadvpl/_skill_catalog.py) e testes de catálogo ([cli/tests/unit/](../../cli/tests/unit/)).
- **6 subagents** ([agents/](../../agents/)) com `description` que decide a delegação.
- **Tabela de decisão** já existe no fragment ([cli/plugadvpl/cli.py](../../cli/plugadvpl/cli.py), `_CLAUDE_FRAGMENT_BODY`): "Explique o fonte" → `arch`, "Quem chama" → `callers`, etc.
- **Pistas negativas já usadas** (o padrão mais forte de desambiguação): `advpl-mvc-tlpp` diz *"Para MVC em .prw clássico use advpl-mvc"*; `advpl-word` lista APIs alucinadas a rejeitar. → manter isso **consistente** nos clusters densos.

**Clusters que colidem** (onde o shadowing nasce): `advpl-mvc` / `advpl-mvc-avancado` / `advpl-mvc-tlpp`; `advpl-web` / `advpl-webservice`; `advpl-excel` / `advpl-word`; `advpl-debugging` / `advpl-log-investigator`.

## 3. A melhoria proposta

### (a) Regras de escrita de `description`/`when_to_use` (do/don't)
Direto da doc Anthropic:
- **Diga O QUÊ + QUANDO**, não só o quê (regra mais repetida).
- **Terceira pessoa** sempre ("Use ao…", nunca "Eu ajudo…") — a description entra no system prompt ([best-practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)).
- **Empacotar palavras-gatilho literais / frasings do usuário** (Claude Code tem campo `when_to_use` exatamente para "trigger phrases").
- **Front-load do caso principal** — a listagem trunca em **1.536 chars** e, com muitas skills, palavras-chave das **menos usadas são cortadas primeiro**; conferir com `/doctor` ([skills](https://code.claude.com/docs/en/skills)).
- **Pistas negativas** ("NÃO use para X; use Y") como desambiguador mais forte.
- **Nomes-gerúndio, nada vago** — evitar `helper`, `utils`, `tools`, `data`, `files`.

### (b) Tabela de decisão = camada fina de desambiguação
A tabela do fragment **não** é o catálogo: é só as **colisões genuínas**, em linhas "escolha X NÃO Y quando…". A doc Anthropic manda manter CLAUDE.md curto ("<200 linhas; CLAUDE.md inchado faz o Claude ignorar instruções" — [best-practices](https://code.claude.com/docs/en/best-practices)). Então as `description` (com `when_to_use` + cláusula de exclusão) carregam o peso; a tabela só resolve o punhado de ambiguidades que a description não resolve.

### (c) Routing-eval (o que faltava)
A peça nova: um eval que mede a **acurácia de seleção** e pega *skill shadowing* à medida que as ~70 skills crescem.

## 4. Implementação com TDD (sub-fases)

Reusa a infra da **Fase 2** (o golden set já tem `expected_skill`).

### 4a — Lint determinístico de descrições (CI, $0)
- **Teste** (`tests/unit/test_skill_descriptions.py`): falha em description vaga (regex de termos proibidos: `helper/utils/tools/data/files`), em 1ª pessoa, em ausência de "Use/quando", e sinaliza overlap de keyword entre skills do mesmo cluster sem cláusula "NÃO use".
- **Impl**: estender [validate_plugin.py](../../scripts/validate_plugin.py) / `_skill_catalog.py` com esses checks. Roda no job `lint-plugin` que já existe.

### 4b — Routing-eval (opt-in, LLM, offline)
- **Teste**: harness com modelo **mockado** valida que, dado `(query → expected_skill)`, o scorer computa **top-1 exact-match** e **set-F1** corretamente; inclui casos **abstain/negativos** (nenhuma skill se aplica — molde [BFCL relevance](https://gorilla.cs.berkeley.edu/leaderboard.html)).
- **Impl**: modo `--routing` no runner do eval (Fase 2) que pede ao modelo (1 classificação, temp 0) a skill para cada query rotulada; mede top-1 ([Braintrust RouteAccuracy](https://www.braintrust.dev/blog/evaluating-agents); [promptfoo `skill-used`/`tool-call-f1`](https://www.promptfoo.dev/docs/guides/test-agent-skills/); [DeepEval Tool Correctness, determinístico](https://deepeval.com/docs/metrics-tool-correctness)). Default off, fora do CI padrão.

### 4c — Afiar descrições dos clusters que colidem
- **Loop determinístico**: rodar o routing-eval, achar os pares confundidos (mvc vs mvc-tlpp, web vs webservice, excel vs word, debugging vs log-investigator), e o fix é **na description** (gatilhos mais precisos + cláusula "NÃO use para … use …"); re-rodar. Cada edição validada pelo eval.
- **Dataset**: ~10–20 queries rotuladas por skill, semeadas de perguntas ADVPL reais + near-duplicates adversariais entre os clusters.

### 4d — Tabela de decisão fina no fragment
- **Teste**: o fragment gerado contém as linhas de desambiguação dos clusters; segue <200 linhas.
- **Impl**: linhas "X NÃO Y quando…" só para as colisões reais.

## 5. Custo & performance

- **Runtime:** $0. A seleção é o que o modelo já faz com as descrições; não adicionamos roteador, embedding nem chamada.
- **CI:** o lint de descrições (4a) é determinístico, sub-segundo, roda no `lint-plugin` atual. O routing-eval LLM (4b) é **opt-in/offline**, não bloqueia PR por padrão.
- **Latência de seleção:** estática (a description já está no system prompt) — 5–20 ms equivalente, vs 430–2000 ms de um roteador LLM que **não** vamos usar ([tiers](https://blog.meganova.ai/the-3-tier-routing-cascade-rule-based-semantic-llm/)).

## 6. Nota — modo "deep review" opt-in (debate), fora do default

Debate/juiz multi-agente **não** entra no caminho padrão (custa 3x+, task-dependent). Mas há um nicho legítimo: o `advpl-reviewer-bot` em revisões **ambíguas/alto-risco**, como **modo opt-in** com early-stopping (parar quando os julgamentos estabilizam — [Beta-Binomial + KS stopping, 2510.12697](https://arxiv.org/html/2510.12697v1), 20–80% menos rounds). Só ativar sob pedido explícito; nunca em pergunta de rotina. É nota de backlog, não fase deste roadmap.

## 7. Pitfalls / decisões em aberto

1. **Skill shadowing**: uma description que casa melhor a query "sequestra" a seleção — causou **até 68%** da degradação e **−21% de pass-rate a 202 skills** ([2605.24050](https://arxiv.org/html/2605.24050)). A 70 skills já estamos na zona de risco; o routing-eval é o detector.
2. **Excesso de near-duplicates** colapsa a acurácia (~30 tools; 13,62% → 43,13% com pré-filtro — [RAG-MCP, 2505.03275](https://arxiv.org/abs/2505.03275)). Manter overlap mínimo entre skills do mesmo cluster.
3. **Não over-especificar o caminho** no eval — pontuar a **skill escolhida**, não uma sequência de tools, pra não penalizar alternativa válida ([writing-tools](https://www.anthropic.com/engineering/writing-tools-for-agents)).
4. **Decisão em aberto**: padronizar um campo `when_to_use` no frontmatter das SKILL.md (hoje só `description`)? Recomendado — alinha com o Claude Code e dá lugar canônico p/ as palavras-gatilho.

## 8. Definition of Done

- [ ] Lint determinístico de descrições no `lint-plugin` (vago/1ª-pessoa/overlap-sem-exclusão), verde.
- [ ] Routing-eval (top-1 + set-F1 + casos abstain) opt-in, com baseline e gate de acurácia.
- [ ] Descrições dos 4 clusters colidentes afiadas (gatilhos + cláusula "NÃO use"), validadas pelo eval.
- [ ] Tabela de decisão fina no fragment (só colisões), <200 linhas.
- [ ] (Opcional) campo `when_to_use` padronizado no frontmatter.

## 9. Fontes

- [Anthropic — Agent Skills overview / best-practices / equipping-agents / context-engineering / writing-tools](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) — description = roteador; O QUÊ+QUANDO; 3ª pessoa; gatilhos; overlap mínimo.
- [Claude Code — skills (when_to_use, truncação 1.536, /doctor) e best-practices (CLAUDE.md <200 linhas)](https://code.claude.com/docs/en/skills)
- [Skill shadowing — até 68% da degradação, −21% pass-rate a 202 skills (2605.24050)](https://arxiv.org/html/2605.24050) · [RAG-MCP — colapso de seleção ~30 tools (2505.03275)](https://arxiv.org/abs/2505.03275)
- [Roteamento estático vs semântico vs LLM — TrueFoundry](https://www.truefoundry.com/blog/llm-routing-cost-quality-aware-model-selection) · [n8n](https://blog.n8n.io/llm-routing/) · [tiers de latência](https://blog.meganova.ai/the-3-tier-routing-cascade-rule-based-semantic-llm/)
- [Routing-eval determinístico — Braintrust RouteAccuracy](https://www.braintrust.dev/blog/evaluating-agents) · [promptfoo skill-used/tool-call-f1](https://www.promptfoo.dev/docs/guides/test-agent-skills/) · [DeepEval Tool Correctness](https://deepeval.com/docs/metrics-tool-correctness) · [BFCL relevance](https://gorilla.cs.berkeley.edu/leaderboard.html)
- [Early-stopping de debate (deep-review opt-in) — 2510.12697](https://arxiv.org/html/2510.12697v1)
