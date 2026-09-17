# v95 — Part 4: Workspaces B (risk, system, versions, gallery)

Part of `2026-09-17-v95-responsive-content-priority`. Header block, goal,
global constraints, parallelisation map and exit criteria live in
`_0-index.md` — read that first.

# Phase D — Workspace adoption, the remaining four

**Group D-i (parallel):** D1+D2 (risk, incl. `ui/matrix.ts`), D3+D4 (system),
D5 (versions), D6 (gallery). One workspace directory each; `matrix.ts` is
rendered only by Risk, so D2 belongs to that group and to no other.

**Every task carries a mandatory visual pass at 390 / 768 / 1024.**

---

### Task D1: Risk — grids that survive a 320px phone

**Files:**
- Modify: `frontend/src/app/workspaces/risk/risk.ts:534,567`
- Test: `frontend/src/app/workspaces/risk/risk.spec.ts`

`risk.ts:534` uses `minmax(300px, 1fr)`. A grid track with a 300px floor
overflows any content box narrower than 300px, which a 320px phone produces
once padding is subtracted. `analytics.ts:1264` already has the right idiom —
`minmax(min(100%, 360px), 1fr)` — and `panel-grid.ts:3` uses it too. This is a
one-line fix applied consistently.

**Interfaces:**
- Consumes: nothing new.
- Produces: no API change.

- [ ] **Step 1: Write the failing test**

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('Risk grid floors', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/risk/risk.ts'), 'utf8');

  it('never declares a fixed px floor a 320px phone cannot meet', () => {
    // minmax(300px, 1fr) overflows its container below ~330px of content
    // box. min(100%, 300px) collapses instead, which is the whole point.
    const bare = [...src.matchAll(/minmax\(\s*(\d+)px/g)].map((m) => Number(m[1]));
    expect(bare.filter((px) => px > 260)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/risk/risk.spec.ts`
Expected: FAIL — received `[300]`.

- [ ] **Step 3: Write the implementation**

In `risk.ts`, change the `.split` rule:

```css
      /* v95 D1: was minmax(300px, 1fr), which overflows a 320px phone once
         panel padding is taken off. min() lets the track collapse rather
         than push the panel sideways -- same idiom as analytics.ts:1264 and
         panel-grid.ts. */
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
```

Leave the `max-width: 639px` block at `:567` as it is — stacking `.kill` is
correct and already uses a declared breakpoint.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/risk/risk.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory**

At 390px and, if the browser allows it, 320px. Expected: no horizontal page
scroll on Risk at either width.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts
git commit -m "fix(v95): Risk grid tracks collapse instead of overflowing a narrow phone"
```

---

### Task D2: `sb-matrix` keeps its row labels while scrolling

**Files:**
- Modify: `frontend/src/app/ui/matrix.ts:46-64`
- Test: `frontend/src/app/ui/matrix.spec.ts` (create if absent)

The correlation matrix is an N×N table with `white-space: nowrap` on every
`th` and `td`, answered only by `.scroll-x { overflow-x: auto }`. There is no
sticky row-header column, so scrolling right to read a correlation loses the
row label that says which pair it belongs to — the number becomes unreadable
in the strict sense that you cannot tell what it describes.

**Interfaces:**
- Consumes: nothing new.
- Produces: the leading `th` in each row is sticky.

- [ ] **Step 1: Write the failing test**

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('sb-matrix row headers', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/matrix.ts'), 'utf8');

  it('pins the row header against horizontal scroll', () => {
    // Without this, scrolling right to reach a correlation scrolls away the
    // label naming the pair. A number you cannot attribute is not data.
    expect(src).toMatch(/th\[scope=["']row["']\][^{]*\{[^}]*position:\s*sticky/s);
    expect(src).toMatch(/th\[scope=["']row["']\][^{]*\{[^}]*left:\s*0/s);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/matrix.spec.ts`
Expected: FAIL — no sticky rule.

- [ ] **Step 3: Write the implementation**

Ensure each row's leading cell is `<th scope="row">`, then add:

```css
    /* v95 D2: the matrix scrolls sideways by design -- an N×N grid of
       correlations has no narrow form. What it must not do is scroll the row
       label away with the columns, because then the number on screen belongs
       to a pair the reader can no longer name. */
    th[scope="row"] {
      position: sticky;
      left: 0;
      z-index: 1;
      background: var(--surface-1);
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/matrix.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory**

At 390px on Risk: scroll the matrix right and confirm the row labels stay put
and remain legible against the scrolling cells.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/matrix.ts frontend/src/app/ui/matrix.spec.ts
git commit -m "fix(v95): matrix row labels stay pinned while the grid scrolls"
```

---

### Task D3: System — settings controls reach the touch floor

**Files:**
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts:403,512,527`
- Test: `frontend/src/app/workspaces/system/settings-tab.spec.ts`

`.restart` and `.reset` are real buttons at `padding: 1px 6px` and `2px 8px` —
roughly 20px tall, deliberately sized below `--control-h` per the comment at
`:521-526`. One of them restarts the bot. A 20px target for a restart button on
a touch screen is a misfire waiting to happen. `.fields` uses
`auto-fill minmax(260px, 1fr)`, which overflows a panel content box below
~290px.

**Interfaces:**
- Consumes: `--control-h`.
- Produces: no API change.

- [ ] **Step 1: Write the failing test**

```ts
describe('System settings touch targets', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/system/settings-tab.ts'), 'utf8');

  it.each(['.restart', '.reset'])('%s meets the shared control height', (selector) => {
    const rule = src.match(new RegExp(`\\${selector}\\s*\\{[^}]*\\}`, 's'))?.[0] ?? '';
    expect(rule).toMatch(/min-height:\s*var\(--control-h\)/);
  });

  it('field grid collapses rather than overflowing a narrow panel', () => {
    expect(src).toMatch(/minmax\(\s*min\(100%,\s*260px\)/);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/system/settings-tab.spec.ts`
Expected: FAIL on all three.

- [ ] **Step 3: Write the implementation**

Add `min-height: var(--control-h);` to `.restart` and `.reset`, and delete the
`:521-526` comment arguing for the smaller size — it is no longer true, and a
comment defending a removed decision is what A6 existed to clean up elsewhere.
Change `.fields` to `repeat(auto-fill, minmax(min(100%, 260px), 1fr))`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/system/settings-tab.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory**

At 390px: both buttons are comfortably tappable; the settings field grid is one
column with no sideways scroll. Confirm the restart button still reads as a
deliberate, guarded action rather than an inviting one — if raising its height
made it look like a primary button, keep the height and reduce its emphasis
through colour, not size.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/system/settings-tab.ts frontend/src/app/workspaces/system/settings-tab.spec.ts
git commit -m "fix(v95): System restart and reset reach the touch floor; field grid collapses"
```

---

### Task D4: System — scan and logs tabs get a narrow form

**Files:**
- Modify: `frontend/src/app/workspaces/system/scan-tab.ts`
- Modify: `frontend/src/app/workspaces/system/logs-tab.ts`
- Test: `frontend/src/app/workspaces/system/scan-tab.spec.ts`

Neither file contains a single narrow rule. `logs-tab.ts` is the easier case —
`.log { overflow: auto }` already contains its own scroll, so it needs only the
controls above it to stop stacking. `scan-tab.ts` needs its control row to
collapse.

**Interfaces:**
- Consumes: `Toolbar` (B4).
- Produces: `SCAN_CONTROLS: ToolbarControl[]`.

- [ ] **Step 1: Write the failing test**

```ts
describe('Scan tab controls', () => {
  it('declares a floor for every control', () => {
    expect(SCAN_CONTROLS.every((c) => c.inlineFrom !== undefined)).toBe(true);
  });

  it('keeps the scan trigger inline everywhere', () => {
    // The one thing this tab is for. It never goes in a sheet.
    expect(SCAN_CONTROLS.find((c) => c.id === 'run')!.inlineFrom).toBe('xs');
  });

  it('demotes the tuning controls below md', () => {
    for (const id of ['universe', 'horizon', 'force']) {
      expect(isInline(SCAN_CONTROLS.find((c) => c.id === id)!.inlineFrom, 'sm')).toBe(false);
    }
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/system/scan-tab.spec.ts`
Expected: FAIL — `SCAN_CONTROLS` is not exported.

- [ ] **Step 3: Write the implementation**

Declare `SCAN_CONTROLS` with `run` at `'xs'`, the progress readout at `'xs'`
(a running scan's progress is never hidden), and the tuning inputs at `'md'`.
Wrap the scan control row in `<sb-toolbar>`. In `logs-tab.ts`, wrap the filter
controls the same way and confirm `.log`'s own `overflow: auto` is left intact.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/system/scan-tab.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory**

At 390px: the scan trigger and its progress are visible without opening the
sheet; the log viewport scrolls itself rather than the page.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/system/scan-tab.ts frontend/src/app/workspaces/system/logs-tab.ts frontend/src/app/workspaces/system/scan-tab.spec.ts
git commit -m "feat(v95): System scan and logs tabs get a narrow form"
```

---

### Task D5: Versions — the lane rail stops clipping silently

**Files:**
- Modify: `frontend/src/app/workspaces/versions/versions.ts:259-284`
- Test: `frontend/src/app/workspaces/versions/versions.spec.ts`

`.lane-name` is `width: 4.5rem`, and `.bracket-row`/`.overlay-row` hard-code
`calc(4.5rem + var(--space-8))` offsets, all inside `.strip { overflow: hidden }`.
At 390px the actual timeline track is ~230px, and anything past it is **clipped
with no scroll affordance** — the worst failure mode available, because the
screen gives no sign that content exists.

**Interfaces:**
- Consumes: nothing new.
- Produces: `--lane-w`, a custom property the three rules share.

- [ ] **Step 1: Write the failing test**

```ts
describe('Versions lane rail', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/versions/versions.ts'), 'utf8');

  it('expresses the rail width once', () => {
    // 4.5rem appeared in three rules; changing one and missing the others
    // slides the brackets off the lanes.
    expect(src).toMatch(/--lane-w:/);
    expect([...src.matchAll(/4\.5rem/g)]).toHaveLength(0);
  });

  it('narrows the rail below sm rather than clipping the track', () => {
    expect(src).toMatch(/@media\s*\(\s*max-width:\s*639px\s*\)[\s\S]*--lane-w:/);
  });

  it('gives the strip a scroll affordance instead of hiding overflow', () => {
    const strip = src.match(/\.strip\s*\{[^}]*\}/s)?.[0] ?? '';
    expect(strip).not.toMatch(/overflow:\s*hidden/);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/versions/versions.spec.ts`
Expected: FAIL on all three.

- [ ] **Step 3: Write the implementation**

```css
    /* v95 D5: the rail width was 4.5rem written into three rules, inside a
       strip with overflow:hidden -- so at 390px the timeline was cut off
       with nothing on screen saying so. One custom property, a narrower rail
       below sm, and a real scroller. */
    :host { --lane-w: 4.5rem; }
    @media (max-width: 639px) { :host { --lane-w: 3rem; } }

    .strip { overflow-x: auto; }
    .lane-name { width: var(--lane-w); }
    .bracket-row { margin-left: calc(var(--lane-w) + var(--space-8)); }
    .overlay-row { left: calc(var(--lane-w) + var(--space-8)); }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/versions/versions.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory**

At 390px: the release timeline scrolls sideways and the brackets stay aligned
with their lanes. At 1024: unchanged from before.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/versions/versions.ts frontend/src/app/workspaces/versions/versions.spec.ts
git commit -m "fix(v95): Versions timeline scrolls instead of clipping, rail width declared once"
```

---

### Task D6: Gallery — the new primitives get demo states

**Files:**
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts`
- Test: `frontend/src/app/workspaces/gallery/gallery.spec.ts`

The gallery is where this repo shows every component state. Three new
behaviours need a demo, or the next person to touch them has no reference:
the toolbar sheet, a collapsed panel with its digest, and a panel force-expanded
over a problem.

**Interfaces:**
- Consumes: `Toolbar` (B4), `Panel.digest`/`Panel.problem` (B7, B8),
  `DataTable` row detail (B3).
- Produces: no API change.

- [ ] **Step 1: Write the failing test**

```ts
describe('Gallery covers the v95 primitives', () => {
  it.each([
    ['toolbar sheet', '.toolbar-sheet-button'],
    ['collapsed panel digest', '.panel-digest'],
    ['force-expanded panel', '.panel-problem'],
    ['row detail', 'button.detail-toggle'],
  ])('demonstrates the %s', (_name, selector) => {
    expect(el().querySelector(selector)).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/gallery/gallery.spec.ts`
Expected: FAIL — none of the four render.

- [ ] **Step 3: Write the implementation**

Add a "Content priority" section to the gallery with four specimens, each
forced through its `viewportAt` override so the state is visible at any window
size — the gallery's job is to show states, not to make the reader resize.
Label each with the rule it demonstrates and the spec section it comes from.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/gallery/gallery.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory**

Load `/ui` at 1024 and confirm all four specimens render their forced state.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/gallery/gallery.ts frontend/src/app/workspaces/gallery/gallery.spec.ts
git commit -m "docs(v95): gallery demonstrates the toolbar sheet, panel digest and row detail"
```

---

## Phase D exit criteria

- No fixed `minmax(Npx, …)` floor above 260px anywhere in `risk.ts` or
  `settings-tab.ts`.
- The correlation matrix keeps its row labels while scrolling.
- `.restart` and `.reset` meet `--control-h`.
- `scan-tab.ts` and `logs-tab.ts` have a narrow form.
- `versions.ts` declares its rail width once and scrolls rather than clipping.
- The gallery demonstrates all four new states.
- All four workspaces looked at, by a person, at 390 / 768 / 1024.
