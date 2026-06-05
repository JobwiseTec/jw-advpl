# Guia — secret scanning (gitleaks) no projeto do cliente

> **Para quê:** impedir que **segredos** (senha, token, connection string, chave) entrem no
> repositório de código ADVPL do cliente. É a **Camada 0 — Prevenção**: complementa o mascaramento
> do plugadvpl (que protege o que **sai** pro LLM) impedindo o segredo de **entrar** no código.
>
> **Onde roda:** no **pre-commit** (bloqueia na máquina do dev) e no **CI** do cliente (bloqueia o merge).

---

## 1. Pré-requisitos

| Item | Como instalar |
|---|---|
| **gitleaks** | Win: `winget install gitleaks` ou `choco install gitleaks`. macOS: `brew install gitleaks`. Linux: baixar o binário em github.com/gitleaks/gitleaks/releases. |
| **pre-commit** (opcional, p/ hook local) | `pip install pre-commit` (ou `pipx install pre-commit`). |
| **Git** | já instalado no ambiente de dev. |

Verifique: `gitleaks version`.

---

## 2. Passo a passo (no repositório de fontes do cliente)

### 2.1 Copie a config
Copie o `.gitleaks.toml` do plugadvpl para a raiz do repositório do cliente (ele já traz as regras
ADVPL/Protheus: `senha=`, `psw=`, `pwd=`, `aut_file`, credencial em URL). Ajuste o `allowlist` para os
caminhos de fixtures/exemplos do cliente.

### 2.2 Hook local (pre-commit)
Crie/edite `.pre-commit-config.yaml` na raiz:

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks
```

Instale o hook:
```bash
pre-commit install
```
Pronto: a partir de agora, **cada commit é varrido**. Se houver senha, o commit é bloqueado.

### 2.3 CI (GitHub Actions)
Crie `.github/workflows/secret-scan.yml`:

```yaml
name: secret-scan
on: [pull_request, push]
jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Install gitleaks
        run: |
          VERSION=8.30.1
          curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${VERSION}/gitleaks_${VERSION}_linux_x64.tar.gz" -o /tmp/g.tar.gz
          tar -xzf /tmp/g.tar.gz -C /tmp gitleaks && sudo mv /tmp/gitleaks /usr/local/bin/
      - run: gitleaks detect --no-git --redact --config .gitleaks.toml --source .
```

> Em GitLab/Azure DevOps, o passo é o mesmo: instalar o binário e rodar `gitleaks detect`.

---

## 3. Uso no dia a dia

```bash
# varredura manual de toda a árvore atual:
gitleaks detect --no-git --redact --config .gitleaks.toml --source .

# varrer o histórico inteiro (uma vez, para auditoria inicial):
gitleaks detect --redact --config .gitleaks.toml
```

- **Achou um segredo de verdade?** Remova do código, troque a credencial vazada (ela é considerada
  comprometida), e mova para variável de ambiente / cofre.
- **Falso-positivo** (ex.: massa de teste)? Adicione o caminho ao `allowlist` do `.gitleaks.toml`, ou
  marque a linha com `# gitleaks:allow`.

---

## 4. Como isso se encaixa na proteção total

| Camada | Ferramenta | Protege |
|---|---|---|
| **0 — Prevenção** | **gitleaks** (este guia) | segredo **entrar** no código do cliente |
| 2 — Egress | plugadvpl `--privacy` | dado sensível **sair** pro LLM |
| 4 — Deployment | Bedrock/Vertex | os **programas** como IP (Fase 2) |

gitleaks não substitui o mascaramento — **previne** o segredo de nascer no repo; o mascaramento cuida
do que já está lá e do que trafega para a IA. Juntos, fecham o ciclo.
