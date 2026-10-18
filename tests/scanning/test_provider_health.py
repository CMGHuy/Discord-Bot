"""v148 O4: per-scan provider degradation metrics -- the fallback rate (one
formula, shared with the Risk page), empty symbols, and stale frames against
the previous NYSE session."""
import datetime as dt
import json
import logging

import pandas as pd
import pytest

from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.scanning import telemetry
from swingbot.core.scanning.telemetry import fallback_rate, provider_health

#: Monday 2026-01-19 (Martin Luther King Jr. Day) is an NYSE holiday, so the
#: session before Tuesday the 20th is Friday the 16th.
TUESDAY_AFTER_HOLIDAY = dt.date(2026, 1, 20)

NO_ALPACA = {"alpaca": 0, "yfinance": 4, "yfinance-fallback": 0, "cache": 0}
NO_PRICES = {"alpaca": 0, "yfinance": 0, "yfinance-fallback": 0, "none": 4}


def _frame(*stamps, tz=None):
    index = pd.DatetimeIndex([pd.Timestamp(s) for s in stamps])
    if tz:
        index = index.tz_localize(tz)
    return pd.DataFrame({"Close": [1.0] * len(index)}, index=index)


def _health(frames, tickers=None, data_sources=NO_ALPACA, price_sources=NO_PRICES,
            today=TUESDAY_AFTER_HOLIDAY):
    tickers = list(frames) if tickers is None else tickers
    return provider_health(tickers, frames, data_sources, price_sources, today)


# --- fallback_rate --------------------------------------------------------------

def test_fallback_rate_pools_every_count_dict():
    counts = [{"alpaca": 3, "yfinance-fallback": 1}, {"alpaca": 4, "yfinance-fallback": 2}]
    assert fallback_rate(counts) == pytest.approx(0.3)


def test_fallback_rate_reads_a_missing_bucket_as_zero():
    assert fallback_rate([{"yfinance-fallback": 1}, {"alpaca": 3}]) == pytest.approx(0.25)


def test_fallback_rate_is_none_when_alpaca_was_asked_for_nothing():
    assert fallback_rate([NO_ALPACA, NO_PRICES]) is None
    assert fallback_rate([]) is None


# --- provider_health: rates -------------------------------------------------------

def test_the_scan_rate_pools_daily_frames_and_live_prices():
    """The Risk page's own fixture (test_api_v1_risk.py), one scan: 6 / 80."""
    health = _health({"A": _frame("2026-01-16")},
                     data_sources={"alpaca": 2, "yfinance": 0, "yfinance-fallback": 0, "cache": 70},
                     price_sources={"alpaca": 72, "yfinance": 2, "yfinance-fallback": 6, "none": 0})
    assert health["provider_fallback_rate"] == 0.075


def test_the_scan_rate_is_none_without_alpaca():
    assert _health({"A": _frame("2026-01-16")})["provider_fallback_rate"] is None


def test_a_missing_price_sources_dict_is_tolerated():
    health = _health({"A": _frame("2026-01-16")},
                     data_sources={"alpaca": 1, "yfinance-fallback": 1}, price_sources=None)
    assert health["provider_fallback_rate"] == 0.5


def test_empty_symbols_count_missing_none_and_empty_frames():
    frames = {"A": _frame("2026-01-16"), "B": None, "C": pd.DataFrame()}
    health = _health(frames, tickers=["A", "B", "C", "D"])
    assert health["empty_symbols"] == 3
    assert health["empty_rate"] == 0.75


def test_an_empty_universe_has_no_empty_rate():
    health = _health({}, tickers=[])
    assert health == {"provider_fallback_rate": None, "empty_symbols": 0,
                      "empty_rate": None, "stale_symbols": 0}


# --- provider_health: stale frames ------------------------------------------------

def test_the_day_after_a_holiday_flags_nothing():
    frames = {t: _frame("2026-01-15", "2026-01-16") for t in ("A", "B", "C")}
    assert _health(frames)["stale_symbols"] == 0


def test_a_frame_ending_before_the_previous_session_is_stale():
    frames = {"FRESH": _frame("2026-01-16"), "TODAY": _frame("2026-01-20"),
              "OLD": _frame("2026-01-14", "2026-01-15")}
    assert _health(frames)["stale_symbols"] == 1


def test_a_tz_aware_index_is_read_in_new_york():
    """03:00 UTC on the 16th is 22:00 ET on the 15th: stale. 21:00 UTC on the
    16th is 16:00 ET on the 16th: fresh."""
    frames = {"LATE": _frame("2026-01-16 21:00", tz="UTC"),
              "EARLY": _frame("2026-01-16 03:00", tz="UTC")}
    assert _health(frames)["stale_symbols"] == 1


def test_a_naive_index_is_taken_as_market_dates():
    frames = {"A": _frame("2026-01-16 00:00"), "B": _frame("2026-01-15 23:59")}
    assert _health(frames)["stale_symbols"] == 1


def test_empty_frames_and_non_datetime_indexes_are_never_stale():
    frames = {"NONE": None, "EMPTY": pd.DataFrame(), "RANGE": pd.DataFrame({"Close": [1.0]})}
    assert _health(frames)["stale_symbols"] == 0


def test_outside_the_frozen_calendar_stale_is_unknown():
    health = _health({"A": _frame("2031-05-30")}, today=dt.date(2031, 6, 2))
    assert health["stale_symbols"] is None


def test_the_fields_are_json_ready():
    frames = {"A": _frame("2026-01-16"), "B": None}
    health = _health(frames, data_sources={"alpaca": 1, "yfinance-fallback": 0})
    assert set(health) == {"provider_fallback_rate", "empty_symbols", "empty_rate", "stale_symbols"}
    assert json.loads(json.dumps(health)) == health


# --- the scan row ---------------------------------------------------------------

@pytest.fixture
def clean_counts():
    swallowed_mod.reset()
    yield
    swallowed_mod.reset()


def test_the_scan_row_helper_returns_the_four_fields(monkeypatch):
    from swingbot.core.scanning import scan_run
    monkeypatch.setattr(scan_run, "market_today", lambda: TUESDAY_AFTER_HOLIDAY)
    stats = {"data_sources": {"alpaca": 3, "yfinance-fallback": 1}, "price_sources": {"alpaca": 0}}
    fields = scan_run._provider_health_fields(["A", "B"], {"A": _frame("2026-01-16")}, stats)
    assert fields == {"provider_fallback_rate": 0.25, "empty_symbols": 1,
                      "empty_rate": 0.5, "stale_symbols": 0}


def test_a_failing_metric_costs_its_fields_not_the_row(monkeypatch, caplog, clean_counts):
    from swingbot.core.scanning import scan_run

    def boom(*args, **kwargs):
        raise ValueError("bad frame")

    monkeypatch.setattr(telemetry, "provider_health", boom)
    with caplog.at_level(logging.WARNING, logger=scan_run.log.name):
        assert scan_run._provider_health_fields(["A"], {}, {}) == {}
    assert swallowed_mod.snapshot()["scan.provider_health"]["count"] == 1
    assert "provider health metrics failed" in caplog.text


def test_the_scan_merges_the_fields_into_its_telemetry_row():
    import inspect
    from swingbot.core.scanning import scan_run
    source = inspect.getsource(scan_run._sync_run_scan)
    assert "scan_stats.update(_provider_health_fields(tickers, fresh_data, scan_stats))" in source
