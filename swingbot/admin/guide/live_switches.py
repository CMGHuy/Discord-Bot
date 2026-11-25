"""v237: which gates the live scan applies, read from the settings themselves.

Chapter 6 lists every built gate with its setting, its current value and
whether the live scan applies it. "Applied" uses the same condition as the
code that consumes the setting (a coupled pair needs both halves), so a gate
that is built but switched off reads "measured, not used" and flips the day
its flag flips. Only the attribute names written in this module are read.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from swingbot import config
from swingbot.admin.guide.live_risk import _field, _flag, _num
from swingbot.core.market import strategy_types

APPLIED = "applied"
NOT_USED = "measured, not used"


@dataclass(frozen=True)
class SwitchRow:
    label: str
    settings: tuple[str, ...]
    active: Callable[[], bool]


def _on(attr: str) -> Callable[[], bool]:
    return lambda: bool(getattr(config, attr))


def _above(attr: str, floor: float) -> Callable[[], bool]:
    return lambda: float(getattr(config, attr)) > floor


def _not(attr: str, baseline: str) -> Callable[[], bool]:
    return lambda: str(getattr(config, attr)) != baseline


def _both(*checks: Callable[[], bool]) -> Callable[[], bool]:
    return lambda: all(check() for check in checks)


def _regime_allow_set() -> bool:
    return any(strategy_types.REGIME_ALLOW.values())


SWITCH_ROWS: tuple[SwitchRow, ...] = (
    SwitchRow("Market regime gate", ("REGIME_GATES_ENABLED",),
              _both(_on("REGIME_GATES_ENABLED"), _regime_allow_set)),
    SwitchRow("Adjacent-horizon alignment", ("MTF_ADJACENT_GATE",), _on("MTF_ADJACENT_GATE")),
    SwitchRow("Relative strength, long arm", ("RS_GATE", "RS_LEADER_PERCENTILE"),
              _both(_on("RS_GATE"), _above("RS_LEADER_PERCENTILE", 0))),
    SwitchRow("Relative strength, short arm", ("RS_GATE", "RS_LAGGARD_PERCENTILE"),
              _both(_on("RS_GATE"), _above("RS_LAGGARD_PERCENTILE", 0))),
    SwitchRow("Dead-cat bounce veto", ("DEAD_CAT_BOUNCE_VETO",), _on("DEAD_CAT_BOUNCE_VETO")),
    # in_earnings_blackout has no caller in the live scan: never "applied" (controller, 2026-11-18).
    SwitchRow("Earnings blackout", ("EARNINGS_BLACKOUT_SESSIONS",), lambda: False),
    SwitchRow("Pullback volume dry-up", ("PULLBACK_DRYUP_SCOPE", "PULLBACK_DRYUP_MAX_RATIO"),
              _both(_not("PULLBACK_DRYUP_SCOPE", "off"), _above("PULLBACK_DRYUP_MAX_RATIO", 0))),
    SwitchRow("Headroom to the first target", ("HEADROOM_SCOPE", "HEADROOM_MIN_R"),
              _both(_not("HEADROOM_SCOPE", "off"), _above("HEADROOM_MIN_R", 0))),
    SwitchRow("S/R minimum level touches", ("SR_MIN_LEVEL_TOUCHES",),
              _above("SR_MIN_LEVEL_TOUCHES", 0)),
    SwitchRow("MA Ribbon confirm bars", ("MA_RIBBON_CONFIRM_BARS",),
              _above("MA_RIBBON_CONFIRM_BARS", 1)),
    SwitchRow("RSI Divergence turn confirmation", ("RSI_DIV_MIN_CONSECUTIVE_TURN",),
              _above("RSI_DIV_MIN_CONSECUTIVE_TURN", 1)),
    SwitchRow("FVG level mode", ("FVG_LEVELS_MODE",), _not("FVG_LEVELS_MODE", "all")),
    SwitchRow("Next-open market entry and gap reclaim", ("MARKET_ENTRY_NEXT_OPEN", "GAP_RECLAIM_ATR"),
              _on("MARKET_ENTRY_NEXT_OPEN")),
    SwitchRow("Data-driven stops", ("DATA_DRIVEN_STOPS_ENABLED",), _on("DATA_DRIVEN_STOPS_ENABLED")),
    SwitchRow("Stall exit", ("STALL_EXIT_ENABLED",), _on("STALL_EXIT_ENABLED")),
    SwitchRow("Runner structure exit", ("RUNNER_STRUCTURE_EXIT",), _not("RUNNER_STRUCTURE_EXIT", "off")),
)


def _value(value) -> str:
    if isinstance(value, bool):
        return _flag(value)
    if isinstance(value, (int, float)):
        return _num(value)
    return f"`{value}`" if str(value) else "(empty)"


def _switch_row(row: SwitchRow) -> str:
    names = ", ".join(f"`{name}`" for name in row.settings)
    now = ", ".join(_value(getattr(config, name)) for name in row.settings)
    verdict = APPLIED if row.active() else NOT_USED
    return f"| {row.label} | {names} | {now} | {verdict} |"


def _switches() -> str:
    rows = ["| Gate | Setting | Now | In the live scan |", "|---|---|---|---|"]
    return "\n".join(rows + [_switch_row(row) for row in SWITCH_ROWS])


def _cfg(attr: str, render: Callable[[object], str]) -> Callable[[], str]:
    return lambda: render(getattr(config, attr))


def _strategy_mode() -> str:
    value = config.STRATEGY_ALERTS_MODE
    label = dict(_field("STRATEGY_ALERTS_MODE").options).get(value, value)
    return f"{label} (`{value}`)"


def _live_strategies() -> str:
    parts = str(config.STRATEGY_ALERTS_LIVE_STRATEGIES or "").split(",")
    names = [part.strip() for part in parts if part.strip()]
    return ", ".join(names) if names else "every strategy"


def _backticked(value) -> str:
    return f"`{value}`"


SWITCH_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "gates.switches": _switches,
    "STRATEGY_ALERTS_MODE": _strategy_mode,
    "STRATEGY_ALERTS_LIVE_STRATEGIES": _live_strategies,
    "RS_GATE": _cfg("RS_GATE", _flag),
    "RS_LEADER_PERCENTILE": _cfg("RS_LEADER_PERCENTILE", _num),
    "RS_LAGGARD_PERCENTILE": _cfg("RS_LAGGARD_PERCENTILE", _num),
    "HTF_CONFLUENCE_ENABLED": _cfg("HTF_CONFLUENCE_ENABLED", _flag),
    "AVWAP_LEVELS_ENABLED": _cfg("AVWAP_LEVELS_ENABLED", _flag),
    "LEVEL_LIFECYCLE_STOPS_ENABLED": _cfg("LEVEL_LIFECYCLE_STOPS_ENABLED", _flag),
    "SCALE_OUT_ENABLED": _cfg("SCALE_OUT_ENABLED", _flag),
    "PLAN_ENGINE_V2": _cfg("PLAN_ENGINE_V2", _backticked),
    "BEAR_REGIME_MODE": _cfg("BEAR_REGIME_MODE", _backticked),
}
