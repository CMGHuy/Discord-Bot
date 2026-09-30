# v113 pre-registration (Parts A, B, D)

Plan: `docs/superpowers/plans/2026-09-28-v113-bearish-day-coverage_0-index.md` (part files `_1a` … `_3`).
Spec: `docs/superpowers/specs/2026-09-28-v113-bearish-day-coverage-design.md`.
Data record: `docs/superpowers/results/2026-09-30-v113-data.md`.

**Committed before any v113 TRAIN number existed.** At commit time no v113 result JSON, `data/v113_*.json` or registry row exists; this document contains no performance figure. Every value below was read from the committed code (`measure_v113.py`, `funnel.py`, `measure_v104.py`, `short_entries.py`, `strategy_types.py`, `params.py`), not from the plan text. `measure_v113.py` last changed in commit ced9775b.

## The `1w` horizon

`HORIZONS["1w"]` verbatim: `label "3-7 day swing"`, `ema_fast 5`, `ema_slow 8`, `vwap_window 5`, `fib_lookback 10`, `sr_lookback 5`, `atr_stop_multiple 1.5`, `max_risk_pct 2.0`, `sr_stop_pct 2.0`, `sr_target_min_pct 2.0`, `sr_target_max_pct 5.0`, `max_holding_days 7`, `rs_window 10`, `min_reward_pct 2.0`. `MIN_BARS["1w"] = 20`. Never grid-searched.

- Masked by default: admitted for no strategy unless a `STRATEGY_GATES[<name>]["cells"]` pair names it; the confluence scan never runs it.
- Strategy-plan reward floor (index amendment 1): 2.0% on `1w`, none on the ten legacy horizons; read by `planning/reward_floor.py` from `build_strategy_plan` and `backtest._trade_plan_at`. The confluence `MIN_REWARD_PCT` path is untouched.
- Per-strategy tables with no `1w` row keep their existing fallbacks, unedited (amendment 4): MACD `(12, 26, 9)`, MA Ribbon `(10, 20, 50)`, Break & Retest recent 10 bars / retest 1.0%, VWAP `hold_bars_other` 2, HTF EMA none.

## Part A: Downtrend Overbought Fade (short-only, `1w`)

Signal at the close of bar t from bars <= t: `close_t < SMA200_t`, `SMA200_t < SMA200_{t-20}`, `RSI(2)_t >= 90`, and no earnings reaction within the next 7 bars (`0 <= evt_bars_to_next <= 7` blocks). Constants: `FADE_SMA 200`, `FADE_SLOPE_BARS 20`, `FADE_RSI_PERIOD 2`, `FADE_RSI_MIN 90.0`, `FADE_STOP_PCT 2.0`, `FADE_EARNINGS_BARS 7`. Default `m` 1.0.

Plan (`PLAN_SHAPES`): `entry_type limit`, `expiry_bars 1`, `tp1_fraction 1.0`, `breakeven_trigger_fraction 1.0`; exit params `trail_atr_mult 2.5`, `tp2 False`. Sell limit at `close_t`, good for one bar; stop = entry x 1.02; target = `entry - m x (stop - entry)`; one leg, no break-even move; time stop at the close of the 7th bar after entry (`max_holding_days 7`).

Fill model and fill-bar rule (amendment 3): the limit fills only on bar t+1, only if its high >= the limit, at `max(open, limit)`. On that bar: fill at or above the stop -> scratch, 0R; else if the high reaches the stop -> loss, -1R (stop first). Bar t+2 is never considered.

Grid `m in {1.0, 1.25, 1.5}` (`A_GRID`). Sizing: v104 fail-closed dollar-risk sizing, always in scope (`SHORT_STRATEGIES`).

- Stage 1: standard tiers (Tier 1 / Tier 2) per `m`; plateau winner via `funnel.stage1` (the value and both grid neighbours clear; winner = best Tier, then highest ExpR).
- Stage 2: `funnel.stage2` per-fold reselection; at least 3 qualifying folds (fold N >= 15) and at least 2/3 of them with ExpR > 0.

## Part B: legacy strategies on `1w`

The 22 `PART_B` cells: 11 `backtest.ALL_STRATEGIES` x {bullish, bearish} (EMA Crossover, VWAP, Fibonacci, Support/Resistance, RSI, MACD, Elliott Wave, MA Ribbon, Break & Retest, RSI Divergence, Volume Profile). Each on `1w` only, its own builder, the cell admitted through `cells` and every other pair on its live mask. No grid.

Bar: every Tier 1 clause **and** the ticker-cluster bootstrap lower bound on ExpR > 0, on TRAIN and again on the holdout. Stage 2 `funnel.fixed_folds` with the same fold rule as Part A. Reported per cell, never selecting: cap-bind rate (planned risk within `CAP_TOLERANCE_PCT = 0.001` pp of the 2% ceiling) and floor-drop rate (plans the 2% floor dropped / plans it judged, counted at the builder, before the bearish laggard rule).

## Part D: live bullish masks on inverse ETFs

Tickers `SH, PSQ, RWM, DOG` (`D_TICKERS`); all four survive the liquidity filter (data record; `universe_n` 4). Cells: exactly the 72 `(strategy, horizon)` pairs `measure_v113.d_cells()` returns (bullish live masks on `LEGACY_HORIZONS`, unchanged):

EMA Crossover: 2w 4w 2m 3m 4m 5m 6m 7m 8m 9m. VWAP: 4w. Fibonacci: 2w 4w 2m 3m 4m 5m 6m 7m 8m 9m. Support/Resistance: 2m 3m. RSI: 2w 4w 2m 3m 4m 5m 6m 7m 8m 9m. MACD: 3m 4m 7m 8m 9m. Elliott Wave: 2w 4w 2m 3m 4m 5m 6m 7m 8m 9m. MA Ribbon: 2w 4w 2m 3m 4m 5m 6m 7m 8m 9m. Break & Retest: 2m 3m 4m. RSI Divergence: 2w 4w 2m 3m 4m 5m 6m 7m 8m 9m. Volume Profile: 7m.

Masks unchanged. One pooled cell, standard tiers (Tier 1 or Tier 2). Stage 2 `fixed_folds`. Per-strategy and per-ticker breakdowns are reported only, never used to select. No registry row (amendment 5).

## Populations

v2 exits, scale-out on (a whole-position target takes the single leg), TP2 levels where a strategy's exit params allow, frictions flag on. The live bearish laggard rule applies to every bearish population (Part A and the bearish Part B cells). `apply_level_lifecycle` as it ships.

## Windows

`TRAIN = 2010-01-01..2025-12-31`. Anchored folds, test years 2013..2025 (13; `measure_v104.FOLD_YEARS`, passed explicitly to `funnel.stage2` and `fixed_folds`). `HOLDOUT = 2026-01-01..2026-09-25` (`HOLDOUT_START`, `HOLDOUT_END`). Thin-holdout reopen date `THIN_REOPEN = 2026-12-31`.

## Tiers (constants from `funnel.py` / `acceptance.py`)

- Tier 1: WR >= `WR_FLOOR` 50.0, ExpR > 0, decided N >= `MIN_N_TRAIN` 30 on TRAIN (`MIN_N_VALIDATION` 15 on the holdout), scratch+timeout share <= `MAX_SCRATCH_SHARE` 0.5.
- Tier 2: ExpR > 0 and ticker-cluster bootstrap lower bound on ExpR > 0 (`BOOTSTRAP_RESAMPLES` 10,000, `BOOTSTRAP_SEED` 42, 2.5th percentile), same N and scratch floors, no WR floor.
- Part B adds the bootstrap lower bound > 0 to Tier 1; `funnel.badge_verdict` alone has none.
- Fold rule: `FOLD_MIN_N` 15, `FOLD_POSITIVE_SHARE` 2/3, `MIN_QUALIFYING_FOLDS` 3.

## Stage 3 (holdout)

One shot per cell, ever. Holdout N < 15 -> write N only, `status: "sealed-thin"`, shot unspent; one retry only when `HOLDOUT_END >= 2026-12-31`. Clauses of the cell's assigned bar: Part A its Stage 1 tier; Part B Tier 1 + lower bound > 0; Part D its Stage 1 tier.

## Multiple testing

24 Stage 1 cells (Part A counts once, its plateau spanning 3 grid values; Part B 22; Part D 1). No correction. Part B's stricter bar (Tier 1 + lower bound) is the spec's answer to its 22 tries.

## Ship rules (spec §7; amendments 2, 5, 6)

- Part B pass: each passing (strategy, direction) is admitted on `1w` via `cells`; one `(strategy, 1w)` registry row is emitted per strategy, covering exactly its admitted 1w directions (spec §7: a strategy's row ships only when every admitted direction passes; a `1w` pass gets its own row). Status VALIDATED only if all emitted payloads are Tier 1 and the pooled badge clears, else WEAK (`measure_v113._validate_emit`, `_registry_row`).
- Part A pass: does **not** ship on the measurement alone. Live execution cannot yet match the backtest (no live `evt_*` columns, no `limit` fill, no whole-position TP1 close, no enforced time-stop exit in `PlanManager`), so the fade ships only with live parity (earnings context, limit entry, whole-position target, enforced time stop, resting-order alert line) and is unmasked last, on `(bearish, 1w)`. If the holdout fails, the parity tasks are recorded as skipped.
- Part D pass: no registry row; the partner is asked whether the confluence scan and bearish strategy signals on the four tickers (unmeasured populations) ship, recommending "measured population only".
- Alerts stay behind soak: `STRATEGY_ALERTS_MODE` and `STRATEGY_ALERTS_LIVE_STRATEGIES` are never changed by this plan.

## Data

Cache `data/backtest_cache_ext` only; the shared `data/backtest_cache/` is never written. Inverse-ETF cache, earnings hash (`market_data/earnings/*.csv`, 76 files, sha256 `3eeb801204606318450cdb3774ff6c893a36538e5db2f46cc713433ae8d759a4`) and universe hash (`data/watchlist.json`, 77 tickers, sha256 `4452b50f6391e7b3f14a224874b7a0dcc8f4245f7f5cca006c0f0ed7c2dca4de`) are recorded in the data record. Filtered `universe_n`: 74 (Parts A/B), 4 (Part D). Survivorship bias inflates long results and deflates short results, and deflates inverse-ETF long results (economically shorts).

## Not re-run (spec "Out of scope")

2x/3x inverse ETFs, options, pair trades, any market-regime gate, and any v93/v101-v104 bearish cell on its original horizons.
