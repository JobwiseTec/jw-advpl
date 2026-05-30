---
description: Métricas por função ADVPL/TLPP (complexidade ciclomática McCabe + LOC + nesting + fan-out + params) para fontes Protheus — Universo 4 Feature B, v0.6.0+
disable-model-invocation: true
arguments: [arquivo|filtros]
allowed-tools: [Bash]
---

# `/plugadvpl:metrics`

**Killer feature do v0.6.0** (Universo 4 — Qualidade & Métricas). Responde **"por onde começar num refactor?"** via ranking de funções por complexidade.

## Uso

```
/plugadvpl:metrics [arquivo]
                   [--min-cc N] [--min-loc N]
                   [--sort cc|loc|nesting|calls|params]
```

## Métricas extraídas (cacheadas em `fonte_metrics`)

| Campo | Significado |
|-------|-------------|
| `loc` | Linhas de código (`linha_fim - linha_inicio + 1`) |
| `cc` | Complexidade ciclomática **McCabe** (1 + paths de decisão: If/ElseIf/While/For/Case/Catch/IIf) |
| `nesting` | Profundidade máxima de blocos aninhados |
| `n_calls_out` | Fan-out: quantas funções essa função chama |
| `params_count` | Número de parâmetros da assinatura |
| `has_doc` | `sim` se função tem header Protheus.doc |

## Exemplos

```bash
# Top-10 funções mais complexas do projeto
/plugadvpl:metrics --sort cc

# Funções gigantes (> 300 linhas) — candidatas refactor
/plugadvpl:metrics --min-loc 300 --sort loc

# CC alta + sem documentação = piores casos
/plugadvpl:metrics --min-cc 15

# Métricas de UM fonte específico
/plugadvpl:metrics ABCCOM01.prw

# Fan-out alto = "função faz muita coisa"
/plugadvpl:metrics --sort calls
```

## Convenção McCabe (decisões que contam CC)

- ✅ `If` / `ElseIf` (cada um +1)
- ❌ `Else` (não adiciona path)
- ✅ `While` / `For` (cada loop +1)
- ✅ `Case` dentro de `Do Case` (cada cláusula +1; `Do Case` em si não conta — equivale ao base)
- ❌ `OtherWise` (não adiciona path)
- ✅ `Catch` (cada handler +1)
- ✅ `IIf()` ternário inline (+1 — caminho condicional)

Função sem ramificação tem **CC = 1** (base). Sem cap superior.

## Limitações conhecidas

- **Macro substitution** (`&cVar`) — mesmo limite dos outros universos. CC pode estar levemente alto/baixo se macro expande pra blocos extra.
- **CC reportada por função** (não por classe/módulo) — agregação fica via SQL no JSON output.
- **Re-ingest necessário** quando schema bumpa (v9→v10).

## Cross-ref

- **`/plugadvpl:hotspots`** — top-N funções mais chamadas (refactor priority complementar — fan-IN)
- **`/plugadvpl:cobertura-doc`** — % funções com Protheus.doc por módulo
- **`/plugadvpl:lint`** — bugs específicos (BP/SEC/PERF) por função
- **`/plugadvpl:arch <fonte>`** — visão consolidada de UM arquivo
