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

Run 2026-08-03 18:50 → 21:0x, 11/11 chunks, 72 tickers × 10 horizons × 8
cut-flag combos. Regenerate every table with:

```
python scripts/summarize_v52_grid.py docs/superpowers/results/v52
```

## Stage 1 — the gate fires. The ladder stops here.

| Stage | bar (Wilson LB) | cells clearing |
|---|---|---|
| Stage 1 | > 60% | **0** |
| Stage 2 | > 70% | **0** |
| Stage 3 | > 80% | **0** |

**Not one cell, in any strategy, at any cut-flag combination, clears LB 60%.**
Per Step 2's pre-registered gate the ladder stops and the achieved frontier is
the result. Steps 3 and 4 are not run: nothing above Stage 1 can be real when
Stage 1 is empty.

## Step 5 — the frontier, reported instead of a winner

Best cell per strategy by Wilson LB. **`cuts=none` wins for all eleven.**

| Strategy | cell | N ind | WR | **LB** | ExpR | loss med | runner R med |
|---|---|---|---|---|---|---|---|
| VWAP | `regime=aligned` | 717 | 51.2% | **47.5%** | +0.367 | 1.75% | +0.82 |
| Break & Retest | `regime=aligned` | 1658 | 49.5% | **47.1%** | +0.278 | 1.75% | +0.53 |
| MA Ribbon | `regime=aligned` | 786 | 49.9% | **46.3%** | +0.316 | 1.75% | +0.74 |
| Elliott Wave | `score>=80` | 202 | 52.5% | **45.4%** | +0.463 | 1.75% | +0.01 |
| Fibonacci | `tier<=A` | 700 | 47.9% | **44.1%** | +0.212 | 1.75% | +0.00 |
| Volume Profile | `score>=60` | 430 | 48.8% | **44.0%** | +0.296 | 1.75% | +0.00 |
| Support/Resistance | `confluence>=5` | 188 | 51.0% | **43.7%** | +0.578 | 1.75% | +0.00 |
| MACD | `regime=aligned` | 418 | 47.4% | **42.5%** | +0.215 | 1.75% | +0.20 |
| RSI Divergence | `score>=70` | 709 | 46.2% | **42.4%** | +0.185 | 1.75% | +0.00 |
| EMA Crossover | `regime=aligned` | 194 | 45.4% | **38.3%** | +0.148 | 1.75% | +0.00 |
| RSI | — | — | — | **no eligible cell** | — | — | — |

**Adopted set: empty.** Per V6 Step 4 that is a valid result and it is not
worked around — no lowering 2.5%, no widening 1.75%, no dropping losers from
the denominator, no quoting the point estimate (51.2%) instead of the bound.

## The finding that matters most: selectivity buys ~1 point

Best LB reachable on each axis family, pooled across all strategies:

| Axis family | best LB | cell |
|---|---|---|
| regime | **47.5%** | `regime=aligned` |
| confluence | 46.8% | `confluence>=3` |
| score | 46.4% | `score>=70` |
| tier | 46.3% | `tier<=B` |
| **all (no selectivity at all)** | **46.3%** | `all` |

**The best unselective cohort is 46.3%. The best selective one is 47.5%.**
Every axis this task exists to search — the quality score, the gatekeeper tier
ladder, confluence count, regime alignment — is worth about **1.2 points of
Wilson lower bound** between them, and the single best axis is the one the
gatekeeper does not own (SPY regime).

V52's premise was that sizing was exhausted and selectivity was the remaining
lever. Sizing was exhausted (V17: 49.6% ceiling). **Selectivity is not a lever
either.** Against V6 Step 3b's 80% constraint the two together fall ~33 points
short, and against Stage 1's 60% they fall ~13 short.

## V51 Step 3 answered: all three early-cut predicates hurt

Mean best LB and mean best ExpR across strategies, per cut-flag combination:

| combo | mean best LB | mean best ExpR |
|---|---|---|
| **none** | **43.96%** | 0.384 |
| time | 43.26% | 0.385 |
| mae | 42.56% | 0.384 |
| time,mae | 42.03% | 0.381 |
| thesis | 33.36% | 0.380 |
| thesis,mae | 33.36% | 0.380 |
| thesis,time | 33.34% | 0.380 |
| thesis,time,mae | 33.34% | 0.380 |

Every predicate costs win rate and **none buys expectancy** — ExpR is flat at
0.380-0.385 across all eight. The thesis cut, pre-registered as "the most
defensible because it is the entry's own logic firing in reverse", is the
**worst**: −10.6 points of LB. It ejects trades that would have recovered.

**They stay default-off**, which is how V51 shipped them. This is the
measurement that decision was waiting on.

## The economics: positive expectancy, carried entirely by the tail

Every strategy shows median realised loss of **exactly 1.75%** — the cap binds
on essentially every loss, and `loss_over_cap_share` is 0.0% throughout, so the
V51 cap is doing exactly what it claims.

The runner leg is where the money is, and it is not where the *typical* trade
is. Per V51 Step 2, a win pays `0.5 × 1.4286 + 0.5 × r_runner`:

| Strategy | runner R median | runner R mean | blended R/win | break-even WR | observed WR |
|---|---|---|---|---|---|
| VWAP | +0.75 | +2.26 | 1.089R | **47.9%** | 51.2% |
| MA Ribbon | +0.58 | +2.10 | 1.006R | **49.9%** | 49.9% |
| Break & Retest | +0.43 | +2.02 | 0.928R | **51.9%** | 49.5% |
| MACD | +0.29 | +2.02 | 0.857R | 53.8% | 47.4% |
| Fibonacci / S-R / Volume Profile / EMA / Elliott / RSI Div | **+0.00** | +1.8 to +2.2 | **0.714R** | **58.3%** | 45-52% |

**Six of eleven strategies have a median runner of exactly 0.00R** — the modal
runner stops at breakeven. Their blended win pays 0.714R, so they need **58.3%**
to break even and observe 45-52%. They are unprofitable on the typical trade
and positive only because mean runner R is ~2.0: a thin tail of large winners
carries the book.

Only VWAP and MA Ribbon sit at or above their own break-even line, and only
just. This is precisely the world V51 Step 2 flagged as the pessimistic case,
and it is the one that measured.

## What this means for the rest of the plan

- **V22 (permutation) has nothing to permute.** It was rescoped to test the
  cohort V52 adopts; the adopted set is empty. Record and stop — which is what
  V22 Step 3 already pre-registers as a legitimate ending.
- **V24's headline will be in-sample and should not be read as validation.**
  With no adopted config there is nothing new to validate; V24 measures the
  shipped defaults. Its `out_of_sample` row is the only one that means
  anything.
- **The 30.3% daily-vs-hourly disagreement from V51 Step 4 is wider than every
  margin here.** The whole frontier spans 38.3-47.5% LB and selectivity moves
  it 1.2 points. None of the differences between cells in this grid survive
  that error bar. Read the frontier as "mid-to-high 40s, flat", not as a
  ranking.
