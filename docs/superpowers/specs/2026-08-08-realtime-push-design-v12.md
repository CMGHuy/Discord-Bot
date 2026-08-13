# Real-time event push (bot → admin → browser)

**Date:** 2026-08-08
**Version:** ui 1.0.9 · bot 1.1.2
**Status:** design agreed, not implemented
**Scope:** design only — transport and event contract, no Angular, no implementation

## Why this exists

The admin UI is being rebuilt as an Angular SPA. That migration is too large for
one spec, so it is split into six sub-projects:

| # | Sub-project | Status |
|---|---|---|
| 1 | REST API for the whole admin surface | agreed (`2026-08-08-admin-rest-api-design-v11.md`) |
| 2 | **Real-time event push (bot → admin)** | **this document** |
| 3 | Design system | agreed (`2026-08-08-admin-design-system-design.md`) |
| 4 | Angular shell + build/deploy/auth | not started |
| 5 | The workspace implementations | not started |
| 6 | Cutover, delete Jinja | not started |

This document covers **only** sub-project 2: how the browser learns that
something changed without asking. It specifies no endpoint bodies (sub-project
1 owns those), no Angular consumption (sub-project 4), and no UI behaviour
(sub-project 3).

## The problem being solved

The admin UI polls. `dashboard.js` re-fetches `/dashboard/fragment` on a user-
configurable timer and `/scan/status` every 5 seconds, unconditionally, forever.

Three costs:

1. **It re-renders whether or not anything changed.** The card-flash animation
   exists to tell you *something* happened — sub-project 3 removed it precisely
   because a 5-second heartbeat is not information.
2. **A whole HTML fragment per tick**, re-rendered server-side, to discover that
   nothing moved.
3. **Latency is the poll interval.** A trade closing is visible somewhere
   between instantly and one full interval later.

The SPA makes 1 and 2 worse, not better: it would poll several JSON endpoints
per workspace instead of one fragment.

### The awkward part: the bot cannot talk to the admin

The bot and the admin are **two separate processes in two separate containers**
(`docker-compose.yml`). They share exactly one thing: the project directory,
bind-mounted to `/app` in both. There is no socket, no queue, no shared memory —
the bot's entire output is files under `data/`.

So "push" here can only mean: the admin notices a file changed, and tells the
browser. The bot is not modified by this sub-project at all.

## Decision 1 — SSE over a file watcher

**Transport: Server-Sent Events at `GET /api/v1/events`. Source: the admin
process watching `data/` for modification.**

SSE because the traffic is one-directional. Every command the browser sends —
close a trade, pause the scan, flip the killswitch — is already an HTTP POST
with a response, and sub-project 1 specifies it as such. A bidirectional socket
would carry nothing in the upstream direction.

**Rejected — WebSocket (Flask-SocketIO):** adds a dependency, a protocol
upgrade path through whatever proxy sits in front, and a second way to invoke
commands that would immediately diverge from the REST ones. It buys a channel
this application has no traffic for.

**Rejected — Redis pub/sub with the bot publishing:** this is the architecturally
correct answer and it is genuinely better — real events at the moment of the
state change, with the bot naming what happened instead of the admin inferring
it. It is rejected on cost, not on merit: a third container, a new runtime
dependency, and modifications to the bot's write paths, for a single-user tool
whose current latency floor is 5 seconds. **If the bot ever needs to push
something the filesystem does not reveal, this is the decision to revisit.**

**Rejected — keep polling, just poll JSON:** honest, and it would work. It
loses the thing that makes the Cockpit feel live and leaves every workspace
inventing its own interval.

### Being honest about what this is

**The file watcher is a polling loop wearing a push costume.** The admin polls
`stat()` on a small set of paths; the browser gets a push. The end-to-end
latency floor is the watcher's interval, not zero.

That is fine here, and it is worth saying why rather than hiding it:

- `stat()` on ~15 paths is microseconds. The current design polls a full
  server-rendered HTML fragment. Moving the poll from the network to the
  filesystem is three orders of magnitude cheaper, which is what buys the
  interval reduction from 5s to sub-second.
- The data itself is not faster than this. The bot writes on a scan tick
  (`SCAN_INTERVAL_MINUTES`); price updates arrive on the monitor's own cycle.
  Sub-second delivery of a value that changes every few minutes is already far
  past the point of diminishing returns.

**Watcher interval: 500ms.** Not configurable. A knob here is a decision
deferred to the user, which sub-project 3 identified as the root cause of the
problems it was fixing.

**Rejected — inotify/`watchdog`:** true kernel notification, no interval. It is
rejected because the volume is bind-mounted from a Windows host in development
and from the host filesystem in production, and inotify events across bind
mounts and network filesystems are the classic source of "works on my machine".
A `stat()` loop behaves identically everywhere. `watchdog` also silently falls
back to polling on the platforms where its native backend is unavailable — the
same loop, with a dependency in front of it.

## Decision 2 — Partial reads are already impossible

> **NG23 correction (2026-08-12).** This decision's premise is too strong, and
> the audit it demanded is what found that out. Eight of the watched `.json`
> paths are written atomically as claimed below; **six are not** —
> `scan_snapshots.json`, `bot_heartbeat.json`, `watchlist.json`,
> `ticker_directory.json`, `admin_jobs.json` and `.env` use plain
> `open(path, "w")` + `json.dump`. The conclusion the decision draws still
> holds for the *watcher*, which never opens a watched file; what does not
> hold is the claim that a mid-write read is impossible anywhere. Full list,
> line references and the narrowness of the actual race:
> `docs/claude/known-traps.md`.

The one thing that would make file-watching genuinely dangerous — reading a
file mid-write and parsing half a JSON document — **does not happen in this
repo**, and that is not luck.

`swingbot/core/jsonio.py` writes to `<path>.tmp`, fsyncs, then `os.replace()`s
into position. `plan_store.py`, `data_store.py` and `data_refresh.py` each do
the same. `os.replace` is atomic on both POSIX and Windows, so a reader either
sees the whole old file or the whole new one. The mtime changes on the rename,
which is exactly the signal the watcher wants.

**This is a load-bearing property and the implementation must not assume it
without checking.** Every path the watcher covers must be confirmed to go
through an atomic writer. Two categories do not, and are handled differently:

- **Append-only `.jsonl`** (`scan_telemetry.jsonl`, `settings_audit.jsonl`) — a
  reader can catch a half-written final line. The watcher does not parse these;
  it emits a change event and the client refetches through the API, which owns
  tolerating a torn trailing line.
- **Flag files** (`scan_running.flag`, `scan_paused.flag`, `trigger_check.flag`,
  `stop_scan.flag`) — existence and mtime are the entire content. Nothing to tear.

The watcher **never parses a watched file.** It compares `(exists, mtime, size)`
and nothing more. This keeps it immune to content-level races and to every
schema change in the files it watches.

## Decision 3 — Thin events

An event says **what changed, not how**:

```
event: trades
data: {"seq": 4812, "at": "2026-08-08T14:03:11+00:00"}
```

The client refetches whatever it is currently displaying, through the normal
sub-project 1 endpoints. There is no payload to keep in sync with the API, and
no second serialisation of a trade.

**Rejected — fat events carrying the changed object.** The watcher does not
know what changed inside a file; it knows the file's mtime moved. Producing a
fat event means keeping the previous parse in memory, re-parsing, and diffing —
per file, per tick — plus a second serialiser that will drift from the API's.
The failure mode of that drift is a UI showing a shape the API would never
return, which is a genuinely nasty class of bug for a modest saving in requests.

**Cost accepted:** one event triggers one refetch, so a burst of writes could
produce a burst of requests. Debouncing (Decision 4) is what keeps that bounded.

### Event taxonomy

One event type per *concern*, not per file — several files can raise the same
event, and the client should not know the storage layout.

| Event | Raised by | The client should |
|---|---|---|
| `trades` | `trades.json`, `plans.json`, `starred_plans.json` | refetch the visible trades list / open trade detail |
| `account` | `account.json`, `state.json` | refetch `/api/v1/cockpit` |
| `analytics` | `analytics_snapshot.json` | refetch the open Analytics view |
| `journal` | `journal.json` | refetch notes on the open trade |
| `scan` | the four `*.flag` files, `scan_snapshots.json`, `scan_telemetry.jsonl` | refetch `/api/v1/system/scan` |
| `bot` | `bot_heartbeat.json` | update the shell's connection indicator |
| `risk` | `killswitch.json` | refetch `/api/v1/risk` |
| `universe` | `watchlist.json`, `ticker_directory.json` | refetch the ticker list |
| `jobs` | `admin_jobs.json`, `tuning_results/` | refetch job status |
| `settings` | `.env` | refetch settings; warn that another session changed them |
| `resync` | server-initiated | refetch **everything** currently on screen |
| `ping` | every 20s | nothing — keeps the connection from idling out |

`settings` watching `.env` is what makes the SPA notice that a *different* admin
tab, or a hand edit on the server, changed configuration underneath it. The
current UI has no such notification and silently overwrites.

## Decision 4 — Debounce, sequence, and recovery

**Debounce: 250ms trailing, per event type.** A scan tick writes several files
in quick succession; the client should get one `trades` event, not four. The
trailing edge is right rather than the leading edge — the goal is "tell me when
the burst settles", not "tell me the instant it starts".

**Every event carries a monotonic `seq`,** issued per connection from a
process-wide counter. It is emitted as the SSE `id:` field so the browser sends
it back as `Last-Event-ID` on reconnect.

**Recovery is a resync, not a replay.** On reconnect the server does not
attempt to replay missed events — it emits a single `resync`. This is correct
*because* the events are thin: a missed event means only that the client's data
is stale, and a full refetch fixes staleness regardless of how many events were
missed or how long the gap was. Keeping a replay buffer would add state, a
retention policy, and a class of bug (buffer overflow → silently wrong UI)
purely to optimise a case that the resync already handles.

`Last-Event-ID` is therefore accepted and logged but not acted on. It stays in
the protocol because it costs nothing and is the natural place to build from if
replay is ever wanted.

**Fallback:** if `EventSource` fails to establish or reconnects more than three
times in a minute, the client falls back to polling the endpoints it needs at
the old 5-second interval and shows a degraded-connection indicator in the shell
(sub-project 3's bot/connection status component). **The UI must remain correct
with the event stream entirely dead** — the stream is an optimisation, never the
only way data arrives. This is the acceptance criterion sub-project 5 should
test by simply blocking the endpoint.

## Decision 5 — Server constraints

The admin runs on **Werkzeug's development server** (`app.run(host, port,
debug=False)` at `app.py:1165`), threaded, in production. That is a pre-existing
condition, not something this sub-project introduces, but SSE interacts with it:

- **Each open SSE connection holds one thread for its lifetime.** With one user
  and a handful of tabs this is unremarkable. It would not be, with many.
- **Cap concurrent event connections at 8**, rejecting further ones with `503`
  and `{"error": {"code": "unavailable"}}`. The cap exists so that a reconnect
  bug in the client leaks visibly and boundedly instead of exhausting the
  process.
- **One watcher thread for the whole process**, started lazily on the first
  connection, fanning out to per-connection queues. Not one watcher per client —
  that would multiply the `stat()` load by the number of tabs.
- The watcher thread must be a **daemon** and must survive an exception on any
  single path (a file being replaced as it is stat-ed is normal), logging at
  most once per path per minute so a permanently missing file cannot flood the
  log the SPA is displaying.

**Docker healthcheck:** unaffected — it curls `/` and accepts 200/401/302, which
does not touch this endpoint. Worth stating because a long-lived streaming
response is exactly the kind of thing that breaks a naive healthcheck.

**Auth:** `/api/v1/events` is guarded like every other v1 route. `EventSource`
cannot set headers, so it relies on the session cookie — which is why
sub-project 1 keeps cookie auth rather than moving to a bearer token. If auth
fails, the endpoint returns `401` with the JSON error body before the stream
starts, and the client must not retry blindly.

## What this retires

At cutover (sub-project 6), all of it — but the mapping is stated here because
it is the justification for the work:

- `dashboard.js`'s `setInterval` on `refreshDashboard` → `account` + `trades`
- `dashboard.js`'s 5-second `refreshScanStatus` → `scan` + `bot`
- The Plans board's polling in the Jinja UI → `trades`
- Job progress polling on the Tuning page → `jobs`
- The "auto-refresh" checkbox and its interval setting → nothing. The concept
  disappears; there is no interval to configure.
- The card-flash-on-refresh animation → already removed by sub-project 3

## Explicitly out of scope

- Any change to the bot process or its write paths
- Endpoint response bodies (sub-project 1)
- The Angular `EventSource` client and how it lands in the store (sub-project 4)
- Per-workspace refetch behaviour (sub-project 5)
- Replacing the Werkzeug dev server with a production WSGI server. It is a real
  issue and this spec is constrained by it, but fixing it is a separate change
  with its own deployment risk and must not be smuggled in here.

## Risks

**The 500ms `stat()` loop is a permanent background cost** for a process that
currently idles. It is small, but it never stops, and on a small Hetzner
instance shared with the bot's scanning it is worth measuring rather than
assuming. Measure before and after.

**A file whose mtime changes without its content changing produces a spurious
event**, and therefore a spurious refetch. Rewriting an identical
`analytics_snapshot.json` on every refresh would do exactly this. Harmless for
correctness, wasteful in aggregate — if it shows up in practice, the fix is
hashing the file, which is a bigger read cost and should only be paid where
measurement justifies it.

**Bind-mounted filesystems can report mtime with coarse granularity** (one
second on some, worse on network mounts). Two writes inside the same granule can
look like one. The debounce already coalesces those into a single event, so the
consequence is bounded — but it means the watcher must compare `size` as well as
`mtime`, which is why Decision 2 specifies both.

**A dead event stream that fails silently is the worst outcome** — a UI that
looks live and is not. The degraded-connection indicator is the mitigation and
it must be visible, not a console warning.

## Open questions

None blocking. Two to settle during implementation:

1. Whether `scan` needs a higher-frequency path during an active scan (progress
   moves fast for a few minutes, then nothing for an hour). The 500ms watcher
   probably covers it; measure before adding a special case.
2. Whether `settings` should carry the changed key names rather than being
   thin. It is the one case where the client's reaction differs by field, and
   `.env` is small enough to diff cheaply. Decide when sub-project 5 builds the
   System workspace.
