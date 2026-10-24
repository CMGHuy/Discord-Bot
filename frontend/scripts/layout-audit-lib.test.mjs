// node --test frontend/scripts/layout-audit-lib.test.mjs
// The pure half of the v179 layout audit. The browser half (layout-audit.mjs)
// is exercised by a real run against a local replica (plan task V179-20).
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  CHECKS, FULL_WIDTHS, ROUTES, classify, countByCheck, dedupe, formatFinding, inScope, isVisuallyHidden, parseArgs, pickIds,
  resolveRoute, slug, validateAllow, vcenterGeometry,
} from './layout-audit-lib.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const TODAY = '2026-10-19';

const finding = (over = {}) => ({
  route: '/analytics?tab=attribution', width: 390, check: 'offscreen', selector: 'sb-heat-grid > div.cell',
  text: '8m', detail: 'right edge at 462px of 390px', ...over,
});
const entry = (over = {}) => ({
  route: '/analytics?tab=attribution', width: 390, check: 'offscreen', selector: 'sb-heat-grid > div.cell',
  reason: 'canvas internals of a third-party chart', date: '2026-10-19', ...over,
});

test('ROUTES visits every route and tab once (spec §2 plus v188 /cancels: 28)', () => {
  assert.equal(ROUTES.length, 28);
  assert.ok(ROUTES.includes('/cancels'));
  assert.equal(new Set(ROUTES).size, ROUTES.length);
  assert.ok(ROUTES.every((route) => route.startsWith('/')));
  for (const tab of ['attribution', 'execution', 'edge', 'pipeline', 'tuning', 'partials']) {
    assert.ok(ROUTES.includes(`/analytics?tab=${tab}`), tab);
  }
  for (const route of ['/dashboard', '/trades', '/trades/:id', '/trades/:id?tab=journal', '/plans/:plan', '/calendar/:date',
    '/watchlist/:symbol', '/risk', '/system?tab=logs', '/system?tab=scan', '/versions', '/research', '/reports?tab=gates', '/ui']) {
    assert.ok(ROUTES.includes(route), route);
  }
});

test('CHECKS are the spec six plus vcenter, in order', () => {
  assert.deepEqual([...CHECKS], ['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter']);
});

test('parseArgs: defaults are the local replica at the three widths', () => {
  const opts = parseArgs([]);
  assert.equal(opts.base, 'http://localhost:1234');
  assert.deepEqual(opts.widths, [...FULL_WIDTHS]);
  assert.deepEqual([...FULL_WIDTHS], [390, 768, 1440]);
  assert.equal(opts.out, null);
  assert.equal(opts.allow, null);
  assert.equal(opts.prune, false);
  assert.equal(opts.settle, 1500);
});

test('parseArgs: every flag, a trailing slash on --base, and --prune', () => {
  const opts = parseArgs(['--base', 'https://bomeo-capital.com/', '--widths', '390,1440', '--out', 'o',
    '--allow', 'a.json', '--prune', '--settle', '800']);
  assert.equal(opts.base, 'https://bomeo-capital.com');
  assert.deepEqual(opts.widths, [390, 1440]);
  assert.equal(opts.out, 'o');
  assert.equal(opts.allow, 'a.json');
  assert.equal(opts.prune, true);
  assert.equal(opts.settle, 800);
});

test('parseArgs: unknown flags, missing values and bad widths throw', () => {
  assert.throws(() => parseArgs(['--path', '/x']), /unknown or incomplete flag --path/);
  assert.throws(() => parseArgs(['--base']), /incomplete flag --base/);
  assert.throws(() => parseArgs(['--widths', '390,abc']), /bad --widths/);
  assert.throws(() => parseArgs(['--widths', '200']), /bad --widths/);
});

test('resolveRoute fills every placeholder and encodes it', () => {
  const ids = { id: 'abc 1', plan: 'p1', symbol: 'BRK.B', date: '2026-10-01' };
  assert.equal(resolveRoute('/trades/:id?tab=why', ids), '/trades/abc%201?tab=why');
  assert.equal(resolveRoute('/plans/:plan', ids), '/plans/p1');
  assert.equal(resolveRoute('/watchlist/:symbol', ids), '/watchlist/BRK.B');
  assert.equal(resolveRoute('/calendar/:date', ids), '/calendar/2026-10-01');
  assert.equal(resolveRoute('/analytics?tab=edge', {}), '/analytics?tab=edge');
});

test('resolveRoute refuses a route it cannot fill', () => {
  assert.throws(() => resolveRoute('/plans/:plan', { plan: null }), /no plan to visit \/plans\/:plan/);
});

test('pickIds: a closed trade (id and day), an open plan, a symbol with trades', () => {
  const ids = pickIds({
    closed: { items: [{ id: 't1', closed_at: '2026-10-01T15:30:00Z' }] },
    open: { items: [{ id: 'p9' }] },
    pending: { items: [{ id: 'p0' }] },
    tickers: { tickers: [{ symbol: 'ZZZ', open_trades: 0, closed_trades: 0 }, { symbol: 'AAPL', open_trades: 1, closed_trades: 3 }] },
  });
  assert.deepEqual(ids, { id: 't1', date: '2026-10-01', plan: 'p9', symbol: 'AAPL' });
});

test('pickIds: a pending plan when nothing is open; null for a gap, never a guess', () => {
  const empty = { items: [] };
  assert.equal(pickIds({ closed: empty, open: empty, pending: { items: [{ id: 'p0' }] }, tickers: { tickers: [] } }).plan, 'p0');
  assert.deepEqual(pickIds({ closed: empty, open: empty, pending: empty, tickers: { tickers: [] } }),
    { id: null, date: null, plan: null, symbol: null });
});

test('dedupe keeps one finding per route, width, check and selector, with a count', () => {
  const out = dedupe([finding(), finding({ text: '9m' }), finding({ width: 768 })]);
  assert.equal(out.length, 2);
  assert.equal(out[0].count, 2);
  assert.equal(out[0].text, '8m');
  assert.equal(out[1].count, 1);
});

test('classify: a finding no entry matches is unallowed', () => {
  const { unallowed, allowed, stale } = classify([finding()], [], TODAY);
  assert.equal(unallowed.length, 1);
  assert.equal(allowed.length, 0);
  assert.equal(stale.length, 0);
});

test('classify: an exact entry allows the finding and carries its reason', () => {
  const { unallowed, allowed } = classify([finding()], [entry()], TODAY);
  assert.equal(unallowed.length, 0);
  assert.equal(allowed[0].reason, 'canvas internals of a third-party chart');
});

test("classify: width '*' matches every width, a number only its own", () => {
  assert.equal(classify([finding({ width: 1440 })], [entry({ width: '*' })], TODAY).unallowed.length, 0);
  assert.equal(classify([finding({ width: 1440 })], [entry({ width: 390 })], TODAY).unallowed.length, 1);
});

test('classify: route, check and selector must match exactly', () => {
  for (const over of [{ route: '/analytics' }, { check: 'clipped' }, { selector: 'sb-heat-grid > div' }]) {
    assert.equal(classify([finding(over)], [entry()], TODAY).unallowed.length, 1, JSON.stringify(over));
  }
});

test('classify: an entry no finding matches is stale', () => {
  const kept = entry();
  const gone = entry({ selector: 'sb-waterfall > text.label' });
  assert.deepEqual(classify([finding()], [kept, gone], TODAY).stale, [gone]);
});

test('classify rejects an entry without a reason, with a bad or future date, or naming what does not exist', () => {
  const cases = [
    [{ reason: '' }, /reason/],
    [{ reason: 'ok' }, /reason/],
    [{ date: '19-10-2026' }, /date/],
    [{ date: '2026-10-20' }, /date/],
    [{ route: '/nowhere' }, /unknown route/],
    [{ check: 'colour' }, /unknown check/],
    [{ width: '390' }, /width/],
    [{ selector: '' }, /selector/],
  ];
  for (const [over, message] of cases) {
    assert.throws(() => classify([], [entry(over)], TODAY), message, JSON.stringify(over));
  }
});

test("inScope: '*' always, a number only when that width ran", () => {
  assert.equal(inScope(entry({ width: '*' }), [390]), true);
  assert.equal(inScope(entry({ width: 768 }), [390, 1440]), false);
  assert.equal(inScope(entry({ width: 390 }), [390]), true);
});

test('formatFinding names route, width, check, selector, text, detail and repeats', () => {
  assert.equal(formatFinding({ ...finding(), count: 3 }),
    '/analytics?tab=attribution @390 offscreen sb-heat-grid > div.cell "8m" -- right edge at 462px of 390px (x3)');
  assert.equal(formatFinding({ ...finding({ text: '' }), count: 1 }),
    '/analytics?tab=attribution @390 offscreen sb-heat-grid > div.cell -- right edge at 462px of 390px');
});

test('countByCheck counts every check, zero included', () => {
  assert.deepEqual(countByCheck([finding(), finding({ check: 'tap' }), finding({ check: 'tap' })]),
    { overflow: 0, offscreen: 1, clipped: 0, tap: 2, text: 0, baseline: 0, vcenter: 0 });
});

test('slug matches browse.mjs file names', () => {
  assert.equal(slug('/analytics?tab=partials'), 'analytics_tab_partials');
  assert.equal(slug('/trades/:id'), 'trades_id');
  assert.equal(slug('/'), 'root');
});

test('the checked-in allow-list is valid today', () => {
  const doc = JSON.parse(readFileSync(join(HERE, 'layout-audit.allow.json'), 'utf8'));
  assert.equal(typeof doc.$comment, 'string');
  assert.ok(Array.isArray(doc.entries));
  assert.doesNotThrow(() => validateAllow(doc.entries, new Date().toISOString().slice(0, 10)));
});

test('isVisuallyHidden: the standard clipped 1px absolute box is hidden, however it clips', () => {
  const box = { position: 'absolute', overflow: 'hidden', clip: 'auto', clipPath: 'inset(50%)' };
  assert.equal(isVisuallyHidden(box, { width: 1, height: 1 }), true);
  assert.equal(isVisuallyHidden({ ...box, clipPath: 'none', clip: 'rect(0px, 0px, 0px, 0px)' }, { width: 1, height: 1 }), true);
});

test('isVisuallyHidden: a visibly clipped or visibly sized element is still audited', () => {
  const box = { position: 'absolute', overflow: 'hidden', clip: 'auto', clipPath: 'inset(50%)' };
  assert.equal(isVisuallyHidden({ ...box, position: 'static' }, { width: 1, height: 1 }), false);
  assert.equal(isVisuallyHidden(box, { width: 120, height: 18 }), false);
  assert.equal(isVisuallyHidden({ ...box, clipPath: 'none' }, { width: 1, height: 1 }), false);
  assert.equal(isVisuallyHidden({ position: 'static', overflow: 'hidden', clip: 'auto', clipPath: 'none' }, { width: 90, height: 18 }), false);
});

test('the audit page code asks the lib predicate, not a class-name list', () => {
  const src = readFileSync(join(HERE, 'layout-audit.mjs'), 'utf8');
  assert.match(src, /isVisuallyHidden/);
  assert.doesNotMatch(src, /closest\('\.sr-only/);
});

const geo = vcenterGeometry();
const rect = (top, bottom, left = 0, right = 10) => ({ top, bottom, left, right, height: bottom - top });

test('centreOffset: positive when the inner box sits low, negative when high, zero when centred', () => {
  assert.equal(geo.centreOffset(rect(10, 20), rect(0, 30)), 0);
  assert.equal(geo.centreOffset(rect(14, 24), rect(0, 30)), 4);
  assert.equal(geo.centreOffset(rect(5, 15), rect(0, 30)), -5);
});

test('contentBox: a cell is measured inside its padding and borders, so uneven padding shows as an offset', () => {
  const box = geo.contentBox(rect(0, 40), { padTop: 6, padBottom: 6, borderTop: 0, borderBottom: 1 });
  assert.deepEqual(box, { top: 6, bottom: 33 });
  // Text 10..27 in a 6/6-padded 42px cell (content 6..36): 2.5px high, past the 2px limit.
  assert.equal(geo.centreOffset(rect(10, 27), geo.contentBox(rect(0, 42), { padTop: 6, padBottom: 6, borderTop: 0, borderBottom: 0 })), -2.5);
});

test('nearestBeside: picks the closest text on the same line as the icon, either side', () => {
  const icon = rect(10, 26, 100, 116);
  const right = rect(11, 27, 120, 180);
  const left = rect(11, 27, 40, 98);
  assert.equal(geo.nearestBeside(icon, [right, left]), left);
  assert.equal(geo.nearestBeside(icon, [right]), right);
});

test('nearestBeside: ignores text on another line, too far away, or with no height', () => {
  const icon = rect(10, 26, 100, 116);
  assert.equal(geo.nearestBeside(icon, [rect(40, 56, 120, 180)]), null);
  assert.equal(geo.nearestBeside(icon, [rect(11, 27, 141, 200)]), null);
  assert.equal(geo.nearestBeside(icon, [rect(18, 18, 120, 180)]), null);
  assert.equal(geo.nearestBeside(icon, []), null);
});

test('vcenterGeometry survives the trip into the page as source', () => {
  const shipped = new Function(`return (${vcenterGeometry.toString()})()`)();
  assert.equal(shipped.centreOffset(rect(14, 24), rect(0, 30)), 4);
});
