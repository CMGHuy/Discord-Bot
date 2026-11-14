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
   **Breakeven**, **Other** (stall + time + manual + `other`), then a
   separated cross-cutting row **Giveback (any ending)**.
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
   | Gave back | mean `mfe_r − r_runner`, the same unclamped formula as the existing Giveback strip (`partials.py::_giveback`), so the tab has one meaning for the measure. It is named "Gave back" so it is not confused with the Giveback ending. |
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
  **below the TP1 price** (`r_runner < r_tp1`), whatever its close reason:
  breakeven, trail or other. It reached halfway to TP2 and ended up
  giving back all of the gain past TP1. *(Partner, 2026-11-07, after the
  panel found the "breakeven" exit is the floor, below.)*
- **Breakeven:** close reason `tp1_runner_be` (bucket `floor`). Since v39
  this is **not** the entry price. It is the post-TP1 floor at
  `entry + ⅔·(tp1 − entry)` (`exit_sim.py::runner_floor`,
  `params.py::RUNNER_FLOOR_FRACTION`), so it banks about ⅔ of TP1's R.
  The partner chose to keep the name "breakeven". The card's and row's
  hint says "the floor locks ⅔ of the TP1 gain" so the label is not read
  as 0R.
- **Trailing stop:** close reason `tp1_runner_trail` (bucket `trail`).
- **TP2:** close reason `tp1_runner_tp2` (bucket `tp2`).

## Population

- Closed runners only. Open runners are excluded, as in every other
  runner figure on the tab.
- **Plans with no TP2 (`no_tp2`) are excluded from the whole section.**
  "% to TP2" and "reached TP2" mean nothing for them. The section states
  how many closed plans were left out. *(Author's call.)*
- **Path figures** are Best R seen, % to TP2, Gave back, the Giveback
  ending (row and card) and the odds chart. They use only runners that
  meet all of these:
  - **pathed:** a `runner_path` stamp with both `mfe_r` and `ladder`.
    Pre-v142 runners and malformed stamps fail this.
  - **measured:** the runner R is known.
  - **not a manual close:** the stamp never sees a manual exit price
    (`runner_path.exit_r` is None for one, `runner_path.py:146-148`), so
    `mfe_r` understates it.
  - **a TP1→TP2 distance:** `tp2_r > r_tp1`.

  Each exclusion is counted and shown, extending
  `partials.py::_exclusions`. *(Author's call; the manual-close exclusion
  is the panel's, quant-researcher 5.)*
- Every runner in the section counts in the three ending cards (TP2,
  Breakeven, Trailing stop), and in N, Share, Avg/Med/Total R, vs all-out
  and Sessions. A runner with no known runner R counts in N and Share
  only, with the count shown.
- **Giveback spans endings.** It is a separate, visually set-apart row
  after Other, labelled "any ending", excluded from the share total, so
  the four ending rows still sum to 100%.
- **The Giveback card's and row's share has its own denominator**: the
  runners that pass the path filter above. The card and the row's Share
  cell both carry it in place ("23% of 41 decidable"), not only in a
  footnote, so no one reads the four cards as one total. *(Panel:
  quant-researcher 6, financial-advisor 2.)*
- Everything follows the tab's existing scope (date range on fill date,
  strategy, horizon, side, ledger, origin): the same `select_plans`
  population as the rest of the tab.
- **Uncertainty:** every share (cards, Share column, odds bars) shows a
  95% Wilson interval beside it. R means show no interval, and their N
  is always visible. Any row, card or odds bar with N < `THIN_N` (10)
  also carries the tab's existing thin marker. Nothing is hidden for
  being thin. *(Panel: quant-researcher 3, financial-advisor 4.)*

## How (decided)

- **Backend:** a new pure function in
  `swingbot/core/analytics/partials.py` (beside `outcomes()`) builds the
  section from the existing `PartialTrade` list. `build_report` adds it to
  the `/analytics/partials` payload under a new key. No new endpoint, no
  new store, no schema change, no change to `runner_path` stamping.
- **`tp2_r`:** `PartialTrade` gains the plan's TP2 in R, computed in
  `partial_trade()` from `plan.tp2` on the initial entry/stop basis (as
  `_one_leg_r` does). It is not a stored field. `plan.tp2` is assigned
  only at plan build (`builders.py:494`, `:796`), and the exit code only
  reads it, so the TP2 on the record is the TP2 in force at TP1.
  *(Panel: staff-engineer 1.)*
- **The `outcomes` payload key is removed.** Its only consumers are the
  panel this replaces (`partials.ts:81`, `:167`, `:209`) and its fixture
  (`partials.fixture.ts:19`). Nothing under `scripts/` or `swingbot/`
  reads it. *(Panel: staff-engineer 2.)*
- **Blast radius:** the new function runs inside `build_report`, and an
  exception there fails the whole `/analytics/partials` response
  (`api_v1/analytics.py:534-547`). The Partials tab would then show one
  panel error for the entire tab. So:
  - The function never raises on a malformed or partial `runner_path`.
    The path filter treats such a stamp as unpathed.
  - A test pins that behaviour.
  - Rollback is an admin-image rollback. Nothing is stored.

  *(Panel: staff-engineer 3.)*
- **Frontend:** the model in `frontend/src/app/api/models.ts`
  (`AnalyticsPartials`) swaps `outcomes` for the new block. The Partials
  tab swaps the "Runner outcome mix" panel for the Runner endings
  section.
- **Copy the section must carry** (exact wording is the builder's, in the
  tab's voice):
  - Header hint: "R, before commissions and tax."
  - On Best R seen / % to TP2: "The peak is known only afterwards; it is
    not a target."
  - On Breakeven: "The floor locks ⅔ of the TP1 gain."
  - On the odds chart: "Read off this book; any threshold taken from it
    is screened on backtest data first." The odds are descriptive
    conditionals on the live book. A progress or giveback threshold read
    from them would need a Stage −2 screen on backtest data before any
    rule uses it (`backtest-methodology.md` § Stage −2).

  *(Panel: financial-advisor 1 and 3, quant-researcher 2.)*
- **Layout C across three widths** (`docs/claude/ui-design.md`):
  - Desktop: 4 cards in a row, then the full-width table, then the odds
    chart.
  - Tablet: cards 2×2; the table scrolls horizontally with the Ending
    column pinned.
  - Phone: cards 2×2, the table scrolls with the Ending column pinned,
    the odds bars stacked full width with labels that wrap.
- The existing **Giveback** strip panel stays, and keeps its name. It
  shows the distribution of `mfe_r − r_runner` over pathed runners. The
  new "Gave back" column uses the same unclamped formula, so the two
  agree. The strip adopts the same path filter as the section (manual
  closes, no-TP2 runners and runners with no TP2 distance all out;
  partner call 2026-11-08) so both read one population, and a
  `giveback_excluded` count says how many it dropped. *(Panel: quant-researcher 4, staff-engineer
  4.)*
- Ending colours reuse the tab's existing outcome tones (`tp2` pos,
  `trail` accent, and so on) so the cards, table and odds bars agree with
  the rest of the tab.

## Non-goals

- No change to any exit rule, trail distance, floor fraction, TP2
  placement or runner fraction. No setting, toggle or "what-if" control
  in this section.
- No money ($) view. The Partials tab is R-only today and stays R-only.
- No per-strategy/horizon split of the endings. The tab's Breakdown
  panel keeps that job. A future spec may add it.
- No backfill of `runner_path` for pre-v142 runners.

## Anti-goals

- **Numbers that don't add up.** The ending cards, the Share column and
  the odds bars must come from one stated population each and agree. A
  giveback runner counted into a 100% total is a failure, even if every
  cell is "right".
- **Thin numbers presented as findings.** A 3-runner row must look thin.
- **Any code path that changes how a live runner is managed.** This spec
  is read-only. A diff touching `plan_manager.py` or `exit_sim*.py` exit
  logic is out of scope.

## Left to the builder

- The payload key name and exact JSON shape (one block holding cards,
  rows, odds and exclusion counts is the expectation).
- Chart component choice for the odds bars: reuse an existing
  `ui/` chart or a stacked-bar primitive if one exists, else a plain
  CSS stacked bar as in the mockup.
- Exact header and hint wording, carrying the copy above.

## Tests

- Backend unit tests for the new function. Each definition gets a test:
  - Giveback: progress at exactly 50%, `r_runner` exactly at `r_tp1`
    (not a giveback) and just below (is one).
  - Progress clamped at 0 and at 1.
  - `tp2_r ≤ r_tp1` excluded.
  - no_tp2 exclusion.
  - Unpathed, malformed-stamp and manual-close runners: out of the path
    figures and counted.
  - Unmeasured runners.
  - The Giveback denominator.

  Also: the four ending shares sum to 100%, odds groups at 25/50/75%,
  Wilson bounds, thin flags, and an empty population.
- An endpoint test that the `/analytics/partials` payload carries the
  block and no longer carries `outcomes`.
- Frontend specs:
  - The section renders the four cards (Giveback with its "of N
    decidable" label), the table rows in order, and the odds bars from a
    fixture.
  - The "Runner outcome mix" panel is gone.
  - Exclusion counts, intervals, thin markers and the required copy show.
  - An empty population renders as measured zeros, not an error.

## Panel review

Run 2026-11-07, after the spec commit, before the partner's review.

- quant-researcher: "Breakeven" exit is the ⅔-of-TP1 floor, not 0R, so the `r_runner ≤ 0` giveback almost never fires -- **applied**: partner redefined giveback as ≥50% progress then closed below TP1; partner kept the name "breakeven", with a hint stating the floor.
- quant-researcher: odds are descriptive conditionals; thresholds read off them need a Stage −2 screen on backtest data -- **applied** (odds-chart copy, How).
- quant-researcher: only a binary thin flag; add intervals -- **applied** (Wilson 95% on every share; R means show N, no interval).
- quant-researcher: clamping giveback biases the mean and disagrees with the unclamped strip -- **applied** (unclamped, renamed "Gave back", strip and column share one formula and population).
- quant-researcher: manual closes understate `mfe_r` -- **applied** (manual closes out of every path figure, counted).
- quant-researcher: Giveback share uses another denominator in the same column -- **applied** ("x% of N decidable" in the cell and on the card).
- staff-engineer: close the "is `plan.tp2` rewritten" question now -- **applied** (only set at build, `builders.py:494`, `:796`).
- staff-engineer: decide the `outcomes` key -- **applied** (removed; only the replaced panel read it).
- staff-engineer: name the blast radius, never raise on a malformed `runner_path`, test it -- **applied**.
- staff-engineer: two "Giveback" meanings on one tab -- **applied** (column renamed "Gave back"; the ending keeps "Giveback").
- staff-engineer: one-population question belongs to quant-researcher -- **rejected**: pointer only, covered by the Population and Anti-goals sections.
- financial-advisor: say R is before commissions and tax -- **applied** (header hint).
- financial-advisor: Giveback card's different denominator must be visible on the card -- **applied** (merged with quant-researcher 6).
- financial-advisor: peak figures read as achievable exits -- **applied** (hint copy).
- financial-advisor: small odds groups read as findings -- **applied** (Wilson interval and N on every bar, thin marker).
- financial-advisor: threshold validity is quant-researcher's -- **rejected**: pointer only, not a finding.

## Close-out panel (diff review, 2026-11-12)

Range `e135cb7d..320981a6`. No BLOCKING finding from any seat; every advisory is carried, none applied in this plan.

- quant-researcher: Wilson interval treats same-week runners as independent (`intervals.py:11`) -- carried: spec chose Wilson; a cluster interval is a possible follow-up.
- quant-researcher: `thin` keys on the numerator on cards/rows but on group size on odds bars (`partials.py:341`, `:403`) -- carried: follows the spec wording; needs a partner call.
- quant-researcher: odds "Other" excludes manual closes while the scorecard "Other" row includes them (`partials.py:403` vs `:318`) -- carried.
- quant-researcher: Giveback strip hint omits the `runner_r_unavailable` exclusion reason (`partials.ts:213`) -- carried.
- staff-engineer: `outcomes` swapped in place, so a cached pre-v219 PWA bundle can break the Partials tab for ~5 min after deploy; rollback mismatches the other way (`partials.py:494`, `pwa-update.service.ts:22`) -- carried: admin-only, self-heals on reload, stores nothing.
- financial-advisor: cost/tax caveat only in the title tooltip, not `PERFORMANCE_CAVEAT` (`runner-endings.ts:17`) -- carried.
- financial-advisor: R columns hide `r_n`/`path_n` denominators (`runner-endings.ts:62-76`) -- carried.
- financial-advisor: odds percentages read as a forecast (`runner-endings.ts:146`) -- carried.
- financial-advisor: Best R seen hindsight note is hover-only (`runner-endings.ts:56`) -- carried.
- financial-advisor: "thin" mark is hover-only on touch (`runner-endings.ts:123`) -- carried.

Prediction check: Bump ui minor / bot patch and Edge none (integrity) held (ui 1.41.0, bot 2.18.4). skills: none affected.
