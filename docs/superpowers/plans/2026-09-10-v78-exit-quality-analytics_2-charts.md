# v78 — Part 2: Primitives and sections (tasks B1…C5)

> Part of `2026-09-10-v78-exit-quality-analytics_0-index.md`. **Read the
> index's Global Constraints before starting any task here.** Part 1 (A1–A4)
> must be merged before C1 begins — C1 fetches the route A4 adds.

**Spec:** `docs/superpowers/specs/2026-09-10-v78-exit-quality-analytics-design.md`

## Part 2 exit criteria

1. `sb-donut` and `sb-scatter` exist in `frontend/src/app/ui/`, hand-rolled
   SVG, no new dependency.
2. A zero-count slice appears in the donut legend and draws no arc — asserted
   by test.
3. The Performance tab renders P1–P6; the Strategies tab renders S1.
4. `analytics.ts` gained mount points only — no chart logic.
5. Each task's own spec file passes under
   `npm test -- --include <that spec>`.

## Conventions every task here follows

- Angular 21.2.21: **signal inputs** (`input()`, `input.required()`),
  `ChangeDetectionStrategy.OnPush`, standalone with an explicit `imports`
  array. Mirror `frontend/src/app/ui/histogram.ts`.
- Chrome tokens come from `CHART_CHROME` (`ui/chart/chart-frame.ts:32` —
  `tickSize: '--text-micro'`, `tickColour: '--text-muted'`). Colours are
  `var(--pos)` / `var(--neg)`, the pair `histogram.ts` already uses.
- **Green/red is reserved for P&L direction** (v30). A categorical breakdown
  such as exit reason uses the neutral ramp, not the signed pair.
- **Signed bars reuse `sb-histogram`.** Put the signed number at the *start* of
  the label with an ASCII hyphen (`-0.42R · stop (n=300)`) and pass
  `count: Math.abs(value)`. The component's default `isNegative` predicate is
  `bin.label.startsWith('-')` (`histogram.ts`), so this needs no new input and
  no new primitive.
- `sb-async` requires `emptyReason` and `emptyTitle`. Use `'no-data-yet'` when
  there are no closed trades at all and `'measured-zero'` when trades exist but
  the slice is genuinely empty.

---

# Phase B — Chart primitives

### Task B1: sb-donut

**Files:**
- Create: `frontend/src/app/ui/donut.ts`
- Test: `frontend/src/app/ui/donut.spec.ts`

**Interfaces:**
- Consumes: `CHART_CHROME` from `./chart/chart-frame`.
- Produces: `DonutComponent` (selector `sb-donut`), and
  `export interface DonutSlice { label: string; count: number; tone?: 'pos' | 'neg' }`.
  C2 renders two of these.

Composition of a whole, which is the one question a donut answers better than a
bar — and the reason v30's rejection of pies does not cover it. v30 rejected
seven pies over the *by-dimension win-rate* block, and `histogram.ts` documents
why: *"a pie cannot show an ordered scale at all."* Both donuts in this plan
show parts that sum to 100% of the book.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/donut.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { Component } from '@angular/core';

import { DonutComponent } from './donut';

@Component({
  imports: [DonutComponent],
  template: `<sb-donut [slices]="slices" />`,
})
class Host {
  slices = [
    { label: 'stop', count: 3 },
    { label: 'tp1', count: 1 },
    { label: 'timeout', count: 0 },
  ];
}

describe('sb-donut', () => {
  function render() {
    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('draws one arc per non-empty slice', () => {
    expect(render().querySelectorAll('circle.slice').length).toBe(2);
  });

  it('lists an empty slice in the legend without drawing it', () => {
    const text = render().textContent ?? '';
    expect(text).toContain('timeout');
    expect(text).toContain('n=0');
  });

  it('shows each slice share as a percentage of the whole', () => {
    expect(render().textContent).toContain('75.0%');
  });

  it('renders nothing when every slice is empty', () => {
    const fixture = TestBed.createComponent(Host);
    fixture.componentInstance.slices = [{ label: 'stop', count: 0 }];
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('circle.slice').length).toBe(0);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/donut.spec.ts`
Expected: FAIL — cannot resolve `./donut`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/app/ui/donut.ts`:

```typescript
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { CHART_CHROME } from './chart/chart-frame';

export interface DonutSlice {
  label: string;
  count: number;
  /** Only for a breakdown that IS a P&L direction. v30 reserves the signed
   *  pair for that; a categorical breakdown leaves this unset and takes the
   *  neutral ramp. */
  tone?: 'pos' | 'neg';
}

interface Arc extends DonutSlice {
  share: number;
  dash: string;
  offset: number;
  fill: string;
}

const R = 60;
const C = 2 * Math.PI * R;

/**
 * Composition of a whole: parts that sum to 100% of the book.
 *
 * Deliberately NOT a general pie. v30 rejected seven pies drawn over the
 * by-dimension win-rate block ("one question asked eight ways") and
 * histogram.ts records the reason a pie is wrong there: it "cannot show an
 * ordered scale at all". A rate is an ordered scale; a share of a total is
 * not. Use sb-histogram for anything rate-shaped.
 *
 * A zero-count slice is legended and not drawn. "Nothing exited this way"
 * and "this way lost everything" must not look the same -- the same rule
 * exit_reason_split states for its own null avg_r.
 */
@Component({
  selector: 'sb-donut',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (total() > 0) {
      <div class="wrap">
        <svg viewBox="0 0 160 160" role="img" [attr.aria-label]="summary()">
          <g transform="rotate(-90 80 80)">
            @for (arc of arcs(); track arc.label) {
              <circle
                class="slice"
                cx="80" cy="80" [attr.r]="r"
                [attr.stroke]="arc.fill"
                [attr.stroke-dasharray]="arc.dash"
                [attr.stroke-dashoffset]="arc.offset" />
            }
          </g>
          <text x="80" y="80" class="hub" text-anchor="middle" dy="0.35em">
            {{ total() }}
          </text>
        </svg>
        <ul class="legend">
          @for (arc of arcs(); track arc.label) {
            <li>
              <span class="swatch" [style.background]="arc.fill"></span>
              <span class="name">{{ arc.label }}</span>
              <span class="figure">n={{ arc.count }}</span>
              <span class="figure">{{ arc.share | number: '1.1-1' }}%</span>
            </li>
          }
        </ul>
      </div>
    }
  `,
  styles: `
    .wrap { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
    svg { width: 160px; height: 160px; flex: none; }
    circle.slice { fill: none; stroke-width: 20; }
    .hub { font-size: 1.25rem; fill: var(--text); }
    .legend { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.15rem; min-width: 14rem; }
    .legend li { display: grid; grid-template-columns: 0.75rem 1fr auto auto; gap: 0.5rem; align-items: center; }
    .swatch { width: 0.75rem; height: 0.75rem; border-radius: 2px; }
    .figure { font-size: var(${CHART_CHROME.tickSize}); color: var(${CHART_CHROME.tickColour}); font-variant-numeric: tabular-nums; }
  `,
})
export class DonutComponent {
  readonly slices = input.required<readonly DonutSlice[]>();

  protected readonly r = R;

  protected readonly total = computed(() =>
    this.slices().reduce((sum, s) => sum + (s.count > 0 ? s.count : 0), 0));

  protected readonly arcs = computed<Arc[]>(() => {
    const total = this.total();
    if (total <= 0) return [];
    let consumed = 0;
    const drawable = this.slices().filter((s) => s.count > 0).length;
    let index = 0;
    return this.slices().map((slice) => {
      const share = (slice.count / total) * 100;
      const arc: Arc = {
        ...slice,
        share,
        dash: slice.count > 0 ? `${(C * slice.count) / total} ${C}` : `0 ${C}`,
        offset: slice.count > 0 ? -((C * consumed) / total) : 0,
        fill: this.fillFor(slice, index, drawable),
      };
      if (slice.count > 0) {
        consumed += slice.count;
        index += 1;
      }
      return arc;
    });
  });

  protected readonly summary = computed(() =>
    this.arcs()
      .filter((a) => a.count > 0)
      .map((a) => `${a.label} ${a.share.toFixed(1)}%`)
      .join(', '));

  /** Signed pair only when the caller says this breakdown IS a direction;
   *  otherwise a neutral opacity ramp, per v30's colour reservation. */
  private fillFor(slice: DonutSlice, index: number, drawable: number): string {
    if (slice.tone === 'pos') return 'var(--pos)';
    if (slice.tone === 'neg') return 'var(--neg)';
    const step = drawable > 1 ? index / (drawable - 1) : 0;
    const weight = Math.round(70 - step * 45);
    return `color-mix(in oklab, var(--text) ${weight}%, transparent)`;
  }
}
```

Add `DecimalPipe` to the component's `imports` array (`imports: [DecimalPipe]`,
imported from `@angular/common`) — the template uses the `number` pipe.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/donut.spec.ts`
Expected: PASS, 4 specs.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/donut.ts frontend/src/app/ui/donut.spec.ts
git commit -m "feat(v78): sb-donut -- composition of a whole, absent is not zero"
```

---

### Task B2: sb-scatter

**Files:**
- Create: `frontend/src/app/ui/scatter.ts`
- Test: `frontend/src/app/ui/scatter.spec.ts`

**Interfaces:**
- Consumes: `CHART_CHROME` from `./chart/chart-frame`.
- Produces: `ScatterComponent` (selector `sb-scatter`), and
  `export interface ScatterPoint { x: number; y: number; label?: string; tone?: 'pos' | 'neg' | 'muted' }`.
  C4 renders one.

The one chart in this plan that gains honesty as the sample shrinks: nine
trades are nine dots, with no aggregate to misstate. It is also why the scatter
takes losers when the aggregate histograms do not — see the index's
winners-only constraint.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/scatter.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { Component } from '@angular/core';

import { ScatterComponent } from './scatter';

@Component({
  imports: [ScatterComponent],
  template: `<sb-scatter [points]="points" xLabel="MAE (R)" yLabel="MFE (R)" />`,
})
class Host {
  points = [
    { x: 0.2, y: 2.0, tone: 'pos' as const, label: 'AAPL' },
    { x: 1.0, y: 0.3, tone: 'neg' as const, label: 'MSFT' },
  ];
}

describe('sb-scatter', () => {
  function render(points?: unknown[]) {
    const fixture = TestBed.createComponent(Host);
    if (points) fixture.componentInstance.points = points as never;
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('draws one dot per point', () => {
    expect(render().querySelectorAll('circle.pt').length).toBe(2);
  });

  it('labels both axes', () => {
    const text = render().textContent ?? '';
    expect(text).toContain('MAE (R)');
    expect(text).toContain('MFE (R)');
  });

  it('renders no plot area when there are no points', () => {
    expect(render([]).querySelectorAll('circle.pt').length).toBe(0);
  });

  it('keeps a point at the domain maximum inside the viewBox', () => {
    const el = render([{ x: 5, y: 5 }, { x: 0, y: 0 }]);
    const cx = [...el.querySelectorAll('circle.pt')].map((c) => Number(c.getAttribute('cx')));
    expect(Math.max(...cx)).toBeLessThanOrEqual(200);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/scatter.spec.ts`
Expected: FAIL — cannot resolve `./scatter`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/app/ui/scatter.ts`:

```typescript
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { CHART_CHROME } from './chart/chart-frame';

export interface ScatterPoint {
  x: number;
  y: number;
  label?: string;
  tone?: 'pos' | 'neg' | 'muted';
}

interface Plotted extends ScatterPoint {
  cx: number;
  cy: number;
  fill: string;
}

const W = 200;
const H = 150;
const PAD = 4;

/**
 * One dot per trade. Unlike every rate chart on the page, this one does not
 * get less honest as the sample shrinks -- there is no aggregate here to
 * misstate, so a nine-trade scatter is nine trades and reads as such.
 *
 * Domains start at zero and are driven by the data's own maximum: MAE and
 * MFE are both >= 0 (mfe_mae.py clamps mae_r with max(0.0, ...)), so a fixed
 * domain would either clip the 13R outlier production actually holds or
 * squash everything else against the axis.
 */
@Component({
  selector: 'sb-scatter',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <figure>
      @if (plotted().length > 0) {
        <svg [attr.viewBox]="'0 0 ' + w + ' ' + h" role="img"
             [attr.aria-label]="plotted().length + ' trades plotted'">
          <line class="axis" [attr.x1]="pad" [attr.y1]="h - pad"
                [attr.x2]="w - pad" [attr.y2]="h - pad" />
          <line class="axis" [attr.x1]="pad" [attr.y1]="pad"
                [attr.x2]="pad" [attr.y2]="h - pad" />
          @for (p of plotted(); track $index) {
            <circle class="pt" [attr.cx]="p.cx" [attr.cy]="p.cy" r="2.5"
                    [attr.fill]="p.fill">
              @if (p.label) { <title>{{ p.label }}</title> }
            </circle>
          }
        </svg>
      }
      <figcaption>
        <span class="ax">{{ xLabel() }}</span>
        <span class="ax">{{ yLabel() }}</span>
        <span class="ax">max {{ xMax() | number: '1.1-1' }} / {{ yMax() | number: '1.1-1' }}</span>
      </figcaption>
    </figure>
  `,
  styles: `
    figure { margin: 0; }
    svg { width: 100%; height: auto; }
    .axis { stroke: var(${CHART_CHROME.tickColour}); stroke-width: 0.5; }
    figcaption { display: flex; gap: 1rem; flex-wrap: wrap; }
    .ax { font-size: var(${CHART_CHROME.tickSize}); color: var(${CHART_CHROME.tickColour}); }
  `,
})
export class ScatterComponent {
  readonly points = input.required<readonly ScatterPoint[]>();
  readonly xLabel = input('');
  readonly yLabel = input('');

  protected readonly w = W;
  protected readonly h = H;
  protected readonly pad = PAD;

  protected readonly xMax = computed(() =>
    Math.max(1, ...this.points().map((p) => p.x)));
  protected readonly yMax = computed(() =>
    Math.max(1, ...this.points().map((p) => p.y)));

  protected readonly plotted = computed<Plotted[]>(() => {
    const xMax = this.xMax();
    const yMax = this.yMax();
    return this.points().map((p) => ({
      ...p,
      cx: PAD + (p.x / xMax) * (W - PAD * 2),
      cy: H - PAD - (p.y / yMax) * (H - PAD * 2),
      fill: p.tone === 'pos' ? 'var(--pos)'
        : p.tone === 'neg' ? 'var(--neg)'
        : `color-mix(in oklab, var(--text) 40%, transparent)`,
    }));
  });
}
```

Add `DecimalPipe` from `@angular/common` to the component's `imports` array.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/scatter.spec.ts`
Expected: PASS, 4 specs.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/scatter.ts frontend/src/app/ui/scatter.spec.ts
git commit -m "feat(v78): sb-scatter -- one dot per trade, honest at any N"
```

---

# Phase C — Sections

### Task C1: API method, store slice and the section shell

**Files:**
- Modify: `frontend/src/app/api/models.ts` (add the payload interface)
- Modify: `frontend/src/app/api/api-client.ts:175-217` (the analytics block)
- Modify: `frontend/src/app/stores/analytics.store.ts` (state, loader, computeds)
- Create: `frontend/src/app/workspaces/analytics/sections/exit-quality.ts`
- Create: `frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (mount only)

**Interfaces:**
- Consumes: `GET /analytics/exit-quality` (A4).
- Produces: `AnalyticsExitQuality` (the payload type),
  `ApiClient.analyticsExitQuality()`, store members `exitQuality`,
  `exitQualityError`, `loadExitQuality()`, `minCellN`, and
  `ExitQualitySectionComponent` (selector `sb-exit-quality`). C2, C3 and C4 all
  fill this component; D1 and D2 consume `minCellN`.

**The surrounding code is the authority on idiom.** `api-client.ts:175-217` is
a block of one-line `http.get` wrappers, and the analytics store's existing
loaders establish how `patchState` and the loading flags are used in this file.
Match the loader immediately above yours if it differs from the sketch below.

- [ ] **Step 1: Write the failing test**

Create
`frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';

import { ExitQualitySectionComponent } from './exit-quality';

describe('sb-exit-quality', () => {
  it('states field coverage rather than silently dropping rows', () => {
    const fixture = TestBed.createComponent(ExitQualitySectionComponent);
    fixture.componentRef.setInput('data', {
      exit_reasons: [], hold_by_outcome: {}, scatter: [],
      efficiency: { bins: [], n: 0, median: null },
      mae: { bins: [], n: 0, median: null },
      coverage: { exit_efficiency: { non_null: 520, total: 591, pct: 88.0 },
                  mae_r: { non_null: 558, total: 591, pct: 94.4 },
                  mfe_r: { non_null: 555, total: 591, pct: 93.9 } },
      min_cell_n: 20,
    });
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('520 of 591');
    expect(text).toContain('88');
  });

  it('renders without data', () => {
    const fixture = TestBed.createComponent(ExitQualitySectionComponent);
    fixture.componentRef.setInput('data', null);
    expect(() => fixture.detectChanges()).not.toThrow();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/sections/exit-quality.spec.ts`
Expected: FAIL — cannot resolve `./exit-quality`.

- [ ] **Step 3: Write the implementation**

Add to `frontend/src/app/api/models.ts`:

```typescript
export interface ExitQualityCoverage {
  non_null: number;
  total: number;
  pct: number;
}

export interface ExitQualityDistribution {
  bins: { lo: number; hi: number; count: number }[];
  n: number;
  median: number | null;
}

export interface ExitReasonRow {
  reason: string;
  n: number;
  share_pct: number;
  total_r: number | null;
  avg_r: number | null;
  win_rate: number | null;
}

export interface AnalyticsExitQuality {
  exit_reasons: ExitReasonRow[];
  hold_by_outcome: {
    avg_winner_days?: number | null;
    avg_loser_days?: number | null;
    ratio?: number | null;
    severity?: string | null;
    n_winners?: number;
    n_losers?: number;
  };
  efficiency: ExitQualityDistribution;
  mae: ExitQualityDistribution;
  scatter: {
    mae_r: number; mfe_r: number; r_realized: number | null;
    outcome: string; ticker: string; strategy: string;
  }[];
  coverage: Record<string, ExitQualityCoverage>;
  min_cell_n: number;
}
```

Add to the analytics block of `frontend/src/app/api/api-client.ts`:

```typescript
  analyticsExitQuality(): Observable<AnalyticsExitQuality> {
    return this.http.get<AnalyticsExitQuality>(`${this.base}/analytics/exit-quality`);
  }
```

In `frontend/src/app/stores/analytics.store.ts` add `exitQuality:
null as AnalyticsExitQuality | null` and `exitQualityError: null as string | null`
to `withState`, a loader in `withMethods`, and a computed for the floor:

```typescript
      loadExitQuality(): void {
        api.analyticsExitQuality().subscribe({
          next: (exitQuality) => patchState(store, { exitQuality, exitQualityError: null }),
          error: () => patchState(store, { exitQualityError: 'Could not load exit quality' }),
        });
      },
```

```typescript
    /** The suppression floor, served by the backend so the SPA never
     *  hard-codes it (index Global Constraint). 20 is the fallback only for
     *  the window before the first fetch resolves. */
    minCellN: computed(() => exitQuality()?.min_cell_n ?? 20),
```

Create
`frontend/src/app/workspaces/analytics/sections/exit-quality.ts`:

```typescript
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { AnalyticsExitQuality } from '../../../api/models';
import { PanelComponent } from '../../../ui/layout';

/**
 * Exit quality: what closed the trade, how much of the move was banked, how
 * much heat it took, and whether losers are held longer than winners.
 *
 * Its own component rather than more template in analytics.ts, which is
 * already ~1700 lines with the whole workspace inline. Separate files also
 * let the chart tasks run in parallel -- concurrent sessions share this
 * working tree, and two agents editing one component do not merge.
 *
 * Every chart here is fed by a partially-populated journal field, so the
 * coverage caption is not decoration: exit_efficiency is null on ~12% of
 * production rows. A chart that drops an eighth of the book without saying
 * so is lying by omission.
 */
@Component({
  selector: 'sb-exit-quality',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PanelComponent],
  template: `
    @if (data(); as d) {
      <sb-panel heading="Exit quality">
        <p class="coverage">{{ coverageText() }}</p>
        <!-- C2 adds the two donuts here, C3 the two histograms,
             C4 the disposition bars and the scatter. -->
      </sb-panel>
    }
  `,
  styles: `
    .coverage { color: var(--text-muted); font-size: var(--text-micro); margin: 0 0 0.5rem; }
  `,
})
export class ExitQualitySectionComponent {
  readonly data = input.required<AnalyticsExitQuality | null>();

  protected readonly coverageText = computed(() => {
    const cov = this.data()?.coverage ?? {};
    const parts = Object.entries(cov).map(
      ([field, c]) => `${field}: ${c.non_null} of ${c.total} (${c.pct}%)`);
    return parts.length ? `Coverage — ${parts.join(' · ')}` : '';
  });
}
```

Mount it in `frontend/src/app/workspaces/analytics/analytics.ts` inside the
Performance tab's "By segment" area — **one line, plus the import**:

```html
<sb-exit-quality [data]="store.exitQuality()" />
```

and call `store.loadExitQuality()` wherever the Performance tab's other loads
are triggered.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/sections/exit-quality.spec.ts`
Expected: PASS, 2 specs.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts \
        frontend/src/app/stores/analytics.store.ts \
        frontend/src/app/workspaces/analytics/sections/exit-quality.ts \
        frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts \
        frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(v78): exit-quality section shell, stating field coverage"
```

---

### Task C2: P1 exit-reason mix and P5 outcome mix

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/sections/exit-quality.ts`
- Test: `frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts`

**Interfaces:**
- Consumes: `DonutComponent`, `DonutSlice` (B1); `HistogramComponent`,
  `HistogramBin` from `../../../ui/histogram`; `AnalyticsExitQuality` (C1).
- Produces: nothing later tasks consume.

`exit_reason_split` returns a fixed nine buckets in `EXIT_REASONS` order
(`metrics.py:27`) — `tp1`, `runner_tp2`, `runner_trail`, `runner_be`, `stop`,
`scratch`, `timeout`, `reversed`, `other` — with every reason emitted even at
`n=0`. **`other` will dominate in production**, because 454 of 782 closed
trades carry no `close_reason` and fall through to it. That is the chart
working: the size of `other` is a legible data-quality defect.

The signed `avg_r` bars put the number first with an ASCII hyphen so
`sb-histogram`'s default `isNegative` predicate (`label.startsWith('-')`)
colours them without a new input.

- [ ] **Step 1: Write the failing tests**

Append to `exit-quality.spec.ts`:

```typescript
  function withReasons() {
    const fixture = TestBed.createComponent(ExitQualitySectionComponent);
    fixture.componentRef.setInput('data', {
      exit_reasons: [
        { reason: 'stop', n: 3, share_pct: 75, total_r: -3, avg_r: -1, win_rate: 0 },
        { reason: 'tp1', n: 1, share_pct: 25, total_r: 1, avg_r: 1, win_rate: 100 },
        { reason: 'timeout', n: 0, share_pct: 0, total_r: 0, avg_r: null, win_rate: null },
      ],
      hold_by_outcome: {}, scatter: [],
      efficiency: { bins: [], n: 0, median: null },
      mae: { bins: [], n: 0, median: null },
      coverage: {}, min_cell_n: 20,
    });
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('keeps every exit reason including the empty ones', () => {
    const text = withReasons().textContent ?? '';
    expect(text).toContain('stop');
    expect(text).toContain('timeout');
  });

  it('omits an empty bucket from the avg-R bars rather than drawing it at zero', () => {
    // avg_r is null for timeout: "no trades exited this way" and "they all
    // lost" must not look the same (exit_reason_split docstring).
    const labels = [...withReasons().querySelectorAll('.name, li')]
      .map((n) => n.textContent ?? '').join(' ');
    expect(labels).not.toContain('0.00R · timeout');
  });

  it('renders an outcome donut from win/loss/other counts', () => {
    expect(withReasons().querySelectorAll('sb-donut').length).toBe(2);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/sections/exit-quality.spec.ts`
Expected: FAIL — no `sb-donut` elements rendered.

- [ ] **Step 3: Write the implementation**

Add to `ExitQualitySectionComponent`'s `imports`: `DonutComponent`,
`HistogramComponent`. Add the computeds:

```typescript
  protected readonly reasonSlices = computed<DonutSlice[]>(() =>
    (this.data()?.exit_reasons ?? []).map((row) => ({
      label: row.reason, count: row.n,
    })));

  /** Signed bars, number first with an ASCII hyphen so sb-histogram's
   *  default isNegative predicate colours them. A null avg_r is an empty
   *  bucket and is dropped, never plotted at zero. */
  protected readonly reasonAvgR = computed<HistogramBin[]>(() =>
    (this.data()?.exit_reasons ?? [])
      .filter((row) => row.avg_r !== null && row.n > 0)
      .map((row) => ({
        label: `${row.avg_r!.toFixed(2)}R · ${row.reason} (n=${row.n})`,
        count: Math.abs(row.avg_r!),
      })));

  protected readonly outcomeSlices = computed<DonutSlice[]>(() => {
    const rows = this.data()?.exit_reasons ?? [];
    const sum = (names: string[]) =>
      rows.filter((r) => names.includes(r.reason)).reduce((t, r) => t + r.n, 0);
    return [
      { label: 'win', count: sum(['tp1', 'runner_tp2', 'runner_trail']), tone: 'pos' },
      { label: 'loss', count: sum(['stop']), tone: 'neg' },
      { label: 'scratch / breakeven', count: sum(['scratch', 'runner_be']) },
      { label: 'timeout', count: sum(['timeout']) },
      { label: 'other / unrecorded', count: sum(['reversed', 'other']) },
    ];
  });
```

Add to the template, inside `<sb-panel heading="Exit quality">`:

```html
        <h4>Exit reason</h4>
        <sb-donut [slices]="reasonSlices()" />
        <sb-histogram [bins]="reasonAvgR()" />

        <h4>Outcome mix</h4>
        <sb-donut [slices]="outcomeSlices()" />
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/sections/exit-quality.spec.ts`
Expected: PASS, 5 specs.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/sections/exit-quality.ts \
        frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts
git commit -m "feat(v78): exit-reason and outcome mix donuts"
```

---

### Task C3: P2 exit efficiency and P4 MAE distributions

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/sections/exit-quality.ts`
- Test: `frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts`

**Interfaces:**
- Consumes: `HistogramComponent`/`HistogramBin`, `MetricChipComponent` from
  `../../../ui/metric-chip`, `ExitQualityDistribution` (C1).
- Produces: nothing later tasks consume.

Both distributions are winners-only by doctrine (index Global Constraints,
quoting `stops.py:19-29`), and both captions must say so — a reader who assumes
the MAE chart covers the whole book will misread stop placement. Production
median efficiency on winners is 0.429, so the median chip is the headline
number here, not the bars.

`sb-metric-chip`'s `value` input is `number | null`, so a null median renders
without special-casing.

- [ ] **Step 1: Write the failing tests**

Append to `exit-quality.spec.ts`:

```typescript
  function withDistributions() {
    const fixture = TestBed.createComponent(ExitQualitySectionComponent);
    fixture.componentRef.setInput('data', {
      exit_reasons: [], hold_by_outcome: {}, scatter: [],
      efficiency: { bins: [{ lo: 0, hi: 0.5, count: 4 }, { lo: 0.5, hi: 1, count: 6 }],
                    n: 10, median: 0.43 },
      mae: { bins: [{ lo: 0, hi: 1, count: 9 }], n: 9, median: 0.3 },
      coverage: {}, min_cell_n: 20,
    });
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows the median capture ratio as a chip', () => {
    expect(withDistributions().textContent).toContain('0.43');
  });

  it('says both distributions are winners-only', () => {
    expect((withDistributions().textContent ?? '').toLowerCase())
      .toContain('winners only');
  });

  it('labels efficiency bins by their range', () => {
    expect(withDistributions().textContent).toContain('0.50');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/sections/exit-quality.spec.ts`
Expected: FAIL — the median chip is not rendered.

- [ ] **Step 3: Write the implementation**

Add `MetricChipComponent` to `imports`, and:

```typescript
  private static bins(dist: ExitQualityDistribution | undefined,
                      decimals: number): HistogramBin[] {
    return (dist?.bins ?? []).map((b) => ({
      label: `${b.lo.toFixed(decimals)}-${b.hi.toFixed(decimals)}`,
      count: b.count,
    }));
  }

  protected readonly efficiencyBins = computed(() =>
    ExitQualitySectionComponent.bins(this.data()?.efficiency, 2));
  protected readonly maeBins = computed(() =>
    ExitQualitySectionComponent.bins(this.data()?.mae, 1));
  protected readonly efficiencyMedian = computed(() =>
    this.data()?.efficiency?.median ?? null);
  protected readonly efficiencyN = computed(() => this.data()?.efficiency?.n ?? 0);
  protected readonly maeMedian = computed(() => this.data()?.mae?.median ?? null);
  protected readonly maeN = computed(() => this.data()?.mae?.n ?? 0);
```

Template additions inside the panel:

```html
        <h4>Exit efficiency — share of the move banked</h4>
        <p class="note">Winners only (n={{ efficiencyN() }}); a loser's
          efficiency is not the same question.</p>
        <sb-metric-chip label="Median capture" [value]="efficiencyMedian()" [decimals]="2" />
        <sb-histogram [bins]="efficiencyBins()" />

        <h4>Heat taken before it worked (MAE)</h4>
        <p class="note">Winners only (n={{ maeN() }}) — a loser's MAE is at
          least the stop it hit, so including losers would widen stops on the
          trades that should have been cut.</p>
        <sb-metric-chip label="Median MAE" [value]="maeMedian()" unit="R" [decimals]="2" />
        <sb-histogram [bins]="maeBins()" />
```

Add `.note { color: var(--text-muted); font-size: var(--text-micro); margin: 0 0 0.35rem; }`
to `styles`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/sections/exit-quality.spec.ts`
Expected: PASS, 8 specs.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/sections/exit-quality.ts \
        frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts
git commit -m "feat(v78): exit-efficiency and MAE distributions, winners only"
```

---

### Task C4: P3 disposition and P6 MFE-vs-MAE scatter

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/sections/exit-quality.ts`
- Test: `frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts`

**Interfaces:**
- Consumes: `ScatterComponent`/`ScatterPoint` (B2), `HistogramComponent`,
  `MetricChipComponent`.
- Produces: nothing later tasks consume.

`hold_by_outcome.ratio` is `avg_loser_days / avg_winner_days` and is **`None`
unless both sides independently clear `MIN_TRADES_FOR_RATIO = 5`**
(`metrics.py:328`). `severity` bands (`_DISPOSITION_HIGH = 1.5`,
`_DISPOSITION_MEDIUM = 1.2`, `metrics.py:795-796`) were borrowed from another
project and are **not calibrated on this repo** — its own docstring calls them
*"a prompt to go and look, never a verdict."* Render the severity as wording,
never as a pass/fail.

- [ ] **Step 1: Write the failing tests**

Append to `exit-quality.spec.ts`:

```typescript
  function withHold(hold: Record<string, unknown>, scatter: unknown[] = []) {
    const fixture = TestBed.createComponent(ExitQualitySectionComponent);
    fixture.componentRef.setInput('data', {
      exit_reasons: [], hold_by_outcome: hold, scatter,
      efficiency: { bins: [], n: 0, median: null },
      mae: { bins: [], n: 0, median: null },
      coverage: {}, min_cell_n: 20,
    });
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders winner and loser hold as two bars', () => {
    const text = withHold({ avg_winner_days: 0.31, avg_loser_days: 0.64,
                            ratio: 2.06, n_winners: 352, n_losers: 212 }).textContent ?? '';
    expect(text).toContain('Winners');
    expect(text).toContain('Losers');
    expect(text).toContain('2.06');
  });

  it('withholds the ratio when either side is under the floor', () => {
    const text = withHold({ avg_winner_days: 0.3, avg_loser_days: 0.6,
                            ratio: null, n_winners: 3, n_losers: 40 }).textContent ?? '';
    expect(text).not.toContain('2.0');
    expect(text.toLowerCase()).toContain('too few');
  });

  it('plots one scatter dot per trade, losers included', () => {
    const el = withHold({}, [
      { mae_r: 0.2, mfe_r: 2.0, r_realized: 1.5, outcome: 'win', ticker: 'AAPL', strategy: 'RSI' },
      { mae_r: 1.0, mfe_r: 0.4, r_realized: -1, outcome: 'loss', ticker: 'MSFT', strategy: 'RSI' },
    ]);
    expect(el.querySelectorAll('circle.pt').length).toBe(2);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/sections/exit-quality.spec.ts`
Expected: FAIL — no disposition bars, no scatter.

- [ ] **Step 3: Write the implementation**

Add `ScatterComponent` to `imports`, and:

```typescript
  protected readonly holdBins = computed<HistogramBin[]>(() => {
    const h = this.data()?.hold_by_outcome ?? {};
    return [
      { label: `Winners (n=${h.n_winners ?? 0})`, count: h.avg_winner_days ?? 0 },
      { label: `Losers (n=${h.n_losers ?? 0})`, count: h.avg_loser_days ?? 0 },
    ];
  });

  protected readonly dispositionRatio = computed(() =>
    this.data()?.hold_by_outcome?.ratio ?? null);

  /** metrics.py:328 -- ratio is null unless BOTH sides clear
   *  MIN_TRADES_FOR_RATIO independently. Say which, rather than showing a
   *  blank chip. */
  protected readonly dispositionNote = computed(() => {
    const h = this.data()?.hold_by_outcome ?? {};
    if (h.ratio != null) {
      return `Losers held ${h.ratio.toFixed(2)}x longer than winners.`
        + (h.severity ? ` Severity: ${h.severity} — a prompt to look, not a verdict.` : '');
    }
    return 'Ratio withheld: too few trades on one side to compare holds.';
  });

  protected readonly scatterPoints = computed<ScatterPoint[]>(() =>
    (this.data()?.scatter ?? []).map((p) => ({
      x: p.mae_r,
      y: p.mfe_r,
      label: `${p.ticker} ${p.strategy} ${p.outcome} ${p.r_realized ?? '?'}R`,
      tone: p.outcome === 'win' ? 'pos' : p.outcome === 'loss' ? 'neg' : 'muted',
    })));
```

Template additions inside the panel:

```html
        <h4>Hold time by outcome</h4>
        <sb-histogram [bins]="holdBins()" />
        <sb-metric-chip label="Disposition ratio" [value]="dispositionRatio()" [decimals]="2" />
        <p class="note">{{ dispositionNote() }}</p>

        <h4>Heat vs run — every closed trade</h4>
        <p class="note">Losers included here deliberately: the separation
          between the two clouds is the diagnostic, and this chart sets no
          stop.</p>
        <sb-scatter [points]="scatterPoints()" xLabel="MAE (R) — heat taken"
                    yLabel="MFE (R) — move available" />
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/sections/exit-quality.spec.ts`
Expected: PASS, 11 specs.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/sections/exit-quality.ts \
        frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts
git commit -m "feat(v78): disposition ratio and the MFE-vs-MAE scatter"
```

---

### Task C5: S1 total R contributed per strategy

**Files:**
- Create: `frontend/src/app/workspaces/analytics/sections/strategy-contribution.ts`
- Create: `frontend/src/app/workspaces/analytics/sections/strategy-contribution.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (mount only, in
  the Strategies tab)

**Interfaces:**
- Consumes: `StatRow.total_r` (A1), served in the snapshot's `by.strategy`
  rows; `HistogramComponent`/`HistogramBin`; `PanelComponent`.
- Produces: `StrategyContributionComponent` (selector `sb-strategy-contribution`).

Runs **parallel with C2–C4** — different file, and it consumes nothing those
tasks introduce.

Production holds 46 strategy cells of which 36 are under the floor, so a
win-rate-per-strategy chart would be a noise field. Total R is different in
kind: it is **additive**, so a thin cell contributes proportionally little and
that is the honest answer rather than a suppressed one. Top 12 by absolute R,
with the remainder folded into one `other (N strategies)` bar so the column
still sums to the book's total R.

- [ ] **Step 1: Write the failing test**

Create `strategy-contribution.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';

import { StrategyContributionComponent } from './strategy-contribution';

function rows(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    key: `strategy-${i}`, n: 30 - i, total_r: (i % 2 ? -1 : 1) * (n - i),
  }));
}

describe('sb-strategy-contribution', () => {
  function render(data: unknown) {
    const fixture = TestBed.createComponent(StrategyContributionComponent);
    fixture.componentRef.setInput('rows', data);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('folds everything past the top 12 into one other bar', () => {
    const text = render(rows(20)).textContent ?? '';
    expect(text).toContain('other (8 strategies)');
  });

  it('does not fold when there are 12 or fewer strategies', () => {
    expect(render(rows(5)).textContent).not.toContain('other (');
  });

  it('puts the signed value first so negative bars colour themselves', () => {
    const text = render([{ key: 'RSI', n: 30, total_r: -4.5 }]).textContent ?? '';
    expect(text).toContain('-4.50R');
  });

  it('skips a strategy with no computable R rather than plotting zero', () => {
    const text = render([{ key: 'RSI', n: 30, total_r: null }]).textContent ?? '';
    expect(text).not.toContain('RSI');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/sections/strategy-contribution.spec.ts`
Expected: FAIL — cannot resolve `./strategy-contribution`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/app/workspaces/analytics/sections/strategy-contribution.ts`:

```typescript
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { HistogramBin, HistogramComponent } from '../../../ui/histogram';
import { PanelComponent } from '../../../ui/layout';

export interface StrategyContributionRow {
  key: string;
  n: number;
  total_r: number | null;
}

const TOP = 12;

/**
 * Where the book's R actually comes from.
 *
 * Win rate per strategy cannot be shown honestly at this sample -- 36 of 46
 * live strategy cells hold fewer than MIN_CELL_N trades. Total R is additive
 * rather than a rate, so a thin cell simply contributes little, which is the
 * true answer instead of a suppressed one. That is why this chart exists
 * where a per-strategy win-rate bar does not.
 *
 * Signed value first, ASCII hyphen, so sb-histogram's default isNegative
 * predicate colours losses without a new input.
 */
@Component({
  selector: 'sb-strategy-contribution',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PanelComponent, HistogramComponent],
  template: `
    <sb-panel heading="Total R contributed per strategy">
      <p class="note">Additive, not a rate — a thin strategy contributes
        little rather than being suppressed. Top {{ top }} by absolute R.</p>
      <sb-histogram [bins]="bins()" />
    </sb-panel>
  `,
  styles: `
    .note { color: var(--text-muted); font-size: var(--text-micro); margin: 0 0 0.35rem; }
  `,
})
export class StrategyContributionComponent {
  readonly rows = input.required<readonly StrategyContributionRow[] | null>();

  protected readonly top = TOP;

  protected readonly bins = computed<HistogramBin[]>(() => {
    // A null total_r means no trade in the group had a computable R
    // (aggregate.py). Dropping it is right; plotting it at zero would claim
    // the strategy netted flat.
    const scored = (this.rows() ?? []).filter(
      (r): r is StrategyContributionRow & { total_r: number } => r.total_r !== null);
    const ranked = [...scored].sort((a, b) => Math.abs(b.total_r) - Math.abs(a.total_r));
    const head = ranked.slice(0, TOP);
    const tail = ranked.slice(TOP);

    const bins = head.map((r) => ({
      label: `${r.total_r.toFixed(2)}R · ${r.key} (n=${r.n})`,
      count: Math.abs(r.total_r),
    }));

    if (tail.length) {
      const rest = tail.reduce((sum, r) => sum + r.total_r, 0);
      bins.push({
        label: `${rest.toFixed(2)}R · other (${tail.length} strategies)`,
        count: Math.abs(rest),
      });
    }
    return bins;
  });
}
```

Mount in the Strategies tab of `analytics.ts` — one line plus the import:

```html
<sb-strategy-contribution [rows]="store.strategyContribution()" />
```

Add the computed to `analytics.store.ts`, reading the snapshot rows A1 extended:

```typescript
    strategyContribution: computed(() =>
      ((snapshot()?.by?.['strategy'] ?? []) as StrategyContributionRow[])),
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/sections/strategy-contribution.spec.ts`
Expected: PASS, 4 specs.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/sections/strategy-contribution.ts \
        frontend/src/app/workspaces/analytics/sections/strategy-contribution.spec.ts \
        frontend/src/app/stores/analytics.store.ts \
        frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(v78): total R contributed per strategy"
```
