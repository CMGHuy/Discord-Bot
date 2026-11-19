"""v235: market placeholders for the guide -- level families, the cluster
tolerance, the horizon table, per-strategy gates and alerts per week -- plus
the registered strategy keys Plan B's cards are checked against.

Masks are read at call time through live_horizons() and admits(), never from
a hard-coded horizon, so a cell shipped in code shows up here with no edit.
alerts.per_week reads the live paper book and always carries its provenance.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from swingbot import config
from swingbot.admin.guide.chapters import anchor_for
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import levels, strategy_types

log = logging.getLogger(__name__)

_WEEKS = 8
_MASKED = "masked — research only"
_NONE = "—"
_ALL_LIVE = "every live horizon"
_DIRECTIONS = ("bullish", "bearish")   # table columns Long, Short


def _load_trades() -> list[dict]:
    """Every live paper trade (patched in tests; the real read needs the database)."""
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status=None, limit=None, sort_by="opened_at") or []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def registered_strategy_keys() -> tuple[str, ...]:
    """Sorted union of the signal functions and the gate table's keys."""
    from swingbot.core.market.strategy import STRATEGY_FUNCS
    return tuple(sorted(set(STRATEGY_FUNCS) | set(strategy_types.STRATEGY_GATES)))


def strategy_file_slug(key: str) -> str:
    """The docs/guide/strategies/<slug>.md name for a strategy key (anchor rule)."""
    return anchor_for(key, {})


def _family_line(name: str) -> str:
    if name != "AVWAP":
        return f"- {name}"
    state = "on" if config.AVWAP_LEVELS_ENABLED else "off"
    return f"- {name} (only when `AVWAP_LEVELS_ENABLED`; currently {state})"


def _families() -> str:
    return "\n".join(_family_line(name) for name in levels.ALL_STRATEGY_FAMILIES)


def _horizon_row(key: str, live: set[str]) -> str:
    spec = strategy_types.HORIZONS[key]
    status = "live" if key in live else _MASKED
    return f"| `{key}` | {spec['label']} | {spec['max_holding_days']} days | {status} |"


def _horizons_table() -> str:
    live = set(strategy_types.live_horizons())
    rows = ["| Horizon | Swing | Longest hold | Status |", "|---|---|---|---|"]
    rows += [_horizon_row(key, live) for key in strategy_types.horizon_order()]
    return "\n".join(rows)


def _side_cell(strategy: str, direction: str, live: tuple[str, ...]) -> str:
    admitted = tuple(hk for hk in strategy_types.horizon_order()
                     if strategy_types.admits(strategy, direction, hk))
    if not admitted:
        return _NONE
    return _ALL_LIVE if admitted == live else ", ".join(admitted)


def _gate_row(strategy: str, live: tuple[str, ...]) -> str:
    cells = [_side_cell(strategy, direction, live) for direction in _DIRECTIONS]
    status = _MASKED if all(cell == _NONE for cell in cells) else "live"
    return f"| {strategy} | {cells[0]} | {cells[1]} | {status} |"


def _gates_list() -> str:
    live = tuple(strategy_types.live_horizons())
    rows = ["| Strategy | Long | Short | Status |", "|---|---|---|---|"]
    rows += [_gate_row(key, live) for key in registered_strategy_keys()]
    return "\n".join(rows)


def _week_start(moment: datetime) -> datetime:
    day = moment.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=day.weekday())


def _opened(trade: dict) -> datetime | None:
    raw = trade.get("opened_at")
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _count_in_window(trades: list[dict], start: datetime, end: datetime) -> int:
    stamps = (_opened(trade) for trade in trades)
    return sum(1 for stamp in stamps if stamp is not None and start <= stamp < end)


def _alerts_per_week() -> str:
    from swingbot.admin.guide.placeholders import provenance_label   # placeholders imports us
    try:
        trades = _load_trades()
    except Exception as exc:  # the guide renders without the database
        swallowed(log, "ops.admin.guide.alerts_per_week", exc,
                  "guide: live paper book unreadable: %s", exc)
        return "not available right now (the live paper book could not be read)"
    now = _now()
    end = _week_start(now)
    count = _count_in_window(trades, end - timedelta(weeks=_WEEKS), end)
    label = provenance_label(source="live paper book", n=count,
                             run_date=now.date().isoformat(), costs_included=False)
    if count == 0:
        return f"no live alerts in the last {_WEEKS} weeks ({label})"
    return f"{count / _WEEKS:.1f} alerts a week, mean of the last {_WEEKS} full weeks ({label})"


MARKET_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "levels.families": _families,
    "CLUSTER_TOLERANCE_PCT": lambda: f"{levels.CLUSTER_TOLERANCE_PCT:g}%",
    "horizons.table": _horizons_table,
    "gates.list": _gates_list,
    "alerts.per_week": _alerts_per_week,
}
