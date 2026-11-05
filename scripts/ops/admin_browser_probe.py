"""Browser probe of the admin under load (v206 P1-a).

Logs into the admin with Playwright, loads a fixed list of pages as a
browser does, and records every /api call's time to first byte, so before
and after numbers come from one instrument. Spec:
docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md, Goal
(Measurement rules) and P1-a.

The top half is pure aggregation, unit-tested. The browser loop imports
Playwright lazily (it is not a declared dependency), so importing this
module never needs it.
"""
from __future__ import annotations

import math
import re
from urllib.parse import urlsplit

API_PREFIX = "/api/v1"
#: Shell and polling endpoints; every other /api path is "heavy" (spec P1-a).
LIGHT_ENDPOINTS = frozenset({
    "/session", "/health", "/system/scan", "/system/preferences",
    "/risk/killswitch", "/market/updates", "/events",
})
#: Below this many samples a row has no p90: it is `thin` and shows its max.
THIN_BELOW = 5
GOAL_ENDPOINT_MS = 5000
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID = re.compile(r"^\d+$")


def settle_time(intervals, quiet_s: float, cap_s: float) -> float | None:
    """When the page went quiet, or None when it never did before `cap_s` (`cap`).

    `intervals` are the calls' (start, end) seconds from navigation; an end of
    None is a call still in flight when the loop stopped. Overlapping calls
    merge. The answer is the start of the first gap of at least `quiet_s`
    with nothing in flight, and that gap must complete by `cap_s`.
    """
    t = 0.0
    for start, end in sorted(intervals, key=lambda interval: interval[0]):
        if start - t >= quiet_s:
            break
        t = max(t, math.inf if end is None else end)
    return t if t + quiet_s <= cap_s else None


def nearest_rank(values, pct: float) -> float:
    """Nearest-rank percentile: always an observed value, never an interpolation."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("nearest_rank of no values")
    rank = max(1, math.ceil(pct * len(ordered) / 100))
    return ordered[rank - 1]


def normalise_endpoint(url: str) -> str:
    """`https://host/api/v1/trades/42?x=1` -> `/trades/{id}`: one endpoint, one row."""
    path = urlsplit(url).path
    if path.startswith(API_PREFIX):
        path = path[len(API_PREFIX):]
    parts = ["{date}" if _DATE.match(p) else "{id}" if _ID.match(p) else p for p in path.split("/")]
    return "/".join(parts).rstrip("/") or "/"


def is_heavy(endpoint: str) -> bool:
    return endpoint not in LIGHT_ENDPOINTS


def _spread(values) -> dict:
    """n / median / p90 / max with the thin rule; an empty input is all None."""
    values = list(values)
    if not values:
        return {"n": 0, "median": None, "p90": None, "max": None, "thin": True}
    thin = len(values) < THIN_BELOW
    return {"n": len(values), "median": nearest_rank(values, 50),
            "p90": None if thin else nearest_rank(values, 90),
            "max": max(values), "thin": thin}


def goal_value(spread: dict) -> float:
    """The figure the 5 s goal reads: the p90, or the max on a thin row."""
    return spread["max"] if spread["thin"] else spread["p90"]


def endpoint_stats(calls) -> list[dict]:
    """Per-endpoint TTFB spread (ms), worst first by `goal_value`."""
    groups: dict[str, list[float]] = {}
    for call in calls:
        if call.get("ttfb_ms") is not None:
            groups.setdefault(normalise_endpoint(call["url"]), []).append(call["ttfb_ms"])
    rows = [{"endpoint": name, **_spread(values)} for name, values in groups.items()]
    return sorted(rows, key=lambda row: (-goal_value(row), row["endpoint"]))


def requests_per_minute(count: int, window_s: float) -> float:
    if window_s <= 0:
        raise ValueError("window_s must be positive")
    return round(count * 60.0 / window_s, 1)


def run_label(samples) -> str:
    """`scan` only when every per-page sample saw a running scan, `quiet` when
    none did, `mixed` otherwise: an unreadable sample (None) or no samples
    at all is evidence of neither."""
    values = list(samples)
    if values and all(value is True for value in values):
        return "scan"
    if values and all(value is False for value in values):
        return "quiet"
    return "mixed"
