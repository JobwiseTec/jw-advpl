# dtc — referência do formato `.dtc`

Referência técnica do leitor de `.dtc` (c-tree ISAM) embarcado no plugadvpl
(`plugadvpl dtc *`). Engine vendorizado de [tbarbito/dtcat](https://github.com/tbarbito/dtcat) (MIT).

## O que é um `.dtc`

Arquivo de dados do **c-tree** (ISAM proprietário da FairCom, usado pelo
DBAccess do Protheus). O **APSDU** (Protheus Data Utility) exporta tabelas pra
`.dtc` autocontido — o formato que esta skill lê.

Dois caminhos de leitura:

1. **Parser DODA nativo (principal)** — para `.dtc` Protheus de **layout fixo**
   (fixed-length). Lê o bloco DODA (descrição de layout) + registros direto dos
   bytes, em Python puro. Detecta a assinatura Protheus (registro fixo + flag de
   delete no offset 0). **Não precisa de FairCom.**
2. **Caminho c-tree (fallback)** — para arquivos de layout variável ou que
   precisem do índice. Registra o `.dtc` como tabela SQL via `ctsqlimp` e
   consulta pelo driver nativo. **Requer FairCom DB** (`FAIRCOM_HOME`).

`plugadvpl dtc doctor` valida o que está disponível.

## Encoding

Protheus grava texto em **cp1252 (Windows-1252)**. O exporter decodifica
cp1252 → UTF-8 ao gerar CSV/JSON/XLSX (fallback `latin1` com `errors=replace`
se houver byte inválido) e faz `rstrip()` no padding de campos fixed-length.
CSV sai como `utf-8-sig` (BOM) pra abrir limpo no Excel. Ver skill
[`advpl-encoding`](../advpl-encoding/SKILL.md).

## Filtro de deletados

Registros marcados como excluídos no Protheus têm `D_E_L_E_T_ = '*'`. Por padrão
o leitor os omite (`WHERE D_E_L_E_T_ <> '*'` no caminho c-tree; equivalente no
parser nativo). Use `--keep-deleted` pra trazê-los.

## Comandos

| Comando | O que faz | Precisa de |
|---|---|---|
| `dtc doctor` | Valida FairCom/driver/ctsqlimp/servidor | — |
| `dtc info <arq>` | Schema + count + amostra | parser nativo |
| `dtc export <arq> -f csv\|json\|xlsx` | Extrai pra arquivo | core (pandas/openpyxl) |
| `dtc batch <pasta> -f ... -o <dir>` | Processa pasta inteira | core (pandas/openpyxl) |
| `dtc server start\|stop\|status` | Gerencia c-tree Server local | FairCom |

## Gotchas

- **`.dtc` vs `.dtcx`**: runtime do Protheus separa dados (`.dtc`) de índice
  (`.dtcx`). Escopo inicial é só o export **autocontido** do APSDU.
- **Versão c-tree**: `.dtc` muito antigo (c-tree V8/V9) pode dar mismatch com
  FairCom V13+ no caminho fallback. O parser nativo independe disso.
- **ARM/Mac M1+**: driver nativo FairCom pode não ter build ARM — use o parser
  nativo (info/export de fixed-length) ou Docker/Rosetta pro fallback.
- **pandas/openpyxl são core**: `export`/`batch` funcionam direto após instalar/
  atualizar o plugadvpl. O `info` nem carrega pandas (import lazy só no export).

## Setup FairCom

Só necessário pro caminho c-tree (layout variável). Guias por SO em
[docs/dtc-setup.md](../../docs/dtc-setup.md).
