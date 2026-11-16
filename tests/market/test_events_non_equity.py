"""Indices, futures, FX pairs and crypto never report earnings -- and never ask Yahoo.

Production (2026-11-08..11-15) logged ~93 "No earnings dates found" plus 93
"No fundamentals data found" Yahoo 404s for ^VIX, ^NDX, ^GSPC, ^DJI and GC=F:
only funds and spot metals were exempt from the earnings fetch.
"""
import pytest

from swingbot.core.market import events


@pytest.fixture(autouse=True)
def _no_yahoo(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a non-equity symbol reached Yahoo's earnings endpoints")
    monkeypatch.setattr(events.yf, "Ticker", boom)
    events._earnings_datetime_cache.clear()
    events._earnings_datetimes_cache.clear()
    yield
    events._earnings_datetime_cache.clear()
    events._earnings_datetimes_cache.clear()


@pytest.mark.parametrize("symbol", ["^VIX", "^NDX", "^GSPC", "^DJI", "SPX", "GC=F", "CL=F",
                                    "EURUSD", "EURUSD=X", "BTC", "BTC-USD"])
def test_non_equities_have_no_earnings(symbol):
    assert events._never_reports(symbol)
    assert events.get_next_earnings_date(symbol) is None
    assert events.get_next_earnings_datetime(symbol) is None
    assert events.get_earnings_datetimes(symbol, refresh=True) == []
    assert events.earnings_within_window(symbol, 30) is None


@pytest.mark.parametrize("symbol", ["AAPL", "INTU", "GOLD", "BRK.B"])
def test_equities_still_report(monkeypatch, symbol):
    monkeypatch.setattr(events, "is_etf", lambda t: False)
    assert not events._never_reports(symbol)


def test_batch_lookup_never_asks_the_layer_for_non_equities(monkeypatch):
    asked = []

    def fake_get(kind, keys, fetch, **kwargs):
        asked.extend(keys)
        return {}

    monkeypatch.setattr(events, "is_etf", lambda t: False)
    monkeypatch.setattr(events.layer, "get", fake_get)
    events._earnings_docs(["AAPL", "^VIX", "GC=F", "BTC-USD"], asker=events.Asker.BACKGROUND)
    assert asked == ["AAPL"]
