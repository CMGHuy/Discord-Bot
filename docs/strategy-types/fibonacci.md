# Fibonacci retracement strategy

How the bot's `"Fibonacci"` strategy finds a setup, sizes a trade, and exits it,
traced from the code as of 2026-09-25 (`main` at `6dd9636d`). Code is
authoritative. If this page and the code disagree, the code wins and this page
is stale.

| What | Where |
|---|---|
| Entry rule (backtest and live share it) | `swingbot/core/market/entry_filters.py` → `fibonacci_entries`, `DEFAULT_PARAMS["Fibonacci"]` |
| Direction gate | `swingbot/core/market/strategy_types.py` → `STRATEGY_GATES["Fibonacci"]` |
| Lookback per horizon | `strategy_types.py` → `HORIZONS[*]["fib_lookback"]`, `FIB_TOLERANCE_PCT` |
| Scanner signal and embed details | `swingbot/core/market/signals.py` → `fibonacci_signal` |
| Stop and target sizing | `swingbot/core/planning/builders.py` → `_fib_branch`, `_fibonacci_plan` |
| Target candidates | `swingbot/core/planning/targets.py` → `fib_target_candidates`, `select_structural_target` |
| Exit parameters | `swingbot/core/planning/params.py` → `EXIT_V2_PARAMS["Fibonacci"]` |
| Backtest wiring | `swingbot/core/backtesting/backtest.py` → `_plan_series`, `_trade_plan_at` |
| Level-map role (confluence pipeline) | `swingbot/core/market/levels.py` (one "Fibonacci" vote) |

---

## 1. The idea

After a strong move (an **impulse**), price often pulls back part of the way
before continuing. Traders measure that pullback as a fraction of the impulse.
The classic fractions are 23.6%, 38.2%, 50%, 61.8% and 78.6%. The idea is that
these levels act as support in an uptrend, or resistance in a downtrend. The bot
trades the **bounce off a mid-depth retracement level in the direction of the
original impulse**.

```
 price
  120 ┤            ● swing high (impulse end)
      │           ╱ ╲
  115 ┤          ╱   ╲ ........ 23.6%  (too shallow, not an entry level)
  112 ┤         ╱     ╲ ....... 38.2%  ┐
  110 ┤        ╱       ╲ ...... 50.0%  ├ entry levels: price must be testing one
  108 ┤       ╱         ●╮ .... 61.8%  ┘  and bouncing off it
  104 ┤      ╱            ↑ ... 78.6%  (too deep, "failed impulse")
  100 ┤ ● swing low (impulse start)
      └──────────────────────────────── time
        low set FIRST, high set AFTER → up-impulse → bullish setup only
```

---

## 2. Drawing the levels

For each bar and each horizon, over the trailing `fib_lookback` bars
(inclusive of the current bar):

```
swing_high = max(High over lookback)
swing_low  = min(Low  over lookback)
range      = swing_high − swing_low
level(r)   = swing_high − r × range          # measured DOWN from the high
```

The same formula serves both directions. In a down-impulse the "retracement"
is a bounce *up* from the low. Price reaches the 0.618 level, for example, after
recovering 38.2% of the fall, and the level acts as resistance.

**Lookback per horizon** (`HORIZONS[*]["fib_lookback"]`, trading days):

| Horizon | 2w | 4w | 2m | 3m | 4m | 5m | 6m | 7m | 8m | 9m |
|---|---|---|---|---|---|---|---|---|---|---|
| `fib_lookback` | 15 | 42 | 84 | 126 | 168 | 210 | 252 | 294 | 336 | 378 |

Two ratio sets are in use, and the difference matters:

- **Entry levels** (`DEFAULT_PARAMS["Fibonacci"]["ratios"]`): **0.382, 0.5,
  0.618** only. 23.6% is treated as too shallow and 78.6% as a failed impulse.
- **Display and target levels** (`indicators.fibonacci_levels`): all five,
  0.236 / 0.382 / 0.5 / 0.618 / 0.786. The embed's "Nearest level" and the
  target candidates use this set. The embed can therefore name 23.6% or 78.6%
  as the nearest level even though an entry never fires on those.

---

## 3. The entry rule (`fibonacci_entries`)

A bar fires **bullish** only when *every* condition below is true on that bar.
The bearish rule is the mirror image. All conditions read the current bar and
earlier bars only (no lookahead).

| # | Condition | Bullish | Bearish |
|---|---|---|---|
| 1 | **Testing a level** | the closest of the 0.382/0.5/0.618 levels is within `FIB_TOLERANCE_PCT` = **2% of the range** of the close, and range > 0 | same |
| 2 | **Impulse direction** | swing low set *before* swing high in the window (`argmax_pos > argmin_pos`) = up-impulse | swing high before low = down-impulse |
| 3 | **Pulled back** | `close[t−5] > close[t−1]`: price was falling into the level | `close[t−5] < close[t−1]` |
| 4 | **Bouncing** | `close[t] > close[t−1]` | `close[t] < close[t−1]` |
| 5 | **Strong bar** | close in the upper half of the bar's range, `close ≥ (H+L)/2` | lower half |
| 6 | **Long-term regime** | `close > MA200` and MA200 rising over 20 bars | MA200 falling over 120 bars and `close < MA200` |
| 7 | **Medium trend** | `close > MA50` | `close < MA50` |
| 8 | **RSI(14) band** | 35 ≤ RSI ≤ 58 (a pullback, not overbought) | 42 ≤ RSI ≤ 65 |
| 9 | **Tape filters** (shared by all strategies) | ATR14/close ≥ 0.7% (not dead), ATR14 ≤ 1.4 × its 60-bar mean (not panicking), volume ≥ 0.9 × 20-bar average | same |

Condition 2 is the important fix, recorded in the docstring. The old version used
only rolling max/min and fired "bullish" on retracements of *downtrends*, where
the Fibonacci level is overhead resistance, not support.

After those nine conditions:

1. **Optional S/R confluence filter** (`FIB_SR_CONFLUENCE_ATR`, default `0.0`,
   off). When on, it keeps a signal only if the tested level sits within
   `tol × ATR14` of the bar's Rolling support/resistance. This was v102, and it
   closed NO-LIFT (see §7).
2. **Optional level-stop filter** (`FIB_LEVEL_STOP_ATR` + `FIB_LEVEL_STOP_DIRECTIONS`,
   default off). This drops signals whose level stop would breach the 2% cap.
   This was v103 mechanism A, and it closed NO-LIFT.
3. **`entries_for` gates.** `STRATEGY_GATES["Fibonacci"] = {"directions": ("bullish",)}`
   turns **every bearish signal off**, because bearish Fibonacci never passed its
   measurement (v93). The market-regime gate then applies as for every strategy.

The output is two boolean series (bullish, bearish) per ticker × horizon. The
**same function** feeds the backtest, the badge registry and the live
strategy-alert path, so backtest and live cannot drift on the entry rule.

---

## 4. Sizing the plan (`_fib_branch` → `_fibonacci_plan`)

Entry = the signal bar's close.

### Stop

The default path is the **swing stop**:

```
stop = swing_low − 0.25 × ATR14        (bullish;  STRUCTURE_BUFFER_ATR = 0.25)
stop = swing_high + 0.25 × ATR14       (bearish)
```

The stop is then **risk-capped**: if `|entry − stop|` exceeds
`capped_planned_loss_pct(h["max_risk_pct"])` of entry, the stop is pulled in to
exactly that distance. `capped_planned_loss_pct` is
`min(horizon max_risk_pct, 2.0)` (`risk_limits.HARD_MAX_PLANNED_LOSS_PCT`), and
every horizon's `max_risk_pct` is ≥ 3%. **So the effective cap is always 2%.**

> **In practice the stop is almost always `entry × 0.98` (bullish).** A swing
> low sits at least one full retracement away (≥ 38.2% of the range). With
> ranges of 10%+ that is far beyond 2%. v101 measured it: after the 2% cap
> landed (`a3a903d6`, 2026-09-21), **the cap binds on 100% of Fibonacci plans**.
> The structure-derived stop is effectively a fixed 2% stop, and it no longer
> sits behind any Fibonacci structure.

**Then the level-lifecycle step can widen it.** `apply_level_lifecycle`
(default on) runs after the builder. It moves the stop behind a *tested*
level, bounded by the horizon's `max_risk_pct` (7% on 4w), **not** by 2%. In
a 2026-09-25 spot check, 12 Fibonacci backtest trades on 5 tickers carried
initial stops of 2.5–7.6%. The live path cancels such a plan at fill;
the backtest does not. See
[shared-mechanics §4a](shared-mechanics.md#4a-level-lifecycle-stop-and-a-2-cap-finding).

When v103's level stop is enabled (it isn't), the stop is instead
`tested_level ∓ b × ATR14`. That stop is used verbatim, or the plan is not
built, and it is never capped.

### Target (TP1)

Candidates (`fib_target_candidates`, computed on history sliced to the signal
bar):

- the swing high and swing low,
- the five retracement levels (0.236 … 0.786),
- the 1.272 and 1.618 extensions on both sides (`swing_high + r·range`,
  `swing_low − r·range`), plus 1.0 when `FIB_TARGET_1_0_EXTENSION` is on (off;
  v84 closed FAIL).

`select_structural_target` picks the **nearest** candidate beyond entry that pays
at least `MIN_RISK_REWARD_RATIO` (1.5R). If the nearest qualifying level is
beyond `MAX_RISK_REWARD_RATIO` (2.5R), TP1 is placed synthetically at exactly
2.5R. **If no candidate clears 1.5R, no plan is built.** No fallback target
exists, by design (plan v31).

### Worked example (4w horizon, bullish)

```
swing_low 100 (earlier), swing_high 120 (later)   → up-impulse, range 20
levels: 0.382 → 112.36   0.5 → 110.00   0.618 → 107.64
close 110.30 → nearest 110.00, distance 0.30/20 = 1.5% of range ≤ 2%  → testing
(assume conditions 3–9 hold) → bullish signal

stop:  100 − 0.25 × ATR(2.0) = 99.50  → 9.8% risk > 2% cap
       → capped: 110.30 × 0.98 = 108.094        risk = 2.206
TP1:   floor 1.5R = 113.61, cap 2.5R = 115.82
       candidates above entry: 112.36 (0.382, only 0.93R: too close),
                               115.28 (0.236, 2.26R): qualifies ✓
       → TP1 = 115.28
```

---

## 5. Managing the trade (exit model v2)

Fibonacci's override row is `EXIT_V2_PARAMS["Fibonacci"] = {"trail_atr_mult": 3.0, "tp2": False}`.

- **TP1 scale-out:** half the position (`TP1_FRACTION = 0.5`) exits at TP1.
- **Runner floor:** once TP1 fills, the runner's stop jumps to lock in ⅔ of the
  entry→TP1 move (`RUNNER_FLOOR_FRACTION`).
- **Trail:** the runner trails a **3.0 × ATR chandelier** stop.
- **No TP2** for Fibonacci (`tp2: False`), so the runner exits on the trail.
- Scratch, timeout and frictions follow the shared v2 exit simulator, identical
  in backtest and live.

The `# N=279 WR=81.7 ExpR=+0.183` comment on that row is from the 2026-07
exit-v2 TRAIN grid, under pre-v31 target arithmetic and before the 2% cap.
**It does not describe today's strategy.** Use §7's figures instead.

---

## 6. Where Fibonacci shows up in the bot

1. **Strategy-sourced alerts (v93 path).** `fibonacci_entries` runs on the last
   completed daily bar. Whether that posts anything is governed by
   `STRATEGY_ALERTS_MODE` (`off` / `shadow` / `live`, default `off`) and
   `STRATEGY_ALERTS_LIVE_STRATEGIES`. A strategy goes live only after `!soak`
   passes.
2. **Scanner signal** (`fibonacci_signal`). It reports trend, triggered and the
   embed details (swing high/low, nearest level, distance as % of range). When
   nothing triggers, the trend label is simply "above or below the 50% level".
3. **Level map for the confluence pipeline** (`levels.py`). All five
   retracements plus the swing high/low become candidate levels. However many
   Fibonacci levels cluster together, they count as **one "Fibonacci" vote**
   toward `MIN_TARGET_CONFLUENCE_COUNT`.
4. **Backtest** (`backtest.py`). It uses the identical entry function and sizing
   builder, via `_plan_series` → `_trade_plan_at`.

---

## 7. How well does it work? (measured, not assumed)

Every figure carries its source, window and N. None was re-derived for this page
beyond reading the named file.

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Badge registry `validation_registry.json` (run 2026-09-10) | 2020-01-01..2023-12-31 | 246 | 35.4% | +0.232 | status **WEAK**. Run date predates the 2% cap (2026-09-21) |
| v101 baseline, bullish (post-2% cap) | TRAIN 2020-01-01..2023-12-31 | 288 | 28.8% | +0.039 | `results/2026-09-24-v101-fib-diagnostic.md`; bearish N=94 WR 25.5% ExpR −0.091 |
| v102/v103 TRAIN_EXT reference, bullish (swing stop, current arithmetic) | 2010-01-01..2023-12-31, universe 73 | 815 | 36.8% | +0.222 | `results/2026-09-24-v102-stage0.md`, `results/2026-09-25-v103-stage12.md` |
| same, bearish (unmasked, laggard rule) | same | 169 | 23.7% | −0.127 | why the bearish side is gated off |
| v104 structural stop, bullish, out-of-scope arm | TRAIN 2010-2025, universe 74 | 1119 | 36.9% | +0.259 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, bullish, in-scope arm | same | 120 | 31.7% | +0.332 | Tier 2 (lower bound +0.162), beats baseline, but only 1 of 3 anchored folds qualifies (needs ≥3) — **NO-LIFT at Stage 2**, holdout shot not spent |

The strategy has **positive but weak expectancy on the bullish side and negative
expectancy on the bearish side**. Win rate is far below 50%, so the edge relies
on winners (≥ 1.5R targets plus the trailing runner) outweighing frequent 1R
losses.

### Research history (all closed; see `docs/claude/backtest-methodology.md` before reopening)

| Plan | Idea | Outcome |
|---|---|---|
| v31 | per-horizon splits | closed, do not re-run |
| v84 | add the 1.0 extension as a target | FAIL, changed one trade in N≈245 |
| v93 | admit bearish | failed its rule, so bearish stays masked |
| v101 | structural-stop filter / deeper-ratio stop / reclaim entry | NO-LIFT, TRAIN diagnostic only. Found the 2% cap binds 100% of plans |
| v102 | keep only levels in confluence with Rolling S/R | NO-LIFT, a de-facto 2w/4w mask |
| v103 A | stop `b` ATR past the tested level (b ∈ 0.1/0.25/0.5), drop-don't-cap | bullish **FAILED VALIDATION** (2024-25: N=190, WR 23.2%, ExpR +0.313, lower bound −0.203). Shot spent |
| v103 C | "Fibonacci Continuation": enter on the break of the swing extreme after a held 0.382–d_max retracement | NO-LIFT (bullish Stage 2: 6/11 folds; bearish Stage 1). Ships masked |
| v104 | structural stop (drop, don't cap) instead of the flat 2% cap | bullish NO-LIFT at Stage 2 (1 of 3 folds qualifies); holdout shot not spent, remains available |

**Main open problem:** because of the 2% cap, the plan's stop no longer reflects
Fibonacci structure. It is a flat 2% stop, often *inside* the retracement zone
the setup relies on. Any reopening needs a mechanism different from those
already closed above.

---

## 8. Algorithm in one block (pseudocode)

```python
for each bar t, horizon h:
    L = HORIZONS[h].fib_lookback
    hi, lo = max(High[t-L+1..t]), min(Low[t-L+1..t]);  rng = hi - lo
    up_impulse = index_of(hi) > index_of(lo)
    levels = {r: hi - r*rng for r in (0.382, 0.5, 0.618)}
    testing = rng > 0 and min(|lvl - Close[t]|) / rng <= 2%

    bull = (testing and up_impulse
            and Close[t-5] > Close[t-1] and Close[t] > Close[t-1]
            and Close[t] >= (High[t]+Low[t])/2
            and Close > MA200 and MA200 rising(20) and Close > MA50
            and 35 <= RSI14 <= 58
            and ATR14/Close >= 0.7% and ATR14 <= 1.4*mean60(ATR14)
            and Volume >= 0.9*mean20(Volume))
    bear = mirror(bull)          # then gated OFF by STRATEGY_GATES

    if bull:
        entry = Close[t]
        stop  = lo - 0.25*ATR14
        stop  = max(stop, entry*(1 - 0.02))       # 2% cap (binds ~always)
        stop, tp1 = level_lifecycle(stop, ...)    # may widen past 2% (see shared-mechanics §4a)
        risk  = entry - stop
        cands = [hi, lo, fib 0.236..0.786, ext 1.272/1.618 both sides]
        above = sorted(c for c in cands if c - entry >= 1.5*risk)
        if not above: skip
        tp1 = min(above[0], entry + 2.5*risk)
        manage: 50% off at tp1 → runner stop to entry + ⅔(tp1-entry)
                → 3.0×ATR chandelier trail, no TP2
```
