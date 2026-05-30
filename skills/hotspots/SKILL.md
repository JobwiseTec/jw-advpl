---
description: Top-N funções ADVPL/TLPP mais chamadas no projeto Protheus — refactor priority por fan-IN (Universo 4 Feature B, v0.6.0+)
disable-model-invocation: true
arguments: [filtros]
allowed-tools: [Bash]
---

# `/plugadvpl:hotspots`

**Killer feature do v0.6.0** (Universo 4 — Qualidade & Métricas). Resposta direta pra "**onde uma mudança impacta mais código?**" — ranking de funções por número de callers.

## Uso

```
/plugadvpl:hotspots [--n 20] [--no-natives|--with-natives]
                    [--tipo user_func|method|execauto|execblock]
```

## O que mostra

| Campo | Significado |
|-------|-------------|
| `destino` | Nome da função (uppercase, sem `U_`) |
| `n_calls` | Total de callsites (chamadas) |
| `n_arquivos` | Em quantos arquivos diferentes ela é chamada |
| `n_callsites` | Callsites únicos (`arquivo::funcao` distintos) |

Ordenado por `n_calls DESC` — mais chamada primeiro.

## Filtro de nativas TOTVS (default ON)

Sem filtro, top-20 vira `RecLock`/`ConOut`/`DbSelectArea`/`xFilial` — sem
valor pra refactor priority. `--no-natives` (default) exclui o catálogo
embarcado `funcoes_nativas` (~7k rows).

Use `--with-natives` se quiser ver TODAS as chamadas (útil pra auditoria
de uso de funções restritas).

## Exemplos

```bash
# Top-20 funções customizadas mais chamadas (refactor priority)
/plugadvpl:hotspots

# Top-50 incluindo nativas (auditoria de uso de DB primitives)
/plugadvpl:hotspots --n 50 --with-natives

# Só métodos de classe (top abstrações de OO)
/plugadvpl:hotspots --tipo method

# Só rotinas TOTVS chamadas via MsExecAuto (cross-ref Universo 3)
/plugadvpl:hotspots --tipo execauto
```

## Cross-ref

- **`/plugadvpl:callers <funcao>`** — callsites detalhados da função top
- **`/plugadvpl:metrics --sort calls`** — fan-OUT (oposto: quantas chamadas a função FAZ)
- **`/plugadvpl:execauto --routine <X>`** — quando o destino é rotina TOTVS
