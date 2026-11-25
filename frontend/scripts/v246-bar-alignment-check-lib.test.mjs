import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  AUDIT_CHECKS, BARS, DEFAULT_BASE, VIEWPORTS,
  auditVerdict, bottomVerdict, controlHeightAt, groupRows, heightVerdict, parseArgs,
} from './v246-bar-alignment-check-lib.mjs';

test('parseArgs defaults to the local admin, strips a trailing slash, takes --out and --audit', () => {
  assert.deepEqual(parseArgs([]), { base: DEFAULT_BASE, out: null, audit: null });
  assert.deepEqual(parseArgs(['--base', 'http://localhost:4123/', '--audit', 'a.json']),
    { base: 'http://localhost:4123', out: null, audit: 'a.json' });
  assert.throws(() => parseArgs(['--widths', '390']), /unknown or incomplete flag --widths/);
  assert.throws(() => parseArgs(['--out']), /unknown or incomplete flag --out/);
});

test('measures phone, tablet and desktop, with 44px controls below 1024px and 28px from it', () => {
  assert.deepEqual(VIEWPORTS.map((v) => v.width), [390, 820, 1440]);
  assert.equal(controlHeightAt(390), 44);
  assert.equal(controlHeightAt(1023), 44);
  assert.equal(controlHeightAt(1024), 28);
  assert.equal(controlHeightAt(1440), 28);
});

test('checks the five bars v246 wraps in sb-field', () => {
  assert.deepEqual(BARS.map((b) => b.name), ['trades', 'calendar', 'analytics', 'watchlist', 'dashboard']);
  assert.deepEqual(BARS.map((b) => b.path), ['/trades', '/calendar', '/insights/analytics', '/watchlist', '/dashboard']);
  assert.equal(BARS.find((b) => b.name === 'calendar').bar, 'sb-control-row[align="end"]');
  assert.deepEqual(AUDIT_CHECKS, ['overflow', 'tap', 'text']);
});

test('groups fields into visual rows by their vertical centre', () => {
  const rows = groupRows([
    { name: 'b', top: 0, bottom: 44 }, { name: 'a', top: 20, bottom: 44 }, { name: 'c', top: 60, bottom: 104 },
  ]);
  assert.deepEqual(rows.map((row) => row.map((box) => box.name)), [['b', 'a'], ['c']]);
  assert.deepEqual(groupRows([]), []);
});

test('passes rows whose bottoms agree within a pixel and names the row that does not', () => {
  assert.deepEqual(bottomVerdict([{ name: 'a', top: 0, bottom: 44 }, { name: 'b', top: 18, bottom: 44.8 }]), []);
  assert.deepEqual(bottomVerdict([{ name: 'Range', top: 0, bottom: 52 }, { name: 'Unit', top: 0, bottom: 24 }]),
    ['row 1: Range=52.0 Unit=24.0']);
  assert.deepEqual(bottomVerdict([]), []);
});

test('names every control that is not --control-h tall, half a pixel or more off', () => {
  assert.deepEqual(heightVerdict([{ name: 'Strategy', height: 28.4 }, { name: '‹', height: 24 }], 28), ['‹=24.0']);
  assert.deepEqual(heightVerdict([], 44), []);
});

test('keeps only the bar pages and the overflow, tap and text checks from the audit', () => {
  const unallowed = [
    { route: '/trades', width: 390, check: 'tap', selector: 'button.x', detail: '30x30' },
    { route: '/trades', width: 390, check: 'baseline', selector: 'p', detail: '3px' },
    { route: '/system', width: 390, check: 'overflow', selector: 'main', detail: '+12px' },
  ];
  assert.deepEqual(auditVerdict(unallowed), ['/trades @390 tap button.x -- 30x30']);
  assert.deepEqual(auditVerdict([]), []);
});
