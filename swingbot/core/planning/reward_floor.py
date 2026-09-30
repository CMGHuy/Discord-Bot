"""v113 §1: the horizon-scoped reward floor for strategy-source plans.

Only a horizon carrying "min_reward_pct" in strategy_types.HORIZONS has one
(today: 1w = 2.0%). Every legacy horizon has none -- exactly as before v113,
when no reward floor gated strategy plans at all (config.MIN_REWARD_PCT gates
only confluence scenarios, and still does). build_strategy_plan and
backtest._trade_plan_at both call clears(), so live and backtest cannot diverge.

DROPS / PASSES count every decision per (strategy, horizon) in this process so
measure_v113 can report a floor-drop rate; call reset() before a measured run.
"""
from __future__ import annotations

import collections

from swingbot.core.market.strategy_types import HORIZONS

DROPS: collections.Counter = collections.Counter()
PASSES: collections.Counter = collections.Counter()
_EPS = 1e-9   # a target exactly on the floor must clear it despite float noise


def floor_pct(horizon_key: str) -> float | None:
    """This horizon's minimum target distance in % of entry, or None (no floor)."""
    return HORIZONS[horizon_key].get("min_reward_pct")


def clears(entry: float, tp1: float, strategy: str, horizon_key: str) -> bool:
    """True when TP1 sits at least the horizon's floor away from entry (either
    direction). Horizons without a floor always clear and are not counted."""
    floor = floor_pct(horizon_key)
    if floor is None:
        return True
    ok = entry > 0 and abs(tp1 - entry) / entry * 100.0 >= floor - _EPS
    (PASSES if ok else DROPS)[(strategy, horizon_key)] += 1
    return ok


def reset() -> None:
    DROPS.clear()
    PASSES.clear()
