# V17 — Target/stop sizing grid, TRAIN only (plan v8, Phase V4)

**Status:** pre-registration written 2026-08-02 **before** the grid was run.
Everything above the "Results" heading was committed first; nothing in it is
edited once numbers exist.

**Command:** `python scripts/tune_sizing.py --strategy "<name>" --json <out>`,
one background chunk per strategy.
**Window:** TRAIN = 1999-01-01 .. 2023-12-31 (`swingbot/core/backtest_windows.py`,
widened by V46). The validation window is not touched and this script has no
flag that could reach it.
**Exit model:** v2 + `--scale-out`, `tp2_mode=levels` — what production runs
(`PLAN_ENGINE_V2` on, `INTRADAY_MANAGER_V2=true`). V16's baseline was v1 by
default and said so; V17 is where exit parameters are actually being chosen, so
it uses the production model, exactly as V16's own note asked.

## Step 1 — the selection rule, pre-registered

Quoted verbatim from plan v8 **V6 Step 3** (human-partner directive, 2026-07-31).
This is the rule; it is not re-derived here and it is not amended after seeing a
result:

```
OBJECTIVE   maximise win_rate
SUBJECT TO  every win >= MIN_TARGET_PCT (2.5%)
            expectancy_r > 0
            scratches + timeouts <= 50% of closed trades
STRETCH     win_rate >= 90%
FLOOR       reject any config with expectancy_r <= 0 regardless of WR
```

**Trade volume is explicitly NOT an objective.** A config producing 20 trades at
85% WR beats one producing 400 at 60%. Frequency does not tie-break.

Two things the rule's own preamble requires, applied here as stated rather than
as new criteria:

1. **`N >= 30` is applied to the independent sample, not the summed one.**
   V16 finding 2 / V49 Step 3 measured that five of eleven strategies reuse the
   same entry signal across horizons — RSI's summed N=122 is ~13 independent
   trades. A strategy-level N in this grid is likewise a sum over ten horizons,
   so the same correction applies or the sample gate is scored against inflated
   evidence. `tune_sizing.py` re-measures the reuse ratio **per config**
   (distinct `(date, entry, direction)` signatures vs. the summed count, flagged
   at >=1.5x, the threshold V49 pinned) and gates on `n_independent`.
2. **Wilson lower bounds beside every win rate** (V6 Step 5), computed on that
   same independent sample. V6 Step 5 also stands: proving WR > 90% needs
   N >= 59, so any cohort under that is provisional however good it looks.

**V6 Step 4's honesty clause is pre-registered here too.** If the frontier tops
out below 90%, the achieved number gets recorded and the task stops. No relaxing
`MIN_TARGET_PCT`, no post-hoc cohort re-cutting, no dropping losers from the
denominator. V16 already measured a ~78% headline ceiling over this window, so
that is the expected outcome, and it is a result.

## Step 2 — the grid, pre-registered

Full cross product, per strategy, all 11 strategies:

| Axis | Values | Knob it moves |
|---|---|---|
| `min_target_pct` | **2.5, 3.5, 5.0** | `config.MIN_TARGET_PCT` — the V10 target floor |
| `rr` | **0.35, 0.75, 1.25, 2.0** | `STRATEGY_RR_OVERRIDE[strategy]` (unfrozen by V6 Step 2) |
| `atr_stop_multiple` | **1.5, 2.0, 2.5** | every horizon's `HORIZONS[hk]["atr_stop_multiple"]` |
| `trail_atr_mult` | **2.0, 2.5, 3.0** | `EXIT_V2_PARAMS[strategy]["trail_atr_mult"]` |

**108 configs x 11 strategies = 1188 runs**, each over the 78-ticker watchlist x
10 horizons.

Three deliberate choices, recorded before the run so they cannot be
rationalised afterwards:

- **The floor axis starts at 2.5, not lower.** The rule's own constraint is
  "every win >= 2.5%", so a config below that is disqualified by construction;
  gridding it would only manufacture rows that cannot be selected. Whether 2.5
  is the right floor is not a V17 question — V12's live measurement and V27's
  shadow week own it.
- **`tp2` is not an axis.** Task 30's TRAIN grid chose it per strategy
  (`EXIT_V2_PARAMS`) and the plan names `tune_exit_v2.py` as the script that
  re-opens it. V17 moves the trail and holds each strategy's adopted `tp2`.
  Caveat for whoever reads this later: those Task-30 values were chosen on the
  old 2020-2023 window under the WR>=80 rule that V6 voided, so they are
  inherited, not re-validated.
- **Per-horizon `atr_stop_multiple` is set uniformly.** It is a flat 2.0 across
  all ten horizons today; V19 owns making it horizon-dependent, and doing that
  here would confound the two.

**Axis interaction, expected in advance:** `MIN_TARGET_PCT` and `rr` both price
TP1 and `apply_target_floor` takes the max, so at high `rr` the floor never binds
and the `min_target_pct` axis collapses — those rows will be exact duplicates.
That is the cross product being honest about a degeneracy, not a bug; duplicate
rows are reported, not deleted.

**Where `atr_stop_multiple` is inert:** it only reaches `plan_engine._atr_plan`.
Fibonacci and Elliott Wave size their stop off structure (capped by
`max_risk_pct`) and Support/Resistance off `sr_stop_pct`, so for those three the
axis is expected to change nothing. Recorded in advance so a flat result there is
read as the known mechanism rather than as a finding.

## The harness — and why it is a new script

`tune_strategy.py --grid` sweeps `entry_filters.DEFAULT_PARAMS`, i.e. *entry*
parameters; `tune_exit_v2.py` sweeps trail/tp2/entry-type. **Neither has an axis
for the target floor, the R:R override or the ATR stop multiple**, so the grid
the plan's V17 Step 2 names could not be expressed in either script. Rather than
bend those two (both are load-bearing for other tasks), V17 adds
`scripts/tune_sizing.py` with exactly the four missing axes and the same
pre-registered rule, and leaves them untouched. The plan's Step 2 wording is
amended to match what was actually run.

### The finding that made the run possible at all

Measured by cProfile on 2026-08-02, not assumed: **an exit-v2 `tp2_mode=levels`
backtest spends ~98% of its runtime inside `build_level_map` ->
`trendline_levels` -> `_find_best_trendline`**, which is O(pivots^3) over the
full df history. One config over the universe costs ~7 min under v2 against
~14 s under v1, and the entire difference is the level map.

None of the level map's inputs — `(df up to the entry bar, horizon, entry
price)` — is a sizing parameter. So a sizing grid recomputes a bit-identical
level map once per config: **the pre-registered grid was a ~30-hour job, of
which ~29 hours was recomputing the same numbers.** `backtest.py` now carries an
opt-in exact-key memo (`enable_level_map_memo`, off by default, tuning harnesses
only — the live bot's memory profile is unchanged). Measured effect on a
4-ticker MACD probe: 29.3s cold, **0.9s warm (~33x)**, with the emitted trades
byte-identical across memoized and non-memoized runs.

This is the third time in this plan that an unexamined cost or gap would have
silently shaped a result (V43's cache overwrite, V48's skipped parity suite).
The memo is an exact memo, not an approximation: a hit returns precisely what
the call would have computed.

---

# Results

*(written after the run; nothing above this line is edited)*

Run 2026-08-02 20:26 → 2026-08-03 05:03 (11/11 chunks, all `rc=0`), then three
chunks re-run 2026-08-03 16:54 → 18:31 for the reason below. Regenerate every
table here with:

```
python scripts/summarize_v17_grid.py docs/superpowers/results/v17
```

## Read this first: the sweep was not one measurement, and had to be repaired

**V51 Step 1's 1.75% loss cap was committed at 22:01, mid-sweep.**
`tune_sizing.py` never touches `MAX_LOSS_CAP_ENABLED` (default `true`), so each
chunk silently inherited whatever the working tree held at its process start.
EMA Crossover, VWAP and Fibonacci started before 22:01 and ran **uncapped**; the
other eight ran **capped**. Nothing in the run announced this — it was caught by
lining chunk start times up against `git log` before writing these tables.

It was not a cosmetic split. In the first aggregation those three chunks were
exactly the three highest win rates *and* exactly the three whose `rr` and
`atr_stop_multiple` axes responded at all, so the apparent finding
"entry structure adds win rate" was perfectly collinear with which code version
had been imported. The three were re-run under capped code; every table below is
the homogeneous capped grid. The uncapped chunks are kept in `v17/uncapped/`
(excluded from the tables — the aggregator globs `v17/*.json` non-recursively)
because the re-run turned them into the other arm of a controlled comparison.

**Both pre-registered degeneracies fired, and the cap added a third that
swallowed the grid.** Predicted above: the floor/`rr` interaction, and
`atr_stop_multiple` being inert for the three structural-stop strategies. Both
hold. What was not predicted is that the cap makes the degeneracies near-total:
capped risk ≤1.75% makes the rr-derived target `rr × 1.75%` = 0.61 / 1.31 /
2.19% for `rr ≤ 1.25`, all under the 2.5% floor, which then binds — so **the
`rr` axis is exactly inert below rr=2.0** (0.00pt, measured, in every capped
chunk), and at rr=2.0 (3.5%) floors 2.5 and 3.5 become identical while only 5.0
still binds. That is the same 2.5/1.75 = **1.4286** threshold V51 Step 1 already
recorded for `tp2_r`, reappearing on a different knob. Widening the ATR stop
likewise just hits the cap (median stop 2.19% > 1.75%), flattening that axis too.

Consequence: **under the shipped cap the 4-value `rr` axis produces no target
the 3-value floor axis does not already produce**, and 108 configs collapse to
as few as **3 distinct win rates** (MA Ribbon, RSI; 30 at most, Break & Retest).

## The tables

Generated by `summarize_v17_grid.py`; not retyped. See the script's output for
the per-axis breakdowns — the load-bearing rows are reproduced here.

### Winners, one per strategy

| Strategy | floor | rr | stop | trail | N | N ind | WR | Wilson LB | ExpR | dead |
|---|---|---|---|---|---|---|---|---|---|---|
| Break & Retest | 2.5 | 0.35 | 2.5 | 2.0 | 2065 | 2065 | 48.2% | 46.1% | +0.204 | 24% |
| EMA Crossover | 2.5 | 0.35 | 1.5 | 2.0 | 245 | 245 | 42.4% | 36.2% | +0.016 | 17% |
| Elliott Wave | 2.5 | 0.35 | 1.5 | 2.0 | 555 | 555 | 43.4% | 39.3% | +0.098 | 16% |
| Fibonacci | 2.5 | 0.35 | 1.5 | 2.5 | 1473 | 1473 | 45.3% | 42.7% | +0.194 | 20% |
| MA Ribbon | 2.5 | 0.35 | 1.5 | 2.0 | 1471 | 894 | 49.6% | 46.2% | +0.292 | 22% |
| MACD | 2.5 | 0.35 | 2.0 | 2.0 | 891 | 495 | 46.6% | 42.2% | +0.108 | 24% |
| RSI | — | — | — | — | — | — | **no config qualifies** | — | — | — |
| RSI Divergence | 2.5 | 0.35 | 2.0 | 3.0 | 8625 | 871 | 44.8% | 41.6% | +0.190 | 18% |
| Support/Resistance | 2.5 | 0.35 | 1.5 | 3.0 | 1871 | 993 | 43.9% | 40.8% | +0.162 | 20% |
| VWAP | 2.5 | 0.35 | 2.0 | 2.5 | 822 | 822 | 49.5% | 46.0% | +0.312 | 23% |
| Volume Profile | 2.5 | 0.35 | 2.0 | 2.5 | 517 | 517 | 47.6% | 43.2% | +0.251 | 21% |

**Every winner sits at `floor=2.5, rr=0.35`** — the loosest target in the grid,
i.e. the pre-registered *lower bound* of the floor axis. The optimum is on the
boundary, so the grid does not contain its own answer on this axis.

### What the 1.75% cap cost — same grid, same window, one knob

| Strategy | arm | best WR | Wilson LB | ExpR | dead | distinct WR of 108 |
|---|---|---|---|---|---|---|
| EMA Crossover | uncapped | 65.3% | 58.7% | +0.025 | 23% | 28 |
| EMA Crossover | **capped** | 42.4% | 36.2% | +0.016 | 17% | 3 |
| Fibonacci | uncapped | 76.8% | 74.3% | +0.138 | 33% | 33 |
| Fibonacci | **capped** | 45.3% | 42.7% | +0.194 | 20% | 9 |
| VWAP | uncapped | 70.6% | 67.1% | +0.118 | 33% | 60 |
| VWAP | **capped** | 49.5% | 46.0% | +0.312 | 23% | 13 |

## Observations, including the ones that hurt

**1. The stretch goal is not reached, and not nearly.** Best qualifying win rate
anywhere in 1188 configs: **49.6%** (MA Ribbon, Wilson LB 46.2%, independent
N=894). Against V6 Step 3's 90% stretch this is not a near miss. Against V6
Step 3b's **80% hard constraint** the entire sizing grid fails, and against even
the **60% first rung** of V52's ladder the best sizing config is more than ten
points short.

**2. Three of the four axes are inert; the fourth is maximised at its lower
bound.** `rr` is identical across 0.35/0.75/1.25 for all ten qualifying
strategies and strictly worse at 2.0; `atr_stop_multiple` moves win rate by
≤0.3pt everywhere; `trail_atr_mult` by ≤0.2pt. Only `min_target_pct` moves it,
monotonically and in the same direction for every strategy (2.5 > 3.5 > 5.0,
by 12-17 points end to end). The grid's entire answer is *"ask for the smallest
win you are allowed to ask for, and nothing else matters."*

**3. The cap costs 21-32 points of win rate and mostly buys expectancy.**
Fibonacci −31.5pt, EMA Crossover −22.9pt, VWAP −21.1pt. This is an order of
magnitude larger than the 3.2 points the V52 groundwork measured, and the two
are not in conflict: that measurement compared 2.00% → 1.75%, whereas this caps
from each strategy's *natural* stop (median 2.19%, often much wider) to 1.75%.
In two of three the trade is favourable on the plan's actual objective —
VWAP's expectancy nearly tripled (+0.118 → +0.312) and Fibonacci's rose
(+0.138 → +0.194) even as win rate collapsed. EMA Crossover's did not
(+0.025 → +0.016). This is exactly V51 Step 2's payoff arithmetic showing up in
measurement: at 2.5%/1.75% a win pays 1.4286R, so fewer, better-paid wins.

**4. The reuse correction flips a verdict, as V17 Step 1 said it might.** RSI
qualifies in **0 of 108** configs on independent N and in **108 of 108** on the
summed N — a 10.0x overcount. It is the only strategy the correction excludes
outright, and without V49's correction it would have entered the tables as a
fully qualifying strategy. RSI Divergence carries a comparable 9.9x ratio but
survives on volume (N=8625 → 871 independent).

**5. Win rate and expectancy rank differently, and the plan's rule now cares
about the second.** MA Ribbon leads on both (49.6%, +0.292), but VWAP is second
on win rate (49.5%) and *first* on expectancy (+0.312), while Break & Retest is
third on win rate (48.2%) and fourth on expectancy. Under V6 Step 3's objective
(maximise WR) the ranking is one thing; under Step 3b's (maximise ExpR subject
to WR ≥ 80%) every one of these fails the constraint and the objective never
gets consulted.

**6. Dead share is comfortable everywhere** — 16-24%, against the 50% ceiling.
Notably the cap *reduces* it (Fibonacci 33% → 20%, VWAP 33% → 23%): a tighter
stop resolves trades that previously timed out. No config was rejected on this
constraint.

## What this means for V52 — its stated premise is void

V52's preamble justifies the ladder's first rung with two numbers: "V17 chunk 1
measured `EMA Crossover` topping out at 65.3%" and "V17 is already printing
Fibonacci at 76.6% WR (LB 74.1%, N=1198) on ATR stops, so entry structure
demonstrably adds win rate over the 43.4% floor." **Both are uncapped
measurements.** Under the cap the same two cells are 42.4% and 45.3%.

So the honest starting position for V52 is not "65-77% and climbing" but
**42-50%, against a measured no-skill floor of 43.4%** — four of eleven
strategies sit at or below that floor. Sizing is exhausted as a lever; whether
entry selectivity can add the 10+ points needed to clear even the 60% rung is
now genuinely open, and the pre-registered expectation for the 80% rung should
be read as considerably more pessimistic than when it was written.

Two things V52 must carry forward, both measured here rather than assumed:

- **Do not grid `rr` against a capped stop.** It cannot move the target below
  `rr = MIN_TARGET_PCT / MAX_LOSS_PCT = 1.4286`, and above it only by
  overriding the floor. Same trap as `tp2_r`.
- **Expectancy and win rate move in opposite directions under the cap.** A
  ladder that gates on win rate alone will reject the configs that are best on
  the rule's own objective. Report both at every rung, per V52 Step 1.
