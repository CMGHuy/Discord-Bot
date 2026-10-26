# v195 — Graphite, Part 4: flat controls, one KPI strip, states and overlays

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-11:" -A 400 <this file>`.

**Scope of this part (V195-10..V195-12):** spec Phase 2, the three remaining primitive families. V195-10 makes the control family flat: no tinted borders, no `color-mix()`, hover is the raised surface, and the accent appears only on a focus ring, a selected option or an engaged filter; the Filters and Columns count badges lose their accent fill. V195-11 gives the stat strip, stat tile and metric card one KPI-strip look: hairline-split cells with one padding and one gap, inside one bordered surface (the panel when the strip sits in one, the strip's own frame when it stands alone in `sb-page`'s `[page-kpis]` slot), and no tinted metric-card fill. V195-12 gives empty, loading and error one style each inside the panel body (`sb-async` reuses `sb-empty-state`, and its error block matches `sb-panel-error`), moves the loading rings off the accent, and pins the confirm dialog, drawer and toasts to the one overlay surface and shadow.

**Where commands run.** Shell state does not persist between Bash calls and `cd` breaks the guardrail hooks, so every command below spells out the worktree path:

- `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`
- `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`

Frontend runs through `npm --prefix "$WT/frontend" ...`. Edit files only under `$WT/`; never the main tree's copies.

**The state parts 1–3 leave (read before editing).** After V195-9, in `$WT`:

- `frontend/src/styles/tokens.css`: `--panel-radius: 6px`, `--control-radius: 4px`, `--chip-radius: 4px`, `--radius-sm: 2px`; `--panel-bg: var(--surface)`, `--panel-border: 1px solid var(--border)`, `--panel-shadow: none`; `--shadow-overlay` unchanged (`0 16px 40px rgba(0, 0, 0, .55), 0 2px 8px rgba(0, 0, 0, .4)`, the one shadow); `--transition: var(--dur-ui) var(--ease-out)` at 120ms (V195-5); density token `--panel-pad` (V195-6: `var(--space-14)` dense and touch, `var(--space-20)` comfortable on a desktop fine pointer); `--text-micro`/`--text-chip` floored at 12px (V195-3).
- `frontend/src/app/ui/stat-tile.ts`: `<div class="tile"` (V195-5 removed `sb-lift`); v194 added the `.label-row` with `about`'s `sb-hint`, `PERFORMANCE_CAVEAT` and the inline `shortfall` (no `title`).
- `frontend/src/app/ui/metric-card.ts`: `<div class="card">` (V195-5); v194 replaced the host `title` with a `.label-row` holding the label and an `sb-hint` for `description`.
- `frontend/src/app/ui/stat-strip.ts` and `stat-strip.spec.ts`: V195-5 deleted `--panel-shadow-lift` from the host and the doc, removed it from the spec's declaration list, and replaced the lift describe with `nothing in a strip lifts (v195 §1.2)`.
- `frontend/src/app/ui/confirm-dialog.ts`: V195-8 added `dangerVariant` and the `[variant]="destructive() ? dangerVariant() : 'primary'"` binding; v194 made `requestClose()` dispatch `DIALOG_CLOSING_EVENT`. Its styles are untouched since v168.
- `frontend/src/app/ui/layout.ts`: V195-9 re-skinned `Panel` only (`--panel-pad`, 13px title); `Drawer` is unchanged since v194.
- `frontend/src/styles.css`: V195-6 rewrote the `body` comment and `.register-instrument`; V195-9 added `.sb-meta` after `.sb-help` and a paragraph to the `.sb-panel` comment. The strip grid (`.sb-strip-grid` and its two `@media` rules) still ends the file.
- `frontend/src/app/ui/elevation.spec.ts`: imports `resolveToken`; ends with V195-3's `describe('v195 §1.2: panels are flat', ...)`; V195-4 replaced the ambient case; V195-5 dropped `sb-lift` from the three markup pins.

v194 and V195-5..V195-9 edited several of these files: every step below names its edit by symbol or by the exact string, never by line number. Re-read each file before editing it.

---

# Phase 2 — Primitives (continued)

### Task V195-10: Flat controls: chip, segmented, form controls, filter bar, control bar, toolbar (4px radius, accent only on primary/selected)
**Model:** sonnet — six small style blocks re-skinned against one source-scan gate; the care is in finding every accent declaration that is not a focus ring or a selected state, and keeping the shared Filters/Columns badge identical.

**Files:**
- Modify: `frontend/src/app/ui/chip.ts` (the `.q1`, `.q2`, `.q4`, `.q5` rules; the `Chip` doc comment)
- Modify: `frontend/src/app/ui/chip.spec.ts` (one new describe)
- Modify: `frontend/src/app/ui/segmented.ts` (the `.segment:hover` rule)
- Modify: `frontend/src/app/ui/segmented.spec.ts` (one new describe)
- Modify: `frontend/src/app/ui/form-controls.ts` (the `select { ... }` and TextInput `input { ... }` rules and the comment above `select`)
- Modify: `frontend/src/app/ui/form-controls.spec.ts` (one new describe)
- Modify: `frontend/src/app/ui/filter-bar.ts` (`FilterChips` styles: `.chip:hover` and `.active`)
- Modify: `frontend/src/app/ui/filter-bar.spec.ts` (one new describe)
- Modify: `frontend/src/app/ui/control-bar.ts` (the `.clear` rule; two new rules after it)
- Modify: `frontend/src/app/ui/toolbar.ts` (`.count`; one new rule after `.toolbar-sheet-button:focus-visible`)
- Modify: `frontend/src/app/ui/toolbar.spec.ts` (the badge case; one new case; one new describe, the family gate)
- Modify (not in the ledger row, see Interfaces): `frontend/src/app/ui/control-bar.spec.ts` (one new describe), `frontend/src/app/ui/column-picker.ts` (its `.count` rule, kept identical to the toolbar's)

**Interfaces:**
- Consumes: `--control-radius` and `--chip-radius` (both `4px` since V195-3); `--transition` (120ms since V195-5); `--surface-raised` (the spec's "raised / hover" step), `--accent`, `--accent-soft`, `--bg`, `--border`, `--border-strong`, `--text`, `--text-secondary` (V195-2 values). No TypeScript API changes: `Chip`, `QualityChip`, `Segmented`, `Select`, `TextInput`, `Checkbox`, `FilterBar`, `FilterChips`, `ControlBar`, `Toolbar` keep every input and output.
- Produces (later tasks and the gallery rely on these looks):
  - Hover on any control in the family is `background: var(--surface-raised)`; the accent appears only in a `:focus-visible` ring, on a selected option (`.current`, `.chip.active`), on an open Filters sheet (`[aria-expanded='true']`), on the engaged-filter dot (`.active-dot`) and as the checkbox `accent-color`.
  - Selected look, shared by `sb-segmented` and `sb-filter-chips`: `background: var(--accent-soft)` with `color: var(--text)` (filter chips add `border-color: var(--accent)`; a segment has no border of its own).
  - Count badge, shared by `sb-toolbar` and `sb-column-picker`: an outlined badge, `border: 1px solid var(--border-strong)`, `color: var(--text-secondary)`, no fill.
  - Fields (`sb-select`, `sb-text-input`) sit on `var(--bg)`, one step under the flat `--surface` panel.
- Ledger gap: `control-bar.spec.ts` is the only spec reading `control-bar.ts`, so the new Clear look is pinned there. `column-picker.spec.ts` asserts `ruleIn(picker, '.count')` **equals** `ruleIn(toolbar, '.count')`, so the toolbar's badge cannot change without `column-picker.ts` changing in the same commit; its spec needs no edit. No other task touches `control-bar.spec.ts` or `column-picker.ts`, so adding them here creates no parallel conflict.

**What changes, and what is already there.** V195-3 already moved every control corner to 4px through `--control-radius`/`--chip-radius`, and none of the six casts a shadow or paints a gradient. What is left is colour. Four quality chips draw a border mixed from a valence hue with `color-mix()` (the only `color-mix()` in the family): a quality band is told by its text colour and its `Lv4` / `Tier B` label, so the tinted border goes. Hover today only changes text or border colour; Graphite's raised step is the hover surface, so a hovered segment, filter chip and Clear take `--surface-raised`. The accent is interactive state only: it stays on focus rings and selected options, but the Filters/Columns count badge (a count, not a state) loses its `--accent-soft` fill, and the control bar's Clear stops being an accent link and becomes the same quiet control as `sb-filter-bar`'s ghost "Clear all". The Filters button gains the accent edge while its sheet is open, the one state it has. Since V195-3 a panel is the flat `--surface`, which is also the fields' fill, so a field inside a panel had no fill step left: fields move to the `--bg` well (the GitHub-dark field look the palette follows) and keep the strong hairline. No input, output or markup changes, so no call site changes.

- [ ] **Step 1: Write the failing chip, segmented and form-control tests**

1. Append to `$WT/frontend/src/app/ui/chip.spec.ts`:

```ts
/* v195 Phase 2: a chip is flat. Its 4px corner is the --chip-radius token
 * (V195-3); a quality band is told by its text colour and its label, never
 * by a border mixed from a valence hue. */
describe('Chip is flat (v195 Phase 2)', () => {
  it('mixes no colour and gives each quality band its text colour only', () => {
    expect(SOURCE).not.toContain('color-mix(');
    for (const band of [1, 2, 3, 4, 5]) {
      const rule = SOURCE.match(new RegExp(`\\.q${band} \\{[^}]*\\}`))![0];
      expect(rule, `q${band}`).toBe(`.q${band} { color: var(--quality-${band}); }`);
    }
  });

  it('draws every chip on one hairline frame with the chip radius', () => {
    const chip = SOURCE.match(/\.chip \{[^}]*\}/)![0];
    expect(chip).toContain('border: 1px solid var(--border-strong);');
    expect(chip).toContain('border-radius: var(--chip-radius);');
  });
});
```

2. Append to `$WT/frontend/src/app/ui/segmented.spec.ts`:

```ts
/* v195 Phase 2: hover is the raised surface, and the accent tint marks the
 * selected segment only, so a hovered option never looks chosen. */
describe('Segmented is flat (v195 Phase 2)', () => {
  const rule = (selector: string) =>
    SOURCE.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{[^}]*\\}`))?.[0] ?? '';

  it('raises an unselected segment on hover and keeps the accent for the selected one', () => {
    const hover = rule('.segment:not(.current):hover');
    expect(hover).toContain('color: var(--text);');
    expect(hover).toContain('background: var(--surface-raised);');
    expect(hover).not.toContain('accent');
    expect(rule('.current')).toContain('background: var(--accent-soft);');
    expect(SOURCE).not.toMatch(/\.segment:hover \{/);
  });
});
```

3. Append to `$WT/frontend/src/app/ui/form-controls.spec.ts`:

```ts
/* v195 Phase 2: since V195-3 a panel is the flat --surface, so a field on
 * --surface had no fill step left against it. Fields sit one step down, on
 * the --bg well, behind the strong hairline; the accent is the focus ring
 * and the checkbox tick only. */
describe('v195 Phase 2: flat fields', () => {
  const field = (tag: 'select' | 'input') => SOURCE.match(new RegExp(`\\n {4}${tag} \\{[^}]*\\}`))?.[0] ?? '';

  it('fills the select and the text input with the --bg well behind the strong hairline', () => {
    for (const tag of ['select', 'input'] as const) {
      const rule = field(tag);
      expect(rule, tag).toContain('background: var(--bg);');
      expect(rule, tag).toContain('border: 1px solid var(--border-strong);');
      expect(rule, tag).toContain('border-radius: var(--control-radius);');
      expect(rule, tag).toContain('transition: border-color var(--transition);');
    }
    expect(SOURCE).not.toContain('background: var(--surface);');
  });

  it('keeps the accent to the focus ring and the checkbox tick', () => {
    expect(SOURCE).toMatch(/select:focus-visible \{ outline: 1px solid var\(--accent\); outline-offset: 1px; \}/);
    expect(SOURCE).toMatch(/input:focus-visible \{ outline: 1px solid var\(--accent\); outline-offset: 1px; \}/);
    expect(SOURCE).toMatch(/input \{ accent-color: var\(--accent\); \}/);
  });
});
```

(`field('input')` returns the first four-space-indented `input {` rule, the text input's; the checkbox's `input { accent-color ... }` comes later in the file.)

- [ ] **Step 2: Write the failing filter-bar, control-bar and toolbar tests**

1. Append to `$WT/frontend/src/app/ui/filter-bar.spec.ts` (it already defines `rule(selector)` above the v179 describes):

```ts
/* v195 Phase 2: a selected filter chip looks like a selected segment (the
 * accent tint, here with the accent edge too); hover is the raised surface
 * and never borrows the accent. */
describe('FilterChips selected and hover states (v195 Phase 2)', () => {
  it('marks the selected chip with the accent edge on the accent tint', () => {
    const selected = rule('.chip.active');
    expect(selected).toContain('color: var(--text)');
    expect(selected).toContain('border-color: var(--accent)');
    expect(selected).toContain('background: var(--accent-soft)');
  });

  it('raises an unselected chip on hover without touching the accent', () => {
    const hover = rule('.chip:not(.active):hover');
    expect(hover).toContain('color: var(--text)');
    expect(hover).toContain('border-color: var(--border-strong)');
    expect(hover).toContain('background: var(--surface-raised)');
    expect(hover).not.toContain('accent');
    expect(SOURCE).not.toMatch(/\.chip:hover \{/);
  });
});
```

2. Append to `$WT/frontend/src/app/ui/control-bar.spec.ts`:

```ts
/* v195 Phase 2: Clear is the same quiet control as sb-filter-bar's ghost
 * "Clear all", not an accent link: the accent is for selected state. */
describe('ControlBar Clear is a quiet control (v195 Phase 2)', () => {
  const rule = (selector: string) =>
    CONTROL_BAR_SOURCE.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{[^}]*\\}`))?.[0] ?? '';

  it('sets Clear in the secondary text on no fill, one control tall, 4px corners', () => {
    const clear = rule('.clear');
    for (const declaration of [
      'min-height: var(--control-h);',
      'min-width: var(--control-h);',
      'background: transparent;',
      'border: 0;',
      'border-radius: var(--control-radius);',
      'color: var(--text-secondary);',
      'font: inherit;',
      'font-size: var(--text-table);',
    ]) expect(clear, declaration).toContain(declaration);
    expect(clear).not.toContain('accent');
  });

  it('raises Clear on hover and rings it in the accent on keyboard focus only', () => {
    expect(rule('.clear:hover')).toContain('background: var(--surface-raised)');
    expect(rule('.clear:hover')).not.toContain('accent');
    expect(rule('.clear:focus-visible')).toContain('outline: 1px solid var(--accent)');
  });
});
```

3. In `$WT/frontend/src/app/ui/toolbar.spec.ts`, inside `describe('sb-toolbar one row pattern (v179 §3.3)', ...)`:
   - In `shows the demoted count as a numeric badge`, replace the line `expect(toolbarRule('.count')).toContain('background: var(--accent-soft)');` with

```ts
    // v195 Phase 2: a count is not a state, so it takes no accent.
    expect(toolbarRule('.count')).toContain('border: 1px solid var(--border-strong)');
    expect(toolbarRule('.count')).toContain('color: var(--text-secondary)');
    expect(toolbarRule('.count')).not.toContain('accent');
    expect(toolbarRule('.count')).not.toContain('background');
```

   - After that case, add:

```ts
  it('edges the Filters button in the accent while its sheet is open, its one state (v195 Phase 2)', () => {
    const button = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.toolbar-sheet-button')!;
    button.click();
    fixture.detectChanges();
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(toolbarRule(".toolbar-sheet-button[aria-expanded='true']")).toContain('border-color: var(--accent)');
  });
```

4. Append to the end of `$WT/frontend/src/app/ui/toolbar.spec.ts`:

```ts
/* v195 Phase 2: buttons, chips, segmented, form controls, filter bar,
 * control bar and toolbar are flat, 4px, and spend the accent only on a
 * keyboard focus ring and on selected or engaged state. button.ts is gated
 * by its own spec (V195-8); these are the other six. Source text: jsdom
 * computes no component style. */
const FAMILY = ['chip.ts', 'segmented.ts', 'form-controls.ts', 'filter-bar.ts', 'control-bar.ts', 'toolbar.ts'];
const stylesOf = (file: string) =>
  [...readFileSync(join(process.cwd(), 'src/app/ui', file), 'utf8').matchAll(/styles:\s*`([\s\S]*?)`/g)]
    .map(([, css]) => css)
    .join('\n')
    .replace(/\/\*[\s\S]*?\*\//g, '');
const rulesOf = (css: string) =>
  [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({ selector: selector.trim(), body }));
/** Where the accent may appear: a focus ring, a selected option, an open or engaged filter. */
const ACCENT_STATE = /:focus-visible|\.current\b|\.active\b|\[aria-expanded='true'\]|\[aria-pressed='true'\]/;

describe('the control family is flat (v195 Phase 2)', () => {
  it.each(FAMILY)('%s casts no shadow, paints no gradient, mixes no colour and moves nothing', (file) => {
    const css = stylesOf(file);
    expect(css.length).toBeGreaterThan(0);
    expect(css).not.toMatch(/box-shadow\s*:/);
    expect(css).not.toContain('gradient(');
    expect(css).not.toContain('color-mix(');
    expect(css).not.toMatch(/(?<![-\w])transform\s*:/);
  });

  it.each(FAMILY)('%s rounds every corner with the 4px control or chip radius', (file) => {
    const radii = [...stylesOf(file).matchAll(/border(?:-[a-z]+)*-radius:\s*([^;}]+)/g)].map(([, value]) => value.trim());
    for (const value of radii) expect(['var(--control-radius)', 'var(--chip-radius)'], `${file}: ${value}`).toContain(value);
  });

  it.each(FAMILY)('%s spends the accent only on focus, selected or engaged state', (file) => {
    for (const { selector, body } of rulesOf(stylesOf(file))) {
      for (const declaration of body.split(';').filter((d) => d.includes('var(--accent'))) {
        const allowed = ACCENT_STATE.test(selector) || declaration.trim().startsWith('accent-color:');
        expect(allowed, `${file}: ${selector} { ${declaration.trim()} }`).toBe(true);
      }
    }
  });
});
```

- [ ] **Step 3: Run them to make sure they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/chip.spec.ts --include src/app/ui/segmented.spec.ts --include src/app/ui/form-controls.spec.ts --include src/app/ui/filter-bar.spec.ts --include src/app/ui/control-bar.spec.ts --include src/app/ui/toolbar.spec.ts
```

Expected: FAIL. `chip.spec.ts`: `mixes no colour ...` (`color-mix(` found; `.q1` carries a border). `segmented.spec.ts`: the new case (no `.segment:not(.current):hover` rule). `form-controls.spec.ts`: `fills the select and the text input ...` (`var(--surface)`, no transition); the accent case already passes. `filter-bar.spec.ts`: both new cases. `control-bar.spec.ts`: both new cases (Clear is `var(--accent)`, no radius). `toolbar.spec.ts`: the badge case, the open-sheet case, `chip.ts casts no shadow ...` (`color-mix(`), and `control-bar.ts` / `toolbar.ts spends the accent only ...` (`.clear`, `.count`).

- [ ] **Step 4: Flatten the chip and the segmented control**

1. In `$WT/frontend/src/app/ui/chip.ts`, replace the five quality rules and the comment between them:

```css
    .q1 { color: var(--quality-1); border-color: color-mix(in srgb, var(--neg) 35%, transparent); }
    .q2 { color: var(--quality-2); border-color: color-mix(in srgb, var(--warn) 35%, transparent); }
    .q3 { color: var(--quality-3); }
    /* Its own hue, not --info's: info is lavender since v80 D1, and level 4
       is the ramp's yellow-green. */
    .q4 { color: var(--quality-4); border-color: color-mix(in srgb, var(--quality-4) 35%, transparent); }
    .q5 { color: var(--quality-5); border-color: color-mix(in srgb, var(--pos) 35%, transparent); }
```

with

```css
    /* v195 Phase 2: a band is its text colour on the chip's one hairline;
       the label (Lv4, Tier B) says the rest. The tinted borders mixed from
       a valence hue are gone with the rest of the decoration. Level 4 keeps
       its own hue, not --info's: info is lavender, level 4 the ramp's
       yellow-green. */
    .q1 { color: var(--quality-1); }
    .q2 { color: var(--quality-2); }
    .q3 { color: var(--quality-3); }
    .q4 { color: var(--quality-4); }
    .q5 { color: var(--quality-5); }
```

and in the `Chip` class doc comment (`A small labelled tag — tier, horizon, confidence.` …), append before its closing `*/`:

```ts
 *
 * v195 Phase 2: flat. One hairline frame (--border-strong) and the 4px
 * --chip-radius; the state tones tint, the quality tones colour the text.
```

2. In `$WT/frontend/src/app/ui/segmented.ts`, in `styles`, replace

```css
    .segment:first-child { border-left: 0; } .segment:hover { color: var(--text); }
```

with

```css
    .segment:first-child { border-left: 0; }
    /* v195 Phase 2: hover is the raised step; the accent tint is the selected segment's alone. */
    .segment:not(.current):hover { color: var(--text); background: var(--surface-raised); }
```

- [ ] **Step 5: Move the fields onto the `--bg` well**

In `$WT/frontend/src/app/ui/form-controls.ts`:

1. Replace the comment above `select {`

```css
    /* v80 D4: a hairline field on the panel's own ground. The caption is the
       global .sb-label. --text-control is 16px on touch, the size below which
       a phone zooms into a focused field. */
```

with

```css
    /* v80 D4: a hairline field; the caption is the global .sb-label.
       --text-control is 16px on touch, the size below which a phone zooms
       into a focused field. v195 Phase 2: the panel is the flat --surface
       now, so the field sits one step down on the --bg well, behind the
       strong hairline, and its edge brightens on hover. */
```

2. In the `select { ... }` rule and in the text input's `input { ... }` rule (the one with `min-width: 0;`), change `background: var(--surface);` to `background: var(--bg);` and add `transition: border-color var(--transition);` as the last declaration of each. The two rules become:

```css
    select {
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--bg);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
      transition: border-color var(--transition);
    }
```

```css
    input {
      min-width: 0;
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--bg);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
      transition: border-color var(--transition);
    }
```

The hover (`border-color: var(--text-muted)`), focus ring, disabled opacity and the checkbox rules stay as they are. `--text` on `--bg` is AA by contrast.spec (V195-2).

- [ ] **Step 6: Filter chips, control bar Clear and the toolbar badge**

1. In `$WT/frontend/src/app/ui/filter-bar.ts`, `FilterChips` styles: replace

```css
    .chip:hover { color: var(--text); border-color: var(--border-strong); }
    .chip:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    /* Selection is interactive state, which is what blue is for. */
    .active { color: var(--text); border-color: var(--accent); background: var(--surface-raised); }
```

with

```css
    /* v195 Phase 2: hover is the raised step, never the accent. */
    .chip:not(.active):hover { color: var(--text); border-color: var(--border-strong); background: var(--surface-raised); }
    .chip:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    /* Selection is interactive state, which is what the accent is for: the
       accent edge on the same accent tint a selected segment carries. */
    .chip.active { color: var(--text); border-color: var(--accent); background: var(--accent-soft); }
```

2. In `$WT/frontend/src/app/ui/control-bar.ts`, replace the `.clear { ... }` rule with:

```css
    /* v195 Phase 2: the same quiet control as sb-filter-bar's ghost
       "Clear all" -- secondary text, the raised step on hover, the accent
       only as the keyboard focus ring. It used to be an accent link, and
       the accent is for selected state. */
    .clear {
      min-height: var(--control-h);
      min-width: var(--control-h);
      padding: 0 var(--space-8);
      background: transparent;
      border: 0;
      border-radius: var(--control-radius);
      color: var(--text-secondary);
      font: inherit;
      font-size: var(--text-table);
      cursor: pointer;
      transition: background var(--transition), color var(--transition);
    }
    .clear:hover { color: var(--text); background: var(--surface-raised); }
    .clear:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
```

3. In `$WT/frontend/src/app/ui/toolbar.ts`:
   - After `.toolbar-sheet-button:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }` add:

```css
    /* v195 Phase 2: the sheet is open -- the button's one state, so its one accent. */
    .toolbar-sheet-button[aria-expanded='true'] { border-color: var(--accent); }
```

   - Replace the `.count { ... }` rule with:

```css
    /* v195 Phase 2: a count is not a state, so it takes no accent: an
       outlined badge in the secondary text. sb-column-picker's .count is
       this rule character for character (column-picker.spec.ts). */
    .count {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 1.5em;
      padding: 0 var(--space-4);
      border: 1px solid var(--border-strong);
      border-radius: var(--chip-radius);
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }
```

4. In `$WT/frontend/src/app/ui/column-picker.ts`, replace its `.count { ... }` rule (the one with `background: var(--accent-soft);`) with the same lines from `.count {` to `}` as the toolbar's above, at the same indentation (four spaces before `.count`, six before each declaration), without the comment. `column-picker.spec.ts`'s `shows visible/total as the same badge the Filters button uses` compares the two rule texts for equality.

- [ ] **Step 7: Run the tests to make sure they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/chip.spec.ts --include src/app/ui/segmented.spec.ts --include src/app/ui/form-controls.spec.ts --include src/app/ui/filter-bar.spec.ts --include src/app/ui/control-bar.spec.ts --include src/app/ui/toolbar.spec.ts --include src/app/ui/column-picker.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/button.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `hit-area.spec.ts` still finds `min-height: var(--control-h)` / `min-width: var(--hit-min)` on `.chip` and `.segment` and `min-width: var(--hit-min)` on `.box`; `column-picker.spec.ts` finds the two `.count` rules equal and the shared trigger declarations (`background: var(--surface-raised)` on `.toolbar-sheet-button` is unchanged); `spacing.spec.ts` finds every new `var()` defined; `button.spec.ts` still finds no `min-height: 0` in `chip.ts` or `control-bar.ts`.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. A workspace spec that pinned the old `.active { ... }` text of `sb-filter-chips` or the accent `.clear` would fail here: move it to `.chip.active` / the quiet Clear, never back.

- [ ] **Step 8: Check the look at three widths**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`, then click through to Trades (toolbar, selects, the Filters sheet and Columns), Analytics (the scope bar's segmented control) and the `/ui` gallery (chips of every tone, segmented, form controls, filter chips). At 1440: a hovered segment and filter chip take the raised step and no accent; the selected segment and selected filter chip carry the accent tint; the Filters and Columns badges are outlined and grey; opening Filters edges the button in the accent; fields read as a darker well inside a panel; quality chips show only coloured text on the grey hairline. At 768 and 390: the same, with every control still 44px tall (`getBoundingClientRect().height`), the Filters sheet in two columns at 390, and the filter chips scrolling sideways on one line. Save the PNGs under the session scratchpad.

- [ ] **Step 9: Close**

Close: standard (test: `frontend/src/app/ui/toolbar.spec.ts`), plus `chip.spec.ts`, `segmented.spec.ts`, `form-controls.spec.ts`, `filter-bar.spec.ts`, `control-bar.spec.ts` and `column-picker.spec.ts` (all under `frontend/src/app/ui/`) in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/ui/chip.ts frontend/src/app/ui/chip.spec.ts frontend/src/app/ui/segmented.ts frontend/src/app/ui/segmented.spec.ts frontend/src/app/ui/form-controls.ts frontend/src/app/ui/form-controls.spec.ts frontend/src/app/ui/filter-bar.ts frontend/src/app/ui/filter-bar.spec.ts frontend/src/app/ui/control-bar.ts frontend/src/app/ui/control-bar.spec.ts frontend/src/app/ui/toolbar.ts frontend/src/app/ui/toolbar.spec.ts frontend/src/app/ui/column-picker.ts
git -C "$WT" commit -m "feat(v195): flat controls, accent only on focus and selected state (V195-10)" -m "Phase 2: quality chips lose their color-mix borders; hover on a segment, filter chip and the control bar's Clear is the raised surface; a selected filter chip takes the selected segment's accent tint; the Filters/Columns count badge is outlined grey, and the Filters button edges in the accent only while its sheet is open; fields sit on the --bg well under the flat panel. A source-scan gate in toolbar.spec.ts holds the six control primitives to no shadow, gradient, colour mix or transform, 4px radii and accent only on focus/selected/engaged state." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-11: One KPI-strip look: stat strip, stat tile and metric card as hairline-split cells in one bordered surface
**Model:** sonnet — two cell rules unified, one fill removed and one global frame added, with the v186 strip contract's pins moved; the care is in keeping the hairline mechanism and the thin-sample cues intact.

**Files:**
- Modify: `frontend/src/styles.css` (two rules appended after the strip grid, at the end of the file)
- Modify: `frontend/src/app/ui/stat-strip.ts` (class doc comment; `:host` loses `--tile-tint-off: none;`)
- Modify: `frontend/src/app/ui/stat-strip.spec.ts` (the host-declaration case; the metric-card tint case; one new describe)
- Modify: `frontend/src/app/ui/stat-tile.ts` (`.tile` rule: `gap`, `padding`, comment)
- Modify: `frontend/src/app/ui/stat-tile.spec.ts` (one new case)
- Modify: `frontend/src/app/ui/metric-card.ts` (class doc comment; `.card` rule: `gap`, `padding`; `.busy`; the two `:host(.tint-…) .card` rules and their comment deleted)
- Modify: `frontend/src/app/ui/metric-card.spec.ts` (one case renamed; one case replaced; one new case)

**Interfaces:**
- Consumes: `StatStrip`, `StatTile`, `MetricCard`, `MIN_SAMPLE_N`, `PERFORMANCE_CAVEAT` (unchanged API; v194 shapes); the v186 strip contract (`--figure-rule`, `--tile-bg`, `--tile-border`, `--tile-radius`, the `.sb-strip-grid` classes); tier-3 `--panel-bg` (`var(--surface)`), `--panel-border`, `--panel-radius` (6px) from V195-3; `--panel-pad` from V195-6; `--space-4`, `--space-10`.
- Produces (V195-25, V195-27, V195-31 and V195-32 put strips in `sb-page`'s `[page-kpis]` slot and rely on this):
  - A `sb-stat-strip` outside any `.sb-panel` is its own bordered surface: `background: var(--panel-bg); border: var(--panel-border); border-radius: var(--panel-radius);` (global rule in `styles.css`). Inside a `.sb-panel` that frame is dropped (`background: none; border: 0; border-radius: 0;`), so a strip in a panel is never box-in-box.
  - One KPI cell: `sb-stat-tile .tile` and `sb-metric-card .card` both `display: flex; flex-direction: column; gap: var(--space-4); height: 100%; box-sizing: border-box; padding: var(--space-10) var(--panel-pad);`.
  - `sb-metric-card` keeps `tint-pos`/`tint-neg` on its host and `pos`/`neg` on its value (`trading-performance.spec.ts` reads the host classes) but paints no fill for them, in or out of a strip; `--tile-tint-off` is gone.

**What changes, and what is already there.** v186 D3 already made a strip a row of hairline-split cells: the strip sets inherited properties, each tile draws its start-edge rule, and the strip clips the first row's and column's. What Phase 2 adds is the "one bordered surface" around them and one cell look. Today a strip is always unframed because it always sat inside a panel; from V195-21 it also stands alone in `sb-page`'s `[page-kpis]` slot, where an unframed row of figures would float on the page ground. The frame is a global rule on the `sb-stat-strip` element (not the strip's own scoped CSS, which stays free of rules and surfaces, as the v186 contract and its spec require) with a `.sb-panel sb-stat-strip` exception, because a panel is already that surface. The strip's host keeps `overflow: hidden`, so with the 1px frame the grid's −1px pull still clips the first row's and first column's rules inside it. The stat tile (`gap: 2px`, `padding: 14px`) and the metric card (`gap: 6px`, `padding: 14px 20px`) become one cell: a 4px stack padded 10px vertically and `--panel-pad` horizontally, so a KPI cell lines up with the panel text beside it in both densities. The metric card's pos/neg fill outside a strip (a solid-colour `linear-gradient` over the surface) goes: a tinted block is the box-in-box v186 removed inside strips, and the value's colour and its sign (true minus since V195-7) carry the valence. The value sizes, the label (`.sb-label`), the `about`/`description` hints, `N=` and both thin-sample cues are untouched.

- [ ] **Step 1: Write the failing strip tests**

In `$WT/frontend/src/app/ui/stat-strip.spec.ts`:

1. In `sets the inherited properties every tile reads, and clips its own box`, delete `'--tile-tint-off: none;',` from the declaration list, and add after the list's `for` loop:

```ts
    // v195 Phase 2: no metric card is filled any more, so there is no fill to switch off.
    expect(host).not.toContain('--tile-tint-off');
```

2. Replace the case `drops a metric card tint inside a strip and keeps it outside` with:

```ts
  it('keeps the judgement on a metric card in and out of a strip, and fills neither (v195 Phase 2)', () => {
    const f = TestBed.createComponent(CardStripHost);
    f.detectChanges();
    const [inside, outside] = [...(f.nativeElement as HTMLElement).querySelectorAll('sb-metric-card')];
    expect(inside.closest('sb-stat-strip')).not.toBeNull();
    expect(outside.closest('sb-stat-strip')).toBeNull();
    for (const card of [inside, outside]) {
      expect(card.classList).toContain('tint-pos');
      expect(card.querySelector('.value')!.classList).toContain('pos');
    }
    expect(STRIP).not.toContain('--tile-tint-off');
    expect(CARD).not.toContain('--tile-tint-off');
  });
```

3. Append at the end of the file:

```ts
/* v195 Phase 2: one KPI-strip look -- hairline-split cells inside one
 * bordered surface. Inside a panel the panel is that surface; standing
 * alone (sb-page's [page-kpis] slot) the strip frames itself. The frame is
 * a global rule, so the strip's own scoped CSS still draws nothing. */
describe('one KPI-strip look (v195 Phase 2)', () => {
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const globalRule = (selector: string) =>
    GLOBAL.match(new RegExp(`(?:^|\\n)${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';
  const cellRule = (source: string, selector: string) =>
    source.match(new RegExp(`(?:^|\\n)\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';
  const CELL = [
    'display: flex;',
    'flex-direction: column;',
    'gap: var(--space-4);',
    'height: 100%;',
    'box-sizing: border-box;',
    'padding: var(--space-10) var(--panel-pad);',
  ];

  it('frames a strip that stands alone as one bordered panel surface', () => {
    const frame = globalRule('sb-stat-strip');
    expect(frame).toContain('background: var(--panel-bg);');
    expect(frame).toContain('border: var(--panel-border);');
    expect(frame).toContain('border-radius: var(--panel-radius);');
    expect(frame).not.toContain('box-shadow');
  });

  it('drops the frame inside a panel, which is already the bordered surface', () => {
    const inPanel = globalRule('.sb-panel sb-stat-strip');
    expect(inPanel).toContain('background: none;');
    expect(inPanel).toContain('border: 0;');
    expect(inPanel).toContain('border-radius: 0;');
    expect(GLOBAL.search(/\n\.sb-panel sb-stat-strip\s*\{/)).toBeGreaterThan(GLOBAL.search(/\nsb-stat-strip\s*\{/));
  });

  it('lays a stat tile and a metric card out as the same cell', () => {
    const tile = cellRule(TILE, '.tile');
    const card = cellRule(CARD, '.card');
    for (const declaration of CELL) {
      expect(tile, `stat-tile ${declaration}`).toContain(declaration);
      expect(card, `metric-card ${declaration}`).toContain(declaration);
    }
  });

  it('fills no metric card: the value colour and its sign carry the valence', () => {
    expect(CARD).not.toMatch(/:host\(\.tint-(pos|neg)\) \.card/);
    expect(CARD).not.toContain('linear-gradient');
  });
});
```

- [ ] **Step 2: Write the failing tile and card tests**

1. In `$WT/frontend/src/app/ui/stat-tile.spec.ts`, inside `describe('StatTile: one variant everywhere (v179 §3.3)', ...)`, after `stacks its parts left-aligned and has no inline or centred variant`, add:

```ts
  it('pads and spaces like every KPI cell, following row density (v195 Phase 2)', () => {
    const tile = rule('.tile');
    expect(tile).toContain('gap: var(--space-4);');
    expect(tile).toContain('padding: var(--space-10) var(--panel-pad);');
    expect(tile).not.toContain('var(--space-14)');
  });
```

2. In `$WT/frontend/src/app/ui/metric-card.spec.ts`:
   - In `describe('sb-metric-card tint (v181 §5)', ...)`, rename `tints the card and colours the figure for a good or bad figure` to `marks a good or bad figure on its host and colours the figure` (body unchanged).
   - In `describe('sb-metric-card in and out of a strip (v186 D3)', ...)`, replace the case `drops its tint where a strip switches it off, keeps it everywhere else` with:

```ts
  it('keeps the judgement on the host and the value, and never fills the card (v195 Phase 2)', () => {
    expect(SOURCE).not.toMatch(/:host\(\.tint-(pos|neg)\) \.card/);
    expect(SOURCE).not.toContain('--tile-tint-off');
    expect(SOURCE).not.toContain('linear-gradient');
    const good = render({ value: 1.2, tint: 'pos' });
    expect(good.classList).toContain('tint-pos');
    expect(good.querySelector('.value')!.classList).toContain('pos');
    const bad = render({ value: -0.4, tint: 'neg' });
    expect(bad.classList).toContain('tint-neg');
    expect(bad.querySelector('.value')!.classList).toContain('neg');
  });

  it('pads and spaces like a stat tile, following row density (v195 Phase 2)', () => {
    const card = rule('.card');
    expect(card).toContain('gap: var(--space-4);');
    expect(card).toContain('padding: var(--space-10) var(--panel-pad);');
    expect(card).not.toContain('var(--space-20)');
    expect(rule('.busy')).toContain('right: var(--panel-pad);');
  });
```

- [ ] **Step 3: Run them to make sure they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/stat-strip.spec.ts --include src/app/ui/stat-tile.spec.ts --include src/app/ui/metric-card.spec.ts
```

Expected: FAIL. `stat-strip.spec.ts`: the host case (`--tile-tint-off` still on the host), the metric-card case (`--tile-tint-off` in both sources), and all four `one KPI-strip look` cases. `stat-tile.spec.ts`: the new padding case. `metric-card.spec.ts`: the fill case and the padding case (the renamed case passes).

- [ ] **Step 4: One cell look in the tile and the card**

1. In `$WT/frontend/src/app/ui/stat-tile.ts`, in the `.tile { ... }` rule, change `gap: 2px;` to `gap: var(--space-4);` and `padding: var(--space-14);` to `padding: var(--space-10) var(--panel-pad);`, and add directly above the `.tile` rule:

```css
    /* v195 Phase 2 -- one KPI cell, the same box as sb-metric-card's .card:
       a 4px stack, 10px top and bottom, --panel-pad at the sides so the
       cell lines up with the panel text beside it in either row density. */
```

2. In `$WT/frontend/src/app/ui/metric-card.ts`:
   - In the `.card { ... }` rule, change `gap: var(--space-6);` to `gap: var(--space-4);` and `padding: var(--space-14) var(--space-20);` to `padding: var(--space-10) var(--panel-pad);`.
   - Change `.busy { position: absolute; top: var(--space-10); right: var(--space-14); }` to `.busy { position: absolute; top: var(--space-10); right: var(--panel-pad); }`.
   - Delete the comment that starts `/* v186 D3 -- inside an sb-stat-strip the strip sets --tile-tint-off: none` and the two rules after it:

```css
    :host(.tint-pos) .card { background: var(--tile-tint-off, linear-gradient(var(--pos-soft), var(--pos-soft)), var(--surface)); }
    :host(.tint-neg) .card { background: var(--tile-tint-off, linear-gradient(var(--neg-soft), var(--neg-soft)), var(--surface)); }
```

   - In the class doc comment (`Deprecated (v80 D4): use sb-figure inside an sb-figure-strip.` …), append before its closing `*/`:

```ts
 *
 * v195 Phase 2: the same KPI cell as sb-stat-tile (one gap, one padding),
 * and no fill. A good or bad figure is still marked on the host
 * (tint-pos / tint-neg) and coloured on the value; the colour and the sign
 * carry the valence, never a tinted block.
```

- [ ] **Step 5: The strip's frame**

1. In `$WT/frontend/src/app/ui/stat-strip.ts`:
   - Delete the `:host` declaration `--tile-tint-off: none;`.
   - In the class doc comment, delete the bullet

```
 * - `--tile-tint-off: none`: sb-metric-card drops its pos/neg fill; the
 *   value's colour and sign carry the valence.
```

   and add, as a new paragraph before `Columns: the global .sb-strip-grid ...`:

```
 * v195 Phase 2: one KPI-strip look. Standing alone (sb-page's
 * [page-kpis] slot) the strip is its own bordered surface, the panel's
 * tokens; inside a .sb-panel the panel is that surface and the frame
 * drops. Both rules are global (styles.css, after the strip grid), so this
 * component's own styles still paint no rule or surface.
```

2. Append to the end of `$WT/frontend/src/styles.css` (after the `@media (min-width: 1024px)` strip-grid rule):

```css

/* v195 Phase 2 -- one KPI-strip look: hairline-split cells (sb-stat-strip
 * and its tiles, above) inside one bordered surface. A strip standing alone
 * on the page, as in sb-page's [page-kpis] slot, is that surface, in the
 * panel's own tokens; inside a panel the panel already is, so the frame
 * drops and a strip is never box-in-box. The strip's host keeps
 * overflow: hidden, so its grid's -1px pull still clips the first row's
 * and first column's rules inside the frame. Element selectors, global,
 * because the strip's scoped styles draw nothing (stat-strip.spec.ts). */
sb-stat-strip {
  background: var(--panel-bg);
  border: var(--panel-border);
  border-radius: var(--panel-radius);
}

.sb-panel sb-stat-strip {
  background: none;
  border: 0;
  border-radius: 0;
}
```

- [ ] **Step 6: Run the tests to make sure they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/stat-strip.spec.ts --include src/app/ui/stat-tile.spec.ts --include src/app/ui/metric-card.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `stat-strip.spec.ts`'s `renders nothing for an empty strip and draws no rule, surface or shadow of its own` still passes (the frame is in `styles.css`, not the strip's `styles`), and `comes after the elevation rules and casts nothing` finds no `box-shadow` after `.sb-strip-grid`; `primitives.spec.ts` G3 still finds exactly the two casts in `styles.css` and only radius tokens or `0`; `spacing.spec.ts` finds `--panel-pad` and `--panel-border` defined; `trading-performance.spec.ts` still reads `tint-pos`/`tint-neg` from the card hosts.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. A workspace spec that asserted a metric card's tinted background, or a tile's 14px padding, is a missed pin: move it to the host class or the shared cell, never back.

- [ ] **Step 7: Check the look at three widths**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard` (trading performance metric cards), then click through to Risk (stat strip in a panel) and Analytics Overview (KPI tiles), and the `/ui` gallery. At 1440: a strip inside a panel shows one frame (the panel's) with hairlines between cells and none around them; a metric card for a good or bad figure has no tinted fill, only its coloured, signed value; tiles and cards share one inner padding (inspect `getComputedStyle(.tile).paddingLeft` = `14px`, then `localStorage.setItem('ui.density', 'comfortable')`, reload through `/app/dashboard`, click back: `20px`). At 768 and 390: the 2-column strip keeps one hairline between columns and between rows, no doubled rule at the clipped edges, and the `N=` / thin-sample line still wraps inside its cell. Save the PNGs under the session scratchpad. (No page has a standalone strip yet; V195-21's gallery entry and the Phase 5 `[page-kpis]` slots show the frame.)

- [ ] **Step 8: Close**

Close: standard (test: `frontend/src/app/ui/stat-strip.spec.ts`), plus `frontend/src/app/ui/stat-tile.spec.ts` and `frontend/src/app/ui/metric-card.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/styles.css frontend/src/app/ui/stat-strip.ts frontend/src/app/ui/stat-strip.spec.ts frontend/src/app/ui/stat-tile.ts frontend/src/app/ui/stat-tile.spec.ts frontend/src/app/ui/metric-card.ts frontend/src/app/ui/metric-card.spec.ts
git -C "$WT" commit -m "feat(v195): one KPI-strip look, framed when it stands alone (V195-11)" -m "Phase 2: sb-stat-tile and sb-metric-card become one KPI cell (4px stack, 10px by --panel-pad padding, so the cell follows row density). A stat strip standing alone is its own bordered surface in the panel tokens, through a global rule that drops inside a .sb-panel, so a strip is never box-in-box. sb-metric-card no longer fills its card for a good or bad figure: the host still carries tint-pos/tint-neg and the value its colour and sign; --tile-tint-off is gone." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-12: Empty, loading and error states in the panel body, one style each; dialogs, drawer and toasts on the overlay surface with the one shadow token
**Model:** sonnet — style unification across seven primitives with one template change in `sb-async`; the care is in keeping every class the workspace specs query (`.failed`, `.retry`, `.stale-badge`) while the two error looks and two empty looks become one.

**Files:**
- Modify: `frontend/src/app/ui/empty-state.ts` (template: the reason span; styles)
- Modify: `frontend/src/app/ui/empty-state.spec.ts` (the dashed-box case replaced; one new case)
- Modify: `frontend/src/app/ui/panel-error.ts` (whole file rewritten below)
- Modify: `frontend/src/app/ui/panel-error.spec.ts` (one new case)
- Modify: `frontend/src/app/ui/async.ts` (template: the empty branch; styles: `.failed`, `.failed-text`, `.retry`, the skeleton bar, `.skeleton-tile`, the `.empty-wrap`/`.reason` rules deleted; class doc)
- Modify: `frontend/src/app/ui/async.spec.ts` (the measured-zero case; one new describe)
- Modify: `frontend/src/app/ui/spinner.ts` (the `.ring` rule; doc comment)
- Modify: `frontend/src/app/ui/confirm-dialog.ts` (the `h2` rule)
- Modify: `frontend/src/app/ui/layout.ts` (`Drawer` styles only: `header` and `.body` padding, `h2`)
- Modify: `frontend/src/app/shell/toast-host.ts` (the `.toast` rule; one new rule)
- Modify: `frontend/src/app/shell/toast-host.spec.ts` (one new case)
- Modify: `frontend/src/app/ui/elevation.spec.ts` (one new describe)
- Modify (not in the ledger row, see Interfaces): `frontend/src/app/ui/spinner.spec.ts` (one new describe), `frontend/src/app/ui/data-table/data-table.ts` (the `.loading-spinner` rule's `border-top-color` and its comment), `frontend/src/app/ui/chart-container.ts` (the `.spinner` rule's `border-top-color`)

**Interfaces:**
- Consumes: `EmptyStateComponent` (`title`, `hint`, `reason`), `PanelError` (`message`, `retry`), `Async` (every input and output unchanged), `Spinner`, `ConfirmDialog` (V195-8's `dangerVariant`; v194's `requestClose`), `Drawer`, `ToastHost`, `.elev-overlay` (styles.css: `--surface-overlay`, `--border-strong`, `--panel-radius`, `--shadow-overlay`), `--scrim`, `--panel-pad` (V195-6), `--neg`, `--neg-soft`, `--warn`, `--surface-raised`, `--text-secondary`; `stripComments` (`ui/testing/all-sources.ts`, already imported in `elevation.spec.ts`).
- Produces (every Phase 5 page renders these states inside its panels):
  - One empty style: `sb-empty-state`, flat in the panel body (no box of its own), padded `var(--space-20) var(--panel-pad)`; its reason label is muted for a measured zero and `--warn` for missing data (`.reason.awaiting`). `sb-async`'s empty branch renders `<sb-empty-state [title] [hint] [reason]="emptyReason()">` and draws no reason chip of its own; the visible reason text is now `Result: 0` / `Awaiting data` (the `.sb-label` caps it on screen).
  - One error style: `sb-panel-error .error` and `sb-async .failed` carry the same declarations (a 2px `--neg` stripe on `--neg-soft`, body text, wrap); `sb-panel-error`'s Retry gains `class="retry"` and shares `sb-async .retry`'s declarations (a quiet bordered control, raised on hover, accent focus ring).
  - One loading ring: `sb-spinner .ring`, `sb-data-table .loading-spinner` and `sb-chart-container .spinner` draw `border: 2px solid var(--border-strong); border-top-color: var(--text-secondary);` (status is not interactive, so not the accent). The skeleton bar paints `var(--border-strong)` (no `color-mix()`), and a tiles skeleton pads like V195-11's KPI cell.
  - Overlays: confirm dialog, drawer and toast keep `.elev-overlay` as their only surface and shadow; dialog and drawer titles are `font-family: var(--font-sans); font-size: var(--text-subhead); font-weight: 600; letter-spacing: normal;`; the drawer pads with `--panel-pad`; a toast has an accent focus ring and wraps inside the viewport.
- Ledger gap: `spinner.spec.ts` is where a ring is pinned, and the "one loading style" rule cannot hold while `data-table.ts` and `chart-container.ts` keep their accent copies of the ring, so their one-line colour change lands here. `data-table.ts` is next edited by V195-13 and `chart-container.ts` by no later task; both run after this task in id order, so there is no parallel conflict. `shell.css`'s `.route-loading-mark` is a fourth copy, left to the shell rewrite (V195-16..V195-18) because those tasks own `shell.css`.

**What changes, and what is already there.** Two empty looks exist today: `sb-empty-state` (a dashed box with a muted caps reason) and `sb-async`'s own coloured reason chip stacked above an `sb-empty-state` that is never told the reason. Two error looks exist: `sb-panel-error` (a dashed `--neg` box on the neg tint, Retry on the right) and `sb-async`'s centred red sentence over a raised Retry. Phase 2 wants one style each, inside the panel body. The empty state becomes flat (the panel is the frame; a dashed box inside a hairline panel is box-in-box) and `sb-async` hands it the reason instead of drawing its own chip; the caution colour for missing data moves onto `sb-empty-state`'s reason label, so the words still lead and the colour repeats them. The error becomes one look in both places: a 2px `--neg` stripe on the neg tint (the same valence-stripe idiom the toasts use), the message in body text, a quiet bordered Retry. Workspace specs query `sb-async`'s `.failed` and `.retry` (risk, calendar, dashboard, watchlist, versions, …), so its error markup and classes stay and only the styles move; `sb-panel-error`'s Retry gains the same `retry` class so one declaration list describes both. Loading keeps the shaped skeleton and the small ring; the ring stops using the accent (status, not interaction) in all three places it is drawn, and the skeleton bar stops mixing colours. The overlays already share `.elev-overlay` and the one `--shadow-overlay`; this task pins that none paints a surface or shadow of its own, sets the dialog and drawer titles in the UI face, pads the drawer with the density token, and gives a toast a focus ring and a viewport-safe width.

- [ ] **Step 1: Write the failing empty-state, panel-error and async tests**

1. In `$WT/frontend/src/app/ui/empty-state.spec.ts`, replace the case

```ts
  it('draws dashed hairline box', () => expect(SOURCE).toMatch(/\.empty \{[^}]*border: 1px dashed var\(--border-strong\)/));
```

with

```ts
  /* v195 Phase 2: the one empty style sits flat in the panel body; the panel is the frame. */
  it('sits flat in the panel body: no box, border or fill of its own', () => { const empty = SOURCE.match(/\.empty \{[^}]*\}/)![0]; expect(empty).not.toMatch(/border|background/); expect(empty).toContain('padding: var(--space-20) var(--panel-pad)'); });
  it('repeats missing data in the caution colour and leaves a measured zero muted', () => { expect(render('No trades', undefined, 'no-data-yet').querySelector('.reason')!.classList).toContain('awaiting'); expect(render('No trades', undefined, 'measured-zero').querySelector('.reason')!.classList).not.toContain('awaiting'); expect(SOURCE).toMatch(/\.reason\.awaiting \{ color: var\(--warn\); \}/); });
```

2. In `$WT/frontend/src/app/ui/panel-error.spec.ts`, inside `describe('PanelError', ...)`, after the existing case add:

```ts
  it('names its Retry like sb-async does, so one rule styles both (v195 Phase 2)', () => {
    const fixture = TestBed.createComponent(PanelError); fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('button')!.classList).toContain('retry');
  });
```

3. In `$WT/frontend/src/app/ui/async.spec.ts`:
   - In `distinguishes a measured zero from missing data`, change `.toContain('awaiting data');` to `.toContain('Awaiting data');` and `.toContain('result: 0');` to `.toContain('Result: 0');` (the reason now comes from `sb-empty-state`, whose `.sb-label` capitalises it on screen).
   - Append at the end of the file:

```ts
/* v195 Phase 2: empty, loading and error each have one style, rendered in
 * the panel body. sb-async keeps the classes the workspace specs query
 * (.failed, .retry) and draws them exactly as sb-panel-error does; its
 * empty branch is sb-empty-state, reason included. */
describe('one empty, loading and error style (v195 Phase 2)', () => {
  const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
  const ASYNC = read('src/app/ui/async.ts');
  const ASYNC_STYLES = ASYNC.slice(ASYNC.indexOf('styles:')).replace(/\/\*[\s\S]*?\*\//g, '');
  const PANEL_ERROR = read('src/app/ui/panel-error.ts');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const ruleIn = (source: string, selector: string) =>
    source.match(new RegExp(`\\n\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';
  const declarations = (rule: string) =>
    rule.slice(rule.indexOf('{') + 1, rule.lastIndexOf('}')).split(';').map((d) => d.trim()).filter(Boolean).sort();

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it("draws sb-async's error and Retry exactly like sb-panel-error's", () => {
    const error = ruleIn(PANEL_ERROR, '.error');
    expect(error).toContain('border-left: 2px solid var(--neg);');
    expect(error).toContain('background: var(--neg-soft);');
    expect(error).not.toContain('dashed');
    expect(declarations(ruleIn(ASYNC, '.failed'))).toEqual(declarations(error));
    expect(declarations(ruleIn(ASYNC, '.retry'))).toEqual(declarations(ruleIn(PANEL_ERROR, '.retry')));
    expect(declarations(ruleIn(ASYNC, '.retry:hover'))).toEqual(declarations(ruleIn(PANEL_ERROR, '.retry:hover')));
  });

  it('renders its empty state through sb-empty-state, reason included, and styles no second one', () => {
    const { el } = render({ empty: true, reason: 'measured-zero' });
    const reasons = [...el.querySelectorAll('.reason')];
    expect(reasons).toHaveLength(1);
    expect(reasons[0].closest('sb-empty-state')).not.toBeNull();
    expect(reasons[0].textContent!.trim()).toBe('Result: 0');
    expect(ASYNC_STYLES).not.toMatch(/\.empty-wrap|\.reason\b/);
  });

  it('paints skeleton bars in the strong rule colour and mixes none', () => {
    const bar = ASYNC.match(/\.skeleton-cell::before,\s*\.skeleton-bar\s*\{[^}]*\}/)![0];
    expect(bar).toContain('background: var(--border-strong);');
    expect(ASYNC).not.toContain('color-mix(');
  });

  it('pads a tiles skeleton like the KPI cell it stands in for (V195-11)', () => {
    expect(ruleIn(ASYNC, '.skeleton-tile')).toContain('padding: var(--space-10) var(--panel-pad);');
  });
});
```

- [ ] **Step 2: Write the failing ring, overlay and toast tests**

1. Append to `$WT/frontend/src/app/ui/spinner.spec.ts`:

```ts
/* v195 Phase 2: one loading ring wherever a ring is drawn, and it is status,
 * not interaction, so it turns in the secondary grey, never the accent. */
describe('one loading ring, off the accent (v195 Phase 2)', () => {
  const RINGS: [string, string][] = [
    ['src/app/ui/spinner.ts', '.ring'],
    ['src/app/ui/data-table/data-table.ts', '.loading-spinner'],
    ['src/app/ui/chart-container.ts', '.spinner'],
  ];

  it.each(RINGS)('%s draws %s as the one grey ring', (path, selector) => {
    const source = readFileSync(join(process.cwd(), path), 'utf8');
    const ring = source.match(new RegExp(`\\n\\s*${selector.replace('.', '\\.')}\\s*\\{[^}]*\\}`))![0];
    expect(ring).toContain('border: 2px solid var(--border-strong);');
    expect(ring).toContain('border-top-color: var(--text-secondary);');
    expect(ring).toContain('border-radius: 50%;');
    expect(ring).toContain('animation: sb-spin 700ms linear infinite;');
    expect(ring).not.toContain('accent');
  });
});
```

2. In `$WT/frontend/src/app/shell/toast-host.spec.ts`, inside `describe('ToastHost', ...)`, after `renders each toast as an overlay button carrying its kind`, add:

```ts
  /* v195 Phase 2: a toast is the overlay surface alone; it wraps inside a
   * phone's width and shows a focus ring, being a real button. */
  it('wraps inside the viewport and rings in the accent on keyboard focus', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/toast-host.ts'), 'utf8');
    const toast = source.match(/\n\s*\.toast \{[^}]*\}/)![0];
    expect(toast).toContain('max-width: min(360px, calc(100vw - 2 * var(--space-20)));');
    expect(toast).not.toMatch(/background|box-shadow/);
    expect(source).toMatch(/\.toast:focus-visible \{ outline: 1px solid var\(--accent\); outline-offset: 2px; \}/);
  });
```

3. Append to the end of `$WT/frontend/src/app/ui/elevation.spec.ts`:

```ts
/* v195 Phase 2: dialogs, the drawer and toasts sit on the one overlay
 * surface (.elev-overlay: --surface-overlay, the strong hairline, the
 * panel radius) and cast the one --shadow-overlay through it; none paints
 * a surface or shadow of its own, and a modal dims with the --scrim token. */
describe('v195 Phase 2: one overlay surface', () => {
  const src = (path: string) => stripComments(readFileSync(join(process.cwd(), path), 'utf8'));
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const ruleOf = (source: string, selector: string) =>
    source.match(new RegExp(`\\n\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';
  const DIALOG = src('src/app/ui/confirm-dialog.ts');
  const LAYOUT = src('src/app/ui/layout.ts');
  const DRAWER = LAYOUT.slice(LAYOUT.indexOf("selector: 'sb-drawer'"), LAYOUT.indexOf('export class Drawer'));
  const TOAST = src('src/app/shell/toast-host.ts');

  it('puts the confirm dialog, the drawer and every toast on .elev-overlay', () => {
    expect(DIALOG).toContain('<dialog #dialog class="elev-overlay"');
    expect(DRAWER).toContain('<dialog #dialog class="drawer elev-overlay"');
    expect(TOAST).toContain('<button class="toast elev-overlay"');
  });

  it('paints no surface and casts no shadow of their own', () => {
    const own: [string, string][] = [
      ['dialog', ruleOf(DIALOG, 'dialog')],
      ['.drawer', ruleOf(DRAWER, '.drawer')],
      ['.drawer.elev-overlay', ruleOf(DRAWER, '.drawer.elev-overlay')],
      ['.toast', ruleOf(TOAST, '.toast')],
    ];
    for (const [name, rule] of own) {
      expect(rule, name).not.toBe('');
      expect(rule, name).not.toMatch(/background|box-shadow/);
    }
    for (const source of [DIALOG, DRAWER, TOAST]) expect(source).not.toMatch(/box-shadow\s*:/);
  });

  it('dims behind a modal with the scrim token', () => {
    expect(ruleOf(DIALOG, 'dialog::backdrop')).toContain('background: var(--scrim)');
    expect(ruleOf(DRAWER, '.drawer::backdrop')).toContain('background: var(--scrim)');
  });

  it('titles a dialog and a drawer alike, sentence case in the UI face', () => {
    for (const [name, source] of [['confirm-dialog', DIALOG], ['drawer', DRAWER]] as const) {
      const h2 = ruleOf(source, 'h2');
      for (const declaration of [
        'font-family: var(--font-sans);',
        'font-size: var(--text-subhead);',
        'font-weight: 600;',
        'letter-spacing: normal;',
      ]) expect(h2, `${name} ${declaration}`).toContain(declaration);
      expect(h2, name).not.toContain('text-transform');
    }
  });

  it('pads the drawer like a panel, following row density', () => {
    expect(ruleOf(DRAWER, 'header')).toContain('padding: var(--space-10) var(--panel-pad);');
    expect(ruleOf(DRAWER, '.body')).toContain('padding: var(--panel-pad);');
  });
});
```

- [ ] **Step 3: Run them to make sure they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/empty-state.spec.ts --include src/app/ui/panel-error.spec.ts --include src/app/ui/async.spec.ts --include src/app/ui/spinner.spec.ts --include src/app/shell/toast-host.spec.ts --include src/app/ui/elevation.spec.ts
```

Expected: FAIL. `empty-state.spec.ts`: both new cases. `panel-error.spec.ts`: the `retry` class case. `async.spec.ts`: the measured-zero case (lower-case text today) and all four `one empty, loading and error style` cases. `spinner.spec.ts`: all three rings (`var(--accent)`). `toast-host.spec.ts`: the new case. `elevation.spec.ts`: the title case and the drawer padding case (the `.elev-overlay`, no-own-surface and scrim cases already pass: they pin what is there).

- [ ] **Step 4: One empty style**

1. In `$WT/frontend/src/app/ui/empty-state.ts`:
   - Template: replace

```html
        <span class="reason sb-label">{{ why === 'measured-zero' ? 'Result: 0' : 'Awaiting data' }}</span>
```

   with

```html
        <span class="reason sb-label" [class.awaiting]="why === 'no-data-yet'">{{ why === 'measured-zero' ? 'Result: 0' : 'Awaiting data' }}</span>
```

   - Replace the `styles` block with:

```ts
  styles: `
    /* v195 Phase 2: the one empty style, inside the panel body. No box of
       its own -- the panel is the frame -- centred and quiet. */
    .empty { display: grid; justify-items: center; gap: var(--space-6); padding: var(--space-20) var(--panel-pad); text-align: center; }
    .empty-title { margin: 0; color: var(--text-secondary); font-size: var(--text-body); }
    .empty-hint { margin: 0; color: var(--text-muted); font-size: var(--text-table); }
    /* A measured zero is a neutral fact (the muted label); missing data is
       a caution. The words carry the difference, the colour repeats it. */
    .reason.awaiting { color: var(--warn); }
  `,
```

2. In `$WT/frontend/src/app/ui/async.ts`, replace the empty branch

```html
    } @else if (empty()) {
      <div class="empty-wrap">
        <span class="reason" [class]="emptyReason()">
          {{ emptyReason() === 'measured-zero' ? 'result: 0' : 'awaiting data' }}
        </span>
        <sb-empty-state [title]="emptyTitle()" [hint]="emptyHint()" />
      </div>
    } @else {
```

with

```html
    } @else if (empty()) {
      <!-- v195 Phase 2: the one empty style, reason included. -->
      <sb-empty-state [title]="emptyTitle()" [hint]="emptyHint()" [reason]="emptyReason()" />
    } @else {
```

and in `styles` delete the `.empty-wrap { text-align: center; }` rule, the `.reason { ... }` rule, the comment `/* A measured zero is a NEUTRAL fact; missing data is a CAUTION. ...` and the two rules `.reason.measured-zero { ... }` and `.reason.no-data-yet { ... }`.

- [ ] **Step 5: One error style**

1. Replace the whole of `$WT/frontend/src/app/ui/panel-error.ts` with:

```ts
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

/** A failed fetch is not an empty chart (v94 H4); this replaces only panel body.
 *
 * v195 Phase 2: the one error style, shared declaration for declaration with
 * sb-async's error branch (async.spec.ts): a 2px --neg stripe on the neg
 * tint, the message in body text, Retry as a quiet bordered control. No
 * dashed box -- the panel around it is the frame. */
@Component({
  selector: 'sb-panel-error', changeDetection: ChangeDetectionStrategy.OnPush, host: { role: 'alert' },
  template: `<div class="error"><span class="text">Could not load@if (message()) { <span class="why"> · {{ message() }}</span> }</span><button type="button" class="retry" (click)="retry.emit()">Retry</button></div>`,
  styles: `
    :host { display: block; }
    .error {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-8);
      min-height: 96px;
      padding: var(--space-14) var(--panel-pad);
      border-left: 2px solid var(--neg);
      border-radius: var(--radius-sm);
      background: var(--neg-soft);
      color: var(--text);
      font-size: var(--text-table);
    }
    .why { color: var(--text-secondary); }
    .retry {
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      background: transparent;
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      cursor: pointer;
      transition: background var(--transition);
    }
    .retry:hover { background: var(--surface-raised); }
    .retry:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
  `,
})
export class PanelError {
  readonly message = input<string | null>(null);
  readonly retry = output<void>();
}
```

2. In `$WT/frontend/src/app/ui/async.ts` `styles`, replace the three rules

```css
    .failed { padding: var(--space-14); text-align: center; }
    .failed-text { color: var(--neg); font-size: var(--text-table); }
    .retry {
      margin-top: var(--space-8);
      min-height: var(--control-h);
      padding: 0 var(--space-14);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      background: var(--surface-raised);
      color: var(--text);
      font-family: var(--font-sans);
      font-size: var(--text-table);
      cursor: pointer;
    }
```

with

```css
    /* v195 Phase 2: the one error style -- sb-panel-error's declarations,
       kept identical by async.spec.ts; the classes stay because workspace
       specs query .failed and .retry. */
    .failed {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-8);
      min-height: 96px;
      padding: var(--space-14) var(--panel-pad);
      border-left: 2px solid var(--neg);
      border-radius: var(--radius-sm);
      background: var(--neg-soft);
      color: var(--text);
      font-size: var(--text-table);
    }
    .failed-text { margin: 0; }
    .retry {
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      background: transparent;
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      cursor: pointer;
      transition: background var(--transition);
    }
    .retry:hover { background: var(--surface-raised); }
    .retry:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
```

- [ ] **Step 6: One loading style**

1. In `$WT/frontend/src/app/ui/async.ts` `styles`:
   - In the `.skeleton-cell::before, .skeleton-bar { ... }` rule, change `background: color-mix(in srgb, var(--surface-raised) 55%, var(--border-strong));` to `background: var(--border-strong);`.
   - In `.skeleton-tile { ... }`, change `padding: var(--space-14);` to `padding: var(--space-10) var(--panel-pad);`.
   - In the `Async` class doc comment, append before its closing `*/`:

```ts
 *
 * v195 Phase 2: one style per state, in the panel body. Empty is
 * sb-empty-state (reason included), error is sb-panel-error's look on the
 * .failed / .retry classes, loading is the skeleton (bars in the strong
 * rule colour) or, for a refetch, the one grey sb-spinner ring.
```

2. In `$WT/frontend/src/app/ui/spinner.ts`, in `.ring`, change `border-top-color: var(--accent);` to `border-top-color: var(--text-secondary);`, and append to the class doc comment before its closing `*/`:

```ts
 *
 * v195 Phase 2: the ring turns in the secondary grey, not the accent -- a
 * load is status, and the accent is kept for interactive state. The table's
 * and the chart frame's rings are the same rule (spinner.spec.ts).
```

3. In `$WT/frontend/src/app/ui/data-table/data-table.ts`, in `.loading-spinner { ... }`, change `border-top-color: var(--accent);` to `border-top-color: var(--text-secondary);`, and in the comment above it change `Same visual language as ChartContainer's spinner (border-top accent` / `colour, 700ms linear spin)` to `Same visual language as ChartContainer's spinner (grey border-top,` / `700ms linear spin)`.

4. In `$WT/frontend/src/app/ui/chart-container.ts`, in `.spinner { ... }`, change `border-top-color: var(--accent);` to `border-top-color: var(--text-secondary);`.

- [ ] **Step 7: The overlays**

1. In `$WT/frontend/src/app/ui/confirm-dialog.ts` `styles`, replace `h2 { font-size: var(--text-subhead); font-weight: 600; }` with

```css
    /* v195 Phase 2: sentence case as given, in the UI face -- the drawer's
       title is the same rule. */
    h2 { font-family: var(--font-sans); font-size: var(--text-subhead); font-weight: 600; letter-spacing: normal; }
```

2. In `$WT/frontend/src/app/ui/layout.ts`, `Drawer` styles only (re-read the file; edit inside the slice from `selector: 'sb-drawer'` to `export class Drawer`):
   - In `header { ... }`, change `padding: var(--space-14);` to `padding: var(--space-10) var(--panel-pad);`.
   - Replace `h2 { font-size: var(--text-subhead); font-weight: 600; }` with `h2 { font-family: var(--font-sans); font-size: var(--text-subhead); font-weight: 600; letter-spacing: normal; }`.
   - Change `.body { padding: var(--space-14); overflow-y: auto; }` to `.body { padding: var(--panel-pad); overflow-y: auto; }`.
   - Above `header {` add:

```css
    /* v195 Phase 2: the drawer pads like a panel (--panel-pad follows row
       density); its surface and shadow are .elev-overlay's alone. */
```

3. In `$WT/frontend/src/app/shell/toast-host.ts` `styles`:
   - In `.toast { ... }`, add `max-width: min(360px, calc(100vw - 2 * var(--space-20)));` after `padding: var(--space-8) var(--space-14);`.
   - After the `.toast { ... }` rule add:

```css
    /* v195 Phase 2: a toast is a real button, so it shows the focus ring. */
    .toast:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
```

- [ ] **Step 8: Run the tests to make sure they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/empty-state.spec.ts --include src/app/ui/panel-error.spec.ts --include src/app/ui/async.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/spinner.spec.ts --include src/app/shell/toast-host.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/layout.spec.ts --include src/app/ui/controls.spec.ts --include src/app/ui/chart-container.spec.ts --include src/app/ui/data-table/data-table.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/motion-css.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `layout.spec.ts`'s drawer cases still find the `.drawer` geometry and the baseline header; `controls.spec.ts` still drives the confirm dialog (V195-8's `dangerVariant` cases); `motion-css.spec.ts` still finds the `sb-skeleton-pulse` guards on `.skeleton-bar`; `primitives.spec.ts` finds only radius tokens and no new colour literal; `spacing.spec.ts` finds `--panel-pad` defined.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. A workspace spec that read the lower-case `awaiting data` / `result: 0` from an `sb-async` empty state, or `.empty-wrap`, is a missed pin: assert the `sb-empty-state` reason (`Awaiting data` / `Result: 0`), never restore the second chip.

- [ ] **Step 9: Check the look at three widths**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`, then click through to Trades (open a row's drawer; trigger a delete to see the confirm dialog, then Cancel), Calendar (an empty day panel) and the `/ui` gallery (async states, panel error, toast). To see the error branch, route one API call to a 500 with `page.route` before clicking into Watchlist. At 1440: an empty panel shows the centred title, hint and caps reason with no dashed box; an error shows the red stripe on the faint red tint with Retry on the right, the same in `sb-async` and `sb-panel-error`; a refetch ring is grey; the dialog and drawer sit on the overlay surface with the one shadow, titles 16px in the UI face; a toast is focusable with a visible ring. At 768: the drawer is 85vw and pads 14px. At 390: the drawer is the bottom sheet, the error's Retry wraps under the message without overflow, and a long toast wraps inside the screen. Save the PNGs under the session scratchpad.

- [ ] **Step 10: Close**

Close: standard (test: `frontend/src/app/ui/async.spec.ts`), plus `frontend/src/app/ui/empty-state.spec.ts`, `frontend/src/app/ui/panel-error.spec.ts`, `frontend/src/app/ui/spinner.spec.ts`, `frontend/src/app/shell/toast-host.spec.ts` and `frontend/src/app/ui/elevation.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/ui/empty-state.ts frontend/src/app/ui/empty-state.spec.ts frontend/src/app/ui/panel-error.ts frontend/src/app/ui/panel-error.spec.ts frontend/src/app/ui/async.ts frontend/src/app/ui/async.spec.ts frontend/src/app/ui/spinner.ts frontend/src/app/ui/spinner.spec.ts frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/chart-container.ts frontend/src/app/ui/confirm-dialog.ts frontend/src/app/ui/layout.ts frontend/src/app/shell/toast-host.ts frontend/src/app/shell/toast-host.spec.ts frontend/src/app/ui/elevation.spec.ts
git -C "$WT" commit -m "feat(v195): one empty, loading and error style; overlays on the one surface (V195-12)" -m "Phase 2: sb-empty-state sits flat in the panel body and colours a missing-data reason as a caution; sb-async renders it with the reason instead of its own chip. sb-panel-error and sb-async's error branch share one look (neg stripe on the neg tint, quiet bordered Retry), pinned declaration for declaration. The loading ring turns grey in sb-spinner, the data table and the chart frame, and the skeleton bar no longer mixes colours. The confirm dialog, drawer and toasts paint no surface or shadow of their own beyond .elev-overlay; dialog and drawer titles share the UI face, the drawer pads with --panel-pad, and a toast gains a focus ring and a viewport-safe width." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```
