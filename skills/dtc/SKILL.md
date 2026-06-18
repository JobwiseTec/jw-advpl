---
description: Lê/exporta arquivos .dtc (c-tree ISAM exportados pelo APSDU/Protheus) sem AppServer — schema, count, amostra e export CSV/JSON/XLSX. Use quando o usuário trouxer um .dtc pra inspecionar ou extrair.
disable-model-invocation: true
arguments: [arquivo_ou_pasta]
allowed-tools: [Bash]
---

# `/plugadvpl:dtc`

Leitor/exporter **standalone** de arquivos `.dtc` (c-tree ISAM) — tipicamente
exports do **APSDU** do Protheus (backups de SX*, SC5, SE1, etc.). Inspeciona
schema, conta/amostra registros e exporta pra CSV / JSON / XLSX **sem subir
AppServer, DBAccess ou RPO**.

Para `.dtc` Protheus de layout fixo (fixed-length), o leitor usa o **parser DODA
nativo em Python puro** — não precisa de nada além do plugadvpl. Só arquivos de
layout variável caem no caminho c-tree (que exige FairCom DB Developer Edition).

## Quando usar

- O usuário recebeu um `.dtc` por e-mail/cloud e quer ver o que tem dentro
- Precisa extrair dados de um backup APSDU sem Protheus rodando (cliente
  air-gapped, ou ambiente local já migrado pra metadado relacional)
- Quer transformar `SX*.dtc` em CSV pra auditoria/análise externa

## Pré-requisitos

- **Inspeção (`info`) e export (`export`/`batch`)**: nada além do plugadvpl —
  parser DODA nativo + pandas/openpyxl já vêm como dependência core.
- **Caminho c-tree (fallback p/ layout variável)**: FairCom DB Developer Edition
  (free) com `FAIRCOM_HOME` setado. Valide com `plugadvpl dtc doctor`. Setup por
  SO em [docs/dtc-setup.md](../../docs/dtc-setup.md).

## Uso

```
/plugadvpl:dtc <arquivo.dtc | pasta>
```

## Execucao

```bash
# Schema + count + amostra (parser nativo, sem dependência externa)
uvx plugadvpl@0.43.2 dtc info $ARGUMENTS

# Export pra CSV/JSON/XLSX (pandas/openpyxl já são core)
uvx plugadvpl@0.43.2 dtc export $ARGUMENTS --format csv

# Valida pré-requisitos do caminho c-tree
uvx plugadvpl@0.43.2 dtc doctor
```

## Exemplos

- `/plugadvpl:dtc SX3010.dtc` — vê schema e amostra da SX3 exportada
- `plugadvpl dtc export SX3010.dtc -f csv` — gera `SX3010.csv` (cp1252 → utf-8)
- `plugadvpl dtc batch ~/inbox/ -f csv -o ./out` — processa a pasta inteira

## Saida

- `info`: tabela Rich com schema (campo/tipo/tamanho/null), total de registros e
  amostra. Encoding cp1252 decodificado corretamente.
- `export`: arquivo no formato pedido. Por padrão filtra registros deletados
  (`D_E_L_E_T_ = '*'`); use `--keep-deleted` pra incluí-los.

## Observacao

Escopo: `.dtc` autocontido exportado pelo APSDU. `.dtc` de runtime Protheus
(com `.dtcx` separado) está fora do escopo inicial. Detalhes do formato, encoding
e gotchas em [reference.md](reference.md).
