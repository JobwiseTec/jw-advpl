"""Integração com o FairCom DB.

Centraliza descoberta de caminhos do FairCom DB, carregamento do driver Python
nativo (pyctree, sobre libctsqlapi) e o registro de arquivos ISAM (.dtc) como
tabelas SQL via a utilidade ctsqlimp.

Decisões de arquitetura (validadas contra o FairCom DB v13):
- Conexão usa o driver NATIVO `pyctree` (DB-API 2.0) que acompanha o FairCom,
  carregado de ``$FAIRCOM_HOME/drivers/python.sql``. Isso elimina a dependência
  de unixODBC/pyodbc e de registro de DSN.
- A leitura de um arquivo ISAM externo exige registrá-lo no dicionário SQL com
  ``ctsqlimp``; ele "linka" o arquivo sem alterar os dados. O arquivo precisa
  conter os recursos IFIL e DODA (arquivos ISAM exportados de aplicativos c-tree
  normalmente já contêm).
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import platform
import re
import shutil
import struct
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Nome do servidor SQL padrão do FairCom DB (config: SERVER_NAME).
DEFAULT_SERVER_NAME = "FAIRCOMS"

# Nomes possíveis da utilidade ctinfo (extrai IFIL/DODA de um arquivo ISAM).
# A variante .standalone roda sem o servidor — preferimos ela.
_CTINFO_NAMES = {
    "Windows": ("ctinfo.standalone.exe", "ctinfo.exe"),
    "_default": ("ctinfo.standalone", "ctinfo"),
}

# Nomes possíveis do binário do servidor, por plataforma.
_SERVER_BINARIES = {
    "Windows": ("faircom.exe", "ctreesql.exe"),
    "_default": ("faircom", "ctreesql"),
}

# Nomes possíveis da utilidade ctsqlimp.
_CTSQLIMP_NAMES = {
    "Windows": ("ctsqlimp.exe",),
    "_default": ("ctsqlimp",),
}


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def native_lib_name() -> str:
    """Nome da biblioteca compartilhada do client SQL nativo, por plataforma."""
    if _is_macos():
        return "libctsqlapi.dylib"
    if _is_windows():
        return "ctsqlapi.dll"
    return "libctsqlapi.so"


def conn_params() -> dict[str, str]:
    """Parâmetros de conexão, com override por variável de ambiente.

    Defaults batem com a instalação padrão do FairCom DB Developer Edition.
    """
    return {
        "user": os.environ.get("DTCAT_USER", "ADMIN"),
        "password": os.environ.get("DTCAT_PASSWORD", "ADMIN"),
        "host": os.environ.get("DTCAT_HOST", "127.0.0.1"),
        "database": os.environ.get("DTCAT_DATABASE", "ctreeSQL"),
        "port": os.environ.get("DTCAT_PORT", "6597"),
    }


def server_name() -> str:
    return os.environ.get("DTCAT_SERVER", DEFAULT_SERVER_NAME)


def find_faircom_home() -> Path | None:
    """Localiza o diretório raiz da instalação do FairCom DB."""
    env = os.environ.get("FAIRCOM_HOME") or os.environ.get("CTREE_HOME")
    if env and Path(env).is_dir():
        return Path(env)
    candidates = [
        Path.home() / "faircom",
        Path("/opt/faircom"),
        Path("/usr/local/faircom"),
        Path("C:/FairCom"),
        Path("C:/Program Files/FairCom"),
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def lib_dir(home: Path) -> Path | None:
    """Diretório que contém a lib nativa do client SQL (libctsqlapi.*)."""
    name = native_lib_name()
    for sub in ("server", "bin", "lib"):
        d = home / sub
        if (d / name).is_file():
            return d
    return None


def native_lib_path(home: Path) -> Path | None:
    d = lib_dir(home)
    return d / native_lib_name() if d else None


def native_driver_dir(home: Path) -> Path | None:
    """Diretório do driver Python nativo (pyctree.py + pyctsqlapi.py)."""
    d = home / "drivers" / "python.sql"
    return d if (d / "pyctree.py").is_file() else None


def server_binary(home: Path) -> Path | None:
    names = _SERVER_BINARIES.get(platform.system(), _SERVER_BINARIES["_default"])
    for sub in ("server", "bin"):
        for n in names:
            p = home / sub / n
            if p.is_file():
                return p
    return None


def ctsqlimp_path(home: Path) -> Path | None:
    names = _CTSQLIMP_NAMES.get(platform.system(), _CTSQLIMP_NAMES["_default"])
    for sub in ("tools", "bin"):
        for n in names:
            p = home / sub / n
            if p.is_file():
                return p
    return None


def ctinfo_path(home: Path) -> Path | None:
    names = _CTINFO_NAMES.get(platform.system(), _CTINFO_NAMES["_default"])
    for sub in ("tools", "bin"):
        for n in names:
            p = home / sub / n
            if p.is_file():
                return p
    return None


# --- extração de layout (DODA) via ctinfo --------------------------------


@dataclass
class FieldDef:
    """Um campo do DODA: nome, offset no registro, tamanho em bytes, tipo c-tree."""

    name: str
    offset: int
    length: int
    ctype: str  # ex.: "FSTRING", "INT4U", "INT2", "CHAR"


@dataclass
class Layout:
    """Layout físico de um arquivo ISAM fixed-length, extraído do DODA."""

    record_length: int
    is_fixed: bool
    fields: list[FieldDef]

    @property
    def delete_field(self) -> FieldDef | None:
        """Campo de soft-delete (D_E_L_E_T_*), se presente."""
        for f in self.fields:
            if f.name.replace("_", "").upper().startswith("DELET"):
                return f
        return None

    @property
    def is_protheus(self) -> bool:
        """Assinatura Protheus: fixed-length com flag de delete no offset 0."""
        d = self.delete_field
        return self.is_fixed and d is not None and d.offset == 0


_DODA_LINE = re.compile(r"^(\w+)\s+(\d+)\s+CT_(\w+)\s+\(\d+\)\s+(\d+)\s*$", re.MULTILINE)
_RECLEN_RE = re.compile(r"Data record length\s*=\s*(\d+)")


def extract_layout(arquivo: Path, home: Path | None = None) -> Layout | None:
    """Extrai o layout (record length + DODA) de um arquivo ISAM.

    Tenta primeiro o parser DODA **nativo** (puro Python, dispensa o FairCom);
    é o caminho principal para arquivos com assinatura Protheus. Se ele não se
    aplicar, cai no ``ctinfo`` (que exige o FairCom instalado).
    """
    native = parse_doda_native(arquivo)
    if native is not None:
        return native
    return _extract_layout_ctinfo(arquivo, home)


def _extract_layout_ctinfo(arquivo: Path, home: Path | None = None) -> Layout | None:
    """Extrai o layout via ``ctinfo.standalone`` (fallback; exige FairCom).

    Devolve ``Layout`` ou ``None`` se não conseguir extrair (arquivo não é
    fixed-length, sem DODA, ou ctinfo indisponível).
    """
    home = home or find_faircom_home()
    if home is None:
        return None
    tool = ctinfo_path(home)
    if tool is None:
        return None
    res = subprocess.run(
        [str(tool), str(arquivo)],
        capture_output=True,
        text=True,
        env=subprocess_env(home),
        check=False,
    )
    out = res.stdout or ""
    if "fixed-length data file" not in out:
        return None  # variável ou ilegível → deixa pro fallback c-tree
    m = _RECLEN_RE.search(out)
    if not m:
        return None
    record_length = int(m.group(1))
    fields = [
        FieldDef(name=g[0], offset=int(g[1]), length=int(g[3]), ctype=g[2])
        for g in _DODA_LINE.findall(out)
    ]
    if not fields:
        return None
    return Layout(record_length=record_length, is_fixed=True, fields=fields)


# --- parser DODA nativo (puro Python, dispensa o FairCom na leitura) -----
#
# O recurso DODA fica dentro do próprio .dtc. Layout do bloco (validado contra
# arquivos reais do Protheus + ctinfo):
#   [uint32 N][uint32 N]                 cabeçalho: contagem de campos, duplicada
#   N x (uint16 tamanho, uint16 tipo)    array de campos, na ordem do registro
#   N x (uint8 prefixo + nome + 0x00)    pool de nomes (cp1252, null-terminated)
# Os offsets de cada campo NÃO são gravados: o c-tree os calcula alinhando cada
# campo conforme seu tipo. Por isso reconstruímos os offsets aqui.

# Código do tipo c-tree (ctport.h) = (índice_base << 3) + classe_de_tamanho.
# Mapeamos para os mesmos nomes que o ctinfo imprime (sem o prefixo "CT_").
_CTYPE_BY_CODE = {
    8: "BOOL", 16: "CHAR", 24: "CHARU",
    33: "INT2", 41: "INT2U", 51: "INT4", 59: "INT4U",
    67: "MONEY", 75: "DATE", 83: "TIME", 91: "SFLOAT", 103: "DFLOAT",
    119: "EFLOAT", 124: "TIMES", 128: "ARRAY", 143: "CURRENCY",
    144: "FSTRING", 146: "STRING", 152: "FPSTRING", 154: "PSTRING",
    160: "F2STRING", 162: "2STRING", 168: "F4STRING", 170: "4STRING",
    177: "FUNICODE", 185: "UNICODE", 193: "F2UNICODE", 201: "2UNICODE",
    227: "INT8", 235: "INT8U",
}  # fmt: skip

# Famílias (código >> 3) de texto/array → alinhadas a 1 byte. Para os tipos
# escalares (inteiros, datas, floats), os 3 bits baixos do código codificam
# (tamanho - 1), então o alinhamento natural é (code & 7) + 1.
_CHAR_BASES = frozenset({2, 3, 16, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27})

# Nomes possíveis do campo de soft-delete do Protheus (sempre no offset 0).
_PROTHEUS_DELETE = (b"D_E_L_E_T_E_D", b"D_E_L_E_T_")


def _ctype_name(code: int) -> str:
    return _CTYPE_BY_CODE.get(code, f"CT{code}")


def _field_align(code: int) -> int:
    """Alinhamento natural do campo no registro, derivado do código c-tree."""
    if (code >> 3) in _CHAR_BASES:
        return 1
    return (code & 7) + 1


def _delete_name_anchors(data: bytes) -> list[int]:
    """Offsets onde começa um nome de campo de soft-delete do Protheus.

    Exige o terminador null logo após o nome (assinatura do pool de nomes), o
    que evita casar com ocorrências do texto dentro dos dados.
    """
    anchors: list[int] = []
    for name in _PROTHEUS_DELETE:
        start = 0
        while True:
            i = data.find(name, start)
            if i < 0:
                break
            end = i + len(name)
            if end < len(data) and data[end] == 0:
                anchors.append(i)
            start = i + 1
    return anchors


def _is_ident(raw: bytes) -> bool:
    """Nome de campo do Protheus: letras, dígitos e ``_`` (ex.: D_E_L_E_T_E_D)."""
    if not raw:
        return False
    return all(
        c == 0x5F or 0x30 <= c <= 0x39 or 0x41 <= c <= 0x5A or 0x61 <= c <= 0x7A for c in raw
    )


def _parse_name_pool(data: bytes, pool: int) -> list[str]:
    """Lê o pool de nomes a partir de ``pool`` (1 byte de prefixo + nome + NUL).

    Tolerante a variações entre versões do APSDU: usa o terminador NUL como
    fronteira e para quando o conteúdo deixa de ser um nome de campo válido
    (pode passar um pouco do fim; a contagem real vem do cabeçalho do DODA).
    """
    names: list[str] = []
    p = pool
    while p < len(data) and len(names) < 8192:
        end = data.find(b"\x00", p + 1)
        if end < 0:
            break
        nm = data[p + 1 : end]
        if not _is_ident(nm):
            break
        names.append(nm.decode("cp1252", "replace"))
        p = end + 1
    return names


def _valid_entries(data: bytes, arr: int, n: int) -> list[tuple[int, int]] | None:
    """Lê e valida ``n`` entradas (uint16 tamanho, uint16 tipo) do array do DODA."""
    if arr < 0 or arr + n * 4 > len(data):
        return None
    ents = [struct.unpack_from("<HH", data, arr + i * 4) for i in range(n)]
    for ln, code in ents:
        base = code >> 3
        # ln == 0 é válido: campos memo/variáveis (ex.: 4STRING) ocupam 0 bytes
        # no registro fixo — o conteúdo fica fora dele.
        if base == 0 or base > 40 or ln > 0xFFFF:  # tipo c-tree plausível
            return None
    # o 1º campo é o de soft-delete: texto/char curto
    if ents[0][1] not in (16, 24, 144, 146, 152, 154):  # CHAR/CHARU/FSTRING/STRING/...
        return None
    return ents


def _locate_array(data: bytes, pool: int, max_n: int) -> tuple[int, list[tuple[int, int]]] | None:
    """Localiza o array de campos do DODA antes do pool de nomes.

    Robusto a variações de versão: primeiro procura o cabeçalho de **contagem
    duplicada** ``(N, N)`` (a contagem é autoritativa); se não houver, tenta o
    array logo antes do pool, tolerando um pequeno gap.
    """
    # 1) cabeçalho de contagem duplicada (N, N) — vale entre versões testadas
    lo = max(0, pool - max_n * 4 - 512)
    for c in range(pool - 8, lo - 1, -1):
        a, b = struct.unpack_from("<II", data, c)
        if a == b and 2 <= a <= max_n:
            ents = _valid_entries(data, c + 8, a)
            if ents is not None and c + 8 + a * 4 <= pool:
                return c + 8, ents
    # 2) fallback: array imediatamente antes do pool (com gap pequeno)
    for gap in range(33):
        arr = pool - gap - max_n * 4
        ents = _valid_entries(data, arr, max_n)
        if ents is not None:
            return arr, ents
    return None


def _parse_doda_from_anchor(data: bytes, anchor: int) -> Layout | None:
    """Reconstrói o Layout assumindo que o pool de nomes começa em ``anchor``.

    Lê os nomes, localiza o array de (tamanho, tipo) de forma robusta a variações
    de versão do APSDU e reconstrói os offsets pela regra de alinhamento do c-tree.
    """
    pool = anchor - 1  # byte de prefixo de tamanho do 1º nome
    if pool < 8:
        return None
    names = _parse_name_pool(data, pool)
    if len(names) < 2:
        return None
    located = _locate_array(data, pool, len(names))
    if located is None:
        return None
    _arr, entries = located
    n = len(entries)
    fields: list[FieldDef] = []
    cur = 0
    for (ln, code), nm in zip(entries, names[:n], strict=True):
        align = _field_align(code)
        if cur % align:
            cur += align - (cur % align)
        fields.append(FieldDef(name=nm, offset=cur, length=ln, ctype=_ctype_name(code)))
        cur += ln
    return Layout(record_length=cur, is_fixed=True, fields=fields)


def parse_doda_native(arquivo: Path) -> Layout | None:
    """Extrai o Layout lendo o DODA direto do .dtc, **sem o FairCom**.

    Caminho zero-FairCom: localiza o recurso DODA pela âncora do campo de
    soft-delete do Protheus, lê o array de (tamanho, tipo) e o pool de nomes, e
    calcula os offsets pela regra de alinhamento do c-tree. Só devolve um Layout
    com assinatura Protheus (fixed-length + delete D_E_L_E_T_* no offset 0);
    para os demais devolve ``None`` (cai no ctinfo / c-tree).
    """
    try:
        data = arquivo.read_bytes()
    except OSError:
        return None
    for anchor in _delete_name_anchors(data):
        layout = _parse_doda_from_anchor(data, anchor)
        if layout is not None and layout.is_protheus:
            return layout
    return None


def sql_dbs_dir(home: Path) -> Path:
    """Diretório de trabalho SQL do servidor (onde os arquivos ISAM são linkados)."""
    return home / "data" / "ctreeSQL.dbs"


def subprocess_env(home: Path) -> dict[str, str]:
    """Ambiente para executáveis do FairCom (ctsqlimp, ctstop) com a lib path certa."""
    env = dict(os.environ)
    extra = os.pathsep.join(str(home / d) for d in ("server", "tools"))
    if _is_macos():
        var = "DYLD_LIBRARY_PATH"
    elif _is_windows():
        var = "PATH"
    else:
        var = "LD_LIBRARY_PATH"
    env[var] = os.pathsep.join(filter(None, [extra, env.get(var, "")]))
    return env


# --- driver nativo -------------------------------------------------------


@lru_cache(maxsize=1)
def load_native_driver(home_str: str | None = None):
    """Importa e devolve o módulo `pyctree` que acompanha o FairCom DB.

    O `pyctsqlapi` faz ``ctypes.CDLL("libctsqlapi.so")`` pelo soname; para não
    depender de LD_LIBRARY_PATH, interceptamos o CDLL durante o import e
    injetamos o caminho absoluto da lib.
    """
    home = Path(home_str) if home_str else find_faircom_home()
    if home is None:
        raise RuntimeError(
            "FairCom DB não encontrado. Defina FAIRCOM_HOME ou veja docs/setup-linux.md"
        )
    libpath = native_lib_path(home)
    drvdir = native_driver_dir(home)
    if libpath is None:
        raise RuntimeError(f"{native_lib_name()} não localizado em {home}")
    if drvdir is None:
        raise RuntimeError(f"driver Python nativo não localizado em {home}/drivers/python.sql")

    import sys

    targets = {"libctsqlapi.so", "ctsqlapi", "libctsqlapi.dylib", "ctsqlapi.dll"}
    real_cdll = ctypes.CDLL

    def patched_cdll(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name in targets:
            name = str(libpath)
        return real_cdll(name, *args, **kwargs)

    ctypes.CDLL = patched_cdll  # type: ignore[assignment]
    sys.path.insert(0, str(drvdir))
    try:
        import pyctree  # type: ignore[import-not-found]
    finally:
        ctypes.CDLL = real_cdll  # type: ignore[assignment]
    return pyctree


def connect(home: Path | None = None):
    """Abre uma conexão DB-API com o servidor SQL local via driver nativo."""
    drv = load_native_driver(str(home) if home else None)
    return drv.connect(**conn_params())


# --- registro de arquivos ISAM via ctsqlimp ------------------------------

_LINKED_RE = re.compile(r"successfully linked", re.IGNORECASE)
_EXISTS_RE = re.compile(r"already exists", re.IGNORECASE)


def safe_table_name(arquivo: Path) -> str:
    """Deriva um nome de tabela SQL válido e determinístico a partir do arquivo.

    Usado como nome simbólico no ``ctsqlimp -n`` (no link e no ``-r``), garantindo
    um nome previsível para consulta e um cleanup que casa exatamente.
    """
    stem = arquivo.stem
    safe = "".join(ch if ch.isalnum() else "_" for ch in stem).strip("_")
    if not safe or safe[0].isdigit():
        safe = f"dtc_{safe}"
    return f"dtcat_{safe.lower()}"


def register_isam(arquivo: Path, home: Path | None = None) -> tuple[Path, str]:
    """Registra um arquivo ISAM (.dtc) como tabela SQL via ctsqlimp.

    Copia o arquivo (e o índice .idx irmão, se existir) para o diretório de
    trabalho SQL do servidor e roda ``ctsqlimp -n <nome>`` para linká-lo sob um
    nome simbólico determinístico. Retorna ``(caminho_no_dbs, nome_da_tabela)``.
    """
    home = home or find_faircom_home()
    if home is None:
        raise RuntimeError("FairCom DB não encontrado (FAIRCOM_HOME).")
    tool = ctsqlimp_path(home)
    if tool is None:
        raise RuntimeError(f"ctsqlimp não localizado em {home}/tools")

    dbs = sql_dbs_dir(home)
    dbs.mkdir(parents=True, exist_ok=True)
    target = dbs / arquivo.name
    if arquivo.resolve() != target.resolve():
        shutil.copy2(arquivo, target)
        idx = arquivo.with_suffix(arquivo.suffix + ".idx")
        if not idx.exists():
            idx = arquivo.with_suffix(".idx")
        if idx.exists():
            shutil.copy2(idx, dbs / idx.name)

    table = safe_table_name(arquivo)
    p = conn_params()
    # Relink defensivo: limpa um eventual registro obsoleto antes de linkar.
    subprocess.run(
        [
            str(tool),
            str(target),
            "-n",
            table,
            "-r",
            "-u",
            p["user"],
            "-a",
            p["password"],
            "-s",
            server_name(),
            "-i",
        ],
        capture_output=True,
        text=True,
        env=subprocess_env(home),
        check=False,
    )
    cmd = [
        str(tool),
        str(target),
        "-n",
        table,
        "-u",
        p["user"],
        "-a",
        p["password"],
        "-s",
        server_name(),
        "-b",  # concede acesso público de leitura à tabela linkada
        "-i",  # modo não interativo
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env=subprocess_env(home), check=False)
    out = (res.stdout or "") + (res.stderr or "")
    if not (_LINKED_RE.search(out) or _EXISTS_RE.search(out)):
        raise RuntimeError(f"ctsqlimp falhou ao registrar {arquivo.name}:\n{out.strip()}")
    return target, table


def unregister_isam(target: Path, table: str, home: Path | None = None) -> None:
    """Desvincula a tabela do dicionário SQL (mantém os dados) e remove a cópia."""
    home = home or find_faircom_home()
    if home is None:
        return
    tool = ctsqlimp_path(home)
    if tool is not None:
        p = conn_params()
        subprocess.run(
            [
                str(tool),
                str(target),
                "-n",
                table,
                "-r",
                "-u",
                p["user"],
                "-a",
                p["password"],
                "-s",
                server_name(),
                "-i",
            ],
            capture_output=True,
            text=True,
            env=subprocess_env(home),
            check=False,
        )
    # remove as cópias feitas no diretório de trabalho
    for f in (target, target.with_suffix(".idx"), Path(str(target) + ".idx")):
        with contextlib.suppress(OSError):
            f.unlink(missing_ok=True)
