#!/usr/bin/env node
// hooks/stop-verify.mjs — plugadvpl Stop hook (Fase 3 roadmap-ia)
//
// Antes de o agente finalizar, extrai os símbolos afirmados no bloco
// <plugadvpl-claims> da última resposta e roda `verify-claims` contra o índice.
// Bloqueia (decision:block) SÓ em not_found de alta confiança (política da
// Fase 1) — re-prompt cirúrgico, listando só o que falhou. Failure-silent:
// qualquer erro libera (nunca trava a sessão). Loop-guard via stop_hook_active.
//
// Ver docs/roadmap-ia/03-grounding-flow.md.

import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const CLAIMS_RE = /<plugadvpl-claims>\s*([\s\S]*?)\s*<\/plugadvpl-claims>/g;

function readStdin() {
  try {
    return readFileSync(0, 'utf-8');
  } catch {
    return '';
  }
}

function extractClaims(text) {
  const matches = [...(text || '').matchAll(CLAIMS_RE)].map((m) => m[1]);
  if (!matches.length) return [];
  try {
    const data = JSON.parse(matches[matches.length - 1]); // último bloco vence
    return Array.isArray(data.claims) ? data.claims : [];
  } catch {
    return [];
  }
}

function lastAssistantText(transcriptPath) {
  let raw;
  try {
    raw = readFileSync(transcriptPath, 'utf-8');
  } catch {
    return '';
  }
  let text = '';
  for (const line of raw.split('\n')) {
    if (!line.trim()) continue;
    let obj;
    try {
      obj = JSON.parse(line);
    } catch {
      continue;
    }
    const m = obj.message || obj;
    if (m && m.role === 'assistant') {
      const c = m.content;
      if (typeof c === 'string') text = c;
      else if (Array.isArray(c))
        text = c.map((p) => (typeof p === 'string' ? p : p && p.text ? p.text : '')).join('');
    }
  }
  return text;
}

// Só bloqueia o que a Fase 1 marca como acionável: not_found de alta confiança
// (ex.: símbolo customer ausente em corpus completo). Nunca relation_absent/low.
function actionableMisses(verdict) {
  const results = verdict && Array.isArray(verdict.results) ? verdict.results : [];
  return results.filter((r) => r.status === 'not_found' && r.confidence === 'high');
}

function runVerify(claims) {
  const cmd = JSON.parse(
    process.env.PLUGADVPL_VERIFY_CMD ||
      '["plugadvpl","--format","json","verify-claims","--stdin"]',
  );
  const [bin, ...args] = cmd;
  const out = execFileSync(bin, args, {
    input: JSON.stringify({ claims }),
    encoding: 'utf-8',
    timeout: 8000,
    stdio: ['pipe', 'pipe', 'ignore'],
  });
  return JSON.parse(out);
}

function main() {
  try {
    const event = JSON.parse(readStdin() || '{}');
    if (event.stop_hook_active) process.exit(0); // loop-guard
    const text = event.transcript_path
      ? lastAssistantText(event.transcript_path)
      : event.last_assistant_message || '';
    const claims = extractClaims(text);
    if (!claims.length) process.exit(0); // nada verificável -> não dispara
    let verdict;
    try {
      verdict = runVerify(claims);
    } catch {
      process.exit(0); // verify falhou (sem CLI/índice) -> libera
    }
    const misses = actionableMisses(verdict);
    if (!misses.length) process.exit(0); // tudo grounded -> libera
    const syms = misses.map((m) => m.symbol).join(', ');
    const out = {
      decision: 'block',
      reason:
        `Verificacao plugadvpl: simbolos nao encontrados no indice (${syms}). ` +
        `Corrija o nome ou marque explicitamente como nao-verificado antes de finalizar. ` +
        `(verify-claims: not_found/high)`,
    };
    process.stdout.write(JSON.stringify(out));
    process.exit(0);
  } catch {
    process.exit(0); // never break the session
  }
}

// Permite import em teste sem rodar main() (que lê stdin real).
if (process.env.PLUGADVPL_HOOK_TEST !== '1') {
  main();
}
export { extractClaims, lastAssistantText, actionableMisses };
