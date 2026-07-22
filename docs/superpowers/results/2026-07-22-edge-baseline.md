# Edge plan Task E11: honest baseline (started here, finalized at E22)

This doc is started at Task E11 (friction model) and finalized at Task E22
(baseline finalization), per the Edge-plan schedule — later tasks (filters,
sizing, regime detection, Tasks E13+) append their own before/after
comparisons here rather than opening new files.

## What changed

`run_backtest(..., exit_model="v1")` (the default v1 walk-forward loop only —
the v2 exit simulator used by the live Plan Engine is untouched, see
`swingbot/core/backtest.py` module docstring and `CLAUDE.md`) now defaults
`frictions=True`:

- Every entry/exit fill is worsened by `SLIPPAGE_BPS` (default 5 bps/side) —
  buys fill higher, sells fill lower.
- Every trade's `r_multiple` is reduced by a round-trip commission expressed
  in R (`COMMISSION_PER_TRADE` / `COMMISSION_RISK_BASIS`, default
  `2 x $1 / $100 = 0.02R`).

This is the new honest baseline every later Edge-plan component (liquidity
screen, position sizing, regime detection, ...) must beat — a filter that
only "improves" a frictionless backtest was never real.

## Method

`python scripts/run_backtest_range.py --train --frictions off|on`, TRAIN
window (2020-01-01..2023-12-31), all 11 strategies pooled across 78 cached
watchlist tickers, one_at_a_time=True, exit_model="v1" (default). Pass gate:
`win_rate>=80, expectancy_r>0, N>=30, excluded_share<=50%`.

## Frictions OFF (pre-E11 arithmetic)

| Strategy | N | Win% | ExpR | Scr | TO | Excl% | PASS |
|---|---|---|---|---|---|---|---|
| EMA Crossover | 68 | 91.2 | +0.191 | 14 | 0 | 17% | PASS |
| VWAP | 139 | 82.0 | +0.086 | 35 | 0 | 20% | PASS |
| Fibonacci | 286 | 81.8 | +0.106 | 106 | 0 | 27% | PASS |
| Support/Resistance | 273 | 80.6 | +0.060 | 130 | 0 | 32% | PASS |
| RSI | 51 | 100.0 | +0.255 | 29 | 0 | 36% | PASS |
| MACD | 145 | 83.4 | +0.094 | 50 | 0 | 26% | PASS |
| Elliott Wave | 118 | 83.9 | +0.095 | 47 | 0 | 28% | PASS |
| MA Ribbon | 259 | 81.1 | +0.071 | 85 | 0 | 25% | PASS |
| Break & Retest | 371 | 80.9 | +0.066 | 143 | 0 | 28% | PASS |
| RSI Divergence | 1711 | 80.4 | +0.094 | 563 | 0 | 25% | PASS |
| Volume Profile | 73 | 82.2 | +0.106 | 31 | 0 | 30% | PASS |

## Frictions ON (new baseline)

| Strategy | N | Win% | ExpR | Scr | TO | Excl% | PASS |
|---|---|---|---|---|---|---|---|
| EMA Crossover | 68 | 91.2 | +0.147 | 14 | 0 | 17% | PASS |
| VWAP | 139 | 82.0 | +0.041 | 35 | 0 | 20% | PASS |
| Fibonacci | 286 | 81.8 | +0.070 | 106 | 0 | 27% | PASS |
| Support/Resistance | 273 | 80.6 | +0.027 | 130 | 0 | 32% | PASS |
| RSI | 51 | 100.0 | +0.209 | 29 | 0 | 36% | PASS |
| MACD | 145 | 83.4 | +0.053 | 50 | 0 | 26% | PASS |
| Elliott Wave | 118 | 83.9 | +0.060 | 47 | 0 | 28% | PASS |
| MA Ribbon | 259 | 81.1 | +0.025 | 85 | 0 | 25% | PASS |
| Break & Retest | 371 | 80.9 | +0.019 | 143 | 0 | 28% | PASS |
| RSI Divergence | 1711 | 80.4 | +0.053 | 563 | 0 | 25% | PASS |
| Volume Profile | 73 | 82.2 | +0.062 | 31 | 0 | 30% | PASS |

## Delta (on - off)

| Strategy | N | Win% (unchanged) | ExpR delta |
|---|---|---|---|
| EMA Crossover | 68 | 91.2 | -0.044 |
| VWAP | 139 | 82.0 | -0.045 |
| Fibonacci | 286 | 81.8 | -0.036 |
| Support/Resistance | 273 | 80.6 | -0.033 |
| RSI | 51 | 100.0 | -0.046 |
| MACD | 145 | 83.4 | -0.041 |
| Elliott Wave | 118 | 83.9 | -0.035 |
| MA Ribbon | 259 | 81.1 | -0.046 |
| Break & Retest | 371 | 80.9 | -0.047 |
| RSI Divergence | 1711 | 80.4 | -0.041 |
| Volume Profile | 73 | 82.2 | -0.044 |

## Observations (honest, not papered over)

- Every strategy's N/Win%/Scr/TO/Excl% is byte-identical between the two
  runs — expected and correct: frictions only touch the entry/exit *fill*
  and the resulting `r_multiple`/`return_pct`, never the planned
  stop/target/break-even-trigger levels the win/loss/scratch/timeout
  classification is decided against (see `backtest.py`'s v1 loop comments).
  A friction bug that shifted classification counts would be a red flag,
  not a curiosity.
- Every strategy's expectancy haircut lands in the predicted **0.03R–0.05R**
  band (min -0.033R Support/Resistance, max -0.047R Break & Retest) —
  consistent with a ~5bps/side slippage + 0.02R commission model at these
  trade counts and R-multiple distributions.
- **All 11 strategies that PASSed frictionless still PASS with frictions
  on** — no strategy's pooled TRAIN expectancy crosses zero or its win rate
  drops below 80 from this haircut alone at the current default
  `SLIPPAGE_BPS=5` / `COMMISSION_PER_TRADE=1.0` / `COMMISSION_RISK_BASIS=100`.
  This is the expected outcome for a conservative-for-liquid-names friction
  model (the E12 liquidity screen is what will make that assumption
  defensible for real trading, not just for this backtest).
- **Known gap in this table (to close at E22 or sooner if a later task
  needs it):** the pooled max-drawdown-% column the task template calls for
  is not currently emitted by `scripts/run_backtest_range.py`'s pooled view
  — `BacktestSummary.max_drawdown_pct` exists per (ticker, strategy,
  horizon) combo but there is no existing pooled-across-tickers equity
  curve to compute a single per-strategy max-DD from. A first attempt at an
  ad hoc pooled-max-DD script (rerunning the full grid a second time with an
  equity-curve calc bolted on) did not finish in a reasonable time in this
  session and was abandoned rather than block the task further; the N/Win%/
  ExpR/Excl%/PASS columns above are the actual, verified
  `run_backtest_range.py --train --frictions off|on` output. Recorded here
  rather than silently dropped, per this repo's "failures are recorded, not
  fixed" convention for these docs.

## Config

New `Field`s in `swingbot/config.py` ("Execution Realism" section):
`SLIPPAGE_BPS` (float, default 5, min 0, max 50, step 1), `COMMISSION_PER_TRADE`
(float, default 1.0, min 0, max 20, step 0.5), `COMMISSION_RISK_BASIS` (float,
default 100.0). All three are live-editable from the admin UI's Settings page
like every other `.env`-driven field.
