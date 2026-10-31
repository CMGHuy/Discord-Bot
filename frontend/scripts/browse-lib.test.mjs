// node --test frontend/scripts/browse-lib.test.mjs
import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { CLIP_MARGIN_PX, clipBox, parseArgs } from './browse-lib.mjs';

const PAGE = { width: 1440, height: 2000 };

test('CLIP_MARGIN_PX is 8', () => {
  assert.equal(CLIP_MARGIN_PX, 8);
});

test('clipBox pads the box by the margin on every side', () => {
  assert.deepEqual(clipBox({ x: 100, y: 200, width: 300, height: 50 }, PAGE),
    { x: 92, y: 192, width: 316, height: 66 });
});

test('clipBox honours an explicit margin', () => {
  assert.deepEqual(clipBox({ x: 100, y: 200, width: 300, height: 50 }, PAGE, 0),
    { x: 100, y: 200, width: 300, height: 50 });
});

test('clipBox clamps to the page at the top-left', () => {
  assert.deepEqual(clipBox({ x: 3, y: 0, width: 50, height: 20 }, PAGE),
    { x: 0, y: 0, width: 61, height: 28 });
});

test('clipBox clamps to the page at the bottom-right', () => {
  assert.deepEqual(clipBox({ x: 1400, y: 1980, width: 40, height: 20 }, PAGE),
    { x: 1392, y: 1972, width: 48, height: 28 });
});

test('clipBox rounds outward to whole pixels', () => {
  assert.deepEqual(clipBox({ x: 10.4, y: 20.6, width: 5.2, height: 5.2 }, PAGE, 0),
    { x: 10, y: 20, width: 6, height: 6 });
});

test('clipBox keeps an element taller than the viewport whole', () => {
  assert.deepEqual(clipBox({ x: 0, y: 100, width: 1440, height: 5000 }, { width: 1440, height: 6000 }),
    { x: 0, y: 92, width: 1440, height: 5016 });
});

test('clipBox returns null for a missing or zero-size box', () => {
  assert.equal(clipBox(null, PAGE), null);
  assert.equal(clipBox(undefined, PAGE), null);
  assert.equal(clipBox({ x: 10, y: 10, width: 0, height: 40 }, PAGE), null);
  assert.equal(clipBox({ x: 10, y: 10, width: 40, height: 0 }, PAGE), null);
});

test('clipBox returns null for a box entirely outside the page', () => {
  assert.equal(clipBox({ x: 2000, y: 10, width: 10, height: 10 }, PAGE), null);
  assert.equal(clipBox({ x: 10, y: 2100, width: 10, height: 10 }, PAGE), null);
});

test('parseArgs keeps the old defaults and adds clip: null', () => {
  assert.deepEqual(parseArgs(['shots']), {
    cmd: 'shots', paths: [], widths: [1440, 1024, 768, 390], base: 'https://bomeo-capital.com',
    out: null, clicks: [], settle: 1500, clip: null,
  });
  assert.equal(parseArgs([]).cmd, 'login');
});

test('parseArgs keeps the existing flags', () => {
  const opts = parseArgs(['shots', '--path', 'trades/x', '--path', '/risk', '--widths', '768,390',
    '--base', 'http://localhost:1234/', '--out', 'shots', '--click', '.a', '--click', '.b', '--settle', '300']);
  assert.deepEqual(opts.paths, ['/trades/x', '/risk']);
  assert.deepEqual(opts.widths, [768, 390]);
  assert.equal(opts.base, 'http://localhost:1234');
  assert.equal(opts.out, 'shots');
  assert.deepEqual(opts.clicks, ['.a', '.b']);
  assert.equal(opts.settle, 300);
});

test('parseArgs stores the --clip selector', () => {
  assert.equal(parseArgs(['shots', '--path', 'risk', '--clip', '.risk-card']).clip, '.risk-card');
});

test('parseArgs rejects --clip without a selector', () => {
  assert.throws(() => parseArgs(['shots', '--clip']), /--clip needs a CSS selector/);
});

test('parseArgs still rejects an unknown flag', () => {
  assert.throws(() => parseArgs(['shots', '--nope', 'x']), /unknown flag --nope/);
});
