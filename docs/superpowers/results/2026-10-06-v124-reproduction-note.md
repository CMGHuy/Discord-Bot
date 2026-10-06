# v124 reproduction note — v103 `b=0` bullish baseline does not reproduce on current main

Written before any v124 bucket table was generated or opened. Raw outputs:
`2026-10-06-v124-repro-bullish.json`, `2026-10-06-v124-repro-bullish-codedefaults.json`
(identical rows; one with the developer environment, one with `.env` and inherited
config overrides stripped), `2026-10-06-v124-repro-bearish.json`.

## Observation

| | N (decided) | WR | ExpR | universe |
|---|---|---|---|---|
| v103/v102 reference (bullish `b=0`) | 815 | 36.81% | +0.2219 | 73 |
| v124 reproduction on main | 880 | 37.16% | +0.2483 | 74 |

Against the stored v103 rows (`data/v103_collect_A.json`, local): 23 trades only in the new run,
none only in the old, 256 shared trades with a different outcome or R. Bearish (description only)
also differs: N=161, WR 33.54%, ExpR +0.0600 against 169 / 23.67% / −0.1269; not re-run at the
parent commit.

## Explanation (bisect, committed code plus data)

1. **Config is not the cause.** Pure code defaults and the developer environment give identical
   output. The v103 commit's own harness (`56f2f6ba`, measurement code `c5e2cbc0`) reproduced the
   stored rows exactly on a 7-ticker subset (161/161, one 0.001 R rounding difference).
2. **One code commit explains the drift: `a356c7f2` "fix(v104): level lifecycle widens only up to
   the stop ceiling".** Its parent `6e080144` on the full 77-name run gives 1094 rows, N=815,
   WR 36.81% (matches v103). `a356c7f2` gives 1116 rows, N=880, WR 37.16%, matching HEAD row for row
   (loss 553, win 327, scratch 224, timeout 12). No later commit changes the output.
   Mechanism: `apply_level_lifecycle` used to widen stops past the 2% hard cap in the backtest
   (trades the live fill check cancels); it now widens only to `stop_scope.stop_ceiling`, so stops,
   risk and re-selected targets change and timeouts fall from 49 to 12. `known-traps.md` already
   records that numbers before and after this commit are not comparable.
3. **Cache re-fetch (data, not code).** Every `backtest_cache_ext` CSV was rewritten on 2026-09-28,
   after v103's run. This accounts for 1 new scratch (UNH 4w 2010-12-10) and 4 changed rows (GOOGL,
   WMT, HD, PEP); none changes decided N or WR.
4. **Universe 74 vs 73:** the 74th name is SNDK. `SNDK.csv` and `CRWV.csv` were created 2026-09-28; the
   filter drops CRWV (data quality), SI=F (liquidity) and SPCX (no file). SNDK has no TRAIN_EXT trades
   (listed 2025), so ticker sets and trades are unchanged by it. The "missing on 09-25" conclusion
   rests on Windows file creation times; no older cache copy exists to confirm it.

## Consequence for v124

The reference baseline is no longer reachable: the bullish v103 `b=0` row changed because the
replay's stop-widening rule changed (v104), not because of anything v124 added. The diagnostic
therefore compares buckets within the current instrument (post-`a356c7f2`, cache of 2026-09-28,
universe 74) and is not comparable to v103's absolute figures. The reproduction check stays in the
report as a recorded mismatch with this explanation.
