"""v201: ``GET /market/updates``, ``POST /market/refresh`` and the refresher health block.

Thin endpoints over the never-fetch door (``swingbot.admin.market_values``) and
the refresh repositories. Nothing here fetches: updates reads the cache and the
in-flight marks, and refresh only enqueues work for the refresher process.

Imports of ``swingbot.admin`` and the repositories live inside the functions
(the circular-import note in ``api_v1/__init__.py``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from flask import jsonify, request

from swingbot.core.infra.swallowed import swallowed

from . import ApiError, api_v1, iso
from .auth import require_auth

log = logging.getLogger(__name__)

MAX_REFRESH_SYMBOLS = 200
_QUOTE_PREFIX = "quote:"


def _parse_since(raw: str | None) -> datetime | None:
    if raw is None or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ApiError("invalid", "since must be an ISO-8601 timestamp", 400) from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _cache_changes(since: datetime) -> list[dict]:
    from swingbot.core.db.repositories.market_shared import market_shared_repo
    from swingbot.core.db.side_engine import side_connection
    from swingbot.core.marketdata.shared.kinds import DataKind
    repo = market_shared_repo()
    with side_connection() as conn:
        rows: list[dict] = []
        for kind in (DataKind.QUOTE, DataKind.INDEX_QUOTE):
            rows.extend(repo.changed_since(kind.value, since, conn=conn))
        return rows


def _mark_changes(since: datetime) -> list[dict]:
    try:
        from swingbot.core.db.repositories import market_refresh
        return list(market_refresh.refresh_mark_repo().changed_since(since))
    except Exception as exc:  # noqa: BLE001 - fail open: updates carry no mark changes
        swallowed(log, "ops.admin.market_updates.marks", exc, "mark changes unreadable: %s", exc)
        return []


def _changed_symbols(rows: list[dict], marks: list[dict]) -> list[str]:
    symbols = {row["symbol"] for row in rows if row.get("symbol")}
    symbols |= {m["key"][len(_QUOTE_PREFIX):] for m in marks
                if str(m.get("key", "")).startswith(_QUOTE_PREFIX)}
    return sorted(symbols)


def _quote_updates(since: datetime, marks: list[dict]) -> list[dict]:
    from swingbot.admin import market_values
    from swingbot.core.marketdata.shared import tape
    from swingbot.core.marketdata.shared.kinds import DataKind
    try:
        rows = _cache_changes(since)
    except Exception as exc:  # noqa: BLE001 - fail open: marks alone still tell the SPA
        swallowed(log, "ops.admin.market_updates.cache", exc, "cache changes unreadable: %s", exc)
        rows = []
    symbols = _changed_symbols(rows, marks)
    tape_syms = [s for s in symbols if tape.is_tape_symbol(s)]
    plain = [s for s in symbols if s not in set(tape_syms)]
    quotes = market_values.read_quotes(plain, kind=DataKind.QUOTE, enqueue=False)
    quotes.update(market_values.read_quotes(tape_syms, kind=DataKind.INDEX_QUOTE,
                                            enqueue=False))
    return [{"symbol": s, "price": quotes[s].price, "as_of": quotes[s].as_of,
             "refreshing": quotes[s].refreshing, "error": quotes[s].error}
            for s in symbols if s in quotes]


def _heartbeat_row() -> dict | None:
    try:
        from swingbot.core.db.repositories import market_refresh
        return market_refresh.refresher_heartbeat_repo().read()
    except Exception as exc:  # noqa: BLE001 - fail open to "no row"
        swallowed(log, "ops.admin.market_updates.heartbeat", exc, "heartbeat unreadable: %s", exc)
        return None


def status_block(now: datetime | None = None) -> dict:
    from swingbot.core.market import session
    from swingbot.core.marketdata.shared import admin_refresh
    now = now or datetime.now(timezone.utc)
    state = session.session_state(now)
    row = _heartbeat_row() or {}
    beat_at = row.get("beat_at")
    cadence = row.get("cadence_s") or admin_refresh.cadence_s(state)
    stalled = admin_refresh.refresher_on() and admin_refresh.heartbeat_stalled(
        beat_at, cadence, now)
    return {
        "session": state,
        "last_close_at": iso(session.last_regular_close(now)),
        "stale_price_s": admin_refresh.stale_after_s("price", state),
        "heartbeat": {"beat_at": iso(beat_at), "cadence_s": cadence,
                      "stalled": bool(stalled)},
    }


def refresher_health() -> dict:
    from swingbot.core.market import session
    from swingbot.core.marketdata.shared import admin_refresh
    if not admin_refresh.refresher_on():
        return {"status": "off", "beat_at": None, "cadence_s": None, "last_error": None}
    row = _heartbeat_row() or {}
    beat_at = row.get("beat_at")
    cadence = row.get("cadence_s") or admin_refresh.cadence_s(session.session_state())
    stalled = admin_refresh.heartbeat_stalled(beat_at, cadence)
    return {"status": "stalled" if stalled else "ok", "beat_at": iso(beat_at),
            "cadence_s": cadence, "last_error": row.get("last_error")}


def _validated_refresh(payload: Any) -> list[str]:
    symbols = payload.get("symbols") if isinstance(payload, dict) else None
    if not isinstance(symbols, list) or not symbols:
        raise ApiError("invalid", "symbols must be a non-empty list of strings", 400)
    if not all(isinstance(s, str) for s in symbols):
        raise ApiError("invalid", "symbols must be a non-empty list of strings", 400)
    if len(symbols) > MAX_REFRESH_SYMBOLS:
        raise ApiError("invalid", f"at most {MAX_REFRESH_SYMBOLS} symbols per request", 400)
    return symbols


@api_v1.route("/market/updates", methods=["GET"])
@require_auth
def market_updates_view():
    now = datetime.now(timezone.utc)
    since = _parse_since(request.args.get("since"))
    quotes = _quote_updates(since, _mark_changes(since)) if since else []
    return jsonify({"cursor": iso(now), "quotes": quotes, "status": status_block(now)})


@api_v1.route("/market/refresh", methods=["POST"])
@require_auth
def refresh_view():
    from swingbot.admin import market_values
    symbols = _validated_refresh(request.get_json(silent=True))
    return jsonify({"queued": market_values.request_refresh(symbols)}), 202
