"""v239: GET /market/regime -- the bear-regime day for the next session, the last 60
stored sessions and the confirmed episode, in the shared vocabulary. Read-only: the
admin process never fetches market data or computes a label (index decision 5). Core
imports live inside the functions (the circular-import note in api_v1/__init__.py).
"""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from flask import jsonify

from . import api_v1, iso
from .auth import require_auth

log = logging.getLogger(__name__)

HISTORY_LIMIT = 60
#: Stored rows read for the episode's "since" count (about two years of sessions),
#: so an episode longer than the 60-row history still counts from its first day.
EPISODE_ROWS = 500


def _empty(mode: str) -> dict:
    return {"mode": mode, "today": None, "history": [], "episode": None}


def _wire(row: Mapping) -> dict:
    from swingbot.core.market import bear_regime as br
    from swingbot.core.presentation import regime_text

    day = br.RegimeDay.from_row(row)
    wire = {name: getattr(day, name) for name in br.ROW_COLUMNS}
    for name in ("session_date", "last_bar_date"):
        wire[name] = None if wire[name] is None else wire[name].isoformat()
    return {**wire, "computed_at": iso(row.get("computed_at")), "display": regime_text.display(day)}


def _episode(rows: Sequence[Mapping]) -> dict | None:
    from swingbot.core.market import bear_regime as br
    from swingbot.core.market import regime_episodes as ep
    from swingbot.core.presentation import regime_text

    days = [(br.RegimeDay.from_row(row).session_date, ep.episode_key(row["state"], row.get("stress")))
            for row in rows]
    current = ep.current_episode(days)
    if current is None:
        return None
    return {"label": regime_text.LABELS[current.key], "since_sessions": current.sessions}


def regime_payload(now: datetime | None = None, repo=None) -> dict:
    """The /market/regime body. `off` (or an unknown mode) reads nothing; an
    unreadable store answers the empty shape, never a stale label."""
    from swingbot.core.db.repositories import market_regime as regime_repo
    from swingbot.core.infra.swallowed import swallowed
    from swingbot.core.scanning import regime_calendar
    from swingbot.core.scanning.regime_scan import regime_mode

    mode = regime_mode()
    if mode == "off":
        return _empty("off")
    try:
        rows = list((repo or regime_repo.market_regime_repo()).recent(EPISODE_ROWS))
        _, target = regime_calendar.session_pair(now or datetime.now(timezone.utc))
    except Exception as exc:
        swallowed(log, "admin.market_regime.read", exc, "regime: store or calendar unreadable: %s", exc)
        return _empty(mode)
    history = [_wire(row) for row in rows[-HISTORY_LIMIT:]]
    today = next((day for day in history if day["session_date"] == target.isoformat()), None)
    return {"mode": mode, "today": today, "history": history, "episode": _episode(rows)}


@api_v1.route("/market/regime", methods=["GET"])
@require_auth
def market_regime_view():
    return jsonify(regime_payload())
