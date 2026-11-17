"""v229 single-leg race on 5-minute bars (spec § Race rule, frozen).

The round-1 rule of swingbot/core/planning/exit_sim.py:_single_leg_exit_walk
(private, daily bars, a TradePlanV2), mirrored here on 5-minute bars: stop
before target within a bar; the stop moves to the fill once price reaches
be_fraction of the TP1 distance and protects LATER bars only; win at TP1,
loss at the stop, scratch at the moved stop; still open at `end` -> marked to
the last raced bar's close. Added on top of the walk: every stop hit fills
through gap_stop_fill, so a session-open gap through the stop fills at the
open. No runner, no TP2 -- the live scale-out is not reproduced."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from swingbot.core.backtesting.instrument.fills import gap_stop_fill
from swingbot.core.market.session import RTH_OPEN
from swingbot.core.market.strategy_types import BREAKEVEN_TRIGGER_FRACTION

from .bars import et_time

SIGN = {"bullish": 1, "bearish": -1}
OUTCOMES = ("win", "loss", "scratch", "timeout", "no_bars")


@dataclass(frozen=True)
class Race:
    outcome: str
    exit_price: float | None
    exit_ts: pd.Timestamp | None
    gap_stop: bool
    stop_moved: bool


NO_BARS = Race("no_bars", None, None, False, False)


def _sign(direction: str) -> int:
    try:
        return SIGN[direction]
    except KeyError:
        raise ValueError(f"unknown direction {direction!r}; expected bullish or bearish") from None


def _window(bars, start, end) -> pd.DataFrame | None:
    if bars is None or bars.empty:
        return None
    window = bars[(bars.index >= start) & (bars.index < end)]
    return None if window.empty else window


def _stop_exit(ts, bar_open: float, level: float, direction: str, moved: bool) -> Race:
    price = float(gap_stop_fill(bar_open, level, direction))
    gapped = price != level and et_time(ts) == RTH_OPEN
    return Race("scratch" if moved else "loss", price, ts, gapped, moved)


def race(bars, *, direction: str, fill: float, stop: float, tp1: float, start, end,
         be_fraction: float = BREAKEVEN_TRIGGER_FRACTION) -> Race:
    """Race one plan over the bars with ``start <= index < end``."""
    sign = _sign(direction)
    window = _window(bars, start, end)
    if window is None:
        return NO_BARS
    trigger = fill + sign * be_fraction * abs(tp1 - fill)
    moved = False
    rows = zip(window.index, window["Open"], window["High"], window["Low"])
    for ts, bar_open, high, low in rows:
        adverse, favour = (low, high) if sign > 0 else (high, low)
        level = fill if moved else stop
        if sign * (adverse - level) <= 0:
            return _stop_exit(ts, float(bar_open), level, direction, moved)
        if sign * (favour - tp1) >= 0:
            return Race("win", float(tp1), ts, False, moved)
        if sign * (favour - trigger) >= 0:
            moved = True
    return Race("timeout", float(window["Close"].iloc[-1]), window.index[-1], False, moved)


def gross_r(result: Race, *, direction: str, fill: float, risk: float) -> float:
    """Frictionless R of a race: sign * (exit - fill) / risk; 0.0 with no exit."""
    if risk <= 0:
        raise ValueError(f"risk must be positive, got {risk}")
    if result.exit_price is None:
        return 0.0
    return _sign(direction) * (result.exit_price - fill) / risk
