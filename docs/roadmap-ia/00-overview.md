# Roadmap IA — "melhor resposta para qualquer pergunta ADVPL", com custo mínimo

> Documento-mestre. Cada fase tem um `.md` próprio com contexto aderente do plugadvpl + a melhoria detalhada + as etapas de TDD.
> Base: pesquisa profunda 2024–2026 (18 claims confirmadas em verificação adversarial 3-votos) + mapeamento do repo na v0.39.0.
> Data: 2026-06-14.

## A tese (validada por pesquisa)

O maior alavanca de qualidade num assistente de código com ferramentas **não é** o LLM se autocorrigir nem um juiz multi-agente caro. É **emparelhar o LLM com um verificador externo, sólido e determinístico** — o *LLM-Modulo Framework* ([Kambhampati, ICML 2024](https://proceedings.mlr.press/v235/kambhampati24a.html)). O CLI determinístico do plugadvpl (índice SQLite, call graph, dicionário SX, lint) **já é** esse verificador. Ou seja: o caminho de maior retorno **não é colar mais máquina agêntica**, é **fechar o loop** entre o agente e o índice e **instrumentar** isso para medir.

Evidência que sustenta o recorte:
- Autocorreção intrínseca (sem ground-truth) **não melhora e às vezes piora** — GPT‑4 GSM8K 95.5%→91.5%→89.0% ([Huang et al., ICLR 2024](https://arxiv.org/abs/2310.01798); [Stechly/Kambhampati, ICLR 2025](https://arxiv.org/abs/2402.08115)). → **não** fazer self-critique como mecanismo padrão.
- "Só re-perguntar travando num verificador sólido mantém quase todo o benefício" ([2402.08115](https://arxiv.org/abs/2402.08115)). → verificador determinístico + re-prompt cirúrgico > críticos elaborados.
- Alucinação de símbolo/citação é detectável por **set-membership** contra um grafo de verdade, **sem inferência semântica** ([Spracklen et al., USENIX Security 2025](https://arxiv.org/abs/2406.10279) mediu ~5–22% de pacotes alucinados verificando contra PyPI/npm). → o índice do plugadvpl é o "PyPI/npm" do ADVPL.

## Filtro de inclusão (só entra ganho alto × custo mínimo)

Conforme pedido, **só entram itens com ganho real e custo mínimo em tokens e performance.**

| ✅ Entra (este roadmap) | ❌ Fica de fora (anti-roadmap, com evidência) |
|---|---|
| **`verify-claims`** — verificador determinístico (1 chamada CLI, lookup sub-ms, JSON compacto) | **Roteador aprendido (GNN/AgentRouter)** — pesado, exige treino, e a alegação de superioridade foi **refutada 0‑3** ([2510.05445](https://arxiv.org/pdf/2510.05445)) |
| **Eval harness** — scorer determinístico = $0; juiz LLM só opt-in/offline | **Debate/juiz multi-agente no caminho padrão** — custa 3x+ e até dezenas de min/tarefa; task-dependent, perde p/ maioria simples em tarefa fácil ([2508.02994](https://arxiv.org/html/2508.02994v1), [2510.12697](https://arxiv.org/html/2510.12697v1)) |
| **Fluxo grounded** — +1 chamada + re-prompt só do que falhou, só quando há símbolo afirmado | **Self-critique/reflexion intrínseco** — degrada qualidade ([2310.01798](https://arxiv.org/abs/2310.01798)) |
| **Dispatch hardening** — editar descrições (uma vez) + routing-eval determinístico ($0 em runtime) | **Embeddings/RAG semântico (sqlite-vec)** — adiciona infra (modelo + vector store), quebra o offline/byte-idêntico, e **não há evidência sobrevivente** de que supere lookup determinístico em código |

> Debate só reaparece como **modo "deep review" opt-in** (não default), gated por dificuldade + early-stopping, dentro do `advpl-reviewer-bot`. Não é fase deste roadmap; é nota no item de dispatch.

## As fases

| Fase | Item | O que entrega | Ganho | Custo marginal | Depende de | Doc |
|---|---|---|---|---|---|---|
| **1** | `verify-claims` | Comando determinístico que recebe símbolos afirmados e devolve verdict JSON (existe / não-encontrado / relação-vale) com bloco de cobertura | Anti-alucinação barata e robusta; primitiva reusável | ~0 tokens (1 call, saída compacta); lookups indexados | índice atual (nada novo) | [01-verify-claims.md](01-verify-claims.md) |
| **2** | Eval harness | Golden Q&A + scorer determinístico (reusa `verify-claims` p/ faithfulness) + gate de regressão no CI | **Gate de medição**: prova que qualquer mudança ajuda antes de shipar | $0 determinístico; juiz LLM opt-in/offline | Fase 1 (reusa) | [02-eval-harness.md](02-eval-harness.md) |
| **3** | Fluxo grounded | Skill + **Stop hook** + fragment que aciona `verify-claims` antes de finalizar e re-prompta só o que falhou | Consistência/menos alucinação na resposta real | +1 call + re-prompt só em falha, só com símbolo afirmado; ≤2 rounds | Fase 1 (comando) + Fase 2 (medir) | [03-grounding-flow.md](03-grounding-flow.md) |
| **4** | Dispatch hardening | Descrições/`when_to_use` afiados + tabela de decisão fina + **routing-eval** no CI | Skill/subagent certo escolhido de forma consistente | $0 em runtime (a seleção o modelo já faz) | Fase 2 (infra de eval) | [04-dispatch-hardening.md](04-dispatch-hardening.md) |

### Grafo de dependência

```
Fase 1 (verify-claims) ──► Fase 2 (eval harness) ──► Fase 3 (grounding flow)
        │                          │
        └──────────────────────────┴──► Fase 4 (dispatch hardening)
```

A Fase 1 é a primitiva (a "verificação determinística de existência" nasce aqui e é reusada como scorer de faithfulness na Fase 2). A Fase 2 é o gate que valida as Fases 3 e 4.

## Princípios transversais (valem em toda fase)

1. **Core determinístico/offline preservado.** Nenhuma chamada de modelo entra no caminho quente do CLI. O CLI só expõe **primitivas melhores (JSON in/out)**; quem orquestra é o agente do host (Claude Code/Cursor/Codex/Gemini) — exatamente a postura atual e coerente com o anti-roadmap "não virar orquestrador de agents".
2. **LLM-in-the-loop só opt-in, offline, nunca default.** Único uso de modelo previsto = o juiz **opcional** do eval harness (Fase 2). Preserva privacy/byte-idêntico/zero-dependência.
3. **Token-frugal por construção.** Saídas JSON compactas; verificação só dispara quando há símbolo afirmado; re-prompt carrega só os nomes que falharam, nunca re-lê fontes.
4. **TDD primeiro.** Toda fase segue o padrão do repo: teste → implementação → wiring → run. Tudo determinístico é unit-testável sem LLM (ver fixtures `synthetic_project`/`indexed_project` em [cli/tests/integration/test_cli.py](../../cli/tests/integration/test_cli.py)).
5. **Reusar a superfície que já existe.** Nada de reescrever: `verify-claims` lê as tabelas que o índice já tem; o eval reusa o scorer; o fluxo grounded reusa o comando; o dispatch reusa o catálogo de skills.

## Como medimos sucesso

A Fase 2 (eval harness) é o juiz de tudo. Sem ela não há prova de ganho — e a pesquisa é unânime que **o eval é pré-requisito para justificar qualquer custo extra**. Métrica-âncora: **faithfulness de símbolo** = (símbolos citados que existem no índice) / (símbolos citados), medida determinística sobre um índice-fixture. Secundárias: exact-match em perguntas categóricas, e (opt-in) helpfulness via juiz LLM com modelo diferente do gerador.

## Postura sobre LLM-in-the-loop (decidida)

**Manter o core determinístico/offline.** A alavanca durável é *verificador determinístico + o LLM que já roda no host fazendo re-prompt grounded*. Não construímos orquestrador nem colocamos modelo no CLI. Qualquer uso de LLM (juiz do eval, modo deep-review com debate) é **opt-in, offline e nunca o caminho padrão**.

## Ressalvas honestas (herdadas da pesquisa)

- **Transferência por analogia.** Nenhum estudo mediu ADVPL/Protheus nem code‑RAG‑sobre‑índice direto. Por isso a Fase 2 (eval) não é opcional: é como confirmamos o ganho no nosso domínio.
- **Política de "não encontrado".** Um símbolo ausente do índice é três coisas distintas — alucinação real, lacuna de cobertura, ou símbolo customer-specific. A Fase 1 trata isso explicitamente (mundo aberto por padrão; só chama "alucinação" quando o corpus é sabidamente completo para aquele tipo, ex.: SX2/SX3).
- **Onde o verificador determinístico brilha** = subtarefas de restrição dura (existe? é o hook MVC certo? a query usa `%notDel%`?), menos em qualidade aberta/estilística.
