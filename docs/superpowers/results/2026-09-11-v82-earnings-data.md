# v82 earnings blackout — earnings data and replay cost

Not a stage. Records the inputs Run 1 reads, before Run 1 starts.

## Earnings dates (Yahoo, `scripts/data/fetch_earnings_dates.py`)

`written 0 | skipped 73 | ETF 14 | no data 2`

This is the closing summary from the idempotent confirmation run. The initial
fill created the 73 non-ETF CSVs; its missing closing summary was corrected
before the confirmation run. The two symbols that still have no data are
`GC_F` and `SI_F`.

## Replay cost

One ticker (AAPL), all 10 horizons, 11 strategies plus the confluence replay,
window 2018-06-01..2023-12-31, serial: 235.574 s.
Projected Run 1: 235.574 s x 89 / 12 workers ~= 0.49 h (29.1 min).
