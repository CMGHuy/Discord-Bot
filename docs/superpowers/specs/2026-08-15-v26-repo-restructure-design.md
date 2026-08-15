# v26 — Repository restructure: core packaging, scripts, tests, docs

Version: ui 1.2.3 · bot 1.1.2
Bump: `bot patch (1.1.2 → 1.1.3)` · `ui none` — the work ships running code but
zero observable difference: no endpoint, embed, chart or setting changes. The
Angular SPA is not touched at all, so its line does not move.
Blocked on: `v24-control-alignment` and `v25-trade-chart`, both of which must be
merged to `main` first. **Do not start this spec while either is live** — v26
renames the files v25 edits. See "Ordering" before executing anything, and run
its reconciliation step before the first move: the inventories below were taken
on 2026-08-15 and v25 adds files to them.

## Goal

`swingbot/core/` is a 46-module flat directory with four sub-packages already
carved out of it (`analytics/`, `charts/`, `edge/`, `scanning/`). The flat
remainder mixes market-data access, analysis primitives, plan construction,
backtesting, trade tracking and persistence plumbing with no grouping, so
locating the module that owns a concern means reading 46 filenames and guessing.
`scripts/` (32 files) and `tests/` (157 files) are flat for the same reason, and
five documents sit at the repo root that belong under `docs/`.

This restructure moves files and rewrites the references that point at them. It
changes no behaviour. The success criterion is exactly that: the full suite
returns its reference baseline unchanged.

## Non-goals

- **No file is split.** `commands/scanning.py` (1759 lines),
  `core/scanning/engine.py` (1731), `core/performance.py` (1317) and
  `core/charts/trade_chart.py` (1188) stay as they are. Splitting them collides
  head-on with the live `v25-trade-chart` plan and is a separate spec.
- **No logic changes**, no signature changes, no new abstractions. A diff hunk
  that is not a move, an import line, a path string or a doc reference is a bug.
- **No new compatibility shims** — see "Shim policy" below.

## The shim policy, and why

The repo has two shims already: `core/scan_engine.py` re-exports
`core/scanning/engine.py`, and `core/trade_plan.py` re-exports
`plan_engine.build_strategy_plan`. `scan_engine.py` is still imported by **eight
live source files** — `bot.py`, `admin/app.py`, `admin/helpers.py`, and four
`commands/` modules — long after the module it fronts was carved out. Call sites
are now split between the shim and the real module, which is strictly worse than
either alone.

That is the evidence: shims introduced as temporary become permanent here.

So this restructure adds none, and **removes both existing ones** as part of the
work. Every old import path is rewritten to its new home in the same commit that
moves the file. The tree ends with fewer indirection layers than it started with,
which is the only outcome that justifies the churn of touching every call site.

The safety net is the test suite. An import that was missed fails at collection,
loudly, before any behaviour runs.

## Target layout

### `swingbot/core/`

The four existing sub-packages are untouched. The 46 flat modules become six:

| Package | Modules |
|---|---|
| `marketdata/` | `data`, `data_store`, `data_refresh`, `backtest_cache`, `fmp_client`, `export_data`, `ticker_directory`, `ticker_utils`, `universe`, `watchlist` |
| `market/` | `indicators`, `candlestick_patterns`, `fvg`, `levels`, `levels_lifecycle`, `trendlines`, `volatility`, `market_context`, `signals`, `strategy`, `strategy_types`, `entry_filters`, `reversal`, `explain`, `events`, `market_events` |
| `planning/` | `plan_engine`, `plan_manager`, `plan_store`, `quality`, `account` |
| `backtesting/` | `backtest`, `backtest_wf`, `backtest_scenarios`, `registry`, `shadow_log` |
| `tracking/` | `performance`, `retrospective`, `risk_metrics` |
| `infra/` | `jsonio`, `state`, `notifier`, `silent_channel` |

**No package may share a name with a module inside it.** `marketdata/` and
`backtesting/` carry the awkward names for this reason, not for style: the
obvious `data/` would contain `data.py` and `backtest/` would contain
`backtest.py`, giving `swingbot.core.data.data`.

That is not merely ugly — it is a silent-failure generator. **105 imports use the
package-attribute form `from swingbot.core import X`**, among them
`from swingbot.core import data as data_module` and
`from swingbot.core import backtest`. Under a colliding name those keep importing
successfully and bind the *package* instead of the module, so the failure surfaces
later as `AttributeError: module 'swingbot.core.data' has no attribute
'fetch_ohlc'` — and a `mock.patch("swingbot.core.data.…")` target would patch a
package. An import error is a good failure; this is the bad one.

`marketdata/` also mirrors the on-disk `market_data/` CSV cache it manages, which
makes the pairing with the sibling `market/` (which computes on bars rather than
fetching them) easier to keep straight.

`scan_engine.py` and `trade_plan.py` are deleted rather than placed.

### Relative imports become absolute

Fourteen of the moving modules import siblings relatively (`from .indicators
import atr`). Most survive the move untouched because their target lands in the
same package — all five of `levels.py`'s relative imports stay inside `market/`.
Three do not, and these break at import time:

| Module | Broken relative imports |
|---|---|
| `backtest.py` → `backtesting/` | `.entry_filters`, `.indicators`, `.levels`, `.plan_engine`, `.strategy`, `.strategy_types` |
| `events.py` → `market/` | `.ticker_utils`, `.universe` (both → `marketdata/`) |
| `data_refresh.py` → `marketdata/` | `.jsonio` (→ `infra/`) |

Rather than fix the three and leave eleven modules whose correctness depends on
two files happening to stay in the same package, **every relative import in a
moving module is rewritten to absolute** (`from swingbot.core.market.indicators
import atr`). The surviving ones are not left alone as a shortcut; the point is
that the next move should not be able to break them silently.

**The reverse direction breaks too, and it is easy to miss.** The packages that
are *not* moving reach upward into ones that are, via parent-relative imports —
ten of them, all in `charts/`:

```
charts/chart_geometry.py       from ..fvg / ..indicators / ..strategy / ..volatility
charts/chart_volume_profile.py from ..strategy
charts/trade_chart.py          from ..indicators / ..trendlines / ..volatility
charts/trade_chart.py          from .. import levels
```

Every target lands in `market/`, so all ten need `..X` → `swingbot.core.market.X`.
`trade_chart.py`'s `from .. import levels` is the package-attribute form again,
in relative dress. Note that four of the ten are in `trade_chart.py`, which v25
edits — another reason v26 waits for it.

Absolute imports make the whole rewrite mechanically verifiable: afterwards,
`grep -rE '^\s*from \.\.?[a-z]' swingbot/core/` returns nothing but same-package
imports inside `analytics/`, `charts/`, `edge/` and `scanning/`.

`validation_registry.json` moves alongside its loader into `backtesting/`, and it
**must move in the same commit**: `registry.py:13` resolves it as
`Path(__file__).with_name("validation_registry.json")`, so the two are coupled by
directory adjacency rather than by an import the rewrite would catch. This is the
only `__file__`-relative lookup among the moving modules — the one other in
`core/` is `charts/chart_style.py`, and `charts/` does not move.

Two boundaries are deliberate and worth stating, because both look wrong at a
glance:

**`data_store` and `backtest_cache` sit side by side in `marketdata/`.** These are the
two parallel OHLCV caches that `known-traps.md` warns about — `market_data/`
keyed by timeframe, and `data/backtest_cache/` keyed by ticker. Filing them
adjacently makes the trap visible in the directory listing rather than only in a
document nobody reads before writing a cache lookup.

**`tracking/` is separate from the existing `analytics/`.** `performance.py` is
the *write* path for the trade log; `analytics/` is derived reporting computed
over closed trades. Merging them would put a 1317-line writer into a package of
pure read-side aggregation.

### `scripts/`

| Folder | Scripts |
|---|---|
| `backtest/` | `run_backtest_range`, `tune_strategy`, `tune_exit_v2`, `tune_confluence_gates`, `run_confluence_validation`, `wf_run`, `wf_components`, `permutation_test`, `ablation`, `reversal_ab`, `quarterly_revalidation` |
| `data/` | `fetch_backtest_data`, `fetch_intraday_cache`, `build_universe`, `fmp_crawl`, `migrate_market_data`, `record_option_snapshots`, `validate_data`, `fill_regime_allow`, `backfill_journal` |
| `reports/` | `shadow_parity_report`, `shadow_component_report`, `sizing_shadow_report`, `parity_exits`, `parity_sizing`, `export_analytics`, `audit_quality_score` |
| `dev/` | `testrun`, `smoke_spa`, `render_chart_fixtures`, `seed_parity_fixtures`, `dump_chart_payloads` |

This is the item with the widest blast radius, and the only one whose failures
are silent. **77 files name `scripts/*.py` paths.** They split sharply, and the
split is what makes the change tractable:

**Five are executable and break at runtime if missed:**

| Reference | Becomes |
|---|---|
| `swingbot/admin/jobs.py:202` — `os.path.join(config._PROJECT_ROOT, "scripts", "tune_strategy.py")` | `"scripts", "backtest", "tune_strategy.py"` |
| `scripts/quarterly_revalidation.py:63` — `subprocess.run([sys.executable, "scripts/fetch_backtest_data.py", …])` | `scripts/data/fetch_backtest_data.py` |
| `scripts/quarterly_revalidation.py:111` — `scripts/wf_run.py` | `scripts/backtest/wf_run.py` |
| `scripts/quarterly_revalidation.py:119` — `scripts/permutation_test.py` | `scripts/backtest/permutation_test.py` |
| `.github/workflows/deploy.yml:63` — `python scripts/testrun.py full` | `python scripts/dev/testrun.py full` |

`admin/jobs.py` is the one that matters most: it is the live subprocess the admin
UI shells out to when a user starts a tuning grid, and it is covered by
`tests/admin/test_jobs.py` and `tests/admin/test_api_v1_jobs.py`.
`deploy.yml:58` (`compileall -q swingbot bot.py admin_ui.py scripts tests`) names
the directory, not a file, and needs no change.

**The other ~72 are prose** — docstrings, comments, `CLAUDE.md` and `README.md`
command blocks, `.claude/` agent and skill definitions, `.env.example` help text,
and the `pytest.ini` header comment. Stale prose misleads the next session rather
than breaking a run, so it is swept in the same commit but is not a correctness
risk.

### `tests/`

The flat files (157 as of 2026-08-15, plus whatever v25 adds) are grouped to
mirror the new core packages —
`tests/market/`, `tests/planning/`, `tests/backtest/`, `tests/tracking/`,
`tests/data/`, `tests/edge/`, `tests/charts/`, `tests/scanning/` — with
`tests/admin/`, `tests/scripts/` and `tests/fixtures/` left where they are.

This was recommended against during design (the naming clusters are shallow —
`edge` at 11 files and `plan` at 9 are the largest — and it doubles the merge
surface against the active `v24` worktree) and included anyway at the author's
direction. Recording the tradeoff here so the next session does not re-litigate
it: the payoff is navigational only, and pytest discovers either layout.

Three failure modes to watch, in order of likelihood:

1. **`conftest.py` scoping.** A test moved one directory deeper still inherits
   `tests/conftest.py`, but anything that relied on being a *sibling* of a
   fixture module does not.
2. **Basename collisions.** With no `__init__.py` files, pytest derives module
   names from basenames, so two same-named files in different subdirectories
   abort collection with "import file mismatch". Every current test filename is
   unique, so this is safe today and becomes a constraint on future naming.
3. **Fixture paths built from `__file__`**, which silently resolve one level off.

`pytest.ini` needs no change: `testpaths = tests` covers subdirectories, and its
`norecursedirs` list already excludes `.claude/worktrees`.

### Root and docs

`DOCKER.md`, `DEPLOY_HETZNER.md` and `MANUAL_VERIFICATION_CHECKLIST.md` move
under `docs/`. `exit_v2_validation.json` and `rescue_rsi_validation.json` — two
backtest validation outputs tracked at the repo root — move to
`docs/superpowers/results/`, where 49 sibling result files already live. The
untracked `.env.bak` and `backtest_range_summary.txt` are deleted.

`README.md` is 645 lines / 46 KB across 33 `##` sections that are really three
documents: strategy concept, setup instructions, and command/feature reference.
It splits into `docs/strategy.md`, `docs/setup.md`, `docs/commands.md` and
`docs/features.md`, leaving `README.md` as an overview plus an index. `CLAUDE.md`
already instructs sessions to grep its headers rather than read it, which is a
workaround for a document that should not be one file.

## The string-literal hazard

Import statements are not the only references to module paths. **41 string
literals** across the test suite name modules directly, in
`mock.patch("swingbot.core.data...")` targets and similar:

```
8  "swingbot.core.universe      7  "swingbot.core.data
7  "swingbot.core.analytics     6  "swingbot.core.registry
4  "swingbot.core.charts        4  "swingbot.core.backtest
2  "swingbot.core.performance   2  "swingbot.core.backtest_cache
1  "swingbot.core.account
```

These are covered by the existing gate rather than being a silent failure class:
`mock.patch` resolves its target at call time and raises `ModuleNotFoundError`
when the path is stale, so a missed rewrite fails the test that uses it. They
must still be swept deliberately — the point is that the suite will catch what
the sweep misses, which is what makes the no-shims choice safe.

`tests/admin/conftest.py` uses `importlib.import_module` with names built at
runtime; it is the one place a path is assembled rather than written, and needs
reading rather than pattern-replacing.

## Sequencing

Five commits, each independently green, in this order:

1. **README split** — docs only, cannot break imports.
2. **Root and docs cleanup** — file moves plus reference updates.
3. **`scripts/` grouping** — plus all 20 referencing files, including CI and deploy.
4. **`tests/` regrouping** — plus `conftest.py` scoping fixes.
5. **`swingbot/core/` re-package** — the move, every call site, both shims deleted.

Docs and scripts lead because they cannot break an import. The core re-package
lands last so it sits at the branch tip, letting the concurrent `v24` worktree
rebase across it once rather than repeatedly.

## Verification

The gate after every commit is `python scripts/testrun.py full` (the path itself
changes at step 3 to `scripts/dev/testrun.py`), against the count recorded on a
clean `main` immediately before step 1 — **not** against the 2026-08-15 figure of
`1686 passed, 66 skipped, 0 failed`, which v25 will have moved (see "The
verification baseline moves too"). Green means `0 failed` *and* `0 xfailed`.

A changed pass count is not automatically a failure, but in this spec it is
suspicious in a way it normally is not: nothing here should add, remove or skip a
test. **A moved count means a test file stopped being collected** — the
characteristic symptom of a directory move that lost its `conftest.py` or landed
outside a `testpaths` root. Investigate any delta rather than accepting it.

After step 5, additionally run the `make check` py_compile pass over `bot.py`,
`admin_ui.py` and `swingbot/**/*.py`, which catches modules no test imports.

Step 3's five executable references are gated unevenly. `admin/jobs.py` is
covered by `tests/admin/test_jobs.py`; `quarterly_revalidation.py` by
`tests/scripts/test_quarterly_revalidation.py`. **`.github/workflows/deploy.yml`
is covered by nothing** — no test executes it — so its `testrun.py` path must be
confirmed by eye before the commit lands.

## Ordering: v26 runs last, after v24 and v25

**This spec does not execute until `v24-control-alignment` and `v25-trade-chart`
have both landed on `main`.** That ordering is a requirement, not a preference:
v26 renames the files those plans are editing, and a restructure that races an
in-flight feature turns every one of that feature's hunks into a rename conflict.

Running last removes the git conflict entirely. What it does *not* remove is
staleness — v24 and v25 change the ground this spec measured.

**v24 is a non-issue.** Its 14 tasks touch `frontend/src/app/**` exclusively;
its Python footprint is empty. The only path it names outside the SPA is
`scripts/testrun.py` as its test command, and since it runs first it will have
finished using that path before step 3 renames it.

**v25 overlaps in three specific places**, all benign given the ordering:

| v25 does | v26 effect |
|---|---|
| Creates `swingbot/core/charts/trendline_fit.py` | None — `charts/` is not a moving package |
| Edits `swingbot/core/charts/{trade_chart,chart_geometry}.py` | None — same reason |
| Edits `swingbot/core/plan_store.py` | Moves it to `planning/`, after v25 is done with it |
| Creates `tests/test_trendline_fit.py`, `tests/test_trade_chart_stored_fit.py`, `tests/test_trendline_fit_persistence.py` | Step 4 must place all three |
| Edits `swingbot/admin/api_v1/market.py`, `tests/admin/conftest.py` | None — neither moves |

### The tables in this spec are inputs, not inventories

The module lists above were derived on 2026-08-15, before v24 and v25 landed.
By execution time they will be **wrong in the safe direction** — missing files
rather than naming absent ones — and the four v25 files above are only the ones
predictable today.

So the first task of the implementation plan is a **reconciliation step**, run
before any file moves:

```bash
git ls-files 'swingbot/core' | awk -F/ 'NF==3' | grep '\.py$'   # vs the core table
git ls-files 'tests'         | awk -F/ 'NF==2'                  # vs the tests grouping
git ls-files 'scripts'       | awk -F/ 'NF==2'                  # vs the scripts table
```

Any file present on disk but absent from the corresponding table is placed by the
**grouping rule**, not by guesswork, and the plan records where it went:

- **`core/`** — by what the module *owns*: fetching or caching market data →
  `marketdata/`; computing an indicator, level or signal from bars → `market/`;
  constructing or tracking a live plan → `planning/`; offline replay and
  validation → `backtesting/`; writing or reporting the trade log → `tracking/`;
  JSON, locks and delivery channels → `infra/`.
- **`tests/`** — mirrors whichever package the module under test now lives in.
- **`scripts/`** — `backtest/`, `data/`, `reports/`, `dev/` by primary purpose.

### The verification baseline moves too

`1686 passed, 66 skipped, 0 failed` is the baseline **as of 2026-08-15**. v25
alone adds at least three test files, so the number will be higher by the time
v26 runs.

The gate is therefore not the literal 1686. It is: **record the count on a clean
`main` immediately before step 1, and require every one of the five commits to
match that recorded number exactly.** `0 failed` and `0 xfailed` remain absolute.

### Worktree note

`worktree-backtest-frictions` was removed on 2026-08-15 as unused. Its branch was
**kept**: it carries two commits not on `main` (`359a25e` frictions in the v2
exit model, `210415e` per-fold progress output).

## Parallelisation

- **Sequential throughout: steps 1 → 5.** Every step edits `CLAUDE.md` and
  `README.md` to re-point paths, so no two steps have disjoint files — the first
  half of the two-part test fails before dependencies are even considered.
- **Within step 5 (parallel):** the six package moves — `marketdata/`, `market/`,
  `planning/`, `backtesting/`, `tracking/`, `infra/` — may be prepared
  concurrently, since each owns a disjoint set of source files. The call-site
  rewrite that follows is **not** parallelisable: `commands/scanning.py`,
  `admin/helpers.py` and `bot.py` each import from several of the six, so
  concurrent agents would overwrite one another in this shared working tree.
- **Within step 3 (parallel):** the four script folders are disjoint, but the
  77-file reference sweep afterwards is single-threaded for the same reason.
- **Nothing in v26 may run concurrently with v24 or v25.** They are predecessors,
  not peers — see "Ordering" above.
