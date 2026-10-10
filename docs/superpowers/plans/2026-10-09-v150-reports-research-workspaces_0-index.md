# v150 Reports and Research workspaces: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V150-4` or `grep -n "^### Task V150-4:" -A 400 docs/superpowers/plans/2026-10-09-v150-reports-research-workspaces_*.md`.

**Bump:** ui minor
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v150-reports-research-workspaces-design.md`](../specs/2026-10-09-v150-reports-research-workspaces-design.md)

**Goal:** Replace the two placeholder workspaces with real pages. **Research** is a read-only browser of the pre-registration ledger plus the strategy registry. **Reports** shows the v146 expectancy-attribution and v147 gate-counterfactual results, one tab each, without recomputing a single figure.

**Architecture:** Two thin Flask modules under `swingbot/admin/api_v1/` (`research.py`, `reports.py`) wrap existing loaders and never reshape their dicts. On the SPA side each workspace follows the Versions pattern: a route-scoped signal store resolved by `resolveRoute`, and a component that renders the store. All knowledge of the v146/v147 field names sits in two places, `api/models.ts` and the pure view-model functions in `stores/reports.store.ts`; the tab components render view models only, so a renamed wire field is a two-file change. No new chart component; only primitives already in `frontend/src/app/ui/`.

**Tech Stack:** Python 3.11, Flask, pytest; Angular 21 (zoneless, signals), `@ngrx/signals`, Vitest.

## Blocked tasks: read this before dispatching anything

`swingbot/core/analytics/expectancy_attribution.py` (v146) and `swingbot/core/analytics/gate_counterfactual_report.py` (v147) **do not exist on `main` as of 2026-10-09**, and neither spec has a plan yet.

| Tasks | State | Unblocks when |
|---|---|---|
| V150-1, V150-2, V150-4, V150-6, V150-8 (Research, the deploy doc) | **Ready now** | — |
| V150-3, V150-5, V150-7, V150-9, V150-10, V150-11 (Reports) | **Blocked** | v146 and v147 are merged to `main` and the four cross-spec requirements hold (check below) |
| V150-12, V150-13 (route rewiring, full suites) | Blocked | every task above is done |

The gate, run from the worktree after rebasing it onto `main`:

```bash
python - <<'EOF'
from swingbot.core.analytics import expectancy_attribution as a
from swingbot.core.analytics import gate_counterfactual_report as g
print("load_latest:", callable(a.load_latest), " load_report:", callable(g.load_report))
EOF
git grep -n "os.replace" -- swingbot/core/analytics/expectancy_attribution.py swingbot/core/analytics/gate_counterfactual_report.py
git grep -n "verdict_of_record\|looks" -- swingbot/core/analytics/expectancy_attribution.py | head
git grep -n "verdict_of_record" -- swingbot/core/analytics/gate_counterfactual_report.py | head
```

Expected: both loaders are callable, both writers use `os.replace`, and `verdict_of_record` appears in both modules (`looks` in v146's). If the loaders live in separate light modules instead (spec § Cross-spec requirements, 2), substitute those module paths here and in V150-3. Anything missing is a v146/v147 defect: stop and report it; do not work around it in v150.

**The Research tasks can be implemented and reviewed first.** They are not merged alone: `Bump: ui minor` is one release, and V150-12 rewires both routes together.

## Global Constraints

- **The page never computes or recomputes a figure, a floor or a verdict.** Whether a bucket is below the floor comes from v146's `thin` flag; whether a gate cell is below it comes from v147's `WAITING` verdict. No `n < 30` test anywhere in the SPA or the endpoints.
- **The endpoint never reshapes a loader's dict.** `result` is the loader's return value, unchanged.
- **Field names are v146's and v147's.** If a name differs from what this plan assumes, rename in v150 (`api/models.ts`, the fixtures, `reports.store.ts`), never in the report modules.
- The verdict of record is THE verdict, shown with its date and N. The latest reading sits in a separate block headed exactly `Latest reading — descriptive` and is never styled as a verdict.
- Below the floor: `WAITING` and an N progress figure only. No muted, provisional or greyed verdict badge, no CI, no difference.
- Exactly one `PREDICTIVE` / `WEAK` / `NOT PREDICTIVE` chip on the Expectancy-attribution tab.
- Caption on every figure table, verbatim: `R units, net of frictions as v146/v147 compute them, pre-tax.`
- Fixed footer on both workspaces, verbatim: `Historical measurement on paper trades; not a forecast or advice.`
- A verdict is worded as a historical measurement, never as an instruction.
- The "screen candidate" marker appears only where the server's BH `q < 0.10`. The page compares the `q` it is given against the constant `SCREEN_CANDIDATE_Q = 0.10`; it computes no q-value.
- The tab is named **Expectancy attribution** (the Analytics workspace already has an "Attribution" tab).
- Read-only: no endpoint or control writes to the ledger or to `data/reports/`.
- No new endpoint for the strategy registry and no change to `_registry_rows`.
- No Postgres table and no Alembic revision.
- Only primitives already in `frontend/src/app/ui/`. No new chart component.
- No in-page `<h1>` (the top bar owns the title), `sb-panel` for cards, `sb-toolbar` for filters, `auto-fit` grids, and a freshness marker on every page that fetches (`workspace-consistency.spec.ts` enforces all five).
- Every Python function ends below cyclomatic complexity 15 (`python -m radon cc -s -n C <files>`).
- Per-task verification is the narrow run: `python scripts/dev/testrun.py file <test>`, or `cd frontend && npm test -- --include <spec> --watch=false`. Both full suites run once, in V150-13.

## Deviations from the spec, found while writing this plan

1. **The "fresh interpreter" import test is replaced.** The spec's Testing section asks that importing `swingbot.admin.api_v1.reports` in a fresh interpreter leaves `swingbot.core.backtesting` out of `sys.modules`. That cannot be tested as written: an `api_v1` endpoint module is not importable on its own (`.auth` imports `swingbot.admin.app`, whose body calls `register()`, which imports every endpoint module: a circular import), and `import swingbot.admin.app` already loads `pandas`, `numpy` and `swingbot.core.backtesting` today (measured 2026-10-09). V150-3 pins the property that is checkable and still useful: `reports.py` has **no module-level import from `swingbot.core`**, so the report modules are imported only when a report endpoint is called. The light-loader requirement on v146/v147 keeps its own tests in those plans.
2. **Multi-select verdict chips are hand-built from `button[sb-button variant="chip"]`.** The spec asks for a multi-select chip set; the shared `sb-filter-chips` is single-select (`selected: string | null`). The buttons sit inside one `slot="verdict"` element of `sb-toolbar`, so the toolbar rule still holds.
3. **`record_exists` resolves against the repo root the ledger lives in** (`LEDGER_PATH.parents[3]`), not a second configured root, so the page and the ledger can never disagree about which tree they describe.
4. **The gate table has no "Latest reading — descriptive" column group.** `sb-data-table` has no column groups and this plan adds no primitive, so the three latest-reading columns are headed `Latest: …` and a caption above the table carries the words `Latest reading — descriptive` verbatim.
5. **Filter changes do not refetch.** Research's filters live in the query string, so every filter change is a navigation and the resolver runs each time; it re-applies the filters and fetches only once per visit (`ResearchStore.ensureLoaded`).
6. **The `N 17 / 30` progress figure uses a display constant** (`FLOOR_N_DISPLAY = 30`, v147 spec `:311`). Whether a cell is below the floor is still decided only by v147 (`verdict_of_record` is null); the constant is text, never a test.
7. **The freshness marker on Reports is never flagged stale.** `sb-freshness` defaults to "stale after 15 minutes", which is wrong for a report with no cadence; the page shows the timestamp and leaves the judgement to the reader.

## Assumed wire shapes (pinned by V150-5 before any Reports UI task starts)

The v146 and v147 specs fix the top-level shape and describe the rest in prose. The Reports tasks are written against the names below. **V150-5 replaces this table's assumptions with the real names from the merged modules**, and its fixtures are what every later Reports task tests against.

v146, `load_latest()` (v146 spec `:297-301`; top-level names are fixed, inner names are assumed):

```
{ generated_at: str, verdict: str, verdict_of_record: {verdict, date, n}, looks: int, seed: int,
  populations: { live: Population | null, train: Population | null } }
Population = { window: str | null, n: int,
  monotonicity: Monotonicity,
  factors: [ { key: str, n: int, delta: float | null, ci_low, ci_high, q: float | null } ],
  buckets: { <dimension>: [ { label: str, n: int, win_rate, exp_r, thin: bool, q: float | null } ] },
  splits: { direction: { <name>: Monotonicity }, horizon: { <name>: Monotonicity } } }
Monotonicity = { n: int, spearman_rho, tercile_spread, ci_low, ci_high, inverted: bool }
```

v147, `load_report()` (v147 spec `:266-338`; assumed throughout):

```
{ generated_at: str, live_window: str | null,
  cells: [ { gate: str, population: "live" | "train", verdict: str, n: int,
             verdict_of_record: {verdict, date, n} | null,
             latest: { difference, ci_low, ci_high, q } | null,
             in_sample: bool, note: str | null } ],
  rows:  [ { gate, reason, population, blocked_n, no_plan_n, fill_rate,
             blocked_exp_r, blocked_win_rate, taken_exp_r, taken_win_rate,
             near_miss_n, near_miss_exp_r, rest_n, rest_exp_r,
             dollar_risk: float | null, over_cap: bool, in_sample: bool } ] }
```

`note` carries the two fixed non-verdict states the spec names: `"no TRAIN population"` (RS) and `"no verdict — no-plan"` (`no_qualifying_target`). If v147 does not persist them, V150-7's `gatesView` derives them from the gate name, and V150-5 records which.

## Where to work

- **Branch and worktree:** `2026-10-09-v150-reports-research-workspaces` at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v150-reports-research-workspaces`. V150-1 Step 0 creates it with the `worktree-lifecycle` skill. Every task runs there. Name the worktree in every subagent dispatch, and after each task run `git -C E:/Documents/Private/Projects/Discord-Bot status --short` to confirm the main tree is unchanged.
- **Skills:** `frontend-design:frontend-design` is not needed (existing primitives, existing layout patterns). `worktree-lifecycle` before creating, rebasing, merging and removing the worktree.
- **Production:** nothing in this plan changes the Hetzner VM. V150-2 only documents a run path. Running the reports there is the partner's call after merge, through `mirror-prod`.
- **Close-out:** the spec carries `Panel: staff-engineer, financial-advisor, quant-researcher`, so `/panel` reviews `main...<branch>` before `/close-out`.

## Parts

| Part | File | Tasks | Content |
|---|---|---|---|
| 0 | `_0-index` (this file) | none | Header, blocked tasks, constraints, deviations, assumed wire shapes, parallelisation, file map |
| 1 | [`_1-endpoints-models`](2026-10-09-v150-reports-research-workspaces_1-endpoints-models.md) | V150-1 .. V150-5 | Both endpoints, the deploy doc, the TypeScript wire models, the shared report fixtures |
| 2 | [`_2-stores`](2026-10-09-v150-reports-research-workspaces_2-stores.md) | V150-6, V150-7 | `ResearchStore`; `ReportsStore` and the two view models |
| 3 | [`_3-research-and-report-tabs`](2026-10-09-v150-reports-research-workspaces_3-research-and-report-tabs.md) | V150-8 .. V150-10 | The Research page, the Expectancy-attribution tab, the Gate-counterfactual tab |
| 4 | [`_4-shell-routes-close-out`](2026-10-09-v150-reports-research-workspaces_4-shell-routes-close-out.md) | V150-11 .. V150-13 | The Reports shell, route rewiring and the stub's deletion, the full suites |

## File map

| File | Task | Responsibility |
|---|---|---|
| `swingbot/admin/api_v1/research.py` (new) | V150-1 | `GET /research/ledger`: rows + q + record flags + vocabularies |
| `tests/admin/test_api_v1_research.py` (new) | V150-1 | Its contract |
| `swingbot/admin/api_v1/__init__.py` | V150-1, V150-3 | One name each added to `register()`'s import list |
| `scripts/dev/select_tests.py` | V150-1 | The ledger row routes to the new test |
| `docs/deploy/DEPLOY_HETZNER.md` | V150-2 | Where the reports run, and the TRAIN-input upload |
| `swingbot/admin/api_v1/reports.py` (new) | V150-3 | The two report envelopes |
| `tests/admin/test_api_v1_reports.py` (new) | V150-3 | Their contract |
| `frontend/src/app/api/models.ts`, `api/api-client.ts` | V150-4, V150-5 | Wire types and three client methods |
| `frontend/src/app/stores/analytics.store.ts` | V150-4 | `StrategyRow` moves to `api/models.ts`, re-exported |
| `frontend/src/app/testing/report-fixtures.ts` (new) | V150-5 | One fixture per report, shared by every Reports spec |
| `frontend/src/app/stores/research.store.ts` (+ spec) | V150-6 | Ledger + registry, filters, sort, paging |
| `frontend/src/app/stores/reports.store.ts` (+ spec) | V150-7 | Per-tab fetch and the two view models |
| `frontend/src/app/workspaces/research/research.ts` (+ spec), `research.routes.ts` | V150-8 | The Research page |
| `frontend/src/app/workspaces/reports/attribution-tab.ts` (+ spec) | V150-9 | Expectancy attribution |
| `frontend/src/app/workspaces/reports/gates-tab.ts` (+ spec) | V150-10 | Gate counterfactual |
| `frontend/src/app/workspaces/reports/reports.ts` (+ spec), `reports.routes.ts` | V150-11 | Tab bar, freshness, not-run, footer |
| `frontend/src/app/app.routes.ts`, `app.routes.spec.ts`, `workspaces/stubs/` (deleted) | V150-12 | Rewiring; the placeholder goes |

## Parallelisation

- **Blocked before start:** V150-3, V150-5, V150-7, V150-9, V150-10, V150-11 wait for the gate above. Nothing else does.
- **Group A (parallel, ready now):** V150-1 (`research.py`, its test, `select_tests.py`, one name in `__init__.py`), V150-2 (`DEPLOY_HETZNER.md`), V150-4 (`models.ts`, `api-client.ts`, `analytics.store.ts`). Disjoint files. V150-4 types the ledger response from the shape this plan fixes in V150-1's Interfaces block, so it does not need V150-1's code.
- **Sequential:**
  - V150-3 after V150-1: both add a name to the same import statement in `api_v1/__init__.py`.
  - V150-5 after V150-4: both edit `api/models.ts` and `api/api-client.ts`. V150-5 also needs V150-3's envelope.
  - V150-6 after V150-4 (consumes `ResearchLedger`, `StrategyRow`, `ApiClient.researchLedger`). V150-7 after V150-5 (consumes the report models and fixtures).
  - V150-8 after V150-6. V150-9 after V150-7. V150-10 after V150-9: it imports `formatR` and `formatInterval` from `attribution-tab.ts`.
  - V150-11 after V150-9 and V150-10 (the shell imports both tab components) and after V150-8 (its spec imports Research's `DISCLAIMER` to assert the two footers are one string).
- **Group B (parallel):** V150-6 with V150-7 (one store file each). V150-8 with the chain V150-9 → V150-10 (disjoint directories).
- **Sequential:** V150-12 after V150-8 and V150-11 (it points both routes at the new `*.routes.ts` and deletes `stubs/`, which both still import until then).
- **Last:** V150-13, both full suites once.
