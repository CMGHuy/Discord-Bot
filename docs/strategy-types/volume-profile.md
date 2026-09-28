# Volume Profile (high-volume-node bounce)

`ENTRY_FUNCS["Volume Profile"]` = `volume_profile_entries` · signal
`volume_profile_signal` · sizing **ATR family** · gate **bullish, 7m only**.
Shared rules: [shared-mechanics.md](shared-mechanics.md).

**One of the two VALIDATED strategies.** MACD is the other.

## Idea

The price where the most volume changed hands (a **high-volume node**, HVN)
acts as a magnet and a floor. Buy a bounce just above a *significant* node.

## How the node is found (`_vectorized_hvn`)

For each bar `i`, over the **previous** `sr_lookback` bars (`i−L … i−1`,
today excluded; `L` is 210 on 7m):

1. Split the window's price range `[min Low, max High]` into **20 bins**.
2. Put each bar's volume into the bin of its midpoint `(H + L) / 2`.
3. The HVN is the **centre of the heaviest bin**. Its *share* is that bin's
   volume over total volume, in %.

## Entry rule (bullish; bearish mirrors)

1. **Just above the node:** `0 ≤ (close − HVN) / HVN ≤ 1.5%` (`prox_pct`).
2. **Significant node:** share ≥ 8% (`node_share`). With 20 bins, an even
   spread is 5% each.
3. **Bouncing:** `close > close[t−1]`.
4. `44 ≤ RSI14 ≤ 64`.
5. Shared: `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`, `vol_ok`.

Bearish: `close` 0–1.5% *below* the node, falling, `36 ≤ RSI ≤ 56`, and the
bear gates.

## Plan and exits

Stop `2 × ATR14`, capped at 2%. TP1 comes from the ATR ladder. The node itself
is not used for sizing. Exits: trail **3.0** × ATR, no TP2.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Registry (run 2026-08-17) | VALIDATION 2024–25 | 32 | 53.1% | +0.547 | **VALIDATED** (v31 shot, pre-2% cap) |
| v104 structural stop, out-of-scope arm | TRAIN 2010-2025, universe 74 | 354 | 42.7% | +0.334 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, in-scope arm | same | 300 | 54.3% | +0.372 | Tier 1, beats baseline, clears the fold check (11 qualifying, 8 positive) — **PROCEEDED to the 2026 holdout** |
| v104 structural stop, in-scope arm | HOLDOUT 2026-01-01..2026-09-25 | 9 | — | — | **sealed-thin** (N=9 < 15); shot unspent, one retry when the holdout reaches 12 months. `results/2026-09-28-v104-holdout.md` |

It has the best ExpR in the registry but the smallest N. N=32 barely clears
the VALIDATION floor of 15, so treat the size of the edge with caution. The
bearish arm failed in v93 and stays masked.

## Pseudocode

```python
hvn, share = heaviest_bin(prev L bars, 20 bins, weight=Volume, price=(H+L)/2)
fire if 0 <= Close/hvn - 1 <= 1.5% and share >= 8% and Close > Close[t-1]
        and 44 <= RSI <= 64 and bull_regime and Close > MA50 and tape_ok
```
