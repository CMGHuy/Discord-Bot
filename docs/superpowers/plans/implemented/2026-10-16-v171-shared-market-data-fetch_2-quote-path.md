# v171 Shared market-data fetch. Part 2: quote path (V171-7..V171-10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V171-9:" -A 300 docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_2-quote-path.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v171-shared-market-data-fetch-design.md`](../specs/2026-10-16-v171-shared-market-data-fetch-design.md) (this part: D1 "one door" for quotes, D2 quote windows and the stored quote stamp, D5 "the 5 s re-quote must name which feed answers when IEX is stale", D6 money-first budget and shared breaker, D8 "trade_monitor and the plan manager share one quote fetch per tick", D9 counts from worker processes)
**Index:** [`2026-10-16-v171-shared-market-data-fetch_0-index.md`](2026-10-16-v171-shared-market-data-fetch_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v171-shared-market-data-fetch` (created in V171-1). Never `cd`; use `git -C $WT` and `python $WT/scripts/dev/testrun.py file <test>`. All file paths below are relative to `$WT`. After every task run `git -C $R status --short` and confirm the main tree is clean.

**Order.** Strictly V171-7 -> V171-8 -> V171-9 -> V171-10 (V171-7 and V171-8 both edit `router.py`; V171-9 needs `router.latest_quotes` and the budgeted router; V171-10 needs `data.get_quote_batch`). All four need part 1 (V171-1..V171-6) committed.

**Consumed from part 1 (ledger names only):** `swingbot.core.marketdata.shared.kinds`: `Asker` (`.priority`, `.window_s(kind)`), `DataKind.QUOTE`, `PROVIDER_ALPACA`, `PROVIDER_YF`, `Entry` (`value`, `fetched_at`, `source`, `outcome`, `age_s()`), `QuoteDetail` (`symbol`, `price`, `trade_at`, `bid`, `ask`, `quote_at`, `source`, `mid()`, `to_doc()`, `from_doc()`), `resolve_asker`; `shared.budget`: `take`, `breaker_allows`, `breaker_record`, `BudgetDeferred` (part 1 header: the layer turns a `BudgetDeferred` raised inside `fetch` into `budget-deferred` outcomes and never takes a token itself); `shared.counters`: `snapshot_and_clear`, `merge`; `shared.layer.get`; `swingbot.core.db.side_engine.reset`.

**Decisions this part fixes** (inside the ledger's contracts):

- **`QuoteDetail.source` names who supplied `price`.** `"alpaca-iex"` (the live feed's name), `"yfinance-1m"` or `"spot"`. `bid`, `ask` and `quote_at` are always Alpaca's IEX quote when Alpaca answered, even when `price` came from the yfinance fallback. So V171-18's order (trade < 60 s, then IEX mid < 60 s, then yfinance 1-minute bar < 60 s) can be read off one `QuoteDetail`.
- **One provider call costs one token, taken at the call site.** The router takes Alpaca tokens and `yf_safe.download` takes yfinance tokens, both at `router.current_asker()`. Callers that run in a spawned worker enter `router.asker_scope(asker)` inside the worker, because a contextvar does not cross a process.
- **An Alpaca denial at any tier keeps today's behaviour (no token, so the router falls back to yfinance).** A yfinance denial raises `BudgetDeferred` at tiers 4-5 only, which `_yf_quote_details` re-raises so the layer can record `budget-deferred`.
- **Fresh-only stays fresh-only.** `get_quote_batch` gains a keyword `fresh_only: bool = False` (an addition to the ledger signature, not a change). Trading callers pass it. It drops any entry whose outcome is `budget-deferred` or whose fetch age exceeds the asker's window.
- **`count` mode makes the same provider calls as today.** The in-process 15 s display caches still short-circuit there, and the monitor and the plan manager each still make their own call. `on` mode is the first mode in which they share.

---

# Phase 2 — Quote path: timestamped quotes, shared budget, layer-backed quote API, one quote per monitor tick

### Task V171-7: Timestamped quotes: `AlpacaProvider.latest_quotes`, `router.latest_quotes`, yfinance 1-minute timestamped fallback

**Model:** sonnet — one provider method and one router function inside `marketdata/providers`, shapes fixed by V171-2

**Files:**
- Modify: `swingbot/core/marketdata/providers/alpaca_provider.py` (beside `latest_prices`, :146-167)
- Modify: `swingbot/core/marketdata/providers/router.py` (`_attempt` :175-183, new `latest_quotes` after `latest_prices` :368-385)
- Modify: `swingbot/core/marketdata/data.py` (new `_yf_quote_details` after `_yf_batch_prices` :225-250)
- Modify: `swingbot/core/marketdata/yf_safe.py` (one re-export line)
- Test: `tests/marketdata/test_alpaca_provider.py`, `tests/marketdata/test_provider_router.py`

**Interfaces:**
- Consumes: `QuoteDetail` (V171-2, `swingbot.core.marketdata.shared.kinds`); `BudgetDeferred` (V171-5, `swingbot.core.marketdata.shared.budget`).
- Produces:
  - `AlpacaProvider.latest_quotes(self, tickers: list[str], max_trade_age_s: int) -> dict[str, QuoteDetail]`: one `get_stock_snapshot` on the live feed. `price`/`trade_at` come from `snap.latest_trade` under the same rule as `_fresh_price` (a regular-session trade older than `max_trade_age_s` gives `price=None, trade_at=None`). `bid`/`ask`/`quote_at` come from `snap.latest_quote` (`bid_price`, `ask_price`, `timestamp`; a non-positive side is `None`, and `quote_at` is `None` unless both sides exist). `source = f"alpaca-{feed}"` (`"alpaca-iex"` by default). A symbol with neither a price nor both quote sides is absent.
  - `router.latest_quotes(tickers: list[str], yf_fetch: Callable[[list[str]], dict[str, QuoteDetail]]) -> dict[str, QuoteDetail]`: the same split, fallback and spot rules as `latest_prices`. Alpaca-eligible symbols without an Alpaca `price` are re-asked from `yf_fetch` (tagged `SOURCE_FALLBACK` in `_last_source`). When the fallback answers, its price is merged with Alpaca's `bid`/`ask`/`quote_at`. Spot symbols take `spot_metals.quote_with_reason` (`source="spot"`, `trade_at = SpotQuote.updated_at`). `latest_prices` is unchanged.
  - `data._yf_quote_details(tickers: list[str]) -> dict[str, QuoteDetail]`: one `yf_safe.download(" ".join(tickers), period="1d", interval="1m", group_by="ticker", prepost=True, progress=False)`. `price` is the last non-NaN close > 0, `trade_at` that bar's timestamp in UTC, `source="yfinance-1m"`, `bid`/`ask`/`quote_at` `None`. `{}` on `DownloadBusy` or any error. `BudgetDeferred` is re-raised (V171-8 starts raising it; the clause is written now so V171-8 does not touch this function).
  - `yf_safe.BudgetDeferred` (re-export of `budget.BudgetDeferred`, part 1's rule).

- [ ] **Step 1: Write the failing provider tests**

Append to `tests/marketdata/test_alpaca_provider.py` (reuses its `FakeClient`, `NOW` = 11:00 ET in session, `_prov`):

```python
from swingbot.core.marketdata.shared.kinds import QuoteDetail


def _qsnap(price, trade_ts, bid=None, ask=None, quote_ts=None):
    trade = None if price is None else SimpleNamespace(price=price, timestamp=trade_ts)
    quote = (None if bid is None and ask is None
             else SimpleNamespace(bid_price=bid, ask_price=ask, timestamp=quote_ts))
    return SimpleNamespace(latest_trade=trade, latest_quote=quote)


def test_latest_quotes_carries_trade_and_quote_timestamps():
    t_trade = NOW - pd.Timedelta(seconds=3)
    t_quote = NOW - pd.Timedelta(seconds=1)
    c = FakeClient(snaps={"AAPL": _qsnap(190.0, t_trade, 189.9, 190.1, t_quote)})
    out = _prov(c).latest_quotes(["AAPL"], 300)
    assert out == {"AAPL": QuoteDetail(symbol="AAPL", price=190.0, trade_at=t_trade,
                                       bid=189.9, ask=190.1, quote_at=t_quote,
                                       source="alpaca-iex")}
    assert str(c.requests[0].feed.value) == "iex"


def test_latest_quotes_stale_trade_in_session_keeps_the_quote():
    t_quote = NOW - pd.Timedelta(seconds=2)
    c = FakeClient(snaps={"AAPL": _qsnap(190.0, NOW - pd.Timedelta(minutes=20),
                                         189.0, 191.0, t_quote)})
    q = _prov(c).latest_quotes(["AAPL"], 300)["AAPL"]
    assert q.price is None and q.trade_at is None
    assert (q.bid, q.ask, q.quote_at) == (189.0, 191.0, t_quote)
    assert q.mid() == 190.0


def test_latest_quotes_symbol_with_no_price_and_one_sided_quote_is_absent():
    c = FakeClient(snaps={"AAPL": _qsnap(None, None, 0.0, 191.0, NOW)})
    assert _prov(c).latest_quotes(["AAPL"], 300) == {}


def test_latest_quotes_rekeys_class_shares():
    c = FakeClient(snaps={"BRK.B": _qsnap(410.0, NOW - pd.Timedelta(seconds=5))})
    assert set(_prov(c).latest_quotes(["BRK-B"], 300)) == {"BRK-B"}


def test_latest_quotes_old_trade_outside_session_is_kept_with_its_timestamp():
    sat = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)
    friday_close = sat - pd.Timedelta(hours=23)
    c = FakeClient(snaps={"AAPL": _qsnap(190.0, friday_close)})
    prov = ap.AlpacaProvider("k", "s", "iex", client=c, now=lambda: sat)
    q = prov.latest_quotes(["AAPL"], 300)["AAPL"]
    assert q.price == 190.0 and q.trade_at == friday_close
```

- [ ] **Step 2: Write the failing router and yfinance tests**

In `tests/marketdata/test_provider_router.py`, give `FakeProvider.__init__` a `quotes=None` parameter (`self.quotes = quotes or {}`, the other defaults unchanged) and this method:

```python
    def latest_quotes(self, tickers, max_age):
        self._maybe(); return {t: q for t, q in self.quotes.items() if t in tickers}
```

Then append:

```python
from datetime import datetime, timezone
from swingbot.core.marketdata.shared.kinds import QuoteDetail

_T = datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc)


def _q(sym, price, source="alpaca-iex", bid=None, ask=None):
    return QuoteDetail(symbol=sym, price=price, trade_at=_T if price else None,
                       bid=bid, ask=ask, quote_at=_T if bid else None, source=source)


def yf_quotes(calls, prices):
    def f(tickers):
        calls.append(list(tickers))
        return {t: _q(t, prices[t], source="yfinance-1m") for t in tickers if t in prices}
    return f


def test_latest_quotes_alpaca_hit_makes_no_yfinance_call(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider(quotes={"AAPL": _q("AAPL", 190.0)})); calls = []
    out = router.latest_quotes(["AAPL"], yf_quotes(calls, {}))
    assert calls == [] and out["AAPL"].price == 190.0
    assert router.last_source("AAPL") == "alpaca"


def test_latest_quotes_stale_trade_falls_back_and_keeps_alpaca_bid_ask(enabled, monkeypatch):
    stale = _q("AAPL", None, bid=189.0, ask=191.0)
    _use(monkeypatch, FakeProvider(quotes={"AAPL": stale})); calls = []
    out = router.latest_quotes(["AAPL"], yf_quotes(calls, {"AAPL": 190.4}))
    assert calls == [["AAPL"]]
    q = out["AAPL"]
    assert (q.price, q.source) == (190.4, "yfinance-1m")
    assert (q.bid, q.ask, q.quote_at) == (189.0, 191.0, _T)
    assert router.last_source("AAPL") == "yfinance-fallback"


def test_latest_quotes_fallback_miss_keeps_the_alpaca_quote_only(enabled, monkeypatch):
    stale = _q("AAPL", None, bid=189.0, ask=191.0)
    _use(monkeypatch, FakeProvider(quotes={"AAPL": stale})); calls = []
    out = router.latest_quotes(["AAPL"], yf_quotes(calls, {}))
    assert out["AAPL"] == stale


def test_latest_quotes_ineligible_symbol_is_plain_yfinance(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider()); calls = []
    out = router.latest_quotes(["SAP.DE"], yf_quotes(calls, {"SAP.DE": 50.0}))
    assert calls == [["SAP.DE"]] and out["SAP.DE"].source == "yfinance-1m"
    assert router.last_source("SAP.DE") == "yfinance"


def test_latest_quotes_spot_metal_takes_the_spot_quote(enabled, monkeypatch):
    from swingbot.core.marketdata import spot_metals
    prov = FakeProvider(); _use(monkeypatch, prov); calls = []
    monkeypatch.setattr(spot_metals, "quote_with_reason",
                        lambda t, **k: (spot_metals.SpotQuote(2400.0, _T), None))
    out = router.latest_quotes(["XAUUSD"], yf_quotes(calls, {}))
    assert prov.calls == 0 and calls == []
    assert out["XAUUSD"] == QuoteDetail(symbol="XAUUSD", price=2400.0, trade_at=_T,
                                        bid=None, ask=None, quote_at=None, source="spot")


def test_latest_quotes_runs_on_the_quote_pool(enabled, monkeypatch):
    import threading
    seen = []

    class Probe(FakeProvider):
        def latest_quotes(self, tickers, max_age):
            seen.append(threading.current_thread().name)
            return {}
    _use(monkeypatch, Probe())
    router.latest_quotes(["AAPL"], yf_quotes([], {}))
    assert seen and seen[0].startswith("alpaca-quote")


def test_yf_quote_details_stamps_the_last_bar_in_utc(monkeypatch):
    from swingbot.core.marketdata import data, yf_safe
    idx = pd.DatetimeIndex(["2026-10-16 10:58", "2026-10-16 10:59"]).tz_localize("America/New_York")
    cols = pd.MultiIndex.from_product([["AAPL"], ["Close"]])
    raw = pd.DataFrame([[190.0], [190.5]], index=idx, columns=cols)
    monkeypatch.setattr(yf_safe, "download", lambda *a, **k: raw)
    q = data._yf_quote_details(["AAPL", "MSFT"])
    assert set(q) == {"AAPL"}
    assert q["AAPL"].price == 190.5 and q["AAPL"].source == "yfinance-1m"
    assert q["AAPL"].trade_at == datetime(2026, 10, 16, 14, 59, tzinfo=timezone.utc)


def test_yf_quote_details_busy_lock_is_empty(monkeypatch):
    from swingbot.core.marketdata import data, yf_safe

    def busy(*a, **k):
        raise yf_safe.DownloadBusy("busy")
    monkeypatch.setattr(yf_safe, "download", busy)
    assert data._yf_quote_details(["AAPL"]) == {}


def test_yf_quote_details_reraises_budget_deferred(monkeypatch):
    from swingbot.core.marketdata import data, yf_safe

    def deferred(*a, **k):
        raise yf_safe.BudgetDeferred("tier 5")
    monkeypatch.setattr(yf_safe, "download", deferred)
    with pytest.raises(yf_safe.BudgetDeferred):
        data._yf_quote_details(["AAPL"])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_alpaca_provider.py` and `python $WT/scripts/dev/testrun.py file tests/marketdata/test_provider_router.py`
Expected: the new tests FAIL with `AttributeError: ... has no attribute 'latest_quotes'` / `'_yf_quote_details'` / `'BudgetDeferred'`. Every pre-existing test passes.

- [ ] **Step 4: Implement `AlpacaProvider.latest_quotes` in `alpaca_provider.py`**

Add `from swingbot.core.marketdata.shared.kinds import QuoteDetail`. Add two private helpers beside `_fresh_price`, plus the method. `_fresh_price` stays untouched, so `latest_prices` keeps its exact behaviour.

```python
    def _quote_sides(self, snap):
        """(bid, ask, quote_at) from the snapshot's latest quote; a missing or
        non-positive side is None, and quote_at is None unless both sides exist."""
        quote = getattr(snap, "latest_quote", None)
        if quote is None:
            return None, None, None
        bid = float(quote.bid_price) if quote.bid_price and quote.bid_price > 0 else None
        ask = float(quote.ask_price) if quote.ask_price and quote.ask_price > 0 else None
        return bid, ask, (quote.timestamp if bid and ask else None)

    def _detail(self, ticker, snap, now, max_age_s):
        price = self._fresh_price(snap, now, max_age_s)
        bid, ask, quote_at = self._quote_sides(snap)
        if price is None and quote_at is None:
            return None
        trade_at = snap.latest_trade.timestamp if price is not None else None
        return QuoteDetail(symbol=ticker, price=price, trade_at=trade_at, bid=bid, ask=ask,
                           quote_at=quote_at, source=f"alpaca-{self._live_feed.value}")

    def latest_quotes(self, tickers, max_trade_age_s):
        """v171: latest_prices with timestamps and the IEX bid/ask. One snapshot call."""
        by_symbol = {to_alpaca_symbol(t): t for t in tickers}
        req = StockSnapshotRequest(symbol_or_symbols=list(by_symbol), feed=self._live_feed)
        snaps = self._call("get_stock_snapshot", req) or {}
        now = self._now()
        out = {}
        for sym, snap in snaps.items():
            detail = self._detail(by_symbol[sym], snap, now, max_trade_age_s) if sym in by_symbol else None
            if detail is not None:
                out[detail.symbol] = detail
        return out
```

- [ ] **Step 5: Implement `router.latest_quotes` and put it on the quote pool**

In `router.py`: import `dataclasses` and `QuoteDetail`. Add the module constant `_QUOTE_METHODS = frozenset({"latest_prices", "latest_quotes"})` and change `_attempt`'s pool choice to `pool = _quote_pool if method in _QUOTE_METHODS else _pool`. That line is the only change to existing code. Then add, after `latest_prices`:

```python
def _with_alpaca_quote(fallback: QuoteDetail, alpaca: QuoteDetail | None) -> QuoteDetail:
    """The fallback's price, the Alpaca IEX bid/ask (the D5 midpoint source)."""
    if alpaca is None or alpaca.quote_at is None:
        return fallback
    return dataclasses.replace(fallback, bid=alpaca.bid, ask=alpaca.ask, quote_at=alpaca.quote_at)

def _spot_quotes(spot) -> dict:
    """v171: spot_metals' quote as a QuoteDetail -- never cached here, never Alpaca."""
    out = {}
    for ticker in spot:
        quote, reason = spot_metals.quote_with_reason(ticker)
        if quote is None:
            _spot_miss[str(ticker).upper().strip()] = reason
            continue
        out[ticker] = QuoteDetail(symbol=ticker, price=quote.price, trade_at=quote.updated_at,
                                  bid=None, ask=None, quote_at=None, source="spot")
        _last_source[ticker] = SOURCE_SPOT
    return out

def latest_quotes(tickers, yf_fetch):
    """v171: latest_prices' routing with timestamps. A symbol whose Alpaca
    answer has no fresh trade price is re-asked from yfinance, keeping the
    Alpaca bid/ask on the merged detail."""
    spot, tickers = spot_metals.split_spot(tickers)
    wanted, rest = _split(tickers)
    got = (_attempt("latest_quotes", wanted,
                    int(config.ALPACA_MAX_TRADE_AGE_SECONDS)) or {}) if wanted else {}
    priced = {t: q for t, q in got.items() if q.price is not None}
    misses = [t for t in wanted if t not in priced]
    _log_fallback("latest_quotes", misses)
    out = dict(got)
    for group, source in ((rest, SOURCE_YF), (misses, SOURCE_FALLBACK)):
        fetched = yf_fetch(group) if group else {}
        out.update({t: _with_alpaca_quote(q, got.get(t)) for t, q in fetched.items()})
        _last_source.update({t: source for t in fetched})
    _last_source.update({t: SOURCE_ALPACA for t in priced})
    _stats["alpaca"] += len(priced)
    _stats["yfinance"] += len(rest)
    _stats["fallback"] += len(misses)
    out.update(_spot_quotes(spot))
    return out
```

- [ ] **Step 6: Implement `data._yf_quote_details` and the `BudgetDeferred` re-export**

In `yf_safe.py` add one line after the imports: `from swingbot.core.marketdata.shared.budget import BudgetDeferred  # noqa: F401  (raised from V171-8 on)`.

In `data.py`, after `_yf_batch_prices` (byte-for-byte unchanged: it is the `off`-mode path), add `from swingbot.core.marketdata.shared.kinds import QuoteDetail`, then:

```python
def _bar_time_utc(ts):
    stamp = pd.Timestamp(ts)
    return (stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")).to_pydatetime()

def _last_minute_quote(raw, ticker):
    try:
        closes = raw[ticker]["Close"].dropna()
    except KeyError:
        return None
    if closes.empty or float(closes.iloc[-1]) <= 0:
        return None
    return QuoteDetail(symbol=ticker, price=float(closes.iloc[-1]),
                       trade_at=_bar_time_utc(closes.index[-1]), bid=None, ask=None,
                       quote_at=None, source="yfinance-1m")

def _yf_quote_details(tickers: list) -> dict:
    """v171: _yf_batch_prices with each price's own bar timestamp (D5: a
    delayed yfinance value counts only if its own timestamp passes 60 s)."""
    try:
        raw = yf_safe.download(" ".join(tickers), period="1d", interval="1m",
                               group_by="ticker", prepost=True, progress=False)
    except yf_safe.BudgetDeferred:
        raise
    except yf_safe.DownloadBusy as exc:
        log.info("yfinance busy, skipped %d ticker(s): %s", len(tickers), exc)
        return {}
    except Exception as exc:
        log.error("_yf_quote_details failed for %d ticker(s): %s", len(tickers), exc, exc_info=True)
        return {}
    if raw is None or raw.empty:
        return {}
    return {t: q for t in tickers if (q := _last_minute_quote(raw, t)) is not None}
```

The `except BudgetDeferred` clause comes first, so the clause order holds even if part 1 makes `BudgetDeferred` a `DownloadBusy` subclass.

- [ ] **Step 7: Run the tests to verify they pass**

Run, one at a time: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_alpaca_provider.py`, `... file tests/marketdata/test_provider_router.py`, `... file tests/marketdata/test_provider_router_robust.py`, `... file tests/scanning/test_no_cross_ticker_mixing.py`
Expected: all PASS, `0 failed`.

- [ ] **Step 8: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/providers/alpaca_provider.py $WT/swingbot/core/marketdata/providers/router.py $WT/swingbot/core/marketdata/data.py`
Expected: no new function at C or above; `_account` is still 11 and `get_current_price_batch` still 12 (radon lists only C+, so neither shows up).

- [ ] **Step 9: Commit**

```bash
git -C $WT add swingbot/core/marketdata/providers/alpaca_provider.py swingbot/core/marketdata/providers/router.py swingbot/core/marketdata/data.py swingbot/core/marketdata/yf_safe.py tests/marketdata/test_alpaca_provider.py tests/marketdata/test_provider_router.py
git -C $WT commit -m "feat(v171): timestamped quotes with IEX bid/ask from Alpaca, yfinance 1-minute fallback"
```

### Task V171-8: Router on the shared budget and breaker (`on` mode), asker carried by contextvar into worker calls

**Model:** opus — the money-path gate every Alpaca call passes

**Files:**
- Modify: `swingbot/core/marketdata/providers/router.py` (`reset` :113, `_active_provider` :123-132, `_collect` :158-168, `_attempt` :175-183, `_round` :186-191, `_account` :217-237)
- Modify: `swingbot/core/marketdata/yf_safe.py` (`download` :51-62)
- Test: `tests/marketdata/test_router_shared_budget.py` (create)

**Interfaces:**
- Consumes: `budget.take(provider, asker) -> bool`, `budget.breaker_allows(provider) -> bool`, `budget.breaker_record(provider, ok) -> None`, `budget.BudgetDeferred` (V171-5); `Asker`, `PROVIDER_ALPACA`, `PROVIDER_YF` (V171-2); `config.MARKETDATA_LAYER` (V171-1).
- Produces:
  - `router.asker_scope(asker: Asker) -> ContextManager[None]` and `router.current_asker() -> Asker` (a module `contextvars.ContextVar`, default `Asker.SCAN`). The router's pool threads already run in a copy of the caller's context (`with_current_context`), so the asker reaches them. A spawned worker does **not** inherit it: the worker body enters `asker_scope` itself (V171-9, V171-10 do).
  - `on` mode only: `_attempt` and `_round` take `budget.take(PROVIDER_ALPACA, current_asker())` instead of `_bucket.take()`. Every breaker verdict is mirrored into `budget.breaker_record(PROVIDER_ALPACA, ok)`. `_active_provider` also requires `budget.breaker_allows(PROVIDER_ALPACA)`, memoised for 1 s per process and re-read after any verdict.
  - `yf_safe.download` in `on` mode takes `budget.take(PROVIDER_YF, current_asker())` before the lock. When the take is denied, a tier 4-5 asker gets `BudgetDeferred` and no download runs. Tiers 1-3 are never denied: they download anyway.
  - `off` and `count`: `_bucket`, `_breaker` and `yf_safe.download` behave exactly as before; `budget` is never called.
  - Both modules call `budget.take` / `budget.breaker_*` **through the module attribute** (`from swingbot.core.marketdata.shared import budget`, then `budget.take(...)`), so tests patch one place.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_router_shared_budget.py`:

```python
"""v171 D6: in `on` mode every Alpaca and yfinance call takes a token from the
one shared budget at the asker's tier; off/count keep the per-process bucket."""
import threading
import time

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import yf_safe
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaMiss
from swingbot.core.marketdata.shared import budget
from swingbot.core.marketdata.shared.kinds import PROVIDER_ALPACA, PROVIDER_YF, Asker


def _df():
    return pd.DataFrame({"Close": [1.0]}, index=pd.DatetimeIndex(["2026-10-15"]))


class FakeProvider:
    def __init__(self, prices=None, exc=None):
        self.prices, self.exc, self.calls, self.askers = prices or {}, exc, 0, []

    def latest_prices(self, tickers, max_age):
        self.calls += 1
        self.askers.append((router.current_asker(), threading.current_thread().name))
        if self.exc:
            raise self.exc
        return {t: p for t, p in self.prices.items() if t in tickers}

    def daily_bars(self, tickers, period):
        self.calls += 1
        return {t: _df() for t in tickers}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", True)
    monkeypatch.setattr(config, "ALPACA_API_KEY_ID", "k")
    monkeypatch.setattr(config, "ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setattr(config, "ALPACA_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(config, "ALPACA_BARS_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(config, "ALPACA_BREAKER_FAILURES", 1)
    monkeypatch.setattr(config, "ALPACA_BREAKER_COOLDOWN_SECONDS", 60)
    router.reset()
    yield
    router.reset()


@pytest.fixture
def shared(monkeypatch):
    """Records every budget call; tokens and breaker answers are set per test."""
    rec = {"take": [], "allows": [], "record": [], "grant": True, "closed": True}

    def take(provider, asker):
        rec["take"].append((provider, asker))
        return rec["grant"]

    def allows(provider):
        rec["allows"].append(provider)
        return rec["closed"]

    monkeypatch.setattr(budget, "take", take)
    monkeypatch.setattr(budget, "breaker_allows", allows)
    monkeypatch.setattr(budget, "breaker_record", lambda p, ok: rec["record"].append((p, ok)))
    return rec


def _use(monkeypatch, prov):
    monkeypatch.setattr(router, "_provider_factory", lambda *a: prov)


def _mode(monkeypatch, mode):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", mode)
    router.reset()


def test_default_asker_is_scan_and_scopes_nest_and_reset():
    assert router.current_asker() is Asker.SCAN
    with router.asker_scope(Asker.STOP_MONITOR):
        assert router.current_asker() is Asker.STOP_MONITOR
        with router.asker_scope(Asker.ADMIN_PAGE):
            assert router.current_asker() is Asker.ADMIN_PAGE
        assert router.current_asker() is Asker.STOP_MONITOR
    assert router.current_asker() is Asker.SCAN


@pytest.mark.parametrize("mode", ["off", "count"])
def test_off_and_count_use_the_local_bucket_and_never_the_budget(enabled, shared, monkeypatch, mode):
    _mode(monkeypatch, mode)
    prov = FakeProvider(prices={"AAPL": 190.0}); _use(monkeypatch, prov)
    router._bucket = router._Bucket(per_minute=1)
    assert router.latest_prices(["AAPL"], lambda ts: {}) == {"AAPL": 190.0}
    assert router.latest_prices(["AAPL"], lambda ts: {"AAPL": 189.0}) == {"AAPL": 189.0}
    assert prov.calls == 1                       # second call had no local token
    monkeypatch.setattr(yf_safe.yf, "download", lambda *a, **k: _df())
    assert not yf_safe.download("AAPL", period="1d").empty
    assert shared["take"] == shared["allows"] == shared["record"] == []


def test_on_takes_one_shared_token_at_the_current_asker(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    prov = FakeProvider(prices={"AAPL": 190.0}); _use(monkeypatch, prov)
    router._bucket.tokens = 0.0                  # the local bucket is not consulted
    with router.asker_scope(Asker.STOP_MONITOR):
        assert router.latest_prices(["AAPL"], lambda ts: {}) == {"AAPL": 190.0}
    assert shared["take"] == [(PROVIDER_ALPACA, Asker.STOP_MONITOR)]
    assert shared["record"] == [(PROVIDER_ALPACA, True)]


def test_on_asker_reaches_the_router_pool_thread(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    prov = FakeProvider(prices={"AAPL": 190.0}); _use(monkeypatch, prov)
    with router.asker_scope(Asker.REQUOTE):
        router.latest_prices(["AAPL"], lambda ts: {})
    asker, thread = prov.askers[0]
    assert asker is Asker.REQUOTE and thread.startswith("alpaca-quote")


def test_on_denied_token_falls_back_to_yfinance(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    shared["grant"] = False
    prov = FakeProvider(prices={"AAPL": 190.0}); _use(monkeypatch, prov)
    out = router.latest_prices(["AAPL"], lambda ts: {"AAPL": 189.5})
    assert prov.calls == 0 and out == {"AAPL": 189.5}
    assert router.last_source("AAPL") == "yfinance-fallback"


def test_on_round_takes_one_token_per_batch(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    monkeypatch.setattr(router, "symbols_per_request", lambda period: 1)
    _use(monkeypatch, FakeProvider())
    with router.asker_scope(Asker.BACKGROUND):
        out = router.daily_bars(["AAPL", "MSFT", "NVDA"], "10y", lambda ts, p: {})
    assert set(out) == {"AAPL", "MSFT", "NVDA"}
    assert shared["take"] == [(PROVIDER_ALPACA, Asker.BACKGROUND)] * 3


def test_on_open_shared_breaker_sends_everything_to_plain_yfinance(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    shared["closed"] = False
    prov = FakeProvider(prices={"AAPL": 190.0}); _use(monkeypatch, prov)
    out = router.latest_prices(["AAPL"], lambda ts: {"AAPL": 189.0})
    assert prov.calls == 0 and out == {"AAPL": 189.0}
    assert router.last_source("AAPL") == "yfinance"
    assert shared["take"] == []


def test_on_failed_call_mirrors_a_failure_verdict(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    _use(monkeypatch, FakeProvider(exc=AlpacaMiss("boom")))
    router.latest_prices(["AAPL"], lambda ts: {})
    assert shared["record"] == [(PROVIDER_ALPACA, False)]


def test_on_shared_breaker_read_is_memoised_and_reread_after_a_verdict(enabled, shared, monkeypatch):
    _mode(monkeypatch, "on")
    _use(monkeypatch, FakeProvider(prices={"AAPL": 190.0}))
    router._active_provider(); router._active_provider()
    assert len(shared["allows"]) == 1
    router.latest_prices(["AAPL"], lambda ts: {})     # records a verdict
    router._active_provider()
    assert len(shared["allows"]) == 2
    router.reset(); router._active_provider()           # reset clears the memo
    assert len(shared["allows"]) == 3


def test_yf_download_on_takes_a_yf_token_at_the_current_asker(shared, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(yf_safe.yf, "download", lambda *a, **k: _df())
    with router.asker_scope(Asker.BACKGROUND):
        yf_safe.download("AAPL", period="1d")
    assert shared["take"] == [(PROVIDER_YF, Asker.BACKGROUND)]


@pytest.mark.parametrize("asker", [Asker.BACKGROUND, Asker.ADMIN_PAGE, Asker.ADMIN_DASHBOARD,
                                   Asker.ADMIN_FRESH])
def test_yf_download_denied_tier_4_5_is_deferred_without_downloading(shared, monkeypatch, asker):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    shared["grant"] = False
    calls = []
    monkeypatch.setattr(yf_safe.yf, "download", lambda *a, **k: calls.append(a) or _df())
    with router.asker_scope(asker), pytest.raises(yf_safe.BudgetDeferred):
        yf_safe.download("AAPL", period="1d")
    assert calls == []
    assert yf_safe.BudgetDeferred is budget.BudgetDeferred


@pytest.mark.parametrize("asker", [Asker.STOP_MONITOR, Asker.REQUOTE, Asker.SCAN])
def test_yf_download_tiers_1_to_3_are_never_denied(shared, monkeypatch, asker):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    shared["grant"] = False
    monkeypatch.setattr(yf_safe.yf, "download", lambda *a, **k: _df())
    with router.asker_scope(asker):
        assert not yf_safe.download("AAPL", period="1d").empty

```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_router_shared_budget.py`
Expected: FAIL with `AttributeError: module ... router has no attribute 'current_asker'` (and the `on` assertions fail once that exists).

- [ ] **Step 3: Implement the asker scope and the shared gates in `router.py`**

Add `import contextlib`, `import contextvars`, `from swingbot.core.marketdata.shared import budget` and `from swingbot.core.marketdata.shared.kinds import PROVIDER_ALPACA, Asker`. Then add these module-level pieces after `_stats`:

```python
_ASKER: contextvars.ContextVar = contextvars.ContextVar("marketdata_asker", default=Asker.SCAN)
#: v171: process-local memo of the shared breaker; at most one read per second.
_SHARED_BREAKER_MEMO_S = 1.0
_shared_breaker_memo: dict = {"stamp": None, "allows": True}

@contextlib.contextmanager
def asker_scope(asker: Asker):
    """Every provider call made inside runs at `asker`'s budget tier (D6)."""
    token = _ASKER.set(asker)
    try:
        yield
    finally:
        _ASKER.reset(token)

def current_asker() -> Asker:
    return _ASKER.get()

def _shared() -> bool:
    return config.MARKETDATA_LAYER == "on"

def _take_token() -> bool:
    """One token for one provider call: the shared budget in `on` mode,
    this process's bucket otherwise (pre-v171, unchanged)."""
    if not _shared():
        return _bucket.take()
    return budget.take(PROVIDER_ALPACA, current_asker())

def _shared_breaker_allows() -> bool:
    if not _shared():
        return True
    now = time.monotonic()
    stamp = _shared_breaker_memo["stamp"]
    if stamp is not None and now - stamp < _SHARED_BREAKER_MEMO_S:
        return _shared_breaker_memo["allows"]
    allows = budget.breaker_allows(PROVIDER_ALPACA)
    _shared_breaker_memo.update(stamp=now, allows=allows)
    return allows

def _record_verdict(ok: bool, auth: bool = False, reason: str = "") -> None:
    """The local breaker always; the shared one too in `on` mode."""
    _breaker.record(ok, auth=auth, reason=reason)
    if _shared():
        budget.breaker_record(PROVIDER_ALPACA, ok)
        _shared_breaker_memo["stamp"] = None
```

Edit the existing functions. Each edit replaces one expression, so no branch is added to them:

- `reset()`: add `_shared_breaker_memo.update(stamp=None, allows=True)`.
- `_active_provider()`: last line becomes `return _provider if _breaker.allows() and _shared_breaker_allows() else None`.
- `_collect()`: both `_breaker.record(...)` calls become `_record_verdict(...)` with the same arguments.
- `_attempt()`: `if prov is None or not _bucket.take():` becomes `if prov is None or not _take_token():`.
- `_round()`: `if _bucket.take() else None` becomes `if _take_token() else None`.
- `_account()`: its three `_breaker.record(...)` calls become `_record_verdict(...)`.

`_retryable` keeps reading `_breaker.allows()` (the local breaker), as before. The shared breaker gates new calls through `_active_provider`.

- [ ] **Step 4: Implement the yfinance token in `yf_safe.py`**

Add `from swingbot import config` and change the V171-7 re-export line to `from swingbot.core.marketdata.shared import budget` plus `from swingbot.core.marketdata.shared.budget import BudgetDeferred  # noqa: F401`. Add `from swingbot.core.marketdata.shared.kinds import PROVIDER_YF`. Then:

```python
def _take_yf_token() -> None:
    """v171 D6, `on` mode only: one yfinance token per download at the
    caller's tier. Tiers 1-3 (stops, re-quote, scan) are never denied."""
    if config.MARKETDATA_LAYER != "on":
        return
    from swingbot.core.marketdata.providers.router import current_asker  # lazy: router imports data paths
    asker = current_asker()
    if budget.take(PROVIDER_YF, asker) or asker.priority <= 3:
        return
    raise BudgetDeferred(f"yfinance budget short for {asker.value}")
```

and make `_take_yf_token()` the first statement of `download(...)`, before the lock is taken. The rest of `download` is unchanged.

- [ ] **Step 5: Run the tests to verify they pass**

Run, one at a time: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_router_shared_budget.py`, `... file tests/marketdata/test_provider_router.py`, `... file tests/marketdata/test_provider_router_robust.py`, `... file tests/marketdata/test_router_scan_context.py`, `... file tests/scanning/test_no_cross_ticker_mixing.py`
Expected: all PASS, `0 failed`. The pre-existing router tests run with `MARKETDATA_LAYER` at its code default `off`, so they prove the `off` path is unchanged.

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/providers/router.py $WT/swingbot/core/marketdata/yf_safe.py`
Expected: nothing listed (`_account` stays at 11, the new helpers are A/B).

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/core/marketdata/providers/router.py swingbot/core/marketdata/yf_safe.py tests/marketdata/test_router_shared_budget.py
git -C $WT commit -m "feat(v171): router and yf_safe take shared budget tokens at the asker's tier in on mode"
```

### Task V171-9: `data.py` quote API through the layer: `get_quote_batch`, `get_current_price_batch`/`get_current_price_detail` routed with asker and age; worker counter round trip

**Model:** opus — fresh-only price semantics for trading code, spans scanning workers and marketdata

**Files:**
- Modify: `swingbot/core/marketdata/data.py` (`get_current_price_batch` :159-211, `PriceQuote` :464-483, `get_current_price_detail` :540-606, `get_current_price` :609-617)
- Modify: `swingbot/core/scanning/fetch.py` (`_price_batch_with_sources` :65-71, `_fetch_live_prices` :491-523)
- Test: `tests/marketdata/test_quote_layer.py` (create), `tests/scanning/test_scan_telemetry_sources.py`

**Interfaces:**
- Consumes: `layer.get(kind, symbols, fetch, *, asker, provider, params="", max_age_s=None, deadline_s=10.0, encode, decode) -> dict[str, Entry]` (V171-6); `Entry`, `QuoteDetail`, `DataKind.QUOTE`, `PROVIDER_ALPACA`, `Asker`, `resolve_asker` (V171-2); `counters.snapshot_and_clear()`, `counters.merge(rows)` (V171-4); `router.latest_quotes`, `data._yf_quote_details` (V171-7); `router.asker_scope` (V171-8).
- Produces:
  - `data.get_quote_batch(tickers: list[str], *, asker: Asker, max_age_s: float | None = None, fresh_only: bool = False) -> dict[str, QuoteDetail]`. Tickers are upper-cased, stripped and de-duplicated. Spot symbols go straight to `router.latest_quotes(spot, _yf_quote_details)` and never reach the layer. The rest go to one `layer.get(DataKind.QUOTE, rest, fetch, asker=asker, provider=PROVIDER_ALPACA, max_age_s=max_age_s, encode=QuoteDetail.to_doc, decode=QuoteDetail.from_doc)` inside `router.asker_scope(asker)`, where `fetch = lambda syms: router.latest_quotes(list(syms), _yf_quote_details)`. `fresh_only=True` drops entries whose outcome is `"budget-deferred"` or whose `age_s()` exceeds the window (`max_age_s`, else `resolve_asker(asker).window_s(DataKind.QUOTE)`). A `QuoteDetail` may carry `price=None` with bid/ask only; price consumers skip it.
  - `data.get_current_price_batch(tickers, *, allow_stale=True, asker: Asker = Asker.SCAN) -> dict[str, float]`: the same return shape. `MARKETDATA_LAYER == "off"` calls `_price_batch_legacy` (today's body, renamed, unchanged). Otherwise prices come from `get_quote_batch(..., fresh_only=not allow_stale)`. `allow_stale=False` gets no last-good fallback. `count` mode keeps the in-process 15 s display short-circuit, so its call volume is today's.
  - `PriceQuote` gains `as_of: datetime | None = None` and `age_s: float | None = None` (positional `PriceQuote(price, stale)` still works).
  - `data.get_current_price_detail(ticker, ttl_seconds=15, *, allow_stale=True, asker: Asker = Asker.ADMIN_PAGE) -> PriceQuote | None`; `data.get_current_price(ticker, ttl_seconds=15, *, allow_stale=True, asker: Asker = Asker.SCAN) -> float | None` (forwards its asker). `off` calls `_price_detail_legacy` (today's body, renamed).
  - `fetch._price_batch_with_sources(tickers) -> (prices, sources)`: `sources["__counts__"]` carries the worker's `counters.snapshot_and_clear()` rows. `fetch._fetch_live_prices` pops it and calls `counters.merge(rows)`. Telemetry `price_sources` never sees the key.

- [ ] **Step 1: Write the failing layer-path tests**

Create `tests/marketdata/test_quote_layer.py`:

```python
"""v171 D1/D2: the data.py quote API goes through the shared layer at the
caller's asker; trading callers stay fresh-only; off mode is pre-v171."""
import time
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata import data
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared import layer
from swingbot.core.marketdata.shared.kinds import (PROVIDER_ALPACA, Asker, DataKind,
                                                   Entry, QuoteDetail)

NOW = datetime.now(timezone.utc)


def _q(sym, price=190.0, age=1.0, bid=None, ask=None, source="alpaca-iex"):
    at = NOW - timedelta(seconds=age)
    return QuoteDetail(symbol=sym, price=price, trade_at=at if price else None,
                       bid=bid, ask=ask, quote_at=at if bid else None, source=source)


def _entry(q, outcome="fetched", age=0.0):
    return Entry(value=q, fetched_at=datetime.now(timezone.utc) - timedelta(seconds=age),
                 source=q.source, outcome=outcome)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(config, "QUOTE_MAX_AGE_MONITOR_S", 15)
    data._last_good_batch_price.clear()
    data._price_cache.clear()
    yield
    data._last_good_batch_price.clear()
    data._price_cache.clear()


@pytest.fixture
def mode(monkeypatch):
    def set_mode(value):
        monkeypatch.setattr(config, "MARKETDATA_LAYER", value)
    return set_mode


@pytest.fixture
def fake_layer(monkeypatch):
    rec = {"calls": [], "entries": {}}

    def get(kind, symbols, fetch, **kw):
        rec["calls"].append({"kind": kind, "symbols": list(symbols), "fetch": fetch,
                             "scoped": router.current_asker(), **kw})
        return {s: rec["entries"][s] for s in symbols if s in rec["entries"]}
    monkeypatch.setattr(layer, "get", get)
    return rec


def test_off_mode_price_batch_is_the_pre_v171_function(mode, fake_layer, monkeypatch):
    mode("off")
    seen = []
    monkeypatch.setattr(data, "_price_batch_legacy",
                        lambda tickers, *, allow_stale: seen.append((tickers, allow_stale)) or {"AAPL": 1.0})
    assert data.get_current_price_batch(["AAPL"], allow_stale=False) == {"AAPL": 1.0}
    assert seen == [(["AAPL"], False)] and fake_layer["calls"] == []


def test_quote_batch_asks_the_layer_once_at_the_asker(mode, fake_layer):
    mode("on")
    fake_layer["entries"]["AAPL"] = _entry(_q("AAPL"))
    out = data.get_quote_batch(["aapl", " AAPL"], asker=Asker.STOP_MONITOR)
    assert out == {"AAPL": fake_layer["entries"]["AAPL"].value}
    [call] = fake_layer["calls"]
    assert call["kind"] is DataKind.QUOTE and call["symbols"] == ["AAPL"]
    assert call["asker"] is Asker.STOP_MONITOR and call["provider"] == PROVIDER_ALPACA
    assert call["scoped"] is Asker.STOP_MONITOR          # inside router.asker_scope
    assert call["encode"] == QuoteDetail.to_doc and call["decode"] == QuoteDetail.from_doc


def test_layer_fetch_is_router_latest_quotes_with_the_yf_minute_fallback(mode, fake_layer, monkeypatch):
    mode("on")
    seen = []
    monkeypatch.setattr(router, "latest_quotes",
                        lambda syms, yf_fetch: seen.append((syms, yf_fetch)) or {})
    data.get_quote_batch(["AAPL"], asker=Asker.SCAN)
    fake_layer["calls"][0]["fetch"](["AAPL"])
    assert seen == [(["AAPL"], data._yf_quote_details)]


def test_spot_metal_never_reaches_the_layer(mode, fake_layer, monkeypatch):
    mode("on")
    spot = _q("XAUUSD", 2400.0, source="spot")
    direct = []
    monkeypatch.setattr(router, "latest_quotes",
                        lambda syms, yf_fetch: direct.append(list(syms)) or {"XAUUSD": spot})
    fake_layer["entries"]["AAPL"] = _entry(_q("AAPL"))
    out = data.get_quote_batch(["XAUUSD", "AAPL"], asker=Asker.STOP_MONITOR)
    assert fake_layer["calls"][0]["symbols"] == ["AAPL"]
    assert direct == [["XAUUSD"]] and out["XAUUSD"] is spot


def test_fresh_only_drops_deferred_and_over_window_entries(mode, fake_layer):
    mode("on")
    fake_layer["entries"].update({
        "AAPL": _entry(_q("AAPL"), "fetched", age=1.0),
        "MSFT": _entry(_q("MSFT"), "budget-deferred", age=1.0),
        "NVDA": _entry(_q("NVDA"), "hit", age=40.0),
    })
    syms = ["AAPL", "MSFT", "NVDA"]
    assert set(data.get_quote_batch(syms, asker=Asker.STOP_MONITOR, fresh_only=True)) == {"AAPL"}
    assert set(data.get_quote_batch(syms, asker=Asker.STOP_MONITOR)) == set(syms)


def test_explicit_max_age_sets_the_fresh_only_window(mode, fake_layer):
    mode("on")
    fake_layer["entries"]["AAPL"] = _entry(_q("AAPL"), "hit", age=7.0)
    assert data.get_quote_batch(["AAPL"], asker=Asker.REQUOTE, max_age_s=5, fresh_only=True) == {}
    assert fake_layer["calls"][0]["max_age_s"] == 5


@pytest.fixture
def quotes(monkeypatch):
    rec = {"calls": [], "out": {}}

    def fake(tickers, *, asker, max_age_s=None, fresh_only=False):
        rec["calls"].append({"tickers": list(tickers), "asker": asker, "fresh_only": fresh_only})
        return dict(rec["out"])
    monkeypatch.setattr(data, "get_quote_batch", fake)
    return rec


def test_trading_batch_is_fresh_only_with_no_last_good_fallback(mode, quotes):
    mode("on")
    data._last_good_batch_price["AAPL"] = (190.0, time.monotonic())
    assert data.get_current_price_batch(["AAPL"], allow_stale=False) == {}
    assert quotes["calls"][0]["fresh_only"] is True


def test_display_batch_falls_back_to_last_good(mode, quotes):
    mode("on")
    data._last_good_batch_price["AAPL"] = (190.0, time.monotonic() - 60)
    assert data.get_current_price_batch(["AAPL"]) == {"AAPL": 190.0}
    assert quotes["calls"][0]["fresh_only"] is False


def test_batch_skips_quotes_without_a_trade_price(mode, quotes):
    mode("on")
    quotes["out"] = {"AAPL": _q("AAPL", None, bid=189.0, ask=191.0), "MSFT": _q("MSFT", 410.0)}
    assert data.get_current_price_batch(["AAPL", "MSFT"], allow_stale=False) == {"MSFT": 410.0}
    assert data._last_good_batch_price["MSFT"][0] == 410.0


def test_batch_forwards_its_asker(mode, quotes):
    mode("on")
    data.get_current_price_batch(["AAPL"], asker=Asker.BACKGROUND)
    assert quotes["calls"][0]["asker"] is Asker.BACKGROUND


def test_count_mode_keeps_the_in_process_display_short_circuit(mode, quotes):
    mode("count")
    data._last_good_batch_price["AAPL"] = (190.0, time.monotonic())
    assert data.get_current_price_batch(["AAPL"]) == {"AAPL": 190.0}
    assert quotes["calls"] == []
    mode("on")
    data.get_current_price_batch(["AAPL"])
    assert len(quotes["calls"]) == 1


def test_price_detail_carries_as_of_and_age(mode, quotes):
    mode("on")
    q = _q("AAPL", 190.0, age=3.0)
    quotes["out"] = {"AAPL": q}
    detail = data.get_current_price_detail("AAPL")
    assert (detail.price, detail.stale, detail.as_of) == (190.0, False, q.trade_at)
    assert 2.5 < detail.age_s < 30
    assert quotes["calls"][0]["asker"] is Asker.ADMIN_PAGE


def test_get_current_price_forwards_asker_and_fresh_only(mode, quotes):
    mode("on")
    quotes["out"] = {"AAPL": _q("AAPL", 190.0)}
    assert data.get_current_price("AAPL", allow_stale=False, asker=Asker.STOP_MONITOR) == 190.0
    assert quotes["calls"][0]["asker"] is Asker.STOP_MONITOR
    assert quotes["calls"][0]["fresh_only"] is True


def test_price_detail_layer_miss_falls_back_to_the_yfinance_history_path(mode, quotes, monkeypatch):
    mode("on")
    monkeypatch.setattr(data, "_detail_from_yfinance",
                        lambda key, cached, now, allow_stale: data.PriceQuote(5.0, True))
    assert data.get_current_price_detail("SAP.DE") == data.PriceQuote(5.0, True)


def test_price_detail_off_mode_is_the_pre_v171_function(mode, quotes, monkeypatch):
    mode("off")
    monkeypatch.setattr(data, "_price_detail_legacy",
                        lambda ticker, ttl_seconds, allow_stale: data.PriceQuote(1.0, False))
    assert data.get_current_price_detail("AAPL") == data.PriceQuote(1.0, False)
    assert quotes["calls"] == []

```

- [ ] **Step 2: Write the failing worker round-trip test**

Append to `tests/scanning/test_scan_telemetry_sources.py` (reuses its `_InlinePool`):

```python
def test_live_price_worker_counts_travel_back_to_the_parent(monkeypatch):
    from swingbot.core.marketdata.shared import counters
    from swingbot.core.scanning import fetch
    rows = [("2026-10-16T14:00:00+00:00", "alpaca", "quote", "SCAN", "fetched", 2)]
    merged = []
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(fetch, "get_current_price_batch", lambda tickers: {"AAPL": 190.0})
    monkeypatch.setattr(counters, "snapshot_and_clear", lambda: list(rows))
    monkeypatch.setattr(counters, "merge", merged.extend)
    fetch.reset_fetch_stats()
    assert fetch._fetch_live_prices(["AAPL"]) == {"AAPL": 190.0}
    assert merged == rows
    assert "__counts__" not in fetch.fetch_stats()["price_sources"]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_quote_layer.py` and `python $WT/scripts/dev/testrun.py file tests/scanning/test_scan_telemetry_sources.py`
Expected: FAIL. The layer tests fail with `AttributeError: module ... data has no attribute 'get_quote_batch'` / `'_price_batch_legacy'`, the round trip with `merged == []`.

- [ ] **Step 4: Implement `get_quote_batch` in `data.py`**

Add the imports `from datetime import datetime, timezone`, `from swingbot import config`, `from swingbot.core.marketdata.shared import layer` and `from swingbot.core.marketdata.shared.kinds import PROVIDER_ALPACA, Asker, DataKind, QuoteDetail, resolve_asker` (`QuoteDetail` is already imported by V171-7). Then add:

```python
def _normalise_tickers(tickers) -> list:
    return list(dict.fromkeys(str(t).upper().strip() for t in tickers
                              if t is not None and str(t).strip()))

def _usable(entry, window, fresh_only: bool) -> bool:
    """A layer entry a caller may use; fresh-only callers never take a
    budget-deferred or over-window value (D2: never "close enough")."""
    if entry is None or entry.value is None:
        return False
    if not fresh_only:
        return True
    return entry.outcome != "budget-deferred" and (window is None or entry.age_s() <= window)

def get_quote_batch(tickers, *, asker, max_age_s=None, fresh_only=False) -> dict:
    """v171: timestamped quotes through the shared layer at `asker`'s window
    and tier. Spot metals keep spot_metals' own path and are never cached."""
    tickers = _normalise_tickers(tickers)
    spot, rest = spot_metals.split_spot(tickers)
    out = router.latest_quotes(spot, _yf_quote_details) if spot else {}
    if not rest:
        return out
    with router.asker_scope(asker):
        entries = layer.get(DataKind.QUOTE, rest,
                            lambda syms: router.latest_quotes(list(syms), _yf_quote_details),
                            asker=asker, provider=PROVIDER_ALPACA, max_age_s=max_age_s,
                            encode=QuoteDetail.to_doc, decode=QuoteDetail.from_doc)
    window = max_age_s if max_age_s is not None else resolve_asker(asker).window_s(DataKind.QUOTE)
    out.update({t: e.value for t, e in entries.items() if _usable(e, window, fresh_only)})
    return out
```

- [ ] **Step 5: Route `get_current_price_batch`**

Rename today's function body to `_price_batch_legacy(tickers, *, allow_stale)`. The body is moved verbatim, its docstring stays, and it keeps calling `router.latest_prices(tickers, _yf_batch_prices)`. The public function becomes:

```python
def get_current_price_batch(tickers: list, *, allow_stale: bool = True,
                            asker: Asker = Asker.SCAN) -> dict:
    """{ticker: price}. See _price_batch_legacy for the contract (unchanged).
    v171: MARKETDATA_LAYER off is that function exactly; count/on read
    get_quote_batch at `asker`, fresh-only when allow_stale=False."""
    if config.MARKETDATA_LAYER == "off":
        return _price_batch_legacy(tickers, allow_stale=allow_stale)
    return _price_batch_layer(tickers, allow_stale=allow_stale, asker=asker)

def _price_batch_layer(tickers, *, allow_stale: bool, asker) -> dict:
    tickers = _normalise_tickers(tickers)
    if not tickers:
        return {}
    now = time.monotonic()
    if allow_stale and config.MARKETDATA_LAYER == "count":
        current = _fresh_batch_prices(tickers, now)
        if len(current) == len(tickers):
            return current
    quotes = get_quote_batch(tickers, asker=asker, fresh_only=not allow_stale)
    out = {t: q.price for t, q in quotes.items() if q.price and q.price > 0}
    for ticker, price in out.items():
        _last_good_batch_price[ticker] = (price, now)
    missing = [t for t in tickers if t not in out]
    if missing and allow_stale:
        out.update(_stale_batch_fallback(missing, now))
    return out
```

`count` mode keeps the short-circuit so its provider calls match today (the D9 baseline). `on` mode skips it, so the shared window decides: an `ADMIN_FRESH` request, max age 0, is never answered from this process's 15 s cache.

- [ ] **Step 6: Route `get_current_price_detail` and `get_current_price`; add the `PriceQuote` fields**

`PriceQuote` gains two trailing fields with defaults, documented in its docstring as "when the price was observed and how old it was at return; `None` before v171 and on the off path":

```python
    as_of: datetime | None = None
    age_s: float | None = None
```

Behaviour-preserving extraction: move the candidate loop plus the last-known-good tail of today's `get_current_price_detail` (:574-606) verbatim into `_detail_from_yfinance(ticker_key: str, cached, now: float, allow_stale: bool) -> PriceQuote | None`. Rename the rest of today's function to `_price_detail_legacy(ticker, ttl_seconds, allow_stale)`, which ends with `return _detail_from_yfinance(ticker_key, cached, now, allow_stale)`. Then:

```python
def get_current_price_detail(ticker: str, ttl_seconds: int = _PRICE_CACHE_TTL_SECONDS,
                             *, allow_stale: bool = True,
                             asker: Asker = Asker.ADMIN_PAGE) -> PriceQuote | None:
    """(today's docstring, plus:) v171: off is _price_detail_legacy exactly;
    count/on ask get_quote_batch at `asker` first and stamp as_of/age_s."""
    if config.MARKETDATA_LAYER == "off":
        return _price_detail_legacy(ticker, ttl_seconds, allow_stale)
    return _price_detail_layer(ticker, ttl_seconds, allow_stale, asker)

def _quote_to_price(q) -> PriceQuote:
    as_of = q.trade_at or q.quote_at
    age = (datetime.now(timezone.utc) - as_of).total_seconds() if as_of else None
    return PriceQuote(q.price, False, as_of, age)

def _price_detail_layer(ticker, ttl_seconds, allow_stale, asker) -> PriceQuote | None:
    key = ticker.upper().strip()
    cached = _price_cache.get(key)
    now = time.monotonic()
    if spot_metals.is_spot_metal(key):
        return _spot_price_detail(key, cached, now, allow_stale)
    if config.MARKETDATA_LAYER == "count" and cached and now - cached[1] < ttl_seconds:
        return PriceQuote(cached[0], cached[2])
    q = get_quote_batch([key], asker=asker, fresh_only=not allow_stale).get(key)
    if q is not None and q.price:
        _price_cache[key] = (q.price, now, False)
        return _quote_to_price(q)
    return _detail_from_yfinance(key, cached, now, allow_stale)
```

`get_current_price` gains `asker: Asker = Asker.SCAN` and passes `asker=asker` to `get_current_price_detail`. Its trading callers (scan reversal check, `plan_manager._price_fn`) therefore never run at the admin tier.

- [ ] **Step 7: Carry worker counts back in `fetch.py`**

```python
def _price_batch_with_sources(tickers: list) -> tuple:
    """(docstring as today, plus:) v171: the worker's D9 counter rows ride
    back under sources["__counts__"] -- this process exits after the call."""
    from swingbot.core.marketdata.providers import router
    from swingbot.core.marketdata.shared import counters
    prices = get_current_price_batch(tickers)
    sources = {t: router.last_source(t) or "none" for t in prices}
    sources["__counts__"] = counters.snapshot_and_clear()
    return prices, sources

def _merge_worker_counts(sources: dict) -> None:
    from swingbot.core.marketdata.shared import counters
    counters.merge(sources.pop("__counts__", []))
```

In `_fetch_live_prices`, call `_merge_worker_counts(sources)` on the line after the `_run_bounded(...)` assignment, before `_record_price_sources(chunk, sources)`. It is an unconditional call, so no branch is added. `get_current_price_batch(tickers)` keeps its one-argument call: the existing telemetry tests patch it with `lambda tickers:`, and the default asker is `Asker.SCAN`.

- [ ] **Step 8: Run the tests to verify they pass**

Run, one at a time: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_quote_layer.py`, `... file tests/scanning/test_scan_telemetry_sources.py`, `... file tests/marketdata/test_current_price_staleness.py`, `... file tests/marketdata/test_data_alpaca_routing.py`, `... file tests/marketdata/test_data_spot.py`, `... file tests/scanning/test_no_cross_ticker_mixing.py`, `... file tests/admin/test_api_v1_watchlist.py`, `... file tests/admin/test_api_v1_tape.py`
Expected: all PASS, `0 failed`. The last six run at the code default `MARKETDATA_LAYER=off`; they prove the off path and the under-1-second `/watchlist/tickers` contract are unchanged.

- [ ] **Step 9: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/data.py $WT/swingbot/core/scanning/fetch.py`
Expected: no function listed that was not listed before; `_price_batch_legacy` and `_price_detail_legacy` keep today's grades (12 / below), and `_price_batch_layer`, `_price_detail_layer`, `get_quote_batch` are each under 10.

- [ ] **Step 10: Commit**

```bash
git -C $WT add swingbot/core/marketdata/data.py swingbot/core/scanning/fetch.py tests/marketdata/test_quote_layer.py tests/scanning/test_scan_telemetry_sources.py
git -C $WT commit -m "feat(v171): data.py quote API through the shared layer with asker, age and fresh-only; worker counts round trip"
```

### Task V171-10: Trade monitor and plan manager share one quote fetch per tick; exit events carry the quote stamp

**Model:** opus — stop monitoring on real positions, spans commands, planning and marketdata

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (`_live_price_batch` :566-587)
- Modify: `swingbot/core/planning/plan_manager.py` (`log_plan_event` :108-123, `poll` :527-587, `_price_fn` :1355-1360, `_price_batch_fn` :1363-1391)
- Test: `tests/commands/test_trade_monitor_shared_quote.py` (create), `tests/planning/test_plan_manager_shared_quote.py` (create)

**Interfaces:**
- Consumes: `data.get_quote_batch(..., asker, fresh_only)` (V171-9); `counters.snapshot_and_clear`, `counters.merge` (V171-4); `QuoteDetail`, `Asker.STOP_MONITOR` (V171-2); `router.current_asker` (V171-8); `side_engine.reset` (V171-3); `config.REBUILD_PRICE_MAX_AGE_S` (V171-1).
- Produces:
  - `plan_manager.monitor_quotes(tickers: list[str]) -> dict[str, QuoteDetail]`. In `count`/`on` mode it runs one `fetch._run_bounded(_monitor_quote_worker, (tickers,), LIVE_PRICE_TIMEOUT_SECONDS, ...)`. The worker calls `get_quote_batch(asker=Asker.STOP_MONITOR, fresh_only=True)` and returns `(docs, counter rows)`, and the parent merges the counts. In `off` mode it wraps today's `get_current_price_batch(allow_stale=False)` result (`source="legacy"`, no timestamps). `{}` on timeout or worker failure. In `on` mode the second asker inside the 15 s window is a cache hit, so monitor plus manager make one provider call. In `count` mode each still makes its own call, as today, and both are counted as `STOP_MONITOR`. (The ledger says "otherwise today's path". This part routes `count` through the worker too, because a spawned worker's counts are lost unless they ride back. Otherwise the D9 baseline would miss the monitor's ~120 calls an hour.)
  - `plan_manager.QuotePrices(dict)`: `{ticker: price}` for `poll`, plus `.details: dict[str, QuoteDetail]`. `_price_batch_fn` returns it in `count`/`on` mode and a plain dict in `off` mode.
  - `plan_manager.quote_stamp(q: QuoteDetail | None, now: datetime) -> dict | None` returns `{"at": iso | None, "kind": "trade" | "yf-1m", "age_s": float | None, "session": "regular" | "pre-market" | "after-hours" | "closed", "confirmed": bool}`. It is `None` for no quote or no price. `confirmed` means `age_s <= REBUILD_PRICE_MAX_AGE_S` (60).
  - `plan_manager.EXIT_TRANSITIONS = frozenset({"closed", "tp1_partial"})`. Those events gain `detail["quote"]`, set only when the batch carried a `QuoteDetail` for the ticker (so the `off` shape is unchanged). The `log_plan_event` INFO line gains ` quote=<kind> <age>s` when it is present.
  - `loops._live_price_batch(tickers)` returns the same `{ticker: price}`. `off` runs `_legacy_live_price_batch` (today's body, renamed); `count`/`on` run `asyncio.to_thread(plan_manager.monitor_quotes, tickers)`.

- [ ] **Step 1: Write the failing plan-manager tests**

Create `tests/planning/test_plan_manager_shared_quote.py`:

```python
"""v171 D2/D8: the plan manager reads the monitor's shared quote and stamps exits."""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.marketdata.shared.kinds import Asker, QuoteDetail
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_manager import PlanManager, QuotePrices, quote_stamp
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_manager_active import _active

ET = ZoneInfo("America/New_York")
REG = datetime(2026, 10, 15, 11, 0, tzinfo=ET)          # Thursday, regular session


def _q(price=94.5, age=2.0, source="alpaca-iex", now=REG):
    at = now.astimezone(timezone.utc) - timedelta(seconds=age)
    return QuoteDetail(symbol="AAPL", price=price, trade_at=at if price else None,
                       bid=None, ask=None, quote_at=None, source=source)


def test_quote_stamp_live_trade_in_session(monkeypatch):
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)
    q = _q(age=2.0)
    assert quote_stamp(q, REG) == {"at": q.trade_at.isoformat(), "kind": "trade", "age_s": 2.0,
                                   "session": "regular", "confirmed": True}


def test_quote_stamp_old_yfinance_minute_bar_is_not_confirmed(monkeypatch):
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)
    s = quote_stamp(_q(age=90.0, source="yfinance-1m"), REG)
    assert (s["kind"], s["age_s"], s["confirmed"]) == ("yf-1m", 90.0, False)


@pytest.mark.parametrize("when, label", [
    (datetime(2026, 10, 15, 8, 0, tzinfo=ET), "pre-market"),
    (datetime(2026, 10, 15, 17, 0, tzinfo=ET), "after-hours"),
    (datetime(2026, 10, 15, 2, 0, tzinfo=ET), "closed"),
    (datetime(2026, 10, 17, 11, 0, tzinfo=ET), "closed"),          # Saturday
])
def test_quote_stamp_session_labels(when, label):
    assert quote_stamp(_q(now=when), when)["session"] == label


def test_quote_stamp_without_a_quote_or_price_is_none():
    assert quote_stamp(None, REG) is None
    assert quote_stamp(_q(price=None), REG) is None


def test_price_batch_fn_off_mode_is_unchanged(monkeypatch):
    from swingbot.core.marketdata.data import get_current_price_batch
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    seen = []
    monkeypatch.setattr(fetch, "_run_bounded",
                        lambda fn, args, timeout, label: seen.append(fn) or {"AAPL": 1.0})
    out = pm._price_batch_fn(["AAPL"])
    assert out == {"AAPL": 1.0} and not isinstance(out, QuotePrices)
    assert seen[0].func is get_current_price_batch and seen[0].keywords == {"allow_stale": False}


def test_price_batch_fn_on_mode_returns_prices_with_details(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    details = {"AAPL": _q(190.0), "MSFT": _q(None)}
    monkeypatch.setattr(pm, "monitor_quotes", lambda tickers: dict(details))
    out = pm._price_batch_fn(["AAPL", "MSFT"])
    assert out == {"AAPL": 190.0} and isinstance(out, QuotePrices)
    assert out.details == details


def test_monitor_quotes_runs_the_worker_and_merges_its_counts(monkeypatch):
    from swingbot.core.marketdata import data
    from swingbot.core.marketdata.shared import counters
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    rows = [("2026-10-15T15:00:00+00:00", "alpaca", "quote", "STOP_MONITOR", "fetched", 1)]
    merged, asked = [], []
    q = _q(190.0)
    monkeypatch.setattr(fetch, "_run_bounded", lambda fn, args, timeout, label: fn(*args))
    monkeypatch.setattr(data, "get_quote_batch",
                        lambda t, *, asker, fresh_only=False, max_age_s=None:
                        asked.append((asker, fresh_only)) or {"AAPL": q})
    monkeypatch.setattr(counters, "snapshot_and_clear", lambda: list(rows))
    monkeypatch.setattr(counters, "merge", merged.extend)
    assert pm.monitor_quotes(["AAPL"]) == {"AAPL": q}
    assert asked == [(Asker.STOP_MONITOR, True)] and merged == rows


def test_monitor_quotes_timeout_is_empty(monkeypatch):
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: None)
    assert pm.monitor_quotes(["AAPL"]) == {}


def _mgr(batch):
    store = PlanStore()
    store.add(_active())
    return PlanManager(store, lambda t: pytest.fail("serial price seam"), price_batch_fn=batch)


def test_exit_event_carries_the_quote_stamp(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)
    q = _q(94.5, age=2.0)
    mgr = _mgr(lambda tickers: QuotePrices({"AAPL": 94.5}, {"AAPL": q}))
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        events = mgr.poll(now=REG)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["quote"] == quote_stamp(q, REG)
    assert any("quote=trade 2.0s" in r.getMessage() for r in caplog.records)


def test_non_exit_event_gets_no_stamp(tmp_path):
    mgr = _mgr(lambda tickers: QuotePrices({"AAPL": 105.0}, {"AAPL": _q(105.0)}))
    events = mgr.poll(now=REG)
    assert [e.transition for e in events] == ["be_moved"] and "quote" not in events[0].detail


def test_plain_dict_prices_add_no_stamp(tmp_path):
    events = _mgr(lambda tickers: {"AAPL": 94.5}).poll(now=REG)
    assert events[0].transition == "closed" and "quote" not in events[0].detail
```

- [ ] **Step 2: Write the failing monitor tests**

Create `tests/commands/test_trade_monitor_shared_quote.py`:

```python
"""v171 D8: trade_monitor and the plan manager land as ONE provider call per
tick in `on` mode; a dead Postgres never stops the stop monitor's quote."""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared.kinds import Asker, QuoteDetail
from swingbot.core.planning import plan_manager
from swingbot.core.scanning import fetch


class CountingProvider:
    def __init__(self):
        self.calls, self.askers = 0, []

    def latest_quotes(self, tickers, max_age):
        self.calls += 1
        self.askers.append(router.current_asker())
        at = datetime.now(timezone.utc) - timedelta(seconds=2)
        return {t: QuoteDetail(symbol=t, price=190.0, trade_at=at, bid=None, ask=None,
                               quote_at=None, source="alpaca-iex") for t in tickers}


@pytest.fixture
def layer_on(monkeypatch):
    for key, value in {"MARKETDATA_LAYER": "on", "ALPACA_ENABLED": True,
                       "ALPACA_API_KEY_ID": "k", "ALPACA_API_SECRET_KEY": "s",
                       "QUOTE_MAX_AGE_MONITOR_S": 15}.items():
        monkeypatch.setattr(config, key, value)
    prov = CountingProvider()
    monkeypatch.setattr(router, "_provider_factory", lambda *a: prov)
    monkeypatch.setattr(fetch, "_run_bounded", lambda fn, args, timeout, label: fn(*args))
    monkeypatch.setattr("swingbot.core.marketdata.data._yf_quote_details",
                        lambda tickers: pytest.fail("yfinance fallback"))
    router.reset()
    yield prov
    router.reset()


@pytest.fixture
def shared_db(monkeypatch, db_committed):
    from swingbot.core.db import side_engine
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_committed.engine.url.render_as_string(hide_password=False))
    reset_engine(); side_engine.reset()
    yield
    side_engine.reset(); reset_engine()


def _tick(monkeypatch, manager_saw):
    monkeypatch.setattr(loops.trade_log, "get_trades", lambda status=None, limit=None: [
        {"ticker": "AAPL", "id": "t1", "status": "open"}])
    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", lambda t, live: [])
    monkeypatch.setattr(loops.trade_log, "check_near_tp_timeout", lambda t, live: [])
    monkeypatch.setattr(plan_manager, "run_manager_tick",
                        lambda: manager_saw.append(plan_manager._price_batch_fn(["AAPL"])) or [])
    asyncio.run(loops.trade_monitor.coro())


def test_monitor_and_manager_share_one_provider_call_per_tick(layer_on, shared_db, monkeypatch):
    saw = []
    _tick(monkeypatch, saw)
    assert layer_on.calls == 1
    assert saw == [{"AAPL": 190.0}] and saw[0].details["AAPL"].trade_at is not None
    assert layer_on.askers == [Asker.STOP_MONITOR]


def test_count_mode_still_makes_one_call_each_as_today(layer_on, shared_db, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    saw = []
    _tick(monkeypatch, saw)
    assert layer_on.calls == 2 and saw == [{"AAPL": 190.0}]


def test_monitor_gets_its_quote_when_postgres_is_down(layer_on, monkeypatch):
    from swingbot.core.db import side_engine
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://x:x@127.0.0.1:1/none")
    side_engine.reset()
    started = time.monotonic()
    try:
        assert asyncio.run(loops._live_price_batch(["AAPL"])) == {"AAPL": 190.0}
    finally:
        side_engine.reset()
    assert time.monotonic() - started < 10 and layer_on.calls == 1


def test_off_mode_keeps_the_legacy_monitor_path(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(plan_manager, "monitor_quotes", lambda t: pytest.fail("layer path"))
    seen = []
    monkeypatch.setattr(loops, "_run_bounded",
                        lambda fn, args, timeout, label: seen.append(fn.keywords) or {"AAPL": 1.0})
    assert asyncio.run(loops._live_price_batch(["AAPL"])) == {"AAPL": 1.0}
    assert seen == [{"allow_stale": False}]


def test_on_mode_monitor_failure_is_a_warning_and_empty(monkeypatch, caplog):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")

    def boom(tickers):
        raise TimeoutError("hung")
    monkeypatch.setattr(plan_manager, "monitor_quotes", boom)
    with caplog.at_level(logging.DEBUG, logger=loops.log.name):
        assert asyncio.run(loops._live_price_batch(["AAPL"])) == {}
    assert [r.levelno for r in caplog.records if r.name == loops.log.name] == [logging.WARNING]
```

Before running it, confirm the side engine builds its URL from `config.DATABASE_URL`: `git -C $WT grep -n "DATABASE_URL" swingbot/core/db/side_engine.py` must show a hit. The `shared_db` and Postgres-down fixtures depend on that.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_plan_manager_shared_quote.py` and `python $WT/scripts/dev/testrun.py file tests/commands/test_trade_monitor_shared_quote.py`
Expected: FAIL with `ImportError: cannot import name 'QuotePrices'` / `AttributeError: ... 'monitor_quotes'`. The DB tests skip only if the local test Postgres is down; start it (`TEST_DATABASE_URL`) rather than accept a skip.

- [ ] **Step 4: Implement the shared monitor quote in `plan_manager.py`**

Add the imports `from swingbot.core.market.session import is_tape_open, now_et` (`RTH_OPEN` and `is_regular_session` are already imported) and `from swingbot.core.marketdata.shared.kinds import Asker, QuoteDetail`. Add after `PlanEvent`:

```python
#: v171 D2: exit transitions whose event carries the quote they were decided on.
EXIT_TRANSITIONS = frozenset({"closed", "tp1_partial"})

class QuotePrices(dict):
    """{ticker: price} for poll(), plus the QuoteDetail each price came from."""
    def __init__(self, prices: dict, details: dict):
        super().__init__(prices)
        self.details = details

def _session_label(now) -> str:
    if is_regular_session(now):
        return "regular"
    if not is_tape_open(now):
        return "closed"
    return "pre-market" if now_et(now).time() < RTH_OPEN else "after-hours"

def quote_stamp(q, now) -> dict | None:
    """The stored quote stamp (D2) of one monitor quote, or None."""
    if q is None or q.price is None:
        return None
    age = (now - q.trade_at).total_seconds() if q.trade_at else None
    return {"at": q.trade_at.isoformat() if q.trade_at else None,
            "kind": "yf-1m" if q.source == "yfinance-1m" else "trade",
            "age_s": round(age, 1) if age is not None else None,
            "session": _session_label(now),
            "confirmed": age is not None and age <= float(config.REBUILD_PRICE_MAX_AGE_S)}

def _stamp_exit_quote(event: PlanEvent, quote, now) -> None:
    if event.transition not in EXIT_TRANSITIONS or quote is None or "quote" in event.detail:
        return
    event.detail["quote"] = quote_stamp(quote, now or datetime.now(timezone.utc))

def _quote_suffix(stamp) -> str:
    return f" quote={stamp['kind']} {stamp['age_s']}s" if stamp else ""
```

In `log_plan_event`, the `_plan_line(...)` call's last argument becomes `(f" reason={reason}" if reason else "") + _quote_suffix(event.detail.get("quote"))`.

In `poll` (CC 20, so no new branch): insert `details = getattr(prices, "details", {})` on the line before `for plan in open_plans:`. Make `_stamp_exit_quote(event, details.get(plan.ticker), now)` the first statement inside `for event in new_events:`, before `log_plan_event(plan, event)`. That way `_on_event` (which passes `tp1_partial` details into the trade's leg) sees the stamp too.

Next to `_price_batch_fn`, move today's `_price_batch_fn` body verbatim into `_legacy_price_batch(tickers)` (docstring kept), then:

```python
def _monitor_quote_worker(tickers: list) -> tuple:
    """Spawned-worker body: fresh-only STOP_MONITOR quotes as docs, plus this
    process's D9 counter rows (the worker exits after the call)."""
    from swingbot.core.marketdata.data import get_quote_batch
    from swingbot.core.marketdata.shared import counters
    quotes = get_quote_batch(tickers, asker=Asker.STOP_MONITOR, fresh_only=True)
    return {t: q.to_doc() for t, q in quotes.items() if q.price}, counters.snapshot_and_clear()

def monitor_quotes(tickers: list) -> dict:
    """v171 D8: the one quote fetch trade_monitor and the plan manager share.
    Process-bounded like every live-price path (_run_bounded's docstring)."""
    if not tickers:
        return {}
    if config.MARKETDATA_LAYER == "off":
        return {t: QuoteDetail(symbol=t, price=p, trade_at=None, bid=None, ask=None,
                               quote_at=None, source="legacy")
                for t, p in _legacy_price_batch(tickers).items()}
    from swingbot.core.marketdata.shared import counters
    from swingbot.core.scanning import fetch
    out = fetch._run_bounded(_monitor_quote_worker, (list(tickers),),
                             float(getattr(config, "LIVE_PRICE_TIMEOUT_SECONDS", 60)),
                             label=f"stop monitor: shared quote batch of {len(tickers)} ticker(s)")
    if not out:
        return {}
    docs, rows = out
    counters.merge(rows)
    return {t: QuoteDetail.from_doc(d) for t, d in docs.items()}

def _price_batch_fn(tickers):
    """Fresh-only price map for plan transitions (see _legacy_price_batch).
    v171: count/on read monitor_quotes and keep each price's QuoteDetail."""
    if config.MARKETDATA_LAYER == "off":
        return _legacy_price_batch(tickers)
    details = monitor_quotes(tickers)
    return QuotePrices({t: q.price for t, q in details.items() if q.price}, details)
```

`_price_fn` passes `asker=Asker.STOP_MONITOR` to `get_current_price(ticker, allow_stale=False, ...)`. `_DEFAULT_PRICE_FN = _price_fn` and `_manager()` stay as they are.

- [ ] **Step 5: Route `loops._live_price_batch`**

Rename today's `_live_price_batch` to `_legacy_live_price_batch` with its body and docstring unchanged. Then add:

```python
async def _live_price_batch(tickers: list) -> dict:
    """Fresh-only live prices for the trade monitor, or {} on failure (see
    _legacy_live_price_batch). v171: count/on use plan_manager.monitor_quotes,
    the fetch the plan manager's tick then reuses from the shared cache."""
    if not tickers:
        return {}
    if config.MARKETDATA_LAYER == "off":
        return await _legacy_live_price_batch(tickers)
    from swingbot.core.planning import plan_manager
    try:
        quotes = await asyncio.to_thread(plan_manager.monitor_quotes, tickers)
    except Exception as exc:
        log.warning("trade_monitor: batch price fetch failed: %s", exc, exc_info=True)
        return {}
    return {t: q.price for t, q in quotes.items() if q.price}
```

`trade_monitor` itself is untouched (CC 13).

- [ ] **Step 6: Run the tests to verify they pass**

Run, one at a time: `python $WT/scripts/dev/testrun.py file tests/planning/test_plan_manager_shared_quote.py`, `... file tests/commands/test_trade_monitor_shared_quote.py`, `... file tests/commands/test_trade_monitor_task.py`, `... file tests/planning/test_trade_monitor_wiring.py`, `... file tests/planning/test_plan_manager_active.py`, `... file tests/scanning/test_log_levels_v111.py`, `... file tests/scanning/test_no_cross_ticker_mixing.py`
Expected: all PASS, `0 failed`. The last five run at `MARKETDATA_LAYER=off` and prove today's monitor path is intact.

- [ ] **Step 7: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/planning/plan_manager.py $WT/swingbot/commands/scanning/loops.py`
Expected: `PlanManager.poll` still C(20), `_step_active` D(21), `_on_event` C(15), `loops._session_scan_tick` C(15). No new function at C or above (`monitor_quotes`, `quote_stamp` and `_live_price_batch` are A/B).

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/commands/scanning/loops.py swingbot/core/planning/plan_manager.py tests/commands/test_trade_monitor_shared_quote.py tests/planning/test_plan_manager_shared_quote.py
git -C $WT commit -m "feat(v171): trade monitor and plan manager share one quote per tick; exit events carry the quote stamp"
```

