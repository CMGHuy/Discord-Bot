# Elliott Wave rescue gate — TRAIN grid (Task 105)

## Rule (pre-registered, quoted verbatim)

Per Task 105's brief (this plan's rescue-phase adaptation of the spec
section 9 TRAIN-grid selection rule used identically for every strategy
grid in this plan, e.g. `scripts/tune_strategy.py`'s own docstring):

> Selection rule (pre-registered, same as elsewhere in this plan): among
> configs with `win_rate>=80, expectancy_r>0, n_eval>=30,
> excluded_share<=0.5`, pick max expectancy_r.

Grid (Task 104/105 brief, quoted verbatim): `w2_max_retrace=[0.618, 0.786] x
w2_max_duration_ratio=[0.75, 1.0]` with `w2_min_retrace` FIXED at `0.382`
for every combo (non-None so the gate is "on", not gridded).

## Setup

- TRAIN window: `2020-01-01 .. 2023-12-31` (`scripts/tune_strategy.py`'s
  `TRAIN` constant — never touch the 2024-2025 validation window here)
- Universe: full cached watchlist — 75 tickers (`fetch_backtest_data
  .load_watchlist()` / `load_cached()`, same cache every other harness run
  in this plan uses)
- Horizons: all of `swingbot.core.strategy_types.HORIZONS`, but Elliott
  Wave's own `elliott_wave_entries` only fires on `4w` (returns all-False
  for every other horizon) — this is unchanged, pre-existing strategy
  behavior, not something this grid controls
- Strategy: `Elliott Wave` only (`--strategy "Elliott Wave"`)
- Baseline params held fixed for every combo: `depth_min=0.30,
  depth_max=0.80` (unchanged from round 1 — only the new wave-2 gate is
  under test this run, per the task brief)
- `PARAM_GRID["Elliott Wave"]` in `scripts/tune_strategy.py` was changed
  from the old `{"depth_min": [0.30, 0.38], "depth_max": [0.78, 0.80]}`
  (that grid was never run/adopted for the rescue) to:
  ```python
  {"w2_min_retrace": [0.382],
   "w2_max_retrace": [0.618, 0.786],
   "w2_max_duration_ratio": [0.75, 1.0]}
  ```
  A single-value list for `w2_min_retrace` holds it constant at 0.382
  across the whole `itertools.product` while still turning the gate on
  (`None` would leave the gate permanently off).
- Aggregation math: identical to every other `tune_strategy.py` run —
  `win_rate` over win+loss only, `expectancy_r` over all closed trades
  (win+loss+scratch+timeout), `excluded_share = (scratch+timeout)/closed`,
  restricted to trades whose `entry_date` falls inside the TRAIN window

## Command

```
python scripts/tune_strategy.py --strategy "Elliott Wave"
```

## Results

| w2_min_retrace | w2_max_retrace | w2_max_duration_ratio | N | Win% | ExpR | Excl% | Qualifies |
|---|---|---|---|---|---|---|---|
| 0.382 | 0.618 | 0.75 | 117 | 83.8 | +0.094 | 28% | YES |
| 0.382 | 0.618 | 1.0  | 135 | 82.2 | +0.080 | 27% | YES |
| 0.382 | 0.786 | 0.75 | 180 | 78.9 | +0.048 | 27% | no (WR<80) |
| 0.382 | 0.786 | 1.0  | 212 | 77.4 | +0.032 | 27% | no (WR<80) |

(Full console output above; every config clears `n_eval>=30` and
`excluded_share<=0.5` by a wide margin — the two gates that actually
discriminate here are `win_rate>=80` and, secondarily, `expectancy_r`.)

**2/4 configs qualify.**

## Selection

Applying the pre-registered rule (max `expectancy_r` among qualifying
configs): the winner is

```
w2_min_retrace=0.382, w2_max_retrace=0.618, w2_max_duration_ratio=0.75
-> N=117, WR=83.8%, ExpR=+0.094, excluded_share=28%
```

This beats the runner-up (`w2_max_duration_ratio=1.0`: WR=82.2%,
ExpR=+0.080) on both win rate and expectancy, so there is no tension in
the ranking — the tighter duration cap (wave-2 must complete in <=75% of
wave-1's bar count, not <=100%) is unambiguously the better filter on
TRAIN.

## Verdict: ADOPTED ON TRAIN

The winning config qualifies under the pre-registered gate
(`win_rate>=80, expectancy_r>0, n_eval>=30, excluded_share<=0.5`) with
room to spare (83.8% vs the 80% floor, +0.094R positive expectancy). Per
the task brief, this is encoded as the new permanent default in
`DEFAULT_PARAMS["Elliott Wave"]` (`swingbot/core/entry_filters.py`):

```python
DEFAULT_PARAMS["Elliott Wave"] = {
    "depth_min": 0.30, "depth_max": 0.80,
    "w2_min_retrace": 0.382, "w2_max_retrace": 0.618,
    "w2_max_duration_ratio": 0.75,
}
```

This is a TRAIN-only result — Elliott Wave remains WEAK in the validation
registry until Task 106 spends its single, pre-registered VALIDATION-window
look on this exact config and reports the out-of-sample verdict honestly
(no retuning after that look, win or lose).
