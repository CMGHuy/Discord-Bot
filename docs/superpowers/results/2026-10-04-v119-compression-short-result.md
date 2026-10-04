# v119 result — compression short, broad and isolated arms: unmeasurable (stopped before Stage −1)

Pre-registration: `docs/superpowers/results/2026-10-01-v119-compression-short-preregistration.md`
(committed `5f1d3f6a`, before this check).
Spec: `docs/superpowers/specs/2026-10-01-v119-short-compression-release-design.md`.
Edge: expectancy.

**Outcome: `unmeasurable` for both arms. No evidence was produced and none is
claimed.** No producer run, pilot, MDE, fold or VALIDATION run took place, no arm
JSON exists, and neither arm's VALIDATION shot was spent. The strategy stays
masked (`STRATEGY_GATES[...] == {"directions": ()}`), `COMPRESSION_SHORT_RESEARCH_MODE`
stays `off`.

## The input check (read-only, 2026-10-04, no outcome read)

The pre-registration requires, for every signal date in the pilot window
(2018-06-01..2020-12-31), an earnings snapshot as observed on or before that
date for both arms, and a dated sector mapping plus the sector-ETF frame for
the isolated arm.

| Input | Needed by | Present? | Finding |
|---|---|---|---|
| Cached stock frames | both | yes | `data/backtest_cache`, 75 files |
| Cached SPY | both | yes | `SPY.csv` |
| PIT S&P 500 membership | both | yes | `data/universe/sp500_membership.csv`, sha256 `183a5708…6dc32` |
| **As-of earnings snapshots** | both | **no** | No archive of calendars *as observed* exists. `market_data/earnings/*.csv` holds `report_date,timing,report_ts_et` — final report dates known later, with no observation time. The only `EarningsSnapshot` producer is the live Yahoo query (`events.py`), observed "now". Using final dates for 2018–2020 would hand the replay knowledge of reports not yet scheduled on the signal date. |
| **Dated sector mapping** | isolated | **no** | `data/universe/sp500_sector_history.csv` does not exist (the v118 blocker; `universe.historical_short_snapshot` returns None without it). |
| **Sector-ETF frames** | isolated | **no** | None of XLK, XLF, XLE, XLV, XLI, XLP, XLY, XLU, XLB, XLRE, XLC is in the backtest cache. |

Per the pre-registration ("If any of these is absent for the pilot window the
measurement is recorded `unmeasurable` and stops before MDE; the absence is
never repaired by backfilling present-day facts"), both arms stop here.

What a run would have done had it started: `compression_research.offline_context()`
returns no snapshot for any date, so every mode-admitted candidate is excluded
`earnings_unknown`; the component arm equals its baseline and `measure_arms.py`
refuses `refused:zero-diff`. That refusal would describe the missing input, not
the signal, so the run was not made. (In this session the producer could not
have resolved its universe in any case: `cached_universe()` reads the watchlist
from Postgres, which was unreachable.)

## Instrument state (shipped inert)

- `COMPRESSION_SHORT_RESEARCH_MODE` (`off|broad|isolated`, default `off`,
  research only) — `REACHABLE` via the `strategy` engine, proven on the stamped
  pilot fixture (`tests/backtesting/test_measure_compression_short.py`): the
  broad component adds exactly the compression row and moves no other row;
  `validate_component.py --stage reachability` reads it `REACHABLE`.
- Explicit offline as-of loader (`compression_research.offline_context`) and
  per-mode supplemental diagnostics (`measure_compression_short`). A
  `measure_arms.py` run with the knob writes them beside the arm file as
  `<out-stem>.diagnostics.json` (scored signals with signal/entry/exit dates,
  mode and exit reason; every excluded candidate with its reason; totals by
  reason and by mode; the `daily_close_proxy` label; the break-even borrow fee;
  a cross-check against the arm's own compression rows), including on a
  zero-diff pilot. The stamped `ArmTrade` rows are unchanged.
- The research cell is now the fixed `("bearish", "2w")` cell; before this task it
  followed the replayed horizon and would have opened the short on every legacy
  horizon under a full-horizon run.

## Not a closed negative

Nothing was measured, so the closed-pre-registration table gets no row and both
arms' shots remain unspent. The faithfulness finding stands independently: the
v72 clause 1 / clause 5 / Stage 0 statistic is identically zero for a new
stratum, so the pre-registered amendment (A1–A3) must be implemented before any
MDE or selection run, whatever data arrives.

## To resume

1. Obtain an earnings-calendar source **as observed on each date** for the
   window (with observation timestamps), and, for the isolated arm, a true
   point-in-time sector history plus the sector-ETF frames.
2. Resolve the pre-registration's UNFROZEN items by committed amendment, and
   implement and test the A1–A3 pooled-ΔWR instrument.
3. Run Stage −1 per arm with the pre-registered commands, then the ladder,
   serially, one arm decided independently of the other.
