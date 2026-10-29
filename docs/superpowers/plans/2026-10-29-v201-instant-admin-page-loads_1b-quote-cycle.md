# v201 Instant admin page loads, part 1b: quote cycle

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Instant admin page loads](../specs/2026-10-29-v201-instant-admin-page-loads.md)
**Index:** [`_0-index.md`](2026-10-29-v201-instant-admin-page-loads_0-index.md): Goal, Global Constraints, Review Focus, Parallelisation and every cross-task contract live there and bind the task below.

Part scope: V201-6 only, split from part 1 to keep that file under the 1500-line cap. It runs after V201-1 … V201-5 (part 1).

`<wt>` is the implementation worktree's absolute path. Every DB-backed test needs the shared `swing-db` replica (`/replicate-prod-db`) before its first run.

### Task V201-6: Quote cycle: batched fetch, capped fallback, marks, queue drain, FX job, `market` NOTIFY

**Model:** opus — the one place admin market fetching now happens; budget tier, fallback cap and marks decide rate-limit safety and whether spinners ever stop.

**Files:**
- Modify: `swingbot/core/marketdata/data.py` (`refresh_quote_batch`, `_YfCap`, after `get_quote_batch` ~line 195)
- Modify: `swingbot/core/marketdata/shared/layer.py` (`put`, after `last_cached`)
- Modify: `swingbot/core/db/notify.py` (`CHANNELS` gains `"market"`), `swingbot/core/db/events.py` (one `FILE_PUBLISHERS` entry: `tests/db/test_file_publishers.py` demands a publisher per SSE event)
- Modify: `swingbot/refresher/loop.py` (`STEPS` default, NOTIFY at the end of `run_cycle`)
- Create: `swingbot/refresher/quotes.py`
- Test: `tests/marketdata/test_refresh_quote_batch.py`, `tests/refresher/test_quote_cycle.py`; modify `tests/db/test_notify_ddl.py` and `tests/admin/test_sse_contract.py` (the ledger's `tests/db/test_notify.py` does not exist; these two pin the channel tuple)

**Interfaces:**
- Consumes: `Asker.ADMIN_REFRESH`, `admin_refresh.quote_mark_key`, `config.ADMIN_REFRESH_YF_FALLBACK_CAP`, `config.ADMIN_REFRESH_MARK_TIMEOUT_S` (V201-1); `refresh_mark_repo().mark/clear`, `quote_currency_repo().get_many` (V201-3); `fx.refresh_quote_codes`, `fx.refresh_pair_frames` (V201-4); `loop.CycleContext`, `loop.STEPS`, `loop.run_cycle`, `SymbolSet` (V201-5).
- Produces (ledger): `data.refresh_quote_batch(tickers, *, yf_limit: int) -> dict[str, QuoteDetail]` (keys upper-cased; only values fetched this call); `layer.put(kind: DataKind, values: dict[str, Any], *, provider: str, encode=identity) -> None`; `notify.CHANNELS[-1] == "market"`; `quotes.quote_step(ctx) -> None`, `quotes.fx_step(ctx) -> None`; `loop.STEPS` starts as `[quotes.quote_step, quotes.fx_step]`. Index symbols are refreshed through `tape.refresh_tape(..., asker=Asker.ADMIN_REFRESH, max_age_s=0)` and marked under `quote_mark_key`. `run_cycle` calls `notify.publish("market")` once when `report.changed`; `quotes._announce_marks(ctx)` publishes once more right after the first marks of a cycle are set, so the SPA sees `refreshing: true` for refreshes the refresher started on its own (partner decision, spec § What the partner decided).

- [ ] **Step 1: Write the failing batch test** `tests/marketdata/test_refresh_quote_batch.py`

```python
"""v201: the refresher's batched quote call -- tier 5, always fetches, capped yfinance."""
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.marketdata import data
from swingbot.core.marketdata.shared import layer
from swingbot.core.marketdata.shared.kinds import Asker, DataKind, QuoteDetail

NOW = datetime.now(timezone.utc)


def _q(sym, source="alpaca-iex", price=10.0):
    return QuoteDetail(sym, price, NOW, None, None, NOW, source)


@pytest.fixture
def shared(db_committed, db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    side_engine.reset()
    yield db_committed
    side_engine.reset()


@pytest.fixture
def provider(monkeypatch):
    calls = {"latest": [], "yf": []}

    def latest(tickers, yf_fetch):           # Alpaca answers nothing: every symbol falls back
        calls["latest"].append(list(tickers))
        got = yf_fetch(list(tickers))
        return {t: got.get(t) or (_q(t, "gold-api") if t == "XAUUSD" else None) for t in tickers}

    def yf(tickers):
        calls["yf"].append(list(tickers))
        return {t: _q(t, "yfinance-1m") for t in tickers}
    monkeypatch.setattr(data.router, "latest_quotes", latest)
    monkeypatch.setattr(data, "_yf_quote_details", yf)
    return calls


def test_refresh_always_fetches_and_writes_the_shared_cache(shared, provider):
    data.refresh_quote_batch(["aapl"], yf_limit=5)
    got = data.refresh_quote_batch(["AAPL"], yf_limit=5)
    assert len(provider["latest"]) == 2 and got["AAPL"].price == 10.0
    assert layer.last_cached(DataKind.QUOTE, ["AAPL"])["AAPL"].value["price"] == 10.0


def test_yfinance_fallback_is_capped_and_zero_skips_it(shared, provider):
    got = data.refresh_quote_batch(["A", "B", "C"], yf_limit=2)
    assert provider["yf"] == [["A", "B"]] and set(got) == {"A", "B"}
    provider["yf"].clear()
    assert data.refresh_quote_batch(["A", "B"], yf_limit=0) == {} and provider["yf"] == []


def test_spot_metals_are_written_for_the_never_fetch_read(shared, provider):
    got = data.refresh_quote_batch(["XAUUSD"], yf_limit=0)
    assert got["XAUUSD"].source == "gold-api"
    assert layer.last_cached(DataKind.QUOTE, ["XAUUSD"])["XAUUSD"].value["source"] == "gold-api"


def test_stop_monitor_still_fetches_past_its_window_after_a_refresher_write(shared, provider):
    data.refresh_quote_batch(["AAPL"], yf_limit=5)
    shared.execute(sa.text("UPDATE market_cache SET fetched_at = now() - interval '20 seconds'"))
    shared.commit()
    data.get_quote_batch(["AAPL"], asker=Asker.STOP_MONITOR)      # window 15 s
    assert len(provider["latest"]) == 2
```

- [ ] **Step 2: Write the failing cycle test** `tests/refresher/test_quote_cycle.py`

```python
"""v201: the quote and FX steps, their marks, and the market NOTIFYs (marks set, values landed)."""
import pathlib
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata.shared.kinds import Asker, QuoteDetail
from swingbot.refresher import loop, quotes
from swingbot.refresher.symbols import SymbolSet
from tests.refresher.test_loop import FakeBeat, FakeQueue

UTC = timezone.utc
REGULAR = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
REPO = pathlib.Path(__file__).resolve().parents[2]


class FakeMarks:
    def __init__(self):
        self.events = []

    def mark(self, keys, *, timeout_s, now=None, conn=None):
        self.events.append(("mark", tuple(keys), timeout_s))

    def clear(self, keys, *, error=None, now=None, conn=None):
        if keys:
            self.events.append(("clear", tuple(keys), error))


@pytest.fixture
def cycle(monkeypatch):
    marks, published, batches, tapes = FakeMarks(), [], [], []

    def batch(tickers, *, yf_limit):
        batches.append((list(tickers), yf_limit))
        return {t: QuoteDetail(t, 1.0, REGULAR, None, None, REGULAR,
                               "yfinance-1m" if t == "YF" else "alpaca-iex")
                for t in tickers if t != "BAD"}
    monkeypatch.setattr(quotes, "refresh_mark_repo", lambda: marks)
    monkeypatch.setattr(quotes.data, "refresh_quote_batch", batch)
    monkeypatch.setattr(quotes.tape, "refresh_tape",
                        lambda syms, *, asker, max_age_s=None: tapes.append((list(syms), asker)) or {})
    monkeypatch.setattr(loop, "refresh_queue_repo", FakeQueue)
    monkeypatch.setattr(loop, "refresher_heartbeat_repo", FakeBeat)
    monkeypatch.setattr(loop, "symbol_set", lambda: SymbolSet(("AAPL", "BAD", "YF"), ("^GSPC",)))
    monkeypatch.setattr(loop, "_scan_running", lambda: False)
    monkeypatch.setattr(loop, "_last_full", None)
    monkeypatch.setattr(loop, "STEPS", [quotes.quote_step])
    monkeypatch.setattr(loop.notify, "publish", published.append)
    return marks, published, batches, tapes


def test_failed_symbol_clears_mark_with_error(cycle):
    marks, published, batches, tapes = cycle
    report = loop.run_cycle(REGULAR)
    assert batches == [(["AAPL", "BAD", "YF"], 25)]
    assert ("clear", ("quote:AAPL", "quote:YF"), None) in marks.events
    assert ("clear", ("quote:BAD",), "no quote") in marks.events
    assert marks.events[0] == ("mark", ("quote:AAPL", "quote:BAD", "quote:YF"), 120.0)
    assert (report.quotes_ok, report.quotes_missed, report.fallback_used) == (("AAPL", "YF"), ("BAD",), 1)
    assert tapes == [(["^GSPC"], Asker.ADMIN_REFRESH)]
    assert published == ["market", "market"] and report.changed is True   # marks set, then values landed


def test_provider_raises_keeps_last_values_and_still_beats(cycle, monkeypatch):
    marks, published, _batches, _tapes = cycle
    beats = FakeBeat()
    monkeypatch.setattr(loop, "refresher_heartbeat_repo", lambda: beats)

    def down(tickers, *, yf_limit):
        raise RuntimeError("alpaca 503")
    monkeypatch.setattr(quotes.data, "refresh_quote_batch", down)
    report = loop.run_cycle(REGULAR)
    assert report.error == "RuntimeError: alpaca 503"
    assert ("clear", ("quote:AAPL", "quote:BAD", "quote:YF"), "RuntimeError: alpaca 503") in marks.events
    assert beats.beats[-1]["last_error"] == "RuntimeError: alpaca 503"


def test_scan_running_skips_yfinance_and_the_yahoo_tape(cycle, monkeypatch):
    marks, _published, batches, tapes = cycle
    monkeypatch.setattr(loop, "_scan_running", lambda: True)
    loop.run_cycle(REGULAR)
    assert batches[0][1] == 0 and tapes == []
    assert ("clear", ("quote:BAD",), "no quote (yfinance fallback skipped during a scan)") in marks.events


def test_nothing_to_do_publishes_nothing(cycle, monkeypatch):
    _marks, published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: SymbolSet((), ()))
    loop.run_cycle(REGULAR)
    assert batches == [] and published == []


def test_fx_step_resolves_codes_for_every_traded_ticker_and_refreshes_pairs(monkeypatch):
    seen = {}
    monkeypatch.setattr(quotes, "_traded_tickers", lambda: ["ASML.AS", "AAPL"])
    monkeypatch.setattr(quotes.fx, "refresh_quote_codes", lambda syms, *, now=None: seen.setdefault("codes", syms))
    monkeypatch.setattr(quotes, "quote_currency_repo", lambda: type("R", (), {"get_many": staticmethod(
        lambda syms, conn=None: {"ASML.AS": {"code": "EUR"}, "AAPL": {"code": "USD"}, "X": {"code": None}})})())
    monkeypatch.setattr(quotes.fx, "refresh_pair_frames", lambda codes: seen.setdefault("pairs", set(codes)))
    full = loop.CycleContext(REGULAR, "regular", SymbolSet(("AAPL", "X"), ()), ["NEW"], [], False,
                             loop.CycleReport("regular", 30.0))
    quotes.fx_step(full)
    assert seen["codes"] == ["AAPL", "X", "NEW", "ASML.AS"] and seen["pairs"] == {"EUR", "USD"}
    seen.clear()
    quotes.fx_step(loop.CycleContext(REGULAR, "regular", SymbolSet((), ()), ["NEW"], [], False,
                                     loop.CycleReport("regular", 30.0)))
    assert seen == {"codes": ["NEW"]}          # queue-only cycle: no traded sweep, no pair refresh


def test_refresher_never_sets_the_admin_lock_timeout_or_writes_ohlcv():
    for path in (REPO / "swingbot" / "refresher").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for banned in ("set_default_lock_timeout", "update_cache", "refresh_symbol", "data_refresh"):
            assert banned not in text, (path.name, banned)
```

- [ ] **Step 3: Update the channel pins**

`tests/db/test_notify_ddl.py`: append `"market"` to the expected `CHANNELS` tuple. `tests/admin/test_sse_contract.py`: add `"market"` to `EXPECTED_EVENTS`, add `SPA_PENDING = {"market"}  # V201-16 subscribes the SPA; remove this set then` and change the last assertion of `test_the_spa_subscribes_to_no_event_this_backend_cannot_raise` to `assert listened | SPA_PENDING == EXPECTED_EVENTS` (true before and after V201-16).

- [ ] **Step 4: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_refresh_quote_batch.py`, `... file tests/refresher/test_quote_cycle.py`, `... file tests/db/test_notify_ddl.py`
Expected: FAIL (`AttributeError: ... refresh_quote_batch`, `ImportError: ... quotes`, tuple mismatch).

- [ ] **Step 5: `data.refresh_quote_batch` and `layer.put`**

```python
class _YfCap:
    """The refresher's yfinance budget for one call: Alpaca misses and yfinance-only
    names share at most `limit` symbols; 0 = never call yfinance."""

    def __init__(self, limit: int):
        self.left = max(0, int(limit))

    def __call__(self, tickers) -> dict:
        take = list(tickers)[:self.left]
        self.left -= len(take)
        return _yf_quote_details(take) if take else {}


def refresh_quote_batch(tickers, *, yf_limit: int) -> dict:
    """v201 refresher: one batched quote call at ADMIN_REFRESH (tier 5) that always
    fetches (max_age_s=0) and lands in the shared cache. Spot metals, which the layer
    never keys, are written with layer.put so the never-fetch read finds them."""
    tickers = _normalise_tickers(tickers)
    spot, rest = spot_metals.split_spot(tickers)
    yf = _YfCap(yf_limit)
    out: dict = {}
    if rest:
        with router.asker_scope(Asker.ADMIN_REFRESH):
            entries = layer.get(DataKind.QUOTE, rest, lambda syms: router.latest_quotes(list(syms), yf),
                                asker=Asker.ADMIN_REFRESH, provider=PROVIDER_ALPACA, max_age_s=0,
                                encode=QuoteDetail.to_doc, decode=QuoteDetail.from_doc)
        out.update({t: e.value for t, e in entries.items()
                    if e.outcome in ("fetched", "shared-wait") and e.value is not None and e.value.price})
    if spot:
        with router.asker_scope(Asker.ADMIN_REFRESH):
            got = router.latest_quotes(spot, yf) or {}
        priced = {t: q for t, q in got.items() if q is not None and q.price}
        layer.put(DataKind.QUOTE, priced, provider="spot", encode=QuoteDetail.to_doc)
        out.update(priced)
    return out
```

`layer.put`: a no-op unless `config.MARKETDATA_LAYER == "on"` and `values` is non-empty; otherwise one `_write([...])` of rows shaped like `_cache_row` (`key=cache_key(kind, s)`, `kind=kind.value`, `symbol=s.upper()`, `fetched_at=_now()`, `source=provider`, `value=encode(v)`) for every non-`None` value. Best effort, like `_write`.

- [ ] **Step 6: `swingbot/refresher/quotes.py`**

Module-level imports the tests patch: `data`, `fx`, `tape` (`swingbot.core.marketdata.shared.tape`), `refresh_mark_repo`, `quote_currency_repo`; `CycleContext` only under `TYPE_CHECKING` (loop imports this module).

```python
def quote_step(ctx: "CycleContext") -> None:
    wanted = list(dict.fromkeys([*ctx.symbols.quotes, *(s.upper() for s in ctx.queued_quotes)]))
    if wanted:
        _refresh_quotes(ctx, wanted)
    if ctx.symbols.index and not ctx.scan_running:
        _refresh_index(ctx, list(ctx.symbols.index))


def _refresh_quotes(ctx, wanted: list[str]) -> None:
    marks = refresh_mark_repo()
    keys = [admin_refresh.quote_mark_key(s) for s in wanted]
    marks.mark(keys, timeout_s=float(config.ADMIN_REFRESH_MARK_TIMEOUT_S))
    _announce_marks(ctx)                        # partner rule: spinner shows during background refreshes too
    ctx.report.changed = True
    limit = 0 if ctx.scan_running else int(config.ADMIN_REFRESH_YF_FALLBACK_CAP)
    try:
        got = data.refresh_quote_batch(wanted, yf_limit=limit)
    except Exception as exc:
        marks.clear(keys, error=f"{type(exc).__name__}: {exc}")
        raise                                   # loop records it; last values stay cached
    ok = [s for s in wanted if s in got]
    missed = [s for s in wanted if s not in got]
    marks.clear([admin_refresh.quote_mark_key(s) for s in ok])
    marks.clear([admin_refresh.quote_mark_key(s) for s in missed], error=_miss_reason(ctx))
    ctx.report.quotes_ok, ctx.report.quotes_missed = tuple(ok), tuple(missed)
    ctx.report.fallback_used = sum(1 for q in got.values() if str(q.source).startswith("yfinance"))
```

`_announce_marks(ctx)` publishes `notify.publish("market")` (through the loop's `_guard`, never raising) the first time it is called in a cycle and sets `ctx.marks_announced = True` (a new `CycleContext` field, default `False`) so later steps in the same cycle do not publish again; `_refresh_index` calls it too. `_miss_reason(ctx)` is `"no quote (yfinance fallback skipped during a scan)"` when `ctx.scan_running`, else `"no quote"`. `_refresh_index(ctx, syms)` marks their quote keys, calls `tape.refresh_tape(syms, asker=Asker.ADMIN_REFRESH, max_age_s=0)`, clears the marks (with `"no quote"` for symbols absent from the reply, the exception text on a raise, re-raised) and sets `ctx.report.changed = True`. Skipped while a scan runs: the tape is a yfinance call (spec "Calls made": the fallback is skipped during scans).

`fx_step(ctx)`: `symbols = [*ctx.symbols.quotes, *queued]`, plus `_traded_tickers()` on a full cycle (`ctx.symbols.quotes` non-empty), de-duplicated in that order; nothing to do on an empty list. `fx.refresh_quote_codes(symbols, now=ctx.now)`; on a full cycle only, `fx.refresh_pair_frames({row["code"] for row in quote_currency_repo().get_many(symbols).values() if row.get("code")})`. `_traded_tickers()` is one `SELECT DISTINCT ticker FROM trades` on `engine.get_engine()` (closed trades' amounts are converted too, and their tickers are in no symbol set); an exception reads as `[]`.

- [ ] **Step 7: Wire the loop, channel and publisher**

`loop.py`: `from swingbot.refresher import quotes` and `from swingbot.core.db import notify`; `STEPS: list[Callable[[CycleContext], None]] = [quotes.quote_step, quotes.fx_step]`; just before `return report` in `run_cycle`: `if report.changed: _guard("refresher.notify", lambda: notify.publish("market"))`. `notify.py`: `CHANNELS` gains `"market"` as its last element (the SPA event contract grows by one; V201-16 subscribes). `events.py`: add `"admin market refresher cycle (swingbot.refresher.loop.run_cycle)": "market",` to `FILE_PUBLISHERS` with a comment: not a file, but the same "raises its concern itself through notify.publish" rule; no table trigger; a cycle raises at most two events (marks set, values landed).

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <f>` for `tests/marketdata/test_refresh_quote_batch.py`, `tests/refresher/test_quote_cycle.py`, `tests/refresher/test_loop.py`, `tests/db/test_notify_ddl.py`, `tests/db/test_file_publishers.py`, `tests/db/test_trigger_coverage.py`, `tests/admin/test_sse_contract.py`, `tests/marketdata/test_quote_layer.py`, `tests/marketdata/test_shared_layer.py`; then `python <wt>/scripts/dev/complexity_gate.py`
Expected: all PASS; gate clean.

- [ ] **Step 9: Commit**

```bash
git -C <wt> add swingbot/core/marketdata/data.py swingbot/core/marketdata/shared/layer.py swingbot/core/db/notify.py swingbot/core/db/events.py swingbot/refresher/loop.py swingbot/refresher/quotes.py tests/marketdata/test_refresh_quote_batch.py tests/refresher/test_quote_cycle.py tests/db/test_notify_ddl.py tests/admin/test_sse_contract.py
git -C <wt> commit -m "feat(v201): refresher quote cycle -- batched tier-5 fetch, capped fallback, marks, FX job, market event"
```

