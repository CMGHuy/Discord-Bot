# Book autopsy, 2026-07-27 to 2026-10-21

- Window (first and last exit date): 2026-07-27 to 2026-10-21
- N closed trades: 473; bar-covered: 463
- Pooled net ExpR (modelled): -0.056; pooled win rate: 48.0%
- Net of frictions: modelled
- Cells tested: 296 (one BH pass over all of them); bootstrap resamples 10000, seed 42
- Effective frictions: {"commission_per_trade": 1.0, "commission_risk_basis": 100.0, "min_risk_fraction": 0.001, "slippage_bps": 5.0}
- Input SHA-256 manifest: 328c1a53205bbd1ae1496f167d7494a88aeac8937f40509e89f7e5acbfd9efbb (63 files; file hashes in JSON)
- Sector map snapshot SHA-256: 640d56ca80d10fe4e5214adf9a9a8f9712a82dcc7eced993203be2e1f3b78ac9 (64 tickers, 18 unknown; mapping in JSON)
- Invocation: 'C:\Users\HuyCao\AppData\Local\Programs\Python\Python311\python.exe' 'E:\Documents\Private\Projects\Discord-Bot\.claude\worktrees\2026-10-24-v192-gap-toward-stop-reclaim\scripts\reports\book_autopsy.py' E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/rows_full.csv E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/rejections_cut.csv --bars-dir E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/bars --out-dir E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/docs/superpowers/results/v192/autopsy-market/full --date 2026-10-21 --entry-type market
- Note: net R is modelled locally (apply_frictions slippage on both fills plus commission_r); live rows store gross R only
- Note: bar cuts read only --bars-dir; anchor lag is at most 4 calendar days (weekends/holidays included); its close must lie within 25% of its planned entry
- Note: alert hour has hour granularity: 09:00-09:29 ET counts as the regular session
- Note: every row drawn from this report is exploratory: the window overlaps the 2026 holdout (spec v161 boundary 5)
- Note: earnings_proximity: earnings_proximity: days_to_earnings is opportunistic; trades without it are uncovered
- Note: fomc_proximity: fomc_proximity: FOMC dates cover 2026-01-01 to 2027-12-08; trades outside are uncovered
- Note: macro: CPI and NFP omitted: market_events.py carries no past dates
- Note: sector_today: sector_today: today's sector map, not point-in-time
- Note: stop cells price the dollar loss at 2% of 10,000 USD
- Note: entry-type filter: market rows only (v192 disclosure); rejection tallies carry no entry type and are unfiltered

## Cells (not thin; by q, then |Δ|)

| cell | N | weeks | WR | net ExpR | gross ExpR | Δ net ExpR [95% CI] | q | notes |
|---|---|---|---|---|---|---|---|---|
| exit_reason=stop | 145 | 12 | 0.0% | -1.320 | -1.250 | -1.823 [-2.243, -1.488] | 0.001 | tickers 49; top share 6.9%; stop 0.37 ATR, loss at 2% $264, overshoot 0.806 |
| exit_reason=runner_be | 49 | 12 | 100.0% | 1.183 | 1.251 | +1.382 [0.979, 1.836] | 0.001 | tickers 26; top share 12.2%; stop 0.37 ATR, loss at 2% $n/a, overshoot n/a |
| gap_through_stop=at_stop | 119 | 13 | 0.0% | -1.072 | -1.000 | +0.797 [0.192, 1.090] | 0.001 | tickers 44; top share 7.6%; stop 0.38 ATR, loss at 2% $214, overshoot n/a |
| open_gap_bucket=favourable | 180 | 13 | 35.0% | -0.483 | -0.414 | -0.732 [-1.288, -0.250] | 0.001 | tickers 49; top share 6.1%; bar-covered 180 |
| holding_bucket=7m\|le_2d | 35 | 11 | 40.0% | -0.467 | -0.400 | -0.444 [-0.778, -0.209] | 0.001 | tickers 19; top share 11.4% |
| dollar_volume_bucket=ge_200m | 461 | 13 | 48.2% | -0.050 | 0.019 | -0.417 [-0.567, -0.257] | 0.001 | tickers 60; top share 8.7%; bar-covered 461 |
| weekend_hold=no | 435 | 13 | 47.1% | -0.142 | -0.073 | -1.068 [-1.620, -0.483] | 0.001 | tickers 63; top share 8.7% |
| weekend_hold=yes | 38 | 11 | 57.9% | 0.926 | 0.995 | +1.068 [0.483, 1.620] | 0.001 | tickers 29; top share 7.9% |
| open_gap_bucket=adverse_large | 185 | 13 | 58.9% | 0.252 | 0.320 | +0.495 [0.092, 1.033] | 0.009 | tickers 46; top share 11.9%; bar-covered 185 |
| exit_reason=other | 192 | 9 | 70.8% | 0.136 | 0.203 | +0.323 [0.067, 0.794] | 0.036 | tickers 50; top share 12.0%; stop 0.31 ATR, loss at 2% $218, overshoot n/a |
| holding_bucket=6m\|le_2d | 33 | 10 | 63.6% | 0.540 | 0.608 | +0.641 [0.046, 1.411] | 0.082 | tickers 22; top share 12.1% |
| weekday=Wed | 126 | 11 | 48.4% | -0.195 | -0.121 | -0.190 [-0.511, 0.005] | 0.121 | tickers 48; top share 13.5% |
| fomc_proximity=no_fomc | 433 | 13 | 45.0% | -0.076 | -0.007 | -0.236 [-1.087, 0.014] | 0.140 | tickers 62; top share 6.2% |
| open_gap_bucket=adverse_small | 54 | 12 | 57.4% | 0.325 | 0.394 | +0.416 [-0.044, 1.109] | 0.161 | tickers 29; top share 9.3%; bar-covered 54 |
| holding_bucket=5m\|le_2d | 42 | 10 | 47.6% | -0.530 | -0.465 | -0.520 [-0.897, 0.173] | 0.281 | tickers 21; top share 9.5% |
| friday_entry=no | 383 | 13 | 46.7% | -0.099 | -0.030 | -0.228 [-0.630, 0.093] | 0.299 | tickers 63; top share 7.6% |
| friday_entry=yes | 90 | 12 | 53.3% | 0.129 | 0.196 | +0.228 [-0.093, 0.630] | 0.299 | tickers 34; top share 12.2% |
| weekday=Fri | 90 | 12 | 53.3% | 0.129 | 0.196 | +0.228 [-0.093, 0.630] | 0.299 | tickers 34; top share 12.2% |
| holding_bucket=4m\|le_2d | 48 | 10 | 45.8% | -0.245 | -0.177 | -0.210 [-0.582, 0.112] | 0.299 | tickers 28; top share 8.3% |
| weekday=Tue | 61 | 11 | 42.6% | 0.072 | 0.139 | +0.146 [-0.093, 0.433] | 0.435 | tickers 26; top share 13.1% |
| sector_today=Information Technology | 250 | 13 | 52.4% | -0.058 | 0.009 | -0.207 [-0.622, 0.204] | 0.532 | tickers 25; top share 16.0% |
| exit_reason=scratch | 45 | 8 | 0.0% | -0.126 | -0.057 | -0.078 [-0.300, 0.087] | 0.532 | tickers 33; top share 6.7%; stop 0.42 ATR, loss at 2% $25, overshoot n/a |
| holding_bucket=3m\|le_2d | 65 | 13 | 41.5% | -0.175 | -0.107 | -0.138 [-0.615, 0.206] | 0.620 | tickers 31; top share 9.2% |
| holding_bucket=4w\|le_2d | 64 | 12 | 51.6% | 0.071 | 0.141 | +0.147 [-0.269, 0.518] | 0.680 | tickers 33; top share 7.8% |
| open_gap_bucket=flat | 34 | 12 | 52.9% | 0.120 | 0.188 | +0.174 [-0.328, 0.654] | 0.715 | tickers 21; top share 14.7%; bar-covered 34 |
| ticker=STX | 40 | 10 | 60.0% | 0.064 | 0.128 | +0.131 [-0.348, 0.794] | 0.715 | tickers 1; top share 100.0% |
| direction=bearish | 123 | 13 | 52.8% | -0.130 | -0.065 | -0.100 [-0.332, 0.232] | 0.738 | tickers 42; top share 8.9% |
| direction=bullish | 350 | 13 | 46.3% | -0.030 | 0.040 | +0.100 [-0.232, 0.332] | 0.738 | tickers 58; top share 8.3% |
| holding_bucket=2m\|le_2d | 57 | 10 | 45.6% | -0.114 | -0.044 | -0.066 [-0.537, 0.322] | 0.853 | tickers 25; top share 19.3% |
| opex_week=other | 355 | 10 | 54.1% | -0.052 | 0.016 | +0.017 [-0.231, 0.288] | 0.900 | tickers 61; top share 10.4% |
| holding_bucket=2w\|le_2d | 47 | 9 | 48.9% | -0.026 | 0.049 | +0.033 [-0.457, 0.514] | 0.931 | tickers 26; top share 8.5% |
| weekday=Thu | 94 | 11 | 45.7% | -0.063 | 0.007 | -0.009 [-0.453, 0.280] | 0.931 | tickers 37; top share 8.5% |
| weekday=Mon | 92 | 11 | 50.0% | -0.092 | -0.029 | -0.044 [-0.381, 0.509] | 0.940 | tickers 37; top share 9.8% |
| alert_hour=20 | 473 | 13 | 48.0% | -0.056 | 0.013 | n/a n/a | n/a | tickers 64; top share 8.5% |
| near_tp_close=other_exit | 473 | 13 | 48.0% | -0.056 | 0.013 | n/a n/a | n/a | tickers 64; top share 8.5% |

Thin cells (tested and counted in BH, never evidence): atr_pct_bucket 3, dollar_volume_bucket 1, earnings_proximity 3, exit_reason 2, fomc_proximity 1, gap_through_stop 1, holding_bucket 15, near_stop_reversal 2, opex_week 1, regime 1, sector_today 7, session_bucket 3, strategy_horizon 159, ticker 63, weekday 2

## Give-back (mfe_r minus gross R, every trade)

- N 453; mean 1.850; median 1.484

## Tallies

- fill_status=filled: 541 (bar_covered 530, of_plans 541)
- fill_status=expired_unfilled: 0 (bar_covered 0, of_plans 541)
- fill_status=never_touched: 0 (bar_covered 0, of_plans 541)
- fill_status=risk_cap: 0 (bar_covered 0, of_plans 541)
- fill_status=invalidated: 0 (bar_covered 0, of_plans 541)
- fill_status=open: 0 (bar_covered 0, of_plans 541)
- fill_status=unknown: 0 (bar_covered 0, of_plans 541)
- alerts_per_day=1: 7 (plans 7)
- alerts_per_day=2_3: 8 (plans 21)
- alerts_per_day=4_6: 14 (plans 69)
- alerts_per_day=7_plus: 31 (plans 444)
- alert_hour_session=premarket: 0
- alert_hour_session=regular: 0
- alert_hour_session=after_close: 541
- alert_hour_session=unknown: 0
- actionable_before_open=yes: 541
- actionable_before_open=no: 0
- actionable_before_open=unknown: 0

