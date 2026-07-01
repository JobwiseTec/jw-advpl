# Setup do leitor `.dtc` (`plugadvpl dtc`)

O subcomando `plugadvpl dtc` lê e exporta arquivos `.dtc` (c-tree ISAM, exports
do APSDU/Protheus). Tem dois caminhos de leitura — só um deles exige instalação
extra.

## O que precisa de quê

| Cenário | Comando | Requisito |
|---|---|---|
| Inspecionar `.dtc` Protheus (layout fixo) | `plugadvpl dtc info <arq>` | **nada** — parser DODA nativo, Python puro |
| Exportar pra CSV/JSON/XLSX | `plugadvpl dtc export` / `batch` | **nada** — pandas/openpyxl já são core |
| Ler `.dtc` de layout variável (fallback c-tree) | idem, via driver | **FairCom DB Developer Edition** |

Instalação (info e export funcionam direto, sem extra):

```bash
uv tool install plugadvpl
```

Para o caminho c-tree (só quando o parser nativo não se aplica), instale o
**FairCom DB Developer Edition** (gratuito) e configure `FAIRCOM_HOME`. Valide
com:

```bash
plugadvpl dtc doctor
```

## Guias por sistema operacional

- [Linux](dtc/setup-linux.md)
- [macOS](dtc/setup-macos.md) — atenção a ARM (M1+); ver nota no guia
- [Windows](dtc/setup-windows.md)

## Referência técnica

Formato `.dtc`, encoding cp1252, filtro de deletados e gotchas estão na skill:
[`skills/dtc/reference.md`](../skills/dtc/reference.md).

> O engine de leitura é vendorizado do projeto [dtcat](https://github.com/tbarbito/dtcat)
> (MIT) — ver `NOTICE` na raiz do repositório.
