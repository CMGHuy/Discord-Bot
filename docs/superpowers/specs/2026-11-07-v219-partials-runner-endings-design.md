# v219 — Partials tab: runner endings (cards, scorecard, odds)

**Version:** ui 1.40.3 · bot 2.17.3
**Bump:** ui minor · bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** quant-researcher, staff-engineer, financial-advisor

## Why

The partner wants to see how the **runner** (the part of a position left
open after TP1) performs, ending by ending: how often it reaches **TP2**,
how often it comes back to **breakeven**, how often it **gives back** a
good move, and how often the **trailing stop** closes it. They also want
the R behind each ending. Today the Partials tab (v142,
`frontend/src/app/workspaces/analytics/tabs/partials.ts`) answers part
of this in its "Runner outcome mix" panel: count, share and average
runner R per close reason. It has no giveback category, no
best-R-before-exit, no "how close to TP2", no conditional odds and no
time per ending.

**It is statistics only.** The partner was explicit: nothing about how
the runner is managed changes. That is why `Edge:` is `none (integrity)`.
The section measures the existing exit rules so a later, separately
screened change can be argued from numbers. It is not that change.

## Goals

1. One **Runner endings** section in the Partials tab, in layout **C**
   (chosen by the partner from mockups on 2026-11-07). It replaces the
   "Runner outcome mix" panel and has three parts, in this order:
   - **Four ending cards:** Runner at TP2 · Runner at breakeven ·
     Giveback · Trailing stop. Each shows share (%) and count.
   - **Scorecard table:** one row per ending, every statistic below as a
     column.
   - **Odds chart:** of runners that reached a level, how they ended.
2. The scorecard rows, in this order: **TP2**, **Trailing stop**,
   **Breakeven**, **↳ Giveback**, **Other** (stall + time + manual +
   `other`).
3. The scorecard columns:

   | Column | Definition |
   |---|---|
   | N | runners in the row |
   | Share | N ÷ runners in the section (see Population), % |
   | Avg R / Med R | mean / median **runner** R (`PartialTrade.r_runner`) |
   | Total R | sum of runner R, weighted by the runner fraction, so it is what the row added to the book in R. Runner R alone overstates a ⅓ runner. |
   | vs all-out | mean `PartialTrade.delta_r` (blended R minus closing everything at TP1, already defined in `partials.py`) |
   | Best R seen | mean `runner_path["mfe_r"]`, the best R the trade reached from TP1 to the runner's close, measured from entry (see "Progress to TP2") |
   | % to TP2 | mean **progress to TP2** per runner (defined below), as % |
   | Giveback | mean `max(0, mfe_r − r_runner)`. Clamped at 0, because a manual close's synthesised exit can sit above a stamp that never saw it. |
   | Sessions | median `hold_tp1_exit` (trading sessions from TP1 to the runner's close) |

4. The **odds chart**: for progress levels **25%, 50% and 75% of the way
   to TP2**, take the runners whose progress reached the level. Show how
   that group split across TP2 / trailing stop / breakeven / other, with
   the group N on each bar.

## Definitions (the partner's)

- **Progress to TP2:** how far the runner got from TP1 towards TP2,
  `(mfe_r − r_tp1) ÷ (tp2_r − r_tp1)`, clamped to [0, 1].
  - `tp2_r` is the plan's TP2 in R, on the same initial entry/stop basis
    as `r_multiple` and `_one_leg_r`.
  - Why not plain R: `runner_path.mfe_r` is measured from entry and is
    floored at `r_tp1` (`runner_path.py::_summarise`). TP1 already sits
    near +1R or above, so a "+1R reached" test is true of every runner.
    Progress also compares fairly across plans whose TP2 sits at
    different R. *(Partner, 2026-11-07, after the builder check found
    the floor.)*
  - A plan whose `tp2_r ≤ r_tp1` has no TP1→TP2 distance. It is left out
    of every progress figure, with the count shown.
- **Giveback:** a runner whose progress reached **≥ 50%** and that closed
  with `r_runner ≤ 0` (breakeven or worse).
- **Breakeven:** close reason `tp1_runner_be` (bucket `floor`).
- **Trailing stop:** close reason `tp1_runner_trail` (bucket `trail`).
- **TP2:** close reason `tp1_runner_tp2` (bucket `tp2`).

## Population

- Closed runners only. Open runners are excluded, as in every other
  runner figure on the tab.
- **Plans with no TP2 (`no_tp2`) are excluded from the whole section.**
  "% to TP2" and "reached TP2" mean nothing for them. The section states
  how many were left out. *(Author's call.)*
- **Pre-v142 runners without a `runner_path` stamp** (`pathed` false)
  count in the cards and in N, Share, Avg/Med/Total R, vs all-out and
  Sessions. They are left out of Best R seen, % to TP2, Giveback, the
  Giveback row/card (which needs `mfe_r`) and the odds chart. The section
  says how many runners each of those figures left out, reusing the
  `path_unavailable` idea in `partials.py::_exclusions`. *(Author's
  call.)*
- **Giveback spans endings.** Most givebacks are breakeven exits, but a
  stall, time or manual close at ≤ 0R after reaching 50% progress is a
  giveback too. The "↳ Giveback" row sits under Breakeven but is labelled
  as counted across endings. It is excluded from the share total, so the
  other rows still sum to 100%. *(Author's call; the mockup showed it as
  "of which" under Breakeven.)*
- **The Giveback card's and row's share uses only the runners where
  giveback can be decided:** pathed, measured and with a TP1→TP2
  distance. The card states that N. A pre-v142 runner can never be a
  giveback, so counting it in the denominator would understate the
  share. *(Author's call.)*
- **The no-TP2 exclusion counts closed plans only.** Open runners are
  excluded anyway.
- A runner with no known runner R (a manual close with no price,
  `measured` false) counts in N and Share only. It is counted out of
  every R column, with the count shown.
- Everything follows the tab's existing scope (date range on fill date,
  strategy, horizon, side, ledger, origin): the same `select_plans`
  population as the rest of the tab.
- Any row, card or odds bar with N < `THIN_N` (10) carries the tab's
  existing thin marker. Nothing is hidden for being thin.

## How (decided)

- **Backend:** a new pure function in
  `swingbot/core/analytics/partials.py` (beside `outcomes()`) builds the
  section from the existing `PartialTrade` list. `build_report` adds it to
  the `/analytics/partials` payload under a new key. No new endpoint, no
  new store, no schema change, no change to `runner_path` stamping.
  `PartialTrade` gains the plan's TP2 in R (`tp2_r`), computed in
  `partial_trade()` from `plan.tp2` on the initial entry/stop basis
  (as `_one_leg_r` does), not as a new stored field. The builder
  confirms whether anything rewrites `plan.tp2` after the fill. If
  something does, progress uses the TP2 in force at TP1 when the record
  has it, and the spec's Population section gains a line saying so.
- **Frontend:** the model in `frontend/src/app/api/models.ts`
  (`AnalyticsPartials`) gains the new block. The Partials tab swaps the
  "Runner outcome mix" panel for the Runner endings section.
- **Layout C across three widths** (`docs/claude/ui-design.md`):
  - Desktop: 4 cards in a row, then the full-width table, then the odds
    chart.
  - Tablet: cards 2×2; the table scrolls horizontally with the Ending
    column pinned.
  - Phone: cards 2×2, the table scrolls with the Ending column pinned,
    the odds bars stacked full width with labels that wrap.
- The existing **Giveback** strip panel stays. It shows the distribution
  of giveback over all pathed runners, which the new mean-per-ending
  column does not replace.
- Ending colours reuse the tab's existing outcome tones (`tp2` pos,
  `trail` accent, and so on) so the cards, table and odds bars agree with
  the rest of the tab.

## Non-goals

- No change to any exit rule, trail distance, breakeven move, TP2
  placement or runner fraction. No setting, toggle or "what-if" control
  in this section.
- No money ($) view. The Partials tab is R-only today and stays R-only.
- No per-strategy/horizon split of the endings. The tab's Breakdown
  panel keeps that job. A future spec may add it.
- No backfill of `runner_path` for pre-v142 runners.

## Anti-goals

- **Numbers that don't add up.** Card shares, table shares and the odds
  bars must come from one population and agree. A giveback runner
  counted twice in a total is a failure, even if every cell is "right".
- **Thin numbers presented as findings.** A 3-runner row must look thin.
- **Any code path that changes how a live runner is managed.** This spec
  is read-only. A diff touching `plan_manager.py` exit logic is out of
  scope.

## Left to the builder

- The payload key name and exact JSON shape (one block holding cards,
  rows, odds and exclusion counts is the expectation).
- Whether the `outcomes` payload key stays. The new section supersedes
  it on screen. Drop it only if nothing else reads it (grep the
  frontend and `swingbot/`).
- Chart component choice for the odds bars: reuse an existing
  `ui/` chart or a stacked-bar primitive if one exists, else a plain
  CSS stacked bar as in the mockup.
- Panel header copy and hint text, in the tab's existing voice.

## Tests

- Backend unit tests for the new function: each definition (progress at
  exactly 50% and `r_runner` at exactly 0R for giveback, progress clamp at
  0 and 1, `tp2_r ≤ r_tp1` excluded, no_tp2 exclusion, unpathed runners,
  unmeasured manual closes, giveback clamp at 0, the giveback
  denominator), shares summing to 100% without the giveback row, odds
  groups at 25/50/75%, thin flags, and an empty population.
- An endpoint test that the `/analytics/partials` payload carries the
  block.
- Frontend specs: the section renders the four cards, the table rows in
  order and the odds bars from a fixture. The old "Runner outcome mix"
  panel is gone. Exclusion counts and thin markers show, and an empty
  population renders as measured zeros, not an error.
