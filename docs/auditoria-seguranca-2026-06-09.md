# Auditoria de Segurança — plugadvpl

- **Data:** 2026-06-09
- **Versão auditada:** v0.31.0 (commit `6b919d4`)
- **Escopo:** CLI Python (`cli/plugadvpl`), hooks do plugin (`hooks/`), instalação (`scripts/`, `.claude-plugin/`), CI/CD (`.github/workflows/`), dependências (`pyproject.toml` + `uv.lock`), documentação pública (`docs/`, `marketing/`).
- **Método:** varredura em 4 dimensões (credenciais, execução/injeção, rede/privacidade, supply chain) com verificação manual de cada achado no código-fonte. Cada item abaixo cita arquivo:linha conferido diretamente — nada aqui é especulação.

---

## Veredicto

**Nenhuma falha crítica explorável foi encontrada.** Não há execução remota de código, não há vazamento de credenciais para disco ou rede, não há telemetria oculta, não há segredos hardcoded, não há SQL injection real, e a cadeia de publicação (PyPI) usa OIDC sem tokens de longa vida.

Foram identificados **2 achados de severidade média** (endurecimento recomendado, ambos exigem que o atacante já tenha comprometido outra coisa antes) e **5 achados de severidade baixa/informativa**. Detalhes abaixo.

---

## Achados

### A1 — `shell=True` no restart do Troca Quente — **MÉDIA**

**Onde:** [tq.py:91-98](../cli/plugadvpl/tq.py#L91-L98)

```python
proc = subprocess.run(
    server.restart_cmd,
    shell=True,
    ...
)
```

O `restart_cmd` vem do registry de servidores (`servers.json`, gravado em `~/.plugadvpl/` com `chmod 0o600` em POSIX por `compile_servers.py`). Com `shell=True`, qualquer conteúdo desse campo é interpretado pelo shell.

**Por que não é crítico:** o `restart_cmd` é configurado pelo próprio usuário via `plugadvpl compile --set-restart-cmd` — é, por design, um comando arbitrário do usuário. Para explorar, um atacante precisaria conseguir escrever no `servers.json` do perfil do usuário; quem consegue isso já consegue coisas piores (editar o PATH, o profile do shell, etc.).

**Por que ainda vale endurecer:** `shell=True` amplia a superfície sem necessidade na maioria dos casos. Em Windows o `chmod 0o600` não tem efeito real (ACLs não são ajustadas), então o arquivo fica com as permissões default da pasta do usuário.

**Recomendação:** aceitar string de comando, mas executar com `shlex.split()` + `shell=False` por padrão, oferecendo um campo opt-in explícito (ex.: `restart_shell = true`) para quem precisa de pipes/builtins do shell. Documentar no help do `--set-restart-cmd` que o comando roda com privilégios do usuário.

---

### A2 — Extração do `.vsix` sem guarda de zip-slip e sem checksum — **MÉDIA**

**Onde:** [compile_installer.py:213](../cli/plugadvpl/compile_installer.py#L213) (download) e [compile_installer.py:240-248](../cli/plugadvpl/compile_installer.py#L240-L248) (extração)

```python
for member in members:
    rel = member[len(prefix):]
    if not rel:
        continue
    dst = target_dir / rel        # rel não é validado contra ".."
```

O instalador do `advpls` baixa o `.vsix` do VSCode Marketplace (URL HTTPS hardcoded da TOTVS/Microsoft) e extrai apenas membros cujo nome começa com o prefixo `extension/.../bin/<os>/`. Porém:

1. **Zip-slip:** um membro com nome `"<prefixo>/../../../evil.exe"` passa no filtro `startswith(prefix)` e o `rel` resultante (`../../../evil.exe`) faz `dst` escapar de `target_dir`. Não há validação de `..` nem `Path.resolve()` + verificação de contenção.
2. **Sem checksum/assinatura:** o `.vsix` baixado não tem hash verificado (a única validação é `BadZipFile`, que detecta corrupção de formato, não adulteração).

**Por que não é crítico:** explorar exige servir um `.vsix` malicioso — ou seja, comprometer o Marketplace da Microsoft ou montar MITM contra TLS válido. O TLS é verificado (default do Python; nenhum `verify=False`/`CERT_NONE` existe no repositório — confirmado por busca).

**Recomendação:** (1) validar cada membro com `dst.resolve().is_relative_to(target_dir.resolve())` antes de escrever — correção de 3 linhas; (2) se a API do Marketplace expuser hash do pacote, conferir; caso contrário, documentar a limitação.

---

### A3 — COLETADB: Basic Auth sobre HTTP sem aviso em runtime — **MÉDIA-BAIXA**

**Onde:** [coletadb_client.py:278-281](../cli/plugadvpl/coletadb_client.py#L278-L281) (header `Authorization: Basic`) e ausência de warning para endpoints `http://` remotos.

O cliente COLETADB autentica com HTTP Basic (base64 ≠ criptografia). Se o usuário configurar um endpoint `http://` apontando para host remoto, **usuário e senha trafegam em claro na rede**. O template do `runtime.toml` já recomenda `host = "127.0.0.1"` + túnel SSH, e o fluxo de compilação tem aviso análogo ([compile.py:395](../cli/plugadvpl/compile.py#L395): "TDS-LS envia user/password sem TLS sobre TCP") — mas o caminho COLETADB não emite aviso equivalente.

**Pontos positivos verificados:** a validação TLS nunca é desabilitada (nenhuma ocorrência de `verify=False`, `ssl._create_unverified_context` ou `CERT_NONE` no pacote); downloads de arquivo do COLETADB têm verificação de hash (SHA256/SHA1/MD5) contra o manifest ([coletadb_client.py:221-272](../cli/plugadvpl/coletadb_client.py#L221-L272)).

**Recomendação:** emitir warning quando o endpoint é `http://` e o host não é loopback (mesmo padrão do aviso já existente no compile). Opcional: aceitar um `ssl_context` customizado para CA corporativa/pinning.

---

### A4 — Chave HMAC default do `--privacy` sem aviso em runtime — **BAIXA**

**Onde:** [privacy/config.py:41](../cli/plugadvpl/privacy/config.py#L41)

```python
_DEV_KEY = b"plugadvpl-privacy-default-key-troque-em-producao"  # gitleaks:allow
```

A tokenização de PII (ex.: `CNPJ_7F3A9C`) usa HMAC. Sem `PLUGADVPL_PRIVACY_KEY` definida, a chave é essa constante pública. Como o espaço de CPF/CNPJ é pequeno e enumerável, quem possui um token gerado com a chave-dev consegue reconstruir o valor original por força bruta de dicionário. A limitação está **documentada honestamente** no próprio código ("tokens estáveis, porém previsíveis — troque em produção"), e o campo `key_explicit` existe na config ([privacy/config.py:63](../cli/plugadvpl/privacy/config.py#L63)) — mas verificado: **nenhum código consome `key_explicit` para avisar o usuário**.

**Recomendação:** quando `--privacy` estiver ativo com a chave-dev (`key_explicit=False`), imprimir um aviso único no stderr sugerindo definir `PLUGADVPL_PRIVACY_KEY`. O campo necessário já existe; falta só o consumo.

---

### A5 — `ci.yml` sem bloco `permissions:` no nível do workflow — **BAIXA**

**Onde:** [.github/workflows/ci.yml](../.github/workflows/ci.yml) (linhas 1-7 não declaram `permissions:`; só o job `bench`, linha 163, declara — e corretamente, pois precisa de `contents: write` para o gh-pages).

Os demais jobs (lint, test, smoke, secret-scan) herdam o default do repositório, que pode ser amplo dependendo da configuração da conta/organização. Os workflows de release ([release.yml:10-12](../.github/workflows/release.yml#L10-L12)) e CodeQL já declaram permissões mínimas — o CI é o único sem.

**Contexto que reduz o risco:** o CI usa `on: pull_request` (não `pull_request_target` — confirmado: zero ocorrências), então PRs de fork não recebem secrets nem token com escrita.

**Recomendação:** adicionar no topo do `ci.yml`:

```yaml
permissions:
  contents: read
```

(o job `bench` mantém seu override local).

---

### A6 — Installers fazem `curl | sh` do instalador do uv — **BAIXA (risco aceito)**

**Onde:** [scripts/install.sh:15](../scripts/install.sh#L15) e [scripts/install.ps1:39,43](../scripts/install.ps1#L39)

Os bootstraps baixam e executam o instalador oficial do uv de `https://astral.sh` quando o uv não está presente (o `.ps1` tenta `winget` primeiro, o que é bom). É o padrão de instalação documentado pela própria Astral, via HTTPS, de fornecedor respeitável — risco residual de comprometimento do domínio astral.sh é aceito pela indústria inteira. Sem ação obrigatória; opcionalmente, pinnar a URL de release específica do GitHub da Astral.

---

### A7 — Observações informativas (sem ação obrigatória)

| # | Observação | Avaliação |
|---|---|---|
| 1 | Credenciais via env vars (`PROTHEUS_USER`/`PROTHEUS_PASS`) são herdadas por subprocessos filhos | Tradeoff inerente ao design env-var; o subprocesso filho é o próprio `advpls`, que precisa delas. Sem vazamento adicional. |
| 2 | `.claude/settings.json` local contém allowlist com `export PROTHEUS_USER=admin` e `curl -u admin:admin` (credenciais de dev local) | **Verificado: o arquivo NÃO está commitado** — `.claude/` está no `.gitignore` (linha 31) e `git ls-files` confirma. Manter assim; são credenciais de AppServer de desenvolvimento local. |
| 3 | SQL com nome de tabela interpolado em f-string (`ingest.py:197`, `ingest_sx.py:610`, `query.py:1668`) | Verificado: todos os identificadores vêm de tuplas/dicts/frozensets **hardcoded no código** — nunca de input externo. Valores de dados usam placeholder `?` corretamente. Não é SQL injection. |
| 4 | Hook `SessionStart` executa Node a cada carga do plugin | Verificado: usa `execFileSync` com args constantes (sem shell), timeout de 10s, output truncado, falha silenciosa. Implementação defensiva correta. |

---

## O que está bem feito (controles verificados)

1. **Credenciais nunca tocam disco em claro.** Precedência env var → keyring do OS (DPAPI/Keychain/Secret Service); o `servers.json` guarda apenas host/porta/nomes de env var ([credentials.py](../cli/plugadvpl/credentials.py)). `set-credentials` usa prompt com `hide_input=True` + confirmação.
2. **Senha não aparece em argumentos de processo.** O compile escreve um `.ini` temporário com `O_EXCL` + `chmod 0o600` em tempdir próprio e o destrói no `finally` ([compile.py:197-215, 455-460](../cli/plugadvpl/compile.py#L197-L215)).
3. **Logs sanitizados por design.** `to_safe_dict()` retorna `<set>`/`<unset>` em vez da senha; catálogo de redação (`lookups/redact_patterns.json`) cobre `password=`, `senha=`, `psw=`, URLs com credencial e chaves hex.
4. **Zero telemetria e zero egress automático.** Únicos pontos de rede: COLETADB (endpoint que o usuário configura), download do VSIX (Marketplace, HTTPS) e TCP ping de diagnóstico. Confirmado por enumeração de todos os usos de `urllib`/`socket` no pacote.
5. **Sem `eval`/`exec`/`pickle`/`yaml.load` em todo o pacote.** Confirmado por busca exaustiva.
6. **Supply chain do release sólida.** PyPI via Trusted Publishing OIDC (sem token de longa vida), actions todas pinned por versão (nenhum `@latest`/`@main`), CodeQL com `security-extended` + agendamento semanal, gitleaks no CI com regras ADVPL customizadas, apenas 5 dependências runtime, todas ativas e travadas no `uv.lock`.
7. **Sem `pull_request_target`.** PRs de fork não acessam secrets.
8. **Instalação do plugin Claude Code é metadata-only.** O `marketplace.json` só aponta o repositório via URL HTTPS; nenhum script de instalação custom roda.
9. **SECURITY.md** existe, com contato, prazo de resposta e escopo explícito, incluindo recomendações de uso seguro (`.plugadvpl/` no `.gitignore`, `--no-content`, `--redact-secrets`).
10. **Docs e marketing limpos.** Nenhum IP interno real, hostname corporativo ou credencial encontrado; exemplos usam valores claramente sintéticos.

---

## Plano de ação sugerido (por prioridade)

> **Status (2026-06-09):** todos os 6 itens implementados na branch
> `fix/security-hardening`, com TDD (plano em
> `docs/superpowers/plans/2026-06-09-security-hardening-auditoria.md`).

| Prioridade | Ação | Esforço | Status |
|---|---|---|---|
| P1 | A2: guarda de zip-slip na extração do VSIX (`is_relative_to` após `resolve()`) | ~3 linhas + teste | ✅ `fix(installer)` |
| P1 | A1: `shell=False` + `shlex.split()` no Troca Quente, com opt-in para shell | pequeno | ✅ `fix(tq)!` — opt-in `--restart-shell` |
| P2 | A3: warning quando endpoint COLETADB é `http://` não-loopback | pequeno | ✅ `fix(coletadb)` — supressível com `--no-security-warning` |
| P2 | A5: `permissions: contents: read` no topo do `ci.yml` | 2 linhas | ✅ `ci:` |
| P3 | A4: aviso de chave-dev quando `--privacy` ativo sem `PLUGADVPL_PRIVACY_KEY` | pequeno | ✅ `fix(privacy)` |
| P3 | A6: (opcional) pinnar URL de release do instalador uv | 1 linha | ✅ `fix(scripts)` — pinado em uv 0.11.19 (GitHub release) |

---

*Auditoria realizada com verificação manual de cada call site citado. Nenhum achado foi incluído sem confirmação direta no código-fonte da versão auditada.*
