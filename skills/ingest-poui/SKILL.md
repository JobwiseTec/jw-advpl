---
description: Detecta projetos PO UI (frontend Angular TOTVS) — versão @po-ui/*, Angular exigido e incompatibilidades
disable-model-invocation: true
arguments: [dir]
allowed-tools: [Bash]
---

# `/plugadvpl:ingest-poui`

Ingere um diretório de projeto PO UI: lê `package.json`, detecta a família
`@po-ui/*`, deriva o major do Angular exigido (major npm == major Angular) e
flag projetos incompatíveis.

## Execução

```bash
uvx plugadvpl@0.26.0 --format md ingest-poui $ARGUMENTS
```

## Relacionado
- Skill `poui-fundamentals` — família @po-ui, versionamento, estrutura.
