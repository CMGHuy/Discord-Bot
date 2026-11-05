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


def _first_heavy(calls) -> dict | None:
    heavy = [c for c in calls if is_heavy(normalise_endpoint(c["url"]))]
    return min(heavy, key=lambda c: c["start_s"]) if heavy else None


def _page_row(page: dict) -> dict:
    first = _first_heavy(page["calls"])
    return {
        "round": page["round"], "route": page["route"], "settle_s": page["settle_s"],
        "capped": page["settle_s"] is None, "requests": len(page["calls"]),
        "rpm": requests_per_minute(len(page["calls"]), page["window_s"]),
        "first_heavy": None if first is None else normalise_endpoint(first["url"]),
        "first_heavy_ttfb_ms": None if first is None else first["ttfb_ms"],
        "scan_running": page["scan_running"],
    }


def _round_row(number: int, pages: list[dict]) -> dict:
    """Rounds are reported apart (round 1 is cold); settle stats cover uncapped pages only."""
    settled = [p["settle_s"] for p in pages if p["settle_s"] is not None]
    capped = len(pages) - len(settled)
    return {
        "round": number, "pages": len(pages), "capped": capped,
        "capped_share": round(capped / len(pages), 3) if pages else 0.0,
        "settle_s": _spread(settled),
        "endpoints": endpoint_stats(c for p in pages for c in p["calls"]),
    }


def summarise(raw: dict) -> dict:
    """What every output renders: provenance, label, Goal figures, rounds, pages, idle."""
    pages, idle = raw["pages"], raw["idle"]
    rows = [_page_row(p) for p in pages]
    endpoints = endpoint_stats(c for p in pages for c in p["calls"])
    idle_rpm = requests_per_minute(len(idle["calls"]), idle["window_s"])
    return {
        "meta": dict(raw["meta"]),
        "label": run_label(p["scan_running"] for p in pages),
        "goal": {
            "first_heavy_ms": _spread(r["first_heavy_ttfb_ms"] for r in rows
                                      if r["first_heavy_ttfb_ms"] is not None),
            "endpoints_over_5s": [r["endpoint"] for r in endpoints if goal_value(r) > GOAL_ENDPOINT_MS],
            "idle_rpm": idle_rpm,
        },
        "rounds": [_round_row(n, [p for p in pages if p["round"] == n])
                   for n in sorted({p["round"] for p in pages})],
        "endpoints": endpoints,
        "pages": rows,
        "idle": {"requests": len(idle["calls"]), "window_s": idle["window_s"],
                 "rpm": idle_rpm, "settle_s": idle.get("settle_s")},
    }


def _num(value, digits: int = 0) -> str:
    return "-" if value is None else f"{value:,.{digits}f}"


def _cells(spread: dict, digits: int = 0) -> str:
    p90 = "thin" if spread["thin"] else _num(spread["p90"], digits)
    return f"{spread['n']} | {_num(spread['median'], digits)} | {p90} | {_num(spread['max'], digits)}"


def _endpoint_table(rows) -> list[str]:
    return ["| Endpoint | n | Median ms | p90 ms | Max ms |", "|---|---|---|---|---|",
            *(f"| `{r['endpoint']}` | {_cells(r)} |" for r in rows)]


def _page_line(p: dict) -> str:
    settle = "cap" if p["capped"] else _num(p["settle_s"], 1)
    heavy = f"`{p['first_heavy']}`" if p["first_heavy"] else "-"
    return (f"| {p['round']} | {p['route']} | {settle} | {p['requests']} | {p['rpm']} | "
            f"{heavy} | {_num(p['first_heavy_ttfb_ms'])} | {p['scan_running']} |")


def _round_lines(rnd: dict) -> list[str]:
    return ["", f"## Round {rnd['round']}",
            f"- Pages {rnd['pages']}, capped {rnd['capped']} ({rnd['capped_share']:.0%}); "
            f"settle s over uncapped pages, n | median | p90 | max: {_cells(rnd['settle_s'], 1)}",
            "", *_endpoint_table(rnd["endpoints"])]


def render_markdown(report: dict) -> str:
    meta, goal, idle = report["meta"], report["goal"], report["idle"]
    lines = [
        f"# Admin browser probe, {meta.get('berlin_time', '-')}", "",
        f"- Label: **{report['label']}** (only `scan` counts toward the Goal)",
        f"- Probe `{meta.get('probe_sha', '-')}`, image `{meta.get('image_tag') or '-'}`, base {meta.get('base', '-')}",
        f"- Date {meta.get('date', '-')}, rounds {meta.get('rounds', '-')}, "
        f"cap {meta.get('cap_s', '-')} s, quiet {meta.get('quiet_s', '-')} s",
        f"- Open SSE streams at start: {_num(meta.get('sse_streams'))}",
        "", "## Goal",
        f"- First heavy call per page (ms), n | median | p90 | max: {_cells(goal['first_heavy_ms'])}",
        f"- Endpoints over 5 s (p90, or max when thin): {', '.join(goal['endpoints_over_5s']) or 'none'}",
        f"- Idle tab: {idle['requests']} requests in {idle['window_s']:.0f} s = {idle['rpm']} per minute",
        "", "## All rounds", "", *_endpoint_table(report["endpoints"]),
    ]
    for rnd in report["rounds"]:
        lines += _round_lines(rnd)
    lines += ["", "## Pages", "",
              "| Round | Route | Settle s | Requests | Per min | First heavy | TTFB ms | Scan |",
              "|---|---|---|---|---|---|---|---|", *(_page_line(p) for p in report["pages"])]
    return "\n".join(lines) + "\n"
