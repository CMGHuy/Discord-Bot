# v147 gate counterfactual: TRAIN reading

**Run:** 2026-10-14, TRAIN 2020-01-01..2023-12-31 (signal date), 75 cached tickers from the main tree's `data/backtest_cache` (read-only; the confluence replay loaded 74/75, one excluded illiquid), universe source `MEASURE_ARMS_UNIVERSE=cache` for both runs, instrument no flag (neither script lists `--instrument`). VALIDATION never read. No RS row (live-only; v34 closed).
**Spec:** `docs/superpowers/specs/2026-10-09-v147-gate-counterfactual-design.md`
**Plan:** `docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_0-index.md`

**Status: a TRAIN reading, not a verdict of record.** The verdict of record is frozen by the first production `build_report()` run that reads these files from `data/reports/inputs/`. This document appends no ledger row and spends no budget.

## Deviations from the plan's commands

- **Universe for the confluence run.** `run_backtest_range.py` has no cache-universe switch and no `--tickers` flag; with no `--universe` it reads the watchlist from Postgres, which is unreachable from the dev machine (`psycopg.OperationalError: getaddrinfo failed`). On the controller's instruction the run used a thin wrapper (outside the repo) that replaces `_tickers_for_run` with the sorted file stems of the main tree's `data/backtest_cache` (75 tickers), matching `MEASURE_ARMS_UNIVERSE=cache` of the compression run, so both populations share one universe. No repo code changed. Command and flags otherwise as planned.

## Commands

    BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache \
      python <wrapper: _tickers_for_run -> 75 cache stems> --train --scenarios --scale-out --record-blocked logs/v147-blocked-confluence.jsonl
    BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache MEASURE_ARMS_UNIVERSE=cache \
      python scripts/backtest/measure_arms.py --record-blocked logs/v147-blocked-compression.jsonl
    python scripts/reports/gate_counterfactual_report.py --train logs/v147-blocked-confluence.jsonl logs/v147-blocked-compression.jsonl --no-live --no-write --json logs/v147-train-report.json

The confluence run's scenario table ended `confluence/pooled  4955  33.9%  +0.042  630 scratches  0 timeouts  11% excluded  FAIL` (unchanged replay output; the recorder is record-only).

## Rows recorded

## logs/v147-blocked-confluence.jsonl: 5881 rows, signal dates 2020-01-06..2023-12-29
| gate | reason | arm | cf_status | rows |
|---|---|---|---|---|
| plan_rejected | None | taken | filled | 5585 |
| plan_rejected | None | taken | no-fill | 296 |

## logs/v147-blocked-compression.jsonl: 47 rows, signal dates 2020-01-22..2023-10-18
| gate | reason | arm | cf_status | rows |
|---|---|---|---|---|
| compression | earnings_unknown | blocked | filled | 1 |
| compression | earnings_unknown | blocked | no-plan | 11 |
| compression | missing_sector | blocked | no-fill | 3 |
| compression | missing_sector | blocked | no-plan | 32 |

**Unexpected:** the confluence file holds only `taken` rows. Step 2 expected `no_qualifying_target` blocked and `risk_cap` blocked rows alongside; there are none (zero blocked rows in 5881). Flagged to the controller, not explained away.

## Cells (gate x population, never pooled; BH over the fixed five-cell family)

| gate | population | verdict | distinct filled N | taken N | difference | 95% CI | q | note |
|---|---|---|---|---|---|---|---|---|
| rs | live | WAITING | 0 | 0 | - | [-, -] | - |  |
| risk_cap | live | WAITING | 0 | 0 | - | [-, -] | - |  |
| compression | live | WAITING | 0 | 0 | - | [-, -] | - |  |
| risk_cap | train | WAITING | 0 | 0 | - | [-, -] | - |  |
| compression | train | WAITING (in-sample) | 1 | 0 | - | [-, -] | - |  |
| rs | train | WAITING | 0 | 0 | - | [-, -] | - | no TRAIN population |
| no_qualifying_target | live | WAITING | 0 | 0 | - | [-, -] | - | no verdict - no-plan |
| no_qualifying_target | train | WAITING | 0 | 0 | - | [-, -] | - | no verdict - no-plan |

## Rows (gate x reason x population)

| gate | reason | pop | blocked N | no-plan N | fill rate | blocked ExpR | blocked WR | taken ExpR | taken WR | near-miss N / ExpR | rest N / ExpR | $risk (x 2% cap) | labels |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| compression | earnings_unknown | train | 12 | 11 | 100.0% | +2.267 | 100.0% | - | - | - / - | - / - | - | in-sample |
| compression | missing_sector | train | 35 | 32 | 0.0% | - | - | - | - | - / - | - / - | - | in-sample |

## Reading

- `risk_cap` (TRAIN shadow of the plan-time 2% cap; every row over-cap, never a tradable alternative): WAITING, N 0 distinct filled, no difference, CI or q; the replay recorded no `risk_cap` rows at all.
- `compression` (TRAIN, in-sample): WAITING, 1 distinct filled blocked setup, taken N 0, no difference; the taken arm is empty, so the TRAIN gate cannot be read until an as-of earnings archive exists (the report's note field is empty; the expected `no TRAIN taken arm` note appears only in the limitations text).
- `no_qualifying_target`: blocked N 0 and no-plan N 0 in the recorded file; no verdict by construction.

## Limitations

- Portfolio state: every blocked candidate is simulated as a lone trade; the portfolio heat and correlated-cluster caps are ignored, and heat at block time is not stored (null).
- Gap floor: simulate_exit books a stop at the stop price, so a gap through the stop reads -1.0R; counterfactual losses on gaps are understated, so the blocked arm's losses are understated.
- R is per-trade risk-normalised (every trade sized to 1R). risk_cap rows add dollar_risk -- the outcome in units of the 2% dollar cap -- and are over-cap: never a tradable alternative.
- TRAIN compression is in-sample (v119 fitted the gate on TRAIN); TRAIN has no as-of earnings archive, so its taken arm is expected to be empty and the cell carries a note, not a verdict.
- Live rows from 2026-10 sit inside the 2026 holdout; a follow-on screen built on a live verdict must name a holdout this report has not seen.
- Short-lane blocked rows are scoped against confluence taken plans (issued plans carry no lane marker); live taken plans store no signal-day close, so their re-walk is never re-anchored.
- A verdict changes nothing: GATE COSTS licenses one Stage -2 screen under a new idea name (for risk_cap, with the partner); no closed pre-registration is reopened.
- The live rows (2026 onward) overlap the v2 instrument's sealed holdout (2026-01-01 onward); any follow-on gate screen built on them has seen that period.

## What this licenses

Nothing changes automatically. A `GATE COSTS` reading of record licenses exactly one Stage -2 screen for loosening that gate under a new idea name; for `risk_cap` that screen also needs the partner, must state its drawdown and risk-of-ruin effect, and must keep the dollar cap binding through sizing, never through stop width. A `GATE EARNS` reading is evidence for a later tightening screen. Neither reopens a closed row.
