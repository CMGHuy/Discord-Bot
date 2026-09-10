# v80 — Terminal foundation, part 2a: canonical components (F4–F7)

Part of `2026-09-10-v80-terminal-foundation_0-index.md`. Read its Global
Constraints and the v77 precondition before starting any task here.

# Phase 2 — Canonical components

## Parallelisation

- **Group A (parallel, after F3): F4–F7 here, F8–F12 in part 2b, F13–F20 in
  parts 3a and 3b.** Each task edits one component file plus that
  component's own spec file. This table covers F4–F12; parts 3a and 3b
  carry their own:

  | Task | Files |
  |---|---|
  | F4 | `button.ts`, `button.spec.ts` |
  | F5 | `form-controls.ts`, `form-controls.spec.ts` |
  | F6 | `chip.ts`, new `chip.spec.ts` |
  | F7 | `layout.ts`, new `layout.spec.ts` |
  | F8 | `data-table/data-table.ts`, `data-table/data-table.spec.ts`, plus two comments in `plan-cell.ts` (no other task touches it) |
  | F9 | `pagination.ts`, `pagination.spec.ts` |
  | F10 | `confidence-cell.ts`, `confidence-cell.spec.ts` |
  | F11 | `empty-state.ts`, new `empty-state.spec.ts` |
  | F12 | `section-head.ts`, `section-head.spec.ts` |

- **No contract dependency inside the group.** F8 renders `sb-empty-state`
  and `sb-pagination`, but only through inputs they already have. F11 and
  F9 change neither component's existing inputs.
- **Sequential edge:** every task consumes F2's colours and F3's
  `--control-h`, `--row-h`, `--text-control` and `.sb-label`.
- **Nothing here edits `controls.spec.ts` or the gallery.** Gallery entries
  land in F25.

---

### Task F4: `button[sb-button]` restyle

**Precondition:** `git merge-base --is-ancestor 24688ff4 main` exits 0. This
task edits v77's `button.ts` (with `danger-icon`); on a tree without v77 the
old strings below do not exist.

**Files:**
- Modify: `frontend/src/app/ui/button.ts`
- Test: `frontend/src/app/ui/button.spec.ts`

**Interfaces:**
- Consumes: `--accent-fill`, `--on-accent` (F2); `--control-h` inside the touch block (F3).
- Produces: no API change. `Button`, `ButtonVariant` and all nine variants
  are unchanged. `segment` and `chip` are documented as deprecated.

- [ ] **Step 1: Write the failing tests**

At the top of `frontend/src/app/ui/button.spec.ts`, add after the `vitest` import:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

Append to the end of the file:

```ts
const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/button.ts'), 'utf8');
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const rule = (selector: string) =>
  SOURCE.match(new RegExp(`${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

/* v80 D4. Asserted against the stylesheet text, as tokens.spec.ts does:
 * jsdom does not resolve var() inside a shorthand, so a computed-style
 * assertion here would be about jsdom rather than about the button. */
describe('v80 D4: the button restyle', () => {
  it('fills primary with the fill blue and its own ink', () => {
    expect(rule(':host(.primary)')).toContain('background: var(--accent-fill)');
    expect(rule(':host(.primary)')).toContain('color: var(--on-accent)');
  });

  it('draws secondary as a hairline, not a raised fill', () => {
    const r = rule(':host(.secondary)');
    expect(r).toContain('background: transparent');
    expect(r).toContain('border-color: var(--border-strong)');
  });

  it('outlines danger in the loss colour and fills it on hover', () => {
    expect(rule(':host(.danger)')).toContain('border-color: var(--neg)');
    expect(rule(':host(.danger:not([disabled]):hover)')).toContain('background: var(--neg)');
  });

  it('grows both icon variants to a square touch target', () => {
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 639px\) \{([\s\S]*?)\n    \}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain(':host(.icon), :host(.danger-icon)');
    expect(block![1]).toContain('min-width: var(--control-h)');
    expect(block![1]).toContain('min-height: var(--control-h)');
  });

  it('marks segment and chip deprecated in favour of sb-segmented', () => {
    expect(SOURCE).toMatch(/Deprecated \(v80 D4\)[\s\S]*sb-segmented/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/button.spec.ts')`

Expected: FAIL.
- The primary, secondary, danger and touch-target tests fail.
- The deprecation test fails: no such comment yet.
- The nine existing variant tests still pass.

- [ ] **Step 3: Implement**

In `frontend/src/app/ui/button.ts`, replace:

```ts
 * `danger-icon` is a v77 addition for destructive icon-only controls, and pairs
 * with `ConfirmDialog` exactly as `danger` does.
 */
```

with:

```ts
 * `danger-icon` is a v77 addition for destructive icon-only controls, and pairs
 * with `ConfirmDialog` exactly as `danger` does.
 *
 * v80 D4 restyles every variant through tokens. `segment` and `chip` are
 * deprecated in favour of `sb-segmented`; Migration moves their call sites.
 */
```

Replace:

```css
    /* Blue is interactive-only, which is exactly what a primary button is --
       the one place the accent is allowed to carry weight. */
    /* Dark ink on the bright accent, not white: --bg against --accent clears
       4.4:1, and the same pairing survives an accent change because both
       sides are tokens. */
    :host(.primary) { background: var(--accent); color: var(--bg); }
    :host(.primary:not([disabled]):hover) { background: color-mix(in srgb, var(--accent) 85%, white); }

    :host(.secondary) {
      background: var(--surface-raised);
      border-color: var(--border-strong);
      color: var(--text);
    }
    :host(.secondary:not([disabled]):hover) { border-color: var(--text-muted); }
```

with:

```css
    /* Blue is interactive-only, which is exactly what a primary button is --
       the one place the accent is allowed to carry weight. v80 D1 split the
       accent: --accent (#5593ff) is the text-safe blue and too light to carry
       white ink, so a filled button paints --accent-fill (#2962ff) with
       --on-accent on top, 4.90:1. */
    :host(.primary) { background: var(--accent-fill); color: var(--on-accent); }
    :host(.primary:not([disabled]):hover) { background: color-mix(in srgb, var(--accent-fill) 85%, white); }

    /* A hairline on whatever ground it sits on. Panels separate by hairlines
       now (v80 D3), and a raised fill made every secondary look pressed. */
    :host(.secondary) {
      background: transparent;
      border-color: var(--border-strong);
      color: var(--text);
    }
    :host(.secondary:not([disabled]):hover) { border-color: var(--text-muted); background: var(--surface-raised); }
```

Replace:

```css
    :host(.danger:not([disabled]):hover) { background: color-mix(in srgb, var(--neg) 14%, transparent); }
```

with:

```css
    /* Fills on hover (v80 D4): the moment before an irreversible click is the
       one place this control should shout. --bg ink on --neg clears 6:1. */
    :host(.danger:not([disabled]):hover) { background: var(--neg); color: var(--bg); }
```

Replace:

```css
    /* A filter toggle. Reads as a chip, behaves as a button: versions/ had
       four of these hand-rolled because no variant covered a control that is
       a chip in appearance and a toggle in function. \`.on\` is the pressed
       state and pairs with aria-pressed at the call site. */
```

with:

```css
    /* Deprecated (v80 D4): a toggle is sb-segmented now. Kept working until
       Migration moves the call sites.

       A filter toggle. Reads as a chip, behaves as a button: versions/ had
       four of these hand-rolled because no variant covered a control that is
       a chip in appearance and a toggle in function. \`.on\` is the pressed
       state and pairs with aria-pressed at the call site. */
```

Replace:

```css
    /* One cell of a segmented control. The group owns the outer border and
       the radius; a segment owns only its divider, so segments sit flush. */
```

with:

```css
    /* Deprecated (v80 D4) with chip above, for the same sb-segmented.

       One cell of a segmented control. The group owns the outer border and
       the radius; a segment owns only its divider, so segments sit flush. */
```

Replace:

```css
    :host(.segment.current) { background: var(--surface-overlay); color: var(--text); }
```

with:

```css
    :host(.segment.current) { background: var(--accent-soft); color: var(--text); }
```

Replace the end of the stylesheet:

```css
    :host(.link:not([disabled]):hover) { text-decoration: underline; }
  `,
```

with:

```css
    :host(.link:not([disabled]):hover) { text-decoration: underline; }

    /* v80 D4 -- a finger needs a square target. The same condition as the
       tokens.css touch block, where --control-h is already 44px. */
    @media (pointer: coarse), (max-width: 639px) {
      :host(.icon), :host(.danger-icon) { min-width: var(--control-h); min-height: var(--control-h); }
    }
  `,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/button.spec.ts' --include='**/controls.spec.ts')`

Expected: PASS. `controls.spec.ts` still finds `primary` on the class list and
the loading lock.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/button.ts frontend/src/app/ui/button.spec.ts
git commit -m "feat(v80): restyle buttons -- fill-blue primary, hairline secondary, touch-sized icons"
```

---

### Task F5: `sb-select`, `sb-text-input`, `sb-checkbox` restyle

**Files:**
- Modify: `frontend/src/app/ui/form-controls.ts`
- Test: `frontend/src/app/ui/form-controls.spec.ts`

**Interfaces:**
- Consumes: `.sb-label`, `--text-control`, `--control-h` (F3).
- Produces: no API change. Label spans carry the class `sb-label`; the
  checkbox's top label keeps `top-label` as well, which `controls.spec.ts` queries.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/form-controls.spec.ts`, replace the imports:

```ts
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { TextInput } from './form-controls';
```

with:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Checkbox, Select, TextInput } from './form-controls';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/form-controls.ts'), 'utf8');
```

Append to the end of the file:

```ts
describe('v80 D4: form controls', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('labels all three controls with the one shared label style', () => {
    const select = TestBed.createComponent(Select);
    select.componentRef.setInput('options', []);
    select.componentRef.setInput('label', 'Strategy');
    select.detectChanges();
    expect((select.nativeElement as HTMLElement).querySelector('.sb-label')!.textContent!.trim())
      .toBe('Strategy');

    const input = TestBed.createComponent(TextInput);
    input.componentRef.setInput('label', 'Ticker');
    input.detectChanges();
    expect((input.nativeElement as HTMLElement).querySelector('.sb-label')!.textContent!.trim())
      .toBe('Ticker');

    const box = TestBed.createComponent(Checkbox);
    box.componentRef.setInput('label', 'Has note');
    box.componentRef.setInput('topLabel', 'Filter');
    box.detectChanges();
    expect((box.nativeElement as HTMLElement).querySelector('.top-label')!.classList)
      .toContain('sb-label');
  });

  it('declares no label typography of its own', () => {
    expect(SOURCE).not.toMatch(/text-transform:\s*uppercase/);
    expect(SOURCE).not.toMatch(/letter-spacing:\s*0\.1em/);
  });

  it('sizes field text with --text-control, which is 16px on touch', () => {
    expect(SOURCE.match(/font-size: var\(--text-control\)/g)?.length ?? 0).toBeGreaterThanOrEqual(2);
  });

  it('never prints readable text in the divider-only grey', () => {
    expect(SOURCE).not.toContain('--text-faint');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/form-controls.spec.ts')`

Expected: FAIL. All four `v80 D4` tests fail: the label spans have class
`label`, there are three local uppercase rules, zero `--text-control`
declarations and three uses of `--text-faint`.

- [ ] **Step 3: Implement**

In `frontend/src/app/ui/form-controls.ts`, replace both occurrences (Select and TextInput) of:

```html
        <span class="label">{{ text }}</span>
```

with:

```html
        <span class="sb-label">{{ text }}</span>
```

Replace Select's styles:

```css
    .field { display: inline-flex; flex-direction: column; gap: var(--space-4); }
    .label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    select {
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
    }
    select:hover:not(:disabled) { border-color: var(--border-strong); }
    select:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    select:disabled { color: var(--text-faint); }
```

with:

```css
    .field { display: inline-flex; flex-direction: column; gap: var(--space-4); }
    /* v80 D4: a hairline field on the panel's own ground. The caption is the
       global .sb-label. --text-control is 16px on touch, the size below which
       a phone zooms into a focused field. */
    select {
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--surface);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
    }
    select:hover:not(:disabled) { border-color: var(--text-muted); }
    select:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    /* Opacity, not --text-faint: that grey is divider-only (contrast.spec.ts). */
    select:disabled { opacity: 0.45; }
```

Replace TextInput's styles:

```css
    .field { display: inline-flex; flex-direction: column; gap: var(--space-4); }
    .label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    input {
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
    }
    input::placeholder { color: var(--text-faint); }
    input:hover:not(:disabled) { border-color: var(--border-strong); }
    input:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
```

with:

```css
    .field { display: inline-flex; flex-direction: column; gap: var(--space-4); }
    /* Same field as sb-select above (v80 D4). */
    input {
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--surface);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
    }
    input::placeholder { color: var(--text-muted); }
    input:hover:not(:disabled) { border-color: var(--text-muted); }
    input:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    input:disabled { opacity: 0.45; }
```

In Checkbox's template, replace:

```html
        <span class="top-label">{{ text }}</span>
```

with:

```html
        <span class="top-label sb-label">{{ text }}</span>
```

In Checkbox's styles, replace:

```css
    .top-label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
```

with:

```css
    /* .top-label's typography is the global .sb-label (v80 D3). */
```

and replace:

```css
    .field:has(input:disabled) { color: var(--text-faint); cursor: default; }
```

with:

```css
    .field:has(input:disabled) { opacity: 0.45; cursor: default; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/form-controls.spec.ts' --include='**/controls.spec.ts')`

Expected: PASS. `controls.spec.ts` still finds `.top-label` and every `label` element.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/form-controls.ts frontend/src/app/ui/form-controls.spec.ts
git commit -m "feat(v80): hairline form controls with the shared label and 16px touch text"
```

---

### Task F6: `sb-chip` tones, mono caps and touch height

**Files:**
- Modify: `frontend/src/app/ui/chip.ts`
- Create: `frontend/src/app/ui/chip.spec.ts`

**Interfaces:**
- Consumes: `--pos-soft`, `--warn-soft`, `--info-soft`, `--info` (F2).
- Produces:
  - `ChipTone` widens to `'neutral' | 'good' | 'warn' | 'info' | 'q1' | 'q2' | 'q3' | 'q4' | 'q5'`
    (additive, so every existing call site still compiles);
  - `Chip.caps = input(true)`;
  - `QualityChip` passes `[caps]="false"`. F25 renders all nine tones.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/chip.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Chip, ChipTone, QualityChip } from './chip';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/chip.ts'), 'utf8');

function render(tone: ChipTone, caps?: boolean): HTMLElement {
  const f = TestBed.createComponent(Chip);
  f.componentRef.setInput('label', 'Swing');
  f.componentRef.setInput('tone', tone);
  if (caps !== undefined) f.componentRef.setInput('caps', caps);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.chip')!;
}

describe('Chip (v80 D4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  for (const tone of ['neutral', 'good', 'warn', 'info', 'q1', 'q2', 'q3', 'q4', 'q5'] as ChipTone[]) {
    it(`renders the ${tone} tone as a class`, () => {
      expect(render(tone).classList).toContain(tone);
    });
  }

  it('sets mono caps by default', () => {
    expect(render('neutral').classList).toContain('caps');
  });

  it('lets a caller keep mixed case', () => {
    expect(render('neutral', false).classList).not.toContain('caps');
  });

  it('keeps a quality chip mixed case, so Lv4 still reads Lv4', () => {
    const f = TestBed.createComponent(QualityChip);
    f.componentRef.setInput('value', 4);
    f.componentRef.setInput('label', 'Lv4');
    f.detectChanges();
    const chip = (f.nativeElement as HTMLElement).querySelector('.chip')!;
    expect(chip.classList).toContain('q4');
    expect(chip.classList).not.toContain('caps');
    expect(chip.textContent!.trim()).toBe('Lv4');
  });

  it('tints the three state tones rather than outlining them', () => {
    expect(SOURCE).toMatch(/\.good \{[^}]*background: var\(--pos-soft\)/);
    expect(SOURCE).toMatch(/\.warn \{[^}]*background: var\(--warn-soft\)/);
    expect(SOURCE).toMatch(/\.info \{[^}]*background: var\(--info-soft\)/);
  });

  it('grows to a 28px minimum on touch and narrow screens', () => {
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 639px\) \{([\s\S]*?)\n    \}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain('min-height: 28px');
  });

  it('no longer borrows --info for the level-4 band', () => {
    expect(SOURCE).not.toMatch(/\.q4 \{[^}]*--info/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/chip.spec.ts')`

Expected: FAIL.
- The build fails first: `'good'`, `'warn'` and `'info'` are not assignable to `ChipTone`, and `caps` is not an input.

- [ ] **Step 3: Implement**

In `frontend/src/app/ui/chip.ts`, replace:

```ts
export type ChipTone = 'neutral' | 'q1' | 'q2' | 'q3' | 'q4' | 'q5';
```

with:

```ts
export type ChipTone = 'neutral' | 'good' | 'warn' | 'info' | 'q1' | 'q2' | 'q3' | 'q4' | 'q5';
```

and, in the comment directly above it, replace:

```ts
 * renders invisible text.
 */
```

with:

```ts
 * renders invisible text.
 *
 * v80 D4 adds `good`, `warn` and `info`: states that are judgements but not
 * quality levels (a gate passed, a stale feed, a note). They tint rather than
 * outline, which is what tells them apart from a quality chip in one row.
 */
```

Replace everything from `/**\n * A small labelled tag` to the end of the file with:

```ts
/**
 * A small labelled tag — tier, horizon, confidence.
 *
 * Deliberately toneless by default: a horizon is not a judgement and does not
 * earn a colour. Use `qualityTone()` for the two that are judgements.
 *
 * Mono caps by default (v80 D4), so a tag reads as a tag and not as a word in
 * the sentence beside it. `caps` exists for the one chip that must keep its
 * case: a quality level is named `Lv4`, and `LV4` reads as something else.
 */
@Component({
  selector: 'sb-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="chip" [class]="tone()" [class.caps]="caps()">{{ label() }}</span>`,
  styles: `
    .chip {
      display: inline-flex;
      align-items: center;
      padding: 1px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-chip);
      font-family: var(--font-mono);
      font-size: var(--text-chip);
      font-weight: 500;
      white-space: nowrap;
    }
    /* The .sb-label spacing, for the same reason: capitals need air. */
    .caps { text-transform: uppercase; letter-spacing: 0.08em; }
    .neutral { color: var(--text-secondary); }
    .good { color: var(--pos); background: var(--pos-soft); border-color: transparent; }
    .warn { color: var(--warn); background: var(--warn-soft); border-color: transparent; }
    .info { color: var(--info); background: var(--info-soft); border-color: transparent; }
    .q1 { color: var(--quality-1); border-color: color-mix(in srgb, var(--neg) 35%, transparent); }
    .q2 { color: var(--quality-2); border-color: color-mix(in srgb, var(--warn) 35%, transparent); }
    .q3 { color: var(--quality-3); }
    /* Its own hue, not --info's: info is lavender since v80 D1, and level 4
       is the ramp's yellow-green. */
    .q4 { color: var(--quality-4); border-color: color-mix(in srgb, var(--quality-4) 35%, transparent); }
    .q5 { color: var(--quality-5); border-color: color-mix(in srgb, var(--pos) 35%, transparent); }

    /* v80 D4 -- a chip in a phone row is a tap target when it sits inside a
       button, and a line of text when it does not; 28px serves both. */
    @media (pointer: coarse), (max-width: 639px) {
      .chip { min-height: 28px; }
    }
  `,
})
export class Chip {
  readonly label = input.required<string>();
  readonly tone = input<ChipTone>('neutral');
  readonly caps = input(true);
}

/**
 * Convenience over `Chip` for the two fields that carry a quality judgement,
 * so no call site has to remember to pass the tone.
 */
@Component({
  selector: 'sb-quality-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip],
  template: `<sb-chip [label]="label()" [tone]="tone()" [caps]="false" />`,
})
export class QualityChip {
  /** A confidence level (1–5) or a tier (`A`/`B`/`C`). */
  readonly value = input.required<number | string | null>();
  /** Shown instead of the raw value — `Lv4`, `Tier B`. Defaults to the value. */
  readonly label = input.required<string>();

  protected readonly tone = computed(() => qualityTone(this.value()));
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/chip.spec.ts' --include='**/chip-row.spec.ts')`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/chip.ts frontend/src/app/ui/chip.spec.ts
git commit -m "feat(v80): chip state tones, mono caps with a quality-chip opt-out, 28px on touch"
```

---

### Task F7: `sb-panel`, `sb-tab-bar`, `sb-control-row`, `sb-drawer`

**Files:**
- Modify: `frontend/src/app/ui/layout.ts`
- Create: `frontend/src/app/ui/layout.spec.ts`

**Interfaces:**
- Consumes: `.sb-label`, `--control-h` (F3).
- Produces: no API change. Specifically:
  - `TabBar` gains protected `fadeStart`/`fadeEnd` signals and a protected
    `measure()` (template-only);
  - `ControlRow.stacked` becomes a no-op kept for compatibility;
  - `Panel`'s heading is an `h2.sb-label`.

**Why a viewport query on `sb-control-row`, against D3's "container
queries".** `container-type: inline-size` makes a box's inline size
independent of its content. `sb-control-row` sits inside flex lines, and in
the sticky settings save bar, where that collapses the row to zero width.
`breakpoints.ts`'s 640 floor via `@media` is the only safe rule here. The same
constraint applies to F17's `sb-panel-grid`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/layout.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Panel, Tab, TabBar } from './layout';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/layout.ts'), 'utf8');
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const rule = (selector: string) =>
  SOURCE.match(new RegExp(`${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

@Component({
  imports: [TabBar],
  template: `<sb-tab-bar [tabs]="tabs" [active]="'plans'" />`,
})
class TabHost {
  readonly tabs: Tab[] = [
    { id: 'plans', label: 'Plans' },
    { id: 'strategies', label: 'Strategies' },
    { id: 'tuning', label: 'Tuning' },
  ];
}

/** jsdom does no layout, so scroll geometry is stubbed onto the element. */
function geometry(el: HTMLElement, scrollWidth: number, clientWidth: number, scrollLeft: number) {
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth });
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(el, 'scrollLeft', { configurable: true, value: scrollLeft });
}

describe('sb-tab-bar overflow (v80 D4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function mount() {
    const f = TestBed.createComponent(TabHost);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    return { f, tabs: el.querySelector('.tabs') as HTMLElement, strip: el.querySelector('.strip')! };
  }

  it('scrolls sideways instead of clipping a tab', () => {
    expect(rule('.tabs')).toContain('overflow-x: auto');
    expect(rule('.tab')).toContain('flex: 0 0 auto');
    expect(rule('.tab')).toContain('white-space: nowrap');
  });

  it('fades the far edge while more tabs sit off-screen', () => {
    const { f, tabs, strip } = mount();
    geometry(tabs, 600, 300, 0);
    tabs.dispatchEvent(new Event('scroll'));
    f.detectChanges();
    expect(strip.classList).toContain('fade-end');
    expect(strip.classList).not.toContain('fade-start');
  });

  it('fades the near edge once scrolled to the end', () => {
    const { f, tabs, strip } = mount();
    geometry(tabs, 600, 300, 300);
    tabs.dispatchEvent(new Event('scroll'));
    f.detectChanges();
    expect(strip.classList).toContain('fade-start');
    expect(strip.classList).not.toContain('fade-end');
  });

  it('shows no fade when every tab fits', () => {
    const { f, tabs, strip } = mount();
    geometry(tabs, 300, 300, 0);
    tabs.dispatchEvent(new Event('scroll'));
    f.detectChanges();
    expect(strip.classList).not.toContain('fade-start');
    expect(strip.classList).not.toContain('fade-end');
  });

  it('sizes tabs from --control-h, so they are 44px on touch', () => {
    expect(rule('.tab')).toContain('min-height: var(--control-h)');
  });
});

describe('sb-panel (v80 D4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('sets its heading in the shared label style', () => {
    const f = TestBed.createComponent(Panel);
    f.componentRef.setInput('heading', 'Exposure');
    f.detectChanges();
    const h2 = (f.nativeElement as HTMLElement).querySelector('h2')!;
    expect(h2.classList).toContain('sb-label');
    expect(h2.textContent!.trim()).toBe('Exposure');
  });
});

describe('sb-control-row and sb-drawer on a phone (v80 D4)', () => {
  it('stacks every control row below 640px, not only stacked ones', () => {
    expect(SOURCE).toMatch(/@media \(max-width: 639px\) \{\s*\.row \{ flex-direction: column; align-items: stretch; \}/);
    expect(SOURCE).not.toMatch(/\.stacked \{/);
  });

  it('sizes the drawer by the dynamic viewport, so the browser bar never covers it', () => {
    expect(rule('.drawer')).toContain('height: 100dvh');
    expect(rule('.drawer')).toContain('max-height: 100dvh');
  });

  it('takes the full width on a phone', () => {
    expect(SOURCE).toMatch(/@media \(max-width: 639px\) \{\s*\.drawer \{ width: 100vw; \}/);
  });

  it('gives the close button a touch-sized target', () => {
    expect(rule('.close')).toContain('min-height: var(--control-h)');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/layout.spec.ts')`

Expected: FAIL.
- The overflow tests fail: there is no `.strip`, so `strip` is null.
- Every source-text assertion fails.
- The panel test fails: `h2` has no class.

- [ ] **Step 3: Implement**

In `frontend/src/app/ui/layout.ts`, replace the Angular import:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  input,
  output,
  viewChild,
} from '@angular/core';
```

with:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  afterNextRender,
  effect,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
```

In Panel's template, replace `          <h2>{{ text }}</h2>` with:

```html
          <h2 class="sb-label">{{ text }}</h2>
```

In Panel's styles, replace:

```css
    h2 {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
```

with:

```css
    /* Typography is the global .sb-label (v80 D3); only the UA margin is
       this component's business. */
    h2 { margin: 0; }
```

Replace the whole TabBar decorator and class (from `@Component({\n  selector: 'sb-tab-bar',` through the closing `}` of `export class TabBar`) with:

```ts
@Component({
  selector: 'sb-tab-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(window:resize)': 'measure()' },
  template: `
    <div class="strip" [class.fade-start]="fadeStart()" [class.fade-end]="fadeEnd()">
      <div #tabList class="tabs" role="tablist" (keydown)="onKeydown($event)" (scroll)="measure()">
        @for (tab of tabs(); track tab.id) {
          <button
            type="button"
            role="tab"
            class="tab"
            [class.active]="tab.id === active()"
            [attr.aria-selected]="tab.id === active()"
            [tabindex]="tab.id === active() ? 0 : -1"
            (click)="activeChange.emit(tab.id)"
          >
            {{ tab.label }}
          </button>
        }
      </div>
    </div>
  `,
  styles: `
    :host { display: block; }
    .strip { position: relative; border-bottom: 1px solid var(--border); }
    /* v80 D4. At 390px Analytics clipped "Tuning" and "Plans" with no way to
       reach them. The strip scrolls instead; tabs never shrink or wrap. */
    .tabs {
      display: flex;
      gap: var(--space-4);
      overflow-x: auto;
      scrollbar-width: none;
    }
    .tabs::-webkit-scrollbar { display: none; }
    .tab {
      flex: 0 0 auto;
      min-height: var(--control-h);
      padding: var(--space-8) var(--space-14);
      background: none;
      border: 0;
      border-bottom: 2px solid transparent;
      color: var(--text-secondary);
      font: inherit;
      font-size: var(--text-table);
      font-weight: 600;
      white-space: nowrap;
      cursor: pointer;
      transition: color var(--transition), border-color var(--transition);
    }
    .tab:hover { color: var(--text); }
    .tab:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .active { color: var(--text); border-bottom-color: var(--accent); }
    /* The edge fade is the "more this way" signal a hidden scrollbar no longer
       gives. Painted over the strip and never in the way of a tap. */
    .strip::before, .strip::after {
      content: '';
      position: absolute;
      top: 0;
      bottom: 0;
      width: var(--space-20);
      pointer-events: none;
      opacity: 0;
      transition: opacity var(--transition);
    }
    .strip::before { left: 0; background: linear-gradient(to right, var(--bg), transparent); }
    .strip::after { right: 0; background: linear-gradient(to left, var(--bg), transparent); }
    .fade-start::before, .fade-end::after { opacity: 1; }
  `,
})
export class TabBar {
  readonly tabs = input.required<Tab[]>();
  readonly active = input.required<string>();
  readonly activeChange = output<string>();

  private readonly tabList = viewChild.required<ElementRef<HTMLElement>>('tabList');
  protected readonly fadeStart = signal(false);
  protected readonly fadeEnd = signal(false);

  constructor() {
    afterNextRender(() => this.measure());
  }

  /** Which edges have tabs beyond them. Runs after first render, on scroll
   *  and on window resize: the only three moments the answer can change
   *  without the tab list itself changing. The 1px slack absorbs sub-pixel
   *  scroll positions, which would otherwise leave a fade stuck on. */
  protected measure(): void {
    const el = this.tabList().nativeElement;
    const overflow = el.scrollWidth - el.clientWidth;
    this.fadeStart.set(overflow > 1 && el.scrollLeft > 1);
    this.fadeEnd.set(overflow > 1 && el.scrollLeft < overflow - 1);
  }

  protected onKeydown(event: KeyboardEvent): void {
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (delta === 0) return;
    event.preventDefault();

    const tabs = this.tabs();
    const current = tabs.findIndex((tab) => tab.id === this.active());
    // Wraps, per the tab pattern: the end of the strip is not a dead end.
    const next = tabs[(current + delta + tabs.length) % tabs.length];
    if (next) this.activeChange.emit(next.id);
  }
}
```

In ControlRow's doc comment, replace:

```ts
 * `stacked` collapses the row to a full-width column below `sm` (640px).
 * `scan-tab`'s kill row hand-rolled exactly this; it belongs here instead.
 */
```

with:

```ts
 * Every row collapses to a full-width column below `sm` (640px); v80 D4
 * made that automatic. `stacked` still sets its class and does nothing
 * else. It is deprecated, and Migration removes it from `scan-tab`'s kill row.
 *
 * A viewport query, not a container query, on purpose: `container-type`
 * makes a box's inline size independent of its content, so a row inside a
 * flex line or the sticky settings save bar would shrink to nothing.
 */
```

In ControlRow's styles, replace:

```css
    @media (max-width: 639px) {
      .stacked { flex-direction: column; align-items: stretch; }
    }
```

with:

```css
    @media (max-width: 639px) {
      .row { flex-direction: column; align-items: stretch; }
    }
```

In Drawer's styles, replace:

```css
    .drawer {
      width: min(480px, 100vw);
      max-width: none;
      height: 100vh;
      max-height: 100vh;
```

with:

```css
    /* dvh, not vh (v80 D4): on a phone 100vh counts the collapsed address
       bar, which puts the drawer's last controls under the browser chrome. */
    .drawer {
      width: min(480px, 100vw);
      max-width: none;
      height: 100dvh;
      max-height: 100dvh;
```

Replace:

```css
    .close {
      padding: 0 var(--space-6);
```

with:

```css
    .close {
      min-width: var(--control-h);
      min-height: var(--control-h);
      padding: 0 var(--space-6);
```

Replace:

```css
    .body { padding: var(--space-14); overflow-y: auto; }
  `,
```

with:

```css
    .body { padding: var(--space-14); overflow-y: auto; }
    /* Full width on a phone: a 480px panel beside a 150px sliver of page
       behind it is a worse drawer than none. */
    @media (max-width: 639px) {
      .drawer { width: 100vw; }
    }
  `,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/layout.spec.ts' --include='**/controls.spec.ts' --include='**/breakpoints.spec.ts')`

Expected: PASS.
- `controls.spec.ts`: the tablist, arrow-key, drawer and `marks a stacked row` tests are unchanged.
- The `[role=tablist]` keydown still lands on `.tabs`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/layout.ts frontend/src/app/ui/layout.spec.ts
git commit -m "feat(v80): scrolling tab bar with edge fades, auto-stacking rows, dvh drawer"
```
