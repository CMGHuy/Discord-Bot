import assert from 'node:assert/strict';
import { test } from 'node:test';
import { labelOk, visitVerdict, renderTable } from './admin-page-timing.mjs';

test('a cell labelled with an age, last close or as-of passes', () => {
  for (const text of ['12 s ago', 'last close · Fri 16:00 ET', 'as of Wed 15:40 ET', '3 min ago']) {
    assert.equal(labelOk({ age: text, valueHidden: false }), true);
  }
});
test('a spinner-only cell (never priced) passes; an unlabelled value fails', () => {
  assert.equal(labelOk({ age: '', valueHidden: true }), true);
  assert.equal(labelOk({ age: '', valueHidden: false }), false);
});
test('a visit passes only within every limit', () => {
  const ok = { firstDataMs: 900, calls: [{ path: '/api/v1/trades', ms: 400, excluded: false }],
    scanMs: [80, 120], cells: 5, unlabelled: 0, timedOut: false };
  assert.equal(visitVerdict(ok).pass, true);
  assert.equal(visitVerdict({ ...ok, firstDataMs: 2100 }).pass, false);
  assert.equal(visitVerdict({ ...ok, calls: [{ path: '/api/v1/dashboard', ms: 2500, excluded: false }] }).pass, false);
  assert.equal(visitVerdict({ ...ok, calls: [{ path: '/api/v1/equity/candles', ms: 9000, excluded: true }] }).pass, true);
  assert.equal(visitVerdict({ ...ok, scanMs: [600] }).pass, false);
  assert.equal(visitVerdict({ ...ok, unlabelled: 1 }).pass, false);
  assert.equal(visitVerdict({ ...ok, timedOut: true }).pass, false);
});
test('the table has one row per visit with its verdict', () => {
  const md = renderTable([{ pass: 'cold', page: 'Trades', firstDataMs: 900, slowest: '/api/v1/trades 400 ms',
    scanMaxMs: 120, cells: 5, unlabelled: 0, verdict: 'PASS' }]);
  assert.match(md, /\| cold \| Trades \| 0\.9 s \| \/api\/v1\/trades 400 ms \| 120 ms \| 5 \/ 0 \| PASS \|/);
});
