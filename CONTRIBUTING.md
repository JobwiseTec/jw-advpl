# Contributing

## Setup local

```bash
git clone https://github.com/plugadvpl-org/plugadvpl
cd plugadvpl

# Instalar uv (https://docs.astral.sh/uv/)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sincronizar deps de dev
uv sync --directory cli

# Rodar testes
cd cli && uv run pytest tests/unit tests/integration -v

# Testar plugin localmente
claude --plugin-dir .
```

## Fixtures locais (`pytest -m local`)

Os testes E2E em `cli/tests/e2e_local/` esperam pastas que existem só na máquina do autor (`customizados-local`). Em CI são pulados automaticamente. Se você é o autor e quer rodar:

```bash
uv run pytest -m local -v
```

## Estilo

- `ruff format` (linhas ≤100)
- `ruff check`
- `mypy --strict`
- Mensagens de commit: Conventional Commits (`feat:`, `fix:`, `refactor:`, ...)
