# v171 Shared market-data fetch. Part 5: demand cuts and the tape (V171-23..V171-29)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V171-25:" -A 300 docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_5-demand-tape.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v171-shared-market-data-fetch-design.md`](../specs/2026-10-16-v171-shared-market-data-fetch-design.md) (this part: D1 "is the only door" and the guard, D2 admin rules (Dashboard 15 s, other pages 60 s, reload means fresh, navigation means reuse, no new spinners), the earnings and metadata rows of the D2 table, D6 tier 4-5, D7 whole, D8 whole)
**Index:** [`2026-10-16-v171-shared-market-data-fetch_0-index.md`](2026-10-16-v171-shared-market-data-fetch_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v171-shared-market-data-fetch` (created in V171-1). Never `cd`; use `git -C $WT` and `python $WT/scripts/dev/testrun.py file <test>`. All file paths below are relative to `$WT`. After every task run `git -C $R status --short` and confirm the main tree is clean.

**Order.** V171-23 needs V171-6 and V171-8; V171-24 needs V171-9 (same `data.py`) and V171-11 (same `data_store.py`); V171-25 needs V171-9; V171-26 needs V171-25 and V171-12 (`daily_delta.read_daily`, `BASIS_YF`) and V171-23 (the earnings warm-up); V171-27 last of the backend (after 9, 12, 13, 16, 23, 24, 26); V171-28 needs V171-6 and V171-15 (both append to `_always_on_loops()`); V171-29 needs V171-28 and V171-25.

**Consumed from parts 1-3 (ledger names only):** `kinds`: `Asker` (`.priority`, `.window_s(kind)`), `DataKind.{QUOTE, DAILY_BARS, INTRADAY_BARS, INDEX_QUOTE, EARNINGS, METADATA}`, `PROVIDER_ALPACA`, `PROVIDER_YF`, `Entry` (`value`, `fetched_at`, `source`, `outcome`, `age_s()`), `QuoteDetail` (`price`, `trade_at`, `quote_at`, `mid()`, `to_doc()`, `from_doc()`), `cache_key`, `fresh_request`, `is_fresh_request`, `resolve_asker`, `INTRADAY_MAX_AGE_S`; `layer.get(kind, symbols, fetch, *, asker, provider, params="", max_age_s=None, deadline_s=10.0, encode, decode) -> dict[str, Entry]`, `layer.lease(kind, symbol, *, asker, deadline_s=30.0)`, `layer.last_cached(kind, symbols, params="")`; `counters.count`, `counters.warn_fail_open(operation, exc)`; `side_engine.side_connection()`; `market_shared_repo().read_entries / write_entries`; `router.asker_scope(asker)`, `router.current_asker()`; `yf_safe.BudgetDeferred`, `yf_safe._take_yf_token()` (V171-8: the one yfinance token rule, tiers 1-3 never denied); `data.get_quote_batch(tickers, *, asker, max_age_s=None, fresh_only=False)`; `daily_delta.read_daily(ticker, basis=None)`, `daily_delta.BASIS_YF`, `data_store.atomic_write_csv` (V171-11).

**Settled contracts this part relies on** (part 1 and 2 headers): the layer never takes a budget token; the provider call site does, at `router.current_asker()`, so every fetch callable below runs inside `router.asker_scope(asker)` and takes its yfinance token through `yf_safe._take_yf_token()` (reused, never copied) when it calls `yf.Ticker` directly. `max_age_s=0.0` means never from cache (`is not None`, never truthiness). `METADATA` is persistent for every asker, `ADMIN_FRESH` included. A `None` value in a fetch reply is a miss and is never written, so a blank reply never overwrites the last good value. `BudgetDeferred` raised inside `fetch` becomes `budget-deferred` (last cached value of any age, else absent).

**Decisions this part fixes** (inside the ledger's contracts):

- **Off means today, exactly.** Every public function edited here keeps its pre-v171 body as a `_..._legacy` helper (moved verbatim) and calls it when `MARKETDATA_LAYER == "off"`. `count` runs the legacy body too and adds one `counters.count(..., "fetched")` per provider round trip it is about to make; `on` goes through the layer. A test per function pins each mode.
- **Earnings: one doc per ticker.** `{"calendar": [ISO dates], "datetimes": [ISO datetimes, original offset kept], "query_ok": bool}`, built from `Ticker.calendar` plus `Ticker.get_earnings_dates(limit=8)`. Every reader derives from it. Two yfinance tokens per ticker. The alert path (`earnings_within_window`) runs at `SCAN`; the compression snapshot stays at the `BACKGROUND` default (it fires only on a raw signal); the admin warm-up runs at `ADMIN_PAGE`. The warm-up pool lives in `events.py`, so V171-23 implements the `ADMIN_PAGE` warm-up and V171-26 only pins it from the admin side.
- **Metadata: one doc per ticker** `{"name", "currency"}` from one `Ticker.info` (currency falls back to `fast_info`), always at `Asker.BACKGROUND` (tier 4: rare, never a tier 1-3 token). The local directory fast path and `ticker_meta_cache.json` stay in every mode. An empty layer answer (deferred or failed) is not cached in-process as "no name".
- **Admin price age is the quote's own age** (`now - (trade_at or quote_at)`), the same rule as V171-9's `PriceQuote.age_s`. The server picks the Dashboard window for `/api/v1/trades` when the request's `Referer` path starts with `/dashboard` (the Dashboard reads its positions through that endpoint), so no SPA contract is added. Rows gain `price_age_s` and `price_as_of` on every row (None when unpriced and on the `off` path).
- **The admin reads daily bars from the yfinance-basis file** (`BASIS_YF`) and never writes `daily_alpaca`. A missing file is filled by `data_refresh.refresh_symbol` (full depth); a stale one by `data_store.update_cache` (incremental, union). Stale = older than the page's quote window (60 s, 0 when fresh) while the US market is active, else `SCAN_CACHE_MAX_AGE_HOURS`. Both run under `layer.lease(DAILY_BARS, ticker)`, the key `daily_delta.write_daily` uses, so the admin and the bot never write one yfinance file at once.
- **The tape module handles exactly the fixed tape plus the proxy-mapped symbols** (`is_tape_symbol`). Every other flagged symbol keeps today's `tape_cache` path; Yahoo-only flags outside the proxy map (for example `^RUT`, `GC=F`, `ASML.AS`) have no proxy and are listed in V171-28. The tape ignores the fresh mark: admin tabs read the shared copy and self-fetch only when it is older than `TAPE_STALE_FALLBACK_S`, in the background.
- **Shared tape needs the layer:** `TAPE_SHARED_ENABLED` takes effect only when `MARKETDATA_LAYER == "on"` (the cache exists only then); otherwise the loop is a no-op and the endpoint keeps today's path.

# Phase 5 — Demand cuts, admin freshness, the guard, the shared tape

### Task V171-23: Earnings through the layer with the 6 h window (`get_next_earnings_date`, `earnings_snapshot`, `get_earnings_datetimes`)

**Model:** sonnet — one module, existing in-process caches become layer calls

**Files:**
- Modify: `swingbot/core/market/events.py` (public readers :55-272, warm-up :132-160)
- Create: `tests/market/test_events_shared_cache.py`

**Interfaces:**
- Consumes: `layer.get` (V171-6); `Asker`, `DataKind.EARNINGS`, `PROVIDER_YF`, `Entry` (V171-2); `counters.count` (V171-4); `router.asker_scope` (V171-8); `yf_safe._take_yf_token`, `yf_safe.BudgetDeferred` (V171-8); `config.MARKETDATA_LAYER`, `EARNINGS_MAX_AGE_S` (V171-1, read through `Asker.window_s`).
- Produces:
  - `events._earnings_docs(tickers: list[str], *, asker: Asker, max_age_s: float | None = None) -> dict[str, dict]`: tickers upper-cased, stripped, de-duplicated; funds and spot metals (`_never_reports`) dropped before the layer; chunks of `_EARNINGS_CHUNK = 10` (one chunk stays well inside the 30 s lease), one `layer.get(DataKind.EARNINGS, chunk, _fetch_earnings_docs, asker=asker, provider=PROVIDER_YF, max_age_s=max_age_s)` per chunk inside `router.asker_scope(asker)`. Each returned doc is the stored doc plus `"fetched_at"` (the entry's `fetched_at` ISO). Every doc returned also primes `_earnings_datetime_cache` and `_earnings_datetimes_cache` with the stamp `time.monotonic() - entry.age_s()`, so the peek functions answer in-process and an old shared doc never gains a fresh 6 h.
  - `events._earnings_doc(ticker: str, *, asker: Asker, max_age_s: float | None = None) -> dict` (ledger): one ticker through `_earnings_docs`; `_EMPTY_DOC = {"calendar": [], "datetimes": [], "query_ok": False, "fetched_at": None}` when absent.
  - `events._fetch_earnings_docs(symbols: list[str]) -> dict[str, dict | None]`: takes `2 * len(symbols)` yfinance tokens up front through `yf_safe._take_yf_token()` (a tier 4-5 denial raises `BudgetDeferred` before any call), then `_fetch_one_doc(symbol)` per symbol on a `ThreadPoolExecutor(max_workers=min(10, n))`. `_fetch_one_doc` walks `candidate_symbols` like the legacy readers: `calendar` from the first candidate whose `Ticker.calendar["Earnings Date"]` is non-empty (only `dt.date` items, ISO); `datetimes` from the first candidate whose `get_earnings_dates(limit=8)` did not raise (`ts.to_pydatetime().isoformat()`, sorted, offset kept); `query_ok` True once a `get_earnings_dates` call returned. A symbol where every call raised is `None` (a miss: never written, so the last good doc survives).
  - Public signatures (keyword added, defaults per the ledger): `get_next_earnings_date(ticker, *, asker: Asker = Asker.BACKGROUND)`, `get_next_earnings_datetime(ticker, *, asker: Asker = Asker.BACKGROUND)`, `get_earnings_datetimes(ticker, *, refresh=False, asker: Asker = Asker.BACKGROUND)` (`refresh=True` -> `max_age_s=0.0`), `earnings_snapshot(ticker, *, now=None, asker: Asker = Asker.BACKGROUND)`, `earnings_within_window(ticker, max_holding_days)` (the alert path: passes `asker=Asker.SCAN`), `warm_earnings_cache_background(tickers, *, asker: Asker = Asker.ADMIN_PAGE) -> threading.Thread` (`on`: one daemon thread calling `_earnings_docs(tickers, asker=asker)`; otherwise today's pool, unchanged).

Derivations in `on` mode (one pure helper each, over a doc): next date = `min(d for d in calendar if d >= market_today())`; next datetime = `min(ts for ts in datetimes if ts >= now_utc)`; datetimes = the sorted list; snapshot = `EarningsSnapshot(observed_at=now if now is not None else fetched_at (else now_utc), reports=datetimes, query_ok=doc["query_ok"], source="yahoo")`. The `_never_reports` early returns stay first in every public function, in every mode.

- [ ] **Step 1: Write the failing tests**

Create `tests/market/test_events_shared_cache.py`:

```python
"""v171 D2/D8: earnings dates through the shared layer with the 6 h window."""
import datetime as dt
from datetime import timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import events
from swingbot.core.marketdata.shared import counters, layer
from swingbot.core.marketdata.shared.kinds import PROVIDER_YF, Asker, DataKind, Entry

NOW = dt.datetime.now(timezone.utc)
FUTURE = (NOW + dt.timedelta(days=14)).replace(microsecond=0)
PAST = (NOW - dt.timedelta(days=80)).replace(microsecond=0)
DOC = {"calendar": [(NOW.date() - dt.timedelta(days=5)).isoformat(), FUTURE.date().isoformat()],
       "datetimes": [FUTURE.isoformat(), PAST.isoformat()], "query_ok": True}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    events._earnings_datetime_cache.clear()
    events._earnings_datetimes_cache.clear()
    monkeypatch.setattr(events, "_never_reports", lambda t: t.upper() in {"SPY", "XAUUSD"})
    yield
    events._earnings_datetime_cache.clear()
    events._earnings_datetimes_cache.clear()


@pytest.fixture
def on_layer(monkeypatch):
    """`on` mode with layer.get answering DOC; records every call's kwargs."""
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    calls = []

    def fake_get(kind, symbols, fetch, **kw):
        calls.append({"kind": kind, "symbols": list(symbols), **kw})
        return {s: Entry(value=dict(DOC), fetched_at=NOW - dt.timedelta(seconds=30),
                         source="yfinance", outcome="hit") for s in symbols}
    monkeypatch.setattr(layer, "get", fake_get)
    return calls


class FakeTicker:
    calls = []

    def __init__(self, symbol):
        self.symbol = symbol

    @property
    def calendar(self):
        FakeTicker.calls.append(("calendar", self.symbol))
        return {"Earnings Date": [FUTURE.date()]}

    def get_earnings_dates(self, limit):
        FakeTicker.calls.append(("dates", self.symbol, limit))
        idx = pd.DatetimeIndex([pd.Timestamp(FUTURE).tz_convert("America/New_York")])
        return pd.DataFrame({"EPS Estimate": [1.0]}, index=idx)


class BrokenTicker:
    def __init__(self, symbol):
        pass

    @property
    def calendar(self):
        raise RuntimeError("yahoo")

    def get_earnings_dates(self, limit):
        raise RuntimeError("yahoo")


@pytest.fixture
def fake_yf(monkeypatch):
    FakeTicker.calls = []
    monkeypatch.setattr(events.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(events, "candidate_symbols", lambda t: [t])
    monkeypatch.setattr(events.yf_safe, "_take_yf_token", lambda: None)
    return FakeTicker.calls


def test_off_mode_is_the_legacy_path(monkeypatch, fake_yf):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(layer, "get", lambda *a, **k: pytest.fail("layer used in off mode"))
    assert events.get_next_earnings_date("AAPL") == FUTURE.date()
    assert fake_yf == [("calendar", "AAPL")]


def test_on_mode_is_one_layer_call_with_the_earnings_kind(on_layer):
    assert events.get_next_earnings_date("aapl ") == FUTURE.date()
    (call,) = on_layer
    assert call["kind"] is DataKind.EARNINGS and call["symbols"] == ["AAPL"]
    assert call["provider"] == PROVIDER_YF and call["asker"] is Asker.BACKGROUND
    assert call["max_age_s"] is None                       # the asker's 6 h window decides


def test_the_alert_path_runs_at_the_scan_tier(on_layer, monkeypatch):
    monkeypatch.setattr(events, "market_today", lambda: NOW.date())
    assert events.earnings_within_window("AAPL", 30) == (FUTURE.date(), 14)
    assert on_layer[0]["asker"] is Asker.SCAN


def test_every_reader_derives_from_the_one_doc(on_layer):
    assert events.get_next_earnings_datetime("AAPL") == FUTURE
    assert events.get_earnings_datetimes("AAPL") == [PAST, FUTURE]
    snap = events.earnings_snapshot("AAPL")
    assert snap.query_ok is True and snap.reports == (PAST, FUTURE) and snap.source == "yahoo"
    assert abs((snap.observed_at - (NOW - dt.timedelta(seconds=30))).total_seconds()) < 1


def test_refresh_forces_a_fetch(on_layer):
    events.get_earnings_datetimes("AAPL", refresh=True)
    assert on_layer[0]["max_age_s"] == 0.0


def test_funds_and_spot_never_reach_the_layer(on_layer):
    assert events.get_next_earnings_date("SPY") is None
    assert events.earnings_snapshot("XAUUSD").source == "nonreporting_instrument"
    assert on_layer == []


def test_a_layer_answer_primes_the_peek_caches(on_layer):
    events.get_earnings_datetimes("AAPL")
    assert events.peek_cached_earnings_datetime("AAPL") == FUTURE
    assert events.peek_cached_earnings_datetimes("AAPL") == [PAST, FUTURE]


def test_fetch_builds_one_doc_with_offsets_kept(fake_yf):
    docs = events._fetch_earnings_docs(["AAPL"])
    assert docs["AAPL"]["calendar"] == [FUTURE.date().isoformat()]
    (stamp,) = docs["AAPL"]["datetimes"]
    assert stamp.endswith(("-04:00", "-05:00"))          # America/New_York offset survives
    assert docs["AAPL"]["query_ok"] is True
    assert ("dates", "AAPL", 8) in fake_yf


def test_fetch_failure_is_a_miss_and_reads_as_query_not_ok(monkeypatch, on_layer):
    monkeypatch.setattr(events.yf, "Ticker", BrokenTicker)
    monkeypatch.setattr(events, "candidate_symbols", lambda t: [t])
    monkeypatch.setattr(events.yf_safe, "_take_yf_token", lambda: None)
    assert events._fetch_earnings_docs(["AAPL"]) == {"AAPL": None}
    monkeypatch.setattr(layer, "get", lambda *a, **k: {})
    assert events.earnings_snapshot("AAPL").query_ok is False


def test_a_short_budget_defers_before_any_call(monkeypatch, fake_yf):
    def deny():
        raise events.yf_safe.BudgetDeferred("tier 5")
    monkeypatch.setattr(events.yf_safe, "_take_yf_token", deny)
    with pytest.raises(events.yf_safe.BudgetDeferred):
        events._fetch_earnings_docs(["AAPL", "MSFT"])
    assert fake_yf == []


def test_count_mode_counts_each_legacy_fetch(monkeypatch, fake_yf):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    seen = []
    monkeypatch.setattr(counters, "count", lambda *a, **k: seen.append(a))
    events.get_next_earnings_date("AAPL")
    events.get_next_earnings_datetime("AAPL")
    events.get_next_earnings_datetime("AAPL")              # in-process 6 h hit: no Yahoo, no count
    assert seen == [(PROVIDER_YF, DataKind.EARNINGS, Asker.BACKGROUND, "fetched")] * 2


def test_warm_up_is_one_layer_call_at_admin_page(on_layer):
    events.warm_earnings_cache_background(["AAPL", "MSFT"]).join(5)
    assert [(c["symbols"], c["asker"]) for c in on_layer] == [(["AAPL", "MSFT"], Asker.ADMIN_PAGE)]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/market/test_events_shared_cache.py`
Expected: FAIL (`AttributeError: module 'swingbot.core.market.events' has no attribute 'yf_safe'` / `'_fetch_earnings_docs'`, and `TypeError` on the `asker` keyword).

- [ ] **Step 3: Implement in `events.py`**

Imports: `from swingbot import config`, `from swingbot.core.marketdata import yf_safe`, `from swingbot.core.marketdata.providers import router`, `from swingbot.core.marketdata.shared import counters, layer`, `from swingbot.core.marketdata.shared.kinds import PROVIDER_YF, Asker, DataKind`. Keep `import yfinance as yf` (`events.py` stays on the V171-27 allowlist: it holds the earnings provider functions). Call `layer.get`, `counters.count` and `yf_safe._take_yf_token` through their modules (the tests patch them there).

Verbatim moves: today's `get_next_earnings_date` body after the `_never_reports` check becomes `_next_earnings_date_legacy(ticker)`; today's `get_earnings_datetimes` cache-and-fetch body becomes `_earnings_datetimes_legacy(ticker, refresh)`; today's `earnings_snapshot` fetch loop becomes `_snapshot_legacy(ticker, observed)`; today's pool body of `warm_earnings_cache_background` becomes `_warm_legacy(tickers)`. `get_next_earnings_datetime` keeps its 6 h in-process cache and `_fetch_next_earnings_datetime` on the `off`/`count` path.

Each public reader is three lines past the `_never_reports` check, for example:

```python
def get_next_earnings_date(ticker: str, *, asker: Asker = Asker.BACKGROUND) -> dt.date | None:
    """(today's docstring) v171: `on` reads the shared earnings doc (6 h window)."""
    if _never_reports(ticker):
        return None
    if config.MARKETDATA_LAYER == "on":
        return _next_date(_earnings_doc(ticker, asker=asker))
    _count_legacy(asker)
    return _next_earnings_date_legacy(ticker)
```

`_count_legacy(asker, will_fetch: bool = True) -> None` calls `counters.count(PROVIDER_YF, DataKind.EARNINGS, asker, "fetched")` only when `MARKETDATA_LAYER == "count"` and `will_fetch`. `get_next_earnings_datetime` passes `will_fetch=peek_cached_earnings_datetime(ticker) is _NOT_CACHED`; `get_earnings_datetimes` passes `will_fetch=_datetimes_will_fetch(ticker, refresh)`, a small helper that mirrors the legacy cache test exactly (a cached `[]` inside 6 h is a hit, not a fetch; `peek_cached_earnings_datetimes` answers None for it, so read `_earnings_datetimes_cache` directly).

`earnings_within_window` changes one line: `next_date = get_next_earnings_date(ticker, asker=Asker.SCAN)`.

`_fetch_one_doc` and the derivation helpers (`_next_date`, `_next_datetime`, `_datetimes`) stay a few lines each; parse with `dt.date.fromisoformat` / `dt.datetime.fromisoformat`. `_earnings_docs` uses `entry.age_s()` for the priming stamp and writes the singular cache with `_next_datetime(doc)`.

- [ ] **Step 4: Run the tests to verify they pass, with the existing earnings tests**

Run: `python $WT/scripts/dev/testrun.py file tests/market/test_events_shared_cache.py`
Expected: PASS.
Run: `git -C $WT grep -l "earnings" -- tests/market tests/admin tests/scanning tests/commands`, then `python $WT/scripts/dev/testrun.py file <each>` for every file that imports `events` or `earnings_calendar`.
Expected: all PASS, `0 failed` (they run at the code default `off`).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/market/events.py`
Expected: no output (every function below C; `get_earnings_datetimes` was B 14 and now delegates).

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/market/events.py tests/market/test_events_shared_cache.py
git -C $WT commit -m "feat(events): v171 earnings through the shared layer, one doc per ticker, 6 h window (V171-23)"
```

### Task V171-24: Metadata and intraday bars through the layer (`get_company_name`, `get_currency_symbol`, `fast_info`, `get_intraday`)

**Model:** sonnet — one module family, persistent metadata kind

**Files:**
- Modify: `swingbot/core/marketdata/data.py` (`get_company_name` :372-410, `_resolve_currency_code` :413-424, `get_currency_symbol` :427-447)
- Modify: `swingbot/core/marketdata/data_store.py` (`get_intraday` :445-482)
- Create: `tests/marketdata/test_metadata_layer.py`

**Interfaces:**
- Consumes: `layer.get`, `layer.lease` (V171-6); `Asker`, `DataKind.METADATA`, `DataKind.INTRADAY_BARS`, `PROVIDER_YF`, `PROVIDER_ALPACA`, `Entry`, `INTRADAY_MAX_AGE_S` (V171-2); `counters.count` (V171-4); `router.asker_scope`, `router.current_asker` (V171-8); `yf_safe._take_yf_token` (V171-8); `providers.base.is_alpaca_eligible` (exists).
- Produces:
  - `data._ticker_meta(ticker: str) -> dict` (ledger): `layer.get(DataKind.METADATA, [key], _fetch_ticker_meta, asker=Asker.BACKGROUND, provider=PROVIDER_YF)` inside `router.asker_scope(Asker.BACKGROUND)`; returns the stored doc `{"name": str | None, "currency": str | None}`, or `{}` when the layer has nothing (budget-deferred, failed). Metadata is persistent (`window_s` is `None` for every asker), so a doc once written is never refetched.
  - `data._fetch_ticker_meta(symbols: list[str]) -> dict[str, dict | None]`: per symbol, per `candidate_symbols` entry, one `yf_safe._take_yf_token()` then one `yf.Ticker(c).info`: `name = info.get("longName") or info.get("shortName")`, `currency = info.get("currency")` upper-cased; when `.info` answered without a currency, one `fast_info` read (today's `_resolve_currency_code` rule) fills it. The first candidate that answered without raising wins. A symbol whose every call raised is `None` (a miss, never written).
  - `data._provider_company_name(key: str) -> tuple[str | None, bool]` and `data._provider_currency_code(key: str) -> tuple[str | None, bool]` (value, answered): `off` -> today's slow path (`_company_name_legacy(key)`, the candidate loop moved verbatim; `_resolve_currency_code(key)`), `answered=True`; `count` -> the same plus `counters.count(PROVIDER_YF, DataKind.METADATA, router.current_asker(), "fetched")`; `on` -> `_ticker_meta(key)`, `answered = bool(meta)`. `get_company_name` and `get_currency_symbol` cache and persist only when `answered`; an unanswered lookup returns `None` / `default_symbol` without writing the in-process cache or `ticker_meta_cache.json`, so a deferred fetch is retried next time. The local directory fast path and the JSON file stay in every mode.
  - `data_store.get_intraday(symbol, interval="1h", base_dir=DATA_DIR, fetch_fn=None)`: unchanged signature. `off` is today's path. Otherwise, after the fresh-file check fails: `with layer.lease(DataKind.INTRADAY_BARS, f"{symbol}:{interval}", asker=router.current_asker())`, re-check the file (another holder may have just written it; read it and fetch nothing), else fetch and merge exactly as today (also when the lease failed open), then `counters.count(_intraday_provider(symbol), DataKind.INTRADAY_BARS, asker, "fetched")`. `_intraday_provider(symbol) -> str` is `PROVIDER_ALPACA` when `config.ALPACA_ENABLED` and `is_alpaca_eligible(symbol)`, else `PROVIDER_YF`.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_metadata_layer.py`:

```python
"""v171 D1/D2: ticker metadata (persistent) and intraday bars through the layer."""
import contextlib
import os
import time
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata import data, data_store
from swingbot.core.marketdata.shared import counters, kinds, layer
from swingbot.core.marketdata.shared.kinds import PROVIDER_YF, Asker, DataKind, Entry
from tests.helpers import make_ohlcv

META = {"ASML.AS": {"name": "ASML Holding N.V.", "currency": "EUR"}}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(data, "_company_name_cache", {})
    monkeypatch.setattr(data, "_currency_cache", {})
    saved = []
    monkeypatch.setattr(data, "_save_ticker_meta_cache", lambda: saved.append(1))
    monkeypatch.setattr("swingbot.core.marketdata.ticker_directory.lookup_name", lambda key: None)
    monkeypatch.setattr(data, "candidate_symbols", lambda t: [t])
    return saved


@pytest.fixture
def on_layer(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    calls = []

    def fake_get(kind, symbols, fetch, **kw):
        calls.append({"kind": kind, "symbols": list(symbols), **kw})
        return {s: Entry(META[s], datetime.now(timezone.utc), "yfinance", "hit")
                for s in symbols if s in META}
    monkeypatch.setattr(layer, "get", fake_get)
    return calls


class FakeTicker:
    reads = []

    def __init__(self, symbol):
        self.symbol = symbol

    @property
    def info(self):
        FakeTicker.reads.append(("info", self.symbol))
        return {"longName": "ASML Holding N.V."}            # no currency: fast_info fills it

    @property
    def fast_info(self):
        FakeTicker.reads.append(("fast_info", self.symbol))
        return {"currency": "eur"}


def test_intraday_window_matches_data_store():
    assert kinds.INTRADAY_MAX_AGE_S == data_store.INTRADAY_MAX_AGE_SECONDS


def test_on_mode_name_and_currency_come_from_one_persistent_meta_doc(on_layer, isolated):
    assert data.get_company_name("asml.as") == "ASML Holding N.V."
    assert data.get_currency_symbol("ASML.AS") == "€"
    assert data.get_company_name("ASML.AS") == "ASML Holding N.V."      # in-process hit
    assert [c["kind"] for c in on_layer] == [DataKind.METADATA] * 2
    assert all(c["asker"] is Asker.BACKGROUND and c["provider"] == PROVIDER_YF for c in on_layer)
    assert len(isolated) == 2                                           # both persisted


def test_an_unanswered_lookup_is_not_cached_as_no_name(on_layer, isolated):
    assert data.get_company_name("NEWCO") is None
    assert "NEWCO" not in data._company_name_cache and isolated == []
    assert data.get_currency_symbol("NEWCO", default_symbol="€") == "€"
    assert "NEWCO" not in data._currency_cache


def test_directory_names_never_reach_the_layer(on_layer, monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.ticker_directory.lookup_name", lambda key: "Apple Inc.")
    assert data.get_company_name("AAPL") == "Apple Inc." and on_layer == []


def test_off_mode_keeps_the_legacy_slow_path(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(layer, "get", lambda *a, **k: pytest.fail("layer used in off mode"))
    FakeTicker.reads = []
    monkeypatch.setattr(data.yf, "Ticker", FakeTicker)
    assert data.get_company_name("ASML.AS") == "ASML Holding N.V."
    assert FakeTicker.reads == [("info", "ASML.AS")]


def test_count_mode_counts_each_metadata_fetch(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    monkeypatch.setattr(data.yf, "Ticker", FakeTicker)
    seen = []
    monkeypatch.setattr(counters, "count", lambda *a, **k: seen.append(a[:2] + a[3:]))
    data.get_company_name("ASML.AS")
    data.get_currency_symbol("ASML.AS")
    assert seen == [(PROVIDER_YF, DataKind.METADATA, "fetched")] * 2


def test_meta_fetch_reads_info_once_and_falls_back_to_fast_info(monkeypatch):
    FakeTicker.reads = []
    monkeypatch.setattr(data.yf, "Ticker", FakeTicker)
    tokens = []
    monkeypatch.setattr(data.yf_safe, "_take_yf_token", lambda: tokens.append(1))
    assert data._fetch_ticker_meta(["ASML.AS"]) == {"ASML.AS": {"name": "ASML Holding N.V.", "currency": "EUR"}}
    assert FakeTicker.reads == [("info", "ASML.AS"), ("fast_info", "ASML.AS")] and tokens


def test_meta_fetch_failure_is_a_miss(monkeypatch):
    class Broken:
        def __init__(self, s):
            pass

        @property
        def info(self):
            raise RuntimeError("yahoo")
    monkeypatch.setattr(data.yf, "Ticker", Broken)
    monkeypatch.setattr(data.yf_safe, "_take_yf_token", lambda: None)
    assert data._fetch_ticker_meta(["ZZZZ"]) == {"ZZZZ": None}


# --- intraday ---------------------------------------------------------------

def _stale_file(tmp_path, symbol="AAPL"):
    data_store.save_to_disk(make_ohlcv([10.0, 11.0]), symbol, "1h", base_dir=str(tmp_path))
    path = data_store.cache_path(symbol, "1h", base_dir=str(tmp_path))
    old = time.time() - data_store.INTRADAY_MAX_AGE_SECONDS - 60
    os.utime(path, (old, old))
    return path


def _lease_recorder(monkeypatch, held=True, on_enter=None):
    taken = []

    @contextlib.contextmanager
    def fake_lease(kind, symbol, *, asker, deadline_s=30.0):
        taken.append((kind, symbol, asker))
        if on_enter:
            on_enter()
        yield held
    monkeypatch.setattr(layer, "lease", fake_lease)
    return taken


def test_on_mode_intraday_fetches_once_under_the_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    _stale_file(tmp_path)
    taken = _lease_recorder(monkeypatch)
    fetched = []
    out = data_store.get_intraday("AAPL", "1h", base_dir=str(tmp_path),
                                  fetch_fn=lambda s, i: fetched.append(s) or make_ohlcv([12.0, 13.0]))
    assert fetched == ["AAPL"] and out is not None
    assert taken == [(DataKind.INTRADAY_BARS, "AAPL:1h", Asker.SCAN)]


def test_a_file_written_by_the_other_holder_is_read_not_refetched(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    path = _stale_file(tmp_path)
    _lease_recorder(monkeypatch, held=False, on_enter=lambda: os.utime(path, None))
    out = data_store.get_intraday("AAPL", "1h", base_dir=str(tmp_path),
                                  fetch_fn=lambda s, i: pytest.fail("refetched"))
    assert out is not None and len(out) == 2


def test_off_mode_intraday_takes_no_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    _stale_file(tmp_path)
    monkeypatch.setattr(layer, "lease", lambda *a, **k: pytest.fail("lease in off mode"))
    out = data_store.get_intraday("AAPL", "1h", base_dir=str(tmp_path),
                                  fetch_fn=lambda s, i: make_ohlcv([12.0, 13.0]))
    assert out is not None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_metadata_layer.py`
Expected: FAIL (`AttributeError: ... has no attribute '_fetch_ticker_meta'`; the on-mode tests call `yf.Ticker` instead of `layer.get`; the intraday on-mode tests see no lease).

- [ ] **Step 3: Implement the metadata path in `data.py`**

Add `from swingbot.core.marketdata.shared import counters` beside the V171-9 layer import, and `PROVIDER_YF` to the `kinds` import. Move today's slow-path loop of `get_company_name` (the `for candidate in candidate_symbols(ticker_key)` block that reads `.info`) verbatim into `_company_name_legacy(ticker_key) -> str | None`. `get_company_name` after the directory fast path becomes:

```python
    name, answered = _provider_company_name(ticker_key)
    if not answered:
        return None            # v171: deferred or failed shared lookup; retry next time
    _company_name_cache[ticker_key] = name
    _save_ticker_meta_cache()  # persist so this network call isn't repeated after the next restart
    return name
```

`get_currency_symbol` does the same with `code, answered = _provider_currency_code(ticker_key)`, returning `default_symbol` uncached when not answered, and today's mapping/caching otherwise. `_ticker_meta`, `_fetch_ticker_meta` and the two `_provider_*` helpers per the Interfaces block, each a few lines (the `_fetch_ticker_meta` per-symbol work goes in `_meta_for(symbol) -> dict | None`). `BudgetDeferred` from `_take_yf_token` propagates out of `_fetch_ticker_meta` (the layer records `budget-deferred`).

- [ ] **Step 4: Implement the intraday lease in `data_store.py`**

Behaviour-preserving extraction: move today's `get_intraday` body from `def _default_fetch` down to `return merged` verbatim into `_fetch_merge_intraday(symbol, interval, base_dir, fetch_fn)`, and the freshness test into `_intraday_fresh(path) -> bool`. Then:

```python
    if _intraday_fresh(path):
        return load_from_disk(symbol, interval, base_dir=base_dir)
    if config.MARKETDATA_LAYER == "off":
        return _fetch_merge_intraday(symbol, interval, base_dir, fetch_fn)
    return _intraday_under_lease(symbol, interval, base_dir, fetch_fn, path)
```

`_intraday_under_lease` imports `layer`, `counters` and the kinds lazily (this module is imported early by many others), takes `asker = router.current_asker()`, holds the lease as described in Interfaces, and counts after a fetch. Spot symbols still return through `_spot_intraday` before any of this (their future's name is what gets leased). Add `from swingbot import config` if the module does not import it yet.

- [ ] **Step 5: Run the tests to verify they pass, with the neighbours**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_metadata_layer.py`
Expected: PASS.
Run: `git -C $WT grep -l "get_company_name\|get_currency_symbol\|get_intraday" -- tests`, then `python $WT/scripts/dev/testrun.py file <each>`
Expected: all PASS, `0 failed`.

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/data.py $WT/swingbot/core/marketdata/data_store.py`
Expected: only `load_normalized` if it was already listed (C 13 is below the C threshold, so normally no output); no new line.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/core/marketdata/data.py swingbot/core/marketdata/data_store.py tests/marketdata/test_metadata_layer.py
git -C $WT commit -m "feat(marketdata): v171 ticker metadata and intraday bars through the shared layer (V171-24)"
```

### Task V171-25: Admin freshness (`X-Swingbot-Fresh`), Dashboard/Trades/Watchlist prices through the layer with ages

**Model:** sonnet — admin readers inside one container, contracts fixed by D2

**Files:**
- Create: `swingbot/admin/freshness.py`
- Modify: `swingbot/admin/app.py` (one `freshness.install(app)` call after `_reload_env_if_changed` :178-195)
- Modify: `swingbot/admin/dashboard.py` (`build_open_trade_views` :355-450: two lines, one new helper)
- Modify: `swingbot/admin/watchlist_rows.py` (`_empty_row` :113-122, `build_market_rows` :148-166, `_live_overlay` :169-185)
- Modify: `swingbot/admin/api_v1/trades.py` (row defaults :310-311 and :513-514, `_attach_current_prices` :1085-1119)
- Modify: `tests/admin/conftest.py` (new fixture `layer_quotes`)
- Modify: `tests/admin/test_api_v1_trades.py` (`TRADE_ROW` gains the two keys), plus every row-shape spec in `tests/admin/test_api_v1_watchlist.py` / `tests/admin/test_watchlist_rows.py` that pins the market row keys
- Create: `tests/admin/test_admin_freshness.py`

**Interfaces:**
- Consumes: `kinds.fresh_request`, `is_fresh_request`, `resolve_asker`, `Asker.ADMIN_PAGE`, `Asker.ADMIN_DASHBOARD`, `DataKind.QUOTE`, `QuoteDetail`, `Entry` (V171-2); `layer.last_cached` (V171-6); `data.get_quote_batch` (V171-9); `config.MARKETDATA_LAYER`.
- Produces (`swingbot/admin/freshness.py`; V171-26 and V171-29 build on it):
  - `FRESH_HEADER = "X-Swingbot-Fresh"`.
  - `install(app) -> None`: registers a `before_request` that enters `kinds.fresh_request()` when `request.headers.get(FRESH_HEADER) == "1"` (the context manager is kept on `flask.g`) and a `teardown_request` that exits it, so the mark covers exactly one request.
  - `layer_on() -> bool` (`config.MARKETDATA_LAYER == "on"`; every admin caller keeps today's path otherwise).
  - `from_dashboard() -> bool`: inside a request, True when the `Referer` URL's path starts with `/dashboard` (the Dashboard reads its positions through `/api/v1/trades`); False outside a request.
  - `page_asker(*, dashboard: bool = False) -> Asker` (`ADMIN_DASHBOARD` or `ADMIN_PAGE`; `resolve_asker` turns either into `ADMIN_FRESH` inside a marked request).
  - `page_window_s(*, dashboard: bool = False) -> float` (`resolve_asker(page_asker(...)).window_s(DataKind.QUOTE)`: 15, 60, or 0.0 when fresh).
  - `page_quotes(tickers: list[str], *, dashboard: bool = False) -> dict[str, QuoteDetail]` (ledger): one `data.get_quote_batch(tickers, asker=page_asker(dashboard=dashboard))`, keys upper-case; any exception -> `{}` (logged at debug). Budget-deferred and deadline answers come back as the last cached value (the layer's rule), an empty cache as absent.
  - `cached_quotes(tickers: list[str]) -> dict[str, Entry]`: one `layer.last_cached(DataKind.QUOTE, tickers)`, each value decoded with `QuoteDetail.from_doc`; never fetches; `{}` on any error.
  - `warm_quotes_background(tickers: list[str], *, dashboard: bool = False) -> threading.Thread`: a daemon thread running `page_quotes` inside `contextvars.copy_context()`, so a fresh mark survives into the thread.
  - `quote_age(q: QuoteDetail | None, now: datetime | None = None) -> tuple[float | None, str | None]`: `(seconds since trade_at or quote_at, that timestamp ISO)`, `(None, None)` when there is neither. Same rule as V171-9's `PriceQuote.age_s`.
- API rows gain `price_age_s: float | None` and `price_as_of: str | None` (ledger): every `/api/v1/trades` row (defaults None in both row builders) and every Watchlist market row (`_empty_row`). Set only when the price came from the layer.

Mode rules: `off` and `count` run today's code in all four readers (count mode's own call volume is the D9 baseline). `on`: the Trades list prices its live rows with one `page_quotes` call (Dashboard asker when `from_dashboard()`); `current_price_stale` is False for a layer price (the age now carries that signal). The Dashboard summary (`build_open_trade_views`) prices with `page_quotes(..., dashboard=True)`. The Watchlist overlay stays cache-only on the request (the under-1-second contract): `cached_quotes` for the overlay, then `warm_quotes_background` for symbols missing or older than `page_window_s()` (every symbol on a fresh reload). `price_source` maps `QuoteDetail.source` onto today's values: `alpaca-*` -> `"alpaca"`, `yfinance-*` -> `"yfinance"`, else None.

- [ ] **Step 1: Add the `layer_quotes` fixture to `tests/admin/conftest.py`**

```python
@pytest.fixture
def layer_quotes(monkeypatch):
    """v171: MARKETDATA_LAYER=on with data.get_quote_batch answered from
    `state["quotes"]`; records (tickers, asker, fresh-marked) per call."""
    from swingbot import config
    from swingbot.core.marketdata import data
    from swingbot.core.marketdata.shared import kinds

    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    state = {"quotes": {}, "calls": []}

    def fake(tickers, *, asker, max_age_s=None, fresh_only=False):
        state["calls"].append((list(tickers), asker, kinds.is_fresh_request()))
        wanted = {t.upper() for t in tickers}
        return {t: q for t, q in state["quotes"].items() if t in wanted}
    monkeypatch.setattr(data, "get_quote_batch", fake)
    return state
```

- [ ] **Step 2: Write the failing tests**

Create `tests/admin/test_admin_freshness.py`:

```python
"""v171 D2 admin rules: reload means fresh, navigation means reuse, ages shown."""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.admin import dashboard, freshness, watchlist_rows
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.kinds import Asker, Entry, QuoteDetail
from tests.admin.test_api_v1_trades import _open_pair
from tests.helpers import make_ohlcv
from tests.store_seed import seed_store

NOW = datetime.now(timezone.utc)


def _q(sym, price, age=12.0, source="alpaca-iex"):
    at = NOW - timedelta(seconds=age)
    return QuoteDetail(symbol=sym, price=price, trade_at=at, bid=None, ask=None,
                       quote_at=None, source=source)


@pytest.fixture
def client(admin_app):
    c = admin_app.test_client()
    c.post("/api/v1/session", json={"username": "admin", "password": "admin"})
    plan, trade = _open_pair(ticker="MSFT")
    seed_store("plans", [plan])
    seed_store("trades", [trade])
    return c


def _row(client, **headers):
    return client.get("/api/v1/trades?status=open", headers=headers).get_json()["items"][0]


def test_the_fresh_header_marks_only_its_own_request(admin_app):
    with admin_app.test_request_context("/api/v1/trades", headers={freshness.FRESH_HEADER: "1"}):
        admin_app.preprocess_request()
        assert kinds.is_fresh_request() is True
        admin_app.do_teardown_request()
    assert kinds.is_fresh_request() is False
    with admin_app.test_request_context("/api/v1/trades"):
        admin_app.preprocess_request()
        assert kinds.is_fresh_request() is False


def test_trade_rows_price_through_one_page_batch_with_their_age(client, layer_quotes):
    layer_quotes["quotes"]["MSFT"] = _q("MSFT", 110.0, age=12.0)
    row = _row(client)
    assert row["current_price"] == 110.0 and row["current_price_stale"] is False
    assert 11.0 <= row["price_age_s"] <= 15.0 and row["price_as_of"].startswith(str(NOW.year))
    assert layer_quotes["calls"] == [(["MSFT"], Asker.ADMIN_PAGE, False)]


def test_the_dashboard_referrer_selects_the_15_s_asker(client, layer_quotes):
    layer_quotes["quotes"]["MSFT"] = _q("MSFT", 110.0)
    _row(client, Referer="http://localhost/dashboard")
    assert layer_quotes["calls"][0][1] is Asker.ADMIN_DASHBOARD


def test_a_reload_runs_fresh_and_still_at_tier_5(client, layer_quotes):
    layer_quotes["quotes"]["MSFT"] = _q("MSFT", 110.0)
    _row(client, **{freshness.FRESH_HEADER: "1"})
    (tickers, asker, fresh) = layer_quotes["calls"][0]
    assert fresh is True
    with kinds.fresh_request():
        resolved = kinds.resolve_asker(asker)
    assert resolved is Asker.ADMIN_FRESH and resolved.priority == 5


def test_empty_cache_and_short_budget_render_todays_failure_value(client, layer_quotes):
    resp = client.get("/api/v1/trades?status=open")
    row = resp.get_json()["items"][0]
    assert resp.status_code == 200 and row["current_price"] is None
    assert row["price_age_s"] is None and row["price_as_of"] is None
    assert row["progress_pct"] is None and row["status_label"]


def test_layer_off_keeps_todays_prefetch_path(client, monkeypatch):
    from swingbot.core.marketdata import data
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(data, "get_quote_batch", lambda *a, **k: pytest.fail("layer used"))
    monkeypatch.setattr(data, "prefetch_prices", lambda tickers: None)
    monkeypatch.setattr(data, "get_current_price_detail", lambda t: data.PriceQuote(110.0, False))
    row = _row(client)
    assert row["current_price"] == 110.0 and row["price_age_s"] is None


def test_the_dashboard_summary_prices_at_the_dashboard_tier(admin_app, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    seen = []
    monkeypatch.setattr(freshness, "page_quotes",
                        lambda t, *, dashboard=False: seen.append((list(t), dashboard)) or {"MSFT": _q("MSFT", 110.0)})
    monkeypatch.setattr(dashboard, "prefetch_prices", lambda t: pytest.fail("legacy prefetch"))
    monkeypatch.setattr(dashboard, "compute_position_size", lambda **k: None)
    trade = {"id": "t1", "ticker": "MSFT", "direction": "bullish", "entry": 100.0,
             "stop_loss": 90.0, "take_profit": 120.0, "opened_at": NOW.isoformat()}
    views = dashboard.build_open_trade_views([trade], {})
    assert views["price"]["t1"] == 110.0 and seen == [(["MSFT"], True)]


@pytest.fixture
def overlay(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(watchlist_rows, "is_us_market_active", lambda: True)
    monkeypatch.setattr(watchlist_rows, "_cached_daily", lambda t: make_ohlcv([100.0, 101.0]))
    entry = Entry(_q("AAPL", 190.0, age=3.0), NOW - timedelta(seconds=3), "alpaca", "hit")
    monkeypatch.setattr(freshness, "cached_quotes", lambda t: {"AAPL": entry})
    warmed = []
    monkeypatch.setattr(freshness, "warm_quotes_background",
                        lambda t, **k: warmed.append(list(t)))
    return warmed


def test_the_watchlist_reads_the_shared_cache_and_warms_the_rest(overlay):
    rows = watchlist_rows.build_market_rows(["AAPL", "MSFT"])
    assert rows["AAPL"]["price"] == 190.0 and rows["AAPL"]["price_source"] == "alpaca"
    assert 2.0 <= rows["AAPL"]["price_age_s"] <= 6.0
    assert rows["MSFT"]["price"] == 101.0 and rows["MSFT"]["price_age_s"] is None
    assert overlay == [["MSFT"]]


def test_a_fresh_reload_warms_every_watchlist_symbol(overlay):
    with kinds.fresh_request():
        watchlist_rows.build_market_rows(["AAPL", "MSFT"])
    assert overlay == [["AAPL", "MSFT"]]


def test_quote_age_reads_the_trade_then_the_quote_time():
    assert freshness.quote_age(None) == (None, None)
    age, as_of = freshness.quote_age(_q("X", 1.0, age=20.0))
    assert 19.0 <= age <= 22.0 and as_of.endswith("+00:00")
    q = QuoteDetail("X", None, None, 1.0, 1.1, NOW - timedelta(seconds=5), "alpaca-iex")
    assert 4.0 <= freshness.quote_age(q)[0] <= 7.0
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_admin_freshness.py`
Expected: FAIL with `ImportError: cannot import name 'freshness' from 'swingbot.admin'`.

- [ ] **Step 4: Implement `freshness.py` and wire `app.py`**

Write the module per the Interfaces block (each function a few lines; `from_dashboard` uses `flask.has_request_context()` and `urllib.parse.urlparse(request.referrer or "").path`). Import `data` and `layer` inside the functions that need them (admin modules import lazily; see the `app.py` circular-import note). In `app.py`, add `from swingbot.admin import freshness` beside the other admin imports and call `freshness.install(app)` directly after the `_reload_env_if_changed` definition.

- [ ] **Step 5: Route the three readers**

- `api_v1/trades.py`: add `"price_age_s": None, "price_as_of": None` after both `"current_price_stale": False` defaults. In `_attach_current_prices`, after `live` is built and not empty: `if freshness.layer_on(): _attach_layer_prices(live); return` (import inside the function). `_attach_layer_prices(live)` calls `freshness.page_quotes([r["ticker"] for r in live], dashboard=freshness.from_dashboard())` once and sets `current_price` (the quote's `price` when > 0, else None), `current_price_stale=False`, and `price_age_s`/`price_as_of` from `freshness.quote_age` (None when there is no price).
- `dashboard.py`: new `_open_trade_prices(open_trades) -> dict[str, float | None]`. `off`/`count`: `prefetch_prices([...])` then `{t["ticker"]: get_current_price(t["ticker"]) for t in open_trades}` (today's calls). `on`: one `freshness.page_quotes(tickers, dashboard=True)`. In `build_open_trade_views` replace the `prefetch_prices(...)` line with `prices = _open_trade_prices(open_trades)` and `price = get_current_price(t["ticker"])` with `price = prices.get(t["ticker"])`. Its CC stays 18.
- `watchlist_rows.py`: `_empty_row` gains `"price_age_s": None, "price_as_of": None`. `build_market_rows` takes `live, quotes = _overlay(tickers)` and builds each row as `_stamp(_market_row(symbol, frames.get(symbol), live.get(symbol)), quotes.get(symbol))`. `_overlay(tickers) -> tuple[dict[str, float], dict[str, QuoteDetail]]` is `(_live_overlay(tickers), {})` unless `freshness.layer_on()`, else `_layer_overlay(tickers)` (market closed -> `({}, {})`; cached entries -> prices and quotes; `warm_quotes_background` for symbols missing or with `entry.age_s() > freshness.page_window_s()`). `_stamp(row, q)` sets the age fields and maps `price_source` only when `q` is given and the row used a live price.

- [ ] **Step 6: Update the row-shape specs and run every admin price test**

Add `"price_age_s": NULLABLE_NUMBER` and `"price_as_of": NULLABLE_STR` to `TRADE_ROW` in `tests/admin/test_api_v1_trades.py`; add the same two keys wherever `tests/admin/test_api_v1_watchlist.py` and `tests/admin/test_watchlist_rows.py` pin the market row (search `"price_source"`).
Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_admin_freshness.py`, then `... file tests/admin/test_api_v1_trades.py`, `... file tests/admin/test_api_v1_watchlist.py`, `... file tests/admin/test_watchlist_rows.py`, `... file tests/admin/test_api_v1_dashboard.py` (if it exists; else every file `git -C $WT grep -l build_open_trade_views -- tests` lists)
Expected: all PASS, `0 failed`; `test_api_v1_watchlist.py`'s under-1-second test still passes.

- [ ] **Step 7: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/admin/freshness.py $WT/swingbot/admin/dashboard.py $WT/swingbot/admin/watchlist_rows.py $WT/swingbot/admin/api_v1/trades.py`
Expected: only the pre-existing `build_open_trade_views - C (18)` (unchanged) and any other pre-existing C lines in `trades.py`, none new.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/admin/freshness.py swingbot/admin/app.py swingbot/admin/dashboard.py swingbot/admin/watchlist_rows.py swingbot/admin/api_v1/trades.py tests/admin/conftest.py tests/admin/test_admin_freshness.py tests/admin/test_api_v1_trades.py tests/admin/test_api_v1_watchlist.py tests/admin/test_watchlist_rows.py
git -C $WT commit -m "feat(admin): v171 reload-fresh header, page quotes through the shared layer with ages (V171-25)"
```

### Task V171-26: Admin chart, risk page, watchlist warm-up and earnings warm-up through the layer

**Model:** sonnet — admin readers, concurrent tabs collapse onto one call

**Files:**
- Modify: `swingbot/admin/freshness.py` (V171-25's module: `page_daily` and its helpers; the ledger row omits this file, but `page_daily` lives there)
- Modify: `swingbot/admin/app.py` (`_ohlcv_frame` :225-244)
- Modify: `swingbot/admin/api_v1/risk.py` (the `get_daily_data_batch(...)` line :281)
- Modify: `swingbot/admin/watchlist_rows.py` (`build_market_rows` cold fetch :160-162)
- Create: `tests/admin/test_admin_layer_readers.py`
- Not modified: `swingbot/admin/api_v1/market.py`. `chart()` and `ohlcv()` import `_ohlcv_frame` from `app` at call time, so routing `_ohlcv_frame` covers both and `market.chart` (CC 24) is untouched.

**Interfaces:**
- Consumes: `freshness.layer_on`, `page_window_s` (V171-25); `daily_delta.read_daily(ticker, basis)`, `daily_delta.BASIS_YF` (V171-12); `layer.lease` (V171-6); `kinds.resolve_asker`, `Asker.ADMIN_PAGE`, `DataKind.DAILY_BARS` (V171-2); `router.asker_scope` (V171-8); `data_refresh.refresh_symbol`, `data_store.update_cache`, `data_store.cache_path`, `data.get_daily_data_batch`, `data.is_us_market_active`, `spot_metals.split_spot` (exist); `events.warm_earnings_cache_background` at `ADMIN_PAGE` (V171-23).
- Produces:
  - `freshness.page_daily(tickers: list[str], *, period: str = "2y") -> dict[str, pd.DataFrame]` (ledger, plus the `period` keyword so each caller keeps today's span): normalised tickers; spot metals keep today's `data.get_daily_data_batch(spot, period=period)`; every other ticker reads the yfinance-basis file through `daily_delta.read_daily(t, basis=daily_delta.BASIS_YF)`, refreshed first when `_daily_stale(t)`; each frame trimmed to `period` (`_PERIOD_DAYS = {"6mo": 183, "1y": 366, "2y": 731, "5y": 1827}` calendar days back from its last bar; an unknown period is not trimmed). A ticker with no frame is absent.
  - `freshness._daily_stale(ticker: str) -> bool`: the file at `data_store.cache_path(ticker, "daily")` is missing, or its mtime age exceeds `page_window_s()` while `data.is_us_market_active()`, else `config.SCAN_CACHE_MAX_AGE_HOURS * 3600` (a fresh reload makes the window 0.0, so a reload refreshes).
  - `freshness._refresh_yf_daily(ticker: str, asker: Asker) -> None`: inside `router.asker_scope(asker)`: a missing file -> `data_refresh.refresh_symbol(ticker, "daily")` (full depth, so a cold file is never seeded shallow); an existing one -> `data_store.update_cache([ticker], "1d")` (incremental union). Any exception (including `BudgetDeferred`) is logged at debug and the file on disk is served.
  - Lease rule per stale ticker: `asker = resolve_asker(Asker.ADMIN_PAGE)`; `with layer.lease(DataKind.DAILY_BARS, t, asker=asker, deadline_s=10.0) as held:` re-read the file, then refresh when still stale and (`held` or the re-read returned None); a lost lease with a file on disk serves that file (another holder just wrote it, or the tier-5 deadline passed: last cached value with its age). The key is the one `daily_delta.write_daily` leases, so admin and bot never write one yfinance file at once. The admin never writes `daily_alpaca`.
- Readers, `on` mode only (each `off`/`count` branch is today's call, unchanged): `app._ohlcv_frame` -> `freshness.page_daily([ticker]).get(ticker)` via `_live_daily(ticker)`; `risk.py` -> `_risk_bars(symbols)` = `freshness.page_daily(symbols)` (2y, today's span); `watchlist_rows.build_market_rows` cold symbols -> `_cold_frames(cold)` = `freshness.page_daily(cold, period="6mo")`. The earnings warm-up (`watchlist._next_earnings` -> `events.warm_earnings_cache_background`) already runs one layer call at `ADMIN_PAGE` since V171-23; this task pins it from the admin side.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_admin_layer_readers.py`:

```python
"""v171 D8: admin chart, risk, watchlist and earnings warm-ups through the layer."""
import contextlib
import os
import threading
import time

import pandas as pd
import pytest

from swingbot import config
from swingbot.admin import freshness, watchlist_rows
from swingbot.core.marketdata import daily_delta, data, data_refresh, data_store
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared import kinds, layer
from swingbot.core.marketdata.shared.kinds import Asker, DataKind
from tests.helpers import make_ohlcv


@pytest.fixture
def env(monkeypatch):
    """on mode; files/staleness/refresh/lease all observable."""
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    st = {"files": {}, "stale": set(), "refreshed": [], "leases": [], "held": True}

    def read(t, basis=None):
        assert basis == daily_delta.BASIS_YF
        return st["files"].get(t)

    def refresh(t, asker):
        st["refreshed"].append((t, asker))
        st["files"][t] = make_ohlcv([100.0 + i for i in range(10)])
        st["stale"].discard(t)

    @contextlib.contextmanager
    def lease(kind, symbol, *, asker, deadline_s=30.0):
        st["leases"].append((kind, symbol, asker))
        yield st["held"]

    monkeypatch.setattr(daily_delta, "read_daily", read)
    monkeypatch.setattr(freshness, "_daily_stale", lambda t: t in st["stale"] or t not in st["files"])
    monkeypatch.setattr(freshness, "_refresh_yf_daily", refresh)
    monkeypatch.setattr(layer, "lease", lease)
    return st


def test_a_fresh_yfinance_file_is_read_with_no_fetch_and_no_lease(env):
    env["files"]["AAPL"] = make_ohlcv([1.0, 2.0])
    assert len(freshness.page_daily(["aapl"])["AAPL"]) == 2
    assert env["refreshed"] == [] and env["leases"] == []


def test_a_missing_file_is_fetched_once_under_the_daily_lease_at_admin_page(env):
    out = freshness.page_daily(["AAPL"])
    assert "AAPL" in out
    assert env["leases"] == [(DataKind.DAILY_BARS, "AAPL", Asker.ADMIN_PAGE)]
    assert env["refreshed"] == [("AAPL", Asker.ADMIN_PAGE)]


def test_a_lost_lease_serves_the_file_on_disk_without_fetching(env):
    env["files"]["AAPL"] = make_ohlcv([1.0, 2.0])
    env["stale"].add("AAPL")
    env["held"] = False
    assert len(freshness.page_daily(["AAPL"])["AAPL"]) == 2 and env["refreshed"] == []


def test_a_lost_lease_with_no_file_still_fetches(env):
    env["held"] = False                                   # failed open, or a holder that wrote nothing
    assert "AAPL" in freshness.page_daily(["AAPL"]) and len(env["refreshed"]) == 1


def test_period_trims_to_todays_span(env):
    env["files"]["AAPL"] = make_ohlcv([100.0] * 600)
    out = freshness.page_daily(["AAPL"], period="6mo")["AAPL"]
    assert out.index[-1] == env["files"]["AAPL"].index[-1]
    assert (out.index[-1] - out.index[0]).days <= 183


def test_spot_keeps_todays_batch_path(env, monkeypatch):
    seen = []
    monkeypatch.setattr(data, "get_daily_data_batch",
                        lambda t, period="2y": seen.append((list(t), period)) or {})
    freshness.page_daily(["XAUUSD"], period="6mo")
    assert seen == [(["XAUUSD"], "6mo")] and env["leases"] == []


def test_refresh_fills_a_missing_file_at_full_depth_and_a_stale_one_incrementally(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(data_store, "cache_path", lambda t, i, base_dir=None: str(tmp_path / f"{t}.csv"))
    monkeypatch.setattr(data_refresh, "refresh_symbol",
                        lambda t, tf: calls.append(("full", t, router.current_asker())))
    monkeypatch.setattr(data_store, "update_cache",
                        lambda syms, interval: calls.append(("delta", syms, interval)))
    freshness._refresh_yf_daily("AAPL", Asker.ADMIN_PAGE)
    (tmp_path / "AAPL.csv").write_text("Date,Close\n")
    freshness._refresh_yf_daily("AAPL", Asker.ADMIN_PAGE)
    assert calls == [("full", "AAPL", Asker.ADMIN_PAGE), ("delta", ["AAPL"], "1d")]


def test_daily_staleness_follows_the_page_window(monkeypatch, tmp_path):
    path = tmp_path / "AAPL.csv"
    path.write_text("Date,Close\n")
    old = time.time() - 120
    os.utime(path, (old, old))
    monkeypatch.setattr(data_store, "cache_path", lambda t, i, base_dir=None: str(path))
    monkeypatch.setattr(config, "QUOTE_MAX_AGE_ADMIN_S", 60)
    monkeypatch.setattr(config, "SCAN_CACHE_MAX_AGE_HOURS", 6)
    monkeypatch.setattr(data, "is_us_market_active", lambda: True)
    assert freshness._daily_stale("AAPL") is True
    monkeypatch.setattr(data, "is_us_market_active", lambda: False)
    assert freshness._daily_stale("AAPL") is False
    with kinds.fresh_request():
        monkeypatch.setattr(data, "is_us_market_active", lambda: True)
        assert freshness._daily_stale("AAPL") is True


def test_chart_risk_and_watchlist_read_page_daily_when_on(admin_app, env, monkeypatch):
    from swingbot.admin import app as app_mod
    from swingbot.admin.api_v1 import risk
    asked = []
    monkeypatch.setattr(freshness, "page_daily",
                        lambda t, period="2y": asked.append((list(t), period)) or {s: make_ohlcv([1.0, 2.0]) for s in t})
    monkeypatch.setattr(data, "get_daily_data", lambda *a, **k: pytest.fail("live chart fetch"))
    monkeypatch.setattr(data, "get_daily_data_batch", lambda *a, **k: pytest.fail("live batch fetch"))
    monkeypatch.setattr(watchlist_rows, "get_daily_data_batch", lambda *a, **k: pytest.fail("live batch fetch"))
    monkeypatch.setattr(watchlist_rows, "_cached_daily", lambda t: None)
    monkeypatch.setattr(watchlist_rows, "is_us_market_active", lambda: False)
    assert len(app_mod._ohlcv_frame("AAPL")) == 2
    assert set(risk._risk_bars(["AAPL", "SPY"])) == {"AAPL", "SPY"}
    watchlist_rows.build_market_rows(["MSFT"])
    assert asked == [(["AAPL"], "2y"), (["AAPL", "SPY"], "2y"), (["MSFT"], "6mo")]


def test_off_mode_keeps_the_live_readers(admin_app, monkeypatch):
    from swingbot.admin import app as app_mod
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(freshness, "page_daily", lambda *a, **k: pytest.fail("layer used"))
    monkeypatch.setattr(data, "get_daily_data", lambda t: make_ohlcv([5.0, 6.0, 7.0]))
    assert len(app_mod._ohlcv_frame("AAPL")) == 3


def test_the_watchlist_earnings_warm_up_runs_at_admin_page(admin_app, monkeypatch):
    from swingbot.admin.api_v1 import watchlist
    from swingbot.core.market import events
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    done, seen = threading.Event(), []

    def docs(tickers, *, asker, max_age_s=None):
        seen.append((list(tickers), asker))
        done.set()
        return {}
    monkeypatch.setattr(events, "_earnings_docs", docs)
    monkeypatch.setattr(events, "_never_reports", lambda t: False)
    events._earnings_datetime_cache.clear()
    watchlist._next_earnings(["AAPL", "MSFT"])
    assert done.wait(5) and seen == [(["AAPL", "MSFT"], Asker.ADMIN_PAGE)]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_admin_layer_readers.py`
Expected: FAIL (`AttributeError: module 'swingbot.admin.freshness' has no attribute 'page_daily'` / `'_daily_stale'`; `risk` has no `_risk_bars`). `test_the_watchlist_earnings_warm_up_runs_at_admin_page` already passes if V171-23 is in; it stays as the admin-side pin.

- [ ] **Step 3: Implement `page_daily` and its helpers in `freshness.py`**

Per the Interfaces block; each helper a few lines (`_daily_for(t)` holds the read / lease / refresh rule for one ticker, `_trim(df, period)` the span). Import `daily_delta`, `data`, `data_refresh`, `data_store`, `layer`, `router`, `spot_metals` inside the functions and call through the module attributes (the tests patch them there).

- [ ] **Step 4: Route the three readers**

- `app.py`: split the try-body of `_ohlcv_frame` into `_live_daily(ticker)`: `on` -> `freshness.page_daily([ticker]).get(ticker.upper().strip())`; otherwise today's `from swingbot.core.marketdata.data import get_daily_data; return get_daily_data(ticker)`. The backtest-cache fallback below stays.
- `risk.py`: `bars = _risk_bars(sorted(set(symbols) | {benchmark})) if symbols else {}` with `_risk_bars(symbols) -> dict`: `on` -> `freshness.page_daily(symbols)`, otherwise today's `get_daily_data_batch(symbols)`.
- `watchlist_rows.py`: `fetched = _cold_frames(cold) if cold else {}` with `_cold_frames(cold) -> dict`: `on` -> `freshness.page_daily(cold, period="6mo")`, otherwise today's `get_daily_data_batch(cold, period="6mo")`.

- [ ] **Step 5: Run the tests to verify they pass, with the admin readers' suites**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_admin_layer_readers.py`, then `... file tests/admin/test_api_v1_market.py`, `... file tests/admin/test_api_v1_watchlist.py`, `... file tests/admin/test_watchlist_rows.py`, `... file tests/admin/test_admin_freshness.py`, and every file `git -C $WT grep -l "risk" -- tests/admin` lists that hits `/api/v1/risk`
Expected: all PASS, `0 failed`.

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/admin/freshness.py $WT/swingbot/admin/app.py $WT/swingbot/admin/api_v1/risk.py $WT/swingbot/admin/watchlist_rows.py`
Expected: no new line (any pre-existing risk-view grade unchanged).

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/admin/freshness.py swingbot/admin/app.py swingbot/admin/api_v1/risk.py swingbot/admin/watchlist_rows.py tests/admin/test_admin_layer_readers.py
git -C $WT commit -m "feat(admin): v171 chart, risk and watchlist bars from the shared yfinance cache under one lease (V171-26)"
```

### Task V171-27: D1 guard test with a frozen allowlist; architecture and known-traps docs; AGENTS.md mirror

**Model:** sonnet — an AST guard in the existing pattern plus doc rows

**Files:**
- Create: `tests/marketdata/test_fetch_layer_guard.py`
- Modify: `docs/claude/architecture.md` (new section after `## Module map`)
- Modify: `docs/claude/known-traps.md` (new section at the end)
- Modify: `AGENTS.md` (Codex mirror, same commit, under its 32 KiB cap)

**Interfaces:**
- Consumes: the code as V171-6..V171-26 left it (this task runs after 9, 12, 13, 16, 23, 24, 26).
- Produces: `ALLOWED` (frozenset of repo-relative POSIX paths; a directory entry ends in `/`), `_violations(path: Path) -> list[str]`. The guard flags, per file under `swingbot/`: `import yfinance` / `import alpaca...`, `from yfinance...` / `from alpaca...`, `from ...yf_safe import download`, and any `yf_safe.download` attribute. `yf.<x>` needs an import, so the import check covers it. `scripts/`, `bot.py` and `admin_ui.py` are out of scope (spec D1).

- [ ] **Step 1: Take the inventory**

Run: `git -C $WT grep -nE "^\s*(import (yfinance|alpaca)|from (yfinance|alpaca))|yf_safe\.download|yf_safe import download" -- swingbot`
Expected: matches only in the files below. Each belongs to a permitted category: the layer, the providers, the yfinance wrapper, a provider-function module the layer's `fetch` callables or `lease` holders call, or a research module out of scope (spec D3). Add an entry only for a file that is in a permitted category and is missing below (for example `data_refresh.py` if V171-16 batched with `yf_safe.download` directly), with its reason. **A file outside every category is a call site V171-23..V171-26 missed: stop and report it to the controller; do not allowlist it.**

- [ ] **Step 2: Write the guard**

Create `tests/marketdata/test_fetch_layer_guard.py`:

```python
"""v171 D1/D8: every Alpaca and yfinance request in swingbot/ goes through the
shared layer. A provider call lives in a provider function the layer calls;
this guard fails any direct import or download anywhere else."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ALLOWED = frozenset({
    "swingbot/core/marketdata/shared/",            # the layer itself (the tape feed's Yahoo download)
    "swingbot/core/marketdata/providers/",         # alpaca-py is imported only here
    "swingbot/core/marketdata/yf_safe.py",         # the serialised, budgeted yfinance wrapper
    "swingbot/core/marketdata/data.py",            # quote, daily-batch and metadata provider functions
    "swingbot/core/marketdata/data_store.py",      # yfinance-basis daily and intraday writers (leased)
    "swingbot/core/marketdata/daily_delta.py",     # D4 window and full fetch on the yfinance basis
    "swingbot/core/market/events.py",              # earnings provider functions behind layer.get
    "swingbot/core/marketdata/backtest_cache.py",  # research cache: backtests are out of scope (spec D3)
    "swingbot/core/marketdata/export_data.py",     # research export: out of scope (spec D3)
})


def _provider_module(name: str) -> bool:
    return name.split(".")[0] in {"yfinance", "alpaca"}


def _violations(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names if _provider_module(a.name)]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if _provider_module(node.module):
                found.append(f"from {node.module}")
            elif node.module.endswith("yf_safe") and any(a.name == "download" for a in node.names):
                found.append("from yf_safe import download")
        elif (isinstance(node, ast.Attribute) and node.attr == "download"
              and isinstance(node.value, ast.Name) and node.value.id == "yf_safe"):
            found.append(f"yf_safe.download at line {node.lineno}")
    return found


def _allowed(rel: str) -> bool:
    return any(rel == a or (a.endswith("/") and rel.startswith(a)) for a in ALLOWED)


def test_no_provider_call_outside_the_layer():
    offenders = {}
    for path in sorted((ROOT / "swingbot").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if not _allowed(rel) and (hits := _violations(path)):
            offenders[rel] = hits
    assert offenders == {}, (
        "Direct Alpaca/yfinance use outside the shared layer (spec v171 D1). Route it "
        f"through swingbot/core/marketdata/shared (layer.get or layer.lease): {offenders}")


def test_every_allowlisted_file_still_needs_its_entry():
    for entry in ALLOWED:
        path = ROOT / entry
        assert path.exists(), f"stale allowlist entry {entry}"
        if path.is_file():
            assert _violations(path), f"{entry} no longer calls a provider: drop it from ALLOWED"


def test_the_guard_sees_every_form(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import yfinance as yf\n"
        "from alpaca.data.historical import StockHistoricalDataClient\n"
        "from swingbot.core.marketdata.yf_safe import download\n"
        "from swingbot.core.marketdata import yf_safe\n"
        "yf_safe.download('AAPL')\n", encoding="utf-8")
    assert len(_violations(sample)) == 4
```

- [ ] **Step 3: Run it**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_fetch_layer_guard.py`
Expected: PASS, `3 passed`. If `test_no_provider_call_outside_the_layer` lists a file, apply Step 1's rule (permitted category -> add with a reason; otherwise stop and report). If `test_every_allowlisted_file_still_needs_its_entry` fails, drop that entry.

- [ ] **Step 4: Document the layer in `docs/claude/architecture.md`**

Insert after the `## Module map` section:

```markdown
## Shared market-data layer (v171)

Every Alpaca and yfinance request in `swingbot/` (bot, spawned `_run_bounded` workers, admin) goes through `swingbot/core/marketdata/shared/`: `kinds.py` (data kinds; askers with priority 1-5 and freshness windows), `layer.py` (`get`: Postgres cache, cross-process lease single-flight, batching; `lease`: bar writers), `budget.py` (one token bucket per provider shared by every process, tier reserves 0/0/0/25 %/50 %, shared breaker), `counters.py` (D9 hourly counts in `market_fetch_counts`) and `tape.py` (the bot's index tape feed). Its tables (`market_cache`, `provider_budget`, `market_fetch_counts`) are reached only through `core/db/repositories/market_shared.py` over `core/db/side_engine.py` (autocommit, 250 ms statement timeout), and every touch fails open. Provider calls stay in provider functions (`providers/`, `yf_safe.py`, `data.py`, `data_store.py`, `daily_delta.py`, `events.py`), which take their budget token at the call site at `router.current_asker()`; `tests/marketdata/test_fetch_layer_guard.py` fails any direct use elsewhere. The D5 rebuild is `core/planning/rebuild.py`, fed by `core/scanning/requote.py`. The admin's reload mark and page readers are `swingbot/admin/freshness.py`. Flags: `MARKETDATA_LAYER` (`off`/`count`/`on`), `DAILY_DELTA_FETCH`, `PLAN_REBUILD_ENABLED`, `TAPE_SHARED_ENABLED`; each off restores the pre-v171 path. Traps: `known-traps.md` § Shared market-data layer.
```

- [ ] **Step 5: Add the traps to `docs/claude/known-traps.md`**

Append:

```markdown
## Shared market-data layer: one door, two daily caches (v171)

- **A new provider call goes through the layer**: a provider function the layer's `fetch` calls, or a `layer.lease` around a bar writer. Never `import yfinance`/`alpaca` or call `yf_safe.download` anywhere else in `swingbot/`; the guard test's allowlist needs a reason line per entry.
- **Budget tokens are taken where the provider is called**, at `router.current_asker()`. A contextvar does not cross `_run_bounded`'s spawned process: enter `router.asker_scope(asker)` inside the worker. Unscoped code runs as `SCAN` (tier 3), so admin code always names its asker.
- **`max_age_s=0.0` means never from cache** (test `is not None`, never truthiness). `METADATA` is persistent for every asker, a fresh admin reload included.
- **A `None` in a fetch reply is a miss and is never written**, so a blank reply never overwrites the last good value. A confirmed empty answer is an empty doc, not `None`.
- **Two daily caches, one adjustment basis each.** `market_data/daily_alpaca/` is Alpaca `Adjustment.ALL`, 10 years, written only by `daily_delta.write_daily` under the key's lease; `market_data/daily/` is yfinance `auto_adjust`, full history, written by its existing yfinance writers. Never splice or write a frame across them. The admin reads only the yfinance file (`freshness.page_daily`). Each file has a `.meta.json` sidecar; a failed D4 delta check means a full refetch, never `history_splice`'s shallow live-only path.
- **`count` mode is the D9 baseline**: it must make exactly today's provider calls. Anything that shares or caches belongs behind `on`.
- **The admin's fresh mark** (`X-Swingbot-Fresh: 1`) lasts one request (`freshness.install`); a background thread keeps it only through `contextvars.copy_context()`.
```

- [ ] **Step 6: Mirror into `AGENTS.md` without growing it**

In the read-before list, replace the `known-traps.md` bullet with:

```markdown
- `known-traps.md`: data caching (v171: every provider call goes through
  `core/marketdata/shared/`, guard test), scan output, embeds, the 2% stop
  cap/clamp, the liquidity floor, production `.env` (never `sed -i`).
```

and in `## Efficient repository navigation`, condense the `doc_section.py` bullet's parenthesis to `prints the named sections (case-insensitive heading prefix; none lists them).` Then measure:

Run: `wc -c $WT/AGENTS.md` and `python $WT/scripts/dev/testrun.py file tests/scout/test_generator_roles.py` and `... file tests/hooks/test_codex_mirror.py`
Expected: byte count at most 32762 (today's CRLF size, under the 32 KiB cap); both files PASS. If it is still over, condense another sentence of the same section without dropping a rule.

- [ ] **Step 7: Commit (docs and mirror together)**

```bash
git -C $WT add tests/marketdata/test_fetch_layer_guard.py docs/claude/architecture.md docs/claude/known-traps.md AGENTS.md
git -C $WT commit -m "test(marketdata): v171 D1 guard, one door for provider calls; architecture, traps and AGENTS mirror (V171-27)"
```

### Task V171-28: Bot tape feed loop: fixed tape plus admin demand, Yahoo indices with Alpaca change-% proxies, blank never overwrites

**Model:** opus — new loop spanning `commands`, `marketdata` and the shared cache

**Files:**
- Create: `swingbot/core/marketdata/shared/tape.py`
- Modify: `swingbot/commands/scanning/loops.py` (new `tape_feed` after V171-15's `daily_reanchor`; `_always_on_loops()` appends it last)
- Modify: `tests/commands/test_daily_reanchor_loop.py` (its last assertion, as V171-15 foresaw)
- Create: `tests/marketdata/test_shared_tape.py`, `tests/commands/test_tape_feed_loop.py`

**Interfaces:**
- Consumes: `layer.get`, `layer.last_cached` (V171-6); `DataKind.INDEX_QUOTE`, `PROVIDER_YF`, `Asker`, `Entry`, `cache_key` (V171-2); `side_connection`, `market_shared_repo().read_entries / write_entries` (V171-3); `counters.warn_fail_open` (V171-4); `router.asker_scope`, `router.current_asker` (V171-8); `yf_safe.download`, `yf_safe.DownloadBusy`, `yf_safe.BudgetDeferred`; `data.get_quote_batch` (V171-9), `data.get_daily_data_batch`, `data.is_us_market_active`; `session.market_today`; config `TAPE_PROXY_SYMBOLS`, `TAPE_SHARED_ENABLED`, `MARKETDATA_LAYER`.
- Produces (`shared/tape.py`; V171-29 consumes):
  - `TAPE_FIXED = ("^GSPC", "^NDX", "^DJI", "^VIX")`; `DEMAND_TTL_S = 15 * 60`; `DEMAND_KEY = cache_key(DataKind.INDEX_QUOTE, "tape-demand")` (`"index:TAPE-DEMAND:"`).
  - `proxy_map() -> dict[str, str]`: parses `TAPE_PROXY_SYMBOLS` at call time; each entry splits on its **last** `=` (`SI=F=SLV` -> `SI=F` -> `SLV`); both sides upper-cased; malformed entries skipped.
  - `is_tape_symbol(symbol: str) -> bool` (added beside the ledger API): in `TAPE_FIXED` or a `proxy_map()` key. **Symbols with no proxy** (any flagged symbol that is not a tape symbol, for example `^RUT`, `GC=F`, `ASML.AS`, and every Alpaca-served stock) keep today's admin `tape_cache` path (V171-29).
  - `@dataclass(frozen=True) class TapeEntry: symbol: str; price: float | None; change_pct: float | None; is_proxy: bool; proxy_symbol: str | None; as_of: datetime | None` (ledger). `as_of` is the cache entry's `fetched_at`.
  - `record_demand(symbols: list[str]) -> None`: keeps only tape symbols outside `TAPE_FIXED`; `on` mode only; reads the demand row, and writes `{symbol: now ISO}` merged with entries younger than `DEMAND_TTL_S` only when some symbol is missing or stamped more than 60 s ago (so an admin poll is not a write per request). Row: `{"key": DEMAND_KEY, "kind": "index", "symbol": "TAPE-DEMAND", "fetched_at": now, "source": "admin", "value": {...}}`. Fails open via `counters.warn_fail_open("tape-demand", exc)`.
  - `demanded_symbols(now: datetime) -> list[str]` (ledger): `TAPE_FIXED` plus demand entries younger than `DEMAND_TTL_S` that are still tape symbols, order kept, de-duplicated; on any error, `TAPE_FIXED` only.
  - `refresh_tape(symbols: list[str], *, asker: Asker = Asker.BACKGROUND, max_age_s: float | None = None) -> dict[str, TapeEntry]` (ledger, plus `max_age_s`): tape symbols only, inside `router.asker_scope(asker)`, one `layer.get(DataKind.INDEX_QUOTE, syms, _fetch_tape, asker=asker, provider=PROVIDER_YF, max_age_s=max_age_s)`.
  - `read_tape(symbols: list[str]) -> dict[str, TapeEntry]` (ledger): one `layer.last_cached(DataKind.INDEX_QUOTE, syms)`, any age; never fetches.
  - `_fetch_tape(symbols) -> dict[str, dict | None]`: one `yf_safe.download(" ".join(symbols), period="5d", interval="1d", group_by="ticker", auto_adjust=False, progress=False)`; per symbol, the last two non-NaN closes give `price` (the last) and `change_pct` (`round((last / prev - 1) * 100, 2)`), doc `{"symbol", "price", "change_pct", "is_proxy": False, "proxy_symbol": None}`. `BudgetDeferred` propagates (the layer keeps the last good values); `DownloadBusy` or any other error counts every symbol as Yahoo-blank. Yahoo-blank symbols with a proxy get `_proxy_changes`: one `data.get_quote_batch(proxies, asker=router.current_asker())` and one `data.get_daily_data_batch(proxies, period="5d")`; the proxy price is the quote's `price`, else its `mid()`; previous close = the last bar dated before `market_today()`; doc `{"symbol", "price": None, "change_pct", "is_proxy": True, "proxy_symbol"}` (change % only, never a level). Anything else is `None`: a miss, never written, so the last good value stays and its age grows.
- `loops.tape_feed` (`@tasks.loop(seconds=60)`, ledger): no-op unless `TAPE_SHARED_ENABLED`, `MARKETDATA_LAYER == "on"` and `data.is_us_market_active()`; otherwise `await asyncio.to_thread(_tape_feed_tick)` inside `try/except: log.exception`. `_tape_feed_tick() -> None` calls `tape.refresh_tape(tape.demanded_symbols(now_utc), asker=Asker.BACKGROUND, max_age_s=_TAPE_FEED_MAX_AGE_S)` with `_TAPE_FEED_MAX_AGE_S = 30.0` (half the period: each tick refetches, and a second process ticking at once shares the fetch).

- [ ] **Step 1: Write the failing module tests**

Create `tests/marketdata/test_shared_tape.py`:

```python
"""v171 D7: the index tape, Yahoo levels with labelled change-%-only ETF proxies."""
import contextlib
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata.shared import layer, tape
from swingbot.core.marketdata.shared.kinds import PROVIDER_YF, Asker, DataKind, Entry, QuoteDetail

NOW = datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc)


def _yahoo(closes: dict) -> pd.DataFrame:
    idx = pd.bdate_range("2026-10-15", periods=2)
    return pd.DataFrame({(s, "Close"): v for s, v in closes.items()}, index=idx)


@pytest.fixture(autouse=True)
def proxies(monkeypatch):
    monkeypatch.setattr(config, "TAPE_PROXY_SYMBOLS", "^GSPC=SPY,^NDX=QQQ,^DJI=DIA,^VIX=VIXY,SI=F=SLV")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")


def test_proxy_map_splits_on_the_last_equals_sign(monkeypatch):
    assert tape.proxy_map() == {"^GSPC": "SPY", "^NDX": "QQQ", "^DJI": "DIA", "^VIX": "VIXY", "SI=F": "SLV"}
    monkeypatch.setattr(config, "TAPE_PROXY_SYMBOLS", "^gspc=spy,broken,,")
    assert tape.proxy_map() == {"^GSPC": "SPY"}


def test_tape_symbols_are_the_fixed_tape_and_the_proxy_map():
    assert all(tape.is_tape_symbol(s) for s in ("^GSPC", "^VIX", "SI=F"))
    assert not tape.is_tape_symbol("NVDA") and not tape.is_tape_symbol("^RUT")


def test_yahoo_rows_carry_level_and_change(monkeypatch):
    monkeypatch.setattr(tape.yf_safe, "download", lambda *a, **k: _yahoo({"^GSPC": [100.0, 102.0]}))
    assert tape._fetch_tape(["^GSPC"]) == {"^GSPC": {"symbol": "^GSPC", "price": 102.0, "change_pct": 2.0,
                                                     "is_proxy": False, "proxy_symbol": None}}


def test_a_blank_yahoo_symbol_shows_its_proxy_change_only(monkeypatch):
    monkeypatch.setattr(tape.yf_safe, "download",
                        lambda *a, **k: _yahoo({"^GSPC": [float("nan"), float("nan")]}))
    monkeypatch.setattr(tape, "market_today", lambda: date(2026, 10, 16))
    q = QuoteDetail("SPY", 505.0, NOW, None, None, None, "alpaca-iex")
    monkeypatch.setattr(tape.data, "get_quote_batch", lambda t, *, asker, **k: {"SPY": q})
    bars = pd.DataFrame({"Close": [500.0, 503.0]}, index=pd.to_datetime(["2026-10-15", "2026-10-16"]))
    monkeypatch.setattr(tape.data, "get_daily_data_batch", lambda t, period: {"SPY": bars})
    row = tape._fetch_tape(["^GSPC"])["^GSPC"]
    assert row == {"symbol": "^GSPC", "price": None, "change_pct": 1.0, "is_proxy": True, "proxy_symbol": "SPY"}


def test_blank_everywhere_is_a_miss_so_the_last_good_value_stays(monkeypatch):
    def busy(*a, **k):
        raise tape.yf_safe.DownloadBusy("busy")
    monkeypatch.setattr(tape.yf_safe, "download", busy)
    monkeypatch.setattr(tape.data, "get_quote_batch", lambda t, *, asker, **k: {})
    monkeypatch.setattr(tape.data, "get_daily_data_batch", lambda t, period: {})
    assert tape._fetch_tape(["^VIX"]) == {"^VIX": None}


def test_a_short_budget_propagates_to_the_layer(monkeypatch):
    def deferred(*a, **k):
        raise tape.yf_safe.BudgetDeferred("tier 5")
    monkeypatch.setattr(tape.yf_safe, "download", deferred)
    with pytest.raises(tape.yf_safe.BudgetDeferred):
        tape._fetch_tape(["^GSPC"])


def test_refresh_is_one_index_layer_call_for_tape_symbols_only(monkeypatch):
    calls = []

    def fake_get(kind, symbols, fetch, **kw):
        calls.append((kind, list(symbols), kw["asker"], kw["provider"], kw["max_age_s"]))
        return {s: Entry({"symbol": s, "price": 1.0, "change_pct": 0.5, "is_proxy": False,
                          "proxy_symbol": None}, NOW, "yfinance", "fetched") for s in symbols}
    monkeypatch.setattr(layer, "get", fake_get)
    out = tape.refresh_tape(["^GSPC", "NVDA", "SI=F"], max_age_s=30.0)
    assert calls == [(DataKind.INDEX_QUOTE, ["^GSPC", "SI=F"], Asker.BACKGROUND, PROVIDER_YF, 30.0)]
    assert out["^GSPC"].as_of == NOW and out["^GSPC"].change_pct == 0.5


def test_read_tape_returns_the_last_good_value_with_its_time(monkeypatch):
    doc = {"symbol": "^VIX", "price": None, "change_pct": -3.1, "is_proxy": True, "proxy_symbol": "VIXY"}
    monkeypatch.setattr(layer, "last_cached", lambda kind, syms, params="": {"^VIX": Entry(doc, NOW, "yfinance", "hit")})
    entry = tape.read_tape(["^VIX"])["^VIX"]
    assert entry == tape.TapeEntry("^VIX", None, -3.1, True, "VIXY", NOW)


@pytest.fixture
def demand_store(monkeypatch):
    rows = {}

    class Repo:
        def read_entries(self, keys, *, conn):
            return {k: rows[k] for k in keys if k in rows}

        def write_entries(self, new, *, conn):
            rows.update({r["key"]: r for r in new})
    monkeypatch.setattr(tape, "market_shared_repo", lambda: Repo())
    monkeypatch.setattr(tape, "side_connection", contextlib.nullcontext)
    return rows


def test_demand_is_recorded_for_proxy_symbols_and_expires(demand_store, monkeypatch):
    monkeypatch.setattr(tape, "_now", lambda: NOW)
    tape.record_demand(["SI=F", "NVDA", "^GSPC"])
    assert list(demand_store[tape.DEMAND_KEY]["value"]) == ["SI=F"]
    assert tape.demanded_symbols(NOW + timedelta(minutes=5)) == [*tape.TAPE_FIXED, "SI=F"]
    assert tape.demanded_symbols(NOW + timedelta(minutes=16)) == list(tape.TAPE_FIXED)


def test_a_recent_demand_is_not_rewritten_every_poll(demand_store, monkeypatch):
    monkeypatch.setattr(tape, "_now", lambda: NOW)
    tape.record_demand(["SI=F"])
    stamp = demand_store[tape.DEMAND_KEY]["fetched_at"]
    monkeypatch.setattr(tape, "_now", lambda: NOW + timedelta(seconds=20))
    tape.record_demand(["SI=F"])
    assert demand_store[tape.DEMAND_KEY]["fetched_at"] == stamp


def test_a_down_demand_store_fails_open(monkeypatch):
    def broken():
        raise RuntimeError("db down")
    monkeypatch.setattr(tape, "side_connection", broken)
    tape.record_demand(["SI=F"])
    assert tape.demanded_symbols(NOW) == list(tape.TAPE_FIXED)
```

- [ ] **Step 2: Write the failing loop tests**

Create `tests/commands/test_tape_feed_loop.py`:

```python
"""v171 D7: the bot feeds the shared tape once a minute in session."""
import asyncio

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.marketdata import data
from swingbot.core.marketdata.shared import tape
from swingbot.core.marketdata.shared.kinds import Asker


@pytest.fixture
def feed(monkeypatch):
    monkeypatch.setattr(config, "TAPE_SHARED_ENABLED", True)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(data, "is_us_market_active", lambda: True)
    monkeypatch.setattr(tape, "demanded_symbols", lambda now: ["^GSPC", "SI=F"])
    calls = []
    monkeypatch.setattr(tape, "refresh_tape",
                        lambda syms, *, asker, max_age_s=None: calls.append((syms, asker, max_age_s)) or {})
    return calls


def _tick():
    asyncio.run(loops_mod.tape_feed.coro())


def test_one_refresh_per_tick_at_the_background_tier(feed):
    _tick()
    assert feed == [(["^GSPC", "SI=F"], Asker.BACKGROUND, 30.0)]


@pytest.mark.parametrize("attr,value", [("TAPE_SHARED_ENABLED", False), ("MARKETDATA_LAYER", "count")])
def test_flag_off_or_layer_not_on_does_nothing(feed, monkeypatch, attr, value):
    monkeypatch.setattr(config, attr, value)
    _tick()
    assert feed == []


def test_out_of_session_does_nothing(feed, monkeypatch):
    monkeypatch.setattr(data, "is_us_market_active", lambda: False)
    _tick()
    assert feed == []


def test_a_failed_refresh_is_logged_not_raised(feed, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(tape, "refresh_tape", boom)
    _tick()
    assert "tape_feed" in caplog.text


def test_registered_last_after_the_reanchor_loop():
    loops = loops_mod._always_on_loops()
    assert loops[-1] is loops_mod.tape_feed
    assert loops.index(loops_mod.daily_reanchor) < loops.index(loops_mod.tape_feed)
```

In `tests/commands/test_daily_reanchor_loop.py`, replace the last assertion of `test_registered_as_an_always_on_loop` with `assert loops.index(loops_mod.daily_reanchor) < loops.index(loops_mod.tape_feed)`.

- [ ] **Step 3: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_tape.py`, then `... file tests/commands/test_tape_feed_loop.py`
Expected: FAIL with `ImportError: cannot import name 'tape'` and `AttributeError: ... 'tape_feed'`.

- [ ] **Step 4: Implement `shared/tape.py`**

Per the Interfaces block. Module-level imports the tests patch: `from swingbot.core.marketdata import data, yf_safe`, `from swingbot.core.marketdata.providers import router`, `from swingbot.core.marketdata.shared import counters, layer`, `from swingbot.core.db.side_engine import side_connection`, `from swingbot.core.db.repositories.market_shared import market_shared_repo`, `from swingbot.core.market.session import market_today`, and `_now = lambda: datetime.now(timezone.utc)` (named function). Keep helpers small: `_close_pair(raw, symbol) -> tuple[float, float] | None` (the `(symbol, "Close")` column of the multi-index frame, `raw["Close"]` for a flat one, last two non-NaN closes, both > 0), `_yahoo_docs(symbols)`, `_proxy_changes(symbols) -> dict[str, tuple[str, float]]`, `_prev_close(frame) -> float | None`, `_read_demand(conn) -> dict[str, str]`, `_entry(sym, e: Entry) -> TapeEntry`. `record_demand` and `demanded_symbols` do nothing with Postgres unless `MARKETDATA_LAYER == "on"`.

- [ ] **Step 5: Add the loop in `loops.py`**

Add `_TAPE_FEED_MAX_AGE_S = 30.0`, `_tape_feed_tick()` and `tape_feed` per the Interfaces block after `daily_reanchor`, importing `data`, `tape` and `Asker` inside the functions (call `tape.refresh_tape`, `tape.demanded_symbols` and `data.is_us_market_active` through the modules). The log line in the except branch is `log.exception("tape_feed: refresh failed")`. Append `tape_feed` as the last member of `_always_on_loops()`. The docstring says the loop feeds the admin's tape from one shared copy (spec D7) and that the admin self-fetches when the copy is older than `TAPE_STALE_FALLBACK_S`.

- [ ] **Step 6: Run the tests to verify they pass, with the loop suites**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_shared_tape.py`, `... file tests/commands/test_tape_feed_loop.py`, `... file tests/commands/test_daily_reanchor_loop.py`, `... file tests/commands/test_scheduled_jobs.py`
Expected: all PASS, `0 failed`.

- [ ] **Step 7: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/shared/tape.py $WT/swingbot/commands/scanning/loops.py`
Expected: only the pre-existing `_session_scan_tick - C (15)`.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/core/marketdata/shared/tape.py swingbot/commands/scanning/loops.py tests/marketdata/test_shared_tape.py tests/commands/test_tape_feed_loop.py tests/commands/test_daily_reanchor_loop.py
git -C $WT commit -m "feat(tape): v171 D7 bot feeds the shared index tape with labelled change-% proxies (V171-28)"
```

### Task V171-29: Admin tape reads the shared copy; self-fetch at tier 5 after 3 min stale; proxy and age fields

**Model:** sonnet — one admin view and its tests

**Files:**
- Modify: `swingbot/admin/api_v1/market.py` (`tape()` :654-717: two lines change, new helpers above it)
- Modify: `swingbot/admin/tape_cache.py` (`prices` :102-104)
- Modify: `tests/admin/test_api_v1_tape.py` (new tests at the end)

**Interfaces:**
- Consumes: `tape.is_tape_symbol`, `record_demand`, `read_tape`, `refresh_tape`, `TapeEntry` (V171-28); `Asker.ADMIN_PAGE` (V171-2); config `TAPE_SHARED_ENABLED`, `MARKETDATA_LAYER`, `TAPE_STALE_FALLBACK_S`.
- Produces: every `/api/v1/market/tape` row gains `is_proxy: bool`, `proxy_symbol: str | None`, `age_s: float | None` (ledger; defaults `False, None, None`, also on the flag-off path). Helpers in `market.py`: `_tape_shared() -> bool` (`TAPE_SHARED_ENABLED and MARKETDATA_LAYER == "on"`); `_tape_quotes(symbols) -> tuple[dict, dict, dict]` (prices, change %, extras) = `_tape_quotes_direct(symbols)` when not shared, else `_shared_tape_quotes(symbols)`; `_tape_quotes_direct` is today's `tape_cache.prices` + `tape_cache.daily_frames` + `_tape_change_pct`, unchanged; `_shared_tape_quotes` sends non-tape symbols through `_tape_quotes_direct` and tape symbols through `tape.record_demand`, `tape.read_tape` and, for any missing or older than `TAPE_STALE_FALLBACK_S`, one `_tape_self_fetch(stale)`; a proxy row is `price=None`, `change_pct` set. `_tape_self_fetch(symbols) -> threading.Thread | None` starts one daemon thread running `_run_tape_self_fetch(symbols)` (`tape.refresh_tape(symbols, asker=Asker.ADMIN_PAGE)`, errors logged) unless `_SELF_FETCH_LOCK` (a `threading.Lock`, taken non-blocking, released by the thread) is held; the response never waits for it (D7: keep showing the last good value with its age meanwhile). The tape ignores the fresh mark (D7: admin tabs read the shared copy). `tape_cache.prices` passes `asker=Asker.ADMIN_PAGE` to `get_current_price_batch` unless `MARKETDATA_LAYER == "off"` (so admin tape prices never run at the default scan tier; `off` calls it exactly as today).

- [ ] **Step 1: Write the failing tests**

Append to `tests/admin/test_api_v1_tape.py`:

```python
# --- v171 D7: the shared tape --------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402


@pytest.fixture
def shared(monkeypatch):
    from swingbot import config
    from swingbot.admin.api_v1 import market
    from swingbot.core.marketdata.shared import tape
    monkeypatch.setattr(config, "TAPE_SHARED_ENABLED", True)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "TAPE_STALE_FALLBACK_S", 180)
    st = {"entries": {}, "demand": [], "self_fetch": []}
    monkeypatch.setattr(tape, "read_tape", lambda syms: {s: st["entries"][s] for s in syms if s in st["entries"]})
    monkeypatch.setattr(tape, "record_demand", lambda syms: st["demand"].append(list(syms)))
    monkeypatch.setattr(market, "_tape_self_fetch", lambda syms: st["self_fetch"].append(list(syms)))
    return st


def _entry(symbol, age_s, **kw):
    from swingbot.core.marketdata.shared import tape
    fields = {"price": 5800.0, "change_pct": 0.4, "is_proxy": False, "proxy_symbol": None, **kw}
    return tape.TapeEntry(symbol=symbol, as_of=datetime.now(timezone.utc) - timedelta(seconds=age_s), **fields)


def _tape_row(client, symbols):
    return client.get(f"/api/v1/market/tape?symbols={symbols}").get_json()["rows"][0]


def test_shared_tape_rows_carry_the_proxy_label_and_age(logged_in, shared):
    shared["entries"]["^GSPC"] = _entry("^GSPC", 20, price=None, change_pct=0.8, is_proxy=True, proxy_symbol="SPY")
    with patch("swingbot.core.marketdata.data.get_current_price_batch", side_effect=AssertionError("Yahoo call")):
        row = _tape_row(logged_in, "^GSPC")
    assert row["price"] is None and row["change_pct"] == 0.8
    assert row["is_proxy"] is True and row["proxy_symbol"] == "SPY" and 18 <= row["age_s"] <= 25
    assert shared["self_fetch"] == [] and shared["demand"] == [["^GSPC"]]


def test_a_stale_shared_entry_keeps_its_value_and_self_fetches_in_the_background(logged_in, shared):
    shared["entries"]["^GSPC"] = _entry("^GSPC", 400)
    row = _tape_row(logged_in, "^GSPC")
    assert row["price"] == 5800.0 and 395 <= row["age_s"] <= 410
    assert shared["self_fetch"] == [["^GSPC"]]


def test_an_empty_shared_cache_renders_a_null_row_not_an_error(logged_in, shared):
    resp = logged_in.get("/api/v1/market/tape?symbols=^VIX")
    row = resp.get_json()["rows"][0]
    assert resp.status_code == 200 and row["symbol"] == "^VIX"
    assert row["price"] is None and row["change_pct"] is None and row["age_s"] is None
    assert row["is_proxy"] is False and shared["self_fetch"] == [["^VIX"]]


def test_a_non_tape_symbol_keeps_todays_path_at_the_admin_tier(logged_in, shared):
    from swingbot.core.marketdata.shared.kinds import Asker
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={"NVDA": 182.4}) as batch:
        row = _tape_row(logged_in, "NVDA")
    assert row["price"] == 182.4 and row["is_proxy"] is False and row["age_s"] is None
    assert batch.call_args.kwargs["asker"] is Asker.ADMIN_PAGE


def test_flag_off_rows_carry_the_default_proxy_fields(logged_in):
    with patch("swingbot.core.marketdata.data.get_current_price_batch", return_value={"NVDA": 182.4}) as batch:
        row = _tape_row(logged_in, "NVDA")
    assert (row["is_proxy"], row["proxy_symbol"], row["age_s"]) == (False, None, None)
    assert batch.call_args.kwargs == {}                     # off: called exactly as before v171


def test_the_self_fetch_runs_once_at_admin_page(monkeypatch):
    from swingbot.admin.api_v1 import market
    from swingbot.core.marketdata.shared import tape
    from swingbot.core.marketdata.shared.kinds import Asker
    calls = []
    monkeypatch.setattr(tape, "refresh_tape", lambda syms, *, asker, **k: calls.append((syms, asker)) or {})
    market._run_tape_self_fetch(["^GSPC"])
    assert calls == [(["^GSPC"], Asker.ADMIN_PAGE)]
    assert market._SELF_FETCH_LOCK.acquire(blocking=False)
    try:
        assert market._tape_self_fetch(["^GSPC"]) is None   # one in flight per process
    finally:
        market._SELF_FETCH_LOCK.release()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_tape.py`
Expected: the new tests FAIL (`AttributeError: ... has no attribute '_tape_self_fetch'`, `KeyError: 'is_proxy'`); the existing tests PASS.

- [ ] **Step 3: Implement**

In `market.py`, add the helpers from the Interfaces block above `tape()` (each a few lines; `_tape_extras(entry, now) -> dict` builds `is_proxy`/`proxy_symbol`/`age_s`, `_NO_EXTRAS` the defaults; import `config`, `threading`, `tape` and `Asker` lazily as the module already does for `tape_cache`). `_run_tape_self_fetch` releases `_SELF_FETCH_LOCK` in `finally` only when the thread wrapper took it: put the release in the thread target wrapper, not in `_run_tape_self_fetch`, so the test can call `_run_tape_self_fetch` directly. In `tape()`, replace the two lines `prices = tape_cache.prices(symbols)` / `frames = tape_cache.daily_frames(symbols)` with `prices, changes, extras = _tape_quotes(symbols)`, and in the row dict use `"change_pct": changes.get(symbol)` plus `**extras.get(symbol, _NO_EXTRAS)`. `tape()` gains no branch. In `tape_cache.prices`, build `kwargs = {} if config.MARKETDATA_LAYER == "off" else {"asker": Asker.ADMIN_PAGE}` (lazy imports) and call `market_data.get_current_price_batch(missing, **kwargs)`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_tape.py`, then `... file tests/admin/test_tape_cache.py`, `... file tests/admin/test_api_v1_market.py`
Expected: all PASS, `0 failed` (including `test_concurrent_tape_requests_share_one_download`, which runs with the layer `off`).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/admin/api_v1/market.py $WT/swingbot/admin/tape_cache.py`
Expected: only the pre-existing `chart - D (24)` (and `_tape_context` if it was listed before, unchanged); `tape` and every new helper below C.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/admin/api_v1/market.py swingbot/admin/tape_cache.py tests/admin/test_api_v1_tape.py
git -C $WT commit -m "feat(admin): v171 D7 tape reads the shared copy, labelled proxies, ages, tier-5 self-fetch when stale (V171-29)"
```
