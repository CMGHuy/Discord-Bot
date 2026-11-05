# Book autopsy, 2026-09-03 to 2026-10-21

- Window (first and last exit date): 2026-09-03 to 2026-10-21
- N closed trades: 218; bar-covered: 210
- Pooled net ExpR (modelled): 0.069; pooled win rate: 31.6%
- Net of frictions: modelled
- Cells tested: 244 (one BH pass over all of them); bootstrap resamples 10000, seed 42
- Effective frictions: {"commission_per_trade": 1.0, "commission_risk_basis": 100.0, "min_risk_fraction": 0.001, "slippage_bps": 5.0}
- Input SHA-256 manifest: 6432de3a0a38d9126aec4ebc0d6090b6bbfbfa6ba089e82c949fe9a0a7004172 (64 files; file hashes in JSON)
- Sector map snapshot SHA-256: ca44693ff1c50c8946a6e2cfffd3c728c87975d4ac9fefc5f32d4ae5c8ed5214 (65 tickers, 17 unknown; mapping in JSON)
- Invocation: 'C:\Users\HuyCao\AppData\Local\Programs\Python\Python311\python.exe' 'E:\Documents\Private\Projects\Discord-Bot\.claude\worktrees\2026-10-24-v192-gap-toward-stop-reclaim\scripts\reports\book_autopsy.py' E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/rows_era.csv E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/rejections_cut.csv --bars-dir E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/bars --out-dir E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/docs/superpowers/results/v192/autopsy-market/control-all-types/sep-era --date 2026-10-21
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
| exit_reason=stop | 101 | 8 | 0.0% | -1.138 | -1.064 | -2.250 [-2.562, -1.982] | 0.001 | tickers 46; top share 7.9%; stop 0.37 ATR, loss at 2% $228, overshoot 0.929 |
| exit_reason=runner_be | 30 | 8 | 100.0% | 1.624 | 1.699 | +1.803 [1.481, 2.270] | 0.001 | tickers 22; top share 10.0%; stop 0.39 ATR, loss at 2% $n/a, overshoot n/a |
| weekend_hold=no | 190 | 8 | 27.4% | -0.144 | -0.068 | -1.660 [-2.152, -1.178] | 0.001 | tickers 58; top share 6.8% |
| gap_through_stop=at_stop | 94 | 8 | 0.0% | -1.074 | -1.000 | +0.921 [0.068, 1.580] | 0.001 | tickers 43; top share 7.4%; stop 0.38 ATR, loss at 2% $215, overshoot n/a |
| fomc_proximity=no_fomc | 213 | 8 | 31.5% | 0.050 | 0.126 | -0.821 [-0.980, -0.695] | 0.001 | tickers 59; top share 6.6% |
| open_gap_bucket=favourable | 86 | 8 | 22.1% | -0.298 | -0.223 | -0.699 [-1.294, -0.369] | 0.001 | tickers 42; top share 7.0%; bar-covered 86 |
| exit_reason=scratch | 38 | 8 | 0.0% | -0.086 | -0.015 | -0.188 [-0.419, -0.054] | 0.009 | tickers 30; top share 7.9%; stop 0.42 ATR, loss at 2% $17, overshoot n/a |
| open_gap_bucket=adverse_large | 82 | 8 | 40.2% | 0.316 | 0.392 | +0.347 [0.011, 0.865] | 0.065 | tickers 39; top share 7.3%; bar-covered 82 |
| friday_entry=no | 177 | 8 | 31.6% | 0.011 | 0.086 | -0.312 [-1.258, 0.302] | 0.508 | tickers 59; top share 7.3% |
| sector_today=Information Technology | 88 | 8 | 30.7% | 0.046 | 0.121 | -0.230 [-0.783, 0.457] | 0.582 | tickers 23; top share 12.5% |
| alert_hour=20 | 202 | 8 | 32.7% | 0.102 | 0.178 | +0.448 [-0.471, 2.342] | 0.657 | tickers 54; top share 6.9% |
| direction=bullish | 189 | 8 | 31.8% | 0.072 | 0.148 | +0.022 [-0.467, 0.720] | 0.929 | tickers 59; top share 5.8% |
| dollar_volume_bucket=ge_200m | 210 | 8 | 31.9% | 0.083 | 0.158 | n/a n/a | n/a | tickers 56; top share 6.7%; bar-covered 210 |
| near_tp_close=other_exit | 218 | 8 | 31.6% | 0.069 | 0.145 | n/a n/a | n/a | tickers 59; top share 6.4% |

Thin cells (tested and counted in BH, never evidence): alert_hour 7, atr_pct_bucket 3, direction 1, earnings_proximity 3, exit_reason 3, fomc_proximity 1, friday_entry 1, gap_through_stop 1, gapped_through_entry 2, holding_bucket 25, near_stop_reversal 2, open_gap_bucket 2, opex_week 2, regime 1, sector_today 7, session_bucket 3, strategy_horizon 103, ticker 59, weekday 6, weekend_hold 1

## Give-back (mfe_r minus gross R, every trade)

- N 216; mean 1.821; median 1.505

## Tallies

- fill_status=filled: 219 (bar_covered 211, of_plans 280)
- fill_status=expired_unfilled: 1 (bar_covered 1, of_plans 280)
- fill_status=never_touched: 0 (bar_covered 0, of_plans 280)
- fill_status=risk_cap: 49 (bar_covered 49, of_plans 280)
- fill_status=invalidated: 11 (bar_covered 11, of_plans 280)
- fill_status=open: 0 (bar_covered 0, of_plans 280)
- fill_status=unknown: 0 (bar_covered 0, of_plans 280)
- alerts_per_day=1: 6 (plans 6)
- alerts_per_day=2_3: 6 (plans 16)
- alerts_per_day=4_6: 9 (plans 44)
- alerts_per_day=7_plus: 14 (plans 214)
- alert_hour_session=premarket: 25
- alert_hour_session=regular: 50
- alert_hour_session=after_close: 205
- alert_hour_session=unknown: 0
- actionable_before_open=yes: 230
- actionable_before_open=no: 50
- actionable_before_open=unknown: 0

