# Book autopsy, 2026-07-20 to 2026-10-21

- Window (first and last exit date): 2026-07-20 to 2026-10-21
- N closed trades: 776; bar-covered: 761
- Pooled net ExpR (modelled): -0.114; pooled win rate: 52.3%
- Net of frictions: modelled
- Cells tested: 362 (one BH pass over all of them); bootstrap resamples 10000, seed 42
- Effective frictions: {"commission_per_trade": 1.0, "commission_risk_basis": 100.0, "min_risk_fraction": 0.001, "slippage_bps": 5.0}
- Input SHA-256 manifest: 8388aec4f555efb819a845fdf7f063aa6050af37f3e03d624e21285437916f93 (75 files; file hashes in JSON)
- Sector map snapshot SHA-256: ad53fc4cf47065ef1300787d8d20cb02d704d1fcdb3e224d23481c92e0889aa7 (76 tickers, 23 unknown; mapping in JSON)
- Invocation: 'C:\Users\HuyCao\AppData\Local\Programs\Python\Python311\python.exe' 'E:\Documents\Private\Projects\Discord-Bot\.claude\worktrees\2026-10-24-v192-gap-toward-stop-reclaim\scripts\reports\book_autopsy.py' E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/rows_full.csv E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/rejections_cut.csv --bars-dir E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/bars --out-dir E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/docs/superpowers/results/v192/autopsy-market/control-all-types/full --date 2026-10-21
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
| exit_reason=stop | 156 | 12 | 0.0% | -1.338 | -1.268 | -1.532 [-2.035, -1.202] | 0.001 | tickers 52; top share 6.4%; stop 0.37 ATR, loss at 2% $268, overshoot 0.853 |
| near_tp_close=other_exit | 774 | 15 | 52.2% | -0.118 | -0.051 | -1.381 [-1.485, -1.257] | 0.001 | tickers 73; top share 7.5% |
| exit_reason=runner_be | 59 | 12 | 96.6% | 1.031 | 1.096 | +1.239 [0.757, 1.822] | 0.001 | tickers 30; top share 11.9%; stop 0.39 ATR, loss at 2% $15, overshoot n/a |
| gap_through_stop=at_stop | 184 | 15 | 0.0% | -1.069 | -1.000 | +0.847 [0.284, 1.129] | 0.001 | tickers 56; top share 6.5%; stop 0.38 ATR, loss at 2% $214, overshoot n/a |
| open_gap_bucket=favourable | 226 | 13 | 36.3% | -0.487 | -0.421 | -0.715 [-1.287, -0.321] | 0.001 | tickers 55; top share 8.0%; bar-covered 226 |
| open_gap_bucket=adverse_large | 193 | 13 | 58.0% | 0.228 | 0.296 | +0.499 [0.138, 1.019] | 0.003 | tickers 48; top share 11.4%; bar-covered 193 |
| holding_bucket=7m\|le_2d | 55 | 12 | 45.5% | -0.357 | -0.292 | -0.261 [-0.541, -0.105] | 0.008 | tickers 24; top share 14.5% |
| weekend_hold=no | 713 | 15 | 52.7% | -0.169 | -0.103 | -0.679 [-1.370, -0.086] | 0.058 | tickers 72; top share 7.6% |
| weekend_hold=yes | 63 | 13 | 47.6% | 0.510 | 0.577 | +0.679 [0.086, 1.370] | 0.058 | tickers 42; top share 7.9% |
| fomc_proximity=no_fomc | 708 | 15 | 50.1% | -0.129 | -0.062 | -0.169 [-1.083, -0.018] | 0.065 | tickers 72; top share 6.1% |
| open_gap_bucket=adverse_small | 60 | 12 | 56.7% | 0.298 | 0.366 | +0.433 [0.021, 1.116] | 0.085 | tickers 31; top share 15.0%; bar-covered 60 |
| holding_bucket=5m\|le_2d | 63 | 11 | 49.2% | -0.474 | -0.409 | -0.392 [-0.811, 0.017] | 0.136 | tickers 27; top share 7.9% |
| alert_hour=20 | 473 | 13 | 48.0% | -0.056 | 0.013 | +0.334 [-0.027, 0.967] | 0.136 | tickers 64; top share 8.5% |
| holding_bucket=6m\|le_2d | 48 | 12 | 62.5% | 0.251 | 0.318 | +0.389 [-0.120, 0.990] | 0.246 | tickers 28; top share 12.5% |
| holding_bucket=4m\|le_2d | 93 | 11 | 51.6% | -0.244 | -0.178 | -0.147 [-0.368, 0.053] | 0.250 | tickers 40; top share 7.5% |
| ticker=GLW | 30 | 11 | 33.3% | -0.406 | -0.339 | -0.303 [-0.800, 0.141] | 0.317 | tickers 1; top share 100.0% |
| exit_reason=other | 462 | 12 | 65.1% | -0.044 | 0.021 | +0.174 [-0.083, 0.511] | 0.317 | tickers 64; top share 8.9%; stop 0.31 ATR, loss at 2% $224, overshoot n/a |
| holding_bucket=3m\|le_2d | 104 | 14 | 46.2% | -0.272 | -0.205 | -0.182 [-0.520, 0.087] | 0.345 | tickers 42; top share 8.6% |
| holding_bucket=4w\|le_2d | 101 | 13 | 57.4% | 0.017 | 0.086 | +0.151 [-0.106, 0.445] | 0.445 | tickers 38; top share 7.9% |
| weekday=Wed | 186 | 12 | 53.2% | -0.176 | -0.105 | -0.081 [-0.339, 0.046] | 0.445 | tickers 53; top share 10.8% |
| gapped_through_entry=not_gapped | 49 | 8 | 40.8% | -0.475 | -0.412 | -0.341 [-1.668, 0.490] | 0.533 | tickers 23; top share 14.3%; bar-covered 49 |
| open_gap_bucket=flat | 38 | 12 | 52.6% | 0.116 | 0.183 | +0.217 [-0.238, 0.602] | 0.539 | tickers 23; top share 15.8%; bar-covered 38 |
| opex_week=other | 629 | 11 | 57.4% | -0.130 | -0.064 | -0.086 [-0.274, 0.111] | 0.556 | tickers 70; top share 8.4% |
| ticker=IREN | 34 | 8 | 73.5% | 0.108 | 0.173 | +0.233 [-0.526, 0.568] | 0.633 | tickers 1; top share 100.0% |
| ticker=WDC | 38 | 9 | 65.8% | 0.006 | 0.072 | +0.126 [-0.346, 0.330] | 0.633 | tickers 1; top share 100.0% |
| weekday=Tue | 111 | 12 | 52.2% | -0.065 | 0.000 | +0.058 [-0.083, 0.260] | 0.639 | tickers 31; top share 9.9% |
| dollar_volume_bucket=ge_200m | 750 | 15 | 52.1% | -0.113 | -0.047 | -0.177 [-0.492, 1.048] | 0.651 | tickers 67; top share 7.7%; bar-covered 750 |
| sector_today=Information Technology | 388 | 15 | 53.3% | -0.150 | -0.084 | -0.116 [-0.444, 0.168] | 0.660 | tickers 26; top share 14.9% |
| direction=bearish | 267 | 15 | 54.7% | -0.180 | -0.116 | -0.100 [-0.274, 0.226] | 0.707 | tickers 56; top share 8.6% |
| direction=bullish | 509 | 15 | 51.1% | -0.080 | -0.012 | +0.100 [-0.226, 0.274] | 0.707 | tickers 71; top share 6.9% |
| friday_entry=no | 615 | 15 | 52.5% | -0.132 | -0.065 | -0.084 [-0.481, 0.204] | 0.743 | tickers 72; top share 6.8% |
| friday_entry=yes | 161 | 14 | 51.5% | -0.047 | 0.018 | +0.084 [-0.204, 0.481] | 0.743 | tickers 44; top share 9.9% |
| weekday=Fri | 161 | 14 | 51.5% | -0.047 | 0.018 | +0.084 [-0.204, 0.481] | 0.743 | tickers 44; top share 9.9% |
| holding_bucket=8m\|le_2d | 46 | 11 | 60.9% | -0.178 | -0.115 | -0.069 [-0.529, 0.218] | 0.769 | tickers 25; top share 8.7% |
| ticker=NBIS | 47 | 13 | 59.6% | -0.185 | -0.121 | -0.076 [-0.566, 0.301] | 0.842 | tickers 1; top share 100.0% |
| weekday=Mon | 132 | 12 | 47.7% | -0.165 | -0.102 | -0.062 [-0.324, 0.261] | 0.848 | tickers 44; top share 7.6% |
| holding_bucket=2m\|le_2d | 98 | 12 | 55.1% | -0.151 | -0.084 | -0.043 [-0.429, 0.247] | 0.868 | tickers 34; top share 15.3% |
| exit_reason=scratch | 48 | 9 | 0.0% | -0.125 | -0.056 | -0.012 [-0.151, 0.075] | 0.868 | tickers 35; top share 6.2%; stop 0.42 ATR, loss at 2% $25, overshoot n/a |
| ticker=MRVL | 31 | 10 | 51.6% | -0.060 | 0.006 | +0.056 [-0.246, 0.800] | 0.872 | tickers 1; top share 100.0% |
| weekday=Thu | 173 | 13 | 57.2% | -0.087 | -0.020 | +0.035 [-0.276, 0.272] | 0.910 | tickers 49; top share 7.5% |
| ticker=ARM | 32 | 10 | 56.2% | -0.085 | -0.023 | +0.031 [-0.515, 0.465] | 0.928 | tickers 1; top share 100.0% |
| ticker=STX | 58 | 12 | 50.0% | -0.130 | -0.066 | -0.017 [-0.285, 0.610] | 0.944 | tickers 1; top share 100.0% |
| holding_bucket=2w\|le_2d | 67 | 12 | 49.2% | -0.109 | -0.037 | +0.005 [-0.351, 0.302] | 0.985 | tickers 30; top share 9.0% |

Thin cells (tested and counted in BH, never evidence): alert_hour 10, atr_pct_bucket 3, dollar_volume_bucket 2, earnings_proximity 3, exit_reason 4, fomc_proximity 1, gap_through_stop 1, gapped_through_entry 1, holding_bucket 16, near_stop_reversal 2, near_tp_close 1, opex_week 1, regime 1, sector_today 7, session_bucket 3, strategy_horizon 196, ticker 66, weekday 2

## Give-back (mfe_r minus gross R, every trade)

- N 749; mean 1.657; median 1.315

## Tallies

- fill_status=filled: 848 (bar_covered 832, of_plans 909)
- fill_status=expired_unfilled: 1 (bar_covered 1, of_plans 909)
- fill_status=never_touched: 0 (bar_covered 0, of_plans 909)
- fill_status=risk_cap: 49 (bar_covered 49, of_plans 909)
- fill_status=invalidated: 11 (bar_covered 11, of_plans 909)
- fill_status=open: 0 (bar_covered 0, of_plans 909)
- fill_status=unknown: 0 (bar_covered 0, of_plans 909)
- alerts_per_day=1: 7 (plans 7)
- alerts_per_day=2_3: 7 (plans 19)
- alerts_per_day=4_6: 15 (plans 74)
- alerts_per_day=7_plus: 34 (plans 573)
- alert_hour_session=premarket: 38
- alert_hour_session=regular: 75
- alert_hour_session=after_close: 560
- alert_hour_session=unknown: 0
- actionable_before_open=yes: 598
- actionable_before_open=no: 75
- actionable_before_open=unknown: 0

