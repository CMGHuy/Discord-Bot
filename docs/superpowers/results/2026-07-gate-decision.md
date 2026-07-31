# Gatekeeper v7 — TRAIN decision memo

Sources: baseline census (G97, `2026-07-gate-baseline.md`), frontier (G98,
`2026-07-gate-frontier.md`), ablation (G99, `2026-07-gate-ablation.md`),
permutation p-values (G100, in the frontier doc), plateau checks (G101,
applied here to the frontier's G94 best cuts). All TRAIN (2021-2023 fold
years, replayed against the fixed 78-ticker/2w-horizon fallback); the
2024-2025 window stays burned (owned by edge E92). Numbers reflect the
current codebase state (post-G99: `rf_stop_sweep` demoted to weight 0).

**Headline: no strategy earns a G95 A or A+ tier proposal, and G100's
permutation test found every strategy's score/outcome monotonicity
statistically indistinguishable from chance (p >= 0.05 for all 11).**
Applying G101's plateau check to the three strategies that do have a G94
"best cut" (Fibonacci, MA Ribbon, RSI Divergence) additionally shows **all
three are spikes, not plateaus** — a third independent check pointing the
same direction. This memo's conclusion follows directly: **at today's TRAIN
sample sizes, the checklist score does not yet support moving any strategy
past `shadow`/`inform` toward a config-level tier cut with confidence.**

## EMA Crossover

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (pooled N=17 never
  clears the N>=30 floor at any cut — plateau-check not applicable, no cut
  was chosen)
- Fold table (baseline only — no filtered comparison exists since no cut
  qualifies):
  | fold | N | WR | exp_r |
  |---|---|---|---|
  | 2021 | 8 | 100.0% | 0.291 |
  | 2022 | 5 | 100.0% | 0.292 |
  | 2023 | 4 | 75.0% | -0.041 |
  | pooled | 17 | 94.1% | 0.213 |
- **"A+ tier fold WR = N/A (no cut qualifies) — this does not support a
  95-class label."**
- Signals kept at chosen cuts: N/A (no cut qualifies) · permutation p = 0.815

## VWAP

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (0 closed trades
  in this replay — structural, not a scoring result)
- Fold table: N=0 in all three fold years; nothing to report
- **"A+ tier fold WR = N/A (0 trades in this replay) — this does not
  support a 95-class label."**
- Signals kept at chosen cuts: N/A · permutation p = 1.0 (degenerate, no data)

## Fibonacci

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (highest WR at
  any N>=30 cut is 71.1% at cut 65, short of baseline+5pts=73.3%;
  plateau-checked anyway on the G94 best cut: **cut 65 is a spike** — the
  widest stable plateau in the sweep centers at cut 30, not 65)
- Fold table (baseline only — no A/A+ cut exists to filter against):
  | fold | N | WR | exp_r |
  |---|---|---|---|
  | 2021 | 22 | 72.7% | -0.036 |
  | 2022 | 4 | 25.0% | -0.692 |
  | 2023 | 15 | 73.3% | -0.027 |
  | pooled | 41 | 68.3% | -0.097 |
- **"A+ tier fold WR = N/A (no cut qualifies) — this does not support a
  95-class label."**
- Signals kept at chosen cuts: N/A (no cut qualifies) · permutation p = 0.512

## Support/Resistance

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (0 closed trades)
- Fold table: N=0 in all three fold years; nothing to report
- **"A+ tier fold WR = N/A (0 trades in this replay) — this does not
  support a 95-class label."**
- Signals kept at chosen cuts: N/A · permutation p = 1.0 (degenerate, no data)

## RSI

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (pooled N=5,
  far below the N>=30 floor — anecdote per G97's own census note)
- Fold table (baseline only):
  | fold | N | WR | exp_r |
  |---|---|---|---|
  | 2021 | 2 | 100.0% | 0.34 |
  | 2022 | 1 | 100.0% | 0.34 |
  | 2023 | 2 | 100.0% | 0.34 |
  | pooled | 5 | 100.0% | 0.34 |
- **"A+ tier fold WR = N/A (no cut qualifies) — this does not support a
  95-class label."**
- Signals kept at chosen cuts: N/A (no cut qualifies) · permutation p = 1.0
  (N too thin for the correlation statistic to compute — n<10 floor)

## MACD

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (0 closed trades)
- Fold table: N=0 in all three fold years; nothing to report
- **"A+ tier fold WR = N/A (0 trades in this replay) — this does not
  support a 95-class label."**
- Signals kept at chosen cuts: N/A · permutation p = 1.0 (degenerate, no data)

## Elliott Wave

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (0 closed trades)
- Fold table: N=0 in all three fold years; nothing to report
- **"A+ tier fold WR = N/A (0 trades in this replay) — this does not
  support a 95-class label."**
- Signals kept at chosen cuts: N/A · permutation p = 1.0 (degenerate, no data)

## MA Ribbon

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (best N>=30 cut
  is WR 76.2% at cut 70, short of baseline+5pts=80.4%; plateau-checked
  anyway: **cut 70 is a spike** — the widest stable plateau centers at
  cut 35)
- Fold table (baseline only — no A/A+ cut exists to filter against):
  | fold | N | WR | exp_r |
  |---|---|---|---|
  | 2021 | 38 | 78.9% | 0.012 |
  | 2022 | 4 | 25.0% | -0.704 |
  | 2023 | 27 | 77.8% | -0.004 |
  | pooled | 69 | 75.4% | -0.036 |
- **"A+ tier fold WR = N/A (no cut qualifies) — this does not support a
  95-class label."**
- Signals kept at chosen cuts: N/A (no cut qualifies) · permutation p = 0.713

## Break & Retest

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (pooled N=19,
  below the N>=30 floor at every cut)
- Fold table (baseline only):
  | fold | N | WR | exp_r |
  |---|---|---|---|
  | 2021 | 12 | 83.3% | 0.069 |
  | 2022 | 1 | 100.0% | 0.286 |
  | 2023 | 6 | 66.7% | -0.154 |
  | pooled | 19 | 78.9% | 0.01 |
- **"A+ tier fold WR = N/A (no cut qualifies) — this does not support a
  95-class label."**
- Signals kept at chosen cuts: N/A (no cut qualifies) · permutation p = 0.346

## RSI Divergence

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (best N>=30 cut
  is WR 76.2% at cut 75, short of baseline+5pts=77.4% — the closest any
  strategy comes to qualifying, and the only cut in the whole run that
  flips expectancy positive, +0.012R; plateau-checked anyway: **cut 75 is
  a spike** — the widest stable plateau centers at cut 35, not 75)
- Fold table (baseline only — no A/A+ cut exists to filter against; this
  is the one strategy whose pooled baseline itself clears N>=30):
  | fold | N | WR | exp_r |
  |---|---|---|---|
  | 2021 | 69 | 76.8% | 0.021 |
  | 2022 | 50 | 66.0% | -0.128 |
  | 2023 | 44 | 72.7% | -0.035 |
  | pooled | 163 | 72.4% | -0.04 |
- **"A+ tier fold WR = N/A (no cut qualifies) — this does not support a
  95-class label."**
- Signals kept at chosen cuts: N/A (no cut qualifies) · permutation p = 0.617

## Volume Profile

- Chosen cuts: A+ = no cut qualifies, A = no cut qualifies (0 closed trades)
- Fold table: N=0 in all three fold years; nothing to report
- **"A+ tier fold WR = N/A (0 trades in this replay) — this does not
  support a 95-class label."**
- Signals kept at chosen cuts: N/A · permutation p = 1.0 (degenerate, no data)

## Aggregate

All-strategies WR before/after at chosen cuts: **unchanged — no strategy has
a surviving A/A+ cut to apply, so "before" and "after" are identical (0.0
pt change) at 100% signals kept** (nothing is filtered). Target band was
+3..+8 pts at <=40% signal loss: **NOT MET** — by construction, since zero
cuts survive to apply. This is not a rounding-error miss; it is the honest
result of every strategy failing at least one of the three independent
checks this plan pre-registered (G95's mechanical A/A+ bar, G100's
permutation test, G101's plateau check).

**Balanced-preset sanity check (G102 step 2):** at the current balanced
`GATE_TIER_B_CUT` default (55.0), the census/frontier data shows 97.6%-100%
of TRAIN signals for every strategy that produced trades (EMA Crossover,
Fibonacci, RSI, MA Ribbon, Break & Retest, RSI Divergence — all >=97.6%
kept at cut 55) still clear tier B. **This clears the >=30%-kept floor by a
wide margin — no loosening of the balanced preset is needed**; the default
is not starving the alert flow.

**Config changes applied:** **none.** `GATE_TIER_APLUS_CUT` (90.0),
`GATE_TIER_A_CUT` (75.0), and `GATE_TIER_B_CUT` (55.0) all stay at their
existing defaults in `swingbot/config.py` — there is no surviving,
evidence-backed cut from this chain to promote into a default, and per the
plan's own honesty rule this phase would rather change nothing than move a
number on marginal/spiky/statistically-noisy evidence. `GATE_MODE` already
defaults to `inform` (unchanged; `shadow`/`inform`/`enforce` ladder was
never touched by this evidence chain regardless of outcome — enforcement
was never on the table without cuts to enforce).

## Where the ladder tops out below target

- **RSI Divergence** is the strategy closest to a real result: the only
  pooled baseline N>=30 (163), the only cut in this whole run that turns
  expectancy positive (cut 75, N=105, +0.012R), yet it still falls short of
  the A-tier WR bar (76.2% vs. 77.4% needed) *and* fails the permutation
  test (p=0.617) *and* the plateau check flags cut 75 as a spike (stable
  center is cut 35, which the frontier shows at a much lower WR). What
  would change this: more TRAIN-comparable signal volume (this fixed
  2w-horizon/78-ticker replay caps N at 163 for the entire 2021-2023
  window) — never a looser WR/N bar. A genuinely wider historical replay
  (more tickers, more horizons exercised by the fold runner) is the honest
  lever here, not relaxed math.
- **Fibonacci and MA Ribbon** show the same shape at smaller scale: a real
  G94 best cut exists, but it is a spike (G101) on marginal evidence
  (N=38/41 and N=63/69 respectively) and does not clear the A-tier bar.
  Same lever: more N.
- **EMA Crossover, RSI, Break & Retest** never clear the N>=30 floor at any
  cut — their pooled baselines (17, 5, 19) are too thin to attempt a cut at
  all. More TRAIN signal volume is the only honest lever; there is nothing
  to retune here.
- **VWAP, Support/Resistance, MACD, Elliott Wave, Volume Profile** produced
  zero trades in this specific replay — a structural gap in the fold
  runner's fixed 2w-horizon fallback (`folds.py:_default_replay`), not
  evidence these strategies never fire. The honest fix is a fold runner
  that exercises more than one horizon per strategy (a future task), not a
  scoring change.
- **The one concrete finding from this chain that did earn a code change**
  is G99's ablation: `rf_stop_sweep` demoted to weight 0 (info-only) because
  it measurably hurt expectancy in 9 of 11 non-trivial fold observations.
  That is exactly the kind of evidence-backed change this phase is designed
  to produce — the difference between it and the tier-cut question is that
  the ablation result cleared its own pre-registered bar (negative in >=2
  folds) decisively, while none of the tier cuts cleared theirs.
