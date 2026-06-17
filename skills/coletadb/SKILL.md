---
description: Extrai o COLETADB.tlpp (componente servidor que dumpa o dicionario SX do Protheus) pra raiz do projeto, na versao casada com o plugin — pra compilar e usar com ingest-protheus
disable-model-invocation: true
arguments: [opcoes]
allowed-tools: [Bash]
---

# `/plugadvpl:coletadb`

Extrai o `coletadb.tlpp` **empacotado no plugin** (componente servidor) pra raiz
do projeto. A versao extraida **casa com a versao do plugadvpl instalado** — fim
do "peguei uma copia antiga em algum lugar".

O `coletadb.tlpp` roda no AppServer Protheus e dumpa o dicionario SX (SX1..SXG +
MPMENU/Schedules/Jobs) em CSVs, consumidos pelo `/plugadvpl:ingest-protheus` via
REST. Tambem tem UI (`U_COLETADB`) com opcao de salvar o bundle na estacao do
cliente (v1.1.0+).

## Uso

```
/plugadvpl:coletadb [--dest <pasta>] [--force]
```

- Sem argumento → extrai pra raiz do projeto.
- `--dest <pasta>` → extrai pra outra pasta da maquina.
- `--force` → sobrescreve se ja existir uma versao diferente.

## Execucao

```bash
uvx plugadvpl@0.43.0 coletadb $ARGUMENTS
```

## Depois de extrair

1. Copie o `coletadb.tlpp` pro RPO custom do AppServer.
2. Compile (TDS-VSCode ou `plugadvpl compile coletadb.tlpp`).
3. Habilite `[HTTPV11]` + `[HTTPURI]` no `appserver.ini`.
4. `plugadvpl ingest-protheus --endpoint <url> --user U --password P`.

## Relacionado

- Skill `ingest-protheus` — consome o dump SX via REST do COLETADB.
- Skill `ingest-sx` — caminho alternativo via CSV exportado do Configurador.
