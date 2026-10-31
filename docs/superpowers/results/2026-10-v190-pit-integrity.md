# v190 PIT store: frozen integrity report

**Spec:** `docs/superpowers/specs/2026-10-24-v190-pit-alpaca-universe-design.md`
**Plan:** `docs/superpowers/plans/2026-10-24-v190-pit-alpaca-universe_0-index.md` (Task V190-21)

## Freeze

- UTC time: 2026-10-31T18:52:05Z
- `data/market_data_pit/_integrity.json` sha256: `15fc954888263f3a8041a8387416cdf12ec10cd605cbeb9c7eff0c83c725f99b`
- Manifest sha256: daily `a2b8fd240553e70c90d7a9c3be19428c9b56b462e35cd5e874601bc4a9169d41`, hourly `4f6677c76a637a9d77e0f809bc9e2aa775445dd9b4c7525eea921b08e88ba3ad`, 15min `9b61d9853714051d8d87a81e0555ea49cc8649acfc5abab1466136e7d84d7ecc` (unchanged between draft and freeze)
- Detector blob ids: `reuse.py` `11ca528237094371aca4997cfccebf167d498d82`, `pit_coverage.py` `8753cea14988d07b175f53593067ac6e8848f0df`
- Worktree HEAD at freeze: `a4c092abe972ceaf5355105309dae0b3d6fc7b79`

Frozen before any strategy result was read. A `--mode update` on `data/market_data_pit/` after this point makes every v3 run stop with `StaleIntegrityError`.

## Thresholds

None changed: `max_missing_run 5`, `trailing_sessions 60`, `min_trailing_share 0.95`, `break_move 0.5`, `break_ratio 10.0`, `revert_sessions 20`, `gap_sessions 20`, `edge_sessions 20`.

## Calibration set

| Ticker | Expected | Observed |
| --- | --- | --- |
| MON | trimmed after the break past its last membership end | admitted; `keep_before 2021-03-16`, `break after last membership end` |
| TWTR, XLNX, ATVI, CELG, CTXS | admitted, no break, no trim | as expected |
| SIVB | admitted, no break | **excluded**: `unresolved break 2023-03-09 (edge)` (last bar 2023-03-09, the bank-failure collapse) |
| FRC | admitted, no break | **excluded**: `in-span break 2023-03-13 (volume): resolve by hand` |
| AAPL, TSLA, NVDA (forward splits), GE (reverse split) | no break | as expected |

SIVB and FRC miss the plan's expectation. No threshold was moved for them (see Hand resolutions).

## Hand resolutions

Partner decision 2026-10-31: freeze as-is with these six excluded; the report has no hand-override field. Evidence is the break kind and date from the report plus the public event, not a re-plotted price window. Every verdict is a **same-issuer event**, so each exclusion drops a real member.

| Ticker | Date | Kind | Resolution | Verdict |
| --- | --- | --- | --- | --- |
| SIVB | 2023-03-09 | edge | unresolved | same issuer: bank-failure collapse at the last bar |
| FRC | 2023-03-13 | volume | in_span | same issuer: bank-failure collapse |
| FI | 2023-06-07 | price+volume | in_span | same issuer: Fiserv ticker change FISV to FI |
| ARNC | 2020-04-01 | price | in_span | same issuer: Arconic/Howmet separation |
| CTRA | 2021-10-04 | volume | in_span | same issuer: Cabot/Cimarex merger |
| APTV | 2017-12-05 | edge | unresolved | same issuer: Delphi Technologies spin-off |

Consequence for v3 results: the universe under-represents blow-ups (SIVB, FRC), a survivorship bias that flatters long-side results slightly. A follow-up spec can add an evidenced admit-override to the integrity contract and re-freeze; until then every v3 figure carries this caveat.

## Counts

865 tickers in the manifests; 754 admitted, 67 excluded (60 `identity re-derived`, 2 `no daily bars in the store window`, 5 break exclusions: ARNC, CTRA, FI, FRC, SIVB... plus APTV counted under `unresolved`), 44 no bars (alias table empty, see backfill log), 30 members with a trim. Context symbols: all 17 admitted. `td.select('alpaca', 'pit', '2025-12-31')` reports 754 available and 111 excluded (67 plus the 44 no-bars).

## Tool summary

See `2026-10-v190-pit-integrity-report.md`.
