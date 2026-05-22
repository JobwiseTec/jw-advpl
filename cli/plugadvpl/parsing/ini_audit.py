"""Audit engine — cruza ini_keys × ini_rules → grava ini_audit_findings.

Estratégia idêntica ao ``env_manager.parse_ini.compare_against_best_practices``:
pra cada regra carregada do catálogo (``ini_rules``), procura a chave na seção
alvo e avalia conformidade usando o ``detection_kind``.

Severidade:
    critical | warning | info — mantida da regra original.

Status final do finding:
    active       → finding em aberto
    ok_with_note → valor não-conforme MAS cliente documentou justificativa em
                    ``comment_above`` (padrão: contém uma das palavras de
                    INTENT_PATTERNS abaixo).
    suppressed   → reservado (futuro: filtro de usuário via runtime config)

Filtro de roles:
    Regras com ``applies_to_role = ''`` aplicam a TODOS os roles do tipo.
    Regras com lista (``'broker_http|broker_soap'``) só aplicam aos roles
    listados. Match exato (case-sensitive contra ``ini_files.role``).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Sequence


# Padrão de intenção em comentários — quando o cliente já documentou que o
# valor diverge do recomendado, o finding vira ``ok_with_note`` em vez de
# ``active``. Lista importada do env_manager.parse_ini._INTENTIONAL_PATTERN.
_INTENT_RE = re.compile(
    r"\b(intencional|nao\s+aplica|justificativa|nosso\s+padrao|cliente\s+exige|"
    r"acordado|aprovado|excecao|nao\s+remover|por\s+design|opcao\s+do\s+cliente)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class _Rule:
    regra_id: str
    section_glob: str
    key_name: str
    expected: str
    severidade: str
    detection_kind: str
    descricao: str
    fix_guidance: str
    applies_to_tipo: str
    applies_to_role: str
    status: str


@dataclass(slots=True)
class AuditResult:
    """Sumário de uma chamada de audit."""
    files_audited: int = 0
    findings_total: int = 0
    by_severity: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.by_severity is None:
            self.by_severity = {"critical": 0, "warning": 0, "info": 0}


# =============================================================================
# Carregamento de regras
# =============================================================================


def _load_rules_for_target(
    conn: sqlite3.Connection, tipo: str, role: str,
) -> list[_Rule]:
    """Carrega regras aplicáveis a um INI específico (filtra por tipo + role).

    Match:
      - ``applies_to_tipo = ''``                  → aplica a todos os tipos
      - ``applies_to_tipo == tipo``               → aplica
      - DENTRO do tipo, ``applies_to_role = ''``  → aplica a todos os roles
      - DENTRO do tipo, ``applies_to_role`` contém ``role`` (sep ``|``) → aplica
    """
    cur = conn.execute(
        """
        SELECT regra_id, section_glob, key_name, expected, severidade,
               detection_kind, descricao, fix_guidance,
               applies_to_tipo, applies_to_role, status
        FROM ini_rules
        WHERE status = 'active'
              AND (applies_to_tipo = '' OR applies_to_tipo = ?)
        """,
        (tipo,),
    )
    rules: list[_Rule] = []
    for row in cur.fetchall():
        r = _Rule(*row)
        atr = r.applies_to_role or ""
        if not atr:
            rules.append(r)
            continue
        roles_list = {x.strip() for x in atr.split("|") if x.strip()}
        if role in roles_list:
            rules.append(r)
    return rules


# =============================================================================
# Resolução de seção-alvo
# =============================================================================


_ENV_KEY_INDICATORS = frozenset({
    "rootpath", "sourcepath", "rpodb", "rpoversion", "startpath",
})


def _resolve_target_sections(
    conn: sqlite3.Connection, file_id: int, section_glob: str,
) -> list[tuple[int, str]]:
    """Devolve ``[(section_id, name_raw), ...]`` que casam o ``section_glob``.

    Suporta hoje:
      - Nome literal (exact, case-insensitive)         — match único
      - ``"<DRIVER>/<env>"`` (ex: ``MSSQL/protheus``)  — wildcard via prefix
      - ``"environment"``                              — qualquer seção
        que tenha chaves indicadoras de environment Protheus
      - ``"*"`` ou ``""``                              — todas as seções não comentadas

    Seções comentadas são sempre ignoradas (chaves são inativas).
    """
    glob_low = section_glob.strip().lower()

    if not glob_low or glob_low == "*":
        cur = conn.execute(
            "SELECT id, name_raw FROM ini_sections WHERE file_id = ? AND commented = 0",
            (file_id,),
        )
        return [(int(r[0]), r[1]) for r in cur.fetchall()]

    if glob_low == "environment":
        # Acha seções com pelo menos 1 chave indicadora
        cur = conn.execute(
            """
            SELECT DISTINCT s.id, s.name_raw
            FROM ini_sections s
            JOIN ini_keys k ON k.section_id = s.id
            WHERE s.file_id = ? AND s.commented = 0
                  AND k.key_norm IN ('rootpath','sourcepath','rpodb','rpoversion','startpath')
            """,
            (file_id,),
        )
        return [(int(r[0]), r[1]) for r in cur.fetchall()]

    # Wildcard com '/': pega o lado esquerdo como prefix
    if "/" in glob_low and ("<" in glob_low or "*" in glob_low):
        prefix = glob_low.split("/")[0].strip("<>*")
        cur = conn.execute(
            "SELECT id, name_raw FROM ini_sections WHERE file_id = ? AND commented = 0 AND name_norm LIKE ?",
            (file_id, f"{prefix}/%"),
        )
        return [(int(r[0]), r[1]) for r in cur.fetchall()]

    # Nome literal (exact, case-insensitive)
    cur = conn.execute(
        "SELECT id, name_raw FROM ini_sections WHERE file_id = ? AND commented = 0 AND name_norm = ?",
        (file_id, glob_low),
    )
    return [(int(r[0]), r[1]) for r in cur.fetchall()]


# =============================================================================
# Avaliação de valor (detection_kind)
# =============================================================================


def _evaluate_value(rule: _Rule, current_value: str | None) -> bool:
    """True se ``current_value`` está CONFORME com ``rule``."""
    expected = rule.expected.strip()
    current = (current_value or "").strip()

    if rule.detection_kind == "key_present":
        return current_value is not None and current != ""

    if rule.detection_kind == "key_missing":
        return current_value is None

    if current_value is None:
        # Chave ausente: a maioria das detection_kinds considera não-conforme,
        # exceto se a regra for opcional (sem expected definido).
        return not expected

    if rule.detection_kind == "value_eq":
        if not expected:
            return True  # sem valor esperado, presença basta
        return _value_matches(current, expected)

    if rule.detection_kind == "value_neq":
        return not _value_matches(current, expected)

    if rule.detection_kind == "value_in":
        opts = {x.strip().lower() for x in expected.split("|") if x.strip()}
        return current.lower() in opts

    if rule.detection_kind == "range_check":
        # expected = "min..max" ou "min.." ou "..max" ou "min..max"
        try:
            val = int(current)
        except ValueError:
            return False
        lo_str, _, hi_str = expected.partition("..")
        lo = int(lo_str) if lo_str else None
        hi = int(hi_str) if hi_str else None
        if lo is not None and val < lo:
            return False
        if hi is not None and val > hi:
            return False
        return True

    if rule.detection_kind == "regex":
        try:
            return bool(re.search(expected, current, re.IGNORECASE))
        except re.error:
            return True  # regex inválida = não falha o audit (regra mal escrita)

    # Default: conservador — não emite finding se a regra é desconhecida
    return True


# Mapeamento de equivalência semântica pra value_eq de booleans.
# Protheus aceita {1, true, yes, sim, .T.} e {0, false, no, nao, .F.} indistintamente.
_BOOL_TRUE = frozenset({"1", "true", "yes", "sim", ".t.", "t"})
_BOOL_FALSE = frozenset({"0", "false", "no", "nao", ".f.", "f"})


def _value_matches(current: str, expected: str) -> bool:
    c = current.strip().lower()
    e = expected.strip().lower()
    if c == e:
        return True
    # Equivalência booleana
    if e in _BOOL_TRUE and c in _BOOL_TRUE:
        return True
    if e in _BOOL_FALSE and c in _BOOL_FALSE:
        return True
    return False


# =============================================================================
# Audit principal
# =============================================================================


def _has_intentional_note(comment_above: str, comment_inline: str) -> bool:
    """True se algum dos comentários contém palavra-chave de justificativa."""
    text = " ".join(filter(None, (comment_above, comment_inline)))
    return bool(text) and bool(_INTENT_RE.search(text))


def audit_one_file(conn: sqlite3.Connection, file_id: int) -> int:
    """Re-audita 1 INI: limpa findings anteriores, processa regras, grava findings.

    Retorna a quantidade de findings criados.
    """
    # Pega tipo + role do arquivo
    cur = conn.execute(
        "SELECT tipo, role FROM ini_files WHERE id = ?",
        (file_id,),
    )
    row = cur.fetchone()
    if row is None:
        return 0
    tipo, role = row[0] or "", row[1] or ""

    rules = _load_rules_for_target(conn, tipo, role)
    if not rules:
        # Sem regras pra esse role; ainda assim limpa findings antigos
        conn.execute("DELETE FROM ini_audit_findings WHERE file_id = ?", (file_id,))
        return 0

    # Limpa findings antigos (rebuild atômico)
    conn.execute("DELETE FROM ini_audit_findings WHERE file_id = ?", (file_id,))

    findings: list[tuple[int, str, str, str, str, str, str, int, str]] = []

    for rule in rules:
        target_sections = _resolve_target_sections(conn, file_id, rule.section_glob)
        if not target_sections:
            # Seção não existe no INI. Em geral isso não é finding (regra de
            # seção que não se aplica), exceto se a key for is_required=True.
            # Mas como o YAML do env_manager não diferencia "key ausente em seção
            # ausente", mantemos conservador: skip.
            continue

        for sec_id, sec_name in target_sections:
            cur = conn.execute(
                """
                SELECT id, key_name, value, linha, comment_inline, comment_above
                FROM ini_keys
                WHERE file_id = ? AND section_id = ? AND key_norm = ?
                """,
                (file_id, sec_id, rule.key_name.lower()),
            )
            key_row = cur.fetchone()

            if key_row is None:
                # Chave ausente. Só vira finding se a regra exigir presença.
                if rule.detection_kind in {"key_present", "value_eq", "value_in", "range_check"}:
                    if rule.expected:  # tem valor esperado → chave é importante
                        findings.append((
                            file_id,
                            sec_name,
                            rule.key_name,
                            rule.regra_id,
                            rule.severidade,
                            f"[{sec_name}] {rule.key_name}=  (chave ausente)",
                            rule.fix_guidance,
                            0,
                            "active",
                        ))
                continue

            _kid, key_name, value, linha, c_inline, c_above = key_row
            conforme = _evaluate_value(rule, value)
            if conforme:
                continue

            # Não-conforme: detecta status (ok_with_note se justificado)
            status = "ok_with_note" if _has_intentional_note(c_above or "", c_inline or "") else "active"
            snippet = f"[{sec_name}] {key_name}={value}"
            findings.append((
                file_id,
                sec_name,
                key_name,
                rule.regra_id,
                rule.severidade,
                snippet[:200],
                rule.fix_guidance,
                int(linha),
                status,
            ))

    if findings:
        conn.executemany(
            """
            INSERT INTO ini_audit_findings (
                file_id, section_raw, key_name, regra_id, severidade,
                snippet, sugestao_fix, linha, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            findings,
        )
    return len(findings)


def audit_files(conn: sqlite3.Connection, file_ids: Sequence[int]) -> AuditResult:
    """Re-audita todos os ``file_ids`` e devolve sumário consolidado."""
    result = AuditResult()
    for fid in file_ids:
        count = audit_one_file(conn, fid)
        result.files_audited += 1
        result.findings_total += count

    # Conta por severidade (1 SELECT consolidado)
    cur = conn.execute(
        """
        SELECT severidade, COUNT(*) FROM ini_audit_findings
        WHERE file_id IN ({}) AND status = 'active'
        GROUP BY severidade
        """.format(",".join("?" * len(file_ids))),
        list(file_ids),
    ) if file_ids else None
    if cur is not None:
        for sev, cnt in cur.fetchall():
            if sev in result.by_severity:
                result.by_severity[sev] = int(cnt)

    conn.commit()
    return result


__all__ = [
    "AuditResult",
    "audit_files",
    "audit_one_file",
]
