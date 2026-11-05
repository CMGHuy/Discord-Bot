# v208 — Benchmark tab, part 5: the tab in three slices, production rollout

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v208 — Benchmark tab](../specs/2026-11-05-v208-benchmark-tab.md) (its *Amendment after the code brief* overrides earlier spec text)
**Index:** [2026-11-05-v208-benchmark-tab_0-index.md](2026-11-05-v208-benchmark-tab_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and the **response contract** live there; every task below implicitly includes them.

Tasks V208-15, V208-15b, V208-16..V208-18 (V208-15 passed 20 KB and was split:
helpers + fixture, then the component frame). V208-15 needs V208-13's types;
V208-15b needs V208-13 (store slice, `BENCHMARK_RANGES`) and V208-14 (chart +
exposure strip) merged; V208-16 and V208-17 extend V208-15b's component in that order; V208-18 runs after every v208 task
is merged and CI is green.

Conventions used in this part:

- **The response carries percentages** (`1.02` = +1.02 %), built by
  V208-10b. The SPA never multiplies by 100; it formats what it receives.
  Drawdowns arrive `<= 0`; `money_dd` is money; `approx_share` is a
  percentage (null on `bot_account`).
- A `reason` string is rendered **verbatim** wherever its `value` is null
  (`needs ≥ 20 sessions`, `needs ≥ 10 index-up and ≥ 10 index-down sessions`,
  `no variance`, `index flat`, `account line only`). Null renders `—`, never
  `0%`.
- `tabs/benchmark.ts` holds pure, exported shaping helpers (unit-tested) plus
  one component; it never fetches. Ledger, strategy, horizon and direction are
  never sent (V208-13 owns the params).
- **tokens.spec gate:** the component uses `sb-segmented`/plain buttons; no
  `display: flex` rule in it may also declare `align-items: center|flex-start|stretch`
  (`frontend/src/app/ui/tokens.spec.ts` "no workspace hand-rolls a control
  row"). Use grid, or flex with `flex-wrap` and `gap` only.
- Colours are tokens only (`--accent`, `--chart-2..5`); `chart-palette.spec.ts`
  and `all-sources.spec.ts` fail on a raw colour.
- Frontend runs are narrow: `node frontend/scripts/ng-test.mjs frontend --include <spec>`;
  the type check is `cd frontend && npx tsc --noEmit -p tsconfig.app.json`;
  the layout-audit lib test is `node --test frontend/scripts/layout-audit-lib.test.mjs`.

# Phase F — the Benchmark tab

### Task V208-15: Benchmark tab helpers and fixture: copy, formats, Today cells, empty states

**Model:** sonnet — pure TypeScript helpers and exact copy pinned by tests; no component or wiring yet (V208-15b).

**Files:**
- Create: `frontend/src/app/workspaces/analytics/tabs/benchmark.ts` (constants and pure helpers; V208-15b adds the component to this file)
- Create: `frontend/src/app/workspaces/analytics/tabs/benchmark.fixture.ts` (shared by V208-15b/16/17's tests, like `partials.fixture.ts`)
- Create: `frontend/src/app/workspaces/analytics/tabs/benchmark.spec.ts`

**Interfaces:**
- Consumes (V208-13): `AnalyticsBenchmark`, `BenchmarkKey`, `BenchmarkPoint`, `BenchmarkStat` from `api/models`. `MINUS` from `ui/format`.
- Produces (V208-15b/16/17 use these; names final):
  - `SERIES_ORDER: readonly BenchmarkKey[] = ['bot_account', 'bot_deployed', 'SPY', 'QQQ', '^IXIC', '^DJI']`
  - `CHIP_LABELS: Record<BenchmarkKey, string>` = `Bot · account`, `Bot · deployed`, `SPY`, `QQQ`, `Nasdaq Comp. (price)`, `Dow (price)` (in `SERIES_ORDER` order)
  - `DEFAULT_VISIBLE: readonly BenchmarkKey[] = ['bot_account', 'bot_deployed', 'SPY', 'QQQ']`; `POLL_MS = 300_000`
  - `SERIES_TOKENS: Record<BenchmarkKey, string>` = `'--accent'` for both bot keys, `'--chart-2'` SPY, `'--chart-3'` QQQ, `'--chart-4'` ^IXIC, `'--chart-5'` ^DJI (token **names**; V208-16 hands them to `<sb-line-chart>`)
  - copy: `PAPER_LINE`, `MIXED_BANNER`, `DEPLOYED_LABEL`, `UNREALISED`, `EMPTY_BARS`, `STALE_BARS` (Step 3)
  - `signedPct(v: number | null, dp = 2): string`; `etClock(iso: string): string`; `stateStamp(p: AnalyticsBenchmark): string`
  - `interface TodayCell { key: BenchmarkKey; label: string; value: string; caption: string | null }`; `todayCells(p: AnalyticsBenchmark): TodayCell[]`
  - `statusNote(p: AnalyticsBenchmark): string | null`; `isMixedCurrency(p: AnalyticsBenchmark): boolean`
  - Fixture: `BENCHMARK_FIXTURE: AnalyticsBenchmark` (session open, 5 sessions, one missing bot session, one 2-session span, one `base_balance` marker, one proxy Dow day, QQQ with a computed beta/alpha) and `benchmarkWith(over: Partial<AnalyticsBenchmark>): AnalyticsBenchmark`.

- [ ] **Step 1: Create the fixture** (`tabs/benchmark.fixture.ts`; a shape fixture — the numbers are not mutually consistent and need not be)

```ts
import { AnalyticsBenchmark, BenchmarkPoint, BenchmarkStat } from '../../../api/models';

const st = (value: number | null, n: number, reason: string | null = null): BenchmarkStat => ({ value, n, reason });
const SHORT = 'needs ≥ 20 sessions';
const CAP = 'needs ≥ 10 index-up and ≥ 10 index-down sessions';
const NO_ALPHA = { value: null, t: null, n: 3, reason: 'needs ≥ 60 sessions', headline: false };
const NO_BETA = { value: null, se: null, n: 3, reason: SHORT };
const DATES = ['2026-10-28', '2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03', '2026-11-04'];
/** One point per date; index 0 is the rebase close (0 %, no day return). */
const line = (cums: (number | null)[], extra: Record<string, Partial<BenchmarkPoint>> = {}): BenchmarkPoint[] =>
  DATES.map((date, i) => ({
    date, cum_pct: cums[i], day_pct: i === 0 || cums[i] === null ? null : (cums[i] as number) - (cums[i - 1] ?? 0),
    span: 1, missing: false, proxy: false, approx: false, clipped: false, ...extra[date],
  }));
const day = (date: string, lines: Record<string, number | null>, exposure: number | null, open: number,
             beat: boolean | null, over: { span?: number; missing?: boolean } = {}) =>
  ({ date, lines, exposure_pct: exposure, open_n: open, beat, span: over.span ?? 1, missing: over.missing ?? false });

export const BENCHMARK_FIXTURE: AnalyticsBenchmark = {
  range: { from: '2026-10-29', to: '2026-11-04', live_since: '2026-08-07', sessions_n: 5, clamped: false, is_all: false },
  as_of: '2026-11-05T15:35:00+00:00', session_state: 'open',
  account_currency: 'USD', mixed_tickers: [],
  benchmarks_status: 'ok', benchmarks_last_session: '2026-11-04',
  today: { session: '2026-11-05', final: false, lines: {
    bot_account: { pct: 0.31, final: false }, bot_deployed: { pct: 0.82, final: false },
    SPY: { pct: 1.02, final: false }, QQQ: { pct: 1.4, final: false },
    '^IXIC': { pct: null, final: false }, '^DJI': { pct: -0.55, final: false } } },
  series: [
    { key: 'bot_account', label: 'Bot · account', kind: 'bot', total_return: true,
      points: line([0, 0.4, null, 0.9, 0.7, 0.58], { '2026-10-30': { missing: true }, '2026-11-02': { span: 2 } }) },
    { key: 'bot_deployed', label: 'Bot · deployed', kind: 'bot', total_return: true,
      points: line([0, 1.1, null, 2.0, 1.6, 1.9], { '2026-10-30': { missing: true }, '2026-11-03': { approx: true } }) },
    { key: 'SPY', label: 'SPY', kind: 'index', total_return: true, points: line([0, 0.5, 0.8, 1.1, 1.0, 1.4]) },
    { key: 'QQQ', label: 'QQQ', kind: 'index', total_return: true, points: line([0, 0.7, 1.2, 1.5, 1.3, 1.8]) },
    { key: '^IXIC', label: 'Nasdaq Comp. (price)', kind: 'index', total_return: false, points: line([0, 0.6, 1.1, 1.6, 1.7, 2.1]) },
    { key: '^DJI', label: 'Dow (price)', kind: 'index', total_return: false,
      points: line([0, 0.2, 0.3, 0.6, 0.5, 0.7], { '2026-10-30': { proxy: true } }) },
  ],
  markers: [{ date: '2026-11-03', kind: 'base_balance' }],
  exposure: [
    { date: '2026-10-29', pct: 41.2, open_n: 3, approx: true }, { date: '2026-10-30', pct: null, open_n: 0, approx: false },
    { date: '2026-11-02', pct: 35.0, open_n: 2, approx: false }, { date: '2026-11-03', pct: 38.0, open_n: 2, approx: false },
    { date: '2026-11-04', pct: 38.0, open_n: 2, approx: false },
  ],
  stats: {
    bot_account: { total_pct: st(0.58, 4), max_dd_pct: st(-0.32, 4), sharpe: st(null, 3, SHORT),
                   money_dd: st(-41.5, 4), losing_streak: 2, approx_share: null },
    bot_deployed: { total_pct: st(1.9, 3), max_dd_pct: st(-0.6, 3), sharpe: st(null, 3, SHORT),
                    money_dd: st(null, 3, 'account line only'), losing_streak: 1, approx_share: 38 },
    SPY: { total_pct: st(1.4, 5), max_dd_pct: st(-0.09, 5), sharpe: st(null, 5, SHORT) },
    QQQ: { total_pct: st(1.8, 5), max_dd_pct: st(-0.2, 5), sharpe: st(null, 5, 'no variance') },
    '^IXIC': { total_pct: st(2.1, 5), max_dd_pct: st(0, 5), sharpe: st(null, 5, SHORT) },
    '^DJI': { total_pct: st(0.7, 5), max_dd_pct: st(-0.1, 5), sharpe: st(null, 5, SHORT) },
  },
  vs: {
    SPY: { lead_pp: st(-0.82, 4), beta: NO_BETA, alpha: NO_ALPHA },
    QQQ: { lead_pp: st(-1.22, 4), beta: { value: 0.42, se: 0.18, n: 61, reason: null },
           alpha: { value: 6.1, t: 0.9, n: 61, reason: null, headline: false } },
    '^IXIC': { lead_pp: st(-1.52, 4), beta: NO_BETA, alpha: NO_ALPHA },
    '^DJI': { lead_pp: st(-0.12, 4), beta: NO_BETA, alpha: NO_ALPHA },
  },
  capture: { index: 'SPY', up_pct: st(null, 2, CAP), down_pct: st(null, 1, CAP), ratio: st(null, 3, CAP),
             up_n: 2, down_n: 1, beat: { up_days: 2, up_beat: 1, down_days: 1, down_beat: 1 } },
  daily: [
    day('2026-11-04', { bot_account: -0.12, bot_deployed: 0.3, SPY: 0.4, QQQ: 0.5, '^IXIC': 0.4, '^DJI': 0.2 }, 38, 2, false),
    day('2026-11-03', { bot_account: null, bot_deployed: null, SPY: -0.1, QQQ: -0.2, '^IXIC': 0.1, '^DJI': -0.1 }, 38, 2, null),
    day('2026-11-02', { bot_account: 0.5, bot_deployed: 0.9, SPY: 0.3, QQQ: 0.3, '^IXIC': 0.5, '^DJI': 0.3 }, 35, 2, null, { span: 2 }),
    day('2026-10-30', { bot_account: null, bot_deployed: null, SPY: 0.3, QQQ: 0.5, '^IXIC': 0.5, '^DJI': 0.1 }, null, 0, null, { missing: true }),
    day('2026-10-29', { bot_account: 0.4, bot_deployed: 1.1, SPY: 0.5, QQQ: 0.7, '^IXIC': 0.6, '^DJI': 0.2 }, 41.2, 3, false),
  ],
  daily_has_more: true,
};

export const benchmarkWith = (over: Partial<AnalyticsBenchmark>): AnalyticsBenchmark => ({ ...BENCHMARK_FIXTURE, ...over });
```

- [ ] **Step 2: Write the failing helper tests** (`tabs/benchmark.spec.ts`; V208-15b appends the component tests to this file)

```ts
import { describe, expect, it } from 'vitest';

import { BENCHMARK_FIXTURE, benchmarkWith } from './benchmark.fixture';
import {
  CHIP_LABELS, PAPER_LINE, SERIES_ORDER, etClock, isMixedCurrency, signedPct, stateStamp, statusNote, todayCells,
} from './benchmark';

describe('benchmark helpers (v208)', () => {
  it('fixes the chip labels, the price indexes labelled in the label itself', () => {
    expect(SERIES_ORDER.map((k) => CHIP_LABELS[k])).toEqual(
      ['Bot · account', 'Bot · deployed', 'SPY', 'QQQ', 'Nasdaq Comp. (price)', 'Dow (price)']);
    expect(PAPER_LINE).toBe('Paper trades only. Returns are pre-tax and exclude fees and slippage; '
      + 'indexes are buy-and-hold. Not a recommendation or forecast.');
  });
  it('formats signed percentages and never turns null into 0%', () => {
    expect([signedPct(1.02), signedPct(-0.12), signedPct(0), signedPct(null), signedPct(6.1, 1)])
      .toEqual(['+1.02%', '−0.12%', '0.00%', '—', '+6.1%']);
  });
  it('stamps the time in New York on both sides of the DST change', () => {
    expect(etClock('2026-11-05T15:35:00+00:00')).toBe('10:35');
    expect(etClock('2026-10-14T19:05:00+00:00')).toBe('15:05');
  });
  it('stamps open, closed, pre-open and no-session differently', () => {
    expect(stateStamp(BENCHMARK_FIXTURE)).toBe('as of 10:35 ET');
    expect(stateStamp(benchmarkWith({ session_state: 'closed', today: { ...BENCHMARK_FIXTURE.today!, final: true } })))
      .toBe('2026-11-05 · final');
    expect(stateStamp(benchmarkWith({ session_state: 'pre', today: { session: '2026-11-04', final: true, lines: {} } })))
      .toBe('2026-11-04 · final');
    expect(stateStamp(benchmarkWith({ today: { session: null as never, final: false, lines: {} } }))).toBe('no session yet');
    expect(stateStamp(benchmarkWith({ today: null }))).toBe('no session yet');
  });
  it('gives every line a Today cell, bot cells unrealised while open, null as —', () => {
    expect(todayCells(BENCHMARK_FIXTURE).map((c) => [c.label, c.value, c.caption])).toEqual([
      ['Bot · account', '+0.31%', 'unrealised · paper'], ['Bot · deployed', '+0.82%', 'unrealised · paper'],
      ['SPY', '+1.02%', null], ['QQQ', '+1.40%', null], ['Nasdaq Comp. (price)', '—', null], ['Dow (price)', '−0.55%', null]]);
    // Open session with no live sample yet: the bot cell is —, never 0%.
    const noSample = todayCells(benchmarkWith({ today: { session: '2026-11-05', final: false,
      lines: { bot_account: { pct: null, final: false }, SPY: { pct: 0.2, final: false } } } }));
    expect(noSample.map((c) => c.value)).toEqual(['—', '+0.20%']);
    const closed = todayCells(benchmarkWith({ session_state: 'closed',
      today: { session: '2026-11-05', final: true, lines: { bot_account: { pct: 0.1, final: true } } } }));
    expect(closed).toEqual([{ key: 'bot_account', label: 'Bot · account', value: '+0.10%', caption: null }]);
    expect(todayCells(benchmarkWith({ today: null }))).toEqual([]);
  });
  it('names the two empty states, and nothing when bars are fine', () => {
    expect(statusNote(BENCHMARK_FIXTURE)).toBeNull();
    expect(statusNote(benchmarkWith({ benchmarks_status: 'empty' }))).toBe('No benchmark data yet');
    expect(statusNote(benchmarkWith({ benchmarks_status: 'stale' }))).toBe('Benchmarks not updating — refresher is off');
  });
  it('flags a non-USD account or any non-USD ticker', () => {
    expect(isMixedCurrency(BENCHMARK_FIXTURE)).toBe(false);
    expect(isMixedCurrency(benchmarkWith({ account_currency: 'EUR' }))).toBe(true);
    expect(isMixedCurrency(benchmarkWith({ mixed_tickers: ['SAP.DE'] }))).toBe(true);
  });
});
```

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/benchmark.spec.ts`
Expected: FAIL — `./benchmark` not found.

- [ ] **Step 3: Implement the helpers in `tabs/benchmark.ts`**

File header comment: v208 — the Benchmark tab; every number arrives as a percentage from the API and the tab only formats it; null is `—`, never `0%`. Exact copy:

```ts
export const PAPER_LINE = 'Paper trades only. Returns are pre-tax and exclude fees and slippage; '
  + 'indexes are buy-and-hold. Not a recommendation or forecast.';
export const MIXED_BANNER = 'Benchmark assumes a USD account trading USD stocks — figures may be mixed-currency';
export const DEPLOYED_LABEL = 'on capital in trades — not account return';
export const UNREALISED = 'unrealised · paper';
export const EMPTY_BARS = 'No benchmark data yet';
export const STALE_BARS = 'Benchmarks not updating — refresher is off';
```

Rules (each pinned above):
- `signedPct`: `null` → `'—'`; `0` → `` `${(0).toFixed(dp)}%` ``; otherwise `+` or `MINUS`, then `Math.abs(v).toFixed(dp)` and `%`.
- `etClock`: `new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(iso))`.
- `stateStamp`: no `today` or a falsy `today.session` → `'no session yet'`; `session_state === 'open' && !today.final` → `` `as of ${etClock(p.as_of)} ET` ``; else `` `${today.session} · final` ``.
- `todayCells`: `SERIES_ORDER` keys present in `today.lines` (none without `today`); `value = signedPct(line.pct)`; `caption = UNREALISED` for a bot key when `session_state === 'open' && !line.final`, else `null`.
- `statusNote`: `'empty'` → `EMPTY_BARS`, `'stale'` → `STALE_BARS`, otherwise `null`. `isMixedCurrency`: `account_currency !== 'USD' || mixed_tickers.length > 0`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/benchmark.spec.ts`, then `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: `0 failed`; the type check is clean (the fixture type-checks against V208-13's `AnalyticsBenchmark`, which is half its point).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/benchmark.ts frontend/src/app/workspaces/analytics/tabs/benchmark.fixture.ts \
  frontend/src/app/workspaces/analytics/tabs/benchmark.spec.ts
git commit -m "feat(v208): Benchmark tab helpers -- exact copy, signed %, ET stamp, Today cells, empty states"
```

### Task V208-15b: Benchmark tab frame: registration, scope-bar mode, Today card, range picker, chips, polling, banners

**Model:** sonnet — one component on existing primitives plus three small wiring edits; layout, copy, state rules and polling conditions are fixed below.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/benchmark.ts` (+ `benchmark.spec.ts`) — add the `BenchmarkTab` component below V208-15's helpers
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (+ `analytics.spec.ts`)
- Modify: `frontend/src/app/workspaces/analytics/scope-bar.ts` (+ `scope-bar.spec.ts`)
- Modify: `frontend/scripts/layout-audit-lib.mjs` (+ `layout-audit-lib.test.mjs`)

**Interfaces:**
- Consumes: V208-15's constants and helpers (`SERIES_ORDER`, `CHIP_LABELS`, `DEFAULT_VISIBLE`, `SERIES_TOKENS`, `POLL_MS`, copy constants, `stateStamp`, `todayCells`, `isMixedCurrency`) and fixture. V208-13: `AnalyticsStore` signals `benchmark()`, `benchmarkError()`, `benchmarkRange()`, `benchmarkCapture()`, `benchmarkLoadingMore()`, `scope()`, methods `setBenchmarkRange(r)`, `refreshBenchmark()`, `setScope(patch)`, `reload('benchmark')`, `setTab(tab, loadNow)`; `BENCHMARK_RANGES`, `DEFAULT_SCOPE`; `BenchmarkRange`. A scope-bar custom date (`scope().from`/`to`) overrides the preset (V208-13 sends it).
- Produces (V208-16/17 extend):
  - `BenchmarkTab` (selector `sb-benchmark-tab`): `store`, `data = computed(() => store.benchmark())`, `visible: WritableSignal<Set<string>>` (init `new Set(DEFAULT_VISIBLE)`), `toggle(key)`, `selectedRange` computed, `pickRange(r: BenchmarkRange)`, `poll()`.
  - Section classes, in order: `.banner` (optional) → `.today` → `.paper` → `.range` → `.chips` → `<!-- V208-16: .stats, .chart -->` → `<!-- V208-17: .daily, .capture, .footnote -->`.
  - Spec helpers exported from `benchmark.spec.ts`: `stubStore(payload, over?)`, `renderTab(store)`, `text(el)`.
  - `ScopeBar` input `benchmark = input(false)`; `ACCOUNT_WIDE_NOTE` exported from `scope-bar.ts`.

- [ ] **Step 1: Write the failing component tests** (append to `tabs/benchmark.spec.ts`; merge the imports into the file's import block)

```ts
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, vi } from 'vitest';
import { AnalyticsBenchmark, BookScope } from '../../../api/models';
import { AnalyticsStore, DEFAULT_SCOPE } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { BenchmarkTab, DEFAULT_VISIBLE, POLL_MS } from './benchmark';

export function stubStore(payload: AnalyticsBenchmark | null, over: Record<string, unknown> = {}) {
  return {
    benchmark: signal(payload), benchmarkError: signal<string | null>(null), benchmarkRange: signal('3M'),
    benchmarkCapture: signal('SPY'), benchmarkLoadingMore: signal(false), scope: signal<BookScope>({ ...DEFAULT_SCOPE }),
    setBenchmarkRange: vi.fn(), setBenchmarkCapture: vi.fn(), refreshBenchmark: vi.fn(),
    loadMoreBenchmarkDaily: vi.fn(), reload: vi.fn(), setScope: vi.fn(), ...over,
  };
}
export function renderTab(store: ReturnType<typeof stubStore>) {
  TestBed.configureTestingModule({ providers: [
    provideZonelessChangeDetection(), provideRouter([]),
    { provide: AnalyticsStore, useValue: store },
    { provide: ConnectionStore, useValue: { currency: signal('$') } },
    { provide: PreferencesStore, useValue: { values: () => ({}), update: () => {} } },
  ] });
  const fixture = TestBed.createComponent(BenchmarkTab);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}
export const text = (el: Element | null) => (el?.textContent ?? '').replace(/\s+/g, ' ').trim();

describe('BenchmarkTab frame (v208)', () => {
  beforeEach(() => TestBed.resetTestingModule());
  afterEach(() => vi.useRealTimers());

  it('renders the Today card, the paper line under it, then range and chips', () => {
    const { el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    const order = [...el.querySelectorAll('.today, .paper, .range, .chips')].map((n) => n.classList[0]);
    expect(order).toEqual(['today', 'paper', 'range', 'chips']);
    expect(text(el.querySelector('.today'))).toContain('as of 10:35 ET');
    expect(text(el.querySelector('.today'))).toContain('unrealised · paper');
    expect(text(el.querySelector('.paper'))).toBe(PAPER_LINE);
    expect(el.querySelector('.banner')).toBeNull();
  });
  it('shows the mixed-currency banner with its exact copy', () => {
    const { el } = renderTab(stubStore(benchmarkWith({ account_currency: 'EUR' })));
    expect(text(el.querySelector('.banner'))).toBe(
      'Benchmark assumes a USD account trading USD stocks — figures may be mixed-currency');
  });
  it('labels the chips exactly, four on by default, the deployed chip carrying its caveat', () => {
    const { el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    const chips = [...el.querySelectorAll<HTMLButtonElement>('.chips button')];
    expect(chips.map((b) => text(b.querySelector('.label')))).toEqual(SERIES_ORDER.map((k) => CHIP_LABELS[k]));
    expect(chips.filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset['key']))
      .toEqual([...DEFAULT_VISIBLE]);
    expect(text(chips[1])).toContain('on capital in trades — not account return');
    expect(chips[1].querySelector('.swatch.dashed')).not.toBeNull();
  });
  it('toggles a chip on and off', () => {
    const { fixture, el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    const dow = el.querySelector<HTMLButtonElement>('.chips button[data-key="^DJI"]')!;
    dow.click(); fixture.detectChanges();
    expect(dow.getAttribute('aria-pressed')).toBe('true');
    dow.click(); fixture.detectChanges();
    expect(dow.getAttribute('aria-pressed')).toBe('false');
  });
  it('picks a preset, and shows none selected while a custom scope date is set', () => {
    const store = stubStore(BENCHMARK_FIXTURE);
    const { fixture, el } = renderTab(store);
    expect(text(el.querySelector('.range button[aria-pressed="true"]'))).toBe('3M');
    store.scope.set({ ...DEFAULT_SCOPE, from: '2026-09-01' });
    fixture.detectChanges();
    expect(el.querySelector('.range button[aria-pressed="true"]')).toBeNull();
    fixture.componentInstance.pickRange('1M');
    expect(store.setScope).toHaveBeenCalledWith({ from: null, to: null });
    expect(store.setBenchmarkRange).toHaveBeenCalledWith('1M');
  });
  it('picks a preset without touching the scope when no custom date is set', () => {
    const store = stubStore(BENCHMARK_FIXTURE);
    renderTab(store).fixture.componentInstance.pickRange('All');
    expect(store.setScope).not.toHaveBeenCalled();
    expect(store.setBenchmarkRange).toHaveBeenCalledWith('All');
  });
  it('says when the range was clamped to the live book', () => {
    const { el } = renderTab(stubStore(benchmarkWith({ range: { ...BENCHMARK_FIXTURE.range, clamped: true } })));
    expect(text(el.querySelector('.range'))).toContain('Live book since 2026-08-07');
  });
  it('shows "No benchmark data yet" when there are no bars', () => {
    expect(text(renderTab(stubStore(benchmarkWith({ benchmarks_status: 'empty' }))).el)).toContain('No benchmark data yet');
  });
  it('shows the refresher-off note with the last stored session', () => {
    const { el } = renderTab(stubStore(benchmarkWith({ benchmarks_status: 'stale' })));
    expect(text(el.querySelector('.stale'))).toBe('Benchmarks not updating — refresher is off · last stored session 2026-11-04');
  });
  it('shows a retryable error above the last data', () => {
    const store = stubStore(BENCHMARK_FIXTURE, { benchmarkError: signal('Server error') });
    const { el } = renderTab(store);
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
    expect(el.querySelector('.today')).not.toBeNull();
  });
  it('polls every five minutes only while the session is open and the page visible', () => {
    vi.useFakeTimers();
    const store = stubStore(BENCHMARK_FIXTURE);
    const { fixture } = renderTab(store);
    vi.advanceTimersByTime(POLL_MS);
    expect(store.refreshBenchmark).toHaveBeenCalledTimes(1);
    const hidden = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    vi.advanceTimersByTime(POLL_MS);
    expect(store.refreshBenchmark).toHaveBeenCalledTimes(1);
    hidden.mockRestore();
    store.benchmark.set(benchmarkWith({ session_state: 'closed' }));
    vi.advanceTimersByTime(POLL_MS);
    expect(store.refreshBenchmark).toHaveBeenCalledTimes(1);
    store.benchmark.set(BENCHMARK_FIXTURE);
    fixture.destroy();
    vi.advanceTimersByTime(POLL_MS);
    expect(store.refreshBenchmark).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Write the failing shell, scope-bar and audit tests**

`analytics.spec.ts`: `'renders the seven tabs and puts the scope in the URL'` becomes "eight tabs", with `'Benchmark'` appended to both its `toContain` loop and the `tabLabels` list. Add:

```ts
  it('mounts the Benchmark tab and puts the scope bar in benchmark mode', () => {
    const { fixture } = create();
    TestBed.inject(AnalyticsStore).setTab('benchmark', false);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-benchmark-tab')).not.toBeNull();
    expect(el.querySelector('sb-scope-bar')!.textContent)
      .toContain('Equity is account-wide: ledger, strategy, horizon and direction filters do not apply.');
  });
```

`scope-bar.spec.ts` (import `ACCOUNT_WIDE_NOTE`; `create` already accepts input overrides):

```ts
  it('collapses to the date range plus the account-wide note in benchmark mode', () => {
    const { fixture, el } = create({ benchmark: true,
      scope: { ...DEFAULT_SCOPE, from: '2026-09-01', ledger: 'weak', strategy: 'MACD' } });
    expect(el.querySelector('sb-date-range')).not.toBeNull();
    expect(el.querySelector('sb-select')).toBeNull();
    expect(el.querySelector('sb-segmented')).toBeNull();
    expect(el.textContent).not.toContain('N=312');
    expect(el.querySelector('[role="note"].account-wide')!.textContent!.trim()).toBe(ACCOUNT_WIDE_NOTE);
    expect(ACCOUNT_WIDE_NOTE).toBe('Equity is account-wide: ledger, strategy, horizon and direction filters do not apply.');
    // Only the date counts as an active filter: ledger and strategy do not apply on this tab.
    expect((fixture.componentInstance as unknown as { activeCount(): number }).activeCount()).toBe(1);
  });
```

`layout-audit-lib.test.mjs`: the title's `(29)` → `(30)`, `assert.equal(ROUTES.length, 30)`, and `'benchmark'` appended to the tab list in the loop.

- [ ] **Step 3: Run them to see them fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/benchmark.spec.ts` (then `.../analytics/analytics.spec.ts` and `.../analytics/scope-bar.spec.ts`) and `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: `BenchmarkTab` not exported; no `Benchmark` tab label; `benchmark` is not a `ScopeBar` input; ROUTES length 29.

- [ ] **Step 4: Implement `BenchmarkTab` in `tabs/benchmark.ts`**

Standalone, `OnPush`, imports `Segmented`, `PanelError`, `EmptyStateComponent` (V208-16/17 add theirs). Template, top to bottom:

1. `@if (store.benchmarkError(); as error) { <sb-panel-error [message]="error" (retry)="store.reload('benchmark')" /> }` — above the data, so a failed poll keeps the last payload on screen.
2. `@if (data(); as p) {`
   - `@if (mixed()) { <p class="banner" role="status">{{ mixedBanner }}</p> }`
   - `<section class="today" aria-label="Today">`: a `<header>` with `<h2>Today</h2>` and `<span class="stamp">{{ stamp() }}</span>`, then `<div class="cells">` with one `<div class="cell" [attr.data-key]="c.key">` per `TodayCell`: `<span class="label">`, `<span class="value num">` (class `pos`/`neg` from the sign of `p.today.lines[c.key].pct`; none for null or 0), and `@if (c.caption) { <span class="caption">{{ c.caption }}</span> }`.
   - `<p class="paper">{{ paperLine }}</p>`
   - `<div class="range"><sb-segmented label="Range" [options]="rangeOptions" [value]="selectedRange()" (valueChange)="pickRange($any($event))" />@if (p.range.clamped) { <span class="clamp">Live book since {{ p.range.live_since }}</span> }</div>`
   - `<div class="chips" role="group" aria-label="Lines">`: per `SERIES_ORDER` key, `<button type="button" [attr.data-key]="key" [attr.aria-pressed]="visible().has(key)" (click)="toggle(key)">` holding `<i class="swatch" [class.dashed]="key === 'bot_deployed'" [style.border-top-color]="'var(' + tokens[key] + ')'"></i><span class="label">{{ labels[key] }}</span>` and, for `bot_deployed`, `<span class="sub">{{ deployedLabel }}</span>`.
   - `@if (p.benchmarks_status === 'empty') { <sb-empty-state [title]="emptyBars" reason="measured-zero" hint="Index bars arrive after the refresher's first cycle." /> }`; `@if (p.benchmarks_status === 'stale') { <p class="stale" role="status">{{ staleBars }} · last stored session {{ p.benchmarks_last_session }}</p> }` (stale keeps the rest of the tab; the index lines run up to the last stored session).
   - `<!-- V208-16: .stats, .chart -->` and `<!-- V208-17: .daily, .capture, .footnote -->`
3. `}` — no payload and no error renders nothing.

Members: `store = inject(AnalyticsStore)`; `router = inject(Router)`; `data`; `visible = signal(new Set<string>(DEFAULT_VISIBLE))`; `toggle(key)` sets a **new** `Set` (signals compare by reference); `rangeOptions = BENCHMARK_RANGES.map((r) => ({ value: r, label: r }))`; `selectedRange = computed(() => (this.store.scope().from || this.store.scope().to ? '' : this.store.benchmarkRange()))`; `pickRange(r)`: when a custom date is set, first `store.setScope({ from: null, to: null })` and `router.navigate([], { queryParams: { from: null, to: null }, queryParamsHandling: 'merge', replaceUrl: true })`; then `store.setBenchmarkRange(r)`. `mixed`, `stamp`, `cells` are computeds over V208-15's helpers; `labels = CHIP_LABELS`, `tokens = SERIES_TOKENS`, plus the copy constants as fields.

Polling, in the constructor: `const timer = setInterval(() => this.poll(), POLL_MS); inject(DestroyRef).onDestroy(() => clearInterval(timer));`. `poll()` calls `store.refreshBenchmark()` only when `this.data()?.session_state === 'open' && document.visibilityState === 'visible'`.

Styles (tokens only; **no `align-items` on any flex rule**): `:host{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--space-14)}`; `.today .cells{display:grid;grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr));gap:var(--space-10)}`; `.cell{display:grid;gap:2px}`; `.chips{display:flex;flex-wrap:wrap;gap:var(--space-6)}`; `.chips button{min-height:44px;padding:0 var(--space-10);border:1px solid var(--border);border-radius:var(--panel-radius);background:var(--surface);color:var(--text-secondary);text-align:left}`; `.chips button[aria-pressed="true"]{border-color:var(--accent);color:var(--text)}`; `.swatch{display:inline-block;width:14px;border-top:2px solid;margin-right:var(--space-6);vertical-align:middle}`; `.swatch.dashed{border-top-style:dashed}`; `.sub,.caption,.clamp,.stamp{font-size:var(--text-micro);color:var(--text-faint)}`; `.sub{display:block}`; `.paper{margin:0;font-size:var(--text-chip);color:var(--text-secondary)}`; `.banner,.stale{margin:0;font-size:var(--text-chip);color:var(--warn)}`; `.range{display:grid;gap:var(--space-6)}`; positive/negative value colours from the tone tokens `ui/stat-tile.ts` uses; `@media (max-width:639px){.today .cells{grid-template-columns:repeat(2,minmax(0,1fr))}}`.

- [ ] **Step 5: Wire the shell, the scope bar and the audit**

- `analytics.ts`: import `BenchmarkTab` and add it to `imports`; append `{ id: 'benchmark', label: 'Benchmark' }` to `tabs`; add `@case ('benchmark') { <sb-benchmark-tab /> }`; bind `[benchmark]="store.tab() === 'benchmark'"` on `<sb-scope-bar>`; doc comment "eight tabs … v142 adds Partials, v208 Benchmark last".
- `scope-bar.ts`: `export const ACCOUNT_WIDE_NOTE = 'Equity is account-wide: ledger, strategy, horizon and direction filters do not apply.'`; `readonly benchmark = input(false)` (doc: v208, equity is account-wide, only the dates apply). `filters` container: `@if (benchmark()) { <sb-date-range [from]="scope().from" [to]="scope().to" (changed)="scopeChange.emit($event)" /> } @else if (!tuning()) { …unchanged… }`. `.scope-line`: `@if (benchmark()) { <span class="account-wide" role="note">{{ accountWideNote }}</span> } @else { <sb-segmented …unit… /> @if (!tuning()) { …unchanged… } }`. `activeCount`: in benchmark mode, count only `from` and `to`. Style `.account-wide { font-size: var(--text-chip); color: var(--text-secondary); min-width: 0; overflow-wrap: anywhere; }`.
- `layout-audit-lib.mjs`: `'/insights/analytics?tab=benchmark'` right after `'/insights/analytics?tab=partials'`; the comment's `(29)` → `(30)`.

- [ ] **Step 6: Run the specs to see them pass**

Run each, expecting `0 failed`:
- `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/benchmark.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/analytics.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/scope-bar.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/tokens.spec.ts` (control-row gate, raw colours)
- `node --test frontend/scripts/layout-audit-lib.test.mjs`
- `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/benchmark.ts frontend/src/app/workspaces/analytics/tabs/benchmark.spec.ts \
  frontend/src/app/workspaces/analytics/analytics.ts frontend/src/app/workspaces/analytics/analytics.spec.ts \
  frontend/src/app/workspaces/analytics/scope-bar.ts frontend/src/app/workspaces/analytics/scope-bar.spec.ts \
  frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs
git commit -m "feat(v208): Benchmark tab frame -- Today card, range, chips, polling, banners, scope-bar mode"
```

### Task V208-16: Benchmark tab: stat strip + chart + exposure band + markers

**Model:** sonnet — shaping a fixed response into tiles and chart series on V208-14's primitives; the labels, guards and headline rule are spelled out below.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/benchmark.ts` (+ `benchmark.spec.ts`)
- Modify: `frontend/src/app/ui/line-chart.ts` (+ `line-chart.spec.ts`) — one additive input, `zeroLine`. The existing `referenceLine` is rendered through `@if (referenceLine(); as ref)`, which drops `0`; changing that would start drawing a line on the Overview and Edge charts that pass `0` today, so the spec's "Overview unchanged" rule forbids it.

**Interfaces:**
- Consumes: V208-15/15b (`SERIES_ORDER`, `CHIP_LABELS`, `SERIES_TOKENS`, `DEPLOYED_LABEL`, `signedPct`, `BenchmarkTab.visible`, the spec's `stubStore`/`renderTab`/`text`, `BENCHMARK_FIXTURE`/`benchmarkWith`). V208-14: `LineChart` (`series`, `valueFormat`, `hoverDetail`), `LineChartSeries { name; points: { date; value: number | null; day?: number | null; flag?: string }[]; color?; dashed? }`, `ExposureStrip` (`dates`, `bars`). `StatTile` (`label`, `value`, `sample`, `tone`, `hint`, `secondary`), `StatTone`, `Panel`, `PanelHeader`. `ConnectionStore.currency()`.
- Produces:
  - `interface BenchmarkTile { label: string; value: string; sample: number | null; hint: string; secondary: string | null; tone: StatTone; bold: boolean }`
  - `interface BenchmarkStatGroup { key: BenchmarkKey; label: string; note: string | null; tiles: BenchmarkTile[] }`
  - `statGroups(p: AnalyticsBenchmark, visible: ReadonlySet<string>, currency: string): BenchmarkStatGroup[]`; component `statTiles = computed(() => statGroups(...))`
  - `pointFlag(pt: BenchmarkPoint): string | undefined`; `chartSeries(p, visible): LineChartSeries[]`; `chartDates(series: LineChartSeries[]): string[]`; `markerNotes(p): string[]`; `stripLine(p): string`
  - `ALPHA_CELLS_HINT = '1 of 24 cells'`; `LineChart` input `zeroLine = input(false)`.

Tile rules (all values arrive as percentages or money; a null value shows `—` and its `reason` **verbatim** in `secondary`; every tile's `sample` is its stat's `n`):

| Group | Tile label | Value | Tone |
|---|---|---|---|
| bot keys | `Total` | `signedPct(total_pct)` | sign |
| bot keys | `Max drawdown` | `signedPct(max_dd_pct)` | `neg` when < 0 |
| bot keys | `Drawdown (<currency>)` | `money(money_dd)`: `−$41.50` | `neg` when < 0 |
| bot keys | `Losing streak` | `<losing_streak> sessions` (sample = `total_pct.n`) | neutral |
| bot keys, every index | `Sharpe (rf = 0)` | `value.toFixed(2)` | neutral |
| every index | `Total`, `Max drawdown` | as above | as above |
| every index | `Lead vs <chip label>` | `vs.lead_pp`: `+1.20 pp` / `−0.82 pp` | sign |
| every index | `Beta` | `β 0.42 ± 0.18` (`se` omitted when null) | neutral |
| every index | `Alpha (rf = 0)` | `α +6.1% (t 0.9)` (`signedPct(v, 1)`, `t` 1 dp) | neutral; `bold = alpha.headline` |

Group `label` = `CHIP_LABELS[key]`; `note` = `DEPLOYED_LABEL` plus `` ` · ${approx_share.toFixed(0)}% approx.` `` when `approx_share` is a number (bot_deployed), `'total return'` for SPY/QQQ, `'price only'` for ^IXIC/^DJI, `null` for bot_account. Groups follow `SERIES_ORDER`, only for visible keys present in `stats`. Hints: Sharpe `Annualised (252), rf = 0, sample std.`; Lead `Bot · account total minus this index's total; descriptive, not evidence of edge.`; Beta `OLS slope of Bot · account daily returns on this index, ± standard error.`; Alpha (headline) `Headline cell: SPY over the whole live book. Annualised Jensen alpha, rf = 0; indicative, not evidence of edge.`; Alpha (other) `` `${ALPHA_CELLS_HINT}: annualised Jensen alpha, rf = 0; indicative, not evidence of edge.` ``; Max drawdown `Largest peak-to-trough fall of the cumulative line.`; Total `Compounded over the sessions used (N).`.

- [ ] **Step 1: Write the failing tests** (append to `tabs/benchmark.spec.ts`, merging imports: `statGroups`, `chartSeries`, `chartDates`, `pointFlag`, `markerNotes`, `stripLine`, `ALPHA_CELLS_HINT` from `./benchmark`)

```ts
describe('benchmark stat strip (v208)', () => {
  const ALL = new Set(['bot_account', 'bot_deployed', 'SPY', 'QQQ']);
  const groups = statGroups(BENCHMARK_FIXTURE, ALL, '$');
  const tile = (key: string, label: string) => groups.find((g) => g.key === key)!.tiles.find((t) => t.label === label)!;

  it('builds one group per visible line, in chip order, with its caveat', () => {
    expect(groups.map((g) => [g.label, g.note])).toEqual([
      ['Bot · account', null], ['Bot · deployed', 'on capital in trades — not account return · 38% approx.'],
      ['SPY', 'total return'], ['QQQ', 'total return']]);
    expect(statGroups(BENCHMARK_FIXTURE, new Set(['^DJI']), '$').map((g) => [g.label, g.note]))
      .toEqual([['Dow (price)', 'price only']]);
  });
  it('formats every tile with its N, drawdowns negative, money in the account symbol', () => {
    expect([tile('bot_account', 'Total').value, tile('bot_account', 'Total').sample, tile('bot_account', 'Total').tone])
      .toEqual(['+0.58%', 4, 'pos']);
    expect(tile('bot_account', 'Max drawdown').value).toBe('−0.32%');
    expect(tile('bot_account', 'Drawdown ($)').value).toBe('−$41.50');
    expect(tile('bot_account', 'Losing streak').value).toBe('2 sessions');
    expect(tile('SPY', 'Lead vs SPY').value).toBe('−0.82 pp');
  });
  it('shows — and the reason verbatim below every guard, never 0', () => {
    expect([tile('bot_account', 'Sharpe (rf = 0)').value, tile('bot_account', 'Sharpe (rf = 0)').secondary])
      .toEqual(['—', 'needs ≥ 20 sessions']);
    expect(tile('QQQ', 'Sharpe (rf = 0)').secondary).toBe('no variance');
    expect([tile('bot_deployed', 'Drawdown ($)').value, tile('bot_deployed', 'Drawdown ($)').secondary])
      .toEqual(['—', 'account line only']);
    expect([tile('SPY', 'Alpha (rf = 0)').value, tile('SPY', 'Alpha (rf = 0)').secondary])
      .toEqual(['—', 'needs ≥ 60 sessions']);
  });
  it('gives beta its SE and alpha its t-stat, plain with "1 of 24 cells" unless it is the headline', () => {
    expect(tile('QQQ', 'Beta').value).toBe('β 0.42 ± 0.18');
    const alpha = tile('QQQ', 'Alpha (rf = 0)');
    expect([alpha.value, alpha.bold, alpha.sample]).toEqual(['α +6.1% (t 0.9)', false, 61]);
    expect(alpha.hint).toContain(ALPHA_CELLS_HINT);
    expect(ALPHA_CELLS_HINT).toBe('1 of 24 cells');
    const headline = statGroups(benchmarkWith({ vs: { ...BENCHMARK_FIXTURE.vs, SPY: { ...BENCHMARK_FIXTURE.vs.SPY!,
      alpha: { value: 4.2, t: 1.1, n: 80, reason: null, headline: true } } } }), ALL, '$');
    const spyAlpha = headline.find((g) => g.key === 'SPY')!.tiles.find((t) => t.label === 'Alpha (rf = 0)')!;
    expect([spyAlpha.value, spyAlpha.bold]).toEqual(['α +4.2% (t 1.1)', true]);
    expect(spyAlpha.hint).not.toContain(ALPHA_CELLS_HINT);
  });
  it('says how many sessions and that beta/alpha are not evidence of edge', () => {
    expect(stripLine(BENCHMARK_FIXTURE)).toBe('5 sessions, paper book — beta/alpha are indicative, not evidence of edge.');
  });
});

describe('benchmark chart (v208)', () => {
  it('draws only the visible lines, tokens and dash from the line, a missing session as a gap', () => {
    const series = chartSeries(BENCHMARK_FIXTURE, new Set(['bot_account', 'bot_deployed', 'SPY']));
    expect(series.map((s) => [s.name, s.color, !!s.dashed])).toEqual([
      ['Bot · account', '--accent', false], ['Bot · deployed', '--accent', true], ['SPY', '--chart-2', false]]);
    const acct = series[0].points;
    expect(acct[0]).toEqual({ date: '2026-10-28', value: 0, day: null, flag: undefined });
    expect(acct[2].value).toBeNull();
    expect(acct[2].flag).toBe('missing session');
    expect(acct[3].flag).toBe('covers 2 sessions');
  });
  it('flags proxy, approximate exposure and clipped days in the tooltip', () => {
    const base = BENCHMARK_FIXTURE.series[0].points[1];
    expect(pointFlag({ ...base, proxy: true })).toBe('proxy ETF');
    expect(pointFlag({ ...base, approx: true, clipped: true })).toBe('exposure approximate · clipped at −100%');
    expect(pointFlag(base)).toBeUndefined();
  });
  it('gives the exposure strip the chart’s own sorted, de-duplicated dates', () => {
    const dates = chartDates(chartSeries(BENCHMARK_FIXTURE, new Set(['SPY', 'QQQ'])));
    expect(dates).toEqual(['2026-10-28', '2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03', '2026-11-04']);
    expect(chartDates([])).toEqual([]);
  });
  it('names each base_balance break under the chart', () => {
    expect(markerNotes(BENCHMARK_FIXTURE)).toEqual([
      'Base balance changed on 2026-11-03: that session is left out of every stat and the account line carries flat.']);
  });
});

describe('BenchmarkTab strip and chart (v208)', () => {
  beforeEach(() => TestBed.resetTestingModule());
  it('puts the strip and the chart after the chips, the headline alpha bold', () => {
    const { el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    const order = [...el.querySelectorAll('.today, .range, .chips, .stats, .chart')].map((n) => n.classList[0]);
    expect(order).toEqual(['today', 'range', 'chips', 'stats', 'chart']);
    expect(text(el.querySelector('.stats .strip-line'))).toContain('not evidence of edge');
    expect(el.querySelectorAll('.chart sb-line-chart')).toHaveLength(1);
    expect(el.querySelector('.chart sb-exposure-strip')).not.toBeNull();
    expect(text(el.querySelector('.chart .markers'))).toContain('2026-11-03');
  });
  it('follows the chips: hiding SPY drops its stat group and its line', () => {
    const { fixture, el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    el.querySelector<HTMLButtonElement>('.chips button[data-key="SPY"]')!.click();
    fixture.detectChanges();
    expect([...el.querySelectorAll('.stats .group h3')].map((h) => text(h))).not.toContain('SPY');
    expect(fixture.componentInstance.chart().map((s) => s.name)).not.toContain('SPY');
  });
  it('renders no strip or chart when there are no bars', () => {
    const { el } = renderTab(stubStore(benchmarkWith({ benchmarks_status: 'empty' })));
    expect(el.querySelector('.stats')).toBeNull();
    expect(el.querySelector('.chart')).toBeNull();
  });
});
```

`line-chart.spec.ts`, inside `'LineChart v208 options'`:

```ts
  it('draws a 0 baseline only when zeroLine is set', () => {
    const off = render([{ name: 'a', points: [{ date: '2026-01-01', value: -1 }, { date: '2026-01-02', value: 2 }] }]);
    expect(off.nativeElement.querySelector('line.zero')).toBeNull();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const on = TestBed.createComponent(LineChart);
    on.componentRef.setInput('series', [{ name: 'a', points: [{ date: '2026-01-01', value: -1 }, { date: '2026-01-02', value: 2 }] }]);
    on.componentRef.setInput('zeroLine', true);
    on.detectChanges();
    expect(on.nativeElement.querySelector('line.zero')).not.toBeNull();
  });
```

- [ ] **Step 2: Run them to see them fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/benchmark.spec.ts` and `... --include src/app/ui/line-chart.spec.ts`
Expected: `statGroups` (and the others) not exported; `zeroLine` is not an input.

- [ ] **Step 3: Implement**

`line-chart.ts`: `readonly zeroLine = input(false);` (doc: v208, a 0 baseline; independent of `referenceLine`, so no existing chart changes). Template, beside the reference line: `@if (zeroLine()) { <line class="zero" [attr.x1]="0" [attr.x2]="600" [attr.y1]="refY(0)" [attr.y2]="refY(0)" /> }`; style `line.zero { stroke: var(--text-faint); stroke-width: 1; vector-effect: non-scaling-stroke; }`.

`benchmark.ts` helpers, by the table and copy above:
- `money(v, currency)`: `—` for null; sign (`MINUS` or none for ≥ 0) + `currency` + `Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })`.
- `pointFlag`: join with `' · '`, in this order, the parts that apply: `missing` → `'missing session'`; `span > 1` → `` `covers ${span} sessions` ``; `proxy` → `'proxy ETF'`; `approx` → `'exposure approximate'`; `clipped` → `'clipped at −100%'`; none → `undefined`.
- `chartSeries`: `p.series` in `SERIES_ORDER` order, visible keys only; `name = CHIP_LABELS[key]`, `color = SERIES_TOKENS[key]`, `dashed = key === 'bot_deployed'` (omit the field otherwise), points `{ date, value: pt.missing ? null : pt.cum_pct, day: pt.day_pct, flag: pointFlag(pt) }`.
- `chartDates`: sorted unique dates over all points (the dates the chart's own x scale spans, so the strip's bars sit under the right points).
- `markerNotes`: one sentence per marker, the copy in the test.
- `stripLine`: `` `${p.range.sessions_n} sessions, paper book — beta/alpha are indicative, not evidence of edge.` ``.
- `statGroups`: one small builder per group kind (`botTiles`, `indexTiles`) so each stays under complexity 15; `tile(label, stat, fmt, hint, tone?)` maps a `BenchmarkStat` to a tile (null value → `—` + `secondary = reason`).

Component: imports `LineChart`, `ExposureStrip`, `StatTile`, `Panel`, `PanelHeader`; `connection = inject(ConnectionStore)`; computeds `statTiles = computed(() => { const p = this.data(); return p ? statGroups(p, this.visible(), this.connection.currency()) : []; })`, `chart = computed(() => …chartSeries…)`, `dates = computed(() => chartDates(this.chart()))`, `bars = computed(() => (this.data()?.exposure ?? []).map(({ date, pct, approx }) => ({ date, pct, approx })))`. Replace the `<!-- V208-16 -->` comment with, when `p.benchmarks_status !== 'empty'`:

```html
<section class="stats" aria-label="Range statistics">
  @for (g of statTiles(); track g.key) {
    <div class="group">
      <h3>{{ g.label }} @if (g.note) { <span class="note">{{ g.note }}</span> }</h3>
      <div class="tiles">@for (t of g.tiles; track t.label) {
        <div class="tile" [class.bold]="t.bold">
          <sb-stat-tile [label]="t.label" [value]="t.value" [sample]="t.sample" [tone]="t.tone" [hint]="t.hint" [secondary]="t.secondary" />
        </div>
      }</div>
    </div>
  }
  <p class="strip-line">{{ stripLine(p) }}</p>
</section>
<sb-panel class="chart">
  <sb-panel-header title="Cumulative return" [n]="p.range.sessions_n"
    hint="Every line rebased to 0% at the close before the range starts. SPY and QQQ are total return; Nasdaq Comp. and Dow are price only. Tap or hover for each line's cumulative and day %." />
  <sb-line-chart [series]="chart()" [valueFormat]="pctFmt" [hoverDetail]="true" [zeroLine]="true" />
  <sb-exposure-strip [dates]="dates()" [bars]="bars()" />
  <p class="exposure-caption">Exposure: share of equity in open trades per session (faded bars: approximate).</p>
  @if (markerNotes(p).length) { <ul class="markers">@for (m of markerNotes(p); track m) { <li>{{ m }}</li> }</ul> }
</sb-panel>
<!-- V208-17: .daily, .capture, .footnote -->
```

(`pctFmt = (v: number) => signedPct(v)`; `stripLine`/`markerNotes` exposed as fields.) Styles: `.stats{display:grid;gap:var(--space-10)}`; `.group h3{margin:0;font-size:var(--text-chip);color:var(--text)}`; `.note{font-weight:normal;color:var(--text-faint);margin-left:var(--space-6)}`; `.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:var(--space-10)}`; `.tile.bold{outline:1px solid var(--accent);border-radius:var(--panel-radius);font-weight:600}`; `.strip-line,.exposure-caption,.markers{margin:0;font-size:var(--text-micro);color:var(--text-faint)}`; `.markers{padding-left:var(--space-14)}`; add `.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}` inside the existing `@media (max-width:639px)` block.

- [ ] **Step 4: Run the specs to see them pass**

Run each, expecting `0 failed`:
- `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/benchmark.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/line-chart.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/overview.spec.ts` (Overview unchanged)
- `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/tokens.spec.ts`, `... --include src/app/ui/chart-palette.spec.ts`, `... --include src/app/ui/all-sources.spec.ts`
- `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/benchmark.ts frontend/src/app/workspaces/analytics/tabs/benchmark.spec.ts \
  frontend/src/app/ui/line-chart.ts frontend/src/app/ui/line-chart.spec.ts
git commit -m "feat(v208): Benchmark stat strip, % chart with exposure band and base_balance markers"
```

### Task V208-17: Benchmark tab: daily table, up/down capture, footnote, three-width layout

**Model:** sonnet — a declared `sb-data-table`, one capture panel and fixed copy, then the layout audit at three widths; every rule is pinned below.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/benchmark.ts` (+ `benchmark.spec.ts`)

**Interfaces:**
- Consumes: V208-15/15b/16 (`SERIES_ORDER`, `CHIP_LABELS`, `signedPct`, `BenchmarkTile`, `BenchmarkTab.visible`, the spec's `stubStore`/`renderTab`/`text`, the fixture). V208-13: `store.benchmarkCapture()`, `setBenchmarkCapture(symbol)`, `loadMoreBenchmarkDaily()`, `benchmarkLoadingMore()`; `BenchmarkDailyRow`, `BenchmarkIndexKey`. `DataTable` (`rows`, `columns`, `visible`, `rowKey`, `clientPaging`, `emptyState`) and `ColumnDef<T>` (`key`, `header`, `value`, `numeric`) from `ui/data-table`; `Segmented`, `StatTile`.
- Produces:
  - `INDEX_KEYS: readonly BenchmarkIndexKey[] = ['SPY', 'QQQ', '^IXIC', '^DJI']`
  - `dailyColumns(capture: string): ColumnDef<BenchmarkDailyRow>[]`; `dailyVisible(visible: ReadonlySet<string>): string[]`
  - `captureTiles(p: AnalyticsBenchmark): BenchmarkTile[]`; `beatLine(p: AnalyticsBenchmark): string`
  - `CAPTURE_FORMULA`, `DOWN_FORMULA`, `TAX_LINE`, `FOOTNOTE: readonly string[]`; table id `'analytics.benchmark.daily'`

Daily table rules (the server already sends percentages, newest first, `null` where a value is missing or excluded):
- Columns, in order: `date` (header `Date`; value `2026-11-02 · covers 2 sessions` when `span > 1`, `2026-10-30 · no bot sample` when `missing`, else the date) — the first column, so `sb-data-table` makes it the sticky pin on phone; one numeric column per series key (header `CHIP_LABELS[key]`, value `signedPct(row.lines[key] ?? null)`); `exposure` (header `Exposure`, `41.2%` 1 dp, `—` for null); `open` (header `Open`, `open_n ?? '—'`); `beat` (header `` `Beat? (vs ${CHIP_LABELS[capture]})` ``, `Yes` / `No` / `—`).
- `dailyVisible`: `date`, the visible series keys in `SERIES_ORDER`, then `exposure`, `open`, `beat`.
- No `compact` slots: the spec wants the full row scrolling sideways on phone with the date pinned, which `sb-data-table` does for a table without compact columns. Client paging (`clientPaging="analytics.benchmark.daily"`) gives the house per-page choice (10 desktop, 5 tablet/phone). Under the table, when `daily_has_more`, a `<button type="button" class="more">Load older sessions</button>` (≥ 44 px, `disabled` while `benchmarkLoadingMore()`) calls `store.loadMoreBenchmarkDaily()`.

Capture rules: segmented `Capture vs` over `INDEX_KEYS` labelled by `CHIP_LABELS`, value `store.benchmarkCapture()`, change → `store.setBenchmarkCapture(key)`. Tiles `Up capture` (`up_pct`, 1 dp, `85.2%`, sample `up_n`, hint `CAPTURE_FORMULA`), `Down capture` (`down_pct`, sample `down_n`, hint `DOWN_FORMULA`), `Capture ratio` (`ratio`, 2 dp + `×`, sample `up_n + down_n`, hint `Up capture ÷ down capture.`). Null → `—` with the reason verbatim in `secondary`.

Exact copy:

```ts
export const CAPTURE_FORMULA = 'Σ bot return on index-up days ÷ Σ index return on those days (sum ratio, not the geometric form)';
export const DOWN_FORMULA = 'Σ bot return on index-down days ÷ Σ index return on those days (sum ratio, not the geometric form); flat days excluded';
export const TAX_LINE = 'Swing turnover is taxed as short-term gains, so after-tax results would differ from this chart.';
export const FOOTNOTE: readonly string[] = [
  'SPY and QQQ are total return (dividends reinvested); Nasdaq Comp. and Dow are price indexes without dividends.',
  'Bot · account is the main-ledger paper equity, cash included: the Dashboard’s daily close. '
    + 'Bot · deployed is trade P&L on capital in trades — not account return.',
  'A missing bot session shows —, never 0%: the index is compounded over the same span and the pair is left out of '
    + 'beta, alpha, Sharpe, capture and Beat?.',
  'Days sourced from a proxy ETF (ONEQ, DIA) are marked in the chart tooltip.',
  TAX_LINE,
];
```

`beatLine`: `` `Bot · account beat ${label} on ${up_beat} of ${up_days} up days and ${down_beat} of ${down_days} down days — descriptive, not evidence of edge.` `` with `label = CHIP_LABELS[capture.index]`.

- [ ] **Step 1: Write the failing tests** (append to `tabs/benchmark.spec.ts`; merge imports: `dailyColumns`, `dailyVisible`, `captureTiles`, `beatLine`, `CAPTURE_FORMULA`, `TAX_LINE`, `FOOTNOTE` from `./benchmark`)

```ts
describe('benchmark daily table and capture (v208)', () => {
  const cols = dailyColumns('SPY');
  const cell = (key: string, i: number) => cols.find((c) => c.key === key)!.value!(BENCHMARK_FIXTURE.daily[i]);

  it('shows a missing session as — and a spanning row as covering N sessions', () => {
    expect([cell('date', 0), cell('bot_account', 0), cell('SPY', 0), cell('exposure', 0), cell('open', 0), cell('beat', 0)])
      .toEqual(['2026-11-04', '−0.12%', '+0.40%', '38.0%', 2, 'No']);
    expect([cell('date', 3), cell('bot_account', 3), cell('SPY', 3), cell('exposure', 3), cell('beat', 3)])
      .toEqual(['2026-10-30 · no bot sample', '—', '+0.30%', '—', '—']);
    expect([cell('date', 2), cell('beat', 2)]).toEqual(['2026-11-02 · covers 2 sessions', '—']);
    expect(cell('bot_deployed', 1)).toBe('—');
  });
  it('names the Beat? column after the capture index and follows the chips', () => {
    expect(cols.find((c) => c.key === 'beat')!.header).toBe('Beat? (vs SPY)');
    expect(dailyColumns('^DJI').find((c) => c.key === 'beat')!.header).toBe('Beat? (vs Dow (price))');
    expect(cols[0].key).toBe('date');
    expect(dailyVisible(new Set(['bot_account', 'SPY']))).toEqual(['date', 'bot_account', 'SPY', 'exposure', 'open', 'beat']);
  });
  it('shows capture as — with the 10+10 reason below the guard, and the formula in the tooltip', () => {
    const [up, down, ratio] = captureTiles(BENCHMARK_FIXTURE);
    expect([up.label, up.value, up.sample, up.secondary]).toEqual(
      ['Up capture', '—', 2, 'needs ≥ 10 index-up and ≥ 10 index-down sessions']);
    expect(up.hint).toBe(CAPTURE_FORMULA);
    expect(CAPTURE_FORMULA).toBe('Σ bot return on index-up days ÷ Σ index return on those days (sum ratio, not the geometric form)');
    expect([down.sample, ratio.sample]).toEqual([1, 3]);
  });
  it('formats computed capture and keeps "index flat" verbatim', () => {
    const p = benchmarkWith({ capture: { ...BENCHMARK_FIXTURE.capture,
      up_pct: { value: 85.24, n: 12, reason: null }, down_pct: { value: 61.0, n: 11, reason: null },
      ratio: { value: 1.3974, n: 23, reason: null } } });
    expect(captureTiles(p).map((t) => t.value)).toEqual(['85.2%', '61.0%', '1.40×']);
    const flat = benchmarkWith({ capture: { ...BENCHMARK_FIXTURE.capture,
      down_pct: { value: null, n: 0, reason: 'index flat' } } });
    expect(captureTiles(flat)[1].secondary).toBe('index flat');
  });
  it('counts beats as description, not edge', () => {
    expect(beatLine(BENCHMARK_FIXTURE)).toBe(
      'Bot · account beat SPY on 1 of 2 up days and 1 of 1 down days — descriptive, not evidence of edge.');
  });
  it('carries the tax sentence and the price-only note in the footnote', () => {
    expect(TAX_LINE).toBe('Swing turnover is taxed as short-term gains, so after-tax results would differ from this chart.');
    expect(FOOTNOTE).toContain(TAX_LINE);
    expect(FOOTNOTE[0]).toContain('price indexes');
  });
});

describe('BenchmarkTab table, capture and layout (v208)', () => {
  beforeEach(() => TestBed.resetTestingModule());
  afterEach(() => vi.restoreAllMocks());

  for (const width of [390, 820, 1440]) {
    it(`keeps the approved order and pins the date column at ${width}px`, () => {
      vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(width);
      const { el } = renderTab(stubStore(BENCHMARK_FIXTURE));
      const order = [...el.querySelectorAll('.today, .range, .chips, .stats, .chart, .daily, .capture, .footnote')]
        .map((n) => n.classList[0]);
      expect(order).toEqual(['today', 'range', 'chips', 'stats', 'chart', 'daily', 'capture', 'footnote']);
      expect(el.querySelector('.daily sb-data-table .compact-list')).toBeNull();
      expect(text(el.querySelector('.daily sb-data-table th.pin'))).toContain('Date');
      expect(el.querySelector('.daily sb-data-table .wrap')!.classList.contains('phone')).toBe(width < 640);
    });
  }
  it('loads older sessions from the server, and says nothing when there are none', () => {
    const store = stubStore(BENCHMARK_FIXTURE);
    const { el } = renderTab(store);
    el.querySelector<HTMLButtonElement>('.daily button.more')!.click();
    expect(store.loadMoreBenchmarkDaily).toHaveBeenCalledTimes(1);
    TestBed.resetTestingModule();
    expect(renderTab(stubStore(benchmarkWith({ daily_has_more: false }))).el.querySelector('.daily button.more')).toBeNull();
  });
  it('disables the button while a page is loading', () => {
    const { el } = renderTab(stubStore(BENCHMARK_FIXTURE, { benchmarkLoadingMore: signal(true) }));
    expect(el.querySelector<HTMLButtonElement>('.daily button.more')!.disabled).toBe(true);
  });
  it('switches the capture index through the store', () => {
    const store = stubStore(BENCHMARK_FIXTURE);
    const { fixture, el } = renderTab(store);
    const qqq = [...el.querySelectorAll<HTMLButtonElement>('.capture button')].find((b) => text(b) === 'QQQ')!;
    qqq.click();
    fixture.detectChanges();
    expect(store.setBenchmarkCapture).toHaveBeenCalledWith('QQQ');
    expect(text(el.querySelector('.capture .beat'))).toContain('not evidence of edge');
  });
  it('sizes the controls for touch and stacks the tiles in two columns on phone', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/tabs/benchmark.ts'), 'utf8');
    expect(src).toMatch(/\.more\{[^}]*min-height:44px/);
    expect(src).toMatch(/@media \(max-width:639px\)\{[^@]*\.tiles\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)\}/);
  });
});
```

(Add `import { readFileSync } from 'node:fs'; import { join } from 'node:path';` at the top, as `partials.spec.ts` does. If `sb-data-table` reads the viewport through `ViewportService` before the spy takes effect, set the spy before `TestBed.configureTestingModule` — move it into `renderTab` via an optional `width` argument rather than dropping the per-width check.)

- [ ] **Step 2: Run them to see them fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/benchmark.spec.ts`
Expected: FAIL — `dailyColumns`, `captureTiles`, `beatLine` and the copy constants not exported; no `.daily`/`.capture`/`.footnote` sections.

- [ ] **Step 3: Implement**

Helpers by the rules above; `dailyColumns` builds the series columns with one `map` over `SERIES_ORDER` (no per-key branches). Component: import `DataTable`, keep `Segmented`/`StatTile`; computeds `dailyCols = computed(() => dailyColumns(this.store.benchmarkCapture()))`, `dailyShown = computed(() => dailyVisible(this.visible()))`, `captureOptions = INDEX_KEYS.map((k) => ({ value: k, label: CHIP_LABELS[k] }))`, `dailyKey = (row: BenchmarkDailyRow) => row.date`. Replace the `<!-- V208-17 -->` comment, inside the same `benchmarks_status !== 'empty'` block as V208-16's sections:

```html
<sb-panel class="daily">
  <sb-panel-header title="Daily comparison" [n]="p.range.sessions_n"
    hint="Newest first. Beat?: this session's return was higher, not evidence of edge. A row covering several sessions compares the same span on both sides; a missing bot session shows —." />
  <sb-data-table [rows]="p.daily" [columns]="dailyCols()" [visible]="dailyShown()" [rowKey]="dailyKey"
    clientPaging="analytics.benchmark.daily" [emptyState]="{ title: 'No sessions in this range' }" />
  @if (p.daily_has_more) {
    <button type="button" class="more" [disabled]="store.benchmarkLoadingMore()" (click)="store.loadMoreBenchmarkDaily()">Load older sessions</button>
  }
</sb-panel>
<sb-panel class="capture">
  <sb-panel-header title="Up/down capture" [n]="p.capture.up_n + p.capture.down_n" [hint]="captureFormula" />
  <sb-segmented label="Capture vs" [options]="captureOptions" [value]="store.benchmarkCapture()"
    (valueChange)="store.setBenchmarkCapture($event)" />
  <div class="tiles">@for (t of captureTiles(p); track t.label) {
    <sb-stat-tile [label]="t.label" [value]="t.value" [sample]="t.sample" [tone]="t.tone" [hint]="t.hint" [secondary]="t.secondary" />
  }</div>
  <p class="beat">{{ beatLine(p) }}</p>
</sb-panel>
<footer class="footnote">@for (line of footnote; track line) { <p>{{ line }}</p> }</footer>
```

Styles: `.more{min-height:44px;margin-top:var(--space-10);padding:0 var(--space-14);border:1px solid var(--border);border-radius:var(--panel-radius);background:var(--surface);color:var(--text)}` (keep the rule text exactly `.more{…min-height:44px…}` with no spaces around the brace or colon, as the source test reads it); `.beat{margin:var(--space-10) 0 0;font-size:var(--text-chip);color:var(--text-secondary)}`; `.footnote{display:grid;gap:var(--space-4)}.footnote p{margin:0;font-size:var(--text-micro);color:var(--text-faint)}`. Keep the phone media block written as `@media (max-width:639px){…}` with `.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}` inside it (V208-16 added it).

- [ ] **Step 4: Run the specs to see them pass**

Run each, expecting `0 failed`:
- `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/benchmark.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/tokens.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/analytics.spec.ts`
- `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

- [ ] **Step 5: Layout audit at all three widths** (`docs/claude/ui-design.md` § UI tasks; this page only)

1. Local replica: `/replicate-prod-db`, then `python -m alembic upgrade head` (the replica needs `v208_001`).
2. Fill local bars once (the refresher does this in production):

```bash
python - <<'PY'
from datetime import datetime, timezone
from swingbot.refresher import loop
from swingbot.refresher.benchmarks import benchmarks_step
from swingbot.refresher.symbols import SymbolSet
now = datetime.now(timezone.utc)
ctx = loop.CycleContext(now, "closed", SymbolSet((), ()), [], [], False, loop.CycleReport("closed", 1800.0))
benchmarks_step(ctx)
print("report error:", ctx.report.error)
PY
```

   Expected: `report error: None`; the step swallows its own failures, so also check `SELECT symbol, count(*) FROM benchmark_bars GROUP BY 1` returns four symbols.
3. `cd frontend && npm run build`, `python admin_ui.py` (local instance from `.env`'s values), `node frontend/scripts/browse.mjs login --base http://localhost:1234`.
4. `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,820,1440` → fix every finding on `/insights/analytics?tab=benchmark` and re-run until it exits 0. Findings on other routes are not this task's; list them in the report.
5. At most four clipped shots, e.g. `node frontend/scripts/browse.mjs shots --base http://localhost:1234 --path "/insights/analytics?tab=benchmark" --widths 390 --clip "sb-benchmark-tab .daily"`: check the date column stays pinned while the row scrolls, chips wrap at 390, tiles sit two per row on phone and auto-fit at 820 and 1440.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/benchmark.ts frontend/src/app/workspaces/analytics/tabs/benchmark.spec.ts
git commit -m "feat(v208): Benchmark daily table, up/down capture and footnote; layout audit clean at 390/768/820/1440"
```

# Phase G — production

### Task V208-18: Production: deploy, `v208_001` check, refresher fill, `open_notional` backfill run + rollback runbook

**Model:** opus — a data write on the production `equity_samples` table with a stop-or-go call at each gate; a wrong read of a count rewrites live rows.

**Files:**
- Modify: `docs/deploy/DEPLOY_HETZNER.md` — new `### v208: benchmark bars and open_notional` directly after the `### v205: daily FX rates (fx_daily_rates)` section (before `## Accessing the admin UI`)

**Interfaces:**
- Consumes: every v208 task merged on `main` and deployed. V208-1 revision `v208_001`, columns `equity_samples.open_notional` / `open_notional_approx`, tables `benchmark_bars`, `benchmark_refresh`. V208-4 CLI `scripts/data/backfill_equity_samples.py --open-notional [--apply]`, which prints `open_notional: would fill <F> rows (<B> backfill, <L> live), <U> unpriced` (dry run) or `open_notional: filled <F> rows (<B> backfill, <L> live), <U> unpriced` (apply), touches only the two new columns, and marks what it fills `open_notional_approx = TRUE`. V208-6 refresher step `benchmarks` (log line `benchmarks step failed` when swallowed). V208-11 `GET /api/v1/analytics/benchmark`.
- Produces: the runbook section and a dated run record in it. Nothing in code.

Rules for this task: connect **only** through `bash scripts/ops/ssh-hetzner.sh "<cmd>"` (stdin piped for SQL), never a raw `ssh`. Every write happens after its dry run and its gate. A gate that fails is a stop: report `BLOCKED:` with the numbers to the controller, who asks the partner; never "fix forward" on production. Keep every command's output (counts, verdicts, timestamps) for the run record in Step 9.

- [ ] **Step 1: Preconditions — merged, green, deployed**

Run: `gh run list --branch main --limit 3` and `gh run watch <id of the newest run>`
Expected: the run that contains the last v208 commit is green through `deploy`. Then:
`bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current"`
Expected: `v208_001 (head)` (or a later head that has `v208_001` in `alembic history`). Record the deploy time (UTC) from the run.

- [ ] **Step 2: Refresher fills `benchmark_bars` by itself**

Wait at least two refresher cycles after the deploy, then:
`bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --since 30m refresher" | grep -i benchmark`
Expected: no `benchmarks step failed` line timed after the `alembic upgrade head` step (earlier ones are the expected missing-table window).

Write `$SCRATCH/v208_bars.sql` (any scratch path outside the repo):

```sql
SELECT (min(at) AT TIME ZONE 'America/New_York')::date AS live_since FROM equity_samples;
SELECT symbol, min(session), max(session), count(*) AS rows,
       count(*) FILTER (WHERE final) AS final_rows,
       count(*) FILTER (WHERE source_symbol <> symbol) AS proxy_rows
  FROM benchmark_bars GROUP BY symbol ORDER BY symbol;
SELECT symbol, full_refreshed_on FROM benchmark_refresh ORDER BY symbol;
```

Run: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot" < "$SCRATCH/v208_bars.sql"`
Expected: four symbols (`QQQ`, `SPY`, `^DJI`, `^IXIC`); each `min` is the first NYSE session on or after `live_since`; each `max` is the last completed session (or today, with exactly one non-final row, during the session); `final_rows` equals the number of NYSE sessions from `min` to the last completed session; one `benchmark_refresh` row per symbol dated the last completed session. `proxy_rows` is normally `0`; a non-zero count is fine (Yahoo was blank) but goes into the run record. Missing symbols or a gap in sessions → stop.

- [ ] **Step 3: The recorder writes `open_notional`**

During regular hours, at least 10 minutes after the deploy:

```sql
SELECT count(*) AS new_live,
       count(*) FILTER (WHERE open_notional IS NOT NULL AND open_notional_approx IS FALSE) AS with_notional
  FROM equity_samples WHERE source = 'live' AND at > '<deploy time UTC>';
```

Expected: `new_live > 0` and `with_notional = new_live`. Outside regular hours, record "pending" and re-check on the next session before closing the plan; it does not block Steps 4-8 (the backfill fills only rows where `open_notional IS NULL`).

- [ ] **Step 4: Dry run on the local replica**

Run `/replicate-prod-db` (tops the replica up to now), then `python -m alembic upgrade head`, then:
`python scripts/data/backfill_equity_samples.py --open-notional`
Expected: one line `open_notional: would fill <F_local> rows (<B> backfill, <L> live), <U> unpriced` and the dry-run note; nothing written (`SELECT count(*) FROM equity_samples WHERE open_notional_approx IS TRUE` on the replica stays `0`).

- [ ] **Step 5: Dry run on production**

Run: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py --open-notional"`
Expected: `open_notional: would fill <F_prod> rows (...)`.
Gate: `F_prod - F_local` equals the number of pre-migration live rows production recorded between the replica sync and the deploy (check with `SELECT count(*) FROM equity_samples WHERE source='live' AND kind='point' AND open_notional IS NULL AND at > '<replica sync time>'` on production; usually `0`). Any other difference → stop. `U` (unpriced) rows stay NULL and show exposure `—`; record the count. `U` above 5 % of `F_prod` → stop and report (the daily-bar fetch is likely failing).

- [ ] **Step 6: PITR check and rollback target**

1. `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && tail -n 5 logs/pitr_verify.log"`
   Expected: the newest `VERDICT <date> PASS` is at most 31 days old. A `FAIL` or an older pass → stop (`schema-evolution.md` § Before running a data revision on production; `docs/deploy/DB_RESTORE.md`).
2. Record `T0`: `bash scripts/ops/ssh-hetzner.sh "date -u '+%F %T'"`.
3. `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && scripts/ops/rollback_to.sh '<T0>' --dry-run"`
   Expected: it resolves the Postgres, `market_data/`, `.env` and image artifacts and does not refuse the target.

- [ ] **Step 7: Fingerprint, apply, verify**

`$SCRATCH/v208_fingerprint.sql`:

```sql
SELECT count(*) AS rows,
       md5(string_agg(id || ':' || at || ':' || realized_balance || ':' || unrealized_pnl || ':' || equity
                      || ':' || open_n || ':' || skipped_n || ':' || source || ':' || kind, ',' ORDER BY id)) AS equity_cols
  FROM equity_samples WHERE at <= '<T0>';
SELECT open_notional_approx, count(*), count(open_notional) FROM equity_samples GROUP BY 1 ORDER BY 1;
```

1. Run it (as in Step 2) → record `rows`, `equity_cols` (hash H0) and the per-flag counts.
2. Apply: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py --open-notional --apply"`
   Expected: `open_notional: filled <F> rows (<B> backfill, <L> live), <U> unpriced` with `F = F_prod`, `B`, `L`, `U` as in Step 5.
3. Run the fingerprint again. Expected: the same `rows` and the same hash H0 (the existing equity columns are untouched); the `TRUE` group grew by exactly `F` and has `count(open_notional) = count(*)`; the `FALSE` group (recorder rows) unchanged except for new samples.
4. Re-run the Step 5 dry run. Expected: `would fill 0 rows (0 backfill, 0 live), <U> unpriced`.

A hash mismatch → run the rollback SQL (Step 9's runbook) at once, then stop and report.

- [ ] **Step 8: The tab reads production data**

`node frontend/scripts/browse.mjs api --base https://bomeo-capital.com --path "/api/v1/analytics/benchmark"` (signs in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` inside the script; never print them)
Expected: `benchmarks_status` `"ok"`; `range.live_since` equals Step 2's `live_since`; six `series`; `exposure` rows carry numbers (`approx: true` for backfilled days); `stats.bot_deployed.approx_share` is a percentage. Then at most two clipped shots, e.g. `node frontend/scripts/browse.mjs shots --base https://bomeo-capital.com --path "/insights/analytics?tab=benchmark" --widths 390,1440 --clip "sb-benchmark-tab .today"`: the Today card and paper line render, no `No benchmark data yet`.

- [ ] **Step 9: Write the runbook and the run record into `DEPLOY_HETZNER.md`**

Insert after the v205 section:

```markdown
### v208: benchmark bars and open_notional

Revision `v208_001` adds `equity_samples.open_notional` / `open_notional_approx`
and the tables `benchmark_bars` (one row per index per NYSE session) and
`benchmark_refresh` (per-symbol "last full refresh" date) for the Analytics
Benchmark tab.

- **Bars fill by themselves.** The refresher's `benchmarks` step writes SPY,
  QQQ, ^IXIC and ^DJI after the first cycle past `alembic upgrade head`: a full
  adjusted-history rewrite since the first equity sample once per session
  day, and today's row every 5 minutes in session. Until the revision is
  applied it logs `benchmarks step failed` once per cycle and recovers. Check:
  the bar SQL in the v208 plan's V208-18 Step 2. With `ADMIN_REFRESHER=off` the
  tab says "Benchmarks not updating — refresher is off"; nothing else is needed.
- **Live samples carry `open_notional` from the deploy on** (the recorder
  writes it, `open_notional_approx = FALSE`).
- **History is filled once** by the backfill, in this order:
  1. dry run on the local replica (`/replicate-prod-db`, `alembic upgrade head`,
     `python scripts/data/backfill_equity_samples.py --open-notional`);
  2. dry run on production:
     `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py --open-notional"`;
  3. PITR check: the newest `VERDICT ... PASS` in `logs/pitr_verify.log` is at most
     31 days old, and `scripts/ops/rollback_to.sh '<now UTC>' --dry-run` resolves;
  4. apply: the same command with `--apply`. It prints `open_notional: filled <n> rows ...`,
     touches only `open_notional`/`open_notional_approx`, and marks every row
     it fills `open_notional_approx = TRUE` (priced from daily closes). A re-run
     prints `would fill 0 rows`.
- **Rollback of the backfill only** (recorder rows keep their values):

      docker compose exec -T db psql -U swingbot -d swingbot -c "UPDATE equity_samples SET open_notional = NULL, open_notional_approx = NULL WHERE open_notional_approx IS TRUE"

- **Rollback of v208:** (1) redeploy the previous image (§ Rolling back); the
  old code never reads the new columns or tables. (2) Only to remove them,
  `docker compose exec -T bot alembic downgrade <the revision v208_001 revises>`
  (check `alembic history` first: it also rolls back every later revision).
  A bad backfill that the SQL above cannot undo: `scripts/ops/rollback_to.sh`
  to the second before the apply.

Run record: <date> — replica dry run <F_local>; production dry run <F_prod>
(<B> backfill, <L> live, <U> unpriced); PITR verdict <date> PASS; applied
<F> rows at <T0 + run time> UTC; equity-column fingerprint unchanged; bars
<min>–<max>, <proxy_rows> proxy rows; recorder check <ok | pending>.
```

Fill the run record with the recorded values (no placeholders left). Then:
Run: `python scripts/dev/testrun.py file tests/scripts/test_deploy_refresher_guard_shape.py` and `python scripts/dev/testrun.py file tests/scripts/test_rollback_to_shape.py`
Expected: `0 failed`.

- [ ] **Step 10: Commit (mirror rule: production is not done until the record is in the repo)**

```bash
git add docs/deploy/DEPLOY_HETZNER.md
git commit -m "docs(v208): DEPLOY_HETZNER -- benchmark bars and open_notional runbook, rollback SQL, production run record"
git push origin main
```

Then watch the pushed run green (`gh run watch`). If Step 3 was "pending", re-run its SQL on the next session and amend the run record in a follow-up commit before `/close-out`.

