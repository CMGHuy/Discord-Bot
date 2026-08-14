"""The /api/v1 blueprint — the SPA's contract with the server.

Spec: `docs/superpowers/specs/implemented/2026-08-08-v11-admin-rest-api-design.md`.

This package began as the SPA-facing half of a two-namespace split: a legacy
`swingbot/admin/api.py` served the Jinja UI's `/api/*` while `/api/v1/*` was
designed for the SPA without being bent around what the old `dashboard.js`
expected. Release B (2026-08-14) deleted the Jinja UI and `api.py` with it,
so this is now the admin's ONLY API namespace.

This module holds only what every endpoint shares — the error shape, the
collection envelope, timestamp rendering, and query-parameter parsing.
Endpoints live in sibling modules (`trades.py`, `dashboard.py`, ...) and are
registered onto `api_v1` below.

Auth lives in `auth.py`, which reaches `swingbot.admin.app` as a MODULE and
reuses `_session_authenticated` rather than reimplementing the predicate, so
there is exactly one Basic/session auth path in the admin.

**This module imports nothing from the rest of `swingbot.admin`, and must
not start.** app.py registers its blueprints at the bottom of its own body,
after every name they import from it exists. Keeping this module free of
admin imports is what lets a test (or any endpoint module) import these
helpers directly without tripping the circular-import deadlock app.py
documents. Endpoint modules take on that constraint instead; they are
imported from app.py's bottom, where the ordering is already sound.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from flask import Blueprint, jsonify, request

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 200

# Reserved by the collection convention, so they are never mistaken for
# filters and never need declaring by an endpoint.
_RESERVED_PARAMS = frozenset({"page", "per_page", "sort"})


class ApiError(Exception):
    """A failure with a stable machine-readable `code`.

    Raised anywhere inside a v1 request and converted to the spec's error
    body by the handler `register()` installs. Endpoints raise this instead
    of returning error tuples so that parsing helpers, which have no way to
    return a Flask response, fail the same way handlers do.
    """

    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def error(code: str, message: str, status: int):
    """The one error body: `{"error": {"code", "message"}}`.

    `code` is stable and may be branched on by the client; `message` is for
    humans and may change freely.
    """
    return jsonify({"error": {"code": code, "message": message}}), status


def collection(items: list, total: int, page: int, per_page: int) -> dict:
    """The one collection envelope.

    `total` is the count AFTER filtering but BEFORE slicing -- the contract
    `_query_closed_trades()` already implements, generalised rather than
    reinvented. Passing `len(items)` here silently produces a one-page
    result set, so callers must pass the pre-slice count.
    """
    return {"items": items, "total": total, "page": page, "per_page": per_page}


def iso(value: datetime | None) -> str | None:
    """ISO-8601 UTC *with* offset, or None.

    Naive datetimes are treated as UTC rather than rejected: older records
    in this codebase carry them, and handing the SPA an offset-less string
    would make it guess. `None` passes through so callers can render an
    absent timestamp without branching.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class CollectionParams:
    page: int = 1
    per_page: int = DEFAULT_PER_PAGE
    sort: tuple[str, str] | None = None
    filters: dict[str, str] = field(default_factory=dict)


def _positive_int(raw: str, name: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ApiError("invalid", f"{name} must be a positive integer", 400)
    if value < 1:
        raise ApiError("invalid", f"{name} must be a positive integer", 400)
    return value


def parse_collection_params(
    args: Mapping[str, Any],
    *,
    allowed_filters: Iterable[str],
    sortable: Iterable[str],
) -> CollectionParams:
    """Parse paging, sort and filters, or raise ApiError(400).

    An unrecognised parameter is rejected rather than ignored. A silently
    ignored filter is how a filter that has stopped working survives to
    production -- the caller sees results, just not the ones it asked for.
    """
    allowed_filters = set(allowed_filters)
    sortable = set(sortable)

    page = _positive_int(args["page"], "page") if args.get("page") else 1
    per_page = (
        min(_positive_int(args["per_page"], "per_page"), MAX_PER_PAGE)
        if args.get("per_page")
        else DEFAULT_PER_PAGE
    )

    sort: tuple[str, str] | None = None
    raw_sort = args.get("sort")
    if raw_sort:
        descending = raw_sort.startswith("-")
        field_name = raw_sort[1:] if descending else raw_sort
        if field_name not in sortable:
            raise ApiError(
                "invalid",
                f"cannot sort by {field_name!r}; sortable: {sorted(sortable)}",
                400,
            )
        sort = (field_name, "desc" if descending else "asc")

    filters: dict[str, str] = {}
    for key, value in args.items():
        if key in _RESERVED_PARAMS:
            continue
        if key not in allowed_filters:
            raise ApiError(
                "invalid",
                f"unknown parameter {key!r}; allowed: {sorted(allowed_filters)}",
                400,
            )
        if value != "" and value is not None:
            filters[key] = value

    return CollectionParams(page=page, per_page=per_page, sort=sort, filters=filters)


def register(app) -> None:
    """Mount the blueprint and install the two v1 error handlers.

    The 404 handler must be APP-level, not blueprint-level: an unmatched URL
    never reaches a blueprint, so a blueprint handler would leave the SPA
    parsing Flask's HTML error page. It scopes itself to /api/v1 by path so
    the Jinja UI's own 404s stay HTML until cutover -- changing those would
    be a live-UI change, which this migration does not make.
    """
    # Endpoint modules are imported HERE, not at this module's top level.
    # They import from swingbot.admin.app, which is only safely
    # importable once app.py's body has run -- and register() is called from
    # app.py's bottom, which is exactly that point. Importing them above
    # would drag those modules in at api_v1 import time and re-create the
    # circular-import deadlock app.py documents.
    from . import (analytics, dashboard, jobs, market, risk,  # noqa: F401
                   session, system, trade_commands, trades,
                   watchlist)  # (register routes)
    # /api/v1/events lives outside this package -- it is one route on top of
    # the watcher and broker, and splitting those across two packages to put
    # the route here would be filing by framework rather than by concern.
    from swingbot.admin.events import stream  # noqa: F401  (registers /events)

    app.register_blueprint(api_v1)

    @app.errorhandler(ApiError)
    def _handle_api_error(exc: ApiError):
        return error(exc.code, exc.message, exc.status)

    @app.errorhandler(404)
    def _handle_not_found(exc):
        if request.path.startswith("/api/v1"):
            return error("not_found", request.path, 404)
        return exc
