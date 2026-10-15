# v162 — Alpaca history store: 15m, 1h and 1d bars from 2016, the new training data

**Version:** ui 1.24.0 · bot 2.5.2 (at writing)
**Bump:** bot patch (a new research store and a training-data default; no alert, embed or live-scan change)
**Edge:** none (integrity) — it replaces the data every backtest trains on with one consistent, deeper, consolidated-tape source. It adds no strategy and sets no threshold; any edge comes from later specs that use the intraday depth.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer, quant-researcher
**Depends on:** v106 (the Alpaca provider, its SIP feed and the 16-minute free-plan delay).

## Why

Yahoo's intraday depth is a hard ceiling (`known-traps.md` § Two OHLCV caches):
1h reaches ~730 trading days, 15m only ~60. No backtest in this repo has
ever seen an intraday bar older than 2023, and the 15m archive
(`market_data/15min/`, v87) only grows forward from its start.

Alpaca, connected since v106, serves the full SIP tape back to January
2016 on the plan we already have. A read-only probe from the production bot
container on 2026-10-15 (`StockBarsRequest`, `DataFeed.SIP`,
`Adjustment.ALL`, 2016-01-04..2018-01-10) returned:

| tf | AAPL | SPY | first bar |
|---|---|---|---|
| 15m | 29,232 | 31,341 | 2016-01-04 09:00 UTC |
| 1h | 7,802 | 7,936 | 2016-01-04 09:00 UTC |

The partner's decision (2026-10-15): fetch 15m, 1h and 1d for the watchlist
from 2016-01-01 to now into `data/market_data/`, keep it separate from the
live caches, and **use it as the training data from now on**.

## What gets built

### 1. The store: `data/market_data/{15min,hourly,daily}/{TICKER}.csv`

- **Location.** Under `data/` (bind-mounted at `/app/data` on the VM,
  gitignored by the existing `market_data/` pattern). It is a **third**
  OHLCV store, next to `data/backtest_cache/` and the root
  `market_data/`. It is written only by the backfill script below, never by
  `data_refresh`, `backtest_cache.ensure_cached` or any live path. The live
  scan never reads it.
- **Format.** CSV, same columns and filename scheme as the other two caches
  (`Open, High, Low, Close, Volume`, index `Datetime` for intraday and `Date`
  for daily, `safe_symbol()` names). No new dependency. Measured size
  estimate for 77 tickers × 10.8 years: about 17M rows with extended hours,
  about **1.2 GB** on disk. The VM has 12 GB free.
- **Source.** `DataFeed.SIP`, `Adjustment.ALL` (split and dividend
  adjusted), `end = now − SIP_DELAY`: the same request shape
  `AlpacaProvider._bars` already makes. One client, reused from
  `providers/alpaca_provider.py`; the backfill does not open its own.
- **15min.** Native Alpaca 15-minute bars, **all sessions stored**
  (04:00–20:00 ET). Readers filter to regular hours by default (§3). Storing
  extended hours costs about 2.5× the rows and keeps a later pre-market study
  possible without a second backfill.
- **hourly.** Built from Alpaca **30-minute** bars with the existing
  `providers.base.to_yf_hourly()`: 09:30-anchored, regular hours only,
  identical in shape to the hourly bars the bot already uses. Alpaca's native
  `1Hour` bars are clock-aligned (09:00, 10:00), and their first regular-hours
  bar would mix pre-market with the open. They are not used.
- **daily.** Native Alpaca daily bars through `to_yf_daily()`.
- **A manifest per timeframe**, `data/market_data/{tf}/_manifest.json`:
  per ticker, the first and last bar, row count, fetch time, the adjustment
  check result (§2) and a status (`ok`, `skipped: <reason>`,
  `flagged: <reason>`). A training run copies the manifest's fetch time into
  its result JSON (§3).

### 2. The backfill script: `scripts/data/fetch_alpaca_history.py`

- `--timeframes 15min,hourly,daily` (default all three), `--start 2016-01-01`,
  `--tickers` (default: the Postgres watchlist), `--mode full|update`.
- **Runs on the VM**, where the Alpaca keys are (`docker compose exec -T bot
  python scripts/data/fetch_alpaca_history.py ...`). The dev machine gets the
  store by pulling it down (§4).
- **Paginated and rate-safe.** One symbol per request for intraday (a
  multi-symbol request shares one 10,000-row page budget, so it saves
  nothing), honouring Alpaca's page token. A token bucket keeps it under 180
  requests a minute (free plan: 200). A 429 or 5xx backs off and retries; a
  401/403 (`AlpacaAuthError`) stops the run. A full run over 15 minutes
  prints a percent, per the repo rule for long runs.
- **Resumable.** Each ticker × timeframe is written atomically (temp file,
  then rename) when it completes. A rerun of `--mode full` skips files whose
  manifest entry is `ok` and newer than `--start` was requested, unless
  `--force`.
- **Skips what Alpaca cannot serve.** The two spot metals (`XAUUSD`,
  `XAGUSD`, built from `GC=F`/`SI=F` per v109), futures (`=F`), indices
  (`^`) and anything `to_alpaca_symbol()` rejects get `skipped:` in the
  manifest. They are listed at the end of the run, never silently dropped.
- **Identity check before a file is accepted.** The `market_cache_repair`
  incident (v116 follow-up) proved one bad fetch can hand a ticker another
  instrument's history. Every daily frame is compared with
  `market_data/daily/{TICKER}.csv` over the overlapping bars, the same
  median-close-ratio test as `market_cache_repair.alpaca_verdict`
  (tolerance 0.5%). A disagreeing ticker is written but marked `flagged:`.
  Ticker reuse is the live risk here: `SNDK` was SanDisk until 2016 and is a
  new listing since 2025. Bars from before the yfinance file's first bar are
  dropped for that ticker, and the manifest says so. The intraday files of a
  ticker inherit its daily status.
- **`--mode update` never merges across an adjustment change.** The repo's
  other caches append and never overwrite, which is how a single bad fetch
  became permanent (`known-traps.md` § The market_data cache never
  self-heals). With `Adjustment.ALL`, every new split or dividend shifts all
  older bars. So `update` fetches from the last cached bar minus 5 sessions.
  If the overlap's closes match within 0.01%, it appends. Otherwise it
  refetches that ticker × timeframe in full and replaces the file. It never
  writes a frame that mixes two adjustment bases.
- **A weekly cron on the VM** runs `--mode update` (Sunday, outside market
  hours), mirrored under `scripts/ops/` per the production-change rule.

### 3. Training reads it by default

- **One read seam**, `swingbot/core/marketdata/history_store.py`:
  `load(ticker, timeframe, session="rth")` returns a normalized frame or
  `None`, plus `manifest(timeframe)`. `session="all"` returns extended hours
  for 15min. It has no network and no write path.
- **The backtest and grid scripts that read `data/backtest_cache/` today**
  (`run_backtest_range.py`, `tune_strategy.py`, the `measure_*` scripts and
  `backtest_wf.py`; the plan's brief enumerates every one) take
  `--data-source alpaca|yfinance`, **default `alpaca`**. `yfinance` reads
  `data/backtest_cache/` exactly as today, so an old result can still be
  reproduced.
- **No silent fallback.** Under `alpaca`, a ticker the manifest marks
  `skipped` or `flagged`, or has no file for, is left out of the run. Its name
  and reason are printed and recorded. A training run never quietly mixes
  sources.
- **Provenance in every result JSON**: `data_source`, the manifest fetch
  time, and the tickers excluded. A result without them was produced on the
  old data.
- **Unchanged:** the Stage −2 idea screen keeps `data/backtest_cache_ext/`
  (point-in-time S&P 500, 2010–2019). Alpaca starts in 2016 and has no
  delisted names, so it cannot serve that screen. The live scan, `data_refresh`,
  the root `market_data/` cache and every alert stay as they are.

### 4. Pulling it to the dev machine

`scripts/ops/pull_history_store.sh` streams the VM store into this repo's
`data/market_data/` through `scripts/ops/ssh-hetzner.sh` (a `tar` over the
existing wrapper, never a raw `scp`), then prints the manifest summary. About
1.2 GB uncompressed, much less compressed.

### 5. The re-baseline measurement

Switching the training data moves every number measured on yfinance. So the
plan's last data task runs the current engine's TRAIN baseline (the
`run_backtest_range.py --train` command the methodology uses for the live
config) **once on each source** and records both in
`docs/superpowers/results/`: trades, win rate, ExpR, and the per-ticker
trade-count differences. This is a measurement of the data change, not a
selection decision. It tunes nothing, uses no VALIDATION run, and re-runs no
closed pre-registration. From this result on, a new spec compares against
the Alpaca baseline.

## Known differences the partner should expect

- **Shorter warm-up.** `backtest_cache` daily history goes back to 2000 or
  listing. Alpaca starts in 2016, four years before TRAIN starts in 2020.
  SMA200 and one-year structure are fine. Anything that looks back more than
  about four years (multi-year support/resistance levels) sees less history,
  so some 2020 setups can change. §5 measures it.
- **The SIP tape, not Yahoo's composite.** Volume and a few highs and lows
  differ slightly. Daily closes should match within the 0.5% identity
  tolerance.
- **Adjustment basis.** `Adjustment.ALL` adjusts for dividends as yfinance's
  `auto_adjust=True` does, but the two vendors' dividend factors are not
  identical. The difference is small and uniform per ticker.
- **Survivorship is unchanged.** Training already uses the current watchlist,
  so a store with no delisted names loses nothing the old cache had.

## Out of scope

- Unadjusted bars, 5m/1m bars, and symbols beyond the watchlist (each one
  flag away later).
- Any strategy that uses intraday bars. It needs its own `SCREEN-PASS` row
  first.
- Moving the live scan or `market_data/` onto Alpaca history.

## Acceptance

1. The VM store holds 15min, hourly and daily files for every watchlist
   equity, starting 2016-01-04 or the listing date, ending within one session
   of the run. Every skip or flag is listed with its reason.
2. Row counts are sane: regular-hours 15min ≈ 26 bars a session, hourly 7,
   with each gap explained by a half-day or holiday. The plan includes a
   check script.
3. A second `--mode update` run on an unchanged day writes nothing. A
   simulated adjustment change triggers a full refetch, never a mixed file.
4. `run_backtest_range.py --train` with no flag reads the Alpaca store and
   stamps provenance. `--data-source yfinance` reproduces a pre-v162 result
   exactly.
5. The §5 two-source baseline is committed under `docs/superpowers/results/`.
6. The cron is installed on the VM and mirrored in `scripts/ops/`.
