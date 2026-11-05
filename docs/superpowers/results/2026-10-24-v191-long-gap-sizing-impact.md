# v191 gap sizing impact: the live book's closed longs re-sized

**Spec:** [v191 design](../specs/2026-10-24-v191-confluence-atr-band-stops-design.md) § "Part B — gap-aware dollar sizing for longs and shorts"
**Run:** 2026-11-05 on `swingbot_prod_replica` (read-only replica of production), `scripts/reports/short_gap_sizing_impact.py --side long`
**Status:** descriptive, not a gate. `LONG_GAP_SIZING=false` is the revert path.

## What is measured

Each closed long (status win/loss/closed, direction bullish) is sized twice at a fixed risk of $100.00 per trade (balance $10,000.00, 1.0%): on the stop, and with the gap floor `max(|entry - stop|, entry x p99_down_gap / 100)`. p99 source: the trade's stored stamp, else the down-gaps over the 250 completed daily bars before the open (fewer than 60 down-gaps: no p99, no change). Dollar P&L = shares x stop distance x the book's R. An exceedance is a dollar loss past the fixed risk.

## Result

| Measure | Value |
|---|---|
| Closed longs in the book | 773 |
| Analysed (R computable) | 772 |
| p99 from a stored stamp / from bars / none | 0 / 761 / 11 |
| Gap-sized (share cut) | 757 (98.1%) |
| Mean size cut, gap-sized longs | 68.2% |
| Mean size cut, all analysed longs | 66.9% |
| Mean R (identical both sides) | -0.088R |
| Dollar P&L at fixed risk, before | -$6,778.16 |
| Dollar P&L at fixed risk, after | -$1,461.81 |
| Losses past the fixed risk, before | 103 |
| Losses past the fixed risk, after | 7 |

## Worst five dollar losses

Before (stop sizing):

| Ticker | Closed | R | $ before | $ after |
|---|---|---|---|---|
| NBIS | 2026-08-04 | -6.03R | -$603.03 | -$145.88 |
| TSLA | 2026-09-05 | -3.85R | -$384.70 | -$175.19 |
| DELL | 2026-08-04 | -3.50R | -$350.14 | -$103.02 |
| GLW | 2026-08-04 | -3.47R | -$347.05 | -$79.39 |
| MRNA | 2026-08-04 | -3.26R | -$326.00 | -$178.70 |

After (gap sizing):

| Ticker | Closed | R | $ before | $ after |
|---|---|---|---|---|
| MRNA | 2026-08-04 | -3.26R | -$326.00 | -$178.70 |
| TSLA | 2026-09-05 | -3.85R | -$384.70 | -$175.19 |
| NBIS | 2026-08-04 | -6.03R | -$603.03 | -$145.88 |
| ARM | 2026-08-05 | -2.19R | -$219.05 | -$128.96 |
| SPCX | 2026-08-03 | -1.22R | -$121.82 | -$121.82 |

## Long-book drawdown

| Measure | Before | After |
|---|---|---|
| Max drawdown, $ in close order | $8,702.60 | $2,405.12 |
| Max drawdown, % of balance | 87.0% | 24.1% |
| Bootstrap max drawdown p50 (ruin.simulate, 1000 trades x 2000 paths) | 67.5% | 25.3% |
| Bootstrap max drawdown p95 | 82.2% | 39.9% |

## Limits

- p99 over about 125 down-gaps is roughly the one or two largest down-gaps of the year: noisy, the same limit v183 accepted for shorts.
- Position caps are off and OPEX scaling is pinned to 1.0 so only the gap rule moves size; with the live caps the cut is the same or smaller.
- No long carried a down-gap stamp before v191 shipped; its p99 is recomputed from the cached daily bars before the open, so a bar-cache gap shows up as `none` (size unchanged).
- R, win rate and ExpR are identical on both sides by construction (R is measured on the stop); only dollars move.
- A gap beyond the ticker's own p99 can still exceed the budget; the exceedance rows count those losses.

## Rollback

- **No deploy needed:** set `LONG_GAP_SIZING=false` in `.env` or the admin config page; the bot hot-reloads. A live `CONFLUENCE_ATR_STOP_FLOOR > 0` is honoured only with `LONG_GAP_SIZING` and `SHORT_GAP_SIZING` both on, so turning this off also zeroes a live floor (logged at ERROR).
- Plans stamped while the switch was on keep their stamped rule; long plans created after the flip size on the stop exactly as before v191.
- Paper trades already sized by the gap rule stay in the book as recorded; nothing re-sizes them.
