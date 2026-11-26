# v249 — Admin client data layer, part 1: baseline and server (V249-1..V249-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V249-2" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-25-v249-admin-client-data-layer-design.md](../specs/2026-11-25-v249-admin-client-data-layer-design.md)
**Index:** [2026-11-25-v249-admin-client-data-layer_0-index.md](2026-11-25-v249-admin-client-data-layer_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there and bind every task below.

Scope of this part: the read-only Playwright measurement script and the
production re-baseline after v250 (V249-1, the only task allowed to merge
before the start gate), the `dims=` multi-dimension form of
`/analytics/by-dimension` (V249-2), the deletion of the Dashboard's
`mode=today` client fallback (V249-3), and the Risk page taking its balance
from the `/risk` body it already reads (V249-4).

# Phase 1 — Measurement and the server form

### Task V249-1: Measurement script, pure half: steps, checkpoint, medians, off-hours guard

**Model:** sonnet — new pure helpers with a mechanical test file, modelled on an existing probe.

**Files:**
- Create: `scripts/dev/admin_data_layer_timing.py` (the pure top half; V249-1b appends the browser half and the CLI)
- Create: `tests/dev/test_admin_data_layer_timing.py` (suite `dev-setup`, whose `tests/dev/` path already exists; no `tests/suites.toml` edit)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (index ledger; V249-1b and close-out use them): `STEPS: tuple[str, ...]`; `TAB_STEPS: dict[str, str]` (step → tab label); `WIDTHS: dict[str, tuple[int, int]]`; `is_api_request(url: str) -> bool`; `select_steps(text: str) -> tuple[str, ...]`; `off_hours(now: datetime) -> bool`; `is_production(base_url: str) -> bool`; `load_rows(path: Path) -> list[dict]`; `append_rows(path: Path, rows: list[dict]) -> None`; `done_runs(rows, steps) -> set[tuple[str, int]]`; `pending_runs(done, widths, runs) -> list[tuple[str, int]]`; `summarise(rows) -> list[dict]` (median per step × width); `render_markdown(summary) -> str`; `progress(done, total) -> str`; JSONL row shape `{step, width, run, ttc_ms, idle_ms, requests, api_bytes}`.

Why this shape: spec § 6 measures cold Dashboard, Dashboard → Trades → Dashboard, Risk, every Analytics tab in turn plus the return to Overview, and 60 s idle on Dashboard, at phone 390×844 and desktop 1440×900, median of three runs. Spec § 7 (Ops and ownership) makes it read-only and off-hours (after the US close, clear of the 22:40 UTC jobs; the index pins 23:15–07:00 UTC on a weekday). CLAUDE.md says a run longer than a few minutes saves each finished unit to disk and skips it on restart. Here the unit is one (width, run) pass, so `done_runs` / `pending_runs` decide what a restart still owes. Tab labels come from `ANALYTICS_TAB_LIST` (`frontend/src/app/workspaces/analytics/analytics.ts:28-33`); `/api/v1/events` is the SSE stream, excluded as in `scripts/ops/admin_browser_probe.py:_is_api`.

- [ ] **Step 1: Write the failing tests**

Create `tests/dev/test_admin_data_layer_timing.py`:

```python
"""The v249 measurement script: pure helpers, the off-hours guard and the
restart checkpoint. The browser loop itself is exercised by the real
re-baseline run (V249-1b), never here."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
import admin_data_layer_timing as t  # noqa: E402


def _row(step, width="phone", run=1, ttc=100.0, idle=200.0, requests=2, api_bytes=1000):
    return {"step": step, "width": width, "run": run, "ttc_ms": ttc, "idle_ms": idle,
            "requests": requests, "api_bytes": api_bytes}


def test_is_api_request_counts_api_v1_but_not_the_stream_or_assets():
    assert t.is_api_request("https://bomeo-capital.com/api/v1/dashboard?mode=all")
    assert t.is_api_request("http://localhost:5000/api/v1/analytics/by-dimension?dim=strategy")
    assert not t.is_api_request("https://bomeo-capital.com/api/v1/events")
    assert not t.is_api_request("https://bomeo-capital.com/app/main.js")
    assert not t.is_api_request("https://bomeo-capital.com/api/v2/dashboard")


def test_steps_walk_the_spec_sequence():
    assert t.STEPS[:5] == ("cold-dashboard", "trades", "back-to-dashboard", "risk", "analytics-overview")
    for label in ("attribution", "execution", "edge", "pipeline", "tuning", "partials", "cancels", "benchmark"):
        assert f"analytics-{label}" in t.STEPS
    assert t.STEPS[-2:] == ("analytics-return-overview", "dashboard-idle-60s")
    assert len(set(t.STEPS)) == len(t.STEPS)
    assert t.TAB_STEPS["analytics-return-overview"] == "Overview"
    assert t.TAB_STEPS["analytics-cancels"] == "Cancels"
    assert t.WIDTHS == {"phone": (390, 844), "desktop": (1440, 900)}


def test_select_steps_adds_the_prerequisites_and_keeps_step_order():
    assert t.select_steps("risk") == ("cold-dashboard", "risk")
    assert t.select_steps("analytics-cancels,trades") == (
        "cold-dashboard", "trades", "analytics-overview", "analytics-cancels")


def test_select_steps_rejects_an_unknown_name():
    with pytest.raises(argparse.ArgumentTypeError, match="unknown step"):
        t.select_steps("cold-dashboard,warp-drive")


def test_summarise_takes_the_median_per_step_and_width_in_step_order():
    rows = [
        _row("risk", "desktop", 1, ttc=300), _row("risk", "desktop", 2, ttc=100), _row("risk", "desktop", 3, ttc=200),
        _row("cold-dashboard", "phone", 1, ttc=None, idle=50), _row("cold-dashboard", "phone", 2, ttc=40, idle=70),
        _row("risk", "phone", 1, ttc=10),
    ]
    summary = t.summarise(rows)
    assert [(s["step"], s["width"]) for s in summary] == [
        ("cold-dashboard", "phone"), ("risk", "phone"), ("risk", "desktop")]
    assert summary[2]["ttc_ms"] == 200 and summary[2]["runs"] == 3
    assert summary[0]["ttc_ms"] == 40          # a None (never rendered) is left out of the median
    assert summary[0]["idle_ms"] == 60


def test_summarise_reports_none_when_no_run_rendered():
    assert t.summarise([_row("risk", ttc=None)])[0]["ttc_ms"] is None


def test_render_markdown_puts_phone_then_desktop_in_each_cell():
    table = t.render_markdown(t.summarise([_row("risk", "desktop", ttc=20), _row("risk", "phone", ttc=10)]))
    assert "| risk | 10 / 20 | 200 / 200 | 2 / 2 | 1000 / 1000 |" in table
    assert t.render_markdown(t.summarise([_row("risk", ttc=None)])).count("| — |") == 1


def test_done_runs_needs_every_selected_step_and_pending_skips_them():
    steps = ("cold-dashboard", "risk")
    rows = [_row("cold-dashboard", "phone", 1), _row("risk", "phone", 1), _row("cold-dashboard", "desktop", 1)]
    done = t.done_runs(rows, steps)
    assert done == {("phone", 1)}
    assert t.pending_runs(done, ("phone", "desktop"), 2) == [("desktop", 1), ("phone", 2), ("desktop", 2)]


def test_append_then_load_round_trips_and_skips_a_line_cut_off_by_a_crash(tmp_path):
    path = tmp_path / "runs.jsonl"
    t.append_rows(path, [_row("risk")])
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"step": "tra')
    assert t.load_rows(path) == [_row("risk")]
    assert t.load_rows(tmp_path / "missing.jsonl") == []


@pytest.mark.parametrize("when, ok", [
    ("2026-12-01T23:20:00", True),    # Tuesday, after the US close
    ("2026-12-01T22:40:00", False),   # the nightly jobs
    ("2026-12-02T06:59:00", True),
    ("2026-12-02T07:00:00", False),
    ("2026-12-05T01:00:00", False),   # Saturday
])
def test_off_hours_window(when, ok):
    assert t.off_hours(datetime.fromisoformat(when).replace(tzinfo=timezone.utc)) is ok


def test_is_production_reads_the_host_only():
    assert t.is_production("https://bomeo-capital.com")
    assert t.is_production("https://www.bomeo-capital.com/")
    assert not t.is_production("http://localhost:5000")


def test_progress_is_a_whole_percent():
    assert t.progress(1, 6) == "16%" and t.progress(6, 6) == "100%" and t.progress(0, 0) == "100%"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_admin_data_layer_timing.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'admin_data_layer_timing'`.

- [ ] **Step 3: Write the pure half of the script**

Create `scripts/dev/admin_data_layer_timing.py`:

```python
"""Admin data-layer timing (v249 V249-1/V249-1b): before/after numbers for page memory.

Logs into the admin with Playwright and walks STEPS at phone (390x844) and
desktop (1440x900), one fresh browser context per run, recording per step:
time to content, idle (last /api/v1 call finished), request count and API
bytes. Spec: docs/superpowers/specs/2026-11-25-v249-admin-client-data-layer-design.md
sections 6 and 7 (Ops and ownership).

    python scripts/dev/admin_data_layer_timing.py --base-url https://bomeo-capital.com --out .superpowers/v249-timing/<run> [--runs 3] [--widths phone,desktop] [--steps risk,analytics-cancels] [--allow-any-hour]

READ-ONLY: every non-GET page request to /api/v1/ is aborted (the login goes
through the context's API client, not the page). Credentials come from `.env`
inside this process and are never printed. Against production it refuses to
start outside 23:15-07:00 UTC on a weekday unless --allow-any-hour. Each
finished (width, run) is appended to DIR/runs.jsonl in one write and skipped
on restart. The top half is pure and unit-tested; Playwright is imported lazily.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ANALYTICS_TABS = ("Overview", "Attribution", "Execution", "Edge", "Pipeline", "Tuning",
                  "Partials", "Cancels", "Benchmark")
TAB_STEPS = {**{f"analytics-{label.lower()}": label for label in ANALYTICS_TABS[1:]},
             "analytics-return-overview": "Overview"}
STEPS: tuple[str, ...] = ("cold-dashboard", "trades", "back-to-dashboard", "risk", "analytics-overview",
                          *(f"analytics-{label.lower()}" for label in ANALYTICS_TABS[1:]),
                          "analytics-return-overview", "dashboard-idle-60s")
WIDTHS = {"phone": (390, 844), "desktop": (1440, 900)}
PRODUCTION_HOST = "bomeo-capital.com"
ROWS_FILE, SUMMARY_FILE = "runs.jsonl", "summary.md"
FIELDS = ("ttc_ms", "idle_ms", "requests", "api_bytes")


def is_api_request(url: str) -> bool:
    """A counted call: under /api/v1/ and not the SSE stream."""
    path = urlsplit(url).path
    return path.startswith("/api/v1/") and path.rstrip("/") != "/api/v1/events"


def select_steps(text: str) -> tuple[str, ...]:
    """`--steps`: known names only, in STEPS order, with the walk's prerequisites added."""
    names = {name.strip() for name in text.split(",") if name.strip()}
    unknown = sorted(names - set(STEPS))
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown step(s) {unknown}; known: {list(STEPS)}")
    names.add("cold-dashboard")                       # every run starts with a loaded app
    if any(name in TAB_STEPS for name in names):
        names.add("analytics-overview")               # a tab is clicked inside Analytics
    return tuple(step for step in STEPS if step in names)


def widths_arg(text: str) -> tuple[str, ...]:
    """`--widths`: names from WIDTHS, comma separated."""
    names = tuple(name.strip() for name in text.split(",") if name.strip())
    if not names or any(name not in WIDTHS for name in names):
        raise argparse.ArgumentTypeError(f"widths must be from {list(WIDTHS)}")
    return names


def off_hours(now: datetime) -> bool:
    """23:15-07:00 UTC on a weekday: after the US close, clear of the 22:40 UTC jobs."""
    now = now.astimezone(timezone.utc)
    minutes = now.hour * 60 + now.minute
    return now.weekday() < 5 and (minutes >= 23 * 60 + 15 or minutes < 7 * 60)


def is_production(base_url: str) -> bool:
    return (urlsplit(base_url).hostname or "").endswith(PRODUCTION_HOST)


def load_rows(path: Path) -> list[dict]:
    """Every complete JSONL row; a line cut off by a crash is skipped."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_rows(path: Path, rows: list[dict]) -> None:
    """One write per finished run, so a crash never leaves half a run looking done."""
    with path.open("a", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(row) + "\n" for row in rows))


def done_runs(rows: list[dict], steps: tuple[str, ...]) -> set[tuple[str, int]]:
    """(width, run) pairs with every selected step on disk: a restart skips them."""
    seen: dict[tuple[str, int], set[str]] = {}
    for row in rows:
        seen.setdefault((row["width"], row["run"]), set()).add(row["step"])
    return {key for key, got in seen.items() if set(steps) <= got}


def pending_runs(done: set[tuple[str, int]], widths: tuple[str, ...], runs: int) -> list[tuple[str, int]]:
    return [(width, run) for run in range(1, runs + 1) for width in widths if (width, run) not in done]


def _median(values: list) -> float | None:
    known = [value for value in values if value is not None]
    return round(statistics.median(known), 1) if known else None


def summarise(rows: list[dict]) -> list[dict]:
    """Median per step x width (a None is left out), in STEPS then WIDTHS order."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["step"], row["width"]), []).append(row)
    step_at = {step: i for i, step in enumerate(STEPS)}
    width_at = {width: i for i, width in enumerate(WIDTHS)}
    keys = sorted(groups, key=lambda k: (step_at.get(k[0], len(step_at)), width_at.get(k[1], len(width_at))))
    return [{"step": step, "width": width, "runs": len(groups[(step, width)]),
             **{field: _median([row.get(field) for row in groups[(step, width)]]) for field in FIELDS}}
            for step, width in keys]


def _cell(summary: list[dict], step: str, field: str) -> str:
    values = [row[field] for width in WIDTHS for row in summary if row["step"] == step and row["width"] == width]
    return " / ".join("—" if value is None else f"{value:.0f}" for value in values) or "—"


def render_markdown(summary: list[dict]) -> str:
    """The spec's baseline table: one row per step, phone / desktop in each cell."""
    lines = ["| Step | Time to content ms | Idle ms | Req | API bytes |", "|---|---|---|---|---|"]
    for step in (s for s in STEPS if any(row["step"] == s for row in summary)):
        lines.append(f"| {step} | " + " | ".join(_cell(summary, step, field) for field in FIELDS) + " |")
    return "\n".join(lines) + "\n"


def progress(done: int, total: int) -> str:
    return f"{100 * done // total if total else 100}%"
```

- [ ] **Step 4: Run the tests to verify they pass, and the complexity gate**

Run: `python scripts/dev/testrun.py file tests/dev/test_admin_data_layer_timing.py`
Expected: PASS (all tests).

Run: `python scripts/dev/complexity_gate.py`
Expected: no function in `scripts/dev/admin_data_layer_timing.py` at or above 15.

- [ ] **Step 5: Commit**

```bash
git add scripts/dev/admin_data_layer_timing.py tests/dev/test_admin_data_layer_timing.py
git commit -m "feat(dev): v249 timing script pure half -- steps, run checkpoint, medians, off-hours guard"
```

### Task V249-1b: Measurement script, browser half + CLI; local smoke; production re-baseline after v250

**Model:** sonnet — Playwright glue copied from an existing probe's pattern, two small tests, then a gated run and a doc edit.

**Files:**
- Modify: `scripts/dev/admin_data_layer_timing.py` (created by V249-1: import block replaced, browser half and CLI appended)
- Modify: `tests/dev/test_admin_data_layer_timing.py` (created by V249-1: three tests appended)
- Modify: `docs/superpowers/specs/2026-11-25-v249-admin-client-data-layer-design.md` (Step 8 only, after v250 deploys)

**Interfaces:**
- Consumes: everything V249-1 produced (`STEPS`, `TAB_STEPS`, `WIDTHS`, `is_api_request`, `select_steps`, `widths_arg`, `off_hours`, `is_production`, `load_rows`, `append_rows`, `done_runs`, `pending_runs`, `summarise`, `render_markdown`, `progress`, `ROWS_FILE`, `SUMMARY_FILE`); `LoginFailed`, `default_env_path()`, `load_credentials(env_path) -> tuple[str, str]` from `scripts/ops/admin_browser_probe.py` (exist; imported by putting `scripts/ops` on `sys.path`, the way `tests/dev/test_hold_status.py` imports from `scripts/dev`).
- Produces (index ledger): the CLI `python scripts/dev/admin_data_layer_timing.py --base-url URL --out DIR [--runs 3] [--widths phone,desktop] [--steps …] [--allow-any-hour]`, writing `DIR/runs.jsonl` and `DIR/summary.md`; `main(argv=None, *, runner=None, env_path=None, now=None) -> int`; `run_browser(args, credentials, rows_path) -> None`.

Navigation uses `history.pushState` + `popstate`. That is the router path a rail link takes, without a reload, and it works at 390 px, where the rail is a different control. Analytics tabs are clicked by role (`[role="tab"]`, `frontend/src/app/ui/layout.ts:259`). Time to content is when the first `main.workspace sb-async .content` becomes visible after the URL changed (`frontend/scripts/admin-page-timing.mjs` waits on the same selector). The write guard and login copy `admin-page-timing.mjs:guardWrites` and `admin_browser_probe.py:_login`: the login goes through `context.request` (not a page request, so the page-level route guard never sees it) and its cookies carry into each fresh run context through `storage_state`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/dev/test_admin_data_layer_timing.py`:

```python
ENV = "ADMIN_USERNAME=partner\nADMIN_PASSWORD=s3cret-value\n"


def test_calls_count_only_api_gets_and_sum_their_bytes():
    class Req:
        def __init__(self, url, method="GET", size=500):
            self.url, self.method, self._size = url, method, size

        def sizes(self):
            return {"responseBodySize": self._size}

    calls = t._Calls(clock=iter([0.0, 0.1]).__next__)
    api, post, stream = Req("https://h/api/v1/risk"), Req("https://h/api/v1/x", "POST"), Req("https://h/api/v1/events")
    for req in (api, post, stream):
        calls.on_request(req)
    assert calls.in_flight() == 1
    calls.on_finished(api)
    assert calls.in_flight() == 0
    assert calls.facts() == {"idle_ms": 100.0, "requests": 1, "api_bytes": 500}


def test_main_refuses_production_inside_trading_hours(tmp_path):
    env = tmp_path / ".env"
    env.write_text(ENV, encoding="utf-8")
    ran = []
    code = t.main(["--base-url", "https://bomeo-capital.com", "--out", str(tmp_path / "out")],
                  runner=lambda *a: ran.append(a), env_path=env,
                  now=datetime(2026, 12, 1, 15, 0, tzinfo=timezone.utc))
    assert code == 2 and ran == []


def test_main_runs_writes_the_summary_and_never_prints_credentials(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(ENV, encoding="utf-8")
    seen = {}

    def runner(args, credentials, rows_path):
        seen["credentials"], seen["steps"] = credentials, args.steps
        t.append_rows(rows_path, [_row("cold-dashboard", "phone", 1), _row("risk", "phone", 1)])

    code = t.main(["--base-url", "http://localhost:5000", "--out", str(tmp_path / "out"), "--steps", "risk"],
                  runner=runner, env_path=env)
    assert code == 0
    assert seen == {"credentials": ("partner", "s3cret-value"), "steps": ("cold-dashboard", "risk")}
    assert "| risk |" in (tmp_path / "out" / "summary.md").read_text(encoding="utf-8")
    printed = capsys.readouterr()
    assert "s3cret-value" not in printed.out + printed.err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_admin_data_layer_timing.py`
Expected: the three new tests FAIL with `AttributeError: module 'admin_data_layer_timing' has no attribute '_Calls'` / `'main'`; V249-1's tests still pass.

- [ ] **Step 3: Replace the import block**

In `scripts/dev/admin_data_layer_timing.py`, replace the import block with:

```python
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
from admin_browser_probe import LoginFailed, default_env_path, load_credentials  # noqa: E402
```

- [ ] **Step 4: Append the browser half and the CLI**

Append to the end of `scripts/dev/admin_data_layer_timing.py`:

```python
ROUTES = {"trades": "/trades", "back-to-dashboard": "/dashboard", "risk": "/risk",
          "analytics-overview": "/insights/analytics", "dashboard-idle-60s": "/dashboard"}
CONTENT = "main.workspace sb-async .content"
CONTENT_TIMEOUT_MS = 60_000
QUIET_S = 1.5
QUIET_CAP_S = 60.0
IDLE_WINDOW_S = 60


class _Calls:
    """GET /api/v1 calls the page starts, timed from the step's mark."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.t0 = clock()
        self.calls: dict[int, dict] = {}

    def mark(self) -> None:
        self.t0, self.calls = self._clock(), {}

    def now_ms(self) -> float:
        return round((self._clock() - self.t0) * 1000, 1)

    def on_request(self, request) -> None:
        if request.method == "GET" and is_api_request(request.url):
            self.calls[id(request)] = {"end_ms": None, "bytes": 0}

    def on_finished(self, request) -> None:
        call = self.calls.get(id(request))
        if call is None:
            return
        call["end_ms"] = self.now_ms()
        try:
            call["bytes"] = int(request.sizes()["responseBodySize"])
        except Exception:  # noqa: BLE001 -- a closed page loses the size, never the call
            call["bytes"] = 0

    def on_failed(self, request) -> None:
        call = self.calls.get(id(request))
        if call is not None:
            call["end_ms"] = self.now_ms()

    def in_flight(self) -> int:
        return sum(1 for call in self.calls.values() if call["end_ms"] is None)

    def facts(self) -> dict:
        ends = [call["end_ms"] for call in self.calls.values() if call["end_ms"] is not None]
        return {"idle_ms": max(ends) if ends else 0.0, "requests": len(self.calls),
                "api_bytes": sum(call["bytes"] for call in self.calls.values())}


# ---------------------------------------------------------------- browser side

def _wait_quiet(page, calls: _Calls) -> None:
    quiet_since, deadline = None, time.monotonic() + QUIET_CAP_S
    while time.monotonic() < deadline:
        page.wait_for_timeout(100)
        if calls.in_flight():
            quiet_since = None
        elif quiet_since is None:
            quiet_since = time.monotonic()
        elif time.monotonic() - quiet_since >= QUIET_S:
            return


def _act(page, base: str, step: str) -> str | None:
    """Start the step; returns the URL to wait away from (None on the cold load)."""
    if step == "cold-dashboard":
        page.goto(f"{base}/dashboard", wait_until="commit")
        return None
    before = page.url
    if step in ROUTES:
        page.evaluate("p => { history.pushState({}, '', p); dispatchEvent(new PopStateEvent('popstate')); }",
                      ROUTES[step])
    else:
        page.get_by_role("tab", name=TAB_STEPS[step], exact=True).click()
    return before


def _time_to_content(page, calls: _Calls, before: str | None) -> float | None:
    try:
        if before is not None:
            page.wait_for_function("u => location.href !== u", arg=before, timeout=CONTENT_TIMEOUT_MS)
        page.locator(CONTENT).first.wait_for(state="visible", timeout=CONTENT_TIMEOUT_MS)
    except Exception:  # noqa: BLE001 -- never rendered is recorded as None, never dropped
        return None
    return calls.now_ms()


def _measure(page, calls: _Calls, base: str, step: str) -> dict:
    calls.mark()
    ttc = _time_to_content(page, calls, _act(page, base, step))
    _wait_quiet(page, calls)
    if step != "dashboard-idle-60s":
        return {"ttc_ms": ttc, **calls.facts()}
    calls.mark()                                      # the 60 s idle window starts once settled
    page.wait_for_timeout(IDLE_WINDOW_S * 1000)
    return {"ttc_ms": None, **calls.facts(), "idle_ms": IDLE_WINDOW_S * 1000}


def _guard_writes(context, aborted: list[int]) -> None:
    def handle(route) -> None:
        if route.request.method in ("GET", "HEAD"):
            route.continue_()
            return
        aborted[0] += 1
        route.abort()
    context.route("**/api/v1/**", handle)


def _login(browser, base: str, credentials: tuple[str, str]) -> dict:
    context = browser.new_context(service_workers="block")
    try:
        user, password = credentials
        try:
            response = context.request.post(f"{base}/api/v1/session", data={"username": user, "password": password})
        except Exception as exc:  # network/TLS: the type only, its text may echo the request
            raise LoginFailed(f"request error: {type(exc).__name__}") from None
        if response.status != 200:
            raise LoginFailed(f"HTTP {response.status}")
        return context.storage_state()
    finally:
        context.close()


def _run_once(browser, storage: dict, base: str, width: str, run: int, steps, aborted) -> list[dict]:
    w, h = WIDTHS[width]
    context = browser.new_context(viewport={"width": w, "height": h}, storage_state=storage,
                                  service_workers="block")
    try:
        _guard_writes(context, aborted)
        page, calls = context.new_page(), _Calls()
        page.on("request", calls.on_request)
        page.on("requestfinished", calls.on_finished)
        page.on("requestfailed", calls.on_failed)
        return [{"step": step, "width": width, "run": run, **_measure(page, calls, base, step)} for step in steps]
    finally:
        context.close()


def run_browser(args, credentials: tuple[str, str], rows_path: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright  # lazy: not a declared dependency
    except ImportError:
        raise LoginFailed("playwright is not installed") from None
    todo = pending_runs(done_runs(load_rows(rows_path), args.steps), args.widths, args.runs)
    total, base, aborted = len(args.widths) * args.runs, args.base_url.rstrip("/"), [0]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            storage = _login(browser, base, credentials)
            for i, (width, run) in enumerate(todo, start=1):
                append_rows(rows_path, _run_once(browser, storage, base, width, run, args.steps, aborted))
                print(f"timing: {progress(total - len(todo) + i, total)} {width} run {run} saved", flush=True)
        finally:
            browser.close()
    print(f"timing: non-GET requests aborted: {aborted[0]}")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Admin data-layer timing (v249).")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", required=True, type=Path, help="directory for runs.jsonl and summary.md")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--widths", type=widths_arg, default=tuple(WIDTHS))
    parser.add_argument("--steps", type=select_steps, default=STEPS)
    parser.add_argument("--allow-any-hour", action="store_true", help="skip the production off-hours guard")
    return parser.parse_args(argv)


def main(argv=None, *, runner=None, env_path=None, now=None) -> int:
    args = parse_args(argv)
    if is_production(args.base_url) and not args.allow_any_hour \
            and not off_hours(now or datetime.now(timezone.utc)):
        print("timing: production runs only 23:15-07:00 UTC on a weekday", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    rows_path = args.out / ROWS_FILE
    try:
        (runner or run_browser)(args, load_credentials(env_path or default_env_path()), rows_path)
    except LoginFailed as exc:
        print(f"timing: login failed: {exc}; nothing measured", file=sys.stderr)
        return 2
    table = render_markdown(summarise(load_rows(rows_path)))
    (args.out / SUMMARY_FILE).write_text(table, encoding="utf-8")
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests and the complexity gate**

Run: `python scripts/dev/testrun.py file tests/dev/test_admin_data_layer_timing.py`
Expected: PASS (all tests, V249-1's and the three new ones).

Run: `python scripts/dev/complexity_gate.py`
Expected: no function in `scripts/dev/admin_data_layer_timing.py` at or above 15.

- [ ] **Step 6: Smoke the browser half against a local admin, then commit**

Start a local admin built from `.env` values (never `admin`/`admin`; `docs/claude/skills-tools.md`), then:

Run: `python scripts/dev/admin_data_layer_timing.py --base-url http://localhost:5000 --out .superpowers/v249-timing/local-smoke --runs 1 --widths desktop --steps risk`
Expected: `timing: 100% desktop run 1 saved`, `timing: non-GET requests aborted: <n>`, and a two-row table (`cold-dashboard`, `risk`) with a number in every cell. Running the same command again prints the table without a `saved` line, because the finished run is read back from disk and skipped. `.superpowers/` is not committed.

```bash
git add scripts/dev/admin_data_layer_timing.py tests/dev/test_admin_data_layer_timing.py
git commit -m "feat(dev): v249 timing script browser half -- read-only guard, fresh context per run, CLI"
```

- [ ] **Step 7: Re-baseline production after v250 deploys (start gate)**

Only once v250 is deployed (confirm read-only with `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps"` and the image tag in the deploy log), between 23:15 and 07:00 UTC on a weekday:

Run: `python scripts/dev/admin_data_layer_timing.py --base-url https://bomeo-capital.com --out .superpowers/v249-timing/after-v250`
Expected: percent lines up to `100%`, an aborted-request count (the guard working, never an error), then the summary table. If interrupted, run the same command again; finished runs are skipped.

- [ ] **Step 8: Record the re-baseline in the spec and commit**

In `docs/superpowers/specs/2026-11-25-v249-admin-client-data-layer-design.md`, rename the heading `### Baseline (production, before)` to `### Baseline (production, before v250 — history)`. Directly above it, insert a new section `### Baseline (production, after v250)` holding: one line with the date, the UTC window, the v250 image tag and the script path `scripts/dev/admin_data_layer_timing.py`; the pasted `summary.md` table; and one sentence for each step whose numbers moved by more than 2× against the history table. Do not edit any other section.

```bash
git add docs/superpowers/specs/2026-11-25-v249-admin-client-data-layer-design.md
git commit -m "docs(v249): production re-baseline after v250 (start gate for V249-2..18)"
```

### Task V249-2: `/analytics/by-dimension?dims=` multi-dimension form: trades scoped once, per-block error, split the cc 33 handler

**Model:** opus — a behaviour-preserving split of a cc 33 handler plus a new response contract another part's client is written against.

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py:216-318` (`analytics_by_dimension` and new helpers just above it)
- Modify: `tests/admin/test_api_v1_analytics.py` (new tests appended after `test_by_dimension_strategy_rows_carry_soak_key`, ~:388)
- Modify: `scripts/dev/complexity_baseline.json` (only through `complexity_gate.py --update`, which can only shrink it)

**Interfaces:**
- Consumes: nothing from earlier tasks. Existing: `_scope(extra)` (:77), `_all_trades` (:91), `_soak_for(strategy)` (:171), `closed_only` (module import), `swallowed(log, tag, exc, level=, exc_info=)` (`swingbot/core/infra/swallowed.py:62`), `ApiError(code, message, status)`.
- Produces (index ledger, Global Constraints "Server envelope"): `GET /api/v1/analytics/by-dimension?dims=a,b,…&<scope>` → 200 `{"blocks": {"a": <body identical to ?dim=a>, "b": {"error": {"code": "dimension_failed", "message": "<ExcType>: <msg>"}}}}`; duplicates collapsed; all blocks failing → `ApiError("dimension_failed", …, 500)`; an unknown name, an empty list, or `dim` and `dims` together → `ApiError("invalid", …, 400)`. Helpers `_dimension_body(scoped: list[dict], scope, dim: str) -> dict`, `_dims_param() -> list[str] | None`, `_multi_dimension_body(scoped, scope, dims: list[str]) -> dict`; also `_scoped_closed(scope) -> list[dict]`, `_dimension_groups(scoped, dim) -> dict`, `_dimension_keys(groups, dim) -> list`, `_dimension_row(key, trades, dim) -> dict`, `_rate_fields(trades) -> dict`, `_strategy_extras(key) -> dict`.

**Start gate (index Global Constraints).** Written against HEAD 02441aa9. Before editing, run `git grep -n "read_scope\|default_view_body\|conditional" -- swingbot/admin/api_v1/analytics.py`. If v250 wrapped `analytics_by_dimension` (a decorator, or its body passed through `default_view_body`), keep that wrapper exactly on the single `?dim=` path and send every `dims=` block through the same `_dimension_body` call the single path makes. The "dims equals four single calls block for block" test decides it.

**Key order on the wire.** `_multi_dimension_body` builds `blocks` in request order, but Flask 3's default JSON provider sorts keys (`sort_keys=True`; nothing in `swingbot/admin` overrides it), so the serialized object comes out alphabetical. The client reads blocks by name (V249-11), so the tests compare key *sets* and never the order. Do not change the app's JSON provider.

**Why not loop over the route.** Spec § 7 (Server side): the multi form loads and scopes the closed trades **once** and groups per dimension. Looping over the single handler would hold an admin request thread about 4× as long. `as_of` stays per block, computed from that dimension's surviving groups (the docstring's "as_of is scoped to the trades that actually survived grouping" rule). `fx_missing_count` and the scope echo are per block too, so every block is byte-for-byte the single body.

- [ ] **Step 1: Capture today's single-form bodies (characterization, never committed)**

Create the temporary file `tests/admin/test_v249_capture_tmp.py`:

```python
"""V249-2 Step 1/6 only -- deleted before the commit. Pins every ?dim= body as raw text."""
import json
import os
import pathlib

from swingbot.core.analytics.aggregate import DIMENSIONS
from tests.admin.test_api_v1_analytics import _closed, logged_in, seed  # noqa: F401 -- fixtures

_BOOK = [
    _closed("a" * 16, strategy="MACD", horizon_key="4w"),
    _closed("b" * 16, status="loss", direction="bearish", strategy="RSI Divergence", horizon_key="2w",
            closed_at="2026-08-05T15:00:00+00:00"),
    _closed("c" * 16, horizon_key="legacy", closed_at="2026-08-06T15:00:00+00:00"),
]


def test_capture_single_dim_bodies(seed, logged_in):
    seed(trades=_BOOK)
    bodies = {dim: logged_in.get(f"/api/v1/analytics/by-dimension?dim={dim}").get_data(as_text=True)
              for dim in DIMENSIONS}
    bodies["scoped"] = logged_in.get(
        "/api/v1/analytics/by-dimension?dim=horizon&direction=bullish").get_data(as_text=True)
    path = pathlib.Path(os.environ["V249_CAPTURE"])
    if path.exists():
        assert json.loads(path.read_text(encoding="utf-8")) == bodies
    else:
        path.write_text(json.dumps(bodies), encoding="utf-8")
```

Run `/replicate-prod-db` once this session if no sibling task did (`tests/admin/` reaches Postgres), then:

Run: `V249_CAPTURE=.superpowers/v249-by-dimension-before.json python scripts/dev/testrun.py file tests/admin/test_v249_capture_tmp.py`
Expected: PASS, and `.superpowers/v249-by-dimension-before.json` now exists (first run writes it).

- [ ] **Step 2: Write the failing tests**

Append to `tests/admin/test_api_v1_analytics.py`, after `test_by_dimension_strategy_rows_carry_soak_key`:

```python
# ---------------------------------------------------------------------------
# v249 V249-2: ?dims= -- several dimensions in one request, trades scoped once
# ---------------------------------------------------------------------------
_FOUR = ("strategy", "horizon", "direction", "dow")


def _dims_book():
    """Three closes; `c` has a horizon outside HORIZONS, so only the horizon
    block drops it -- its as_of differs from the other blocks'."""
    return [
        _closed("a" * 16, strategy="MACD", horizon_key="4w"),
        _closed("b" * 16, status="loss", direction="bearish", strategy="RSI Divergence", horizon_key="2w",
                closed_at="2026-08-05T15:00:00+00:00"),
        _closed("c" * 16, horizon_key="legacy", closed_at="2026-08-06T15:00:00+00:00"),
    ]


@pytest.mark.parametrize("scope", ["", "&direction=bullish"])
def test_dims_equals_the_four_single_calls_block_for_block(seed, logged_in, scope):
    seed(trades=_dims_book())
    response = logged_in.get(f"/api/v1/analytics/by-dimension?dims={','.join(_FOUR)}{scope}")
    assert response.status_code == 200
    blocks = response.get_json()["blocks"]
    assert set(blocks) == set(_FOUR)
    for dim in _FOUR:
        assert blocks[dim] == logged_in.get(f"/api/v1/analytics/by-dimension?dim={dim}{scope}").get_json(), dim


def test_dims_keeps_as_of_per_block_and_collapses_duplicates(seed, logged_in):
    seed(trades=_dims_book())
    body = logged_in.get("/api/v1/analytics/by-dimension?dims=horizon,horizon,%20dow").get_json()
    assert set(body["blocks"]) == {"horizon", "dow"}
    assert body["blocks"]["horizon"]["as_of"] == "2026-08-05"   # the legacy-horizon close is dropped here only
    assert body["blocks"]["dow"]["as_of"] == "2026-08-06"
    assert body["blocks"]["dow"]["n"] == 3


def test_dims_loads_and_scopes_the_closed_trades_once(seed, logged_in, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog

    seed(trades=_dims_book())
    calls = []
    original = TradeLog.get_trades

    def counting(self, *args, **kwargs):
        calls.append(kwargs.get("status"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TradeLog, "get_trades", counting)
    assert logged_in.get(f"/api/v1/analytics/by-dimension?dims={','.join(_FOUR)}").status_code == 200
    assert len(calls) == 1, f"get_trades called {len(calls)} times: {calls}"


def _failing_for(monkeypatch, failing):
    from swingbot.admin.api_v1 import analytics as analytics_api

    real = analytics_api._dimension_groups

    def flaky(scoped, dim):
        if dim in failing:
            raise ValueError(f"no {dim}")
        return real(scoped, dim)

    monkeypatch.setattr(analytics_api, "_dimension_groups", flaky)


def test_dims_answers_a_failing_dimension_with_its_own_error_block(seed, logged_in, monkeypatch):
    seed(trades=_dims_book())
    _failing_for(monkeypatch, {"dow"})
    response = logged_in.get("/api/v1/analytics/by-dimension?dims=strategy,dow")
    assert response.status_code == 200
    blocks = response.get_json()["blocks"]
    assert blocks["dow"] == {"error": {"code": "dimension_failed", "message": "ValueError: no dow"}}
    assert [row["key"] for row in blocks["strategy"]["rows"]]          # the other block is whole


def test_dims_is_a_500_when_every_dimension_fails(seed, logged_in, monkeypatch):
    seed(trades=_dims_book())
    _failing_for(monkeypatch, {"strategy", "dow"})
    assert_error(logged_in.get("/api/v1/analytics/by-dimension?dims=strategy,dow"), "dimension_failed", 500)


@pytest.mark.parametrize("query", [
    "dims=strategy,tier",              # an unknown name fails the whole request
    "dims=",                           # an empty list
    "dims=%20,%20",                    # only blanks
    "dim=strategy&dims=horizon",       # both forms at once
])
def test_dims_rejects_unknown_empty_or_mixed(logged_in, query):
    assert_error(logged_in.get(f"/api/v1/analytics/by-dimension?{query}"), "invalid", 400)


def test_dims_requires_auth(client):
    assert_error(client.get("/api/v1/analytics/by-dimension?dims=strategy"), "auth", 401)


def test_dims_still_rejects_an_unknown_parameter(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/by-dimension?dims=strategy&bogus=1"), "invalid", 400)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: FAIL. The `dims=` tests get a 400 (`dims` is rejected as an unknown parameter by `reject_unknown`), `_failing_for` raises `AttributeError: ... has no attribute '_dimension_groups'`, and `test_dims_rejects_unknown_empty_or_mixed`, `test_dims_requires_auth` and `test_dims_still_rejects_an_unknown_parameter` already pass. The existing tests pass.

- [ ] **Step 4: Split the handler and add the multi form**

In `swingbot/admin/api_v1/analytics.py`, insert these helpers directly above `@api_v1.route("/analytics/by-dimension", ...)`:

```python
_DIMENSION_FAILED = "dimension_failed"


def _scoped_closed(scope) -> list[dict]:
    """The scoped closed trades in the account currency: loaded once per request."""
    from swingbot.core.analytics.scope import select

    from .money import to_account_currency
    return select(to_account_currency(closed_only(_all_trades(TradeLog()))), scope)


def _dimension_groups(scoped: list[dict], dim: str) -> dict:
    """Group the scoped trades for one dimension (strategy by its real label, horizon by HORIZONS only)."""
    from swingbot.core.analytics.aggregate import group_by
    from swingbot.core.market.strategy_types import HORIZONS
    from swingbot.core.tracking.performance import primary_strategy_label

    if dim == "strategy":            # the real per-trade label, as before
        groups: dict[str, list[dict]] = {}
        for t in scoped:
            groups.setdefault(primary_strategy_label(t), []).append(t)
        return groups
    if dim == "horizon":
        return {k: v for k, v in group_by(scoped, dim).items() if k in HORIZONS}
    return group_by(scoped, dim)


def _dimension_keys(groups: dict, dim: str) -> list:
    """Horizon by progression, month by date, everything else by size then name."""
    from swingbot.core.market.strategy_types import HORIZONS

    if dim == "horizon":
        order = {h: i for i, h in enumerate(HORIZONS)}
        return sorted(groups, key=lambda k: order.get(k, len(order)))
    if dim == "month":
        return sorted(groups)
    return sorted(groups, key=lambda k: (-len(groups[k]), str(k)))


def _rate_fields(trades: list[dict]) -> dict:
    """The five rate fields; null under MIN_CELL_N (spec v94 D7/H1)."""
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.aggregate import MIN_CELL_N

    thin = len(trades) < MIN_CELL_N
    fns = {"exp_r": m.expectancy_r, "win_rate": m.win_rate, "profit_factor": m.profit_factor,
           "avg_win_r": m.avg_win_r, "avg_loss_r": m.avg_loss_r}
    return {key: None if thin else fn(trades) for key, fn in fns.items()}


def _strategy_extras(key) -> dict:
    """`badge` and `soak` for a dim=strategy row (v93 Task 13)."""
    from swingbot.core.backtesting.registry import get_badge

    verdict, _ = _soak_for(key)
    return {"badge": get_badge("strategy", key).status,
            "soak": {"pass": verdict["pass"], "n_closed": verdict["n_closed"],
                     "clauses": verdict["clauses"]} if verdict["n_closed"] else None}


def _dimension_row(key, trades: list[dict], dim: str) -> dict:
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.risk_metrics import max_drawdown_r

    ordered = sorted(trades, key=lambda t: t.get("closed_at") or "")
    rs = [r for t in ordered if (r := m.r_multiple(t)) is not None]
    row = {
        "key": str(key), "n": len(trades),
        "wins": sum(1 for t in trades if t.get("status") == "win"),
        "losses": sum(1 for t in trades if t.get("status") == "loss"),
        **_rate_fields(trades),
        "total_r": (round(sum(rs), 4) if rs else None),
        "total_pnl": round(sum(float(t.get("realized_pnl_amount") or 0.0) for t in trades), 2),
        "max_drawdown_r": max_drawdown_r(rs),
    }
    if dim == "strategy":
        row.update(_strategy_extras(key))
    return row


def _dimension_body(scoped: list[dict], scope, dim: str) -> dict:
    """One dimension's whole body -- the `?dim=` response and each `?dims=` block alike."""
    from swingbot.core.analytics.aggregate import MIN_CELL_N
    from swingbot.core.analytics.scope import echo

    from .money import missing_count

    groups = _dimension_groups(scoped, dim)
    rows = [_dimension_row(key, groups[key], dim) for key in _dimension_keys(groups, dim)]
    dated = [t["closed_at"][:10] for trades in groups.values() for t in trades if t.get("closed_at")]
    return {"rows": rows, "as_of": max(dated) if dated else None,
            "min_cell_n": MIN_CELL_N, "fx_missing_count": missing_count(scoped),
            **echo(scope, len(scoped))}


def _dims_param() -> list[str] | None:
    """`?dims=a,b`: names in request order, duplicates collapsed; None when absent.

    An unknown name, an empty list, or `dim` beside it is a 400 for the whole
    request, as an unknown `dim` is today."""
    from swingbot.core.analytics.aggregate import DIMENSIONS

    if "dims" not in request.args:
        return None
    if "dim" in request.args:
        raise ApiError("invalid", "pass dim or dims, not both", 400)
    names = list(dict.fromkeys(n.strip() for n in request.args.get("dims", "").split(",") if n.strip()))
    if not names:
        raise ApiError("invalid", f"dims must name at least one of {list(DIMENSIONS)}", 400)
    unknown = [n for n in names if n not in DIMENSIONS]
    if unknown:
        raise ApiError("invalid", f"dims must be from {list(DIMENSIONS)}, got {unknown[0]!r}", 400)
    return names


def _multi_dimension_body(scoped: list[dict], scope, dims: list[str]) -> dict:
    """One block per dimension over the same scoped trades; a failing dimension
    is its own `{"error": ...}` block, every one failing is a 500 (spec v249 § 7)."""
    blocks: dict[str, dict] = {}
    failed = 0
    for dim in dims:
        try:
            blocks[dim] = _dimension_body(scoped, scope, dim)
        except Exception as exc:  # noqa: BLE001 -- one dimension's failure is its own block
            swallowed(log, "ops.admin.analytics.by_dimension_block", exc, level=logging.ERROR, exc_info=True)
            blocks[dim] = {"error": {"code": _DIMENSION_FAILED, "message": f"{type(exc).__name__}: {exc}"}}
            failed += 1
    if failed == len(dims):
        raise ApiError(_DIMENSION_FAILED, f"every dimension failed: {', '.join(dims)}", 500)
    return {"blocks": blocks}
```

Then replace the body of `analytics_by_dimension` (everything after its docstring, currently L238-318: the imports, the `dim` check, the grouping, ordering and rows loop, and the `jsonify` return) with:

```python
    scope = _scope(extra=("dim", "dims"))
    dims = _dims_param()
    if dims is not None:
        return jsonify(_multi_dimension_body(_scoped_closed(scope), scope, dims))
    from swingbot.core.analytics.aggregate import DIMENSIONS

    dim = (request.args.get("dim") or "").strip()
    if dim not in DIMENSIONS:
        raise ApiError("invalid", f"dim must be one of {list(DIMENSIONS)}, got {dim!r}", 400)
    return jsonify(_dimension_body(_scoped_closed(scope), scope, dim))
```

Append this paragraph to the end of the handler's docstring (before its closing `"""`):

```text
    spec v249 § 2: `?dims=a,b,...` answers `{"blocks": {name: <the ?dim=name
    body>}}` from ONE load and scope of the closed trades; a dimension that
    raises becomes `{"error": {"code": "dimension_failed", ...}}` in place of
    its body (HTTP 200 while one block stands, 500 when none does). `dim` and
    `dims` together, an empty list or an unknown name are a 400.
```

The order of the original validation is kept: `_scope` runs first (unknown parameters and a bad scope are still 400 before `dim` is checked).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: PASS (all, old and new).

Run: `python scripts/dev/testrun.py file tests/admin/test_api_analytics.py`
Expected: PASS (R9-02's by-dimension tests, the 401 test and the unknown-parameter test unchanged).

- [ ] **Step 6: Prove the single form is byte-identical, then delete the capture**

Run: `V249_CAPTURE=.superpowers/v249-by-dimension-before.json python scripts/dev/testrun.py file tests/admin/test_v249_capture_tmp.py`
Expected: PASS. The file exists now, so this run compares the raw text of every `?dim=` body, plus the scoped one, against the pre-change capture.

Then delete `tests/admin/test_v249_capture_tmp.py` and `.superpowers/v249-by-dimension-before.json`. Neither is committed.

- [ ] **Step 7: Complexity gate — lock in the drop**

Run: `python -m radon cc -s -n C swingbot/admin/api_v1/analytics.py`
Expected: `analytics_by_dimension` and the new helpers are not listed (all below C / under 11).

Run: `python scripts/dev/complexity_gate.py --update`
Expected: the `"swingbot.admin.api_v1.analytics:analytics_by_dimension": 33` entry leaves `scripts/dev/complexity_baseline.json` (or shrinks); `git diff scripts/dev/complexity_baseline.json` shows nothing else changed. If other entries moved, they belong to other work: revert those lines by hand and keep only this one.

Run: `python scripts/dev/complexity_gate.py`
Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(api): v249 by-dimension dims= form -- one trade load, per-dimension error blocks"
git add scripts/dev/complexity_baseline.json
git commit -m "chore(complexity): v249 analytics_by_dimension split -- baseline entry drops"
```

### Task V249-3: Delete the Dashboard `mode=today` client fallback (`loadToday`, `TodayFallback`) + extend the server `today` pin

**Model:** sonnet — a contained deletion in one store with its spec rewrites and one extended server assertion.

**Files:**
- Modify: `frontend/src/app/stores/dashboard.store.ts:45-57` (state docs), `:77-87` (`TodayFallback`), `:335-450` (`withMethods`: `loadToday`, `widerRoad`, `resolveScoped`, `refetch`, `load`, `select`)
- Modify: `frontend/src/app/stores/dashboard.store.spec.ts` (`:542` comment; describe "today's figures and the chart's Latest button" `:724-1028`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts:1008-1028` (`todayFailedInPeriod`)
- Modify: `tests/admin/test_api_v1_dashboard.py:928-934` (`test_today_block_is_present_and_shaped_for_all_and_range`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (index ledger; V249-9 builds on it): `resolveScoped()` takes no argument and runs a full load's rules (today owed); `resolve()` and `load()` keep their signatures. A wider answer never sends a `mode=today` request.

**What stays.** The pick-versus-load distinction that `TodayFallback` also carried is not about the fallback. A load (first load, every event refresh) marks today loading and reports a failed request as today's failure. A pick (`setPreset`, a settled Range) does so only while no today figures have landed. Tests at `:761`, `:839` and `:848` pin that, and the Realised today card shows `todayLoading` as busy, so dropping the rule would flash the card on every pick. It moves into a private `requestScoped(always: boolean)`. `resolveScoped()` is `requestScoped(true)`, and `select` calls `requestScoped(false)`. No server code changes (index Global Constraints "Server `today` block"). `tests/admin_perf/golden/dashboard.json` and `dashboard_today.json` are not touched.

- [ ] **Step 1: Extend the server pin (it passes already; it pins what the client now relies on)**

In `tests/admin/test_api_v1_dashboard.py`, replace `test_today_block_is_present_and_shaped_for_all_and_range` with:

```python
def test_today_block_is_present_and_shaped_for_all_and_range(seed, logged_in):
    """v249 deleted the SPA's `mode=today` fallback: every `all` and `range`
    answer must carry today's block, equal to `mode=today`'s own figures."""
    seed(**_parity_book())
    today = logged_in.get("/api/v1/dashboard?mode=today").get_json()
    for body in (logged_in.get("/api/v1/dashboard?mode=all").get_json(),
                 _range(logged_in).get_json()):
        assert_shape(body["today"], {"realized": dict, "lifecycle": dict}, where="today")
        assert_shape(body["today"]["realized"], _REALIZED_SHAPE, where="today.realized")
        assert set(body["today"]["lifecycle"]) == set(body["lifecycle"])
        assert body["today"] == {"realized": today["realized"], "lifecycle": today["lifecycle"]}
```

Run `/replicate-prod-db` once this session if no sibling task did, then:

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py`
Expected: PASS.

- [ ] **Step 2: Rewrite the store tests (failing first)**

In `frontend/src/app/stores/dashboard.store.spec.ts`:

(a) Replace the comment at `:542-544` with:

```ts
    // Since v249 a wider answer never sends a today-only fetch (mode=today): its `today` block is
    // today's figures. A 1D request still in flight when a wider preset is picked is the only
    // mode=today request these helpers must ignore.
```

(b) Delete these three tests from the "today's figures and the chart's Latest button" describe: `'falls back to the today request when the wider response has no block (older backend)'` (`:818`), `'keeps the previous today figures and stops loading when the fallback today fetch fails'` (`:831`), `'keeps the newest today answer when an older fallback lands after it'` (`:949`).

(c) Insert where `:818` was:

```ts
    it('sends no today request when a wider answer has no block (v249: no fallback)', () => {
      const reqs = widenThenPush();
      expect(reqs.map(modeOf)).toEqual(['range']);
      flushScoped(reqs);
      expect(requests()).toHaveLength(0);
      expect(store.todayLoading()).toBe(false);
      expect(store.todayError()).toBeNull();
      expect(store.todayRealized()).toEqual(TODAY);       // the previous figures stay
    });
```

(d) Replace `'never lets an older today fetch overwrite a newer block'` (`:966`) with:

```ts
    it('never lets an older 1D answer overwrite a newer block', () => {
      tick();
      const [first] = requests();                        // the 1D load, left in flight
      store.setPreset('1M');
      const newerFigures = { amount: 45, pct: 1.5, n: 4, wins: 3, losses: 1 };
      flushScoped(requests(), block(newerFigures));      // the wider answer carries the block
      expect(store.todayRealized()).toEqual(newerFigures);
      first.flush({ ...RESPONSE, realized: TODAY });     // the older 1D answer lands last
      expect(store.todayRealized()).toEqual(newerFigures);
      expect(store.todayLoading()).toBe(false);
    });
```

(e) Replace `'reports a failed today fetch instead of loading forever'` (`:981`) with:

```ts
    it('reports a failed wider request as today failing while today is owed, never loading forever', () => {
      tick();
      const [first] = requests();
      store.setPreset('1M');                             // before any today answer: today owed
      fail(first);
      requests().forEach(fail);                          // the 1M request fails too
      expect(store.todayLoading()).toBe(false);
      expect(store.todayError()).not.toBeNull();
      expect(store.todayLifecycle()).toEqual([]);
      expect(requests()).toHaveLength(0);                // and no today request follows
    });
```

(f) Replace `'clears the today error once a today answer lands'` (`:996`) with:

```ts
    it('clears the today error once a today block lands', () => {
      const [scopedReq] = widenThenPush();
      fail(scopedReq);                                   // a load owes today: its failure is today's
      expect(store.todayError()).not.toBeNull();
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(300);
      flushScoped(requests(), block(TODAY));
      expect(store.todayError()).toBeNull();
      expect(store.todayLoading()).toBe(false);
      expect(requests()).toHaveLength(0);
    });
```

`flushToday` has no caller left after (b)–(f): delete it from the describe's helpers too (`:738-740`), or lint fails on an unused const.

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/dashboard.store.spec.ts`
Expected: FAIL. `'sends no today request when a wider answer has no block'` fails: the old store still sends the `mode=today` fallback, so `requests()` has length 1.

- [ ] **Step 3: Delete the fallback in the store**

In `frontend/src/app/stores/dashboard.store.ts`:

Replace the `todayData` / `todayLoading` docs (`:45-53`) with:

```ts
  /** Today's realised block and lifecycle counts, kept beside the scoped
   *  response: the Realised today card and the Open positions tabs read
   *  today in every mode. Under 1D it is the scoped response itself; under
   *  a wider scope it is that response's `today` block (v217; v249 removed
   *  the today-only fallback, the SPA never runs against a server without
   *  the block). Null until one lands. */
  todayData: DashboardToday | null;
  /** A scoped request that owes today's figures is in flight. */
  todayLoading: boolean;
```

Delete `TodayFallback` and its doc comment (`:77-80`); keep `TodayRoad`.

Replace the comment above `let todayIssued = 0;` (`:337-341`) with:

```ts
    // Today's figures arrive by two roads -- a 1D scoped response and a
    // wider response's `today` block -- stamped on one counter. Any today
    // answer is today's, whatever the scope became meanwhile, so it lands
    // unless a newer today answer already has; `todayLoading` clears only
    // once the newest stamp has settled.
```

Delete `loadToday` and its doc comment (`:361-371`).

Replace `widerRoad` and its doc comment (`:384-406`) with:

```ts
    /** v217 (v205 P3-a): a wider answer carries today's figures as its
     *  `today` block, so no second request goes out. The stamp is taken at
     *  issue: an older 1D answer never lands on top of the block. `always`:
     *  a full load owes today (loading shown, a failure reported); a pick
     *  owes it only while nothing has landed. */
    const widerRoad = (always: boolean): TodayRoad => {
      const owed = always || untracked(() => store.todayData()) === null;
      const stamp = ++todayIssued;
      if (owed) patchState(store, { todayLoading: true });
      const settle = (): void => {
        if (stamp === todayIssued) patchState(store, { todayLoading: false });
      };
      return {
        next: (data) => {
          if (data.today !== undefined) landToday(stamp, data.today);
          else settle();
        },
        error: (error) => {
          if (owed) failToday(stamp, error);
          else settle();
        },
        cancel: settle,
      };
    };
```

Rename `resolveScoped` to `requestScoped`, change its parameter from `fallback: TodayFallback` to `always: boolean`, and pass it on: `const today = mode === 'today' ? dayRoad() : widerRoad(always);`. The rest of its body is unchanged. Then replace the block from `/** Public: a full load's rules (today owed). */` through `const select = …` (`:439-452`) with:

```ts
    /** The scoped request under a full load's rules (today owed). */
    const resolveScoped = (): Observable<void> => requestScoped(true);

    /** Public: a full load's rules (today owed). */
    const resolve = (): Observable<void> => resolveScoped();

    const refetch = (source: Observable<void>): void => {
      source.subscribe({ error: () => undefined });
    };

    /** First load and every event refresh. One request in every scope. */
    const load = (): void => refetch(resolveScoped());

    const select = (selection: ScopeSelection): void => {
      patchState(store, { selection });
      refetch(requestScoped(false));
    };
```

Confirm nothing else names the deleted symbols:

Run: `git grep -n "loadToday\|TodayFallback\|today-only" -- frontend/src`
Expected: no output.

- [ ] **Step 4: Rewrite the Dashboard page helper**

In `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, replace `todayFailedInPeriod` (`:1008-1028`, with its doc comment) with:

```ts
  /** The 1D load fails, then 1M is picked and answers with the counts. That
   *  answer has no `today` block (the store sends no fallback since v249),
   *  so today's figures stay failed while the scoped counts land. */
  async function todayFailedInPeriod(): Promise<ComponentFixture<Dashboard>> {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flushTradeGroups(backend);
    const store = TestBed.inject(DashboardStore);
    fail(backend.expectOne('/api/v1/dashboard?mode=today'));
    store.setPreset('1M');
    for (const req of backend.match((r) => r.url === '/api/v1/dashboard')) {
      req.flush(payload({ scope: { mode: 'range' }, lifecycle: { ...LIFECYCLE, CLOSED: 40 } as never }));
    }
    backend.expectNone((r) => r.url === '/api/v1/dashboard');
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }
```

The two tests that call it (`"falls back to the scoped answer's open counts when today's fetch failed"` and `"says today's figures could not load instead of ringing forever"`) stay as they are.

- [ ] **Step 5: Run the frontend tests and lint**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/dashboard.store.spec.ts`
Expected: PASS.

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: PASS.

Run: `npm --prefix frontend run lint`
Expected: no errors.

Run: `git diff --stat -- tests/admin_perf/golden`
Expected: no output (goldens untouched).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/stores/dashboard.store.ts frontend/src/app/stores/dashboard.store.spec.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "refactor(ui): v249 delete the dashboard mode=today client fallback -- the today block always rides along"
git add tests/admin/test_api_v1_dashboard.py
git commit -m "test(api): v249 pin the dashboard today block equal to mode=today for all and range"
```

