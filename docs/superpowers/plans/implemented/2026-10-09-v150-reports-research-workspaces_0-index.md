# v150 Reports and Research workspaces: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V150-4` or `grep -n "^### Task V150-4:" -A 400 docs/superpowers/plans/2026-10-09-v150-reports-research-workspaces_*.md`.

**Bump:** ui minor
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v150-reports-research-workspaces-design.md`](../specs/2026-10-09-v150-reports-research-workspaces-design.md)

**Goal:** Replace the two placeholder workspaces with real pages. **Research** is a read-only browser of the pre-registration ledger plus the strategy registry. **Reports** shows the v146 expectancy-attribution and v147 gate-counterfactual results, one tab each, without recomputing a single figure.

**Architecture:** Two thin Flask modules under `swingbot/admin/api_v1/` (`research.py`, `reports.py`) wrap existing loaders and never reshape their dicts. On the SPA side each workspace follows the Versions pattern: a route-scoped signal store resolved by `resolveRoute`, and a component that renders the store. All knowledge of the v146/v147 field names sits in two places, `api/models.ts` and the pure view-model functions in `stores/reports.store.ts`; the tab components render view models only, so a renamed wire field is a two-file change. No new chart component; only primitives already in `frontend/src/app/ui/`.

**Tech Stack:** Python 3.11, Flask, pytest; Angular 21 (zoneless, signals), `@ngrx/signals`, Vitest.

## Blocked tasks: read this before dispatching anything

`swingbot/core/analytics/expectancy_attribution.py` (v146) and `swingbot/core/analytics/gate_counterfactual_report.py` (v147) **do not exist on `main` as of 2026-10-09**. v146 and v147 now have plans; their loaders live in `swingbot/core/infra/expectancy_attribution_store.py` (`load_latest`) and `swingbot/core/infra/gate_counterfactual_store.py` (`load_report`), re-exported by the analytics modules.

| Tasks | State | Unblocks when |
|---|---|---|
| V150-1, V150-2, V150-4, V150-6, V150-8 (Research, the deploy doc) | **Ready now** | — |
| V150-3, V150-5, V150-7, V150-9, V150-10, V150-11 (Reports) | **Blocked** | v146 and v147 are merged to `main` and the four cross-spec requirements hold (check below) |
| V150-12, V150-13 (route rewiring, full suites) | Blocked | every task above is done |

The gate, run from the worktree after rebasing it onto `main`:

```bash
python - <<'EOF'
from swingbot.core.infra import expectancy_attribution_store as a
from swingbot.core.infra import gate_counterfactual_store as g
print("load_latest:", callable(a.load_latest), " load_report:", callable(g.load_report))
EOF
git grep -n "os.replace" -- swingbot/core/infra/jsonio.py
git grep -n "atomic_write_json" -- swingbot/core/infra/expectancy_attribution_store.py swingbot/core/infra/gate_counterfactual_store.py
git grep -n "verdict_of_record\|looks" -- swingbot/core/analytics/expectancy_attribution.py | head
git grep -n "verdict_of_record" -- swingbot/core/analytics/gate_counterfactual_report.py | head
```

Expected: both loaders are callable, `jsonio.py` uses `os.replace` and both store modules write through `atomic_write_json`, and `verdict_of_record` appears in both analytics modules (`looks` in v146's). The loaders live in the light infra store modules (spec § Cross-spec requirements, 2), which V150-3 imports. Anything missing is a v146/v147 defect: stop and report it; do not work around it in v150.

**The Research tasks can be implemented and reviewed first.** They are not merged alone: `Bump: ui minor` is one release, and V150-12 rewires both routes together.

## Cross-plan coordination (audit 2026-10-10)

- **v146, v147 — V150-3 and the gate above:** import `load_latest` from `swingbot.core.infra.expectancy_attribution_store` and `load_report` from `swingbot.core.infra.gate_counterfactual_store`, never from `swingbot.core.analytics.*` (that package pulls pandas/numpy). Names verified against v146 V146-9 and v147 V147-8.
- **v151 — V150-5/V150-7:** the exported TS gate-counterfactual row type is `GateCounterfactualRow` (renamed from `GateRow`; `GateRowView` stays), because v151 defines its own `GateRow`.
- **v151 — V150-12:** `app.routes.spec.ts` readiness `expected` list: add this plan's paths to the current list, keeping entries other plans added (v151 V151-16 adds `'plans/:id'`); never paste a full literal.
- **v148 — V150-1/V150-3:** `api_v1/__init__.py` `register()` tuple: add this plan's names in alphabetical position, keeping names other plans added (v148 adds `ops_health`).
- **v148 swallowed-error ratchet:** if `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), follow the rule in v148's index § Cross-plan coordination (`docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md`). V150-3's `_envelope` handler re-raises (`raise ApiError(...) from exc`), so the ratchet does not count it; any new handler that swallows must follow that rule.
- **v149 complexity gate:** if `scripts/dev/complexity_gate.py` exists (v149 merged), follow the rule in v149's § Cross-plan coordination (`docs/superpowers/plans/2026-10-09-v149-hygiene-gates.md`).

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

## Wire shapes (pinned 2026-10-15 from 01d8aaae)

V150-5 read `expectancy_attribution.build_report` / `gate_counterfactual_report.build_report` and dumped one real result of each from the modules' own test populations. The TypeScript models in `frontend/src/app/api/models.ts` and the fixtures in `frontend/src/app/testing/report-fixtures.ts` are the authority; `report-fixtures.spec.ts` pins every key list below, so a fixture that drifts from the wire fails there. Every later Reports task tests against those fixtures. **Where a later task's code in parts 2-4 still uses an assumed name, use the real one** (the "Differences" lines say which).

v146, `load_latest()` (`swingbot/core/infra/expectancy_attribution_store.py`):

```
{ generated_at, verdict, verdict_of_record: {verdict, date, n}, looks, seed,
  provenance: {...},                               # filled by run(); {} from build_report alone
  populations: { live: Population | null, train: Population | null } }
Population = { window: {first_week, last_week}, n,
  monotonicity: Monotonicity,
  factors: [ {key, n, n_pos, n_zero, delta, ci_low, ci_high, p, q} ],
  buckets: { <grouping>: [ {label, n, win_rate, exp_r, exp_r_gross, thin, q, delta, ci_low, ci_high, p
                            [, unevaluated_n, rr: {p25, median, p75}]   # confidence_decile only
                           } ] },
  splits: { direction: {<label>: Monotonicity}, horizon: {<label>: Monotonicity} },
  notes: [str] }
Monotonicity = { n, spearman_rho, tercile_spread, ci_low, ci_high, p, inverted,
                 tercile_n: [int, int, int], rr_by_tercile: [{p25, median, p75} x3] }
```

Differences from the assumptions:

- **`window` is an object** `{first_week, last_week}` (ISO Mondays), not a string. Never null on a present population (an empty population is `null` as a whole). The store's `reading(..., window)` and the tab's `Window` cell format it, e.g. `first_week..last_week`.
- **Grouping keys** are `confidence_decile, confidence_level, confluence, regime2_state, rs_quintile, direction, horizon, earnings, earnings_in_hold` (that order). The assumed `regime` is **`regime2_state`** (labels `bull_quiet`, `bull_volatile`, `bear_quiet`, `bear_volatile`), and `earnings_bucket` is **`earnings`** (labels `0-5`, `6-10`, `11-20`, `>20`, `none`, `unknown`).
- **Factor keys are display names** (`MACD momentum`, `RSI trend alignment`, ...), not snake_case.
- **v146 `win_rate` is a percent (0-100)**; v147's `*_win_rate` and `fill_rate` are fractions (0-1). Format each in its own unit; never share one formatter blindly.
- Extra fields the page may ignore: `provenance`, `notes`, `p` everywhere, `tercile_n`, `rr_by_tercile`, `n_pos`/`n_zero`, `exp_r_gross`, bucket `delta`/`ci_low`/`ci_high`. A thin bucket's `p` and `q` are null in practice (v146 runs no look under its floor); the fixture's thin bucket keeps `q 0.01` on purpose.
- Fixture value renames that parts 2-4 must follow: dimension keys `regime2_state` / `earnings` (labels `bull_quiet` / `bear_volatile`), factor keys `RSI trend alignment` (q 0.04, candidate) / `MACD momentum` (q 0.31), split names `Direction:bullish`, `Direction:bearish`, `Horizon:2w`, `Horizon:3m` (the bearish split keeps spread -0.05; TRAIN bearish n 620). The regime candidate reads `bull_quiet (Live)`.

v147, `load_report()` (`swingbot/core/infra/gate_counterfactual_store.py`):

```
{ generated_at, live_window: "first..last" | null, bh_family: 5, seed, limitations: [str],
  cells: [ {gate, population, verdict, n, taken_n, verdict_of_record: {verdict, date, n} | null,
            latest: {difference, ci_low, ci_high, q, p} | null, in_sample, note: str | null} ],
  rows:  [ {gate, reason, population, blocked_n, no_plan_n, fill_rate,
            blocked_exp_r, blocked_win_rate, taken_n, taken_exp_r, taken_win_rate, taken_realised_exp_r,
            near_miss_n, near_miss_exp_r, rest_n, rest_exp_r, dollar_risk, over_cap, in_sample} ] }
```

Differences from the assumptions: extra `bh_family`, `seed`, `limitations` at the top; `taken_n` on cells and rows; `p` inside `latest`; `taken_realised_exp_r` on rows (the taken arm's booked R, never the taken ExpR). `near_miss_*` / `rest_*` are null on `compression` rows (no margin band). A real report carries **eight cells**: the five verdict cells (`rs`/live, `risk_cap`/live, `compression`/live, `risk_cap`/train, `compression`/train), then three note cells (`rs`/train, `no_qualifying_target`/live, `no_qualifying_target`/train). The fixture keeps the plan's six; V150-7 adds a local `no_qualifying_target` cell where it needs that case.

The three questions:

1. **Direction and horizon splits** live at `populations.<p>.splits.direction|horizon`, as assumed: `{<label>: Monotonicity}`. Direction labels are `bullish` / `bearish`; horizon labels are `HORIZONS` keys (`1w`, `2w`, `4w`, `2m` ... `9m`), sorted digits-first by v146.
2. **v147 persists the non-verdict states** in the cell's `note`, as assumed: `"no TRAIN population"` (`rs`/train) and `"no verdict — no-plan"` (both `no_qualifying_target` cells), plus two run-time notes on a cell at or above the floor whose taken arm is unusable: `"no TRAIN taken arm — no as-of earnings archive"` (`compression`/train) / `"no <POP> taken arm"`, and `"taken arm below the floor (<k> distinct filled setups < 30)"`. A cell with a note is always `WAITING` with `verdict_of_record: null`; `gatesView` (V150-7) shows the note and derives nothing from the gate name.
3. **The interval is flat** `ci_low` / `ci_high` in both reports (monotonicity, factors, buckets, and v147's `latest`), as assumed. Below v147's floor `latest` is null in practice; the fixture fills live `rs`'s on purpose so the page proves it shows none of it.

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
