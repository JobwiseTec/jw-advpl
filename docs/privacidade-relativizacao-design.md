# Relativização — design da próxima fase

> **Objetivo:** proteger **números sensíveis** (limite de crédito, saldo, valor de pedido, salário)
> mostrando a **relação** (“saldo ≈ 105% do limite”) em vez do valor real — para debug de bug
> dependente de dado sem vazar o número. Este documento mapeia as **frentes** de onde isso pode vir
> e recomenda **o melhor caminho**.
>
> **Status:** design / proposta (nada implementado).

---

## 0. Estado atual — o que JÁ temos e o que FALTA

### Blocos de construção prontos (Fase 1 + 2.1)
- ✅ Gancho de mascaramento no egress (`output.render`).
- ✅ **Classificação SX3 de campo** (a verdade do dicionário): identificador (CPF/CNPJ),
  valor `money`/`volume`/`rate` (pela PICTURE), status/flag. — *é o que faltava pra saber o papel
  de cada número.*
- ✅ **Bucketização** (valor único → ordem de grandeza, `~10k-100k`). — *relativiza UM valor.*
- ✅ Tokenização estável de identificadores.

### O que ainda FALTA pra relativizar com razão/desfecho ("saldo 105% do limite")
A bucketização relativiza **um** valor (magnitude). A relativização verdadeira precisa de **dois**
valores e da **relação** entre eles — e isso exige peças que ainda não existem:

| # | Peça que falta | Por quê | Tamanho |
|---|---|---|---|
| 1 | **Extrair os pontos de decisão do fonte** | Saber, em cada `If`, QUAIS campos são comparados e com QUAL operador (`saldo < limite`). O parser hoje extrai funções/tabelas/chamadas, não os operandos das comparações. | médio (parsing novo) |
| 2 | **Relação entre campos** | Saber que `A1_SALDUP` se compara com `A1_LC`. Vem da extração (#1) ou de um mapa curado. | pequeno (deriva de #1) |
| 3 | **Caminho do dado do registro** | O valor real de `A1_LC` para *um* cliente só existe num registro. O plugadvpl indexa **fonte + SX**, não registros. Precisa de um input: o dev cola os valores, ou um comando consulta o banco. | médio→grande |
| 4 | **Motor `diagnose`** | Junta fonte (decisões #1) + registro (valores #3), computa o **desfecho** de cada comparação e **relativiza** os operandos sensíveis (`saldo 103% > limite: TRUE`). | médio |
| 5 | **Comando + formato do trace** | A CLI `plugadvpl diagnose <rotina> <registro>` e a saída legível do trace relativizado. | pequeno |

### Caminho incremental sugerido
1. **Extração de comparações do fonte** (#1) — sozinho já entrega valor: "quais campos decidem este
   bloqueio". Não precisa de dado de registro.
2. **Input de registro** (#3) — começar pelo mais simples (o dev cola os valores; o filtro já
   mascara/bucketiza na entrada).
3. **Motor `diagnose`** (#4) — cruza #1 + #3, computa desfecho, relativiza.
4. **Comando + trace** (#5).

> **A dependência incontornável:** relativização precisa do **valor do registro** (#3), que hoje está
> fora do plugadvpl. É a peça que define onde a feature mora — por isso o `diagnose` é um comando
> novo, não um ajuste no mascarador de texto.

---

## 1. O que muda em relação à Fase 1

A Fase 1 mascara **identificadores** (CPF/CNPJ/e-mail) e **segredos** — coisas que casam um
**padrão de formato**. Relativização é outra natureza: um número como `48000` **não tem formato
sensível** (é só um número), e o que importa não é o número em si, mas a **relação** dele com outro
(`saldo < limite`, `saldo 105% do limite`).

---

## 2. A tensão central (por que é difícil)

Relativizar exige **duas coisas que o mascarador de texto da Fase 1 não tem**:

1. **Semântica de campo** — saber que *este* número é um limite de crédito (sensível) e *aquele* é um
   status (manter). Um número sozinho não se identifica.
2. **Contexto de comparação** — “105%” precisa de **dois valores** (saldo E limite) e da relação
   entre eles. O mascarador vê uma célula por vez.

> **Realização-chave:** relativização **não pertence ao caminho do código-fonte** — pertence ao
> caminho do **dado transacional**. No fonte, os números são literais (regra de negócio que a IA
> precisa ver) ou referências de campo (`A1_LC`, sem valor em runtime). O valor real de `A1_LC` para
> *um cliente* só existe quando alimentamos a IA com o **registro** — e é aí, e só aí, que
> relativização faz sentido. Hoje o plugadvpl indexa **fonte + dicionário SX**, não registros. Logo,
> relativização **depende de uma capacidade nova**: lidar com valores de registro.

---

## 3. As frentes — onde números sensíveis aparecem, e o melhor tratamento de cada

| Frente | Exemplo | Tem contexto de comparação? | Melhor tratamento |
|---|---|---|---|
| **A. Parâmetro SX6 / `MV_*`** | `MV_LIMITE = 50000` | Não (valor único) | **Bucket** (“faixa 10k–100k”), ciente do campo |
| **B. Literal em SQL / código** | `WHERE C5_VALBRUT > 100000` | Não (é regra de negócio) | **Manter** (a IA precisa da regra); opcional bucket se a política for sensível |
| **C. Valor de registro (debug)** | `A1_LC=50000, A1_SALDUP=51500` p/ um cliente | **Sim** (vs limite, vs pedido) | **Relativizar** (“saldo 103% do limite”) — via comando dedicado |
| **D. Comparação no fonte** | `If nSaldo < nLimite` | Estrutura, sem valores | **Manter** (é a lógica) |
| **E. Valor em log** | `limite=50000 saldo=51500` | Às vezes (o log já traz o par) | **Bucket** ou aproveitar o desfecho já logado |

**Conclusão das frentes:** três comportamentos distintos —
**manter** (regra/estrutura: B, D), **bucketizar** (valor único sensível: A, E),
**relativizar** (par com contexto: C). Só **C** precisa do contexto de comparação — e é o caso de
maior valor (o “cliente bloqueado indevidamente”).

---

## 4. Os caminhos de implementação (do mais simples ao mais completo)

### Caminho 1 — Bucketização ciente do campo *(fundação, baixo esforço)*
Estende o mascarador do egress para ser **ciente do campo**: usando `campos_semantica.json`, marca
colunas/campos financeiros e troca o número pela **faixa/ordem de grandeza** (`48000 → "~10k–100k"`).
- **Onde:** o mascarador passa a operar por **linha+coluna** (hoje é por valor), consultando a
  semântica do campo.
- **Cobre:** frentes A e E (valor único). **Não** dá a razão precisa.
- **Pró:** simples, determinístico, sem contexto; protege o R$ sem quebrar a magnitude.
- **Contra:** coarse — “saldo faixa X vs limite faixa X” não diz se saldo>limite.

### Caminho 2 — Relativização par-a-par *(precisa do par na mesma linha)*
Quando uma linha traz **ambos** os campos relacionados (saldo **e** limite), computa a razão e emite
“saldo ≈ 105% do limite”.
- **Onde:** pós-processador de linha + um **mapa de relações** curado (qual campo relativiza contra qual).
- **Pró:** dá a razão diagnóstica.
- **Contra:** frágil — exige os dois campos juntos no mesmo output; mapa curado.

### Caminho 3 — Comando `diagnose` / `trace` *(a casa natural da relativização)*
Um **comando novo** que recebe uma rotina + um registro, **avalia os pontos de decisão** e emite um
**trace relativizado**: “entrou no IF da linha 88 (saldo 103% > limite: TRUE); `MV_X_LIBLIM='N'` →
bloqueia”.
- **Onde:** novo comando que lê os pontos de decisão do fonte (o parser/lint já extrai estrutura) e
  liga os valores do registro, computando os **desfechos** — relativizando os operandos sensíveis.
- **Pró:** tem o contexto de comparação **por construção**; serve direto o caso de debug; aqui o
  “105%” mora corretamente.
- **Contra:** feature maior — precisa casar pontos-de-decisão ↔ valores de registro.

### Caminho 4 — Debug diferencial *(extensão do diagnose)*
Compara dois registros (um com problema, um sem) e mostra **só a diferença** relativizada
(“o bloqueado pertence a grupo com saldo 105%; o liberado não tem grupo”).
- **Pró:** mata o enigma por comparação, sem expor nenhum dos dois.
- **Contra:** precisa de dois registros; extensão do comando.

### Caminho 5 — Hook no harness *(fora do plugin)*
Como o plugadvpl não vê o registro a menos que alguém o traga, parte da relativização pode viver num
**hook do harness** que intercepta valores de registro colados/consultados. Fora do escopo do plugin,
mas é onde a cobertura total mora.

---

## 5. O melhor caminho (recomendação)

**Não tentar embutir relativização no mascarador de texto genérico** — ele não tem contexto. Em vez
disso, uma abordagem **em camadas**, do alicerce ao diferencial:

1. **Alicerce — Bucketização ciente do campo (Caminho 1).** Extensão direta do mascarador atual para
   ser *ciente do campo* via `campos_semantica.json`. Protege número sensível único (SX6/`MV_*`,
   colunas de valor, logs) com baixo esforço e boa cobertura. **É o primeiro passo concreto.**

2. **Diferencial — Comando `diagnose` (Caminho 3).** A casa correta da relativização verdadeira
   (razão + desfecho). Serve o caso real de debug (“por que bloqueou?”). Maior esforço, maior valor —
   é o que transforma “mascaramento” em “debug seguro de dado”.

3. **Extensão — Diferencial (Caminho 4)** sobre o `diagnose`, quando houver demanda.

**Escopo honesto:** relativização atua no **caminho do dado** (registro/param/log), **não** no
caminho de metadado de fonte. No fonte, número é regra de negócio → **mantido**. Isso evita o erro de
“relativizar a lógica” e degradar a análise.

---

## 6. O que construir primeiro (MVP da próxima fase)

**Fase 2.1 — mascaramento ciente do campo (bucketize):**
- Estender o mascarador para receber a **coluna** junto do valor (`mask_row` ciente de coluna).
- Tabela de política por campo derivada de `campos_semantica.json`:
  `financeiro/valor → bucketize` · `identificador → tokeniza` · `status/flag → mantém`.
- Buckets configuráveis (ordem de grandeza ou faixas).
- Cobrir onde colunas = campos: SX6 (valor de `MV_*`), e qualquer output futuro com colunas de campo.
- Testes: valor financeiro vira faixa; status mantém; identificador tokeniza; off = idêntico.

**Fase 2.2 — comando `diagnose` (a relativização de verdade):** projeto à parte, depois do alicerce.

---

## 7. Decisões em aberto (suas)

1. **Buckets:** ordem de grandeza (`~10^4`) ou faixas nomeadas (`10k–100k` / `100k–1M`)?
2. **Literais de regra no fonte** (ex.: `> 100000`): manter sempre (é lógica) ou bucketizar quando a
   política de crédito for considerada sensível?
3. **`diagnose`:** vale o investimento no comando dedicado agora, ou começamos só com a bucketização
   ciente do campo e medimos o ganho antes?
4. **Origem do registro no `diagnose`:** o dev cola os valores, ou o comando consulta o banco
   (exigiria credencial — entra na esteira de segurança)?
