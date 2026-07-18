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


def adx_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder ADX (EWM alpha=1/period). Shared regime helper for rescue
    gates: high = sustained directional movement, low = range. Scale-free --
    it measures the *ratio* of up- to down-movement, not its size."""
    h, l, c = df["High"], df["Low"], df["Close"]
    up, dn = h.diff(), -l.diff()
    plus_dm = ((up > dn) & (up > 0)) * up
    minus_dm = ((dn > up) & (dn > 0)) * dn
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()],
                   axis=1).max(axis=1)
    atr_w = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_w
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_w
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


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


DEFAULT_PARAMS["EMA Crossover"] = {"rsi_dip": 45, "ext_atr": 1.0,
                                   "entry_mode": "cross", "pullback_max_bars": 10}


def ema_cross_entries(df, horizon_key, params=None):
    p = _params("EMA Crossover", params)
    h = HORIZONS[horizon_key]
    g = compute_shared_gates(df)
    close = df["Close"]
    fast = ema(close, h["ema_fast"])
    slow = ema(close, h["ema_slow"])
    diff = fast - slow
    # 2-bar hold: crossed last bar AND held today (filters one-bar fakeouts)
    held_bull = (diff.shift(2) <= 0) & (diff.shift(1) > 0) & (diff > 0)
    held_bear = (diff.shift(2) >= 0) & (diff.shift(1) < 0) & (diff < 0)

    # --- rescue mode (Task 107): enter on the pullback, not the cross ---
    if p.get("entry_mode") == "pullback":
        window = int(p.get("pullback_max_bars", 10))
        touched_bull = (df["Low"] <= fast) & (df["Close"] > fast)
        touched_bear = (df["High"] >= fast) & (df["Close"] < fast)

        def _first_touch_after(cross_mask, touch_mask):
            out = pd.Series(False, index=df.index)
            for ci in np.where(cross_mask.values)[0]:
                for j in range(ci + 1, min(ci + 1 + window, len(df))):
                    if touch_mask.values[j]:
                        out.iloc[j] = True
                        break                     # first touch only
            return out

        held_bull = _first_touch_after(held_bull, touched_bull).fillna(False)
        held_bear = _first_touch_after(held_bear, touched_bear).fillna(False)

    rsi14 = g["rsi14"]
    rsi_dipped = rsi14.rolling(5).min().shift(1) < p["rsi_dip"]          # real pullback preceded
    rsi_surged = rsi14.rolling(5).max().shift(1) > (100 - p["rsi_dip"])
    m = macd(close)
    mom_bull = (m["macd"] > 0) | (rsi14 > 60)
    mom_bear = (m["macd"] < 0) | (rsi14 < 40)
    slow_rising = slow > slow.shift(5)      # cross inside a falling slow EMA is a trap
    slow_falling = slow < slow.shift(5)
    not_extended = (close - fast).abs() <= g["atr14"] * p["ext_atr"]

    bullish = (held_bull & slow_rising & not_extended & (rsi14 > 50) & rsi_dipped & mom_bull
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (held_bear & slow_falling & not_extended & (rsi14 < 50) & rsi_surged & mom_bear
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["EMA Crossover"] = ema_cross_entries


DEFAULT_PARAMS["VWAP"] = {"ext_pct": 1.5, "hold_bars_2w": 3, "hold_bars_other": 2}


def vwap_entries(df, horizon_key, params=None):
    p = _params("VWAP", params)
    h = HORIZONS[horizon_key]
    g = compute_shared_gates(df)
    close = df["Close"]
    vwap = rolling_vwap(df, h["vwap_window"])
    diff = close - vwap

    hold = p["hold_bars_2w"] if horizon_key == "2w" else p["hold_bars_other"]
    held_bull = (diff.shift(hold) <= 0)
    held_bear = (diff.shift(hold) >= 0)
    for k in range(hold):
        held_bull = held_bull & (diff.shift(k) > 0)
        held_bear = held_bear & (diff.shift(k) < 0)

    vwap_up = vwap > vwap.shift(3)
    vwap_down = vwap < vwap.shift(3)
    ext = (close - vwap).abs() / vwap.replace(0, np.nan) * 100
    not_extended = ext <= p["ext_pct"]       # reclaim near value, don't chase
    rsi14 = g["rsi14"]

    bullish = (held_bull & vwap_up & not_extended & rsi14.between(50, 65)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (held_bear & vwap_down & not_extended & rsi14.between(35, 50)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["VWAP"] = vwap_entries


DEFAULT_PARAMS["MACD"] = {"ext_atr": 1.0}


def macd_entries(df, horizon_key, params=None):
    p = _params("MACD", params)
    g = compute_shared_gates(df)
    close = df["Close"]
    fast_p, slow_p, sig_p = MACD_PERIODS_BY_HORIZON.get(horizon_key, (12, 26, 9))
    m = macd(close, fast=fast_p, slow=slow_p, signal=sig_p)
    macd_line, hist = m["macd"], m["histogram"]
    diff = macd_line - m["signal"]

    crossed_up = (diff.shift(1) <= 0) & (diff > 0)
    crossed_down = (diff.shift(1) >= 0) & (diff < 0)
    hist_held_bull = (hist.shift(2) <= 0) & (hist.shift(1) > 0) & (hist > 0)
    hist_held_bear = (hist.shift(2) >= 0) & (hist.shift(1) < 0) & (hist < 0)
    hist_rising2 = (hist > hist.shift(1)) & (hist.shift(1) > hist.shift(2))   # accelerating
    hist_falling2 = (hist < hist.shift(1)) & (hist.shift(1) < hist.shift(2))
    not_extended = (close - ema(close, fast_p)).abs() <= g["atr14"] * p["ext_atr"]
    rsi14 = g["rsi14"]

    bullish = ((crossed_up | hist_held_bull) & hist_rising2 & (macd_line > 0)
               & (rsi14 > 50) & not_extended
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = ((crossed_down | hist_held_bear) & hist_falling2 & (macd_line < 0)
               & (rsi14 < 50) & not_extended
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["MACD"] = macd_entries


# Ribbon periods per horizon -- shared with signals.py (which had its own copy)
RIBBON_PERIODS_BY_HORIZON = {
    "2w": (10, 20, 50), "4w": (10, 20, 50),
    "2m": (20, 50, 100), "3m": (20, 50, 200),
    "4m": (30, 67, 200), "5m": (40, 83, 200), "6m": (50, 100, 200),
    "7m": (60, 117, 200), "8m": (70, 133, 200), "9m": (80, 150, 200),
}

DEFAULT_PARAMS["MA Ribbon"] = {
    "ext_pct": 8.0,
    "min_width_pctile": None,
    "require_expanding": False,
}


def ma_ribbon_entries(df, horizon_key, params=None):
    p = _params("MA Ribbon", params)
    g = compute_shared_gates(df)
    close = df["Close"]
    fast_p, mid_p, slow_p = RIBBON_PERIODS_BY_HORIZON.get(horizon_key, (10, 20, 50))
    fast = ema(close, fast_p)
    mid = ema(close, mid_p)
    slow_sma = close.rolling(slow_p).mean()
    diff = fast - mid

    crossed_up = (diff.shift(1) <= 0) & (diff > 0) & (fast > slow_sma) & (mid > slow_sma)
    crossed_down = (diff.shift(1) >= 0) & (diff < 0) & (fast < slow_sma) & (mid < slow_sma)
    slow_rising = slow_sma > slow_sma.shift(10)    # alignment without slope = chop trap
    slow_falling = slow_sma < slow_sma.shift(10)
    rsi14 = g["rsi14"]
    not_ext_bull = (close <= slow_sma * (1 + p["ext_pct"] / 100)) & rsi14.between(48, 70)
    not_ext_bear = (close >= slow_sma * (1 - p["ext_pct"] / 100)) & rsi14.between(30, 52)
    m = macd(close)

    bullish = (crossed_up & slow_rising & not_ext_bull & (m["macd"] > 0)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (crossed_down & slow_falling & not_ext_bear & (m["macd"] < 0)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)

    # --- rescue gate (Task 101): only trade an EXPANDING ribbon ---
    min_wp = p.get("min_width_pctile")
    req_exp = p.get("require_expanding")
    if min_wp is not None or req_exp:
        ribbon = pd.concat([fast, mid, slow_sma], axis=1)
        width = (ribbon.max(axis=1) - ribbon.min(axis=1)) / close
        if min_wp is not None:
            wide_enough = (width.rolling(126).rank(pct=True) >= min_wp).fillna(False)
            bullish &= wide_enough
            bearish &= wide_enough
        if req_exp:
            expanding = (width.diff(3) > 0).fillna(False)
            bullish &= expanding
            bearish &= expanding

    return bullish, bearish


ENTRY_FUNCS["MA Ribbon"] = ma_ribbon_entries


DEFAULT_PARAMS["Support/Resistance"] = {"base_atr": 4.0, "close_frac": 0.4, "gap_pct": 3.0}


def support_resistance_entries(df, horizon_key, params=None):
    p = _params("Support/Resistance", params)
    h = HORIZONS[horizon_key]
    g = compute_shared_gates(df)
    close, high, low, open_ = df["Close"], df["High"], df["Low"], df["Open"]
    lookback = h["sr_lookback"]

    resistance = high.rolling(lookback).max().shift(1)
    support = low.rolling(lookback).min().shift(1)
    vol_avg20 = df["Volume"].rolling(20).mean()
    volume_confirmed = (df["Volume"] / vol_avg20) >= SR_VOLUME_MULTIPLE
    crossed_up = (close.shift(1) <= resistance.shift(1)) & (close > resistance)
    crossed_down = (close.shift(1) >= support.shift(1)) & (close < support)

    # Base quality: the 10 bars BEFORE the breakout were a tight range.
    base_range = (high.rolling(10).max() - low.rolling(10).min()).shift(1)
    base_tight = base_range <= g["atr14"] * p["base_atr"]

    # Breakout bar quality: closes near its high (bull) / low (bear).
    bar_rng = (high - low).replace(0, np.nan)
    strong_close_bull = close >= high - p["close_frac"] * bar_rng
    strong_close_bear = close <= low + p["close_frac"] * bar_rng

    # No exhaustion gap: don't buy a bar that OPENED far beyond the level.
    no_gap_bull = open_ <= resistance * (1 + p["gap_pct"] / 100)
    no_gap_bear = open_ >= support * (1 - p["gap_pct"] / 100)

    bullish = (crossed_up & volume_confirmed & base_tight & strong_close_bull & no_gap_bull
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    bearish = (crossed_down & volume_confirmed & base_tight & strong_close_bear & no_gap_bear
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["Support/Resistance"] = support_resistance_entries


BRT_RECENT_BARS = {
    "2w": 10, "4w": 15, "2m": 20, "3m": 25,
    "4m": 27, "5m": 28, "6m": 30, "7m": 32, "8m": 33, "9m": 35,
}
BRT_RETEST_PCT = {
    "2w": 1.0, "4w": 1.5, "2m": 1.5, "3m": 1.0,
    "4m": 1.5, "5m": 1.5, "6m": 1.5, "7m": 1.5, "8m": 1.5, "9m": 1.5,
}

DEFAULT_PARAMS["Break & Retest"] = {"hold_tol_pct": 0.5}


def break_retest_entries(df, horizon_key, params=None):
    p = _params("Break & Retest", params)
    h = HORIZONS[horizon_key]
    g = compute_shared_gates(df)
    close, high, low = df["Close"], df["High"], df["Low"]
    lookback = h["sr_lookback"]

    resistance = high.rolling(lookback).max().shift(lookback)
    support = low.rolling(lookback).min().shift(lookback)
    vol_ratio = df["Volume"] / df["Volume"].rolling(20).mean()
    recent = BRT_RECENT_BARS.get(horizon_key, 10)

    broke_up = (high.rolling(recent).max().shift(1) > resistance) & \
               (vol_ratio.rolling(recent).max().shift(1) >= SR_VOLUME_MULTIPLE)
    broke_dn = (low.rolling(recent).min().shift(1) < support) & \
               (vol_ratio.rolling(recent).max().shift(1) >= SR_VOLUME_MULTIPLE)

    dist_to_res = (close - resistance) / resistance.replace(0, np.nan) * 100
    dist_to_sup = (close - support) / support.replace(0, np.nan) * 100
    retest_pct = BRT_RETEST_PCT.get(horizon_key, 1.0)

    # The retest must HOLD the level and the entry bar must have turned:
    held_level_bull = low >= resistance * (1 - p["hold_tol_pct"] / 100)
    held_level_bear = high <= support * (1 + p["hold_tol_pct"] / 100)
    turned_bull = close > high.shift(1)
    turned_bear = close < low.shift(1)
    rsi14 = g["rsi14"]

    bullish = (broke_up & dist_to_res.between(0, retest_pct) & held_level_bull & turned_bull
               & rsi14.between(42, 63)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    bearish = (broke_dn & dist_to_sup.between(-retest_pct, 0) & held_level_bear & turned_bear
               & rsi14.between(37, 58)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["Break & Retest"] = break_retest_entries


DEFAULT_PARAMS["RSI"] = {"os_level": 35, "ob_level": 65, "confirm": "prev_high",
                         # rescue gate: train-grid winner 2026-07-18
                         # (docs/superpowers/results/2026-07-rescue-rsi-train.md)
                         "max_adx": 20, "require_bb_range": False}


def rsi_entries(df, horizon_key, params=None):
    """Oversold bounce inside a structurally healthy uptrend. Dip-buying by
    construction happens BELOW the short MAs, so this strategy uses the
    slope-only regime gate (200-SMA rising) instead of close>MA gates."""
    p = _params("RSI", params)
    g = compute_shared_gates(df)
    close, high, low = df["Close"], df["High"], df["Low"]
    rsi14 = g["rsi14"]
    os_, ob = p["os_level"], p["ob_level"]

    consec_oversold = (rsi14.shift(1) < os_) & (rsi14.shift(2) < os_)
    consec_overbought = (rsi14.shift(1) > ob) & (rsi14.shift(2) > ob)
    crossed_up = consec_oversold & (rsi14 >= os_)
    crossed_down = consec_overbought & (rsi14 <= ob)

    if p["confirm"] == "prev_high":
        confirm_bull = close > high.shift(1)
        confirm_bear = close < low.shift(1)
    else:  # "prev_close"
        confirm_bull = close > close.shift(1)
        confirm_bear = close < close.shift(1)

    bounce_started = close > close.shift(3)     # not a falling knife
    fade_started = close < close.shift(3)
    ma200 = g["ma200"]
    ma200_down = (ma200 < ma200.shift(120)).fillna(False)

    bullish = (crossed_up & g["bull_regime_slope_only"] & bounce_started & confirm_bull
               & (rsi14 < 40)
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (crossed_down & ma200_down & fade_started & confirm_bear
               & (rsi14 > 60)
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)

    # --- rescue gate (Task 95): only dip-buy/fade in RANGE regimes ---
    # Mean-reversion entries in trending tape are exactly where round 1
    # showed this strategy bleeding; ADX + Bollinger containment restrict
    # it to sideways conditions. None/False = gate off (backward compatible).
    max_adx = p.get("max_adx")
    if max_adx is not None:
        range_regime = (adx_series(df) < max_adx).fillna(False)
        bullish &= range_regime
        bearish &= range_regime
    if p.get("require_bb_range"):
        mid = close.rolling(20).mean()
        sd = close.rolling(20).std()
        in_band = ((close <= mid + 2 * sd) & (close >= mid - 2 * sd)).fillna(False)
        bullish &= in_band
        bearish &= in_band
    return bullish, bearish


ENTRY_FUNCS["RSI"] = rsi_entries


DEFAULT_PARAMS["RSI Divergence"] = {"rsi_reclaim": 45,
                                    # rescue gate (Task 98) -- off until the
                                    # train grid (Task 99) adopts winners
                                    "min_volume_ratio": None,
                                    "min_reclaim_strength": None}


def rsi_divergence_entries(df, horizon_key, params=None):
    """Hidden divergence (trend continuation), rolling formulation, plus a
    confirmation: RSI has actually started turning in the trade direction.
    Divergence alone marks potential -- the reclaim marks the entry."""
    p = _params("RSI Divergence", params)
    g = compute_shared_gates(df)
    close = df["Close"]
    rsi14 = g["rsi14"]
    lb = 20
    reclaim = p["rsi_reclaim"]

    price_hl = close > close.rolling(lb).min().shift(lb)    # higher low
    rsi_ll = rsi14 < rsi14.rolling(lb).min().shift(lb)      # RSI lower low
    price_lh = close < close.rolling(lb).max().shift(lb)
    rsi_hh = rsi14 > rsi14.rolling(lb).max().shift(lb)

    turn_bull = (rsi14 > reclaim) & (rsi14 > rsi14.shift(1))
    turn_bear = (rsi14 < (100 - reclaim)) & (rsi14 < rsi14.shift(1))

    bullish = (price_hl & rsi_ll & turn_bull & rsi14.between(28, 52)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (price_lh & rsi_hh & turn_bear & rsi14.between(48, 72)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)

    # --- rescue gate (Task 98): confirmation quality on the reclaim bar ---
    # This detector is a rolling formulation (no discrete swing points), so
    # reclaim strength is measured from the recent lb-bar swing extreme
    # toward the lb-bar range midpoint (deviation from the plan's discrete
    # swing-mid formula, which is vacuous against rolling extremes).
    # None = gate off (backward compatible).
    min_vr = p.get("min_volume_ratio")
    min_rs = p.get("min_reclaim_strength")
    if min_vr is not None:
        vol_ratio = df["Volume"] / df["Volume"].rolling(20).mean()
        vr_ok = (vol_ratio >= min_vr).fillna(False)
        bullish &= vr_ok
        bearish &= vr_ok
    if min_rs is not None:
        lo = close.rolling(lb).min()
        hi = close.rolling(lb).max()
        mid = (lo + hi) / 2
        reclaim_floor = lo + min_rs * (mid - lo)
        reclaim_ceil = hi - min_rs * (hi - mid)
        bullish &= (close >= reclaim_floor).fillna(False)
        bearish &= (close <= reclaim_ceil).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["RSI Divergence"] = rsi_divergence_entries


def _vectorized_hvn(df, lookback, n_bins=20):
    """Per-bar High Volume Node price AND its share of window volume (%).
    Same numpy approach as the old backtest.py loop, extended to keep the
    winning bucket's volume share so node significance can gate entries."""
    _high, _low = df["High"].values, df["Low"].values
    _vol = df["Volume"].values
    _mid = (_high + _low) / 2
    n = len(df)
    hvn = np.full(n, np.nan)
    share = np.full(n, np.nan)
    for i in range(lookback, n):
        lo_idx = i - lookback
        pmin = _low[lo_idx:i].min()
        pmax = _high[lo_idx:i].max()
        rng = pmax - pmin
        if rng <= 0:
            continue
        idx = np.minimum(((_mid[lo_idx:i] - pmin) / rng * n_bins).astype(int), n_bins - 1)
        bins = np.bincount(idx, weights=_vol[lo_idx:i], minlength=n_bins)
        total = bins.sum()
        if total <= 0:
            continue
        k = bins.argmax()
        hvn[i] = pmin + (k + 0.5) * rng / n_bins
        share[i] = bins[k] / total * 100
    return pd.Series(hvn, index=df.index), pd.Series(share, index=df.index)


DEFAULT_PARAMS["Volume Profile"] = {"node_share": 8.0, "prox_pct": 1.5}


def volume_profile_entries(df, horizon_key, params=None):
    p = _params("Volume Profile", params)
    h = HORIZONS[horizon_key]
    g = compute_shared_gates(df)
    close = df["Close"]

    hvn, share = _vectorized_hvn(df, h["sr_lookback"])
    dist_pct = (close - hvn) / hvn.replace(0, np.nan) * 100
    significant = share >= p["node_share"]      # marginal argmax nodes are noise
    rsi14 = g["rsi14"]
    bounce_bull = close > close.shift(1)
    bounce_bear = close < close.shift(1)

    bullish = (dist_pct.between(0, p["prox_pct"]) & significant & bounce_bull
               & rsi14.between(44, 64)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (dist_pct.between(-p["prox_pct"], 0) & significant & bounce_bear
               & rsi14.between(36, 56)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["Volume Profile"] = volume_profile_entries


DEFAULT_PARAMS["Elliott Wave"] = {
    "depth_min": 0.30, "depth_max": 0.80,
    # Rescue gate (Task 104/105): strict wave-2 validation. TRAIN grid
    # (docs/superpowers/results/2026-07-rescue-elliott-train.md) selected
    # this config -- N=117, WR=83.8%, ExpR=+0.094 on TRAIN, the pre-
    # registered max-expectancy winner among qualifying configs. Adopted
    # here permanently; Task 106 spends the single VALIDATION-window look
    # against this exact config, no retuning after.
    "w2_min_retrace": 0.382, "w2_max_retrace": 0.618, "w2_max_duration_ratio": 0.75,
}


def elliott_wave_entries(df, horizon_key, params=None):
    """Wave-3 breakout approximation. Only the 4w horizon fires: 2w pivots
    are noise, >=2m pivot approximation degrades (documented in the old
    backtest). Adds the textbook wave-2 depth check (30-80% of wave 1)."""
    p = _params("Elliott Wave", params)
    if horizon_key != "4w":
        return _off(df), _off(df)
    g = compute_shared_gates(df)
    threshold_pct = HORIZONS[horizon_key]["max_risk_pct"]
    bull_raw, bear_raw, levels = elliott_wave3_entries(df, threshold_pct)

    # --- rescue gate (Task 104): strict wave-2 validation ---
    # `levels` is shared by both the bullish (kind0=="low") and bearish
    # (kind0=="high") wave triples, keyed by the breakout bar index -- a
    # given bar belongs to at most one side, so clearing both raw series at
    # a rejected bar is safe (the other side is already False there).
    w2_min = p.get("w2_min_retrace")
    w2_max = p.get("w2_max_retrace")
    dur_ratio = p.get("w2_max_duration_ratio")
    if any(v is not None for v in (w2_min, w2_max, dur_ratio)):
        for j, lv in list(levels.items()):
            wave1_len = lv["wave1"] - lv["wave0"]
            if wave1_len == 0:
                bad = True
            else:
                # Signed ratio: numerator and denominator both flip sign
                # together on the bearish (high/low/high) side, so this
                # yields the same magnitude as the unsigned bullish case
                # without needing an abs().
                retrace = (lv["wave1"] - lv["wave2"]) / wave1_len
                # Classic wave-2-overlaps-wave-1-origin invalidation, valid
                # for either side: wave2 must stay on the same side of
                # wave0 as wave1 is.
                overlap = (lv["wave2"] - lv["wave0"]) * wave1_len <= 0
                bad = ((w2_min is not None and retrace < w2_min)
                       or (w2_max is not None and retrace > w2_max)
                       or (dur_ratio is not None and
                           (lv["wave2_idx"] - lv["wave1_idx"])
                           > dur_ratio * (lv["wave1_idx"] - lv["wave0_idx"]))
                       or overlap)
            if bad:
                bull_raw.iloc[j] = False
                bear_raw.iloc[j] = False
                levels.pop(j)

    depth_ok = _off(df)
    for j, lv in levels.items():
        impulse = abs(lv["wave1"] - lv["wave0"])
        if impulse <= 0:
            continue
        depth = abs(lv["wave1"] - lv["wave2"]) / impulse
        depth_ok.iloc[j] = p["depth_min"] <= depth <= p["depth_max"]

    rsi14 = g["rsi14"]
    rsi_rising = rsi14 > rsi14.shift(2)
    rsi_falling = rsi14 < rsi14.shift(2)

    bullish = (bull_raw & depth_ok & (rsi14 > 55) & rsi_rising
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (bear_raw & depth_ok & (rsi14 < 45) & rsi_falling
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["Elliott Wave"] = elliott_wave_entries
