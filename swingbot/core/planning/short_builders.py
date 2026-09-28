"""v104 Part B sizing: the structure stop verbatim (drop, never cap), TP1 from
the ATR ladder plus each strategy's own lower levels. Shared by the live
builder branch and backtest._trade_plan_at, so the two cannot diverge."""
from __future__ import annotations

import math

import pandas as pd

from swingbot.core.market.entry_filters import DEFAULT_PARAMS
from swingbot.core.market.indicators import zigzag_pivots
from swingbot.core.market.short_entries import BULL_TRAP, structure_at
from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES
from swingbot.core.risk_limits import planned_loss_pct
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


def plan_short(df, index, strategy, horizon_key, direction, *, entry, atr_val, scan_params=None):
    """(stop, tp1, candidates) for a v104 short at `index`, else None."""
    if direction != "bearish" or strategy not in SHORT_STRATEGIES:
        return None
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
