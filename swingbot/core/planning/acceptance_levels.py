"""v129 acceptance-failure exits: the level a plan leans on.

Shared by BOTH plan paths -- the live builders (builders.py) and the
backtest (backtest._bt_plan) -- for the reason builders.py's level-lifecycle
comment records: a stop/exit feature reaching only one path is unmeasurable
by construction (edge-engine v4, v92 STALL_EXIT_ENABLED). V129-5 adds the
flag-on arm transforms here; with ACCEPTANCE_EXIT_ENABLED off this module
only records acceptance_level and never touches a stop.
"""
from __future__ import annotations

BREAK_RETEST = "Break & Retest"


def stamp_strategy_acceptance(plan, df, index) -> None:
    """Record the broken level on a Break & Retest plan. Every other
    strategy keeps acceptance_level None -- only Break & Retest has a
    well-defined broken level (spec § Out of scope)."""
    if plan.strategy != BREAK_RETEST:
        return
    from swingbot.core.market.entry_filters import break_retest_level_at
    plan.acceptance_level = break_retest_level_at(df, index, plan.horizon_key,
                                                  plan.direction)


def stamp_confluence_acceptance(plan, df, level) -> None:
    """Record a confluence plan's level: the scenario's stop BEFORE
    _clamp_stop_to_hard_cap ran (supports[0] / resistances[0])."""
    plan.acceptance_level = None if level is None else float(level)
