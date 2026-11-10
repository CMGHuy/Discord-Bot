# v223 Provider alert counts only real Alpaca failures — Part 1: classification, routing, telemetry

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [2026-11-10-v223-provider-alert-stale-quote-split-design.md](../specs/2026-11-10-v223-provider-alert-stale-quote-split-design.md)
**Index:** [2026-11-10-v223-provider-alert-stale-quote-split_0-index.md](2026-11-10-v223-provider-alert-stale-quote-split_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there.

# Phase 1 — Classification and routing

### Task V223-1: One live-price tag list (base, fetch, scan_run)

**Model:** opus — crosses two `swingbot/core` packages (`marketdata`, `scanning`)

**Files:**
- Modify: `swingbot/core/marketdata/providers/base.py:12-18` (constants)
- Modify: `swingbot/core/scanning/fetch.py:44` (`_PRICE_SOURCE_KEYS`)
- Modify: `swingbot/core/scanning/scan_run.py:62` (`_SOURCE_BUCKETS`)
- Test: `tests/scanning/test_scan_telemetry_sources.py` (suite `scanning`)

**Interfaces:**
- Consumes: nothing.
- Produces: `base.SOURCE_OLD_PRINT = "yfinance-old-print"`,
  `base.PRICE_SOURCES = (SOURCE_ALPACA, SOURCE_YF, SOURCE_FALLBACK, SOURCE_OLD_PRINT)`.
  `fetch.fetch_stats()["price_sources"]` gains the key `"yfinance-old-print"`
  (5 keys in total). `scan_run._count_sources` keeps exactly
  `alpaca / yfinance / yfinance-fallback / cache`.

Spec items 4 and 7. The worker process ships `router.last_source` strings back
through `_price_batch_with_sources` (`fetch.py:74`); `_record_price_sources`
(`fetch.py:94`) puts any key not in `_PRICE_SOURCE_KEYS` into `"none"`, so the
new tag must be in the list. Item 7 needs no code: a ticker with no price is
not in `prices`, so it is not in `sources` and is already counted `"none"`.

- [ ] **Step 1: Update the two existing 4-key assertions and write the failing tests**

In `tests/scanning/test_scan_telemetry_sources.py`, change the expected dict
in `test_live_prices_count_each_tickers_provider` (around L80) to:

```python
    assert fetch.fetch_stats()["price_sources"] == {
        "alpaca": 1, "yfinance": 1, "yfinance-fallback": 0,
        "yfinance-old-print": 0, "none": 1}
```

`test_a_failed_chunk_counts_its_tickers_as_none` (around L95) only reads
`["none"]`; add one assertion under it so the bucket set is pinned there too:

```python
    assert set(fetch.fetch_stats()["price_sources"]) == {
        "alpaca", "yfinance", "yfinance-fallback", "yfinance-old-print", "none"}
```

Append these tests at the end of the file:

```python
# --- v223: one live-price tag list -----------------------------------------------

def test_price_source_keys_are_the_provider_tags_plus_none():
    from swingbot.core.marketdata.providers.base import PRICE_SOURCES
    from swingbot.core.scanning import fetch
    assert PRICE_SOURCES == ("alpaca", "yfinance", "yfinance-fallback", "yfinance-old-print")
    assert fetch._PRICE_SOURCE_KEYS == PRICE_SOURCES + ("none",)


def test_an_old_print_answered_by_yfinance_gets_its_own_bucket(monkeypatch):
    from swingbot.core.marketdata.providers import router
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(fetch, "get_current_price_batch",
                        lambda tickers: {"AAPL": 190.0, "MSFT": 410.0, "NVDA": 120.0})
    monkeypatch.setattr(router, "last_source", lambda t: {
        "AAPL": "alpaca", "MSFT": "yfinance-old-print", "NVDA": "yfinance-fallback"}.get(t))
    fetch.reset_fetch_stats()
    fetch._fetch_live_prices(["AAPL", "MSFT", "NVDA"])
    assert fetch.fetch_stats()["price_sources"] == {
        "alpaca": 1, "yfinance": 0, "yfinance-fallback": 1,
        "yfinance-old-print": 1, "none": 0}


def test_an_old_print_yfinance_also_failed_for_lands_in_none(monkeypatch):
    """Spec item 7: no price at all -> "none" (empty_rate covers it), never
    an old print."""
    from swingbot.core.marketdata.providers import router
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(fetch, "get_current_price_batch", lambda tickers: {"AAPL": 190.0})
    monkeypatch.setattr(router, "last_source", lambda t: {
        "AAPL": "alpaca", "MSFT": "yfinance-old-print"}.get(t))
    fetch.reset_fetch_stats()
    assert fetch._fetch_live_prices(["AAPL", "MSFT"]) == {"AAPL": 190.0}
    counts = fetch.fetch_stats()["price_sources"]
    assert counts["none"] == 1 and counts["yfinance-old-print"] == 0


def test_daily_buckets_never_include_the_old_print_tag():
    """The daily path (_merge, daily_delta) has no freshness rule and never
    emits yfinance-old-print; its buckets are built from the same constants."""
    from swingbot.core.marketdata.providers.base import (
        SOURCE_ALPACA, SOURCE_FALLBACK, SOURCE_OLD_PRINT, SOURCE_YF)
    from swingbot.core.scanning.scan_run import _SOURCE_BUCKETS, _count_sources
    assert _SOURCE_BUCKETS == (SOURCE_ALPACA, SOURCE_YF, SOURCE_FALLBACK)
    counts = _count_sources({"AAPL": _frame("alpaca"), "X": _frame("yfinance-old-print")})
    assert SOURCE_OLD_PRINT not in counts
    assert counts == {"alpaca": 1, "yfinance": 0, "yfinance-fallback": 0, "cache": 1}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_scan_telemetry_sources.py`
Expected: FAIL — `ImportError: cannot import name 'PRICE_SOURCES'` and the
5-key dict assertions.

- [ ] **Step 3: Add the constants to `base.py`**

In `swingbot/core/marketdata/providers/base.py`, replace the constant block
(L12-18) with:

```python
NY = ZoneInfo("America/New_York")
SOURCE_ALPACA = "alpaca"
SOURCE_YF = "yfinance"
SOURCE_FALLBACK = "yfinance-fallback"
#: v223: Alpaca's last IEX trade is older than ALPACA_MAX_TRADE_AGE_SECONDS
#: while the tape is open outside the regular session, so yfinance was asked
#: on purpose. Not an Alpaca failure: telemetry.fallback_rate never counts it.
SOURCE_OLD_PRINT = "yfinance-old-print"
SOURCE_SPOT = "spot"                 # v109: gold-api.com live spot quote
SOURCE_SPOT_SCALED = "spot-scaled"   # v109: futures bars x live spot ratio

#: v223: every tag the live-price router path writes to last_source for an
#: Alpaca-eligible or plain-yfinance ticker. fetch's price buckets are built
#: from it, so a new tag can never fall silently into "none".
PRICE_SOURCES = (SOURCE_ALPACA, SOURCE_YF, SOURCE_FALLBACK, SOURCE_OLD_PRINT)
```

- [ ] **Step 4: Derive `fetch._PRICE_SOURCE_KEYS`**

In `swingbot/core/scanning/fetch.py`, add the import next to the other
`swingbot.core.marketdata` imports (around L25-30):

```python
from swingbot.core.marketdata.providers.base import PRICE_SOURCES
```

and replace L44:

```python
_PRICE_SOURCE_KEYS = PRICE_SOURCES + ("none",)
```

- [ ] **Step 5: Derive `scan_run._SOURCE_BUCKETS`**

In `swingbot/core/scanning/scan_run.py`, add the import with the other
`swingbot.core` imports at the top of the file:

```python
from swingbot.core.marketdata.providers.base import SOURCE_ALPACA, SOURCE_FALLBACK, SOURCE_YF
```

and replace L62:

```python
#: Daily frames only: the daily path has no freshness rule, so it never emits
#: SOURCE_OLD_PRINT (v223) -- that tag is live-price only.
_SOURCE_BUCKETS = (SOURCE_ALPACA, SOURCE_YF, SOURCE_FALLBACK)
```

Before adding each import, run
`git grep -n "providers.base import" swingbot/core/scanning/fetch.py swingbot/core/scanning/scan_run.py`;
if a `from ...providers.base import` line already exists, extend it instead of
adding a second one.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_scan_telemetry_sources.py`
Expected: PASS, 0 failed.

Also run: `python scripts/dev/testrun.py file tests/scanning/test_provider_health.py`
Expected: PASS (its price-source dicts are literals and are unaffected).

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/marketdata/providers/base.py swingbot/core/scanning/fetch.py swingbot/core/scanning/scan_run.py tests/scanning/test_scan_telemetry_sources.py
git commit -m "feat(v223): one live-price tag list -- SOURCE_OLD_PRINT, PRICE_SOURCES, fetch and scan_run buckets derived from it"
```

### Task V223-2: Alpaca old-print classifier and `*_answers` methods

**Model:** sonnet — normal TDD inside one module, behaviour fully given by the spec's table

**Files:**
- Modify: `swingbot/core/marketdata/providers/alpaca_provider.py:78-83` (`_tape_is_live` docstring), `:158-211` (`_fresh_price`, `_detail`, `latest_quotes`, `latest_prices`)
- Test: `tests/marketdata/test_alpaca_provider.py` (suite `market-data`)

**Interfaces:**
- Consumes: `session.is_tape_open(now)`, `session.is_nyse_regular_session(now)`
  (`swingbot/core/market/session.py:56/234`, both accept an aware UTC
  datetime and convert to ET); `session` is already imported at L13.
- Produces (consumed by V223-3, by method **name** through `router._attempt`):
  - `AlpacaProvider._price_verdict(snap, now, max_age_s) -> tuple[float | None, bool]`
  - `AlpacaProvider.latest_price_answers(tickers, max_trade_age_s) -> tuple[dict[str, float], frozenset[str]]`
  - `AlpacaProvider.latest_quote_answers(tickers, max_trade_age_s) -> tuple[dict[str, QuoteDetail], frozenset[str]]`
  - `latest_prices` / `latest_quotes` keep their exact return shapes (element 0).
  - `_detail(ticker, snap, now, max_age_s)` now returns `tuple[QuoteDetail | None, bool]` (private; its only caller is `latest_quote_answers`).

Spec items 1 and 2. The second element is the set of tickers answered with an
old print. It comes from the trade's own branch in `_price_verdict`, never
from the shape of the detail: an old print with no two-sided quote has **no**
detail but is still in the set. Nothing is stored on `self`, because one
provider object is shared across the router's `_quote_pool` threads.

- [ ] **Step 1: Write the failing tests**

Append to `tests/marketdata/test_alpaca_provider.py` (after
`test_latest_quotes_overnight_old_print_is_kept`; `_snap`, `_qsnap`,
`FakeClient`, `ap`, `QuoteDetail` and `pd` are already defined or imported above):

```python
# --- v223: old print vs miss vs hit ------------------------------------------------
# From 2026-11-01 ET is UTC-5. Tue 2026-11-10 is a full session; Thu 2026-11-26
# (Thanksgiving) a full holiday; Fri 2026-11-27 a 13:00 ET early close.

def _utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


_HIT, _OLD, _MISS = (190.0, False), (None, True), (None, False)


@pytest.mark.parametrize("now, expected", [
    (_utc(2026, 11, 10, 8, 59), _HIT),     # 03:59 ET, tape closed
    (_utc(2026, 11, 10, 9, 0), _OLD),      # 04:00 ET, pre-market begins
    (_utc(2026, 11, 10, 14, 29), _OLD),    # 09:29 ET
    (_utc(2026, 11, 10, 14, 30), _MISS),   # 09:30 ET, regular session
    (_utc(2026, 11, 10, 20, 59), _MISS),   # 15:59 ET
    (_utc(2026, 11, 10, 21, 0), _OLD),     # 16:00 ET, after-hours
    (_utc(2026, 11, 11, 0, 59), _OLD),     # 19:59 ET
    (_utc(2026, 11, 11, 1, 0), _HIT),      # 20:00 ET, tape closed
    (_utc(2026, 11, 27, 18, 30), _OLD),    # 13:30 ET on the early-close day
    (_utc(2026, 11, 26, 17, 0), _HIT),     # 12:00 ET on a full holiday
])
def test_price_verdict_for_an_hour_old_trade(now, expected):
    prov = ap.AlpacaProvider("k", "s", "iex", client=FakeClient(), now=lambda: now)
    snap = _snap(190.0, now - pd.Timedelta(hours=1))
    assert prov._price_verdict(snap, now, 300) == expected


@pytest.mark.parametrize("now", [_utc(2026, 11, 10, 9, 30), _utc(2026, 11, 10, 15, 0),
                                 _utc(2026, 11, 10, 22, 0), _utc(2026, 11, 14, 15, 0)])
def test_price_verdict_fresh_trade_is_a_hit_at_any_time(now):
    prov = ap.AlpacaProvider("k", "s", "iex", client=FakeClient(), now=lambda: now)
    assert prov._price_verdict(_snap(190.0, now - pd.Timedelta(seconds=30)), now, 300) == _HIT


@pytest.mark.parametrize("snap", [
    _qsnap(None, None, 189.9, 190.1, _utc(2026, 11, 10, 13, 0)),                       # no trade
    _qsnap(0.0, _utc(2026, 11, 10, 12, 0), 189.9, 190.1, _utc(2026, 11, 10, 13, 0)),   # zero price
    SimpleNamespace(latest_quote=None),                                                # no trade attr
])
def test_price_verdict_without_a_positive_trade_is_a_miss(snap):
    now = _utc(2026, 11, 10, 13, 0)                                    # 08:00 ET, pre-market
    prov = ap.AlpacaProvider("k", "s", "iex", client=FakeClient(), now=lambda: now)
    assert prov._price_verdict(snap, now, 300) == _MISS


_PRE = _utc(2026, 11, 10, 13, 0)                                       # 08:00 ET


def _pre_prov(snaps):
    return ap.AlpacaProvider("k", "s", "iex", client=FakeClient(snaps=snaps), now=lambda: _PRE)


def test_no_snapshot_is_a_miss_not_an_old_print():
    assert _pre_prov({}).latest_price_answers(["AAPL"], 300) == ({}, frozenset())
    assert _pre_prov({}).latest_quote_answers(["AAPL"], 300) == ({}, frozenset())


def test_latest_price_answers_names_the_old_prints():
    snaps = {"AAPL": _snap(190.0, _PRE - pd.Timedelta(seconds=30)),
             "MSFT": _snap(410.0, _PRE - pd.Timedelta(hours=12)),
             "NVDA": _snap(0.0, _PRE - pd.Timedelta(seconds=30))}
    prices, old = _pre_prov(snaps).latest_price_answers(["AAPL", "MSFT", "NVDA"], 300)
    assert prices == {"AAPL": 190.0}
    assert old == frozenset({"MSFT"})


def test_latest_quote_answers_old_print_keeps_its_quote():
    snaps = {"AAPL": _qsnap(190.0, _PRE - pd.Timedelta(hours=12), 189.9, 190.1, _PRE)}
    details, old = _pre_prov(snaps).latest_quote_answers(["AAPL"], 300)
    q = details["AAPL"]
    assert q.price is None and q.trade_at is None
    assert (q.bid, q.ask, q.quote_at) == (189.9, 190.1, _PRE)
    assert old == frozenset({"AAPL"})


def test_latest_quote_answers_old_print_without_a_two_sided_quote_is_still_named():
    snaps = {"AAPL": _qsnap(190.0, _PRE - pd.Timedelta(hours=12))}
    assert _pre_prov(snaps).latest_quote_answers(["AAPL"], 300) == ({}, frozenset({"AAPL"}))


def test_latest_quote_answers_rekeys_class_shares_in_both_elements():
    snaps = {"BRK.B": _qsnap(410.0, _PRE - pd.Timedelta(hours=12))}
    assert _pre_prov(snaps).latest_quote_answers(["BRK-B"], 300) == ({}, frozenset({"BRK-B"}))


def test_old_trade_in_the_regular_session_is_never_an_old_print():
    """A frozen IEX feed in regular hours stays an Alpaca miss and still alerts."""
    now = _utc(2026, 11, 10, 16, 0)                                    # 11:00 ET
    snaps = {"AAPL": _qsnap(190.0, now - pd.Timedelta(minutes=20), 189.9, 190.1, now)}
    prov = ap.AlpacaProvider("k", "s", "iex", client=FakeClient(snaps=snaps), now=lambda: now)
    details, old = prov.latest_quote_answers(["AAPL"], 300)
    assert details["AAPL"].price is None and old == frozenset()


def test_the_wrappers_return_exactly_element_zero():
    snaps = {"AAPL": _qsnap(190.0, _PRE - pd.Timedelta(seconds=30), 189.9, 190.1, _PRE),
             "MSFT": _qsnap(410.0, _PRE - pd.Timedelta(hours=12), 409.0, 411.0, _PRE),
             "NVDA": _qsnap(0.0, _PRE, None, None, None)}
    tickers = ["AAPL", "MSFT", "NVDA"]
    assert _pre_prov(snaps).latest_prices(tickers, 300) == \
        _pre_prov(snaps).latest_price_answers(tickers, 300)[0]
    assert _pre_prov(snaps).latest_quotes(tickers, 300) == \
        _pre_prov(snaps).latest_quote_answers(tickers, 300)[0]


def test_answers_make_one_snapshot_call():
    c = FakeClient(snaps={"AAPL": _snap(190.0, _PRE - pd.Timedelta(hours=12))})
    prov = ap.AlpacaProvider("k", "s", "iex", client=c, now=lambda: _PRE)
    prov.latest_quote_answers(["AAPL", "MSFT"], 300)
    assert len(c.requests) == 1 and str(c.requests[0].feed.value) == "iex"
```

The existing tests `test_stale_iex_trade_is_a_miss_in_session`,
`test_latest_quotes_stale_trade_in_session_keeps_the_quote`,
`test_latest_quotes_premarket_friday_print_is_a_miss_so_yfinance_can_answer`,
`test_latest_quotes_after_hours_old_print_is_a_miss` and
`test_latest_quotes_overnight_old_print_is_kept` must keep passing unchanged:
through the wrappers an old print still has no price.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_alpaca_provider.py`
Expected: FAIL — `AttributeError: 'AlpacaProvider' object has no attribute '_price_verdict'`
(and `latest_price_answers` / `latest_quote_answers`).

- [ ] **Step 3: Implement the classifier and the answers methods**

In `swingbot/core/marketdata/providers/alpaca_provider.py`, update the
`_tape_is_live` docstring (L78-83) so it no longer claims every old print in
the tape is a miss:

```python
def _tape_is_live(now: datetime) -> bool:
    """A live US tape (pre-market, regular, after-hours; holiday aware). Inside
    it an old IEX print is not served: in the regular session it is a miss, in
    pre-market and after-hours an old print (v223), both re-asked from
    yfinance. Outside it (weekend, overnight) the last print IS the latest one."""
    return session.is_tape_open(now)
```

Replace `_fresh_price` (L158-164) with the classifier plus a thin wrapper:

```python
    def _price_verdict(self, snap, now, max_age_s):
        """(price, old_print) for one snapshot -- the one place a trade is
        classified (v223). A positive trade is a hit when fresh or when no
        tape is live. An old one while the tape is live is an old print
        outside the NYSE regular session (pre-market, after-hours, the
        afternoon of an early close) and a miss inside it, so a frozen
        regular-hours feed still counts as an Alpaca failure. No trade or a
        non-positive price is a miss."""
        trade = getattr(snap, "latest_trade", None)
        if trade is None or not trade.price or trade.price <= 0:
            return None, False
        if (now - trade.timestamp).total_seconds() <= max_age_s or not _tape_is_live(now):
            return float(trade.price), False
        return None, not session.is_nyse_regular_session(now)

    def _fresh_price(self, snap, now, max_age_s):
        return self._price_verdict(snap, now, max_age_s)[0]
```

Replace `_detail`, `latest_quotes` and `latest_prices` (L176-211) with:

```python
    def _detail(self, ticker, snap, now, max_age_s):
        """(QuoteDetail or None, old_print). An old print with no two-sided
        quote has no detail but keeps its old_print flag."""
        price, old_print = self._price_verdict(snap, now, max_age_s)
        bid, ask, quote_at = self._quote_sides(snap)
        if price is None and quote_at is None:
            return None, old_print
        trade_at = snap.latest_trade.timestamp if price is not None else None
        return QuoteDetail(symbol=ticker, price=price, trade_at=trade_at, bid=bid, ask=ask,
                           quote_at=quote_at, source=f"alpaca-{self._live_feed.value}"), old_print

    def _snapshots(self, tickers):
        """One get_stock_snapshot call: ([(our ticker, snap), ...], now)."""
        by_symbol = {to_alpaca_symbol(t): t for t in tickers}
        req = StockSnapshotRequest(symbol_or_symbols=list(by_symbol), feed=self._live_feed)
        snaps = self._call("get_stock_snapshot", req) or {}
        pairs = [(by_symbol[sym], snap) for sym, snap in snaps.items() if sym in by_symbol]
        return pairs, self._now()

    def latest_quote_answers(self, tickers, max_trade_age_s):
        """v223: (details, old-print tickers) from one snapshot call. A pure
        return value: the provider is shared across quote threads."""
        pairs, now = self._snapshots(tickers)
        out, old = {}, set()
        for ticker, snap in pairs:
            detail, old_print = self._detail(ticker, snap, now, max_trade_age_s)
            if detail is not None:
                out[ticker] = detail
            if old_print:
                old.add(ticker)
        return out, frozenset(old)

    def latest_quotes(self, tickers, max_trade_age_s):
        return self.latest_quote_answers(tickers, max_trade_age_s)[0]

    def latest_price_answers(self, tickers, max_trade_age_s):
        """v223: (prices, old-print tickers) from one snapshot call."""
        pairs, now = self._snapshots(tickers)
        out, old = {}, set()
        for ticker, snap in pairs:
            price, old_print = self._price_verdict(snap, now, max_trade_age_s)
            if price is not None:
                out[ticker] = price
            elif old_print:
                old.add(ticker)
        missing = [t for t in tickers if t not in out and t not in old]
        if missing:
            log.debug("Alpaca snapshot: no fresh price for %s", ", ".join(missing[:10]))
        return out, frozenset(old)

    def latest_prices(self, tickers, max_trade_age_s):
        return self.latest_price_answers(tickers, max_trade_age_s)[0]
```

`git grep -n "_fresh_price\|\._detail(" swingbot` must show no other caller of
`_detail` (the brief verified only `latest_quotes` called it).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_alpaca_provider.py`
Expected: PASS, 0 failed (the new table and the five pre-existing old-print tests).

Also run the direct wrapper callers' tests:
`python scripts/dev/testrun.py file tests/scripts/test_provider_parity_report.py`
Expected: PASS.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every touched method is well under 15).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/marketdata/providers/alpaca_provider.py tests/marketdata/test_alpaca_provider.py
git commit -m "feat(v223): Alpaca classifies old prints apart from misses -- _price_verdict, latest_*_answers, wrappers keep their shape"
```

### Task V223-3: Router tags old prints apart from misses

**Model:** sonnet — one module; `latest_quotes` is C(12), so the shared steps move into named helpers (no legacy >= 15 split)

**Files:**
- Modify: `swingbot/core/marketdata/providers/router.py:25-26` (import), `:30` (`_QUOTE_METHODS`), `:117` (`_stats`), `:340-344` (logging helpers), `:445-462` (`latest_prices`), `:486-507` (`latest_quotes`)
- Test: `tests/marketdata/test_provider_router.py` (suite `market-data`)

**Interfaces:**
- Consumes: `base.SOURCE_OLD_PRINT` (V223-1);
  `AlpacaProvider.latest_price_answers` / `latest_quote_answers` returning
  `(dict, frozenset[str])` (V223-2).
- Produces: `router.last_source(t) == "yfinance-old-print"` for an
  old-print ticker yfinance answered; `router.stats()["old_print"]`;
  `latest_prices` / `latest_quotes` signatures and return shapes unchanged
  (callers in `data.py:226,235,249,254,359,827` untouched).

Spec item 3. Rules:
- The router asks `latest_<kind>_answers` when the active provider has that
  attribute, otherwise the plain method. When the call fails (`_attempt`
  returns None) or the provider has no `*_answers`, the old-print set is
  empty, so every unpriced eligible symbol is a miss tagged
  `yfinance-fallback`. That can only over-report failures.
- Old prints and misses are re-asked from yfinance **in one call** (the same
  `unpriced` list, in `wanted` order, as today's `misses` call), then tagged
  per ticker. The number of yfinance calls is unchanged.
- `_QUOTE_METHODS` holds method **names**; `_attempt` picks `_quote_pool` by
  that name, so both new names go into it or they would run on the bulk-bars pool.
- `_stats["fallback"]` counts misses only; `_stats["old_print"]` counts old
  prints. `reset()` already zeroes every `_stats` key generically.
- `latest_quotes` keeps the Alpaca bid/ask on an old-print detail
  (`_with_alpaca_quote`), as for misses.

- [ ] **Step 1: Write the failing tests**

Append to `tests/marketdata/test_provider_router.py` (after the
`latest_quotes` tests; `FakeProvider`, `enabled`, `_use`, `_q`, `_T`,
`yf_quotes`, `AlpacaMiss` are already defined or imported in the file):

```python
# --- v223: old prints are tagged apart from misses ----------------------------------

class AnswersProvider(FakeProvider):
    """A provider with the v223 *_answers contract; `old` names old prints."""
    def __init__(self, old=(), **kw):
        super().__init__(**kw)
        self.old = frozenset(old)
    def latest_price_answers(self, tickers, max_age):
        return self.latest_prices(tickers, max_age), self.old & set(tickers)
    def latest_quote_answers(self, tickers, max_age):
        return self.latest_quotes(tickers, max_age), self.old & set(tickers)


def yf_prices(calls, prices):
    def f(tickers):
        calls.append(list(tickers))
        return {t: prices[t] for t in tickers if t in prices}
    return f


def test_answers_methods_run_on_the_quote_pool():
    assert {"latest_price_answers", "latest_quote_answers"} <= router._QUOTE_METHODS


def test_latest_prices_tags_old_prints_and_misses_apart(enabled, monkeypatch):
    _use(monkeypatch, AnswersProvider(prices={"AAPL": 190.0}, old={"MSFT"})); calls = []
    out = router.latest_prices(["AAPL", "MSFT", "NVDA"],
                               yf_prices(calls, {"MSFT": 410.0, "NVDA": 120.0}))
    assert calls == [["MSFT", "NVDA"]]                     # one yfinance call, as before
    assert out == {"AAPL": 190.0, "MSFT": 410.0, "NVDA": 120.0}
    assert router.last_source("AAPL") == "alpaca"
    assert router.last_source("MSFT") == "yfinance-old-print"
    assert router.last_source("NVDA") == "yfinance-fallback"
    s = router.stats()
    assert (s["alpaca"], s["fallback"], s["old_print"]) == (1, 1, 1)


def test_latest_quotes_tags_old_prints_and_keeps_alpaca_bid_ask(enabled, monkeypatch):
    old = _q("MSFT", None, bid=409.0, ask=411.0)
    _use(monkeypatch, AnswersProvider(quotes={"AAPL": _q("AAPL", 190.0), "MSFT": old},
                                      old={"MSFT"})); calls = []
    out = router.latest_quotes(["AAPL", "MSFT", "NVDA"],
                               yf_quotes(calls, {"MSFT": 410.2, "NVDA": 120.0}))
    assert calls == [["MSFT", "NVDA"]]
    assert (out["MSFT"].price, out["MSFT"].source) == (410.2, "yfinance-1m")
    assert (out["MSFT"].bid, out["MSFT"].ask, out["MSFT"].quote_at) == (409.0, 411.0, _T)
    assert router.last_source("MSFT") == "yfinance-old-print"
    assert router.last_source("NVDA") == "yfinance-fallback"
    s = router.stats()
    assert (s["alpaca"], s["fallback"], s["old_print"]) == (1, 1, 1)


def test_an_old_print_yfinance_cannot_answer_has_no_source(enabled, monkeypatch):
    _use(monkeypatch, AnswersProvider(old={"MSFT"})); calls = []
    out = router.latest_prices(["MSFT"], yf_prices(calls, {}))
    assert out == {} and router.last_source("MSFT") is None
    assert router.stats()["old_print"] == 1


@pytest.mark.parametrize("entry", ["prices", "quotes"])
def test_a_failed_answers_call_makes_every_symbol_a_miss(enabled, monkeypatch, entry):
    _use(monkeypatch, AnswersProvider(old={"MSFT"}, exc=AlpacaMiss("500"))); calls = []
    if entry == "prices":
        router.latest_prices(["AAPL", "MSFT"], yf_prices(calls, {"AAPL": 1.0, "MSFT": 2.0}))
    else:
        router.latest_quotes(["AAPL", "MSFT"], yf_quotes(calls, {"AAPL": 1.0, "MSFT": 2.0}))
    assert calls == [["AAPL", "MSFT"]]
    assert router.last_source("AAPL") == router.last_source("MSFT") == "yfinance-fallback"
    s = router.stats()
    assert (s["fallback"], s["old_print"]) == (2, 0)


@pytest.mark.parametrize("entry", ["prices", "quotes"])
def test_a_provider_without_answers_tags_every_miss_fallback(enabled, monkeypatch, entry):
    _use(monkeypatch, FakeProvider()); calls = []
    if entry == "prices":
        router.latest_prices(["MSFT"], yf_prices(calls, {"MSFT": 2.0}))
    else:
        router.latest_quotes(["MSFT"], yf_quotes(calls, {"MSFT": 2.0}))
    assert router.last_source("MSFT") == "yfinance-fallback"
    assert router.stats()["old_print"] == 0


def test_reset_zeroes_the_old_print_count(enabled, monkeypatch):
    _use(monkeypatch, AnswersProvider(old={"MSFT"}))
    router.latest_prices(["MSFT"], yf_prices([], {"MSFT": 2.0}))
    router.reset()
    assert router.stats()["old_print"] == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_provider_router.py`
Expected: FAIL — `_QUOTE_METHODS` lacks the names, `KeyError: 'old_print'`,
and MSFT tagged `yfinance-fallback`.

- [ ] **Step 3: Constants, stats key and quote-pool names**

In `router.py`, extend the base import (L25-26):

```python
from swingbot.core.marketdata.providers.base import (
    SOURCE_ALPACA, SOURCE_FALLBACK, SOURCE_OLD_PRINT, SOURCE_SPOT, SOURCE_YF,
    is_alpaca_eligible)
```

Replace L30:

```python
_QUOTE_METHODS = frozenset({"latest_prices", "latest_quotes",
                            "latest_price_answers", "latest_quote_answers"})
```

Replace L117:

```python
_stats = {"alpaca": 0, "yfinance": 0, "fallback": 0, "old_print": 0, "failures": 0}
```

- [ ] **Step 4: Shared live-price helpers**

Directly below `_log_fallback` (L340-344) add:

```python
def _log_unpriced(kind: str, unpriced: list, old: frozenset) -> None:
    """DEBUG lines keeping real misses and v223 old prints apart."""
    _log_fallback(kind, [t for t in unpriced if t not in old])
    if old:
        log.debug("Alpaca %s: old IEX print for %d symbol(s), re-asked from yfinance: %s",
                  kind, len(old), ", ".join(sorted(old)[:10]))


def _ask_alpaca(kind: str, wanted: list) -> tuple[dict, frozenset]:
    """v223: Alpaca's live answer for `wanted` plus the tickers it answered
    with an old print. `kind` is "price" or "quote". Uses
    latest_<kind>_answers when the active provider has it; without it, or on
    a failed call, the old-print set is empty so every unpriced symbol counts
    as a miss -- this can over-report failures, never hide one."""
    if not wanted:
        return {}, frozenset()
    age = int(config.ALPACA_MAX_TRADE_AGE_SECONDS)
    answers = f"latest_{kind}_answers"
    if hasattr(_active_provider(), answers):
        result = _attempt(answers, wanted, age)
        return (result[0] or {}, frozenset(result[1])) if result is not None else ({}, frozenset())
    return _attempt(f"latest_{kind}s", wanted, age) or {}, frozenset()


def _unpriced(wanted: list, priced, old: frozenset) -> tuple[list, frozenset]:
    """Eligible tickers with no Alpaca price, in `wanted` order, and the old
    prints among them."""
    unpriced = [t for t in wanted if t not in priced]
    return unpriced, frozenset(t for t in unpriced if t in old)


def _yf_answers(yf_fetch, rest: list, unpriced: list, old: frozenset) -> dict:
    """yfinance for the non-eligible group and the unpriced group (one call
    each, as before v223); tags each answered ticker's source."""
    fetched_rest = yf_fetch(rest) if rest else {}
    fetched_unpriced = yf_fetch(unpriced) if unpriced else {}
    _last_source.update({t: SOURCE_YF for t in fetched_rest})
    _last_source.update({t: SOURCE_OLD_PRINT if t in old else SOURCE_FALLBACK
                         for t in fetched_unpriced})
    return {**fetched_rest, **fetched_unpriced}


def _count_live(n_alpaca: int, n_rest: int, unpriced: list, old: frozenset) -> None:
    _stats["alpaca"] += n_alpaca
    _stats["yfinance"] += n_rest
    _stats["old_print"] += len(old)
    _stats["fallback"] += len(unpriced) - len(old)
```

`_active_provider()` is breaker-gated and cheap; `hasattr(None, ...)` is
False, so a disabled or open-breaker router takes the plain branch, where
`_attempt` returns None as before.

- [ ] **Step 5: Rewrite the two entry points on the helpers**

Replace `latest_prices` (L445-462):

```python
def latest_prices(tickers, yf_fetch):
    spot, tickers = spot_metals.split_spot(tickers)
    wanted, rest = _split(tickers)
    got, old_set = _ask_alpaca("price", wanted)
    unpriced, old = _unpriced(wanted, got, old_set)
    _log_unpriced("latest_prices", unpriced, old)
    out = dict(got)
    out.update(_yf_answers(yf_fetch, rest, unpriced, old))
    _last_source.update({t: SOURCE_ALPACA for t in got})
    _count_live(len(got), len(rest), unpriced, old)
    out.update(_spot_prices(spot))
    return out
```

Replace `latest_quotes` (L486-507):

```python
def latest_quotes(tickers, yf_fetch):
    """v171: latest_prices' routing with timestamps. A symbol whose Alpaca
    answer has no fresh trade price is re-asked from yfinance, keeping the
    Alpaca bid/ask on the merged detail; v223 tags an old print
    yfinance-old-print and a real miss yfinance-fallback."""
    spot, tickers = spot_metals.split_spot(tickers)
    wanted, rest = _split(tickers)
    got, old_set = _ask_alpaca("quote", wanted)
    priced = {t: q for t, q in got.items() if q.price is not None}
    unpriced, old = _unpriced(wanted, priced, old_set)
    _log_unpriced("latest_quotes", unpriced, old)
    out = dict(got)
    fetched = _yf_answers(yf_fetch, rest, unpriced, old)
    out.update({t: _with_alpaca_quote(q, got.get(t)) for t, q in fetched.items()})
    _last_source.update({t: SOURCE_ALPACA for t in priced})
    _count_live(len(priced), len(rest), unpriced, old)
    out.update(_spot_quotes(spot))
    return out
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_provider_router.py`
Expected: PASS, 0 failed (new tests and every pre-existing `latest_*` test).

Then run the other router-touching files, one at a time:
- `python scripts/dev/testrun.py file tests/marketdata/test_provider_router_robust.py`
- `python scripts/dev/testrun.py file tests/marketdata/test_provider_router_spot.py`
- `python scripts/dev/testrun.py file tests/marketdata/test_router_shared_budget.py`
- `python scripts/dev/testrun.py file tests/marketdata/test_data_alpaca_routing.py`
- `python scripts/dev/testrun.py file tests/commands/test_trade_monitor_shared_quote.py`

Expected: each PASS. Their fake providers have no `*_answers`, so they take
the plain branch unchanged.

- [ ] **Step 7: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; `latest_quotes` drops below its old C(12).

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/marketdata/providers/router.py tests/marketdata/test_provider_router.py
git commit -m "feat(v223): router tags old IEX prints yfinance-old-print apart from real misses; failed or plain calls stay fallback"
```

# Phase 2 — Telemetry and display

### Task V223-4: `old_print_rate` telemetry field and embed line

**Model:** sonnet — a new metric and an embed line, behaviour given by the spec

**Files:**
- Modify: `swingbot/core/scanning/telemetry.py:1-10` (import), `:65-73` (`fallback_rate` docstring), `:113-137` (`provider_health`)
- Modify: `swingbot/core/scanning/scan_run.py:76-79` (`_provider_health_fields` docstring only)
- Modify: `swingbot/commands/scanning/notices.py:232-254` (`_provider_lines` neighbour, both embeds)
- Test: `tests/scanning/test_provider_health.py`, `tests/scanning/test_ops_watch.py` (suite `scanning`)

**Interfaces:**
- Consumes: `base.SOURCE_ALPACA`, `SOURCE_FALLBACK`, `SOURCE_OLD_PRINT` (V223-1).
- Produces: `telemetry.old_print_rate(price_sources: dict | None) -> float | None`;
  `provider_health(...)` returns five keys: `provider_fallback_rate`,
  `old_print_rate`, `empty_symbols`, `empty_rate`, `stale_symbols`. The row
  gets the field through `scan_run._provider_health_fields`, unchanged.
  `ops_watch.provider_verdict` is **not** changed: it reads only
  `provider_fallback_rate` and `empty_rate`.

Spec items 5, 6 and 9 (embeds). `fallback_rate` keeps its formula: an old
print is in neither its numerator nor its denominator. `old_print_rate` is
computed over `price_sources` only, because daily frames can never be old
prints. It is display only, with no alert and no threshold.

- [ ] **Step 1: Update the field-set tests and write the failing tests**

In `tests/scanning/test_provider_health.py`:

`test_the_fields_are_json_ready` (around L121): replace the `set(health)` assertion with

```python
    assert set(health) == {"provider_fallback_rate", "old_print_rate", "empty_symbols",
                           "empty_rate", "stale_symbols"}
```

`test_the_scan_row_helper_returns_the_four_fields` (around L137): rename it to
`test_the_scan_row_helper_returns_the_provider_fields` and replace its final
assertion with (`price_sources` is `{"alpaca": 0}`, so the old-print pool is empty):

```python
    assert fields == {"provider_fallback_rate": 0.25, "old_print_rate": None,
                      "empty_symbols": 1, "empty_rate": 0.5, "stale_symbols": 0}
```

Extend the existing top-of-file import to
`from swingbot.core.scanning.telemetry import fallback_rate, old_print_rate, provider_health`,
then append to the `fallback_rate` section of the same file:

```python
# --- v223: old prints ---------------------------------------------------------------

PRE_MARKET_DATA = {"alpaca": 85, "yfinance": 0, "yfinance-fallback": 0, "cache": 2}
PRE_MARKET_PRICES = {"alpaca": 7, "yfinance": 0, "yfinance-fallback": 0,
                     "yfinance-old-print": 80, "none": 0}


def test_old_prints_are_neither_hits_nor_failures_in_the_fallback_rate():
    health = _health({"A": _frame("2026-01-16")}, data_sources=PRE_MARKET_DATA,
                     price_sources=PRE_MARKET_PRICES)
    assert health["provider_fallback_rate"] == 0.0


def test_old_print_rate_is_over_live_price_asks_only():
    health = _health({"A": _frame("2026-01-16")}, data_sources=PRE_MARKET_DATA,
                     price_sources=PRE_MARKET_PRICES)
    assert health["old_print_rate"] == pytest.approx(round(80 / 87, 4))


def test_old_print_rate_counts_real_misses_in_its_pool():
    prices = {"alpaca": 6, "yfinance-fallback": 2, "yfinance-old-print": 2, "yfinance": 9}
    assert old_print_rate(prices) == pytest.approx(0.2)


@pytest.mark.parametrize("prices", [
    {"alpaca": 0, "yfinance": 4, "yfinance-fallback": 0, "yfinance-old-print": 0, "none": 3},
    {},
    None,
    "not a dict",
])
def test_old_print_rate_is_none_without_live_price_asks(prices):
    assert old_print_rate(prices) is None


def test_all_zero_counts_give_both_rates_none():
    zero_data = {"alpaca": 0, "yfinance": 0, "yfinance-fallback": 0, "cache": 0}
    zero_prices = dict.fromkeys(("alpaca", "yfinance", "yfinance-fallback",
                                 "yfinance-old-print", "none"), 0)
    health = _health({"A": _frame("2026-01-16")}, data_sources=zero_data,
                     price_sources=zero_prices)
    assert health["provider_fallback_rate"] is None and health["old_print_rate"] is None


def test_a_price_dict_without_old_prints_reads_zero():
    """A count dict with no old-print bucket (as before v223) reads 0.0: Alpaca was asked."""
    health = _health({"A": _frame("2026-01-16")},
                     price_sources={"alpaca": 7, "yfinance": 0, "yfinance-fallback": 1, "none": 0})
    assert health["old_print_rate"] == 0.0
```

(The last case is 0 / 8 = 0.0, not None: Alpaca *was* asked and answered
with no old print. "—" is for rows that never carried the field, which
`ops_health` reads as None.)

In `tests/scanning/test_ops_watch.py`, add below the `ROW_PRE_V148` constant:

```python
#: v223: a pre-market scan -- every unanswered symbol was an old print, not a failure.
ROW_PRE_MARKET = {**ROW_OK, "provider_fallback_rate": 0.0, "old_print_rate": 0.92}
```

add two cases to the `test_provider_verdict` parametrize list:

```python
    (ROW_PRE_MARKET, False, None),                                # old prints never alert
    ({**ROW_PRE_MARKET, "provider_fallback_rate": 0.25}, False, "alert"),   # real misses still do
```

and append these embed tests after `test_the_provider_recovery_shows_the_healthy_figures`:

```python
def test_the_provider_alert_shows_the_old_print_rate_of_live_price_asks():
    embed = notices.provider_degraded_embed({**ROW_BAD, "old_print_rate": 0.42}, 20.0, 5.0)
    assert "• Old IEX prints: 42.0% of live-price asks" in embed.description
    assert "Stale symbols: 2" in embed.description


def test_the_provider_recovery_shows_the_old_print_rate():
    embed = notices.provider_recovered_embed(ROW_PRE_MARKET)
    assert "• Old IEX prints: 92.0% of live-price asks" in embed.description


@pytest.mark.parametrize("build", [
    lambda row: notices.provider_degraded_embed(row, 20.0, 5.0),
    notices.provider_recovered_embed,
])
def test_a_row_without_the_old_print_rate_reads_as_a_dash(build):
    assert "• Old IEX prints: — of live-price asks" in build(ROW_BAD).description
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_provider_health.py`
Expected: FAIL — `ImportError: cannot import name 'old_print_rate'`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_ops_watch.py`
Expected: FAIL on the three embed tests (no "Old IEX prints" line). The two
new `provider_verdict` cases already PASS (verdict logic is unchanged); they
are regression pins.

- [ ] **Step 3: Implement `old_print_rate` and the field**

In `swingbot/core/scanning/telemetry.py`, add below the existing imports:

```python
from swingbot.core.marketdata.providers.base import (
    SOURCE_ALPACA, SOURCE_FALLBACK, SOURCE_OLD_PRINT)
```

Replace the `fallback_rate` docstring (formula unchanged):

```python
def fallback_rate(source_counts: list[dict]) -> float | None:
    """yfinance-fallback over everything Alpaca was asked for (hits + misses),
    pooled across `source_counts` -- daily-frame and live-price count dicts
    alike. None when Alpaca was asked for nothing (disabled, or its breaker
    open throughout). The one formula behind each scan's
    ``provider_fallback_rate`` and the Risk page's pooled rate (v106).
    v223: yfinance-old-print is in neither term -- an old IEX print outside
    the regular session is neither an Alpaca hit nor an Alpaca failure."""
    hits = sum(int(d.get(SOURCE_ALPACA, 0)) for d in source_counts)
    misses = sum(int(d.get(SOURCE_FALLBACK, 0)) for d in source_counts)
    return misses / (hits + misses) if hits + misses else None


def old_print_rate(price_sources: dict | None) -> float | None:
    """v223: old IEX prints re-asked from yfinance, as a share of live-price
    asks -- yfinance-old-print / (alpaca + yfinance-fallback +
    yfinance-old-print), over `price_sources` only (daily frames are never
    old prints). None when that sum is 0 or there is no count dict. Display
    only: nothing alerts on it."""
    if not isinstance(price_sources, dict):
        return None
    old = int(price_sources.get(SOURCE_OLD_PRINT, 0))
    asked = old + sum(int(price_sources.get(k, 0)) for k in (SOURCE_ALPACA, SOURCE_FALLBACK))
    return old / asked if asked else None
```

In `provider_health`, change the docstring's first line to
`"""v148 O4: one scan's provider degradation, five telemetry-row fields.`,
add this bullet after the `provider_fallback_rate` bullet:

```
    - ``old_print_rate``: :func:`old_print_rate` over `price_sources` only
      (v223), labelled "of live-price asks" wherever it is shown.
```

and replace the body with:

```python
    rate = fallback_rate([d for d in (data_sources, price_sources) if isinstance(d, dict)])
    old = old_print_rate(price_sources)
    empty = sum(1 for ticker in tickers if _is_empty(frames.get(ticker)))
    return {
        "provider_fallback_rate": None if rate is None else round(rate, 4),
        "old_print_rate": None if old is None else round(old, 4),
        "empty_symbols": empty,
        "empty_rate": round(empty / len(tickers), 4) if tickers else None,
        "stale_symbols": _stale_count(tickers, frames, today),
    }
```

Also update `scan_run._provider_health_fields`'s docstring wording "the four
provider-degradation fields" / "these four fields" to "the provider-degradation
fields" / "these fields" (`swingbot/core/scanning/scan_run.py` around L76-79;
docstring only, no code change) and add the file to the commit.

- [ ] **Step 4: Add the embed line**

In `swingbot/commands/scanning/notices.py`, add below `_provider_lines`:

```python
def _old_print_line(row: dict) -> str:
    """v223: display only -- old IEX prints outside regular hours, re-asked
    from yfinance. A pre-v223 row has no field and reads "—"."""
    return f"• Old IEX prints: {_rate(row.get('old_print_rate'))} of live-price asks"
```

Replace both embed builders:

```python
def provider_degraded_embed(row: dict, fallback_pct: float, empty_pct: float):
    """v148 O4: the newest scan breached a provider threshold."""
    fallback, empty = _provider_lines(row)
    return system_embed(Kind.HEALTH_ALERT, "market-data provider degraded", (
        f"{fallback}, alert above {fallback_pct:g}%\n"
        f"{empty}, alert above {empty_pct:g}%\n"
        f"• Stale symbols: {_value(row.get('stale_symbols'))}\n"
        f"{_old_print_line(row)}\n"
        f"• Scan at: {_value(row.get('at'))}\n"
        "Scans continue: fallback tickers ran on yfinance data, empty ones were skipped."))


def provider_recovered_embed(row: dict):
    """v148 O4: a scan is back under both provider thresholds."""
    fallback, empty = _provider_lines(row)
    return system_embed(Kind.HEALTH_RECOVERED, "market-data provider healthy again",
                        f"{fallback}\n{empty}\n{_old_print_line(row)}\n"
                        f"• Scan at: {_value(row.get('at'))}")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_provider_health.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/scanning/test_ops_watch.py`
Expected: PASS, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/telemetry.py swingbot/core/scanning/scan_run.py tests/scanning/test_provider_health.py
git commit -m "feat(v223): old_print_rate telemetry field over live-price asks; fallback_rate excludes old prints"
git add swingbot/commands/scanning/notices.py tests/scanning/test_ops_watch.py
git commit -m "feat(v223): provider degraded/recovered embeds show the old-print rate; old-print rows never alert"
```
