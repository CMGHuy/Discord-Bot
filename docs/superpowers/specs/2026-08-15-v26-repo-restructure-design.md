# v26 — Repository restructure: core packaging, scripts, tests, docs

Version: ui 1.2.3 · bot 1.1.2
Bump: `bot patch (1.1.2 → 1.1.3)` · `ui none` — the work ships running code but
zero observable difference: no endpoint, embed, chart or setting changes. The
Angular SPA is not touched at all, so its line does not move.

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
| `data/` | `data`, `data_store`, `data_refresh`, `backtest_cache`, `fmp_client`, `export_data`, `ticker_directory`, `ticker_utils`, `universe`, `watchlist` |
| `market/` | `indicators`, `candlestick_patterns`, `fvg`, `levels`, `levels_lifecycle`, `trendlines`, `volatility`, `market_context`, `signals`, `strategy`, `strategy_types`, `entry_filters`, `reversal`, `explain`, `events`, `market_events` |
| `planning/` | `plan_engine`, `plan_manager`, `plan_store`, `quality`, `account` |
| `backtest/` | `backtest`, `backtest_wf`, `backtest_scenarios`, `registry`, `shadow_log` |
| `tracking/` | `performance`, `retrospective`, `risk_metrics` |
| `infra/` | `jsonio`, `state`, `notifier`, `silent_channel` |

`scan_engine.py` and `trade_plan.py` are deleted rather than placed.

`validation_registry.json` moves alongside its loader into `backtest/`, and it
**must move in the same commit**: `registry.py:13` resolves it as
`Path(__file__).with_name("validation_registry.json")`, so the two are coupled by
directory adjacency rather than by an import the rewrite would catch. This is the
only `__file__`-relative lookup among the moving modules — the one other in
`core/` is `charts/chart_style.py`, and `charts/` does not move.

Two boundaries are deliberate and worth stating, because both look wrong at a
glance:

**`data_store` and `backtest_cache` sit side by side in `data/`.** These are the
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

The 157 flat files are grouped to mirror the new core packages —
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
changes at step 3 to `scripts/dev/testrun.py`), against the reference baseline
**`1686 passed, 66 skipped, 0 failed`**. Green means `0 failed` *and* `0 xfailed`.

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

## Known collision

The `.claude/worktrees/2026-08-14-v24-control-alignment` worktree is being
actively committed to by another session (it advanced from `7d8918e` to `c0d1cb9`
during this design). Step 5 renames most of `swingbot/core` underneath it.

Git tracks these renames well because content is unchanged — the moves are pure
`git mv` plus import-line edits, so similarity detection has an easy job. The
cost is real but bounded, and it lands on whoever owns v24. It is named here so
that it is a known cost rather than a surprise.

The `worktree-backtest-frictions` worktree was removed on 2026-08-15 as unused.
Its branch was **kept**: it carries two commits not on `main` (`359a25e`
frictions in the v2 exit model, `210415e` per-fold progress output).

## Parallelisation

- **Sequential throughout: steps 1 → 5.** Every step edits `CLAUDE.md` and
  `README.md` to re-point paths, so no two steps have disjoint files — the first
  half of the two-part test fails before dependencies are even considered.
- **Within step 5 (parallel):** the six package moves — `data/`, `market/`,
  `planning/`, `backtest/`, `tracking/`, `infra/` — may be prepared
  concurrently, since each owns a disjoint set of source files. The call-site
  rewrite that follows is **not** parallelisable: `commands/scanning.py`,
  `admin/helpers.py` and `bot.py` each import from several of the six, so
  concurrent agents would overwrite one another in this shared working tree.
- **Within step 3 (parallel):** the four script folders are disjoint, but the
  20-file reference sweep afterwards is single-threaded for the same reason.
