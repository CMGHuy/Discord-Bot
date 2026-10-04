# v123 Task 0: Baseline Runner Headroom Instrument

## Specification

**Frozen Stop Rule (from spec v123):**
```
"NO_HEADROOM" when mean capture >= 0.75
"HEADROOM" otherwise
```

## Definitions

**MFE (Maximum Favorable Excursion) R:**
- Window: `[TP1 bar, exit bar)` (closes from bar after TP1 touched through exit bar exclusive)
- Formula: Best close within MFE window minus entry price, divided by risk
- Capped below by realised runner R

**Capture Ratio:**
- Formula: `runner_r / mfe_r` (only for trades with MFE > 0)
- Interpretation: Fraction of maximum available runner potential that was actually realized

## Instrument Configuration

**Time Window (TRAIN):**
- Start: 2020-01-01
- End: 2023-12-31

**Universe:** Full cached universe (all tickers)

**Horizons:** All ten horizons (from `swingbot.core.backtesting.arms.windows.ALL_HORIZONS`)

**Engines:**
- StrategyEngine.iter_trades (strategy-generated plans from backtesting)
- replay_scenarios (sentiment/regime-based replay scenarios)

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

The `stop_rule()` function:
```python
mean = summary["pooled"]["mean_capture"]
return "NO_HEADROOM" if mean is not None and mean >= 0.75 else "HEADROOM"
```

**NO_HEADROOM verdict:** Runner leg captured >= 75% of available MFE, indicating limited headroom for improvement.

**HEADROOM verdict:** Runner leg captured < 75% of available MFE, indicating potential for optimization.

## Status

**Task V123-0:** Baseline read-only instrument created. No changes to `swingbot/` files.

**Next:** Dispatch backtest-runner to execute full TRAIN replay and record results.
