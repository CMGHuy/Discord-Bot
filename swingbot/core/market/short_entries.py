"""v104 Part B: three short-only strategies that are not mirrors of long rules.

Each strategy is a `*_frame(df, horizon_key, params)` returning per-bar
columns -- `signal` plus the structure its sizing needs -- computed from bars
<= t only (tests pin truncation invariance). ENTRY_FUNCS gets a short-only
wrapper; STRATEGY_GATES ships every name masked until its holdout shot passes.
Market layer: this module never imports planning.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.market.entry_filters import (DEFAULT_PARAMS, ENTRY_FUNCS, _params,
                                                compute_shared_gates)
from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES, SR_VOLUME_MULTIPLE

BULL_TRAP, VOL_BREAKDOWN, GAP_DRIFT = SHORT_STRATEGIES
# Pinned to planning.params.STRUCTURE_BUFFER_ATR by a test (market never imports planning).
STOP_ATR = 0.25

DEFAULT_PARAMS[BULL_TRAP] = {"k": 3, "earnings": "hold"}
DEFAULT_PARAMS[VOL_BREAKDOWN] = {"m": 1.0, "earnings": "hold"}
DEFAULT_PARAMS[GAP_DRIFT] = {"g": 0.05}
_SPY_COLUMNS = ("ctx_spy_down", "ctx_spy_ret63")

_COLUMNS = ("signal", "level", "stop", "target_a", "target_b")


def earnings_ok(df: pd.DataFrame, params: dict) -> pd.Series:
    """`exit_before` blocks an entry whose report reacts within one bar
    (index amendment 1); otherwise every bar is allowed. Fail-closed on a
    missing column: silently holding through would measure the wrong arm."""
    if params.get("earnings", "hold") != "exit_before":
        return pd.Series(True, index=df.index)
    if "evt_bars_to_next" not in df.columns:
        raise ValueError("exit_before needs earnings_context.attach(df, ticker) first (v104)")
    return ~(df["evt_bars_to_next"] <= 1)


def _empty(df: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame({col: np.nan for col in _COLUMNS[1:]}, index=df.index)
    frame.insert(0, "signal", False)
    return frame


def _first_traps(close, level, high, k):
    """For each breakout bar b (close > level[b]) find the first t in (b, b+k]
    closing below level[b]. The first trap claiming a bar keeps it."""
    n = len(close)
    signal = np.zeros(n, dtype=bool)
    trap_level = np.full(n, np.nan)
    peak = np.full(n, np.nan)
    source = np.full(n, -1)
    with np.errstate(invalid="ignore"):
        breakouts = np.flatnonzero(close > level)
    for b in breakouts:
        for t in range(b + 1, min(b + k, n - 1) + 1):
            if close[t] < level[b]:
                if not signal[t]:
                    signal[t], trap_level[t] = True, level[b]
                    peak[t], source[t] = high[b:t + 1].max(), b
                break
    return signal, trap_level, peak, source


def bull_trap_frame(df: pd.DataFrame, horizon_key: str, params: dict | None = None) -> pd.DataFrame:
    """B1: a close above the prior sr_lookback high that closes back below it
    within k bars. Stop above the failed high; targets the pre-breakout base."""
    p = _params(BULL_TRAP, params)
    lookback = HORIZONS[horizon_key]["sr_lookback"]
    high, low = df["High"], df["Low"]
    level = high.rolling(lookback).max().shift(1).to_numpy(dtype=float)
    signal, trap_level, peak, source = _first_traps(
        df["Close"].to_numpy(dtype=float), level, high.to_numpy(dtype=float), int(p["k"]))
    gates = compute_shared_gates(df)
    base_low = low.rolling(10).min().shift(1).to_numpy(dtype=float)
    target_a = np.where(source >= 0, base_low[np.clip(source, 0, None)], np.nan)
    keep = pd.Series(signal, index=df.index) & gates["atr_floor"] & gates["vol_ok"] & earnings_ok(df, p)
    return pd.DataFrame({
        "signal": keep.fillna(False).astype(bool),
        "level": trap_level,
        "stop": peak + STOP_ATR * gates["atr14"].to_numpy(dtype=float),
        "target_a": target_a,
        "target_b": low.rolling(lookback).min().shift(1).to_numpy(dtype=float),
    }, index=df.index)


def vol_breakdown_frame(df: pd.DataFrame, horizon_key: str, params: dict | None = None) -> pd.DataFrame:
    """B2: a close under the prior sr_lookback low, in a falling market (SPY below
    a falling MA50), on heavy volume, with ATR EXPANDING (>= m x its 60-bar mean,
    the reverse of atr_calm), by a name weaker than SPY over 63 bars. Without the
    market-context block there is no signal (silent while masked)."""
    p = _params(VOL_BREAKDOWN, params)
    if not all(col in df.columns for col in _SPY_COLUMNS):
        return _empty(df)
    lookback = HORIZONS[horizon_key]["sr_lookback"]
    gates = compute_shared_gates(df)
    close, atr14 = df["Close"], gates["atr14"]
    support = df["Low"].rolling(lookback).min().shift(1)
    market_down = df["ctx_spy_down"] == 1.0
    weaker = (close / close.shift(63) - 1.0) < df["ctx_spy_ret63"]
    heavy = df["Volume"] >= SR_VOLUME_MULTIPLE * df["Volume"].rolling(20).mean()
    expanding = atr14 >= float(p["m"]) * atr14.rolling(60).mean()
    signal = ((close < support) & market_down & weaker & heavy & expanding
              & gates["atr_floor"] & earnings_ok(df, p))
    frame = _empty(df)
    frame["signal"] = signal.fillna(False).astype(bool)
    frame["level"] = support.to_numpy(dtype=float)
    frame["stop"] = (support + STOP_ATR * atr14).to_numpy(dtype=float)
    return frame


def gap_drift_frame(df: pd.DataFrame, horizon_key: str, params: dict | None = None) -> pd.DataFrame:
    """B3: the session after an earnings reaction that gapped down >= g and did
    not recover (close below the reaction day's close). Stop above the reaction
    day's high. Horizon-independent entry. Without earnings context, no signal."""
    p = _params(GAP_DRIFT, params)
    if "evt_reaction" not in df.columns:
        return _empty(df)
    close = df["Close"]
    gap_day = (df["evt_reaction"] == 1.0) & (df["Open"] <= close.shift(1) * (1.0 - float(p["g"])))
    after_gap = gap_day.shift(1, fill_value=False).astype(bool)
    signal = after_gap & (close < close.shift(1))
    gates = compute_shared_gates(df)
    frame = _empty(df)
    frame["signal"] = signal.fillna(False).astype(bool)
    frame["level"] = close.shift(1).to_numpy(dtype=float)
    frame["stop"] = (df["High"].shift(1) + STOP_ATR * gates["atr14"]).to_numpy(dtype=float)
    return frame


FRAMES = {BULL_TRAP: bull_trap_frame, VOL_BREAKDOWN: vol_breakdown_frame, GAP_DRIFT: gap_drift_frame}


def _short_only(frame_fn):
    def entries(df, horizon_key, params=None):
        bearish = frame_fn(df, horizon_key, params)["signal"]
        return pd.Series(False, index=df.index), bearish
    return entries


def structure_at(strategy: str, df: pd.DataFrame, index: int, horizon_key: str,
                 params: dict | None = None) -> dict | None:
    """The signal bar's structure computed from bars <= index, else None."""
    if index < 0:
        index += len(df)
    row = FRAMES[strategy](df.iloc[:index + 1], horizon_key, params).iloc[-1]
    if not bool(row["signal"]):
        return None
    return {key: float(row[key]) for key in ("stop", "target_a", "target_b")}


def _register() -> None:
    for name, frame_fn in FRAMES.items():
        ENTRY_FUNCS[name] = _short_only(frame_fn)


_register()
