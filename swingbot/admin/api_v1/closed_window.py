"""v181 -- the `[from, to)` window a closed trade is counted in.

Shared by `GET /dashboard?mode=range` (`dashboard.py`) and the Closed tab's
`GET /trades?closed_from=&closed_to=` (`trades.py`). One parser and one
in-window test, so the KPI cards and the table under them are structurally
unable to disagree about which closes a window holds.

The SPA builds every window from whole New York buckets (spec v181 § 6), but
nothing here knows about New York: a window is two aware instants, and a close
is compared as an instant. A naive stored `closed_at` is read as UTC, exactly
as `dashboard.is_today_berlin` reads it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

from . import ApiError


class ClosedWindow(NamedTuple):
    """Half-open `[start, end)`; both bounds timezone-aware."""

    start: datetime
    end: datetime


def _aware(raw: str | None, name: str) -> datetime:
    """One bound, or a 400 naming the parameter.

    A naive bound is rejected rather than read as UTC: the caller is the SPA,
    which always sends an offset, so a naive value is a malformed request --
    unlike a stored `closed_at`, which is old data and gets the UTC reading.
    """
    text = (raw or "").strip()
    if not text:
        raise ApiError("invalid", f"{name} is required: a window needs both bounds", 400)
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError("invalid", f"{name} is not an ISO timestamp: {raw!r}", 400)
    if value.tzinfo is None:
        raise ApiError("invalid", f"{name} must carry a timezone offset", 400)
    return value


def parse_closed_window(
    from_raw: str | None,
    to_raw: str | None,
    *,
    names: tuple[str, str] = ("from", "to"),
) -> ClosedWindow:
    """Both bounds, aware, in order -- or `ApiError("invalid", ..., 400)`.

    `names` are the query-parameter names the caller read, so the error
    message says `closed_from` on `/trades` and `from` on `/dashboard`.
    An empty window (`from == to`) is valid and simply holds nothing.
    """
    start = _aware(from_raw, names[0])
    end = _aware(to_raw, names[1])
    if start > end:
        raise ApiError("invalid", f"{names[0]} must not be after {names[1]}", 400)
    return ClosedWindow(start, end)


def closed_in_window(iso_ts: str | None, window: ClosedWindow) -> bool:
    """Whether a close at `iso_ts` falls in `[start, end)`.

    Missing or unreadable means outside: it cannot be shown to satisfy the
    window, and keeping it would make a count disagree with its rows.
    """
    if not iso_ts:
        return False
    try:
        value = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return window.start <= value < window.end
