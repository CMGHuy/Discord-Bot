# RSI hidden divergence

`ENTRY_FUNCS["RSI Divergence"]` = `rsi_divergence_entries` · signal
`rsi_divergence_signal` · sizing **ATR family** · gate **none** (both
directions, all horizons). Shared rules: [shared-mechanics.md](shared-mechanics.md).

## Idea

In an up-trend, **hidden bullish divergence** means price makes a higher low
while RSI makes a lower low. The pullback was deep in momentum terms but
shallow in price terms, which is a continuation sign. Divergence only marks
potential. The entry fires when RSI actually turns back up.

## Entry rule (bullish; bearish mirrors)

This is a **rolling** formulation with no discrete swing points, and a fixed
`lb = 20`. **The entry rule does not depend on the horizon.** The same bars
fire on all 10 horizons.

1. **Price higher low:** `close > min(close over the 20 bars ending 20 bars ago)`.
2. **RSI lower low:** `RSI14 < min(RSI14 over the 20 bars ending 20 bars ago)`.
3. **RSI reclaim and turn:** `RSI14 > 45` (`rsi_reclaim`) and RSI rising.
   "Rising" means one bar up; `RSI_DIV_MIN_CONSECUTIVE_TURN` defaults to 1.
4. `28 ≤ RSI14 ≤ 52`.
5. Shared: `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`, `vol_ok`.

Rules 2–4 together put today's RSI in a narrow band: above 45, at most 52,
and below the previous window's RSI minimum.

Bearish: `close <` the prior window's max close, RSI `>` the prior window's
max RSI, `RSI < 55` and falling, `48 ≤ RSI ≤ 72`, and the bear gates.

Task 98 rescue gates `min_volume_ratio` / `min_reclaim_strength` are `None`
(off).

## Plan and exits

Stop `2 × ATR14`, capped at 2%. TP1 comes from the ATR ladder. Exits: trail
**2.0** × ATR, no TP2.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Registry (run 2026-07-18) | VALIDATION 2024–25 | 1099 | 75.8% | +0.208 | **WEAK**, pre-v31 arithmetic: stale |
| v84 persistence K=2 / 3 / 4 | TRAIN | 473 / 70 / 10 | 49.0 / 28.6 / 10.0% | K=3: −0.262 | persistence made it worse, so it was **rejected on TRAIN** and is permanently WEAK |
| v104 structural stop, bullish, out-of-scope arm | TRAIN 2010-2025, universe 74 | 5282 | 43.6% | +0.395 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, bullish, in-scope arm | same | 3855 | 50.9% | +0.288 | Tier 1, clears the fold check (13 qualifying, 10 positive), but in-scope ExpR is below the out-of-scope arm's — **NO-LIFT at Stage 1** |
| v104 structural stop, bearish, out-of-scope arm | TRAIN 2010-2025, universe 74 | 768 | 34.9% | +0.281 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, bearish, in-scope arm | same | 391 | 34.8% | −0.070 | bootstrap lower bound −0.362, no tier — **NO-LIFT at Stage 1** |

This is by far the highest-volume strategy. N=1099 counts every horizon, and
because the entry ignores the horizon, those are heavily the same bars counted
repeatedly.

**v113 1w cells (Part B, TRAIN 2010-01-01..2025-12-31, universe 74, horizon 1w masked):** bullish N=484, WR 40.1%, ExpR +0.337, lower bound +0.231, cleared Tier 2 at Stage 1; Part B bar failing clauses: wr; folds 12 qualifying / 11 positive. bearish N=75, WR 33.3%, ExpR +0.227, lower bound -0.093, no tier; Part B bar failing clauses: wr, lower_bound; folds 0 qualifying / 0 positive. Neither cell proceeds to the holdout (Part B's bar is Tier 1 plus a bootstrap lower bound > 0; every 1w cell fails Tier 1 on WR); no `cells` admission, no registry row. Source: `results/2026-09-30-v113-partB.md`.

## Pseudocode

```python
prior_min_c = rolling_min(Close, 20).shift(20)
prior_min_rsi = rolling_min(RSI, 20).shift(20)
fire if Close > prior_min_c and RSI < prior_min_rsi and 45 < RSI <= 52
        and RSI > RSI[t-1] and bull_regime and Close > MA50 and tape_ok
```
