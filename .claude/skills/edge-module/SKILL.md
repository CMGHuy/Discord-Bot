---
name: edge-module
description: Use when adding or changing a strategy or edge module under swingbot/core/edge/ or swingbot/core/market/strategy_types.py -- registry entry, badge tier, entry-signal wiring, or where it plugs into the scan pipeline. Not for tuning an existing strategy's parameters (use backtest-gate) and not for changing how a strategy is displayed.
---

# Edge module

## Step 1 — Read the authority

`docs/claude/architecture.md` -- the module map (`core/edge/` vs
`core/market/`), the entry-signal single source, and how badges and the
registry work. This skill does not restate any of it; nothing here
substitutes for reading it.

## Step 2 — Verify every symbol before you use it

Plans and briefs invent symbols here routinely. Before citing a function,
class or dict name in code or in a plan task, confirm it exists:
`git grep -n "def <symbol>" -- "swingbot/**/*.py"`, or dispatch
`symbol-verifier` for a batch of them. A plausible-sounding name that isn't
real ships a task nobody can implement.

## Step 3 — Register once

A strategy that computes but is not registered is invisible to the scan
pipeline -- it will never alert. One registered twice scores twice, and its
paper-trade stats become uninterpretable. Check both directions before
committing: does the module actually get reached from the pipeline, and is
it reached exactly once.

## Step 4 — A new module ships WEAK

A badge tier is a measured claim, not a default a new module gets to pick.
Earning anything better than WEAK means a pre-registration -- invoke
`backtest-gate` before claiming one, never after.

## Step 5 — Check the entry signal has one source

Two paths computing the same entry is how live and backtest diverge. Confirm
the new or changed logic reads through the single entry-signal source
architecture.md names, not a second copy grown for convenience in only the
backtest or only the live scanner.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "It works in the backtest, so it's wired" | The replay harness never calls the scan engine -- a strategy can pass every backtest and still never fire live. |
| "I'll badge it after we see live results" | Live results are not a pre-registration; the badge still needs a validation run through `backtest-gate`. |
| "It's just a new parameter set on an existing strategy" | A new parameter set on an already-registered strategy is tuning, not a new module -- that's `backtest-gate`'s territory, not this one's. |

## Trigger table

Should fire: adding a new strategy module under `swingbot/core/edge/`.
Should fire: adding or changing an entry in `STRATEGY_GATES` in
`strategy_types.py`.
Should fire: wiring a new edge module into the scan pipeline so it starts
computing signals.
Should not fire: renaming a chart label or legend entry.
Should not fire: changing an alert embed's field layout or copy.
Should not fire: tuning an existing strategy's `DEFAULT_PARAMS` values.
