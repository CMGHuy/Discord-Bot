# Instant admin page loads implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [Instant admin page loads](../specs/2026-10-29-v201-instant-admin-page-loads.md)

**Goal:**

Every main admin page (Dashboard, Trades, Trade detail, Watchlist, Risk,
Analytics, Calendar) takes 8 s to over 30 s to show data that is already in
Postgres. Measured on production on 2026-10-29, `/dashboard` took 8–22 s and
fired three times on login, `/trades` 19 s, and Risk, Analytics and Calendar
timed out. Under that pile-up even `/system/scan` took 75 s. The time goes to
market-data and FX network calls made inside request threads: one gunicorn
worker, 16 threads, one process-wide yfinance lock. A blocking route resolver
then hides each page's skeleton until the slowest call returns, and a reload
forces the slowest path (`X-Swingbot-Fresh` maps to the 0 s `ADMIN_FRESH`
window).

Once this ships, no page-load request makes a market or FX network call.
A new `refresher` compose service, a separate process with its own yfinance
lock, owns all admin market fetching. It runs as a dedicated tier-5
`ADMIN_REFRESH` asker inside the shared v171 quote cache. Each cycle it
refreshes quotes for open trades, live plans, the watchlist and the tape
(about 30 s in regular hours, 5 min extended, 30 min closed). It also
resolves and stores quote-currency codes (including "unknown" answers),
refreshes FX pair files, and stores snapshots of the heavy pages (risk,
the analytics snapshot behind the dashboard sparkline, and whichever
Analytics and Calendar default views measure slow). Before each fetch it
marks the keys in flight and NOTIFYs a thin `market` SSE event, then NOTIFYs
again when the values land (so a spinner shows for its own refreshes too). Request handlers read only Postgres and those stored values.
Every market-derived value comes with `as_of` and `refreshing`, and every
total also carries its oldest input, `stale_count` and `missing_count`, so a
missing input is never summed as zero. The SPA stops blocking routes. On the
`market` event a live-values store calls `GET /market/updates?since=` and
patches values in place. One `sb-market-value` cell draws the value, its
age (or "last close · Fri 16:00 ET" when the market is closed) and a
spinner while a refresh is in flight. A stalled refresher (heartbeat older
than 3× cadence) shows a banner. A visible Refresh control on Dashboard,
Trades, Trade detail and Risk is the only way a request can ask for a fetch,
and it does so by queueing one.

Left alone: Discord alerts, the scan pipeline, plan building, backtests, the
OHLCV/daily-bar caches the scan and backtests read (the refresher writes only
the shared quote cache, its own tables and the FX pair files the admin
already refreshes today), `analytics_snapshot.json` and every Discord reader
of it, page layouts, and every stop-monitor/scan quote window.
`ADMIN_REFRESHER=off` brings back today's request-time paths exactly.

Success is the spec's Verification. After deploy, the same Playwright timing
probe shows first data visible in 2 s or less on all seven pages, cold and
warm and during a scan, with every page-load call at 2 s or less and
`/system/scan` at 0.5 s or less. A label check finds an as-of or "last close"
label on every displayed price, total, P&L and risk figure. Both are recorded
in `docs/superpowers/results/`. Tests pin snapshot/request payload parity,
loud failure on a missing bar cache, incomplete totals and the kill switch.

**Architecture:** Three layers share one contract module,
`swingbot/core/marketdata/shared/admin_refresh.py`, which holds the kill
switch, cadences, staleness thresholds, mark keys, queue priorities and
snapshot keys. (1) **Refresher**, the new process package `swingbot/refresher/`
(`python -m swingbot.refresher`). It holds a Postgres advisory lock so only
one instance runs. Each loop works out the session state, builds the symbol
set from Postgres, drains the refresh queue, runs one batched quote call
through `data.refresh_quote_batch` (Alpaca first, a capped yfinance fallback
that is skipped during a scan), runs the FX job, runs due snapshot builders
from `swingbot/core/analytics/admin_snapshots.py`, beats
`refresher_heartbeat`, and NOTIFYs `market` when its marks are set and again when something changed.
(2) **Request path:** `swingbot/admin/market_values.py` is the only door page
handlers use for market values. It is a never-fetch read plus
marks/queue/snapshot reads, and it falls back to today's functions when the
refresher is off. (3) **SPA:** non-blocking routes, a `LiveValuesStore` on
the existing event stream, and the `sb-market-value` cell. Five new tables
come in one Alembic revision. The risk metrics code moves out of the Flask
blueprint into `swingbot/core/analytics/risk_payload.py`, so the refresher
and the request path call the same functions.

**Tech stack:** Python 3.11, Flask, SQLAlchemy/Alembic (Postgres), psycopg
LISTEN/NOTIFY, pandas; Angular (signals, zoneless) + Vitest; Docker Compose;
Playwright (production probe only).

## Global Constraints

- `Bump: ui patch, bot patch` — applied at `/close-out`, not by any task. No `VERSION.json` edit in a task. If V201-11 finds a deploy needs a manual server step, it stops and reports it so the controller re-grades `Bump:` (`working-conventions.md` § The three levels).
- Implement in a worktree under `.claude/worktrees/` (name per `document-lifecycle.md`). Every command uses absolute paths or `git -C <wt>`; stage explicit paths only, never `git add -A`.
- **No request thread makes a market or FX network call when `admin_refresh.refresher_on()` is true.** The Refresh control is no exception: it *enqueues* and returns. Forbidden in page-load handlers when on: `freshness.page_quotes`, `data.get_quote_batch`, `data.get_current_price*`, `data.prefetch_prices`, `data.get_daily_data_batch`, `fx.quote_currency_code(..., fetch=True)`, `fx._refreshed_frame`, `yf_safe.download`, `snapshots.refresh_snapshot`, `collect_portfolio_state`, `freshness.warm_quotes_background`.
- `refresher_on()` is `config.ADMIN_REFRESHER == "on" and config.MARKETDATA_LAYER == "on"`. Otherwise every request path runs **today's code unchanged**. Production runs `MARKETDATA_LAYER=on`.
- `ADMIN_REFRESHER` defaults to `"on"` so a normal deploy needs no `.env` edit. `tests/admin/conftest.py` pins it `"off"` (autouse) so the existing admin suite keeps covering the fallback path. New tests set it `"on"` explicitly.
- The refresher never calls `yf_safe.set_default_lock_timeout`, never runs in the bot or admin container, and never writes a daily/intraday OHLCV file except the FX pair files `fx` already refreshes. A test pins this (V201-6).
- Refresher quote fetches use `Asker.ADMIN_REFRESH` (tier 5, 50 % budget reserve). Stop-monitor, requote and scan windows are untouched.
- A missing input is never zero. Totals carry `missing_count` and `incomplete`; a missing quote, bar file or FX code is listed, never dropped.
- Snapshots record `inputs` exactly as the "Snapshot inputs" contract below. `stale_inputs` is true when the oldest bar date is before the last completed NYSE session.
- New tables are Postgres-only, created by the one Alembic revision `v201_001`, registered with `schema.register` and `PROMOTION_REASONS`. None goes in `events.TABLE_CHANNELS`: the refresher calls `notify.publish("market")` itself, at most twice per cycle (marks set, values landed).
- Every function written or changed stays below cyclomatic complexity 15 (`python scripts/dev/complexity_gate.py`). `list_trades` (34) and `build_open_trade_views` (17) are legacy and only shrink, by extraction.
- Tests: `tests/admin/` is at about 1141 of 1200, so **add no test file there**. Edit existing ones only where behaviour changes. Backend refresher/request-path tests go in `tests/refresher/` and `tests/admin_market/`, both in a new `[suites.refresher]` (V201-1). Config keys go in `tests/test_config_v201_keys.py` (suite `config`), migration/repo tests in `tests/db/` (suite `storage`), FX/kinds/budget tests in `tests/marketdata/` (suite `market-data`). SPA tests are co-located `*.spec.ts`.
- Per-task verification is the narrow run `python <wt>/scripts/dev/testrun.py file <test>` (SPA: `npx --prefix <wt>/frontend vitest run <spec>`). The one full-suite run is V201-19. A task that runs DB tests runs `/replicate-prod-db` first into the shared `swing-db` container.
- UI: every new element is checked at mobile, tablet and desktop widths (`ui-design.md`). Age label and spinner wrap under the value on narrow widths and never widen a table column.
- Production is touched only by V201-20 (read-only Playwright probe after the partner's normal deploy). No task deploys or edits the VM `.env`.

## Review Focus

- **The refresher dies in regular hours.** Within 3× cadence the shell shows "prices paused, refresher not running" and every age label takes the stalled tone. On a Saturday with a live heartbeat nothing warns; prices read "last close · Fri 16:00 ET". Pinned in V201-10 (`test_health_reports_refresher_stalled_after_three_cadences`) and V201-16 (`marketAgeLabel` specs `stalled feed wins over closed` and `closed market reads last close, not stale`).
- **A ticker added a moment ago.** The row shows `null` price with `price_refreshing: true` and one queue row. When the refresher's fetch for it fails, the mark clears with an error, and the cell shows the error style, not an endless spinner. Pinned in V201-7 (`test_never_seen_symbol_is_null_refreshing_and_enqueued_once`), V201-6 (`test_failed_symbol_clears_mark_with_error`) and V201-16 (`error stops the spinner`).
- **The provider raises for a whole cycle.** Last values are kept, ages grow, the heartbeat still beats with `last_error`, and no mark outlives `ADMIN_REFRESH_MARK_TIMEOUT_S`. Pinned in V201-6 (`test_provider_raises_keeps_last_values_and_still_beats`) and V201-3 (`test_marks_expire_after_timeout`).
- **Two refresher containers overlap during a compose recreate.** The second cannot take the advisory lock, fetches nothing and retries. Pinned in V201-5 (`test_second_instance_does_not_fetch`).
- **A position quoted in a currency the provider answered "unknown".** It counts in `missing_count`, the total is `incomplete`, it is never summed as zero, and the code is retried only after `ADMIN_REFRESH_FX_UNKNOWN_RETRY_S`. Pinned in V201-4 (`test_unknown_code_is_persisted_and_not_retried_before_backoff`), V201-7 (`test_total_with_unknown_currency_counts_missing_not_zero`) and V201-8 (`test_dashboard_kpis_incomplete_when_a_position_is_unpriced`).

## Parallelisation

At most 2 implementers at once (`CLAUDE.md`). Sequential edges and why:

- **V201-1 first.** Every backend task imports `admin_refresh`, the config fields or `Asker.ADMIN_REFRESH`, and V201-1 registers the `refresher` suite that the test dirs need.
- **V201-2 → V201-3:** the repositories read the tables of revision `v201_001`.
- **V201-3 → V201-4, V201-5, V201-7:** each consumes a repository from `market_refresh.py`.
- **V201-4 → V201-6:** the quote cycle calls `fx.refresh_quote_codes` / `fx.refresh_pair_frames`.
- **V201-5 → V201-6:** the quote cycle plugs into `loop.run_cycle`; both edit `swingbot/refresher/loop.py`.
- **V201-5 → V201-11:** the compose `command:` names `swingbot.refresher`.
- **V201-7 → V201-8, V201-9, V201-10, V201-12:** they consume `market_values`; V201-12 also edits `swingbot/admin/freshness.py` after V201-7 has.
- **V201-8 ∥ V201-9:** disjoint files (`admin/dashboard.py`, `api_v1/dashboard.py`, `api_v1/market.py`, `watchlist_rows.py` vs `api_v1/trades.py`); both may run together.
- **V201-12 → V201-13 → V201-14:** V201-13's risk builder calls `risk_payload.metrics_and_correlation`; V201-14 registers builders in V201-13's `admin_snapshots.BUILDERS` and edits `swingbot/refresher/snapshot_job.py` after it. V201-13 also needs V201-6 (it edits `loop.py`).
- **SPA (V201-15..18)** depends on no backend task at test time (fakes stand in; payload shapes are fixed below), so V201-15 and V201-16 may run beside any backend task. V201-15 ∥ V201-16 (disjoint: `routing/`, `stores/dashboard|tape|market-index`, `workspaces/*/*.routes.ts` vs `api/`, `ui/`, `shell/`, `stores/live-values.store.ts`). **V201-15, V201-16 → V201-17, V201-18.** V201-17 ∥ V201-18 (disjoint workspaces; neither edits `models.ts`, which V201-16 owns).
- **V201-19** (full suite) follows every task through V201-18. **V201-20** runs only after the branch is merged and the partner has deployed; it is a post-deploy check, not a code task.

## Task ledger

| ID | Title | Part | Model | Files | Cross-task contract |
|---|---|---|---|---|---|
| V201-1 | Config fields, `Asker.ADMIN_REFRESH`, session state, contract module, `refresher` suite | 1 | opus | Modify `swingbot/config.py`, `swingbot/core/marketdata/shared/kinds.py`, `swingbot/core/market/session.py`, `tests/suites.toml`, `tests/marketdata/test_shared_kinds.py`, `tests/marketdata/test_shared_budget.py`; create `swingbot/core/marketdata/shared/admin_refresh.py`, `tests/test_config_v201_keys.py`, `tests/refresher/__init__.py`, `tests/refresher/test_admin_refresh_contract.py`, `tests/admin_market/__init__.py` | Fields + defaults: see "Config fields". `Asker.ADMIN_REFRESH = "admin_refresh"`, priority 5, `_QUOTE_ATTR` → `"ADMIN_REFRESH_REGULAR_S"`. `session.SESSION_REGULAR/EXTENDED/CLOSED = "regular"/"extended"/"closed"`; `session.session_state(now: datetime \| None = None) -> str`; `session.last_regular_close(now=None) -> datetime` (UTC-aware). `admin_refresh`: see "Contract module". `[suites.refresher]` paths `["tests/refresher/", "tests/admin_market/"]` |
| V201-2 | Alembic revision `v201_001`: five tables + `market_cache` index | 1 | opus | Create `swingbot/core/db/migrations/versions/v201_001_admin_refresher.py`, `tests/db/test_v201_tables.py`; modify `swingbot/core/db/schema.py` | `revision = "v201_001"`, `down_revision` = the head at run time (`v173_002` today; `v200_001` if v200 merged first). Tables and columns: see "Tables". Index `market_cache_kind_updated_idx` on `market_cache(kind, updated_at)`. None in `TABLE_CHANNELS` |
| V201-3 | Repositories for snapshots, quote currencies, queue, marks, heartbeat | 1 | sonnet | Create `swingbot/core/db/repositories/market_refresh.py`, `tests/db/test_market_refresh_repos.py`; modify `swingbot/core/db/repositories/market_shared.py`, `tests/db/test_market_shared_repo.py` (or the existing market_shared repo test file) | Classes and accessors: see "Repositories". `MarketSharedRepository.changed_since(kind: str, since: datetime, *, conn) -> list[dict]` (`key, symbol, fetched_at, doc, updated_at`) |
| V201-4 | FX: persisted quote-currency codes, never-fetch request reads, conversion moved to core | 1 | opus | Modify `swingbot/core/marketdata/fx.py`, `swingbot/admin/api_v1/money.py`, `swingbot/admin/api_v1/risk_read_model.py`, `tests/marketdata/test_fx.py`; create `swingbot/core/marketdata/fx_convert.py`, `tests/marketdata/test_fx_persisted.py` | `fx.quote_currency_code(ticker, *, fetch: bool = True) -> str \| None` (`fetch=False`: memo → `quote_currencies` row → `None`, never network); `fx.fx_rate(from_code, to_code, on, *, refresh: bool = True)` (`refresh=False` never calls `_refreshed_frame`); `fx.refresh_quote_codes(symbols, *, now=None) -> dict[str, str \| None]`; `fx.refresh_pair_frames(codes: Iterable[str]) -> list[str]`. `fx_convert.to_account_currency(rows, *, account=None, fetch=True)`, `fx_convert.convert_amount(amount, ticker, on, *, account=None, fetch=True) -> tuple[float \| None, bool]`, `fx_convert.missing_count(rows) -> int`; `money.py` re-exports them and passes `fetch=not admin_refresh.refresher_on()` |
| V201-5 | Refresher process: advisory lock, cadence loop, symbol set, heartbeat, queue prune, entry point | 1 | opus | Create `swingbot/refresher/__init__.py`, `__main__.py`, `lock.py`, `symbols.py`, `loop.py`; `tests/refresher/test_loop.py`, `tests/refresher/test_lock.py`, `tests/refresher/test_symbols.py` | `lock.ADVISORY_LOCK_KEY = 201001`; `lock.single_instance() -> ContextManager[bool]`. `symbols.SymbolSet(quotes: tuple[str, ...], index: tuple[str, ...])`; `symbols.symbol_set() -> SymbolSet`. `loop.CycleReport` (dataclass: `session, cadence_s, quotes_ok: tuple, quotes_missed: tuple, fallback_used: int, snapshots_written: tuple, error: str \| None, changed: bool`); `loop.run_cycle(now=None) -> CycleReport`; `loop.run_forever(stop: threading.Event) -> None`; `loop.STEPS: list[Callable[[CycleContext], None]]` hook list later tasks append to; `loop.CycleContext` (dataclass: `now, session, symbols: SymbolSet, queued_quotes: list[str], queued_snapshots: list[str], scan_running: bool, report: CycleReport`). `__main__.main() -> int` |
| V201-6 | Quote cycle: batched fetch, capped fallback, marks, queue drain, FX job, `market` NOTIFY | 1b | opus | Modify `swingbot/core/marketdata/data.py`, `swingbot/core/marketdata/shared/layer.py`, `swingbot/core/db/notify.py`, `swingbot/core/db/events.py` (comment only), `swingbot/refresher/loop.py`, `tests/db/test_notify_ddl.py` and `tests/admin/test_sse_contract.py` (channel list); create `swingbot/refresher/quotes.py`, `tests/refresher/test_quote_cycle.py`, `tests/marketdata/test_refresh_quote_batch.py` | `data.refresh_quote_batch(tickers, *, yf_limit: int) -> dict[str, QuoteDetail]` (asker `ADMIN_REFRESH`, `max_age_s=0`, `yf_limit=0` skips yfinance); `layer.put(kind: DataKind, values: dict[str, Any], *, provider: str, encode=identity) -> None` (spot metals); `notify.CHANNELS` gains `"market"`; `quotes.quote_step(ctx: CycleContext) -> None`, `quotes.fx_step(ctx) -> None` appended to `loop.STEPS` |
| V201-7 | Request-path door: `market_values` (never-fetch reads, refreshing, enqueue, totals, fresh hint) | 2 | sonnet | Create `swingbot/admin/market_values.py`, `tests/admin_market/conftest.py`, `tests/admin_market/test_market_values.py`; modify `tests/admin/conftest.py` (autouse `ADMIN_REFRESHER="off"`) | See "Request-path door" and "MarketMeta" |
| V201-8 | Dashboard, tape and watchlist read through the door; no-network page-load test; endpoint sweep | 2 | opus | Modify `swingbot/admin/dashboard.py`, `swingbot/admin/api_v1/dashboard.py`, `swingbot/admin/api_v1/market.py`, `swingbot/admin/watchlist_rows.py`; create `tests/admin_market/test_page_loads_never_fetch.py`, `tests/admin_market/test_dashboard_market.py`, `tests/admin_market/test_tape_watchlist_market.py`, `docs/superpowers/results/2026-10-29-v201-endpoint-sweep.md` | Dashboard open-position rows carry the row quote fields; dashboard body gains `market_meta: MarketMeta` (open-positions totals). Tape and watchlist rows carry the row quote fields. `tests/admin_market/test_page_loads_never_fetch.py` exposes `PAGE_LOAD_ENDPOINTS: list[str]` and fixture `network_forbidden` that V201-9/13/14 extend |
| V201-9 | Trades list and Trade detail read through the door; sort on cached prices; real `prices_as_of` | 2 | opus | Modify `swingbot/admin/api_v1/trades.py`, `tests/admin_market/test_page_loads_never_fetch.py` (append endpoints); create `tests/admin_market/test_trades_market.py` | List body: `prices_as_of` = oldest row `price_as_of` (or `None`), `market_meta: MarketMeta`; rows carry the row quote fields; detail body carries the row quote fields and `market_meta` |
| V201-10 | `GET /market/updates`, `POST /market/refresh`, refresher in `/system/health` | 2 | sonnet | Create `swingbot/admin/api_v1/market_updates.py`, `tests/admin_market/test_market_updates.py`; modify `swingbot/admin/api_v1/__init__.py` (import), `swingbot/admin/api_v1/ops_health.py` | See "Endpoints" |
| V201-11 | Ops: `refresher` compose service, deploy digest loop, PITR rollback, deploy doc | 2 | sonnet | Modify `docker-compose.yml`, `deploy/deploy.sh`, `scripts/ops/rollback_to.sh`, `docs/deploy/DEPLOY_HETZNER.md`, `tests/db/test_compose.py` | Service `refresher`, `container_name: swing-refresher`, `command: ["python", "-m", "swingbot.refresher"]`, same image/env_file/state mounts as `bot`, `cpus: "0.5"`, memory limit, `depends_on: db: service_healthy`. `rollback_to.sh` stops/starts `bot admin refresher`; deploy digest loop `for svc in bot admin refresher` |
| V201-12 | Risk metrics move to core; read-only daily bars that fail loudly | 3 | opus | Create `swingbot/core/analytics/risk_payload.py`, `swingbot/core/marketdata/daily_readonly.py`, `tests/refresher/test_risk_payload.py`, `tests/refresher/test_daily_readonly.py`; modify `swingbot/admin/api_v1/risk.py`, `swingbot/admin/freshness.py` | `risk_payload.RiskMetrics` (dataclass: `metrics: dict, correlation: dict, availability: dict, bars_as_of: dict[str, str], missing_bars: list[str]`); `risk_payload.metrics_and_correlation(bars_reader: Callable[[list[str]], dict]) -> RiskMetrics`. `daily_readonly.DailyCacheUnavailable(RuntimeError)`; `daily_readonly.read_cached_daily(tickers, *, period="2y") -> tuple[dict, list[str]]`. `freshness.page_daily(tickers, *, period="2y", read_only=False)` |
| V201-13 | Snapshot job + risk and analytics snapshots; Risk, sparkline and `/analytics/snapshot` read them | 3 | opus | Create `swingbot/core/analytics/admin_snapshots.py`, `swingbot/refresher/snapshot_job.py`, `tests/refresher/test_snapshot_job.py`, `tests/refresher/test_admin_snapshots.py`, `tests/admin_market/test_risk_snapshot_route.py`; modify `swingbot/core/analytics/snapshots.py`, `swingbot/refresher/loop.py`, `swingbot/admin/api_v1/risk.py`, `swingbot/admin/api_v1/dashboard.py`, `swingbot/admin/api_v1/analytics.py` (`_snapshot` only), `tests/admin_market/test_page_loads_never_fetch.py` | `snapshots.compute_snapshot() -> dict` (`refresh_snapshot` = `save_snapshot(compute_snapshot())`, file unchanged); `admin_snapshots.SnapshotResult(doc: dict, inputs: dict, stale_inputs: bool)`; `admin_snapshots.BUILDERS: dict[str, Callable[[], SnapshotResult]]`; `admin_snapshots.register_builder(key, fn)`; `admin_snapshots.build_inputs(...) -> dict`; `admin_snapshots.stale_inputs_for(bars_oldest: date \| None, now=None) -> bool`; `snapshot_job.snapshot_step(ctx) -> None`; `snapshot_job.due_keys(now, last_runs: dict[str, datetime], *, trades_changed: bool, scan_completed: bool, queued: list[str]) -> list[str]`. Risk body gains `market_meta`, `bars_meta: {bars_as_of_oldest, bars_as_of_newest, stale_inputs, missing}`, `computed_at` |
| V201-14 | Analytics and Calendar: measure, extract payload builders, snapshot the slow default views, label filtered views | 3 | opus | Create `swingbot/core/analytics/page_payloads.py`, `tests/refresher/test_page_payloads.py`, `tests/admin_market/test_analytics_calendar_market.py`, `docs/superpowers/results/2026-10-29-v201-analytics-calendar-measure.md`; modify `swingbot/admin/api_v1/analytics.py`, `swingbot/admin/api_v1/calendar.py`, `swingbot/core/analytics/admin_snapshots.py` (register builders), `tests/admin_market/test_page_loads_never_fetch.py` | `page_payloads.performance_payload(scope, *, fetch: bool) -> dict`; `page_payloads.equity_curve_payload(scope, *, fetch: bool) -> dict`; `page_payloads.calendar_pnl_payload(month: str, strategy, horizon, *, fetch: bool) -> dict`. Snapshot keys registered only for views the measurement finds over 2 s: `analytics.performance:<ledger>`, `analytics.equity_curve:<ledger>`, `calendar.pnl:<YYYY-MM>` (current + previous month). Every Analytics/Calendar body gains `market_meta` |
| V201-15 | SPA: routes stop blocking; one dashboard load; one shared tape request | 4 | sonnet | Modify `frontend/src/app/routing/route-resolver.ts` (+spec), `routing/route-loading.service.ts` (+spec), the 15 `workspaces/*/*.routes.ts` that call `resolveRoute` (+ their specs), `stores/dashboard.store.ts` (+spec), `stores/tape.store.ts` (+spec), `stores/market-index.store.ts` (+spec), `api/interceptors.ts` (`routeRefreshInterceptor` only); create `stores/tape-feed.ts` (+spec) | `resolveRoute` removed (file deleted) once no route uses it; each route's store loads on component init. `TapeFeed` (`providedIn: 'root'`): `register(owner: string, symbols: Signal<string[]>) -> void`, `rows: Signal<Record<string, TapeRow>>`, `asOf: Signal<string \| null>`; one `api.tape(mergedSymbols)` per poll |
| V201-16 | SPA: `market` event, live-values store, `sb-market-value` cell, refresh button, stalled banner | 4 | sonnet | Modify `frontend/src/app/api/event-stream.ts` (+spec), `api/api-client.ts`, `api/models.ts`, `ui/age-hint.ts` (+spec), `shell/shell.html`, `shell/shell.ts`; create `stores/live-values.store.ts` (+spec), `ui/market-value.ts` (+spec), `ui/incomplete-note.ts` (+spec), `ui/market-refresh.ts` (+spec), `shell/refresher-banner.ts` (+spec) | See "SPA contract" |
| V201-17 | SPA: Dashboard, Trades, Trade detail, Watchlist and tape render market cells; Refresh controls | 4 | sonnet | Modify `frontend/src/app/workspaces/dashboard/**`, `workspaces/trades/**` (list + detail), `workspaces/watchlist/**` (list only), `shell/tape/**`, their stores and specs | Uses `sb-market-value`, `sb-incomplete-note`, `sb-market-refresh` (Dashboard open positions, Trades list, Trade detail), `LiveValuesStore.quote(symbol)` to patch rows; stop/target proximity cells carry the price age |
| V201-18 | SPA: Risk (two clocks), Analytics, Calendar, sparkline labels; Refresh on Risk | 4 | sonnet | Modify `frontend/src/app/workspaces/risk/**`, `workspaces/analytics/**`, `workspaces/calendar/**`, `workspaces/dashboard/**` (sparkline panel only), their stores and specs | Risk shows "prices as of HH:MM" (`market_meta.as_of`) and "daily bars through <Mon D> close" (`bars_meta.bars_as_of_oldest`); `stale_inputs` → stale tone; snapshot keys patched from `LiveValuesStore.snapshot(key)` |
| V201-19 | Full suite | 4 | sonnet | Fix observed defects in the owning task's files only | `python <wt>/scripts/dev/testrun.py full`: `0 failed`, `0 xfailed`; `complexity_gate.py` clean; `npx --prefix <wt>/frontend ng test --watch=false` green; `ng build` green |
| V201-20 | Post-deploy production timing and label check | 4 | sonnet | Create `scripts/ops/admin_page_timing.py`, `docs/superpowers/results/2026-10-29-v201-page-timing.md` | Before table (spec) vs after table: seven pages × cold/warm/during-scan, every page-load call, `/system/scan`; label check per page; pass = spec Goal 6 + labels |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-29-v201-instant-admin-page-loads_1-refresher-foundations.md` | V201-1 … V201-5 | Config/asker/session contract, tables, repositories, persisted FX, the refresher process |
| 1b | `2026-10-29-v201-instant-admin-page-loads_1b-quote-cycle.md` | V201-6 | The refresher's quote cycle and `market` NOTIFY (split out: part 1 would pass the 1500-line cap) |
| 2 | `2026-10-29-v201-instant-admin-page-loads_2-request-path-and-ops.md` | V201-7 … V201-11 | The never-fetch request door, Dashboard/tape/watchlist/Trades wiring, updates + refresh endpoints, health, compose/deploy/rollback |
| 3 | `2026-10-29-v201-instant-admin-page-loads_3-snapshots.md` | V201-12 … V201-14 | Risk code into core, read-only bars, snapshot job, Risk/sparkline/Analytics/Calendar snapshots and labels |
| 4 | `2026-10-29-v201-instant-admin-page-loads_4-spa-and-verification.md` | V201-15 … V201-20 | Non-blocking routes, live values, the market cell, page wiring, full suite, production check |

## Cross-task contracts

### Config fields (V201-1; `swingbot/config.py`, group `"Data Sources"`, all hot-reloadable)

| Key | Type | Default | Range |
|---|---|---|---|
| `ADMIN_REFRESHER` | select `on`/`off` (`_MODE_VALUES`) | `on` | — |
| `ADMIN_REFRESH_REGULAR_S` | number | 30 | 10–300 |
| `ADMIN_REFRESH_EXTENDED_S` | number | 300 | 60–3600 |
| `ADMIN_REFRESH_CLOSED_S` | number | 1800 | 300–7200 |
| `ADMIN_REFRESH_SNAPSHOT_S` | number | 300 | 60–3600 |
| `ADMIN_REFRESH_YF_FALLBACK_CAP` | number | 25 | 0–500 |
| `ADMIN_REFRESH_MARK_TIMEOUT_S` | number | 120 | 30–900 |
| `ADMIN_REFRESH_FX_UNKNOWN_RETRY_S` | number | 21600 | 600–604800 |
| `ADMIN_STALE_PRICE_REGULAR_S` | number | 120 | 30–1800 |
| `ADMIN_STALE_PRICE_EXTENDED_S` | number | 900 | 60–7200 |
| `ADMIN_STALE_SNAPSHOT_REGULAR_S` | number | 600 | 60–7200 |
| `ADMIN_STALE_SNAPSHOT_EXTENDED_S` | number | 1800 | 300–14400 |

### Contract module (V201-1; `swingbot/core/marketdata/shared/admin_refresh.py`)

- `refresher_on() -> bool` (see Global Constraints).
- `cadence_s(state: str) -> float`: regular, extended and closed map to the three `ADMIN_REFRESH_*_S` fields.
- `stale_after_s(kind: str, state: str) -> float | None`: `kind` is `"price"` or `"snapshot"`. Regular and extended use the four `ADMIN_STALE_*` fields; `closed` → `None`.
- `heartbeat_stalled(beat_at: datetime | None, cadence: float, now: datetime | None = None) -> bool`: `None` → `True`, else age > 3 × cadence.
- `quote_mark_key(symbol) -> str` → `"quote:<SYMBOL>"`. `snapshot_mark_key(key) -> str` → `"snapshot:<key>"`.
- `PRIORITY_USER = 0`, `PRIORITY_FRESH_HINT = 1`, `PRIORITY_MISSING = 2`.
- `QUEUE_KIND_QUOTE = "quote"`, `QUEUE_KIND_SNAPSHOT = "snapshot"`.
- `SNAPSHOT_KEY_PATTERNS: tuple[str, ...] = ("risk", "analytics.snapshot", "analytics.performance:*", "analytics.equity_curve:*", "calendar.pnl:*")`. `is_snapshot_key(key) -> bool` matches with `fnmatch`.
- `HEARTBEAT_KEY = "refresher"`. `QUEUE_RETENTION_S = 3600`.

### Tables (V201-2; each also has `standard_columns()` = `doc JSONB`, `updated_at`)

- `admin_snapshots`: `key Text PK`, `computed_at TIMESTAMPTZ NOT NULL`, `inputs JSONB NOT NULL DEFAULT '{}'`, `stale_inputs Boolean NOT NULL DEFAULT false`; index `admin_snapshots_updated_idx (updated_at)`. The payload is `doc`.
- `quote_currencies`: `symbol Text PK`, `code Text NULL`, `outcome Text NOT NULL` (`"known"` \| `"unknown"`), `checked_at TIMESTAMPTZ NOT NULL`, `retry_after TIMESTAMPTZ NULL`.
- `market_refresh_queue`: `id BigInteger PK`, `kind Text NOT NULL`, `key Text NOT NULL`, `priority SmallInteger NOT NULL`, `requested_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `taken_at TIMESTAMPTZ NULL`; partial unique index `market_refresh_queue_pending_uq (kind, key) WHERE taken_at IS NULL`; index `market_refresh_queue_take_idx (taken_at, priority, requested_at)`.
- `market_refresh_marks`: `key Text PK`, `started_at TIMESTAMPTZ NOT NULL`, `expires_at TIMESTAMPTZ NOT NULL`, `error Text NULL`, `error_at TIMESTAMPTZ NULL`; index `market_refresh_marks_updated_idx (updated_at)`. A row with `expires_at <= now()` is not in flight. A cleared mark keeps its row with `expires_at = now()` and the error, so `/market/updates` sees the change.
- `refresher_heartbeat`: `key Text PK`, `beat_at TIMESTAMPTZ NOT NULL`, `cadence_s Float NOT NULL`, `session Text NOT NULL`, `cycle_ms Integer NULL`, `last_error Text NULL`.

### Repositories (V201-3; `swingbot/core/db/repositories/market_refresh.py`, connection handling as `equity_samples.py`)

- `AdminSnapshotRepository`: `put(key, doc, inputs, *, computed_at, stale_inputs) -> None`; `get(key) -> dict | None` (`key, doc, inputs, computed_at, stale_inputs, updated_at`); `get_many(keys) -> dict[str, dict]`; `changed_since(since: datetime) -> list[dict]` (`key, computed_at, stale_inputs, updated_at`).
- `QuoteCurrencyRepository`: `get_many(symbols) -> dict[str, dict]` (`symbol, code, outcome, checked_at, retry_after`); `put(symbol, code, outcome, *, checked_at, retry_after=None) -> None`; `due(symbols, now) -> list[str]` (symbols with no row, plus `unknown` rows with `retry_after <= now`).
- `RefreshQueueRepository`: `enqueue(kind, keys, *, priority) -> int` (rows inserted; skips a pending `(kind, key)`, and a lower priority number replaces a pending higher one); `take(limit: int) -> list[dict]` (`kind, key, priority`, ordered priority then `requested_at`, stamps `taken_at`); `prune(older_than: datetime) -> int`.
- `RefreshMarkRepository`: `mark(keys, *, timeout_s: float, now=None) -> None`; `clear(keys, *, error: str | None = None, now=None) -> None`; `active(keys, now=None) -> set[str]`; `errors(keys) -> dict[str, str]`; `changed_since(since: datetime) -> list[dict]` (`key, in_flight: bool, error, updated_at`).
- `RefresherHeartbeatRepository`: `beat(*, cadence_s: float, session: str, cycle_ms: int | None, last_error: str | None, now=None) -> None`; `read() -> dict | None` (`beat_at, cadence_s, session, cycle_ms, last_error`).
- Accessors: `admin_snapshot_repo()`, `quote_currency_repo()`, `refresh_queue_repo()`, `refresh_mark_repo()`, `refresher_heartbeat_repo()`.

### Request-path door (V201-7; `swingbot/admin/market_values.py`)

- `MarketQuote` (frozen dataclass: `symbol: str, price: float | None, as_of: str | None, age_s: float | None, refreshing: bool, error: str | None`).
- `read_quotes(symbols: Iterable[str]) -> dict[str, MarketQuote]`. Keys are upper-case. It never fetches. Any symbol that is missing, or older than `stale_after_s("price", state)` and not in flight, is enqueued at `PRIORITY_MISSING`, and a missing one is returned with `refreshing=True`. When `kinds.is_fresh_request()`, every symbol is enqueued at `PRIORITY_FRESH_HINT`.
- `quote_fields(q: MarketQuote | None) -> dict` returns exactly `current_price`, `current_price_stale` (`False`), `price_as_of`, `price_age_s`, `price_refreshing`, `price_error`. These are the **row quote fields**.
- `total_meta(quotes: Iterable[MarketQuote | None], *, extra_missing: int = 0, now=None) -> dict` → MarketMeta with `source="request"`.
- `read_snapshot(key: str) -> dict | None` → `{doc, computed_at, inputs, stale_inputs, refreshing, error}`. A missing key is enqueued at `PRIORITY_MISSING` and returns `None`.
- `snapshot_meta(snap: dict | None, *, quotes_meta: dict | None = None) -> dict` → MarketMeta with `source="snapshot"`.
- `request_refresh(symbols: Iterable[str], snapshots: Iterable[str], *, priority: int = PRIORITY_USER) -> int`.

### MarketMeta (every key always present)

`{"as_of": str | None, "refreshing": bool, "stale_count": int, "missing_count": int, "incomplete": bool, "computed_at": str | None, "stale_inputs": bool, "source": "request" | "snapshot", "error": str | None}`. `as_of` is the **oldest** input `as_of`. `incomplete` is `missing_count > 0`.

### Snapshot inputs (V201-13; `admin_snapshots.build_inputs`)

`{"computed_at": iso, "oldest_quote_as_of": iso | None, "bars_as_of": {"per_symbol": {SYM: "YYYY-MM-DD"}, "oldest": date | None, "newest": date | None}, "missing": {"quotes": [...], "bars": [...], "fx": [...]}, "ledger": str | None, "trade_ids": [...]}`

### Endpoints (V201-10)

- `GET /api/v1/market/updates?since=<ISO-8601>` (`since` optional; malformed → 400 `invalid`). Returns `{"cursor": iso, "quotes": [{"symbol", "price", "as_of", "refreshing", "error"}], "snapshots": [{"key", "computed_at", "refreshing", "stale_inputs", "error"}], "status": {"session", "last_close_at", "stale_price_s", "stale_snapshot_s", "heartbeat": {"beat_at", "cadence_s", "stalled"}}}`. Without `since`, the lists are empty and only `status` is filled. It never fetches.
- `POST /api/v1/market/refresh`, body `{"symbols": [str] (≤ 200), "snapshots": [str] (each passes is_snapshot_key)}`. Both empty, too many symbols or an unknown key → 400. Success → 202 `{"queued": int}`.
- `GET /api/v1/system/health` gains `refresher: {"status": "ok" | "stalled" | "off", "beat_at", "cadence_s", "last_error"}`.
- Thin SSE event `market` (no payload). The SPA reacts by calling `/market/updates?since=<cursor>`, and does the same on reconnect.

### SPA contract (V201-16; `frontend/src/app`)

- `api/models.ts`: `MarketMeta`, `QuoteUpdate`, `SnapshotUpdate`, `MarketStatus`, `MarketUpdates` mirror the JSON above; `RowQuoteFields { current_price; price_as_of; price_age_s; price_refreshing; price_error }`.
- `ApiClient.marketUpdates(since: string | null): Observable<MarketUpdates>`; `ApiClient.refreshMarket(body: {symbols?: string[]; snapshots?: string[]}): Observable<{queued: number}>`.
- `EventName` / `EVENT_NAMES` gain `'market'`.
- `LiveValuesStore` (`stores/live-values.store.ts`, root): `status: Signal<MarketStatus | null>`, `stalled: Signal<boolean>`, `quote(symbol): Signal<QuoteUpdate | null>`, `snapshot(key): Signal<SnapshotUpdate | null>`, `requestRefresh(symbols: string[], snapshots: string[]): void` (marks those keys `refreshing` locally at once).
- `ui/age-hint.ts`: `marketAgeLabel(asOf: string | null, nowMs: number, status: MarketStatus | null, kind: 'price' | 'snapshot') -> {text: string | null, tone: 'fresh' | 'stale' | 'stalled' | 'closed'}`. Stalled wins over closed, and closed wins over stale. The closed text is `last close · <Ddd> HH:MM ET`.
- `sb-market-value` (`ui/market-value.ts`): inputs `asOf`, `refreshing`, `error`, `kind` (`'price'` default), `staleInputs` (default `false`). The value is projected through `<ng-content>`. It ticks off `ui/clock.ts` and shows an `sb-spinner` while `refreshing && !error`, or alone when the value is empty.
- `sb-incomplete-note` (`ui/incomplete-note.ts`): input `missing: number` → "incomplete: N positions unpriced"; nothing at 0.
- `sb-market-refresh` (`ui/market-refresh.ts`): inputs `symbols: string[]`, `snapshots: string[]`, a button labelled "Refresh"; calls `LiveValuesStore.requestRefresh`.
- `sb-refresher-banner` (`shell/refresher-banner.ts`): "Prices paused: refresher not running" while `LiveValuesStore.stalled()`.

## Out of scope (endpoint sweep)

These keep their current fetch paths behind their existing skeleton or
spinner. Their routes stop blocking in V201-15, but they are not
pre-warmed:

- Charts: `/equity/candles`, trade and plan chart endpoints, ticker-detail
  charts. They need bars, not quotes, and the spec makes a display-bar cache
  out of scope.
- Research, reports, versions, system, cancels and plan detail: no quote/FX
  total on page load is in the spec's page list.

V201-8 runs the sweep (`git grep` of request handlers for the forbidden
functions) and writes any further hit into
`docs/superpowers/results/2026-10-29-v201-endpoint-sweep.md`, either listed
here with a reason or flagged to the controller.
