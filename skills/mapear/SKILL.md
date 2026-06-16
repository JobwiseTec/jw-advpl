---
description: Dossiê determinístico de uma rotina ADVPL (identidade + tabelas + grafo) + verificação contra o índice — SEM LLM
disable-model-invocation: true
arguments: [codigo]
allowed-tools: [Bash]
---

# `/plugadvpl:mapear`

**Mapa completo e determinístico de uma rotina, numa chamada só.** Reúne TUDO que o índice sabe (identidade, funções, tabelas lidas/gravadas, grafo de chamadas) e **verifica cada símbolo** contra o índice — separando "tabela fora do dicionário (cobertura)" de símbolo realmente ausente.

**100% determinístico, SEM LLM.** Serve de fonte-de-verdade pra alimentar qualquer agente (Claude/Codex/Copilot/Gemini) — em vez de o modelo orquestrar `find -> arch -> callers -> callees` (frágil), o código faz isso e devolve pronto e verificado.

O que vem no mapa:
- **Identidade:** tipo do fonte, linhas, namespace, capabilities, includes
- **Funções:** user functions, total, pontos de entrada
- **Tabelas:** lidas / gravadas / reclock / via ExecAuto
- **Integração:** quem chama a rotina e o que ela chama
- **Verificação:** quantos símbolos confirmados no índice; funções ausentes (grave) vs tabelas no código fora do SX2 (cobertura, não erro)

## Uso

```
/plugadvpl:mapear <codigo> [--detalhe]
```

`--detalhe` expande, por user function interna, o que cada uma chama.

## Execução

```bash
uvx plugadvpl@0.41.0 --format md mapear $codigo
```

> **Para agente IA:** passe `--format md` (ou `--format json` pra parsear). A flag `--format` vem **antes** do subcomando (é global no callback). O mapa confirma SÍMBOLOS (função/tabela), nunca o SENTIDO de negócio da rotina — afirmações de domínio precisam ser conferidas no fonte.

## Exemplos

- `/plugadvpl:mapear COLETADB` — tipo, tabelas e grafo de uma rotina
- `/plugadvpl:mapear U_MINHAFUNC --detalhe` — com o que cada função interna chama

## Próximos passos sugeridos

- `/plugadvpl:arch <arquivo>` — visão arquitetural do fonte
- `/plugadvpl:impacto <campo>` — impacto de mudança de campo SX3
- `/plugadvpl:verify-claims` — verificar símbolos de uma resposta contra o índice
