# Edge plan Task E11: honest baseline (started here, finalized at E22)

This doc is started at Task E11 (friction model) and finalized at Task E22
(baseline finalization), per the Edge-plan schedule — later tasks (filters,
sizing, regime detection, Tasks E13+) append their own before/after
comparisons here rather than opening new files.

**Finalized at E22 (2026-07-24):** the tables below were regenerated against
current code — frictions (E11) + the E12 liquidity screen + the E16
data-quality screen are all active in the same run now, and a pooled
per-strategy max-DD column has been added. The E11-era tables further down
this doc predate E12/E16 taking effect in `run_backtest_range.py` and are
kept for history only — do **not** use their N values, they are stale (see
Observations below for the size of the drift). **The "Frictions ON (E22
final, liquidity+quality screened)" table is the reference every later
Phase-E2 component must beat.**

## Frictions ON (E22 final, liquidity+quality screened) — THE reference baseline

Method: `python scripts/run_backtest_range.py --train --frictions on`
(current code), TRAIN window (2020-01-01..2023-12-31), all 11 strategies
pooled across the 78 cached watchlist tickers minus 10 excluded (below),
`one_at_a_time=True`, `exit_model="v1"` (default). Pass gate:
`win_rate>=80, expectancy_r>0, N>=30, excluded_share<=50%`. Full stdout:
`.superpowers/sdd/e22-train-frictions-on.log` (gitignored scratch — the
table below is the durable record).

| Strategy | N | Win% | ExpR | MaxDD% | Scr | TO | Excl% | PASS |
|---|---|---|---|---|---|---|---|---|
| EMA Crossover | 66 | 90.9 | +0.145 | -1.9 | 13 | 0 | 16% | PASS |
| VWAP | 134 | 81.3 | +0.035 | -7.4 | 33 | 0 | 20% | PASS |
| Fibonacci | 275 | 81.1 | +0.062 | -11.2 | 100 | 0 | 27% | PASS |
| Support/Resistance | 263 | 81.7 | +0.039 | -7.2 | 122 | 0 | 32% | PASS |
| RSI | 51 | 100.0 | +0.209 | -0.8 | 29 | 0 | 36% | PASS |
| MACD | 140 | 83.6 | +0.055 | -9.2 | 46 | 0 | 25% | PASS |
| Elliott Wave | 102 | 83.3 | +0.052 | -4.5 | 45 | 0 | 31% | PASS |
| MA Ribbon | 254 | 81.9 | +0.033 | -7.7 | 83 | 0 | 25% | PASS |
| Break & Retest | 324 | 81.5 | +0.026 | -8.5 | 127 | 0 | 28% | PASS |
| RSI Divergence | 1531 | 81.6 | +0.063 | -30.1 | 552 | 0 | 27% | PASS |
| Volume Profile | 71 | 81.7 | +0.057 | -2.7 | 30 | 0 | 30% | PASS |

**All 11 strategies still PASS after liquidity+quality screening.**
`MaxDD%` is a pooled-per-strategy proxy: every ticker/horizon's trades for
that strategy, sorted chronologically by entry date, compounded into one
equity curve at an assumed fixed 1% risk per trade (`pooled_max_dd_pct()`,
new in `scripts/run_backtest_range.py`, Task E22) — **not** a true
concurrent-position-aware portfolio curve (overlapping trades aren't
modeled), but a standard, defensible way to turn a pool of R-multiples into
a single max-DD figure without a second full backtest run. RSI Divergence's
-30.1% is the largest — expected given it also has by far the largest trade
count (1531) and 27% exclusion share; still PASSes the gate, which is
about win_rate/expectancy_r/N, not drawdown.

## Frictions OFF (E22 final, same liquidity+quality-screened ticker set)

Same method as above with `--frictions off`. N/Win%/Scr/TO/Excl% are
byte-identical to the ON table (frictions never touch classification, only
the fill/`r_multiple` economics — same invariant as the original E11
finding). Full stdout: `.superpowers/sdd/e22-train-frictions-off.log`.

| Strategy | N | Win% | ExpR | MaxDD% | Scr | TO | Excl% | PASS |
|---|---|---|---|---|---|---|---|---|
| EMA Crossover | 66 | 90.9 | +0.190 | -1.6 | 13 | 0 | 16% | PASS |
| VWAP | 134 | 81.3 | +0.079 | -4.2 | 33 | 0 | 20% | PASS |
| Fibonacci | 275 | 81.1 | +0.099 | -10.0 | 100 | 0 | 27% | PASS |
| Support/Resistance | 263 | 81.7 | +0.071 | -6.7 | 122 | 0 | 32% | PASS |
| RSI | 51 | 100.0 | +0.255 | 0.0 | 29 | 0 | 36% | PASS |
| MACD | 140 | 83.6 | +0.097 | -8.0 | 46 | 0 | 25% | PASS |
| Elliott Wave | 102 | 83.3 | +0.087 | -3.6 | 45 | 0 | 31% | PASS |
| MA Ribbon | 254 | 81.9 | +0.080 | -7.0 | 83 | 0 | 25% | PASS |
| Break & Retest | 324 | 81.5 | +0.072 | -7.0 | 127 | 0 | 28% | PASS |
| RSI Divergence | 1531 | 81.6 | +0.104 | -22.7 | 552 | 0 | 27% | PASS |
| Volume Profile | 71 | 81.7 | +0.101 | -2.6 | 30 | 0 | 30% | PASS |

## Delta (E22 final: on - off)

| Strategy | N | Win% (unchanged) | ExpR delta |
|---|---|---|---|
| EMA Crossover | 66 | 90.9 | -0.045 |
| VWAP | 134 | 81.3 | -0.044 |
| Fibonacci | 275 | 81.1 | -0.037 |
| Support/Resistance | 263 | 81.7 | -0.032 |
| RSI | 51 | 100.0 | -0.046 |
| MACD | 140 | 83.6 | -0.042 |
| Elliott Wave | 102 | 83.3 | -0.035 |
| MA Ribbon | 254 | 81.9 | -0.047 |
| Break & Retest | 324 | 81.5 | -0.046 |
| RSI Divergence | 1531 | 81.6 | -0.041 |
| Volume Profile | 71 | 81.7 | -0.044 |

## Excluded symbols (E12 liquidity + E16 data-quality, same set both runs)

10 of 78 watchlist tickers excluded from the TRAIN grid above — identical
exclusion list in both the frictions-on and frictions-off runs (screening
doesn't depend on the frictions flag):

**Illiquid (E12), 2 tickers:**
- `GC=F`: avg dollar vol $3.1M < $20M floor
- `SI=F`: avg dollar vol $0.1M < $20M floor

**Bad data (E16), 8 tickers:**
- `ASTS`: >5 consecutive identical closes (frozen feed?)
- `BKNG`: >5 consecutive identical closes (frozen feed?)
- `CRWV`: >40% bar on 2025-04-01 without volume spike (bad split adjust?)
- `HIMS`: >5 consecutive identical closes (frozen feed?)
- `HOOD`: >40% bar on 2021-08-04 without volume spike (bad split adjust?)
- `QBTS`: >5 consecutive identical closes (frozen feed?); >40% bar on
  2024-12-16 without volume spike (bad split adjust?)
- `SHOP`: >40% bar on 2015-05-21 without volume spike (bad split adjust?)
- `SOFI`: >40% bar on 2021-01-07 without volume spike (bad split adjust?)

## Observations (E22 finalization, honest, not papered over)

- **The E11-era tables below (68/139/286/273/... watchlist tickers) predate
  E12/E16 actually excluding anything in this script** — despite the E11
  doc text implying screening was already active, the real N values shifted
  materially once this task actually ran the grid with today's code: e.g.
  Break & Retest 371 -> 324 (-47), Elliott Wave 118 -> 102 (-16), RSI
  Divergence 1711 -> 1531 (-180). All still comfortably clear the `N>=30`
  gate and every strategy still PASSes, so this doesn't change any
  accept/reject decision made so far — but it means anything that quoted
  the old N values as "the screened baseline" was wrong. This finalized
  table is the first one that's actually true to that description.
- The max-DD gap flagged at E11 ("known gap... to close at E22") is closed:
  `pooled_max_dd_pct()` reuses the trades the grid run already collects
  (no second backtest run needed — the earlier abandoned attempt re-ran the
  whole grid a second time just for this and was too slow). See the method
  note under the reference table above for exactly what this number is and
  isn't.
- Frictions haircut is slightly larger than the pre-screening E11 estimate
  (now 0.032R-0.047R vs the original 0.033R-0.047R) — screening out 10
  tickers shifted the trade mix marginally but the haircut band is
  essentially unchanged, as expected (frictions are a fixed per-trade cost
  model, not ticker-dependent).

---

## E11-era tables (kept for history — stale N, see finalization note above)

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
