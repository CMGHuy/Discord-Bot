import datetime as dt

import swingbot.config as config
import swingbot.core.macro.earnings as earnings

PAYLOAD = {"earningsCalendar": [
    {"date": "2026-07-01", "symbol": "NVDA"},      # past
    {"date": "2026-07-22", "symbol": "NVDA"},      # next
    {"date": "2026-10-21", "symbol": "NVDA"},
]}

NOW = dt.date(2026, 7, 14)


def _with_key(monkeypatch, payload=PAYLOAD):
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "k", raising=False)
    monkeypatch.setattr(earnings, "fetch_json", lambda *a, **k: payload)


def test_day_math(monkeypatch):
    _with_key(monkeypatch)
    assert earnings.days_to_earnings("NVDA", now=NOW) == 8
    assert earnings.earnings_within("NVDA", 10, now=NOW) is True
    assert earnings.earnings_within("NVDA", 3, now=NOW) is False


def test_no_future_earnings_is_none(monkeypatch):
    _with_key(monkeypatch, {"earningsCalendar": [{"date": "2026-07-01"}]})
    assert earnings.days_to_earnings("NVDA", now=NOW) is None


def test_no_key_none_and_no_network(monkeypatch):
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "", raising=False)

    def boom(*a, **k):
        raise AssertionError("no network without a key")
    monkeypatch.setattr(earnings, "fetch_json", boom)
    assert earnings.days_to_earnings("NVDA", now=NOW) is None
    assert earnings.earnings_within("NVDA", 3, now=NOW) is None   # unknown, never False


def test_events_fallback_is_opt_in(monkeypatch):
    """The repo already has a yfinance-backed earnings lookup in core/events.py.
    It is uncached network I/O, so this module never reaches for it unless the
    caller opts in — otherwise a scan-time check would silently start making
    per-ticker yfinance calls."""
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "", raising=False)
    called = {"n": 0}

    def fake_next(ticker):
        called["n"] += 1
        return dt.date(2026, 7, 20)

    import swingbot.core.events as events_mod
    monkeypatch.setattr(events_mod, "get_next_earnings_date", fake_next)

    assert earnings.days_to_earnings("NVDA", now=NOW) is None
    assert called["n"] == 0                                  # not consulted by default
    assert earnings.days_to_earnings("NVDA", now=NOW, fallback_to_events=True) == 6
    assert called["n"] == 1
