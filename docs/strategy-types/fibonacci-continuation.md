# Fibonacci Continuation (measured move) — masked, experimental

`ENTRY_FUNCS["Fibonacci Continuation"]` = `fib_continuation_entries` · no
scanner signal function · sizing **structural** (`_fib_continuation_plan`) ·
gate **`{"directions": ()}` = never fires**. It is **not** in
`backtest.ALL_STRATEGIES`. Added by v103 (mechanism C), which closed NO-LIFT.
Shared rules: [shared-mechanics.md](shared-mechanics.md).
Its sibling is [fibonacci.md](fibonacci.md).

## Idea

The Fibonacci retracement strategy buys *at* the level. This one instead
waits for the retracement to **hold** at a normal depth, and buys only when
price **breaks back through the swing high**. That confirms the trend resumed,
and the stop sits just under the broken high, which fits inside the 2% cap.

## Entry rule (bullish; bearish mirrors)

All structure uses **prior bars** (High/Low shifted 1) over `fib_lookback`.
Only today's close is compared against it.

1. **Up-impulse:** in the window, the swing low comes before the swing high.
2. **A real pullback:** at least 2 bars since the swing high
   (`min_pullback_bars`).
3. **Held retracement:** `retrace` is the lowest low after the high.
   `depth = (high − retrace) / (high − low)` must be between
   **0.382 (`d_min`) and `d_max` (0.618)**.
4. **Break:** `close > swing high`.
5. **Fits the cap:** `stop = swing high − 0.25 × ATR14`. If the stop is more
   than 2% from the close, the signal is dropped, never capped.
6. Shared: `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`, `vol_ok`.
   There is no RSI condition.

## Plan

- **Stop:** the structure stop above, used verbatim, or no plan.
- **TP1 candidates** (`fib_continuation_targets`):
  - `retrace + impulse` (the measured move);
  - `high + 0.272 × impulse`;
  - `high + 0.618 × impulse`.

  These are the 1.272 and 1.618 extensions measured from the broken level.
  The usual 1.5R–2.5R selection applies.
- **Exits:** trail 2.5 × ATR, TP2 on.

## Measured (v103, extended cache, universe 73)

| Direction | Stage | Result |
|---|---|---|
| bullish | TRAIN 2010–23, d_max 0.5 / 0.618 / 0.786 | N=774 / 1199 / 1613, WR 34.4–36.4%, ExpR +0.241 / +0.243 / +0.216. All three cells cleared Tier 2 |
| bullish | Stage 2 (11 anchored folds) | 6 of 11 folds positive, 8 needed, so **NO-LIFT at Stage 2** |
| bearish | TRAIN 2010–23 | N=63 / 92 / 130, ExpR +0.087 / −0.058 / −0.018, every bootstrap lower bound negative, so **NO-LIFT at Stage 1** |

The VALIDATION budget is **unspent**. Reopening needs a trigger other than
"break of the swing extreme after a 0.382–d_max hold". Source:
`docs/superpowers/results/2026-09-25-v103-stage12.md`.

## Pseudocode

```python
hi, lo = swing extremes of prior L bars (High/Low shifted 1)
require index(lo) < index(hi) and bars_since(hi) >= 2
retrace = min(Low after hi); depth = (hi - retrace) / (hi - lo)
stop = hi - 0.25*ATR
fire if 0.382 <= depth <= 0.618 and Close > hi and (Close-stop)/Close <= 2%
        and bull_regime and Close > MA50 and tape_ok        # then masked by STRATEGY_GATES
tp1 from {retrace + (hi-lo), hi + 0.272*(hi-lo), hi + 0.618*(hi-lo)}
```
