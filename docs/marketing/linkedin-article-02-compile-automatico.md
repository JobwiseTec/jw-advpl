# Como compilar ADVPL em qualquer shell, em qualquer projeto, em CI — sem virar refém do TDS-VSCode

> **Sub-título:** O TDS-VSCode é ótimo pra desenvolver, mas péssimo pra automatizar. Você não consegue rodar `gh actions` que compile 200 fontes a cada PR, nem encadear `compile` em scripts. Mostro como o `plugadvpl compile` resolve isso usando o **binário oficial `advpls` da TOTVS** por baixo.

## O problema real

Compile de ADVPL hoje, na prática:

1. Abre TDS-VSCode
2. Conecta no AppServer (popup, clica, escolhe environment, digita senha)
3. Botão direito no fonte → Compilar
4. Espera, lê stdout amarelo no Output panel
5. Tem erro? Procura no panel "Problems"
6. Vai pro próximo fonte. Repete.

Funciona? Funciona. Escala? Não.

**Casos onde isso quebra:**

- **CI/CD:** "Quero que cada PR rode compile em N fontes antes de mergear." Não tem como rodar TDS-VSCode em GitHub Actions / GitLab / Jenkins.
- **Patches grandes:** Receber um pacote de 100 fontes pra compilar manualmente é tortura.
- **Múltiplos environments:** AppServer com `protheus`, `protheus_rest`, `protheus_web` — você precisa lembrar de compilar pros 3, senão o REST serve código velho enquanto o `protheus` tem o novo. Bug silencioso clássico.
- **Pré-flight check:** "Esse RPO tá saudável? Os includes batem? O AppServer aceita conexão?" — não tem comando, é tudo "tenta compilar e vê se quebra".
- **Compartilhar setup entre devs:** Cada um configura TDS-VSCode do zero. Não tem registry compartilhado.

## A solução

O **`plugadvpl compile`** é um **wrapper Python sobre o `advpls`** — o binário oficial da TOTVS que vive dentro da extensão TDS-VSCode pública.

> Nota: o `plugadvpl` NÃO reimplementa o compilador. ADVPL é proprietário TOTVS, sem fork open-source. O plugin chama o `advpls` via `subprocess`, captura stdout/stderr + `.errprw`, parseia output em texto livre via regex externalizados, e devolve **JSON estruturado** consumível por CI.

### Setup zero-config (3 comandos, 1x na vida)

```bash
# 1. Instala o binario advpls (interativo: copia de path local OU baixa do Marketplace VSCode, ~118MB)
plugadvpl compile --install-advpls

# 2. Importa servers do TDS-VSCode (le ~/.totvsls/servers.json automaticamente)
plugadvpl compile --import-tds-servers --yes

# 3. Salva credencial no cofre nativo do OS (Win Credential Manager / macOS Keychain / Linux Secret Service)
plugadvpl compile --set-credentials <nome-do-server>
# Prompt seguro com getpass, senha NUNCA grava em arquivo
```

A partir daí, **qualquer projeto, qualquer shell, sem env var, sem runtime.toml:**

```bash
plugadvpl compile --use-server prod --mode cli FONTE.PRW
```

### 2 modos de compile

```bash
# appre (local, pre-processador, sem AppServer)
plugadvpl compile --mode appre FONTE.PRW

# cli (full, conecta no AppServer via TCP, atualiza RPO)
plugadvpl compile --use-server prod --mode cli FONTE.PRW
```

`appre` é rápido, valida sintaxe e expande includes. Roda offline. Bom pra CI de lint sintático.

`cli` é o real — compila contra o AppServer e atualiza o `custom.rpo`. Equivalente ao "F11" do TDS-VSCode, mas via terminal.

### `--all-envs` resolve o RPO sync

Tem AppServer com `protheus` E `protheus_rest`? Antes era:

```bash
plugadvpl compile --use-server X --use-environment protheus FONTE.PRW
plugadvpl compile --use-server X --use-environment protheus_rest FONTE.PRW
```

Ou pior — esquecer o segundo, deploy ir pro ar, REST servir código velho, e você passar 2 horas debugando.

Agora:

```bash
plugadvpl compile --use-server X --all-envs FONTE.PRW
```

Compila pros N envs do server em sequência, anota linha com coluna `env`, exit code é o pior dos envs.

### `--doctor` pra pre-flight check

```bash
plugadvpl compile --doctor
```

Devolve JSON estruturado com:

- `advpls` detectado? (path absoluto + versão)
- Includes do Protheus encontrados?
- AppServer respondendo na porta TCP?
- Credenciais resolvidas (env var, keyring, ou auto-detect)?
- `next_actions` ordenadas pra resolver o que falta

Ideal pra agente IA seguir passo a passo OU pra dev novo entender o que precisa configurar.

### `--probe-appserver` descobre build do AppServer

Cliente passou só "host:port" e você não sabe a versão? Tem 2 modos:

```bash
# Modo network: invoca advpls cli action=validate
plugadvpl compile --probe-appserver 10.0.0.5:1234

# Modo log: parseia protheus.log offline (quando não tem rede)
plugadvpl compile --probe-appserver /caminho/pra/protheus.log
```

Saída: build + flag SSL + ambiente padrão. Funciona via SSH tunnel/VPN também.

### `--explain-config` pra debugar setup

```bash
plugadvpl compile --explain-config --use-server prod
```

JSON estruturado mostrando ordem de precedência da resolução:

```
CLI flag > runtime.toml > registry > keyring > env > auto-detect
```

E de onde veio cada campo. Senha sempre redacted (`"<set>"` / `"<unset>"`, nunca o valor).

Quando dá problema "por que está usando aquele advpls" ou "por que a credencial não tá resolvendo", essa é a resposta.

## Ganhos concretos

### Em desenvolvimento

- Compile sem sair do terminal. Encadeia com git, com `pytest`, com bash scripts.
- Setup uma vez, usa em qualquer projeto. Não precisa "criar servers.json" em cada repo.
- Senha no cofre do OS — nunca mais `$env:PROTHEUS_USER="..."` em cada shell.

### Em CI/CD

- GitHub Actions rodando `plugadvpl compile --doctor` + `compile --changed-since main` em cada PR.
- Saída JSON `--format json` é estável e parseável.
- Exit codes: `0` = OK, `1` = compile falhou, `2` = config errada. CI pode reagir diferente em cada caso.

### Em multi-cliente / consultoria

- Cada cliente é um server no registry global. Troca rápida: `--use-server cliente-A` vs `--use-server cliente-B`.
- `--probe-appserver` pra descobrir versão do AppServer do cliente novo sem precisar de TDS-VSCode configurado.
- `--import-tds-servers` puxa setup que você já tem no TDS-VSCode em 1 comando.

### Em equipe

- Todo dev compila igual. Sem "funciona na minha máquina, no TDS-VSCode" / "no meu não" — todo mundo usa o mesmo `advpls`, o mesmo registry global, a mesma resolução de credencial.

## Exemplo de fluxo real

```bash
# Setup uma vez (Windows PowerShell)
plugadvpl compile --install-advpls
plugadvpl compile --import-tds-servers --yes
plugadvpl compile --set-credentials prod

# Diariamente
git pull
plugadvpl compile --use-server prod --all-envs --changed-since main
# compila so o que mudou desde o branch main, em todos os envs

# Em CI (GitHub Actions)
- name: Compile changed sources
  run: |
    uvx plugadvpl compile --doctor
    uvx plugadvpl compile --mode appre --changed-since origin/main \
      --format json > compile.json
```

## Open-source, MIT, sem telemetria

Wrapper sobre o `advpls` oficial da TOTVS (também MIT, distribuído na extensão TDS-VSCode pública). 100% local. Não envia código nem credencial pra ninguém.

→ **PyPI:** [pypi.org/project/plugadvpl](https://pypi.org/project/plugadvpl)
→ **GitHub:** [github.com/JoniPraia/plugadvpl](https://github.com/JoniPraia/plugadvpl)
→ **Docs:** `docs/setup-compile.md` (guia passo-a-passo) + `docs/compile-checklist.md` (o que coletar antes)

#ADVPL #TLPP #Protheus #TOTVS #CICD #DevOps #OpenSource
