"""
SINGLE SOURCE of entry logic for every strategy -- consumed by BOTH the
backtest (backtest._vectorized_entries) and the live scanner (signals.py).
Change a filter here and both worlds change together; that is the point.

Every function returns (bullish_entries, bearish_entries): boolean Series
aligned to df.index, True on bars where a fresh entry fires.

NO-LOOKAHEAD RULE: conditions may reference only the current bar and
earlier (`shift(+n)`, trailing `rolling`). Never `shift(-n)`, never
centered windows. Every boolean Series is `.fillna(False)` -- a gate that
cannot be computed yet (short history) BLOCKS entries, it never passes.

Tunables live in DEFAULT_PARAMS (per strategy); scripts/tune_strategy.py
sweeps them on the train window only. STRATEGY_GATES (strategy_types.py)
lets tuning disable a direction or horizons per strategy.
"""
import numpy as np
import pandas as pd

from .indicators import atr, ema, macd, rolling_vwap, rsi, elliott_wave3_entries
from .strategy_types import (
    FIB_TOLERANCE_PCT, HORIZONS, MACD_PERIODS_BY_HORIZON, SR_VOLUME_MULTIPLE,
    STRATEGY_GATES,
)

ATR_FLOOR_PCT = 0.007   # skip dead-flat tape: ATR must be >= 0.7% of price
ATR_CALM_MULT = 1.4     # skip panic tape: ATR must be <= 1.4x its 60-bar mean
VOL_OK_MULT   = 0.9     # entry bar volume >= 0.9x its 20-bar mean

# Per-strategy tunables. Tasks 6-12 add one entry each; tune_strategy.py
# mutates these in-place per grid point (and restores afterwards).
DEFAULT_PARAMS: dict[str, dict] = {}

# Registry: strategy name -> entry function. Tasks 6-12 populate it.
ENTRY_FUNCS: dict[str, "callable"] = {}


def compute_shared_gates(df: pd.DataFrame) -> dict:
    """Gates applied to (almost) every strategy -- see spec section 5.
    RSI exception: dip-buying uses `bull_regime_slope_only` and skips trend50."""
    close = df["Close"]
    atr14 = atr(df, 14)
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    vol_avg20 = df["Volume"].rolling(20).mean()
    return {
        "bull_regime": ((close > ma200) & (ma200 > ma200.shift(20))).fillna(False),
        "bull_regime_slope_only": (ma200 > ma200.shift(120)).fillna(False),
        "bear_regime": ((ma200 < ma200.shift(120)) & (close < ma200)).fillna(False),
        "trend50_bull": (close > ma50).fillna(False),
        "trend50_bear": (close < ma50).fillna(False),
        "atr_floor": ((atr14 / close.replace(0, np.nan)) >= ATR_FLOOR_PCT).fillna(False),
        "atr_calm": (atr14 <= atr14.rolling(60).mean() * ATR_CALM_MULT).fillna(False),
        "vol_ok": (df["Volume"] >= vol_avg20 * VOL_OK_MULT).fillna(False),
        "rsi14": rsi(close, 14),
        "atr14": atr14,
        "ma50": ma50,
        "ma200": ma200,
    }


def _rolling_argmax_pos(s: pd.Series, lookback: int) -> pd.Series:
    """Position (0..lookback-1) of the max within each trailing window ending
    at the bar (inclusive). NaN until `lookback` bars exist. Higher position
    = the extreme happened more recently."""
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    if len(v) >= lookback:
        w = np.lib.stride_tricks.sliding_window_view(v, lookback)
        out[lookback - 1:] = w.argmax(axis=1)
    return pd.Series(out, index=s.index)


def _rolling_argmin_pos(s: pd.Series, lookback: int) -> pd.Series:
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    if len(v) >= lookback:
        w = np.lib.stride_tricks.sliding_window_view(v, lookback)
        out[lookback - 1:] = w.argmin(axis=1)
    return pd.Series(out, index=s.index)


def _params(strategy: str, params: dict | None) -> dict:
    merged = dict(DEFAULT_PARAMS.get(strategy, {}))
    if params:
        merged.update(params)
    return merged


def _off(df: pd.DataFrame) -> pd.Series:
    return pd.Series(False, index=df.index)


def entries_for(strategy: str, df: pd.DataFrame, horizon_key: str,
                params: dict | None = None) -> tuple[pd.Series, pd.Series]:
    """Dispatch to the strategy's entry function, then apply STRATEGY_GATES
    (direction/horizon restrictions decided by train-window tuning)."""
    bullish, bearish = ENTRY_FUNCS[strategy](df, horizon_key, params)

    gates = STRATEGY_GATES.get(strategy)
    if gates:
        horizons = gates.get("horizons")
        if horizons is not None and horizon_key not in horizons:
            return _off(df), _off(df)
        directions = gates.get("directions")
        if directions is not None:
            if "bullish" not in directions:
                bullish = _off(df)
            if "bearish" not in directions:
                bearish = _off(df)
    return bullish, bearish


DEFAULT_PARAMS["Fibonacci"] = {
    "ratios": (0.382, 0.5, 0.618),   # 23.6% too shallow, 78.6% = failed impulse
    "rsi_bull": (35, 58),
    "rsi_bear": (42, 65),
}


def fibonacci_entries(df, horizon_key, params=None):
    """Retracement bounce WITH swing-direction awareness: a bullish bounce is
    only valid when the up-impulse is the recent structure (swing low set
    BEFORE swing high). The old rolling-max/min version fired 'bullish' on
    retracements of downtrends, where the fib level is overhead resistance."""
    p = _params("Fibonacci", params)
    h = HORIZONS[horizon_key]
    lookback = h["fib_lookback"]
    g = compute_shared_gates(df)
    close, high, low = df["Close"], df["High"], df["Low"]

    swing_high = high.rolling(lookback).max()
    swing_low = low.rolling(lookback).min()
    rng = swing_high - swing_low

    # Swing direction: where in the window did the extremes happen?
    hi_pos = _rolling_argmax_pos(high, lookback)
    lo_pos = _rolling_argmin_pos(low, lookback)
    up_impulse = (hi_pos > lo_pos)       # low first, then high -> uptrend pullback
    down_impulse = (lo_pos > hi_pos)

    levels = pd.DataFrame({r: swing_high - r * rng for r in p["ratios"]})
    nearest_distance = levels.sub(close, axis=0).abs().min(axis=1)
    distance_pct = (nearest_distance / rng * 100).replace([np.inf, -np.inf], np.nan)
    is_testing = (distance_pct <= FIB_TOLERANCE_PCT) & rng.gt(0)

    pulled_back_bull = close.shift(5) > close.shift(1)
    bouncing_bull = close > close.shift(1)
    pulled_back_bear = close.shift(5) < close.shift(1)
    bouncing_bear = close < close.shift(1)
    upper_half = close >= (high + low) / 2   # bounce bar closes strong
    lower_half = close <= (high + low) / 2

    rsi14 = g["rsi14"]
    bullish = (is_testing & up_impulse & pulled_back_bull & bouncing_bull & upper_half
               & g["bull_regime"] & g["trend50_bull"]
               & rsi14.between(*p["rsi_bull"])
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (is_testing & down_impulse & pulled_back_bear & bouncing_bear & lower_half
               & g["bear_regime"] & g["trend50_bear"]
               & rsi14.between(*p["rsi_bear"])
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["Fibonacci"] = fibonacci_entries
