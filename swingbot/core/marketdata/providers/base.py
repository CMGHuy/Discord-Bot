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
SOURCE_SPOT = "spot"                 # v109: gold-api.com live spot quote
SOURCE_SPOT_SCALED = "spot-scaled"   # v109: futures bars x live spot ratio

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


def to_store_intraday(df: pd.DataFrame) -> pd.DataFrame:
    """v162 history store: raw Alpaca intraday bars (UTC) as naive
    America/New_York wall-clock bars labelled at the bar start, index
    `Datetime`. Every session is kept (04:00-20:00 ET); readers filter.
    A naive input index is taken as UTC. Duplicates (a year window's
    inclusive end) keep the last bar."""
    out = _yf_columns(df)
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    out.index = idx.tz_convert(NY).tz_localize(None)
    out.index.name = "Datetime"
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()


def to_store_hourly(df30: pd.DataFrame) -> pd.DataFrame:
    """v162 history store: `to_yf_hourly` (09:30-anchored, regular hours,
    the last bar 15:30-16:00 is a half-hour) with the New York index made
    naive. Wall-clock times are kept as they are."""
    out = to_yf_hourly(df30)
    out.index = pd.DatetimeIndex(out.index).tz_localize(None)
    out.index.name = "Datetime"
    return out
