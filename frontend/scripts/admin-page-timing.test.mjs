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

import { missingRequirements, PAGES, PNL_BASIS } from './admin-page-timing.mjs';

test('Risk requires both clocks and the P&L basis', () => {
  const risk = PAGES.find((p) => p.name === 'Risk');
  assert.deepEqual(missingRequirements('FX rates as of Oct 29 daily bars through Oct 28 close ' + PNL_BASIS, {}, risk), []);
  assert.deepEqual(missingRequirements('FX rates as of Oct 29', {}, risk), ['daily bars through', PNL_BASIS]);
});
test('the dashboard requires the sparkline snapshot cell', () => {
  const dash = PAGES.find((p) => p.name === 'Dashboard');
  assert.deepEqual(missingRequirements('', { 'sb-portfolio-value sb-market-value': true }, dash), []);
  assert.deepEqual(missingRequirements('', {}, dash), ['sb-portfolio-value sb-market-value']);
});
test('a page with no requirements misses nothing', () => {
  assert.deepEqual(missingRequirements('', {}, { name: 'Trades', rail: 'Trades' }), []);
});
test('a missing label fails the visit; a v201 visit without the field keeps its verdict', () => {
  const ok = { firstDataMs: 900, calls: [], scanMs: [80], cells: 3, unlabelled: 0, timedOut: false };
  assert.equal(visitVerdict(ok).pass, true);
  const bad = visitVerdict({ ...ok, missing: ['daily bars through'] });
  assert.equal(bad.pass, false);
  assert.deepEqual(bad.reasons, ['missing label: daily bars through']);
});
test('PAGES keeps v201 order and appends the three snapshot pages', () => {
  assert.deepEqual(PAGES.map((p) => p.name),
    ['Dashboard', 'Trades', 'Trade detail', 'Watchlist', 'Risk', 'Analytics', 'Calendar']);
});

import { preflightSnapshots } from './admin-page-timing.mjs';

test('the v204 preflight needs snapshots[] and status.stale_snapshot_s', () => {
  assert.equal(preflightSnapshots({ snapshots: [], status: { stale_snapshot_s: 5 } }), null);
  const msg = 'v204 not deployed: /market/updates has no snapshots';
  assert.equal(preflightSnapshots({ status: { stale_snapshot_s: 5 } }), msg);
  assert.equal(preflightSnapshots({ snapshots: [], status: {} }), msg);
  assert.equal(preflightSnapshots(null), msg);
});
