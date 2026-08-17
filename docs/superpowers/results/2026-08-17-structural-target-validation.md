# Structural target selection — VALIDATION (v31 Task 18)

The plan's **one** pre-registered, irreversible VALIDATION shot. Run
2026-08-17, held-out window `2024-01-01..2025-12-31`, dispatched to the
`backtest-runner` subagent, ~5 min total (4 sequential runs, ~65-90s each).
Results recorded as-is below; **not retuned after seeing them.**

## Which strategies got a shot, and why

Per `docs/claude/backtest-methodology.md`: "a config that fails train never
gets a validation shot." Task 17's TRAIN pre-registration
(`2026-08-17-structural-target-train.md`) found exactly 4 of 11 strategies
with at least one (strategy, horizon) cell clearing the pre-registered rule
(`expectancy_r>0`, `win_rate>=50`, `N>=30`, `excl<=50%`): **Break & Retest,
MACD, VWAP, Volume Profile.** Only these 4 ran here. The other 7 were not
touched — no command was run for them, no registry entry was written or
edited for them.

## Granularity reconciliation (stated once, applies to all 4 runs below)

Task 17's TRAIN selection rule was applied **per (strategy, horizon) cell**
— that is what actually decided which strategies earned a shot. This
VALIDATION step runs **pooled across all horizons per strategy**, via
`scripts/backtest/run_backtest_range.py --strategy "<name>"`, the existing
mechanism this repo's registry has always used (every prior validation
here, including the 2026-07-18 run already in the registry, is pooled per
strategy — `registry.get_badge` and `stamp_badge` read badges by strategy,
not by (strategy, horizon) cell). Cell-level registry emission does not
exist in this codebase; adding it would have meant writing and using new,
never-before-run code for the one irreversible shot itself — judged too
risky to introduce here. This is a deliberate, acknowledged granularity
difference from Task 17's own selection rule, not an oversight: TRAIN
answered "does this strategy have *any* real edge under the new pricing,"
VALIDATION answers "does that edge hold up pooled, out-of-sample" using the
apparatus this repo's badge system has always relied on.

`--pass-wr 50` (Task 17's pre-registered floor) was not a pre-existing CLI
flag on `run_backtest_range.py` — `build_registry_records()` already
accepted a `pass_wr` parameter (default 80.0) but nothing wired it to the
command line, so every prior run always regenerated the registry against
the old 80% floor regardless of intent. Added the flag (mechanical: one
`argparse` entry, threaded through both `build_registry_records()` call
sites and the printed report's own `passes()` check, which had the same
80.0 hard-coded independently and would otherwise have shown a
misleading `PASS`/`FAIL` column inconsistent with the registry's real
verdict) — this is infrastructure Task 18 already anticipated needing
("pass the new floor rather than editing the default"), not a parameter
tune. Smoke-tested on a throwaway custom window before the real runs (no
`--emit-registry`, so it could not touch the registry).

## Results

### Break & Retest — WEAK (was VALIDATED pre-v31)

```
Strategy                   N   Win%    ExpR  MaxDD% AvgWinR   Scr    TO  Excl%   tp2% trail%    be%   rto%  FAIL
Break & Retest           112   49.1  +0.195    -9.1  +1.567    43    13    33%   0.0%  74.5%   5.5%  20.0%

-- per horizon --
2m  16  37.5  -0.118   2w  13  46.2  +0.144   3m   4  50.0  +0.170
4m  13  46.2  +0.287   4w  31  45.2  +0.151   5m   8  50.0  +0.105
6m   5  40.0  -0.112   7m   5  40.0  -0.015   8m   9  66.7  +0.517
9m   8  87.5  +1.559
```

Win rate (49.1%) sits just under the 50% floor pooled across all
horizons, despite two individual horizons (2m at 47/N, 4m at 34/N)
clearing the bar on TRAIN. **WEAK.**

### MACD — VALIDATED

```
Strategy                   N   Win%    ExpR  MaxDD% AvgWinR   Scr    TO  Excl%   tp2% trail%    be%   rto%  PASS
MACD                     112   50.0  +0.219   -14.9  +1.565    29     3    22%  39.3%  50.0%   3.6%   7.1%

-- per horizon --
3m  30  40.0  +0.031   4m  31  48.4  +0.233   7m  17  58.8  +0.432
8m  17  58.8  +0.407   9m  17  52.9  +0.235
```

Clears all four gates pooled. **VALIDATED.**

### VWAP — WEAK (was VALIDATED pre-v31)

```
Strategy                   N   Win%    ExpR  MaxDD% AvgWinR   Scr    TO  Excl%   tp2% trail%    be%   rto%  FAIL
VWAP                      75   49.3  +0.302    -9.5  +1.768    15     3    19%   0.0%  70.3%  10.8%  18.9%

-- per horizon --
4w  44  52.3  +0.249   6m   8  25.0  -0.131   7m   9  55.6  +1.217
8m   7  57.1  +0.289   9m   7  42.9  +0.229
```

Win rate (49.3%) sits just under the 50% floor pooled, despite the TRAIN-
qualifying 4w horizon (65/N, 52.3%) individually clearing it. **WEAK.**

### Volume Profile — VALIDATED

```
Strategy                   N   Win%    ExpR  MaxDD% AvgWinR   Scr    TO  Excl%   tp2% trail%    be%   rto%  PASS
Volume Profile            32   53.1  +0.547    -5.9  +2.276    12     1    29%   0.0%  88.2%   5.9%   5.9%

-- per horizon --
7m  32  53.1  +0.547
```

7m is Volume Profile's only horizon with signals in this window (same as
TRAIN). Clears all four gates. **VALIDATED.**

## Verdict per strategy

| Strategy | TRAIN (qualifying cells) | VALIDATION (pooled) | Registry status |
|---|---|---|---|
| Break & Retest | 2m, 4m | N=112, WR=49.1%, ExpR=+0.195 | **WEAK** |
| MACD | 4m | N=112, WR=50.0%, ExpR=+0.219 | **VALIDATED** |
| VWAP | 4w | N=75, WR=49.3%, ExpR=+0.302 | **WEAK** |
| Volume Profile | 7m | N=32, WR=53.1%, ExpR=+0.547 | **VALIDATED** |

**2 of 4 strategies that earned a shot pass VALIDATION.** Both failures
missed the 50% win-rate floor by less than a point pooled (49.1%, 49.3%)
while their TRAIN-qualifying individual horizon still looks real on its
own numbers — this is exactly what pooling across all horizons (including
several that never showed a real edge on TRAIN) will do to a strategy
whose edge, if any, is concentrated in one or two horizons. Recorded as
measured; not retuned, not re-run with the individual qualifying horizon
isolated (that would be exactly the "reopen with looser conditions" the
one-shot budget forbids).

## Blast radius (checked before committing the registry, as Task 18 requires)

`registry.get_badge` is what `stamp_badge` reads for every live plan;
`confluence`-source plans (the main scan-alert pipeline) fall back to
their `primary_strategy_for` attribution's `source="strategy"` badge when
no confluence-specific record exists (`registry.py`'s own documented
fallback chain). **Two strategies' live badge status changes as of this
commit:**

- **Break & Retest**: `VALIDATED` (pre-v31, 2026-07-18, 84.5% WR under
  arithmetic that no longer exists) → **`WEAK`**. Every live plan whose
  primary confirming method is Break & Retest now renders
  `WEAK_CAUTION_TEXT` and the WEAK badge chip/color where it previously
  showed VALIDATED.
- **VWAP**: `VALIDATED` (pre-v31, 80.5% WR) → **`WEAK`**. Same effect.

This is a real finding about the new engine, shipping as measured, not
suppressed or softened. It is the honest cost of pricing targets off real
structure instead of a fixed, easy-to-clear 0.30-0.40R fraction of risk:
some strategies' apparent edge was an artifact of how cheap the old target
was to reach, not a real edge that survives a harder target.

## A separate, real finding this run surfaced but does NOT resolve

Three strategies currently hold a **`VALIDATED` badge from 2026-07-18**
that describes arithmetic **deleted by this plan's Task 14**
(`STRATEGY_RR_OVERRIDE`, the fixed 0.30-0.40R target) — **and none of them
cleared Task 17's new TRAIN rule at any horizon**: `Fibonacci`, `RSI`,
`Support/Resistance`. Their registry entries are unchanged by this commit
(correctly — they did not earn a shot) but are now stale in a stronger
sense than "old data": they describe a pricing mechanism that no longer
exists in the live code at all, yet continue to badge live plans
VALIDATED today.

**Deliberately not resolved here.** Two ways to "fix" this were both
rejected as out of scope for Task 18: (1) running a validation shot for
these 3 anyway would violate "a config that fails train never gets a
validation shot" — they did not earn one; (2) hand-editing their registry
entries to WEAK is explicitly forbidden by `registry.py`'s own docstring
("hand-edits are forbidden except the initial round-1 seed"). Whether
these 3 strategies' pre-v31 shot should be treated as still valid, spent-
but-inapplicable, or something else is a genuine open policy question this
plan did not anticipate and this task does not have standing to decide
unilaterally — raised to the human partner directly rather than resolved
by omission.

## Registry

`swingbot/core/backtesting/validation_registry.json` regenerated and
committed in the same commit as this file (`registry.py`'s docstring
forbids hand-edits). 11 `source="strategy"` records total: 4 updated
(`run_date=2026-08-17`), 7 unchanged (`run_date=2026-07-18`, including the
3 named above). 11 `source="confluence"` records unaffected by this run
(not regenerated, not touched).

## Closed pre-registration

Added to `docs/claude/backtest-methodology.md`'s closed-pre-registration
table in the same commit: structural target selection (v31) — TRAIN found
4 of 11 strategies with a qualifying cell; VALIDATION passed 2 of those 4
(MACD, Volume Profile); Break & Retest and VWAP flipped from their pre-v31
VALIDATED badge to WEAK. **Do not re-run any of this** — a new hypothesis
about a different horizon-scoped configuration would need its own,
separate pre-registration and its own shot, never a re-read of this table
with looser conditions.
