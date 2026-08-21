# v47 — Scan throughput for a growing watchlist

Version: ui 1.8.0 · bot 1.3.2
Bump: `bot patch` · `ui patch`

`bot patch` and not minor: the bot does exactly what it did before, faster. Nobody
"has to look at it anew" — the alerts, the horizons and the plans are unchanged.
`ui patch` because three new `Field` entries appear as new rows on the admin
Settings page (a new control is a patch, per `working-conventions.md`).

## Problem

The watchlist is 78 tickers today and is heading toward 300–500. Three separate
things break at that scale, and only one of them is what "scanning all horizons
takes too long" sounds like from the outside.

**1. The live scan re-downloads the entire history of every ticker, every tick.**
`_crawl_latest_data()` (`swingbot/core/scanning/engine.py:614`) calls
`get_daily_data(ticker, period=config.DEFAULT_HISTORY_PERIOD)` per ticker.
`DEFAULT_HISTORY_PERIOD` defaults to `10y` (`swingbot/config.py:297`) and
`get_daily_data()` (`swingbot/core/marketdata/data.py:15`) goes straight to
`yf.download(...)` with **no cache check of any kind**. At the default
`SCAN_INTERVAL_MINUTES` of 5 (`swingbot/config.py:124`) that is ~78 full
ten-year downloads per ticker per session day. At 500 tickers it is 39,000
downloads a day for data whose only new content is one daily bar.

**2. That crawl is deliberately sequential, and for a good reason.** It used to
run through a `ThreadPoolExecutor` and was reverted: the pinned yfinance 0.2.66
builds `download()` on a shared, non-reentrant module global (`_DFS`), and
concurrent calls let two tickers' downloads clobber each other mid-flight. Two
real watchlist tickers scanned seconds apart were once logged as open trades
with byte-identical entry/stop/target/confidence values — one ticker's price
data attributed to the other. The upstream fix ("Make yf.download() reentrant by
removing shared module globals") landed only in yfinance 1.4.0. So more threads
is not available as an answer here, and correctness is why.

**3. Horizons are already free — the intuition in the request is wrong.** All ten
horizons for a ticker reuse the one frame the crawl fetched: `_scan_one()`
(`engine.py:830`) loops `horizons_to_scan` in-process against a single `df`, and
that analysis already runs through a bounded thread pool (`map_tickers()`,
`engine.py:805`, `SCAN_WORKERS` default 4). Adding horizons costs CPU, not
network. **The network crawl is the bottleneck, not the horizon count.**

A fourth, smaller one: the scan makes up to ~12 further sequential fetches
outside the watchlist crawl — the regime benchmark (`engine.py:1267`) and the
distinct SPDR sector ETFs (`_fetch_frames`, `engine.py:1289`).

Separately, the offline path has its own problem: `run_scenario_backtest()`
(`swingbot/core/backtesting/backtest_scenarios.py:145`) walks
`for ticker: for horizon:` strictly sequentially at ~30s per ticker-horizon. At
500 tickers × 10 horizons that is a run measured in days.

**The machinery to fix (1) already exists and is already running.**
`marketdata/data_store.py` + `marketdata/data_refresh.py` maintain
`market_data/daily/{TICKER}.csv` incrementally and staleness-gated, driven by the
`market_data_refresh` task loop (`swingbot/commands/scanning.py:1311`), which is
on by default (`MARKET_DATA_AUTO_REFRESH`) and already scoped to exactly
`load_watchlist()` (`commands/scanning.py:1331`). The live scan simply never
reads it. That cache was built for the edge-engine/backtest side and never wired
into the bot's own crawl.

## Goals

- Steady-state live scan makes **≈0 network calls for a warm ticker**.
- A cold or bulk-added set of tickers is fetched concurrently without
  reintroducing the cross-ticker corruption bug.
- Offline scenario backtests use all available cores.
- **No new container, no new deployable, no yfinance version bump.**

## Non-goals

- **Upgrading yfinance past 1.4.0.** Considered and deferred: it would re-enable
  thread-based concurrency, but it is a major-version jump requiring real
  re-verification, and Component 2 gets concurrency without it. Revisit only if
  the process-pool overhead proves unacceptable.
- A separate market-data service/container. Considered and rejected: there is one
  consumer topology (bot + admin on a shared volume) and the in-process loop
  already covers it.
- Changing what the scan computes. Every horizon, gate, and plan stays as-is.
  This is a pure throughput change and must be observably output-identical.

## Component 1 — Cache-first crawl

`_crawl_latest_data()` gains a cache lookup ahead of the network.

Per ticker, in order:

1. **Fresh cache hit** — `data_refresh.is_stale(ticker, "daily", max_age_hours=config.SCAN_CACHE_MAX_AGE_HOURS)` is `False`
   → `data_store.load_from_disk(ticker, "daily")`, use that frame, **no network**.
2. **Miss / stale / unreadable** → the ticker goes onto a `cold` list. It is
   **not** fetched inline.
3. After the loop, the `cold` list is fetched by Component 2 and merged into the
   same `LRUFrames` (`engine.py:454`) the sequential path already fills.

`is_stale()` (`data_refresh.py:79`) is reused rather than reinvented: it already
handles "file missing" and takes an explicit `max_age_hours` override, so the
scan's freshness bar is independent of the background loop's own 12h daily
refetch cadence.

**The frames are equivalent, and this is the load-bearing claim of the whole
design.** `fetch_interval_data(ticker, "daily")` (`data_store.py:159`) resolves
symbols through the *same* `candidate_symbols(ticker)` helper as
`get_daily_data()`, uses the same `auto_adjust=True`, and for daily
(`max_days: None`) requests `period="max"` — a strict **superset** of the 10y
`get_daily_data()` asks for. Same source, same adjustment, more history.

**But the CSV round-trip is a real risk and must be tested, not assumed.**
`load_from_disk()` is `pd.read_csv(path, index_col=0, parse_dates=True)`, and a
frame that has been to disk and back can differ from a live download in dtype
(`Volume` as `int64` vs `float64`) and in index tz-awareness — `_align_tz()`
(`data_refresh.py:102`) exists precisely because "a cached CSV can round-trip
either way". Downstream, `market_context.attach()`, `refresh_rs_cache()` and
every indicator in `_scan_one` consume these frames. A normalization helper on
the load path (column set, dtypes, tz-naive index, sorted unique index) is part
of this component, not an afterthought.

**Cache-miss safety.** A ticker that is neither cached nor successfully fetched
is simply absent from the result — today's exact contract
(`fresh_data.get(ticker)` → `None` → treated as "no data this ticker this scan").
No new failure mode is introduced. Component 1 must not change the semantics of
the existing `is_stop_requested()` per-ticker checkpoint or the `ScanProgress`
counters.

Same treatment for the regime benchmark and sector ETFs (`_fetch_frames`), which
are the same fetch shape against a small fixed symbol list.

## Component 2 — Cold-ticker fetch, with a process-pool fallback

Given the `cold` list from Component 1:

- `len(cold) <= config.COLD_FETCH_PROCESS_THRESHOLD` → **fetch sequentially, via
  today's exact code path, unchanged.** This is the common case (one or two
  tickers the background loop has not caught up on yet) and it deliberately
  carries zero new risk surface.
- `len(cold) > threshold` → fan out across a `ProcessPoolExecutor` sized by
  `config.FETCH_WORKERS`, one ticker per task.

**Why processes and not threads.** The bug in problem (2) is a *shared module
global* inside yfinance. Separate processes have separate interpreters and
separate memory, so `_DFS` is not shared and cannot be clobbered across workers.
This buys concurrency without touching the version pin. Workers return plain
`(ticker, DataFrame | None)` pairs — picklable, no shared mutable state, no
locking — and the parent merges them.

**Sizing.** The deploy target is a small 2–4 core box. `FETCH_WORKERS` defaults
to `0`, meaning auto — `max(1, os.cpu_count() - 1)` resolved at the call site —
and the work is network-bound anyway so oversubscribing buys nothing. It is a
config `Field` so it is tunable per-deploy without a code change, like
`SCAN_WORKERS` already is.

**Error isolation matches `map_tickers()`:** one worker raising is logged and
becomes `None` for that ticker; it never aborts the batch.

**Interaction with the background loop.** This path is a *fallback*, not the
primary. In steady state `market_data_refresh` keeps the cache warm and `cold` is
empty or tiny. The process pool exists for two situations: first boot before the
refresh loop has ever run, and a bulk watchlist addition.

## Component 3 — Parallel scenario replay

`run_scenario_backtest()`'s nested loop becomes a worker-pool map over
**tickers**, each task replaying all horizons for its own frame. Every unit is
already fully independent: it reads `frames[ticker]`, calls
`replay_scenarios(ticker, df, hk, gates=gates)` and `simulate_exit(...)`, and
contributes only to its own result lists. Aggregation (`_aggregate`) happens
strictly after every task returns, so there is no shared mutable state mid-loop
to serialize around.

**Grouped per ticker, not per `(ticker, horizon)` pair.** The OHLCV frame is the
expensive thing to move across a process boundary (~2 MB for a ten-year daily
history); a per-pair split would pickle the same frame once per horizon — ten
times the IPC for parallelism a 2–4 core box cannot use anyway. At 300–500
tickers, per-ticker tasks already give far more units than cores.

This is CPU-bound work on local CSVs with **no network and no yfinance
involvement at all**, so it carries none of Component 2's constraints.

Reuses `FETCH_WORKERS`; backtests are offline and manual, so a second knob is not
worth the config surface.

Ordering: results are grouped per horizon and then aggregated, so worker
completion order cannot affect the output — but the plan must assert that,
because a changed aggregate here would silently invalidate the closed
pre-registrations in `docs/claude/backtest-methodology.md`.

**`run_backtest_range.py`'s own `for ticker in tickers:` loader loop
(`scripts/backtest/run_backtest_range.py:142`) stays sequential** — it is CSV
reads and cheap screens, not the ~30s/pair replay, and per-ticker `print(...,
flush=True)` progress output is required by `CLAUDE.md` for long runs.

## Config surface

Three new `Field` entries in `swingbot/config.py`, "Universe & Scanning":

| Field | Default | Meaning |
|---|---|---|
| `SCAN_CACHE_MAX_AGE_HOURS` | `6` | How old `market_data/daily/{T}.csv` may be before the scan treats the ticker as cold. Below `data_refresh`'s 12h daily window on purpose, so the scan's bar is its own. |
| `COLD_FETCH_PROCESS_THRESHOLD` | `10` | Cold-ticker count at or below which the fallback stays sequential. |
| `FETCH_WORKERS` | `0` | Process-pool size for the cold-fetch fallback and the scenario replay. **`0` means auto** — resolved at the call site to `max(1, os.cpu_count() - 1)`. A `Field` default is a string cast by `int()` (`config.py:705`), so a computed default cannot live in the schema; `0`-as-auto is the only honest way to express it. |

`.env.example` gains all three (there is a test asserting `.env.example` stays in
sync with the schema — see `tests/test_env_example_sync.py`).

## Testing

Baseline to hold: `1686 passed, 66 skipped, 0 failed`, and `0 xfailed`.

**Mandatory regression test — cross-ticker data mixing.** The failure this design
is routing around already happened in production and corrupted real trade
records, so it gets a test that targets it directly, not incidental coverage.
Push several distinguishable tickers through the Component 2 process-pool path
concurrently and assert each returned frame's content matches *that* ticker.
Achieved with a fetch stub that returns a ticker-identifiable frame (e.g. a close
series derived from the symbol), so the test asserts the routing rather than
Yahoo's data, needs no network, and would have caught the original bug.

Beyond that:

- **Frame equivalence** — a cached-CSV round-trip frame and a live-download frame
  produce the same columns, dtypes and index type, and `_scan_one` yields the
  same scenarios for both. This is what guards the load-bearing claim above.
- **Cache-first routing** — a warm ticker makes zero fetch calls (assert against a
  patched `get_daily_data`/`fetch_interval_data`); a stale one and a missing one
  both land on the `cold` list.
- **Threshold behaviour** — at/below `COLD_FETCH_PROCESS_THRESHOLD` the process
  pool is never constructed; above it, it is.
- **Error isolation** — one failing ticker yields `None` for itself and does not
  abort the batch, in both the sequential and pooled paths.
- **Scenario-replay output identity** — `run_scenario_backtest()` returns
  byte-identical aggregates parallel vs sequential on a fixture universe. This is
  the gate that protects the closed pre-registrations.
- **Existing contracts preserved** — `is_stop_requested()` still ends a crawl
  early, `ScanProgress.total`/`done` still count as they do today, `LRUFrames`
  eviction still applies.

New tests belong in `tests/scanning/` (crawl routing, threshold),
`tests/marketdata/` (frame equivalence) and `tests/backtesting/` (replay
identity), matching the existing layout.

## Parallelisation

- **Group 1 (parallel):** Component 3 (`backtest_scenarios.py` +
  `tests/backtesting/`) may proceed alongside Components 1–2. It shares no file
  with them and consumes no symbol they introduce, apart from the `FETCH_WORKERS`
  config `Field` — so it is parallel-safe **only once that Field exists**.
- **Sequential:** the config `Field` additions land first (Components 1, 2 and 3
  all read them, and all three would otherwise edit `swingbot/config.py`
  concurrently — this working tree is shared, so that is an overwrite, not a
  merge). Component 1 before Component 2: Component 2 consumes the `cold` list
  Component 1 produces, and both edit
  `swingbot/core/scanning/engine.py`. The cross-ticker regression test comes
  after Component 2, since it asserts against the pooled path that task
  introduces.

## Success criteria

1. A warm scan of the current 78-ticker watchlist issues **zero** OHLCV network
   calls for tickers whose cache is fresh.
2. A cold bulk add of >10 tickers fetches concurrently and every resulting frame
   belongs to its own ticker (the regression test above).
3. `run_scenario_backtest()` output is unchanged versus sequential on a fixture
   universe.
4. Full suite green at the baseline, `0 failed` and `0 xfailed`.
