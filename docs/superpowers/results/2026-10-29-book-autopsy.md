# Book autopsy, 2026-07-20 to 2026-10-29

- Window (first and last exit date): 2026-07-20 to 2026-10-29
- N closed trades: 828; bar-covered: 810
- Pooled net ExpR (modelled): -0.113; pooled win rate: 50.6%
- Net of frictions: modelled
- Cells tested: 368 (one BH pass over all of them); bootstrap resamples 10000, seed 42
- Effective frictions: {"commission_per_trade": 1.0, "commission_risk_basis": 100.0, "min_risk_fraction": 0.001, "slippage_bps": 5.0}
- Input SHA-256 manifest: 2eb70b026a8d4a472ffa9d768a157226f1516538bf1ba80db27d9728b15e12d6 (75 files; file hashes in JSON)
- Sector map snapshot SHA-256: ad53fc4cf47065ef1300787d8d20cb02d704d1fcdb3e224d23481c92e0889aa7 (76 tickers, 23 unknown; mapping in JSON)
- Invocation: 'C:\Users\HuyCao\AppData\Local\Programs\Python\Python311\python.exe' 'E:\Documents\Private\Projects\Discord-Bot\scripts\reports\book_autopsy.py' C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/854b4512-b6bf-4405-83b4-7d4e09e966c4/scratchpad/rows.csv C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/854b4512-b6bf-4405-83b4-7d4e09e966c4/scratchpad/rejections.csv --bars-dir C:/Users/HuyCao/AppData/Local/Temp/claude/E--Documents-Private-Projects-Discord-Bot/854b4512-b6bf-4405-83b4-7d4e09e966c4/scratchpad/autopsy_bars --date 2026-10-29
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
| exit_reason=runner_tp2 | 37 | 8 | 100.0% | 2.747 | 2.818 | +2.993 [2.615, 3.320] | 0.001 | tickers 25; top share 8.1%; stop 0.34 ATR, loss at 2% $n/a, overshoot n/a |
| exit_reason=stop | 184 | 13 | 0.0% | -1.307 | -1.236 | -1.535 [-2.032, -1.222] | 0.001 | tickers 55; top share 6.5%; stop 0.38 ATR, loss at 2% $261, overshoot 0.852 |
| near_tp_close=other_exit | 826 | 16 | 50.5% | -0.116 | -0.049 | -1.379 [-1.475, -1.261] | 0.001 | tickers 73; top share 7.3% |
| exit_reason=runner_be | 65 | 13 | 96.9% | 1.069 | 1.136 | +1.283 [0.838, 1.813] | 0.001 | tickers 33; top share 10.8%; stop 0.37 ATR, loss at 2% $15, overshoot n/a |
| gap_through_stop=at_stop | 210 | 16 | 0.0% | -1.069 | -1.000 | +0.846 [0.331, 1.115] | 0.001 | tickers 59; top share 6.7%; stop 0.38 ATR, loss at 2% $214, overshoot n/a |
| gap_through_stop=through_stop | 51 | 8 | 0.0% | -1.915 | -1.852 | -0.846 [-1.115, -0.331] | 0.001 | tickers 26; top share 11.8%; stop 0.39 ATR, loss at 2% $383, overshoot 0.852 |
| open_gap_bucket=favourable | 256 | 14 | 35.2% | -0.444 | -0.376 | -0.665 [-1.175, -0.311] | 0.001 | tickers 57; top share 7.4%; bar-covered 256 |
| open_gap_bucket=adverse_large | 205 | 14 | 56.1% | 0.220 | 0.289 | +0.470 [0.136, 0.949] | 0.004 | tickers 52; top share 10.7%; bar-covered 205 |
| weekend_hold=no | 756 | 16 | 51.2% | -0.167 | -0.100 | -0.630 [-1.219, -0.109] | 0.042 | tickers 72; top share 7.4% |
| weekend_hold=yes | 72 | 14 | 44.4% | 0.463 | 0.530 | +0.630 [0.109, 1.219] | 0.042 | tickers 43; top share 6.9% |
| holding_bucket=7m\|le_2d | 56 | 12 | 46.4% | -0.299 | -0.234 | -0.200 [-0.412, -0.026] | 0.070 | tickers 24; top share 14.3% |
| alert_hour=20 | 518 | 14 | 46.3% | -0.051 | 0.018 | +0.362 [0.034, 0.936] | 0.083 | tickers 66; top share 8.1% |
| open_gap_bucket=adverse_small | 63 | 12 | 55.6% | 0.300 | 0.369 | +0.427 [0.020, 1.036] | 0.092 | tickers 32; top share 15.9%; bar-covered 63 |
| holding_bucket=4m\|le_2d | 98 | 13 | 49.0% | -0.266 | -0.200 | -0.174 [-0.413, 0.014] | 0.146 | tickers 41; top share 7.1% |
| fomc_proximity=no_fomc | 747 | 16 | 48.6% | -0.132 | -0.065 | -0.199 [-0.931, 0.803] | 0.150 | tickers 72; top share 6.0% |
| sector_today=Industrials | 30 | 11 | 36.7% | -0.404 | -0.332 | -0.293 [-0.627, 0.050] | 0.193 | tickers 4; top share 53.3% |
| weekday=Wed | 193 | 13 | 51.3% | -0.203 | -0.132 | -0.118 [-0.404, 0.023] | 0.246 | tickers 54; top share 10.4% |
| holding_bucket=6m\|le_2d | 49 | 12 | 61.2% | 0.224 | 0.291 | +0.358 [-0.139, 0.875] | 0.281 | tickers 28; top share 12.2% |
| holding_bucket=3m\|le_2d | 110 | 15 | 44.5% | -0.286 | -0.219 | -0.200 [-0.532, 0.072] | 0.301 | tickers 44; top share 8.2% |
| exit_reason=other | 462 | 12 | 65.1% | -0.044 | 0.021 | +0.156 [-0.068, 0.485] | 0.320 | tickers 64; top share 8.9%; stop 0.31 ATR, loss at 2% $224, overshoot n/a |
| ticker=GLW | 30 | 11 | 33.3% | -0.406 | -0.339 | -0.304 [-0.808, 0.160] | 0.338 | tickers 1; top share 100.0% |
| holding_bucket=5m\|le_2d | 65 | 13 | 49.2% | -0.413 | -0.348 | -0.326 [-0.732, 0.150] | 0.355 | tickers 27; top share 7.7% |
| holding_bucket=4w\|le_2d | 105 | 14 | 56.2% | 0.013 | 0.082 | +0.144 [-0.095, 0.410] | 0.430 | tickers 38; top share 7.6% |
| sector_today=Health Care | 31 | 10 | 54.8% | 0.158 | 0.227 | +0.303 [-0.209, 1.066] | 0.460 | tickers 4; top share 77.4% |
| weekday=Tue | 127 | 13 | 49.6% | -0.053 | 0.013 | +0.071 [-0.056, 0.241] | 0.460 | tickers 36; top share 9.4% |
| gapped_through_entry=not_gapped | 53 | 9 | 37.7% | -0.501 | -0.438 | -0.322 [-1.319, 0.303] | 0.485 | tickers 23; top share 13.2%; bar-covered 53 |
| open_gap_bucket=flat | 42 | 13 | 50.0% | 0.110 | 0.178 | +0.204 [-0.207, 0.605] | 0.539 | tickers 26; top share 14.3%; bar-covered 42 |
| opex_week=other | 680 | 12 | 55.0% | -0.127 | -0.061 | -0.083 [-0.266, 0.101] | 0.539 | tickers 71; top share 8.1% |
| direction=bearish | 273 | 16 | 53.5% | -0.192 | -0.128 | -0.119 [-0.286, 0.167] | 0.585 | tickers 56; top share 8.4% |
| direction=bullish | 555 | 16 | 49.2% | -0.073 | -0.005 | +0.119 [-0.167, 0.286] | 0.585 | tickers 71; top share 6.7% |
| dollar_volume_bucket=ge_200m | 799 | 16 | 50.6% | -0.107 | -0.041 | -0.172 [-0.480, 1.056] | 0.660 | tickers 67; top share 7.5%; bar-covered 799 |
| friday_entry=no | 657 | 16 | 50.7% | -0.135 | -0.068 | -0.108 [-0.481, 0.166] | 0.667 | tickers 72; top share 6.5% |
| friday_entry=yes | 171 | 15 | 50.3% | -0.027 | 0.040 | +0.108 [-0.166, 0.481] | 0.667 | tickers 46; top share 9.9% |
| weekday=Fri | 171 | 15 | 50.3% | -0.027 | 0.040 | +0.108 [-0.166, 0.481] | 0.667 | tickers 46; top share 9.9% |
| ticker=IREN | 36 | 9 | 69.4% | 0.070 | 0.135 | +0.191 [-0.556, 0.531] | 0.693 | tickers 1; top share 100.0% |
| holding_bucket=2m\|le_2d | 106 | 13 | 51.9% | -0.200 | -0.133 | -0.101 [-0.494, 0.182] | 0.693 | tickers 36; top share 15.1% |
| holding_bucket=8m\|le_2d | 50 | 13 | 58.0% | -0.185 | -0.121 | -0.077 [-0.501, 0.178] | 0.739 | tickers 27; top share 8.0% |
| sector_today=Information Technology | 408 | 16 | 52.2% | -0.141 | -0.074 | -0.060 [-0.349, 0.196] | 0.817 | tickers 26; top share 14.7% |
| ticker=STX | 60 | 13 | 48.3% | -0.161 | -0.097 | -0.052 [-0.352, 0.482] | 0.837 | tickers 1; top share 100.0% |
| ticker=ARM | 34 | 12 | 55.9% | -0.043 | 0.020 | +0.073 [-0.439, 0.533] | 0.852 | tickers 1; top share 100.0% |
| ticker=NBIS | 49 | 14 | 57.1% | -0.181 | -0.116 | -0.072 [-0.546, 0.293] | 0.852 | tickers 1; top share 100.0% |
| ticker=MRVL | 31 | 10 | 51.6% | -0.060 | 0.006 | +0.055 [-0.247, 0.789] | 0.874 | tickers 1; top share 100.0% |
| weekday=Thu | 186 | 14 | 53.8% | -0.134 | -0.067 | -0.028 [-0.394, 0.224] | 0.890 | tickers 54; top share 7.0% |
| weekday=Mon | 138 | 13 | 48.5% | -0.098 | -0.035 | +0.017 [-0.271, 0.406] | 0.924 | tickers 45; top share 7.2% |
| exit_reason=scratch | 59 | 10 | 0.0% | -0.116 | -0.045 | -0.004 [-0.140, 0.077] | 0.936 | tickers 40; top share 5.1%; stop 0.43 ATR, loss at 2% $23, overshoot n/a |
| holding_bucket=2w\|le_2d | 74 | 13 | 48.6% | -0.095 | -0.022 | +0.019 [-0.366, 0.382] | 0.960 | tickers 31; top share 9.5% |
| ticker=WDC | 41 | 11 | 61.0% | -0.101 | -0.035 | +0.012 [-0.612, 0.254] | 0.995 | tickers 1; top share 100.0% |

Thin cells (tested and counted in BH, never evidence): alert_hour 10, atr_pct_bucket 3, dollar_volume_bucket 2, earnings_proximity 3, exit_reason 3, fomc_proximity 1, gapped_through_entry 1, holding_bucket 17, near_stop_reversal 2, near_tp_close 1, opex_week 1, regime 1, sector_today 5, session_bucket 3, strategy_horizon 201, ticker 66, weekday 2

## Give-back (mfe_r minus gross R, every trade)

- N 801; mean 1.662; median 1.324

## Tallies

- fill_status=filled: 908 (bar_covered 889, of_plans 970)
- fill_status=expired_unfilled: 1 (bar_covered 1, of_plans 970)
- fill_status=never_touched: 0 (bar_covered 0, of_plans 970)
- fill_status=risk_cap: 50 (bar_covered 50, of_plans 970)
- fill_status=invalidated: 11 (bar_covered 11, of_plans 970)
- fill_status=open: 0 (bar_covered 0, of_plans 970)
- fill_status=unknown: 0 (bar_covered 0, of_plans 970)
- alerts_per_day=1: 6 (plans 6)
- alerts_per_day=2_3: 7 (plans 19)
- alerts_per_day=4_6: 16 (plans 80)
- alerts_per_day=7_plus: 38 (plans 629)
- alert_hour_session=premarket: 38
- alert_hour_session=regular: 83
- alert_hour_session=after_close: 613
- alert_hour_session=unknown: 0
- actionable_before_open=yes: 651
- actionable_before_open=no: 83
- actionable_before_open=unknown: 0

