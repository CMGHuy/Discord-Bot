# Book autopsy, 2026-09-02 to 2026-10-21 (current exit-model era)

- Window (first and last exit date): 2026-09-02 to 2026-10-21
- N closed trades: 221; bar-covered: 213
- Pooled net ExpR (modelled): 0.063; pooled win rate: 31.2%
- Net of frictions: modelled
- Cells tested: 244 (one BH pass over all of them); bootstrap resamples 10000, seed 42
- Effective frictions: {"commission_per_trade": 1.0, "commission_risk_basis": 100.0, "min_risk_fraction": 0.001, "slippage_bps": 5.0}
- Input SHA-256 manifest: eb56f17de7c3b83e4b9653c9c12b54231e19d5646bd8dd2ca2a3a8842073a016 (63 files; file hashes in JSON)
- Sector map snapshot SHA-256: 86c14be67844f934334f8cfc113e76e054cd95da738d734215c7acf7d87a8f2b (64 tickers, 16 unknown; mapping in JSON)
- Invocation: 'C:\Users\HuyCao\AppData\Local\Programs\Python\Python311\python.exe' 'E:\Documents\Private\Projects\Discord-Bot\scripts\reports\book_autopsy.py' C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/c649b0dd-899b-4e09-94cd-eeb855856122/scratchpad/rows_sep.csv C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/c649b0dd-899b-4e09-94cd-eeb855856122/scratchpad/rejections.csv --bars-dir C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/c649b0dd-899b-4e09-94cd-eeb855856122/scratchpad/autopsy_bars --out-dir C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/c649b0dd-899b-4e09-94cd-eeb855856122/scratchpad/era --date 2026-10-21
- Note: era filter: the same 2026-10-21 export restricted to trades opened on or after 2026-09-01 and plans created (or opened) on or after that date. Jul–Aug trades mostly used a 0.35R first target, so pooling both eras hides the current system; the unfiltered book is `2026-10-21-book-autopsy.md`
- Note: net R is modelled locally (apply_frictions slippage on both fills plus commission_r); live rows store gross R only
- Note: bar cuts read only --bars-dir; anchor lag is at most 4 calendar days (weekends/holidays included); its close must lie within 25% of its planned entry
- Note: alert hour has hour granularity: 09:00-09:29 ET counts as the regular session
- Note: every row drawn from this report is exploratory: the window overlaps the 2026 holdout (spec v161 boundary 5)
- Note: earnings_proximity: earnings_proximity: days_to_earnings is opportunistic; trades without it are uncovered
- Note: fomc_proximity: fomc_proximity: FOMC dates cover 2026-01-01 to 2027-12-08; trades outside are uncovered
- Note: macro: CPI and NFP omitted: market_events.py carries no past dates
- Note: sector_today: sector_today: today's sector map, not point-in-time
- Note: stop cells price the dollar loss at 2% of 10,000 USD

## Cells (not thin; by q, then |Δ|)

| cell | N | weeks | WR | net ExpR | gross ExpR | Δ net ExpR [95% CI] | q | notes |
|---|---|---|---|---|---|---|---|---|
| exit_reason=stop | 101 | 8 | 0.0% | -1.138 | -1.064 | -2.212 [-2.539, -1.916] | 0.001 | tickers 46; top share 7.9%; stop 0.37 ATR, loss at 2% $228, overshoot 0.929 |
| exit_reason=runner_be | 30 | 8 | 100.0% | 1.624 | 1.699 | +1.806 [1.495, 2.274] | 0.001 | tickers 22; top share 10.0%; stop 0.39 ATR, loss at 2% $n/a, overshoot n/a |
| weekend_hold=no | 193 | 8 | 26.9% | -0.147 | -0.071 | -1.663 [-2.150, -1.190] | 0.001 | tickers 58; top share 6.7% |
| gap_through_stop=at_stop | 94 | 8 | 0.0% | -1.074 | -1.000 | +0.921 [0.068, 1.580] | 0.001 | tickers 43; top share 7.4%; stop 0.38 ATR, loss at 2% $215, overshoot n/a |
| fomc_proximity=no_fomc | 216 | 8 | 31.0% | 0.044 | 0.120 | -0.827 [-0.985, -0.703] | 0.001 | tickers 59; top share 6.5% |
| open_gap_bucket=favourable | 88 | 8 | 21.6% | -0.301 | -0.226 | -0.696 [-1.271, -0.370] | 0.001 | tickers 42; top share 6.8%; bar-covered 88 |
| exit_reason=scratch | 41 | 8 | 0.0% | -0.107 | -0.036 | -0.209 [-0.455, -0.062] | 0.007 | tickers 32; top share 7.3%; stop 0.42 ATR, loss at 2% $21, overshoot n/a |
| open_gap_bucket=adverse_large | 83 | 8 | 39.8% | 0.311 | 0.388 | +0.350 [0.017, 0.871] | 0.056 | tickers 40; top share 7.2%; bar-covered 83 |
| friday_entry=no | 180 | 8 | 31.1% | 0.004 | 0.080 | -0.319 [-1.273, 0.301] | 0.493 | tickers 59; top share 7.2% |
| sector_today=Information Technology | 91 | 8 | 29.7% | 0.033 | 0.107 | -0.244 [-0.786, 0.395] | 0.519 | tickers 23; top share 13.2% |
| alert_hour=20 | 205 | 8 | 32.2% | 0.095 | 0.171 | +0.441 [-0.471, 2.308] | 0.653 | tickers 54; top share 6.8% |
| holding_bucket=4w\|le_2d | 32 | 8 | 34.4% | 0.141 | 0.221 | +0.091 [-0.477, 0.719] | 0.850 | tickers 24; top share 9.4% |
| direction=bearish | 30 | 8 | 30.0% | 0.046 | 0.118 | -0.019 [-0.649, 0.467] | 0.937 | tickers 14; top share 16.7% |
| direction=bullish | 191 | 8 | 31.4% | 0.066 | 0.142 | +0.019 [-0.467, 0.649] | 0.937 | tickers 59; top share 5.8% |
| dollar_volume_bucket=ge_200m | 213 | 8 | 31.5% | 0.077 | 0.152 | n/a n/a | n/a | tickers 56; top share 6.6%; bar-covered 213 |
| near_tp_close=other_exit | 221 | 8 | 31.2% | 0.063 | 0.139 | n/a n/a | n/a | tickers 59; top share 6.3% |

Thin cells (tested and counted in BH, never evidence): alert_hour 7, atr_pct_bucket 3, earnings_proximity 3, exit_reason 3, fomc_proximity 1, friday_entry 1, gap_through_stop 1, gapped_through_entry 2, holding_bucket 24, near_stop_reversal 2, open_gap_bucket 2, opex_week 2, regime 1, sector_today 7, session_bucket 3, strategy_horizon 103, ticker 59, weekday 6, weekend_hold 1

## Give-back (mfe_r minus gross R, every trade)

- N 219; mean 1.821; median 1.506

## Tallies

- fill_status=filled: 229 (bar_covered 220, of_plans 288)
- fill_status=expired_unfilled: 1 (bar_covered 1, of_plans 288)
- fill_status=never_touched: 0 (bar_covered 0, of_plans 288)
- fill_status=risk_cap: 47 (bar_covered 47, of_plans 288)
- fill_status=invalidated: 11 (bar_covered 11, of_plans 288)
- fill_status=open: 0 (bar_covered 0, of_plans 288)
- fill_status=unknown: 0 (bar_covered 0, of_plans 288)
- alerts_per_day=1: 5 (plans 5)
- alerts_per_day=2_3: 7 (plans 20)
- alerts_per_day=4_6: 8 (plans 40)
- alerts_per_day=7_plus: 15 (plans 223)
- alert_hour_session=premarket: 25
- alert_hour_session=regular: 50
- alert_hour_session=after_close: 213
- alert_hour_session=unknown: 0
- actionable_before_open=yes: 238
- actionable_before_open=no: 50
- actionable_before_open=unknown: 0

