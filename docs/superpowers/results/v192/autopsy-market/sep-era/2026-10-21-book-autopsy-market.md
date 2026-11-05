# Book autopsy, 2026-09-03 to 2026-10-21

- Window (first and last exit date): 2026-09-03 to 2026-10-21
- N closed trades: 202; bar-covered: 195
- Pooled net ExpR (modelled): 0.102; pooled win rate: 32.7%
- Net of frictions: modelled
- Cells tested: 222 (one BH pass over all of them); bootstrap resamples 10000, seed 42
- Effective frictions: {"commission_per_trade": 1.0, "commission_risk_basis": 100.0, "min_risk_fraction": 0.001, "slippage_bps": 5.0}
- Input SHA-256 manifest: 71817252d21c6ec4347a61b5bf95bef64698793ada245710a18ce4d7b76dcdf9 (53 files; file hashes in JSON)
- Sector map snapshot SHA-256: 64dd4398668303b3698577f4496424e7dbdb538d3ddcb200620dff42d1b2371d (54 tickers, 15 unknown; mapping in JSON)
- Invocation: 'C:\Users\HuyCao\AppData\Local\Programs\Python\Python311\python.exe' 'E:\Documents\Private\Projects\Discord-Bot\.claude\worktrees\2026-10-24-v192-gap-toward-stop-reclaim\scripts\reports\book_autopsy.py' E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/rows_era.csv E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/rejections_cut.csv --bars-dir E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/logs/v192/autopsy/bars --out-dir E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim/docs/superpowers/results/v192/autopsy-market/sep-era --date 2026-10-21 --entry-type market
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
| exit_reason=stop | 94 | 8 | 0.0% | -1.143 | -1.069 | -2.329 [-2.782, -2.053] | 0.001 | tickers 43; top share 8.5%; stop 0.37 ATR, loss at 2% $229, overshoot 0.929 |
| weekend_hold=no | 175 | 8 | 28.6% | -0.087 | -0.011 | -1.418 [-2.102, -0.722] | 0.001 | tickers 53; top share 7.4% |
| fomc_proximity=no_fomc | 197 | 8 | 32.5% | 0.083 | 0.159 | -0.789 [-0.968, -0.565] | 0.001 | tickers 54; top share 7.1% |
| open_gap_bucket=favourable | 75 | 8 | 22.7% | -0.281 | -0.206 | -0.704 [-1.215, -0.387] | 0.001 | tickers 39; top share 8.0%; bar-covered 75 |
| open_gap_bucket=adverse_large | 80 | 8 | 41.2% | 0.339 | 0.416 | +0.332 [-0.042, 0.866] | 0.126 | tickers 37; top share 7.5%; bar-covered 80 |
| sector_today=Information Technology | 83 | 8 | 32.5% | 0.116 | 0.191 | -0.315 [-0.839, 0.247] | 0.349 | tickers 21; top share 13.2% |
| friday_entry=no | 161 | 8 | 32.9% | 0.046 | 0.122 | -0.277 [-1.071, 0.273] | 0.499 | tickers 53; top share 8.1% |
| direction=bullish | 181 | 8 | 32.6% | 0.108 | 0.185 | +0.061 [-0.567, 0.548] | 0.821 | tickers 54; top share 6.1% |
| alert_hour=20 | 202 | 8 | 32.7% | 0.102 | 0.178 | n/a n/a | n/a | tickers 54; top share 6.9% |
| dollar_volume_bucket=ge_200m | 195 | 8 | 33.3% | 0.125 | 0.201 | n/a n/a | n/a | tickers 51; top share 7.2%; bar-covered 195 |
| near_tp_close=other_exit | 202 | 8 | 32.7% | 0.102 | 0.178 | n/a n/a | n/a | tickers 54; top share 6.9% |

Thin cells (tested and counted in BH, never evidence): atr_pct_bucket 3, direction 1, earnings_proximity 3, exit_reason 4, fomc_proximity 1, friday_entry 1, gap_through_stop 2, holding_bucket 23, near_stop_reversal 2, open_gap_bucket 2, opex_week 2, regime 1, sector_today 7, session_bucket 3, strategy_horizon 99, ticker 54, weekday 6, weekend_hold 1

## Give-back (mfe_r minus gross R, every trade)

- N 200; mean 1.819; median 1.446

## Tallies

- fill_status=filled: 203 (bar_covered 196, of_plans 203)
- fill_status=expired_unfilled: 0 (bar_covered 0, of_plans 203)
- fill_status=never_touched: 0 (bar_covered 0, of_plans 203)
- fill_status=risk_cap: 0 (bar_covered 0, of_plans 203)
- fill_status=invalidated: 0 (bar_covered 0, of_plans 203)
- fill_status=open: 0 (bar_covered 0, of_plans 203)
- fill_status=unknown: 0 (bar_covered 0, of_plans 203)
- alerts_per_day=1: 6 (plans 6)
- alerts_per_day=2_3: 6 (plans 15)
- alerts_per_day=4_6: 7 (plans 32)
- alerts_per_day=7_plus: 13 (plans 150)
- alert_hour_session=premarket: 0
- alert_hour_session=regular: 0
- alert_hour_session=after_close: 203
- alert_hour_session=unknown: 0
- actionable_before_open=yes: 203
- actionable_before_open=no: 0
- actionable_before_open=unknown: 0

