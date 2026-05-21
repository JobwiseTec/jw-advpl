---
description: Indexa Dicionário SX via REST API do COLETADB (Universo 5) — workflow ao vivo, sem CSV manual
disable-model-invocation: true
arguments: [opcoes]
allowed-tools: [Bash]
---

# `/plugadvpl:ingest-protheus`

Indexa o Dicionário SX (SX1..SXG + SIX) chamando o endpoint REST do `COLETADB.tlpp` instalado no AppServer Protheus do cliente. Substitui o workflow manual do `ingest-sx` (CSV exportado do Configurador) por **dump ao vivo via HTTP**.

Convive com `/plugadvpl:ingest-sx` — quem não tem `COLETADB` instalado continua usando CSV.

Pré-requisito: rodar `/plugadvpl:init` antes (cria `.plugadvpl/index.db`).

## Uso

```
/plugadvpl:ingest-protheus --endpoint <url> [--token <T>] [--tables SX2,SX3,...]
/plugadvpl:ingest-protheus --endpoint <url> --check
/plugadvpl:ingest-protheus --endpoint <url> --dry-run
```

## Argumentos

- `--endpoint URL` — base URL do COLETADB (ex: `http://protheus:8181/rest/coletadb`). **Obrigatório**.
- `--token TOKEN` — bearer token. Fallback pra env var `COLETADB_TOKEN`.
- `--user USER` + `--password PASS` — alternativa pra HTTP Basic auth.
- `--tables CSV` — filtra tabelas a baixar (ex: `SX2,SX3,SX7`). Default: todas.
- `--check` — só health-check, não toca DB.
- `--dry-run` — health + lista tabelas, não baixa dump.
- `--timeout N` — timeout por request HTTP (default 30s).

## Execucao

```bash
uvx plugadvpl@0.9.5 ingest-protheus $ARGUMENTS
```

## Exemplos

- `/plugadvpl:ingest-protheus --endpoint http://protheus:8181/rest/coletadb --token $TOKEN` — ingest completo
- `/plugadvpl:ingest-protheus --endpoint <url> --tables SX3,SX7 --token $TOKEN` — só campos e gatilhos
- `/plugadvpl:ingest-protheus --endpoint <url> --check --token $TOKEN` — só valida conectividade
- `/plugadvpl:ingest-protheus --endpoint <url> --dry-run --token $TOKEN` — preview sem baixar dump

## Pré-requisitos no AppServer

O `COLETADB.tlpp` precisa estar **instalado e ativo** no AppServer do cliente. Caso `/check` retorne **404**, peça ao TI do cliente pra compilar a reference impl em `docs/reference-impl/coletadb.tlpp` (em release futura, flag `--install-server-component` fará isso automático via `plugadvpl compile`).

## Saida

Counts por tabela após o ingest (linhas inseridas via REST), tempo total, versão do COLETADB e build do Protheus. Re-rodar é idempotente (`INSERT OR REPLACE`).

## Paridade com ingest-sx

O DB resultante deste comando é **bit-identico** ao produzido por `/plugadvpl:ingest-sx` rodado contra o CSV equivalente. Comandos downstream (`/plugadvpl:impacto`, `/plugadvpl:gatilho`, `/plugadvpl:sx-status`) funcionam idêntico independente da fonte.

## Diferenças de ingest-sx

| | `ingest-sx` (CSV) | `ingest-protheus` (REST) |
|---|---|---|
| Pré-requisito | CSV exportado manualmente do Configurador | `COLETADB.tlpp` instalado no AppServer |
| Freshness | Foto do momento da exportação | Estado atual do banco |
| Trabalho do dev | Pedir export → receber zip → descompactar → ingest | 1 comando |
| Tabelas custom (Z*/X*) | Não — só padrão SX | Sim (Fase 4b, futuro) |
| Drift detection | Não | Sim (Fase 4a, futuro) |
| Conectividade necessária | Não (offline) | Sim (HTTP ao AppServer) |

## Erros comuns

- **`--endpoint obrigatorio`** — passe `--endpoint <url>`
- **`Auth obrigatoria`** — passe `--token`, defina `COLETADB_TOKEN`, ou use `--user`/`--password`
- **`404 Not Found em <url>`** — COLETADB não instalado no AppServer (vide pré-requisitos)
- **`401 Unauthorized`** — token inválido ou expirado
- **`Conectividade falhou`** — AppServer fora do ar, VPN, ou firewall

## Roadmap (vide [issue #3](https://github.com/JoniPraia/plugadvpl/issues/3))

- ✅ **Fase 3** (v0.10.0) — comando básico, contract canonical
- 🔜 **Fase 4a** — `plugadvpl sx-drift` (compara DB local vs estado atual via REST)
- 🔜 **Fase 4b** — suporte a custom tables `Z*`/`X*`
- 🔜 **Fase 4c** — auto-install do COLETADB via `plugadvpl compile`
