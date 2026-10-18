"""v171 D2/D6: data kinds, askers, priorities, windows, cache keys, quote shape."""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.kinds import (
    OUTCOMES, Asker, DataKind, Entry, QuoteDetail, cache_key, fresh_request,
    is_fresh_request, resolve_asker)

T0 = datetime(2026, 10, 16, 14, 30, tzinfo=timezone.utc)


def test_kind_values_are_short_stable_strings():
    assert [k.value for k in DataKind] == ["quote", "daily", "intraday", "index", "earnings", "meta"]


def test_priorities_put_money_first():
    assert [a.priority for a in Asker] == [1, 2, 3, 4, 5, 5, 5]
    assert Asker.STOP_MONITOR.priority < Asker.REQUOTE.priority < Asker.SCAN.priority


@pytest.mark.parametrize("asker,attr", [
    (Asker.STOP_MONITOR, "QUOTE_MAX_AGE_MONITOR_S"), (Asker.REQUOTE, "QUOTE_MAX_AGE_REQUOTE_S"),
    (Asker.SCAN, "QUOTE_MAX_AGE_SCAN_S"), (Asker.BACKGROUND, "QUOTE_MAX_AGE_SCAN_S"),
    (Asker.ADMIN_DASHBOARD, "QUOTE_MAX_AGE_DASHBOARD_S"), (Asker.ADMIN_PAGE, "QUOTE_MAX_AGE_ADMIN_S"),
])
def test_quote_window_reads_the_askers_knob_at_call_time(monkeypatch, asker, attr):
    monkeypatch.setattr(config, attr, 7)
    assert asker.window_s(DataKind.QUOTE) == 7.0


def test_default_quote_windows_match_the_spec():
    assert Asker.REQUOTE.window_s(DataKind.QUOTE) == 5.0
    assert Asker.ADMIN_DASHBOARD.window_s(DataKind.QUOTE) == 15.0
    assert Asker.ADMIN_PAGE.window_s(DataKind.QUOTE) == 60.0


def test_other_kind_windows():
    assert Asker.SCAN.window_s(DataKind.INDEX_QUOTE) == 60.0
    assert Asker.STOP_MONITOR.window_s(DataKind.EARNINGS) == 21600.0
    assert Asker.ADMIN_PAGE.window_s(DataKind.INTRADAY_BARS) == float(kinds.INTRADAY_MAX_AGE_S)
    assert Asker.SCAN.window_s(DataKind.DAILY_BARS) == 0.0
    assert Asker.SCAN.window_s(DataKind.METADATA) is None


def test_fresh_asker_is_zero_except_for_persistent_metadata():
    for kind in (DataKind.QUOTE, DataKind.INDEX_QUOTE, DataKind.EARNINGS, DataKind.INTRADAY_BARS):
        assert Asker.ADMIN_FRESH.window_s(kind) == 0.0
    assert Asker.ADMIN_FRESH.window_s(DataKind.METADATA) is None


def test_cache_key_upper_cases_the_symbol():
    assert cache_key(DataKind.QUOTE, "aapl") == "quote:AAPL:"
    assert cache_key(DataKind.INTRADAY_BARS, "msft", "1h") == "intraday:MSFT:1h"


def test_entry_age():
    entry = Entry(value=1.0, fetched_at=T0, source="alpaca", outcome="hit")
    assert entry.age_s(T0 + timedelta(seconds=12.5)) == 12.5


def test_quote_mid_needs_a_sane_two_sided_quote():
    q = QuoteDetail("AAPL", 100.0, T0, 99.9, 100.1, T0, "alpaca-iex")
    assert q.mid() == pytest.approx(100.0)
    assert QuoteDetail("AAPL", None, None, None, 100.1, T0, "x").mid() is None
    assert QuoteDetail("AAPL", None, None, 0.0, 100.1, T0, "x").mid() is None
    assert QuoteDetail("AAPL", None, None, 100.2, 100.1, T0, "x").mid() is None   # crossed


def test_quote_doc_round_trip_keeps_timestamps():
    q = QuoteDetail("AAPL", 100.0, T0, 99.9, 100.1, T0 + timedelta(seconds=2), "alpaca-iex")
    doc = q.to_doc()
    assert doc["trade_at"] == T0.isoformat()
    assert QuoteDetail.from_doc(doc) == q
    empty = QuoteDetail("XYZ", None, None, None, None, None, "yfinance-1m")
    assert QuoteDetail.from_doc(empty.to_doc()) == empty


def test_outcomes_are_the_d9_set():
    assert OUTCOMES == ("hit", "shared-wait", "fetched", "budget-deferred", "failed")


def test_fresh_request_resolves_admin_askers_only():
    assert resolve_asker(Asker.ADMIN_PAGE) is Asker.ADMIN_PAGE
    with fresh_request():
        assert is_fresh_request() is True
        assert resolve_asker(Asker.ADMIN_PAGE) is Asker.ADMIN_FRESH
        assert resolve_asker(Asker.ADMIN_DASHBOARD) is Asker.ADMIN_FRESH
        assert resolve_asker(Asker.STOP_MONITOR) is Asker.STOP_MONITOR
    assert is_fresh_request() is False
