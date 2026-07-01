# FairCom DB no macOS — fallback c-tree (opcional)

> ⚠️ **Você provavelmente NÃO precisa disto.** Para ler/exportar `.dtc` do
> Protheus (fixed-length), o dtcat funciona em Python puro, sem FairCom — basta
> `pip install` e usar. Veja o [README](../README.md).
>
> Este guia só é necessário para o **fallback c-tree opcional**, usado em
> arquivos `.dtc` que não são fixed-length do Protheus (variáveis/indexados).

Guia passo a passo para instalar e configurar o **FairCom DB** no macOS.

> O dtcat usa o **driver Python nativo** que acompanha o FairCom DB. **Não é
> necessário unixODBC nem configurar DSN.**

> **Nota sobre Apple Silicon (M1/M2/M3+):** A FairCom (ainda) não fornece um build nativo arm64. O build Intel x86_64 roda via **Rosetta 2** com desempenho aceitável para cargas de inspeção/exportação.

## 1. Pré-requisitos

```bash
# Homebrew (se ainda não estiver instalado)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# ferramentas Python
brew install uv
```

No Apple Silicon, habilite o Rosetta 2 uma vez (o sistema pede automaticamente na primeira vez que um binário Intel roda, ou execute):

```bash
softwareupdate --install-rosetta --agree-to-license
```

## 2. FairCom DB Developer Edition

O dtcat **não empacota** os binários da FairCom. Baixe o Developer Edition diretamente:

- **Formulário de cadastro:** https://www.faircom.com/download-ctreeace
- **Todos os downloads da FairCom:** https://www.faircom.com/products/downloads

Preencha o formulário → receba um email → baixe o build **macOS x86_64** (`.dmg`).

Ou use o instalador assistido:

```bash
./scripts/install-faircom.sh
```

### Instalação manual

1. Abra o `.dmg`, arraste o FairCom para `~/faircom` (ou `/Applications/FairCom`)
2. Configure o ambiente (aponta para o diretório do servidor, que contém a lib nativa):

```bash
cat >> ~/.zshrc << 'EOF'
export FAIRCOM_HOME="$HOME/faircom"
export DYLD_LIBRARY_PATH="$FAIRCOM_HOME/server:$DYLD_LIBRARY_PATH"
EOF
source ~/.zshrc
```

### Estrutura relevante da instalação

| Caminho | O que é |
|---|---|
| `~/faircom/server/faircom` | binário do servidor SQL |
| `~/faircom/server/libctsqlapi.dylib` | lib nativa do client SQL |
| `~/faircom/drivers/python.sql/pyctree.py` | driver Python nativo (DB-API 2.0) |
| `~/faircom/tools/ctsqlimp` | utilidade que registra arquivos ISAM como tabela SQL |
| `~/faircom/data/ctreeSQL.dbs/` | diretório de trabalho SQL do servidor |

## 3. Instale o plugadvpl

```bash
uv tool install plugadvpl
```

## 4. Valide

```bash
plugadvpl dtc doctor
```

## 5. Uso típico

```bash
plugadvpl dtc server start
plugadvpl dtc info ~/Downloads/clientes.dtc
plugadvpl dtc export ~/Downloads/clientes.dtc -f csv -o ~/out/clientes.csv
plugadvpl dtc server stop
```

O `plugadvpl dtc` registra cada `.dtc` no dicionário SQL (via `ctsqlimp`), lê e depois
desvincula automaticamente — os dados originais não são alterados.

## Conexão (avançado)

| Variável | Padrão |
|---|---|
| `DTCAT_HOST` | `127.0.0.1` |
| `DTCAT_PORT` | `6597` |
| `DTCAT_DATABASE` | `ctreeSQL` |
| `DTCAT_USER` | `ADMIN` |
| `DTCAT_PASSWORD` | `ADMIN` |
| `DTCAT_SERVER` | `FAIRCOMS` |

## Solução de problemas

| Erro | Causa | Correção |
|---|---|---|
| `dyld: Library not loaded: libctsqlapi.dylib` | lib fora do path | `export DYLD_LIBRARY_PATH=$FAIRCOM_HOME/server:$DYLD_LIBRARY_PATH` |
| `bad CPU type in executable` (Apple Silicon) | Rosetta não instalado | `softwareupdate --install-rosetta --agree-to-license` |
| `ctsqlimp falhou ao registrar` | servidor parado ou arquivo sem IFIL/DODA | `plugadvpl dtc server start`; confirme a origem do `.dtc` |
