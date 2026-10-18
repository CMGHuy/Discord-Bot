# v166 Trade detail reorganisation. Part 5: responsive grid, visual pass, full suite (TD11..TD13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task TD11:" -A 400 docs/superpowers/plans/2026-10-16-v166-trade-detail-reorganisation_5-grid-verify.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v166-trade-detail-reorganisation-design.md`](../specs/2026-10-16-v166-trade-detail-reorganisation-design.md) (§ 7 Responsive card grid and its Acceptance rule; § Testing, Visual pass; amendments 1 and 3)
**Index:** [`2026-10-16-v166-trade-detail-reorganisation_0-index.md`](2026-10-16-v166-trade-detail-reorganisation_0-index.md) carries the header, `## Global Constraints`, `## Review Focus`, `## Parallelisation`, the task ledger and `## Handoff`. Every task below implicitly includes the Global Constraints.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation`. Never `cd`; use `git -C $WT`, `python $WT/scripts/dev/testrun.py ...` and `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`. File paths in `**Files:**` blocks are relative to `$WT`.

**`GATES`** = `--include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts` (written out in full in every command below).

**Order.** TD11 after TD10 (part 4): both tabs are mounted as `div.grid-host > div.card-grid.(overview|why)-grid` with `div.cell[data-area]` children and the `[style.--areas-1|2|3]` bindings. TD12 after TD11. TD13 last, after every other task is committed.

**State this part starts from (after TD10).** `trade-detail.ts` carries TD9's one-column grid rules (`.grid-host { min-width: 0 }`, `.card-grid { display: grid; grid-template-columns: minmax(0, 1fr); grid-template-areas: var(--areas-1); gap: var(--section-gap) }`, `.cell { min-width: 0 }`, `.context { display: grid; align-content: start; gap: var(--section-gap) }`) and, now dead, the old `.panels` rule and the page-level `dl`, `dl > div`, `dt`, `dd` rules (their last users, the Plan, Live and Strategy blocks, are gone). The four dl-bearing cards (`position-card.ts`, `strategy-record-card.ts`, `level-sources-card.ts`, `scores-card.ts`) lay their `dl` out in one column.

**Three device classes (`docs/claude/ui-design.md` § Device classes, § Checklist).** This part is where the page is made, and checked, to work on phone (< 640), tablet (640–1023) and desktop (>= 1024) at once:
- The card grid responds to its **container** (`.grid-host`, `container: cards / inline-size`), not the viewport: 1 column below 640 px of container width, 2 at 640–1023, 3 at >= 1024 (amendment 1; only the declared breakpoints, `ui/breakpoints.ts:BREAKPOINTS`). At a 1440 px viewport the content pane is about 1370 px (3 columns), at 1024 about 960 (2), at 768 (2), at 390 (1). Opening or closing the sidebar moves the grid between classes live, with no device detection.
- Each card's own `dl` reads its **cell** (`.cell`, `container-type: inline-size`) and flows into two columns at >= 640 px of cell width. No container ever sits on the shared `sb-panel`.
- No horizontal page scroll: every wrapper keeps `min-width: 0`, every track is `minmax(0, 1fr)`, and the tables inside cards scroll inside their own `.table-scroll` box (TD7).
- Touch targets: the header actions and tab buttons take `min-height: var(--control-h)`, which `tokens.css` raises to 44 px under `(pointer: coarse), (max-width: 639px)`. TD12 measures them at 390 px.
- Nothing on this page is a paged data table, so `§ Tables and pagers` does not apply; there is no per-device saved choice.
- Done means checked at 1440, 1024, 768 and 390 px with Playwright (`frontend/scripts/browse.mjs`), never claude-in-chrome: TD12.

---

# Phase 5 — Grid and verification

### Task TD11: Responsive grid: container queries at 640/1024, area maps, stretch, two-column `dl`; `.panels` removed

**Model:** sonnet — CSS in one component plus source-pinning specs

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (styles only: the dead `.panels` rule, TD9's grid block, the dead page-level `dl` / `dl > div` / `dt` / `dd` rules)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (two `node:` imports at the top; one new describe block at the end)
- Modify: `frontend/src/app/workspaces/trades/position-card.ts` (styles: one `@container` block)
- Modify: `frontend/src/app/workspaces/trades/strategy-record-card.ts` (styles: one `@container` block)
- Modify: `frontend/src/app/workspaces/trades/level-sources-card.ts` (styles: one `@container` block)
- Modify: `frontend/src/app/workspaces/trades/scores-card.ts` (styles: one `@container` block)

`plan-card.ts` is named in the index ledger's TD11 row but needs no edit: the Plan card holds a `table` inside `.table-scroll` (TD7), not a `dl`, so the two-column rule has nothing to apply to. `level-sources-card.ts` and `scores-card.ts` are added because they are the two dl-bearing cards most often given a full row (`sources sources sources`; `scores` widens when `why` is absent), which is where a cell actually reaches 640 px. No other task or contract depends on this file list.

**Interfaces:**
- Consumes (TD9 / TD10 DOM, `trade-detail.ts`): `div.grid-host > div.card-grid.why-grid` and `div.grid-host > div.card-grid.overview-grid`, each carrying `[style.--areas-1]`, `[style.--areas-2]`, `[style.--areas-3]`; each card in a `div.cell[data-area="<card>"]` with `style="grid-area: <card>"`; the Why tab's Context cell is `div.cell.context` holding two children (`sb-why-panel` calendar, then `sb-trade-strategy-record`).
- Consumes (TD8, `why-areas.ts`): `whyAreas(present)` and `OVERVIEW_AREAS`, whose `one` / `two` / `three` strings are the `grid-template-areas` for 1 / 2 / 3 columns. Unchanged here.
- Consumes (TD7 / TD8 cards): every card host is `:host { display: block; min-width: 0 }` with one `sb-panel` as its only element child, except `sb-trade-outcome-card` (a stack). `sb-why-panel` renders one `sb-panel` per requested section, so a one-section instance holds a single `sb-panel`.
- Produces (grid CSS contract, ledger TD11): `.grid-host { container: cards / inline-size }`; `.card-grid` uses `var(--areas-1)` by default, `var(--areas-2)` inside `@container cards (min-width: 640px)`, `var(--areas-3)` inside `@container cards (min-width: 1024px)`; `.cell { container-type: inline-size; min-width: 0 }`; each dl-bearing card's `dl` is two columns inside `@container (min-width: 640px)`. TD12 measures exactly these.

**Rules (spec § 7, amendments 1 and 3, Global Constraints "Breakpoints" and "Containers on trade-page wrappers only").**
- Only `640px` and `1024px` appear in a width query in any file this task touches; no range syntax (`width >= ...`), no EXEMPT entry.
- `container-type` sits on `.grid-host` (named `cards`) and on `.cell`; never on `sb-panel` or anything under `ui/`.
- Row levelling (`align-items: stretch`) needs the visible card to fill its stretched cell. `sb-panel` has no host display or height, so the page sets them from the call site with `:host ::ng-deep`, the `calendar.ts:355-367` precedent. It is scoped to `.cell > * > sb-panel:only-child`: a card whose host holds one panel. The Outcome card (a stack of panels) keeps its natural height inside its stretched cell rather than having its panels share the extra space unevenly.
- `.cell` becomes a one-track grid (`grid-template-columns: minmax(0, 1fr)`) so its single child, the card host, is a grid item and stretches to the row height. That makes its height definite, so `height: 100%` on the panel inside resolves.
- Context (`.cell.context`) keeps its two stacked panels: rows `auto 1fr`, so the calendar keeps its own height and the Strategy record takes what is left of the row, ending level with its row partner.
- No outer margin anywhere (spacing between cards is the grid `gap`), no hex literal, only existing tokens (`--section-gap`, `--space-20`).

**Why the specs read source.** jsdom computes no layout and evaluates no `@container` query, so the new cases pin the stylesheet text (the `ui/filter-bar.spec.ts` precedent: `readFileSync(join(process.cwd(), ...))`). TD12's Playwright pass checks the rendered result.

- [ ] **Step 1: Write the failing grid spec**

In `frontend/src/app/workspaces/trades/trade-detail.spec.ts`, add these two lines as the first two lines of the file, above `import { provideHttpClient, withInterceptors } from '@angular/common/http';`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

Then append at the very end of the file:

```ts
/* v166 TD11 -- the responsive card grid (spec § 7, amendments 1 and 3).
 * jsdom computes no layout and evaluates no @container query, so these
 * cases pin the stylesheet source (the ui/filter-bar.spec.ts precedent);
 * TD12's Playwright pass checks the rendered grid at 1440 / 1024 / 768 /
 * 390 px. */
const trades = (file: string): string =>
  readFileSync(join(process.cwd(), 'src/app/workspaces/trades', file), 'utf8');

describe('TradeDetail — responsive card grid (v166)', () => {
  const PAGE = trades('trade-detail.ts');

  it('makes the grid wrapper the container the columns respond to', () => {
    expect(PAGE).toMatch(/\.grid-host \{[^}]*container: cards \/ inline-size/);
  });

  it('lays one column below 640 px of container width, in reading order', () => {
    expect(PAGE).toMatch(
      /\.card-grid \{[^}]*grid-template-columns: minmax\(0, 1fr\);[^}]*grid-template-areas: var\(--areas-1\)/,
    );
  });

  it('switches to two columns at 640 px and three at 1024 px of container width', () => {
    expect(PAGE).toMatch(
      /@container cards \(min-width: 640px\) \{\s*\.card-grid \{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);[^}]*grid-template-areas: var\(--areas-2\)/,
    );
    expect(PAGE).toMatch(
      /@container cards \(min-width: 1024px\) \{\s*\.card-grid \{[^}]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\);[^}]*grid-template-areas: var\(--areas-3\)/,
    );
  });

  it('uses only the declared breakpoints, and no range syntax to slip past the guard', () => {
    const widths = [...PAGE.matchAll(/\((?:min|max)-width: (\d+)px\)/g)].map((match) => match[1]);
    expect(new Set(widths)).toEqual(new Set(['640', '1024']));
    expect(PAGE).not.toMatch(/\(\s*width\s*[<>]/);
  });

  it('puts each card cell in its own inline-size container, never the shared panel', () => {
    expect(PAGE).toMatch(/\.cell \{[^}]*container-type: inline-size/);
    expect(PAGE).toMatch(/\.cell \{[^}]*grid-template-columns: minmax\(0, 1fr\)/);
    expect(PAGE).not.toMatch(/sb-panel[^{}]*\{[^}]*container-type/);
  });

  it('stretches a one-panel card to its cell so paired cards end level', () => {
    expect(PAGE).toMatch(/\.card-grid \{[^}]*align-items: stretch/);
    expect(PAGE).toMatch(/:host ::ng-deep \.cell > \* > sb-panel:only-child \{[^}]*display: block;[^}]*height: 100%/);
    expect(PAGE).toMatch(/:host ::ng-deep \.cell > \* > sb-panel:only-child > \.panel \{[^}]*height: 100%/);
  });

  it('gives the Context cell rows auto then 1fr, so the Strategy record fills the row', () => {
    expect(PAGE).toMatch(/\.context \{[^}]*grid-template-rows: auto 1fr/);
    expect(PAGE).not.toMatch(/\.context \{[^}]*align-content: start/);
  });

  it('drops the auto-fit .panels rule and the dead page-level dl rules', () => {
    expect(PAGE).not.toMatch(/\.panels\b/);
    expect(PAGE).not.toMatch(/auto-fit/);
    expect(PAGE).not.toMatch(/^\s*dl \{/m);
    expect(PAGE).not.toMatch(/<dl\b/);
  });

  for (const file of ['position-card.ts', 'strategy-record-card.ts', 'level-sources-card.ts', 'scores-card.ts']) {
    it(`flows ${file}'s label/value list into two columns once its cell is 640 px wide`, () => {
      const card = trades(file);
      expect(card).toMatch(
        /@container \(min-width: 640px\) \{\s*dl \{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);[^}]*column-gap: var\(--space-20\)/,
      );
      expect(card).not.toMatch(/container-type/);
    });
  }
});
```

- [ ] **Step 2: Run the spec to verify it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts`
Expected: FAIL — only cases in the new `TradeDetail — responsive card grid (v166)` block fail: no `container: cards`, no `@container cards` queries, `.context` still `align-content: start`, `.panels` and the page `dl` rules still present, no `@container` block in the four cards (`uses only the declared breakpoints` fails on an empty set). Every other block passes. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

- [ ] **Step 3: Confirm the page-level `dl` rules are dead before deleting them**

Run: `git -C $WT grep -n -E "<dl|class=\"panels\"" -- frontend/src/app/workspaces/trades/trade-detail.ts`
Expected: no output (TD9 moved the Strategy `dl` into `strategy-record-card.ts`; TD10 deleted the Plan and Live blocks, the last users of `.panels` and of the Per share / Opened / Now / Stop to target / Partial position `dl`s). If a line prints, stop and report it: something still renders a `dl` or `.panels` and needs its own decision.

- [ ] **Step 4: Replace the grid styles in `trade-detail.ts`**

In `frontend/src/app/workspaces/trades/trade-detail.ts`, in the `styles`, replace the whole run from `.panels {` through the closing brace of the `dd { ... }` rule. It reads (TD9 inserted its block between `.panels` and `dl`):

```css
    .panels {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: var(--section-gap);
      align-items: start;
    }
    /* v166 -- the card grid the Why and Overview tabs place their cards in.
       One column here, in reading order (the phone layout); TD11 makes
       .grid-host the container and switches to --areas-2 / --areas-3 at
       640 / 1024 px of container width. The maps are computed
       (why-areas.ts) and bound as --areas-1/2/3 on the grid; each cell
       names its own grid-area. */
    .grid-host {
      min-width: 0;
    }
    .card-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: var(--areas-1);
      gap: var(--section-gap);
    }
    .cell {
      min-width: 0;
    }
    /* Two panels stacked in one cell: the calendar, then the Strategy record. */
    .context {
      display: grid;
      align-content: start;
      gap: var(--section-gap);
    }
    dl {
      display: grid;
      gap: var(--space-6);
    }
    dl > div {
      display: flex;
      justify-content: space-between;
      gap: var(--space-10);
    }
    dt {
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    dd {
      color: var(--text);
      font-size: var(--text-table);
    }
```

with

```css
    /* v166 -- the card grid the Overview and Why tabs place their cards in
       (spec § 7, amendment 1). .grid-host is the container, so the columns
       follow the width the page actually has -- sidebar open or closed,
       window dragged narrower -- not the device: 1 column below 640 px of
       container width, 2 at 640-1023, 3 at >= 1024. Only the declared
       breakpoints (ui/breakpoints.ts) appear; ui/breakpoint-guard.spec.ts
       reads @container queries too. The area maps are computed
       (why-areas.ts: a card that would render nothing is not mounted and
       its row partner takes the row) and bound as --areas-1/2/3 on each
       grid; each cell names its own grid-area. */
    .grid-host {
      container: cards / inline-size;
      min-width: 0;
    }
    .card-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: var(--areas-1);
      align-items: stretch;
      gap: var(--section-gap);
    }
    @container cards (min-width: 640px) {
      .card-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
        grid-template-areas: var(--areas-2);
      }
    }
    @container cards (min-width: 1024px) {
      .card-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
        grid-template-areas: var(--areas-3);
      }
    }
    /* Each cell is the inline-size container its card's own dl query reads
       (the card files' @container (min-width: 640px)); the containers live
       on these trade-page wrappers only, so no other admin page changes.
       A one-track grid, so the card host stretches to the row height. */
    .cell {
      container-type: inline-size;
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      min-width: 0;
    }
    /* Two panels stacked in one cell (spec § 4): the calendar at its own
       height, then the Strategy record taking the rest of the row. */
    .context {
      grid-template-rows: auto 1fr;
      gap: var(--section-gap);
    }
    /* Paired cards end level (spec § 7, amendment 3). The shared panel has
       no host display or height, so a stretched cell alone would level an
       invisible box; this call-site rule makes a one-panel card's panel
       fill its cell (the calendar.ts:355-367 precedent). The Outcome card,
       a stack, keeps its natural height. */
    :host ::ng-deep .cell > * > sb-panel:only-child {
      display: block;
      height: 100%;
    }
    :host ::ng-deep .cell > * > sb-panel:only-child > .panel {
      height: 100%;
      box-sizing: border-box;
    }
```

`.cell.context` keeps `display: grid` from `.cell`; its single track and the two rows give the stacked layout. The Journal tab's rules, `.no-detail`, `.muted-gap`, `.chart` and the rest are untouched. The comments above deliberately never put the word `sb-panel` before a rule containing `container-type` (Step 1's negative regex reads across comments).

- [ ] **Step 5: Add the two-column `dl` rule to the four dl-bearing cards**

Each block goes at the end of the component's `styles` string, directly after the line named, before the closing backtick. The query has no container name, so it reads the nearest inline-size container: the `.cell` the card sits in (Step 4).

In `frontend/src/app/workspaces/trades/position-card.ts`, after `    .row-sub { display: block; font-size: var(--text-chip); }`:

```css
    /* v166 TD11: rows flow into two columns once the card's cell (the
       trade page's .cell container) is >= 640 px wide (spec § 7). */
    @container (min-width: 640px) {
      dl { grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: var(--space-20); }
    }
```

In `frontend/src/app/workspaces/trades/strategy-record-card.ts`, after `    .decayed { margin-top: var(--space-10); color: var(--warn); font-size: var(--text-table); }`:

```css
    /* v166 TD11: rows flow into two columns once the card's cell (the
       trade page's .cell container) is >= 640 px wide (spec § 7). */
    @container (min-width: 640px) {
      dl { grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: var(--space-20); }
    }
```

In `frontend/src/app/workspaces/trades/level-sources-card.ts`, after `    li { overflow-wrap: anywhere; }`:

```css
    /* v166 TD11: rows flow into two columns once the card's cell (the
       trade page's .cell container) is >= 640 px wide (spec § 7). */
    @container (min-width: 640px) {
      dl { grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: var(--space-20); }
    }
```

In `frontend/src/app/workspaces/trades/scores-card.ts`, after `    .scores-foot { margin-top: var(--space-10); font-size: var(--text-table); line-height: 1.6; }`:

```css
    /* v166 TD11: rows flow into two columns once the card's cell (the
       trade page's .cell container) is >= 640 px wide (spec § 7). */
    @container (min-width: 640px) {
      dl { grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: var(--space-20); }
    }
```

Each card's `dl` already is `display: grid` with a row `gap` (TD7 / TD8), so the block only adds the columns. Rows flow left to right, then down; each `dl > div` keeps its own label/value layout.

- [ ] **Step 6: Run the page spec, the four card specs and the UI gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/trades/position-card.spec.ts --include src/app/workspaces/trades/strategy-record-card.spec.ts --include src/app/workspaces/trades/level-sources-card.spec.ts --include src/app/workspaces/trades/scores-card.spec.ts --include src/app/workspaces/trades/why-areas.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts`
Expected: PASS, 0 failed. `breakpoint-guard.spec.ts` sees only `640` and `1024` in the new queries; `spacing.spec.ts` finds `--space-20` and `--section-gap` defined and no outer margin; `primitives.spec.ts` finds no `.pos`/`.neg`/`.muted`/promoted class and no hex. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

Then confirm no container landed on a shared primitive and the shared components are untouched:

Run: `git -C $WT grep -n "container" -- frontend/src/app/workspaces/trades/`
Expected: lines only in `trade-detail.ts` (`container: cards / inline-size`, the two `@container cards` queries, `container-type: inline-size` on `.cell`, and comments), the four card files (one `@container (min-width: 640px)` each, plus its comment), and the new spec cases. Nothing under `why/`.

Run: `git -C $WT diff --stat main -- frontend/src/app/workspaces/trades/why/ frontend/src/app/workspaces/plans/plan-detail.ts frontend/src/app/ui/`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts frontend/src/app/workspaces/trades/position-card.ts frontend/src/app/workspaces/trades/strategy-record-card.ts frontend/src/app/workspaces/trades/level-sources-card.ts frontend/src/app/workspaces/trades/scores-card.ts
git -C $WT commit -m "feat(v166): TD11 responsive card grid -- container queries at 640/1024, stretch, two-column dl

The Overview and Why grids now answer to their own width: one column
below 640 px of container width, two at 640-1023, three at 1024 and up,
switching between the computed area maps. Each cell is its own
inline-size container, so a card's dl flows into two columns once the
cell is 640 px wide; nothing is set on the shared panel. One-panel cards
fill their stretched cell (call-site ::ng-deep, the calendar precedent),
so paired cards end level. The auto-fit .panels rule and the dead
page-level dl rules are gone.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task TD12: Playwright visual pass at 1440/1024/768/390 on local `ng serve --port 4123`

**Model:** sonnet — runs the stack and judges screenshots against the acceptance rule

**Files:**
- Modify: `docs/superpowers/plans/2026-10-16-v166-trade-detail-reorganisation_0-index.md` (records the pass under `## Progress`)
- Modify (only if the pass finds a layout defect): `frontend/src/app/workspaces/trades/trade-detail.ts`
- Scratch, git-ignored, never committed: `.superpowers/v166-td12-probe.mjs` (the layout probe below) and `.superpowers/v166-shots/` (PNG + text per shot). `.superpowers/` is in `.gitignore`.

**Interfaces:**
- Consumes (TD11 grid CSS contract): `.grid-host` is the `cards` container; `.card-grid` has 1 / 2 / 3 tracks below 640 / at 640-1023 / at >= 1024 px of `.grid-host` width; each card sits in a `.card-grid > .cell`.
- Consumes (TD5 / TD6 DOM): the strip's tiles are `sb-outcome-strip .tile[data-tile]`, siblings in one flex row; the header actions are `.actions > button[sb-button]`; the tab bar's buttons are `[role="tab"]` (`ui/layout.ts` `TabBar`).
- Consumes (`frontend/scripts/browse.mjs`, unchanged): `login --base <url>`, `shots --base <url> --out <dir> --widths 1440,1024,768,390 --path <p> [--path ...]`, its persistent profile under `%LOCALAPPDATA%\swingbot-playwright\profile` (the probe reuses it, so one sign-in serves both).
- Produces: nothing a later task reads, beyond the `## Progress` record.

**The acceptance rule (spec § 7, the partner's):** at 1440, 1024, 768 and 390 px, on a closed two-leg trade, an open or partial trade and a pending plan, **no row contains a single card narrower than the full row while empty space sits beside it, and no page scrolls sideways.** Plus `docs/claude/ui-design.md` § Checklist: touch targets at least 44 px on a phone, a wide table scrolls inside its own box, never the page.

**Data (index `## Handoff`):** the local stack serves the local database, which may lack some groups. Shoot every group it has; record each missing one as "not in the local data, covered by the production re-shot after deploy". Never edit data to manufacture a case.

**Backend note.** The API runs from the main tree (`$R/admin_ui.py`; the worktree has no `.env`), so it does not publish `risk_stop` yet (TD1 lives on the branch). On a PARTIAL trade the Plan card therefore shows no `Working stop ... (was ...)` row and no resting-stop line locally (spec Edge case "`risk_stop` null"). That changes one card's height, not the grid; the production re-shot covers the full card.

- [ ] **Step 1: Check the tools**

```bash
test -d $WT/frontend/node_modules || npm --prefix $WT/frontend ci
npm --prefix $WT/frontend exec -- playwright --version
node --check $WT/frontend/scripts/browse.mjs
```
Expected: a `Version 1.x` line and no output from `node --check`. If Playwright's Chromium is missing on this machine, `npm --prefix $WT/frontend exec -- playwright install chromium` once (`docs/claude/skills-tools.md`).

- [ ] **Step 2: Write the layout probe**

Create `$WT/.superpowers/v166-td12-probe.mjs` (git-ignored; delete it in Step 11):

```js
#!/usr/bin/env node
/**
 * v166 TD12 -- throwaway layout probe for the trade page's acceptance rule.
 *
 *   node v166-td12-probe.mjs pick    <frontendDir> <base>
 *   node v166-td12-probe.mjs measure <frontendDir> <base> <path> [<path> ...]
 *
 * Reuses browse.mjs's persistent profile, so the sign-in from
 * `browse.mjs login` carries over. One profile, one browser: never run it
 * while a browse.mjs window is open.
 */
import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { join } from 'node:path';

const [cmd, frontendDir, base, ...paths] = process.argv.slice(2);
const { chromium } = createRequire(join(frontendDir, 'package.json'))('playwright');
const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const WIDTHS = [1440, 1024, 768, 390];
const TOUCH_MIN = 44;
const STATUSES = ['CLOSED', 'PARTIAL', 'ACTIVE', 'PENDING', 'CANCELLED', 'EXPIRED'];

async function getJson(page, path) {
  return page.evaluate(async (url) => {
    const res = await fetch(url, { credentials: 'include' });
    return res.ok ? res.json() : null;
  }, `${base}${path}`);
}

async function rowsByStatus(page) {
  const out = {};
  for (const status of STATUSES) {
    const body = await getJson(page, `/api/v1/trades?status=${status}&per_page=200`);
    if (!body) throw new Error(`GET /api/v1/trades?status=${status} failed -- signed in? (browse.mjs login)`);
    out[status] = body.items;
  }
  return out;
}

/** A list row with leg_total >= 2 may be a PARTIAL plan's banked leg, so the
 *  detail endpoint decides which plan is really a closed two-leg trade. */
async function closedTwoLeg(page, closed) {
  for (const row of closed.filter((r) => (r.leg_total ?? 1) >= 2)) {
    const detail = await getJson(page, `/api/v1/trades/${row.id}`);
    if (detail?.status === 'CLOSED') return row.id;
  }
  return null;
}

async function pick(page) {
  const rows = await rowsByStatus(page);
  const first = (list, test = () => true) => list.find(test)?.id ?? null;
  return {
    closedTwoLeg: await closedTwoLeg(page, rows.CLOSED),
    closedOneLeg: first(rows.CLOSED, (r) => (r.leg_total ?? 1) < 2),
    partial: first(rows.PARTIAL),
    active: first(rows.ACTIVE),
    pending: first(rows.PENDING),
    unfilled: first([...rows.CANCELLED, ...rows.EXPIRED]),
    legacy: first(rows.CLOSED, (r) => r.origin && r.origin !== 'plan'),
  };
}

/** Runs in the page. Self-contained: Playwright ships its source text. */
function layoutReport() {
  const host = document.querySelector('sb-trade-detail');
  if (!host) return { error: 'no sb-trade-detail on the page' };
  const rowsOf = (els) => {
    const rows = new Map();
    for (const el of els) {
      const box = el.getBoundingClientRect();
      if (box.width === 0) continue;
      const key = Math.round(box.top);
      rows.set(key, [...(rows.get(key) ?? []), box]);
    }
    return [...rows.values()];
  };
  const holes = (outerEl, items, label) => {
    const outer = outerEl.getBoundingClientRect();
    return rowsOf(items).flatMap((row) => {
      const left = Math.min(...row.map((b) => b.left));
      const right = Math.max(...row.map((b) => b.right));
      const full = left <= outer.left + 2 && right >= outer.right - 2;
      return full ? [] : [`${label}: a row of ${row.length} card(s) covers ${Math.round(left - outer.left)}-${Math.round(right - outer.left)} of ${Math.round(outer.width)} px`];
    });
  };
  const sideways = [];
  for (let el = host; el; el = el.parentElement) {
    const scrolls = el === document.documentElement || /(auto|scroll)/.test(getComputedStyle(el).overflowX);
    if (scrolls && el.scrollWidth > el.clientWidth + 1) {
      sideways.push(`${el.tagName.toLowerCase()}: scrollWidth ${el.scrollWidth} > clientWidth ${el.clientWidth}`);
    }
  }
  const grids = [...host.querySelectorAll('.grid-host > .card-grid')].map((grid) => {
    const containerWidth = Math.round(grid.parentElement.getBoundingClientRect().width);
    return {
      grid: grid.className,
      containerWidth,
      columns: getComputedStyle(grid).gridTemplateColumns.split(' ').length,
      expected: containerWidth >= 1024 ? 3 : containerWidth >= 640 ? 2 : 1,
      holes: holes(grid, [...grid.querySelectorAll(':scope > .cell')], grid.className),
    };
  });
  const firstTile = host.querySelector('sb-outcome-strip .tile');
  const stripHoles = firstTile
    ? holes(firstTile.parentElement, [...firstTile.parentElement.querySelectorAll(':scope > .tile')], 'strip')
    : [];
  const smallTargets = [...host.querySelectorAll('.actions button, [role="tab"]')]
    .map((el) => ({ label: el.textContent.trim(), height: Math.round(el.getBoundingClientRect().height) }))
    .filter((target) => target.height < 44);
  return { sideways, grids, stripHoles, smallTargets };
}

function problemsOf(report, width) {
  if (report.error) return [report.error];
  return [
    ...report.sideways.map((line) => `scrolls sideways: ${line}`),
    ...report.grids.flatMap((g) => [
      ...g.holes,
      ...(g.columns === g.expected ? [] : [`${g.grid}: ${g.columns} columns at ${g.containerWidth} px of container, expected ${g.expected}`]),
    ]),
    ...report.stripHoles,
    ...(width < 640 ? report.smallTargets.map((t) => `touch target ${t.height} px < ${TOUCH_MIN}: ${t.label}`) : []),
  ];
}

async function settle(page) {
  await page.waitForFunction(() => {
    const host = document.querySelector('sb-trade-detail');
    return !!host && host.innerText.trim().length > 200 && !/Loading/.test(document.body.innerText);
  }, null, { timeout: 30_000 }).catch(() => console.error('still loading after 30s'));
  await page.waitForTimeout(1500);
}

async function measure(page) {
  let failures = 0;
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of paths) {
      await page.goto(`${base}/${path.replace(/^\//, '')}`, { waitUntil: 'load' });
      await settle(page);
      const report = await page.evaluate(layoutReport);
      const problems = problemsOf(report, width);
      failures += problems.length;
      const columns = (report.grids ?? []).map((g) => `${g.grid.split(' ').pop()}=${g.columns}@${g.containerWidth}px`).join(' ');
      console.log(`${problems.length ? 'FAIL' : 'PASS'} ${path} @${width} ${columns}${problems.map((p) => `\n  - ${p}`).join('')}`);
    }
  }
  return failures;
}

const context = await chromium.launchPersistentContext(PROFILE, { headless: true, viewport: { width: 1440, height: 900 } });
try {
  const page = context.pages()[0] ?? (await context.newPage());
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  if (cmd === 'pick') console.log(JSON.stringify(await pick(page), null, 2));
  else if (cmd === 'measure') process.exitCode = (await measure(page)) ? 1 : 0;
  else throw new Error(`unknown command ${cmd}`);
} finally {
  await context.close();
}
```

Check it parses:

```bash
node --check $WT/.superpowers/v166-td12-probe.mjs
```
Expected: no output, exit 0.

- [ ] **Step 3: Start the local stack**

Each is a long-running process: start it with the Bash tool's `run_in_background`, never with `&`, and watch its output for the ready line.

```bash
python $R/admin_ui.py
npm --prefix $WT/frontend exec -- ng serve --port 4123
```

- `admin_ui.py` is the API `ng serve` proxies to (`frontend/proxy.conf.json` -> `http://localhost:1234`), run from `$R` (see the Backend note). If it exits (no database reachable, a missing setting), stop and report `BLOCKED:` with its last log lines; never point the proxy anywhere else.
- `:4123` is this repo's `ng serve` port. If it is taken (another session serving), use `--port 4124` and write `4124` for `4123` in every command below.
- Ready when `ng serve` prints `Local: http://localhost:4123/`.

- [ ] **Step 4: Find the URL prefix the dev server answers on**

`angular.json` stamps `baseHref: /app/`; production serves the workspace routes at the root as well. Ask the dev server which form it answers:

```bash
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://localhost:4123/trades
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://localhost:4123/app/trades
```
Expected: at least one prints `200 text/html`. Write `$P` for its prefix below: empty when `/trades` answers 200 HTML, `app/` otherwise. (Paths are written without a leading slash: Git Bash rewrites `/trades/...`.)

- [ ] **Step 5: Sign in once**

```bash
node $WT/frontend/scripts/browse.mjs login --base http://localhost:4123
```
Tell the controller the browser window is waiting: the partner types the local admin login into it (never scripted, asked for or stored). `Signed in.` on stderr ends the step; the window closes and frees the profile for the probe.

- [ ] **Step 6: Pick the trades**

```bash
node $WT/.superpowers/v166-td12-probe.mjs pick $WT/frontend http://localhost:4123
```
Expected: a JSON object with `closedTwoLeg`, `closedOneLeg`, `partial`, `active`, `pending`, `unfilled`, `legacy`, each an id or `null`. The acceptance set is `closedTwoLeg` (fall back to `closedOneLeg` when null), `partial` (fall back to `active`), and `pending`. `unfilled` and `legacy` are extra cases (Review Focus 2 and 3) shot when present. Write down which acceptance groups are `null`: they go into the record in Step 10.

Build the path list from the non-null ids, in this order, each as `"${P}trades/<id>"` and `"${P}trades/<id>?tab=why"`: closed, open/partial, pending, unfilled, legacy. Add `"${P}trades/<closed id>?tab=journal"` and `"${P}trades/<closed id>?tab=chart"` once, for the sideways-scroll check on the two tabs without a card grid. Write the list as `PATHS` below (each path its own quoted argument).

- [ ] **Step 7: Measure the acceptance rule**

```bash
node $WT/.superpowers/v166-td12-probe.mjs measure $WT/frontend http://localhost:4123 PATHS
```
Expected: one `PASS <path> @<width> overview-grid=<n>@<w>px` (or `why-grid=...`) line per path and width, exit code 0, and the column counts follow the container width: 3 at >= 1024 px of container, 2 at 640-1023, 1 below 640 (roughly 3 at a 1440 viewport, 2 at 1024 and 768, 1 at 390, with the sidebar in its default state). Each `FAIL` line lists its problems:
- `scrolls sideways: ...`: the page (or the shell's scroll pane) is wider than the viewport. A table inside a card's `.table-scroll` does not count, the probe only walks from the page host up.
- `<grid>: a row of N card(s) covers a-b of W px`: a row ends short of the grid edge, which is the partner's rule broken (a lone narrow card beside empty space).
- `<grid>: N columns at W px of container, expected M`: the container query is not switching.
- `strip: a row of N card(s) ...`: a strip row leaves a gap (the strip's flex tiles should always fill).
- `touch target H px < 44: <label>` (390 only): a header action or a tab is too small to tap.

- [ ] **Step 8: Take the screenshots and judge them**

```bash
node $WT/frontend/scripts/browse.mjs shots --base http://localhost:4123 --out $WT/.superpowers/v166-shots --widths 1440,1024,768,390 PATHS_AS_FLAGS
```
where `PATHS_AS_FLAGS` is every path of Step 6 preceded by `--path` (`--path "trades/<id>" --path "trades/<id>?tab=why" ...`). Expected: one `<slug>@<width>.png` and `.txt` per path and width under `$WT/.superpowers/v166-shots/`.

Open every PNG with the Read tool. Per shot, write one line: path, width, columns seen, and yes/no for each of
- a row holding a single card narrower than the row, with empty space beside it;
- sideways scroll (content cut at the right edge, a horizontal scrollbar on the page);
- paired cards in a row ending at different heights (a one-panel card that did not stretch; the Outcome card may end short of its cell, by design);
- clipped or overlapping text in the identity line, the strip or a card;
- header action buttons on a row of their own at 390 (spec § 1: they wrap under the chips, never alone).

- [ ] **Step 9: Fix a layout defect, if one was found**

A grid, cell or stretch defect the probe or shots show is fixed in `frontend/src/app/workspaces/trades/trade-detail.ts`, with only the allowed breakpoints (640 / 1024, Global Constraints). The 2026-10-17 visual amendment below permits one separate confidence-row fix in `why/why-panel.ts` and its focused spec. Neither fix edits `ui/` or card markup. After each page fix:

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts`
Expected: PASS, 0 failed (update a TD11 source-pinning case in the same commit only when the fix changes the very rule it pins, and say so in the commit body).

```bash
git -C $WT add frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git -C $WT commit -m "fix(v166): TD12 <what the shots showed, in one line>

<the probe or shot line that showed it, and what the rule now does>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Then re-run Steps 7 and 8 for the affected paths. For a cause inside a shared component other than the approved `WhyPanel` confidence-row exception, stop and report the probe line and PNG path to the controller as `BLOCKED:`.

- [ ] **Step 10: Get the partner's sign-off**

Report to the controller in one message: the absolute PNG paths (`$WT/.superpowers/v166-shots/...`), the probe's output from the last Step 7 run, the per-shot lines from Step 8, any fix commit, and the acceptance groups missing from the local data. The controller asks the partner (`AskUserQuestion`, recommended option first: "Signed off") and passes back the answer. Without "Signed off", the task is not done: fix what the partner names (Step 9), re-measure, re-shoot, ask again.

- [ ] **Step 11: Record the pass and stop the stack**

In `$WT/docs/superpowers/plans/2026-10-16-v166-trade-detail-reorganisation_0-index.md`, under `## Progress`: if the body is still the line `Not started. Update this block when a phase closes.`, replace that line; otherwise keep what is there and add below it:

```markdown
- **Phases 1-4 and TD11 (TD1-TD11):** done on branch `2026-10-16-v166-trade-detail-reorganisation`.
- **Visual pass (TD12), <YYYY-MM-DD>:** local `ng serve` on :4123 against the local database, at 1440 / 1024 / 768 / 390 px. Shot: <closed two-leg <id> | closed one-leg <id>>, <partial <id> | active <id>>, <pending <id>>, <unfilled / legacy ids, if any>; Overview and Why each, Journal and Chart once. Probe: every line PASS; columns <3/2/2/1 or what was seen> per width. <No fix needed | fix commit <sha>: one line>. Not in the local data, covered by the production re-shot after deploy: <groups, or "none">. Signed off by the partner in chat on <YYYY-MM-DD>.
- **Next:** TD13, the full suite.
```

and append to `## Handoff`:

```markdown
- **After deploy (from TD12):** re-shoot production with `node frontend/scripts/browse.mjs shots --out <dir> --widths 1440,1024,768,390 --path "trades/<SPCX id>" --path "trades/<SPCX id>?tab=why"` (the closed two-leg SPCX trade whose id starts `f48c80e2`, spec Status line; `browse.mjs api --path "api/v1/trades?ticker=SPCX"` finds it) plus an open/partial trade and a pending plan, and check the same rule; production publishes `risk_stop`, so the PARTIAL Plan card's working-stop row and resting-stop line show there for the first time.
```

Stop the two background processes (`admin_ui.py`, `ng serve`), then remove the probe (the shots stay in the ignored `.superpowers/v166-shots/` for the controller):

```bash
rm $WT/.superpowers/v166-td12-probe.mjs
git -C $WT status --short
```
Expected: `git status` lists only the index file (and `trade-detail.ts` / its spec only if a Step 9 fix is still uncommitted, which it must not be).

- [ ] **Step 12: Commit**

```bash
git -C $WT add docs/superpowers/plans/2026-10-16-v166-trade-detail-reorganisation_0-index.md
git -C $WT commit -m "docs(v166): TD12 visual pass recorded -- 1440/1024/768/390, partner sign-off

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

#### TD12 visual amendment, approved 2026-10-17

The first local pass used the existing `swingbot_prod_replica` through a
process-only API connection. Its data supplied closed, partial and cancelled
trades, but no pending plan; no records were changed. Across 48 page and width
combinations the area-map column counts matched the container widths, with no
grid holes or page overflow. The Back link was below the phone touch-target
height and was corrected in `trade-detail.ts` with a focused regression.

The screenshots also revealed overlapping confidence-factor labels and notes
inside the shared `WhyPanel` at 390–1024 px. The partner approved a direct,
scoped correction to `why/why-panel.ts` and its spec before merge. This is the
only exception to the shared `why/` exclusion above. Re-run the focused Why
spec, plan-detail spec and five UI gates, then re-shoot Why at all four widths
for the closed, partial and cancelled local cases. Check the affected rows for
overlap in the PNGs and by DOM geometry. Keep the pending case marked absent for
the after-deploy re-shot.

The local replica's stale scan banner covers the Back link at every tested
width. That shell/data condition remains a recorded limitation; it does not
alter the trade grid and is outside this plan's code scope.

### Task TD13: Full Python suite, whole frontend spec run, radon check

**Model:** haiku — runs commands, no code

**Files:**
- None created or modified. A failure found here is fixed by the task that owns the file (see Step 6), never by this task.

**Interfaces:**
- Consumes: every commit TD1-TD12 made on branch `2026-10-16-v166-trade-detail-reorganisation`.
- Produces: the plan's one full-suite verdict, reported to the controller (the gate `/close-out` reads).

Run this only when `git -C $WT status --short` prints nothing and TD12's sign-off is recorded. This is the plan's single full-suite run (Global Constraints: per-task runs are narrow); a failure is fixed and re-run **alone**, never by re-running the whole suite.

- [ ] **Step 1: Confirm the tree is clean and the plan's commits are on the branch**

```bash
git -C $WT status --short
git -C $WT log --oneline main..HEAD
```
Expected: no output from `status`; `log` lists the TD1-TD12 commits (TD12's `docs(v166): TD12 visual pass recorded ...` last, after any `fix(v166): TD12 ...`).

- [ ] **Step 2: Run the full Python suite**

Dispatch the `test-runner` subagent (so the output stays out of this context) with the command:

Run: `python $WT/scripts/dev/testrun.py full`
Expected: `0 failed` and `0 xfailed` (a changed pass count is not a failure, `docs/claude/testing-cost.md`). The suite includes `tests/admin/test_exit_reason_labels.py` and the `risk_stop` cases in `tests/admin/test_api_v1_trades.py` and `tests/admin/test_trades_partial_row.py` (suite `admin`, path-based; `tests/suites.toml` unchanged).

- [ ] **Step 3: Run the whole frontend spec suite and the production build**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false`
Expected: every spec file passes, 0 failed, including the updated `why-panel.spec.ts`, unchanged other `why/*.spec.ts`, `workspaces/plans/plan-detail.spec.ts`, and the five UI gate specs. A 60 s `Timeout waiting for worker ... no tests` with nothing run is machine load: re-run once (`docs/claude/testing-cost.md` § Frontend).

Run: `npm --prefix $WT/frontend run build`
Expected: the build completes with no error (CI's `frontend-test` job runs the same build after the specs; a bundle-budget error here would fail CI).

- [ ] **Step 4: Check Python complexity did not get worse**

```bash
git -C $WT show main:swingbot/admin/api_v1/trades.py > $WT/.superpowers/v166-trades-main.py
python -m radon cc -s -n C $WT/.superpowers/v166-trades-main.py | sed -E 's/ [0-9]+:[0-9]+ / /' | tail -n +2 > $WT/.superpowers/v166-radon-main.txt
python -m radon cc -s -n C $WT/swingbot/admin/api_v1/trades.py | sed -E 's/ [0-9]+:[0-9]+ / /' | tail -n +2 > $WT/.superpowers/v166-radon-branch.txt
diff $WT/.superpowers/v166-radon-main.txt $WT/.superpowers/v166-radon-branch.txt && echo "radon: unchanged"
python -m radon cc -s -n C $WT/tests/admin/test_exit_reason_labels.py
rm $WT/.superpowers/v166-trades-main.py $WT/.superpowers/v166-radon-main.txt $WT/.superpowers/v166-radon-branch.txt
```
Expected: `radon: unchanged` (the same functions at the same grades and scores, `_row_from_plan` still `C (15)`; line numbers are stripped because TD1 shifts them; `tail` drops the file-name line, which differs), and no output for the new test file (every function below C).

- [ ] **Step 5: Check the files the plan must not touch**

```bash
git -C $WT diff --name-only main -- frontend/src/app/workspaces/trades/why/
git -C $WT diff --stat main -- frontend/src/app/workspaces/plans/plan-detail.ts frontend/src/app/workspaces/trades/trade-actions.ts frontend/src/app/ui/ tests/suites.toml VERSION.json
```
Expected: the first command lists only `why/why-panel.ts` and `why/why-panel.spec.ts`; the second prints nothing (`plan-detail.ts`, `trade-actions.ts`, `ui/`, the suite map and the version file remain untouched; the bump is `/close-out`'s).

- [ ] **Step 6: If anything failed**

Do not re-run the full suite. Report to the controller the failing test id (Python `path::test`, or the frontend spec file and case name), its error, and which task's files it touches (index task ledger). The controller dispatches the fix at that task's `Model:` tier; afterwards re-run only the failing test:
- Python: `python $WT/scripts/dev/testrun.py file <tests/...py>`;
- frontend: `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>` (plus the five UI gate specs if a non-spec frontend file changed).

Then repeat Steps 4 and 5 only if the fix touched `trades.py` or a shared path.

- [ ] **Step 7: Report the verdict (no commit)**

This task commits nothing. Confirm:

```bash
git -C $WT status --short
```
Expected: no output. Report to the controller: the Python summary line (`N passed, 0 failed, 0 xfailed`), the frontend summary line (`Test Files N passed`, `Tests N passed`), `build` OK, `radon: unchanged`, the empty diff of Step 5, and any fix made under Step 6 with its commit. The plan is then ready for `/close-out` (bump `ui minor; bot none` from the index header) and the production re-shot recorded in `## Handoff`.
