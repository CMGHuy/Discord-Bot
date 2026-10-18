import pandas as pd
import pytest
from swingbot.core.marketdata.providers import base

@pytest.mark.parametrize("t,ok", [
    ("AAPL", True), ("SPY", True), ("BRK-B", True),
    ("SAP.DE", False), ("^GSPC", False), ("EURUSD=X", False),
    ("GC=F", False), ("BTC-USD", False), ("", False),
])
def test_eligibility(t, ok):
    assert base.is_alpaca_eligible(t) is ok

def test_class_share_symbol_mapping():
    assert base.to_alpaca_symbol("BRK-B") == "BRK.B"
    assert base.to_alpaca_symbol("AAPL") == "AAPL"

def _alpaca_daily():
    idx = pd.DatetimeIndex(["2026-09-24 04:00", "2026-09-25 04:00"], tz="UTC", name="timestamp")
    return pd.DataFrame({"open": [1, 2], "high": [2, 3], "low": [0.5, 1.5],
                         "close": [1.5, 2.5], "volume": [100, 200],
                         "trade_count": [5, 6], "vwap": [1.4, 2.4]}, index=idx)

def test_to_yf_daily_matches_yfinance_shape():
    out = base.to_yf_daily(_alpaca_daily())
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert out.index.tz is None
    assert list(out.index) == [pd.Timestamp("2026-09-24"), pd.Timestamp("2026-09-25")]
    assert all(out.dtypes == "float64")

def test_to_yf_hourly_rebuilds_on_0930_grid():
    idx = pd.date_range("2026-09-25 09:00", "2026-09-25 16:00", freq="30min",
                        tz=base.NY).tz_convert("UTC")
    df = pd.DataFrame({"open": range(len(idx)), "high": range(1, len(idx) + 1),
                       "low": range(len(idx)), "close": range(len(idx)),
                       "volume": [10] * len(idx)}, index=idx).astype(float)
    out = base.to_yf_hourly(df)
    assert str(out.index.tz) == "America/New_York"
    assert [t.strftime("%H:%M") for t in out.index] == [
        "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]
    first = out.iloc[0]          # 09:30 + 10:00 half-hours, pre-market 09:00 excluded
    assert first["Open"] == 1 and first["Close"] == 2 and first["Volume"] == 20
    assert out.iloc[-1]["Volume"] == 10   # 15:30 bar is one half-hour; 16:00 excluded


# --- v162: history store converters (naive America/New_York wall-clock) -------

def _raw(utc_stamps):
    idx = pd.DatetimeIndex(utc_stamps, tz="UTC", name="timestamp")
    n = len(idx)
    return pd.DataFrame({"open": [1.0] * n, "high": [2.0] * n, "low": [0.5] * n,
                         "close": [1.5] * n, "volume": [100.0] * n,
                         "trade_count": [5] * n, "vwap": [1.4] * n}, index=idx)


def _hhmm(index):
    return [t.strftime("%Y-%m-%d %H:%M") for t in index]


def test_to_store_intraday_is_naive_new_york_wall_clock_across_both_dst_changes():
    # 09:30 ET is 14:30 UTC under EST and 13:30 UTC under EDT.
    # 2026: DST starts Sun 2026-03-08 and ends Sun 2026-11-01.
    out = base.to_store_intraday(_raw([
        "2026-03-06 14:30",   # Fri, EST
        "2026-03-09 13:30",   # Mon, EDT
        "2026-10-30 13:30",   # Fri, EDT
        "2026-11-02 14:30",   # Mon, EST
    ]))
    assert out.index.tz is None
    assert out.index.name == "Datetime"
    assert _hhmm(out.index) == ["2026-03-06 09:30", "2026-03-09 09:30",
                                "2026-10-30 09:30", "2026-11-02 09:30"]


def test_to_store_intraday_keeps_extended_hours():
    # 04:00 EDT = 08:00 UTC; the 19:45 EDT bar starts at 23:45 UTC
    out = base.to_store_intraday(_raw(["2026-03-09 08:00", "2026-03-09 23:45"]))
    assert _hhmm(out.index) == ["2026-03-09 04:00", "2026-03-09 19:45"]


def test_to_store_intraday_shape_sorted_and_deduplicated():
    raw = _raw(["2026-03-09 14:00", "2026-03-09 13:45", "2026-03-09 14:00"])
    raw.iloc[2, raw.columns.get_loc("close")] = 9.0       # the later duplicate wins
    out = base.to_store_intraday(raw)
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert all(out.dtypes == "float64")
    assert _hhmm(out.index) == ["2026-03-09 09:45", "2026-03-09 10:00"]
    assert out["Close"].iloc[-1] == 9.0


def test_to_store_intraday_treats_a_naive_index_as_utc():
    raw = _raw(["2026-03-09 13:30"])
    raw.index = raw.index.tz_localize(None)
    assert _hhmm(base.to_store_intraday(raw).index) == ["2026-03-09 09:30"]


def _thirty_minute_session(day):
    idx = pd.date_range(f"{day} 09:00", f"{day} 16:00", freq="30min",
                        tz=base.NY).tz_convert("UTC")
    return pd.DataFrame({"open": range(len(idx)), "high": range(1, len(idx) + 1),
                         "low": range(len(idx)), "close": range(len(idx)),
                         "volume": [10] * len(idx)}, index=idx).astype(float)


@pytest.mark.parametrize("day", ["2026-03-06", "2026-03-09"])   # EST, then EDT
def test_to_store_hourly_is_naive_on_the_0930_grid(day):
    out = base.to_store_hourly(_thirty_minute_session(day))
    assert out.index.tz is None and out.index.name == "Datetime"
    assert [t.strftime("%H:%M") for t in out.index] == [
        "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]
    assert {t.strftime("%Y-%m-%d") for t in out.index} == {day}
