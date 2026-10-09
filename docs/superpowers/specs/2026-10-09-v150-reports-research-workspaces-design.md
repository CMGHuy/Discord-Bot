# v150 — Reports and Research workspaces: the two placeholder pages become real

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** ui minor (two placeholder workspaces become real pages)
**Edge:** none (integrity) — display only. It renders verdicts other documents measure (v146, v147, the pre-registration ledger) and sets no threshold, gates nothing and re-runs nothing.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, quant-researcher
**Status:** spec written 2026-10-09.
**Depends on:** v146 (expectancy-attribution report module) and v147 (gate-counterfactual report module) for the Reports tabs' data — see "Contract with v146/v147". The Research workspace depends on nothing unbuilt.

## Why

The sidebar's REVIEW group has listed **Research** and **Reports** since the
shell was built (`frontend/src/app/shell/shell.ts:131-132`), and both land on
one honest placeholder: `PlannedWorkspace`
(`frontend/src/app/workspaces/stubs/planned-workspace.ts:25`), fed per route by
`stubs/research.routes.ts:2` and `stubs/reports.routes.ts:2` and registered in
`frontend/src/app/app.routes.ts:106-115` behind `authGuard`, with subtitles that
still end in "planned".

Two new reports now need a home, and the ledger already has one nobody can see:

1. **v146 expectancy attribution** — does each entry factor (confidence decile,
   confluence, regime, RS quintile, earnings proximity) actually separate good
   trades from bad, live and on TRAIN?
2. **v147 gate counterfactual** — does each gate earn the trades it blocks?
3. **The pre-registration ledger**
   (`docs/superpowers/results/preregistration-ledger.jsonl`, 61 rows today) —
   every hypothesis this repo has measured and what it concluded. Today it is
   readable only as raw JSONL in an editor.

Both reports are produced by scripts, so without a page their answer lives in a
terminal scrollback or a results doc. The partner should be able to open the
admin and see, per factor and per gate, the current verdict and how much live
evidence is behind it.

## Decisions taken in the brainstorm

| Question | Decision |
|---|---|
| What Reports holds | The v146 and v147 reports, one tab each |
| What Research holds | A read-only browser of the pre-registration ledger, plus the strategy registry badge tiers |
| Where report logic lives | In the v146/v147 importable modules; scripts and endpoints are both thin wrappers |
| Report not run yet | An explicit "not yet run" state, never an error and never an empty chart |
| Editing the ledger from the UI | No — the ledger is append-only through `scripts/reports/preregistration_ledger.py` |
| The placeholder | `PlannedWorkspace` and `workspaces/stubs/` are deleted once both pages are real |

## Contract with v146/v147

This spec **does not compute either report**. It requires two things of each
report module, and the v150 plan must not start its Reports tasks until both
hold on `main`:

1. **A JSON-serialisable result.** The module's builder returns a plain `dict`
   (no dataclasses, NaN, numpy scalars or `datetime` objects — `None` for an
   absent value, ISO strings for times) that `flask.jsonify` serialises
   unchanged. The endpoint never reshapes it; the TypeScript model mirrors it.
2. **A persisted latest result at a fixed path.** The TRAIN half of both
   reports is a backtest — minutes, not a request. So the script that runs the
   report writes the result to `data/reports/expectancy-attribution.json` and
   `data/reports/gate-counterfactual.json` (under `config.DATA_DIR`,
   `swingbot/config.py:64`), and the module exposes a loader that returns that
   dict or `None` when the file is absent. `data/` is bind-mounted into both the
   bot and admin containers (`docker-compose.yml:132`, `:192`), so a run on the
   VM is visible to the admin without a rebuild. These files are snapshots like
   `data/scan_snapshots.json` (`swingbot/core/scanning/snapshots.py:9`) — not a
   store, no Postgres table, no Alembic revision. The writer creates
   `data/reports/` if absent.

**Minimum fields this page reads.** The names are v146's and v147's to choose;
if they differ from the list below, the v150 plan renames here, never there.

- *Expectancy attribution:* `generated_at`; `live` and `train` windows with
  their N; per factor: `factor`, `verdict`
  (`PREDICTIVE` / `WEAK` / `NOT PREDICTIVE`), a monotonicity figure, the
  per-factor ExpR delta (best bucket minus worst), and `buckets[]` each carrying
  `key` plus `live` and `train` sub-objects of `{n, exp_r, win_rate}`.
- *Gate counterfactual:* `generated_at`; per gate: `gate`, `blocked_n`,
  `fill_rate`, `blocked` and `taken` sub-objects of `{n, exp_r, win_rate}`,
  `verdict` (`GATE EARNS` / `GATE COSTS` / `INCONCLUSIVE`), `live_n`, and the
  live N target (30).

**Flagged, not resolved here:** at the time of writing neither v146 nor v147 is
committed (no `*v146*` or `*v147*` file under `docs/superpowers/`, and no
attribution or gate-counterfactual module under `swingbot/`). If either spec
lands without a persisted result, its owner adds the write-and-load pair above
or the v150 plan adds it as its own first task — the endpoint never runs a
backtest inside a request.

## API

Two new endpoint modules under `swingbot/admin/api_v1/`, added to the import
list in `register()` (`swingbot/admin/api_v1/__init__.py:208-210`). Both use
`@require_auth` (`api_v1/auth.py:30`) like every sibling.

### `reports.py`

- `GET /api/v1/reports/expectancy-attribution`
- `GET /api/v1/reports/gate-counterfactual`

Each returns one envelope:

```
{ "status": "ok" | "not_run",
  "generated_at": str | null,        # copied from the result, for the freshness marker
  "result": { ...the module's dict, unchanged... } | null }
```

`not_run` is a **200**, not a 404: the endpoint exists and answers truthfully
that nothing has been produced yet. This follows `versions.py:115-128`, which
returns a well-formed empty shape when its frozen file is missing rather than
raising, so the page renders "no history recorded" instead of an error toast.
A result file that exists but fails to parse is a real fault — 500 with the
standard error body (`__init__.py:89-95`), not a silent `not_run`.

### `research.py`

- `GET /api/v1/research/ledger` — every ledger row, enriched:

```
{ "rows": [{ ...the nine LEDGER_FIELDS...,
             "q": float | null,            # BH q-value across the ledger, reported never gating
             "record_exists": bool,         # does `record` resolve inside the image
             "record_kind": "results" | "specs" | "plans" | "other" }],
  "verdicts": [str],                        # stats.VERDICTS, so the SPA hardcodes none
  "instruments": [str] }                    # stats.INSTRUMENTS
```

It reuses the existing validated reader rather than parsing the file itself:
`load_ledger()` (`swingbot/core/backtesting/instrument/stats.py:179`) for rows,
`ledger_qvalues()` (`:208`) for `q`, `VERDICTS`/`INSTRUMENTS` (`:116-118`) for
the filter vocabularies. A ledger line that fails `validate_ledger_row` makes
`load_ledger` raise; the endpoint lets that surface as a 500 — a corrupt ledger
is a defect to see, not hide. The whole ledger is returned (61 rows, a few KB);
filtering and search are client-side, as Analytics already does with
`createClientPage` (`frontend/src/app/ui/data-table/client-page.ts`).

**How the container reads the ledger.** The file is in the image. The runtime
stage copies the whole build context (`Dockerfile:90`, `COPY . .`, under
`WORKDIR /app`), and `.dockerignore` excludes `data/`, `logs/`, `.git/`,
`.claude/` and build output but **not `docs/`**. `LEDGER_PATH` resolves from
the module's own location (`stats.py:110-111`, `parents[4]` → the repo root,
`/app` in the container), so `load_ledger()` works unchanged there. The
consequence the page states in its footer: **the ledger shown is the one in the
deployed image** — a row appended on `main` appears after the next deploy, not
before. No volume mount is added for it: the ledger is a git-tracked record
(`stats.py:105-108`), and "nothing on the host may shadow" the image's code
(`docker-compose.yml:28-29`).

**Strategy badge tiers need no new endpoint.** `GET /api/v1/analytics/registry`
(`swingbot/admin/api_v1/analytics.py:709-714`) already returns
`{"registry": _registry_rows()}` (`swingbot/admin/queries.py:192`): one pooled
row per strategy with `status` (`VALIDATED`/`WEAK`), OOS `n`/`win_rate`/
`expectancy_r`, `window`, `run_date`, live counterparts and `evidence_decay`.
The SPA already has `ApiClient.analyticsRegistry()`
(`frontend/src/app/api/api-client.ts:277-279`); its model is still
`registry: unknown[]` (`frontend/src/app/api/models.ts:662-664`), while the row
type lives as `StrategyRow` in `stores/analytics.store.ts:50`. v150 narrows the
model to `StrategyRow[]` (moving the interface into `api/models.ts`, re-exported
from the store so Analytics imports are untouched).

## Frontend

Both workspaces follow the Versions pattern exactly
(`frontend/src/app/workspaces/versions/versions.routes.ts:6`): one route child
with a route-scoped store in `providers`, `runGuardsAndResolvers: 'always'`,
`routeData(...)` and `resolve: { ready: resolveRoute(...) }`. That puts them
inside the readiness contract `app.routes.spec.ts:109-112` enumerates, and both
paths are added to its `expected` list.

New files:

```
frontend/src/app/workspaces/reports/reports.routes.ts
frontend/src/app/workspaces/reports/reports.ts            (+ .spec.ts)
frontend/src/app/workspaces/reports/attribution-tab.ts     (+ .spec.ts)
frontend/src/app/workspaces/reports/gates-tab.ts           (+ .spec.ts)
frontend/src/app/workspaces/research/research.routes.ts
frontend/src/app/workspaces/research/research.ts           (+ .spec.ts)
frontend/src/app/stores/reports.store.ts                   (+ .spec.ts)
frontend/src/app/stores/research.store.ts                  (+ .spec.ts)
```

`app.routes.ts:106-115` points both routes at the new `*.routes.ts` and drops
"planned" from both subtitles (Reports: "What the measurements say about entries
and gates"; Research: "Every pre-registration and its verdict"). Refresh: neither
page has a server event — a report result changes only when a script runs — so
both use `onEvents()` with no names; the resolver runs on navigation and the
page offers the `sb-async` retry. Every page uses only existing primitives in
`frontend/src/app/ui/` — no new chart component.

### Reports workspace

A `TabBar` (`ui/layout.ts:250`) with two tabs routed by `?tab=attribution|gates`,
default `attribution`. Each tab fetches only its own report.

**Not yet run.** When the envelope says `not_run`, the tab renders `sb-async`
with `emptyReason="no-data-yet"` (`ui/async.ts:6`), title "Not yet run", and a
hint naming the v146/v147 script to run. Never a zero, never an empty axis —
the same rule as Versions' "No version history".

**Freshness.** `generated_at` drives `sb-freshness`, satisfying the D30 rule
`workspace-consistency.spec.ts:65-75` enforces.

**Expectancy attribution tab** (named "Expectancy attribution" — the existing
Analytics **Attribution** tab, `workspaces/analytics/tabs/attribution.ts`, answers
a different question: which strategies produced the live R).

1. **Verdict row** — one `sb-chip` per factor: name + `PREDICTIVE` / `WEAK` /
   `NOT PREDICTIVE`, with the per-factor ExpR delta. Clicking a chip scrolls to
   that factor's panel.
2. **Per-factor panel** (one `sb-panel` each, in the result's order) — a
   `sb-bar-list` of ExpR per bucket, **live and TRAIN side by side** (two lists
   in a two-cell `auto-fit` grid that stacks at phone width), the monotonicity
   figure and verdict badge in the panel header. A bucket with **N < 30** is
   drawn with `withheld: true` (`ui/bar-list.ts` greys label and value) and its
   N shown — present but visibly not evidence.
3. **Footer** — the live and TRAIN windows with their N, and "descriptive — not
   a gate".

**Gate counterfactual tab.**

1. **Gate table** (`sb-data-table`) — one row per gate: blocked N, fill rate,
   blocked ExpR / WR, taken ExpR / WR, and a verdict badge (`GATE EARNS` /
   `GATE COSTS` / `INCONCLUSIVE`).
2. **Live N progress** — per gate, a bar of `live_n` toward 30; below 30 the
   verdict badge is rendered muted and labelled "provisional".
3. **Footer** — window, population, "a verdict here changes no gate; a change
   goes through its own pre-registration".

### Research workspace

Two stacked sections on one page (no tabs — the registry is about a dozen rows and reads
as context for the ledger, not a destination of its own).

1. **Strategy registry** — compact `sb-data-table`: strategy, badge tier
   (`VALIDATED` / `WEAK`), OOS N, OOS ExpR, live N, `evidence_decay`. Read from
   `/analytics/registry`; badges come from the server verbatim.
2. **Pre-registration ledger** —
   - `sb-toolbar` (`ui/toolbar.ts:84`, as `workspace-consistency.spec.ts:40-51`
     requires for filters): a verdict chip set built from the response's
     `verdicts` (multi-select, counts per verdict shown), an instrument
     `sb-segmented`, and a text search over `id` and `hypothesis`.
   - `sb-data-table`, newest `date` first: date, id, hypothesis (truncated),
     instrument, N, ExpR, p, q, verdict badge. Paged client-side, 25 rows.
   - **Row detail** in a `Drawer` (`ui/layout.ts:414`): every field in full, the
     q-value labelled "reported, never gating", and the `record` path as a
     monospace value with a copy button. A `record_exists: false` path is shown
     struck through with "not in this deploy". No outbound link: the docs are
     not served by the admin, and the repo is not assumed public.
   - Footer: "The ledger as of the deployed build. Append rows with
     `scripts/reports/preregistration_ledger.py`; this page never edits it."

Filter state (verdicts, instrument, search) lives in the query string so a
filtered view is shareable, as Analytics' URL state is.

### Removing the placeholder

Once both routes point at real pages, delete
`frontend/src/app/workspaces/stubs/` entirely (`planned-workspace.ts`,
`planned-workspace.spec.ts`, `reports.routes.ts`, `research.routes.ts`), and
replace the `app.routes.spec.ts:96-105` "exposes Research and Reports as
guarded, titled lazy stubs" test — it is superseded by the two paths joining the
readiness contract above.

## Edge cases

| Case | Handling |
|---|---|
| Report file absent | `status: not_run`, 200; tab shows "Not yet run" with the script to run |
| Report file present but malformed | 500 standard error body; `sb-async` error state with retry |
| Factor bucket or gate with N < 30 | Shown, greyed (`withheld`) / badge "provisional"; never hidden |
| Live half present, TRAIN half absent (or the reverse) | The present side renders; the absent side reads "not in this run" — never zero |
| Ledger row with null `n` / `exp_r` / `p` (32 of 61 today have null `n`) | Em dash; `q` null; sorts last on that column |
| Ledger line fails validation | `load_ledger` raises → 500; the page shows the error, not a partial ledger |
| `record` path missing from the image | `record_exists: false`, struck-through path |
| A verdict added to `stats.VERDICTS` later | Appears as a filter chip automatically (server-sent list) |
| No registry rows | `sb-async` measured-zero empty state |

## Testing

**pytest** — `tests/admin/test_api_v1_reports.py`, `tests/admin/test_api_v1_research.py`,
both asserting shapes with `assert_shape` (`tests/admin/api_v1_contract.py`),
which fails on extra keys as well as missing ones:

- reports: `not_run` when the file is absent (status 200, `result: null`); `ok`
  passes the module dict through unchanged (a fixture file under `tmp_path`
  with `DATA_DIR` monkeypatched); malformed file → 500 error body; auth required.
- research: rows equal `load_ledger()` of a fixture ledger plus `q`,
  `record_exists`, `record_kind`; `q` matches `ledger_qvalues`; `verdicts`
  equals `stats.VERDICTS`; an invalid ledger line → 500; auth required.
- One test that the real committed ledger loads through the endpoint, so a
  ledger the page cannot render fails CI rather than production.

**Vitest** — one spec per component and store:

- `reports.spec.ts`: tab switching via `?tab=`; only the active tab fetches.
- `attribution-tab.spec.ts`: renders from a fixture; verdict chips; live/TRAIN
  side by side; N < 30 bucket greyed; `not_run` state.
- `gates-tab.spec.ts`: table rows and badges; provisional below N 30; `not_run`.
- `research.spec.ts`: verdict and instrument filters, search, drawer detail,
  missing-record rendering, registry section; filter state round-trips the URL.
- `reports.store.spec.ts`, `research.store.spec.ts`: resolve, error, narrowing.
- `app.routes.spec.ts`: both paths in the readiness contract; no route imports
  from `workspaces/stubs/`.
- `workspace-consistency.spec.ts` passes unchanged over the new sources.

Every new or changed function stays under cyclomatic complexity 15.

## Parallelisation

- **Blocked before start:** the Reports API and Reports UI tasks wait for v146
  and v147 to merge with the result contract above. The Research tasks do not
  wait — they can run first.
- **Group A (parallel):** `api_v1/research.py` + its test; `api_v1/reports.py`
  + its test (only once v146/v147 are on `main`) — disjoint files. Their one
  shared file, `api_v1/__init__.py`'s import list, is edited by whichever lands
  second, or by a dedicated one-line task after both.
- **Sequential:** `api/models.ts` + `api-client.ts` (both new models, the
  `StrategyRow` move) after Group A — one shared file pair, and each model
  mirrors an endpoint's response. Stores after the models.
- **Group B (parallel, after the stores):** the Research workspace; the Reports
  workspace with its two tabs — disjoint directories, each consuming only its
  own store.
- **Sequential:** `app.routes.ts` + `app.routes.spec.ts` rewiring and the
  `stubs/` deletion after Group B (the routes import the new components; the
  stubs cannot go while a route still loads them).
- **Last:** full Python suite and full `npm test`, once.

## Out of scope

- Computing either report, choosing its buckets or its verdict thresholds — v146/v147 own all of it.
- Scheduling report runs (cron on the VM). A later spec if the partner wants it.
- Writing to the ledger from the UI, or rendering the results docs it points at.
- "Scheduled reports and exports" and the "symbol research desk" the placeholders promised — not chosen.
- A new endpoint for the registry, or any change to `_registry_rows`.
