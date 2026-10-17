# Book autopsy, 2026-07-20 to 2026-10-15

- Window (first and last exit date): 2026-07-20 to 2026-10-15
- N closed trades: 732; bar-covered: 718
- Pooled net ExpR (modelled): -0.127; pooled win rate: 51.6%
- Net of frictions: modelled
- Cells tested: 351 (one BH pass over all of them); bootstrap resamples 10000, seed 42
- Effective frictions: {"commission_per_trade": 1.0, "commission_risk_basis": 100.0, "min_risk_fraction": 0.001, "slippage_bps": 5.0}
- Input SHA-256 manifest: 9ad0869fc04830b431f6cc2d011fa49eab09c942c5728ffb84ace5ceb85c04cb (75 files; file hashes in JSON)
- Sector map snapshot SHA-256: ad53fc4cf47065ef1300787d8d20cb02d704d1fcdb3e224d23481c92e0889aa7 (76 tickers, 23 unknown; mapping in JSON)
- Invocation: 'C:\Users\HuyCao\AppData\Local\Programs\Python\Python311\python.exe' 'C:\Users\HuyCao\.codex\worktrees\b06d\Discord-Bot\scripts\reports\book_autopsy.py' 'C:\Users\HuyCao\.codex\worktrees\b06d\Discord-Bot\.superpowers\sdd\2026-10-15-v161-trade-scout_0-index\scratch\rows_corrected.csv' 'C:\Users\HuyCao\.codex\worktrees\b06d\Discord-Bot\.superpowers\sdd\2026-10-15-v161-trade-scout_0-index\scratch\rejections.csv' --bars-dir 'C:\Users\HuyCao\.codex\worktrees\b06d\Discord-Bot\.superpowers\sdd\2026-10-15-v161-trade-scout_0-index\scratch\autopsy_bars' --out-dir 'E:\Documents\Private\Projects\Discord-Bot\docs\superpowers\results' --date 2026-10-16
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
| exit_reason=stop | 136 | 11 | 0.0% | -1.350 | -1.281 | -1.503 [-2.005, -1.134] | 0.001 | tickers 48; top share 5.9%; stop 0.36 ATR, loss at 2% $270, overshoot 0.890 |
| near_tp_close=other_exit | 730 | 14 | 51.5% | -0.131 | -0.065 | -1.394 [-1.510, -1.266] | 0.001 | tickers 71; top share 7.5% |
| exit_reason=runner_be | 51 | 11 | 68.6% | 0.818 | 0.882 | +1.015 [0.496, 1.879] | 0.001 | tickers 26; top share 13.7%; stop 0.44 ATR, loss at 2% $36, overshoot n/a |
| gap_through_stop=at_stop | 170 | 14 | 0.0% | -1.068 | -1.000 | +0.884 [0.091, 1.157] | 0.001 | tickers 53; top share 7.1%; stop 0.36 ATR, loss at 2% $214, overshoot n/a |
| open_gap_bucket=favourable | 208 | 12 | 36.5% | -0.511 | -0.444 | -0.726 [-1.238, -0.333] | 0.001 | tickers 50; top share 8.6%; bar-covered 208 |
| open_gap_bucket=adverse_large | 177 | 12 | 53.7% | 0.204 | 0.272 | +0.490 [0.145, 0.930] | 0.003 | tickers 48; top share 11.9%; bar-covered 177 |
| alert_hour=20 | 434 | 12 | 46.3% | -0.068 | 0.000 | +0.374 [0.162, 0.996] | 0.007 | tickers 62; top share 8.5% |
| fomc_proximity=no_fomc | 664 | 14 | 49.4% | -0.146 | -0.079 | -0.205 [-1.115, -0.049] | 0.020 | tickers 71; top share 6.0% |
| holding_bucket=5m\|le_2d | 62 | 11 | 48.4% | -0.451 | -0.387 | -0.354 [-0.751, 0.031] | 0.165 | tickers 27; top share 8.1% |
| weekend_hold=no | 676 | 14 | 52.2% | -0.170 | -0.103 | -0.557 [-1.327, 0.079] | 0.180 | tickers 70; top share 7.5% |
| weekend_hold=yes | 56 | 12 | 44.6% | 0.387 | 0.453 | +0.557 [-0.079, 1.327] | 0.180 | tickers 39; top share 8.9% |
| open_gap_bucket=adverse_small | 54 | 11 | 55.6% | 0.295 | 0.363 | +0.450 [-0.051, 1.192] | 0.180 | tickers 30; top share 11.1%; bar-covered 54 |
| holding_bucket=7m\|le_2d | 51 | 11 | 47.1% | -0.280 | -0.216 | -0.165 [-0.409, 0.087] | 0.288 | tickers 23; top share 13.7% |
| weekday=Wed | 181 | 11 | 53.0% | -0.205 | -0.134 | -0.103 [-0.367, 0.032] | 0.298 | tickers 53; top share 9.9% |
| holding_bucket=3m\|le_2d | 95 | 13 | 47.4% | -0.302 | -0.236 | -0.201 [-0.554, 0.094] | 0.322 | tickers 40; top share 9.5% |
| holding_bucket=6m\|le_2d | 45 | 11 | 62.2% | 0.194 | 0.261 | +0.342 [-0.214, 0.882] | 0.337 | tickers 26; top share 13.3% |
| exit_reason=other | 461 | 11 | 65.1% | -0.058 | 0.007 | +0.186 [-0.093, 0.517] | 0.338 | tickers 64; top share 8.9%; stop 0.31 ATR, loss at 2% $224, overshoot n/a |
| holding_bucket=4w\|le_2d | 98 | 12 | 56.1% | 0.030 | 0.099 | +0.182 [-0.094, 0.492] | 0.338 | tickers 38; top share 8.2% |
| ticker=GLW | 30 | 11 | 33.3% | -0.404 | -0.337 | -0.289 [-0.760, 0.159] | 0.340 | tickers 1; top share 100.0% |
| open_gap_bucket=flat | 35 | 11 | 57.1% | 0.148 | 0.214 | +0.271 [-0.197, 0.708] | 0.405 | tickers 20; top share 14.3%; bar-covered 35 |
| direction=bearish | 262 | 14 | 51.5% | -0.218 | -0.154 | -0.142 [-0.298, 0.138] | 0.451 | tickers 55; top share 8.8% |
| direction=bullish | 470 | 14 | 51.7% | -0.076 | -0.009 | +0.142 [-0.138, 0.298] | 0.451 | tickers 68; top share 6.8% |
| ticker=WDC | 38 | 9 | 65.8% | 0.024 | 0.089 | +0.159 [-0.270, 0.367] | 0.504 | tickers 1; top share 100.0% |
| ticker=IREN | 33 | 8 | 75.8% | 0.175 | 0.239 | +0.317 [-0.504, 0.686] | 0.513 | tickers 1; top share 100.0% |
| friday_entry=no | 585 | 14 | 51.3% | -0.158 | -0.092 | -0.156 [-0.626, 0.159] | 0.571 | tickers 70; top share 6.7% |
| friday_entry=yes | 147 | 13 | 53.1% | -0.003 | 0.062 | +0.156 [-0.159, 0.626] | 0.571 | tickers 43; top share 10.9% |
| weekday=Fri | 147 | 13 | 53.1% | -0.003 | 0.062 | +0.156 [-0.159, 0.626] | 0.571 | tickers 43; top share 10.9% |
| holding_bucket=4m\|le_2d | 89 | 11 | 52.8% | -0.195 | -0.130 | -0.077 [-0.286, 0.160] | 0.612 | tickers 40; top share 7.9% |
| dollar_volume_bucket=ge_200m | 707 | 14 | 51.3% | -0.128 | -0.062 | -0.192 [-0.508, 1.025] | 0.621 | tickers 66; top share 7.8%; bar-covered 707 |
| holding_bucket=8m\|le_2d | 46 | 11 | 54.4% | -0.212 | -0.149 | -0.091 [-0.639, 0.219] | 0.728 | tickers 25; top share 8.7% |
| sector_today=Information Technology | 368 | 14 | 52.7% | -0.129 | -0.064 | -0.090 [-0.425, 0.201] | 0.766 | tickers 26; top share 14.9% |
| ticker=STX | 55 | 10 | 50.9% | -0.068 | -0.004 | +0.064 [-0.220, 0.766] | 0.775 | tickers 1; top share 100.0% |
| weekday=Mon | 126 | 11 | 42.9% | -0.203 | -0.141 | -0.092 [-0.375, 0.243] | 0.785 | tickers 43; top share 7.9% |
| ticker=NBIS | 45 | 12 | 60.0% | -0.210 | -0.147 | -0.089 [-0.594, 0.271] | 0.800 | tickers 1; top share 100.0% |
| ticker=MRVL | 30 | 9 | 46.7% | -0.049 | 0.017 | +0.082 [-0.217, 0.953] | 0.804 | tickers 1; top share 100.0% |
| holding_bucket=2w\|le_2d | 62 | 11 | 48.4% | -0.180 | -0.108 | -0.058 [-0.409, 0.275] | 0.823 | tickers 29; top share 9.7% |
| weekday=Tue | 108 | 11 | 49.1% | -0.097 | -0.032 | +0.035 [-0.183, 0.243] | 0.823 | tickers 29; top share 10.2% |
| opex_week=other | 617 | 10 | 55.4% | -0.132 | -0.066 | -0.032 [-0.253, 0.157] | 0.853 | tickers 69; top share 8.3% |
| weekday=Thu | 157 | 13 | 59.9% | -0.094 | -0.028 | +0.042 [-0.282, 0.305] | 0.891 | tickers 46; top share 8.3% |
| exit_reason=scratch | 38 | 8 | 0.0% | -0.138 | -0.070 | -0.012 [-0.155, 0.094] | 0.903 | tickers 28; top share 7.9%; stop 0.42 ATR, loss at 2% $28, overshoot n/a |
| holding_bucket=2m\|le_2d | 91 | 11 | 53.8% | -0.154 | -0.088 | -0.031 [-0.475, 0.243] | 0.909 | tickers 32; top share 15.4% |
| ticker=ARM | 31 | 10 | 51.6% | -0.162 | -0.100 | -0.036 [-0.602, 0.369] | 0.929 | tickers 1; top share 100.0% |

Thin cells (tested and counted in BH, never evidence): alert_hour 10, atr_pct_bucket 3, dollar_volume_bucket 2, exit_reason 4, fomc_proximity 1, gap_through_stop 1, gapped_through_entry 2, holding_bucket 15, near_stop_reversal 2, near_tp_close 1, opex_week 1, regime 1, sector_today 7, session_bucket 3, strategy_horizon 190, ticker 65, weekday 2

## Give-back (mfe_r minus gross R, every trade)

- N 701; mean 1.610; median 1.287

## Tallies

- fill_status=filled: 825 (bar_covered 809, of_plans 880)
- fill_status=expired_unfilled: 1 (bar_covered 1, of_plans 880)
- fill_status=never_touched: 0 (bar_covered 0, of_plans 880)
- fill_status=risk_cap: 45 (bar_covered 45, of_plans 880)
- fill_status=invalidated: 9 (bar_covered 9, of_plans 880)
- fill_status=open: 0 (bar_covered 0, of_plans 880)
- fill_status=unknown: 0 (bar_covered 0, of_plans 880)
- alerts_per_day=1: 7 (plans 7)
- alerts_per_day=2_3: 5 (plans 15)
- alerts_per_day=4_6: 14 (plans 70)
- alerts_per_day=7_plus: 33 (plans 552)
- alert_hour_session=premarket: 38
- alert_hour_session=regular: 67
- alert_hour_session=after_close: 539
- alert_hour_session=unknown: 0
- actionable_before_open=yes: 577
- actionable_before_open=no: 67
- actionable_before_open=unknown: 0

