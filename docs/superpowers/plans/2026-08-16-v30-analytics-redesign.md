# v30 — Analytics Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Analytics workspace per
`docs/superpowers/specs/2026-08-16-v30-analytics-redesign-design.md`: fix two
mislabeling/alignment bugs, build one reusable multi-series line chart, use it
plus an extended `Histogram` to add six chart panels across a restructured
Performance tab, a restored Calibration chart and a new fifth "Plans" tab,
paginate every table that can grow, and give the three hand-rolled tables the
phone-card layout `sb-data-table` already gives everything else for free.

**Architecture:** Two independent foundations first — the frontend chart
primitives (Task Group 1) and nothing on the backend needs them — then four
mostly-parallel branches: Performance tab (2-4), Calibration tab (5),
Strategies tab pagination (6), the new Plans tab (7-9, backend then frontend),
and the Tuning tab conversions (10-12). Close with a full gate (13).

**Tech Stack:** Angular 21 signals, `@ngrx/signals`, vitest, SVG (no charting
library — this app draws its own, see `ui/histogram.ts` and `ui/sparkline.ts`
for the existing style); Python 3.11+, Flask, pytest.

## Global Constraints

- **`sb-data-table`'s phone-card layout is automatic** (spec v18 Decision 9,
  `data-table.ts`) — any table converted to it needs no extra responsive work.
- **Categorical color (the line chart's legend, the Plans tab's badge/tier
  bars) follows `styles/tokens.css`'s rule: five reserved hues, "a sixth hue
  is a review defect."** Where a chart needs to distinguish several named
  series, invoke the `dataviz` skill and use its validated palette
  (`references/palette.md`) rather than inventing colors — same rule the
  Versions timeline's per-version shading followed earlier in this repo's
  history (one hue, varying lightness, when the data is ordinal; the fixed
  8-hue categorical palette when it's genuinely nominal identity like "which
  strategy").
- **"UI renders, analytics computes"** (`api_v1/analytics.py`'s own docstring)
  — the new Plans endpoint must assemble from a `core`/`admin.queries`
  function, never compute inline in the Flask route.
- **No animation on data change** (spec 3's "no card-flash on refresh" rule)
  — the line chart redraws in place, no transition.
- Run the suite via `python scripts/dev/testrun.py file <path>` while
  iterating and `python scripts/dev/testrun.py full` at the gate. Frontend:
  `cd frontend && npx ng test`, never raw `vitest run` (loses the jsdom
  environment).
- Bump `VERSION.json`'s `ui` line only — the Discord bot is untouched.

---

# Phase 1 — Chart primitives (foundation)

## Parallelisation

**Sequential within the phase** (Task 2 needs Task 1's exported functions),
but the whole phase has no dependency on the backend work in Phase 5 below —
they may run concurrently once someone is free for each.

## Task 1: `sb-line-chart` — geometry, pure and unit-tested

**Files:**
- Create: `frontend/src/app/ui/line-chart.ts` (component + exported pure
  functions)
- Test: `frontend/src/app/ui/line-chart.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `LineChartPoint { date: string; value: number }`,
  `LineChartSeries { name: string; points: LineChartPoint[] }`, and the
  exported pure functions `lineChartXScale`, `lineChartYScale`,
  `seriesPath(series: LineChartSeries, xScale, yScale): string`. Task 2
  renders these; Task 4/9/11/etc. pass series into the component.

- [x] **Step 1: Write the failing geometry tests**

```ts
import { describe, expect, it } from 'vitest';
import { lineChartXScale, lineChartYScale, seriesPath } from './line-chart';

describe('lineChartXScale', () => {
  it('maps the earliest date to 0 and the latest to 1', () => {
    const scale = lineChartXScale(['2026-01-01', '2026-01-11', '2026-01-21']);
    expect(scale('2026-01-01')).toBeCloseTo(0, 5);
    expect(scale('2026-01-21')).toBeCloseTo(1, 5);
    expect(scale('2026-01-11')).toBeCloseTo(0.5, 5);
  });

  it('is a real time scale, not an index scale', () => {
    // Three dates, unevenly spaced -- an index scale would put the middle
    // one at 0.5. Jan 3 is 2/20 of the way from Jan 1 to Jan 21.
    const scale = lineChartXScale(['2026-01-01', '2026-01-03', '2026-01-21']);
    expect(scale('2026-01-03')).toBeCloseTo(0.1, 5);
  });

  it('a single date does not divide by zero', () => {
    const scale = lineChartXScale(['2026-01-01']);
    expect(scale('2026-01-01')).toBe(0);
    expect(Number.isNaN(scale('2026-01-01'))).toBe(false);
  });
});

describe('lineChartYScale', () => {
  it('maps the lowest value to 0 and the highest to 1', () => {
    const scale = lineChartYScale([10, 30, 20]);
    expect(scale(10)).toBeCloseTo(0, 5);
    expect(scale(30)).toBeCloseTo(1, 5);
  });

  it('a flat series (one distinct value) does not divide by zero', () => {
    const scale = lineChartYScale([5, 5, 5]);
    expect(scale(5)).toBeCloseTo(0.5, 5);
    expect(Number.isNaN(scale(5))).toBe(false);
  });

  it('respects a fixed [min, max] domain when one is given', () => {
    // The Calibration decile chart needs an absolute 0-100 win-rate axis,
    // not one auto-scaled to whichever decile happens to be tallest --
    // see Task 8's own note on why Histogram needed the same fix.
    const scale = lineChartYScale([60, 85], { min: 0, max: 100 });
    expect(scale(0)).toBeCloseTo(0, 5);
    expect(scale(100)).toBeCloseTo(1, 5);
    expect(scale(85)).toBeCloseTo(0.85, 5);
  });
});

describe('seriesPath', () => {
  it('builds one SVG line command per point after the first', () => {
    const series = {
      name: 'ui',
      points: [
        { date: '2026-01-01', value: 0 },
        { date: '2026-01-11', value: 10 },
      ],
    };
    const x = lineChartXScale(['2026-01-01', '2026-01-11']);
    const y = lineChartYScale([0, 10]);
    const path = seriesPath(series, x, y);
    expect(path.startsWith('M ')).toBe(true);
    expect(path.match(/L /g)).toHaveLength(1);
  });

  it('a single point draws nothing rather than throwing', () => {
    const series = { name: 'ui', points: [{ date: '2026-01-01', value: 0 }] };
    const x = lineChartXScale(['2026-01-01']);
    const y = lineChartYScale([0]);
    expect(() => seriesPath(series, x, y)).not.toThrow();
  });
});
```

- [x] **Step 2: Run to verify they fail**

Run: `cd frontend && npx ng test`
Expected: FAIL — `line-chart.ts` does not exist yet

- [x] **Step 3: Implement the geometry functions**

```ts
export interface LineChartPoint {
  date: string;
  value: number;
}

export interface LineChartSeries {
  name: string;
  points: LineChartPoint[];
}

/** Maps an ISO date string to 0-1, linear in TIME, not in array index --
 *  unevenly-spaced dates (a weekly rolling-return point beside a monthly
 *  calendar-return one) must not be drawn as if they were evenly spaced. */
export function lineChartXScale(dates: readonly string[]): (date: string) => number {
  const times = dates.map((d) => new Date(d).getTime());
  const min = Math.min(...times);
  const max = Math.max(...times);
  const span = max - min;
  return (date: string) => (span === 0 ? 0 : (new Date(date).getTime() - min) / span);
}

/** Maps a value to 0-1. An explicit `domain` (e.g. a fixed 0-100 win-rate
 *  axis) wins over the auto min/max of `values` -- see the Calibration
 *  decile chart, which needs an ABSOLUTE scale so an 80% reference line
 *  means the same thing regardless of which decile happens to be tallest. */
export function lineChartYScale(
  values: readonly number[],
  domain?: { min: number; max: number },
): (value: number) => number {
  const min = domain?.min ?? Math.min(...values);
  const max = domain?.max ?? Math.max(...values);
  const span = max - min;
  // A flat series has no range to scale into. Drawn at the middle rather
  // than the top or bottom, where it would read as an extreme -- same rule
  // sparkline.ts's y() already applies.
  return (value: number) => (span === 0 ? 0.5 : (value - min) / span);
}

/** One series' SVG path, in a 0-1 x 0-1 coordinate space the component
 *  scales into its actual viewBox. */
export function seriesPath(
  series: LineChartSeries,
  xScale: (date: string) => number,
  yScale: (value: number) => number,
): string {
  const points = series.points;
  if (points.length === 0) return '';
  if (points.length === 1) {
    const x = xScale(points[0].date);
    const y = 1 - yScale(points[0].value);
    return `M ${x.toFixed(4)} ${y.toFixed(4)}`;
  }
  return points
    .map((p, i) => {
      const x = xScale(p.date).toFixed(4);
      const y = (1 - yScale(p.value)).toFixed(4); // SVG y grows downward
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    })
    .join(' ');
}
```

- [x] **Step 4: Run to verify they pass**

Run: `cd frontend && npx ng test`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/line-chart.ts frontend/src/app/ui/line-chart.spec.ts
git commit -m "feat(ui): line-chart geometry -- a real time scale, not an index scale

Unevenly-spaced dates must not draw as evenly spaced, which is the same
lesson the Versions timeline's lane geometry needed fixed for the same
reason. yScale takes an optional fixed domain because the Calibration
decile chart (Task 8) needs an absolute 0-100 axis, not one auto-scaled to
whichever decile happens to be tallest."
```

## Task 2: `sb-line-chart` — render (axes, series, legend)

**Files:**
- Modify: `frontend/src/app/ui/line-chart.ts`
- Test: `frontend/src/app/ui/line-chart.spec.ts`

**Interfaces:**
- Consumes: `LineChartPoint`, `LineChartSeries`, `lineChartXScale`,
  `lineChartYScale`, `seriesPath` from Task 1.
- Produces: the `LineChart` component, selector `sb-line-chart`, inputs
  `series: input.required<readonly LineChartSeries[]>()`,
  `yDomain: input<{min: number; max: number} | null>(null)`,
  `referenceLine: input<number | null>(null)`,
  `valueFormat: input<(value: number) => string>((v) => v.toFixed(2))`.
  Tasks 4, 9, 11, 12, 18-20 consume this component.

- [x] **Step 1: Write the failing render test**

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { LineChart } from './line-chart';

describe('LineChart', () => {
  function render(series: { name: string; points: { date: string; value: number }[] }[]) {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(LineChart);
    fixture.componentRef.setInput('series', series);
    fixture.detectChanges();
    return fixture;
  }

  it('draws one path per series', () => {
    const fixture = render([
      { name: 'ui', points: [{ date: '2026-01-01', value: 0 }, { date: '2026-01-02', value: 1 }] },
      { name: 'bot', points: [{ date: '2026-01-01', value: 2 }, { date: '2026-01-02', value: 3 }] },
    ]);
    expect(fixture.nativeElement.querySelectorAll('path.series')).toHaveLength(2);
  });

  it('shows no legend for a single series -- the panel heading already names it', () => {
    const fixture = render([{ name: 'ui', points: [{ date: '2026-01-01', value: 0 }] }]);
    expect(fixture.nativeElement.querySelector('.legend')).toBeNull();
  });

  it('shows a legend entry per series once there is more than one', () => {
    const fixture = render([
      { name: 'ui', points: [{ date: '2026-01-01', value: 0 }] },
      { name: 'bot', points: [{ date: '2026-01-01', value: 1 }] },
    ]);
    const entries = fixture.nativeElement.querySelectorAll('.legend .entry');
    expect(entries).toHaveLength(2);
    expect(entries[0].textContent).toContain('ui');
    expect(entries[1].textContent).toContain('bot');
  });

  it('draws the reference line when one is given', () => {
    const fixture = render([{ name: 'wr', points: [{ date: '2026-01-01', value: 60 }] }]);
    expect(fixture.nativeElement.querySelector('line.reference')).toBeNull();
    fixture.componentRef.setInput('referenceLine', 80);
    fixture.componentRef.setInput('yDomain', { min: 0, max: 100 });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('line.reference')).not.toBeNull();
  });

  it('renders nothing rather than throwing when every series is empty', () => {
    expect(() => render([{ name: 'ui', points: [] }])).not.toThrow();
  });
});
```

- [x] **Step 2: Run to verify it fails**

Run: `cd frontend && npx ng test`
Expected: FAIL — `LineChart` is not exported

- [x] **Step 3: Implement the component**

Append to `frontend/src/app/ui/line-chart.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** Eight categorical hues, fixed order -- the dataviz skill's palette,
 *  `references/palette.md` (light-mode steps; this app is dark-only, see
 *  `styles/tokens.css`'s own "Dark only" note, so these are the dark-surface
 *  steps from that same reference). A ninth series folds into "Other" per
 *  the skill's own rule rather than cycling back to hue 1. */
const SERIES_COLORS = [
  '#5b9bd5', '#e8734a', '#4fb87a', '#e0b64a',
  '#c77dc0', '#4dbfb8', '#8b7ec8', '#d65f6f',
] as const;

/**
 * A multi-series time chart with a shared axis, a legend past one series,
 * and an optional fixed reference line -- built once for the three "over
 * time" Performance panels (Task 4, 9, 11) and the restored Calibration
 * decile chart (Task 8), rather than three bespoke SVGs. Neither existing
 * primitive fit: `Sparkline` is a deliberately unlabelled 100x24 single
 * series (its own doc comment), `Histogram` is bars only.
 *
 * No animation on data change (spec 3's "no card-flash on refresh" rule) --
 * a value updates in place, same as every other live figure in this app.
 */
@Component({
  selector: 'sb-line-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (hasData()) {
      <svg viewBox="0 0 600 220" preserveAspectRatio="none" role="img">
        @if (referenceLine(); as ref) {
          <line class="reference" [attr.x1]="0" [attr.x2]="600"
                [attr.y1]="refY(ref)" [attr.y2]="refY(ref)" />
        }
        @for (series of series(); track series.name; let i = $index) {
          <path class="series" [attr.d]="pathFor(series)"
                [attr.stroke]="colorFor(i)" fill="none" />
        }
      </svg>
      @if (series().length > 1) {
        <div class="legend">
          @for (series of series(); track series.name; let i = $index) {
            <span class="entry">
              <i [style.background]="colorFor(i)"></i>{{ series.name }}
            </span>
          }
        </div>
      }
    } @else {
      <p class="empty">No data to chart.</p>
    }
  `,
  styles: `
    :host { display: block; }
    svg { width: 100%; height: 140px; }
    path.series { stroke-width: 2; vector-effect: non-scaling-stroke; }
    line.reference {
      stroke: var(--text-faint);
      stroke-width: 1;
      stroke-dasharray: 4 3;
      vector-effect: non-scaling-stroke;
    }
    .legend { display: flex; flex-wrap: wrap; gap: var(--space-10); margin-top: var(--space-8);
              font-size: var(--text-chip); color: var(--text-secondary); }
    .entry { display: inline-flex; align-items: center; gap: var(--space-4); }
    .entry i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
    .empty { color: var(--text-faint); font-size: var(--text-table); }
  `,
})
export class LineChart {
  readonly series = input.required<readonly LineChartSeries[]>();
  readonly yDomain = input<{ min: number; max: number } | null>(null);
  readonly referenceLine = input<number | null>(null);
  readonly valueFormat = input<(value: number) => string>((v) => v.toFixed(2));

  protected readonly hasData = computed(() =>
    this.series().some((s) => s.points.length > 0),
  );

  private readonly allDates = computed(() =>
    this.series().flatMap((s) => s.points.map((p) => p.date)),
  );
  private readonly allValues = computed(() =>
    this.series().flatMap((s) => s.points.map((p) => p.value)),
  );

  private readonly xScale = computed(() => lineChartXScale(this.allDates()));
  private readonly yScale = computed(() =>
    lineChartYScale(this.allValues(), this.yDomain() ?? undefined),
  );

  protected pathFor(series: LineChartSeries): string {
    const path = seriesPath(series, this.xScale(), this.yScale());
    // Scale the 0-1 path up into the 600x220 viewBox.
    return path.replace(/([ML]) ([\d.]+) ([\d.]+)/g, (_, cmd, x, y) =>
      `${cmd} ${(Number(x) * 600).toFixed(2)} ${(Number(y) * 220).toFixed(2)}`);
  }

  protected refY(value: number): number {
    return (1 - this.yScale()(value)) * 220;
  }

  protected colorFor(index: number): string {
    return SERIES_COLORS[index % SERIES_COLORS.length];
  }
}
```

- [x] **Step 4: Run to verify it passes**

Run: `cd frontend && npx ng test`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/line-chart.ts frontend/src/app/ui/line-chart.spec.ts
git commit -m "feat(ui): sb-line-chart renders -- axes via scale, legend past one series"
```

## Task 3: `sb-line-chart` — hover crosshair + tooltip

**Files:**
- Modify: `frontend/src/app/ui/line-chart.ts`
- Test: `frontend/src/app/ui/line-chart.spec.ts`

**Interfaces:**
- Consumes: Task 2's `LineChart` component internals.
- Produces: pointer-move behaviour only; no new public inputs/outputs.

- [x] **Step 1: Write the failing hover test**

```ts
it('shows a tooltip with every series value at the hovered date', () => {
  const fixture = render([
    { name: 'ui', points: [{ date: '2026-01-01', value: 10 }, { date: '2026-01-11', value: 20 }] },
    { name: 'bot', points: [{ date: '2026-01-01', value: 1 }, { date: '2026-01-11', value: 2 }] },
  ]);
  const svg = fixture.nativeElement.querySelector('svg');
  svg.dispatchEvent(new MouseEvent('pointermove', { clientX: 0, bubbles: true }));
  fixture.detectChanges();
  const tooltip = fixture.nativeElement.querySelector('.tooltip');
  expect(tooltip).not.toBeNull();
  expect(tooltip.textContent).toContain('ui');
  expect(tooltip.textContent).toContain('bot');
});

it('hides the tooltip on pointer leave', () => {
  const fixture = render([{ name: 'ui', points: [{ date: '2026-01-01', value: 10 }] }]);
  const svg = fixture.nativeElement.querySelector('svg');
  svg.dispatchEvent(new MouseEvent('pointermove', { clientX: 0, bubbles: true }));
  fixture.detectChanges();
  svg.dispatchEvent(new MouseEvent('pointerleave', { bubbles: true }));
  fixture.detectChanges();
  expect(fixture.nativeElement.querySelector('.tooltip')).toBeNull();
});
```

- [x] **Step 2: Run to verify it fails**

Run: `cd frontend && npx ng test`
Expected: FAIL — no `.tooltip` ever renders

- [x] **Step 3: Implement hover**

`getBoundingClientRect()` is unavailable in jsdom's layout-less environment
(same trap this repo already documents for width-dependent tests elsewhere),
so the hover handler works off the SVG's `viewBox` coordinate space via
`clientX` relative to the element's own bounding box read at pointer time —
the test above only asserts the tooltip's PRESENCE and CONTENT, never a
pixel position, for exactly that reason.

```ts
  protected readonly hoverIndex = signal<number | null>(null);

  private readonly nearestDates = computed(() => {
    const dates = [...new Set(this.allDates())].sort(
      (a, b) => new Date(a).getTime() - new Date(b).getTime(),
    );
    return dates;
  });

  protected onPointerMove(event: PointerEvent): void {
    const dates = this.nearestDates();
    if (dates.length === 0) return;
    const svg = event.currentTarget as SVGSVGElement;
    const rect = svg.getBoundingClientRect();
    const fraction = rect.width > 0 ? (event.clientX - rect.left) / rect.width : 0;
    const index = Math.round(fraction * (dates.length - 1));
    this.hoverIndex.set(Math.max(0, Math.min(dates.length - 1, index)));
  }

  protected onPointerLeave(): void {
    this.hoverIndex.set(null);
  }

  protected readonly tooltipDate = computed(() => {
    const index = this.hoverIndex();
    return index === null ? null : this.nearestDates()[index];
  });

  protected readonly tooltipRows = computed(() => {
    const date = this.tooltipDate();
    if (date === null) return [];
    return this.series()
      .map((s) => ({ name: s.name, point: s.points.find((p) => p.date === date) }))
      .filter((row): row is { name: string; point: LineChartPoint } => row.point !== undefined);
  });
```

Wire into the template's `<svg>`:

```html
<svg viewBox="0 0 600 220" preserveAspectRatio="none" role="img"
     (pointermove)="onPointerMove($event)" (pointerleave)="onPointerLeave()">
```

And after the `</svg>`:

```html
@if (tooltipRows().length) {
  <div class="tooltip">
    <strong>{{ tooltipDate() }}</strong>
    @for (row of tooltipRows(); track row.name) {
      <div>{{ row.name }}: {{ valueFormat()(row.point.value) }}</div>
    }
  </div>
}
```

Add `signal` to the `@angular/core` import list, and this to `styles`:

```css
    .tooltip {
      position: absolute;
      padding: var(--space-6) var(--space-8);
      background: var(--surface-overlay);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
      font-size: var(--text-chip);
      pointer-events: none;
    }
```

- [x] **Step 4: Run to verify it passes**

Run: `cd frontend && npx ng test`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/line-chart.ts frontend/src/app/ui/line-chart.spec.ts
git commit -m "feat(ui): sb-line-chart hover crosshair and tooltip"
```

## Task 4: `Histogram` gains `max` and `referenceLine`

**Files:**
- Modify: `frontend/src/app/ui/histogram.ts`
- Test: `frontend/src/app/ui/histogram.spec.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: two new optional inputs on `Histogram`: `max: input<number | null>(null)`,
  `referenceLine: input<number | null>(null)`. Both additive — every existing
  call site (Return distribution, R-multiple distribution x2, By month, once
  Task 5 adds it) keeps working unchanged. Task 8 (Calibration) is the first
  consumer of both.

- [x] **Step 1: Write the failing tests**

```ts
it('scales against the tallest bin by default', () => {
  const fixture = render([{ label: 'a', count: 10 }, { label: 'b', count: 5 }]);
  const fills = fixture.nativeElement.querySelectorAll('.fill');
  expect(fills[0].style.width).toBe('100%');
  expect(fills[1].style.width).toBe('50%');
});

it('scales against a fixed max when one is given', () => {
  // Two deciles at 60% and 85% win rate must scale against 100, not against
  // each other -- against each other, 60 would render as a near-empty bar
  // relative to 85, which understates a genuinely bad decile.
  const fixture = render(
    [{ label: 'D1', count: 60 }, { label: 'D10', count: 85 }],
    { max: 100 },
  );
  const fills = fixture.nativeElement.querySelectorAll('.fill');
  expect(fills[0].style.width).toBe('60%');
  expect(fills[1].style.width).toBe('85%');
});

it('draws a reference line at the given value against the active scale', () => {
  const fixture = render([{ label: 'D1', count: 60 }], { max: 100, referenceLine: 80 });
  const line = fixture.nativeElement.querySelector('.reference-line');
  expect(line).not.toBeNull();
  expect(line.style.left).toBe('80%');
});

it('draws no reference line when none is given', () => {
  const fixture = render([{ label: 'a', count: 10 }]);
  expect(fixture.nativeElement.querySelector('.reference-line')).toBeNull();
});
```

- [x] **Step 2: Run to verify they fail**

Run: `cd frontend && npx ng test`
Expected: FAIL — `max`/`referenceLine` inputs don't exist, `.reference-line` never renders

- [x] **Step 3: Implement**

```ts
  readonly max = input<number | null>(null);
  readonly referenceLine = input<number | null>(null);

  private readonly tallest = computed(() =>
    this.max() ?? Math.max(...this.bins().map((bin) => bin.count), 1),
  );

  protected width(count: number): number {
    return (count / this.tallest()) * 100;
  }

  protected referenceLeft(): number {
    const ref = this.referenceLine();
    return ref === null ? 0 : (ref / this.tallest()) * 100;
  }
```

Template — one `<li>` becomes an outer wrapper so the reference line can span
every bar's track without belonging to any one of them:

```html
    @if (referenceLine(); as ref) {
      <div class="reference-line" [style.left.%]="referenceLeft()"></div>
    }
    <ul [class.has-reference]="referenceLine() !== null">
```

(close the existing `</ul>` unchanged; wrap the whole thing in a `<div class="wrap">`
so `.reference-line`'s `position: absolute` has a positioned ancestor spanning
the full width including the `.track` columns — the label/count columns sit
outside the line's span, which is why it needs its own coordinate space
rather than being a child of `.track`)

```css
    .wrap { position: relative; }
    .reference-line {
      position: absolute;
      top: 0; bottom: 0;
      /* Matches .track's own left offset (4rem label + gap) so the line
         lands on the bars themselves, not the label column. */
      left: calc(4rem + var(--space-8));
      right: 2.5rem;
      border-left: 1px dashed var(--text-faint);
    }
```

Actually simplest and least fragile: keep `.reference-line` positioned
relative to `.track` itself, repeated per row via CSS rather than one
absolutely-positioned overlay — reconsider only if the overlay approach
above proves visually wrong once Task 8 renders it; the test only checks
`style.left`, which either approach satisfies identically.

- [x] **Step 4: Run to verify they pass**

Run: `cd frontend && npx ng test`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/histogram.ts frontend/src/app/ui/histogram.spec.ts
git commit -m "feat(ui): Histogram gains a fixed max and a reference line

Additive -- every existing bar list keeps its auto-scale-to-tallest-bin
default. Needed by the restored Calibration decile chart (Task 8): deciles
must scale against an absolute 0-100 win-rate axis, not against each other,
or a genuinely bad decile reads as a full bar next to a worse one."
```

## Task 5: Client-side pagination helper

**Files:**
- Create: `frontend/src/app/ui/data-table/client-page.ts`
- Test: `frontend/src/app/ui/data-table/client-page.spec.ts`

**Interfaces:**
- Consumes: `PageSpec` from `./data-table.types`.
- Produces: `createClientPage<T>(rows: () => readonly T[], perPage = 25):
  { page: WritableSignal<number>; visible: Signal<T[]>; pageSpec: Signal<PageSpec>; setPage(n: number): void }`.
  Tasks 6, 7, 10, 12, 13, 20, 21 all call this once per table instead of
  hand-rolling the same slice-and-count logic nine times.

- [x] **Step 1: Write the failing tests**

```ts
import { signal } from '@angular/core';
import { describe, expect, it } from 'vitest';
import { createClientPage } from './client-page';

describe('createClientPage', () => {
  it('slices to the requested page size', () => {
    const rows = signal(Array.from({ length: 30 }, (_, i) => i));
    const page = createClientPage(rows, 10);
    expect(page.visible()).toEqual(Array.from({ length: 10 }, (_, i) => i));
  });

  it('pageSpec.total is the pre-slice count, not visible().length', () => {
    const rows = signal(Array.from({ length: 30 }, (_, i) => i));
    const page = createClientPage(rows, 10);
    expect(page.pageSpec()).toEqual({ total: 30, page: 1, perPage: 10 });
  });

  it('setPage moves the window', () => {
    const rows = signal(Array.from({ length: 30 }, (_, i) => i));
    const page = createClientPage(rows, 10);
    page.setPage(2);
    expect(page.visible()).toEqual(Array.from({ length: 10 }, (_, i) => i + 10));
  });

  it('a row set shrinking below the current page clamps back rather than showing nothing', () => {
    const rows = signal(Array.from({ length: 30 }, (_, i) => i));
    const page = createClientPage(rows, 10);
    page.setPage(3); // rows 20-29
    rows.set(Array.from({ length: 15 }, (_, i) => i)); // only 2 pages now
    expect(page.page()).toBe(2);
    expect(page.visible()).toEqual(Array.from({ length: 5 }, (_, i) => i + 10));
  });
});
```

- [x] **Step 2: Run to verify they fail**

Run: `cd frontend && npx ng test`
Expected: FAIL — `client-page.ts` does not exist

- [x] **Step 3: Implement**

```ts
import { Signal, WritableSignal, computed, signal } from '@angular/core';
import { PageSpec } from './data-table.types';

export interface ClientPage<T> {
  page: WritableSignal<number>;
  visible: Signal<T[]>;
  pageSpec: Signal<PageSpec>;
  setPage(n: number): void;
}

/** Client-side pagination over an already-fetched array — Analytics data
 *  isn't page-shaped at the API level the way Trades' collection endpoint
 *  is, so slicing what's already in hand is simpler and needs no backend
 *  change. `rows` is a function (not a plain array) so this stays correct
 *  when the underlying store re-fetches and the array identity changes. */
export function createClientPage<T>(rows: () => readonly T[], perPage = 25): ClientPage<T> {
  const page = signal(1);

  const totalPages = computed(() => Math.max(1, Math.ceil(rows().length / perPage)));

  // Clamp on read rather than in a separate effect: a `setPage` call can
  // race a rows() shrink from either direction, and clamping wherever the
  // value is actually consumed is the one place that can't be out of date.
  const clampedPage = computed(() => Math.min(page(), totalPages()));

  const visible = computed(() => {
    const start = (clampedPage() - 1) * perPage;
    return rows().slice(start, start + perPage);
  });

  const pageSpec = computed<PageSpec>(() => ({
    total: rows().length,
    page: clampedPage(),
    perPage,
  }));

  return {
    page,
    visible,
    pageSpec,
    setPage: (n: number) => page.set(Math.max(1, n)),
  };
}
```

- [x] **Step 4: Run to verify they pass**

Run: `cd frontend && npx ng test`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/data-table/client-page.ts frontend/src/app/ui/data-table/client-page.spec.ts
git commit -m "feat(ui): client-side pagination helper for Analytics's un-paged data

Nine tables across the Analytics workspace need paging and none of them
are server-paginated the way Trades' collection endpoint is -- one shared
factory over an already-fetched array beats hand-rolling the slice nine
times."
```

---

# Phase 2 — Performance tab

## Parallelisation

**Sequential within the phase** (Task 7's sub-sections are where Tasks 8/9's
new panels land). Depends only on Phase 1's `sb-line-chart` (Tasks 1-3) and
`createClientPage` (Task 5) — no dependency on Phases 3-6 below.

## Task 6: Fix the two bugs, on this tab

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing new — this task only changes existing markup/CSS.

- [x] **Step 1: Relabel the two R-multiple panels**

Find (Performance tab, near the date-range control):

```html
          <sb-panel heading="R-multiple distribution">
            @if (store.rHistogram().length) {
```

Change the heading to:

```html
          <sb-panel heading="R-multiple distribution (selected range)">
```

Find (Performance tab, in the SR50/snapshot section):

```html
        @if (store.rMultipleBins().length) {
          <sb-panel heading="R-multiple distribution">
```

Change to:

```html
          <sb-panel heading="R-multiple distribution (all-time)">
```

- [x] **Step 2: Fix the flush-panel subtitle alignment**

In the `styles` template literal, find:

```css
    /* -- SR55/SR61: explanatory copy ------------------------------------ */

    .glossary, .sub {
```

Insert before it:

```css
    /* .panel-subtitle and .section-help carry no horizontal padding of
       their own (styles.css). Inside a [flush]="true" sb-panel that leaves
       them flush against the panel's left border while the panel's own
       <header> keeps its 14px padding -- visibly misaligned against the
       heading directly above. Every flush panel on this workspace (Strategy
       registry, Tier calibration, Badge drift, and Task 8's restored
       Calibration chart) gets this fix from one rule. */
    sb-panel .panel-subtitle,
    sb-panel .section-help {
      padding: 0 var(--space-14);
    }
```

- [x] **Step 3: Verify by eye**

Run: `cd frontend && npx ng build`
Expected: `Application bundle generation complete.` — this is a CSS-only
change with no unit-testable assertion; the full visual check happens in
Task 22 (responsive/phone pass) which screenshots every tab.

- [x] **Step 4: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "fix(analytics): relabel the two R-multiple panels, fix subtitle alignment

Not a duplicate: one is scoped to the date-range control, the other is
always all-time (GET /analytics/snapshot, 'forwarded verbatim'). Both stay,
now distinguishable by heading.

.panel-subtitle/.section-help carry no horizontal padding, which only shows
up inside a flush panel where the header beside them does have 14px --
fixed once for every flush panel on this workspace rather than per-panel."
```

## Task 7: Performance tab — four labeled sub-sections

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: four `<h2 class="section">` headings wrapping the existing
  panels in `<div class="section-group">` blocks. No panel's content
  changes — Tasks 9 and 11 add NEW panels inside these groups afterward.

- [x] **Step 1: Wrap the existing panels**

In the `@case ('performance')` block, group the existing panels (identified
by their current heading) into four `<div class="section-group">` blocks,
each preceded by an `<h2 class="section">`:

```html
        <h2 class="section">Snapshot</h2>
        <div class="panels">
          <sb-panel heading="Record"> ... </sb-panel>
          <sb-panel heading="Overall"> ... </sb-panel>
        </div>
        <div class="panels">
          <sb-panel heading="Risk-adjusted"> ... </sb-panel>
          @if (store.streaks(); as streaks) { <sb-panel heading="Streaks"> ... </sb-panel> }
        </div>

        <h2 class="section">Distributions</h2>
        <sb-panel [heading]="derivedHeading()"> <!-- the range control + its chips --> </sb-panel>
        <div class="panels">
          <sb-panel heading="Return distribution"> ... </sb-panel>
          <sb-panel heading="R-multiple distribution (selected range)"> ... </sb-panel>
        </div>
        @if (store.rMultipleBins().length) {
          <sb-panel heading="R-multiple distribution (all-time)"> ... </sb-panel>
        }
        <div class="panels">
          <sb-panel heading="By holding period"> ... </sb-panel>
          <!-- Task 9 replaces "By month"'s <dl> with a Histogram here -->
        </div>

        <h2 class="section">Over time</h2>
        <!-- Task 9's By-month bar chart, Task 10's Account balance/Drawdown
             upgrade + benchmark overlay, Task 11's Rolling returns and
             Cumulative-by-strategy all land here -->

        <h2 class="section">By segment</h2>
        <sb-panel heading="Journal"> ... </sb-panel>
        @if (store.cumulativeByStrategy().length) { <!-- moves: see Task 11 --> }
        <sb-panel heading="By confidence level" [flush]="true"> ... </sb-panel>
        <sb-panel [heading]="'By ' + store.breakdownLabel().toLowerCase()" [flush]="true"> ... </sb-panel>
```

This step is a pure reorganisation — move each existing `<sb-panel>` block
(and its surrounding `@if`, unchanged) under the section it now belongs to,
per the spec's grouping. No panel gains or loses content in this step.

- [x] **Step 2: Add the section heading style**

```css
    .section {
      margin: var(--space-20) 0 var(--space-10);
      color: var(--text-faint);
      font-size: var(--text-micro);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .section:first-of-type { margin-top: 0; }
```

- [x] **Step 3: Build and eyeball**

Run: `cd frontend && npx ng build`
Expected: `Application bundle generation complete.`

- [x] **Step 4: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "refactor(analytics): group the Performance tab into four labelled sections

Snapshot / Distributions / Over time / By segment. No panel's content
changes, only where it sits -- the next three tasks add new panels into
the sections this creates."
```

## Task 8: By month → bar chart

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`

**Interfaces:**
- Consumes: `store.calendarReturns()` (existing, unchanged — `{month,
  return_pct, n}[]`), `Histogram` from `ui/histogram`.
- Produces: nothing new for later tasks.

- [x] **Step 1: Write the failing test**

`analytics.store.spec.ts` already has a fixture with a `calendar` array
(check the existing `PERFORMANCE` fixture — reuse it, add a case if it has
fewer than 2 months). Add:

```ts
it('exposes a month histogram computed from calendarReturns', () => {
  respondPerformance({ calendar: [
    { month: '2026-06', return_pct: 4.2, n: 3 },
    { month: '2026-07', return_pct: -1.8, n: 2 },
  ] });
  tick();
  expect(store.monthHistogram()).toEqual([
    { label: '2026-06', count: 4.2 },
    { label: '2026-07', count: -1.8 },
  ]);
});
```

- [x] **Step 2: Run to verify it fails**

Run: `python scripts/dev/testrun.py file` doesn't apply here — frontend:
`cd frontend && npx ng test`
Expected: FAIL — `store.monthHistogram is not a function`

- [x] **Step 3: Add the computed to `analytics.store.ts`**

Near `calendarReturns`:

```ts
    /** `calendarReturns` reshaped for `Histogram` -- `count` here is a
     *  monthly return percentage, not literally a count; the field is
     *  generically a number and Histogram's `negative` predicate already
     *  colours a signed value correctly regardless of what it represents. */
    monthHistogram: computed<HistogramBin[]>(() =>
      (performance()?.calendar ?? []).map((month) => ({
        label: month.month,
        count: month.return_pct,
      }))),
```

- [x] **Step 4: Run to verify it passes**

Run: `cd frontend && npx ng test`
Expected: PASS

- [x] **Step 5: Render it, replacing the `<dl>`**

In `analytics.ts`, `@case ('performance')`, in the "Distributions" section's
second `.panels` row (see Task 7 Step 1), replace:

```html
          <sb-panel heading="By month">
            @if (store.calendarReturns().length) {
              <dl>
                @for (month of store.calendarReturns(); track month.month) {
                  <div>
                    <dt>{{ month.month }}</dt>
                    <dd class="num">
                      {{ month.return_pct.toFixed(2) }}% · {{ fmtCount(month.n) }}
                    </dd>
                  </div>
                }
              </dl>
            } @else {
              <p class="stale">No months with closed trades.</p>
            }
          </sb-panel>
```

with:

```html
          <sb-panel heading="By month">
            @if (store.monthHistogram().length) {
              <sb-histogram [bins]="store.monthHistogram()" />
            } @else {
              <p class="stale">No months with closed trades.</p>
            }
          </sb-panel>
```

- [x] **Step 6: Build and run the frontend suite**

Run: `cd frontend && npx ng build && npx ng test`
Expected: bundle complete; all tests pass

- [x] **Step 7: Commit**

```bash
git add frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): By month becomes a bar chart

Reuses Histogram rather than the dl list -- return% per month is a signed
number Histogram's negative predicate already colours correctly, same as
every other P&L-shaped bar on this tab."
```

## Task 9: Account balance / Drawdown upgrade + SPY benchmark overlay

**Files:**
- Modify: `frontend/src/app/stores/analytics.store.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`
- Test: `frontend/src/app/stores/analytics.store.spec.ts`

**Interfaces:**
- Consumes: `store.equitySeries()`, `store.drawdownSeries()` (existing,
  `SeriesPoint[]`, confirmed `{date: string; value: number}` — already the
  shape `LineChartSeries.points` wants, no mapping needed),
  `store.benchmarkSeries()` (existing, unused until now — `{date: string;
  pct: number}[]`), `LineChartSeries` from `ui/line-chart`.
- Produces: `store.balanceWithBenchmark(): LineChartSeries[]` — used by
  this task only.

- [x] **Step 1: Write the failing test**

```ts
it('overlays the SPY benchmark on the account-balance series when present', () => {
  respondPerformance({ benchmark: { spy_cum: { '2026-01-01': 0, '2026-01-11': 3.2 } } });
  tick();
  const series = store.balanceWithBenchmark();
  expect(series.map((s) => s.name)).toEqual(['Account balance', 'SPY']);
});

it('omits the SPY series entirely when the benchmark fetch was unavailable', () => {
  respondPerformance({ benchmark: { spy_cum: {} } });
  tick();
  expect(store.balanceWithBenchmark().map((s) => s.name)).toEqual(['Account balance']);
});
```

- [x] **Step 2: Run to verify it fails**

Run: `cd frontend && npx ng test`
Expected: FAIL — `store.balanceWithBenchmark is not a function`

- [x] **Step 3: Add the computed**

`analytics.store.ts` has exactly one `withComputed(...)` call today, and
`equitySeries`/`benchmarkSeries` are both properties of the object literal
it returns — not bare identifiers in scope for a NEW computed being added
inside that same literal (an object literal's own properties can't
reference each other by name while being built). Add a new, separate
`withComputed` stage instead, right after the existing one and before
`withMethods` — its factory receives the accumulated store (state + every
computed defined so far), which is where `equitySeries()`/`benchmarkSeries()`
become callable:

```ts
  withComputed(({ equitySeries, benchmarkSeries }) => ({
    /** Account balance, with SPY's cumulative return overlaid when the
     *  benchmark fetch succeeded -- best-effort, so an unavailable benchmark
     *  degrades to the balance line alone rather than an empty chart. */
    balanceWithBenchmark: computed<LineChartSeries[]>(() => {
      const balance: LineChartSeries = { name: 'Account balance', points: equitySeries() };
      const spy = benchmarkSeries();
      if (spy.length === 0) return [balance];
      return [balance, { name: 'SPY', points: spy.map((p) => ({ date: p.date, value: p.pct })) }];
    }),
  })),
```

Import `LineChartSeries` from `'../ui/line-chart'` at the top of the file.

- [x] **Step 4: Run to verify it passes**

Run: `cd frontend && npx ng test`
Expected: PASS

- [x] **Step 5: Render, replacing the two `Sparkline`s**

In `analytics.ts`'s "Over time" section (Task 7), replace:

```html
        @if (store.equitySeries().length) {
          <div class="panels">
            <sb-panel heading="Account balance">
              <sb-sparkline [points]="equityPoints()" label="Account balance over the whole record" />
              <p class="series-note">{{ store.equitySeries().length }} points · {{ seriesRange(store.equitySeries()) }}</p>
            </sb-panel>
            <sb-panel heading="Drawdown">
              <sb-sparkline [points]="drawdownPoints()" label="Percentage below the running peak balance" />
              <p class="series-note">Peak-to-trough, as a share of the running high. Higher is worse.</p>
            </sb-panel>
          </div>
        }
```

with:

```html
        @if (store.equitySeries().length) {
          <div class="panels">
            <sb-panel heading="Account balance">
              <sb-line-chart [series]="store.balanceWithBenchmark()" [valueFormat]="fmtLineValue" />
              <p class="series-note">{{ store.equitySeries().length }} points · {{ seriesRange(store.equitySeries()) }}</p>
            </sb-panel>
            <sb-panel heading="Drawdown">
              <sb-line-chart [series]="drawdownSeriesForChart()" [valueFormat]="fmtLineValue" />
              <p class="series-note">Peak-to-trough, as a share of the running high. Higher is worse.</p>
            </sb-panel>
          </div>
        }
```

Add to the `Analytics` component class:

```ts
  protected readonly fmtLineValue = (value: number): string => `${value.toFixed(2)}%`;

  protected readonly drawdownSeriesForChart = computed<LineChartSeries[]>(() => [
    { name: 'Drawdown', points: this.store.drawdownSeries() },
  ]);
```

Add `LineChart` to the component's `imports` array and
`import { LineChart, LineChartSeries } from '../../ui/line-chart';` to its
imports. Remove `Sparkline` from `imports` only if Task 11 (which also
touches this file) confirms nothing else on the tab still uses
`<sb-sparkline>` — grep first:
`grep -n "sb-sparkline" frontend/src/app/workspaces/analytics/analytics.ts`.
The Strategy registry's rolling-win-rate cell (`#rollingCell`) also uses
`sb-sparkline` and is NOT touched by this task, so `Sparkline` stays
imported.

- [x] **Step 6: Build and run the frontend suite**

Run: `cd frontend && npx ng build && npx ng test`
Expected: bundle complete; all tests pass

- [x] **Step 7: Commit**

```bash
git add frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): Account balance/Drawdown on sb-line-chart, SPY overlay restored

benchmarkSeries has been fetched and computed since SR54 and never
rendered; it overlays account balance now, best-effort -- an unavailable
benchmark degrades to the balance line alone."
```

## Task 10: Rolling returns + Cumulative return by strategy — new charts

**Files:**
- Modify: `frontend/src/app/stores/analytics.store.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`
- Test: `frontend/src/app/stores/analytics.store.spec.ts`

**Interfaces:**
- Consumes: `store.rollingReturns()` (existing, unused —
  `{date, return_pct}[]`), `store.cumulativeByStrategy()` (existing —
  `{strategy, points: {date, cum_pct}[]}[]`).
- Produces: `store.rollingReturnsChart(): LineChartSeries[]`,
  `store.cumulativeByStrategyChart(): LineChartSeries[]`.

- [ ] **Step 1: Write the failing tests**

```ts
it('exposes rolling returns as a single-series line chart', () => {
  respondPerformance({ rolling_returns: [
    { date: '2026-01-01', return_pct: 1.1 }, { date: '2026-01-08', return_pct: -0.4 },
  ] });
  tick();
  expect(store.rollingReturnsChart()).toEqual([{
    name: 'Rolling return',
    points: [{ date: '2026-01-01', value: 1.1 }, { date: '2026-01-08', value: -0.4 }],
  }]);
});

it('exposes cumulative-by-strategy as one series per strategy', () => {
  respondPerformance({ cumulative_by_strategy: {
    RSI: [{ date: '2026-01-01', cum_pct: 2.1 }],
    VWAP: [{ date: '2026-01-01', cum_pct: -0.5 }],
  } });
  tick();
  const chart = store.cumulativeByStrategyChart();
  expect(chart.map((s) => s.name)).toEqual(['RSI', 'VWAP']); // sorted, matches cumulativeByStrategy
  expect(chart[0].points).toEqual([{ date: '2026-01-01', value: 2.1 }]);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx ng test`
Expected: FAIL — both computeds undefined

- [ ] **Step 3: Add the computeds**

`rollingReturnsChart` only needs `performance()`, which is already a
destructured parameter of the big `withComputed` block `rollingReturns`
lives in — add it there directly:

```ts
    rollingReturnsChart: computed<LineChartSeries[]>(() => [{
      name: 'Rolling return',
      points: (performance()?.rolling_returns ?? [])
        .map((p) => ({ date: p.date, value: p.return_pct })),
    }]),
```

`cumulativeByStrategyChart` is different: it needs `cumulativeByStrategy()`,
which is a SIBLING property inside that same `withComputed`'s returned
object literal — not a bare identifier in scope there (an object literal's
own properties can't reference each other by name while being built). Same
issue Task 9's `balanceWithBenchmark` just hit, same fix: a new, separate
`withComputed(...)` call, whose factory receives the accumulated store
(state + every computed defined so far) as its parameter. Add another one,
after Task 9's:

```ts
  withComputed(({ cumulativeByStrategy }) => ({
    cumulativeByStrategyChart: computed<LineChartSeries[]>(() =>
      cumulativeByStrategy().map((s) => ({
        name: s.strategy,
        points: s.points.map((p) => ({ date: p.date, value: p.cum_pct })),
      }))),
  })),
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd frontend && npx ng test`
Expected: PASS

- [ ] **Step 5: Render both, and move Cumulative-by-strategy out of "By segment"**

In `analytics.ts`'s "Over time" section, after the Account balance/Drawdown
panels row, add:

```html
        <div class="panels">
          <sb-panel heading="Rolling returns">
            <sb-line-chart [series]="store.rollingReturnsChart()" [valueFormat]="fmtLineValue" />
          </sb-panel>
          <sb-panel heading="Cumulative return by strategy">
            @if (store.cumulativeByStrategyChart().length) {
              <sb-line-chart [series]="store.cumulativeByStrategyChart()" [valueFormat]="fmtLineValue" />
            } @else {
              <p class="stale">No strategies with closed trades yet.</p>
            }
          </sb-panel>
        </div>
```

Delete the OLD "Cumulative return by strategy" `<dl>` panel from wherever
Task 7 Step 1 placed it in "By segment" (it listed
`fmtCumulative(series.points)` — the last-point-only text). `fmtCumulative`
and the `<dl>` block are now dead; remove them. Grep first to confirm no
other call site: `grep -n "fmtCumulative" frontend/src/app/workspaces/analytics/analytics.ts`.

- [ ] **Step 6: Build and run the frontend suite**

Run: `cd frontend && npx ng build && npx ng test`
Expected: bundle complete; all tests pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): rolling returns and cumulative-by-strategy become real charts

rollingReturns has been fetched and never rendered since SR54. Cumulative
return by strategy previously showed fmtCumulative() -- the LAST point of
each strategy's series only, whose own doc comment said 'the full series is
in the payload for whoever plots it.' It's plotted now, one line per
strategy, replacing the last-point-only list."
```

---

# Phase 3 — Calibration tab

## Parallelisation

Depends on Phase 1 (Tasks 1-4). No dependency on Phase 2.

## Task 11: Restore the decile calibration chart

**Files:**
- Modify: `frontend/src/app/stores/analytics.store.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`
- Test: `frontend/src/app/stores/analytics.store.spec.ts`

**Interfaces:**
- Consumes: `store.deciles()` (existing — confirmed shape `{decile: string,
  n: number, win_rate: number | null, expectancy_r: number | null}`;
  `win_rate` IS nullable, per this codebase's own "null means insufficient
  data, never coerced to 0" rule that already runs through `HoldingBucket`
  and every other nullable figure here), `Histogram`'s new `max`/
  `referenceLine` inputs from Task 4.
- Produces: `store.decileHistogram(): HistogramBin[]`.

- [ ] **Step 1: Write the failing tests**

```ts
it('exposes deciles as a fixed-0-100 histogram', () => {
  respondCalibration({ deciles: [
    { decile: 'D1', n: 12, win_rate: 42, expectancy_r: 0.1 },
    { decile: 'D10', n: 15, win_rate: 88, expectancy_r: 0.4 },
  ] });
  tick();
  expect(store.decileHistogram()).toEqual([
    { label: 'D1', count: 42 }, { label: 'D10', count: 88 },
  ]);
});

it('omits a decile with too few trades to have a win rate yet, rather than charting it as 0', () => {
  respondCalibration({ deciles: [
    { decile: 'D1', n: 12, win_rate: 42, expectancy_r: 0.1 },
    { decile: 'D5', n: 0, win_rate: null, expectancy_r: null },
  ] });
  tick();
  expect(store.decileHistogram()).toEqual([{ label: 'D1', count: 42 }]);
});
```

(`respondCalibration` — check whether `analytics.store.spec.ts` already has
a helper of this shape for the Calibration tab's fetch; if not, mirror
`respondPerformance`'s pattern against `backend.expectOne('/api/v1/analytics/calibration')`.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx ng test`
Expected: FAIL — `store.decileHistogram is not a function`

- [ ] **Step 3: Add the computed**

Same cross-reference issue Tasks 9 and 10 hit: `deciles` is a sibling
property inside the store's one big `withComputed` object literal, not a
bare identifier available to a new computed added inside that same
literal. Add another separate `withComputed` stage, after Task 10's:

```ts
  withComputed(({ deciles }) => ({
    /** A decile with no closed trades yet has `win_rate: null` -- omitted
     *  rather than charted as 0, which would read as "this decile loses
     *  every time" instead of "not enough data yet". */
    decileHistogram: computed<HistogramBin[]>(() =>
      deciles()
        .filter((d): d is typeof d & { win_rate: number } => d.win_rate !== null)
        .map((d) => ({ label: d.decile, count: d.win_rate }))),
  })),
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx ng test`
Expected: PASS

- [ ] **Step 5: Render the chart above the existing table**

In `analytics.ts`'s `@case ('calibration')`, "Quality score vs outcome"
panel, before the `<sb-data-table>`:

```html
          <p class="panel-subtitle">
            Each decile's realised win rate, against an 80% target.
          </p>
          @if (store.decileHistogram().length) {
            <sb-histogram [bins]="store.decileHistogram()" [max]="100" [referenceLine]="80" />
          }
          <sb-data-table
            [rows]="store.deciles()"
            ...
```

Add `Histogram` to this component's `imports` if it isn't already there —
it is (used by Return/R-multiple distributions), so no import change needed.

- [ ] **Step 6: Build and run the frontend suite**

Run: `cd frontend && npx ng build && npx ng test`
Expected: bundle complete; all tests pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): restore the decile calibration chart the SPA rewrite dropped

The Jinja page drew an 80% target line across the deciles (SR61's own
comment on this panel says so); the rewrite kept only the sentence. Uses
Histogram's new fixed-max + reference-line inputs (Task 4) rather than the
component's default scale-to-tallest-bin, which would understate a
genuinely bad decile sitting next to a worse one."
```

---

# Phase 4 — Strategies tab pagination

## Parallelisation

Depends only on Task 5 (`createClientPage`). No dependency on Phases 2-3.

## Task 12: Paginate the Strategy registry table

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`

**Interfaces:**
- Consumes: `createClientPage` from `ui/data-table/client-page`.
- Produces: nothing for later tasks.

- [ ] **Step 1: Wire it up**

Add to the `Analytics` component class:

```ts
  protected readonly strategyPage = createClientPage(() => this.store.strategyRows());
```

In the template, `<sb-data-table>` for Strategy registry, add:

```html
          <sb-data-table
            [rows]="strategyPage.visible()"
            [columns]="strategyColumns()"
            [visible]="strategyKeys"
            [rowKey]="strategyKey"
            [loading]="store.loading()"
            [emptyState]="strategyEmpty"
            [pagination]="strategyPage.pageSpec()"
            (pageChange)="strategyPage.setPage($event)"
          />
```

Import `createClientPage` from `'../../ui/data-table/client-page'`.

- [ ] **Step 2: Build**

Run: `cd frontend && npx ng build`
Expected: `Application bundle generation complete.`

(No new unit test — `createClientPage` is already tested in Task 5;
component wiring is exercised by the existing `versions.spec.ts`-style
overflow test pattern IF one is added for this workspace, which is out of
scope here per the spec's existing precedent that Dashboard/Analytics don't
carry their own component spec files, relying on store specs instead.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): paginate the Strategy registry table"
```

## Task 13: Paginate confidence + breakdown tables (Performance tab)

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`

**Interfaces:**
- Consumes: `createClientPage`.
- Produces: nothing for later tasks.

- [ ] **Step 1: Wire up both tables**

```ts
  protected readonly confidencePage = createClientPage(() => this.store.byConfidence());
  protected readonly breakdownPage = createClientPage(() => this.store.breakdownRows());
```

Bind exactly as Task 12 did, on both `<sb-data-table>` usages (By confidence
level, By {dimension}) — `[rows]="confidencePage.visible()"` /
`[pagination]="confidencePage.pageSpec()"` / `(pageChange)="confidencePage.setPage($event)"`,
same pattern for `breakdownPage`.

**One nuance for breakdown:** changing the `Group by` dimension via
`onBreakdown()` must reset the page back to 1 — otherwise switching from a
50-row dimension to a 5-row one while on page 3 shows an empty table. In
`onBreakdown()`:

```ts
  protected onBreakdown(dimension: BreakdownDimension): void {
    this.store.setBreakdown(dimension);
    this.breakdownPage.setPage(1);
  }
```

(confirm `onBreakdown`'s current body via
`grep -n "onBreakdown" frontend/src/app/workspaces/analytics/analytics.ts`
and add the reset line to it rather than replacing the whole method if it
already does more than call `store.setBreakdown`.)

- [ ] **Step 2: Build**

Run: `cd frontend && npx ng build`
Expected: `Application bundle generation complete.`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): paginate confidence and breakdown tables

Breakdown resets to page 1 on a dimension change -- otherwise switching to
a smaller dimension while on a later page shows an empty table that reads
as 'no data' rather than 'wrong page'."
```

## Task 14: Paginate deciles + tiers + drift tables (Calibration tab)

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`

**Interfaces:**
- Consumes: `createClientPage`.
- Produces: nothing for later tasks.

- [ ] **Step 1: Wire up all three**

```ts
  protected readonly decilePage = createClientPage(() => this.store.deciles());
  protected readonly tierPage = createClientPage(() => this.store.tiers());
  protected readonly driftPage = createClientPage(() => this.store.drift());
```

Same binding pattern as Task 12 on each of the three `<sb-data-table>`s in
`@case ('calibration')`.

- [ ] **Step 2: Build**

Run: `cd frontend && npx ng build`
Expected: `Application bundle generation complete.`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): paginate deciles, tiers and drift tables"
```

---

# Phase 5 — Plans tab: backend

## Parallelisation

**Sequential within the phase** (Task 16 consumes Task 15's function). No
dependency on Phases 1-4 or Phase 6 — pure Python, can run fully in parallel
with all frontend work above once someone is free.

## Task 15: Plan-lifecycle aggregation

**Files:**
- Modify: `swingbot/admin/queries.py`
- Test: `tests/admin/test_queries_plan_lifecycle.py` (create)

**Interfaces:**
- Consumes: `PlanStore().all()`, `PlanStatus` from
  `swingbot.core.planning.plan_engine` (already imported in `queries.py`).
- Produces: `_plan_lifecycle() -> dict` with keys `funnel`, `fill_rate`,
  `badges`, `tiers` (exact shape in Step 3). Task 16 serializes this
  verbatim into the new endpoint's response.

- [ ] **Step 1: Write the failing tests**

```python
from types import SimpleNamespace

from swingbot.admin.queries import _plan_lifecycle
from swingbot.core.planning.plan_engine import PlanStatus


def _plan(status, history, created_at="2026-01-01", tier="B", badge="VALIDATED"):
    return SimpleNamespace(
        status=status, status_history=history, created_at=created_at,
        tier=tier, badge=badge,
    )


def test_funnel_counts_by_furthest_stage_ever_reached():
    plans = [
        _plan(PlanStatus.CANCELLED, [{"status": "CANCELLED", "at": "2026-01-02"}]),
        _plan(PlanStatus.ACTIVE, [{"status": "ACTIVE", "at": "2026-01-02"}]),
        _plan(PlanStatus.PARTIAL, [
            {"status": "ACTIVE", "at": "2026-01-02"},
            {"status": "PARTIAL", "at": "2026-01-05"},
        ]),
        _plan(PlanStatus.CLOSED, [
            {"status": "ACTIVE", "at": "2026-01-02"},
            {"status": "PARTIAL", "at": "2026-01-05"},
            {"status": "CLOSED", "at": "2026-01-09"},
        ]),
        # Closed WITHOUT ever hitting PARTIAL -- stopped out directly.
        _plan(PlanStatus.CLOSED, [
            {"status": "ACTIVE", "at": "2026-01-02"},
            {"status": "CLOSED", "at": "2026-01-04"},
        ]),
    ]
    result = _plan_lifecycle(plans)
    assert result["funnel"] == {
        "posted": 5, "filled": 4, "hit_tp1": 2, "closed": 2,
    }


def test_funnel_a_still_pending_plan_is_in_flight_not_a_failure():
    plans = [_plan(PlanStatus.PENDING, [])]
    result = _plan_lifecycle(plans)
    assert result["funnel"]["posted"] == 1
    assert result["funnel"]["filled"] == 0
    assert result["in_flight"] == 1


def test_fill_rate_scoped_to_resolved_plans_only():
    plans = [
        _plan(PlanStatus.CANCELLED, [{"status": "CANCELLED", "at": "2026-01-03"}],
              created_at="2026-01-01"),
        _plan(PlanStatus.CLOSED, [
            {"status": "ACTIVE", "at": "2026-01-05"},
            {"status": "CLOSED", "at": "2026-01-10"},
        ], created_at="2026-01-01"),
        # Still open -- must NOT count toward fill_rate either way.
        _plan(PlanStatus.PENDING, [], created_at="2026-01-01"),
    ]
    result = _plan_lifecycle(plans)
    assert result["fill_rate"]["resolved_n"] == 2
    assert result["fill_rate"]["fill_rate_pct"] == 50.0
    # Jan 1 -> Jan 5 = 4 days, the only filled resolved plan.
    assert result["fill_rate"]["median_days_to_fill"] == 4.0


def test_fill_rate_null_with_no_resolved_plans():
    plans = [_plan(PlanStatus.PENDING, [])]
    result = _plan_lifecycle(plans)
    assert result["fill_rate"]["resolved_n"] == 0
    assert result["fill_rate"]["fill_rate_pct"] is None
    assert result["fill_rate"]["median_days_to_fill"] is None


def test_badge_and_tier_counts():
    plans = [
        _plan(PlanStatus.PENDING, [], badge="VALIDATED", tier="A"),
        _plan(PlanStatus.PENDING, [], badge="VALIDATED", tier="B"),
        _plan(PlanStatus.PENDING, [], badge="WEAK", tier="C"),
    ]
    result = _plan_lifecycle(plans)
    assert result["badges"] == {"VALIDATED": 2, "WEAK": 1}
    assert result["tiers"] == {"A": 1, "B": 1, "C": 1}


def test_empty_plan_list_returns_well_formed_zeros():
    result = _plan_lifecycle([])
    assert result["funnel"] == {"posted": 0, "filled": 0, "hit_tp1": 0, "closed": 0}
    assert result["in_flight"] == 0
    assert result["fill_rate"] == {"resolved_n": 0, "fill_rate_pct": None, "median_days_to_fill": None}
    assert result["badges"] == {}
    assert result["tiers"] == {}
```

- [ ] **Step 2: Run to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_queries_plan_lifecycle.py`
Expected: FAIL — `ImportError: cannot import name '_plan_lifecycle'`

- [ ] **Step 3: Implement**

Add `from datetime import datetime` and `from statistics import median` to
`queries.py`'s existing top-of-file import block (alongside `import json`,
`import os`, `import re`) — this file keeps every import there, unlike
`api_v1/analytics.py`'s function-local style; match the file being edited,
not the one that happened to be read most recently.

Add to `swingbot/admin/queries.py`, near `_plan_rows`:

```python
def _reached(plan, status: str) -> bool:
    """Whether `plan` ever transitioned INTO `status`, at any point in its
    history -- not whether it is currently there. The state machine
    (_LEGAL_TRANSITIONS) is monotonic with no backward transition, so a
    plan currently CLOSED may or may not have passed through PARTIAL on the
    way, and only the history says which."""
    return any(h.get("status") == status for h in (plan.status_history or []))


def _days_between(start: str, end: str) -> float:
    """Whole days, swing-trade granularity -- created_at is documented as
    an 'ISO date of the bar/scan', not a precise timestamp, so resolving
    below day granularity would imply precision neither field actually
    carries."""
    return (datetime.fromisoformat(end[:10]) - datetime.fromisoformat(start[:10])).days


def _plan_lifecycle(plans: list) -> dict:
    """Funnel, fill-rate/time-to-fill, and badge/tier distribution over
    every plan ever posted -- the Plans tab's three panels. Walks
    `PlanStore().all()` the same way `_plan_rows` already does, rather than
    a second read path.

    Funnel counts are BY FURTHEST STAGE EVER REACHED (`_reached`), not by
    current status: a plan currently CLOSED may have stopped out directly
    from ACTIVE without ever hitting PARTIAL, so "hit_tp1" cannot be read
    off current status alone.

    fill_rate is scoped to RESOLVED plans (CLOSED or CANCELLED) only --
    a still-PENDING plan hasn't finished its journey yet, and folding it in
    would bias the rate toward "undecided" rather than measure a real
    outcome.
    """
    posted = len(plans)
    filled = sum(1 for p in plans if _reached(p, PlanStatus.ACTIVE))
    hit_tp1 = sum(1 for p in plans if _reached(p, PlanStatus.PARTIAL))
    closed = sum(1 for p in plans if p.status == PlanStatus.CLOSED)
    in_flight = sum(
        1 for p in plans
        if p.status in (PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL)
    )

    resolved = [p for p in plans if p.status in (PlanStatus.CLOSED, PlanStatus.CANCELLED)]
    filled_resolved = [p for p in resolved if _reached(p, PlanStatus.ACTIVE)]
    fill_days = []
    for p in filled_resolved:
        active_entry = next(h for h in p.status_history if h["status"] == PlanStatus.ACTIVE)
        fill_days.append(_days_between(p.created_at, active_entry["at"]))

    badges: dict[str, int] = {}
    tiers: dict[str, int] = {}
    for p in plans:
        badges[p.badge] = badges.get(p.badge, 0) + 1
        tiers[p.tier] = tiers.get(p.tier, 0) + 1

    return {
        "funnel": {"posted": posted, "filled": filled, "hit_tp1": hit_tp1, "closed": closed},
        "in_flight": in_flight,
        "fill_rate": {
            "resolved_n": len(resolved),
            "fill_rate_pct": (
                round(len(filled_resolved) / len(resolved) * 100, 1) if resolved else None
            ),
            "median_days_to_fill": median(fill_days) if fill_days else None,
        },
        "badges": badges,
        "tiers": tiers,
    }
```

- [ ] **Step 4: Run to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_queries_plan_lifecycle.py`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/queries.py tests/admin/test_queries_plan_lifecycle.py
git commit -m "feat(analytics): plan-lifecycle aggregation -- funnel, fill rate, badges/tiers

Funnel counts are by furthest stage EVER reached (scans status_history),
not current status -- a CLOSED plan may have stopped out directly from
ACTIVE without ever hitting PARTIAL, and current status alone can't tell
those two paths apart. fill_rate excludes in-flight plans: a still-PENDING
plan hasn't resolved yet, and counting it would bias the rate toward
undecided rather than measure a real outcome."
```

## Task 16: `GET /analytics/plans` endpoint

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py`
- Test: `tests/admin/test_api_v1_analytics.py` (check whether this file
  exists first — `find tests/admin -iname "*analytics*"` — create it
  following this repo's usual `_LOGIN`/`logged_in` fixture pattern, matching
  `tests/admin/test_api_v1_versions.py`'s structure, if it does not)

**Interfaces:**
- Consumes: `_plan_lifecycle` from Task 15, `PlanStore` from
  `swingbot.core.planning.plan_store`.
- Produces: `GET /api/v1/analytics/plans` → `{funnel, in_flight, fill_rate,
  badges, tiers}`, verbatim from `_plan_lifecycle`.

- [ ] **Step 1: Write the failing test**

This file's own routes import per-function, not at module scope — every
route but the one carrying `TradeLog` does this (`analytics_registry`'s
`from swingbot.admin.queries import _registry_rows`, inside the function,
is the closest precedent). The new route matches that, so the test patches
`PlanStore` at its TRUE origin (`swingbot.core.planning.plan_store`)
rather than on `api_v1.analytics`'s own namespace — patching the origin
module's attribute works whether the importing route resolves it lazily or
at module scope, so this is also the more robust target regardless of
which style Step 3 ends up using:

```python
def test_plans_endpoint_serves_the_lifecycle_aggregation(logged_in, monkeypatch):
    import swingbot.core.planning.plan_store as plan_store_mod

    class FakeStore:
        def all(self):
            return []

    monkeypatch.setattr(plan_store_mod, "PlanStore", FakeStore)
    body = logged_in.get("/api/v1/analytics/plans").get_json()
    assert body["funnel"] == {"posted": 0, "filled": 0, "hit_tp1": 0, "closed": 0}
    assert body["in_flight"] == 0
    assert "fill_rate" in body
    assert "badges" in body
    assert "tiers" in body


def test_plans_requires_auth(client):
    assert client.get("/api/v1/analytics/plans").status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: FAIL — 404, route doesn't exist

- [ ] **Step 3: Add the route**

Append to `swingbot/admin/api_v1/analytics.py`:

```python
@api_v1.route("/analytics/plans", methods=["GET"])
@require_auth
def analytics_plans():
    """Lifecycle funnel, fill rate/time-to-fill, and badge/tier distribution
    over every plan ever posted -- the Plans tab. 'UI renders, analytics
    computes': the actual walk is `_plan_lifecycle`, this route only calls
    and forwards it, same as every other route in this module.
    """
    from swingbot.admin.queries import _plan_lifecycle
    from swingbot.core.planning.plan_store import PlanStore

    return jsonify(_plan_lifecycle(PlanStore().all()))
```

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(analytics): GET /analytics/plans -- the Plans tab's endpoint

Assembles and forwards _plan_lifecycle verbatim, matching this module's own
'UI renders, analytics computes' rule -- nothing computed inline in the route."
```

---

# Phase 6 — Plans tab: frontend

## Parallelisation

**Sequential within the phase.** Depends on Phase 5 (Task 16's endpoint)
and, for the chart panels, Phase 1 (`sb-line-chart`/`Histogram`). No
dependency on Phases 2-4.

## Task 17: Store + API client + models for the Plans tab

**Files:**
- Modify: `frontend/src/app/api/models.ts`
- Modify: `frontend/src/app/api/api-client.ts`
- Modify: `frontend/src/app/stores/analytics.store.ts`
- Test: `frontend/src/app/stores/analytics.store.spec.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `AnalyticsPlans` model type, `ApiClient.analyticsPlans()`,
  `AnalyticsTab` widened to include `'plans'`, `store.plans`,
  `store.funnelChart()`, `store.fillRatePct()`, `store.medianDaysToFill()`,
  `store.badgeChart()`, `store.tierChart()`. Task 18 renders all of these.

- [ ] **Step 1: Write the failing test**

```ts
it('fetches /analytics/plans when the plans tab opens', () => {
  store.setTab('plans');
  tick();
  backend.expectOne('/api/v1/analytics/plans').flush({
    funnel: { posted: 10, filled: 8, hit_tp1: 5, closed: 4 },
    in_flight: 3,
    fill_rate: { resolved_n: 7, fill_rate_pct: 71.4, median_days_to_fill: 2.5 },
    badges: { VALIDATED: 7, WEAK: 3 },
    tiers: { A: 4, B: 3, C: 3 },
  });
  expect(store.funnelChart()).toEqual([
    { label: 'Posted', count: 10 }, { label: 'Filled', count: 8 },
    { label: 'Hit TP1', count: 5 }, { label: 'Closed', count: 4 },
  ]);
  expect(store.fillRatePct()).toBe(71.4);
  expect(store.medianDaysToFill()).toBe(2.5);
  expect(store.badgeChart()).toEqual([
    { label: 'VALIDATED', count: 7 }, { label: 'WEAK', count: 3 },
  ]);
  expect(store.tierChart()).toEqual([
    { label: 'A', count: 4 }, { label: 'B', count: 3 }, { label: 'C', count: 3 },
  ]);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx ng test`
Expected: FAIL — `store.setTab('plans')` rejects an unknown tab / `funnelChart` undefined

- [ ] **Step 3: Add the model type**

In `frontend/src/app/api/models.ts`, near `AnalyticsCalibration`:

```ts
export interface AnalyticsPlans {
  funnel: { posted: number; filled: number; hit_tp1: number; closed: number };
  in_flight: number;
  fill_rate: {
    resolved_n: number;
    fill_rate_pct: number | null;
    median_days_to_fill: number | null;
  };
  badges: Record<string, number>;
  tiers: Record<string, number>;
}
```

- [ ] **Step 4: Add the API client method**

In `frontend/src/app/api/api-client.ts`, near `analyticsCalibration`:

```ts
  analyticsPlans(): Observable<AnalyticsPlans> {
    return this.http.get<AnalyticsPlans>(`${this.base}/analytics/plans`);
  }
```

Add `AnalyticsPlans` to this file's import from `./models`.

- [ ] **Step 5: Widen `AnalyticsTab`, add state, add `loadPlans`**

In `analytics.store.ts`:

```ts
export type AnalyticsTab = 'performance' | 'strategies' | 'calibration' | 'tuning' | 'plans';

export const ANALYTICS_TABS: readonly AnalyticsTab[] = [
  'performance', 'strategies', 'calibration', 'tuning', 'plans',
] as const;
```

Add `plans: AnalyticsPlans | null;` to `AnalyticsSlice`, `plans: null,` to
the `withState` initial value, and `AnalyticsPlans` to the `models` import.

In the `withMethods` block, alongside `loadCalibration`:

```ts
    const loadPlans = (): void => {
      patchState(store, { loading: true });
      api.analyticsPlans().subscribe({
        next: (plans) => patchState(store, { plans, loading: false, error: null }),
        error: fail,
      });
    };
```

Add `case 'plans': return loadPlans();` to the `load()` switch.

Add `setTab` if it doesn't already exist as a public method — check
`grep -n "setTab" frontend/src/app/stores/analytics.store.ts`; the
component's `goToTab()` likely calls `patchState(store, {tab})` directly
rather than through a store method, in which case this test's
`store.setTab('plans')` call should instead read
`patchState-equivalent`: use whatever the existing tests in this file
already use to change tabs (grep `store.tab` usage in
`analytics.store.spec.ts` for the established pattern and match it exactly
rather than inventing a `setTab` method this store doesn't have).

- [ ] **Step 6: Add the chart-shaping computeds**

In `withComputed`, destructuring `plans` alongside the others:

```ts
    funnelChart: computed<HistogramBin[]>(() => {
      const f = plans()?.funnel;
      if (!f) return [];
      return [
        { label: 'Posted', count: f.posted },
        { label: 'Filled', count: f.filled },
        { label: 'Hit TP1', count: f.hit_tp1 },
        { label: 'Closed', count: f.closed },
      ];
    }),
    fillRatePct: computed(() => plans()?.fill_rate.fill_rate_pct ?? null),
    medianDaysToFill: computed(() => plans()?.fill_rate.median_days_to_fill ?? null),
    inFlight: computed(() => plans()?.in_flight ?? 0),
    badgeChart: computed<HistogramBin[]>(() =>
      Object.entries(plans()?.badges ?? {}).map(([label, count]) => ({ label, count }))),
    tierChart: computed<HistogramBin[]>(() =>
      Object.entries(plans()?.tiers ?? {})
        .sort(([a], [b]) => a.localeCompare(b)) // A, B, C
        .map(([label, count]) => ({ label, count }))),
```

- [ ] **Step 7: Run to verify it passes**

Run: `cd frontend && npx ng test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts
git commit -m "feat(analytics): Plans tab data -- store, API client, models"
```

## Task 18: Plans tab — render

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`

**Interfaces:**
- Consumes: everything Task 17 produces, `Histogram`, `MetricChip` (already
  imported).
- Produces: the rendered fifth tab.

- [ ] **Step 1: Add the tab entry**

In the component-local `TABS` array:

```ts
const TABS: Tab[] = [
  { id: 'performance', label: 'Performance' },
  { id: 'strategies', label: 'Strategies' },
  { id: 'calibration', label: 'Calibration' },
  { id: 'tuning', label: 'Tuning' },
  { id: 'plans', label: 'Plans' },
];
```

- [ ] **Step 2: Add the `@case`**

In the `@switch (activeTab())`, after `@case ('tuning')`:

```html
      @case ('plans') {
        <p class="section-help">
          Every plan ever posted, and how far it got: PENDING (posted,
          waiting for its entry trigger) &rarr; ACTIVE (filled) &rarr;
          PARTIAL (TP1 hit) &rarr; CLOSED, or CANCELLED at any point before
          filling. Fill rate and time-to-fill are measured over RESOLVED
          plans only (CLOSED or CANCELLED) &mdash; a plan still waiting
          hasn't finished its journey yet, and counting it would bias the
          rate toward "undecided".
        </p>

        <sb-panel heading="Lifecycle funnel">
          @if (store.funnelChart().length) {
            <sb-histogram [bins]="store.funnelChart()" />
            <p class="series-note">{{ store.inFlight() }} currently in flight (not counted above).</p>
          } @else {
            <p class="stale">No plans posted yet.</p>
          }
        </sb-panel>

        <div class="panels">
          <sb-panel heading="Fill rate">
            <div class="chips">
              <sb-metric-chip label="Filled" [value]="store.fillRatePct()" unit="%" [decimals]="1" />
              <sb-metric-chip label="Median days to fill" [value]="store.medianDaysToFill()" [decimals]="1" />
            </div>
          </sb-panel>

          <sb-panel heading="Badge distribution">
            @if (store.badgeChart().length) {
              <sb-histogram [bins]="store.badgeChart()" [isNegative]="isWeakBadge" />
            } @else {
              <p class="stale">No plans posted yet.</p>
            }
          </sb-panel>
        </div>

        <sb-panel heading="Tier distribution">
          @if (store.tierChart().length) {
            <sb-histogram [bins]="store.tierChart()" />
          } @else {
            <p class="stale">No plans posted yet.</p>
          }
        </sb-panel>
      }
```

Add to the component class:

```ts
  /** WEAK reads as the "loss" side of this bar list -- greyscale would be
   *  equally defensible (a badge is a quality judgement, not P&L), but
   *  VALIDATED-vs-WEAK is structurally the same "good/bad split" the
   *  green/red pair exists for elsewhere on this workspace's strategy
   *  badges (see #badgeCell's own note on why THAT one stays greyscale --
   *  the difference is this chart has no chip carrying the badge word
   *  beside it, so colour is the only signal available here). */
  protected readonly isWeakBadge = (bin: HistogramBin): boolean => bin.label === 'WEAK';
```

Import `HistogramBin` from `'../../ui/histogram'` if not already imported.

- [ ] **Step 3: Build and run the frontend suite**

Run: `cd frontend && npx ng build && npx ng test`
Expected: bundle complete; all tests pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): render the Plans tab -- funnel, fill rate, badge/tier charts"
```

---

# Phase 7 — Tuning tab

## Parallelisation

**Sequential within the phase.** Depends only on Task 5 (`createClientPage`).
No dependency on Phases 2-6.

## Task 19: Convert tuning grid results to `sb-data-table`

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.columns.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`

**Interfaces:**
- Consumes: `GridRow` (existing, from `analytics.store.ts`),
  `createClientPage`.
- Produces: `GRID_COLUMNS: ColumnDef<GridRow>[]` — used only here.

- [ ] **Step 1: Add the column definitions**

In `analytics.columns.ts`, matching `STRATEGY_COLUMNS`'s real shape exactly
(`key`/`header`/`numeric`/`value`, NOT `label`/`align`/`sortable` — verified
directly against the file: `{ key: 'strategy', header: 'Strategy' }`,
`{ key: 'win_rate', header: 'OOS WR', numeric: true, value: (r) => rate(r.win_rate) }`).
A column with no `value` gets a `cell: TemplateRef` attached by key in the
component instead, same as `strategy`/`rolling`/`status` are here:

```ts
export const GRID_COLUMNS: ColumnDef<GridRow>[] = [
  { key: 'paramLabel', header: 'Parameters', value: (r) => r.paramLabel },
  { key: 'n_eval', header: 'N', numeric: true, value: (r) => count(r.n_eval) },
  { key: 'win_rate', header: 'Win rate', numeric: true, value: (r) => rate(r.win_rate) },
  { key: 'expectancy_r', header: 'ExpR', numeric: true, value: (r) => expectancy(r.expectancy_r) },
  { key: 'excluded_share', header: 'Excluded', numeric: true,
    value: (r) => `${(r.excluded_share * 100).toFixed(0)}%` },
  { key: 'passes', header: 'Bar' },     // cell slot, filled in analytics.ts
  { key: 'propose', header: '' },       // cell slot, filled in analytics.ts
];
```

`count`, `rate`, `expectancy` are already exported from this file — reuse
them rather than reformatting inline.

- [ ] **Step 2: Replace the hand-rolled `<table class="grid">`**

Add to the `Analytics` component, mirroring `protected readonly columns`
in `frontend/src/app/workspaces/dashboard/dashboard.ts` — the existing
"attach a TemplateRef to a shared ColumnDef list by key" pattern:

```ts
  protected readonly gridPage = createClientPage(() => this.store.grid());
  protected readonly gridRowKey = (row: GridRow) => String(row.row_index);
  protected readonly gridKeys = allKeys(GRID_COLUMNS);

  private readonly gridPassesCell = viewChild.required<TemplateRef<RowContext<GridRow>>>('gridPassesCell');
  private readonly gridProposeCell = viewChild.required<TemplateRef<RowContext<GridRow>>>('gridProposeCell');

  protected readonly gridColumns = computed<ColumnDef<GridRow>[]>(() => {
    const cells: Record<string, TemplateRef<RowContext<GridRow>>> = {
      passes: this.gridPassesCell(),
      propose: this.gridProposeCell(),
    };
    return GRID_COLUMNS.map((column) =>
      cells[column.key] ? { ...column, cell: cells[column.key] } : column);
  });
```

Add `ng-template`s for the two cell slots (near the file's other `#xCell`
templates):

```html
    <ng-template #gridPassesCell let-row>
      @if (row.passes) { <sb-chip label="Clears" tone="q5" /> }
    </ng-template>
    <ng-template #gridProposeCell let-row>
      <button sb-button variant="secondary" type="button"
              [loading]="store.proposing() === row.row_index"
              (click)="askPropose(row)">
        Propose
      </button>
    </ng-template>
```

Replace the `@if (store.grid().length) { <sb-panel ...><table class="grid">...`
block's inner table with:

```html
            <sb-data-table
              [rows]="gridPage.visible()"
              [columns]="gridColumns()"
              [visible]="gridKeys"
              [rowKey]="gridRowKey"
              [pagination]="gridPage.pageSpec()"
              (pageChange)="gridPage.setPage($event)"
            />
```

Import `allKeys` from `./analytics.columns` if not already imported (it is
— `strategyKeys`/`confidenceKeys`/etc. already use it), and `GRID_COLUMNS`
alongside the file's other column-list imports.

- [ ] **Step 3: Build and run the frontend suite**

Run: `cd frontend && npx ng build && npx ng test`
Expected: bundle complete; all tests pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.columns.ts frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): tuning grid results become sb-data-table -- pagination and phone cards in one move"
```

## Task 20: Convert past jobs to `sb-data-table`

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.columns.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`

**Interfaces:**
- Consumes: `JobSummary` (`{id, kind, state, started_at, finished_at,
  returncode}`, `analytics.store.ts`).
- Produces: `PAST_JOBS_COLUMNS: ColumnDef<JobSummary>[]` — used only here.

- [ ] **Step 1: Add columns**

`ColumnDef`'s real shape (Task 19 confirmed it against `STRATEGY_COLUMNS`):
`key`/`header`/`numeric`/`value`, not `label`/`align`:

```ts
export const PAST_JOBS_COLUMNS: ColumnDef<JobSummary>[] = [
  { key: 'id', header: 'Job', value: (r) => r.id },
  { key: 'state', header: 'State', value: (r) => r.state },
  { key: 'started_at', header: 'Started', value: (r) => date(r.started_at) },
];
```

`date` is already imported in this file (used by `STRATEGY_COLUMNS`'s
`run_date` column).

- [ ] **Step 2: Replace the hand-rolled `<ul class="jobs">`**

```ts
  protected readonly pastJobsPage = createClientPage(() => this.store.pastJobs());
  protected readonly pastJobRowKey = (row: JobSummary) => row.id;
  protected readonly pastJobsKeys = allKeys(PAST_JOBS_COLUMNS);
  protected readonly pastJobsColumns = PAST_JOBS_COLUMNS; // static, no cell slots needed
```

```html
        @if (store.pastJobs(); as past) {
          @if (past.length) {
            <sb-panel heading="Earlier jobs" [flush]="true">
              <sb-data-table
                [rows]="pastJobsPage.visible()"
                [columns]="pastJobsColumns"
                [visible]="pastJobsKeys"
                [rowKey]="pastJobRowKey"
                [pagination]="pastJobsPage.pageSpec()"
                (pageChange)="pastJobsPage.setPage($event)"
              />
            </sb-panel>
          }
        }
```

Import `JobSummary` and `PAST_JOBS_COLUMNS` alongside this file's other
Analytics-tab imports.

- [ ] **Step 3: Build and run the frontend suite**

Run: `cd frontend && npx ng build && npx ng test`
Expected: bundle complete; all tests pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.columns.ts frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): past jobs become sb-data-table -- pagination and phone cards"
```

## Task 21: Paginate the proposals list

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`

**Interfaces:**
- Consumes: `createClientPage`, `proposalViews()` (existing computed).
- Produces: nothing for later tasks.

- [ ] **Step 1: Wire it up**

Each proposal is a card with its own nested diff table, not flat row data —
`sb-data-table` doesn't fit, so this gets a small dedicated pager rather
than the shared component:

```ts
  protected readonly proposalsPage = createClientPage(() => this.proposalViews(), 8);
```

In the template, `@for (proposal of proposals; track proposal.filename)`
becomes `@for (proposal of proposalsPage.visible(); track proposal.filename)`,
reading from `proposalsPage.visible()` in place of the current
`proposalViews(); as proposals` binding. After the closing `}` of that
`@for`, add:

```html
          <sb-pagination [pagination]="proposalsPage.pageSpec()" (pageChange)="proposalsPage.setPage($event)" />
```

(`sb-pagination` — the standalone component `PaginationComponent` used
directly rather than through `sb-data-table`; confirm its import path via
`grep -n "class PaginationComponent" frontend/src/app/ui/pagination.ts` and
add it to this component's `imports` array — it was used exactly this way,
standalone, in the Versions workspace's own pagination, see
`frontend/src/app/workspaces/versions/versions.ts`.)

- [ ] **Step 2: Build**

Run: `cd frontend && npx ng build`
Expected: `Application bundle generation complete.`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "feat(analytics): paginate the proposals list

Each proposal is a card with its own nested diff table, not flat row data,
so it gets its own small pager (8 per page) rather than sb-data-table."
```

---

# Phase 8 — Close

## Parallelisation

**Sequential.** The gate is last.

## Task 22: Full gate + responsive/phone verification

**Files:** none modified — verification only.

- [ ] **Step 1: Confirm nothing still references removed symbols**

Run: `grep -n "fmtCumulative\|class=\"grid\"\|class=\"jobs\"" frontend/src/app/workspaces/analytics/analytics.ts`
Expected: no output (all three were removed in Tasks 10, 19, 20)

- [ ] **Step 2: Run both suites**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`

Run: `cd frontend && npx ng test`
Expected: all files pass

- [ ] **Step 3: Screenshot every tab at a phone width**

Use `chrome-devtools-mcp` (or the equivalent available browser tool):
`resize_page` to 380x900, navigate to `/analytics` with each of
`?tab=performance`, `?tab=strategies`, `?tab=calibration`, `?tab=tuning`,
`?tab=plans`, and `take_screenshot fullPage:true` on each. Confirm by eye:
no horizontal overflow on any tab, the three converted tables (tuning grid,
past jobs — Tasks 19-20) render as cards not a squeezed table, the Strategy
registry/breakdown/confidence/deciles/tiers/drift tables (already on
`sb-data-table`) do the same, and the heatmap's horizontal scroll (left
as-is per the spec) is the only place that scrolls sideways.

- [ ] **Step 4: Verify the two original bugs, by eye**

On the Strategies tab: "Strategy registry" heading and "out-of-sample
validation status per strategy" subtitle share a left edge. On the
Performance tab: the two R-multiple panels read "(selected range)" and
"(all-time)".

## Task 23: Version bump, regenerate, close the plan

**Files:**
- Modify: `VERSION.json`
- Modify: `swingbot/admin/version_history.json` (regenerated)
- Modify: `docs/superpowers/specs/2026-08-16-v30-analytics-redesign-design.md` (move)
- Modify: `docs/superpowers/plans/2026-08-16-v30-analytics-redesign.md` (move)

- [ ] **Step 1: Bump `ui`**

Edit `VERSION.json`: bump `ui` to the next minor (check the current value
first — `cat VERSION.json` — this plan was written against `1.5.1`, so the
bump is to `1.6.0` unless something else has shipped in between; if so,
bump from whatever `ui` actually is at commit time, still a minor step, and
say why in the commit if it lands feeling smaller than a minor). Set
`ui_updated` to now (`YYYY-MM-DD HH-MM-SS`, UTC). Leave `bot`/`bot_updated`
alone.

```bash
git add VERSION.json
git commit -m "release(ui): 1.6.0 -- the Analytics redesign

Minor: a fifth tab appears, the Performance tab's layout changes shape, and
three data views that were text lists become charts. Someone who used
Analytics yesterday has to look at it anew."
```

- [ ] **Step 2: Regenerate — AFTER the bump commit, never before**

```bash
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(versions): regenerate version_history.json for 1.6.0"
```

- [ ] **Step 3: Move the spec and plan to `implemented/`**

```bash
git mv docs/superpowers/specs/2026-08-16-v30-analytics-redesign-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-08-16-v30-analytics-redesign.md docs/superpowers/plans/implemented/
git commit -m "docs: v30 close, so it leaves the live list"
```

- [ ] **Step 4: Push**

```bash
git fetch origin && git rev-list --left-right --count main...origin/main
git push origin main
```
