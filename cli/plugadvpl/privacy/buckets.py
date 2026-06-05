"""Bucketização de valores financeiros: número -> faixa nomeada (Fase 2.1).

Protege o número sensível (limite, saldo, valor) mostrando a **ordem de grandeza**
em vez do valor exato — preservando o sinal diagnóstico sem vazar o R$ real.
*Single-value*: não precisa de contexto de comparação (a razão "105%" fica para o
futuro comando ``diagnose``).

Classificação de "campo financeiro" em duas vias, do mais preciso ao fallback:

1. **SX3-backed (verdade do dicionário):** um conjunto de nomes de campo onde
   ``X3_TIPO='N'`` com decimais — injetado via ``PrivacyConfig.financial_fields``
   (gerado de ``sx3.csv`` por :func:`financial_fields_from_sx3`). Bate ~100%.
2. **Heurística de nome (fallback sem SX3):** prefixo ``VL/VAL/SAL/PRC`` na parte
   do campo + raízes de tributo/valor. Recall ~65% medido em SX3 real — por isso
   é só fallback; com SX3 disponível, prefira a via 1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

# Mínimo de dígitos na parte inteira da PICTURE para classificar como "volume"
# (peso/quantidade/estoque) — distingue de alíquota/percentual, que é pequena.
_VOLUME_MIN_DIGITS = 4

# Prefixos da PARTE do campo (após o último '_') que indicam valor monetário.
# VL/VAL=valor, SAL=saldo, PRC=preço, PRV=preço de venda/produto, PRU=preço unit.
_MONETARY_PREFIXES = ("VL", "VAL", "SAL", "PRC", "PRV", "PRU")

# Raízes de valor/tributo/preço comuns no dicionário Protheus (inclui pedido/produto:
# preço unitário, custo, valor atual de estoque, mercadoria).
_MONETARY_TOKENS = (
    "SALDO",
    "SALDU",
    "LIMITE",
    "_LC",
    "CUST",
    "UNIT",
    "UPRC",
    "VATU",
    "MERC",
    "TOTAL",
    "COMIS",
    "FRETE",
    "DESCON",
    "DESCNT",
    "JUR",
    "IRRF",
    "INSS",
    "FECP",
    "ICMS",
    "COFINS",
    "TRIBUT",
    "MULTA",
    "SEGURO",
    "RENDA",
    "SALARIO",
    "MONTAN",
    "DEBITO",
    "CREDITO",
    "ADIANT",
    "ANTECIP",
    "LIQUID",
    "BRUTO",
    "PRECO",
    "DESP",
    "BASE",
)

# Faixas nomeadas (limite_superior_exclusivo, rótulo).
_RANGES = (
    (1_000, "<1k"),
    (10_000, "1k-10k"),
    (100_000, "10k-100k"),
    (1_000_000, "100k-1M"),
    (10_000_000, "1M-10M"),
    (100_000_000, "10M-100M"),
)


def is_financial_field(column: str, known: frozenset[str] = frozenset()) -> bool:
    """True se a coluna/campo indica valor financeiro.

    ``known`` (SX3-backed) tem prioridade e é exato; sem ele, cai na heurística
    de nome (prefixo VL/VAL/SAL/PRC + raízes de tributo).
    """
    upper = column.upper()
    if upper in known:
        return True
    part = upper.rsplit("_", 1)[-1] if "_" in upper else upper
    if part.startswith(_MONETARY_PREFIXES):
        return True
    return any(tok in upper for tok in _MONETARY_TOKENS)


def picture_class(picture: str) -> str:
    """Classifica um campo numérico pela PICTURE em ``money`` | ``volume`` | ``rate``:

    - ``money``: tem agrupamento de milhar (vírgula), ``@E 9,999,999.99`` -> valor R$;
    - ``volume``: número grande sem vírgula, ``@E 999999.999`` -> peso/quantidade/estoque;
    - ``rate``: número pequeno, ``@E 99.99`` -> alíquota/percentual (geralmente público).
    """
    if "," in picture:
        return "money"
    integer_part = picture.split(".", 1)[0]
    if integer_part.count("9") >= _VOLUME_MIN_DIGITS:
        return "volume"
    return "rate"


def financial_fields_from_sx3(
    rows: Iterable[dict[str, object]],
    *,
    campo_key: str = "X3_CAMPO",
    tipo_key: str = "X3_TIPO",
    dec_key: str = "X3_DECIMAL",
    pic_key: str = "X3_PICTURE",
    categories: Collection[str] | None = None,
) -> frozenset[str]:
    """Extrai do SX3 os campos de valor (``X3_TIPO='N'`` com decimais) — a verdade
    do dicionário. Cobre **pedido, produto, custo, estoque, peso, quantidade**.

    ``categories`` filtra por :func:`picture_class` (``money``/``volume``/``rate``):

    - ``None`` (default): **todos** os N+decimais (mais seguro / abrangente).
    - ``("money",)``: só dinheiro (R$) — pega nomes idiossincráticos (ZDSC/ABAT/CM).
    - ``("money", "volume")``: dinheiro **e** peso/quantidade/estoque (volume de
      negócio sensível), **excluindo** alíquota/percentual público.
    """
    allow = frozenset(c.lower() for c in categories) if categories is not None else None
    out: set[str] = set()
    for row in rows:
        if str(row.get(tipo_key, "")).strip().upper() != "N":
            continue
        try:
            dec = int(str(row.get(dec_key, "0")).strip() or "0")
        except ValueError:
            dec = 0
        if dec <= 0:
            continue
        campo = str(row.get(campo_key, "")).strip().upper()
        if not campo:
            continue
        if allow is not None and picture_class(str(row.get(pic_key, ""))) not in allow:
            continue
        out.add(campo)
    return frozenset(out)


def bucket(value: float) -> str:
    """Número -> faixa nomeada (ex.: ``48000`` -> ``"~10k-100k"``)."""
    magnitude = abs(value)
    if magnitude == 0:
        return "~0"
    sign = "-" if value < 0 else ""
    for upper, label in _RANGES:
        if magnitude < upper:
            return f"~{sign}{label}"
    return f"~{sign}>=100M"


def _to_float(text: str) -> float:
    """Converte string numérica (pt-BR ``1.234,56`` ou ``1234.56``) em float."""
    cleaned = text.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")  # pt-BR: ponto=milhar
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")  # vírgula decimal isolada
    return float(cleaned)


def try_bucket(value: object) -> str | None:
    """Se ``value`` for numérico (int/float ou string numérica), devolve a faixa."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return bucket(float(value))
    if isinstance(value, str) and value.strip():
        try:
            return bucket(_to_float(value))
        except ValueError:
            return None
    return None
