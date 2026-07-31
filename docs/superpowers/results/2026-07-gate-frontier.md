# Gatekeeper v7 — frontier run (TRAIN folds)

Run: `python scripts/gate_frontier.py` · 2026-07-31 · commit `8752faa` (base) +
uncommitted G98 work · full 11-strategy run, cuts `range(0, 101, 5)`.
No tuning decisions live in this file beyond the mechanical, pre-registered
`propose_tier_cuts` output (G95) — those are proposals only, never applied to
config by code. Same replay universe as the G97 baseline census: 78-ticker
watchlist, anchored TRAIN folds (test years 2021/2022/2023), fixed
`horizon_key="2w"`, `gate_eval=True`, annotate-only (no `gate_min_tier`
filter applied to the replay itself).

`best cut` below uses the G94 constrained selector: highest-WR cut with
`n_kept >= 30` and signal loss `<= 40%`. `proposal` uses the G95 mechanical
procedure: A+ = lowest cut with `wilson_lb >= 0.80` and `n_kept >= 59`; A =
lowest cut with `wr >= baseline + 5pts` and `n_kept >= 30`.

## Headline table

| Strategy | WR @ chosen cut | Wilson LB | % kept | expectancy_r | chosen cut |
|---|---|---|---|---|---|
| EMA Crossover | no cut qualifies (N=17 pooled, below N>=30 floor at every cut) | — | — | — | — |
| VWAP | no cut qualifies — 0 closed trades in this replay | — | — | — | — |
| Fibonacci | 73.5% | 0.5535 | 82.9% | -0.025 | 70 |
| Support/Resistance | no cut qualifies — 0 closed trades in this replay | — | — | — | — |
| RSI | no cut qualifies (N=5 pooled, far below N>=30 floor) | — | — | — | — |
| MACD | no cut qualifies — 0 closed trades in this replay | — | — | — | — |
| Elliott Wave | no cut qualifies — 0 closed trades in this replay | — | — | — | — |
| MA Ribbon | 75.8% | 0.6298 | 89.9% | -0.030 | 70 |
| Break & Retest | no cut qualifies (N=19 pooled, below N>=30 floor at every cut) | — | — | — | — |
| RSI Divergence | 73.2% | 0.6504 | 87.1% | -0.028 | 70 |
| Volume Profile | no cut qualifies — 0 closed trades in this replay | — | — | — | — |

## Per-strategy detail

### EMA Crossover
Baseline (cut 0): N=17, WR=94.1%, Wilson LB=0.6924, expectancy_r=0.213.
No cut in the 0–100 sweep ever reaches `n_kept >= 30` (baseline pooled N is
already 17, below the floor) — **no cut qualifies**. `propose_tier_cuts`
agrees: no A+ candidate (`wilson_lb >= 0.80` never reached — best LB is the
baseline's own 0.6924) and no A candidate (nothing beats baseline WR + 5pts
while keeping N>=30, since every cut above 0 only shrinks the already-thin
pool). Directional-only evidence.

### VWAP
0 closed trades across all three TRAIN fold years at the fixed 2w-horizon
fallback replay (matches the G97 baseline census). Frontier, deciles, best
cut and proposal are all empty/`null` — nothing to report. This is a
limitation of the fold runner's fixed-horizon replay, not evidence VWAP
never fires live.

### Fibonacci
Baseline (cut 0): N=41, WR=68.3%, expectancy_r=-0.097. The frontier climbs
through cut 70 (N=34, WR=73.5%, Wilson LB=0.5535, expectancy_r=-0.025,
82.9% of signals kept) — this **is** the G94 best cut (only eligible cut
with N>=30 and <=40% signal loss). `propose_tier_cuts` selects the same row
for the **A** tier (WR 73.5% clears baseline+5pts=73.3% by a hair, N=34>=30);
no A+ candidate exists (Wilson LB never reaches 0.80 at any cut with N>=59 —
pooled N=41 never gets that large even at cut 0). Expectancy stays negative
even at the chosen cut, so this cut trims losers by WR but does not yet
produce a profitable filtered subset — worth flagging in the G102 decision
memo. `data/tuning_proposals/` holds two runs of this proposal (2026-07-31
12:48:20 and 12:59:22), byte-identical apart from timestamp — reproducibility
confirmed.

### Support/Resistance
0 closed trades across all three TRAIN fold years (matches G97). Nothing to
report.

### RSI
Baseline (cut 0): N=5, WR=100.0%, expectancy_r=0.34. Every cut through 90
still shows N>=1 at 100% WR (the sample never contains a loss), but N=5
pooled is far too thin to clear the N>=30 fold-gate floor — **no cut
qualifies**, and the G97 baseline census already flagged this N as
"anecdote, not evidence." `propose_tier_cuts` correctly declines (no A/A+
candidate clears `n_kept >= 30`/`59`).

### MACD
0 closed trades across all three TRAIN fold years (matches G97). Nothing to
report.

### Elliott Wave
0 closed trades across all three TRAIN fold years (matches G97). Nothing to
report.

### MA Ribbon
Baseline (cut 0): N=69, WR=75.4%, expectancy_r=-0.036. Best cut is 70
(N=62, WR=75.8%, Wilson LB=0.6298, expectancy_r=-0.030, 89.9% kept) — a
real cut (N>=30, <=40% loss) but a marginal one: WR moves only +0.4pts and
expectancy stays negative and barely changes. `propose_tier_cuts` finds
**no** A/A+ candidate — no cut beats baseline WR by the required +5pts, and
none reaches Wilson LB 0.80. The G94 "best cut" here is real but not strong
enough to earn a G95 tier proposal; the two selectors disagreeing is exactly
the intended behavior (G94 always returns the best available option under
its own floor constraints, G95 only proposes when the bar for a *tier
label* is cleared).

### Break & Retest
Baseline (cut 0): N=19, WR=78.9%, expectancy_r=0.01. Pooled N is below the
N>=30 floor at every cut in the sweep (cuts above 0 only shrink the already-
thin pool further) — **no cut qualifies**. No proposal either. Consistent
with the G97 baseline note that N=19 pooled is "thin (below the N>=30
fold-gate floor)."

### RSI Divergence
Baseline (cut 0): N=163, WR=72.4%, expectancy_r=-0.04 — the only strategy
whose pooled baseline itself clears N>=30. Best cut is 70 (N=142, WR=73.2%,
Wilson LB=0.6504, expectancy_r=-0.028, 87.1% kept): a real, well-supported
cut by sample size, but a small one — WR moves only +0.8pts and expectancy
stays negative. `propose_tier_cuts` finds no A/A+ candidate (no cut clears
baseline+5pts=77.4% while keeping N>=30 — the census already noted the
90-99 score decile is this strategy's *worst*-performing band, i.e. score is
not monotone here). This non-monotonicity is exactly what G100's permutation
test evaluates next.

### Volume Profile
0 closed trades across all three TRAIN fold years (matches G97). Nothing to
report.

## Honest summary

5 of 11 strategies (VWAP, Support/Resistance, MACD, Elliott Wave, Volume
Profile) produced zero frontier data — same fixed-horizon replay limitation
noted in the G97 census, not evidence those strategies never fire live.
Of the 6 strategies with trades, only 3 (Fibonacci, MA Ribbon, RSI
Divergence) clear the N>=30 floor at any cut; EMA Crossover, RSI and Break &
Retest never do (pooled N too thin at cut 0 already). Of those 3, only
Fibonacci earns a mechanical G95 tier proposal (A cut @ 70), and even there
expectancy stays negative post-cut — a WR-only improvement, not yet a
profitable filtered subset. No strategy in this run reaches an A+ candidate
(`wilson_lb >= 0.80` with `n_kept >= 59`) — the sample sizes here are simply
too small for that bar. This is a frontier, not a verdict: G99 (ablation),
G100 (permutation reality check) and G101 (plateau check) are what turn
these candidate cuts into decision-grade evidence, synthesized in G102.
