# v205 — Admin read performance: Dashboard and Calendar in seconds, not a minute

**Version:** ui 1.38.0 · bot 2.16.1
**Bump:** bot patch, ui patch
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
**byte-identical JSON** to today for the same database state (Part 3 adds
fields; it removes none). The Dashboard and Calendar pages settle in a few
seconds.

## Non-goals

- No SQL rewrite of metrics (calendar grid, stats, expectancy) and no
  precomputed payloads in the refresher: both risk the admin's numbers
  drifting from the definitions the backtests and the bot use.
- No change to the bot process, the scan, or any stored shape. No schema
  migration.
- No second gunicorn worker (in-memory login limiter, SSE broker and
  swallowed-error counter require one).
- No UI change a user can see beyond speed.

## Design

### Layer 1 — remove the repeated work (no staleness risk)

**L1-a. FX lookup in O(log n).** `fx._close_on_or_before` keeps its
contract (last positive close within `[day - FALLBACK_DAYS, day]`, None
otherwise) but reads from a per-frame lookup built once: a sorted
`numpy` array of `date` ordinals and the matching positive closes,
memoised beside the frame in `_frames` (rebuilt whenever the frame is).
A lookup is one `searchsorted` and a bounds check. A test pins equality
with the old implementation over every day of a real pair frame,
including gaps, non-positive and NaN closes, days before the first bar and
after the last.

**L1-b. Quote codes resolved in one query and negatives memoised.**
`fx_convert._Rates` resolves all tickers of a call up front with one
`quote_currency_repo().get_many(keys)` when `fetch=False`. An `unknown`
outcome is memoised in the process until its stored `retry_after` passes
(the refresher's own back-off), so it is no longer re-read per request.
`fetch=True` behaviour (refresher off) is unchanged.

**L1-c. Load each store once per request.** A small request-scoped read
context (`swingbot/admin/read_context.py`) memoises, on `flask.g`:
the trade list (`TradeLog._all()`), the plan records (`PlanStore._all()`),
`plan_to_dict` rows, and `load_account_config()`. The admin routes and
helpers on the profiled paths (`dashboard.py`, `trades.py:build_rows`,
`admin/queries.py`, `calendar.py`, `pnl_calendar.load_rows`,
`tracking/equity.load_plans_by_id`) read through it when a request context
exists and fall back to today's direct call otherwise, so the bot, the
refresher and every non-request caller are untouched. Callers receive the
same objects they receive today; the context lives one request only, so a
write inside the request (a POST) must not read a stale memo -- write
routes do not use it, and a test asserts no write route imports it.

**L1-d. Measurement stays in the product.** Every `/api/v1` response gets
a `Server-Timing` header (`total`, `db` time and statement count via a
SQLAlchemy `before/after_cursor_execute` listener scoped to the request),
and a request slower than `ADMIN_SLOW_REQUEST_MS` (default 2000) logs one
line with path, total, db time and statement count. A test budget pins the
statement count and the number of `list_all` calls per profiled endpoint
against a fixture database, so a regression fails CI rather than a page.

### Layer 2 — a cross-request snapshot of the parsed stores

**L2-a. Snapshot cache.** `swingbot/admin/store_snapshot.py` keeps, per
process, the parsed trade list and plan records (and `plan_to_dict` rows)
with a version key. Each request asks for the version with one query per
store: `select count(*), max(updated_at) from trades` (likewise `plans`),
~0.5 ms. A changed key rebuilds that store's snapshot under a lock (one
rebuild, concurrent readers wait for it rather than rebuilding in
parallel). The read context of L1-c reads through the snapshot.

**L2-b. Version key soundness.** The plan's first Layer 2 task verifies
that every write path to `trades` and `plans` advances `updated_at`
(repository `upsert`/`update` paths, the bot's writers, the importer, any
raw SQL). Any path that does not is fixed to set it, or the key falls back
to a cheaper-than-parse alternative chosen in that task (e.g. a
statement-level trigger bumping a sequence). The cache never trusts a key
the task could not prove.

**L2-c. Mutation safety.** Snapshot records are shared across requests,
so a caller mutating one would corrupt every later response. The plan
audits every consumer reached from the admin read context and either
(a) proves it read-only, or (b) changes it to copy before writing (the
pattern `fx_convert.to_account_currency` already follows). The snapshot
hands out records wrapped so that, under tests, any mutation raises
(`types.MappingProxyType` or a frozen-dict test double over the fixture
DB); production hands out the plain dicts. A test runs every profiled
endpoint twice against the frozen snapshot and asserts identical output.

**L2-d. Kill switch.** `ADMIN_STORE_SNAPSHOT=on|off` (default `on`,
hot-reloaded via SIGHUP like every `.env` key, added to
`swingbot/config.py`'s schema). `off` restores Layer 1 behaviour exactly.

### Part 3 — fewer heavy requests per page

**P3-a. `/dashboard` carries `today`.** When the scope is wider than 1D,
the response includes a `today` block with the fields the SPA's
`landToday` consumes today, computed from the already-loaded trades with
mode `today`. `dashboard.store.ts` drops the separate `loadToday()`
request and lands `today` from the main response; the 1D scope is
unchanged. The old `?mode=today` call keeps working (no API removal).

**P3-b. `/calendar/pnl/day` carries `prev_day` / `next_day`.** The
nearest trading day before and after `date` under the same
strategy/horizon filter, across all history (`null` at either end).
`calendar-day.store.ts` drops `loadEdge` and its two possible
`/calendar/pnl` calls. The month grid call stays (the page shows the
month context), and sparklines stay separate on purpose (tiles render
before any CSV is parsed).

## Error handling

- A failing version query in L2 falls back to a fresh Layer 1 load for
  that request and logs once per minute (swallowed-error counter), never
  serving a snapshot it cannot vouch for.
- A failed snapshot rebuild leaves the previous snapshot unused (not
  served) and the request loads directly.
- FX lookup failures keep today's semantics: a missing rate is `None` and
  `fx_missing`, never 1.0.

## Testing

Each part ships its own unit tests in the same commits (backend pytest,
frontend store specs in the runner the existing `*.store.spec.ts` use), including empty and
edge cases: an empty book, no trades today, a first/last trading day with
no neighbour, a pair frame with gaps and non-positive closes, an unknown
quote code past and before its retry time, a write between two reads
invalidating the snapshot, and the kill switch. Golden-output tests
capture today's JSON of every profiled endpoint from a fixture database
before Layer 1 and assert it unchanged after each layer. Complexity stays
under 15 per function. The plan's last task is the one full-suite run.

After Layer 1 and again after Layer 2 the plan re-runs the production
timing script (read-only, from the `admin` container) and records the
table in this spec's results section; the Goal's thresholds are the
acceptance bar.

## Rollout

Layer 1 -> merge, deploy, measure on production -> Layer 2 -> merge,
deploy, measure -> Part 3 (backend first, then the stores) -> close-out.
Each step is its own set of scoped commits. The intermediate deploys are
`bot` patch releases cut by the plan's checkpoint tasks (bump resolved from
`VERSION.json` at that moment, history regenerated); close-out resolves
the final `bot` and `ui` patch. Production is changed only by a deploy of
committed `main`, never a live edit.
