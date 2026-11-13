"""v227: ``GET /feed-posts`` and ``GET /feed-posts/kinds`` -- what the site speaks.

``/feed-posts`` pages the simple-channel post log (feed_posts) after an id,
oldest first; with no ``after`` it returns only ``latest_id``, which is how a
freshly opened tab starts without a backlog. ``/feed-posts/kinds`` lists the
toggleable kinds per family, with the spoken phrase and a sample, so the
Settings block never hard-codes the registry.

Imports of the repository, the side engine and the presentation registry live
inside the functions (the circular-import note in ``api_v1/__init__.py``).
"""
from __future__ import annotations

import sqlalchemy as sa
from flask import jsonify, request

from swingbot.core.db.engine import DatabaseUnavailable

from . import ApiError, api_v1, iso
from .auth import require_auth

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def _int_arg(name: str, default: int | None) -> int | None:
    raw = request.args.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise ApiError("invalid", f"{name} must be an integer", 400) from None


def _limit() -> int:
    limit = _int_arg("limit", DEFAULT_LIMIT)
    if limit < 1:
        raise ApiError("invalid", "limit must be at least 1", 400)
    return min(limit, MAX_LIMIT)


def _latest() -> int:
    from swingbot.core.db import side_engine
    from swingbot.core.db.repositories.feed_posts import feed_posts_repo
    with side_engine.side_connection() as conn:
        return feed_posts_repo().latest_id(conn=conn)


def _page(after: int, limit: int) -> list[dict]:
    from swingbot.core.db import side_engine
    from swingbot.core.db.repositories.feed_posts import feed_posts_repo
    with side_engine.side_connection() as conn:
        return feed_posts_repo().after(after, limit, conn=conn)


def _family(kind_name: str) -> str | None:
    from swingbot.core.presentation.kinds import Kind
    member = Kind.__members__.get(kind_name)
    return member.family.name if member is not None else None


def _item(row: dict) -> dict:
    return {"id": row["id"], "posted_at": iso(row["posted_at"]), "kind": row["kind"],
            "family": _family(row["kind"]), "ticker": row["ticker"], "headline": row["headline"]}


@api_v1.route("/feed-posts", methods=["GET"])
@require_auth
def feed_posts_view():
    after = _int_arg("after", None)
    limit = _limit()
    try:
        latest = _latest()   # before the page: a row landing in between is never skipped
        rows = [] if after is None else _page(after, limit)
    except (DatabaseUnavailable, sa.exc.OperationalError, sa.exc.InterfaceError):
        raise ApiError("unavailable", "feed posts are unavailable right now", 503) from None
    return jsonify({"items": [_item(row) for row in rows], "latest_id": latest})


def _kinds_payload() -> list[dict]:
    from swingbot.core.presentation.feed_headline import FEED_FAMILIES, kind_phrase, sample_headline
    from swingbot.core.presentation.kinds import Family, Kind
    return [{"family": family.name, "label": family.label.capitalize(),
             "default_on": family is not Family.WATCH,
             "kinds": [{"kind": kind.name, "label": kind.label, "phrase": kind_phrase(kind),
                        "sample": sample_headline(kind)}
                       for kind in Kind if kind.family is family]}
            for family in FEED_FAMILIES]


@api_v1.route("/feed-posts/kinds", methods=["GET"])
@require_auth
def feed_post_kinds_view():
    return jsonify({"families": _kinds_payload()})
