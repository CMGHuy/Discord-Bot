"""v129 acceptance-failure exits: the level a plan leans on.

Shared by BOTH plan paths -- the live builders (builders.py) and the
backtest (backtest._bt_plan) -- for the reason builders.py's level-lifecycle
comment records: a stop/exit feature reaching only one path is unmeasurable
by construction (edge-engine v4, v92 STALL_EXIT_ENABLED). With
ACCEPTANCE_EXIT_ENABLED off this module only records acceptance_level and
never touches a stop; the flag-on arm transforms (Z, B) live here too.
"""
from __future__ import annotations

import math

from swingbot import config
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct

BREAK_RETEST = "Break & Retest"
ARM_Z, ARM_B = "Z", "B"
ARMS = (ARM_Z, ARM_B)


def enabled_arms() -> frozenset:
    """Arms in force. ACCEPTANCE_EXIT_ARMS is read only when the master flag
    is on; unknown letters and blanks are dropped, never raised on."""
    if not getattr(config, "ACCEPTANCE_EXIT_ENABLED", False):
        return frozenset()
    raw = str(getattr(config, "ACCEPTANCE_EXIT_ARMS", "") or "")
    return frozenset(part.strip().upper() for part in raw.split(",")) & frozenset(ARMS)


def close_threshold(level, atr_val, b, direction) -> float:
    """The close that ends the trade: level - b*ATR (bullish, exit on a close
    strictly below), level + b*ATR (bearish, strictly above)."""
    return level - b * atr_val if direction == "bullish" else level + b * atr_val


def disaster_stop(entry, level, atr_val, m, direction) -> float:
    """Arm Z's intrabar stop: level -/+ m*ATR, pulled in to the 2% hard cap
    when farther -- max(level - m*atr, entry*(1 - 0.02)) for a bullish plan."""
    cap = entry * HARD_MAX_PLANNED_LOSS_PCT / 100.0
    if direction == "bullish":
        return max(level - m * atr_val, _inside_cap(entry, entry - cap))
    return min(level + m * atr_val, _inside_cap(entry, entry + cap))


def _inside_cap(entry, stop) -> float:
    """Nudge `stop` toward entry by single ulps until planned_loss_pct is at
    most the cap exactly -- entry*0.98 can land 1 ulp past 2.0%, which
    plan_manager's strict risk_cap comparison would reject."""
    while planned_loss_pct(entry, stop) > HARD_MAX_PLANNED_LOSS_PCT:
        stop = math.nextafter(stop, entry)
    return stop


def confluence_eligible(entry, level, direction) -> bool:
    """Arm Z applies only when the level sits on the stop side of entry and
    within the 2% cap (1e-9 tolerance, as entry_filters does) -- exactly the
    plans _clamp_stop_to_hard_cap did NOT move. The rest keep today's stop and
    get no acceptance exit."""
    if level is None or entry is None or entry <= 0:
        return False
    on_stop_side = level < entry if direction == "bullish" else level > entry
    return on_stop_side and planned_loss_pct(entry, level) <= HARD_MAX_PLANNED_LOSS_PCT + 1e-9


def apply_arm_z(plan, atr_val, m, b) -> bool:
    """Write arm Z onto an eligible confluence plan: stop_loss becomes the
    disaster stop (so 1R = entry -> disaster stop for every consumer) and the
    close threshold is set. Returns eligibility; an ineligible plan is
    left exactly as built."""
    entry, level = plan.trigger_price, plan.acceptance_level
    if not confluence_eligible(entry, level, plan.direction):
        return False
    plan.stop_loss = disaster_stop(entry, level, atr_val, m, plan.direction)
    plan.acceptance_close_below = close_threshold(level, atr_val, b, plan.direction)
    return True


def apply_arm_b(plan, atr_val, b) -> bool:
    """Arm B: stop unchanged (the 2*ATR fallback); add the close threshold
    at the broken level. False when the plan has no level (warm-up)."""
    if plan.acceptance_level is None:
        return False
    plan.acceptance_close_below = close_threshold(plan.acceptance_level, atr_val, b,
                                                  plan.direction)
    return True


def atr_at(df, index, entry) -> float:
    """ATR14 at `index`, through _safe_atr_value (2% of entry when NaN or
    non-positive) -- causal, so df and df.iloc[:index+1] agree."""
    from swingbot.core.market.indicators import atr as atr_indicator
    from .targets import _safe_atr_value
    return _safe_atr_value(entry, float(atr_indicator(df, 14).iloc[index]))


def stamp_strategy_acceptance(plan, df, index) -> None:
    """Record the broken level on a Break & Retest plan; with arm B enabled,
    also set its close threshold. Every other strategy is left untouched --
    only Break & Retest has a well-defined broken level."""
    if plan.strategy != BREAK_RETEST:
        return
    from swingbot.core.market.entry_filters import break_retest_level_at
    plan.acceptance_level = break_retest_level_at(df, index, plan.horizon_key,
                                                  plan.direction)
    if ARM_B in enabled_arms():
        apply_arm_b(plan, atr_at(df, index, plan.trigger_price),
                    config.ACCEPTANCE_CLOSE_BUFFER_ATR)


def stamp_confluence_acceptance(plan, df, level) -> None:
    """Record a confluence plan's pre-clamp level; with arm Z enabled, apply
    the disaster stop and close threshold at the creating bar's ATR14."""
    plan.acceptance_level = None if level is None else float(level)
    if ARM_Z in enabled_arms():
        apply_arm_z(plan, atr_at(df, len(df) - 1, plan.trigger_price),
                    config.ACCEPTANCE_DISASTER_ATR_M, config.ACCEPTANCE_CLOSE_BUFFER_ATR)
