---
description: Aplicação de patch .PTM no RPO via `plugadvpl apply-patch` (advpls patchApply) com backup, idempotência por hash e rollback. Use quando o usuário pede "aplica esse patch", "aplica esse .PTM/.zip", "instala o pacote de correção TOTVS", "aplica hotfix no RPO", ou pergunta sobre ordem/segurança de aplicação de patches. NÃO usar pra compilar fonte (use compile) nem pra Troca Quente do RPO (use tq).
---

# apply-patch — Aplicação de `.PTM` no RPO

`plugadvpl apply-patch` aplica patches TOTVS (`.PTM`) no RPO via `advpls cli action=patchApply`, endurecendo o workflow artesanal (ZIP → `.bat` → torcer). Spec: [docs/superpowers/specs/2026-06-16-u6-apply-patch-design.md]. Contrato: [docs/apply-patch-contract.md].

## Quando usar

- Aplicar um `.PTM` único (hotfix) ou um `.zip` de pacote de correção/emergencial TOTVS.
- Aplicar um diretório com vários `.PTM` em ordem.
- Consultar o que já foi aplicado num environment (`--list-applied`).

## O que o plugin resolve (vs script artesanal)

- **Idempotência por hash** — reaplicar o mesmo `.PTM` no mesmo env vira `skipped` (não reaplica).
- **Status real parseado do log** — o advpls retorna **exit 0 mesmo em aplicação parcial**; o plugin lê o log e distingue `applied` / `partial` / `failed`.
- **ZIP híbrido** — você passa o `.zip`; o plugin descompacta internamente e aplica `.PTM` a `.PTM` em ordem alfabética (mantém controle de ordem/hash/backup).
- **Backup do RPO** — best-effort via `--rpo-path` (quando o AppServer é local).
- **PROD safety** — `--confirm-prod` obrigatório em server marcado prod.

## Workflow recomendado

1. **Dry-run primeiro** — veja o plano sem aplicar:
   ```bash
   plugadvpl apply-patch ./pacote.zip --use-server qa --dry-run
   ```
   Mostra cada `.PTM` e se será `APLICAR` ou `SKIP (já aplicado)`.

2. **Aplique** (com backup se o AppServer for local):
   ```bash
   plugadvpl apply-patch ./pacote.zip --use-server qa \
     --rpo-path /caminho/apo/<env>/tttm120.rpo
   ```
   Saída: tabela `ptm_name | status | detail` + summary `{applied, partial, skipped, failed}`.

3. **Em PROD** — `--confirm-prod` é obrigatório e `--no-backup` é proibido:
   ```bash
   plugadvpl apply-patch ./hotfix.PTM --use-server prd --confirm-prod --rpo-path ...
   ```

4. **Audite** o que já entrou:
   ```bash
   plugadvpl apply-patch --use-server prd --list-applied
   ```

## Credenciais

`apply-patch` resolve user/senha na ordem **env vars → keyring**:
- Env: exporte `PROTHEUS_USER` / `PROTHEUS_PASSWORD`.
- Keyring: `plugadvpl compile --set-credentials <server>`.

## Interpretando o resultado

| status | Significado |
|---|---|
| `applied` | Patch aplicado por completo. Gravado em `patches_applied`. |
| `partial` | **Aplicou só recursos novos** (`applyOldProgram` OFF). O RPO já tinha versões mais novas de parte do patch. Use `--apply-old` se quiser forçar os antigos. Gravado. |
| `skipped` | Hash já em `patches_applied` nesse env — não reaplicado. |
| `failed` | Erro real do advpls (ex.: `File could not be copied`, build incompatível). **Não gravado** → re-run tenta de novo. Sequência aborta nesse ponto. Exit 4. |

## Pegadinhas (descobertas em smoke real)

- **`secure` é numérico** — o plugin emite `0`/`1` automaticamente. (`false`/`true` derruba o advpls com `[ERROR] stoi` — por isso não dá pra usar a palavra.)
- **`[ERROR] Unable to connect` é benigno** — é a negociação secure→plain; o parser ignora.
- **`localPatch=True`** — o `.PTM` é copiado pro staging do AppServer (no `RootPath`). Se o copy falhar (`File could not be copied`), o patch não aplica — verifique permissão/espaço no `protheus_data` do server.
- **Lock por env** — uma batch por vez por environment (`~/.plugadvpl/locks/<env>.lock`). Lock órfão? remova o arquivo.

## Quando NÃO usar

- Compilar fonte `.prw`/`.tlpp` → use `plugadvpl compile`.
- Trocar a pasta ativa do RPO (Troca Quente) → use `plugadvpl tq`.
- Distribuir/baixar patches TOTVS → fora de escopo (IP TOTVS).

## Códigos de saída

`0` ok · `2` erro de uso (prod sem `--confirm-prod`, input inválido) · `3` server unreachable/auth · `4` ≥1 patch falhou · `5` lock ocupado · `6` `allow_prod=false`.
