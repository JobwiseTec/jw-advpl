"""Fase 4 do roadmap-ia — dispatch hardening.

Scorers determinísticos para um routing-eval (top-1 + set-F1) e um lint de
qualidade de `description` de skill (a description É o roteador — Anthropic
Agent Skills). A predição de skill por um LLM é opt-in/offline; aqui só o
scoring/lint determinístico ($0), que entra no CI.

Ver docs/roadmap-ia/04-dispatch-hardening.md.
"""

from __future__ import annotations

import re

# Termos vagos que, sozinhos, são uma description ruim (Anthropic best-practices).
_VAGUE_STANDALONE = {
    "helper",
    "helpers",
    "utils",
    "util",
    "tools",
    "tool",
    "data",
    "files",
    "file",
    "documents",
}

# 1ª pessoa: a description entra no system prompt; deve ser 3ª pessoa/imperativo.
_FIRST_PERSON_RE = re.compile(
    r"(?i)^\s*eu\b|\beu (ajudo|posso|consigo|vou|faço)\b|\bI (can|help|will|am)\b"
)

_MIN_DESCRIPTION_LEN = 25


def top1_accuracy(cases: list[dict[str, str]]) -> float:
    """Acurácia top-1 de seleção (predicted == expected). Lista vazia → 1.0."""
    if not cases:
        return 1.0
    correct = sum(1 for c in cases if c.get("predicted") == c.get("expected"))
    return correct / len(cases)


def set_f1(predicted: set[str], expected: set[str]) -> float:
    """F1 não-ordenado entre dois conjuntos (multi-skill / tool-call-f1)."""
    if not predicted and not expected:
        return 1.0
    tp = len(predicted & expected)
    if tp == 0:
        return 0.0
    precision = tp / len(predicted)
    recall = tp / len(expected)
    return 2 * precision * recall / (precision + recall)


def lint_description(name: str, description: str) -> list[str]:
    """Erros de qualidade numa description de skill (vazio = ok).

    Regras (ERROR): curta demais (vaga), termo vago sozinho, 1ª pessoa.
    """
    issues: list[str] = []
    d = description.strip()
    if len(d) < _MIN_DESCRIPTION_LEN:
        issues.append(
            f"{name}: description curta demais ({len(d)} chars) — vaga, diga O QUÊ + QUANDO"
        )
    if d.lower().rstrip(".") in _VAGUE_STANDALONE:
        issues.append(f"{name}: description vaga ('{d}') — use gatilhos e caso de uso")
    if _FIRST_PERSON_RE.search(d):
        issues.append(f"{name}: description em 1ª pessoa — use 3ª pessoa/imperativo ('Use ao...')")
    return issues
