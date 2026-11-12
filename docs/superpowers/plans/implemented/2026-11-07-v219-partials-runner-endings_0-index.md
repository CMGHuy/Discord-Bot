# v219 — Partials tab: runner endings (cards, scorecard, odds) (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v219 — Partials tab: runner endings](../specs/2026-11-07-v219-partials-runner-endings-design.md) (panel review applied, 975a2a77)

## Goal

The partner wants to see how the **runner** (the part of a position left
open after TP1) ends, ending by ending. How often does it reach TP2? How
often does it fall back to the post-TP1 floor ("breakeven")? How often
does it give back a good move? How often does the trailing stop close it?
And what R sits behind each of those? Today the Partials tab answers part
of this with one share bar ("Runner outcome mix"): count, share and
average runner R per close reason. It has no giveback category, no best R
seen before the exit, no "how close to TP2", no conditional odds and no
time per ending.

Once this plan ships, the Partials tab carries a **Runner endings**
section in place of that share bar, in the partner's layout C. Four
ending cards (TP2, Breakeven, Giveback, Trailing stop) come first, each
with its share, its 95% Wilson interval and its count. A scorecard table
follows, with one row per ending (TP2, Trailing stop, Breakeven, Other)
plus a set-apart "Giveback (any ending)" row. Its columns are N, Share,
Avg/Med/Total R, vs all-out, Best R seen, % to TP2, Gave back and
Sessions. Last comes an odds chart: of the runners that got 25%, 50% or
75% of the way from TP1 to TP2, how they ended. The `/analytics/partials`
payload swaps its `outcomes` key for one `runner_endings` block. The
existing Giveback strip keeps its name and now reads the same population
as the section's path figures.

How it works in idea: every number is computed server-side by pure
functions in `swingbot/core/analytics/partials.py`, over the
`PartialTrade` list `build_report` already builds. `PartialTrade` gains a
derived `tp2_r` (the plan's TP2 in R on the initial entry/stop basis). It
also gains a `decidable` test (a well-typed `runner_path` stamp, a known
runner R, not a manual close, TP2 above TP1) and a clamped `progress` to
TP2. Shares carry a Wilson interval from a new small helper in
`swingbot/core/analytics/intervals.py`. A malformed stamp is treated as
unpathed and never raises, because an exception inside `build_report`
fails the whole tab. The frontend draws the block in a new
`sb-runner-endings` component; the tab only hosts it.

What it leaves alone: every exit rule, trail distance, floor fraction,
TP2 placement and runner fraction. Nothing in `plan_manager.py`,
`exit_sim*.py` or `runner_path` stamping changes. There is no new
endpoint, no store, no schema change and no money view. The other
Partials panels (funnel, waterfall, ladder, split, holds, breakdown) keep
their figures; only the Giveback strip's population narrows to the
section's path filter.

Success is measured by the tests: the four ending rows sum to 100% of
the section, the Giveback share carries its own "of N decidable"
denominator, each exclusion is counted, a malformed stamp leaves the
endpoint answering, and the section renders at 390, 768 and 1440 px with
`frontend/scripts/layout-audit.mjs` exiting 0. It is statistics only, so
no ExpR or win-rate claim follows from it.

## Architecture

- **Backend (Part 1).** `intervals.py::wilson_interval` (new). In
  `partials.py`: `PartialTrade` gains `tp2_r` plus the `decidable` and
  `progress` properties, and `pathed` becomes type-checked. New pure
  builders `ending_rows`, `ending_cards`, `runner_odds`,
  `path_exclusions` and `runner_endings` sit beside `counterfactuals`.
  `build_report` emits `runner_endings` and drops `outcomes`, and
  `outcomes()` is deleted. `counterfactuals.giveback` reads only
  decidable runners and gains `giveback_excluded`. The route
  (`swingbot/admin/api_v1/analytics.py::analytics_partials`) is
  untouched: it already returns `build_report` whole.
- **Frontend (Part 2).** `models.ts` gains the `runner_endings` types.
  A new standalone component, `tabs/runner-endings.ts`, holds the cards,
  the scorecard (Ending column sticky, `.table-scroll`) and the CSS
  stacked odds bars. `sb-share-bar` has no interval/N slot, so the odds
  bars are plain CSS. `partials.ts` hosts it in a `.wide` panel where
  "Runner outcome mix" was, and drops `outcomeSegments`/`BUCKETS`.
  Release bumps `VERSION.json` (ui minor, bot patch) and regenerates
  `version_history.json`.

## Global Constraints

- Statistics only: no diff to `swingbot/core/planning/plan_manager.py`, `exit_sim*.py` exit logic, `runner_path.py` stamping, any store or any schema.
- Population: closed runners only; plans with no TP2 (`bucket == "no_tp2"`) are out of the whole section and counted as `excluded.no_tp2`.
- Ending of a runner, by bucket: `tp2`→`tp2`, `trail`→`trail`, `floor`→`floor` ("Breakeven"), `stall`/`time`/`manual`/`other`→`other`.
- **Decidable** (the path filter, for Best R seen, % to TP2, Gave back, Giveback and the odds): `pathed` (dict stamp, `mfe_r` a finite real number that is not a bool, `ladder` a dict) **and** `r_runner is not None` **and** `bucket != "manual"` (manual closes are filtered by bucket, never by `r_runner is None`) **and** `tp2_r is not None and tp2_r > r_tp1`.
- **Progress to TP2** = `(mfe_r − r_tp1) ÷ (tp2_r − r_tp1)`, clamped to [0, 1]; None unless decidable.
- **Giveback** = decidable, `progress >= 0.5` **and** `r_runner < r_tp1` (strictly below; exactly at `r_tp1` is not a giveback), whatever the ending.
- Giveback's share denominator is `decidable`; the four ending rows' denominator is `n` (section runners) and their shares sum to 100%.
- A runner with `r_runner is None` counts in N and Share only (not in any R mean, Total R, vs all-out or Sessions).
- Total R = sum of `(1 − fraction) · r_runner`; vs all-out = mean `PartialTrade.delta_r`; Gave back = mean `mfe_r − r_runner` unclamped, same formula as `_giveback`.
- Every share: percentage 1 dp, with Wilson 95% `lo`/`hi` as percentages 1 dp; `share`/`lo`/`hi` are None when the denominator is 0. R means carry no interval.
- Thin: `n < THIN_N` (10) on every row, card and odds bar; thin is marked, never hidden.
- `build_report` never raises on a malformed or partial `runner_path`; a test pins it.
- Required copy (wording the builder's, in the tab's voice): header hint "R, before commissions and tax."; on Best R seen / % to TP2 "The peak is known only afterwards; it is not a target."; on Breakeven "The floor locks ⅔ of the TP1 gain."; on the odds chart "Read off this book; any threshold taken from it is screened on backtest data first."
- Layout C: desktop 4 cards in a row → full-width table → odds; tablet and phone cards 2×2, table scrolls with the Ending column pinned; phone odds bars full width, labels wrap. Breakpoints only from `ui/breakpoints.ts` (639/640, 1023/1024).
- Ending tones reuse the tab's: `tp2` pos, `trail` accent, `floor` neg, `other` warn, `giveback` warn.
- Every function < complexity 15 (`scripts/dev/complexity_gate.py`); do not grow `kpis` (12) or `counterfactuals` (11).
- Narrow runs only: `python scripts/dev/testrun.py file <test>` and `node frontend/scripts/ng-test.mjs frontend --include <spec>`. No task runs the full suite (CI does). The admin endpoint test runs `/replicate-prod-db` against the shared `swing-db` (port 56789) first.

## Payload contract: `runner_endings`

`build_report(...)["runner_endings"]` (Python dict, JSON as-is):

```
{
  "n": int,              # closed runners in the section (no_tp2 and open excluded)
  "decidable": int,      # of those, runners passing the path filter
  "cards": [Share & {"ending": "tp2"|"floor"|"giveback"|"trail"}],      # in this order
  "rows":  [Row],        # endings "tp2","trail","floor","other","giveback", in this order
  "odds":  [{"level": 25|50|75, "n": int, "thin": bool,
             "split": [{"ending": "tp2"|"trail"|"floor"|"other", "n": int,
                        "share": float|None, "lo": float|None, "hi": float|None}]}],
  "excluded": {"no_tp2": int, "runner_r_unavailable": int, "manual_close": int,
               "unpathed": int, "no_tp2_distance": int}
}
Share = {"ending", "n", "denominator", "share", "lo", "hi", "thin"}
Row   = Share + {"r_n": int, "avg_r", "median_r", "total_r", "vs_all_out",
                 "path_n": int, "best_r", "progress", "gave_back", "sessions"}   # floats or None
```

- `excluded` path reasons are counted **first failing, in this order**: `runner_r_unavailable` → `manual_close` → `unpathed` → `no_tp2_distance`. So they sum to `n − decidable`.
- `progress` is a percentage 0–100, 1 dp. `avg_r`, `total_r`, `vs_all_out`, `best_r` and `gave_back` are rounded to 4 dp (`_mean`). `median_r` and `sessions` are `_median` floats.
- Odds group at level L: decidable runners with `progress >= L/100`; `split` shares are over the group `n`.

Expected block for `tests/analytics/test_partials.py::_book()` with `MANUAL` (both parts use it; the frontend fixture copies it):

```
n 4, decidable 3; excluded {no_tp2 1, runner_r_unavailable 0, manual_close 1, unpathed 0, no_tp2_distance 0}
rows (ending n denom share lo hi thin | r_n avg median total vs_all_out | path_n best progress gave_back sessions):
  tp2      1 4 25.0 4.6 69.9 T | 1 4.0  4.0  2.0  1.0  | 1 4.2 100.0 0.2  4.0
  trail    1 4 25.0 4.6 69.9 T | 1 3.0  3.0  1.5  0.5  | 1 3.6  80.0 0.6  2.0
  floor    1 4 25.0 4.6 69.9 T | 1 1.34 1.34 0.67 -0.33| 1 2.6  30.0 1.26 2.0
  other    1 4 25.0 4.6 69.9 T | 1 2.5  2.5  1.25 0.25 | 0 None None None 2.0
  giveback 0 3  0.0 0.0 56.2 T | 0 None None None None | 0 None None None None
cards: tp2, floor, giveback, trail (the matching rows' Share fields)
odds: 25 -> n 3: tp2 1 33.3 (6.1-79.2), trail 1 33.3 (6.1-79.2), floor 1 33.3 (6.1-79.2), other 0 0.0 (0.0-56.2)
      50 -> n 2: tp2 1 50.0 (9.5-90.5), trail 1 50.0 (9.5-90.5), floor 0 0.0 (0.0-65.8), other 0 0.0 (0.0-65.8)
      75 -> same as 50 (C's progress is 0.8)
counterfactuals.giveback [0.2, 1.26, 0.6] (A, B, C; F has no TP2), giveback_excluded 2
```

## Parallelisation

- **Lane A (backend, Part 1):** V219-1 ∥ V219-2 (disjoint files: `intervals.py` + its test vs `partials.py` + `test_partials.py`; no contract between them). Then V219-3, which consumes both (`wilson_interval`, `decidable`/`progress`), then V219-4, which consumes V219-3's builders. V219-2 → V219-3 → V219-4 are sequential for two reasons: they share a file (`partials.py`, `test_partials.py`) and each consumes the previous one's symbols.
- **Lane B (frontend, Part 2):** V219-5 can start alongside Lane A. It depends only on the payload contract above, not on backend code, and its files (`models.ts`, the fixture, the new component and its spec) are disjoint. V219-5b follows V219-5 (same files: it builds the component on its helpers). V219-6 follows V219-5b: it consumes `RunnerEndings` and shares `models.ts` and the fixture.
- **V219-7 (release)** runs last, after all of V219-1..6 are merged: the version bump describes the whole change, and `build_version_matrix.py` walks the release commits.
- Lanes A and B may run at the same time (at most 2 implementers). V219-6's layout audit needs a backend that serves `runner_endings`, so it runs after V219-4 is merged into the worktree.

## Task ledger

| ID | Title | Part | Model | Files (C create / M modify) | Creates for later tasks |
|---|---|---|---|---|---|
| V219-1 | Wilson interval helper | 1 | sonnet — new statistical helper, one module, behaviour fixed by formula | C `swingbot/core/analytics/intervals.py`, C `tests/analytics/test_intervals.py` | `wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] \| None` (fractions in [0, 1]; None when `n < 1`) |
| V219-2 | PartialTrade: `tp2_r`, typed `pathed`, `decidable`, `progress`; Giveback strip on the path filter | 1 | sonnet — normal TDD inside one module | M `swingbot/core/analytics/partials.py`, M `tests/analytics/test_partials.py` | `PartialTrade.tp2_r: float \| None = None` (last field); properties `pathed` (type-checked), `decidable -> bool`, `progress -> float \| None`; `counterfactuals()["giveback_excluded"]: int`; constant `GIVEBACK_PROGRESS = 0.5` |
| V219-3 | Ending rows and path exclusions | 1 | sonnet — new metric builders in one module | M `swingbot/core/analytics/partials.py`, M `tests/analytics/test_partials.py` | `ENDING_ROWS = ("tp2", "trail", "floor", "other")`; `ending_of(t: PartialTrade) -> str`; `is_giveback(t) -> bool`; `_share(k: int, n: int) -> dict` (`share`, `lo`, `hi`); `ending_rows(runners: list[PartialTrade]) -> list[dict]` (5 Rows); `path_exclusions(runners) -> dict` (4 path keys) |
| V219-4 | Odds, cards, `runner_endings`, `outcomes` key removed, never-raise and endpoint tests | 1 | sonnet — assembles V219-3's builders, one module plus its endpoint test | M `swingbot/core/analytics/partials.py`, M `tests/analytics/test_partials.py`, M `tests/admin/test_api_v1_analytics_partials.py` | `ENDING_CARDS = ("tp2", "floor", "giveback", "trail")`; `ODDS_LEVELS = (25, 50, 75)`; `ending_cards(rows) -> list[dict]`; `runner_odds(runners) -> list[dict]`; `runner_endings(trades: list[PartialTrade]) -> dict`; payload key `runner_endings`; `outcomes()` and the `outcomes` key gone |
| V219-5 | Frontend model, fixture and the runner-endings helpers | 2 | sonnet — new UI component from a fixed contract | M `frontend/src/app/api/models.ts`, M `frontend/src/app/workspaces/analytics/tabs/partials.fixture.ts`, C `frontend/src/app/workspaces/analytics/tabs/runner-endings.ts`, C `frontend/src/app/workspaces/analytics/tabs/runner-endings.spec.ts` | Types `PartialsEnding`, `PartialsShare`, `PartialsEndingCard`, `PartialsEndingRow`, `PartialsOddsSegment`, `PartialsOddsBar`, `PartialsRunnerEndings`; `AnalyticsPartials.runner_endings`; `counterfactuals.giveback_excluded: number`; fixture exports `RUNNER_ENDINGS_FIXTURE`, `RUNNER_ENDINGS_EMPTY`; helpers `ENDING_META`, `shareText`, `endingCards`, `scorecardRows`, `oddsBars`, `exclusionNote` and the copy constants |
| V219-5b | The `sb-runner-endings` component: cards, pinned scorecard, CSS odds bars | 2 | sonnet — new UI component from a fixed contract | M `frontend/src/app/workspaces/analytics/tabs/runner-endings.ts`, M `frontend/src/app/workspaces/analytics/tabs/runner-endings.spec.ts` | component `RunnerEndings` (selector `sb-runner-endings`, inputs `block: PartialsRunnerEndings` required, `thinN: number` required) |
| V219-6 | Partials tab hosts Runner endings; "Runner outcome mix" removed; three-width check | 2 | sonnet — one page's UI wiring and removal | M `frontend/src/app/workspaces/analytics/tabs/partials.ts`, M `frontend/src/app/workspaces/analytics/tabs/partials.spec.ts`, M `frontend/src/app/api/models.ts`, M `frontend/src/app/workspaces/analytics/tabs/partials.fixture.ts` | `PartialsOutcome`, `AnalyticsPartials.outcomes`, `outcomeSegments`, `BUCKETS` removed |
| V219-7 | Release: ui minor, bot patch, version history | 2 | haiku — fixed VERSION.json bump and regeneration | M `VERSION.json`, M `swingbot/admin/version_history.json` | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | [`2026-11-07-v219-partials-runner-endings_1-backend.md`](2026-11-07-v219-partials-runner-endings_1-backend.md) | V219-1..V219-4 | Wilson helper, PartialTrade additions, ending rows/cards/odds, `runner_endings` in the payload, `outcomes` removed |
| 2 | [`2026-11-07-v219-partials-runner-endings_2-frontend-and-release.md`](2026-11-07-v219-partials-runner-endings_2-frontend-and-release.md) | V219-5..V219-7 | Model, `sb-runner-endings` component, tab wiring at three widths, release |

## Notes for the part writers

- Spec citation drift: `plan.tp2` is assigned at plan build, `builders.py:494` (`tp2=tp2`) and the tp2 computed near `builders.py:779-785` (the spec's `:796` has drifted). `tp2_r` is computed in `partial_trade()` as `_one_leg_r(view, {"exit_price": plan.tp2})` when `plan.tp2 is not None`.
- `RUNNER_FLOOR_FRACTION` exists (`swingbot/core/planning/params.py:17`, `2.0 / 3.0`) and `runner_floor` exists (`swingbot/core/planning/exit_sim.py:390`); the Breakeven hint's "⅔" is correct. Neither is imported by this plan.
- `PartialTrade` is constructed positionally only in `partials.py:165` (no test constructs it); add `tp2_r` as the last field with a default.
- The tab's empty state fires on `population.partial === 0`; the "empty population renders as measured zeros" frontend case is a block with `n == 0` while `partial > 0` (all runners open).
- The scorecard's pinned Ending cell needs an opaque background; use the panel's background token from `frontend/src/app/ui/layout.ts` (`Panel`), checked with `git grep`.
