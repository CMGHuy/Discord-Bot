# v131 reference reproduction against v103 -- why it does not match

Written before any v131 cell result was opened. Inputs: `2026-10-08-v131-reproduction.json`,
`data/v103_collect_A.json` (`rows_by_cell["0"]`, bullish), the reference arm's rows in
`data/v131_collect_*.json` (reference rows only, no cell rows), and the committed
`2026-10-06-v124-reproduction-note.md`.

## 1. The numbers (bullish, TRAIN slice 2010-01-01..2023-12-31, decided trades = win + loss)

| | N | WR | ExpR | universe |
|---|---|---|---|---|
| v103 reference (expected) | 815 | 36.81% | +0.2219 | 73 |
| v131 reference arm, today's code (got) | 880 | 37.16% | +0.2483 | 74 |

`matches` is false. Checked: the stored v103 bullish rows, run through the same pooled-stats
function, give exactly 815 / 36.81 / +0.2219, so the expected figure is faithful to the stored rows.
Raw rows (all outcomes): v103 1093, today 1116 (outcomes today: loss 553, win 327, scratch 224,
timeout 12; v103: loss 515, win 300, scratch 229, timeout 49).

## 2. Universe difference

`data/v103_collect_A.json` is on disk, so the comparison is per ticker on traded rows.
- Tickers traded by v103's bullish reference: 62. Tickers traded by today's: 62. The sets are identical;
  no ticker is only in one side.
- Universe size 73 vs 74 therefore adds no trades to the reference arm. (The v124 note names the
  extra universe member as SNDK, listed 2025, which has no TRAIN-window trades; I did not re-derive
  which name it is -- `data/watchlist.json` is gitignored, so git history cannot show it.)
- Per-ticker raw trade counts differ for 16 tickers (v103 -> today): AMD 20->21, AMZN 47->51,
  BKNG 21->23, GD 26->27, HD 28->29, ILMN 26->27, INTC 30->31, META 16->17, MSFT 35->36,
  MSTR 28->30, ORCL 24->25, PEP 30->31, SBUX 18->20, SNPS 34->35, TSLA 13->15, UNH 22->23
  (sum +23). All other ticker counts are equal; full today counts are in the JSON `by_ticker`.

Trade-level, keyed (ticker, entry_date, horizon): all 1093 v103 entries are present today; 23 entries
exist only today (none only in v103). The 23 extras: 15 loss, 6 scratch, 2 win; horizons 4w x8,
2m x4, 3m x4, 5m x4, 4m x2, 6m x1. Among the 1093 shared entries, 236 have a different outcome
or R (scratch/timeout -> win/loss, changed R on wins, some wins -> scratch/loss). Entry dates
are the same, so the entry signal is unchanged; the stop/target/exit side differs.
(The v124 note counts 256 changed by its own keying; I did not reconcile the 20-row difference.)

## 3. Code changes on the reference arm's path since 56f2f6ba

`git log --oneline 56f2f6ba..HEAD -- swingbot/core/market/entry_filters.py swingbot/core/planning
swingbot/core/backtesting/backtest.py swingbot/core/market/levels.py` lists 64 commits (2026-09-28
to 2026-10-08), grouped:

- v104 `6e080144 stop_scope`, `c2b3ad73 builders read stop_ceiling`, `a356c7f2 level lifecycle widens
  only up to the stop ceiling`, `09ea2796`, `3c6f9f54`/`ad6ba7cf` (dollar-risk sizing), `fd21ecf0`,
  `018ab65b`, `8328a6c6`: **`a356c7f2` can and, per the v124 bisect, does move Fibonacci trades**
  (backtest stops no longer widen past the 2% cap, so stops, risk and re-selected targets change).
  The rest are scoped to strategies in `STRUCTURAL_STOP_SCOPE`, shorts, or earnings caps: not shown
  to touch Fibonacci bullish; uncertain.
- v113 (`d2c2705f`, `5edda83e`, `811724fc`, `0e94b8d8`, `6819ae25`): horizon masking, reward floor on
  1w, limit entry type, per-strategy plan shapes. Floor applies to 1w only (not in the ten horizons
  measured) and Fibonacci keeps the market shape; probably no effect, not independently verified.
- v115 `92bd929d`, `56fab3d0`: clamps a *confluence* stop beyond 2%; confluence only. Probably no effect.
- v111 logging, v119 (compression short), v108 (EMA re-arm), v67/v116 (store plumbing): other
  strategies or non-trading code. No expected effect.
- v123 (`e72b35d5`..`689cb3a5`, `fceed15f`, `dff63adb`): runner structure exit behind a flag plus a
  byte-identical-witness refactor of the exit walk. Flag-gated; no effect expected, not re-verified.
- v125 (`d99f21e2`, `a43a73a2`): entry_context / replay snapshots, metadata. No expected effect.
- v128 `b4b9fc79`, v129 (`1a02c91a`..`55317c33`, `e4901804`): FVG level map; acceptance-exit fields
  and flags, inert by default. No expected effect.
- v137 (`f945962f`, `e007d02d`, `d2595f56`): v2 backtest builds every plan through
  `build_strategy_plan`; `_trade_plan_at` retired. Could move plans; the v124 bisect found no output
  change after `a356c7f2`, so apparently behaviour-preserving for this arm.
- v131 (`92190f31`, `e59b38d9`, `25750e83`, `34982fdc`): limit arm machinery; Fibonacci reference
  keeps the market entry. No effect found (the reference rows match the v124 reproduction exactly).

## 4. Conclusion

Evidence supports this attribution:
1. Universe 73 vs 74: no effect on the reference arm. Same 62 traded tickers; the extra name traded nothing.
2. Code: the N/WR/ExpR gap comes from `a356c7f2` (v104 level-lifecycle stop widening). The v124 note
   bisected this on the full run (parent `6e080144`: 1094 rows, N 815, WR 36.81; `a356c7f2`: 1116 rows,
   N 880, WR 37.16, equal to HEAD). I checked only that today's rows reproduce the v124 figures
   (880 / 37.16 / +0.2483, 1116 raw rows) and the row-level differences above; I did not rerun the bisect.
3. Data: v124 attributes 1 extra scratch and 4 changed rows to the 2026-09-28 cache re-fetch. Not
   re-verified here; none of those changes decided N or WR per v124.

Not fully attributed: the exact split of the 23 extra rows and 236 changed rows between (2) and
(3) is not re-derived here, and the 256-vs-236 difference in changed-row counts is unreconciled.

Stage 1's reference arm is today's code on today's universe (74 names, the spec's "same window and
universe"). No cell is adjusted by this gap, and v103's figures are not used as a target.
