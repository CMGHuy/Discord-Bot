# LEVEL_LIFECYCLE_STOPS_ENABLED — VALIDATION shot (2024–2025)

**Status: RUN AND CLOSED, 2026-08-08. Verdict — CONFIRMED, NO MEASURABLE EFFECT.**

The rule below was committed in `e4fb75d` *before* the run (git history is the
proof) and is reproduced here unedited. Raw legs:
`2026-08-08-level-lifecycle-stops-validation-{baseline,component}.json`.

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

Aggregate, trade-weighted across all 11 strategies:

| leg | closed | N | Win% | ExpR | Scr | TO | Excl% |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 3491 | 2442 | 78.21 | +0.1068 | 1033 | 16 | 30.0% |
| component | 3474 | 2398 | 78.90 | **+0.1105** | 1058 | 18 | 31.0% |

**delta expectancy_r = +0.0037R** · delta win_rate = +0.68pp · delta closed = −17

Pre-registered clauses:

| clause | result | value |
|---|---|---|
| 1. component ExpR > 0 | PASS | +0.1105 |
| 2. delta >= 0 | PASS | +0.0037 |
| 3. component N >= 15 | PASS | 2398 |
| 4. scr+TO <= 50% of closed | PASS | 31.0% |

Delta `+0.0037R` < the pre-registered `+0.0056R` strength threshold →
**CONFIRMED, NO MEASURABLE EFFECT.**

Per strategy (reported, never selected on):

| strategy | N_b | N_c | ExpR_b | ExpR_c | delta | WR_b | WR_c |
|---|---:|---:|---:|---:|---:|---:|---:|
| Break & Retest | 306 | 295 | +0.1239 | +0.1415 | **+0.0175** | 77.5 | 79.7 |
| MACD | 134 | 139 | +0.0995 | +0.1173 | **+0.0178** | 83.6 | 84.9 |
| VWAP | 114 | 114 | +0.0663 | +0.0804 | **+0.0141** | 74.6 | 76.3 |
| Volume Profile | 85 | 82 | +0.1159 | +0.1174 | +0.0015 | 81.2 | 81.7 |
| MA Ribbon | 160 | 160 | +0.0425 | +0.0426 | +0.0002 | 77.5 | 77.5 |
| Elliott Wave | 59 | 59 | +0.0329 | +0.0329 | +0.0000 | 74.6 | 74.6 |
| Fibonacci | 174 | 174 | +0.1930 | +0.1930 | +0.0000 | 82.2 | 82.2 |
| RSI | 18 | 18 | −0.3600 | −0.3600 | +0.0000 | 50.0 | 50.0 |
| Support/Resistance | 163 | 163 | +0.1018 | +0.1018 | +0.0000 | 84.0 | 84.0 |
| RSI Divergence | 1193 | 1159 | +0.1161 | +0.1157 | −0.0004 | 77.5 | 78.0 |
| EMA Crossover | 36 | 35 | −0.0411 | −0.0451 | −0.0040 | 69.4 | 68.6 |

**Standing-gate PASS/FAIL flips between legs: 0.** No strategy changed status
under `WR>=80, ExpR>0, N>=15, excl<=50%`.

## Observations

_Written after reading the numbers; recorded as-is, not fixed._

**The verdict stands as pre-registered, and it is the weak one.** Delta is
positive, same sign as TRAIN, and roughly two-thirds of TRAIN's pooled
`+0.0056R` — but "two-thirds of an already-thin effect" is a description, not a
defence, and the threshold was fixed precisely so that this sentence could not
become the headline. **No confidence interval was pre-registered and none is
computed here**, so a delta of `+0.0037R` on a single window cannot be
distinguished from noise by this shot. That is a limitation of the design, not
a finding about the component.

**What the shot does establish, and it is not nothing: the flag does not
degrade anything out-of-sample.** Aggregate expectancy is up, win rate is up
0.68pp, no strategy flipped its standing-gate status, and the trade count moved
−0.5% (TRAIN: −0.6%) — the expected signature of a component that only *widens*
a stop under a `max_risk_pct` cap and re-derives the target to preserve the
frozen R:R. It is not buying expectancy by cutting trades.

**The interpretation guard applies and is being honoured.** TRAIN put the whole
effect in the 2022 bear fold; 2024–2025 has no comparable sustained drawdown,
so a small delta is what the mechanism hypothesis predicted. Per the guard
committed in advance, that is **not** grounds to upgrade this to a
confirmation — the prediction was made in a form that would have been satisfied
by almost any non-negative number, which is exactly why it cannot do the work
of evidence. It is equally not disproof of the 2022 result.

**The effect is concentrated, and the concentration is informative.** Four
strategies moved by exactly `+0.0000` (Elliott Wave, Fibonacci, RSI,
Support/Resistance): for these the stop anchor never fired, or never fired in a
way that changed an outcome. Three carry the whole aggregate — Break & Retest
(+0.0175), MACD (+0.0178), VWAP (+0.0141). That is coherent with the mechanism:
those three size through the ATR default, so a tested floor is a genuine
improvement on their stop, whereas Fibonacci and Support/Resistance already
size structurally off swings and levels, leaving the anchor nothing to add.
Two strategies drift slightly negative (EMA Crossover −0.0040 on N=35, RSI
Divergence −0.0004 on N=1159); neither is meaningful at those magnitudes.

**Aggregate win rate is 78.2/78.9%, below the standing gate's 80% — in both
legs.** That is a pre-existing property of the pooled 11-strategy set on this
window, not something the component caused, and the standing gate is applied
per strategy (where 0 flipped), not to the pool. Noted so a later reader does
not attribute it to the flag.

**Recommendation.** Enabling `LEVEL_LIFECYCLE_STOPS_ENABLED` by default is
*defensible* — it cleared TRAIN, it cleared every clause of this shot, and it
degrades nothing measurable. It is **not** evidence-backed as beneficial: the
honest summary is one bear-year fold on TRAIN plus a noise-level positive
out-of-sample. Whoever makes that call should make it knowing the support is
mechanistic reasoning, not a measured out-of-sample edge.

**The validation budget for this component is now spent.** No retune, no second
window, no per-strategy subset re-run. If the concentration finding above is to
be pursued (e.g. enabling the anchor only for ATR-sized strategies), that is a
*new* component with its own TRAIN evidence and its own pre-registration — not
a re-reading of this table.
