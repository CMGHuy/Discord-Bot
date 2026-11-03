"""GET /api/v1/live: the shell's Live dock in one DB-only read (v202).

Heat is the Risk page's own definition (`portfolio_state.open_heat_state`).
Postgres only: no market-data provider, no `collect_portfolio_state`. Each
section catches its own failure and answers `availability: "unavailable"`
with its keys kept as null, so a failed read never passes for zero heat.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import jsonify, request

from swingbot.core.infra.swallowed import swallowed

from . import api_v1, error, iso
from .auth import require_auth

log = logging.getLogger(__name__)

DEFAULT_LIMIT = 8
MAX_LIMIT = 50

_HEAT_KEYS = ("open_pct", "cap_pct", "utilisation_pct", "open_amount", "cap_amount",
              "headroom_pct", "headroom_amount", "balance")
_HEAT_EMPTY = {**{key: None for key in _HEAT_KEYS}, "includes_resting": True}
_AWAITING_EMPTY = {"count": None, "next_expiry": None}
_KILLSWITCH_EMPTY = {"engaged": None, "since": None, "detail": None}


def parse_limit(raw: str | None) -> int | None:
    """`?limit=`: absent -> DEFAULT_LIMIT, clamped to MAX_LIMIT; None when invalid."""
    if raw is None or raw == "":
        return DEFAULT_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return min(value, MAX_LIMIT) if value >= 1 else None


def _section(as_of: str, values: dict, reason: str | None = None) -> dict:
    state = "ok" if reason is None else "unavailable"
    return {"availability": state, "as_of": as_of, "reason": reason, **values}


def _guarded(name: str, read, empty: dict, now: datetime) -> dict:
    """`read()`'s values as an ok section, or `<name>_unavailable` with `empty`."""
    as_of = iso(now)
    try:
        return _section(as_of, read())
    except Exception as exc:
        swallowed(log, f"ops.live.{name}", exc, level=logging.WARNING)
        return _section(as_of, empty, f"{name}_unavailable")


def _heat_figures(open_pct: float, cap_pct: float, balance: float) -> dict:
    """Dollars beside percent; utilisation and headroom deliberately unclamped."""
    cap = float(cap_pct)
    open_amount = round(open_pct / 100.0 * balance, 2)
    cap_amount = round(cap / 100.0 * balance, 2)
    return {
        "open_pct": open_pct, "cap_pct": cap,
        "utilisation_pct": round(open_pct / cap * 100.0, 1) if cap else None,
        "open_amount": open_amount, "cap_amount": cap_amount,
        "headroom_pct": round(cap - open_pct, 2),
        "headroom_amount": round(cap_amount - open_amount, 2),
        "balance": round(balance, 2), "includes_resting": True,
    }


def heat_section(now: datetime) -> dict:
    from swingbot.core.edge.portfolio_state import open_heat_state
    as_of = iso(now)
    try:
        state = open_heat_state(as_of)
    except Exception as exc:
        swallowed(log, "ops.live.heat", exc, level=logging.WARNING)
        return _section(as_of, _HEAT_EMPTY, "heat_unavailable")
    status = state.get("availability") or {}
    if status.get("state") != "ok":
        return _section(as_of, _HEAT_EMPTY, status.get("reason") or "heat_unavailable")
    return _section(as_of, _heat_figures(state["open_heat"], state["heat_cap"], state["balance"]))


def _sections(now: datetime) -> dict:
    """V202-1b replaces the two placeholders with the real sections."""
    as_of = iso(now)
    return {"heat": heat_section(now),
            "awaiting": _section(as_of, _AWAITING_EMPTY, "not wired"),
            "killswitch": _section(as_of, _KILLSWITCH_EMPTY, "not wired")}


def _events(limit: int, now: datetime) -> tuple[list, dict]:
    """Placeholder until V202-3 wires `live_events.collect_events`."""
    return [], {"availability": "unavailable", "as_of": iso(now), "missing": [],
                "reason": "not wired"}


@api_v1.route("/live", methods=["GET"])
@require_auth
def get_live():
    """The Live dock in one read; the shape is `LiveSnapshot` in models.ts."""
    limit = parse_limit(request.args.get("limit"))
    if limit is None:
        return error("invalid", "limit must be a whole number of at least 1.", 400)
    now = datetime.now(timezone.utc)
    events, meta = _events(limit, now)
    return jsonify({**_sections(now), "events": events, "events_meta": meta})
