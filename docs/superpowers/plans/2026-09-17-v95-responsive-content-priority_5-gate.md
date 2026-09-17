# v95 — Part 5: The gate

Part of `2026-09-17-v95-responsive-content-priority`. Header block, goal,
global constraints, parallelisation map and exit criteria live in
`_0-index.md` — read that first.

# Phase E — Parity gate, handoff, verification

**Sequential throughout.** E1 asserts against declarations that every Phase C
and D task produces; running it earlier fails for the right reason at the wrong
time. E4 is last by definition.

---

### Task E1: The parity gate

**Files:**
- Create: `frontend/src/app/ui/parity.spec.ts`
- Modify: `frontend/src/app/ui/priority.ts` (export the registry helper)

This is what makes "full parity" a gate rather than an aspiration. It walks
every declared column, control and panel in the app and asserts each is
reachable at all five viewports — inline, or through a destination that exists
and is not itself demoted.

It belongs beside `breakpoints.spec.ts`, `tokens.spec.ts` and
`workspace-consistency.spec.ts`, which this repo already keeps for exactly this
class of guarantee.

**Interfaces:**
- Consumes: every `*_CONTROLS` and `*_COLUMNS` export from Phases C and D,
  `PriorityDecl`, `isInline`, `VIEWPORT_ORDER`.
- Produces: `assertReachable(decls: PriorityDecl[]): string[]` in `priority.ts`
  — returns the ids that fail, empty when all pass. A function rather than a
  bare test so the gallery and any future surface can reuse it.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/parity.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { VIEWPORT_ORDER, assertReachable, isInline } from './priority';
import { TRADES_CONTROLS } from '../workspaces/trades/trades';
import { TRADE_COLUMNS } from '../workspaces/trades/trades.columns';
import { DASHBOARD_COLUMNS } from '../workspaces/dashboard/dashboard';
import { WATCHLIST_COLUMNS, WATCHLIST_CONTROLS } from '../workspaces/watchlist/watchlist';
import { SCAN_CONTROLS } from '../workspaces/system/scan-tab';

/* v95 §9. Parity is a promise about REACHABILITY, not visibility. A demoted
 * item is fine; an item demoted to a destination that does not exist, or that
 * is itself demoted at the same viewport, is not. */

const SURFACES = {
  'trades controls': TRADES_CONTROLS.map((c) => ({ ...c, demotesTo: 'sheet' as const })),
  'trades columns': TRADE_COLUMNS.map((c) => ({ id: c.key, inlineFrom: c.inlineFrom, demotesTo: 'expansion' as const })),
  'dashboard columns': DASHBOARD_COLUMNS.map((c) => ({ id: c.key, inlineFrom: c.inlineFrom, demotesTo: 'expansion' as const })),
  'watchlist columns': WATCHLIST_COLUMNS.map((c) => ({ id: c.key, inlineFrom: c.inlineFrom, demotesTo: 'expansion' as const })),
  'watchlist controls': WATCHLIST_CONTROLS.map((c) => ({ ...c, demotesTo: 'sheet' as const })),
  'scan controls': SCAN_CONTROLS.map((c) => ({ ...c, demotesTo: 'sheet' as const })),
};

describe('content parity', () => {
  it.each(Object.entries(SURFACES))('%s: every item is reachable at every viewport', (_name, decls) => {
    expect(assertReachable(decls)).toEqual([]);
  });

  it.each(Object.entries(SURFACES))('%s: every id is unique', (_name, decls) => {
    const ids = decls.map((d) => d.id);
    expect(ids).toEqual([...new Set(ids)]);
  });

  it('every surface keeps at least one item inline at xs', () => {
    // A surface where everything demotes renders as an empty bar above a
    // sheet button -- technically parity, practically a blank screen.
    for (const [name, decls] of Object.entries(SURFACES)) {
      const inline = decls.filter((d) => isInline(d.inlineFrom, 'xs'));
      expect(inline.length, `${name} has nothing inline at xs`).toBeGreaterThan(0);
    }
  });

  it('covers every viewport in VIEWPORT_ORDER, so a new band cannot be forgotten', () => {
    expect(VIEWPORT_ORDER).toHaveLength(5);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/parity.spec.ts`
Expected: FAIL — `assertReachable` is not exported.

- [ ] **Step 3: Write the implementation**

Add to `frontend/src/app/ui/priority.ts`:

```ts
/**
 * Which of these declarations are NOT reachable at some viewport — v95 §9.
 *
 * Returns the failing ids, empty when every item is reachable everywhere.
 * Returning ids rather than throwing keeps it usable outside a test, and
 * makes a failure name what broke instead of only that something did.
 *
 * A declaration fails when it demotes but names no destination, or names one
 * this surface does not provide. It does NOT fail merely for being demoted —
 * that is the whole design.
 */
export function assertReachable(decls: PriorityDecl[]): string[] {
  const failed: string[] = [];
  const targets: ReadonlySet<DemotionTarget> = new Set(['expansion', 'sheet', 'digest']);

  for (const decl of decls) {
    const demotesSomewhere = VIEWPORT_ORDER.some((v) => !isInline(decl.inlineFrom, v));
    if (demotesSomewhere && !targets.has(decl.demotesTo)) {
      failed.push(decl.id);
    }
  }
  return failed;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/parity.spec.ts`
Expected: PASS. **If a surface fails, fix the declaration, never the gate** —
a gate edited to accommodate a failure is not a gate.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/priority.ts frontend/src/app/ui/parity.spec.ts
git commit -m "test(v95): parity gate -- every declared item reachable at every viewport"
```

---

### Task E2: The repo-wide breakpoint guard

**Files:**
- Create: `frontend/src/app/ui/breakpoint-guard.spec.ts`

A2 and A5 corrected the drift in two files. This makes the rule permanent
across `frontend/src/app/`, so the next hand-rolled `max-width: 900px` fails in
CI rather than six months later when someone resizes to exactly that width.

The two documented exceptions are `tape.css` and `earnings-calendar.ts` — both
genuinely special-cased, both already correct, both named in the spec.

**Interfaces:**
- Consumes: `BREAKPOINTS`.
- Produces: a guard test only.

- [ ] **Step 1: Write the failing test**

```ts
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { BREAKPOINTS } from './breakpoints';

/* Declared floors, and the max-width form of each (floor - 1). An @media
 * cannot read var(), so these literals are duplicated from breakpoints.ts by
 * necessity -- this test is what keeps the two in step. */
const ALLOWED = new Set(
  Object.values(BREAKPOINTS).flatMap((v) => [String(v), String(v - 1)]),
);

/** Genuinely bespoke, documented in spec v95 §6. */
const EXEMPT = ['shell/tape/tape.css', 'workspaces/watchlist/earnings-calendar.ts'];

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.(ts|css)$/.test(entry) && !/\.spec\.ts$/.test(entry) ? [path] : [];
  });
}

describe('breakpoint discipline', () => {
  const root = join(process.cwd(), 'src/app');

  it('uses only declared breakpoint values in width queries', () => {
    const offenders: string[] = [];

    for (const path of walk(root)) {
      const relative = path.slice(root.length + 1).replace(/\\/g, '/');
      if (EXEMPT.some((e) => relative.endsWith(e))) continue;

      const widths = [...readFileSync(path, 'utf8')
        .matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);

      for (const width of widths) {
        if (!ALLOWED.has(width)) offenders.push(`${relative}: ${width}px`);
      }
    }

    // A value outside the declared set puts the stylesheet and
    // ViewportService on different scales -- the defect breakpoints.ts's own
    // docstring warns about, and the one v95 A2 found in shell.css.
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails or passes**

Run: `cd frontend && npm test -- --include src/app/ui/breakpoint-guard.spec.ts`
Expected: PASS if A2, A5, C3 and D5 all landed correctly. **If it fails, the
named files are real drift the earlier tasks missed** — fix them here rather
than exempting them. Only add to `EXEMPT` for a value that is genuinely not a
breakpoint (a print query, a `min-resolution`), and say why in a comment.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/ui/breakpoint-guard.spec.ts
git commit -m "test(v95): guard every width query against the declared breakpoints"
```

---

### Task E3: Hand the requirement to v94

**Files:**
- Modify: `docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md:301-302`

v94's spec lists "mobile-first layout beyond the existing breakpoints" as a
non-goal. That was correct when written and is now incomplete: v95 excluded
Analytics precisely because v94 rebuilds it, so without this amendment Analytics
becomes the one workspace the parity gate cannot cover.

This edits a **committed spec of a live plan**. It adds a requirement; it
changes nothing v94 has already decided.

**Interfaces:**
- Consumes: nothing.
- Produces: no code.

- [ ] **Step 1: Read the current non-goal**

```bash
sed -n '295,305p' docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md
```

- [ ] **Step 2: Apply the amendment**

Replace the non-goal clause naming mobile-first layout with:

```markdown
per-panel filters (the bar is the only scope); changing `MIN_CELL_N` or making
it a setting.

**Amended by v95 (2026-09-17).** "Mobile-first layout beyond the existing
breakpoints" was a non-goal here because no model existed to adopt. v95 now
provides one, and Analytics is the single workspace it deliberately excluded —
v95 §11. So the rebuild **does** carry a responsive requirement: every column,
control and panel this spec creates declares `inlineFrom` per v95 §3, demotes
to the destination its kind names in v95 §4, and is registered with the parity
gate in v95 §9. Without this, Analytics is the one workspace that gate cannot
cover.
```

- [ ] **Step 3: Verify the cross-reference resolves**

```bash
grep -n "v95" docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md
grep -n "§11\|Analytics" docs/superpowers/specs/2026-09-17-v95-responsive-content-priority-design.md | head
```

Expected: v94 names v95, and v95 §11 names v94. A one-way reference is how this
gets forgotten.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md
git commit -m "docs(v94): Analytics adopts v95's content-priority model as it is rebuilt"
```

---

### Task E4: Full-suite verification

**Files:** none.

- [ ] **Step 1: Run the frontend suite once, over everything**

Run: `cd frontend && npm test`

Expected: `0 failed`. This plan edits no Python, so
`python scripts/dev/testrun.py full` is **not** part of its gate — do not run
it to feel thorough.

**If it is not green, fix forward from those failures.** They are this plan's
regressions, and the task is not done until the run is. A red result here is
the start of the work, not a reason to re-open earlier tasks.

Two failure shapes to expect, both legitimate and both fixed here:
- A test asserting a height that A3's touch floor changed. The assertion was
  pinning the opt-out; update it to `--control-h`.
- A test counting rendered columns that B2's split changed. Point it at the
  inline set.

One failure shape that is **not** legitimate: any v80 D4 phone-mode test. If
`'keeps the table below the breakpoint -- no cards'`, the pinned identity
column or the sort select fails, a task reversed a decision this plan
committed to preserving. Fix the task, not the test.

- [ ] **Step 2: Final visual walk**

At 390, 768 and 1024, walk all eight workspaces plus the shell. Confirm the
five defects that motivated the spec are gone:

1. `997,291.88 €` readable on one line at 768px.
2. Trades' first data row reachable without four screens of scrolling.
3. Open Positions shows P&L% and R inline; the rest one tap away.
4. Status tabs show their counts at every width.
5. Calendar's month data reachable in about one screen at 390px.

- [ ] **Step 3: Commit anything the walk fixed**

```bash
git add -A frontend/src
git commit -m "fix(v95): defects found in the final responsive walk"
```

---

## Phase E exit criteria

- `parity.spec.ts` passes over every surface, with no surface empty at `xs`.
- `breakpoint-guard.spec.ts` passes with only the two documented exemptions.
- v94's spec names v95, and v95 §11 names v94.
- `cd frontend && npm test` is green once, at E4.
- The five motivating defects are gone, confirmed by eye at three widths.
- v80 D4 survives untouched.

## Closing the plan

Per `docs/claude/document-lifecycle.md`: move all six part files to
`docs/superpowers/plans/implemented/`, move the spec to
`docs/superpowers/specs/implemented/`, and resolve the `ui minor` bump from the
`VERSION.json` on disk at that moment — never from this plan, which
deliberately states no number.
