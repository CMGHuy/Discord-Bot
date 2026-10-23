# v183 gap sizing impact: the live book's closed shorts re-sized

**Spec:** [v183 design](../specs/2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md) § "Measured once, after build (not a gate)"
**Run:** 2026-10-23 on `swingbot_prod_replica` (read-only replica of production), `scripts/reports/short_gap_sizing_impact.py`
**Status:** descriptive, not a gate. The cut stays unvalidated; `SHORT_GAP_SIZING=false` is the revert path.

## What is measured

Each closed short (status win/loss/closed, direction bearish) is sized twice at a fixed risk of $100.00 per trade (balance $10,000.00, 1.0%): on the stop, and with the gap floor `max(|entry - stop|, entry x p99_up_gap / 100)`. p99 source: the trade's stored stamp, else the up-gaps over the 250 completed daily bars before the open (fewer than 60 up-gaps: no p99, no change). Dollar P&L = shares x stop distance x the book's R.

## Result

| Measure | Value |
|---|---|
| Closed shorts in the book | 335 |
| Analysed (R computable) | 331 |
| p99 from a stored stamp / from bars / none | 0 / 309 / 22 |
| Gap-sized (share cut) | 307 (92.7%) |
| Mean size cut, gap-sized shorts | 74.0% |
| Mean size cut, all analysed shorts | 68.6% |
| Mean R (identical both sides) | -0.093R |
| Dollar P&L at fixed risk, before | -$3,062.70 |
| Dollar P&L at fixed risk, after | -$1,118.23 |

## Worst five dollar losses

Before (stop sizing):

| Ticker | Closed | R | $ before | $ after |
|---|---|---|---|---|
| ORCL | 2026-09-10 | -3.78R | -$378.01 | -$107.17 |
| FTNT | 2026-07-29 | -3.58R | -$358.11 | -$110.73 |
| DDOG | 2026-09-03 | -3.06R | -$305.59 | -$46.42 |
| SHOP | 2026-08-06 | -2.73R | -$272.97 | -$67.06 |
| SHOP | 2026-08-05 | -2.61R | -$261.02 | -$68.74 |

After (gap sizing):

| Ticker | Closed | R | $ before | $ after |
|---|---|---|---|---|
| PATH | 2026-07-24 | -1.16R | -$116.13 | -$116.13 |
| SPCX | 2026-07-31 | -1.13R | -$113.49 | -$113.49 |
| PATH | 2026-07-28 | -1.11R | -$111.32 | -$111.32 |
| FTNT | 2026-07-29 | -3.58R | -$358.11 | -$110.73 |
| PYPL | 2026-07-15 | -1.10R | -$109.77 | -$109.77 |

## Short-book drawdown

| Measure | Before | After |
|---|---|---|
| Max drawdown, $ in close order | $5,148.21 | $1,603.07 |
| Max drawdown, % of balance | 51.5% | 16.0% |
| Bootstrap max drawdown p50 (ruin.simulate, 1000 trades x 2000 paths) | 67.1% | 31.7% |
| Bootstrap max drawdown p95 | 81.9% | 43.0% |

## Limits

- p99 over about 125 up-gaps is roughly the one or two largest up-gaps of the year: noisy, accepted in the spec.
- Position caps are off and OPEX scaling is pinned to 1.0 so only the gap rule moves size; with the live caps the cut is the same or smaller.
- Trades opened before v183 shipped carry no stamp; their p99 is recomputed from the cached daily bars before the open, so a bar-cache gap shows up as `none` (size unchanged).
- R, win rate and ExpR are identical on both sides by construction (R is measured on the stop); only dollars move.

## Rollback

- **No deploy needed:** set `SHORT_GAP_SIZING=false` (and `SHORT_RISK_NOTICE=false` for the notice) in `.env` or the admin config page; the bot hot-reloads. Plans stamped while the switch was on keep their stamped rule; plans created after the flip size on the stop exactly as before v183.
- **Code rollback** (`scripts/ops/rollback_to.sh`): the `gap_sizing` / `risk_notice` keys on plan docs and trade records and the `data/short_interest.json` cache are left in place, unread and harmless.
- Paper trades already sized by the gap rule stay in the book as recorded; nothing re-sizes them.
