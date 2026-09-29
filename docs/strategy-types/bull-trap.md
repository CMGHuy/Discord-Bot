# Bull Trap (B1, short-only)

`ENTRY_FUNCS["Bull Trap"]` = short-only wrapper over `bull_trap_frame`
(`swingbot/core/market/short_entries.py`) · sizing `plan_short` in
`swingbot/core/planning/short_builders.py` · gate **bearish only, ships
masked** (`STRATEGY_GATES["Bull Trap"] = {"directions": ()}`) — it never
alerts and the backtest never selects it until its holdout shot passes.
Shared rules: [shared-mechanics.md](shared-mechanics.md), but note this
strategy is **always** in the v104 structural-stop scope (§4b there) — it
never runs under the flat 2% cap, in scope or out.

One of three v104 Part B mechanisms, not a mirror of any bullish rule
(spec rationale: [shared-mechanics.md](shared-mechanics.md) §4b, and
`docs/claude/backtest-methodology.md`'s v104 rows).

## Idea

A failed breakout: price closes above the recent range high, then closes back
below that same level within a few bars. The breakout buyers who bought the
high are now underwater, and the level that looked like resistance-turned-
support failed to hold — a classic bull trap.

## Entry rule

- **Level** `R = max(High over sr_lookback)`, shifted 1 bar (the same rolling
  high Support/Resistance uses).
- **Breakout bar `b`:** `close[b] > R[b]`.
- **Entry (trap) bar `t`:** the first bar in `(b, b + k]` with `close[t] <
  R[b]`. **Grid `k ∈ {1, 2, 3}`, loosest 3** (measured value: `k=3`, per
  `DEFAULT_PARAMS["Bull Trap"]`). The first trap bar to claim a breakout wins
  it — a bar never fires twice, and a later breakout from the same level
  starts its own fresh `k`-bar window.
- **Filters:** `atr_floor`, `vol_ok`. No regime filter — the setup is
  specifically about failing at resistance, not about the broader trend.
- **Earnings axis:** `exit_before` blocks an entry whose next scheduled
  report reacts within 1 bar; otherwise it enters normally (index amendment
  1). Fails closed if `earnings_context.attach` was never called.

## Plan and exits

- **Stop:** `max(High over b..t) + 0.25 × ATR14` — above the trap's own
  wick, not just the breakout bar's close.
- **TP1 candidates:** the ATR ladder, the 10-bar low before `b`, and
  `min(Low over sr_lookback)` shifted 1 — the pre-breakout base and the
  broader range low.
- **Sizing:** `plan_short` computes the stop from `structure_at` and rejects
  the plan outright if the stop is beyond the horizon's ceiling (**drop,
  never cap** — this strategy is always in scope). A valid stop still needs a
  target clearing `MIN_RISK_REWARD_RATIO` (1.5R) or no plan is built, same
  rule as every other strategy.
- **Exits:** shared, fixed and not tuned across all three shorts — exit
  model v2, 50% off at TP1, trail 2.5 × ATR, **TP2 off**, TP1 selected by
  `select_structural_target` (1.5R floor, 2.5R cap).

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| v104 Stage 0, hold, loosest cell (k=3) | TRAIN 2010-2025, universe 74 | 30,452 | — | — | signal count only; `results/2026-09-28-v104-stage0.md` |
| v104 Stage 1, k=1, hold | TRAIN 2010-2025 | 590 | 27.6% | −0.147 | lower bound −0.331, no tier |
| v104 Stage 1, k=2, hold | TRAIN 2010-2025 | 746 | 28.4% | −0.146 | lower bound −0.298, no tier |
| v104 Stage 1, k=3 (loosest), hold | TRAIN 2010-2025 | 814 | 27.3% | −0.170 | lower bound −0.322, no tier |
| v104 Stage 1, k=1, exit_before | TRAIN 2010-2025 | 498 | 22.3% | −0.199 | lower bound −0.364, no tier |
| v104 Stage 1, k=2, exit_before | TRAIN 2010-2025 | 626 | 22.8% | −0.207 | lower bound −0.338, no tier |
| v104 Stage 1, k=3 (loosest), exit_before | TRAIN 2010-2025 | 684 | 21.5% | −0.231 | lower bound −0.359, no tier |

**Every cell's ExpR is negative, in both earnings settings, at every grid
value.** `exit_before` is consistently worse than `hold` (closing the short
before an earnings reaction costs it ExpR at all three `k` values, roughly
-0.05 to -0.06R). No cell clears Tier 1 (WR ≥ 50) or Tier 2 (bootstrap lower
bound > 0). **NO-LIFT at Stage 1 — no holdout shot spent, budget intact.**
Full detail: `results/2026-09-28-v104-partB.md`.

## Pseudocode

```python
R = rolling_max(High, sr_lookback).shift(1)
breakouts = where(Close > R)
for b in breakouts:
    for t in range(b + 1, b + k + 1):
        if Close[t] < R[b] and not already_claimed(t):
            signal[t] = True
            stop[t] = max(High[b:t+1]) + 0.25 * ATR14[t]
            target_a[t] = min(Low[b-10:b])       # pre-breakout base
            target_b[t] = min(Low[t-sr_lookback:t])
            break  # first trap claims the bar
fire if signal and atr_floor and vol_ok and earnings_ok
```
