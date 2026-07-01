# Aplicador de SXs — gerador determinístico de update de dicionário (design)

> **Status:** design aprovado (aguardando review). **Data:** 2026-06-16.
> **Terminologia:** chamamos de **"aplicador de SXs"** — um programa ADVPL que aplica
> alterações de dicionário (SX/SIX) num ambiente, em **modo exclusivo**. Não usar outro nome.

## 1. Motivação

Hoje, quando o `advpl-code-generator` precisa criar uma customização de dicionário (um campo
novo, uma tabela, um parâmetro `MV_*`), a tendência do modelo é gerar um `RecLock("SX3",.T.)`
ingênuo. Isso **só grava o metadado** no dicionário — **a coluna não passa a existir na tabela
física** do banco, e não há controle de modo exclusivo, ordem de campo, ou aplicação física
(`ALTER TABLE`). O resultado é frágil e frequentemente quebra em produção.

O **aplicador de SXs** é o jeito correto: um `.prw` que (a) roda em **modo exclusivo**, (b) grava
os dicionários com a semântica certa de cada SX, e (c) **materializa as mudanças na tabela física**
via `X31UpdTable`. A estrutura desse `.prw` é sempre a mesma (boilerplate idêntico); só os dados do
dicionário mudam.

## 2. Objetivos / Não-objetivos

**Objetivos**
- Gerar um `.prw` **estruturalmente idêntico** a cada execução (boilerplate byte-estável) — nunca
  introduzir variação que cause erro de compilação/execução.
- Cobrir os **8 dicionários**: SX2 (tabelas), SX3 (campos), SIX (índices), SX6 (parâmetros),
  SX7 (gatilhos), SX1 (perguntas), SXA (pastas), SX5 (tabelas genéricas).
- Determinismo: mesmo spec → bytes idênticos (testável por snapshot).
- Conhecer **cada campo** de cada SX (tipo, tamanho, default, obrigatoriedade) — codificado em
  `schema.py` e ensinado na skill.

**Não-objetivos (YAGNI)**
- Não gerar a partir de um diff de dois dumps de SX (v2, se houver demanda).
- Não aplicar o dicionário pelo próprio CLI (o CLI **emite** o `.prw`; quem aplica é o Protheus).
- Não embutir LLM no core (a tese: determinismo no código; o agente só monta o spec).

## 3. Arquitetura

```
pedido em linguagem natural
        │  (agente advpl-code-generator + skill aplicador-sx)
        ▼
   spec.json   ── o QUE aplicar (tabelas/campos/params/gatilhos/perguntas/pastas)
        │  plugadvpl gen-aplicador-sx --spec spec.json --out a099999.prw
        ▼  (Python, DETERMINÍSTICO: valida → emite)
   a099999.prw  =  BOILERPLATE FIXO (byte-estável)  +  FSAtu* gerados do spec
```

Quatro peças:

1. **Emissor determinístico** (`cli/plugadvpl/aplicador_sx/`): valida o spec e emite o `.prw`.
2. **Comando** `gen-aplicador-sx` (handler fino em `cli.py`).
3. **Skill de conhecimento** `aplicador-sx`: conceito + cada campo de cada SX + como montar o spec.
4. **Integração** no agente `advpl-code-generator`: monta o spec e chama o gerador no lugar do RecLock.

## 4. Garantia de "estrutura idêntica pra nunca dar erro"

1. **Boilerplate = template fixo** empacotado (`boilerplate.prw.tmpl`). O modelo nunca o reescreve;
   o emissor só substitui slots (`{numero}`, `{fsatu_calls}`, `{regua}`, `{fsatu_bodies}`).
2. **`FSAtu*` = código-molde por tipo**: o `aEstrut` e o laço de insert/update são **constantes**;
   só as linhas `aAdd(aSXn, {...})` (dados) variam.
3. **Validação do schema antes de emitir**: campo obrigatório ausente, tipo errado, tamanho
   estourado → erro com mensagem clara, **nunca emite** `.prw` inválido.
4. **Determinismo**: ordenação estável das entradas, sem data/random embutidos → reprodutível,
   travado por snapshot golden.
5. **Valores dependentes do ambiente-alvo são resolvidos em RUNTIME no ADVPL gerado, não pelo
   emissor.** A próxima ordem livre do campo (`X3_ORDEM`) e o sufixo de empresa no `X2_ARQUIVO`
   dependem do dicionário/empresa do ambiente onde o `.prw` roda — então o **código ADVPL gerado**
   os calcula em execução (`dbSeek` da última ordem, `cEmpAnt` etc.). O emissor Python **nunca**
   lê estado de dicionário; por isso `spec.json → bytes idênticos` continua valendo.

## 5. Schema do spec (entrada)

JSON com `numero` (id do update) + uma chave por dicionário (todas opcionais; emite só as que vierem).
O usuário/agente preenche **apenas o dado**; o emissor preenche todas as posições do array com
defaults seguros.

```jsonc
{
  "numero": "099999",
  "sx2": [ { "alias": "ZXX", "nome": "Cadastro X", "modo": "E",
             "unico": "ZXX_FILIAL+ZXX_COD", "rotina": "" } ],
  "sx3": [ { "alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6,
             "titulo": "Codigo", "usado": "todos", "f3": "", "trigger": false } ],
  "six": [ { "alias": "ZXX", "ordem": "1", "chave": "ZXX_FILIAL+ZXX_COD",
             "descricao": "Filial + Codigo", "showpesq": false } ],
  "sx6": [ { "var": "MV_XCUST1", "tipo": "C", "conteudo": "1", "descric": "Desc" } ],
  "sx7": [ { "campo": "ZXX_COD", "regra": "...", "cdomin": "ZXX_DESC", "tipo": "P" } ],
  "sx1": [ { "grupo": "ZXX01", "ordem": "01", "pergunta": "Filtro?", "variavel": "MV_PAR01",
             "tipo": "C", "tamanho": 6 } ],
  "sxa": [ { "alias": "ZXX", "ordem": "01", "descricao": "Dados" } ],
  "sx5": [ { "tabela": "ZX", "chave": "001", "descricao": "Opcao 1" } ]
}
```

## 6. Cobertura dos 8 dicionários (os campos — codificados em `schema.py`)

Cada SX tem um array com posições fixas. O emissor preenche **todas**; o spec informa as poucas
que importam. Defaults seguros entre `[ ]`.

- **SX2 (tabelas) — 20 col**: `X2_CHAVE, X2_PATH, X2_ARQUIVO, X2_NOME, X2_NOMESPA, X2_NOMEENG,
  X2_MODO[E], X2_TTS, X2_ROTINA, X2_PYME, X2_UNICO, X2_DISPLAY, X2_SYSOBJ, X2_USROBJ, X2_POSLGT,
  X2_CLOB, X2_AUTREC, X2_MODOEMP[E], X2_MODOUN[E], X2_MODULO[0]`. Insert; update parcial só de
  `X2_ROTINA/X2_UNICO/X2_DISPLAY/X2_SYSOBJ/X2_USROBJ/X2_POSLGT`. `X2_ARQUIVO` recebe sufixo de empresa.
- **SX3 (campos) — 46 col**: `X3_ARQUIVO, X3_ORDEM, X3_CAMPO, X3_TIPO, X3_TAMANHO, X3_DECIMAL,
  X3_TITULO/TITSPA/TITENG, X3_DESCRIC/DESCSPA/DESCENG, X3_PICTURE, X3_VALID, X3_USADO, X3_RELACAO,
  X3_F3, X3_NIVEL, X3_RESERV[xxxxxx x], X3_CHECK, X3_TRIGGER, X3_PROPRI[U], X3_BROWSE, X3_VISUAL[A],
  X3_CONTEXT[R], X3_OBRIGAT, X3_VLDUSER, X3_CBOX/CBOXSPA/CBOXENG, X3_PICTVAR, X3_WHEN, X3_INIBRW,
  X3_GRPSXG, X3_FOLDER, X3_CONDSQL, X3_CHKSQL, X3_IDXSRV, X3_ORTOGRA[N], X3_TELA, X3_POSLGT,
  X3_IDXFLD[N], X3_AGRUP, X3_MODAL, X3_PYME`. **Só insert** (nunca atualiza existente). `X3_ORDEM`
  calculado automaticamente (próxima ordem livre do alias). Se `X3_GRPSXG` setado, tamanho vem do SXG.
  `X3_USADO` = máscara de 256 (emissor expande `"todos"` na máscara padrão). `X3_PROPRI='U'` sempre.
- **SIX (índices) — 10 col**: `INDICE, ORDEM, CHAVE, DESCRICAO/DESCSPA/DESCENG, PROPRI[U], F3,
  NICKNAME, SHOWPESQ[N]`. Insert/update; se a chave mudou, drop físico `TcInternal(60,...)`.
  Regra: 1ª ordem = `'1'`; chave começa por `ALIAS_FILIAL`.
- **SX6 (parâmetros) — 22 col**: `X6_FIL['  '], X6_VAR, X6_TIPO, X6_DESCRIC/DSCSPA/DSCENG,
  X6_DESC1/DSCSPA1/DSCENG1, X6_DESC2/DSCSPA2/DSCENG2, X6_CONTEUD/CONTSPA/CONTENG, X6_PROPRI,
  X6_VALID, X6_INIT, X6_DEFPOR/DEFSPA/DEFENG, X6_PYME`. **Só insert** (respeita valor já
  customizado no ambiente). Descrição longa quebra em `DESCRIC/DESC1/DESC2` (~50 chars cada).
- **SX7 (gatilhos) — 11 col**: `X7_CAMPO, X7_SEQUENC, X7_REGRA, X7_CDOMIN, X7_TIPO, X7_SEEK,
  X7_ALIAS, X7_ORDEM, X7_CHAVE, X7_PROPRI, X7_CONDIC`. Insert checando que `X7_CAMPO` existe no SX3.
- **SX1 (perguntas) — 43 col** (a aproximação some quando o bloco repetido `X1_VAR01..05` +
  `DEF/DEFSPA/DEFENG/CNT` por opção é contado): `X1_GRUPO, X1_ORDEM, X1_PERGUNT/PERSPA/PERENG, X1_VARIAVL,
  X1_TIPO, X1_TAMANHO, X1_DECIMAL, X1_PRESEL, X1_GSC, X1_VALID, (X1_VAR01..05 + DEF + DEFSPA +
  DEFENG + CNT por opção), X1_F3, X1_PYME, X1_GRPSXG, X1_HELP, X1_PICTURE, X1_IDFIL`. Insert por
  `grupo+ordem`.
- **SXA (pastas/abas) — 8 col**: `XA_ALIAS, XA_ORDEM, XA_DESCRIC/DESCSPA/DESCENG, XA_AGRUP,
  XA_TIPO, XA_PROPRI`. Insert.
- **SX5 (tabelas genéricas) — 6 col**: `X5_FILIAL, X5_TABELA, X5_CHAVE, X5_DESCRI/DESCSPA/DESCENG`.
  Insert.

> A lista completa de defaults, tamanhos e validações por campo vive em `schema.py` (fonte da
> verdade em código) e é documentada em prosa na skill `aplicador-sx`.

## 7. Boilerplate (template fixo, sanitizado)

13 funções idênticas em todo aplicador, extraídas **sanitizadas** (sem nada de cliente) de um
exemplo canônico:

- `User Function A<numero>(cEmpAmb, cFilAmb)` — `FormBatch` avisando "rode em **modo EXCLUSIVO** +
  faça **BACKUP**"; checa `MPDicInDB()` (recusa ISAM); modo interativo (seleção de empresas) vs
  automático (RPC).
- `FSTProc()` — por empresa: `RpcSetEnv` → chama os `FSAtu*` ativos → `__SetX31Mode(.F.)` +
  loop `X31UpdTable(alias)` (ALTER TABLE físico). `SetRegua1(N)` = nº real de seções.
- `FSAtuSX2/SX3/SIX/SX6/SX7/SX1/SXA/SX5()` — geradas (estrutura fixa + dados do spec).
- `FSAtuHlp()` — helps de campo. **Na v1 é emitida fixa e vazia** (não é seção do spec); helps de
  campo ficam para v2. É o que os exemplos fazem na esmagadora maioria.
- Boilerplate puro (copiado idêntico): `EscEmpresa, MarcaTodos, InvSelecao, RetSelecao, MarcaMas,
  VerTodos, MyOpenSM0` (abertura exclusiva do SM0), `LeLog`.

## 8. Componentes / arquivos

- `cli/plugadvpl/aplicador_sx/__init__.py`
- `cli/plugadvpl/aplicador_sx/schema.py` — schema + validação por campo (cada SX).
- `cli/plugadvpl/aplicador_sx/emit.py` — monta cada `FSAtu*` + assembla o `.prw`.
- `cli/plugadvpl/aplicador_sx/boilerplate.prw.tmpl` — template fixo (force-included no wheel, mesmo
  mecanismo do `coletadb.tlpp`).
- `@app.command("gen-aplicador-sx")` em `cli.py` (fino: lê spec de `--spec`/stdin, chama o emissor,
  escreve `--out` em cp1252 ou stdout).
- `skills/aplicador-sx/SKILL.md` — knowledge skill (ripple de contagem de skills 72→73).
- catálogo/agent: passo no `advpl-code-generator` para usar o gerador.

## 9. Tratamento de erros

Validação **antes** de emitir, com mensagem acionável: campo obrigatório ausente, tipo inválido,
tamanho estourado, alias/campo fora do padrão (ex.: campo deve ser `ALIAS_NOME`), índice sem
`ALIAS_FILIAL` na chave. Nunca emite `.prw` parcial/inválido — ou valida tudo, ou falha com o motivo.

**SX7 — gatilho sobre campo fora do spec é WARNING, não erro.** É legítimo criar um gatilho sobre
um campo que já existe no ambiente-alvo (não está sendo criado neste run). Então, se o `X7_CAMPO`
não estiver em nenhum SX3 do spec, o emissor **avisa** (pode ser campo pré-existente) mas **emite** —
não bloqueia.

## 10. Encoding

Saída em **cp1252** (`.prw` clássico). O emissor escreve cp1252 byte-a-byte; determinístico
(sem BOM, sem CRLF inconsistente — define a política e trava no snapshot).

## 11. Testes (TDD)

1. **Schema** (unit): cada SX — obrigatórios, limites de tamanho, defaults, rejeições.
2. **Emit por tipo** (unit): dada uma entrada do spec → linha(s) `aAdd` esperada(s).
3. **Snapshot golden**: um spec completo (todos os 8 tipos, sintético `ZXX`) → `.prw` byte-estável.
   É o teste que trava "estrutura idêntica".
4. **Determinismo**: emitir 2× o mesmo spec → bytes idênticos.
5. **Lint do próprio plugadvpl**: o `.prw` emitido parseia (`parse_source`) e passa no `lint`
   **com as categorias BP/SEC suprimidas de propósito** — o boilerplate usa, legitimamente, padrões
   que o lint sinaliza (ex.: `RpcSetEnv` num update batch dispara SEC-001, que só faz sentido em REST;
   `Then`/escopo do boilerplate fixo). A supressão é intencional e documentada aqui pra ninguém
   "consertar" e quebrar o golden. O ciclo ainda fecha: o gerador respeita PERF/SQL/MOD.

## 12. Confidencialidade (inegociável)

- Boilerplate e exemplos da skill **100% sintéticos** (`ZXX`, `MV_X*`) — zero nome/e-mail/path/
  prefixo de cliente.
- O material de referência recebido (um guia + uma pasta de exemplos com código de cliente) é
  mantido **fora do git** — serve só para extrair o padrão localmente, nunca é commitado.
- Nada que entre no repo (spec, skill, template, fixtures, snapshot) pode conter dado de cliente.

## 13. Faseamento da implementação

Uma feature coesa; o plano implementa em fases incrementais sob TDD:

1. **Espinha**: schema + emit do boilerplate + SX3 (campo) + comando + snapshot golden mínimo.
2. **Criação de tabela**: SX2 + SIX (fecha o caso "tabela do zero").
3. **Demais dicionários**: SX6, SX7, SX1, SXA, SX5.
4. **Skill** `aplicador-sx` + integração no `advpl-code-generator` + ripple de contagem.

Cada fase: RED→GREEN, snapshot atualizado, `.prw` emitido passa no lint.

## 14. Riscos / questões abertas

- **Boilerplate sanitizado fiel**: extrair o boilerplate sem dado de cliente e garantir que ainda
  compila. Mitigação: revisar token a token; snapshot trava o resultado.
- **`X3_USADO` (máscara de 256)**: o emissor precisa de presets (`"todos"`, lista de módulos).
  Mitigação: começar com `"todos"` e um conjunto pequeno de presets.
- **Variações de boilerplate** entre exemplos: escolher **um** canônico e padronizar (não tentar
  suportar todas as variações observadas).
