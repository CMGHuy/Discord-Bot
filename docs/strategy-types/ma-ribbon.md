# MA Ribbon alignment

`ENTRY_FUNCS["MA Ribbon"]` = `ma_ribbon_entries` · signal `ma_ribbon_signal` ·
sizing **ATR family** · gate **bullish, all horizons**. Shared rules:
[shared-mechanics.md](shared-mechanics.md).

## Idea

Three moving averages stacked in order (fast > mid > slow), with the slow one
rising, describe a clean up-trend. The bot enters the moment the fast EMA
crosses above the mid EMA while both already sit above a rising slow SMA.

## Periods per horizon (`RIBBON_PERIODS_BY_HORIZON`: fast EMA, mid EMA, slow SMA)

| 2w | 4w | 2m | 3m | 4m | 5m | 6m | 7m | 8m | 9m |
|---|---|---|---|---|---|---|---|---|---|
| 10/20/50 | 10/20/50 | 20/50/100 | 20/50/200 | 30/67/200 | 40/83/200 | 50/100/200 | 60/117/200 | 70/133/200 | 80/150/200 |

## Entry rule (bullish; bearish mirrors)

1. **Cross into alignment:** `fast − mid` goes from ≤ 0 to > 0 on this bar,
   with `fast > slowSMA` and `mid > slowSMA`.
2. **Slow SMA rising:** `slowSMA > slowSMA[t−10]`. Alignment without slope is
   a chop trap.
3. **Not extended:** `close ≤ slowSMA × 1.08` (`ext_pct` 8%) and
   `48 ≤ RSI14 ≤ 70`.
4. `MACD(12,26) > 0`.
5. Shared: `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`, `vol_ok`.

Bearish: the mirror cross below a falling slow SMA, `close ≥ slow × 0.92`,
`30 ≤ RSI ≤ 52`, `MACD < 0`, and the bear gates.

Optional gates, all off by default and all closed:
- `MA_RIBBON_CONFIRM_BARS` (default 1): the alignment must hold for N bars.
- `min_width_pctile` / `require_expanding` (Task 101): width filters.

## Plan and exits

Stop `2 × ATR14`, capped at 2%. TP1 comes from the ATR ladder. Exits: trail
2.5 × ATR, no TP2.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Registry (run 2026-07-18) | VALIDATION 2024–25 | 137 | 78.1% | +0.213 | **WEAK**, pre-v31 arithmetic: stale |
| v84 baseline (K=1) | TRAIN | 233 | 48.1% | +0.270 | current arithmetic |
| v84 `confirm_bars` K=2 / K=3 | TRAIN | 210 / 194 | 48.1% / 49.0% | +0.269 / +0.289 | both miss WR ≥ 50 by 1–2pp, so the axis is **closed** |
| v104 structural stop, out-of-scope arm | TRAIN 2010-2025, universe 74 | 1139 | 44.4% | +0.337 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, in-scope arm | same | 670 | 48.8% | +0.258 | Tier 2, clears the fold check (13 qualifying, 12 positive), but in-scope ExpR is *below* the out-of-scope arm's — **NO-LIFT at Stage 1** |

## Pseudocode

```python
f, m, s = EMA(fp), EMA(mp), SMA(sp)
fire if (f-m)[t-1] <= 0 < (f-m)[t] and f > s and m > s and s > s[t-10]
        and Close <= 1.08*s and 48 <= RSI <= 70 and MACD > 0
        and bull_regime and Close > MA50 and tape_ok
```
