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
- **no endpoint over 5 s** (max);
- one idle tab sends **under 10 requests per minute** during a scan
  (today ~120);
- JSON stays **byte-identical** for the same database state, except fields a
  plan adds on purpose (it removes none).

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
  `system/versions`) for `--rounds` rounds (default 2). Each is a full load
  at the root path (production serves the SPA at `/`, not `/app/`).
- A page counts as **settled** once no `/api` call (ignoring
  `/api/v1/events`) has been in flight for 2 s, capped at `--cap` seconds
  (default 90). It records the settle time, or `cap` when the page never
  goes quiet.
- Per call it records the URL, status, start offset, TTFB, total time and
  bytes.
- Writes `--out <dir>/probe.json` and `probe.md`: per-endpoint
  n/median/p90/max TTFB, per-page requests per minute, and the first heavy
  call's TTFB per page. "Heavy" means any `/api` path outside `session`,
  `health`, `system/scan`, `system/preferences`, `risk/killswitch` and
  `market/updates`. It also reads `/api/v1/system/scan` once at the start
  and end and records `scan_running`.
- `--base` defaults to `https://bomeo-capital.com`; a local instance works
  the same way.
- Read-only: GETs, plus the session POST.

The aggregation (URL normalisation, percentiles, requests per minute, the
heavy-call rule) lives in pure functions with unit tests on a JSON fixture.
The browser part is not unit-tested.

**P1-b. Scan progress travels in the `scan` event.** `Event`
(`admin/events/broker.py:67`) stays thin for every event except `scan`,
which gains an optional `progress` field. Its shape is the subset of
`/system/scan` (`api_v1/system.py:_scan_status`) the progress strip and
connection store read: `running` and `progress`, the latter being the same
record the route returns. The broker builds it **once per published `scan`
event**, never per connection. Whatever reads the record for
`_scan_status` today is reused, not copied. If the read raises, the event
goes out thin, and the failure is logged at most once a minute
(`progress_errors` counted). Every other event's `data()` stays
byte-identical.

**P1-c. Client.** In `connection.store.ts`:

- On a `scan` event **with** `progress`, patch `scanRunning` and
  `scanProgress` from the event and send no request.
- `/system/scan` is fetched at boot, on `bot`, on `resync`, and as a
  **fallback** when a `scan` event arrives without `progress` (an older
  server, or a failed read). The fallback is throttled to one request per
  5 s, using the existing `EventStream` throttle mechanism at a 5 s
  interval.
- `/health` is fetched at boot, on `bot`, and every 5 min while the tab is
  visible. It no longer reacts to `scan`.
- `EventStream` must expose the last event's data for `scan`. Today it
  exposes only counters. The change is additive: counters keep working for
  every other subscriber.

**P1-d. `/live` stops reacting to `scan`.** `LIVE_REFRESH_EVENTS` becomes
`['trades', 'bot', 'risk']`. The plan's first `/live` task lists every
field of the `/live` payload and shows that none changes during a scan
except through `trades`, `bot` or `risk`. Any field that does gets its own
named trigger, never `scan` back.

**P1-e. One boot tape request.** Find why `TapeFeed` (`stores/tape-feed.ts`)
sends the same symbol list twice at boot (probably two registrations in the
same tick, each starting a request). Coalesce registrations made in one
tick into one request. Same output, one call.

**Plan 1 tests:**

- broker: a `scan` event carries `progress`; other events are
  byte-identical; a raising read sends a thin event and logs once.
- `connection.store` spec: no `/health` call on `scan`; progress is patched
  from the event; a thin event triggers at most one fallback call per 5 s;
  `bot` and `resync` still fetch.
- `live.store` spec: `scan` triggers nothing.
- `TapeFeed` spec: two registrations in one tick make one request.
- probe aggregation unit tests on a fixture, including an empty run and a
  page that hits the cap.

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
`/trades`, `/calendar/pnl`, `/calendar/pnl/day`, `/dashboard`, and plan 4's
routes once they read the snapshot; each route is admitted by an audit
task, never assumed). For those routes:

- A weak ETag, the hash of (snapshot generation, `PlanRepository.version()`
  and its trades twin, the normalised query string, today's Berlin date,
  the authenticated user).
- `If-None-Match` that matches returns **304 with no body**.
- `Cache-Control: private, no-cache` (revalidate every time; never stale).

Every other route keeps `no-store`, including anything that depends on the
clock or on live prices (`/live`, `/market/*`, open P&L). A test asserts the
allow-list exactly, so admitting a route is a reviewed diff. With
`ADMIN_STORE_SNAPSHOT=off`, or when a route raises before its ETag is
computed, the response carries no ETag and behaves as today. The kill
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
a bounded cache with its staleness stated in the response, never a silent
one. This plan's task list stays open in this spec until the profiles
exist.

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

- byte-identical JSON tests before and after for every route a plan touches
  (v205's harness);
- ETag tests: a repeat request gets 304; a trade write (version bump) gets
  200; crossing Berlin midnight on an injected clock gets 200; a route off
  the list never carries an ETag;
- v205 L2-c's frozen-snapshot double-run test covers plan 3.

## Rollout and rollback

Each plan deploys on its own: deploy, run the probe during a scan, record
the table in `## Results`. Rollback is redeploying the previous image.
Every client change works against an older server: a thin `scan` event
falls back to fetching, a missing `today` or `prev_day` falls back to the
old calls (v205 P3), and no ETag means plain 200s. Plan 3's server changes
switch off with `ADMIN_STORE_SNAPSHOT=off` via SIGHUP.

## Results

Filled in by each plan after its production probe run.

### Baseline (2026-11-05, before v206)

The table in `## Why`. Throwaway probe, 2 rounds × 12 pages, scan
running, settle cap 90 s. Nearly every page hit the cap, so none ever went
quiet.
