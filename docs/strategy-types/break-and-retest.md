# Break & Retest

`ENTRY_FUNCS["Break & Retest"]` = `break_retest_entries` · signal
`break_retest_signal` · sizing **ATR family** · gate **both directions,
horizons 2m / 3m / 4m**. Shared rules: [shared-mechanics.md](shared-mechanics.md).

## Idea

After a resistance level breaks, old resistance often becomes new support.
Instead of buying the breakout, the bot waits for price to **come back and
test the broken level**. It enters when the level holds and price turns up
again.

## Entry rule (bullish; bearish mirrors)

- **The level is an *older* ceiling:**
  `resistance = max(High over sr_lookback)`, shifted by `sr_lookback`. That
  is the high of the window that *ended* `sr_lookback` bars ago, not the
  recent one.
- **Tables per horizon:**
  - `recent` (`BRT_RECENT_BARS`): 2w 10, 4w 15, 2m 20, 3m 25, 4m 27, 5m 28,
    6m 30, 7m 32, 8m 33, 9m 35.
  - `retest_pct` (`BRT_RETEST_PCT`): 1.0% on 2w and 3m, 1.5% elsewhere.

1. **It broke:** within the last `recent` bars (excluding today), some high
   exceeded `resistance`, and some bar in that window had volume
   `≥ 1.5 × mean20`.
2. **Back at the level:** `0 ≤ (close − resistance) / resistance ≤ retest_pct`.
3. **Held:** `Low ≥ resistance × (1 − 0.5%)` (`hold_tol_pct`).
4. **Turned:** `close > High[t−1]`.
5. `42 ≤ RSI14 ≤ 63`.
6. Shared: `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`. No
   `vol_ok`, because volume is checked in rule 1.

Bearish: the mirror image against old support, with `37 ≤ RSI ≤ 58` and
`close < Low[t−1]`.

## Plan and exits

Stop `2 × ATR14`, capped at 2%. TP1 comes from the ATR ladder. Exits: trail
**3.0** × ATR, no TP2.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Registry (run 2026-08-17) | VALIDATION 2024–25 | 112 | 49.1% | +0.195 | **WEAK**: v31's VALIDATION flipped it from VALIDATED |
| v84 gated {2m, 3m, 4m} | TRAIN | 105 | 53.3% | +0.308 | gate shipped (it removes a proven-negative population), but 2022 blew up (WR 14.3%, ExpR −0.343), so the badge closed before VALIDATION |
| v104 structural stop, bullish, out-of-scope arm | TRAIN 2010-2025, universe 74 | 482 | 40.2% | +0.214 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, bullish, in-scope arm | same | 405 | 52.3% | +0.319 | Tier 1, beats baseline, clears the fold check (11 qualifying, 10 positive) — **PROCEEDED to the 2026 holdout** |
| v104 structural stop, bullish, in-scope arm | HOLDOUT 2026-01-01..2026-09-25 | 4 | — | — | **sealed-thin** (N=4 < 15); shot unspent, retry when the holdout reaches 12 months |
| v104 structural stop, bearish, out-of-scope arm | TRAIN 2010-2025, universe 74 | 38 | 39.5% | +0.390 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, bearish, in-scope arm | same | 32 | 40.6% | +0.227 | bootstrap lower bound −0.275, no tier — **NO-LIFT at Stage 1** |

Break & Retest is the one Part A strategy gated for both directions. Per the
registry rule (a strategy's row is written only when every admitted direction
passes), **the bearish NO-LIFT means no registry row is written for this
strategy even if the bullish arm's pending holdout retry eventually passes** —
its holdout is sealed-thin above, not a pass. `results/2026-09-28-v104-partA.md`, `results/2026-09-28-v104-holdout.md`.

v84 context: the pooled TRAIN was N=298 WR 48.0%, but it splits by horizon
(2m/3m/4m WR 53.1/57.1/51.4%, while 6m was WR 27.8% ExpR −0.157). The gate
keeps the good horizons and both directions.

**v113 1w cells (Part B, TRAIN 2010-01-01..2025-12-31, universe 74, horizon 1w masked):** bullish N=100, WR 31.0%, ExpR +0.138, lower bound -0.035, no tier; Part B bar failing clauses: wr, lower_bound; folds 0 qualifying / 0 positive. bearish N=7, WR 42.9%, ExpR +0.174, lower bound -0.417, no tier; Part B bar failing clauses: wr, n, scratch, lower_bound; folds 0 qualifying / 0 positive. Neither cell proceeds to the holdout (Part B's bar is Tier 1 plus a bootstrap lower bound > 0; every 1w cell fails Tier 1 on WR); no `cells` admission, no registry row. Source: `results/2026-09-30-v113-partB.md`.

## Pseudocode

```python
R = rolling_max(High, L).shift(L)
broke = max(High[t-recent..t-1]) > R and max(volratio[t-recent..t-1]) >= 1.5
fire if broke and 0 <= Close/R - 1 <= retest_pct and Low >= 0.995*R
        and Close > High[t-1] and 42 <= RSI <= 63 and bull_regime and Close > MA50 and atr_ok
```
