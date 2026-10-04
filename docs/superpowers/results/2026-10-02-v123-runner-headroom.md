# v123 Task 0: Baseline Runner Headroom Instrument

## Specification

**Frozen Stop Rule (from spec v123):**
> if mean runner capture ≥ 75%, there is no headroom: both arms can only exit at or before today's runner exit (`hl_trail` only ratchets the stop tighter; `progress_stall` only adds an earlier exit), so both close without a shot. The numbers are reported as-is either way; this is baseline description, not selection.

## Definitions

**MFE (Maximum Favorable Excursion) R:**
- Window: closes from the TP1 bar through the bar before the runner exit; floor = realised runner R
- Formula: Best close within MFE window minus entry price, divided by risk

**Capture Ratio:**
- Formula: `runner_r / mfe_r` (only for trades with MFE > 0)
- Interpretation: Fraction of maximum available runner potential that was actually realized

## Instrument Configuration

**Time Window (TRAIN):**
- Start: 2020-01-01
- End: 2023-12-31
- Recorded before outcome is read from CSV

**Universe:** Every ticker with a daily CSV in the local backtest cache (market_data/daily), listed from disk; not watchlist-filtered, because production Postgres is unreachable from the dev machine

**Horizons:** All ten horizons (from `swingbot.core.backtesting.arms.windows.ALL_HORIZONS`)

**Engines:**
- `StrategyEngine.iter_trades` (strategy-generated plans)
- `replay_scenarios` (live plan constructor replayed on TRAIN)

**Exit Simulation:** `scale_out=True` (runner tracking enabled)

## Inclusion Criteria

Only trades with:
1. `outcome == "win"` (reached TP1)
2. Two legs (`len(result.legs) == 2`, indicating runner exit executed)

Non-runner trades (single leg or non-wins) are excluded.

## Metrics Produced

### Per-Trade Row
- `horizon_key`: Horizon identifier (e.g., "2w", "4w")
- `source`: Plan source ("strategy" or "replay")
- `runner_r`: Realized return on runner leg (risk units)
- `mfe_r`: Maximum favorable excursion (risk units)
- `capture`: Realized capture ratio (runner_r / mfe_r)
- `reason`: Exit reason code from runner leg (e.g., "runner_trail")

### Summary Aggregation (by `summarise()`)
- **pooled**: Aggregated across all trades
  - `n`: Total trade count
  - `mean_runner_r`: Average realized runner return
  - `mean_mfe_r`: Average maximum favorable excursion
  - `mean_capture`: Mean of per-trade capture ratios (where mfe_r > 0)
  - `sum_capture`: Pooled capture (sum of all runner_r / sum of all mfe_r)
  - `reasons_pct`: Distribution of exit reasons as percentages
- **per_horizon**: Same metrics grouped by horizon_key

## Stop Rule Logic

The `stop_rule()` function uses `pooled["mean_capture"]` — the per-trade mean over all trades with MFE > 0:
```python
mean = summary["pooled"]["mean_capture"]
return "NO_HEADROOM" if mean is not None and mean >= 0.75 else "HEADROOM"
```

Note: `sum_capture` (pooled: sum of all runner_r / sum of all mfe_r) is reported alongside `mean_capture` but is not the decision rule.

**NO_HEADROOM verdict:** Mean runner capture >= 75%, indicating limited headroom for improvement.

**HEADROOM verdict:** Mean runner capture < 75%, indicating potential for optimization.

## Status

**Task V123-0:** Baseline read-only instrument created. No changes to `swingbot/` files.

**Next:** Dispatch backtest-runner to execute full TRAIN replay and record results.

## Results (appended as-is after the run)

Note: The 2026-09-10 "43%" memory figure is superseded by this re-derivation.
