# v165 P&L calendar day page. Implementation Plan, part 3b: day page, drawer button and URL filters, final runs (CD12..CD14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task CD13:" -A 400 docs/superpowers/plans/2026-10-15-v165-calendar-day-page_3b-day-page-drawer-url.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v165-calendar-day-page-design.md`](../specs/2026-10-15-v165-calendar-day-page-design.md) (D5 layout, D6 drawer and URL, D7 copy, Testing)
**Index:** [`2026-10-15-v165-calendar-day-page_0-index.md`](2026-10-15-v165-calendar-day-page_0-index.md) — Global Constraints, Review Focus, `## Parallelisation`, the task ledger and `## Where to work` (`$WT` = the worktree, `$R` = the main tree; never `cd`, use absolute paths). This file is the tail of part 3 (`_3-day-page-ui.md`, CD10..CD11), split off only to keep every file under 1500 lines.

Order: CD12 after CD9 and CD11; CD13 after CD12 and CD7; CD14 last, after everything is committed.

Frontend runs (from the index): `npm --prefix $WT/frontend run test -- --watch=false --include='<spec glob>'`; if the builder rejects `--include`, run `npm --prefix $WT/frontend run test -- --watch=false` (the whole frontend suite). A `Timeout waiting for worker` is a known flake: re-run once.

Names consumed from earlier parts (do not redefine them): CD7 types in `frontend/src/app/api/models.ts`; CD8 `month-context.ts` and `day-copy.ts`; CD9 `CalendarDayStore`/`DaySort` in `frontend/src/app/stores/calendar-day.store.ts`; CD11 `DayTradeCard` in `day/day-trade-card.ts`.

### Task CD12: Day page `CalendarDayPage` and the `calendar/:date` route

**Model:** sonnet — one page inside one workspace, layout fixed by D5/D7

**Files:**
- Create: `frontend/src/app/workspaces/calendar/day/calendar-day.ts`
- Create: `frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts`
- Modify: `frontend/src/app/workspaces/calendar/calendar.routes.ts` (whole file, today one line)

**Interfaces:**
- Consumes: CD9 `CalendarDayStore` and `DaySort` (`frontend/src/app/stores/calendar-day.store.ts`); CD11 `DayTradeCard` (`./day-trade-card`); CD8 `WIN_RATE_MIN_N`, `monthOf`, `ordinal`, `percentileView` (`./month-context`), `PAPER_CAPTION`, `ONE_DAY_CAVEAT`, `R_TOOLTIP`, `legsSampleNote` (`./day-copy`); CD7 `CalendarTrade`, `DayBreakdownDimension`, `DayBreakdownRow`, `DayContext`, `DayDelta`, `SparkSeries`; existing `monthLabel` (`../calendar.helpers`), `StatTile` (`ui/stat-tile`), `Panel`, `Tab`, `TabBar` (`ui/layout`), `Segmented`, `SegmentOption` (`ui/segmented`), `EmptyStateComponent` (`ui/empty-state`, selector `sb-empty-state`, inputs `title`, `hint`), `ConnectionStore.currency()`, `ABSENT, money, rMultiple` (`ui/format`), `resolveRoute` (`routing/route-resolver`), `onEvents, routeData` (`routing/route-metadata`).
- Produces: component `CalendarDayPage`, selector `sb-calendar-day`, input `date = input<string>()` (the raw `:date` param, bound by `withComponentInputBinding()`); exported pure `longDate(date: string): string`, `weekdayName(date: string): string`, `interface MonthLine {path: string; marker: {x: number; y: number} | null; zeroY: number | null}`, `monthLineGeometry(curve: {date: string; value: number}[], dayIndex: number, width?: number, height?: number): MonthLine` (defaults 240, 56), `breakdownWinRate(row: DayBreakdownRow): string`; `calendarRoutes` = `[<'' list route, now pathMatch 'full'>, {path: ':date', providers: [CalendarDayStore], runGuardsAndResolvers: 'always', data: routeData('Calendar day', onEvents('trades')), resolve: {ready}, loadComponent → CalendarDayPage}]`. CD13 replaces only the `''` route's `resolve`.

**Layout (spec D5, top to bottom; D7 copy verbatim):**
1. Header: `← Calendar · <Month YYYY>` back link to `/calendar?month=<YYYY-MM>&<set filters>`; the long date (`Wednesday, August 5, 2026`); `‹ prev day` / `next day ›` links to `/calendar/<day>?<set filters>` from `store.prevDay()` / `store.nextDay()`, rendered as disabled text when null.
2. `PAPER_CAPTION` directly under the header, **always** (empty and error states too). The seven drawer tiles (Total, Total P&L, Win rate, Winners, Losers, Average trade, Worst drawdown), each with `[sample]="day.trade_count"`; the three R tiles carry `R_TOOLTIP` as their `title`. When `store.hasLegs()`: `legsSampleNote(trade_count)` under the tiles.
3. Two panels side by side (one column below 640px): **How this day compares** — percentile (`percentileView(context.percentile, context.history_days).text`), month rank, vs average day, vs average `<Weekday>`, then `ONE_DAY_CAVEAT`; every figure in neutral text (no `pos`/`neg` class anywhere in the panel, D7). **Month so far** — the month equity line (`monthCtx.curve`) with this day marked, month-to-date P&L and R (P&L and R signs may use `pos`/`neg`), and the same rank line (`3rd best of 3 days in August 2026`). A null-net day has no marker and rank `—`.
4. **What drove it** — `sb-tab-bar` Strategy / Horizon / Direction / Exit (ids are the `DayBreakdownDimension`s); a table `key · n · P&L · R · Win % · bar` — P&L and R **before** win%; win% is `—` with class `withheld` when `n < WIN_RATE_MIN_N` (5) or `win_rate` is null; the R header carries `R_TOOLTIP`; the bar is `|pnl| / max |pnl|` of the visible rows, `pos`/`neg` by sign.
5. **Trades (n)** — `sb-segmented` sort (P&L, R, Close time, Ticker → `store.setSort`) in the panel's `panel-actions` slot; one `sb-day-trade-card` per `store.trades()` row, tracked by `trade_id:leg_index`, given `store.sparklines()?.series['<trade_id>:<leg_index>']`.
- `store.day() === null && store.empty()` (a 404 day or a malformed date): `sb-empty-state` titled `No closed trades on <raw :date> under this filter`, header and prev/next still rendered. `store.loading()` with no day yet: `Loading...`. `store.error()`: a `role="status"` line, as on the calendar.
- Dates stay strings; `longDate`/`weekdayName` format through `Date.UTC` with `timeZone: 'UTC'` so the weekday never shifts with the viewer's zone.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts`:

```ts
import { HttpRequest, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideLocationMocks } from '@angular/common/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Routes, provideRouter, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { of } from 'rxjs';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../../api/interceptors';
import {
  CalendarDay,
  CalendarDaySparklines,
  CalendarDayTrades,
  CalendarTrade,
  DayContext,
  PnlCalendar,
} from '../../../api/models';
import { CalendarDayStore } from '../../../stores/calendar-day.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { calendarRoutes } from '../calendar.routes';
import {
  CalendarDayPage,
  breakdownWinRate,
  longDate,
  monthLineGeometry,
  weekdayName,
} from './calendar-day';
import { ONE_DAY_CAVEAT, PAPER_CAPTION, R_TOOLTIP } from './day-copy';

const DAY_URL = '/api/v1/calendar/pnl/day';
const MONTH_URL = '/api/v1/calendar/pnl';
const SPARK_URL = '/api/v1/calendar/pnl/day/sparklines';

const cell = (date: string, net: number | null, r: number | null): CalendarDay =>
  ({ date, net_pnl_amount: net, net_r: r, trade_count: 1, win_rate: null });

const monthBody = (month: string, days: CalendarDay[]): PnlCalendar => ({
  as_of: '2026-08-20T12:00:00Z', month, days,
  totals: { net_pnl_amount: null, net_r: null, trade_count: days.length, win_rate: null },
  day_of_week: [], best_day: null, worst_day: null,
  streak: { direction: null, days: 0 }, filters: { strategies: [], horizons: [] },
});

/** Running P&L 30, -60, 60; 2026-08-05 is the worst of three. */
const AUGUST = monthBody('2026-08', [
  cell('2026-08-03', 30, 0.6), cell('2026-08-05', -90, -1.8), cell('2026-08-10', 120, 2.4),
]);

const trade = (over: Partial<CalendarTrade> = {}): CalendarTrade => ({
  trade_id: 'a'.repeat(16), plan_id: null, opened_at: '2026-08-03T14:00:00+00:00',
  ticker: 'AAPL', strategy: 'EMA20', horizon: '4w', direction: 'bullish',
  day: '2026-08-05', closed_at: '2026-08-05T15:00:00+00:00', outcome: 'win',
  pnl_amount: 40, r_multiple: 0.8, mfe_r: null, mae_r: null, exit_efficiency: null,
  tags: [], auto_lesson: null, leg_index: 0, leg_total: 1,
  entry_price: 100, exit_price: 104, stop_price: 95, tp1: 104, tp2: 110,
  shares: 10, held_hours: 49, return_pct: 4, exit_reason: 'tp1',
  ...over,
});

const LEG = trade({ leg_index: 1, leg_total: 2 });
const LOSER = trade({
  trade_id: 'b'.repeat(16), ticker: 'MSFT', strategy: 'VWAP', direction: 'bearish',
  closed_at: '2026-08-05T14:00:00+00:00', outcome: 'loss',
  pnl_amount: -130, r_multiple: -2.6, exit_reason: 'stop',
});

const CONTEXT: DayContext = {
  percentile: 87.3, history_days: 212,
  vs_avg_day: { pnl_amount: 12.5, r: 0.25 },
  vs_weekday_avg: { pnl_amount: -3, r: null },
};

const dayBody = (over: Partial<CalendarDayTrades> = {}): CalendarDayTrades => ({
  as_of: '2026-08-20T12:00:00Z', date: '2026-08-05', trades: [LEG, LOSER], trade_count: 2,
  winners: 1, losers: 1, total_r: -1.8, total_ccy: -90, win_rate: 50,
  avg_trade_r: -0.9, worst_drawdown_r: -2.6,
  contributors: [{ ticker: 'AAPL', r: 0.8 }], detractors: [{ ticker: 'MSFT', r: -2.6 }],
  context: CONTEXT,
  breakdown: {
    strategy: [
      { key: 'EMA20', n: 1, pnl_amount: 40, r: 0.8, win_rate: 100 },
      { key: 'VWAP', n: 1, pnl_amount: -130, r: -2.6, win_rate: 0 },
    ],
    horizon: [{ key: '4w', n: 2, pnl_amount: -90, r: -1.8, win_rate: 50 }],
    direction: [
      { key: 'bullish', n: 1, pnl_amount: 40, r: 0.8, win_rate: 100 },
      { key: 'bearish', n: 1, pnl_amount: -130, r: -2.6, win_rate: 0 },
    ],
    exit_reason: [
      { key: 'tp1', n: 1, pnl_amount: 40, r: 0.8, win_rate: 100 },
      { key: 'stop', n: 1, pnl_amount: -130, r: -2.6, win_rate: 0 },
    ],
  },
  ...over,
});

const SPARKS: CalendarDaySparklines = {
  as_of: '2026-08-20T12:00:00Z', date: '2026-08-05', truncated: false,
  series: {
    [`${'a'.repeat(16)}:1`]: {
      closes: [{ date: '2026-08-03', close: 100 }, { date: '2026-08-05', close: 104 }],
      exit_bar: 1, last_bar: '2026-08-28', stale: false,
      entry: 100, stop: 95, tp1: 104, tp2: 110, exit: 104, exit_date: '2026-08-05',
    },
    [`${'b'.repeat(16)}:0`]: null,
  },
};

const PREFERENCES = { resolve: () => of(undefined), values: () => ({}), update: () => undefined };

function configure(routes: Routes = []): void {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(routes, withComponentInputBinding()),
      provideLocationMocks(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      { provide: ConnectionStore, useValue: { currency: () => '€' } },
      { provide: PreferencesStore, useValue: PREFERENCES },
      ...(routes.length ? [] : [CalendarDayStore]),
    ],
  });
}

/** Answers whatever the store asked for: the day (or a 404), the month,
 *  any edge month (from `edges`, else empty) and the sparklines. */
function answer(day: CalendarDayTrades | 404, edges: Record<string, CalendarDay[]> = {}): void {
  const backend = TestBed.inject(HttpTestingController);
  const dayReq = backend.expectOne((r) => r.url === DAY_URL);
  if (day === 404) {
    dayReq.flush({ error: { code: 'not_found', message: 'no closed trades' } },
                 { status: 404, statusText: 'Not Found' });
  } else {
    dayReq.flush(day);
  }
  for (const req of backend.match((r) => r.url === MONTH_URL)) {
    const month = req.request.params.get('month')!;
    req.flush(month === '2026-08' ? AUGUST : monthBody(month, edges[month] ?? []));
  }
  for (const req of backend.match((r) => r.url === MONTH_URL)) {   // edge lookups made after the month
    const month = req.request.params.get('month')!;
    req.flush(monthBody(month, edges[month] ?? []));
  }
  for (const req of backend.match((r) => r.url === SPARK_URL)) req.flush(SPARKS);
}

async function open(
  date: string,
  day: CalendarDayTrades | 404 = dayBody(),
  edges: Record<string, CalendarDay[]> = {},
): Promise<ComponentFixture<CalendarDayPage>> {
  configure();
  const store = TestBed.inject(CalendarDayStore);
  store.setRoute(date, 'EMA20', null);
  store.resolve().subscribe();
  answer(day, edges);
  const fixture = TestBed.createComponent(CalendarDayPage);
  fixture.componentRef.setInput('date', date);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

const el = (fixture: ComponentFixture<unknown>) => fixture.nativeElement as HTMLElement;
const text = (root: HTMLElement, selector: string) =>
  root.querySelector(selector)?.textContent?.replace(/\s+/g, ' ').trim();
const click = async (fixture: ComponentFixture<unknown>, selector: string, label: string) => {
  const button = [...el(fixture).querySelectorAll<HTMLElement>(selector)]
    .find((b) => b.textContent?.trim().startsWith(label));
  button!.click();
  fixture.detectChanges();
  await fixture.whenStable();
};

describe('calendar-day helpers', () => {
  it('formats the long date and weekday in UTC', () => {
    expect(longDate('2026-08-05')).toBe('Wednesday, August 5, 2026');
    expect(weekdayName('2026-08-03')).toBe('Monday');
  });

  it('draws the month line through zero with the day marked', () => {
    const curve = [
      { date: '2026-08-03', value: 30 },
      { date: '2026-08-05', value: -60 },
      { date: '2026-08-10', value: 60 },
    ];
    expect(monthLineGeometry(curve, 1)).toEqual({
      path: 'M 0.00 15.50 L 120.00 53.00 L 240.00 3.00',
      marker: { x: 120, y: 53 },
      zeroY: 28,
    });
    expect(monthLineGeometry(curve, -1).marker).toBeNull();
    expect(monthLineGeometry([], -1)).toEqual({ path: '', marker: null, zeroY: null });
  });

  it('withholds win% below five rows', () => {
    const row = { key: 'EMA20', n: 4, pnl_amount: 10, r: 0.2, win_rate: 75 };
    expect(breakdownWinRate(row)).toBe('—');
    expect(breakdownWinRate({ ...row, n: 5, win_rate: 60 })).toBe('60%');
    expect(breakdownWinRate({ ...row, n: 9, win_rate: null })).toBe('—');
  });
});

describe('CalendarDayPage', () => {
  it('shows the paper caption, the long date and the seven tiles, R explained', async () => {
    const fixture = await open('2026-08-05');
    expect(text(el(fixture), '.caption')).toBe(PAPER_CAPTION);
    expect(text(el(fixture), '.long-date')).toBe('Wednesday, August 5, 2026');
    expect(el(fixture).querySelectorAll('.tiles sb-stat-tile')).toHaveLength(7);
    expect(el(fixture).querySelectorAll(`.tiles sb-stat-tile[title="${R_TOOLTIP}"]`)).toHaveLength(3);
  });

  it('says once that scale-out legs count separately, only when there are legs', async () => {
    const legs = await open('2026-08-05');
    expect(text(el(legs), '.sample-note')).toBe('2 rows · scale-out legs count separately');
    const whole = await open('2026-08-05', dayBody({ trades: [trade(), LOSER] }));
    expect(el(whole).querySelector('.sample-note')).toBeNull();
  });

  it('compares the day with its N beside it, in neutral text, with the caveat', async () => {
    const root = el(await open('2026-08-05'));
    expect(text(root, '.percentile')).toBe('87th percentile of 212 other trading days');
    expect(text(root, '.compare .rank')).toBe('3rd best of 3 days in August 2026');
    expect(text(root, '.vs-day')).toBe('+12.50 € · +0.25R');
    expect(text(root, '.vs-weekday-label')).toBe('vs average Wednesday');
    expect(text(root, '.vs-weekday')).toBe('-3.00 € · —');
    expect(root.querySelectorAll('.compare .pos, .compare .neg')).toHaveLength(0);
    expect(text(root, '.caveat')).toBe(ONE_DAY_CAVEAT);
  });

  it('bands the percentile below 60 days and hides it below 20', async () => {
    const band = el(await open('2026-08-05', dayBody({
      context: { ...CONTEXT, percentile: 70, history_days: 40 },
    })));
    expect(text(band, '.percentile')).toBe('Top third of 40 other trading days · small sample');
    const hidden = el(await open('2026-08-05', dayBody({
      context: { ...CONTEXT, percentile: null, history_days: 12 },
    })));
    expect(text(hidden, '.percentile')).toBe('Only 12 trading days so far — percentile hidden');
  });

  it('renders a day with no net figure as dashes, never 0', async () => {
    const root = el(await open('2026-08-05', dayBody({
      context: {
        percentile: null, history_days: 100,
        vs_avg_day: { pnl_amount: null, r: null },
        vs_weekday_avg: { pnl_amount: null, r: null },
      },
    })));
    expect(text(root, '.percentile')).toBe('—');
    expect(text(root, '.vs-day')).toBe('—');
    expect(text(root, '.vs-weekday')).toBe('—');
  });

  it('draws the month so far with this day marked and month-to-date figures', async () => {
    const root = el(await open('2026-08-05'));
    expect(root.querySelector('svg.month-line circle.marker')).not.toBeNull();
    expect(text(root, '.mtd-pnl')).toBe('-60.00 €');
    expect(text(root, '.mtd-r')).toBe('-1.20R');
    expect(root.querySelector('.mtd-r')?.getAttribute('title')).toBe(R_TOOLTIP);
    expect(text(root, '.month-panel .rank')).toBe('3rd best of 3 days in August 2026');
  });

  it('breaks the day down by strategy first, P&L and R before win%, and switches tab', async () => {
    const fixture = await open('2026-08-05');
    const heads = [...el(fixture).querySelectorAll('.breakdown thead th')].map((th) => th.textContent?.trim());
    expect(heads).toEqual(['Strategy', 'n', 'P&L', 'R', 'Win %', '']);
    expect(el(fixture).querySelector('.breakdown thead th.r-head')?.getAttribute('title')).toBe(R_TOOLTIP);
    const keys = () => [...el(fixture).querySelectorAll('.breakdown-row .key')].map((k) => k.textContent?.trim());
    expect(keys()).toEqual(['EMA20', 'VWAP']);
    await click(fixture, 'sb-tab-bar button', 'Horizon');
    expect(keys()).toEqual(['4w']);
    expect(text(el(fixture), '.breakdown thead th')).toBe('Horizon');
  });

  it('greys win% out below five rows and shows it from five', async () => {
    const thin = el(await open('2026-08-05'));
    const cellOf = (root: HTMLElement) => root.querySelector('.breakdown-row .win');
    expect(cellOf(thin)?.textContent?.trim()).toBe('—');
    expect(cellOf(thin)?.classList.contains('withheld')).toBe(true);
    const wide = el(await open('2026-08-05', dayBody({
      breakdown: { ...dayBody().breakdown,
        strategy: [{ key: 'EMA20', n: 5, pnl_amount: 40, r: 0.8, win_rate: 60 }] },
    })));
    expect(cellOf(wide)?.textContent?.trim()).toBe('60%');
    expect(cellOf(wide)?.classList.contains('withheld')).toBe(false);
  });

  it('lists one card per row, sorted by P&L, and re-sorts by close time', async () => {
    const fixture = await open('2026-08-05');
    const tickers = () => [...el(fixture).querySelectorAll('sb-day-trade-card .ticker')]
      .map((t) => t.textContent?.trim());
    expect(text(el(fixture), '.trades-panel h2')).toBe('Trades (2)');
    expect(tickers()).toEqual(['AAPL', 'MSFT']);
    await click(fixture, 'sb-segmented button', 'Close time');
    expect(tickers()).toEqual(['MSFT', 'AAPL']);
    expect(el(fixture).querySelector('sb-day-trade-card a.open')?.getAttribute('href'))
      .toBe('/trades/' + 'b'.repeat(16));
  });

  it('gives each card its own sparkline, and a dash where there is none', async () => {
    const cards = el(await open('2026-08-05')).querySelectorAll('sb-day-trade-card');
    expect(cards[0].querySelector('sb-trade-sparkline svg')).not.toBeNull();
    expect(cards[1].querySelector('sb-trade-sparkline .spark-empty')).not.toBeNull();
  });

  it('shows a 404 day as the empty state, with working prev/next and the caption', async () => {
    const root = el(await open('2026-08-04', 404));
    expect(text(root, 'sb-empty-state .empty-title')).toBe('No closed trades on 2026-08-04 under this filter');
    expect(root.querySelector('a.prev')?.getAttribute('href')).toBe('/calendar/2026-08-03?strategy=EMA20');
    expect(root.querySelector('a.next')?.getAttribute('href')).toBe('/calendar/2026-08-05?strategy=EMA20');
    expect(root.querySelector('.tiles')).toBeNull();
    expect(text(root, '.caption')).toBe(PAPER_CAPTION);
  });

  it('steps to the next month at the month edge, skipping its empty days', async () => {
    const root = el(await open('2026-08-10', dayBody({ date: '2026-08-10' }), {
      '2026-09': [{ ...cell('2026-09-01', 0, 0), trade_count: 0 }, cell('2026-09-02', 15, 0.3)],
    }));
    expect(root.querySelector('a.prev')?.getAttribute('href')).toBe('/calendar/2026-08-05?strategy=EMA20');
    expect(root.querySelector('a.next')?.getAttribute('href')).toBe('/calendar/2026-09-02?strategy=EMA20');
  });

  it('disables a step with nowhere to go', async () => {
    const root = el(await open('2026-08-10', dayBody({ date: '2026-08-10' })));
    expect(root.querySelector('a.next')).toBeNull();
    expect(text(root, '.next.off')).toBe('next day ›');
  });

  it('goes back to the same filtered month', async () => {
    const root = el(await open('2026-08-05'));
    expect(text(root, 'a.back')).toBe('← Calendar · August 2026');
    expect(root.querySelector('a.back')?.getAttribute('href')).toBe('/calendar?month=2026-08&strategy=EMA20');
  });
});

describe('calendar/:date route', () => {
  const ROUTES: Routes = [{ path: 'calendar', children: calendarRoutes }];

  async function take(predicate: (r: HttpRequest<unknown>) => boolean): Promise<TestRequest> {
    const backend = TestBed.inject(HttpTestingController);
    for (let i = 0; i < 50; i++) {
      const [found] = backend.match(predicate);
      if (found) return found;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    throw new Error('the expected request was never made');
  }

  it('keeps the list route first and the day route after it', () => {
    expect(calendarRoutes.map((r) => r.path)).toEqual(['', ':date']);
    expect(calendarRoutes[0].pathMatch).toBe('full');
  });

  it('hands the date and the filters from the URL to the day store', async () => {
    configure(ROUTES);
    const harness = await RouterTestingHarness.create();
    const navigation = harness.navigateByUrl('/calendar/2026-08-05?strategy=EMA20&horizon=4w');
    const day = await take((r) => r.url === DAY_URL);
    expect(day.request.params.get('date')).toBe('2026-08-05');
    expect(day.request.params.get('strategy')).toBe('EMA20');
    expect(day.request.params.get('horizon')).toBe('4w');
    day.flush(dayBody());
    (await take((r) => r.url === MONTH_URL)).flush(AUGUST);
    await navigation;
    (await take((r) => r.url === SPARK_URL)).flush(SPARKS);
    harness.detectChanges();
    expect(harness.routeDebugElement?.componentInstance).toBeInstanceOf(CalendarDayPage);
    expect(text(harness.routeNativeElement!, '.long-date')).toBe('Wednesday, August 5, 2026');
  });

  it('shows the empty state for an impossible date without a single request', async () => {
    configure(ROUTES);
    const harness = await RouterTestingHarness.create('/calendar/2026-02-30');
    TestBed.inject(HttpTestingController).verify();
    expect(text(harness.routeNativeElement!, 'sb-empty-state .empty-title'))
      .toBe('No closed trades on 2026-02-30 under this filter');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/workspaces/calendar/day/calendar-day.spec.ts'`
Expected: FAIL at compile — `Cannot find module './calendar-day'`.

- [ ] **Step 3: Write the page**

Create `frontend/src/app/workspaces/calendar/day/calendar-day.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import {
  CalendarTrade,
  DayBreakdownDimension,
  DayBreakdownRow,
  DayContext,
  DayDelta,
  SparkSeries,
} from '../../../api/models';
import { CalendarDayStore, DaySort } from '../../../stores/calendar-day.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { ABSENT, money, rMultiple } from '../../../ui/format';
import { Panel, Tab, TabBar } from '../../../ui/layout';
import { SegmentOption, Segmented } from '../../../ui/segmented';
import { StatTile } from '../../../ui/stat-tile';
import { monthLabel } from '../calendar.helpers';
import { ONE_DAY_CAVEAT, PAPER_CAPTION, R_TOOLTIP, legsSampleNote } from './day-copy';
import { DayTradeCard } from './day-trade-card';
import { WIN_RATE_MIN_N, monthOf, ordinal, percentileView } from './month-context';

/* v165 D5 -- one P&L calendar day as a page: the drawer's tiles, how the day
 * compares (D2), what drove it (D3), and every row as a card with its
 * sparkline (D1/D4). The drawer stays the quick preview. D7 governs every
 * word and colour here: paper caption always, N beside every comparison,
 * comparison figures in neutral text. */

const UTC_DAY = (date: string): Date => {
  const [year, month, day] = date.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day));
};

/** "Wednesday, August 5, 2026", in UTC so the viewer's zone never shifts it. */
export function longDate(date: string): string {
  return UTC_DAY(date).toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC',
  });
}

export function weekdayName(date: string): string {
  return UTC_DAY(date).toLocaleDateString('en-US', { weekday: 'long', timeZone: 'UTC' });
}

export interface MonthLine {
  path: string;
  marker: { x: number; y: number } | null;
  /** Where 0 sits, so a month under water reads as one. */
  zeroY: number | null;
}

const LINE_PAD = 3;
const round2 = (value: number): number => Math.round(value * 100) / 100;

/** The month's running P&L as a path, 0 always inside the domain. */
export function monthLineGeometry(
  curve: { date: string; value: number }[],
  dayIndex: number,
  width = 240,
  height = 56,
): MonthLine {
  if (curve.length === 0) return { path: '', marker: null, zeroY: null };
  const values = [0, ...curve.map((p) => p.value)];
  const min = Math.min(...values);
  const span = Math.max(...values) - min;
  const y = (v: number) =>
    round2(span === 0 ? height / 2 : height - LINE_PAD - ((v - min) / span) * (height - 2 * LINE_PAD));
  const last = curve.length - 1;
  const points = curve.map((p, i) => ({ x: last === 0 ? width / 2 : round2((i / last) * width), y: y(p.value) }));
  const path = points.length === 1
    ? `M 0.00 ${points[0].y.toFixed(2)} L ${width.toFixed(2)} ${points[0].y.toFixed(2)}`
    : points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ');
  return { path, marker: points[dayIndex] ?? null, zeroY: y(0) };
}

/** D7 / financial-advisor 6: win% on fewer than five rows is noise. */
export function breakdownWinRate(row: DayBreakdownRow): string {
  if (row.n < WIN_RATE_MIN_N || row.win_rate === null) return ABSENT;
  return `${row.win_rate.toFixed(0)}%`;
}

const TABS: Tab[] = [
  { id: 'strategy', label: 'Strategy' },
  { id: 'horizon', label: 'Horizon' },
  { id: 'direction', label: 'Direction' },
  { id: 'exit_reason', label: 'Exit' },
];

const SORTS: SegmentOption[] = [
  { value: 'pnl', label: 'P&L' },
  { value: 'r', label: 'R' },
  { value: 'closed', label: 'Close time' },
  { value: 'ticker', label: 'Ticker' },
];

function sign(value: number | null): 'pos' | 'neg' | null {
  if (value === null || value === 0) return null;
  return value > 0 ? 'pos' : 'neg';
}

@Component({
  selector: 'sb-calendar-day',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DayTradeCard, EmptyStateComponent, Panel, RouterLink, Segmented, StatTile, TabBar],
  host: { class: 'register-presentation' },
  template: `
    <header class="day-head">
      <a class="back" [routerLink]="['/calendar']" [queryParams]="backParams()">← Calendar{{ backMonth() }}</a>
      <h2 class="long-date">{{ title() }}</h2>
      <nav class="steps" aria-label="Trading days">
        @if (store.prevDay(); as prev) {
          <a class="prev" [routerLink]="['/calendar', prev]" [queryParams]="store.filterParams()">‹ prev day</a>
        } @else {
          <span class="prev off">‹ prev day</span>
        }
        @if (store.nextDay(); as next) {
          <a class="next" [routerLink]="['/calendar', next]" [queryParams]="store.filterParams()">next day ›</a>
        } @else {
          <span class="next off">next day ›</span>
        }
      </nav>
    </header>
    <p class="caption">{{ caption }}</p>
    @if (store.error(); as message) {
      <p class="stale" role="status">{{ message }}</p>
    }

    @if (store.day(); as day) {
      <div class="tiles">
        <sb-stat-tile label="Total" [value]="r(day.total_r)" [sample]="day.trade_count" [attr.title]="rTooltip" />
        <sb-stat-tile label="Total P&L" [value]="ccy(day.total_ccy)" [sample]="day.trade_count" />
        <sb-stat-tile label="Win rate" [value]="winRate(day.win_rate)" [sample]="day.trade_count" />
        <sb-stat-tile label="Winners" [value]="day.winners.toString()" [sample]="day.trade_count" tone="pos" />
        <sb-stat-tile label="Losers" [value]="day.losers.toString()" [sample]="day.trade_count" tone="neg" />
        <sb-stat-tile label="Average trade" [value]="r(day.avg_trade_r)" [sample]="day.trade_count" [attr.title]="rTooltip" />
        <sb-stat-tile label="Worst drawdown" [value]="r(day.worst_drawdown_r)" [sample]="day.trade_count" tone="neg" [attr.title]="rTooltip" />
      </div>
      @if (store.hasLegs()) {
        <p class="sample-note">{{ legsNote(day.trade_count) }}</p>
      }

      <div class="panels">
        <sb-panel heading="How this day compares">
          <dl class="compare">
            <div><dt>Among trading days</dt><dd class="percentile">{{ percentile(day.context) }}</dd></div>
            <div><dt>In the month</dt><dd class="rank">{{ rankText() }}</dd></div>
            <div><dt>vs average day</dt><dd class="vs-day">{{ delta(day.context.vs_avg_day) }}</dd></div>
            <div><dt class="vs-weekday-label">vs average {{ weekday() }}</dt><dd class="vs-weekday">{{ delta(day.context.vs_weekday_avg) }}</dd></div>
          </dl>
          <p class="caveat">{{ caveat }}</p>
        </sb-panel>
        <sb-panel heading="Month so far" class="month-panel">
          @if (monthLine(); as line) {
            <svg class="month-line" viewBox="0 0 240 56" width="100%" height="56" preserveAspectRatio="none" aria-hidden="true">
              @if (line.zeroY !== null) {
                <line class="zero" x1="0" x2="240" [attr.y1]="line.zeroY" [attr.y2]="line.zeroY" />
              }
              <path class="curve" [attr.d]="line.path" />
              @if (line.marker; as m) {
                <circle class="marker" r="3" [attr.cx]="m.x" [attr.cy]="m.y" />
              }
            </svg>
          }
          <p class="mtd">
            Month to date
            <span class="mtd-pnl" [class.pos]="mtdSign() === 'pos'" [class.neg]="mtdSign() === 'neg'">{{ ccy(store.monthCtx()?.mtdPnl ?? null) }}</span>
            ·
            <span class="mtd-r" [title]="rTooltip">{{ r(store.monthCtx()?.mtdR ?? null) }}</span>
          </p>
          <p class="rank">{{ rankText() }}</p>
        </sb-panel>
      </div>

      <sb-panel heading="What drove it">
        <sb-tab-bar [tabs]="tabs" [active]="dimension()" (activeChange)="setDimension($event)" />
        <table class="breakdown">
          <thead>
            <tr>
              <th>{{ dimensionLabel() }}</th>
              <th class="num">n</th>
              <th class="num">P&amp;L</th>
              <th class="num r-head" [title]="rTooltip">R</th>
              <th class="num">Win %</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            @for (row of breakdownRows(); track row.key) {
              <tr class="breakdown-row">
                <th scope="row" class="key">{{ row.key }}</th>
                <td class="num">{{ row.n }}</td>
                <td class="num" [class.pos]="signOf(row.pnl_amount) === 'pos'" [class.neg]="signOf(row.pnl_amount) === 'neg'">{{ ccy(row.pnl_amount) }}</td>
                <td class="num" [class.pos]="signOf(row.r) === 'pos'" [class.neg]="signOf(row.r) === 'neg'">{{ r(row.r) }}</td>
                <td class="num win" [class.withheld]="breakdownWinRate(row) === absent">{{ breakdownWinRate(row) }}</td>
                <td class="bar"><span class="fill" [class.pos]="signOf(row.pnl_amount) === 'pos'" [class.neg]="signOf(row.pnl_amount) === 'neg'" [style.width.%]="barWidth(row)"></span></td>
              </tr>
            }
          </tbody>
        </table>
      </sb-panel>

      <sb-panel [heading]="'Trades (' + day.trade_count + ')'" class="trades-panel">
        <sb-segmented panel-actions label="Sort trades" [options]="sorts" [value]="store.sort()" (valueChange)="setSort($event)" />
        @for (trade of store.trades(); track trade.trade_id + ':' + trade.leg_index) {
          <sb-day-trade-card [trade]="trade" [series]="seriesFor(trade)" />
        }
      </sb-panel>
    } @else if (store.empty()) {
      <sb-empty-state [title]="emptyTitle()" hint="Step to a neighbouring trading day, or widen the filters." />
    } @else if (store.loading()) {
      <p class="day-loading">Loading...</p>
    }
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }
    .day-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-14); }
    .back { color: var(--text-secondary); text-decoration: none; }
    .back:hover, .back:focus-visible { color: var(--text); text-decoration: underline; }
    .long-date { margin: 0; font-size: var(--text-h2, 1.25rem); font-weight: 600; }
    .steps { display: inline-flex; gap: var(--space-14); margin-left: auto; }
    .steps a { color: var(--accent); text-decoration: none; }
    .steps .off { color: var(--text-faint); }
    .caption, .sample-note, .caveat { margin: 0; color: var(--text-secondary); font-size: var(--text-table); }
    .stale { margin: 0; color: var(--warn); font-size: var(--text-table); }
    .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--space-8); }
    .panels { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-14); }
    @media (max-width: 639px) { .panels { grid-template-columns: minmax(0, 1fr); } }
    /* D7: comparison figures stay in the neutral text colour. */
    .compare { display: grid; gap: var(--space-8); margin: 0 0 var(--space-10); }
    .compare div { display: flex; justify-content: space-between; gap: var(--space-10); }
    .compare dt { color: var(--text-secondary); }
    .compare dd { margin: 0; color: var(--text); font-family: var(--font-mono); text-align: right; }
    .month-line { display: block; margin-bottom: var(--space-8); }
    .month-line .zero { stroke: var(--border-strong); stroke-dasharray: 2 2; }
    .month-line .curve { fill: none; stroke: var(--text-secondary); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
    .month-line .marker { fill: var(--accent); }
    .mtd, .month-panel .rank { margin: var(--space-4) 0 0; font-size: var(--text-table); }
    .mtd span { font-family: var(--font-mono); }
    .pos { color: var(--pos); }
    .neg { color: var(--neg); }
    .breakdown { width: 100%; margin-top: var(--space-10); border-collapse: collapse; font-size: var(--text-table); }
    .breakdown th, .breakdown td { padding: var(--space-4) var(--space-6); text-align: left; }
    .breakdown .num { text-align: right; font-family: var(--font-mono); }
    .breakdown .r-head { cursor: help; }
    .breakdown .win.withheld { color: var(--text-faint); }
    .breakdown .bar { width: 30%; }
    .breakdown .fill { display: block; height: 8px; border-radius: 2px; background: var(--text-faint); }
    .breakdown .fill.pos { background: var(--pos); }
    .breakdown .fill.neg { background: var(--neg); }
    .day-loading { margin: 0; color: var(--text-secondary); }
  `,
})
export class CalendarDayPage {
  readonly store = inject(CalendarDayStore);
  private readonly connection = inject(ConnectionStore);

  /** The raw `:date` param, kept for the empty-state wording. */
  readonly date = input<string>();

  protected readonly caption = PAPER_CAPTION;
  protected readonly caveat = ONE_DAY_CAVEAT;
  protected readonly rTooltip = R_TOOLTIP;
  protected readonly absent = ABSENT;
  protected readonly tabs = TABS;
  protected readonly sorts = SORTS;
  protected readonly breakdownWinRate = breakdownWinRate;
  protected readonly legsNote = legsSampleNote;
  protected readonly signOf = sign;

  protected readonly dimension = signal<DayBreakdownDimension>('strategy');

  protected readonly title = computed(() => {
    const date = this.store.date();
    return date ? longDate(date) : (this.date() ?? '');
  });
  protected readonly weekday = computed(() => {
    const date = this.store.date();
    return date ? weekdayName(date) : 'weekday';
  });
  protected readonly monthName = computed(() => {
    const date = this.store.date();
    return date ? monthLabel(monthOf(date)) : null;
  });
  protected readonly backMonth = computed(() => (this.monthName() ? ` · ${this.monthName()}` : ''));
  protected readonly backParams = computed(() => {
    const date = this.store.date();
    return { ...(date ? { month: monthOf(date) } : {}), ...this.store.filterParams() };
  });
  protected readonly emptyTitle = computed(
    () => `No closed trades on ${this.date() ?? ''} under this filter`,
  );

  protected readonly rankText = computed(() => {
    const ctx = this.store.monthCtx();
    if (!ctx || ctx.rank === null) return ABSENT;
    return `${ordinal(ctx.rank)} best of ${ctx.rankOf} days in ${this.monthName()}`;
  });
  protected readonly monthLine = computed(() => {
    const ctx = this.store.monthCtx();
    return ctx && ctx.curve.length ? monthLineGeometry(ctx.curve, ctx.dayIndex) : null;
  });
  protected readonly mtdSign = computed(() => sign(this.store.monthCtx()?.mtdPnl ?? null));

  protected readonly dimensionLabel = computed(
    () => TABS.find((tab) => tab.id === this.dimension())?.label ?? '',
  );
  protected readonly breakdownRows = computed<DayBreakdownRow[]>(
    () => this.store.day()?.breakdown[this.dimension()] ?? [],
  );
  private readonly maxAbsPnl = computed(() =>
    Math.max(0, ...this.breakdownRows().map((row) => Math.abs(row.pnl_amount ?? 0))),
  );

  protected setDimension(id: string): void {
    this.dimension.set(id as DayBreakdownDimension);
  }

  protected setSort(value: string): void {
    this.store.setSort(value as DaySort);
  }

  protected barWidth(row: DayBreakdownRow): number {
    const max = this.maxAbsPnl();
    return max === 0 || row.pnl_amount === null ? 0 : (Math.abs(row.pnl_amount) / max) * 100;
  }

  protected seriesFor(trade: CalendarTrade): SparkSeries | null | undefined {
    return this.store.sparklines()?.series[`${trade.trade_id}:${trade.leg_index}`];
  }

  protected percentile(context: DayContext): string {
    return percentileView(context.percentile, context.history_days).text;
  }

  /** Neutral text by design (D7): the sign is in the figure, not a colour. */
  protected delta(value: DayDelta): string {
    if (value.pnl_amount === null && value.r === null) return ABSENT;
    return `${this.ccy(value.pnl_amount)} · ${this.r(value.r)}`;
  }

  protected ccy(value: number | null): string {
    return money(value, this.connection.currency(), 2);
  }

  protected r(value: number | null): string {
    return rMultiple(value);
  }

  protected winRate(value: number | null): string {
    return value === null ? ABSENT : `${value.toFixed(0)}%`;
  }
}
```

- [ ] **Step 4: Add the route**

Replace the whole of `frontend/src/app/workspaces/calendar/calendar.routes.ts` with (the `''` route is unchanged except `pathMatch: 'full'`, which keeps it from swallowing `/calendar/<date>`):

```ts
import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { map } from 'rxjs';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { CalendarDayStore } from '../../stores/calendar-day.store';
import { CalendarStore } from '../../stores/calendar.store';

export const calendarRoutes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    providers: [CalendarStore],
    runGuardsAndResolvers: 'always',
    data: routeData('Calendar', onEvents('trades')),
    resolve: { ready: resolveRoute(() => inject(CalendarStore).resolve()) },
    loadComponent: () => import('./calendar').then((m) => m.Calendar),
  },
  {
    // v165 D5: one day as a page. `:date` and the strategy/horizon query
    // params are the whole state; a malformed date resolves to the empty
    // state without a request (CalendarDayStore.setRoute).
    path: ':date',
    providers: [CalendarDayStore],
    runGuardsAndResolvers: 'always',
    data: routeData('Calendar day', onEvents('trades')),
    resolve: {
      ready: resolveRoute((route) => {
        const store = inject(CalendarDayStore);
        store.setRoute(
          route.paramMap.get('date'),
          route.queryParamMap.get('strategy'),
          route.queryParamMap.get('horizon'),
        );
        return store.resolve().pipe(map(() => undefined));
      }),
    },
    loadComponent: () => import('./day/calendar-day').then((m) => m.CalendarDayPage),
  },
];
```

- [ ] **Step 5: Run the day spec and the routing spec to verify they pass**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/workspaces/calendar/day/calendar-day.spec.ts' --include='src/app/app.routes.spec.ts'`
Expected: PASS — every `calendar-day.spec.ts` test, and `app.routes.spec.ts`'s "serves the calendar workspace behind the auth guard" still green (child 0 is still the list route). If `--include` is rejected, run `npm --prefix $WT/frontend run test -- --watch=false`, expected PASS.

If the harness test "hands the date and the filters ..." times out waiting for a request, the resolver did not run: check that `PreferencesStore` is the stub in `configure()` (the real one would first ask `/api/v1/preferences`).

- [ ] **Step 6: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/calendar/day/calendar-day.ts frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts frontend/src/app/workspaces/calendar/calendar.routes.ts
git -C $WT commit -m "feat(calendar-ui): calendar day page at /calendar/:date -- tiles, comparison, breakdown, trade cards

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the last command lists none of this task's files.

### Task CD13: Drawer "Open full day" button, D7 caption in the drawer, calendar month/filters in the URL

**Model:** sonnet — store and component edits inside one workspace

**Files:**
- Modify: `frontend/src/app/stores/calendar.store.ts` (imports; `CalendarUrlParams`, `urlState`; `withMethods` gains `router`, `writeUrl`, `matchesUrl`, `applyUrl`; the four setters write the URL)
- Modify: `frontend/src/app/workspaces/calendar/calendar.routes.ts` (the `''` route's `resolve` only)
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts` (imports; drawer template; three class members)
- Modify: `frontend/src/app/workspaces/calendar/calendar.spec.ts` (new tests in the drawer `describe`; a new `describe` at the end)
- Modify: `frontend/src/app/stores/calendar.store.spec.ts` (`provideRouter([])`; new tests)

**Interfaces:**
- Consumes: CD12's `calendarRoutes` (two children, `''` with `pathMatch: 'full'`, then `':date'`); CD8 `PAPER_CAPTION`, `legsSampleNote` (`day/day-copy.ts`); CD7's `openDay` flush body in `calendar.spec.ts` (already carries `context`/`breakdown`); existing `BACKGROUND_REFRESH_INFO` (`frontend/src/app/routing/route-loading.service.ts:15`, `{ backgroundRefresh: true }`), `RouteRefreshService` (navigates `router.url` with `info: BACKGROUND_REFRESH_INFO` on a `trades` event), `Router.currentNavigation()` (Angular 21 signal; `route-loading.service.ts:41` reads it the same way).
- Produces: `export interface CalendarUrlParams {month: string | null; strategy: string | null; horizon: string | null}`; `CalendarStore.applyUrl(params: CalendarUrlParams): void` (ledger); `CalendarStore.matchesUrl(params: CalendarUrlParams): boolean` (used only by the route in this task); `setMonth`/`stepMonth`/`setStrategy`/`setHorizon` now also write `month`, `strategy`, `horizon` to the current URL with `replaceUrl: true`.

**Design (controller decision on the index's open point 2 — store-driven, not resolver-driven):**
- The store initialises **once** from the route's query params, in the `''` route's resolver (`applyUrl` then `resolve()`), and writes every change back itself: `router.navigate([], { queryParams: { month, strategy: strategy || null, horizon: horizon || null }, queryParamsHandling: 'merge', replaceUrl: true })`. `merge` drops a `null` key, so "any strategy" leaves no `strategy=` behind.
- That write is a navigation, and the route has `runGuardsAndResolvers: 'always'` (needed so `RouteRefreshService`'s same-URL reload re-runs the resolver). So the resolver is a **no-op when the URL already equals store state** (`matchesUrl`) and the store has data — the setter has already made the one request. A background refresh (`currentNavigation().extras.info.backgroundRefresh`), a first visit (`data() === null`) and a hand-edited or back-button URL (state differs) still load. **One API call per filter change**, pinned by a spec through the real route.
- `urlState`: an absent or malformed `month` (anything but `YYYY-MM`, month 01–12) is the current month; absent filters are `''` ("any"). `applyUrl` with an equal state changes nothing (an open drawer stays open); with a different state it patches month and filters and clears the selected day, like the setters.
- Drawer (D6, D7): an **Open full day →** link to `/calendar/<selectedDay>` carrying only the set filters, shown whenever a day is selected (also on an empty day — the page's prev/next still help); `PAPER_CAPTION` at the top of the drawer summary; `legsSampleNote(trade_count)` under the drawer tiles when any row has `leg_total > 1`.

- [ ] **Step 1: Write the failing store tests**

In `frontend/src/app/stores/calendar.store.spec.ts`:

1. Change the vitest import to `import { beforeEach, describe, expect, it, vi } from 'vitest';` and add `import { Router, provideRouter } from '@angular/router';` after the `@angular/core/testing` import.
2. Add `provideRouter([]),` to the `providers` array, directly after `provideZonelessChangeDetection(),` (the store now injects `Router`).
3. Add these tests as the last tests inside `describe('CalendarStore', ...)`:

```ts
  it('applyUrl takes month and filters from the URL without a request', () => {
    tick();
    respond();

    store.applyUrl({ month: '2026-03', strategy: 'VWAP', horizon: null });
    expect(store.month()).toBe('2026-03');
    expect(store.strategy()).toBe('VWAP');
    expect(store.horizon()).toBe('');
    backend.expectNone((r) => r.url === '/api/v1/calendar/pnl');
  });

  it('matchesUrl reads absent and malformed params as the defaults', () => {
    tick();
    respond();

    const month = store.month();               // the current month on a fresh store
    expect(store.matchesUrl({ month: null, strategy: null, horizon: null })).toBe(true);
    expect(store.matchesUrl({ month, strategy: null, horizon: null })).toBe(true);
    expect(store.matchesUrl({ month: '2026-13', strategy: null, horizon: null })).toBe(true);
    expect(store.matchesUrl({ month: 'abc', strategy: null, horizon: null })).toBe(true);
    expect(store.matchesUrl({ month: '1999-01', strategy: null, horizon: null })).toBe(false);
    expect(store.matchesUrl({ month, strategy: 'EMA20', horizon: null })).toBe(false);
  });

  it('applyUrl with the state it already has leaves the open day alone', () => {
    tick();
    respond();
    store.selectDay('2026-08-03');
    backend.expectOne((r) => r.url === '/api/v1/calendar/pnl/day').flush({ date: '2026-08-03', trades: [] });

    store.applyUrl({ month: store.month(), strategy: null, horizon: null });
    expect(store.selectedDay()).toBe('2026-08-03');

    store.applyUrl({ month: '2026-01', strategy: null, horizon: null });
    expect(store.selectedDay()).toBeNull();
  });

  it('every setter writes month and filters to the URL, replacing history', () => {
    tick();
    respond();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);

    store.setMonth('2026-08');
    backend.expectOne((r) => r.params.get('month') === '2026-08').flush(RESPONSE);
    store.setStrategy('EMA20');
    backend.expectOne((r) => r.params.get('strategy') === 'EMA20').flush(RESPONSE);
    store.setHorizon('4w');
    backend.expectOne((r) => r.params.get('horizon') === '4w').flush(RESPONSE);
    store.stepMonth(1);
    backend.expectOne((r) => r.params.get('month') === '2026-09').flush(RESPONSE);

    expect(navigate).toHaveBeenCalledTimes(4);
    expect(navigate).toHaveBeenLastCalledWith([], {
      queryParams: { month: '2026-09', strategy: 'EMA20', horizon: '4w' },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
    store.setStrategy('');
    backend.expectOne((r) => r.url === '/api/v1/calendar/pnl').flush(RESPONSE);
    // "Any strategy" is a null, which `merge` drops from the URL.
    expect(navigate).toHaveBeenLastCalledWith([], expect.objectContaining({
      queryParams: { month: '2026-09', strategy: null, horizon: '4w' },
    }));
  });
```

- [ ] **Step 2: Write the failing drawer and URL tests**

In `frontend/src/app/workspaces/calendar/calendar.spec.ts`:

1. Replace the import block at the top (lines 1–19 before CD7; the imports only, up to and including the `CalendarStore` import) with:

```ts
import { HttpRequest, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideLocationMocks } from '@angular/common/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { Router, provideRouter, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { of } from 'rxjs';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { CalendarTrade, PnlCalendar } from '../../api/models';
import { BACKGROUND_REFRESH_INFO } from '../../routing/route-loading.service';
import { PreferencesStore } from '../../stores/preferences.store';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { Calendar } from './calendar';
import { calendarRoutes } from './calendar.routes';
import { CalendarStore } from '../../stores/calendar.store';
import { PAPER_CAPTION } from './day/day-copy';
```

2. Add these tests as the last tests inside `describe('Calendar day drawer', ...)` (after `'stays closed until a day is chosen'`):

```ts
  it('offers the full day page, carrying the active filters', async () => {
    const fixture = seed();
    fixture.componentInstance.store.setStrategy('EMA20');
    TestBed.inject(HttpTestingController)
      .expectOne((r) => r.params.get('strategy') === 'EMA20')
      .flush(RESPONSE);
    await openDay(fixture, [TRADE]);

    const link = el(fixture).querySelector('a.open-day');
    expect(link?.textContent?.trim()).toBe('Open full day →');
    expect(link?.getAttribute('href')).toBe('/calendar/2026-08-03?strategy=EMA20');
  });

  it('links the bare day when no filter is set, even on an empty day', async () => {
    const fixture = seed();
    await openDay(fixture, []);
    expect(el(fixture).querySelector('a.open-day')?.getAttribute('href')).toBe('/calendar/2026-08-03');
  });

  it('captions the drawer summary as paper, before costs', async () => {
    const fixture = seed();
    await openDay(fixture, [TRADE]);
    expect(el(fixture).querySelector('.day-caption')?.textContent?.trim()).toBe(PAPER_CAPTION);
  });

  it('says once that scale-out legs count separately', async () => {
    const fixture = seed();
    await openDay(fixture, [
      { ...TRADE, leg_index: 0, leg_total: 2 },
      { ...TRADE, leg_index: 1, leg_total: 2 },
    ]);
    expect(el(fixture).querySelector('.day-sample-note')?.textContent?.trim())
      .toBe('2 rows · scale-out legs count separately');

    const whole = seed();
    await openDay(whole, [TRADE]);
    expect(el(whole).querySelector('.day-sample-note')).toBeNull();
  });
```

3. Append this `describe` at the end of the file:

```ts
describe('Calendar URL (v165 D6)', () => {
  const MONTH_URL = '/api/v1/calendar/pnl';

  function mount(): void {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: 'calendar', children: calendarRoutes }], withComponentInputBinding()),
        provideLocationMocks(),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
        // The real one would first ask /api/v1/preferences inside resolveRoute.
        { provide: PreferencesStore, useValue: {
          resolve: () => of(undefined), values: () => ({}), update: () => undefined,
        } },
      ],
    });
  }

  const settle = async () => {
    for (let i = 0; i < 10; i++) await new Promise((resolve) => setTimeout(resolve, 0));
  };

  async function take(predicate: (r: HttpRequest<unknown>) => boolean): Promise<TestRequest> {
    const backend = TestBed.inject(HttpTestingController);
    for (let i = 0; i < 50; i++) {
      const [found] = backend.match(predicate);
      if (found) return found;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    throw new Error('the expected request was never made');
  }

  async function openAt(url: string): Promise<{ harness: RouterTestingHarness; store: InstanceType<typeof CalendarStore> }> {
    mount();
    const harness = await RouterTestingHarness.create();
    const navigation = harness.navigateByUrl(url);
    (await take((r) => r.url === MONTH_URL)).flush(RESPONSE);
    await navigation;
    const store = (harness.routeDebugElement!.componentInstance as Calendar).store;
    return { harness, store };
  }

  it('restores the month and the filters from the URL in its first request', async () => {
    mount();
    const harness = await RouterTestingHarness.create();
    const navigation = harness.navigateByUrl('/calendar?month=2026-08&strategy=EMA20');
    const first = await take((r) => r.url === MONTH_URL);
    expect(first.request.params.get('month')).toBe('2026-08');
    expect(first.request.params.get('strategy')).toBe('EMA20');
    expect(first.request.params.has('horizon')).toBe(false);
    first.flush(RESPONSE);
    await navigation;

    const store = (harness.routeDebugElement!.componentInstance as Calendar).store;
    expect([store.month(), store.strategy(), store.horizon()]).toEqual(['2026-08', 'EMA20', '']);
  });

  it('makes exactly one request per filter change and writes it to the URL', async () => {
    const { store } = await openAt('/calendar?month=2026-08&strategy=EMA20');
    const backend = TestBed.inject(HttpTestingController);

    store.setHorizon('4w');
    await settle();
    const calls = backend.match((r) => r.url === MONTH_URL);
    expect(calls).toHaveLength(1);
    expect(calls[0].request.params.get('horizon')).toBe('4w');
    calls[0].flush(RESPONSE);

    await settle();
    backend.expectNone((r) => r.url === MONTH_URL);       // the URL write did not reload
    const url = TestBed.inject(Router).url;
    expect(url.startsWith('/calendar?')).toBe(true);
    expect(url).toContain('month=2026-08');
    expect(url).toContain('strategy=EMA20');
    expect(url).toContain('horizon=4w');

    store.stepMonth(-1);
    await settle();
    const stepped = backend.match((r) => r.url === MONTH_URL);
    expect(stepped).toHaveLength(1);
    expect(stepped[0].request.params.get('month')).toBe('2026-07');
    stepped[0].flush(RESPONSE);
    await settle();
    expect(TestBed.inject(Router).url).toContain('month=2026-07');
  });

  it('still reloads on a background refresh of the same URL', async () => {
    await openAt('/calendar?month=2026-08');
    const router = TestBed.inject(Router);
    void router.navigateByUrl(router.url, {
      onSameUrlNavigation: 'reload', replaceUrl: true, info: BACKGROUND_REFRESH_INFO,
    });
    const refresh = await take((r) => r.url === MONTH_URL);
    expect(refresh.request.params.get('month')).toBe('2026-08');
    refresh.flush(RESPONSE);
  });

  it('loads a URL edited by hand, filters it does not name included', async () => {
    const { harness, store } = await openAt('/calendar?month=2026-08&strategy=EMA20');
    const navigation = harness.navigateByUrl('/calendar?month=2026-07');
    const edited = await take((r) => r.url === MONTH_URL);
    expect(edited.request.params.get('month')).toBe('2026-07');
    expect(edited.request.params.has('strategy')).toBe(false);
    edited.flush(RESPONSE);
    await navigation;
    expect([store.month(), store.strategy()]).toEqual(['2026-07', '']);
  });
});
```

- [ ] **Step 3: Run both specs to verify they fail**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/stores/calendar.store.spec.ts' --include='src/app/workspaces/calendar/calendar.spec.ts'`
Expected: FAIL — `Property 'applyUrl' does not exist` / `'matchesUrl' does not exist` at compile; once those compile, the drawer tests fail on a missing `a.open-day`, `.day-caption`, `.day-sample-note`, and the URL tests on two requests per filter change and a URL without `horizon=4w`.

- [ ] **Step 4: Teach the store the URL**

In `frontend/src/app/stores/calendar.store.ts`:

1. Add `import { Router } from '@angular/router';` after the `@ngrx/signals` import.
2. Directly after `export function shiftMonth(...) { ... }`, add:

```ts
/** The calendar's URL state (v165 D6). `null` = absent from the query string. */
export interface CalendarUrlParams {
  month: string | null;
  strategy: string | null;
  horizon: string | null;
}

const MONTH_PARAM = /^\d{4}-(0[1-9]|1[0-2])$/;

/** The store state a URL stands for: an absent or malformed month is the
 *  current month (what a bare `/calendar` has always shown), absent filters
 *  are "any". */
function urlState(params: CalendarUrlParams): { month: string; strategy: string; horizon: string } {
  return {
    month: params.month !== null && MONTH_PARAM.test(params.month) ? params.month : currentMonth(),
    strategy: params.strategy ?? '',
    horizon: params.horizon ?? '',
  };
}
```

3. Change the `withMethods` signature to inject the router:

```ts
  withMethods((store, api = inject(ApiClient), preferences = inject(PreferencesStore), router = inject(Router)) => {
```

4. Directly after the `const load = (): void => { ... };` block, add:

```ts
    /** v165 D6: the month and filters live in the URL, so a filtered month is
     *  a link and the day page's back link lands on it. The store has already
     *  loaded for this state; the route's resolver sees URL == state and does
     *  nothing (see calendar.routes.ts), so this costs no second request. */
    const writeUrl = (): void => {
      void router.navigate([], {
        queryParams: {
          month: store.month(),
          strategy: store.strategy() || null,
          horizon: store.horizon() || null,
        },
        queryParamsHandling: 'merge',
        replaceUrl: true,
      });
    };

    const matchesUrl = (params: CalendarUrlParams): boolean => {
      const next = urlState(params);
      return next.month === store.month()
        && next.strategy === store.strategy()
        && next.horizon === store.horizon();
    };
```

5. In the returned object, add `matchesUrl,` after `load,`, add `writeUrl();` as the last line of each of `setMonth`, `stepMonth`, `setStrategy` and `setHorizon` (after their `load();`), and add this method directly after `setHorizon`:

```ts
      /** From the route, never a request: the resolver loads afterwards. An
       *  equal state changes nothing, so an open drawer survives a no-op. */
      applyUrl(params: CalendarUrlParams): void {
        if (matchesUrl(params)) return;
        patchState(store, {
          ...urlState(params),
          selectedDay: null,
          dayDetail: null,
          dayTrades: null,
        });
      },
```

- [ ] **Step 5: Make the list route's resolver store-driven**

In `frontend/src/app/workspaces/calendar/calendar.routes.ts` (as left by CD12):

1. Replace the import block with this one, followed by the two helpers (both sit between the imports and `export const calendarRoutes`):

```ts
import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Router, Routes } from '@angular/router';
import { map, of } from 'rxjs';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { CalendarDayStore } from '../../stores/calendar-day.store';
import { CalendarStore, CalendarUrlParams } from '../../stores/calendar.store';

const listParams = (route: ActivatedRouteSnapshot): CalendarUrlParams => ({
  month: route.queryParamMap.get('month'),
  strategy: route.queryParamMap.get('strategy'),
  horizon: route.queryParamMap.get('horizon'),
});

/** RouteRefreshService's same-URL reload after a `trades` event. */
const isBackgroundRefresh = (): boolean => {
  const info = inject(Router).currentNavigation()?.extras.info as { backgroundRefresh?: boolean } | undefined;
  return info?.backgroundRefresh === true;
};
```

2. Replace the `''` route's `resolve` line with:

```ts
    // v165 D6, store-driven: the store reads the URL once here and writes
    // every change back itself (replaceUrl) after making the one request for
    // it. That write is a navigation and this route runs its resolver
    // 'always', so URL == state with data loaded is a no-op -- one request
    // per filter change. A first visit, a hand-edited URL, back/forward and
    // a background refresh still load.
    resolve: {
      ready: resolveRoute((route) => {
        const store = inject(CalendarStore);
        const params = listParams(route);
        if (store.data() !== null && store.matchesUrl(params) && !isBackgroundRefresh()) {
          return of(undefined);
        }
        store.applyUrl(params);
        return store.resolve();
      }),
    },
```

The `':date'` route and its `map` import stay as CD12 wrote them.

- [ ] **Step 6: Add the drawer link, caption and legs line**

In `frontend/src/app/workspaces/calendar/calendar.ts`:

1. Add after the `./calendar.helpers` import:

```ts
import { PAPER_CAPTION, legsSampleNote } from './day/day-copy';
```

2. In the drawer template, insert directly after the opening `<sb-drawer ...>` tag (before `@if (store.dayLoading())`):

```html
      @if (store.selectedDay(); as day) {
        <!-- v165 D6: the drawer is the quick preview; the page is the full day. -->
        <a class="open-day" [routerLink]="['/calendar', day]" [queryParams]="dayLinkParams()">Open full day →</a>
      }
```

3. In the `@else if (store.dayDetail(); as detail)` branch, insert directly before `<div class="day-summary">`:

```html
        <p class="day-caption">{{ paperCaption }}</p>
```

and directly after that `day-summary` `</div>`:

```html
        @if (hasLegs(detail.trades)) {
          <p class="day-sample-note">{{ legsNote(detail.trade_count) }}</p>
        }
```

4. Add to the `styles` block, after the `.day-summary` rule:

```css
    .open-day { display: inline-block; margin-bottom: var(--space-10); color: var(--accent); font-weight: 600; text-decoration: none; }
    .open-day:hover, .open-day:focus-visible { text-decoration: underline; }
    .day-caption, .day-sample-note { margin: 0 0 var(--space-8); color: var(--text-secondary); font-size: var(--text-micro); }
```

5. Add these members to the `Calendar` class, directly after `protected readonly dateTime = dateTime;`:

```ts
  /** D7: the drawer's summary says what these figures are. */
  protected readonly paperCaption = PAPER_CAPTION;
  protected readonly legsNote = legsSampleNote;

  /** Only the filters that are set, so a bare day links as `/calendar/<date>`. */
  protected readonly dayLinkParams = computed(() => ({
    ...(this.store.strategy() ? { strategy: this.store.strategy() } : {}),
    ...(this.store.horizon() ? { horizon: this.store.horizon() } : {}),
  }));

  protected hasLegs(trades: CalendarTrade[]): boolean {
    return trades.some((trade) => trade.leg_total > 1);
  }
```

- [ ] **Step 7: Run both specs, then the routing and day specs, to verify they pass**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/stores/calendar.store.spec.ts' --include='src/app/workspaces/calendar/**/*.spec.ts' --include='src/app/app.routes.spec.ts'`
Expected: PASS — every existing calendar, store and routing test plus the new ones. If `--include` is rejected, run `npm --prefix $WT/frontend run test -- --watch=false`, expected PASS.

If "makes exactly one request per filter change" sees **two** requests, the resolver is not short-circuiting: check that `writeUrl()` runs **after** `patchState` in the setter (so `matchesUrl` already sees the new state) and that `matchesUrl` is in the store's returned object.

- [ ] **Step 8: Commit**

```bash
git -C $WT add frontend/src/app/stores/calendar.store.ts frontend/src/app/stores/calendar.store.spec.ts frontend/src/app/workspaces/calendar/calendar.routes.ts frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts
git -C $WT commit -m "feat(calendar-ui): drawer opens the full day; calendar month and filters live in the URL

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the last command lists none of this task's files.


### Task CD14: Full Python suite, whole frontend spec run, radon check

**Model:** haiku — runs commands, no code

**Files:** none (verification only; a failure is fixed in the task that owns the file, then re-run alone).

**Interfaces:** consumes every commit of CD1..CD13 on the branch `2026-10-15-v165-calendar-day-page` in `$WT`; produces the recorded results below.

- [ ] **Step 1: Confirm everything is committed**

```bash
git -C $WT status --short
git -C $WT log --oneline main..HEAD
```

Expected: `status` prints nothing; `log` lists the CD1..CD13 commits.

- [ ] **Step 2: Full Python suite (dispatch the `test-runner` agent, never inline)**

Dispatch `test-runner` with: "Run `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py full` and return only the verdict line and any failing test ids."

Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`testing-cost.md`). A failure is fixed in its owning task's files, committed, and re-run alone with `testrun.py file <path>` — never by re-running the full suite.

- [ ] **Step 3: Whole frontend spec run**

```bash
npm --prefix $WT/frontend run test -- --watch=false
```

Expected: every spec passes. A `Timeout waiting for worker` is the known flake: re-run once; a second timeout is a real failure.

- [ ] **Step 4: Complexity check on every Python file the plan touched**

```bash
python -m radon cc -s -n C $WT/swingbot/core/analytics/pnl_calendar.py $WT/swingbot/core/analytics/day_sparklines.py $WT/swingbot/core/analytics/metrics.py $WT/swingbot/admin/api_v1/calendar.py
```

Expected: no function this plan wrote or changed is listed (all < 15); in particular `calendar_pnl_day` no longer appears (it was D(22) before CD5). A legacy function listed here that this plan did not touch is not a failure, but must be no worse than on `main` (`git -C $WT diff main -- <file>` shows it untouched).

- [ ] **Step 5: Record results**

Append to `.superpowers/sdd/progress.md` in `$R`: the Python verdict line, the frontend spec count, the radon output (or "clean"), and the branch HEAD. Then the controller runs `/panel staff-engineer,financial-advisor,quant-engineer main...2026-10-15-v165-calendar-day-page` (pre-close-out) before merge and `/close-out`.
