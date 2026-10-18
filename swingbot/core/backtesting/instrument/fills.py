"""v2 fills (v136 spec section 2): every price-vs-level comparison the v2 exit
walk makes, and the price each comparison fills at.

Pure functions of bar prices, a level and a direction ("bullish" | anything
else = bearish, as everywhere in planning). Imports nothing from swingbot but
the contract: ``plan_manager`` imports ``exit_sim`` (a cycle) and
``planning.lifecycle`` takes a whole plan. The two live gap helpers
(``plan_manager.gap_stop_fill``/``gap_target_fill``) and the lifecycle touch
and entry-fill rules are mirrored here one line each, and
tests/backtesting/instrument/test_fills.py pins the parity.

Entries keep today's open-aware rules (a stop entry never fills better than
its trigger, a limit never worse than its limit) whatever ``gap_through``
says; ``gap_through`` governs exits: True fills a stop or target the bar
gapped through at the open, False at the level.
"""
from __future__ import annotations

from .contract import FillModel

STOP, TARGET = "stop", "target"
_ENTRY_TYPES = ("market", "stop_entry", "limit")


def require_supported(fill_model: FillModel) -> None:
    """ValueError unless the v2 walk implements this fill model's rules."""
    if fill_model.market_entry != "next_open" or fill_model.same_bar != "stop_first":
        raise ValueError(
            "the v2 exit walk implements market_entry='next_open' and "
            f"same_bar='stop_first' only; got {fill_model!r}")


def gap_stop_fill(bar_open: float, level: float, direction: str) -> float:
    """A stop the bar reached: at the level, or at the open if it gapped through."""
    return min(bar_open, level) if direction == "bullish" else max(bar_open, level)


def gap_target_fill(bar_open: float, level: float, direction: str) -> float:
    """A target the bar reached: at the level, or at the (better) open past it."""
    return max(bar_open, level) if direction == "bullish" else min(bar_open, level)


def stop_touched(bar_high: float, bar_low: float, stop: float, direction: str) -> bool:
    """The bar traded at or through `stop` (bullish: low <= stop)."""
    return bar_low <= stop if direction == "bullish" else bar_high >= stop


def target_touched(bar_high: float, bar_low: float, target: float, direction: str) -> bool:
    """The bar traded at or through a favourable level (bullish: high >= target)."""
    return bar_high >= target if direction == "bullish" else bar_low <= target


def at_or_beyond_stop(price: float, stop: float, direction: str) -> bool:
    """`price` already sits at or through the stop."""
    return price <= stop if direction == "bullish" else price >= stop


def entry_touched(entry_type: str, direction: str, bar_high: float, bar_low: float,
                  level: float, *, strict: bool = False) -> bool:
    """A resting order traded on this bar. ``stop_entry``: the breakout reached
    the trigger (bullish: high >= level). ``limit``: the pullback reached the
    limit (bullish: low <= level), or traded strictly through it when `strict`
    (v131 limit_strict_fill)."""
    bull = direction == "bullish"
    if entry_type == "stop_entry":
        return bar_high >= level if bull else bar_low <= level
    if entry_type != "limit":
        raise ValueError(f"no resting order for entry_type {entry_type!r}")
    if strict:
        return bar_low < level if bull else bar_high > level
    return bar_low <= level if bull else bar_high >= level


def entry_fill(fill_model: FillModel, entry_type: str, direction: str, *,
               bar_open: float, level: float | None = None) -> float:
    """The entry price on the fill bar. ``market``: the bar's open (only under
    ``market_entry == "next_open"``). ``stop_entry``: the trigger, or the worse
    open past it (bullish: max). ``limit``: the limit, or the better open past
    it (bullish: min)."""
    if entry_type not in _ENTRY_TYPES:
        raise ValueError(f"unknown entry_type {entry_type!r}")
    if entry_type == "market":
        require_supported(fill_model)
        return float(bar_open)
    if level is None:
        raise ValueError(f"a {entry_type} fill needs its level")
    take_max = (entry_type == "stop_entry") == (direction == "bullish")
    return float(max(bar_open, level) if take_max else min(bar_open, level))


def exit_fill(fill_model: FillModel, kind: str, level: float, bar_open: float,
              direction: str) -> float:
    """The exit price of a stop or target this bar reached: at the open when the
    bar gapped through it and the model fills gaps there, else at the level."""
    if kind not in (STOP, TARGET):
        raise ValueError(f"exit kind must be 'stop' or 'target', got {kind!r}")
    if not fill_model.gap_through:
        return float(level)
    if kind == STOP:
        return float(gap_stop_fill(bar_open, level, direction))
    return float(gap_target_fill(bar_open, level, direction))
