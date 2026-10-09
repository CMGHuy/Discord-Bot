# v148 — Ops hardening: production WSGI, login hardening, liveness alerts, provider and swallowed-error visibility

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** ui patch · bot patch — ui: the partner sees two new panels on the System → Scan tab and a "too many attempts" login message; the server swap under them is invisible. bot: new ops-channel notices (stale scan, provider degradation, recovery); no alert, plan or trade changes.
**Edge:** none (integrity) — no change to what is scanned, alerted or traded; it buys earlier detection of a dead bot or a degraded data feed, nothing on `ExpR`
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer
**Status:** spec written 2026-10-09; design approved in the brainstorm; plan not written.

## Why

Five gaps, each one a way production can be wrong without anyone seeing it:

1. The admin UI runs Flask's development server (`app.run`,
   `swingbot/admin/app.py:378`, launched by `docker-compose.yml:177`). It is
   what Werkzeug itself says not to put on a public hostname, and this admin
   is public through the Cloudflare tunnel.
2. Password checks use plain `==`/`!=`, and nothing limits guessing.
3. A bot that hangs or dies posts nothing. The failure-streak escalation
   (`_maybe_escalate_health`, `swingbot/commands/scanning/loops.py:61`) only
   fires when ticks *run and fail*; a wedged tick or a dead process never
   reaches it.
4. Alpaca → yfinance fallback, stale and empty symbols are measured partly and
   shown only as a pooled rate on the Risk page; nothing alerts.
5. 323 `except Exception` handlers in `swingbot/`, `bot.py`, `admin_ui.py`
   (`git grep -n "except Exception" -- 'swingbot/*.py' bot.py admin_ui.py | wc -l`),
   no counter. The 2026-09-14 `lxml` outage (comment in `requirements.txt`)
   sat silently inside one of them.

## Facts the design rests on (verified 2026-10-09)

Several differ from the brainstorm's wording; each correction is applied below
and listed again in "Contradictions found".

- **SSE delivery is fed by Postgres LISTEN/NOTIFY, fanned out in-process.**
  `DbEventListener` (`swingbot/admin/events/db_listener.py`) holds one LISTEN
  connection per process; `EventBroker` (`swingbot/admin/events/broker.py`)
  owns a process-wide sequence counter and a cap of `MAX_CONNECTIONS = 8`
  (`broker.py:58`); the route is `stream.py:103`, the client one
  `EventSource` (`frontend/src/app/api/event-stream.ts:87`). Two workers would
  each still deliver events, but with independent `id:` sequences and a cap of
  8 *per worker*. One worker remains right; the binding reasons are the login
  limiter and the admin-side error counter (both in memory) plus a single
  sequence space.
- **The heartbeat is a database row, not a file.** `runstate._write_heartbeat`
  (`swingbot/commands/scanning/runstate.py:28`, called at `loops.py:166` at the
  start of every tick, paused or off-session included) merges
  `{timestamp, session_active, scan_paused}` into the singleton `bot_heartbeat`
  row (`swingbot/core/db/schema.py:152`, repo
  `swingbot/core/db/repositories/heartbeat.py`); extra fields land in its
  `doc` JSONB, so new fields need no migration. Its docstring still says
  "JSON file". `record_tick_success` (`runstate.py:48`) stamps `last_success`
  after every tick that did not raise — including paused and off-session ones.
- **Three plain credential comparisons, not two:** Basic in
  `app.require_auth` (`app.py:159`), Basic in the v1 decorator
  (`swingbot/admin/api_v1/auth.py:38-39`), and the SPA login form itself,
  `POST /api/v1/session` (`swingbot/admin/api_v1/session.py:56`, `!=`).
  The session check already uses `hmac.compare_digest` (`app.py:144`).
- **Behind the tunnel every request comes from the `cloudflared` container.**
  `request.remote_addr` is the same for everyone; the client address is the
  `CF-Connecting-IP` header. Nothing in `swingbot/` reads it today.
- **The SPA would mislabel a 429.** `session.store.ts:128-131` maps anything
  that is not `ApiError.isAuth` (`api-error.ts:30`) to "Could not reach the
  admin. Is it running?".
- **The scan-run record is `data/scan_telemetry.jsonl`.** One row per scan from
  `scan_run.py:1144-1159` via `telemetry.log_scan_telemetry`
  (`swingbot/core/scanning/telemetry.py:11`, which also publishes the `scan`
  NOTIFY). It already carries `tickers`, `errors` (= tickers with no frame),
  `data_sources` (`_count_sources`, `scan_run.py:56`, buckets
  `alpaca / yfinance / yfinance-fallback / cache`) and `price_sources`
  (`fetch.py:34,43`). `risk.py:82` `_data_sources_summary` pools a fallback
  rate over the last 20 rows.
- **Scan fetches run in spawned children.** `_run_bounded` uses
  `ProcessPoolExecutor(mp_context=_SPAWN_CTX)` (`fetch.py:145-148`); the
  live-price chunk (`fetch.py:64`, `:515`) runs `get_current_price_batch` in
  a fresh process whose `_last_good_batch_price` (`data.py:143`) is empty, so
  the stale fallback (`data.py:286`, used at `:207`) never serves a scan
  price. Anything counted in memory inside a child is lost unless it travels
  back with the result, as `price_sources` already does. Likewise the
  router's `_stats` (`router.py:110`, `stats()` at `:419`) never sees scan
  fetches.
- **Admin access logging rides on Werkzeug.** `admin_ui.setup_logging`
  pins the `werkzeug` logger at INFO (`admin_ui.py:24`) so the Logs page shows
  admin requests; `tests/admin/test_admin_logging.py` pins that. Under
  gunicorn those lines disappear unless `gunicorn.access` is wired the same way.
- **gunicorn does not import on Windows** (it needs `fcntl`), and this dev
  machine is Windows. No test may import gunicorn; `admin_ui.py` +
  `app.run` stays the local entry point.
- **CI boots the admin with `python admin_ui.py`** (`.github/workflows/deploy.yml:605`).

## O1 — Production WSGI server

- New `admin_wsgi.py` at repo root: calls `admin_ui.setup_logging()`, then
  `record_boot("admin")` (as `admin_ui.py` does today), then exposes
  `from swingbot.admin.app import app`. `admin_ui.py` keeps `main()` →
  `app.run` for local dev, unchanged.
- New `deploy/gunicorn.conf.py` (plain Python, no gunicorn import):
  `bind = f"{ADMIN_HOST or '0.0.0.0'}:{ADMIN_PORT or 1234}"`, `workers = 1`,
  `worker_class = "gthread"`, `threads = 16`, `timeout = 60`,
  `graceful_timeout = 5` (open SSE streams would otherwise hold every restart
  for the 30 s default; the client reconnects), `keepalive = 5`,
  `accesslog = "-"`, `preload_app = False` (the broker's listener thread must
  start in the worker, not the master). 16 threads = the 8-stream SSE cap + 8
  for ordinary requests; the cap stays at 8.
- `admin_ui.setup_logging` also pins `gunicorn.access` and `gunicorn.error`
  at INFO onto the same handlers, so admin request lines keep reaching
  `logs/admin.log`.
- `docker-compose.yml:177` → `["gunicorn", "-c", "deploy/gunicorn.conf.py", "admin_wsgi:app"]`;
  `deploy.yml:605` the same. The healthcheck (`curl /`) is unchanged.
- `requirements.txt`: `gunicorn==<exact version>` (newest 23.x on PyPI at
  implementation, pinned exactly per the file's own policy), Linux-only in use.
- **Task 1 is read-only verification** before any of this: confirm by reading
  `broker.py`, `db_listener.py`, `stream.py` and `app.py:76` that nothing in
  the admin process depends on more than one worker and nothing breaks with
  one (secret-key creation, background threads, module-level caches), and
  record the finding in the plan's Progress block. If it finds a blocker, stop
  and ask.

## O2 — Constant-time checks and a login limiter

- One helper, `credentials_match(username, password) -> bool` in
  `swingbot/admin/app.py`, doing `hmac.compare_digest` on UTF-8 bytes of both
  fields (both always compared — no short-circuit on the username). All three
  sites (`app.py:159`, `auth.py:38-39`, `session.py:56`) call it.
- New `swingbot/admin/login_limiter.py`: `LoginLimiter(max_failures=5,
  window_s=900)` with `check(key) -> int | None` (seconds to wait, or None),
  `fail(key)`, `succeed(key)` (clears the key). Sliding window over failure
  timestamps, a lock, and pruning on every call so memory is bounded by
  addresses seen in the last 15 minutes. One module-level instance — valid
  because there is one worker (O1).
- Key: `CF-Connecting-IP` when present, else `request.remote_addr`. The header
  is spoofable only by someone who can reach port 1234 directly, which the
  firewall already forbids (`docs/deploy/DEPLOY_HETZNER.md` "Accessing the
  admin UI").
- Shared by all three paths: a locked key gets **429** with `Retry-After:
  <seconds>`; v1 paths use the existing body shape (`error("rate_limited",
  "Too many failed sign-ins. Try again in N minutes.", 429)`,
  `api_v1/__init__.py:89`, header added on the returned response); the
  `app.require_auth` Basic path returns a plain-text 429. A wrong credential
  calls `fail`, a right one `succeed`. Only *attempts* count — a request with
  no credentials at all is not a failure.
- SPA: `'rate_limited'` joins `ApiErrorCode` (`api-error.ts:12`), and
  `session.store.ts` shows the server's message for a 429 instead of
  "Could not reach the admin"; `session.store.spec.ts` covers it.

## O3 — Stale-scan alerts, in the bot and from outside it

**In-bot watchdog.** New `swingbot/commands/scanning/ops_watch.py` with
`scan_watchdog`, `@tasks.loop(minutes=1)`, added to `_always_on_loops()`
(`loops.py:861`). The decision is a pure function:

`stale_scan_verdict(now, last_success, interval_min, booted_at, *, in_session,
paused, failure_alert_active, stale_alert_active) -> "alert" | "recover" | None`

- `"alert"` when in session, not paused, no failure-streak alert already
  active, `last_success` older than `2 × SCAN_INTERVAL_MINUTES`, the process
  has been up at least that long (so a morning restart after an overnight
  outage does not alert before its first tick), and no stale alert is active.
- `"recover"` when a stale alert is active and `last_success` is fresh again.
- `last_success` missing → `None` ("unknown", the same rule as
  `runstate._read_heartbeat`).

The alert posts once per incident to `_ops_channel()` (`loops.py:50`) as an
embed from `swingbot/commands/scanning/notices.py` beside
`health_alert_embed` (`notices.py:44`), naming
the age and the last success; `stale_alert_active` is persisted in the
heartbeat doc (new `runstate` getters/setters, as `alert_active` is at
`runstate.py:71-76`) so a restart neither re-posts nor forgets. This catches
the case the existing escalation cannot: `session_scan` awaits its tick, so a
wedged tick stops `last_success` while the event loop — and this watchdog —
keeps running. It cannot catch a dead process or a blocked event loop.

**Out-of-process cron.** `scripts/ops/heartbeat_watch.sh`, every 5 minutes on
the VM, 24/7 (the heartbeat is written every tick whatever the session):

- reads `doc->>'timestamp'` (written only by the bot's `_write_heartbeat`;
  `ts` is also bumped by admin-side writes such as an unpause,
  `runstate.py:101-107`) through
  `docker compose exec -T db psql -U swingbot -d swingbot -tAc ...`;
- stale when older than `max(15 min, 3 × SCAN_INTERVAL_MINUTES)` (interval read
  from `.env` with `grep`, default 5); a failed query counts as an incident of
  its own ("cannot read heartbeat");
- posts to `OPS_ALERT_WEBHOOK_URL` with `curl` once per incident and once on
  recovery, state in `logs/heartbeat_watch.state`; appends every run's verdict
  line to `logs/heartbeat_watch.log`; no URL → logs and exits 0.
- `.env` values are read with `grep '^KEY=' | cut -d= -f2-`, never sourced
  (the `$`-mangling trap noted in `DEPLOY_HETZNER.md`).
- `scripts/ops/install_heartbeat_watch_cron.sh`, idempotent, marker-line
  pattern of `install_intraday_coverage_cron.sh`; a permanent job, not
  one-shot.

Mirroring (`working-conventions.md` § Mirroring, § Scheduling): both scripts
and the `.env.example` key are committed before the install; the install, and
setting the prod webhook (`scripts/ops/env_set.py`), happen through
`ssh-hetzner.sh` only after the deploy; `DEPLOY_HETZNER.md` gains a row for the
cron next to the backup table. The prod-side task is not done until the cron
has logged one healthy verdict and a forced test post (`--test`) has reached
the channel.

## O4 — Provider degradation metrics

Per scheduled scan, three new fields on the telemetry row, computed by one
pure function `provider_health(tickers, frames, data_sources, price_sources,
today)` in `telemetry.py` and merged into `scan_stats` at `scan_run.py:1144`:

- `provider_fallback_rate` — `yfinance-fallback / (alpaca + yfinance-fallback)`
  over this scan's `data_sources` plus `price_sources`: the formula
  `risk.py:82-103` already pools over 20 scans. Both callers use the one
  function (`risk.py` passes its pooled counts); `None` when Alpaca was asked
  for nothing (disabled, or breaker open throughout).
- `empty_symbols` — tickers with no frame or an empty one (today's `errors`,
  kept), plus `empty_rate` = that / `tickers`.
- `stale_symbols` — frames whose last bar date is older than the previous
  business day (`pandas` `BDay`) in the session timezone. **Redefined from the
  brainstorm:** the `data.py:286` stale-price fallback never fires in a scan
  (spawned child, empty cache — see Facts), so "stale" here means an old daily
  frame. A market holiday can over-count the next day; `stale_symbols` is
  therefore displayed, never alerted on.

**Alert.** After each scheduled scan, `ops_watch.check_provider_health(row)`
reads the newest scan row (`recent_scan_telemetry(1)`, `telemetry.py:36`,
which already skips non-scan rows) and posts one ops embed when
`provider_fallback_rate > PROVIDER_FALLBACK_ALERT_PCT/100` or
`empty_rate > EMPTY_SYMBOLS_ALERT_PCT/100`; once per incident
(`provider_alert_active` in the heartbeat doc), one recovery notice when a scan
is back under both. Called from `_session_scan_tick` after the scan, wrapped
so it can never fail the tick.

**Config** (`swingbot/config.py` `FIELDS`, section "Data Sources", hot-reloadable,
`.env.example` updated):

| Key | Type | Default | Range |
|---|---|---|---|
| `PROVIDER_FALLBACK_ALERT_PCT` | number | 20 | 1–100 |
| `EMPTY_SYMBOLS_ALERT_PCT` | number | 5 | 1–100 |
| `OPS_ALERT_WEBHOOK_URL` | password, `sensitive=True` | "" | — (read by the cron only) |

## O5 — Swallowed-error visibility

**Helper.** New `swingbot/core/infra/swallowed.py`:

- `swallowed(log, tag, exc, msg="", *args, level=logging.WARNING, exc_info=False)`
  logs through the *caller's* logger at the caller's existing level with the
  existing message, adds `extra={"swallowed_tag": tag}`, and increments a
  thread-safe per-tag counter `{count, first_at, last_at, last_error}`
  (`last_error` = `type(exc).__name__: str(exc)` truncated to 200 chars; no
  traceback, no locals). Converting a site therefore changes no log text and
  no level — tests that assert log lines stay green.
- `snapshot()`, `merge(counts)`, `reset()` (tests only).
- Tags are `<area>.<function>` (`scan.telemetry`, `marketdata.price_batch`,
  `earnings.next_date`), unique per site.

**Child processes.** `_run_bounded` (`fetch.py:148`) submits a module-level
`_counted_call(fn, *args)` that returns `(result, swallowed.snapshot())`; a
spawned child starts at zero, so the snapshot is its delta, and the parent
merges it. A killed (timed-out) child loses its counts; its log lines remain.

**Flush.** `_write_heartbeat` adds `swallowed: {since: <process boot>, counts:
snapshot()}` to the heartbeat doc every tick. The admin reads the bot's counts
from there and its own from memory (one worker).

**Conversion — this spec's ratchet step.** Every handler catching `Exception`
in these scopes that does not re-raise becomes a `swallowed(...)` call:

| Scope | Files | `except Exception` today |
|---|---|---|
| scan | `swingbot/core/scanning/*.py` | 60 |
| marketdata | `swingbot/core/marketdata/**/*.py` | 35 |
| earnings | `swingbot/core/market/events.py`, `earnings_history.py` | 6 |

A handler that re-raises is not a swallow and stays as is. A handler that logs
nothing today calls `swallowed(..., level=logging.DEBUG)`. Behaviour
(return values, fallbacks) is unchanged at every site. `swingbot/core/
marketdata/adjustments.py` has no such handler and is not touched (another
session has it modified).

**Ratchet test** `tests/infra/test_swallowed_ratchet.py`, AST-based over
`swingbot/**/*.py`, `bot.py`, `admin_ui.py`, `admin_wsgi.py`: a handler is
*untagged* when it catches `Exception` (alone or in a tuple), its body calls
no `swallowed`, and it contains no `raise`. Two assertions: zero untagged in
the three scopes above; the repo-wide untagged count **equals**
`BASELINE` (measured after the conversion), and the failure message on a
lower count says "lower BASELINE to N" — so it can only fall.

## Admin surface

- New `swingbot/admin/api_v1/ops_health.py`, registered in the import list at
  `api_v1/__init__.py:208`: `GET /api/v1/system/health`, `require_auth`,
  returning `{providers: [last 20 scan rows: at, tickers,
  provider_fallback_rate, stale_symbols, empty_symbols, empty_rate],
  thresholds: {fallback_pct, empty_pct}, swallowed: [{process, tag, count,
  first_at, last_at, last_error}], bot_counts_since}`. Rows predating v148
  carry `null` for the new fields and render as "—".
- System → Scan tab (`frontend/src/app/workspaces/system/scan-tab.ts`, after
  the "Bot process" panel at `:129`): two new standalone components,
  `provider-health-panel.ts` (a table of the 20 scans, newest first, a
  threshold breach marked with the existing danger token plus text, not colour
  alone) and `swallowed-errors-panel.ts` (sorted by count, process column,
  relative "last seen"). Data via `system.store.ts`, refreshed on the existing
  `scan` and `bot` SSE events.

## Complexity

Every new or changed function stays below cyclomatic complexity 15
(`python -m radon cc -s -n C <files>`). `stale_scan_verdict` and
`provider_health` are written as early-return guards; the conversion never
adds a branch to a function already at or above 15 — it replaces a handler
body one-for-one.

## Testing

Per task, the narrow run (`python scripts/dev/testrun.py file ...`;
frontend `npm test -- --include <spec>`):

- `tests/admin/test_gunicorn_conf.py` — loads `deploy/gunicorn.conf.py` with
  `runpy` (no gunicorn import): one worker, gthread, threads ≥ 2 × the SSE cap,
  `preload_app` false; `admin_wsgi` exposes the same `app` object.
- `tests/admin/test_admin_logging.py` — extended for `gunicorn.access` at INFO.
- `tests/admin/test_login_limiter.py` — 5 failures → 429 + `Retry-After` on all
  three paths; success clears; window expiry (injected clock); key from
  `CF-Connecting-IP`; no-credential requests do not count.
- `tests/scanning/test_ops_watch.py` — `stale_scan_verdict` truth table
  (session, paused, boot grace, failure alert active, missing value) and the
  once-per-incident/recovery sequence with a fake channel.
- `tests/scanning/test_provider_health.py` — rates, `None` without Alpaca,
  stale by business day, risk.py's pooled figure unchanged on a fixture.
- `tests/infra/test_swallowed.py` — counter, merge, thread safety, log text and
  level unchanged; `_run_bounded` round-trips a child's counts.
- `tests/infra/test_swallowed_ratchet.py` — above.
- `tests/scripts/test_heartbeat_watch.py` — the cron script's `--dry-run
  --age <s>` prints the verdict without psql or curl; run through `bash`,
  skipped where bash is absent.
- Frontend: `session.store.spec.ts` (429 message), both panel specs.

The plan's last task runs `python scripts/dev/testrun.py full` and
`cd frontend && npm test` once each.

## Parallelisation

Task ids are the plan's to assign; groups by work unit:

- **Sequential first:** W1 (read-only single-worker verification) before W2.
- **Group 1 (parallel, after W1):** W2 gunicorn (`admin_wsgi.py`,
  `admin_ui.py`, `deploy/gunicorn.conf.py`, `docker-compose.yml`,
  `deploy.yml`, `requirements.txt`, logging test); W3 auth (`app.py`,
  `api_v1/auth.py`, `api_v1/session.py`, `login_limiter.py`,
  `session.store.ts`); W4 swallowed helper (`core/infra/swallowed.py`,
  `fetch.py` `_run_bounded`, `runstate.py` flush); W5 config keys
  (`config.py`, `.env.example`). Disjoint files, no shared symbol.
- **Group 2 (parallel, after W4):** W6a scan conversion (`core/scanning/*`),
  W6b marketdata conversion (`core/marketdata/**`), W6c earnings conversion
  (`core/market/events.py`, `earnings_history.py`). Each consumes
  `swallowed`; disjoint directories.
- **Sequential:** W7 provider metrics after W6a (both edit `scan_run.py`).
  W8 ratchet test after all of Group 2 (its `BASELINE` is the post-conversion
  count). W9 `ops_watch` + notices + `loops.py` after W4, W5, W7 (it consumes
  the heartbeat helpers, the threshold keys and the telemetry fields). W10 cron
  scripts + `DEPLOY_HETZNER.md` after W5 (consumes the webhook key name);
  otherwise parallel with W6–W9. W11 `ops_health.py` after W4, W5, W7.
  W12 frontend panels after W11. W13 full suites last.
- **After merge and deploy (production, via `ssh-hetzner.sh`):** set
  `OPS_ALERT_WEBHOOK_URL`, install the cron, confirm one healthy verdict and a
  test post; confirm `docker compose ps` shows the admin under gunicorn and the
  login works through the tunnel.

## Out of scope

Converting `except Exception` outside the three scopes (later ratchet steps,
one spec each); multi-worker admin or a shared limiter store; alerting on
`stale_symbols`; a dead-man's-switch outside the VM (the cron dies with the
VM); persisting swallowed counts across restarts.

## Contradictions found while writing (flagged, design adjusted minimally)

1. Heartbeat is a Postgres row, not a file → the cron queries the DB.
2. SSE events come from Postgres NOTIFY, so multi-worker would still deliver;
   one worker is kept for the limiter, the admin counter and one sequence space.
3. A third plain comparison exists (`session.py:56`, the SPA login) → covered.
4. Behind Cloudflare, `remote_addr` is one address → limiter keys on
   `CF-Connecting-IP`.
5. The `data.py:286` stale fallback never runs in a scan → `stale_symbols`
   redefined as old daily frames, display only.
6. Scan fetches run in spawned children → swallowed counts travel back
   through `_run_bounded`.
7. Fallback counts already exist in telemetry and risk.py → reused, one formula.
8. Werkzeug request logging and `python admin_ui.py` in CI need carrying over.
9. Bump: the cron install is a post-deploy step, but the bot and admin run
   without it, so it is not the "deploy needs a manual step" of a major.
