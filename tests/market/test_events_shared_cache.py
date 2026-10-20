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


def test_the_compression_gate_snapshot_runs_at_the_scan_tier(monkeypatch):
    from swingbot.core.scanning import scan_run
    seen = {}
    monkeypatch.setattr(events, "earnings_snapshot", lambda t, **kw: seen.update(kw))
    _, snapshot_of = scan_run._compression_hooks(NOW, None, {}, {}, {})
    snapshot_of("AAPL")
    assert seen["asker"] is Asker.SCAN


def test_a_stale_served_doc_keeps_its_true_age(monkeypatch):
    """BudgetDeferred path: layer serves the old doc; observed_at and the peek stamp show its age."""
    import time
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    old = NOW - dt.timedelta(hours=7)
    monkeypatch.setattr(layer, "get", lambda kind, symbols, fetch, **kw: {
        s: Entry(value=dict(DOC), fetched_at=old, source="yfinance", outcome="budget-deferred")
        for s in symbols})
    snap = events.earnings_snapshot("AAPL")
    assert abs((snap.observed_at - old).total_seconds()) < 1
    _, stamp = events._earnings_datetime_cache["AAPL"]
    assert time.monotonic() - stamp > 6 * 3600                    # already past the 6 h peek window
    assert events.peek_cached_earnings_datetime("AAPL") is events._NOT_CACHED


def test_nothing_cached_reads_as_query_not_ok(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(layer, "get", lambda *a, **k: {})
    snap = events.earnings_snapshot("AAPL")
    assert snap.query_ok is False and snap.reports == ()
