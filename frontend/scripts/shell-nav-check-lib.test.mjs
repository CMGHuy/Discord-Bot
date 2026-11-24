import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  DEFAULT_BASE, DEFAULT_TABS, EDITED_PATHS, EDITED_TABS, MIN_TARGET_PX, RAIL_PATHS, RAIL_WIDTH_PX, VIEWPORTS,
  exitCode, formatResult, parseArgs, sameList, smallTargets, tooltipVerdict,
} from './shell-nav-check-lib.mjs';

test('parseArgs defaults to the local admin and strips a trailing slash from --base', () => {
  assert.deepEqual(parseArgs([]), { base: DEFAULT_BASE, out: null });
  assert.equal(DEFAULT_BASE, 'http://localhost:1234');
  assert.deepEqual(parseArgs(['--base', 'http://localhost:4123/', '--out', 'x']), { base: 'http://localhost:4123', out: 'x' });
});

test('parseArgs rejects an unknown or incomplete flag', () => {
  assert.throws(() => parseArgs(['--widths', '390']), /unknown or incomplete flag --widths/);
  assert.throws(() => parseArgs(['--base']), /unknown or incomplete flag --base/);
});

test('checks the narrow phone, the phone, the tablet and the desktop (spec v240 §9)', () => {
  assert.deepEqual(VIEWPORTS.map((v) => v.width), [320, 390, 820, 1440]);
  assert.equal(RAIL_WIDTH_PX, 64);
  assert.equal(MIN_TARGET_PX, 44);
});

test('expects the rail order and the round-trip bars the spec names (v240 §5, §6, §11)', () => {
  assert.deepEqual(RAIL_PATHS, ['/dashboard', '/watchlist', '/trades', '/calendar', '/risk', '/insights', '/system']);
  assert.deepEqual(DEFAULT_TABS, ['Home', 'Watchlist', 'Trades', 'Calendar', 'More']);
  assert.deepEqual(EDITED_TABS, ['Home', 'Trades', 'Calendar', 'Risk', 'More']);
  assert.deepEqual(EDITED_PATHS, ['/dashboard', '/trades', '/calendar', '/risk']);
});

test('smallTargets names boxes under 44px on either side, with half a pixel for rounding', () => {
  const boxes = [
    { name: 'ok', width: 44, height: 44 }, { name: 'rounded', width: 43.6, height: 48 },
    { name: 'thin', width: 60, height: 28 }, { name: 'narrow', width: 30, height: 44 },
  ];
  assert.deepEqual(smallTargets(boxes), ['thin', 'narrow']);
  assert.deepEqual(smallTargets([]), []);
});

test('tooltipVerdict names the first thing wrong, or null', () => {
  assert.equal(tooltipVerdict({ name: '', tooltip: 'Risk', visible: true }), 'no-name');
  assert.equal(tooltipVerdict({ name: 'Risk', tooltip: null, visible: false }), 'no-tooltip');
  assert.equal(tooltipVerdict({ name: 'Risk', tooltip: 'Risk', visible: false }), 'not-shown');
  assert.equal(tooltipVerdict({ name: 'Risk', tooltip: 'Heat', visible: true }), 'tooltip-not-name');
  assert.equal(tooltipVerdict({ name: 'Risk', tooltip: 'Risk', visible: true }), null);
});

test('sameList compares in order; exitCode is 0 only when every check passed; formatResult reads PASS/FAIL', () => {
  assert.equal(sameList(['a', 'b'], ['a', 'b']), true);
  assert.equal(sameList(['b', 'a'], ['a', 'b']), false);
  assert.equal(exitCode([{ ok: true }, { ok: true }]), 0);
  assert.equal(exitCode([{ ok: true }, { ok: false }]), 1);
  assert.equal(exitCode([]), 0);
  assert.equal(formatResult({ name: 'rail-width@1440', ok: true, detail: '64px' }), 'PASS rail-width@1440');
  assert.equal(formatResult({ name: 'rail-width@820', ok: false, detail: '80px' }), 'FAIL rail-width@820 -- 80px');
  assert.equal(formatResult({ name: 'x', ok: false, detail: '' }), 'FAIL x');
});
