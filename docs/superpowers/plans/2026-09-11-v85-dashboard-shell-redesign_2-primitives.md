# v85 Part 2 — The shared primitives

Header block, global constraints, waves, parallelisation and exit criteria live
in `2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

**R2-01 … R2-06 are Group P**: six new files, no shared file, safe to run in
parallel after R1-03. **R2-07 runs after them, alone.**

These six exist so that nine workspaces cannot drift apart. Every one of them
is a rule from the spec made unavoidable: a metric that cannot be rendered
without its sample size, a panel that cannot be rendered without its
timestamp, one control bar instead of nine. Building them first is what makes
the workspace parts short.

---

## Conventions every task here follows

Read these once; they are not repeated per task.

- Standalone component, `ChangeDetectionStrategy.OnPush`, signal `input()`s —
  match `frontend/src/app/ui/chip.ts`.
- Selector prefix `sb-`, file named after the component, spec beside it.
- Colour only from `tokens.css`. `ui/primitives.spec.ts` fails the build on a
  hex literal in a component.
- Spec file shape: `provideZonelessChangeDetection()` in `beforeEach`, render
  through `TestBed.createComponent` + `componentRef.setInput`, assert on the
  rendered DOM — match `frontend/src/app/ui/chip.spec.ts`.
- Run one spec with `cd frontend && npx ng test --include <path>` (~55s).

---

# Phase 1 — The primitives

### Task R2-01: `sb-stat-tile` — a metric that carries its own sample size

**Files:**
- Create: `frontend/src/app/ui/stat-tile.ts`
- Create: `frontend/src/app/ui/stat-tile.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `StatTile` component (selector `sb-stat-tile`), inputs `label`
  (string), `value` (string | null), `sample` (number | null), `tone`
  (`'neutral' | 'pos' | 'neg'`), `hint` (string | undefined); and the exported
  constant `MIN_SAMPLE_N = 30`. Consumed by R4-02, R8-04, R9-03, R10-04.

**Why this is a component and not a CSS class.** Spec D23: every derived metric
renders with its N adjacent, and anything below the minimum renders
de-emphasised with how many more trades it needs. Written as a convention, that
rule survives until the third page that forgets it. Written as the only way to
render a metric, it cannot be forgotten.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/stat-tile.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { MIN_SAMPLE_N, StatTile } from './stat-tile';

function render(inputs: Record<string, unknown>): HTMLElement {
  const f = TestBed.createComponent(StatTile);
  f.componentRef.setInput('label', 'Win rate');
  f.componentRef.setInput('value', '68%');
  for (const [key, val] of Object.entries(inputs)) f.componentRef.setInput(key, val);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.tile')!;
}

describe('StatTile (v85 D23)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders the label and the value', () => {
    const el = render({});
    expect(el.querySelector('.label')!.textContent).toContain('Win rate');
    expect(el.querySelector('.value')!.textContent).toContain('68%');
  });

  it('renders a null value as no-value, never as zero', () => {
    const el = render({ value: null });
    expect(el.querySelector('.value')!.textContent!.trim()).toBe('—');
    expect(el.querySelector('.value')!.textContent).not.toContain('0');
  });

  it('renders the sample size adjacent to the value', () => {
    const el = render({ sample: 412 });
    expect(el.querySelector('.sample')!.textContent).toContain('N=412');
  });

  it('omits the sample line when no sample was supplied', () => {
    expect(render({}).querySelector('.sample')).toBeNull();
  });

  it('de-emphasises a figure below the minimum sample', () => {
    const el = render({ sample: 7 });
    expect(el.classList).toContain('thin');
  });

  it('says how many more trades a thin figure needs', () => {
    const el = render({ sample: 7 });
    expect(el.querySelector('.sample')!.getAttribute('title'))
      .toContain(`${MIN_SAMPLE_N - 7} more`);
  });

  it('does not de-emphasise a figure at the minimum', () => {
    expect(render({ sample: MIN_SAMPLE_N }).classList).not.toContain('thin');
  });

  it('marks a thin figure for assistive tech, not by colour alone', () => {
    const el = render({ sample: 7 });
    expect(el.querySelector('.sample')!.textContent).toContain('thin sample');
  });

  it('carries the tone as a class', () => {
    expect(render({ tone: 'neg' }).classList).toContain('neg');
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/ui/stat-tile.spec.ts
```

Expected: FAIL — `Failed to resolve import "./stat-tile"`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/ui/stat-tile.ts`:

```typescript
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * The smallest sample a derived metric may be read from without a warning.
 *
 * 30 is not a law of statistics; it is the point below which this book's
 * per-strategy and per-horizon slices have historically flipped sign on one
 * more trade. R11-04 makes it a setting — until then it is a constant, so the
 * primitive can ship in wave 1 ahead of the control that tunes it.
 */
export const MIN_SAMPLE_N = 30;

export type StatTone = 'neutral' | 'pos' | 'neg';

/**
 * One metric, its label, and its sample size — spec v85 D23.
 *
 * The sample size is not decoration and not a tooltip. A win rate of 68% over
 * seven trades and one over four hundred are different claims, and a tile that
 * renders them identically is the correctness bug this component exists to
 * prevent. Below `MIN_SAMPLE_N` the tile de-emphasises itself and says how many
 * more closed trades it needs — the figure is still shown, because hiding it
 * would stop you watching a young strategy develop.
 *
 * `value` is pre-formatted by the caller. This component never formats a
 * number: the pages that use it disagree about units (R, %, currency) and a
 * formatter here would have to learn all of them.
 */
@Component({
  selector: 'sb-stat-tile',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="tile" [class.thin]="thin()" [class]="tone()">
      <div class="label">{{ label() }}</div>
      <div class="value">{{ value() ?? '—' }}</div>
      @if (sample() !== null) {
        <div class="sample" [title]="sampleTitle()">
          N={{ sample() }}@if (thin()) {<span class="flag"> · thin sample</span>}
        </div>
      }
      @if (hint()) {
        <div class="hint">{{ hint() }}</div>
      }
    </div>
  `,
  styles: `
    .tile {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: var(--pad);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }
    .label {
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-faint);
    }
    .value {
      font-size: var(--text-metric);
      font-variant-numeric: tabular-nums;
      color: var(--text);
    }
    .pos .value { color: var(--pos); }
    .neg .value { color: var(--neg); }
    .sample,
    .hint {
      font-size: var(--text-micro);
      font-variant-numeric: tabular-nums;
      color: var(--text-faint);
    }
    /* The second cue. Opacity alone would be a colour-only signal, which the
       plan forbids; `.flag` puts the same fact in words. */
    .thin .value { opacity: 0.62; }
    .thin .flag { font-style: italic; }
  `,
})
export class StatTile {
  readonly label = input.required<string>();
  readonly value = input.required<string | null>();
  readonly sample = input<number | null>(null);
  readonly tone = input<StatTone>('neutral');
  readonly hint = input<string | undefined>(undefined);

  protected readonly thin = computed(() => {
    const n = this.sample();
    return n !== null && n < MIN_SAMPLE_N;
  });

  protected readonly sampleTitle = computed(() => {
    const n = this.sample();
    if (n === null) return '';
    if (n >= MIN_SAMPLE_N) return `${n} closed trades`;
    return `${n} closed trades — ${MIN_SAMPLE_N - n} more before this figure is worth reading`;
  });
}
```

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/ui/stat-tile.spec.ts
```

Expected: PASS, `Test Files 1 passed`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/stat-tile.ts frontend/src/app/ui/stat-tile.spec.ts
git commit -m "feat(ui): sb-stat-tile carries its own sample size (v85 D23)"
```

---

### Task R2-02: `sb-control-bar` — one place per-page controls live

**Files:**
- Create: `frontend/src/app/ui/control-bar.ts`
- Create: `frontend/src/app/ui/control-bar.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `ControlBar` component (selector `sb-control-bar`), inputs
  `activeCount` (number), `clearable` (boolean); output `cleared`; two content
  slots projected by attribute — `[filters]` and `[scope]`. Consumed by R4-07,
  R6-03, R7-05, R8-06, R9-04, R10-03.

**Why one component.** Spec D22: the mockups place per-page controls in a
different spot on every sheet. Nine independently placed clusters drift apart
the first time one is edited alone, and none of them survive 390px without
being solved nine times. One bar, one wrap rule, one accessible Clear.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/control-bar.spec.ts`:

```typescript
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ControlBar } from './control-bar';

@Component({
  standalone: true,
  imports: [ControlBar],
  template: `
    <sb-control-bar [activeCount]="count" (cleared)="cleared = true">
      <button filters id="chip">Open</button>
      <select scope id="range"><option>YTD</option></select>
    </sb-control-bar>
  `,
})
class Host {
  count = 0;
  cleared = false;
}

function host(count: number) {
  const f = TestBed.createComponent(Host);
  f.componentInstance.count = count;
  f.detectChanges();
  return f;
}

describe('ControlBar (v85 D22)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('projects filters into the leading slot', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.filters #chip')).not.toBeNull();
  });

  it('projects scope controls into the trailing slot', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.scope #range')).not.toBeNull();
  });

  it('hides Clear when nothing is filtered', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.clear')).toBeNull();
  });

  it('shows the active count when something is filtered', () => {
    const el = host(3).nativeElement as HTMLElement;
    expect(el.querySelector('.clear')!.textContent).toContain('3');
  });

  it('emits cleared when Clear is pressed', () => {
    const f = host(2);
    (f.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.clear')!.click();
    expect(f.componentInstance.cleared).toBe(true);
  });

  it('names itself for assistive tech', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.bar')!.getAttribute('aria-label')).toBe('Page controls');
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/ui/control-bar.spec.ts
```

Expected: FAIL — `Failed to resolve import "./control-bar"`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/ui/control-bar.ts`:

```typescript
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

/**
 * The one control bar — spec v85 D22.
 *
 * Filters and chips go in the `filters` slot, scope controls (range pickers,
 * unit selectors) in the `scope` slot. The bar owns the wrap behaviour and the
 * Clear affordance so that no page has to solve either, and so that the two
 * never disagree between pages.
 *
 * It does not own any state. `activeCount` is computed by the page from its own
 * query parameters — this component must not become a second copy of the truth
 * about what is filtered.
 */
@Component({
  selector: 'sb-control-bar',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bar" role="group" aria-label="Page controls">
      <div class="filters"><ng-content select="[filters]" /></div>
      <div class="scope">
        <ng-content select="[scope]" />
        @if (activeCount() > 0) {
          <button type="button" class="clear" (click)="cleared.emit()">
            Clear {{ activeCount() }}
          </button>
        }
      </div>
    </div>
  `,
  styles: `
    .bar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--gap);
      padding: var(--pad) 0;
    }
    .filters,
    .scope {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--gap);
      min-width: 0;
    }
    .clear {
      font-size: var(--text-micro);
      color: var(--accent);
      background: none;
      border: 0;
      cursor: pointer;
    }
    /* At phone width the two groups stack rather than compete for one row.
       Nothing is hidden — the plan forbids a control that vanishes silently. */
    @media (max-width: 640px) {
      .bar { flex-direction: column; align-items: stretch; }
      .scope { justify-content: flex-start; }
    }
  `,
})
export class ControlBar {
  readonly activeCount = input<number>(0);
  readonly cleared = output<void>();
}
```

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/ui/control-bar.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/control-bar.ts frontend/src/app/ui/control-bar.spec.ts
git commit -m "feat(ui): sb-control-bar, one per-page control surface (v85 D22)"
```

---

### Task R2-03: `sb-gauge` — a dial that tells the truth past 100%

**Files:**
- Create: `frontend/src/app/ui/gauge.ts`
- Create: `frontend/src/app/ui/gauge.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `Gauge` component (selector `sb-gauge`), inputs `value`
  (number | null), `max` (number, default 100), `label` (string), `caption`
  (string | undefined). Consumed by R8-05.

**The one behaviour that matters.** `GET /risk` returns `utilisation_pct`
deliberately **unclamped** — the API comment says so, because 130% of the heat
cap is exactly the situation the reader must see. A gauge that pins its needle
at full would throw that away. The needle clamps; the readout does not, and
past `max` the arc takes the over-limit treatment.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/gauge.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Gauge } from './gauge';

function render(inputs: Record<string, unknown>): HTMLElement {
  const f = TestBed.createComponent(Gauge);
  f.componentRef.setInput('label', 'Heat utilisation');
  f.componentRef.setInput('value', 62);
  for (const [key, val] of Object.entries(inputs)) f.componentRef.setInput(key, val);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.gauge')!;
}

describe('Gauge (v85 D36)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('prints the value', () => {
    expect(render({}).querySelector('.readout')!.textContent).toContain('62');
  });

  it('prints a null value as no-value', () => {
    expect(render({ value: null }).querySelector('.readout')!.textContent!.trim()).toBe('—');
  });

  it('prints the true figure past the maximum rather than clamping it', () => {
    expect(render({ value: 130 }).querySelector('.readout')!.textContent).toContain('130');
  });

  it('clamps only the needle', () => {
    const el = render({ value: 130 });
    const angle = Number(el.querySelector('.needle')!.getAttribute('data-angle'));
    expect(angle).toBe(180);
  });

  it('marks the over-limit state with more than colour', () => {
    const el = render({ value: 130 });
    expect(el.classList).toContain('over');
    expect(el.querySelector('.readout')!.textContent).toContain('over limit');
  });

  it('does not mark exactly at the limit as over', () => {
    expect(render({ value: 100 }).classList).not.toContain('over');
  });

  it('exposes the reading to assistive tech', () => {
    const el = render({ value: 62 });
    expect(el.getAttribute('role')).toBe('meter');
    expect(el.getAttribute('aria-valuenow')).toBe('62');
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/ui/gauge.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/ui/gauge.ts`:

```typescript
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * A half-dial for one bounded ratio — spec v85 D36.
 *
 * Used for portfolio heat utilisation, whose API value is intentionally not
 * clamped (`admin/api_v1/risk.py`: "Utilisation is NOT clamped … 130% is
 * exactly the situation the reader must see"). This component honours that:
 * the needle stops at the end of the arc because it has nowhere else to go,
 * but the readout always prints the real number and the whole gauge takes an
 * `over` treatment that is stated in words as well as in colour.
 *
 * Hand-authored SVG. The plan forbids a charting dependency, and a 180° arc is
 * two `path` elements.
 */
@Component({
  selector: 'sb-gauge',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="gauge"
      [class.over]="over()"
      role="meter"
      [attr.aria-label]="label()"
      [attr.aria-valuenow]="value()"
      [attr.aria-valuemin]="0"
      [attr.aria-valuemax]="max()"
    >
      <svg viewBox="0 0 120 66" width="100%" height="auto" aria-hidden="true">
        <path class="track" d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke-width="10" />
        @if (value() !== null) {
          <path
            class="needle"
            [attr.data-angle]="angle()"
            [attr.d]="needlePath()"
            fill="none"
            stroke-width="10"
            stroke-linecap="round"
          />
        }
      </svg>
      <div class="readout">
        @if (value() === null) {
          —
        } @else {
          {{ value() }}%@if (over()) {<span class="flag"> · over limit</span>}
        }
      </div>
      <div class="label">{{ label() }}</div>
      @if (caption()) { <div class="caption">{{ caption() }}</div> }
    </div>
  `,
  styles: `
    .gauge { display: flex; flex-direction: column; align-items: center; gap: 2px; }
    .track { stroke: var(--border); }
    .needle { stroke: var(--accent); }
    .over .needle { stroke: var(--neg); }
    .readout {
      font-size: var(--text-metric);
      font-variant-numeric: tabular-nums;
      color: var(--text);
    }
    .over .readout { color: var(--neg); }
    .flag { font-size: var(--text-micro); font-style: italic; }
    .label {
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-faint);
    }
    .caption { font-size: var(--text-micro); color: var(--text-faint); text-align: center; }
  `,
})
export class Gauge {
  readonly value = input.required<number | null>();
  readonly max = input<number>(100);
  readonly label = input.required<string>();
  readonly caption = input<string | undefined>(undefined);

  protected readonly over = computed(() => {
    const v = this.value();
    return v !== null && v > this.max();
  });

  /** Degrees along the 180° arc. Clamped — the arc ends; the number does not. */
  protected readonly angle = computed(() => {
    const v = this.value();
    if (v === null) return 0;
    const ratio = Math.min(Math.max(v / this.max(), 0), 1);
    return ratio * 180;
  });

  /** The filled portion of the arc, drawn from the left end to the needle. */
  protected readonly needlePath = computed(() => {
    const rad = (Math.PI * (180 - this.angle())) / 180;
    const x = 60 + 50 * Math.cos(rad);
    const y = 60 - 50 * Math.sin(rad);
    const large = this.angle() > 180 ? 1 : 0;
    return `M10 60 A50 50 0 ${large} 1 ${x.toFixed(2)} ${y.toFixed(2)}`;
  });
}
```

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/ui/gauge.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/gauge.ts frontend/src/app/ui/gauge.spec.ts
git commit -m "feat(ui): sb-gauge, unclamped readout with a clamped needle (v85 D36)"
```

---

### Task R2-04: `sb-matrix` — a correlation heatmap with the clusters drawn on it

**Files:**
- Create: `frontend/src/app/ui/matrix.ts`
- Create: `frontend/src/app/ui/matrix.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `Matrix` component (selector `sb-matrix`), inputs `labels`
  (`string[]`), `values` (`(number | null)[][]`), `clusters` (`string[][]`,
  default `[]`). Consumed by R8-05.

**What makes this worth building rather than a table of numbers.** Spec D38:
the matrix shows the raw pairwise relationships, and the bot's own cluster
groupings are outlined on top of it. That pairing is the point — a cluster the
sizing logic treats as one risk, drawn over the correlations it was derived
from, makes a mis-grouped cluster visible in one glance.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/matrix.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Matrix } from './matrix';

const LABELS = ['AAPL', 'MSFT', 'XOM'];
const VALUES = [
  [1, 0.68, 0.12],
  [0.68, 1, null],
  [0.12, null, 1],
];

function render(inputs: Record<string, unknown> = {}): HTMLElement {
  const f = TestBed.createComponent(Matrix);
  f.componentRef.setInput('labels', LABELS);
  f.componentRef.setInput('values', VALUES);
  for (const [key, val] of Object.entries(inputs)) f.componentRef.setInput(key, val);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.matrix')!;
}

describe('Matrix (v85 D38)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders one row per label', () => {
    expect(render().querySelectorAll('tbody tr').length).toBe(3);
  });

  it('renders a correlation to two decimals', () => {
    expect(render().querySelector('tbody tr td')!.textContent).toContain('1.00');
  });

  it('renders a missing pair as no-value, never as zero correlation', () => {
    const cells = render().querySelectorAll('tbody tr')[1].querySelectorAll('td');
    expect(cells[2].textContent!.trim()).toBe('—');
    expect(cells[2].classList).toContain('missing');
  });

  it('bands a cell by magnitude so the heat is readable', () => {
    const cells = render().querySelectorAll('tbody tr')[0].querySelectorAll('td');
    expect(cells[0].classList).toContain('b5');
    expect(cells[2].classList).toContain('b1');
  });

  it('marks cells that fall inside one of the bot clusters', () => {
    const el = render({ clusters: [['AAPL', 'MSFT']] });
    const cells = el.querySelectorAll('tbody tr')[0].querySelectorAll('td');
    expect(cells[1].classList).toContain('clustered');
    expect(cells[2].classList).not.toContain('clustered');
  });

  it('states cluster membership in text, not by outline alone', () => {
    const el = render({ clusters: [['AAPL', 'MSFT']] });
    const cells = el.querySelectorAll('tbody tr')[0].querySelectorAll('td');
    expect(cells[1].getAttribute('title')).toContain('same cluster');
  });

  it('scrolls inside its own container rather than the page', () => {
    expect(render().classList).toContain('scroll-x');
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/ui/matrix.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/ui/matrix.ts`:

```typescript
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * A square correlation heatmap — spec v85 D38.
 *
 * A table rather than an SVG grid: the values are text that must stay
 * selectable and readable by a screen reader, and a `<table>` gives the row and
 * column headers for free. Colour bands the magnitude; the number is always
 * printed, because a heatmap you cannot read the value off is a picture.
 *
 * `clusters` are the bot's own groupings from `GET /risk`. A pair inside one
 * gets an outline *and* a title saying so — the outline alone would be a
 * colour-only cue.
 */
@Component({
  selector: 'sb-matrix',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="matrix scroll-x">
      <table>
        <thead>
          <tr>
            <th scope="col"></th>
            @for (label of labels(); track label) {
              <th scope="col">{{ label }}</th>
            }
          </tr>
        </thead>
        <tbody>
          @for (row of labels(); track row; let r = $index) {
            <tr>
              <th scope="row">{{ row }}</th>
              @for (col of labels(); track col; let c = $index) {
                <td
                  [class]="cellClass(r, c)"
                  [attr.title]="cellTitle(row, col, r, c)"
                >{{ cellText(r, c) }}</td>
              }
            </tr>
          }
        </tbody>
      </table>
    </div>
  `,
  styles: `
    .scroll-x { overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; }
    th {
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-faint);
      font-weight: 400;
      text-align: right;
      padding: 2px 6px;
      white-space: nowrap;
    }
    td {
      font-size: var(--text-micro);
      font-variant-numeric: tabular-nums;
      text-align: right;
      padding: 2px 6px;
      color: var(--text);
      white-space: nowrap;
    }
    .b1 { background: var(--quality-1); }
    .b2 { background: var(--quality-2); }
    .b3 { background: var(--quality-3); }
    .b4 { background: var(--quality-4); }
    .b5 { background: var(--quality-5); }
    .missing { color: var(--text-faint); background: none; }
    .clustered { outline: 1px solid var(--accent); outline-offset: -1px; }
  `,
})
export class Matrix {
  readonly labels = input.required<string[]>();
  readonly values = input.required<(number | null)[][]>();
  readonly clusters = input<string[][]>([]);

  /** Symbol → cluster index, so a cell lookup is O(1) rather than a scan. */
  private readonly clusterOf = computed(() => {
    const map = new Map<string, number>();
    this.clusters().forEach((group, i) => group.forEach((symbol) => map.set(symbol, i)));
    return map;
  });

  protected cellText(r: number, c: number): string {
    const v = this.values()[r]?.[c];
    return v === null || v === undefined ? '—' : v.toFixed(2);
  }

  protected cellClass(r: number, c: number): string {
    const v = this.values()[r]?.[c];
    if (v === null || v === undefined) return this.clustered(r, c) ? 'missing clustered' : 'missing';
    // Five bands over |ρ|, matching the five-step quality ramp the chips use.
    const band = Math.min(5, Math.max(1, Math.ceil(Math.abs(v) * 5) || 1));
    return this.clustered(r, c) ? `b${band} clustered` : `b${band}`;
  }

  protected cellTitle(row: string, col: string, r: number, c: number): string {
    const v = this.values()[r]?.[c];
    const base = v === null || v === undefined
      ? `${row} vs ${col}: not enough overlapping bars`
      : `${row} vs ${col}: ${v.toFixed(2)}`;
    return this.clustered(r, c) ? `${base} — same cluster, sized as one risk` : base;
  }

  private clustered(r: number, c: number): boolean {
    if (r === c) return false;
    const map = this.clusterOf();
    const a = map.get(this.labels()[r]);
    const b = map.get(this.labels()[c]);
    return a !== undefined && a === b;
  }
}
```

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/ui/matrix.spec.ts
```

Expected: PASS. If `--quality-1`…`--quality-5` are absent from `tokens.css`,
stop: they exist (the chip ramp uses them) and a missing one means you are in
the wrong file.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/matrix.ts frontend/src/app/ui/matrix.spec.ts
git commit -m "feat(ui): sb-matrix, correlation heatmap with clusters outlined (v85 D38)"
```

---

### Task R2-05: `sb-timeline` — a vertical release rail

**Files:**
- Create: `frontend/src/app/ui/timeline.ts`
- Create: `frontend/src/app/ui/timeline.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `Timeline` component (selector `sb-timeline`), input `items`
  (`TimelineItem[]`), and the exported interface
  `TimelineItem { id: string; title: string; meta: string; current: boolean }`;
  one content slot projected by attribute `[body]` with implicit context.
  Consumed by R12-04.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/timeline.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Timeline, TimelineItem } from './timeline';

const ITEMS: TimelineItem[] = [
  { id: 'ui-2.14.0', title: 'v2.14.0', meta: 'UI · 22 Apr 2024', current: true },
  { id: 'ui-2.13.1', title: 'v2.13.1', meta: 'UI · 10 Apr 2024', current: false },
];

function render(items = ITEMS): HTMLElement {
  const f = TestBed.createComponent(Timeline);
  f.componentRef.setInput('items', items);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.timeline')!;
}

describe('Timeline (v85 D28)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders one entry per item', () => {
    expect(render().querySelectorAll('.entry').length).toBe(2);
  });

  it('renders the title and meta line', () => {
    const first = render().querySelector('.entry')!;
    expect(first.querySelector('.title')!.textContent).toContain('v2.14.0');
    expect(first.querySelector('.meta')!.textContent).toContain('UI · 22 Apr 2024');
  });

  it('marks the current release with a word, not only a filled dot', () => {
    const first = render().querySelector('.entry')!;
    expect(first.classList).toContain('current');
    expect(first.querySelector('.badge')!.textContent).toContain('Current');
  });

  it('leaves earlier releases unmarked', () => {
    expect(render().querySelectorAll('.entry')[1].querySelector('.badge')).toBeNull();
  });

  it('renders an ordered list so the sequence survives without CSS', () => {
    expect(render().querySelector('ol')).not.toBeNull();
  });

  it('renders nothing but an empty rail for an empty list', () => {
    expect(render([]).querySelectorAll('.entry').length).toBe(0);
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/ui/timeline.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/ui/timeline.ts`:

```typescript
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export interface TimelineItem {
  /** Stable key — `<component>-<version>`. */
  id: string;
  title: string;
  /** One line under the title: component, date. */
  meta: string;
  current: boolean;
}

/**
 * A vertical rail of dated entries — spec v85 D28, used by Versions.
 *
 * An `<ol>` because the order is the meaning: without CSS this must still read
 * as newest-first. The dot is drawn with a border on the list item rather than
 * an SVG, so it scales with the type and needs no viewBox.
 *
 * Each entry's body is projected, so Versions can put provenance and telemetry
 * inside without this component learning what either is.
 */
@Component({
  selector: 'sb-timeline',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="timeline">
      <ol>
        @for (item of items(); track item.id) {
          <li class="entry" [class.current]="item.current">
            <div class="head">
              <span class="title">{{ item.title }}</span>
              @if (item.current) { <span class="badge">Current</span> }
            </div>
            <div class="meta">{{ item.meta }}</div>
            <div class="body"><ng-content select="[body]" /></div>
          </li>
        }
      </ol>
    </div>
  `,
  styles: `
    ol { list-style: none; margin: 0; padding: 0 0 0 var(--pad); border-left: 1px solid var(--border); }
    .entry { position: relative; padding: 0 0 var(--gap) var(--pad); }
    .entry::before {
      content: '';
      position: absolute;
      left: calc(var(--pad) * -1 - 5px);
      top: 4px;
      width: 9px;
      height: 9px;
      border-radius: 50%;
      border: 2px solid var(--border);
      background: var(--bg);
    }
    .entry.current::before { border-color: var(--accent); background: var(--accent); }
    .head { display: flex; align-items: center; gap: var(--gap); }
    .title { font-size: var(--text-body); color: var(--text); font-variant-numeric: tabular-nums; }
    .badge {
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--accent);
      border: 1px solid var(--accent);
      border-radius: var(--radius);
      padding: 0 4px;
    }
    .meta { font-size: var(--text-micro); color: var(--text-faint); }
  `,
})
export class Timeline {
  readonly items = input.required<TimelineItem[]>();
}
```

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/ui/timeline.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/timeline.ts frontend/src/app/ui/timeline.spec.ts
git commit -m "feat(ui): sb-timeline for the Versions rail (v85 D28)"
```

---

### Task R2-06: `sb-freshness` — every panel says how old it is

**Files:**
- Create: `frontend/src/app/ui/freshness.ts`
- Create: `frontend/src/app/ui/freshness.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `Freshness` component (selector `sb-freshness`), inputs `at`
  (`string | null` — an ISO timestamp), `staleAfterSec` (number, default 900),
  `now` (`Date | null`, default `null`, test seam). Consumed by R4-07, R7-05,
  R8-06, R9-04.

**Why per panel.** Spec D30: the header's Live dot means only that the event
stream is connected. A single page-level "data as of" is wrong the moment a
quote is two seconds old while a risk metric is fifteen minutes old — and the
page most likely to mislead is the one whose header says "Live" over a stale
number.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/freshness.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Freshness } from './freshness';

const NOW = new Date('2026-09-11T14:30:00Z');

function render(inputs: Record<string, unknown>): HTMLElement {
  const f = TestBed.createComponent(Freshness);
  f.componentRef.setInput('at', '2026-09-11T14:29:30Z');
  f.componentRef.setInput('now', NOW);
  for (const [key, val] of Object.entries(inputs)) f.componentRef.setInput(key, val);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.freshness')!;
}

describe('Freshness (v85 D30)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('prints the time the data is as of', () => {
    expect(render({}).textContent).toContain('as of');
  });

  it('is not stale inside the threshold', () => {
    expect(render({}).classList).not.toContain('stale');
  });

  it('is stale past the threshold', () => {
    const el = render({ at: '2026-09-11T14:00:00Z', staleAfterSec: 900 });
    expect(el.classList).toContain('stale');
  });

  it('says stale in words, not by colour alone', () => {
    const el = render({ at: '2026-09-11T14:00:00Z', staleAfterSec: 900 });
    expect(el.textContent).toContain('stale');
  });

  it('reports an absent timestamp as unknown rather than as now', () => {
    const el = render({ at: null });
    expect(el.textContent).toContain('age unknown');
    expect(el.classList).toContain('stale');
  });

  it('reports an unparseable timestamp as unknown', () => {
    const el = render({ at: 'not-a-date' });
    expect(el.textContent).toContain('age unknown');
  });

  it('is announced politely rather than interrupting', () => {
    expect(render({}).getAttribute('aria-live')).toBe('polite');
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/ui/freshness.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/ui/freshness.ts`:

```typescript
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * "as of 14:29:30" for one panel — spec v85 D30.
 *
 * `now` is an input purely so the spec can pin it; in the app it is left null
 * and `Date.now()` is read at render. This component deliberately does not tick
 * — a per-second timer per panel would be a dozen timers on Risk alone, and the
 * page's own refetch is what moves this value.
 *
 * An absent or unparseable timestamp is treated as **stale**, never as fresh.
 * The failure mode this guards is a panel that silently claims to be current
 * because its data arrived without a time on it.
 */
@Component({
  selector: 'sb-freshness',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="freshness" [class.stale]="stale()" aria-live="polite">
      @if (clock() === null) {
        age unknown
      } @else {
        as of {{ clock() }}@if (stale()) {<span class="flag"> · stale</span>}
      }
    </span>
  `,
  styles: `
    .freshness {
      font-size: var(--text-micro);
      font-variant-numeric: tabular-nums;
      color: var(--text-faint);
    }
    .stale { color: var(--warn); }
    .flag { font-style: italic; }
  `,
})
export class Freshness {
  readonly at = input.required<string | null>();
  readonly staleAfterSec = input<number>(900);
  readonly now = input<Date | null>(null);

  private readonly parsed = computed(() => {
    const raw = this.at();
    if (!raw) return null;
    const d = new Date(raw);
    return Number.isNaN(d.getTime()) ? null : d;
  });

  protected readonly clock = computed(() => {
    const d = this.parsed();
    return d === null ? null : d.toISOString().slice(11, 19);
  });

  protected readonly stale = computed(() => {
    const d = this.parsed();
    if (d === null) return true;
    const now = this.now() ?? new Date();
    return (now.getTime() - d.getTime()) / 1000 > this.staleAfterSec();
  });
}
```

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/ui/freshness.spec.ts
```

Expected: PASS. If `--warn` is not in `tokens.css`, add it in R1-02's style
rather than inventing a hex here.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/freshness.ts frontend/src/app/ui/freshness.spec.ts
git commit -m "feat(ui): sb-freshness, per-panel data age (v85 D30)"
```

---

# Phase 2 — The guard

### Task R2-07: The consistency guard every workspace is measured against

**Files:**
- Create: `frontend/src/app/workspaces/workspace-consistency.spec.ts`

**Interfaces:**
- Consumes: the six primitives above, by file name.
- Produces: a failing spec that names, per workspace, which rules it still
  breaks. Every workspace task in waves 2 and 3 is finished when its own name
  no longer appears in this spec's output.

**This task commits a deliberately failing test.** That is the point: the guard
is the worklist. It is the only red spec allowed in this plan, and R12-08 is
where it turns green.

- [ ] **Step 1: Write the guard**

Create `frontend/src/app/workspaces/workspace-consistency.spec.ts`:

```typescript
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = join(process.cwd(), 'src/app/workspaces');

/** Every workspace component file, excluding specs and the gallery. */
function workspaceSources(): { name: string; path: string; source: string }[] {
  const out: { name: string; path: string; source: string }[] = [];
  for (const dir of readdirSync(ROOT, { withFileTypes: true })) {
    if (!dir.isDirectory() || dir.name === 'gallery') continue;
    for (const file of readdirSync(join(ROOT, dir.name))) {
      if (!file.endsWith('.ts') || file.endsWith('.spec.ts') || file.endsWith('.routes.ts')) continue;
      const path = join(ROOT, dir.name, file);
      out.push({ name: `${dir.name}/${file}`, path, source: readFileSync(path, 'utf8') });
    }
  }
  return out;
}

const SOURCES = workspaceSources();

describe('workspace consistency (v85)', () => {
  it('finds workspace sources at all', () => {
    expect(SOURCES.length).toBeGreaterThan(0);
  });

  it('renders no in-page heading — the top bar owns the title (D4)', () => {
    const offenders = SOURCES.filter((s) => /<h1[\s>]/.test(s.source)).map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('uses sb-panel rather than a hand-rolled card', () => {
    const offenders = SOURCES
      .filter((s) => /class="panel"/.test(s.source) && !/sb-panel/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('uses the shared control bar wherever a page has filters (D22)', () => {
    const offenders = SOURCES
      .filter((s) => /sb-filter-bar|class="filters"/.test(s.source) && !/sb-control-bar/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('sizes metric grids with auto-fit rather than a fixed column count', () => {
    const offenders = SOURCES
      .filter((s) => /grid-template-columns:\s*repeat\(\s*\d/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('declares a freshness marker on every page that fetches (D30)', () => {
    const offenders = SOURCES
      .filter((s) => /sb-async/.test(s.source) && !/sb-freshness/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it and record the worklist**

```bash
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: **FAIL**, with each failing assertion listing the workspace files that
still break it. Paste that list into the commit message — it is the worklist
waves 2 and 3 work through.

- [ ] **Step 3: Commit the failing guard**

```bash
git add frontend/src/app/workspaces/workspace-consistency.spec.ts
git commit -m "test(ui): add the v85 workspace consistency guard, deliberately failing

Lists, per rule, which workspaces still break it. Turns green at R12-08."
```
