"""v192: the gap-toward-stop reclaim rule, one module for live and replay.

A market plan built under MARKET_ENTRY_NEXT_OPEN waits for the next session's
open (``waits_next_open``). At that open, in this order (``decide_at_open``):

1. the open at or beyond the stop cancels (``OPEN_THROUGH_STOP``);
2. with a stored reclaim level X and the open at or beyond X toward the stop,
   the plan rests as a DAY stop order at the planned entry E for that session
   (``RECLAIM_WAIT``) and fills only on a trade one tick through E;
3. a stop farther than the plan's ceiling from the open cancels (``RISK_CAP``);
4. otherwise the plan fills at the open (``FILL_OPEN``).

E is ``plan.trigger_price``. ``a_t`` is Wilder ATR14 of the completed bars
through the creating bar t -- never t + 1 (NO-LOOKAHEAD) -- and X = E -/+ g x a_t
rounded to the tick away from E. Both are computed once at creation
(``stamp_next_open``) and stored on the plan; every later decision reads the
stored values, so a reload, a knob flip or a restart never moves them.
"""
from __future__ import annotations

import math

from swingbot import config
from swingbot.core.risk_limits import planned_loss_pct
from .lifecycle import at_or_beyond_stop
from .plan_types import PlanStatus
from .stop_scope import plan_stop_ceiling

OPEN_THROUGH_STOP = "open_through_stop"
GAP_NO_RECLAIM = "gap_no_reclaim"
RISK_CAP = "risk_cap"
FILL_OPEN = "open"
RECLAIM_WAIT = "reclaim_wait"
ATR_PERIOD = 14
MIN_ATR_BARS = 15

_GRID_EPS = 1e-9


def tick_for(price: float) -> float:
    """The price grid: a cent from $1 up, a hundredth of a cent below."""
    return 0.01 if price >= 1 else 0.0001


def _places(tick: float) -> int:
    return 2 if tick >= 0.01 else 4


def _on_grid(value: float, tick: float, up: bool) -> float:
    """Round onto the tick grid -- ceil when ``up``, else floor -- tolerant of float noise."""
    steps = value / tick
    steps = math.ceil(steps - _GRID_EPS) if up else math.floor(steps + _GRID_EPS)
    return round(steps * tick, _places(tick))


def atr_at(df, index: int) -> float | None:
    """Wilder ATR14 of ``df.iloc[:index + 1]`` (bars through ``index`` only), or None
    with fewer than MIN_ATR_BARS bars, or when it is NaN or not positive."""
    if index >= len(df):
        raise IndexError(f"bar {index} is beyond a frame of {len(df)} bars")
    if index + 1 < MIN_ATR_BARS:
        return None
    from swingbot.core.market.indicators import atr as atr_indicator
    value = float(atr_indicator(df.iloc[:index + 1], ATR_PERIOD).iloc[-1])
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def reclaim_level_for(entry: float, atr: float, g: float, direction: str) -> float:
    """X = E - g x a_t floored (bullish) / E + g x a_t ceiled (bearish), on E's tick grid."""
    tick = tick_for(entry)
    if direction == "bullish":
        return _on_grid(entry - g * atr, tick, up=False)
    return _on_grid(entry + g * atr, tick, up=True)


def effective_g() -> float:
    """GAP_RECLAIM_ATR as honoured: 0 unless MARKET_ENTRY_NEXT_OPEN is on."""
    if not getattr(config, "MARKET_ENTRY_NEXT_OPEN", False):
        return 0.0
    return float(getattr(config, "GAP_RECLAIM_ATR", 0.0))


def next_open_applies(plan) -> bool:
    """A builder should build this plan waiting for the next open: a market plan,
    MARKET_ENTRY_NEXT_OPEN on, and not a v180 next-open strategy (Turtle Soup keeps
    its own path)."""
    from .next_open_entry import uses_next_open_fill   # next_open_entry imports exit_sim
    return (getattr(plan, "entry_type", None) == "market"
            and bool(getattr(config, "MARKET_ENTRY_NEXT_OPEN", False))
            and not uses_next_open_fill(plan))


def waits_for_open(plan) -> bool:
    """This plan is a market plan still waiting for its next open. Reads the persisted
    marker, never the knob: a plan resting since before a flip keeps its path, and a
    hand-built PENDING market plan without the marker keeps the close fill."""
    return (getattr(plan, "entry_type", None) == "market"
            and getattr(plan, "status", None) == PlanStatus.PENDING
            and getattr(plan, "waits_next_open", None) is True)


def stamp_next_open(plan, df, index: int) -> None:
    """Turn a freshly built market plan into one that waits for the next open.
    ``index`` is the creating bar t in ``df``. Stores a_t and X only when the veto is
    armed (effective_g() > 0) and a_t is usable; otherwise the plan fills at the
    open as the baseline does."""
    plan.entry_price = None
    plan.waits_next_open = True
    g = effective_g()
    if g <= 0:
        return
    a_t = atr_at(df, index)
    if a_t is None:
        return
    plan.reclaim_atr = a_t
    plan.reclaim_level = reclaim_level_for(plan.trigger_price, a_t, g, plan.direction)


def gap_toward_stop(plan, open_price: float) -> float:
    """Price distance the open sits beyond E toward the stop (positive = toward it)."""
    if plan.direction == "bullish":
        return plan.trigger_price - open_price
    return open_price - plan.trigger_price


def _at_or_beyond_level(plan, open_price: float) -> bool:
    level = getattr(plan, "reclaim_level", None)
    if level is None:
        return False
    return open_price <= level if plan.direction == "bullish" else open_price >= level


def decide_at_open(plan, open_price: float) -> str:
    """The open decision, in the frozen order (module docstring)."""
    if at_or_beyond_stop(plan, open_price):
        return OPEN_THROUGH_STOP
    if _at_or_beyond_level(plan, open_price):
        return RECLAIM_WAIT
    if planned_loss_pct(open_price, plan.stop_loss) > plan_stop_ceiling(plan):
        return RISK_CAP
    return FILL_OPEN


def _through_entry(plan) -> float:
    """E plus one tick in the trade's direction (bullish up, bearish down)."""
    tick = tick_for(plan.trigger_price)
    sign = 1 if plan.direction == "bullish" else -1
    return round(plan.trigger_price + sign * tick, _places(tick))


def reclaim_touched(plan, high: float, low: float) -> bool:
    """The bar traded one tick through E: bullish High >= E + tick, bearish Low <= E - tick."""
    level = _through_entry(plan)
    return high >= level if plan.direction == "bullish" else low <= level


def reclaim_fill_price(plan) -> float:
    """Replay's reclaim fill: E + tick (bullish) / E - tick (bearish) -- the one adverse
    tick standing in for the DAY stop order's slippage (the v1 arm replay applies no
    frictions in either arm). Live fills at E."""
    return _through_entry(plan)
