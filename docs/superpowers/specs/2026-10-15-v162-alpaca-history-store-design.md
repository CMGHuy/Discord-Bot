# v162 — Alpaca history store: 15m, 1h and 1d bars from 2016, the new training data

**Version:** ui 1.24.0 · bot 2.5.2 (at writing)
**Bump:** bot patch (a new research store, a training-data default and a provenance field on result rows; no alert, embed or live-scan change)
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
live caches, and **use it as the training data from now on**. That choice is
fixed. It does not depend on what §5 measures (see § Research discipline).

## What gets built

### 1. The store: `data/market_data/{15min,hourly,daily}/{TICKER}.csv`

- **Location.** Under `data/` (bind-mounted at `/app/data` on the VM,
  gitignored by the existing `market_data/` pattern, `.gitignore:31`). It
  is a **third** OHLCV store, next to `data/backtest_cache/` and the root
  `market_data/`. Only the backfill script below writes to it. `data_refresh`,
  `backtest_cache.ensure_cached` and every live path leave it alone, and the
  live scan never reads it. `data/backtest_cache/` stays in place: the live
  bot, the journal backfill and the `yfinance` source still use it, so it
  is not retired.
- **Format.** CSV, same columns and filename scheme as the other two caches
  (`Open, High, Low, Close, Volume`, `safe_symbol()` names). No new
  dependency. Estimated size for 77 tickers × 10.8 years: about 17M rows
  with extended hours, about **1.2 GB** on disk.
- **One index convention, stated and tested.** Intraday files use naive
  **America/New_York wall-clock** times, labelled at the bar start
  (`Datetime`). Daily files use naive dates (`Date`). Alpaca returns UTC, and
  `to_yf_hourly` returns a tz-aware NY index (`providers/base.py:46`); both
  are converted before writing. `backtest_cache.normalize_ohlcv`
  (`backtest_cache.py:68`) and `data_store.py:331` expect naive indexes. A
  round-trip test (fetch frame → CSV → `history_store.load()`) pins this
  across one DST change in each direction.
- **Source.** `DataFeed.SIP`, `Adjustment.ALL` (split and dividend
  adjusted), `end = now − SIP_DELAY`, the same shape as
  `AlpacaProvider._bars` (`alpaca_provider.py:93-99`). `_bars` takes no
  `end` or page control, and alpaca-py pages inside one call. So the
  provider gains one public method, `history_bars(ticker, timeframe, start,
  end)`, and the backfill calls it **one calendar year at a time**. That
  keeps memory bounded, makes each year a resume point and lets a rate
  limiter count the calls. Live callers of `_bars` are unchanged.
- **15min.** Native Alpaca 15-minute bars, **all sessions stored**
  (04:00–20:00 ET). Readers filter to regular hours by default (§3).
- **hourly.** Built from Alpaca **30-minute** bars with the existing
  `providers.base.to_yf_hourly()`: 09:30-anchored, regular hours only, the
  same shape as the hourly bars the bot already uses. The last bar of a
  session (15:30–16:00) covers only 30 minutes, and on half-days the session
  ends earlier. Its volume is not comparable with a full hour. Alpaca's
  native `1Hour` bars are clock-aligned and are not used.
- **daily.** Native Alpaca daily bars through `to_yf_daily()`.
- **A manifest per timeframe**, `data/market_data/{tf}/_manifest.json`:
  per ticker, the first and last bar, row count, fetch time, a SHA-256 of
  the file, the identity-check result (§2) and a status (`ok`,
  `skipped: <reason>`, `flagged: <reason>`). The top level records feed
  (`sip`), adjustment (`all`) and a hash over all per-ticker hashes.

### 2. The backfill script: `scripts/data/fetch_alpaca_history.py`

- `--timeframes 15min,hourly,daily` (default all three), `--start 2016-01-01`,
  `--tickers` (default: the Postgres watchlist), `--mode full|update`.
- **Runs on the VM in its own container**, outside market hours:
  `docker compose run --rm bot python scripts/data/fetch_alpaca_history.py ...`.
  It does not use `exec` into the running bot, which is capped at
  `cpus: "1.0"` (`docker-compose.yml:111-118`) beside the 5-minute scan.
  During the US regular session it refuses to start unless given `--force-hours`.
- **Rate-safe, beside the live provider.** The key's budget (200
  requests a minute) is shared with the live scan. The backfill's token
  bucket is capped at **120 requests a minute**. A 429 or 5xx backs off and
  retries. A 401/403 (`AlpacaAuthError`) stops the run. A run over 15
  minutes prints a percent.
- **Disk guard.** Before writing, the script estimates the run's size and
  refuses if free space would drop below 3 GB. The same disk holds the PITR
  repository (`docker-compose.yml:73`) and the nightly dumps
  (`scripts/ops/backup_db.sh:15`). The plan records the measured full-run
  size and the weekly update's growth.
- **Resumable and atomic.** Each ticker × timeframe is written to a temp
  file and renamed when complete. A rerun of `--mode full` skips files whose
  manifest entry is `ok` and covers `--start`, unless given `--force`.
- **Skips what Alpaca cannot serve.** The spot metals (`XAUUSD`, `XAGUSD`,
  built from `GC=F`/`SI=F` per v109), futures (`=F`), indices (`^`) and
  anything `to_alpaca_symbol()` rejects are marked `skipped:` and listed at
  the end of the run.
- **Identity check before a file is accepted.** One bad fetch can hand a
  ticker another instrument's history (`known-traps.md` § The market_data
  cache never self-heals). The check compares each daily frame with
  `data/backtest_cache/{TICKER}.csv`, which goes back to 2000 or listing. It
  falls back to `market_data/daily/` when that file is missing. The test is
  the median close ratio over the overlap (tolerance 0.5%, as
  `market_cache_repair.ALPACA_TOLERANCE`). It is NaN-safe and needs at least
  **250 overlapping bars**: fewer is `flagged: short-overlap`, never a pass.
  A disagreeing ticker is written but `flagged:`. Ticker reuse is the live
  risk here: `SNDK` was SanDisk until 2016 and is a new listing since 2025.
  Bars before the reference file's first bar are dropped, and the manifest
  says so. Intraday files inherit their ticker's daily status.
- **`--mode update` never mixes adjustment bases, and it moves all three
  timeframes together.** With `Adjustment.ALL`, every new split or dividend
  rescales all older bars. A short overlap check misses that, because the
  shift is uniform and can be tiny. So `update` refetches each ticker's
  **full daily history** (one page per ticker, about 77 requests). It then
  compares every stored daily close with the fresh one. If any differs by
  more than 1e-6 relative, or a ratio steps like a split, the basis has
  changed. Then **all three timeframes of that ticker are refetched in full
  and replaced together**. Otherwise each timeframe appends the bars after
  its last one. No file ever holds two bases, and no ticker has timeframes
  on different bases.
- **A weekly cron on the VM** runs `--mode update` on Sunday, mirrored under
  `scripts/ops/` per the production-change rule.

### 3. Training reads it by default

- **One read seam**, `swingbot/core/marketdata/history_store.py`:
  `load(ticker, timeframe, session="rth")` returns a normalized frame or
  `None`, and `manifest(timeframe)` returns the manifest. `session="all"`
  returns extended hours for 15min. It has no network and no write path.
- **One switch.** A new config field `TRAINING_DATA_SOURCE` (`alpaca` |
  `yfinance`, default `alpaca`, section "Data Sources" in
  `swingbot/config.py`) sets the default. Every backtest and grid script
  that reads `data/backtest_cache/` today accepts `--data-source` to
  override it: `run_backtest_range.py`, `tune_strategy.py`, the `measure_*`
  scripts and `backtest_wf.py`. The plan's brief lists every one.
  **Rollback is one `.env` line:** `TRAINING_DATA_SOURCE=yfinance`.
- **The admin Tuning page** (`swingbot/admin/jobs.py:73-85,217` builds the
  `tune_strategy.py` argv from a whitelist) gains a `--data-source` choice,
  defaulting to the config value, and shows each result's source. Without
  it, the flip would silently change every admin-run grid.
- **No silent fallback, and a missing store is an error.** If the store or
  its manifest is absent (a fresh checkout, a worktree, CI), an `alpaca`
  run **stops with an error naming the missing path**. It never runs with
  zero tickers. With the manifest present, a ticker marked `skipped` or
  `flagged`, or with no file, is left out. Its name and reason are printed
  and recorded. A training run never mixes sources.
- **Provenance everywhere a result lands:** `data_source`, feed,
  adjustment, the manifest's top-level hash and the excluded tickers go
  into every result JSON. New rows of
  `swingbot/core/backtesting/validation_registry.json` (via
  `--emit-registry`, `run_backtest_range.py:480`) and of
  `docs/superpowers/results/preregistration-ledger.jsonl` gain a
  `data_source` field. Old rows have none; they mean `yfinance`. Readers
  treat a missing field that way and the rows are not rewritten
  (`schema-evolution.md`: an added field, no read-time upcasting of
  meaning beyond that one default).
- **Unchanged:** the Stage −2 idea screen keeps `data/backtest_cache_ext/`
  (point-in-time S&P 500, 2010–2019). Alpaca starts in 2016 and has no
  delisted names, so it cannot serve that screen. The live scan,
  `data_refresh`, the root `market_data/` cache and every alert stay as
  they are.

### 4. Pulling it to the dev machine

`scripts/ops/pull_history_store.sh` streams the VM store into this repo's
`data/market_data/` through `scripts/ops/ssh-hetzner.sh` (a `tar` over the
existing wrapper, never a raw `scp`), then checks every file against the
manifest hashes and prints the summary.

### 5. The re-baseline measurement

Switching the training data moves every number measured on yfinance. The
plan's last data task measures that once, reproducibly:

- **Frozen inputs.** Before any run, `data/backtest_cache/` is copied to
  `data/backtest_cache_snapshot_v162/` with a hash manifest, and the
  `yfinance` legs read that copy (`BACKTEST_CACHE_DIR`). The Alpaca legs read
  the store at a recorded manifest hash. Every leg runs on **the same ticker
  set**: the intersection of `ok` Alpaca tickers and cached yfinance
  tickers.
- **Three legs**, each with the current live config: (a) yfinance as today,
  (b) yfinance truncated to start 2016-01-01, (c) Alpaca. (a)→(b) isolates
  the shorter warm-up; (b)→(c) isolates the vendor (SIP tape, adjustment
  factors).
- **Two windows**: TRAIN 2020-01-01..2023-12-31, and the fold-train window
  2018-06-01..2022-12-31 that closed instruments used (v122, v127, v135,
  v139), where a 2016 start leaves only about 2.4 years of look-back.
- **Reported** in `docs/superpowers/results/`: trades, win rate, ExpR and
  per-ticker trade-count differences. Each ExpR and win-rate difference
  comes with its week-clustered bootstrap 95% interval
  (`week_cluster_bootstrap`), and its window and N in the same sentence.
  These numbers describe a data change. They are never quoted as a lift.

## Research discipline

The data change must not become a way round the methodology's one-shot rules
(`backtest-methodology.md` § Windows, § Closed pre-registrations, § Evidence,
registry and ledger):

- **A new data source does not reset a VALIDATION budget.** A component whose
  validation shot was spent on yfinance (RS_GATE, AVWAP, the v31 badges,
  every ledger row with a validation verdict) has spent it. 2024–2025 stays
  tainted for every selection decision. `--data-source` on `--validation`
  gives no component a second run.
- **Every closed pre-registration stays closed.** Re-measuring a closed
  component on Alpaca bars is the same hypothesis on a new dataset ("a better
  instrument is not a new hypothesis"), not a new mechanism. This includes
  v122, v127, v129, v135, v139 and v143.
- **§5 is not a decision.** If the Alpaca baseline comes out worse, the
  source stays Alpaca. There is no switch back to yfinance and no choosing a
  source per ticker or per strategy. Doing that would turn two datasets into
  a fork picked after the fact.
- **Each new pre-registration names its `data_source`** in its frozen block,
  before TRAIN is read.
- **The registry and the ledger keep the two populations apart** through
  the `data_source` field (§3). Badge tiers are scored per row as today, and
  a reader can tell which data scored them.

## Known differences the partner should expect

- **Shorter warm-up.** `backtest_cache` daily history goes back to 2000 or
  listing; Alpaca starts in 2016. That leaves four years before TRAIN and
  about 2.4 before the fold-train window. Multi-year S/R levels see less
  history. §5 leg (b) measures exactly this.
- **The SIP tape, not Yahoo's composite.** Volume and a few highs and lows
  differ slightly. Daily closes agree within the 0.5% identity tolerance.
- **Adjustment basis.** `Adjustment.ALL` and yfinance's `auto_adjust=True`
  both adjust for dividends, with slightly different factors. The difference
  is small and uniform per ticker.
- **Survivorship is unchanged.** Training already uses the current
  watchlist.

## Docs and tests this changes

- `known-traps.md` § Two OHLCV caches becomes three stores, with who writes
  and reads each. `architecture.md`, the `backtest_wf.py:87` docstring,
  `backtest-methodology.md` (§ Research discipline above, condensed) and
  `AGENTS.md` (the Codex mirror, same commit) are updated to match.
- `scripts/dev/select_tests.py:247` gains a `DATA_READERS` row for
  `data/market_data/` and the `history_store` fixtures. The new test
  directory joins one suite in `tests/suites.toml`.

## Out of scope

- Unadjusted bars, 5m/1m bars, and symbols beyond the watchlist.
- Any strategy that uses intraday bars. It needs its own `SCREEN-PASS` row
  first.
- Moving the live scan or `market_data/` onto Alpaca history.
- Retiring `data/backtest_cache/` (still the live bot's daily cache).

## Acceptance

1. The VM store holds 15min, hourly and daily files for every watchlist
   equity, starting 2016-01-04 or the listing date, ending within one session
   of the run. Every skip or flag is listed with its reason.
2. Row counts are sane: regular-hours 15min ≈ 26 bars a session, hourly 7.
   Each gap is explained by a half-day or holiday, and a check script in the
   plan does this.
3. The index round-trip test passes across both DST changes.
4. `--mode update` on an unchanged day writes nothing. A simulated dividend
   rescale, even one below 0.01%, triggers a lockstep refetch of all three
   timeframes, never a mixed file.
5. `run_backtest_range.py --train` with no flag reads the Alpaca store and
   stamps provenance. With no store present it errors. With
   `--data-source yfinance` against the v162 snapshot it reproduces the §5
   leg (a) numbers.
6. The admin Tuning page offers the source and shows it on each result.
7. The §5 three-leg, two-window baseline is committed under
   `docs/superpowers/results/`.
8. The cron is installed on the VM and mirrored in `scripts/ops/`. The store
   is pulled to this machine and verified against its hashes.

## Panel review

Spec review, 2026-10-15, on 963254d0.

- staff-engineer: [BLOCKING] admin Tuning page would silently flip with the default, with no source choice and no rollback -- applied (§3 admin choice, `TRAINING_DATA_SOURCE` one-line rollback)
- staff-engineer: missing manifest in a worktree or CI would give an empty run instead of an error -- applied (§3 hard error)
- staff-engineer: backfill via `exec` in the CPU-capped bot container, sharing the rate budget with no hours window -- applied (§2 `compose run --rm`, outside hours, 120/min)
- staff-engineer: `_bars` has no paging or end control; the provider needs a named new method -- applied (§1 `history_bars`, yearly chunks)
- staff-engineer: identity check against the never-self-healing `market_data/daily` -- applied (§2 reference is `data/backtest_cache`)
- staff-engineer: docs still say "two caches"; no owner for `backtest_cache` -- applied (§ Docs and tests; § Out of scope says why it stays)
- staff-engineer: disk shared with PITR and dumps, no ceiling or growth figure -- applied (§2 disk guard, sizes measured in the plan)
- staff-engineer: no `DATA_READERS` row -- applied
- staff-engineer: warm-up reproducibility belongs to quant-engineer -- applied (deferred to that role; see below)
- quant-engineer: [BLOCKING] §5 not reproducible over a live-refreshed cache; mixed universes -- applied (frozen snapshot with hashes, intersection ticker set; "exactly" now scoped to the snapshot)
- quant-engineer: [BLOCKING] a 5-session 0.01% overlap misses a uniform dividend rescale -- applied (full daily history compared at 1e-6 every update). The finding's example arithmetic was off (0.05–0.3% is above 0.01%), but the gap is real for small or rare dividends.
- quant-engineer: [BLOCKING] index and timezone convention unstated; UTC vs NY vs naive -- applied (§1 naive NY wall-clock, DST round-trip test)
- quant-engineer: last hourly bar is a half-hour -- applied (noted in §1)
- quant-engineer: intraday must refetch in lockstep with daily -- applied (§2)
- quant-engineer: warm-up and vendor effects are confounded -- applied (§5 leg b)
- quant-engineer: provenance needs feed, adjustment and a content hash -- applied
- quant-engineer: identity check needs a minimum overlap and NaN-safety -- applied (250 bars)
- quant-researcher: [BLOCKING] new source must not reset VALIDATION budgets -- applied (§ Research discipline)
- quant-researcher: [BLOCKING] closed pre-registrations stay closed on new data -- applied
- quant-researcher: §5 outcome must not change the source choice; pre-registrations name the source up front -- applied
- quant-researcher: §5 differences need week-clustered intervals -- applied
- quant-researcher: registry rows carry no source -- applied (`data_source` on new rows)
- quant-researcher: ledger rows carry no source -- applied
- quant-researcher: fold-train window gets about 2.4 years of look-back -- applied (§5 second window)
