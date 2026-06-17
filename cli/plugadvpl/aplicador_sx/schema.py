"""Schema das colunas SX + validação do spec do aplicador de SXs.

``Col`` descreve uma coluna física de um dicionário SX (nome, chave no spec
JSON, tipo, default seguro, obrigatoriedade, tamanho máximo). ``SX3_COLS`` é a
lista canônica dos 46 campos do SX3 na ordem física da tabela.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Col:
    nome: str  # nome da coluna SX (ex.: "X3_CAMPO")
    chave: str | None  # chave no spec JSON (ex.: "campo"); None = sempre default
    tipo: str  # 'C' | 'N' | 'L' | 'D'
    default: object = ""
    obrig: bool = False
    maxlen: int | None = None


SX3_COLS: list[Col] = [
    Col("X3_ARQUIVO", "alias", "C", "", obrig=True, maxlen=3),
    Col("X3_ORDEM", "ordem", "C", "01", maxlen=2),
    Col("X3_CAMPO", "campo", "C", "", obrig=True, maxlen=10),
    Col("X3_TIPO", "tipo", "C", "C", obrig=True, maxlen=1),
    Col("X3_TAMANHO", "tamanho", "N", 0),
    Col("X3_DECIMAL", "decimal", "N", 0),
    Col("X3_TITULO", "titulo", "C", "", maxlen=30),
    Col("X3_TITSPA", "titulo", "C", "", maxlen=30),
    Col("X3_TITENG", "titulo", "C", "", maxlen=30),
    Col("X3_DESCRIC", "descric", "C", "", maxlen=50),
    Col("X3_DESCSPA", "descric", "C", "", maxlen=50),
    Col("X3_DESCENG", "descric", "C", "", maxlen=50),
    Col("X3_PICTURE", "picture", "C", "", maxlen=20),
    Col("X3_VALID", "valid", "C", "", maxlen=120),
    Col("X3_USADO", "usado", "C", "", maxlen=256),
    Col("X3_RELACAO", "relacao", "C", "", maxlen=80),
    Col("X3_F3", "f3", "C", "", maxlen=10),
    Col("X3_NIVEL", "nivel", "N", 0),
    Col("X3_RESERV", None, "C", "xxxxxx x", maxlen=20),
    Col("X3_CHECK", "check", "C", "", maxlen=120),
    Col("X3_TRIGGER", "trigger", "C", "", maxlen=1),
    Col("X3_PROPRI", None, "C", "U", maxlen=1),
    Col("X3_BROWSE", "browse", "C", "N", maxlen=1),
    Col("X3_VISUAL", None, "C", "A", maxlen=1),
    Col("X3_CONTEXT", None, "C", "R", maxlen=1),
    Col("X3_OBRIGAT", "obrigat", "C", "", maxlen=16),
    Col("X3_VLDUSER", "vlduser", "C", "", maxlen=120),
    Col("X3_CBOX", "cbox", "C", "", maxlen=120),
    Col("X3_CBOXSPA", "cbox", "C", "", maxlen=120),
    Col("X3_CBOXENG", "cbox", "C", "", maxlen=120),
    Col("X3_PICTVAR", "pictvar", "C", "", maxlen=20),
    Col("X3_WHEN", "when", "C", "", maxlen=120),
    Col("X3_INIBRW", "inibrw", "C", "", maxlen=60),
    Col("X3_GRPSXG", "grpsxg", "C", "", maxlen=3),
    Col("X3_FOLDER", "folder", "C", "", maxlen=2),
    Col("X3_CONDSQL", "condsql", "C", "", maxlen=120),
    Col("X3_CHKSQL", "chksql", "C", "", maxlen=120),
    Col("X3_IDXSRV", "idxsrv", "C", "", maxlen=120),
    Col("X3_ORTOGRA", None, "C", "N", maxlen=1),
    Col("X3_TELA", "tela", "C", "", maxlen=10),
    Col("X3_POSLGT", None, "C", "", maxlen=16),
    Col("X3_IDXFLD", None, "C", "N", maxlen=1),
    Col("X3_AGRUP", "agrup", "C", "", maxlen=20),
    Col("X3_MODAL", None, "C", "", maxlen=1),
    Col("X3_PYME", None, "C", "", maxlen=1),
    # X3_INIT: inicializador padrão do campo (coluna física do SX3). Mantido como
    # default-only (chave=None) para totalizar as 46 colunas do dicionário.
    Col("X3_INIT", None, "C", "", maxlen=120),
]

SX2_COLS: list[Col] = [
    Col("X2_CHAVE", "alias", "C", "", obrig=True, maxlen=3),
    Col("X2_PATH", "path", "C", "", maxlen=99),
    Col("X2_ARQUIVO", "alias", "C", "", maxlen=8),  # loop aplica sufixo de empresa em runtime
    Col("X2_NOME", "nome", "C", "", obrig=True, maxlen=30),
    Col("X2_NOMESPA", "nome", "C", "", maxlen=30),
    Col("X2_NOMEENG", "nome", "C", "", maxlen=30),
    Col("X2_MODO", "modo", "C", "E", maxlen=1),
    Col("X2_TTS", None, "C", "", maxlen=1),
    Col("X2_ROTINA", "rotina", "C", "", maxlen=10),
    Col("X2_PYME", None, "C", "", maxlen=1),
    Col("X2_UNICO", "unico", "C", "", maxlen=99),
    Col("X2_DISPLAY", "display", "C", "", maxlen=99),
    Col("X2_SYSOBJ", None, "C", "", maxlen=1),
    Col("X2_USROBJ", None, "C", "", maxlen=1),
    Col("X2_POSLGT", None, "C", "", maxlen=16),
    Col("X2_CLOB", None, "C", "", maxlen=1),
    Col("X2_AUTREC", None, "C", "", maxlen=1),
    Col("X2_MODOEMP", None, "C", "E", maxlen=1),
    Col("X2_MODOUN", None, "C", "E", maxlen=1),
    Col("X2_MODULO", None, "N", 0),
]

# SIX (índices). Os "nomes" abaixo são os rótulos lógicos do aEstrut, que
# coincidem com os campos físicos reais do SIX (INDICE/ORDEM/CHAVE/...).
SIX_COLS: list[Col] = [
    Col("INDICE", "alias", "C", "", obrig=True, maxlen=3),
    Col("ORDEM", "ordem", "C", "1", obrig=True, maxlen=2),
    Col("CHAVE", "chave", "C", "", obrig=True, maxlen=99),
    Col("DESCRICAO", "descricao", "C", "", maxlen=50),
    Col("DESCSPA", "descricao", "C", "", maxlen=50),
    Col("DESCENG", "descricao", "C", "", maxlen=50),
    Col("PROPRI", None, "C", "U", maxlen=1),
    Col("F3", "f3", "C", "", maxlen=10),
    Col("NICKNAME", "nickname", "C", "", maxlen=10),
    Col("SHOWPESQ", "showpesq", "C", "N", maxlen=1),
]


SX6_COLS: list[Col] = [
    Col("X6_FIL", None, "C", "  ", maxlen=2),  # global (2 espaços) por default
    Col("X6_VAR", "var", "C", "", obrig=True, maxlen=20),
    Col("X6_TIPO", "tipo", "C", "C", maxlen=1),
    Col("X6_DESCRIC", "descric", "C", "", maxlen=40),
    Col("X6_DSCSPA", "descric", "C", "", maxlen=40),
    Col("X6_DSCENG", "descric", "C", "", maxlen=40),
    Col("X6_DESC1", "desc1", "C", "", maxlen=40),
    Col("X6_DSCSPA1", "desc1", "C", "", maxlen=40),
    Col("X6_DSCENG1", "desc1", "C", "", maxlen=40),
    Col("X6_DESC2", "desc2", "C", "", maxlen=40),
    Col("X6_DSCSPA2", "desc2", "C", "", maxlen=40),
    Col("X6_DSCENG2", "desc2", "C", "", maxlen=40),
    Col("X6_CONTEUD", "conteudo", "C", "", maxlen=200),
    Col("X6_CONTSPA", "conteudo", "C", "", maxlen=200),
    Col("X6_CONTENG", "conteudo", "C", "", maxlen=200),
    Col("X6_PROPRI", None, "C", "U", maxlen=1),
    Col("X6_VALID", "valid", "C", "", maxlen=120),
    Col("X6_INIT", "init", "C", "", maxlen=200),
    Col("X6_DEFPOR", None, "C", "", maxlen=40),
    Col("X6_DEFSPA", None, "C", "", maxlen=40),
    Col("X6_DEFENG", None, "C", "", maxlen=40),
    Col("X6_PYME", None, "C", "", maxlen=1),
]

SX7_COLS: list[Col] = [
    Col("X7_CAMPO", "campo", "C", "", obrig=True, maxlen=10),
    Col("X7_SEQUENC", "sequenc", "C", "001", maxlen=3),
    Col("X7_REGRA", "regra", "C", "", maxlen=250),
    Col("X7_CDOMIN", "cdomin", "C", "", maxlen=10),
    Col("X7_TIPO", "tipo", "C", "P", maxlen=1),
    Col("X7_SEEK", "seek", "C", "N", maxlen=1),
    Col("X7_ALIAS", "xalias", "C", "", maxlen=3),
    Col("X7_ORDEM", "xordem", "N", 0),
    Col("X7_CHAVE", "xchave", "C", "", maxlen=40),
    Col("X7_PROPRI", None, "C", "U", maxlen=1),
    Col("X7_CONDIC", "condic", "C", "", maxlen=250),
]

SX1_COLS: list[Col] = [
    Col("X1_GRUPO", "grupo", "C", "", obrig=True, maxlen=10),
    Col("X1_ORDEM", "ordem", "C", "", obrig=True, maxlen=2),
    Col("X1_PERGUNT", "pergunta", "C", "", obrig=True, maxlen=30),
    Col("X1_PERSPA", "pergunta", "C", "", maxlen=30),
    Col("X1_PERENG", "pergunta", "C", "", maxlen=30),
    Col(
        "X1_VARIAVL", "variavel", "C", "", maxlen=6
    ),  # MV_CHx legado (≤6); NÃO é o MV_PARxx (vem da ordem)
    Col("X1_TIPO", "tipo", "C", "C", maxlen=1),
    Col("X1_TAMANHO", "tamanho", "N", 0),
    Col("X1_DECIMAL", "decimal", "N", 0),
    Col("X1_PRESEL", "presel", "N", 0),
    Col("X1_GSC", "gsc", "C", "G", maxlen=1),  # 'G'=Get livre; '1'=radio (auto quando há opções)
    Col("X1_VALID", "valid", "C", "", maxlen=120),
    # bloco 01..05 (var/def/defspa/defeng/cnt). chaves expandidas de "opcoes" no emit.
    Col("X1_VAR01", "var01", "C", "", maxlen=10),
    Col("X1_DEF01", "def01", "C", "", maxlen=40),
    Col("X1_DEFSPA1", "def01", "C", "", maxlen=40),
    Col("X1_DEFENG1", "def01", "C", "", maxlen=40),
    Col("X1_CNT01", "cnt01", "C", "", maxlen=10),
    Col("X1_VAR02", "var02", "C", "", maxlen=10),
    Col("X1_DEF02", "def02", "C", "", maxlen=40),
    Col("X1_DEFSPA2", "def02", "C", "", maxlen=40),
    Col("X1_DEFENG2", "def02", "C", "", maxlen=40),
    Col("X1_CNT02", "cnt02", "C", "", maxlen=10),
    Col("X1_VAR03", "var03", "C", "", maxlen=10),
    Col("X1_DEF03", "def03", "C", "", maxlen=40),
    Col("X1_DEFSPA3", "def03", "C", "", maxlen=40),
    Col("X1_DEFENG3", "def03", "C", "", maxlen=40),
    Col("X1_CNT03", "cnt03", "C", "", maxlen=10),
    Col("X1_VAR04", "var04", "C", "", maxlen=10),
    Col("X1_DEF04", "def04", "C", "", maxlen=40),
    Col("X1_DEFSPA4", "def04", "C", "", maxlen=40),
    Col("X1_DEFENG4", "def04", "C", "", maxlen=40),
    Col("X1_CNT04", "cnt04", "C", "", maxlen=10),
    Col("X1_VAR05", "var05", "C", "", maxlen=10),
    Col("X1_DEF05", "def05", "C", "", maxlen=40),
    Col("X1_DEFSPA5", "def05", "C", "", maxlen=40),
    Col("X1_DEFENG5", "def05", "C", "", maxlen=40),
    Col("X1_CNT05", "cnt05", "C", "", maxlen=10),
    Col("X1_F3", "f3", "C", "", maxlen=10),
    Col("X1_PYME", None, "C", "", maxlen=1),
    Col("X1_GRPSXG", "grpsxg", "C", "", maxlen=3),
    Col("X1_HELP", "help", "C", "", maxlen=120),
    Col("X1_PICTURE", "picture", "C", "", maxlen=20),
    Col("X1_IDFIL", None, "C", "", maxlen=1),
]

SXA_COLS: list[Col] = [
    Col("XA_ALIAS", "alias", "C", "", obrig=True, maxlen=3),
    Col(
        "XA_ORDEM", "ordem", "C", "1", obrig=True, maxlen=2
    ),  # C(1) físico; '01' normalizado p/ '1' no emit
    Col("XA_DESCRIC", "descricao", "C", "", maxlen=30),
    Col("XA_DESCSPA", "descricao", "C", "", maxlen=30),
    Col("XA_DESCENG", "descricao", "C", "", maxlen=30),
    Col("XA_AGRUP", "agrup", "C", "", maxlen=10),
    Col("XA_TIPO", "tipo", "C", "", maxlen=1),
    Col("XA_PROPRI", None, "C", "U", maxlen=1),
]

SX5_COLS: list[Col] = [
    Col("X5_FILIAL", None, "C", "  ", maxlen=2),
    Col("X5_TABELA", "tabela", "C", "", obrig=True, maxlen=2),
    Col("X5_CHAVE", "chave", "C", "", obrig=True, maxlen=10),
    Col("X5_DESCRI", "descricao", "C", "", maxlen=40),
    Col("X5_DESCSPA", "descricao", "C", "", maxlen=40),
    Col("X5_DESCENG", "descricao", "C", "", maxlen=40),
]


# Mapa tipo -> colunas. Ordem de inserção segue a ordem canônica de emissão
# (_ORDEM_TIPOS em emit.py): sx2, sx3, six, sx6, sx7, sx1, sxa, sx5.
SX_COLS: dict[str, list[Col]] = {
    "sx2": SX2_COLS,
    "sx3": SX3_COLS,
    "six": SIX_COLS,
    "sx6": SX6_COLS,
    "sx7": SX7_COLS,
    "sx1": SX1_COLS,
    "sxa": SXA_COLS,
    "sx5": SX5_COLS,
}


# Colunas IDENTIFICADORAS: tamanho excedido é limite ESTRUTURAL (quebra/colide) ->
# erro. Nas demais (títulos, descrições, valores, máscaras), exceder só trunca no
# Protheus -> warning (não bloqueia a geração por um tamanho fora do padrão).
_LEN_HARD: frozenset[str] = frozenset(
    {
        "X3_CAMPO",
        "X3_ARQUIVO",
        "X2_CHAVE",
        "INDICE",
        "XA_ALIAS",
        "X5_TABELA",
        "X7_CAMPO",
        "X6_VAR",
        "X1_GRUPO",
    }
)


def validate_spec(spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Retorna (erros, warnings). Erros bloqueiam a emissão; warnings só avisam."""
    erros: list[str] = []
    warnings: list[str] = []
    if not str(spec.get("numero", "")).strip():
        erros.append("'numero' é obrigatório (id do update).")
    for tipo, cols in SX_COLS.items():
        for i, entry in enumerate(spec.get(tipo, []) or []):
            vistos: set[str] = (
                set()
            )  # 1 erro por chave do spec (colunas espelhadas compartilham chave)
            for c in cols:
                if c.chave is None or c.chave in vistos:
                    continue
                vistos.add(c.chave)
                val = entry.get(c.chave)
                if c.obrig and (val is None or val == ""):
                    erros.append(f"{tipo}[{i}]: '{c.chave}' obrigatório ({c.nome}).")
                if c.maxlen and isinstance(val, str) and len(val) > c.maxlen:
                    msg = f"{tipo}[{i}]: '{c.chave}' excede {c.maxlen} chars ({c.nome})."
                    (erros if c.nome in _LEN_HARD else warnings).append(msg)
    # SIX: a chave do índice deve começar por ALIAS_FILIAL (spec §6). Índices que
    # não filtram por filial vazam dados entre filiais.
    for i, e in enumerate(spec.get("six", []) or []):
        alias = str(e.get("alias", "") or "").strip()
        chave = str(e.get("chave", "") or "").strip()
        if alias and chave and not chave.upper().startswith(f"{alias.upper()}_FILIAL"):
            erros.append(f"six[{i}]: 'chave' deve começar por {alias}_FILIAL (índice por filial).")
    # SX7 (chunk 3): gatilho sobre campo fora do spec -> WARNING (pode pré-existir).
    # Inerte sem sx7.
    campos_spec = {e.get("campo") for e in (spec.get("sx3") or [])}
    for i, e in enumerate(spec.get("sx7", []) or []):
        if e.get("campo") and e["campo"] not in campos_spec:
            warnings.append(
                f"sx7[{i}]: campo '{e['campo']}' não está no spec (pode ser pré-existente)."
            )
    return erros, warnings
