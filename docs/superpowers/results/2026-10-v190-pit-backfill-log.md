# v190 PIT store: backfill log

**Spec:** [v190 PIT Alpaca universe](../specs/2026-10-24-v190-pit-alpaca-universe-design.md)
**Plan:** [v190 data and release tasks](../plans/2026-10-24-v190-pit-alpaca-universe_4-rebaseline-data-and-release.md)

Task V190-18 is incomplete. This preliminary log records the takeover baseline only. Configuration-loading scripts and fetches await explicit authorization; none has been started by the takeover worker.

Paths for the remaining operation:

- Worktree: `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v190-pit-alpaca-universe`
- PIT store: `E:/Documents/Private/Projects/Discord-Bot/data/market_data_pit`
- Extended identity references: `E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext`

## Backfill as found

The takeover brief reports that Windows CIM and WSL `pgrep` checks found no running fetcher on 2026-10-27 at approximately 07:36 UTC. No running command line was available to copy. The original fetch start, end and summary are unknown; they must not be inferred from a manifest timestamp.

The brief's prescribed process checks are `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*fetch_alpaca_history*' } | Select-Object ProcessId, CreationDate, CommandLine | Format-List` and `wsl -e pgrep -af fetch_alpaca_history`. Their earlier raw output and exact check start/end times were not included in the brief. Repeat these checks immediately before any fetch; never start a second fetcher while one runs.

Source-only preflight verified `fetch_alpaca_history.py` accepts `--universe sp500_pit`, `--root`, `--backtest-dir`, `--timeframes`, `--tickers` and `--force`; a universe run disables the market-data identity fallback. `store_io.is_complete(entry, start)`, `universe.universe_symbols(name)` and `data_store.safe_symbol(ticker)` exist. No imports were executed for that verification.

## Measured after the backfill

Measured 2026-10-31 ~17:00Z with the plan's Step 3 script (`store_io.is_complete(entry, "2016-01-01")`), 848 `sp500_pit` members:

| Timeframe | Manifest hash | Updated (UTC) | Status counts | Absent | Incomplete |
| --- | --- | --- | --- | --- | --- |
| daily | 6c0b8186572676ebd62593619a3b3360defade9b284eafccf78367a126b9a2b3 | 2026-10-27T20:20:34Z | ok 568, flagged no-reference 180, flagged price-mismatch 55, flagged short-overlap 1, skipped no Alpaca bars 44 | 0 | 0 |
| hourly | 349e66117d828377bbff6a8768fc9ab2a3c0a7b1d50aa82b0b9906cd27421d11 | 2026-10-30T09:22:04Z | ok 568, flagged no-reference 180, flagged price-mismatch 55, skipped no Alpaca bars 45 | 0 | 0 |
| 15min | 8f1c00b62cd7994a2bfc6ac4637ba38e51cfdb910cdae4eed85252bf6d7f07bf | final r8 manifest | ok 568, flagged no-reference 180, flagged price-mismatch 55, skipped no Alpaca bars 45 | 0 | 0 |

Before the 15min takeover (2026-10-31 ~12:27Z) the 15min manifest held 434 of 848 members (414 absent).

## Fallback identities re-fetched

Measured with the Step 4 script: **0** daily entries have a non-`flagged: no-reference` identity without a `backtest_cache_ext` reference. No fallback repair fetch was needed or run.

## Passes

Daily and hourly completed before this takeover (attempts r1-r5 of the hourly pass were refused by the US-session guard on 2026-10-29 and the watchdog stopped at its restart cap; the manifests above show them complete).

| Timeframe | Command | UTC start | UTC end | Summary line | Exit |
| --- | --- | --- | --- | --- | --- |
| 15min (r6) | `fetch_alpaca_history.py --universe sp500_pit --root $PIT --backtest-dir $EXT --timeframes 15min` | 2026-10-31T09:23:08Z | ~09:23Z | none logged (log holds only the exit line) | 1 |
| 15min (r7) | same, no `--tickers` | 2026-10-31T12:28Z | 2026-10-31T13:13:00Z | none: stopped by the operator at ~103 re-written files; it was re-fetching existing members instead of the missing ones | 127 (kill) |
| 15min (r8) | same plus `--tickers <the 414 members absent from the manifest>` | 2026-10-31T13:13Z | 2026-10-31T16:59:10Z | `written 391, unchanged 0, refetched 0, skipped 23, flagged 112, requests 4554` | 0 |

r7 re-wrote about 100 existing 15min files (BK..HAR) before it was stopped; they are complete members and were not repaired separately.

## Final state

All three timeframes: `absent 0`, `incomplete 0` (table above). Total PIT store size 3.7G; free space on the E: volume 112G (63% used).

Members with `skipped: no Alpaca bars` (V190-20's input), 44 in daily:
`ACS ANRZQ AYE BDK BJS BMC BNI BTUUQ CBE CEPH CFN CMCSK COV CPWR CVH EKDKQ FDO GR HCBK HNZ HSH HSP KRFT LO MEE MFE MHS MOLX MWV NOVL NYX PBG PETM PGN PTV RSHCQ RX SIAL SUNEQ SWY TEG TIE TLAB XTO`

Hourly and 15min carry the same 44 plus `SBNY` (45).
