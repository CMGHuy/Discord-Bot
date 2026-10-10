# v151 Plan detail page and the shared "Why" panel: Part 3b, the plan page and both full suites

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V151-16:" -A 600 docs/superpowers/plans/2026-10-10-v151-plan-detail-why-panel_3b-plan-page-and-suites.md`.

**Bump:** ui minor · bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v151-plan-detail-why-panel-design.md`](../specs/2026-10-09-v151-plan-detail-why-panel-design.md)

This file continues Part 3 ([`_3-shared-components-and-pages`](2026-10-10-v151-plan-detail-why-panel_3-shared-components-and-pages.md)), which reached the 1500-line budget after V151-15. Global constraints, the decisions, the wire contract, the task ledger and `## Parallelisation` live in the index: [`2026-10-10-v151-plan-detail-why-panel_0-index.md`](2026-10-10-v151-plan-detail-why-panel_0-index.md). Part 3's header carries the component rules and the Part 2 contracts. The short version:

- V151-16 starts after V151-15, because its redirect lands on the trade page's arrival banner (`state: { from: 'plan' }`). V151-17 runs last, once.
- `workspaces/plans/plan-detail.ts` sits directly in a workspace directory, so `workspace-consistency.spec.ts` scans it: no `<h1`, `sb-panel` for cards, `[staleAsOf]` on its `sb-async`, `auto-fit` grids only. Because it uses `sb-async`, it never contains the literal class name `skeleton`. It never defines `.pos`, `.neg`, `.muted`, `.head`, `.row-link`, `.note` or `.chips` in `styles` (`ui/primitives.spec.ts`). It has no raw `<button>`.
- The page places, edits and cancels nothing. It carries no actions: those stay on the trade page.
- Narrow verification per task: `npm --prefix frontend test -- --include <spec> --watch=false`. **Never `cd` in Bash.** Stage files by name, never `git add -A`. Do not bump `VERSION.json`.

# Phase 6 (continued): the plan page

### Task V151-16: Plan page `plans/:id` + routes + redirects

**Model:** sonnet — a new routed page composing six components, with redirect logic that has to be exact (replaceUrl, banner state only on the terminal cases) and three gate files to register in.

**Files:**
- Create: `frontend/src/app/workspaces/plans/plan-detail.ts`
- Create: `frontend/src/app/workspaces/plans/plan-detail.routes.ts`
- Test: `frontend/src/app/workspaces/plans/plan-detail.spec.ts`
- Modify: `frontend/src/app/app.routes.ts` (beside `trades/:id`, `:44-51`)
- Modify: `frontend/src/app/app.routes.spec.ts` (readiness `expected` list `:110-113`, plus one new `it`)
- Modify: `frontend/src/app/ui/async-coverage.spec.ts` (`FETCHING`, `:14-34`)

**Interfaces:**
- Consumes:
  - `TradeDetailStore` (`setId(id, loadNow = true)`, which is a no-op for the same id; `resolve()`; `trade()`, `detail()`, `error()`, plus every computed V151-15 binds). V151-8 computeds: `expiresOn`, `timeExitOn`, `holdCapBars`, `acceptanceLevel`, `sessionsSinceCreated`, `confidencePoints`, `confidenceUnevaluated`, `gates`, `calendar`, `gapP90Pct`, `gapFragile`.
  - `ChartStore` (route-scoped, read by `sb-plan-chart`).
  - The six Group A components, with the inputs listed under V151-15: `WhyPanel` and `WHY_SECTIONS` (V151-9), `LevelsBlock` (V151-10), `IfItGetsThere` (V151-11), `SizingPanel` (V151-12), `OutcomePath` (V151-13), `PlanChart` (V151-14).
  - `routeData`, `onEvents` (`routing/route-metadata`) and `resolveRoute` (`routing/route-resolver`), used exactly as `trade-detail.routes.ts` uses them. `asyncInputs`, `Async` (`ui/async`).
  - V151-15's arrival contract: the trade page shows its banner when `history.state.from === 'plan'`.
  - V151-7 added `"plans"` to `spa.py` `WORKSPACES`, so `/plans/<id>` reloads into the SPA.
- Produces:
  - `export class PlanDetail` (selector `sb-plan-detail`), with input `id: string` (required, bound from the route by `withComponentInputBinding`).
  - `export const planDetailRoutes: Routes`.
  - `export function looksLikePlanId(id: string): boolean`. This mirrors `_looks_like_a_plan_id` (`swingbot/admin/api_v1/trades.py:648`): 36 characters and exactly 4 dashes.
  - `export function redirectFor(status: string | null, barsToExpiry: number | null): 'banner' | null`. It returns `'banner'` for CLOSED, for CANCELLED, and for PENDING with `barsToExpiry === 0`. Otherwise it returns `null`.
  - `export function timingLines(t: PlanTiming): string[]` and `export interface PlanTiming { status: string | null; expiresOn: string | null; barsToExpiry: number | null; holdCapBars: number | null; timeExitOn: string | null }`. These are local to this file and no other task uses them.

Page layout (spec § Plan page), one scrolling page with no tabs:
1. Header: ticker, direction, status indicator, `strategy · horizon`, badge, the `Lv` chip, the created date. Below that, the timing lines:
   - PENDING: `Expires <expires_on> at the close (ET) (<bars_to_expiry> bars left)`. A missing date renders `—`.
   - When `hold_cap_bars` is set: `Time exit after <n> sessions`, plus ` — <time_exit_on> at the close (ET)` once filled.
2. `<sb-levels-block>`.
3. PENDING only: `<sb-if-it-gets-there>` and `<sb-sizing-panel>`.
4. `<sb-why-panel>` with all five sections.
5. `<sb-plan-chart>`.
6. `<sb-outcome-path>`. A PENDING plan has no legs, so this shows the timeline alone.
7. The link `Open the full trade record` → `/trades/:id`.

Redirects use `router.navigate(['/trades', id], { replaceUrl: true, ... })`, so Back is not a loop:

| Case | Navigation extras |
|---|---|
| CLOSED, CANCELLED, or PENDING with `bars_to_expiry === 0` | `{ replaceUrl: true, state: { from: 'plan' } }` |
| id is not plan-shaped (legacy trade id) | `{ replaceUrl: true }`, with no `state` and no fetch |
| 404 | no navigation; `sb-async`'s error state |

The redirect check is an effect over `store.trade()`, so it runs again on every load, including the `trades`-event refetch when the plan closes while the page is open.

- [ ] **Step 1: Write the failing page tests**

Create `frontend/src/app/workspaces/plans/plan-detail.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import {
  Signal,
  WritableSignal,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { type MockInstance, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { ChartStore } from '../../stores/chart.store';
import { TradeDetailStore } from '../../stores/trade-detail.store';
import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { PlanDetail, looksLikePlanId, redirectFor, timingLines } from './plan-detail';

// The page renders sb-plan-chart, whose TradeChart asks for matchMedia.
installMatchMediaPolyfill();

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();

  changes(name: string): Signal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter.asReadonly();
  }
}

const PLAN_ID = '44444444-4444-4444-8444-444444444444';
const LEGACY_ID = 'aaaaaaaaaaaaaaaa';

const DETAIL = {
  trade_id: 'ffffffffffffffff',
  note: null,
  created_at: '2026-10-05T14:00:00+00:00',
  plan_source: 'scan',
  entry_type: 'stop_entry',
  trigger_price: 101.5,
  expiry_bars: 5,
  tp1_fraction: 0.5,
  breakeven_trigger_fraction: 0.6,
  explanation: 'Price reclaimed the 50-day after a three-week base.',
  confirmed_by: [{ strategy: 'VWAP', horizon_key: '2w' }],
  target_sources: ['Fib 1.618'],
  stop_sources: ['Swing low'],
  target2_sources: [],
  confidence_breakdown: { 'Trend alignment': 'above the 200-day' },
  quality_breakdown: [['Badge', 15]],
  status_history: [],
  legs: [],
  legs_realized: [],
  sizing_mode: 'risk_pct',
  working_stop: null,
  entry_context: { rs_pctile: 62, gap_p90_pct: 1.85, gap_fragile: false },
  risk_features: { days_to_earnings: null },
  cohort_label: 'COHORT_TYPICAL',
  confidence_points: null,
  confidence_unevaluated: [],
  gates: [{
    key: 'rs', label: 'Relative strength', value: 62, threshold: 0,
    margin: null, applies: false, parts: [], note: 'bullish arm disabled',
  }],
  sessions_since_created: 2,
  expires_on: '2026-10-12',
  time_exit_on: null,
  calendar: [{ date: '2026-10-16', kind: 'opex_monthly', label: 'Monthly OPEX' }],
  hold_cap_bars: null,
  acceptance_level: null,
};

function planResponse(status: string, overrides: object = {}, detail: object = {}) {
  return {
    id: PLAN_ID,
    origin: 'plan',
    status,
    ticker: 'AAPL',
    direction: 'bullish',
    strategy: 'RSI Divergence',
    horizon: '4w',
    tier: 'A',
    badge: 'VALIDATED',
    confidence_level: 4,
    confidence_score: 78,
    quality_score: 80,
    entry: status === 'PENDING' ? null : 101.5,
    stop_loss: 95,
    target: 110,
    target2: 118,
    risk_reward: 2,
    shares: 10,
    open_shares: 10,
    position_value: 1015,
    current_price: 103,
    current_price_stale: false,
    exit_price: null,
    realized_pnl_amount: null,
    pnl_pct: 1.5,
    r_multiple: null,
    held_hours: 30,
    opened_at: '2026-10-06T14:05:00Z',
    closed_at: null,
    has_note: false,
    progress_pct: 40,
    entry_pct: 33,
    progress_band: 'toward_target',
    blink_seconds: null,
    status_label: 'Moving toward target',
    bars_to_expiry: status === 'PENDING' ? 3 : null,
    detail: { ...DETAIL, ...detail },
    ...overrides,
  };
}

describe('PlanDetail', () => {
  let backend: HttpTestingController;
  let navigate: MockInstance<Router['navigate']>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  });

  function mount(id: string) {
    const fixture = TestBed.createComponent(PlanDetail);
    fixture.componentRef.setInput('id', id);
    fixture.detectChanges();
    return fixture;
  }

  function render(status: string, overrides: object = {}, detail: object = {}): HTMLElement {
    const fixture = mount(PLAN_ID);
    backend.expectOne(`/api/v1/trades/${PLAN_ID}`).flush(planResponse(status, overrides, detail));
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders an ACTIVE plan: header, levels, Why panel, chart, outcome path, record link', () => {
    const el = render('ACTIVE');
    const text = el.textContent ?? '';
    expect(text).toContain('AAPL');
    expect(text).toContain('RSI Divergence · 4w');
    expect(text).toContain('VALIDATED');
    expect(text).toContain('Lv4');
    expect(el.querySelector('sb-levels-block')).toBeTruthy();
    expect(el.querySelector('sb-why-panel')).toBeTruthy();
    expect(el.querySelector('sb-plan-chart')).toBeTruthy();
    expect(el.querySelector('sb-outcome-path')).toBeTruthy();
    expect(text).toContain("Gate margins (vs today's thresholds)");
    expect(text).toContain('Monthly OPEX');
    expect(text).toContain('Paper plan — this page places no orders.');
    const link = el.querySelector<HTMLAnchorElement>('a.record-link');
    expect(link?.textContent).toContain('Open the full trade record');
    expect(link?.getAttribute('href')).toBe(`/trades/${PLAN_ID}`);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('keeps the gap and sizing panels on the trade record for a filled plan', () => {
    const el = render('ACTIVE');
    expect(el.querySelector('sb-if-it-gets-there')).toBeNull();
    expect(el.querySelector('sb-sizing-panel')).toBeNull();
  });

  it('shows the expiry line, If-it-gets-there and Sizing for a PENDING plan', () => {
    const el = render('PENDING');
    const text = el.textContent ?? '';
    expect(text).toContain('Expires 2026-10-12 at the close (ET) (3 bars left)');
    expect(el.querySelector('sb-if-it-gets-there')).toBeTruthy();
    expect(el.querySelector('sb-sizing-panel')).toBeTruthy();
    expect(text).not.toContain('Scale-out');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('shows the time-exit line once a hold cap is set', () => {
    const text = render('ACTIVE', {}, { hold_cap_bars: 10, time_exit_on: '2026-10-19' })
      .textContent ?? '';
    expect(text).toContain('Time exit after 10 sessions — 2026-10-19 at the close (ET)');
  });

  for (const [status, overrides] of [
    ['CLOSED', {}],
    ['CANCELLED', {}],
    ['PENDING', { bars_to_expiry: 0 }],
  ] as const) {
    it(`redirects a ${status}${'bars_to_expiry' in overrides ? ' (expired)' : ''} plan to its trade record with the banner state`, () => {
      render(status, overrides);
      expect(navigate).toHaveBeenCalledWith(
        ['/trades', PLAN_ID],
        { replaceUrl: true, state: { from: 'plan' } },
      );
    });
  }

  it('redirects a legacy trade id without the banner state and without fetching', () => {
    mount(LEGACY_ID);
    expect(navigate).toHaveBeenCalledWith(['/trades', LEGACY_ID], { replaceUrl: true });
    backend.expectNone(`/api/v1/trades/${LEGACY_ID}`);
  });

  it('shows the error state on a 404 rather than redirecting', () => {
    const fixture = mount(PLAN_ID);
    backend.expectOne(`/api/v1/trades/${PLAN_ID}`).flush(
      { error: { code: 'not_found', message: `No trade with id '${PLAN_ID}'` } },
      { status: 404, statusText: 'Not Found' },
    );
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.failed')).toBeTruthy();
    expect(navigate).not.toHaveBeenCalled();
  });
});

describe('looksLikePlanId', () => {
  it('accepts a dashed uuid4 and rejects a trade id', () => {
    expect(looksLikePlanId(PLAN_ID)).toBe(true);
    expect(looksLikePlanId(LEGACY_ID)).toBe(false);
    expect(looksLikePlanId('')).toBe(false);
    expect(looksLikePlanId('4444444444444444444444444444444444-4')).toBe(false);
  });
});

describe('redirectFor', () => {
  it('sends the terminal cases to the trade record with the banner', () => {
    expect(redirectFor('CLOSED', null)).toBe('banner');
    expect(redirectFor('CANCELLED', null)).toBe('banner');
    expect(redirectFor('PENDING', 0)).toBe('banner');
  });

  it('keeps an open plan on the page', () => {
    expect(redirectFor('PENDING', 3)).toBeNull();
    expect(redirectFor('PENDING', null)).toBeNull();
    expect(redirectFor('ACTIVE', null)).toBeNull();
    expect(redirectFor('PARTIAL', null)).toBeNull();
    expect(redirectFor(null, null)).toBeNull();
  });
});

describe('timingLines', () => {
  const base = { status: 'ACTIVE', expiresOn: null, barsToExpiry: null, holdCapBars: null, timeExitOn: null };

  it('says nothing for a filled plan with no hold cap', () => {
    expect(timingLines(base)).toEqual([]);
  });

  it('words a pending expiry, with a dash for a date outside the calendar', () => {
    expect(timingLines({ ...base, status: 'PENDING', expiresOn: '2026-10-12', barsToExpiry: 3 }))
      .toEqual(['Expires 2026-10-12 at the close (ET) (3 bars left)']);
    expect(timingLines({ ...base, status: 'PENDING', barsToExpiry: 3 }))
      .toEqual(['Expires — at the close (ET) (3 bars left)']);
  });

  it('words the time exit before and after the fill', () => {
    expect(timingLines({ ...base, holdCapBars: 10 })).toEqual(['Time exit after 10 sessions']);
    expect(timingLines({ ...base, holdCapBars: 10, timeExitOn: '2026-10-19' }))
      .toEqual(['Time exit after 10 sessions — 2026-10-19 at the close (ET)']);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/plans/plan-detail.spec.ts --watch=false`
Expected: FAIL, because `./plan-detail` cannot be resolved.

- [ ] **Step 3: Write the page**

Create `frontend/src/app/workspaces/plans/plan-detail.ts`:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  untracked,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { TradeDetailStore } from '../../stores/trade-detail.store';
import { asyncInputs, Async } from '../../ui/async';
import { QualityChip } from '../../ui/chip';
import { dateTime, text } from '../../ui/format';
import { StatusIndicator } from '../../ui/status-indicator';
import { IfItGetsThere } from '../trades/why/if-it-gets-there';
import { LevelsBlock } from '../trades/why/levels-block';
import { OutcomePath } from '../trades/why/outcome-path';
import { PlanChart } from '../trades/why/plan-chart';
import { SizingPanel } from '../trades/why/sizing-panel';
import { WHY_SECTIONS, WhyPanel } from '../trades/why/why-panel';

/** `_looks_like_a_plan_id` (`swingbot/admin/api_v1/trades.py:648`): plan ids
 *  are 36-char dashed uuid4s, trade ids 16 dash-free characters. */
export function looksLikePlanId(id: string): boolean {
  return id.length === 36 && id.split('-').length - 1 === 4;
}

/** A plan whose open life is over goes to its trade record, with the banner
 *  that says why (spec v151 § Redirects). A Discord link outlives the plan
 *  and must still land somewhere useful. */
export function redirectFor(status: string | null, barsToExpiry: number | null): 'banner' | null {
  if (status === 'CLOSED' || status === 'CANCELLED') return 'banner';
  if (status === 'PENDING' && barsToExpiry === 0) return 'banner';
  return null;
}

export interface PlanTiming {
  status: string | null;
  expiresOn: string | null;
  barsToExpiry: number | null;
  holdCapBars: number | null;
  timeExitOn: string | null;
}

const AT_CLOSE = 'at the close (ET)';

/** Expiry and the time exit both resolve on a daily bar, so each date reads
 *  as a session date "at the close (ET)". A date outside the session
 *  calendar's coverage arrives as null and renders as a dash, never hidden. */
export function timingLines(t: PlanTiming): string[] {
  const lines: string[] = [];
  if (t.status === 'PENDING') {
    const left = t.barsToExpiry === null ? '' : ` (${t.barsToExpiry} bars left)`;
    lines.push(`Expires ${t.expiresOn ?? '—'} ${AT_CLOSE}${left}`);
  }
  if (t.holdCapBars !== null) {
    const on = t.timeExitOn ? ` — ${t.timeExitOn} ${AT_CLOSE}` : '';
    lines.push(`Time exit after ${t.holdCapBars} sessions${on}`);
  }
  return lines;
}

/**
 * One open plan, end to end (spec v151): the levels order-ready, the Why
 * panel, the chart and how it is playing out, on one scrolling page.
 * Reached from a Discord alert's title link.
 *
 * Read-only on purpose. The bot is paper-only, and this page places, edits
 * and cancels nothing; the actions stay on the trade record it links to.
 * A plan that is over redirects there (see `redirectFor`).
 */
@Component({
  selector: 'sb-plan-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    Async,
    QualityChip,
    StatusIndicator,
    WhyPanel,
    LevelsBlock,
    IfItGetsThere,
    SizingPanel,
    OutcomePath,
    PlanChart,
  ],
  template: `
    <header class="plan-head">
      <a class="back" routerLink="/trades">← Trades</a>

      @if (store.trade(); as trade) {
        <div class="plan-title" role="heading" aria-level="2">
          <span class="ticker">{{ trade.ticker }}</span>
          <span class="tag">{{ fmtText(trade.direction) }}</span>
          <sb-status-indicator
            [status]="trade.status"
            [current]="trade.current_price"
            [entry]="trade.entry"
            [stop]="trade.stop_loss"
            [target]="trade.target"
          />
        </div>
        <div class="tags">
          @if (strategyLine(); as line) {
            <span class="tag">{{ line }}</span>
          }
          @if (trade.badge) {
            <span class="tag">{{ trade.badge }}</span>
          }
          @if (trade.confidence_level !== null) {
            <sb-quality-chip
              [value]="trade.confidence_level"
              [label]="'Lv' + trade.confidence_level"
            />
          }
          @if (createdAt(); as at) {
            <span class="created">created {{ fmtDate(at) }}</span>
          }
        </div>
        @for (line of timing(); track line) {
          <p class="timing">{{ line }}</p>
        }
      } @else if (store.error(); as message) {
        <p class="plan-title" role="status">{{ message }}</p>
      } @else {
        <!-- Not the sb-async placeholder class: this file uses sb-async, and
             async-coverage.spec.ts bans that literal class name here. -->
        <p class="plan-title loading-title" role="status">Loading…</p>
      }
    </header>

    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="measured-zero"
      emptyTitle="Plan not found"
      [skeletonRows]="3"
      [skeletonCols]="4"
      (retry)="store.load()"
    >
      @if (store.trade(); as trade) {
        <div class="body">
          <div class="panels">
            <sb-levels-block
              [direction]="trade.direction"
              [entryType]="store.detail()?.entry_type ?? null"
              [trigger]="store.triggerPrice()"
              [entry]="trade.entry"
              [stop]="trade.stop_loss"
              [stopLabel]="stopLabel()"
              [target1]="trade.target"
              [target2]="trade.target2"
              [riskReward]="trade.risk_reward"
              [acceptanceLevel]="store.acceptanceLevel()"
              [tp1Pct]="store.tp1Pct()"
              [breakevenTriggerPct]="store.breakevenTriggerPct()"
            />
            <!-- PENDING only: the gap and sizing picture before the trigger
                 fires. A filled plan keeps them on its trade record. -->
            @if (trade.status === 'PENDING') {
              <sb-if-it-gets-there
                [direction]="trade.direction"
                [target2]="trade.target2"
                [stopLoss]="trade.stop_loss"
              />
              <sb-sizing-panel
                [shares]="trade.shares"
                [positionValue]="trade.position_value"
                [sizingMode]="store.detail()?.sizing_mode ?? null"
                [workingStop]="store.detail()?.working_stop ?? null"
                [gapP90Pct]="store.gapP90Pct()"
                [gapFragile]="store.gapFragile()"
              />
            }
          </div>

          <sb-why-panel
            [sections]="sections"
            [status]="trade.status"
            [barsToExpiry]="trade.bars_to_expiry"
            [sessionsSinceCreated]="store.sessionsSinceCreated()"
            [entry]="trade.entry"
            [trigger]="store.triggerPrice()"
            [stop]="trade.stop_loss"
            [stopLabel]="stopLabel()"
            [target1]="trade.target"
            [target2]="trade.target2"
            [acceptanceLevel]="store.acceptanceLevel()"
            [targetSources]="store.targetSources()"
            [stopSources]="store.stopSources()"
            [target2Sources]="store.target2Sources()"
            [confirmedBy]="store.confirmedBy()"
            [confidencePoints]="store.confidencePoints()"
            [confidenceUnevaluated]="store.confidenceUnevaluated()"
            [confidenceFactors]="store.confidenceFactors()"
            [qualityFactors]="store.qualityFactors()"
            [gates]="store.gates()"
            [calendar]="store.calendar()"
            [explanation]="store.explanation()"
          />

          <sb-plan-chart [ticker]="trade.ticker" [tradeId]="trade.id" />

          <sb-outcome-path [legs]="store.legs()" [timeline]="store.timeline()" />

          <a class="record-link" [routerLink]="['/trades', id()]">Open the full trade record</a>
        </div>
      }
    </sb-async>
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: var(--section-gap); }
    .plan-head {
      display: grid;
      gap: var(--space-8);
    }
    .back, .record-link {
      color: var(--accent);
      font-size: var(--text-table);
      text-decoration: none;
    }
    .back:hover, .record-link:hover {
      text-decoration: underline;
    }
    .plan-title {
      margin: 0;
      display: flex;
      align-items: center;
      gap: var(--space-10);
      font-size: var(--text-title);
      font-weight: 600;
    }
    .ticker {
      font-family: var(--font-mono);
    }
    .loading-title {
      color: var(--text-faint);
    }
    .tags {
      display: flex;
      align-items: center;
      gap: var(--space-6);
      flex-wrap: wrap;
    }
    .tag {
      padding: 1px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-chip);
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }
    .created, .timing {
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    .body {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: var(--section-gap);
    }
    .panels {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: var(--section-gap);
      align-items: start;
    }
  `,
})
export class PlanDetail {
  private readonly router = inject(Router);
  protected readonly store = inject(TradeDetailStore);

  readonly id = input.required<string>();

  protected readonly async = computed(() => asyncInputs(this.store, { isEmpty: () => false }));
  protected readonly sections = WHY_SECTIONS;

  protected readonly fmtText = text;
  protected readonly fmtDate = dateTime;

  /** Same rule as the trade page: a PARTIAL plan's stop is the runner's. */
  protected readonly stopLabel = computed(() =>
    this.store.trade()?.status === 'PARTIAL' ? 'Trailing stop' : 'Stop',
  );

  protected readonly strategyLine = computed(() => {
    const trade = this.store.trade();
    return [trade?.strategy, trade?.horizon].filter((part) => !!part).join(' · ');
  });

  protected readonly createdAt = computed(() => this.store.detail()?.created_at ?? null);

  protected readonly timing = computed(() => {
    const trade = this.store.trade();
    if (!trade) return [];
    return timingLines({
      status: trade.status,
      expiresOn: this.store.expiresOn(),
      barsToExpiry: trade.bars_to_expiry ?? null,
      holdCapBars: this.store.holdCapBars(),
      timeExitOn: this.store.timeExitOn(),
    });
  });

  constructor() {
    // A legacy trade id has no plan page: hand it to the trade record at
    // once, without fetching it here and without the banner state.
    effect(() => {
      const id = this.id();
      if (!looksLikePlanId(id)) {
        untracked(() => this.leave(id, false));
        return;
      }
      this.store.setId(id);
    });

    // Runs on every load, so a plan that closes while the page is open (the
    // store refetches on the `trades` event) still redirects.
    effect(() => {
      const trade = this.store.trade();
      const id = this.id();
      if (!trade || !looksLikePlanId(id)) return;
      if (redirectFor(trade.status, trade.bars_to_expiry ?? null) === 'banner') {
        untracked(() => this.leave(id, true));
      }
    });
  }

  /** replaceUrl: Back from the trade record must not land on this page and
   *  bounce straight back. */
  private leave(id: string, banner: boolean): void {
    this.router.navigate(
      ['/trades', id],
      banner ? { replaceUrl: true, state: { from: 'plan' } } : { replaceUrl: true },
    );
  }
}
```

`store.load()` (the retry) exists on `TradeDetailStore` (`trade-detail.store.ts:544`). It also fetches the journal, as on the trade page.

- [ ] **Step 4: Run the page tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/workspaces/plans/plan-detail.spec.ts --watch=false`
Expected: PASS (15 tests).

If the 404 test finds no `.failed`, check how `trade-detail.spec.ts`'s `'shows the error state on a first-load failure'` reaches it (a 503). `sb-async` renders the same error block for any status once `store.error()` is set and nothing is loading.

- [ ] **Step 5: Write the route file**

Create `frontend/src/app/workspaces/plans/plan-detail.routes.ts`:

```ts
import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { ChartStore } from '../../stores/chart.store';
import { TradeDetailStore } from '../../stores/trade-detail.store';

/** Mirrors `trade-detail.routes.ts`: the same route-scoped stores and the same
 *  resolver, because the plan page reads the same `GET /api/v1/trades/:id`
 *  (it already resolves plan ids). Refetches on `trades` and `journal`, so a
 *  plan that closes while the page is open redirects on the next load. */
export const planDetailRoutes: Routes = [{
  path: '',
  providers: [TradeDetailStore, ChartStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Plan', onEvents('trades', 'journal')),
  resolve: {
    ready: resolveRoute((route) => {
      const store = inject(TradeDetailStore);
      store.setId(route.paramMap.get('id')!, false);
      return store.resolve();
    }),
  },
  loadComponent: () => import('./plan-detail').then((m) => m.PlanDetail),
}];
```

- [ ] **Step 6: Register the route, with a failing routing test first**

In `frontend/src/app/app.routes.spec.ts`, add `'plans/:id'` (after `'trades/:id'`) to the current readiness `expected` list (`:110-113`), keeping every entry already there (v150 V150-12 adds `'research'`, `'reports'`); never paste the literal below over it. On today's list:

```ts
  const expected = [
    'dashboard', 'trades', 'trades/:id', 'plans/:id', 'analytics', 'calendar', 'watchlist',
    'watchlist/:symbol', 'risk', 'system', 'versions',
  ] as const;
```

Then add this `it` inside the same `describe` as `'serves the calendar workspace behind the auth guard'`, directly after that test:

```ts
  it('serves the plan page behind the auth guard (v151)', async () => {
    const route = routes.find((r) => r.path === 'plans/:id');
    expect(route).toBeDefined();
    expect(route?.canMatch).toEqual([authGuard]);
    expect(route?.title).toBe('Plan detail');
    expect(route?.data?.['subtitle']).toBe('Why this plan, and how it is going');

    const children = await route!.loadChildren!() as Routes;
    expect(children[0]?.loadComponent).toBeTypeOf('function');
    expect(await children[0]!.loadComponent!()).toBeDefined();
  });
```

Run: `npm --prefix frontend test -- --include src/app/app.routes.spec.ts --watch=false`
Expected: FAIL. No route has the path `plans/:id`.

In `frontend/src/app/app.routes.ts`, insert directly after the `trades/:id` route object (after `:51`):

```ts
  {
    // v151: one open plan, reached from a Discord alert's title link. Its
    // own route-scoped stores and resolver, like Trade Detail. spa.py's
    // WORKSPACES lists `plans` so a reload of /plans/<id> serves the SPA.
    path: 'plans/:id',
    canMatch: [authGuard],
    title: 'Plan detail',
    data: { subtitle: 'Why this plan, and how it is going' },
    loadChildren: () => import('./workspaces/plans/plan-detail.routes').then((m) => m.planDetailRoutes),
  },
```

Run: `npm --prefix frontend test -- --include src/app/app.routes.spec.ts --watch=false`
Expected: PASS.

- [ ] **Step 7: Register the page with the fetch-coverage gate**

In `frontend/src/app/ui/async-coverage.spec.ts`, add this line to `FETCHING` (`:14-34`), directly after `'workspaces/trades/trade-detail.ts',`:

```ts
  // v151's plan page: the same detail fetch as the trade page.
  'workspaces/plans/plan-detail.ts',
```

Run: `npm --prefix frontend test -- --include src/app/ui/async-coverage.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --watch=false`
Expected: PASS. If `primitives.spec.ts` flags `plan-detail.ts`, the cause is a class it bans (`.head`, `.note`, `.pos`, …) or a raw `<button>`. Rename the class. Do not add an allowlist entry.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/workspaces/plans/plan-detail.ts frontend/src/app/workspaces/plans/plan-detail.routes.ts frontend/src/app/workspaces/plans/plan-detail.spec.ts frontend/src/app/app.routes.ts frontend/src/app/app.routes.spec.ts frontend/src/app/ui/async-coverage.spec.ts
git commit -m "feat(ui): v151 plan page plans/:id with redirects to the trade record (V151-16)"
```

### Task V151-17: Full suites, complexity check

**Model:** haiku — runs fixed commands and reads verdicts; any failure goes back to the task that owns the file.

**Files:**
- None created or modified. A failure is fixed in the owning task's files, under that task's id (see the ledger), never patched here.

**Interfaces:**
- Consumes: every earlier task (V151-1 .. V151-16) merged on the implementation branch.
- Produces: the green verdicts the controller records before `/close-out`.

This is the one full run of each suite for the plan (index § Global Constraints). Do not run either suite earlier as a check.

- [ ] **Step 1: Complexity on every Python file the plan touched**

Run:

```bash
python -m radon cc -s -n C swingbot/core/market/session.py swingbot/core/presentation/why_view.py swingbot/admin/trade_why.py swingbot/admin/api_v1/trades.py swingbot/core/presentation/components.py swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/execution_embeds.py swingbot/core/scanning/lifecycle_embeds.py swingbot/commands/views.py swingbot/commands/trades.py swingbot/admin/spa.py swingbot/config.py
```

Expected: every function this plan added or changed scores **below 15**. `-n C` prints grade C (11-20) and worse, so a listed function is not by itself a failure: read its number. A listed function the plan added or changed with a score of 15 or more is a failure. A legacy function already at 15 or more may be listed, but its score must not have risen. Check `get_trade`, `_plan_detail` and `_legacy_detail` against `main`:

```bash
git show main:swingbot/admin/api_v1/trades.py > "$TMPDIR/trades_main.py" && python -m radon cc -s "$TMPDIR/trades_main.py" | grep -E "get_trade|_plan_detail|_legacy_detail"; python -m radon cc -s swingbot/admin/api_v1/trades.py | grep -E "get_trade|_plan_detail|_legacy_detail"
```

Expected: each of the three has the same score on the branch as on `main` (`_plan_detail` C 11, `_legacy_detail` B 6, `get_trade` B 7), or lower. If `$TMPDIR` is unset in Git Bash, use the session scratchpad directory instead.

- [ ] **Step 2: Syntax pass**

Run: `python -m py_compile bot.py admin_ui.py swingbot/core/market/session.py swingbot/core/presentation/why_view.py swingbot/admin/trade_why.py swingbot/admin/api_v1/trades.py swingbot/core/presentation/components.py swingbot/config.py swingbot/admin/spa.py`
Expected: no output.

- [ ] **Step 3: Python full suite (via the `test-runner` agent)**

Dispatch the `test-runner` subagent with: `python scripts/dev/testrun.py full`.
Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`testing-cost.md`). Do not run the suite in this context.

- [ ] **Step 4: Frontend full suite and production build**

Run: `npm --prefix frontend test -- --watch=false`
Expected: every spec passes, including `workspace-consistency.spec.ts`, `ui/async-coverage.spec.ts`, `ui/primitives.spec.ts`, `app.routes.spec.ts`, `trade-detail.spec.ts` and the eight new specs under `workspaces/trades/why/` and `workspaces/plans/`.

Run: `npm --prefix frontend run build`
Expected: the build completes with no type errors. It runs the template type-check that Vitest does not run in full. That check catches an input binding whose type does not match, for example a `number | undefined` bound to a `number | null` input.

- [ ] **Step 5: Record the result**

Append one line to `.superpowers/sdd/progress.md` (never `cat` it, append only):

```bash
echo "$(date -u +%Y-%m-%dT%H:%MZ) v151 V151-17: radon clean, py full <verdict line>, frontend test <N passed>, build ok" >> .superpowers/sdd/progress.md
```

Fill in the two verdicts from Steps 3 and 4. There is no commit in this task. The controller commits any fixes under their own task ids and then runs `/close-out`, which applies `ui minor · bot patch` to `VERSION.json` and regenerates `version_history.json`.

After the merge, and not as a task here: setting `ADMIN_PUBLIC_URL` on the VM is the partner's decision. See the index's `## After merge` section.

