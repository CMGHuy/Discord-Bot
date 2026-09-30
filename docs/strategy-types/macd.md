# MACD momentum

`ENTRY_FUNCS["MACD"]` = `macd_entries` · signal `macd_signal` · sizing **ATR
family** · gate **bullish, horizons 3m / 4m / 7m / 8m / 9m**. Shared rules:
[shared-mechanics.md](shared-mechanics.md).

**One of the two VALIDATED strategies.** Volume Profile is the other.

## Idea

MACD is the difference between a fast EMA and a slow EMA, and its signal line
is an EMA of MACD. When MACD turns up through its signal line **while already
above zero**, with the histogram accelerating, momentum is re-asserting inside
an existing up-trend.

## Periods per horizon (`MACD_PERIODS_BY_HORIZON`)

| 2w | 4w | 2m | 3m | 4m | 5m | 6m | 7m | 8m | 9m |
|---|---|---|---|---|---|---|---|---|---|
| 8/17/9 | 12/26/9 | 12/26/9 | 19/39/9 | 21/43/9 | 24/48/9 | 26/52/9 | 28/56/9 | 31/61/9 | 33/65/9 |

## Entry rule (bullish; bearish mirrors)

`hist = MACD − signal`.

1. **Trigger:** either MACD crossed above the signal line on this bar, **or**
   the histogram turned positive and held (`hist[t−2] ≤ 0`, `hist[t−1] > 0`,
   `hist[t] > 0`).
2. **Accelerating:** `hist[t] > hist[t−1] > hist[t−2]`.
3. **Above zero:** `MACD > 0`.
4. `RSI14 > 50`.
5. **Not extended:** `|close − EMA(fast period)| ≤ 1.0 × ATR14`.
6. Shared: `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`, `vol_ok`.

Bearish: a cross down (or the histogram turning negative), the histogram
falling for 2 bars, `MACD < 0`, `RSI < 50`, and the bear gates.

## Plan and exits

Stop `2 × ATR14`, capped at 2%. TP1 comes from the ATR ladder. Exits: trail
**2.0** × ATR, **TP2 on**, the only ATR-family strategy with TP2.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Registry (run 2026-08-17) | VALIDATION 2024–25 | 112 | 50.0% | +0.219 | **VALIDATED** (v31 shot, current targets, pre-2% cap) |
| v104 structural stop, out-of-scope arm | TRAIN 2010-2025, universe 74 | 732 | 39.9% | +0.202 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, in-scope arm | same | 633 | 51.2% | +0.240 | Tier 1, beats baseline, clears the fold check (13/13) — **PROCEEDED to the 2026 holdout** |
| v104 structural stop, in-scope arm | HOLDOUT 2026-01-01..2026-09-25 | 27 | 44.4% | +0.053 | win-rate clause **FAILS** (44.4% < 50% floor); ExpR positive and beats baseline. Shot spent, final. `results/2026-09-28-v104-holdout.md` |

The win rate sits exactly on the 50% floor. The bearish arm was re-derived in
v93 and failed, so it stays masked.

**v113 1w cells (Part B, TRAIN 2010-01-01..2025-12-31, universe 74, horizon 1w masked):** bullish N=435, WR 36.1%, ExpR +0.172, lower bound +0.072, cleared Tier 2 at Stage 1; Part B bar failing clauses: wr; folds 12 qualifying / 9 positive. bearish N=72, WR 22.2%, ExpR -0.148, lower bound -0.357, no tier; Part B bar failing clauses: wr, exp_r, lower_bound; folds 0 qualifying / 0 positive. Neither cell proceeds to the holdout (Part B's bar is Tier 1 plus a bootstrap lower bound > 0; every 1w cell fails Tier 1 on WR); no `cells` admission, no registry row. Source: `results/2026-09-30-v113-partB.md`.

## Pseudocode

```python
m, s = macd(close, *PERIODS[h]); hist = m - s
trigger = crossed_up(m, s) or (hist[t-2] <= 0 < hist[t-1] and hist[t] > 0)
fire if trigger and hist[t] > hist[t-1] > hist[t-2] and m > 0 and RSI > 50
        and |Close - EMA(fast)| <= ATR and bull_regime and Close > MA50 and tape_ok
```
