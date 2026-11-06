# Live-book loss review, 2026-09-01..2026-11-06

**Source:** `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rows" < scripts/ops/export_book_rows.sh`
(read-only, run 2026-11-06 08:31 UTC). The raw CSV stays out of the repo.
**Population:** `row_kind = trade`, `opened_at >= 2026-09-01`, `r_realized`
not null. N = 392 (200 loss, 90 win, 76 scratch, 26 closed).

These are live-book, in-sample, exploratory numbers. They motivated v214 (first numbered v211, renumbered after a collision) and
v212 and do not license any gate. The split at 2026-09-01 is the partner's
window, chosen before the analysis. The pre-September rows are shown for
contrast only.

## Book

| Cut | N | ExpR | WR | Sum R |
|---|---|---|---|---|
| All | 392 | +0.049 | 27% | +19.1 |
| Excluding manual admin closes | 367 | −0.012 | — | — |
| Manual admin closes | 25 | +0.935 | 64% | +23.4 |
| Opened 2026-09 | 94 | +0.020 | 31% | +1.8 |
| Opened 2026-10 | 225 | +0.128 | 28% | +28.8 |
| Opened 2026-11 (to the 6th) | 73 | −0.159 | 18% | −11.6 |
| Longs | 339 | −0.002 | 26% | −0.8 |
| Shorts | 53 | +0.374 | 34% | +19.8 |

## Losses

- **Holding time.** Median 0.09 days (2.2 h). 88% stopped within 1 day, 93%
  within 2 days.
- **Stop distance** (`|entry − stop| / entry`). Median 1.77% for losses and
  1.80% for wins. 80 of 392 trades sit at or under 1.75%.
- **ATR at entry.** Daily-range ATR14 proxy from yfinance: median 4.74% of
  price on the 196 non-FX losses. The stop is therefore about 0.37 ATR.
- **After the stop.** 57% of those 196 losses saw price reach TP1 within 10
  sessions after the stop-out (daily highs/lows, yfinance, fetched
  2026-11-06).
- **Clustering.** The worst close-days were 2026-11-05 (43 closed, −17.8R)
  and 2026-10-30 (25 closed, −11.9R). Both are covered by v209/v210.

## Plan attribution by target source (`primary_strategy_for`)

| Population | N | ExpR | WR | Sum R |
|---|---|---|---|---|
| Longs, `FVG (bearish)`, opened Sep 1 onward | 68 | −0.199 | 19% | −13.6 |
| Longs, `FVG (bearish)`, opened before Sep 1 | 61 | −0.060 | — | −3.7 |
| Longs, `FVG (bullish)`, opened Sep 1 onward | 33 | +0.298 | 36% | +9.8 |

**Looked at and dropped:**
- **Earnings within 5 days** (N 54, −0.286): v82 is closed, and it pointed
  the opposite way on TRAIN.
- **The volatile regimes:** almost entirely 2026-11-05.
- **Same-day re-entry after a stop-out on the same ticker:** N 76, +0.027,
  against +0.050 for first-of-day trades. Not worse overall.
