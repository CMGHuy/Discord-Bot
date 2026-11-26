/**
 * Pure helpers for v248-price-rows-check.mjs (v248 V248-16, spec 1g): the pages, the widths,
 * the fixture rows the two intercepted reads serve, and the verdicts. No browser here, so
 * `node --test` covers all of it.
 */
import { fileURLToPath } from 'node:url';

export { exitCode, formatResult } from './shell-nav-check-lib.mjs';

export const DEFAULT_BASE = 'http://localhost:1234';

export const VIEWPORTS = Object.freeze([
  Object.freeze({ name: 'phone', width: 390, height: 844 }),
  Object.freeze({ name: 'tablet', width: 768, height: 1024 }),
  Object.freeze({ name: 'desktop', width: 1440, height: 900 }),
]);

export const PAGES = Object.freeze([
  Object.freeze({ name: 'dashboard', path: '/dashboard', scope: 'sb-positions-table' }),
  Object.freeze({ name: 'trades', path: '/trades', scope: 'main' }),
]);

export const FIXTURE = fileURLToPath(new URL('../src/app/testing/fixtures/v248-worst-case-row.json', import.meta.url));

const FLAGS = new Set(['--base', '--out', '--audit']);

export function parseArgs(argv) {
  const opts = { base: DEFAULT_BASE, out: null, audit: null };
  for (let i = 0; i < argv.length; i += 2) {
    const flag = argv[i];
    const value = argv[i + 1];
    if (!FLAGS.has(flag) || value === undefined) throw new Error(`unknown or incomplete flag ${flag}`);
    opts[flag.slice(2)] = flag === '--base' ? value.replace(/\/+$/, '') : value;
  }
  return opts;
}

/** The three fixture rows with their timestamps moved so the fixture's `now` is `nowMs`. */
export function fixtureRows(fixture, nowMs) {
  const shift = nowMs - Date.parse(fixture.now);
  const moved = (value) => (value == null ? value : new Date(Date.parse(value) + shift).toISOString());
  return ['worst_case', 'stale_live', 'no_price'].map((name) => {
    const row = { ...fixture.base, ...fixture.rows[name] };
    row.price_as_of = moved(row.price_as_of);
    row.price_error_at = moved(row.price_error_at);
    return row;
  });
}

export function isTradesList(url) {
  return url.pathname === '/api/v1/trades';
}

export function isMarketUpdates(url) {
  return url.pathname === '/api/v1/market/updates';
}

const HELD = new Set(['ACTIVE', 'PARTIAL']);

export function tradesBody(rows, url) {
  const wanted = (url.searchParams.get('status') ?? '').split(',').filter(Boolean).map((s) => s.toUpperCase());
  const items = wanted.length === 0 || wanted.some((s) => HELD.has(s)) ? rows : [];
  return {
    items,
    total: items.length,
    page: 1,
    per_page: Number(url.searchParams.get('per_page')) || 20,
    market_meta: { as_of: null, refreshing: false, stale_count: 1, missing_count: 1, incomplete: true, source: 'request' },
  };
}

export function marketUpdatesBody(nowMs) {
  return {
    cursor: 'v248-check',
    quotes: [],
    snapshots: [],
    status: {
      session: 'regular',
      last_close_at: new Date(nowMs - 18 * 3_600_000).toISOString(),
      stale_price_s: 120,
      stale_snapshot_s: 600,
      heartbeat: { beat_at: new Date(nowMs).toISOString(), cadence_s: 30, stalled: false },
    },
  };
}

export const EXPECTED_TEXT = Object.freeze([
  'prev close', 'at prev close', 'refresh failed', 'no price yet', 'no trade and no daily close cached',
]);

/** Every page and width shows the full copy: the Trades phone row carries the error in its P&L % cell. */
export function expectedText(_pageName, _width) {
  return EXPECTED_TEXT;
}

export function clipVerdict(items) {
  return items.filter((item) => item.clippedBy).map((item) => `${item.name} clipped by ${item.clippedBy}`);
}

export function pageOverflowVerdict(docWidth, viewportWidth) {
  return docWidth <= viewportWidth
    ? null
    : `page is ${docWidth}px wide at ${viewportWidth}: the table must scroll inside its container`;
}

export function auditVerdict(unallowed, routes = PAGES.map((p) => p.path)) {
  return unallowed.filter((f) => routes.includes(f.route))
    .map((f) => `${f.route} @${f.width} ${f.check} ${f.selector} -- ${f.detail}`);
}
