"""v144: the display-only context on an outlook card and the digest's regime
lines. Weekly and hourly price action is shown, never used as a gate: a gate
would be a new filter, and a new filter needs a SCREEN-PASS first."""
from __future__ import annotations

import pandas as pd

from swingbot.core.scanning.regime import get_market_regime

_WEEKLY_MA = 20
_HOURLY_SWING_BARS = 7


def _weekly(daily) -> pd.DataFrame | None:
    if daily is None or len(daily) == 0:
        return None
    frame = daily[["High", "Low", "Close"]].copy()
    frame.index = pd.DatetimeIndex(frame.index)
    weekly = frame.resample("W-FRI").agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
    return weekly if len(weekly) > _WEEKLY_MA else None


def weekly_phrase(daily) -> str | None:
    weekly = _weekly(daily)
    if weekly is None:
        return None
    ma = float(weekly["Close"].rolling(_WEEKLY_MA).mean().iloc[-1])
    side = "above" if float(weekly["Close"].iloc[-1]) > ma else "below"
    lows = "higher lows" if float(weekly["Low"].iloc[-1]) > float(weekly["Low"].iloc[-2]) else "lower lows"
    return f"Weekly: {side} 20w MA, {lows}"


def hourly_phrase(hourly, direction: str) -> str | None:
    if hourly is None or len(hourly) < _HOURLY_SWING_BARS:
        return None
    recent = hourly.tail(_HOURLY_SWING_BARS)
    close = float(recent["Close"].iloc[-1])
    if direction == "bullish":
        level = float(recent["Low"].min())
        return f"Hourly: {'holding' if close > level else 'at'} 1h swing low {level:.2f}"
    level = float(recent["High"].max())
    return f"Hourly: {'below' if close < level else 'at'} 1h swing high {level:.2f}"


def context_line(daily, hourly, direction: str) -> str | None:
    parts = [part for part in (weekly_phrase(daily), hourly_phrase(hourly, direction)) if part]
    return " · ".join(parts) or None


def regime_line(symbol: str, daily) -> str | None:
    if daily is None or len(daily) == 0:
        return None
    try:
        label = get_market_regime(daily, symbol).label
    except Exception:
        return None                       # too little history for the 200EMA regime
    weekly = weekly_phrase(daily)
    return f"{symbol}: {label}" + (f" · {weekly}" if weekly else "")


def regime_lines(frames: dict) -> list[str]:
    return [line for line in (regime_line(symbol, frame) for symbol, frame in frames.items()) if line]
