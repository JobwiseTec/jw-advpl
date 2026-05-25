# Como extrair o dicionário SX do Protheus em 1 comando (e cruzar com seus fontes em segundos)

> **Sub-título:** Pare de exportar CSVs manualmente do SIGACFG. O `plugadvpl` puxa os 21 arquivos do dicionário direto do AppServer via REST e indexa tudo em SQLite local — pronto pra análise de impacto em qualquer customização.

## O problema real

Toda customização Protheus sólida começa entendendo o dicionário SX. Quais campos da SA1 já existem? Onde o campo `B1_PRV1` é usado? Esse gatilho SX7 que estou criando, vai disparar em cascata pra mais quê? O parâmetro `MV_LJTOPRT` aparece em que rotinas?

Quem trabalha com Protheus há tempo conhece os dois caminhos clássicos:

**Caminho A — manual via SIGACFG:**
1. Logar no Configurador
2. Misc → Exportar Dicionário em CSV
3. Esperar gerar 11 arquivos (SX1, SX2, SX3, SX5, SX6, SX7, SX9, SXA, SXB, SXG, SIX)
4. Pegar o ZIP
5. Descompactar localmente
6. Abrir cada CSV no Excel pra procurar o que precisa
7. Cruzar manualmente com os fontes

Lento, repetitivo, e o cruzamento "ver onde esse campo é usado nos fontes" continua manual.

**Caminho B — pedir pro TI do cliente exportar:**

Aí você vira refém do calendário do TI do cliente. Pediu hoje? Recebe semana que vem. E quando recebe, já é foto velha do dicionário.

**Caminho C — não cruzar com fontes e só "ler o código":**

Aí você gasta 2 horas procurando todas as referências de um campo via `grep`/Ctrl+F. Esquece de algumas. Cria gatilho. Quebra produção. Repete.

## A solução

O **`plugadvpl`** (CLI Python open-source, MIT) ataca os 3 caminhos:

### Para quem TEM o CSV em mãos

```bash
plugadvpl ingest-sx /caminho/pra/csvs/
```

Os 11 CSVs do SIGACFG entram numa base SQLite local em segundos. A partir daí, você tem:

- `plugadvpl impacto A1_COD` — cruza referências do campo em **3 camadas**: fontes que usam + SX3 (onde está definido) + SX7 (gatilhos que mexem nele) + SX1 (perguntas que validam). Profundidade `--depth 1..3`.
- `plugadvpl gatilho B1_TIPO` — cadeia de gatilhos origem → destino, navegável.
- `plugadvpl sx-status` — counts por tabela do dicionário.

### Para quem TEM acesso REST ao AppServer

```bash
plugadvpl ingest-protheus --endpoint http://protheus:8181/rest \
  --user admin --password $PROTHEUS_PASS
```

Em vez de pedir CSV, o plugin **dumpa o dicionário ao vivo** via REST. Atrás do `--endpoint` mora um fonte TLPP open-source (`COLETADB.tlpp`, MIT) que você instala no AppServer 1x — daí em diante, qualquer dev autorizado puxa o dicionário com 1 comando.

O bundle entregue cobre **21 tabelas** (não só 11):

- **SX padrão (11):** SX1 perguntas, SX2 tabelas, SX3 campos, SX5 tabelas genéricas, SX6 parâmetros MV_*, SX7 gatilhos, SX9 relacionamentos, SXA pastas, SXB consultas F3, SXG grupos de campo, SIX índices
- **SX adicional (3):** XXA, XAM, XAL
- **MPMENU (6):** menus completos com hierarquia (`mpmenu_menu` + `mpmenu_function` + `mpmenu_item` + `mpmenu_i18n` + `mpmenu_key_words` + `mpmenu_rw`)
- **SCHEDULES:** agendamentos do scheduler interno (XX0/XX1/XX2 com recorrência decodificada)
- **JOBS:** parse recursivo de `appserver*.ini`
- **RECORD_COUNTS:** inventário de rows físicas por tabela (via DBMS), pra ordenar tabelas por volume real

A versão é foto do momento do request. Quer comparar 2 momentos? Roda 2 vezes e diff.

### Para quem não tem nem CSV nem REST

Configure o `COLETADB.tlpp` no cliente. É um fonte de ~1900 linhas, MIT, distribuído em `docs/reference-impl/coletadb.tlpp`. Setup:

```ini
; appserver.ini
[HTTPV11]
ENABLE=1
PORT=8181

[HTTPURI]
URL=/rest
PrepareIn=<emp>,<fil>
Security=1
CORSEnable=1
```

Compila, restart do AppServer, e pronto.

## Killer feature: `plugadvpl impacto`

Você tem que mudar o tamanho do campo `A1_COD` de 6 pra 9 chars. Quanto trabalho vai dar? Antes do `plugadvpl`:

1. Procurar `A1_COD` em todos os fontes (regex)
2. Procurar gatilhos SX7 que mexem em `A1_COD`
3. Procurar consultas SXB que filtram por `A1_COD`
4. Procurar pergunte SX1 que valida tamanho
5. Tomar café, achar mais 3 lugares que esquecemos
6. Tomar mais café

Com plugadvpl:

```bash
plugadvpl impacto A1_COD --depth 3
```

Output JSON estruturado:

```json
{
  "campo": "A1_COD",
  "definicao_sx3": { "tabela": "SA1", "tipo": "C", "tamanho": 6, ... },
  "fontes_que_usam": [
    {"arquivo": "MATA440.PRW", "linha": 142, "modo": "read"},
    {"arquivo": "U_CADCLI.PRW", "linha": 89, "modo": "write"},
    ...
  ],
  "gatilhos_sx7_que_disparam": [...],
  "consultas_sxb": [...],
  "perguntas_sx1": [...],
  "regras_lint_cross_file": ["SX-003 OK", "SX-007 WARN"]
}
```

Em 1 segundo você sabe **TUDO** que precisa revisar. Não tem mais "esqueci de mudar no gatilho".

## Como começar (3 comandos, 5 minutos)

### Pré-requisito

Python 3.11+ e `uv` (gerenciador rápido):

```powershell
# Windows
winget install astral-sh.uv

# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Setup

```bash
uv tool install plugadvpl
cd seu/projeto/protheus
plugadvpl init                                    # cria .plugadvpl/index.db
plugadvpl ingest                                  # indexa os fontes (paralelo, ~60s pra 2k fontes)
plugadvpl ingest-sx /caminho/pra/csvs/sx          # OU ingest-protheus --endpoint ...
```

Pronto. Agora você tem o dicionário + os fontes cruzados num único banco SQLite local (`.plugadvpl/index.db`, fica no `.gitignore` automaticamente).

### Comandos úteis

```bash
plugadvpl impacto A1_COD --depth 3                # impacto cross-camada
plugadvpl gatilho B1_TIPO                         # cadeia de SX7
plugadvpl trace MV_LJTOPRT                        # grafo unificado
plugadvpl find "Pergunte"                         # busca FTS
plugadvpl lint --regra SX-007                     # lint cross-file
```

## Por que isso importa

Tempo médio gasto por consultoria Protheus pra entender "onde esse campo é usado": **30-90 minutos por campo**, somando grep nos fontes, abrir SX3/SX7/SX1 no SIGACFG, conferir, esquecer, abrir de novo.

Com `plugadvpl impacto`: **3 segundos.**

Em uma customização com 30 campos novos no SA1, isso é **15-45 horas de trabalho que voltam pro escopo**. E o cruzamento é **mais completo** (a ferramenta não esquece de nada que está indexado).

## Open-source, MIT, sem telemetria

100% local. Roda na sua máquina, indexa seus fontes locais, banco SQLite no seu disco. Não envia dado pra ninguém, não precisa de licença, não cobra. Comunidade ADVPL define o roadmap via issues no GitHub.

→ **PyPI:** [pypi.org/project/plugadvpl](https://pypi.org/project/plugadvpl)
→ **GitHub:** [github.com/JoniPraia/plugadvpl](https://github.com/JoniPraia/plugadvpl)
→ **COLETADB.tlpp reference impl:** `docs/reference-impl/coletadb.tlpp` (MIT)

#ADVPL #TLPP #Protheus #TOTVS #DicionarioSX #OpenSource #DevOps
