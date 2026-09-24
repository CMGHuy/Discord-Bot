# v102 — extended 2010-2025 cache fetch and v101 equivalence check

**Plan:** `docs/superpowers/plans/2026-09-24-v102-fib-sr-confluence-extended-history.md`, Task V102-4
**Run date:** 2026-09-24

## Step 1: Fetch

```
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/fetch_backtest_data.py --start 2010-01-01 --end 2025-12-31
```

`Done: 75 fetched, 0 already cached, 3 failed ['CRWV', 'SNDK', 'SPCX']` (~1.5 min).

The plan's expected failure set was `CRWV, SNDK, SPCX, GC=F, SI=F`; `GC=F` and `SI=F` both succeeded this run (4023 and 4022 bars respectively) — that expectation was stale, not a defect in this fetch. `CRWV`/`SNDK`/`SPCX` are confirmed absent from the shared `data/backtest_cache/` too, so the extended cache's failures are consistent with the shared cache's.

## Step 2: Coverage check

| Check | Result | Required |
|---|---|---|
| `missing_in_ext` | `[]` | must be empty |
| `extra_in_ext` | `[]` | — |
| `tickers_with_2010_data` | 48 of 75 | — |
| `SPY_first` | 2010-01-04 | at or before 2010-01-05 |

No `--force` re-fetch was needed.

## Step 3: Equivalence check against v101 (data sanity, not a hypothesis test — no budget spent)

Baseline: `docs/superpowers/results/2026-09-24-v101-fib-diagnostic.md`, current arithmetic (post-`a3a903d6` 2% stop cap).

| Direction | Metric | v101 baseline | ext-cache result | Δ | Tolerance | Verdict |
|---|---|---|---|---|---|---|
| Bullish | N | 288 | 289 | +0.35% | ±5% | PASS |
| Bullish | WR | 28.8% | 28.4% | -0.4pp | ±1.5pp | PASS |
| Bullish | ExpR | +0.039 | +0.009 | -0.030 | ±0.03 | PASS (at the boundary) |
| Bearish | N | 94 | 93 | -1.06% | ±5% | PASS |
| Bearish | WR | 25.5% | 24.7% | -0.8pp | ±1.5pp | PASS |
| Bearish | ExpR | -0.091 | -0.105 | -0.014 | ±0.03 | PASS |

Bearish clears comfortably. Bullish ExpR drift (+0.039 → +0.009) sits exactly on the ±0.03 tolerance edge (|Δ| = 0.030). Recorded as a pass, not a comfortable one — the extended cache's deeper warm-up and re-based adjusted prices are the expected sources of drift per the plan; nothing here points to a ticker-history or universe-filter discrepancy, but this is the metric to re-check first if a later stage's numbers look inconsistent with v101's diagnostic.

**Shared cache integrity confirmed:** `data/backtest_cache/` file count unchanged at 75 before and after this task; every command explicitly set `BACKTEST_CACHE_DIR=data/backtest_cache_ext`.

## Verdict

**PASS**, both directions, within tolerance. Proceeding to V102-5 (Stage 0 signal counts).
