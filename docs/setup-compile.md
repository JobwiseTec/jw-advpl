# Setup `plugadvpl compile` — guia completo

Como deixar o subcomando `compile` funcional do zero, em qualquer máquina.

---

## 🤖 Uso pelo agente Claude

Se você é o agente IA recebendo "quero compilar X.PRW", o workflow é **simples**:

```bash
# 1. Sempre primeiro: pre-flight check
plugadvpl --format json compile --doctor

# 2. Se status="needs_setup", processe cada item em next_actions
#    (cada um diz exatamente o que perguntar ao usuário e o que fazer com a resposta)

# 3. Re-rode --doctor até status="ready"

# 4. Compile (flags ANTES do nome do arquivo!)
plugadvpl compile --mode appre --includes <pasta> X.PRW
```

Detalhes do workflow agente em [`skills/compile/SKILL.md`](../skills/compile/SKILL.md).
O resto deste doc é **referência humana** com explicação dos pré-requisitos.

---

## TL;DR (3 minutos)

| Modo | Precisa | Pra que serve |
|---|---|---|
| **`appre`** (default em auto) | `advpls` + includes Protheus | Validação rápida local (sintaxe + macros + includes) — não detecta erros semânticos |
| **`cli`** (full compile) | tudo acima + AppServer rodando + credenciais | Compilação completa, gera RPO. Pega tudo. |

Comando mais comum:

```bash
plugadvpl compile --mode appre --includes <pasta-includes-protheus> meufonte.prw
```

> ⚠️ **Sempre flags `--xxx` antes do nome do arquivo** (convenção UNIX).

---

## Pré-requisitos por modo

### Modo `appre` (local, sem AppServer)

Precisa de **2 coisas**:

#### 1. Binário `advpls`

Vem dentro da extensão oficial **TDS-VSCode** (gratuita, Marketplace público da Microsoft):

| OS | Path típico (`advpls` dentro da extensão) |
|---|---|
| Windows | `<ext>/node_modules/@totvs/tds-ls/bin/windows/advpls.exe` |
| Linux | `<ext>/node_modules/@totvs/tds-ls/bin/linux/advpls` |
| macOS | `<ext>/node_modules/@totvs/tds-ls/bin/mac/advpls` |

Onde `<ext>` depende de como você obteve a extensão:

**Opção A — Já tem VSCode + TDS-VSCode instalado:**
```
~/.vscode/extensions/totvs.tds-vscode-<versão>/
```
Localizar (PowerShell):
```powershell
Get-ChildItem "$env:USERPROFILE\.vscode\extensions\totvs.tds-vscode-*\node_modules\@totvs\tds-ls\bin\windows\advpls.exe"
```

**Opção B — Baixar só o binário (CI/sem VSCode):**
```powershell
# 1. Baixar .vsix (~118MB)
Invoke-WebRequest `
  -Uri "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/TOTVS/vsextensions/tds-vscode/latest/vspackage" `
  -OutFile tds-vscode.vsix

# 2. Extrair (.vsix é zip)
Expand-Archive tds-vscode.vsix -DestinationPath tds-vscode/

# 3. Caminho final
$advpls = "tds-vscode/extension/node_modules/@totvs/tds-ls/bin/windows/advpls.exe"
```

```bash
# Linux/macOS
curl -L -o tds-vscode.vsix \
  "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/TOTVS/vsextensions/tds-vscode/latest/vspackage"
unzip -q tds-vscode.vsix -d tds-vscode/
advpls=tds-vscode/extension/node_modules/@totvs/tds-ls/bin/linux/advpls
chmod +x $advpls
```

#### 2. Includes Protheus reais

A pasta `Include/` da instalação Protheus, com **~1.100 arquivos `.ch`** incluindo:

- `PRTOPDEF.CH` (obrigatório — sem ele `appre` falha com `C2090`)
- `protheus.ch`
- `topconn.ch`
- `totvs.ch`
- `restful.ch`
- ... 1.100+ outros

**Esses includes NÃO vêm com TDS-VSCode** — vêm com a instalação do AppServer/SDK Protheus (licenciado pela TOTVS). Caminhos comuns:

- `D:\TOTVS\protheus\Include\`
- `D:\PrjProtheus\protheus\Include\`
- `C:\Program Files\TOTVS\Microsiga\Protheus\Include\`

Se você não tem AppServer local, opções:
- Copie `Include/` de um Protheus instalado em outra máquina (zip + transfer)
- Use `--mode cli` apontando pra AppServer remoto (a compilação acontece lá)
- Sem includes, `appre` só funciona pra fontes **sem `#include`** (raro)

#### Como informar o `advpls` ao `plugadvpl`

3 caminhos, em ordem de precedência:

1. **Env var** (mais simples pra teste pontual):
   ```bash
   export PLUGADVPL_ADVPLS_BINARY=/caminho/advpls
   ```
2. **`runtime.toml`** (recomendado pra projeto persistente):
   ```bash
   plugadvpl compile --init-config    # cria .plugadvpl/runtime.toml
   # Edite [tds_ls].binary = "/caminho/advpls"
   ```
3. **PATH** (último recurso): se `advpls` está no `$PATH`/`%PATH%`, é auto-detectado.

### Modo `cli` (compilação completa via AppServer)

Tudo do modo `appre` **mais**:

#### 3. AppServer rodando

Local (`D:\TOTVS\protheus\bin\Appserver\appserver.exe`) ou remoto. Precisa estar com TCP exposto (default porta `1234`).

#### 4. `runtime.toml` configurado

```bash
plugadvpl compile --init-config
```

Edite `<root>/.plugadvpl/runtime.toml`:

```toml
[tds_ls]
binary = "D:/IA/Tools/tds-vscode/extracted/extension/node_modules/@totvs/tds-ls/bin/windows/advpls.exe"

[appserver]
host = "127.0.0.1"    # use 127.0.0.1 + SSH tunnel se AppServer é remoto
port = 1234
secure = false
build = "7.00.240223P"   # ver no console do AppServer
environment = "P2510"    # ambiente configurado no appserver.ini

[auth]
user_env = "PROTHEUS_USER"    # nome da env var, NUNCA o valor
password_env = "PROTHEUS_PASS"
aut_file = ""    # opcional — chave .aut da TOTVS

[compile]
recompile = true
includes = ["D:/PrjProtheus/protheus/Include"]
mode = "auto"
timeout_seconds = 120
include_warnings = true
```

#### 5. Credenciais via env var

```bash
# Bash / zsh
export PROTHEUS_USER=admin
export PROTHEUS_PASS='senha-real'

# PowerShell
$env:PROTHEUS_USER = "admin"
$env:PROTHEUS_PASS = "senha-real"
```

Em CI use secrets (GitHub Actions / GitLab CI variables). **Nunca** commite valor no `runtime.toml`.

#### 6. (Recomendado) SSH tunnel pra AppServer remoto

TDS-LS envia user/password sem TLS sobre TCP. Pra AppServer não-local, tunelar:

```bash
ssh -L 1234:localhost:1234 user@protheus-remoto.com -N
```

E no `runtime.toml`: `host = "127.0.0.1"` (o tunnel resolve).

`plugadvpl` imprime warning se detectar host remoto sem `--no-security-warning`.

---

## Cenários típicos

### Dev local com TDS-VSCode + Protheus instalado

```bash
# Localiza advpls dentro da extensão VSCode
$advpls = (Get-ChildItem "$env:USERPROFILE\.vscode\extensions\totvs.tds-vscode-*\node_modules\@totvs\tds-ls\bin\windows\advpls.exe").FullName
$env:PLUGADVPL_ADVPLS_BINARY = $advpls

# Compila modo appre
plugadvpl compile --mode appre --includes "D:\TOTVS\protheus\Include" MEUFONTE.PRW
```

### CI sem nada Protheus na máquina

`.github/workflows/compile.yml`:
```yaml
- name: Setup advpls
  run: |
    curl -L -o tds.vsix \
      "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/TOTVS/vsextensions/tds-vscode/latest/vspackage"
    unzip -q tds.vsix -d tds-vscode/
    chmod +x tds-vscode/extension/node_modules/@totvs/tds-ls/bin/linux/advpls
    echo "PLUGADVPL_ADVPLS_BINARY=$PWD/tds-vscode/extension/node_modules/@totvs/tds-ls/bin/linux/advpls" >> $GITHUB_ENV

- name: Cache includes Protheus
  uses: actions/cache@v4
  with:
    path: protheus-includes/
    key: protheus-includes-${{ hashFiles('protheus-includes-version.txt') }}

- name: Compile changed
  run: |
    pip install plugadvpl
    plugadvpl compile --mode appre --includes ./protheus-includes \
      --changed-since origin/main
```

Includes Protheus precisam ser disponibilizados (S3 privado, artifact pré-cacheado, etc — não distribuíveis publicamente por licença TOTVS).

### Dev usando VPS Protheus + tunnel

```bash
# Terminal 1: tunnel persistente
ssh -L 1234:localhost:1234 -L 8080:localhost:8080 fabrica@meu-vps -N

# Terminal 2: configurar e compilar
export PROTHEUS_USER=admin
export PROTHEUS_PASS='secret'
plugadvpl compile --init-config
# Edite runtime.toml: host = "127.0.0.1"
plugadvpl compile --mode cli MEUFONTE.PRW
```

---

## Troubleshooting

### `Error C2090 File not found PRTOPDEF.CH`

Includes Protheus não chegaram ao `advpls`. Causas:

1. `--includes` não passado. Solução: `--includes <pasta-include-protheus>` (flag **antes** do nome do arquivo).
2. Pasta passada não tem `PRTOPDEF.CH`. Verifique: `ls <pasta>/PRTOPDEF.CH` (case-insensitive em Windows).
3. Em `runtime.toml`, `[compile].includes = []` está vazio.

### `advpls not found in PATH`

`PLUGADVPL_ADVPLS_BINARY` não setado e `advpls` fora do PATH. Solução: setar env var ou `[tds_ls].binary` no `runtime.toml`.

### `nenhum fonte informado` (exit 2)

Esqueceu de passar o arquivo OU passou flags depois do arquivo (typer consome flags como mais arquivos). Sempre: `plugadvpl compile [OPTIONS] <fontes...>`.

### `runtime.toml required for cli mode`

Você passou `--mode cli` mas não criou `runtime.toml`. Rode: `plugadvpl compile --init-config`.

### Compila no `appre` mas tem erro de `If` sem `EndIf` ignorado

Esperado. `appre` é só pré-processador — não detecta erros semânticos. Pra esses, use `--mode cli` com AppServer rodando.

### Exit code `4294967295` no JSON (Windows)

Bug corrigido em v0.8.1. Atualize: `uv tool install plugadvpl --reinstall`.

### Output JSON tem `__unmatched__` ruidoso

Bug corrigido em v0.8.2 (filtro de log interno do advpls). Atualize.

---

## Referências

- [Spec da Fase 1](fase1/compile-design.md) — design completo do subcomando
- [CHANGELOG v0.8.x](../CHANGELOG.md#080---2026-05-18) — histórico de fixes do compile
- [cli-reference §compile](cli-reference.md#compile) — sintaxe e exit codes
