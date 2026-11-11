"""v218 P3-c: weak ETag and 304 for allow-listed admin GET views.

``@conditional(route_key, admit)`` sits under ``@require_auth`` (a 401 never
reaches it) and above ``@read_scope`` (a 304 opens no scope and builds
nothing). The tag is computed **before** the view runs, from its inputs
alone: the build, the store generations, the plans/trades/journal
``version()`` tuples (read once per request, shared with the snapshot), the
FX daily table's version, the normalised query, the Berlin date and the
principal. A matching ``If-None-Match`` returns a bodiless 304, which skips
the route's work as well as its bytes. A 200 carries the tag and
``Cache-Control: private, no-cache``; any other status carries neither.

No tag at all -- the view runs exactly as before -- when the switch
``ADMIN_STORE_SNAPSHOT`` is off, the snapshot listener is not connected, the
client sent ``X-Swingbot-Fresh: 1``, ``admit(request.args)`` says no, or any
input raises (logged once through ``swallowed``). Which views carry the
decorator is pinned exactly by tests/admin_perf/test_conditional_routes.py.
"""
from __future__ import annotations

import functools
import hashlib
import logging
from typing import Callable, TypeVar
from urllib.parse import urlencode

from flask import make_response, request
from werkzeug.datastructures import MultiDict

from swingbot import config
from swingbot.admin import build_identity
from swingbot.core.infra import store_generation, store_snapshot
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata import fx_convert

log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)

CONDITIONAL_ATTR = "__conditional__"
CACHE_CONTROL = "private, no-cache"
_TAG_HEX = 32


def normalised_query(args: MultiDict) -> str:
    """Every (key, value) pair, sorted, url-encoded: order never changes the tag."""
    return urlencode(sorted(args.items(multi=True)))


def _fx_version() -> tuple:
    from swingbot.core.db.repositories.market_refresh import fx_daily_rate_repo
    return fx_daily_rate_repo().version()


def _principal() -> tuple:
    """(role, username, user_id); a Basic-auth caller passed require_auth as the admin."""
    from swingbot.admin import app as _app
    who = _app.resolve_principal()
    if who is not None:
        return (who.get("role"), who.get("username"), who.get("user_id"))
    auth = request.authorization
    return ("admin", auth.username if auth else None, None)


def etag_inputs(route_key: str, args: MultiDict) -> tuple:
    """Exactly the documented inputs, in a fixed order."""
    return (route_key, build_identity.build_version(), store_generation.token(),
            store_snapshot.request_versions(), _fx_version(), normalised_query(args),
            fx_convert.berlin_today().isoformat(), _principal())


def _eligible() -> bool:
    from swingbot.admin.freshness import FRESH_HEADER
    return (config.ADMIN_STORE_SNAPSHOT == "on" and store_generation.connected()
            and request.headers.get(FRESH_HEADER) != "1")


def compute_etag(route_key: str, args: MultiDict) -> str | None:
    """``W/"<32 hex>"``, or None when ineligible or when any input raises."""
    try:
        if not _eligible():
            return None
        digest = hashlib.sha256(repr(etag_inputs(route_key, args)).encode("utf-8")).hexdigest()
    except Exception as exc:
        swallowed(log, "ops.admin.etag", exc)
        return None
    return f'W/"{digest[:_TAG_HEX]}"'


def _opaque(tag: str) -> str:
    tag = tag.strip()
    return tag[2:] if tag.startswith("W/") else tag


def if_none_match_hits(header: str | None, tag: str) -> bool:
    """True for ``*`` or any listed tag equal to ``tag``, weak or strong form."""
    if not header:
        return False
    want = _opaque(tag)
    return any(part.strip() == "*" or _opaque(part) == want for part in header.split(","))


def _admitted(admit: Callable[[MultiDict], bool]) -> bool:
    try:
        return bool(admit(request.args))
    except Exception as exc:
        swallowed(log, "ops.admin.etag", exc)
        return False


def _with_tag(response, tag: str):
    response.headers["ETag"] = tag
    response.headers["Cache-Control"] = CACHE_CONTROL
    return response


def conditional(route_key: str, admit: Callable[[MultiDict], bool]) -> Callable[[F], F]:
    """Weak ETag / 304 for one GET view; place it under @require_auth, above @read_scope."""

    def decorate(view: F) -> F:
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            tag = compute_etag(route_key, request.args) if _admitted(admit) else None
            if tag is not None and if_none_match_hits(request.headers.get("If-None-Match"), tag):
                return _with_tag(make_response("", 304), tag)
            response = make_response(view(*args, **kwargs))
            if tag is not None and response.status_code == 200:
                _with_tag(response, tag)
            return response

        setattr(wrapper, CONDITIONAL_ATTR, route_key)
        return wrapper  # type: ignore[return-value]

    return decorate
