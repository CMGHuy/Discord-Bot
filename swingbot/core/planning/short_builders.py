"""v104 Part B sizing: the structure stop verbatim (drop, never cap), TP1 from
the ATR ladder plus each strategy's own lower levels. Shared by the live
builder branch and backtest._trade_plan_at, so the two cannot diverge."""
from __future__ import annotations

import math

import pandas as pd

from swingbot.core.market.entry_filters import DEFAULT_PARAMS
from swingbot.core.market.indicators import zigzag_pivots
from swingbot.core.market.short_entries import BULL_TRAP, FADE, structure_at
from swingbot.core.market.strategy_types import COMPRESSION_SHORT, HORIZONS, SHORT_STRATEGIES
from swingbot.core.risk_limits import planned_loss_pct
from .params import STRUCTURE_BUFFER_ATR
from .stop_scope import stop_ceiling
from .targets import atr_target_candidates, select_structural_target


def _swing_lows_below(df, index, horizon_key, entry):
    pivots = zigzag_pivots(df.iloc[:index + 1], HORIZONS[horizon_key]["max_risk_pct"])
    return [float(price) for _, price, kind in pivots if kind == "low" and price < entry]


def _candidates(strategy, df, index, horizon_key, entry, atr_val, structure):
    candidates = atr_target_candidates(entry, atr_val, "bearish")
    if strategy == BULL_TRAP:
        return candidates + [v for v in (structure["target_a"], structure["target_b"]) if math.isfinite(v)]
    return candidates + _swing_lows_below(df, index, horizon_key, entry)


def _valid_stop(strategy, horizon_key, entry, stop):
    if not math.isfinite(stop) or stop <= entry:
        return False
    ceiling_pct, _ = stop_ceiling(strategy, "bearish", horizon_key)
    return planned_loss_pct(entry, stop) <= ceiling_pct + 1e-9


def _fade_plan(df, index, horizon_key, entry):
    """v113 A: the fade's fixed geometry, read from the signal bar's frame row --
    stop = entry x 1.02, TP1 = entry - m x (stop - entry). No target selection:
    the spec fixes m (grid {1.0, 1.25, 1.5}, frozen by the pre-registration).
    A stop beyond the horizon's ceiling drops the plan (never capped)."""
    structure = structure_at(FADE, df, index, horizon_key)
    if structure is None or not _valid_stop(FADE, horizon_key, entry, structure["stop"]):
        return None
    tp1 = structure["target_a"]
    return structure["stop"], tp1, [tp1]


def plan_short(df, index, strategy, horizon_key, direction, *, entry, atr_val, scan_params=None):
    """(stop, tp1, candidates) for a v104 short or the v113 fade at `index`, else None."""
    if direction != "bearish" or strategy not in SHORT_STRATEGIES:
        return None
    if strategy == FADE:
        return _fade_plan(df, index, horizon_key, entry)
    structure = structure_at(strategy, df, index, horizon_key)
    if structure is None or not _valid_stop(strategy, horizon_key, entry, structure["stop"]):
        return None
    if scan_params is None:
        from swingbot.scan_params import ScanParams
        scan_params = ScanParams.from_config()
    candidates = _candidates(strategy, df, index, horizon_key, entry, atr_val, structure)
    tp1 = select_structural_target(entry, structure["stop"], False, candidates,
                                   scan_params.min_risk_reward_ratio, scan_params.max_risk_reward_ratio)
    return None if tp1 is None else (structure["stop"], tp1, candidates)


def _supports_as_of(df, index, horizon_key, trigger, level_map):
    """Supports for a compression short: the caller's map, else one built from
    bars <= index only (the engine hands none when TP2 is off)."""
    if level_map is not None:
        return level_map[0]
    from swingbot.core.market import levels as levels_mod
    return levels_mod.build_level_map(df.iloc[:index + 1], HORIZONS[horizon_key], trigger)[0]


def compression_structure(df, index, *, trigger, atr_val, horizon_key, level_map, scan_params):
    """v119: (stop, target) for the compression short, sized off the resting
    `trigger` -- stop = release-bar high + the structural ATR buffer (a ceiling
    breach REJECTS, never clamps); target = the nearest lower support whose RR
    from the trigger sits inside the current band. No ATR fallback and no
    synthetic cap: no qualifying support means no plan."""
    stop = float(df["High"].iloc[index]) + STRUCTURE_BUFFER_ATR * atr_val
    if not _valid_stop(COMPRESSION_SHORT, horizon_key, trigger, stop):
        return None
    risk = stop - trigger
    low, high = scan_params.min_risk_reward_ratio, scan_params.max_risk_reward_ratio
    supports = _supports_as_of(df, index, horizon_key, trigger, level_map)
    valid = [p for p in (float(lv.price) for lv in supports)
             if p < trigger and low <= (trigger - p) / risk <= high]
    return (stop, max(valid)) if valid else None


def short_hold_cap(df, index, strategy):
    """Bars to hold a short on its `exit_before` setting: the bar before the
    next report reacts. None when holding through or no report is known."""
    if strategy not in SHORT_STRATEGIES:
        return None
    if DEFAULT_PARAMS[strategy].get("earnings", "hold") != "exit_before":
        return None
    if "evt_bars_to_next" not in df.columns:
        raise ValueError(f"{strategy} exit_before needs earnings_context.attach(df, ticker) (v104)")
    bars = df["evt_bars_to_next"].iloc[index]
    return None if pd.isna(bars) else max(int(bars) - 1, 1)
