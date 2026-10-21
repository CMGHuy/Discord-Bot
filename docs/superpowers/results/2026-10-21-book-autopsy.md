# Book autopsy, 2026-07-20 to 2026-10-21

- Window (first and last exit date): 2026-07-20 to 2026-10-21
- N closed trades: 776; bar-covered: 761
- Pooled net ExpR (modelled): -0.107; pooled win rate: 50.5%
- Net of frictions: modelled
- Cells tested: 362 (one BH pass over all of them); bootstrap resamples 10000, seed 42
- Effective frictions: {"commission_per_trade": 1.0, "commission_risk_basis": 100.0, "min_risk_fraction": 0.001, "slippage_bps": 5.0}
- Input SHA-256 manifest: a74fa6ae7f02d7ec0ac2dc79eecdc0bb6e429f7140984c9172b40f6aeb9cb87a (75 files; file hashes in JSON)
- Sector map snapshot SHA-256: ad53fc4cf47065ef1300787d8d20cb02d704d1fcdb3e224d23481c92e0889aa7 (76 tickers, 23 unknown; mapping in JSON)
- Invocation: 'C:\Users\HuyCao\AppData\Local\Programs\Python\Python311\python.exe' 'E:\Documents\Private\Projects\Discord-Bot\scripts\reports\book_autopsy.py' C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/c649b0dd-899b-4e09-94cd-eeb855856122/scratchpad/rows.csv C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/c649b0dd-899b-4e09-94cd-eeb855856122/scratchpad/rejections.csv --bars-dir C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/c649b0dd-899b-4e09-94cd-eeb855856122/scratchpad/autopsy_bars --out-dir C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/c649b0dd-899b-4e09-94cd-eeb855856122/scratchpad/full --date 2026-10-21
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
| exit_reason=stop | 156 | 12 | 0.0% | -1.315 | -1.245 | -1.512 [-2.024, -1.158] | 0.001 | tickers 52; top share 6.4%; stop 0.37 ATR, loss at 2% $263, overshoot 0.890 |
| near_tp_close=other_exit | 774 | 15 | 50.4% | -0.111 | -0.044 | -1.374 [-1.492, -1.248] | 0.001 | tickers 73; top share 7.5% |
| exit_reason=runner_be | 59 | 12 | 72.9% | 0.902 | 0.968 | +1.092 [0.540, 1.820] | 0.001 | tickers 30; top share 11.9%; stop 0.39 ATR, loss at 2% $36, overshoot n/a |
| gap_through_stop=at_stop | 190 | 15 | 0.0% | -1.069 | -1.000 | +0.884 [0.072, 1.163] | 0.001 | tickers 58; top share 6.8%; stop 0.38 ATR, loss at 2% $214, overshoot n/a |
| open_gap_bucket=favourable | 226 | 13 | 35.4% | -0.467 | -0.400 | -0.698 [-1.225, -0.328] | 0.001 | tickers 55; top share 8.0%; bar-covered 226 |
| open_gap_bucket=adverse_large | 194 | 13 | 52.6% | 0.221 | 0.289 | +0.472 [0.145, 0.914] | 0.003 | tickers 49; top share 11.3%; bar-covered 194 |
| holding_bucket=7m\|le_2d | 55 | 12 | 43.6% | -0.338 | -0.273 | -0.248 [-0.523, -0.100] | 0.008 | tickers 24; top share 14.5% |
| fomc_proximity=no_fomc | 708 | 15 | 48.3% | -0.123 | -0.056 | -0.182 [-1.087, -0.026] | 0.047 | tickers 72; top share 6.1% |
| weekend_hold=no | 713 | 15 | 51.0% | -0.161 | -0.095 | -0.664 [-1.363, -0.063] | 0.069 | tickers 72; top share 7.6% |
| weekend_hold=yes | 63 | 13 | 44.4% | 0.503 | 0.570 | +0.664 [0.063, 1.363] | 0.069 | tickers 42; top share 7.9% |
| open_gap_bucket=adverse_small | 57 | 12 | 54.4% | 0.323 | 0.391 | +0.446 [-0.019, 1.170] | 0.136 | tickers 31; top share 10.5%; bar-covered 57 |
| holding_bucket=5m\|le_2d | 63 | 11 | 47.6% | -0.461 | -0.397 | -0.385 [-0.795, 0.023] | 0.143 | tickers 27; top share 7.9% |
| alert_hour=20 | 473 | 13 | 45.2% | -0.049 | 0.020 | +0.312 [-0.050, 0.951] | 0.167 | tickers 64; top share 8.5% |
| holding_bucket=6m\|le_2d | 48 | 12 | 62.5% | 0.271 | 0.338 | +0.403 [-0.104, 1.013] | 0.222 | tickers 28; top share 12.5% |
| ticker=GLW | 30 | 11 | 33.3% | -0.404 | -0.337 | -0.308 [-0.797, 0.133] | 0.297 | tickers 1; top share 100.0% |
| holding_bucket=3m\|le_2d | 104 | 14 | 46.2% | -0.269 | -0.202 | -0.187 [-0.513, 0.076] | 0.303 | tickers 42; top share 8.6% |
| holding_bucket=4m\|le_2d | 93 | 11 | 50.5% | -0.222 | -0.156 | -0.130 [-0.352, 0.068] | 0.311 | tickers 40; top share 7.5% |
| holding_bucket=4w\|le_2d | 101 | 13 | 55.5% | 0.035 | 0.104 | +0.163 [-0.099, 0.447] | 0.378 | tickers 38; top share 7.9% |
| exit_reason=other | 462 | 12 | 65.1% | -0.044 | 0.021 | +0.157 [-0.109, 0.514] | 0.409 | tickers 64; top share 8.9%; stop 0.31 ATR, loss at 2% $224, overshoot n/a |
| open_gap_bucket=flat | 40 | 12 | 55.0% | 0.151 | 0.219 | +0.244 [-0.181, 0.619] | 0.414 | tickers 23; top share 15.0%; bar-covered 40 |
| weekday=Wed | 186 | 12 | 52.7% | -0.167 | -0.096 | -0.078 [-0.339, 0.049] | 0.456 | tickers 53; top share 10.8% |
| ticker=IREN | 34 | 8 | 73.5% | 0.168 | 0.232 | +0.288 [-0.509, 0.670] | 0.552 | tickers 1; top share 100.0% |
| direction=bearish | 267 | 15 | 51.3% | -0.188 | -0.124 | -0.124 [-0.283, 0.189] | 0.552 | tickers 56; top share 8.6% |
| direction=bullish | 509 | 15 | 50.1% | -0.065 | 0.003 | +0.124 [-0.189, 0.283] | 0.552 | tickers 71; top share 6.9% |
| ticker=WDC | 38 | 9 | 65.8% | 0.024 | 0.089 | +0.137 [-0.321, 0.340] | 0.554 | tickers 1; top share 100.0% |
| opex_week=other | 629 | 11 | 55.2% | -0.123 | -0.057 | -0.081 [-0.278, 0.120] | 0.588 | tickers 70; top share 8.4% |
| sector_today=Information Technology | 388 | 15 | 50.5% | -0.145 | -0.079 | -0.129 [-0.467, 0.160] | 0.604 | tickers 26; top share 14.9% |
| dollar_volume_bucket=ge_200m | 750 | 15 | 50.3% | -0.106 | -0.040 | -0.170 [-0.482, 1.055] | 0.642 | tickers 67; top share 7.7%; bar-covered 750 |
| weekday=Tue | 111 | 12 | 49.5% | -0.058 | 0.007 | +0.058 [-0.125, 0.254] | 0.667 | tickers 31; top share 9.9% |
| holding_bucket=8m\|le_2d | 46 | 11 | 54.4% | -0.212 | -0.149 | -0.112 [-0.659, 0.206] | 0.692 | tickers 25; top share 8.7% |
| gapped_through_entry=not_gapped | 50 | 8 | 40.0% | -0.406 | -0.344 | -0.188 [-1.652, 0.524] | 0.753 | tickers 23; top share 14.0%; bar-covered 50 |
| friday_entry=no | 615 | 15 | 50.7% | -0.124 | -0.058 | -0.084 [-0.512, 0.214] | 0.753 | tickers 72; top share 6.8% |
| friday_entry=yes | 161 | 14 | 49.7% | -0.041 | 0.025 | +0.084 [-0.214, 0.512] | 0.753 | tickers 44; top share 9.9% |
| weekday=Fri | 161 | 14 | 49.7% | -0.041 | 0.025 | +0.084 [-0.214, 0.512] | 0.753 | tickers 44; top share 9.9% |
| exit_reason=scratch | 48 | 9 | 0.0% | -0.125 | -0.056 | -0.019 [-0.161, 0.079] | 0.801 | tickers 35; top share 6.2%; stop 0.42 ATR, loss at 2% $25, overshoot n/a |
| weekday=Mon | 132 | 12 | 43.2% | -0.168 | -0.105 | -0.074 [-0.356, 0.267] | 0.833 | tickers 44; top share 7.6% |
| holding_bucket=2m\|le_2d | 98 | 12 | 52.0% | -0.150 | -0.084 | -0.049 [-0.437, 0.220] | 0.839 | tickers 34; top share 15.3% |
| ticker=NBIS | 47 | 13 | 59.6% | -0.168 | -0.104 | -0.065 [-0.545, 0.301] | 0.864 | tickers 1; top share 100.0% |
| weekday=Thu | 173 | 13 | 57.2% | -0.071 | -0.005 | +0.046 [-0.261, 0.284] | 0.874 | tickers 49; top share 7.5% |
| ticker=STX | 58 | 12 | 50.0% | -0.081 | -0.017 | +0.029 [-0.264, 0.606] | 0.900 | tickers 1; top share 100.0% |
| ticker=MRVL | 31 | 10 | 45.2% | -0.082 | -0.015 | +0.027 [-0.265, 0.789] | 0.956 | tickers 1; top share 100.0% |
| holding_bucket=2w\|le_2d | 67 | 12 | 49.2% | -0.097 | -0.024 | +0.011 [-0.355, 0.344] | 0.975 | tickers 30; top share 9.0% |
| ticker=ARM | 32 | 10 | 53.1% | -0.104 | -0.042 | +0.003 [-0.578, 0.457] | 0.982 | tickers 1; top share 100.0% |

Thin cells (tested and counted in BH, never evidence): alert_hour 10, atr_pct_bucket 3, dollar_volume_bucket 2, earnings_proximity 3, exit_reason 4, fomc_proximity 1, gap_through_stop 1, gapped_through_entry 1, holding_bucket 16, near_stop_reversal 2, near_tp_close 1, opex_week 1, regime 1, sector_today 7, session_bucket 3, strategy_horizon 196, ticker 66, weekday 2

## Give-back (mfe_r minus gross R, every trade)

- N 745; mean 1.636; median 1.315

## Tallies

- fill_status=filled: 855 (bar_covered 838, of_plans 914)
- fill_status=expired_unfilled: 1 (bar_covered 1, of_plans 914)
- fill_status=never_touched: 0 (bar_covered 0, of_plans 914)
- fill_status=risk_cap: 47 (bar_covered 47, of_plans 914)
- fill_status=invalidated: 11 (bar_covered 11, of_plans 914)
- fill_status=open: 0 (bar_covered 0, of_plans 914)
- fill_status=unknown: 0 (bar_covered 0, of_plans 914)
- alerts_per_day=1: 6 (plans 6)
- alerts_per_day=2_3: 7 (plans 20)
- alerts_per_day=4_6: 14 (plans 70)
- alerts_per_day=7_plus: 35 (plans 582)
- alert_hour_session=premarket: 38
- alert_hour_session=regular: 75
- alert_hour_session=after_close: 565
- alert_hour_session=unknown: 0
- actionable_before_open=yes: 603
- actionable_before_open=no: 75
- actionable_before_open=unknown: 0

