# Edge Engine — Growth Maximization Implementation Plan (100 tasks)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute strictly in order (Tasks E1–E100).

**Goal:** Maximize compounded account growth honestly — by raising per-trade expectancy (better filters, data-driven stops/targets), raising valid-trade frequency (a liquidity-screened 500+ ticker & index universe), and protecting compounding (fractional-Kelly & volatility-targeted sizing, portfolio heat and correlation caps, drawdown throttles) — with every new component forced through a walk-forward anti-overfit harness before it touches live behavior.

**What this plan will NOT do (read before Task E1):**

- It will **not** target a ~100% win rate. Win rate is trivially inflated by shrinking targets and widening stops, which destroys expectancy; the validated 80–87% OOS win rates of the current system are already near the healthy ceiling for its R:R profile. The optimization target throughout is **expectancy_r and compounded growth at bounded drawdown**, never raw WR.
- It will **not** promise a 10x timeline. It ships a growth calculator (E2) so the real timeline is always visible: 10x = `ln(10)/ln(1 + risk_pct × expectancy_r)` closed trades. Example: 1% risk, +0.10R → ≈2,303 trades; at 60 valid signals/month post-universe-expansion that is a ~3–4 year base case, faster only via the levers this plan builds — never via leverage-to-ruin.
- It will **not** reuse the burned 2024–2025 validation window for tuning. All new components validate by **anchored walk-forward folds inside 2018–2023** (E31) plus a **live shadow forward-gate** (E40). The 2024–2025 window is touched exactly once more, at E97, for the pooled final system, pre-registered.

**Architecture:** New `swingbot/core/edge/` package (growth math, sizing, portfolio risk, regime v2, factors), `swingbot/core/backtest_wf.py` walk-forward harness, execution-realism layer inside the existing backtest, `charts/` v3 decision charts. Everything gates through TRAIN-fold discipline → shadow forward-test → live, mirroring the flag/shadow pattern proven in plan-engine-v2.

**Tech Stack:** Python 3.11+, pandas, numpy, mplfinance/matplotlib, pytest ≥8. **No new pip dependencies** (no ML frameworks — every model here is transparent arithmetic the walk-forward harness can audit).

**Prerequisites:** plan-engine-v2 merged (TradePlanV2, exit simulator, registry); cockpit-v3 Part 1 merged (analytics: journal MFE/MAE, jsonio, snapshot). Independent of cockpit Parts 2–3 and llm-advisor.

## Progress

> - **Branch:** `feature/edge-engine`
> - **Completed:** —
> - **Next:** Task E1

## Global Constraints

- **Optimization target:** `expectancy_r` and fold-consistent compounded growth; WR is reported, never optimized.
- **Pre-registered fold gate (fixed now, before any data contact):** anchored expanding folds — train 2018→fold-start, test years 2021 / 2022 / 2023. A component passes if pooled test `expectancy_r` improves vs baseline in **≥ 2 of 3 folds**, no fold degrades baseline expectancy by more than 0.05R, and N ≥ 30 per fold. Components that fail are documented and dropped — no second grid on the same hypothesis.
- **Every new gate/filter/factor is a flag-gated config Field, default off**, tuned only via the walk-forward harness, promoted to live only after the E40 shadow forward-gate.
- **Sizing safety rails (frozen constants):** `KELLY_FRACTION_CAP = 0.25` (quarter-Kelly ceiling), `PORTFOLIO_HEAT_CAP_PCT = 6.0` default, drawdown throttle ladder fixed at E45. Nothing in this plan may raise effective risk beyond these without the user editing config deliberately.
- **Same-bar conservative ordering, win definition, and exit constants from plan-engine-v2 are untouched.**
- **Every task ends green:** `python -m pytest tests/ -q` + `make check` before commit; conventional commits; run from repo root.
- **Backtest data:** cached daily OHLCV 2018-06→present via `scripts/fetch_backtest_data.py`; universe files under `data/universe/`.
- **DataFrame convention** unchanged (`Open,High,Low,Close,Volume`, DatetimeIndex).

## File Structure (target state)

```
swingbot/core/edge/
  __init__.py         growth.py (math)       ruin.py (Monte Carlo)
  sizing.py (kelly/vol-target)               heat.py (portfolio risk)
  correlation.py      regime2.py             factors.py (RS, MTF, breadth)
  stops.py (MAE/MFE-driven)                  frictions.py (slippage/commission)
  gates.py (earnings/liquidity/gap)          throttle.py (streak/DD ladders)
swingbot/core/
  backtest_wf.py      walk-forward fold engine + permutation test
  backtest.py         MOD frictions + portfolio replay mode
  universe.py         NEW universe files + liquidity screen
  scan_engine / scanning/*  MOD new gates (flag-gated), parallel scan
swingbot/core/charts/
  decision_chart.py   NEW one-pager trade chart (MTF, AVWAP, RS, outcome cloud)
  portfolio_charts.py NEW heat/correlation/growth-path/Monte-Carlo renders
scripts/
  build_universe.py, wf_run.py, permutation_test.py, ablation.py, premortem template
tests/  test_edge_*.py, test_wf_*.py, test_universe.py, test_decision_chart.py ...
```

---

# Phase E0 — Honest growth math & sizing foundations (E1–E10)

### Task E1: `edge` package + growth equations

**Files:** Create `swingbot/core/edge/__init__.py`, `swingbot/core/edge/growth.py`; Test `tests/test_edge_growth.py`

**Interfaces:** `per_trade_growth(risk_pct, expectancy_r) -> float`; `trades_to_multiple(multiple, risk_pct, expectancy_r) -> int | None` (None when expectancy ≤ 0); `eta_days(trades_needed, trades_per_month) -> int`; `growth_table(expectancies, risks) -> list[dict]`.

- [ ] **Step 1: Failing test**

```python
# tests/test_edge_growth.py
from swingbot.core.edge.growth import trades_to_multiple, per_trade_growth

def test_ten_x_trade_count_golden():
    # 1% risk, +0.10R expectancy -> 0.1% growth per closed trade
    assert trades_to_multiple(10, 1.0, 0.10) == 2303
    assert per_trade_growth(1.0, 0.10) == 0.001

def test_negative_expectancy_never_compounds():
    assert trades_to_multiple(10, 1.0, -0.05) is None
```

- [ ] **Step 2: FAIL → implement (`math.log`) → PASS. Step 3: Commit** — `feat: growth equations (the honest 10x math)`

### Task E2: `!growth` command — the reality dashboard

**Files:** Modify `swingbot/commands/trades.py` (or new `commands/growth.py`); Test `tests/test_edge_growth.py`
**Interfaces:** `!growth [target_multiple]` — reads live expectancy/frequency from the analytics snapshot, prints: current expectancy_r, live trades/month, projected trades & ETA to target at current settings, and the sensitivity table (what expectancy +0.05R or frequency +20/mo does to the ETA). Renderer `growth_report(snapshot, target=10.0) -> str` is the tested unit.
- [ ] Failing test (fixture snapshot → report contains trade count + ETA) → implement → commit `feat: !growth reality dashboard`

### Task E3: Bootstrap Monte Carlo — drawdown & ruin

**Files:** Create `swingbot/core/edge/ruin.py`; Test `tests/test_edge_ruin.py`
**Interfaces:** `simulate(r_multiples: list[float], *, risk_pct, n_trades=1000, n_paths=2000, seed=42) -> dict` — bootstrap-resamples the realized R distribution, compounds paths, returns `{p50_final_multiple, p05_final_multiple, max_dd_p50, max_dd_p95, p_ruin (equity < 0.5×start), p_10x}`. Deterministic under seed.
- [ ] Failing test (synthetic R list: known heavy-loss mix → `p_ruin` rises with `risk_pct`; monotonicity assertion between risk 1% and 5%) → implement (numpy, vectorized) → commit `feat: bootstrap Monte Carlo ruin/drawdown simulator`

### Task E4: Fractional-Kelly sizing

**Files:** Create `swingbot/core/edge/sizing.py`; Test `tests/test_edge_sizing.py`
**Interfaces:** `kelly_fraction(win_rate, avg_win_r, avg_loss_r) -> float` (0 when edge ≤ 0); `kelly_risk_pct(stats, cap=0.25) -> float` — quarter-Kelly of the strategy's OWN live+registry stats, floored/ceilinged to [0.25%, 2.0%] of equity; docstring shows the derivation. `KELLY_FRACTION_CAP = 0.25` frozen.
- [ ] Failing tests (golden: WR 0.80, avg win 0.4R, avg loss 1.0R → kelly = 0.8 − 0.2/0.4 = 0.30 → quarter-Kelly 7.5% → capped to 2.0%; zero-edge → 0) → implement → commit `feat: fractional-Kelly sizing math`

### Task E5: Volatility-targeted sizing

**Files:** Modify `sizing.py`; Test `tests/test_edge_sizing.py`
**Interfaces:** `vol_target_risk_pct(ticker_atr_pct, portfolio_target_daily_vol_pct=0.7, open_positions=…) -> float` — scales per-position risk so estimated portfolio daily vol stays near target; combined mode `effective_risk_pct = min(config_risk, kelly_risk, vol_target_risk)`.
- [ ] Failing tests (high-ATR ticker gets less risk; combination takes the min) → implement → commit `feat: volatility-targeted sizing`

### Task E6: Sizing modes wired into `account.compute_position_size`

**Files:** Modify `swingbot/core/account.py`, `swingbot/config.py` (Field `POSITION_SIZING_MODE` gains options `kelly`, `vol_target`, `min_of_all`; Field `PORTFOLIO_TARGET_DAILY_VOL_PCT`)
- [ ] Failing tests (each mode produces documented share counts on a fixture account; default mode unchanged byte-for-byte) → implement → commit `feat: kelly/vol-target sizing modes (default unchanged)`

### Task E7: Portfolio heat cap

**Files:** Create `swingbot/core/edge/heat.py`; wire into the alert path pre-sizing; config Field `PORTFOLIO_HEAT_CAP_PCT` (default 6.0)
**Interfaces:** `open_heat(open_trades) -> float` (Σ per-trade risk-to-stop as % of equity); `remaining_heat(...)`; entries that would exceed the cap emit the plan flagged `"heat_blocked": true` (shown, not hidden — user requirement pattern) with size 0 suggestion.
- [ ] Failing tests (3 open × 2% → 6% heat → next plan blocked; closing one frees heat) → implement → commit `feat: portfolio heat cap`

### Task E8: Correlation-aware exposure

**Files:** Create `swingbot/core/edge/correlation.py`; Test `tests/test_edge_correlation.py`
**Interfaces:** `returns_corr(ticker_a_df, ticker_b_df, window=90) -> float`; `cluster_exposure(open_trades, candidate_ticker, dfs) -> dict {max_corr, correlated_heat}`; gate: candidate with corr > 0.75 to open positions counts their heat against its own cluster budget (`CORRELATED_HEAT_CAP_PCT`, default 3.0). Sector fallback when data thin: same first-2 GICS chars from ticker directory.
- [ ] Failing tests (two clones corr ≈ 1.0; cluster heat math) → implement → commit `feat: correlation-aware heat clustering`

### Task E9: Growth-path tracker

**Files:** Modify `swingbot/core/analytics/snapshots.py` consumer side only via new `edge/growth.py` fn; Test `tests/test_edge_growth.py`
**Interfaces:** `growth_path(equity_curve_points, start_balance, target_multiple=10) -> dict {current_multiple, pct_to_target, required_daily_growth_for_eta(years=[3,5,8]), on_track_vs: {…}}` — consumed by `!growth` and the E80 chart.
- [ ] Failing test (fixture curve at 1.5x → correct pct + required rates) → implement → commit `feat: growth-path tracker`

### Task E10: Phase E0 checkpoint

- [ ] Full suite green; run `python -c` smoke printing the growth table and a Monte Carlo summary for the current live R-history; paste both into the Progress block. Commit `docs: E0 checkpoint`.

---

# Phase E1 — Data, universe & execution realism (E11–E22)

### Task E11: Friction model in the backtest

**Files:** Create `swingbot/core/edge/frictions.py`; Modify `swingbot/core/backtest.py` (fill functions); config Fields `SLIPPAGE_BPS` (default 5), `COMMISSION_PER_TRADE` (default 1.0)
**Interfaces:** `apply_frictions(fill_price, side, slippage_bps) -> float`; every simulated entry/exit fill worsens by slippage; expectancy math subtracts commission as R via risk amount. Backtest gains `--frictions on|off` (default ON from now; a one-time re-baseline table TRAIN 2018–2023 with/without is committed to the results doc — expect ~0.02–0.05R haircut; this is the honest baseline every later component beats).
- [ ] Failing tests (bullish entry fills higher, exit fills lower by bps; golden number) → implement → re-baseline run → commit `feat: slippage+commission realism (new baseline)`

### Task E12: Liquidity screen

**Files:** Create `swingbot/core/universe.py`; Test `tests/test_universe.py`
**Interfaces:** `liquidity_ok(df, min_avg_dollar_vol=20_000_000, min_price=5.0) -> bool` (20d average); scan skips illiquid tickers (log-visible), backtest excludes them; constants are config Fields.
- [ ] Failing tests (penny/thin fixture fails; SPY-like passes) → implement + wire → commit `feat: liquidity screen`

### Task E13: Universe files + S&P 500 builder

**Files:** Create `scripts/build_universe.py`, `data/universe/sp500.json`, `data/universe/etfs.json` (SPY, QQQ, IWM, DIA, XL-sector ETFs, GLD, TLT)
**Interfaces:** builder scrapes/fixes the S&P 500 constituent list (documented manual-refresh fallback: paste from a public source), writes `{symbol, name, sector}`; `universe.load(name) -> list[dict]`. Watchlist remains the user's curated overlay; scanning source becomes `WATCHLIST | UNIVERSE_NAME` via config Field `SCAN_UNIVERSE` (default `watchlist` — no behavior change yet).
- [ ] Failing tests (loader validates schema; dedupe) → implement, run builder, commit files → `feat: tradeable universe files`

### Task E14: Index/ETF plan support

**Files:** Modify `swingbot/core/plan_engine.py` callers/`strategy_types.py` metadata; Test `tests/test_universe.py`
**Interfaces:** ETFs/indices flow through the same pipeline; earnings gates auto-skip for ETFs (`is_etf(symbol)` from universe files); sizing uses the same ATR math. Verified by building a plan for SPY end-to-end in a test.
- [ ] Failing test (SPY plan builds; `days_to_earnings` path skipped) → implement → commit `feat: index/ETF plan support`

### Task E15: Incremental data cache

**Files:** Modify `swingbot/core/data_store.py`, `scripts/fetch_backtest_data.py`
**Interfaces:** `update_cache(symbols) -> dict` fetches only bars newer than each CSV's last date (yfinance ranged call), atomic CSV replace; nightly-safe for 500+ symbols. `--universe sp500` flag on the fetch script.
- [ ] Failing tests (existing CSV grows without duplicate index rows; empty-delta no-op) → implement → commit `perf: incremental OHLCV cache`

### Task E16: Data-quality validator

**Files:** Create `scripts/validate_data.py` + `universe.py` fn; Test `tests/test_universe.py`
**Interfaces:** `data_quality_issues(df, symbol) -> list[str]` — flags: >5 consecutive identical closes, single-bar move >40% without volume spike (bad split adjust), negative/zero prices, gaps >10 calendar days. Scan/backtest skip symbols with issues (logged); script reports across the cache.
- [ ] Failing tests (each rule on a synthetic frame) → implement → run once over cache → commit `feat: data-quality gate`

### Task E17: Overnight gap model

**Files:** Create part of `swingbot/core/edge/gates.py`; Test `tests/test_edge_gates.py`
**Interfaces:** `gap_stats(df, lookback=250) -> dict {p90_gap_pct, p99_gap_pct}` (|open/prev close − 1| distribution); `stop_beyond_gap_noise(stop_pct, gap_p90) -> bool` — plans whose stop distance < the ticker's P90 overnight gap are flagged `"gap_fragile": true` (a stop inside gap noise is a coin flip, not risk control). Walk-forward will test it as a filter in E33.
- [ ] Failing tests (gappy synthetic vs smooth) → implement → commit `feat: overnight gap-noise model`

### Task E18: Earnings blackout gate

**Files:** Modify `gates.py`; config Field `EARNINGS_BLACKOUT_DAYS` (default 0 = off)
**Interfaces:** `in_earnings_blackout(symbol, now, days) -> bool` using the existing earnings-info source (+ Finnhub if the advisor's L11 module exists — soft import). Flag-gated filter candidate for E33.
- [ ] Failing tests (inside/outside window; ETF exempt) → implement → commit `feat: earnings blackout gate (off by default)`

### Task E19: Intraday confirmation data (1h bars)

**Files:** Modify `data_store.py` (1h interval cache, 730d yfinance limit respected); Test `tests/test_universe.py`
**Interfaces:** `get_intraday(symbol, interval="1h") -> pd.DataFrame | None` (cached, None-safe); used by E29 entry-timing factor. Never required — daily-only mode always works.
- [ ] Failing tests (cache roundtrip; None on fetch error) → implement → commit `feat: 1h bar cache`

### Task E20: Scan parallelization

**Files:** Modify `swingbot/core/scanning/engine.py` (thread-pool over tickers, pool size config `SCAN_WORKERS` default 4 — CX23-safe); Test `tests/test_universe.py`
- [ ] Failing test (results identical ordered set vs serial on 10 fixtures; wall-clock assertion skipped in CI) → implement → commit `perf: parallel scan`

### Task E21: Universe-scale dry run

- [ ] Operational task: fetch sp500 cache (`--universe sp500`), run one full scan with `SCAN_UNIVERSE=sp500` in a test channel; record scan duration + memory in the Progress block; if >15 min on CX23, tune `SCAN_WORKERS`/batching before proceeding. Commit notes.

### Task E22: Phase E1 checkpoint

- [ ] Full suite + `make check`; re-baseline doc committed (`docs/superpowers/results/2026-XX-edge-baseline.md`) with frictions-on TRAIN numbers per strategy — the reference every Phase-E2 component must beat. Commit `docs: friction-adjusted baseline`.

---

# Phase E2 — Signal & exit upgrades (E23–E44)

Every factor lands the same way: pure function → flag-gated filter/score → walk-forward fold gate (Phase E3 harness; earlier factors are re-run under it at E39). No factor tunes on 2024+.

### Task E23: Regime model v2

**Files:** Create `swingbot/core/edge/regime2.py`; Test `tests/test_edge_regime2.py`
**Interfaces:** `classify(spy_df, breadth: float | None) -> str` over 4 regimes — `bull_quiet` (SPY>200EMA, 20d realized vol < 60th pctile), `bull_volatile`, `bear_quiet`, `bear_volatile`; `regime_series(spy_df) -> pd.Series` for backtests. Transparent thresholds as constants.
- [ ] Failing tests (synthetic regimes classify correctly; series aligns to index) → implement → commit `feat: 4-state regime model`

### Task E24: Per-strategy regime gates (walk-forward candidate)

**Files:** Modify `swingbot/core/entry_filters.py` (gate hook), `strategy_types.py` (optional `regime_allow` per strategy); config flag `REGIME_GATES_ENABLED`
**Interfaces:** backtest + live share `regime_allow` exactly like `STRATEGY_GATES`. The actual allowed-set per strategy is decided by E33's fold runs, not here — this task ships the mechanism + characterization tests only.
- [ ] Failing tests (gate excludes entries in disallowed regime in both paths) → implement → commit `feat: regime gate mechanism`

### Task E25: Relative-strength factor

**Files:** Create `swingbot/core/edge/factors.py`; Test `tests/test_edge_factors.py`
**Interfaces:** `rs_percentile(ticker_df, spy_df, window=63) -> float` (0–100, 3-month return vs SPY, percentile against the scanned universe snapshot `data/universe/rs_cache.json` refreshed per scan); filter candidate `rs_min` (long entries) for the fold harness.
- [ ] Failing tests (outperformer > underperformer; cache refresh) → implement → commit `feat: relative-strength factor`

### Task E26: Sector RS factor

**Files:** Modify `factors.py`
**Interfaces:** `sector_rs(sector, sector_etf_dfs, spy_df) -> float`; combined `rs_score = 0.7×ticker_rs + 0.3×sector_rs`.
- [ ] Failing tests → implement → commit `feat: sector RS`

### Task E27: Multi-timeframe alignment score

**Files:** Modify `factors.py`
**Interfaces:** `mtf_alignment(daily_df, direction) -> int` (0–3: weekly EMA trend, weekly higher-low structure, daily>weekly pivot) — weekly resampled from daily (no new data); filter candidate `mtf_min`.
- [ ] Failing tests (aligned uptrend → 3; chop → ≤1) → implement → commit `feat: MTF alignment score`

### Task E28: Breadth internals

**Files:** Modify `factors.py`; scan hook computes daily breadth from the universe cache
**Interfaces:** `breadth_pct_above_50ema(universe_dfs) -> float`; feeds regime2's `breadth` arg and a filter candidate (`no new longs when breadth < X` — X fold-tuned).
- [ ] Failing tests (synthetic universe halves) → implement → commit `feat: market breadth factor`

### Task E29: Intraday entry-timing check

**Files:** Modify `factors.py` (uses E19 1h bars)
**Interfaces:** `intraday_confirms(symbol, direction) -> bool | None` — last 1h close above VWAP-of-day for longs (None when no data ⇒ neutral, never blocks). Live-only refinement (stop-entry plans keep their daily trigger; this only annotates plan quality) — explicitly NOT a backtest filter (no intraday history depth), documented as such.
- [ ] Failing tests (confirm/reject/None paths) → implement → commit `feat: intraday confirmation annotation`

### Task E30: Anchored VWAP levels

**Files:** Modify `swingbot/core/levels.py` (new level source) + `factors.py` anchors
**Interfaces:** `anchored_vwap(df, anchor_idx) -> pd.Series`; anchors = last 2 swing lows/highs (existing pivot logic) + highest-volume day in 120d; AVWAPs enter the level map as target/stop candidates with source label `"AVWAP"` (they cluster with existing levels — confluence count benefits).
- [ ] Failing tests (AVWAP math golden on synthetic; level map contains AVWAP entries) → implement → commit `feat: anchored VWAP levels`

### Task E31: Data-driven stops from MAE distributions

**Files:** Create `swingbot/core/edge/stops.py`; Test `tests/test_edge_stops.py`
**Interfaces:** `mae_informed_stop_mult(journal_entries, strategy) -> float | None` — P90 of winners' `mae_r` per strategy (winners rarely go beyond it; stops tighter than that are noise-stopped, wider waste risk); returns an ATR-mult adjustment factor clamped [0.8, 1.3], None when N < 40. Flag `DATA_DRIVEN_STOPS_ENABLED`; fold-validated at E33 using backtest-simulated MAE (same computation over fold-train trades).
- [ ] Failing tests (synthetic winner MAE distribution → expected mult; N floor) → implement → commit `feat: MAE-informed stop sizing`

### Task E32: MFE-informed TP2 + time stops

**Files:** Modify `stops.py`
**Interfaces:** `mfe_informed_tp2_r(fold_trades, strategy) -> float | None` (P60 of winners' `mfe_r` — a TP2 the runner actually reaches); `optimal_time_stop_days(fold_trades, strategy) -> int | None` (day by which P80 of eventual winners had reached ≥0.5R — beyond it, expectancy of holding decays). Both feed plan_engine as optional overrides behind the same flag.
- [ ] Failing tests → implement → commit `feat: MFE-informed TP2 + time stops`

### Task E33: Fold-tune the Phase-E2 filter set

**Files:** Create `scripts/wf_components.py`; results doc `docs/superpowers/results/2026-XX-edge-folds.md`
- [ ] Run the E39 harness (build order note: E39 lands the engine — this task executes after it; keep as the *decision record* task): one fold-run per component (regime gates, rs_min grid {50,60,70}, sector on/off, mtf_min {1,2}, breadth floor {40,45,50}, gap-fragile filter, earnings blackout {2,3} days, MAE-stop mult, MFE TP2, time stops) against the E22 baseline, gate per Global Constraints, record pass/fail + adopted values in the results doc and as config defaults (flags stay off until E40 shadow).
- [ ] Commit — `docs: component fold decisions (pre-registered gate applied)`

### Task E34: Candlestick quality at levels

**Files:** Modify `swingbot/core/candlestick_patterns.py` + `factors.py`
**Interfaces:** `pattern_quality_at_level(df, idx, level) -> int` (0–10: close position in range, volume vs 20d, wick rejection through the level). Score component candidate (feeds quality score, not a hard filter).
- [ ] Failing tests → implement → commit `feat: level-touch candle quality`

### Task E35: Volume profile HVN/LVN targets

**Files:** Modify `swingbot/core/levels.py` volume-profile source
**Interfaces:** high/low-volume nodes from the existing 180d profile enter the level map (`"HVN"/"LVN"`); LVNs preferred as TP zones (price moves fast through them), HVNs as stop shelter. Pure level-map enrichment — confluence machinery does the rest.
- [ ] Failing tests (bimodal volume fixture → nodes found) → implement → commit `feat: HVN/LVN levels`

### Task E36: Divergence quality upgrade

**Files:** Modify `swingbot/core/signals.py` RSI-divergence detector
**Interfaces:** divergence strength score (number of swing points, slope differential, volume confirmation) replacing the binary detect; fold candidate `div_strength_min`.
- [ ] Characterization tests first (current detections unchanged with score attached) → implement → commit `feat: scored divergences`

### Task E37: Composite entry-quality score v2

**Files:** Modify `swingbot/core/quality.py`
**Interfaces:** new components (weights fold-audited, live path stays transparent points): RS percentile (0–10), MTF alignment (0–10), breadth (0–5), candle quality (0–5), gap-fragility penalty (−10–0). Total still clamped 0–100; decile audit (v2 Task 52 harness) re-run and committed.
- [ ] Failing tests (component points) → implement → re-audit → commit `feat: quality score v2 components`

### Task E38: Pyramiding rules

**Files:** Modify `swingbot/core/plan_manager.py` (guarded by `PYRAMIDING_ENABLED`, default off)
**Interfaces:** on PARTIAL (TP1 banked, stop at BE): optionally add ½-size at +1R with stop for the add at entry — total position risk never exceeds the original 1R at any moment (invariant test). Fold-validated as an exit-model variant before enabling.
- [ ] Failing tests (risk invariant across add scenarios, incl. gap-through) → implement → commit `feat: risk-invariant pyramiding (off)`

### Task E39: Walk-forward engine

**Files:** Create `swingbot/core/backtest_wf.py`, `scripts/wf_run.py`; Test `tests/test_wf_engine.py`
**Interfaces:** `run_folds(component_config, folds=ANCHORED_FOLDS) -> dict` — `ANCHORED_FOLDS = [(2018..2020→2021), (2018..2021→2022), (2018..2022→2023)]` frozen constant; per fold: baseline vs component expectancy_r/N/WR, pooled deltas, pass/fail per the pre-registered gate; JSON + table output. Reuses the existing backtest engine with frictions on.
- [ ] Failing tests (fold boundaries respected — no test-year bar reachable in train; gate logic on synthetic results) → implement → commit `feat: anchored walk-forward harness`
- *(Ordering note: E39 is built immediately after E32; E33's decision runs then execute. The numbering keeps the decision record adjacent to the components it judges.)*

### Task E40: Shadow forward-gate

**Files:** Modify shadow logger (v2 Task 86 infra) + `scripts/shadow_component_report.py`
**Interfaces:** any fold-passing component runs 4 weeks in shadow (both variants logged); report compares realized signal quality (would-be entries' 10-day forward returns) component-on vs off; promotion = user flips the flag after reading the report. Pre-registered promotion bar: component-on cohort forward expectancy ≥ component-off.
- [ ] Failing tests (report math on fixture shadow logs) → implement → commit `feat: component shadow forward-gate`

### Task E41: Permutation test (reality check)

**Files:** Create `scripts/permutation_test.py`; Test `tests/test_wf_engine.py`
**Interfaces:** `p_value(strategy_config, n_perm=200) -> float` — re-runs fold tests with entry dates circularly shifted by random offsets (destroys signal, preserves autocorrelation); a component whose real expectancy beats <95% of permuted runs is flagged "indistinguishable from luck" in the fold doc.
- [ ] Failing tests (planted signal → low p; pure noise → high p, seeded) → implement → commit `feat: permutation reality check`

### Task E42: Parameter-plateau report

**Files:** Modify `backtest_wf.py`
**Interfaces:** `plateau_report(component, param, grid) -> dict` — expectancy across the param neighborhood; adopted values must sit on a plateau (neighbors within 0.03R), never on a spike. Auto-appended to fold docs.
- [ ] Failing tests (spike vs plateau fixtures) → implement → commit `feat: parameter plateau check`

### Task E43: Feature ablation harness

**Files:** Create `scripts/ablation.py`
**Interfaces:** with all adopted components on, remove one at a time across folds → contribution table; components contributing <0.01R pooled are candidates for removal (simplicity is robustness). Run + commit table after E33 adoption.
- [ ] Implement + run → commit `feat: ablation harness + first table`

### Task E44: Phase E2/E3 checkpoint

- [ ] Full suite; fold doc, permutation p-values, plateau evidence, ablation table all committed; adopted flag defaults recorded (still shadow-only). Commit `docs: edge components adopted (evidence pack)`.

---

# Phase E3 — Campaign & survival systems (E45–E56)

### Task E45: Drawdown throttle ladder

**Files:** Create `swingbot/core/edge/throttle.py`; config `DD_THROTTLE_ENABLED`
**Interfaces:** frozen ladder — equity DD from peak >8%: risk ×0.75; >12%: ×0.5; >16%: ×0.25; >20%: new entries paused until DD <15% (hysteresis). `current_throttle(equity_curve) -> float`. Applied inside effective-risk (E5 min-chain).
- [ ] Failing tests (each rung + hysteresis path) → implement → commit `feat: drawdown throttle ladder`

### Task E46: Loss-streak damper

**Files:** Modify `throttle.py`
**Interfaces:** `streak_multiplier(recent_closed) -> float` — 4 consecutive losses: ×0.5 next entries; recovers to ×1.0 after 2 wins. Combines multiplicatively with the DD ladder, floor 0.25.
- [ ] Failing tests → implement → commit `feat: loss-streak damper`

### Task E47: Kill switch

**Files:** Modify `throttle.py` + scan loop + `!killswitch` command + admin banner
**Interfaces:** hard pause of ALL new entries when: DD >20%, or SPY daily move beyond ±5%, or data-quality failures >20% of universe (broken feed). Manual `!killswitch on|off|status`. State in `data/killswitch.json` (jsonio). Alerts still generated + labeled `⛔ ENTRIES PAUSED (kill switch)` — informed, not blind.
- [ ] Failing tests (each trigger; manual override; label) → implement → commit `feat: kill switch`

### Task E48: Stale-position recycler

**Files:** Modify `plan_manager.py`
**Interfaces:** positions past `optimal_time_stop_days` (E32) with <0.3R progress emit a `♻️ recycle candidate` notice (capital sitting in dead trades is frequency lost — the compounding lever). Advice-only.
- [ ] Failing tests → implement → commit `feat: stale-position notices`

### Task E49: Sector concentration cap

**Files:** Modify `heat.py`
**Interfaces:** max open heat per sector `SECTOR_HEAT_CAP_PCT` (default 3.0) using universe sector tags; same flagged-not-hidden blocking as E7.
- [ ] Failing tests → implement → commit `feat: sector heat cap`

### Task E50: Portfolio replay backtest mode

**Files:** Modify `backtest.py` (`--portfolio` mode); Test `tests/test_wf_portfolio.py`
**Interfaces:** chronological replay of ALL signals under real constraints (heat cap, correlation cap, sector cap, throttles, sizing mode) → equity curve + max DD + realized trades/month; THE number that feeds honest 10x ETAs (per-signal expectancy overstates growth when capital is constrained).
- [ ] Failing tests (heat cap forces signal skips deterministically on fixtures) → implement → commit `feat: portfolio-level replay`

### Task E51: Portfolio replay of the adopted system

- [ ] Run `--portfolio` over TRAIN folds with adopted components + quarter-Kelly + throttles: record CAGR, max DD, trades/month, Monte Carlo p_ruin at 3 risk levels → `docs/superpowers/results/2026-XX-edge-portfolio.md`. This doc IS the honest growth expectation. Commit.

### Task E52: `!portfolio` command

**Files:** New renderer in `commands/trades.py` or `commands/growth.py`
**Interfaces:** open heat vs cap, per-sector bars, correlation clusters, current throttle multiplier, kill-switch state, growth-path summary — the survival dashboard in one embed.
- [ ] Failing tests (renderer) → implement → commit `feat: !portfolio survival dashboard`

### Task E53: Weekly risk report

**Files:** Retrospective hook + `edge/` reporter
**Interfaces:** Sunday post: week's heat utilization, biggest correlated cluster, throttle activations, Monte Carlo refresh on updated R-history, growth-path delta.
- [ ] Failing tests → implement → commit `feat: weekly risk report`

### Task E54: Admin risk panel

**Files:** Admin page (or dashboard cards if cockpit Part 3 absent — degrade gracefully)
**Interfaces:** heat gauge, sector bars, throttle state, kill switch toggle (POST with confirm).
- [ ] Failing tests (route + toggle) → implement → commit `feat: admin risk panel`

### Task E55: Sizing-mode shadow comparison

- [ ] Operational: run 4 weeks logging what kelly/vol-target/min-of-all WOULD have sized vs actual (shadow columns in trades records); report script compares realized growth per mode. Decision recorded; user flips `POSITION_SIZING_MODE` deliberately. Commit report.

### Task E56: Phase E3 checkpoint

- [ ] Full suite; portfolio doc + risk surfaces live-smoked in test channel. Commit `docs: survival systems checkpoint`.

---

# Phase E4 — Decision charts v3 (E57–E76)

All renders use `chart_style.py` constants; every new chart has a file-exists + no-crash test on synthetic data (`tests/test_decision_chart.py`, `tests/test_portfolio_charts.py`); wired behind the existing chart entry points.

### Task E57: `decision_chart.py` skeleton — the one-pager

**Files:** Create `swingbot/core/charts/decision_chart.py`
**Interfaces:** `render_decision_chart(symbol, daily_df, plan, context: dict, out_dir) -> str` — composite figure: main daily panel (candles + plan levels reusing trade_chart drawing), weekly context panel, RS strip, info column. `context` keys land in E58–E66. This becomes the alert chart when `DECISION_CHART_ENABLED` (default off until E67).
- [ ] Test (renders with minimal context) → implement grid layout → commit `feat: decision chart skeleton`

### Task E58: Weekly context panel

- [ ] Weekly resample candles, 10/40-week EMAs, weekly pivot levels; current week highlighted. Test + commit `feat: weekly panel`.

### Task E59: Anchored VWAP overlays on the main panel

- [ ] E30 AVWAPs drawn (distinct color, anchor markers ⚓). Test + commit `feat: AVWAP overlay`.

### Task E60: RS strip panel

- [ ] 63-day RS-vs-SPY line with 50th-pctile shading; current percentile annotated. Test + commit `feat: RS strip`.

### Task E61: Regime background shading

- [ ] Main panel background tinted by regime2 series (quiet/volatile × bull/bear = 4 alphas of green/red); legend chip. Test + commit `feat: regime shading`.

### Task E62: Historical outcome cloud

**Interfaces:** for the plan's strategy: past fold-trade outcomes at similar setups drawn as translucent forward R-paths from entry (green wins/red losses) projected from the current entry point — the trader SEES the distribution they're buying. Data from fold results cache; ≥20 samples or panel omitted.
- [ ] Test + commit `feat: outcome cloud`.

### Task E63: Expected-value cone

- [ ] P25/P50/P75 MFE trajectory cone (from E32 distributions) overlaid to TP zones; EV per R annotated. Test + commit `feat: EV cone`.

### Task E64: Gap-risk band

- [ ] P90 overnight gap band drawn around the stop (E17); `gap_fragile` plans get the ⚠ label on the band. Test + commit `feat: gap band`.

### Task E65: Sizing math box

- [ ] Info column block: risk %, source of the min() (config/kelly/vol-target/throttle), shares, heat before→after, cluster note. Test + commit `feat: sizing math box`.

### Task E66: Quality + follow-score box

- [ ] Info column: quality v2 component bars, follow score chip, badge + OOS stats, advisor verdict when present. Test + commit `feat: quality box`.

### Task E67: Decision chart wired to alerts

- [ ] Config Field `DECISION_CHART_ENABLED` (default off); alert path renders it instead of the legacy chart when on; chart cache (cockpit B34 if present, else direct); side-by-side smoke in test channel. Commit `feat: decision charts on alerts (flag)`.

### Task E68: `portfolio_charts.py` — heat treemap

**Files:** Create `swingbot/core/charts/portfolio_charts.py`
**Interfaces:** `render_heat_map(open_trades, caps) -> str` — nested rectangles: sector → position, area = heat, color = current R. Attached to `!portfolio`.
- [ ] Test + commit `feat: heat treemap`.

### Task E69: Correlation heatmap image

- [ ] `render_corr_matrix(open_trades, dfs)` — 90d returns-corr matrix, >0.75 cells outlined. Test + commit `feat: correlation heatmap`.

### Task E70: Monte Carlo fan chart

- [ ] `render_mc_fan(sim_result, start_balance)` — P5/P25/P50/P75/P95 equity paths, 10x line drawn, p_10x + max-DD annotations. Attached to `!growth`. Test + commit `feat: Monte Carlo fan`.

### Task E71: Growth-path chart

- [ ] `render_growth_path(equity_curve, target=10)` — actual curve vs required-rate curves for 3/5/8-year 10x; current multiple marker. Test + commit `feat: growth-path chart`.

### Task E72: Regime timeline chart

- [ ] SPY 2y with regime shading + per-regime live win-rate table strip; for `!regime`. Test + commit `feat: regime timeline`.

### Task E73: Fold-evidence chart

- [ ] `render_fold_evidence(component_results)` — per-fold expectancy deltas as grouped bars with the pass-gate line; embedded in fold docs + admin. Test + commit `feat: fold evidence chart`.

### Task E74: Chart render performance pass

- [ ] Profile decision chart (target <3s warm on CX23); precompute/copy shared panels, reuse figure where safe, assert wall-time bound in a local (non-CI) benchmark note. Commit `perf: decision chart under 3s`.

### Task E75: Chart visual QA

- [ ] Render the full set against 5 real tickers + SPY; eyeball at Discord sizes (readable at 400px height); fix label collisions (existing `_spread_labels` reuse). Notes + commit `style: chart QA pass`.

### Task E76: Phase E4 checkpoint

- [ ] Full suite; all charts smoke in test channel; screenshots archived under `docs/superpowers/results/charts-v3/`. Commit.

---

# Phase E5 — Frequency scale-up (E77–E88)

### Task E77: Universe rollout — top-150 by liquidity

- [ ] Flip `SCAN_UNIVERSE` to a `sp500_top150.json` (built by E13 script, liquidity-ranked) in production; watch one week of scan durations + alert volume. Alert flood control: config `MAX_ALERTS_PER_SCAN` (default 10) — ranked by follow score, remainder to a digest line. Commit config + notes.

### Task E78: Signal dedup at portfolio level

**Files:** Modify scan engine dedup
**Interfaces:** cross-ticker dedup — multiple same-sector signals in one scan collapse to the highest follow-score one + a "also qualifying: X, Y" line (correlation cap would block the rest anyway; don't tease untakeable trades).
- [ ] Failing tests → implement → commit `feat: portfolio-aware signal dedup`

### Task E79: Per-horizon capacity budget

- [ ] `MAX_OPEN_PER_HORIZON` (default 4) — spreads capital across time horizons so a single horizon's regime doesn't own the book. Tests + commit.

### Task E80: ETF baseline strategies fold-run

- [ ] Run existing validated strategies over the ETF universe through the fold harness (indices trend cleaner; expect S/R + Break&Retest to pass); registry entries per the standard process; results doc. Commit `docs: ETF fold results`.

### Task E81: Universe RS rotation report

- [ ] Weekly post: top/bottom RS deciles of the universe, sector rotation table — where the next trades likely come from. Tests + commit.

### Task E82: Scan health telemetry

- [ ] Per-scan JSON line (duration, tickers, errors, signals, alerts) to `data/scan_telemetry.jsonl`; admin sparkline; alert if scan duration doubles. Tests + commit.

### Task E83: Memory ceiling guard

- [ ] CX23 8GB: cap concurrent loaded DataFrames (LRU release in the scan loop), assert RSS < 2.5GB in the E77 dry-run notes. Commit.

### Task E84: Full-500 rollout decision

- [ ] Operational: if 150-ticker telemetry is healthy 2 weeks, flip to full sp500 + ETFs; else document the ceiling and stay. Notes committed.

### Task E85: Frequency impact measurement

- [ ] Report: valid signals/month before vs after universe expansion; recompute `!growth` ETA with the real new frequency. THE payoff measurement of this phase. Commit report.

### Task E86: Alert routing by tier

- [ ] Config: tier-A VALIDATED alerts → main channel; the rest → a `#scanner-firehose` channel id Field (default same channel = no change). Tests + commit.

### Task E87: Weekend full-universe deep scan

- [ ] Saturday job: full-universe scan at relaxed thresholds → watchlist candidates report (feeds Monday's curated watchlist). Tests + commit.

### Task E88: Phase E5 checkpoint

- [ ] Suite green; telemetry healthy; frequency report committed.

---

# Phase E6 — Final verification & governance (E89–E100)

### Task E89: Full-system walk-forward re-run

- [ ] Everything adopted, portfolio mode, frictions on, folds 2021/22/23: the complete evidence pack regenerated in one command (`scripts/wf_run.py --full`); committed doc.

### Task E90: Full-system permutation test

- [ ] E41 against the final system; p-value in the doc. If p > 0.05, STOP and strip components until the edge is real — pre-registered rule.

### Task E91: Sensitivity table

- [ ] Final system at slippage 5/10/20 bps and risk 0.5/1.0/1.5% → expectancy + growth + p_ruin grid; the "how wrong can our assumptions be" table. Commit.

### Task E92: The single 2024–2025 shot

- [ ] **Pre-registered, run once:** pooled final system, portfolio mode, on the held-out window. Gates: expectancy_r > 0 after frictions, max DD < 25%, and per-strategy WR within 10 points of fold results. Reported as-is regardless of outcome; failing components revert to their pre-E33 state. Commit verbatim results.

### Task E93: 4-week live paper forward-test

- [ ] All flags on in shadow/paper (no real behavioral change vs current live until this gate passes); weekly comparison snapshots; promotion decision doc at the end. The market's own out-of-sample is the only judge left.

### Task E94: Promotion + rollback plan

- [ ] Flip adopted flags live; documented one-line rollback per flag; `docs/superpowers/results/2026-XX-edge-final.md` records what went live and why.

### Task E95: Pre-mortem document

- [ ] `docs/superpowers/edge-premortem.md`: the ways this system dies (regime break, liquidity evaporation, correlated gap, data feed corruption, overfit residue, user overriding throttles) and the built-in tripwire for each (kill switch, drift alerts, permutation re-runs, throttle ladder). Honest, specific, committed.

### Task E96: Quarterly re-validation cron

- [ ] Documented quarterly ritual + script: refresh folds with the newest completed year, re-run drift/permutation, rotate the fold set forward. Calendar note in README.

### Task E97: Risk disclosure in every surface

- [ ] Footer audit: growth/portfolio/decision charts and `!growth` carry "Backtested + paper-tested projections. Real results will differ. Risk of loss is real." — verify + test presence.

### Task E98: Docs — the growth playbook

- [ ] README section: the growth equation, the three levers, what the throttles do, how to read the fan chart, why the system will never promise 100% WR — written for future-you in a drawdown.

### Task E99: Performance + integration sweep

- [ ] Full suite, `make check`, scan-cycle timing with everything on, memory check, chart timing, one full day of live operation reviewed. Fix stragglers.

### Task E100: Final checkpoint

- [ ] Progress block completed; evidence pack index (baseline → folds → ablation → portfolio → 2024–25 shot → paper gate) linked from README. **Plan complete — the honest maximum-growth configuration of this bot, with its real ETA visible in `!growth`.**
