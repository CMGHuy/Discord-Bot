"""v109: spot metals never report earnings -- and never ask Yahoo."""
import pytest

from swingbot.core.market import events


@pytest.fixture(autouse=True)
def _no_yahoo(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a spot metal reached Yahoo's earnings endpoints")
    monkeypatch.setattr(events.yf, "Ticker", boom)
    events._earnings_datetime_cache.clear()
    events._earnings_datetimes_cache.clear()
    yield
    events._earnings_datetime_cache.clear()
    events._earnings_datetimes_cache.clear()


@pytest.mark.parametrize("symbol", ["XAUUSD", "XAGUSD", "xauusd"])
def test_spot_metals_have_no_earnings(symbol):
    assert events.get_next_earnings_date(symbol) is None
    assert events.get_next_earnings_datetime(symbol) is None
    assert events.get_earnings_datetimes(symbol, refresh=True) == []
    assert events.earnings_within_window(symbol, 30) is None


def test_never_reports_covers_funds_and_spot(monkeypatch):
    monkeypatch.setattr(events, "is_etf", lambda t: t == "SPY")
    assert events._never_reports("SPY") and events._never_reports("XAUUSD")
    assert not events._never_reports("AAPL") and not events._never_reports("GC=F")
