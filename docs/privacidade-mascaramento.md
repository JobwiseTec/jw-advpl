# Privacidade — Mascaramento de dados sensíveis no egress

> Camada **opt-in** que protege dados sensíveis **antes** de qualquer conteúdo sair do plugadvpl
> rumo a um LLM. Desligada por padrão; ligada, mascara **só o que vai sair** — sem mudar o índice,
> sem persistir nada, sem perder a precisão da análise.

---

## 1. O problema

O plugadvpl indexa código-fonte e o entrega para análise por LLM. Esse conteúdo pode conter
**valores sensíveis embutidos**: CPF/CNPJ de massa de teste, senha hardcoded, e-mail, credencial em
URL. Sem proteção, esses valores cruzam a fronteira para a API do modelo.

A camada de privacidade intercepta no **ponto único de saída** (`output.render`) e troca o que é
sensível **antes** do envio. O dado real **nunca sai da máquina**.

---

## 2. O princípio: identifica × decide

Mascarar não é apagar todo valor — é distinguir **o que identifica** do **que decide a lógica**:

| Papel do valor | Exemplo | Ação |
|---|---|---|
| **Identificador** | CPF, CNPJ, e-mail | **tokeniza** (apelido estável) |
| **Segredo** | senha, token, credencial em URL | **redige** (irreversível) |
| **Estrutura / decisão não-sensível** | nome de função/tabela, flag, parâmetro `MV_*`, status | **mantém** (a IA precisa) |

Resultado: a IA enxerga a **mesma lógica**; só não vê os **valores reais**. Comandos que devolvem
metadado estrutural (`arch`, `find`, `tables`, `callers`…) saem **idênticos** ao normal.

---

## 3. Como funciona

### 3.1 Tokenização estável (identificadores)

```
token = HMAC_SHA256(chave_da_sessão, valor_normalizado)
```

- **Estável:** o mesmo valor vira sempre o mesmo token — inclusive entre comandos diferentes
  (processos separados), pois é determinístico, **sem mapa em disco**.
- **De mão única:** não há como reverter o token para o valor (de propósito — o desenvolvedor
  consulta o valor real no próprio fonte/sistema local).
- **Normalizado:** `11.222.333/0001-81` e `11222333000181` → o **mesmo** token.

### 3.2 Dois estilos de token

| Estilo | CPF/CNPJ vira | Quando usar |
|---|---|---|
| `label` (default) | `CNPJ_7F3A9C` | Claro que está mascarado. Bom para grep/comentários. |
| `fpe` (format-preserving) | `94.062.125/5558-17` (fake **válido**, mesma forma) | Quando o valor participa de **lógica posicional** — `SubStr(cCgc,1,8)` pega a raiz, montagem de chave mantém o comprimento. |

O modo `fpe` resolve o caso clássico do **gatilho que fatia o CNPJ para montar uma chave**: o token
mantém 14 dígitos e a raiz é estável, então a IA raciocina **identicamente** sobre a chave — sem o
número real.

### 3.3 Redação de segredos (irreversível)

Reusa o catálogo `lookups/redact_patterns.json` (compartilhado com o parser de compilação):
`password=`, `senha=`, `pwd=`, `psw=`, `aut_file=`, chave hex longa, e **credencial em URL**
(`scheme://user:pass@host` → `scheme://[REDACTED]@host`). Segredo não tem valor de análise → some.

### 3.4 Reconhecedores (precisão por checksum)

- **CPF / CNPJ**: regex de formato **+ dígito verificador** — o checksum elimina o falso-positivo de
  "qualquer 11 dígitos vira CPF". CPF/CNPJ inválido **não** é mascarado.
- **E-mail**: regex.
- **IP**: disponível, mas **opt-in** (evita falso-positivo com número de versão/build).

### 3.5 Bucketização de valores financeiros (opt-in, ciente do campo)

Números sensíveis (limite, saldo, valor) não casam padrão de formato — são "só números". Com
`PLUGADVPL_PRIVACY_BUCKETIZE=1`, colunas cujo **nome** indica valor financeiro (convenção SX3:
`A1_LC`, `ZZ3_VLBASE`, `C5_VALBRUT`…) têm o valor trocado por uma **faixa nomeada** (`50000 →
"~10k-100k"`), preservando a ordem de grandeza sem o R$ real. Números **estruturais** (linha, cc,
loc) e status/flags são **mantidos**. Exemplo de um registro:

```
A1_CGC     -> CNPJ_XOPHAIMQGK   (identificador → token)
A1_MSBLQL  -> 2                 (status → mantido)
A1_LC      -> ~10k-100k         (limite → faixa)
A1_SALDUP  -> ~10k-100k         (saldo → faixa)
```

**Classificação do campo financeiro — duas vias:**

1. **SX3-backed (a verdade do dicionário):** aponte `PLUGADVPL_PRIVACY_FIELDS_FILE` para uma lista
   JSON de campos de valor (gerada do `sx3.csv` com `buckets.financial_fields_from_sx3`). Cobre
   **pedido, produto, custo, estoque, peso, quantidade** — todos `X3_TIPO='N'` com decimais.
   O parâmetro `categories` filtra pela PICTURE (`picture_class`):
   - `("money",)` — só R$ (agrupamento de milhar); pega nomes idiossincráticos (`ZDSC`/`ABAT`/`CM`);
   - `("money","volume")` — R$ **e** peso/quantidade/estoque (volume de negócio sensível),
     excluindo alíquota/percentual público;
   - `None` (default) — **tudo** que é N+decimais (mais abrangente).

   **Bate ~100%** (validado em SX3 real: 4.720 money, 80 volume, 1.012 rate/alíquota).
2. **Heurística de nome (fallback sem SX3):** prefixo `VL/VAL/SAL/PRC` + raízes de tributo. Recall
   **~66%** medido em SX3 real — por isso, com o dicionário disponível, prefira a via 1.

É *single-value* (não dá a razão "105%"); a relativização com razão/desfecho fica para o futuro
comando `diagnose` (ver `docs/privacidade-relativizacao-design.md`).

### 3.6 Garantias de não-corrupção

- **Chaves/IDs numéricos longos** (ex.: chave de acesso NFe de 44 dígitos) **não** são corrompidos:
  os lookarounds impedem mascarar um "CPF/CNPJ substring" dentro de um número maior, e o padrão de
  hex exige ao menos uma letra a-f (número puro = ID, preservado).
- **Estrutura preservada**: chaves de dicionário, tags XML/JSON, SQL ao redor — tudo intacto.

---

## 4. Como ligar

```bash
# por sessão (tokens estáveis entre os comandos da sessão):
export PLUGADVPL_PRIVACY=1
export PLUGADVPL_PRIVACY_KEY=<segredo-da-sessão>     # sem isso, usa chave-dev fixa
export PLUGADVPL_PRIVACY_STYLE=fpe                   # opcional: label (default) | fpe
plugadvpl <comando>

# ou pontual, via flag:
plugadvpl --privacy <comando>
plugadvpl --no-privacy <comando>     # força desligado
```

Variáveis de ambiente:

| Variável | Default | Efeito |
|---|---|---|
| `PLUGADVPL_PRIVACY` | (off) | Liga o mascaramento (`1`/`true`/`on`/`sim`). |
| `PLUGADVPL_PRIVACY_KEY` | chave-dev fixa | Chave HMAC — estabiliza e protege os tokens. **Defina em produção.** |
| `PLUGADVPL_PRIVACY_STYLE` | `label` | `label` ou `fpe`. |
| `PLUGADVPL_PRIVACY_BUCKETIZE` | (off) | Bucketiza valores em colunas financeiras (faixa nomeada). |
| `PLUGADVPL_PRIVACY_FIELDS_FILE` | — | JSON de campos de valor (do SX3) p/ classificação exata. |
| `PLUGADVPL_PRIVACY_RECOGNIZERS` | `cpf,cnpj,email` | Quais entidades mascarar. |
| `PLUGADVPL_PRIVACY_REDACT_SECRETS` | `1` | Redação de segredos via catálogo. |

A flag `--privacy/--no-privacy` sobrepõe a env var.

**Auditoria:** ao mascarar, emite em `stderr` (nunca no `stdout` do LLM) uma contagem por tipo —
`[privacy] mascarado: cnpj=3 email=1 secret=1` — **sem** o valor real.

---

## 5. Desempenho e precisão

- **Custo proporcional ao tamanho da saída** (~0,14 ms/KB). Output real (limitado por `--limit`,
  na casa dos KB): **< 1 ms — imperceptível**. Desligado: **0 ms** (caminho não é nem chamado).
- **Precisão preservada por desenho**: só valores-folha mudam; metadado estrutural sai idêntico.
- **Sem estado, sem disco**: cada comando é um processo efêmero; nada é persistido — o "reset" entre
  sessões é de graça.

---

## 6. Limites (honestos)

- Cobre o que **passa pelo plugadvpl**. Um assistente que leia o `.prw` cru direto (fora da
  ferramenta) não é coberto — proteção total exige um hook no próprio harness, ou rodar a inferência
  dentro do perímetro do cliente (deployment, fora deste escopo).
- **Relativização** de número financeiro (limite → "saldo 105%") é uma fase seguinte — hoje números
  passam intactos (correto para debug).
- **NER de nomes** em texto livre (Presidio/spaCy) é opt-in pesado, fora desta versão.

---

## 7. Arquitetura (resumo)

```
query → output.render()  ──►  [privacy?]  ──►  stdout
                                  │
                          privacy/ (módulo)
                          ├─ brdocs   detecção + checksum CPF/CNPJ
                          ├─ engine   tokeniza (label/fpe) + redige segredos
                          ├─ config   opt-in (env / flag)
                          └─ auditoria (tipo + contagem, sem valor)
```

O gancho fica **dentro de `render()`** (o egress verdadeiramente único), depois do corte por
`--limit` — então o custo é proporcional ao output, não à base. Caminhos de relatório HTML
(`ini-audit`/`log-diagnose --format html`) também são mascarados.
