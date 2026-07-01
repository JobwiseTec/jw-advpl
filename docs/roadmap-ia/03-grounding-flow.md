# Fase 3 — Fluxo de verificação grounded (fragment + Stop hook + skill)

> **Objetivo:** fazer o agente do host, **antes de finalizar** uma resposta ADVPL, extrair os símbolos que afirmou e rodar o `verify-claims` (Fase 1); se algum não existe, **re-promptar só o que falhou** e corrigir. É o *Chain-of-Verification* com a etapa de verificação **ancorada no índice** em vez da memória do modelo.
>
> **Ganho:** menos alucinação na resposta real, de forma consistente — o ponto exato da pesquisa. **Custo:** +1 chamada + re-prompt só em falha, só quando há símbolo afirmado; loop ≤2 rounds. Em resposta limpa: 1 chamada de verificador, 0 re-prompt.

---

## 1. A ideia, com a mudança que a torna sólida

*Chain-of-Verification* (CoVe) roda 4 passos: rascunho → planeja perguntas de verificação → responde-as **independentemente** → resposta final verificada ([Dhuliawala et al., ACL 2024](https://arxiv.org/abs/2309.11495)). Ganhos: ~2× de precisão em list-QA, FACTSCORE 55.9→71.4. **A mudança-chave:** o CoVe responde as perguntas de verificação da *memória do modelo* — e os próprios autores deixam "usar tool/retrieval na verificação" como trabalho futuro. O plugadvpl substitui esse passo por um **lookup determinístico** (`verify-claims`): a "resposta independente" vira **ground truth**, não um segundo palpite. É estritamente mais forte que o CoVe original.

O laço é gated por um verificador sólido (LLM-Modulo): "só re-perguntar travando num verificador sólido mantém quase todo o benefício" ([2402.08115](https://arxiv.org/abs/2402.08115)), com rounds **hard-capped** ([LLM-Modulo, 2402.01817](https://arxiv.org/abs/2402.01817)). E a trava de segurança: **só corrigir sob sinal real do verificador** — autocorreção intrínseca degrada ([Huang et al., 2310.01798](https://arxiv.org/abs/2310.01798)).

## 2. Contexto aderente — o que o plugadvpl JÁ tem

- **Sistema de hooks** ([hooks/hooks.json](../../hooks/hooks.json) + [hooks/session-start.mjs](../../hooks/session-start.mjs)) — hoje só `SessionStart`. Adicionamos um **`Stop` hook** (mesma stack Node `.mjs`, falha-silenciosa como o atual).
- **Padrão de teste de hook `.mjs` a partir do pytest** já existe (`cli/tests/integration/test_session_start_hook.py`). → reusamos o molde para testar o Stop hook.
- **Fragment CLAUDE.md/AGENTS.md** gerado em [cli/plugadvpl/cli.py](../../cli/plugadvpl/cli.py) (constante `_CLAUDE_FRAGMENT_BODY`) — adicionamos a instrução de **tagear símbolos afirmados**.
- **`verify-claims` (Fase 1)** = o verificador chamado pelo hook.
- **Skills** ([skills/](../../skills/), catálogo em [cli/plugadvpl/_skill_catalog.py](../../cli/plugadvpl/_skill_catalog.py)) — uma skill nova (ou nota na `plugadvpl-index-usage`) documenta o procedimento.

## 3. A melhoria proposta — três peças, por papel

Cada peça difere em **quem decide** (Anthropic [hooks](https://code.claude.com/docs/en/hooks) vs [skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)):

### (a) Fragment (always-on, shaping) — torna a extração grátis
Instrução no fragment: *quando a resposta afirmar símbolos ADVPL (funções, tabelas, campos SX3, `MV_*`), liste-os num bloco legível por máquina* — assim a extração é trivial e não custa re-leitura de fonte:

```
<plugadvpl-claims>
{"claims":[{"id":"c1","kind":"function","symbol":"FWModelEvent"},
           {"id":"c2","kind":"field","symbol":"ZX1_STATUS"}]}
</plugadvpl-claims>
```

### (b) Stop hook (harness-enforced, garantido) — o executor
No evento `Stop`, o hook: extrai o bloco da última mensagem do assistente → roda `plugadvpl verify-claims --stdin` → se houver `not_found` que a política da Fase 1 qualifica como acionável (ex.: símbolo customer ausente num corpus completo), retorna:

```json
{"decision":"block","reason":"Símbolos não encontrados no índice: ZX1_STATUSX. Corrija o nome ou marque como não-verificado. (verify-claims: not_found/high)"}
```

`decision:block` **impede o agente de parar** e injeta `reason` como re-prompt — listando **só os símbolos que falharam**. É o único mecanismo que *garante* "verifique antes de finalizar" ([hooks](https://code.claude.com/docs/en/hooks)). Hooks são cross-agent só no Claude Code; nos demais (Cursor/Copilot/Codex/Gemini) a peça (a)+(c) age como versão **advisory**.

### (c) Skill (model-invoked) — a doc do procedimento
Skill leve (≈100 tokens de metadata, corpo sob demanda) com o contrato e o quê/quando verificar — invocada em respostas complexas.

## 4. Política de gating (o que segura o custo)

- **Trigger só com claim verificável.** Se o rascunho não tem bloco `<plugadvpl-claims>` (resposta conceitual, sem símbolo), o hook **não dispara** — pula verificação inteira. Evita *overthinking* em pergunta fácil ([overthinking, 2604.10739](https://arxiv.org/html/2604.10739v1)).
- **≤2 rounds, para no primeiro pass.** Guard contra loop infinito via `stop_hook_active` ([hooks](https://code.claude.com/docs/en/hooks)). Round-2 falhou? **Expõe os símbolos não-verificados ao usuário** em vez de continuar o laço.
- **Nunca gate na confiança do modelo** — a autoconfiança reportada é "severamente superestimada (95–100% mesmo quando a acurácia real é bem menor)" ([TACL](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00713/125495)). Gate na **presença de claim verificável**, não na certeza sentida.
- **Só corrige sob sinal do verificador.** Nunca deixar o modelo decidir sozinho que errou (anti self-critique).

## 5. Implementação com TDD (sub-fases)

### 3a — Extração do bloco de claims (pura)
- **Teste** (`tests/unit/test_claims_extract.py`): extrai `claims[]` de um texto com `<plugadvpl-claims>`; retorna vazio quando ausente; ignora bloco malformado sem quebrar.
- **Impl**: parser do bloco (em `verify.py` ou helper do hook).

### 3b — Stop hook `.mjs`
- **Teste** (`tests/integration/test_stop_hook.py`, no molde do `test_session_start_hook.py`): dado um transcript-fake com símbolo inexistente → hook chama `verify-claims` e emite `{"decision":"block","reason":...}` citando só o símbolo que falhou; com tudo existente → emite allow (sem block); erro do CLI → falha-silenciosa (não bloqueia).
- **Impl**: `hooks/stop-verify.mjs` + registro em `hooks/hooks.json` (`Stop`). Falha-silenciosa como o session-start.

### 3c — Fragment + skill
- **Teste**: o fragment gerado contém a instrução do bloco de claims; testes de catálogo/links das skills seguem verdes ([test_skill_catalog](../../cli/tests/unit/)).
- **Impl**: trecho em `_CLAUDE_FRAGMENT_BODY` + skill nova/atualizada.

### 3d — Gating (rounds, trigger, loop-guard)
- **Testes**: sem bloco → hook não dispara; `stop_hook_active` → não re-bloqueia; após 2 rounds com falha → mensagem ao usuário em vez de novo block.
- **Impl**: a lógica de gating no hook.

### 3e — Validação ponta-a-ponta (via Fase 2, Camada B)
- Rodar o eval `--with-agent` com o fluxo **off vs on** e mostrar faithfulness subindo sem estourar tokens. É a prova de ganho.

## 6. Custo & performance

- **Resposta limpa (caso comum):** 1 chamada `verify-claims` (saída compacta) e **0** re-prompt. Extração é grátis (bloco já tagueado, sem reler fonte).
- **Resposta com erro:** +1 re-prompt carregando **só os nomes que falharam** (não fontes), ≤2 rounds.
- **Resposta conceitual (sem símbolo):** **0** overhead — hook nem dispara.
- **Risco de desperdício confirmatório** (a maioria dos self-checks não muda nada — [Self-Verification Dilemma, 2602.03485](https://arxiv.org/abs/2602.03485)) é **limitado** aqui porque o check externo é barato (1 lookup), não um raciocínio caro do modelo.

## 7. Pitfalls / decisões em aberto

1. **Loop infinito** se o `stop_hook_active`/cap de rounds falhar → testar explicitamente.
2. **Over-trigger** em resposta sem símbolo → trigger condicionado ao bloco de claims.
3. **Cross-agent**: o `Stop` hook só é garantido no Claude Code; documentar que em Cursor/Copilot/Codex/Gemini o fluxo é advisory (fragment+skill).
4. **Falso-positivo de cobertura** (Fase 1) vazando para re-prompt chato → o hook só bloqueia no que a Fase 1 marca como acionável (ex.: `not_found/high` em símbolo customer), nunca em `relation_absent/low`.
5. **Decisão em aberto**: o bloco de claims deve ser visível ao usuário final ou stripado da resposta renderizada? Sugestão: stripar na renderização (é metadado de verificação), manter no transcript pro hook.

## 8. Definition of Done

- [ ] `hooks/stop-verify.mjs` + registro `Stop` em `hooks/hooks.json`, falha-silenciosa.
- [ ] Extração de claims testada (pura) + Stop hook testado (molde session-start).
- [ ] Instrução do bloco `<plugadvpl-claims>` no fragment; skill do procedimento.
- [ ] Gating completo (trigger condicional, ≤2 rounds, loop-guard) testado.
- [ ] Camada B do eval mostra faithfulness↑ com o fluxo on, sem estouro de tokens.
- [ ] Doc de cross-agent (garantido no Claude Code, advisory nos demais).

## 9. Fontes

- [Chain-of-Verification (CoVe), ACL 2024 — 4 passos; verificação independente; tool-use como extensão recomendada](https://arxiv.org/abs/2309.11495)
- [LLM-Modulo — laço generate-test-critique com verificador sólido, rounds hard-capped](https://arxiv.org/abs/2402.01817)
- [2402.08115 — re-prompt com verificador sólido mantém quase todo o benefício; self-critique colapsa](https://arxiv.org/abs/2402.08115)
- [Huang et al., ICLR 2024 — sem feedback externo a autocorreção degrada](https://arxiv.org/abs/2310.01798) · [Kamoi et al., TACL 2024 — só funciona com feedback externo confiável](https://arxiv.org/abs/2406.01297)
- [Claude Code Hooks — Stop hook, decision:block+reason, stop_hook_active](https://code.claude.com/docs/en/hooks) · [Agent Skills overview (progressive disclosure)](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Self-Verification Dilemma (2602.03485) — rechecks confirmatórios; suprimi-los economiza ~20% tokens](https://arxiv.org/abs/2602.03485) · [Confiança auto-reportada superestimada (TACL)](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00713/125495)
