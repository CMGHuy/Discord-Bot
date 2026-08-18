"""Horizon-to-horizon trend agreement (v33).

Every check here compares THIS bot's own horizons against each other, using
each horizon's own ema_fast/ema_slow from HORIZONS. That is the difference
from regime.get_htf_bias (a fixed 50/200 EMA proxy that only covers 5 of the
10 horizons) and from factors.mtf_alignment (a weekly resample).

Pure functions: no config reads, no I/O, so the gate that consumes them stays
testable and the backtest can call them directly.
"""
from __future__ import annotations

import pandas as pd

from swingbot.core.market.indicators import ema
from swingbot.core.market.strategy_types import HORIZONS

MACRO_ANCHOR_HORIZON = "6m"

_LADDER = list(HORIZONS.keys())


def adjacent_horizon(horizon_key: str) -> str | None:
    """The next horizon up, or None for the longest one (an exemption)."""
    try:
        idx = _LADDER.index(horizon_key)
    except ValueError:
        return None
    return _LADDER[idx + 1] if idx + 1 < len(_LADDER) else None


def horizon_trend(df: pd.DataFrame, horizon_key: str) -> str | None:
    """"bullish" when this horizon's ema_fast is above its ema_slow, else
    "bearish". None when the horizon is unknown or history is too short --
    callers must treat None as unknown, never as agreement."""
    settings = HORIZONS.get(horizon_key)
    if settings is None or df is None:
        return None
    slow = settings["ema_slow"]
    if len(df) < slow + 1:
        return None
    fast_series = ema(df["Close"], settings["ema_fast"])
    slow_series = ema(df["Close"], slow)
    if fast_series.empty or slow_series.empty:
        return None
    return "bullish" if fast_series.iloc[-1] > slow_series.iloc[-1] else "bearish"


def _verdict(trend: str | None, direction: str, reason_if_unknown: str) -> dict:
    if trend is None:
        return {"status": "exempt", "reason": reason_if_unknown, "trend": None}
    if trend == direction:
        return {"status": "aligned", "reason": f"{trend} trend agrees", "trend": trend}
    return {"status": "opposed", "reason": f"{trend} trend opposes", "trend": trend}


def adjacent_aligned(df: pd.DataFrame, horizon_key: str, direction: str) -> dict:
    """Does the next horizon up agree? 'exempt' when there is no higher
    horizon or its trend is unknowable -- never conflated with 'aligned'."""
    nxt = adjacent_horizon(horizon_key)
    if nxt is None:
        return {"status": "exempt", "reason": "no higher horizon above "
                f"{horizon_key}", "trend": None}
    return _verdict(horizon_trend(df, nxt), direction,
                    f"insufficient history for {nxt}")


def macro_aligned(df: pd.DataFrame, horizon_key: str, direction: str) -> dict:
    """Agreement with the fixed 6m macro anchor. Horizons at or beyond the
    anchor are exempt: a horizon cannot anchor to itself or to something
    shorter than itself."""
    if horizon_key not in _LADDER:
        return {"status": "exempt", "reason": "unknown horizon", "trend": None}
    if _LADDER.index(horizon_key) >= _LADDER.index(MACRO_ANCHOR_HORIZON):
        return {"status": "exempt",
                "reason": f"{horizon_key} is at or beyond the "
                          f"{MACRO_ANCHOR_HORIZON} anchor", "trend": None}
    return _verdict(horizon_trend(df, MACRO_ANCHOR_HORIZON), direction,
                    f"insufficient history for {MACRO_ANCHOR_HORIZON}")
