# Code complexity limit

Referenced from the root `CLAUDE.md`.

## The rule

**Every function and method you write or change ends at cyclomatic complexity
below 15** (14 or less), as radon scores it. It applies to all Python here —
`swingbot/`, `bot.py`, `admin_ui.py`, `scripts/`, `tests/`. It is a floor under
every new implementation and every fix, not a cleanup target for later.

A limit that says "usually" gets a 200-line exception the first time a fix is
urgent. The rule holds for urgent fixes too: the split is part of the fix.

## Why this repo needs it

Complexity is where fixes go wrong here. At the 2026-09-24 audit, 47 functions
scored above 20, and the worst were the ones that matter most:

| Function | Score | Lines |
|---|---|---|
| `charts/trade_chart.generate_trade_chart` | 191 | 891 |
| `scanning/scan_run._sync_run_scan` | 108 | 827 |
| `tracking/retrospective.build_daily_retrospective` | 106 | 317 |
| `backtesting/backtest.run_backtest` | 59 | 267 |

Current scores are in `scripts/dev/complexity_baseline.json`; this table is the 2026-09-24 audit.

Nobody holds 108 branches in their head, and a unit test cannot reach one
branch without dragging in the other 107. A fix in the live scan path or the
backtest engine is exactly where a silent behaviour change costs money or
invalidates a comparison. Figures drift; re-measure rather than quote them.

## Measuring

The limit is enforced by `scripts/dev/complexity_gate.py`. radon is pinned in
`requirements.txt`, so it is installed with everything else.

```bash
python scripts/dev/complexity_gate.py             # the gate: every tracked .py file against the baseline
python -m radon cc -s -n C <files you touched>    # while iterating: every block scoring 11+, with its number
```

The gate compares every function scoring 15 or more with
`scripts/dev/complexity_baseline.json` and fails on any difference:

| Verdict | Meaning | What to do |
|---|---|---|
| `new` | a function at 15 or more that is not in the baseline | split it |
| `risen` | a baseline function scores higher than recorded | move the new logic into a helper |
| `improved` | a baseline function scores lower, still 15 or more | `--update`, same commit |
| `gone` | a baseline function is now under 15 or no longer exists | `--update`, same commit |

`improved` and `gone` fail on purpose: a baseline left at the old score would
let the function climb back to it unnoticed. **`--update` only shrinks the
baseline.** It never adds a key and never raises a score, so it cannot accept
a regression.

It runs in `python scripts/dev/testrun.py full` (a `slow` test,
`tests/dev/test_complexity_gate.py`) and as the "Complexity gate" step in the
`backend-lint-gate` CI job, where a red result blocks the production deploy. A
hotfix that lowers a legacy function's score runs `--update` in the same commit.

The local pre-commit command for this gate is `python scripts/dev/complexity_gate.py`:
the `fast` and `changed` test tiers do not run the slow real-tree test. Without
git (the Docker image has no `.git`) the gate prints `VERDICT: SKIP` and exits 0,
except when the `CI` environment variable is set: there it prints `VERDICT: FAIL`
and exits 1, so a CI job that cannot measure never passes.

### Frontend lint

The frontend side is `npm run lint`, run from `frontend/`. It is the only lint
entry point: `ng lint` (its `angular.json` target was added by the schematic) is
not used and may not honour suppressions. Today's violations are frozen in
`frontend/eslint-suppressions.json`. A fix that removes a suppressed violation
runs `npx eslint --prune-suppressions` (from `frontend/`) in the same commit,
mirroring `--update` above; otherwise ESLint exits non-zero on the now-unused
suppression. The Lint step gates `publish-image`, so a hotfix that touches
suppressed code does this too. One known unsuppressible warning (an unused
`max-len` disable in `trade-detail.store.ts`) exits 0.

**Moving or renaming a legacy function** shows up as a `gone` key plus a
`new` key with the same score, and the gate prints a hint naming the pair.
Hand-edit the key in the baseline first, then run `--update`; it refuses
while such a pair exists. The diff is one renamed key with an unchanged
score, which review confirms.

**Closures count on their own.** radon does not add a closure's branches to
its parent's score, and `radon cc` on the command line does not list
closures at all. The gate walks them and keys each as `module:outer.inner`,
so wrapping branches in an inner function is not a way under the limit.
Comprehensions are counted in the function that contains them.

## Getting under the limit

- **Split at a real seam**: gather → decide → render, or validate → compute →
  persist. Each piece takes values and returns values, so it can be tested
  alone. A pure helper is the goal.
- **Table-drive an `if/elif` chain** keyed on a value: a dict of
  `key -> handler` costs one branch however many keys it has.
- **Guard clauses**: return early on the boring cases so the main path is not
  nested four deep.
- **Name what a condition means.** `if _is_stale(bar, now):` beats a
  three-clause boolean, and the helper carries its own score.

What does not count as splitting: a helper that takes ten parameters and hands
back nine of them, a chain of lambdas or one giant comprehension holding the
same branches, or a `# noqa`. If the pieces cannot be named for what they do,
the seam is wrong; look for another.

## Legacy functions already at 15 or more

`scripts/dev/complexity_baseline.json` is the record of which functions are
legacy and at what score. A function not in it has no allowance.

Do not raise a legacy function's score, and do not grow it: put your new
logic in a helper under the limit and call it. Fully decomposing a legacy
function is its own commit, never smuggled into a fix.

## A refactor must not change behaviour

Splitting a function for this rule is a refactor: same inputs, same outputs.

- Have tests around it **before** you start. If there are none, write
  characterization tests against the current behaviour first (for a chart,
  compare the rendered image bytes before and after).
- Refactors and behaviour changes go in **separate commits**, so a regression
  bisects to one or the other.
- Whether a refactor bumps `VERSION.json` follows `working-conventions.md`
  (the test is observable difference, not diff size); never bump to mark one.
- Anything under `swingbot/core/market/`, `edge/`, `scanning/`, `planning/` is
  also under the NO-LOOKAHEAD rule, and a decomposition that could move a
  backtest number goes through `backtest-gate`. Byte-identical output is the
  bar, not "close".

## When a plan task conflicts

A plan written before this rule may spell out one big function. The rule wins:
split the function, keep the plan task's behaviour and its acceptance test.
