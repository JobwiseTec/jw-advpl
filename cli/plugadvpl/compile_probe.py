"""Descobre dados de AppServer sem precisar de TDS-VSCode (v0.8.11).

Caso de uso: usuário tem instalação Protheus local mas nunca usou TDS-VSCode
(que normalmente seria a fonte de ``buildVersion``). ``--probe-appserver``
parseia ``protheus.log`` para extrair a build, evitando que o usuário precise
ir manualmente caçar essa informação.

Funções puras: recebem Path, devolvem dataclass. Sem efeito colateral.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProbeResult:
    """Resultado do probe de AppServer."""

    log_path: Path
    build: str  # ex.: "7.00.240223P" — vazio se não encontrou
    build_date: str  # ex.: "Oct 3 2025" — vazio se não encontrou
    lines_scanned: int


# Linha típica no protheus.log:
#   * TOTVS - Build 7.00.240223P - Oct 3 2025
# Variações observadas: prefixo pode ter timestamp/PID, "TOTVS" pode aparecer
# em maiúscula/mista. Regex tolera espaços extras.
_BUILD_LINE_RE = re.compile(
    r"TOTVS\s*-\s*Build\s+(?P<build>[\w.]+)\s*-\s*(?P<date>.+?)\s*$",
    re.IGNORECASE,
)

# Locais comuns onde protheus.log fica quando user aponta para a raíz do Protheus.
_LOG_SUBPATHS: tuple[str, ...] = (
    "log/protheus.log",
    "bin/Appserver/log/protheus.log",
    "bin/Appserver/protheus.log",
    "Appserver/log/protheus.log",
    "protheus.log",
)


def _resolve_log_path(target: Path) -> Path | None:
    """Resolve caminho do protheus.log a partir de Path ambíguo.

    Aceita:
    - Path direto pro .log (foo/protheus.log)
    - Raiz da instalação Protheus (procura em subpaths comuns)
    """
    if target.is_file():
        return target
    if not target.is_dir():
        return None
    for sub in _LOG_SUBPATHS:
        cand = target / sub
        if cand.is_file():
            return cand
    return None


def probe_appserver_log(target: Path, max_lines: int = 5000) -> ProbeResult | None:
    """Parseia protheus.log à procura da linha "TOTVS - Build X - Date".

    A linha aparece no boot do AppServer — limitamos leitura a ``max_lines``
    primeiras linhas pra evitar varrer log de produção inteiro (pode ter GB).

    Returns:
        ProbeResult com build/build_date extraídos. None se log não encontrado.
        Se log existe mas não tem a linha, retorna ProbeResult com build="".
    """
    log_path = _resolve_log_path(target)
    if log_path is None:
        return None

    build = ""
    date = ""
    count = 0
    try:
        # CP1252 — protheus.log historicamente vem assim no Windows.
        # errors=replace pra não travar em bytes corrompidos de log antigo.
        with log_path.open("r", encoding="cp1252", errors="replace") as fh:
            for line in fh:
                count += 1
                if count > max_lines:
                    break
                m = _BUILD_LINE_RE.search(line)
                if m:
                    build = m.group("build").strip()
                    date = m.group("date").strip()
                    break
    except OSError:
        return ProbeResult(log_path=log_path, build="", build_date="", lines_scanned=count)

    return ProbeResult(log_path=log_path, build=build, build_date=date, lines_scanned=count)
