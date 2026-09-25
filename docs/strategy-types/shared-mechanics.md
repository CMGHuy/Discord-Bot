# Shared mechanics (every strategy)

The per-strategy pages describe what is unique to each strategy. This page is
everything they share: the tape gates, the three sizing families, the 2% cap,
the level-lifecycle stop, the exit model, direction/horizon gates, and how to
read a registry badge. Traced from code on 2026-09-25 (`main` at `6dd9636d`).

## 1. One entry function, three consumers

Every strategy has exactly one entry function in
`swingbot/core/market/entry_filters.py`, registered as `ENTRY_FUNCS[name]`. It
returns two boolean series (bullish, bearish) per ticker × horizon.
`entries_for(strategy, df, horizon)` calls it and then applies
`STRATEGY_GATES` and the regime gate. That one call feeds:

1. **the backtest** (`backtest.py`),
2. **the badge registry** (`validation_registry.json`, scored from backtests),
3. **live strategy alerts** (the v93 path, controlled by `STRATEGY_ALERTS_MODE`
   `off`/`shadow`/`live`, default `off`, with `STRATEGY_ALERTS_LIVE_STRATEGIES`).

The per-strategy `*_signal` functions in `signals.py` build the scanner's
`SignalResult`: trend, triggered flag and embed details. Where they decide
"triggered", they call `entries_for`, so they cannot disagree with the
backtest about when a setup fires.

## 2. Shared gates (`compute_shared_gates`)

| Gate | Definition | Used by |
|---|---|---|
| `bull_regime` | `close > MA200` and `MA200 > MA200[t−20]` | all bullish rules except RSI |
| `bull_regime_slope_only` | `MA200 > MA200[t−120]` | RSI (dip-buys sit below the MAs by construction) |
| `bear_regime` | `MA200 < MA200[t−120]` and `close < MA200` | all bearish rules |
| `trend50_bull` / `trend50_bear` | `close > MA50` / `close < MA50` | all except RSI |
| `atr_floor` | `ATR14 / close ≥ 0.7%` (`ATR_FLOOR_PCT`): skip dead tape | all |
| `atr_calm` | `ATR14 ≤ 1.4 × mean60(ATR14)` (`ATR_CALM_MULT`): skip panic tape | all |
| `vol_ok` | `Volume ≥ 0.9 × mean20(Volume)` (`VOL_OK_MULT`) | all except S/R and Break & Retest, which have their own volume rules |

MAs are simple moving averages of close. RSI and ATR use Wilder smoothing.
The regime gate in `entries_for` (`REGIME_GATES_ENABLED` / `REGIME_ALLOW`) is
off and `{}`, and its v17 pre-registration is closed.

## 3. Direction and horizon gates (`STRATEGY_GATES`)

| Strategy | Directions | Horizons |
|---|---|---|
| Fibonacci | bullish | all |
| Fibonacci Continuation | **none (masked)** | — |
| RSI | bullish | all |
| MA Ribbon | bullish | all |
| VWAP | bullish | 4w |
| Support/Resistance | bullish | 2m, 3m |
| MACD | bullish | 3m, 4m, 7m, 8m, 9m |
| Volume Profile | bullish | 7m |
| Break & Retest | both | 2m, 3m, 4m |
| EMA Crossover, RSI Divergence, Elliott Wave | both | all (Elliott fires on 4w only, by its own rule) |

Most comments beside these gates carry **pre-v31 figures and say so ("stale")**.
Only VWAP and Break & Retest were re-derived under current arithmetic (v84).

## 4. Sizing: three families

Entry is the signal bar's close (`STRATEGY_ENTRY_TYPE` is empty, so every
strategy uses a market entry at the trigger price). `build_strategy_plan`
(live) and `_trade_plan_at` (backtest) share the builders in
`swingbot/core/planning/builders.py`.

| Family | Strategies | Stop | TP1 candidates |
|---|---|---|---|
| **ATR** (`_atr_plan`) | EMA Crossover, VWAP, RSI, MACD, MA Ribbon, Break & Retest, RSI Divergence, Volume Profile | `2 × ATR14` (`atr_stop_multiple`), times an optional MAE multiplier (off) and the monthly-opex widening (`OPEX_STOP_WIDEN_PCT`) | the ATR ladder `entry ± k·ATR`, k ∈ {1, 2, 3, 4, 5, 6, 8, 10} |
| **Structural** | Fibonacci, Support/Resistance, Elliott Wave, Fibonacci Continuation | derived from the strategy's own structure (see each page) | the strategy's own levels (see each page) |

The rules shared by every family:

- **2% cap in the builder.** A stop more than
  `capped_planned_loss_pct(h["max_risk_pct"]) = min(max_risk_pct, 2.0)`% from
  entry is pulled in to exactly that distance. Every horizon's
  `max_risk_pct` is ≥ 3, so **the builder's cap is always 2%**. The exceptions
  are the v103 level stop and Fibonacci Continuation, which reject the plan
  instead of capping.
- **TP1 = `select_structural_target`.** It picks the nearest candidate beyond
  entry that pays ≥ `MIN_RISK_REWARD_RATIO` (1.5R). If the nearest qualifying
  one is beyond `MAX_RISK_REWARD_RATIO` (2.5R), TP1 is placed synthetically at
  exactly 2.5R. **If none clears 1.5R, no plan is built.** No fallback exists.
- **ATR family in practice:** with no cap, risk = 2 ATR, so the floor is 3 ATR
  and TP1 lands on the ladder's 3-ATR rung (1.5R). When ATR > 1% of price the
  2% cap binds, risk < 2 ATR, and TP1 is the first ladder rung ≥ 1.5R.

### 4a. Level lifecycle stop, and a 2% cap finding

After the builder, `apply_level_lifecycle` (`planning/lifecycle.py`) runs on
**every** strategy, live and in the backtest. It is gated by
`LEVEL_LIFECYCLE_STOPS_ENABLED`, which defaults to **true**. If the nearest
level behind the stop has been **tested** and held, the stop is moved to
`level ∓ 0.25 ATR`, **widen-only**, and TP1 is re-selected against the new
risk. If no candidate still clears 1.5R, the widening is rolled back.

> **Finding (2026-09-25): the widening is bounded by the horizon's
> `max_risk_pct` (3–11%), not by the 2% cap.** Nothing in the backtest
> re-checks the cap afterwards. A spot check on 5 tickers (AAPL, MSFT, NVDA,
> JPM, AMD) × Fibonacci/MACD/Support-Resistance × 4w/3m/6m found:
> - **lifecycle on:** **22 of 83 backtest trades had an initial stop wider
>   than 2%, the worst at 8.87%;**
> - **lifecycle off:** the worst was exactly 2.00%.
>
> On the live path a pending plan whose fill would breach 2% is cancelled
> (`plan_manager.py`, `cancelled_risk_cap`). The backtest has no equivalent,
> so it scores trades that live would cancel. That is a backtest ≠ live gap,
> and it affects every strategy's post-cap badge and TRAIN figures, including
> v101–v103. Not yet fixed; it needs its own plan (`Edge: none (integrity)`).
> Script: scratch `cap_check.py` in the 2026-09-25 session, a
> `run_backtest(..., exit_model="v2", scale_out=True, tp2_mode="levels",
> frictions=True)` sweep comparing `|entry − stop_loss| / entry`.

## 5. Exits (exit model v2)

Every plan has `TP1_FRACTION = 0.5`: half the position exits at TP1. After
that, the runner's stop locks in ⅔ of the entry→TP1 move
(`RUNNER_FLOOR_FRACTION`) and then trails a chandelier stop of
`trail_atr_mult × ATR`. `BREAKEVEN_TRIGGER_FRACTION = 0.5` moves the stop to
entry once price covers half the distance to target, and an exit there counts
as a scratch. Pending plans expire after `DEFAULT_EXPIRY_BARS = 5`. Holding is
capped at `max_holding_days` (timeout).

Per-strategy overrides (`planning/params.py` → `EXIT_V2_PARAMS`). A missing
key gets the defaults `trail 2.5, tp2 on`:

| Strategy | Trail (× ATR) | TP2 |
|---|---|---|
| VWAP | 2.5 | off |
| Fibonacci | 3.0 | off |
| RSI | 2.0 | off |
| MACD | 2.0 | on |
| MA Ribbon | 2.5 | off |
| Break & Retest | 3.0 | off |
| RSI Divergence | 2.0 | off |
| Volume Profile | 3.0 | off |
| Fibonacci Continuation | 2.5 | on |
| EMA Crossover, Support/Resistance, Elliott Wave | 2.5 (default) | on (default) |

When TP2 is on, it is the first clustered level-map level beyond TP1, and the
TP1→TP2 leg is capped at 3× the entry→TP1 leg (`MAX_TARGET2_LEG_MULTIPLE`).
The `N= WR= ExpR=` comments beside `EXIT_V2_PARAMS` come from the 2026-07
exit-v2 TRAIN grid, which ran before v31 and before the 2% cap. They are
**not** current performance.

## 6. Reading a badge

`swingbot/core/backtesting/validation_registry.json` holds one row per
strategy. Before quoting a row, check its `run_date`:

| run_date | Means |
|---|---|
| 2026-07-18 | **pre-v31** (v31 structural targets landed 2026-08-16): old target arithmetic, stale |
| 2026-08-17 | v31 VALIDATION shots, current targets, **before the 2% cap** (2026-09-21) |
| 2026-09-10 | legacy badge refresh (TRAIN only), before the 2% cap |

**No registry row post-dates the 2% cap.** Every figure on these pages is also
subject to the §4a lifecycle finding.

## 7. Horizon parameters

`HORIZONS` in `strategy_types.py`. `atr_stop_multiple` is 2.0 everywhere.

| | 2w | 4w | 2m | 3m | 4m | 5m | 6m | 7m | 8m | 9m |
|---|---|---|---|---|---|---|---|---|---|---|
| `ema_fast` / `ema_slow` | 8/13 | 9/21 | 14/35 | 20/50 | 30/100 | 40/150 | 50/200 | 60/250 | 70/300 | 80/350 |
| `vwap_window` | 10 | 21 | 42 | 63 | 84 | 105 | 126 | 147 | 168 | 189 |
| `fib_lookback` | 15 | 42 | 84 | 126 | 168 | 210 | 252 | 294 | 336 | 378 |
| `sr_lookback` | 10 | 30 | 60 | 90 | 120 | 150 | 180 | 210 | 240 | 270 |
| `max_risk_pct` | 3.0 | 7.0 | 8.0 | 9.0 | 9.3 | 9.7 | 10.0 | 10.3 | 10.7 | 11.0 |
| `max_holding_days` | 14 | 28 | 60 | 90 | 120 | 150 | 180 | 210 | 240 | 270 |
