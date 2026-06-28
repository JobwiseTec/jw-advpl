---
description: Dicionário SX do Protheus — SX1 (perguntas), SX2 (tabelas), SX3 (campos), SX5 (tabelas genéricas), SX6 (parâmetros MV_*), SX7 (gatilhos), SX8 (numeração sequencial), SX9 (relacionamentos), SXA (pastas/folders), SXB (consultas F3), SXG (grupos de campo), SIX (índices). Use ao criar campo/parâmetro/gatilho/consulta, customizar via dicionário, ou diagnosticar comportamento controlado pelo SX. Para análise cruzada com fontes, use /plugadvpl:impacto e /plugadvpl:gatilho.
---

# advpl-dicionario-sx — Dicionário de dados Protheus

O **Dicionário SX** é o conjunto de tabelas de metadados que controlam estrutura, apresentação, validação e comportamento de tudo no Protheus. **Parte do código-fonte do Protheus está no dicionário** — alterar SX3, SX7, SXB muda comportamento sem recompilar.

A partir da **v0.3.0 do plugadvpl** (Universo 2), o dicionário SX é ingerido via `/plugadvpl:ingest-sx <pasta-csv>` e cruzado com fontes via `/plugadvpl:impacto <campo>` (killer feature). Veja `[[advpl-dicionario-sx-validacoes]]` pra detalhes das expressões ADVPL embutidas em `X3_VALID`/`X7_REGRA`/`X1_VALID`.

## Quando usar

- Usuário pede para "criar campo", "adicionar parâmetro `MV_*`", "criar gatilho", "criar pergunta", "criar consulta F3", "F3 lookup".
- Investigar por que um campo aparece/desaparece (provavelmente `X3_USADO`/`X3_WHEN`).
- Customizar comportamento sem mexer em fonte (preferir SX a PE quando possível).
- Diagnose "campo custom não aparece no cadastro" — checar `X3_USADO`, `X3_FOLDER`, browse default.
- Análise de impacto: `/plugadvpl:impacto A1_COD` cruza referências do campo em fontes + SX3 + SX7 + SX1.

## Mapa das tabelas SX

| Tabela | Função                                     | Tabela no plugadvpl (após `ingest-sx`) | Cardinalidade típica  |
|--------|---------------------------------------------|----------------------------------------|------------------------|
| SX1    | Perguntas (`Pergunte`/`ParamBox`)           | `perguntas`                            | ~10k+ por instalação   |
| SX2    | Mapeamento físico de arquivos (X2_CHAVE)    | `tabelas`                              | ~1500 tabelas oficiais |
| SX3    | Campos de tabelas (estrutura + UI + regras) | `campos`                               | ~80k campos            |
| SX5    | Tabelas genéricas (códigos auxiliares)      | `tabelas_genericas`                    | ~5k registros          |
| SX6    | Parâmetros `MV_*` (configuração)            | `parametros`                           | ~3k parâmetros         |
| SX7    | Gatilhos de campo                           | `gatilhos`                             | ~10k gatilhos          |
| SX8    | Reserva de numeração sequencial             | (runtime, não ingestado)               | runtime                |
| SX9    | Relacionamentos entre entidades             | `relacionamentos`                      | ~20k                   |
| SXA    | Pastas (folders) de cadastro                | `pastas`                               | ~500                   |
| SXB    | Consultas padrão F3                         | `consultas`                            | ~2k                    |
| SXG    | Grupos de tamanho/template de campo         | `grupos_campo`                         | ~500                   |
| SIX    | Índices físicos das tabelas                 | `indices`                              | ~5k índices            |

## SX3 — Campos (o mais importante)

```
X3_ARQUIVO  Tabela (ex: SA1)
X3_CAMPO    Nome (A1_COD)
X3_TIPO     C/N/D/M/L (character/numeric/date/memo/logical)
X3_TAMANHO  Tamanho
X3_DECIMAL  Casas decimais
X3_TITULO   Título da coluna (PT)
X3_DESCRIC  Descrição estendida
X3_PICTURE  Máscara (`@!`, `@E 999,999.99`)
X3_VALID    Expressão de validação (`U_XYZVAL()`, `NaoVazio()`, etc.)
X3_INIT     Inicializador (`Space(10)`, `CToD("")`, `U_XYZINIT()`)
X3_WHEN     Habilitação condicional
X3_VLDUSER  Validação adicional (user-level)
X3_USADO    varchar(120) — bitmap por módulo/segmento do ERP (FAT/EST/FIN/...). NÃO é empresa/filial. Use X3Uso()/X3TreatUso().
X3_BROWSE   Aparece em browse? (S/N)
X3_RELACAO  Default/fórmula
X3_F3       Consulta padrão (referência à SXB)
X3_TRIGGER  varchar(1): "S" se possui gatilho SX7; vazio = não
X3_FOLDER   varchar(1) — aba SXA onde aparece (casa com XA_ORDEM)
X3_OBRIGAT  varchar(8) — bitmap controlado por API (v12.1.7+ usa X3TreatObrigat). Setar "S" via SQL direto é IGNORADO.
X3_PROPRI   U=User custom / S=System TOTVS
X3_GRPSXG   varchar(3) — grupo SXG (template de tamanho). NB: docs antigos chamam de X3_GRUPO — coluna física é x3_grpsxg.
X3_NIVEL    Nível de acesso (visibilidade)
```

### Customizando campo sem mexer no fonte

- **Esconder**: `X3_BROWSE='N'`, `X3_NIVEL` baixo, ou apagar bit de módulo em `X3_USADO` **via API** (`FwPutSX3()`/Configurador — não SQL direto, é bitmap de ~113-117 chars).
- **Tornar opcional**: `X3_OBRIGAT=''` (já é o default de quase todos os campos). **Tornar obrigatório**: prefira `X3_VALID := "!Empty(M->CAMPO)"` — atribuir `"S"` em `X3_OBRIGAT` via SQL direto é silenciosamente ignorado em v12.1.7+ (campo é bitmap controlado por API).

### Criar campo SX3 via SQL (cookbook)

Pra scriptar criação de campo custom (pipeline/CI, ambiente sem GUI) — quando `FwPutSX3()`/Configurador não couberem no workflow — ver [`reference.md` §15](reference.md): regra de ouro (clonar bitmaps via subselect), workflow 3-fases (ALTER + INSERT + cache invalidation), checklist pré-INSERT, armadilhas frequentes.
- **Validação custom**: `X3_VALID := "U_XYZVAL()"` — User Function deve existir nos fontes. Lint `SX-001` flagga se não.
- **Default custom**: `X3_INIT := "U_XYZDEF()"` ou `X3_RELACAO := "U_XYZDEF()"`.
- **Lookup F3**: `X3_F3 := "SA1XYZ"` — alias deve existir em SXB. Lint `SX-011` flagga se não.

Veja `[[advpl-dicionario-sx-validacoes]]` pra padrões de `X3_VALID`/`X3_INIT`/`X3_WHEN`.

## SX7 — Gatilhos

Disparam ao terminar edição de um campo, modificando outro.

```
X7_CAMPO   Campo gatilho (A1_COD)
X7_SEQUENC Sequência (01, 02, ...)
X7_REGRA   Expressão que retorna valor
X7_CDOMIN  Campo destino (A1_NOME)
X7_TIPO    P/vazio = Primário (mais comum); X = Posicionamento. Tipo "E" (Estrangeiro) NÃO existe no padrão atual.
X7_SEEK    "S" — usa DbSeek + alias na regra
X7_ALIAS   Alias-fonte (se SEEK=S)
X7_ORDEM   Ordem do índice no seek
X7_CHAVE   Expressão da chave para o seek
X7_CONDIC  Condição pra disparar (.T. default)
X7_PROPRI  U=User custom / S=System
```

Exemplo: ao digitar `A1_COD`, busca no SA1 e preenche `A1_NOME`:

```
X7_CAMPO   = A1_COD
X7_REGRA   = SA1->A1_NREDUZ
X7_CDOMIN  = A1_NOME
X7_TIPO    = P
X7_SEEK    = S
X7_ALIAS   = SA1
X7_ORDEM   = 1
X7_CHAVE   = xFilial("SA1") + M->A1_COD
```

Lint relacionado:
- `SX-002` — `X7_CDOMIN` (campo destino) não existe em `campos` (SX3).
- `SX-010` — `X7_TIPO='P'` (Pesquisar) sem `X7_SEEK='S'`.

## SX1 — Perguntas

```advpl
// Para criar pergunta via script de update:
PutSx1("XYZREL  ",;                       // grupo (8 chars padded)
       "01",;                              // ordem
       "Empresa De?",;                     // texto PT
       "Empresa De?",;                     // texto EN
       "Empresa De?",;                     // texto ES
       "mv_ch1",;                          // ID interno
       "C",;                               // tipo (C/N/D/L)
       2,;                                  // tamanho
       0,;                                  // decimal
       0,;                                  // presel
       "G",;                                // GET (G) ou CMB (C)
       "",;                                 // valid
       "mv_par01",;                         // MV_PAR identificador
       "",;                                 // F3
       "",;                                 // grupo
       "",;                                 // help
       "", "", "", "", "", "", "", "", "", ; // 9 textos cmb
       "", "", "", "", "",;                  // outros
       {}, {}, {}, "")

// Em código, ler:
Pergunte("XYZREL", .T.)   // .T. = abre dialog interativo
nValor := MV_PAR02         // valores ficam em Private MV_PAR01..MV_PAR99
```

**Recomendação TOTVS atual:** use `ParamBox()` em vez de `Pergunte` em código novo — mais rápido, passa Code Analysis, não depende de cadastro SX1. Veja `[[advpl-fundamentals]]`.

Lint relacionado:
- `SX-004` — grupo SX1 sem `Pergunte()` correspondente em fontes.

## SX6 — Parâmetros MV_*

```advpl
// Ler parametro (3 formas)
cValor := GetMV("MV_LOCPAD")                       // sem default
cValor := GetMV("MV_LOCPAD", .F., "01")            // com default "01"
cValor := SuperGetMV("MV_LOCPAD", .F., "01")       // versao recomendada (cache, multi-filial)

// Criar via PutMV (raro em runtime, mais em update sx)
PutMV("MV_XYZPAR", "valor")
```

Parâmetros são por empresa/filial. Convenção:
- **Padrão TOTVS**: `MV_*` (3-12 chars após underscore).
- **Cliente custom**: `MV_XYZ*` (prefixo cliente).

Lint relacionado:
- `SX-003` — parâmetro `MV_*` declarado mas zero referências em fonte.

## SXB — Consultas F3 (lookup)

Tipo `1` (Consulta padrão) + tipo `2` (Filtros/colunas) + tipo `3` (Itens da consulta) + tipo `4` (Validações).

```
XB_ALIAS    Identificador (ex: SA1XYZ)
XB_TIPO     1/2/3/4
XB_SEQ      Sequência
XB_COLUNA   Coluna do filtro / item
XB_DESCR1   Descrição PT
XB_DESCR2   Descrição EN
XB_DESCR3   Descrição ES
XB_CONTEM   Conteúdo (campo, condição, expressão)
XB_WCONTEM  Quando contém (filtro adicional)
```

Atribui ao campo via `X3_F3 := "SA1XYZ"`. Quando user pressiona F3 no campo, abre a consulta.

Para **consulta específica** (SXB que chama função em vez de browsear tabela por índice) e o
padrão de **F3 genérico** (uma SXB + dispatcher por `ReadVar` roteando vários campos), veja
`[[advpl-consulta-padrao]]` — inclui a estrutura de registros por `XB_TIPO` (1/2/5) e o
contrato da função (retorna lógico + grava o valor).

Lint relacionado:
- `SX-011` — `X3_F3` aponta pra alias SXB que não existe.

## SX8 — Numeração sequencial (runtime)

Numerador transacional para gerar códigos sequenciais sem colisão multi-usuário:

```advpl
// Pega proximo numero (reserva temporario)
cNum := GetSx8Num("SC5", "C5_NUM")
// Faz o RecLock e popula com cNum
RecLock("SC5", .T.)
SC5->C5_NUM := cNum
SC5->(MsUnlock())

// Confirma o numero (incrementa contador permanentemente)
ConfirmSx8()

// OU se cancelar a operacao:
RollBackSx8()    // libera o numero pra proximo cliente
```

> **Crítico:** sempre par `GetSx8Num` + `ConfirmSx8` OU `RollBackSx8`. Esquecer `ConfirmSx8` segura o número numa thread morta — próximo cliente pega outro número.

## SX9 — Relacionamentos

Define joins automáticos entre tabelas usadas em consultas standard. Raramente customizado.

## SIX — Índices

```
INDICE     Ordem (01, 02, ...)
CHAVE      Expressão da chave (FILIAL+COD)
DESCRICAO  Descrição
PROPRI     U (Único/User) ou S (Sistema)
F3         Aparece como consulta?
NICKNAME   Apelido para uso em ADVPL
SHOWPESQ   S/N — mostra no F4 (pesquisa)
```

Adicionar índice custom: `INDICE >= 21` (TOTVS usa 01-20).

## SXA — Pastas (folders de cadastro)

Define abas e seu conteúdo no cadastro MVC ou Modelo3:

```
XA_ALIAS    Tabela (SA1)
XA_ORDEM    Sequência
XA_DESCRIC  Descrição da aba (PT)
```

Campos pertencem à aba via `X3_FOLDER` (mesmo valor de `XA_ORDEM`).

## SXG — Grupos de tamanho

Templates de tamanho/picture compartilhados entre campos similares:

```
XG_GRUPO       C(3) — ID do grupo (ex: "037")
XG_DESCRI      C(30) — Descrição (PT; XG_DESCSPA/XG_DESCENG). NB: no CSV do Configurador o header costuma vir como XG_DESCRIC (legado).
XG_SIZE        N — Tamanho padrão (ex: 15). NB: no CSV do Configurador costuma vir como XG_TAMANHO.
XG_SIZEMAX     N — Tamanho máximo permitido na faixa (CSV: XG_TAMMAX)
XG_SIZEMIN     N — Tamanho mínimo permitido na faixa (CSV: XG_TAMMIN)
XG_PICTURE     C(45) — Máscara
XG_CHECK1      C(32) — Expressão de validação adicional
XG_CHECK2      C(32) — Segunda expressão de validação
(NÃO existem XG_DECIMAL nem XG_TIPO no schema físico — tipo/decimal vêm do SX3 que referencia o grupo)
```

Campos que usam o grupo: `X3_GRPSXG := "037"`.

Mudar grupo SXG = mudar tamanho de TODOS os campos do grupo de uma vez. Útil pra alinhar valores monetários em todo o ERP.

## Funções utilitárias canônicas

| Função                                  | Para que serve                                   |
|-----------------------------------------|--------------------------------------------------|
| `GetSX3Cache(cCampo, cAtr)`             | Lê SX3 cacheado (rápido)                          |
| `X3Descricao(cCampo)`                   | Atalho para X3_DESCRIC                            |
| `X3Titulo(cCampo)`                      | Atalho para X3_TITULO                             |
| `TamSX3(cCampo)`                        | Retorna `{tamanho, decimal, tipo}`                |
| `Posicione(alias, ordem, key, cmpRet)`  | Equivalente a `DbSeek` + retorno do campo         |
| `ExistChav(alias, key, ordem)`          | Confere se chave existe (boolean)                 |
| `ExistCpo(alias, key, ordem)`           | Existe + alguns checks adicionais                 |
| `GetMV(cParam, lOblig, xDef)`           | Lê SX6 (sem cache)                                |
| `SuperGetMV(cParam, lOblig, xDef, cFil)`| Lê SX6 com cache + multi-filial (recomendado)     |
| `PutMV(cParam, xValor)`                 | Grava SX6                                          |
| `Pergunte(cGrp, lAsk)`                  | Lê SX1, preenche `MV_PAR0X`                        |
| `GetSx8Num(alias, campo)`               | Reserva próximo número sequencial                  |
| `ConfirmSx8()` / `RollBackSx8()`        | Confirma ou cancela reserva                        |
| `MsExecAuto(bRot, aDados, nOpc)`        | Executa rotina padrão (usa SX3/SX7)                |
| `FwxFilial(alias)`                      | Resolve filial conforme `X2_MODO`                  |
| `FwSX3Util():GetAllFields(alias)`       | Lista todos campos de uma tabela                   |

## Anti-padrões

- **Editar SX no banco direto** (DBA) em vez de script via `PutSx3/PutSx7` → perde rastreio, não vai pra outros ambientes.
- **Campo customer sem prefixo de cliente** (`A1_CAMPO` em vez de `A1_XCAMPO` ou `A1_ZCAMPO`) → colisão em upgrade TOTVS.
- **Gatilho com `X7_REGRA` complexa inline** em vez de chamar `U_XYZxxx` → impossível debugar e versionar.
- **Parâmetro `MV_` sem documentar** (X6_DESCRIC vazia) → ninguém sabe o que faz.
- **Esquecer `X3_NIVEL`** ao criar campo confidencial → todos veem em browse.
- **Hardcode de campo** `A1_XYZ` no fonte sem checar `FieldPos("A1_XYZ") > 0` → quebra se cliente não tiver o campo (customização em cliente A, fonte em cliente B).
- **`GetSx8Num` sem `ConfirmSx8`/`RollBackSx8`** → numerador trava em thread morta.
- **`X3_VALID` chamando função restrita TOTVS** → lint `SX-007` critical.
- **`X3_VALID` com SQL embedado** (`BeginSql`/`TCQuery`) → query a cada validação, anti-performance. Lint `SX-006`.
- **Tabela compartilhada (`X2_MODO='C'`) com `xFilial` em `X3_VALID`** → inconsistência. Lint `SX-008`.

## Workflow plugadvpl (v0.3.0+)

```bash
# 1. Exporta dicionario via Configurador -> Misc -> Exportar Dicionario
#    (gera sx1.csv, sx2.csv, sx3.csv, ..., sxg.csv, six.csv)

# 2. Ingere no plugadvpl
plugadvpl ingest-sx /caminho/pra/csvs

# 3. Confere
plugadvpl sx-status
#   tabelas        rows
#   ------------- -----
#   tabelas         12
#   campos        2451
#   gatilhos       186
#   parametros     324
#   ...

# 4. Analise de impacto cross-camadas (killer feature)
plugadvpl impacto A1_COD --depth 3
#   Mostra TODA cadeia de impacto: fontes que mencionam + X3_VALID/INIT/WHEN
#   + X7_REGRA + X1_VALID que referenciam A1_COD

# 5. Cadeia de gatilhos
plugadvpl gatilho A1_COD --depth 3

# 6. Lint cross-file
plugadvpl lint --cross-file --regra SX-005     # campos custom sem refs
plugadvpl lint --cross-file                    # todas as 11 SX-* rules
```

## Cross-references com outras skills

- `[[advpl-dicionario-sx-validacoes]]` — detalhe das expressões ADVPL em X3_VALID/X3_INIT/X3_WHEN/X3_VLDUSER, X7_REGRA, X1_VALID.
- `[[advpl-fundamentals]]` — convenções de nomenclatura de campos custom (prefixo cliente).
- `[[advpl-mvc]]` / `[[advpl-mvc-avancado]]` — `FWFormStruct(1, "SA1")` lê do SX3.
- `[[advpl-pontos-entrada]]` — PE `<rotina>STRU` adiciona grid baseada em SX3 custom.
- `[[advpl-code-review]]` — lint SX-001..SX-011 cross-file rules.
- `[[advpl-embedded-sql]]` — `%table:SA1%` resolve via SX2 mapping; `SX-006` flagga SQL em X3_VALID.
- `[[advpl-debugging]]` — diagnose "campo não aparece" / "gatilho não dispara".
- `[[plugadvpl-index-usage]]` — `/plugadvpl:impacto`, `/plugadvpl:gatilho`, `/plugadvpl:sx-status`, `/plugadvpl:ingest-sx`.

## Comandos plugadvpl relacionados

- `/plugadvpl:ingest-sx <pasta-csv>` — popula as 11 tabelas SX no índice.
- `/plugadvpl:sx-status` — counts por tabela do dicionário.
- `/plugadvpl:impacto <campo>` — cruza referências em fontes ↔ SX3 ↔ SX7 ↔ SX1 (depth 1..3).
- `/plugadvpl:gatilho <campo>` — cadeia BFS de gatilhos SX7.
- `/plugadvpl:tables <T>` — lista campos da tabela vinda do SX3 indexado.
- `/plugadvpl:param <MV_*>` — descobre uso de parâmetro no projeto.
- `/plugadvpl:find function PutSx3` — scripts de manipulação SX.
- `/plugadvpl:lint --cross-file` — roda as 11 regras SX-001..SX-011.

## Referência profunda

Para detalhes completos (~1.6k linhas), consulte [`reference.md`](reference.md) ao lado deste arquivo:

- Esquema completo de **toda** SX (cada coluna documentada).
- Catálogo de `X3_PICTURE` (formatos `@!`, `@R`, `@E`, máscaras numéricas/data).
- Bitmap `X3_USADO` por contexto e como manipular.
- Fluxo de execução de gatilho (SX7) com encadeamento e short-circuit.
- Convenções para customização: campos reais × virtuais, contexto compartilhado × exclusivo.
- Procedimentos para upgrade-safe modifications.

## Sources

- [Dicionário de Dados SX - TDN](https://tdn.totvs.com/display/public/framework/Dicionario+de+Dados+SX)
- [PutSx3 - Frameworksp - TDN](https://tdn.totvs.com/display/framework/PutSx3)
- [Manipular SX1 (Pergunte) - TOTVS Central](https://centraldeatendimento.totvs.com/hc/pt-br/articles/8188934752535)
- [Cross Segmentos Dicionário SX - TOTVS Central](https://centraldeatendimento.totvs.com/hc/pt-br/articles/360018402211)
- [Função GetSx8Num - Tudo em AdvPL](https://siga0984.wordpress.com/tag/getsx8num/)
- [Padrões de migração e atualização SX - Terminal de Informação](https://terminaldeinformacao.com/)
