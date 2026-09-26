# v106 — Alpaca as a live-path market-data provider, yfinance as fallback

**Version:** ui 1.21.0 · bot 1.10.3
**Bump:** bot minor, ui minor
**Edge:** none (integrity)
**Plan:** `docs/superpowers/plans/2026-09-26-v106-alpaca-data-provider.md`

Spec 1 of 2. Spec 2 (mirroring paper trades onto an Alpaca *paper* account for
realistic fills) is a separate, later brainstorm and must reconcile with the
blocked v81 execution-feed branch (`2026-09-10-v81-execution-feed`) rather than
duplicate it. Nothing here places an order.

## Why

Every bar and quote the bot sees comes from yfinance: unofficial, rate-limited,
and slow cold — a single cold `get_daily_data_batch` ticker measured **18.5 s**
(the open blocker in memory, 2026-09-22), with blast radius over the scanner,
chart rendering and the admin watchlist. Alpaca's Market Data API is official,
batched, and fast. The goals, all three agreed in the brainstorm:

1. **Reliability + speed** — no multi-second cold fetches on US names, fewer
   fetch failures.
2. **Data quality** — a parity report that says, with numbers, where the two
   sources disagree.
3. **Groundwork for execution** — spec 2's orders price off the same feed the
   signals saw.

`Edge: none (integrity)` — this claims no ExpR lift. Removing stale/failed
data from the live path is integrity work; any live-book change during the
soak is **not** attributed to it.

## Decisions (from the brainstorm)

| Decision | Choice |
|---|---|
| Scope | **Live path only.** Scanner, live prices, charts, watchlist, `get_intraday`. The backtest CSV cache and `scripts/data/fetch_backtest_data.py` stay yfinance, so every closed pre-registration stays comparable. |
| Plan tier | **Alpaca Free (Basic).** SIP for anything ≥ 15 min old; IEX real-time for the last-trade price only. |
| Client | **`alpaca-py`** (`StockHistoricalDataClient`) — the same package spec 2 will use for orders. |
| Shape | **Provider seam + router** (approach A), yfinance as per-symbol fallback, `.env` kill switch. |

## Architecture

New package `swingbot/core/marketdata/providers/`:

- **`base.py`** — `is_alpaca_eligible(symbol) -> bool` and the **frame
  contract** helpers.
  - Eligible = `asset_class.classify(sym)` in `{"equity", "etf"}` **and** the
    symbol has no exchange suffix (`.DE`, `.AS`, `.L`, …). US class shares are
    eligible under both spellings (`BRK.B`/`BRK-B` → Alpaca `BRK.B`).
  - Not eligible: indices (`^`), FX (`=X`), futures (`=F`), crypto (`-USD`), and
    anything that needs `candidate_symbols` aliasing.
  - `to_yf_daily(df)` turns Alpaca's `(symbol, timestamp)` UTC frame into
    exactly what `get_daily_data_batch` returns today: a tz-naive
    `DatetimeIndex` at midnight (ET session date), columns
    `Open/High/Low/Close/Volume` as float.
  - `to_yf_hourly(df30)` turns Alpaca **30-minute** bars into Yahoo-shaped 1h
    bars. Regular session only, rebuilt on 09:30 boundaries (09:30, 10:30, …,
    15:30), tz-aware `America/New_York`.
    - **Why 30-minute bars:** Alpaca 1h bars align to the clock hour (09:00),
      Yahoo's to 09:30. Merging hour-aligned bars into the existing
      `market_data/hourly/` CSV would interleave two bar grids.
- **`alpaca_provider.py`** — `AlpacaProvider` wraps one lazily built
  `StockHistoricalDataClient`:
  - `daily_bars(symbols, period)` — `StockBarsRequest(TimeFrame.Day,
    feed=DataFeed.SIP, adjustment=Adjustment.ALL, end=now−16 min)`. One request
    per call; alpaca-py pages internally. `Adjustment.ALL` matches yfinance
    `auto_adjust=True` (split + dividend).
  - `intraday_bars(symbol, interval="1h")` — 30-minute SIP bars, 700 days, then
    `to_yf_hourly`. Only `"1h"` is supported; any other interval is a miss.
  - `latest_prices(symbols)` — `StockSnapshotRequest(feed=DataFeed.IEX)`, price
    = `latest_trade.price`. **During the regular session, a trade older than
    `ALPACA_MAX_TRADE_AGE_SECONDS` (default 300) is a miss**, not a price: IEX
    carries ~2–3% of volume, and a lagging IEX print must never reach a trading
    caller (`allow_stale=False`). **IEX volume is never read.**
  - `period` mapping: `1d/5d/1mo/3mo/6mo/1y/2y/5y/10y` → calendar offsets;
    `max` → 2016-01-01 (Alpaca SIP history floor).
- **`router.py`** — the only module `data.py`/`data_store.py` call:
  - `daily_bars(tickers, period, yf_fetch)`, `latest_prices(tickers, yf_fetch)`,
    `intraday_bars(symbol, interval, yf_fetch)`. `yf_fetch` is the existing
    yfinance code path, passed as a callable. The router imports no yfinance
    code, so the fallback is exactly today's behaviour.
  - Splits the tickers by `is_alpaca_eligible` when `ALPACA_ENABLED` is on and
    the breaker is closed. Eligible tickers go to Alpaca, all others to
    `yf_fetch`. **Per-symbol fallback:** any eligible ticker Alpaca misses
    (exception, timeout, empty) is retried in one `yf_fetch` call.
  - Tags every returned frame with `frame.attrs["source"]` (`alpaca` /
    `yfinance` / `yfinance-fallback`) and records `last_source(symbol)` for
    price calls.
  - **Timeout:** each Alpaca call runs under `ALPACA_TIMEOUT_SECONDS` (default
    5) in a worker thread. On a timeout the result is abandoned and the call
    falls back.
  - **Circuit breaker:** `ALPACA_BREAKER_FAILURES` (default 3) consecutive
    whole-call failures open it for `ALPACA_BREAKER_COOLDOWN_SECONDS`
    (default 300). A 401/403 opens it until the next config reload. One WARNING
    per state change, never per call.
  - **Token bucket:** a 150 req/min cap (under Free's 200). An exhausted bucket
    is a miss, and the call falls back.
  - `stats()` returns counters `{alpaca, yfinance, fallback, failures,
    breaker_open}`.
  - Config is read **at call time** (`config.ALPACA_*`). The client is cached
    keyed on `(key_id, secret)`, so a SIGHUP that changes the keys rebuilds the
    client and clears the auth latch on the next call. No reload hook is
    needed, which matters because the admin container has no
    `bot_core.on_config_reload`. `reset()` exists for tests.
  - **Process note:** scan fetches run in a *spawned* child
    (`scanning/fetch.py:_run_bounded`), so the breaker state and counters there
    are per-call. The parent counts sources from the returned frames'
    `attrs["source"]` (T8 proves attrs survive the pickle round trip; if they
    don't, the child returns `(frames, sources)`).

**Where the router is called.** It intercepts the network call inside each
existing function; every public signature stays the same:

| Function | Change |
|---|---|
| `data.get_daily_data_batch` | Download + slicing extracted into `_yf_daily_batch(tickers, period)`; the body becomes `router.daily_bars(tickers, period, _yf_daily_batch)`. |
| `data.get_daily_data` | An eligible ticker tries `router.daily_bars([t], …)` first; on a miss, the existing `candidate_symbols` loop runs unchanged. |
| `data.get_current_price_batch` | The 1-minute `yf_safe.download` step extracted into `_yf_batch_prices(tickers)`; replaced by `router.latest_prices(tickers, _yf_batch_prices)`. **All caches and TTLs (`_last_good_batch_price`, 15 s / 900 s) are untouched.** This lowers the function's complexity from D(23). |
| `data.get_current_price_detail` | An eligible ticker tries `router.latest_prices([t], …)` first. A hit gives `PriceQuote(price, stale=False)` and goes into `_price_cache` exactly like the primary yfinance source. A miss runs the existing two-source loop. |
| `data_store.get_intraday` | `_default_fetch` tries `router.intraday_bars` first. `merge_adjusted` / `_align_tz` are unchanged. |

**Explicitly untouched (still yfinance):**
- `data_store.fetch_interval_data` and the `market_data_refresh` loop. They use
  `period="max"`, and Alpaca's 2016 floor would silently shorten chart history.
- The backtest cache and every `scripts/data/*` fetcher.
- Earnings (`market/events.py`), company name and currency lookups, option
  snapshots.

**Config** (`swingbot/config.py`, "Data Sources" section, all hot-reloadable):
- `ALPACA_ENABLED` (bool, default **false**)
- `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` (password, sensitive)
- `ALPACA_DATA_FEED_LIVE` (default `iex`; set to `sip` on a paid plan)
- `ALPACA_TIMEOUT_SECONDS`, `ALPACA_MAX_TRADE_AGE_SECONDS`,
  `ALPACA_BREAKER_FAILURES`, `ALPACA_BREAKER_COOLDOWN_SECONDS`

`.env.example` gets the commented block. `requirements.txt` pins `alpaca-py`.
The Dockerfile already installs from `requirements.txt`.

## Observability

- **Scan telemetry.** The `data/scan_telemetry.jsonl` row (built at
  `scan_run.py` ~963) gains `data_sources: {alpaca, yfinance,
  yfinance_fallback}`, counted from the cold-frame fetch.
- **Admin.** `admin/api_v1/risk.py:_scan_health` adds a `data_sources` summary:
  - enabled / feed / breaker state, plus the fallback rate over the last 20
    scans;
  - the Risk workspace (`frontend/src/app/workspaces/risk/risk.ts`) renders it
    next to scan health;
  - watchlist rows gain `price_source` (from `router.last_source`), shown as a
    small badge beside the existing `current_price_stale` indicator.
  - An instrument that hides where its number came from has a correctness bug.
- **Parity report.** `scripts/reports/provider_parity_report.py` (read-only,
  network):
  - samples the eligible watchlist and compares Alpaca SIP vs yfinance daily
    bars over the last 60 sessions;
  - measures close difference in bps (median / p95 / max), days missing on
    either side, split/dividend mismatches (difference > 50 bps on one date
    across a known corporate action), and the volume ratio (SIP only);
  - also reports the IEX-last-trade vs yfinance live-price difference at run
    time;
  - optional `--json` output.

## Error handling

The rules are per symbol, never per batch. Degraded is always yfinance, never
nothing. Every Alpaca failure mode (auth, 5xx, 429, timeout, empty frame,
unknown symbol, stale IEX trade, bucket exhausted) is a **miss** that goes to
the per-symbol fallback. A trading caller never gets a worse answer than today:
at worst it gets today's yfinance answer after one bounded Alpaca attempt.

## Testing

No network anywhere in the suite. `StockHistoricalDataClient` is faked.

- **Frame contract:** recorded Alpaca fixtures through `to_yf_daily` /
  `to_yf_hourly` must equal yfinance-shaped fixtures in columns, dtypes, index
  type and tz. This is extended from the existing
  `tests/marketdata/test_frame_equivalence.py` pattern.
- **Router:** eligibility split, per-symbol fallback, timeout, breaker
  opening, cool-down and auth latch, token bucket, source tags, `reset()`.
- **Kill switch characterization:** with `ALPACA_ENABLED=false`, every wrapped
  function returns exactly what the pre-change code returned for the same
  faked yfinance input (the existing `test_data.py` /
  `test_current_price_staleness.py` fakes stay valid unchanged).
- **Stale-trade guard:** a regular-session IEX trade older than the max age
  never reaches an `allow_stale=False` caller.
- **Pickle:** `attrs["source"]` survives a `_run_bounded` spawn round trip.

## Rollout and acceptance (pre-registered)

1. Merge with `ALPACA_ENABLED=false` and deploy to Hetzner. No observable
   change.
2. Add the keys to the production `.env`, mirror the placeholder names into
   `.env.example`, and commit. Run the parity report on production.
3. Set `ALPACA_ENABLED=true` and send SIGHUP. Soak for **5 trading days**;
   compare against the preceding 5 from `scan_telemetry.jsonl`.
4. **Pass requires all of:**
   - (a) p95 cold `get_daily_data_batch` wall time **< 3 s**
   - (b) Alpaca fallback rate **< 5 %** of eligible symbol-fetches
   - (c) scan fetch-failure rate (`errors` + `data_skips` per ticker) **no
     worse** than the baseline window
   - (d) parity median close difference **≤ 5 bps**, and every
     split/dividend mismatch explained in the write-up
5. **Any failed clause:** switch `ALPACA_ENABLED` back to false, write up the
   failure, and record it. Thresholds are not tuned after the fact.

## Out of scope

- The backtest cache and any backtest re-run.
- Websocket streaming (a possible v2 if a paid plan ever happens).
- Alpaca news and fundamentals, crypto via Alpaca.
- Spec 2 (the execution mirror).

## Changes to the approved design

Recorded here for the spec review:

- **No startup warm step.** `get_daily_data_batch` has no cache to warm; the
  18.5 s was yfinance latency itself, which Alpaca's batched call removes
  directly.
- **The yfinance code is not moved into a `yfinance_provider.py`.** It stays in
  place as the injected `yf_fetch` callable. Same behaviour, far less churn.
- **30-minute → 1h resampling** for `get_intraday` (grid alignment, above).
- **The stale IEX-trade guard** was added once the survey showed
  `allow_stale=False` trading callers read the same price path.

## Parallelisation

- **Sequential:**
  - T1 (dependency + config) comes before everything.
  - T2 (`base.py`) comes before T3/T4.
  - T5 (kill-switch characterization tests, pinned against today's code)
    comes before T6.
  - T6 comes after T3–T5 (it wires the router into `data.py`).
  - T10 (frontend) comes after T9 (it consumes the new `data_sources` /
    `price_source` fields).
- **Group A (parallel after T2):**
  - T3 (`alpaca_provider.py`) and T4 (`router.py`) touch disjoint files. T4
    depends only on T2's contract and fakes the provider.
- T12 (full suite) after all code tasks; T13 (production rollout + soak) and
  T14 (close-out) after T12, in that order.
- **Group B (parallel after T6):**
  - T7 (`data_store.get_intraday`), T8 (scan telemetry, `scan_run.py`), and
    T11 (parity report script) touch disjoint files, with no shared new
    symbols beyond T4's already-landed router.
  - T9 (admin API) also belongs to this group; T10 waits on it.
