"""HTF trend detection."""
from __future__ import annotations

import pandas as pd


def _resample_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Open": df["Open"].resample("W-FRI").first(),
        "High": df["High"].resample("W-FRI").max(),
        "Low": df["Low"].resample("W-FRI").min(),
        "Close": df["Close"].resample("W-FRI").last(),
    }).dropna()


def _pivots(closes: pd.Series, span: int = 2) -> tuple[list, list]:
    highs, lows = [], []
    vals = closes.values
    for i in range(span, len(vals) - span):
        window = vals[i - span:i + span + 1]
        if vals[i] == window.max():
            highs.append(float(vals[i]))
        elif vals[i] == window.min():
            lows.append(float(vals[i]))
    return highs, lows


def _trend(closes: pd.Series, fast: int, slow: int) -> str:
    """SMA cross + pivot structure; SMAs within 0.5% of each other are
    treated as flat (keeps oscillating ranges deterministic)."""
    if len(closes) < slow + 5:
        return "range"
    sma_fast = float(closes.rolling(fast).mean().iloc[-1])
    sma_slow = float(closes.rolling(slow).mean().iloc[-1])
    if abs(sma_fast / sma_slow - 1.0) < 0.005:
        return "range"

    # Extract window for pivot analysis
    window_size = min(len(closes), 8 * fast)
    window_closes = closes.iloc[-window_size:]
    highs, lows = _pivots(window_closes)

    # If no pivots found, use overall window trend as fallback
    if len(highs) == 0 and len(lows) == 0:
        # Use first vs last close in window for trend direction
        first_close = float(window_closes.iloc[0])
        last_close = float(window_closes.iloc[-1])
        if last_close > first_close:
            # Uptrend: higher lows (lows increase from first to last)
            highs = [first_close, last_close]
        else:
            # Downtrend: lower lows (lows decrease from first to last)
            lows = [first_close, last_close]

    up_structure = ((len(highs) >= 2 and highs[-1] > highs[0])
                    or (len(lows) >= 2 and lows[-1] > lows[0]))
    down_structure = ((len(highs) >= 2 and highs[-1] < highs[0])
                      or (len(lows) >= 2 and lows[-1] < lows[0]))
    if sma_fast > sma_slow and up_structure:
        return "up"
    if sma_fast < sma_slow and down_structure:
        return "down"
    return "range"


def htf_trend(df_daily: pd.DataFrame) -> dict:
    weekly_df = _resample_weekly(df_daily)
    daily = _trend(df_daily["Close"], 20, 50)
    if len(weekly_df) < 45:                      # 40w SMA + margin
        return {"weekly": "range", "daily": daily,
                "detail": "insufficient weekly history"}
    weekly = _trend(weekly_df["Close"], 10, 40)
    return {"weekly": weekly, "daily": daily,
            "detail": f"weekly {weekly} (10/40w SMA + pivots), daily {daily}"}
