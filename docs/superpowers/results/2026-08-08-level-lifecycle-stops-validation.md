# LEVEL_LIFECYCLE_STOPS_ENABLED — VALIDATION shot (2024–2025)

**Status at time of writing: PRE-REGISTERED, NOT YET RUN.**
This section is committed *before* the run so the rule provably predates the
data. The Results and Observations sections below are empty on purpose.

## Why this shot is being spent

`LEVEL_LIFECYCLE_STOPS_ENABLED` passed its TRAIN fold gate on 2026-08-08
(`2026-08-08-level-lifecycle-folds.md`): 2 of 3 anchored folds improved, pooled
**+0.0056R**. That pass is real but thin, and it is not evenly earned — 2022
(+0.0209R) carries it while 2023 (+0.0007R) is noise-level. Per
`docs/claude/backtest-methodology.md`, a config that clears TRAIN gets exactly
one VALIDATION run, recorded as-is and never retuned after.

## Setup (fixed)

- **Window:** VALIDATION, 2024-01-01 .. 2025-12-31 (entry-date window).
- **Universe:** `--universe sp500` → 78 effective symbols (only names present in
  `data/backtest_cache/` produce a frame). Same effective set as the TRAIN fold
  shot and the P2a regime evidence.
- **Two legs, identical but for one env var:**
  - baseline — `LEVEL_LIFECYCLE_STOPS_ENABLED=false`
  - component — `LEVEL_LIFECYCLE_STOPS_ENABLED=true`
- **Command (both legs):**
  `python scripts/run_backtest_range.py --validation --universe sp500
  --exit-model v2 --scale-out --tp2 levels --json <leg>.json`
  (frictions default ON — matches the TRAIN legs and the E22 baseline tooling.)
- `LEVEL_LIFECYCLE_TARGETS_ENABLED` and `REGIME_GATES_ENABLED` stay **off** in
  both legs. Bundling them would make the result unattributable.

## Pre-registered decision rule (fixed before data contact)

Aggregate = trade-weighted across all 11 strategies, from the per-strategy JSON.

> **CONFIRMED** iff all four hold:
> 1. component aggregate `expectancy_r` **> 0**
> 2. delta = component − baseline aggregate `expectancy_r` **>= 0**
> 3. component aggregate `N` **>= 15** (the methodology's validation minimum)
> 4. component scratches+timeouts **<= 50%** of closed trades

Strength descriptor, also fixed now so the write-up cannot be spun afterwards:

| condition | verdict |
|---|---|
| delta **>= +0.0056R** (reproduces TRAIN's pooled effect or better) | CONFIRMED WITH EFFECT |
| **0 <= delta < +0.0056R** | CONFIRMED, NO MEASURABLE EFFECT |
| delta **< 0**, or any of (1)/(3)/(4) fails | NOT CONFIRMED |

**Selection is on expectancy.** Win rate is reported and never selected on —
the same rule §5.3 of the design doc fixed for P2a, for the same reason.

## Interpretation guard (committed in advance)

TRAIN localized essentially the whole effect to **2022, the bear fold**, which
is the mechanistically sensible place for it: anchoring a stop behind a level
price has actually tested and held matters most when price is repeatedly
probing support. VALIDATION 2024–2025 contains no comparable sustained
drawdown.

Therefore a **near-zero delta is the expected outcome** under the mechanism
hypothesis. That is written down *now*, before the run, because it cuts both
ways and both directions are tempting after the fact:

- A near-zero delta must be reported as **"no measurable effect out-of-sample"**.
  It must **not** be rescued as "consistent with the mechanism, so the flag is
  fine anyway" — that reasoning would confirm the component no matter what the
  number was, which makes the shot worthless.
- A near-zero delta is equally **not** disproof of the 2022 finding. The window
  lacks the conditions the mechanism needs; absence of evidence here is not
  evidence of absence.
- A **negative** delta is a real failure and ends the component: the flag stays
  default-off, permanently, for this design.

**This is the one shot.** No retune, no second window, no threshold adjustment,
no per-strategy cherry-picking after the fact.

## Results

_Empty until the run completes._

## Observations

_Empty until the run completes._
