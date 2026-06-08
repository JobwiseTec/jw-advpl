// Smoke-test Node puro (sem framework). Roda: node hooks/session-start.test.mjs
import assert from 'node:assert';

process.env.PLUGADVPL_HOOK_TEST = '1';
const { HEALTHY_REMINDER, isHookQuiet } = await import('./session-start.mjs');

// 1. O lembrete existe e cita a regra-chave.
assert.ok(HEALTHY_REMINDER.includes('plugadvpl arch'), 'lembrete deve citar arch');
assert.ok(HEALTHY_REMINDER.includes('Antes de Read'), 'lembrete deve ser imperativo');
assert.ok(HEALTHY_REMINDER.length < 700, 'lembrete deve ser curto');

// 2. Opt-out reconhece valores truthy.
for (const v of ['1', 'true', 'on', 'sim', 'YES']) {
  process.env.PLUGADVPL_HOOK_QUIET = v;
  assert.strictEqual(isHookQuiet(), true, `quiet deve reconhecer '${v}'`);
}
process.env.PLUGADVPL_HOOK_QUIET = '';
assert.strictEqual(isHookQuiet(), false, 'sem env → não-quiet');

console.log('session-start.test.mjs: OK');
