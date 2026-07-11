# Task 20: Out-of-sample validation

Validation window: **2024-01-01 .. 2025-12-31** (held out from all tuning in
Task 19). Run **once**, via:

```
python scripts/run_backtest_range.py --validation --json validation_results.json
```

Per spec section 9 / plan Global Constraints, this run is not repeated and
`DEFAULT_PARAMS` / `STRATEGY_GATES` / `STRATEGY_RR_OVERRIDE` are not touched
after seeing these numbers, even where the result is worse than train. Pass
gate on validation: `win_rate >= 80, expectancy_r > 0, N >= 15,
scratches+timeouts <= 50% of closed trades` (N floor is 15 here vs 30 on
train — shorter window, same everything else).

## Full VALIDATION result table (verbatim)

```
== VALIDATION 2024-01-01 .. 2025-12-31 | pass: WR>=80, ExpR>0, N>=15, excl<=50% ==
Strategy                   N   Win%    ExpR   Scr    TO  Excl%  PASS
EMA Crossover             78   76.9  +0.032    16     0    17%  FAIL
VWAP                      77   80.5  +0.064    27     0    26%  PASS
Fibonacci                206   81.6  +0.105    67     3    25%  PASS
Support/Resistance       190   86.8  +0.117    90     0    32%  PASS
RSI                      414   68.4  -0.030   117    10    23%  FAIL
MACD                     123   81.3  +0.071    46     0    27%  PASS
Elliott Wave             159   74.8  +0.008    59     1    27%  FAIL
MA Ribbon                137   78.1  +0.039    52     0    28%  FAIL
Break & Retest           148   83.8  +0.094    55     3    28%  PASS
RSI Divergence          1101   75.8  +0.045   406     0    27%  FAIL
Volume Profile            47   83.0  +0.136     9     0    16%  PASS
```

Per-strategy x horizon breakdown (same run, for anyone auditing the Task 19
gates against out-of-sample data):

```
Strategy               Horiz      N   Win%    ExpR
Break & Retest         2m        26   92.3  +0.181
Break & Retest         2w        18   77.8  +0.041
Break & Retest         3m         8   62.5  -0.096
Break & Retest         4m        10  100.0  +0.184
Break & Retest         4w        40   82.5  +0.078
Break & Retest         5m        10   80.0  +0.053
Break & Retest         6m         7   57.1  -0.200
Break & Retest         7m        10   80.0  +0.080
Break & Retest         8m        10  100.0  +0.292
Break & Retest         9m         9   88.9  +0.180
EMA Crossover          2m         9  100.0  +0.286
EMA Crossover          2w        33   63.6  -0.119
EMA Crossover          3m         2  100.0  +0.350
EMA Crossover          4w        33   81.8  +0.084
EMA Crossover          6m         1  100.0  +0.350
Elliott Wave           4w       159   74.8  +0.008
Fibonacci              2m        16   68.8  -0.023
Fibonacci              2w        30   60.0  -0.120
Fibonacci              3m        13   84.6  +0.126
Fibonacci              4m        13  100.0  +0.347
Fibonacci              4w        58   79.3  +0.077
Fibonacci              5m        18   88.9  +0.200
Fibonacci              6m        13   92.3  +0.224
Fibonacci              7m        14   92.9  +0.280
Fibonacci              8m        17   88.2  +0.211
Fibonacci              9m        14   92.9  +0.247
MA Ribbon              2m         8   87.5  +0.132
MA Ribbon              2w        60   76.7  +0.028
MA Ribbon              3m         5   60.0  -0.136
MA Ribbon              4m         5   60.0  -0.158
MA Ribbon              4w        50   80.0  +0.053
MA Ribbon              5m         4   75.0  +0.010
MA Ribbon              6m         2  100.0  +0.117
MA Ribbon              8m         2  100.0  +0.350
MA Ribbon              9m         1  100.0  +0.175
MACD                   3m        33   87.9  +0.126
MACD                   4m        33   84.8  +0.096
MACD                   7m        17   70.6  -0.036
MACD                   8m        19   78.9  +0.052
MACD                   9m        21   76.2  +0.025
RSI                    2m        40   70.0  -0.012
RSI                    2w        49   67.3  -0.051
RSI                    3m        40   70.0  -0.012
RSI                    4m        40   70.0  -0.012
RSI                    4w        41   65.9  -0.056
RSI                    5m        41   68.3  -0.030
RSI                    6m        41   68.3  -0.030
RSI                    7m        41   68.3  -0.030
RSI                    8m        41   68.3  -0.030
RSI                    9m        40   67.5  -0.033
RSI Divergence         2m       106   76.4  +0.049
RSI Divergence         2w       135   69.6  -0.021
RSI Divergence         3m       108   76.9  +0.055
RSI Divergence         4m       108   76.9  +0.055
RSI Divergence         4w       105   76.2  +0.047
RSI Divergence         5m       108   76.9  +0.055
RSI Divergence         6m       108   76.9  +0.055
RSI Divergence         7m       108   76.9  +0.055
RSI Divergence         8m       108   76.9  +0.055
RSI Divergence         9m       107   76.6  +0.053
Support/Resistance     2m       103   87.4  +0.128
Support/Resistance     3m        87   86.2  +0.106
VWAP                   4w        43   81.4  +0.067
VWAP                   6m        12   75.0  +0.011
VWAP                   7m        11   81.8  +0.096
VWAP                   8m         5  100.0  +0.219
VWAP                   9m         6   66.7  -0.086
Volume Profile         7m        47   83.0  +0.136
```

Raw JSON: `validation_results.json` (repo root, not committed by this task --
the summary table above is the committed record).

## TRAIN table for comparison (verbatim, from `docs/superpowers/results/2026-07-train-tuning.md` Step 5)

```
== TRAIN 2020-01-01 .. 2023-12-31 | pass: WR>=80, ExpR>0, N>=30, excl<=50% ==
Strategy                   N   Win%    ExpR   Scr    TO  Excl%  PASS
EMA Crossover            111   68.5  -0.056    40     0    26%  FAIL
VWAP                     139   82.0  +0.086    35     0    20%  PASS
Fibonacci                286   81.8  +0.106   106     0    27%  PASS
Support/Resistance       273   80.6  +0.060   130     0    32%  PASS
RSI                      608   85.2  +0.140   231     0    28%  PASS
MACD                     145   83.4  +0.094    50     0    26%  PASS
Elliott Wave             317   75.7  +0.015   121     1    28%  FAIL
MA Ribbon                259   81.1  +0.071    85     0    25%  PASS
Break & Retest           357   80.4  +0.061   143     0    29%  PASS
RSI Divergence          1711   80.4  +0.094   563     0    25%  PASS
Volume Profile            73   82.2  +0.106    31     0    30%  PASS
```

## Side-by-side comparison

| Strategy | Train N/WR/ExpR/PASS | Validation N/WR/ExpR/PASS | Delta WR | Delta ExpR |
|---|---|---|---|---|
| EMA Crossover | 111 / 68.5 / -0.056 / FAIL | 78 / 76.9 / +0.032 / FAIL | +8.4 | +0.088 |
| VWAP | 139 / 82.0 / +0.086 / PASS | 77 / 80.5 / +0.064 / PASS | -1.5 | -0.022 |
| Fibonacci | 286 / 81.8 / +0.106 / PASS | 206 / 81.6 / +0.105 / PASS | -0.2 | -0.001 |
| Support/Resistance | 273 / 80.6 / +0.060 / PASS | 190 / 86.8 / +0.117 / PASS | +6.2 | +0.057 |
| RSI | 608 / 85.2 / +0.140 / PASS | 414 / 68.4 / -0.030 / **FAIL** | -16.8 | -0.170 |
| MACD | 145 / 83.4 / +0.094 / PASS | 123 / 81.3 / +0.071 / PASS | -2.1 | -0.023 |
| Elliott Wave | 317 / 75.7 / +0.015 / FAIL | 159 / 74.8 / +0.008 / FAIL | -0.9 | -0.007 |
| MA Ribbon | 259 / 81.1 / +0.071 / PASS | 137 / 78.1 / +0.039 / **FAIL** | -3.0 | -0.032 |
| Break & Retest | 357 / 80.4 / +0.061 / PASS | 148 / 83.8 / +0.094 / PASS | +3.4 | +0.033 |
| RSI Divergence | 1711 / 80.4 / +0.094 / PASS | 1101 / 75.8 / +0.045 / **FAIL** | -4.6 | -0.049 |
| Volume Profile | 73 / 82.2 / +0.106 / PASS | 47 / 83.0 / +0.136 / PASS | +0.8 | +0.030 |

**9/11 PASS on train -> 6/11 PASS on validation.** Three strategies that
passed train flip to FAIL out-of-sample: **RSI**, **MA Ribbon**, **RSI
Divergence**. This is reported as-is; no gate or parameter was touched after
seeing these numbers (see "Honest observations" below).

## Tuned parameters and gates in effect for this run (unchanged since Task 19)

`DEFAULT_PARAMS` (in `swingbot/core/entry_filters.py`) -- only one entry
differs from the strategies' original shipped defaults, per Task 19 Step 2/3
(the only strategy with a fully-qualifying train-window grid config):

- RSI Divergence: `rsi_reclaim` 40 -> **45**

All other strategies kept their pre-redesign defaults; Task 19 found no
grid config that cleared the train pass bar for them (see Step 2 of
`2026-07-train-tuning.md`), so their WR/ExpR outcome is entirely a function
of the shared entry gates + `STRATEGY_GATES` below, not per-strategy param
retuning.

`STRATEGY_RR_OVERRIDE` (in `swingbot/core/strategy_types.py`, hard floor 0.30
-- break-even WR at that R:R is 76.9%, see docstring update below):

| Strategy | R:R override |
|---|---|
| Fibonacci, RSI, RSI Divergence, Volume Profile | 0.40 |
| EMA Crossover, VWAP, Support/Resistance, MACD, Elliott Wave, MA Ribbon, Break & Retest | 0.35 |

`STRATEGY_GATES` (in `swingbot/core/strategy_types.py`, applied via
`entry_filters.entries_for` -- same code path backtest and live signals
share):

| Strategy | Gate |
|---|---|
| Fibonacci | bullish only |
| RSI | bullish only |
| MA Ribbon | bullish only |
| VWAP | bullish + {4w, 6m, 7m, 8m, 9m} |
| Support/Resistance | bullish + {2m, 3m} |
| MACD | bullish + {3m, 4m, 7m, 8m, 9m} |
| Volume Profile | bullish + {7m} |
| EMA Crossover | none (ungated, documented FAILING) |
| Elliott Wave | none (ungated, documented FAILING) |
| Break & Retest | none (passes ungated, both directions) |
| RSI Divergence | none (passed ungated on train; **fails on validation**, see below) |

## Verdict per strategy

| Strategy | Verdict | Basis |
|---|---|---|
| VWAP | **PASS-GATED** | Gate (bullish + 5 horizons) holds up: N=77, WR=80.5, ExpR=+0.064, excl=26% -- all four bars cleared out-of-sample. |
| Fibonacci | **PASS-GATED** | Gate (bullish only) holds up: N=206, WR=81.6, ExpR=+0.105, excl=25%. Near-identical to train (81.8/+0.106) -- the most stable strategy across windows. |
| Support/Resistance | **PASS-GATED** | Gate (bullish + {2m,3m}) holds up and improves: N=190, WR=86.8, ExpR=+0.117, excl=32%. |
| MACD | **PASS-GATED** | Gate (bullish + 5 horizons) holds up: N=123, WR=81.3, ExpR=+0.071, excl=27%. |
| Volume Profile | **PASS-GATED** | Gate (bullish + 7m only) holds up: N=47, WR=83.0, ExpR=+0.136, excl=16%. Smallest N of the passing strategies but still well clear of the N>=15 floor and every other bar. |
| Break & Retest | **PASS** | No gate applied (train already passed ungated); validation confirms: N=148, WR=83.8, ExpR=+0.094, excl=28%. |
| RSI | **FAIL** | Bullish-only gate does NOT hold up out-of-sample: N=414, WR=68.4 (well under the 80 bar), ExpR=-0.030 (negative). Passed train (WR=85.2, ExpR=+0.140) but that edge did not generalize. Reported as-is, not retuned. |
| MA Ribbon | **FAIL** | Bullish-only gate does not hold up: N=137, WR=78.1 (just under 80), ExpR=+0.039 (still positive, but WR bar alone fails it). Passed train (WR=81.1). Reported as-is. |
| RSI Divergence | **FAIL** | Passed train ungated (WR=80.4) but validation WR=75.8, under the 80 bar (ExpR still positive at +0.045, largest N of any strategy at 1101). Reported as-is; the `rsi_reclaim=45` retune from Task 19 is not touched. |
| EMA Crossover | **FAIL** | Already documented FAILING on train (no reachable gate, Task 19 Step 3). Validation: N=78, WR=76.9, ExpR=+0.032 -- ExpR turned positive but WR is still under 80. Consistent with the Task 19 conclusion that no allowed gate rescues this strategy; no new gate was invented here per the no-retuning rule. |
| Elliott Wave | **FAIL** | Already documented FAILING on train. Validation: N=159, WR=74.8, ExpR=+0.008 -- close to train's WR=75.7/ExpR=+0.015, i.e. consistently a scratch-heavy, near-breakeven strategy across both windows. No surprises. |

**Final score: 6/11 PASS(-GATED) on validation vs 9/11 on train.**

## Honest observations (no retuning performed)

- **EMA Crossover and Elliott Wave** were predicted to fail validation
  (documented FAILING on train, Task 19) and did fail, consistent with the
  train-window conclusion that no allowed gate policy rescues them.
- **Three strategies genuinely surprised**: RSI, MA Ribbon, and RSI
  Divergence all passed train (with or without a gate) but fail validation.
  RSI's drop is the largest and most notable: WR 85.2 -> 68.4, ExpR
  +0.140 -> -0.030 (train's edge inverted to a loser out-of-sample). This is
  the train/validation split doing its job -- it caught overfitting to the
  2020-2023 window that a train-only evaluation would have missed. Per the
  task constraint, no gate/param was adjusted in response; this is reported,
  not fixed, here.
- **Five strategies (VWAP, Fibonacci, Support/Resistance, MACD, Volume
  Profile, Break & Retest -- six, including the ungated one) held up**
  within a few points of their train numbers, several actually improving
  (Support/Resistance ExpR +0.060 -> +0.117; Break & Retest +0.061 ->
  +0.094). Fibonacci in particular is nearly identical across both windows,
  the strongest evidence of a real, non-overfit edge.
- Net effect: the redesign delivers a **majority (6/11) of strategies that
  clear the win-rate/expectancy bar out-of-sample**, not merely on the
  window they were gated against -- a materially different (weaker) result
  than the train-only 9/11, and that gap is the headline finding of this
  validation, not a defect in how it was run.
