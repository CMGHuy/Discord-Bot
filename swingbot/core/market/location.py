# swingbot/core/market/location.py
"""Location, leg-phase and zone-quality features at the entry bar (v125).

Every value is computed at ``df``'s final bar from ``df`` alone, so the
caller's slicing (``df.iloc[:i + 1]`` in replay, the completed frame live)
is the only time boundary. Swing pivots come only from v121's
``structure.confirmed_pivots`` (the single home of the confirmation lag);
levels come from ``levels.build_level_map`` built here on the same frame;
zone lifecycle comes from ``levels_lifecycle.classify_levels``, which slices
to ``:i + 1`` itself. Frozen descriptive constants: 60-bar minimum, 10-bar
departure window, the lifecycle module's TOUCH_ATR_MULT touch tolerance.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from swingbot.core.market.indicators import atr
from swingbot.core.market.levels import build_level_map
from swingbot.core.market.levels_lifecycle import TOUCH_ATR_MULT, classify_levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.market.structure import _num, confirmed_pivots

MIN_BARS = 60             # below this every key is None
DEPARTURE_WINDOW = 10     # frozen: bars after the last touch that count as the departure
LOCATION_KEYS = ("zone_dist_atr", "room_atr", "range_pos", "leg_phase",
                 "zone_state", "zone_touches", "zone_departure_atr")


def side_levels(df: pd.DataFrame, horizon_key: str, direction: str):
    """(entry-side level, opposing level) as ``levels.Level`` or None.

    Bullish: nearest support below the close, nearest resistance above.
    Bearish mirrors. Unknown horizon -> (None, None)."""
    h = HORIZONS.get(horizon_key)
    if h is None:
        return None, None
    supports, resistances = build_level_map(df, h, float(df["Close"].iloc[-1]))
    support = supports[0] if supports else None
    resistance = resistances[0] if resistances else None
    return (support, resistance) if direction == "bullish" else (resistance, support)


def _range_pos(close: float, sh: float, sl: float, bullish: bool) -> float | None:
    if not sh > sl:
        return None
    return _num((close - sl) / (sh - sl) if bullish else (sh - close) / (sh - sl))


def _leg_phase(close: float, sh: float, sl: float, bullish: bool) -> str:
    beyond, broken = (close > sh, close < sl) if bullish else (close < sl, close > sh)
    if beyond:
        return "impulse"
    return "broken" if broken else "pullback"


def swing_location(df: pd.DataFrame, direction: str) -> dict:
    """``range_pos`` and ``leg_phase`` from the last confirmed swing high/low."""
    piv = confirmed_pivots(df).iloc[-1]
    sh, sl = piv["last_sh"], piv["last_sl"]
    if pd.isna(sh) or pd.isna(sl):
        return {"range_pos": None, "leg_phase": None}
    close, bullish = float(df["Close"].iloc[-1]), direction == "bullish"
    if not math.isfinite(close):
        return {"range_pos": None, "leg_phase": None}
    return {"range_pos": _range_pos(close, float(sh), float(sl), bullish),
            "leg_phase": _leg_phase(close, float(sh), float(sl), bullish)}


def zone_departure_atr(df: pd.DataFrame, t: int, level: float | None, direction: str,
                       atr_value: float | None) -> float | None:
    """Best direction-signed close beyond ``level`` in the DEPARTURE_WINDOW bars
    after the last bar ``j < t`` whose range touched it, in ATR. Reads bars
    ``0..t`` only, even when the window would run past ``t``."""
    if level is None or not atr_value:
        return None
    tol = atr_value * TOUCH_ATR_MULT
    high = df["High"].to_numpy(float)[:t]
    low = df["Low"].to_numpy(float)[:t]
    touched = np.flatnonzero((low <= level + tol) & (high >= level - tol))
    if not touched.size:
        return None
    j = int(touched[-1])
    window = df["Close"].to_numpy(float)[j + 1:min(j + DEPARTURE_WINDOW, t) + 1]
    if not window.size:
        return None
    sign = 1.0 if direction == "bullish" else -1.0
    return _num(float(np.max(sign * (window - level))) / atr_value)


def _zone_lifecycle(df: pd.DataFrame, level, horizon_key: str) -> dict:
    states = classify_levels(df, len(df) - 1, [level], horizon_key=horizon_key) if level is not None else []
    if not states:
        return {"zone_state": None, "zone_touches": None}
    return {"zone_state": states[0].state, "zone_touches": int(states[0].touches)}


def _distance_atr(close: float, level, atr_value: float) -> float | None:
    return None if level is None else _num(abs(close - float(level.price)) / atr_value)


def location_features(df: pd.DataFrame, direction: str, horizon_key: str) -> dict:
    """Every LOCATION_KEYS value at ``df``'s final bar, for the trade's
    direction. < 60 bars or no ATR returns all None; never raises on NaN bars."""
    out = dict.fromkeys(LOCATION_KEYS)
    if df is None or len(df) < MIN_BARS:
        return out
    atr_value = _num(atr(df, 14).iloc[-1])
    if not atr_value:
        return out
    close, t = float(df["Close"].iloc[-1]), len(df) - 1
    entry_side, opposing = side_levels(df, horizon_key, direction)
    out.update(zone_dist_atr=_distance_atr(close, entry_side, atr_value),
               room_atr=_distance_atr(close, opposing, atr_value),
               zone_departure_atr=zone_departure_atr(
                   df, t, None if entry_side is None else float(entry_side.price), direction, atr_value))
    out.update(swing_location(df, direction))
    out.update(_zone_lifecycle(df, entry_side, horizon_key))
    return out
