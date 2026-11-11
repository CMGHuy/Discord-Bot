# v206 — Admin under load: the browser, during a scan, in seconds

**Version:** ui 1.39.0 · bot 2.16.3
**Bump:** ui patch, bot patch (each plan bumps on its own; speed is the only visible difference)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, senior-engineer, quant-engineer
**Follows:** v205 (`docs/superpowers/specs/2026-11-04-v205-admin-read-performance-design.md`)

## Why

v205 measured endpoints **from inside the `admin` container, one request at
a time**, and after Layer 1 `/dashboard` answers in 2.4–3.0 s there. The
partner does not use the admin that way. On 2026-11-05 ~16:20–16:50 Berlin
(US session, a scan running) a Playwright probe logged into
bomeo-capital.com and loaded 12 pages twice, as a browser does. About
4,800 API calls in ~30 minutes, time to first byte as the browser saw it:

| Endpoint | n | Median ms | p90 ms | Max ms |
|---|---|---|---|---|
| `/cancel-precision` | 2 | 43,558 | — | 43,558 |
| `/analytics/performance` | 1 | 34,562 | — | 34,562 |
| `/analytics/equity-curve` | 5 | 13,041 | 15,633 | 15,633 |
| `/dashboard` | 21 | 11,922 | 21,619 | 26,097 |
| `/analytics/variance-band` | 7 | 7,709 | 9,406 | 9,406 |
| `/research/ledger` | 2 | 7,101 | — | 7,101 |
| `/calendar/pnl/day/sparklines` | 6 | 6,169 | 9,441 | 9,441 |
| `/market/tape` | 116 | 4,877 | 9,977 | 19,006 |
| `/analytics/registry` | 2 | 4,797 | — | 4,797 |
| `/equity/candles` | 9 | 4,752 | 13,669 | 13,669 |
| `/calendar/pnl/day` | 7 | 4,659 | 7,483 | 7,483 |
| `/trades` | 15 | 3,877 | 12,913 | 13,884 |
| `/watchlist/tickers` | 12 | 3,014 | 6,301 | 7,175 |
| `/calendar/pnl` | 20 | 2,758 | 7,525 | 7,583 |
| `/live` | 289 | 1,750 | 2,238 | 8,181 |
| `/market/updates` | 262 | 599 | 3,708 | 12,619 |
| `/system/scan` | 1,740 | 273 | 1,535 | 13,614 |
| `/health` | 1,818 | 91 | 423 | 11,345 |

The gap between 2.5 s in the container and 12 s in the browser is
**contention**. The admin is one gunicorn worker (`deploy/gunicorn.conf.py`,
one worker is a requirement there) whose threads share one GIL, so every
request queues behind the others. Four causes stack:

1. **Scan polling.** `stores/connection.store.ts` refetches `/health` **and**
   `/system/scan` on every `scan` SSE event. While a scan runs that event
   fires about once a second (`api/event-stream.ts:36`), so **every open tab
   sends ~2 requests a second**: ~85 of each per 90 s on every page probed.
   `/live` also lists `scan` among its triggers (`stores/live.store.ts:11`),
   giving ~20 `/live` calls per 90 s at ~1.8 s each.
2. **Boot fan-out.** The Dashboard starts `dashboard?mode=today`, `trades`
   twice (all, and `status=ACTIVE`), `equity/candles` and `market/tape` in
   the same instant, and each takes 8–16 s when they all run at once. The
   shell sends the same 60-symbol `/market/tape` request **twice within
   30 ms** at boot (5.2 s and 14.0 s).
3. **Every refetch recomputes.** Every API response is `no-store` with no
   validator (`api_v1/__init__.py:61`), so a refetch with nothing changed
   costs the same as the first fetch. That is v205's cause 3, which Layer 2
   addresses.
4. **Slow endpoints v205 never profiled.** v205 profiled only the Dashboard
   and Calendar routes. `cancel-precision`, `analytics/performance`,
   `equity-curve`, `variance-band`, `research/ledger`, `sparklines` and
   `equity/candles` are each seconds to tens of seconds on their own.

Caveat on the baseline: the probe was one extra tab, and other tabs may
have been open. Numbers outside a scan will be lower; the shape is the
same.

## Goal

Measured with the committed browser probe (below) **while a scan runs**:

- the first heavy data call on every probed page lands in **under 2 s
  (p90)**;
- **no endpoint whose p90 exceeds 5 s**;
- one idle tab sends **under 10 requests per minute** during a scan
  (today ~120);
- JSON stays **byte-identical** for the same database state, clock and price
  source (see Testing), except fields a plan adds on purpose (it removes
  none).

**Measurement rules** (they make runs comparable):

- Percentiles are **nearest-rank**. A per-endpoint p90 is reported only at
  n ≥ 5; below that the row shows its max and is marked `thin`. The probe's
  default of 3 rounds gives every route-bound endpoint n ≥ 3. A `thin` row
  counts against the 5 s goal on its max.
- **Idle rate** is measured in a separate **idle-hold phase**: after the
  last round the probe opens `dashboard`, waits for it to settle (or hit
  the cap), then counts `/api` requests (excluding `/events`) over the next
  120 s and reports requests per minute.
- **Scan state is sampled per page**, by reading `/api/v1/system/scan`
  once after each page settles. A run counts toward the Goal only if every
  sample shows `running: true`. Any other run is labelled `mixed` or
  `quiet`, kept in `## Results`, but not used as evidence.
- Rounds are reported **separately** (round 1 is cold, later rounds may hit
  warm caches), and so are capped pages: the share of capped pages, and
  settle statistics over **uncapped pages only**.
- Each result records the git SHA of the probe, the production image tag,
  the Berlin time, the pinned calendar date and the open SSE stream count,
  so the thread budget is known (gunicorn has 16 threads and each stream
  holds one). No endpoint exposes that count today, only
  `EventBroker.connection_count` (`broker.py:190`). Plan 1 adds it to
  `/api/v1/health` as an additive `sse_streams` field.

## Non-goals

- No change to the bot process or the scan. The `scan` event's new payload
  is read by the admin from what the bot already writes.
- No SQL rewrite of metrics and no precomputed payloads in the refresher
  (v205's reasons stand).
- **No second gunicorn worker** and no moving the login limiter, the
  swallowed-error counter or the SSE broker out of process memory. If the
  Goal is still missed after plan 4, a separate spec takes that up.
- No visible UI change beyond speed. The scan progress strip keeps its
  current resolution.

## Plans

Four plans, in order. Each ends with a deploy and a browser probe run whose
table goes into `## Results`. **A later plan is written only after the
earlier one is measured**, so a stage the numbers no longer need is dropped.
Plan 1 takes this spec's number; plans 2–4 each take the next free number at
their own creation and link back with `**Spec:** v206`.

1. **Probe + polling** (plan v206).
2. **v205 Part 3**, plus the Dashboard boot `/trades` merge.
3. **v205 Layer 2**, plus ETag/304 and `Server-Timing`.
4. **Analytics outliers**, profiling first.

v205's spec stays the authority for Layer 2 (L2-a..d) and Part 3
(P3-a, P3-b). This spec does not restate them. It adds only what is new, and
v205's `## Results` keeps receiving its in-container measurements.

## Design

### Plan 1 — probe and polling

**P1-a. Browser probe.** `scripts/ops/admin_browser_probe.py`, from the
throwaway script that produced the table above:

- Playwright Chromium, headless, **service workers blocked**, viewport
  1440×900.
- Logs in by `POST /api/v1/session` with `ADMIN_USERNAME`/`ADMIN_PASSWORD`
  read from `.env` inside the script. The values are never printed, logged
  or written to output.
- Visits a fixed route list (`dashboard`, `trades`, `trades/calendar`,
  `trades/calendar/<date>`, `trades/cancels`, `watchlist`, `risk`,
  `insights/analytics`, `insights/research`, `insights/reports`, `system`,
  `system/versions`) for `--rounds` rounds (default 3), in that fixed order,
  then runs the idle-hold phase (Goal § Measurement rules). Each is a full
  load at the root path (production serves the SPA at `/`, not `/app/`).
  `<date>` comes from `--date`, which is required, so runs being compared
  name the same day.
- A page counts as **settled** once no `/api` call (ignoring
  `/api/v1/events`) has been in flight for 2 s, capped at `--cap` seconds
  (default 90). It records the settle time, or `cap` when the page never
  goes quiet. The settle rule is a **pure function**,
  `settle_time(intervals, quiet_s, cap_s)` over the calls' (start, end)
  intervals, and the live loop only collects intervals. That way the
  metric the Goal depends on is unit-tested, overlapping calls and the
  never-quiet case included.
- Per call it records the URL, status, start offset, TTFB, total time and
  bytes.
- Writes `--out <dir>/probe.json` and `probe.md`: per-endpoint
  n/median/p90/max TTFB, per-page requests per minute, and the first heavy
  call's TTFB per page. "Heavy" means any `/api` path outside `session`,
  `health`, `system/scan`, `system/preferences`, `risk/killswitch` and
  `market/updates`. It records `scan_running` per page (Goal § Measurement
  rules) and the `Server-Timing` header when present (P3-d).
- `--base` defaults to `https://bomeo-capital.com`; a local instance works
  the same way.
- Read-only: GETs, plus the session POST.

The aggregation (URL normalisation, nearest-rank percentiles with the
`thin` rule, requests per minute, the heavy-call rule, `settle_time`, the
run label from per-page scan samples) lives in pure functions with unit
tests on a JSON fixture. A test also asserts that the credential values
never appear in `probe.json` or `probe.md`, using a fixture with sentinel
credentials. Only the browser loop itself goes without a unit test.

**P1-b. Scan progress travels in the `scan` event.** `Event`
(`admin/events/broker.py:67`, a frozen dataclass whose `data()` returns
`{seq, at}`) gains an optional `progress: dict | None = None`. `data()`
includes `progress` **only when it is set**, so every other event's frame
stays byte-identical. The shape is the subset of `/system/scan`
(`api_v1/system.py:_scan_status`) the progress strip reads: `running` and
`progress` (the same record the route returns).

- **Where it is read.** `publish` runs on the `db-event-listener` thread,
  whose contract is that `emit` must not block (`db_listener.py:39-41`).
  The read is therefore limited to `progress_store` plus
  `is_scan_running()`, never the full `scan_status_payload`
  (`admin/app.py:378`, which also reads the runstate and heartbeat). It
  runs once per **flushed** `scan` event, after the 250 ms debounce, never
  per connection, through the existing fail-fast `side_connection()`
  (`core/db/side_engine.py:86`, whose statement timeout is
  `MARKETDATA_PG_TIMEOUT_MS`, 250 ms by default). The broker gains an
  injectable progress reader and clock beside `watcher_factory` for tests. A test asserts that
  one publish with N subscribers reads once.
- **Failure must be visible.** `progress_store.read()` swallows every error
  and returns `None`, which is also the legitimate "nothing publishing"
  value (`core/scanning/progress_store.py:98-115`). The plan adds a raising
  variant (or a sentinel) for this caller. A read that fails, or times
  out, sends the event **thin** (no `progress` key), never
  `progress: null`. The failure counts in the admin's existing
  swallowed-error counter and is logged at most once a minute, with an
  injected clock in tests.
- **Every `scan` source gets it.** `scan` is raised by `scan_progress`,
  `runtime_flags`, `scan_snapshots` and `scan_telemetry`
  (`core/db/events.py:20,46-47`). All of them carry the read. From now on
  the connection store's `botAlive`, `botHealthy`, `botLastSeen` and
  `botLastSuccess` refresh on `bot` (and boot and `resync`) only, not on
  `scan`. That is acceptable because those are heartbeat facts, which is
  what `bot` reports.
- **Collapse and debounce.** The debounce keeps the latest payload. The
  backlog-collapse path still sends a bare `resync`, and the client fetches
  on `resync`.

**P1-c. Client.** This retires `EventStream`'s documented v12 invariant
("the reaction to an event is always a refetch, never a patch",
`api/event-stream.ts:62-65`) **for `scan` only**. The class doc and
`event-stream.spec.ts` change in the same plan to state the exception.

- **Two separate signals.** `EventStream.payload('scan')` is a new,
  **unthrottled** signal holding the last *validated* payload, or `null`.
  The existing `changes('scan')` counter stays as it is. A pure validator,
  `parseScanEventProgress(data): ScanEventProgress | null`, with its own
  spec, treats anything malformed as absent. The payload signal is cleared
  on `resync`, on degrade to polling (the 5 s polling timer bumps counters
  and must never re-patch stale progress) and on reconnect.
- **Connection store.** A non-null `payload('scan')` patches `scanRunning`
  and `scanProgress` and sends no request. A `scan` tick whose payload is
  `null` (an older server, a failed read, degraded mode) is the
  **fallback**: it fetches `/system/scan`, throttled with
  `changes('scan', { minIntervalMs: 5000 })` through the existing throttle
  mechanism.
  `/system/scan` is still fetched at boot, on `bot` and on `resync`.
- **`/health`** is fetched at boot, on `bot`, and from a new 5-minute timer
  that skips while `document.hidden`. When the tab becomes visible and more
  than 5 minutes have passed since the last fetch, it fetches once. It no
  longer reacts to `scan`. Fake-timer specs cover hidden, visible and the
  catch-up fetch.
- **Route reloads on `scan`.** The System workspace
  (`workspaces/system/system.routes.ts:14`, `refreshOnSystem`) and ticker
  detail (`ticker-detail.routes.ts:8`) reload their whole route on every
  `scan`, through `RouteRefreshService`, which listens to the unthrottled
  `EventStream.raised` with a 300 ms debounce. Throttling `changes()` does
  not reach them. `RouteRefreshService` gains a per-event minimum interval,
  and `scan` gets 5 s (the System page's `paused`/`pending` change only
  through `runtime_flags`, so 5 s is enough). This brings both pages into
  the Goal's scope.

**P1-d. `/live` stops reacting to `scan`.** `LIVE_REFRESH_EVENTS` becomes
`['trades', 'bot', 'risk']`. The plan's `/live` task lists every field of
the `/live` payload and its trigger as a table in a comment beside
`LIVE_REFRESH_EVENTS`. A field that changes during a scan through anything
other than `trades`, `bot` or `risk` gets its own named trigger, never
`scan` back. A spec asserts the array exactly.

**P1-e. One boot tape request.** The probe shows the same 60-symbol
`/market/tape` request going out twice within 30 ms at boot. **The cause is
not known yet.** `TapeFeed.refresh()` (`stores/tape-feed.ts:56-63`) already
coalesces callers in the same tick through its `queued` microtask, so a
"two registrations in one tick" fix would change nothing. Likely
candidates: a `register()` in a later tick re-running the `merged()`
effect, or `scan` and `market` counters ticking in separate tasks. The
plan's first tape task writes a spec that **fails on today's code** and
reproduces the double request (the leading hypothesis is that `TapeFeed.fetch()` has no in-flight
de-duplication, while `tape.store.ts:53` and `market-index.store.ts:38` each
call `feed.refresh()` from their own `load()` in different ticks), then
fixes it with an in-flight guard. If no unit
reproduction is found, the task records what it ruled out, and the
request stays as it is until the probe can tell the cases apart.

**Complexity.** Each plan 1 task that changes a function measures it before
and after (`complexity_gate.py`; for TypeScript, the same < 15 rule by
inspection). The broker's `publish` and `connection.store`'s effect are the
two at risk, and each gets a named helper rather than a new branch.

**Plan 1 tests:**

- broker: a `scan` event carries `progress`; other events are
  byte-identical; one publish with N subscribers reads once; a raising or
  timed-out read sends a thin event, counts once, and logs at most once a
  minute (injected clock).
- `event-stream` spec: `payload('scan')` holds the last valid payload;
  malformed input yields `null`; the payload is cleared on resync, degrade
  and reconnect; counters are unchanged for every other event.
- `parseScanEventProgress` spec: valid, missing and malformed inputs.
- `connection.store` spec: no `/health` call on `scan`; progress is patched
  from the payload; a `scan` tick with a null payload triggers at most one
  fallback call per 5 s; `bot` and `resync` still fetch; the 5-minute
  health timer pauses while hidden and catches up on visible (fake timers).
- `RouteRefreshService` spec: `scan` reloads a route at most once per 5 s;
  other events keep the 300 ms debounce.
- `live.store` spec: `LIVE_REFRESH_EVENTS` equals exactly
  `['trades', 'bot', 'risk']`.
- `TapeFeed` spec: the double-request reproduction, which fails before the
  fix (P1-e).
- `/health` test: `sse_streams` equals the broker's connection count, and
  the other fields are unchanged.
- probe unit tests on a fixture: `settle_time` with overlapping intervals,
  a gap just under and just over 2 s, the never-quiet case and an empty
  page; nearest-rank percentiles and the `thin` rule; the run label from
  per-page scan samples; and that no credential appears in the output.

### Plan 2 — v205 Part 3 plus one boot merge

P3-a and P3-b exactly as v205 designs them. Added here: the Dashboard boot
fetches `/trades` twice (`sort=-opened_at&page=1&per_page=20` and
`status=ACTIVE&...`). The plan's first task finds the components behind
each call. If the open-positions panel can take its rows from one shared
call with identical rendered output (the same rows in the same order,
asserted by a spec), the two calls merge. If not, the task records why, and
both calls stay.

### Plan 3 — v205 Layer 2, ETag/304 and Server-Timing

L2-a..d exactly as v205 designs them. Added here:

**P3-c. Conditional responses.** An explicit **allow-list** of routes that
read only snapshot-backed stores and the request's parameters (candidates:
`/trades` with closed-only filters, `/calendar/pnl`, `/calendar/pnl/day`,
and plan 4's routes once they read the snapshot). Each route is admitted by
an audit task, never assumed. The audit lists every payload field and shows
that none depends on a live price, an FX quote fresher than the daily
`fx_daily_rates` row, the wall clock below day resolution (ages,
"x min ago", `generated_at`), or a setting outside the key. **`/dashboard`
is excluded**: it carries open P&L from live prices. So is any `/trades`
variant that includes open trades, unless its audit shows no price-derived
field. For admitted routes:

- A weak ETag, the hash of (build version from `VERSION.json` plus the image
  tag, snapshot generation, `PlanRepository.version()` and its trades twin,
  a settings generation bumped on every SIGHUP reload, `fx_daily_rates`'
  latest date, the normalised query string, today's Berlin date, and the
  authenticated user). The build version makes a deploy or a rollback
  change every tag, so a browser never gets a 304 for a body another image
  produced.
- **The tag is computed before the body is built**, from those inputs
  alone. A matching `If-None-Match` skips the route's computation, which is
  the point (cause 3), not only the bytes.
- `If-None-Match` that matches returns **304 with no body**.
- `Cache-Control: private, no-cache` (revalidate every time; never stale).

Every other route keeps `no-store`, including anything that depends on the
clock or on live prices (`/live`, `/market/*`, open P&L). A test asserts the
allow-list exactly, so admitting a route is a reviewed diff. With
`ADMIN_STORE_SNAPSHOT=off`, or when computing the tag raises, the response
carries no ETag and behaves as today. The kill
switch covers both features.

**P3-d. `Server-Timing` on every `/api` response:** `db;dur=<ms>` (v205's
statement timer), `app;dur=<ms>` (wall time minus db), and
`snap;desc=hit|miss|off`. The browser probe records the header when it is
present.

### Plan 4 — analytics outliers

The plan's first task profiles in production, with v205's pipe-in cProfile
method: `cancel-precision`, `analytics/performance`,
`analytics/equity-curve`, `analytics/variance-band`, `research/ledger`,
`calendar/pnl/day/sparklines`, `equity/candles` and `market/tape`. It
records the top cumulative costs per route in this spec under
`## Plan 4 profiles`. The fix tasks are written from those profiles under
the same rules: no SQL rewrite of metrics, byte-identical JSON, and reuse
of the Layer 2 snapshot where a route re-reads trades or plans. A route
whose cost is an external fetch (Yahoo in `market/tape`, for instance) gets
a bounded cache, never a silent one. Its key is the normalised symbol set,
with a stated TTL of at most 60 s (the tape already shows "N s ago"), and
the payload carries an `as_of` timestamp per symbol. `as_of` is an added
field, declared as such under the byte-identity rule. Tape quotes are
display-only. A test asserts that no fill, sizing, risk or P&L path reads
the cache. This plan's task list stays open in this spec until the profiles
exist.

**Added 2026-11-06 (site audit): profile `/risk` too.** Production's
slow-request log (2026-11-05 15:51 to 11-06 09:47 UTC) has it at 16 calls,
avg 23.1 s, max 40.2 s, db 1.9 s, so nearly all of it is Python. An
in-process cProfile on the local replica (refresher off, so not
production-exact) put the warm call at 22.8 s: `collect_portfolio_state`
15.6 s (per-ticker `_observed` daily bars, `_clusters_state`), trade-record
loading 5.9 s (`codec.normalise`, 643k calls). The same log shows
`/versions` at avg 88 s, db 0; that was `release_windows.telemetry_for`
re-parsing `scan_telemetry.jsonl` once per release, fixed outside this spec
(f425fc9f).

### Production re-check (2026-11-06, Plan 1 still unmerged)

The partner reported the Dashboard still loads slowly. This is a
read-only check, taken during a scan with Plan 1 built in its worktree
but not on `main` or production. It found the same cause as `## Why`,
now worse:

- The `admin` container is `unhealthy` at ~97 % CPU. Load average is 6.7
  on 2 vCPUs.
- Scans take ~335 s and start every ~6 min, so the `scan` SSE event
  fires about once a second **~95 % of the time**. Scan time is the
  normal state, not the edge case.
- One Dashboard tab over ~12 min made 797 `/health`, 677
  `/system/scan`, 348 `/live` and 35 `/dashboard` calls.
- Average server time per request (`request_timing` slow log): `/live`
  13.2 s (1.75 s on 11-05), `/dashboard` 18.0 s, `/equity/candles`
  10.1 s, `/market/tape` 7.8 s, `/system/scan` 2.5 s.

Two causes this spec does not name yet. Both are follow-ups for a later
plan, not Plan 1 scope:

1. **Cancelled requests keep running on the server.**
   `LiveStore.load()` unsubscribes the previous `/live` before sending
   the next one. That aborts the XHR only, and the server finishes the
   work anyway. A request every 2 s that takes ~13 s leaves ~7 in
   flight in the one worker. P1-d removes the `scan` trigger, which
   removes the 2 s cadence. The pattern (cancel in the browser,
   re-request while the server is still busy) remains for any slow
   endpoint.
2. **`/live` reads whole tables for 8 rows.** `live_events._load_plans`
   and `_closed_newest` take every plan (842) and every trade (1,164),
   then sort in Python and slice. `open_heat_state` and
   `PlanStore().records()` do full reads too. Timed in-container, in
   its own process (no GIL contention from the worker):
   `collect_events(8)` 1.7 s, `_sections` 1.2 s, `TradeLog()._all()`
   0.5 s warm. That is ~3 s per call before any contention. An
   `ORDER BY … LIMIT` read would drop this to near zero.

## Error handling

- `scan` event without `progress`, or a malformed one: the client falls
  back to the throttled `/system/scan` fetch. A malformed payload is
  treated as absent, never patched partially.
- The broker's progress read fails: the event goes out thin and is logged
  once a minute, so a broken read never stops events.
- ETag: no snapshot, or an exception before the hash, means no ETag
  (today's behaviour). A 304 is only ever sent for an allow-listed route
  with a computed tag.
- Probe: a page that never settles is recorded as `cap`, never dropped. A
  failed login exits non-zero before any page loads.

## Testing

Per plan, as listed in each plan section. Across plans:

- byte-identical JSON tests before and after for every route a plan touches,
  in v205's harness extended with an **injected clock and an injected price
  and FX source**. Fields that legitimately vary between runs
  (`generated_at`-style stamps, relative ages) are listed per route and
  pinned by the injected clock, never stripped silently;
- ETag tests: a repeat request gets 304; a trade write (version bump) gets
  200; crossing Berlin midnight on an injected clock gets 200; a build
  version change gets 200; a SIGHUP settings reload gets 200; a route off
  the list never carries an ETag; and the allow-list equals its expected
  set exactly;
- v205 L2-c's frozen-snapshot double-run test covers plan 3.

## Rollout and rollback

Each plan deploys on its own: deploy, run the probe during a scan, record
the table in `## Results`. Rollback is redeploying the previous image.
Every client change works against an older server: a thin `scan` event
falls back to fetching, a missing `today` or `prev_day` falls back to the
old calls (v205 P3), and no ETag means plain 200s. Plan 3's server changes
switch off with `ADMIN_STORE_SNAPSHOT=off` via SIGHUP.

## Panel review

Spec review 2026-11-05 (staff-engineer on opus, senior-engineer and
quant-engineer on sonnet), against 2a74d023. Every finding was applied.

**BLOCKING**

- staff-engineer: the ETag lacked a build version, so a deploy or rollback could 304 a body from another image -- applied (P3-c key).
- senior-engineer: `TapeFeed` already coalesces same-tick callers, so the proposed fix and test were no-ops -- applied (P1-e: cause unknown; first write a failing reproduction).
- senior-engineer: payload signal vs throttled counter unspecified, no validator, and the "never a patch" doc contradicted -- applied (P1-c two signals, `parseScanEventProgress`, doc and spec change).
- senior-engineer: the settle rule had no test -- applied (P1-a pure `settle_time`).
- quant-engineer: `/dashboard` carries price-dependent open P&L with no price input in the tag -- applied (`/dashboard` excluded; field audit per route).
- quant-engineer: byte-identity was undefined for time-dependent fields -- applied (injected clock, price and FX; varying fields listed and pinned).
- quant-engineer: the tape cache had no key, TTL, as-of or isolation from money paths -- applied (plan 4).

**ADVISORY**

- staff-engineer: the progress read on the listener thread must not block -- applied (narrow read, after debounce, 200 ms timeout).
- staff-engineer: `progress_store.read()` swallows errors, so the failure branch was unreachable -- applied (raising variant or sentinel; thin, never null).
- staff-engineer: `scan` is raised by four sources, and the bot-heartbeat fields now refresh on `bot` only -- applied (stated in P1-b).
- staff-engineer: the thin-event invariant and degraded-mode stale payload -- applied (P1-c clearing rules).
- staff-engineer: settings hot-reload missing from the tag -- applied (settings generation).
- staff-engineer: tag computed before the body -- applied.
- staff-engineer: SSE thread budget unrecorded -- applied (open stream count in each result).
- staff-engineer: `system.store`'s own `/system/scan` fetch -- applied (5 s throttle, in scope).
- senior-engineer: the 5-minute `/health` timer needs fake-timer specs -- applied.
- senior-engineer: rate-limited log needs an injected clock and a named counter; one read per publish -- applied.
- senior-engineer: idle rate not computable, scan-state rule and 5 s outlier rule -- applied (Measurement rules).
- senior-engineer: calendar date source and a credential-leak test -- applied (`--date` required; sentinel test).
- senior-engineer: `/live` field audit only in prose -- applied (field-to-trigger table plus an exact-array spec).
- senior-engineer: optional `progress` field wiring, debounce and collapse -- applied (P1-b).
- senior-engineer: complexity measured on touched functions -- applied (Plan 1 Complexity).
- quant-engineer: percentiles at small n -- applied (nearest-rank, n >= 5, `thin`).
- quant-engineer: scan state sampled only at the ends; rounds mixed -- applied (per-page samples, run labels, rounds separate, provenance).
- quant-engineer: pinned date and SHA -- applied.
- quant-engineer: capped pages mixed into settle statistics -- applied (capped share reported apart).

## Results

Filled in by each plan after its production probe run.

### Baseline (2026-11-05, before v206)

The table in `## Why`. Throwaway probe, 2 rounds × 12 pages, scan
running, settle cap 90 s. Nearly every page hit the cap, so none ever went
quiet.

### Plan 1 baseline (committed probe)

**Superseded by `### Plan 1 after` below: the scan baseline was never taken and is no longer owed.** One run so far, and it is labelled `quiet`, so it does
not count toward the Goal (only `scan` runs do). The `scan` baseline is still
owed: rerun the probe during a US-session scan (`--date 2026-11-03`, same
flags) before V206-13 pushes, then replace this note with that run's table.

| Run | Label | When | Image | Pages | Idle tab |
|---|---|---|---|---|---|
| `v206-baseline-quiet-1` | quiet (not evidence) | 2026-11-05 22:03 UTC, no scan running | `ghcr.io/cmghuy/discord-bot:sha-d0500efab0cc` | 36 | 17 requests in 120 s = 8.5/min |
| `v206-baseline-mixed-1` | mixed (not evidence) | 2026-11-06 12:39 Berlin, scan ended mid-run | `ghcr.io/cmghuy/discord-bot:sha-d5f56464e217` | 36 | 79 requests in 120 s = 39.5/min |
| `v206-baseline-scan-1` (labelled mixed) | mixed (not evidence) | 2026-11-06 15:44 Berlin, session scans every 5 min (~286 s each), gaps between them hit some samples | `ghcr.io/cmghuy/discord-bot:sha-68927fbd8cc2` (ui 1.40.0 / bot 2.17.0, pre-Plan-1), probe `92d2b3f7` | 36 | 38 requests in 120 s = 19.0/min |

The mixed run (scan stopped partway) still shows the load: `/cancel-precision`
43.0 s max, `/analytics/performance` 35.6 s, `/dashboard` median 10.8 s /
p90 23.9 s over 27 samples, `/market/tape` 169 calls (median 4.3 s, max 51.8 s)
and an idle tab at 39.5 requests/min. The `scan` baseline is still owed.

The second mixed run (15:44 Berlin, mostly inside scans) is worse: 27 of 36
pages hit the 90 s cap in round 1. `/system/scan` 289 calls (median 1.1 s,
p90 34.7 s, max 50.4 s), `/health` 351 calls (p90 32.8 s, max 50.2 s),
`/dashboard` median 17.0 s / p90 33.1 s over 15 samples, `/market/tape` 76
calls (median 10.7 s, p90 23.3 s, max 49.1 s), `/trades` median 13.8 s, and
`/insights/*`, `/risk`, `/system/versions` page loads timed out. A strict
`scan` label looks unreachable with back-to-back 5-minute session scans: the
few seconds between scans catch at least one sample per hour-long run. The
Plan 1 after-run (V206-13) should be compared against this run with that
caveat, using the same flags.

Worth knowing from the quiet run: with no scan running the idle tab already
sits near the Plan 1 target (under 10/min), as expected since the polling
under repair is scan-driven. Heavy calls were still slow with the scan off
(p90 / max: `/dashboard` 11.9 s / 12.7 s, `/live` 9.9 s / 25.5 s,
`/market/tape` 6.4 s / 23.4 s; `/versions` max 56.7 s), so scan polling is
not the only load on the single admin worker. Plans 2-4 own those calls. The
probe's `/health` had no `sse_streams` yet (it ships in V206-4), so the
stream count reads `-`.

### Plan 2 boot merge (V217-1)

**Verdict: no merge. Both boot `/trades` calls stay.** Pinned by
`frontend/src/app/workspaces/dashboard/dashboard.spec.ts` ("Dashboard boot
/trades calls (v217 V217-1)") and
`frontend/src/app/workspaces/dashboard/panels/exposure-by-horizon.spec.ts`
("exposure by horizon vs the Open tab (v217 V217-1)").

The Dashboard boot sends two `/trades` requests, as § Plan 2 says:

| Caller | Query | Feeds |
|---|---|---|
| `dashboard.ts` `recent` (activity feed) | `sort=-opened_at&page=1&per_page=20`, no status | `deriveActivity` (at most 6 events), `liveSymbols` for Refresh, the trade drawer's lookups, the `recentSettled` redirect rule |
| `positions-table.ts` own `TradesStore` | `status=ACTIVE&sort=-opened_at&page=1&per_page=<10 desktop, 5 tablet/phone, or saved>` | the Open tab, its server pager, its own `trades`-event refetch |

Why they cannot merge under this section's rule ("the same rows in the same
order, asserted by a spec"):

1. The feed is not a superset of the Open tab. It holds the 20 newest rows of
   every status, so an ACTIVE position opened before those 20 is rendered by
   the table and missing from the feed (the spec seeds exactly that case).
2. The page sizes differ (20 vs 10/5/saved), and the table pages on the
   server and refetches on its own events. A shared response would have to
   carry both windows.

The brief behind plan v217 counted a third call, `sb-exposure-by-horizon`
(`status=open&per_page=200`). That panel is not mounted. It left the
Dashboard template in `d9fef9eb` (2026-09-12), and the boot spec asserts no
such element and no such tag in `dashboard.ts`. Had it been mounted, it still
could not share the Open tab's call: `status=open` is ACTIVE plus PARTIAL at
200 rows unpaged, `status=ACTIVE` is ACTIVE only and paged, so a PARTIAL
runner lands in one and not the other. Deleting the unmounted panel
(`panels/exposure-by-horizon.ts`, its spec and its `PANEL_HELP` entry) is a
follow-up outside plan v217.

### Plan 1 after (committed probe)

**Not evidence for the Goal.** The scan baseline (V206-3) was never taken: Plan 1
deployed before it, so production no longer runs the code it had to measure.
Scans also run back to back every ~5 minutes (about 4 min each), so a strict
`scan`-labelled run is not reachable. Partner decision 2026-11-06: record the
`mixed` after-run and compare it with the old-image `mixed` run above.

| Run | Label | When | Image | Pages |
|---|---|---|---|---|
| `v206-after-mixed-1` | mixed (not evidence) | 2026-11-06 17:17 Berlin | `ghcr.io/cmghuy/discord-bot:sha-2365278852ec` | 36 |

Old-image mixed run → after-run (same probe, same flags):

| Measure | Before | After |
|---|---|---|
| `/dashboard` p90 | 23.9 s | 14.8 s |
| `/cancel-precision` max | 43.0 s | 11.7 s |
| `/analytics/performance` max | 35.6 s | 0.33 s |
| `/market/tape` calls / max | 169 / 51.8 s | 73 / 9.2 s |
| Idle tab | 39.5 req/min | 22.5 req/min |

Confound: the after image also carries v204 (Risk/Analytics/Calendar read stored snapshots), so `/analytics/performance` and part of `/cancel-precision` are v204's effect, not Plan 1's. Indicative improvement, but the idle rate still sits above the under-10/min
target and ten endpoints still exceed 5 s p90. The heavy calls (`/dashboard`,
`/trades`, `/live`, `/market/tape`) are owned by the later v206 plans.

## Panel review (pre-close-out, Plan 1)

staff-engineer, senior-engineer, quant-engineer over `bfde298c^1...bfde298c`: 0 blocking, 16 advisory.

- staff: after-table credits Plan 1 with v204's effect -- applied (confound named)
- staff: baseline note contradicts the after section -- applied (marked superseded)
- staff: probe keeps results in memory until the end -- carried to the later plans (probe checkpointing)
- staff/senior: scan-event progress read runs on the listener thread, side pool budget undocumented -- carried (bounded by 250 ms statement timeout)
- staff: lint was red after the merge -- rejected: fixed on main by 472da417/13920002 before this close-out
- staff: `sse_streams` counts one process -- rejected: spec pins one gunicorn worker
- senior: `summarise` complexity 13, `payload(_name)` comment -- rejected: under the limit, cosmetic
- quant: hung/failed calls and page-with-no-calls bias the probe low; scan label ignores the idle window; meta lacks probe dirtiness/host; raw probe.json not committed -- carried to the later plans' probe work

### Plan 2 after (committed probe)

**Not a strict `scan` run:** labelled `mixed`, like both pre-Plan-1 runs (scans run
back to back, so the gap between two scans always catches a sample). Run
2026-11-06 17:43 Berlin, `--date 2026-11-03`, 3 rounds x 12 pages, image
`ghcr.io/cmghuy/discord-bot:sha-7b17ccc000ae` (ui 1.40.3 / bot 2.17.3: v206
Plan 1 + v217), credentials absent from the output. Compared with the
second pre-Plan-1 run (15:44 Berlin, image `sha-68927fbd8cc2`, same flags);
the two share a label and a time of day, so the comparison is fair but not
a strict A/B. Output: `.superpowers/probe/v217-after-1/` (git-ignored).

| Endpoint | Before p90 / max | After p90 / max |
|---|---|---|
| `/system/scan` | 34.7 s / 50.4 s (289 calls) | 0.7 s / 2.2 s (78 calls) |
| `/health` | 32.8 s / 50.2 s (351 calls) | 0.15 s / 0.43 s (78 calls) |
| `/session` | 16.3 s / 39.8 s | 0.10 s / 0.21 s |
| `/dashboard` | 33.1 s / 35.8 s (median 17.0 s) | 11.4 s / 16.2 s (median 9.0 s) |
| `/market/tape` | 23.3 s / 49.1 s (76 calls) | 6.9 s / 9.3 s (78 calls) |
| `/trades` | 20.5 s / 21.0 s | 11.1 s / 11.4 s |
| `/market/updates` | 12.3 s / 43.4 s (171 calls) | 1.9 s / 5.0 s (229 calls) |
| `/live` | 10.8 s / 17.2 s | 8.8 s / 10.1 s |
| Idle tab | 38 requests / 120 s = 19.0 per min | 33 requests / 120 s = 16.5 per min |

The scan-time polling Plan 1 removed is gone: `/system/scan` and `/health` calls
fell by 73% and 78%, and both are fast again. No page load timed out this
time (the baseline had `/risk`, `/insights/*` and `/system/versions` loads at
the 90 s cap). Still slow and owned by Plans 3 and 4: `/dashboard` (median
9 s), `/trades` (9 s median) and `/live` (5.5 s median), plus
`/cancel-precision` (36 s max, 3 calls). The idle tab at 16.5 per minute
is still above the Plan 1 target of under 10 per minute, so that target is
not met in a mixed run and needs a look in Plan 3.

The probe cannot show v217's own savings: it opens the Dashboard on 1D, which
sent one `/dashboard` before v217 too, and a mid-month day page made no extra
month call before either. The wider-scope Dashboard request and the
day-edge month lookup are pinned by their specs (V217-3, V217-4, V217-5, V217-5b).

### Plan 3 version() gap (V218-1)

`(count, max(updated_at))` is built from stamps written before commit:
`upsert()`/`patch()` use `clock_timestamp()` (`repositories/base.py:89,101`),
`insert()` uses the column default `now()` (transaction start). A transaction that
commits after a concurrent one can therefore land under an older stamp, and the
token does not move although a row changed.
`tests/db/test_v218_store_versions.py` reproduces it on two real connections for
`trades` (`TradeRepository.version()`, new in V218-1) and `plans`.

Existing callers of `plans_repo().version()`:

| Caller | Use | Verdict |
|---|---|---|
| `swingbot/admin/api_v1/cancel_precision.py:38-41` `_memo_key()` | memo key `(version, UTC hour)` of the cancel-precision payload | affected: an upsert committed under an older stamp leaves `(count, max)` unchanged, so the memo serves the old payload until the hour turns |
| `swingbot/admin/watchlist_rows.py:67-73` `_plans_signature()` | signature `("db", count, max)` of the watchlist plan projection | affected: same mechanism; stale until a later plan write moves the token |

Fix: V218-6 appends `store_generation.generation("trades")` to both keys. The
v218 snapshot listener bumps that generation on every `trades` NOTIFY, and the
`plans` and `starred_plans` triggers fire that channel too. The snapshot (V218-4)
and the ETag (V218-8) never trust versions alone either: their tokens carry the
generations too.
