# V52 — The selectivity ladder, TRAIN only (plan v8, Phase V4)

**Status:** pre-registration written 2026-08-03 **before** the harness was run.
Everything above the "Results" heading was committed first; nothing in it is
edited once numbers exist.

**Command:** `python scripts/tune_selectivity.py --strategy "<name>" --json <out>`,
one background chunk per strategy.
**Window:** TRAIN = 1999-01-01 .. 2023-12-31. `gate_eval=True` enforces
`backtest.assert_train_only`, so a frame reaching into 2024-2025 raises rather
than silently scoring — the validation window cannot be touched from here.
**Exit model:** v2 + scale-out, **`tp2_mode=none`** (V51 Step 2's uncapped
runner, not V17's `levels`), `MAX_LOSS_CAP_ENABLED=true` at
`MAX_LOSS_PCT=1.75`, `MIN_TARGET_PCT=2.5`.

## The rule, pre-registered

Quoted from plan v8 **V6 Step 3b** (human-partner directive, 2026-08-02, as
revised the same day). This is the rule; it is not re-derived here and it is
not amended after seeing a result:

```
OBJECTIVE   maximise expectancy_r
SUBJECT TO  win_rate >= 80%          <- hard constraint
            every win >= 2.5%
            every loss <= 1.75%
            cut sooner than 1.75% when the entry thesis is already invalid
            scratches + timeouts <= 50% of closed trades
NO CEILING  no maximum on profit -- winners run on the trail, no fixed tp2
FLOOR       reject any config with win_rate < 80% regardless of expectancy
```

Reached in three pre-registered stages, each a **gate**, not a milestone:
**Stage 1 LB > 60%**, **Stage 2 LB > 70%**, **Stage 3 LB > 80%**, all on the
**Wilson lower bound** over the *independent* sample, never the point estimate.

**Adoption is on Wilson LB, never on observed WR.** V6 Step 5's math: proving
>80% needs N ≥ 29 at 95% observed, 64 at 90%, 256 at 85%. A cohort that clears
a rung on its point estimate but not its lower bound has not cleared it.

## What the entry evidence actually says, before this runs

Carried in from V17 (2026-08-03) so the expectation cannot be rewritten later:

- The full 1188-config sizing grid tops out at **49.6%** WR (LB 46.2%).
- The measured no-skill floor is **43.4%** pessimistic / 47.4% optimistic
  (`2026-08-02-v52-barrier-base-rate.md`). Four of eleven strategies sit at or
  below it after the cap.
- V52's original premise — Fibonacci at 76.6%, EMA Crossover at 65.3% — was
  measured on **uncapped** chunks and is void. Capped, those cells are 45.3%
  and 42.4%.

**No expectation is pre-registered for any rung.** The honest position is that
selectivity must carry the full 10+ points from sizing's 49.6% ceiling to
Stage 1 unaided, and nothing measured so far says it can. Inventing a
probability now, after seeing V17 fail, is the move V6 Step 4 forbids.

## The grid, pre-registered

**Selectivity axes** — all four are *post-hoc slices of one trade set*, not
separate runs. The gatekeeper annotation is evaluated at the signal bar, so a
single backtest per (strategy, cut-flag combo) yields every cell.

| Axis | Values | Source |
|---|---|---|
| gate score | deciles, cuts at 0,10,…,90 | `BacktestTrade.gate_score` (G91) |
| gatekeeper tier | A+, A, B, C | `BacktestTrade.gate_tier` |
| confluence count | 0…6 | `BacktestTrade.confluence_count` (V52) |
| regime alignment | aligned / opposed / all | `edge/regime2.regime_series` on SPY vs `direction` |

**Cut-flag axis** — V51 Step 3's three predicates, crossed as a full 2³:

| Flag | Config |
|---|---|
| thesis invalidation | `EARLY_CUT_THESIS_ENABLED` |
| time stop | `EARLY_CUT_TIME_ENABLED` |
| adverse excursion | `EARLY_CUT_MAE_ENABLED` |

**11 strategies × 8 flag combos = 88 backtest runs**, each over the 77-ticker
watchlist × 10 horizons, every selectivity cell sliced from those in memory.

### Reported per cell, all of it

`N`, **independent N** (V49's reuse correction — a selective cohort is *more*
exposed to horizon reuse, not less), observed WR, **Wilson LB**, ExpR, the
realised-loss distribution against the 1.75% cap, median **runner** hold, and
the **runner-leg R distribution**. The last is not optional: V51 Step 2
measured that with `tp1_fraction` frozen at 0.5 the break-even win rate swings
**41.2% → 58.3%** purely on runner performance, straddling the 43.4% no-skill
floor, so a blended ExpR cannot say whether the economics work at all.

### Three choices recorded before the run

- **Score and tier are not independent** — tier is a function of score, so
  gridding both is partly redundant. Both are reported anyway because tier is
  what production enforces and score is where the frontier lives. Neither is
  treated as confirming the other.
- **`rr` is not an axis.** V17 measured that against a capped stop it cannot
  move the target below `rr = MIN_TARGET_PCT / MAX_LOSS_PCT` = **1.4286**, and
  above it only by overriding the floor. Gridding it would manufacture
  duplicate rows, exactly as it did in V17.
- **Multiple comparisons are real here.** 10 score cuts × 4 tiers × 7
  confluence counts × 3 regime states × 8 flag combos is ~6700 cells per
  strategy. At α=0.05 a few hundred will clear any rung by chance alone. The
  permutation test V52 Step 3 requires is therefore **not** a formality, and a
  Stage-1 pass with no permutation support is reported as unproven.

## Honesty clause, pre-registered

Per V6 Step 4 and V17's precedent: if the frontier tops out below a rung, the
achieved number is recorded and the ladder **stops there**. No lowering 2.5%,
no widening 1.75%, no dropping losers from the denominator, no quoting a point
estimate to reach a rung, no re-cutting cohorts after seeing which cut wins.
**An empty adopted set with an honest frontier is a valid result for this task**
— and given V17, it is the expected one.

---

# Results

*(written after the run; nothing above this line is edited)*
