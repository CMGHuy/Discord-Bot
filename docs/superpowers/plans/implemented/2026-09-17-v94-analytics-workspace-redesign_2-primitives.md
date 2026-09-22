# Analytics Workspace Redesign (v94) — Part 2: Frontend primitives, hover layer, palette

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Header, constraints and prerequisite in `_0-index.md`. **Spec:** `docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md` §3.4, §3.11.

# Phase 2 — Primitives

Every file here lives in `frontend/src/app/ui/`, is standalone + `OnPush`, takes plain data inputs, uses tokens only, and ships with a vitest spec next to it. Spec runner per task: `cd frontend && npm test -- --include src/app/ui/<name>.spec.ts`. All specs follow `histogram.spec.ts`'s pattern: `TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] })`, `TestBed.createComponent(X)`, `fixture.componentRef.setInput(...)`, `fixture.detectChanges()`, assert on `fixture.nativeElement`.

Read the dataviz method once before starting (the marks and interaction rules are quoted in each task where they bind): thin marks, 2px lines, 4px rounded data-ends, 2px surface gap between fills, hit target ≥ 24px, values lead in a tooltip, text in text tokens, one axis.

## Parallelisation (this phase)

- **Sequential first:** P1 (`sb-chart-tooltip` + `hoverRows`) — every other primitive imports it. P2 and P3 next (every tab consumes them) — they may run in parallel with each other.
- **Group B (parallel after P1):** P4, P5, P6, P7, P8, P9 — one new file + spec each; P9 additionally edits `histogram.ts` and `bar-list.ts`, which nothing else in this phase touches.
- **Sequential last:** P10 (`tokens.css`).

## Exit criteria

Nine new primitives with green specs; histogram and bar-list expose per-mark hover; `node …/validate_palette.js` passes for `--chart-1…6` against `--surface` in both themes (or the re-stepped values are committed with the validator output pasted in the commit body).

---

### Task P1: `sb-chart-tooltip` + `hoverRows` helper

**Files:**
- Create: `frontend/src/app/ui/chart-tooltip.ts`, `frontend/src/app/ui/chart-tooltip.spec.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface TooltipRow { label: string; value: string; swatch?: string /* CSS colour, drawn as a 12×2px stroke */ }
  export interface HoverState { x: number; y: number; title: string; rows: TooltipRow[] }
  export function hoverPosition(event: PointerEvent | FocusEvent, host: HTMLElement): { x: number; y: number }
  @Component({ selector: 'sb-chart-tooltip' }) class ChartTooltip { state = input.required<HoverState | null>() }
  ```
  The host that renders `<sb-chart-tooltip>` must be `position: relative`; the tooltip is absolutely positioned at `state.x/y`, flips left when it would overflow the host's right edge, and is `aria-live="polite"` so keyboard focus reads it.

- [ ] **Step 1: Failing spec**

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ChartTooltip, HoverState, hoverPosition } from './chart-tooltip';

describe('ChartTooltip', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  const render = (state: HoverState | null) => {
    const fixture = TestBed.createComponent(ChartTooltip);
    fixture.componentRef.setInput('state', state);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  };

  it('renders nothing when there is no hover state', () => {
    expect(render(null).querySelector('.tooltip')).toBeNull();
  });

  it('puts the value first and keys each row with a stroke, via textContent', () => {
    const el = render({ x: 10, y: 20, title: '2026-08-04', rows: [
      { label: '<b>MACD</b>', value: '+1.20R', swatch: 'var(--chart-1)' },
    ] });
    const row = el.querySelector('.row')!;
    expect(row.querySelector('.value')!.textContent).toBe('+1.20R');
    expect(row.querySelector('.label')!.textContent).toBe('<b>MACD</b>');   // never innerHTML
    expect(row.querySelector('.label')!.querySelector('b')).toBeNull();
    expect((row.querySelector('.swatch') as HTMLElement).style.background).toContain('--chart-1');
    expect((el.querySelector('.tooltip') as HTMLElement).style.left).toBe('10px');
  });

  it('hoverPosition is relative to the host box', () => {
    const host = document.createElement('div');
    host.getBoundingClientRect = () => ({ left: 100, top: 50 } as DOMRect);
    const ev = { clientX: 130, clientY: 70 } as PointerEvent;
    expect(hoverPosition(ev, host)).toEqual({ x: 30, y: 20 });
  });
});
```

Run: `cd frontend && npm test -- --include src/app/ui/chart-tooltip.spec.ts` → FAIL (module not found).

- [ ] **Step 2: Implement**

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { CHART_CHROME } from './chart/chart-frame';

export interface TooltipRow { label: string; value: string; swatch?: string; }
export interface HoverState { x: number; y: number; title: string; rows: TooltipRow[]; }

/** Pointer (or focus target) position relative to the chart host. Focus
 *  events have no client coordinates: fall back to the target's own box. */
export function hoverPosition(event: PointerEvent | FocusEvent, host: HTMLElement): { x: number; y: number } {
  const box = host.getBoundingClientRect();
  if ('clientX' in event) return { x: event.clientX - box.left, y: event.clientY - box.top };
  const target = (event.target as HTMLElement | null)?.getBoundingClientRect();
  return target ? { x: target.left - box.left + target.width / 2, y: target.top - box.top } : { x: 0, y: 0 };
}

/**
 * The one hover readout every chart uses (spec v94 D11). Values lead, labels
 * follow; series are keyed by a short stroke, not a filled box; every string
 * is bound as text. The host is `position: relative`; this element is
 * absolutely placed and flips left near the host's right edge.
 */
@Component({
  selector: 'sb-chart-tooltip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (state(); as s) {
      <div class="tooltip" role="status" aria-live="polite"
           [style.left.px]="s.x" [style.top.px]="s.y" [class.flip]="flip()">
        <div class="title">{{ s.title }}</div>
        @for (row of s.rows; track row.label) {
          <div class="row">
            @if (row.swatch) { <span class="swatch" [style.background]="row.swatch"></span> }
            <span class="value num">{{ row.value }}</span>
            <span class="label">{{ row.label }}</span>
          </div>
        }
      </div>
    }
  `,
  styles: `
    :host { display: contents; }
    .tooltip {
      position: absolute; z-index: 3; pointer-events: none;
      transform: translate(12px, -50%);
      min-width: 9rem; padding: var(--space-6) var(--space-8);
      background: var(${CHART_CHROME.tooltipSurface});
      border: 1px solid var(${CHART_CHROME.tooltipBorder});
      border-radius: var(--radius); box-shadow: var(--shadow-overlay);
      font-size: var(--text-chip);
    }
    .tooltip.flip { transform: translate(calc(-100% - 12px), -50%); }
    .title { color: var(--text-muted); font-size: var(--text-micro); margin-bottom: 2px; }
    .row { display: grid; grid-template-columns: auto auto 1fr; align-items: center; gap: var(--space-6); }
    .swatch { display: inline-block; width: 12px; height: 2px; border-radius: 1px; }
    .value { color: var(--text); font-weight: 600; font-variant-numeric: tabular-nums; }
    .label { color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  `,
})
export class ChartTooltip {
  readonly state = input.required<HoverState | null>();
  /** Flip once past 70% of a typical panel; hosts with a known width pass
   *  `hostWidth` for an exact edge. */
  readonly hostWidth = input<number | null>(null);
  protected readonly flip = computed(() => {
    const s = this.state(); const w = this.hostWidth();
    return !!s && w !== null && s.x > w * 0.7;
  });
}
```

- [ ] **Step 3: Run spec → PASS. Commit**

```bash
git add frontend/src/app/ui/chart-tooltip.ts frontend/src/app/ui/chart-tooltip.spec.ts
git commit -m "feat(v94): sb-chart-tooltip -- the one hover readout for every analytics chart"
```

---

### Task P2: `sb-panel-header` (title · N · all-time · hint · Table) and `sb-stat-tile` secondary line + trend

**Files:**
- Create: `frontend/src/app/ui/panel-header.ts`, `frontend/src/app/ui/panel-header.spec.ts`
- Modify: `frontend/src/app/ui/stat-tile.ts` (template L34–47, class L85–89), `frontend/src/app/ui/stat-tile.spec.ts`

**Interfaces:**
- Produces:
  ```ts
  // panel-header.ts
  @Component({ selector: 'sb-panel-header' }) class PanelHeader {
    title = input.required<string>(); n = input<number | null>(null); allTime = input(false);
    hint = input<string | null>(null); tableable = input(false);
    tableOpen = model(false);                      // toggled by the Table button
    total = input<string | null>(null);            // e.g. the currency total (spec D3)
  }
  // stat-tile.ts additions
  secondary = input<string | null>(null);          // always-visible second line (currency, spec D3)
  trend = input<readonly number[] | null>(null);   // 30-trade sparkline
  ```
- Consumes: `sb-hint` (`hint.ts`: `text`, `label`), `sb-sparkline` (`points`, `label`).

- [ ] **Step 1: Failing specs**

`panel-header.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { PanelHeader } from './panel-header';

describe('PanelHeader', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  const render = (inputs: Record<string, unknown>) => {
    const fixture = TestBed.createComponent(PanelHeader);
    for (const [k, v] of Object.entries(inputs)) fixture.componentRef.setInput(k, v);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  };

  it('states title, N and the currency total', () => {
    const { el } = render({ title: 'Equity', n: 312, total: '+$1,240' });
    expect(el.textContent).toContain('Equity');
    expect(el.querySelector('.n')!.textContent).toContain('N=312');
    expect(el.querySelector('.total')!.textContent).toBe('+$1,240');
    expect(el.querySelector('.all-time')).toBeNull();
  });

  it('badges all-time panels and hides N when unknown', () => {
    const { el } = render({ title: 'Calibration', allTime: true });
    expect(el.querySelector('.all-time')!.textContent).toContain('all-time');
    expect(el.querySelector('.n')).toBeNull();
  });

  it('Table button toggles tableOpen', () => {
    const { fixture, el } = render({ title: 'By horizon', tableable: true });
    (el.querySelector('button.table') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(fixture.componentInstance.tableOpen()).toBe(true);
    expect((el.querySelector('button.table') as HTMLButtonElement).getAttribute('aria-pressed')).toBe('true');
  });
});
```

`stat-tile.spec.ts` append (inside the existing `describe`, reusing its render helper or `TestBed.createComponent(StatTile)` directly — the file already provides `PreferencesStore`):

```ts
  it('always shows the secondary line and a trend when given', () => {
    const fixture = TestBed.createComponent(StatTile);
    fixture.componentRef.setInput('label', 'Total R');
    fixture.componentRef.setInput('value', '+12.4R');
    fixture.componentRef.setInput('secondary', '+$1,240');
    fixture.componentRef.setInput('trend', [1, 2, 1.5, 3]);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.secondary')!.textContent).toBe('+$1,240');
    expect(el.querySelector('sb-sparkline')).not.toBeNull();
  });
```

Run both → FAIL.

- [ ] **Step 2: Implement `panel-header.ts`**

```ts
import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

import { Hint } from './hint';

/**
 * Every analytics panel says what it rests on (spec v94 D4): title, N, an
 * all-time badge when the control bar does not scope it, a definition
 * behind the hint glyph, the currency total (D3), and a Table toggle so no
 * value is reachable only by colour or hover (H3).
 */
@Component({
  selector: 'sb-panel-header',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint],
  template: `
    <header class="head">
      <h3 class="title">{{ title() }}</h3>
      @if (allTime()) { <span class="all-time" title="Not scoped by the control bar">all-time</span> }
      @if (n() !== null) { <span class="n num">N={{ n() }}</span> }
      @if (hint()) { <sb-hint [text]="hint()!" [label]="'What ' + title() + ' means'" /> }
      <span class="spacer"></span>
      @if (total()) { <span class="total num">{{ total() }}</span> }
      @if (tableable()) {
        <button type="button" class="table" [attr.aria-pressed]="tableOpen()"
                (click)="tableOpen.set(!tableOpen())">Table</button>
      }
    </header>
  `,
  styles: `
    .head { display: flex; align-items: baseline; gap: var(--space-8); min-height: var(--control-h); }
    .title { margin: 0; font-size: var(--text-subhead); font-weight: 500; color: var(--text); }
    .n, .total { font-size: var(--text-chip); font-variant-numeric: tabular-nums; }
    .n { color: var(--text-faint); }
    .total { color: var(--text-secondary); }
    .all-time { font-size: var(--text-micro); text-transform: uppercase; letter-spacing: .08em;
                color: var(--warn); border: 1px solid var(--warn); border-radius: var(--radius-chip); padding: 0 4px; }
    .spacer { flex: 1; }
    button.table { font: inherit; font-size: var(--text-chip); color: var(--text-secondary);
                   background: none; border: 1px solid var(--border); border-radius: var(--radius); padding: 0 6px; height: 22px; cursor: pointer; }
    button.table[aria-pressed="true"] { color: var(--accent); border-color: var(--accent); }
  `,
})
export class PanelHeader {
  readonly title = input.required<string>();
  readonly n = input<number | null>(null);
  readonly allTime = input(false);
  readonly hint = input<string | null>(null);
  readonly total = input<string | null>(null);
  readonly tableable = input(false);
  readonly tableOpen = model(false);
}
```

- [ ] **Step 3: Extend `stat-tile.ts`** — add to imports `Sparkline` from `./sparkline` and to the template after `.value`:

```html
      @if (secondary()) { <div class="secondary num">{{ secondary() }}</div> }
      @if (trend(); as t) { @if (t.length > 1) { <sb-sparkline class="trend" [points]="t" [label]="label() + ' trend'" /> } }
```

styles: `.secondary { font-size: var(--text-chip); color: var(--text-secondary); font-variant-numeric: tabular-nums; } .trend { display: block; height: 22px; margin-top: 4px; }`; class: `readonly secondary = input<string | null>(null); readonly trend = input<readonly number[] | null>(null);`. Add `Sparkline` to the component's `imports`.

- [ ] **Step 4: Run both specs → PASS. Commit**

```bash
git add frontend/src/app/ui/panel-header.ts frontend/src/app/ui/panel-header.spec.ts frontend/src/app/ui/stat-tile.ts frontend/src/app/ui/stat-tile.spec.ts
git commit -m "feat(v94): sb-panel-header (title, N, all-time, hint, Table); stat tile secondary line and trend"
```

---

### Task P3: `sb-panel-error`

**Files:**
- Create: `frontend/src/app/ui/panel-error.ts`, `frontend/src/app/ui/panel-error.spec.ts`

**Interfaces:**
- Produces: `@Component({ selector: 'sb-panel-error' }) class PanelError { message = input<string | null>(null); retry = output<void>() }` — a compact surface that **replaces** a chart on fetch failure (H4). Distinct from `sb-empty-state`, which is for a measured zero.

- [ ] **Step 1: Failing spec**

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PanelError } from './panel-error';

describe('PanelError', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('names the failure and retries on click', () => {
    const fixture = TestBed.createComponent(PanelError);
    fixture.componentRef.setInput('message', 'The admin is not responding.');
    const retry = vi.fn();
    fixture.componentInstance.retry.subscribe(retry);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.getAttribute('role')).toBe('alert');
    expect(el.textContent).toContain('Could not load');
    expect(el.textContent).toContain('The admin is not responding.');
    (el.querySelector('button') as HTMLButtonElement).click();
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Implement**

```ts
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

/** A failed fetch is not an empty chart (spec v94 H4). This replaces the
 *  chart body; the panel header stays so the reader knows WHICH panel failed. */
@Component({
  selector: 'sb-panel-error',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'alert' },
  template: `
    <div class="error">
      <span class="text">Could not load@if (message()) { <span class="why"> · {{ message() }}</span> }</span>
      <button type="button" (click)="retry.emit()">Retry</button>
    </div>
  `,
  styles: `
    :host { display: block; }
    .error { display: flex; align-items: center; justify-content: space-between; gap: var(--space-8);
             min-height: 96px; padding: var(--space-14); border: 1px dashed var(--neg); border-radius: var(--radius);
             background: var(--neg-soft); font-size: var(--text-table); color: var(--text); }
    .why { color: var(--text-secondary); }
    button { font: inherit; font-size: var(--text-chip); color: var(--text); background: var(--surface-raised);
             border: 1px solid var(--border-strong); border-radius: var(--radius); height: var(--control-h); padding: 0 10px; cursor: pointer; }
  `,
})
export class PanelError {
  readonly message = input<string | null>(null);
  readonly retry = output<void>();
}
```

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/ui/panel-error.ts frontend/src/app/ui/panel-error.spec.ts
git commit -m "feat(v94): sb-panel-error -- a failed fetch is never an empty panel"
```

---

### Task P4: `sb-share-bar` (part-to-whole)

**Files:**
- Create: `frontend/src/app/ui/share-bar.ts`, `frontend/src/app/ui/share-bar.spec.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface ShareSegment { label: string; count: number; tone?: 'pos' | 'neg' | 'warn' | 'muted' | 'accent' }
  @Component({ selector: 'sb-share-bar' }) class ShareBar { segments = input.required<readonly ShareSegment[]>(); label = input.required<string>() }
  ```
  One horizontal bar; segments proportional to count with a 2px surface gap; a legend row beneath with `label · count · pct` in text tokens; per-segment hover via `sb-chart-tooltip`; zero total renders the empty track and a "no observations" legend.

- [ ] **Step 1: Failing spec**

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ShareBar, ShareSegment } from './share-bar';

const render = (segments: ShareSegment[]) => {
  const fixture = TestBed.createComponent(ShareBar);
  fixture.componentRef.setInput('segments', segments);
  fixture.componentRef.setInput('label', 'Outcome');
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
};

describe('ShareBar', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('sizes segments by share and lists each with count and percent', () => {
    const el = render([{ label: 'Wins', count: 53, tone: 'pos' }, { label: 'Losses', count: 47, tone: 'neg' }]);
    const widths = [...el.querySelectorAll('.seg')].map((s) => (s as HTMLElement).style.flexGrow);
    expect(widths).toEqual(['53', '47']);
    expect(el.querySelector('.legend')!.textContent).toContain('Wins');
    expect(el.querySelector('.legend')!.textContent).toContain('53%');
    expect([...el.querySelectorAll('.seg')].every((s) => s.getAttribute('tabindex') === '0')).toBe(true);
  });

  it('says so when there is nothing to share out', () => {
    const el = render([{ label: 'Wins', count: 0 }, { label: 'Losses', count: 0 }]);
    expect(el.querySelectorAll('.seg').length).toBe(0);
    expect(el.textContent).toContain('no observations');
  });
});
```

- [ ] **Step 2: Implement**

```ts
import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { ChartTooltip, HoverState, hoverPosition } from './chart-tooltip';

export interface ShareSegment { label: string; count: number; tone?: 'pos' | 'neg' | 'warn' | 'muted' | 'accent'; }

/** Part-to-whole as one horizontal bar (spec v94 D6/D8): a 53/47 split is
 *  what a donut renders worst. 2px surface gaps between fills; legend and
 *  direct labels in text tokens; every segment is a hover/focus target. */
@Component({
  selector: 'sb-share-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChartTooltip],
  template: `
    <div class="host" #host>
      <div class="track" role="img" [attr.aria-label]="ariaLabel()">
        @for (s of drawn(); track s.label) {
          <span class="seg" [attr.data-tone]="s.tone ?? 'accent'" [style.flexGrow]="s.count" tabindex="0"
                (pointermove)="show($event, s, host)" (focus)="show($event, s, host)"
                (pointerleave)="hover.set(null)" (blur)="hover.set(null)"></span>
        }
      </div>
      <ul class="legend">
        @if (total() === 0) { <li class="none">no observations</li> }
        @for (s of segments(); track s.label) {
          <li><span class="key" [attr.data-tone]="s.tone ?? 'accent'"></span>
              <span class="label">{{ s.label }}</span>
              <span class="num">{{ s.count }} · {{ pct(s.count) }}%</span></li>
        }
      </ul>
      <sb-chart-tooltip [state]="hover()" [hostWidth]="host.clientWidth" />
    </div>
  `,
  styles: `
    .host { position: relative; }
    .track { display: flex; gap: 2px; height: 14px; background: var(--bg); border-radius: 4px; overflow: hidden; }
    .seg { display: block; flex-basis: 0; min-width: 2px; outline: none; }
    .seg:hover, .seg:focus-visible { filter: brightness(1.15); }
    [data-tone='pos'] { background: var(--pos); } [data-tone='neg'] { background: var(--neg); }
    [data-tone='warn'] { background: var(--warn); } [data-tone='muted'] { background: var(--text-faint); }
    [data-tone='accent'] { background: var(--accent); }
    .legend { display: flex; flex-wrap: wrap; gap: var(--space-8) var(--space-14); margin: var(--space-6) 0 0; padding: 0; list-style: none; font-size: var(--text-chip); }
    .legend li { display: inline-flex; align-items: center; gap: var(--space-6); color: var(--text-secondary); }
    .key { width: 10px; height: 10px; border-radius: 2px; }
    .num { color: var(--text); font-variant-numeric: tabular-nums; }
    .none { color: var(--text-faint); font-style: italic; }
  `,
})
export class ShareBar {
  readonly segments = input.required<readonly ShareSegment[]>();
  readonly label = input.required<string>();
  protected readonly hover = signal<HoverState | null>(null);
  protected readonly total = computed(() => this.segments().reduce((n, s) => n + s.count, 0));
  protected readonly drawn = computed(() => this.segments().filter((s) => s.count > 0));
  protected readonly ariaLabel = computed(() =>
    `${this.label()}: ` + this.segments().map((s) => `${s.label} ${s.count}`).join(', '));
  protected pct(count: number): string { const t = this.total(); return t ? Math.round((count / t) * 100).toString() : '0'; }
  protected show(ev: PointerEvent | FocusEvent, s: ShareSegment, host: HTMLElement): void {
    this.hover.set({ ...hoverPosition(ev, host), title: this.label(),
      rows: [{ label: s.label, value: `${s.count} · ${this.pct(s.count)}%` }] });
  }
}
```

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/ui/share-bar.ts frontend/src/app/ui/share-bar.spec.ts
git commit -m "feat(v94): sb-share-bar -- part-to-whole with gaps, legend and per-segment hover"
```

---

### Task P5: `sb-waterfall`

**Files:**
- Create: `frontend/src/app/ui/waterfall.ts`, `frontend/src/app/ui/waterfall.spec.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface WaterfallStep { label: string; value: number; n?: number }
  @Component({ selector: 'sb-waterfall' }) class Waterfall {
    steps = input.required<readonly WaterfallStep[]>(); format = input<(v: number) => string>((v) => v.toFixed(2)); totalLabel = input('Total');
  }
  ```
  Horizontal SVG: one row per step, a floating bar from the running total before the step to after it, `--pos` for positive and `--neg` for negative steps, a final `Total` bar from 0 in `--accent`, a 1px zero rule, direct value labels on every row (there are ≤ 9 rows by construction: top 8 + Other), per-bar hover.

- [ ] **Step 1: Failing spec**

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Waterfall } from './waterfall';

describe('Waterfall', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('walks from zero through each step to the total', () => {
    const fixture = TestBed.createComponent(Waterfall);
    fixture.componentRef.setInput('steps', [
      { label: 'MACD', value: 4, n: 40 }, { label: 'RSI', value: -6, n: 30 }, { label: 'Other', value: 1, n: 12 },
    ]);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const bars = [...el.querySelectorAll('rect.bar')];
    expect(bars.length).toBe(4);                                  // 3 steps + total
    expect(bars[0].getAttribute('data-tone')).toBe('pos');
    expect(bars[1].getAttribute('data-tone')).toBe('neg');
    expect(bars[3].getAttribute('data-tone')).toBe('total');
    expect(fixture.componentInstance['runs']()).toEqual([[0, 4], [4, -2], [-2, -1], [0, -1]]);
    expect(el.textContent).toContain('-1.00');
  });
});
```

- [ ] **Step 2: Implement**

```ts
import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { CHART_CHROME } from './chart/chart-frame';
import { ChartTooltip, HoverState, hoverPosition } from './chart-tooltip';

export interface WaterfallStep { label: string; value: number; n?: number; }

const W = 320, ROW = 22, LABEL_W = 96, PAD = 8;

/** Who made and who lost the R (spec v94 D7): each step floats from the
 *  running total before it to the running total after it; the last bar is
 *  the book total from zero. Thin marks, 4px rounded ends, one axis. */
@Component({
  selector: 'sb-waterfall',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChartTooltip],
  template: `
    <div class="host" #host>
      <svg [attr.viewBox]="'0 0 ' + width + ' ' + height()" [attr.height]="height()" width="100%" role="img" aria-label="Contribution waterfall">
        <line class="zero" [attr.x1]="x(0)" [attr.x2]="x(0)" y1="0" [attr.y2]="height()" />
        @for (row of rows(); track row.label; let i = $index) {
          <text class="label" [attr.x]="labelW - 6" [attr.y]="i * rowH + rowH / 2 + 4" text-anchor="end">{{ row.label }}</text>
          <rect class="bar" rx="4" [attr.data-tone]="row.tone" [attr.x]="row.x" [attr.y]="i * rowH + 5" [attr.width]="row.w" height="12" tabindex="0"
                (pointermove)="show($event, row, host)" (focus)="show($event, row, host)" (pointerleave)="hover.set(null)" (blur)="hover.set(null)" />
          <text class="value num" [attr.x]="row.tx" [attr.y]="i * rowH + rowH / 2 + 4" [attr.text-anchor]="row.anchor">{{ format()(row.value) }}</text>
        }
      </svg>
      <sb-chart-tooltip [state]="hover()" [hostWidth]="host.clientWidth" />
    </div>
  `,
  styles: `
    .host { position: relative; }
    svg { display: block; overflow: visible; }
    .zero { stroke: var(${CHART_CHROME.axis}); stroke-width: 1; }
    .bar[data-tone='pos'] { fill: var(--pos); } .bar[data-tone='neg'] { fill: var(--neg); } .bar[data-tone='total'] { fill: var(--accent); }
    .bar:hover, .bar:focus-visible { filter: brightness(1.15); outline: none; }
    .label { fill: var(${CHART_CHROME.tickColour}); font-size: 11px; }
    .value { fill: var(--text); font-size: 11px; font-variant-numeric: tabular-nums; }
  `,
})
export class Waterfall {
  readonly steps = input.required<readonly WaterfallStep[]>();
  readonly format = input<(v: number) => string>((v) => v.toFixed(2));
  readonly totalLabel = input('Total');
  protected readonly width = W; protected readonly rowH = ROW; protected readonly labelW = LABEL_W;
  protected readonly hover = signal<HoverState | null>(null);

  /** [from, to] running totals per step, then [0, total]. */
  protected readonly runs = computed<[number, number][]>(() => {
    let run = 0; const out: [number, number][] = [];
    for (const s of this.steps()) { out.push([run, run + s.value]); run += s.value; }
    out.push([0, run]); return out;
  });
  private readonly domain = computed(() => {
    const vals = this.runs().flat(); return { min: Math.min(0, ...vals), max: Math.max(0, ...vals) };
  });
  protected readonly height = computed(() => (this.steps().length + 1) * ROW);
  protected x(v: number): number {
    const { min, max } = this.domain(); const span = max - min || 1;
    return LABEL_W + PAD + ((v - min) / span) * (W - LABEL_W - 2 * PAD);
  }
  protected readonly rows = computed(() => {
    const steps = [...this.steps(), { label: this.totalLabel(), value: this.runs().at(-1)![1] }];
    return steps.map((s, i) => {
      const [a, b] = this.runs()[i]; const x0 = this.x(Math.min(a, b)), x1 = this.x(Math.max(a, b));
      const tone = i === steps.length - 1 ? 'total' : s.value >= 0 ? 'pos' : 'neg';
      const right = b >= a;
      return { label: s.label, value: i === steps.length - 1 ? b : s.value, n: (s as WaterfallStep).n, tone,
               x: x0, w: Math.max(2, x1 - x0), tx: right ? x1 + 4 : x0 - 4, anchor: right ? 'start' : 'end' };
    });
  });
  protected show(ev: PointerEvent | FocusEvent, row: { label: string; value: number; n?: number }, host: HTMLElement): void {
    this.hover.set({ ...hoverPosition(ev, host), title: row.label,
      rows: [{ label: 'contribution', value: this.format()(row.value) }, ...(row.n != null ? [{ label: 'trades', value: String(row.n) }] : [])] });
  }
}
```

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/ui/waterfall.ts frontend/src/app/ui/waterfall.spec.ts
git commit -m "feat(v94): sb-waterfall -- contribution steps from zero to the book total"
```

---

### Task P6: `sb-dot-plot` (measure vs N, floor line)

**Files:**
- Create: `frontend/src/app/ui/dot-plot.ts`, `frontend/src/app/ui/dot-plot.spec.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface DotPoint { label: string; n: number; value: number | null }
  @Component({ selector: 'sb-dot-plot' }) class DotPlot {
    points = input.required<readonly DotPoint[]>(); floor = input.required<number>();
    yLabel = input('ExpR'); format = input<(v: number) => string>((v) => v.toFixed(2));
  }
  ```
  x = N on a log10 scale, y = value; a vertical dotted floor line at `floor`; points with `value === null` (server-nulled, H1) are drawn **hollow at y = 0** with a "withheld" title; a zero rule on y; each dot has a 24px transparent hit circle; a `<table class="sr-only">` view lists every point.

- [ ] **Step 1: Failing spec**

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { DotPlot } from './dot-plot';

describe('DotPlot', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('draws filled dots above the floor, hollow withheld dots below it, and 24px hit areas', () => {
    const fixture = TestBed.createComponent(DotPlot);
    fixture.componentRef.setInput('points', [
      { label: 'MACD', n: 140, value: 0.2 }, { label: 'VP', n: 9, value: null },
    ]);
    fixture.componentRef.setInput('floor', 20);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const dots = [...el.querySelectorAll('circle.dot')];
    expect(dots[0].classList.contains('withheld')).toBe(false);
    expect(dots[1].classList.contains('withheld')).toBe(true);
    expect([...el.querySelectorAll('circle.hit')].every((c) => c.getAttribute('r') === '12')).toBe(true);
    expect(el.querySelector('line.floor')).not.toBeNull();
    expect(el.querySelector('table')!.textContent).toContain('withheld');
  });
});
```

- [ ] **Step 2: Implement**

```ts
import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { CHART_CHROME } from './chart/chart-frame';
import { ChartTooltip, HoverState, hoverPosition } from './chart-tooltip';

export interface DotPoint { label: string; n: number; value: number | null; }

const W = 320, H = 180, PAD = { l: 36, r: 12, t: 8, b: 22 };

/** The honesty instrument (spec v94 D7): every cell of a dimension as one
 *  dot, sample size on a log axis, the floor drawn on screen. A cell the
 *  server withheld (H1) is a hollow dot on the zero line -- present, counted,
 *  never coloured as a result. */
@Component({
  selector: 'sb-dot-plot',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChartTooltip],
  template: `
    <div class="host" #host>
      <svg [attr.viewBox]="'0 0 ' + w + ' ' + h" width="100%" [attr.height]="h" role="img" [attr.aria-label]="yLabel() + ' against sample size'">
        <line class="axis" [attr.x1]="pad.l" [attr.x2]="w - pad.r" [attr.y1]="y(0)" [attr.y2]="y(0)" />
        <line class="floor" [attr.x1]="x(floor())" [attr.x2]="x(floor())" [attr.y1]="pad.t" [attr.y2]="h - pad.b" />
        <text class="tick" [attr.x]="x(floor()) + 3" [attr.y]="pad.t + 9">N={{ floor() }}</text>
        @for (t of xTicks(); track t) { <text class="tick" [attr.x]="x(t)" [attr.y]="h - 6" text-anchor="middle">{{ t }}</text> }
        @for (p of points(); track p.label) {
          <circle class="dot" [class.withheld]="p.value === null" [attr.cx]="x(p.n)" [attr.cy]="y(p.value ?? 0)" r="4" />
          <circle class="hit" [attr.cx]="x(p.n)" [attr.cy]="y(p.value ?? 0)" r="12" tabindex="0"
                  (pointermove)="show($event, p, host)" (focus)="show($event, p, host)" (pointerleave)="hover.set(null)" (blur)="hover.set(null)" />
        }
      </svg>
      <table class="sr-only"><caption>{{ yLabel() }} by sample size</caption>
        @for (p of points(); track p.label) { <tr><th scope="row">{{ p.label }}</th><td>N={{ p.n }}</td><td>{{ p.value === null ? 'withheld (below floor)' : format()(p.value) }}</td></tr> }
      </table>
      <sb-chart-tooltip [state]="hover()" [hostWidth]="host.clientWidth" />
    </div>
  `,
  styles: `
    .host { position: relative; }
    svg { display: block; }
    .axis { stroke: var(${CHART_CHROME.axis}); stroke-width: 1; }
    .floor { stroke: var(--text-faint); stroke-width: 1; stroke-dasharray: 2 3; }
    .tick { fill: var(${CHART_CHROME.tickColour}); font-size: 10px; }
    .dot { fill: var(--accent); }
    .dot.withheld { fill: none; stroke: var(--text-faint); stroke-width: 1.5; }
    .hit { fill: transparent; outline: none; }
    .hit:hover + .dot, .hit:focus-visible ~ .dot { filter: brightness(1.2); }
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  `,
})
export class DotPlot {
  readonly points = input.required<readonly DotPoint[]>();
  readonly floor = input.required<number>();
  readonly yLabel = input('ExpR');
  readonly format = input<(v: number) => string>((v) => v.toFixed(2));
  protected readonly w = W; protected readonly h = H; protected readonly pad = PAD;
  protected readonly hover = signal<HoverState | null>(null);

  private readonly xMax = computed(() => Math.max(this.floor() * 2, ...this.points().map((p) => p.n), 10));
  private readonly yAbs = computed(() => Math.max(0.5, ...this.points().map((p) => Math.abs(p.value ?? 0))));
  protected x(n: number): number {
    const lo = 0, hi = Math.log10(this.xMax());
    return PAD.l + ((Math.log10(Math.max(1, n)) - lo) / (hi - lo || 1)) * (W - PAD.l - PAD.r);
  }
  protected y(v: number): number {
    const a = this.yAbs(); return PAD.t + ((a - v) / (2 * a)) * (H - PAD.t - PAD.b);
  }
  protected readonly xTicks = computed(() => [1, 10, 100, 1000].filter((t) => t <= this.xMax()));
  protected show(ev: PointerEvent | FocusEvent, p: DotPoint, host: HTMLElement): void {
    this.hover.set({ ...hoverPosition(ev, host), title: p.label, rows: [
      { label: this.yLabel(), value: p.value === null ? 'withheld' : this.format()(p.value) },
      { label: 'trades', value: String(p.n) },
    ] });
  }
}
```

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/ui/dot-plot.ts frontend/src/app/ui/dot-plot.spec.ts
git commit -m "feat(v94): sb-dot-plot -- measure against N with the floor on screen"
```

---

### Task P7: `sb-strip-plot` (groups with medians)

**Files:**
- Create: `frontend/src/app/ui/strip-plot.ts`, `frontend/src/app/ui/strip-plot.spec.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface StripGroup { label: string; values: readonly number[]; tone?: 'pos' | 'neg' | 'accent' }
  @Component({ selector: 'sb-strip-plot' }) class StripPlot {
    groups = input.required<readonly StripGroup[]>(); unit = input('d'); format = input<(v: number) => string>((v) => v.toFixed(2));
  }
  export function median(values: readonly number[]): number | null
  ```
  One row per group; each value a 2px-wide tick jittered ±4px vertically for legibility; a 2px median bar in `--text`; shared x-axis across groups (linear, from 0 to the max); label with `N=` and the median in text; per-tick hover.

- [ ] **Step 1: Failing spec**

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { StripPlot, median } from './strip-plot';

describe('StripPlot', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('median of even and odd lists, null for empty', () => {
    expect(median([3, 1, 2])).toBe(2); expect(median([1, 2, 3, 4])).toBe(2.5); expect(median([])).toBeNull();
  });

  it('draws a tick per value and a median bar per group on a shared axis', () => {
    const fixture = TestBed.createComponent(StripPlot);
    fixture.componentRef.setInput('groups', [
      { label: 'Winners', values: [0.2, 0.3, 0.4], tone: 'pos' }, { label: 'Losers', values: [0.6, 0.8], tone: 'neg' },
    ]);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('line.tick').length).toBe(5);
    expect(el.querySelectorAll('line.median').length).toBe(2);
    expect(el.textContent).toContain('N=3');
    expect(el.textContent).toContain('median 0.30d');
  });
});
```

- [ ] **Step 2: Implement**

```ts
import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { CHART_CHROME } from './chart/chart-frame';
import { ChartTooltip, HoverState, hoverPosition } from './chart-tooltip';

export interface StripGroup { label: string; values: readonly number[]; tone?: 'pos' | 'neg' | 'accent'; }

export function median(values: readonly number[]): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b); const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

const W = 320, ROW = 34, LABEL_W = 110, PAD = 8;

/** The disposition effect is a shape, not a sentence (spec v94 D8): every
 *  hold as a tick, winners and losers as two rows on one axis, the median
 *  as the only heavy mark. */
@Component({
  selector: 'sb-strip-plot',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChartTooltip],
  template: `
    <div class="host" #host>
      <svg [attr.viewBox]="'0 0 ' + w + ' ' + height()" width="100%" [attr.height]="height()" role="img" aria-label="Distribution by group">
        @for (g of rows(); track g.label; let i = $index) {
          <text class="label" [attr.x]="labelW - 6" [attr.y]="i * rowH + 14" text-anchor="end">{{ g.label }}</text>
          <text class="sub" [attr.x]="labelW - 6" [attr.y]="i * rowH + 27" text-anchor="end">N={{ g.values.length }}@if (g.median !== null) { · median {{ format()(g.median) }}{{ unit() }}}</text>
          <line class="base" [attr.x1]="labelW" [attr.x2]="w - pad" [attr.y1]="i * rowH + 20" [attr.y2]="i * rowH + 20" />
          @for (v of g.values; track $index; let j = $index) {
            <line class="tick" [attr.data-tone]="g.tone ?? 'accent'" [attr.x1]="x(v)" [attr.x2]="x(v)"
                  [attr.y1]="i * rowH + 12 + jitter(j)" [attr.y2]="i * rowH + 28 + jitter(j)" tabindex="0"
                  (pointermove)="show($event, g.label, v, host)" (focus)="show($event, g.label, v, host)" (pointerleave)="hover.set(null)" (blur)="hover.set(null)" />
          }
          @if (g.median !== null) { <line class="median" [attr.x1]="x(g.median)" [attr.x2]="x(g.median)" [attr.y1]="i * rowH + 6" [attr.y2]="i * rowH + 34" /> }
        }
      </svg>
      <sb-chart-tooltip [state]="hover()" [hostWidth]="host.clientWidth" />
    </div>
  `,
  styles: `
    .host { position: relative; } svg { display: block; }
    .label { fill: var(--text); font-size: 11px; } .sub { fill: var(${CHART_CHROME.tickColour}); font-size: 10px; }
    .base { stroke: var(${CHART_CHROME.grid}); stroke-width: 1; }
    .tick { stroke-width: 2; opacity: .7; outline: none; }
    .tick[data-tone='pos'] { stroke: var(--pos); } .tick[data-tone='neg'] { stroke: var(--neg); } .tick[data-tone='accent'] { stroke: var(--accent); }
    .tick:hover, .tick:focus-visible { opacity: 1; stroke-width: 3; }
    .median { stroke: var(--text); stroke-width: 2; }
  `,
})
export class StripPlot {
  readonly groups = input.required<readonly StripGroup[]>();
  readonly unit = input('d');
  readonly format = input<(v: number) => string>((v) => v.toFixed(2));
  protected readonly w = W; protected readonly rowH = ROW; protected readonly labelW = LABEL_W; protected readonly pad = PAD;
  protected readonly hover = signal<HoverState | null>(null);
  protected readonly height = computed(() => Math.max(1, this.groups().length) * ROW + 6);
  private readonly max = computed(() => Math.max(0.01, ...this.groups().flatMap((g) => g.values)));
  protected x(v: number): number { return LABEL_W + (v / this.max()) * (W - LABEL_W - PAD); }
  protected jitter(j: number): number { return ((j * 7) % 9) - 4; }          // deterministic ±4px
  protected readonly rows = computed(() => this.groups().map((g) => ({ ...g, median: median(g.values) })));
  protected show(ev: PointerEvent | FocusEvent, group: string, v: number, host: HTMLElement): void {
    this.hover.set({ ...hoverPosition(ev, host), title: group, rows: [{ label: 'held', value: `${this.format()(v)}${this.unit()}` }] });
  }
}
```

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/ui/strip-plot.ts frontend/src/app/ui/strip-plot.spec.ts
git commit -m "feat(v94): sb-strip-plot -- one tick per observation, medians on a shared axis"
```

---

### Task P8: `sb-small-multiples` (shared y over `sb-line-chart`)

**Files:**
- Create: `frontend/src/app/ui/small-multiples.ts`, `frontend/src/app/ui/small-multiples.spec.ts`

**Interfaces:**
- Consumes: `LineChart` (`series`, `yDomain`, `referenceLine`, `valueFormat` inputs; `LineChartSeries {name, points: {date, value}[]}`).
- Produces:
  ```ts
  export interface MultiplePane { title: string; series: LineChartSeries[]; n?: number }
  @Component({ selector: 'sb-small-multiples' }) class SmallMultiples {
    panes = input.required<readonly MultiplePane[]>(); referenceLine = input<number | null>(0); valueFormat = input<(v: number) => string>((v) => v.toFixed(2));
    sharedDomain = computed<{min:number;max:number}>()   // min/max over every pane, padded 5%
  }
  ```
  A responsive grid (`repeat(auto-fill, minmax(180px, 1fr))`); every pane passes the same `yDomain` so a flat pane reads as flat (spec D9).

- [ ] **Step 1: Failing spec**

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { SmallMultiples } from './small-multiples';

describe('SmallMultiples', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('shares one y-domain across panes and titles each with N', () => {
    const fixture = TestBed.createComponent(SmallMultiples);
    fixture.componentRef.setInput('panes', [
      { title: 'MACD', n: 40, series: [{ name: 'MACD', points: [{ date: '2026-08-01', value: 0 }, { date: '2026-08-02', value: 8 }] }] },
      { title: 'RSI', n: 12, series: [{ name: 'RSI', points: [{ date: '2026-08-01', value: 0 }, { date: '2026-08-02', value: -2 }] }] },
    ]);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('sb-line-chart').length).toBe(2);
    expect(fixture.componentInstance.sharedDomain()).toEqual({ min: -2.5, max: 8.5 });
    expect(el.textContent).toContain('MACD');
    expect(el.textContent).toContain('N=12');
  });
});
```

- [ ] **Step 2: Implement**

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { LineChart, LineChartSeries } from './line-chart';

export interface MultiplePane { title: string; series: LineChartSeries[]; n?: number; }

/** Cumulative R per strategy as small multiples, never one twelve-line
 *  chart (spec v94 D9). One y-domain for every pane so a flat pane reads as
 *  flat and a steep one as steep. */
@Component({
  selector: 'sb-small-multiples',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LineChart],
  template: `
    <div class="grid">
      @for (pane of panes(); track pane.title) {
        <figure class="pane">
          <figcaption><span class="title">{{ pane.title }}</span>@if (pane.n != null) { <span class="n num">N={{ pane.n }}</span> }</figcaption>
          <sb-line-chart [series]="pane.series" [yDomain]="sharedDomain()" [referenceLine]="referenceLine()" [valueFormat]="valueFormat()" />
        </figure>
      }
    </div>
  `,
  styles: `
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: var(--space-14); }
    .pane { margin: 0; }
    figcaption { display: flex; justify-content: space-between; font-size: var(--text-chip); margin-bottom: 2px; }
    .title { color: var(--text); } .n { color: var(--text-faint); font-variant-numeric: tabular-nums; }
    sb-line-chart { display: block; height: 96px; }
  `,
})
export class SmallMultiples {
  readonly panes = input.required<readonly MultiplePane[]>();
  readonly referenceLine = input<number | null>(0);
  readonly valueFormat = input<(v: number) => string>((v) => v.toFixed(2));
  readonly sharedDomain = computed(() => {
    const values = this.panes().flatMap((p) => p.series.flatMap((s) => s.points.map((pt) => pt.value)));
    if (!values.length) return { min: -1, max: 1 };
    const min = Math.min(0, ...values), max = Math.max(0, ...values), pad = (max - min || 1) * 0.05;
    return { min: min - pad, max: max + pad };
  });
}
```

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/ui/small-multiples.ts frontend/src/app/ui/small-multiples.spec.ts
git commit -m "feat(v94): sb-small-multiples -- one shared y-domain over sb-line-chart panes"
```

---

### Task P9: `sb-heat-grid` (floor-aware cells) + per-mark hover on `sb-histogram` and `sb-bar-list`

**Files:**
- Create: `frontend/src/app/ui/heat-grid.ts`, `frontend/src/app/ui/heat-grid.spec.ts`
- Modify: `frontend/src/app/ui/histogram.ts` (template L37–52, class), `frontend/src/app/ui/histogram.spec.ts`
- Modify: `frontend/src/app/ui/bar-list.ts` (template; class), `frontend/src/app/ui/bar-list.spec.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface HeatCell { r: number; c: number; n: number; value: number | null }
  export type HeatRamp = 'diverging' | 'sequential';
  @Component({ selector: 'sb-heat-grid' }) class HeatGrid {
    rows = input.required<readonly string[]>(); cols = input.required<readonly string[]>(); cells = input.required<readonly HeatCell[]>();
    ramp = input<HeatRamp>('diverging'); format = input<(v: number) => string>((v) => v.toFixed(2)); floor = input<number>(20);
    foldedRow = input<{ label: string; cells: readonly Omit<HeatCell, 'r'>[] } | null>(null);
  }
  ```
  Cells with `value === null` render blank with their N in `--text-faint` and a dotted outline (H1). Diverging ramp: `--neg` ← `--surface` → `--pos` via `color-mix` at 5 steps centred on 0; sequential: `--surface` → `--accent` at 5 steps. Every cell is a hover/focus target; a Table view is the grid itself (it is a `<table>`).
- `sb-histogram` and `sb-bar-list` each gain a `<sb-chart-tooltip>` and per-row `pointermove`/`focus` handlers showing `label · count` (histogram) and `label · value · N` (bar list). No input changes.

- [ ] **Step 1: Failing specs**

`heat-grid.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { HeatGrid } from './heat-grid';

describe('HeatGrid', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('blanks withheld cells with their N and colours the rest by step', () => {
    const fixture = TestBed.createComponent(HeatGrid);
    fixture.componentRef.setInput('rows', ['MACD']);
    fixture.componentRef.setInput('cols', ['2w', '1m']);
    fixture.componentRef.setInput('cells', [{ r: 0, c: 0, n: 3, value: null }, { r: 0, c: 1, n: 40, value: 0.3 }]);
    fixture.componentRef.setInput('foldedRow', { label: 'Other (5)', cells: [{ c: 0, n: 7, value: null }, { c: 1, n: 2, value: null }] });
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const tds = [...el.querySelectorAll('td')];
    expect(tds[0].classList.contains('withheld')).toBe(true);
    expect(tds[0].textContent!.trim()).toBe('n=3');
    expect(tds[1].getAttribute('data-step')).toBe('p2');
    expect(el.querySelectorAll('tbody tr').length).toBe(2);
    expect(el.textContent).toContain('Other (5)');
  });
});
```

`histogram.spec.ts` append (inside `describe('Histogram')`, using its `render`):

```ts
  it('shows a tooltip for the hovered bin', () => {
    const element = render([{ label: '0.0R', count: 9 }]);
    element.querySelector('li')!.dispatchEvent(new PointerEvent('pointermove', { clientX: 5, clientY: 5 }));
    // OnPush: read the tooltip after a change-detection pass
    const fixture = (element as any).__ngContext__ ? null : null;
    expect(element.querySelector('li')!.getAttribute('tabindex')).toBe('0');
  });
```

(If reading the rendered tooltip needs the fixture, restructure `render` to return `{ fixture, element }` and call `fixture.detectChanges()` after dispatch; assert `element.querySelector('.tooltip .value')!.textContent === '9'`.) `bar-list.spec.ts`: same shape — dispatch `pointermove` on the first `li`, `detectChanges()`, assert the tooltip's `.value` equals the row's `text`.

- [ ] **Step 2: Implement `heat-grid.ts`**

```ts
import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { ChartTooltip, HoverState, hoverPosition } from './chart-tooltip';

export interface HeatCell { r: number; c: number; n: number; value: number | null; }
export type HeatRamp = 'diverging' | 'sequential';

/** Strategy x horizon as a grid that can be read (spec v94 D7/H1). A cell
 *  under the floor is blank with its N and a dotted outline -- present, never
 *  coloured. Diverging ramp centred on zero for ExpR; one hue for rates/N. */
@Component({
  selector: 'sb-heat-grid',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChartTooltip],
  template: `
    <div class="host scroll-x" #host>
      <table>
        <thead><tr><th scope="col"></th>@for (c of cols(); track c) { <th scope="col">{{ c }}</th> }</tr></thead>
        <tbody>
          @for (row of rows(); track row; let r = $index) {
            <tr><th scope="row">{{ row }}</th>
              @for (c of cols(); track c; let ci = $index) {
                @let cell = at(r, ci);
                <td [class.withheld]="cell?.value == null" [attr.data-step]="step(cell?.value ?? null)" tabindex="0"
                    (pointermove)="show($event, row, c, cell, host)" (focus)="show($event, row, c, cell, host)"
                    (pointerleave)="hover.set(null)" (blur)="hover.set(null)">
                  @if (cell?.value != null) { {{ format()(cell!.value!) }} } @else { <span class="n">n={{ cell?.n ?? 0 }}</span> }
                </td>
              }
            </tr>
          }
          @if (foldedRow(); as f) {
            <tr class="folded"><th scope="row">{{ f.label }}</th>
              @for (cell of f.cells; track cell.c) {
                <td [class.withheld]="cell.value == null" [attr.data-step]="step(cell.value)" tabindex="0"
                    (pointermove)="show($event, f.label, cols()[cell.c], cell, host)" (focus)="show($event, f.label, cols()[cell.c], cell, host)"
                    (pointerleave)="hover.set(null)" (blur)="hover.set(null)">
                  @if (cell.value != null) { {{ format()(cell.value) }} } @else { <span class="n">n={{ cell.n }}</span> }
                </td>
              }
            </tr>
          }
        </tbody>
      </table>
      <sb-chart-tooltip [state]="hover()" [hostWidth]="host.clientWidth" />
    </div>
  `,
  styles: `
    .host { position: relative; } .scroll-x { overflow-x: auto; }
    table { border-collapse: separate; border-spacing: 2px; width: 100%; }
    th { font-size: var(--text-micro); text-transform: uppercase; letter-spacing: .08em; color: var(--text-faint); font-weight: 400; text-align: right; padding: 2px 6px; white-space: nowrap; }
    td { font-size: var(--text-micro); font-variant-numeric: tabular-nums; text-align: right; padding: 4px 6px; color: var(--text); border-radius: 2px; outline: none; }
    td:hover, td:focus-visible { box-shadow: inset 0 0 0 1px var(--accent); }
    td.withheld { background: none; outline: 1px dotted var(--border-strong); outline-offset: -1px; }
    .n { color: var(--text-faint); }
    td[data-step='n2'] { background: color-mix(in oklab, var(--neg) 70%, var(--surface)); }
    td[data-step='n1'] { background: color-mix(in oklab, var(--neg) 35%, var(--surface)); }
    td[data-step='z']  { background: var(--surface-raised); }
    td[data-step='p1'] { background: color-mix(in oklab, var(--pos) 35%, var(--surface)); }
    td[data-step='p2'] { background: color-mix(in oklab, var(--pos) 70%, var(--surface)); }
    td[data-step='s1'] { background: color-mix(in oklab, var(--accent) 15%, var(--surface)); }
    td[data-step='s2'] { background: color-mix(in oklab, var(--accent) 30%, var(--surface)); }
    td[data-step='s3'] { background: color-mix(in oklab, var(--accent) 50%, var(--surface)); }
    td[data-step='s4'] { background: color-mix(in oklab, var(--accent) 70%, var(--surface)); }
    td[data-step='s5'] { background: color-mix(in oklab, var(--accent) 90%, var(--surface)); color: var(--on-accent); }
    tr.folded th { font-style: italic; }
  `,
})
export class HeatGrid {
  readonly rows = input.required<readonly string[]>();
  readonly cols = input.required<readonly string[]>();
  readonly cells = input.required<readonly HeatCell[]>();
  readonly ramp = input<HeatRamp>('diverging');
  readonly format = input<(v: number) => string>((v) => v.toFixed(2));
  readonly floor = input<number>(20);
  readonly foldedRow = input<{ label: string; cells: readonly Omit<HeatCell, 'r'>[] } | null>(null);
  protected readonly hover = signal<HoverState | null>(null);

  private readonly index = computed(() => { const m = new Map<string, HeatCell>(); for (const c of this.cells()) m.set(`${c.r}:${c.c}`, c); return m; });
  private readonly absMax = computed(() => Math.max(0.01, ...this.cells().map((c) => Math.abs(c.value ?? 0)),
    ...(this.foldedRow()?.cells.map((c) => Math.abs(c.value ?? 0)) ?? [])));
  protected at(r: number, c: number): HeatCell | undefined { return this.index().get(`${r}:${c}`); }
  /** Five steps. Diverging: n2 n1 z p1 p2 around 0. Sequential: s1..s5 over [0, max]. */
  protected step(v: number | null): string | null {
    if (v === null) return null;
    const t = v / this.absMax();
    if (this.ramp() === 'diverging') return t <= -0.5 ? 'n2' : t < -0.1 ? 'n1' : t <= 0.1 ? 'z' : t < 0.5 ? 'p1' : 'p2';
    return 's' + Math.min(5, Math.max(1, Math.ceil(Math.abs(t) * 5)));
  }
  protected show(ev: PointerEvent | FocusEvent, row: string, col: string, cell: Omit<HeatCell, 'r'> | undefined, host: HTMLElement): void {
    this.hover.set({ ...hoverPosition(ev, host), title: `${row} · ${col}`, rows: [
      { label: 'value', value: cell?.value == null ? `withheld (n<${this.floor()})` : this.format()(cell.value) },
      { label: 'trades', value: String(cell?.n ?? 0) },
    ] });
  }
}
```

- [ ] **Step 3: Hover on `histogram.ts`** — import `ChartTooltip, HoverState, hoverPosition`; add `imports: [ChartTooltip]`; wrap `.wrap` in `<div class="host" #host style="position:relative">`; on each `<li>` add `tabindex="0" (pointermove)="show($event, bin, host)" (focus)="show($event, bin, host)" (pointerleave)="hover.set(null)" (blur)="hover.set(null)"`; append `<sb-chart-tooltip [state]="hover()" [hostWidth]="host.clientWidth" />`; class: `protected readonly hover = signal<HoverState | null>(null); protected show(ev, bin, host) { this.hover.set({ ...hoverPosition(ev, host), title: bin.label, rows: [{ label: 'observations', value: String(bin.count) }] }); }`. Add `li:hover .fill, li:focus-within .fill { filter: brightness(1.15); } li { outline: none; }`.

- [ ] **Step 4: Hover on `bar-list.ts`** — same pattern; tooltip rows `[{ label: row.label, value: row.text }, { label: 'trades', value: nText(row) }]`.

- [ ] **Step 5: Run the three specs → PASS. Commit**

```bash
git add frontend/src/app/ui/heat-grid.ts frontend/src/app/ui/heat-grid.spec.ts frontend/src/app/ui/histogram.ts frontend/src/app/ui/histogram.spec.ts frontend/src/app/ui/bar-list.ts frontend/src/app/ui/bar-list.spec.ts
git commit -m "feat(v94): sb-heat-grid with blank thin cells; per-mark hover on histogram and bar list"
```

---

### Task P10: Palette validation of `--chart-1…6` in both themes

**Files:**
- Modify (only if a check fails): `frontend/src/styles/tokens.css` (`--chart-1…6`, L162–167 and the light-theme block's counterparts)
- Modify: `frontend/src/app/ui/tokens.spec.ts` (pin the six values exist in both themes)

**Interfaces:** none. Produces a validator report in the commit body.

- [ ] **Step 1: Locate the validator** — it ships with the `dataviz` skill: `ls "$(dirname "$(find / -path '*dataviz/scripts/validate_palette.js' 2>/dev/null | head -1)")"` on POSIX, or on this machine `C:/Users/HuyCao/AppData/Local/Temp/claude/bundled-skills/*/dataviz/scripts/validate_palette.js`. If absent, invoke the `dataviz` skill once to materialise it.

- [ ] **Step 2: Read the six dark values and the dark surface** — `grep -n -E "^\s*--(chart-[1-6]|surface):" frontend/src/styles/tokens.css` (first block = dark). Run:

```bash
node <path>/validate_palette.js "#4c8dff,#c97a22,#a868e0,#b08c14,#1a9db3,#7076e8" --mode dark --surface "#131722"
```

Then the light block's values with `--mode light --surface <light --surface>`. (Pass `--help` first if the flag names differ; the skill's `SKILL.md` documents them.)

- [ ] **Step 3: Fix any FAIL** by re-stepping the failing token in `tokens.css` to the nearest passing value the validator suggests, re-run until every check passes in both modes. A contrast WARN is acceptable **only** because every chart here direct-labels or has a Table view (P2/P9); note that in the commit body.

- [ ] **Step 4: Pin in `tokens.spec.ts`** — add a test that both theme blocks define `--chart-1` … `--chart-6` (read `tokens.css` with `readFileSync`, regex `--chart-(\d):` per block, expect 6 in each).

- [ ] **Step 5: Verify** — `cd frontend && npm test -- --include src/app/ui/tokens.spec.ts` → PASS. Commit with the validator output pasted:

```bash
git add frontend/src/styles/tokens.css frontend/src/app/ui/tokens.spec.ts
git commit -m "chore(v94): validate --chart-1..6 against both surfaces (dataviz six checks)" -m "<paste console.table output for dark and light here>"
```
