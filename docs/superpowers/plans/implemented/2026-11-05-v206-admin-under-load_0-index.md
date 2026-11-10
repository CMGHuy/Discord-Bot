# v206 Plan 1 — Admin under load: probe and polling (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md) (Plan 1 only: § Goal / Measurement rules, § Plan 1 P1-a..P1-e, Plan 1 tests, Complexity)

## Goal

On 2026-11-05, during a US-session scan, a Playwright probe found the admin
answering its heavy calls in 4–43 s, not the 2.5 s v205 measured inside the
container. The admin is one gunicorn worker whose threads share one GIL, so
every request waits behind every other. The biggest, cheapest cause is
polling: while a scan runs the `scan` SSE event fires about once a second,
and every open tab answers each one with `/health` plus `/system/scan`, plus
`/live`, plus a whole-route reload on System and ticker detail. That is
about 120 requests a minute from one idle tab, all queueing in front of the
calls a person is waiting for.

This plan is the first of four. It does two things. First, it commits the
browser probe (`scripts/ops/admin_browser_probe.py`) under the spec's
measurement rules: nearest-rank percentiles with a `thin` rule, a pure
`settle_time`, an idle-hold phase, a scan sample per page, and a run label.
Before and after numbers then come from one instrument instead of a
throwaway script. Second, it removes the scan-driven polling. The broker
reads the scan progress once per flushed `scan` event and sends it in the
event. The connection store patches the progress strip from that payload,
so no request goes out. `/health` moves to boot, `bot` and a 5-minute
visible-tab timer. `/live` stops listening to `scan`, route reloads on
`scan` are limited to once per 5 s, and the boot `/market/tape` request is
de-duplicated. `/health` also reports `sse_streams`, so every probe result
records the thread budget.

The plan leaves the bot process, the scan, the SQL, the gunicorn worker
count and every response body alone. `sse_streams` and the `progress` key on
`scan` events are the only additions. Plans 2–4 (v205 Part 3, Layer 2 with
ETag, analytics outliers) are written later under their own numbers, once
this plan's numbers are in.

Success has two parts. The probe's unit tests pin every metric the Goal
depends on. Then a production run during a scan, recorded under the spec's
`## Results` beside a baseline taken with the same probe before deploy,
shows the idle-tab rate falling from about 120 to under 10 requests a
minute. The heavy-call goals (under 2 s p90, no endpoint over 5 s p90) are
plans 2–4's to reach. This plan records where they stand.

## Architecture

- **Probe** (P1-a): one script, pure aggregation functions at module level
  (unit-tested on a JSON fixture), Playwright imported lazily inside
  `run_browser()` only. Playwright is not a declared dependency, so the
  tests never import it.
- **Broker** (P1-b): `EventBroker.publish("scan")` calls an injectable
  `progress_reader` **outside** the lock, once per publish. The default
  reader uses `side_connection()` (fail-fast, `MARKETDATA_PG_TIMEOUT_MS`
  statement timeout) with `progress_store.read_strict(conn=)` and
  `runstate.is_scan_running(conn=)`. A raise sends the event thin, counts
  `admin.events.scan_progress` in the swallowed-error counter, and logs at
  most once per 60 s on an injectable clock.
- **Client** (P1-c..e): `EventStream.payload('scan')` is an unthrottled
  signal of the last validated payload (`parseScanEventProgress`). It is
  cleared on resync, degrade, poll ticks and reconnect. `ConnectionStore`
  patches from it, and falls back to a throttled `/system/scan` only when it
  is null. `RouteRefreshService` gains per-event minimum intervals
  (`scan: 5000`). `LIVE_REFRESH_EVENTS` drops `scan`. `TapeFeed` gets an
  in-flight guard.

**Tech stack:** Python 3.11, Flask, SQLAlchemy, pytest; Angular (signals,
`@ngrx/signals`), Vitest, zoneless TestBed; Playwright (Python, probe only).

## Global Constraints

- **Byte-identical JSON** for the same DB state, clock and price source; the only additions are `sse_streams` on `/api/v1/health` and `progress` on `scan` SSE frames (spec § Goal). Nothing is removed.
- `Event.data()` for every event other than a `scan` with a successful read stays exactly `{"seq": …, "at": …}`; the backlog collapse stays a bare `resync`. A failed read sends a thin event, **never** `"progress": null`.
- The broker's progress read never runs inside `self._lock`, runs once per publish (never per connection), and only for `scan`.
- Swallowed-error tag: `admin.events.scan_progress`; log at most once per 60 s.
- `/system/scan` fallback throttle: `changes('scan', { minIntervalMs: 5000 })`. `/health` timer: 5 min (300 000 ms), skipped while `document.hidden`, one catch-up fetch on visible when more than 5 min have passed since the last fetch.
- `LIVE_REFRESH_EVENTS` is exactly `['trades', 'bot', 'risk']`; `scan` is never added back.
- `RouteRefreshService` `scan` minimum interval 5000 ms; every other event keeps the 300 ms debounce unchanged.
- Probe: credentials read from `.env` inside the script, **never printed, logged or written**. Playwright Chromium headless, service workers blocked, viewport 1440×900, routes fixed in spec order, `--rounds` 3, `--cap` 90, quiet 2 s, `--date` required, `--base` default `https://bomeo-capital.com`. GETs plus the session POST only. Failed login exits non-zero before any page loads.
- Percentiles nearest-rank; p90 only at n ≥ 5, otherwise `thin` with max; heavy = any `/api` path except `session`, `health`, `system/scan`, `system/preferences`, `risk/killswitch`, `market/updates` (and `/events`).
- Production is reached only through `bash scripts/ops/ssh-hetzner.sh "<cmd>"`; a production change is mirrored into the repo (`mirror-prod` skill). Deploy is push-to-`main` → CI (`docs/deploy/DEPLOY_HETZNER.md`).
- Every touched Python function stays < 15 cyclomatic complexity (`python scripts/dev/complexity_gate.py` before and after); TypeScript by inspection. `publish` and the connection-store effect get named helpers, not new branches.
- Narrow test runs only: `python scripts/dev/testrun.py file <test>`; frontend `node <wt>/frontend/scripts/ng-test.mjs <wt>/frontend --include <spec>`. **No task runs the full suite**: CI does after the push.
- Implementation happens in a worktree (`.claude/worktrees/2026-11-05-v206-admin-under-load`); every command names the worktree path `<wt>`.

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| A probe | V206-1 → V206-1b → V206-2 → V206-3 | `scripts/ops/admin_browser_probe.py`, its test, fixture; spec `## Results` | V206-1b and V206-2 extend V206-1's module; V206-3 runs V206-2's CLI |
| B health | V206-4 | `api_v1/session.py`, `tests/admin/test_api_v1_session.py`, `tests/admin/test_api_v1_dashboard.py` | — |
| C broker | V206-5 → V206-6 | `progress_store.py`, `runstate.py` → `broker.py` | V206-6 consumes `read_strict(conn=)` and `is_scan_running(conn=)` |
| D client stream | V206-7 → V206-8 → V206-9 | `models.ts`, `scan-event-progress.ts` → `event-stream.ts` → `connection.store.ts` | V206-8 consumes the validator; V206-9 consumes `payload('scan')` |
| E route refresh | V206-10 | `route-refresh.service.ts` + spec | — |
| F live | V206-11 | `live.store.ts` + spec | — |
| G tape | V206-12 | `tape-feed.ts` + spec | — |
| H release | V206-13 | `VERSION.json`, `version_history.json`, spec `## Results` | needs every other task merged; V206-3's baseline must exist |

Groups B, C, D, E, F, G touch disjoint files and share no contract, so they may run in parallel after V206-2. The plan's only cross-language contract is the `scan` frame shape `{"seq", "at", "progress": {"running", "progress"}}`, fixed in the ledger below. **V206-3 must run before V206-13 pushes**: the baseline has to measure the code production runs today. Nothing deploys before V206-13, because the branch merges only there. V206-3 and V206-13 both edit the spec's `## Results`, under different sub-headings, in that order.

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V206-1 | Probe aggregation primitives: settle time, percentiles, endpoints, label | 1 | sonnet | C `scripts/ops/admin_browser_probe.py`; C `tests/scripts/test_admin_browser_probe.py` | `settle_time(intervals, quiet_s, cap_s) -> float \| None` (None = cap); `nearest_rank(values, pct) -> float`; `normalise_endpoint(url) -> str`; `is_heavy(endpoint) -> bool`; `endpoint_stats(calls) -> list[dict]`; `requests_per_minute(count, window_s) -> float`; `run_label(samples) -> str` (`scan`/`mixed`/`quiet`) |
| V206-1b | Probe report: fixture, `summarise`, `render_markdown` | 1 | sonnet | C `tests/scripts/fixtures/admin_browser_probe_raw.json`; M `scripts/ops/admin_browser_probe.py`; M `tests/scripts/test_admin_browser_probe.py` | `summarise(raw) -> dict`; `render_markdown(report) -> str`; raw shape `{meta, pages[], idle}` |
| V206-2 | Probe CLI, browser loop, outputs, credential hygiene | 1 | sonnet | M `scripts/ops/admin_browser_probe.py`; M `tests/scripts/test_admin_browser_probe.py` | CLI `python scripts/ops/admin_browser_probe.py --date YYYY-MM-DD --out DIR [--base URL] [--rounds 3] [--cap 90] [--image-tag TAG]`; `main(argv=None, *, runner=None, env_path=None) -> int`; `LoginFailed`; writes `DIR/probe.json`, `DIR/probe.md` |
| V206-3 | Baseline probe run on production during a scan | 1 | sonnet | M `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (`## Results` → `### Plan 1 baseline (committed probe)`) | baseline table the V206-13 comparison reads |
| V206-4 | `/health` reports `sse_streams` | 1 | sonnet | M `swingbot/admin/api_v1/session.py`; M `tests/admin/test_api_v1_session.py`; M `tests/admin/test_api_v1_dashboard.py` | `/api/v1/health` field `sse_streams: int` = `get_broker().connection_count` |
| V206-5 | Raising progress read + `conn=` on the running flag | 1b | sonnet | M `swingbot/core/scanning/progress_store.py`; M `swingbot/core/scanning/runstate.py`; C `tests/scanning/test_progress_store_strict.py` | `progress_store.read_strict(*, conn=None) -> dict \| None` (raises); `runstate.is_scan_running(*, conn=None) -> bool` |
| V206-6 | Broker: `scan` events carry progress | 1b | opus | M `swingbot/admin/events/broker.py`; M `tests/admin/test_event_broker.py`; M `tests/admin/test_event_stream.py` | `Event.progress: dict \| None = None`; `Event.data()` adds `"progress"` only when set; `EventBroker(*, watcher_factory=None, progress_reader=None, clock=time.monotonic, max_connections=…, queue_limit=…)`; `progress_reader() -> dict \| None` returning `{"running": bool, "progress": dict \| None}`; tag `admin.events.scan_progress` |
| V206-7 | `parseScanEventProgress` validator | 2 | sonnet | M `frontend/src/app/api/models.ts`; C `frontend/src/app/api/scan-event-progress.ts`; C `frontend/src/app/api/scan-event-progress.spec.ts` | `interface ScanEventProgress { running: boolean; progress: ScanProgressRecord \| null }`; `parseScanEventProgress(frame: unknown): ScanEventProgress \| null` (reads `frame.progress`) |
| V206-8 | `EventStream.payload('scan')` + invariant doc | 2 | sonnet | M `frontend/src/app/api/event-stream.ts`; M `frontend/src/app/api/event-stream.spec.ts` | `EventStream.payload(name: 'scan'): Signal<ScanEventProgress \| null>` |
| V206-9 | ConnectionStore: patch from payload, throttled fallback, health timer | 2 | sonnet | M `frontend/src/app/stores/connection.store.ts`; M `frontend/src/app/stores/connection.store.spec.ts`; M `frontend/src/app/shell/shell.spec.ts`; M `frontend/src/app/workspaces/trades/trade-detail.spec.ts` | `SCAN_FALLBACK_MIN_INTERVAL_MS = 5000`; `HEALTH_INTERVAL_MS = 300_000` (exported) |
| V206-10 | RouteRefreshService per-event minimum interval | 2 | sonnet | M `frontend/src/app/routing/route-refresh.service.ts`; M `frontend/src/app/routing/route-refresh.service.spec.ts` | `EVENT_MIN_INTERVAL_MS: Partial<Record<EventName, number>> = { scan: 5000 }` (exported) |
| V206-11 | `/live` stops reacting to `scan` + field table | 2 | sonnet | M `frontend/src/app/stores/live.store.ts`; M `frontend/src/app/stores/live.store.spec.ts` | `LIVE_REFRESH_EVENTS = ['trades', 'bot', 'risk']` |
| V206-12 | TapeFeed: failing double-request repro, then in-flight guard | 2 | sonnet | M `frontend/src/app/stores/tape-feed.ts`; M `frontend/src/app/stores/tape-feed.spec.ts` | — |
| V206-13 | Release, deploy, after-probe during a scan, Results | 2b | sonnet | M `VERSION.json`; M `swingbot/admin/version_history.json`; M `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-05-v206-admin-under-load_1-probe-and-broker.md` | V206-1..V206-4 (with V206-1b) | probe, baseline run, `/health` stream count |
| 1b | `2026-11-05-v206-admin-under-load_1b-broker.md` | V206-5..V206-6 | raising progress read, broker scan payload |
| 2 | `2026-11-05-v206-admin-under-load_2-client-and-release.md` | V206-7..V206-12 | validator, EventStream payload, connection store, route refresh, `/live`, tape |
| 2b | `2026-11-05-v206-admin-under-load_2b-release.md` | V206-13 | release, deploy, after-probe, Results |
