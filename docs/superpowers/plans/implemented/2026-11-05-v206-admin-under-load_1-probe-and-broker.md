# v206 Plan 1, part 1 — probe, baseline, `/health` stream count

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md)
**Index:** [`2026-11-05-v206-admin-under-load_0-index.md`](2026-11-05-v206-admin-under-load_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Tasks V206-1, V206-1b, V206-2..V206-4 (V206-1 passed the 20 KB cap and was split into V206-1 + V206-1b). V206-5..V206-6 (index group C) are in [`_1b-broker.md`](2026-11-05-v206-admin-under-load_1b-broker.md): this file would otherwise pass the 1500-line cap. `<wt>` is the implementation worktree, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v206-admin-under-load`; every command runs with that path, never in the main tree. Python tests run narrow (`python <wt>/scripts/dev/testrun.py file <test>` from `<wt>`); no task runs the full suite.

# Phase A — the browser probe

### Task V206-1: Probe aggregation primitives: settle time, percentiles, endpoints, label

**Model:** sonnet — new self-contained module of pure functions with table-driven tests; no shared state, no cross-package seam.

**Files:**
- Create: `scripts/ops/admin_browser_probe.py`
- Create: `tests/scripts/test_admin_browser_probe.py`

**Interfaces:**
- Consumes: nothing.
- Produces (V206-1b and V206-2 extend this module):
  - `settle_time(intervals, quiet_s: float, cap_s: float) -> float | None`: `None` means the page is `cap`.
  - `nearest_rank(values, pct: float) -> float` (raises `ValueError` on no values).
  - `normalise_endpoint(url: str) -> str`, `is_heavy(endpoint: str) -> bool`.
  - `endpoint_stats(calls) -> list[dict]`: rows `{endpoint, n, median, p90, max, thin}` (ms), worst first by `goal_value`.
  - `goal_value(spread: dict) -> float`; private `_spread(values) -> {n, median, p90, max, thin}` (V206-1b reuses it).
  - `requests_per_minute(count: int, window_s: float) -> float`.
  - `run_label(samples) -> str`: `scan` / `mixed` / `quiet`.
  - Constants `API_PREFIX = "/api/v1"`, `LIGHT_ENDPOINTS`, `THIN_BELOW = 5`, `GOAL_ENDPOINT_MS = 5000`.

The settle rule (spec P1-a): a page is settled once no `/api` call (ignoring `/api/v1/events`) has been in flight for `quiet_s` (2 s); the settle time is the moment that quiet gap began. A gap of exactly `quiet_s` counts. The gap must complete by `cap_s`, otherwise the page is `cap`. A call still in flight when the loop stopped has `end` `None` (in flight forever). Percentiles are nearest-rank; a p90 exists only at n ≥ 5, below that the row is `thin` and the 5 s goal reads its max. "Heavy" is any `/api` path outside `session`, `health`, `system/scan`, `system/preferences`, `risk/killswitch`, `market/updates` (and `/events`).

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_admin_browser_probe.py` (`tests/scripts/` is already in suite `tooling`; no `tests/suites.toml` edit):

```python
"""scripts/ops/admin_browser_probe.py: the browser probe (v206 P1-a).

Only the Playwright loop goes without a unit test (spec P1-a); every metric
the Goal reads -- settle time, nearest-rank percentiles with the thin rule,
the heavy-call rule, requests per minute, the run label -- is pinned here.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import admin_browser_probe as probe  # noqa: E402


def test_importing_the_probe_does_not_import_playwright():
    """Playwright is not a declared dependency: only the browser loop imports it."""
    assert "playwright" not in sys.modules


# --- settle_time -------------------------------------------------------------

def test_overlapping_calls_merge_and_the_page_settles_when_the_last_one_ends():
    intervals = [(2.9, 4.0), (0.0, 1.0), (0.5, 3.0)]  # unsorted on purpose
    assert probe.settle_time(intervals, 2.0, 90.0) == 4.0


def test_a_gap_just_under_the_quiet_window_does_not_settle_the_page():
    assert probe.settle_time([(0.0, 1.0), (2.99, 3.5)], 2.0, 90.0) == 3.5


def test_a_gap_just_over_the_quiet_window_settles_the_page_where_the_gap_began():
    assert probe.settle_time([(0.0, 1.0), (3.01, 3.5)], 2.0, 90.0) == 1.0


def test_a_call_still_in_flight_at_the_cap_means_the_page_never_settled():
    assert probe.settle_time([(0.0, 1.0), (1.5, None)], 2.0, 90.0) is None


def test_a_quiet_gap_that_completes_after_the_cap_is_still_cap():
    assert probe.settle_time([(0.0, 89.0)], 2.0, 90.0) is None


def test_a_page_with_no_calls_settles_at_once():
    assert probe.settle_time([], 2.0, 90.0) == 0.0


# --- percentiles and the thin rule -------------------------------------------

@pytest.mark.parametrize("pct, expected", [(0, 15), (50, 35), (90, 50), (100, 50)])
def test_nearest_rank_picks_an_observed_value(pct, expected):
    assert probe.nearest_rank([50, 15, 40, 20, 35], pct) == expected


def test_nearest_rank_of_nothing_is_an_error_not_a_zero():
    with pytest.raises(ValueError):
        probe.nearest_rank([], 90)


def test_four_values_are_thin_and_carry_no_p90():
    calls = [{"url": "/api/v1/trades", "ttfb_ms": v} for v in (100, 200, 300, 400)]
    (row,) = probe.endpoint_stats(calls)
    assert row == {"endpoint": "/trades", "n": 4, "median": 200, "p90": None, "max": 400, "thin": True}
    assert probe.goal_value(row) == 400


def test_five_values_get_a_p90():
    calls = [{"url": "/api/v1/trades", "ttfb_ms": v} for v in (100, 200, 300, 400, 500)]
    (row,) = probe.endpoint_stats(calls)
    assert row["thin"] is False and row["p90"] == 500
    assert probe.goal_value(row) == 500


def test_calls_without_a_ttfb_are_not_timed():
    assert probe.endpoint_stats([{"url": "/api/v1/live", "ttfb_ms": None}]) == []


def test_rows_are_worst_first_and_a_thin_row_ranks_on_its_max():
    calls = ([{"url": "/api/v1/system/scan", "ttfb_ms": v} for v in (200, 240, 250, 260, 300, 6000)]
             + [{"url": "/api/v1/trades?page=1", "ttfb_ms": v} for v in (700, 4000)]
             + [{"url": "/api/v1/health", "ttfb_ms": 90}])
    rows = probe.endpoint_stats(calls)
    assert [r["endpoint"] for r in rows] == ["/system/scan", "/trades", "/health"]
    assert rows[0] == {"endpoint": "/system/scan", "n": 6, "median": 250, "p90": 6000, "max": 6000, "thin": False}


# --- endpoints ---------------------------------------------------------------

@pytest.mark.parametrize("url, expected", [
    ("https://bomeo-capital.com/api/v1/dashboard?mode=today", "/dashboard"),
    ("/api/v1/trades/42", "/trades/{id}"),
    ("/api/v1/calendar/pnl/day/2026-11-03", "/calendar/pnl/day/{date}"),
    ("/api/v1/calendar/pnl/day/sparklines?date=2026-11-03", "/calendar/pnl/day/sparklines"),
])
def test_endpoints_drop_host_prefix_query_ids_and_dates(url, expected):
    assert probe.normalise_endpoint(url) == expected


@pytest.mark.parametrize("endpoint", ["/session", "/health", "/system/scan", "/system/preferences",
                                      "/risk/killswitch", "/market/updates", "/events"])
def test_shell_and_polling_endpoints_are_light(endpoint):
    assert probe.is_heavy(endpoint) is False


@pytest.mark.parametrize("endpoint", ["/dashboard", "/market/tape", "/trades", "/live"])
def test_every_other_endpoint_is_heavy(endpoint):
    assert probe.is_heavy(endpoint) is True


# --- rates and labels --------------------------------------------------------

def test_requests_per_minute():
    assert probe.requests_per_minute(6, 120.0) == 3.0
    assert probe.requests_per_minute(4, 5.5) == 43.6


def test_requests_per_minute_needs_a_window():
    with pytest.raises(ValueError):
        probe.requests_per_minute(3, 0.0)


@pytest.mark.parametrize("samples, label", [
    ([True, True, True], "scan"),
    ([False, False], "quiet"),
    ([True, False], "mixed"),
    ([True, None], "mixed"),
    ([], "mixed"),
])
def test_only_a_scan_on_every_page_labels_the_run_scan(samples, label):
    assert probe.run_label(samples) == label
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/scripts/test_admin_browser_probe.py`
Expected: collection error, `ModuleNotFoundError: No module named 'admin_browser_probe'`.

- [ ] **Step 3: Write the primitives**

Create `scripts/ops/admin_browser_probe.py`:

```python
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
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/scripts/test_admin_browser_probe.py`
Expected: all pass, `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: no new offender (every function here is a few branches).

- [ ] **Step 6: Commit**

```bash
git -C "<wt>" add scripts/ops/admin_browser_probe.py tests/scripts/test_admin_browser_probe.py
git -C "<wt>" commit -m "feat(v206): browser probe primitives -- settle time, nearest-rank, run label (V206-1)"
```

### Task V206-1b: Probe report: fixture, `summarise`, `render_markdown`

**Model:** sonnet — pure report assembly over V206-1's primitives, pinned by a hand-computed fixture.

**Files:**
- Create: `tests/scripts/fixtures/admin_browser_probe_raw.json`
- Modify: `scripts/ops/admin_browser_probe.py`
- Modify: `tests/scripts/test_admin_browser_probe.py`

**Interfaces:**
- Consumes (V206-1): `_spread`, `goal_value`, `endpoint_stats`, `normalise_endpoint`, `is_heavy`, `requests_per_minute`, `run_label`, `GOAL_ENDPOINT_MS`.
- Produces (V206-2 writes this raw shape and calls these; V206-3 and V206-13 read the output):
  - `summarise(raw: dict) -> dict` with keys `meta`, `label`, `goal {first_heavy_ms, endpoints_over_5s, idle_rpm}`, `rounds [{round, pages, capped, capped_share, settle_s, endpoints}]`, `endpoints`, `pages [{round, route, settle_s, capped, requests, rpm, first_heavy, first_heavy_ttfb_ms, scan_running}]`, `idle {requests, window_s, rpm, settle_s}`.
  - `render_markdown(report: dict) -> str`.
  - Raw shape: `{"meta": {...}, "pages": [{"round", "route", "final_url", "settle_s" (float|null = cap), "window_s", "scan_running" (bool|null), "calls": [{"url", "status", "start_s", "end_s" (float|null), "ttfb_ms" (float|null), "total_ms", "bytes", "server_timing"}]}], "idle": {"route", "settle_s", "window_s", "calls": [...]}}`.

Spec Measurement rules this task pins: rounds reported separately; capped pages reported as a share, settle statistics over uncapped pages only; the first heavy call's TTFB per page; idle rate from the idle-hold phase; provenance (`meta`) carried through untouched.

- [ ] **Step 1: Write the fixture**

Create `tests/scripts/fixtures/admin_browser_probe_raw.json` (new `fixtures/` directory under `tests/scripts/`, already in suite `tooling`). Every expected figure in Step 2 is hand-computed from it.

```json
{
 "meta": {"probe_sha": "abc1234", "image_tag": "ghcr.io/example/swingbot:abc1234",
          "berlin_time": "2026-11-05T16:20:00+01:00", "date": "2026-11-03",
          "base": "https://bomeo-capital.com", "rounds": 2, "cap_s": 90, "quiet_s": 2.0,
          "sse_streams": 3, "login_status": 200},
 "pages": [
  {"round": 1, "route": "dashboard", "final_url": "/dashboard", "settle_s": 3.5, "window_s": 5.5, "scan_running": true,
   "calls": [
    {"url": "https://bomeo-capital.com/api/v1/health", "status": 200, "start_s": 0.1, "end_s": 0.2, "ttfb_ms": 90, "total_ms": 100, "bytes": 120, "server_timing": null},
    {"url": "https://bomeo-capital.com/api/v1/dashboard?mode=today", "status": 200, "start_s": 0.2, "end_s": 1.5, "ttfb_ms": 1200, "total_ms": 1300, "bytes": 9000, "server_timing": null},
    {"url": "/api/v1/trades?sort=-opened_at&page=1", "status": 200, "start_s": 0.3, "end_s": 1.3, "ttfb_ms": 900, "total_ms": 1000, "bytes": 5000, "server_timing": null},
    {"url": "/api/v1/system/scan", "status": 200, "start_s": 3.0, "end_s": 3.5, "ttfb_ms": 200, "total_ms": 500, "bytes": 400, "server_timing": null}]},
  {"round": 1, "route": "trades", "final_url": "/trades", "settle_s": null, "window_s": 90.0, "scan_running": true,
   "calls": [
    {"url": "/api/v1/trades", "status": 200, "start_s": 0.2, "end_s": 4.5, "ttfb_ms": 4000, "total_ms": 4300, "bytes": 5000, "server_timing": null},
    {"url": "/api/v1/system/scan", "status": 200, "start_s": 1.0, "end_s": 1.4, "ttfb_ms": 300, "total_ms": 400, "bytes": 400, "server_timing": null},
    {"url": "/api/v1/system/scan", "status": 200, "start_s": 2.0, "end_s": 2.3, "ttfb_ms": 250, "total_ms": 300, "bytes": 400, "server_timing": null},
    {"url": "/api/v1/system/scan", "status": 200, "start_s": 3.0, "end_s": 9.1, "ttfb_ms": 6000, "total_ms": 6100, "bytes": 400, "server_timing": null}]},
  {"round": 2, "route": "dashboard", "final_url": "/dashboard", "settle_s": 2.1, "window_s": 4.1, "scan_running": true,
   "calls": [
    {"url": "/api/v1/health", "status": 200, "start_s": 0.0, "end_s": 0.1, "ttfb_ms": 80, "total_ms": 100, "bytes": 120, "server_timing": null},
    {"url": "/api/v1/dashboard?mode=today", "status": 200, "start_s": 0.1, "end_s": 0.9, "ttfb_ms": 800, "total_ms": 800, "bytes": 9000, "server_timing": "db;dur=310"},
    {"url": "/api/v1/trades?status=ACTIVE", "status": 200, "start_s": 0.1, "end_s": 0.8, "ttfb_ms": 700, "total_ms": 700, "bytes": 2000, "server_timing": null},
    {"url": "/api/v1/system/scan", "status": 200, "start_s": 1.0, "end_s": 2.1, "ttfb_ms": 260, "total_ms": 1100, "bytes": 400, "server_timing": null}]},
  {"round": 2, "route": "trades", "final_url": "/trades", "settle_s": 1.2, "window_s": 3.2, "scan_running": true,
   "calls": [
    {"url": "/api/v1/trades", "status": 200, "start_s": 0.2, "end_s": 1.2, "ttfb_ms": 1100, "total_ms": 1000, "bytes": 5000, "server_timing": null},
    {"url": "/api/v1/system/scan", "status": 200, "start_s": 0.3, "end_s": 0.6, "ttfb_ms": 240, "total_ms": 300, "bytes": 400, "server_timing": null}]}
 ],
 "idle": {"route": "dashboard", "settle_s": 2.4, "window_s": 120.0,
  "calls": [
   {"url": "/api/v1/system/scan", "status": 200, "start_s": 1.0, "end_s": 1.2, "ttfb_ms": 150, "total_ms": 200, "bytes": 400, "server_timing": null},
   {"url": "/api/v1/system/scan", "status": 200, "start_s": 21.0, "end_s": 21.2, "ttfb_ms": 150, "total_ms": 200, "bytes": 400, "server_timing": null},
   {"url": "/api/v1/system/scan", "status": 200, "start_s": 41.0, "end_s": 41.2, "ttfb_ms": 150, "total_ms": 200, "bytes": 400, "server_timing": null},
   {"url": "/api/v1/live", "status": 200, "start_s": 50.0, "end_s": 51.5, "ttfb_ms": 1400, "total_ms": 1500, "bytes": 3000, "server_timing": null},
   {"url": "/api/v1/system/scan", "status": 200, "start_s": 61.0, "end_s": 61.2, "ttfb_ms": 150, "total_ms": 200, "bytes": 400, "server_timing": null},
   {"url": "/api/v1/system/scan", "status": 200, "start_s": 81.0, "end_s": 81.2, "ttfb_ms": 150, "total_ms": 200, "bytes": 400, "server_timing": null}]}
}
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/scripts/test_admin_browser_probe.py` (add `import json` beside the existing `import sys` at the top):

```python
# --- summarise and render (V206-1b) ------------------------------------------

FIXTURE = Path(__file__).parent / "fixtures" / "admin_browser_probe_raw.json"


@pytest.fixture
def raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_summary_carries_provenance_and_the_run_label(raw):
    report = probe.summarise(raw)
    assert report["label"] == "scan"
    assert report["meta"] == raw["meta"]


def test_summary_goal_figures(raw):
    goal = probe.summarise(raw)["goal"]
    # First heavy TTFB per page: 1200, 4000, 800, 1100 -> n=4, thin, median rank 2 = 1100.
    assert goal["first_heavy_ms"] == {"n": 4, "median": 1100, "p90": None, "max": 4000, "thin": True}
    assert goal["endpoints_over_5s"] == ["/system/scan"]
    assert goal["idle_rpm"] == 3.0


def test_summary_rounds_are_apart_and_settle_stats_skip_capped_pages(raw):
    first, second = probe.summarise(raw)["rounds"]
    assert (first["round"], first["pages"], first["capped"], first["capped_share"]) == (1, 2, 1, 0.5)
    assert first["settle_s"] == {"n": 1, "median": 3.5, "p90": None, "max": 3.5, "thin": True}
    assert (second["capped"], second["settle_s"]["median"], second["settle_s"]["max"]) == (0, 1.2, 2.1)
    assert [r["endpoint"] for r in second["endpoints"]] == ["/trades", "/dashboard", "/system/scan", "/health"]


def test_summary_endpoints_pool_every_round(raw):
    rows = probe.summarise(raw)["endpoints"]
    assert [r["endpoint"] for r in rows] == ["/system/scan", "/trades", "/dashboard", "/health"]
    assert rows[1] == {"endpoint": "/trades", "n": 4, "median": 900, "p90": None, "max": 4000, "thin": True}


def test_page_rows_carry_cap_and_the_first_heavy_call(raw):
    pages = probe.summarise(raw)["pages"]
    capped = pages[1]
    assert capped["capped"] is True and capped["settle_s"] is None
    assert (capped["first_heavy"], capped["first_heavy_ttfb_ms"]) == ("/trades", 4000)
    # /health starts first on the dashboard but is light; the heavy call is /dashboard.
    assert (pages[0]["first_heavy"], pages[0]["first_heavy_ttfb_ms"]) == ("/dashboard", 1200)
    assert (pages[0]["requests"], pages[0]["rpm"]) == (4, 43.6)


def test_a_page_with_only_light_calls_has_no_first_heavy_call(raw):
    raw["pages"] = [{**raw["pages"][0], "calls": raw["pages"][0]["calls"][:1]}]
    page = probe.summarise(raw)["pages"][0]
    assert (page["first_heavy"], page["first_heavy_ttfb_ms"]) == (None, None)
    assert probe.summarise(raw)["goal"]["first_heavy_ms"]["n"] == 0


def test_summary_idle(raw):
    assert probe.summarise(raw)["idle"] == {"requests": 6, "window_s": 120.0, "rpm": 3.0, "settle_s": 2.4}


def test_markdown_shows_the_label_thin_rows_cap_and_the_idle_rate(raw):
    text = probe.render_markdown(probe.summarise(raw))
    assert "Label: **scan**" in text
    assert "Open SSE streams at start: 3" in text
    assert "| `/system/scan` | 6 | 250 | 6,000 | 6,000 |" in text
    assert "| `/trades` | 4 | 900 | thin | 4,000 |" in text
    assert "| 1 | trades | cap |" in text
    assert "## Round 2" in text
    assert "6 requests in 120 s = 3.0 per minute" in text
    assert "Endpoints over 5 s (p90, or max when thin): /system/scan" in text


def test_markdown_shows_a_dash_for_an_unknown_stream_count(raw):
    raw["meta"]["sse_streams"] = None
    assert "Open SSE streams at start: -" in probe.render_markdown(probe.summarise(raw))
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/scripts/test_admin_browser_probe.py`
Expected: the V206-1 tests pass; the new ones fail with `AttributeError: module 'admin_browser_probe' has no attribute 'summarise'`.

- [ ] **Step 4: Write the report half**

Append to `scripts/ops/admin_browser_probe.py`, after `run_label`:

```python
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
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/scripts/test_admin_browser_probe.py`
Expected: all pass, `0 failed`.

- [ ] **Step 6: Complexity gate**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: no new offender; `render_markdown` is the largest function here and stays well under 15.

- [ ] **Step 7: Commit**

```bash
git -C "<wt>" add scripts/ops/admin_browser_probe.py tests/scripts/test_admin_browser_probe.py tests/scripts/fixtures/admin_browser_probe_raw.json
git -C "<wt>" commit -m "feat(v206): browser probe report -- rounds apart, capped share, idle rate, markdown (V206-1b)"
```

### Task V206-2: Probe CLI, browser loop, outputs, credential hygiene

**Model:** sonnet — CLI and Playwright loop around V206-1/1b's pure functions; credential hygiene is pinned by a sentinel test, the loop itself is untested by design (spec P1-a).

**Files:**
- Modify: `scripts/ops/admin_browser_probe.py`
- Modify: `tests/scripts/test_admin_browser_probe.py`

**Interfaces:**
- Consumes (V206-1, V206-1b): `settle_time`, `summarise`, `render_markdown`, the raw shape, and the test file's `raw` fixture.
- Consumes (V206-4, optional at run time): `/api/v1/health` field `sse_streams`; absent on an older server, recorded as `None`.
- Produces (V206-3, V206-13 run it):
  - CLI `python scripts/ops/admin_browser_probe.py --date YYYY-MM-DD --out DIR [--base URL] [--rounds 3] [--cap 90] [--image-tag TAG]`; exit 0 on a run, 2 on a failed or impossible login.
  - `main(argv=None, *, runner=None, env_path=None) -> int`; `runner(args, credentials) -> raw dict` (default `run_browser`).
  - `LoginFailed(reason: str)`; `ROUTES`; `routes(day) -> list[str]`; `parse_args`, `load_credentials(env_path) -> (user, password)`, `default_env_path() -> Path`, `build_meta(args, now=None) -> dict`, `write_outputs(out_dir, raw) -> dict`.
  - Writes `DIR/probe.json` (`{"raw": ..., "report": ...}`) and `DIR/probe.md`.

Spec P1-a and Global Constraints: Chromium headless, service workers blocked, viewport 1440×900, routes fixed in spec order, `--rounds` 3, `--cap` 90, quiet 2 s, `--date` required, `--base` default `https://bomeo-capital.com`. GETs plus the session POST only. Credentials are read from `.env` inside the script and are **never printed, logged or written**; a failed login exits non-zero **before any page loads** (the session POST goes through `context.request`, before `new_page()`). A page that never settles is recorded as `cap`, never dropped. The live loop only collects intervals; `settle_time` decides. A worktree has no `.env`, so `default_env_path()` falls back to the main checkout's.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_admin_browser_probe.py`:

```python
# --- CLI, outputs and credential hygiene (V206-2) ----------------------------

SENTINEL_USER = "sentinel-user-7f3a"
SENTINEL_PASS = "sentinel-pass-91c2"
ARGV = ["--date", "2026-11-03", "--out"]


def _env(tmp_path):
    path = tmp_path / ".env"
    path.write_text(f"# admin\nADMIN_USERNAME={SENTINEL_USER}\nADMIN_PASSWORD=\"{SENTINEL_PASS}\"\n",
                    encoding="utf-8")
    return path


def _runner_from(raw, seen=None):
    def runner(args, credentials):
        if seen is not None:
            seen.append(credentials)
        return {"meta": {"login_status": 200, "sse_streams": 2}, "pages": raw["pages"], "idle": raw["idle"]}
    return runner


def test_routes_are_the_spec_list_in_order_with_the_pinned_date():
    assert probe.routes("2026-11-03") == [
        "dashboard", "trades", "trades/calendar", "trades/calendar/2026-11-03", "trades/cancels",
        "watchlist", "risk", "insights/analytics", "insights/research", "insights/reports",
        "system", "system/versions"]


def test_defaults_match_the_spec():
    args = probe.parse_args(["--date", "2026-11-03", "--out", "x"])
    assert (args.base, args.rounds, args.cap, args.image_tag) == ("https://bomeo-capital.com", 3, 90.0, "")


@pytest.mark.parametrize("argv", [["--out", "x"], ["--date", "2026-13-40", "--out", "x"], ["--date", "2026-11-03"]])
def test_date_and_out_are_required_and_the_date_must_be_real(argv):
    with pytest.raises(SystemExit):
        probe.parse_args(argv)


def test_meta_records_provenance(monkeypatch):
    from datetime import datetime
    monkeypatch.setattr(probe, "_git_sha", lambda: "abc1234")
    args = probe.parse_args(["--date", "2026-11-03", "--out", "x", "--image-tag", "ghcr.io/x:1"])
    meta = probe.build_meta(args, now=datetime(2026, 11, 5, 16, 20, tzinfo=probe.BERLIN))
    assert meta == {"probe_sha": "abc1234", "image_tag": "ghcr.io/x:1", "berlin_time": "2026-11-05T16:20:00+01:00",
                    "date": "2026-11-03", "base": "https://bomeo-capital.com", "rounds": 3, "cap_s": 90.0,
                    "quiet_s": 2.0}


def test_credentials_reach_the_runner_but_never_the_output(tmp_path, raw, capsys):
    seen, out = [], tmp_path / "run"
    code = probe.main(ARGV + [str(out)], runner=_runner_from(raw, seen), env_path=_env(tmp_path))
    assert code == 0
    assert seen == [(SENTINEL_USER, SENTINEL_PASS)]
    printed = capsys.readouterr()
    texts = [(out / "probe.json").read_text(encoding="utf-8"), (out / "probe.md").read_text(encoding="utf-8"),
             printed.out, printed.err]
    for text in texts:
        assert SENTINEL_USER not in text and SENTINEL_PASS not in text


def test_outputs_merge_runner_meta_over_provenance(tmp_path, raw, monkeypatch):
    monkeypatch.setattr(probe, "_git_sha", lambda: "abc1234")
    out = tmp_path / "run"
    probe.main(ARGV + [str(out), "--image-tag", "ghcr.io/x:1"], runner=_runner_from(raw), env_path=_env(tmp_path))
    written = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    meta = written["report"]["meta"]
    assert (meta["probe_sha"], meta["image_tag"], meta["sse_streams"], meta["login_status"]) == \
        ("abc1234", "ghcr.io/x:1", 2, 200)
    assert written["report"]["label"] == "scan"
    assert "Label: **scan**" in (out / "probe.md").read_text(encoding="utf-8")


def test_a_failed_login_exits_non_zero_and_writes_nothing(tmp_path, capsys):
    def runner(args, credentials):
        raise probe.LoginFailed("HTTP 401")
    out = tmp_path / "run"
    assert probe.main(ARGV + [str(out)], runner=runner, env_path=_env(tmp_path)) == 2
    assert not out.exists()
    err = capsys.readouterr().err
    assert "HTTP 401" in err and SENTINEL_PASS not in err and SENTINEL_USER not in err


def test_missing_credentials_fail_before_the_browser_starts(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OTHER=1\n", encoding="utf-8")

    def runner(*_):
        raise AssertionError("the browser must not start without credentials")
    assert probe.main(ARGV + [str(tmp_path / "run")], runner=runner, env_path=env) == 2


def test_default_env_path_prefers_this_checkout(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    assert probe.default_env_path() == tmp_path / ".env"


class _Request:
    def __init__(self, url, response_start=150.0):
        self.url = url
        self.timing = {"startTime": 0, "requestStart": 50.0, "responseStart": response_start, "responseEnd": 400.0}

    def response(self):
        return None


def test_the_recorder_tracks_api_calls_only_and_knows_what_is_in_flight():
    ticks = iter([0.0, 0.5, 1.0, 1.5])
    recorder = probe._Recorder(clock=lambda: next(ticks))  # t0 = 0.0
    api, events, asset = _Request("https://h/api/v1/trades"), _Request("https://h/api/v1/events"), _Request("https://h/main.js")
    for request in (api, events, asset):
        recorder.on_request(request)                         # api starts at 0.5
    assert recorder.in_flight() == 1
    recorder.on_finished(api)                                # ends at 1.0
    (call,) = recorder.calls.values()
    assert (call["start_s"], call["end_s"], call["ttfb_ms"], call["total_ms"]) == (0.5, 1.0, 100.0, 400.0)
    assert recorder.in_flight() == 0
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/scripts/test_admin_browser_probe.py`
Expected: the V206-1/1b tests pass; the new ones fail with `AttributeError` (`routes`, `parse_args`, `main`, `_Recorder`, ...).

- [ ] **Step 3: Write the CLI and the browser loop**

In `scripts/ops/admin_browser_probe.py`, replace the import block with:

```python
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
```

Add the usage line to the module docstring, after its first paragraph:

```text
    python scripts/ops/admin_browser_probe.py --date 2026-11-03 --out .superpowers/probe/<run> [--image-tag TAG]
```

Append at the end of the module:

```python
# --- the browser loop and the CLI (V206-2) -----------------------------------

ROOT = Path(__file__).resolve().parents[2]
BERLIN = ZoneInfo("Europe/Berlin")
DEFAULT_BASE = "https://bomeo-capital.com"
#: Spec P1-a, in this fixed order; production serves the SPA at the root path.
ROUTES = ("dashboard", "trades", "trades/calendar", "trades/calendar/{date}", "trades/cancels",
          "watchlist", "risk", "insights/analytics", "insights/research", "insights/reports",
          "system", "system/versions")
QUIET_S = 2.0
IDLE_ROUTE = "dashboard"
IDLE_WINDOW_S = 120.0
VIEWPORT = {"width": 1440, "height": 900}
_ENV_LINE = re.compile(r"\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$")


class LoginFailed(Exception):
    """No session: carries a reason (an HTTP status), never a credential."""


def routes(day: str) -> list[str]:
    return [route.format(date=day) for route in ROUTES]


def _iso_date(text: str) -> str:
    date.fromisoformat(text)  # ValueError -> argparse rejects the value
    return text


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browser probe of the admin under load (v206).")
    parser.add_argument("--date", required=True, type=_iso_date, help="day for trades/calendar/<date>")
    parser.add_argument("--out", required=True, type=Path, help="directory for probe.json and probe.md")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--cap", type=float, default=90.0, help="settle cap per page, seconds")
    parser.add_argument("--image-tag", default="", help="production image tag, recorded in the result")
    return parser.parse_args(argv)


def default_env_path() -> Path:
    """`.env` in this checkout, else the main checkout's (a worktree has none)."""
    local = ROOT / ".env"
    if local.exists():
        return local
    try:
        common = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return local
    return Path(common).parent / ".env"


def load_credentials(env_path: Path) -> tuple[str, str]:
    """ADMIN_USERNAME / ADMIN_PASSWORD from `.env`. Never printed, logged or written."""
    env = {}
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        match = _ENV_LINE.match(line)
        if match:
            env[match.group(1)] = match.group(2).strip('"').strip("'")
    user, password = env.get("ADMIN_USERNAME"), env.get("ADMIN_PASSWORD")
    if not user or not password:
        raise LoginFailed("ADMIN_USERNAME or ADMIN_PASSWORD missing from .env")
    return user, password


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def build_meta(args, now=None) -> dict:
    now = now or datetime.now(BERLIN)
    return {"probe_sha": _git_sha(), "image_tag": args.image_tag or None,
            "berlin_time": now.isoformat(timespec="seconds"), "date": args.date, "base": args.base,
            "rounds": args.rounds, "cap_s": args.cap, "quiet_s": QUIET_S}


def write_outputs(out_dir: Path, raw: dict) -> dict:
    report = summarise(raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "probe.json").write_text(json.dumps({"raw": raw, "report": report}, indent=1), encoding="utf-8")
    (out_dir / "probe.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def _is_api(url: str) -> bool:
    return "/api/" in url and "/api/v1/events" not in url


def _response_facts(request) -> dict:
    timing = request.timing
    facts = {"ttfb_ms": None, "total_ms": round(timing["responseEnd"], 1)}
    if timing["responseStart"] > 0:
        facts["ttfb_ms"] = round(timing["responseStart"] - timing["requestStart"], 1)
    try:
        response = request.response()
        if response is not None:
            facts["status"] = response.status
            facts["server_timing"] = response.headers.get("server-timing")
            facts["bytes"] = len(response.body()) if response.status == 200 else None
    except Exception:  # noqa: BLE001 -- a closed page loses the facts, never the call
        pass
    return facts


class _Recorder:
    """One page's /api calls. The live loop only collects; `settle_time` decides."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.t0 = clock()
        self.calls: dict[int, dict] = {}

    def reset(self) -> None:
        self.t0, self.calls = self._clock(), {}

    def _now(self) -> float:
        return round(self._clock() - self.t0, 3)

    def in_flight(self) -> int:
        return sum(1 for call in self.calls.values() if call["end_s"] is None)

    def on_request(self, request) -> None:
        if _is_api(request.url):
            self.calls[id(request)] = {"url": request.url, "status": None, "start_s": self._now(), "end_s": None,
                                       "ttfb_ms": None, "total_ms": None, "bytes": None, "server_timing": None}

    def on_finished(self, request) -> None:
        call = self.calls.get(id(request))
        if call is not None:
            call["end_s"] = self._now()
            call.update(_response_facts(request))

    def on_failed(self, request) -> None:
        call = self.calls.get(id(request))
        if call is not None:
            call["end_s"] = self._now()


def _wait_quiet(page, recorder: _Recorder, cap_s: float) -> float:
    """Poll until nothing has been in flight for QUIET_S, or the cap. Returns the window (s)."""
    quiet_since = None
    while time.monotonic() - recorder.t0 < cap_s:
        page.wait_for_timeout(100)
        if recorder.in_flight():
            quiet_since = None
        elif quiet_since is None:
            quiet_since = time.monotonic()
        elif time.monotonic() - quiet_since >= QUIET_S:
            break
    return round(time.monotonic() - recorder.t0, 3)


def _visit(page, recorder: _Recorder, url: str, cap_s: float) -> dict:
    recorder.reset()
    try:
        page.goto(url, wait_until="load", timeout=int(cap_s * 1000))
    except Exception as exc:  # noqa: BLE001 -- a page that never loads is `cap`, never dropped
        print(f"probe: {url} did not load ({type(exc).__name__})", file=sys.stderr)
    window = _wait_quiet(page, recorder, cap_s)
    calls = list(recorder.calls.values())
    return {"final_url": page.url, "window_s": window, "calls": calls,
            "settle_s": settle_time([(c["start_s"], c["end_s"]) for c in calls], QUIET_S, cap_s)}


def _get_json(context, url: str) -> dict | None:
    try:
        response = context.request.get(url, timeout=30_000)
        return response.json() if response.ok else None
    except Exception:  # noqa: BLE001 -- an unreadable sample is recorded as unknown
        return None


def _scan_sample(context, base: str) -> bool | None:
    body = _get_json(context, f"{base}/api/v1/system/scan")
    return None if body is None else bool(body.get("running"))


def _login(context, base: str, credentials: tuple[str, str]) -> int:
    user, password = credentials
    response = context.request.post(f"{base}/api/v1/session", data={"username": user, "password": password})
    if response.status != 200:
        raise LoginFailed(f"HTTP {response.status}")
    return response.status


def _probe_page(page, context, recorder, base: str, rnd: int, route: str, cap_s: float) -> dict:
    visit = _visit(page, recorder, f"{base}/{route}", cap_s)
    return {"round": rnd, "route": route, **visit, "final_url": visit["final_url"].replace(base, ""),
            "scan_running": _scan_sample(context, base)}


def _idle(page, recorder: _Recorder, base: str, cap_s: float) -> dict:
    """Spec Measurement rules: open dashboard, settle (or cap), then count /api requests for 120 s."""
    visit = _visit(page, recorder, f"{base}/{IDLE_ROUTE}", cap_s)
    recorder.reset()
    page.wait_for_timeout(IDLE_WINDOW_S * 1000)
    return {"route": IDLE_ROUTE, "settle_s": visit["settle_s"], "window_s": IDLE_WINDOW_S,
            "calls": list(recorder.calls.values())}


def run_browser(args, credentials: tuple[str, str]) -> dict:
    """The live loop. Logs in before any page exists, so a failed login loads nothing."""
    from playwright.sync_api import sync_playwright  # lazy: not a declared dependency

    base = args.base.rstrip("/")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport=VIEWPORT, service_workers="block")
            meta = {"login_status": _login(context, base, credentials)}
            # Streams other tabs hold before this probe opens its own.
            meta["sse_streams"] = (_get_json(context, f"{base}/api/v1/health") or {}).get("sse_streams")
            page, recorder = context.new_page(), _Recorder()
            page.on("request", recorder.on_request)
            page.on("requestfinished", recorder.on_finished)
            page.on("requestfailed", recorder.on_failed)
            pages = [_probe_page(page, context, recorder, base, rnd, route, args.cap)
                     for rnd in range(1, args.rounds + 1) for route in routes(args.date)]
            idle = _idle(page, recorder, base, args.cap)
        finally:
            browser.close()
    return {"meta": meta, "pages": pages, "idle": idle}


def main(argv=None, *, runner=None, env_path=None) -> int:
    args = parse_args(argv)
    meta = build_meta(args)
    try:
        credentials = load_credentials(env_path or default_env_path())
        raw = (runner or run_browser)(args, credentials)
    except LoginFailed as exc:
        print(f"probe: login failed: {exc}; nothing measured", file=sys.stderr)
        return 2
    raw["meta"] = {**meta, **raw.get("meta", {})}
    report = write_outputs(args.out, raw)
    print(f"probe: {report['label']} run, {len(raw['pages'])} pages -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/scripts/test_admin_browser_probe.py`
Expected: all pass, `0 failed`; `test_importing_the_probe_does_not_import_playwright` still passes (the import is inside `run_browser`).

- [ ] **Step 5: Smoke the CLI against nothing**

Run: `cd "<wt>" && python scripts/ops/admin_browser_probe.py --out x; echo "exit $?"`
Expected: argparse usage error naming `--date`, `exit 2`. No browser starts, nothing is written.

- [ ] **Step 6: Complexity gate**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: no new offender (`_wait_quiet` and `load_credentials` are the largest, under 6).

- [ ] **Step 7: Commit**

```bash
git -C "<wt>" add scripts/ops/admin_browser_probe.py tests/scripts/test_admin_browser_probe.py
git -C "<wt>" commit -m "feat(v206): browser probe CLI and Playwright loop, credentials never written (V206-2)"
```

### Task V206-3: Baseline probe run on production during a scan

**Model:** sonnet — an operational measurement run with read-only production commands and a results write-up; no code changes.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (`## Results` → new `### Plan 1 baseline (committed probe)`)

**Interfaces:**
- Consumes (V206-2): the probe CLI, `probe.json` (`report.label`, `report.goal`, `report.idle`) and `probe.md`.
- Produces (V206-13): the baseline section V206-13 compares against, run with `--date 2026-11-03` (the date the throwaway baseline pinned; V206-13 must pass the same), plus the output directory `<wt>/.superpowers/probe/v206-baseline/` (git-ignored).

This run measures **the code production runs today**, so it must finish before V206-13 pushes (index § Parallelisation). It counts as evidence only with label `scan` (every per-page sample saw `running: true`, spec Measurement rules); a `mixed` or `quiet` run is still recorded but is not the baseline. `/health` has no `sse_streams` before V206-4 deploys, so the stream count reads `-` here; that is expected. Production is touched read-only and only through `bash scripts/ops/ssh-hetzner.sh`; nothing on the VM changes, so `mirror-prod` does not apply. Credentials stay inside the probe; never echo `.env` values.

- [ ] **Step 1: Make sure the probe and Chromium are ready**

Run: `git -C "<wt>" log --oneline -3` and confirm the V206-2 commit is there.
Run: `python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(); b.close(); p.stop(); print('chromium ok')"`
Expected: `chromium ok`. If Chromium is missing, run `python -m playwright install chromium` and repeat.

- [ ] **Step 2: Wait for a scan, then confirm it from the VM**

The session scan runs during US hours (15:30–22:00 Berlin; Git Bash has no timezone data, so compute Berlin as `date -u` plus 1 h in winter). Check the running flag read-only:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -c 'from swingbot.core.scanning.runstate import is_scan_running; print(is_scan_running())'"
```

Expected: `True`. If `False`, wait and re-check every few minutes. Do not start a run on `False`: it will be labelled `quiet` or `mixed`.

- [ ] **Step 3: Read the production image tag**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps --format '{{.Image}}' admin"
```

Expected: one image reference. Keep it as `<tag>` for the next step.

- [ ] **Step 4: Run the probe in the background**

Three rounds of 12 pages at up to 90 s each plus the 120 s idle hold can take about an hour, so run it with `run_in_background` and wait for the exit notification (do not poll):

```bash
python "<wt>/scripts/ops/admin_browser_probe.py" --date 2026-11-03 --out "<wt>/.superpowers/probe/v206-baseline" --image-tag "<tag>" > "<wt>/.superpowers/probe/v206-baseline.log" 2>&1
```

Expected: exit 0 and the last log line `probe: scan run, 36 pages -> ...`. Exit 2 means the login failed; the log names the HTTP status only. Fix the cause (wrong `.env`, server down) and rerun from Step 2.

- [ ] **Step 5: Verify the run: label, shape, and no credential in the output**

```bash
python - "<wt>/.superpowers/probe/v206-baseline" "E:/Documents/Private/Projects/Discord-Bot/.env" <<'EOF'
import json, re, sys
from pathlib import Path
out, env = Path(sys.argv[1]), Path(sys.argv[2])
pattern = re.compile(r"\s*(ADMIN_USERNAME|ADMIN_PASSWORD)\s*=\s*(.*?)\s*$")
values = [m.group(2).strip('"').strip("'") for m in map(pattern.match, env.read_text(encoding="utf-8").splitlines()) if m]
texts = [(out / "probe.json").read_text(encoding="utf-8"), (out / "probe.md").read_text(encoding="utf-8")]
print("credentials absent:", len(values) == 2 and all(v not in t for v in values for t in texts))
report = json.loads(texts[0])["report"]
print("label:", report["label"], "| pages:", len(report["pages"]), "| idle rpm:", report["idle"]["rpm"])
assert report["label"] == "scan", "not a scan run: record it, then rerun from Step 2 during a scan"
assert len(report["pages"]) == 36
EOF
```

Expected: `credentials absent: True`, `label: scan | pages: 36 | idle rpm: <n>` and no assertion error. The script prints booleans and figures only, never a value from `.env`.

If the label is `mixed` or `quiet`: keep that run's directory (rename it `v206-baseline-<label>-1`), record it in Step 6 under the same heading marked "not evidence", and rerun from Step 2 during the next scan.

- [ ] **Step 6: Record the baseline in the spec**

In `<wt>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md`, append after the existing `### Baseline (2026-11-05, before v206)` subsection:

```markdown
### Plan 1 baseline (committed probe)

Before v206 Plan 1 deploys, with `scripts/ops/admin_browser_probe.py` at
`<probe_sha>`, against image `<tag>`, `<berlin_time>` Berlin, `--date 2026-11-03`,
3 rounds × 12 pages, cap 90 s, quiet 2 s. Label **scan** (every page sampled
`running: true`). Open SSE streams: not exposed before V206-4.

<the body of probe.md from "## Goal" to the end, with every "##" heading demoted to "####">
```

Fill the `<...>` fields from `probe.json` `report.meta`, and paste `probe.md` itself; do not retype any figure. Any `mixed` or `quiet` run from Step 5 goes below it as `#### Not evidence: <label> run, <berlin_time>` with its Goal lines only.

- [ ] **Step 7: Check the spec section reads back**

Run: `python scripts/dev/doc_section.py "<wt>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md" "Plan 1 baseline (committed probe)" | head -20`
Expected: the provenance paragraph and the `#### Goal` lines (exit 0; exit 2 means read the file at `## Results` directly).

- [ ] **Step 8: Commit**

```bash
git -C "<wt>" add docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
git -C "<wt>" commit -m "docs(v206): Plan 1 baseline with the committed browser probe, during a scan (V206-3)"
```

# Phase B — `/health` reports the stream count

### Task V206-4: `/health` reports `sse_streams`

**Model:** sonnet — one additive field on an existing route plus its contract test; no shared contract beyond the field name.

**Files:**
- Modify: `swingbot/admin/api_v1/session.py`
- Modify: `tests/admin/test_api_v1_session.py`
- Modify: `tests/admin/test_api_v1_dashboard.py` (its `test_health_carries_the_versions_and_the_market_session` pins the exact `/health` key set too; not in the index ledger's file list, test-only)

**Interfaces:**
- Consumes: `swingbot.admin.events.broker.get_broker()` and `EventBroker.connection_count` (both exist, `broker.py:190`, `:289`).
- Produces (V206-2's probe reads it into `meta.sse_streams`): `/api/v1/health` field `sse_streams: int` = `get_broker().connection_count`.

Spec Goal (Measurement rules): each result records the open SSE stream count, because gunicorn has 16 threads and each stream holds one; no endpoint exposes it today. The field is **additive** (Global Constraints: nothing removed, every other field byte-identical). The broker module is imported lazily inside the helper: `broker.py` imports `swingbot.admin.api_v1`, so a module-level import here would be circular. `get_broker()` builds the broker without starting a watcher (the watcher starts on the first `subscribe()`), so the call costs a lock and a `len()`.

The admin `client` fixture seeds the account store, so these tests need the shared `swing-db` container: run `/replicate-prod-db` first if no task in this session has (`skills-tools.md`).

- [ ] **Step 1: Measure complexity before**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: passes; note `health` in `swingbot/admin/api_v1/session.py` is a low single-digit function.

- [ ] **Step 2: Write the failing tests**

In `tests/admin/test_api_v1_session.py`, add `import pytest` at the top of the imports if it is not already there, then change the shape in `test_health_ok_with_basic_auth`:

```python
    assert_shape(
        r.get_json(),
        {"ok": bool, "versions": dict, "market_active": bool, "currency": str, "sse_streams": int},
    )
```

and, after `test_health_ok_with_basic_auth`, add:

```python
class _InertWatcher:
    def start(self):
        return self

    def stop(self):
        return None


@pytest.fixture
def broker(admin_app, monkeypatch):
    """A broker with an inert watcher, installed as the process singleton.

    Depends on `admin_app` so it is installed after the fixture's module
    reloads; `/health` imports the broker module at call time.
    """
    from swingbot.admin.events import broker as b
    made = b.EventBroker(watcher_factory=lambda emit: _InertWatcher())
    monkeypatch.setattr(b, "_BROKER", made)
    return made


def test_health_reports_the_open_event_stream_count(client, auth, broker):
    """v206: every probe result records the SSE thread budget (each stream holds a gunicorn thread)."""
    assert client.get("/api/v1/health", headers=auth).get_json()["sse_streams"] == 0
    with broker.subscribe(), broker.subscribe():
        body = client.get("/api/v1/health", headers=auth).get_json()
        assert body["sse_streams"] == broker.connection_count == 2
    assert client.get("/api/v1/health", headers=auth).get_json()["sse_streams"] == 0


def test_health_keeps_every_other_field_as_it_was(client, auth, broker):
    from swingbot import config
    from swingbot.admin import helpers

    body = client.get("/api/v1/health", headers=auth).get_json()
    body.pop("sse_streams")
    assert set(body) == {"ok", "versions", "market_active", "currency"}
    assert body["ok"] is True
    assert body["versions"] == helpers.get_versions()
    assert body["currency"] == config.CURRENCY_SYMBOL
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_session.py`
Expected: `test_health_ok_with_basic_auth` fails with `missing key(s) ['sse_streams']`; `test_health_reports_the_open_event_stream_count` fails with `KeyError: 'sse_streams'`.

- [ ] **Step 4: Add the field**

In `swingbot/admin/api_v1/session.py`, add above `@api_v1.route("/health", ...)`:

```python
def _sse_streams() -> int:
    """Open event streams in this process (v206 Measurement rules).

    Each stream holds a gunicorn thread for its whole life, so the count is
    the thread budget a probe result has to record. The broker module is
    imported here, not at the top: `broker.py` imports `api_v1`, so a
    module-level import would be circular.
    """
    from swingbot.admin.events import broker as _broker
    return _broker.get_broker().connection_count
```

and add the field as the last entry of the `jsonify({...})` dict in `health()`, after `"currency": config.CURRENCY_SYMBOL,`:

```python
        # v206: the open SSE stream count (additive). Each stream holds a
        # gunicorn thread, so the browser probe records it with every result.
        "sse_streams": _sse_streams(),
```

Add one line to `health()`'s docstring: `v206 adds `sse_streams`, the open event-stream count, for the browser probe.`

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_session.py`
Expected: all pass, `0 failed`.

- [ ] **Step 6: Update the second test that pins the health key set**

In `tests/admin/test_api_v1_dashboard.py`, `test_health_carries_the_versions_and_the_market_session` (around line 572), change the shape to:

```python
    assert_shape(
        body,
        {"ok": bool, "versions": dict, "market_active": bool, "currency": str, "sse_streams": int},
    )
```

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py`
Expected: all pass, `0 failed`.

Run: `git -C "<wt>" grep -n "\"currency\": str}" -- tests/`
Expected: no line that lacks `sse_streams` beside a `/health` body. If another one appears, give it the same `"sse_streams": int` entry and run that file alone.

- [ ] **Step 7: Complexity after**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: passes; `health` unchanged in complexity (the field adds no branch), `_sse_streams` is 1.

- [ ] **Step 8: Commit**

```bash
git -C "<wt>" add swingbot/admin/api_v1/session.py tests/admin/test_api_v1_session.py tests/admin/test_api_v1_dashboard.py
git -C "<wt>" commit -m "feat(v206): /health reports sse_streams, the open event-stream count (V206-4)"
```

