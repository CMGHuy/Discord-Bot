# V22 — Permutation test: nothing to permute (plan v8, Phase V4)

**Status:** closed 2026-08-04 as a **pre-registered null**. No new permutation
was run. This file records why running one would have been the wrong action,
not a skipped step.

## The rule this task was operating under

V22 was rescoped on 2026-08-03 after its original premise was struck. The
task's own Step 1 ends:

> So V22 must take route (b) and scope the test to whatever cohort V52
> actually adopts [...] If V52's ladder stops at its Stage-1 gate there is no
> adopted cohort, and V22 has nothing to permute: record that and stop, rather
> than permuting the full system to manufacture a number.

and Step 3:

> **If it fires again, stop the phase and record "no demonstrable edge"** — do
> not keep tuning. This is a legitimate ending for this plan.

Both conditions are now met. This file is the "record that and stop".

## Why there is nothing to permute

**V52's adopted set is empty.** The selectivity ladder stopped at Stage 1: no
cell, in any strategy, at any cut-flag combination, cleared the pre-registered
Wilson LB 60% gate. Best anywhere was **47.5%** (VWAP, `regime=aligned`) —
about **13 points short** of Stage 1 and **33 short** of the 80% constraint.
(`2026-08-03-v52-selectivity-ladder.md`)

**V17's sizing grid was already exhausted** before that: 1188 configs topping
out at **49.6% WR (LB 46.2%)**, three of four axes inert under the 1.75% cap
and the fourth maximised at its pre-registered *lower* bound.
(`docs/superpowers/results/v17/`)

Route (b) — "permutation-test one adopted component on a narrow scope" — is
the only feasible route, and it requires an adopted component. There is none.
Route (a), a cheaper repeated-call path in `run_folds`/`_default_run`, does
not exist. The unscoped full-system permutation is the thing E90 measured at
**300+ hours** on this hardware and declared infeasible.

Permuting the shipped defaults instead would answer a question nobody asked
and no gate reads — and would produce a number that later readers could
mistake for validation of an adopted config. That is the specific failure V22
Step 1 was rewritten to prevent.

## The "no demonstrable edge" ending, and exactly how strong it is

The ending Step 3 prescribes is reached, but it is **not** reached by a fresh
permutation. It rests on three pieces of prior evidence, and this is weaker
than the gate as originally written — stated plainly rather than dressed up:

| Evidence | What it shows | Strength |
|---|---|---|
| **G100** | p ≥ 0.05 for all 11 strategies (0.346–1.0) | A real permutation, but on the pre-v8 configuration |
| **V17** | Sizing frontier tops out at LB 46.2% | Exhaustive over its 1188-config grid |
| **V52** | Selectivity moves the frontier **1.2 points**, to LB 47.5% | Exhaustive over its pre-registered axes |

Against a measured no-skill floor of **43.4%** at the 1.75% stop, the entire
reachable frontier sits in the mid-to-high 40s. The strongest single axis was
SPY regime alignment — which the gatekeeper does not own.

**The economics say the same thing independently.** Six of eleven strategies
have a median runner of exactly **0.00R**, so a win pays 0.714R and needs
**58.3%** to break even against 45–52% observed. The system is unprofitable on
the typical trade and positive only on a thin tail.

## What is NOT claimed here

- **No new permutation p-value exists for the current configuration.** G100's
  p-values predate v8's cap, floor and exit changes. Anyone needing a p-value
  for today's code must run it; this file does not substitute for that.
- **This is not evidence that no edge could exist** — only that the two levers
  this plan pre-registered (sizing, selectivity) were searched to exhaustion
  and neither reaches the bar.
- **V22 Step 2 is not satisfied and is not ticked.** It requires
  pre-registering `p < 0.05` *before running*; nothing was run, so there is
  nothing it could honestly attach to. Ticking it would assert a
  pre-registration document that does not exist.

## Consequences for the rest of the plan

- **V18 (walk-forward)** has no candidate config to walk forward. Its adoption
  gate ("≥2 of 3 folds improve") compares a candidate against a baseline, and
  V17/V52 adopted nothing.
- **V24** would measure shipped defaults only, and its window now swallows
  TRAIN, so its headline is in-sample. It also must not be fired without an
  explicit human decision.

Both are dependency-blocked by the same empty adopted set, not by missing
work.
