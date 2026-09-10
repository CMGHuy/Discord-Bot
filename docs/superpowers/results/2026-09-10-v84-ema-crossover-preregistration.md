# v84 — EMA Crossover rescue: PRE-REGISTRATION

**Written 2026-09-10, before any fold-year or VALIDATION number was seen.**

**Edge:** none (integrity) — re-measurement of an unchanged mechanism.

## Hypothesis

EMA Crossover's `WEAK` badge (2026-07-18, WR 75.0% vs the then-current 80%
floor, N=36) was measured under the fixed per-strategy reward:risk table that
plan v31 deleted. Its live mechanism — the round-2 pullback entry
(`entry_mode="pullback"`, `pullback_max_bars=15`,
`entry_filters.py:217-228`) — is **unchanged**. Re-measured under current
arithmetic (`--exit-model v2 --scale-out`) its fresh TRAIN score is
**N=55, WR 61.8%, ExpR +0.494**, which clears every badge clause.

This is not a retry of the closed pullback-entry pre-registration. That verdict
was "this mechanism fails under the fixed-R:R arithmetic"; that arithmetic no
longer exists for any strategy. The question asked here — "does this unchanged
mechanism clear the badge floor under the arithmetic that now exists?" — has
never been asked.

## Pre-registered rule

1. **Fold stability:** the FOLD-STABILITY RULE (plan part 1, Instrument note) —
   badge clauses hold in >=2 of 3 fold years (2021/2022/2023) at N>=15 each,
   no fold year with expectancy_r < -0.05.
2. **If and only if (1) PASSES:** spend the single VALIDATION shot
   (2024-01-01..2025-12-31) and record its result as-is.
3. **If (1) FAILS:** EMA Crossover is recorded closed at this stage, stays
   `WEAK`, and **no VALIDATION run is performed**.

No configuration is tuned at any point. There is no grid, because there is no
parameter being chosen.

## Results

### Fold stability (Task R2/R3)

Full 77-ticker universe (2 excluded illiquid: GC=F, SI=F — static across all
three fold years), `--exit-model v2 --scale-out --pass-wr 50`.

| Fold year | N | Win rate | ExpR | Badge clauses hold? |
|---|---|---|---|---|
| 2021 | 13 | 53.8% | +0.346 | **no — N<15** |
| 2022 | 16 | 75.0% | +0.747 | yes |
| 2023 | 13 | 53.8% | +0.513 | **no — N<15** |

**Fold-stability verdict: FAIL** — 1 of 3 fold years hold the badge clauses at
N>=15; the other two would clear WR>=50 and ExpR>0 on their own numbers, but
the rule requires N>=15 *before* a fold counts, and both sit at N=13. No fold
year has expectancy_r < -0.05 (the worst is +0.346), so the campaign's only
disqualifying condition here is the N-floor, not the direction of the result.

**CLOSED at fold stability.** EMA Crossover's fresh TRAIN score (N=55, WR
61.8%, ExpR +0.494, pooled across all four TRAIN years) does not translate into
stable single-year samples — the pooled strength is real but each individual
year's trade count (13-16) is too thin for this rule's bar. The VALIDATION
budget was **NOT spent** and remains available. Per
`docs/claude/backtest-methodology.md`, this closes the question at this stage;
reopening it needs a genuinely new mechanism, not a re-run. **Task R4 does not
run.**
