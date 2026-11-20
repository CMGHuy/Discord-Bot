"""v235: risk and sizing placeholders for the guide.

Every value is read when the placeholder renders (config globals follow the
SIGHUP hot reload; module constants are read by attribute), so a changed
default can never leave stale prose. Only names in RISK_PLACEHOLDERS exist:
no function here takes a name, and nothing reads a config attribute that is
not spelled out below.

Sizing settings an operator edits with !account (risk per trade, the dollar
risk cap, the sizing mode, the position caps, the open-position limit) come
from the stored account row the sizer reads, never from their .env seeds.
"""
from __future__ import annotations

import logging
from typing import Callable

from swingbot import config
from swingbot.core.edge import correlation, sizing
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.planning import gap_sizing

log = logging.getLogger(__name__)

UNAVAILABLE = "not available right now"


def _num(value) -> str:
    return f"{float(value):g}"


def _pct(value) -> str:
    return f"{_num(value)}%"


def _flag(value) -> str:
    return "on" if value else "off"


def _money(value) -> str:
    amount = float(value)
    return f"${amount:,.0f}" if amount.is_integer() else f"${amount:,.2f}"


def _field(attr: str) -> config.Field:
    return next(f for f in config.FIELDS if f.attr == attr)


def _cfg_pct(attr: str) -> Callable[[], str]:
    return lambda: _pct(getattr(config, attr))


def _load_account() -> dict:
    """The stored account row (patched in tests; the real read needs the database)."""
    from swingbot.core.planning.account import load_account_config
    return load_account_config()


def _account_value(key: str):
    """One setting from the stored account row; None when it cannot be read."""
    try:
        return _load_account().get(key)
    except Exception as exc:  # the guide renders without the database
        swallowed(log, "ops.admin.guide.account_row", exc,
                  "guide: account row unreadable: %s", exc)
        return None


def _from_account(key: str, render: Callable[[object], str]) -> Callable[[], str]:
    def placeholder() -> str:
        value = _account_value(key)
        return UNAVAILABLE if value is None else render(value)
    return placeholder


def _risk_max() -> str:
    return _pct(_field("RISK_PER_TRADE_PCT").max)


def _mode_text(value) -> str:
    label = dict(_field("POSITION_SIZING_MODE").options).get(value, value)
    return f"{label} (`{value}`)"


def _count(value) -> str:
    return str(int(value))


def _sector_fallback() -> str:
    return (f"when two tickers have fewer than {correlation.MIN_OVERLAP_BARS} overlapping "
            "daily returns, sharing a sector counts as correlated")


def _gap_basis(on: bool, gap_word: str, minimum: int) -> str:
    if not on:
        return "the stop distance only"
    p_rule = gap_sizing.RULE_GAP.removeprefix("gap_")
    return (f"the larger of the stop distance and entry × the ticker's {p_rule} {gap_word} "
            f"over the last {gap_sizing.LOOKBACK} completed bars "
            f"(needs at least {minimum} {gap_word}s)")


def _gap_table() -> str:
    short_on, long_on = bool(config.SHORT_GAP_SIZING), bool(config.LONG_GAP_SIZING)
    rows = [
        "| Side | Gap-aware sizing | Sized on |",
        "|---|---|---|",
        f"| Short | {_flag(short_on)} | {_gap_basis(short_on, 'up-gap', gap_sizing.MIN_UP_GAPS)} |",
        f"| Long | {_flag(long_on)} | {_gap_basis(long_on, 'down-gap', gap_sizing.MIN_DOWN_GAPS)} |",
    ]
    note = ("With fewer gaps on record the plan is sized on the stop. The stop itself never "
            "moves and R is always measured on the stop; only the share count can shrink.")
    return "\n".join(rows) + "\n\n" + note


def _bot_version() -> str:
    from swingbot.admin import helpers   # call time: tests/admin/conftest.py reloads helpers
    return str(helpers.get_versions()["bot"])


RISK_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "MAX_STOP_LOSS_PCT": _cfg_pct("MAX_STOP_LOSS_PCT"),
    "MIN_STOP_DISTANCE_PCT": _cfg_pct("MIN_STOP_DISTANCE_PCT"),
    "CLAMP_STOP_TO_HARD_CAP": lambda: _flag(config.CLAMP_STOP_TO_HARD_CAP),
    "RISK_PER_TRADE_PCT": _from_account("risk_pct", _pct),
    "RISK_PER_TRADE_PCT.max": _risk_max,
    "MAX_RISK_AMOUNT_ABSOLUTE": _from_account("max_risk_amount_absolute", _money),
    "PORTFOLIO_HEAT_CAP_PCT": _cfg_pct("PORTFOLIO_HEAT_CAP_PCT"),
    "CORRELATED_HEAT_CAP_PCT": _cfg_pct("CORRELATED_HEAT_CAP_PCT"),
    "SECTOR_HEAT_CAP_PCT": _cfg_pct("SECTOR_HEAT_CAP_PCT"),
    "POSITION_SIZING_MODE": _from_account("sizing_mode", _mode_text),
    "correlation.threshold": lambda: _num(correlation.DEFAULT_THRESHOLD),
    "correlation.window": lambda: f"{correlation.DEFAULT_WINDOW} trading days",
    "correlation.sector_fallback": _sector_fallback,
    "sizing.kelly_cap": lambda: f"{_num(sizing.KELLY_FRACTION_CAP)} of full Kelly",
    "sizing.risk_floor": lambda: _pct(sizing.RISK_FLOOR_PCT),
    "sizing.risk_ceiling": lambda: _pct(sizing.RISK_CEILING_PCT),
    "sizing.gap": _gap_table,
    "version.bot": _bot_version,
    "MAX_POSITION_SIZE_PCT": _from_account("max_position_pct", _pct),
    "MAX_POSITION_VALUE_ABSOLUTE": _from_account("max_position_value_absolute", _money),
    "MAX_OPEN_POSITIONS": _from_account("max_open_positions", _count),
}
