# Elliott Wave rescue gate — VALIDATION (Task 106, single run)

## Rule (pre-registered, quoted verbatim)

Per the plan's Global Constraints (same rule every rescue/VALIDATION run in
this plan uses, e.g. `docs/superpowers/results/2026-07-confluence-validation.md`):

> VALIDATION is run **once per component** (exit model v2, confluence gates,
> each rescue strategy) with pre-registered gates; results reported as-is,
> never retuned after.

> **Acceptance gates:** `win_rate >= 80`, `expectancy_r > 0`, `N >= 15`
> (validation), `scratches+timeouts <= 50%` of closed trades.

The config under test is the one Task 105's TRAIN grid selected and
permanently adopted into `DEFAULT_PARAMS["Elliott Wave"]`
(`swingbot/core/entry_filters.py`), quoted from
`docs/superpowers/results/2026-07-rescue-elliott-train.md`:

```
w2_min_retrace=0.382, w2_max_retrace=0.618, w2_max_duration_ratio=0.75
-> TRAIN: N=117, WR=83.8%, ExpR=+0.094, excluded_share=28%
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
- Strategy: `Elliott Wave` only (`--strategy "Elliott Wave"`), which only
  fires on the `4w` horizon (unchanged, pre-existing behavior)
- Exit model: v2 with scale-out (`--exit-model v2 --scale-out`)
- Params: whatever is currently in `DEFAULT_PARAMS["Elliott Wave"]` at run
  time — i.e. the Task 105-adopted rescue gate, not overridden here
- Aggregation math: identical to every other `run_backtest_range.py` run —
  `win_rate` over win+loss only, `expectancy_r` over all closed trades
  (win+loss+scratch+timeout), `excluded_share = (scratches+timeouts)/closed`

## Command

```
python scripts/run_backtest_range.py --validation --exit-model v2 \
    --scale-out --strategy "Elliott Wave" --json rescue_elliott_validation.json
```

Raw output JSON: `docs/superpowers/results/rescue_elliott_validation.json`
(moved there after the run; the script writes it to the invocation
directory).

## Result

| Strategy | Horizon | N | Win% | ExpR | AvgWinR | Scr | TO | Excl% | tp2% | trail% | be% | rto% | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Elliott Wave | 4w | 75 | 77.3 | +0.064 | +0.405 | 25 | 1 | 26% | 25.9% | 12.1% | 55.2% | 6.9% | FAIL |

(Transcribed verbatim from the console table the harness prints; only
`4w` appears in the per-horizon breakdown because Elliott Wave fires on no
other horizon, so the strategy-level and per-horizon rows are identical.)

## PASS/FAIL vs gates (N floor 15)

- `N=75 >= 15` — clears the sample-size floor comfortably.
- `excluded_share=26% <= 50%` — clears the scratch+timeout cap comfortably.
- `expectancy_r=+0.064 > 0` — clears the expectancy gate.
- `win_rate=77.3% >= 80%` — **fails.** 2.7 points short of the 80% floor.

Three of four gates pass; the win-rate gate — the one this whole rescue was
staged to clear — does not. **Overall verdict: FAIL.**

## Honest observations

This VALIDATION run does not qualify Elliott Wave, but it is a real
improvement over both the pre-rescue baseline and a directionally
consistent (not surprising) out-of-sample result:

- Pre-rescue baseline (round 1, no wave-2 gate, registry record dated
  2026-07-10): N=159, WR=74.8%, ExpR=+0.008 on the same validation window.
- TRAIN (this rescue's grid, gate on): N=117, WR=83.8%, ExpR=+0.094.
- VALIDATION (this run, same gate, same window as the pre-rescue baseline):
  N=75, WR=77.3%, ExpR=+0.064.

The gate genuinely helped: win rate rose from 74.8% to 77.3% and
expectancy roughly 8x'd (+0.008 to +0.064) versus the ungated pre-rescue
baseline on the identical validation window — this is not a wash. But the
TRAIN-to-VALIDATION drop (83.8% to 77.3%, a similar-sized give-back to
what other TRAIN/VALIDATION pairs in this plan have shown) lands the win
rate short of the 80% acceptance floor. This is the expected/consistent
direction for a TRAIN-selected config evaluated out-of-sample, not an
anomaly, and per the plan's methodology **no parameter is retuned in
response to this result.**

## Verdict: FAIL — Elliott Wave remains WEAK

Per the task's pre-registered fallback, Elliott Wave stays WEAK. No
`--emit-registry` run was made (that step is conditional on a VALIDATION
PASS, which did not happen) and `swingbot/core/validation_registry.json`
is untouched — its existing `"Elliott Wave"` record (WEAK, WR=74.8%,
run_date 2026-07-10, the round-1 result) stands as the source of truth.
The rescue gate code (Task 104) and its TRAIN-adopted defaults (Task 105)
remain in the codebase — they are a real, measured improvement over the
ungated strategy — but do not cross this plan's bar for VALIDATED status.

**Methodology caveat:** Task 105's TRAIN grid ran under v1/no-scale-out
economics (see the "Methodology gap" note appended to
`2026-07-rescue-elliott-train.md`) because `scripts/tune_strategy.py` did not
yet support `--exit-model`/`--scale-out` when that task executed, while this
VALIDATION run correctly used v2/scale-out. The two are not a matched pair
the way RSI's TRAIN/VALIDATION runs are. This is recorded honestly rather
than corrected, since correcting it would require a second VALIDATION-window
look at this strategy — forbidden by the plan's one-look budget regardless
of the reason. The FAIL verdict above is the real, final result.
