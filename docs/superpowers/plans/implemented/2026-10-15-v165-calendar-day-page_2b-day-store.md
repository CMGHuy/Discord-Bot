# v165 P&L calendar day page. Implementation Plan, part 2b: the day store (CD9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull the task with `grep -n "^### Task CD9:" -A 300 docs/superpowers/plans/2026-10-15-v165-calendar-day-page_2b-day-store.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v165-calendar-day-page-design.md`](../specs/2026-10-15-v165-calendar-day-page-design.md) (D5 data loading)
**Index:** [`2026-10-15-v165-calendar-day-page_0-index.md`](2026-10-15-v165-calendar-day-page_0-index.md) — Global Constraints, Review Focus, `## Parallelisation`, the task ledger and `## Where to work` (`$WT`, `$R`; never `cd`). This file is the tail of part 2 (`_2-sparklines-day-data.md`, CD6..CD8), split off only to keep every file under 1500 lines.

CD9 runs after CD7 and CD8 are committed.

### Task CD9: `CalendarDayStore`: day + month in parallel, sparklines after, 404 as empty, prev/next across months, sort

**Model:** sonnet — one store, behaviour fixed by D5

**Files:**
- Create: `frontend/src/app/stores/calendar-day.store.ts`
- Create: `frontend/src/app/stores/calendar-day.store.spec.ts`

**Interfaces:**
- Consumes: CD7 `CalendarDayTrades` (with `context`, `breakdown`), `CalendarTrade` (D1 fields), `CalendarDaySparklines`, `ApiClient.calendarPnlDaySparklines`; existing `ApiClient.calendarPnl`, `ApiClient.calendarPnlDay`, `PnlCalendar`, `routeRequest` (`routing/route-request.ts`), `ApiError` (`status`, `code`), `shiftMonth` (exported by `stores/calendar.store.ts`); CD8 `isIsoDate`, `monthOf`, `adjacentTradingDay`, `monthContext`, `MonthContext`.
- Produces (CD12 consumes): `type DaySort = 'pnl' | 'r' | 'closed' | 'ticker'`; `sortTrades(trades: CalendarTrade[], sort: DaySort): CalendarTrade[]`; `CalendarDayStore` (signalStore, **not** `providedIn: 'root'` — the `calendar/:date` route provides it) with state `date: string | null, strategy: string, horizon: string, day: CalendarDayTrades | null, month: PnlCalendar | null, sparklines: CalendarDaySparklines | null, loading: boolean, error: string | null, empty: boolean, prevEdge: string | null, nextEdge: string | null, sort: DaySort`; methods `setRoute(date: string | null, strategy: string | null, horizon: string | null): void`, `resolve(): Observable<unknown>`, `setSort(sort: DaySort): void`; computeds `trades: CalendarTrade[]`, `monthCtx: MonthContext | null`, `prevDay: string | null`, `nextDay: string | null`, `filterParams: {strategy?: string; horizon?: string}`, `hasLegs: boolean`.

**Behaviour (spec D5):**
- `setRoute` stores the route: a date that fails `isIsoDate` becomes `date: null`; it clears `day`, `month`, `sparklines`, both edges, `error`, `empty`.
- `resolve()` with `date === null` → `empty: true`, **no request**. Otherwise the day route and `/calendar/pnl?month=<monthOf(date)>` start **together** (`forkJoin`), both with the filters. A day **404** is the empty state (`day: null, empty: true`, no error); any other failure sets `error` (the calendar store's wording for `unavailable`). The resolver completes when both answer — the sparklines are **not** part of it.
- Sparklines start only after the day answered 200, and a response for a date the store has since left is dropped. A sparklines failure leaves `sparklines: null` (cards render `—`).
- Prev/next = `adjacentTradingDay` over the month's `days`; only when that is `null` (the month's edge) does the store make **one** lookup of the adjacent month (`shiftMonth(month, ±1)`) and keep that month's nearest trading day as `prevEdge`/`nextEdge`.
- `trades` = `sortTrades(day.trades, sort)`; default sort `'pnl'` (the first sort the spec lists). P&L and R sort descending with nulls last; close time ascending (the day as it happened); ticker A→Z. The sort is stable, so ties keep the server's close order; the input array is never mutated.
- `filterParams` carries only the set filters (for `[queryParams]` on links); `hasLegs` is true when any row has `leg_total > 1` (D7 sample line).

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/stores/calendar-day.store.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { CalendarDay, CalendarDayTrades, CalendarTrade, PnlCalendar } from '../api/models';
import { CalendarDayStore, sortTrades } from './calendar-day.store';

const DAY_URL = '/api/v1/calendar/pnl/day';
const MONTH_URL = '/api/v1/calendar/pnl';
const SPARK_URL = '/api/v1/calendar/pnl/day/sparklines';

const cell = (date: string, net: number | null, count = 1): CalendarDay =>
  ({ date, net_pnl_amount: net, net_r: net === null ? null : net / 50, trade_count: count, win_rate: null });

const monthBody = (month: string, days: CalendarDay[]): PnlCalendar => ({
  as_of: '2026-08-20T12:00:00Z', month, days,
  totals: { net_pnl_amount: null, net_r: null, trade_count: days.length, win_rate: null },
  day_of_week: [], best_day: null, worst_day: null,
  streak: { direction: null, days: 0 }, filters: { strategies: [], horizons: [] },
});

const AUGUST = monthBody('2026-08', [cell('2026-08-03', 30), cell('2026-08-05', -90), cell('2026-08-10', 120)]);

const trade = (over: Partial<CalendarTrade> = {}): CalendarTrade => ({
  trade_id: 'a'.repeat(16), plan_id: null, opened_at: '2026-08-03T14:00:00+00:00',
  ticker: 'AAPL', strategy: 'EMA20', horizon: '4w', direction: 'bullish',
  day: '2026-08-05', closed_at: '2026-08-05T20:00:00+00:00', outcome: 'win',
  pnl_amount: 50, r_multiple: 1, mfe_r: null, mae_r: null, exit_efficiency: null,
  tags: [], auto_lesson: null, leg_index: 0, leg_total: 1,
  entry_price: 100, exit_price: 105, stop_price: 95, tp1: 110, tp2: null,
  shares: 10, held_hours: 54, return_pct: 5, exit_reason: 'tp1',
  ...over,
});

const dayBody = (trades: CalendarTrade[]): CalendarDayTrades => ({
  as_of: '2026-08-20T12:00:00Z', date: '2026-08-05', trades, trade_count: trades.length,
  winners: 0, losers: 0, total_r: null, total_ccy: null, win_rate: null,
  avg_trade_r: null, worst_drawdown_r: null, contributors: [], detractors: [],
  context: { percentile: null, history_days: 0,
    vs_avg_day: { pnl_amount: null, r: null }, vs_weekday_avg: { pnl_amount: null, r: null } },
  breakdown: { strategy: [], horizon: [], direction: [], exit_reason: [] },
});

describe('sortTrades', () => {
  const rows = [
    trade({ trade_id: 'a', ticker: 'MSFT', pnl_amount: 10, r_multiple: null, closed_at: '2026-08-05T15:00:00Z' }),
    trade({ trade_id: 'b', ticker: 'AAPL', pnl_amount: null, r_multiple: 2, closed_at: '2026-08-05T13:00:00Z' }),
    trade({ trade_id: 'c', ticker: 'NVDA', pnl_amount: 50, r_multiple: -1, closed_at: '2026-08-05T14:00:00Z' }),
  ];
  const ids = (sorted: CalendarTrade[]) => sorted.map((t) => t.trade_id);

  it('sorts P&L and R descending with nulls last, close time ascending, ticker A-Z', () => {
    expect(ids(sortTrades(rows, 'pnl'))).toEqual(['c', 'a', 'b']);
    expect(ids(sortTrades(rows, 'r'))).toEqual(['b', 'c', 'a']);
    expect(ids(sortTrades(rows, 'closed'))).toEqual(['b', 'c', 'a']);
    expect(ids(sortTrades(rows, 'ticker'))).toEqual(['b', 'a', 'c']);
  });

  it('never mutates its input', () => {
    sortTrades(rows, 'ticker');
    expect(ids(rows)).toEqual(['a', 'b', 'c']);
  });
});

describe('CalendarDayStore', () => {
  let store: InstanceType<typeof CalendarDayStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        CalendarDayStore,
      ],
    });
    store = TestBed.inject(CalendarDayStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const open = (date: string | null, strategy: string | null = null, horizon: string | null = null) => {
    store.setRoute(date, strategy, horizon);
    store.resolve().subscribe();
  };
  const monthReq = (month: string) =>
    backend.expectOne((r) => r.url === MONTH_URL && r.params.get('month') === month);

  it('asks for the day and its month together, with the filters, and the sparklines only after the day', () => {
    open('2026-08-05', 'VWAP', null);
    const day = backend.expectOne((r) => r.url === DAY_URL);
    const month = monthReq('2026-08');                 // both open at once: parallel
    expect(day.request.params.get('date')).toBe('2026-08-05');
    expect(day.request.params.get('strategy')).toBe('VWAP');
    expect(day.request.params.has('horizon')).toBe(false);
    expect(month.request.params.get('strategy')).toBe('VWAP');
    backend.expectNone((r) => r.url === SPARK_URL);

    day.flush(dayBody([trade()]));
    month.flush(AUGUST);
    expect(store.loading()).toBe(false);
    expect(store.empty()).toBe(false);
    expect(store.trades()).toHaveLength(1);
    expect(store.sparklines()).toBeNull();             // the page renders before them

    const spark = backend.expectOne((r) => r.url === SPARK_URL);
    expect(spark.request.params.get('date')).toBe('2026-08-05');
    expect(spark.request.params.get('strategy')).toBe('VWAP');
    spark.flush({ as_of: 'x', date: '2026-08-05', truncated: false, series: { ['a'.repeat(16) + ':0']: null } });
    expect(store.sparklines()?.truncated).toBe(false);
    backend.verify();
  });

  it('treats a 404 day as the empty state with working prev/next, and asks for no sparklines', () => {
    open('2026-08-04');
    backend.expectOne((r) => r.url === DAY_URL)
      .flush({ error: { code: 'not_found', message: 'no closed trades on 2026-08-04' } },
             { status: 404, statusText: 'Not Found' });
    monthReq('2026-08').flush(AUGUST);
    expect(store.empty()).toBe(true);
    expect(store.error()).toBeNull();
    expect(store.day()).toBeNull();
    expect(store.prevDay()).toBe('2026-08-03');
    expect(store.nextDay()).toBe('2026-08-05');
    backend.verify();
  });

  it('makes no request at all for a malformed or impossible date', () => {
    for (const bad of ['2026-02-30', 'abc', '2026-8-3', null]) {
      open(bad);
      backend.verify();
      expect(store.date()).toBeNull();
      expect(store.empty()).toBe(true);
    }
  });

  it('looks one month back for prev at the first trading day of a month', () => {
    open('2026-08-03');
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([trade()]));
    monthReq('2026-08').flush(AUGUST);
    monthReq('2026-07').flush(monthBody('2026-07', [
      cell('2026-07-28', 10), cell('2026-07-30', 0, 0),     // the 30th had no closes
    ]));
    expect(store.prevDay()).toBe('2026-07-28');
    expect(store.nextDay()).toBe('2026-08-05');
    backend.expectNone((r) => r.url === MONTH_URL && r.params.get('month') === '2026-09');
  });

  it('looks one month ahead for next at the last trading day, and is null when that month is empty', () => {
    open('2026-08-10');
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([trade()]));
    monthReq('2026-08').flush(AUGUST);
    monthReq('2026-09').flush(monthBody('2026-09', []));
    expect(store.prevDay()).toBe('2026-08-05');
    expect(store.nextDay()).toBeNull();
  });

  it('shows an error, not the empty state, when the day route fails for another reason', () => {
    open('2026-08-05');
    monthReq('2026-08').flush(AUGUST);
    backend.expectOne((r) => r.url === DAY_URL)
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    expect(store.error()).toBe('The admin is not responding -- these figures may be stale.');
    expect(store.empty()).toBe(false);
    expect(store.loading()).toBe(false);
  });

  it('derives sort, month context, filter params and the legs flag', () => {
    open('2026-08-05', null, '4w');
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([
      trade({ trade_id: 'x', ticker: 'MSFT', pnl_amount: 5 }),
      trade({ trade_id: 'y', ticker: 'AAPL', pnl_amount: 40, leg_index: 1, leg_total: 2 }),
    ]));
    monthReq('2026-08').flush(AUGUST);
    expect(store.trades().map((t) => t.trade_id)).toEqual(['y', 'x']);   // default: P&L
    store.setSort('ticker');
    expect(store.trades().map((t) => t.ticker)).toEqual(['AAPL', 'MSFT']);
    expect(store.monthCtx()?.rank).toBe(3);
    expect(store.monthCtx()?.rankOf).toBe(3);
    expect(store.filterParams()).toEqual({ horizon: '4w' });
    expect(store.hasLegs()).toBe(true);
  });

  it('drops a sparklines answer for a date the page has already left', () => {
    open('2026-08-05');
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([trade()]));
    monthReq('2026-08').flush(AUGUST);
    const late = backend.expectOne((r) => r.url === SPARK_URL);
    store.setRoute('2026-08-10', null, null);
    late.flush({ as_of: 'x', date: '2026-08-05', truncated: false, series: {} });
    expect(store.sparklines()).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/stores/calendar-day.store.spec.ts'`
Expected: FAIL at compile — `Cannot find module './calendar-day.store'`.

- [ ] **Step 3: Write the store**

Create `frontend/src/app/stores/calendar-day.store.ts`:

```ts
import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { Observable, catchError, forkJoin, of, tap, throwError } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import {
  CalendarDaySparklines,
  CalendarDayTrades,
  CalendarTrade,
  PnlCalendar,
} from '../api/models';
import { routeRequest } from '../routing/route-request';
import {
  MonthContext,
  adjacentTradingDay,
  isIsoDate,
  monthContext,
  monthOf,
} from '../workspaces/calendar/day/month-context';
import { shiftMonth } from './calendar.store';

/* v165 D5 -- the calendar day page's data. Provided by the `calendar/:date`
 * route, never at root: each visit owns its day. */

export type DaySort = 'pnl' | 'r' | 'closed' | 'ticker';

/** Descending, nulls last -- a missing figure is never ranked as 0. */
function descNullsLast(a: number | null, b: number | null): number {
  if (a === null || b === null) return a === null ? (b === null ? 0 : 1) : -1;
  return b - a;
}

const COMPARE: Record<DaySort, (a: CalendarTrade, b: CalendarTrade) => number> = {
  pnl: (a, b) => descNullsLast(a.pnl_amount, b.pnl_amount),
  r: (a, b) => descNullsLast(a.r_multiple, b.r_multiple),
  closed: (a, b) => (a.closed_at ?? '').localeCompare(b.closed_at ?? ''),
  ticker: (a, b) => a.ticker.localeCompare(b.ticker),
};

/** Stable (ties keep the server's close order); never mutates `trades`. */
export function sortTrades(trades: CalendarTrade[], sort: DaySort): CalendarTrade[] {
  return [...trades].sort(COMPARE[sort]);
}

interface CalendarDaySlice {
  date: string | null;
  strategy: string;
  horizon: string;
  day: CalendarDayTrades | null;
  month: PnlCalendar | null;
  sparklines: CalendarDaySparklines | null;
  loading: boolean;
  error: string | null;
  /** True for a malformed date or a day with no rows under the filter. */
  empty: boolean;
  /** Nearest trading day in the adjacent month, looked up only at the edge. */
  prevEdge: string | null;
  nextEdge: string | null;
  sort: DaySort;
}

type Filters = { strategy?: string; horizon?: string };

const UNAVAILABLE = 'The admin is not responding -- these figures may be stale.';

const notFoundAsNull = (error: unknown): Observable<null> =>
  error instanceof ApiError && error.status === 404 ? of(null) : throwError(() => error);

export const CalendarDayStore = signalStore(
  withState<CalendarDaySlice>({
    date: null, strategy: '', horizon: '',
    day: null, month: null, sparklines: null,
    loading: false, error: null, empty: false,
    prevEdge: null, nextEdge: null, sort: 'pnl',
  }),
  withComputed(({ date, day, month, sort, prevEdge, nextEdge, strategy, horizon }) => ({
    trades: computed(() => sortTrades(day()?.trades ?? [], sort())),
    monthCtx: computed<MonthContext | null>(() => {
      const current = date();
      const data = month();
      return current && data ? monthContext(data.days, current) : null;
    }),
    prevDay: computed(() => {
      const current = date();
      const data = month();
      return current && data ? adjacentTradingDay(data.days, current, -1) ?? prevEdge() : null;
    }),
    nextDay: computed(() => {
      const current = date();
      const data = month();
      return current && data ? adjacentTradingDay(data.days, current, 1) ?? nextEdge() : null;
    }),
    filterParams: computed<Filters>(() => ({
      ...(strategy() ? { strategy: strategy() } : {}),
      ...(horizon() ? { horizon: horizon() } : {}),
    })),
    hasLegs: computed(() => (day()?.trades ?? []).some((t) => t.leg_total > 1)),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    const filters = (): Filters => ({
      strategy: store.strategy() || undefined,
      horizon: store.horizon() || undefined,
    });

    /** After the day, never blocking it; a late answer for a day the page
     *  has left is dropped. A failure leaves the cards on `—`. */
    const loadSparklines = (date: string): void => {
      api.calendarPnlDaySparklines({ date, ...filters() }).subscribe({
        next: (sparklines) => {
          if (store.date() === date) patchState(store, { sparklines });
        },
        error: () => undefined,
      });
    };

    /** One lookup of the adjacent month, only when this month has no
     *  trading day on that side of `date`. */
    const loadEdge = (date: string, data: PnlCalendar, step: 1 | -1): void => {
      if (adjacentTradingDay(data.days, date, step) !== null) return;
      api.calendarPnl({ month: shiftMonth(monthOf(date), step), ...filters() }).subscribe({
        next: (other) => {
          if (store.date() !== date) return;
          const edge = adjacentTradingDay(other.days, date, step);
          patchState(store, step === 1 ? { nextEdge: edge } : { prevEdge: edge });
        },
        error: () => undefined,
      });
    };

    const resolve = (): Observable<unknown> => {
      const date = store.date();
      if (date === null) {
        patchState(store, { empty: true, loading: false });
        return of(undefined);
      }
      const day$ = api.calendarPnlDay({ date, ...filters() }).pipe(
        catchError(notFoundAsNull),
        tap((day) => {
          patchState(store, { day, empty: day === null });
          if (day) loadSparklines(date);
        }),
      );
      const month$ = api.calendarPnl({ month: monthOf(date), ...filters() }).pipe(
        tap((month) => {
          patchState(store, { month });
          loadEdge(date, month, -1);
          loadEdge(date, month, 1);
        }),
      );
      return routeRequest(forkJoin([day$, month$]), {
        start: () => patchState(store, { loading: true, error: null }),
        next: () => patchState(store, { loading: false }),
        error: (error) => patchState(store, {
          loading: false,
          error: error.code === 'unavailable' ? UNAVAILABLE : error.message,
        }),
      });
    };

    return {
      resolve,

      /** From the route: `:date` and the `strategy`/`horizon` query params. */
      setRoute(date: string | null, strategy: string | null, horizon: string | null): void {
        patchState(store, {
          date: isIsoDate(date) ? date : null,
          strategy: strategy ?? '',
          horizon: horizon ?? '',
          day: null, month: null, sparklines: null,
          prevEdge: null, nextEdge: null, error: null, empty: false,
        });
      },

      setSort(sort: DaySort): void {
        patchState(store, { sort });
      },
    };
  }),
);
```

- [ ] **Step 4: Run the spec to verify it passes**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/stores/calendar-day.store.spec.ts'`
Expected: PASS (2 `sortTrades` tests + 8 store tests). If `--include` is rejected, run `npm --prefix $WT/frontend run test -- --watch=false`, expected PASS.

- [ ] **Step 5: Commit**

```bash
git -C $WT add frontend/src/app/stores/calendar-day.store.ts frontend/src/app/stores/calendar-day.store.spec.ts
git -C $WT commit -m "feat(calendar-ui): CalendarDayStore -- day and month together, sparklines after, 404 as empty

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the last command lists none of this task's files.
