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
