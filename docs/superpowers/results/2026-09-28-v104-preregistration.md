# v104 — Pre-registration (Task V104-15)

**Plan:** `docs/superpowers/plans/2026-09-25-v104-structural-stops-and-shorts_2-measurement.md`, Task V104-15
**Spec:** `docs/superpowers/specs/2026-09-25-v104-structural-stops-and-shorts-design.md` §5, §6
**Run date:** 2026-09-28
**HOLDOUT_END: 2026-09-25**, frozen in `scripts/backtest/measure_v104.py:38` by this task,
committed in the same commit as this document. Every value below is copied verbatim from
the committed `scripts/backtest/measure_v104.py`, `scripts/backtest/funnel.py` and the
plan index's Global Constraints/amendments — none of it is copied from the plan prose.

## Candidates

**Part A — 15 cells** (`PART_A` in `measure_v104.py:44-51`; admitted horizons per
`STRATEGY_GATES` in `swingbot/core/market/strategy_types.py:219-249`; `ALL_HZ` = all 10
horizons `2w,4w,2m,3m,4m,5m,6m,7m,8m,9m`):

| # | Strategy | Direction | Admitted horizons |
|---|---|---|---|
| 1 | Fibonacci | bullish | ALL_HZ (10) |
| 2 | RSI | bullish | ALL_HZ (10) |
| 3 | MA Ribbon | bullish | ALL_HZ (10) |
| 4 | VWAP | bullish | 4w |
| 5 | Support/Resistance | bullish | 2m, 3m |
| 6 | MACD | bullish | 3m, 4m, 7m, 8m, 9m |
| 7 | Volume Profile | bullish | 7m |
| 8 | Break & Retest | bullish | 2m, 3m, 4m |
| 9 | Break & Retest | bearish | 2m, 3m, 4m |
| 10 | EMA Crossover | bullish | ALL_HZ (10) — ungated |
| 11 | EMA Crossover | bearish | ALL_HZ (10) — ungated |
| 12 | RSI Divergence | bullish | ALL_HZ (10) — ungated |
| 13 | RSI Divergence | bearish | ALL_HZ (10) — ungated |
| 14 | Elliott Wave | bullish | ALL_HZ (10) — ungated |
| 15 | Elliott Wave | bearish | ALL_HZ (10) — ungated |

**Part B — 3 mechanisms × earnings settings entering Stage 1** (from V104-14,
`docs/superpowers/results/2026-09-28-v104-stage0.md`; none closed —
`closed_at_stage0=[]` on all three JSONs):

| Mechanism | Strategy | Earnings settings entering Stage 1 | Loosest-cell N |
|---|---|---|---|
| B1 | Bull Trap | hold, exit_before | 30,452 / 28,091 |
| B2 | Vol Expansion Breakdown | hold, exit_before | 3,755 / 3,171 |
| B3 | Earnings Gap Drift | hold (only setting) | 3,220 |

That is 5 mechanism × earnings combinations, all clearing Stage 0's N ≥ 30 floor at the
loosest cell by a wide margin.

## Definitions

**Part A in/out arms** (`measure_v104.py:82-88`, the `scope()` context manager):
`STRUCTURAL_STOP_SCOPE = ""` is the out-of-scope (baseline, today's) arm;
`STRUCTURAL_STOP_SCOPE = "<Strategy>:<direction>"` is the in-scope (structural-stop) arm,
set one cell at a time.

**B1 — Bull Trap** (`MECHANISMS["B1"]`, `measure_v104.py:54-55`): knob `k`, grid
`(1, 2, 3)`, loosest `3`, earnings settings `(hold, exit_before)`.

**B2 — Vol Expansion Breakdown** (`MECHANISMS["B2"]`, `measure_v104.py:56-57`): knob `m`,
grid `(1.0, 1.2, 1.4)`, loosest `1.0`, earnings settings `(hold, exit_before)`.

**B3 — Earnings Gap Drift** (`MECHANISMS["B3"]`, `measure_v104.py:58-59`): knob `g`, grid
`(0.05, 0.08, 0.12)`, loosest `0.05`, earnings settings `(hold,)` — no earnings axis; B3's
entry does not read `evt_bars_to_next`, so `exit_before` does not apply to it.

**Earnings axis** (index amendment 1, spec §3.4 as amended): the original "next reaction
within `max_holding_days`" block would reject almost every entry on long horizons.
Amended — `exit_before` blocks entry only when the next scheduled reaction is ≤ 1 bar
away; otherwise it enters, with the hold capped at the bar before the reaction
(`hold_cap_bars` on `TradePlanV2`, read by `simulate_exit`, `swingbot/core/planning/exit_sim.py:356-358`).

## Windows

- `TRAIN = 2010-01-01..2025-12-31` (`measure_v104.py:36`).
- Folds: **13 anchored folds, test years 2013..2025** (`FOLD_YEARS = tuple(range(2013, 2026))`,
  `measure_v104.py:40`), passed explicitly to `funnel.fixed_folds`/`funnel.stage2` as
  `fold_years=FOLD_YEARS`. Note: `funnel.py`'s own module-level `FOLD_YEARS` default
  (`tuple(range(2013, 2024))`, 11 years, `funnel.py:24`) is never used here — every v104
  call passes its own 13-year `FOLD_YEARS` explicitly, overriding that default.
- `HOLDOUT = 2026-01-01..2026-09-25` (`HOLDOUT_START = "2026-01-01"`, `measure_v104.py:37`;
  `HOLDOUT_END = "2026-09-25"`, frozen by this task).

## Clauses

**Tier 1** (`funnel.py:16-19`): `WR_FLOOR = 50.0`, ExpR > 0, `MIN_N_TRAIN = 30` on TRAIN
(`MIN_N_VALIDATION = 15` on the holdout), scratch+timeout share ≤ `MAX_SCRATCH_SHARE = 0.5`.

**Tier 2**: ExpR > 0, and the ticker-cluster bootstrap lower bound on ExpR > 0
(`n_resamples=acceptance.BOOTSTRAP_RESAMPLES` — 10,000 per the plan's Global Constraints,
`seed=BOOTSTRAP_SEED=42`, `funnel.py:25`, 2.5th percentile), same N and scratch floors as
Tier 1, no WR floor.

**Part A Stage 1** (`measure_v104.py:161-166`): the in-scope arm clears Tier 1 or Tier 2 on
TRAIN, **and** its ExpR beats the out-of-scope arm's ExpR (`beats_baseline`) on TRAIN
(re-measured after Part 0's lifecycle fix).

**Part A Stage 2**: `funnel.fixed_folds(arms["in"], FOLD_YEARS)` then
`funnel.fold_verdict` — clears with `MIN_QUALIFYING_FOLDS = 3` folds at test
`FOLD_MIN_N = 15`, and `FOLD_POSITIVE_SHARE = 2/3` of qualifying folds with ExpR > 0
(`funnel.py:20-22`).

**Part B Stages 1-2** (`measure_v104.py:217-219`): Stage 1 — Tier 1/2 plus the plateau
(a cell counts only if its grid neighbours pass the same tier, within one earnings
setting `e`); winner is the highest-ExpR Tier 1 plateau cell, else highest-ExpR Tier 2
plateau cell, else none. Stage 2 — `funnel.stage2(by_value, "bearish", spec.grid,
fold_years=FOLD_YEARS)`: per-fold reselection on `2010..Y-1` (highest ExpR with N ≥ 30),
clears with the same 3-folds/N≥15/⅔-positive rule as Part A.

**Stage 3 (holdout, both parts):** the assigned tier clears on the in-scope/winning arm
with holdout N ≥ 15, **and** (Part A only) in-scope ExpR ≥ out-of-scope ExpR on the
holdout.

## Thin-holdout rule (spec §5.4, as `measure_v104.py:259-271` enforces it)

A Stage 3 run with decided N < 15 writes N only — `status: "sealed-thin"`, no WR/ExpR/rows.
The shot is **unspent**. It may run exactly once more, and only once `HOLDOUT_END ≥
2026-12-31` (`THIN_REOPEN = "2026-12-31"`, `measure_v104.py:39`); the script refuses an
earlier retry (`check_shot_allowed`, `measure_v104.py:259-271`). At that point N < 15 is a
final NO-LIFT.

## One-shot rule (spec §5.6, as the script enforces it)

`check_shot_allowed` refuses a Stage 3 run when the pre-registration or evaluate JSON is
uncommitted, or when an output for that candidate already exists under any date — except a
`sealed-thin` output that meets the thin-holdout retry condition above.

## Multiple testing

Up to **18 holdout shots** (15 Part A cells + 3 Part B mechanisms). At the 2.5% one-sided
bootstrap bound, about **0.45 false passes are expected** across the full set. No
correction is applied; each verdict in the eventual holdout doc will restate this figure
beside it.

## Registry rule (index amendment 2)

The registry is keyed `(source, strategy, horizon)`, no direction. A Part A pass writes
that strategy's row only when **every** direction the strategy's live `STRATEGY_GATES`
entry admits has passed; otherwise no row is written and the methodology row records why
(the v103 rule). Each Part B short is one direction, so a pass writes exactly one row.

## Populations

- **Part A:** live-gate populations, current arithmetic (v2 exits, scale-out, TP2, and
  frictions on as already shipped; `apply_level_lifecycle` as fixed by V104-2's Part 0
  integrity fix). The bearish-only live gate override applies to every bearish arm already
  measured under it (v93).
- **Part B (shorts):** short-only, always in `STRUCTURAL_STOP_SCOPE` (never runs under the
  2% cap). Applies the live `rs_combined` laggard rule, as for every bearish plan
  (backtest == live). Shared, fixed and not tuned: exit model v2; 50% off at TP1; trail
  2.5 × ATR; **TP2 off**; TP1 by `select_structural_target` (1.5R floor, 2.5R cap). Every
  rule reads closed bars ≤ t only (no-lookahead, truncation-tested per V104-7 through
  V104-11).
- **Survivorship bias, stated:** the universe is today's survivors. This biases longs up
  and shorts down — a short mechanism passing this measurement clears a harder bar than an
  equivalent long would.

## Data

- **Cache:** extended to `HOLDOUT_END=2026-09-25` (`docs/superpowers/results/2026-09-28-v104-data.md`).
  The literal last cached row (2026-09-28) is a partial intraday bar (fetched mid-session);
  every v104 window bounds at `HOLDOUT_END`, excluding it by construction.
- **Earnings:** `market_data/earnings/*.csv`, 76 files, sha256
  `3eeb801204606318450cdb3774ff6c893a36538e5db2f46cc713433ae8d759a4` (covers all 75 non-ETF
  watchlist tickers; the 76th file is a stale leftover for a delisted-from-watchlist
  ticker). Coverage 2001-01-18..2026-12-09.
- **Universe:** 77 raw watchlist tickers, sha256
  `4452b50f6391e7b3f14a224874b7a0dcc8f4245f7f5cca006c0f0ed7c2dca4de`. `universe_n=74` after
  the measurement script's own filter (excludes `GC=F`/`SI=F` as non-equities and `SPCX`,
  which has no usable price history) — this is the number every later stage must match.

## Not re-run (spec §8)

Not re-run: v31 horizon splits, v17 `REGIME_ALLOW`, v84's per-strategy axes, v93's
mirrored bearish arms, v101, v102, and v103 A/C. Out of scope: the confluence pipeline's
own 2% cap (a different path); universe expansion; TP2 or trail tuning for shorts.

## Verdict

Pre-registration complete. 15 Part A cells and 5 Part B mechanism × earnings combinations
are registered for Stage 1/2 on TRAIN, each with exactly one 2026 holdout shot ever.
Proceeding to V104-16 (Part A collect and evaluate) only after this document and the
`HOLDOUT_END` freeze are committed together.
