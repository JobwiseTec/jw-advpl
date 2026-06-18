# FairCom DB no Windows — fallback c-tree (opcional)

> ⚠️ **Você provavelmente NÃO precisa disto.** Para ler/exportar `.dtc` do
> Protheus (fixed-length), o dtcat funciona em Python puro, sem FairCom — basta
> `py -m pip install` e usar. Veja o [README](../README.md).
>
> Este guia só é necessário para o **fallback c-tree opcional**, usado em
> arquivos `.dtc` que não são fixed-length do Protheus (variáveis/indexados).

Guia passo a passo para instalar e configurar o **FairCom DB** no Windows.

> O dtcat usa o **driver Python nativo** que acompanha o FairCom DB. **Não é
> necessário configurar DSN ODBC.**

## 1. Python e uv

Instale o Python 3.11+ a partir de https://python.org/downloads (marque "Add to PATH" durante a instalação).

Instale o uv:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## 2. FairCom DB Developer Edition

O dtcat **não empacota** os binários da FairCom. Baixe o Developer Edition diretamente:

- **Formulário de cadastro:** https://www.faircom.com/download-ctreeace
- **Todos os downloads da FairCom:** https://www.faircom.com/products/downloads

Preencha o formulário (nome, email, empresa, país) → receba um email → baixe o build **Windows x64** (`.msi` ou `.zip`).

Ou use o instalador assistido:

```powershell
.\scripts\install-faircom.ps1
```

### Instalação manual

1. Execute o `.msi`, aceite os padrões (caminho típico: `C:\FairCom\V<versão>`)
2. Defina as variáveis de ambiente:
   - **Configurações → Sistema → Sobre → Configurações avançadas do sistema → Variáveis de Ambiente**
   - Nova variável de usuário: `FAIRCOM_HOME` = `C:\FairCom\V13.0.0` (ajuste para a sua versão)
   - Adicione `%FAIRCOM_HOME%\server` ao `PATH` (para a `ctsqlapi.dll`)

### Estrutura relevante da instalação

| Caminho | O que é |
|---|---|
| `%FAIRCOM_HOME%\server\faircom.exe` | binário do servidor SQL |
| `%FAIRCOM_HOME%\server\ctsqlapi.dll` | lib nativa do client SQL |
| `%FAIRCOM_HOME%\drivers\python.sql\pyctree.py` | driver Python nativo (DB-API 2.0) |
| `%FAIRCOM_HOME%\tools\ctsqlimp.exe` | utilidade que registra arquivos ISAM como tabela SQL |
| `%FAIRCOM_HOME%\data\ctreeSQL.dbs\` | diretório de trabalho SQL do servidor |

## 3. Instale o plugadvpl

```powershell
uv tool install plugadvpl
```

## 4. Valide

```powershell
plugadvpl dtc doctor
```

Todas as verificações devem reportar **OK**.

## 5. Uso típico

```powershell
# 1. Inicie o servidor FairCom local
plugadvpl dtc server start
plugadvpl dtc server status

# 2. Inspecione um .dtc
plugadvpl dtc info $env:USERPROFILE\Downloads\clientes.dtc

# 3. Exporte
plugadvpl dtc export $env:USERPROFILE\Downloads\clientes.dtc -f xlsx -o clientes.xlsx

# 4. Pare o servidor
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
| `FairCom DB não encontrado` | `FAIRCOM_HOME` não definido | defina a variável de usuário `FAIRCOM_HOME` |
| `ctsqlapi.dll não encontrada` | `server\` fora do PATH | adicione `%FAIRCOM_HOME%\server` ao PATH |
| `ctsqlimp falhou ao registrar` | servidor parado ou arquivo sem IFIL/DODA | `plugadvpl dtc server start`; confirme a origem do `.dtc` |
| `Access denied` ao iniciar o servidor | permissão no diretório de dados | rode o PowerShell como Administrador |
