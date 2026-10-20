import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { QuoteStamp } from '../../api/models';
import { quoteLine } from './quote-line';

const stamp = (patch: Partial<QuoteStamp> = {}): QuoteStamp => ({
  at: '2026-10-15T13:00:01+00:00', kind: 'trade', age_s: 2.4, session: 'regular', confirmed: true, ...patch,
});

describe('quoteLine (v171 D2/D5)', () => {
  it('reads n/a before v171', () => {
    expect(quoteLine(null)).toBe('n/a');
    expect(quoteLine(undefined)).toBe('n/a');
  });
  it('names the kind and the time to post', () => {
    expect(quoteLine(stamp())).toBe('Live trade, 2.4 s to post');
    expect(quoteLine(stamp({ kind: 'mid', age_s: 0.8 }))).toBe('Bid/ask mid, 0.8 s to post');
    expect(quoteLine(stamp({ kind: 'yf-1m', age_s: 3 }))).toBe('Yahoo 1-min bar, 3.0 s to post');
  });
  it('adds the session outside regular hours', () => {
    expect(quoteLine(stamp({ kind: 'mid', age_s: 1.7, session: 'pre-market' })))
      .toBe('Bid/ask mid, 1.7 s to post, pre-market');
  });
  it('says the price was not confirmed live', () => {
    expect(quoteLine(stamp({ kind: 'scan', confirmed: false, session: 'pre-market' })))
      .toBe('Price not confirmed live, pre-market');
    expect(quoteLine(stamp({ kind: 'scan', confirmed: false, age_s: null }))).toBe('Price not confirmed live');
  });
  it('omits an unknown age', () => {
    expect(quoteLine(stamp({ age_s: null }))).toBe('Live trade');
  });
});

/* Source pins: jsdom does not lay these pages out; V171-33 checks them rendered. */
const src = (path: string) => readFileSync(join(process.cwd(), 'src/app', path), 'utf8');

describe('v171 page wiring', () => {
  it('dashboard live P&L carries a 15 s age hint', () => {
    const text = src('workspaces/dashboard/dashboard.ts');
    expect(text).toMatch(/<sb-age-hint \[ageS\]="row\.price_age_s \?\? null" \[windowS\]="dashboardWindowS"/);
    expect(text).toContain('DASHBOARD_PRICE_WINDOW_S');
  });
  it('watchlist price and the trade detail price tile carry a 60 s age hint', () => {
    expect(src('workspaces/watchlist/watchlist.ts')).toMatch(/<sb-age-hint \[ageS\]="row\.price_age_s \?\? null" \[windowS\]="pageWindowS"/);
    expect(src('workspaces/trades/outcome-strip.ts')).toMatch(/<sb-age-hint \[ageS\]="tile\.ageS" \[windowS\]="pageWindowS"/);
  });
  it('trade detail and plan page show the alert price line', () => {
    expect(src('workspaces/trades/trade-detail.ts')).toContain('alertPrice: quoteLine(this.store.detail()?.quote ?? null)');
    expect(src('workspaces/plans/plan-detail.ts')).toContain('Alert price: {{ quoteLine(store.detail()?.quote ?? null) }}');
  });
});
