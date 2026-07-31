# Gatekeeper v7 — frontier run (TRAIN folds)

Run: `python scripts/gate_frontier.py --permutation` (G98 + G100 combined) ·
2026-07-31 · commit range `19b73a7`(G98)..`8f8f17f`(G99)..`c0c5b10`(G101) ·
full 11-strategy run, cuts `range(0, 101, 5)`. No tuning decisions live in
this file beyond the mechanical, pre-registered `propose_tier_cuts` output
(G95) — those are proposals only, never applied to config by code. Same
replay universe as the G97 baseline census: 78-ticker watchlist, anchored
TRAIN folds (test years 2021/2022/2023), fixed `horizon_key="2w"`,
`gate_eval=True`, annotate-only (no `gate_min_tier` filter applied to the
replay itself).

**Numbers below are post-G99**: `rf_stop_sweep`'s registry weight was
demoted to 0.0 by the G99 ablation commit (`8f8f17f`), which changes every
trade's `gate_score` (the denominator in `score()` no longer includes that
check). `gate_frontier.py` reruns `run_folds` fresh each invocation rather
than reusing cached scores, so this run (executed after G99 landed)
reflects the current, demoted scoring — the first version of this doc
(written between the G98 and G99 commits) described slightly different
cut-level numbers; those are superseded here. Baseline pooled N/WR per
strategy (cut 0, unaffected by scoring since it keeps everything) is
unchanged from G97/G98.

`best cut` below uses the G94 constrained selector: highest-WR cut with
`n_kept >= 30` and signal loss `<= 40%`. `proposal` uses the G95 mechanical
procedure: A+ = lowest cut with `wilson_lb >= 0.80` and `n_kept >= 59`; A =
lowest cut with `wr >= baseline + 5pts` and `n_kept >= 30`.

## Headline table

| Strategy | WR @ chosen cut | Wilson LB | % kept | expectancy_r | chosen cut |
|---|---|---|---|---|---|
| EMA Crossover | no cut qualifies (N=17 pooled, below N>=30 floor at every cut) | — | — | — | — |
| VWAP | no cut qualifies — 0 closed trades in this replay | — | — | — | — |
| Fibonacci | 71.1% | 0.5389 | 92.7% | -0.059 | 65 |
| Support/Resistance | no cut qualifies — 0 closed trades in this replay | — | — | — | — |
| RSI | no cut qualifies (N=5 pooled, far below N>=30 floor) | — | — | — | — |
| MACD | no cut qualifies — 0 closed trades in this replay | — | — | — | — |
| Elliott Wave | no cut qualifies — 0 closed trades in this replay | — | — | — | — |
| MA Ribbon | 76.2% | 0.6351 | 91.3% | -0.025 | 70 |
| Break & Retest | no cut qualifies (N=19 pooled, below N>=30 floor at every cut) | — | — | — | — |
| RSI Divergence | 76.2% | 0.667 | 64.4% | +0.012 | 75 |
| Volume Profile | no cut qualifies — 0 closed trades in this replay | — | — | — | — |

## Per-strategy detail

### EMA Crossover
Baseline (cut 0): N=17, WR=94.1%, Wilson LB=0.6924, expectancy_r=0.213.
No cut ever reaches `n_kept >= 30` (baseline pooled N is already 17) —
**no cut qualifies**. No A/A+ proposal either. Directional-only evidence.

### VWAP
0 closed trades across all three TRAIN fold years (matches G97). Nothing to
report.

### Fibonacci
Baseline (cut 0): N=41, WR=68.3%, expectancy_r=-0.097. Best cut is 65
(N=38, WR=71.1%, Wilson LB=0.5389, expectancy_r=-0.059, 92.7% kept) — real
(N>=30, <=40% loss) but modest: +2.8 WR points, expectancy still negative.
`propose_tier_cuts` finds **no** A/A+ candidate post-demotion (no cut
reaches baseline+5pts=73.3% while keeping N>=30 — the highest WR at any
N>=30 cut is 71.1% at cut 65). This differs from the pre-G99 run, where cut
70 (N=34, WR=73.5%) narrowly cleared the A bar; demoting `rf_stop_sweep`
reshuffled which trades keep or lose score at each cut, and the earlier
"clears by a hair" result did not survive re-scoring. Read: Fibonacci's
score does not currently support a tier proposal either way.

### Support/Resistance
0 closed trades across all three TRAIN fold years (matches G97). Nothing to
report.

### RSI
Baseline (cut 0): N=5, WR=100.0%, expectancy_r=0.34. N=5 pooled is far too
thin to clear the N>=30 floor — **no cut qualifies**; the G97 census already
flagged this as anecdote, not evidence.

### MACD
0 closed trades across all three TRAIN fold years (matches G97). Nothing to
report.

### Elliott Wave
0 closed trades across all three TRAIN fold years (matches G97). Nothing to
report.

### MA Ribbon
Baseline (cut 0): N=69, WR=75.4%, expectancy_r=-0.036. Best cut is 70
(N=63, WR=76.2%, Wilson LB=0.6351, expectancy_r=-0.025, 91.3% kept) — real
but marginal: +0.8 WR points, expectancy stays negative. `propose_tier_cuts`
finds no A/A+ candidate (nothing beats baseline+5pts=80.4%, nothing reaches
Wilson LB 0.80).

### Break & Retest
Baseline (cut 0): N=19, WR=78.9%, expectancy_r=0.01. Pooled N is below the
N>=30 floor at every cut — **no cut qualifies**. No proposal either.
Consistent with the G97 baseline note that N=19 is thin.

### RSI Divergence
Baseline (cut 0): N=163, WR=72.4%, expectancy_r=-0.04 — the only strategy
whose pooled baseline clears N>=30. Best cut is now 75 (N=105, WR=76.2%,
Wilson LB=0.667, expectancy_r=**+0.012**, 64.4% kept) — the single cut in
this entire run where a filtered subset both clears N>=30/40%-loss AND
turns expectancy positive. This is a materially better result than the
pre-G99 run (which put the best cut at 70, N=142, WR=73.2%, expectancy
still negative) — demoting `rf_stop_sweep` moved enough trades' scores that
a stronger, previously-hidden cut became visible at 75. Even so,
`propose_tier_cuts` finds no A/A+ candidate (baseline+5pts=77.4% is not
reached by any N>=30 cut, and no cut reaches Wilson LB 0.80) — a real
G94 "best cut," not yet a G95-grade tier proposal. **G100's permutation
test (below) found this strategy's p=0.617 — nowhere near significant** —
so even this improved cut cannot be presented as proven signal at today's
sample size.

### Volume Profile
0 closed trades across all three TRAIN fold years (matches G97). Nothing to
report.

## G100: permutation reality check on the score

Run: `python scripts/gate_frontier.py --permutation` · 2026-07-31 ·
`permutation_test(trades, n=1000, seed=0)` per strategy over the same
annotate-only TRAIN trades (post-G99 scoring). Shuffles `gate_score` across
trades 1000x; `p_value` = fraction of shuffles whose score/outcome rank
correlation (`observed_rho`, Spearman-style) beats the real, unshuffled
ordering. **Pre-registered stopping rule: p >= 0.05 means the observed
monotonicity is statistically indistinguishable from a random relabeling of
scores — i.e. the score's apparent ability to separate winners from losers
could be luck, and no cut chosen from it should be trusted as
decision-grade.**

| Strategy | observed_rho | p_value | Verdict |
|---|---|---|---|
| EMA Crossover | -0.2371 | 0.815 | noise (p>=0.05) |
| VWAP | 0.0 | 1.0 | no data (0 trades) |
| Fibonacci | -0.0003 | 0.512 | noise (p>=0.05) |
| Support/Resistance | 0.0 | 1.0 | no data (0 trades) |
| RSI | 0.0 | 1.0 | noise (p>=0.05, N too thin to compute — n<10 floor in `_spearman_score_outcome`) |
| MACD | 0.0 | 1.0 | no data (0 trades) |
| Elliott Wave | 0.0 | 1.0 | no data (0 trades) |
| MA Ribbon | -0.0706 | 0.713 | noise (p>=0.05) |
| Break & Retest | 0.0809 | 0.346 | noise (p>=0.05) |
| RSI Divergence | -0.0247 | 0.617 | noise (p>=0.05) |
| Volume Profile | 0.0 | 1.0 | no data (0 trades) |

**Every single strategy's p-value is >= 0.05 — several land at or near 1.0.**
Applying the pre-registered stopping rule literally: **the gate score shows
no statistically defensible monotonic relationship with trade outcome for
ANY strategy at this sample size, in this TRAIN fold replay.** This is the
honest reading of a genuinely small-sample problem (only RSI Divergence
pooled N clears 100, and even there rho is slightly *negative* — consistent
with the census's own observation that its 90-99 score decile used to be
its worst-performing band) — it is not evidence the checklist's individual
checks are worthless, only that this replay cannot yet statistically prove
the *composite score* orders outcomes better than chance. **Per the
pre-registered rule, this phase stops here on the tuning side: G102's
decision memo must not present any frontier cut as a proven "the score
works" result** — cuts may still be recorded as directional/mechanical
proposals (as G95 already labels them), but none of them clear the bar this
permutation test was designed to enforce.

## Honest summary

5 of 11 strategies (VWAP, Support/Resistance, MACD, Elliott Wave, Volume
Profile) produced zero frontier data — same fixed-horizon replay limitation
noted in the G97 census, not evidence those strategies never fire live. Of
the 6 strategies with trades, only 3 (Fibonacci, MA Ribbon, RSI Divergence)
clear the N>=30 floor at any cut; EMA Crossover, RSI and Break & Retest
never do (pooled N too thin at cut 0 already). Post-G99 (rf_stop_sweep
demoted), **none** of the 3 earns a mechanical G95 tier proposal — RSI
Divergence's best cut (75) is the one bright spot, turning expectancy
positive (+0.012R) for the first time in this whole evidence chain, but it
still doesn't clear the A-tier bar. No strategy in this run reaches an A+
candidate (`wilson_lb >= 0.80` with `n_kept >= 59`). **G100's permutation
test then found every single strategy's p-value >= 0.05 — the pre-registered
stopping rule triggers across the board: at today's TRAIN sample sizes, no
strategy's score statistically proves it separates winners from losers
better than chance.** This is a frontier and an honest null result, not a
verdict: G99 (ablation) already found one red flag (`rf_stop_sweep`)
net-harmful and demoted it, which measurably improved RSI Divergence's best
cut; G101 (plateau check) and G102 (decision memo) proceed with this stop
explicitly on the record rather than silently presenting frontier cuts as
proven.
