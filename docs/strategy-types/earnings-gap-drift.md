# Earnings Gap Drift (B3, short-only)

`ENTRY_FUNCS["Earnings Gap Drift"]` = short-only wrapper over
`gap_drift_frame` (`swingbot/core/market/short_entries.py`) · sizing
`plan_short` in `swingbot/core/planning/short_builders.py` · gate **bearish
only, ships masked** (`STRATEGY_GATES["Earnings Gap Drift"] = {"directions":
()}`). Shared rules: [shared-mechanics.md](shared-mechanics.md) §4b — always
in the v104 structural-stop scope. Unlike Bull Trap and Vol Expansion
Breakdown, **this strategy has no earnings axis at all** — `exit_before`
does not apply to it, since it is entirely built from the earnings reaction
itself.

One of three v104 Part B mechanisms, not a mirror of any bullish rule.

## Idea

A bad earnings reaction that does not get bought back: the stock gaps down
hard on its reaction day and keeps drifting lower the next session instead of
recovering. The premise is post-earnings-announcement drift on the downside —
that an unrecovered gap-down carries continuation risk into the following
session.

## Entry rule

- **Reaction day:** `evt_reaction == 1.0` (the earnings-context column,
  `swingbot/core/market/earnings_context.py` — the one bar per report where
  the reaction is measured; this is same-bar information, not a lookahead
  exception, unlike `evt_bars_to_next`).
- **Gap-down day condition:** `Open ≤ close[t−1] × (1 − g)` on the reaction
  day. **Grid `g ∈ {0.05, 0.08, 0.12}`, loosest 0.05** (measured value:
  `g=0.05`).
- **Entry (drift) bar:** the session *after* the gap day, if it closes below
  the gap day's close (`close < close[gap_day]`) — no recovery.
- **Horizon-independent:** the entry ignores `horizon_key` entirely, so all
  ten horizons see the same underlying bars; a pooled N across horizons
  counts the same trades up to ten times (disclosure, not a bug — matches
  the same construction B3's Stage 0 counts flagged).
- **Without `evt_reaction` in the frame, this strategy returns no signal at
  all** (silent, not an error).

## Plan and exits

- **Stop:** `High[gap_day] + 0.25 × ATR14` — above the gap day's own high,
  not the drift-entry bar's.
- **TP1 candidates:** the ATR ladder plus every zigzag swing low below entry,
  same as Vol Expansion Breakdown.
- **Sizing:** same `plan_short` rule — drop, never cap.
- **Exits:** shared across all three shorts — exit model v2, 50% off at TP1,
  trail 2.5 × ATR, TP2 off, TP1 by `select_structural_target`.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| v104 Stage 0, loosest cell (g=0.05) | TRAIN 2010-2025, universe 74 | 3,220 | — | — | signal count only; `results/2026-09-28-v104-stage0.md` |
| v104 Stage 1, g=0.05 (loosest) | TRAIN 2010-2025 | 716 | 35.5% | −0.024 | lower bound −0.206, no tier |
| v104 Stage 1, g=0.08 | TRAIN 2010-2025 | 335 | 39.7% | +0.043 | lower bound −0.217, no tier |
| v104 Stage 1, g=0.12 | TRAIN 2010-2025 | 148 | 35.8% | +0.023 | lower bound −0.364, no tier |

`g=0.08` and `g=0.12` post small **positive point-estimate** ExpR, the
closest of any v104 short cell to a Tier 2 pass — but both bootstrap lower
bounds stay negative, so neither clears the tier (Tier 2 needs the lower
bound itself above 0, not the point estimate). No plateau forms with the
negative loosest cell, so there is no Stage 1 winner. Several per-fold-year
test counts sit below the 15-trade floor even though the pooled N is large
(716 at the loosest cell); the 2016 and 2024 folds show large single-year
swings (+2.017R and +1.654R respectively) on only 9 trades each — exactly the
small-N noise the fold-stability check exists to catch. **NO-LIFT at Stage 1
— no holdout shot spent, budget intact.** Full detail:
`results/2026-09-28-v104-partB.md`.

## Pseudocode

```python
if "evt_reaction" not in df: return no_signal

gap_day = (evt_reaction == 1.0) & (Open <= Close.shift(1) * (1 - g))
after_gap = gap_day.shift(1)
fire if after_gap and Close < Close.shift(1)   # no recovery the next session
stop = High.shift(1) + 0.25 * ATR14            # gap day's own high
```
