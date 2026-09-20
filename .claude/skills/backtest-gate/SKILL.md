---
name: backtest-gate
description: Use when about to run, re-run, or interpret any backtest, grid, walk-forward, fold or validation script (scripts/backtest/run_backtest_range.py, scripts/backtest/tune_strategy.py, --train, --validation, --grid, --exit-model, --scale-out) -- BEFORE the command, not after. Also when a result is about to be called a pass. Not for reading a backtest result already in context, and not for the test suite (use /gate).
---

# Backtest acceptance gate

## Step 1 — Read the authority

`docs/claude/backtest-methodology.md`. Read it before anything else here — it
owns the six-clause acceptance gate, the four-stage funnel, the TRAIN/
VALIDATION windows, the frozen constants, and the closed pre-registration
table. This skill does not restate any of that; nothing here substitutes for
reading it.

## Step 2 — Is this shot already spent?

Check the closed pre-registration table by component name before touching a
grid or a flag. `guardrails.py`'s `_rule_closed_preregistration` denies the
ALL-CAPS knobs mechanically at the Bash layer. It cannot see a lower-case
knob (`min_level_touches`, `confirm_bars`) or a strategy-plus-mechanism pair
that revisits an old idea under a new name — those close the same way, on
paper only, and the hook lets them straight through. The hook is a floor,
never the check itself.

## Step 3 — Which funnel stage is this?

Name the stage out loud before running anything: MDE precheck, fold-train
selection, fold-test walkforward, or the validation shot. Only the last one
draws on the one-shot budget. A validation run with no registered train
result behind it is not a validation — it is a train run wearing the wrong
label. The doc's funnel table says what each stage actually requires.

## Step 4 — Run it off this context

Anything past a couple of minutes goes to the `backtest-runner` subagent,
chunked per strategy, with flushed per-unit progress. Past about fifteen
minutes that progress must resolve to a percent figure in a log deleted on
completion — that is how "how far along" gets answered without raw output
landing in this session.

## The gate

Pass means every applicable clause in the doc's acceptance table cleared, on
the pre-registered N, inside the pre-registered window — not most of them,
not the interesting ones. A clause relaxed, re-scoped, or swapped after the
result is already visible is not the same test anymore; it is a new
hypothesis wearing the old pre-registration's clothes, and it needs its own
spec.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "N came in under the floor, widen the window" | That's a new pre-registration, not a rescue — the window was part of what got registered. |
| "The direction is right, just not significant" | A direction is not a result; the gate exists because non-significant directions regress to nothing on the next sample. |
| "Re-run to confirm" | Confirming is what VALIDATION was for. A second validation run on the same component spends the budget's one shot twice. |
| "This is different enough from the closed row to not count" | Say so to the human partner and let them authorise it — a session doesn't get to decide its own exception, same as `git-safety.md`'s branch rule. |

## Trigger table

Should fire: about to invoke `tune_strategy.py` with a `--grid`.
Should fire: about to say a grid cell or validation run passed.
Should fire: asked whether a flag should ship default-on after a backtest.
Should fire: about to add `--exit-model v2 --scale-out` to a
`run_backtest_range.py --validation` call.
Should not fire: reading a `results/*.md` file already open in context.
Should not fire: running the pytest suite (`/gate` covers that).
Should not fire: asking what a horizon or strategy name means.
Should not fire: reading a chart or alert embed that cites a backtest badge.
