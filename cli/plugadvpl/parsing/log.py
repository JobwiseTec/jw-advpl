"""Parser de log Protheus — tokenização em eventos + metadata + métricas.

Porta a engine validada do ``env_manager.parse_log`` (1055 linhas) pro idioma
do plugadvpl: dataclasses tipadas, sem state global, sem acesso ao YAML (regras
e tips vivem em ``log_rules``/``log_tips`` no DB). O match acontece em
``parsing/log_diagnose.py``.

Pipeline em 2 estágios:

    STAGE 1 (top-down, neste módulo): ``tokenize_events(content)`` quebra o log
    em eventos delimitados por 1 dos 4 formatos de header reconhecidos. Linhas
    subsequentes (até o próximo header) viram body do evento, preservando blocos
    multi-linha (THREAD ERROR + stacktrace, dumps SQL) intactos.

    STAGE 2 (bottom-up, em ``log_diagnose``): inverte a lista de eventos e aplica
    ``log_rules`` com short-circuit. Para quando atinge ``max_findings``, janela
    ``--since``, ou esgota eventos. Resultado: erros MAIS RECENTES primeiro.

Formatos de header reconhecidos:
    1) console.log moderno (ISO 8601 + thread_id): ``2026-03-09T10:35:35-03:00 1648|...``
    2) error.log PT-BR: ``THREAD ERROR ([31716], TIRETPIN, THIS)   06/03/2026   22:42:06``
    3) Timestamp PT-BR isolado: ``[06/03/2026 22:42:06] ...``
    4) Severity bracket: ``[INFO] ...``, ``[ERROR] ...``, etc.

Encoding: detecta BOM + faz fallback ``utf-8 → cp1252`` (logs Protheus geralmente
são CP1252 mas console.log moderno pode ser UTF-8).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(slots=True)
class LogEvent:
    """1 evento tokenizado: header + body acumulado até o próximo header."""
    line_number: int
    header_line: str
    body_lines: list[str] = field(default_factory=list)
    timestamp: datetime | None = None
    thread_id: str | None = None

    @property
    def body(self) -> str:
        return "\n".join(self.body_lines)

    @property
    def full_text(self) -> str:
        if self.body_lines:
            return self.header_line + "\n" + self.body
        return self.header_line


@dataclass(slots=True)
class LogHeaderMetadata:
    """Metadata extraída do header (error.log/profile.log têm ``[key: value]``)."""
    environment: str = ""
    appserver: str = ""
    build: str = ""
    rpo_version: str = ""
    thread: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class LogScanMetrics:
    """Métricas opcionais extraídas do console.log de startup."""
    memory_total_mb: str = ""
    memory_used_mb: str = ""
    memory_free_mb: str = ""
    memory_resident_mb: str = ""
    start_time_s: str = ""


@dataclass(slots=True)
class ParsedLog:
    filename: str
    tipo: str                                # console|error|profile|compile|outro
    encoding: str
    events: list[LogEvent]
    metadata: LogHeaderMetadata
    metrics: LogScanMetrics
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    # ``truncated_at_line``: se o log excedeu ``max_lines`` na tokenização,
    # guarda a linha onde a leitura parou; ``None`` se foi consumido inteiro.
    # Permite o ingest avisar o usuário sem deixar o cutoff silencioso (review #4).
    truncated_at_line: int | None = None


# =============================================================================
# Encoding
# =============================================================================


_UTF8_BOM = b"\xef\xbb\xbf"


def detect_log_encoding(raw: bytes) -> str:
    if raw.startswith(_UTF8_BOM):
        return "utf-8-bom"
    try:
        raw.decode("ascii")
        return "ascii"
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


def decode_log_bytes(raw: bytes) -> str:
    if raw.startswith(_UTF8_BOM):
        return raw[len(_UTF8_BOM):].decode("utf-8", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


# =============================================================================
# Regex de headers (4 formatos) + ruído
# =============================================================================


# 1) console.log moderno: ISO 8601 + thread_id (ex: "2026-03-09T10:35:35.103-03:00 1648|...")
RE_HEADER_ISO_THREAD = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})?)\s+(\d+)\|"
)

# 2) error.log THREAD ERROR PT-BR
RE_HEADER_THREAD_ERROR = re.compile(
    r"^THREAD ERROR\s*\(\[(\d+)\],\s*\w+,\s*\w+\)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})"
)

# 3) Timestamp PT-BR isolado: "[06/03/2026 22:42:06] ..."
RE_HEADER_PTBR_TS = re.compile(
    r"^\[(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})\]"
)

# 4) Severity bracket: "[INFO]", "[ERROR]", "[WARN]", etc.
RE_HEADER_BRACKET_SEV = re.compile(
    r"^\[(INFO|WARN(?:ING)?|ERROR|FATAL|DEBUG|TRACE)\b"
)

# Padrões de ruído operacional (linhas que NÃO geram finding mesmo casando regra)
RE_NOISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"deleting thread Pool"),
    re.compile(r"deleting server,"),
    re.compile(r"Deleting jobs from Threadpool"),
    re.compile(r"Function '\w+' has more than 10 characters"),
    re.compile(r"POWERSCHEMES.*Thread"),
)

# Captura de timestamp + thread (usados em body matching depois)
RE_TIMESTAMP_ANY = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})?)"
)
RE_THREAD_ID = re.compile(r"\[Thread\s+(\d+)\]")

# Metadata header [key: value] (error.log/profile.log)
RE_HEADER_KV = re.compile(
    r"^\[\s*([a-zA-Z_][a-zA-Z0-9_\s]*?)\s*[:=]\s*([^\]]*?)\s*\]\s*$",
    re.MULTILINE,
)
METADATA_KEYS_OF_INTEREST = frozenset({
    "build", "platform", "appversion", "environment", "thread", "dbthread",
    "appserver", "rpo_version", "user", "rpoversion", "username",
    "filial", "empresa", "callstack",
})

# Métricas
RE_MEMORY_OS = re.compile(
    r"Physical memory\s*\.\s*([\d.]+)\s*MB\.\s*Used\s*([\d.]+)\s*MB\.\s*Free\s*([\d.]+)\s*MB"
)
RE_MEMORY_APP = re.compile(r"Service Resident Memory\s*\.\.\.\s*([\d.]+)\s*MB")
RE_START_TIME = re.compile(r"Application Server Start Time:\s*([\d.]+)\s*s")


# =============================================================================
# Helpers
# =============================================================================


def is_noise(line: str) -> bool:
    """True se a linha é ruído operacional (ignorar mesmo casando regra)."""
    return any(p.search(line) for p in RE_NOISE_PATTERNS)


def detect_log_type(filename: str) -> str:
    """Classifica o log pelo nome do arquivo. Default 'outro'."""
    n = filename.lower()
    if "console" in n:
        return "console"
    if "error" in n:
        return "error"
    if "profile" in n:
        return "profile"
    if "compila" in n or "compile" in n or "build" in n:
        return "compile"
    return "outro"


def is_protheus_log_filename(name: str) -> bool:
    """Heurística pra discovery: nome bate com algum padrão de log Protheus."""
    n = name.lower()
    if not (n.endswith(".log") or n.endswith(".out")):
        return False
    tokens = ("console", "error", "profile", "compila", "compile", "appserver", "tss")
    return any(t in n for t in tokens)


# =============================================================================
# Stage 1 — Tokenização
# =============================================================================


def _try_parse_event_header(line: str) -> dict[str, Any] | None:
    """Tenta casar 1 dos 4 formatos. Retorna {timestamp, thread_id} ou None."""
    m = RE_HEADER_ISO_THREAD.match(line)
    if m:
        try:
            ts = datetime.fromisoformat(m.group(1))
        except (ValueError, TypeError):
            ts = None
        return {"timestamp": ts, "thread_id": m.group(2)}

    m = RE_HEADER_THREAD_ERROR.match(line)
    if m:
        try:
            ts = datetime.strptime(f"{m.group(2)} {m.group(3)}", "%d/%m/%Y %H:%M:%S")
        except (ValueError, TypeError):
            ts = None
        return {"timestamp": ts, "thread_id": m.group(1)}

    m = RE_HEADER_PTBR_TS.match(line)
    if m:
        try:
            ts = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d/%m/%Y %H:%M:%S")
        except (ValueError, TypeError):
            ts = None
        return {"timestamp": ts, "thread_id": None}

    m = RE_HEADER_BRACKET_SEV.match(line)
    if m:
        return {"timestamp": None, "thread_id": None}

    return None


def tokenize_events(content: str, max_lines: int = 1_000_000) -> list[LogEvent]:
    """Quebra o log em eventos delimitados por header reconhecido.

    Linhas órfãs antes do primeiro header são descartadas. Linhas órfãs no fim
    viram body do último evento conhecido. Cutoff em ``max_lines`` é silencioso
    aqui — pra detectar truncamento, use ``tokenize_events_with_meta`` ou
    ``parse_log_file`` (que captura ``truncated_at_line`` em ``ParsedLog``).
    """
    events, _truncated = tokenize_events_with_meta(content, max_lines=max_lines)
    return events


def tokenize_events_with_meta(
    content: str, max_lines: int = 1_000_000,
) -> tuple[list[LogEvent], int | None]:
    """Igual a ``tokenize_events`` mas retorna ``(events, truncated_at_line)``.

    ``truncated_at_line`` é ``None`` se o log foi consumido inteiro, ou o
    número da primeira linha NÃO processada se atingiu ``max_lines``.
    """
    events: list[LogEvent] = []
    current: LogEvent | None = None
    truncated_at: int | None = None

    for line_idx, raw in enumerate(content.splitlines(), 1):
        if line_idx > max_lines:
            truncated_at = line_idx
            break
        line = raw.rstrip("\r\n")

        if not line.strip():
            if current is not None:
                current.body_lines.append(line)
            continue

        parsed_header = _try_parse_event_header(line)
        if parsed_header is not None:
            if current is not None:
                events.append(current)
            current = LogEvent(
                line_number=line_idx,
                header_line=line,
                timestamp=parsed_header["timestamp"],
                thread_id=parsed_header["thread_id"],
            )
        elif current is not None:
            current.body_lines.append(line)

    if current is not None:
        events.append(current)
    return events, truncated_at

    return events


# =============================================================================
# Metadata extraction + scan metrics
# =============================================================================


def extract_header_metadata(content: str, scan_lines: int = 200) -> LogHeaderMetadata:
    """Extrai metadata ``[key: value]`` do início de error.log / profile.log."""
    head = "\n".join(content.splitlines()[:scan_lines])
    md = LogHeaderMetadata()

    for m in RE_HEADER_KV.finditer(head):
        key_raw = m.group(1).strip().lower().replace(" ", "_")
        value = m.group(2).strip()
        if not value or value.upper() in ("N/A", "ND"):
            continue
        if key_raw == "environment":
            md.environment = value
        elif key_raw == "appserver":
            md.appserver = value
        elif key_raw == "build":
            md.build = value
        elif key_raw == "rpo_version" or key_raw == "rpoversion":
            md.rpo_version = value
        elif key_raw == "thread":
            md.thread = value
        elif key_raw in METADATA_KEYS_OF_INTEREST:
            md.extra[key_raw] = value
        else:
            md.extra[key_raw] = value

    return md


def scan_metrics(content: str, scan_lines: int = 500) -> LogScanMetrics:
    """Vasculha as primeiras N linhas pra memória, start time."""
    head = "\n".join(content.splitlines()[:scan_lines])
    metrics = LogScanMetrics()

    m = RE_MEMORY_OS.search(head)
    if m:
        metrics.memory_total_mb = m.group(1)
        metrics.memory_used_mb = m.group(2)
        metrics.memory_free_mb = m.group(3)

    m = RE_MEMORY_APP.search(head)
    if m:
        metrics.memory_resident_mb = m.group(1)

    m = RE_START_TIME.search(head)
    if m:
        metrics.start_time_s = m.group(1)

    return metrics


# =============================================================================
# Timestamps (helpers pra --since)
# =============================================================================


def find_latest_timestamp(events: list[LogEvent]) -> datetime | None:
    """Maior timestamp entre os eventos. Normaliza mistura naive/aware."""
    timestamps = [ev.timestamp for ev in events if ev.timestamp is not None]
    if not timestamps:
        return None
    has_aware = any(t.tzinfo is not None for t in timestamps)
    has_naive = any(t.tzinfo is None for t in timestamps)
    if has_aware and has_naive:
        timestamps = [t.replace(tzinfo=None) for t in timestamps]
    return max(timestamps)


def find_earliest_timestamp(events: list[LogEvent]) -> datetime | None:
    timestamps = [ev.timestamp for ev in events if ev.timestamp is not None]
    if not timestamps:
        return None
    has_aware = any(t.tzinfo is not None for t in timestamps)
    has_naive = any(t.tzinfo is None for t in timestamps)
    if has_aware and has_naive:
        timestamps = [t.replace(tzinfo=None) for t in timestamps]
    return min(timestamps)


# =============================================================================
# Parser principal
# =============================================================================


def parse_log_file(content: str | bytes, filename: str = "") -> ParsedLog:
    """Parseia 1 log Protheus: tokeniza eventos + metadata + métricas.

    Aceita ``str`` ou ``bytes``. Decoda com fallback utf-8 → cp1252. Tipo do log
    é classificado pelo nome do arquivo (``console.log`` → ``console``, etc.).
    """
    if isinstance(content, bytes):
        encoding = detect_log_encoding(content)
        text = decode_log_bytes(content)
    else:
        encoding = "str"
        text = content

    events, truncated_at = tokenize_events_with_meta(text)
    metadata = extract_header_metadata(text)
    metrics = scan_metrics(text)

    first_ts = find_earliest_timestamp(events)
    last_ts = find_latest_timestamp(events)

    return ParsedLog(
        filename=filename,
        tipo=detect_log_type(filename),
        encoding=encoding,
        events=events,
        metadata=metadata,
        metrics=metrics,
        truncated_at_line=truncated_at,
        first_ts=first_ts,
        last_ts=last_ts,
    )


__all__ = [
    "LogEvent",
    "LogHeaderMetadata",
    "LogScanMetrics",
    "ParsedLog",
    "decode_log_bytes",
    "detect_log_encoding",
    "detect_log_type",
    "extract_header_metadata",
    "find_earliest_timestamp",
    "find_latest_timestamp",
    "is_noise",
    "is_protheus_log_filename",
    "parse_log_file",
    "scan_metrics",
    "tokenize_events",
    "tokenize_events_with_meta",
]
