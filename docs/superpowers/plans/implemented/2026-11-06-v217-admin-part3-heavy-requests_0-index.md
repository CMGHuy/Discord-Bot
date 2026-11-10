# v217 — Admin Part 3: fewer heavy requests per page (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md) (§ Plan 2 — v205 Part 3 plus one boot merge; § Error handling, § Testing, § Rollout and rollback). P3 authority: [v205 — Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md) § Part 3 — fewer heavy requests per page (P3-a, P3-b), § Testing, § Rollout and rollback.

## Goal

The admin is one gunicorn worker, so every request a page sends waits
behind every other request on the box. v206 Plan 1 removed the scan-driven
polling. What is left on the two busiest pages is duplicated heavy work.
The Dashboard opened on a wider scope (1W, 1M, All, a range) sends
`/dashboard` twice: once for the scope and once with `mode=today` for the
"today" figures. Each call loads every trade and rebuilds the plan rows.
The calendar day page sends `/calendar/pnl/day`, the month grid, and
sometimes a second month grid only to find the previous or next trading day
across a month edge.

Once this plan ships, a wider-scope `/dashboard` (modes `all` and `range`)
carries a `today` block (`realized` and `lifecycle` computed with mode
`today` from the same loaded trades, no second `get_trades`). The SPA lands
it from the scoped response and sends the `today` request only when the
block is missing, which happens on an older backend after a rollback.
`/calendar/pnl/day` carries `prev_day` / `next_day`, the nearest trading
days under the same strategy/horizon filter across all history (`null` at
either end). The SPA uses them and asks for the neighbouring month only
when the fields are missing. That is a deliberate behaviour change: today
the SPA looks one month either way, so a gap longer than a month shows no
neighbour, and the server field finds it. A 404 empty day has no body to
carry the fields, so it keeps the month grid plus `loadEdge` path.

v206 Plan 2 also asks whether the Dashboard's boot `/trades` calls can
merge. There are two: the activity feed (`dashboard.ts`, newest 20 of
every status) and the positions table (`status=ACTIVE`, paged 10/5/saved,
server pagination, its own refetch). The brief counted a third,
exposure-by-horizon (`status=open&per_page=200`), but that panel has not
been mounted since `d9fef9eb` (2026-09-12); V217-1 pins its absence. The
feed is not a superset of the Open tab, because an ACTIVE row older than
the 20 newest is missing from it. So the first task is an evidence task:
specs that pin the two boot calls and why the feed-to-positions merge
fails, plus a population comparison showing the unmounted
exposure-by-horizon panel could not share the positions table's rows
either. It writes the outcome into the v206 spec and adds no merge code;
deleting the dead panel is a follow-up outside v217.

The plan leaves `?mode=today`, the 1D scope, `mode=active`, the month grid
call, the sparklines, the SQL, the worker count and every other field
alone. The `dashboard` (mode `active`) and `dashboard_today` goldens stay
byte-identical. The `calendar_day` golden gains exactly the two new fields.
Success is measured by the committed browser probe
(`scripts/ops/admin_browser_probe.py --date 2026-11-03`) run during a scan
(label `scan`). A wider-scope Dashboard boot sends one `/dashboard` instead
of two, a day page in the middle of a month sends no extra month request,
and the endpoint table is recorded in the v206 spec's `## Results` next to
Plan 1's numbers.

## Architecture

Backend: one new helper in each route module, so the views gain at most one
call each. `swingbot/admin/api_v1/dashboard.py` gets `_today_block(all_raw)`,
which reuses `_realized_parts`, `_realized` and `_lifecycle_counts` with mode
`"today"`. `dashboard()` adds `"today"` to its JSON only when
`mode in ("all", "range")`. `swingbot/core/analytics/pnl_calendar.py` gets a
pure `adjacent_trading_days(rows, date)` over the already filtered
all-history rows, and `calendar_pnl_day()` spreads its result into the
response. Frontend: the models gain optional fields. `dashboard.store.ts`
lands `data.today` through the existing `landToday` stamp rules and falls
back to `loadToday()` only when the block is `undefined`.
`calendar-day.store.ts` lands `prev_day`/`next_day` and runs `loadEdge` only
for a field that is `undefined` (decided after both `forkJoin` members
answer). Its 404 path is unchanged.

**Tech stack:** Python 3.11, Flask (`api_v1` blueprint), pytest (suites
`admin`, `admin-perf`, `analytics`); Angular with signal stores
(`@ngrx/signals`), Vitest via `frontend/scripts/ng-test.mjs`.

## Global Constraints

- `today` appears in `/dashboard` **only for modes `all` and `range`**; never for `active` or `today`. `tests/admin_perf/golden/dashboard.json` and `dashboard_today.json` stay byte-identical (pinned by the existing golden test and by a new absence test).
- `today` block shape is exactly `{"realized": <same shape as top-level realized>, "lifecycle": <same shape as top-level lifecycle>}`. It equals `GET /api/v1/dashboard?mode=today`'s `realized` and `lifecycle` on the same book. A zero-close day is a measured zero (`n: 0`, amounts `null`), never an absent block.
- The today block reuses the request's `all_raw`. No second `TradeLog().get_trades`, and the `dashboard` SQL budget in `tests/admin_perf/test_budgets.py` (12 statements, 4 list_all) does not rise, for mode `all` too.
- `prev_day` / `next_day` are `YYYY-MM-DD` strings or `null`, always present on a 200 `/calendar/pnl/day`, under the same `strategy`/`horizon` filter, across all history. 404 bodies are unchanged.
- `tests/admin_perf/golden/calendar_day.json` is hand-edited in the same commit as the code: `"prev_day": "2026-11-02"`, `"next_day": null` (golden book days 2026-10-29, 2026-11-02, 2026-11-03; golden date 2026-11-03). Its other bytes do not change. `record_golden` never overwrites.
- Frontend: "absent" means `undefined` (older backend) → fallback request. `null` means "no neighbour / measured", never a fetch.
- Every function written or changed stays at cyclomatic complexity < 15 (`scripts/dev/complexity_gate.py`). `dashboard()` and `calendar_pnl_day()` gain one call each at most.
- Every task ships its own tests. Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`, `node frontend/scripts/ng-test.mjs frontend --include <spec>`). **No task runs the full suite; CI does after the push.**
- Tests that reach Postgres (suites `admin`, `admin-perf`) run `/replicate-prod-db` first, once per session, against the shared `swing-db` container (port 56789). Never a per-task database.
- No UI layout change: no template or style edits. The rendered Dashboard and calendar day pages are identical at mobile, tablet and desktop. V217-6's probe and the component specs are the check.
- Implementation runs in worktree `.claude/worktrees/2026-11-06-v217-admin-part3-heavy-requests` (branch of the same name). Nothing is committed on `main` except by V217-6's merge.
- Production is read-only except through the push-to-`main` → CI deploy (`docs/deploy/DEPLOY_HETZNER.md`). Any direct VM change follows `mirror-prod`. Credentials stay inside the probe, never echoed.

## Parallelisation

| Group | Tasks | Why this order |
|---|---|---|
| A | V217-1 | Evidence only. Edits `dashboard.spec.ts`, `exposure-by-horizon.spec.ts` and the v206 spec. No contract with any other task. Can run beside B/C. |
| B | V217-2, V217-3 | Disjoint files (`calendar.py` + `pnl_calendar.py` + calendar tests/golden vs `dashboard.py` + dashboard tests); may run in parallel. |
| C | V217-4 → V217-5 | Both modify `frontend/src/app/api/models.ts` (same file: sequential). V217-4 consumes V217-2's field names, V217-5 V217-3's block shape. Both are fixed in the ledger, and the specs mock HTTP, so C may start before B merges. |
| D | V217-6 | Sequential edge on everything: the release merges and deploys the whole branch. It also edits the v206 spec after V217-1 (same file: `## Results`). |

At most 2 implementers at once (`CLAUDE.md`). Suggested waves: (V217-1 ∥ V217-2), (V217-3 ∥ V217-4), V217-5, V217-5b, V217-6. V217-5 also edits `dashboard.spec.ts`, so it runs after V217-1.

## Task ledger

| Id | Title | Part | Model | Files created / modified | Symbols for later tasks |
|---|---|---|---|---|---|
| V217-1 | Boot `/trades` merge: evidence specs, record the verdict | 1 | sonnet | M `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`; M `frontend/src/app/workspaces/dashboard/panels/exposure-by-horizon.spec.ts`; M `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (`## Results` → new `### Plan 2 boot merge (V217-1)`) | spec heading `### Plan 2 boot merge (V217-1)` (V217-6 writes below it) |
| V217-2 | `/calendar/pnl/day` carries `prev_day` / `next_day` | 1 | sonnet | M `swingbot/core/analytics/pnl_calendar.py`; M `swingbot/admin/api_v1/calendar.py`; M `tests/analytics/test_pnl_calendar.py`; M `tests/admin/test_api_v1_calendar.py`; M `tests/admin_perf/golden/calendar_day.json` | `pnl_calendar.adjacent_trading_days(rows: list[dict], date: str) -> dict[str, str \| None]` returning `{"prev_day": ..., "next_day": ...}`; response keys `prev_day`, `next_day` |
| V217-3 | `/dashboard` carries `today` for modes `all`/`range` | 1 | sonnet | M `swingbot/admin/api_v1/dashboard.py`; M `tests/admin/test_api_v1_dashboard.py`; C `tests/admin_perf/test_today_block.py` | `dashboard._today_block(all_raw: list[dict]) -> dict` = `{"realized": dict, "lifecycle": dict}`; `dashboard._TODAY_BLOCK_MODES = ("all", "range")`; response key `today` |
| V217-4 | Calendar day store uses server neighbours, `loadEdge` only as fallback | 2 | sonnet | M `frontend/src/app/api/models.ts` (`CalendarDayTrades`); M `frontend/src/app/stores/calendar-day.store.ts`; M `frontend/src/app/stores/calendar-day.store.spec.ts` | `CalendarDayTrades.prev_day?: string \| null`, `CalendarDayTrades.next_day?: string \| null` |
| V217-5 | Dashboard store lands `today` from the scoped response | 2 | opus | M `frontend/src/app/api/models.ts` (`Dashboard`, new `DashboardToday`); M `frontend/src/app/stores/dashboard.store.ts`; M `frontend/src/app/stores/dashboard.store.spec.ts`; M `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (`todayFailedInPeriod` flushes the fallback `mode=today` request; after V217-1, same file) | `export interface DashboardToday { realized: Dashboard['realized']; lifecycle: Dashboard['lifecycle']; }`; `Dashboard.today?: DashboardToday`; store slice `todayData: DashboardToday \| null` (public `todayRealized`, `todayLifecycle`, `todayLoading`, `todayError` unchanged) |
| V217-5b | Dashboard store today block: the remaining pinning specs | 2 | sonnet | M `frontend/src/app/stores/dashboard.store.spec.ts` | — (spec-only; pins V217-5's rules) |
| V217-6 | Release, deploy, probe during a scan, Results | 2 | sonnet | M `VERSION.json`; M `swingbot/admin/version_history.json` (regenerated); M `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (`## Results` → new `### Plan 2 after (committed probe)`) | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | [`2026-11-06-v217-admin-part3-heavy-requests_1-backend.md`](2026-11-06-v217-admin-part3-heavy-requests_1-backend.md) | V217-1..V217-3 | Boot-merge evidence and verdict; the two server fields with pytest (admin, admin-perf, analytics) and the hand-edited golden |
| 2 | [`2026-11-06-v217-admin-part3-heavy-requests_2-frontend-and-release.md`](2026-11-06-v217-admin-part3-heavy-requests_2-frontend-and-release.md) | V217-4..V217-6 | The two stores with fallback specs (rewriting the always-fetch-today cases); release, deploy, scan probe, Results |

## Notes for part writers

- **V217-1** is short, with no merge code. Spec 1 (`dashboard.spec.ts`) asserts the boot's two `/trades` requests and their params (and that `sb-exposure-by-horizon` is not mounted), and that an ACTIVE row outside the feed's newest 20 renders in the positions table but is absent from the feed's rows. That is the recorded reason the merge fails. Spec 2 compares exposure-by-horizon (`status=open`, ACTIVE+PARTIAL, 200) with positions-table (`ACTIVE`, paged). Expected verdict: status sets and page sizes differ, so identical output cannot be asserted. Record "keep both" with these reasons in the v206 spec. If the evidence ever contradicts this, return `BLOCKED`. Do not write merge code.
- **V217-3** tests: `today` absent for modes `active` and `today`, present for `all` and a `range` window; it equals `?mode=today` for `realized` and `lifecycle` (`_today_iso()` / Berlin today); measured zero on a book with no closes today; empty book. In `test_today_block.py` (admin-perf, `golden_seed` + `frozen_clock`): mode `all` costs ≤ `BUDGETS["dashboard"]`, and `get_trades` runs once per request.
- **V217-5** rewrites the specs that encode always-fetch-today (`dashboard.store.spec.ts` ~L528-547, L554, L741, L764-800). New cases: a wider scope with `today` in the response sends one request and `todayRealized`/`todayLifecycle` land from it. Without `today`, the old second `mode=today` request goes out. 1D is unchanged. An older in-flight today fetch never overwrites a newer block (stamp rules). Keep the "keeps today when a wider preset is picked after 1D" behaviour.
- **V217-4** cases: fields present → `backend.expectNone` for the adjacent month; `null` at both ends → no month fetch and `prevDay`/`nextDay` null (unless the month grid has a neighbour, which wins as today); a gap longer than a month resolves from the server field; fields absent → today's `loadEdge` path (existing specs stay); 404 → empty state with working prev/next via `loadEdge`; the absent check runs after both `forkJoin` members answer, in either flush order.
- **V217-6** follows the shape of v206's `V206-13`: preconditions, narrow verification of every touched test file, two release commits plus regenerated `version_history.json`, a merge through `worktree-lifecycle`, a pipeline watch, a read-only check that production runs the new image (for example `curl` of `/calendar/pnl/day` keys via the admin container), waiting for a scan, a background probe (`--date 2026-11-03`, label `scan`), the credential-absence check, and a generated before/after table vs `v206-after`.
