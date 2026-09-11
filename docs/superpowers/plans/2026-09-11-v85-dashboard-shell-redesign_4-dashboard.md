# v85 Part 3 — Dashboard panels

Header block, global constraints, parallelisation and exit criteria live in
`2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

R4-01, R4-02, R4-05 and R4-06 are **Group B** — one new file each, safe to run
in parallel. R4-03 → R4-04 is one strand inside that group. R4-07 and R4-08
are sequential after all of them: both edit `dashboard.ts`.

Every panel in this part is a presentational component: inputs in, no store
injection, no fetching. The page (R4-07) wires them to `DashboardStore`. That
is what lets each one be tested with plain values and rendered in `/ui`.

---

# Phase 1 — Panels

### Task R4-01: Portfolio Value panel

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts`
- Create: `frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts`

**Interfaces:**
- Consumes: `--text-hero` (R1-02); `sb-panel` and `sb-sparkline` primitives.
- Produces: `<sb-portfolio-value>` with inputs
  `balance: number | null`, `changePct: number | null`,
  `points: readonly number[]`, `currency: string`.
  R4-07 binds these to `DashboardStore.balance/openPnlPct/equityPoints` and
  `ConnectionStore.currency`.

**No range tabs and no intraday chart** — D8. The only series that exists is
`equity_30d`, and seven range buttons where one has data is six lies.

- [ ] **Step 1: Write the failing test**

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';

import { PortfolioValue } from './portfolio-value';

describe('portfolio value panel', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(PortfolioValue);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('shows the balance as the hero figure with its currency', () => {
    const el = render({ balance: 997480.01, changePct: 0.36, points: [1, 2], currency: '€' });
    expect(el.querySelector('.figure')?.textContent).toContain('997,480.01');
    expect(el.querySelector('.figure')?.textContent).toContain('€');
  });

  it('tones the day change by sign', () => {
    expect(render({ balance: 1, changePct: 0.36, points: [], currency: '€' })
      .querySelector('.change')?.classList.contains('pos')).toBe(true);
    expect(render({ balance: 1, changePct: -0.36, points: [], currency: '€' })
      .querySelector('.change')?.classList.contains('neg')).toBe(true);
  });

  it('renders no value rather than a zero when the balance is missing', () => {
    const el = render({ balance: null, changePct: null, points: [], currency: '€' });
    expect(el.querySelector('.figure')?.textContent).not.toContain('0.00');
    expect(el.querySelector('.change')).toBeNull();
  });

  it('omits the sparkline entirely when there are no points', () => {
    expect(render({ balance: 1, changePct: 0, points: [], currency: '€' })
      .querySelector('sb-sparkline')).toBeNull();
    expect(render({ balance: 1, changePct: 0, points: [1, 2, 3], currency: '€' })
      .querySelector('sb-sparkline')).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
```

Expected: FAIL — cannot resolve `./portfolio-value`.

- [ ] **Step 3: Write the component**

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Panel } from '../../../ui/layout';
import { Sparkline } from '../../../ui/sparkline';
import { amount, pct } from '../../../ui/format';

/**
 * The account, in one figure — v85 D8.
 *
 * Deliberately NOT the mockup's interactive intraday chart: the only equity
 * series this bot keeps is `equity_30d`, 30 daily points. A 1D/1W/1M/3M/YTD/
 * 1Y/ALL strip over one series would be six controls that cannot answer.
 */
@Component({
  selector: 'sb-portfolio-value',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Sparkline],
  template: `
    <sb-panel heading="Portfolio value">
      @if (balance() !== null) {
        <p class="figure">{{ money() }}</p>
      } @else {
        <p class="figure muted">—</p>
      }

      @if (changePct() !== null) {
        <p class="change" [class.pos]="changePct()! > 0" [class.neg]="changePct()! < 0">
          {{ fmtPct(changePct()) }} today
        </p>
      }

      @if (points().length) {
        <sb-sparkline [points]="points()" label="30-day equity" />
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .figure {
      margin: 0;
      font-size: var(--text-hero);
      font-weight: 600;
      color: var(--text);
      font-variant-numeric: tabular-nums;
      line-height: 1.1;
    }
    .figure.muted { color: var(--text-faint); }
    .change {
      margin: var(--space-4) 0 var(--space-10);
      font-size: var(--text-body);
      font-variant-numeric: tabular-nums;
    }
    .change.pos { color: var(--pos); }
    .change.neg { color: var(--neg); }
  `,
})
export class PortfolioValue {
  readonly balance = input<number | null>(null);
  readonly changePct = input<number | null>(null);
  readonly points = input<readonly number[]>([]);
  readonly currency = input('€');

  protected readonly money = computed(() => amount(this.balance(), this.currency()));
  protected fmtPct = pct;
}
```

Check `ui/format.ts`'s exported names before relying on `amount`/`pct` — the
Dashboard already imports both (`dashboard.ts:40`), so they exist; confirm
their argument order.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts \
        frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
git commit -m "feat(dashboard): add the portfolio value panel"
```

---

### Task R4-02: Trading Performance panel

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`
- Create: `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`

**Interfaces:**
- Consumes: `DashboardStore.payoffRatio` (R3-03) via its input; `sb-panel`,
  `sb-metric-card`.
- Produces: `<sb-trading-performance>` with inputs `openPnlPct`, `winRate`,
  `expectancyR`, `avgConfidence`, `realizedAmount`, `realizedLabel`,
  `openTrades`, `riskUsedPct`, `riskCapPct`, `payoffRatio`, `currency`,
  `scope`, and output `scopeChange: 'today' | 'all'`.

**Eight metrics, and no risk dial.** The mockup embeds a risk gauge plus a
Risk per trade / Current risk / Remaining risk breakdown in this panel; that is
the Risk & Exposure content the spec cut, and rebuilding it here would
reintroduce it by the back door (D9).

- [ ] **Step 1: Write the failing test**

```ts
it('shows all eight metrics', () => {
  const el = render({
    openPnlPct: 0.36, winRate: 49.1, expectancyR: -0.16, avgConfidence: 4.0,
    realizedAmount: 0, realizedLabel: 'Realised today', openTrades: 1,
    riskUsedPct: 0, riskCapPct: 6, payoffRatio: 2.34, currency: '€', scope: 'today',
  });
  const labels = [...el.querySelectorAll('sb-metric-card')]
    .map((c) => c.textContent ?? '');
  expect(labels.length).toBe(8);
  expect(el.textContent).toContain('Payoff ratio');
  expect(el.textContent).toContain('2.34');
});

it('emits the scope the user picked', () => {
  const f = TestBed.createComponent(TradingPerformance);
  f.componentRef.setInput('scope', 'today');
  f.detectChanges();
  let picked: string | undefined;
  f.componentInstance.scopeChange.subscribe((s: string) => (picked = s));
  (f.nativeElement as HTMLElement)
    .querySelector<HTMLButtonElement>('[data-scope="all"]')!.click();
  expect(picked).toBe('all');
});

it('renders a missing payoff ratio as no value, never as zero', () => {
  // null means "not enough outcomes yet". 0 would claim wins are worthless
  // against losses -- a real and very different statement.
  const el = render({ payoffRatio: null, riskCapPct: 6, currency: '€', scope: 'today' });
  const card = [...el.querySelectorAll('sb-metric-card')]
    .find((c) => c.textContent?.includes('Payoff ratio'))!;
  expect(card.textContent).not.toContain('0.00');
});

it('carries no risk gauge -- that is the cut Risk & Exposure content', () => {
  const el = render({ riskUsedPct: 0, riskCapPct: 6, currency: '€', scope: 'today' });
  expect(el.querySelector('sb-donut')).toBeNull();
  expect(el.textContent).not.toContain('Remaining risk');
});
```

Write the same `render()` helper this part's other specs use.

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

```ts
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { Button } from '../../../ui/button';
import { ControlRow, Panel } from '../../../ui/layout';
import { MetricCard } from '../../../ui/metric-card';

export type DashboardScopeMode = 'today' | 'all';

/**
 * The eight figures — v85 D9.
 *
 * Win rate, expectancy and payoff ratio travel together on purpose: win rate
 * and payoff ratio decompose expectancy, so read as a triple they say why the
 * expectancy is what it is rather than only what it is.
 *
 * The scope control sits in this panel's header (D10) and is page-wide: it
 * also re-scopes the Closed tab below. That was chosen deliberately with the
 * caveat understood — it is not an oversight to "fix" by narrowing it.
 */
@Component({
  selector: 'sb-trading-performance',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, MetricCard, ControlRow, Button],
  template: `
    <sb-panel heading="Trading performance">
      <sb-control-row panel-actions role="group" aria-label="Date scope">
        @for (option of scopes; track option.mode) {
          <button
            sb-button
            type="button"
            [attr.data-scope]="option.mode"
            [variant]="scope() === option.mode ? 'secondary' : 'ghost'"
            [attr.aria-pressed]="scope() === option.mode"
            (click)="scopeChange.emit(option.mode)"
          >{{ option.label }}</button>
        }
      </sb-control-row>

      <div class="grid">
        <sb-metric-card label="Open P&L" [value]="openPnlPct()" tone="pnl" unit="%" />
        <sb-metric-card label="Win rate" [value]="winRate()" unit="%" [decimals]="1" />
        <sb-metric-card label="Expectancy" [value]="expectancyR()" tone="pnl" unit="R" />
        <sb-metric-card label="Payoff ratio" [value]="payoffRatio()" [decimals]="2" />
        <sb-metric-card [label]="realizedLabel()" [value]="realizedAmount()"
                        tone="pnl" [unit]="currencyUnit()" />
        <sb-metric-card label="Open trades" [value]="openTrades()" [decimals]="0" />
        <sb-metric-card label="Avg confidence" [value]="avgConfidence()" [decimals]="1" />
        <sb-metric-card label="Risk used" [value]="riskUsedPct()" unit="%" [sub]="riskSub()" />
      </div>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    /* auto-fit rather than a fixed count: eight cards should reflow to 4×2,
       2×4 or 1×8 by available width, not by a breakpoint list. */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: var(--space-14);
    }
  `,
})
export class TradingPerformance {
  readonly openPnlPct = input<number | null>(null);
  readonly winRate = input<number | null>(null);
  readonly expectancyR = input<number | null>(null);
  readonly avgConfidence = input<number | null>(null);
  readonly realizedAmount = input<number | null>(null);
  readonly realizedLabel = input('Realised today');
  readonly openTrades = input<number>(0);
  readonly riskUsedPct = input<number | null>(null);
  readonly riskCapPct = input<number | null>(null);
  /** Mean winning R over the magnitude of mean losing R. Null, never 0, when
   *  either side has no outcomes yet — see payoff_ratio_from_rs. */
  readonly payoffRatio = input<number | null>(null);
  readonly currency = input('€');
  readonly scope = input<DashboardScopeMode>('today');
  readonly scopeChange = output<DashboardScopeMode>();

  protected readonly scopes: { mode: DashboardScopeMode; label: string }[] = [
    { mode: 'today', label: 'Today' },
    { mode: 'all', label: 'All days' },
  ];

  protected readonly currencyUnit = computed(() => ` ${this.currency()}`);
  protected readonly riskSub = computed(() => {
    const cap = this.riskCapPct();
    return cap === null ? null : `of ${cap.toFixed(1)}% cap`;
  });
}
```

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/trading-performance.ts \
        frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts
git commit -m "feat(dashboard): add the trading performance panel"
```

---

### Task R4-03: Recent Activity derivation

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/panels/activity.ts`
- Create: `frontend/src/app/workspaces/dashboard/panels/activity.spec.ts`

**Interfaces:**
- Consumes: `TradeRow` from `api/models`.
- Produces:
  - `interface ActivityEvent { kind: 'opened' | 'closed' | 'cancelled'; at: string; ticker: string; detail: string; id: string }`
  - `deriveActivity(rows: readonly TradeRow[], limit?: number): ActivityEvent[]`

  R4-04 renders these.

**Three kinds, not four — D15 resolved.** `TradeRow` has `banked_fraction`,
`banked_exit_price` and `banked_r` but **no `banked_at`**. Its only timestamps
are `opened_at` and `closed_at`, so a TP1 line could only be dated by
inference. Do not add one, and do not date it from `closed_at`.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'vitest';

import { deriveActivity } from './activity';

function row(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'p1', leg_index: 0, ticker: 'ASTS', direction: 'bullish',
    status: 'ACTIVE', opened_at: '2026-09-11T15:53:00Z', closed_at: null,
    ...over,
  } as never;
}

describe('activity derivation', () => {
  it('emits an opened event for a filled position', () => {
    const events = deriveActivity([row()]);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ kind: 'opened', ticker: 'ASTS' });
  });

  it('emits both opened and closed for a position that has closed', () => {
    const events = deriveActivity([
      row({ status: 'CLOSED', closed_at: '2026-09-11T16:20:00Z' }),
    ]);
    expect(events.map((e) => e.kind)).toEqual(['closed', 'opened']);
  });

  it('emits cancelled rather than closed for a cancelled plan', () => {
    const events = deriveActivity([
      row({ status: 'CANCELLED', opened_at: null, closed_at: '2026-09-11T16:20:00Z' }),
    ]);
    expect(events.map((e) => e.kind)).toEqual(['cancelled']);
  });

  it('never emits a TP1 event, because no row carries a TP1 timestamp', () => {
    const events = deriveActivity([
      row({ status: 'PARTIAL', banked_fraction: 0.5, banked_r: 1.0 }),
    ]);
    expect(events.map((e) => e.kind)).toEqual(['opened']);
  });

  it('orders newest first across every row', () => {
    const events = deriveActivity([
      row({ id: 'a', opened_at: '2026-09-11T10:00:00Z' }),
      row({ id: 'b', opened_at: '2026-09-11T14:00:00Z' }),
    ]);
    expect(events.map((e) => e.id)).toEqual(['b:opened', 'a:opened']);
  });

  it('skips rows with no usable timestamp instead of dating them now', () => {
    expect(deriveActivity([row({ opened_at: null, closed_at: null })])).toEqual([]);
  });

  it('caps the feed at the requested limit', () => {
    const rows = Array.from({ length: 20 }, (_, i) =>
      row({ id: `p${i}`, opened_at: `2026-09-11T10:${String(i).padStart(2, '0')}:00Z` }));
    expect(deriveActivity(rows, 6)).toHaveLength(6);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/activity.spec.ts
```

Expected: FAIL — cannot resolve `./activity`.

- [ ] **Step 3: Write the derivation**

```ts
import { TradeRow } from '../../../api/models';

export interface ActivityEvent {
  kind: 'opened' | 'closed' | 'cancelled';
  /** ISO instant. Never synthesised — a row with no timestamp is skipped. */
  at: string;
  ticker: string;
  detail: string;
  /** Stable across refetches, so the list does not re-animate: one row can
   *  produce two events, so the row id alone would not be unique. */
  id: string;
}

const DEFAULT_LIMIT = 6;

/**
 * The activity feed, derived from trade rows already fetched — v85 D15.
 *
 * There is no backend event log, so this is the honest maximum: what the trade
 * records themselves can date. Three kinds, not the mockup's four — no row
 * carries a TP1 timestamp (`banked_at` does not exist), and no "system scan"
 * or "price alert" event exists anywhere in this bot.
 */
export function deriveActivity(
  rows: readonly TradeRow[],
  limit: number = DEFAULT_LIMIT,
): ActivityEvent[] {
  const events: ActivityEvent[] = [];

  for (const row of rows) {
    const ticker = row.ticker;

    if (row.closed_at) {
      const cancelled = row.status?.toUpperCase() === 'CANCELLED';
      events.push({
        kind: cancelled ? 'cancelled' : 'closed',
        at: row.closed_at,
        ticker,
        detail: cancelled
          ? 'Plan cancelled before filling'
          : `Closed${row.r_multiple != null ? ` at ${row.r_multiple > 0 ? '+' : ''}${row.r_multiple.toFixed(2)}R` : ''}`,
        id: `${row.id}:${cancelled ? 'cancelled' : 'closed'}`,
      });
    }

    if (row.opened_at) {
      events.push({
        kind: 'opened',
        at: row.opened_at,
        ticker,
        detail: `${row.direction === 'bearish' ? 'Short' : 'Long'}${row.entry != null ? ` at ${row.entry}` : ''}`,
        id: `${row.id}:opened`,
      });
    }
  }

  return events
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, limit);
}
```

`localeCompare` on ISO-8601 strings sorts correctly without constructing a
`Date` per comparison, and avoids an invalid-date NaN silently reordering the
list.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/activity.spec.ts
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/activity.ts \
        frontend/src/app/workspaces/dashboard/panels/activity.spec.ts
git commit -m "feat(dashboard): derive an activity feed from trade timestamps"
```

---

### Task R4-04: Recent Activity panel

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`
- Create: `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts`

**Interfaces:**
- Consumes: `ActivityEvent` from R4-03; the `'opened'`/`'closed'` icons from
  R1-03; `dateTime` from `ui/format`.
- Produces: `<sb-recent-activity>` with input `events: readonly ActivityEvent[]`.

- [ ] **Step 1: Write the failing test**

```ts
it('lists each event with its ticker, detail and time', () => {
  const el = render({ events: [
    { kind: 'opened', at: '2026-09-11T15:53:00Z', ticker: 'ASTS', detail: 'Long at 60.54', id: 'a:opened' },
  ]});
  const item = el.querySelector('.event')!;
  expect(item.textContent).toContain('ASTS');
  expect(item.textContent).toContain('Long at 60.54');
});

it('distinguishes the three kinds by class, not by colour alone', () => {
  const el = render({ events: [
    { kind: 'opened', at: '2026-09-11T15:00:00Z', ticker: 'A', detail: '', id: '1' },
    { kind: 'closed', at: '2026-09-11T14:00:00Z', ticker: 'B', detail: '', id: '2' },
    { kind: 'cancelled', at: '2026-09-11T13:00:00Z', ticker: 'C', detail: '', id: '3' },
  ]});
  expect([...el.querySelectorAll('.event')].map((n) => n.className))
    .toEqual(['event opened', 'event closed', 'event cancelled']);
});

it('says so when there is nothing yet rather than rendering an empty box', () => {
  const el = render({ events: [] });
  expect(el.textContent).toContain('No activity yet');
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Panel } from '../../../ui/layout';
import { Icon } from '../../../ui/icon';
import { dateTime } from '../../../ui/format';
import { ActivityEvent } from './activity';

/** What just happened, from the trade records themselves — v85 D15. */
@Component({
  selector: 'sb-recent-activity',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Icon, RouterLink],
  template: `
    <sb-panel heading="Recent activity">
      <a panel-actions class="all-link" routerLink="/trades">View all</a>

      @if (events().length) {
        <ul class="feed">
          @for (event of events(); track event.id) {
            <li class="event {{ event.kind }}">
              <sb-icon [name]="event.kind === 'opened' ? 'opened' : 'closed'" />
              <span class="ticker">{{ event.ticker }}</span>
              <span class="detail">{{ event.detail }}</span>
              <time class="at" [attr.datetime]="event.at">{{ fmt(event.at) }}</time>
            </li>
          }
        </ul>
      } @else {
        <p class="empty">No activity yet — it fills as plans open and close.</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .feed { margin: 0; padding: 0; list-style: none; display: grid; gap: var(--space-8); }
    .event {
      display: grid;
      grid-template-columns: auto auto 1fr auto;
      align-items: baseline;
      gap: var(--space-8);
      font-size: var(--text-table);
    }
    /* The icon carries the kind as a shape; colour is the second cue, never
       the only one. */
    .event.opened sb-icon { color: var(--accent); }
    .event.closed sb-icon { color: var(--pos); }
    .event.cancelled sb-icon { color: var(--text-faint); }
    .ticker { font-family: var(--font-mono); color: var(--text); font-weight: 600; }
    .detail { color: var(--text-secondary); }
    .at { color: var(--text-faint); font-variant-numeric: tabular-nums; white-space: nowrap; }
    .empty { margin: 0; color: var(--text-faint); font-size: var(--text-chip); }
    .all-link { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .all-link:hover { text-decoration: underline; }
  `,
})
export class RecentActivity {
  readonly events = input<readonly ActivityEvent[]>([]);
  protected fmt = dateTime;
}
```

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/recent-activity.ts \
        frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts
git commit -m "feat(dashboard): add the recent activity panel"
```

---

### Task R4-05: Watchlist panel

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/panels/watchlist-panel.ts`
- Create: `frontend/src/app/workspaces/dashboard/panels/watchlist-panel.spec.ts`

**Interfaces:**
- Consumes: `TapeRow` from `api/models`.
- Produces: `<sb-watchlist-panel>` with input `rows: readonly TapeRow[]` and
  `limit: number`. R4-07 binds it to `TapeStore.rows`.

- [ ] **Step 1: Write the failing test**

```ts
function tape(over: Partial<TapeRow> = {}): TapeRow {
  return { symbol: 'GS', price: 1022.63, change_pct: -0.06,
           context_kind: null, context_label: null, sort_rank: 2, ...over };
}

it('lists symbol, price and day change', () => {
  const el = render({ rows: [tape()] });
  expect(el.textContent).toContain('GS');
  expect(el.textContent).toContain('1,022.63');
  expect(el.textContent).toContain('-0.06');
});

it('tones the change by sign', () => {
  const el = render({ rows: [tape({ change_pct: 1.24 }), tape({ symbol: 'X', change_pct: -1.24 })] });
  const cells = el.querySelectorAll('.change');
  expect(cells[0].classList.contains('pos')).toBe(true);
  expect(cells[1].classList.contains('neg')).toBe(true);
});

it('shows a dash, not a zero, for a symbol with no price yet', () => {
  const el = render({ rows: [tape({ price: null, change_pct: null })] });
  expect(el.querySelector('.price')?.textContent?.trim()).toBe('—');
});

it('caps the list at the limit', () => {
  const rows = Array.from({ length: 12 }, (_, i) => tape({ symbol: `S${i}` }));
  expect(render({ rows, limit: 5 }).querySelectorAll('tbody tr')).toHaveLength(5);
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/watchlist-panel.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TapeRow } from '../../../api/models';
import { Panel } from '../../../ui/layout';
import { num, pct } from '../../../ui/format';

/** The watchlist, as a table rather than a moving strip — the same tape data
 *  the top bar scrolls, sitting still long enough to read. */
@Component({
  selector: 'sb-watchlist-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, RouterLink],
  template: `
    <sb-panel heading="Watchlist">
      <a panel-actions class="all-link" routerLink="/watchlist">View all</a>
      <table>
        <thead>
          <tr><th scope="col">Symbol</th><th scope="col">Price</th><th scope="col">1D</th></tr>
        </thead>
        <tbody>
          @for (row of visible(); track row.symbol) {
            <tr>
              <td><a class="symbol" [routerLink]="['/watchlist', row.symbol]">{{ row.symbol }}</a></td>
              <td class="price">{{ row.price === null ? '—' : fmtNum(row.price) }}</td>
              <td class="change"
                  [class.pos]="(row.change_pct ?? 0) > 0"
                  [class.neg]="(row.change_pct ?? 0) < 0">
                {{ row.change_pct === null ? '—' : fmtPct(row.change_pct) }}
              </td>
            </tr>
          }
        </tbody>
      </table>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    th {
      text-align: left;
      color: var(--text-faint);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      font-weight: 500;
      padding-bottom: var(--space-4);
    }
    td { padding: var(--space-4) 0; font-variant-numeric: tabular-nums; }
    td.price, td.change, th:not(:first-child) { text-align: right; }
    .symbol { color: var(--accent); font-family: var(--font-mono); text-decoration: none; }
    .symbol:hover { text-decoration: underline; }
    .change.pos { color: var(--pos); }
    .change.neg { color: var(--neg); }
    .all-link { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
  `,
})
export class WatchlistPanel {
  readonly rows = input<readonly TapeRow[]>([]);
  readonly limit = input(6);

  protected readonly visible = computed(() => this.rows().slice(0, this.limit()));
  protected fmtNum = num;
  protected fmtPct = pct;
}
```

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/watchlist-panel.spec.ts
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/watchlist-panel.ts \
        frontend/src/app/workspaces/dashboard/panels/watchlist-panel.spec.ts
git commit -m "feat(dashboard): add the watchlist panel"
```

---

### Task R4-06: Market Movers panel

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/panels/market-movers.ts`
- Create: `frontend/src/app/workspaces/dashboard/panels/market-movers.spec.ts`

**Interfaces:**
- Consumes: `TapeRow`; `sb-tab-bar` from `ui/layout`.
- Produces: `<sb-market-movers>` with input `rows: readonly TapeRow[]`.

**Two tabs, not three — D17 resolved.** `TapeRow` is
`{ symbol, price, change_pct, context_kind, context_label, sort_rank }`. There
is no volume on it and no other client-side source for one, so the mockup's
"Most Active" tab has no honest filling and is not built. Do not approximate it
with change, spread or row count.

- [ ] **Step 1: Write the failing test**

```ts
it('ranks gainers highest-first and losers lowest-first', () => {
  const rows = [
    tape({ symbol: 'A', change_pct: 2.69 }),
    tape({ symbol: 'B', change_pct: -1.10 }),
    tape({ symbol: 'C', change_pct: 1.24 }),
    tape({ symbol: 'D', change_pct: -3.40 }),
  ];
  const f = mount({ rows });
  expect(symbols(f)).toEqual(['A', 'C']);          // gainers tab is default

  click(f, 'losers');
  expect(symbols(f)).toEqual(['D', 'B']);
});

it('offers exactly two tabs, because there is no volume to rank activity by', () => {
  const f = mount({ rows: [] });
  const labels = [...(f.nativeElement as HTMLElement).querySelectorAll('[role="tab"]')]
    .map((t) => t.textContent?.trim());
  expect(labels).toEqual(['Top gainers', 'Top losers']);
});

it('excludes unpriced symbols from both tabs rather than ranking them as zero', () => {
  const f = mount({ rows: [tape({ symbol: 'A', change_pct: null }), tape({ symbol: 'B', change_pct: 1 })] });
  expect(symbols(f)).toEqual(['B']);
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/market-movers.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

Reuse `sb-tab-bar` from `ui/layout` — it already owns the roving tabindex,
`role="tablist"` and the scroll fades. Read its `tabs` input type at the top of
`ui/layout.ts` and match it exactly.

```ts
import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { TapeRow } from '../../../api/models';
import { Panel, TabBar } from '../../../ui/layout';
import { pct } from '../../../ui/format';

type MoverTab = 'gainers' | 'losers';

/**
 * Top gainers and top losers, ranked from the tape already on screen.
 *
 * **Two tabs, not the mockup's three.** `TapeRow` carries no volume, so
 * "Most Active" cannot be answered — v85 D17. A proxy would be a number that
 * looks like activity and is not.
 */
@Component({
  selector: 'sb-market-movers',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, TabBar],
  template: `
    <sb-panel heading="Market movers">
      <sb-tab-bar [tabs]="tabs" [active]="active()" (activeChange)="active.set($any($event))" />
      <ul class="movers">
        @for (row of visible(); track row.symbol) {
          <li>
            <span class="symbol">{{ row.symbol }}</span>
            <span class="change" [class.pos]="row.change_pct! > 0" [class.neg]="row.change_pct! < 0">
              {{ fmtPct(row.change_pct) }}
            </span>
          </li>
        } @empty {
          <li class="empty">No priced symbols yet.</li>
        }
      </ul>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .movers { margin: var(--space-8) 0 0; padding: 0; list-style: none; display: grid; gap: var(--space-6); }
    .movers li { display: flex; justify-content: space-between; font-size: var(--text-table); }
    .symbol { font-family: var(--font-mono); color: var(--text); }
    .change { font-variant-numeric: tabular-nums; }
    .change.pos { color: var(--pos); }
    .change.neg { color: var(--neg); }
    .empty { color: var(--text-faint); font-size: var(--text-chip); }
  `,
})
export class MarketMovers {
  readonly rows = input<readonly TapeRow[]>([]);
  readonly limit = input(5);

  protected readonly active = signal<MoverTab>('gainers');
  protected readonly tabs = [
    { id: 'gainers', label: 'Top gainers' },
    { id: 'losers', label: 'Top losers' },
  ];

  /** Unpriced symbols are dropped, not sorted as 0: a symbol whose quote has
   *  not arrived is not a symbol that did not move. */
  protected readonly visible = computed(() => {
    const priced = this.rows().filter((row) => row.change_pct !== null);
    const sorted = [...priced].sort((a, b) =>
      this.active() === 'gainers'
        ? (b.change_pct ?? 0) - (a.change_pct ?? 0)
        : (a.change_pct ?? 0) - (b.change_pct ?? 0),
    );
    return sorted.slice(0, this.limit());
  });

  protected fmtPct = pct;
}
```

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/market-movers.spec.ts
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/market-movers.ts \
        frontend/src/app/workspaces/dashboard/panels/market-movers.spec.ts
git commit -m "feat(dashboard): add the market movers panel"
```

---

# Phase 2 — The page

### Task R4-07: Assemble the Dashboard page

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (template and styles)
- Test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes: all five panels (R4-01 … R4-06), `DashboardStore`, `TapeStore`,
  `ConnectionStore`.
- Produces: the page layout. R4-08 and Part 4 edit this same file afterwards.

**What comes out:** the `.primary` metric-card row, the `.chips` chip row, the
`realized-count` line, and the `lifecycle` nav strip — every one of them is
replaced by a panel above. **What must not come out:** the `sb-async` wrapper,
the scope wiring, or the `sb-panel` holding the positions tables (Part 4
replaces its contents, not this task).

- [ ] **Step 1: Write the failing test**

```ts
it('lays the page out as the five panels plus the positions table', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;

  expect(el.querySelector('sb-portfolio-value')).not.toBeNull();
  expect(el.querySelector('sb-trading-performance')).not.toBeNull();
  expect(el.querySelector('sb-recent-activity')).not.toBeNull();
  expect(el.querySelector('sb-watchlist-panel')).not.toBeNull();
  expect(el.querySelector('sb-market-movers')).not.toBeNull();
});

it('drops the old metric rows the panels replaced', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  expect(el.querySelector('.primary')).toBeNull();
  expect(el.querySelector('sb-chip-row.chips')).toBeNull();
  expect(el.querySelector('.lifecycle')).toBeNull();
});

it('has no Risk & Exposure or Account Info panel', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const text = (f.nativeElement as HTMLElement).textContent ?? '';
  expect(text).not.toContain('Risk & Exposure');
  expect(text).not.toContain('Account Info');
});

it('routes the panel scope control back into the store', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  el.querySelector<HTMLButtonElement>('[data-scope="all"]')!.click();
  f.detectChanges();
  expect(TestBed.inject(DashboardStore).scope()).toBe('all');
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: FAIL — no `sb-portfolio-value`.

- [ ] **Step 3: Rewrite the page body**

In `dashboard.ts`, add the five panels to `imports`, inject `TapeStore`, and
replace the `.primary` / `.realized-count` / `.chips` / `.lifecycle` blocks
inside `sb-async` with:

```html
    <div class="top-row">
      <sb-portfolio-value
        [balance]="store.balance()"
        [changePct]="store.equityChangePct()"
        [points]="store.equityPoints()"
        [currency]="connection.currency()"
      />
      <sb-trading-performance
        [openPnlPct]="store.openPnlPct()"
        [winRate]="store.winRate()"
        [expectancyR]="store.expectancyR()"
        [avgConfidence]="store.avgConfidence()"
        [realizedAmount]="store.realizedAmount()"
        [realizedLabel]="realizedLabel()"
        [openTrades]="store.openTrades()"
        [riskUsedPct]="store.riskUsedPct()"
        [riskCapPct]="store.riskCapPct()"
        [payoffRatio]="store.payoffRatio()"
        [currency]="connection.currency()"
        [scope]="store.scope()"
        (scopeChange)="store.setScope($event)"
      />
    </div>
```

and, below the positions panel, the bottom row:

```html
    <div class="bottom-row">
      <sb-recent-activity [events]="activity()" />
      <sb-market-movers [rows]="tape.rows()" />
      <sb-watchlist-panel [rows]="tape.rows()" />
    </div>
```

Add to the class, and add `TradesStore` to the component's `providers` array
beside `DashboardStore`:

```ts
  protected readonly tape = inject(TapeStore);
  /** This page's own instance, and NOT the positions table's: that one holds
   *  whichever single tab is selected, which is the wrong population for a
   *  feed that must span opens and closes at once. Provided on this component
   *  (see `providers`), so it is created on entry and destroyed on exit. */
  private readonly recent = inject(TradesStore);

  protected readonly activity = computed(() => deriveActivity(this.recent.rows()));
```

and in the constructor, the one query that feeds it:

```ts
    // Every status, newest first. ACTIVITY_WINDOW rows in, at most six events
    // out (deriveActivity's own cap) -- a row can yield two events, so the
    // fetch has to be wider than the feed.
    this.recent.setQuery({ sort: '-opened_at', page: 1, per_page: 20 });
```

Do not reach into the positions table for these rows.

Then the styles:

```css
    /* Two columns at desktop, stacking below the same 900px the top bar uses
       for its own first drop -- one breakpoint vocabulary per page. */
    .top-row {
      display: grid;
      grid-template-columns: minmax(0, 3fr) minmax(0, 4fr);
      gap: var(--register-pad);
    }
    .bottom-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: var(--register-pad);
    }
    @media (max-width: 900px) {
      .top-row { grid-template-columns: minmax(0, 1fr); }
    }
```

Delete the now-unused `.primary`, `.chips`, `.lc*`, `.lifecycle` and
`.realized-count` rules, and drop `MetricCard`, `MetricChip` and `ChipRow` from
`imports` if nothing else in the file uses them.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: PASS. Existing tests in this file that assert the old metric rows are
being deliberately replaced — rewrite them to assert the panel that took over,
never delete them outright.

- [ ] **Step 5: Look at it**

`cd frontend && npm start`, open `/dashboard`, and screenshot at 1440px and
390px via chrome-devtools. Confirm the two-column top row, the three-up bottom
row, and no horizontal scroll at phone width.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.ts \
        frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "feat(dashboard): compose the page from the v85 panels"
```

---

### Task R4-08: Move the explanatory copy behind affordances

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts`
- Test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes: `sb-drawer` from `ui/layout` (already imported by this file).
- Produces: nothing new.

**Every word survives — D18.** Four pieces of copy move: the "What appears
here" qualifying-trades explainer, the share-count snapshot note, the
position-premium/sizing explanation, and the closing footnote. The lifecycle
guide is already a drawer and stays one. **Do not delete any of this text.**

- [ ] **Step 1: Write the failing test**

```ts
it('keeps the qualifying-trades explainer reachable but off the page face', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;

  // Not in the page body any more…
  expect(el.querySelector('.explainer')).toBeNull();

  // …but one click away, and still the same rule, stated in full.
  el.querySelector<HTMLButtonElement>('[data-info="qualifying"]')!.click();
  f.detectChanges();
  expect(el.textContent).toContain('Only trades that meet');
  expect(el.textContent).toContain('are logged here as paper trades');
});

it('keeps the sizing note and the footnote reachable too', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  expect(el.querySelector('[data-info="sizing"]')).not.toBeNull();
  expect(el.querySelector('[data-info="prices"]')).not.toBeNull();
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: FAIL — `.explainer` still renders, no `[data-info]` trigger.

- [ ] **Step 3: Move each piece into a drawer**

Add one signal per drawer and a small trigger beside the panel each explains:

```ts
  protected readonly infoOpen = signal<null | 'qualifying' | 'sizing' | 'prices'>(null);
```

Trigger, projected into the relevant panel's actions slot:

```html
        <button sb-button variant="ghost" type="button" data-info="qualifying"
                aria-label="What appears here"
                (click)="infoOpen.set('qualifying')">?</button>
```

Drawer, with the copy moved **verbatim** out of the old `.explainer`
paragraph — same words, same `<strong>`/`<em>`/`<code>` emphasis:

```html
    <sb-drawer [open]="infoOpen() === 'qualifying'" heading="What appears here"
               (closed)="infoOpen.set(null)">
      <p class="section-help">
        <strong>What appears here:</strong>
        Only trades that meet <em>every</em> configured requirement (min reward,
        stop distance, risk:reward, min strategies confirmed, min confidence) are
        logged here as paper trades. Trade plans shown by <code>!check</code> that
        don't clear all requirements appear in Discord but are <strong>not</strong>
        logged — they're marked in bold red in the Discord embed. The automatic
        background scan only ever posts and logs fully-qualifying setups.
      </p>
    </sb-drawer>
```

Repeat for `sizing` (the `premiumExplanation()` text plus the share-count
snapshot note) and `prices` (the footnote, including `riskSizingNote()` and the
`!account` line). Keep the existing `lifecycleInfoOpen` drawer exactly as it is
— it is already the pattern the other three now follow.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Prove nothing was lost**

```bash
git show HEAD~1:frontend/src/app/workspaces/dashboard/dashboard.ts > /tmp/before.ts
```

Diff the prose by eye between `/tmp/before.ts` and the current file: every
sentence that was on the page must appear in a drawer. This is the one check
that catches "moved behind an affordance" quietly becoming "deleted".

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.ts \
        frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "refactor(dashboard): move explanatory copy behind info drawers"
```

---

### Task R4-09: Reconcile the Dashboard against mockup sheet 1

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts`
- Modify: `frontend/src/app/workspaces/dashboard/trading-performance.ts`
- Test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes: the assembled page from R4-07.
- Produces: nothing new.

**Why this task exists.** R4-01…R4-08 were written against
`images/Mock up.png`. `images/Dashboard Trades Watchlist Risk.png` (sheet 1)
arrived later and shows the Dashboard again, in more detail. Spec D31 says the
Dashboard is **diffed and amended, not rewritten** — this task is that diff.

**Two divergences are already known; find the rest by looking.**

1. **The equity curve gains a range toggle** — sheet 1 shows
   `1D · 1W · 1M · YTD · 1Y · ALL`. Finding 7 constrains it: the payload is
   `equity_30d`, thirty **daily** points. `1D` has no intraday series behind
   it and `1Y`/`ALL` have no history behind them. Render only the ranges the
   data supports (`1W`, `1M`, and `ALL` meaning all thirty points) and omit the
   rest. **Do not render a disabled `1D` button** — an affordance that exists
   but never works is worse than its absence.
2. **The allocation donut has no honest occupant.** This book is one asset
   class with no cash line. Its slot takes **exposure by horizon** instead: a
   donut over open risk grouped by the plan's horizon, which is the real
   composition question this book has.

- [ ] **Step 1: Capture the current state**

With `npm start` running, screenshot `/dashboard` at 1440px. Open sheet 1
beside it and write the divergence list into the commit message you will use in
step 6. Anything not in the two known items above needs a judgement: is it a
real difference, or the same design drawn at a different zoom?

- [ ] **Step 2: Write the failing tests**

Add to `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`:

```typescript
it('offers only the equity ranges the 30-day series supports', () => {
  const labels = Array.from(
    (render().nativeElement as HTMLElement).querySelectorAll('.equity-range button'),
  ).map((b) => b.textContent!.trim());
  expect(labels).toEqual(['1W', '1M', 'ALL']);
});

it('does not render a range it cannot draw', () => {
  const labels = Array.from(
    (render().nativeElement as HTMLElement).querySelectorAll('.equity-range button'),
  ).map((b) => b.textContent!.trim());
  expect(labels).not.toContain('1D');
});

it('shows exposure by horizon where the mockup shows asset allocation', () => {
  const el = render().nativeElement as HTMLElement;
  expect(el.querySelector('sb-panel[heading="Exposure by horizon"]')).not.toBeNull();
  expect(el.textContent).not.toContain('Asset allocation');
});
```

- [ ] **Step 3: Run them to make sure they fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: FAIL on the three new assertions.

- [ ] **Step 4: Make the changes**

Add the three-button `sb-segmented` range control above the equity curve,
slicing `equity_30d` to the last 5 / 21 / all points. Replace the allocation
slot with an `sb-donut` over open risk grouped by horizon, computed from the
positions already on the payload — no new endpoint.

- [ ] **Step 5: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard
git commit -m "feat(dashboard): reconcile against mockup sheet 1 (v85 D31)

Equity range toggle limited to the ranges the 30-day series supports;
allocation slot carries exposure by horizon, which this book actually has."
```
