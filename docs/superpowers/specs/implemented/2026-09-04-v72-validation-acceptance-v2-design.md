# v72 — Validation acceptance v2: a discrimination-first gate

**Version:** ui 1.11.0 · bot 1.6.1
**Bump:** bot patch (1.6.1 → 1.6.2) — new module and CLI under `swingbot/`
and `scripts/`, no observable difference to any alert, chart or screen.
**Edge:** none (integrity) — this buys **no** edge. It changes what a future
feature must prove before it ships, and its whole value is preventing edge
that isn't there from being adopted. Naming it `expectancy` would be the
exact borrowed-language failure `document-conventions.md` warns about.

## Goal

Make the VALIDATION gate answer the question it is asked: **does this feature
raise the win rate without giving up profit?** Today it does not, and the
evidence is not theoretical — it is the most recent shot in the book.

Win rate becomes the objective; expectancy becomes a non-inferiority
constraint; three further clauses exist so the objective cannot be reached by
arithmetic instead of skill.

## Why — what the current gate actually measures

Seven findings from `backtest-methodology.md`, the v68 records, and the
measurement scripts. They are the requirements list; each maps to a clause or
a stage below.

1. **The win-rate gate measures the population, not the feature.** v68's
   component arm scored WR 34.5% → `FAIL: win_rate >= 50`. The baseline on the
   same window was **34.9%**. No filter on the confluence-scan population can
   pass an absolute 50% floor, because the population sits near 35%; and a
   feature that *cut* win rate 3pp on a population already at 55% would pass.
   The clause is close to uncorrelated with "does this help".
2. **The shot was unresolvable before it was fired.** TRAIN selected a
   +0.0104R effect. Per-trade R has SD ≈ 1R, so at N≈850 the standard error on
   a delta is ≈ ±0.05R — roughly 5× the effect. Nothing gates the spend on
   whether the hypothesis is answerable.
3. **TRAIN selection is argmax over a grid with no multiplicity control.**
   12 cells scored, winner = the maximum. `backtest_wf.plateau_report()` exists
   precisely to catch "the optimum is noise you happened to sample" and was not
   called; the TRAIN doc itself recorded that every axis improved monotonically
   toward *looser* — the signature of no effect — and the shot was spent anyway.
4. **The unit of comparison is wrong for filters.** A veto's real hypothesis is
   "the trades I remove are worse than the ones I keep". Differencing two pooled
   means over ~98%-identical populations discards nearly all the power that
   question has.
5. **Nine scripts under `scripts/backtest/` carry gate logic in several
   dialects.** `backtest_wf.gate()` is fold-based and strict;
   `measure_dcb_veto.py:324` hand-rolls four absolute clauses. Per-plan gate
   code means each plan quietly picks its own bar.
6. **The stronger instrument already exists and was skipped.** Three anchored
   folds plus `permutation_test.py` give three independent test years and a null
   distribution. v68 got one pooled two-year number.
7. **Pooled win rate is a mix statistic.** A filter that removes
   RSI-Divergence trades raises pooled WR without improving any single stratum.
   Nothing currently requires stratification.

## The gate

A feature ships on-by-default only if **every** clause passes. Clauses 1–5
apply to all features; clause 6 applies to subset-type features (filters,
vetoes, gates) and is skipped, with that skip recorded, for others.

| # | Clause | Instrument | Threshold |
|---|---|---|---|
| 1 | **Win rate improves** | mix-standardised ΔWR, cluster bootstrap over tickers | ΔWR > 0, one-sided p < 0.05 |
| 2 | **Profit rate preserved** | ΔExpR, same bootstrap, non-inferiority | lower 95% bound > −0.01R |
| 3 | **Geometry lock** | median planned RR and `avg_win_r`, component vs baseline | neither falls > 2% |
| 4 | **Volume floor** | accepted-alert count | cut ≤ 25% |
| 5 | **Not luck** | `permutation_test.py`, entry-date circular shift, n = 200 | p < 0.05 on ΔWR |
| 6 | **Mechanism** (subset features) | removed vs retained population | removed WR < retained WR **and** removed ExpR ≤ 0 |

### Why clause 3 is load-bearing

Win rate and expectancy are locked in a one-for-one trade along the *geometry*
axis: break-even WR is `1/(1+RR)`, so pulling targets from 2.0R toward 1.5R
raises win rate and buys nothing. They move *together* only along the
*discrimination* axis — removing a genuinely negative-expectancy population.
Without clause 3, "WR up, ExpR flat" is passed trivially by tightening targets,
and the repo would ship a stream of features that feel better and earn
identically. The 2% tolerance is deliberately tight: manufacturing a
meaningful WR gain by geometry needs roughly a 15% RR shift inside the
1.5–2.5 band, so 2% blocks the cheat with room to spare for honest noise.

### Why clause 6 exists

Clause 1 can pass on a lucky pooled shift. Clause 6 asks the mechanism
question directly — *are the trades you removed actually the bad ones?* — and
it is the clause that makes a passing result explainable rather than merely
significant. It is also nearly free: the removed set is already computed.

### What is deleted

The absolute `win_rate >= 50` floor leaves the **feature-acceptance** path
entirely. It remains where it means something — as a strategy-badge threshold
over a strategy's own population. `expectancy_r > 0` as an absolute clause
likewise goes: a feature is judged against the baseline it replaces, never
against zero. `N >= 15` is superseded by the MDE precheck (Stage 0), which is
the honest version of the same intent.

## Staging — the funnel

Selection never touches scoring data, and the scarce 2024–25 shot is defended
by two free gates in front of it.

```
Stage 0  MDE precheck        Minimum detectable ΔWR at the N achievable in
         (free)              VALIDATION, 80% power, α = .05, variance and
                             ticker-cluster correlation estimated from the
                             fold-train population. Achievable N is projected
                             by scaling fold-test-year N by window length —
                             never by reading a count out of 2024-25.
                             TRAIN effect below MDE ⇒ shot REFUSED and recorded
                             as "unresolvable, budget not spent".

Stage 1  Selection           Grid runs ONLY inside fold-train windows:
         (free)              2018-06..2020, 2018-06..2021, 2018-06..2022.
                             plateau_report() is mandatory and disqualifying:
                             an adopted value that is a spike, not a plateau,
                             does not proceed.

Stage 2  Walk-forward        Score on fold-test years 2021 / 2022 / 2023.
         (free, repeatable)  Gate: ≥ 2 of 3 folds with ΔWR > 0, no fold worse
                             than −1.0pp, per-fold N ≥ 30. FAIL ⇒ no shot spent,
                             component closed, budget intact.

Stage 3  VALIDATION          2024-01-01..2025-12-31. ONE shot, ever. Full
         (one shot)          clause set above. Result recorded as-is.
```

Stage 2 being **free and repeatable** is the point of the whole redesign: it is
where v68 would have died at zero cost to its budget.

Two facts this staging depends on, both verified:

- **The cache starts 2018-06-01** (`scripts/data/fetch_backtest_data.py:42`),
  so `ANCHORED_FOLDS`' nominal `2018-01-01` edge is fiction — the first fold
  trains on ~2.5 years, not 3. The constant is corrected to `2018-06-01` and
  the docstring says why. This is a documentation fix, not a behaviour change:
  the data was never there.
- **The old TRAIN window 2020-01-01..2023-12-31 overlaps fold-test years
  2021/2022/2023.** That is the contamination this staging removes: under
  v2, selection sees fold-train only, so Stage 2 is genuinely out-of-sample
  with respect to Stage 1.

## Statistics

### Cluster bootstrap over tickers — the primary instrument

Trades on one ticker share a price path and are strongly correlated. Treating
them as independent overstates power in every test the repo currently uses.
The primary instrument is therefore a **bootstrap resampling tickers, not
trades** (10,000 resamples, seeded, seed recorded in the results doc), which
prices that correlation honestly. With 89 cached tickers the resample space is
comfortable.

This one instrument serves clauses 1 and 2 and works identically whether a
feature removes trades, changes their outcomes, or both — which the
subset-vs-paired special cases below do not.

### Mix standardisation

Every ΔWR is reported twice: raw, and **standardised to the baseline arm's
(strategy × horizon) stratum weights**. The gate reads the standardised
number. This is what removes the Simpson artifact in finding 7 — a feature
that only changes which strata are represented produces a standardised ΔWR of
approximately zero and fails clause 1, correctly. The per-stratum table is
always printed, gate or no gate.

### Pairing

Arms are keyed on `(ticker, strategy, horizon_key, entry_date)`. Every field
already exists on `BacktestTrade` (`backtest.py:80-92`, which also carries
`entry`, `stop_loss` and `take_profit` — so clause 3's planned RR is
computable with **no schema change**). The key splits the population into:

- **removed** — in baseline, absent from component (drives clause 6),
- **changed** — same key, different outcome,
- **unchanged** — identical in both, carries no information about the feature
  and is excluded from the discordant diagnostics while remaining in the
  arm-level statistics.

### Sample width

Stages 2 and 3 run **89 cached tickers × 10 horizons**, replacing v68's 25 × 5
— about 7× the sample. Estimated 2–5 h wall clock for a full funnel, dispatched
to `backtest-runner`. That estimate is extrapolated from v68's 5.4-minute run
and should be **measured, not trusted**, by the first plan task that runs it.

## Implementation

Two new files; no change to any live path.

**`swingbot/core/backtesting/acceptance.py`** — owns the clause set and the
statistics. Public surface:

```python
evaluate(baseline: list[BacktestTrade],
         component: list[BacktestTrade],
         *, stage: str, seed: int = 42) -> AcceptanceResult
mde_win_rate(population: list[BacktestTrade],
             *, target_n: int, power: float = 0.80, alpha: float = 0.05) -> float
```

`AcceptanceResult` carries a per-clause verdict, the point estimate and
interval behind each, the per-stratum table, the removed/changed/unchanged
split, and an overall `PASS`/`FAIL`. It renders itself as the results-doc
table so the record and the computation cannot drift.

**`scripts/backtest/validate_component.py`** — the single CLI that runs the
funnel (`--stage mde|select|walkforward|validation`), writes the raw JSON, and
emits the results-doc skeleton with the pre-registered clause set quoted into
it before the run, not after.

**What this replaces.** A measurement script's job becomes: produce two arms
of `BacktestTrade` and hand them to `acceptance.evaluate()`. It does not get to
define what passing means. `backtest_wf.gate()` is re-metric'd to ΔWR for
Stage 2 and keeps its constants; the bespoke clause blocks in
`measure_dcb_veto.py` and the other measurement scripts are left in place as
history — they are records of shots already fired, and rewriting them would
falsify what those runs actually applied.

## Scope

**New pre-registrations only.** `RS_GATE`, `AVWAP_LEVELS_ENABLED` and the
level-lifecycle stops keep their current defaults. No re-runs, no reopened
budgets, no re-litigating closed questions — `backtest-methodology.md` is
explicit that a closed pre-registration is not reopened by a better
instrument, and a better instrument is exactly what this is.

**Non-goals:** no ML; no live-path change; no forward paper-trade validation
channel (worth its own spec later — `data/shadow_plans.jsonl` is the cleanest
data in the system, but a feature would wait months to accumulate N); no
change to the `Edge:` taxonomy.

## Known gap — `harvest` features have no gate

A `harvest` feature (exits, targets, sizing) moves geometry **by
construction** and therefore cannot pass clause 3. This spec does not write
its acceptance rule, and that is a deliberate omission rather than an
oversight: the honest rule for harvest work is expectancy-primary with a win
rate floor, which is close to the *old* gate and needs its own reasoning about
what floor and why. Until that spec exists, a `harvest` feature is out of
scope for this funnel and must say so in its own pre-registration.

`Edge: expectancy` and `Edge: volume` features are fully covered.

## Parallelisation

- **Group 1 (parallel):** the `ANCHORED_FOLDS` start-date correction, and the
  `docs/claude/backtest-methodology.md` rewrite — one file each, no shared
  symbol, and the doc describes the procedure rather than importing it.
- **Sequential:** `acceptance.py` before `validate_component.py` (the CLI
  consumes `evaluate()` and `AcceptanceResult`). Both before the
  `backtest_wf.gate()` re-metric, which consumes `acceptance`'s ΔWR helper.
  The first real funnel run comes last — it is the thing that measures the
  runtime estimate, and it needs every piece above it.
- **Group 2 (parallel), after `acceptance.py`:** the unit tests for the
  bootstrap, the MDE calculation, and the mix standardisation — three test
  files, one module under test, no shared fixture state.

## Acceptance criteria for this work

This spec ships tooling, so it is verified like tooling, not like a component:

1. **v68 is the regression fixture.** `acceptance.evaluate()` reproduces that
   run's published arm-level numbers (baseline WR 34.9% / N 859; component
   WR 34.5% / N 844) and returns `FAIL` — on clauses 1 and 6, not on the
   absolute floors v2 no longer applies. **A v2 gate that passed v68 would be
   evidence against this design.**

   The population must be regenerated: `data/v68_validation_dcb.json` is
   gitignored and is **not on this machine**, and neither is the
   `2026-09-04-v68-d9-dcb-veto-validation.log` its results doc cites — so the
   plan's first task re-runs `measure_dcb_veto.py` on the recorded cell
   (`d15_gN_voff`, ~5.4 min) and commits the arm-level trade lists as a small
   test fixture, so this can never go missing again.

   **This is not a re-run of the pre-registration.** v68's budget is spent and
   its verdict stands unchanged; regenerating a population to test an
   *instrument* makes no selection decision and reopens nothing. Nothing about
   `DEAD_CAT_BOUNCE_VETO`'s default may change as a result of this work, whatever
   the v2 gate says about it.
2. The bootstrap's coverage is checked against a synthetic population with a
   known ΔWR: the 95% interval contains the true value in ~95% of 1,000
   simulated draws.
3. `mde_win_rate()` on v68's TRAIN population, projected to that shot's
   achievable N, returns a value **larger** than v68's TRAIN effect — i.e.
   Stage 0 would have refused the shot before it was fired.
4. The mix-standardisation test: a synthetic feature that only re-weights
   strata, changing no within-stratum outcome, returns standardised ΔWR ≈ 0
   while raw ΔWR is materially non-zero.
5. `python scripts/dev/testrun.py full` — `0 failed`, `0 xfailed`, once, as the
   plan's final task.
