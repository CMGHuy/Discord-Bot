"""Section-5 timing & trigger checks."""
from __future__ import annotations

import math

from swingbot.core.gate.levels import _safe_atr
from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult

# TradePlanV2's machine-readable entry vocabulary (plan_engine.py) —
# extend here if the engine grows new entry types.
ENTRY_TYPES = ("stop_entry", "market")


def check_trigger_objective(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Plan-integrity invariant (HB). Firing in production = engine bug
    surfaced loudly, not a market condition."""
    problems = []
    if plan.entry_type not in ENTRY_TYPES:
        problems.append(f"unknown entry_type {plan.entry_type!r}")
    if (plan.trigger_price is None or
        not isinstance(plan.trigger_price, (int, float)) or
        (isinstance(plan.trigger_price, float) and math.isnan(plan.trigger_price)) or
        plan.trigger_price <= 0):
        problems.append("no concrete trigger price")
    if problems:
        return CheckResult("trigger_objective", "timing", "fail", 6.0,
                           "plan has no objective trigger: " + "; ".join(problems),
                           {"entry_type": str(plan.entry_type),
                            "trigger_price": plan.trigger_price})
    return CheckResult("trigger_objective", "timing", "pass", 6.0,
                       f"objective trigger: {plan.entry_type} @ {plan.trigger_price:.2f}",
                       {"entry_type": plan.entry_type})


register(check_id="trigger_objective", section="timing", weight=6.0,
         func=check_trigger_objective, hard_block=True, backtestable=False)
