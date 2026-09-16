# v89 Admin UI Integrity and Spacing — Part 1: shared frontend foundation

> Header, global constraints, parallelisation and the task index live in `2026-09-16-v89-ui-integrity-and-spacing_0-index.md`. Every task here implicitly includes that file's Global Constraints.

# Phase 1 — Foundation (worktree)

### Task UA1: Spacing token, stack class, and the two guard specs

**Files:**
- Modify: `frontend/src/styles/tokens.css` (spacing block, ~line 213)
- Modify: `frontend/src/styles.css` (append after the `.register-instrument` block, ~line 217)
- Modify: `frontend/src/app/ui/confirm-dialog.ts` (styles, ~line 62)
- Modify: `frontend/src/app/workspaces/analytics/sections/exit-quality.ts:10` (`--space-16` → `--space-14`)
- Modify: `frontend/src/app/workspaces/versions/versions.ts:250,308` (`--space-2` → `--space-4`)
- Create: `frontend/src/app/ui/spacing.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - CSS token `--section-gap` (20px, or 14px below 640px).
  - Global class `.sb-stack` (single-column grid, `gap: var(--section-gap)`).
  - Global class `.sb-row` (auto-fit columns, same gap, `align-items: start`; column floor from `--row-min`, default 320px).
  - `frontend/src/app/ui/spacing.spec.ts` with the constant `PENDING_MARGIN_RULES: ReadonlySet<string>`. Tasks UA8–UA13 each delete their own entries from it, and **UA14 deletes the constant** once it is empty.

- [ ] **Step 0: Create the worktree**

Use the `EnterWorktree` tool (or `git worktree add .claude/worktrees/2026-09-16-v89-ui-integrity-and-spacing -b 2026-09-16-v89-ui-integrity-and-spacing main`) and continue inside it. First run `git worktree list` — if that path already exists, resume it instead of creating a new one.

- [ ] **Step 1: Write the failing guard spec**

Create `frontend/src/app/ui/spacing.spec.ts`:

```ts
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * v89 — two static guards for the spacing rule (spec §4.3).
 *
 * Read as TEXT for the reason tokens.spec.ts gives: jsdom neither resolves
 * `var()` nor lays anything out, so a computed-style assertion would pass on
 * a stylesheet that defines nothing. `process.cwd()` is the frontend root
 * under `ng test`.
 */
const SRC = join(process.cwd(), 'src');

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.(ts|css)$/.test(name) && !name.endsWith('.spec.ts') ? [path] : [];
  });
}

const FILES = walk(SRC).map((path) => ({ path: relative(SRC, path).replace(/\\/g, '/'), text: readFileSync(path, 'utf8') }));

// --- guard 1: every var(--x) is defined somewhere ------------------------

/** Custom properties that are legitimately set at runtime rather than in a
 *  stylesheet. Each entry says where. Add to this only with that reason. */
const RUNTIME_DEFINED = new Set<string>([
  '--heat', // calendar.ts binds [style.--heat] per cell
]);

function definedTokens(): Set<string> {
  const out = new Set<string>(RUNTIME_DEFINED);
  for (const { text } of FILES) {
    for (const m of text.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) out.add(m[1]);
    for (const m of text.matchAll(/\[style\.(--[a-zA-Z0-9-]+)\]/g)) out.add(m[1]);
    for (const m of text.matchAll(/setProperty\(\s*['"](--[a-zA-Z0-9-]+)['"]/g)) out.add(m[1]);
  }
  return out;
}

describe('design tokens are defined before they are used', () => {
  it('references no custom property that nothing defines', () => {
    const defined = definedTokens();
    const missing: string[] = [];
    for (const { path, text } of FILES) {
      for (const m of text.matchAll(/var\((--[a-zA-Z0-9-]+)/g)) {
        if (!defined.has(m[1])) missing.push(`${path}: ${m[1]}`);
      }
    }
    // A CSS declaration whose var() is undefined is dropped silently -- this
    // is how the Exit quality grid rendered with no gap (--space-16) and the
    // Versions chips with no padding (--space-2).
    expect([...new Set(missing)]).toEqual([]);
  });
});

// --- guard 2: panels own no outer margin --------------------------------

/** Selectors that name a panel-level block wherever they appear. */
const PANEL_ELEMENTS = /^(sb-panel|sb-section-head|sb-async|sb-data-table|sb-exit-quality|sb-strategy-contribution)$/;
/** Layout classes that wrap rows of panels. */
const LAYOUT_CLASSES = new Set(['panels', 'chart-grid', 'kpi-row', 'bottom-row', 'split', 'section', 'breakdowns', 'sb-stack', 'sb-row']);

/** `file|selector` entries that break the rule today. Each workspace task
 *  (UA8-UA13) deletes its own entries as it converts; UA14 deletes this
 *  constant once it is empty. It must never grow. */
export const PENDING_MARGIN_RULES: ReadonlySet<string> = new Set<string>([
  'app/workspaces/analytics/analytics.ts|sb-section-head',
  'app/workspaces/analytics/analytics.ts|sb-panel',
  'app/workspaces/analytics/analytics.ts|.section',
  'app/workspaces/analytics/analytics.ts|.kpi-row',
  'app/workspaces/analytics/analytics.ts|.breakdowns',
  'app/workspaces/analytics/analytics.ts|.breakdowns > * + *',
  'app/workspaces/dashboard/dashboard.ts|.bottom-row',
  'app/workspaces/dashboard/dashboard.ts|.positions-panel',
  'app/workspaces/trades/trade-detail.ts|.panels',
]);

function stylesOf(text: string): string {
  const at = text.indexOf('styles:');
  return (at < 0 ? '' : text.slice(at)).replace(/\/\*[\s\S]*?\*\//g, '');
}

function panelClassesOf(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of text.matchAll(/<sb-panel\b[^>]*?\bclass="([^"]+)"/g)) {
    m[1].split(/\s+/).forEach((c) => out.add(c));
  }
  return out;
}

function isPanelLevel(selector: string, panelClasses: Set<string>): boolean {
  const last = selector.trim().split(/\s+/).pop() ?? '';
  if (PANEL_ELEMENTS.test(last)) return true;
  const cls = /^\.([a-zA-Z0-9_-]+)/.exec(selector.trim());
  return cls !== null && (LAYOUT_CLASSES.has(cls[1]) || panelClasses.has(cls[1]));
}

describe('spacing between panels comes from the stack gap, not margins', () => {
  it('declares no outer margin on a panel-level selector', () => {
    const offenders: string[] = [];
    for (const { path, text } of FILES.filter((f) => f.path.startsWith('app/workspaces/'))) {
      const panelClasses = panelClassesOf(text);
      for (const m of stylesOf(text).matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
        const body = m[2];
        const margin = /margin(-top|-bottom|-block)?\s*:\s*([^;]+)/.exec(body);
        if (!margin || /^\s*(0|auto)\s*$/.test(margin[2])) continue;
        for (const selector of m[1].split(',').map((s) => s.trim()).filter(Boolean)) {
          if (!isPanelLevel(selector, panelClasses)) continue;
          const key = `${path}|${selector}`;
          if (!PENDING_MARGIN_RULES.has(key)) offenders.push(key);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix frontend test -- --include src/app/ui/spacing.spec.ts`
Expected: guard 1 FAILS, listing at least `app/workspaces/analytics/sections/exit-quality.ts: --space-16` and `app/workspaces/versions/versions.ts: --space-2`. Guard 2 either passes, or lists offenders that are not in `PENDING_MARGIN_RULES`.

For any other guard-1 entry, find where that property is set:
- **Set at runtime** (a binding or `setProperty`): add it to `RUNTIME_DEFINED` with a one-line comment saying where.
- **Genuinely undefined:** fix the reference to the nearest defined token.

For any guard-2 offender not listed, first confirm by reading the rule that it really is a panel-level margin, then add it to `PENDING_MARGIN_RULES`. Name the owning task in the commit message.

- [ ] **Step 3: Add the token, the two layout classes, and the dialog host rule**

In `frontend/src/styles/tokens.css`, directly after `--space-20: 20px;`:

```css

  /* v89 -- THE gap between sibling panels, vertical and horizontal, in both
   * registers (spec §4.2). --register-pad still governs density INSIDE a
   * panel; it no longer decides how far apart two panels sit, which is how
   * two pages with the same structure came to measure 10 and 20. */
  --section-gap: var(--space-20);
```

And after the `@media (pointer: coarse), (max-width: 639px)` block:

```css

/* v89 -- width only, not pointer: a touch laptop at 1440 keeps desktop
 * rhythm; only a narrow viewport tightens it. */
@media (max-width: 639px) {
  :root { --section-gap: var(--space-14); }
}
```

In `frontend/src/styles.css`, after the `.register-instrument { ... }` block:

```css

/* v89 -- the one way sibling panels are spaced (spec §4.2). A workspace
 * wraps panels in .sb-stack; a row of side-by-side panels is .sb-row inside
 * it. Neither the panels nor these wrappers carry outer margins. */
.sb-stack {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-content: start;
  gap: var(--section-gap);
}
.sb-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--row-min, 320px)), 1fr));
  align-items: start;
  gap: var(--section-gap);
}
```

In `frontend/src/app/ui/confirm-dialog.ts`, first line inside `styles: \``:

```css
    /* v89: a closed <dialog> is display:none, but this host element is not,
       so in a grid parent it became a zero-height item that added a second
       gap wherever it sat between two panels. */
    :host { display: contents; }
```

- [ ] **Step 4: Fix the two undefined references**

- `frontend/src/app/workspaces/analytics/sections/exit-quality.ts:10`: change `gap:var(--space-16)` to `gap:var(--space-14)`.
- `frontend/src/app/workspaces/versions/versions.ts:250`: change `padding: var(--space-2) var(--space-6);` to `padding: var(--space-4) var(--space-6);`.
- `frontend/src/app/workspaces/versions/versions.ts:308`: change `gap: var(--space-2);` to `gap: var(--space-4);`.

- [ ] **Step 5: Add `--section-gap` to the token spec's required list**

In `frontend/src/app/ui/tokens.spec.ts`, add `'--section-gap',` after `'--control-h',` in `REQUIRED`.

- [ ] **Step 6: Run both specs to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/ui/spacing.spec.ts`
Expected: PASS (2 tests).
Run: `npm --prefix frontend test -- --include src/app/ui/tokens.spec.ts`
Expected: PASS.
Run: `npm --prefix frontend test -- --include src/app/ui/confirm-dialog.spec.ts`
Expected: PASS. (If this spec file does not exist, skip.)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/styles.css frontend/src/app/ui/confirm-dialog.ts frontend/src/app/ui/spacing.spec.ts frontend/src/app/ui/tokens.spec.ts frontend/src/app/workspaces/analytics/sections/exit-quality.ts frontend/src/app/workspaces/versions/versions.ts
git commit -m "feat(v89): one section gap, a stack class, and guards for undefined tokens and panel margins"
```

---

### Task UA2: `sb-bar-list` — one labelled value per row, signed or rate

**Files:**
- Create: `frontend/src/app/ui/bar-list.ts`
- Create: `frontend/src/app/ui/bar-list.spec.ts`

**Interfaces:**
- Consumes: `CHART_CHROME` from `frontend/src/app/ui/chart/chart-frame.ts`; `ABSENT` from `frontend/src/app/ui/format.ts`.
- Produces:
  - `export interface BarRow { label: string; value: number | null; n?: number | null; withheld?: boolean }`
  - `export type BarListMode = 'signed' | 'rate'`
  - `@Component({ selector: 'sb-bar-list' }) export class BarList` with inputs:
    - `rows: readonly BarRow[]` (required)
    - `mode: BarListMode = 'signed'`
    - `format: (value: number) => string` (required)
    - `max: number | null = null` (signed scale ceiling; default is the largest |value|)
    - `reference: number | null = null` (rate mode only, 0–100)
    - `withheldFloor: number | null = null` (renders `n=3 · <20` on withheld rows)
  - Rendered DOM contract used by later specs: `li` per row (class `withheld` when withheld); `.label`, `.value`, `.n`; `.fill[data-tone="pos"|"neg"|"above"|"below"]` with inline `left`/`width` percentages; `.axis` in signed mode; `.ref` in rate mode when `reference` is set.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/ui/bar-list.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { BarList, BarListMode, BarRow } from './bar-list';

function render(rows: BarRow[], opts: { mode?: BarListMode; max?: number; reference?: number; floor?: number } = {}) {
  const fixture = TestBed.createComponent(BarList);
  fixture.componentRef.setInput('rows', rows);
  fixture.componentRef.setInput('format', (v: number) => `${v.toFixed(1)}%`);
  if (opts.mode) fixture.componentRef.setInput('mode', opts.mode);
  if (opts.max !== undefined) fixture.componentRef.setInput('max', opts.max);
  if (opts.reference !== undefined) fixture.componentRef.setInput('reference', opts.reference);
  if (opts.floor !== undefined) fixture.componentRef.setInput('withheldFloor', opts.floor);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const fills = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('.fill')];

describe('BarList', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  describe('signed mode', () => {
    it('draws a loss to the LEFT of the zero axis and colours it negative', () => {
      // The By month bug: -82.47 rendered as a full-width green bar.
      const el = render([{ label: '2026-07', value: -80 }, { label: '2026-09', value: 40 }]);
      const [loss, gain] = fills(el);
      expect(loss.dataset['tone']).toBe('neg');
      expect(loss.style.left).toBe('0%');
      expect(loss.style.width).toBe('50%');
      expect(gain.dataset['tone']).toBe('pos');
      expect(gain.style.left).toBe('50%');
      expect(gain.style.width).toBe('25%');
      expect(el.querySelector('.axis')).not.toBeNull();
    });

    it('honours an explicit max', () => {
      const [only] = fills(render([{ label: '9m', value: 0.5 }], { max: 1 }));
      expect(only.style.width).toBe('25%');
    });

    it('draws no bar for zero or null, and prints an em dash for null', () => {
      const el = render([{ label: 'a', value: 0 }, { label: 'b', value: null }]);
      expect(fills(el)).toHaveLength(0);
      expect(el.querySelectorAll('.value')[1].textContent!.trim()).toBe('—');
    });
  });

  describe('rate mode', () => {
    it('scales against 100 and places the reference line at its value', () => {
      const el = render([{ label: '0h-2h', value: 64.705882, n: 357 }], { mode: 'rate', reference: 50 });
      const [bar] = fills(el);
      expect(parseFloat(bar.style.width)).toBeCloseTo(64.71, 1);
      expect(el.querySelector<HTMLElement>('.ref')!.style.left).toBe('50%');
    });

    it('colours by the reference, not by a hard-coded gain colour', () => {
      const el = render([{ label: 'hi', value: 60 }, { label: 'lo', value: 40 }], { mode: 'rate', reference: 50 });
      expect(fills(el).map((f) => f.dataset['tone'])).toEqual(['above', 'below']);
    });

    it('formats the value instead of printing the raw float', () => {
      const el = render([{ label: '2h-4h', value: 45.045045, n: 117 }], { mode: 'rate', reference: 50 });
      expect(el.querySelector('.value')!.textContent!.trim()).toBe('45.0%');
      expect(el.querySelector('.n')!.textContent!.trim()).toBe('n=117');
    });

    it('draws no bar for a withheld row and says why in the n column', () => {
      const el = render([{ label: 'Saturday', value: null, n: 3, withheld: true }], { mode: 'rate', reference: 50, floor: 20 });
      expect(fills(el)).toHaveLength(0);
      expect(el.querySelector('li')!.classList).toContain('withheld');
      expect(el.querySelector('.n')!.textContent!.trim()).toBe('n=3 · <20');
      // The label stays the label -- it no longer carries "(n=3 — below 20, rate withheld)".
      expect(el.querySelector('.label')!.textContent!.trim()).toBe('Saturday');
    });

    it('clamps a rate above 100 to the track', () => {
      const [bar] = fills(render([{ label: 'x', value: 130 }], { mode: 'rate' }));
      expect(bar.style.width).toBe('100%');
    });
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix frontend test -- --include src/app/ui/bar-list.spec.ts`
Expected: FAIL — `Cannot find module './bar-list'`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/app/ui/bar-list.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { CHART_CHROME } from './chart/chart-frame';
import { ABSENT } from './format';

/** One labelled figure. `n` is its sample; `withheld` means a rate held back
 *  below the sample floor, drawn with no bar. */
export interface BarRow {
  label: string;
  value: number | null;
  n?: number | null;
  withheld?: boolean;
}

/** `signed`: a P&L-like figure, drawn either side of a centre zero axis.
 *  `rate`: a 0-100 share against a fixed scale and a reference line. */
export type BarListMode = 'signed' | 'rate';

type Tone = 'pos' | 'neg' | 'above' | 'below';

interface Drawn extends BarRow {
  text: string;
  left: number;
  width: number;
  tone: Tone;
}

/**
 * A labelled value per row, as a horizontal bar — v89 (spec §3.1).
 *
 * Deliberately NOT sb-histogram. That component draws COUNTS: width is
 * count/tallest, the count prints raw, and "negative" means "the label starts
 * with a minus". Feeding it monthly returns drew -82% as a full-width green
 * bar; feeding it win rates printed 64.705882 and coloured 33% green. This one
 * takes a signed or bounded VALUE, a formatter, and an N column.
 *
 * Rate mode colours above/below the reference with the accent and a muted
 * tone, not green/red: the green/red pair is reserved for P&L direction, and
 * a 45% win rate is not a loss.
 */
@Component({
  selector: 'sb-bar-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ul>
      @for (row of drawn(); track row.label) {
        <li [class.withheld]="row.withheld">
          <span class="label" [title]="row.label">{{ row.label }}</span>
          <span class="track" aria-hidden="true">
            @if (mode() === 'signed') { <span class="axis"></span> }
            @if (mode() === 'rate' && reference() !== null) {
              <span class="ref" [style.left.%]="clamp(reference()!)"></span>
            }
            @if (row.width > 0) {
              <span class="fill" [attr.data-tone]="row.tone" [style.left.%]="row.left" [style.width.%]="row.width"></span>
            }
          </span>
          <span class="value num">{{ row.text }}</span>
          <span class="n num">{{ nText(row) }}</span>
        </li>
      }
    </ul>
  `,
  styles: `
    :host { display: block; }
    ul { display: grid; gap: var(--space-4); margin: 0; padding: 0; list-style: none; }
    li {
      display: grid;
      grid-template-columns: 9rem minmax(0, 1fr) 5rem 4.5rem;
      align-items: center;
      gap: var(--space-8);
      font-size: var(--text-table);
    }
    @media (max-width: 639px) {
      li { grid-template-columns: 5.5rem minmax(0, 1fr) 4rem 3.5rem; }
    }
    .label {
      color: var(${CHART_CHROME.tickColour});
      font-size: var(${CHART_CHROME.tickSize});
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .track { position: relative; height: 10px; background: var(--bg); border-radius: 2px; }
    .axis { position: absolute; top: -2px; bottom: -2px; left: 50%; border-left: 1px solid var(--border-strong); }
    .ref { position: absolute; top: -3px; bottom: -3px; border-left: 1px dashed var(--text-faint); z-index: 1; }
    .fill { position: absolute; top: 0; bottom: 0; border-radius: 2px; }
    .fill[data-tone='pos'] { background: var(--pos); }
    .fill[data-tone='neg'] { background: var(--neg); }
    .fill[data-tone='above'] { background: var(--accent); }
    .fill[data-tone='below'] { background: var(--text-faint); }
    .value { text-align: right; color: var(--text); white-space: nowrap; }
    .n { text-align: right; color: var(--text-faint); font-size: var(--text-chip); white-space: nowrap; }
    li.withheld .label, li.withheld .value { color: var(--text-faint); }
  `,
})
export class BarList {
  readonly rows = input.required<readonly BarRow[]>();
  readonly mode = input<BarListMode>('signed');
  readonly format = input.required<(value: number) => string>();
  readonly max = input<number | null>(null);
  readonly reference = input<number | null>(null);
  readonly withheldFloor = input<number | null>(null);

  private readonly ceiling = computed(() => {
    const explicit = this.max();
    if (explicit !== null && explicit > 0) return explicit;
    const values = this.rows()
      .map((row) => row.value)
      .filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
      .map(Math.abs);
    return values.length ? Math.max(...values) || 1 : 1;
  });

  protected readonly drawn = computed<Drawn[]>(() =>
    this.rows().map((row) => {
      const v = row.value;
      const usable = !row.withheld && typeof v === 'number' && Number.isFinite(v);
      const text = usable ? this.format()(v) : ABSENT;
      if (!usable || v === 0) return { ...row, text, left: 0, width: 0, tone: 'pos' as Tone };

      if (this.mode() === 'rate') {
        const width = this.clamp(v);
        const ref = this.reference();
        return { ...row, text, left: 0, width, tone: (ref === null || v >= ref ? 'above' : 'below') as Tone };
      }

      const half = Math.min(50, (Math.abs(v) / this.ceiling()) * 50);
      return v > 0
        ? { ...row, text, left: 50, width: half, tone: 'pos' as Tone }
        : { ...row, text, left: 50 - half, width: half, tone: 'neg' as Tone };
    }),
  );

  protected clamp(value: number): number {
    return Math.min(100, Math.max(0, value));
  }

  protected nText(row: Drawn): string {
    if (row.n === null || row.n === undefined) return '';
    const floor = this.withheldFloor();
    return row.withheld && floor !== null ? `n=${row.n} · <${floor}` : `n=${row.n}`;
  }
}
```

- [ ] **Step 4: Run the spec to verify it passes**

Run: `npm --prefix frontend test -- --include src/app/ui/bar-list.spec.ts`
Expected: PASS (9 tests).

Also run: `npm --prefix frontend test -- --include src/app/ui/spacing.spec.ts`
Expected: PASS. The new file must reference only defined tokens.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/bar-list.ts frontend/src/app/ui/bar-list.spec.ts
git commit -m "feat(v89): sb-bar-list for signed values and rates, separate from the count histogram"
```

---

### Task UA3: Inline bold formatter, gauge and donut fixes, one count per table

**Files:**
- Create: `frontend/src/app/ui/inline-md.ts`
- Create: `frontend/src/app/ui/inline-md.spec.ts`
- Modify: `frontend/src/app/ui/gauge.ts:29` (svg `height`)
- Modify: `frontend/src/app/ui/gauge.spec.ts` (one added test)
- Modify: `frontend/src/app/ui/donut.ts:12` (styles: `text` fill)
- Modify: `frontend/src/app/ui/pagination.ts` (new `navOnly` input)
- Modify: `frontend/src/app/ui/pagination.spec.ts` (new tests)
- Modify: `frontend/src/app/ui/data-table/data-table.ts:180-188` (bottom pager is nav-only)
- Modify: `frontend/src/app/ui/data-table/data-table.spec.ts` (new test)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `export interface InlineSegment { text: string; bold: boolean }`
  - `export function inlineSegments(source: string | null | undefined): InlineSegment[]`
  - `@Component({ selector: 'sb-inline-md' }) export class InlineMd` with input `text: string | null`, rendering `<b>` per bold segment and plain text otherwise. It never binds HTML.
  - `PaginationComponent` input `navOnly: boolean = false`. When true it renders no per-page selector and no range label, and renders nothing at all when there is only one page.

- [ ] **Step 1: Write the failing inline-md spec**

Create `frontend/src/app/ui/inline-md.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { InlineMd, inlineSegments } from './inline-md';

describe('inlineSegments', () => {
  it('splits **bold** runs from plain text', () => {
    expect(inlineSegments('Stop at **425.76** (-3.3%)')).toEqual([
      { text: 'Stop at ', bold: false },
      { text: '425.76', bold: true },
      { text: ' (-3.3%)', bold: false },
    ]);
  });

  it('leaves a single asterisk and an unclosed pair as literal text', () => {
    expect(inlineSegments('2 * 3 and **open')).toEqual([{ text: '2 * 3 and **open', bold: false }]);
  });

  it('returns no segments for null, undefined or empty input', () => {
    expect(inlineSegments(null)).toEqual([]);
    expect(inlineSegments(undefined)).toEqual([]);
    expect(inlineSegments('')).toEqual([]);
  });
});

describe('InlineMd', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(text: string) {
    const fixture = TestBed.createComponent(InlineMd);
    fixture.componentRef.setInput('text', text);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders bold segments as <b> and never shows the asterisks', () => {
    const el = render('**Worst:** ORCL -3.78R');
    expect(el.querySelector('b')!.textContent).toBe('Worst:');
    expect(el.textContent).not.toContain('**');
  });

  it('escapes markup instead of interpreting it', () => {
    const el = render('<img src=x onerror=alert(1)> **ok**');
    expect(el.querySelector('img')).toBeNull();
    expect(el.textContent).toContain('<img src=x onerror=alert(1)>');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix frontend test -- --include src/app/ui/inline-md.spec.ts`
Expected: FAIL — `Cannot find module './inline-md'`.

- [ ] **Step 3: Implement the formatter**

Create `frontend/src/app/ui/inline-md.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export interface InlineSegment {
  text: string;
  bold: boolean;
}

/**
 * `**bold**` and nothing else — v89 (spec §3.7).
 *
 * The explanation and journal digest strings are written for Discord, whose
 * markdown the admin UI printed verbatim ("**AXON**"). Only bold is honoured:
 * it is the one construct those producers emit, and a fuller parser is a
 * second renderer to keep safe. Output is segments, not HTML, so the template
 * interpolates text and nothing from the server is ever bound as markup.
 */
export function inlineSegments(source: string | null | undefined): InlineSegment[] {
  if (!source) return [];
  const out: InlineSegment[] = [];
  const pattern = /\*\*([^*]+?)\*\*/g;
  let cursor = 0;
  for (const match of source.matchAll(pattern)) {
    const at = match.index ?? 0;
    if (at > cursor) out.push({ text: source.slice(cursor, at), bold: false });
    out.push({ text: match[1], bold: true });
    cursor = at + match[0].length;
  }
  if (cursor < source.length) out.push({ text: source.slice(cursor), bold: false });
  return out;
}

@Component({
  selector: 'sb-inline-md',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `@for (segment of segments(); track $index) {@if (segment.bold) {<b>{{ segment.text }}</b>} @else {{{ segment.text }}}}`,
  styles: `:host { display: inline; } b { font-weight: 600; color: var(--text); }`,
})
export class InlineMd {
  readonly text = input<string | null>(null);
  protected readonly segments = computed(() => inlineSegments(this.text()));
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npm --prefix frontend test -- --include src/app/ui/inline-md.spec.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Write the failing gauge, donut and pagination tests**

Append to `frontend/src/app/ui/gauge.spec.ts`, inside its top-level `describe` (the file's `render(inputs)` helper sets label and value):

```ts
  it('sets no invalid height attribute on the svg (v89: console error on every page)', () => {
    const svg = render({}).querySelector('svg')!;
    expect(svg.getAttribute('height')).not.toBe('auto');
  });
```

Append to `frontend/src/app/ui/pagination.spec.ts`:

```ts
describe('PaginationComponent navOnly (v89: one count per table)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(spec: { page: number; perPage: number; total: number }) {
    const f = TestBed.createComponent(PaginationComponent);
    f.componentRef.setInput('pagination', spec);
    f.componentRef.setInput('showPerPage', true);
    f.componentRef.setInput('navOnly', true);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('renders nothing when everything fits on one page', () => {
    expect(render({ page: 1, perPage: 25, total: 4 }).querySelector('.pager')).toBeNull();
  });

  it('renders the buttons but neither the range label nor the rows selector', () => {
    const el = render({ page: 2, perPage: 25, total: 90 });
    expect(el.querySelectorAll('.pager button')).toHaveLength(4);
    expect(el.querySelector('.range')).toBeNull();
    expect(el.querySelector('.per-page')).toBeNull();
  });
});
```

The file already imports `provideZonelessChangeDetection`, `TestBed` and the vitest globals used here.

Append to `frontend/src/app/ui/data-table/data-table.spec.ts`, directly after the test `'derives the pager from \`total\`, not from the rows it was handed'` (~line 250), in the same `describe` (it uses that block's `host`, `fixture` and `el()`):

```ts
  it('prints the range once, at the top, and only buttons below (v89)', () => {
    host.pagination.set({ total: 90, page: 2, perPage: 25 });
    fixture.detectChanges();

    expect(el().querySelectorAll('.pager .range')).toHaveLength(1);
    expect(el().querySelectorAll('.pager')).toHaveLength(2);
  });

  it('prints a one-page table\'s count once and no second pager (v89)', () => {
    host.pagination.set({ total: 4, page: 1, perPage: 25 });
    fixture.detectChanges();

    expect(el().querySelectorAll('.pager')).toHaveLength(1);
    expect(el().querySelector('.pager .range')!.textContent).toContain('4 rows');
  });
```

Add one CSS assertion to the donut. `frontend/src/app/ui/donut.ts` has no spec file, so create `frontend/src/app/ui/donut.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('donut centre total', () => {
  it('gives the svg text a fill from the text palette (v89: it rendered black on dark)', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/ui/donut.ts'), 'utf8');
    expect(source).toMatch(/text\{[^}]*fill:var\(--text-secondary\)/);
  });
});
```

- [ ] **Step 6: Run them to verify they fail**

Run each:
- `npm --prefix frontend test -- --include src/app/ui/gauge.spec.ts` → FAIL (`height` is `auto`)
- `npm --prefix frontend test -- --include src/app/ui/pagination.spec.ts` → FAIL (`navOnly` is not an input)
- `npm --prefix frontend test -- --include src/app/ui/data-table/data-table.spec.ts` → FAIL (two `.range`)
- `npm --prefix frontend test -- --include src/app/ui/donut.spec.ts` → FAIL

- [ ] **Step 7: Implement the four fixes**

`frontend/src/app/ui/gauge.ts:29` — replace

```html
      <svg viewBox="0 0 120 66" width="100%" height="auto" aria-hidden="true">
```
with
```html
      <!-- No height attribute: "auto" is not an SVG length (console error on
           every load, v89). The viewBox ratio sizes it from the width. -->
      <svg viewBox="0 0 120 66" width="100%" aria-hidden="true">
```

`frontend/src/app/ui/donut.ts:12` — in the `styles` string, directly after `svg{width:160px;height:160px}`, insert:

```
text{fill:var(--text-secondary);font-size:var(--text-table);font-variant-numeric:tabular-nums}
```

`frontend/src/app/ui/pagination.ts`:
- Wrap the whole template in `@if (!navOnly() || pageCount() > 1) { ... }`.
- Change the per-page block's condition from `@if (showPerPage())` to `@if (showPerPage() && !navOnly())`.
- Change `<span class="range num">{{ rangeLabel() }}</span>` to `@if (!navOnly()) {<span class="range num">{{ rangeLabel() }}</span>}`.
- Add the input below `readonly announce = input(false);`:

```ts
  /** v89: the SECOND pager under a long table. Buttons only -- the range
   *  and the rows selector already sit above the table, and printing them
   *  twice made "4 rows" appear top and bottom on a four-row table. */
  readonly navOnly = input(false);
```

`frontend/src/app/ui/data-table/data-table.ts`: in the pager `ng-template` (~line 186), bind `[navOnly]="!announce"`, so the top instance (`announce: true`) is full and the bottom instance (`announce: false`) is buttons only:

```html
    <ng-template #pagerTemplate let-page let-announce="announce">
      <sb-pagination [pagination]="page" [showPerPage]="showPerPage()" [announce]="announce" [navOnly]="!announce"
        (pageChange)="pageChange.emit($event)" (perPageChange)="perPageChange.emit($event)" />
    </ng-template>
```

- [ ] **Step 8: Run all four specs to verify they pass**

Run the four commands from Step 6. Expected: PASS for each.
Then run: `npm --prefix frontend test -- --include src/app/ui/spacing.spec.ts` → PASS.

If an existing data-table or pagination test asserted a second `.range` or a bottom rows selector, update that assertion to the one-count behaviour and say so in the commit message.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/ui/inline-md.ts frontend/src/app/ui/inline-md.spec.ts frontend/src/app/ui/gauge.ts frontend/src/app/ui/gauge.spec.ts frontend/src/app/ui/donut.ts frontend/src/app/ui/donut.spec.ts frontend/src/app/ui/pagination.ts frontend/src/app/ui/pagination.spec.ts frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts
git commit -m "feat(v89): bold-only inline formatter; gauge height and donut text fixes; one count per table"
```
