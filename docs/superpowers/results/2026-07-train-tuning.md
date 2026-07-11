# Task 19: Train-window tuning + gates

Train window: 2020-01-01 .. 2023-12-31. Selection rule: among configs with
`n_eval>=30, win_rate>=80, expectancy_r>0, excluded_share<=0.5`, pick max
expectancy. All numbers below come from `scripts/tune_strategy.py` and
`scripts/run_backtest_range.py --train` run against the cached OHLCV in
`data/backtest_cache/` (75/78 watchlist tickers).

## Step 1 — break-even trigger

Ran `tune_strategy.py --strategy "MACD" --be-trigger X` and `--strategy "RSI"
--be-trigger X` for X in {0.4, 0.5, 0.6}, then re-ran the winning config at
each X through the raw backtest to get full-precision expectancy (the tuner
prints only 3 decimals, which produced apparent ties at 3dp):

| Strategy | X=0.4 ExpR | X=0.5 ExpR | X=0.6 ExpR | Best X |
|---|---|---|---|---|
| MACD (ext_atr=1.5) | 0.008863 | **0.009366** | 0.001905 | 0.5 |
| RSI (os_level=35, confirm=prev_close) | 0.058714 | **0.067427** | 0.066598 | 0.5 |

At full precision X=0.5 is the unambiguous expectancy winner for BOTH
strategies (no tie-break needed). **Decision: keep `BREAKEVEN_TRIGGER_FRACTION
= 0.5`** — no change to `strategy_types.py`.

## Step 2 — per-strategy sweeps (train window, default BE=0.5)

`python scripts/tune_strategy.py --strategy "<name>"` over the full
`PARAM_GRID`, TRAIN window, qualifying rule WR>=80/ExpR>0/N>=30/excl<=50%.
Full per-config output in the shell log; top candidates below.

| Strategy | Qualifying | Best config (by ExpR) | N | WR | ExpR | Excl% |
|---|---|---|---|---|---|---|
| EMA Crossover | 0/9 | rsi_dip=50, ext_atr=1.5 | 510 | 73.7 | -0.003 | 28% |
| VWAP | 0/6 | ext_pct=1.0, hold_bars_other=2 | 273 | 78.8 | +0.048 | 24% |
| Fibonacci | 0/4 | ratios=(.382,.5,.618), rsi_bull=(40,60) | 501 | 77.8 | +0.067 | 25% |
| Support/Resistance | 0/9 | base_atr=3.0, close_frac=0.5 | 1291 | 79.6 | +0.052 | 30% |
| RSI | 0/4 | os_level=35, confirm=prev_close | 1431 | 77.9 | +0.067 | 26% |
| MACD | 0/3 | ext_atr=1.5 | 2460 | 75.0 | +0.009 | 25% |
| Elliott Wave | 0/4 | depth_min=0.38, depth_max=0.80 | 266 | 77.8 | +0.038 | 25% |
| MA Ribbon | 0/3 | ext_pct=8.0 (= current default) | 371 | 78.4 | +0.045 | 24% |
| Break & Retest | 2/3 | hold_tol_pct=0.5 (= current default) | 357 | 80.4 | +0.061 | 29% |
| RSI Divergence | 3/3 | rsi_reclaim=45 | 1711 | 80.4 | +0.094 | 25% |
| Volume Profile | 0/9 | node_share=10.0, prox_pct=2.0 | 3446 | 74.6 | +0.031 | 29% |

Only **RSI Divergence** and **Break & Retest** had >=1 fully-qualifying grid
config (untamed, both directions pooled). Per Step 3, only these two get
`DEFAULT_PARAMS` changes:
- RSI Divergence: `rsi_reclaim` 40 -> **45** (ExpR 0.090 -> 0.094 at similar N/WR).
- Break & Retest: winner (`hold_tol_pct=0.5`) already equals the shipped
  default -- no change.

The other 9 strategies had no grid config clearing the WR>=80 bar pooled
across both directions (several came close pooled bullish-only, see Step 3
below), so their `DEFAULT_PARAMS` are left as-is and the failure is
addressed via `STRATEGY_GATES` in Step 4.

## Step 3 — per-direction / per-horizon breakdown (current DEFAULT_PARAMS, no gate)

For the 9 non-qualifying strategies, split TRAIN trades by `t.direction`,
then by horizon within the bullish side (ad hoc script, not committed --
mirrors `run_backtest_range.py`'s pooling exactly):

| Strategy | Bullish-only | Bearish-only |
|---|---|---|
| EMA Crossover | N=72 WR=70.8 ExpR=-0.032 (fail) | N=39 WR=64.1 ExpR=-0.101 (fail) |
| VWAP | N=339 WR=77.3 ExpR=+0.035 (fail) | N=115 WR=68.7 ExpR=-0.053 (fail) |
| Fibonacci | N=286 WR=81.8 ExpR=+0.106 excl=27% **PASS** | N=187 WR=70.1 ExpR=-0.015 (fail) |
| Support/Resistance | N=1331 WR=76.9 ExpR=+0.026 (fail) | N=518 WR=79.7 ExpR=+0.055 (fail) |
| RSI | N=608 WR=85.2 ExpR=+0.140 excl=28% **PASS** | N=487 WR=66.7 ExpR=-0.049 (fail) |
| MACD | N=685 WR=76.8 ExpR=+0.028 (fail) | N=305 WR=69.8 ExpR=-0.044 (fail) |
| Elliott Wave | N=174 WR=74.1 ExpR=-0.001 (fail; only 4w fires) | N=143 WR=77.6 ExpR=+0.038 (fail) |
| MA Ribbon | N=259 WR=81.1 ExpR=+0.071 excl=25% **PASS** | N=112 WR=72.3 ExpR=-0.019 (fail) |
| Volume Profile | N=1860 WR=76.0 ExpR=+0.045 (fail) | N=773 WR=70.0 ExpR=-0.015 (fail) |

Fibonacci, RSI and MA Ribbon already qualify bullish-only (gate rule 1) --
no horizon restriction needed for them. The remaining 6 need the
bullish-by-horizon breakdown to find a rule-2 (bullish + restricted
horizons) subset with per-horizon WR>=80, ExpR>0, N>=10:

| Strategy | Horizons w/ WR>=80,ExpR>0,N>=10 (bullish) |
|---|---|
| EMA Crossover | 4w only (N=28) |
| VWAP | 4w, 6m, 7m, 8m, 9m |
| Support/Resistance | 2m, 3m |
| MACD | 3m, 4m, 7m, 8m, 9m |
| Elliott Wave | none (only horizon that fires, 4w, fails WR/ExpR) |
| Volume Profile | 7m only |

Pooling exactly those horizon subsets (verified with the actual
`STRATEGY_GATES` mask via `run_backtest`, not hand-summed):

| Strategy | Gate | N | WR | ExpR | Excl% | Result |
|---|---|---|---|---|---|---|
| VWAP | bullish + {4w,6m,7m,8m,9m} | 139 | 82.0 | +0.086 | 20% | **PASS** |
| Support/Resistance | bullish + {2m,3m} | 273 | 80.6 | +0.060 | 32% | **PASS** |
| MACD | bullish + {3m,4m,7m,8m,9m} | 145 | 83.4 | +0.094 | 26% | **PASS** |
| Volume Profile | bullish + {7m} | 73 | 82.2 | +0.106 | 30% | **PASS** |
| EMA Crossover | bullish + {4w} | 28 | 85.7 | +0.107 | 32% | FAIL (N<30) |
| Elliott Wave | bullish only | 174 | 74.1 | -0.001 | 33% | FAIL (WR/ExpR) |

**EMA Crossover** and **Elliott Wave** cannot reach a passing train
configuration under the allowed gate policy (mildest-gate-first, no R:R
changes, no retuning past the grid already swept): EMA Crossover's only
per-horizon-qualifying subset (bullish 4w) tops out at N=28, under the
N>=30 floor even before any other filter; Elliott Wave only ever fires on
4w and that horizon's bullish stats don't clear WR>=80 either. Per the
Step 4 policy, rule 3 applies: **both are left ungated and recorded as
FAILING.**

## Step 4 — gates applied to `STRATEGY_GATES`

Written into `swingbot/core/strategy_types.py` (see inline comments there
citing the same numbers):

| Strategy | Gate |
|---|---|
| Fibonacci | `{"directions": ("bullish",)}` |
| RSI | `{"directions": ("bullish",)}` |
| MA Ribbon | `{"directions": ("bullish",)}` |
| VWAP | `{"directions": ("bullish",), "horizons": ("4w","6m","7m","8m","9m")}` |
| Support/Resistance | `{"directions": ("bullish",), "horizons": ("2m","3m")}` |
| MACD | `{"directions": ("bullish",), "horizons": ("3m","4m","7m","8m","9m")}` |
| Volume Profile | `{"directions": ("bullish",), "horizons": ("7m",)}` |
| EMA Crossover | none -- **FAILING** (documented, ungated) |
| Elliott Wave | none -- **FAILING** (documented, ungated) |
| Break & Retest | none needed -- passes ungated (both directions) |
| RSI Divergence | none needed -- passes ungated with `rsi_reclaim=45` |

## Step 5 — TRAIN confirmation (`python scripts/run_backtest_range.py --train`)

After applying the `DEFAULT_PARAMS` change (RSI Divergence `rsi_reclaim=45`)
and the `STRATEGY_GATES` above:

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

9/11 PASS. **EMA Crossover** and **Elliott Wave** remain **documented
FAILING** per Step 4 rule 3 (no gate policy combination reaches the
acceptance bar on train without lowering R:R below 0.30 or inventing new
filters, both disallowed). These two carry into the redesign as known-weak
strategies; nothing further to do within this task's scope.

`python -m pytest tests -v`: **32 passed** -- gates changed entry counts
(as expected) but no test asserts specific counts, so nothing broke.

