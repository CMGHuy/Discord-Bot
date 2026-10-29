# Instant admin page loads: part 2, request path and ops

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Instant admin page loads](../specs/2026-10-29-v201-instant-admin-page-loads.md)
**Index:** [`_0-index.md`](2026-10-29-v201-instant-admin-page-loads_0-index.md): Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and every cross-task contract (Config fields, Contract module, Tables, Repositories, Request-path door, MarketMeta, Endpoints). Read its Global Constraints before any task here.

This part holds V201-7 … V201-11. It builds the one request-path door
(`swingbot/admin/market_values.py`), routes Dashboard, tape, watchlist,
Trades and Trade detail through it, adds the updates/refresh endpoints and
the refresher's health line, and ships the `refresher` compose service with
its deploy and rollback wiring.

`<wt>` below is the implementation worktree's absolute path. Every DB-backed
test run is preceded once per session by `/replicate-prod-db` into the shared
`swing-db` container.

**Shared test scaffolding (created in V201-7, used by every task here):**
`tests/admin_market/conftest.py` gives `market` (fake quote cache, queue,
marks, snapshots and heartbeat), `session_is` (pins the session state),
`refresher_on` (flags only) and `on_client` (an authenticated admin test
client with the refresher on). `tests/admin_market/test_page_loads_never_fetch.py`
(V201-8) gives `PAGE_LOAD_ENDPOINTS`, `FORBIDDEN` and the `network_forbidden`
fixture.

---

# Phase: request path (V201-7 … V201-10)

### Task V201-7: Request-path door `market_values` (never-fetch reads, refreshing, enqueue, totals, fresh hint)

**Model:** sonnet — a new self-contained module against fixed repository contracts, with fake-backed unit tests.

**Files:**
- Create: `swingbot/admin/market_values.py`
- Create: `tests/admin_market/conftest.py`
- Create: `tests/admin_market/test_market_values.py`
- Modify: `tests/admin/conftest.py` (one autouse fixture; the `fx.quote_currency_code` lambda accepts keywords)

**Interfaces:**
- Consumes (V201-1): `admin_refresh.refresher_on`, `stale_after_s`, `quote_mark_key`, `snapshot_mark_key`, `is_snapshot_key`, `PRIORITY_USER/FRESH_HINT/MISSING`, `QUEUE_KIND_QUOTE/SNAPSHOT`; `session.session_state(now=None) -> str`. (V201-3) `market_refresh.refresh_queue_repo()`, `refresh_mark_repo()`, `admin_snapshot_repo()` with the index's "Repositories" methods. Existing: `layer.last_cached(kind, symbols) -> dict[str, Entry]` (`{}` unless `MARKETDATA_LAYER == "on"`), `kinds.is_fresh_request()`, `kinds.Entry` (`value, fetched_at, source, outcome`).
- Produces: the index's "Request-path door" exactly, plus two **additive keyword defaults** fixed here for V201-8 and V201-10: `read_quotes(symbols, *, kind: DataKind = DataKind.QUOTE, enqueue: bool = True, now: datetime | None = None)` and `read_snapshot(key, *, enqueue: bool = True)`. `MarketQuote` gains a trailing `source: str | None = None` (the provider label the watchlist shows). `enqueue=False` is the read the updates endpoint uses; it never writes the queue.
- Produces (tests): fixtures `market`, `session_is`, `refresher_on`, `on_client` in `tests/admin_market/conftest.py`; helper `quote_entry(symbol, price, *, age_s, source="alpaca-iex") -> Entry`.

**Behaviour fixed here (the tests pin each line):**
- `read_quotes` reads `layer.last_cached(kind, wanted)` once and the marks once (`active` + `errors` over the `quote:<SYM>` keys). It never calls a provider. A doc is read generically: `price = doc.get("price")` (≤ 0 → `None`), and `as_of` is the doc's `trade_at` or `quote_at`, else the entry's `fetched_at`. That serves `QUOTE` and `INDEX_QUOTE` docs alike. `age_s` is measured from `as_of`.
- **Enqueue decisions use cache age (`Entry.age_s()`), not `as_of`.** A thin stock whose last trade is 5 min old but was fetched 20 s ago is not re-queued on every request.
- A missing symbol → `price=None, refreshing=True`, enqueued at `PRIORITY_MISSING`. A cached symbol older than `stale_after_s("price", state)` and not in flight is enqueued at `PRIORITY_MISSING`, and its `refreshing` reflects the mark only. In `closed` state the threshold is `None`, so nothing old is enqueued. Under `kinds.is_fresh_request()` every wanted symbol is enqueued at `PRIORITY_FRESH_HINT` instead.
- Repository errors (marks read, queue write) fail open through `swallowed(log, "admin.market_values.<op>", exc, ...)`. With no marks, `refreshing` comes only from "missing", and a failed enqueue never fails the page.
- `total_meta`: `missing_count = (#None or price-None quotes) + extra_missing`; `as_of` = the oldest priced `as_of` (ISO string); `stale_count` = priced quotes with `age_s > stale_after_s("price", state)` (`0` when closed); `refreshing` = any; `error` = first non-`None`; `computed_at=None`, `stale_inputs=False`, `source="request"`.
- `read_snapshot`: a row → `{"doc", "computed_at" (ISO), "inputs", "stale_inputs", "refreshing", "error"}`, with refreshing/error from the `snapshot:<key>` mark. No row → enqueue `QUEUE_KIND_SNAPSHOT` at `PRIORITY_MISSING` (when `enqueue`) and return `None`.
- `snapshot_meta(None)` → `refreshing=True`, every count `0`, `as_of=None`, `source="snapshot"`. With a snapshot: `as_of = inputs["oldest_quote_as_of"]`, `missing_count = len(set(missing.quotes) | set(missing.fx))`, plus `computed_at`, `stale_inputs`, `error`. `stale_count` and extra `refreshing` come from `quotes_meta` when given.
- `request_refresh` upper-cases and dedupes symbols, raises `ValueError` for a key failing `is_snapshot_key`, enqueues both kinds at `priority` and returns the inserted-row total. It does not swallow repository errors: the endpoint answers 500 rather than hiding a half-done enqueue.

- [ ] **Step 1: Write the shared fixtures** in `tests/admin_market/conftest.py`

```python
"""Fakes for the v201 request-path door: quote cache, queue, marks, snapshots, heartbeat.

The admin app fixtures are reused as-is from tests/admin/conftest.py. Its
autouse `_pin_admin_refresher_off` is deliberately NOT imported."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata.shared.kinds import DataKind, Entry, QuoteDetail
from tests.admin.conftest import _clear_login_limiter, admin_app, auth, client  # noqa: F401


def utcnow():
    return datetime.now(timezone.utc)


def quote_entry(symbol, price, *, age_s, source="alpaca-iex"):
    at = utcnow() - timedelta(seconds=age_s)
    doc = QuoteDetail(symbol=symbol, price=price, trade_at=at, bid=None, ask=None,
                      quote_at=None, source=source).to_doc()
    return Entry(doc, at, source, "ok")


@dataclass
class FakeQueue:
    pending: dict = field(default_factory=dict)          # (kind, key) -> priority

    def enqueue(self, kind, keys, *, priority):
        added = 0
        for key in keys:
            old = self.pending.get((kind, key))
            if old is None:
                added += 1
            if old is None or priority < old:
                self.pending[(kind, key)] = priority
        return added


@dataclass
class FakeMarks:
    in_flight: set = field(default_factory=set)
    errors_by_key: dict = field(default_factory=dict)
    changed: list = field(default_factory=list)

    def active(self, keys, now=None):
        return {k for k in keys if k in self.in_flight}

    def errors(self, keys):
        return {k: self.errors_by_key[k] for k in keys if k in self.errors_by_key}

    def changed_since(self, since):
        return list(self.changed)


@dataclass
class FakeSnapshots:
    rows: dict = field(default_factory=dict)

    def get(self, key):
        return self.rows.get(key)

    def changed_since(self, since):
        return [{k: r[k] for k in ("key", "computed_at", "stale_inputs", "updated_at")}
                for r in self.rows.values()]


@dataclass
class FakeHeartbeat:
    row: dict | None = None

    def read(self):
        return self.row


@dataclass
class Market:
    cache: dict = field(default_factory=dict)             # (kind, SYMBOL) -> Entry
    queue: FakeQueue = field(default_factory=FakeQueue)
    marks: FakeMarks = field(default_factory=FakeMarks)
    snapshots: FakeSnapshots = field(default_factory=FakeSnapshots)
    heartbeat: FakeHeartbeat = field(default_factory=FakeHeartbeat)

    def quote(self, symbol, price, *, age_s, kind=DataKind.QUOTE, source="alpaca-iex"):
        self.cache[(kind, symbol.upper())] = quote_entry(
            symbol.upper(), price, age_s=age_s, source=source)


@pytest.fixture
def market(monkeypatch):
    from swingbot.core.db.repositories import market_refresh
    from swingbot.core.marketdata.shared import layer
    state = Market()
    monkeypatch.setattr(layer, "last_cached", lambda kind, symbols, params="": {
        s: state.cache[(kind, s)] for s in symbols if (kind, s) in state.cache})
    monkeypatch.setattr(market_refresh, "refresh_queue_repo", lambda: state.queue)
    monkeypatch.setattr(market_refresh, "refresh_mark_repo", lambda: state.marks)
    monkeypatch.setattr(market_refresh, "admin_snapshot_repo", lambda: state.snapshots)
    monkeypatch.setattr(market_refresh, "refresher_heartbeat_repo", lambda: state.heartbeat)
    return state


@pytest.fixture
def session_is(monkeypatch):
    from swingbot.core.market import session

    def pin(state):
        monkeypatch.setattr(session, "session_state", lambda now=None: state)
    pin("regular")
    return pin


@pytest.fixture
def refresher_on(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")


@pytest.fixture
def on_client(admin_app, market, session_is, auth, monkeypatch):
    # After admin_app, which pins MARKETDATA_LAYER="off" for the admin suite.
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    c = admin_app.test_client()
    c.environ_base["HTTP_AUTHORIZATION"] = auth["Authorization"]
    return c
```

- [ ] **Step 2: Write the failing door tests** in `tests/admin_market/test_market_values.py`

```python
from datetime import datetime, timezone

import pytest

from swingbot.admin import market_values as mv
from swingbot.core.marketdata import data
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.admin_refresh import (
    PRIORITY_FRESH_HINT, PRIORITY_MISSING, PRIORITY_USER, QUEUE_KIND_QUOTE, QUEUE_KIND_SNAPSHOT)
from swingbot.core.marketdata.shared.kinds import DataKind

ROW_QUOTE_FIELDS = {"current_price", "current_price_stale", "price_as_of", "price_age_s",
                    "price_refreshing", "price_error"}
META_KEYS = {"as_of", "refreshing", "stale_count", "missing_count", "incomplete",
             "computed_at", "stale_inputs", "source", "error"}


@pytest.fixture(autouse=True)
def _no_provider(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the door fetched")
    monkeypatch.setattr(data, "get_quote_batch", boom)


def test_cached_quote_is_read_with_its_age_and_no_fetch(market, session_is):
    market.quote("MSFT", 110.0, age_s=12)
    q = mv.read_quotes(["msft"])["MSFT"]
    assert q.price == 110.0 and q.refreshing is False and q.error is None
    assert 11 <= q.age_s <= 15 and q.as_of.startswith("20") and q.source == "alpaca-iex"
    assert market.queue.pending == {}


def test_never_seen_symbol_is_null_refreshing_and_enqueued_once(market, session_is):
    first = mv.read_quotes(["NEWX"])["NEWX"]
    mv.read_quotes(["NEWX"])
    assert first.price is None and first.refreshing is True
    assert market.queue.pending == {(QUEUE_KIND_QUOTE, "NEWX"): PRIORITY_MISSING}


def test_stale_symbol_is_enqueued_unless_in_flight(market, session_is):
    market.quote("OLD", 5.0, age_s=600)
    market.quote("BUSY", 6.0, age_s=600)
    market.marks.in_flight.add("quote:BUSY")
    got = mv.read_quotes(["OLD", "BUSY"])
    assert got["OLD"].refreshing is False and got["BUSY"].refreshing is True
    assert market.queue.pending == {(QUEUE_KIND_QUOTE, "OLD"): PRIORITY_MISSING}


def test_closed_market_never_requeues_old_quotes(market, session_is):
    session_is("closed")
    market.quote("MSFT", 110.0, age_s=2 * 86400)
    assert mv.read_quotes(["MSFT"])["MSFT"].price == 110.0
    assert market.queue.pending == {}


def test_fresh_hint_enqueues_every_symbol(market, session_is):
    market.quote("MSFT", 110.0, age_s=1)
    with kinds.fresh_request():
        mv.read_quotes(["MSFT", "NVDA"])
    assert market.queue.pending == {(QUEUE_KIND_QUOTE, "MSFT"): PRIORITY_FRESH_HINT,
                                    (QUEUE_KIND_QUOTE, "NVDA"): PRIORITY_FRESH_HINT}


def test_enqueue_false_never_writes_the_queue(market, session_is):
    mv.read_quotes(["NEWX"], enqueue=False)
    assert market.queue.pending == {}


def test_index_quotes_read_their_own_kind(market, session_is):
    market.quote("^GSPC", 5000.0, age_s=5, kind=DataKind.INDEX_QUOTE)
    assert mv.read_quotes(["^GSPC"], kind=DataKind.INDEX_QUOTE)["^GSPC"].price == 5000.0


def test_mark_error_is_reported_and_stops_refreshing(market, session_is):
    market.quote("BAD", 7.0, age_s=30)
    market.marks.errors_by_key["quote:BAD"] = "provider 503"
    q = mv.read_quotes(["BAD"])["BAD"]
    assert q.error == "provider 503" and q.refreshing is False


def test_repository_failure_fails_open(market, session_is, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(market.marks, "active", broken)
    monkeypatch.setattr(market.queue, "enqueue", broken)
    market.quote("MSFT", 110.0, age_s=5)
    assert mv.read_quotes(["MSFT", "NEWX"])["MSFT"].price == 110.0


def test_quote_fields_are_exactly_the_row_quote_fields(market, session_is):
    market.quote("MSFT", 110.0, age_s=5)
    fields = mv.quote_fields(mv.read_quotes(["MSFT"])["MSFT"])
    assert set(fields) == ROW_QUOTE_FIELDS and fields["current_price_stale"] is False
    assert set(mv.quote_fields(None)) == ROW_QUOTE_FIELDS
    assert mv.quote_fields(None)["price_refreshing"] is False


def test_total_meta_takes_the_oldest_input_and_counts_stale(market, session_is):
    market.quote("A", 1.0, age_s=10)
    market.quote("B", 2.0, age_s=200)                 # regular: stale after 120 s
    quotes = mv.read_quotes(["A", "B"])
    meta = mv.total_meta(quotes.values())
    assert meta["as_of"] == quotes["B"].as_of
    assert meta["stale_count"] == 1 and meta["missing_count"] == 0
    assert meta["incomplete"] is False and meta["source"] == "request"


def test_total_with_unknown_currency_counts_missing_not_zero(market, session_is):
    market.quote("A", 1.0, age_s=10)
    quotes = mv.read_quotes(["A", "NEWX"])
    meta = mv.total_meta(quotes.values(), extra_missing=1)    # 1 unknown-currency position
    assert meta["missing_count"] == 2 and meta["incomplete"] is True
    assert meta["refreshing"] is True


def test_total_meta_closed_session_counts_nothing_stale(market, session_is):
    session_is("closed")
    market.quote("A", 1.0, age_s=3 * 86400)
    assert mv.total_meta(mv.read_quotes(["A"]).values())["stale_count"] == 0


def test_market_meta_always_has_every_key():
    assert set(mv.total_meta([])) == META_KEYS and set(mv.snapshot_meta(None)) == META_KEYS


def test_missing_snapshot_is_enqueued_and_reads_none(market):
    assert mv.read_snapshot("risk") is None
    assert market.queue.pending == {(QUEUE_KIND_SNAPSHOT, "risk"): PRIORITY_MISSING}
    assert mv.snapshot_meta(None)["refreshing"] is True


def test_snapshot_reads_with_marks_and_inputs(market):
    at = datetime(2026, 10, 29, 14, 30, tzinfo=timezone.utc)
    market.snapshots.rows["risk"] = {
        "key": "risk", "doc": {"heat": 1.0}, "computed_at": at, "stale_inputs": True,
        "updated_at": at,
        "inputs": {"oldest_quote_as_of": "2026-10-29T14:29:00+00:00",
                   "missing": {"quotes": ["X"], "bars": ["Y"], "fx": ["X", "Z"]}}}
    market.marks.in_flight.add("snapshot:risk")
    snap = mv.read_snapshot("risk")
    assert snap["doc"] == {"heat": 1.0} and snap["refreshing"] is True
    meta = mv.snapshot_meta(snap)
    assert meta["as_of"] == "2026-10-29T14:29:00+00:00" and meta["missing_count"] == 2
    assert meta["stale_inputs"] is True and meta["computed_at"].startswith("2026-10-29T14:30")


def test_request_refresh_enqueues_at_user_priority(market):
    assert mv.request_refresh(["msft", "MSFT", "nvda"], ["risk"]) == 3
    assert market.queue.pending[(QUEUE_KIND_QUOTE, "MSFT")] == PRIORITY_USER
    assert market.queue.pending[(QUEUE_KIND_SNAPSHOT, "risk")] == PRIORITY_USER


def test_request_refresh_rejects_an_unknown_snapshot_key(market):
    with pytest.raises(ValueError):
        mv.request_refresh([], ["nope"])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_market/test_market_values.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'swingbot.admin.market_values'`.

- [ ] **Step 4: Implement `swingbot/admin/market_values.py`**

The module docstring says it is the only door page handlers use for market values when `admin_refresh.refresher_on()`: it never fetches, and the Refresh control only enqueues. Top-level imports: `from swingbot.core.db.repositories import market_refresh` and `from swingbot.core.market import session`, both called through the module attribute (`market_refresh.refresh_queue_repo()`, `session.session_state()`) so the fixtures can patch them. Also import `admin_refresh`, `kinds`, `DataKind` and `swallowed`. Import `layer` inside `_cached(kind, symbols)`, as `freshness.cached_quotes` does.

The public names are exactly the contract: `MarketQuote` (frozen dataclass: `symbol, price, as_of, age_s, refreshing, error, source=None`), `read_quotes`, `quote_fields`, `total_meta`, `read_snapshot`, `snapshot_meta` and `request_refresh`. The private helpers each stay well under complexity 15:
- `_upper_unique(symbols) -> list[str]`
- `_cached(kind, symbols) -> dict[str, Entry]`
- `_doc_as_of(entry) -> datetime`: `datetime.fromisoformat` on `trade_at`/`quote_at`, falling back to `entry.fetched_at`
- `_quote(symbol, entry, in_flight, error, now) -> MarketQuote`
- `_marks(keys) -> tuple[set[str], dict[str, str]]` (fails open)
- `_due(wanted, entries, quotes, now) -> list[str]`
- `_enqueue(kind, keys, priority)` (fails open)
- `_meta(**overrides) -> dict`: the one place that holds every MarketMeta key and its default

`price_age_s` is `round(age_s, 1)`.

- [ ] **Step 5: Pin the admin suite to the fallback path** in `tests/admin/conftest.py`

Add this beside `_clear_login_limiter`:

```python
@pytest.fixture(autouse=True)
def _pin_admin_refresher_off(monkeypatch):
    """v201: the admin suite keeps covering today's request-time paths; the
    refresher-on paths are tested in tests/admin_market/."""
    from swingbot import config
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
```

Then change the `admin_app` FX pin so it accepts V201-4's keyword: `lambda ticker, **_kw: fx.account_currency_code()`. Skip this if V201-4 already made the change.

- [ ] **Step 6: Run the door tests and the admin freshness file**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_market/test_market_values.py`
Expected: PASS, `0 failed`.
Run: `python <wt>/scripts/dev/testrun.py file tests/admin/test_admin_freshness.py`
Expected: PASS (the refresher is pinned off, so behaviour is unchanged).
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: no new violation.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add swingbot/admin/market_values.py tests/admin_market/conftest.py tests/admin_market/test_market_values.py tests/admin/conftest.py
git -C <wt> commit -m "feat(v201): never-fetch market_values door for admin page loads"
```

### Task V201-8: Dashboard, tape and watchlist read through the door; no-network page-load test; endpoint sweep

**Model:** opus — three legacy request paths (one over the complexity limit) change behind a kill switch, and the never-fetch test is the spec's headline guard.

**Files:**
- Modify: `swingbot/admin/dashboard.py` (`_open_trade_prices` call site in `build_open_trade_views`; new `_open_trade_market`)
- Modify: `swingbot/admin/api_v1/dashboard.py` (`_open_figures`, `_equity_30d`; new `_open_meta`)
- Modify: `swingbot/admin/api_v1/market.py` (`_tape_quotes`; new `_door_tape_quotes`, `_door_extras`, `_disk_frames`)
- Modify: `swingbot/admin/watchlist_rows.py` (`_overlay`, `_stamp`, `_cold_frames`; new `_door_overlay`, `_stamp_door`, `_disk_frames`)
- Create: `tests/admin_market/test_page_loads_never_fetch.py`
- Create: `tests/admin_market/test_dashboard_market.py`
- Create: `tests/admin_market/test_tape_watchlist_market.py`
- Create: `docs/superpowers/results/2026-10-29-v201-endpoint-sweep.md`

**Interfaces:**
- Consumes: V201-7 `market_values.read_quotes(symbols, *, kind=DataKind.QUOTE, enqueue=True)`, `quote_fields`, `total_meta`, `MarketQuote` (`.source`); V201-1 `admin_refresh.refresher_on()`; V201-4 `money.convert_amount`/`to_account_currency` already pass `fetch=not refresher_on()`. Fixtures `market`, `session_is`, `on_client` (V201-7).
- Produces: `/api/v1/dashboard` body key `market_meta: MarketMeta` (the open-position totals: `open_pnl_pct`, `open_pnl_amount`), always present, refresher on or off. `build_open_trade_views(...)` return dict gains `"quotes": dict[str, MarketQuote]` (`{}` when off). `/market/tape` rows and watchlist rows gain the **row quote fields** when the refresher is on. The Dashboard's open-positions table reads `/trades` (TradesStore), so its rows get their quote fields in V201-9.
- Produces (tests): `tests/admin_market/test_page_loads_never_fetch.py` with `PAGE_LOAD_ENDPOINTS: list[str]`, `FORBIDDEN: list[tuple[str, str]]`, fixtures `network_forbidden` (returns the list of forbidden names called) and `book` (an `on_client` with an open MSFT pair, a two-name watchlist and cached quotes). V201-9, 13 and 14 append to both lists and import the fixtures.

**Behaviour fixed here:**
- **Refresher off: every path below is today's code, byte for byte.** Each new branch is the first statement of the function it guards: `if admin_refresh.refresher_on(): return <door path>`.
- Dashboard (`_open_trade_market(open_trades) -> tuple[dict, dict]`): on → `market_values.read_quotes(tickers)`, prices `{ticker: quote.price}`; off → `(_open_trade_prices(open_trades), {})`. `build_open_trade_views` replaces its one `prices = _open_trade_prices(...)` line with `prices, quotes = _open_trade_market(open_trades)` and adds `"quotes": quotes` to its return dict. That adds no branch to the legacy C(17) function.
- `_open_meta(open_trades, views, fx_missing) -> dict`: with quotes → `total_meta([quotes.get(TICKER) per open trade], extra_missing=fx_missing)`; without (off, or no positions) → `total_meta([], extra_missing=<positions with price None> + fx_missing)`. `_open_figures` returns it as `"market_meta"`.
- `_equity_30d` when on: `load_snapshot(max_age_seconds=_ANY_AGE_S)` (`_ANY_AGE_S = 10**9`), never `refresh_snapshot()`. V201-13 replaces this read with the `analytics.snapshot` row.
- Tape when on (`_door_tape_quotes`): tape symbols (`tape.is_tape_symbol`) read `read_quotes(mine, kind=DataKind.INDEX_QUOTE)` for price and age, `tape.read_tape(mine)` for `change_pct`/proxy, and `tape.record_demand(mine)` as today. They never `_tape_self_fetch`. Other symbols read `read_quotes(others)`, and their `change_pct` comes from `_tape_change_pct(s, price, _disk_frames(others))`, where `_disk_frames` is `data_store.load_normalized(sym, "daily")` of any age, errors dropped, never refreshed. Each row's extras: `_NO_EXTRAS` keys (proxy fields from the tape entry, `age_s` = `round(q.age_s, 1)` or `None`) plus `quote_fields(q)`.
- Watchlist when on: `_door_overlay(tickers)` returns `({}, {})` when `not is_us_market_active()` (the closed market shows the last close, as today, and nothing is enqueued). Otherwise it returns `({T: q.price for priced}, read_quotes(tickers))`. `_stamp` dispatches a `MarketQuote` to `_stamp_door(row, q)`: `row.update(quote_fields(q))`, then `price_source = _quote_provider(q.source or "")` when both prices are set. `_cold_frames` reads `_disk_frames(cold)`: any-age disk files, no `page_daily`, no `get_daily_data_batch`.

- [ ] **Step 1: Write the never-fetch guard** in `tests/admin_market/test_page_loads_never_fetch.py`

First confirm every `(module, name)` below exists (`git -C <wt> grep -n "def <name>\|import.*<name>" -- <module path>`); `monkeypatch.setattr` raises on a missing one, which is how a later rename gets caught.

```python
"""v201 Goal 1: with the refresher on, no page-load handler reaches a market or FX provider.

Handlers swallow exceptions, so a raising fake alone proves nothing: every
forbidden call is recorded, and the test asserts the record is empty."""
import importlib

import pytest

from swingbot.core.marketdata.shared.kinds import DataKind
from tests.admin.test_api_v1_trades import _open_pair
from tests.store_seed import seed_store

PAGE_LOAD_ENDPOINTS: list[str] = [
    "/api/v1/dashboard?mode=today",
    "/api/v1/dashboard?mode=all",
    "/api/v1/market/tape?symbols=MSFT,NEWX,%5EGSPC",
    "/api/v1/watchlist/tickers",
]

FORBIDDEN: list[tuple[str, str]] = [
    ("swingbot.core.marketdata.data", "get_quote_batch"),
    ("swingbot.core.marketdata.data", "get_current_price"),
    ("swingbot.core.marketdata.data", "get_current_price_detail"),
    ("swingbot.core.marketdata.data", "get_current_price_batch"),
    ("swingbot.core.marketdata.data", "prefetch_prices"),
    ("swingbot.core.marketdata.data", "get_daily_data_batch"),
    ("swingbot.core.marketdata.data", "_provider_currency_code"),
    ("swingbot.core.marketdata.data", "warm_batch_price_cache_background"),
    ("swingbot.core.marketdata.data_refresh", "refresh_symbol"),
    ("swingbot.core.marketdata.fx", "_refreshed_frame"),
    ("swingbot.core.marketdata.yf_safe", "download"),
    ("swingbot.core.marketdata.shared.tape", "refresh_tape"),
    ("swingbot.core.analytics.snapshots", "refresh_snapshot"),
    ("swingbot.core.edge.portfolio_state", "collect_portfolio_state"),
    ("swingbot.admin.freshness", "page_quotes"),
    ("swingbot.admin.freshness", "page_daily"),
    ("swingbot.admin.freshness", "warm_quotes_background"),
    ("swingbot.admin.tape_cache", "prices"),
    ("swingbot.admin.tape_cache", "daily_frames"),
    # Imported by name (brief 0.12): patching `data` alone would miss these.
    ("swingbot.admin.dashboard", "get_current_price"),
    ("swingbot.admin.dashboard", "prefetch_prices"),
    ("swingbot.admin.watchlist_rows", "get_daily_data_batch"),
    ("swingbot.admin.watchlist_rows", "warm_batch_price_cache_background"),
]


@pytest.fixture
def network_forbidden(monkeypatch):
    calls: list[str] = []
    for module, name in FORBIDDEN:
        def boom(*args, _name=f"{module}.{name}", **kwargs):
            calls.append(_name)
            raise AssertionError(f"network call on a page load: {_name}")
        monkeypatch.setattr(importlib.import_module(module), name, boom)
    return calls


@pytest.fixture
def book(on_client, market):
    plan, trade = _open_pair(ticker="MSFT")
    seed_store("plans", [plan])
    seed_store("trades", [trade])
    seed_store("watchlist", ["MSFT", "NVDA"])
    market.quote("MSFT", 110.0, age_s=5)
    market.quote("^GSPC", 5000.0, age_s=5, kind=DataKind.INDEX_QUOTE)
    return on_client


@pytest.mark.parametrize("endpoint", PAGE_LOAD_ENDPOINTS)
def test_page_load_makes_no_network_call(book, network_forbidden, endpoint):
    resp = book.get(endpoint)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert network_forbidden == []
```

- [ ] **Step 2: Write the failing dashboard tests** in `tests/admin_market/test_dashboard_market.py`

```python
from swingbot import config
from swingbot.core.marketdata import data
from swingbot.core.marketdata.shared.admin_refresh import QUEUE_KIND_QUOTE
from tests.admin.test_api_v1_trades import _open_pair
from tests.store_seed import seed_store


def _seed_msft():
    plan, trade = _open_pair(ticker="MSFT", entry=100.0)
    seed_store("plans", [plan])
    seed_store("trades", [trade])


def test_dashboard_prices_open_positions_from_the_cache(on_client, market):
    _seed_msft()
    market.quote("MSFT", 110.0, age_s=5)
    body = on_client.get("/api/v1/dashboard?mode=today").get_json()
    assert body["open_pnl_pct"] == 10.0
    meta = body["market_meta"]
    assert meta["as_of"] is not None and meta["missing_count"] == 0
    assert meta["incomplete"] is False and meta["source"] == "request"


def test_dashboard_kpis_incomplete_when_a_position_is_unpriced(on_client, market):
    _seed_msft()                                    # no cached quote at all
    body = on_client.get("/api/v1/dashboard?mode=today").get_json()
    assert body["open_pnl_pct"] is None and body["open_pnl_amount"] is None
    meta = body["market_meta"]
    assert meta["missing_count"] == 1 and meta["incomplete"] is True and meta["refreshing"] is True
    assert (QUEUE_KIND_QUOTE, "MSFT") in market.queue.pending


def test_refresher_off_restores_the_request_time_fetch(client, auth, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    calls = []

    def fake(tickers, *, asker, max_age_s=None, fresh_only=False):
        calls.append(list(tickers))
        return {}
    monkeypatch.setattr(data, "get_quote_batch", fake)
    _seed_msft()
    body = client.get("/api/v1/dashboard?mode=today", headers=auth).get_json()
    assert calls == [["MSFT"]]
    assert body["market_meta"]["missing_count"] == 1 and body["market_meta"]["as_of"] is None
```

- [ ] **Step 3: Write the failing tape and watchlist tests** in `tests/admin_market/test_tape_watchlist_market.py`

```python
import pandas as pd
import pytest

from swingbot.admin import watchlist_rows
from swingbot.core.marketdata import data_store
from swingbot.core.marketdata.shared.kinds import DataKind

ROW_QUOTE_FIELDS = {"current_price", "current_price_stale", "price_as_of", "price_age_s",
                    "price_refreshing", "price_error"}


@pytest.fixture
def disk(monkeypatch):
    frames = {}
    monkeypatch.setattr(data_store, "load_normalized", lambda sym, tf: frames.get(sym))
    return frames


def _rows(client, symbols):
    body = client.get(f"/api/v1/market/tape?symbols={symbols}").get_json()
    return {r["symbol"]: r for r in body["rows"]}


def test_tape_rows_carry_cached_quotes_and_their_age(on_client, market, disk):
    market.quote("MSFT", 110.0, age_s=8)
    market.quote("^GSPC", 5000.0, age_s=8, kind=DataKind.INDEX_QUOTE)
    disk["MSFT"] = pd.DataFrame({"Close": [100.0, 100.0]})
    rows = _rows(on_client, "MSFT,%5EGSPC")
    assert ROW_QUOTE_FIELDS <= set(rows["MSFT"])
    assert rows["MSFT"]["price"] == 110.0 and rows["MSFT"]["change_pct"] == 10.0
    assert rows["MSFT"]["price_refreshing"] is False and rows["MSFT"]["price_as_of"]
    assert rows["^GSPC"]["price"] == 5000.0 and rows["^GSPC"]["age_s"] >= 7


def test_tape_never_seen_symbol_is_null_and_refreshing(on_client, market, disk):
    row = _rows(on_client, "NEWX")["NEWX"]
    assert row["price"] is None and row["price_refreshing"] is True


def test_watchlist_overlays_cached_quotes_in_session(refresher_on, market, session_is,
                                                     disk, monkeypatch):
    monkeypatch.setattr(watchlist_rows, "is_us_market_active", lambda *a, **k: True)
    monkeypatch.setattr(watchlist_rows, "_cached_daily",
                        lambda t: pd.DataFrame({"Close": [100.0, 101.0]}))
    market.quote("MSFT", 110.0, age_s=5)
    row = watchlist_rows.build_market_rows(["MSFT"])["MSFT"]
    assert row["price"] == 110.0 and row["price_source"] == "alpaca"
    assert row["price_refreshing"] is False and row["price_age_s"] is not None


def test_watchlist_cold_symbol_reads_disk_of_any_age(refresher_on, market, session_is,
                                                     disk, monkeypatch):
    monkeypatch.setattr(watchlist_rows, "is_us_market_active", lambda *a, **k: False)
    monkeypatch.setattr(watchlist_rows, "_cached_daily", lambda t: None)   # stale file
    disk["NVDA"] = pd.DataFrame({"Close": [90.0, 95.0]},
                                index=pd.to_datetime(["2026-10-27", "2026-10-28"]))
    row = watchlist_rows.build_market_rows(["NVDA"])["NVDA"]
    assert row["price"] == 95.0 and row["as_of"] == "2026-10-28"
    assert market.queue.pending == {}            # closed market: last close, no enqueue
```

- [ ] **Step 4: Run the three files to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_market/test_page_loads_never_fetch.py`
Expected: FAIL. The dashboard and watchlist endpoints record `swingbot.admin.freshness.page_quotes` / `page_daily`, and the tape records `tape_cache.prices`.
Run the same for `test_dashboard_market.py` and `test_tape_watchlist_market.py`.
Expected: FAIL (`KeyError: 'market_meta'`, missing row quote fields).

- [ ] **Step 5: Implement the dashboard path**

In `swingbot/admin/dashboard.py`, add `_open_trade_market(open_trades: list) -> tuple[dict, dict]` under `_open_trade_prices` (import `admin_refresh` and `market_values` inside it, as this module already does for `freshness`). Swap the one call line in `build_open_trade_views` and add `"quotes": quotes` to its return dict. In `swingbot/admin/api_v1/dashboard.py`, add `_open_meta(open_trades: list[dict], views: dict, fx_missing: int) -> dict`, have `_open_figures` return `"market_meta": _open_meta(...)` (it travels through `**open_figures` into the body unchanged), and branch `_equity_30d`'s read as described above.

- [ ] **Step 6: Implement the tape and watchlist paths**

In `swingbot/admin/api_v1/market.py`, `_tape_quotes` starts with `if admin_refresh.refresher_on(): return _door_tape_quotes(symbols)`. Add `_door_tape_quotes(symbols: list[str]) -> tuple[dict, dict, dict]`, `_door_extras(q, entry) -> dict` and `_disk_frames(symbols: list[str]) -> dict` with lazy imports, matching the module's style. In `swingbot/admin/watchlist_rows.py`, add `_door_overlay`, `_stamp_door` and `_disk_frames` and the three guard lines. `_stamp` checks `isinstance(quote, market_values.MarketQuote)` before its existing body.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_market/test_page_loads_never_fetch.py`, then `tests/admin_market/test_dashboard_market.py`, then `tests/admin_market/test_tape_watchlist_market.py`
Expected: PASS each, `0 failed`.
Run: `python <wt>/scripts/dev/testrun.py file tests/admin/test_admin_freshness.py` and `... file tests/admin/test_api_v1_watchlist.py`
Expected: PASS (off path unchanged).
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: no new violation; `build_open_trade_views` is not above its baseline.

- [ ] **Step 8: Run the endpoint sweep and record it**

Run: `git -C <wt> grep -nE "page_quotes|get_quote_batch|get_current_price|prefetch_prices|get_daily_data_batch|quote_currency_code|fx_rate|refresh_snapshot|collect_portfolio_state|warm_quotes_background|warm_batch_price|page_daily|tape_cache\.|yf_safe|refresh_tape" -- swingbot/admin`

Write `docs/superpowers/results/2026-10-29-v201-endpoint-sweep.md` with a one-line purpose, the command, the date and the worktree HEAD. Then add one table row per hit: `file:line` · the endpoint(s) reaching it · verdict. The verdict is one of:
- `door (V201-8)`
- `door (V201-9)` for `api_v1/trades.py`
- `snapshot (V201-13)` for `risk.py`, `_equity_30d`, `analytics._snapshot`
- `measure + door (V201-14)` for Analytics and Calendar
- `refresher-off fallback only` (the hit sits behind a `refresher_on()` guard)
- `out of scope: <reason>` for an endpoint listed in the index's "Out of scope (endpoint sweep)"
- `UNCLASSIFIED`

Report any `UNCLASSIFIED` row to the controller in the task's handback; do not widen this task to fix it.

- [ ] **Step 9: Commit**

```bash
git -C <wt> add swingbot/admin/dashboard.py swingbot/admin/api_v1/dashboard.py swingbot/admin/api_v1/market.py swingbot/admin/watchlist_rows.py tests/admin_market/test_page_loads_never_fetch.py tests/admin_market/test_dashboard_market.py tests/admin_market/test_tape_watchlist_market.py docs/superpowers/results/2026-10-29-v201-endpoint-sweep.md
git -C <wt> commit -m "feat(v201): dashboard, tape and watchlist read market values through the door"
```

### Task V201-9: Trades list and Trade detail read through the door; sort on cached prices; real `prices_as_of`

**Model:** opus — `list_trades` is a legacy E(34) function that may only shrink, and the price attach runs twice on a priced sort.

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` (`_attach_current_prices`, `list_trades`, `get_trade`; new `_attach_door_prices`, `_prices_as_of`, `_position_rows`, `_row_quote`, `_page_market_meta`)
- Modify: `tests/admin_market/test_page_loads_never_fetch.py` (append endpoints)
- Create: `tests/admin_market/test_trades_market.py`

**Interfaces:**
- Consumes: V201-7 `market_values.read_quotes`, `quote_fields`, `total_meta`, `MarketQuote`; V201-1 `admin_refresh.refresher_on()`; `money.missing_count(rows)` (counts rows with `fx_missing`); V201-8 `PAGE_LOAD_ENDPOINTS`, `network_forbidden`, `book`.
- Produces: `GET /api/v1/trades` body: `prices_as_of` = the **oldest** `price_as_of` of the page's priced rows (or `None`) when the refresher is on, and today's now-stamp when it is off; `market_meta: MarketMeta` always. Live rows (status not terminal) carry the six row quote fields when on. `GET /api/v1/trades/<id>` carries the same row fields and `market_meta`. The Dashboard's open-positions table and V201-17 read these.

**Behaviour fixed here:**
- `_attach_current_prices(rows)` gains one guard right after `live` is computed and found non-empty: `if admin_refresh.refresher_on(): _attach_door_prices(live); return`. `_attach_door_prices(live)` does one `market_values.read_quotes([r["ticker"] ...])` and `r.update(quote_fields(q))` per row. The rest of the function is today's code.
- **Sorting by `pnl_pct` / `progress_pct` / `r_multiple` keeps its existing branch.** With the refresher on, that branch is one Postgres read of every live ticker, not a fetch. No new code is needed beyond the guard above; the test pins that a priced sort makes no network call and orders by the cached price.
- `_prices_as_of(page_rows) -> str | None`: on → `min` of the non-`None` `price_as_of` among rows with a `current_price` (ISO strings compared after `datetime.fromisoformat`), else `None`; off → today's expression, moved here unchanged. `list_trades` assigns `body["prices_as_of"] = _prices_as_of(page_rows)`, which removes a conditional from `list_trades`.
- `_position_rows(rows)` = rows whose status is neither terminal nor `"PENDING"`, with a ticker (the predicate `_attach_unrealized_pnl` already uses). A pending plan holds no position and is never counted as unpriced.
- `_row_quote(row) -> MarketQuote` rebuilds the door value from the row fields (`ticker`, `current_price`, `price_as_of`, `price_age_s`, `price_refreshing`, `price_error`).
- `_page_market_meta(rows) -> dict`: `pos = _position_rows(rows)`, `fx = missing_count(pos)`; on → `total_meta([_row_quote(r) for r in pos], extra_missing=fx)`; off → `total_meta([], extra_missing=fx + <pos with current_price None>)`. `list_trades` sets `body["market_meta"]`, and `get_trade` sets `row["market_meta"]` just before `jsonify`.
- `follow_score` (`_attach_follow_scores`) is DB-only. The never-fetch guard proves it here, so it gets no cache. Its latency is checked by V201-20's timing probe.

- [ ] **Step 1: Write the failing tests** in `tests/admin_market/test_trades_market.py`

```python
import pytest

from swingbot import config
from swingbot.core.marketdata import data
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.admin_market.test_page_loads_never_fetch import network_forbidden  # noqa: F401
from tests.store_seed import seed_store

ROW_QUOTE_FIELDS = {"current_price", "current_price_stale", "price_as_of", "price_age_s",
                    "price_refreshing", "price_error"}


def _pair(n, ticker, entry=100.0):
    plan = _plan(f"2222222{n}-2222-4222-8222-222222222222", ticker=ticker, status="ACTIVE")
    plan.update({"direction": "bullish", "entry_price": entry, "stop_loss": 90.0, "tp1": 120.0})
    trade = _trade(f"t-open-{n}", plan_id=plan["plan_id"], ticker=ticker, status="open")
    trade.update({"entry": entry, "stop_loss": 90.0, "take_profit": 120.0})
    return plan, trade


@pytest.fixture
def two_open(on_client):
    (p1, t1), (p2, t2) = _pair(1, "MSFT"), _pair(2, "NVDA")
    seed_store("plans", [p1, p2])
    seed_store("trades", [t1, t2])
    return on_client


def _items(client, query="status=open"):
    body = client.get(f"/api/v1/trades?{query}").get_json()
    return body, {r["ticker"]: r for r in body["items"]}


def test_list_rows_carry_cached_quotes_and_the_oldest_as_of(two_open, market,
                                                            network_forbidden):
    market.quote("MSFT", 110.0, age_s=10)
    market.quote("NVDA", 95.0, age_s=100)
    body, rows = _items(two_open)
    assert ROW_QUOTE_FIELDS <= set(rows["MSFT"])
    assert rows["MSFT"]["current_price"] == 110.0 and rows["MSFT"]["price_refreshing"] is False
    assert body["prices_as_of"] == rows["NVDA"]["price_as_of"]          # the older of the two
    assert body["market_meta"]["as_of"] == rows["NVDA"]["price_as_of"]
    assert body["market_meta"]["missing_count"] == 0
    assert network_forbidden == []


def test_unpriced_position_makes_the_page_incomplete(two_open, market):
    market.quote("MSFT", 110.0, age_s=10)
    body, rows = _items(two_open)
    assert rows["NVDA"]["current_price"] is None and rows["NVDA"]["price_refreshing"] is True
    assert body["market_meta"]["missing_count"] == 1 and body["market_meta"]["incomplete"] is True
    assert body["prices_as_of"] == rows["MSFT"]["price_as_of"]


def test_no_priced_row_means_no_prices_as_of(two_open, market):
    body, _ = _items(two_open)
    assert body["prices_as_of"] is None and body["market_meta"]["as_of"] is None


@pytest.mark.parametrize("field", ["pnl_pct", "progress_pct", "r_multiple"])
def test_priced_sort_orders_on_cached_prices_without_a_fetch(two_open, market,
                                                             network_forbidden, field):
    market.quote("MSFT", 110.0, age_s=10)     # +10 %
    market.quote("NVDA", 115.0, age_s=10)     # +15 %
    body, _ = _items(two_open, f"status=open&sort=-{field}")
    assert [r["ticker"] for r in body["items"]] == ["NVDA", "MSFT"]
    assert network_forbidden == []


def test_trade_detail_carries_row_quote_fields_and_meta(two_open, market):
    market.quote("MSFT", 110.0, age_s=10)
    row = two_open.get("/api/v1/trades/22222221-2222-4222-8222-222222222222").get_json()
    assert ROW_QUOTE_FIELDS <= set(row) and row["current_price"] == 110.0
    assert row["market_meta"]["missing_count"] == 0 and row["market_meta"]["as_of"]


def test_refresher_off_keeps_the_now_stamp(client, auth, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(data, "prefetch_prices", lambda tickers: None)
    monkeypatch.setattr(data, "get_current_price_detail", lambda t: type(
        "D", (), {"price": 110.0, "stale": False})())
    plan, trade = _pair(1, "MSFT")
    seed_store("plans", [plan])
    seed_store("trades", [trade])
    body = client.get("/api/v1/trades?status=open", headers=auth).get_json()
    assert body["items"][0]["current_price"] == 110.0
    assert body["prices_as_of"] is not None                     # today's behaviour
    assert set(body["market_meta"]) >= {"as_of", "missing_count", "incomplete"}
```

Sort spelling is the collection convention's `sort=-<field>` for descending (`tests/admin/test_api_v1_trades.py:785`). Detail is addressed by the **plan id** for a plan-backed position (`get_trade` → `_looks_like_a_plan_id`).

- [ ] **Step 2: Append the trades endpoints to the never-fetch guard**

In `tests/admin_market/test_page_loads_never_fetch.py`, append to `PAGE_LOAD_ENDPOINTS`:

```python
    "/api/v1/trades?page=1&per_page=200",
    "/api/v1/trades?status=open&sort=-pnl_pct",
    "/api/v1/trades/22222222-2222-4222-8222-222222222222",
```

(`book` seeds `_open_pair`, whose plan id is the one above; detail is addressed by plan id.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_market/test_trades_market.py`
Expected: FAIL (`KeyError: 'market_meta'`; `network_forbidden` records `swingbot.admin.freshness.page_quotes`).
Run: `python <wt>/scripts/dev/testrun.py file tests/admin_market/test_page_loads_never_fetch.py`
Expected: FAIL on the three new endpoints only.

- [ ] **Step 4: Implement** the five helpers and the three call-site edits described above in `swingbot/admin/api_v1/trades.py`

Import `admin_refresh` and `market_values` lazily inside the helpers (this module already imports `freshness` lazily), and add `missing_count` to the existing `from .money import ...` line. `list_trades` changes in exactly two places: the `prices_as_of` assignment becomes `_prices_as_of(page_rows)`, and one new line, `body["market_meta"] = _page_market_meta(page_rows)`. `get_trade` gains `row["market_meta"] = _page_market_meta([row])` before `jsonify(row)`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_market/test_trades_market.py`, then `... file tests/admin_market/test_page_loads_never_fetch.py`
Expected: PASS, `0 failed`.
Run: `python <wt>/scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py` and `... file tests/admin/test_admin_freshness.py`
Expected: PASS (off path unchanged; `market_meta` is an added key). If a contract test in `tests/admin/` pins the exact key set of the list body or the detail row, add `market_meta` to that expected set. That is the only edit allowed in `tests/admin/`.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: `list_trades` at or below its baseline (34); `_attach_current_prices` < 15.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add swingbot/admin/api_v1/trades.py tests/admin_market/test_trades_market.py tests/admin_market/test_page_loads_never_fetch.py
git -C <wt> commit -m "feat(v201): trades list and detail price from the cache with oldest-input as_of"
```

### Task V201-10: `GET /market/updates`, `POST /market/refresh`, refresher in `/system/health`

**Model:** sonnet — two thin endpoints and one health block over the door and repositories, with exact JSON contracts from the index.

**Files:**
- Create: `swingbot/admin/api_v1/market_updates.py`
- Create: `tests/admin_market/test_market_updates.py`
- Modify: `swingbot/admin/api_v1/__init__.py` (add `market_updates` to the endpoint import tuple in `register()`)
- Modify: `swingbot/admin/api_v1/ops_health.py` (`get_system_health` gains `"refresher"`)

**Interfaces:**
- Consumes: V201-7 `market_values.read_quotes(..., kind=, enqueue=False)`, `read_snapshot(key, enqueue=False)`, `request_refresh`; V201-3 `MarketSharedRepository.changed_since(kind, since, *, conn)`, `refresh_mark_repo().changed_since(since)` (`key, in_flight, error, updated_at`), `admin_snapshot_repo().changed_since(since)`, `refresher_heartbeat_repo().read()` (`beat_at, cadence_s, session, cycle_ms, last_error`); V201-1 `admin_refresh.cadence_s`, `stale_after_s`, `heartbeat_stalled(beat_at, cadence, now=None)`, `is_snapshot_key`, `refresher_on`; `session.session_state(now)`, `session.last_regular_close(now)`; `tape.is_tape_symbol`; `side_connection` (`swingbot.core.db.side_engine`); `iso`, `ApiError`, `api_v1`, `require_auth`.
- Produces: the index's "Endpoints" JSON exactly. Also `market_updates.status_block(now: datetime | None = None) -> dict` (the `status` object) and `market_updates.refresher_health() -> dict` (the health block), which `ops_health` imports. `MAX_REFRESH_SYMBOLS = 200`.

**Behaviour fixed here:**
- `GET /market/updates`: `now` is taken first and becomes `cursor` (`iso(now)`). A row written while the read runs is therefore sent again next time rather than lost. A missing or empty `since` means empty lists plus `status`. `since` parses with `datetime.fromisoformat` after a trailing `Z` → `+00:00`; a naive value is UTC; anything unparsable raises `ApiError("invalid", "since must be an ISO-8601 timestamp", 400)`.
- Quote updates: `symbols = {row["symbol"] for kinds "quote" and "index" changed since} ∪ {key[len("quote:"):] for changed marks starting "quote:"}`. Tape symbols read `kind=DataKind.INDEX_QUOTE`, the rest `QUOTE`, both with `enqueue=False`. The list is sorted by symbol, items `{"symbol", "price", "as_of", "refreshing", "error"}`. The cache read is the private `_cache_changes(since) -> list[dict]` (one `side_connection`, both kinds), which the tests patch.
- Snapshot updates: `keys = {changed snapshot rows} ∪ {mark keys starting "snapshot:"}`. With a row: `{"key", "computed_at", "refreshing", "stale_inputs", "error"}` from `read_snapshot(key, enqueue=False)`. Without one: `computed_at=None, stale_inputs=False`, plus `refreshing`/`error` from the mark row. Sorted by key.
- `status_block(now)`: `session = session_state(now)`, `last_close_at = iso(last_regular_close(now))`, `stale_price_s`/`stale_snapshot_s` from `stale_after_s`. `heartbeat.cadence_s` is the row's, else `cadence_s(session)`. `heartbeat.stalled = refresher_on() and heartbeat_stalled(beat_at, cadence, now)`: with the kill switch off, no refresher is expected and the SPA must not raise "prices paused". A heartbeat read error fails open to "no row".
- `refresher_health()`: `{"status": "off" | "ok" | "stalled", "beat_at", "cadence_s", "last_error"}`. `"off"` when `not refresher_on()`, with the other three `None`.
- `POST /market/refresh`: body `{"symbols": [str], "snapshots": [str]}`, both optional lists. Any of the following → `400 invalid` and nothing is enqueued: a non-list, a non-string item, both empty, more than `MAX_REFRESH_SYMBOLS` symbols, or a key failing `is_snapshot_key`. Success → `202 {"queued": n}`. It never fetches.

- [ ] **Step 1: Write the failing tests** in `tests/admin_market/test_market_updates.py`

```python
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.admin.api_v1 import market_updates
from swingbot.core.marketdata.shared.admin_refresh import PRIORITY_USER, QUEUE_KIND_SNAPSHOT
from tests.admin_market.test_page_loads_never_fetch import network_forbidden  # noqa: F401

NOW = datetime.now(timezone.utc)


def _beat(age_s, cadence=30.0):
    return {"beat_at": NOW - timedelta(seconds=age_s), "cadence_s": cadence,
            "session": "regular", "cycle_ms": 900, "last_error": None}


@pytest.fixture
def changes(monkeypatch):
    rows: list[dict] = []
    monkeypatch.setattr(market_updates, "_cache_changes", lambda since: list(rows))
    return rows


def test_without_since_only_status_is_filled(on_client, market, changes):
    market.heartbeat.row = _beat(10)
    body = on_client.get("/api/v1/market/updates").get_json()
    assert body["quotes"] == [] and body["snapshots"] == []
    datetime.fromisoformat(body["cursor"])
    status = body["status"]
    assert status["session"] == "regular" and status["stale_price_s"] == 120
    assert status["heartbeat"]["stalled"] is False and status["heartbeat"]["cadence_s"] == 30.0
    assert status["last_close_at"] is not None


def test_since_lists_changed_quotes_and_in_flight_marks(on_client, market, changes,
                                                        network_forbidden):
    market.quote("MSFT", 110.0, age_s=5)
    changes.append({"key": "quote:MSFT:", "symbol": "MSFT", "fetched_at": NOW,
                    "doc": {}, "updated_at": NOW})
    market.marks.in_flight.add("quote:NVDA")
    market.marks.changed.append({"key": "quote:NVDA", "in_flight": True, "error": None,
                                 "updated_at": NOW})
    since = (NOW - timedelta(minutes=1)).isoformat()
    body = on_client.get("/api/v1/market/updates", query_string={"since": since}).get_json()
    by_symbol = {q["symbol"]: q for q in body["quotes"]}
    assert by_symbol["MSFT"]["price"] == 110.0 and by_symbol["MSFT"]["refreshing"] is False
    assert by_symbol["NVDA"]["price"] is None and by_symbol["NVDA"]["refreshing"] is True
    assert set(by_symbol["MSFT"]) == {"symbol", "price", "as_of", "refreshing", "error"}
    assert market.queue.pending == {}                       # the updates read never enqueues
    assert network_forbidden == []


def test_since_lists_snapshots_with_and_without_a_row(on_client, market, changes):
    market.snapshots.rows["risk"] = {"key": "risk", "doc": {}, "inputs": {},
                                     "computed_at": NOW, "stale_inputs": True, "updated_at": NOW}
    market.marks.changed.append({"key": "snapshot:analytics.snapshot", "in_flight": True,
                                 "error": None, "updated_at": NOW})
    body = on_client.get("/api/v1/market/updates",
                         query_string={"since": "2026-01-01T00:00:00Z"}).get_json()
    snaps = {s["key"]: s for s in body["snapshots"]}
    assert snaps["risk"]["stale_inputs"] is True and snaps["risk"]["computed_at"]
    assert snaps["analytics.snapshot"] == {"key": "analytics.snapshot", "computed_at": None,
                                           "refreshing": True, "stale_inputs": False,
                                           "error": None}


def test_malformed_since_is_400(on_client, market, changes):
    resp = on_client.get("/api/v1/market/updates?since=yesterday")
    assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "invalid"


def test_heartbeat_not_stalled_when_the_refresher_is_off(on_client, market, changes,
                                                         monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    body = on_client.get("/api/v1/market/updates").get_json()
    assert body["status"]["heartbeat"]["stalled"] is False


def test_refresh_enqueues_and_answers_202(on_client, market):
    resp = on_client.post("/api/v1/market/refresh",
                          json={"symbols": ["msft", "nvda"], "snapshots": ["risk"]})
    assert resp.status_code == 202 and resp.get_json() == {"queued": 3}
    assert market.queue.pending[(QUEUE_KIND_SNAPSHOT, "risk")] == PRIORITY_USER


@pytest.mark.parametrize("body", [
    {},
    {"symbols": [], "snapshots": []},
    {"symbols": "MSFT"},
    {"symbols": [1]},
    {"symbols": [f"S{i}" for i in range(201)]},
    {"snapshots": ["not-a-key"]},
])
def test_refresh_rejects_a_bad_body(on_client, market, body):
    resp = on_client.post("/api/v1/market/refresh", json=body)
    assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "invalid"
    assert market.queue.pending == {}


@pytest.mark.parametrize("age_s, expected", [(60, "ok"), (100, "stalled")])
def test_health_reports_refresher_stalled_after_three_cadences(on_client, market,
                                                               age_s, expected):
    market.heartbeat.row = _beat(age_s, cadence=30.0)
    block = on_client.get("/api/v1/system/health").get_json()["refresher"]
    assert block["status"] == expected and block["cadence_s"] == 30.0


def test_health_reports_off_when_the_flag_is_off(on_client, market, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    assert on_client.get("/api/v1/system/health").get_json()["refresher"] == {
        "status": "off", "beat_at": None, "cadence_s": None, "last_error": None}


def test_no_heartbeat_row_reads_stalled(on_client, market):
    assert on_client.get("/api/v1/system/health").get_json()["refresher"]["status"] == "stalled"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_market/test_market_updates.py`
Expected: FAIL, `ImportError: cannot import name 'market_updates'`.

- [ ] **Step 3: Implement `swingbot/admin/api_v1/market_updates.py`**

Two routes (`market_updates_view`, `refresh_view`), both `@require_auth`, plus `status_block`, `refresher_health`, `MAX_REFRESH_SYMBOLS`. Private helpers: `_parse_since(raw) -> datetime | None`, `_cache_changes(since) -> list[dict]`, `_mark_changes(since) -> list[dict]` (fails open to `[]` through `swallowed`), `_quote_updates(since, marks) -> list[dict]`, `_snapshot_updates(since, marks) -> list[dict]`, `_heartbeat_row() -> dict | None` (fails open), `_validated_refresh(payload) -> tuple[list[str], list[str]]` (raises `ApiError("invalid", ..., 400)`). Every function is under complexity 15. Follow this package's own rule: import `swingbot.admin.market_values` and the repositories inside the functions, never at module top (the circular-import note in `api_v1/__init__.py`).

- [ ] **Step 4: Register and wire health**

In `swingbot/admin/api_v1/__init__.py` `register()`, add `market_updates` to the `from . import (...)` tuple, in alphabetical order after `market`. In `ops_health.get_system_health`, add `"refresher": market_updates.refresher_health()` to the returned dict, with `from . import market_updates` inside the function.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_market/test_market_updates.py`
Expected: PASS, `0 failed`.
Run: `python <wt>/scripts/dev/testrun.py file tests/admin/test_api_v1_ops_health.py`
Expected: PASS. If that file asserts the exact top-level key set, add `"refresher"` to it; that is the only `tests/admin/` edit allowed.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: no new violation.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add swingbot/admin/api_v1/market_updates.py swingbot/admin/api_v1/__init__.py swingbot/admin/api_v1/ops_health.py tests/admin_market/test_market_updates.py
git -C <wt> commit -m "feat(v201): market updates and refresh endpoints, refresher health"
```

# Phase: ops (V201-11)

### Task V201-11: Ops: `refresher` compose service, deploy digest loop, PITR rollback, deploy doc

**Model:** sonnet — config and shell edits pinned by shape tests; the one judgement call (rollback to a pre-v201 image) is decided below.

**Files:**
- Modify: `docker-compose.yml` (new `refresher` service after `admin`)
- Modify: `deploy/deploy.sh` (digest loop at :265, success line)
- Modify: `scripts/ops/rollback_to.sh` (step 4 stop at :59, step 9 start at :87)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (line 7 service list; new section; the rollback-order line at :434)
- Modify: `tests/db/test_compose.py`
- Modify: `tests/scripts/test_rollback_to_shape.py` (its markers name the `bot admin` lines this task changes; it is not in the ledger row, but the edit is forced and no other task touches the file)

**Interfaces:**
- Consumes: V201-5 entry point `python -m swingbot.refresher` (`swingbot/refresher/__main__.py:main`); V201-1 `ADMIN_REFRESHER`.
- Produces: compose service `refresher` exactly as the ledger row: `container_name: swing-refresher`, `command: ["python", "-m", "swingbot.refresher"]`, the same `image`, `env_file` and `volumes` as `bot`, `cpus: "0.5"`, `mem_limit: 1g`, `restart: unless-stopped`, the bot's `kill -0 1` healthcheck, `depends_on: db: service_healthy`, no `build`, no `ports`.

**Decisions fixed here:**
- **A normal deploy needs no manual step.** `deploy.sh` runs `docker compose up -d --no-build --wait` (no service list) at :180, which creates `refresher` with the pulled image. The digest loop then verifies it like `bot` and `admin`. `.env` needs no edit: `ADMIN_REFRESHER` defaults to `on`. So `Bump:` stays `ui patch, bot patch`. If the implementer finds any step this does not cover, stop and report it to the controller, which re-grades `Bump:` (Global Constraints). Do not add the step silently.
- **Order on deploy:** `up --wait` (:180) runs before `alembic upgrade head` (:189). The refresher's first cycles after a deploy that adds `v201_001` can therefore hit missing tables. V201-5's loop logs the cycle error and retries next cadence; it must not exit. The deploy doc says so. If V201-5's process exits on that error, `--wait` fails the deploy; report it as a V201-5 defect, not a deploy-script change.
- **Rollback to an image that predates v201** has no `swingbot.refresher` module. A blind `up --wait bot admin refresher` would crash-loop the refresher and fail the script after Postgres was already restored. Step 9 therefore probes the target image first:

  ```bash
  # v201: an image older than the refresher has no swingbot.refresher module.
  SERVICES="bot admin"
  if docker run --rm --entrypoint python "$bot_image" -c "import swingbot.refresher" </dev/null >/dev/null 2>&1; then
    SERVICES="bot admin refresher"
  fi
  docker compose up -d --no-build --wait $SERVICES
  ```

  Step 4 becomes `docker compose stop bot admin refresher`, which is a no-op for a service with no container.
- `cpus: "0.5"` is a hard cap. The bot keeps its `1.0` and admin its `cpu_shares: 2048` on the 2-vCPU box, and a 52 s `collect_portfolio_state` in the refresher can no longer starve the admin worker. `mem_limit: 1g` covers pandas daily-bar frames for the snapshot builders.

- [ ] **Step 1: Write the failing compose and deploy tests** in `tests/db/test_compose.py`

Change the parametrize list of `test_application_services_wait_for_a_healthy_database` to `["bot", "admin", "refresher"]`, then append:

```python
DEPLOY = COMPOSE.parent / "deploy" / "deploy.sh"


def test_refresher_runs_its_own_entry_point_off_the_bot_image(compose):
    bot, refresher = compose["services"]["bot"], compose["services"]["refresher"]
    assert refresher["image"] == bot["image"]
    assert refresher["command"] == ["python", "-m", "swingbot.refresher"]
    assert refresher["container_name"] == "swing-refresher"
    assert refresher["restart"] == "unless-stopped"
    assert refresher["env_file"] == bot["env_file"]
    assert refresher["healthcheck"]["test"] == bot["healthcheck"]["test"]


def test_refresher_mounts_exactly_the_bot_state(compose):
    # Same daily-cache volume as bot and admin (spec Operations): the snapshot
    # builders read the bars the scan keeps warm, and nothing else.
    assert compose["services"]["refresher"]["volumes"] == compose["services"]["bot"]["volumes"]


def test_refresher_is_capped_and_never_built_or_published(compose):
    refresher = compose["services"]["refresher"]
    assert refresher["cpus"] == "0.5" and refresher["mem_limit"] == "1g"
    assert "build" not in refresher and "ports" not in refresher


def test_deploy_verifies_the_refresher_runs_the_pulled_image():
    src = DEPLOY.read_text(encoding="utf-8")
    assert "for svc in bot admin refresher; do" in src
    assert "for svc in bot admin; do" not in src
```

- [ ] **Step 2: Update the rollback shape test** in `tests/scripts/test_rollback_to_shape.py`

Replace every `"docker compose stop bot admin"` marker with `"docker compose stop bot admin refresher"`, and every `"docker compose up -d --no-build --wait bot admin"` with `"docker compose up -d --no-build --wait $SERVICES"`. That covers the order list, `test_images_must_still_be_on_ghcr_before_anything_stops` and the v184 reminder test. Then append:

```python
def test_the_refresher_starts_only_if_the_target_image_has_it(src):
    probe = src.index('-c "import swingbot.refresher"')
    assert src.index("scan_paused") < probe < src.index(
        "docker compose up -d --no-build --wait $SERVICES")
    assert 'SERVICES="bot admin"' in src and 'SERVICES="bot admin refresher"' in src
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_compose.py`
Expected: FAIL, `KeyError: 'refresher'` and the deploy-loop assertion.
Run: `python <wt>/scripts/dev/testrun.py file tests/scripts/test_rollback_to_shape.py`
Expected: FAIL, `ValueError: substring not found`.

- [ ] **Step 4: Add the compose service** in `docker-compose.yml`, directly after the `admin` service

```yaml
  refresher:
    # v201: the admin's market refresher. A process of its own, so a slow
    # batch or a long portfolio-state build can neither hold the admin's
    # gunicorn threads nor share a yfinance download lock with the scan and
    # the stop monitor (each process has its own _DOWNLOAD_LOCK). It fetches
    # quotes, quote-currency codes and FX pairs as the tier-5 ADMIN_REFRESH
    # asker, stores the heavy page snapshots, and NOTIFYs `market`. The admin
    # pages only read what it stored. Kill switch: ADMIN_REFRESHER=off puts
    # the admin back on request-time fetching (docs/deploy/DEPLOY_HETZNER.md).
    image: ${SWING_BOT_IMAGE:-swing-bot:latest}
    command: ["python", "-m", "swingbot.refresher"]
    container_name: swing-refresher
    restart: unless-stopped
    # Hard cap, like the bot's: the box has two vCPUs and the admin worker is
    # the one someone is waiting on.
    cpus: "0.5"
    mem_limit: 1g
    env_file:
      - .env
    # Exactly the bot's state mounts (see its comment): the daily-bar cache
    # it reads read-only for snapshots, the FX pair files it refreshes, and
    # .env for hot reload.
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./exports:/app/exports
      - ./market_data:/app/market_data
      - ./.env:/app/.env
      - ./.env.bak:/app/.env.bak
    healthcheck:
      test: ["CMD-SHELL", "kill -0 1 2>/dev/null"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    depends_on:
      db:
        condition: service_healthy
```

Copy the bot's `volumes` list verbatim from the file as it stands in the worktree, so the equality test holds even if the bot's list changed since this plan.

- [ ] **Step 5: Edit the deploy and rollback scripts**

`deploy/deploy.sh`: change `for svc in bot admin; do` to `for svc in bot admin refresher; do`, the comment above it to `# bot/admin/refresher only -- cloudflared ...`, and `==> Both services run the pulled image.` to `==> All three services run the pulled image.`.
`scripts/ops/rollback_to.sh`: step 4 becomes `docker compose stop bot admin refresher`, and step 9's start becomes the probe block from "Decisions fixed here". Keep LF endings and no `sed -i` (`test_it_logs_every_rollback_and_never_sed`).

- [ ] **Step 6: Update `docs/deploy/DEPLOY_HETZNER.md`**

- Line 7: "restarts the Docker services (`bot`, `admin` and, since v201, `refresher`)".
- New section `## The refresher service (v201)`, placed after the section that describes the two services. It says:
  - what the service does (one paragraph, matching the compose comment);
  - a normal deploy starts it, with no manual step;
  - its first cycles after a migration-bearing deploy may log a missing-table error until the `alembic upgrade head` step runs, then recover by themselves;
  - logs: `docker compose logs -f refresher`;
  - health: the admin's `/system` page `refresher` line (`ok` / `stalled` / `off`);
  - kill switch: `python3 scripts/ops/env_set.py ADMIN_REFRESHER off` then `docker compose restart admin refresher`, which puts the admin pages back on request-time fetching exactly as before v201;
  - `rollback_to.sh` stops it with the other writers and starts it only when the target image has it.
- Line 434 (rollback order): add `refresher` to `docker compose restart bot admin`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_compose.py`
Expected: PASS, `0 failed`.
Run: `python <wt>/scripts/dev/testrun.py file tests/scripts/test_rollback_to_shape.py`
Expected: PASS, `0 failed`.
Run: `docker compose -f <wt>/docker-compose.yml config --quiet` and `docker compose -f <wt>/docker-compose.yml --profile tunnel config --quiet`
Expected: exit 0, no output (the CI `compose-lint` checks). If Docker is not available on this machine, say so in the handback; CI runs the same check.
Run: `bash -n <wt>/scripts/ops/rollback_to.sh && bash -n <wt>/deploy/deploy.sh`
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git -C <wt> add docker-compose.yml deploy/deploy.sh scripts/ops/rollback_to.sh docs/deploy/DEPLOY_HETZNER.md tests/db/test_compose.py tests/scripts/test_rollback_to_shape.py
git -C <wt> commit -m "ops(v201): refresher compose service, deploy verification and PITR rollback"
```

