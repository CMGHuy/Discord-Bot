# MA Ribbon rescue gate — TRAIN grid (Task 102)

## Rule (pre-registered, quoted verbatim)

From the rescue-phase brief carried into `scripts/tune_strategy.py`'s module
docstring and used unchanged for every rescue strategy in this phase:

> Selection rule (spec section 9): among configs with WR>=80, ExpR>0, N>=30,
> pick max expectancy. If none qualify, the ranking output still shows the
> best candidates so the failure policy (gating directions/horizons) can be
> applied by hand.

Restated with the excluded-share cap that's also part of every rescue task's
acceptance bar in this plan:

> among configs with `win_rate>=80, expectancy_r>0, n_eval>=30,
> excluded_share<=0.5`, pick max expectancy_r

## Setup

- TRAIN window: `2020-01-01` .. `2023-12-31` (via `tune_strategy.py`'s
  `run_config`, which filters `t.entry_date` into this range)
- Universe: 75 of 78 watchlist tickers loaded from `data/backtest_cache/`
  (`CRWV`, `SNDK`, `SPCX` skipped — no cached OHLCV, consistent with every
  other harness run in this plan)
- Horizons: all 10 in `swingbot.core.strategy_types.HORIZONS`, pooled
  together (both directions, `one_at_a_time=True`) — `tune_strategy.py`
  does not break results out per horizon for single-strategy grids
- Grid (Task 102's brief, `PARAM_GRID["MA Ribbon"]` in `scripts/tune_strategy.py`):
  `min_width_pctile in {0.3, 0.4, 0.5} x require_expanding in {True, False}`
  (6 points), `ext_pct` held fixed at its current baseline (`8.0`) for every
  combo — only the new Task 101 gate params are under test
- Command: `python scripts/tune_strategy.py --strategy "MA Ribbon"`

## Results (full grid, all 6 points)

| min_width_pctile | require_expanding | N | WR% | ExpR | Excl% | Qualifies? |
|---|---|---|---|---|---|---|
| 0.3 | True  | 6  | 100.0 | +0.191 | 45% | no — N<30 |
| 0.3 | False | 34 | 79.4  | +0.050 | 31% | no — WR<80 |
| 0.4 | True  | 0  | n/a   | +0.000 | 100% | no — N=0 |
| 0.4 | False | 16 | 75.0  | +0.009 | 27% | no — N<30, WR<80 |
| 0.5 | True  | 0  | n/a   | +0.000 | 100% | no — N=0 |
| 0.5 | False | 15 | 80.0  | +0.060 | 25% | no — N<30 |

(Console output archived verbatim: `scripts/tune_strategy.py --strategy "MA
Ribbon"` run against the cached OHLCV; see the tool-run transcript for this
task.)

**0/6 configs qualify** under the pre-registered rule
(`win_rate>=80, expectancy_r>0, n_eval>=30, excluded_share<=0.5`).

## Honest verdict: REJECTED-ON-TRAIN

Every grid point fails on at least one gate, and the pattern is a direct
trade-off between sample size and the other two metrics:

- `require_expanding=True` (either width threshold) throws away almost every
  trade — `min_width_pctile=0.3` keeps only 6 (WR=100%, but N is nowhere
  near the 30-trade floor and 45% of what's left is scratches/timeouts);
  `0.4` and `0.5` combined with the expansion requirement keep **zero**
  trades at all (`excluded_share=100%` because every remaining bar is
  excluded, not because trades lost).
- `require_expanding=False` at any width threshold keeps more trades (15-34)
  but none reaches both `WR>=80` and `N>=30` simultaneously: the closest,
  `min_width_pctile=0.5, require_expanding=False` (N=15, WR=80.0,
  ExpR=+0.060), clears the win-rate bar exactly but fails the N>=30 floor by
  half; `min_width_pctile=0.3, require_expanding=False` (N=34) clears N but
  falls short on win rate (79.4 < 80).

The gate as specified narrows the strategy toward higher-conviction setups
(win rate trends up as the width/expansion filters tighten) but at a cost to
sample size that's steeper than the win-rate gain — there is no point on
this 6-point grid where both move favorably at once relative to the
pre-registered floor. This is not a borderline call: the best-by-ExpR
qualifying candidate is zero, so there is nothing to rank.

Per the plan's fallback for a no-winner outcome, **`DEFAULT_PARAMS["MA
Ribbon"]` is left untouched** (`ext_pct=8.0`, `min_width_pctile=None`,
`require_expanding=False` — gate off, as shipped in Task 101). MA Ribbon
does not get a validation-window look under this rescue (Task 103's
permanent-WEAK path applies) — spending that one look on a gate that
doesn't even clear TRAIN would violate the plan's "one look, no retuning"
discipline for no informational gain.
