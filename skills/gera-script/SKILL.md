---
description: Gera um script .ps1/.sh determinístico de aplicação de patch (.PTM) + compilação de fontes Protheus, pré-preenchido a partir de um servidor do registry, para um operador humano rodar na base do cliente sem plugadvpl nem IA. Use quando o usuário pede "gera um script de patch e compilação", "script pra aplicar PTM e compilar", "script standalone pro cliente rodar", "deploy sem plugadvpl na ponta". NÃO use para aplicar patch agora (use apply-patch) nem para compilar agora (use compile).
disable-model-invocation: true
arguments: [use-server]
allowed-tools: [Bash, Read, Write]
---

# `/plugadvpl:gera-script`

Forja, na máquina do dev, um script **autossuficiente** (`.ps1` e/ou `.sh`) + um `patch_e_compilacao_config.json` **pré-preenchido**, para um **operador humano** rodar na base do cliente **sem plugadvpl nem IA**. Aplica patches `.PTM` (extrai ZIP → `patchApply` em ordem alfabética → `defragRPO`) e compila fontes (`.prw/.tlpp/.prx`). Determinístico (mesma entrada → mesmos bytes), sem LLM.

> **Por que gerar em vez de aplicar direto?** `apply-patch` e `compile` nativos exigem plugadvpl instalado e, em geral, um agente conduzindo. Em muitas bases de cliente não há nenhum dos dois — o operador precisa de um script pronto que ele mesmo executa.

## Como os dados entram

| Dado | Origem | No artefato |
|------|--------|-------------|
| host / port / build / environment | `--use-server <nome>` (`~/.plugadvpl/servers.json`) | embutido no config |
| paths da máquina-cliente (advpls, fontes, patches, includes, logs) | plugadvpl não conhece | **placeholder** no config (o script aborta se não preenchido) |
| senha | nunca no registry | env var (`--secret env`, default) ou no config (`--secret config`) — **nunca** embutida em texto puro |

## Uso

```
plugadvpl gera-script --use-server qa --shell both --out ./deploy
```

- `--shell ps1|sh|both` — qual(is) script(s) gerar (Windows / Linux / ambos).
- `--secret env|config` — `env` grava só o **nome** da env var (ex.: `PROTHEUS_PASS`); `config` põe um placeholder de senha no JSON (arquivo `0600`).
- `--tq` — inclui a **3ª fase (Troca Quente)**: promove o RPO de compilação para o ambiente destino.
- `--out <dir>` — diretório de saída (default: atual). `--force` sobrescreve.
- `--example` imprime um config JSON de exemplo; `--schema` imprime as chaves por origem (machine-readable, sempre em sync com o gerador).

## Fase Troca Quente (`--tq`)

Cria uma pasta datada nova no `apo` do destino, copia o RPO de compilação (`tttm120.rpo`/`custom.rpo`, configurável em `TQ_RPO_FILES`) para ela e **repointa o `SourcePath`** nos `appserver*.ini` do destino. Chaves: `TQ_DEST_APO` (apo do destino), `TQ_CMP_RPO` (RPO de compilação), `TQ_DEST_BIN` (bin do appserver destino). Pula sozinha se `TQ_DEST_APO` ficar vazio/placeholder.

- **Restart (obrigatório p/ appserver REST):** preencha `TQ_RESTART_CMD` — após o swap o script reinicia o appserver destino (REST não recarrega o RPO sem restart). `TQ_HEALTHCHECK_URL` (opcional) confirma que voltou.
- ⚠️ É a fase **destrutiva no destino** (tipo produção) — por isso é opt-in via `--tq`.

## Hardening assado de fábrica

`secure` numérico (0/1 — `true`/`false` derruba o advpls com `[ERROR] stoi`), checagem de exit-code por etapa, `.PTM` em ordem alfabética, `defragRPO` ao final.

> **Trade-off:** por ser standalone (roda sem plugadvpl na ponta), o script **não** tem a idempotência-por-hash nem o parse-de-log do `apply-patch` nativo. Para aplicar patch com essas garantias na sua máquina, use `/plugadvpl:apply-patch`.

## O operador, na base do cliente

1. Edita o `patch_e_compilacao_config.json` (preenche os paths locais).
2. (modo env) define a senha: `set PROTHEUS_PASS=...` / `export PROTHEUS_PASS=...`.
3. Roda `patch_e_compilacao.ps1` (Windows) ou `patch_e_compilacao.sh` (Linux, requer `jq`).
