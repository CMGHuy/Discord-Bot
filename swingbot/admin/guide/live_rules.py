"""v237: plan, level and throttle rule numbers for the guide.

Chapters 4, 7 and 8 explain these rules; every number they quote comes from
here, read when the placeholder renders (config globals follow the SIGHUP
hot reload, module constants are read by attribute), so a changed default
never leaves stale prose. Only names in RULE_PLACEHOLDERS exist.
"""
from __future__ import annotations

from typing import Callable

from swingbot import config
from swingbot.admin.guide.live_risk import _flag, _num, _pct
from swingbot.core import risk_limits
from swingbot.core.edge import throttle
from swingbot.core.market import levels_lifecycle, strategy_types
from swingbot.core.planning import builders, params


def _share(fraction) -> str:
    """A fraction as a whole percent: 0.5 -> '50%', 2/3 -> '67%'."""
    return f"{round(float(fraction) * 100)}%"


def _ratio(value) -> str:
    return f"{_num(value)}:1"


def _cfg(attr: str, render: Callable[[object], str]) -> Callable[[], str]:
    return lambda: render(getattr(config, attr))


def _clamp_level() -> str:
    return _pct(risk_limits.HARD_MAX_PLANNED_LOSS_PCT - builders.CLAMP_HEADROOM_PCT)


def _ladder_size(mult: float) -> str:
    return "paused" if mult <= 0 else f"{_share(mult)} of normal"


def _ladder() -> str:
    rungs = throttle.DD_LADDER
    rows = ["| Drawdown from peak | New-entry size |", "|---|---|",
            f"| up to {_pct(rungs[0][0])} | full size |"]
    rows += [f"| more than {_pct(dd)} | {_ladder_size(mult)} |" for dd, mult in rungs]
    return "\n".join(rows)


def _streak() -> str:
    return (f"after {throttle.STREAK_TRIGGER} losses in a row, new entries are sized at "
            f"{_num(throttle.STREAK_MULT)} × normal until "
            f"{throttle.STREAK_RECOVERY_WINS} wins land")


RULE_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "MIN_REWARD_PCT": _cfg("MIN_REWARD_PCT", _pct),
    "MIN_RISK_REWARD_RATIO": _cfg("MIN_RISK_REWARD_RATIO", _ratio),
    "MAX_RISK_REWARD_RATIO": _cfg("MAX_RISK_REWARD_RATIO", _ratio),
    "CONFLUENCE_DEVIATION_PCT": _cfg("CONFLUENCE_DEVIATION_PCT", _pct),
    "MIN_TARGET_CONFLUENCE_COUNT": _cfg("MIN_TARGET_CONFLUENCE_COUNT", _num),
    "DEDUP_TOLERANCE_PCT": _cfg("DEDUP_TOLERANCE_PCT", _pct),
    "SIGNAL_CONFIRMATION_SCANS": _cfg("SIGNAL_CONFIRMATION_SCANS", _num),
    "MIN_ALERT_CONFIDENCE_LEVEL": _cfg("MIN_ALERT_CONFIDENCE_LEVEL", _num),
    "stop.hard_cap": lambda: _pct(risk_limits.HARD_MAX_PLANNED_LOSS_PCT),
    "stop.clamp_level": _clamp_level,
    "plan.tp1_share": lambda: _share(params.TP1_FRACTION),
    "plan.runner_floor": lambda: _share(params.RUNNER_FLOOR_FRACTION),
    "plan.breakeven_trigger": lambda: _share(strategy_types.BREAKEVEN_TRIGGER_FRACTION),
    "plan.trail_atr": lambda: f"{_num(params.TRAIL_ATR_MULT)} × ATR(14)",
    "plan.expiry_bars": lambda: f"{params.DEFAULT_EXPIRY_BARS} bars",
    "levels.touch_atr": lambda: f"{_num(levels_lifecycle.TOUCH_ATR_MULT)} × ATR",
    "levels.break_atr": lambda: f"{_num(levels_lifecycle.BREAK_ATR_MULT)} × ATR",
    "throttle.ladder": _ladder,
    "throttle.resume": lambda: _pct(throttle.RESUME_DD_PCT),
    "throttle.streak": _streak,
    "DD_THROTTLE_ENABLED": _cfg("DD_THROTTLE_ENABLED", _flag),
    "KILLSWITCH_DEFAULT_ON": _cfg("KILLSWITCH_DEFAULT_ON", _flag),
}
