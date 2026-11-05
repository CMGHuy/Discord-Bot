# Admin read performance, Layer 1: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md), § "Layer 1 — remove the repeated work (plan v205)", "Error handling", "Testing", "Rollout and rollback". Layer 2 and Part 3 are later plans with their own numbers; nothing here builds them.

**Goal:**

The partner sees the Dashboard take over a minute to show trades and the
Calendar take very long to show anything. Production measured on 2026-11-04
shows every profiled admin endpoint at 3–12 s for payloads of 1–43 KB. The
database is not the cause: `select 1` takes 0.5 ms and the whole `trades` table
loads in 334 ms. The time goes on Python doing the same work again. Every FX
conversion scans a currency pair's whole price history (4.1 s of the 7.1 s in
`/calendar/pnl`). One request loads and parses the same trades and plans up to
8 times. Unknown quote currencies are looked up one ticker at a time. One
gunicorn worker serves the page's 4–5 parallel requests on one GIL, so the
waits add up.

Layer 1 removes that repeated work and changes no definitions. Once it ships,
four things are true. Every `/api/v1` response carries a `Server-Timing`
header (total, db time, statement count), and requests slower than
`ADMIN_SLOW_REQUEST_MS` log one line. Each request loads each store once,
through a `contextvars` memo in `swingbot/core/infra/read_memo.py` that
only the admin's GET read routes switch on. A route opts in with
`@read_scope`. Quote codes resolve in one batched query, and an `unknown`
answer is remembered for 5 minutes. FX rates come from a small
`fx_daily_rates` table holding one rate per pair per Berlin day. A rate is
"the last positive close strictly before D". The refresher writes the row
at 08:00 Berlin, a one-off backfill fills past days, and readers look the
rate up in a dict instead of scanning a frame.

The bot, the scan, sizing, the kill switch, every backtest and every stored
record are left alone. Layer 1 changes only the admin's read path, the
refresher's FX job and one new table. On purpose, converted money amounts in
the admin move from "exit day's close" to "the close before the exit's Berlin
day". This applies to the realized P&L amounts, the equity curve in the
account currency, Calendar totals and risk heat weights. R, win rate,
expectancy and percent P&L do not move.

Success is measured on production with the timing script V205-1 adds. It is
run once before this plan and once after its deploy, and both tables go into
the spec's `## Results`. The target is every profiled endpoint **under 1.5 s**
(spec Goal). The JSON must be byte-identical to today, proven by goldens frozen
in V205-4. Only the money fields that L1-a deliberately moves are exempt, and
those are checked against hand-computed references.

**Architecture:** L1-d first. V205-1..V205-5 add the timing script, an engine
hook in `core/db/engine.py` and an admin SQL tally (`swingbot/admin/request_timing.py`),
the `Server-Timing` header and slow log, then goldens and budgets that pin
today's output and cost. L1-c (V205-6..V205-9) adds the core read memo,
routes `TradeLog._all`, `PlanStore._all` and `account._sum_realized_pnl`
through it, audits nested writes, and switches it on with `@read_scope` on
six GET views. L1-b (V205-10) batches quote codes. L1-a (V205-11..V205-16)
adds the table and its repository, the rate rule and table memo
(`core/marketdata/fx_daily.py`), snap and backfill (`core/marketdata/fx_snap.py`,
a refresher step, an ops script), then rewires `fx.fx_rate` and `fx_convert`
onto Berlin days. V205-17 is the one full-suite run. V205-18 deploys, measures
and records the results.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy Core (engine events) + Alembic (Postgres), pandas, `contextvars`, `zoneinfo`, pytest.

## Global Constraints

- **Bump: bot patch** (backend only; ui none for this plan) is applied at `/close-out`, never by a task. No task edits `VERSION.json` or `version_history.json`.
- Implement in a worktree under `.claude/worktrees/` named per `document-lifecycle.md`. Every command uses absolute paths or `git -C <wt>`; never `cd`. Stage explicit paths only, never `git add -A`. Commit after each task in scoped commits.
- **Order is a contract (spec § Layer 1):** goldens and budgets (V205-4, V205-5) are committed before any code they cover changes. L1-b and L1-c (V205-7..V205-10) are pure refactors and must pass the V205-4 goldens **unchanged**. L1-a's output change lands only in V205-15 and V205-16, after V205-9 and V205-10 are merged into the branch.
- **Goldens are frozen.** `tests/admin_perf/golden/*.json` is written once by V205-4 from today's code and never regenerated or edited. Money fields are compared through `tests/admin_perf/money_reference.py:EXPECTED_MONEY`. Only V205-15 and V205-16 edit it. Each value they change is a hand-computed number from `golden_book.FX_CLOSES`, with the arithmetic in a comment, and is never recomputed through `fx_convert`. A failing golden means the code is fixed, never the golden.
- **The memo is opt-in and read-only.** Outside `read_memo.scope()` (the bot, the refresher, scripts, every write) each store call behaves exactly as today. Inside a scope, `_all()`-backed reads return **per-call shallow copies** (`dict(r)` per record) of the memoised records, so callers keep today's ownership of fresh dicts. A call that passes `conn` (a transaction) always bypasses the memo. The scope is entered and reset in `try/finally`, so 16 gunicorn threads never share one. No `POST/PUT/PATCH/DELETE` view carries `@read_scope`.
- **No core → admin/flask import.** `swingbot/core/infra/read_memo.py`, `fx_daily.py` and `fx_snap.py` import nothing from `swingbot.admin` or `flask`. The SQL counting listener is attached only by the admin (`request_timing.install`) through `engine.add_engine_hook`. The bot and the refresher never call it, so their engines never carry it. The hook survives `reset_engine()`.
- **FX day rule (one helper):** `fx_convert.fx_day(stamp)`. An aware ISO stamp converts to `Europe/Berlin`. A naive stamp is UTC first. A date-only string or a `date` is that date, unshifted. `None`/empty is Berlin today. No caller takes `str(stamp)[:10]`. A live amount uses `fx_convert.berlin_today()`.
- **Rate rule (one function, snap and backfill alike):** `fx_daily.rate_before(frame, day)` returns the last positive close dated **strictly before** `day`, the frame index normalised to dates explicitly. Duplicate and unsorted stamps are allowed, and NaN and non-positive closes are skipped. It returns `None` unless `day - bar_date <= FALLBACK_DAYS` (7). Rows hold **major** codes only. `fx._major` maps a minor quote first, and the scale multiplies after the lookup. Identity is decided on majors. **Never 1.0 for a missing rate:** `None` plus `fx_missing`. An unreadable table is `fx_missing`, never a 500.
- **Deploy window:** `deploy.sh` runs `alembic upgrade head` *after* `up --wait`, so admin and refresher run briefly without `fx_daily_rates`. Every read of the table degrades to a miss, and `quotes.fx_snap_step` catches its own exception and tags it `swallowed(log, "ops.refresher.fx_snap", ...)` (`quotes` cannot call `loop._guard`, since `loop` imports `quotes`); it leaves `ctx.report.error` unset so a missed snap never marks the refresher as failing. Neither may raise into a request or crash the cycle.
- **One revision `v205_001`.** Its `down_revision` is what `python -m alembic -c <wt>/alembic.ini heads` prints at run time (`v200_001` expected; v204's unimplemented `v204_001` may land first). It is registered with `schema.register` plus `PROMOTION_REASONS`, not in `events.TABLE_CHANNELS`, and has a working downgrade. `tests/db/test_v200_discord_issued_at.py`'s fixed-head assertion is relaxed in the same commit.
- **Complexity < 15** for every function written or changed (`python <wt>/scripts/dev/complexity_gate.py`). `trades.list_trades` (E32), `TradeLog.get_trades` (C18) and `queries._plan_rows` (C18) get decorator lines or one-line call-site swaps only. New logic goes into new helpers.
- **Tests:** add no test file under `tests/admin/` (suite at 1192/1200); edit files there only where an FX assertion deliberately changes (V205-15/16). New admin endpoint tests live in `tests/admin_perf/`, registered by V205-2 as suite `admin-perf` in `tests/suites.toml` (same commit). Others: `tests/infra/` (read memo), `tests/db/` (engine hook, migration, repo), `tests/marketdata/` (rate rule, memo, snap), `tests/refresher/` (snap step), `tests/scripts/` (ops scripts), `tests/test_config_v205_keys.py` (config).
- **Module state in tests:** every new process-wide memo has a reset seam (`read_memo` needs none, being contextvar-scoped; `fx._unknown_until`, `fx_daily.reset_memo()`) and reads time through a seam: `fx._clock()` / `fx_daily._clock()` (monotonic), never a patched stdlib `time`.
- **Swallowed errors:** every new `except` calls `swallowed(log, "<area>.<function>", exc, ...)` with a tag unique repo-wide (`tests/infra/test_swallowed_ratchet.py`).
- Per-task verification is the narrow run `python <wt>/scripts/dev/testrun.py file <test>`. A task whose tests hit the database runs `/replicate-prod-db` first, into the shared `swing-db` container (port 56789). The one full-suite run is V205-17.
- **Production** is touched only by V205-1 (read-only timing, before) and V205-18 (deploying committed `main`, running the committed backfill script and the timing script). Connect only through `bash scripts/ops/ssh-hetzner.sh`. No live edit, and no `.env` edit on the VM. Credentials come from the container environment and are never printed.

## Parallelisation

At most 2 implementers at once (`CLAUDE.md`). Sequential edges and their reasons:

- **V205-1 ∥ V205-2.** Disjoint files (`scripts/ops/`, `tests/scripts/` against `core/db/engine.py`, `swingbot/admin/request_timing.py`). V205-1 parses the header format fixed below from literal strings, so it does not need V205-3's code.
- **V205-2 → V205-3:** V205-3 extends `request_timing.py` and consumes `SqlTally`/`start_request`/`end_request`.
- **V205-2 → V205-4:** V205-2 creates `tests/admin_perf/` (its `conftest.py`) and registers suite `admin-perf`. **V205-3 ∥ V205-4:** disjoint files (`request_timing.py`, `app.py`, `config.py`, `.env.example` against new test-only files).
- **V205-4 → V205-4b:** 4b records goldens through 4's harness and appends to its test file. Everywhere below, "V205-4" as a predecessor means V205-4 and V205-4b both done.
- **V205-3, V205-4 → V205-5:** budgets read statement counts from V205-3's tally and seed V205-4's `golden_book`.
- **V205-6 ∥ V205-3, V205-4, V205-5:** a new core file and `tests/infra/` only.
- **V205-4, V205-5, V205-6 → V205-7 → V205-8 → V205-9.** V205-7 must run against frozen goldens and budgets and consumes `read_memo`. V205-8 audits V205-7's copies. V205-9 switches the memo on in production routes, so it lands only after the audit. V205-9 also lowers V205-5's budgets.
- **V205-10 ∥ V205-6..V205-9** (after V205-4): disjoint files (`fx.py`, `fx_convert.py`, `tests/marketdata/` against the stores, admin views, `tests/infra/`). Budgets assert `<=`, so whichever of V205-9/V205-10 lands second still passes.
- **V205-11 ∥ V205-6..V205-10:** additive schema plus repository; no output change. It touches `schema.py`, `market_refresh.py`, the new revision and `tests/db/` only.
- **V205-11 → V205-12 → V205-13 → V205-14.** `fx_daily` reads the repository. `fx_snap.snap` builds on `fx_daily.rate_before`. `fx_snap.backfill` extends `fx_snap.py`, and its `snap == backfill` test needs `snap`.
- **V205-12 → V205-12b** (12b appends the memo to the module 12 creates). V205-13 needs only `rate_before`, so it starts after V205-12; V205-15 calls `lookup`/`reset_memo`, so it needs V205-12b.
- **V205-9, V205-10, V205-12b → V205-15 → V205-16.** L1-a's output change lands only after both refactors pass the goldens. V205-15 edits `fx.py` after V205-10. V205-16 edits `fx_convert.py` after V205-10 and V205-15, and both edit `money_reference.py`.
- **V205-14 ∥ V205-15** (disjoint: `fx_snap.py`, the script, `DEPLOY_HETZNER.md` against `fx.py`, `tests/marketdata/test_fx*.py`); both precede V205-16.
- **V205-17** (full suite) follows every task through V205-16. **V205-18** runs only after the controller merges the branch into `main` and it is deployed. It is the post-merge deploy step, not a code task.

## Task ledger

| ID | Title | Part | Model | Files | Cross-task contract |
|---|---|---|---|---|---|
| V205-1 | Read-only production timing script; baseline run | 1 | sonnet | Create `scripts/ops/admin_endpoint_timing.py`, `tests/scripts/test_admin_endpoint_timing.py`; modify `docs/superpowers/specs/2026-11-04-v205-admin-read-performance-design.md` (`## Results`: "Before v205 (script)" table) | See "Timing script" |
| V205-2 | Engine hook in `get_engine`; admin SQL tally; `admin-perf` suite | 1 | sonnet | Modify `swingbot/core/db/engine.py`, `tests/suites.toml`; create `swingbot/admin/request_timing.py`, `tests/db/test_engine_hooks.py`, `tests/admin_perf/__init__.py`, `tests/admin_perf/conftest.py`, `tests/admin_perf/test_sql_tally.py` | See "Engine hook" and "Request timing" |
| V205-3 | `Server-Timing` on every `/api/v1` response; slow-request log; `ADMIN_SLOW_REQUEST_MS` | 1 | sonnet | Modify `swingbot/admin/request_timing.py`, `swingbot/admin/app.py`, `swingbot/config.py`, `.env.example`; create `tests/admin_perf/test_server_timing.py`, `tests/test_config_v205_keys.py` | See "Request timing", "Config field" |
| V205-4 | Golden book: seed, frozen clock, masking; golden endpoint test harness | 1 | opus | Create `tests/admin_perf/golden_book.py`, `tests/admin_perf/test_golden_endpoints.py`; modify `tests/admin_perf/conftest.py` | See "Golden book" |
| V205-4b | Money references, golden recorder and frozen `golden/*.json` | 1b | opus | Create `tests/admin_perf/money_reference.py`, `tests/admin_perf/record_golden.py`, `tests/admin_perf/golden/<name>.json` (one per `ENDPOINTS` key); append tests to `tests/admin_perf/test_golden_endpoints.py` | See "Golden book" |
| V205-5 | Per-endpoint budgets: statement count and `list_all` calls | 2 | sonnet | Create `tests/admin_perf/test_budgets.py` | `BUDGETS: dict[str, tuple[int, int]]` (endpoint name → max statements, max `Repository.list_all` calls), today's measured values; asserts `<=` |
| V205-6 | Core read memo (`contextvars`) | 2 | sonnet | Create `swingbot/core/infra/read_memo.py`, `tests/infra/test_read_memo.py`; modify `docs/claude/architecture.md` (module-map row) | See "Read memo" |
| V205-7 | Stores read through the memo: `TradeLog._all`, `PlanStore._all`, `_sum_realized_pnl` | 2 | opus | Modify `swingbot/core/tracking/performance.py`, `swingbot/core/planning/plan_store.py`, `swingbot/core/planning/account.py`; create `tests/infra/test_read_memo_stores.py` | Keys `read_memo.TRADE_ROWS`, `TRADES`, `PLANS`; `conn` given → bypass |
| V205-8 | Nested-write audit of GET-path mutators; deep copies where needed | 2 | opus | Modify only the mutators the audit convicts (candidates `swingbot/admin/api_v1/trades.py` `_attach_current_prices`, `_attach_unrealized_pnl`, `_strip_internal_fields`; `swingbot/admin/queries.py`; `swingbot/admin/api_v1/dashboard.py`); create `tests/admin_perf/test_memo_isolation.py` | Uses `read_memo.peek(key)`; records the audit verdict per mutator in the test module docstring |
| V205-9 | `@read_scope` on six GET views; mutating-route guard; write-then-reread tests; budgets lowered | 3 | sonnet | Create `swingbot/admin/api_v1/read_scope.py`, `tests/admin_perf/test_read_scope_routes.py`; modify `swingbot/admin/api_v1/dashboard.py`, `trades.py`, `live.py`, `calendar.py`, `tests/admin_perf/test_budgets.py` | See "Read scope decorator" |
| V205-10 | L1-b: quote codes in one query; 5-minute negative memo | 3 | sonnet | Modify `swingbot/core/marketdata/fx.py`, `swingbot/core/marketdata/fx_convert.py`; create `tests/marketdata/test_fx_quote_batch.py`; one-line `_unknown_until` reset in the `_isolated` fixtures of `tests/marketdata/test_fx.py`, `tests/marketdata/test_fx_persisted.py` | See "Quote batch" |
| V205-11 | Alembic `v205_001`: `fx_daily_rates`; repository; head test relaxed | 3 | opus | Create `swingbot/core/db/migrations/versions/v205_001_fx_daily_rates.py`, `tests/db/test_v205_fx_daily_rates.py`; modify `swingbot/core/db/schema.py`, `swingbot/core/db/repositories/market_refresh.py`, `tests/db/test_v200_discord_issued_at.py`, `tests/db/test_unknown_field_round_trip.py` (`NOT_REPOSITORY_BACKED` entry) | See "Table" and "Repository" |
| V205-12 | Rate rule `rate_before` (new module `fx_daily`) | 3 | opus | Create `swingbot/core/marketdata/fx_daily.py`, `tests/marketdata/test_fx_daily.py`; modify `docs/claude/architecture.md` (module-map row) | `FALLBACK_DAYS`, `rate_before`, `_clock` (see "fx_daily") |
| V205-12b | The version-keyed `fx_daily_rates` memo: `lookup`, `reset_memo` | 3b | opus | Modify `swingbot/core/marketdata/fx_daily.py`; create `tests/marketdata/test_fx_daily_lookup.py` | `VERSION_CHECK_S = 60`, `lookup(base, account, day) -> float \| None`, `reset_memo()` (see "fx_daily") |
| V205-13 | Snap at 08:00 Berlin: `fx_snap.snap`, refresher step | 4 | opus | Create `swingbot/core/marketdata/fx_snap.py`, `tests/marketdata/test_fx_snap.py`, `tests/refresher/test_fx_snap_step.py`; modify `swingbot/refresher/quotes.py`, `swingbot/refresher/loop.py` | See "fx_snap" |
| V205-14 | Backfill: `fx_snap.backfill`, ops script, deploy runbook step | 4 | sonnet | Modify `swingbot/core/marketdata/fx_snap.py` (also the snap freshness guard), `tests/marketdata/test_fx_snap.py`, `docs/deploy/DEPLOY_HETZNER.md`; create `scripts/ops/backfill_fx_daily_rates.py`, `tests/scripts/test_backfill_fx_daily_rates.py` | See "fx_snap" (backfill), "Backfill script" |
| V205-15 | `fx.fx_rate` reads the table; strictly-before rule replaces `_close_on_or_before`; FX tests updated | 4 | opus | Modify `swingbot/core/marketdata/fx.py`, `tests/marketdata/test_fx.py`, `tests/marketdata/test_fx_persisted.py`, `tests/admin_perf/money_reference.py`, `tests/admin_perf/golden_book.py`, `tests/admin_perf/conftest.py` (`golden_seed.set_fx` seeds `fx_daily_rates`, `fx_daily.reset_memo()` on teardown) (seed `fx_daily_rates` rows) | See "fx_rate after V205-15" |
| V205-16 | `fx_convert` on Berlin days; major-code identity; Berlin-today callers; admin FX tests updated | 5 | opus | Modify `swingbot/core/marketdata/fx_convert.py`, `swingbot/admin/api_v1/dashboard.py` (line ~320), `swingbot/admin/api_v1/trades.py` (line ~1341), `swingbot/admin/api_v1/risk_read_model.py` (docstring), `swingbot/admin/api_v1/risk.py` (`_distribution_metrics` passes `fx_convert.fx_day(checked)`), `tests/admin/test_api_v1_money.py`, `tests/admin/test_api_v1_risk.py`, `tests/admin/test_risk_read_model.py`, `tests/admin/test_trades_golden_rows.py`, `tests/analytics/test_cancel_replay.py` (each only where an assertion moves), `tests/admin_perf/money_reference.py`, `tests/admin_perf/golden_book.py` (`CLOCK_MODULES` gains `fx_convert`); create `tests/admin_perf/test_fx_day.py` (suite `admin-perf`: market-data has ~5 tests of headroom left) | See "fx_convert after V205-16" |
| V205-17 | Full suite | 5 | sonnet | Fix observed defects in the owning task's files only | `python <wt>/scripts/dev/testrun.py full`: `0 failed`, `0 xfailed`; `complexity_gate.py` clean; `plan_lint.py` clean |
| V205-18 | Deploy, migrate, backfill, measure; spec `## Results` | 5 | sonnet | Modify `docs/superpowers/specs/2026-11-04-v205-admin-read-performance-design.md` (`## Results`: "After v205" table and verdict) | Uses V205-1's script and V205-14's script unchanged |

The ledger has 20 rows, the cap (V205-4 → 4b and V205-12 → 12b split for the size caps). No further split is possible: a task that outgrows 20 KB moves to a follow-up plan.

**`swallowed()` tags** in every task must match `tests/infra/test_swallowed_ratchet.py:45` (`^(scan|marketdata|earnings|runstate|ops)\.`); part 1 uses `ops.db_engine.apply_hooks` and `ops.request_timing.end_request`. A `db.` or `admin.` tag fails that test.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-04-v205-admin-read-performance_1-measurement-and-goldens.md` | V205-1 … V205-4 | Timing script and baseline, engine hook and SQL tally, Server-Timing and slow log, golden book harness |
| 1b | `2026-11-04-v205-admin-read-performance_1b-goldens.md` | V205-4b | Money references, golden recorder, frozen golden JSON |
| 2 | `2026-11-04-v205-admin-read-performance_2-read-memo.md` | V205-5 … V205-8 | Budgets, the core read memo, stores through it, nested-write audit |
| 3 | `2026-11-04-v205-admin-read-performance_3-scope-quotes-and-table.md` | V205-9 … V205-12 | `@read_scope` on GET views, quote batching, the `fx_daily_rates` table and repo, rate rule and table memo |
| 3b | `2026-11-04-v205-admin-read-performance_3b-fx-daily-memo.md` | V205-12b | The `fx_daily_rates` memo |
| 4 | `2026-11-04-v205-admin-read-performance_4-snap-backfill-fx-rate.md` | V205-13 … V205-15 | 08:00 snap and refresher step, backfill script and runbook, `fx_rate` on the table |
| 5 | `2026-11-04-v205-admin-read-performance_5-berlin-day-and-ship.md` | V205-16 … V205-18 | `fx_convert` Berlin days and callers, full suite, deploy and results |

## Cross-task contracts

Existing names used unchanged (verified in the brief): `fx.FALLBACK_DAYS`, `MINOR_UNITS`, `_major`, `_clock`, `_frames`, `_quote_codes`, `_pair_frame(pair, *, refresh=True)`, `_disk_frame`, `refresh_pair_frames`, `quote_currency_code(ticker, *, fetch=True)`, `account_currency_code()`; `fx_convert.rate`, `quote_code`, `_Rates`, `_at`, `_converted`, `to_account_currency`, `convert_amount`, `MONEY_FIELDS`, `missing_count`; `quote_currency_repo()` and `QuoteCurrencyRepository.get_many(symbols, *, conn=None)`; `Repository.list_all(*, conn=None, where=None, order_by=None, limit=None)`; `engine.get_engine()`, `reset_engine()`; `api_v1.auth.require_auth`; `loop.STEPS`, `CycleContext.now` (aware UTC); `swallowed(log, tag, exc, ...)`.

### Timing script (V205-1; `scripts/ops/admin_endpoint_timing.py`)

- `endpoints(month: str, day: str) -> dict[str, str]`, a name-to-path map. Its keys and order are **the endpoint names every task uses**: `dashboard` `/api/v1/dashboard`, `dashboard_today` `/api/v1/dashboard?mode=today`, `trades` `/api/v1/trades`, `trades_open` `/api/v1/trades?status=open`, `live` `/api/v1/live`, `calendar_month` `/api/v1/calendar/pnl?month=<month>`, `calendar_day` `/api/v1/calendar/pnl/day?date=<day>`, `calendar_sparklines` `/api/v1/calendar/pnl/day/sparklines?date=<day>`. The writer checks the sparklines route's query parameters in `calendar.py` and uses those.
- `parse_server_timing(header: str | None) -> dict[str, dict]`: `{"total": {"dur": float}, "db": {"dur": float, "statements": int}}`. A missing or foreign header gives `{}`, so the baseline before V205-3 still prints.
- `time_endpoints(client, headers: dict, paths: dict[str, str], *, runs: int = 2) -> list[dict]`: rows `{name, path, run, status, ms, bytes, db_ms, statements}` (the last two `None` when absent).
- `format_table(rows) -> str` (markdown) and `main(argv: list[str] | None = None) -> int` with `--month YYYY-MM` / `--date YYYY-MM-DD` (defaults: the Berlin month and Berlin date now) and `--runs N`.
- It runs inside the admin container, either as `docker compose exec -T admin python - [args] < scripts/ops/admin_endpoint_timing.py` or, once deployed, as `python scripts/ops/admin_endpoint_timing.py`. It uses `swingbot.admin.app.app.test_client()` with HTTP Basic auth built from `os.environ["ADMIN_USERNAME"]`/`["ADMIN_PASSWORD"]`. Credentials are never printed, and a test asserts the password is absent from stdout. It makes GET requests only. If importing `swingbot.admin.app` starts background threads that write, the writer switches to `urllib` against `http://127.0.0.1:$ADMIN_PORT` and records why in the module docstring.

### Engine hook (V205-2; `swingbot/core/db/engine.py`)

- `add_engine_hook(hook: Callable[[Engine], None]) -> None`. It appends once: the same hook object is never added twice. If `_engine` already exists, the hook is applied to it at once.
- `get_engine()` calls every registered hook on each engine it creates, so a hook survives `reset_engine()`.
- `_ENGINE_HOOKS: list[Callable[[Engine], None]]` is module state, and tests restore it with `monkeypatch.setattr(engine, "_ENGINE_HOOKS", [])`.

### Request timing (V205-2, V205-3; `swingbot/admin/request_timing.py`)

- `@dataclass class SqlTally: statements: int = 0; db_s: float = 0.0`.
- `start_request() -> contextvars.Token` (fresh `SqlTally` in contextvar `_TALLY`); `end_request(token) -> SqlTally` (resets the var, returns the tally); `current() -> SqlTally | None`.
- `install_sql_counter() -> None`: `engine.add_engine_hook(_attach)`. `_attach` registers `before_cursor_execute`/`after_cursor_execute` listeners (`sqlalchemy.event.listen`) that add to `current()` when it is not `None`, and do nothing otherwise. Idempotent.
- V205-3: `install(app: Flask) -> None` calls `install_sql_counter()` and registers app-level `before_request`/`after_request` hooks that act only when `request.path.startswith("/api/v1")`. `app.py` calls `request_timing.install(app)` once. `server_timing(total_s: float, tally: SqlTally) -> str` returns **exactly** `total;dur=<total_ms:.1f>, db;dur=<db_ms:.1f>;desc="<n> statements"`. Slow log: `log.warning("slow request %s total=%.0fms db=%.0fms statements=%d", path, ...)` when `total_ms > float(config.ADMIN_SLOW_REQUEST_MS)`, read per request (hot reload via `config.auto_reload_if_changed`).

### Config field (V205-3; `swingbot/config.py`)

`ADMIN_SLOW_REQUEST_MS`: section `"Admin UI"`, `type="number"`, `default="2000"`, `min=100`, `max=60000`, `step=100`, hot-reloadable (the `Field` default), with a help text naming v205. `.env.example` gains `ADMIN_SLOW_REQUEST_MS=2000` in the Admin UI block. `tests/test_config_v205_keys.py` mirrors `tests/test_config_v201_keys.py`.

### Golden book (V205-4; `tests/admin_perf/`)

- `golden_book.FROZEN_NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)`. `MONTH = "2026-11"`, `DAY = "2026-11-03"`.
- `golden_book.CLOCK_MODULES: tuple[str, ...]` lists the modules whose module-level `datetime`/`date`/`dt` names the `frozen_clock` fixture replaces with frozen subclasses. It starts with every module in the profiled endpoints' call path that reads the wall clock; V205-16 appends `swingbot.core.marketdata.fx_convert`.
- `golden_book.ENDPOINTS: dict[str, str]` = `admin_endpoint_timing.endpoints(MONTH, DAY)` (imported, never retyped).
- `golden_book.FX_CLOSES: dict[str, dict[str, float]]`: hand-written `USDEUR=X` daily closes, including gaps, a non-positive close and a close on a USD trade's exit day. `golden_book.QUOTES: dict[str, str]`: one USD ticker, the rest EUR.
- Fixtures in `tests/admin_perf/conftest.py` (V205-4 extends V205-2's file): `frozen_clock`; `golden_seed` (seeds plans, trades and account through `tests.store_seed.seed_store`, pins quotes and frames); `logged_in` (session login as `tests/admin/test_api_v1_dashboard.py:96-104`).
- `golden_book.mask(payload) -> payload` replaces the values of `VOLATILE_KEYS` (only what is still nondeterministic under `frozen_clock`, each one named with a reason) and of every money pointer in `money_reference.EXPECTED_MONEY` with `"<masked>"`.
- `money_reference.EXPECTED_MONEY: dict[str, dict[str, float | None]]` maps endpoint name to JSON pointer (`"/trades/0/realized_pnl_amount"` style) to the hand-computed value.
- `record_golden.py` (`python -m tests.admin_perf.record_golden`) writes `golden/<name>.json` (sorted keys, indent 1). `test_golden_endpoints.py` is parametrised over `ENDPOINTS`. It asserts `mask(live) == mask(golden)` and that each `EXPECTED_MONEY` pointer resolves to its value (`pytest.approx(abs=0.005)`).

### Read memo (V205-6; `swingbot/core/infra/read_memo.py`, leaf module: stdlib only)

- `TRADE_ROWS = "trade_rows"`, `TRADES = "trades"`, `PLANS = "plans"`.
- `scope() -> ContextManager[None]`: a `contextlib.contextmanager` that sets a fresh `dict` in contextvar `_MEMO` and resets its token in `finally`. Nested scopes reuse the outer memo.
- `active() -> bool`.
- `records(key: str, loader: Callable[[], list[dict]]) -> list[dict]`: outside a scope, `loader()` unchanged. Inside, the first call stores `loader()`, and every call returns `[dict(r) for r in stored]`.
- `mapping(key: str, loader: Callable[[], dict[str, dict]]) -> dict[str, dict]`: the same, returning `{k: dict(v) for k, v in stored.items()}`.
- `peek(key: str) -> object | None` is a test seam: the stored value or `None`.

### Read scope decorator (V205-9; `swingbot/admin/api_v1/read_scope.py`)

- `READ_SCOPE_ATTR = "__read_scope__"`; `read_scope(view)` returns a `functools.wraps` wrapper running `view` inside `read_memo.scope()`, with `setattr(wrapper, READ_SCOPE_ATTR, True)`. It is placed **under** `@require_auth`, whose `wraps` copies the attribute outward.
- Exactly these six views carry it: `dashboard.dashboard`, `trades.list_trades`, `live.get_live`, `calendar.calendar_pnl`, `calendar.calendar_pnl_day`, `calendar.calendar_pnl_day_sparklines`.

### Quote batch (V205-10; `swingbot/core/marketdata/fx.py`, `fx_convert.py`)

- `fx.UNKNOWN_MEMO_S = 300`; `fx._unknown_until: dict[str, float]` (monotonic deadline via `_clock()`; tests reset it like `_frames`).
- `fx.stored_codes(keys: Iterable[str]) -> dict[str, str | None]` makes one `quote_currency_repo().get_many(...)` for the keys in neither memo. It memoises `known` codes in `_quote_codes` for the process, and anything else in `_unknown_until` until `_clock() + UNKNOWN_MEMO_S`. A repo error gives all-`None`, swallowed, and no memo entry. `_stored_code(key)` becomes `stored_codes([key]).get(key)`.
- `fx_convert._Rates(account, fetch=True, tickers=())`: when `fetch` is `False`, it resolves `tickers` up front with one `fx.stored_codes(...)`. `to_account_currency` passes its rows' tickers. `fetch=True` keeps today's one-argument `fx.quote_currency_code(ticker)` call (test seams depend on it).

### Table (V205-11; revision `v205_001`)

`fx_daily_rates`: `base Text`, `account Text`, `day Date` (composite PK in that order), `rate` (the float type `schema.py` already uses for prices; `NOT NULL`), `bar_date Date NOT NULL`, `snapped_at TIMESTAMPTZ NOT NULL`, `source Text NOT NULL` (`snap`/`backfill`), plus `standard_columns()`. No secondary index. `PROMOTION_REASONS["fx_daily_rates"]` gives one reason per promoted column. The downgrade drops the table.

### Repository (V205-11; `swingbot/core/db/repositories/market_refresh.py`)

- `class FxDailyRateRepository(Repository)` is built as `super().__init__(fx_daily_rates, key="day")`. Every method below writes its own SQL.
- `insert_if_absent(rows: Iterable[dict], *, conn=None) -> int`: `pg_insert(...).on_conflict_do_nothing(index_elements=["base", "account", "day"])`, returning the rows written. Each row is `{base, account, day: date, rate: float, bar_date: date, snapped_at: datetime, source: str}`.
- `all_rates(*, conn=None) -> list[dict]`: `{base, account, day, rate, bar_date}` ordered by `(base, account, day)`.
- `version(*, conn=None) -> tuple[int, datetime | None]`: `(count(*), max(snapped_at))`.
- `days_present(base: str, account: str, *, conn=None) -> set[date]`.
- `QuoteCurrencyRepository.known_codes(*, conn=None) -> set[str]`: distinct `code` where `outcome = 'known'`.
- Accessor `fx_daily_rate_repo() -> FxDailyRateRepository` (via `_singleton`).

### fx_daily (V205-12; `swingbot/core/marketdata/fx_daily.py`; imports nothing from `fx`)

- `FALLBACK_DAYS = 7` (V205-15 makes `fx.FALLBACK_DAYS` this same object by import). `VERSION_CHECK_S = 60`.
- `rate_before(frame: pd.DataFrame | None, day: date) -> tuple[float, date] | None` follows the rule in Global Constraints and returns `(close, bar_date)`. It is vectorised: it never builds a Python list over the whole index per call.
- `lookup(base: str, account: str, day: date) -> float | None` takes majors and no scale. It reads the whole table into `{(base, account): sorted [(day, rate, bar_date)]}` and checks `fx_daily_rate_repo().version()` at most once per `VERSION_CHECK_S` (`_clock()`), reloading only when the version changed. An exact row wins. Otherwise it takes the nearest earlier row whose `bar_date` is within `FALLBACK_DAYS` of `day`, else `None`. A read error gives `None` for that call, swallowed as `marketdata.fx_daily.lookup`, and the memo is kept.
- `reset_memo() -> None`; `_clock() -> float` (monotonic seam).

### fx_snap (V205-13, V205-14; `swingbot/core/marketdata/fx_snap.py`)

- `SNAP_HOUR = 8`. `pairs_in_use() -> list[tuple[str, str]]`: sorted `(major(code), account_major)` for each `quote_currency_repo().known_codes()` whose major differs from `fx._major(fx.account_currency_code())[0]`.
- `snap(now: datetime) -> int` (V205-13). `now` is aware; it is converted with `astimezone(ZoneInfo("Europe/Berlin"))`, never naive arithmetic. It returns 0 before 08:00 Berlin. Otherwise, for each pair lacking a row for the Berlin day `D`, it computes `fx_daily.rate_before(fx._pair_frame(f"{base}{account}=X", refresh=False), D)` and writes via `insert_if_absent` with `source="snap"` and `snapped_at=now`. It returns rows written. No rate gives no row. **Freshness guard:** a pair whose frame's last bar is before `_last_weekday_before(D)` writes no row this cycle; a later cycle writes it (added by V205-14, which amends `snap`).
- `backfill(*, start: date | None = None, end: date | None = None, now: datetime | None = None) -> int` (V205-14) uses the same rule with `source="backfill"`. It covers every day from the first frame bar's next day through `end` (default: the Berlin date of `now`), restricted to days where `rate_before` gives a value. It is insert-if-absent and idempotent. V205-14 also produces `INSERT_CHUNK = 1000` (Postgres's 65,535-parameter limit) and `planned_rows(*, start=None, end=None, now=None) -> list[dict]` (the dry-run source); only the script uses them.
- Refresher (V205-13): `quotes.fx_snap_step(ctx: CycleContext) -> None` calls `fx_snap.snap(ctx.now)` and is appended to `loop.STEPS` after `quotes.fx_step`, so it runs every cycle even when `fx_step` returns early.

### Backfill script (V205-14; `scripts/ops/backfill_fx_daily_rates.py`)

`main(argv: list[str] | None = None) -> int` takes `--start`, `--end` and `--dry-run` (prints counts only), calls `fx_snap.backfill`, and prints `written=<n>`. It follows the `scripts/ops/backfill_issued_at_discord.py` style. On production it runs as `docker compose exec -T admin python scripts/ops/backfill_fx_daily_rates.py`.

### fx_rate after V205-15 (`swingbot/core/marketdata/fx.py`)

`fx_rate(from_code, to_code, on, *, refresh=True)` keeps its signature (`fx_convert.rate` and test seams call it). It takes majors and scale as today. Equal majors return the scale. Otherwise it calls `fx_daily.lookup(src, dst, day)`. On a miss with `refresh=True` (refresher off, the kill-switch path) it falls back to `fx_daily.rate_before(_pair_frame(pair, refresh=True), day)` and writes nothing. On a miss with `refresh=False` it returns `None`. The result is multiplied by the scale. `_close_on_or_before` is deleted.

### fx_convert after V205-16 (`swingbot/core/marketdata/fx_convert.py`)

- `FX_DAY_TZ = ZoneInfo("Europe/Berlin")`. `berlin_today() -> date` returns `datetime.now(FX_DAY_TZ).date()` (module-level `datetime`, so `frozen_clock` reaches it). `fx_day(stamp) -> date` follows the rule in Global Constraints, accepting `str`, `datetime`, `date` or `None`, and replaces `_day`.
- `_converted` identity is `fx._major(quote)[0] == fx._major(rates.account)[0]`, giving `_at(amount, quote, day, rates)` with the scale only (no lookup). Per-leg rounding and then a rounded sum are kept as today.
- `dashboard.py` (~320) and `trades.py` (~1341) pass `fx_convert.berlin_today()` instead of `date.today()`. `risk_read_model` receives Berlin today from its caller(s); V205-16 names each caller it changes.
