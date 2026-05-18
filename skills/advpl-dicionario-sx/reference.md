# Dicionário de Dados – Estrutura SX do Protheus

> Documentação técnica completa sobre as tabelas SX do dicionário de dados do ERP Protheus (TOTVS).
> Baseada em fontes oficiais: TDN TOTVS, forum.totvs.io, ProtheusAdvpl, Terminal de Informação.

---

## Sumário

1. [Visão Geral do Dicionário de Dados](#1-visão-geral-do-dicionário-de-dados)
   - [O que é o dicionário de dados](#o-que-é-o-dicionário-de-dados)
   - [Por que centralizar metadados](#por-que-centralizar-metadados)
   - [Como o sistema usa o dicionário](#como-o-sistema-usa-o-dicionário)
   - [Mapa completo da família SX](#mapa-completo-da-família-sx)
2. [SX1 — Perguntas do Usuário](#2-sx1--perguntas-do-usuário)
3. [SX2 — Mapeamento de Arquivos](#3-sx2--mapeamento-de-arquivos)
4. [SX3 — Campos das Tabelas](#4-sx3--campos-das-tabelas)
   - [Campos de identificação e estrutura](#41-campos-de-identificação-e-estrutura)
   - [Campos de apresentação](#42-campos-de-apresentação)
   - [Campos de comportamento](#43-campos-de-comportamento)
   - [X3_VALID — Validação de campo](#44-x3_valid--validação-de-campo)
   - [X3_WHEN — Habilitação condicional](#45-x3_when--habilitação-condicional)
   - [X3_TRIGGER — Gatilhos](#46-x3_trigger--gatilhos)
   - [Consultas F3 via X3_F3](#47-consultas-f3-via-x3_f3)
   - [Array interno da SX3 em ADVPL](#48-array-interno-da-sx3-em-advpl)
5. [SX5 — Tabelas Genéricas](#5-sx5--tabelas-genéricas)
6. [SX6 — Parâmetros MV_](#6-sx6--parâmetros-mv_)
7. [SX7 — Gatilhos de Campos](#7-sx7--gatilhos-de-campos)
   - [Tipos de gatilho](#71-tipos-de-gatilho)
   - [Campos da SX7](#72-campos-da-sx7)
   - [Fluxo de execução de um gatilho](#73-fluxo-de-execução-de-um-gatilho)
   - [Encadeamento de gatilhos](#74-encadeamento-de-gatilhos)
   - [Exemplo real de gatilho](#75-exemplo-real-de-gatilho)
8. [SX8 — Reserva de Numeração](#8-sx8--reserva-de-numeração)
9. [SX9 — Relacionamentos entre Entidades](#9-sx9--relacionamentos-entre-entidades)
10. [SXB — Consultas Padrão (F3)](#10-sxb--consultas-padrão-f3)
    - [Tipos de registro na SXB](#101-tipos-de-registro-na-sxb)
    - [Criando uma consulta F3](#102-criando-uma-consulta-f3-personalizada)
11. [SXE e SXF — Controle de Numeração Sequencial](#11-sxe-e-sxf--controle-de-numeração-sequencial)
12. [SIX — Índices dos Arquivos](#12-six--índices-dos-arquivos)
13. [SXA — Pastas e Agrupamentos de Campos](#13-sxa--pastas-e-agrupamentos-de-campos)
14. [Funções ADVPL Relacionadas ao Dicionário](#14-funções-advpl-relacionadas-ao-dicionário)
    - [GetSX3Cache e X3Descricao](#141-getsx3cache-e-x3descricao)
    - [Posicione](#142-posicione)
    - [ExecAuto e MsExecAuto](#143-execauto-e-msexecauto)
    - [FWMGetDef](#144-fwmgetdef)
    - [FieldPos, FieldGet, FieldPut](#145-fieldpos-fieldget-fieldput)
    - [Funções de SX5](#146-funções-de-sx5)
    - [Funções de SX6](#147-funções-de-sx6)
    - [Funções de SX7 e SX8](#148-funções-de-sx7-e-sx8)
15. [Customização via Dicionário](#15-customização-via-dicionário)
    - [Campos reais vs. virtuais](#151-campos-reais-vs-virtuais)
    - [Contexto compartilhado vs. exclusivo](#152-contexto-compartilhado-vs-exclusivo)
    - [Convenções de nomenclatura](#153-convenções-de-nomenclatura)
    - [Boas práticas](#154-boas-práticas)

---

## 1. Visão Geral do Dicionário de Dados

### O que é o dicionário de dados

O Microsiga Protheus possui um conjunto de tabelas especiais que definem a organização básica de todos os dados do sistema. A esse conjunto de tabelas chamamos de **Dicionário de Dados**. Ele armazena metainformações como:

- Estrutura física das tabelas (quais campos existem e seus tipos)
- Propriedades de apresentação na interface (títulos, máscaras, ordem nas telas)
- Regras de validação, habilitação e disparo automático
- Parâmetros de configuração do sistema
- Consultas de pesquisa (F3)
- Relacionamentos entre entidades
- Controle de numeração sequencial

O dicionário reside no diretório `\SYSTEM\` da instalação do Protheus e é compartilhado por todas as instâncias da aplicação. Pode-se afirmar que **parte do código-fonte do Protheus encontra-se na forma de Dicionário de Dados**.

### Por que centralizar metadados

Centralizar metadados no dicionário traz vantagens fundamentais:

- **Flexibilidade sem recompilação:** ao alterar o dicionário, a mudança entra em vigor imediatamente. O SX3 é considerado "ativo" — nenhum fonte precisa ser recompilado.
- **Separação de responsabilidades:** regras de negócio ficam no dicionário, não espalhadas por centenas de fontes.
- **Customização segura:** é possível adicionar campos, validações e gatilhos sem modificar os fontes TOTVS originais.
- **Suporte a múltiplos bancos:** o TopConnect usa o dicionário para mapear campos para Oracle, SQL Server, MySQL e outros bancos. Inclusões e alterações na SX3 são sincronizadas automaticamente para o banco relacional.

### Como o sistema usa o dicionário

Quando um usuário acessa uma rotina pela primeira vez:

1. O Protheus lê a **SX2** para descobrir as tabelas necessárias e seu modo de acesso.
2. Lê a **SX3** para obter a estrutura de campos (tipo, tamanho, título, validações).
3. Lê a **SX7** para carregar os gatilhos associados aos campos.
4. Lê a **SXB** para disponibilizar as consultas F3.
5. Lê a **SX6** para obter parâmetros de configuração.
6. Lê a **SX9** para verificar relacionamentos e integridade referencial.

Todas essas leituras são cacheadas internamente para performance.

### Mapa completo da família SX

| Tabela | Descrição |
|--------|-----------|
| **SX1** | Perguntas de parametrização (relatórios e processos) |
| **SX2** | Mapeamento de arquivos/tabelas |
| **SX3** | Dicionário de campos das tabelas |
| **SX4** | Configuração de agenda de relatórios e processos |
| **SX5** | Tabelas genéricas de domínio |
| **SX6** | Parâmetros MV_ do sistema |
| **SX7** | Gatilhos de campos |
| **SX8** | Reserva de numeração sequencial (controle transacional) |
| **SX9** | Relacionamentos entre arquivos |
| **SXA** | Pastas e agrupamentos de campos |
| **SXB** | Consultas padrão (LookUps / F3) |
| **SXD** | Cadastro de relatórios e processos para agendamento |
| **SXE** | Controle de numeração — próximo número + 1 |
| **SXF** | Controle de numeração — último número sequencial + 1 |
| **SXG** | Configuração padrão para grupo de campos |
| **SXH** | Tabela de eventos do sistema |
| **SXI** | Inscrição para acesso a eventos |
| **SIX** | Índices dos arquivos |

---

## 2. SX1 — Perguntas do Usuário

### O que é a SX1

A tabela **SX1** define de forma padronizada a interface de perguntas (ou parâmetros de entrada) exibidas ao usuário antes da execução de relatórios e processos. Cada conjunto de perguntas é chamado de **grupo de perguntas**, identificado por `X1_GRUPO`.

Exemplos de uso: filtros de período (data de/até), filtros de código (produto de/até), opções de impressão (resumido/detalhado).

### Campos da SX1

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `X1_GRUPO` | C(10) | Identificador do grupo de perguntas (ex: `"REL001"`) |
| `X1_ORDEM` | C(2) | Ordem de exibição dentro do grupo (`"01"`, `"02"`, ...) |
| `X1_PERGUNT` | C(30) | Texto da pergunta em português |
| `X1_PERSPA` | C(30) | Texto da pergunta em espanhol |
| `X1_PERENG` | C(30) | Texto da pergunta em inglês |
| `X1_VARIAVL` | C(6) | Variável de memória associada |
| `X1_TIPO` | C(1) | Tipo do campo: `C`=Caractere, `N`=Numérico, `D`=Data, `L`=Lógico, `M`=Memo |
| `X1_TAMANHO` | N | Tamanho do campo de resposta |
| `X1_DECIMAL` | N | Casas decimais (para tipo `N`) |
| `X1_PRESEL` | **N** | Pré-seleção para combos — **coluna é numérica** (`double precision`). Em SQL direto use número, não string: `x1_presel = 1`, não `'01'`. ADVPL coerce mas o banco rejeita. |
| `X1_GSC` | C(1) | Tipo de input — valores observados: `G`=Get (input livre, mais comum), `C`=Combo (dropdown), `R`=Range/Radio (segundo mais usado depois de G/C), `S`, `F`=File, `E`, `K`. |
| `X1_VALID` | C(160) | Expressão de validação ADVPL |
| `X1_F3` | C(6) | Consulta F3 disponível para o campo |
| `X1_VAR01`..`X1_VAR05` | C(15) | Variáveis MV_PAR correspondentes (`MV_PAR01`..`MV_PAR05`) |
| `X1_DEF01`..`X1_DEF05` | C(15) | Valores default de cada opção (multilíngue: `X1_DEFSPA*`/`X1_DEFENG*`) |
| `X1_CNT01`..`X1_CNT05` | C(60) | Conteúdos da pergunta |
| `X1_HELP` | C(14) | Referência ao help do SX5 |
| `X1_PICTURE` | C(40) | Máscara de formatação |
| `X1_GRPSXG` | C(3) | Grupo SXG (template de tamanho) |
| `X1_IDFIL` | C(6) | Filial de identificação |
| `X1_PYME` | C(1) | Marca uso na versão PME |

### Função Pergunte

```advpl
/*
  Pergunte( cGrupo, lExibe )
  cGrupo  - Identificador do grupo na SX1
  lExibe  - .T. = exibe janela ao usuário
            .F. = apenas carrega variáveis sem mostrar tela
*/
Pergunte("REL001", .T.)   // Exibe tela de perguntas

// Após Pergunte(), as variáveis MV_PAR01..MV_PARxx ficam preenchidas
cDtIni := MV_PAR01   // Ex: data início
cDtFim := MV_PAR02   // Ex: data fim
```

### Criando perguntas via ADVPL

```advpl
User Function zCriaSX1()
    Local cGrupo := "ZREL001"

    // Estrutura: {Texto, MV_PAR, Tipo, Tamanho, Decimal, F3, Default, Combo}
    Local aPergs := {;
        {"Data De:",   "MV_PAR01", "D", 8, 0, "", CToD("01/01/25"), ""},;
        {"Data Ate:",  "MV_PAR02", "D", 8, 0, "", Date(),            ""},;
        {"Produto De:","MV_PAR03", "C", 15,0, "SB1","",""},;
        {"Produto Ate:","MV_PAR04","C", 15,0, "SB1","",""}  ;
    }

    AjustaSX1(cGrupo, aPergs)
Return

// Uso posterior
User Function zRelatorio()
    Pergunte("ZREL001", .T.)
    // MV_PAR01 = data início, MV_PAR02 = data fim
    // MV_PAR03 = produto de, MV_PAR04 = produto até
Return
```

### Gravação manual na SX1

```advpl
DbSelectArea("SX1")
DbSetOrder(1)  // X1_GRUPO + X1_ORDEM
If !DbSeek(PadR("ZREL001", 6) + "01")
    RecLock("SX1", .T.)   // .T. = inclusão
Else
    RecLock("SX1", .F.)   // .F. = alteração
EndIf

SX1->X1_GRUPO   := "ZREL001"
SX1->X1_ORDEM   := "01"
SX1->X1_PERGUNT := "Data De:"
SX1->X1_TIPO    := "D"
SX1->X1_TAMANHO := 8
SX1->X1_VAR01   := "MV_PAR01"
SX1->X1_DEF01   := DToC(Date())

SX1->(MsUnlock())
```

---

## 3. SX2 — Mapeamento de Arquivos

### O que é a SX2

A tabela **SX2** define de forma padronizada todas as tabelas disponíveis dentro do Protheus. É ela quem informa ao sistema:

- O alias (identificador lógico) de cada tabela, utilizado em todo código ADVPL
- O nome físico da tabela no banco de dados
- O modo de acesso (compartilhado entre filiais ou exclusivo por filial)
- O prefixo dos campos pertencentes à tabela

### Campos da SX2

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `X2_CHAVE` | C(3) | Alias/prefixo da tabela (ex: `"SA1"`, `"SB1"`) — chave de busca. **O prefixo dos campos é derivado deste valor** (não existe coluna `X2_PREF`). |
| `X2_NOME` | C(30) | Nome descritivo/real da tabela (PT — também `X2_NOMESPA`/`X2_NOMEENG`) |
| `X2_MODO` | C(1) | Modo de acesso: `"C"`=Compartilhado, `"E"`=Exclusivo |
| `X2_MODOUN` | C(1) | Modo por **unidade** (diferente de X2_MODO) |
| `X2_MODOEMP` | C(1) | Modo por **empresa** |
| `X2_UNICO` | C(250) | Expressão da chave única (essencial pra customização) |
| `X2_ARQUIVO` | C(8) | Nome físico do arquivo (prefixo + código da empresa + "0") |
| `X2_PATH` | C(40) | Caminho/path do arquivo |
| `X2_TTS` | C(1) | Indica uso de controle de transação |
| `X2_ROTINA` | C(40) | Rotina responsável pela manutenção da tabela |
| `X2_DELET` | **N** | **Contador numérico** de registros deletados — **não** é flag `"S"/"N"`. Em SQL direto exige número. |
| `X2_MODULO` | N | Módulo a que pertence (numérico — pra filtrar por módulo) |
| `X2_DISPLAY` | C(254) | Filtro de exibição |
| `X2_TAMFIL` / `X2_TAMUN` / `X2_TAMEMP` | N | Tamanhos do FILIAL/UNIDADE/EMPRESA usados |
| `X2_POSLGT` / `X2_CLOB` / `X2_AUTREC` | C(1) | Flags de comportamento |
| `X2_STAMP` / `X2_INSDT` | C(1) | Timestamp/inserção controlada |
| `X2_SYSOBJ` / `X2_USROBJ` | C(100) | Objetos de sistema / usuário |
| `X2_PYME` | C(1) | Marca uso na versão PME |

> **Atenção:** docs antigos TOTVS mencionam uma coluna `X2_PREF` para "prefixo dos campos" — **ela não existe** no schema atual. `SELECT x2_pref FROM sx2xxx` falha com *column does not exist*. O prefixo dos campos é simplesmente as 2-3 primeiras letras de `X2_CHAVE` (ex: `SA1` → campos com prefixo `A1_`).

### Convenção de nomenclatura das tabelas

Os nomes das tabelas no Protheus seguem um padrão:

```
SA1 010
│└┘ └┤└
│ │  │└── Dígito reservado TOTVS (sempre "0")
│ │  └─── Número da empresa (2 dígitos)
│ └────── Sequência dentro da família (1..Z)
└──────── Família do arquivo (A..Z, 0..9)
```

O "S" inicial indica que o arquivo pertence ao ambiente genérico Microsiga. Por exemplo: `SA1010` — "S" (Siga), "A" (família de Clientes/Fornecedores/etc.), "1" (sequência), "01" (empresa 01), "0" (dígito TOTVS).

### Modo compartilhado vs. exclusivo

- **Compartilhado (`C`):** O campo de filial fica em branco. Todos os registros são visíveis por todas as filiais. Exemplo: tabela de produtos (SB1) — em geral, o mesmo produto existe para todas as filiais.
- **Exclusivo (`E`):** O campo de filial recebe o código da filial atual. Cada filial vê apenas seus registros. Exemplo: tabela de pedidos de venda (SC5) — cada filial tem seus próprios pedidos.

```advpl
// Verificando o modo de uma tabela
DbSelectArea("SX2")
DbSetOrder(1)  // X2_CHAVE
If DbSeek("SA1")
    cModo := SX2->X2_MODO        // "C" ou "E"
    cPref := SubStr(SX2->X2_CHAVE, 2, 2)  // Prefixo dos campos derivado da chave
                                          // (ex: "SA1" → "A1")
EndIf
```

### Criando tabela customizada via SX2

```advpl
// Exemplo de registro SX2 para tabela customizada
DbSelectArea("SX2")
DbSetOrder(1)
If !DbSeek("ZZ1")
    RecLock("SX2", .T.)
    SX2->X2_CHAVE   := "ZZ1"
    SX2->X2_NOME    := "Tabela Customizada"
    SX2->X2_MODO    := "E"   // Exclusiva por filial
    SX2->X2_UNICO   := "ZZ1_FILIAL+ZZ1_COD"
    // Não atribuir X2_PREF — coluna não existe; prefixo é derivado de X2_CHAVE
    SX2->(MsUnlock())
EndIf
```

---

## 4. SX3 — Campos das Tabelas

### O que é a SX3

A tabela **SX3** é o coração do dicionário de dados. Ela define de forma padronizada a estrutura completa de todos os campos de todas as tabelas do Protheus. Toda modificação de campo — inclusão, alteração, inibição — deve ser feita nesta tabela.

O SX3 determina os campos contidos no banco de dados, sendo o TopConnect responsável por sincronizar automaticamente as alterações com o banco relacional (Oracle, SQL Server, MySQL, etc.).

### 4.1 Campos de identificação e estrutura

| Campo | Tipo | Tam | Descrição |
|-------|------|-----|-----------|
| `X3_ARQUIVO` | C | 6 | Alias da tabela (definida em SX2->X2_CHAVE) |
| `X3_ORDEM` | C | 2 | Ordem de apresentação na tela (`"01"`, `"02"`, ...) |
| `X3_CAMPO` | C | 10 | Nome físico do campo no banco de dados |
| `X3_TIPO` | C | 1 | Tipo do campo (ver tabela abaixo) |
| `X3_TAMANHO` | N | 3 | Tamanho total do campo |
| `X3_DECIMAL` | N | 2 | Número de casas decimais (somente para `N`) |
| `X3_CONTEXT` | C | 1 | Contexto: `R`=Real (físico), `V`=Virtual (não persiste) |

**Tipos de campo (X3_TIPO):**

| Valor | Tipo | Descrição |
|-------|------|-----------|
| `C` | Caractere | Letras, números, símbolos especiais |
| `N` | Numérico | Valores numéricos inteiros ou decimais |
| `D` | Data | Data no formato definido pelo sistema |
| `L` | Lógico | Verdadeiro (`.T.`) ou Falso (`.F.`) |
| `M` | Memo | Texto longo (armazenado separadamente) |
| `V` | Virtual | Campo calculado/virtual (obsoleto; use `X3_CONTEXT = "V"`) |

### 4.2 Campos de apresentação

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `X3_TITULO` | C | Título resumido do campo (exibido na tela e no browse) |
| `X3_DESCRIC` | C | Descrição completa do campo |
| `X3_TITSPA` | C | Título em espanhol |
| `X3_TITENG` | C | Título em inglês |
| `X3_DESCSPA` | C | Descrição em espanhol |
| `X3_DESCENG` | C | Descrição em inglês |
| `X3_PICTURE` | C | Máscara de formatação (ex: `@!`, `@E 999.999,99`, `99/99/9999`) |
| `X3_CBOX` | C | Opções de combo no formato `"1=Ativo;2=Inativo"` |
| `X3_BROWSE` | C | `"S"` = exibe no browse (listagem), `"N"` = não exibe |
| `X3_VISUAL` | C | Visibilidade: `"A"`=Alterar, `"V"`=Visualizar, `""`=Oculto |
| `X3_NÍVEL` | N | Nível de acesso necessário para ver/editar o campo |
| `X3_GRPSXG` | C | `varchar(3)` — referência ao **grupo SXG** (template de tamanho). Docs TOTVS antigos chamam de `X3_GRUPO`, mas a coluna física é `X3_GRPSXG`: `SELECT x3_grupo FROM sx3xxx` falha com *column does not exist*. Não confundir com `X3_FOLDER` (pasta na tela). |
| `X3_PYME` | C | Indica se o campo é usado na versão PME |

### 4.3 Campos de comportamento

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `X3_OBRIGAT` | C | `varchar(8)` — na prática quase sempre **vazio**. A partir de v12.1.7 a estrutura mudou de binário para CHAR controlado por API; use `X3TreatObrigat()` para analisar/transformar (`Bin2Str()` falha após 12.1.7). Atribuir `"S"` direto via SQL é silenciosamente ignorado. Para forçar preenchimento de forma confiável, use `X3_VALID := "!Empty(M->CAMPO)"`. |
| `X3_VALID` | C | Expressão/função de validação do conteúdo |
| `X3_RELACAO` | C | Inicializador padrão (valor sugerido na inclusão) |
| `X3_F3` | C | Alias da consulta SXB ou código de tabela SX5 para o F3 |
| `X3_WHEN` | C | Condição ADVPL para habilitar a edição do campo |
| `X3_TRIGGER` | C | `varchar(1)` — `"S"` = campo possui gatilhos na SX7; vazio = não tem. API ADVPL pode expor como lógico (`.T./.F.`), mas em SQL direto / script de update use literal `"S"`. |
| `X3_USADO` | C | `varchar(120)` — bitmap indicando em quais **módulos/segmentos do ERP** (FAT, EST, FIN, COM, RH, …) o campo está habilitado. **Não** é empresa/filial — para filtragem por empresa/filial use `X3_CONDSQL` ou filtro de aplicação. A partir da v12.1.7 a estrutura mudou de binário para CHAR controlado por API; use `X3TreatUso()` para analisar/transformar, ou `X3Uso(SX3->X3_USADO)` para checar runtime. Manipular via SQL direto exige reproduzir o bitmap exato — caminho seguro: clonar de campo similar via subselect (`FwPutSX3()` é o caminho oficial). |
| `X3_INIBRW` | C | Expressão para exibição no browse (campos virtuais no browse) |

### 4.4 X3_VALID — Validação de campo

O campo `X3_VALID` contém uma expressão ADVPL que é avaliada quando o usuário confirma o conteúdo do campo. O retorno **obrigatoriamente deve ser lógico** (`.T.` ou `.F.`).

```advpl
// Exemplos de X3_VALID:

// Verifica se o campo não está vazio
X3_VALID := "!Empty(M->A1_COD)"

// Chama função de validação do dicionário
X3_VALID := "ExistCpo('SA1')"           // Verifica se código existe na SA1
X3_VALID := "ExistCpo('SB1',M->C6_PRODUTO)" // Verifica produto na SB1

// Chama função customizada
X3_VALID := "u_ValidaCliente()"

// Expressão composta
X3_VALID := "M->A1_TIPO $ 'FJL' .And. !Empty(M->A1_COD)"

// Validação de intervalo numérico
X3_VALID := "M->ZZ1_PERC >= 0 .And. M->ZZ1_PERC <= 100"
```

O prefixo `M->` indica variável de memória — durante a edição, os campos ficam em memória antes de serem gravados no banco.

#### Relação com MaFisRef (fiscal)

Em campos fiscais (módulo MATXFIS), a validação frequentemente chama `MaFisRef()` para verificar referências fiscais:

```advpl
X3_VALID := "MaFisRef('CF0_CLAFI','ZA0',M->CF0_CLAFI)"
```

### 4.5 X3_WHEN — Habilitação condicional

O campo `X3_WHEN` controla quando um campo pode ser editado. O retorno também deve ser lógico.

```advpl
// Exemplos de X3_WHEN:

// Campo só editável na inclusão
X3_WHEN := "Inclui"

// Campo só editável na alteração
X3_WHEN := "Altera"

// Campo só editável se outro campo tem determinado valor
X3_WHEN := "M->A1_TIPO == 'F'"   // Apenas para pessoa física

// Combinação com variáveis do sistema
X3_WHEN := "Inclui .Or. (Altera .And. M->C5_LIBEROK == 'N')"

// Função customizada
X3_WHEN := "u_PermiteEditar()"
```

**Nota:** `Inclui` e `Altera` são variáveis PRIVATE padrão do Protheus que indicam o modo atual da rotina.

### 4.6 X3_TRIGGER — Gatilhos

O campo `X3_TRIGGER` é **`varchar(1)`** no banco (`character(1)` no PostgreSQL/Oracle): valor `"S"` indica que o campo possui gatilhos associados na tabela SX7; vazio indica que não tem. Quando habilitado, ao sair do campo o sistema consulta a SX7 e executa os gatilhos configurados. A API ADVPL pode tratar o valor como lógico (`.T./.F.`), mas em SQL direto e scripts de update use sempre literal `"S"`.

```advpl
// Verificando programaticamente se um campo tem gatilhos
If ExistTrigger("C6_PRODUTO")
    RunTrigger("C6_PRODUTO")
EndIf
```

### 4.7 Consultas F3 via X3_F3

O campo `X3_F3` define qual consulta é exibida quando o usuário pressiona `[F3]` no campo:

- Se for um alias de consulta cadastrada na **SXB** (ex: `"QB_CLI"`), abre a tela de pesquisa.
- Se for um código numérico de tabela da **SX5** (ex: `"02"`), exibe a lista de opções da tabela genérica.

```advpl
// X3_F3 = "SB1" → abre consulta padrão de produtos (SXB alias SB1)
// X3_F3 = "21"  → abre tabela genérica SX5 com X5_TABELA = "21"
```

### 4.8 Array interno da SX3 em ADVPL

Ao trabalhar com funções que retornam a estrutura da SX3 como array, as posições são:

| Posição | Campo SX3 | Descrição |
|---------|-----------|-----------|
| `[01]` | `X3_CAMPO` | Nome do campo |
| `[02]` | — | Filial? |
| `[03]` | `X3_TAMANHO` | Tamanho |
| `[04]` | `X3_DECIMAL` | Decimais |
| `[05]` | `X3_TIPO` | Tipo |
| `[06]` | `X3_TITULO` | Título |
| `[07]` | `X3_DESCRIC` | Descrição |
| `[08]` | `X3_PICTURE` | Máscara |
| `[09]` | `X3_NÍVEL` | Nível de acesso |
| `[10]` | `X3_VALID` | Validação usuário |
| `[11]` | `X3_USADO` | Usado? |
| `[12]` | `X3_RELACAO` | Inicializador padrão |
| `[13]` | `X3_F3` | Consulta F3 |
| `[14]` | `X3_VISUAL` | Visual |
| `[15]` | `X3_CONTEXT` | Contexto (Real/Virtual) |
| `[16]` | `X3_BROWSE` | Browse |
| `[17]` | `X3_OBRIGAT` | Obrigatório |
| `[18]` | `X3_CBOX` | Opções combo |
| `[19]` | `X3_WHEN` | Modo de edição |
| `[20]` | `X3_INIBRW` | Inicializador browse |
| `[21]` | — | Pasta (SXA) |

---

## 5. SX5 — Tabelas Genéricas

### O que é a SX5

A tabela **SX5** é o repositório de tabelas genéricas de domínio do Protheus. Ela armazena pequenos conjuntos de valores (como tipos, situações, classificações, UFs, países) que são referenciados por campos de outras tabelas.

Cada conjunto de valores forma uma "tabela" identificada por `X5_TABELA`, e cada item dessa tabela tem uma chave (`X5_CHAVE`) e uma descrição (`X5_DESCRI`).

### Campos da SX5

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `X5_FILIAL` | C | Filial |
| `X5_TABELA` | C | Código da tabela genérica (ex: `"02"` = Tipos de Cliente) |
| `X5_CHAVE` | C | Código do item dentro da tabela |
| `X5_DESCRI` | C | Descrição em português |
| `X5_DESCSPA` | C | Descrição em espanhol |
| `X5_DESCENG` | C | Descrição em inglês |

**Ordem 1 (índice principal):** `X5_FILIAL + X5_TABELA + X5_CHAVE`

### Exemplos de tabelas genéricas comuns

| X5_TABELA | Descrição |
|-----------|-----------|
| `"02"` | Tipos de cliente |
| `"03"` | Condições de pagamento (tipos) |
| `"10"` | Regiões |
| `"21"` | Países |
| `"33"` | Unidades da Federação |

### Funções para SX5

#### Posicione com SX5

```advpl
// Sintaxe geral de Posicione
// Posicione(cAlias, nOrdem, cChave, cCampo)

// Buscar descrição de uma tabela genérica
cDescricao := Posicione("SX5", 1, xFilial("SX5") + "02" + cTipo, "X5_DESCRI")

// Com AllTrim para remover espaços
cDescricao := AllTrim(Posicione("SX5", 1, xFilial("SX5") + "21" + cPais, "X5_DESCRI"))
```

#### SX5Desc e fDescSX5

```advpl
// SX5Desc(cTabela, cChave) — retorna descrição diretamente
cDesc := SX5Desc("02", M->A1_TIPO)

// fDescSX5 — requer posicionamento prévio
DbSelectArea("SX5")
SX5->(DbSetOrder(1))
If SX5->(MsSeek(FWxFilial("SX5") + "02" + cTipoCli))
    cDesc := fDescSX5(1)   // 1 = descrição idioma atual
EndIf
```

#### FWGetSX5 e FWPutSX5

```advpl
// FWGetSX5(cTabela, cChave, cIdioma) — retorna array
aInfo := FWGetSX5("02", cTipo, "pt-br")
// aInfo[1] = filial, [2] = tabela, [3] = chave, [4] = descrição
cDesc := AllTrim(aInfo[4])

// FWPutSX5 — cria ou atualiza registro
FWPutSX5("CUSTOM", "ZZ", "01", "Opção 1", "Option 1")
```

#### Criação manual de registro na SX5

```advpl
User Function zCriaSX5(cTabela, cChave, cDesc)
    Local cFilSX5 := FWxFilial("SX5")

    DbSelectArea("SX5")
    SX5->(DbSetOrder(1))

    If !SX5->(DbSeek(cFilSX5 + cTabela + cChave))
        RecLock("SX5", .T.)
        X5_FILIAL  := cFilSX5
        X5_TABELA  := cTabela
        X5_CHAVE   := cChave
        X5_DESCRI  := cDesc
        X5_DESCSPA := cDesc
        X5_DESCENG := cDesc
        SX5->(MsUnlock())
    EndIf
Return
```

### Vincular SX5 a um campo via F3

No campo `X3_F3` da SX3, coloque o código da tabela genérica. Ao pressionar `[F3]`, o sistema exibe os itens da SX5 com `X5_TABELA` = valor informado.

```advpl
// No SX3 do campo A1_TIPO:
// X3_F3 = "02"  → abre tabela genérica 02 (tipos de cliente)
```

---

## 6. SX6 — Parâmetros MV_

### O que é a SX6

A tabela **SX6** armazena todos os parâmetros de configuração do sistema Protheus. Os parâmetros geralmente têm o prefixo `MV_` e controlam comportamentos do ERP — desde configurações fiscais até regras de negócio específicas de cada módulo.

### Campos da SX6

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `X6_FIL` | C(2) | Filial do parâmetro |
| `X6_VAR` | C(10) | Nome do parâmetro (ex: `"MV_ESTADO"`) |
| `X6_TIPO` | C(1) | Tipo do valor: `C`=Caractere, `N`=Numérico, `L`=Lógico, `D`=Data |
| `X6_DESCRIC` | C(50) | Descrição — parte 1 (PT / `X6_DESCSPA` / `X6_DESCENG`) |
| `X6_DESC1` | C(50) | Descrição — parte 2 (multilíngue) |
| `X6_DESC2` | C(50) | Descrição — parte 3 (multilíngue) |
| `X6_CONTEUD` | C(250) | Conteúdo/valor do parâmetro (multilíngue: `X6_CONTSPA`/`X6_CONTENG`) |
| `X6_PROPRI` | C(1) | Propriedade: `"U"`=Usuário (customizável) |
| `X6_PYME` | C(1) | Marca uso na versão PME |
| `X6_VALID` | C(160) | Expressão ADVPL de validação ao **gravar** o parâmetro (ex: `'Pertence("SN")'`). Roda no `PutMV` / Configurador. |
| `X6_INIT` | C(128) | Inicializador — valor default quando o `GetMV`/`SuperGetMV` não acha registro. |
| `X6_DEFPOR` / `X6_DEFSPA` / `X6_DEFENG` | C(250) | Defaults multilíngues (diferentes de `X6_CONTEUD`) |
| `X6_EXPDEST` | C(1) | Expressão de destino (uso em integração) |
| `X6_ACTIVE` | C(1) | **Importante**: controla se o parâmetro está **ativo**. Em algumas releases, parâmetro com `X6_ACTIVE` vazio é ignorado pelo runtime. Setar `"1"` ao criar custom. |

### GetMV — Obter valor de parâmetro

```advpl
// Sintaxe: GetMV(cParâmetro, lConsulta, xDefault)

// Uso simples
cEstado := GetMV("MV_ESTADO")

// Com valor default caso parâmetro não exista
nPercDesc := GetMV("MV_PERDESC", .F., 0)

// Verificando existência antes de ler
If FWSX6Util():ExistsParam("MV_MEUPARAM")
    cValor := GetMV("MV_MEUPARAM")
EndIf
```

### SuperGetMV — Versão com cache

```advpl
// SuperGetMV é mais performática: usa cache interno
// Sintaxe: SuperGetMV(cParâmetro, lHelp, cPadrao, cFilial)

// Básico
cValor := SuperGetMV("MV_ESTADO", .F., "SP")

// Com filial específica
cValor := SuperGetMV("MV_ESTADO", .F., "SP", "01")

// Comparação de performance:
// GetMV    → acessa SX6 a cada chamada
// SuperGetMV → primeira chamada acessa SX6, demais usam cache
```

### PutMV — Alterar valor de parâmetro

```advpl
User Function zAlterParam()
    Local cValor := FWInputBox("Informe o novo valor", "Parâmetro")
    If !Empty(cValor)
        PutMV("MV_MEUPARAM", cValor)
        MsgInfo("Parâmetro alterado com sucesso!")
    EndIf
Return
```

### Criando parâmetros via código

```advpl
User Function zCriaSX6()
    // Array de parâmetros: {Nome, Tipo, Descrição, Conteúdo}
    Local aParams := {;
        {"MV_ZPARAM1", "C", "Parâmetro texto customizado",  "VALOR"},;
        {"MV_ZPARAM2", "N", "Percentual máximo de desconto", "10"  },;
        {"MV_ZPARAM3", "L", "Habilita funcionalidade X",     ".T." };
    }
    Local nI, cFil

    cFil := FWxFilial("SX6")

    DbSelectArea("SX6")
    DbSetOrder(1)  // X6_FIL + X6_VAR

    For nI := 1 To Len(aParams)
        If !DbSeek(cFil + aParams[nI][1])
            RecLock("SX6", .T.)
            X6_FIL     := cFil
            X6_VAR     := aParams[nI][1]
            X6_TIPO    := aParams[nI][2]
            X6_PROPRI  := "U"
            X6_DESCRIC := SubStr(aParams[nI][3], 1, 50)
            X6_CONTEUD := aParams[nI][4]
            X6_ACTIVE  := "1"   // crítico: parâmetro inativo é ignorado em releases recentes
            SX6->(MsUnlock())
        EndIf
    Next nI
Return
```

---

## 7. SX7 — Gatilhos de Campos

### O que é a SX7

A tabela **SX7** armazena os gatilhos de campos do Protheus. Um gatilho define o que acontece automaticamente quando o usuário preenche ou altera um determinado campo — como buscar e preencher campos relacionados em outras tabelas, calcular valores ou disparar lógicas.

Os gatilhos eliminam a necessidade de codificar manualmente a lógica de preenchimento em cada rotina.

### 7.1 Tipos de gatilho

Valores observados em `X7_TIPO` em releases atuais:

| Tipo | Nome | Descrição |
|------|------|-----------|
| `P` ou vazio | **Primário** (padrão) | Preenche um campo na mesma tela. Tipo mais utilizado. |
| `X` | **Posicionamento** | Posiciona um alias sem efetuar atualização — usado para relacionamentos. |

> **Cuidado:** docs antigos citam tipo `"E"` (**Estrangeiro** — atualizaria campo em outra tabela). Na prática, esse tipo **não existe** em releases modernas: zero ocorrências no dicionário padrão. Gravar `X7_TIPO='E'` faz o appserver ignorar o gatilho. Para atualizar campo em outra tabela, use rotina/PE em ADVPL, não SX7.

### 7.2 Campos da SX7

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `X7_CAMPO` | C(10) | Campo de origem — dispara o gatilho quando alterado. **O alias da tabela é derivado do prefixo** (`B1_DESC` → SB1); não existe coluna `X7_ARQUIVO`. |
| `X7_SEQUENC` | C(3) | Sequência de execução (`"001"`, `"002"`, ...). **Nome correto é `X7_SEQUENC` com `C` final** — `X7_SEQUEN` não existe (`SELECT x7_sequen FROM sx7xxx` falha). |
| `X7_REGRA` | C(200) | Expressão ADVPL que define o valor a atribuir ao contra domínio |
| `X7_CDOMIN` | C(10) | Contra domínio — campo que receberá o resultado |
| `X7_TIPO` | C(1) | Tipo: `P`/vazio=Primário, `X`=Posicionamento |
| `X7_SEEK` | C(1) | `"S"` = realiza posicionamento na tabela antes de avaliar a regra |
| `X7_ALIAS` | C(3) | Alias da tabela a ser posicionada |
| `X7_ORDEM` | N | Índice da tabela a ser usada no posicionamento |
| `X7_CHAVE` | C(200) | Expressão-chave para o posicionamento (use `M->` para variáveis de memória) |
| `X7_CONDIC` | C(40) | **Condição única** (ADVPL) — se `.F.`, gatilho não executa. **Não existem `X7_CONDIN` + `X7_CONDOUT` separadas** em releases modernas: foi unificado em `X7_CONDIC` numa só. |
| `X7_PROPRI` | C(1) | Propriedade do campo destino (`"R"`=Replace, `"A"`=Append) |

### 7.3 Fluxo de execução de um gatilho

```
[Usuário altera X7_CAMPO na tela]
          │
          ▼
[X7_CONDIC avaliada?]
     │         └── Falso → Gatilho ignorado
     │ Verdadeiro
     ▼
[X7_SEEK = "S"?]
     │         └── Não → pula posicionamento
     │ Sim
     ▼
[Posiciona X7_ALIAS usando índice X7_ORDEM e chave X7_CHAVE]
          │
          ▼
[Avalia expressão X7_REGRA (macro execução)]
          │
          ▼
[Atribui resultado ao campo X7_CDOMIN na tela]
```

### 7.4 Encadeamento de gatilhos

Quando múltiplos gatilhos são configurados para o mesmo campo (`X7_CAMPO`), o Protheus os executa na ordem definida por `X7_SEQUENC`. Se o primeiro gatilho já posicionou a tabela, os seguintes podem omitir `X7_ALIAS`, `X7_ORDEM` e `X7_CHAVE` — a tabela permanece posicionada.

```
X7_SEQUENC = "001" → Posiciona SB1 pela chave do produto, retorna B1_DESC
X7_SEQUENC = "002" → Sem posicionamento, retorna B1_UM (mesma posição SB1)
X7_SEQUENC = "003" → Sem posicionamento, retorna B1_LOCPAD
```

### 7.5 Exemplo real de gatilho

**Cenário:** ao informar o código do produto em um pedido de venda, preencher automaticamente a descrição, a unidade de medida e o preço.

| Campo SX7 | Seq 001 | Seq 002 | Seq 003 |
|-----------|---------|---------|---------|
| `X7_CAMPO` | `C6_PRODUTO` | `C6_PRODUTO` | `C6_PRODUTO` |
| `X7_SEQUENC` | `001` | `002` | `003` |
| `X7_TIPO` | `P` | `P` | `P` |
| `X7_CDOMIN` | `C6_DESCRI` | `C6_UM` | `C6_PRUNIT` |
| `X7_REGRA` | `SB1->B1_DESC` | `SB1->B1_UM` | `SB1->B1_PRV1` |
| `X7_SEEK` | `S` | `` | `` |
| `X7_ALIAS` | `SB1` | `` | `` |
| `X7_ORDEM` | `1` | `` | `` |
| `X7_CHAVE` | `xFilial("SB1")+M->C6_PRODUTO` | `` | `` |
| `X7_CONDIC` | (vazio = sempre dispara) | (vazio) | (vazio) |

```advpl
// Executar gatilho manualmente (ex: importação de planilha)
If ExistTrigger("C6_PRODUTO")
    aCols[nLin][FieldPos("C6_PRODUTO") - 1] := cCodProd
    RunTrigger("C6_PRODUTO", nLin)
EndIf
```

---

## 8. SX8 — Reserva de Numeração

### O que é a SX8

A tabela **SX8** é o mecanismo de **reserva transacional de numeração** no Protheus. Quando um processo precisa gerar um número sequencial (ex: número de nota fiscal, número de pedido), a reserva garante que dois processos concorrentes não obtenham o mesmo número.

As funções `GetSXENum`, `ConfirmSX8` e `RollBackSX8` trabalham em conjunto para controlar esse ciclo.

### Fluxo da reserva de numeração

```
GetSXENum("SA1", "A1_COD")
       │
       ▼
Número reservado na SX8 (ainda não confirmado)
       │
       ├── Processo bem-sucedido → ConfirmSX8()
       │         └── Número é gravado definitivamente nas SXE/SXF
       │
       └── Erro no processo → RollBackSX8()
                 └── Número é liberado, voltará à sequência anterior
```

### Funções de numeração

```advpl
User Function zExemploNumeracao()
    Local aArea   := GetArea()
    Local cCodigo := ""

    Begin Transaction
        // Obtém próximo número disponível
        cCodigo := GetSXENum("SA1", "A1_COD")

        // ... lógica do processo usando cCodigo ...

        If lMsErroAuto  // Ocorreu erro
            RollBackSX8()    // Libera o número
            DisarmTransaction()
        Else
            ConfirmSX8()     // Confirma o número
        EndIf
    End Transaction

    RestArea(aArea)
Return
```

```advpl
// Sintaxe completa do GetSXENum
// GetSXENum(cAlias, cCampo, [cAliasSX8], [nOrdem])
cNum := GetSXENum("SC5", "C5_NUM")          // Número de pedido
cNF  := GetSXENum("SF2", "F2_DOC", , 1)    // Número de nota fiscal
```

### SXE vs. License Server

| Método | Velocidade | Observação |
|--------|-----------|------------|
| Via SXE/SXF | ~3,375s para 100 números | Método legado (58% dos ambientes) |
| Via License Server | ~0,093s para 100 números | Método moderno, muito mais rápido |

A TOTVS recomenda migrar para o controle via License Server antes de atualizar releases.

---

## 9. SX9 — Relacionamentos entre Entidades

### O que é a SX9

O Protheus não usa integridade referencial no SGBD (sem *foreign keys* no banco). Os relacionamentos entre tabelas são definidos na aplicação, na tabela **SX9**. Isso permite flexibilidade para suportar múltiplos bancos de dados com comportamento uniforme.

A SX9 é usada para:
- Ativar a Integridade Referencial do ERP
- Auxiliar o framework MVC a entender relacionamentos cabeçalho-itens
- Servir de referência para customizações e consultas

### Campos da SX9

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `X9_DOM` | C(3) | Tabela de origem (Domínio) |
| `X9_IDENT` | C(3) | **Parte da chave** — identifica o registro quando há múltiplos relacionamentos entre as mesmas duas tabelas (ex: SC5↔SC6 com vários laços). Esquecer no INSERT gera conflito de chave. |
| `X9_CDOM` | C(3) | Tabela de destino (Contra Domínio) |
| `X9_EXPDOM` | C(250) | Expressão da chave no lado do domínio |
| `X9_EXPCDOM` | C(250) | Expressão da chave no lado do contra domínio |
| `X9_LIGDOM` | C(1) | Cardinalidade do lado domínio (`"1"` ou `"N"`) |
| `X9_LIGCDOM` | C(1) | Cardinalidade do lado contra domínio (`"1"` ou `"N"`) |
| `X9_VINFIL` | C(1) | Vínculo do modo de compartilhamento de filiais |
| `X9_CHVFOR` | C(1) | Chave forte (exige mesmo modo de compartilhamento) |
| `X9_PROPRI` | C(1) | Propriedade: `U`=User custom / `S`=System |
| `X9_USEFIL` | C(1) | Usa filial no relacionamento |
| `X9_ENABLE` | C(1) | **Controla se o relacionamento está ativo**. Vazio/desabilitado faz o framework ignorar a SX9 — sem warning. Sempre conferir ao criar relacionamento novo. |
| `X9_CONDSQL` | C(250) | Filtro SQL adicional aplicado ao relacionamento |

### Cardinalidades

| Combinação | Significado |
|------------|-------------|
| `X9_LIGDOM="1"` / `X9_LIGCDOM="1"` | Um para Um (1:1) |
| `X9_LIGDOM="1"` / `X9_LIGCDOM="N"` | Um para Muitos (1:N) — o mais comum |
| `X9_LIGDOM="N"` / `X9_LIGCDOM="1"` | Muitos para Um (N:1) |

### Exemplo de consulta SQL na SX9

```sql
-- Listar todos os relacionamentos do banco
SELECT
    X9_DOM     AS Origem,
    X9_CDOM    AS Destino,
    X9_EXPDOM  AS ExpressaoOrigem,
    X9_EXPCDOM AS ExpressaoDestino,
    X9_LIGDOM + ' para ' + X9_LIGCDOM AS Cardinalidade
FROM SX9990
WHERE D_E_L_E_T_ = ' '
ORDER BY Origem, Destino

-- Relacionamentos envolvendo a tabela SA1 (Clientes)
SELECT *
FROM SX9990
WHERE (X9_DOM = 'SA1' OR X9_CDOM = 'SA1')
  AND D_E_L_E_T_ = ' '
```

### SX9 no contexto MVC (cabeçalho e itens)

No framework MVC do Protheus, o relacionamento entre tabela de cabeçalho (Master) e tabela de itens (Detail) é configurado na SX9. Os campos relevantes para o MVC são:

| Campo | Descrição no contexto MVC |
|-------|--------------------------|
| `X9_DOM` | Tabela Master (cabeçalho), ex: `"SC5"` (Pedidos de Venda) |
| `X9_CDOM` | Tabela Detail (itens), ex: `"SC6"` (Itens do Pedido) |
| `X9_EXPDOM` | Expressão de ligação no master (ex: chave do pedido) |
| `X9_EXPCDOM` | Expressão correspondente no detail |

```advpl
// Em uma rotina MVC, o relacionamento SX9 é lido automaticamente
// pelo framework FWModel para montar o Modelo 2 (cabeçalho + grid)
oModel := MPFormModel():New("MEUMODELO")
oModel:SetRelation("ZZ1", "ZZ2", "ZZ1_FILIAL+ZZ1_COD", "ZZ2_FILIAL+ZZ2_PAI")
// O SetRelation reflete o que está definido na SX9
```

---

## 10. SXB — Consultas Padrão (F3)

### O que é a SXB

A tabela **SXB** armazena as **Consultas Padrão** do Protheus — as telas de pesquisa que aparecem quando o usuário pressiona `[F3]` em um campo ou acessa uma pesquisa. Cada consulta é identificada por um alias (`XB_ALIAS`) e composta por múltiplos registros com diferentes tipos.

No campo `X3_F3` da SX3, informa-se o alias da consulta SXB desejada.

### Campos da SXB

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `XB_ALIAS` | C(6) | Nome/alias da consulta (identificador único). **Máximo 6 chars** — `"ZPROD01"` (7 chars) seria truncado para `"ZPROD0"`. |
| `XB_TIPO` | C(1) | Tipo do registro (ver seção abaixo) |
| `XB_SEQ` | C(2) | Sequência do registro dentro do tipo |
| `XB_COLUNA` | C(2) | Coluna, índice ou referência de coluna |
| `XB_DESCRI` | C(20) | Descrição da consulta ou do título da coluna (multilíngue: `XB_DESCSPA`/`XB_DESCENG`) |
| `XB_CONTEM` | C(250) | Conteúdo: tabela, campo, filtro ou expressão de retorno |
| `XB_WCONTEM` | C(250) | **When Contém** — filtro condicional adicional, útil para consultas complexas |

### 10.1 Tipos de registro na SXB

Uma consulta completa na SXB é formada por registros de vários tipos:

#### Tipo 1 — Cabeçalho da consulta

Define o nome, a tabela principal e o tipo de índice.

```advpl
// XB_TIPO = "1"
// XB_ALIAS   = "ZCons01"     Nome da consulta
// XB_SEQ     = "01"          Sequência
// XB_COLUNA  = "RE"          Tipo de busca (RE = com retorno)
// XB_DESCRI  = "Clientes"    Descrição exibida ao usuário
// XB_CONTEM  = "SA1"         Alias da tabela principal
```

#### Tipo 2 — Títulos das colunas

Define os cabeçalhos das colunas exibidas na grid da consulta.

```advpl
// XB_TIPO = "2"
// Seq 01: XB_DESCRI = "Código",  XB_COLUNA = "01"
// Seq 02: XB_DESCRI = "Nome",    XB_COLUNA = "02"
// Seq 03: XB_DESCRI = "Tipo",    XB_COLUNA = "03"
```

#### Tipo 3 — Filtro/expressão

Define um filtro ADVPL aplicado aos registros exibidos.

```advpl
// XB_TIPO = "3"
// XB_CONTEM = "SA1->A1_FILIAL == xFilial('SA1')"
```

#### Tipo 4 — Campos das colunas

Define quais campos da tabela são exibidos em cada coluna.

```advpl
// XB_TIPO = "4"
// Seq 01: XB_CONTEM = "A1_COD"    → coluna "Código"
// Seq 02: XB_CONTEM = "A1_NOME"   → coluna "Nome"
// Seq 03: XB_CONTEM = "A1_TIPO"   → coluna "Tipo"
```

#### Tipo 5 — Retorno da consulta

Define qual campo é retornado ao campo de origem quando o usuário seleciona um registro.

```advpl
// XB_TIPO = "5"
// XB_CONTEM = "A1_COD"   → retorna o código do cliente
```

### Resumo dos tipos

| Tipo | Função |
|------|--------|
| `"1"` | Cabeçalho: nome da consulta, tabela principal, modo de busca |
| `"2"` | Títulos das colunas exibidas na grid |
| `"3"` | Filtro/expressão ADVPL aplicado à lista |
| `"4"` | Campos reais da tabela vinculados a cada coluna |
| `"5"` | Campo retornado ao confirmar a seleção |
| `"6"` | Observado na base mas pouco documentado (consultas avançadas) |
| `"7"` | Observado na base mas pouco documentado |
| `"8"` | Observado na base mas pouco documentado (raro) |
| `"9"` | Observado na base mas pouco documentado |

> Os tipos 6-9 são observados em milhares de registros do dicionário padrão TOTVS mas não têm documentação pública clara. Ao customizar uma consulta, focar em 1-5; mas ao **ler** SXB existente (ex: para análise de impacto), considerar que esses tipos podem aparecer.

### 10.2 Criando uma consulta F3 personalizada

#### Via Configurador (SIGACFG)

1. Acesse `Base de Dados > Dicionário > Consultas Padrão`
2. Clique em `Incluir`
3. Informe o Alias (nome da consulta)
4. Adicione os registros de cada tipo

#### Via código ADVPL

```advpl
User Function zCriaConsF3()
    Local aSXB  := {}
    Local cAls  := "ZPROD1"    // Alias da consulta (máx 6 chars!)

    // Tipo 1 — Cabeçalho
    // {Alias, Tipo, Seq, Coluna, Descri, DescrSpa, DescrEng, Contem}
    Aadd(aSXB, {cAls, "1", "01", "RE", "Produtos", "Productos", "Products", "SB1"})

    // Tipo 2 — Títulos das colunas
    Aadd(aSXB, {cAls, "2", "01", "01", "Código",   "Codigo",   "Code",    ""})
    Aadd(aSXB, {cAls, "2", "02", "02", "Descrição","Descripcion","Description",""})
    Aadd(aSXB, {cAls, "2", "03", "03", "Tipo",     "Tipo",     "Type",    ""})

    // Tipo 3 — Filtro
    Aadd(aSXB, {cAls, "3", "01", "01", "", "", "", "SB1->B1_FILIAL == xFilial('SB1')"})

    // Tipo 4 — Campos
    Aadd(aSXB, {cAls, "4", "01", "01", "Código",      "","", "B1_COD"  })
    Aadd(aSXB, {cAls, "4", "01", "02", "Descrição",   "","", "B1_DESC" })
    Aadd(aSXB, {cAls, "4", "01", "03", "Tipo",        "","", "B1_TIPO" })

    // Tipo 5 — Retorno
    Aadd(aSXB, {cAls, "5", "01", "01", "Código", "", "", "B1_COD"})

    // Gravar na SXB
    DbSelectArea("SXB")
    DbSetOrder(1)

    Local nI
    For nI := 1 To Len(aSXB)
        If !DbSeek(aSXB[nI][1] + aSXB[nI][2] + aSXB[nI][3])
            RecLock("SXB", .T.)
            SXB->XB_ALIAS  := aSXB[nI][1]
            SXB->XB_TIPO   := aSXB[nI][2]
            SXB->XB_SEQ    := aSXB[nI][3]
            SXB->XB_COLUNA := aSXB[nI][4]
            SXB->XB_DESCRI := aSXB[nI][5]
            SXB->XB_CONTEM := aSXB[nI][8]
            SXB->(MsUnlock())
        EndIf
    Next nI

    // No campo X3_F3 do SX3, coloque "ZPROD1"
    MsgInfo("Consulta " + cAls + " criada com sucesso!")
Return

// Abrir consulta via código
User Function zAbreF3()
    Local cRetorno := ""
    cRetorno := ConPad1("ZPROD1")    // Abre a consulta e retorna o valor selecionado
    MsgInfo("Selecionado: " + cRetorno)
Return
```

---

## 11. SXE e SXF — Controle de Numeração Sequencial

### O que são SXE e SXF

As tabelas **SXE** e **SXF** armazenam os contadores de numeração sequencial das tabelas do Protheus. Elas trabalham em conjunto com a SX8 (reserva transacional).

| Tabela | Descrição |
|--------|-----------|
| **SXE** | Controla o **próximo número a ser utilizado** (próximo número + 1) |
| **SXF** | Controla o **último número sequencial confirmado** (por filial) |

Cada registro nessas tabelas corresponde a uma tabela + campo do sistema. Quando `GetSXENum` é chamado, ele:

1. Lê o valor atual de SXE/SXF
2. Reserva o número na SX8 (lock transacional)
3. Retorna o número ao chamador

Quando `ConfirmSX8` é chamado, o contador em SXE/SXF é incrementado definitivamente. Quando `RollBackSX8` é chamado, a reserva é desfeita e o número volta à fila.

### Ajustando numeração manualmente

Em situações onde a numeração ficou dessincronizada (ex: importação direta no banco), é possível ajustar a SXE/SXF pelo Configurador:

1. Acesse `Base de Dados > Seqüências`
2. Localize a tabela e o campo desejado
3. Altere o próximo número

```advpl
// Verificar numeração atual via ADVPL
DbSelectArea("SXE")
DbSetOrder(1)
If DbSeek(xFilial("SXE") + "SC5" + "C5_NUM")
    cProxNum := SXE->E_NUMERO   // Próximo número disponível
EndIf
```

---

## 12. SIX — Índices dos Arquivos

### O que é a SIX

A tabela **SIX** armazena a definição de todos os índices das tabelas do Protheus. Assim como os campos são definidos na SX3, os índices são definidos na SIX — permitindo ao TopConnect criar e manter os índices no banco relacional.

### Campos principais da SIX

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `INDICE` | C(3) | Alias da tabela (ex: `"SA1"`) |
| `ORDEM` | C(1) | Número da ordem do índice (`"1"`, `"2"`, ...) |
| `CHAVE` | C(160) | Expressão-chave do índice (ex: `"A1_FILIAL+A1_COD+A1_LOJA"`) |
| `DESCRICAO` | C(70) | Descrição do índice (PT — também `DESCSPA`/`DESCENG`). **Atenção:** nome real é `DESCRICAO`, não `DESCR` (`SELECT descr FROM sixxxx` falha). |
| `PROPRI` | C(1) | `U`=User custom / `S`=System TOTVS |
| `F3` | C(160) | Consulta F3 do índice |
| `NICKNAME` | C(10) | Apelido para uso em ADVPL |
| `SHOWPESQ` | C(1) | `"S"` = exibe no atalho de pesquisa |
| `IX_VIRTUAL` | C(1) | Índice virtual (feature moderna) |
| `IX_VIRCUST` | C(1) | Índice virtual customizado |

> Observação: ao contrário das outras tabelas SX, **SIX não tem prefixo `ix_` na maioria das colunas** — é legado. Colunas: `indice`, `ordem`, `chave`, `descricao`, `propri`, `f3`, `nickname`, `showpesq`.

```advpl
// Exemplo: definindo índice na SIX via ADVPL
DbSelectArea("SIX")
DbSetOrder(1)
If !DbSeek("ZZ1" + "1")
    RecLock("SIX", .T.)
    SIX->INDICE    := "ZZ1"
    SIX->ORDEM     := "1"
    SIX->CHAVE     := "ZZ1_FILIAL+ZZ1_COD"
    SIX->DESCRICAO := "Codigo da Tabela Customizada"   // coluna é DESCRICAO, não DESCR
    SIX->SHOWPESQ  := "S"
    SIX->(MsUnlock())
EndIf
```

---

## 13. SXA — Pastas e Agrupamentos de Campos

### O que é a SXA

A tabela **SXA** define as **pastas** (abas) das telas de cadastro do Protheus. Os campos da SX3 são associados às pastas da SXA por meio do campo `X3_FOLDER` (que casa com `XA_ORDEM`). _Não confundir com `X3_GRPSXG`, que aponta para o grupo SXG de template de tamanho._

### Campos da SXA

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `XA_ALIAS` | C | Alias da tabela |
| `XA_ORDEM` | C | Ordem da pasta na tela |
| `XA_DESCRI` | C | Descrição/título da pasta (PT-BR) |
| `XA_DESCSPA` | C | Descrição em espanhol |
| `XA_DESCENG` | C | Descrição em inglês |

```advpl
// No SX3, o campo X3_FOLDER vincula o campo à pasta da SXA
// Ex: X3_FOLDER = "001" → pasta "Dados Gerais" definida na SXA com XA_ORDEM = "001"
```

---

## 14. Funções ADVPL Relacionadas ao Dicionário

### 14.1 GetSX3Cache e X3Descricao

A função `GetSX3Cache` retorna o conteúdo de qualquer coluna da SX3 para um campo informado, usando o cache interno do Protheus (sem acessar o banco diretamente).

```advpl
// Sintaxe: GetSX3Cache(cCampo, cColunaSX3)

// Obter título de um campo
cTitulo  := GetSX3Cache("A1_COD",  "X3_TITULO")   // Retorna "Código"
cTipo    := GetSX3Cache("A1_NOME", "X3_TIPO")      // Retorna "C"
cTamanho := GetSX3Cache("A1_NOME", "X3_TAMANHO")  // Retorna tamanho numérico
cValid   := GetSX3Cache("A1_COD",  "X3_VALID")     // Retorna expressão de validação
cContext := GetSX3Cache("A1_COD",  "X3_CONTEXT")   // Retorna "R" ou "V"

// X3Descricao retorna o título do campo (equivalente ao X3_TITULO)
cDesc := X3Descricao("A1_NOME")   // Retorna "Razão Social"

// Uso combinado com X3USO
If X3USO(GetSX3Cache(cCampo, "X3_USADO"))
    // Campo está habilitado para uso
EndIf
```

### 14.2 Posicione

`Posicione` busca um registro em qualquer tabela por uma chave e retorna o conteúdo de um campo. É uma das funções mais utilizadas no desenvolvimento Protheus.

```advpl
// Sintaxe: Posicione(cAlias, nOrdem, cChave, cCampo)

// Buscar nome do cliente
cNome := Posicione("SA1", 1, xFilial("SA1") + cCodCli + cLojaCliente, "A1_NOME")

// Buscar descrição do produto
cDesc := Posicione("SB1", 1, xFilial("SB1") + cCodProd, "B1_DESC")

// Buscar descrição de tabela genérica SX5
cTipo := Posicione("SX5", 1, xFilial("SX5") + "02" + cTipoCli, "X5_DESCRI")

// Buscar razão social do fornecedor
cRazao := AllTrim(Posicione("SA2", 1, xFilial("SA2") + cCodFor + cLojaFor, "A2_NOME"))

// IMPORTANTE: Posicione afeta a posição atual da tabela!
// Use GetArea()/RestArea() para preservar a área:
Local aArea := GetArea()
cNome := Posicione("SA1", 1, xFilial("SA1") + cCod + cLoja, "A1_NOME")
RestArea(aArea)
```

**Alternativa moderna: GetAdvFVal**

```advpl
// GetAdvFVal retorna múltiplos campos de uma só vez
aResult := GetAdvFVal("SA1", {"A1_NOME", "A1_TIPO", "A1_CGC"}, ;
                      {1}, {xFilial("SA1") + cCod + cLoja})
cNome := aResult[1]
cTipo := aResult[2]
cCGC  := aResult[3]
```

### 14.3 ExecAuto e MsExecAuto

`MsExecAuto` (ou `ExecAuto`) automatiza a execução de rotinas padrão do Protheus — inclusão, alteração e exclusão de registros — sem necessidade de interface com o usuário. A função respeita todas as validações do dicionário (SX3_VALID, SX7, etc.).

```advpl
// Estrutura básica do MsExecAuto
User Function zIncluiProduto()
    Local aArea       := FWGetArea()
    Local lAutomatico := IsBlind()

    // Variáveis PRIVATE obrigatórias
    Private lMsErroAuto    := .F.
    Private lMsHelpAuto    := .T.   // Não exibe janelas de erro
    Private lAutoErrNoFile := .T.   // Não gera arquivo de log

    // Array de dados: {NomeCampo, Valor, Nil}
    Local aVetor := {;
        {"B1_COD",   "PROD001",          Nil},;
        {"B1_DESC",  "Produto de Teste", Nil},;
        {"B1_TIPO",  "PA",               Nil},;
        {"B1_UM",    "UN",               Nil},;
        {"B1_IPI",   0,                  Nil},;
        {"B1_PICM",  12,                 Nil} ;
    }

    Begin Transaction
        // Parâmetros: função, array de dados, operação (3=Incluir, 4=Alterar, 5=Excluir)
        MsExecAuto({|x, y| Mata010(x, y)}, aVetor, 3)

        If lMsErroAuto
            // Tratar erro
            aErro := MostraErro()
            ConOut("Erro: " + aErro)
            DisarmTransaction()
        EndIf
    End Transaction

    FWRestArea(aArea)
Return
```

```advpl
// ExecAuto com cabeçalho e itens (Modelo 2)
User Function zIncluiPedido()
    Private lMsErroAuto := .F.

    // Array de cabeçalho
    Local aHeader := {;
        {"C5_FILIAL",  xFilial("SC5"), Nil},;
        {"C5_CLIENTE", "000001",       Nil},;
        {"C5_LOJACLI", "01",           Nil},;
        {"C5_EMISSAO", dDatabase,      Nil} ;
    }

    // Array de itens (array de arrays)
    Local aItems := {;
        {{"C6_PRODUTO", "PROD001", Nil}, {"C6_QTDVEN", 10, Nil}, {"C6_PRUNIT", 25.50, Nil}},;
        {{"C6_PRODUTO", "PROD002", Nil}, {"C6_QTDVEN",  5, Nil}, {"C6_PRUNIT", 12.00, Nil}} ;
    }

    Begin Transaction
        MsExecAuto({|x, y, z| MATA460(x, y, z)}, aHeader, aItems, 3)
        If lMsErroAuto
            MostraErro()
            DisarmTransaction()
        EndIf
    End Transaction
Return
```

**Operações disponíveis:**

| Código | Operação |
|--------|----------|
| `3` | Inclusão |
| `4` | Alteração |
| `5` | Exclusão |

**Variáveis PRIVATE de controle:**

| Variável | Valor Inicial | Descrição |
|----------|--------------|-----------|
| `lMsErroAuto` | `.F.` | `.T.` se houve erro na execução |
| `lMsHelpAuto` | `.T.` | Captura mensagens sem exibir janela |
| `lAutoErrNoFile` | `.T.` | Não gera arquivo de log em disco |

### 14.4 FWMGetDef

`FWMGetDef` retorna o valor padrão (`X3_RELACAO`) de um campo do dicionário. Útil no MVC para inicializar campos com seus defaults.

```advpl
// Sintaxe: FWMGetDef(cTabela, cCampo)

// Obter valor default do campo A1_TIPO na tabela SA1
xDefault := FWMGetDef("SA1", "A1_TIPO")

// Em modelos MVC, inicializar campos com defaults do dicionário
oModel := FWLoadModel("MATA030")
oModel:SetValue("SA1", "A1_TIPO", FWMGetDef("SA1", "A1_TIPO"))
```

### 14.5 FieldPos, FieldGet, FieldPut

Estas funções manipulam campos pela posição física na workarea — sem dependência do nome do campo.

```advpl
// FieldPos(cNomeCampo) — retorna a posição numérica do campo
nPos := FieldPos("A1_COD")      // Retorna, ex: 3
If nPos == 0
    ConOut("Campo não encontrado na workarea atual!")
EndIf

// FieldGet(nPosicao) — retorna o conteúdo do campo
DbSelectArea("SA1")
DbSetOrder(1)
DbSeek(xFilial("SA1") + "000001" + "01")
cCod  := FieldGet(FieldPos("A1_COD"))     // Valor do A1_COD
cNome := FieldGet(FieldPos("A1_NOME"))    // Valor do A1_NOME

// FieldPut(nPosicao, xValor) — grava valor no campo
RecLock("SA1", .F.)
FieldPut(FieldPos("A1_EMAIL"), "novo@email.com")
SA1->(MsUnlock())

// Uso combinado típico
Local nI
For nI := 1 To FCount()  // Percorre todos os campos da workarea
    ConOut(FieldName(nI) + " = " + cValToChar(FieldGet(nI)))
Next nI
```

### 14.6 Funções de SX5

| Função | Assinatura | Descrição |
|--------|-----------|-----------|
| `Posicione` | `Posicione("SX5",1,xFilial+tab+chave,"X5_DESCRI")` | Retorna descrição pelo índice |
| `SX5Desc` | `SX5Desc(cTabela, cChave)` | Retorna descrição diretamente |
| `fDescSX5` | `fDescSX5(1)` | Retorna descrição do registro posicionado |
| `FWGetSX5` | `FWGetSX5(cTabela, cChave, cIdioma)` | Retorna array com dados do registro |
| `FWPutSX5` | `FWPutSX5(cFlavour, cTabela, cChave, cDescPT, cDescEN)` | Cria/atualiza registro |

### 14.7 Funções de SX6

| Função | Assinatura | Descrição |
|--------|-----------|-----------|
| `GetMV` | `GetMV(cParam, lConsulta, xDefault)` | Obtém valor do parâmetro |
| `SuperGetMV` | `SuperGetMV(cParam, lHelp, cPadrao, cFilial)` | Obtém valor com cache |
| `PutMV` | `PutMV(cParam, xValor)` | Altera valor do parâmetro |

### 14.8 Funções de SX7 e SX8

| Função | Descrição |
|--------|-----------|
| `ExistTrigger(cCampo)` | Verifica se existe gatilho para o campo |
| `RunTrigger(cCampo, [nLinha])` | Executa o gatilho do campo informado |
| `GetSXENum(cAlias, cCampo)` | Obtém próximo número sequencial |
| `ConfirmSX8()` | Confirma a numeração gerada por GetSXENum |
| `RollBackSX8()` | Desfaz a numeração gerada por GetSXENum |

---

## 15. Customização via Dicionário

### 15.1 Campos reais vs. virtuais

#### Campo Real (`X3_CONTEXT = "R"`)

- Cria uma coluna física no banco de dados
- O valor é persistido entre sessões
- Deve ser usado para armazenar dados que precisam de persistência

```advpl
// Exemplo: criando campo real via código
// X3_CAMPO   = "ZZ1_CODREF"
// X3_TIPO    = "C"
// X3_TAMANHO = 15
// X3_CONTEXT = "R"   ← persiste no banco
```

#### Campo Virtual (`X3_CONTEXT = "V"`)

- **Não cria coluna no banco de dados**
- Existe apenas em memória durante a execução de uma rotina
- Útil para cálculos, totalizadores, formatações exibidas na tela
- Geralmente preenchido via `X3_RELACAO` (inicializador) ou gatilhos (SX7)

```advpl
// Exemplo: campo virtual para exibir descrição do produto
// X3_CAMPO   = "ZZ1_DESCP"    ← campo virtual
// X3_TIPO    = "C"
// X3_TAMANHO = 40
// X3_CONTEXT = "V"            ← não persiste no banco
// X3_RELACAO = "Posicione('SB1',1,xFilial('SB1')+M->ZZ1_PROD,'B1_DESC')"
// X3_BROWSE  = "S"            ← exibido na listagem

// Para o browse de campos virtuais, usa-se X3_INIBRW
// X3_INIBRW  = "Posicione('SB1',1,xFilial('SB1')+ZZ1->ZZ1_PROD,'B1_DESC')"
// (No browse, o contexto é a própria tabela, sem prefixo M->)
```

### 15.2 Contexto compartilhado vs. exclusivo

A decisão de tornar uma tabela compartilhada ou exclusiva (`X2_MODO`) tem impacto direto na consulta dos dados:

```advpl
// Para tabela EXCLUSIVA ("E"):
// xFilial("SA1") retorna o código da filial atual (ex: "01")
// A chave de busca inclui a filial: "01" + "000001" + "01"
cNome := Posicione("SA1", 1, xFilial("SA1") + cCod + cLoja, "A1_NOME")

// Para tabela COMPARTILHADA ("C"):
// xFilial("SB1") retorna espaços em branco "  "
// A chave de busca: "  " + "PROD001"
cDesc := Posicione("SB1", 1, xFilial("SB1") + cCodProd, "B1_DESC")

// A função xFilial() cuida automaticamente disso!
// Nunca hardcode a filial — sempre use xFilial("ALIAS")
```

### 15.3 Convenções de nomenclatura

A TOTVS reserva faixas de nomes para customizações de clientes e parceiros:

| Prefixo | Destinado a |
|---------|-------------|
| `SA`..`SZ`, `S0`..`S9` | Uso exclusivo TOTVS |
| `ZA`..`ZZ`, `Z0`..`Z9` | **Customizações de clientes** |
| `YA`..`YZ` | Uso de parceiros/consultores |

```advpl
// Nomenclatura correta para campos customizados:
// ZZ1_CODREF  ← tabela ZZ1, prefixo ZZ1, campo CODREF
// A1_ZCAMPO   ← campo customizado na tabela SA1 (prefixo "A1_Z")

// NUNCA use:
// A1_CAMPO  ← pode colidir com campo TOTVS em update futuro
```

### 15.4 Boas práticas

#### Quando usar dicionário vs. hard-coded

```advpl
// USE O DICIONÁRIO quando:
// - Precisar de campo novo em tabela existente
// - Precisar de validação reutilizável
// - Precisar de consulta F3 reutilizável
// - Precisar de parâmetro configurável pelo usuário

// EVITE hard-coded quando:
// - A informação pode variar por empresa/filial
// - A regra pode mudar sem recompilação
// - Existe equivalente no dicionário
```

#### Acesso ao dicionário: performance

```advpl
// MAU USO: acesso direto à SX3 em laços
For nI := 1 To nTot
    DbSelectArea("SX3")         // ← abre e fecha área repetidamente
    DbSeek("A1_COD")
    cTitulo := SX3->X3_TITULO
Next nI

// BOM USO: GetSX3Cache usa cache interno
For nI := 1 To nTot
    cTitulo := GetSX3Cache("A1_COD", "X3_TITULO")  // ← cache!
Next nI
```

#### X3_VALID e funções fiscais

```advpl
// Campos fiscais frequentemente usam MaFisRef()
// X3_VALID = "MaFisRef('CF0_CLAFI','ZA0',M->CF0_CLAFI)"

// ExistCpo() verifica existência em outra tabela
// X3_VALID = "ExistCpo('SA1')"         // campo atual existe em SA1
// X3_VALID = "ExistCpo('SB1', M->C6_PRODUTO)"  // produto específico

// Expressão negativa: campo não pode ficar vazio E deve existir
// X3_VALID = "!Empty(M->A1_COD) .And. ExistCpo('SA1')"
```

#### Campos obrigatórios vs. validação

```advpl
// X3_OBRIGAT (CHAR(8), bitmap) → quando preenchido via API, o sistema verifica
//                                se o campo está vazio ANTES de chamar X3_VALID.
//                                ATENÇÃO: setar "S" via SQL direto é silenciosamente
//                                ignorado em v12.1.7+. Para forçar obrigatoriedade
//                                de forma confiável, use X3_VALID = "!Empty(M->CAMPO)".
// X3_VALID                     → expressão adicional de validação de conteúdo

// Ordem de verificação pelo sistema:
// 1. X3_WHEN  → campo está habilitado?
// 2. X3_OBRIGAT → campo está vazio? (se bitmap obrigatório estiver setado, rejeita)
// 3. X3_VALID → expressão de validação
// 4. X3_TRIGGER → executa gatilhos SX7 (se X3_TRIGGER = "S")
```

#### Atualização do dicionário — ferramenta correta

```advpl
// RECOMENDADO: use o Configurador (SIGACFG)
// Base de Dados > Dicionário > Base de Dados
// Alterações pelo Configurador são replicadas automaticamente para o banco

// Via código: use apenas para distribuição de patches/instaladores
// NUNCA manipule o dicionário diretamente em produção via fonte ADVPL
// O TOTVS Code Analysis aponta acesso direto ao dicionário como ofensor

// CORRETO para distribuição:
User Function zInstalaDict()
    // Usa funções oficiais de instalação de dicionário
    // ou ExecAuto das rotinas do Configurador
    FWCallProgram("CFGX031")   // Abre o Configurador programaticamente
Return
```

---

## 15. Cookbook — criando campo SX3 customizado via SQL

Receita prática pra criar um campo custom na SX3 quando você precisa scriptar um update (pipeline CI/CD, ambiente sem GUI, atualização em massa). O caminho **oficial TOTVS** continua sendo `FwPutSX3()` em ADVPL ou o Configurador (SIGACFG); use SQL direto só quando esses não couberem no workflow.

> ⚠️ **TOTVS desencoraja manipulação direta do dicionário em produção.** Esta seção é defensiva: documenta o que funciona quando você *já* decidiu ir por SQL, pra você não tomar pé errado.

### 15.1 Regra de ouro: clonar bitmaps via subselect

`X3_USADO` (varchar(120) — bitmap de módulos) e `X3_RESERV` (varchar(16) — bitmap de propriedades) são controlados por API a partir de v12.1.7. **Não invente os valores**: clone de campo similar da mesma tabela usando `INSERT ... SELECT`.

```sql
-- ❌ Errado (parece funcionar — campo aparece no dbstruct — mas a tela ignora):
INSERT INTO sx3xxx (..., x3_usado, ...)
VALUES (..., '111111111111111111', ...);   -- bitmap inventado

-- ✅ Certo (bitmap clonado de campo similar via subselect):
INSERT INTO sx3xxx (..., x3_usado, x3_reserv, ...)
SELECT ..., x3_usado, x3_reserv, ...
  FROM sx3xxx
 WHERE x3_arquivo='SB1' AND x3_campo='B1_FAMILIA' AND d_e_l_e_t_=' ';
```

Validação rápida: `SELECT length(x3_usado) FROM sx3xxx WHERE x3_campo='SEU_CAMPO  '` deve devolver algo entre **113 e 120** chars. Se for muito menor, o bitmap está malformado.

### 15.2 Workflow (3 fases)

Pra campo Real (não-virtual) numa tabela existente:

```sql
BEGIN;

-- Fase 1: coluna física no banco (só se x3_context='R')
ALTER TABLE sb1xxx ADD COLUMN b1_znovo VARCHAR(1) NOT NULL DEFAULT ' ';

-- Fase 2: registro SX3 clonando bitmaps de campo template
INSERT INTO sx3xxx (
  x3_arquivo, x3_ordem, x3_campo, x3_tipo, x3_tamanho, x3_decimal,
  x3_titulo, x3_titspa, x3_titeng,
  x3_descric, x3_descspa, x3_desceng,
  x3_picture, x3_valid, x3_usado, x3_relacao, x3_f3, x3_nivel, x3_reserv,
  x3_browse, x3_visual, x3_context, x3_obrigat,
  x3_cbox, x3_when, x3_grpsxg, x3_folder, x3_propri, x3_trigger,
  d_e_l_e_t_
)
SELECT
  'SB1', 'ZA', 'B1_ZNOVO  ',                      -- arquivo, ordem (Z* p/ custom), campo (10 chars padded)
  'C', 1, 0,                                       -- tipo C, tamanho 1
  'Novo Cmp  ', 'Novo Cmp  ', 'New Field  ',       -- títulos (12 chars padded - sem acentos)
  'Descricao do Campo Novo  ',                     -- descric PT (25 chars)
  'Descripcion Campo Nuevo  ', 'New Field Desc           ',
  '@!', 'Pertence("FC")',                          -- picture, valid (Pertence valida combo)
  x3_usado,                                        -- CLONADO do template
  '', '', 1,
  x3_reserv,                                       -- CLONADO do template
  'N', ' ', ' ', '        ',                       -- browse=N, visual/context vazio, obrigat vazio (8 chars)
  'F=FOB;C=CIF',                                   -- cbox: storage=val, label=val
  '', '   ', '1',                                  -- when, grpsxg vazio, folder='1'
  'U', '',                                         -- propri=U (custom), sem trigger
  ' '
  FROM sx3xxx
 WHERE x3_arquivo='SB1' AND x3_campo='B1_FAMILIA' AND d_e_l_e_t_=' ';

-- Fase 3: invalidar cache do dicionário
-- (o mecanismo depende do ambiente — Configurador faz automaticamente.
--  Via SQL puro, sinalize a tabela de controle de metadata do DBAccess
--  conforme a documentação da release; ou reinicie dbaccess + appserver.)

COMMIT;
```

Depois do COMMIT, **invalidar cache** (restart `dbaccess` + appserver, ou comando equivalente) e validar via REST `dbstruct?alias=SB1` ou em ADVPL com `DbStruct("SB1")` que o campo aparece.

### 15.3 Checklist pré-INSERT em sx3xxx

- [ ] `x3_arquivo` = alias existe em SX2 (`SELECT 1 FROM sx2xxx WHERE x2_chave='SB1'`)
- [ ] `x3_campo` ≤ 10 chars, padded com espaço (`'B1_ZNOVO  '`)
- [ ] `x3_ordem` único na tabela (`SELECT MAX(x3_ordem) FROM sx3xxx WHERE x3_arquivo='SB1'`)
- [ ] Prefixo custom (`Z*` ou `X*`) — evita colisão em upgrade TOTVS
- [ ] `x3_propri='U'` se custom
- [ ] `x3_tipo` ∈ {`C`, `N`, `D`, `M`, `L`}
- [ ] `x3_usado` / `x3_reserv` **CLONADOS** via subselect — não inventar
- [ ] `x3_browse` ∈ {`S`, `N`, vazio} — **nunca `1`, `0` ou outros**
- [ ] `x3_visual` ∈ {`A`, `V`, vazio}
- [ ] `x3_context` ∈ {`R`, `V`, vazio}
- [ ] `x3_folder` setado se quer aparecer na tela MVC (conferir SXA antes pra usar valor existente)
- [ ] Se `x3_context='R'`, `ALTER TABLE` físico **antes** do INSERT
- [ ] `x3_titulo` ≤ 12 chars; `x3_descric` ≤ 25 chars — **sem acentos** (bancos legados costumam ser CP1252; scripts UTF-8 + DB CP1252 = mojibake)
- [ ] Se combo: `x3_cbox='val=Label;val=Label'` **E** `x3_valid="Pertence('VALS')"` (defesa dupla)
- [ ] Pós-INSERT: invalidar cache do dicionário antes de testar na tela

### 15.4 Armadilhas frequentes

| Sintoma | Causa | Fix |
|---|---|---|
| Campo aparece no `dbstruct` REST mas não na tela | `x3_browse='1'` (ou valor fora de S/N/vazio) | `UPDATE x3_browse='N'` |
| Campo aparece no `dbstruct` mas tela "Cadastrais" não exibe | `x3_folder` vazio ou referenciando pasta inexistente | `UPDATE x3_folder='1'` (ou folder existente em SXA) |
| INSERT passou mas tela ignora completamente | `x3_usado` formato inventado (literal `'111…'`) | Clonar de campo similar via SELECT subselect |
| `x3_obrigat='S'` não força preenchimento | Coluna é bitmap controlado por API; valor `'S'` ignorado | Usar `x3_valid='!Empty(M->CAMPO)'` |
| Acentos viram `?` ou mojibake no `x3_titulo` | Banco em CP1252 + script em UTF-8 | Manter títulos ASCII puro (sem acentos) |
| Combo aparece vazio mesmo com `x3_cbox` preenchido | Formato errado (sem `=` ou sem `;`) | Formato literal: `val=Label;val=Label` |
| Cache de dicionário não atualiza após INSERT | Faltou invalidar o cache do DBAccess | Restart `dbaccess` + appserver, ou usar Configurador |

### 15.5 Validação visual (template de QA)

Compare o campo novo contra um template conhecido — `len_usado` muito menor que ~115 indica INSERT errado:

```sql
SELECT
  campo,
  x3_ordem, x3_folder, x3_browse, x3_visual, x3_context, x3_propri,
  length(x3_usado)  AS len_usado,    -- esperado entre 113 e 120
  length(x3_reserv) AS len_reserv,   -- esperado > 0 quando clonado
  x3_cbox
FROM (
  SELECT 'NOVO' AS campo, * FROM sx3xxx
   WHERE x3_arquivo='SB1' AND x3_campo='B1_ZNOVO   ' AND d_e_l_e_t_=' '
  UNION ALL
  SELECT 'TPLT' AS campo, * FROM sx3xxx
   WHERE x3_arquivo='SB1' AND x3_campo='B1_FAMILIA' AND d_e_l_e_t_=' '
) t;
```

Saída deve ter `NOVO` e `TPLT` com mesmos valores em colunas de comportamento (`x3_folder`, `x3_browse`, `x3_visual`, `x3_context`, `x3_propri`, `len_usado`, `len_reserv`), divergindo só em `x3_ordem`, `x3_campo`, `x3_titulo`, `x3_cbox`.

---

## Referências

- [TDN TOTVS — Guia do Dicionário de Dados](https://tdn.totvs.com/pages/releaseview.action?pageId=22479484)
- [TDN TOTVS — SX2 Tabelas de Dados](https://tdn.totvs.com/display/framework/SX2+-+Tabelas+de+Dados)
- [TDN TOTVS — SX3 Campos das Tabelas](https://tdn.totvs.com/display/public/framework/SX3+-+Campos+das+tabelas)
- [TDN TOTVS — SX7 Gatilhos de Campos](https://tdn.totvs.com/display/framework/SX7+-+Gatilhos+de+Campos)
- [TDN TOTVS — SX9 Relacionamento entre Tabelas](https://tdn.totvs.com/pages/viewpage.action?pageId=22479673)
- [TDN TOTVS — SX1 Perguntas do Usuário](https://tdn.totvs.com/pages/viewpage.action?pageId=22479548)
- [TDN TOTVS — SuperGetMV](https://tdn.engpro.totvs.com.br/display/public/PROT/SuperGetMv)
- [ProtheusAdvpl — Funções do Dicionário de Dados](https://protheusadvpl.com.br/category/protheus/programacao/advpl/advpl-ii/funcoes-do-dicionario-de-dados/)
- [ProtheusAdvpl — GetSX3Cache](https://protheusadvpl.com.br/getsx3cache/)
- [ProtheusAdvpl — Posicione](https://protheusadvpl.com.br/posicione/)
- [ProtheusAdvpl — GetSXENum](https://protheusadvpl.com.br/getsxenum/)
- [Terminal de Informação — Criando tabelas a quente](https://terminaldeinformacao.com/2015/10/05/criando-tabelas-campos-e-indices-a-quente-no-protheus/)
- [Terminal de Informação — Conhecendo a SX9](https://terminaldeinformacao.com/2020/08/21/conhecendo-a-tabela-de-relacionamentos-do-protheus-sx9/)
- [Terminal de Informação — Controle de numerações SX8](https://terminaldeinformacao.com/2023/11/04/controle-de-numeracoes-usando-confirmsx8-getsxenum-e-rollbacksx8-maratona-advpl-e-tl-088/)
- [Terminal de Informação — Função para criar SXB via ADVPL](https://terminaldeinformacao.com/2018/08/07/funcao-para-criar-uma-consulta-f3-sxb-advpl/)
- [Terminal de Informação — Parâmetros GetMV e SuperGetMV](https://terminaldeinformacao.com/2024/03/07/buscando-conteudos-de-parametros-com-getmv-e-supergetmv-maratona-advpl-e-tl-279/)
- [Terminal de Informação — MsExecAuto](https://terminaldeinformacao.com/2024/04/17/atualizando-informacoes-atraves-da-msexecauto-maratona-advpl-e-tl-360/)
- [SemPreju — Metadado SX7 Gatilhos](https://sempreju.com.br/metadado-sx7-gatilhos-de-campos/)
- [SemPreju — SX5 Tabelas Genéricas](https://sempreju.com.br/entendendo-o-sx5-tabelas-genericas-do-protheus/)
- [Mastersiga — SX1 Perguntas do Usuário](https://mastersiga.tomticket.com/kb/configurador/sx1-perguntas-do-usuario)
- [Mastersiga — Particularidades da SX3](https://mastersiga.tomticket.com/kb/configurador/informacoes-e-particularidades-da-tabela-sx3)
- [GitHub dan-atilio — Exemplos ADVPL](https://github.com/dan-atilio/AdvPL)
- [Central Atendimento TOTVS — MsExecAuto exemplos](https://centraldeatendimento.totvs.com/hc/pt-br/articles/360022717031)
- [Central Atendimento TOTVS — GetMV e SuperGetMV](https://centraldeatendimento.totvs.com/hc/pt-br/articles/8188934752535)
