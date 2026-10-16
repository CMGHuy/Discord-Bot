# v165 P&L calendar day page. Implementation Plan, part 3: sparkline and trade card (CD10..CD11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task CD11:" -A 400 docs/superpowers/plans/2026-10-15-v165-calendar-day-page_3*.md`. CD12..CD14 continue in `2026-10-15-v165-calendar-day-page_3b-day-page-drawer-url.md` (split off only to keep every file under 1500 lines).

**Spec:** [`docs/superpowers/specs/2026-10-15-v165-calendar-day-page-design.md`](../specs/2026-10-15-v165-calendar-day-page-design.md) (D5 layout, D6 drawer and URL, D7 copy, Testing)
**Index:** [`2026-10-15-v165-calendar-day-page_0-index.md`](2026-10-15-v165-calendar-day-page_0-index.md) — Global Constraints, Review Focus, `## Parallelisation`, the task ledger and `## Where to work` (`$WT` = the worktree, `$R` = the main tree; never `cd`, use absolute paths).

Order inside this part: CD10 after CD7; CD11 after CD10 and CD8; CD12 after CD9 and CD11; CD13 after CD12 and CD7; CD14 last, after everything is committed.

Frontend runs (from the index): `npm --prefix $WT/frontend run test -- --watch=false --include='<spec glob>'`; if the builder rejects `--include`, run `npm --prefix $WT/frontend run test -- --watch=false` (the whole frontend suite). A `Timeout waiting for worker` is a known flake: re-run once.

Names this part consumes from earlier parts (do not redefine them):
- CD7, `frontend/src/app/api/models.ts`: `CalendarTrade` (with `entry_price, exit_price, stop_price, tp1, tp2, shares, held_hours, return_pct, exit_reason, leg_index, leg_total`), `CalendarDayTrades` (with `context: DayContext`, `breakdown: DayBreakdown`), `DayBreakdownDimension`, `DayBreakdownRow`, `SparkSeries`, `CalendarDaySparklines`, `PnlCalendar`, `CalendarDay`.
- CD8, `frontend/src/app/workspaces/calendar/day/month-context.ts`: `WIN_RATE_MIN_N`, `monthOf`, `ordinal`, `percentileView`; `day-copy.ts`: `PAPER_CAPTION`, `ONE_DAY_CAVEAT`, `R_TOOLTIP`, `FINAL_STOP_LABEL`, `legsSampleNote`.
- CD9, `frontend/src/app/stores/calendar-day.store.ts`: `CalendarDayStore` (`date, strategy, horizon, day, month, sparklines, loading, error, empty, sort`; `trades, monthCtx, prevDay, nextDay, filterParams, hasLegs`; `setRoute, resolve, setSort`), `DaySort`.

### Task CD10: `sb-trade-sparkline`: 120x32 close line, final-stop/entry/target ticks, exit dot, dimmed post-exit bars, Chart-tab link

**Model:** sonnet — one presentational component with a pure geometry helper

**Files:**
- Create: `frontend/src/app/workspaces/calendar/day/trade-sparkline.ts`
- Create: `frontend/src/app/workspaces/calendar/day/trade-sparkline.spec.ts`

**Interfaces:**
- Consumes: CD7 `SparkSeries {closes: SparkClose[]; exit_bar: number; last_bar: string; stale: boolean; entry, stop, tp1, tp2, exit: number | null; exit_date: string}` (`frontend/src/app/api/models.ts`); CD8 `FINAL_STOP_LABEL` (`./day-copy`).
- Produces (CD11 renders it): `type TickKind = 'entry' | 'stop' | 'tp1' | 'tp2'`; `interface SparkGeometry {path: string; dimmedPath: string; ticks: {kind: TickKind; y: number}[]; exitDot: {x: number; y: number} | null}`; `sparkGeometry(series: SparkSeries, width?: number, height?: number): SparkGeometry` (defaults 120, 32); component `TradeSparkline`, selector `sb-trade-sparkline`, inputs `series = input<SparkSeries | null | undefined>()`, `tradeId = input.required<string>()`.

**Rules (spec D4/D5, quant-engineer 1, 3, 4):**
- The existing `ui/sparkline.ts` draws one polyline in 100x24 with no ticks or dot; it is **not** reused or changed. This is a new component.
- One y scale over the closes **and** every non-null level (entry, stop, tp1, tp2, exit), so a tick is always inside the box; 2px vertical padding; a flat domain draws down the middle (`height / 2`).
- x is linear in bar index across the full width; a single bar sits at `width / 2` and its line is drawn flat across the box.
- `path` = bars `0..exit_bar` (solid); `dimmedPath` = bars `exit_bar..end` (the up-to-3 post-exit context bars), `''` when the exit bar is the last bar. An `exit_bar` outside `closes` draws everything solid and no dot.
- The **exit dot** sits at the recorded `exit` price on the exit bar, never at the bar's close (the close is the session close, not the fill). No dot when `exit` is `null` (all ticks nulled because entry no longer sits on the bars) or when `stale` (the exit bar is then just the cache's last bar, not the exit day).
- Ticks are emitted in the order entry, stop, tp1, tp2, skipping nulls. The stop tick's tooltip is `FINAL_STOP_LABEL` ("final stop").
- `stale: true` renders a `cache ends <last_bar>` note beside the line.
- `null` (no cached file, spot metal, empty window) and `undefined` (no answer yet, a failed sparklines call, or a row past the 50-row cap) both render `—`; there is no spinner per card (CD9: "a sparklines failure leaves `sparklines: null`, cards render `—`").
- The whole sparkline links to `/trades/<tradeId>?tab=chart` (the trade detail's Chart tab is selected by `?tab=chart`, `trade-detail.ts` `goToTab`).

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/calendar/day/trade-sparkline.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { SparkSeries } from '../../../api/models';
import { TradeSparkline, sparkGeometry } from './trade-sparkline';

/** Six bars, exit on the fourth (index 3), two dimmed context bars after it.
 *  Levels: stop 9 is the domain floor, close 13 the ceiling, so
 *  y(v) = 30 - (v - 9) / 4 * 28 and x steps by 120 / 5 = 24. */
const SERIES: SparkSeries = {
  closes: [
    { date: '2026-07-29', close: 10 },
    { date: '2026-07-30', close: 11 },
    { date: '2026-07-31', close: 12 },
    { date: '2026-08-03', close: 13 },
    { date: '2026-08-04', close: 12 },
    { date: '2026-08-05', close: 11 },
  ],
  exit_bar: 3,
  last_bar: '2026-08-28',
  stale: false,
  entry: 10,
  stop: 9,
  tp1: 13,
  tp2: null,
  exit: 12.5,
  exit_date: '2026-08-03',
};

describe('sparkGeometry', () => {
  it('draws the bars up to the exit solid and the context bars after it dimmed', () => {
    const g = sparkGeometry(SERIES);
    expect(g.path).toBe('M 0.00 23.00 L 24.00 16.00 L 48.00 9.00 L 72.00 2.00');
    expect(g.dimmedPath).toBe('M 72.00 2.00 L 96.00 9.00 L 120.00 16.00');
  });

  it('puts a tick at every recorded level, in entry, stop, tp1, tp2 order, skipping nulls', () => {
    expect(sparkGeometry(SERIES).ticks).toEqual([
      { kind: 'entry', y: 23 },
      { kind: 'stop', y: 30 },
      { kind: 'tp1', y: 2 },
    ]);
  });

  it('puts the exit dot at the recorded fill, not at the exit bar close', () => {
    // The bar closed at 13 (y 2); the fill was 12.5 (y 5.5).
    expect(sparkGeometry(SERIES).exitDot).toEqual({ x: 72, y: 5.5 });
  });

  it('draws only the close line when every tick was nulled (entry off the bars)', () => {
    const g = sparkGeometry({ ...SERIES, entry: null, stop: null, tp1: null, tp2: null, exit: null });
    expect(g.ticks).toEqual([]);
    expect(g.exitDot).toBeNull();
    // Domain is now the closes alone: 10 is the floor.
    expect(g.path.startsWith('M 0.00 30.00')).toBe(true);
  });

  it('has no exit dot on a stale series: its last bar is not the exit day', () => {
    expect(sparkGeometry({ ...SERIES, stale: true }).exitDot).toBeNull();
  });

  it('has no dimmed part when the exit bar is the last bar', () => {
    const g = sparkGeometry({ ...SERIES, closes: SERIES.closes.slice(0, 4) });
    expect(g.dimmedPath).toBe('');
    expect(g.path.endsWith('L 120.00 2.00')).toBe(true);
  });

  it('draws a single bar as a flat line down the middle', () => {
    const g = sparkGeometry({
      ...SERIES,
      closes: [{ date: '2026-08-03', close: 50 }],
      exit_bar: 0, entry: 50, stop: null, tp1: null, tp2: null, exit: 50,
    });
    expect(g.path).toBe('M 0.00 16.00 L 120.00 16.00');
    expect(g.dimmedPath).toBe('');
    expect(g.exitDot).toEqual({ x: 60, y: 16 });
  });

  it('draws everything solid and no dot when exit_bar is outside the closes', () => {
    const g = sparkGeometry({ ...SERIES, exit_bar: 9 });
    expect(g.dimmedPath).toBe('');
    expect(g.exitDot).toBeNull();
    expect(g.path.endsWith('L 120.00 16.00')).toBe(true);
  });

  it('is empty for an empty close list', () => {
    expect(sparkGeometry({ ...SERIES, closes: [] })).toEqual({
      path: '', dimmedPath: '', ticks: [], exitDot: null,
    });
  });
});

describe('TradeSparkline', () => {
  let fixture: ComponentFixture<TradeSparkline>;

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
    fixture = TestBed.createComponent(TradeSparkline);
    fixture.componentRef.setInput('tradeId', 'PLAN-1');
  });

  const render = async (series: SparkSeries | null | undefined): Promise<HTMLElement> => {
    fixture.componentRef.setInput('series', series);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  };

  it('links the whole sparkline to the trade Chart tab', async () => {
    const el = await render(SERIES);
    expect(el.querySelector('a.spark')?.getAttribute('href')).toBe('/trades/PLAN-1?tab=chart');
  });

  it('draws the ticks, the dimmed context and the exit dot, with the stop called the final stop', async () => {
    const el = await render(SERIES);
    expect(el.querySelectorAll('line.tick')).toHaveLength(3);
    const stop = el.querySelector('line.tick[data-kind=stop]');
    expect(stop?.querySelector('title')?.textContent).toBe('final stop');
    expect(el.querySelector('path.dimmed')).not.toBeNull();
    expect(el.querySelector('circle.exit')).not.toBeNull();
    expect(el.querySelector('svg')?.getAttribute('viewBox')).toBe('0 0 120 32');
  });

  it('says where a stale cache ends', async () => {
    const el = await render({ ...SERIES, stale: true, last_bar: '2026-08-04' });
    expect(el.querySelector('.stale-note')?.textContent?.trim()).toBe('cache ends 2026-08-04');
    expect(el.querySelector('circle.exit')).toBeNull();
  });

  it('renders a dash, not an empty box, with no series or no answer', async () => {
    for (const series of [null, undefined]) {
      const el = await render(series);
      expect(el.querySelector('svg')).toBeNull();
      expect(el.querySelector('.spark-empty')?.textContent?.trim()).toBe('—');
    }
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/workspaces/calendar/day/trade-sparkline.spec.ts'`
Expected: FAIL at compile — `Cannot find module './trade-sparkline'`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/calendar/day/trade-sparkline.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { SparkSeries } from '../../../api/models';
import { FINAL_STOP_LABEL } from './day-copy';

/* v165 D4/D5 -- one trade's daily closes on the day page: the recorded
 * entry, final stop and targets as ticks, the exit as a dot at the FILL
 * price, and the up-to-3 bars after the exit drawn dimmed (context, not
 * part of the trade). Not `ui/sparkline.ts`: that one is a bare 100x24
 * polyline with nowhere to put a level. */

export type TickKind = 'entry' | 'stop' | 'tp1' | 'tp2';

export interface SparkGeometry {
  /** Bars 0..exit_bar. */
  path: string;
  /** Bars exit_bar..end; '' when the exit bar is the last one. */
  dimmedPath: string;
  ticks: { kind: TickKind; y: number }[];
  exitDot: { x: number; y: number } | null;
}

interface Point {
  x: number;
  y: number;
}

const TICK_KINDS: readonly TickKind[] = ['entry', 'stop', 'tp1', 'tp2'];
const TICK_LABELS: Record<TickKind, string> = {
  entry: 'entry',
  stop: FINAL_STOP_LABEL,
  tp1: 'TP1',
  tp2: 'TP2',
};
/** Keeps the stroke and the dot off the box edge. */
const PAD = 2;
const NO_GEOMETRY: SparkGeometry = { path: '', dimmedPath: '', ticks: [], exitDot: null };

const round2 = (value: number): number => Math.round(value * 100) / 100;

/** One scale for closes and levels together, so every tick lands inside. */
function yScale(values: number[], height: number): (value: number) => number {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const usable = height - PAD * 2;
  return (value) => round2(span === 0 ? height / 2 : height - PAD - ((value - min) / span) * usable);
}

function linePath(points: Point[], width: number): string {
  if (points.length === 1) {
    const y = points[0].y.toFixed(2);
    return `M 0.00 ${y} L ${width.toFixed(2)} ${y}`;
  }
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ');
}

function levelsOf(series: SparkSeries): { kind: TickKind; value: number }[] {
  return TICK_KINDS.flatMap((kind) => {
    const value = series[kind];
    return value === null ? [] : [{ kind, value }];
  });
}

/** The exit bar's index, or null when the server's index is unusable. */
function exitIndex(series: SparkSeries, last: number): number | null {
  const bar = series.exit_bar;
  return Number.isInteger(bar) && bar >= 0 && bar <= last ? bar : null;
}

/** Pure, so the drawing is asserted without a DOM. */
export function sparkGeometry(series: SparkSeries, width = 120, height = 32): SparkGeometry {
  const closes = series.closes.map((bar) => bar.close);
  if (closes.length === 0) return NO_GEOMETRY;
  const levels = levelsOf(series);
  const exit = series.exit;
  const y = yScale([...closes, ...levels.map((l) => l.value), ...(exit === null ? [] : [exit])], height);
  const last = closes.length - 1;
  const points = closes.map((close, i) => ({
    x: last === 0 ? width / 2 : round2((i / last) * width),
    y: y(close),
  }));
  const exitBar = exitIndex(series, last);
  const cut = exitBar ?? last;
  return {
    path: linePath(points.slice(0, cut + 1), width),
    dimmedPath: cut < last ? linePath(points.slice(cut), width) : '',
    ticks: levels.map((l) => ({ kind: l.kind, y: y(l.value) })),
    exitDot: exitBar === null || exit === null || series.stale
      ? null
      : { x: points[exitBar].x, y: y(exit) },
  };
}

@Component({
  selector: 'sb-trade-sparkline',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    @if (geometry(); as g) {
      <a class="spark" [routerLink]="['/trades', tradeId()]" [queryParams]="chartTab"
         aria-label="Open this trade's chart">
        <svg [attr.viewBox]="viewBox" [attr.width]="width" [attr.height]="height" aria-hidden="true">
          @for (tick of g.ticks; track tick.kind) {
            <line class="tick" [attr.data-kind]="tick.kind" x1="0" [attr.x2]="width"
                  [attr.y1]="tick.y" [attr.y2]="tick.y"><title>{{ tickLabel(tick.kind) }}</title></line>
          }
          <path class="line" [attr.d]="g.path" />
          @if (g.dimmedPath) {
            <path class="line dimmed" [attr.d]="g.dimmedPath" />
          }
          @if (g.exitDot; as dot) {
            <circle class="exit" r="2.5" [attr.cx]="dot.x" [attr.cy]="dot.y"><title>exit</title></circle>
          }
        </svg>
      </a>
      @if (staleEnd(); as end) {
        <span class="stale-note">cache ends {{ end }}</span>
      }
    } @else {
      <span class="spark-empty" title="No cached daily bars for this row">—</span>
    }
  `,
  styles: `
    :host { display: inline-flex; align-items: center; gap: var(--space-6); }
    .spark { display: inline-flex; line-height: 0; border-radius: 2px; }
    .spark:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    .line { fill: none; stroke: var(--text-secondary); stroke-width: 1.25; }
    .line.dimmed { opacity: 0.35; stroke-dasharray: 2 2; }
    .tick { stroke: var(--text-faint); stroke-width: 1; stroke-dasharray: 3 2; }
    .tick[data-kind='stop'] { stroke: var(--neg); }
    .tick[data-kind='tp1'], .tick[data-kind='tp2'] { stroke: var(--pos); }
    .exit { fill: var(--accent); }
    .stale-note { color: var(--text-faint); font-size: var(--text-chip); white-space: nowrap; }
    .spark-empty { color: var(--text-faint); font-family: var(--font-mono); }
  `,
})
export class TradeSparkline {
  readonly series = input<SparkSeries | null | undefined>();
  /** `plan_id ?? trade_id` -- the id the `/trades/:id` route takes. */
  readonly tradeId = input.required<string>();

  protected readonly width = 120;
  protected readonly height = 32;
  protected readonly viewBox = `0 0 ${this.width} ${this.height}`;
  protected readonly chartTab = { tab: 'chart' };

  protected readonly geometry = computed(() => {
    const series = this.series();
    return series ? sparkGeometry(series, this.width, this.height) : null;
  });

  protected readonly staleEnd = computed(() => {
    const series = this.series();
    return series?.stale ? series.last_bar : null;
  });

  protected tickLabel(kind: TickKind): string {
    return TICK_LABELS[kind];
  }
}
```

- [ ] **Step 4: Run the spec to verify it passes**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/workspaces/calendar/day/trade-sparkline.spec.ts'`
Expected: PASS (both `describe` blocks). If `--include` is rejected, run `npm --prefix $WT/frontend run test -- --watch=false`, expected PASS.

- [ ] **Step 5: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/calendar/day/trade-sparkline.ts frontend/src/app/workspaces/calendar/day/trade-sparkline.spec.ts
git -C $WT commit -m "feat(calendar-ui): trade sparkline with final-stop, entry and target ticks and the exit fill

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the last command lists none of this task's files.

### Task CD11: `sb-day-trade-card`: rich trade row with prices, held time, shares, MFE/MAE, sparkline and Open button

**Model:** sonnet — one presentational component

**Files:**
- Create: `frontend/src/app/workspaces/calendar/day/day-trade-card.ts`
- Create: `frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts`

**Interfaces:**
- Consumes: CD7 `CalendarTrade` (D1 fields), `SparkSeries`; CD8 `R_TOOLTIP` (`./day-copy`); CD10 `TradeSparkline` (`./trade-sparkline`, inputs `series`, `tradeId`); existing `ConnectionStore.currency()` (`frontend/src/app/stores/connection.store.ts`), `Chip`/`ChipTone` (`frontend/src/app/ui/chip.ts`, inputs `label`, `tone`, `caps`), `ABSENT, held, money, num, pct, rMultiple` (`frontend/src/app/ui/format.ts`).
- Produces (CD12 renders it): component `DayTradeCard`, selector `sb-day-trade-card`, inputs `trade = input.required<CalendarTrade>()`, `series = input<SparkSeries | null | undefined>()`; exported pure `legLabel(trade: CalendarTrade): string | null`, `heldLabel(hours: number | null): string`, `tradeLinkId(trade: CalendarTrade): string`.

**Rules (spec D5 item 5, D7):**
- Header: ticker, direction (`bullish` → `Long`, `bearish` → `Short`, anything else `—`), `strategy · horizon`, the leg label (`Leg i of n`, only when `leg_total > 1`, 1-based like the drawer), the exit-reason chip (`exit_reason` verbatim, not upper-cased; `other` is `muted`, every other reason `neutral` — no celebratory tint), then P&L, R, % return.
- Only the P&L and R figures use the `pos`/`neg` tokens (D7); % return, prices, held time, shares and MFE/MAE are neutral text.
- The R figure carries `R_TOOLTIP` as its `title` (D7: every R figure explained).
- Prices line: `Entry · Exit · Final stop · TP1 · TP2`, 2 dp grouped (`num`). The stop is labelled **Final stop** (the recorded `stop_loss` is the final one; a trailed runner's stop moved).
- Second line: `Held <held()> · Shares <n> · MFE <R> · MAE <R>`. Whole shares print with 0 dp, leg-scaled fractional shares with 2 dp.
- Every null figure renders `—` (`ABSENT`), never `0`.
- `tradeLinkId` = `plan_id ?? trade_id` (the drawer's and the Trades list's rule); **Open →** links to `/trades/<id>`; the sparkline links to the same id's Chart tab.
- Lesson and tags render as in the drawer.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { CalendarTrade, SparkSeries } from '../../../api/models';
import { ConnectionStore } from '../../../stores/connection.store';
import { R_TOOLTIP } from './day-copy';
import { DayTradeCard, heldLabel, legLabel, tradeLinkId } from './day-trade-card';

const TRADE: CalendarTrade = {
  trade_id: 'a'.repeat(16),
  ticker: 'AAPL',
  strategy: 'EMA20',
  horizon: '4w',
  direction: 'bullish',
  day: '2026-08-03',
  closed_at: '2026-08-03T20:00:00+00:00',
  outcome: 'win',
  pnl_amount: 50,
  r_multiple: 2,
  mfe_r: 2.4,
  mae_r: -0.3,
  exit_efficiency: 83,
  tags: ['clean-exit'],
  auto_lesson: 'Held to target.',
  plan_id: 'PLAN-9',
  opened_at: '2026-08-01T14:30:00+00:00',
  leg_index: 0,
  leg_total: 1,
  entry_price: 100,
  exit_price: 110,
  stop_price: 95,
  tp1: 120,
  tp2: null,
  shares: 10,
  held_hours: 53.5,
  return_pct: 10,
  exit_reason: 'tp1',
};

const SERIES: SparkSeries = {
  closes: [{ date: '2026-08-01', close: 100 }, { date: '2026-08-03', close: 110 }],
  exit_bar: 1, last_bar: '2026-08-28', stale: false,
  entry: 100, stop: 95, tp1: 120, tp2: null, exit: 110, exit_date: '2026-08-03',
};

describe('day-trade-card helpers', () => {
  it('labels a leg 1-based and a whole trade not at all', () => {
    expect(legLabel(TRADE)).toBeNull();
    expect(legLabel({ ...TRADE, leg_index: 1, leg_total: 3 })).toBe('Leg 2 of 3');
  });

  it('formats held time, with a dash for none', () => {
    expect(heldLabel(53.5)).toBe('2d 5h 30m');
    expect(heldLabel(5.25)).toBe('5h 15m');
    expect(heldLabel(null)).toBe('—');
  });

  it('links to the plan when there is one, else the trade', () => {
    expect(tradeLinkId(TRADE)).toBe('PLAN-9');
    expect(tradeLinkId({ ...TRADE, plan_id: null })).toBe('a'.repeat(16));
  });
});

describe('DayTradeCard', () => {
  let fixture: ComponentFixture<DayTradeCard>;

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: ConnectionStore, useValue: { currency: () => '€' } },
      ],
    });
    fixture = TestBed.createComponent(DayTradeCard);
  });

  const render = async (
    trade: CalendarTrade,
    series: SparkSeries | null | undefined = undefined,
  ): Promise<HTMLElement> => {
    fixture.componentRef.setInput('trade', trade);
    fixture.componentRef.setInput('series', series);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  };
  const text = (el: HTMLElement, selector: string) =>
    el.querySelector(selector)?.textContent?.replace(/\s+/g, ' ').trim();

  it('shows who, how and how much in the header', async () => {
    const el = await render(TRADE);
    expect(text(el, '.ticker')).toBe('AAPL');
    expect(text(el, '.direction')).toBe('Long');
    expect(text(el, '.setup')).toBe('EMA20 · 4w');
    expect(text(el, 'sb-chip')).toBe('tp1');
    expect(text(el, '.pnl')).toBe('+50.00 €');
    expect(text(el, '.r')).toBe('+2.00R');
    expect(text(el, '.return')).toBe('+10.00%');
    expect(el.querySelector('.leg')).toBeNull();
  });

  it('tints only P&L and R, and explains R', async () => {
    const el = await render({ ...TRADE, pnl_amount: -20, r_multiple: -0.8, return_pct: -4 });
    expect(el.querySelector('.pnl')?.classList.contains('neg')).toBe(true);
    expect(el.querySelector('.r')?.classList.contains('neg')).toBe(true);
    expect(el.querySelector('.return')?.classList.contains('neg')).toBe(false);
    expect(el.querySelector('.r')?.getAttribute('title')).toBe(R_TOOLTIP);
  });

  it('lists the recorded prices, calling the stop the final stop', async () => {
    const el = await render(TRADE);
    expect(text(el, '.prices')).toBe(
      'Entry 100.00 · Exit 110.00 · Final stop 95.00 · TP1 120.00 · TP2 —',
    );
  });

  it('shows held time, shares and MFE/MAE', async () => {
    const el = await render(TRADE);
    expect(text(el, '.stats')).toBe('Held 2d 5h 30m · Shares 10 · MFE +2.40R · MAE -0.30R');
    const leg = await render({ ...TRADE, shares: 3.3333, leg_index: 1, leg_total: 3 });
    expect(text(leg, '.stats')).toContain('Shares 3.33');
    expect(text(leg, '.leg')).toBe('Leg 2 of 3');
  });

  it('renders every missing figure as a dash, never 0', async () => {
    const el = await render({
      ...TRADE, direction: null, pnl_amount: null, r_multiple: null, return_pct: null,
      entry_price: null, exit_price: null, stop_price: null, tp1: null, tp2: null,
      shares: null, held_hours: null, mfe_r: null, mae_r: null,
    });
    expect(text(el, '.direction')).toBe('—');
    expect(text(el, '.pnl')).toBe('—');
    expect(text(el, '.r')).toBe('—');
    expect(text(el, '.return')).toBe('—');
    expect(text(el, '.prices')).toBe('Entry — · Exit — · Final stop — · TP1 — · TP2 —');
    expect(text(el, '.stats')).toBe('Held — · Shares — · MFE — · MAE —');
    expect(el.textContent).not.toContain('0.00');
  });

  it('opens the trade, and the sparkline opens its chart', async () => {
    const el = await render(TRADE, SERIES);
    expect(el.querySelector('a.open')?.getAttribute('href')).toBe('/trades/PLAN-9');
    expect(text(el, 'a.open')).toBe('Open →');
    expect(el.querySelector('sb-trade-sparkline a.spark')?.getAttribute('href'))
      .toBe('/trades/PLAN-9?tab=chart');
    const orphan = await render({ ...TRADE, plan_id: null });
    expect(orphan.querySelector('a.open')?.getAttribute('href')).toBe('/trades/' + 'a'.repeat(16));
  });

  it('shows a dash where there is no sparkline', async () => {
    const el = await render(TRADE, null);
    expect(el.querySelector('sb-trade-sparkline .spark-empty')).not.toBeNull();
  });

  it('mutes an unmapped exit reason', async () => {
    const el = await render({ ...TRADE, exit_reason: 'other' });
    expect(el.querySelector('sb-chip .chip')?.classList.contains('muted')).toBe(true);
  });

  it('keeps the lesson and the tags', async () => {
    const el = await render(TRADE);
    expect(text(el, '.lesson')).toBe('Held to target.');
    expect(text(el, '.tags')).toBe('clean-exit');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/workspaces/calendar/day/day-trade-card.spec.ts'`
Expected: FAIL at compile — `Cannot find module './day-trade-card'`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/calendar/day/day-trade-card.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { CalendarTrade, SparkSeries } from '../../../api/models';
import { ConnectionStore } from '../../../stores/connection.store';
import { Chip, ChipTone } from '../../../ui/chip';
import { ABSENT, held, money, num, pct, rMultiple } from '../../../ui/format';
import { R_TOOLTIP } from './day-copy';
import { TradeSparkline } from './trade-sparkline';

/* v165 D5 item 5 -- one row of the day page's Trades list. Every figure is
 * read from the calendar row as served (D1); nothing is re-derived here. */

/** "Leg 2 of 3" for a scale-out leg, null for a whole trade. 1-based, like
 *  the drawer. */
export function legLabel(trade: CalendarTrade): string | null {
  return trade.leg_total > 1 ? `Leg ${trade.leg_index + 1} of ${trade.leg_total}` : null;
}

export function heldLabel(hours: number | null): string {
  return held(hours);
}

/** The `/trades/:id` route takes the plan id when there is one -- the
 *  drawer's and the Trades list's rule. */
export function tradeLinkId(trade: CalendarTrade): string {
  return trade.plan_id ?? trade.trade_id;
}

const DIRECTIONS: Record<string, string> = { bullish: 'Long', bearish: 'Short' };

function sign(value: number | null): 'pos' | 'neg' | null {
  if (value === null || value === 0) return null;
  return value > 0 ? 'pos' : 'neg';
}

@Component({
  selector: 'sb-day-trade-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip, RouterLink, TradeSparkline],
  template: `
    @let t = trade();
    <article class="card">
      <header>
        <strong class="ticker">{{ t.ticker }}</strong>
        <span class="direction">{{ direction() }}</span>
        <span class="setup">{{ t.strategy }} · {{ t.horizon ?? absent }}</span>
        @if (leg(); as label) {
          <span class="leg">{{ label }}</span>
        }
        <sb-chip [label]="t.exit_reason" [tone]="exitTone()" [caps]="false" />
        <span class="figures">
          <span class="pnl" [class.pos]="pnlSign() === 'pos'" [class.neg]="pnlSign() === 'neg'">{{ pnl() }}</span>
          <span class="r" [title]="rTooltip" [class.pos]="rSign() === 'pos'" [class.neg]="rSign() === 'neg'">{{ r(t.r_multiple) }}</span>
          <span class="return">{{ returnPct() }}</span>
        </span>
      </header>
      <p class="prices">
        Entry {{ price(t.entry_price) }} · Exit {{ price(t.exit_price) }} ·
        Final stop {{ price(t.stop_price) }} · TP1 {{ price(t.tp1) }} · TP2 {{ price(t.tp2) }}
      </p>
      <p class="stats">
        Held {{ heldText() }} · Shares {{ sharesText() }} ·
        MFE {{ r(t.mfe_r) }} · MAE {{ r(t.mae_r) }}
      </p>
      <footer>
        <sb-trade-sparkline [series]="series()" [tradeId]="linkId()" />
        <a class="open" [routerLink]="['/trades', linkId()]">Open →</a>
      </footer>
      @if (t.auto_lesson; as lesson) {
        <p class="lesson">{{ lesson }}</p>
      }
      @if (t.tags.length) {
        <p class="tags">
          @for (tag of t.tags; track tag) {
            <span class="tag">{{ tag }}</span>
          }
        </p>
      }
    </article>
  `,
  styles: `
    :host { display: block; }
    .card { padding: var(--space-10) 0; border-bottom: 1px solid var(--border); }
    header { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }
    .direction, .setup, .leg { color: var(--text-secondary); font-size: var(--text-table); }
    .leg { font-size: var(--text-micro); }
    .figures { display: inline-flex; gap: var(--space-10); margin-left: auto; font-family: var(--font-mono); }
    .pnl.pos, .r.pos { color: var(--pos); }
    .pnl.neg, .r.neg { color: var(--neg); }
    .r { cursor: help; }
    .return { color: var(--text-secondary); }
    .prices, .stats {
      margin: var(--space-4) 0 0;
      color: var(--text-secondary);
      font-family: var(--font-mono);
      font-size: var(--text-micro);
    }
    footer { display: flex; align-items: center; gap: var(--space-14); margin-top: var(--space-6); }
    .open { margin-left: auto; color: var(--accent); font-weight: 600; text-decoration: none; }
    .open:hover, .open:focus-visible { text-decoration: underline; }
    .lesson { margin: var(--space-6) 0 0; font-size: var(--text-table); }
    .tags { display: flex; flex-wrap: wrap; gap: var(--space-4); margin: var(--space-6) 0 0; }
    .tag {
      padding: 1px var(--space-6);
      border: 1px solid var(--border);
      border-radius: var(--radius-chip);
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }
    @media (max-width: 639px) { .figures { margin-left: 0; width: 100%; } }
  `,
})
export class DayTradeCard {
  readonly trade = input.required<CalendarTrade>();
  readonly series = input<SparkSeries | null | undefined>();

  private readonly connection = inject(ConnectionStore);

  protected readonly absent = ABSENT;
  protected readonly rTooltip = R_TOOLTIP;

  protected readonly linkId = computed(() => tradeLinkId(this.trade()));
  protected readonly leg = computed(() => legLabel(this.trade()));
  protected readonly direction = computed(() => DIRECTIONS[this.trade().direction ?? ''] ?? ABSENT);
  protected readonly exitTone = computed<ChipTone>(() =>
    this.trade().exit_reason === 'other' ? 'muted' : 'neutral',
  );
  protected readonly pnl = computed(() => money(this.trade().pnl_amount, this.connection.currency(), 2));
  protected readonly pnlSign = computed(() => sign(this.trade().pnl_amount));
  protected readonly rSign = computed(() => sign(this.trade().r_multiple));
  protected readonly returnPct = computed(() => pct(this.trade().return_pct));
  protected readonly heldText = computed(() => heldLabel(this.trade().held_hours));
  protected readonly sharesText = computed(() => {
    const shares = this.trade().shares;
    return shares === null ? ABSENT : num(shares, Number.isInteger(shares) ? 0 : 2);
  });

  protected price(value: number | null): string {
    return num(value, 2);
  }

  protected r(value: number | null): string {
    return rMultiple(value);
  }
}
```

If the template compiler rejects `@let` (Angular < 18.1; this repo is on `~21.2`, so it should not), replace `t` with `trade()` throughout the template.

- [ ] **Step 4: Run the spec to verify it passes**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/workspaces/calendar/day/day-trade-card.spec.ts'`
Expected: PASS. If `--include` is rejected, run `npm --prefix $WT/frontend run test -- --watch=false`, expected PASS.

- [ ] **Step 5: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/calendar/day/day-trade-card.ts frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts
git -C $WT commit -m "feat(calendar-ui): day trade card with prices, hold time, shares, MFE/MAE and an Open button

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the last command lists none of this task's files.

