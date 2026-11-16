# Book autopsy, 2026-07-20 to 2026-11-16

- Window (first and last exit date): 2026-07-20 to 2026-11-16
- N closed trades: 1067; bar-covered: 1042
- Pooled net ExpR (modelled): -0.087; pooled win rate: 44.6%
- stall exclusion stall_2026_08: N 37, gross ExpR -0.645, worst R -6.033
- Net of frictions: modelled
- Cells tested: 411 (one BH pass over all of them); bootstrap resamples 10000, seed 42
- Exit-model era boundary (production deploy of b4ef2e87): 2026-09-15T08:54:50Z (source: VM /opt/swing-bot git reflog: 8c0aeec965ff reset at 2026-09-15T08:54:50Z); era columns carry no CI and no q
- alert-hour coverage (trades): live 507, discord 266, unknown 294
- Effective frictions: {"commission_per_trade": 1.0, "commission_risk_basis": 100.0, "min_risk_fraction": 0.001, "slippage_bps": 5.0}
- Input SHA-256 manifest: fe403481f18a74886388fc0117cbe65a1f5e9ee7b670980832422c25e5d65faa (89 files; file hashes in JSON)
- Sector map snapshot SHA-256: 65bf26fb84bef39380842a26cddafc014fa81e2d50d6b1c961b38d72e934cc24 (89 tickers, 27 unknown; mapping in JSON)
- Invocation: 'C:\Users\HuyCao\AppData\Local\Programs\Python\Python311\python.exe' 'E:\Documents\Private\Projects\Discord-Bot\scripts\reports\book_autopsy.py' C:/Users/HuyCao/AppData/Local/Temp/claude/7e460affbd84d936/95f2de5c-61ee-44e2-95ed-1fb3238728c6/scratchpad/rows.csv C:/Users/HuyCao/AppData/Local/Temp/claude/7e460affbd84d936/95f2de5c-61ee-44e2-95ed-1fb3238728c6/scratchpad/rejections.csv --bars-dir C:/Users/HuyCao/AppData/Local/Temp/claude/7e460affbd84d936/95f2de5c-61ee-44e2-95ed-1fb3238728c6/scratchpad/autopsy_bars
- Note: net R is modelled locally (apply_frictions slippage on both fills plus commission_r); live rows store gross R only
- Note: bar cuts read only --bars-dir; anchor lag is at most 4 calendar days (weekends/holidays included); its close must lie within 25% of its planned entry
- Note: alert hour comes only from issued_at (the live stamp or the v200 Discord backfill); a plan without one is unknown, never a bar-date or fill hour
- Note: alert hour has hour granularity: 09:00-09:29 ET counts as the regular session
- Note: every row drawn from this report is exploratory: the window overlaps the 2026 holdout (spec v161 boundary 5)
- Note: Gap sign: open_gap_pct compares the fill-day open with the planned entry and is positive when the open was worse for the trade (higher for a long, lower for a short), so open_better is an open more than 0.25% on the trade's side of the planned entry, flat is within 0.25%, open_worse_small is worse by up to 1.0% and open_worse_large is worse by more than 1.0%.
- Note: earnings_proximity: earnings_proximity: days_to_earnings is opportunistic; trades without it are uncovered
- Note: fomc_proximity: fomc_proximity: FOMC dates cover 2026-01-01 to 2027-12-08; trades outside are uncovered
- Note: macro: CPI and NFP omitted: market_events.py carries no past dates
- Note: sector_today: sector_today: today's sector map, not point-in-time
- Note: stop cells price the dollar loss at 2% of 10,000 USD

## Cells (not thin; by q, then |Δ|)

| cell | N | weeks | WR | net ExpR | gross ExpR | Δ net ExpR [95% CI] | q | eras pre / straddle / post (N WR net) | notes |
|---|---|---|---|---|---|---|---|---|---|
| exit_reason=runner_tp2 | 63 | 10 | 100.0% | 2.958 | 3.032 | +3.236 [2.785, 3.505] | 0.001 | 3 100.0% +1.297 / 2 100.0% +2.266 / 58 100.0% +3.067 | tickers 32; top share 9.5%; stop 0.30 ATR, loss at 2% $n/a, overshoot n/a; outcome-defined (not known at entry) |
| exit_reason=stop | 317 | 16 | 0.0% | -1.200 | -1.127 | -1.583 [-2.093, -1.304] | 0.001 | 49 0.0% -1.351 / 2 0.0% -1.066 / 266 0.0% -1.174 | tickers 68; top share 5.4%; stop 0.31 ATR, loss at 2% $240, overshoot 0.839; outcome-defined (not known at entry) |
| exit_reason=runner_be | 94 | 16 | 97.9% | 1.310 | 1.381 | +1.533 [1.071, 1.932] | 0.001 | 26 92.3% +0.458 / 0 n/a / 68 100.0% +1.636 | tickers 45; top share 11.7%; stop 0.31 ATR, loss at 2% $15, overshoot n/a; outcome-defined (not known at entry) |
| near_tp_close=other_exit | 1065 | 19 | 44.5% | -0.090 | -0.020 | -1.353 [-1.457, -1.225] | 0.001 | 549 60.8% -0.143 / 8 25.0% +0.270 / 508 27.2% -0.038 | tickers 87; top share 6.2%; outcome-defined (not known at entry) |
| gap_through_stop=at_stop | 344 | 19 | 0.0% | -1.072 | -1.000 | +0.835 [0.396, 1.271] | 0.001 | 96 0.0% -1.063 / 2 0.0% -1.066 / 246 0.0% -1.075 | tickers 71; top share 5.2%; stop 0.31 ATR, loss at 2% $214, overshoot n/a; outcome-defined (not known at entry) |
| gap_through_stop=through_stop | 48 | 10 | 0.0% | -1.907 | -1.839 | -0.835 [-1.271, -0.396] | 0.001 | 28 0.0% -1.566 / 0 n/a / 20 0.0% -2.384 | tickers 28; top share 10.4%; stop 0.28 ATR, loss at 2% $381, overshoot 0.839; outcome-defined (not known at entry) |
| strategy_horizon=Volume Profile HVN\|2w | 36 | 11 | 30.6% | -0.460 | -0.386 | -0.386 [-0.703, -0.228] | 0.001 | 17 58.8% -0.303 / 0 n/a / 19 5.3% -0.600 | tickers 19; top share 13.9% |
| weekend_hold=no | 965 | 19 | 44.8% | -0.153 | -0.084 | -0.687 [-1.110, -0.253] | 0.011 | 510 62.7% -0.145 / 7 14.3% -0.067 / 448 24.8% -0.164 | tickers 85; top share 6.4%; outcome-defined (not known at entry) |
| weekend_hold=yes | 102 | 17 | 43.1% | 0.534 | 0.604 | +0.687 [0.253, 1.110] | 0.011 | 41 39.0% -0.054 / 1 100.0% +2.634 / 60 45.0% +0.901 | tickers 55; top share 4.9%; outcome-defined (not known at entry); era sign flip |
| open_gap_bucket=open_better | 360 | 17 | 32.5% | -0.272 | -0.201 | -0.402 [-0.703, -0.095] | 0.036 | 134 48.5% -0.393 / 5 20.0% +0.076 / 221 23.1% -0.207 | tickers 73; top share 6.4%; bar-covered 360; fill-defined (not known at entry) |
| weekday=Wed | 242 | 15 | 44.6% | -0.243 | -0.171 | -0.201 [-0.446, -0.024] | 0.063 | 130 65.4% -0.152 / 0 n/a / 112 20.5% -0.348 | tickers 66; top share 8.3% |
| holding_bucket=4m\|le_2d | 117 | 15 | 42.7% | -0.315 | -0.248 | -0.256 [-0.562, -0.029] | 0.073 | 77 59.7% -0.172 / 0 n/a / 40 10.0% -0.590 | tickers 46; top share 7.7%; outcome-defined (not known at entry) |
| holding_bucket=7m\|le_2d | 65 | 15 | 43.1% | -0.287 | -0.221 | -0.213 [-0.469, -0.018] | 0.089 | 41 53.7% -0.258 / 0 n/a / 24 25.0% -0.337 | tickers 31; top share 12.3%; outcome-defined (not known at entry) |
| sector_today=Industrials | 41 | 13 | 31.7% | -0.378 | -0.306 | -0.260 [-0.504, -0.019] | 0.093 | 18 50.0% -0.305 / 1 100.0% +1.899 / 22 13.6% -0.541 | tickers 5; top share 46.3% |
| open_gap_bucket=open_worse_small | 70 | 16 | 52.9% | 0.303 | 0.373 | +0.389 [0.021, 0.951] | 0.101 | 37 67.6% +0.140 / 0 n/a / 33 36.4% +0.486 | tickers 37; top share 14.3%; bar-covered 70; fill-defined (not known at entry) |
| open_gap_bucket=open_worse_large | 306 | 17 | 45.4% | 0.137 | 0.208 | +0.307 [0.005, 0.619] | 0.127 | 110 69.1% +0.108 / 2 50.0% +0.917 / 194 32.0% +0.145 | tickers 64; top share 7.8%; bar-covered 306; fill-defined (not known at entry) |
| sector_today=Health Care | 34 | 12 | 55.9% | 0.326 | 0.396 | +0.484 [-0.076, 1.136] | 0.223 | 17 58.8% -0.174 / 0 n/a / 17 52.9% +0.827 | tickers 4; top share 76.5%; era sign flip |
| fomc_proximity=no_fomc | 979 | 19 | 42.6% | -0.104 | -0.034 | -0.204 [-0.882, 0.932] | 0.249 | 488 58.8% -0.152 / 3 0.0% -0.732 / 488 26.6% -0.052 | tickers 86; top share 5.3%; outcome-defined (not known at entry) |
| ticker=RKLB | 35 | 13 | 45.7% | 0.384 | 0.454 | +0.487 [-0.124, 1.311] | 0.328 | 17 52.9% -0.171 / 0 n/a / 18 38.9% +0.907 | tickers 1; top share 100.0%; era sign flip |
| exit_reason=scratch | 111 | 13 | 0.0% | -0.155 | -0.081 | -0.075 [-0.200, 0.022] | 0.349 | 11 0.0% -0.215 / 4 0.0% -0.060 / 96 0.0% -0.152 | tickers 56; top share 5.4%; stop 0.35 ATR, loss at 2% $31, overshoot n/a; outcome-defined (not known at entry) |
| alert_hour=15 | 55 | 14 | 32.7% | -0.293 | -0.222 | -0.266 [-0.682, 0.099] | 0.360 | 23 39.1% -0.585 / 0 n/a / 32 28.1% -0.083 | tickers 32; top share 7.3% |
| weekday=Tue | 165 | 15 | 45.5% | -0.027 | 0.042 | +0.072 [-0.038, 0.229] | 0.390 | 89 56.2% -0.117 / 1 100.0% +1.899 / 75 32.0% +0.053 | tickers 46; top share 8.5%; era sign flip |
| ticker=ASTS | 37 | 11 | 40.5% | 0.276 | 0.350 | +0.376 [-0.182, 0.886] | 0.392 | 7 57.1% +0.229 / 0 n/a / 30 36.7% +0.286 | tickers 1; top share 100.0% |
| ticker=GLW | 32 | 13 | 31.2% | -0.339 | -0.272 | -0.260 [-0.660, 0.146] | 0.404 | 21 38.1% -0.331 / 0 n/a / 11 18.2% -0.355 | tickers 1; top share 100.0% |
| alert_hour=16 | 34 | 11 | 52.9% | 0.532 | 0.607 | +0.604 [-0.198, 1.502] | 0.411 | 10 60.0% -0.045 / 0 n/a / 24 50.0% +0.772 | tickers 24; top share 11.8%; era sign flip |
| gapped_through_entry=not_gapped | 68 | 11 | 32.4% | -0.450 | -0.384 | -0.305 [-1.085, 0.168] | 0.411 | 39 46.2% -0.658 / 0 n/a / 29 13.8% -0.170 | tickers 32; top share 10.3%; bar-covered 68 |
| exit_reason=other | 461 | 14 | 65.7% | -0.018 | 0.048 | +0.122 [-0.078, 0.523] | 0.439 | 441 66.0% -0.060 / 0 n/a / 20 60.0% +0.905 | tickers 64; top share 8.9%; stop 0.28 ATR, loss at 2% $225, overshoot n/a; outcome-defined (not known at entry); era sign flip |
| alert_hour=08 | 31 | 10 | 38.7% | 0.314 | 0.387 | +0.375 [-0.265, 0.992] | 0.472 | 7 57.1% -0.110 / 0 n/a / 24 33.3% +0.437 | tickers 22; top share 9.7%; era sign flip |
| sector_today=Information Technology | 527 | 19 | 43.8% | -0.165 | -0.096 | -0.142 [-0.410, 0.105] | 0.502 | 291 60.8% -0.148 / 5 20.0% +0.278 / 231 22.9% -0.195 | tickers 31; top share 12.5% |
| weekday=Mon | 149 | 16 | 44.3% | 0.019 | 0.086 | +0.124 [-0.135, 0.388] | 0.596 | 78 55.1% -0.153 / 7 14.3% +0.038 / 64 34.4% +0.226 | tickers 52; top share 6.7%; era sign flip |
| alert_hour=14 | 45 | 12 | 48.9% | -0.258 | -0.185 | -0.225 [-0.798, 0.290] | 0.619 | 22 68.2% -0.232 / 0 n/a / 23 30.4% -0.283 | tickers 29; top share 8.9% |
| holding_bucket=9m\|le_2d | 43 | 14 | 44.2% | -0.252 | -0.182 | -0.172 [-0.592, 0.187] | 0.648 | 20 80.0% +0.065 / 0 n/a / 23 13.0% -0.528 | tickers 29; top share 9.3%; outcome-defined (not known at entry); era sign flip |
| session_bucket=close | 48 | 8 | 37.5% | 0.249 | 0.327 | +0.317 [-0.244, 0.768] | 0.648 | 0 n/a / 0 n/a / 48 37.5% +0.249 | tickers 30; top share 10.4% |
| ticker=ARM | 36 | 14 | 55.6% | 0.048 | 0.114 | +0.140 [-0.268, 0.446] | 0.676 | 20 75.0% +0.056 / 1 0.0% -0.065 / 15 33.3% +0.044 | tickers 1; top share 100.0% |
| session_bucket=open | 247 | 10 | 25.9% | -0.095 | -0.020 | -0.110 [-0.344, 0.188] | 0.717 | 0 n/a / 0 n/a / 247 25.9% -0.095 | tickers 65; top share 6.1% |
| holding_bucket=3m\|le_2d | 135 | 18 | 42.2% | -0.164 | -0.096 | -0.088 [-0.369, 0.144] | 0.733 | 78 56.4% -0.189 / 1 100.0% +1.899 / 56 21.4% -0.166 | tickers 52; top share 7.4%; outcome-defined (not known at entry) |
| regime=bull_quiet | 307 | 8 | 28.7% | 0.050 | 0.127 | +0.217 [-0.227, 0.517] | 0.770 | 0 n/a / 0 n/a / 307 28.7% +0.050 | tickers 66; top share 6.2% |
| strategy_horizon=FVG (bearish)\|4w | 33 | 13 | 48.5% | 0.034 | 0.105 | +0.125 [-0.296, 0.476] | 0.770 | 15 73.3% +0.136 / 1 0.0% -0.065 / 17 29.4% -0.051 | tickers 22; top share 9.1%; era sign flip |
| holding_bucket=2m\|le_2d | 126 | 15 | 46.0% | -0.163 | -0.093 | -0.086 [-0.451, 0.203] | 0.814 | 60 66.7% -0.208 / 0 n/a / 66 27.3% -0.122 | tickers 44; top share 12.7%; outcome-defined (not known at entry) |
| direction=bearish | 320 | 19 | 50.0% | -0.136 | -0.069 | -0.069 [-0.228, 0.199] | 0.845 | 231 57.1% -0.233 / 1 0.0% -0.065 / 88 31.8% +0.118 | tickers 62; top share 8.1%; era sign flip |
| direction=bullish | 747 | 19 | 42.3% | -0.067 | 0.004 | +0.069 [-0.199, 0.228] | 0.845 | 320 63.7% -0.070 / 7 28.6% +0.318 / 420 26.2% -0.071 | tickers 85; top share 5.3% |
| ticker=NBIS | 59 | 17 | 54.2% | -0.031 | 0.036 | +0.060 [-0.272, 0.356] | 0.887 | 35 71.4% +0.055 / 0 n/a / 24 29.2% -0.156 | tickers 1; top share 100.0%; era sign flip |
| holding_bucket=4w\|le_2d | 144 | 17 | 45.8% | -0.055 | 0.017 | +0.038 [-0.135, 0.233] | 0.890 | 66 66.7% -0.038 / 3 0.0% -0.393 / 75 29.3% -0.056 | tickers 42; top share 7.6%; outcome-defined (not known at entry) |
| ticker=IREN | 44 | 11 | 61.4% | -0.006 | 0.061 | +0.085 [-0.392, 0.376] | 0.897 | 28 85.7% +0.161 / 0 n/a / 16 18.8% -0.297 | tickers 1; top share 100.0%; era sign flip |
| alert_hour=11 | 118 | 16 | 39.0% | -0.006 | 0.067 | +0.048 [-0.193, 0.283] | 0.903 | 41 65.8% -0.069 / 0 n/a / 77 24.7% +0.028 | tickers 49; top share 9.3%; era sign flip |
| open_gap_bucket=flat | 59 | 15 | 39.0% | -0.109 | -0.039 | -0.062 [-0.395, 0.282] | 0.903 | 23 65.2% -0.053 / 1 0.0% -0.051 / 35 22.9% -0.147 | tickers 34; top share 11.9%; bar-covered 59; fill-defined (not known at entry) |
| friday_entry=no | 829 | 19 | 45.1% | -0.100 | -0.030 | -0.056 [-0.362, 0.191] | 0.903 | 427 61.6% -0.151 / 8 25.0% +0.270 / 394 27.7% -0.052 | tickers 85; top share 5.9% |
| friday_entry=yes | 238 | 18 | 42.9% | -0.044 | 0.025 | +0.056 [-0.191, 0.362] | 0.903 | 124 58.9% -0.092 / 0 n/a / 114 25.4% +0.008 | tickers 58; top share 7.1%; era sign flip |
| weekday=Fri | 238 | 18 | 42.9% | -0.044 | 0.025 | +0.056 [-0.191, 0.362] | 0.903 | 124 58.9% -0.092 / 0 n/a / 114 25.4% +0.008 | tickers 58; top share 7.1%; era sign flip |
| opex_week=other | 911 | 14 | 47.1% | -0.093 | -0.024 | -0.040 [-0.188, 0.145] | 0.903 | 496 63.7% -0.140 / 0 n/a / 415 27.2% -0.037 | tickers 86; top share 6.7% |
| ticker=SNDK | 34 | 12 | 38.2% | -0.027 | 0.040 | +0.062 [-0.249, 0.394] | 0.908 | 18 44.4% -0.188 / 0 n/a / 16 31.2% +0.154 | tickers 1; top share 100.0%; era sign flip |
| weekday=Thu | 256 | 17 | 46.9% | -0.057 | 0.012 | +0.040 [-0.220, 0.235] | 0.918 | 120 67.5% -0.180 / 0 n/a / 136 28.7% +0.051 | tickers 65; top share 6.2%; era sign flip |
| alert_hour=12 | 84 | 13 | 35.7% | -0.073 | 0.002 | -0.030 [-0.276, 0.206] | 0.921 | 22 59.1% -0.224 / 2 50.0% +0.783 / 60 26.7% -0.046 | tickers 49; top share 4.8% |
| atr_pct_bucket=1.5_3 | 36 | 9 | 19.4% | 0.033 | 0.110 | +0.074 [-0.340, 0.621] | 0.932 | 0 n/a / 0 n/a / 36 19.4% +0.033 | tickers 19; top share 16.7% |
| holding_bucket=6m\|le_2d | 59 | 16 | 52.5% | -0.129 | -0.060 | -0.043 [-0.518, 0.322] | 0.941 | 36 66.7% -0.127 / 0 n/a / 23 30.4% -0.131 | tickers 33; top share 8.5%; outcome-defined (not known at entry) |
| alert_hour=09 | 111 | 16 | 31.5% | -0.064 | 0.009 | -0.020 [-0.267, 0.178] | 0.941 | 17 58.8% +0.030 / 1 0.0% -0.051 / 93 26.9% -0.081 | tickers 47; top share 7.2%; era sign flip |
| ticker=MRVL | 45 | 13 | 40.0% | -0.114 | -0.045 | -0.028 [-0.281, 0.418] | 0.948 | 26 50.0% -0.298 / 0 n/a / 19 26.3% +0.138 | tickers 1; top share 100.0%; era sign flip |
| holding_bucket=8m\|le_2d | 61 | 16 | 50.8% | -0.110 | -0.043 | -0.024 [-0.383, 0.262] | 0.963 | 38 71.0% +0.032 / 1 0.0% -1.068 / 22 18.2% -0.310 | tickers 33; top share 6.6%; outcome-defined (not known at entry); era sign flip |
| alert_hour=04 | 36 | 10 | 38.9% | -0.090 | -0.022 | -0.046 [-0.358, 0.455] | 0.965 | 16 56.2% +0.167 / 0 n/a / 20 25.0% -0.295 | tickers 23; top share 8.3%; era sign flip |
| alert_hour=10 | 141 | 16 | 42.5% | -0.041 | 0.029 | +0.006 [-0.180, 0.222] | 0.974 | 54 66.7% -0.027 / 3 33.3% +0.589 / 84 27.4% -0.073 | tickers 48; top share 6.4% |
| alert_hour=13 | 66 | 15 | 40.9% | -0.020 | 0.052 | +0.029 [-0.289, 0.326] | 0.977 | 27 66.7% +0.023 / 1 0.0% -1.063 / 38 23.7% -0.022 | tickers 39; top share 7.6%; era sign flip |
| dollar_volume_bucket=ge_200m | 1028 | 19 | 44.6% | -0.082 | -0.012 | +0.026 [-0.321, 0.996] | 0.977 | 533 60.6% -0.140 / 8 25.0% +0.270 / 487 27.5% -0.023 | tickers 80; top share 6.4%; bar-covered 1028 |
| ticker=STX | 66 | 15 | 48.5% | -0.072 | -0.007 | +0.016 [-0.239, 0.552] | 0.977 | 48 54.2% -0.172 / 0 n/a / 18 33.3% +0.194 | tickers 1; top share 100.0%; era sign flip |
| holding_bucket=5m\|le_2d | 75 | 15 | 50.7% | -0.098 | -0.030 | -0.011 [-0.295, 0.290] | 0.977 | 47 61.7% -0.250 / 0 n/a / 28 32.1% +0.159 | tickers 32; top share 8.0%; outcome-defined (not known at entry); era sign flip |
| holding_bucket=2w\|le_2d | 124 | 15 | 39.5% | -0.097 | -0.023 | -0.011 [-0.378, 0.259] | 0.977 | 40 62.5% -0.150 / 0 n/a / 84 28.6% -0.071 | tickers 39; top share 8.9%; outcome-defined (not known at entry) |
| atr_pct_bucket=3_5 | 99 | 9 | 28.3% | -0.045 | 0.034 | -0.010 [-0.368, 0.482] | 0.977 | 0 n/a / 0 n/a / 99 28.3% -0.045 | tickers 38; top share 6.1% |
| session_bucket=midday | 213 | 9 | 26.3% | -0.038 | 0.040 | +0.001 [-0.230, 0.239] | 0.977 | 0 n/a / 0 n/a / 213 26.3% -0.038 | tickers 72; top share 7.0% |
| near_stop_reversal=reversed_to_target | 35 | 8 | 0.0% | -1.108 | -1.033 | +0.001 [-0.098, 0.134] | 0.979 | 0 n/a / 0 n/a / 35 0.0% -1.108 | tickers 26; top share 11.4%; bar-covered 35; stop 0.33 ATR, loss at 2% $222, overshoot 1.140; outcome-defined (not known at entry) |
| near_stop_reversal=wider_stop_lost | 99 | 8 | 0.0% | -1.109 | -1.034 | -0.001 [-0.134, 0.098] | 0.979 | 0 n/a / 0 n/a / 99 0.0% -1.109 | tickers 42; top share 7.1%; bar-covered 99; stop 0.35 ATR, loss at 2% $222, overshoot 1.113; outcome-defined (not known at entry) |
| atr_pct_bucket=ge_5 | 371 | 10 | 27.8% | -0.041 | 0.035 | -0.017 [-0.470, 0.349] | 0.990 | 0 n/a / 0 n/a / 371 27.8% -0.041 | tickers 46; top share 8.1% |
| ticker=WDC | 51 | 12 | 54.9% | -0.094 | -0.026 | -0.007 [-0.548, 0.315] | 0.990 | 33 72.7% +0.011 / 0 n/a / 18 22.2% -0.288 | tickers 1; top share 100.0%; era sign flip |

Thin cells (tested and counted in BH, never evidence): alert_hour 5, dollar_volume_bucket 2, earnings_proximity 3, exit_reason 3, fomc_proximity 1, gapped_through_entry 1, holding_bucket 17, near_tp_close 1, opex_week 1, regime 2, sector_today 6, strategy_horizon 219, ticker 77, weekday 2

## Give-back (mfe_r minus gross R, every trade)

- N 1011; mean 1.825; median 1.420

## Tallies

- alert-hour coverage (plans): live 579, discord 334, unknown 64
- fill_status=filled: 1145 (bar_covered 1118, of_plans 1212)
- fill_status=expired_unfilled: 1 (bar_covered 1, of_plans 1212)
- fill_status=never_touched: 0 (bar_covered 0, of_plans 1212)
- fill_status=risk_cap: 53 (bar_covered 53, of_plans 1212)
- fill_status=invalidated: 13 (bar_covered 12, of_plans 1212)
- fill_status=open: 0 (bar_covered 0, of_plans 1212)
- fill_status=unknown: 0 (bar_covered 0, of_plans 1212)
- alerts_per_day=1: 6 (plans 6)
- alerts_per_day=2_3: 8 (plans 21)
- alerts_per_day=4_6: 17 (plans 84)
- alerts_per_day=7_plus: 49 (plans 866)
- alert_hour_session=premarket: 151
- alert_hour_session=regular: 715
- alert_hour_session=after_close: 47
- alert_hour_session=unknown: 64
- actionable_before_open=yes: 198
- actionable_before_open=no: 715
- actionable_before_open=unknown: 64
- rejection_reason=rebuild:no_scenario: 280 (days 8)

