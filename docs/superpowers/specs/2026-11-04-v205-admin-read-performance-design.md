# v205 — Admin read performance: Dashboard and Calendar in seconds, not a minute

**Version:** ui 1.38.0 · bot 2.16.1
**Bump:** bot patch (was `bot patch, ui patch`: v205 changed no frontend file)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer

## Why

The partner reported the Dashboard taking more than a minute to show its
trades and the Calendar taking very long to show anything. The data is
small (1,113 trades, 790 plans, `trades` is 6.7 MB), so the queries are
not the problem. Measured on production on 2026-11-04, one client, no
contention, read-only timing from inside the `admin` container:

| Endpoint | Time (two runs) | Payload |
|---|---|---|
| `/api/v1/dashboard` | 9.4 s / 6.6 s | 1.4 KB |
| `/api/v1/dashboard?mode=today` | 8.5 s / 7.5 s | 1.4 KB |
| `/api/v1/trades` | 8.6 s / 8.4 s | 43 KB |
| `/api/v1/trades?status=open` | 9.6 s / 9.7 s | 19 KB |
| `/api/v1/live` | 3.6 s / 5.3 s | 2 KB |
| `/api/v1/calendar/pnl?month=2026-11` | 10.2 s / 11.8 s | 2.3 KB |
| `/api/v1/calendar/pnl/day?date=2026-11-03` | 10.3 s / 7.2 s | 7.4 KB |
| `/api/v1/calendar/pnl/day/sparklines` | 2.8 s / 1.3 s | 2.9 KB |

The database answers `select 1` in 0.5 ms and the whole `trades` table in
334 ms; `/dashboard` issues 29 SQL statements, `/calendar/pnl` 61. The time
is Python, repeated work, found by cProfile on production:

1. **FX rate lookup scans the whole pair history per call.**
   `swingbot/core/marketdata/fx.py:_close_on_or_before` converts every index
   stamp of the pair's daily frame to a `date` in a Python list on every
   call. 86 calls x ~47 ms = **4.1 s of `/calendar/pnl`'s 7.1 s**; it also
   runs inside `/dashboard` (`_open_amounts` -> `convert_amount`) and every
   money-bearing route.
2. **The same tables are loaded and parsed several times per request.**
   `/dashboard` calls `repositories/base.py:list_all` **8 times**:
   `TradeLog._all()` (1 x `_json_record` per trade, ~1 ms each),
   `PlanStore._all()` 4x via `load_plans_by_id` (twice) and
   `admin/queries.py:_plan_rows` (`plan_to_dict`, ~3 ms x 790 plans = 2.3 s),
   and `account.load_account_config` twice, each re-summing every trade in
   `_sum_realized_pnl` (2.7 s together).
3. **Every request re-parses everything**, even when nothing changed since
   the previous request a second ago.
4. **The pages multiply it.** The admin is one gunicorn worker with 16
   threads (`deploy/gunicorn.conf.py`, one worker is a requirement there), so
   concurrent requests share one GIL. The Dashboard on any scope wider than
   1D sends `/dashboard?mode=...` **and** `/dashboard?mode=today`
   (`frontend/src/app/stores/dashboard.store.ts` `loadToday`), next to
   `/trades` and `/live`. The Calendar day page sends `/calendar/pnl/day`,
   `/calendar/pnl` and up to two more `/calendar/pnl` for adjacent months
   (`calendar-day.store.ts` `loadEdge`), then sparklines. Five ~9 s requests
   on one GIL is the minute the partner sees.

Locally (Windows, Docker port-forward, replica at `v197_001`) the same
endpoints take 7–23 s; the local profile is dominated by per-ticker
`quote_currency_repo().get_many([key])` round trips because the replica
lacks the table. That N+1 shape exists on production too (59 calls in
`/calendar/pnl`, 0.26 s there): unknown codes are never memoised.


## Goal

Every endpoint above answers in **under 1.5 s after Layer 1** and **under
0.5 s after Layer 2** on production, measured with the same script, with
**byte-identical JSON** to today for the same database state, except the
converted money amounts L1-a deliberately moves onto the daily 08:00 rate
(Part 3 adds fields; it removes none). The Dashboard and Calendar pages
settle in a few seconds.

## Non-goals

- No SQL rewrite of metrics (calendar grid, stats, expectancy) and no
  precomputed payloads in the refresher: both risk the admin's numbers
  drifting from the definitions the backtests and the bot use.
- No change to the bot process, the scan, or any existing stored shape.
  The one schema change is the new `fx_daily_rates` table (L1-a).
- No change to how the Calendar buckets a close into a day
  (`pnl_calendar.py:56`, `closed_at[:10]`, the UTC date). The FX day key
  is its own explicit rule (L1-a); aligning the Calendar's bucket to
  Berlin is a separate question, not this spec.
- No second gunicorn worker (in-memory login limiter, SSE broker and
  swallowed-error counter require one).
- No UI change a user can see beyond speed.

## Three plans

The spec spawns **three plans, in order, each ending with its own one
full-suite run and then a deploy** (`document-conventions.md` § One full
suite run): **v205** builds Layer 1; Layer 2 and Part 3 each take the next
free number at their own creation and link back with `**Spec:** v205`.
Each plan measures production after its deploy and records the table in
this spec's `## Results`. A later plan is written only after the earlier
one's measurement, so Layer 2 can be dropped if Layer 1 already meets
0.5 s.

## Design

### Layer 1 — remove the repeated work (plan v205)

Layer 1's tasks run in this order: **L1-d first** (goldens and budgets
pin today's output), then **L1-b and L1-c** (pure refactors, proven
byte-identical by those goldens), then **L1-a last** (the only
intended change in output, proven against an independent reference).

**L1-a. One FX rate per currency pair per day, snapped at 08:00 Berlin
(partner, 2026-11-04).** Today every converted amount reads the pair's
whole daily frame and scans it in Python for its exit date's close
(`fx.py:_close_on_or_before`). That becomes a small stored table of daily
rates and a dict lookup.

- **One rule for "the day".** The FX day of an amount is the **Berlin
  calendar date** of its timestamp: `closed_at` (and each leg's
  `closed_at`) is parsed as an aware ISO stamp, a naive stamp is read as
  UTC (every writer stores `datetime.now(timezone.utc)`,
  `performance.py:174,628,1229`), then converted to `Europe/Berlin`. A live
  amount (open P&L, `dashboard.py:320` `date.today()`, `_day`'s absent-stamp
  fallback, `risk_read_model.py`) uses **Berlin today**. One helper in
  `fx_convert` applies it everywhere; no caller takes `str(stamp)[:10]`.
- **What the table holds.** `fx_daily_rates`: `base` and `account` as
  **major** ISO codes, `day` (Berlin date), `rate`, `bar_date` (the frame
  bar the rate came from), `snapped_at`, `source` (`snap`|`backfill`);
  primary key `(base, account, day)`. It is created by an Alembic revision
  per `schema-evolution.md`, with a working downgrade, and read by a
  repository beside `quote_currency_repo`. Minor units never get rows:
  `fx._major` maps a quote (`GBp`, `ZAc`, `ILA`) to its major code and
  scale **before** the lookup, and the scale multiplies after it. Identity
  is decided on **major** codes: GBp into a GBP account is `x 0.01` with no
  lookup, and GBp into EUR is `GBPEUR x 0.01`. `fx_convert._converted`'s
  exact-code shortcut (`quote == rates.account`) is replaced by that
  major-code test.
- **The day's value: one rule for snap and backfill.** The rate for day D
  is **the last positive close dated strictly before D** in the pair's
  daily frame (index normalised to dates explicitly, whatever its tz).
  That is the newest completed close known at 08:00 Berlin on D. A row is
  written only if that bar's date is within `FALLBACK_DAYS` (7) of D. Past
  that, there is no row and the amount is `fx_missing`, exactly as a >7-day
  gap is today. The partner asked for "one value at 08:00, used all day".
  The latest completed daily close at that moment is chosen over a live
  spot because it is reproducible from the frames: `snap(D) == backfill(D)`
  for the same frame, by construction and by test.
- **Snap.** The refresher's FX job (`swingbot/refresher/quotes.py:132-135`,
  after `refresh_pair_frames`) runs on every cycle. When the Berlin clock
  (`ctx.now` converted, never naive UTC arithmetic) is at or past 08:00, it
  writes the day's row for every pair in use that lacks one. "In use" means
  the majors of every `known` code in the quote-currency store.
  Insert-if-absent, never update: the first value written is the day's
  value. A currency that first appears after 08:00, or a refresher that
  was down at 08:00, gets its row on the next cycle, with the same value
  (the rule depends only on bars before D).
- **Backfill.** One idempotent script fills every past day the frames
  allow (same rule, `source=backfill`, insert-if-absent). It runs once on
  production after the migration, as a step of plan v205's deploy, and
  can be re-run safely.
- **Read.** `fx_convert` reads `(base, account, fx-day)` from a
  process-wide memo of the whole table (a few currencies times a few
  years, a few thousand rows). The memo is keyed on the table's version
  (`count(*), max(snapped_at)`). The key is checked at most once per 60 s,
  so a missing key (before 08:00, refresher down, a pair with no frame)
  never reloads per request. Before today's row exists, day D falls back to
  the nearest earlier row whose `bar_date` is within `FALLBACK_DAYS` of D,
  else `None` with `fx_missing`. **Never 1.0.** An unreadable table is
  `fx_missing`, never a 500.
- **Callers.** Read-side and admin-only: `admin/api_v1/money.py`,
  `admin/api_v1/risk_read_model.py` and the refresher. The bot's sizing,
  balance, kill switch and every backtest keep using quote-currency
  amounts, untouched.

**Figures this moves, on purpose.** Admin amounts converted to the
account currency move from "exit day's close" to "close before the exit
day": realized P&L amounts (Dashboard, Trades, Analytics), the equity
curve in account currency, Calendar day and month totals, and the risk
read model's heat weights, which are now the morning rate all day instead
of moving intraday. **Unaffected:** R multiples, win rate, expectancy,
percent P&L, every bot figure.

**L1-b. Quote codes in one query, short negative memo.**
`fx_convert._Rates` resolves all tickers of a call up front with one
`quote_currency_repo().get_many(keys)` when `fetch=False`. An `unknown`
outcome is memoised in the process for **at most 5 minutes**, not until
`retry_after`, so a code the refresher resolves in the meantime shows up
within 5 minutes. `fetch=True` (refresher off) is unchanged.

**L1-c. Load each store once per request: opt-in, read routes only.**
The seam lives in **core**, so no core module imports admin or flask: a
`contextvars`-based memo in `swingbot/core/infra/read_memo.py`.
`TradeLog._all()`, `PlanStore._all()` and the trade rows
`account._sum_realized_pnl` reads read through it **only while a memo
scope is active**. Outside a scope (the bot, the refresher, scripts,
every write) the memo does nothing, and each call is today's direct call.
The admin activates a scope with an explicit `@read_scope` decorator on
**GET routes only**, listed in the plan: `dashboard`, `trades` list,
`live`, the calendar three and any route the profile shows reading the
same stores. A request context alone never activates it. A test enumerates
every `POST/PATCH/PUT/DELETE` route under `/api/v1` and asserts none
carries the decorator. A behavioural test on each mutating route (write,
then re-read in the same request where the route does so, e.g.
`trade_commands.py:80-86` `_plan_row`) asserts the fresh value. Callers
receive the same objects as today.

**L1-d. Measurement stays in the product.** Every `/api/v1` response gets
a `Server-Timing` header (`total`, `db` time and statement count). The
counting listener (`before/after_cursor_execute`) is installed **only by
the admin app**, through a hook `core/db/engine.get_engine` calls on every
engine it creates, so it survives `reset_engine()`. The bot's and the
refresher's engines never carry it. A request slower than
`ADMIN_SLOW_REQUEST_MS` (default 2000) logs one line: path, total, db
time, statement count. The knob is declared in `swingbot/config.py`'s
schema and hot-reloaded on SIGHUP. Golden-output tests capture today's
JSON of every profiled endpoint from a fixture database, and a budget pins
statement count and `list_all` calls per endpoint, so a regression fails
CI rather than a page.

### Layer 2 — a cross-request snapshot (second plan)

**L2-a. Snapshot.** A per-process snapshot of the **raw** parsed records
(trades, plans and the rows `_sum_realized_pnl` sums) in core, beside the
L1-c memo, which reads through it when `ADMIN_STORE_SNAPSHOT=on`. Raw
records only: anything derived from the clock (days held, open P&L,
`plan_to_dict`'s time-dependent fields, "today") is computed per request
from them, never stored. One rebuild runs at a time under a lock;
concurrent readers wait for it.

**L2-b. Invalidation: the NOTIFY listener first, a version check second.**
`trades` and `plans` already fire statement-level NOTIFY triggers at
commit on channel `trades` (`migrations/versions/p1_003_notify_function.py:18`,
`p2_001_plans_and_starred.py:25`). The admin already runs
`DbEventListener` (`admin/events/db_listener.py:112-144`). Its
`on_notification('trades')` bumps a generation counter that keys the
snapshot. A `resync`, or a listener that is not connected, bypasses the
snapshot until reconnected. Because delivery is asynchronous (a POST
followed at once by a GET can beat it), each request also compares the
stores' version: `PlanRepository.version()` (`repositories/plans.py:44-49`,
already a cache key) and a twin added on the trades repository. A
`count`/`max(updated_at)` key alone is not trusted. `clock_timestamp()` is
statement time, not commit time (`repositories/base.py:89,101`), so a
long transaction can commit under an older stamp. The NOTIFY generation
is what closes that gap. The plan's first task records whether the same
gap affects the two existing callers of `version()`
(`cancel_precision.py:41`, `watchlist_rows.py:71`) and fixes them the
same way. Spurious bumps from `starred_plans` (shared channel) are
harmless.

**L2-c. Mutation safety in production, not only in tests.** Each request
gets **its own shallow copies** of the snapshot's records (about 1.1k
dicts, cheap). The plan audits every consumer for writes into **nested**
values (lists, dicts inside a record) and makes each one copy before
writing, the pattern `fx_convert.to_account_currency` follows. Under
tests the snapshot is frozen deeply (`MappingProxyType` or a frozen
double), so a nested write raises. A test runs every profiled endpoint
twice against the frozen snapshot and asserts identical output. A second
test advances an injected clock across midnight Berlin and asserts the
time-derived fields change.

**L2-d. Kill switch.** `ADMIN_STORE_SNAPSHOT=on|off` (default `on`,
declared in `swingbot/config.py`'s schema, hot-reloaded on SIGHUP). `off`
restores Layer 1 behaviour exactly.

### Part 3 — fewer heavy requests per page (third plan)

**P3-a. `/dashboard` carries `today`.** When the scope is wider than 1D,
the response includes a `today` block with the fields the SPA's
`landToday` consumes, computed from the same loaded trades with mode
`today`. `dashboard.store.ts` lands it from the main response and calls
`loadToday()` **only when the block is absent** (an older backend after a
rollback). The 1D scope is unchanged, and `?mode=today` keeps working.

**P3-b. `/calendar/pnl/day` carries `prev_day` / `next_day`.** These are
the nearest trading days before and after `date` under the same
strategy/horizon filter, across all history (`null` at either end).
`calendar-day.store.ts` uses them and runs `loadEdge` **only when the
fields are absent**. The month grid call stays (the page shows the month
context), and sparklines stay separate on purpose (tiles render before any
CSV is parsed).

## Error handling

- L2: a failing version query, a disconnected listener or a failed rebuild
  means that request loads directly (Layer 1 behaviour), logged at most
  once per minute through the swallowed-error counter. A snapshot the
  checks cannot vouch for is never served.
- FX: a missing rate is `None` with `fx_missing`, never 1.0; a missed
  08:00 snap is written on the next cycle with the same value; an
  unreadable `fx_daily_rates` is `fx_missing`, never a 500.

## Testing

Each change ships its own unit tests in the same commits: backend pytest,
and frontend store specs in the runner the existing `*.store.spec.ts`
use. Cases included:

- An empty book, no trades today, a first or last trading day with no
  neighbour.
- A response without the Part 3 fields (the fallback path).
- An unknown quote code inside and past its 5-minute memo.
- A write between two reads invalidating the snapshot, a listener
  resync, and the kill switch.

FX tests, each against **hand-computed reference rates** on a fixture
frame, never a recomputation through `fx_convert`:

- The "last positive close strictly before D" rule over gaps, NaN and
  non-positive closes, duplicate and unsorted stamps, first and last bar,
  and a gap longer than 7 days.
- `snap(D) == backfill(D)`.
- Insert-if-absent across two refresher cycles on one Berlin day, with an
  injected `ctx.now`.
- The 08:00 Berlin gate on both DST switch days.
- Closes at 21:59, 22:00, 23:59 and 00:30 UTC mapping to the right Berlin
  day.
- GBp→GBP, GBp→EUR and ZAc into each account currency.
- A scale-out trade whose legs close on different days, with per-leg
  rounding then a rounded sum, as today.

Goldens compare every non-money field byte-for-byte; money fields compare
against the hand-computed reference. Complexity stays under 15 per
function. Each plan's last task is its one full-suite run.

## Rollout and rollback

Each plan: implement in its worktree → its full suite → merge →
deploy per `docs/deploy/DEPLOY_HETZNER.md` (v205 adds the migration and
the one-off backfill) → run the read-only production timing script →
record `## Results` → close-out with that plan's bump. Production changes
only by deploying committed `main`, never a live edit.

Rollback, per `DEPLOY_HETZNER.md § Rolling back`:

- **Layer 1:** redeploy the previous image. The `fx_daily_rates` table is
  left in place (the old code never reads it) or removed with the
  revision's downgrade.
- **Layer 2:** `ADMIN_STORE_SNAPSHOT=off` and a SIGHUP, no deploy needed.
- **Part 3:** the SPA tolerates a backend without the new fields, so the
  backend can roll back while browsers hold the new bundle; an old
  bundle ignores the new fields.

## Panel review

Spec review, 2026-11-04, after commit 050f4496. Each finding cites its
role and is recorded as applied or rejected.

- staff-engineer [BLOCKING]: the memo activated by any request context
  also covers write routes, and their in-request re-reads would see stale
  data; an import test cannot guard it -- **applied** (L1-c: opt-in
  `@read_scope` on GET routes only, a route-enumeration test, a
  write-then-reread behavioural test).
- staff-engineer [BLOCKING]: `read_context.py` in admin, read by core
  modules, would add a core -> admin/flask import to bot paths --
  **applied** (L1-c/L2-a: a contextvar memo in `core/infra`; admin only
  activates it).
- staff-engineer [ADVISORY]: `count/max(updated_at)` is unsound under
  statement-time stamps and late commits -- **applied** (L2-b: NOTIFY
  generation as primary, version as a second check, the existing
  `version()` callers reviewed).
- staff-engineer [ADVISORY]: reuse the existing NOTIFY triggers and
  `DbEventListener` -- **applied** (L2-b).
- staff-engineer [ADVISORY]: `_sum_realized_pnl` bypasses the snapshot,
  so the 0.5 s Goal cannot be met -- **applied** (L1-c/L2-a cover its
  rows).
- staff-engineer [ADVISORY]: reuse `PlanRepository.version()` and add a
  trades twin -- **applied** (L2-b).
- staff-engineer [ADVISORY]: mid-plan deploys would ship code that never
  passed the full suite -- **applied** (three plans, each with its own
  full run before its deploy).
- staff-engineer [ADVISORY]: no rollback named; the SPA must tolerate
  missing fields -- **applied** (Rollout and rollback; P3 fallbacks).
- staff-engineer [ADVISORY]: `ADMIN_SLOW_REQUEST_MS` missing from the
  config schema -- **applied** (L1-d).
- staff-engineer [ADVISORY]: freezing only in tests leaves production
  exposed -- **applied** (L2-c: per-request shallow copies plus a nested
  audit).
- staff-engineer [ADVISORY]: the frame-order and duplicate-stamp
  equivalence for the old lookup -- **applied** in a changed form: L1-a
  replaces the lookup, and the backfill tests cover duplicate and
  unsorted stamps.
- staff-engineer [ADVISORY]: the engine listener must survive
  `reset_engine()` and stay out of the bot -- **applied** (L1-d: an
  admin-installed hook in `get_engine`).
- quant-engineer [BLOCKING]: the FX day key is the UTC date, not Berlin
  -- **applied** (L1-a: one Berlin-date rule for stamps, legs and
  "today"; UTC boundary tests).
- quant-engineer [BLOCKING]: snap (live spot) and backfill (last close)
  are different quantities -- **applied** (L1-a: both store the last
  positive close strictly before D; `snap == backfill` test; `bar_date`
  recorded).
- quant-engineer [BLOCKING]: minor units and identity are underspecified
  -- **applied** (L1-a: major-code rows only, scale after lookup,
  identity on majors).
- quant-engineer [BLOCKING]: an unbounded forward-fill would hide
  `fx_missing` -- **applied** (L1-a: a row only when the bar is within
  7 days; a >7-day gap test).
- quant-engineer [BLOCKING]: the memo reloads per request when today's
  key is missing, and has no version -- **applied** (L1-a: version-keyed,
  checked at most every 60 s).
- quant-engineer [ADVISORY]: goldens cannot prove the refactors with L1-a
  in the same layer, and recomputing through `fx_convert` is tautological
  -- **applied** (L1 order d → b, c → a; hand-computed references;
  scale-out legs).
- quant-engineer [ADVISORY]: name the admin figures that move --
  **applied** ("Figures this moves, on purpose").
- quant-engineer [ADVISORY]: the snapshot must hold raw records only;
  time drift test -- **applied** (L2-a, L2-c midnight test).
- quant-engineer [ADVISORY]: the unknown-code memo until `retry_after`
  is too long -- **applied** (L1-b: 5-minute cap).
- quant-engineer [ADVISORY]: the DST gate needs an injected clock, two
  cycles a day, and a definition of "in use" -- **applied** (L1-a Snap;
  Testing).

### Pre-close-out panel (2026-11-05, staff-engineer, quant-engineer)

Over the plan's diff (`891d860b..92e35a03`, the `2fc79125` merge fix, `27568e0a`).

- quant-engineer BLOCKING: `fx_snap._is_current` could freeze a non-final D-1
  bar into the insert-if-absent table, so snap(D) != backfill(D) -- **applied**
  (`4afb9a67`: a row is written only from a bar known final, in snap and
  backfill; a weekday file mtime is not accepted as proof, because a failed
  ranged fetch also touches the file). Re-reviewed: no BLOCKING. Production's
  2026-11-05 row was read-only checked: equal to the final 2026-11-04 close.
- staff-engineer: CURRENCY_SYMBOL change needs a backfill re-run; rollback order
  and downgrade scope unwritten -- **applied** (`fe7997b8`, DEPLOY_HETZNER.md).
- staff-engineer: bump level vs the manual backfill step -- partner chose
  `bot patch`; the spec's `ui patch` prediction is amended to none (backend only).
- staff-engineer: `snap` pulls each pair's whole day history every cycle
  (`fx_snap.py:97`, `market_refresh.py:115`); no repair path for a wrong
  permanent row; `fx_daily.lookup` swallows every failure at DEBUG
  (`fx_daily.py:137`) -- **carried**: a single-row EXISTS or a per-day flag, a
  documented repair statement, and a rate-limited WARNING belong in a follow-up.
- staff-engineer: Layer 2 must profile the application-side time of `dashboard`
  and `dashboard_today` (about 2.1-3.0 s with 0.4-0.6 s of database) before
  building the snapshot machinery -- **carried** to the Layer 2 plan.
- quant-engineer: `_day_rate` returns the nearest earlier row when D's own row
  is absent, so a past amount can shift once D's row is written; `snap` never
  fills a skipped weekday (documented: run the backfill); `_stale_logged` is
  never pruned; `_final_through` counts a junk-close later bar as proof -- **carried**
  (the skipped-weekday note is **applied** in the runbook).

## Results

Filled by each plan after its production measurement.

### Before v205 (script)

Measured 2026-11-04 ~23:15 Berlin with `scripts/ops/admin_endpoint_timing.py --month 2026-11 --date 2026-11-03 --runs 2`
inside the production `admin` container (piped over stdin), script at commit 4f1f8230.

| Endpoint | Path | Run | Status | ms | Bytes | db ms | Statements |
|---|---|---|---|---|---|---|---|
| dashboard | `/api/v1/dashboard` | 1 | 200 | 4422.2 | 1430 | - | - |
| dashboard_today | `/api/v1/dashboard?mode=today` | 1 | 200 | 4007.9 | 1429 | - | - |
| trades | `/api/v1/trades` | 1 | 200 | 5149.4 | 43190 | - | - |
| trades_open | `/api/v1/trades?status=open` | 1 | 200 | 4763.2 | 28085 | - | - |
| live | `/api/v1/live` | 1 | 200 | 1381.8 | 2040 | - | - |
| calendar_month | `/api/v1/calendar/pnl?month=2026-11` | 1 | 200 | 4116.4 | 2332 | - | - |
| calendar_day | `/api/v1/calendar/pnl/day?date=2026-11-03` | 1 | 200 | 4131.4 | 7384 | - | - |
| calendar_sparklines | `/api/v1/calendar/pnl/day/sparklines?date=2026-11-03` | 1 | 200 | 948.1 | 2939 | - | - |
| dashboard | `/api/v1/dashboard` | 2 | 200 | 4114.2 | 1430 | - | - |
| dashboard_today | `/api/v1/dashboard?mode=today` | 2 | 200 | 3812.9 | 1429 | - | - |
| trades | `/api/v1/trades` | 2 | 200 | 4907.0 | 43189 | - | - |
| trades_open | `/api/v1/trades?status=open` | 2 | 200 | 4885.4 | 28076 | - | - |
| live | `/api/v1/live` | 2 | 200 | 1401.7 | 2040 | - | - |
| calendar_month | `/api/v1/calendar/pnl?month=2026-11` | 2 | 200 | 4197.7 | 2332 | - | - |
| calendar_day | `/api/v1/calendar/pnl/day?date=2026-11-03` | 2 | 200 | 4191.5 | 7384 | - | - |
| calendar_sparklines | `/api/v1/calendar/pnl/day/sparklines?date=2026-11-03` | 2 | 200 | 780.6 | 2939 | - | - |

### After v205 (script)

Measured 2026-11-05 15:14 Berlin with `scripts/ops/admin_endpoint_timing.py --month 2026-11 --date 2026-11-03 --runs 2`
inside the `admin` container (image `sha-2fc791252ee1`), after the backfill (dry run planned=8362,
written=8362, re-run written=0; `fx_daily_rates`: 1 pair (USD/EUR), 8363 rows: 8362 backfill + 1 snap).

| Endpoint | Path | Run | Status | ms | Bytes | db ms | Statements |
|---|---|---|---|---|---|---|---|
| dashboard | `/api/v1/dashboard` | 1 | 200 | 3021.6 | 1386 | 621.1 | 23 |
| dashboard_today | `/api/v1/dashboard?mode=today` | 1 | 200 | 2121.7 | 1385 | 444.5 | 8 |
| trades | `/api/v1/trades` | 1 | 200 | 964.9 | 43016 | 274.9 | 6 |
| trades_open | `/api/v1/trades?status=open` | 1 | 200 | 1115.5 | 24539 | 227.5 | 5 |
| live | `/api/v1/live` | 1 | 200 | 1283.0 | 2022 | 404.5 | 6 |
| calendar_month | `/api/v1/calendar/pnl?month=2026-11` | 1 | 200 | 810.3 | 2420 | 160.0 | 2 |
| calendar_day | `/api/v1/calendar/pnl/day?date=2026-11-03` | 1 | 200 | 825.2 | 7389 | 160.2 | 2 |
| calendar_sparklines | `/api/v1/calendar/pnl/day/sparklines?date=2026-11-03` | 1 | 200 | 726.5 | 3233 | 142.0 | 2 |
| dashboard | `/api/v1/dashboard` | 2 | 200 | 2368.4 | 1386 | 454.5 | 8 |
| dashboard_today | `/api/v1/dashboard?mode=today` | 2 | 200 | 2191.8 | 1385 | 447.0 | 8 |
| trades | `/api/v1/trades` | 2 | 200 | 1139.8 | 43020 | 276.7 | 5 |
| trades_open | `/api/v1/trades?status=open` | 2 | 200 | 989.1 | 24560 | 222.9 | 5 |
| live | `/api/v1/live` | 2 | 200 | 1555.6 | 2022 | 438.9 | 6 |
| calendar_month | `/api/v1/calendar/pnl?month=2026-11` | 2 | 200 | 776.6 | 2420 | 240.6 | 2 |
| calendar_day | `/api/v1/calendar/pnl/day?date=2026-11-03` | 2 | 200 | 752.0 | 7389 | 139.2 | 2 |
| calendar_sparklines | `/api/v1/calendar/pnl/day/sparklines?date=2026-11-03` | 2 | 200 | 686.3 | 3233 | 181.4 | 2 |

**Verdict against the Layer 1 Goal (every endpoint under 1.5 s):** not met.
Slowest row: `dashboard` run 1 at 3021.6 ms (before: 4422.2 ms). Rows at or over 1500 ms,
which is where the Layer 2 plan starts: `dashboard` run 1 (3021.6 ms, db 621.1 ms, 23
statements), `dashboard` run 2 (2368.4 ms, db 454.5 ms, 8 statements), `dashboard_today`
run 1 (2121.7 ms, db 444.5 ms, 8 statements), `dashboard_today` run 2 (2191.8 ms, db
447.0 ms, 8 statements), `live` run 2 (1555.6 ms, db 438.9 ms, 6 statements). Database
time is a minor share of these rows, so most of the remainder is application-side.
On purpose (L1-a): converted money amounts now use the close before the exit's Berlin day.
