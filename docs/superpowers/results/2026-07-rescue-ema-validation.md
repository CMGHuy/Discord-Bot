# EMA Crossover rescue gate — VALIDATION (Task 109, single run)

## Rule (pre-registered, quoted verbatim)

Per the plan's Global Constraints (same rule every rescue/VALIDATION run in
this plan uses, e.g. `docs/superpowers/results/2026-07-confluence-validation.md`):

> VALIDATION is run **once per component** (exit model v2, confluence gates,
> each rescue strategy) with pre-registered gates; results reported as-is,
> never retuned after.

> **Acceptance gates:** `win_rate >= 80`, `expectancy_r > 0`, `N >= 15`
> (validation), `scratches+timeouts <= 50%` of closed trades.

The config under test is the one Task 108's TRAIN grid selected and
permanently adopted into `DEFAULT_PARAMS["EMA Crossover"]`
(`swingbot/core/entry_filters.py`), quoted from
`docs/superpowers/results/2026-07-rescue-ema-train.md`:

```
entry_mode=pullback, pullback_max_bars=15 (rsi_dip=45, ext_atr=1.0 unchanged)
-> TRAIN: N=68, WR=91.2%, ExpR=+0.197, excluded_share=17%
```

This VALIDATION run is the single, pre-registered out-of-sample look at
that exact config — no parameter is touched based on this run's result,
win or lose.

## Setup

- VALIDATION window: `2024-01-01 .. 2025-12-31` (run once, per
  `scripts/run_backtest_range.py --validation`)
- Universe: full watchlist — 75 of 78 cached tickers (`CRWV`, `SNDK`,
  `SPCX` have no cached OHLCV and were skipped, same as every other
  harness run in this plan)
- Strategy: `EMA Crossover` only (`--strategy "EMA Crossover"`)
- Exit model: v2 with scale-out (`--exit-model v2 --scale-out`)
- Params: whatever is currently in `DEFAULT_PARAMS["EMA Crossover"]` at run
  time — i.e. the Task 108-adopted pullback gate (`entry_mode=pullback,
  pullback_max_bars=15`), not overridden here
- Aggregation math: identical to every other `run_backtest_range.py` run —
  `win_rate` over win+loss only, `expectancy_r` over all closed trades
  (win+loss+scratch+timeout), `excluded_share = (scratches+timeouts)/closed`

## Command

```
python scripts/run_backtest_range.py --validation --exit-model v2 \
    --scale-out --strategy "EMA Crossover" --json rescue_ema_validation.json
```

Raw output JSON: `docs/superpowers/results/rescue_ema_validation.json`
(moved there after the run; the script writes it to the invocation
directory).

## Result

| Strategy | Horizon | N | Win% | ExpR | AvgWinR | Scr | TO | Excl% | tp2% | trail% | be% | rto% | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EMA Crossover | (all, pooled) | 36 | 75.0 | +0.061 | +0.442 | 12 | 0 | 25% | 63.0% | 3.7% | 33.3% | 0.0% | FAIL |

Per-horizon breakdown (for gating decisions, transcribed verbatim from the
console table the harness prints):

| Strategy | Horiz | N | Win% | ExpR |
|---|---|---|---|---|
| EMA Crossover | 2m | 6  | 83.3  | +0.116 |
| EMA Crossover | 2w | 16 | 75.0  | +0.100 |
| EMA Crossover | 3m | 3  | 100.0 | +0.343 |
| EMA Crossover | 4m | 1  | 100.0 | +0.084 |
| EMA Crossover | 4w | 9  | 55.6  | -0.151 |
| EMA Crossover | 5m | 0  | n/a   | +0.000 |
| EMA Crossover | 6m | 1  | 100.0 | +0.421 |

## PASS/FAIL vs gates (N floor 15)

- `N=36 >= 15` — clears the sample-size floor.
- `excluded_share=25% <= 50%` — clears the scratch+timeout cap comfortably.
- `expectancy_r=+0.061 > 0` — clears the expectancy gate.
- `win_rate=75.0% >= 80%` — **fails.** 5 points short of the 80% floor.

Three of four gates pass; the win-rate gate — the one this whole rescue was
staged to clear — does not. **Overall verdict: FAIL.**

## Honest observations

This VALIDATION run does not qualify EMA Crossover, despite a very strong
TRAIN result (91.2% WR, the best clean pass of any strategy in this rescue
phase):

- Pre-rescue baseline (round 1, no pullback gate, registry record dated
  2026-07-18): N=78, WR=76.9%, ExpR=+0.015 on the same validation window.
- TRAIN (this rescue's grid, gate on, `pullback_max_bars=15`): N=68,
  WR=91.2%, ExpR=+0.197.
- VALIDATION (this run, same gate/config, same window as the pre-rescue
  baseline): N=36, WR=75.0%, ExpR=+0.061.

The pullback gate is directionally mixed out-of-sample: expectancy roughly
4x'd versus the ungated pre-rescue baseline (+0.015 to +0.061) and the
sample size, while much smaller than TRAIN's 68 (only 36 crosses found a
qualifying pullback in the validation window), still clears N>=15
comfortably. But win rate did not carry over the TRAIN gain at all — it
landed at 75.0%, fractionally *below* the pre-rescue ungated baseline's
76.9%, not above it. The per-horizon table shows why: `4w` (the horizon the
strategy's own docstring elsewhere flags as the most reliable for other
gated strategies) posts a losing 55.6% WR / -0.151 ExpR on only 9 trades,
dragging the pooled figure down, while every other horizon with N>=3 clears
80%+ WR on very thin samples (`3m`: 3 trades, `4m`/`6m`: 1 trade each — not
independently meaningful). This is a textbook TRAIN-overfit signature: a
91.2% TRAIN win rate that does not survive contact with 2024-2025 data,
consistent with round 1's original prediction that EMA Crossover would be
difficult to rescue. Per the plan's methodology, **no parameter is retuned
in response to this result** — the config stays exactly as TRAIN selected
it.

## Verdict: FAIL — EMA Crossover remains WEAK (last rescue attempt, phase closed)

Per the task's pre-registered fallback, EMA Crossover stays WEAK. No
`--emit-registry` run was made (that step is conditional on a VALIDATION
PASS, which did not happen) and `swingbot/core/validation_registry.json` is
untouched — its existing `"EMA Crossover"` record (WEAK, WR=76.9%,
run_date 2026-07-18, the round-1 result) stands as the source of truth.
`tests/test_registry.py::test_weak_strategy` (which asserts `EMA Crossover`
is `WEAK`) needs no change.

The rescue gate code (Task 107, the pullback entry-mode redesign) and its
TRAIN-adopted defaults (Task 108, `entry_mode=pullback,
pullback_max_bars=15`) remain in the codebase — they are a real, measured
improvement in expectancy over the ungated strategy on this exact
validation window (+0.061 vs +0.015) — but do not cross this plan's win-rate
bar for VALIDATED status.

This closes the rescue phase's five-strategy attempt list: RSI
(VALIDATED), RSI Divergence (REJECTED-ON-TRAIN), MA Ribbon
(REJECTED-ON-TRAIN), Elliott Wave (passed TRAIN, FAILED validation), EMA
Crossover (passed TRAIN, FAILED validation) — one rescued, four still WEAK.
