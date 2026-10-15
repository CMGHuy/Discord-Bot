"""v162: fetch one ticker x timeframe from Alpaca one calendar year at a time
and convert it to the store's frame shape (spec §1).

Each year is one `AlpacaProvider.history_bars` call routed through the
guards' token bucket and backoff, so memory stays bounded and every request
is counted. Conversion runs once on the joined raw frame: the hourly
resample needs whole sessions.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timezone

import pandas as pd

from swingbot.core.marketdata.providers.base import (
    to_store_hourly,
    to_store_intraday,
    to_yf_daily,
)

from alpaca_history.guards import TokenBucket, call_with_backoff

# Store timeframe -> the Alpaca timeframe key `history_bars` accepts. hourly is
# built from 30-minute bars (09:30-anchored); Alpaca's clock-aligned 1Hour
# bars are never requested.
ALPACA_TIMEFRAME = {"15min": "15min", "hourly": "30min", "daily": "1d"}

_CONVERTERS = {"15min": to_store_intraday, "hourly": to_store_hourly, "daily": to_yf_daily}


def _check(timeframe: str) -> None:
    if timeframe not in ALPACA_TIMEFRAME:
        raise ValueError(f"unknown store timeframe {timeframe!r}; "
                         f"expected one of {sorted(ALPACA_TIMEFRAME)}")


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def year_windows(start: date, end: datetime) -> list[tuple[datetime, datetime]]:
    """UTC (start, end) windows, one per calendar year, the last ending at `end`."""
    end = _utc(end)
    cur = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    windows = []
    while cur < end:
        nxt = datetime(cur.year + 1, 1, 1, tzinfo=timezone.utc)
        windows.append((cur, min(nxt, end)))
        cur = nxt
    return windows


def fetch_raw(provider, ticker: str, timeframe: str, start: date, end: datetime, *,
              limiter: TokenBucket, sleep=time.sleep) -> pd.DataFrame | None:
    """The raw Alpaca frame for `ticker` over [start, end], or None when no year has bars."""
    _check(timeframe)
    alpaca_tf = ALPACA_TIMEFRAME[timeframe]
    parts = []
    for lo, hi in year_windows(start, end):
        frame = call_with_backoff(
            lambda lo=lo, hi=hi: provider.history_bars(ticker, alpaca_tf, lo, hi),
            limiter=limiter, sleep=sleep)
        if frame is not None and len(frame):
            parts.append(frame)
    if not parts:
        return None
    raw = pd.concat(parts).sort_index()
    return raw[~raw.index.duplicated(keep="last")]


def to_store_frame(timeframe: str, raw: pd.DataFrame) -> pd.DataFrame:
    """Raw Alpaca bars -> the store's naive-index `Open..Volume` frame."""
    _check(timeframe)
    return _CONVERTERS[timeframe](raw)


def fetch_store_frame(provider, ticker: str, timeframe: str, start: date, end: datetime, *,
                      limiter: TokenBucket, sleep=time.sleep) -> pd.DataFrame | None:
    """`fetch_raw` then `to_store_frame`; None when there is nothing to store."""
    raw = fetch_raw(provider, ticker, timeframe, start, end, limiter=limiter, sleep=sleep)
    if raw is None:
        return None
    frame = to_store_frame(timeframe, raw)
    return frame if len(frame) else None
