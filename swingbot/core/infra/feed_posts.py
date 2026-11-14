"""v227: record each accepted simple-channel post for the site's voice notifications.

Called by the two simple-channel senders right after ``log_posted``, inside the
send's ``try``, so a row exists only for a message Discord accepted
(swingbot/commands/scanning/alerts.py:_mirror and the feed branch of
swingbot/core/scanning/lifecycle_embeds.py:_send_instruction).

Never raises, and never holds the bot loop longer than the side engine's
statement timeout: the insert runs on swingbot.core.db.side_engine (autocommit,
fail-fast, its own tiny pool), never the main pool. It stays synchronous on
purpose -- the bot process is the only writer, so id order is commit order and
``GET /feed-posts?after=<id>`` never skips a row; a thread would break that.

``FEED_POSTS_ENABLED`` off returns before any work. The prune runs at most once
per ``PRUNE_EVERY_S`` per process (an in-process clock, not a scheduled job).

The presentation registry and the repository are imported inside the functions:
core/infra keeps no module-level import of presentation (the cycle
posted_log.py avoids).
"""
from __future__ import annotations

import logging
import time

from swingbot import config
from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)

RETENTION_DAYS = 7
PRUNE_EVERY_S = 3600

_clock = time.monotonic
_last_prune: float | None = None


def reset_prune_clock() -> None:
    """Forget the last prune (tests): the next recorded post prunes again."""
    global _last_prune
    _last_prune = None


def record_feed_post(embed, ticker: str | None, kind=None) -> None:
    """Record one accepted simple-channel post; never raises."""
    if not config.FEED_POSTS_ENABLED:
        return
    try:
        recorded = _insert(embed, ticker, kind)
    except Exception as exc:  # noqa: BLE001 -- a lost notification, never a lost send
        swallowed(log, "ops.feed_posts_record", exc, level=logging.DEBUG)
        return
    if recorded:
        _maybe_prune()


def _insert(embed, ticker, kind) -> bool:
    kind = kind or getattr(embed, "kind", None)
    if kind is None:
        return False
    from swingbot.core.db import side_engine
    from swingbot.core.db.repositories.feed_posts import feed_posts_repo
    from swingbot.core.presentation.feed_headline import feed_headline

    ticker = ticker.strip() if isinstance(ticker, str) and ticker.strip() else None
    headline = feed_headline(kind, embed, ticker)
    with side_engine.side_connection() as conn:
        feed_posts_repo().insert(kind.name, ticker, headline, conn=conn)
    return True


def _maybe_prune() -> None:
    global _last_prune
    now = _clock()
    if _last_prune is not None and now - _last_prune < PRUNE_EVERY_S:
        return
    _last_prune = now    # set before the attempt: a failing prune is not retried every post
    try:
        from swingbot.core.db import side_engine
        from swingbot.core.db.repositories.feed_posts import feed_posts_repo
        with side_engine.side_connection() as conn:
            feed_posts_repo().prune(RETENTION_DAYS, conn=conn)
    except Exception as exc:  # noqa: BLE001 -- retention is best effort
        swallowed(log, "ops.feed_posts_prune", exc, level=logging.DEBUG)
