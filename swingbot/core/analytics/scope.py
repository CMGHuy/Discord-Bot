"""One scope for every analytics route (spec v94 D2/D5).

Parsed once per request, applied by every `/analytics/*` route, echoed in
every scoped payload -- so the frontend sends one query string everywhere and
can prove which population each panel shows. Pure: no Flask here; the route
layer converts `ScopeError` into its 400.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from swingbot.core.analytics import metrics as m
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.tracking.performance import primary_strategy_label

SCOPE_PARAMS = ("from", "to", "ledger", "strategy", "horizon", "direction")
LEDGERS = ("main", "weak", "both")
DIRECTIONS = ("bullish", "bearish")
CLOSED_STATUSES = ("win", "loss", "closed")


class ScopeError(ValueError):
    """A malformed scope parameter. Never a silently-dropped filter."""


@dataclass(frozen=True)
class BookScope:
    start: str | None = None
    end: str | None = None
    ledger: str = "main"
    strategy: str | None = None
    horizon: str | None = None
    direction: str | None = None


def _day(args: Mapping[str, str], name: str) -> str | None:
    raw = (args.get(name) or "").strip()
    if not raw:
        return None
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise ScopeError(f"{name} must be a YYYY-MM-DD date")
    return raw


def _choice(args: Mapping[str, str], name: str, allowed: tuple[str, ...], default: str | None) -> str | None:
    raw = (args.get(name) or "").strip()
    if not raw:
        return default
    if raw not in allowed:
        raise ScopeError(f"{name} must be one of {list(allowed)}, got {raw!r}")
    return raw


def parse_scope(args: Mapping[str, str]) -> BookScope:
    start, end = _day(args, "from"), _day(args, "to")
    if start and end and start > end:
        raise ScopeError("from must not be after to")
    return BookScope(
        start=start, end=end,
        ledger=_choice(args, "ledger", LEDGERS, "main") or "main",
        strategy=(args.get("strategy") or "").strip() or None,
        horizon=_choice(args, "horizon", tuple(HORIZONS), None),
        direction=_choice(args, "direction", DIRECTIONS, None),
    )


def reject_unknown(args: Mapping[str, str], extra: tuple[str, ...] = ()) -> None:
    allowed = set(SCOPE_PARAMS) | set(extra)
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise ScopeError(f"unknown parameter {unknown[0]!r}; allowed: {sorted(allowed)}")


def closed_only(trades: list[dict]) -> list[dict]:
    return [t for t in trades if t.get("status") in CLOSED_STATUSES]


def select(closed: list[dict], scope: BookScope) -> list[dict]:
    out = m.in_date_range(closed, start=scope.start, end=scope.end)
    if scope.ledger != "both":
        out = [t for t in out if (t.get("ledger") or "main") == scope.ledger]
    if scope.strategy:
        out = [t for t in out if primary_strategy_label(t) == scope.strategy]
    if scope.horizon:
        out = [t for t in out if t.get("horizon_key") == scope.horizon]
    if scope.direction:
        out = [t for t in out if t.get("direction") == scope.direction]
    return out


def echo(scope: BookScope, n: int) -> dict:
    return {"scope": {"from": scope.start, "to": scope.end, "ledger": scope.ledger,
                      "strategy": scope.strategy, "horizon": scope.horizon,
                      "direction": scope.direction}, "n": n}
