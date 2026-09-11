# v85 Part 5 — The other workspaces, and release

Header block, global constraints, parallelisation and exit criteria live in
`2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

**R5-01 runs first and alone** — it writes the guard that the rest satisfy.
**R5-02 … R5-08 are Group C**: one workspace each, disjoint files, safe to run
in parallel. **R5-09 runs last and alone.**

---

## The v85 panel language

Every restyle task in this part applies the same checklist. It is written once
here rather than repeated in eight tasks, and each task's Step 3 means "apply
this list to this workspace":

1. **Panels are `sb-panel`**, never a bespoke `div` with a border and a
   heading. A workspace that hand-rolled a card gets the primitive instead.
2. **Metric grids are `repeat(auto-fit, minmax(140px, 1fr))`**, matching
   `sb-trading-performance` — not a fixed column count and not a breakpoint
   list.
3. **Row rhythm is `var(--register-pad)`** between panels, matching the
   Dashboard's `.top-row` / `.bottom-row`.
4. **Tables use the shared header treatment**: `--text-micro`, uppercase,
   `letter-spacing: 0.1em`, `--text-faint`, right-aligned numeric columns with
   `font-variant-numeric: tabular-nums`.
5. **No colour outside `tokens.css`.** `ui/primitives.spec.ts` already fails
   the build on a hex literal; this is a reminder, not a new rule.
6. **No in-page `<h1>`/heading** — the top bar owns it (R1-11 removed them;
   do not reintroduce one).
7. **State cues are never colour alone.** Where a workspace signals status by
   colour, add the second cue (weight, a rail, an icon) the nav got in R1-10.

---

# Phase 1 — The guard

### Task R5-01: A consistency guard across every workspace

**Files:**
- Create: `frontend/src/app/workspaces/workspace-consistency.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: a failing test listing every workspace still to convert. R5-02 …
  R5-08 each turn one name green.

This is the one test in Part 5 that is supposed to stay red for a while. It
reads the workspace sources as text, which is unusual — but the property being
checked ("no workspace hand-rolls a panel") is a property of the source, not of
a rendered component, and eight separate render assertions would not catch a
ninth workspace added later.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'vitest';

/** Every workspace entry component, by source path. Vitest resolves these
 *  eagerly as raw strings, so this reads the file rather than rendering it. */
const SOURCES = import.meta.glob('./**/*.ts', { as: 'raw', eager: true }) as
  Record<string, string>;

const WORKSPACE_ENTRY = /\/(dashboard|trades|analytics|calendar|watchlist|risk|system|versions)\/[a-z-]+\.ts$/;

function workspaceFiles(): [string, string][] {
  return Object.entries(SOURCES).filter(
    ([path]) => WORKSPACE_ENTRY.test(path) && !path.endsWith('.spec.ts')
      && !path.includes('.routes.') && !path.includes('.helpers.'),
  );
}

describe('workspace visual consistency', () => {
  it('uses the shared panel primitive rather than hand-rolled cards', () => {
    const offenders = workspaceFiles()
      .filter(([, source]) => source.includes('<div class="panel')
        || /border:\s*1px solid var\(--border\)[\s\S]{0,80}border-radius/.test(source))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it('never hard-codes a colour', () => {
    const offenders = workspaceFiles()
      .filter(([, source]) => /#[0-9a-fA-F]{3,8}\b/.test(source))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it('renders no in-page page heading -- the top bar owns the title', () => {
    const offenders = workspaceFiles()
      .filter(([, source]) => /<sb-section-head[^>]*\sheading=/.test(source)
        || /<h1[\s>]/.test(source))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it and read the failure as a worklist**

```bash
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: FAIL, with each assertion naming the files still to convert. **Copy
that list into the task notes** — it is the actual scope of R5-02 … R5-08, and
it is more trustworthy than this plan's guess at which workspace hand-rolled
what.

- [ ] **Step 3: Commit the guard red**

```bash
git add frontend/src/app/workspaces/workspace-consistency.spec.ts
git commit -m "test(workspaces): add the v85 consistency guard"
```

Committing a known-failing test is deliberate here and only here: it is the
checklist the parallel Group C tasks work against. It goes green at R5-08 and
must be green before R5-09.

---

# Phase 2 — Group C: the workspaces

Each task below has the same shape. The differences are which files, and what
that workspace's own spec asserts.

### Task R5-02: Restyle Watchlist and Ticker detail

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts`
- Modify: `frontend/src/app/workspaces/watchlist/ticker-detail.ts`
- Test: the existing specs in that directory

**Interfaces:**
- Consumes: the panel language above.
- Produces: nothing. Presentation only — no template logic, binding or store
  call changes.

- [ ] **Step 1: Capture the before**

With `npm start` running, screenshot `/watchlist` and one `/watchlist/:symbol`
at 1440px and 390px via chrome-devtools. These are the comparison for step 5.

- [ ] **Step 2: Run the workspace's specs and note them green**

```bash
cd frontend && npx ng test --include "src/app/workspaces/watchlist/**/*.spec.ts"
```

Expected: PASS. A restyle must not change behaviour, so this is the baseline —
if anything is red before you start, fix that first or the diff is unreadable.

- [ ] **Step 3: Apply the panel language**

Work the checklist at the top of this file, item by item, against both files.
Change only `styles`, class names and the markup that carries them. If a
change requires touching a binding, a `computed`, or a store call, stop — that
is not a restyle and belongs in its own task.

- [ ] **Step 4: Run the specs again**

```bash
cd frontend && npx ng test --include "src/app/workspaces/watchlist/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: the workspace specs still PASS unchanged, and the guard no longer
names these two files.

- [ ] **Step 5: Compare against the before**

Screenshot both pages again at both widths. Confirm: the same information is
present, nothing overflows at 390px, and the panels now read as the same
system as the Dashboard.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/watchlist
git commit -m "style(watchlist): apply the v85 panel language"
```

---

### Task R5-03: Restyle Trades and Trade detail

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.ts`
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts`
- Test: the existing specs in that directory

**Interfaces:**
- Consumes: the panel language.
- Produces: nothing.

**The heaviest one in this group.** Trades shares `trades.columns.ts` with the
Dashboard's table — **do not edit that file here.** Its column definitions are
shared by design (spec v18 D6: shared definitions, separate preferences), and
changing them to suit one workspace changes both.

- [ ] **Step 1: Capture the before**

Screenshot `/trades` and one `/trades/:id` at 1440px and 390px.

- [ ] **Step 2: Run the specs and note them green**

```bash
cd frontend && npx ng test --include "src/app/workspaces/trades/**/*.spec.ts"
```

- [ ] **Step 3: Apply the panel language**

Checklist items 1–7. Trade detail's tab strip already uses `sb-tab-bar` — leave
its behaviour alone and restyle only what the checklist names.

- [ ] **Step 4: Run the specs again**

```bash
cd frontend && npx ng test --include "src/app/workspaces/trades/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

- [ ] **Step 5: Compare against the before**

Confirm in particular that the trades table's own column picker and density
controls still work — they share the primitive the Dashboard's table uses, and
a styling change to a shared control shows up here first.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/trades
git commit -m "style(trades): apply the v85 panel language"
```

---

### Task R5-04: Restyle Analytics

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (and any panel
  components in that directory)
- Test: the existing specs in that directory

**Interfaces:**
- Consumes: the panel language.
- Produces: nothing.

**Charts keep their own palette.** `ui/chart-palette.ts` and
`ui/chart/chart-theme.ts` own series colours and are shared with Trade detail's
chart — the checklist's "no colour outside tokens" applies to the page chrome,
not to a chart's series encoding. Do not retune the chart palette here.

- [ ] **Step 1: Capture the before**

Screenshot `/analytics` at 1440px and 390px, including each of its tabs.

- [ ] **Step 2: Run the specs and note them green**

```bash
cd frontend && npx ng test --include "src/app/workspaces/analytics/**/*.spec.ts"
```

- [ ] **Step 3: Apply the panel language**

- [ ] **Step 4: Run the specs again**

```bash
cd frontend && npx ng test --include "src/app/workspaces/analytics/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

- [ ] **Step 5: Compare against the before**

Charts must be legible at 390px — this is the workspace where a padding change
most easily squeezes a plot into unreadability.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/analytics
git commit -m "style(analytics): apply the v85 panel language"
```

---

### Task R5-05: Restyle Calendar

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts`
- Test: the existing specs in that directory

**Interfaces:**
- Consumes: the panel language.
- Produces: nothing.

The P&L grid's own green/red cells are a data encoding, like a chart's — keep
them reading from `--pos`/`--neg` and do not flatten them to chrome colours.

- [ ] **Step 1: Capture the before** — screenshot `/calendar` at both widths.

- [ ] **Step 2: Run the specs and note them green**

```bash
cd frontend && npx ng test --include "src/app/workspaces/calendar/**/*.spec.ts"
```

- [ ] **Step 3: Apply the panel language**

- [ ] **Step 4: Run the specs again**

```bash
cd frontend && npx ng test --include "src/app/workspaces/calendar/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

- [ ] **Step 5: Compare against the before** — the month grid must not wrap or
clip at 390px.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/calendar
git commit -m "style(calendar): apply the v85 panel language"
```

---

### Task R5-06: Restyle Risk

**Files:**
- Modify: `frontend/src/app/workspaces/risk/risk.ts`
- Test: the existing specs in that directory

**Interfaces:**
- Consumes: the panel language.
- Produces: nothing.

**The killswitch control lives here and is the most consequential button in the
app.** Restyle it, but it must stay unmistakable and must keep whatever
confirmation it already has. If it currently has none, that is a finding to
report — not something to fix silently inside a styling task.

- [ ] **Step 1: Capture the before** — screenshot `/risk` at both widths, in
both killswitch states if you can reach them.

- [ ] **Step 2: Run the specs and note them green**

```bash
cd frontend && npx ng test --include "src/app/workspaces/risk/**/*.spec.ts"
```

- [ ] **Step 3: Apply the panel language**

- [ ] **Step 4: Run the specs again**

```bash
cd frontend && npx ng test --include "src/app/workspaces/risk/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

- [ ] **Step 5: Compare against the before** — engage the killswitch on a
scratch data dir and confirm both this page and the shell strip (R1-09) say so.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/risk
git commit -m "style(risk): apply the v85 panel language"
```

---

### Task R5-07: Restyle System and Versions

**Files:**
- Modify: `frontend/src/app/workspaces/system/system.ts`
- Modify: `frontend/src/app/workspaces/versions/versions.ts`
- Test: the existing specs in both directories

**Interfaces:**
- Consumes: the panel language.
- Produces: nothing.

Two small workspaces in one task: neither carries enough markup to be worth a
reviewer's separate gate, and they share no file with each other or with any
other Group C task.

- [ ] **Step 1: Capture the before** — screenshot `/system` and `/versions` at
both widths.

- [ ] **Step 2: Run the specs and note them green**

```bash
cd frontend && npx ng test --include "src/app/workspaces/system/**/*.spec.ts"
cd frontend && npx ng test --include "src/app/workspaces/versions/**/*.spec.ts"
```

- [ ] **Step 3: Apply the panel language**

System's settings form controls come from `ui/form-controls.ts` — restyle the
page, not the primitive. A change there reaches every form in the app and is
not in this plan's scope.

- [ ] **Step 4: Run the specs again**

```bash
cd frontend && npx ng test --include "src/app/workspaces/system/**/*.spec.ts"
cd frontend && npx ng test --include "src/app/workspaces/versions/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

- [ ] **Step 5: Compare against the before**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/system frontend/src/app/workspaces/versions
git commit -m "style(system,versions): apply the v85 panel language"
```

---

### Task R5-08: Add the new components to the /ui gallery

**Files:**
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts`
- Test: `frontend/src/app/workspaces/gallery/gallery.spec.ts` (if present)

**Interfaces:**
- Consumes: every component added in Parts 1, 3 and 4.
- Produces: nothing. The gallery is the developer surface where a primitive is
  checked in isolation.

The gallery is where the four new icons (R1-03) and the five new panels
(R3-01 … R3-06) become inspectable without seeding trade data. A component
that is not in it is one nobody can check in both themes and both densities.

- [ ] **Step 1: Write the failing test**

```ts
it('exhibits every v85 panel and icon', () => {
  const f = TestBed.createComponent(Gallery);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  for (const tag of ['sb-portfolio-value', 'sb-trading-performance',
                     'sb-recent-activity', 'sb-watchlist-panel', 'sb-market-movers']) {
    expect(el.querySelector(tag)).not.toBeNull();
  }
  for (const icon of ['clock', 'more', 'opened', 'closed']) {
    expect(el.querySelector(`sb-icon[name="${icon}"]`)).not.toBeNull();
  }
});
```

If this workspace has no spec file, create one following the pattern in any
other workspace spec in this repo.

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include "src/app/workspaces/gallery/**/*.spec.ts"
```

Expected: FAIL — none of the new tags are present.

- [ ] **Step 3: Add a section per component**

Follow the gallery's existing section pattern. Feed each panel static sample
values — including the null cases, which is the point of having them here:
a `payoffRatio` of `null`, a `balance` of `null`, an empty activity feed.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include "src/app/workspaces/gallery/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: PASS — and the consistency guard should now be **fully green**, with
every workspace converted. If it is not, the remaining names are Group C tasks
that have not landed yet; wait for them rather than patching around it.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/gallery
git commit -m "feat(gallery): exhibit the v85 panels and icons"
```

---

# Phase 3 — Verification and release

### Task R5-09: Full-suite verification and release

**Files:**
- Modify: `VERSION.json`
- Modify: whatever `scripts/dev/build_version_matrix.py` regenerates
- Move: this plan's five part files into `docs/superpowers/plans/implemented/`

**Interfaces:**
- Consumes: every task in every part.
- Produces: the release.

**This is the plan's only full-suite run.** It has not been run per-task and
must not be run again after a clean merge.

- [ ] **Step 1: Confirm the consistency guard is green**

```bash
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: PASS. A red guard here means a Group C task is missing; do not
release past it.

- [ ] **Step 2: Run the whole frontend suite**

```bash
cd frontend && npx ng test
```

Expected: every spec passes. Read the output — a changed test count is fine, a
failure is not.

- [ ] **Step 3: Run the whole backend suite**

```bash
python scripts/dev/testrun.py full
```

Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure;
read `docs/claude/testing-cost.md` before reacting to one.

- [ ] **Step 4: Screenshot every workspace, both widths**

With the dev server running, capture all eight workspaces plus the two detail
views at 1440px and 390px. Check each against exit criteria 1–4 in the index:
no leftover heading, no double title, no old-style panel, no horizontal
scroll. This is the evidence that a visual redesign actually landed — the test
suites cannot see any of it.

- [ ] **Step 5: Bump the versions**

Read `VERSION.json` **from disk right now** — never from this plan, never from
memory, never from an earlier task's note. Then:

- `ui` gets a **minor** bump (`x.Y.0`), per the index header.
- `bot` gets a **patch** bump (`x.y.Z`).
- Set each bumped line's `*_updated` stamp to now, in the existing
  `YYYY-MM-DD HH-MM-SS` format.

```bash
python scripts/dev/build_version_matrix.py
```

The local gate runs before the bump and structurally cannot catch a missed
regeneration — this step is the only thing that does.

- [ ] **Step 6: Close the plan out**

```bash
git mv docs/superpowers/plans/2026-09-11-v85-dashboard-shell-redesign_*.md \
       docs/superpowers/plans/implemented/
```

If either prediction in the header came out wrong — the `ui` bump landed as a
patch, or the work bought something other than `none (integrity)` — amend that
line in this closing commit with one clause saying why. A wrong prediction
recorded is worth more than a right one assumed.

- [ ] **Step 7: Commit the release**

```bash
git add VERSION.json docs/superpowers/plans
git commit -m "release(v85): dashboard and shell redesign"
```

- [ ] **Step 8: Mirror anything that changed on production**

If any fix was made directly on the Hetzner VM during this work, it must be
back in this repo and committed before the plan is done — `CLAUDE.md`'s
standing rule. If nothing was touched there, say so in the task notes.
