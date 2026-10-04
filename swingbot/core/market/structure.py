"""Causal swing structure and volume-in-context features (v121).

The pivot contract: bar ``i`` is a swing high when ``High[i]`` is strictly
greater than the ``k`` highs before it and >= the ``k`` highs after it
(mirror for lows). A pivot at ``i`` is knowable only from bar ``i + k``; at
decision bar ``t`` only pivots with ``i <= t - k`` exist. Every consumer
(v121 snapshot, v122 gate, v123 exit) calls ``confirmed_pivots`` -- this is
the single place the confirmation lag lives. ``k`` is frozen at 3.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from swingbot.core.market.indicators import atr

PIVOT_K = 3   # frozen; not a search knob
PIVOT_COLUMNS = ("last_sh_pos", "last_sh", "prior_sh_pos", "prior_sh",
                 "last_sl_pos", "last_sl", "prior_sl_pos", "prior_sl")


def _num(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return round(value, 6) if math.isfinite(value) else None


def pivot_confirmations(df: pd.DataFrame, k: int = PIVOT_K) -> tuple[np.ndarray, np.ndarray]:
    """Boolean arrays indexed by CONFIRMATION bar ``j``: True when bar ``j - k``
    is a swing high / swing low. Row ``j`` reads only bars ``j - 2k .. j``."""
    high, low = df["High"], df["Low"]
    pivot_high, pivot_low = high.shift(k), low.shift(k)
    sh = (pivot_high > high.shift(k + 1).rolling(k).max()) & (pivot_high >= high.rolling(k).max())
    sl = (pivot_low < low.shift(k + 1).rolling(k).min()) & (pivot_low <= low.rolling(k).min())
    return sh.fillna(False).to_numpy(bool), sl.fillna(False).to_numpy(bool)


def _last_two(flags: np.ndarray, prices: np.ndarray, k: int) -> tuple[np.ndarray, ...]:
    """Per bar: (last_pos, last_price, prior_pos, prior_price) of confirmed pivots."""
    n = len(flags)
    events = np.flatnonzero(flags) - k
    count = np.cumsum(flags)
    out = [np.full(n, np.nan) for _ in range(4)]
    for slot, back in ((0, 1), (2, 2)):
        has = count >= back
        pos = events[count[has] - back]
        out[slot][has] = pos
        out[slot + 1][has] = prices[pos]
    return tuple(out)


def confirmed_pivots(df: pd.DataFrame, k: int = PIVOT_K) -> pd.DataFrame:
    """Per bar ``t``: positional index and price of the last two confirmed swing
    highs and lows known at ``t`` (NaN where fewer exist). Truncation-stable:
    row ``t`` equals the last row of ``confirmed_pivots(df.iloc[:t + 1])``."""
    sh, sl = pivot_confirmations(df, k)
    highs = _last_two(sh, df["High"].to_numpy(float), k)
    lows = _last_two(sl, df["Low"].to_numpy(float), k)
    return pd.DataFrame(dict(zip(PIVOT_COLUMNS, highs + lows)), index=df.index)


MIN_BARS = 60               # below this every feature is None
ABSORPTION_VOL_MULT = 1.5   # frozen descriptive definition
ABSORPTION_RANGE_ATR = 0.6  # frozen descriptive definition
SHORT_WINDOW, LONG_WINDOW = 10, 50
PROGRESS_LOOKBACK = 10
MIN_LEG_THIRD = 2           # impulse_range_decay needs >= 2 bars per third (a leg of >= 6 bars)
LEG_SHAPE_KEYS = ("pullback_depth_frac", "pullback_bars_ratio", "impulse_atr_per_bar", "impulse_range_decay")
STRUCTURE_KEYS = ("structure_state", "structure_aligned", "last_pivot_held", "hh_failed",
                  "swing_high_atr", "swing_low_atr", "vol_trend_10_50", "range_trend_10_50",
                  "progress_atr_10", "absorption_bar", "absorption_count_10", "pullback_vol_ratio",
                  *LEG_SHAPE_KEYS)


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    return pd.concat([df["High"] - df["Low"], (df["High"] - prev_close).abs(),
                      (df["Low"] - prev_close).abs()], axis=1).max(axis=1)


def absorption_series(df: pd.DataFrame, atr_series: pd.Series) -> pd.Series:
    """True where Volume / mean20(prior bars) >= 1.5 and (High-Low)/ATR14 <= 0.6."""
    prior = df["Volume"].rolling(20).mean().shift(1)
    heavy = df["Volume"] / prior.where(prior > 0) >= ABSORPTION_VOL_MULT
    narrow = (df["High"] - df["Low"]) / atr_series.where(atr_series > 0) <= ABSORPTION_RANGE_ATR
    return (heavy & narrow).fillna(False)


def _last_pivot_before(flags: np.ndarray, before: int, k: int) -> int | None:
    positions = np.flatnonzero(flags) - k
    earlier = positions[positions < before]
    return int(earlier[-1]) if len(earlier) else None


def pullback_legs(df: pd.DataFrame, direction: str, k: int = PIVOT_K) -> tuple[int, int, int] | None:
    """Positional ``(base, turn, t)`` of the impulse/pullback legs at the final bar.

    Bullish: turn = SH, the last confirmed swing high; base = SL0, the last
    swing low before SH; impulse = base..turn, pullback = turn+1..t. None when
    either pivot is missing or Close[t] > High[SH] (not a pullback). Bearish
    mirrors with lows. Bars turn+1..turn+3 are ordinary, knowable bars: only
    the pivot label is lagged."""
    sh, sl = pivot_confirmations(df, k)
    bullish = direction == "bullish"
    turn_flags, base_flags = (sh, sl) if bullish else (sl, sh)
    t = len(df) - 1
    turn = _last_pivot_before(turn_flags, t + 1, k)
    if turn is None:
        return None
    base = _last_pivot_before(base_flags, turn, k)
    if base is None:
        return None
    close = float(df["Close"].iloc[t])
    beyond = close > float(df["High"].iloc[turn]) if bullish else close < float(df["Low"].iloc[turn])
    return None if beyond else (base, turn, t)


def _leg_ratio(volume: np.ndarray, start: int, pivot: int, t: int) -> float | None:
    impulse, pullback = volume[start:pivot + 1], volume[pivot + 1:t + 1]
    if len(impulse) < 2 or len(pullback) < 2:
        return None
    impulse_mean, pullback_mean = float(np.mean(impulse)), float(np.mean(pullback))
    if not (impulse_mean > 0 and pullback_mean > 0):
        return None
    return _num(pullback_mean / impulse_mean)


def pullback_vol_ratio(df: pd.DataFrame, direction: str, k: int = PIVOT_K) -> float | None:
    """Mean pullback-leg volume / mean impulse-leg volume at the final bar
    (legs per ``pullback_legs``)."""
    legs = pullback_legs(df, direction, k)
    return None if legs is None else _leg_ratio(df["Volume"].to_numpy(float), *legs)


def _impulse_height(high: np.ndarray, low: np.ndarray, base: int, turn: int, bullish: bool) -> float:
    return float(high[turn] - low[base]) if bullish else float(high[base] - low[turn])


def _pullback_give(high: np.ndarray, low: np.ndarray, turn: int, t: int, bullish: bool) -> float:
    """How far the pullback leg's extreme has retraced from the turn pivot."""
    if bullish:
        return float(high[turn] - np.min(low[turn + 1:t + 1]))
    return float(np.max(high[turn + 1:t + 1]) - low[turn])


def _range_decay(tr: np.ndarray, base: int, turn: int) -> float | None:
    """Mean true range of the impulse leg's last third / its first third."""
    leg = tr[base:turn + 1]
    third = len(leg) // 3
    if third < MIN_LEG_THIRD:
        return None
    first = float(np.mean(leg[:third]))
    return _num(float(np.mean(leg[-third:])) / first) if first > 0 else None


def leg_shape_features(df: pd.DataFrame, direction: str, atr_value: float | None) -> dict:
    """Pullback depth/duration and impulse speed/decay on the ``pullback_legs``
    legs. All None when the legs are undefined or the impulse has no height."""
    out = dict.fromkeys(LEG_SHAPE_KEYS)
    legs = pullback_legs(df, direction)
    if legs is None:
        return out
    base, turn, t = legs
    bullish = direction == "bullish"
    high, low = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    height = _impulse_height(high, low, base, turn, bullish)
    if not height > 0:
        return out
    impulse_bars = turn - base
    out.update(pullback_depth_frac=_num(_pullback_give(high, low, turn, t, bullish) / height),
               pullback_bars_ratio=_num((t - turn) / impulse_bars),
               impulse_atr_per_bar=_num(height / impulse_bars / atr_value) if atr_value else None,
               impulse_range_decay=_range_decay(true_range(df).to_numpy(float), base, turn))
    return out


def _state(piv) -> str | None:
    if any(pd.isna(piv[c]) for c in ("last_sh", "prior_sh", "last_sl", "prior_sl")):
        return None
    if piv["last_sh"] > piv["prior_sh"] and piv["last_sl"] > piv["prior_sl"]:
        return "up"
    if piv["last_sh"] < piv["prior_sh"] and piv["last_sl"] < piv["prior_sl"]:
        return "down"
    return "mixed"


def _structure_keys(piv, close: float, direction: str) -> dict:
    bullish = direction == "bullish"
    state = _state(piv)
    pivot, side = (piv["last_sl"], 1) if bullish else (piv["last_sh"], -1)
    last, prior = (piv["last_sh"], piv["prior_sh"]) if bullish else (piv["last_sl"], piv["prior_sl"])
    return {
        "structure_state": state,
        "structure_aligned": None if state is None else state == ("up" if bullish else "down"),
        "last_pivot_held": None if pd.isna(pivot) else bool(side * (close - pivot) > 0),
        "hh_failed": None if pd.isna(last) or pd.isna(prior) else bool(side * (last - prior) <= 0),
    }


def _ratio_of_means(series: pd.Series) -> float | None:
    long_mean = series.iloc[-LONG_WINDOW:].mean()
    return _num(series.iloc[-SHORT_WINDOW:].mean() / long_mean) if long_mean else None


def _atr_keys(df: pd.DataFrame, piv, atr_value: float | None, direction: str) -> dict:
    if not atr_value:
        return {"swing_high_atr": None, "swing_low_atr": None, "progress_atr_10": None}
    close = float(df["Close"].iloc[-1])
    sign = 1 if direction == "bullish" else -1
    move = close - float(df["Close"].iloc[-1 - PROGRESS_LOOKBACK])
    return {"swing_high_atr": _num((piv["last_sh"] - close) / atr_value),
            "swing_low_atr": _num((close - piv["last_sl"]) / atr_value),
            "progress_atr_10": _num(sign * move / atr_value)}


def structure_features(df: pd.DataFrame, direction: str) -> dict:
    """Every STRUCTURE_KEYS value at ``df``'s final bar, expressed for the
    trade's direction. Reads only ``df``; < 60 bars returns all None."""
    out = {key: None for key in STRUCTURE_KEYS}
    if df is None or len(df) < MIN_BARS:
        return out
    piv = confirmed_pivots(df).iloc[-1]
    atr_series = atr(df, 14)
    atr_value = _num(atr_series.iloc[-1])
    absorption = absorption_series(df, atr_series)
    out.update(_structure_keys(piv, float(df["Close"].iloc[-1]), direction))
    out.update(_atr_keys(df, piv, atr_value, direction))
    out.update(vol_trend_10_50=_ratio_of_means(df["Volume"].astype(float)),
               range_trend_10_50=_ratio_of_means(true_range(df)),
               absorption_bar=bool(absorption.iloc[-1]),
               absorption_count_10=int(absorption.iloc[-SHORT_WINDOW:].sum()),
               pullback_vol_ratio=pullback_vol_ratio(df, direction))
    out.update(leg_shape_features(df, direction, atr_value))
    return out
