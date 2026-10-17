"""v148 OH14: earnings handlers count under their tags."""
import pytest

from swingbot import config
from swingbot.core.infra import swallowed as sw
from swingbot.core.market import earnings_history, events
from swingbot.core.marketdata.ticker_utils import candidate_symbols


def _boom(*a, **k):
    raise RuntimeError("probe")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    sw.reset()
    monkeypatch.setattr(events.yf, "Ticker", _boom)
    yield
    sw.reset()


def test_next_date_counts_per_candidate():
    assert events.get_next_earnings_date("AAPL") is None
    assert sw.snapshot()["earnings.next_date"]["count"] == len(candidate_symbols("AAPL"))


def test_next_datetime_counts():
    events._fetch_next_earnings_datetime("AAPL")
    assert sw.snapshot()["earnings.next_datetime"]["count"] == len(candidate_symbols("AAPL"))


def test_datetimes_counts():
    events.get_earnings_datetimes("AAPL", refresh=True)
    assert sw.snapshot()["earnings.datetimes"]["count"] == len(candidate_symbols("AAPL"))


def test_snapshot_counts():
    events.earnings_snapshot("AAPL")
    assert sw.snapshot()["earnings.snapshot"]["count"] == len(candidate_symbols("AAPL"))


def test_warmup_counts(monkeypatch):
    monkeypatch.setattr(events, "get_next_earnings_datetime", _boom)
    events.warm_earnings_cache_background(["AAPL"]).join(5)
    assert sw.snapshot()["earnings.warmup"]["count"] == 1


def test_history_refresh_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(earnings_history, "get_earnings_datetimes", _boom)
    earnings_history.refresh_watchlist_earnings(["AAPL"])
    assert sw.snapshot()["earnings.history_refresh"]["last_error"] == "RuntimeError: probe"
