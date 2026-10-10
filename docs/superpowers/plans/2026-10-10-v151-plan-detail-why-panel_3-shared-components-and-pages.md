# v151 Plan detail page and the shared "Why" panel: Part 3, outcome path, plan chart, both pages, full suites

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V151-15:" -A 600 docs/superpowers/plans/2026-10-10-v151-plan-detail-why-panel_3-shared-components-and-pages.md`.

**Bump:** ui minor · bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v151-plan-detail-why-panel-design.md`](../specs/2026-10-09-v151-plan-detail-why-panel-design.md)

Global constraints, the decisions, the wire contract, the task ledger and `## Parallelisation` live in the index: [`2026-10-10-v151-plan-detail-why-panel_0-index.md`](2026-10-10-v151-plan-detail-why-panel_0-index.md). The short version for this part:

- V151-13 and V151-14 belong to Group A (parallel after V151-8, alongside V151-9..12). V151-15 starts only after all six Group A components exist. V151-16 follows V151-15. V151-17 runs last.
- Components under `workspaces/trades/why/` never define `.pos`, `.neg`, `.muted`, `.head`, `.row-link`, `.note` or `.chips` in `styles` (`ui/primitives.spec.ts`). Use the globals from `styles.css`. No hex colours. No raw `<button>` (use `sb-button`, or the retry `sb-chart-container` already owns).
- `workspaces/plans/plan-detail.ts` sits directly in a workspace directory, so `workspace-consistency.spec.ts` scans it: no `<h1`, `sb-panel` for cards, `[staleAsOf]` on its `sb-async`, `auto-fit` grids only. It uses `sb-async`, so it never contains the literal class name `skeleton` (`async-coverage.spec.ts`).
- Contracts from Part 2 (committed): the Why panel keeps the labels `Target confirmed by` / `Stop confirmed by` / `Target 2 confirmed by` and a `Confirmed by` label, plus the headings `Confidence breakdown`, `Quality breakdown`, `Why this trade`. Quality and confidence points keep the ASCII sign format (`+15`, `-5`). Its `sb-panel`s never get a `digest`, so the gate caveat cannot be collapsed. Store computeds available on `TradeDetailStore` from V151-8: `confidencePoints`, `confidenceUnevaluated`, `gates`, `calendar`, `entryContext`, `riskFeatures`, `sessionsSinceCreated`, `expiresOn`, `timeExitOn`, `holdCapBars`, `acceptanceLevel`, `gapP90Pct`, `gapFragile`.
- Narrow verification per task: `npm --prefix frontend test -- --include <spec> --watch=false`. **Never `cd` in Bash.** Stage files by name, never `git add -A`. Do not bump `VERSION.json`.

# Phase 5 (continued): the last two shared components

### Task V151-13: `sb-outcome-path`

**Model:** sonnet — a behaviour-preserving extraction of two panels whose existing trade-page assertions must keep passing, plus one store-backed test.

**Files:**
- Create: `frontend/src/app/workspaces/trades/why/outcome-path.ts`
- Test: `frontend/src/app/workspaces/trades/why/outcome-path.spec.ts`

**Interfaces:**
- Consumes: `Leg`, `StatusEvent` (exported from `frontend/src/app/stores/trade-detail.store.ts:42-55`, unchanged by V151-8); `Panel` (`ui/layout`); `dateTime`, `num`, `rMultiple`, `share` (`ui/format`). Extracted from `trade-detail.ts:497-550` (the Live tab's `Scale-out` and `Timeline` panels). `trade-detail.ts` itself is not edited here; V151-15 swaps the panels for this component.
- Produces: `export class OutcomePath` (selector `sb-outcome-path`); inputs `legs: Leg[]` (default `[]`) and `timeline: StatusEvent[]` (default `[]`).

Behaviour is the trade page's, unchanged:
- `Scale-out` renders only when there is more than one leg. One leg is not a scale-out.
- The first leg is labelled `First` and every later leg `Runner`. A leg with no exit price reads `still open`.
- `Timeline` renders only when there is at least one event. Each event shows its status, then its reason, then its time.
- A PENDING plan has no legs, so it shows the timeline alone (spec § Plan page item 6). That needs no input of its own.
- "Realized preferred over live" is the store's `legs` computed (`trade-detail.store.ts:300-305`: `legs_realized` wins over `legs`). The last test pins that the component renders whatever that computed hands it.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/workspaces/trades/why/outcome-path.spec.ts`:

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
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../../../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../../api/interceptors';
import { Leg, StatusEvent, TradeDetailStore } from '../../../stores/trade-detail.store';
import { OutcomePath } from './outcome-path';

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

const TWO_LEGS: Leg[] = [
  { fraction: 0.5, exitPrice: 110, r: 1.2, reason: 'TP1' },
  { fraction: 0.5, exitPrice: null, r: null, reason: null },
];

const TIMELINE: StatusEvent[] = [
  { status: 'CREATED', reason: 'scan', at: '2026-08-01T09:30:00Z' },
  { status: 'ACTIVE', reason: 'trigger filled', at: '2026-08-02T14:05:00Z' },
];

describe('OutcomePath', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(legs: Leg[], timeline: StatusEvent[]): HTMLElement {
    const fixture = TestBed.createComponent(OutcomePath);
    fixture.componentRef.setInput('legs', legs);
    fixture.componentRef.setInput('timeline', timeline);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders the scale-out legs, saying which is still open', () => {
    const text = render(TWO_LEGS, TIMELINE).textContent ?? '';
    expect(text).toContain('Scale-out');
    expect(text).toContain('First');
    expect(text).toContain('Runner');
    expect(text).toContain('50%');
    expect(text).toContain('110.00');
    expect(text).toContain('+1.20R');
    expect(text).toContain('TP1');
    expect(text).toContain('still open');
  });

  it('colours a closed leg by the sign of its R', () => {
    const el = render(TWO_LEGS, TIMELINE);
    expect(el.querySelector('.factors .pos')?.textContent).toContain('+1.20R');
  });

  it('shows no Scale-out panel for a single leg', () => {
    const text = render([{ fraction: 1, exitPrice: null, r: null, reason: null }], TIMELINE)
      .textContent ?? '';
    expect(text).not.toContain('Scale-out');
  });

  it('renders the timeline in order with reasons', () => {
    const el = render(TWO_LEGS, TIMELINE);
    const statuses = [...el.querySelectorAll('.tl-status')].map((n) => n.textContent?.trim());
    expect(statuses).toEqual(['CREATED', 'ACTIVE']);
    expect(el.textContent).toContain('Timeline');
    expect(el.textContent).toContain('trigger filled');
  });

  it('shows the timeline alone for a pending plan (no legs yet)', () => {
    const text = render([], [TIMELINE[0]]).textContent ?? '';
    expect(text).toContain('Timeline');
    expect(text).toContain('CREATED');
    expect(text).not.toContain('Scale-out');
  });

  it('renders nothing at all with no legs and no events', () => {
    const el = render([], []);
    expect(el.querySelector('sb-panel')).toBeNull();
  });
});

describe('OutcomePath fed by the store', () => {
  const ID = 'ffffffffffffffff';

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
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
  });

  it('renders the realized legs when the store has both realized and live ones', () => {
    const store = TestBed.inject(TradeDetailStore);
    const backend = TestBed.inject(HttpTestingController);
    store.setId(ID);
    // Partial row: the store only reads `detail` for these two computeds.
    backend.expectOne(`/api/v1/trades/${ID}`).flush({
      id: ID,
      detail: {
        created_at: null,
        status_history: [],
        legs: [
          { fraction: 0.5, exit_price: 999, r: 9.9, reason: 'live' },
          { fraction: 0.5, exit_price: null, r: null, reason: null },
        ],
        legs_realized: [
          { fraction: 0.5, exit_price: 110, r: 2.0, reason: 'tp1' },
          { fraction: 0.5, exit_price: 104, r: 0.8, reason: 'trail' },
        ],
      },
    });

    const fixture = TestBed.createComponent(OutcomePath);
    fixture.componentRef.setInput('legs', store.legs());
    fixture.componentRef.setInput('timeline', store.timeline());
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('+2.00R');
    expect(text).toContain('trail');
    expect(text).not.toContain('999');
  });
});
```

The store's `load()` also asks for the trade's journal. That request is left open on purpose, exactly as `trade-detail.spec.ts` does. This spec never calls `backend.verify()`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/outcome-path.spec.ts --watch=false`
Expected: FAIL, because `./outcome-path` cannot be resolved.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/trades/why/outcome-path.ts`:

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { Leg, StatusEvent } from '../../../stores/trade-detail.store';
import { dateTime, num, rMultiple, share } from '../../../ui/format';
import { Panel } from '../../../ui/layout';

/**
 * How a plan has played out (spec v151): the scale-out legs and the status
 * timeline. Extracted from the trade page's Live tab so the plan page can
 * show the same path. Plain inputs only; the page passes the store's `legs`
 * and `timeline` computeds in.
 */
@Component({
  selector: 'sb-outcome-path',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <!-- Scale-out legs. A position that took TP1 and is riding a runner
         is TWO results, and a single P&L figure describes neither. -->
    @if (legs().length > 1) {
      <sb-panel heading="Scale-out">
        <dl class="factors">
          @for (leg of legs(); track $index) {
            <div>
              <dt>
                @if ($index === 0) { First } @else { Runner }
                @if (leg.fraction !== null) {
                  <span class="muted muted-gap">{{ fmtShare(leg.fraction * 100) }}</span>
                }
              </dt>
              <dd class="num">
                @if (leg.exitPrice !== null) {
                  {{ fmt(leg.exitPrice) }}
                  @if (leg.r !== null) {
                    <span [class]="pnlClass(leg.r)">{{ fmtR(leg.r) }}</span>
                  }
                  @if (leg.reason) {
                    <span class="muted muted-gap">{{ leg.reason }}</span>
                  }
                } @else {
                  <span class="muted muted-gap">still open</span>
                }
              </dd>
            </div>
          }
        </dl>
      </sb-panel>
    }

    <!-- The plan's audit trail. Every transition carries the reason it
         happened, which is the only place "why did this cancel" is
         answered. -->
    @if (timeline().length) {
      <sb-panel heading="Timeline">
        <ol class="timeline">
          @for (event of timeline(); track $index) {
            <li>
              <span class="tl-status">{{ event.status }}</span>
              @if (event.reason) {
                <span class="tl-reason">{{ event.reason }}</span>
              }
              @if (event.at) {
                <span class="tl-at">{{ fmtDate(event.at) }}</span>
              }
            </li>
          }
        </ol>
      </sb-panel>
    }
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }
    dl {
      display: grid;
      gap: var(--space-6);
    }
    dl > div {
      display: flex;
      justify-content: space-between;
      gap: var(--space-10);
    }
    dt {
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    dd {
      color: var(--text);
      font-size: var(--text-table);
    }
    .factors > div {
      align-items: baseline;
      gap: var(--space-14);
    }
    .factors dd {
      text-align: right;
    }
    .muted-gap {
      margin-left: var(--space-6);
    }
    /* A rule down the left with a node per event: the shape says "these
       happened in order", which a plain list does not. */
    .timeline {
      display: grid;
      gap: var(--space-8);
      margin-left: var(--space-6);
      padding-left: var(--space-14);
      border-left: 1px solid var(--border-strong);
      list-style: none;
    }
    .timeline li {
      position: relative;
      font-size: var(--text-table);
    }
    .timeline li::before {
      content: '';
      position: absolute;
      left: calc(-1 * var(--space-14) - 3px);
      top: 0.45em;
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: var(--border-strong);
    }
    .tl-status {
      color: var(--text);
      font-weight: 600;
    }
    .tl-reason {
      margin-left: var(--space-6);
      color: var(--text-secondary);
    }
    .tl-at {
      margin-left: var(--space-6);
      color: var(--text-faint);
      font-size: var(--text-chip);
    }
  `,
})
export class OutcomePath {
  readonly legs = input<Leg[]>([]);
  readonly timeline = input<StatusEvent[]>([]);

  protected readonly fmt = num;
  protected readonly fmtShare = share;
  protected readonly fmtR = rMultiple;
  protected readonly fmtDate = dateTime;

  /** The trade page's own valence rule: the sign picks the global class. */
  protected pnlClass(value: number | null | undefined): string {
    if (value === null || value === undefined) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  }
}
```

If the store-backed test fails because the store's `legs` computed no longer prefers `legs_realized`, stop and report it. This task does not edit the store.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/outcome-path.spec.ts --watch=false`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades/why/outcome-path.ts frontend/src/app/workspaces/trades/why/outcome-path.spec.ts
git commit -m "feat(ui): v151 extract the outcome path (scale-out legs + timeline) (V151-13)"
```

### Task V151-14: `sb-plan-chart`

**Model:** sonnet — moves the chart wiring into a component that drives an injected store, and the tests must settle real HTTP requests through `ChartStore`.

**Files:**
- Create: `frontend/src/app/workspaces/trades/why/plan-chart.ts`
- Test: `frontend/src/app/workspaces/trades/why/plan-chart.spec.ts`

**Interfaces:**
- Consumes: `ChartStore` (`frontend/src/app/stores/chart.store.ts`: `setTarget(ticker, tradeId)` at `:126`, which is a no-op for the same pair; `data()`, `loading()`, `error()`, `isEmpty()`, `retry()`). `ChartContainer` (`ui/chart-container`: inputs `loading`, `error`, `hasData`, `height`, `caption`, `canRetry`; output `retry`; its error overlay renders a `.retry` button). `TradeChart` (`ui/chart/trade-chart`, input `data`). Extracted from `trade-detail.ts:551-563` (the Chart tab), `chartCaption` (`:1133-1147`) and `chartEmpty` (`:1150`).
- Produces: `export class PlanChart` (selector `sb-plan-chart`); inputs `ticker: string | null` and `tradeId: string | null`, both defaulting to `null`. It injects `ChartStore` from its injector (route-scoped on both pages) and calls `chart.setTarget(ticker, tradeId)` in an effect (index decision 9). `trade-detail.ts` keeps its own `setTarget` effect, so the chart still preloads before the Chart tab opens. `setTarget` is idempotent, so the two effects cost one request.

The caption is the trade page's: `<ticker> — daily, with this plan's levels`, plus the overlays' sources joined with ` · ` when the chart draws any. It is `null` until a ticker is known. "Empty" is `ChartStore.isEmpty()`: the request came back with no bars. Null data (still loading, or between targets) is not empty.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/workspaces/trades/why/plan-chart.spec.ts`:

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
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../../../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../../api/interceptors';
import { ChartResponse } from '../../../api/models';
import { ChartStore } from '../../../stores/chart.store';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { PlanChart } from './plan-chart';

// PlanChart renders a real TradeChart once bars arrive, and lightweight-charts
// asks for matchMedia the moment a chart exists. See the polyfill for why.
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

const ID = '44444444-4444-4444-8444-444444444444';

const RESPONSE: ChartResponse = {
  ticker: 'AAPL',
  ohlcv: [
    { t: 1_767_312_000, o: 1, h: 2, l: 0.5, c: 1.5, v: 100 },
    { t: 1_767_398_400, o: 1.5, h: 2.5, l: 1, c: 2, v: 120 },
  ],
  indicators: {
    rsi: [null, 55],
    macd: { line: [null, 0.4], signal: [null, 0.2], hist: [null, 0.2] },
    kc: { upper: [null, 2.4], lower: [null, 0.6] },
  },
  volume_profile: [{ price: 1.5, volume: 220 }],
  levels: { entry: 1.4, stop: 1.1, target1: 2.2, target2: null, working_stop: 1.2 },
  overlays: [
    {
      side: 'target',
      source: 'EMA20',
      shape: { kind: 'curve', label: 'EMA20', points: [[1_767_312_000, 1.2]] },
    },
  ],
  notes: [],
  currency: '$',
};

describe('PlanChart', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  function mount(ticker: string | null, tradeId: string | null) {
    const fixture = TestBed.createComponent(PlanChart);
    fixture.componentRef.setInput('ticker', ticker);
    fixture.componentRef.setInput('tradeId', tradeId);
    fixture.detectChanges();
    return fixture;
  }

  const chartRequest = () =>
    backend.expectOne((req) => req.url === '/api/v1/market/chart/AAPL');

  it('loads the chart for its ticker and plan id', () => {
    mount('AAPL', ID);
    const request = chartRequest();
    expect(request.request.params.get('trade_id')).toBe(ID);
  });

  it('asks for nothing before the ticker is known', () => {
    mount(null, null);
    backend.expectNone((req) => req.url.startsWith('/api/v1/market/chart/'));
  });

  it('captions the chart with the ticker and the drawn methods', () => {
    const fixture = mount('AAPL', ID);
    chartRequest().flush(RESPONSE);
    fixture.detectChanges();
    const caption = (fixture.nativeElement as HTMLElement).querySelector('figcaption');
    expect(caption?.textContent).toContain("AAPL — daily, with this plan's levels · EMA20");
  });

  it('says so when the window has no bars', () => {
    const fixture = mount('AAPL', ID);
    chartRequest().flush({ ...RESPONSE, ohlcv: [] });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent)
      .toContain('No price history for this window');
  });

  it('offers a retry that re-issues the request after a failure', () => {
    const fixture = mount('AAPL', ID);
    chartRequest().flush(
      { error: { code: 'unavailable', message: 'nope' } },
      { status: 503, statusText: 'x' },
    );
    fixture.detectChanges();
    const retry = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.retry');
    expect(retry).toBeTruthy();

    retry!.click();
    fixture.detectChanges();
    chartRequest().flush(RESPONSE);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.retry')).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/plan-chart.spec.ts --watch=false`
Expected: FAIL, because `./plan-chart` cannot be resolved.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/trades/why/plan-chart.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, effect, inject, input } from '@angular/core';

import { ChartStore } from '../../../stores/chart.store';
import { ChartContainer } from '../../../ui/chart-container';
import { TradeChart } from '../../../ui/chart/trade-chart';

/**
 * The plan's chart (spec v151): daily bars with this plan's levels and the
 * methods that put them there. Extracted from the trade page's Chart tab so
 * the plan page draws the same chart.
 *
 * The one shared component that is not plain inputs: it reads `ChartStore`
 * from its injector (route-scoped on both pages) and points it at its own
 * ticker and plan id. `setTarget` is a no-op for the same pair, so a page that
 * already set the target (the trade page preloads it) costs no second request.
 */
@Component({
  selector: 'sb-plan-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChartContainer, TradeChart],
  template: `
    <sb-chart-container
      [loading]="chart.loading()"
      [error]="chart.error()"
      [hasData]="!chart.isEmpty()"
      [height]="520"
      [caption]="caption()"
      [canRetry]="true"
      (retry)="chart.retry()"
    >
      <sb-trade-chart [data]="chart.data()" />
    </sb-chart-container>
  `,
  styles: `
    :host { display: block; }
  `,
})
export class PlanChart {
  protected readonly chart = inject(ChartStore);

  readonly ticker = input<string | null>(null);
  readonly tradeId = input<string | null>(null);

  /** The confirming methods, when the chart draws any. An empty list is an
   *  ordinary state (an older trade with no recorded sources), so the caption
   *  simply says less rather than announcing an absence. */
  protected readonly caption = computed(() => {
    const ticker = this.ticker();
    if (!ticker) return null;
    const source = (this.chart.data()?.overlays ?? [])
      .map((overlay) => overlay.source)
      .join(' · ');
    const base = `${ticker} — daily, with this plan's levels`;
    return source ? `${base} · ${source}` : base;
  });

  constructor() {
    // Both, and both from the plan: the ticker is what is charted, and the id
    // is what adds the plan lines, the working stop and the overlays. A null
    // ticker asks for nothing (ChartStore.load returns early).
    effect(() => this.chart.setTarget(this.ticker(), this.tradeId()));
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/plan-chart.spec.ts --watch=false`
Expected: PASS (5 tests). If the retry test sees no `.retry` button, read `ui/chart-container.ts:60-73`: the button renders only in the `error` state with `canRetry` true. Check that the 503 flush leaves `chart.error()` non-null; do not change `ChartContainer`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades/why/plan-chart.ts frontend/src/app/workspaces/trades/why/plan-chart.spec.ts
git commit -m "feat(ui): v151 extract the plan chart into sb-plan-chart (V151-14)"
```

# Phase 6: the two pages

### Task V151-15: Trade page onto the shared components + arrival banner

**Model:** sonnet — a behaviour-preserving refactor of a 1258-line component across three tabs, with an existing suite that must stay green unchanged, plus one new banner.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts`
- Test: `frontend/src/app/workspaces/trades/trade-detail.spec.ts`

**Interfaces:**
- Consumes, all from Group A (they must all be on the branch before this task starts):
  - `WhyPanel`, `WHY_SECTIONS`, `type WhySection` from `./why/why-panel` (V151-9). Inputs used: `sections`, `status`, `barsToExpiry`, `sessionsSinceCreated`, `entry`, `trigger`, `stop`, `stopLabel`, `target1`, `target2`, `acceptanceLevel`, `targetSources`, `stopSources`, `target2Sources`, `confirmedBy`, `confidencePoints`, `confidenceUnevaluated`, `confidenceFactors`, `qualityFactors`, `gates`, `calendar`, `explanation`.
  - `LevelsBlock` from `./why/levels-block` (V151-10). Inputs: `direction`, `entryType`, `trigger`, `entry`, `stop`, `stopLabel`, `target1`, `target2`, `riskReward`, `acceptanceLevel`, `tp1Pct`, `breakevenTriggerPct`.
  - `IfItGetsThere` from `./why/if-it-gets-there` (V151-11). Inputs: `direction`, `target2`, `stopLoss`.
  - `SizingPanel` from `./why/sizing-panel` (V151-12). Inputs: `shares`, `positionValue`, `sizingMode`, `workingStop`, `gapP90Pct`, `gapFragile`.
  - `OutcomePath` from `./why/outcome-path` (V151-13). Inputs: `legs`, `timeline`.
  - `PlanChart` from `./why/plan-chart` (V151-14). Inputs: `ticker`, `tradeId`.
  - Store computeds from V151-8: `acceptanceLevel`, `sessionsSinceCreated`, `confidencePoints`, `confidenceUnevaluated`, `gates`, `calendar`, `gapP90Pct`, `gapFragile`. Existing ones: `triggerPrice`, `tp1Pct`, `breakevenTriggerPct`, `targetSources`, `stopSources`, `target2Sources`, `confirmedBy`, `confidenceFactors`, `qualityFactors`, `explanation`, `legs`, `timeline`, `detail`, `detailAbsent`.
- Produces:
  - `export function arrivalBanner(status: string | null, barsToExpiry: number | null): string`, exported from `trade-detail.ts`. It returns `'This plan has expired — this is its trade record.'` for PENDING with `barsToExpiry === 0`, `'This plan was cancelled — this is its trade record.'` for CANCELLED, `'This plan is closed — this is its trade record.'` for CLOSED, and `''` for anything else.
  - `TradeDetail.arrivedFromPlan: boolean` (`protected readonly`). It is read once at construction from `history.state?.from === 'plan'` (index decision 10). V151-16 navigates here with `{ replaceUrl: true, state: { from: 'plan' } }`.

What changes on the trade page (spec § Trade page):
- **Plan tab**, in this order: `<sb-levels-block>`, Per share (unchanged), `<sb-if-it-gets-there>`, `<sb-sizing-panel>`, Opened (unchanged), then `<sb-why-panel>`. The why panel replaces the old `Why this trade` / `Confirmed by` / `Confidence breakdown` / `Quality breakdown` panels. The Levels panel's `.sources` block is gone, because the Why panel is now the one place sources render. Labels and headings stay the same, so the existing assertions hold.
- **Legacy record** (`detailAbsent()`): the "logged before" note stays exactly as it is. Below it the Why panel renders only `gates` and `calendar`. Gate rows are never hidden (spec § Edge cases, `entry_context` empty → `—`), and the reasoning sections stay out, as today.
- **Live tab**: the `Scale-out` and `Timeline` panels become `<sb-outcome-path>`. Now, Stop to target, Partial position and Actions stay as they are. Actions stay on the trade page only.
- **Chart tab**: `<sb-plan-chart>`. The component's own `setTarget` effect stays, so the chart still preloads before the tab opens (decision 9).
- **Arrival banner**: one `role="status"` line at the top of the header, only when `arrivedFromPlan` is true and `arrivalBanner(...)` returns text. A direct visit shows no banner.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/trades/trade-detail.spec.ts`, change the vitest import line to:

```ts
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
```

and change the component import to:

```ts
import { TradeDetail, arrivalBanner } from './trade-detail';
```

Then append these blocks at the end of the file. Leave every existing `it` untouched.

```ts
describe('TradeDetail — the shared Why components (v151)', () => {
  let backend: HttpTestingController;

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
  });

  function mount(tab: string, detail: object = DETAIL, status = 'ACTIVE', overrides: object = {}) {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail, status, overrides));
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('hosts the levels block, the two plan panels and the Why panel on the Plan tab', () => {
    const el = mount('plan');
    expect(el.querySelector('sb-levels-block')).toBeTruthy();
    expect(el.querySelector('sb-if-it-gets-there')).toBeTruthy();
    expect(el.querySelector('sb-sizing-panel')).toBeTruthy();
    expect(el.querySelector('sb-why-panel')).toBeTruthy();
    expect(el.textContent).toContain('Paper plan — this page places no orders.');
  });

  it('renders the level sources exactly once', () => {
    const text = mount('plan').textContent ?? '';
    expect(text.split('Target confirmed by').length - 1).toBe(1);
    expect(text.split('Stop confirmed by').length - 1).toBe(1);
  });

  it('shows the gate margins section with its caveat on the Plan tab', () => {
    const text = mount('plan').textContent ?? '';
    expect(text).toContain("Gate margins (vs today's thresholds)");
    expect(text).toContain(
      "Margins are measured against today's thresholds, not the ones in force when this plan was issued.",
    );
    expect(text).toContain('Calendar in the holding window');
  });

  it('keeps the gate rows on a legacy record that has no detail', () => {
    const el = mount('plan', {
      ...DETAIL,
      explanation: null,
      confirmed_by: [],
      target_sources: [],
      stop_sources: [],
      confidence_breakdown: null,
      quality_breakdown: [],
      status_history: [],
      gates: [{
        key: 'rs', label: 'Relative strength', value: null, threshold: 25,
        margin: null, applies: false, parts: [], note: 'exempt',
      }],
    });
    const text = el.textContent ?? '';
    expect(text).toContain('logged before the admin UI captured the full alert detail');
    expect(text).toContain('Relative strength');
    expect(text).not.toContain('Why this trade');
    expect(text).not.toContain('Quality breakdown');
  });

  it('hosts the outcome path on the Live tab', () => {
    const el = mount('live');
    expect(el.querySelector('sb-outcome-path')).toBeTruthy();
    expect(el.textContent).toContain('Scale-out');
    expect(el.textContent).toContain('Timeline');
  });

  it('hosts the plan chart on the Chart tab', () => {
    const el = mount('chart');
    expect(el.querySelector('sb-plan-chart')).toBeTruthy();
  });
});

describe('TradeDetail — arrival banner from the plan page (v151)', () => {
  let backend: HttpTestingController;

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
  });

  afterEach(() => history.replaceState(null, ''));

  function mountWithState(state: object | null, status: string, overrides: object = {}) {
    history.replaceState(state, '');
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(DETAIL, status, overrides));
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('says the plan is closed when redirected from a closed plan', () => {
    const el = mountWithState({ from: 'plan' }, 'CLOSED');
    expect(el.querySelector('.arrival')?.textContent).toContain('This plan is closed');
  });

  it('says the plan was cancelled when redirected from a cancelled plan', () => {
    const el = mountWithState({ from: 'plan' }, 'CANCELLED');
    expect(el.querySelector('.arrival')?.textContent).toContain('This plan was cancelled');
  });

  it('says the plan has expired when redirected from an expired pending plan', () => {
    const el = mountWithState({ from: 'plan' }, 'PENDING', { bars_to_expiry: 0 });
    expect(el.querySelector('.arrival')?.textContent).toContain('This plan has expired');
  });

  it('shows no banner on a direct visit', () => {
    const el = mountWithState(null, 'CLOSED');
    expect(el.querySelector('.arrival')).toBeNull();
  });

  it('shows no banner for a live plan even with the state set', () => {
    const el = mountWithState({ from: 'plan' }, 'ACTIVE');
    expect(el.querySelector('.arrival')).toBeNull();
  });
});

describe('arrivalBanner', () => {
  it('words each terminal case', () => {
    expect(arrivalBanner('PENDING', 0)).toBe('This plan has expired — this is its trade record.');
    expect(arrivalBanner('CANCELLED', null)).toBe('This plan was cancelled — this is its trade record.');
    expect(arrivalBanner('CLOSED', null)).toBe('This plan is closed — this is its trade record.');
  });

  it('returns nothing for a plan that is still open', () => {
    expect(arrivalBanner('PENDING', 3)).toBe('');
    expect(arrivalBanner('PENDING', null)).toBe('');
    expect(arrivalBanner('ACTIVE', null)).toBe('');
    expect(arrivalBanner('PARTIAL', null)).toBe('');
    expect(arrivalBanner(null, null)).toBe('');
  });
});
```

The Chart-tab test does not settle the chart request. `trade-detail.spec.ts` never calls `backend.verify()`, so an open chart or journal request is fine here, as it already is for the existing tests.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/trade-detail.spec.ts --watch=false`
Expected: FAIL. `arrivalBanner` is not exported, and the new `sb-*` selectors are absent. Every pre-existing test still passes.

- [ ] **Step 3: Rewire `trade-detail.ts`**

Make these edits in `frontend/src/app/workspaces/trades/trade-detail.ts`, in order. Line numbers are from `main` before this task.

**3a. Imports (`:13-35`).** Delete these three import lines:

```ts
import { ChartContainer } from '../../ui/chart-container';
import { TradeChart } from '../../ui/chart/trade-chart';
import { InlineMd } from '../../ui/inline-md';
```

Then add these after the `./trade-actions` import block:

```ts
import { IfItGetsThere } from './why/if-it-gets-there';
import { LevelsBlock } from './why/levels-block';
import { OutcomePath } from './why/outcome-path';
import { PlanChart } from './why/plan-chart';
import { SizingPanel } from './why/sizing-panel';
import { WHY_SECTIONS, WhyPanel, WhySection } from './why/why-panel';
```

**3b. Module-level helpers.** Insert these directly after `const TAB_IDS = new Set(TABS.map((tab) => tab.id));`:

```ts
/** A legacy record with no captured detail still shows its gate rows: "not
 *  recorded" is a measured answer and is never hidden (spec v151 § Edge
 *  cases). The reasoning sections stay out, exactly as before. */
const ABSENT_SECTIONS: readonly WhySection[] = ['gates', 'calendar'];

const ARRIVAL_SUFFIX = ' — this is its trade record.';

/**
 * Why the plan page sent the reader here instead (spec v151 § Arrival
 * banner). A Discord link outlives the plan's open life; when it lands on
 * the trade record, this line says why. Empty for a plan that is still open.
 */
export function arrivalBanner(status: string | null, barsToExpiry: number | null): string {
  if (status === 'PENDING' && barsToExpiry === 0) return `This plan has expired${ARRIVAL_SUFFIX}`;
  if (status === 'CANCELLED') return `This plan was cancelled${ARRIVAL_SUFFIX}`;
  if (status === 'CLOSED') return `This plan is closed${ARRIVAL_SUFFIX}`;
  return '';
}

/** Read once, at construction: the plan page's redirect passes
 *  `state: { from: 'plan' }`, and a direct visit has no such state. */
function cameFromPlan(): boolean {
  if (typeof history === 'undefined') return false;
  const state: unknown = history.state;
  return typeof state === 'object' && state !== null
    && (state as Record<string, unknown>)['from'] === 'plan';
}
```

**3c. The component's `imports` array (`:63-78`).** Replace it with:

```ts
  imports: [
    RouterLink,
    TabBar,
    Panel,
    ControlRow,
    StatusIndicator,
    QualityChip,
    Button,
    ConfirmDialog,
    MetricChip,
    Chip,
    Async,
    WhyPanel,
    LevelsBlock,
    IfItGetsThere,
    SizingPanel,
    OutcomePath,
    PlanChart,
  ],
```

**3d. The arrival banner.** In the template, directly after `<a class="back" routerLink="/trades">← Trades</a>` (`:81`), insert:

```html
      @if (arrival(); as message) {
        <p class="arrival" role="status">{{ message }}</p>
      }
```

**3e. The Plan tab.** Replace everything from `@case ('plan') {` (`:158`) up to, but not including, `@case ('live') {` (`:382`) with:

```html
      @case ('plan') {
        @if (store.trade(); as trade) {
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

            <sb-panel heading="Per share">
              <dl>
                <div>
                  <dt>Risk</dt>
                  <dd class="num">{{ fmt(store.riskPerShare()) }}</dd>
                </div>
                <div>
                  <dt>Reward</dt>
                  <dd class="num">{{ fmt(store.rewardPerShare()) }}</dd>
                </div>
                <div>
                  <dt>Direction</dt>
                  <dd>{{ fmtText(trade.direction) }}</dd>
                </div>
                <div>
                  <dt>Origin</dt>
                  <dd>{{ fmtText(trade.origin) }}</dd>
                </div>
              </dl>
            </sb-panel>

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

            <sb-panel heading="Opened">
              <dl>
                <div>
                  <dt>At</dt>
                  <dd>{{ fmtDate(trade.opened_at) }}</dd>
                </div>
                <div>
                  <dt>Closed</dt>
                  <dd>{{ fmtDate(trade.closed_at) }}</dd>
                </div>
                <div>
                  <dt>Entry type</dt>
                  <dd>{{ fmtText(store.detail()?.entry_type ?? null) }}</dd>
                </div>
                <div>
                  <dt>P&L</dt>
                  <dd class="num">{{ fmtPct(trade.pnl_pct) }}</dd>
                </div>
              </dl>
            </sb-panel>
          </div>

          <!-- The reasoning. Everything above is a number; the Why panel is
               the only part of the screen that says why any of them were
               chosen, and the one place level sources render (v151). -->
          @if (store.detailAbsent()) {
            <!-- Not an error and not an empty panel per field: this record
                 predates the detail capture entirely, and nine em dashes read
                 as a failed load rather than as a fact about an old trade. -->
            <p class="no-detail">
              This trade was logged before the admin UI captured the full alert
              detail — only the plan above is available for it.
            </p>
          }
          <sb-why-panel
            [sections]="whySections()"
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
        }
      }
```

**3f. The Live tab's two lower panels.** Replace everything from the comment `<!-- Scale-out legs. A position that took TP1 and is riding a runner` (`:497`) through the closing `}` of `@if (store.timeline().length) { ... }` (`:548`) with:

```html
          <sb-outcome-path [legs]="store.legs()" [timeline]="store.timeline()" />
```

The `@if (store.trade(); as trade) {` and `}` that wrap the Live tab stay where they are.

**3g. The Chart tab.** Replace the body of `@case ('chart') { ... }` (`:551-565`) with:

```html
      @case ('chart') {
        <div class="chart">
          <sb-plan-chart [ticker]="store.trade()?.ticker ?? null" [tradeId]="store.trade()?.id ?? null" />
        </div>
      }
```

**3h. Styles.** These rules now belong to the child components. Delete these blocks from the `styles` string: `.prose`, `.sources`, `.sources p`, `.src-label`, `.confirmations`, `.confirmations li`, the comment plus `.factors > div` and `.factors dd`, the comment plus `.timeline`, `.timeline li`, `.timeline li::before`, `.tl-status`, `.tl-reason`, `.tl-at`. Keep `.no-detail`, `.muted-gap` (the Partial position panel still uses it) and `.chart {}`. Add after `.back:hover { ... }`:

```css
    /* Why the plan page sent the reader here (v151). Informational, not a
       warning: the record is fine, the plan's open life is simply over. */
    .arrival {
      max-width: 68ch;
      padding: var(--space-8);
      border-left: 2px solid var(--accent);
      color: var(--text);
      font-size: var(--text-table);
    }
```

**3i. Class members.** In `export class TradeDetail`:

Delete `levelWord`, `oppositeWord`, `ifItGetsThereHeading` (and the `/* -- SR60 ... */` banner comment above them), `chartCaption`, `chartEmpty`, and the `signed()` method with its doc comment. `sb-if-it-gets-there`, `sb-plan-chart` and `sb-why-panel` own them now. Keep `stopLabel`, which the Live tab still uses. Keep `chart` and the `setTarget` effect in the constructor (decision 9).

Add, directly after `readonly tab = input<string>();`:

```ts
  /** True only when the plan page redirected here (v151). Read once: a
   *  later navigation inside this page must not re-raise the banner. */
  protected readonly arrivedFromPlan: boolean = cameFromPlan();

  protected readonly arrival = computed(() => {
    if (!this.arrivedFromPlan) return '';
    const trade = this.store.trade();
    return trade ? arrivalBanner(trade.status, trade.bars_to_expiry ?? null) : '';
  });

  /** Every Why section, except on a record that predates detail capture,
   *  which keeps only its gate rows and calendar. */
  protected readonly whySections = computed<readonly WhySection[]>(() =>
    this.store.detailAbsent() ? ABSENT_SECTIONS : WHY_SECTIONS,
  );
```

Then check that nothing still refers to a deleted member:

Run: `git grep -n "levelWord\|oppositeWord\|ifItGetsThereHeading\|chartCaption\|chartEmpty\|signed(" -- frontend/src/app/workspaces/trades/trade-detail.ts`
Expected: no output.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/trade-detail.spec.ts --watch=false`
Expected: PASS. Every pre-existing test must pass with no edit to it.

If an existing test fails, the extraction changed behaviour. Fix the binding, not the test. The likely causes:
- `'labels the stop plain "Stop"'`: `stopLabel()` must reach both `sb-levels-block` and `sb-why-panel`.
- `'renders the trigger price and the two fractions unsigned'`: `tp1Pct` / `breakevenTriggerPct` must reach `sb-levels-block`.

If an arrival test sees no banner, `history.state` was overwritten before construction. Log `history.state` inside `cameFromPlan()` to confirm. Do **not** move the read later than construction.

Then run the gates that scan this file:

Run: `npm --prefix frontend test -- --include src/app/ui/async-coverage.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --watch=false`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git commit -m "feat(ui): v151 trade page composes the shared Why components; arrival banner (V151-15)"
```

**Continues in Part 3b** ([`_3b-plan-page-and-suites`](2026-10-10-v151-plan-detail-why-panel_3b-plan-page-and-suites.md)): V151-16 (the plan page) and V151-17 (both full suites). This file reached the 1500-line budget after V151-15, and a task is never split or compressed to fit.
