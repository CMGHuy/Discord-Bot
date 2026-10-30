# Admin snapshot pages implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [Admin snapshot pages](../specs/2026-10-29-v204-admin-snapshot-pages.md) (precedence: "Brief corrections", then "Panel amendments", then the earlier text)
**Depends on:** v201 ([index](2026-10-29-v201-instant-admin-page-loads_0-index.md), § "Cross-task contracts") merged into `main` before V204-1 starts.

**Goal:**

Risk, Analytics and Calendar are the admin pages that still time out. On
production on 2026-10-29 `GET /risk`, `/analytics/performance` and
`/calendar/pnl` failed at 30 s, and `/analytics/equity-curve` took 47.5 s.
The reason is that their request threads do the heavy work themselves:
`get_risk` runs `collect_portfolio_state` and reads daily bars (4 s when
quiet, 52 s under a scan), and the dashboard sparkline rebuilds
`refresh_snapshot()` inline and then returns an empty series to the very
request that rebuilt it. v201 fixed prices with a background refresher.
This plan does the same for these computed pages.

Once shipped, v201's refresher process also runs a **snapshot worker** on
its own thread. It recomputes the Risk payload, the analytics snapshot that
feeds the sparkline, and (where measuring shows a need) the default
Analytics and Calendar views, then stores each one as a row in a new
Postgres table `admin_snapshots`. Each row records the inputs it was built
from: FX rates, quotes where used, a fingerprint of each daily-bar file,
the thresholds in force and the code version. Page requests read the row,
never the network. They render it at once with its age, a spinner while a
rebuild runs, and a stale warning when the bars behind it are older than
the last completed NYSE session. The risk maths moves into `swingbot/core`
unchanged, so the snapshot and the kill-switch fallback (`ADMIN_REFRESHER=off`,
today's request-time code) call the same functions. Frozen golden payloads,
recorded before the move, prove that.

Discord, the scan, plan building, backtests and the file
`analytics_snapshot.json` are left as they are. The file keeps its Discord
readers, and a parity test pins it to the table. Filtered Analytics views and
older Calendar months are not snapshotted. They compute on request from
Postgres and persisted FX, and never fetch.

Success is measured on production with v201's Playwright timing script,
extended in V204-19. Risk, Analytics, Calendar and the dashboard sparkline
must show data within 2 s, cold, warm and during a scan. `/system/scan`
must stay within 0.5 s. A label check confirms that every figure carries
its as-of, that Risk shows its two clocks ("FX rates as of" and "daily bars
through"), and that P&L reads "pre-tax, before modelled frictions".

**Architecture:** A core read-only bar reader (`daily_readonly`) and the moved
risk payload (`risk_payload`) are shared by the refresher's snapshot builders
(`admin_snapshots`) and the kill-switch-off request path. A snapshot worker
thread in the refresher builds due keys under a time budget and upserts them
compare-and-set. Request handlers read rows through v201's `market_values`
door, which never builds and only enqueues. The SPA patches snapshot keys from
`/market/updates` and refetches its page once per newer snapshot.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy Core + Alembic (Postgres),
pandas, threading; Angular (zoneless, signals), vitest; Playwright (Node) for
the production probe.

## Global Constraints

- `Bump: ui patch, bot patch` is applied at `/close-out`, not by any task. No task edits `VERSION.json`.
- **v201 is merged first.** Before V204-1, `git -C <wt> grep -n "def refresher_on" swingbot/core/marketdata/shared/admin_refresh.py` and `git -C <wt> grep -n "def request_refresh" swingbot/admin/market_values.py` both hit. If either misses, stop and report `BLOCKED: v201 not merged`.
- Implement in a worktree under `.claude/worktrees/`, named per `document-lifecycle.md`. Every command uses absolute paths or `git -C <wt>`. Stage explicit paths only, never `git add -A`.
- **No request thread serving Risk, Analytics, Calendar or the dashboard sparkline makes a market, FX or daily-bar network call while `admin_refresh.refresher_on()` is true.** Forbidden in those handlers when on: everything v201 forbids, plus `freshness.page_daily(..., read_only=False)`, `freshness._daily_for`, `data.get_daily_data`, `data.get_daily_data_batch`, `snapshots.refresh_snapshot`, `snapshots.compute_snapshot`, `collect_portfolio_state`, every `admin_snapshots.build_*`, `fx.quote_currency_code(..., fetch=True)` and `fx._refreshed_frame`. The Risk Refresh control *enqueues* and returns.
- **Kill switch.** When `refresher_on()` is false, Risk, Analytics, Calendar and the sparkline run **today's request-time code** (`_cached(...)`, `collect_portfolio_state`, `load_snapshot(...) or refresh_snapshot()`). The only change on that path is the new meta keys added beside the old payload. `tests/admin/conftest.py` already pins `ADMIN_REFRESHER="off"` (V201-7), so the existing admin suite keeps covering the fallback. New tests set `"on"` explicitly.
- **Golden payloads are frozen.** V204-1 writes `tests/admin_snapshots/golden/*.json` from the code as it was before this plan. No later task regenerates or edits them. A failing parity test means the code is fixed, never the golden file.
- **Success path byte-identical.** The moved risk code and every builder return the same payload as the pre-v204 request path for the same inputs. Errors that today's code swallows (`refresh_snapshot`, `_asset_correlation`, `_distribution_metrics`) are surfaced **only** under `strict=True`, which the snapshot builders use: they raise, or the symbol lands in `missing` with a reason.
- **Read-only bars.** The snapshot path reads daily bars only through `daily_readonly.read_cached_daily`, which reads only `daily_delta.read_daily(T, basis=daily_delta.BASIS_YF)`. It never reads `data/backtest_cache/`, never calls a provider and never writes or creates a file or directory. An unmounted cache directory raises `DailyCacheUnavailable`. A file that is unreadable, empty or shorter than `min_rows` goes into `missing` with a reason. Spot metals are always `missing` (`"spot_metal"`) and are excluded from `stale_inputs`. No new `swingbot.core` → `swingbot.admin` import.
- **`stale_inputs` has one source:** `admin_snapshots.expected_bar_date(now)`, built on v201's `session.last_regular_close(now)` converted to an America/New_York date. Between that close and 20:00 ET on the same date, the expected date is the previous session's. Non-US tickers use the same NYSE date.
- **A missing input is never zero.** A position with no FX code, or no bars where bars are needed, is left out of the affected figure and counted in `missing_count`. The body's `lower_bound` names that figure. Correlation with fewer than 2 overlapping bars, and beta with zero benchmark variance, are `null` with a reason, never `NaN` or `0`.
- **One table, one revision.** `admin_snapshots` is created by the one Alembic revision `v204_001`. Its `down_revision` is the head that `python -m alembic -c <wt>/alembic.ini heads` prints at run time (`v201_001` expected). It is registered with `schema.register` and `PROMOTION_REASONS`, and it is not in `events.TABLE_CHANNELS`. There is one row per key, written by `put` as compare-and-set (newer `computed_at` wins), and month keys older than the previous month are pruned. The downgrade drops the table.
- **Snapshots never stall prices.** Builds run on the snapshot worker thread, never inline in `loop.run_cycle`. Each build has the `ADMIN_SNAPSHOT_BUDGET_S` budget. A build that overruns is abandoned: its mark is cleared with an error, its late result can only land through the compare-and-set, and the key is not built again while that thread is still alive.
- **At most three `market` events per cycle:** the quote marks set (v201), the cycle-end publish that carries quote values and snapshot marks (v201's, with `report.changed`), and one worker publish per landed batch.
- **No notification volume.** Nothing under `swingbot/refresher/`, nor `swingbot/core/analytics/admin_snapshots.py`, `risk_payload.py` or `swingbot/core/marketdata/daily_readonly.py`, imports `discord` or `swingbot.commands`. V204-10 pins this with an AST guard and a runtime check.
- **Copy, exact:** P&L basis `pre-tax, before modelled frictions`; Risk clocks `FX rates as of HH:MM` and `daily bars through Mmm D close`; lower bound `≥ <value>, <N> position unpriced` / `positions unpriced`; closed market `as of last close · Ddd HH:MM ET`.
- Every function written or changed stays below cyclomatic complexity 15 (`python <wt>/scripts/dev/complexity_gate.py`). A moved function keeps its body.
- Tests: **add no test file under `tests/admin/`** (that suite sits near its cap). Edit existing files there only where a shape changes. New backend tests go in `tests/admin_snapshots/`, a new suite `admin-snapshots` that V204-1 registers. Exceptions: migration and repository tests go in `tests/db/` (suite `storage`), config keys in `tests/test_config_v204_keys.py` (suite `config`, beside `tests/test_config_v201_keys.py`), and the page-load append in `tests/admin_market/test_page_loads_never_fetch.py`. SPA tests are co-located `*.spec.ts`.
- Per-task verification is the narrow run `python <wt>/scripts/dev/testrun.py file <test>` (SPA: `npm --prefix <wt>/frontend exec -- ng test --watch=false --include <spec>`). The one full-suite run is V204-18. A task that runs DB tests runs `/replicate-prod-db` first, into the shared `swing-db` container.
- UI: every new label, spinner and note is checked at mobile, tablet and desktop widths (`ui-design.md`). It wraps under its value on narrow widths and never widens a table column.
- **Production is touched only by V204-19,** a read-only Playwright probe after the partner's normal deploy. V204-2 measures locally against the replicated DB. No task deploys anything or edits the VM `.env`.

## Review Focus

- **The refresher container lacks the bar-cache mount (or loses it).** The risk build raises `DailyCacheUnavailable`, the previous row is kept, the mark clears with the error, and the Risk page shows the error tone over the old age. It never shows zero metrics. Pinned in V204-5 (`test_unmounted_cache_dir_raises`) and V204-9 (`test_failing_build_keeps_previous_row_and_clears_mark_with_error`).
- **A build overruns its budget during a scan and finishes after the next build has landed.** The late `put` is rejected, the newer row stays, and no second build of that key starts while the first thread is alive. Pinned in V204-4 (`test_put_older_computed_at_is_rejected`) and V204-9 (`test_overrun_is_abandoned_and_late_result_cannot_overwrite`).
- **A Monday 09:40 ET after a holiday Friday, a Saturday, and 17:30 ET before the scan updates the daily file.** `stale_inputs` follows `expected_bar_date`: not flagged when the bars hold the last completed session, flagged when they are a session behind. Pinned in V204-7 (`test_expected_bar_date_*`, four cases).
- **First boot after deploy, or a new month: the key has no row yet.** The route returns the empty body with `refreshing: true` and enqueues the key once. It does not return a 500, zeros or a request-time build. A month that rolls off is pruned. Pinned in V204-11 (`test_absent_snapshot_is_refreshing_and_enqueued_once`), V204-12 (`test_risk_on_with_no_row_returns_empty_body_refreshing`) and V204-10 (`test_month_rollover_prunes_old_calendar_key`).
- **An open spot-metal or non-USD position with no persisted FX code.** It is listed in `missing`, the affected figure carries `lower_bound`, and the SPA shows `≥ …, 1 position unpriced`. It is never summed as zero. Pinned in V204-12 (`test_risk_lower_bound_names_figures_missing_inputs`) and V204-16 (`lower-bound note renders for a partial book`).

## Parallelisation

At most 2 implementers at once (`CLAUDE.md`). Sequential edges and why:

- **V204-1 first.** The golden payloads must be recorded before any code they cover changes, and V204-1 registers the `admin-snapshots` suite that every later backend test file lives in.
- **V204-2 ∥ V204-1, V204-3, V204-4.** Its files are disjoint: a new timing script and a results doc. **V204-2 → V204-8** because V204-8 sets `SNAPSHOT_ROUTES` from its verdict.
- **V204-3 ∥ V204-4.** Disjoint files: `config.py` and `admin_refresh.py`, against the migration, `schema.py` and the repository.
- **V204-5 → V204-6 → V204-7 → V204-8.** V204-6 consumes `read_cached_daily` and `collect_portfolio_state(bars_reader=)`. V204-7 consumes `risk_payload.metrics_and_correlation`. V204-8 extends V204-7's `admin_snapshots.py`.
- **V204-3 → V204-7:** `build_inputs` records the snapshot thresholds and `expected_bar_date` uses the snapshot key helpers.
- **V204-4, V204-8 → V204-9 → V204-10.** The worker puts through the repository and calls `builders()`. Both tasks edit `swingbot/refresher/snapshot_job.py`.
- **V204-3, V204-4 → V204-11:** the door reads `admin_snapshot_repo()` and validates keys with `is_snapshot_key`.
- **V204-7, V204-11 → V204-12 → V204-13 → V204-14.** V204-12 edits `risk.py`. V204-13 and V204-14 both edit `api_v1/analytics.py`. V204-14 alone appends the Risk, Analytics and Calendar endpoints to `tests/admin_market/test_page_loads_never_fetch.py`, so it runs last of the three.
- **SPA.** V204-15 depends on no backend task at test time, because fakes stand in and the payload shapes are fixed below. It may run beside any backend task. **V204-15 → V204-16, V204-17**, which consume its primitives. **V204-16 ∥ V204-17**: disjoint files (`stores/risk.store.ts`, `workspaces/risk/**` against `stores/analytics|calendar|dashboard.store.ts`, `workspaces/analytics|calendar|dashboard/**`).
- **Ownership of `dashboard.store.ts` and the sparkline.** v201's V201-17 owned `frontend/src/app/stores/dashboard.store.ts` and `workspaces/dashboard/**` and left the sparkline unlabelled. In v204 the only editor of those files is **V204-17**, which adds the sparkline's snapshot label on top of V201-17's merged code. No other v204 task touches them. If V201-17 is not on `main` when V204-17 starts, stop and report.
- **V204-18** (full suite) follows every task through V204-17. **V204-19** runs only after the branch is merged and the partner has deployed. It is a post-deploy check, not a code task.

## Task ledger

| ID | Title | Part | Model | Files | Cross-task contract |
|---|---|---|---|---|---|
| V204-1 | Golden parity payloads from today's request code; `admin-snapshots` suite | 1 | opus | Create `tests/admin_snapshots/__init__.py`, `tests/admin_snapshots/golden_book.py`, `tests/admin_snapshots/record_golden.py`, `tests/admin_snapshots/golden/{risk,performance_main,equity_curve_main,calendar_pnl,analytics_snapshot,sparkline}.json`, `tests/admin_snapshots/test_golden_today.py`; modify `tests/suites.toml` | `golden_book.py`: pytest fixture `golden_book` (seeds the fixed book, writes yfinance-basis bar files under a tmp `DATA_DIR`, stubs FX to fixed rates, freezes `now` at `GOLDEN_NOW = datetime(2026, 10, 28, 21, 0, tzinfo=UTC)`, poisons every network function); `golden_payload(name: str) -> dict`; `GOLDEN_NAMES: tuple[str, ...]`; `normalise(body: dict) -> dict` (drops `killswitch`, `scan_health`, `as_of`/`built_at` wall-clock keys). `[suites.admin-snapshots]` paths `["tests/admin_snapshots/"]` |
| V204-2 | Measure first: Analytics/Calendar under persisted FX alone | 1 | sonnet | Create `scripts/dev/time_admin_routes.py`, `tests/admin_snapshots/test_time_admin_routes.py`, `docs/superpowers/results/2026-10-29-v204-measure-first.md` | Results doc carries one verdict line per route, `analytics.performance`, `analytics.equity_curve` and `calendar.pnl`, each `request` or `snapshot`. Rule: `request` when, against the replicated DB with `ADMIN_REFRESHER=on` and the network poisoned, warm max ≤ 0.5 s **and** cold max ≤ 1.0 s over 5 runs each; otherwise `snapshot`. A network call during the run is a defect to report, not a timing |
| V204-3 | Snapshot config fields, `stale_after_s("snapshot")`, snapshot keys and marks | 1 | sonnet | Modify `swingbot/config.py`, `swingbot/core/marketdata/shared/admin_refresh.py`; create `tests/test_config_v204_keys.py`, `tests/admin_snapshots/test_snapshot_contract.py` | See "Config fields" and "Contract module additions" |
| V204-4 | Alembic `v204_001`: `admin_snapshots` table; compare-and-set repository | 1 | opus | Create `swingbot/core/db/migrations/versions/v204_001_admin_snapshots.py`, `swingbot/core/db/repositories/admin_snapshots.py`, `tests/db/test_v204_admin_snapshots.py`; modify `swingbot/core/db/schema.py` | See "Table" and "Repository" |
| V204-5 | Core read-only daily-bar reader; `page_daily(read_only=)`; `collect_portfolio_state(bars_reader=)` | 2 | opus | Create `swingbot/core/marketdata/daily_readonly.py`, `tests/admin_snapshots/test_daily_readonly.py`; modify `swingbot/admin/freshness.py`, `swingbot/core/edge/portfolio_state.py` | See "Read-only bars" |
| V204-6 | Risk maths moves to core unchanged; strict mode; parity with golden | 2 | opus | Create `swingbot/core/analytics/risk_payload.py`, `tests/admin_snapshots/test_risk_payload.py`; move `swingbot/admin/api_v1/risk_read_model.py` → `swingbot/core/analytics/risk_read_model.py` (`git mv`, admin path re-exports its three public names); modify `swingbot/admin/api_v1/risk.py`; retarget patch paths only in `tests/admin/test_api_v1_risk.py`, `tests/admin/test_risk_read_model.py` | See "Risk payload" |
| V204-7 | Snapshot inputs, `expected_bar_date`/`stale_inputs`, the risk builder | 2 | opus | Create `swingbot/core/analytics/admin_snapshots.py`, `tests/admin_snapshots/test_snapshot_inputs.py`, `tests/admin_snapshots/test_build_risk.py` | See "Snapshot builders" (V204-7 rows) |
| V204-8 | Analytics, sparkline and Calendar builders; `compute_snapshot`; file-producer parity | 2 | opus | Modify `swingbot/core/analytics/admin_snapshots.py`, `swingbot/core/analytics/snapshots.py`; create `swingbot/core/analytics/page_bodies.py` (only for routes V204-2 marked `snapshot`), `tests/admin_snapshots/test_build_analytics.py`, `tests/admin_snapshots/test_file_producer_parity.py`; modify `swingbot/admin/api_v1/analytics.py`, `swingbot/admin/api_v1/calendar.py` only to call moved body functions | See "Snapshot builders" (V204-8 rows) |
| V204-9 | Snapshot worker thread: budget, abandon, compare-and-set landing, marks, landed event | 3 | opus | Create `swingbot/refresher/snapshot_job.py`, `tests/admin_snapshots/test_snapshot_worker.py` | See "Snapshot job" (V204-9 rows) |
| V204-10 | Scheduling: due keys, cadence, trade/scan triggers, queue keys, month prune; loop step; no-notification guard | 3 | opus | Modify `swingbot/refresher/snapshot_job.py`, `swingbot/refresher/loop.py`, `swingbot/refresher/__main__.py` (start/stop the worker); create `tests/admin_snapshots/test_snapshot_schedule.py`, `tests/admin_snapshots/test_no_notification_guard.py` | See "Snapshot job" (V204-10 rows) |
| V204-11 | Request door for snapshots; `snapshots` on `/market/updates` and `/market/refresh` | 3 | sonnet | Modify `swingbot/admin/market_values.py`, `swingbot/admin/api_v1/market_updates.py`; create `tests/admin_snapshots/test_snapshot_door.py`, `tests/admin_snapshots/test_market_updates_snapshots.py` | See "Request-path door additions" and "Endpoints" |
| V204-12 | Risk reads its snapshot; kill-switch fallback pinned; two-clock metas; lower bounds | 3 | opus | Modify `swingbot/admin/api_v1/risk.py`, `tests/admin/test_api_v1_risk.py` (`test_risk_shape` gains the new keys); create `tests/admin_snapshots/test_risk_route.py` | See "Risk body additions" |
| V204-13 | Sparkline, `/analytics/snapshot` and the strategies registry read `analytics.snapshot`; request-time `refresh_snapshot` guard | 4 | sonnet | Modify `swingbot/admin/api_v1/dashboard.py` (`_equity_30d`), `swingbot/admin/api_v1/analytics.py` (`_snapshot`, `analytics_snapshot`), `swingbot/admin/queries.py` (`_registry_rows`), `tests/admin/test_api_v1_dashboard.py` (`equity_30d` shape); create `tests/admin_snapshots/test_sparkline_and_snapshot_route.py`, `tests/admin_snapshots/test_no_request_refresh_snapshot.py` | `equity_30d` gains `market_meta`; `/analytics/snapshot` body gains `market_meta`. Guard names `api_v1/analytics.py` `_snapshot`, `api_v1/dashboard.py` `_equity_30d` and `queries.py` `_registry_rows` |
| V204-14 | Analytics default/filtered and Calendar routes: snapshot or never-fetch request, both with `market_meta`; page-load no-network test | 4 | opus | Modify `swingbot/admin/api_v1/analytics.py` (`/analytics/performance`, `/analytics/equity-curve`), `swingbot/admin/api_v1/calendar.py` (`calendar_pnl`), `tests/admin_market/test_page_loads_never_fetch.py` (append `/risk`, `/analytics/snapshot`, `/analytics/performance`, `/analytics/equity-curve`, `/calendar/pnl`, a filtered `/analytics/performance?strategy=…`, and `/calendar/pnl?month=<older>`); create `tests/admin_snapshots/test_analytics_calendar_routes.py` | Every Analytics/Calendar body gains `market_meta` (`source: "snapshot"` for a default view whose route is in `SNAPSHOT_ROUTES`, else `"request"` with FX as-of and counts) |
| V204-15 | SPA primitives: snapshot models, live snapshot updates, snapshot age tone, refresh with snapshots, `followSnapshot`, lower-bound and P&L-basis labels | 4 | sonnet | Modify `frontend/src/app/api/models.ts`, `api/api-client.ts`, `stores/live-values.store.ts` (+spec), `ui/age-hint.ts` (+spec), `ui/market-value.ts` (+spec), `ui/market-refresh.ts` (+spec); create `stores/snapshot-follow.ts` (+spec), `ui/lower-bound.ts` (+spec), `ui/pnl-basis.ts` (+spec) | See "SPA contract" |
| V204-16 | SPA Risk: two clocks, panel warnings, heat vs account, lower bounds, pre-tax label, Refresh | 5 | sonnet | Modify `frontend/src/app/stores/risk.store.ts` (+spec), `workspaces/risk/risk.ts` (+`risk.spec.ts`), `workspaces/risk/risk.html`/`.scss` if the component has them | Consumes "SPA contract"; produces nothing shared |
| V204-17 | SPA Analytics, Calendar and the dashboard sparkline: snapshot labels, filtered as-of labels, pre-tax label | 5 | sonnet | Modify `frontend/src/app/stores/analytics.store.ts` (+spec), `workspaces/analytics/tabs/overview.ts` (+spec), `stores/calendar.store.ts` (+spec), `workspaces/calendar/calendar.ts` (+spec), `stores/dashboard.store.ts` (+spec), the `sb-trading-performance` sparkline panel under `workspaces/dashboard/` (+spec) | Consumes "SPA contract"; produces nothing shared |
| V204-18 | Full suite | 5 | sonnet | Fix observed defects in the owning task's files only | `python <wt>/scripts/dev/testrun.py full`: `0 failed`, `0 xfailed`; `complexity_gate.py` clean; `npm --prefix <wt>/frontend exec -- ng test --watch=false` green; `ng build` green |
| V204-19 | Post-deploy production timing and label check | 5 | sonnet | Modify `frontend/scripts/admin-page-timing.mjs`, `frontend/scripts/admin-page-timing.test.mjs`; create `docs/superpowers/results/2026-10-29-v204-page-timing.md` | Extends v201's script with pages `risk`, `analytics`, `calendar` and the dashboard sparkline selector. It does not write a new probe. Records commit, versions, scan state, and each snapshot's `bars_as_of` and `computed_at` per pass. Pass = spec Goal 4 + the label check |

The ledger has 19 tasks. One `b` split row is the most the cap leaves room for.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-29-v204-admin-snapshot-pages_1-golden-and-foundations.md` | V204-1 … V204-4 | Golden payloads, measure-first, snapshot config/keys, the table and its compare-and-set repository |
| 2 | `2026-10-29-v204-admin-snapshot-pages_2-risk-move-and-builders.md` | V204-5 … V204-8 | Read-only bars, the risk move with parity, snapshot inputs/staleness, every builder |
| 3 | `2026-10-29-v204-admin-snapshot-pages_3-worker-and-risk-route.md` | V204-9 … V204-12 | Snapshot worker, scheduling and guard, the request door and endpoints, the Risk route |
| 4 | `2026-10-29-v204-admin-snapshot-pages_4-routes-and-spa-primitives.md` | V204-13 … V204-15 | Sparkline/analytics-snapshot/registry routes, Analytics/Calendar routes, SPA primitives |
| 5 | `2026-10-29-v204-admin-snapshot-pages_5-spa-pages-and-verification.md` | V204-16 … V204-19 | Risk page, Analytics/Calendar/sparkline labels, full suite, production check |

## Cross-task contracts

v201 names used unchanged: `admin_refresh.refresher_on`, `cadence_s`, `stale_after_s`, `PRIORITY_*`, `QUEUE_KIND_SNAPSHOT`; `session.session_state`, `session.last_regular_close`; `refresh_queue_repo()`, `refresh_mark_repo()`; `market_values.total_meta`, `request_refresh`, MarketMeta; `loop.STEPS`, `loop.CycleContext.queued_snapshots`, `loop.CycleReport.snapshots_written`/`changed`/`error`; `notify.publish("market")`; `fx.quote_currency_code(t, *, fetch=False)`, `fx.fx_rate(..., refresh=False)`; `fx_convert.to_account_currency`, `convert_amount`, `missing_count`; SPA `LiveValuesStore`, `marketAgeLabel`, `sb-market-value`, `sb-incomplete-note`, `sb-market-refresh`.

### Config fields (V204-3; `swingbot/config.py`, group `"Data Sources"`, all hot-reloadable)

| Key | Type | Default | Range |
|---|---|---|---|
| `ADMIN_SNAPSHOT_REGULAR_S` | number | 300 | 60–3600 |
| `ADMIN_SNAPSHOT_EXTENDED_S` | number | 900 | 60–7200 |
| `ADMIN_SNAPSHOT_CLOSED_S` | number | 3600 | 300–21600 |
| `ADMIN_SNAPSHOT_BUDGET_S` | number | 90 | 10–600 |
| `ADMIN_STALE_SNAPSHOT_REGULAR_S` | number | 600 | 60–3600 |
| `ADMIN_STALE_SNAPSHOT_EXTENDED_S` | number | 1800 | 300–7200 |

### Contract module additions (V204-3; `swingbot/core/marketdata/shared/admin_refresh.py`)

- `stale_after_s("snapshot", state)`: regular and extended map to the two `ADMIN_STALE_SNAPSHOT_*` fields; `closed` → `None` (the closed rule is "built before `last_regular_close`, or `stale_inputs`", applied by the door and the SPA). `"price"` is unchanged.
- `snapshot_cadence_s(state: str) -> float`: the three `ADMIN_SNAPSHOT_*_S` cadence fields.
- `snapshot_mark_timeout_s() -> float` = `ADMIN_SNAPSHOT_BUDGET_S + 30`.
- `SNAPSHOT_RISK = "risk"`, `SNAPSHOT_ANALYTICS = "analytics.snapshot"`.
- `performance_key(ledger: str) -> str` → `"analytics.performance:<ledger>"`; `equity_curve_key(ledger: str) -> str` → `"analytics.equity_curve:<ledger>"`; `calendar_key(month: str) -> str` → `"calendar.pnl:<YYYY-MM>"`. `<ledger>` ∈ `swingbot.core.analytics.scope.LEDGERS`; any other value raises `ValueError`.
- `is_snapshot_key(key: str) -> bool`: true exactly for the five shapes above.
- `snapshot_mark_key(key: str) -> str` → `"snapshot:<key>"`. It raises `ValueError` unless `is_snapshot_key(key)`. `snapshot_key_of(mark_key: str) -> str | None` is its inverse (`None` for non-snapshot marks).
- `calendar_months(now: datetime | None = None) -> tuple[str, str]`: current and previous month as `YYYY-MM`, taken from the America/New_York date.

### Table (V204-4; revision `v204_001`, `down_revision` = head at run time)

`admin_snapshots`: `key Text PK`, `computed_at TIMESTAMPTZ NOT NULL`, `stale_inputs Boolean NOT NULL server_default false`, `inputs JSONB NOT NULL`, plus `standard_columns()` (`doc JSONB` holds the payload, `updated_at`). Index `admin_snapshots_updated_idx (updated_at)`. It is not in `TABLE_CHANNELS`. The downgrade drops the index and then the table.

### Repository (V204-4; `swingbot/core/db/repositories/admin_snapshots.py`, connection handling as `equity_samples.py`)

- `AdminSnapshotRepository.put(key: str, doc: dict, inputs: dict, *, computed_at: datetime, stale_inputs: bool) -> bool`. It is `pg_insert(...).on_conflict_do_update(index_elements=["key"], set_=..., where=table.c.computed_at < excluded.computed_at)` and returns `True` when a row was written. An equal or older `computed_at` writes nothing.
- `read(key: str) -> dict | None` and `read_many(keys: Iterable[str]) -> dict[str, dict]`, each row `{key, doc, inputs, computed_at, stale_inputs, updated_at}`.
- `changed_since(since: datetime) -> list[dict]` (`key, computed_at, stale_inputs, updated_at`, where `updated_at > since`).
- `prune(prefix: str, keep: Iterable[str]) -> int`: deletes rows whose key starts with `prefix` and is not in `keep`.
- Accessor `admin_snapshot_repo() -> AdminSnapshotRepository`.

### Read-only bars (V204-5; `swingbot/core/marketdata/daily_readonly.py`)

- `class DailyCacheUnavailable(RuntimeError)`.
- `PERIOD_DAYS: dict[str, int]` and `trim(df, period: str)` move here from `freshness._PERIOD_DAYS`/`_trim`; `freshness` imports them.
- `@dataclass(frozen=True) ReadOnlyBars`: `frames: dict[str, pd.DataFrame]` (upper-case keys), `missing: dict[str, str]` (symbol → `"no_file"` \| `"spot_metal"` \| `"unreadable"` \| `"empty"` \| `"short:<rows>/<min_rows>"`), `fingerprints: dict[str, dict]` (`{"path": str, "mtime": float, "last_bar": "YYYY-MM-DD", "rows": int}` per read file).
- `read_cached_daily(tickers: Iterable[str], *, period: str = "2y", min_rows: int = 1) -> ReadOnlyBars`. It raises `DailyCacheUnavailable("daily bar cache <abs dir> is not mounted")` when the yfinance-basis cache directory is not a directory.
- `class RecordingReader`: `__init__(*, period: str = "2y", min_rows: int = 1)`; `__call__(symbols: list[str]) -> dict[str, pd.DataFrame]` (frames only, the shape `bars_reader` callers expect); `.seen -> ReadOnlyBars` (every call merged). `DailyCacheUnavailable` propagates.
- `freshness.page_daily(tickers, *, period="2y", read_only: bool = False) -> dict`: when `read_only`, returns `read_cached_daily(tickers, period=period).frames`. Otherwise it is today's code.
- `collect_portfolio_state(*, bars_reader: Callable[[list[str]], dict] | None = None) -> dict` and `_daily_frames(trades, bars_reader=None)`. With no reader, today's behaviour, which Discord's `commands/growth.py` keeps. With a reader, it never calls `data.get_daily_data`, and `DailyCacheUnavailable` propagates instead of being swallowed.

### Risk payload (V204-6; `swingbot/core/analytics/risk_payload.py`)

- Moved from `risk.py` with their bodies and log tags unchanged: `_position_risk`, `_positions`, `_heat_gap_block`, `_metric`, `_money_metric`, `_closed_history`, `_r_metrics`, `_closed_metrics`, `_asset_correlation`, `_market_values`, `_covered_distribution`, `_distribution_metrics`, and the private helpers they call. `_money_metric` converts through `fx_convert` (`fetch=not refresher_on()`).
- `@dataclass(frozen=True) RiskMetrics`: `metrics: dict, correlation: dict, availability: dict, bars_as_of: dict[str, str], missing_bars: dict[str, str]`.
- `metrics_and_correlation(bars_reader: Callable[[list[str]], dict], *, strict: bool = False) -> RiskMetrics` (today's `_risk_metrics_and_correlation` body). With `strict=True`, the exceptions `_asset_correlation` and `_distribution_metrics` swallow today are raised instead. With either value, correlation with fewer than 2 overlapping bars → `{"labels": [...], "values": null, "reason": "insufficient_overlap"}`, and beta with zero benchmark variance → `null` plus `availability["beta_spy"] = "zero_variance"`.
- `market_body(state: dict, result: RiskMetrics) -> dict` builds keys `heat, availability` (with no `killswitch`), `positions, sector_heat, unmapped_count, clusters, throttle, metrics, correlation`.
- `empty_body() -> dict` has every `market_body` key with empty values (`None`/`0`/`{}`, `correlation = {"labels": [], "values": []}`).
- `risk.py` keeps `_risk_bars` (which passes `read_only=refresher_on()`), `_cached`, `_fresh_kill`, `_scan_health`, and these compat names: `_risk_metrics() -> RiskMetrics` (`metrics_and_correlation(_risk_bars)`, looked up at call time), `_risk_metrics_and_correlation()` (the old tuple) and `_distribution_metrics(open_trades, benchmark, checked)`. The off-path JSON stays byte-identical to `golden/risk.json` after `normalise`.

### Snapshot builders (`swingbot/core/analytics/admin_snapshots.py`)

V204-7:
- `@dataclass(frozen=True) SnapshotResult`: `doc: dict, inputs: dict, stale_inputs: bool`.
- `build_inputs(*, computed_at: datetime, quotes: Mapping[str, Mapping] | None = None, fx: Mapping[str, Mapping] | None = None, bars: ReadOnlyBars | None = None, missing_quotes: Iterable[str] = (), missing_fx: Iterable[str] = (), ledger: str | None = None, trade_ids: Iterable = ()) -> dict` returns this **inputs shape**: `{"computed_at": iso, "oldest_quote_as_of": iso | None, "quotes": {SYM: {"price", "as_of"}}, "fx": {CCY: {"rate", "as_of"}}, "oldest_fx_as_of": iso | None, "bars_as_of": {"per_symbol": {SYM: "YYYY-MM-DD"}, "oldest": str | None, "newest": str | None}, "bar_files": {SYM: fingerprint}, "missing": {"quotes": [sorted], "fx": [sorted], "bars": {SYM: reason}}, "ledger": str | None, "trade_ids": [in order], "thresholds": {"stale_snapshot_regular_s", "stale_snapshot_extended_s", "stale_price_regular_s", "stale_price_extended_s"}, "code_version": VERSION.json "bot"}`.
- `expected_bar_date(now: datetime | None = None) -> date` and `stale_inputs_for(per_symbol: Mapping[str, str], now: datetime | None = None) -> bool`. The latter excludes spot metals and is `False` when nothing is left.
- `build_risk() -> SnapshotResult`. It uses `RecordingReader(min_rows=<the risk metric window>)`, `collect_portfolio_state(bars_reader=reader)`, `metrics_and_correlation(reader, strict=True)` and `market_body`. Its quote inputs are empty (brief correction). FX inputs come from `fx.quote_currency_code(t, fetch=False)` and `fx.fx_rate(..., refresh=False)`. `trade_ids` are the open trade ids.

V204-8:
- `SNAPSHOT_ROUTES: frozenset[str]`, a subset of `{"analytics.performance", "analytics.equity_curve", "calendar.pnl"}`, set from V204-2's verdicts and naming the routes whose default view is snapshotted.
- `build_analytics_snapshot() -> SnapshotResult` (`doc = snapshots.compute_snapshot()`; it never writes `analytics_snapshot.json`); `build_performance(ledger: str)`, `build_equity_curve(ledger: str)`, `build_calendar(month: str)`, each `-> SnapshotResult` and each the moved route body function for the default scope.
- `builders(now: datetime | None = None) -> dict[str, Callable[[], SnapshotResult]]`, in order: `risk`, `analytics.snapshot`, then per ledger in `scope.LEDGERS` the performance and equity-curve keys whose route is in `SNAPSHOT_ROUTES`, then `calendar_key(m)` for both `calendar_months(now)` when `"calendar.pnl"` is in it.
- `snapshots.compute_snapshot() -> dict`: `refresh_snapshot`'s gather + `build_snapshot`, raising. `refresh_snapshot()` becomes `save_snapshot(compute_snapshot())` inside today's `try/except`, so the file and its Discord readers are unchanged.
- `page_bodies.py` (created only for routes marked `snapshot`) holds `performance_body(scope) -> dict`, `equity_curve_body(scope) -> dict`, `calendar_body(month: str, filters) -> dict`, moved unchanged from the routes, which call them.

### Snapshot job (`swingbot/refresher/snapshot_job.py`)

V204-9:
- `class SnapshotWorker`: `__init__(*, builders_fn=admin_snapshots.builders, repo_fn=admin_snapshot_repo, marks_fn=refresh_mark_repo, publish=notify.publish, budget_fn=lambda: config.ADMIN_SNAPSHOT_BUDGET_S, clock=None)`. Methods: `submit(keys: Iterable[str]) -> list[str]` (non-blocking; returns the keys accepted, skipping pending, building and abandoned-but-alive keys); `start() -> None`; `stop(timeout: float = 5.0) -> None`; `run_batch(keys: list[str]) -> list[str]`, the synchronous test seam that returns the keys landed.
- `drain_landed() -> list[str]`: keys landed since the last call.
- Per key, `run_batch` re-marks (`timeout_s=snapshot_mark_timeout_s()`, no publish), then runs build + `put` in a daemon thread `snapshot-build-<key>` and joins for the budget. On success it clears the mark. On error it clears the mark with `error=f"{type(exc).__name__}: {exc}"` and keeps the previous row. On overrun it clears the mark with `error="budget exceeded after <N>s"` and holds the key in `abandoned` until its thread ends. After the batch, it calls `publish("market")` once if anything landed or errored, guarded so it never raises.

V204-10:
- `due_keys(now: datetime, last_runs: Mapping[str, datetime], *, session: str, builder_keys: Sequence[str], trades_changed: bool, scan_completed: bool, queued: Iterable[str]) -> list[str]`. A key is due when it is absent from `last_runs`, when `now - last_runs[k] >= snapshot_cadence_s(session)`, or when `trades_changed or scan_completed`. A queued key that has a builder is appended if not already due. A queued key without one is dropped.
- `snapshot_step(ctx: CycleContext) -> None` is appended to `loop.STEPS` after `quotes.fx_step`. It computes the due keys, marks the accepted ones (`timeout_s=snapshot_mark_timeout_s()`), sets `ctx.report.changed = True`, calls `worker().submit(...)`, puts `drain_landed()` into `ctx.report.snapshots_written`, and prunes `calendar.pnl:` rows outside `calendar_months(ctx.now)`. It never builds and never publishes.
- `worker() -> SnapshotWorker`: the process singleton, started by `__main__.main()` before `run_forever` and stopped after it.
- `_trades_fingerprint() -> tuple | None` (`SELECT count(*), max(updated_at) FROM trades`; `None` on error).

### Request-path door additions (V204-11; `swingbot/admin/market_values.py`)

- `read_snapshot(key: str, *, now: datetime | None = None) -> dict` always returns `{"key", "doc": dict | None, "inputs": dict | None, "computed_at": str | None, "stale_inputs": bool, "refreshing": bool, "error": str | None}`. It never builds. An absent row gives `doc: None, refreshing: True` and is enqueued at `PRIORITY_MISSING`. A row that is stale and not in flight is enqueued at `PRIORITY_MISSING`. Stale means older than `stale_after_s("snapshot", state)`, or, when closed, `computed_at < last_regular_close`. `kinds.is_fresh_request()` → enqueued at `PRIORITY_FRESH_HINT`.
- `snapshot_meta(snap: dict, *, extra_missing: int = 0) -> dict` returns a MarketMeta with `source: "snapshot"`. `as_of` is the oldest of `oldest_quote_as_of`/`oldest_fx_as_of`, else `computed_at`. It also sets `computed_at`, `stale_inputs`, `refreshing` and `error`. `missing_count` counts the unique symbols across `missing.quotes`, `missing.fx` and the keys of `missing.bars`, plus `extra_missing`. `stale_count` is `0`.
- `request_refresh(symbols, *, snapshots: Iterable[str] = (), priority: int = PRIORITY_USER) -> int`. Snapshot keys are validated with `is_snapshot_key` (`ValueError`) and enqueued as `QUEUE_KIND_SNAPSHOT`.

### Endpoints (V204-11)

- `GET /api/v1/market/updates` gains `"snapshots": [{"key", "computed_at", "stale_inputs", "refreshing", "error"}]`, holding the keys whose row or `snapshot:` mark changed since `since` (empty without `since`), and `status.stale_snapshot_s: float | None`.
- `POST /api/v1/market/refresh` accepts `{"symbols": [str], "snapshots": [str]}`. Either list may be empty, but not both. A non-list `snapshots`, a non-string item or an unknown key → 400 `invalid`. Success → 202 `{"queued": int}`.

### Risk body additions (V204-12; on and off paths alike)

`market_meta: MarketMeta`; `computed_at: str | None`; `bars_meta: {"per_symbol": {SYM: "YYYY-MM-DD"}, "oldest": str | None, "newest": str | None, "stale_inputs": bool, "missing": [{"symbol", "reason"}]}`; `fx_meta: {"as_of": str | None, "missing": [str]}`; `lower_bound: [str]`, the dotted body paths computed without at least one position (subset of `"metrics.closed"`, `"metrics.distribution"`, `"correlation"`, `"clusters"`); `account: {"balance": float | None, "currency": str}` where the payload already has the balance. On: `doc` from `read_snapshot("risk")` (else `empty_body()`), plus live `killswitch` and `scan_health`. Off: today's code plus these keys computed from the request's own inputs.

### SPA contract (V204-15; `frontend/src/app`)

- `api/models.ts`: `SnapshotUpdate {key; computed_at; stale_inputs; refreshing; error}`; `MarketUpdates.snapshots: SnapshotUpdate[]`; `MarketStatus.stale_snapshot_s: number | null`; `RiskBarsMeta`, `RiskFxMeta`; `Risk` gains optional `market_meta`, `computed_at`, `bars_meta`, `fx_meta`, `lower_bound`, `account`; `EquitySeries.market_meta?`; the Analytics snapshot/performance/equity-curve and Calendar bodies gain `market_meta?`.
- `ApiClient.refreshMarket(body: {symbols: string[]; snapshots?: string[]})`.
- `LiveValuesStore.snapshot(key: string): Signal<SnapshotUpdate | null>`; `requestRefresh(symbols: string[], snapshots: string[] = [])` marks those keys refreshing locally at once.
- `marketAgeLabel(asOf, nowMs, status, opts?: {kind?: 'price' | 'snapshot'; staleInputs?: boolean; computedAt?: string | null})`. For a snapshot, `staleInputs` makes it stale in every state. Regular and extended use `status.stale_snapshot_s`. Closed is stale when `computedAt < status.last_close_at`, and otherwise reads `as of last close · Ddd HH:MM ET`. Stalled still wins.
- `sb-market-value` gains inputs `kind: 'price' | 'snapshot'` (default `'price'`), `staleInputs: boolean` (default `false`) and `computedAt: string | null`.
- `sb-market-refresh` gains input `snapshots: string[]` (default `[]`).
- `stores/snapshot-follow.ts`: `followSnapshot(key: () => string | null, loadedAt: () => string | null, reload: () => void): EffectRef` calls `reload()` once per `live.snapshot(key())()?.computed_at` later than `loadedAt()`. `snapshotMeta(meta: MarketMeta | null | undefined, live: SnapshotUpdate | null): MarketMeta | null` returns `meta` with `refreshing ||= live.refreshing` and `error ??= live.error`.
- `ui/lower-bound.ts`: `lowerBoundLabel(value: string, missing: number): string | null` → `≥ <value>, <N> position unpriced` / `positions unpriced`, or `null` at 0.
- `ui/pnl-basis.ts`: `PNL_BASIS_LABEL = 'pre-tax, before modelled frictions'`.
- Snapshot keys the stores follow: `risk`, `analytics.snapshot` (sparkline), `analytics.performance:<ledger>` and `analytics.equity_curve:<ledger>` (default view only, `<ledger>` = the store's `ledger` scope value), `calendar.pnl:<YYYY-MM>` (the month shown). A key with no snapshot never updates, so its page shows its request-time `market_meta` only.

## Out of scope

- Discord commands, `analytics_snapshot.json` (kept, pinned by V204-8's parity test), the scan, plan building, backtests and the OHLCV caches.
- The ~14 other Analytics routes (`/analytics/by-dimension`, `/heat-grid`, `/journal`, …) and `/calendar/pnl/day*`. They are not snapshotted and keep today's request path. The page-load test covers only the endpoints the Risk, Analytics overview and Calendar pages call on load.
- New Risk metrics (losing streak, concentration view): a later Risk-page spec (spec § Panel review).
