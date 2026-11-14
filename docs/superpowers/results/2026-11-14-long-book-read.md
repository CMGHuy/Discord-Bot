# LONG book read, production, 2026-11-14

Read-only export of the production book (`scripts/ops/export_book_rows.sh`,
1,088 closed trades, 760 bullish) plus a read-only pass over the VM's 5-minute
bars. Every figure here is **exploratory**: a live-book cell picked from many
slices, never evidence for a rule. Nothing was changed on production.

## The book

LONG trades closed on or after 2026-10-01 (UTC):

| Window | N | Win rate | ExpR | Avg win | Avg loss |
|---|---|---|---|---|---|
| Since 2026-10-01 | 363 | 25.9% | +0.041R | +2.41R | -0.78R |
| Last 30 days | 310 | 25.2% | +0.006R | +2.42R | -0.81R |
| Last 14 days | 173 | 23.7% | +0.020R | +2.74R | -0.83R |

| Last leg | N | Sum R |
|---|---|---|
| `loss` | 196 | -207.2 |
| `scratch` (breakeven stop) | 73 | -3.9 |
| `tp1_runner_be` | 48 | +77.9 |
| `tp1_runner_tp2` | 44 | +141.1 |

Slices, same window:

| Slice | N | Win rate | ExpR |
|---|---|---|---|
| Closed the day it opened | 196 | 14.8% | -0.382R |
| Held overnight | 167 | 38.9% | +0.538R |
| Entered in the `open` session bucket | 178 | 25.3% | -0.043R |
| Entered `midday` | 150 | 23.3% | -0.006R |
| Entered `close` | 35 | 40.0% | +0.672R |
| Source `FVG (bearish)` | 64 | 17.2% | -0.188R |
| Source `FVG (bullish)` | 34 | 38.2% | +0.308R |
| `regime2_state` = `bull_volatile` | 96 | 17.7% | -0.307R |
| `entry_type` = `stop_entry` | 21 | 9.5% | -0.478R |

The same-day split is conditioned on the outcome, so it describes where the
losses sit and is not a filter. `bull_volatile` is already closed (`REGIME_ALLOW`,
v17 P2a: 0 of 44 cells). `stop_entry`, the 4m/9m horizons and the Wednesday cell
are small and unadjusted for the number of slices read; no action.

## Finding 1: the stored MFE/MAE is wrong for short holds

`swingbot/core/analytics/mfe_mae.py` slices **daily** bars from the entry day to
the exit day, so a trade that lives a few hours is credited with the whole day's
range, including the part before its entry and after its exit. Recomputed from
5-minute bars between `opened_at` and `closed_at` (357 of 363 trades had
coverage):

| Last leg | N | Median MFE, 5-minute | Median MFE, stored | Median MAE, 5-minute |
|---|---|---|---|---|
| `loss` | 192 | 0.31R | 1.24R | 1.16R |
| `scratch` | 71 | 1.38R | 1.67R | 0.41R |
| `tp1_runner_be` | 48 | 2.61R | 2.90R | 0.30R |
| `tp1_runner_tp2` | 44 | 3.49R | 3.52R | 0.12R |

Losers that truly reached +1R before stopping out: **13 of 192**. The stored
field puts 167 of the 269 non-winners at or above +1R. Exit efficiency, the
journal's auto-lessons and every give-back read on the live book inherit the
error. This earns the integrity spec that follows this document.

## Finding 2: the breakeven move has no headroom

Hypothesis read: with stops clamped near 0.35 ATR, moving the stop to breakeven
at `BREAKEVEN_TRIGGER_FRACTION = 0.5` of the TP1 distance might be turning
winners into scratches. Counterfactual on the 71 scratches with 5-minute
coverage: after the breakeven exit, which of the original stop and TP1 trades
first, within 14 calendar days?

| First touch after the scratch | N |
|---|---|
| Original stop | 51 |
| TP1 | 18 |
| Neither | 2 |

| Trigger fraction | Scratches that would continue | Reach TP1 | Hit the stop | Change over 357 longs |
|---|---|---|---|---|
| 0.75 | 40 | 12 (+26.0R at TP1) | 27 (-27R) | +0.001R per trade |
| 1.0 (no move before TP1) | 71 | 18 (+37.6R at TP1) | 51 (-51R) | -0.027R per trade |

TP1 touches are credited at TP1 only. Crediting them at the book's mean R for a
TP1 trade (about 2.4R) leaves 1.0 negative and 0.75 near zero. The breakeven
move is doing its job: about 72% of scratches go on to the original stop.

**Outcome:** no harvest headroom, so no spec. A later-trigger or no-trigger
breakeven arm is not worth a pre-registration on this evidence; reopening needs
a measured headroom from a different mechanism, not this read repeated.

## What this read leads to

- **Intraday MFE/MAE** (finding 1): integrity spec, written next.
- **Entry session:** the `close` bucket cell is the largest unexplained
  difference in the book. A daily-bar screen cannot see it; it gets a
  deferred-entry counterfactual on the bot's own plans with forward confirmation.
- **Bearish-FVG long source:** one avoid-mode idea screen. Prior evidence runs
  against it (`screen-fvg_overhead_aged` SCREEN-FAIL at +0.37R, v128 `off`
  ΔExpR -0.004R), and the live cell is about one standard error from zero.
- **Noise stop-outs from clamped stops:** already v212 / v216, in flight.
