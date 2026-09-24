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

Nobody holds 108 branches in their head, and a unit test cannot reach one
branch without dragging in the other 107. A fix in the live scan path or the
backtest engine is exactly where a silent behaviour change costs money or
invalidates a comparison. Figures drift; re-measure rather than quote them.

## Measuring

```bash
python -m pip install radon                       # once; not a project dependency
python -m radon cc -s -n C <files you touched>    # every block scoring 11+, with its number
```

Any block you wrote or changed that prints `(15)` or higher is a violation.
Radon counts closures and comprehensions, so a nested helper does not hide its
branches from the parent's score.

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
- A refactor with no observable difference does not bump `VERSION.json`
  (`working-conventions.md`: the test is observable difference, not diff size).
- Anything under `swingbot/core/market/`, `edge/`, `scanning/`, `planning/` is
  also under the NO-LOOKAHEAD rule, and a decomposition that could move a
  backtest number goes through `backtest-gate`. Byte-identical output is the
  bar, not "close".

## When a plan task conflicts

A plan written before this rule may spell out one big function. The rule wins:
split the function, keep the plan task's behaviour and its acceptance test.
