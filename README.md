# plugadvpl

Plugin Claude Code + CLI Python que indexa fontes ADVPL/TLPP em SQLite e
permite ao Claude consultar metadados (funções, tabelas, MV_*, call graph,
SQL embedado) **antes** de abrir arquivos `.prw` inteiros, economizando
10–15× tokens em projetos Protheus.

## Status

Em desenvolvimento (v0.1.0 não publicada ainda).

## Quick start (quando lançado)

```bash
# 1. Instalar uv (se não tiver)
winget install astral-sh.uv   # Windows
# ou: curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Adicionar marketplace do plugin no Claude Code
/plugin marketplace add github.com/plugadvpl-org/plugadvpl
/plugin install plugadvpl

# 3. Abrir projeto Protheus, executar:
/plugadvpl:init
/plugadvpl:ingest

# 4. Pronto. Claude agora usa o índice.
```

Ver `docs/superpowers/specs/2026-05-11-plugadvpl-design.md` para design completo.

## Licença

MIT. Ver [LICENSE](LICENSE) e [NOTICE](NOTICE).
