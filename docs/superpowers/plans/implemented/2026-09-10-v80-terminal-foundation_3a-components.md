# v80 — Terminal foundation, part 3a: canonical components (F13–F16)

Part of `2026-09-10-v80-terminal-foundation_0-index.md`. Read its Global
Constraints and the v77 precondition before starting any task here.

# Phase 2 — Canonical components (continued)

## Parallelisation

- **Group A (parallel, after F3), continued.** F13–F16 run alongside F4–F12
  (parts 2a, 2b) and F17–F20 (part 3b):

  | Task | Files |
  |---|---|
  | F13 | `filter-bar.ts`, new `filter-bar.spec.ts` |
  | F14 | `format.ts` (`held()` only), `format.spec.ts` |
  | F15 | new `segmented.ts`, new `segmented.spec.ts` |
  | F16 | new `figure.ts`, new `figure.spec.ts`, plus deprecation comments in `metric-card.ts` and `metric-chip.ts` (no other task touches either) |

- **No contract dependency.**
  - F16 imports `ABSENT`/`num` from `format.ts`, which F14 does not change;
    F14 edits only `held()`.
  - F13 keeps importing `Button`, whose API F4 does not change.
- **Known interim red:** F15 and F16 add `sb-segmented`, `sb-figure` and
  `sb-figure-strip`. `workspaces/gallery/gallery.spec.ts`'s `renders sb-…`
  cases for them fail until F25, by design (index, Global Constraints).

---

### Task F13: `sb-filter-bar` counts and two-column stacking

**Files:**
- Modify: `frontend/src/app/ui/filter-bar.ts`
- Create: `frontend/src/app/ui/filter-bar.spec.ts`

**Interfaces:**
- Consumes: `Button` (unchanged).
- Produces:
  - `FilterBar.shown = input<number | null>(null)` and `FilterBar.total = input<number | null>(null)`;
  - the summary reads `N active · X of Y` when both are set, and `N active` otherwise;
  - `FilterBar` renders its own `.bar` row instead of `sb-control-row`;
  - `FilterChips` is documented as deprecated.

**Recorded in the spec (D4).** The existing contract is `N active` and
`Clear all`. `controls.spec.ts` pins both and may not be edited (spec gate 7,
Parallelisation), so this task keeps `N active` and adds `· X of Y`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/filter-bar.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { FilterBar } from './filter-bar';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/filter-bar.ts'), 'utf8');

@Component({
  imports: [FilterBar],
  template: `
    <sb-filter-bar [activeCount]="active()" [shown]="shown()" [total]="total()" (cleared)="onCleared()">
      <span class="projected">control</span>
    </sb-filter-bar>
  `,
})
class Host {
  readonly active = signal(0);
  readonly shown = signal<number | null>(null);
  readonly total = signal<number | null>(null);
  cleared = 0;
  onCleared(): void {
    this.cleared += 1;
  }
}

describe('FilterBar (v80 D4)', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const summary = () => el().querySelector('.active')?.textContent!.replace(/\s+/g, ' ').trim();

  it('says nothing about filters when none are on', () => {
    expect(el().querySelector('.summary')).toBeNull();
  });

  it('states how many filters are on and how much of the list they left', () => {
    host.active.set(2);
    host.shown.set(12);
    host.total.set(40);
    fixture.detectChanges();
    expect(summary()).toBe('2 active · 12 of 40');
  });

  it('shows the count alone when the caller has no pre-filter total', () => {
    host.active.set(2);
    host.shown.set(12);
    fixture.detectChanges();
    expect(summary()).toBe('2 active');
  });

  it('clears every filter in one click', () => {
    host.active.set(1);
    fixture.detectChanges();
    [...el().querySelectorAll('button')].find((b) => b.textContent!.includes('Clear all'))!.click();
    expect(host.cleared).toBe(1);
  });

  it('projects the caller\'s controls into its own row', () => {
    expect(el().querySelector('.bar .projected')).not.toBeNull();
    expect(el().querySelector('sb-control-row')).toBeNull();
  });

  it('stacks to a two-column grid when its own box is phone-narrow', () => {
    expect(SOURCE).toMatch(/:host \{[^}]*container: filter-bar \/ inline-size/);
    expect(SOURCE).toMatch(
      /@container filter-bar \(max-width: 639px\) \{\s*\.bar \{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
    );
  });

  it('marks sb-filter-chips deprecated in favour of sb-segmented', () => {
    expect(SOURCE).toMatch(/Deprecated \(v80 D4\)[\s\S]*sb-segmented/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/filter-bar.spec.ts')`

Expected: FAIL. The build fails first: `shown` and `total` are not inputs of `sb-filter-bar`.

- [ ] **Step 3: Implement**

In `frontend/src/app/ui/filter-bar.ts`, delete the line:

```ts
import { ControlRow } from './layout';
```

Replace everything from `/**\n * The row of filter controls above a table.` through the closing `}` of
`export class FilterBar` with:

```ts
/**
 * The row of filter controls above a table.
 *
 * `activeCount` and "Clear all" are the reason this is a component rather than
 * a `<div>`: a filtered table that looks like an empty one is the single most
 * common way a list tool wastes someone's afternoon, so the bar always states
 * how many filters are on and always offers one click to remove them.
 *
 * `shown` and `total` (v80 D4) add "12 of 40" beside the count, so the bar
 * says how much the filters removed as well as how many there are. A caller
 * whose store has no pre-filter total passes neither and shows the count
 * alone, rather than a made-up denominator.
 *
 * Controls are projected, so a workspace composes its own `Select`s and
 * `TextInput`s here rather than this component growing a filter schema.
 *
 * Its own row rather than `sb-control-row` since v80. The bar becomes a
 * two-column grid when ITS box is narrow (a drawer as much as a phone), which
 * is a container query on this host, and a control row's inner row cannot be
 * restyled from outside that component's encapsulation.
 */
@Component({
  selector: 'sb-filter-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button],
  template: `
    <div class="bar">
      <ng-content />

      @if (activeCount() > 0) {
        <span class="summary">
          <span class="active num">{{ activeCount() }} active@if (shown() !== null && total() !== null) {<span class="of">{{ ' · ' }}{{ shown() }} of {{ total() }}</span>}</span>
          <button sb-button variant="ghost" type="button" (click)="cleared.emit()">
            Clear all
          </button>
        </span>
      }
    </div>
  `,
  styles: `
    /* A container, so the stack below follows this bar's own width: a filter
       bar in a narrow drawer stacks exactly as it does on a phone (v80 D3).
       Block in normal flow, so container-type cannot collapse it. */
    :host { display: block; padding: var(--space-10) 0; container: filter-bar / inline-size; }
    /* sb-control-row's alignment rule, restated: bottom edges line up whether
       or not a control carries a label above it. */
    .bar {
      display: flex;
      align-items: flex-end;
      align-content: flex-start;
      flex-wrap: wrap;
      gap: var(--space-10);
    }
    .summary { display: inline-flex; align-items: center; gap: var(--space-8); margin-left: auto; }
    .active { color: var(--text-secondary); font-size: var(--text-table); }
    .of { color: var(--text-muted); }
    @container filter-bar (max-width: 639px) {
      .bar { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: end; }
      .summary { grid-column: 1 / -1; justify-content: space-between; margin-left: 0; }
    }
  `,
})
export class FilterBar {
  readonly activeCount = input(0);
  /** Rows left after filtering. Shown only together with `total`. */
  readonly shown = input<number | null>(null);
  /** Rows before filtering. */
  readonly total = input<number | null>(null);
  readonly cleared = output<void>();
}
```

Replace:

```ts
/**
 * A single-select chip row — Trades' status filter.
```

with:

```ts
/**
 * Deprecated (v80 D4): a single-select toggle is `sb-segmented` now. This
 * keeps working until Migration moves its two call sites.
 *
 * A single-select chip row — Trades' status filter.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/filter-bar.spec.ts' --include='**/controls.spec.ts')`

Expected: PASS.
- `controls.spec.ts`: `3 active`, `Clear all`, the chip-row tests and
  `ownRows` are unchanged (`ownRows` filters the host's own children, so a
  filter bar without a control row changes nothing).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/filter-bar.ts frontend/src/app/ui/filter-bar.spec.ts
git commit -m "feat(v80): filter bar says X of Y and stacks to two columns in a narrow box"
```

---

### Task F14: `held()` always includes minutes

**Files:**
- Modify: `frontend/src/app/ui/format.ts:60-72` (`held`)
- Test: `frontend/src/app/ui/format.spec.ts:36-67` (`describe('held')`)

**Interfaces:**
- Consumes: nothing.
- Produces: `held(hours)` keeps its signature. The output always ends in
  minutes and keeps every part below the largest one: `4d 2h 15m`, `4d 0h 5m`,
  `3h 0m`, `45m`, `0m`, and `—` for null.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/format.spec.ts`, replace the whole `describe('held', () => { … });` block with:

```ts
describe('held (v80 cell contract: minutes always present)', () => {
  it('renders minutes alone under an hour', () => {
    expect(held(0.75)).toBe('45m');
    expect(held(0.5)).toBe('30m');
  });

  it('keeps a zero minutes part under a day', () => {
    expect(held(3)).toBe('3h 0m');
    expect(held(5.2)).toBe('5h 12m');
  });

  it('keeps zero hour and minute parts past a day', () => {
    expect(held(98.25)).toBe('4d 2h 15m');
    expect(held(96 + 5 / 60)).toBe('4d 0h 5m');
    expect(held(48)).toBe('2d 0h 0m');
    expect(held(24.25)).toBe('1d 0h 15m');
  });

  it('renders "0m" rather than blank for a duration under a minute', () => {
    expect(held(0)).toBe('0m');
  });

  it('carries a minute that rounds up to 60 into the hour', () => {
    expect(held(59.999 / 60)).toBe('1h 0m');
  });

  it('renders an em dash for null or undefined', () => {
    expect(held(null)).toBe('—');
    expect(held(undefined)).toBe('—');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/format.spec.ts')`

Expected: FAIL. `held(3)` returns `3h`, `held(96 + 5/60)` returns `4d 5m`,
`held(48)` returns `2d`, `held(24.25)` returns `1d 15m` and `held(59.999/60)`
returns `1h`.

- [ ] **Step 3: Implement**

In `frontend/src/app/ui/format.ts`, replace:

```ts
/** Holding period at day/hour/minute precision. */
export function held(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return ABSENT;
  const totalMinutes = Math.round(hours * 60);
  const days = Math.floor(totalMinutes / 1440);
  const hrs = Math.floor((totalMinutes % 1440) / 60);
  const mins = totalMinutes % 60;
  const parts: string[] = [];
  if (days) parts.push(`${days}d`);
  if (hrs) parts.push(`${hrs}h`);
  if (mins || parts.length === 0) parts.push(`${mins}m`);
  return parts.join(' ');
}
```

with:

```ts
/**
 * Holding period at day/hour/minute precision.
 *
 * The v80 cell contract: minutes are always present, and every part below
 * the largest is kept, zero or not -- `4d 0h 5m`, `3h 0m`, `45m`. Dropping
 * zero parts made `4d 15m` and `4d 15h` one letter apart in a column read at
 * a glance, and made an open row's live value change shape each time a part
 * crossed zero on the 30s clock.
 */
export function held(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return ABSENT;
  const totalMinutes = Math.round(hours * 60);
  const days = Math.floor(totalMinutes / 1440);
  const hrs = Math.floor((totalMinutes % 1440) / 60);
  const mins = totalMinutes % 60;
  if (days) return `${days}d ${hrs}h ${mins}m`;
  if (hrs) return `${hrs}h ${mins}m`;
  return `${mins}m`;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/format.spec.ts' --include='**/trades.columns.spec.ts' --include='**/trade-detail.spec.ts')`

Expected: PASS. Neither workspace spec asserts a rendered `held()` string
(checked: `git grep` over `workspaces/**/*.spec.ts` finds no `Nd`/`Nh` literal).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/format.ts frontend/src/app/ui/format.spec.ts
git commit -m "feat(v80): held() always shows minutes -- 3h 0m, 4d 0h 5m"
```

---

### Task F15: `sb-segmented`, the one toggle

**Files:**
- Create: `frontend/src/app/ui/segmented.ts`
- Create: `frontend/src/app/ui/segmented.spec.ts`

**Interfaces:**
- Consumes: `--control-h`, `--accent-soft` (F2, F3).
- Produces: `Segmented` (`selector: 'sb-segmented'`) and
  `SegmentOption { value: string; label: string; count?: number }`. Inputs:
  - `options = input.required<SegmentOption[]>()`;
  - `label = input.required<string>()` (the group's accessible name);
  - `value = model<string>('')`, which gives `[(value)]` and `valueChange`.

  F25 renders it.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/segmented.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { SegmentOption, Segmented } from './segmented';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/segmented.ts'), 'utf8');
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const rule = (selector: string) =>
  SOURCE.match(new RegExp(`${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

const OPTIONS: SegmentOption[] = [
  { value: 'open', label: 'Open', count: 4 },
  { value: 'partial', label: 'Partial' },
  { value: 'closed', label: 'Closed', count: 12 },
];

@Component({
  imports: [Segmented],
  template: `<sb-segmented label="Status" [options]="options" [(value)]="value" />`,
})
class Host {
  readonly options = OPTIONS;
  readonly value = signal('open');
}

describe('Segmented (v80 D4)', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const group = () => el().querySelector('[role=group]') as HTMLElement;
  const buttons = () => [...el().querySelectorAll('button')] as HTMLButtonElement[];
  const pressed = () => buttons().map((b) => b.getAttribute('aria-pressed'));
  const tabStops = () => buttons().map((b) => b.getAttribute('tabindex'));
  const key = (k: string) => {
    group().dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true }));
    fixture.detectChanges();
  };

  it('renders one real button per option inside a named group', () => {
    expect(group().getAttribute('aria-label')).toBe('Status');
    expect(buttons().map((b) => b.textContent!.replace(/\s+/g, ' ').trim()))
      .toEqual(['Open 4', 'Partial', 'Closed 12']);
  });

  it('marks exactly the selected option pressed', () => {
    expect(pressed()).toEqual(['true', 'false', 'false']);
  });

  it('shows a count only where the store supplied one', () => {
    expect(buttons()[0].querySelector('.count')!.textContent!.trim()).toBe('4');
    expect(buttons()[1].querySelector('.count')).toBeNull();
  });

  it('binds the value two ways on click', () => {
    buttons()[2].click();
    fixture.detectChanges();
    expect(host.value()).toBe('closed');
    expect(pressed()).toEqual(['false', 'false', 'true']);
  });

  it('keeps one tab stop, on the selected option', () => {
    expect(tabStops()).toEqual(['0', '-1', '-1']);
    host.value.set('partial');
    fixture.detectChanges();
    expect(tabStops()).toEqual(['-1', '0', '-1']);
  });

  it('puts the tab stop on the first option when the value matches none', () => {
    host.value.set('expired');
    fixture.detectChanges();
    expect(tabStops()).toEqual(['0', '-1', '-1']);
  });

  it('moves with the arrow keys and wraps at both ends', () => {
    key('ArrowLeft');
    expect(host.value()).toBe('closed');
    key('ArrowRight');
    expect(host.value()).toBe('open');
    key('ArrowDown');
    expect(host.value()).toBe('partial');
    key('ArrowUp');
    expect(host.value()).toBe('open');
  });

  it('jumps to the ends with Home and End', () => {
    key('End');
    expect(host.value()).toBe('closed');
    key('Home');
    expect(host.value()).toBe('open');
  });

  it('moves focus with the selection', () => {
    buttons()[0].focus();
    key('ArrowRight');
    expect(document.activeElement).toBe(buttons()[1]);
  });

  it('ignores keys that are not navigation', () => {
    key('a');
    expect(host.value()).toBe('open');
  });

  it('scrolls sideways rather than clipping or wrapping an option', () => {
    expect(rule('.track')).toContain('overflow-x: auto');
    expect(rule('.segment')).toContain('flex: 0 0 auto');
    expect(rule('.segment')).toContain('white-space: nowrap');
  });

  it('sizes options from --control-h, so they are 44px on touch', () => {
    expect(rule('.segment')).toContain('min-height: var(--control-h)');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/segmented.spec.ts')`

Expected: FAIL. `./segmented` does not exist and the build cannot resolve it.

- [ ] **Step 3: Implement**

Create `frontend/src/app/ui/segmented.ts`:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  input,
  model,
  viewChildren,
} from '@angular/core';

/** One choice in a segmented control. */
export interface SegmentOption {
  value: string;
  label: string;
  /** Shown beside the label when the store knows the count. */
  count?: number;
}

/**
 * The one toggle -- spec v80 D4.
 *
 * Six screens hand-built a segmented toggle, and `sb-filter-chips` plus the
 * button's `segment` and `chip` variants were three more ways to draw the
 * same control. This replaces all of them in Migration.
 *
 * A toggle group, not a radio group and not tabs: each option is a real
 * button carrying `aria-pressed`, which is what the existing chip rows
 * already announce, so a screen-reader user hears the same control after
 * Migration as before it. The keyboard is the radio pattern's, because that
 * is what a single-select row wants: one tab stop (roving tabindex), the
 * arrow keys to move and wrap, Home and End to jump.
 *
 * The track scrolls sideways when the options do not fit, and an option
 * never shrinks or wraps. A clipped option is an option nobody can choose,
 * and moving focus scrolls the chosen one into view.
 */
@Component({
  selector: 'sb-segmented',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="track" role="group" [attr.aria-label]="label()" (keydown)="onKeydown($event)">
      @for (option of options(); track option.value; let i = $index) {
        <button
          #segment
          type="button"
          class="segment"
          [class.current]="option.value === value()"
          [attr.aria-pressed]="option.value === value()"
          [tabindex]="i === focusIndex() ? 0 : -1"
          (click)="value.set(option.value)"
        >
          {{ option.label }}
          @if (option.count !== undefined) {
            <span class="count num">{{ option.count }}</span>
          }
        </button>
      }
    </div>
  `,
  styles: `
    /* min-width: 0 so the host can be narrower than its options inside a flex
       row, which is what hands the overflow to .track's scroller. */
    :host { display: block; min-width: 0; max-width: 100%; }
    .track {
      display: inline-flex;
      max-width: 100%;
      overflow-x: auto;
      scrollbar-width: thin;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
    }
    .segment {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      gap: var(--space-6);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      background: transparent;
      border: 0;
      border-left: 1px solid var(--border);
      color: var(--text-secondary);
      font: inherit;
      font-size: var(--text-table);
      font-weight: 500;
      white-space: nowrap;
      cursor: pointer;
      transition: color var(--transition), background var(--transition);
    }
    .segment:first-child { border-left: 0; }
    .segment:hover { color: var(--text); }
    .segment:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    /* Selection is interactive state, which is what blue is for. */
    .current { background: var(--accent-soft); color: var(--text); }
    .count { color: var(--text-muted); font-size: var(--text-chip); }
  `,
})
export class Segmented {
  readonly options = input.required<SegmentOption[]>();
  /** The group's accessible name: "Status", "Horizon". */
  readonly label = input.required<string>();
  readonly value = model<string>('');

  private readonly segments = viewChildren<ElementRef<HTMLButtonElement>>('segment');

  /** The option holding the tab stop: the selected one, or the first when
   *  the value matches nothing, so the group is never unreachable by Tab. */
  protected readonly focusIndex = computed(() =>
    Math.max(0, this.options().findIndex((option) => option.value === this.value())),
  );

  protected onKeydown(event: KeyboardEvent): void {
    const options = this.options();
    if (!options.length) return;
    const last = options.length - 1;
    const current = this.focusIndex();
    const next =
      event.key === 'ArrowRight' || event.key === 'ArrowDown' ? (current === last ? 0 : current + 1)
      : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? (current === 0 ? last : current - 1)
      : event.key === 'Home' ? 0
      : event.key === 'End' ? last
      : -1;
    if (next < 0) return;
    event.preventDefault();
    this.value.set(options[next].value);
    this.segments()[next]?.nativeElement.focus();
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/segmented.spec.ts')`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/segmented.ts frontend/src/app/ui/segmented.spec.ts
git commit -m "feat(v80): sb-segmented -- one toggle with counts, roving tabindex, no clipping"
```

---

### Task F16: `sb-figure` and `sb-figure-strip`

**Files:**
- Create: `frontend/src/app/ui/figure.ts`
- Create: `frontend/src/app/ui/figure.spec.ts`
- Modify: `frontend/src/app/ui/metric-card.ts` (class comment only)
- Modify: `frontend/src/app/ui/metric-chip.ts` (class comment only)

**Interfaces:**
- Consumes: `ABSENT`, `num` from `format.ts` (unchanged by F14); `.sb-label`
  and `--text-metric` (F3).
- Produces:
  - `Figure` (`sb-figure`) with inputs `label` (required string), `value`
    (required `number | null`), `tone: FigureTone = 'plain'`, `unit = ''`,
    `decimals = 2`, `sub: string | null = null`;
  - `FigureTone = 'plain' | 'pnl' | 'caution'`, the same meanings as `MetricTone`;
  - `FigureStrip` (`sb-figure-strip`), which sets `--figure-columns`
    (1–4, from the projected figure count) on its host.

  F25 renders both.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/figure.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Figure, FigureStrip, FigureTone } from './figure';

const read = (file: string) => readFileSync(join(process.cwd(), 'src/app/ui', file), 'utf8');
const SOURCE = read('figure.ts');

function figure(
  value: number | null,
  tone: FigureTone = 'plain',
  extra: { unit?: string; decimals?: number; sub?: string } = {},
): HTMLElement {
  const f = TestBed.createComponent(Figure);
  f.componentRef.setInput('label', 'Expectancy');
  f.componentRef.setInput('value', value);
  f.componentRef.setInput('tone', tone);
  for (const [name, input] of Object.entries(extra)) f.componentRef.setInput(name, input);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

const valueOf = (el: HTMLElement) => el.querySelector('.value')!;

describe('Figure (v80 D4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('labels the figure in the shared label style', () => {
    expect(figure(1).querySelector('.sb-label')!.textContent!.trim()).toBe('Expectancy');
  });

  it('formats to the requested decimals with the unit attached', () => {
    expect(valueOf(figure(54.23, 'plain', { unit: '%', decimals: 1 })).textContent!.trim()).toBe('54.2%');
  });

  it('colours a pnl figure by sign, and leaves zero uncoloured', () => {
    expect(valueOf(figure(0.21, 'pnl')).classList).toContain('pos');
    expect(valueOf(figure(-0.4, 'pnl')).classList).toContain('neg');
    const zero = valueOf(figure(0, 'pnl')).classList;
    expect(zero).not.toContain('pos');
    expect(zero).not.toContain('neg');
  });

  it('never colours a plain figure green or red, even when negative', () => {
    const cls = valueOf(figure(-3, 'plain')).classList;
    expect(cls).not.toContain('neg');
    expect(cls).not.toContain('pos');
  });

  it('paints a caution figure amber', () => {
    expect(valueOf(figure(82, 'caution')).classList).toContain('warn');
  });

  it('is an em dash with no unit when there is no value yet', () => {
    const v = valueOf(figure(null, 'pnl', { unit: '%' }));
    expect(v.textContent!.trim()).toBe('—');
    expect(v.classList).toContain('absent');
  });

  it('carries at most one sub-line', () => {
    expect(figure(1, 'plain', { sub: 'n = 184' }).querySelector('.sub')!.textContent!.trim()).toBe('n = 184');
    expect(figure(1).querySelector('.sub')).toBeNull();
  });

  it('sets the value in mono 500 at the metric size', () => {
    const rule = SOURCE.match(/\.value \{[^}]*\}/)![0];
    expect(rule).toContain('font-weight: 500');
    expect(rule).toContain('var(--text-metric)');
  });

  it('shrinks the value to 20px when its strip is phone-narrow', () => {
    expect(SOURCE).toMatch(/@container figures \(max-width: 639px\) \{[\s\S]*?\.value \{ font-size: var\(--text-title\); \}/);
  });
});

@Component({
  imports: [Figure, FigureStrip],
  template: `
    <sb-figure-strip>
      @for (n of figures(); track n) {
        <sb-figure [label]="'F' + n" [value]="n" />
      }
    </sb-figure-strip>
  `,
})
class StripHost {
  readonly figures = signal([1, 2, 3]);
}

describe('FigureStrip (v80 D4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('gives each figure a column, up to four', () => {
    const f = TestBed.createComponent(StripHost);
    f.detectChanges();
    const strip = (f.nativeElement as HTMLElement).querySelector('sb-figure-strip') as HTMLElement;
    expect(strip.style.getPropertyValue('--figure-columns')).toBe('3');

    f.componentInstance.figures.set([1, 2, 3, 4, 5, 6]);
    f.detectChanges();
    expect(strip.style.getPropertyValue('--figure-columns')).toBe('4');
  });

  it('draws hairlines between figures and none around a lone figure', () => {
    expect(SOURCE).toMatch(/\.strip \{[^}]*--figure-rule: 1px/);
    expect(SOURCE).toMatch(/border-left: var\(--figure-rule, 0px\) solid var\(--border\)/);
  });

  it('drops to two per row when the strip is phone-narrow', () => {
    expect(SOURCE).toMatch(/@container figures \(max-width: 639px\) \{\s*\.strip \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/);
  });
});

describe('the figure primitives it replaces', () => {
  for (const file of ['metric-card.ts', 'metric-chip.ts']) {
    it(`${file} is marked deprecated in favour of sb-figure`, () => {
      expect(read(file)).toMatch(/Deprecated \(v80 D4\): use `sb-figure`/);
    });
  }
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/figure.spec.ts')`

Expected: FAIL. `./figure` does not exist.

- [ ] **Step 3: Implement**

Create `frontend/src/app/ui/figure.ts`:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  contentChildren,
  input,
} from '@angular/core';

import { ABSENT, num } from './format';

/** How a figure is coloured. `pnl` is the ONLY tone that may go green or red:
 *  those two colours mean P&L direction and nothing else. */
export type FigureTone = 'plain' | 'pnl' | 'caution';

/**
 * One headline figure -- spec v80 D4.
 *
 * Replaces four treatments: `sb-metric-card`, `sb-metric-chip`, the two mixed
 * on one screen, and Risk's hand-built 25px/700 number. One label, one value
 * with its unit, at most one sub-line. Hierarchy comes from which figures a
 * screen puts in its strip, not from a second size.
 *
 * Mono 500 at --text-metric (28px), tabular: JetBrains Mono is self-hosted at
 * 400/500/700, and 700 is for ticker symbols only (D3). `--register-figure`
 * still wins where a register sets it, as it did for MetricCard.
 */
@Component({
  selector: 'sb-figure',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="figure">
      <span class="sb-label">{{ label() }}</span>
      <span class="value num" [class]="toneClass()">{{ display() }}</span>
      @if (sub(); as subtext) {
        <span class="sub num">{{ subtext }}</span>
      }
    </div>
  `,
  styles: `
    /* The hairline between figures is this figure's own top and left border,
       sized by --figure-rule, which only sb-figure-strip sets. A figure on its
       own draws none. */
    :host {
      display: block;
      min-width: 0;
      border-left: var(--figure-rule, 0px) solid var(--border);
      border-top: var(--figure-rule, 0px) solid var(--border);
    }
    .figure {
      display: flex;
      flex-direction: column;
      gap: var(--space-6);
      height: 100%;
      box-sizing: border-box;
      padding: var(--space-14) var(--space-20);
      background: var(--surface);
    }
    .value {
      font-family: var(--font-mono);
      font-size: var(--register-figure, var(--text-metric));
      font-weight: 500;
      font-variant-numeric: tabular-nums;
      line-height: 1.1;
      white-space: nowrap;
    }
    .sub { color: var(--text-muted); font-size: var(--register-label, var(--text-table)); }
    .warn { color: var(--warn); }
    /* --text-muted, not --text-faint: "no value yet" is something to read. */
    .absent { color: var(--text-muted); }
    /* 20px when the strip is phone-narrow (v80 D3): a container query against
       sb-figure-strip, an ancestor of this element. Last in the sheet, so a
       parser that does not know @container loses nothing after it. */
    @container figures (max-width: 639px) {
      .figure { padding: var(--space-10) var(--space-14); }
      .value { font-size: var(--text-title); }
    }
  `,
})
export class Figure {
  readonly label = input.required<string>();
  readonly value = input.required<number | null>();
  readonly tone = input<FigureTone>('plain');
  /** Rendered straight after the number: '%', 'R', ' €'. Money units come
   *  from `ConnectionStore.currency()`, never a literal. */
  readonly unit = input('');
  readonly decimals = input(2);
  readonly sub = input<string | null>(null);

  /** An em dash, never "0": a figure with no value yet is not a figure that
   *  is zero, and the unit goes with the number. */
  protected readonly display = computed(() => {
    const value = this.value();
    return value === null ? ABSENT : `${num(value, this.decimals())}${this.unit()}`;
  });

  protected readonly toneClass = computed(() => {
    const value = this.value();
    if (value === null) return 'absent';
    if (this.tone() === 'caution') return 'warn';
    if (this.tone() !== 'pnl') return '';
    // Exactly zero is neither a profit nor a loss.
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  });
}

/**
 * A hairline-divided strip of headline figures -- spec v80 D4.
 *
 * Up to four per row, and two when the strip itself is phone-narrow. The
 * column count comes from the projected figures, so four take quarters and
 * three take thirds without the caller naming a count; a fifth wraps.
 *
 * Each figure draws its own top and left rule, and this host clips the outer
 * ones: the grid sits at -1px inside an overflow-hidden box that carries the
 * frame. So however the figures wrap, no row or column shows a doubled rule
 * or a missing one.
 */
@Component({
  selector: 'sb-figure-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[style.--figure-columns]': 'columns()' },
  template: `<div class="strip"><ng-content /></div>`,
  styles: `
    /* A container, so two-per-row follows the strip's own box rather than the
       viewport. Block in normal flow, so container-type cannot collapse it. */
    :host {
      display: block;
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      container: figures / inline-size;
    }
    .strip {
      --figure-rule: 1px;
      display: grid;
      grid-template-columns: repeat(var(--figure-columns, 4), minmax(0, 1fr));
      margin: -1px 0 0 -1px;
    }
    @container figures (max-width: 639px) {
      .strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  `,
})
export class FigureStrip {
  private readonly figures = contentChildren(Figure);
  protected readonly columns = computed(() => Math.min(4, Math.max(1, this.figures().length)));
}
```

In `frontend/src/app/ui/metric-card.ts`, replace:

```ts
/**
 * One large number with a label. The Dashboard's primary tier.
```

with:

```ts
/**
 * Deprecated (v80 D4): use `sb-figure` inside an `sb-figure-strip`. Kept
 * working until Migration moves its ten call sites, then deleted.
 *
 * One large number with a label. The Dashboard's primary tier.
```

In `frontend/src/app/ui/metric-chip.ts`, replace:

```ts
/**
 * One number with a label, compact. The Dashboard's secondary tier.
```

with:

```ts
/**
 * Deprecated (v80 D4): use `sb-figure` inside an `sb-figure-strip`. Kept
 * working until Migration moves its seventeen call sites, then deleted.
 *
 * One number with a label, compact. The Dashboard's secondary tier.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/figure.spec.ts')`

Expected: PASS.

If `gives each figure a column, up to four` reads `''`, jsdom's CSS
declaration did not keep a custom property that Angular set through
`style.setProperty`. Assert on
`strip.getAttribute('style')` containing `--figure-columns: 3` instead: the
binding is the behaviour, and the style attribute is where it lands.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/figure.ts frontend/src/app/ui/figure.spec.ts frontend/src/app/ui/metric-card.ts frontend/src/app/ui/metric-chip.ts
git commit -m "feat(v80): sb-figure and sb-figure-strip; metric card and chip deprecated"
```
