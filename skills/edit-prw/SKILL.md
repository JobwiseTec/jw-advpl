---
description: Workflow seguro pra editar .prw cp1252 com Claude Code (Read/Edit são UTF-8 only). Use ANTES de qualquer Read/Edit em .prw com acentos.
disable-model-invocation: true
arguments: [arquivo]
allowed-tools: [Bash]
---

# `/plugadvpl:edit-prw`

> 🚨 **CRÍTICO pro agente**: Read/Edit tools do Claude Code são **UTF-8 only**.
> Quando lêem `.prw` cp1252, bytes acentuados viram `�` (replacement char).
> Se você fizer `Edit` nessa visão, o `Edit` regrava o arquivo **inteiro**
> em UTF-8 — incluindo os `�` — **corrompendo acentos não-editados**.

## Workflow obrigatório (Caminho A — stage/commit)

Sempre que precisar editar `.prw` cp1252 com Read/Edit do Claude:

```bash
# 1. ANTES de qualquer Read/Edit — converte cp1252 → utf-8
plugadvpl edit-prw stage <fonte.prw>
#   Cria <fonte>.bak com bytes cp1252 originais

# 2. Agora pode usar Read/Edit/Write livremente. Acentos preservados.
#    (Arquivo está temporariamente em UTF-8 — NÃO compila ainda, é só pra editar)

# 3. DEPOIS de todas as edições — volta pra cp1252
plugadvpl edit-prw commit <fonte.prw>
#   Acentos novos digitados durante edição viram bytes cp1252 corretamente
```

## Caminhos alternativos

### Caminho B — edição cirúrgica em PowerShell (sem stage/commit)

Quando a mudança é mecânica (find/replace):
```powershell
$path = "Customizados\FOO.PRW"
$enc  = [System.Text.Encoding]::GetEncoding(1252)
$txt  = $enc.GetString([System.IO.File]::ReadAllBytes($path))
$txt  = $txt -replace 'PADRAO_VELHO', 'PADRAO_NOVO'
[System.IO.File]::WriteAllBytes($path, $enc.GetBytes($txt))
```
Zero conversão, mas verboso pra refactor maior.

### Caminho C — restringir Edit a trechos ASCII puro

❌ **NÃO RECOMENDADO**. Mesmo editando só linhas sem `�`, o `Edit` regrava o
arquivo inteiro como UTF-8 e os `�` substituem acentos não-editados.

## Subcomandos

| Comando | Função |
|---|---|
| `edit-prw stage <arq>` | cp1252 → utf-8 (cria `.bak` com original). Use ANTES de Read/Edit |
| `edit-prw commit <arq>` | utf-8 → cp1252 (reverso). Use DEPOIS de editar |
| `edit-prw check <arq>` | Diagnóstico: detecta encoding atual vs esperado pela extensão. Exit 1 se mismatch |
| `edit-prw open <arq>` | Imprime conteúdo em UTF-8 puro (não modifica arquivo). Útil pra ler sem stage |
| `edit-prw save <arq> --from X --to Y` | Conversão manual genérica (stage/commit são atalhos disso) |

## Quando NÃO precisa do stage/commit

- Arquivo é `.tlpp` (já é UTF-8 nativo)
- Arquivo é `.prw` em UTF-8 puro (raro mas existe — checa com `edit-prw check`)
- Você vai usar PowerShell/script externo pra editar (Caminho B)
- Não tem acentos no arquivo nem nas suas mudanças (ASCII puro)

## Exemplo completo

```bash
# Inspeciona primeiro
plugadvpl --format json edit-prw check Customizados/LJ7016_PE.PRW
# {"file": "...", "detected_encoding": "cp1252", "match": true, ...}

# Stage
plugadvpl edit-prw stage Customizados/LJ7016_PE.PRW
# ✓ Staged: ... agora em utf-8 (acentos preservados)

# ----- Aqui Claude usa Read/Edit normalmente -----

# Commit
plugadvpl edit-prw commit Customizados/LJ7016_PE.PRW
# ✓ Committed: ... volta em cp1252 (pronto pra compilar)

# Confirma round-trip
plugadvpl --format json edit-prw check Customizados/LJ7016_PE.PRW
# {"detected_encoding": "cp1252", "match": true, ...}
```

## Skills relacionadas

- `advpl-encoding` — política geral de encoding em fontes ADVPL/TLPP
- `compile` — após editar, compile pra validar (`plugadvpl compile --mode appre <fonte>`)
