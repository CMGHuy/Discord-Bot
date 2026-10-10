# v150 — Reports and Research workspaces: the two placeholder pages become real

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** ui minor (two placeholder workspaces become real pages)
**Edge:** none (integrity) — display only. It renders verdicts other documents measure (v146, v147, the pre-registration ledger) and sets no threshold, gates nothing and re-runs nothing.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, quant-researcher
**Status:** spec written 2026-10-09; panel review applied; plan: [`2026-10-09-v150-reports-research-workspaces_0-index.md`](../plans/2026-10-09-v150-reports-research-workspaces_0-index.md).
**Depends on:** v146 (`load_latest()`, v146 spec `:297`) and v147 (`load_report()`, v147 spec `:270`) for the Reports tabs' data, plus the cross-spec requirements in "Contract with v146/v147". The Research workspace depends on nothing unbuilt.

## Why

The sidebar's REVIEW group has listed **Research** and **Reports** since the
shell was built (`frontend/src/app/shell/shell.ts:131-132`), and both land on
one honest placeholder: `PlannedWorkspace`
(`frontend/src/app/workspaces/stubs/planned-workspace.ts:25`), fed per route by
`stubs/research.routes.ts:2` and `stubs/reports.routes.ts:2` and registered in
`frontend/src/app/app.routes.ts:106-115` behind `authGuard`, with subtitles that
still end in "planned".

Two new reports now need a home, and the ledger already has one nobody can see:

1. **v146 expectancy attribution** — does confidence predict R, and which
   buckets (confidence decile, confluence, regime, RS quintile, earnings
   proximity, direction, horizon) separate good trades from bad, live and on TRAIN?
2. **v147 gate counterfactual** — does each gate earn the trades it blocks?
3. **The pre-registration ledger**
   (`docs/superpowers/results/preregistration-ledger.jsonl`, 61 rows today) —
   every hypothesis this repo has measured and what it concluded. Today it is
   readable only as raw JSONL in an editor.

Both reports are produced by scripts, so without a page their answer lives in a
terminal scrollback or a results doc. The partner should be able to open the
admin and see each verdict of record, how much evidence is behind it, and what
the latest reading says — without mistaking one for the other.

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

This spec **does not compute either report** and **never recomputes a figure
or a floor in the page**. It consumes the two loaders the sibling specs
already fix:

- **v146** — `swingbot/core/analytics/expectancy_attribution.py`,
  `load_latest() -> dict | None` (v146 spec `:297`), reading
  `data/reports/expectancy-attribution.json`.
- **v147** — `swingbot/core/analytics/gate_counterfactual_report.py`,
  `load_report() -> dict | None` (v147 spec `:270`), reading
  `data/reports/gate-counterfactual.json`.

`None` means "never run". `data/` is bind-mounted into both containers
(`docker-compose.yml:140` bot, `:206` admin), so a run is visible to the admin
without a rebuild. Field names are v146's and v147's; the TypeScript models
mirror the modules' dicts and the endpoint never reshapes them. If a name
differs from the prose below, the v150 plan renames here, never there.

### What the page reads — v146

Shape fixed at v146 spec `:297-301`:
`{generated_at, verdict, seed, populations: {live: {...}, train: {...}}}`,
each population carrying `buckets`, `factors`, `monotonicity`.

- **`verdict`** — the one top-level confidence verdict, `PREDICTIVE` / `WEAK`
  / `NOT PREDICTIVE` (with "inverted" inside NOT PREDICTIVE, v146 `:273-277`).
  It is the **verdict of record**: computed once at the scheduled run, never
  revised by later runs (v146 `:279-281`).
- **`populations.live` / `.train`** — never pooled. `monotonicity`: Spearman ρ
  and top-minus-bottom tercile ExpR with its week-clustered 95% CI (v146
  `:240-243`). `factors`: per-factor ExpR delta (scored > 0 minus scored 0,
  v146 `:235-238`) with CI and BH q. `buckets`: N / WR / ExpR per bucket of
  each dimension, including the direction and horizon splits (v146 `:258-259`),
  with **`thin: true`** on every N < 30 bucket (v146 `:301`).

### What the page reads — v147

One row per **gate × reason × population**, live and TRAIN side by side, never
pooled (v147 `:274-285`): blocked N, `no-plan` N, fill rate, blocked and taken
ExpR / WR over `filled`, the near-miss vs rest split, and on `risk_cap` rows
the fixed-dollar-risk column with the **over-cap** tag. Verdicts live on the
**five cells** gate × population (live `rs`, `risk_cap`, `compression`;
TRAIN `risk_cap`, `compression`; v147 `:315-319`):

- `GATE EARNS` / `GATE COSTS` / `INCONCLUSIVE` / **`WAITING`** (v147 `:309-313`).
- The **difference** blocked − taken ExpR, its week-clustered 95% CI and BH q
  across the five cells.
- N = **distinct filled setups** (v147 `:287-291`) — the page reads it, never
  counts rows and never applies the 30 floor itself.
- The **verdict of record** with its date and N, frozen at the first reading
  with N ≥ 30 (v147 `:321-324`); later readings are descriptive.
- Labels: **in-sample** on TRAIN compression (v147 `:332`), the live window
  inside the 2026 holdout (v147 `:326-328`), and the portfolio-state
  limitation printed beside every live verdict (v147 `:334-338`).

### Cross-spec requirements on the v146 and v147 plans

Each is small, and the v150 Reports tasks do not start until both plans
satisfy them on `main`:

1. **Atomic write.** The writer writes a temp file in `data/reports/` and
   `os.replace`s it over the target, so the admin never reads a half-written
   file. That is what lets a parse failure mean a real fault (see API).
2. **Cheap loader import.** The admin imports only the loader. `load_latest()`
   / `load_report()` must be importable without pulling pandas, numpy or
   `swingbot.core.backtesting` — either the module lazy-imports those inside
   its builder, or the loader lives in a separate light module the endpoint
   imports. A test in each plan pins it (fresh interpreter, import the loader,
   assert none of those are in `sys.modules`).
3. **Fields persisted, not left in the results doc.** v146: the verdict of
   record's run date and N beside `verdict`, carried forward unchanged by
   later runs, and the looks count (the BH family size, v146 `:245-248`).
   v147: per cell the verdict of record (verdict, date, N) and the latest
   reading's difference, CI and q; per row the labels above.
4. **Ownership and retention.** `data/reports/*.json` is owned by the v146 and
   v147 modules. Each run overwrites its file; there is no history beyond the
   latest (the verdict of record survives because the writer carries it
   forward inside the file). These are snapshots like
   `data/scan_snapshots.json` (`swingbot/core/scanning/snapshots.py:9`) — no
   Postgres table, no Alembic revision.

### Where the reports run in production

The live DB is on the Hetzner VM, so both report scripts run **there, inside
the bot container**, and write the VM's `data/reports/`:

```
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/<script>.py ..."
```

The TRAIN half is a backtest produced on the dev machine (`backtest-runner`);
its JSONL inputs are piped up over ssh stdin into `data/reports/inputs/` on
the VM (`bash scripts/ops/ssh-hetzner.sh "cat > /opt/swing-bot/data/reports/inputs/<file>" < <local file>`)
before the script runs. `docs/deploy/DEPLOY_HETZNER.md` does not document this
step today; the v150 plan adds it as a task (its "Remote commands through
`ssh-hetzner.sh`" paragraph, `DEPLOY_HETZNER.md:421-423`, is where it goes).

## API

Two new endpoint modules under `swingbot/admin/api_v1/`, added to the import
list in `register()` (`swingbot/admin/api_v1/__init__.py:208-210`). Both use
`@require_auth` (`api_v1/auth.py:30`) like every sibling.

### `reports.py`

- `GET /api/v1/reports/expectancy-attribution` — calls v146 `load_latest()`.
- `GET /api/v1/reports/gate-counterfactual` — calls v147 `load_report()`.

Each returns one envelope:

```
{ "status": "ok" | "not_run",
  "generated_at": str | null,        # copied from the result, for the freshness marker
  "result": { ...the loader's dict, unchanged... } | null }
```

Loader returns `None` → `not_run`, a **200**, not a 404: the endpoint answers
truthfully that nothing has been produced yet, as `versions.py:115-128`
returns a well-formed empty shape when its frozen file is missing. A loader
that raises (a file present but unparseable — impossible from an atomic
writer, so a real fault) → 500 with the standard error body
(`__init__.py:89-95`), never a silent `not_run`. The endpoint never runs a
backtest or a build inside a request.

### `research.py`

- `GET /api/v1/research/ledger` — every ledger row, enriched:

```
{ "rows": [{ ...the nine LEDGER_FIELDS...,
             "q": float | null,            # BH q-value across the whole ledger, reported never gating
             "record_exists": bool,         # does `record` resolve inside the image
             "record_kind": "results" | "specs" | "plans" | "other" }],
  "q_family_m": int,                        # rows with a p-value, i.e. the BH family size
  "verdicts": [str],                        # stats.VERDICTS, so the SPA hardcodes none
  "instruments": [str] }                    # stats.INSTRUMENTS
```

It reuses the existing validated reader: `load_ledger()`
(`swingbot/core/backtesting/instrument/stats.py:179`) for rows,
`ledger_qvalues()` (`:208`) for `q`, `VERDICTS`/`INSTRUMENTS` (`:116-118`) for
the filter vocabularies. A ledger line that fails `validate_ledger_row` makes
`load_ledger` raise; the endpoint lets that surface as a 500. The whole ledger
is returned (61 rows, a few KB); filtering and search are client-side, as
Analytics does with `createClientPage`
(`frontend/src/app/ui/data-table/client-page.ts`).

**How the container reads the ledger.** The file is in the image: the runtime
stage copies the build context (`Dockerfile:90`, `COPY . .`), and
`.dockerignore` excludes `data/`, `logs/`, `.git/`, `.claude/` and build output
but **not `docs/`**. `LEDGER_PATH` resolves from the module's location
(`stats.py:110-111`, `parents[4]` → `/app`), so `load_ledger()` works
unchanged. **The ledger shown is the one in the deployed image** — a row
appended on `main` appears after the next deploy. No volume mount: the ledger
is a git-tracked record (`stats.py:105-108`), and nothing on the host may
shadow the image's code (`docker-compose.yml:28-29`).

**Strategy badge tiers need no new endpoint.** `GET /api/v1/analytics/registry`
(`swingbot/admin/api_v1/analytics.py:709-714`) returns
`{"registry": _registry_rows()}` (`swingbot/admin/queries.py:192`): per
strategy `status` (`VALIDATED`/`WEAK`), OOS `n`/`win_rate`/`expectancy_r`,
`window`, `run_date`, live counterparts and `evidence_decay`. The SPA has
`ApiClient.analyticsRegistry()` (`frontend/src/app/api/api-client.ts:277-279`);
its model is still `registry: unknown[]` (`frontend/src/app/api/models.ts:662-664`)
while the row type is `StrategyRow` in `stores/analytics.store.ts:50`. v150
narrows the model to `StrategyRow[]` (moved into `api/models.ts`, re-exported
from the store so Analytics imports are untouched).

## Frontend

Both workspaces follow the Versions pattern
(`frontend/src/app/workspaces/versions/versions.routes.ts:6`): one route child
with a route-scoped store in `providers`, `runGuardsAndResolvers: 'always'`,
`routeData(...)` and `resolve: { ready: resolveRoute(...) }`, joining the
readiness contract `app.routes.spec.ts:109-112` enumerates.

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
and gates"; Research: "Every pre-registration and its verdict"). Neither page
has a server event — a result changes only when a script runs — so both use
`onEvents()` with no names; the resolver runs on navigation and the page
offers the `sb-async` retry. Only existing primitives in `frontend/src/app/ui/`
— no new chart component.

**Fixed footer on both workspaces:** "Historical measurement on paper trades;
not a forecast or advice."

**Display rules shared by both report tabs** (the quant rules, applied once):

- **The verdict of record is THE verdict** — shown with its date and N. The
  latest reading sits in a separate block headed "Latest reading —
  descriptive", never styled as a verdict.
- **Below the floor:** `WAITING` with an N progress bar (`N 17 / 30`) and
  nothing else — no muted, provisional or greyed verdict badge, no CI.
  Whether a figure is below the floor comes from v146's `thin` flag or v147's
  distinct-filled-setup N and `WAITING`; the page never tests N < 30 itself.
- **Caption on every figure table:** "R units, net of frictions as v146/v147
  compute them, pre-tax."
- A verdict is worded as a historical measurement ("over these trades, the
  gate's blocked setups returned less than its taken ones"), never as an
  instruction ("keep this gate").

### Reports workspace

A `TabBar` (`ui/layout.ts:250`) with two tabs routed by `?tab=attribution|gates`,
default `attribution`. Each tab fetches only its own report.

**Not yet run.** On `not_run` the tab renders `sb-async` with
`emptyReason="no-data-yet"` (`ui/async.ts:6`), title "Not yet run", and the
production command from "Where the reports run in production". Never a zero,
never an empty axis.

**Freshness.** `generated_at` drives `sb-freshness`, satisfying the D30 rule
`workspace-consistency.spec.ts:65-75` enforces.

**Expectancy attribution tab** (named "Expectancy attribution" — the Analytics
**Attribution** tab, `workspaces/analytics/tabs/attribution.ts`, answers a
different question).

1. **Verdict of record** — one `sb-chip`: the top-level `verdict`
   (`PREDICTIVE` / `WEAK` / `NOT PREDICTIVE`, "inverted" noted when present),
   its date and N. This is the **only** PREDICTIVE/WEAK/NOT PREDICTIVE chip on
   the page.
2. **Latest reading — descriptive** — per population, side by side:
   Spearman ρ and top-minus-bottom tercile ExpR with its 95% CI.
3. **Factors** — one row per factor, live and TRAIN: ExpR delta with its CI.
   No verdict chip. A "screen candidate" marker appears only when the factor's
   BH q < 0.10 — a candidate for a Stage −2 screen, never a filter.
4. **Bucket panels** (one `sb-panel` per dimension, in the result's order:
   confidence decile and level, confluence, regime, RS quintile, earnings
   bucket and earnings-inside-the-hold, direction, horizon) — a `sb-bar-list`
   of ExpR per bucket, **live and TRAIN side by side** (two-cell `auto-fit`
   grid that stacks at phone width). A `thin` bucket is drawn
   `withheld: true` (`ui/bar-list.ts:6`) with its N — present, visibly not
   evidence. A bucket with BH q < 0.10 carries the screen-candidate marker.
5. **Direction and horizon splits** — the monotonicity reading repeated per
   direction and per horizon, as v146 splits every verdict table (v146
   `:258-259`), so a lift concentrated in one is visible.
6. **Footer** — each population's window and N, the seed, "looks: *n* — BH
   family for every q on this tab", the R caption, "descriptive — not a gate".

**Gate counterfactual tab.**

1. **Verdict table** (`sb-data-table`) — one row per cell (gate ×
   population, the five cells): verdict of record with date and N (or
   `WAITING` + N progress), then the latest reading — difference
   (blocked − taken), week-clustered 95% CI, BH q — under a "Latest reading —
   descriptive" column group, blank while `WAITING`. RS shows "no TRAIN
   population" in its TRAIN slot; `no_qualifying_target` shows "no verdict —
   no-plan".
2. **Labels beside verdicts** — **in-sample** on the TRAIN compression cell;
   beside every live verdict, the portfolio-state limitation ("simulated as a
   lone trade; ignores heat and correlation caps") and the 2026-holdout note
   ("live window inside the 2026 holdout; a follow-on screen needs an unseen
   one").
3. **Detail rows** — expanding a cell lists its gate × reason rows: blocked N,
   `no-plan` N, fill rate, blocked and taken ExpR / WR, near-miss vs rest.
   Every `risk_cap` row shows the dollar-risk column beside R and the
   **over-cap** tag ("a trade the dollar-risk rule forbids; not a tradable
   alternative").
4. **Footer** — "BH family: the five verdict cells", the R caption, "a
   verdict here changes no gate; a change goes through its own
   pre-registration".

### Research workspace

Two stacked sections on one page (no tabs — the registry is about a dozen rows
and reads as context for the ledger).

1. **Strategy registry** — compact `sb-data-table`: strategy, badge tier with
   `run_date` and `window` beside it, OOS N, OOS ExpR, live N,
   `evidence_decay`. `WEAK` renders muted, visibly distinct from `VALIDATED`.
   A line above the table: "Figures in R, pre-tax." Read from
   `/analytics/registry`; tiers come from the server verbatim.
2. **Pre-registration ledger** —
   - `sb-toolbar` (`ui/toolbar.ts:84`, as `workspace-consistency.spec.ts:40-51`
     requires for filters): a verdict chip set from the response's `verdicts`
     (multi-select, counts shown), an instrument `sb-segmented`, and a text
     search over `id` and `hypothesis`.
   - `sb-data-table`, newest `date` first: date, id, hypothesis (truncated),
     instrument, N, ExpR, p, q, verdict badge. No window column — the ledger
     does not record one. Paged client-side, 25 rows.
   - **Row detail** in a `Drawer` (`ui/layout.ts:414`): every field in full;
     the q-value labelled "reported, never gating — BH over all *m* ledger
     rows with a p-value (`q_family_m`), mixing instruments; filters do not
     change it"; the `record` path as a monospace value with a copy button,
     labelled "window and method: see record". A `record_exists: false` path
     is struck through with "not in this deploy". No outbound link: the docs
     are not served by the admin.
   - Footer: "The ledger as of the deployed build. Append rows with
     `scripts/reports/preregistration_ledger.py`; this page never edits it."

Filter state (verdicts, instrument, search) lives in the query string so a
filtered view is shareable.

### Removing the placeholder

Once both routes point at real pages, delete
`frontend/src/app/workspaces/stubs/` entirely (`planned-workspace.ts`,
`planned-workspace.spec.ts`, `reports.routes.ts`, `research.routes.ts`), and
replace the `app.routes.spec.ts:96-105` "exposes Research and Reports as
guarded, titled lazy stubs" test — superseded by the readiness contract.

## Edge cases

| Case | Handling |
|---|---|
| Loader returns `None` | `status: not_run`, 200; "Not yet run" with the production command |
| Loader raises | 500 standard error body; `sb-async` error state with retry |
| Cell below the floor (v147 `WAITING`) | `WAITING` + N progress only; no badge, no CI, no difference |
| `thin` bucket (v146) | Shown `withheld` with N; enters no marker |
| Factor or bucket with q ≥ 0.10 | Delta and CI shown, no screen-candidate marker |
| RS TRAIN slot / `no_qualifying_target` | "no TRAIN population" / "no verdict — no-plan" |
| Live half present, TRAIN half absent (or the reverse) | The present side renders; the absent side reads "not in this run" — never zero |
| Ledger row with null `n` / `exp_r` / `p` (32 of 61 today have null `n`) | Em dash; `q` null; sorts last on that column |
| Ledger line fails validation | `load_ledger` raises → 500; the page shows the error, not a partial ledger |
| `record` path missing from the image | `record_exists: false`, struck-through path |
| A verdict added to `stats.VERDICTS` later | Appears as a filter chip automatically |
| No registry rows | `sb-async` measured-zero empty state |

## Testing

**pytest** — `tests/admin/test_api_v1_reports.py`,
`tests/admin/test_api_v1_research.py`, both asserting shapes with
`assert_shape` (`tests/admin/api_v1_contract.py`), which fails on extra keys:

- reports: loader `None` → `not_run`, 200, `result: null`; a fixture dict
  passes through unchanged (loader monkeypatched); loader raises → 500 error
  body; auth required; importing `swingbot.admin.api_v1.reports` in a fresh
  interpreter leaves `swingbot.core.backtesting` out of `sys.modules`.
- research: rows equal `load_ledger()` of a fixture ledger plus `q`,
  `record_exists`, `record_kind`; `q` matches `ledger_qvalues`; `q_family_m`
  equals the count of rows with a p-value; `verdicts` equals `stats.VERDICTS`;
  an invalid ledger line → 500; auth required.
- One test that the real committed ledger loads through the endpoint, so a
  ledger the page cannot render fails CI rather than production.
- `tests/admin/test_api_v1_research.py` is added to the existing ledger row in
  `scripts/dev/select_tests.py:274-277`, so a ledger edit selects it.

**Vitest** — one spec per component and store:

- `reports.spec.ts`: tab switching via `?tab=`; only the active tab fetches;
  both workspaces render the fixed footer.
- `attribution-tab.spec.ts`: exactly one verdict chip (the top-level
  verdict, with date and N); latest reading in its own descriptive block;
  factors show delta + CI with no chip; screen-candidate marker only at
  q < 0.10; `thin` bucket withheld; direction/horizon splits; looks count in
  the footer; `not_run`.
- `gates-tab.spec.ts`: five cells; a `WAITING` fixture (N 29) shows progress
  and no badge, CI or difference; verdict of record vs a different latest
  reading rendered apart; in-sample, over-cap, portfolio-state and holdout
  labels; `not_run`.
- `research.spec.ts`: verdict and instrument filters, search, drawer detail
  with `q_family_m`, missing-record rendering; registry `WEAK` muted with
  `run_date`/`window`; filter state round-trips the URL.
- `reports.store.spec.ts`, `research.store.spec.ts`: resolve, error, narrowing.
- `app.routes.spec.ts`: both paths in the readiness contract; no route imports
  from `workspaces/stubs/`.
- `workspace-consistency.spec.ts` passes unchanged over the new sources.

Every new or changed function stays under cyclomatic complexity 15.

## Parallelisation

- **Blocked before start:** the Reports API and Reports UI tasks wait for v146
  and v147 on `main` with the four cross-spec requirements met. The Research
  tasks do not wait.
- **Group A (parallel):** `api_v1/research.py` + its test + the
  `select_tests.py` row; `api_v1/reports.py` + its test (once v146/v147 are
  on `main`) — disjoint files. `api_v1/__init__.py`'s import list is edited
  by whichever lands second, or a one-line task after both.
- **Independent:** the `DEPLOY_HETZNER.md` task documenting the production
  run path and the TRAIN-input upload.
- **Sequential:** `api/models.ts` + `api-client.ts` (both new models, the
  `StrategyRow` move) after Group A; stores after the models.
- **Group B (parallel, after the stores):** the Research workspace; the
  Reports workspace with its two tabs — disjoint directories.
- **Sequential:** `app.routes.ts` + `app.routes.spec.ts` rewiring and the
  `stubs/` deletion after Group B.
- **Last:** full Python suite and full `npm test`, once.

## Out of scope

- Computing either report, choosing its buckets, floors or verdict thresholds — v146/v147 own all of it.
- Scheduling report runs (cron on the VM). A later spec if the partner wants it.
- Writing to the ledger from the UI, or rendering the results docs it points at.
- "Scheduled reports and exports" and the "symbol research desk" the placeholders promised — not chosen.
- A new endpoint for the registry, or any change to `_registry_rows`.

## Panel review

- staff-engineer: consume v146's shape (`verdict`, `seed`, `populations{live,train}` with `buckets`/`factors`/`monotonicity`); one top-level confidence verdict of record -- applied
- staff-engineer: consume v147's shape (gate × reason × population rows, five cells, WAITING, verdict of record with date and N, labels) -- applied
- staff-engineer: stale "Flagged, not resolved here" fallback removed; `load_latest()` (v146 `:297`) and `load_report()` (v147 `:270`) cited by name and line -- applied
- staff-engineer: production run path on the VM bot container via `ssh-hetzner.sh`; TRAIN inputs piped over stdin into `data/reports/inputs/`; DEPLOY_HETZNER.md step is a plan task -- applied
- staff-engineer: atomic write (temp + `os.replace`) stated as a cross-spec requirement on the v146/v147 plans -- applied
- staff-engineer: admin imports only a light loader (lazy imports or separate module), pinned by a test -- applied
- staff-engineer: research endpoint test added to the ledger row in `scripts/dev/select_tests.py:274-277` -- applied
- staff-engineer: mount cites fixed to `docker-compose.yml:140` and `:206` -- applied
- staff-engineer: `data/reports/*.json` owned by the v146/v147 modules; each run overwrites; no retention beyond latest -- applied
- financial-advisor: report captions read "R units, net of frictions as v146/v147 compute them, pre-tax" -- applied
- financial-advisor: gate verdict worded as a historical measurement, never an instruction -- applied
- financial-advisor: WEAK muted and distinct from VALIDATED; `run_date` beside the tier -- applied
- financial-advisor: registry carries a "Figures in R, pre-tax" line -- applied
- financial-advisor: fixed footer on both workspaces: "Historical measurement on paper trades; not a forecast or advice." -- applied
- quant-researcher: [BLOCKING] below the floor show WAITING with N progress only, never a muted/provisional verdict badge -- applied
- quant-researcher: [BLOCKING] verdict of record (date, N) shown as THE verdict; latest reading shown separately, labelled descriptive -- applied
- quant-researcher: only the top-level confidence verdict gets a PREDICTIVE/WEAK/NOT PREDICTIVE chip; factors show delta + CI, screen-candidate marker only at BH q < 0.10 -- applied
- quant-researcher: gate table shows difference (blocked − taken), week-clustered 95% CI and BH q -- applied
- quant-researcher: footers state the BH family (v146 looks count; v147 five cells) -- applied
- quant-researcher: in-sample label on TRAIN compression; portfolio-state limitation and 2026-holdout note beside live verdicts -- applied
- quant-researcher: ledger drawer states BH family size m, that it mixes instruments, and that q ignores filters -- applied
- quant-researcher: ledger records no window; the drawer points to `record` for it -- applied
- quant-researcher: page uses v146's `thin` flag and v147's distinct-filled-setup N; never recomputes N < 30 -- applied
- quant-researcher: registry shows `run_date` and `window` beside the tier -- applied
- quant-researcher: attribution tab carries the direction and horizon splits per v146 -- applied
