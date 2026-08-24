Version: ui 1.8.4 · bot 1.4.3
Bump: bot patch
Edge: none (integrity)

# Batch the scan's yfinance fetches

## Problem

The session scan (`swingbot/core/scanning/engine.py`) takes 7+ minutes for a
78-ticker watchlist and grows with watchlist size, against a 5-minute scan
interval — scans are starting to overlap their own cadence. Reading the
pipeline and confirming live on production (Hetzner, 2026-08-24) narrowed this
to two independent sources of per-ticker network round trips, both un-batched:

1. **Crawl phase, cold tickers.** `_crawl_latest_data()` serves warm tickers
   from `market_data/daily/*.csv` at no network cost (v47), but every cache
   miss goes through `_fetch_one_ticker()` — one `yf.download()` call per
   cold ticker. On a fresh cache (redeploy, or a watchlist add) this is
   effectively every ticker.
2. **Analyze phase, every ticker, every scan.** `_scan_one()` calls
   `get_current_price(ticker)` for **every** ticker on **every** scan, to get
   a live (incl. pre/post-market) price for SL/TP monitoring and new-plan
   pricing. Its 15s in-memory cache never helps here — the scan interval is
   5 minutes — so this is a guaranteed fresh network call per ticker per
   scan, up to two HTTP requests each (a 1-minute-history call, then a
   `fast_info` fallback).

Confirmed live on production the same day: the container's first scan after a
14:16 redeploy hit 63 cold tickers and **never returned** — 2h20m+ later it
was still running, at ~1% CPU (not computing, blocked on I/O), with 67+
leaked sockets in `CLOSE_WAIT` to Yahoo's edge. `d251cef` (committed by a
concurrent session mid-investigation, same incident) already put a hard
wall-clock budget (`COLD_FETCH_TIMEOUT_SECONDS`, 180s) around the cold-fetch
process pool so a stuck ticker can no longer wedge the scan forever — **that
fix is real and stays**, but it only bounds the pathological case. It does
not reduce the ~63 sequential round trips in the common case, and it does not
touch the live-price fetch at all, which has zero deadline protection today
and runs on every single scan regardless of cache state. That combination —
not "no timeout anywhere" (yfinance's own defaults are 10–30s; not "no
session reuse" (yfinance 0.2.66 already holds one singleton `curl_cffi`
session process-wide) — is what makes this scale with ticker count and
occasionally go pathological under load.

## Goals

- Cut scan time toward ~2 minutes for the current 78-ticker watchlist, and
  keep it near-flat as the watchlist grows (round trips become O(chunks), not
  O(tickers)).
- Give the live-price fetch the same wall-clock deadline protection the cold
  OHLCV fetch just got, instead of relying solely on yfinance's own
  not-fully-reliable per-call timeout (per `d251cef`'s finding: a stalled DNS
  lookup or fork-inherited lock can wedge a worker with no exception and no
  CPU use, past the nominal timeout).
- Zero change to trading logic — same prices, same signals, same plans;
  purely how the numbers get fetched.

## Non-goals

- The `market_data_refresh` background loop, already budgeted (`5f56475`).
- The unrelated `COVERAGE REGRESSION` hourly-data-truncation errors observed
  in production logs during this investigation (`EA/hourly`, `AMD/hourly`,
  ~50 others) — a real bug, but in the refresh loop's merge logic, not the
  scan's fetch path. Flagging it here for a separate investigation; out of
  scope for this spec.
- `get_current_price()` itself and its callers outside the scan hot path
  (`get_all_unrealized_pnl()`, the admin dashboard's P&L call) — low
  frequency, small N (open trades only), not part of the 5-minute cadence.
  Stays exactly as-is; this spec adds batch functions alongside it.

## Design

### New batch fetch functions (`swingbot/core/marketdata/data.py`)

- **`get_daily_data_batch(tickers: list[str], period: str) -> dict[str, DataFrame]`**
  — one `yf.download(tickers=" ".join(tickers), period=period, interval="1d",
  group_by="ticker", auto_adjust=True, progress=False)` call. A ticker whose
  slice comes back empty/all-NaN is simply absent from the returned dict —
  identical contract to today's per-ticker `get_daily_data()` failure case.
- **`get_current_price_batch(tickers: list[str]) -> dict[str, float]`** — one
  `yf.download(tickers=" ".join(tickers), period="1d", interval="1m",
  group_by="ticker", prepost=True, progress=False)` call, returning the last
  non-NaN close per ticker. Same absent-on-failure contract.

Both verified working against live Yahoo data during this investigation: 15
tickers × 2y daily in 1.34s, 10 tickers × 1-day/1-minute in 16s, in one call
each — replacing what is today 15 or 10 separate blocking calls.

`candidate_symbols()` alias resolution (for tickers Yahoo lists under a
different symbol) is **not** applied inside the batch call — batching only
covers the literal watchlist tickers. Any ticker absent from a batch result
falls back to the existing single-ticker `get_daily_data()` /
`get_current_price()` path (which already does candidate-symbol resolution),
run for just that small remainder. In steady state this remainder is empty or
near-empty, so it costs nothing; it exists so alias resolution isn't silently
dropped for the rare ticker that needs it.

### Bounded execution, generalized from `d251cef`

`_fetch_cold_frames()` today submits one `ProcessPoolExecutor` future **per
cold ticker** and waits on all of them with a wall-clock budget
(`COLD_FETCH_TIMEOUT_SECONDS`), killing whatever hasn't returned. This spec
factors that wait-budget-and-kill logic out of `_fetch_cold_frames()` into a
small reusable helper:

```python
def _run_bounded(fn, args: tuple, timeout_seconds: int, label: str):
    """Runs fn(*args) in a single-process pool with a hard wall-clock
    budget. Returns fn's result, or None if the budget is exceeded (the
    worker process is killed outright -- shutdown(wait=False) alone only
    cancels futures that never started, per d251cef). A process, not a
    thread, because a stalled DNS lookup or fork-inherited lock can wedge a
    worker with no exception and no CPU use, past whatever timeout the
    called function itself was given -- only a killed process is a reliable
    ceiling."""
```

Both new batch calls route through this helper instead of each growing their
own copy of the wait/kill logic. `_fetch_cold_frames()` is rewritten to
submit **one future per chunk** (calling `get_daily_data_batch`) instead of
one future per ticker — same safety mechanism, applied to O(chunks) units of
work instead of O(tickers).

### Crawl phase changes (`_crawl_latest_data`, `_sync_run_scan`)

1. Warm/cold split unchanged (cache-first, per ticker, no network).
2. Cold tickers, if any, are fetched via `_run_bounded(get_daily_data_batch,
   (chunk, period), COLD_FETCH_TIMEOUT_SECONDS)` — one call per chunk of
   `BATCH_FETCH_CHUNK_SIZE` tickers (default covers the full current
   watchlist in one chunk), chunks run sequentially (each is itself already
   a single yfinance call; no concurrent-`download()`-call safety issue to
   manage since nothing calls `download()` from two places at once).
3. Immediately after crawl resolves (still inside the crawl phase, preserving
   the "only the crawl phase touches yfinance" architecture invariant), the
   **whole watchlist** — not just cold tickers, since a warm daily-bar cache
   says nothing about today's live price — goes through
   `_run_bounded(get_current_price_batch, (chunk,), LIVE_PRICE_TIMEOUT_SECONDS)`,
   chunked the same way, producing a `{ticker: price}` dict
   (`live_prices`) passed down into the analyze phase.
4. A ticker absent from `live_prices` (chunk failed/timed out, or genuinely
   no data) falls back to today's daily close from `fresh_data` — same
   fallback `_scan_one` already does today (`current_price = live if (live
   and live > 0) else float(df["Close"].iloc[-1])`), just sourced from a
   dict lookup instead of a fresh network call.

### Analyze phase changes (`_scan_one`)

`live = get_current_price(ticker)` (line 1093) becomes `live =
live_prices.get(ticker)` — a dict lookup, zero network. `_scan_one` gains a
`live_prices: dict` parameter, threaded through from `_sync_run_scan`
alongside the existing `regime`/`rs_cache`/`spy_df`/`breadth` scan-wide
readings it already receives. This also fixes the module's own docstring
claim that the analyze phase "never touches yfinance" — after this change
it's actually true, not aspirational.

### Config changes

| Field | Change |
|---|---|
| `COLD_FETCH_TIMEOUT_SECONDS` | Kept, repurposed: now bounds one batched-chunk future instead of one per-ticker future. Default (180s) unchanged — it's a ceiling for the pathological case, not a tuning target. |
| `LIVE_PRICE_TIMEOUT_SECONDS` | New. Bounds the new batched live-price fetch the same way. Default 60s. |
| `BATCH_FETCH_CHUNK_SIZE` | New. Tickers per batched `yf.download()` call, for both cold-OHLCV and live-price. Default 100 (covers today's 78-ticker watchlist in one chunk with headroom). |
| `COLD_FETCH_PROCESS_THRESHOLD` | **Removed.** Existed to decide "is spawning a process worth it for this many tickers" when each ticker was its own future; with batching, one process handles any cold count uniformly, so the branch it guarded no longer exists. |
| `FETCH_WORKERS` | **Unchanged** — still consumed by `backtest_scenarios.py`'s offline replay pool, unrelated to this spec. `_resolve_workers()` stays for that caller; the scan path no longer needs it once cold fetches are one future per chunk rather than one per ticker. |

`_fetch_one_ticker()` and the plain sequential (non-pooled) branch of
`_fetch_cold_frames()` are deleted — every cold fetch now goes through the
chunked/bounded path uniformly, regardless of count.

## Error handling

- A chunk that times out or raises: every ticker in that chunk is treated as
  a failed fetch for this scan — identical to today's single-ticker failure
  contract (`df=None` / absent from `fresh_data`, absent from `live_prices`
  with fallback to daily close). One bad chunk never aborts the rest of the
  crawl; remaining chunks still run.
- A ticker present in the batch response but with only NaN rows (delisted,
  bad symbol, market holiday for that specific listing) is treated the same
  as "absent" — falls through to the single-ticker alias-resolution
  fallback described above.
- No behavior change to `trade_log.update_open_trades` / `_check_near_close`
  / plan pricing: they still receive a `current_price` float exactly as
  before, just sourced differently upstream.

## Testing

- `get_daily_data_batch` / `get_current_price_batch`: mock `yf.download`'s
  multi-index (`group_by="ticker"`) response shape for (a) full success, (b)
  one ticker's slice all-NaN, (c) an empty DataFrame (total failure).
- `_run_bounded`: a fast-returning function returns its result normally; a
  function that never returns within the budget yields `None` and the
  process is confirmed killed (reuse the process-liveness assertion pattern
  from `tests/scanning/test_cold_fetch_pool.py`, generalized from
  per-ticker to per-chunk).
- `_crawl_latest_data`: chunking splits an over-`BATCH_FETCH_CHUNK_SIZE`
  cold list into multiple bounded calls; a chunk failure doesn't drop the
  other chunks' results.
- `_scan_one`: given a `live_prices` dict, uses the dict value when present
  and falls back to the daily close when the ticker is absent — no network
  call reachable from this function anymore (assert `get_current_price` is
  not called from within `_scan_one`'s code path).
- Full-suite run (`python scripts/dev/testrun.py full`) once, as this plan's
  final task, per `docs/claude/document-conventions.md`.

## Parallelisation

Sequential throughout: `data.py`'s two new batch functions and `_run_bounded`
must land before `engine.py`'s crawl/analyze integration can consume them,
and `_scan_one`'s `live_prices` parameter is a contract change every caller
of `_scan_one` must adopt in the same step (an intermediate state where some
callers pass it and some don't is not a valid checkpoint). Every task also
touches one of two files (`data.py`, `engine.py`), both edited by more than
one task, so there is no genuinely disjoint-file group to parallelize here.
