# Strategy Win-Rate Redesign — Design Spec

**Date:** 2026-07-10
**Goal:** Every strategy in `swingbot/core` (EMA Crossover, VWAP, Fibonacci, Support/Resistance, RSI, MACD, Elliott Wave, MA Ribbon, Break & Retest, RSI Divergence, Volume Profile) achieves **≥ 80% win rate AND positive expectancy** on out-of-sample backtest data, with the live bot recommending exactly the trades the backtest measured.

---

## 1. Problem statement

The codebase already went through one "≥80% win rate" tuning pass, and it took the wrong lever:

1. **`STRATEGY_RR_OVERRIDE` in `backtest.py` sets take-profit at 0.10–0.12× the stop distance.** At R:R = 0.10 the break-even win rate is 1/(1+0.10) ≈ **91%**. A strategy can print 85% win rate and still lose money — one stop-out erases ten wins. The `!backtest` command's own help text admits this.
2. **Live/backtest drift.** The live bot's `trade_plan.py` ignores `STRATEGY_RR_OVERRIDE` and sizes targets from `HORIZONS[h]["reward_risk_ratio"]` (0.40–1.25R). The backtest therefore measures trades the live bot never recommends, and vice versa. Backtest entry conditions (`_vectorized_entries` in `backtest.py`) have also drifted far from the live signal functions (`signals.py`) — the backtest has ~6 extra filters per strategy that live alerts don't apply.
3. **Timeouts are invisible.** Trades that hit neither stop nor target within `max_holding_days` are excluded from both win rate and expectancy. A trade that drifts −6% for 60 days simply vanishes from the stats.
4. **`run_backtest_2025.py` is broken** (imports `WATCHLIST` from `swingbot.config`, which no longer exists — the watchlist lives in `data/watchlist.json`) and only evaluates 2025, a bull year.

## 2. Success criteria (acceptance gate)

Measured by the new harness (§4) on the **validation window, which the tuning process never reads until the end**:

| Metric | Requirement |
|---|---|
| Win rate per strategy (all horizons + both directions pooled, whole watchlist) | ≥ 80%, where win rate = wins / (wins + losses) |
| Expectancy per strategy | > 0 R per closed trade, computed over ALL closed trades: wins, losses, break-even scratches (≈0 R), and timeouts marked-to-market at the timeout bar's close |
| Sample size per strategy | ≥ 30 evaluated (win/loss) trades on train, ≥ 15 on validation. Below that the number is noise, not evidence |
| Honesty guard | scratches + timeouts together ≤ 50% of all closed trades per strategy (prevents gaming win rate by pushing everything into the "excluded" buckets) |

- **Train window:** entries 2020-01-01 → 2023-12-31 (covers COVID crash, 2021 bull, 2022 bear).
- **Validation window:** entries 2024-01-01 → 2025-12-31. Tuning must never look at it; it is run once per strategy at the end, and the numbers reported are whatever they are.
- **Universe:** the ~60 tickers in `data/watchlist.json` at implementation time (snapshot the list into the harness config so results are reproducible).
- **Failure policy (explicit):** if a strategy cannot clear the bar with honest improvements, first *gate* it — restrict it to the horizons and directions where it passes on train (e.g. long-only, 4w+2m only), re-validate. If it still fails, report it as failing in the final results table. Do NOT shrink targets below R:R 0.30 to fake the number.

## 3. Architecture changes

### 3.1 Single source of truth for entry logic (kills live/backtest drift)

New module: **`swingbot/core/entry_filters.py`**.

For each strategy, one function computes the entry conditions **as boolean Series over the whole DataFrame**:

```python
def ema_cross_entries(df: pd.DataFrame, horizon_key: str) -> tuple[pd.Series, pd.Series]:
    """Returns (bullish_entries, bearish_entries) — True on bars where a
    fresh entry signal fires. Uses only data up to and including each bar
    (no lookahead: every rolling/shift references past bars only)."""
```

- `backtest.py::_vectorized_entries` becomes a thin dispatcher into these functions (the per-strategy `if` blocks are deleted).
- `signals.py` signal functions call the same function and read `.iloc[-1]` to decide `triggered` for the live scan. The existing `SignalResult` shape, `details` dicts, and non-triggered "bias" reporting stay as they are — only the *trigger* condition is replaced.
- Shared gates (§5) live in this module too, so a filter change automatically applies to both worlds.
- **No-lookahead rule:** every condition may reference only bar `i` and earlier (`shift`, `rolling` on past bars). This must be stated in the module docstring and respected by every filter.

### 3.2 Single source of truth for trade plans

- Move `STRATEGY_RR_OVERRIDE` from `backtest.py` into `strategy_types.py` with new values (§6). `backtest.py` re-exports it so existing imports keep working.
- `trade_plan.py` must consume it: after computing stop distance the same way it does today, the take-profit becomes `entry ± risk × STRATEGY_RR_OVERRIDE[strategy]`. `HORIZONS[h]["reward_risk_ratio"]` remains only as a fallback for strategies absent from the override map (there should be none).
- **Consumer reality check (verified during design):** `trade_plan.compute_trade_plan` is currently called by no live code path — live scan alerts flow through the separate confluence pipeline (`scanning/` + `levels.py`, out of scope §10), and strategy signals reach users via the `/info` command → `evaluate_all` → `signals.py`. `trade_plan.py` is still updated because it is the documented plan generator that `backtest._trade_plan_at` mirrors, and the two must not drift.
- `backtest.py::_trade_plan_at` keeps mirroring `trade_plan.py` (as today) but both now read the same constants.
- `TradePlan` gains a `management_note: str` field stating the §7 rule ("after price covers half the distance to target, move stop to entry — a break-even exit is a scratch, not a loss") so any current or future renderer of a strategy trade plan shows the management rule the backtest assumes.

### 3.3 Data cache + reusable harness

- **`scripts/fetch_backtest_data.py`** — downloads daily OHLCV for every watchlist ticker, **2018-06-01 → 2025-12-31** (≥ 18 months warm-up before the train window: the regime gate needs 200-SMA + a 120-bar shift ≈ 320 bars before it can pass), via yfinance with `auto_adjust=True`; saves one **CSV** per ticker under `data/backtest_cache/` (CSV, not parquet — the environment has no pyarrow and the data is small). Skips tickers already cached (delete the folder to force refresh). Handles yfinance MultiIndex columns (flatten to `Open/High/Low/Close/Volume`).
- **`scripts/run_backtest_range.py`** (replaces `run_backtest_2025.py`) — loads from the cache (no network), runs all strategies × horizons × tickers with `one_at_a_time=True`, filters trades to an eval window given by `--from/--to` (presets `--train`, `--validation`), and prints/saves the per-strategy pooled table: evaluated N, win rate, expectancy_r (all-closed-trades definition), scratch %, timeout %, and a pass/fail flag against §2. Also emits per-strategy×horizon breakdown for the gating decisions in §2's failure policy.
- **`scripts/tune_strategy.py`** — grid sweep for one strategy over its small tunable set (§8), train window only, prints ranked configurations.

## 4. Metrics engine changes (`backtest.py`)

Outcome taxonomy becomes four-valued: `win | loss | scratch | timeout`.

- **win / loss** — target/stop hit first, as today (stop wins same-bar ties — keep the conservative rule).
- **scratch** — the break-even stop (§7) was hit after being moved to entry. `r_multiple ≈ 0` (exactly 0 at entry price; report actual).
- **timeout** — `max_holding_days` elapsed. NEW: exit is marked-to-market at that bar's close; `return_pct`/`r_multiple` are computed from it instead of `None`.
- `win_rate = wins / (wins + losses)` (unchanged definition).
- `expectancy_r = mean(r_multiple over ALL closed trades)` — wins, losses, scratches, timeouts. This replaces the current wins/losses-only formula and is the number that must be > 0.
- `BacktestSummary` gains `scratches: int`; existing consumers (`swingbot/commands/backtest.py` formatting, `run_backtest_range.py`) are updated to show it.

## 5. Shared entry-quality gates (applied to every strategy, both directions)

Defined once in `entry_filters.py`:

| Gate | Bullish condition | Bearish condition |
|---|---|---|
| `regime` | close > 200-SMA **and** 200-SMA today > 200-SMA 20 bars ago | 200-SMA today < 200-SMA 120 bars ago (keep the existing strict 6-month-downtrend gate) **and** close < 200-SMA |
| `trend50` | close > 50-SMA | close < 50-SMA |
| `atr_floor` | ATR(14)/close ≥ 0.7% (skip dead-flat tape) | same |
| `atr_calm` | ATR(14) ≤ 1.4 × its own 60-bar mean (skip panic regimes) | same |
| `vol_ok` | volume ≥ 0.9 × 20-bar average volume | same |

**Exception — RSI (§8.5):** a dip-buyer is *supposed* to enter while price is temporarily below its moving averages, so the `regime` gate for RSI uses only the slope condition (200-SMA rising over 120 bars) without `close > 200-SMA`, and `trend50` is not applied to RSI. All other strategies take the full gate set.

Rationale: 2020–2025 was a structurally long-biased tape; the strict bearish regime gate keeps counter-trend shorts (the biggest current losers) out. If the bearish side of a strategy still fails on train after all improvements, the failure policy in §2 disables it for that strategy (long-only gating) — that is an accepted, documented outcome, not a hack.

When a horizon has fewer bars than a gate needs (e.g. 200-SMA slope on short history), the gate evaluates False (no entry) — never NaN-passes. `.fillna(False)` everywhere.

## 6. Reward:risk — move from 0.10 to the profitable zone

New `STRATEGY_RR_OVERRIDE` starting values (tunable within §8's grid, hard floor 0.30):

| Strategy family | Start R:R | Break-even WR | Target WR |
|---|---|---|---|
| Mean-reversion at structure (RSI, Fibonacci, Volume Profile, RSI Divergence) | 0.40 | 71.4% | ≥ 80% |
| Trend-continuation (EMA Crossover, VWAP, MACD, MA Ribbon, Elliott Wave) | 0.35 | 74.1% | ≥ 80% |
| Breakout (Support/Resistance, Break & Retest) | 0.35 | 74.1% | ≥ 80% |

At 80% WR and 0.35R with the §7 exit engine, expectancy ≈ 0.8×0.35 − 0.2×1.0 = **+0.08 R per trade** before scratches; scratches only improve it (they replace full losses).

Stops keep their current structure: ATR-multiple (2×ATR capped at `max_risk_pct`) for indicator strategies, structural swing±buffer for Fibonacci/Elliott, fixed-% for S/R — unchanged mechanics, single shared constants.

## 7. Exit engine: break-even stop (the honest win-rate lever)

This is how win rate rises without shrinking the target. In `run_backtest`'s walk-forward loop (and stated on live alerts):

- Let `T` = target distance (`|take_profit − entry|`), trigger level = `entry ± 0.5×T` (favorable direction).
- **When a bar's favorable extreme reaches the trigger level, the stop moves to entry** for all subsequent bars. (Check trigger using the bar's high/low; conservative ordering within the trigger bar itself: if the same bar reaches the trigger AND later would hit the original stop, the break-even move only protects *subsequent* bars — within the trigger bar the original stop still applies. Stop-wins-ties preserved.)
- Outcomes: original stop hit → `loss`; entry-stop hit after move → `scratch`; target hit → `win`.

Effect: a large fraction of trades that reach half-target but reverse — currently full 1R losses — become ≈0R scratches. Losses shrink in count; win rate (wins/(wins+losses)) rises; expectancy rises because 1R losses convert to 0R.

The 0.5×T trigger fraction is a tunable in §8 (candidates 0.4 / 0.5 / 0.6).

## 8. Per-strategy algorithm improvements

Each strategy gets: shared gates (§5) + the specific changes below, implemented once in `entry_filters.py`. The current backtest-only filters listed here as "keep" must also start applying to live alerts (that is the point of §3.1). Tunables are swept on train only via `scripts/tune_strategy.py`; everything else is fixed by design.

### 8.1 EMA Crossover (trend pullback-and-resume)
- Keep: 2-bar hold after cross; prior-pullback RSI filter (RSI dipped < 45 within 5 bars pre-cross for bull); momentum confirm (MACD > 0 or RSI > 60).
- Add: slow EMA rising — `ema_slow > ema_slow.shift(5)` for bull (mirror for bear). A cross inside a falling slow EMA is a counter-trend trap.
- Add: not-extended — close within 1.0 × ATR(14) of the fast EMA at entry (chasing extended crosses is where losses cluster).
- Tunables: RSI dip threshold {40, 45, 50}; extension cap {0.75, 1.0, 1.5} × ATR.

### 8.2 VWAP (value reclaim)
- Keep: 3-bar hold (2w) / 2-bar hold (others); VWAP trending in trade direction over 3 bars.
- Add: not-extended — close within 1.5% of VWAP at entry (reclaim entries near value, not after the move is spent).
- Add: RSI(14) between 50 and 65 for bull (above 50 = momentum, below 65 = not yet overbought); mirror 35–50 for bear.
- Tunables: extension cap {1.0%, 1.5%, 2.0%}; hold bars {2, 3}.

### 8.3 Fibonacci (retracement bounce) — algorithmic fix, not just filters
- **Fix swing direction:** current code takes `rolling(max)`/`rolling(min)` with no ordering, so a "bullish retracement" fires even when the swing high came *before* the swing low (i.e., a downtrend, where the level is resistance overhead, not support). New rule: bullish setups require `argmax(High, lookback) > argmin(Low, lookback)` — the up-impulse must be the *recent* structure (low first, then high, price now pulling back). Mirror for bearish.
- **Restrict levels:** bullish bounces only at 38.2% / 50% / 61.8% retracements (23.6% is too shallow to be a real pullback; 78.6% means the impulse has failed). Same tolerance mechanic (±2% of range) as today.
- Keep: pulled-back-then-bouncing shape (`close.shift(5) > close.shift(1)` and `close > close.shift(1)`), RSI band 35–58 bull.
- Add: bounce-bar quality — entry bar closes in its upper half (`close ≥ (high+low)/2`) for bull; mirror for bear.
- Stop stays structural (swing low − 0.25 ATR, capped at `max_risk_pct`); target from R:R override.
- Tunables: level set {38.2/50/61.8 vs 50/61.8 only}; RSI band edges.

### 8.4 Support/Resistance (breakout from a base)
- Keep: fresh cross of prior-window extreme; volume ≥ 1.5× 20-bar average; ATR-calm gate.
- Add: **base quality** — the 10 bars before breakout must be a tight range: `(rolling10 High.max − rolling10 Low.min) ≤ 4 × ATR(14)`, measured on the bars *before* the breakout bar. Breakouts from tight bases follow through; breakouts out of wide chop don't.
- Add: **close strength** — breakout bar closes in the top 40% of its own high-low range for bull (`close ≥ high − 0.4×(high−low)`); mirror for bear. Filters intraday-spike-and-fade breakouts.
- Add: **no exhaustion gap** — bar's open ≤ 3% above the broken resistance for bull; mirror for bear.
- Tunables: base tightness {3, 4, 5} × ATR; close-strength fraction {0.3, 0.4, 0.5}.

### 8.5 RSI (oversold bounce inside an uptrend)
- Keep: 2 consecutive bars RSI < 35 then recross ≥ 35; 200-SMA rising over 120 bars for bull; recovery confirmation (`close > close.shift(3)`); ATR-calm.
- Add: **trigger-bar confirmation** — entry bar's close > previous bar's high (the bounce is real, not an RSI wobble inside a falling knife). Mirror for bear.
- Tunables: oversold threshold {30, 35}; confirmation {close > prev high, close > prev close}.

### 8.6 MACD (momentum-regime cross)
- Keep: cross or 2-bar histogram hold; zero-line filter (bull only when MACD line > 0); horizon-scaled periods; RSI > 50 bull.
- Add: **histogram rising 2 bars** at entry (`hist > hist.shift(1) > hist.shift(2)` for bull) — enters while momentum is accelerating, not on a stalling cross. Mirror for bear.
- Add: not-extended — close within 1.0 × ATR of EMA(fast_p of MACD) — same rationale as 8.1.
- Tunables: extension cap {0.75, 1.0, 1.5} × ATR.

### 8.7 Elliott Wave (wave-3 breakout approximation)
- Keep: only the 4w horizon fires (documented reason: pivot approximation degrades elsewhere); RSI > 55 and rising for bull; volume gate.
- Add: wave-2 retracement depth check — wave 2 must retrace 30–80% of wave 1 (a textbook wave-2; beyond 80% invalidates the count). Depth = (wave1 − wave2) / (wave1 − wave0) for bullish (mirror for bearish). Requires a small backward-compatible change to `indicators.elliott_wave3_entries`: record `"wave0": p0` alongside the existing `wave1`/`wave2` keys in `entry_levels` (the pivot loop already has `p0` in scope).
- Tunables: retracement window {30–80%, 38–78%}.

### 8.8 MA Ribbon (aligned trend ignition)
- Keep: fast/mid cross with both above/below slow SMA; not-extended (within 8% of slow SMA); RSI bands; MACD sign agreement.
- Add: slow SMA slope agreement — slow SMA rising over 10 bars for bull; mirror for bear (alignment without slope is a sideways chop trap).
- Tunables: extension cap {6%, 8%, 10%}.

### 8.9 Break & Retest
- Keep: breakout within recent window on ≥1.5× volume; retest proximity band per horizon; RSI band; ATR-calm.
- Add: **retest hold + bounce** — the retest must hold the level (`low ≥ level × (1 − 0.5%)` on the entry bar for bull) AND the entry bar closes above the prior bar's high. Currently the signal fires while price is still falling into the level — entering before the retest proves anything.
- Tunables: hold tolerance {0.3%, 0.5%, 0.8%}; retest zone widths (keep current per-horizon table as start).

### 8.10 RSI Divergence (hidden divergence, trend continuation)
- Keep: hidden bull = price higher low + RSI lower low in a 20-bar window (rolling formulation in the vectorized version); trend gates.
- Add: **confirmation bar** — RSI back above 40 and rising (`rsi > rsi.shift(1)`) for bull at entry; mirror (RSI < 60 and falling) for bear. Divergence alone marks *potential*; entry needs the turn to have started.
- Tunables: RSI reclaim level {38, 40, 45}.

### 8.11 Volume Profile (HVN bounce)
- Keep: price within 1.5% above HVN for bull / below for bear (vectorized numpy HVN calc); RSI bands.
- Add: **node significance** — the HVN bucket must hold ≥ 8% of window volume (a dominant node is a real shelf; a marginal argmax is noise). The vectorized loop already computes bin volumes; keep the share alongside the level.
- Add: bounce confirmation — `close > close.shift(1)` for bull; mirror for bear.
- Tunables: node share {6%, 8%, 10%}; proximity band {1.0%, 1.5%, 2.0%}.

## 9. Tuning protocol (guardrails against overfitting)

1. Grid size per strategy ≤ ~20 combinations (2–3 tunables × 2–3 values). No optimizer beyond this.
2. Selection on **train only**: among configs meeting WR ≥ 80% ∧ expectancy > 0 ∧ N ≥ 30, pick max expectancy; if none meet the bar, pick max WR with expectancy > 0 and apply the §2 failure policy (gate horizons/directions).
3. **One** validation run per strategy at the very end. No iterating on validation numbers. If validation fails, report the failure — retuning on validation defeats the design.
4. Bearish sides that fail on train get disabled (long-only strategy) *before* validation, as part of the config, not after seeing validation results.

## 10. Out of scope

- Confluence backtest engine (`backtest_confluence.py`) — it consumes `_vectorized_entries`, so it inherits the improvements automatically; its own thresholds (`CONFLUENCE_*`) are not retuned.
- Charts, embeds, Discord command UX beyond adding the scratch column and updated help text (the `!backtest` help text explaining win-rate-vs-expectancy should be rewritten to describe the new engine).
- Options, intraday data, position sizing, portfolio simulation.
- Adding/removing strategies from the registry.

## 11. Risks stated plainly

- **2024–2025 validation is still a mostly-bull tape.** Passing validation is evidence, not proof. The equity-curve honesty caveats in `backtest.py`'s docstring (survivorship bias, no slippage/fees, independent trades) all still apply and stay in the docs.
- **Some strategies may not make it.** RSI Divergence and Volume Profile are the weakest concepts (loose pattern definitions); the failure policy exists for them.
- **Signal frequency will drop** — accepted per requirements ("quality over quantity", floor of statistical meaningfulness only).
