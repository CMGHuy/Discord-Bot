"""Drawdown throttle ladder + loss-streak damper (E46) + kill switch (E47).

The math of drawdowns is asymmetric (-20% needs +25% back) and the math
of tilted operators is worse. The ladder cuts risk mechanically so
neither compounding nor judgment has to survive a deep hole at full
size. Constants are FROZEN by the plan's Global Constraints."""
from __future__ import annotations

DD_LADDER = ((8.0, 0.75), (12.0, 0.50), (16.0, 0.25), (20.0, 0.0))
RESUME_DD_PCT = 15.0   # once paused, entries resume only below this


def drawdown_pct(equity_points: list) -> float:
    peak, dd = float("-inf"), 0.0
    for v in equity_points:
        peak = max(peak, v)
        if peak > 0:
            dd = max(dd, (peak - v) / peak * 100.0)
    # current (not max-historical) drawdown is what throttles sizing:
    return (peak - equity_points[-1]) / peak * 100.0 if equity_points and peak > 0 else 0.0


def current_throttle(equity_points: list, was_paused: bool = False) -> tuple:
    dd = drawdown_pct(equity_points)
    if was_paused and dd >= RESUME_DD_PCT:
        return 0.0, True                       # hysteresis: stay paused
    mult = 1.0
    for threshold, m in DD_LADDER:
        if dd > threshold:
            mult = m
    return mult, mult == 0.0
