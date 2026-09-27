"""v106 provider contract: which symbols Alpaca may serve, and the frame
shapes every provider must hand back -- identical to what the yfinance path
returns today, so no consumer can tell the sources apart."""
import re
from zoneinfo import ZoneInfo

import pandas as pd

from swingbot.core.marketdata.asset_class import classify

NY = ZoneInfo("America/New_York")
SOURCE_ALPACA = "alpaca"
SOURCE_YF = "yfinance"
SOURCE_FALLBACK = "yfinance-fallback"

_US_SHAPE = re.compile(r"^[A-Z]{1,5}(-[A-Z])?$")
_COLS = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}


def is_alpaca_eligible(ticker: str) -> bool:
    t = (ticker or "").upper().strip()
    if not _US_SHAPE.match(t):
        return False
    return classify(t) in {"equity", "etf"}


def to_alpaca_symbol(ticker: str) -> str:
    return ticker.upper().strip().replace("-", ".")


def _yf_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df[list(_COLS)].rename(columns=_COLS).astype("float64")


def to_yf_daily(df: pd.DataFrame) -> pd.DataFrame:
    out = _yf_columns(df)
    out.index = pd.DatetimeIndex(df.index).tz_convert(NY).normalize().tz_localize(None)
    out.index.name = "Date"
    return out


def to_yf_hourly(df30: pd.DataFrame) -> pd.DataFrame:
    frame = _yf_columns(df30)
    frame.index = pd.DatetimeIndex(df30.index).tz_convert(NY)
    frame = frame.between_time("09:30", "15:59")
    out = frame.resample("60min", origin="start_day", offset="30min",
                         label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    out = out.dropna(subset=["Open"])
    out.index.name = "Datetime"
    return out
