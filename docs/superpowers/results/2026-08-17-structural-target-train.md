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

Run 2026-08-17, dispatched to the `backtest-runner` subagent, wall-clock
~7 minutes. Raw artifacts: `2026-08-17-structural-target-train-summary.txt`
(the script's own report), `2026-08-17-structural-target-train.json` (pooled
per-strategy stats), `2026-08-17-structural-target-train.log` /
`2026-08-17-fetch-backtest-data.log` (per-ticker progress, gitignored --
kept on disk in this worktree, not committed).

**Setup note:** this worktree had no `data/` directory at all (fresh
worktree). `scripts/data/fetch_backtest_data.py` needed
`data/watchlist.json` (gitignored runtime state), copied from the main
checkout before the fetch would run. 75 of 79 watchlist tickers cached; 4
failed (`CRWV`, `SNDK`: <260 bars of history; `EA`, `SPCX`: Yahoo
"possibly delisted"). Of the 78 tickers entering the backtest (75 cached +
SPY/GC=F/SI=F), 7 more were excluded by the run's own pre-existing quality
gates: `GC=F`/`SI=F` (illiquid, Task E12), `ASTS`/`HIMS`/`QBTS` (frozen
feed, Task E16), `HOOD`/`SOFI`/`QBTS` (bad split-adjust, Task E16). None of
this is a v31/methodology issue -- it is the same data-quality gate every
backtest run here already has.

### Pooled table (per strategy, all horizons combined)

```
Strategy                   N   Win%    ExpR  MaxDD% AvgWinR   Scr    TO  Excl%
EMA Crossover             53   64.2  +0.470    -3.0  +1.525    19     2    28%
VWAP                     115   43.5  +0.148   -16.0  +1.718    44     6    30%
Fibonacci                241   36.1  +0.226   -40.5  +2.274    49    57    31%
Support/Resistance       241   45.6  +0.323   -14.4  +2.048    77    24    30%
RSI                       38   23.7  -0.120   -23.7  +1.864    39     3    52%
MACD                     112   50.0  +0.151   -11.4  +1.489    73     1    40%
Elliott Wave              95   32.6  +0.203   -18.9  +2.437    21    31    35%
MA Ribbon                230   47.8  +0.273   -21.3  +1.776    73    16    28%
Break & Retest           295   47.5  +0.200   -32.4  +1.589    85    19    26%
RSI Divergence          1463   48.3  +0.240   -75.3  +1.708   443    18    24%
Volume Profile            63   50.8  +0.285    -7.0  +1.681    17     0    21%
```

The `PASS`/`FAIL` column the script itself prints uses its own
hard-coded default (`win_rate >= 80`) and is **not** this pre-registration's
rule -- every row above prints `FAIL` against that stale default, which is
expected and not evidence of anything (see "Why the old 80% gate can't be
reused" above). The verdict below applies the rule actually pre-registered.

### Applying the pre-registered rule, per (strategy, horizon) cell

The rule was pre-registered **per cell**, not pooled per strategy -- a
strategy's pooled row can look like it qualifies purely because one good
horizon is averaged in with nine bad ones (this is exactly what happened
for EMA Crossover: pooled N=53/WR=64.2%/ExpR=+0.470 looks like a pass, but
**no individual horizon has N>=30** -- the pooled N only clears the floor
by summing nine horizons that individually don't). The full 73-row
per-cell breakdown is in `2026-08-17-structural-target-train-summary.txt`.

The script's own per-cell table prints only N/Win%/ExpR, not the
scratches/timeouts split needed for the `excl<=50%` leg of the rule --
recomputed directly for the resulting candidates using the identical
`pool()`/`run_backtest()` calls the real script uses (same exit model,
scale-out, tp2 mode, frictions), scoped to just those cells so the extra
run took under a minute rather than repeating the full grid.

**5 cells clear all four gates** (`expectancy_r > 0`, `win_rate >= 50`,
`N >= 30`, `excl <= 50%`), across 4 of 11 strategies:

| Strategy | Horizon | N | Win% | ExpR | Scr+TO | Excl% |
|---|---|---|---|---|---|---|
| Break & Retest | 2m | 47 | 55.3 | +0.440 | 8+5=13 | 21.7% |
| Break & Retest | 4m | 34 | 50.0 | +0.146 | 11+1=12 | 26.1% |
| MACD | 4m | 30 | 53.3 | +0.191 | 15+0=15 | 33.3% |
| VWAP | 4w | 65 | 52.3 | +0.330 | 25+6=31 | 32.3% |
| Volume Profile | 7m | 63 | 50.8 | +0.285 | 17+0=17 | 21.0% |

Volume Profile's 7m cell **is** its pooled row (7m is its only horizon
with any signals at all in this window), so its pooled Excl%=21% already
confirmed the fourth gate without a separate recompute.

**Every other cell in the 73-row breakdown fails at least one gate** --
overwhelmingly the `win_rate >= 50` floor: Fibonacci, MA Ribbon, RSI
Divergence, Support/Resistance, and Elliott Wave never clear 50% win rate
at any horizon with N>=30 (RSI Divergence in particular sits at 44-49%
across every single horizon, consistently just under the floor). RSI fails
on both win rate and expectancy at every horizon (all N<=4 with negative
ExpR except one two-signal horizon). EMA Crossover, despite the misleading
pooled row, has zero cells with N>=30 at all.

## Observations (honest, not retuned)

- **Both predicted-in-advance effects happened.** Trade count fell
  sharply (RSI Divergence's pooled N=1463 is still large only because it
  fires far more often than any other strategy; every other strategy's
  pooled N is under 300, several under 100) and win rate fell
  substantially from the old regime's implicit ~90%+ (a 0.30-0.40R target
  is reached almost every time price moves at all) to a 24-64% range
  pooled, 0-100% per cell before the N filter removes the noise. Both are
  the change working, exactly as anticipated before this run: targets
  sit 3-7x farther away now, so fewer of them get touched, and the ones
  that do are worth far more when they hit (AvgWinR ranges 1.49-2.44R
  pooled, vs. the old regime's ~0.30-0.40R by construction).
- **4 of 11 strategies show at least one horizon with real, positive
  expectancy above the new win-rate floor.** This is a materially
  different, and much more informative, result than "the old 80% gate
  against the new engine produces all-FAIL," which is what the stale
  default column shows and is exactly the non-answer the pre-registration
  exists to avoid.
- **The other 7 strategies show no qualifying cell in this window.** RSI
  Divergence's near-universal ~48-49% win rate (never quite 50%, at every
  single horizon) is a striking, specific pattern worth naming rather
  than burying in the aggregate -- it is not noise, it is consistently a
  couple of points short everywhere. Recorded as a negative result for
  this window; not retuned, not investigated further here (that is a
  separate question from what this pre-registration asked).
- **This is a TRAIN result only.** None of the 5 qualifying cells above
  are validated, badged, or shipped by this run -- Task 18 is the one
  pre-registered VALIDATION shot each of these 4 strategies now becomes
  eligible for (a strategy with zero qualifying cells gets no shot at
  all). Nothing here changes live behavior; `swingbot/core/backtesting/validation_registry.json`
  is untouched until Task 18 runs and is committed.
