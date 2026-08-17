# Structural target selection — TRAIN pre-registration (v31 Task 17)

Written and committed **before** the run, per `docs/claude/backtest-methodology.md`.

## This is a NEW pre-registration

This is not a re-run, re-ask, or loosening of any row in
`docs/claude/backtest-methodology.md`'s closed pre-registration table
(`REGIME_ALLOW`, `DATA_DRIVEN_STOPS_ENABLED`, level-lifecycle targets). It is
a different question about a different engine: plan v31
(`docs/superpowers/plans/2026-08-16-v31-structural-targets.md`) replaced
every strategy's target-pricing arithmetic (`entry ± risk * rr`, a fixed
per-strategy R:R override of 0.30–0.40) with
`plan_engine.select_structural_target` — the nearest real level beyond entry
that pays at least `MIN_RISK_REWARD_RATIO` (1.5), capped at
`MAX_RISK_REWARD_RATIO` (2.5). That arithmetic did not exist when any closed
row above was measured, so there is no prior shot to reopen.

## Hypothesis

Pricing every plan's target off a real structural level that pays at least
1.5x the plan's own risk (capped at 2.5x), instead of a fixed fraction of
risk, produces a strategy corpus with positive expectancy on TRAIN — fewer,
larger-R trades rather than many small-R ones.

## Selection rule (fixed in advance)

Per (strategy, horizon) cell:

> include iff `expectancy_r > 0` (primary) **and** `win_rate >= 50` (floor)
> **and** `N >= 30` **and** `(scratches + timeouts) <= 50%` of closed trades.

`win_rate >= 50` replaces the old `>= 80` gate. That old gate is
**mathematically incompatible with this change and is not carried over**:
break-even win rate at reward:risk ratio X is `1/(1+X)`. At the old fixed
0.30 floor that is 76.9%, which is why the old gate was set to 80% (a
comfortable margin above break-even). At the new band's floor of 1.5R,
break-even is `1/(1+1.5) = 40%`; at the cap of 2.5R it is `1/(1+2.5) =
28.6%`. Demanding 80% win rate at a 1.5R target asks for an edge no
strategy in this repo has ever shown on TRAIN — re-running the old gate
against the new engine would produce a table of failures that says nothing
about whether the new engine works, only that the old gate no longer fits
the new arithmetic. 50% is chosen the same way 80% was: a margin over
break-even (40% at the floor), fixed from arithmetic before seeing any
result, not read off a table.

`scratches + timeouts <= 50%` is carried over unchanged from the old rule.

## Windows

TRAIN only: `2020-01-01` .. `2023-12-31`. The 2024-2025 window stays tainted
for this decision (per methodology) until Task 18's one-shot VALIDATION run.

## Universe / strategies / horizons

Full watchlist (`data/watchlist.json` at run time) x all 11 strategies in
`backtest.ALL_STRATEGIES` x all 10 horizons in `HORIZONS`, `--exit-model v2
--scale-out` (the frozen exit-v2 params per strategy from the 2026-07 TRAIN
grid, unaffected by this plan — v31 only changes target *selection*, not
exit simulation).

## What "the change working" looks like (stated before seeing results)

Expected, not a red flag:
- **Trade count falls.** Fewer bars produce a candidate that clears
  `MIN_RISK_REWARD_RATIO` against a real level than always produced *some*
  entry ± risk*rr number.
- **Win rate falls substantially** (targets are 3–7x farther away than the
  old 0.30–0.40R fixed fraction).

Both are recorded as-is. **Record failures; do not retune** — a strategy
that fails this rule on TRAIN gets no VALIDATION shot (Task 18), full stop.

## Run command

```bash
python scripts/data/fetch_backtest_data.py          # cache was absent in this worktree
python scripts/backtest/run_backtest_range.py --train --exit-model v2 --scale-out --json 2026-08-17-structural-target-train.json
```

Dispatched to the `backtest-runner` subagent so per-ticker progress output
stays out of the main session context, per `docs/claude/skills-tools.md`.

## Results

*(filled in after the run — this file is committed once, before running,
with everything above; the table and observations below are appended in the
same commit as the run's own results, not a later edit to the
pre-registration itself.)*
