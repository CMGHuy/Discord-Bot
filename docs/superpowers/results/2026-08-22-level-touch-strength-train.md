# v36 TRAIN result — level touch strength

**Outcome: no measured edge. VALIDATION not run. `LEVEL_TOUCH_STRENGTH` stays
default-off.**

## What Tasks 1–5 built

`find_touches` / `grade_level` (per-horizon recency-decayed rejection/break
grading, `swingbot/core/market/level_strength.py`), `Level.strength` with a
per-bar cache (`levels.py`), a strength **tiebreaker** in confluence target
selection (`plan_engine._select_target`, active only when two or more
candidates are already tied on distance-from-entry within
`TARGET_TIE_TOLERANCE_PCT=5.0` and all are touch-graded), and a v32 confidence
factor driven by the same score. All gated behind `config.LEVEL_TOUCH_STRENGTH`
(default `false`). This code is being left in place, inert — see Decision.

## TRAIN population

15 tickers (of 82) × 5 horizons (`4w, 2m, 3m, 4m, 6m`), 7 excluded for bad data
or illiquidity (frozen-feed closes: ASTS, HIMS, QBTS; bad split adjustment:
HOOD, SOFI; illiquid: GC_F, SI_F). 647 total trades, 550 evaluated
(closed-and-classified) after excluding scratches/timeouts from the win-rate
denominator per the usual convention.

Raw run logs: `2026-08-21-v36-task6-step1-arms.log`,
`-armsCD.log`, `-armD-only.log` (same directory; `*.log` is gitignored per
repo convention — these are the incremental per-ticker traces, not the
deliverable). The underlying `data/v36_train_step1.json` /
`data/v36_train_timing.json` are also gitignored (`data/v3*_*.json`, matching
v32–v35 precedent) — numbers below are copied from them verbatim.

**Caveat on provenance:** the harness script that ran these arms was not
committed anywhere in this worktree's history. The logs show genuine
incremental per-ticker execution (flushed progress lines, monotonically
increasing elapsed time, plausible per-ticker trade counts) consistent with a
real run rather than a fabricated one, and were treated as trustworthy on that
basis — but they are not reproducible from git alone. A future session
re-touching this area should write and commit a proper harness before trusting
new numbers.

## Four-arm result (Task 6 Step 1)

| Arm | Selection uses strength | Confidence factor | n (unfiltered) | Win rate | Expectancy (R) |
|---|---|---|---|---|---|
| A (baseline) | no | no | 550 | 37.09% | 0.0670 |
| B | yes | no | 550 | 37.09% | 0.0670 |
| C | no | yes | 550 | 37.09% | 0.0670 |
| D | yes | yes | 550 | 37.09% | 0.0670 |

Arms A and B are **byte-identical** — same 647 trades, same win/loss/scratch
counts. Arms C and D likewise identical to each other and to A/B on the
unfiltered population (the confidence factor doesn't change which trades are
taken, only how they're graded/filtered downstream).

Filtering C/D to `confidence_level >= 4`:

| | n (eval) | Win rate | Expectancy (R) | Alert volume vs. unfiltered |
|---|---|---|---|---|
| C/D filtered | 201 | 36.32% | 0.0057 | 37.1% (−62.9%) |

Filtering **degrades** both win rate (37.09% → 36.32%) and expectancy (0.0670R
→ 0.0057R, essentially flat) while cutting alert volume 62.9% — far past the
pre-registration's planned 30% ceiling.

## Scan-duration budget (Task 6 Step 3)

Projected full-universe (82 ticker) scan: 211.4s warm / 215.3s cold vs. a 300s
(`SCAN_INTERVAL_MINUTES=5`) budget. Holds independently of the decision below.

## Why A and B are identical, not a bug

`_select_target`'s strength tiebreak only fires when (a) two or more candidates
are tied within 5% of each other's distance from entry, on the confluence
target-selection path specifically, and (b) every tied candidate has real
touch history (`Level.strength["available"]`). That combination apparently
never occurred in this 550-trade TRAIN sample. The tiebreak is architecturally
incapable of making win rate *worse* (it only ever chooses among
already-distance-tied candidates, never overrides the primary distance
criterion) — but it also produced no measurable *better* here.

## Decision

- **Confidence factor (Tasks 5/6 arms C, D): dropped.** Measured net negative
  on TRAIN — lower win rate, expectancy collapse, alert volume cut far beyond
  the plan's own ceiling. Per "prioritise expectancy" (`CLAUDE.md`), a change
  that lowers `ExpR` is a regression regardless of what it does to win rate,
  and this one lowers both.
- **Task 6 Step 2 (tolerance_pct / half-life sweep): skipped.** The sweep only
  changes the *strength score* fed to the tiebreak; it cannot make ties occur
  more often (that's gated by `TARGET_TIE_TOLERANCE_PCT`, untouched by this
  plan). With zero observed ties in TRAIN, a 12-point grid search chasing a
  rounding-noise effect on a population that shows none is exactly the
  overfit-to-TRAIN risk `backtest-methodology.md` warns against, for no known
  payoff.
- **VALIDATION: not run.** It is a one-shot per
  `docs/claude/backtest-methodology.md`, and the pre-registration's own PASS
  bar requires win rate to *improve*. Spending that shot on a config that
  showed zero lift on TRAIN would very likely just close the door on a genuine
  future attempt at this mechanism. Better to record "no edge, as built" and
  stop here.
- **`LEVEL_TOUCH_STRENGTH` stays `default=false`.** Tasks 1–5's code
  (`find_touches`, `grade_level`, `Level.strength`, the tiebreak, the
  confidence factor) stays in the codebase, inert behind the flag — it is not
  a stub, it is a measured "doesn't help here."
- **Edge: none measured.** This closes as a documented no-go, not a shipped
  feature — see `docs/claude/backtest-methodology.md`'s closed
  pre-registration table.

## If this is revisited

The selection tiebreak's precondition (a real distance tie on the confluence
path) is rare enough in this sample that it's worth checking, before spending
more TRAIN budget, whether confluence plans with genuine near-ties are common
enough anywhere in the full 82-ticker universe to matter. If they aren't, the
mechanism is sound but the population it targets may just be too small to ever
move a pooled number, independent of tuning.
