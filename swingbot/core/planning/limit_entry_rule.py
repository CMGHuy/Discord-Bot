"""v212 resting-limit fill rule, shared by ``exit_sim_v2`` (replay),
``plan_manager`` (live) and the measurement.

Spec § The rule 6 and the G2 tie rules decide one bar, long side (short
mirrored), top to bottom:

1. an open at or through the stop fills at the open and is gap-stopped
   (a realised loss, never a scratch: the open comes first on the bar);
2. a bar reaching TP1 (or ``limit_cancel_level``), inclusive, cancels --
   also when it reaches the limit too (conservative same-bar rule);
3. an open at or through the limit L fills at the open;
4. a trade-through one tick past L fills at L (``touch=True``: reaching L);
5. otherwise nothing.

``open_=None`` (a live poll without a session open) skips rules 1 and 3.
Expiry is the caller's business. Out-of-scope limit plans (v113 fade, v131
Fibonacci Limit, ``limit_entry_f is None``) keep ``lifecycle.limit_hit`` /
``limit_cancelled`` and never reach this module.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from swingbot.core.market.atr_band import tick_size

if TYPE_CHECKING:
    from swingbot.core.planning.plan_types import TradePlanV2

_EPS = 1e-9


class BarOutcome(NamedTuple):
    kind: str            # "fill" | "cancel" | "none"
    fill: float | None   # set only for "fill"
    gap_stopped: bool    # True only for a fill at an open at or through the stop


NONE = BarOutcome("none", None, False)


def is_arm_limit(plan: "TradePlanV2") -> bool:
    return plan.entry_type == "limit" and plan.limit_entry_f is not None


def _bull(plan: "TradePlanV2") -> bool:
    return plan.direction == "bullish"


def _beyond(price: float, level: float, bull: bool) -> bool:
    """Price at or past ``level`` on the adverse (entry) side."""
    return price <= level if bull else price >= level


def tp1_reached(plan: "TradePlanV2", high: float, low: float) -> bool:
    level = plan.limit_cancel_level if plan.limit_cancel_level is not None else plan.tp1
    return high >= level if _bull(plan) else low <= level


def _traded(plan: "TradePlanV2", high: float, low: float, touch: bool) -> bool:
    bull = _bull(plan)
    limit = plan.trigger_price
    step = 0.0 if touch else tick_size(limit)
    if bull:
        return low <= limit - step + _EPS
    return high >= limit + step - _EPS


def bar_outcome(plan: "TradePlanV2", *, open_: float | None, high: float, low: float,
                touch: bool = False) -> BarOutcome:
    if not is_arm_limit(plan):
        raise ValueError(f"plan {plan.plan_id} is not an arm limit")
    bull = _bull(plan)
    if open_ is not None and _beyond(open_, plan.stop_loss, bull):
        return BarOutcome("fill", open_, True)
    if tp1_reached(plan, high, low):
        return BarOutcome("cancel", None, False)
    if open_ is not None and _beyond(open_, plan.trigger_price, bull):
        return BarOutcome("fill", open_, False)
    if _traded(plan, high, low, touch):
        return BarOutcome("fill", plan.trigger_price, False)
    return NONE
