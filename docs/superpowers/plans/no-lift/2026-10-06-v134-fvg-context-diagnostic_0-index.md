# v134 FVG context diagnostic (structure, confluence, approach): Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V134-3` or `grep -n "^### Task V134-3" -A 200 docs/superpowers/plans/2026-10-06-v134-fvg-context-diagnostic_*.md`.

**Closed (no-lift, 2026-10-10, partner decision):** never implemented; no code of this plan exists on any branch. Its premise is gone: v130 (structure features) closed no-lift, so `structure.major_structure_features` is not on `main` and V134-8 can never run; the displacement claim is already closed at plan level by v143 (and v128's `displacement@k` was refused at Stage 0). Found by the 2026-10-10 cross-plan audit. Do not re-open under another name (v143 rule).

**Bump:** none
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/no-lift/2026-10-06-v134-fvg-context-diagnostic-design.md`](../../specs/no-lift/2026-10-06-v134-fvg-context-diagnostic-design.md)

**Goal:** Build a causal instrument that tags every fair value gap at formation and at first touch, then measure once, on TRAIN 2020-01-01..2023-12-31, whether each of four handbook claims (displacement, structure, confluence, approach) separates gap outcomes. It gates nothing and changes no vote.

**Architecture:** A new pure module, `swingbot/core/market/fvg_context.py`, exposes the five functions the spec names (`all_gaps`, `first_touch`, `formation_tags`, `touch_tags`, `gap_outcome`) plus the frozen constants. No live path imports it. A read-only script, `scripts/backtest/measure_fvg_context_diagnostic.py`, truncates each cached frame at 2023-12-31, builds Table A (every gap scored at first touch, carrying the pre-registered verdict) and Table B (baseline FVG-tagged confluence plans, confounded, no verdict), and writes one results document. The six-clause verdict is committed in a pre-registration record before the one run.

**Tech Stack:** Python 3.11, pandas/numpy, pytest. Existing: `market.fvg`, `market.levels`, `market.structure`, `market.indicators.atr`, `strategy_types.HORIZONS`, `backtesting.acceptance`, `backtesting.arms.windows`, `scripts/backtest/measure_arms.py` (`load_frame`, `cached_universe`). From v128 (not on `main` yet): `fvg.is_displacement_gap`, `scripts/backtest/fvg_attribution.py`. From v130 (not on `main` yet): `structure.major_structure_features`.

## Where to work

- **Branch and worktree:** `2026-10-06-v134-fvg-context-diagnostic`, at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v134-fvg-context-diagnostic`. V134-1 creates it with the `worktree-lifecycle` skill. All implementation and the one measurement run happen there. Name the worktree in every subagent dispatch, and after each task run `git -C E:/Documents/Private/Projects/Discord-Bot status --short` to confirm the main tree is unchanged.
- **Backtest cache:** `data/` is gitignored, so the worktree has none. Prefix the measurement command with `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache`. Never fetch into the main-tree cache from the worktree.
- **Skills:** `no-lookahead` before every task that edits `fvg_context.py` (V134-2..5, V134-7, V134-8) and again in V134-15. `backtest-gate` before V134-13. `worktree-lifecycle` before creating the branch, before merging `main` into it, and before merging it out.

## Dependencies: what is blocked on what

Neither dependency is on `main` at writing (2026-10-06, `main` at `f51271b5`). V134-1 is the hard gate that checks them.

| Task | Needs | Why |
|---|---|---|
| V134-1 | nothing | It is the gate. It also creates the worktree |
| V134-2 .. V134-6 | **nothing** | Gap enumeration, first touch, origin / size / approach / touch_close / confluence tags, the outcome, and the script's pure arithmetic and verdict read only symbols on `main` today |
| V134-7 | **v128 (V128-1)** | Calls `fvg.is_displacement_gap`; its tests import v128's `tests/market/fvg_frames.py` |
| V134-8 | **v130 (V130-3)** | Calls `structure.major_structure_features`; its tests import v130's `tests/market/structure_tier_fixtures.py` |
| V134-9 | v128 and v130 (through V134-7, V134-8) | The Table A collector emits every tag |
| V134-10 | **v128 (V128-5)** | Table B replays through `fvg_attribution.py` |
| V134-11 | V134-9, V134-10 | Renders both tables |
| V134-12, V134-13 | v128 **closed** (its row in `backtest-methodology.md`) and v130 | The record is frozen and the run happens only after v128's grid and selection are final |
| V134-14, V134-15 | V134-13 | Close-out and the one full-suite run |

**If V134-1 reports a dependency missing:** V134-2 .. V134-6 may still be done on the branch. Nothing from V134-7 on may start. Do not stub, copy or re-implement a missing symbol. When the dependency lands on `main`, merge `main` into the branch (`worktree-lifecycle`) and re-run V134-1 Step 2 before V134-7.

## Global Constraints

- Measurement only. No change to `fvg.py`, `levels.py`, the confluence vote, plans, alerts, charts, config flags or stored records. `fvg_context.py` is imported by no live path.
- Window: daily bars, the standard backtest cache, every cached ticker. A gap is in the population only if its formation bar is on or after 2020-01-01 **and** its formation, first touch and outcome all end on or before 2023-12-31. A gap that would need a later bar is dropped and counted as `censored`. Bars before 2020 are lookback only.
- The script never hands the instrument a bar dated after 2023-12-31 and refuses any window touching 2024-01-01 or later. 2024–25 is v128's unspent VALIDATION window.
- Gap (bullish; bearish mirrors every comparison): forms at bar `i` when `Low[i] > High[i − 2]`; `bottom = High[i − 2]`, `top = Low[i]`, `mid` their mean; `m = i − 1`. Every gap is enumerated at formation.
- First touch: the first bar `τ > i` with `Low[τ] ≤ top`. `High[τ] ≥ bottom` is a touch; `High[τ] < bottom` is `gapped_through`; none within 60 bars is `untouched`.
- Frozen module constants (partner-approved 2026-10-06, never searched): stop buffer `0.25` ATR14, target `1.5` R, outcome horizon `20` bars, touch horizon `60` bars, displacement `k = 1.5`, structure event age `≤ 1`, confluence horizon `4w`.
- Outcome, with `a = ATR14[τ]`: `stop = bottom − 0.25 × a`. `Close[τ] ≤ stop` is failed on touch (no entry). Otherwise `entry = Close[τ]`, `risk = entry − stop`, `target = entry + 1.5 × risk`. Bars `τ+1 … τ+20`: loss at the first `Low ≤ stop`, win at the first `High ≥ target`, stop first on a shared bar; neither is a timeout marked at `Close[τ+20]`.
- Per bucket: `N`, hold rate `wins / (wins + losses)`, mean R over scored gaps (win `+1.5`, loss `−1`, timeout at its mark), failed-on-touch share. **These are gap statistics, never the bot's ExpR.**
- Verdict (bullish gaps, Table A), all six: (1) hold rate higher in the favourable bucket; (2) mean R no lower; (3) failed-on-touch share no higher; (4) both sides `N ≥ 100` scored gaps; (5) clauses 1 and 2 hold separately in 2020–21 and 2022–23 with `N ≥ 50` per side in each half; (6) on bearish gaps clause 1 has the same sign, or a side is under `N = 100`.
- Claims (favourable / against): displacement `yes` / `no`; structure `bos` or `choch` / `none`; confluence `3+` / `0` and `1-2`; approach `slowing` / `not_slowing` (`short` excluded). `origin`, `size` and `touch_close` are descriptive and carry no verdict. Nothing else may be promoted to a claim afterwards.
- Table B buckets with `N < 30` print `thin` and no ExpR. Table B carries no verdict and says it is confounded.
- The pre-registration record is committed **before** the run. The run happens **once**, through the `backtest-runner` agent, with flushed per-ticker progress and a percent figure in a log deleted on completion.
- Every function ends at cyclomatic complexity < 15; this plan holds itself to `python -m radon cc -s -n C <files>` printing nothing.
- Per-task check: `python scripts/dev/testrun.py file <the task's test file>`. The full suite runs **once**, in V134-15.

## Frozen readings (the spec is silent or loose; fixed here before any run and quoted in the pre-registration record)

| # | Reading | Where |
|---|---|---|
| F1 | The instrument returns `pending` when the frame ends before a touch or an outcome is known. On a frame truncated at 2023-12-31 that is exactly "would need a later bar", so the script counts it as `censored` | V134-2, V134-5, V134-9 |
| F2 | A gap whose ATR14 at `i` or at `τ` is not a finite positive number is dropped and counted as `no_atr`, a census bucket of its own (ABNB lists on 2020-12-10, so this happens). v130 item 3 is the precedent | V134-3, V134-5, V134-9 |
| F3 | `approach` is `short` whenever the ratio is undefined: under 6 bars, or a first third with zero true range | V134-3 |
| F4 | `touch_close` is geometric (`above` means `Close[τ] > top`) and is **not** mirrored for bearish gaps. Table A prints per direction, so no information is lost | V134-3 |
| F5 | The confluence bucket id is ASCII `1-2` in code and in the report (the spec prints `1–2`) | V134-4 |
| F6 | `formation_tags` returns the raw `size_atr`. Quintile edges are computed in the script, per direction, over every resolved gap of the population (touched, gapped-through and untouched; never censored) | V134-3, V134-6, V134-9 |
| F7 | `N` is scored gaps (win + loss + timeout). Failed-on-touch share is `failed / (scored + failed)` | V134-6 |
| F8 | The two halves split on the gap's **formation** date | V134-6 |
| F9 | A clause whose statistic cannot be computed (no decided gap on a side) fails. Clause 6 compares the sign of `hold rate(favourable) − hold rate(against)` on bearish gaps with the bullish sign | V134-6 |
| F10 | The window guard also refuses a start before 2020-01-01: pre-2020 bars are lookback only, so such a window would change the population | V134-6 |
| F11 | The structure tag calls `structure.major_structure_features(df.iloc[:i + 1], gap direction)`. `struct_event_last` is v130's single latest event, so an `*_against` event newer than a `*_with` one reads `none` | V134-8 |
| F12 | The confluence tag calls `collect_candidate_levels(window, HORIZONS["4w"], Close[τ])` with no `params`, as the spec writes it, and counts families with `count_confirming_strategies(..., mid, CLUSTER_TOLERANCE_PCT, candidates=)` minus `FVG` | V134-4 |
| F13 | Table B replays the baseline over `windows.ALL_HORIZONS` (what a v128 baseline arm is) under `apply_knobs({"FVG_LEVELS_MODE": "all"})`, so it is the `all` arm whatever v128 made the default | V134-10 |
| F14 | Table B `N` is closed trades (`acceptance.CLOSED`); win rate and ExpR are `acceptance.win_rate` / `expectancy_r`. It is not split by direction (the spec asks for bucket × source only) | V134-10 |
| F15 | The results document keeps the spec's date, `2026-10-06-v134-fvg-context-diagnostic.md`, whatever day the run happens (v130's convention) | V134-13 |

## Spec gaps resolved from v128's and v130's code: the controller should confirm these

These three are where the spec does not match what v128 and v130 will actually provide. Each resolution below takes its answer from the sibling plan's code, not from a new design, and each is quoted in the pre-registration record. **If the controller disagrees with one, change it before V134-12; after that it is frozen.**

| # | Spec says | Code says | Resolution in this plan |
|---|---|---|---|
| G1 | Table B tags each `record_ticker` plan "by the most recently formed FVG candidate in its level cluster" | `record_ticker`'s row is `{"key", "fvg_family", "candidates"}`. It carries neither the plan's take-profit nor its signal bar, so the gap cannot be identified from the row | V134-10's `replay_plans` is `record_ticker`'s body kept open: the same `_recording` context and the same `_provenance_row` call, also returning the recorder's own log record (`signal_index`, `take_profit`) and the trades. A test pins that its rows equal `record_ticker`'s. "Its level cluster" is read as v128's vote definition, the one that makes `fvg_family` true: an unfilled gap whose mid is within `fvg_attribution.VOTE_TOLERANCE_PCT` (5.0%) of the take-profit at the signal bar; the most recently formed such gap is taken |
| G2 | Table B is "split by confluence-sourced and strategy-sourced" | `record_ticker` replays `ConfluenceEngine` only, and v128's resolution A6 records that a strategy plan has no confluence vote. No strategy-sourced plan can carry `fvg_family` | The strategy side is structurally empty. Table B prints the confluence side and a one-line note saying why the strategy side is `n/a`. No strategy replay is added |
| G3 | "v130 implemented. The structure tag reads v130's snapshot keys" | v130's plan (V130-8, branch B) leaves its branch **unmerged** on a "not more informative" verdict, so `major_structure_features` would never reach `main` | V134-1 stops with `BLOCKED` in that case and asks the partner. This plan does not read v130's unmerged branch and does not drop the structure claim on its own |

Also found while verifying: v128's planned `tests/market/fvg_frames.py::witness_frame` passes a `zip` to `bar_frame`, which calls `len()` on it and raises `TypeError` (V128-1 Step 2). v134's tests therefore never call `witness_frame`; they use v128's hand-built candle constants and `gap_frame` only.

## File map

| File | Task | Responsibility |
|---|---|---|
| `swingbot/core/market/fvg_context.py` (new) | V134-2..5, V134-7, V134-8 | The instrument: `all_gaps`, `first_touch`, `formation_tags`, `touch_tags`, `gap_outcome`, frozen constants |
| `tests/market/fvg_context_frames.py` (new) | V134-2 | Standalone hand-built frames (true range 2.0 on every bar, so ATR14 is exactly 2.0), `mirror`, `extend`. Does not import v128's helpers |
| `tests/market/test_fvg_context_gaps.py`, `test_fvg_context_tags.py`, `test_fvg_context_confluence.py`, `test_fvg_context_outcome.py` (new) | V134-2..5 | One file per dependency-free task |
| `tests/market/test_fvg_context_displacement.py` (new) | V134-7 | Uses v128's `tests/market/fvg_frames.py` |
| `tests/market/test_fvg_context_structure.py` (new) | V134-8 | Uses v130's `tests/market/structure_tier_fixtures.py` |
| `scripts/backtest/measure_fvg_context_diagnostic.py` (new) | V134-6, V134-9..11 | Window guard, bucket arithmetic, verdict, both collectors, report, CLI |
| `tests/scripts/test_measure_fvg_context_diagnostic.py` (new) | V134-6, V134-9..11 | Grows with the script |
| `docs/superpowers/results/2026-10-06-v134-fvg-context-preregistration.md` (new) | V134-12 | The frozen record, committed before the run |
| `docs/superpowers/results/2026-10-06-v134-fvg-context-diagnostic.md` (new) | V134-13 | The one results document |
| `docs/claude/backtest-methodology.md` (modify) | V134-14 | Four rows, one per claim |

Verified on `main` at `f51271b5` (`git grep -n`, 2026-10-06): `fvg.find_fair_value_gaps_detailed` (keys `bottom, top, mid, bar_index, direction`; `bar_index` is the third candle), `levels.collect_candidate_levels(df, h, current_price, trendline_candidates=None, params=None)`, `levels.count_confirming_strategies(df, h, current_price, target_price, tolerance_pct, candidates=None)`, `levels.CLUSTER_TOLERANCE_PCT = 1.5`, `levels.strategy_family` / `_STRATEGY_FAMILY_PREFIXES` (`("FVG", "FVG")`), `structure.true_range(df)`, `structure.MIN_LEG_THIRD = 2`, `structure.MIN_BARS = 60`, `indicators.atr(df, period=14)`, `strategy_types.HORIZONS["4w"]`, `acceptance.ArmTrade` (`.key`, `.outcome`, `.r_multiple`, `.source`), `acceptance.CLOSED` / `win_rate` / `expectancy_r`, `arms.windows.VALIDATION_START = "2024-01-01"` / `ALL_HORIZONS`, `arms.knobs.apply_knobs`, `arms.confluence_engine.ConfluenceEngine.run_ticker(ticker, df, horizons, signal_window, params)`, `backtest_scenarios._resolve_replay_workers`, `measure_arms.load_frame` / `cached_universe`, `ScanParams.from_config`, `tests.conftest.make_ohlcv`, `tests.backtesting.test_v74_fixture.load_v74_fixture`. `structure._range_decay` exists but takes impulse-leg indices; it is **not** reused, and the return-leg ratio is written in `fvg_context.py`. **Created by v128 (checked in V134-1):** `fvg.is_displacement_gap(df, gap, k, atr_series=None)`, `fvg_attribution.record_ticker(ticker, df, horizons, signal_window)`, `fvg_attribution._recording(log, level_bars)`, `fvg_attribution._provenance_row(ticker, df, record, level_bars, memo)`, `fvg_attribution.VOTE_TOLERANCE_PCT`, `config.FVG_LEVELS_MODE`, `tests/market/fvg_frames.py`. **Created by v130 (checked in V134-1):** `structure.major_structure_features(df, direction)`, `structure.MAJOR_KEYS`, `tests/market/structure_tier_fixtures.py` (`DOWN`, `tier_frame`). **Created by this plan:** everything under "File map".

## Review Focus

1. **A 2024 bar reaching the instrument.** The cache runs to 2025-12-30. `_worker` must truncate before either collector sees the frame. Pinned by `test_the_worker_truncates_before_either_collector_sees_the_frame` and `test_a_gap_whose_outcome_would_need_a_2024_bar_is_censored` (V134-9, V134-11).
2. **`untouched` reported for a gap that merely ran out of frame.** That would count a censored gap as a resolved one. Pinned by `test_a_frame_that_ends_inside_the_60_bars_is_pending_not_untouched` (V134-2).
3. **A tag reading past its bar.** Every tag function slices its prefix first. Pinned by the `test_appending_bars_...` tests in each task and by `test_the_real_collector_reads_nothing_after_the_touch_bar` (V134-4).
4. **The gap's own family counted as confluence.** Pinned by `test_the_gaps_own_family_never_counts` (V134-4).
5. **Same-bar stop and target scored as a win.** Pinned by `test_the_stop_wins_a_bar_that_reaches_both` (V134-5).
6. **A second run after seeing the first.** `main` refuses to overwrite the results document. Pinned by `test_main_never_overwrites_a_result` (V134-11).
7. **A favourable bucket promoted after the fact.** `CLAIMS` is the only input to the verdict. Pinned by `test_verdicts_cover_exactly_the_four_declared_claims` (V134-6).

## Parts

| Part | Tasks | Content |
|---|---|---|
| `2026-10-06-v134-fvg-context-diagnostic_1-instrument.md` | V134-1 .. V134-5 | Phase 0 (precondition gate) and Phase 1 (the dependency-free instrument) |
| `2026-10-06-v134-fvg-context-diagnostic_2-script-and-blocked-tags.md` | V134-6 .. V134-9 | Phase 2 (the script's dependency-free core) and Phase 3 (the two blocked tags and the Table A collector) |
| `2026-10-06-v134-fvg-context-diagnostic_3-tables-run-close-out.md` | V134-10 .. V134-15 | Phase 4 (Table B, report, CLI), Phase 5 (pre-registration and the one run), Phase 6 (close-out and the full suite) |

## Parallelisation

Sequential throughout: gate → instrument → script → run → close-out. No two tasks may be dispatched at once.

- **V134-1 before everything:** it creates the worktree and decides which tasks may start.
- **V134-2 → V134-3 → V134-4 → V134-5, then V134-7 → V134-8:** all six edit the one file `swingbot/core/market/fvg_context.py`. V134-3 and V134-4 both rewrite `touch_tags`; V134-3, V134-7 and V134-8 all rewrite `formation_tags`. Two agents on that file overwrite each other.
- **V134-6 after V134-5:** it creates the script file and has no symbol dependency on the instrument, but it is kept in the chain because V134-9..11 edit the same script file and the same test file. It sits before V134-7 only because it needs no dependency, so it can be finished while v128 and v130 are still open.
- **V134-9 after V134-7 and V134-8:** its rows carry the `displacement` and `structure` keys those tasks add to `formation_tags`.
- **V134-9 → V134-10 → V134-11:** one script file and one test file. V134-11 renders what V134-9 and V134-10 collect.
- **V134-12 after V134-11:** the record quotes the script's exact CLI. **V134-13 after V134-12:** the script refuses to run without the record, and the record must be committed first. **V134-14 after V134-13**, **V134-15 last** (the one full-suite run).
- **Cross-plan:** v128 and v130 must land on `main` before V134-7 and V134-8 (see "Dependencies"). No other live plan is known to touch a file in this plan's file map.
