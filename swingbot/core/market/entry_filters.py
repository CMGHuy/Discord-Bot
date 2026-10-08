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

Tunables live in DEFAULT_PARAMS (per strategy); scripts/backtest/tune_strategy.py
sweeps them on the train window only. STRATEGY_GATES (strategy_types.py)
lets tuning disable a direction or horizons per strategy.
"""
import contextlib
import numpy as np
import pandas as pd

from swingbot.core.market.indicators import atr, ema, macd, rolling_vwap, rsi, elliott_wave3_entries
from swingbot.core.market.strategy_types import (
    FIB_TOLERANCE_PCT, HORIZONS, MACD_PERIODS_BY_HORIZON, SR_VOLUME_MULTIPLE,
    STRATEGY_GATES, admits,
)
from swingbot.core.risk_limits import capped_planned_loss_pct

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


def apply_regime_gate(bull: pd.Series, bear: pd.Series, strategy: str,
                      regimes: "pd.Series | None"):
    """Zero out entries on bars whose market regime the strategy isn't
    allowed to trade. Flag-gated + empty-by-default: shipping the
    mechanism costs nothing until E33's evidence fills REGIME_ALLOW."""
    from swingbot import config
    from swingbot.core.market.strategy_types import REGIME_ALLOW
    allowed = REGIME_ALLOW.get(strategy)
    if not getattr(config, "REGIME_GATES_ENABLED", False) or not allowed or regimes is None:
        return bull, bear
    ok = regimes.reindex(bull.index).isin(allowed).fillna(False)
    return (bull & ok), (bear & ok)


def entries_for(strategy: str, df: pd.DataFrame, horizon_key: str,
                params: dict | None = None,
                regimes: "pd.Series | None" = None) -> tuple[pd.Series, pd.Series]:
    """Dispatch to the strategy's entry function, then apply the mask (strategy_types.admits: STRATEGY_GATES' direction/horizon axes plus v113 "cells").

    `regimes` stays an explicit parameter for callers that already hold a
    series, but it no longer has to be passed: when it is None the regime is
    read off `df`'s context block instead (market_context.attach). That is what
    finally feeds apply_regime_gate, which has been inert since E24 for want of
    a market dataframe in this call chain -- all 12 call sites keep working
    unchanged."""
    bullish, bearish = ENTRY_FUNCS[strategy](df, horizon_key, params)

    if regimes is None:
        # Fail-closed by design: with REGIME_GATES_ENABLED on and no context
        # block on df, this raises rather than silently skipping the gate.
        from swingbot.core.market import market_context
        regimes = market_context.get(df, "ctx_regime")

    # v113 §2: strategy_types.admits is the mask rule (legacy axes + "cells").
    if not admits(strategy, "bullish", horizon_key):
        bullish = _off(df)
    if not admits(strategy, "bearish", horizon_key):
        bearish = _off(df)

    bullish, bearish = apply_regime_gate(bullish, bearish, strategy, regimes)
    return bullish, bearish


@contextlib.contextmanager
def gate_override(strategy: str, gates: dict | None):
    missing = object()
    previous = STRATEGY_GATES.get(strategy, missing)
    try:
        if gates is None:
            STRATEGY_GATES.pop(strategy, None)
        else:
            STRATEGY_GATES[strategy] = gates
        yield
    finally:
        if previous is missing:
            STRATEGY_GATES.pop(strategy, None)
        else:
            STRATEGY_GATES[strategy] = previous


DEFAULT_PARAMS["Fibonacci"] = {
    "ratios": (0.382, 0.5, 0.618),   # 23.6% too shallow, 78.6% = failed impulse
    "rsi_bull": (35, 58),
    "rsi_bear": (42, 65),
}


def _fib_sr_confluence(df, h, levels, close, atr14):
    """v102: True where the tested Fibonacci retracement level (the ratio
    level nearest the close -- the one is_testing found) sits within
    FIB_SR_CONFLUENCE_ATR x ATR14 of the bar's Rolling support or resistance.
    Rolling S/R is levels.py's own definition (rolling sr_lookback extreme,
    shift(1)), the one level family v49 measured as nearly independent of
    Fibonacci. Never compared against the swing extremes: a shorter-window
    rolling low often IS the Fibonacci swing low, which would be trivially
    true. Flag 0 (or absent) -> all True, so entries are bit-identical to
    pre-v102. Reads bars <= i only."""
    from swingbot import config
    tol = float(getattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0) or 0.0)
    if tol <= 0:
        return pd.Series(True, index=df.index)
    arr = levels.to_numpy(dtype=float)
    dist = np.abs(arr - close.to_numpy(dtype=float)[:, None])
    dist = np.where(np.isnan(dist), np.inf, dist)
    tested = arr[np.arange(len(arr)), dist.argmin(axis=1)]
    lookback = h["sr_lookback"]
    support = df["Low"].rolling(lookback).min().shift(1).to_numpy(dtype=float)
    resistance = df["High"].rolling(lookback).max().shift(1).to_numpy(dtype=float)
    gap = np.fmin(np.abs(tested - support), np.abs(tested - resistance))
    with np.errstate(invalid="ignore"):
        keep = gap <= tol * atr14.to_numpy(dtype=float)
    return pd.Series(keep, index=df.index)


_LEVEL_STOP_DIRECTIONS = ("bullish", "bearish")


def _fib_level_stop_config():
    """Return the v103 level-stop ATR buffer and enabled directions.

    Configuration is read at call time so SIGHUP reloads take effect. Parsing
    forgives case and spaces; unknown direction names are ignored.
    """
    from swingbot import config

    buffer_atr = float(getattr(config, "FIB_LEVEL_STOP_ATR", 0.0) or 0.0)
    raw_directions = str(getattr(config, "FIB_LEVEL_STOP_DIRECTIONS", "") or "")
    directions = frozenset(value.strip().lower() for value in raw_directions.split(","))
    return buffer_atr, directions & frozenset(_LEVEL_STOP_DIRECTIONS)


def fib_level_stop_series(df, horizon_key, direction, buffer_atr, params=None):
    """Return each bar's eligible Fibonacci level stop, otherwise NaN.

    The tested ratio level and ATR use only the current bar and its trailing
    lookback. Stops that are non-losing or exceed the hard planned-loss cap
    are dropped, never moved to the cap.
    """
    params = _params("Fibonacci", params)
    horizon = HORIZONS[horizon_key]
    lookback = horizon["fib_lookback"]
    swing_high = df["High"].rolling(lookback).max()
    swing_low = df["Low"].rolling(lookback).min()
    price_range = swing_high - swing_low
    levels = np.column_stack([
        (swing_high - ratio * price_range).to_numpy(dtype=float)
        for ratio in params["ratios"]
    ])
    close = df["Close"].to_numpy(dtype=float)
    distances = np.abs(levels - close[:, None])
    distances = np.where(np.isnan(distances), np.inf, distances)
    tested_level = levels[np.arange(len(close)), distances.argmin(axis=1)]
    atr14 = atr(df, 14).to_numpy(dtype=float)
    is_bullish = direction == "bullish"
    stop = tested_level - buffer_atr * atr14 if is_bullish else tested_level + buffer_atr * atr14
    with np.errstate(invalid="ignore", divide="ignore"):
        losing_side = stop < close if is_bullish else stop > close
        loss_pct = np.abs(close - stop) / close * 100
        within_cap = loss_pct <= capped_planned_loss_pct(horizon["max_risk_pct"]) + 1e-9
    return pd.Series(np.where(losing_side & within_cap, stop, np.nan), index=df.index)


def fib_level_stop_at(df, index, horizon_key, direction, params=None):
    """Read the enabled level stop at one bar; None means the mode is off."""
    buffer_atr, directions = _fib_level_stop_config()
    if buffer_atr <= 0 or direction not in directions:
        return None
    if index < 0:
        index += len(df)
    frame_at_bar = df.iloc[:index + 1]
    stop = fib_level_stop_series(
        frame_at_bar, horizon_key, direction, buffer_atr, params=params,
    ).iloc[-1]
    return float(stop)


def _apply_fib_level_stop(df, horizon_key, params, bullish, bearish):
    """Drop in-scope Fibonacci signals whose level stop is ineligible."""
    buffer_atr, directions = _fib_level_stop_config()
    if buffer_atr <= 0:
        return bullish, bearish
    if "bullish" in directions:
        bullish = bullish & fib_level_stop_series(
            df, horizon_key, "bullish", buffer_atr, params=params,
        ).notna()
    if "bearish" in directions:
        bearish = bearish & fib_level_stop_series(
            df, horizon_key, "bearish", buffer_atr, params=params,
        ).notna()
    return bullish, bearish


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
    confluence = _fib_sr_confluence(df, h, levels, close, g["atr14"])
    bullish, bearish = bullish & confluence, bearish & confluence
    bullish, bearish = _apply_fib_level_stop(df, horizon_key, p, bullish, bearish)
    return bullish, bearish


ENTRY_FUNCS["Fibonacci"] = fibonacci_entries


# --- v103 C: Fibonacci Continuation ----------------------------------------

DEFAULT_PARAMS["Fibonacci Continuation"] = {
    "d_min": 0.382,
    "d_max": 0.618,
    "min_pullback_bars": 2,
}
# Kept as a market-layer literal so market never imports planning. The test
# pins it to planning.params.STRUCTURE_BUFFER_ATR.
FIB_CONTINUATION_STOP_ATR = 0.25


def _extreme_after(values, lookback, positions, reducer):
    """Return each rolling window's extreme strictly after its indexed bar."""
    values = np.asarray(values, dtype=float)
    result = np.full(len(values), np.nan)
    if len(values) < lookback:
        return result
    windows = np.lib.stride_tricks.sliding_window_view(values, lookback)
    suffix = reducer.accumulate(windows[:, ::-1], axis=1)[:, ::-1]
    positions = np.asarray(positions, dtype=float)[lookback - 1:]
    rows = np.nonzero(np.isfinite(positions) & (positions < lookback - 1))[0]
    result[lookback - 1 + rows] = suffix[rows, positions[rows].astype(int) + 1]
    return result


def _continuation_sides(prior_high, prior_low, lookback, direction):
    """Return structural continuation arrays for one direction."""
    high_position = _rolling_argmax_pos(prior_high, lookback).to_numpy()
    low_position = _rolling_argmin_pos(prior_low, lookback).to_numpy()
    swing_high = prior_high.rolling(lookback).max().to_numpy(dtype=float)
    swing_low = prior_low.rolling(lookback).min().to_numpy(dtype=float)
    if direction == "bullish":
        retrace = _extreme_after(prior_low.to_numpy(), lookback, high_position, np.minimum)
        return swing_high, swing_low, high_position, low_position, retrace, 1.0
    retrace = _extreme_after(prior_high.to_numpy(), lookback, low_position, np.maximum)
    return swing_low, swing_high, low_position, high_position, retrace, -1.0


def fib_continuation_frame(df, horizon_key, direction, params=None):
    """Compute v103 continuation structure from prior bars and this close."""
    params = _params("Fibonacci Continuation", params)
    horizon = HORIZONS[horizon_key]
    lookback = horizon["fib_lookback"]
    level, anchor, position, other_position, retrace, sign = _continuation_sides(
        df["High"].shift(1), df["Low"].shift(1), lookback, direction,
    )
    close = df["Close"].to_numpy(dtype=float)
    atr14 = atr(df, 14).to_numpy(dtype=float)
    stop = level - sign * FIB_CONTINUATION_STOP_ATR * atr14
    with np.errstate(invalid="ignore", divide="ignore"):
        impulse = np.abs(level - anchor)
        depth = np.where(impulse > 0, np.abs(level - retrace) / impulse, np.nan)
        structure = (other_position < position) & (
            (lookback - 1 - position) >= params["min_pullback_bars"]
        )
        held = (depth >= params["d_min"]) & (depth <= params["d_max"])
        crossed = sign * (close - level) > 0
        loss_pct = np.abs(close - stop) / close * 100
        fits = loss_pct <= capped_planned_loss_pct(horizon["max_risk_pct"]) + 1e-9
        signal = structure & held & crossed & fits & (impulse > 0)
    return pd.DataFrame({
        "level": level, "impulse": impulse, "retrace": retrace, "depth": depth,
        "stop": stop, "signal": signal.astype(bool),
    }, index=df.index)


def fib_continuation_at(df, index, horizon_key, direction, params=None):
    """Return one signal bar's continuation structure, otherwise None."""
    if index < 0:
        index += len(df)
    row = fib_continuation_frame(
        df.iloc[:index + 1], horizon_key, direction, params,
    ).iloc[-1]
    if not bool(row["signal"]):
        return None
    return {key: float(row[key]) for key in ("level", "impulse", "retrace", "stop")}


def fib_continuation_entries(df, horizon_key, params=None):
    """Return continuation entries after the common trend, ATR, and volume gates."""
    gates = compute_shared_gates(df)
    common = gates["atr_floor"] & gates["atr_calm"] & gates["vol_ok"]
    bullish_signal = fib_continuation_frame(df, horizon_key, "bullish", params)["signal"]
    bearish_signal = fib_continuation_frame(df, horizon_key, "bearish", params)["signal"]
    bullish = (bullish_signal & gates["bull_regime"] & gates["trend50_bull"] & common)
    bearish = (bearish_signal & gates["bear_regime"] & gates["trend50_bear"] & common)
    return bullish.fillna(False).astype(bool), bearish.fillna(False).astype(bool)


ENTRY_FUNCS["Fibonacci Continuation"] = fib_continuation_entries


# --- v131: Fibonacci Limit -- a resting buy limit inside the retracement zone --
#
# Armed at the close of bar t, from bars <= t only, while the pullback is still
# above the order. Bullish only. Masked in STRATEGY_GATES; the v131 measurement
# unmasks it through gate_override. The plan side (entry at the limit, stop and
# target priced from it) lives in planning/builders.py.

DEFAULT_PARAMS["Fibonacci Limit"] = {
    "L": 0.618,   # limit sits L of the leg below the swing high; grid {0.5, 0.618}
    "N": 5,       # order life in bars after t; grid {3, 5, 10}; == PLAN_SHAPES expiry_bars
}
FIB_LIMIT_MIN_RETRACE = 0.236   # the close must already be this deep into the leg
FIB_LIMIT_MIN_AGE = 3           # the swing-high bar is at least this many bars old


def fib_limit_anchors(df, horizon_key):
    """Rolling swing anchors at each bar -- the same rolling `fib_lookback`
    max High / min Low fibonacci_entries uses -- plus the swing-high bar's
    absolute position (the leg's identity) and whether the low came first.
    Trailing windows only: row t reads bars <= t."""
    lookback = HORIZONS[horizon_key]["fib_lookback"]
    high, low = df["High"], df["Low"]
    hi_pos = _rolling_argmax_pos(high, lookback)
    lo_pos = _rolling_argmin_pos(low, lookback)
    bar = pd.Series(np.arange(len(df), dtype=float), index=df.index)
    return pd.DataFrame({
        "swing_high": high.rolling(lookback).max(),
        "swing_low": low.rolling(lookback).min(),
        "swing_high_idx": bar - (lookback - 1) + hi_pos,
        "up_leg": hi_pos > lo_pos,
    }, index=df.index)


def _fib_limit_candidates(df, anchors, ratio):
    """Conditions 1-4 of the v131 arming rule, per bar (no order bookkeeping)."""
    gates = compute_shared_gates(df)
    leg = anchors["swing_high"] - anchors["swing_low"]
    retrace = (anchors["swing_high"] - df["Close"]) / leg.where(leg > 0)
    age = pd.Series(np.arange(len(df), dtype=float), index=df.index) - anchors["swing_high_idx"]
    ok = (anchors["up_leg"] & (age >= FIB_LIMIT_MIN_AGE)
          & (retrace >= FIB_LIMIT_MIN_RETRACE) & (retrace < ratio)
          & gates["bull_regime"] & gates["trend50_bull"]
          & gates["atr_floor"] & gates["atr_calm"])
    return ok.fillna(False).astype(bool)


def _order_after_bar(order, t, bar_low, bar_high, life):
    """The resting order still live after bar t's close, else None: it filled
    (Low < limit, strictly), cancelled (High > the frozen swing high) or
    reached the end of its `life` bars. Reads bar t only."""
    if order is None:
        return None
    armed_at, limit, cancel = order
    done = bar_low < limit or bar_high > cancel or t - armed_at >= life
    return None if done else order


def _arm_orders(candidate, leg, low, high, limit, cancel, life):
    """Walk the bars in order. Arm at t when conditions 1-4 hold, no order is
    live and this leg (its swing-high bar) has never armed -- an expired or
    cancelled order never re-arms the same leg. The live-order state at t is
    built from bars <= t, so the mask is causal."""
    arm = np.zeros(len(candidate), dtype=bool)
    armed_legs = set()
    order = None
    for t in range(len(candidate)):
        order = _order_after_bar(order, t, low[t], high[t], life)
        if order is None and candidate[t] and leg[t] not in armed_legs:
            arm[t] = True
            armed_legs.add(leg[t])
            order = (t, limit[t], cancel[t])
    return arm


def fibonacci_limit_setups(df, horizon_key, params=None):
    """v131 arming mask plus the frozen order geometry, per bar:
    `arm`, `swing_high`, `swing_low`, `swing_high_idx` and
    `limit_price = swing_high - L * (swing_high - swing_low)`."""
    p = _params("Fibonacci Limit", params)
    anchors = fib_limit_anchors(df, horizon_key)
    limit = anchors["swing_high"] - p["L"] * (anchors["swing_high"] - anchors["swing_low"])
    arm = _arm_orders(
        _fib_limit_candidates(df, anchors, p["L"]).to_numpy(),
        anchors["swing_high_idx"].to_numpy(), df["Low"].to_numpy(dtype=float),
        df["High"].to_numpy(dtype=float), limit.to_numpy(dtype=float),
        anchors["swing_high"].to_numpy(dtype=float), int(p["N"]))
    return pd.DataFrame({"arm": arm, "swing_high": anchors["swing_high"],
                         "swing_low": anchors["swing_low"],
                         "swing_high_idx": anchors["swing_high_idx"],
                         "limit_price": limit}, index=df.index)


def _fib_limit_row(df, index, horizon_key):
    """The anchors row at `index`, computed from bars <= index only; None when
    the window is incomplete or the leg is flat."""
    if index < 0:
        index += len(df)
    lookback = HORIZONS[horizon_key]["fib_lookback"]
    window = df.iloc[max(0, index + 1 - lookback):index + 1]   # the rolling window itself
    row = fib_limit_anchors(window, horizon_key).iloc[-1]
    high, low = float(row["swing_high"]), float(row["swing_low"])
    if not (np.isfinite(high) and np.isfinite(low)) or high <= low:
        return None
    return row


def fib_limit_price_at(df, index, horizon_key, direction, params=None):
    """The v131 limit price frozen at bar `index`: swing_high - L * leg.
    Bullish only; None for bearish or an unusable window."""
    row = _fib_limit_row(df, index, horizon_key) if direction == "bullish" else None
    if row is None:
        return None
    ratio = _params("Fibonacci Limit", params)["L"]
    return float(row["swing_high"] - ratio * (row["swing_high"] - row["swing_low"]))


def fib_limit_cancel_at(df, index, horizon_key, direction):
    """The frozen swing high: a bar trading above it cancels the unfilled order."""
    row = _fib_limit_row(df, index, horizon_key) if direction == "bullish" else None
    return None if row is None else float(row["swing_high"])


DEFAULT_PARAMS["EMA Crossover"] = {
    "rsi_dip": 45, "ext_atr": 1.0,
    # Rescue gate (Task 107/108): pullback entry mode. TRAIN grid
    # (docs/superpowers/results/2026-07-rescue-ema-train.md) found all 3
    # pullback_max_bars points qualifying (WR>=80, ExpR>0, N>=30,
    # excl<=50%); pullback_max_bars=15 is the pre-registered max-expectancy
    # winner (N=68, WR=91.2%, ExpR=+0.197 on TRAIN) vs the "cross" baseline
    # (N=110, WR=68.2%, ExpR=-0.059) it replaces. Adopted here permanently;
    # Task 109 spends the single VALIDATION-window look against this exact
    # config, no retuning after.
    "entry_mode": "pullback", "pullback_max_bars": 15,
    # v108 re-arm: pullback touch *events* taken per held cross, per direction.
    # 1 = first touch only -- the pre-v108 entry, bit-for-bit. Changed only by
    # a v108 funnel verdict (docs/superpowers/results/*-v108-*.md).
    "max_touches_bull": 1, "max_touches_bear": 1,
}


def _touch_events_after(cross, touch, window, max_touches):
    """Mark the first `max_touches` touch events in the `window` bars after each cross.

    A touch event is a touching bar whose previous bar did not touch, so a run
    of consecutive touching bars is one event. The first touching bar inside a
    window always opens an event, even when the cross bar itself touched --
    that keeps max_touches=1 identical to the pre-v108 first-touch rule. Each
    cross counts independently. Bar j reads only the cross at ci < j and the
    touch mask at j and j-1 (no lookahead).
    """
    if max_touches < 1:
        raise ValueError(f"max_touches must be >= 1, got {max_touches}")
    cross = np.asarray(cross, dtype=bool)
    touch = np.asarray(touch, dtype=bool)
    starts = touch & ~np.concatenate(([False], touch[:-1]))
    out = np.zeros(len(touch), dtype=bool)
    for ci in np.flatnonzero(cross):
        taken = 0
        for j in range(ci + 1, min(ci + 1 + window, len(touch))):
            if touch[j] and (j == ci + 1 or starts[j]):
                out[j] = True
                taken += 1
                if taken >= max_touches:
                    break
    return out


def _pullback_entries(cross, touch, window, max_touches):
    """Series wrapper: the touch-event bars that follow a held cross."""
    marks = _touch_events_after(cross.fillna(False).to_numpy(dtype=bool),
                                touch.fillna(False).to_numpy(dtype=bool),
                                window, max_touches)
    return pd.Series(marks, index=cross.index)


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

        # v108 re-arm: the first K touch events per held cross (K=1 = pre-v108).
        held_bull = _pullback_entries(held_bull, touched_bull, window,
                                      int(p.get("max_touches_bull", 1)))
        held_bear = _pullback_entries(held_bear, touched_bear, window,
                                      int(p.get("max_touches_bear", 1)))

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


DEFAULT_PARAMS["VWAP"] = {
    "ext_pct": 1.5, "hold_bars_2w": 3, "hold_bars_other": 2,
    # v84 R14 fallback. None = gate off (the shipped default until its own
    # TRAIN + fold check passes). Units: VWAP's 8-bar rise per ATR.
    "min_vwap_slope_atr": None,
}


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
    slope_min = p.get("min_vwap_slope_atr")
    if slope_min is not None:
        atr14 = g["atr14"]
        slope = (vwap - vwap.shift(8)) / atr14.replace(0, np.nan)
        vwap_up = vwap_up & (slope >= slope_min)
        vwap_down = vwap_down & (slope <= -slope_min)
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
    # v84 rescue: fast/mid must sit on the correct side of slow for N
    # consecutive bars ending at the crossover. 1 = off (same-bar firing).
    "confirm_bars": 1,
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

    # --- v84 rescue: temporal persistence of the alignment ---
    # Distinct axis from the closed width grid below: width measures how far
    # apart the ribbon is right now; this measures how long the ordering has
    # held. Targets whipsaw false-starts, not narrow ribbons.
    from swingbot import config
    confirm = int(params.get("confirm_bars") if params and "confirm_bars" in params
                  else getattr(config, "MA_RIBBON_CONFIRM_BARS", None)
                  or p["confirm_bars"])
    if confirm > 1:
        above_slow = (fast > slow_sma) & (mid > slow_sma)
        below_slow = (fast < slow_sma) & (mid < slow_sma)
        held_up = (above_slow.rolling(confirm).sum() == confirm).fillna(False)
        held_dn = (below_slow.rolling(confirm).sum() == confirm).fillna(False)
        bullish &= held_up
        bearish &= held_dn

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


DEFAULT_PARAMS["Support/Resistance"] = {"base_atr": 4.0, "close_frac": 0.4,
                                        "gap_pct": 3.0,
                                        # v84 rescue: the broken level must
                                        # have been tested and rejected this
                                        # many times first. 0 = off.
                                        "min_level_touches": 0}


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

    # --- v84 rescue: level-touch significance, as a PRE-ENTRY gate ---
    # Adjacency declared: the closed LEVEL_TOUCH_STRENGTH (v36) used touch
    # count as a post-selection tiebreak between target candidates and
    # measured net-negative. This is the same signal at a different pipeline
    # point -- gating which setups fire at all. Different mechanism, and the
    # results doc says so explicitly.
    from swingbot import config
    min_touches = int(params.get("min_level_touches") if params and
                      "min_level_touches" in params
                      else getattr(config, "SR_MIN_LEVEL_TOUCHES", None)
                      or p["min_level_touches"])
    if min_touches > 0:
        near = 0.5 * g["atr14"]
        # approached the level and closed back on the wrong side of it
        rejected_res = ((high >= resistance - near) & (close < resistance))
        rejected_sup = ((low <= support + near) & (close > support))
        touches_res = rejected_res.rolling(lookback).sum().shift(1)
        touches_sup = rejected_sup.rolling(lookback).sum().shift(1)
        bullish &= (touches_res >= min_touches).fillna(False)
        bearish &= (touches_sup >= min_touches).fillna(False)

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


def _break_retest_levels(df, horizon_key):
    """The broken levels Break & Retest trades against: the `sr_lookback`-bar
    high / low as it stood `sr_lookback` bars earlier. Every value is built
    from bars at or before its own index (shift(lookback)) -- no lookahead.
    Shared by break_retest_entries and break_retest_level_at (v129)."""
    lookback = HORIZONS[horizon_key]["sr_lookback"]
    resistance = df["High"].rolling(lookback).max().shift(lookback)
    support = df["Low"].rolling(lookback).min().shift(lookback)
    return resistance, support


def break_retest_level_at(df, index, horizon_key, direction):
    """v129: the broken level a Break & Retest entry at `index` leans on --
    resistance for a bullish retest, support for a bearish one. None while
    the series is still warming up."""
    resistance, support = _break_retest_levels(df, horizon_key)
    value = float((resistance if direction == "bullish" else support).iloc[index])
    return value if np.isfinite(value) else None


def break_retest_entries(df, horizon_key, params=None):
    p = _params("Break & Retest", params)
    g = compute_shared_gates(df)
    close, high, low = df["Close"], df["High"], df["Low"]

    resistance, support = _break_retest_levels(df, horizon_key)
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
                                    "min_reclaim_strength": None,
                                    # v84 rescue: RSI must move in the trade
                                    # direction for N consecutive bars, not
                                    # the single uptick below. 1 = off.
                                    "min_consecutive_rsi_turn": 1}


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

    from swingbot import config
    min_turn = int(params.get("min_consecutive_rsi_turn") if params and
                   "min_consecutive_rsi_turn" in params
                   else getattr(config, "RSI_DIV_MIN_CONSECUTIVE_TURN", None)
                   or p["min_consecutive_rsi_turn"])
    min_turn = max(1, min_turn)
    rising = rsi14 > rsi14.shift(1)
    falling = rsi14 < rsi14.shift(1)
    if min_turn > 1:
        rising = (rising.rolling(min_turn).sum() == min_turn)
        falling = (falling.rolling(min_turn).sum() == min_turn)
    turn_bull = (rsi14 > reclaim) & rising.fillna(False)
    turn_bear = (rsi14 < (100 - reclaim)) & falling.fillna(False)

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


# v104 Part B registers its short-only strategies into ENTRY_FUNCS and
# DEFAULT_PARAMS. Imported last: short_entries imports names defined above.
from swingbot.core.market import short_entries  # noqa: E402,F401
