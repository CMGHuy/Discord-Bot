# VWAP reclaim

`ENTRY_FUNCS["VWAP"]` = `vwap_entries` · signal `vwap_signal` · sizing **ATR
family** · gate **bullish, 4w only**. Shared rules:
[shared-mechanics.md](shared-mechanics.md).

## Idea

VWAP is the volume-weighted "fair value" of recent trading. The bot buys when
price **reclaims a rising VWAP and holds above it**, while it is still close
to value rather than stretched.

## How VWAP is computed

Daily bars carry no intraday ticks, so VWAP is a **rolling** one
(`indicators.rolling_vwap`):
`sum(typical × volume) / sum(volume)` over `vwap_window` bars, where
`typical = (H + L + C) / 3`. The window runs from 10 bars (2w) to 189 (9m).
The live gate uses only 4w, which is 21 bars.

## Entry rule (bullish; bearish mirrors)

`diff = close − VWAP`, `hold = 3` on 2w and `2` on every other horizon.

1. **Reclaim and hold:** `diff[t − hold] ≤ 0` and `diff > 0` on each of the
   last `hold` bars (t, t−1, … t−hold+1).
2. **VWAP rising:** `VWAP > VWAP[t−3]`.
3. **Near value:** `|close − VWAP| / VWAP ≤ 1.5%` (`ext_pct`), so it doesn't
   chase.
4. `50 ≤ RSI14 ≤ 65`.
5. Shared: `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`, `vol_ok`.

Bearish: a loss of VWAP held for `hold` bars, VWAP falling,
`35 ≤ RSI ≤ 50`, and the bear gates.

Optional `min_vwap_slope_atr` requires the 8-bar VWAP rise to be at least
that many ATRs. It defaults to `None` (off). It came from the v84 fallback and
failed fold stability.

## Plan and exits

Stop `2 × ATR14`, capped at 2%. TP1 comes from the ATR ladder. Exits: trail
2.5 × ATR, **no TP2**.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Registry (run 2026-08-17) | VALIDATION 2024–25 | 75 | 49.3% | +0.302 | **WEAK**: v31's VALIDATION flipped it from VALIDATED |
| v84, 4w-only | TRAIN | 68 | 52.9% | +0.335 | gate shipped; badge closed at fold stability (only 2023 of 3 folds holds) |
| v104 structural stop, out-of-scope arm | TRAIN 2010-2025, universe 74 | 382 | 45.0% | +0.411 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, in-scope arm | same | 316 | 49.1% | +0.234 | Tier 2, clears the fold check (9 qualifying, 6 positive), but in-scope ExpR is below the out-of-scope arm's — **NO-LIFT at Stage 1** |

Positive expectancy, but a win rate just under 50%, and the fold years don't
hold N.

## History

- Pre-v31: a hand-calibrated five-horizon mask.
- v84 R11: re-derived under current arithmetic and narrowed to 4w. Dropped
  horizons: 6m ExpR −0.078, 9m −0.519 (N=9).
- v84 slope fallback: clears TRAIN but fails folds, so it ships inert.

**v113 1w cells (Part B, TRAIN 2010-01-01..2025-12-31, universe 74, horizon 1w masked):** bullish N=528, WR 36.9%, ExpR +0.235, lower bound +0.149, cleared Tier 2 at Stage 1; Part B bar failing clauses: wr; folds 12 qualifying / 11 positive. bearish N=60, WR 28.3%, ExpR -0.033, lower bound -0.317, no tier; Part B bar failing clauses: wr, exp_r, lower_bound; folds 0 qualifying / 0 positive. Neither cell proceeds to the holdout (Part B's bar is Tier 1 plus a bootstrap lower bound > 0; every 1w cell fails Tier 1 on WR); no `cells` admission, no registry row. Source: `results/2026-09-30-v113-partB.md`.

## Pseudocode

```python
vwap = rolling_vwap(window)
fire if all(Close[t-k] > vwap[t-k] for k in 0..hold-1) and Close[t-hold] <= vwap[t-hold]
        and vwap > vwap[t-3] and |Close/vwap - 1| <= 1.5% and 50 <= RSI <= 65
        and bull_regime and Close > MA50 and tape_ok
```
