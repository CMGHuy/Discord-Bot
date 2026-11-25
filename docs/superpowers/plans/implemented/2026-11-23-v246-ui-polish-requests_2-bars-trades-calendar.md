# v246 — UI polish, Plan A of five: requests — Part 2: segmented phone rule, flex-end bars, Trades and Calendar

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V246-7" -A 400 <this file>`).

**Spec:** [2026-11-23-v246-ui-polish-filters-charts-interactions-design.md](../specs/2026-11-23-v246-ui-polish-filters-charts-interactions-design.md) §A2 ("The bars that exist", "Control height", "Toggle groups", "Phone", the Trades and Calendar consumers) and the A rows of "Three devices" and "Testing".
**Index:** [2026-11-23-v246-ui-polish-requests_0-index.md](2026-11-23-v246-ui-polish-requests_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and the binding `## Handoff` decisions live there; every task below implicitly includes them.

Tasks: V246-5 (`sb-segmented` takes the full row on a phone), V246-6 (two bars align on the bottom edge, `sb-control-row` gains the opt-in), V246-7 (Trades toolbar wrapped in `sb-field`, Density segmented), V246-8 (Calendar month row wrapped in `sb-field`, Show segmented).

Order: V246-5 and V246-6 touch disjoint files and may run in either order once Part 1 (V246-3, V246-4) is merged; V246-7 and V246-8 need all four (`sb-field`, the label drop, the date-range field, the segmented phone rule, the flex-end bars and the `sb-control-row` opt-in). V246-8 also runs after **V247-3** (it edits `calendar.ts` / `calendar.spec.ts` links) and V246-5 after **V247-3 / V247-8** (both edit `ui/hit-area.spec.ts`): rebase onto them, never over them. All frontend commands run from the worktree root with `cd frontend &&`; `--include` paths are relative to `frontend/`.

Contracts from Part 1 these tasks rely on (do not restate them in code, import them):
- `Field` (`sb-field`, `frontend/src/app/ui/field.ts`): inputs `label` (`''` → `aria-hidden` filler line), `size: 's' | 'm' | 'l' | 'auto'` (default `'m'`), `fullRow`; host `data-size`, classes `no-label`, `full-row`; caption `.sb-label.field-label`, always `aria-hidden="true"`; sets `--sb-control-w` (`--field-s/m/l` = 136/176/240px; `100%` below 640px except `auto`).
- `sb-select` / `sb-text-input` inside a field draw no `.sb-label`, carry host class `in-field`, and name themselves own `label` → `ariaLabel` → field label.
- A date range is written `<sb-field label="..." size="auto" [fullRow]="true"><sb-date-range … /></sb-field>`; its inputs are then named `"<label> from"` / `"<label> to"`.
- In `sb-toolbar` the `sb-field`, not the control, carries `slot="<id>"` (brief Trap 3).

---

# Phase 3 — The bars

### Task V246-5: `sb-segmented` in a bar: 3+ options take the full row below 640px, equal segments, never wrap

**Model:** sonnet — one computed signal, a host class and a phone CSS block on a 42-line shared control, pinned by CSS-source specs; the rule is spelled out below.

**Files:**
- Modify: `frontend/src/app/ui/segmented.ts` (whole file, 42 lines)
- Modify: `frontend/src/app/ui/segmented.spec.ts` (one added `describe` at the end)
- Modify: `frontend/src/app/ui/hit-area.spec.ts` (two rows in the `GROWN` table of `describe('v179: controls that grow to the hit size', …)`, after the existing `segmented.ts` row)

**Interfaces:**
- Consumes: `--control-h`, `--hit-min`, `--space-6` (`styles/tokens.css`).
- Produces (consumed by V246-8, V246-9, V246-10): `Segmented.many: Signal<boolean>` (`options().length >= 3`), reflected as host class `many`. Below 640px a `many` group fills its row (`:host(.many) { width: 100% }`), the track is a full-width flex row and every segment takes an equal share (`flex: 1 1 0`) without dropping under `--hit-min`; the track never wraps (no `flex-wrap`), so a too-narrow row scrolls (the existing `overflow-x: auto`) instead of breaking onto a second line. Two-option groups keep their natural width everywhere.

**Why.** Spec §A2 "Phone": "A segmented group with 3 or more options takes the full row, splits it into equal segments, and never wraps." Today `.track` is `inline-flex` and `.segment` is `flex: 0 0 auto`, so at 390 Calendar's €/R/Trades/Win rate switch and the Dashboard's 1H/4H/1D/1W sit at their text width beside whatever else fits, ragged against the full-width selects stacked around them. The rule lives in the component, not in each consumer, so every 3+ option group (Calendar "Show", Analytics "Units", Dashboard "Interval") gets it at once; a two-option group (Trades "Density", Dashboard "Trades") keeps its natural width, which already fits a phone cell. The field around the group (`<sb-field … size="auto" [fullRow]="true">`, V246-3) supplies the full row in the bar and drops its empty label filler there; this task makes the group fill the row it is given. Touch: `min-height: var(--control-h)` (44px below 1024px) is already on `.segment`, and the equal share keeps `min-width: var(--hit-min)`, so no segment shrinks under the 44px target (spec "Three devices").

- [ ] **Step 1: Write the failing segmented spec**

Append to the end of `frontend/src/app/ui/segmented.spec.ts`:

```ts
/* v246 §A2 "Phone": a group of three or more options takes the full row
 * below 640px, split into equal segments that never wrap. Two options keep
 * their natural width. jsdom resolves no media query, so the phone rule is
 * read from source (the pattern of control-bar.spec.ts). */
const TWO: SegmentOption[] = [{ value: 'compact', label: 'Compact' }, { value: 'full', label: 'Full' }];
@Component({ imports: [Segmented], template: `<sb-segmented label="Density" [options]="options()" [(value)]="value" />` })
class SizedHost { readonly options = signal<SegmentOption[]>(TWO); readonly value = signal('compact'); }

describe('Segmented on a phone (v246 §A2)', () => {
  beforeEach(() => { TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }); });

  const PHONE = SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';
  const phoneRule = (selector: string) =>
    PHONE.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{[^}]*\\}`))?.[0] ?? '';

  function mount(options: SegmentOption[]) {
    const f = TestBed.createComponent(SizedHost);
    f.componentInstance.options.set(options);
    f.detectChanges();
    const debug = f.debugElement.query((d) => d.name === 'sb-segmented');
    return { f, host: debug.nativeElement as HTMLElement, segmented: debug.componentInstance as Segmented };
  }

  it('marks a group of three or more options as many', () => {
    const { host, segmented } = mount(OPTIONS);
    expect(segmented.many()).toBe(true);
    expect(host.classList).toContain('many');
  });

  it('leaves a two-option group at its natural width', () => {
    const { host, segmented } = mount(TWO);
    expect(segmented.many()).toBe(false);
    expect(host.classList).not.toContain('many');
  });

  it('follows the options: a group that grows to three becomes many', () => {
    const { f, host } = mount(TWO);
    f.componentInstance.options.set([...TWO, { value: 'roomy', label: 'Roomy' }]);
    f.detectChanges();
    expect(host.classList).toContain('many');
  });

  it('stretches a many group across its row below 640px, and only there', () => {
    expect(phoneRule(':host(.many)')).toContain('width: 100%');
    expect(phoneRule(':host(.many) .track')).toContain('display: flex');
    expect(phoneRule(':host(.many) .track')).toContain('width: 100%');
    // Outside the phone block the track stays inline-flex at its natural width.
    expect(SOURCE).toMatch(/\n {4}\.track \{ display: inline-flex;/);
  });

  it('splits the row into equal segments that keep the touch target', () => {
    const segment = phoneRule(':host(.many) .segment');
    expect(segment).toContain('flex: 1 1 0');
    expect(segment).toContain('min-width: var(--hit-min)');
    expect(SOURCE).toMatch(/\.segment \{[^}]*min-height: var\(--control-h\)/);
  });

  it('never wraps: a row too narrow for every option scrolls instead', () => {
    expect(SOURCE).not.toMatch(/flex-wrap:\s*wrap/);
    expect(SOURCE).toMatch(/\.track \{[^}]*overflow-x: auto/);
    expect(SOURCE).toMatch(/\.segment \{[^}]*white-space: nowrap/);
  });

  it('declares the phone block at 639px, not one pixel into tablet', () => {
    expect(SOURCE).toContain('@media (max-width: 639px)');
    expect(SOURCE).not.toContain('max-width: 640px');
  });
});
```

No import changes: line 1 already imports `readFileSync` / `join`; line 2 imports `Component`, `provideZonelessChangeDetection`, `signal`, `TestBed`, `beforeEach`, `describe`, `expect`, `it`; line 3 imports `SegmentOption, Segmented`; `SOURCE` and `OPTIONS` (three options) are the module constants at lines 4-5.

- [ ] **Step 2: Add the hit-area rows**

In `frontend/src/app/ui/hit-area.spec.ts`, in the `GROWN` table, directly after the row `['src/app/ui/segmented.ts', '.segment', 'min-width: var(--hit-min)'],` add:

```ts
    // v246 §A2: every option is one control tall (44px below 1024px), and the
    // equal phone segments of a 3+ option group never shrink under the target.
    ['src/app/ui/segmented.ts', '.segment', 'min-height: var(--control-h)'],
    ['src/app/ui/segmented.ts', ':host(.many) .segment', 'min-width: var(--hit-min)'],
```

`rule()` in that file matches the first rule whose selector starts a line (`^\s*<selector>\s*\{`), so `.segment` resolves to the base rule and `:host(.many) .segment` to the phone rule added in Step 4. If V247-3 or V247-8 has already edited this table (they add rail and overview rows), keep their rows and add these two after the segmented row; never drop a row on merge.

- [ ] **Step 3: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/segmented.spec.ts --include src/app/ui/hit-area.spec.ts`
Expected: FAIL — `segmented.many` is not a function and the host has no `many` class; `phoneRule(':host(.many)')` is `''`; hit-area's `:host(.many) .segment sets min-width: var(--hit-min)` row fails. The `.segment … min-height` row and every pre-existing test pass.

- [ ] **Step 4: Implement**

Replace `frontend/src/app/ui/segmented.ts` with:

```ts
import { ChangeDetectionStrategy, Component, ElementRef, computed, input, model, viewChildren } from '@angular/core';

/** One choice in a segmented control. */
export interface SegmentOption { value: string; label: string; count?: number; }

/** A group this long takes the full row on a phone (v246 §A2). */
const MANY_OPTIONS = 3;

/**
 * A single-select toggle with roving tabindex and arrow-key navigation.
 *
 * v246 §A2 "Phone": below 640px a group of three or more options (`many`)
 * fills its row and splits it into equal segments, each at least the touch
 * target wide; the track never wraps, so a row too narrow for every option
 * scrolls. Two options keep their natural width. In a filter bar the group
 * sits in `<sb-field size="auto" [fullRow]="true">`, which gives it the row.
 */
@Component({
  selector: 'sb-segmented', changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[class.many]': 'many()' },
  template: `
    <div class="track" role="group" [attr.aria-label]="label()" (keydown)="onKeydown($event)">
      @for (option of options(); track option.value; let i = $index) {
        <button #segment type="button" class="segment" [class.current]="option.value === value()"
          [attr.aria-pressed]="option.value === value()" [tabindex]="i === focusIndex() ? 0 : -1" (click)="value.set(option.value)">
          {{ option.label }} @if (option.count !== undefined) { <span class="count num">{{ option.count }}</span> }
        </button>
      }
    </div>`,
  styles: `
    :host { display: block; min-width: 0; max-width: 100%; }
    .track { display: inline-flex; max-width: 100%; overflow-x: auto; scrollbar-width: thin; border: 1px solid var(--control-border); border-radius: var(--control-radius); }
    .segment { flex: 0 0 auto; display: inline-flex; align-items: center; gap: var(--space-6); min-height: var(--control-h); min-width: var(--hit-min); justify-content: center; padding: 0 var(--space-10); background: transparent; border: 0; border-left: 1px solid var(--border); color: var(--text-secondary); font: inherit; font-size: var(--text-table); font-weight: 500; white-space: nowrap; cursor: pointer; transition: color var(--transition), background var(--transition); }
    .segment:first-child { border-left: 0; }
    /* v195 Phase 2: hover is the raised step; the accent tint is the selected segment's alone. */
    .segment:not(.current):hover { color: var(--text); background: var(--surface-raised); }
    .segment:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .current { background: var(--accent-soft); color: var(--text); }
    .count { color: var(--text-muted); font-size: var(--text-chip); }
    /* v246 §A2: 3+ options fill the phone row in equal, never-wrapping
       segments. 639px, not 640: 640 is the first tablet width (BREAKPOINTS.sm). */
    @media (max-width: 639px) {
      :host(.many) { width: 100%; }
      :host(.many) .track { display: flex; width: 100%; }
      :host(.many) .segment { flex: 1 1 0; min-width: var(--hit-min); padding: 0 var(--space-6); }
    }
  `,
})
export class Segmented {
  readonly options = input.required<SegmentOption[]>(); readonly label = input.required<string>(); readonly value = model<string>('');
  /** Three or more options: the group takes the full row on a phone. */
  readonly many = computed(() => this.options().length >= MANY_OPTIONS);
  private readonly segments = viewChildren<ElementRef<HTMLButtonElement>>('segment');
  protected readonly focusIndex = computed(() => Math.max(0, this.options().findIndex((option) => option.value === this.value())));
  protected onKeydown(event: KeyboardEvent): void {
    const options = this.options(); if (!options.length) return;
    const last = options.length - 1; const current = this.focusIndex();
    const next = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? (current === last ? 0 : current + 1)
      : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? (current === 0 ? last : current - 1)
      : event.key === 'Home' ? 0 : event.key === 'End' ? last : -1;
    if (next < 0) return; event.preventDefault(); this.value.set(options[next].value); this.segments()[next]?.nativeElement.focus();
  }
}
```

Against today's file the only changes are the `MANY_OPTIONS` constant, the docblock, the `host` line, the phone `@media` block (its closing brace on its own line, four spaces in, which the spec's `PHONE` regex reads) and the `many` member. The base `.track` / `.segment` rules are byte-identical, so the v80 and v195 tests keep passing. If v247 (V240 doctena radii) has changed a base rule's text since this plan was written, keep the merged base rules and add only the listed lines.

- [ ] **Step 5: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/segmented.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/toolbar.spec.ts`
Expected: PASS, 0 failed. (`toolbar.spec.ts` is in the run because its `the control family is flat (v195 Phase 2)` describe reads `segmented.ts` styles; the phone block adds no accent, no shadow and no radius, so it stays green.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/segmented.ts frontend/src/app/ui/segmented.spec.ts frontend/src/app/ui/hit-area.spec.ts
git commit -m "feat(v246): sb-segmented with 3+ options fills the phone row in equal, never-wrapping segments" -m "Segmented.many (host class many); segments keep --hit-min and --control-h; two-option groups unchanged."
```

### Task V246-6: Bars align on the bottom edge: `sb-control-bar`, `sb-toolbar` → `flex-end`, `sb-control-row` opt-in `align="end"`; phone fields fill their grid cell

**Model:** sonnet — CSS changes in two shared bars and one opt-in input on a third, plus projection and CSS-source specs; the v179 baseline pin stays and gains a sibling pin.

**Files:**
- Modify: `frontend/src/app/ui/control-bar.ts:31-77` (the `styles` block)
- Modify: `frontend/src/app/ui/control-bar.spec.ts` (imports; one added `describe` at the end)
- Modify: `frontend/src/app/ui/toolbar.ts:75-85` and `:124-125` (`:host`, `.toolbar-inline`, `.toolbar-sheet.open`)
- Modify: `frontend/src/app/ui/toolbar.spec.ts` (imports; one added `describe` at the end)
- Modify: `frontend/src/app/ui/layout.ts:384-438` (`ControlRow`: one docblock paragraph, a `host` binding, one style rule, one input)
- Modify: `frontend/src/app/ui/layout.spec.ts` (imports; one `describe` added directly after `sb-control-row on the last baseline (v179 §3.4)`, which stays as it is)

**Interfaces:**
- Consumes (from V246-3, V246-4): `Field` (`sb-field`) from `frontend/src/app/ui/field.ts`; `Select`, `TextInput` from `frontend/src/app/ui/form-controls.ts`; the `--field-l` token (240px).
- Produces (consumed by V246-7..V246-11 and V246-18):
  - `sb-control-bar`: `.bar` and `.filters, .scope` use `align-items: flex-end`; `.clear` is `height: var(--control-h)` (plus the existing `min-height`); below 640px `.filters` is the two-column grid with `align-items: end; justify-items: stretch`, so each field fills its cell.
  - `sb-toolbar`: `:host` and `.toolbar-inline` use `align-items: flex-end`; the open sheet's grid columns are `minmax(var(--field-l), 1fr)` so the widest field (L) fits one cell at tablet width.
  - `sb-control-row`: `ControlRow.align = input<ControlRowAlign>('baseline')` with `export type ControlRowAlign = 'baseline' | 'end'`, reflected as host attribute `data-align`. Default `baseline` keeps v179 §3.4's `align-items: last baseline` for every existing user; `align="end"` sets `align-items: flex-end` from 640px up (below 640px every row is the full-width column, as today). Only v246's bars set it: Calendar's month row (V246-8). Markup: `<sb-control-row page-scope align="end">`.
  - The CSS-source assertion shape later consumer specs reuse: `expect(css).toMatch(/align-items:\s*flex-end/)` against the bar's source read with `readFileSync(join(process.cwd(), 'src/app/ui/<bar>.ts'), 'utf8')`.

**Why.** Spec §A2 "The bars that exist": "`sb-control-bar` and `sb-toolbar` switch to `align-items: flex-end`, so fields line up along the bottom even if a label wraps." Today both centre their items, so a field with a caption above it and a control without one end at different heights (Calendar's arrows and switch float about 28px above the selects at 1440 and 820; Analytics' date boxes sit above its selects). Index Handoff decision 8 (amended by the partner, 2026-11-24) keeps Calendar in `sb-control-row` and makes its bottom alignment opt-in: `sb-control-row` keeps v179 §3.4's `last baseline` as the default, chosen so a plain text item in a row (the Versions "Running now" label, the settings save bar) sits on the controls' text line, and its ~15 other users are untouched. A v246 bar opts in with `align="end"`: every control in it sits in an `sb-field` whose label line is always present, so the field bottoms are the control bottoms and `flex-end` holds them on one line whatever the label line does, while `last baseline` needs each item to have a text baseline (an item without one, such as an icon-only button or an empty field, synthesises it from its bottom edge and lands on its neighbours' text line instead). The opt-in applies from 640px up; below that the row is a full-width column (`align-items: stretch`), which the existing phone rule already says. "Phone": `control-bar.ts` keeps its two-column grid below 640px and "fields fill their grid cell", which `justify-items: stretch` states (an `sb-field` below 640px sets `--sb-control-w: 100%`, V246-3). "Control height": the Clear button is one `--control-h` tall, the same box as every field's control, so its bottom edge is theirs. The toolbar's sheet columns grow from `12rem` (192px) to `--field-l` (240px) so an L field such as Trades' Ticker never overflows its cell when the sheet opens at 820.

- [ ] **Step 1: Write the failing control-bar spec**

In `frontend/src/app/ui/control-bar.spec.ts`, add under `import { ControlBar } from './control-bar';`:

```ts
import { Field } from './field';
import { Select } from './form-controls';
```

and append at the end of the file:

```ts
@Component({
  imports: [ControlBar, Field, Select],
  template: `
    <sb-control-bar [activeCount]="1">
      <ng-container filters>
        <sb-field id="f-strategy" label="Strategy" size="m"><sb-select [options]="options" /></sb-field>
        <sb-field id="f-horizon" size="s"><sb-select ariaLabel="Horizon" [options]="options" /></sb-field>
      </ng-container>
      <ng-container scope>
        <sb-field id="f-units" label="Units" size="auto"><button type="button">R</button></sb-field>
      </ng-container>
    </sb-control-bar>
  `,
})
class FieldHost {
  readonly options = [{ value: 'rsi', label: 'RSI' }];
}

/* v246 §A2: every control sits in an sb-field, and the bar lines the fields
 * up along their bottom edge. jsdom lays nothing out, so the alignment is
 * read from source; V246-18 measures it in Chromium at 390/820/1440. */
describe('ControlBar aligns fields on the bottom edge (v246 §A2)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  const rule = (selector: string) =>
    CONTROL_BAR_SOURCE.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{[^}]*\\}`))?.[0] ?? '';
  const phoneBlock = () =>
    CONTROL_BAR_SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';

  it('projects sb-field wrappers into both slots, Clear after the scope fields', () => {
    const f = TestBed.createComponent(FieldHost);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect([...el.querySelectorAll('.filters > sb-field')].map((n) => n.id)).toEqual(['f-strategy', 'f-horizon']);
    expect(el.querySelector('.scope > sb-field#f-units')).not.toBeNull();
    expect(el.querySelector('.scope > sb-field + .clear')).not.toBeNull();
  });

  it('aligns the bar and both groups along the bottom edge, never their centres', () => {
    expect(rule('.bar')).toContain('align-items: flex-end');
    expect(CONTROL_BAR_SOURCE).toMatch(/\.filters,\s*\.scope \{[^}]*align-items: flex-end;/);
    expect(CONTROL_BAR_SOURCE).not.toMatch(/align-items:\s*center/);
  });

  it('makes Clear exactly one control tall, the box every field ends in', () => {
    // \s before "height" so min-height does not satisfy it.
    expect(rule('.clear')).toMatch(/\sheight: var\(--control-h\);/);
    expect(rule('.clear')).toContain('min-height: var(--control-h);');
  });

  it('fills each phone grid cell with its field and keeps the bottoms on one line', () => {
    const filters = phoneBlock().match(/\.filters \{[^}]*\}/)?.[0] ?? '';
    expect(filters).toContain('grid-template-columns: repeat(2, minmax(0, 1fr))');
    expect(filters).toContain('align-items: end');
    expect(filters).toContain('justify-items: stretch');
    expect(phoneBlock()).toMatch(/\.bar \{ flex-direction: column; align-items: stretch; \}/);
  });
});
```

- [ ] **Step 2: Write the failing toolbar spec**

In `frontend/src/app/ui/toolbar.spec.ts`, add under `import { Toolbar, ToolbarControl } from './toolbar';`:

```ts
import { Field } from './field';
import { TextInput } from './form-controls';
```

and append at the end of the file:

```ts
@Component({
  imports: [Toolbar, Field, TextInput],
  template: `
    <sb-toolbar [controls]="controls" [viewportAt]="viewportAt()">
      <sb-field slot="ticker" label="Ticker" size="l"><sb-text-input id="ticker" placeholder="AAPL" /></sb-field>
    </sb-toolbar>
  `,
})
class FieldToolbarHost {
  readonly viewportAt = signal<Viewport | null>('md');
  readonly controls: ToolbarControl[] = [{ id: 'ticker', label: 'Ticker', inlineFrom: 'md' }];
}

describe('sb-toolbar aligns fields on the bottom edge (v246 §A2)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('aligns the host row and the inline row along the bottom edge, never their centres', () => {
    for (const selector of [':host', '.toolbar-inline']) {
      expect(toolbarRule(selector), selector).toContain('align-items: flex-end');
      expect(toolbarRule(selector), selector).not.toContain('align-items: center');
    }
  });

  it('sizes the sheet columns so the widest field (L) fits one cell', () => {
    expect(toolbarRule('.toolbar-sheet.open')).toContain('grid-template-columns: repeat(auto-fill, minmax(var(--field-l), 1fr))');
    expect(toolbarRule('.toolbar-sheet.open')).toContain('align-items: end');
  });

  it('moves a slotted sb-field between the row and the sheet as one element, control and all', () => {
    const f = TestBed.createComponent(FieldToolbarHost);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const field = el.querySelector('.toolbar-inline > sb-field[slot="ticker"]');
    expect(field).not.toBeNull();
    expect(field!.querySelector('#ticker input')).not.toBeNull();

    f.componentInstance.viewportAt.set('sm');
    f.detectChanges();
    expect(el.querySelector('.toolbar-inline > sb-field')).toBeNull();
    expect(el.querySelector('.toolbar-sheet > sb-field[slot="ticker"]')).toBe(field);
  });
});
```

`toolbarRule` is the module helper at line 120; `Component`, `signal`, `provideZonelessChangeDetection`, `TestBed`, `beforeEach` and `Viewport` are already imported at lines 3-7.

- [ ] **Step 3: Pin the `sb-control-row` opt-in**

In `frontend/src/app/ui/layout.spec.ts`, change the import on line 10 to `import { ControlRow, Drawer, Panel, Tab, TabBar } from './layout';` and add under it `import { Field } from './field';`. Leave `describe('sb-control-row on the last baseline (v179 §3.4)', …)` (lines 392-404) exactly as it is: it is the pin for the default. Directly after its closing `});` add:

```ts
@Component({
  imports: [ControlRow, Field],
  template: `
    <sb-control-row id="plain"><button type="button">Run</button></sb-control-row>
    <sb-control-row id="bar" align="end">
      <sb-field id="arrows" size="auto" [fullRow]="true"><button type="button">‹</button></sb-field>
      <sb-field id="horizon" label="Horizon" size="s"><select><option>Any</option></select></sb-field>
    </sb-control-row>
  `,
})
class RowHost {}

/* v246 §A2 (index Handoff 8, amended): a bar whose controls all sit in
 * sb-fields opts into bottom-edge alignment with align="end". The default
 * stays last baseline (pinned just above), so the other rows are untouched. */
describe('sb-control-row align="end" opt-in (v246 §A2)', () => {
  const ROW = stylesOf('sb-control-row', 'ControlRow');

  function mount(): HTMLElement {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const f = TestBed.createComponent(RowHost);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('reflects the alignment on the host: baseline by default, end when asked', () => {
    const el = mount();
    expect(el.querySelector('#plain')!.getAttribute('data-align')).toBe('baseline');
    expect(el.querySelector('#bar')!.getAttribute('data-align')).toBe('end');
  });

  it('aligns an opted-in row along the bottom edge from 640px up', () => {
    expect(ROW).toMatch(
      /@media \(min-width: 640px\) \{\s*:host\(\[data-align='end'\]\) \.row \{ align-items: flex-end; \}\s*\}/,
    );
  });

  it('keeps last baseline as the default rule', () => {
    expect(ruleIn(ROW, '.row')).toContain('align-items: last baseline');
    expect(ruleIn(ROW, '.row')).not.toContain('flex-end');
  });

  it('holds sb-field wrappers as its direct items', () => {
    const ids = [...mount().querySelectorAll('#bar .row > sb-field')].map((n) => n.id);
    expect(ids).toEqual(['arrows', 'horizon']);
  });
});
```

`stylesOf`, `ruleIn` and `esc` are defined at lines 16 and 320-324, above this block; `Component`, `TestBed` and `provideZonelessChangeDetection` are imported at lines 3-4. The other `sb-control-row` test (`stacks every control row below 640px`, line 155) is unchanged and keeps passing: the opt-in rule sits in its own `min-width` block, after the phone block, so the phone block's text does not change.

- [ ] **Step 4: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/control-bar.spec.ts --include src/app/ui/toolbar.spec.ts --include src/app/ui/layout.spec.ts`
Expected: FAIL — `.bar` and `:host` have `align-items: center`; `.clear` has no plain `height`; the phone `.filters` has no `justify-items`; the sheet columns are `minmax(12rem, 1fr)`; `sb-control-row` has no `data-align` and no `min-width: 640px` rule. The control-bar and toolbar projection tests already pass (they pin the markup the consumers write); the v179 baseline pin passes before and after.

- [ ] **Step 5: Implement `sb-control-bar`**

In `frontend/src/app/ui/control-bar.ts`, replace the `.bar` and `.filters, .scope` rules (lines 32-47) with:

```css
    /* v246 §A2: the bottom edge, not the centre. Every control in the bar
       sits in an sb-field whose label line is always there (an aria-hidden
       filler when unlabelled), so the field bottoms are the control bottoms
       and flex-end puts them on one line even when a label wraps. */
    .bar {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      justify-content: space-between;
      gap: var(--space-10);
      padding: var(--space-10) 0;
    }
    .filters,
    .scope {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      gap: var(--space-10);
      min-width: 0;
    }
```

In the `.clear` rule, add `height: var(--control-h);` as its first declaration (above `min-height: var(--control-h);`), with the comment line `/* v246: one control tall, the box every field ends in. */` directly above the rule's existing v195 comment. Replace the phone `.filters` line (line 74) with:

```css
      /* v246 §A2: each field fills its cell (an sb-field sets
         --sb-control-w: 100% below 640px), so a 2-2-1 stack shows equal
         widths; end keeps the bottoms on one line per grid row. */
      .filters { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: end; justify-items: stretch; }
```

The phone `.bar` and `.scope` lines stay as they are.

- [ ] **Step 6: Implement `sb-toolbar`**

In `frontend/src/app/ui/toolbar.ts`, in the `:host` rule change `align-items: center;` to `align-items: flex-end;` and put this comment directly above `:host {`:

```css
    /* v246 §A2: projected controls sit in sb-fields (the field carries the
       slot); flex-end lines their bottom edges up, labelled or not. */
```

Replace the `.toolbar-inline` line (line 85) with:

```css
    .toolbar-inline { display: flex; align-items: flex-end; gap: var(--space-10); flex-wrap: wrap; min-width: 0; max-width: 100%; }
```

and the `.toolbar-sheet.open` line (line 125) with:

```css
    /* v246 §A2: a column is at least the widest field (--field-l), so an L
       field never overflows its cell when the sheet opens at tablet width. */
    .toolbar-sheet.open { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--field-l), 1fr)); align-items: end; }
```

The `@container toolbar (max-width: 639px)` two-column rule and the phone `display: contents` block are unchanged. The `.toolbar-sheet-button` keeps its own `align-items: center` (it centres the button's label and count inside the button; it is not a row alignment).

- [ ] **Step 7: Implement the `sb-control-row` opt-in**

In `frontend/src/app/ui/layout.ts`, directly above the `/**` docblock of `ControlRow` (the one beginning `* The one sanctioned control row.`), add:

```ts
/** How an `sb-control-row` lines up its items (v246 §A2): `baseline` (the
 *  default, v179 §3.4) or `end`, the bottom edge, for a bar whose controls
 *  all sit in sb-fields. */
export type ControlRowAlign = 'baseline' | 'end';
```

In the docblock, directly after the paragraph that ends `of on their bottom border.`, add this paragraph (the `last baseline` paragraph itself stays):

```ts
 * **`align="end"`, opt-in** (v246 §A2, index Handoff 8 as amended). A bar
 * whose every control sits in an `sb-field` (ui/field.ts) opts into
 * `flex-end`: each field's label line is always present (an aria-hidden
 * filler when unlabelled), so a field's bottom edge IS its control's, and
 * the bottom edge holds them on one line whatever the label lines do. Only
 * v246's bars set it (Calendar's month row); every other row keeps the last
 * baseline above, so its plain text stays on the controls' text line. From
 * 640px up only: below that every row is the full-width column.
```

In the `@Component` for `sb-control-row`, add after `changeDetection: ChangeDetectionStrategy.OnPush,`:

```ts
  host: { '[attr.data-align]': 'align()' },
```

In its `styles`, directly after the closing `}` of the `@media (max-width: 639px) { .row { … } }` block, add:

```css
    /* v246 §A2: the opt-in bottom edge for a bar of sb-fields; from 640px
       up only, so the phone column above keeps align-items: stretch. */
    @media (min-width: 640px) {
      :host([data-align='end']) .row { align-items: flex-end; }
    }
```

and in `export class ControlRow`, after `readonly stacked = input(false);`, add:

```ts
  /** `end` lines the row up along the bottom edge (v246 §A2); a bar whose
   *  controls all sit in sb-fields sets it. Default: last baseline. */
  readonly align = input<ControlRowAlign>('baseline');
```

The `.row` rule keeps `align-items: last baseline;`.

- [ ] **Step 8: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/control-bar.spec.ts --include src/app/ui/toolbar.spec.ts --include src/app/ui/layout.spec.ts --include src/app/ui/hit-area.spec.ts`
Expected: PASS, 0 failed.

Then the consumers of the three bars, whose specs read rendered markup (no consumer source changes here, so they must stay green):

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed. A failure in a workspace spec that asserts `align-items: center` on `sb-control-bar` or `sb-toolbar` is a pinned old alignment: update that assertion to `flex-end` with a one-line `v246 §A2` comment, and list the file in the commit body. No `sb-control-row` user changes here, so none of their specs may change.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/ui/control-bar.ts frontend/src/app/ui/control-bar.spec.ts frontend/src/app/ui/toolbar.ts frontend/src/app/ui/toolbar.spec.ts frontend/src/app/ui/layout.ts frontend/src/app/ui/layout.spec.ts
git commit -m "feat(v246): sb-control-bar and sb-toolbar align fields on the bottom edge; sb-control-row gains opt-in align=end" -m "flex-end replaces centre in the two bars; sb-control-row keeps last baseline (v179 §3.4) unless align=end; Clear one --control-h tall; phone fields fill their grid cell; sheet columns fit an L field."
```

# Phase 4 — Trades and Calendar wrapped

### Task V246-7: Trades toolbar: controls in `sb-field` (dates "Opened" M+M, Ticker L, Strategy M, selects S/M); Compact/Full → `sb-segmented` "Density"

**Model:** sonnet — template wrapping in a 1340-line workspace plus one small typed handler; every slot, label and size is fixed in the table below.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.ts` — imports (lines 49-54) and the `imports: [...]` array (line 163); the toolbar template from `<div slot="density" …>` (line 280) through the `slot="note"` select (line 372); styles `.export-wrap` (line 666) and `.density` (line 670); class members after `setDensity()` (lines 896-905)
- Modify: `frontend/src/app/workspaces/trades/trades.spec.ts` (one added `describe` after `describe('Trades — the opened-at range', …)`)

**Interfaces:**
- Consumes: `Field` (`sb-field`, `frontend/src/app/ui/field.ts`, V246-3); the label drop and naming in `sb-select` / `sb-text-input` and the date-range field naming (V246-4); `Segmented`, `SegmentOption` (`frontend/src/app/ui/segmented.ts`); the flex-end `sb-toolbar` and its `--field-l` sheet columns (V246-6); existing `Trades.setDensity(next: Density)`, `Trades.density: WritableSignal<Density>`, `TRADES_CONTROLS` (unchanged).
- Produces: nothing a later task imports. V246-11's gate reads this file: every `<sb-select`, `<sb-text-input`, `<sb-date-range` and `<sb-segmented` in it sits inside an `<sb-field`.

**Why.** Spec §A2: on Trades "the date range sits unlabelled on the chip row, and the Ticker and Strategy boxes are about twice as wide as the selects". Each filter becomes one `sb-field` carrying the toolbar `slot` (brief Trap 3: the field, not the control, is the projected element) with the field's label as the only caption (Handoff 2: the controls drop their own `label`; the field names them). Sizes, from the field-size rule (S a short select, M a date or Strategy, L a free-text search):

| slot | field label | size | control |
|---|---|---|---|
| `density` | Density | `auto` | `sb-segmented` "Row density" (Compact / Full) |
| `dates` | Opened | `auto`, `fullRow` | `sb-date-range` (From and To at M each, V246-4) |
| `ticker` | Ticker | `l` | `sb-text-input type=search` |
| `origin` | Origin | `s` | `sb-select` |
| `strategy` | Strategy | `m` | `sb-text-input type=search` |
| `horizon` | Horizon | `s` | `sb-select` |
| `confidence` | Confidence | `s` | `sb-select` |
| `tier` | Tier | `s` | `sb-select` |
| `badge` | Badge | `s` | `sb-select` |
| `note` | Note | `s` | `sb-select` |

Every select is S: the widest option text ("Has a note", "Validated", "Tier A", "Any") fits `--field-s` (136px). "Toggle groups": Compact/Full "stops being two plain-text buttons" and renders as `sb-segmented` with the label "Density"; its group keeps today's accessible name "Row density" (contains the visible word, WCAG 2.5.3). It has two options, so it keeps its natural width on a phone (V246-5). The date-range field spans the whole row wherever the toolbar lays its controls out as a grid (the sheet below `md`, two columns on a phone): `fullRow` (V246-3) handles a flex row, and `grid-column: 1 / -1` on the field handles the grid, which the field cannot set for itself because it does not know its parent is a grid. Status chips, the column picker and Export CSV are not field controls (the gate's list is select / text input / date range / segmented) and stay as they are; Export CSV's wrapper becomes one `--control-h` tall so its link text centres on the controls' row instead of sitting on their bottom border under the flex-end toolbar.

- [ ] **Step 1: Write the failing spec**

In `frontend/src/app/workspaces/trades/trades.spec.ts`, directly after the closing `});` of `describe('Trades — the opened-at range', …)`, add:

```ts
/* -- v246 §A2 -- every toolbar control in one sb-field ------------------- */

describe('Trades toolbar fields (v246 §A2)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/trades/trades.ts'), 'utf8');
  const FIELDS: [slot: string, label: string, size: string][] = [
    ['density', 'Density', 'auto'],
    ['dates', 'Opened', 'auto'],
    ['ticker', 'Ticker', 'l'],
    ['origin', 'Origin', 's'],
    ['strategy', 'Strategy', 'm'],
    ['horizon', 'Horizon', 's'],
    ['confidence', 'Confidence', 's'],
    ['tier', 'Tier', 's'],
    ['badge', 'Badge', 's'],
    ['note', 'Note', 's'],
  ];
  const slot = (el: HTMLElement, id: string) =>
    el.querySelector(`sb-toolbar [slot="${id}"]`) as HTMLElement;

  it.each(FIELDS)('puts %s in an sb-field labelled %s at size %s, the field carrying the slot', (id, label, size) => {
    const field = slot(render().nativeElement as HTMLElement, id);
    expect(field.tagName.toLowerCase()).toBe('sb-field');
    expect(field.getAttribute('data-size')).toBe(size);
    expect(field.querySelector('.field-label')!.textContent!.trim()).toBe(label);
  });

  it('draws one caption per field: no wrapped control prints its own label', () => {
    const el = render().nativeElement as HTMLElement;
    for (const [id] of FIELDS) expect(slot(el, id).querySelectorAll('.sb-label'), id).toHaveLength(1);
  });

  it('names every wrapped control from its field', () => {
    const el = render().nativeElement as HTMLElement;
    for (const [id, label] of FIELDS.filter(([id]) => id !== 'density' && id !== 'dates')) {
      expect(slot(el, id).querySelector('select, input')!.getAttribute('aria-label'), id).toBe(label);
    }
    expect(slot(el, 'dates').querySelector('input.from')!.getAttribute('aria-label')).toBe('Opened from');
    expect(slot(el, 'dates').querySelector('input.to')!.getAttribute('aria-label')).toBe('Opened to');
  });

  it('gives the date range the whole row: flex row on a phone, grid row in the sheet', () => {
    const dates = slot(render().nativeElement as HTMLElement, 'dates');
    expect(dates.classList).toContain('full-row');
    expect(dates.classList).toContain('range-field');
    expect(SOURCE).toMatch(/\.range-field \{ grid-column: 1 \/ -1; \}/);
  });

  it('wraps every select, text input, date range and segmented in the template in a field', () => {
    const template = SOURCE.slice(SOURCE.indexOf('<sb-toolbar'), SOURCE.indexOf('</sb-toolbar>'));
    const controls = template.match(/<sb-(select|text-input|date-range|segmented)\b/g) ?? [];
    const fields = template.match(/<sb-field\b/g) ?? [];
    expect(controls).toHaveLength(10);
    expect(fields).toHaveLength(10);
    expect(template).not.toMatch(/<sb-(select|text-input|date-range|segmented)\b[^>]*\bslot=/);
  });

  it('renders Compact / Full as one sb-segmented group, not two ghost buttons', () => {
    const el = render().nativeElement as HTMLElement;
    const group = slot(el, 'density').querySelector('sb-segmented [role="group"]')!;
    expect(group.getAttribute('aria-label')).toBe('Row density');
    expect([...group.querySelectorAll('button')].map((b) => b.textContent!.trim())).toEqual(['Compact', 'Full']);
    expect(el.querySelector('.density')).toBeNull();
    expect(SOURCE).not.toMatch(/\.density \{/);
  });

  it('presses the current density (compact by default) and switches on a press', () => {
    const f = render();
    const el = f.nativeElement as HTMLElement;
    const buttons = () => [...slot(el, 'density').querySelectorAll<HTMLButtonElement>('button')];
    const density = (f.componentInstance as unknown as { density: () => string }).density;
    expect(density()).toBe('compact');
    expect(buttons().map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false']);

    buttons()[1].click();
    f.detectChanges();
    expect(density()).toBe('full');
    expect(buttons().map((b) => b.getAttribute('aria-pressed'))).toEqual(['false', 'true']);
  });

  it('ignores a value that is not a density', () => {
    const f = render();
    const trades = f.componentInstance as unknown as { density: () => string; onDensity(v: string): void };
    trades.onDensity('roomy');
    expect(trades.density()).toBe('compact');
  });

  it('centres the Export CSV link on the control row: its box is one control tall', () => {
    expect(SOURCE).toMatch(/\.export-wrap \{[^}]*min-height: var\(--control-h\)/);
  });
});
```

`render()`, `readFileSync` and `join` are already in scope (lines 8-9, 114). The existing `translates a date-range change into opened_from/opened_to` test keeps querying `sb-toolbar [slot=dates] input.to`, which now matches through the field.

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trades.spec.ts`
Expected: FAIL — `[slot="density"]` is a `div`, the other slots are the bare controls (`tagName` is `sb-select` / `sb-text-input` / `sb-date-range`), there is no `.field-label`, the date inputs are named `From date` / `To date`, `onDensity` is not a function, `.density {` is still in the styles. Every pre-existing test passes.

- [ ] **Step 3: Imports**

In `frontend/src/app/workspaces/trades/trades.ts`, add next to the other `../../ui/` imports (after `import { DateRange } from '../../ui/date-range';`, line 53):

```ts
import { Field } from '../../ui/field';
import { SegmentOption, Segmented } from '../../ui/segmented';
```

and add `Field,` and `Segmented,` to the component's `imports: [...]` array directly after `DateRange,`. `Button` stays imported: the header actions still use `sb-button`.

- [ ] **Step 4: Wrap the toolbar controls**

Replace the `density` group (the `<div slot="density" class="density" role="group" aria-label="Row density">` element and its two buttons, lines 280-303) with:

```html
        <!-- v246 §A2: the density pair is an sb-segmented in its own field,
             the same toggle style as every other group in a bar. -->
        <sb-field slot="density" label="Density" size="auto">
          <sb-segmented
            label="Row density"
            [options]="densityOptions"
            [value]="density()"
            (valueChange)="onDensity($event)"
          />
        </sb-field>
```

Leave `<span slot="export" class="export-wrap">…</span>` and its comment as they are. Replace everything from the `sb-date-range` element (including its `v85 D32` comment, which moves inside) through the `slot="note"` select (lines 309-372) with:

```html
        <!-- v246 §A2: each filter is one sb-field; the field carries the
             toolbar slot (the projected element) and the one caption, and
             names the control. Sizes: S a short select, M a date or
             Strategy, L the ticker search. -->
        <sb-field slot="dates" class="range-field" label="Opened" size="auto" [fullRow]="true">
          <!-- v85 D32: the opened-at range narrows WHEN, not WHAT -- a scope
               control rather than a field filter. -->
          <sb-date-range
            [from]="opened_from() ?? null"
            [to]="opened_to() ?? null"
            (changed)="onDateRange($event)"
          />
        </sb-field>
        <sb-field slot="ticker" label="Ticker" size="l">
          <sb-text-input
            type="search"
            placeholder="AAPL"
            [value]="ticker() ?? ''"
            (valueChange)="navigate({ ticker: $event })"
          />
        </sb-field>
        <sb-field slot="origin" label="Origin" size="s">
          <sb-select
            placeholder="Any"
            [value]="origin() ?? ''"
            [options]="originOptions"
            (valueChange)="navigate({ origin: $event })"
          />
        </sb-field>
        <!-- SR52. The five the parity audit found, in the order they narrow a
             search: what the setup was, then how it was graded, then whether it
             has been written up. -->
        <sb-field slot="strategy" label="Strategy" size="m">
          <sb-text-input
            type="search"
            placeholder="RSI"
            [value]="strategy() ?? ''"
            (valueChange)="navigate({ strategy: $event })"
          />
        </sb-field>
        <sb-field slot="horizon" label="Horizon" size="s">
          <sb-select
            placeholder="Any"
            [value]="horizon() ?? ''"
            [options]="horizonOptions"
            (valueChange)="navigate({ horizon: $event })"
          />
        </sb-field>
        <sb-field slot="confidence" label="Confidence" size="s">
          <sb-select
            placeholder="Any"
            [value]="confidence() ?? ''"
            [options]="confidenceOptions"
            (valueChange)="navigate({ confidence: $event })"
          />
        </sb-field>
        <sb-field slot="tier" label="Tier" size="s">
          <sb-select
            placeholder="Any"
            [value]="tier() ?? ''"
            [options]="tierOptions"
            (valueChange)="navigate({ tier: $event })"
          />
        </sb-field>
        <sb-field slot="badge" label="Badge" size="s">
          <sb-select
            placeholder="Any"
            [value]="badge() ?? ''"
            [options]="badgeOptions"
            (valueChange)="navigate({ badge: $event })"
          />
        </sb-field>
        <sb-field slot="note" label="Note" size="s">
          <sb-select
            placeholder="Any"
            [value]="has_note() ?? ''"
            [options]="noteOptions"
            (valueChange)="navigate({ has_note: $event })"
          />
        </sb-field>
```

Every binding and handler is today's; only the `slot` moves to the field and the control's own `label` goes (the field names it). Nothing sits in a host-side `@if` / `@for` (brief Trap 3).

- [ ] **Step 5: Styles**

Replace the `.export-wrap` line (line 666) with:

```css
    /* v246 §A2: one control tall with the link centred, so under the
       flex-end toolbar Export CSV reads on the controls' row, not below it. */
    .export-wrap { display: inline-flex; align-items: center; gap: var(--space-4); min-height: var(--control-h); }
```

Replace the `.density` rule and its `v95 C1` comment (lines 668-670) with:

```css
    /* v246 §A2: the date range takes a whole row where the toolbar is a grid
       (the sheet below md, two columns on a phone); fullRow covers the flex
       row. On the field, which carries this component's style scope even
       after sb-toolbar moves it. */
    .range-field { grid-column: 1 / -1; }
```

- [ ] **Step 6: The density handler**

In the class, directly after `setDensity()` (ends line 905), add:

```ts
  /** v246 §A2: the Density segmented's options, in reading order. */
  protected readonly densityOptions: SegmentOption[] = [
    { value: 'compact', label: 'Compact' },
    { value: 'full', label: 'Full' },
  ];

  /** The segmented speaks strings; only the two densities reach setDensity. */
  protected onDensity(value: string): void {
    if (value === 'compact' || value === 'full') this.setDensity(value);
  }
```

- [ ] **Step 7: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trades.spec.ts`
Expected: PASS, 0 failed.

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed (pulls in the other specs that mount Trades, such as the reachability and access specs).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/trades/trades.spec.ts
git commit -m "feat(v246): Trades toolbar filters in sb-field (Opened range, Ticker L, Strategy M, selects S); Density is sb-segmented" -m "The field carries the toolbar slot and the one caption; the date range spans the sheet's grid row; Export CSV is one control tall."
```

### Task V246-8: Calendar month row: arrows, metric switch (→ `sb-segmented` "Show") and selects in `sb-field`s inside `sb-control-row`

**Model:** sonnet — template wrapping of one scope row in an 849-line workspace, a small typed handler and two rewritten source assertions; names, sizes and order are fixed below.

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts` — imports (lines 10-19) and the `imports: [...]` array (lines 40-43); the `<sb-control-row page-scope>` block (lines 84-120); styles `.months` / `.month` / `.metric…` (lines 404-419); class members after `metrics` (lines 609-614)
- Modify: `frontend/src/app/workspaces/calendar/calendar.spec.ts` — the `keeps the metric toggle cells a hit-minimum wide` test (line 845), the `puts the month filters in the scope bar` test (lines 985-996), and one added `describe` after `describe('Calendar on sb-page (v195 Phase 4, §5.2)', …)`

**Interfaces:**
- Consumes: `Field` (`sb-field`, V246-3); the label drop in `sb-select` (V246-4); `Segmented` and its `many` phone rule (V246-5); the opt-in `align="end"` on `sb-control-row` (`ControlRow.align`, V246-6); existing `CalendarStore.setMetric(metric: CalendarMetric)`, `CalendarStore.metric()`, `Calendar.metrics` (`{ value: CalendarMetric; label: string }[]`, money option labelled with the account currency).
- Produces: nothing a later task imports. V246-11's gate treats `sb-control-row` as a bar and reads this file: its `<sb-select>` and `<sb-segmented>` sit inside `<sb-field>`, and the row sets `align="end"`.

**Why.** Spec §A2: on Calendar "the month arrows and the €/R switch sit about 28px above the selects" at 1440 and 820. Index Handoff decision 8 (amended): the row stays an `sb-control-row`, opts into bottom-edge alignment with `align="end"` (V246-6; every other `sb-control-row` keeps last baseline), and every control in it goes into an `sb-field`, so each control's bottom edge is its field's bottom edge and the four line up. The fields, in reading order:

| field | label | size | control |
|---|---|---|---|
| month | none (filler) | `auto`, `fullRow` | `.months`: Previous month, the month name, Next month |
| show | Show | `auto`, `fullRow` | `sb-segmented` "Show": the currency, R, Trades, Win rate |
| strategy | Strategy | `m` | `sb-select` "Any strategy" |
| horizon | Horizon | `s` | `sb-select` "Any horizon" |

"Toggle groups": the €/R/Trades/Win rate switch renders as `sb-segmented` labelled "Show" (Handoff 4: today it is a `div.metric` of `sb-button variant="segment"`), so its own `.metric` styles go and it gets the shared roving tabindex, arrow keys and `aria-pressed`. Its four options make it `many` (V246-5): on a phone it fills its row in equal segments. "Phone": the month field and the Show field are full-row controls and drop the empty label filler there (`fullRow` + no label, V246-3); `sb-control-row` already stacks to one full-width column below 640px, so the selects fill the row too (`--sb-control-w: 100%`). The month name is running text inside the arrow pair, so `.months` keeps centring its own three children, one `--control-h` tall, inside the field. The store's `setMetric` takes a `CalendarMetric`; the segmented emits a string, so a small handler admits only a listed metric.

- [ ] **Step 1: Write the failing spec**

In `frontend/src/app/workspaces/calendar/calendar.spec.ts`, replace the test at line 845:

```ts
  it('keeps the metric toggle cells a hit-minimum wide: the one-character currency cell was 29px (v179 layout audit)', () => {
    expect(SOURCE).toMatch(/\.metric button \{[^}]*min-width:\s*var\(--hit-min\)/);
  });
```

with:

```ts
  it('draws the metric switch with the shared segmented, whose cells keep the hit minimum (v179 layout audit, v246 §A2)', () => {
    // The one-character currency cell was 29px wide. sb-segmented's .segment
    // carries min-width: var(--hit-min) (pinned in ui/hit-area.spec.ts).
    // A CSS rule starting a line; `store.metric()` in the class is not one.
    expect(SOURCE).not.toMatch(/^\s*\.metric\b/m);
    expect(SOURCE).not.toContain('variant="segment"');
    const segmented = readFileSync(join(process.cwd(), 'src/app/ui/segmented.ts'), 'utf8');
    expect(segmented).toMatch(/\.segment \{[^}]*min-width: var\(--hit-min\)/);
  });
```

In `it('puts the month filters in the scope bar, and nothing destructive', …)` (line 985), replace the line `expect(scope.querySelector('.metric')).not.toBeNull();` with `expect(scope.querySelector('sb-segmented')).not.toBeNull();`.

Then, directly after the closing `});` of `describe('Calendar on sb-page (v195 Phase 4, §5.2)', …)`, add:

```ts
/* -- v246 §A2 -- the month row: every control in one sb-field ------------ */

describe('Calendar month row in sb-field (v246 §A2)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/calendar/calendar.ts'), 'utf8');

  async function scope(): Promise<{ fixture: ComponentFixture<Calendar>; row: HTMLElement }> {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, row: el(fixture).querySelector('sb-page [page-scope]') as HTMLElement };
  }
  const fields = (row: HTMLElement) => [...row.querySelectorAll<HTMLElement>('.row > sb-field')];
  const showButtons = (row: HTMLElement) => [...fields(row)[1].querySelectorAll<HTMLButtonElement>('sb-segmented button')];

  it('puts the arrows, the Show switch and both selects each in one sb-field, in reading order', async () => {
    const { row } = await scope();
    const all = fields(row);
    expect(all.map((f) => f.querySelector('.field-label')!.textContent!.trim())).toEqual(['', 'Show', 'Strategy', 'Horizon']);
    expect(all.map((f) => f.getAttribute('data-size'))).toEqual(['auto', 'auto', 'm', 's']);
    expect(all[0].querySelector('.months button[aria-label="Previous month"]')).not.toBeNull();
    expect(all[0].querySelector('.months button[aria-label="Next month"]')).not.toBeNull();
    expect(all[1].querySelector('sb-segmented')).not.toBeNull();
    expect(all[2].querySelector('sb-select')).not.toBeNull();
    expect(all[3].querySelector('sb-select')).not.toBeNull();
  });

  it('gives the arrows and the switch a whole phone row, the arrows without a filler line there', async () => {
    const [month, show, strategy] = fields((await scope()).row);
    expect(month.classList).toContain('full-row');
    expect(month.classList).toContain('no-label');
    expect(show.classList).toContain('full-row');
    expect(show.classList).not.toContain('no-label');
    expect(strategy.classList).not.toContain('full-row');
  });

  it('draws one caption per field and names the selects from them', async () => {
    const { row } = await scope();
    for (const field of fields(row)) expect(field.querySelectorAll('.sb-label')).toHaveLength(1);
    const selects = [...row.querySelectorAll('sb-select select')];
    expect(selects.map((s) => s.getAttribute('aria-label'))).toEqual(['Strategy', 'Horizon']);
  });

  it('names the switch "Show" and lists the four metrics in order', async () => {
    const { row } = await scope();
    expect(fields(row)[1].querySelector('[role="group"]')!.getAttribute('aria-label')).toBe('Show');
    const labels = showButtons(row).map((b) => b.textContent!.trim());
    expect(labels).toHaveLength(4);
    expect(labels.slice(1)).toEqual(['R', 'Trades', 'Win rate']);
  });

  it('switches the metric from the segmented and presses the chosen one', async () => {
    const { fixture, row } = await scope();
    showButtons(row)[1].click();
    fixture.detectChanges();
    expect(fixture.componentInstance.store.metric()).toBe('r');
    expect(showButtons(row).map((b) => b.getAttribute('aria-pressed'))).toEqual(['false', 'true', 'false', 'false']);
    expect(el(fixture).querySelector('.cell[data-date="2026-08-03"] .value')?.textContent).toContain('R');
  });

  it('ignores a value that is not a calendar metric', async () => {
    const { fixture } = await scope();
    const before = fixture.componentInstance.store.metric();
    (fixture.componentInstance as unknown as { onMetric(v: string): void }).onMetric('sharpe');
    expect(fixture.componentInstance.store.metric()).toBe(before);
  });

  it('opts the month row into bottom-edge alignment', async () => {
    expect((await scope()).row.getAttribute('data-align')).toBe('end');
  });

  it('keeps every select and segmented of the row inside a field in the template', () => {
    const row = SOURCE.slice(SOURCE.indexOf('<sb-control-row page-scope align="end">'), SOURCE.indexOf('</sb-control-row>'));
    expect(row).not.toBe('');
    expect(row.match(/<sb-(select|segmented)\b/g)).toHaveLength(3);
    expect(row.match(/<sb-field\b/g)).toHaveLength(4);
    expect(row).not.toContain('role="group" aria-label="Metric"');
  });
});
```

`seed()`, `el()`, `ComponentFixture`, `Calendar`, `readFileSync` and `join` are already imported or defined at the top of the file.

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/calendar/calendar.spec.ts`
Expected: FAIL — no `data-align` on the row, no `sb-field` in the scope row, no `sb-segmented` (the switch is still `div.metric`), the selects print their own captions and have no `aria-label`, `onMetric` is not a function, and `.metric` is still in the source. The other Calendar tests pass.

- [ ] **Step 3: Imports**

In `frontend/src/app/workspaces/calendar/calendar.ts`, add with the other `../../ui/` imports:

```ts
import { Field } from '../../ui/field';
import { Segmented } from '../../ui/segmented';
```

and add `Field,` and `Segmented,` to the component's `imports: [...]` array (keep it alphabetical within its first line: `Button, ControlRow, Drawer, ExcursionEstimate, Field, LegName, Panel, Page, RouterLink, Segmented, Select, StatStrip, StatTile, Async,`). `Button` stays: the month arrows are still `sb-button`.

- [ ] **Step 4: Wrap the month row**

Replace the block from `<!-- v195 §5.2: the scope bar holds the month and the filters only. -->` through `</sb-control-row>` (lines 84-120; if V247-3 shifted the lines, the block is the one opened by `<sb-control-row page-scope>`) with:

```html
      <!-- v195 §5.2: the scope bar holds the month and the filters only.
           v246 §A2: each control sits in one sb-field, and align="end" lines
           the fields up along their bottom edge (the opt-in, V246-6). -->
      <sb-control-row page-scope align="end">
        <!-- No caption: the month name says what the arrows step. A full
             row on a phone, where the empty label line drops. -->
        <sb-field size="auto" [fullRow]="true">
          <div class="months">
            <button sb-button type="button" variant="ghost"
                    (click)="store.stepMonth(-1)" aria-label="Previous month">‹</button>
            <span class="month">{{ label() }}</span>
            <button sb-button type="button" variant="ghost"
                    (click)="store.stepMonth(1)" aria-label="Next month">›</button>
          </div>
        </sb-field>

        <sb-field label="Show" size="auto" [fullRow]="true">
          <sb-segmented
            label="Show"
            [options]="metrics()"
            [value]="store.metric()"
            (valueChange)="onMetric($event)"
          />
        </sb-field>

        <sb-field label="Strategy" size="m">
          <sb-select
            placeholder="Any strategy"
            [options]="store.strategyOptions()"
            [value]="store.strategy()"
            (valueChange)="store.setStrategy($event)"
          />
        </sb-field>
        <sb-field label="Horizon" size="s">
          <sb-select
            placeholder="Any horizon"
            [options]="store.horizonOptions()"
            [value]="store.horizon()"
            (valueChange)="store.setHorizon($event)"
          />
        </sb-field>
      </sb-control-row>
```

Bindings and handlers are today's except the row's new `align="end"` and the switch, which now goes through `onMetric`; the selects lose their own `label` (the field captions and names them).

- [ ] **Step 5: Styles**

Replace the month-stepper comment and rules and the whole `.metric` group (from `/* The month stepper: two buttons with the month between them.` through `.metric button.active { … }`, lines 404-419) with:

```css
    /* The month stepper: two buttons with the month between them, in one
       sb-field (v246 §A2). It centres its own three children, because the
       month is running text, and is one control tall, so the field's bottom
       edge -- where the align="end" row aligns it -- is the buttons'. */
    .months { display: flex; align-items: center; gap: var(--space-8); min-height: var(--control-h); }
    .month { min-width: 10ch; font-weight: 600; }
```

The metric switch's look now comes from `sb-segmented` (hit-minimum cells, the accent-soft current segment); no Calendar rule restyles it.

- [ ] **Step 6: The metric handler**

In the class, directly after the `metrics` computed (ends line 614), add:

```ts
  /** v246 §A2: the Show segmented speaks strings; only a listed metric
   *  reaches the store. */
  protected onMetric(value: string): void {
    const option = this.metrics().find((candidate) => candidate.value === value);
    if (option) this.store.setMetric(option.value);
  }
```

- [ ] **Step 7: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/calendar/calendar.spec.ts`
Expected: PASS, 0 failed.

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed (pulls in the calendar day and route specs that mount the workspace).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts
git commit -m "feat(v246): Calendar month row in sb-field -- arrows, Show segmented, Strategy M, Horizon S" -m "The euro/R/Trades/Win rate switch becomes sb-segmented 'Show'; its .metric styles go; the row opts into align=end (bottom edge)."
```
