# EMA Crossover (pullback mode)

`ENTRY_FUNCS["EMA Crossover"]` = `ema_cross_entries` (`entry_filters.py`) ·
signal `ema_cross_signal` · sizing **ATR family** · gate **none** (both
directions, all horizons). Shared rules: [shared-mechanics.md](shared-mechanics.md).

## Idea

A fast EMA crossing above a slow EMA marks a new up-trend. Buying the cross
itself chases, so the bot waits for the **first pullback to the fast EMA after
the cross** and enters when that pullback holds.

## Entry rule (bullish; bearish mirrors)

Periods per horizon: `ema_fast`/`ema_slow` (2w 8/13 … 9m 80/350, see
[shared-mechanics §7](shared-mechanics.md#7-horizon-parameters)).

1. **Held cross:** `diff = EMAfast − EMAslow` was ≤ 0 two bars ago and > 0 on
   both the previous bar and this one. This filters one-bar fake-outs.
2. **Pullback entry** (`entry_mode = "pullback"`, `pullback_max_bars = 15`):
   within 15 bars after that cross, the **first** bar whose `Low ≤ EMAfast` and
   `Close > EMAfast` becomes the candidate. It touched the EMA and closed back
   above it.
3. On that candidate bar, all of these must hold:
   - slow EMA rising over 5 bars (a cross inside a falling slow EMA is a trap);
   - `|close − EMAfast| ≤ 1.0 × ATR14` (`ext_atr`): not extended;
   - `RSI14 > 50`, and the lowest RSI of the previous 5 bars was `< 45`
     (`rsi_dip`), so a real dip came first;
   - momentum: `MACD(12,26) > 0` or `RSI > 60`;
   - shared: `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`, `vol_ok`.

Bearish uses a held cross down, `High ≥ EMAfast` and `Close < EMAfast`, a
falling slow EMA, `RSI < 50`, a previous 5-bar RSI max `> 55`, momentum
`MACD < 0` or `RSI < 40`, and `bear_regime`/`trend50_bear`.

## Plan and exits

Stop `2 × ATR14`, capped at 2%. TP1 is the nearest ATR-ladder rung ≥ 1.5R,
capped at 2.5R. Exits use the defaults: trail 2.5 × ATR, TP2 on.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Registry (run 2026-07-18) | VALIDATION 2024–25 | 36 | 75.0% | +0.061 | **WEAK**, pre-v31 arithmetic: stale |
| v84 re-measurement | TRAIN | 55 | 61.8% | +0.494 | clears every badge clause, but only 1 of 3 fold years has N ≥ 15, so **CLOSED** before VALIDATION |
| v104 structural stop, bullish, out-of-scope arm | TRAIN 2010-2025, universe 74 | 137 | 39.4% | +0.150 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, bullish, in-scope arm | same | 70 | 51.4% | +0.284 | Tier 1, beats baseline, but 0 of 13 folds qualify — **NO-LIFT at Stage 2** |
| v104 structural stop, bearish, out-of-scope arm | TRAIN 2010-2025, universe 74 | 23 | 26.1% | −0.180 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, bearish, in-scope arm | same | 3 | 33.3% | −0.107 | N=3, below the N ≥ 30 floor — **NO-LIFT at Stage 1** |

## History

- Tasks 107–109 (2026-07): the rescue switched the entry from "cross" to
  "pullback". On TRAIN, pullback scored N=68 WR 91.2% against the cross
  baseline's N=110 WR 68.2%, both under pre-v31 arithmetic. Task 109 spent the
  VALIDATION shot, and the strategy stays WEAK.
- v84: closed at fold stability. The problem is thin volume, not a blow-up.
  Reopening needs a new mechanism.

## Pseudocode

```python
cross_t = bars where diff[t-2] <= 0 < diff[t-1] and diff[t] > 0
for each cross_t:
    t = first bar in (cross_t, cross_t+15] with Low <= EMAf and Close > EMAf
    fire if EMAs rising(5) and |Close-EMAf| <= ATR and RSI > 50
            and min(RSI[t-5..t-1]) < 45 and (MACD > 0 or RSI > 60)
            and bull_regime and Close > MA50 and tape_ok
```
