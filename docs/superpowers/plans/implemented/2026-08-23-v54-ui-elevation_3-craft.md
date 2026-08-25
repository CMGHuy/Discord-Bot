# UI Elevation (v54) — Part 3: Depth and numeric craft

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Index:** `2026-08-23-v54-ui-elevation_0-index.md` — read its Global Constraints first.
**Spec:** `docs/superpowers/specs/2026-08-23-v54-ui-elevation-design.md` (decisions D2, D4)

**Goal:** The elevation ladder carries real meaning and is enforced; every numeric in the app is aligned, fixed-precision, and signed in two channels.

**Runs after `_1` merges. Parallel with `_2`** — `_2` edits workspace templates, `_3` edits `tokens.css`, `ui/` numerics and the elevation rule.

## Two corrections to the spec, found by reading the code

**1. G3 is refined, not as written.** The spec says *"`box-shadow` appears in exactly one rule"*. The codebase has five uses and **four are `inset`**:

| Use | What it is |
|---|---|
| `shell.css:188` `inset 2px 0 0 var(--accent)` | active-nav indicator |
| `versions.ts:237` `inset 0 0 0 1px var(--bg)` | a ring between adjacent swatches |
| `earnings-calendar.ts:158` `inset 0 0 0 2px var(--accent)` | today marker |
| `versions.ts:256` `0 0 0 9999px var(--overlay-dim)` | a scrim faked with a huge spread |
| `column-picker.ts:115` `0 6px 24px rgb(0 0 0 / .5)` | **a genuine L3 overlay shadow** |

An `inset` shadow is a border drawn inside the box — a different thing from elevation, and forbidding it would force four correct rules to be rewritten worse. **G3 becomes: a non-`inset` `box-shadow` appears in exactly one rule (the L3 rule).** The `9999px` spread scrim is not a shadow either; Task 24 converts it to `--scrim`.

Update the spec's G3 wording as part of Task 24's commit.

**2. D4 is mostly already built.** `ui/format.ts` already exports `ABSENT = '—'`, `num`, `pct`, `share`, `money`, `rMultiple`, and `direction-arrow.ts` already encodes direction as a glyph. So D4 is an **adoption and gap-closing** job, not a greenfield one. Tasks 25–28 reflect that. Do not rewrite `format.ts`.

---

### Task 22: The two new tokens

**Files:**
- Modify: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/app/ui/tokens.spec.ts`

**Interfaces:**
- Produces: `--shadow-overlay`, `--scrim`. Tasks 23–24 and wave `_4` consume them.

- [ ] **Step 1: Add them to the required list in `tokens.spec.ts`**

In the `REQUIRED` array, after `'--border-strong'`:

```ts
  '--shadow-overlay',
  '--scrim',
```

And append a rule test:

```ts
  it('defines exactly one elevation shadow, for L3', () => {
    expect(CSS).toMatch(/^\s*--shadow-overlay:\s*0 8px 24px/m);
  });
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd frontend && npm test -- --include src/app/ui/tokens.spec.ts`
Expected: FAIL — both tokens undefined.

- [ ] **Step 3: Add the tokens**

In `tokens.css`, inside `:root`, after the `--border-strong` line:

```css
  /* -- elevation --------------------------------------------------------
   * ONE shadow, and it means one thing: this element is not part of the
   * page flow.
   *
   * Depth in a dark UI is carried by surface LIGHTNESS, not by shadow --
   * the four surface tokens above already step 0a0b10 -> 10121a -> 171a25
   * -> 1e2230, which is the ladder. A shadow under a panel on near-black
   * reads as smudge rather than depth, so L1 and L2 have none and only L3
   * (dropdown, popover, tooltip, toast, drawer, dialog) takes this.
   *
   * An `inset` box-shadow is NOT this: it is a border drawn inside the box
   * (the active-nav indicator, a focus ring, the today marker) and stays
   * allowed. The gate in primitives.spec.ts checks non-inset shadows only.
   */
  --shadow-overlay: 0 8px 24px rgba(0, 0, 0, .55), 0 2px 6px rgba(0, 0, 0, .4);

  /* Alias for the dim behind a MODAL L3 element. --overlay-dim is the raw
   * colour; this names what it is for, so a scrim stops being hand-rolled
   * (versions.ts faked one with a 9999px spread). */
  --scrim: var(--overlay-dim);
```

- [ ] **Step 4: Run, then commit**

Run: `cd frontend && npm test -- --include src/app/ui/tokens.spec.ts` → PASS.

```bash
git add frontend/src/styles/tokens.css frontend/src/app/ui/tokens.spec.ts
git commit -m "feat(v54): add --shadow-overlay and --scrim"
```

---

### Task 23: The L3 rule, and everything that floats adopts it

**Files:**
- Modify: `frontend/src/styles.css` (the single L3 rule)
- Modify: `frontend/src/app/ui/column-picker.ts`, `ui/layout.ts` (`sb-drawer`), `ui/confirm-dialog.ts`, `shell/toast-host.ts`, `ui/profile-menu.ts` if it renders a menu surface
- Test: `frontend/src/app/ui/elevation.spec.ts` (create)

**Interfaces:**
- Consumes: `--surface-overlay`, `--border-strong`, `--shadow-overlay`, `--scrim`.
- Produces: the `.elev-overlay` and `.elev-scrim` classes. Wave `_4` uses them for presentation-register panels.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/elevation.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const GLOBAL = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');

describe('the elevation ladder', () => {
  it('defines one overlay rule carrying the only elevation shadow', () => {
    expect(GLOBAL).toMatch(/\.elev-overlay\s*\{[^}]*box-shadow:\s*var\(--shadow-overlay\)/s);
  });

  it('gives the overlay the raised surface and the strong border', () => {
    const rule = GLOBAL.match(/\.elev-overlay\s*\{[^}]*\}/s)![0];
    expect(rule).toContain('var(--surface-overlay)');
    expect(rule).toContain('var(--border-strong)');
  });

  it('defines a scrim that uses the token rather than a raw rgba', () => {
    const rule = GLOBAL.match(/\.elev-scrim\s*\{[^}]*\}/s)![0];
    expect(rule).toContain('var(--scrim)');
    expect(rule).not.toMatch(/rgba?\(/);
  });
});
```

- [ ] **Step 2: Run and watch it fail.**

Run: `cd frontend && npm test -- --include src/app/ui/elevation.spec.ts`

- [ ] **Step 3: Add the rule to `styles.css`**

```css
/* L3 — the only level that casts a shadow.
 *
 * L0 --bg (the page, no border), L1 --surface (a panel, 1px border),
 * L2 --surface-raised (a thing on a panel, 1px border) and L3 (this) are the
 * whole ladder. Levels 0-2 are distinguished by surface lightness alone; a
 * shadow at those levels is mud on near-black, not depth.
 *
 * So a shadow here says exactly one thing: THIS ELEMENT IS NOT PART OF THE
 * PAGE FLOW. Dropdown, popover, tooltip, toast, drawer, dialog. Nothing else
 * may take it, and primitives.spec.ts enforces that. */
.elev-overlay {
  background: var(--surface-overlay);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  box-shadow: var(--shadow-overlay);
}

/* The dim behind a MODAL L3 element. Transient overlays (tooltip, dropdown,
 * toast) do not take this — dimming the page for a tooltip would be absurd,
 * and dimming it for a toast would make every notification modal. */
.elev-scrim {
  position: fixed;
  inset: 0;
  background: var(--scrim);
}
```

- [ ] **Step 4: Adopt it**

For each of `column-picker`, `sb-drawer` (in `layout.ts`), `confirm-dialog`, `toast-host` and any menu surface in `profile-menu`:

- Add `elev-overlay` to the floating element's class list.
- Delete that component's own `background`, `border` and `box-shadow` declarations for the floating surface. Keep `position`, `z-index`, `width`, `max-height`, `overflow`.
- For the modal ones (`sb-drawer` on the phone overlay, `confirm-dialog`), replace the hand-rolled scrim element's styles with `class="elev-scrim"`.

`column-picker.ts:115`'s `0 6px 24px rgb(0 0 0 / 0.5)` is the shadow being replaced — the values differ slightly from `--shadow-overlay` and that is the point: two floating surfaces with different shadows is exactly the inconsistency this fixes.

- [ ] **Step 5: Look at it**

Run: `cd frontend && npm start`, open `/ui`, and check every floating surface in the gallery: dropdown, drawer, dialog, toast. They must be visually identical in depth.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(v54): one L3 elevation rule; every floating surface adopts it"
```

---

### Task 24: Gate G3, and convert the faked scrim

**Files:**
- Modify: `frontend/src/app/workspaces/versions/versions.ts:256`
- Modify: `frontend/src/app/ui/primitives.spec.ts`
- Modify: `docs/superpowers/specs/2026-08-23-v54-ui-elevation-design.md` (G3 wording)

- [ ] **Step 1: Write the gate**

Append to `primitives.spec.ts`:

```ts
/**
 * G3 — a non-inset box-shadow appears in exactly one rule, the L3 rule.
 *
 * `inset` is deliberately exempt and is not a loophole: an inset shadow is a
 * border drawn inside the box, not elevation. The four in this codebase are
 * the active-nav indicator, two focus/selection rings and the today marker,
 * and rewriting them as borders would change layout for no gain.
 */
describe('G3: only L3 casts a shadow', () => {
  const shadows = (source: string) =>
    [...source.matchAll(/box-shadow:\s*([^;]+);/g)]
      .map(([, value]) => value.trim())
      .filter((value) => !value.startsWith('inset'));

  for (const { name, source } of callSites()) {
    it(`${name} casts no elevation shadow`, () => {
      expect(shadows(source)).toEqual([]);
    });
  }

  it('ui/ casts exactly one, and it is the token', () => {
    const global = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');
    expect(shadows(global)).toEqual(['var(--shadow-overlay)']);
  });
});
```

- [ ] **Step 2: Run and watch it fail** for `versions.ts` (the `9999px` spread) and any component whose shadow Task 23 missed.

- [ ] **Step 3: Convert versions' faked scrim**

Replace the `box-shadow: 0 0 0 9999px var(--overlay-dim);` trick with a real scrim element carrying `class="elev-scrim"`, sitting behind the highlighted element with a lower `z-index`. The spread trick works but is invisible to the gate and to anyone reading the file for "what dims the page here".

- [ ] **Step 4: Update the spec's G3 wording**

In `docs/superpowers/specs/2026-08-23-v54-ui-elevation-design.md`, replace the G3 row with:

```
| G3 | A non-`inset` `box-shadow` appears in exactly one rule (the L3 rule). `inset` shadows are borders drawn inside the box, not elevation, and stay allowed. |
```

- [ ] **Step 5: Run and commit**

```bash
git add frontend/src docs/superpowers/specs
git commit -m "test(v54): gate elevation shadows; convert versions' spread-scrim to --scrim"
```

---

### Task 25: `signed()` — sign in two channels

**Files:**
- Modify: `frontend/src/app/ui/format.ts`
- Test: `frontend/src/app/ui/format.spec.ts` (extend)

**Interfaces:**
- Consumes: `ABSENT`, `num` from `format.ts`.
- Produces: `export function signed(value: number | null | undefined, decimals?: number): string`. Task 28 uses it for every signed cell.

`format.ts` already handles precision and absence. The gap is the sign: a red number is not readable as negative in a screenshot, by a colour-blind reader, or in the Discord paste of a chart.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/app/ui/format.spec.ts`:

```ts
import { signed } from './format';

describe('signed', () => {
  it('prefixes a plus so gain is legible without colour', () => {
    expect(signed(1.5)).toBe('+1.50');
  });

  it('uses a real minus sign, not a hyphen', () => {
    // U+2212. A hyphen is narrower than a digit and breaks tabular alignment
    // down a column, which is the entire reason numerics are mono here.
    expect(signed(-1.5)).toBe('−2.00'.replace('2.00', '1.50'));
  });

  it('renders zero without a sign, because zero has none', () => {
    expect(signed(0)).toBe('0.00');
  });

  it('renders absence as the em dash, not as zero', () => {
    expect(signed(null)).toBe('—');
    expect(signed(undefined)).toBe('—');
  });

  it('honours a decimals override', () => {
    expect(signed(1.5, 1)).toBe('+1.5');
  });
});
```

- [ ] **Step 2: Run and watch it fail.**

Run: `cd frontend && npm test -- --include src/app/ui/format.spec.ts`

- [ ] **Step 3: Implement**

Append to `format.ts`:

```ts
/**
 * A signed figure, with the sign carried by a glyph as well as by colour.
 *
 * Colour is never the only channel: a screenshot pasted into Discord keeps
 * the hue but a colour-blind reader does not, and `--pos`/`--neg` are close
 * enough in lightness that a greyscale print loses them entirely.
 *
 * The minus is U+2212, not a hyphen. A hyphen is narrower than a digit even
 * in a mono face, so a column of hyphen-negatives does not align with a
 * column of positives — which defeats the tabular numerics the whole numeric
 * law rests on. Zero takes no sign, because it has none.
 */
export function signed(value: number | null | undefined, decimals = 2): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return ABSENT;
  if (value === 0) return num(0, decimals);
  return value > 0 ? `+${num(value, decimals)}` : `−${num(Math.abs(value), decimals)}`;
}
```

- [ ] **Step 4: Run and commit**

```bash
git add frontend/src/app/ui/format.ts frontend/src/app/ui/format.spec.ts
git commit -m "feat(v54): signed() carries sign as a glyph, not colour alone"
```

---

### Task 26: `sb-magnitude` — the shared inline bar

**Files:**
- Create: `frontend/src/app/ui/magnitude.ts`
- Test: `frontend/src/app/ui/magnitude.spec.ts`
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts`

**Interfaces:**
- Produces: `<sb-magnitude [value]="r" [max]="maxR" />`. Task 28 uses it in the R columns.

- [ ] **Step 1: Write the failing test**

```ts
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Magnitude } from './magnitude';

function render(value: number | null, max = 4) {
  const f = TestBed.createComponent(Magnitude);
  f.componentRef.setInput('value', value);
  f.componentRef.setInput('max', max);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('Magnitude', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('scales the bar against max', () => {
    expect(render(2, 4).querySelector('.bar')!.getAttribute('style')).toContain('50%');
  });

  it('grows leftward for a negative so the zero line reads as a centre', () => {
    expect(render(-2, 4).querySelector('.bar')!.classList.contains('neg')).toBe(true);
  });

  it('clamps beyond max rather than overflowing the cell', () => {
    expect(render(99, 4).querySelector('.bar')!.getAttribute('style')).toContain('100%');
  });

  it('renders nothing for an absent value', () => {
    expect(render(null).querySelector('.bar')).toBeNull();
  });

  it('is decorative, so it is hidden from assistive tech', () => {
    // The adjacent cell already carries the number; announcing the bar too
    // would read every figure twice.
    expect(render(2).getAttribute('aria-hidden')).toBe('true');
  });
});
```

- [ ] **Step 2: Run, watch it fail, implement**

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * A bar showing how big a figure is, beside the figure itself.
 *
 * Magnitude is what a column of digits is worst at: reading "+2.10" against
 * "+0.30" takes a comparison, and a bar takes a glance. Decorative by
 * construction — the number is always adjacent, so this is aria-hidden and
 * announcing it would read every figure twice.
 *
 * Colour follows the valence law: --pos for a gain, --neg for a loss. That is
 * the one place a bar may carry a hue, and it reinforces a sign the adjacent
 * `signed()` string has already spelled out.
 */
@Component({
  selector: 'sb-magnitude',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'aria-hidden': 'true' },
  template: `
    @if (width(); as pct) {
      <span class="bar" [class.neg]="isNegative()" [style.width.%]="pct"></span>
    }
  `,
  styles: `
    :host { display: block; height: 3px; background: var(--surface-raised); border-radius: 2px; }
    .bar { display: block; height: 100%; border-radius: 2px; background: var(--pos); }
    .bar.neg { background: var(--neg); margin-left: auto; }
  `,
})
export class Magnitude {
  readonly value = input.required<number | null>();
  readonly max = input(1);

  protected readonly isNegative = computed(() => (this.value() ?? 0) < 0);
  protected readonly width = computed(() => {
    const v = this.value();
    if (typeof v !== 'number' || !Number.isFinite(v)) return null;
    const max = Math.abs(this.max()) || 1;
    return Math.min(100, (Math.abs(v) / max) * 100);
  });
}
```

- [ ] **Step 3: Add it to the gallery, run, commit**

```bash
git add frontend/src/app
git commit -m "feat(v54): add sb-magnitude for scannable figure size"
```

---

### Task 27: The numeric-law gate

**Files:**
- Create: `frontend/src/app/ui/numeric.spec.ts`

- [ ] **Step 1: Write it**

```ts
import { describe, expect, it } from 'vitest';

/**
 * Numerics are mono and tabular via `.num`, right-aligned, and formatted
 * through `ui/format.ts`. This gate catches the two ways that slips:
 * interpolating a raw number into a template, and using toFixed at a call
 * site instead of the shared formatter.
 */
describe('the numeric law', () => {
  for (const { name, source } of callSites()) {
    it(`${name} formats numbers through ui/format.ts`, () => {
      const offenders = [...source.matchAll(/\{\{[^}]*\.toFixed\(/g)].map(([m]) => m.trim());
      expect(offenders).toEqual([]);
    });

    it(`${name} uses toLocaleString nowhere`, () => {
      // format.ts owns locale decisions; a second one drifts from the first.
      expect(source).not.toContain('toLocaleString');
    });
  }
});
```

- [ ] **Step 2: Run it**

Run: `cd frontend && npm test -- --include src/app/ui/numeric.spec.ts`

Every failure is a real finding: route that call site through `num`, `pct`, `rMultiple`, `signed` or `money`. If a call site needs a format `format.ts` does not have, **add it to `format.ts`** rather than exempting the file.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/ui/numeric.spec.ts frontend/src/app
git commit -m "test(v54): gate numeric formatting through format.ts"
```

---

### Task 28: Apply the numeric law across the tables

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.ts`
- Modify: every workspace rendering an R, %, price or count column

- [ ] **Step 1: Give `data-table` a numeric column kind**

Read `data-table.ts` (667 lines) and find its column descriptor. Add an `align: 'start' | 'end'` field defaulting to `'start'`, and have the cell renderer apply `text-align: end` plus the `.num` class when `align === 'end'`. Right-alignment belongs to the table, not to 40 call sites.

- [ ] **Step 2: Mark every numeric column `align: 'end'`**

Sweep the workspaces. Every R, percentage, price, count and duration column.

- [ ] **Step 3: Move signed columns onto `signed()` and add `sb-magnitude` to the R columns**

For every column showing a signed R or P&L figure: value via `signed(...)`, and an `<sb-magnitude>` beneath it with `max` bound to that column's observed maximum from the store.

- [ ] **Step 4: Name the unit once, in the header**

Where a cell repeats a unit (`1.20R`, `4.5%`), move the unit into the column header (`R`, `%`) and drop it from the cell. A unit repeated 200 times down a column is 200 pieces of ink carrying one fact.

- [ ] **Step 5: Check the gallery and every table by eye**

Run: `cd frontend && npm start`. Every numeric column must right-align, every decimal place must be constant down a column, and `—` must be visibly different from `0.00`.

- [ ] **Step 6: Run everything and commit**

Run: `cd frontend && npm test` → green.
Run: `python scripts/dev/testrun.py full` → unchanged.

```bash
git add frontend/src/app
git commit -m "feat(v54): apply the numeric law across every table"
```

---

### Task 29: Add the wave's parts to the gallery

**Files:** Modify `frontend/src/app/workspaces/gallery/gallery.ts`.

- [ ] Add an **Elevation** section: the four levels side by side as labelled boxes, so the ladder can be judged as a ramp rather than one surface at a time.
- [ ] Add a **Numerics** section: a small table showing positive, negative, zero and absent for each of `num`, `pct`, `rMultiple`, `signed`, `money`, with `sb-magnitude` beside the R column.
- [ ] Run `npm test` — `gallery.spec.ts` requires `<sb-magnitude` to appear, so this also closes G8 for the new primitive.
- [ ] Commit: `docs(v54): show elevation and numerics in the gallery`.

## Wave 3 done when

- [ ] `--shadow-overlay` and `--scrim` exist; no component hand-rolls either.
- [ ] Exactly one non-`inset` `box-shadow` in the codebase (G3, as refined above), and the spec's G3 row is updated to match.
- [ ] Every floating surface is visually identical in depth in `/ui`.
- [ ] No `.toFixed(` in a template, no `toLocaleString` anywhere.
- [ ] Every numeric column right-aligned, `.num`, fixed precision, unit in the header.
- [ ] `—` and `0.00` visibly different in every table.
- [ ] Python suite unchanged.
