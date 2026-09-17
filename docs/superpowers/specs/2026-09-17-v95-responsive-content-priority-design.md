Version: ui 1.18.3 · bot 1.9.2
Bump: ui minor · bot none
Edge: none (integrity)
Depends on: nothing. Hands one requirement to v94 (§11), which must land the
Analytics adoption this spec deliberately excludes.

# v95 — Responsive content priority: one declaration, three demotion ladders, parity by test

## 1. Why

The admin UI has four declared breakpoints, a `ViewportService` that exposes
`isPhone()` and `isNarrow()`, and a tokens layer that already raises every
`--control-h`-sized control to 44px under a coarse pointer. The scaffolding is
good. The adoption is not: 28 files across a shell, ten workspaces and a full
primitive set carry hand-rolled `@media` blocks, no two alike, and the rest
carry none.

Audited live on production at 390px, 768px and 1024px on 2026-09-17. Everything
below was **observed on screen**, not inferred from CSS.

### 1.1 The tablet band does not exist

At 768px — iPad portrait — the Dashboard's portfolio value renders as four
broken fragments: `99` / `€` / `0.0` / `tod`. The figure is `997,291.88 €`. The
30-day equity sparkline beside it disappears entirely.

The cause is a gap, not a bug in any one rule. `trading-performance.ts:114`
provides a mobile treatment below **640px**; the workspace grids reflow at
**1000px**. Between those two numbers the desktop layout renders in a space that
cannot hold it, and the KPI grid's `repeat(4, minmax(140px,180px))` — a 560px
hard floor — wins the space fight against the equity block. `REALISED TODAY`
wraps its currency symbol onto a second line for the same reason.

Every tablet in portrait lands in this gap. It is the most broken width in the
application and the least deliberately designed.

### 1.2 On phones, chrome buries content

**Trades at 390px** requires roughly 1,700px of scrolling before the first trade
row. Above it, stacked vertically and all expanded by default: two destructive
buttons (`Clear open`, `Clear history`), a Compact/Full toggle, eight filter
chips, a date range, `Export CSV`, a `Columns 12/29` picker, eight filter
selects, a rows-per-page selector and a pagination bar. The top ~450px is
near-empty, because the control bar places one right-aligned item per row and
pads the left with nothing.

**Calendar at 390px** repeats the shape: filters plus six stat tiles push the
month grid — the reason the page exists — past 1,400px.

### 1.3 Tables hide the columns that matter

Open Positions at 390px shows `#`, `STATUS`, `TICKER`, `CONFIDENCE`. It hides
`NOW`, `PLAN`, `P&L %`, `R`, `HELD` and `OPENED` off the right edge, behind a
horizontal scroller. The columns a trader would open a phone to check are
precisely the hidden ones, while a progress bar consumes ~40% of the width.

`data-table.ts:360` adds a sort `<select>` and pins the row's identity column
below 639px. `td.num { white-space: nowrap }` (`:275`) guarantees the scroller
engages. Trades offers 29 columns through the same component.

**This is v80's design, not an oversight.** v80 D4 ("`sb-data-table` phone mode,
card mode replaced", shipped `ccd57608`, 2026-09-10) deliberately removed card
mode in favour of the pinned identity column and sort select, and removed
`.card`, `.card-head`, `.card-body`, `.card-value` and `.card-actions` with it.
Its test `'keeps the table below the breakpoint -- no cards'` is the record of
that decision. v95 does not reverse it — see §4.1.

What v80 left behind is debris, and that part is a real defect: `--cell-wrap`
and `--sep-wrap` are no longer set by anything, while `dashboard.ts:511-521`
still sets `white-space: var(--cell-wrap, nowrap)` and still cites "DataTable's
card-mode wrap contract (see its `.card-value` block)". The widest cell on the
page is permanently `nowrap` behind a comment describing machinery that was
deleted. `data-table.ts:461` likewise still claims "Cards instead of a table,
below `sm` — spec v18 Decision 9", which v80 superseded.

### 1.4 Smaller, confirmed

- **Status tabs lose their counts on phone.** Desktop reads
  `Open 6 · Pending 0 · Partial 0 · Closed 3 · Cancelled 0`. Phone renders five
  bare glyphs with no labels and no numbers. Accessible names survive; the
  visible information does not.
- **Duplicate pagination.** Six rows are bracketed by two complete six-control
  pagination bars — roughly 250px of vertical space, more than the rows.
- **Panel order inverts the wrong way.** At 768px the Dashboard correctly leads
  with the summary. At 390px `dashboard.ts:527` reorders to put Open Positions
  first, pushing every headline number below a very tall table.
- **Destructive actions sit under the thumb.** `Close all open/partial` is
  prominent at phone width; `Clear open` / `Clear history` are the first things
  on Trades.
- **The market tape is permanently clipped**, rendering `MKT | 11.00 | D ⏱20:42`.
  It carries four indices and has room for about one.
- **Breakpoint drift.** `shell.css:374` and `:377` branch at 900px and 720px —
  values matching none of the four declared breakpoints. The stylesheet and
  `ViewportService.isNarrow()` can therefore disagree about what "narrow" means,
  which is exactly the defect `breakpoints.ts`'s own docstring warns about.
- **Touch-target opt-outs.** `button.ts:129` (`:host(.chip)`) and `:163`
  (`:host(.link)`) set `min-height: 0`, explicitly discarding the 44px floor that
  `tokens.css:294-300` provides. Downstream: chips ~28px (`chip.ts:126`),
  column-picker rows ~26px (`column-picker.ts:118`), settings reset/restart ~20px
  (`settings-tab.ts:512,527`), `control-bar.ts:48` `.clear` ~16px.

### 1.5 What already works

Three places solve this correctly and are the models the rest should copy:

- `earnings-calendar.ts:180-195` collapses a seven-column grid into an agenda
  list on phone. The main Calendar (`calendar.ts:361`) never received the same
  treatment and keeps `repeat(7, minmax(0,1fr))` at every width.
- `analytics.ts:1264` uses `minmax(min(100%, 360px), 1fr)`. That `min(100%, …)`
  idiom is what keeps `risk.ts:534` (`minmax(300px,1fr)`) and
  `settings-tab.ts:403` (`minmax(260px,1fr)`) from overflowing at 320px.
- `tokens.css:294-300` already raises `--control-h`/`--row-h` to 44px and
  `--text-control` to 16px under `(pointer: coarse), (max-width: 639px)`. Every
  touch defect in §1.4 is a component opting *out* of a floor that exists.

## 2. Non-goals

- **The Analytics workspace.** v94 rebuilds it across 36 tasks and explicitly
  defers responsive work (its spec, line 301-302). Adopting this model there
  now would be thrown away. §11 hands v94 the requirement instead.
- **A visual redesign.** Type scale, palette, spacing tokens and iconography are
  unchanged. This spec reorganises what appears where, not how it looks.
- **A general layout engine.** Three concrete ladders, not an abstraction that
  could express arbitrary layouts. See §4.
- **Backend, bot or API changes.** `Bump: bot none`.
- **New breakpoints.** The four in `breakpoints.ts` are correct and stay. The
  work is making the stylesheets honour them.

## 3. The declaration

One field, on every displayable thing:

```ts
/** The narrowest viewport at which this item appears inline. */
inlineFrom: Viewport;   // 'xs' | 'sm' | 'md' | 'lg' | 'xl'
```

`inlineFrom: 'xs'` means always inline. `inlineFrom: 'md'` means inline from
1024px up and **demoted** below it — never removed, never hidden.

This reuses the existing `Viewport` union and `viewportFor()` unchanged. There is
no second scale, no numeric rank, and nothing to reconcile with the breakpoints
already declared. The resolver is pure, so it tests headless exactly as
`breakpoints.ts` does today.

## 4. The three ladders

Demotion is a promise about *reachability*, so every demoted thing has a named
destination. Three kinds, three destinations:

| Kind | Demoted to |
|---|---|
| **Column** | the row's existing `expansion` template |
| **Control** | the toolbar's filter sheet |
| **Panel** | collapsed in place — title, one-line digest, chevron |

A stat tile is a panel. Calendar's six tiles and the Dashboard's KPI tiles
declare `inlineFrom` and collapse to a digest like any other panel, which is why
no fourth ladder is needed for fields inside a panel.

Three concrete ladders rather than one engine. This boundary is deliberate: each
ladder is independently reviewable and independently revertable, where a general
engine would have to be understood whole before any of it could be trusted.

### 4.1 Columns → the row's existing expansion

Below its `inlineFrom`, a column leaves the grid and renders in the row's
detail expansion instead. **No cards.** `DataTable` already takes an
`expansion` input (`TemplateRef<RowContext<T>>`), and v80's pinned identity
column and phone sort select stay exactly as they are; `inlineFrom` decides
only which columns render inline and which move into that expansion.

For Open Positions the inline `xs` set is ticker, P&L% and R — not the progress
bar that currently occupies 40% of the width, which demotes.

This reaches the same destination the ladder names using machinery that is
already shipped and tested, and reverses no part of v80 D4. Cards may still be
the better rendering on a 390px screen; that question is deferred to its own
spec rather than settled by assertion here (§13).

The stale debris goes with this task: delete `--cell-wrap`/`--sep-wrap` and the
comments at `dashboard.ts:511-521` and `data-table.ts:461` that describe
removed machinery.

### 4.2 Controls → the filter sheet

Below its `inlineFrom`, a control moves into one sheet per toolbar, opened from a
single button. The button carries a badge counting demoted controls that are
**active** — see §5.

This is what collapses Trades' 1,700px of chrome without removing one control.

### 4.3 Panels → collapsed with a digest

Below its `inlineFrom`, a panel renders as its title, a one-line digest and a
chevron, expanding in place on tap. Collapsed state is per-viewport and per-
session; it is not persisted across reloads.

Each collapsible panel must supply a digest that answers the panel's own
question in one line. `MARKET MOVERS` collapsed reads `no priced symbols yet`,
not `—`. A panel with no meaningful digest is not a candidate for collapse and
declares `inlineFrom: 'xs'`.

Panels additionally declare `order` per band, which is how the Dashboard leads
with the summary at every width instead of only at 768px.

## 5. Honesty guards

The model's failure mode is hiding something that changes what the numbers mean.
Three guards, all testable:

1. **Active demoted controls are counted.** The sheet button shows how many
   demoted controls are non-default. A filter you cannot see that is narrowing
   your data is a correctness bug, not a layout preference.
2. **Panels force-expand over a problem.** If a panel's data is stale, errored,
   or scoped to something unrepresentative, it expands regardless of
   `inlineFrom`. A collapsed digest reading `—` above a failing panel is
   precisely the defect the UX seat exists to refuse.
3. **Demotion never drops an accessible name.** The status tabs already prove
   this can go wrong visually while the a11y tree stays intact; the reverse must
   not happen.

## 6. Components

**New — `frontend/src/app/ui/priority.ts`**
The `inlineFrom` type, the pure resolver (`isInline(inlineFrom, viewport)`), the
digest contract, and the registry types the parity gate walks. Pure; no Angular
dependency beyond the `Viewport` import.

**`ui/data-table/`** — per-column `inlineFrom`, routing demoted columns into the
existing `expansion` template. Retires the dead `--cell-wrap`/`--sep-wrap`
references and the two superseded comments. **Keeps v80 D4 intact**: the pinned
identity column, the phone sort `<select>`, and the
`'keeps the table below the breakpoint -- no cards'` test all stay.

**`ui/control-bar.ts` + `ui/filter-bar.ts` → one toolbar** — owns the sheet and
the active badge. `filter-bar.ts` is already marked deprecated in favour of
`sb-segmented`; this finishes that migration rather than adding a third pattern.

**`ui/panel-grid.ts`** — per-band `order`, collapse with digest, the
force-expand guard.

**Unchanged and kept:** `tape.css` and `earnings-calendar.ts` keep their bespoke
media queries; both are genuinely special-cased and both already work.

## 7. Workspace adoption

Adoption is declaration, not styling: a workspace sets `inlineFrom` on a column
and deletes its hand-rolled media query. The 28 scattered `@media` blocks shrink
to the handful that earn their keep.

Eight workspaces, one task each, ordered by observed pain:

| # | Workspace | Principal work |
|---|---|---|
| 1 | `trades` | toolbar sheet (the 1,700px), `inlineFrom` over 29 columns, destructive-action placement |
| 2 | `dashboard` | the 768px equity collapse, panel order at `xs`, duplicate pagination, tab counts |
| 3 | `calendar` | stat tiles → digest, month grid → agenda at `xs` (copy `earnings-calendar.ts`) |
| 4 | `watchlist` | column `inlineFrom`, toolbar; keep v80's `symbol` identity pin |
| 5 | `risk` | `minmax(300px,1fr)` → `min(100%, …)`, `matrix.ts` sticky row headers |
| 6 | `system` | `settings-tab.ts` touch targets and `.fields` overflow; `scan-tab`/`logs-tab` have no narrow rules at all |
| 7 | `versions` | the hard-coded `4.5rem` lane rail inside `overflow:hidden`, which clips silently |
| 8 | `gallery` | demo surface; add the new primitives' states |

## 8. Cross-cutting fixes

Done first, because everything downstream assumes the breakpoints are truthful:

- `shell.css:374,377` — 900px/720px → the declared breakpoints.
- The 640–1024 tablet band, across `trading-performance.ts` and the workspace
  grids currently reflowing at 1000px.
- Remove the `min-height: 0` opt-outs in `button.ts:129,163` and the ~6 call
  sites that inherit them, restoring the 44px floor `tokens.css:294` provides.
- `histogram.ts:88` — `min-width: 0` + ellipsis on `.label`, whose callers feed
  it strings far longer than its `4rem` track.
- `recent-activity.ts:54` — `min-width: 0` on `.detail`.

## 9. The parity gate

A spec test walks every registered column, control, panel and field, and asserts
each is reachable at all five viewports — inline, or through a named
disclosure. It fails on any item whose demotion destination does not exist or is
itself demoted.

This is what makes "full parity" a gate rather than an aspiration, and it sits
alongside the tests this repo already keeps for exactly this purpose:
`breakpoints.spec.ts`, `tokens.spec.ts`, `workspace-consistency.spec.ts`.

## 10. Verification

- **Per task:** `python scripts/dev/testrun.py file <the touched spec>`, plus a
  screenshot pass at 390 / 768 / 1024 via the connected Chrome DevTools MCP.
  The audit that produced §1 found defects the suite does not catch; the visual
  pass is not optional on a workspace task.
- **Per plan part:** `python scripts/dev/testrun.py fast`.
- **Once, as the plan's final task:** `python scripts/dev/testrun.py full`.
  Green means `0 failed` and `0 xfailed`.

## 11. Handoff to v94

v94's spec must gain one requirement: the Analytics workspace adopts
`inlineFrom` and the three ladders as it is rebuilt, rather than inheriting the
pre-v95 pattern. Its current non-goal "mobile-first layout beyond the existing
breakpoints" is amended to name this spec. Without that amendment Analytics is
the one workspace the parity gate cannot cover.

## 12. Risks

- **Step 2 has app-wide blast radius.** Between the primitives landing and the
  last workspace adopting, the app is more broken than today, in ways the suite
  may not catch. Mitigated by the per-task visual pass (§10) and by the eight
  workspace tasks being independently revertable.
- **Routing columns into the expansion changes an interaction**, though less
  than cards would: a value that was visible after a sideways scroll now needs a
  row tap. Trades is where this bites hardest at 29 columns, and it should be
  looked at on a real device before Trades merges.
- **This spec reads v80 as settled and builds on it.** If v80 D4 turns out to
  have been provisional rather than decided, §4.1 is the task to revisit, and
  §13 is the place that argument belongs.
- **Line references in §1 and §8 are as of the 2026-09-17 audit.** They must be
  re-verified at implementation time — several files are large and actively
  edited. The `symbol-verifier` subagent exists for this.
- **`filter-bar.ts` has live call sites.** Converging it into the toolbar is a
  migration, not a deletion; call sites move in the workspace tasks that own
  them, not in the primitives task.

## 13. Deferred: cards vs pinned column, on evidence

v18 Decision 9 specified cards on phones. v80 D4 replaced them with the pinned
identity column and shipped that. Neither decision was taken against a measured
comparison, and this spec deliberately does not settle it — it builds on v80
because v80 is what is shipped, not because cards were shown to be worse.

That comparison gets its own spec, written after v95's plan and run once v95's
`inlineFrom` declarations exist (they are the input either rendering needs):

- **The question.** On a 390px viewport, does a trader find a named value on a
  Trades row faster and more accurately with (a) v80's pinned column plus
  sideways scroll, (b) v95's pinned column plus row expansion, or (c) cards?
- **Pre-registered before looking:** the tasks, the rows, and what result would
  change the decision. A comparison that decides its threshold afterwards is not
  a comparison.
- **The honest null.** "No detectable difference, keep v80" is a complete and
  publishable answer, and the most likely one.

Until that spec closes, v80 D4 stands and §4.1 is the implementation.
