---
description: Gera um "aplicador de SXs" (.prw ADVPL) determinístico a partir de um spec JSON, aplicando customizações de dicionário (SX2 tabelas, SX3 campos, SIX índices, SX6 params MV_*, SX7 gatilhos, SX1 perguntas, SXA pastas, SX5 tabelas genéricas) em modo EXCLUSIVO — no lugar de um RecLock ingênuo. Use ao criar/alterar campo, tabela, índice, parâmetro, gatilho ou pergunta via dicionário. NÃO use para gerar fonte de regra de negócio (use advpl-code-generator) nem para diagnosticar SX existente (use advpl-dicionario-sx).
disable-model-invocation: true
arguments: [spec]
allowed-tools: [Bash, Read, Write]
---

# `/plugadvpl:gen-aplicador-sx`

Gera um **aplicador de SXs**: um `.prw` ADVPL **determinístico** (mesma spec → mesmos bytes) que aplica mudanças de dicionário (SX/SIX) em **modo EXCLUSIVO** (`MyOpenSM0` / `RpcSetEnv` / `X31UpdTable`), com **backup** antes, em vez de um `RecLock` solto em cima do SX. O CLI monta o fonte a partir de um spec JSON — sem LLM, sem random/Date.

> **Por que não RecLock direto no SX?** Atualizar dicionário fora de update estruturado corrompe metadados (X3_ORDEM fora de sequência, índice físico não dropado quando a chave muda, parâmetro sobreposto). O aplicador roda exclusivo + backup, calcula a ordem, dropa índice físico quando preciso, e é insert-aware (não duplica nem sobrescreve o que já existe).

## O que é o spec JSON

```json
{
  "numero": "099999",
  "sx2": [ ... ],
  "sx3": [ ... ],
  "six": [ ... ],
  "sx6": [ ... ],
  "sx7": [ ... ],
  "sx1": [ ... ],
  "sxa": [ ... ],
  "sx5": [ ... ]
}
```

Só `numero` é obrigatório; **todas as seções SX são opcionais** — emite só as presentes (ordem canônica sx2 → sx3 → six → sx6 → sx7 → sx1 → sxa → sx5). O `.prw` final vira `User Function A{numero}`.

### Exemplo sintético (tabela ZXX + campo + índice + parâmetro)

```json
{
  "numero": "099999",
  "sx2": [
    { "alias": "ZXX", "nome": "Cadastro de Exemplo", "modo": "C", "unico": "ZXX_FILIAL+ZXX_COD" }
  ],
  "sx3": [
    { "alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Codigo" },
    { "alias": "ZXX", "campo": "ZXX_DESC", "tipo": "C", "tamanho": 40, "titulo": "Descricao" }
  ],
  "six": [
    { "alias": "ZXX", "ordem": "1", "chave": "ZXX_FILIAL+ZXX_COD", "descricao": "Por codigo" }
  ],
  "sx6": [
    { "var": "MV_XEXMPL", "tipo": "L", "conteudo": ".T.", "descric": "Habilita rotina de exemplo" }
  ]
}
```

## Referência de campos por tipo

As chaves abaixo são as que você preenche no spec; o gerador aplica os defaults seguros e espelha pra todos os idiomas (SPA/ENG) e colunas físicas. Derivado de `aplicador_sx/schema.py`.

| Tipo | Chaves do spec | Defaults aplicados |
|---|---|---|
| **sx2** (tabelas) | `alias`*, `nome`*, `modo`, `unico`, `display`, `rotina`, `path` | `modo='E'` |
| **sx3** (campos) | `alias`*, `campo`*, `tipo`*, `tamanho`, `decimal`, `titulo`, `descric`, `picture`, `valid`, `when`, `usado`, `f3`, `cbox`, `relacao`, `folder`, `grpsxg`, `trigger`, `browse` | `tipo='C'`, `usado='todos'` (máscara 256 módulos), `browse='N'`; **X3_ORDEM automática** |
| **six** (índices) | `alias`*, `ordem`*, `chave`*, `descricao`, `f3`, `nickname`, `showpesq` | `ordem='1'`, `showpesq='N'` |
| **sx6** (params MV_*) | `var`*, `tipo`, `conteudo`, `descric`, `desc1`, `desc2`, `valid`, `init` | `tipo='C'`, filial global; **insert-only** |
| **sx7** (gatilhos) | `campo`*, `sequenc`, `regra`, `cdomin`, `tipo`, `seek`, `xalias`, `xordem`, `xchave`, `condic` | `sequenc='001'`, `tipo='P'`, `seek='N'`; marca X3_TRIGGER='S' na origem |
| **sx1** (perguntas) | `grupo`*, `ordem`*, `pergunta`*, `variavel`, `tipo`, `tamanho`, `valid`, `f3`, `help`, `opcoes:[{var,def,cnt}]` (até 5) | `tipo='C'`; **insert-only** |
| **sxa** (pastas) | `alias`*, `ordem`*, `descricao`, `agrup`, `tipo` | `ordem='01'`; **insert-only** |
| **sx5** (tabelas genéricas) | `tabela`*, `chave`*, `descricao` | filial global; **insert-only** |

`*` = obrigatório (a validação bloqueia a emissão se faltar).

### Regras importantes

- **SIX:** a `chave` do índice **deve começar por `ALIAS_FILIAL`** (ex.: `ZXX_FILIAL+ZXX_COD`). Índice que não filtra por filial vaza dados entre filiais — a validação bloqueia.
- **SX3 é insert-only:** só cria campo que ainda não existe; o **X3_ORDEM é calculado em runtime** (sequência por alias). Não altera campo existente.
- **SX6 é insert-only:** respeita valores existentes — só insere o parâmetro quando a chave `X6_FIL+X6_VAR` não existe; nunca sobrescreve conteúdo de um MV já cadastrado.
- **SX7** marca `X3_TRIGGER='S'` no campo de origem (se ele existir no SX3). Gatilho sobre campo fora do spec → warning (pode pré-existir).
- O programa roda em **modo EXCLUSIVO + backup primeiro** (`MyOpenSM0`/`RpcSetEnv`/`X31UpdTable`). Aplique fora do horário produtivo.

## Execução

```bash
# spec em arquivo:
uvx plugadvpl@0.43.0 gen-aplicador-sx --spec spec.json --out a099999.prw

# spec via stdin:
echo '{"numero":"099999","sx6":[{"var":"MV_XEXMPL","tipo":"L","conteudo":".T."}]}' \
  | uvx plugadvpl@0.43.0 gen-aplicador-sx --spec - --out a099999.prw
```

`--spec <arquivo.json>` (ou `-` pra ler do stdin). `--out a<numero>.prw` grava em **cp1252**; sem `--out`, imprime o `.prw` no stdout. Validação inválida → exit ≠ 0 + `erro:` no stderr.

## Para agente IA

- O `.prw` gerado **confere SÍMBOLO, não SENTIDO**: a validação garante chaves obrigatórias, limites de tamanho e a regra `ALIAS_FILIAL` do índice — **não** garante que a regra de negócio (X3_VALID, X3_WHEN, X7_REGRA, conteúdo do MV) esteja correta. **Confirme as regras no fonte / no dicionário existente** antes de aplicar.
- Antes de rodar: garanta **modo EXCLUSIVO + backup** do ambiente (o aplicador faz backup, mas a janela exclusiva é responsabilidade da operação).
- Para montar o spec a partir de um dicionário existente, cruze com [[advpl-dicionario-sx]] (campos válidos por tipo) e [[plugadvpl-index-usage]] (consultar SX2/SX3/SX6 indexados).
