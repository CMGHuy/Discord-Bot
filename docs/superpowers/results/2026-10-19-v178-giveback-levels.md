# v178 measurement: runner give-back levels (range-multiple and profit-share arms)

**Plan:** [`2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md`](../plans/implemented/2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md)
**Spec:** [`2026-10-19-v178-runner-giveback-levels-preregistration-design.md`](../specs/implemented/2026-10-19-v178-runner-giveback-levels-preregistration-design.md)
**Raw results:** v178/*.json
**Looks:** one per output (the script refuses an existing file).
**Verdict:** NO-LIFT — every arm refused at stage 0.

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

## Stage −1 reachability (pilot)

Pilot run n = 493 entries (window 2018-06-01..2020-12-31, close basis). The frozen block in `v178/pilot-close.json` matches the block above on window, arms, frictions, data source, engines, horizons and basis; the first-10-tickers detail has no JSON field and was not compared.

| Arm | Changed vs A | Verdict |
|---|---|---|
| R0.75 | 25 | REACHABLE |
| R1.00 | 23 | REACHABLE |
| R1.25 | 14 | REACHABLE |
| S0.25 | 23 | REACHABLE |
| S0.33 | 22 | REACHABLE |
| S0.50 | 10 | REACHABLE |

Control B changed vs A: 3. Survivors: all six candidates. **Gate:** open, continue to the train simulation (V178-9).

## Stage 0 (pooled fold-train, paired MDE)

Close basis, 10838 paired fold-train entries per arm (each vs control A). Ticker-cluster 95% CI; Holm-adjusted p across the six arms; the week-cluster interval is descriptive. v92 context for the R arms: nearest cell `trigger_r=2.50, mult=1.50`, context only, never a threshold.

| Arm | n | Changed | ΔExpR | Ticker-cluster 95% CI | p | Holm p | MDE (paired) | Week-cluster interval | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| R0.75 | 10838 | 778 | +0.0094 | [-0.0077, +0.0320] | 0.1705 | 1.0000 | 0.0251 | [-0.0079, +0.0324] | REFUSED |
| R1.00 | 10838 | 691 | +0.0078 | [-0.0079, +0.0290] | 0.1973 | 1.0000 | 0.0232 | [-0.0087, +0.0298] | REFUSED |
| R1.25 | 10838 | 606 | +0.0071 | [-0.0069, +0.0275] | 0.2181 | 1.0000 | 0.0222 | [-0.0077, +0.0284] | REFUSED |
| S0.25 | 10838 | 683 | +0.0041 | [-0.0105, +0.0236] | 0.3305 | 1.0000 | 0.0216 | [-0.0115, +0.0244] | REFUSED |
| S0.33 | 10838 | 610 | +0.0057 | [-0.0099, +0.0261] | 0.2767 | 1.0000 | 0.0229 | [-0.0103, +0.0268] | REFUSED |
| S0.50 | 10838 | 418 | +0.0041 | [-0.0109, +0.0243] | 0.3508 | 1.0000 | 0.0225 | [-0.0105, +0.0242] | REFUSED |

**Gate:** `stopped_at = stage0`, `stage3_arm = null`: every candidate is REFUSED at stage 0. Stages 1 and 2 did not run. Per the frozen stop rule: no high/low sensitivity run, no VALIDATION. Verdict **NO-LIFT** (the spec's base case). Best arm by ΔExpR: R0.75 (p = 0.1705, the ledger p).

## Descriptive only (150 cells looked at; none is an effect claim)

Whole-book view per candidate (n = 13733 train entries, close basis). Trend/chop is computed only for the `regime_arms` (R0.75, S0.33). Nothing here is a pass criterion.

| Arm | Book ExpR (arm / A) | Max DD $ (arm / A) | Long ΔR (n) | Short ΔR (n) | Trend ΔR | Chop ΔR | Shock ΔR | Calm ΔR | vs B ΔR | Top-2 horizon share | Outcome flips |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R0.75 | 0.0816 / 0.0798 | 45,146 / 49,641 | -0.0068 (8896) | +0.0175 (4837) | +0.0194 | -0.0269 | +0.0941 | -0.0194 | +0.0049 | 0.693 | 0 |
| R1.00 | 0.0840 / 0.0798 | 46,925 / 49,641 | -0.0022 (8896) | +0.0159 (4837) | n/a | n/a | +0.0465 | +0.0038 | +0.0074 | 0.397 | 0 |
| R1.25 | 0.0857 / 0.0798 | 50,075 / 49,641 | +0.0029 (8896) | +0.0114 (4837) | n/a | n/a | +0.0221 | +0.0179 | +0.0091 | 0.354 | 0 |
| S0.25 | 0.0844 / 0.0798 | 48,968 / 49,641 | +0.0001 (8896) | +0.0127 (4837) | n/a | n/a | +0.0190 | +0.0132 | +0.0078 | 0.314 | 0 |
| S0.33 | 0.0850 / 0.0798 | 50,726 / 49,641 | +0.0020 (8896) | +0.0109 (4837) | +0.0131 | -0.0077 | +0.0355 | +0.0105 | +0.0084 | 0.293 | 0 |
| S0.50 | 0.0808 / 0.0798 | 51,611 / 49,641 | -0.0022 (8896) | +0.0070 (4837) | n/a | n/a | -0.0357 | +0.0168 | +0.0042 | 0.575 | 0 |

Per-horizon ΔR (vs A):

| Arm | 2w | 4w | 2m | 3m | 4m | 5m | 6m | 7m | 8m | 9m |
|---|---|---|---|---|---|---|---|---|---|---|
| R0.75 | +0.0047 | +0.0028 | +0.0052 | +0.0053 | -0.0036 | +0.0008 | -0.0018 | -0.0004 | -0.0009 | +0.0046 |
| R1.00 | +0.0011 | +0.0037 | +0.0069 | +0.0076 | -0.0001 | +0.0046 | +0.0029 | +0.0031 | +0.0057 | +0.0055 |
| R1.25 | -0.0020 | +0.0049 | +0.0117 | +0.0066 | +0.0023 | +0.0065 | +0.0069 | +0.0041 | +0.0088 | +0.0082 |
| S0.25 | +0.0027 | +0.0034 | +0.0060 | +0.0065 | +0.0019 | +0.0052 | +0.0036 | +0.0047 | +0.0063 | +0.0051 |
| S0.33 | +0.0082 | +0.0063 | +0.0043 | +0.0064 | +0.0060 | +0.0059 | +0.0026 | +0.0021 | +0.0052 | +0.0046 |
| S0.50 | -0.0001 | -0.0020 | -0.0020 | +0.0013 | +0.0023 | +0.0030 | +0.0007 | +0.0016 | +0.0035 | +0.0034 |

R0.75 runner context (4295 runner trades): allowance p10/p50/p90 = 0.0135 / 0.0269 / 0.0648; 3319 stop exits, 66.6% new-best-10 and 99.4% quick; mean give-back 0.422R (p95 1.367R, max 16.33R), 35.1% gapped; worst week 2020-W12 ($16,020, 82 runners). Near-duplicate (S0.33 vs R1.00): {'floor_bound_share': 0.8463329452852154, 'differs_from_r100': 583}.

**Reading for the partner (trade-off, not a pass):** every pooled ΔExpR is positive but below its paired MDE, and every CI spans zero. For the best arm (R0.75) the gain sits in short trades and trend regimes while long trades and chop are negative, so the lift is not uniform. Close-basis figures are an upper bound on any live result.

## Verdict

**NO-LIFT**, produced at stage 0: all six arms were refused on the pooled fold-train window (paired N = 10838 entries per arm), the spec's base case.

- Ledger fields: `n` = 13733, `p` = 0.1705 (pooled fold-train p of the best arm R0.75), Holm-adjusted p = 1.0000 for every arm (R0.75, R1.00, R1.25, S0.25, S0.33, S0.50), `cells_looked_at` = 150.
- What stays: The live fixed 5% (v176) stays. `GIVEBACK_MODE` defaults to `pct`; the range and profit-share modes ship merged and inert (V178-7). No high/low sensitivity run and no VALIDATION read: VALIDATION is unspent.
- Reopening needs a mechanism other than a runner stop at the best close since TP1 minus k × ATR(14) for k ∈ {0.75, 1.0, 1.25}, or minus max(f × open profit, 1.0 × ATR(14)) for f ∈ {0.25, 0.33, 0.50}. Another k or f, a horizon-scaled multiple, or a different floor is a new pre-registration (spec § Out of scope).
- v92 overlap: family R is adjacent to the closed v92 adaptive trail (nearest cell `trigger_r=2.50, mult=1.50`); context only, never a threshold.
- Liquid-universe limit: 75 liquid cached names; the result says nothing about thin names, where ATR is noisy.

## Ledger row

`v178-giveback-levels: verdict NO-LIFT, p=0.1705, BH q=0.3751 across 11 ledger p-values (71 rows). Reported, not gating.`

The BH q-value is printed for context and never gates (`backtest-methodology.md`).

## Panel review at close-out

No BLOCKING finding. Wording only; no reading changed, no stage re-run, VALIDATION unspent.

- risk-manager 1: arms R1.25, S0.33, S0.50 show higher max drawdown than A (50,075 / 50,726 / 51,611 vs 49,641 dollars) -- applied: stated here; any reopening reports drawdown beside ExpR.
- risk-manager 2 / veteran-trader 1: the 35.1% gapped share and 16.33R max give-back come from the legacy simulator path, which fills a runner stop at the stop level, not the gap open -- applied: the gap figures are an optimistic fill model for A and every arm alike; the paired ΔExpR largely cancels it, but no gap number here is a live estimate.
- risk-manager 3: the mode constants are mutable globals set by the measurement script -- declined for now: they are not config, a SIGHUP cannot change them, and the default is `pct`; recorded as a follow-up in the plan index.
- risk-manager 4 / veteran-trader 5: drawdown caveat and thin-name fill realism not in the closed row -- declined: the closed row stays a verdict record; this document carries both.
- veteran-trader 2: the shock-week gain (+0.0941 for R0.75, 945 runners) is dominated by 2020-W12; not a mechanism for reopening -- applied (stated here).
- veteran-trader 3: range and profit-share stops move every bar, so a live port needs a stop-move message -- applied: follow-up for any Phase B spec.
- veteran-trader 4: "upper bound" means intrabar and gap fills, not frictions (5 bps and $1 per side are applied) -- applied (stated here).
- quant-researcher 1: "best arm R0.75" holds only on the pooled fold-train window (n = 10838); on the whole train book (n = 13733) the order flips (R1.25 +0.0059, S0.33 +0.0052, S0.25 +0.0046, R1.00 +0.0042, R0.75 +0.0017, S0.50 +0.0010) -- applied: k = 0.75 is not the leading value for any reopening.
- quant-researcher 2: R0.75's gain is concentrated on shock days (+0.0941, n = 945 vs calm -0.0194, n = 3350) and top-2 horizons (0.693) -- applied (stated here).
- quant-researcher 3: ledger `n` = 13733 is the whole-book count, `p` = 0.1705 comes from the paired pooled fold-train sample, N = 10838 -- declined: a ledger row is never edited; both counts are named here and in the closed row.
