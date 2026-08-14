# Control alignment and settings grouping — Implementation Plan (v24)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-08-14-v22-control-alignment-design.md`
**Version:** ui 1.2.3 · bot 1.1.2
**Bump:** ui patch, applied last, after Task 14 is green.

**Goal:** Give every interactive control one shared height and one sanctioned
row layout, and rebuild the Settings form so each section groups its fields by
control type with cell bands that align across the grid.

**Architecture:** A single token (`--control-h`) sizes all four control
components. One new layout primitive (`sb-control-row`) owns the flex rule that
47 hand-rolled rows currently each decide for themselves. The Settings form
keeps its responsive `auto-fill` grid but each field spans four subgrid rows, so
the parent sizes label / control / help / meta bands to the tallest cell in the
row. Nothing about the palette, type scale or token system changes.

**Tech Stack:** Angular 21 (signals, `OnPush`, `input()`/`model()`), plain CSS
in component `styles`, design tokens in `src/styles/tokens.css`, vitest via
`npm test` (run from `frontend/`).

## Global Constraints

- **No hex outside `src/styles/tokens.css`.** Every colour is a `var(--token)`.
- **No `if (key === …)` in `settings-tab.ts`.** The form renders from
  `config.py`'s schema; a new setting must appear with zero frontend change
  (spec v14 Decision 8). Grouping keys off `controlOf(field)`, never a key name.
- **`box-sizing: border-box` is already global** (`src/styles.css:9`), so
  `height: var(--control-h)` includes borders. Do not re-declare it per
  component.
- **Tests assert behaviour and structure, never paint.** jsdom does no layout,
  so a computed-height assertion would pass on a stylesheet that defines
  nothing. Height is guarded at the source-text level instead (Task 2).
- **Commands run from `frontend/`:** `npm test` (vitest). Full Python suite
  (`python scripts/testrun.py full`) is untouched by this plan but is the
  pre-commit gate per `CLAUDE.md`.
- **Never edit files under `.claude/worktrees/`** from a main-tree session.

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/styles/tokens.css` | defines `--control-h` | 1 |
| `src/app/ui/tokens.spec.ts` | token + consumption guard | 1, 2, 13 |
| `src/app/ui/form-controls.ts` | select, text input, checkbox | 2, 3 |
| `src/app/ui/button.ts` | button variants | 2 |
| `src/app/ui/layout.ts` | panel, tab bar, drawer, **control row** | 4 |
| `src/app/ui/controls.spec.ts` | control + layout component tests | 3, 4, 5 |
| `src/app/ui/filter-bar.ts` | filter bar, chips | 5 |
| `src/app/ui/confirm-dialog.ts` | confirm dialog | 5 |
| `src/app/workspaces/system/settings-grouping.ts` | **new** — pure partition | 6 |
| `src/app/workspaces/system/settings-grouping.spec.ts` | **new** — its tests | 6 |
| `src/app/workspaces/system/settings-tab.ts` | the settings form | 6, 7, 8 |
| the nine workspace files | control-row conversion | 9–12 |

## Parallelisation

- **Sequential: Tasks 1 → 2 → 3 → 4 → 5.** Each consumes the previous task's
  token, input or component, and three of the five edit `ui/` files the others
  also touch.
- **Tasks 6–8 and Tasks 9–12 are parallel with each other.** 6–8 are confined to
  `settings-tab.ts` and its new sibling module; 9–12 touch the other eight
  workspace files.
- **Within 9–12: fully parallel, four workers.** No shared file, and none
  introduces a symbol another consumes. This is the widest group in the plan.
- **Sequential: Task 13 after every one of 9–12.** Its guard asserts no
  workspace hand-rolls a control row; run earlier it fails for the right reason
  at the wrong time.
- **Sequential: Task 14 last.** It inspects rows that must already be converted.
- **This whole plan is parallel with plan v25** (the trade chart). The two share
  no file: v25's frontend work is confined to `ui/chart/` and the chart sections
  of `trade-detail.ts` / `ticker-detail.ts`, neither of which Tasks 9–12 touch.

Two workers on one file do **not** merge — this working tree is shared and the
second silently overwrites the first. Respect the groups.

---

# Phase 1 — The contract

### Task 1: The `--control-h` token

**Files:**
- Modify: `frontend/src/styles/tokens.css` (after the spacing scale, ~line 114)
- Test: `frontend/src/app/ui/tokens.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: CSS custom property `--control-h`, value `28px`. Every later task
  in Phase 1 reads it.

- [ ] **Step 1: Write the failing test**

In `tokens.spec.ts`, add `'--control-h'` to the `REQUIRED` array (it sits with
the other layout tokens, after `'--radius-chip'`), and add this test inside the
`describe('design tokens', …)` block:

```ts
  it('sizes controls with a single height token', () => {
    expect(CSS).toMatch(/^\s*--control-h:\s*28px;/m);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/ui/tokens.spec.ts`
Expected: FAIL — two failures, `defines --control-h` and `sizes controls with a
single height token`.

- [ ] **Step 3: Add the token**

In `tokens.css`, immediately after `--space-20: 20px;` and before the
breakpoints comment:

```css
  /* -- controls --------------------------------------------------------
   * ONE height for every interactive control, so a button beside a field
   * is flush. The two were 29px (button, padding 6px 14px) and 25px
   * (input, 4px 8px) -- a 4px difference that no row could reconcile
   * because neither side owned it.
   *
   * 28 splits the difference: the input gains 3px, the button loses 1,
   * nothing visibly moves, and it lands on the 4px grid the spacing scale
   * implies. 26 (the input's height) is below a comfortable click target;
   * 30 (the button's) costs a row of visible data in every table toolbar
   * on a dashboard built for 11px type.
   *
   * `.icon` buttons are exempt -- square by construction, sized by glyph.
   */
  --control-h: 28px;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/app/ui/tokens.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/app/ui/tokens.spec.ts
git commit -m "feat(ui): --control-h, one height for every control"
```

---

### Task 2: The four controls consume it

**Files:**
- Modify: `frontend/src/app/ui/form-controls.ts:53-61` (select), `:107-115` (input)
- Modify: `frontend/src/app/ui/button.ts:29-43` (`:host`), `:75-81` (`.icon`)
- Test: `frontend/src/app/ui/tokens.spec.ts`

**Interfaces:**
- Consumes: `--control-h` from Task 1.
- Produces: nothing new in TypeScript. Later tasks rely on the *rendered*
  height being uniform.

- [ ] **Step 1: Write the failing test**

Append to `tokens.spec.ts`. It reads the component sources as text, the same way
the file already reads `tokens.css` — jsdom does no layout, so this is the only
honest place to assert it:

```ts
const UI = join(process.cwd(), 'src/app/ui');

describe('control height', () => {
  for (const file of ['form-controls.ts', 'button.ts']) {
    it(`${file} sizes its controls from --control-h`, () => {
      const source = readFileSync(join(UI, file), 'utf8');
      expect(source).toContain('var(--control-h)');
    });
  }

  it('no control hardcodes a vertical padding any more', () => {
    const source = readFileSync(join(UI, 'form-controls.ts'), 'utf8');
    expect(source).not.toMatch(/padding:\s*var\(--space-4\)\s+var\(--space-8\)/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/ui/tokens.spec.ts`
Expected: FAIL — `form-controls.ts sizes its controls from --control-h`.

- [ ] **Step 3: Size the controls**

In `form-controls.ts`, in **both** the `sb-select` and `sb-text-input` style
blocks, replace the padding line of the `select` / `input` rule:

```css
      padding: var(--space-4) var(--space-8);
```

with:

```css
      height: var(--control-h);
      padding: 0 var(--space-8);
```

In `button.ts`, in the `:host` rule, replace:

```css
      padding: var(--space-6) var(--space-14);
```

with:

```css
      min-height: var(--control-h);
      padding: 0 var(--space-14);
```

`min-height` rather than `height`, because a button's content is projected and
may wrap; the row still aligns because 28px is the floor every sibling also
sits at.

In the `:host(.icon)` rule, add `min-height: 0;` above its existing
`padding: var(--space-4);` so icon buttons stay glyph-sized.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/app/ui/`
Expected: PASS, including the pre-existing `controls.spec.ts` — nothing there
asserts padding.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/form-controls.ts frontend/src/app/ui/button.ts frontend/src/app/ui/tokens.spec.ts
git commit -m "fix(ui): controls share one height, so a button beside a field is flush"
```

---

### Task 3: `sb-checkbox` gains an optional top label

**Files:**
- Modify: `frontend/src/app/ui/form-controls.ts:150-181` (the `Checkbox` component)
- Test: `frontend/src/app/ui/controls.spec.ts`

**Interfaces:**
- Consumes: `--control-h` from Task 1.
- Produces: `Checkbox.topLabel: InputSignal<string | null>`, default `null`.
  Task 8 sets it on the Settings find-row.

- [ ] **Step 1: Write the failing test**

In `controls.spec.ts`, add to the existing host component's template:

```html
    <sb-checkbox label="Only changed" topLabel="Filter" [(checked)]="flagged" />
```

and add `flagged = signal(false);` to the host class. Then add:

```ts
  it('renders a top label above the box when one is given', () => {
    const top = fixture.nativeElement.querySelector('sb-checkbox .top-label');
    expect(top?.textContent?.trim()).toBe('Filter');
  });

  it('keeps the inline caption as the checkbox own name', () => {
    const caption = fixture.nativeElement.querySelector('sb-checkbox .box span');
    expect(caption?.textContent?.trim()).toBe('Only changed');
  });

  it('omits the top label element entirely when unset', () => {
    const bare = fixture.nativeElement.querySelectorAll('sb-checkbox');
    // The template's other checkbox has no topLabel.
    const without = Array.from(bare).find(
      (el) => !(el as Element).querySelector('.top-label'),
    );
    expect(without).toBeTruthy();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/ui/controls.spec.ts`
Expected: FAIL — `renders a top label above the box`, `top` is null.

- [ ] **Step 3: Implement**

Replace the `Checkbox` component's template and styles:

```ts
  template: `
    <label class="field" [class.stacked]="topLabel()">
      @if (topLabel(); as text) {
        <span class="top-label">{{ text }}</span>
      }
      <span class="box">
        <input
          type="checkbox"
          [checked]="checked()"
          [disabled]="disabled()"
          (change)="checked.set($any($event.target).checked)"
        />
        <span>{{ label() }}</span>
      </span>
    </label>
  `,
  styles: `
    .field {
      display: inline-flex;
      align-items: center;
      gap: var(--space-6);
      font-size: var(--text-table);
      color: var(--text);
      cursor: pointer;
    }
    /* Label above, control below -- the same two bands sb-select and
       sb-text-input have, so a checkbox can share a row with them. */
    .stacked { flex-direction: column; align-items: flex-start; gap: var(--space-4); }
    .top-label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    /* The control band. Height matched to every other control so the row
       aligns on the box, not on the caption's text. */
    .box { display: inline-flex; align-items: center; gap: var(--space-6); height: var(--control-h); }
    .field:has(input:disabled) { color: var(--text-faint); cursor: default; }
    input { accent-color: var(--accent); }
  `,
```

and add to the class:

```ts
  /** Rendered above the box, matching sb-select and sb-text-input, so a
   *  checkbox can sit in a control row without breaking its alignment. The
   *  inline `label` stays either way -- it is the checkbox's own name. */
  readonly topLabel = input<string | null>(null);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/app/ui/controls.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/form-controls.ts frontend/src/app/ui/controls.spec.ts
git commit -m "feat(ui): optional top label on sb-checkbox"
```

---

### Task 4: The `sb-control-row` primitive

**Files:**
- Modify: `frontend/src/app/ui/layout.ts` (append after `TabBar`, before `Drawer`)
- Test: `frontend/src/app/ui/controls.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `ControlRow` component, selector `sb-control-row`, one input
  `stacked: InputSignal<boolean>` (default `false`). Tasks 5, 8, 9–12 import it
  from `'../../ui/layout'` (workspaces) or `'./layout'` (ui).

- [ ] **Step 1: Write the failing test**

In `controls.spec.ts`, import `ControlRow` from `'./layout'`, add it to the host
component's `imports`, and add to the template:

```html
    <sb-control-row>
      <sb-text-input label="Search" [(value)]="query" />
      <button sb-button>Go</button>
    </sb-control-row>
    <sb-control-row [stacked]="true"><button sb-button>Kill</button></sb-control-row>
```

Then:

```ts
  it('projects its controls', () => {
    const row = fixture.nativeElement.querySelector('sb-control-row .row');
    expect(row?.querySelector('sb-text-input')).toBeTruthy();
    expect(row?.querySelector('button[sb-button]')).toBeTruthy();
  });

  it('marks a stacked row so it can collapse at narrow widths', () => {
    const rows = fixture.nativeElement.querySelectorAll('sb-control-row .row');
    expect(rows[0].classList.contains('stacked')).toBe(false);
    expect(rows[1].classList.contains('stacked')).toBe(true);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/ui/controls.spec.ts`
Expected: FAIL — `'sb-control-row' is not a known element`.

- [ ] **Step 3: Implement**

Append to `layout.ts`:

```ts
/**
 * The one sanctioned control row.
 *
 * Before this, 47 rows across the workspaces each picked their own
 * `align-items` — `center`, `baseline`, `flex-start`, `stretch` — and a row
 * mixing a labelled input with a bare button could not align under any of
 * them, because the two controls disagreed about where their label went and
 * differed by 4px in height. `--control-h` and the checkbox's top label fixed
 * the controls; this fixes the container.
 *
 * **`flex-end`, and the reason matters.** A labelled control is label-band +
 * control-band; a bare button is control-band only. Aligning on the BOTTOM
 * edge is the only rule under which both land on the same line, whatever the
 * label does above it.
 *
 * Flexbox already aligns per-line when wrapping — `align-items` applies within
 * each flex line, not across the container — so a wrapped second line aligns
 * with itself for free. That was never the bug; mismatched control heights
 * inside one line was.
 *
 * `stacked` collapses the row to a full-width column below `sm` (640px).
 * `scan-tab`'s kill row hand-rolled exactly this; it belongs here instead.
 */
@Component({
  selector: 'sb-control-row',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="row" [class.stacked]="stacked()"><ng-content /></div>`,
  styles: `
    .row {
      display: flex;
      align-items: flex-end;
      align-content: flex-start;
      flex-wrap: wrap;
      gap: var(--space-10);
    }
    /* 640 is breakpoints.ts's sm floor, repeated as a literal because
       @media cannot evaluate var() -- the same reason the breakpoints are
       not tokens. breakpoints.spec.ts pins the arithmetic. */
    @media (max-width: 639px) {
      .stacked { flex-direction: column; align-items: stretch; }
    }
  `,
})
export class ControlRow {
  readonly stacked = input(false);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/app/ui/controls.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/layout.ts frontend/src/app/ui/controls.spec.ts
git commit -m "feat(ui): sb-control-row, the one sanctioned control row"
```

---

### Task 5: The two `ui/` rows become consumers

**Files:**
- Modify: `frontend/src/app/ui/filter-bar.ts:24-55` (`FilterBar`)
- Modify: `frontend/src/app/ui/confirm-dialog.ts:38` (template), `:72-73` (styles)
- Test: `frontend/src/app/ui/controls.spec.ts` (existing assertions must still pass)

**Interfaces:**
- Consumes: `ControlRow` from Task 4.
- Produces: nothing new. `FilterBar`'s public API (`activeCount`, `cleared`) is
  unchanged.

- [ ] **Step 1: Run the existing tests to establish green**

Run: `cd frontend && npx vitest run src/app/ui/controls.spec.ts`
Expected: PASS. These assertions are the safety net for this refactor — the
filter bar's projected controls, its active count and its Clear all button must
behave identically afterwards.

- [ ] **Step 2: Convert `FilterBar`**

Import `ControlRow` from `'./layout'` and add it to `imports`. Replace the
template and the `.bar` / `.controls` styles:

```ts
  template: `
    <sb-control-row>
      <ng-content />

      @if (activeCount() > 0) {
        <span class="active num">{{ activeCount() }} active</span>
        <button sb-button variant="ghost" type="button" (click)="cleared.emit()">
          Clear all
        </button>
      }
    </sb-control-row>
  `,
  styles: `
    :host { display: block; padding: var(--space-10) 0; }
    .active { margin-left: auto; color: var(--text-secondary); font-size: var(--text-table); }
  `,
```

The nested `.controls` wrapper goes: it existed only to re-declare the same
flex rule the outer bar already had, and one row is one row.

- [ ] **Step 3: Convert `ConfirmDialog`'s action row**

In `confirm-dialog.ts`, import `ControlRow` from `'./layout'`, add it to
`imports`, change `<div class="actions">` to `<sb-control-row class="actions">`
and its closing tag to `</sb-control-row>`. In the styles, replace the
`.actions` rule's `display: flex;` and any `align-items` / `gap` lines it
carries with:

```css
    .actions { justify-content: flex-end; }
```

(`sb-control-row` supplies display, alignment, wrap and gap; only the
right-alignment is this dialog's own.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/app/ui/`
Expected: PASS, unchanged count.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/filter-bar.ts frontend/src/app/ui/confirm-dialog.ts
git commit -m "refactor(ui): filter bar and confirm dialog use sb-control-row"
```

---

# Phase 2 — Settings

*Parallel with Phase 3. One worker takes Tasks 6–8 in order.*

### Task 6: Group a section's fields by control type

**Files:**
- Create: `frontend/src/app/workspaces/system/settings-grouping.ts`
- Create: `frontend/src/app/workspaces/system/settings-grouping.spec.ts`

**Interfaces:**
- Consumes: `SettingField` from `'../../api/models'`; the same three-way
  mapping `settings-tab.ts` already implements in `controlOf`.
- Produces:
  - `export type ControlKind = 'checkbox' | 'select' | 'input';`
  - `export function controlOf(field: SettingField): ControlKind`
  - `export interface FieldGroup { kind: ControlKind; fields: SettingField[] }`
  - `export function groupByControl(fields: SettingField[]): FieldGroup[]`
  Task 7 imports all four into `settings-tab.ts`.

- [ ] **Step 1: Write the failing test**

Create `settings-grouping.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { SettingField } from '../../api/models';
import { controlOf, groupByControl } from './settings-grouping';

function field(key: string, type: string): SettingField {
  return { key, label: key, type, value: '', default: '', help: '',
           options: [], sensitive: false, hot_reloadable: true,
           min: null, max: null, step: null } as unknown as SettingField;
}

describe('groupByControl', () => {
  it('orders groups checkboxes, selects, then inputs', () => {
    const groups = groupByControl([
      field('a_text', 'string'),
      field('b_flag', 'checkbox'),
      field('c_mode', 'select'),
    ]);
    expect(groups.map((g) => g.kind)).toEqual(['checkbox', 'select', 'input']);
  });

  it('preserves schema order inside a group', () => {
    const groups = groupByControl([
      field('z_flag', 'checkbox'),
      field('a_flag', 'checkbox'),
    ]);
    expect(groups[0].fields.map((f) => f.key)).toEqual(['z_flag', 'a_flag']);
  });

  it('omits a group with no fields rather than emitting an empty one', () => {
    const groups = groupByControl([field('only', 'checkbox')]);
    expect(groups).toHaveLength(1);
    expect(groups[0].kind).toBe('checkbox');
  });

  it('treats every non-checkbox, non-select type as an input', () => {
    for (const type of ['string', 'number', 'float', 'password']) {
      expect(controlOf(field('k', type))).toBe('input');
    }
  });

  it('returns nothing for an empty section', () => {
    expect(groupByControl([])).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/workspaces/system/settings-grouping.spec.ts`
Expected: FAIL — cannot resolve `./settings-grouping`.

- [ ] **Step 3: Implement**

Create `settings-grouping.ts`:

```ts
import { SettingField } from '../../api/models';

/**
 * Which control a field gets, and how a section's fields are grouped by it.
 *
 * Extracted from `settings-tab.ts` so the partition is a pure function with
 * its own tests, rather than a computed buried in a 585-line component.
 *
 * **The mapping is by `type` alone, never by key.** `GET /system/settings`
 * ships `config.py`'s schema and this form renders whatever arrives, so a new
 * setting appears with zero frontend change (spec v14 Decision 8). An
 * `if (key === …)` anywhere in this file would quietly end that property.
 */
export type ControlKind = 'checkbox' | 'select' | 'input';

export function controlOf(field: SettingField): ControlKind {
  if (field.type === 'checkbox') return 'checkbox';
  if (field.type === 'select') return 'select';
  return 'input';
}

export interface FieldGroup {
  kind: ControlKind;
  fields: SettingField[];
}

/**
 * A section's fields, partitioned by control type.
 *
 * Checkboxes first, then selects, then text and number inputs: shortest cells
 * to tallest, so the most variable cells sink to the bottom of the panel and
 * the eye gets a compact block of toggles at the top.
 *
 * **Stable within a group** — `config.py`'s declaration order survives, so
 * settings written next to each other stay next to each other. A sort here
 * would scatter them alphabetically and lose the author's grouping.
 *
 * An empty group is omitted rather than emitted, so the template never has to
 * guard against rendering a header-less run of nothing.
 */
const ORDER: ControlKind[] = ['checkbox', 'select', 'input'];

export function groupByControl(fields: SettingField[]): FieldGroup[] {
  return ORDER.map((kind) => ({
    kind,
    fields: fields.filter((field) => controlOf(field) === kind),
  })).filter((group) => group.fields.length > 0);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/app/workspaces/system/settings-grouping.spec.ts`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/system/settings-grouping.ts frontend/src/app/workspaces/system/settings-grouping.spec.ts
git commit -m "feat(settings): group a section's fields by control type"
```

---

### Task 7: Render the groups, and align cells with subgrid

**Files:**
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts:82-157` (the
  `.fields` block), `:~335-345` (the `.fields` / `.field` / `.changed` styles),
  and the class's `controlOf` (now imported)

**Interfaces:**
- Consumes: `groupByControl`, `controlOf`, `FieldGroup` from Task 6.
- Produces: nothing new externally. Task 8 edits the same file afterwards.

- [ ] **Step 1: Delete the local `controlOf` and import the module**

Add to the imports at the top of the file:

```ts
import { FieldGroup, controlOf, groupByControl } from './settings-grouping';
```

Delete the `controlOf` method from the class (it moved in Task 6) and add:

```ts
  protected readonly groupsOf = groupByControl;
  protected readonly controlOf = controlOf;
```

- [ ] **Step 2: Restructure the template**

Replace the whole `<div class="fields"> … </div>` block with a group loop. Note
each `.field` now emits **exactly four children** — the four subgrid bands — so
an absent help block still occupies its row:

```html
        @for (group of groupsOf(section.fields); track group.kind) {
          <div class="fields" [class.compact]="group.kind === 'checkbox'">
            @for (field of group.fields; track field.key) {
              <div
                class="field"
                [class.changed]="isChanged(field)"
                [class.off-default]="store.differsFromDefault(field)"
              >
                <span class="band-label"></span>

                <div class="band-control">
                  @switch (controlOf(field)) {
                    @case ('checkbox') {
                      <sb-checkbox
                        [label]="field.label"
                        [checked]="boolValue(field)"
                        (checkedChange)="store.edit(field, $event)"
                      />
                    }
                    @case ('select') {
                      <sb-select
                        [label]="field.label"
                        [options]="optionsOf(field)"
                        [value]="textValue(field)"
                        (valueChange)="store.edit(field, $event)"
                      />
                    }
                    @default {
                      <sb-text-input
                        [label]="field.label"
                        [type]="inputTypeOf(field)"
                        [min]="field.min"
                        [max]="field.max"
                        [step]="field.step"
                        [value]="textValue(field)"
                        (valueChange)="store.edit(field, $event)"
                      />
                    }
                  }
                </div>

                <p class="help">{{ field.help }}</p>

                <p class="meta">
                  <span class="key">{{ field.key }}</span>
                  @if (field.default) {
                    <span class="default-badge" title="Default value">{{ field.default }}</span>
                  }
                  @if (store.differsFromDefault(field)) {
                    <button
                      sb-button
                      variant="ghost"
                      type="button"
                      class="reset"
                      [title]="'Reset to ' + field.default"
                      (click)="store.resetField(field)"
                    >
                      reset to default
                    </button>
                  }
                  @if (!field.hot_reloadable) {
                    <span class="restart">restart required</span>
                  }
                  @if (field.sensitive) {
                    <span class="secret">stored value hidden — type to replace</span>
                  }
                </p>
              </div>
            }
          </div>
        }
```

The empty `.band-label` span is deliberate: the control components render their
own labels, but the band must exist so all four rows of every cell map onto the
parent's rows. The `@if (field.help)` guard is gone for the same reason — an
empty `<p>` collapses to nothing visually and keeps the band count at four.

- [ ] **Step 3: Replace the grid styles**

Replace the `.fields`, `.field` and `.changed` rules:

```css
    .fields {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: var(--space-14);
      /* Between groups, against --space-14 between fields. The grouping is
         signposted by this gap and nothing else: sub-headings here would be
         widget-shape names ("Toggles", "Values") under a panel that already
         has a real one, and every section would carry three. */
      margin-bottom: var(--space-20);
    }
    /* A checkbox has no 260px-wide control to hold. */
    .compact { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }

    /* Four bands -- label, control, help, meta -- mapped onto four parent
       rows. The parent then sizes each band to the TALLEST cell across the
       row, so every control starts at the same y and every meta line bottoms
       out together, with the help text unclamped.
       Without subgrid the two requirements fight: fixed per-cell rows need
       the help clamped, and unclamped help puts every control at its own
       offset. */
    .field {
      grid-row: span 4;
      display: grid;
      grid-template-rows: subgrid;
      gap: var(--space-4);
      /* A CONSTANT gutter on every cell. Before this, .changed added a 2px
         border plus 8px of padding to edited fields only, so typing in a
         field shoved its contents 10px right of its neighbours -- the change
         marker was itself an alignment offender. */
      border-left: 2px solid transparent;
      padding-left: var(--space-8);
    }
    .changed { border-left-color: var(--accent); }
    .band-control { display: flex; align-items: flex-end; }
```

- [ ] **Step 4: Run the frontend suite**

Run: `cd frontend && npm test`
Expected: PASS. If a settings spec asserted the old flat `.fields` structure,
update it to query `.fields .field` — the class names are unchanged, only their
nesting is.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/system/settings-tab.ts
git commit -m "feat(settings): grouped sections with subgrid-aligned cells"
```

---

### Task 8: The find row and the save bar

**Files:**
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts:49-62` (`.find`),
  `:163-203` (`.bar`), and their styles

**Interfaces:**
- Consumes: `ControlRow` (Task 4), `Checkbox.topLabel` (Task 3).
- Produces: nothing new.

- [ ] **Step 1: Import the primitive**

Add `ControlRow` to the file's `imports` array and to its import statement from
`'../../ui/layout'` (which already imports `Panel`).

- [ ] **Step 2: Convert the find row**

Replace the `<div class="find" role="search">` block:

```html
    <sb-control-row class="find" role="search">
      <sb-text-input
        label="Find a setting"
        type="text"
        [value]="store.settingsQuery()"
        (valueChange)="store.setSettingsQuery($event)"
      />
      <sb-checkbox
        topLabel="Filter"
        label="Only changed from default"
        [checked]="store.onlyChanged()"
        (checkedChange)="store.setOnlyChanged($event)"
      />
      <span class="found">{{ foundLabel() }}</span>
    </sb-control-row>
```

The checkbox's `topLabel` is what lets it sit beside the labelled search input:
both now have a label band above a 28px control band, so their boxes align.

- [ ] **Step 3: Convert the save bar and drop the dead styles**

Replace `<div class="bar">` with `<sb-control-row class="bar">` (closing tag
`</sb-control-row>`), and `<div class="bar-actions">` with
`<sb-control-row class="bar-actions">`.

In the styles, delete the `display: flex`, `align-items`, `gap` and `flex-wrap`
declarations from `.find`, `.bar` and `.bar-actions` — the primitive owns all
four. Keep only what is each row's own:

```css
    .find { margin-bottom: var(--space-10); }
    .find .found {
      margin-left: auto;
      color: var(--text-faint);
      font-size: var(--text-chip);
      font-variant-numeric: tabular-nums;
    }
    .bar-actions { margin-left: auto; }
```

- [ ] **Step 4: Run the frontend suite**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/system/settings-tab.ts
git commit -m "refactor(settings): find row and save bar use sb-control-row"
```

---

# Phase 3 — The workspaces

*Parallel with Phase 2 and internally parallel: four workers, one task each.*

**The method, identical in Tasks 9–12 — classify, then convert.** In each file,
read every `display: flex` rule and sort it into one of three buckets:

- **Control row** — the rule's element contains `sb-button`, `sb-select`,
  `sb-text-input`, `sb-checkbox` or `sb-filter-bar`. Convert: replace the
  element with `<sb-control-row class="…">`, delete `display`, `align-items`,
  `align-content`, `flex-wrap` and `gap` from its CSS rule, keep anything else
  (`margin`, `justify-content`, `margin-left: auto`).
- **Text row** — `.head`, `.meta`, `.cell`, `.count`, figures. **Leave it
  alone.** `align-items: baseline` on a row of text is correct and converting it
  would be the same mistake in the other direction.
- **Layout container** — grids, page scaffolding, panel bodies. Leave alone.

Import `ControlRow` from `'../../ui/layout'` and add it to the component's
`imports` array.

### Task 9: `trades/trades.ts`

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (16 control
  references, 3 flex rules)
- Test: `frontend/src/app/workspaces/trades/` existing specs

**Interfaces:**
- Consumes: `ControlRow` from Task 4.
- Produces: nothing.

- [ ] **Step 1: Establish green and classify**

Run: `cd frontend && npm test`
Expected: PASS — the baseline this refactor must preserve.

Then list the file's flex rules and their buckets:

```bash
cd frontend/src/app/workspaces/trades && grep -n "display: flex" -B 1 trades.ts
```

Record each as control / text / container before editing anything.

- [ ] **Step 2: Convert the control rows**

For every rule classified as a control row, apply the method above. Example
shape — the toolbar wrapping the filter bar and the column picker:

```html
<sb-control-row class="toolbar">
  <sb-filter-bar [activeCount]="activeFilters()" (cleared)="clearFilters()">
    <sb-select label="Strategy" … />
    <sb-select label="Horizon" … />
  </sb-filter-bar>
  <sb-column-picker … />
</sb-control-row>
```

with its CSS reduced to what is the toolbar's own:

```css
    .toolbar { margin-bottom: var(--space-10); }
```

- [ ] **Step 3: Leave the text rows**

Confirm no `.head`, `.cell` or `.count` rule was touched:

```bash
cd frontend/src/app/workspaces/trades && grep -n "align-items: baseline" trades.ts
```

Expected: the same lines as before Step 2.

- [ ] **Step 4: Run the suite**

Run: `cd frontend && npm test`
Expected: PASS, unchanged count.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades/trades.ts
git commit -m "refactor(trades): control rows use sb-control-row"
```

---

### Task 10: `analytics/analytics.ts`

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (1523 lines, four
  tabs, 6 control references, 7 flex rules)

**Interfaces:**
- Consumes: `ControlRow` from Task 4.
- Produces: nothing.

- [ ] **Step 1: Establish green and classify**

Run: `cd frontend && npm test`
Expected: PASS.

```bash
cd frontend/src/app/workspaces/analytics && grep -n "display: flex" -B 1 analytics.ts
```

This file has four tabs and its rows are spread across them; classify all seven
before editing, and note which tab each belongs to so Step 4's check covers all
four.

- [ ] **Step 2: Convert the control rows**

Apply the method. Each converted element becomes `<sb-control-row class="…">`
and its CSS rule loses `display`, `align-items`, `align-content`, `flex-wrap`
and `gap`, keeping margins and `justify-content`.

- [ ] **Step 3: Leave the text rows**

`.heat` and `.scan-figures`-style rows on `align-items: baseline` are text rows.
Confirm untouched:

```bash
cd frontend/src/app/workspaces/analytics && grep -n "align-items: baseline" analytics.ts
```

- [ ] **Step 4: Run the suite**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "refactor(analytics): control rows use sb-control-row"
```

---

### Task 11: `system/scan-tab.ts` and `system/logs-tab.ts`

**Files:**
- Modify: `frontend/src/app/workspaces/system/scan-tab.ts` (5 control
  references, 2 flex rules, owns the `.kill` stacking row)
- Modify: `frontend/src/app/workspaces/system/logs-tab.ts` (3 control
  references, 5 flex rules)

**Interfaces:**
- Consumes: `ControlRow` and its `stacked` input from Task 4.
- Produces: nothing.

- [ ] **Step 1: Establish green and classify**

Run: `cd frontend && npm test`
Expected: PASS.

```bash
cd frontend/src/app/workspaces/system && grep -n "display: flex" -B 1 scan-tab.ts logs-tab.ts
```

- [ ] **Step 2: Convert `scan-tab`, and move the kill row's stacking into the primitive**

`scan-tab` hand-rolls the collapse this primitive now owns:

```css
      .kill { flex-direction: column; align-items: stretch; }
```

Convert the element to `<sb-control-row class="kill" [stacked]="true">` and
**delete that media-query rule entirely**, along with the `.kill` rule's
`display`, `align-items` and `gap`. The behaviour is identical — the primitive
uses the same 640px floor — and it is now one implementation instead of a local
exception.

- [ ] **Step 3: Convert `logs-tab`**

Its `.level` and `.actions` rows carry the level filter and the follow toggle;
both are control rows. `.count` is a text row and stays.

- [ ] **Step 4: Run the suite**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/system/scan-tab.ts frontend/src/app/workspaces/system/logs-tab.ts
git commit -m "refactor(system): scan and logs control rows use sb-control-row"
```

---

### Task 12: `risk`, `watchlist`, `dashboard`, `trade-detail`

**Files:**
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (2 controls, 9 flex rules —
  mostly text and containers)
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts` (2 controls, 3
  flex rules; the `.add` row is `align-items: flex-start`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (1 control, 4)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (1 control, 5)

**Interfaces:**
- Consumes: `ControlRow` from Task 4.
- Produces: nothing.

- [ ] **Step 1: Establish green and classify**

Run: `cd frontend && npm test`
Expected: PASS.

```bash
cd frontend/src/app/workspaces && grep -n "display: flex" -B 1 \
  risk/risk.ts watchlist/watchlist.ts dashboard/dashboard.ts trades/trade-detail.ts
```

`risk.ts` has the highest ratio of text rows to control rows in the codebase —
nine flex rules and two controls. Expect to convert one or two and leave the
rest.

- [ ] **Step 2: Convert the control rows**

Apply the method per file. `watchlist`'s `.add` row (the add-ticker input beside
its button) is the clearest case: `align-items: flex-start` is why the button
currently sits level with the input's *label* instead of its box.

- [ ] **Step 3: Leave the text rows**

```bash
cd frontend/src/app/workspaces && grep -n "align-items: baseline" \
  risk/risk.ts watchlist/watchlist.ts dashboard/dashboard.ts trades/trade-detail.ts
```

Expected: unchanged from Step 1.

- [ ] **Step 4: Run the suite**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/trades/trade-detail.ts
git commit -m "refactor(workspaces): remaining control rows use sb-control-row"
```

---

# Phase 4 — Lock it in

### Task 13: The guard that catches the 48th row

**Files:**
- Modify: `frontend/src/app/ui/tokens.spec.ts`

**Interfaces:**
- Consumes: the converted state of every file from Tasks 9–12.
- Produces: nothing.

**Do not start this task until Tasks 9–12 are all committed.** Run earlier it
fails for the right reason at the wrong time.

- [ ] **Step 1: Write the failing test**

Append to `tokens.spec.ts`:

```ts
import { readdirSync } from 'node:fs';

const WORKSPACES = join(process.cwd(), 'src/app/workspaces');

function workspaceSources(): { name: string; source: string }[] {
  const out: { name: string; source: string }[] = [];
  for (const dir of readdirSync(WORKSPACES)) {
    for (const file of readdirSync(join(WORKSPACES, dir))) {
      if (!file.endsWith('.ts') || file.endsWith('.spec.ts')) continue;
      out.push({
        name: `${dir}/${file}`,
        source: readFileSync(join(WORKSPACES, dir, file), 'utf8'),
      });
    }
  }
  return out;
}

const CONTROLS = /sb-button|sb-select|sb-text-input|sb-checkbox|sb-filter-bar/;

describe('no workspace hand-rolls a control row', () => {
  for (const { name, source } of workspaceSources()) {
    if (!CONTROLS.test(source)) continue;

    it(`${name} routes its control rows through sb-control-row`, () => {
      // Every flex rule that also declares an alignment is a row that took a
      // position on the question sb-control-row exists to answer. A text row
      // (.head, .meta, .cell) is exempt by name -- baseline on text is right.
      const offenders = [...source.matchAll(/\.([\w-]+)\s*\{[^}]*display:\s*flex[^}]*\}/g)]
        .filter(([rule]) => /align-items:\s*(center|flex-start|stretch)/.test(rule))
        .map(([, className]) => className)
        .filter((className) => !/^(head|meta|cell|count|figures|tags)/.test(className));

      expect(offenders).toEqual([]);
    });
  }
});
```

- [ ] **Step 2: Run test to verify it fails on an unconverted file**

Run: `cd frontend && git stash && npx vitest run src/app/ui/tokens.spec.ts; git stash pop`
Expected: FAIL on several workspace files — proving the guard has teeth. Then
with the conversions applied it must pass; if it does not, the named file has a
control row Tasks 9–12 missed. Fix the file, not the test.

- [ ] **Step 3: Run against the converted tree**

Run: `cd frontend && npx vitest run src/app/ui/tokens.spec.ts`
Expected: PASS.

- [ ] **Step 4: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/tokens.spec.ts
git commit -m "test(ui): guard against hand-rolled control rows"
```

---

### Task 14: The responsive pass

**Files:**
- Modify: whichever workspace files the pass finds wanting (expected: few or
  none)
- Reference: `frontend/src/app/ui/breakpoints.ts` — `sm` 640, `md` 1024,
  `lg` 1440, `xl` 1920, each a **floor**

**Interfaces:**
- Consumes: every converted row.
- Produces: nothing.

- [ ] **Step 1: Build and serve**

Run: `cd frontend && npm start`
Open the admin, log in, and put the browser at 375px, 640px, 1024px, 1440px and
1920px in turn (device toolbar, responsive mode).

- [ ] **Step 2: Walk every converted row at each width**

At each width visit: Dashboard, Trades (filter bar + chips + pagination), Trade
detail (all five tabs), Watchlist (add row), Ticker detail, Risk, Analytics (all
four tabs), System → Scan, System → Logs, System → Settings.

Record, per row: does it wrap, and when it wraps does each line align on its own
bottom edge? Two specific checks:

- **640px** — the sidebar becomes an overlay; rows gain width abruptly.
- **1024px** — the sidebar drops to its rail; the same in reverse.

- [ ] **Step 3: Check the Settings grid at `xs`**

At 375px the settings grid must show exactly one column, and every cell's four
bands must still line up with its neighbours above and below. Subgrid on a
single-column grid is the degenerate case and is where a band-count mistake in
Task 7 would show.

- [ ] **Step 4: Apply `stacked` where a row is unreadable wrapped**

For any row that wraps into something worse than a stack — controls of very
different widths, or a row where the wrapped line reads as unrelated to the
first — set `[stacked]="true"` on its `sb-control-row`. Do not add a new media
query; the primitive owns that breakpoint.

- [ ] **Step 5: Run the suite and commit**

Run: `cd frontend && npm test`
Expected: PASS.

```bash
git add frontend/src/app/workspaces/
git commit -m "fix(ui): responsive pass over the converted control rows"
```

Then the release marker, its own commit, last:

```bash
# VERSION.json: ui 1.2.3 -> 1.2.4, ui_updated to now (UTC, YYYY-MM-DD HH-MM-SS)
git add VERSION.json
git commit -m "release(ui): 1.2.4 -- control alignment and grouped settings"
```

---

## Definition of done

- `npm test` green from `frontend/`, including the two new guards.
- `python scripts/testrun.py full` green (`0 failed`, `0 xfailed`).
- A button beside a field is flush in every workspace.
- Every Settings section shows checkboxes, then selects, then inputs, with the
  bands of every cell in a row aligned.
- Typing in a settings field moves nothing.
- `VERSION.json` bumped `ui` to 1.2.4 in its own final commit.
