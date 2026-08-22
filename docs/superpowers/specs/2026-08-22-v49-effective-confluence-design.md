Version: ui 1.8.0 · bot 1.3.2
Bump: bot minor (1.3.2 → 1.4.0) — changes what `count_confirming_strategies`
returns for every scenario, which moves both the `MIN_TARGET_CONFLUENCE_COUNT`
gate and the confidence base level. Observably different alert stream. `ui`
none (the Settings page renders the new Field automatically; no new page).
Edge: expectancy — the mechanism removes a negative-expectancy population
(scenarios whose confluence count is inflated by redundant detectors) rather
than extracting more R from the ones that survive.
Origin: EXTERNAL — HKUDS/Vibe-Trading, read 2026-08-22, now vendored
(untracked, gitignored) at `Vibe-Trading-main/` in this repo's root. The
matrix→scalar reduction is
adapted from its `agent/backtest/regime.py` (rolling correlation matrix reduced
to an edge-density scalar); the permutation control is from
`agent/src/factors/bench_runner_strict.py` (same-universe random control,
Harvey-Liu-Zhu 2016). Not measured on this repo's data before adoption.
**Revert lever:** `EFFECTIVE_CONFLUENCE_ENABLED = false`. That flag is the only
way this document can change trading behaviour, it ships default-off, and it
flips to `true` only on a passed VALIDATION shot. Setting it back to `false`
restores the pre-v49 alert stream exactly — no data migration, no code revert.

# Effective confluence count

## Problem

`levels.count_confirming_strategies` (`swingbot/core/market/levels.py:463`)
returns `len(families)` — an unweighted count of how many of the 12 entries in
`ALL_STRATEGY_FAMILIES` (`levels.py:448`) put their own predicted level within
`CONFLUENCE_DEVIATION_PCT` of the scenario's target. That integer is the single
most load-bearing number in the scan pipeline. It is:

- the `MIN_TARGET_CONFLUENCE_COUNT` gate (`config.py:167`, default `2`), applied
  in `scanning/engine.py:1139` **before** confidence is computed at all;
- the confidence base level, `max(1, min(5, target_confluence[0]))`
  (`engine.py:1090`, and `confidence.py` Step 1);
- computed a second time for the stop (`engine.py:1079`).

The count treats all 12 families as equally independent votes. They are not.
EMA, VWAP, AVWAP, Bollinger Bands, Donchian Channel and Rolling S/R are all
moving-window price-envelope derivations over the same close series; Fibonacci,
Zigzag Pivot and Floor Pivot are all swing-extreme derivations over the same
pivots. Several of these co-locate by construction, not by corroboration. A
scenario reported as "5 strategies confirm" can be two independent observations
counted five times.

This matters because the confluence-scan population is the only negative one in
the book — **53.5% WR / −0.171R over 4641 trades**, the largest population
recorded (`results/2026-07-pooled-validation.md`, VALIDATION 2024–25; quoted as
recorded, not re-derived here). If the count that admits those trades is
inflated by redundancy, the gate is admitting scenarios that never had the
corroboration the number claimed.

The repo has already accepted this principle one level shallower. v35 collapsed
every per-anchor AVWAP label back into a single `AVWAP` family precisely so the
method count would not "inflate 1-for-1 with however many anchors this ticker
happens to have" (`levels.py:403-410`) — described there as "the exact trap this
plan's Global Constraints forbid". This spec applies the same correction one
layer up, between families rather than within one.

The idea is borrowed from HKUDS/Vibe-Trading's `backtest/regime.py`, which
reduces a rolling correlation matrix to a scalar by asking what fraction of
pairs are genuinely distinct, on the premise that correlated things are one
thing and not many. We already apply that reasoning at portfolio level —
`edge/correlation.py` opens with "three 'different' trades that are 0.9-
correlated are one trade at 3x size" — and have never applied it at the
confluence level, which is where the losses are.

## Non-goals

- **Not a new detector.** No family is added, removed, or re-tuned. The 12
  sources and `CONFLUENCE_DEVIATION_PCT` are untouched; only the reduction from
  "which families landed" to "how many independent votes is that" changes.
- **Not ML, and nothing fitted at runtime.** The redundancy matrix is measured
  once on TRAIN and frozen as a module constant, in the style of every other
  `edge/` component ("transparent arithmetic -- no ML, no fitted black boxes",
  `edge/__init__.py`). `swingbot/` imports no estimator.
- **Not a re-opening of any closed pre-registration.** This touches neither
  `REGIME_ALLOW`, `AVWAP_LEVELS_ENABLED`, `RS_GATE`, nor v31 structural targets.
  It is a new mechanism with its own hypothesis and its own one-shot budget.
- **Not a gate loosened anywhere.** Acceptance stays `win_rate >= 50`,
  `expectancy_r > 0`, `N >= 30` (train) / `N >= 15` (validation). `N_eff <= N`
  always, so the gate can only ever become stricter — this spec cannot buy a
  win-rate number by admitting more trades.
- **No change to `!check <horizon> <min_strategies>`.** The per-run override
  keeps its current meaning against whichever count is live.

## Design

### 1. The redundancy matrix

A symmetric 12×12 matrix `R` over `ALL_STRATEGY_FAMILIES`, where `R[i][j]` is
the measured probability that family `j` lands within `CONFLUENCE_DEVIATION_PCT`
of a price given that family `i` did, over the TRAIN window (2020-01-01 …
2023-12-31) and the full scan universe. `R[i][i] = 1` by definition. The matrix
is symmetrised as `(R[i][j] + R[j][i]) / 2` so the reduction is order-free.

Measured once by a script, then **pasted into the module as a literal constant
table** with the measuring commit hash in a comment. Nothing reads a data file
at scan time; the constant is auditable by eye and by the fold harness, and it
cannot drift between the bot and a backtest.

### 2. The reduction

Given the set `F` of families that landed, with `N = |F|`:

```
N_eff = N² / Σ_{i∈F} Σ_{j∈F} R[i][j]
```

This is the participation ratio — the effective number of independent bets. It
behaves correctly at both ends: if every present family is mutually independent
(`R[i][j] = 0` for `i≠j`) the denominator is `N` and `N_eff = N`; if all are
perfectly redundant (`R[i][j] = 1`) the denominator is `N²` and `N_eff = 1`. It
is monotone in `N` and bounded by `1 <= N_eff <= N`.

The integer the pipeline consumes is `floor(N_eff)`, pre-registered as `floor`
rather than `round` because the gate should fail closed: a scenario at 2.9
effective votes has not earned a 3.

### 3. Wiring

`count_confirming_strategies` keeps its signature and its `(count, families)`
return shape. Behind `EFFECTIVE_CONFLUENCE_ENABLED` (new `config.py` Field,
`type="bool"`, **default `false`**) it returns `floor(N_eff)` in slot 0; the
family-name list in slot 1 is unchanged, so every embed, chart and log line that
names the confirming families keeps working untouched.

Both consumers move together, deliberately. `confidence.py:41` documents the
invariant that the gate and the confidence base level "can never disagree about
what 'N strategies confirmed this' means"; splitting them would be a worse bug
than the one being fixed. `stop_confluence` (`engine.py:1079`) uses the same
function and therefore changes with it.

The flag check sits **outside** any `try`, following the `AVWAP_LEVELS_ENABLED`
precedent at `levels.py:352`, so a missing or renamed Field fails loudly instead
of silently disabling the component forever.

### 4. Why it ships dark

This changes the count for every scenario, which moves the gate and the
confidence score together. That is a signal-quality change, not an additive
annotation — the same reason v35's twelfth source shipped dark for weeks. It
goes on only if the pre-registration below clears.

## Pre-registration

Written before any data contact, per `docs/claude/backtest-methodology.md`.

**Hypothesis.** Discounting confluence votes by measured inter-family redundancy
raises pooled expectancy on the confluence-scan population, because the
population's negative expectancy is partly composed of scenarios whose raw count
overstated their corroboration.

**Instrument.** `scripts/backtest/measure_effective_confluence.py`, purpose-built.
The replay harness in `run_backtest_range.py` never calls `scanning/engine.py`
and therefore cannot see this component — the same trap v34's RS gate hit, where
the measurement had to be made with a dedicated script
(`measure_rs_gate_effect.py`) and the plan record says so explicitly. Assume the
same here; the plan's first task is to confirm it rather than inherit it.

**Grid (TRAIN only, and deliberately tiny).** Every additional cell is another
draw whose maximum is what gets reported, so the grid is three cells:
`MIN_TARGET_CONFLUENCE_COUNT ∈ {2, 3}` against `EFFECTIVE_CONFLUENCE_ENABLED
∈ {false, true}`, with the `false` arm at the shipped default `2` as the single
baseline. No threshold inside the reduction is tuned — `floor` and the
participation ratio are both fixed by this document.

**Fold gate.** The existing `backtest_wf.ANCHORED_FOLDS` gate, unchanged:
`GATE_MIN_IMPROVING_FOLDS = 2`, `GATE_MAX_DEGRADATION_R = 0.05`,
`GATE_MIN_N_PER_FOLD = 30`.

**Permutation control — the clause that makes this different.** Clearing a
zero-benchmarked gate is not sufficient evidence here. The redundancy matrix has
12 free-ish rows and could raise expectancy by accidentally down-weighting
whichever families happen to be unprofitable in-sample, which is a fitted
result wearing a mechanism's clothes. So:

- **Null:** the family-redundancy structure carries no information about which
  targets work.
- **Control:** apply a random permutation π to the family labels of the frozen
  matrix (family `i` inherits family `π(i)`'s row and column, preserving the
  matrix's whole distribution of values and its symmetry), recompute `N_eff` for
  every scenario, and re-run the identical TRAIN measurement. `K = 200`
  permutations, seeded and recorded.
- **Rule:** the real matrix's pooled ΔExpR must exceed the **95th percentile**
  of the 200 permuted ΔExpR values. Beating zero is not enough; it must beat its
  own shuffle on the same population.

This is lifted from Vibe-Trading's `src/factors/bench_runner_strict.py`, whose
stated finding is that a raw IC/t-stat gate benchmarked against zero passes
almost any factor at some parameter setting, and that only 1 of 12 factors
survived a same-universe random control. Our gates are all zero-benchmarked
today, and v34's RS gate is the standing example of the cost: it passed
VALIDATION at +1.17pp with overlapping Wilson intervals and the record correctly
says "not a demonstrated edge". A permutation control turns that sentence into a
number.

**VALIDATION (one shot, only if TRAIN clears both the fold gate and the
permutation control).** Pooled over the confluence-scan population, 2024–2025:

1. `expectancy_r` strictly greater than the `false` arm's, and `> 0` in absolute
   terms;
2. `win_rate >= 50`;
3. `N >= 15`;
4. **Volume guard:** alert-count reduction `<= 25%` versus the `false` arm. The
   mechanism is meant to remove a bad sub-population, not to shrink `N` until
   the ratio looks good. Breaching this fails the shot even if 1–3 pass.

Results recorded as-is in `docs/superpowers/results/`, with the permutation
distribution's percentiles in the table. A failure closes the component; it does
not earn a re-run at a looser threshold.

## Testing

- `test_effective_confluence.py` — the reduction as pure arithmetic: identity
  matrix gives `N_eff == N`; all-ones gives `N_eff == 1`; `N=0` and `N=1` return
  `0` and `1`; monotonicity, `1 <= N_eff <= N` over random symmetric matrices;
  `floor` applied at the boundary (2.999 → 2).
- Matrix invariants — symmetric, unit diagonal, every entry in `[0, 1]`, exactly
  12×12, and its family order matches `ALL_STRATEGY_FAMILIES` element-for-element
  (an ordering drift here silently mislabels every weight).
- Flag-off equivalence — with `EFFECTIVE_CONFLUENCE_ENABLED = false`,
  `count_confirming_strategies` returns exactly what it returns today, asserted
  against fixtures, not by inspection.
- Missing-Field loudness — a renamed config Field raises rather than degrading
  to off (the `levels.py:352` precedent).
- Slot-1 stability — the family-name list is byte-identical with the flag on and
  off, so embeds and charts are unaffected.

Run with `python scripts/dev/testrun.py file tests/test_effective_confluence.py`
while iterating; `full` before the closing commit. Note the scan pipeline touch
means `fast` auto-escalates.

## Drive-by

`config.py:172-173`'s help text for `MIN_TARGET_CONFLUENCE_COUNT` enumerates the
families and says "10 total". `ALL_STRATEGY_FAMILIES` has held **12** since AVWAP
(v35) and Volume Profile were added. Fix the string in the same commit that adds
the new Field; it is user-visible on the Settings page.

## Parallelisation

- **Group 1 (parallel):** the measurement script
  (`scripts/backtest/measure_effective_confluence.py`) and the pure-arithmetic
  reduction plus its test file — disjoint files, and the reduction's contract
  (`n_eff(families, matrix) -> float`) is fixed by §2 of this document, so
  neither waits on the other to learn it.
- **Sequential:** the frozen matrix constant lands only after the script runs
  (it is that script's output). The `levels.py` wiring and the `config.py` Field
  come after the constant, because they consume it. The TRAIN grid, the
  permutation control and the VALIDATION shot are strictly ordered — each is
  gated on the previous one clearing, and running the shot early spends the
  budget on a component that had not earned it.
- **Sequential for a second reason:** `levels.py`, `config.py` and
  `engine.py` are each touched by exactly one task, but this working tree is
  shared with concurrent sessions. Two agents on `levels.py` overwrite rather
  than merge, so the wiring is one task, not three.
