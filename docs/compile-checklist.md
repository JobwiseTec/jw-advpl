# Compile ADVPL — o que você precisa em mãos

Antes de pedir "compila esse fonte" ao agente (ou rodar `plugadvpl compile` direto), reúna as infos abaixo. O agente vai perguntar — ter os dados prontos economiza ida-e-volta.

> 💡 Não precisa decorar nada. Rode `plugadvpl --format json compile --doctor` e o sistema descobre sozinho o que tem e o que falta. Este guia é só pra você entender **por que** cada coisa importa.

---

## Primeiro: qual modo você quer?

Existem **2 modos** de compilação:

| Modo | O que faz | Quando usar |
|---|---|---|
| **`appre`** | Pré-processamento local (sem AppServer). Pega: sintaxe básica, `#include` faltando, macros inválidas. **NÃO pega** erros semânticos (`If` sem `EndIf`, tipo errado) | Validação rápida (~60ms), CI leve, dev sem AppServer |
| **`cli`** | Compilação completa via AppServer TCP. Pega tudo. Gera RPO. | CI rigoroso, gerar binário final, validar semântica |

**Recomendação inicial**: comece com **`appre`** (menos coisas pra configurar). Quando precisar de validação completa, migre pra `cli`.

---

## Checklist `appre` — 2 itens (mais simples)

### ☐ 1. Binário `advpls`

**O que é**: o compilador da TOTVS. Programa executável `advpls.exe` (Windows) ou `advpls` (Linux/macOS).

**Como saber se já tem**:
```powershell
# Windows
Get-ChildItem "$env:USERPROFILE\.vscode\extensions\totvs.tds-vscode-*\node_modules\@totvs\tds-ls\bin\windows\advpls.exe" -ErrorAction SilentlyContinue
```
```bash
# Linux/macOS
ls ~/.vscode/extensions/totvs.tds-vscode-*/node_modules/@totvs/tds-ls/bin/*/advpls 2>/dev/null
```
Se aparecer um path → tem. Se sair vazio → não tem.

**Se não tem** — rode:

```bash
plugadvpl compile --install-advpls
```

Comando interativo que pergunta:
- **(1) Copiar de um path local** — se você já tem advpls em alguma pasta (de instalação antiga, máquina virtual, etc.), informe o path e ele copia pra `~/.plugadvpl/advpls/`
- **(2) Baixar do Marketplace** — sem precisar do VSCode instalado, baixa `.vsix` público da Microsoft (~118MB), extrai só o que precisa (~40MB de binário + companions), descarta o resto

**O comando sempre mostra plano + pede confirmação antes de qualquer operação destrutiva ou pesada.** Não baixa surpresa.

Depois de instalar, `--doctor` detecta automaticamente — não precisa configurar nada.

---

### ☐ 2. Pasta de includes Protheus

**O que é**: ~1.100 arquivos `.ch` (headers C-like com macros: `PRTOPDEF.CH`, `protheus.ch`, `topconn.ch`, `totvs.ch`, etc.). Sem isso, `appre` falha imediatamente com `Error C2090 File not found PRTOPDEF.CH`.

**Como saber se já tem**:
- Procure uma pasta chamada `Include/` na instalação Protheus:
  ```powershell
  # Windows — tente esses paths
  Test-Path "D:\TOTVS\protheus\Include"
  Test-Path "C:\TOTVS\protheus\Include"
  Test-Path "D:\PrjProtheus\protheus\Include"
  Test-Path "C:\Program Files\TOTVS\Microsiga\Protheus\Include"
  ```
- A pasta certa **tem** `PRTOPDEF.CH` (case-insensitive em Windows). Se tiver, é ela.

**Se não tem**:
- Esses includes **vêm com o AppServer/SDK Protheus** instalado pela TOTVS. Não são distribuídos publicamente (licença).
- Sem includes locais, **`appre` não funciona**. Suas opções:
  - Copiar a pasta `Include/` de uma máquina com Protheus instalado (zip + transferir)
  - Usar `--mode cli` em vez de `appre` (compila no AppServer remoto, que já tem os includes lá)

**O agente vai perguntar**: "Confirma usar `D:\PrjProtheus\protheus\Include`?" (ou similar — ele detecta sozinho se tiver instalação típica).

---

## Checklist `cli` — 5 itens (compilação completa)

Tudo do `appre` (binário + includes) **mais**:

### ☐ 3. AppServer rodando

**O que é**: o servidor Protheus rodando, escutando TCP na porta que você vai indicar. Pode ser:
- **Local**: `appserver.exe` na sua máquina (ex: `D:\TOTVS\protheus\bin\Appserver\appserver.exe`)
- **Remoto**: AppServer em VPS/servidor da empresa (cuidado: porta 1234 sem TLS — use SSH tunnel)

**Como saber se está rodando**:
```powershell
# Windows
Test-NetConnection -ComputerName localhost -Port 1234
```
```bash
# Linux/macOS
nc -z localhost 1234 && echo "rodando" || echo "não rodando"
```
Se responde → OK. Se não → suba o AppServer.

**Se for remoto**, recomendamos SSH tunnel:
```bash
ssh -L 1234:localhost:1234 user@meu-servidor-protheus.com -N
# deixa rodando em outro terminal
```
Isso evita expor credenciais em TCP cru pela internet.

**Info que você precisa anotar**:
- `host` (ex: `127.0.0.1` se local ou via tunnel)
- `port` (default `1234`)

---

### ⚡ Atalho — cadastre seus servers UMA vez (`~/.plugadvpl/servers.json`)

Se você compila pra **vários servers** (dev local, hml, prod, cliente A, cliente B), não precisa repetir `host`/`port`/`build`/`environment` em todo `runtime.toml`. Cadastra **uma vez** e usa em qualquer projeto:

```bash
# Tem TDS-VSCode? Importa direto:
plugadvpl compile --import-tds-servers
# Detecta ~/.totvsls/servers.json (do TDS-VSCode), pergunta confirmação, importa

# OU cadastra manual:
plugadvpl compile --add-server
# Interativo: pergunta nome, host, port, build, environments, default

# Lista o que tem cadastrado:
plugadvpl compile --list-servers

# Compila usando server cadastrado (sem precisar de runtime.toml):
plugadvpl compile --use-server dev-local --mode cli SEU_FONTE.PRW

# Override de environment pontual (servers podem ter vários: P2510, TEST, HML):
plugadvpl compile --use-server dev-local --use-environment TEST --mode cli SEU_FONTE.PRW
```

**Registry global** em `~/.plugadvpl/servers.json` (per-user, NUNCA grava senha — só nome das env vars). Permissão `0o600` em POSIX.

---

### ☐ 4. `build` e `environment` do AppServer

**O que é**: identificadores que o AppServer espera receber pra autenticar.

- **`build`**: versão do compilador esperada pelo AppServer (ex: `7.00.240223P`). Tem que bater **exatamente**.
- **`environment`**: nome do ambiente configurado no `appserver.ini` (ex: `P2510`, `PRODUCAO`, `HOMOLOG`).

**Como descobrir**:
1. **Console do AppServer** quando ele inicia mostra o `build` (linha tipo `Build 7.00.240223P`)
2. **`appserver.ini`** do servidor tem `[ENVIRONMENTS]` listando os ambientes
3. **Já compila pelo TDS-VSCode?** Abre `~/.totvsls/servers.json` (Linux/macOS) ou `%USERPROFILE%\.totvsls\servers.json` (Windows) — tem `build` e `environment` lá

**Anote**: `build` exato + nome do `environment` que vai usar.

---

### ☐ 5. Credenciais (usuário + senha Protheus)

**O que é**: usuário/senha que autentica no AppServer pra compilar. Tipicamente o mesmo que você usa pra entrar no Protheus.

**Como você fornece** (importante — segurança):
- **NUNCA** coloque a senha no `runtime.toml` (ele pode ser commitado por engano)
- Configure como **variável de ambiente**:
  ```powershell
  $env:PROTHEUS_USER = "admin"
  $env:PROTHEUS_PASS = "sua-senha-aqui"
  ```
  ```bash
  export PROTHEUS_USER=admin
  export PROTHEUS_PASS='sua-senha-aqui'
  ```
- Em CI use **secrets** (GitHub Actions → repo Settings → Secrets, GitLab CI variables, etc.)

**O `runtime.toml` referencia o nome da variável, não o valor**:
```toml
[auth]
user_env = "PROTHEUS_USER"      # nome
password_env = "PROTHEUS_PASS"  # nome
```

**O agente vai pedir**: "Setar `$PROTHEUS_PASS` — senha (não vou logar)". Você seta no terminal antes de chamar o agente novamente.

---

## Tabela resumo — info pra coletar antes

Preencha estes 5 dados antes de chamar o agente:

| # | Dado | Exemplo | Onde achar |
|---|---|---|---|
| 1 | Path do `advpls` | `D:\IA\Tools\tds-vscode\extracted\extension\node_modules\@totvs\tds-ls\bin\windows\advpls.exe` | Extensão TDS-VSCode (Marketplace) |
| 2 | Path da pasta Include | `D:\PrjProtheus\protheus\Include` | Instalação Protheus local |
| 3 | Host + porta AppServer | `127.0.0.1:1234` (local ou via tunnel) | `appserver.ini` ou setup do servidor |
| 4 | Build + environment | `7.00.240223P` + `P2510` | Console AppServer ou `~/.totvsls/servers.json` |
| 5 | Usuário + senha Protheus | `admin` / `senha123` (em env var!) | Mesmo do TDS-VSCode |

> 🤖 **Se você não souber alguma**: roda `plugadvpl --format json compile --doctor` e o sistema diz exatamente o que falta com sugestões prontas.

---

## "Não tenho nada disso, vou começar do zero"

Mínimo viável pra **só rodar `appre`** (sem AppServer):

1. Instala extensão TDS-VSCode no VSCode (Marketplace, busca "TOTVS") → tem o binário `advpls`
2. Pede pra alguém da empresa zipar a pasta `Include/` do Protheus + transfere pra você
3. Roda: `plugadvpl compile --mode appre --includes <pasta-Include> SEU_FONTE.PRW`

**Tempo estimado**: 10 min se já tem VSCode.

Pra **`cli`**: também precisa de acesso a um AppServer (próprio ou de um servidor da empresa via SSH tunnel) + credenciais.

---

## "Tenho TDS-VSCode funcionando, replique a config"

Sorte — você já tem **tudo**. O `plugadvpl --doctor` provavelmente vai detectar 90% sozinho. Só responde quando ele perguntar (`runtime.toml` pra modo `cli`).

---

## Próximos passos

- **Quer setup detalhado por OS**: [`docs/setup-compile.md`](setup-compile.md)
- **Quer entender o workflow do agente**: [`skills/compile/SKILL.md`](../skills/compile/SKILL.md)
- **Quer só rodar e ver**: `plugadvpl --format json compile --doctor` (ele te guia)
