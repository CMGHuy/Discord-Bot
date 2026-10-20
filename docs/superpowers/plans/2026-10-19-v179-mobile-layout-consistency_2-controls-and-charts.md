# v179 — Mobile layout consistency, Part 2: controls, tab rails and charts

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-19-v179-mobile-layout-consistency-design.md](../specs/2026-10-19-v179-mobile-layout-consistency-design.md) — §3.3 (filter area, tab bar, charts), §2.1 (overflow), §6b.5 and §6b.7.
**Index:** [2026-10-19-v179-mobile-layout-consistency_0-index.md](2026-10-19-v179-mobile-layout-consistency_0-index.md) — Goal, Architecture, **Global Constraints**, **Contracts**, **Parallelisation** and the task ledger live there and bind every task below.

Tasks V179-5..V179-8. Every task runs in the worktree `.claude/worktrees/2026-10-19-v179-mobile-layout-consistency` (created by V179-1). Paths under "Files" are full repo paths; commands run from the worktree root. Part 1's tokens are in place before this part starts: `--font-num`, the floored `--text-micro`/`--text-chip`, `--hit-min`, `.sb-hit`, and `--control-h: 44px` under `(pointer: coarse), (max-width: 1023px)`.

**One sequencing note on top of the index.** V179-7's heat-grid edge fade consumes `edgeFades` from `ui/scroll-rail.ts`, which V179-6 creates, so V179-7 runs **after** V179-6 (the index lists them as parallel; this is the stricter order, never a looser one). V179-5 and V179-6 still share no file and may run together.

---

# Phase 2 — Controls, tab rails and charts

### Task V179-5: One filter/control row pattern

**Model:** sonnet — four small primitives, CSS-as-source-text tests, one judgement call on where the empty gap comes from.

**Files:**
- Modify: `frontend/src/app/ui/control-bar.ts`
- Modify: `frontend/src/app/ui/control-bar.spec.ts`
- Modify: `frontend/src/app/ui/filter-bar.ts`
- Modify: `frontend/src/app/ui/filter-bar.spec.ts`
- Modify: `frontend/src/app/ui/toolbar.ts`
- Modify: `frontend/src/app/ui/toolbar.spec.ts`
- Modify: `frontend/src/app/ui/column-picker.ts`
- Modify: `frontend/src/app/ui/column-picker.spec.ts`

**Interfaces:**
- Consumes: `--control-h` (44px under `(pointer: coarse), (max-width: 1023px)` since V179-2), `--font-num` via `.num` (V179-1), and the existing tokens `--accent-soft`, `--control-radius`, `--chip-radius`. Any `sb-hit` class V179-2 put on `.chip` or `.trigger` stays.
- Produces: `.toolbar-sheet-button` styled as a normal control-height button with a `.count.num` badge (the ledger's "Creates" entry); `sb-filter-bar` that takes no room when it is empty; `sb-filter-chips` as one scrolling line on a phone. No TypeScript API changes — the inputs and outputs of all four components stay as they are.

**What is wrong today (spec §2.3 "Filter areas").** Trades at 390px: chip row → `Columns 12/29` → a grey 27px "Filters 13" block (the `<button class="toolbar-sheet-button">` has no background or border rule, so the browser's default grey button shows) → ~60px of empty space (Trades mounts `<sb-filter-bar [activeCount]="…" />` with nothing projected; with no active filter its `.bar` is empty, yet the host keeps `padding: var(--space-10) 0` and sits between two `--section-gap`s of Trades' `:host` grid) → the table's own `Sort` select. Watchlist puts a 27px chip, a 44px input and the grey block side by side at three heights. Analytics' five `sb-select`s inside `sb-control-bar` wrap 2 + 3 at unequal widths.

**Fix, primitive by primitive** (spec §3.3 "Filter area"): chips are one line that scrolls sideways on a phone, on their own full-width line; `Filters` and `Columns` are the same normal button — same height (`--control-h`), surface, border and radius, the count as a badge — and wrap together as a unit; the open filter sheet and `sb-control-bar`'s filter slot lay controls out in equal columns (two on a phone-width bar). The table's `Sort` select is `sb-data-table`'s `.phone-sort`, already sized from `--control-h`; `data-table.ts` belongs to Part 3 and is not touched here — removing the empty filter bar is what closes the gap above it.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/ui/control-bar.spec.ts` (put the two `node:` imports at the top of the file, beside the existing imports):

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const CONTROL_BAR_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/control-bar.ts'), 'utf8');

describe('ControlBar one row pattern (v179 §3.3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  // The phone block, whatever it contains, as one string.
  const phoneBlock = () =>
    CONTROL_BAR_SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n    \}/)?.[1] ?? '';

  it('stacks at the declared phone breakpoint, not one pixel into tablet', () => {
    // 640px is the first `sm` (tablet) width -- BREAKPOINTS.sm in breakpoints.ts.
    expect(CONTROL_BAR_SOURCE).toContain('@media (max-width: 639px)');
    expect(CONTROL_BAR_SOURCE).not.toContain('max-width: 640px');
  });

  it('lays phone filters out as two equal columns instead of a ragged wrap', () => {
    expect(phoneBlock()).toMatch(
      /\.filters \{[^}]*display: grid;[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
    );
  });

  it('keeps every projected control reachable -- the grid only re-arranges them', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.filters #chip')).not.toBeNull();
    expect(el.querySelector('.scope #range')).not.toBeNull();
  });
});
```

Append to `frontend/src/app/ui/filter-bar.spec.ts` (it already has `SOURCE`, `FilterBar` and the Angular imports; add `FilterChips` to the `./filter-bar` import):

```ts
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const rule = (selector: string) =>
  SOURCE.match(new RegExp(`${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

describe('FilterBar with nothing to say (v179 §3.3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('renders an empty bar when nothing is projected and nothing is active', () => {
    // Trades mounts <sb-filter-bar [activeCount]="…" /> with no projected
    // control; Angular leaves only comment nodes, which :empty ignores.
    const f = TestBed.createComponent(FilterBar);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('.bar')!.matches(':empty')).toBe(true);
  });

  it('takes no room at all when the bar is empty', () => {
    // The empty bar used to keep its 2 x --space-10 padding and sit between
    // two section gaps: the ~60px hole above Trades' Sort select.
    expect(SOURCE).toMatch(/:host:has\(> \.bar:empty\) \{ display: none; \}/);
  });
});

describe('FilterChips on a phone (v179 §3.3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('is one line that scrolls sideways, never a wrapped block', () => {
    const phone = SOURCE.match(/\/\* v179 chips \*\/\s*@media \(max-width: 639px\) \{([\s\S]*?)\n    \}/)?.[1] ?? '';
    expect(phone).toMatch(/:host \{ flex: 1 1 100%; \}/);
    expect(phone).toMatch(/\.chips \{[^}]*flex-wrap: nowrap;[^}]*overflow-x: auto;/);
  });

  it('never squeezes or wraps a chip label', () => {
    expect(rule('.chip')).toContain('flex: 0 0 auto');
    expect(rule('.chip')).toContain('white-space: nowrap');
  });

  it('sizes chips from --control-h like every other control on the row', () => {
    expect(rule('.chip')).toContain('min-height: var(--control-h)');
  });

  it('lets its host shrink inside a flex row', () => {
    expect(SOURCE).toMatch(/selector: 'sb-filter-chips'[\s\S]*?:host \{ display: block; min-width: 0; max-width: 100%; \}/);
  });

  it('still renders the All chip and every option', () => {
    const f = TestBed.createComponent(FilterChips);
    f.componentRef.setInput('chips', [{ value: 'open', label: 'Open' }, { value: 'closed', label: 'Closed' }]);
    f.detectChanges();
    const labels = [...(f.nativeElement as HTMLElement).querySelectorAll('.chip')].map((b) => b.textContent!.trim());
    expect(labels).toEqual(['All', 'Open', 'Closed']);
  });
});
```

Append to `frontend/src/app/ui/toolbar.spec.ts` (put the two `node:` imports at the top):

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const TOOLBAR_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/toolbar.ts'), 'utf8');
const toolbarRule = (selector: string) =>
  TOOLBAR_SOURCE.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\{[^}]*\\}`))?.[0] ?? '';

describe('sb-toolbar one row pattern (v179 §3.3)', () => {
  let fixture: ComponentFixture<Host>;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    fixture.componentInstance.viewportAt.set('sm');
    fixture.detectChanges();
  });

  it('styles Filters as a normal control button, not the browser-default grey block', () => {
    const rule = toolbarRule('.toolbar-sheet-button');
    expect(rule).toContain('min-height: var(--control-h)');
    expect(rule).toContain('background: var(--surface-raised)');
    expect(rule).toContain('border: 1px solid var(--border)');
    expect(rule).toContain('font: inherit');
  });

  it('shows the demoted count as a numeric badge', () => {
    const badge = (fixture.nativeElement as HTMLElement).querySelector('.toolbar-sheet-button .count')!;
    expect(badge.classList).toContain('num');
    expect(badge.textContent!.trim()).toBe('2');
    expect(toolbarRule('.count')).toContain('border-radius: var(--chip-radius)');
    expect(toolbarRule('.count')).toContain('background: var(--accent-soft)');
  });

  it('lays the open sheet out in equal columns, two on a phone-width bar', () => {
    expect(TOOLBAR_SOURCE).toMatch(/:host \{[^}]*container: toolbar \/ inline-size;/);
    expect(toolbarRule('.toolbar-sheet.open')).toContain('display: grid');
    expect(TOOLBAR_SOURCE).toMatch(
      /@container toolbar \(max-width: 639px\) \{\s*\.toolbar-sheet\.open \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/,
    );
  });
});
```

Append to `frontend/src/app/ui/column-picker.spec.ts` (put the two `node:` imports at the top). This is the one place that pins "Filters and Columns are the same button", so it reads both sources:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const read = (file: string) => readFileSync(join(process.cwd(), 'src/app/ui', file), 'utf8');
const ruleIn = (source: string, selector: string) =>
  source.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\{[^}]*\\}`))?.[0] ?? '';

/** What makes Filters and Columns read as one control family. */
const SHARED_CONTROL_BUTTON = [
  'min-height: var(--control-h)',
  'padding: 0 var(--space-10)',
  'background: var(--surface-raised)',
  'border: 1px solid var(--border)',
  'border-radius: var(--control-radius)',
  'font-size: var(--text-table)',
];

describe('ColumnPicker trigger (v179 §3.3)', () => {
  const picker = read('column-picker.ts');
  const toolbar = read('toolbar.ts');

  it('matches the Filters button: one height, one look', () => {
    const trigger = ruleIn(picker, '.trigger');
    const filters = ruleIn(toolbar, '.toolbar-sheet-button');
    for (const declaration of SHARED_CONTROL_BUTTON) {
      expect(trigger).toContain(declaration);
      expect(filters).toContain(declaration);
    }
  });

  it('shows visible/total as the same badge the Filters button uses', () => {
    expect(picker).toContain('<span class="count num">{{ visible().length }}/{{ columns().length }}</span>');
    expect(ruleIn(picker, '.count')).toBe(ruleIn(toolbar, '.count'));
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/control-bar.spec.ts --include src/app/ui/filter-bar.spec.ts --include src/app/ui/toolbar.spec.ts --include src/app/ui/column-picker.spec.ts`
Expected: FAIL — `max-width: 640px` still present, no phone `.filters` grid, no `:host:has(> .bar:empty)` rule, no `/* v179 chips */` block, `.toolbar-sheet-button` without background or border, `.count` without `num`, no `container: toolbar`, `.trigger` without `min-height`. The `:empty`, "All chip" and "reachable" tests already pass — they pin behaviour that must survive.

- [ ] **Step 3: Implement `sb-control-bar`**

In `frontend/src/app/ui/control-bar.ts` replace the whole `@media (max-width: 640px) { … }` block and its comment with:

```css
    /* At phone width the two groups stack rather than compete for one row.
       Nothing is hidden — the plan forbids a control that vanishes silently.
       v179 §3.3: the filter selects become two equal columns, so five selects
       read as a 2-2-1 grid instead of a ragged 2 + 3 wrap at three widths.
       639px, not 640: 640 is the first tablet width (BREAKPOINTS.sm). */
    @media (max-width: 639px) {
      .bar { flex-direction: column; align-items: stretch; }
      .filters { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: end; }
      .scope { justify-content: flex-start; }
    }
```

- [ ] **Step 4: Implement `sb-filter-bar` and `sb-filter-chips`**

In `frontend/src/app/ui/filter-bar.ts`, `FilterBar`'s `styles` gains these lines directly after its `:host { … }` line:

```css
    /* v179: with nothing projected and nothing active the bar has nothing to
       say, so it takes no room -- it used to keep its padding and sit between
       two section gaps (~60px of blank above Trades' table). */
    :host:has(> .bar:empty) { display: none; }
```

Angular's emulated encapsulation rewrites `:host:has(> .bar:empty)` to `[_nghost-…]:has(> .bar[_ngcontent-…]:empty)` (supported since Angular 17; this repo is on 21.2). If the build warns about the selector, use the equivalent functional form `:host(:has(> .bar:empty)) { display: none; }` and change the test regex to match it — the rule itself is not optional.

Replace `FilterChips`' whole `styles` block with the following (keep the template as it is, including any `sb-hit` class V179-2 added to the chip buttons):

```ts
  styles: `
    :host { display: block; min-width: 0; max-width: 100%; }
    .chips { display: flex; gap: var(--space-4); flex-wrap: wrap; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-6);
      flex: 0 0 auto;
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      background: transparent;
      border: 1px solid var(--border);
      border-radius: var(--chip-radius);
      color: var(--text-secondary);
      font: inherit;
      font-size: var(--text-table);
      white-space: nowrap;
      cursor: pointer;
      transition: color var(--transition), border-color var(--transition);
    }
    .chip:hover { color: var(--text); border-color: var(--border-strong); }
    .chip:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    /* Selection is interactive state, which is what blue is for. */
    .active { color: var(--text); border-color: var(--accent); background: var(--surface-raised); }
    .count { color: var(--text-muted); font-size: var(--text-chip); }
    /* v179 chips */
    @media (max-width: 639px) {
      :host { flex: 1 1 100%; }
      .chips { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: thin; padding-bottom: 2px; }
    }
  `,
```

`:host { flex: 1 1 100% }` only acts where the chips are a flex item (Trades' `sb-toolbar` inline row): there it gives the chips their own full-width line, so `Columns` and `Filters` wrap together onto the next line as a unit. The partly cut last chip is the "more this way" cue; the thin scrollbar stays for mouse users in narrow desktop windows.

- [ ] **Step 5: Implement `sb-toolbar`**

In `frontend/src/app/ui/toolbar.ts`:

1. The badge gets the numeric face. In the template change `<span class="count">{{ demoted().length }}</span>` to:

```html
        <span class="count num">{{ demoted().length }}</span>
```

2. Replace the whole `styles` block with:

```ts
  styles: `
    :host { display: flex; align-items: center; gap: var(--space-10); flex-wrap: wrap; container: toolbar / inline-size; }
    .toolbar-inline { display: flex; align-items: center; gap: var(--space-10); flex-wrap: wrap; min-width: 0; max-width: 100%; }
    /* v179 §3.3: the same button as sb-column-picker's .trigger -- one
       height, one surface, the count as a badge. Without these rules the
       browser's default grey button showed through ("Filters 13"). */
    .toolbar-sheet-button {
      display: inline-flex;
      align-items: center;
      gap: var(--space-6);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--control-radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      cursor: pointer;
      transition: border-color var(--transition);
    }
    .toolbar-sheet-button:hover { border-color: var(--border-strong); }
    .toolbar-sheet-button:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    .count {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 1.5em;
      padding: 0 var(--space-4);
      border-radius: var(--chip-radius);
      background: var(--accent-soft);
      color: var(--text);
      font-size: var(--text-chip);
    }
    /* Selects in the sheet share one width rule: equal columns, two on a
       phone-width bar (the rule sb-filter-bar's container query already uses). */
    .toolbar-sheet { display: none; width: 100%; gap: var(--space-10); }
    .toolbar-sheet.open { display: grid; grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr)); align-items: end; }
    @container toolbar (max-width: 639px) {
      .toolbar-sheet.open { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    .active-dot::after { content: attr(data-count); color: var(--accent); }
  `,
```

`container: toolbar / inline-size` is safe on this host: `sb-toolbar` is always a block-level child of its page (Trades, Watchlist, Research, System logs and scan, the gallery), never shrink-wrapped. One exception to check: System logs puts `<sb-toolbar panel-actions …>` inside a panel header — confirm in Step 7's gallery run and in V179-8's browser check that its controls still show (an inline-size container in a shrink-wrapped flex item collapses to zero width). If it does collapse there, give that call site's host `flex: 1 1 auto` in `logs-tab.ts` rather than dropping the container.

- [ ] **Step 6: Implement `sb-column-picker`**

In `frontend/src/app/ui/column-picker.ts` replace the `.trigger { … }` rule and the `.count { … }` rule with:

```css
    /* v179 §3.3: the same button as sb-toolbar's Filters button. */
    .trigger {
      display: inline-flex;
      align-items: center;
      gap: var(--space-6);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--control-radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      cursor: pointer;
      transition: border-color var(--transition);
    }
```

```css
    .count {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 1.5em;
      padding: 0 var(--space-4);
      border-radius: var(--chip-radius);
      background: var(--accent-soft);
      color: var(--text);
      font-size: var(--text-chip);
    }
```

The `.count` rule is byte-identical to the toolbar's — the spec asserts exactly that. Leave `.trigger:hover`, `.trigger:focus-visible`, the panel, the checkbox labels and `.reset` as they are (V179-2 owns their hit areas).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/control-bar.spec.ts --include src/app/ui/filter-bar.spec.ts --include src/app/ui/toolbar.spec.ts --include src/app/ui/column-picker.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/workspaces/system/logs-tab.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/all-sources.spec.ts`
Expected: PASS, 0 failed. `breakpoint-guard.spec.ts` stays green: 639 is a declared value, and the guard's regex reads `@container` widths too.  `spacing`, `primitives` and `all-sources` are the repo-wide token, colour and radius gates; every value above is an existing token.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/ui/control-bar.ts frontend/src/app/ui/control-bar.spec.ts frontend/src/app/ui/filter-bar.ts frontend/src/app/ui/filter-bar.spec.ts
git commit -m "fix(ui): one filter row pattern -- phone filter grid, chips on one scrolling line, empty filter bar takes no room (v179)"
git add frontend/src/app/ui/toolbar.ts frontend/src/app/ui/toolbar.spec.ts frontend/src/app/ui/column-picker.ts frontend/src/app/ui/column-picker.spec.ts
git commit -m "fix(ui): Filters and Columns share one control-height button with a count badge (v179)"
```

---

### Task V179-6: Scroll-active-into-view for `sb-tab-bar` and the settings category rail

**Model:** sonnet — a new pure helper module plus two call sites; the only subtlety is the render-effect timing in jsdom.

**Files:**
- Create: `frontend/src/app/ui/scroll-rail.ts`
- Create: `frontend/src/app/ui/scroll-rail.spec.ts`
- Modify: `frontend/src/app/ui/layout.ts` (`TabBar` only, ~l.172-290 — V179-3 has already edited `Panel` and `ControlRow` in the same file; V179-15 edits `Drawer` later)
- Modify: `frontend/src/app/ui/layout.spec.ts`
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts`
- Modify: `frontend/src/app/workspaces/system/settings-tab.spec.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks beyond the tokens (`--bg`, `--space-20`, `--transition` exist today).
- Produces (index Contracts, verbatim):
  ```ts
  // ui/scroll-rail.ts
  export function edgeFades(el: HTMLElement): { start: boolean; end: boolean };
  export function revealActive(container: HTMLElement, active: Element | null): void;   // no-op when scrollIntoView is missing (jsdom)
  ```
  V179-7 imports `edgeFades` for `sb-heat-grid`'s scroll box.

**What is wrong today (spec §2.1, §6b.5).** `sb-tab-bar` (Analytics' seven tabs, System, Reports, Dashboard positions, gallery) already scrolls sideways and fades its edges, but a tab selected from the URL (`/analytics?tab=partials`) can sit off-screen on load, and nothing brings a newly selected tab into view. The System settings group strip is not a tab bar: it is `nav.category-rail` of `sb-button`s (`settings-tab.ts` ~l.95-103), which turns into a horizontal scroller below 640px with **no** fade and no scroll-into-view ("Pip…", "Scan…" cut at the edge).

**Fix.** One small module owns the two measurements — "which edges hide content" and "bring the active item into view along the rail" — and both rails call it after every render in which the active item or the item list changed. `revealActive` uses `scrollIntoView({ block: 'nearest', inline: 'nearest' })`, which scrolls the rail sideways and moves the page only if the item is out of view vertically; it does nothing when the rail does not overflow (so the desktop settings rail, a vertical list, is never touched) and nothing in jsdom, which has no `scrollIntoView`. Plain `overflow-x: auto`, no scroll-snap (spec §6 left it to the builder: snap fights the fade and the reveal on a seven-tab strip).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/scroll-rail.spec.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';

import { edgeFades, revealActive } from './scroll-rail';

/** jsdom lays nothing out: fake the three numbers a rail is measured by. */
function rail(scrollWidth: number, clientWidth: number, scrollLeft = 0): HTMLElement {
  const el = document.createElement('div');
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth });
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(el, 'scrollLeft', { configurable: true, value: scrollLeft });
  return el;
}

function item(): { el: HTMLElement; spy: ReturnType<typeof vi.fn> } {
  const el = document.createElement('button');
  const spy = vi.fn();
  Object.defineProperty(el, 'scrollIntoView', { configurable: true, value: spy });
  return { el, spy };
}

describe('edgeFades (v179 §3.3)', () => {
  it('shows no fade when everything fits', () => {
    expect(edgeFades(rail(300, 300))).toEqual({ start: false, end: false });
  });

  it('fades only the far edge at the start of an overflowing rail', () => {
    expect(edgeFades(rail(600, 300, 0))).toEqual({ start: false, end: true });
  });

  it('fades both edges part-way along', () => {
    expect(edgeFades(rail(600, 300, 150))).toEqual({ start: true, end: true });
  });

  it('fades only the near edge once scrolled to the end', () => {
    expect(edgeFades(rail(600, 300, 300))).toEqual({ start: true, end: false });
  });

  it('ignores a sub-pixel overflow (rounding, not hidden content)', () => {
    expect(edgeFades(rail(301, 300, 0))).toEqual({ start: false, end: false });
  });
});

describe('revealActive (v179 §6b.5)', () => {
  it('brings the active item into view along the rail, never jumping the page', () => {
    const { el, spy } = item();
    revealActive(rail(900, 390), el);
    expect(spy).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' });
  });

  it('does nothing when the rail does not overflow', () => {
    // The desktop settings rail is a vertical list: scrolling it "into view"
    // could only move the page.
    const { el, spy } = item();
    revealActive(rail(300, 300), el);
    expect(spy).not.toHaveBeenCalled();
  });

  it('does nothing without an active item', () => {
    expect(() => revealActive(rail(900, 390), null)).not.toThrow();
  });

  it('does nothing where scrollIntoView is missing (jsdom)', () => {
    const el = document.createElement('button');
    Object.defineProperty(el, 'scrollIntoView', { configurable: true, value: undefined });
    expect(() => revealActive(rail(900, 390), el)).not.toThrow();
  });
});
```

Append to `frontend/src/app/ui/layout.spec.ts` (add `afterEach` and `vi` to the `vitest` import; `Component`, `signal`, `TestBed`, `provideZonelessChangeDetection`, `Tab`, `TabBar`, `SOURCE` and `geometry` already exist in the file):

```ts
@Component({ imports: [TabBar], template: `<sb-tab-bar [tabs]="tabs" [active]="active()" />` })
class ActiveTabHost {
  readonly tabs: Tab[] = [
    { id: 'overview', label: 'Overview' }, { id: 'attribution', label: 'Attribution' },
    { id: 'execution', label: 'Execution' }, { id: 'edge', label: 'Edge' },
    { id: 'pipeline', label: 'Pipeline' }, { id: 'tuning', label: 'Tuning' },
    { id: 'partials', label: 'Partials' },
  ];
  readonly active = signal('overview');
}

/** Every element overflows: 900px of tabs in a 390px phone. Defined on the
 *  prototype so it holds before the first render, which is when the reveal
 *  for a tab chosen by the URL runs. */
function overflowEverything(): () => void {
  Object.defineProperty(HTMLElement.prototype, 'scrollWidth', { configurable: true, get: () => 900 });
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 390 });
  return () => {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>)['scrollWidth'];
    delete (HTMLElement.prototype as unknown as Record<string, unknown>)['clientWidth'];
  };
}

describe('sb-tab-bar keeps the active tab in view (v179 §6b.5)', () => {
  let spy: ReturnType<typeof vi.fn>;
  let restore: () => void;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    spy = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: spy });
    restore = overflowEverything();
  });

  afterEach(() => {
    restore();
    delete (HTMLElement.prototype as unknown as Record<string, unknown>)['scrollIntoView'];
  });

  async function mount(active: string) {
    const f = TestBed.createComponent(ActiveTabHost);
    f.componentInstance.active.set(active);
    f.detectChanges();
    await f.whenStable();
    f.detectChanges();
    return f;
  }

  const revealed = () => (spy.mock.contexts.at(-1) as HTMLElement | undefined)?.textContent?.trim();

  it('reveals a tab chosen by the URL on first render', async () => {
    await mount('partials');
    expect(spy).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' });
    expect(revealed()).toBe('Partials');
  });

  it('reveals the newly active tab whenever the active tab changes', async () => {
    const f = await mount('overview');
    spy.mockClear();
    f.componentInstance.active.set('tuning');
    f.detectChanges();
    await f.whenStable();
    expect(revealed()).toBe('Tuning');
  });

  it('re-measures the fades after revealing', async () => {
    const f = await mount('overview');
    const strip = (f.nativeElement as HTMLElement).querySelector('.strip')!;
    // scrollLeft 0 on a 900/390 rail: more tabs off to the right only.
    expect(strip.classList).toContain('fade-end');
    expect(strip.classList).not.toContain('fade-start');
  });

  it('measures through the shared rail helper, not a private copy', () => {
    expect(SOURCE).toMatch(/import \{ edgeFades, revealActive \} from '\.\/scroll-rail';/);
    expect(SOURCE).toContain('afterRenderEffect(');
  });
});
```

Append to `frontend/src/app/workspaces/system/settings-tab.spec.ts` (add `afterEach`, `beforeEach` and `vi` to the `vitest` import, and `SettingField` to the `../../api/models` import):

```ts
/* -- v179 §6b.5 -- the settings category rail fades and reveals ----------- */

function field(key: string): SettingField {
  return {
    key, label: key, type: 'str', value: 'x', default: 'x', help: '',
    min: null, max: null, step: null, options: [], sensitive: false, hot_reloadable: true,
  };
}

const RAIL_SECTIONS = ['Discord', 'Scanning', 'Pipeline', 'Risk'].map((name) => ({
  name, icon: 'settings', description: '', fields: [field(name.toLowerCase())],
}));

function railGeometry(el: HTMLElement, scrollWidth: number, clientWidth: number, scrollLeft: number): void {
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth });
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(el, 'scrollLeft', { configurable: true, value: scrollLeft });
}

describe('Settings category rail (v179 §6b.5)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/system/settings-tab.ts'), 'utf8');
  let spy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    spy = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: spy });
  });

  afterEach(() => {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>)['scrollIntoView'];
  });

  async function loaded() {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/system/settings').flush(payload({ sections: RAIL_SECTIONS }));
    await fixture.whenStable();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    return { fixture, el, rail: el.querySelector('nav.category-rail') as HTMLElement };
  }

  it('fades the far edge while more categories sit off-screen', async () => {
    const { fixture, el, rail } = await loaded();
    railGeometry(rail, 700, 358, 0);
    rail.dispatchEvent(new Event('scroll'));
    fixture.detectChanges();
    const strip = el.querySelector('.rail-strip')!;
    expect(strip.classList).toContain('fade-end');
    expect(strip.classList).not.toContain('fade-start');
  });

  it('brings the chosen category into view along the rail', async () => {
    const { fixture, rail } = await loaded();
    railGeometry(rail, 700, 358, 0);
    const risk = [...rail.querySelectorAll('button')].find((b) => b.textContent!.includes('Risk'))!;
    risk.click();
    fixture.detectChanges();
    await fixture.whenStable();
    expect((spy.mock.contexts.at(-1) as HTMLElement).textContent).toContain('Risk');
  });

  it('draws the fades with the same gradient as sb-tab-bar', () => {
    expect(src).toMatch(/\.rail-strip::before \{[^}]*linear-gradient\(to right, var\(--bg\), transparent\)/);
    expect(src).toMatch(/\.rail-strip\.fade-start::before, \.rail-strip\.fade-end::after \{ opacity: 1; \}/);
  });

  it('re-measures on window resize and lets the strip shrink in the phone layout', () => {
    expect(src).toContain(`'(window:resize)': 'measureRail()'`);
    expect(src).toMatch(/\.rail-strip \{[^}]*min-width: 0;/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/scroll-rail.spec.ts --include src/app/ui/layout.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts`
Expected: FAIL — `./scroll-rail` cannot be resolved; `scrollIntoView` never called by `TabBar`; no `.rail-strip` in the settings tab.

- [ ] **Step 3: Create `ui/scroll-rail.ts`**

Create `frontend/src/app/ui/scroll-rail.ts`:

```ts
/**
 * Shared measuring for a rail that scrolls sideways — v179 §3.3, §6b.5.
 *
 * Two rails need the same two answers: `sb-tab-bar` (Analytics' seven tabs on
 * a phone) and the System settings `nav.category-rail`. `sb-heat-grid`'s
 * scroll box uses the first. Before this module only the tab bar measured
 * its fades, and neither rail brought the active item into view, so a tab
 * chosen by the URL could load off-screen with nothing pointing at it.
 *
 * Pure DOM reads, no Angular: each caller decides when to call (after the
 * render in which its active item or its item list changed, and on scroll
 * and resize for the fades).
 */

/** Which edges currently hide content. 1px of slack absorbs sub-pixel
 *  rounding, which is not hidden content. */
export function edgeFades(el: HTMLElement): { start: boolean; end: boolean } {
  const overflow = el.scrollWidth - el.clientWidth;
  return {
    start: overflow > 1 && el.scrollLeft > 1,
    end: overflow > 1 && el.scrollLeft < overflow - 1,
  };
}

/**
 * Scroll `active` into view along `container`, if the container overflows.
 *
 * `block: 'nearest'` moves the page only when the item is out of view
 * vertically (it never is on load or after a click on it); `inline:
 * 'nearest'` scrolls the rail the least distance that shows the whole item.
 * A rail that does not overflow is left alone, so a vertical list (the
 * desktop settings rail) can never move the page. jsdom has no
 * `scrollIntoView`; the call is then a no-op rather than an error.
 */
export function revealActive(container: HTMLElement, active: Element | null): void {
  if (!active) return;
  const reveal = (active as HTMLElement).scrollIntoView as HTMLElement['scrollIntoView'] | undefined;
  if (typeof reveal !== 'function') return;
  if (container.scrollWidth - container.clientWidth <= 1) return;
  reveal.call(active, { block: 'nearest', inline: 'nearest' });
}
```

- [ ] **Step 4: Wire `TabBar`**

In `frontend/src/app/ui/layout.ts`:

1. In the `@angular/core` import list replace `afterNextRender,` with `afterRenderEffect,` (`TabBar`'s constructor is the file's only `afterNextRender` user — confirm with `git grep -n afterNextRender frontend/src/app/ui/layout.ts`; keep the import if another user appeared). Add below the other local imports:

```ts
import { edgeFades, revealActive } from './scroll-rail';
```

2. Replace `TabBar`'s constructor and `measure()`:

```ts
  constructor() {
    // v179 §6b.5: after every render in which the active tab or the tab list
    // changed -- including the first, so a tab chosen by the URL is not left
    // off-screen -- bring the active tab into view, then re-measure the fades.
    afterRenderEffect(() => {
      this.active();
      this.tabs();
      untracked(() => this.reveal());
    });
  }

  protected measure(): void {
    const fades = edgeFades(this.tabList().nativeElement);
    this.fadeStart.set(fades.start);
    this.fadeEnd.set(fades.end);
  }

  private reveal(): void {
    const list = this.tabList().nativeElement;
    revealActive(list, list.querySelector('[role="tab"][aria-selected="true"]'));
    this.measure();
  }
```

`untracked` is already imported in `layout.ts`. The host `(window:resize)` and the `.tabs` `(scroll)` bindings stay as they are.

- [ ] **Step 5: Wire the settings category rail**

In `frontend/src/app/workspaces/system/settings-tab.ts`:

1. Imports — replace the first line and add the helper:

```ts
import {
  ChangeDetectionStrategy, Component, ElementRef, afterRenderEffect, computed, inject, signal, untracked, viewChild,
} from '@angular/core';
```

```ts
import { edgeFades, revealActive } from '../../ui/scroll-rail';
```

2. `@Component` metadata — add (the component has no `host` today):

```ts
  host: { '(window:resize)': 'measureRail()' },
```

3. Template — wrap the rail; the buttons are unchanged:

```html
    <div class="rail-strip" [class.fade-start]="railFades().start" [class.fade-end]="railFades().end">
    <nav #rail class="category-rail" aria-label="Settings categories" (scroll)="measureRail()">
      @for (category of categories(); track category.id) {
        <button sb-button variant="ghost" type="button"
                [class.active]="activeCategory() === category.id"
                (click)="activeCategory.set(category.id)">
          {{ category.label }} <span>{{ category.keys.length }}</span>
        </button>
      }
    </nav>
    </div>
```

4. Styles — replace the `.category-rail { display: grid; … }` line and the `@media (max-width: 639px) { .settings-layout … }` line with:

```css
    /* v179 §6b.5: the strip carries the edge fades, the nav scrolls inside it
       (the same fade as sb-tab-bar). min-width: 0 lets the strip shrink in
       the one-column phone layout instead of widening the page. */
    .rail-strip { position: relative; min-width: 0; align-self: start; }
    .rail-strip::before, .rail-strip::after {
      content: ''; position: absolute; top: 0; bottom: 0; width: var(--space-20);
      pointer-events: none; opacity: 0; transition: opacity var(--transition);
    }
    .rail-strip::before { left: 0; background: linear-gradient(to right, var(--bg), transparent); }
    .rail-strip::after { right: 0; background: linear-gradient(to left, var(--bg), transparent); }
    .rail-strip.fade-start::before, .rail-strip.fade-end::after { opacity: 1; }
    .category-rail { display: grid; align-content: start; gap: var(--space-4); }
    @media (max-width: 639px) {
      .settings-layout { grid-template-columns: minmax(0, 1fr); }
      .category-rail { grid-auto-flow: column; grid-auto-columns: max-content; overflow-x: auto; scrollbar-width: none; }
    }
```

Keep the `.category-rail button`, `.category-rail button.active` and `.category-rail span` lines as they are.

5. Class — add beside `activeCategory`:

```ts
  private readonly rail = viewChild<ElementRef<HTMLElement>>('rail');
  protected readonly railFades = signal({ start: false, end: false });

  constructor() {
    // v179 §6b.5: the rail only exists once settings have loaded (it sits
    // inside the sb-async body), hence the optional viewChild. Reveal the
    // chosen category and re-measure after every render that changed it.
    afterRenderEffect(() => {
      this.activeCategory();
      this.categories();
      const rail = this.rail()?.nativeElement;
      if (!rail) return;
      untracked(() => {
        revealActive(rail, rail.querySelector('button.active'));
        this.measureRail();
      });
    });
  }

  protected measureRail(): void {
    const rail = this.rail()?.nativeElement;
    if (rail) this.railFades.set(edgeFades(rail));
  }
```

If `SettingsTab` already declares a constructor by the time this task runs, put the `afterRenderEffect(...)` call at its end instead of adding a second constructor.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/scroll-rail.spec.ts --include src/app/ui/layout.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts --include src/app/workspaces/analytics/analytics.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/all-sources.spec.ts`
Expected: PASS, 0 failed. The existing v80 D4 fade tests in `layout.spec.ts` keep passing unchanged (`measure()` gives the same answers through `edgeFades`).

If the render-effect tests see no call, the first thing to check is the flush: `fixture.whenStable()` runs the after-render hooks under zoneless TestBed in this repo (`shell/nav-indicator.spec.ts` relies on it for `afterNextRender`). If it does not for `afterRenderEffect`, add `TestBed.tick();` after `f.detectChanges()` in `mount()` — do not weaken the assertions.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/scroll-rail.ts frontend/src/app/ui/scroll-rail.spec.ts frontend/src/app/ui/layout.ts frontend/src/app/ui/layout.spec.ts
git commit -m "feat(ui): sb-tab-bar scrolls the active tab into view; edge fades measured by ui/scroll-rail (v179)"
git add frontend/src/app/workspaces/system/settings-tab.ts frontend/src/app/workspaces/system/settings-tab.spec.ts
git commit -m "fix(system): settings category rail fades its edges and reveals the active category on a phone (v179)"
```

---

### Task V179-7: Chart and grid containment

**Model:** sonnet — five compact (partly minified) chart primitives; exact substring edits and one small SVG geometry change.

**Files:**
- Modify: `frontend/src/app/ui/heat-grid.ts`
- Modify: `frontend/src/app/ui/heat-grid.spec.ts`
- Modify: `frontend/src/app/ui/bar-list.ts`
- Modify: `frontend/src/app/ui/bar-list.spec.ts`
- Modify: `frontend/src/app/ui/histogram.ts`
- Modify: `frontend/src/app/ui/histogram.spec.ts`
- Modify: `frontend/src/app/ui/share-bar.ts`
- Modify: `frontend/src/app/ui/share-bar.spec.ts`
- Modify: `frontend/src/app/ui/waterfall.ts`
- Modify: `frontend/src/app/ui/waterfall.spec.ts`

**Interfaces:**
- Consumes: `edgeFades(el: HTMLElement): { start: boolean; end: boolean }` from `frontend/src/app/ui/scroll-rail.ts` (created by V179-6 — this task runs after it, see the part header).
- Produces: a two-line `sb-bar-list` item under a narrow container (the ledger's "Creates" entry); every chart primitive's host can shrink (`min-width: 0`) and never paints past its own box. No input or output changes on any of the five components.

**What is wrong today (spec §2.1).** Analytics → Attribution at 390px: the Strategy × horizon `sb-heat-grid` clips after `7m` with 8m/9m off-screen and no sign of them; `sb-bar-list` puts its `n=` column at x=462 and its value at x=398 (fixed tracks `5.5rem minmax(0,1fr) 4rem 3.5rem` plus gaps do not fit a ~330px panel body); `sb-waterfall` value labels and long strategy names paint outside the SVG (`overflow: visible`, value text anchored past the plot's right edge). Partials repeats the bar-list and adds `sb-histogram` and `sb-share-bar`. Part of this is the page grid around them (V179-8 fixes that, after reproducing it); this task makes each primitive contain itself whatever box it is given (spec §3.3 "Charts and grids": reflow to the container, or scroll inside their own box with a visible edge fade; never widen the page).

**Per primitive:**
- `sb-heat-grid` scrolls inside its own box (a 9-column grid cannot reflow into 330px and stay readable) with the same edge fade as `sb-tab-bar`, measured by `edgeFades` on render, scroll and resize.
- `sb-bar-list` reflows: when its own container is narrower than 26rem it becomes a two-line item — label, value and `n=` on line 1, the bar on line 2 (spec §3.3). 26rem is the list's own need (9rem label + 5rem value + 4.5rem n + three gaps + a bar worth reading), not a viewport breakpoint; it is a container query on the component, so it tracks the panel the list sits in, at every device. The old `@media (max-width: 639px)` track squeeze is removed — every phone panel is below 26rem, so it was dead and still overflowed.
- `sb-waterfall` reserves room for its value labels inside the viewBox and shortens long labels (full label in an SVG `<title>` and in the existing tooltip), then clips with `overflow: hidden`.
- `sb-histogram` and `sb-share-bar` only lacked a shrinkable host; the share-bar legend may now break inside an item.

- [ ] **Step 1: Write the failing tests**

In every spec below, move the new `import` lines to the top of the file with the existing ones.

Append to `frontend/src/app/ui/heat-grid.spec.ts` (a new line after the existing one-line file):

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const HEAT_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/heat-grid.ts'), 'utf8');

function setGeometry(el: HTMLElement, scrollWidth: number, clientWidth: number, scrollLeft: number): void {
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth });
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(el, 'scrollLeft', { configurable: true, value: scrollLeft });
}

describe('HeatGrid containment (v179 §3.3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function wide() {
    const f = TestBed.createComponent(HeatGrid);
    const cols = ['1w', '2w', '3w', '1m', '2m', '3m', '6m', '7m', '8m', '9m'];
    f.componentRef.setInput('rows', ['MACD', 'RSI']);
    f.componentRef.setInput('cols', cols);
    f.componentRef.setInput('cells', cols.flatMap((_, c) => [0, 1].map((r) => ({ r, c, n: 40, value: c / 10 - 0.4 }))));
    f.detectChanges();
    return { f, el: f.nativeElement as HTMLElement };
  }

  it('keeps every column in the DOM -- 8m and 9m scroll into view, they are not dropped', () => {
    const { el } = wide();
    const headers = [...el.querySelectorAll('thead th[scope="col"]')].map((th) => th.textContent!.trim());
    expect(headers.slice(-2)).toEqual(['8m', '9m']);
  });

  it('fades the far edge while columns sit off-screen', () => {
    const { f, el } = wide();
    const box = el.querySelector('.scroll-x') as HTMLElement;
    setGeometry(box, 700, 330, 0);
    box.dispatchEvent(new Event('scroll'));
    f.detectChanges();
    const frame = el.querySelector('.frame')!;
    expect(frame.classList).toContain('fade-end');
    expect(frame.classList).not.toContain('fade-start');
  });

  it('shrinks with its panel and scrolls only inside its own box', () => {
    expect(HEAT_SOURCE).toContain(':host{display:block;min-width:0;max-width:100%}');
    expect(HEAT_SOURCE).toContain('.scroll-x{overflow-x:auto}');
    expect(HEAT_SOURCE).toContain("import{edgeFades}from'./scroll-rail'");
  });
});
```

Append to `frontend/src/app/ui/bar-list.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const BAR_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/bar-list.ts'), 'utf8');

describe('BarList narrow container (v179 §3.3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('is its own size container and can shrink inside a grid', () => {
    expect(BAR_SOURCE).toContain(':host{display:block;min-width:0;container:bar-list/inline-size}');
  });

  it('drops to two lines -- label, value and n, then the bar -- in a narrow box', () => {
    const narrow = BAR_SOURCE.match(/@container bar-list \(max-width: 26rem\)\{([\s\S]*?\})\}/)?.[1] ?? '';
    expect(narrow).toContain("grid-template-areas:'label value n' 'track track track'");
    expect(narrow).toContain('grid-template-columns:minmax(0,1fr) auto auto');
    for (const area of ['.label{grid-area:label}', '.track{grid-area:track}', '.value{grid-area:value}', '.n{grid-area:n}']) {
      expect(narrow).toContain(area);
    }
  });

  it('no longer squeezes fixed tracks by viewport width', () => {
    expect(BAR_SOURCE).not.toContain('@media(max-width:639px)');
  });

  it('still renders label, bar, value and n for every row -- nothing is dropped', () => {
    const el = render([{ label: 'Saturday', value: 12.5, n: 41 }]);
    const li = el.querySelector('li')!;
    expect(li.querySelector('.label')!.textContent).toBe('Saturday');
    expect(li.querySelector('.track')).not.toBeNull();
    expect(li.querySelector('.value')!.textContent!.trim()).toBe('12.5%');
    expect(li.querySelector('.n')!.textContent!.trim()).toBe('n=41');
  });
});
```

Append to `frontend/src/app/ui/histogram.spec.ts` (it already imports `readFileSync` and `join`):

```ts
describe('Histogram containment (v179 §3.3)', () => {
  it('has a host that can shrink inside a grid track', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/ui/histogram.ts'), 'utf8');
    expect(src).toMatch(/:host \{ display: block; min-width: 0; \}/);
  });
});
```

Append to `frontend/src/app/ui/share-bar.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('ShareBar containment (v179 §3.3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/share-bar.ts'), 'utf8');

  it('has a host that can shrink inside a grid track', () => {
    expect(src).toContain(':host { display:block; min-width:0; }');
  });

  it('lets a long legend item break instead of pushing the page wide', () => {
    expect(src).toMatch(/\.legend li \{[^}]*min-width:0;[^}]*flex-wrap:wrap;/);
    expect(src).toMatch(/\.legend li span:not\(\.key\) \{ overflow-wrap:anywhere; \}/);
  });
});
```

Append to `frontend/src/app/ui/waterfall.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/* Mirrors waterfall.ts: W = 320 (viewBox width), LABEL_W = 96, VALUE_W = 44. */
const W = 320, LABEL_W = 96, VALUE_W = 44;

describe('Waterfall containment (v179 §3.3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function render(steps: { label: string; value: number }[]) {
    const fixture = TestBed.createComponent(Waterfall);
    fixture.componentRef.setInput('steps', steps);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('keeps every value label inside the viewBox, on both sides of zero', () => {
    const el = render([
      { label: 'MACD', value: 40 }, { label: 'RSI', value: -55 }, { label: 'Bollinger', value: 30 },
    ]);
    for (const text of el.querySelectorAll<SVGTextElement>('text.value')) {
      const x = Number(text.getAttribute('x'));
      if (text.getAttribute('text-anchor') === 'start') expect(x + VALUE_W).toBeLessThanOrEqual(W);
      else expect(x - VALUE_W).toBeGreaterThanOrEqual(LABEL_W);
    }
  });

  it('shortens a long label to fit its column and keeps the full name as a title', () => {
    const el = render([{ label: 'Support bounce with volume confirmation', value: 2 }]);
    const label = el.querySelector('text.label')!;
    expect(label.firstChild!.textContent!.trim()).toBe('Support bounc…');
    expect(label.querySelector('title')!.textContent).toBe('Support bounce with volume confirmation');
  });

  it('clips at its own box instead of painting past it', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/ui/waterfall.ts'), 'utf8');
    expect(src).toContain('svg { display:block; overflow:hidden; }');
    expect(src).toContain(':host { display:block; min-width:0; }');
  });
});
```

`'Support bounc…'` is the first 13 characters plus `…` — 14 characters, the `LABEL_CHARS` cap below.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/heat-grid.spec.ts --include src/app/ui/bar-list.spec.ts --include src/app/ui/histogram.spec.ts --include src/app/ui/share-bar.spec.ts --include src/app/ui/waterfall.spec.ts`
Expected: FAIL — no `.frame`, no host rules, no `@container bar-list`, the `@media(max-width:639px)` squeeze still present, a waterfall value label past `W - VALUE_W`, long labels unshortened, `overflow:visible`. The "nothing is dropped" and "keeps every column" tests already pass.

- [ ] **Step 3: Contain `sb-heat-grid`**

`frontend/src/app/ui/heat-grid.ts` is two minified lines; make these exact substring replacements (no reformatting, so the diff stays reviewable):

1. Imports — replace `import{ChangeDetectionStrategy,Component,computed,input,signal}from'@angular/core';` with:

```ts
import{ChangeDetectionStrategy,Component,ElementRef,afterRenderEffect,computed,input,signal,untracked,viewChild}from'@angular/core';import{edgeFades}from'./scroll-rail';
```

2. Decorator — replace `selector:'sb-heat-grid',changeDetection:ChangeDetectionStrategy.OnPush,` with:

```ts
selector:'sb-heat-grid',changeDetection:ChangeDetectionStrategy.OnPush,host:{'(window:resize)':'measure()'},
```

3. Template start — replace `` template:`<div class="host scroll-x" #host><table> `` with:

```ts
template:`<div class="frame" [class.fade-start]="fades().start" [class.fade-end]="fades().end"><div class="host scroll-x" #host (scroll)="measure()"><table>
```

4. Template end — replace `` [hostWidth]="host.clientWidth"/></div>` `` with:

```ts
[hostWidth]="host.clientWidth"/></div></div>`
```

5. Styles start — replace `` styles:`.host{position:relative}.scroll-x{overflow-x:auto} `` with (same fade as `sb-tab-bar`, on the panel surface the grid sits on):

```ts
styles:`:host{display:block;min-width:0;max-width:100%}.frame{position:relative}.frame::before,.frame::after{content:'';position:absolute;top:0;bottom:0;width:var(--space-20);pointer-events:none;opacity:0;transition:opacity var(--transition);z-index:1}.frame::before{left:0;background:linear-gradient(to right,var(--surface),transparent)}.frame::after{right:0;background:linear-gradient(to left,var(--surface),transparent)}.frame.fade-start::before,.frame.fade-end::after{opacity:1}.host{position:relative}.scroll-x{overflow-x:auto}
```

6. Class body — replace `export class HeatGrid{` with:

```ts
export class HeatGrid{private readonly box=viewChild.required<ElementRef<HTMLElement>>('host');protected readonly fades=signal({start:false,end:false});constructor(){afterRenderEffect(()=>{this.cols();this.cells();untracked(()=>this.measure())})}protected measure(){this.fades.set(edgeFades(this.box().nativeElement))}
```

The table keeps `width:100%`: in the scroll box it grows to its content's minimum when the panel is narrower, and the box scrolls; the fades say so. The tooltip still positions against `.host` (unchanged).

- [ ] **Step 4: Reflow `sb-bar-list`**

In `frontend/src/app/ui/bar-list.ts`'s `styles` string:

1. Replace `:host{display:block}` with:

```css
:host{display:block;min-width:0;container:bar-list/inline-size}
```

2. Replace `@media(max-width:639px){li{grid-template-columns:5.5rem minmax(0,1fr) 4rem 3.5rem}}` with:

```css
@container bar-list (max-width: 26rem){li{grid-template-columns:minmax(0,1fr) auto auto;grid-template-areas:'label value n' 'track track track';row-gap:var(--space-4)}.label{grid-area:label}.track{grid-area:track}.value{grid-area:value}.n{grid-area:n}}
```

Then add, directly above the `@Component({selector:'sb-bar-list'` line, a comment that records the threshold's origin (the minified line stays as it is):

```ts
/* v179 §3.3: below a 26rem CONTAINER the item is two lines -- label, value and
 * n= on the first, the bar on the second. 26rem is the list's own minimum
 * (9rem label + 5rem value + 4.5rem n + gaps + a readable bar), measured on
 * the panel it sits in, so it is a container size, not one of BREAKPOINTS'
 * viewport widths. The old @media (max-width: 639px) squeeze overflowed every
 * phone panel and is gone. */
```

- [ ] **Step 5: Contain `sb-histogram`, `sb-share-bar` and `sb-waterfall`**

`frontend/src/app/ui/histogram.ts` — make the first rule inside `styles` (before the `/* The reference line sits …` comment):

```css
    :host { display: block; min-width: 0; }
```

`frontend/src/app/ui/share-bar.ts` — in `styles`, replace `.host { position:relative; }` with `:host { display:block; min-width:0; } .host { position:relative; }`, and replace `.legend li { display:inline-flex; align-items:center; gap:var(--space-6); color:var(--text-secondary); }` with:

```css
.legend li { display:inline-flex; align-items:center; gap:var(--space-6); min-width:0; flex-wrap:wrap; color:var(--text-secondary); } .legend li span:not(.key) { overflow-wrap:anywhere; }
```

`frontend/src/app/ui/waterfall.ts`:

1. Replace `const W = 320, ROW = 22, LABEL_W = 96, PAD = 8;` with:

```ts
/* v179 §3.3: VALUE_W reserves room for a value label on each side of the
 * plot, so labels anchored past a bar's end stay inside the viewBox;
 * LABEL_CHARS caps a strategy name to what fits in LABEL_W at 11px. */
const W = 320, ROW = 22, LABEL_W = 96, PAD = 8, VALUE_W = 44, LABEL_CHARS = 14;
```

2. Replace the body of `x()` — `return LABEL_W + PAD + (value - min) / (max - min || 1) * (W - LABEL_W - 2 * PAD);` — with:

```ts
return LABEL_W + PAD + VALUE_W + (value - min) / (max - min || 1) * (W - LABEL_W - 2 * PAD - 2 * VALUE_W);
```

3. Add after `x()`:

```ts
  protected short(label: string): string { return label.length > LABEL_CHARS ? `${label.slice(0, LABEL_CHARS - 1)}…` : label; }
```

4. In the template replace `text-anchor="end">{{ row.label }}</text>` with:

```html
text-anchor="end">{{ short(row.label) }}<title>{{ row.label }}</title></text>
```

5. In `styles` replace `.host { position:relative; } svg { display:block; overflow:visible; }` with:

```css
:host { display:block; min-width:0; } .host { position:relative; } svg { display:block; overflow:hidden; }
```

Arithmetic the test relies on: the plot spans x = 96 + 8 + 44 = 148 to 148 + (320 − 96 − 16 − 88) = 268. A right-anchored value sits at most at 268 + 4 = 272, and 272 + 44 = 316 ≤ 320; a left-anchored one at least at 148 − 4 = 144, and 144 − 44 = 100 ≥ 96.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/heat-grid.spec.ts --include src/app/ui/bar-list.spec.ts --include src/app/ui/histogram.spec.ts --include src/app/ui/share-bar.spec.ts --include src/app/ui/waterfall.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/all-sources.spec.ts --include src/app/workspaces/analytics/tabs/attribution.spec.ts --include src/app/workspaces/analytics/tabs/partials.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts`
Expected: PASS, 0 failed. The existing heat-grid, bar-list, share-bar and waterfall assertions (tones, widths, `runs()`) are unchanged: only layout, label text and x positions moved, and the original waterfall test checks tones and `runs()`, not x.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/heat-grid.ts frontend/src/app/ui/heat-grid.spec.ts frontend/src/app/ui/bar-list.ts frontend/src/app/ui/bar-list.spec.ts
git commit -m "fix(ui): heat grid scrolls in its own faded box; bar list drops to two lines in a narrow panel (v179)"
git add frontend/src/app/ui/histogram.ts frontend/src/app/ui/histogram.spec.ts frontend/src/app/ui/share-bar.ts frontend/src/app/ui/share-bar.spec.ts frontend/src/app/ui/waterfall.ts frontend/src/app/ui/waterfall.spec.ts
git commit -m "fix(ui): histogram, share bar and waterfall stay inside their box at phone widths (v179)"
```

---

### Task V179-8: Partials and Attribution overflow — browser repro, root-cause fix, Parts 1–2 browser check

**Model:** sonnet — a measured browser reproduction drives a two-line CSS fix; then the three-width check over everything Parts 1–2 changed.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/partials.ts`
- Modify: `frontend/src/app/workspaces/analytics/tabs/partials.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/tabs/attribution.ts`
- Modify: `frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts`

**Interfaces:**
- Consumes: the finished primitives of V179-1..V179-7 (floored text tokens, hit areas, baseline panels, single-variant stat tile, filter row, tab reveal, contained charts).
- Produces: nothing later tasks import. The browser check's findings, if any, are fixed in the file the finding traces to (a Part 1–2 file) and committed with this task.

**What the code says before measuring (spec §6b.7).** Partials' `.kpis` is already `repeat(auto-fit,minmax(10rem,1fr))`, so the stat-tile grid is not the origin. Two rules in both tabs are the prime suspects:
- `:host{display:grid;…}` with no `grid-template-columns`: the single implicit column is `auto`, sized to its widest child's min-content, so one wide child widens the whole tab — `.kpis` included, which is why the right stat tile was cut at x=418. `Analytics` itself already uses `grid-template-columns: minmax(0, 1fr)` for exactly this reason.
- the phone rule `@media (max-width: 639px) { .panels { grid-template-columns: 1fr } }`: a bare `1fr` is `minmax(auto, 1fr)`, whose minimum is the widest panel's min-content — Partials' seven-column `.breakdown` table, Attribution's heat grid and table. The desktop rule above it already says `minmax(0, 1fr)`.

Spec §6b.7 requires reproducing before fixing: the measurement decides, not this paragraph.

- [ ] **Step 1: Serve the worktree build locally and sign in**

Run `/replicate-prod-db` (production data into the local replica), then from the worktree root:

```bash
cd frontend && npm run build && cd ..
python admin_ui.py            # serves the SPA at http://localhost:1234 -- leave running (run_in_background)
node frontend/scripts/browse.mjs login --base http://localhost:1234
```

`browse.mjs` signs in with `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded from `.env` inside the script, never printed, into its persistent profile.

- [ ] **Step 2: Reproduce and find the outermost overflowing box**

Write this throwaway script outside the repo (it is a diagnostic, not a deliverable — V179-19 builds the checked-in audit):

```bash
REPRO="$(mktemp -d)" && cat > "$REPRO/widest.mjs" <<'JS'
// Usage (from frontend/): node "$REPRO/widest.mjs" http://localhost:1234 "/analytics?tab=partials" 390
import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { join } from 'node:path';
const require = createRequire(join(process.cwd(), 'package.json'));
const { chromium } = require('playwright');
const [base, path, width] = [process.argv[2], process.argv[3], Number(process.argv[4] ?? 390)];
const profile = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const context = await chromium.launchPersistentContext(profile, {
  headless: true, viewport: { width, height: 900 }, isMobile: width < 640, hasTouch: width < 640,
});
try {
  const page = await context.newPage();
  await page.goto(base + path);
  await page.waitForFunction(() => {
    const main = document.querySelector('main');
    return !!main && main.innerText.length > 200 && !/Loading/.test(main.innerText);
  }, null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  const report = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const name = (el) => el.tagName.toLowerCase() + (el.classList.length ? '.' + [...el.classList].join('.') : '');
    const offenders = [...document.querySelectorAll('main *')].filter((el) => el.getBoundingClientRect().right > vw + 1);
    // Outermost first: an offender whose parent does not overflow is where the widening starts.
    const roots = offenders.filter((el) => !offenders.includes(el.parentElement));
    return {
      scrollX: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - vw,
      roots: roots.slice(0, 12).map((el) => {
        const cs = getComputedStyle(el.parentElement);
        return `${name(el)} right=${Math.round(el.getBoundingClientRect().right)} parent=${name(el.parentElement)} parentDisplay=${cs.display} parentCols="${cs.gridTemplateColumns}" minContent=${el.scrollWidth}`;
      }),
    };
  });
  console.log(`${path} @${width}: page-scroll-x=${report.scrollX}`);
  for (const line of report.roots) console.log('  ' + line);
} finally {
  await context.close();
}
JS
cd frontend
node "$REPRO/widest.mjs" http://localhost:1234 "/analytics?tab=partials" 390
node "$REPRO/widest.mjs" http://localhost:1234 "/analytics?tab=attribution" 390
cd ..
```

Expected (the bug, reproduced): `page-scroll-x` > 0 on both tabs (spec §2.1: Partials 58px, Attribution 102px — V179-7 has already removed the bar-list and waterfall share, so the numbers may be smaller). Read the `roots`: the outermost offender and its parent's computed `grid-template-columns` name the rule that widens the page. Write the two `path @390: page-scroll-x=… / root …` lines into the commit message of Step 6.

- If the roots are the tab's own `.panels` / `.kpis` children (parent `sb-partials-tab` or `sb-attribution-tab` with a single `auto` or wide pixel column), the suspects above are confirmed: apply Steps 3–5 as written.
- If a root sits somewhere else (for example inside one primitive), fix it in that primitive's file instead, add a source-text test for that rule to the primitive's spec in the same style as Step 3, and still apply Steps 3–5 — the bare `1fr` and implicit `auto` column remain latent defects of the same kind.

- [ ] **Step 3: Write the failing tests**

Append to `frontend/src/app/workspaces/analytics/tabs/partials.spec.ts` (it already imports `readFileSync` and `join`):

```ts
describe('partials.ts never widens the page (v179 §2.1, §6b.7)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/tabs/partials.ts'), 'utf8');

  it('sizes its one column to the tab, not to its widest child', () => {
    expect(src).toContain(':host{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--space-14)}');
  });

  it('keeps the phone panel track shrinkable', () => {
    expect(src).toContain('@media(max-width:639px){.panels{grid-template-columns:minmax(0,1fr)}}');
    expect(src).not.toMatch(/\.panels\{grid-template-columns:1fr\}/);
  });

  it('scrolls the seven-column breakdown table inside its panel', () => {
    expect(src).toContain('<div class="table-scroll"><table class="breakdown">');
    expect(src).toContain('.table-scroll{overflow-x:auto;max-width:100%}');
  });

  it('keeps every breakdown column -- scrolling, not dropping', () => {
    const { el } = render(PARTIALS_FIXTURE);
    expect([...el.querySelectorAll('.breakdown thead th')]).toHaveLength(7);
  });
});
```

Append to `frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts` (it already imports `readFileSync` and `join`):

```ts
describe('attribution.ts never widens the page (v179 §2.1)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/tabs/attribution.ts'), 'utf8');

  it('sizes its one column to the tab, not to its widest child', () => {
    expect(src).toMatch(/:host \{ display: grid; grid-template-columns: minmax\(0, 1fr\); gap: var\(--space-14\); \}/);
  });

  it('keeps the phone panel track shrinkable', () => {
    expect(src).toContain('@media (max-width: 639px) { .panels { grid-template-columns: minmax(0, 1fr); } }');
    expect(src).not.toMatch(/\.panels \{ grid-template-columns: 1fr; \}/);
  });
});
```

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/partials.spec.ts --include src/app/workspaces/analytics/tabs/attribution.spec.ts`
Expected: FAIL on the host, phone-track and table-scroll assertions; the "every breakdown column" test passes.

- [ ] **Step 4: Fix Partials**

In `frontend/src/app/workspaces/analytics/tabs/partials.ts`:

1. Template — wrap the breakdown table (the closing `</table>` gains a `</div>`):

```html
            <div class="table-scroll"><table class="breakdown">
```

```html
            </table></div></sb-panel>
```

2. `styles` — three exact replacements in the minified string:
   - `:host{display:grid;gap:var(--space-14)}` → `:host{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--space-14)}`
   - `@media(max-width:639px){.panels{grid-template-columns:1fr}}` → `@media(max-width:639px){.panels{grid-template-columns:minmax(0,1fr)}}`
   - append `.table-scroll{overflow-x:auto;max-width:100%}` right after `.wide{grid-column:1/-1}`

- [ ] **Step 5: Fix Attribution**

In `frontend/src/app/workspaces/analytics/tabs/attribution.ts` `styles`:

```css
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); }
```

replaces `:host { display: grid; gap: var(--space-14); }`, and

```css
    @media (max-width: 639px) { .panels { grid-template-columns: minmax(0, 1fr); } }
```

replaces `@media (max-width: 639px) { .panels { grid-template-columns: 1fr; } }`. The breakdown is an `sb-data-table`, which scrolls inside its own `.scroller` already.

- [ ] **Step 6: Verify the fix in tests and in the browser, then commit**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/partials.spec.ts --include src/app/workspaces/analytics/tabs/attribution.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/spacing.spec.ts`
Expected: PASS, 0 failed.

Rebuild and re-measure (the `admin_ui.py` from Step 1 serves `frontend/dist`, so a rebuild is enough):

```bash
cd frontend && npm run build
node "$REPRO/widest.mjs" http://localhost:1234 "/analytics?tab=partials" 390
node "$REPRO/widest.mjs" http://localhost:1234 "/analytics?tab=attribution" 390
cd ..
```

Expected: `page-scroll-x=0` on both, and no `roots` lines. Anything else: return to Step 2's second bullet with the new root.

```bash
git add frontend/src/app/workspaces/analytics/tabs/partials.ts frontend/src/app/workspaces/analytics/tabs/partials.spec.ts frontend/src/app/workspaces/analytics/tabs/attribution.ts frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts
git commit -m "fix(analytics): Partials and Attribution size to the tab, not their widest child (v179)

Repro at 390px before the fix (widest.mjs):
<paste the page-scroll-x and root lines from Step 2>
After: page-scroll-x=0 on both."
```

- [ ] **Step 7: Parts 1–2 browser check at 1440, 768 and 390**

```bash
OUT="$(mktemp -d)"
node frontend/scripts/browse.mjs shots --base http://localhost:1234 --widths 1440,768,390 --out "$OUT" \
  --path /dashboard --path /trades --path /watchlist --path /calendar --path /risk --path /versions \
  --path /research --path /reports --path /system --path "/system?tab=logs" --path /ui \
  --path /analytics --path "/analytics?tab=attribution" --path "/analytics?tab=execution" \
  --path "/analytics?tab=edge" --path "/analytics?tab=pipeline" --path "/analytics?tab=tuning" \
  --path "/analytics?tab=partials"
grep -H "page-scroll-x" "$OUT"/*.txt | grep -v "page-scroll-x: 0"
```

Expected: the `grep` prints nothing for every Analytics tab, `/system` and `/calendar` (Parts 1–2 own those overflows). Trades, Dashboard, Watchlist and Research may still scroll sideways inside their tables (Part 3 replaces those on phone) but must not report page overflow from the filter row. Then open the 390 and 768 PNGs and check, page by page:

| What | Where | Pass when |
|---|---|---|
| Text floor (V179-1) | any `.sb-label`, stat-tile label/`N=`, side-menu tagline | nothing visibly smaller than the table text's 11px floor, also with the zoom preference at 90% (set it in the profile menu, re-shoot `/analytics`) |
| Hit areas (V179-2) | chips, `Columns`, `Filters`, segments, "View all" | each control is at least 44px tall at 390 and 768 |
| Panel baseline (V179-3) | Analytics Equity header, any panel with `N=` and ⓘ | label, `N=`, total and ⓘ on one baseline; one header height |
| Stat tiles (V179-4) | Calendar totals, Analytics, Risk | one stacked, left-aligned layout; equal heights in a row; every caption, `N=` and ⓘ still shown |
| Filter row (V179-5) | Trades, Watchlist, Analytics | chips on one scrolling line; `Columns` and `Filters` same height and look with count badges; no blank band above Trades' table; Analytics selects in two equal columns at 390 |
| Tab reveal (V179-6) | `/analytics?tab=partials` @390, `/system` @390 | the Partials tab is visible and underlined on load; the settings rail shows an edge fade where categories are hidden |
| Charts (V179-7, V179-8) | Attribution, Partials @390 | heat grid scrolls inside its panel with a fade; bar lists are two-line items; waterfall labels inside the panel; no tile cut off |

Also check `/system?tab=logs` at 1440 and 390: the `sb-toolbar` in its panel header (V179-5's container note) still shows its controls.

Each failure is fixed in the file it traces to (the Part 1–2 task that owns it), with a test in that file's spec in the style of the owning task, run with that spec's narrow `ng test --include`, and committed as `fix(ui): <what> -- v179 Parts 1–2 browser check`. Re-shoot the affected paths until the table passes. Stop `admin_ui.py` when done.

---
