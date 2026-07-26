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


STREAK_TRIGGER = 4
STREAK_MULT = 0.5
STREAK_RECOVERY_WINS = 2
COMBINED_FLOOR = 0.25


def streak_multiplier(recent_closed: list) -> float:
    """4 consecutive losses halve new-entry risk until 2 wins land.
    Scratches/timeouts are noise: they neither break nor extend a streak."""
    decisive = [o for o in recent_closed if o in ("win", "loss")]
    streak = wins_after = 0
    triggered = False
    for o in decisive:
        if o == "loss":
            streak += 1
            if streak >= STREAK_TRIGGER:
                triggered, wins_after = True, 0
        else:
            streak = 0
            if triggered:
                wins_after += 1
                if wins_after >= STREAK_RECOVERY_WINS:
                    triggered = False
    return STREAK_MULT if triggered else 1.0


def combined_throttle(dd_mult: float, streak_mult: float) -> float:
    if dd_mult <= 0.0:
        return 0.0
    return max(COMBINED_FLOOR, dd_mult * streak_mult)
