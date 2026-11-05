"""Browser probe of the admin under load (v206 P1-a).

Logs into the admin with Playwright, loads a fixed list of pages as a
browser does, and records every /api call's time to first byte, so before
and after numbers come from one instrument. Spec:
docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md, Goal
(Measurement rules) and P1-a.

    python scripts/ops/admin_browser_probe.py --date 2026-11-03 --out .superpowers/probe/<run> [--image-tag TAG]

The top half is pure aggregation, unit-tested. The browser loop imports
Playwright lazily (it is not a declared dependency), so importing this
module never needs it.
"""
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
