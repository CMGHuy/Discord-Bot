# EMA Crossover rescue gate — TRAIN grid (Task 108)

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
  together (both directions, `one_at_a_time=True`)
- Economics: `--exit-model v2 --scale-out` on every invocation, per this
  rescue's critical methodology lesson (TRAIN grid selection must match
  the economics VALIDATION will use — see
  `docs/superpowers/results/2026-07-rescue-ribbon-train.md`'s correction
  note for the full history of that bug).
- Grid (Task 107/108's new gate, `PARAM_GRID["EMA Crossover"]` in
  `scripts/tune_strategy.py`): `entry_mode="pullback" x
  pullback_max_bars in {5, 10, 15}` (3 points). `rsi_dip`/`ext_atr` stay
  fixed at baseline (`45`/`1.0`) for every combo — only the new pullback
  gate is under test.
  - Task 108's literal wording asks for `entry_mode=[cross, pullback] x
    pullback_max_bars=[5,10,15]`, a 6-point cartesian grid. Since
    `entry_mode="cross"` never reads `pullback_max_bars`, that literal
    product wastes 3 rows repeating one identical baseline. Instead, the
    grid here holds `entry_mode` fixed at `"pullback"` (3 points, one per
    `pullback_max_bars`) and the `"cross"` baseline is computed once,
    separately, as the comparison point below.
- Commands:
  - Pullback grid: `python scripts/tune_strategy.py --strategy "EMA Crossover" --exit-model v2 --scale-out`
  - Cross baseline (single point, current/pre-rescue behavior):
    `python scripts/tune_strategy.py --strategy "EMA Crossover" --exit-model v2 --scale-out --grid entry_mode=cross`

## Results

| entry_mode | pullback_max_bars | N | WR% | ExpR | Excl% | Qualifies? |
|---|---|---|---|---|---|---|
| cross (baseline) | n/a | 110 | 68.2 | -0.059 | 27% | no — WR<80, ExpR<0 |
| pullback | 5  | 54 | 90.7 | +0.192 | 17% | **yes** |
| pullback | 10 | 63 | 90.5 | +0.187 | 17% | **yes** |
| pullback | 15 | 68 | 91.2 | +0.197 | 17% | **yes** |

(Console output archived verbatim from the two `tune_strategy.py` runs
above, run against the cached OHLCV.)

**3/3 pullback configs qualify** under the pre-registered rule
(`win_rate>=80, expectancy_r>0, n_eval>=30, excluded_share<=0.5`). The
`cross` baseline does not qualify (WR=68.2 < 80, ExpR=-0.059 < 0), matching
round 1's finding that EMA Crossover fails at 76.9% WR out-of-sample (the
in-sample TRAIN number differs somewhat from round 1's OOS figure, as
expected, but the qualitative verdict — cross-mode entries do not clear the
80% bar — is the same).

## Honest verdict: PASSED-ON-TRAIN

Unlike every other rescue attempt in this phase (RSI Divergence, MA Ribbon,
Elliott Wave all failed or only partially cleared TRAIN), the pullback
entry-mode redesign is a clean, unambiguous win here: **all three grid
points qualify**, and win rate (90.5–91.2%) plus expectancy (+0.187 to
+0.197) both move sharply in the right direction relative to the `cross`
baseline, at a real cost in trade count (110 -> 54-68, since the gate
throws out crosses that never see a genuine pullback within the window)
but nowhere near enough to breach the `N>=30` floor. Sample size actually
*increases* monotonically with the window (`pullback_max_bars=5` -> 54,
`10` -> 63, `15` -> 68) as more crosses get a chance to find their
pullback, while win rate and expectancy stay essentially flat across the
window choice (91.2/90.5/90.7 WR, +0.197/+0.187/+0.192 ExpR) — the gate's
benefit comes from filtering *which* crosses get taken (only those that
pull back to the fast EMA first), not from the window length itself.

Per the pre-registered rule, **max expectancy_r among qualifying configs**
selects `pullback_max_bars=15` (ExpR=+0.197, N=68, WR=91.2%) — narrowly
ahead of `pullback_max_bars=5` (+0.192) and `pullback_max_bars=10`
(+0.187), and also the config with the most trades, so there's no
sample-size trade-off working against this pick either.

**`DEFAULT_PARAMS["EMA Crossover"]` is updated** (`swingbot/core/entry_filters.py`)
to `entry_mode="pullback", pullback_max_bars=15` (with `rsi_dip=45,
ext_atr=1.0` unchanged) — this is now the default, backward-compat-breaking
change for this strategy; `entry_mode="cross"` must be requested explicitly
to get the old behavior (see `tests/test_rescue_ema.py`'s `CROSS` constant).

Per this rescue phase's spec, a config that clears TRAIN earns the single
VALIDATION-window look — Task 109 spends it against this exact
`pullback_max_bars=15` config, no retuning after seeing the result.
