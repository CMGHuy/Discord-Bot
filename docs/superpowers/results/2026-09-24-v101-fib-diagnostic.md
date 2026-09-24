# v101 Phase A — Fibonacci mechanism diagnostic (TRAIN)

**Edge:** expectancy
**Window:** TRAIN 2020-01-01..2023-12-31. No VALIDATION data read.
**Universe:** 73 symbols (cached universe after `liquidity_reason` / `data_quality_issues`, the v93 filter).
**Arithmetic:** `run_backtest`, v2 exits, scale-out, TP2 levels, frictions on. Bullish trades come from the live gate; bearish trades from v93's unmasked pass plus the `rs_combined` laggard rule.
**Fixed before the run:** `RECLAIM_WINDOW = 5`, `RATIO_LADDER = (0.382, 0.5, 0.618, 0.786, 1.0)`, WR floor 50, N floor 30 (decided, pooled per direction).
**Script:** `scripts/backtest/measure_fib_diagnostic.py` (main @ 4d873f61). Raw output: `2026-09-24-v101-fib-diagnostic.json`, `-table.md`. Pre-cap control: `-precap.json`, `-precap-table.md`.

## Deviations from the plan, decided during execution

1. **The diagnostic reproduces `_trade_plan_at` exactly, including `apply_level_lifecycle`.** The plan assumed the trade's stop equals `_fibonacci_plan`'s. It doesn't: the lifecycle step (`LEVEL_LIFECYCLE_STOPS_ENABLED`) re-prices stops afterwards. `stop_mismatch` now compares against `_trade_plan_at`'s own output (tolerance `max(1e-4, 1e-6·entry)`, v2 stores `round(·, 4)`). It is **0 in both directions** in both runs.
2. **#2/#4 are paired and calibrated.** Base and arm are scored on the identical rows where both closed. For the exit rule, #2/#4 use a calibrated win rate: v2 WR of those same trades, plus (arm − base) under the simple first-touch simulator. The simulator's absolute WR is never compared to the floor.
3. **#4 (reclaim) is the full production plan at the reclaim bar j** (`_trade_plan_at(frame, j, …)`, so the 2% cap applies at `entry_j` and lifecycle runs). It counts as invalidated if any bar in (i, j] trades through the bar-i stop. This replaces the plan's "same stop" wording, which would have measured trades live cancels.

## Sanity gates

The first run's gates **failed**, and the cause was found and confirmed:

| Check | Current run | Expected | 
|---|---|---|
| v93 bearish reproduction | 246 / 121 / N 94 / WR 25.5% / ExpR −0.091 | 226 / 107 / N 89 / 21.3% / −0.255 |
| Bullish vs registry | N 288 / 28.8% / +0.039 | N 246 / 35.4% / +0.232 |
| Stop mismatches | 0 / 0 | 0 |

**Cause: `a3a903d6` (2026-09-21) capped every strategy builder's stop at `HARD_MAX_PLANNED_LOSS_PCT` = 2%.** Before that, Fibonacci's stop could sit up to `max_risk_pct` (3–11%) from entry. v93 (2026-09-17) and the registry row (2026-09-10) both predate it.
**Confirmed by control run** with the cap monkeypatched off (`builders.capped_planned_loss_pct = mfd.capped_planned_loss_pct = lambda p: float(p)`, no repo change): `v93_exact=True`, with 226 / 107 / N 89 / 21.3% / −0.255 exactly. The bullish baseline is N 249 / 35.3% / +0.231 against the registry's 246 / 35.4% / +0.232; the 3-trade gap is the universe filter.

## Results — current arithmetic (the population a flag would ship into)

| Direction | Cell | N | WR | ExpR |
|---|---|---:|---:|---:|
| bullish | baseline (v2) | 288 | 28.8% | +0.039 |
| bullish | #1 structural_only (v2) | **0** | — | — |
| bullish | #2 deeper_stop calibrated | 368 | 28.7% | +0.034 |
| bullish | #4 reclaim calibrated | 218 | 35.9% | +0.013 |
| bearish | baseline (v2) | 94 | 25.5% | −0.091 |
| bearish | #1 structural_only (v2) | **0** | — | — |
| bearish | #2 deeper_stop calibrated | 119 | 25.5% | −0.088 |
| bearish | #4 reclaim calibrated | 60 | 49.1% | +0.246 |

| Direction | cap rate | lifecycle rate | over-hard-cap rate | reclaim rate | #4 coverage |
|---|---:|---:|---:|---:|---:|
| bullish | 100.0% | 41.3% | 41.3% | 72.5% | 58.4% |
| bearish | 100.0% | 32.2% | 32.2% | 65.3% | 51.2% |

The full table, including the simple-simulator base/arm rows and per-horizon description rows, is in `2026-09-24-v101-fib-diagnostic-table.md`.

## Results — pre-cap control (old arithmetic, for comparison only)

| Direction | Cell | N | WR | ExpR |
|---|---|---:|---:|---:|
| bullish | baseline | 249 | 35.3% | +0.231 |
| bullish | #1 structural_only | 17 | 23.5% | +0.076 |
| bullish | #2 calibrated | 341 | 36.7% | +0.195 |
| bullish | #4 calibrated | 206 | 29.4% | +0.027 |
| bearish | baseline | 89 | 21.3% | −0.255 |
| bearish | #1 structural_only | 2 | 0.0% | −0.369 |
| bearish | #2 calibrated | 105 | 22.9% | −0.221 |
| bearish | #4 calibrated | 59 | 25.0% | −0.155 |

## Reading

- **#1 (structural-stop filter) is empty by construction.** Under the 2% cap, no Fibonacci swing extreme ever sits within 2% of entry (cap rate 100% in both directions), so "keep only structural stops" keeps nothing. Before the cap it kept 17 bullish trades at WR 23.5%, *worse* than the capped ones. The hypothesis that capped stops cause the low win rate is refuted either way.
- **#2 (deeper-ratio stop)** moves nothing: calibrated WR 28.8% → 28.7% bullish and 25.5% → 25.5% bearish, the same ExpR within ±0.005. Under the 2% cap the deeper-ratio stop is almost always capped to the same price.
- **#4 (reclaim entry)** has opposite signs in the two directions. Bullish it lowers ExpR (+0.039 → +0.013) while calibrated WR rises to 35.9%, still 14pp short. Bearish it reaches calibrated **WR 49.1%, ExpR +0.246 at N 60**, the closest cell to the floor. It still fails the floor, rests on a calibration (the simulator's own arm WR is 26.7%), and does not replicate under the pre-cap control (25.0%, −0.155). That is a spike, not a plateau. It is **not** a candidate, and per the spec it may not be rescued by moving the floor or the window.
- Per-horizon rows are description only (#3 is closed by v31) and carry no candidates.
- **Current-arithmetic baseline, for the record:** bullish Fibonacci is now N 288, WR 28.8%, ExpR +0.039 on TRAIN, far below the registry row's +0.232, which was scored before the 2% cap.

## Verdict

**NO-LIFT.** No pooled per-direction cell reaches WR ≥ 50 at N ≥ 30 under current arithmetic or under the pre-cap control. VALIDATION not spent.

## Findings outside v101's scope (recorded, not acted on)

1. **Every registry badge predates the 2% cap.** `a3a903d6` changed every strategy builder's stop on 2026-09-21. The registry's newest row is 2026-09-10, and MACD and Volume Profile (the two VALIDATED rows) were scored 2026-08-17. Their populations no longer exist in the current engine. Fibonacci's own TRAIN ExpR fell from +0.232 to +0.039 across that change.
2. **The lifecycle step can widen a stop past the 2% hard cap.** `apply_level_lifecycle` (`swingbot/core/planning/lifecycle.py`) bounds widening by the raw `max_risk_pct`, not `capped_planned_loss_pct`. `a3a903d6`'s message says this was deliberate. Measured here: 41.3% of bullish and 32.2% of bearish TRAIN Fibonacci trades carry a stop more than 2% from entry (rounding-safe tolerance). Fibonacci plans use `market` entry, and `plan_manager` cancels over-cap plans only on the stop-entry fill path (`plan_manager.py:519`). A market-entry plan only gets a warning (`plan_manager.py:385`), so live alerts can carry more than 2% planned loss. Whether `LEVEL_LIFECYCLE_STOPS_ENABLED` is on in production `.env` has not been checked.
