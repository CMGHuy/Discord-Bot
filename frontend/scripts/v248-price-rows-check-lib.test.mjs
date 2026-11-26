import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  DEFAULT_BASE, EXPECTED_TEXT, FIXTURE, PAGES, VIEWPORTS,
  auditVerdict, clipVerdict, expectedText, fixtureRows, isMarketUpdates, isTradesList,
  marketUpdatesBody, pageOverflowVerdict, parseArgs, tradesBody,
} from './v248-price-rows-check-lib.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const fix = JSON.parse(readFileSync(FIXTURE, 'utf8'));

test('parseArgs defaults to the local admin and takes --out and --audit', () => {
  assert.deepEqual(parseArgs([]), { base: DEFAULT_BASE, out: null, audit: null });
  assert.deepEqual(parseArgs(['--base', 'http://localhost:4123/', '--audit', 'a.json']),
    { base: 'http://localhost:4123', out: null, audit: 'a.json' });
  assert.throws(() => parseArgs(['--widths', '390']), /unknown or incomplete flag --widths/);
});

test('checks phone, tablet and desktop on the two pages', () => {
  assert.deepEqual(VIEWPORTS.map((v) => v.width), [390, 768, 1440]);
  assert.deepEqual(PAGES.map((p) => p.path), ['/dashboard', '/trades']);
});

test('fixtureRows merges base and rows and moves the timestamps to now, keeping nulls', () => {
  const now = Date.parse(fix.now) + 3_600_000;
  const rows = fixtureRows(fix, now);
  assert.deepEqual(rows.map((r) => r.ticker), ['DOCU', 'HOOD', 'CRWV']);
  const [wc, live, none] = rows;
  assert.equal(wc.price_as_of, null);
  assert.equal(wc.price_error_at, '2026-11-25T15:59:00.000Z');
  assert.equal(live.price_as_of, '2026-11-25T15:46:00.000Z');
  assert.equal(wc.price_kind, 'prev_close');
  assert.equal('price_kind' in none, false);
  assert.equal(fix.rows.stale_live.price_as_of, '2026-11-25T14:46:00Z');   // input untouched
});

test('intercepts exactly the trades list and the market updates reads', () => {
  assert.equal(isTradesList(new URL('http://x/api/v1/trades?status=ACTIVE&page=1')), true);
  assert.equal(isTradesList(new URL('http://x/api/v1/trades/abc')), false);
  assert.equal(isTradesList(new URL('http://x/api/v1/trades/cancels')), false);
  assert.equal(isMarketUpdates(new URL('http://x/api/v1/market/updates?since=1')), true);
  assert.equal(isMarketUpdates(new URL('http://x/api/v1/market/refresh')), false);
});

test('tradesBody serves the held rows to a held or unfiltered query and nothing to the others', () => {
  const rows = fixtureRows(fix, Date.parse(fix.now));
  const body = tradesBody(rows, new URL('http://x/api/v1/trades?status=ACTIVE&per_page=12'));
  assert.equal(body.items.length, 3);
  assert.equal(body.total, 3);
  assert.equal(body.per_page, 12);
  assert.equal(body.market_meta.incomplete, true);
  assert.equal(tradesBody(rows, new URL('http://x/api/v1/trades')).items.length, 3);
  assert.equal(tradesBody(rows, new URL('http://x/api/v1/trades?status=CLOSED')).items.length, 0);
  assert.equal(tradesBody(rows, new URL('http://x/api/v1/trades?status=PENDING')).total, 0);
});

test('marketUpdatesBody is a regular session with no quotes', () => {
  const body = marketUpdatesBody(Date.parse(fix.now));
  assert.deepEqual(body.quotes, []);
  assert.equal(body.status.session, 'regular');
  assert.equal(body.status.stale_price_s, 120);
  assert.equal(body.status.heartbeat.stalled, false);
});

test('expected text is the full component copy on every page and width', () => {
  const src = readFileSync(join(HERE, '..', 'src', 'app', 'ui', 'position-format.ts'), 'utf8');
  for (const copy of ['no trade and no daily close cached', 'at prev close', 'no price yet', 'prev close'])
    assert.ok(src.includes(`'${copy}'`) && EXPECTED_TEXT.includes(copy), copy);
  assert.ok(expectedText('dashboard', 390).includes('refresh failed'));
  assert.ok(expectedText('trades', 390).includes('refresh failed'));
  assert.ok(expectedText('trades', 768).includes('refresh failed'));
});

test('verdicts name what failed and pass a clean page', () => {
  assert.deepEqual(clipVerdict([{ name: '.fig −11.82%', clippedBy: null }]), []);
  assert.deepEqual(clipVerdict([{ name: '.pp-value 1,234.56', clippedBy: 'td.cell overflow:hidden' }]),
    ['.pp-value 1,234.56 clipped by td.cell overflow:hidden']);
  assert.equal(pageOverflowVerdict(390, 390), null);
  assert.match(pageOverflowVerdict(512, 390), /page is 512px wide at 390/);
  const unallowed = [
    { route: '/trades', width: 390, check: 'clipped', selector: 'td', detail: 'x' },
    { route: '/risk', width: 390, check: 'tap', selector: 'a', detail: 'y' },
  ];
  assert.deepEqual(auditVerdict(unallowed), ['/trades @390 clipped td -- x']);
});
