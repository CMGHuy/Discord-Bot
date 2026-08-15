# v27 baseline — working notes, deleted in Task 15

Recorded from `worktree-2026-08-15-v27-repo-restructure`, branched off
`origin/main` at `88f73b7`.

## Predecessors landed (Step 1)

`2026-08-14-v24-control-alignment.md` and `2026-08-14-v25-trade-chart.md` are
**not** at the top level of `docs/superpowers/plans/` — both moved to
`implemented/` when they closed (`7fc775e` for v24, folded into
`ceb7b96 Merge branch 'worktree-2026-08-14-v25-trade-chart'` for v25). Only
`2026-08-15-v27-repo-restructure.md` and `2026-08-15-v29-versions-timeline.md`
remain live. v27 is unblocked.

## Clean tree at origin/main (Step 2)

`git status --porcelain`: no output. `origin/main..main` and `main..origin/main`:
`0` and `0`. The shared local `main` ref (worktrees share one `.git`) is exactly
`origin/main`.

## Baseline test count (Step 3)

```
VERDICT: PASS  1663 passed, 136 skipped  in 74.4s
```

**136 skipped, not the spec's example figure of 66** — expected, not a problem.
`data/backtest_cache/` is gitignored (`.gitignore:20`, zero tracked files) and
this worktree's checkout has no copy of it, so the full exit/sizing parity
matrix (`tests/test_exit_parity.py` + `tests/test_sizing_parity.py`) skips all
132 cases here instead of the ~66 a populated cache leaves passing — the same
CI behaviour documented in `docs/claude/testing-cost.md`. `0 failed` is what
this task gates on, and that held. **BASELINE: 1663 passed, 136 skipped, 0
failed, 0 xfailed** is the number every later task's suite run compares against
for regressions, not the spec's stale example.

## Reconciled inventories (Step 4)

**`swingbot/core/` — exact match, no assignment needed.** The 45 flat modules
on disk (44 `.py` files plus `__init__.py`) diff to nothing against the spec's
table: 43 modules placed into the six new packages plus `scan_engine.py` and
`trade_plan.py` (both deleted, not placed). `swingbot/core/charts/trendline_fit.py`
— v25's addition — is already inside `charts/`, which does not move; no action.

**`tests/` — true current flat count is 120, not the spec's "157 as of
2026-08-15."** That figure predates this task by definition (the spec's own
words: "measured on 2026-08-15, before v24 and v25 landed... this task
replaces them with the truth on disk"); 120 supersedes it. 162 files are
tracked under `tests/` total; the other 42 already live in `tests/admin/`,
`tests/fixtures/`, `tests/scripts/` — the three subdirectories the spec says
stay where they are. No fourth subdirectory exists yet; nothing has been
partially restructured already. v25's three test files are present and
confirmed:

- `tests/test_trendline_fit.py` → `tests/charts/`
- `tests/test_trade_chart_stored_fit.py` → `tests/charts/`
- `tests/test_trendline_fit_persistence.py` → `tests/charts/`

(assignment given directly by the plan's Task 1 text — all three test chart
code). No other flat test file is unaccounted for.

**`scripts/` — one unplanned file: `build_version_matrix.py`.** 33 flat
scripts exist on disk against the spec's table of 32
(11 backtest/ + 9 data/ + 7 reports/ + 5 dev/). The one extra,
`scripts/build_version_matrix.py`, postdates the spec entirely — it was
written the same day (2026-08-15) but after v26/v27 were authored, for the
Versions workspace (`v27` plan's sibling work, `v28`/`v29`). Assigned by the
spec's own rule ("by primary purpose"):

- `scripts/build_version_matrix.py` → `scripts/dev/`

It derives a build artifact (`swingbot/admin/version_history.json`) from git
history for the admin UI to serve — the same kind of build-support tooling as
`testrun.py` and `smoke_spa.py`, both already in `dev/`, and unlike anything
in `backtest/`, `data/` or `reports/`, none of which touch git history or
produce admin-served artifacts.

No other file, in any of the three directories, is present on disk and absent
from the spec's tables (or, for `tests/`, absent from its grouping rule's
implied coverage).
