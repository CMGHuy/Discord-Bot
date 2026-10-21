# v178 measurement: runner give-back levels (range-multiple and profit-share arms)

**Plan:** [`2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md`](../plans/2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md)
**Spec:** [`2026-10-19-v178-runner-giveback-levels-preregistration-design.md`](../specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md)
**Raw results:** v178/*.json
**Looks:** one per output (the script refuses an existing file).

## Frozen block (stated before any window is read)

| Item | Frozen value |
|---|---|
| Pilot window (`windows.STAGES["pilot"]`) | 2018-06-01 .. 2020-12-31 (first 10 tickers of the sorted universe) |
| Pooled fold-train window | 2018-06-01 .. 2022-12-31 |
| Fold-train windows (three) | 2020: 2018-06-01 .. 2020-12-31; 2021: 2018-06-01 .. 2021-12-31; 2022: 2018-06-01 .. 2022-12-31 |
| Fold-test years (three) | 2021, 2022, 2023 (2021-01-01 .. 2021-12-31; 2022-01-01 .. 2022-12-31; 2023-01-01 .. 2023-12-31) |
| VALIDATION | 2024-01-01 .. 2025-12-31, one shot, stage-3 arm only, partner's go |
| Arms | A: 5% of the best close. B: give-back off. R: k in {0.75, 1.0, 1.25}. S: f in {0.25, 0.33, 0.50} with a 1.0 x ATR floor. No other value is ever run |
| Entries | one control-A pass per ticker; every entry re-simulated under each arm |
| Data source | `yfinance`, 75-ticker cache |
| Engines | both: `StrategyEngine.iter_trades` and `replay_scenarios` |
| Horizons / mode / instrument | all ten horizons, `scale_out=True`, instrument v1 |
| Frictions (from `config`, read now) | `SLIPPAGE_BPS` = 5.0 per side; `COMMISSION_PER_TRADE` = 1.0 per side ($); `COMMISSION_RISK_BASIS` = 100.0 ($) |
| Gating basis | close; high/low is a TRAIN-side sensitivity only, never VALIDATION |
| `cells_looked_at` | 150 + the sensitivity cells if they run |
| Stop gates of this part | after V178-8: every candidate refused at stage -1 (zero changed outcomes on the pilot) ends the test, skip to V178-11, verdict `UNMEASURABLE`. After V178-9: every candidate refused at stage 0 ends the test as a finished result (the spec's base case): no sensitivity run, no VALIDATION, skip to V178-11, verdict `NO-LIFT`; stage 1 or stage 2 closing everything ends it the same way. V178-10 runs only if exactly one arm (`summary.stage3_arm`) survived stages 0-2, and only after the partner says go through `AskUserQuestion`; VALIDATION is read once, never for the high/low sensitivity |

**v92 overlap disclosure.** Family R is adjacent to the closed v92 adaptive trail (nearest v92 cell `trigger_r=2.50, mult=1.50`, dExpR -0.0045R to +0.0091R across its grid, best cell lower bound -0.0131R). This is context, never a threshold; the partner ruled this a new test.

**Liquid-universe limit.** 75 liquid cached names: the result says nothing about thin names, where ATR is noisy.
