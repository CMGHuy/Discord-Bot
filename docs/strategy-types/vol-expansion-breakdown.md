# Vol Expansion Breakdown (B2, short-only)

`ENTRY_FUNCS["Vol Expansion Breakdown"]` = short-only wrapper over
`vol_breakdown_frame` (`swingbot/core/market/short_entries.py`) · sizing
`plan_short` in `swingbot/core/planning/short_builders.py` · gate **bearish
only, ships masked** (`STRATEGY_GATES["Vol Expansion Breakdown"] =
{"directions": ()}`). Shared rules: [shared-mechanics.md](shared-mechanics.md)
§4b — always in the v104 structural-stop scope, never the flat 2% cap.

One of three v104 Part B mechanisms, not a mirror of any bullish rule.

## Idea

A breakdown under a broad market decline, on volatility that is *expanding*,
not calm — the opposite of `atr_calm`, the shared gate every other rule uses
to avoid panic tape. The premise: when the market itself is falling and a
laggard breaks its own range low on heavy volume while its volatility is
actively widening, that is the kind of tape declines actually pay on, not the
quiet grind the bot's other rules are tuned for.

## Entry rule

- **Market:** SPY closes below a falling 50-day average
  (`ctx_spy_down == 1.0`, from `market_context.attach` — v104's B2 columns,
  `close < MA50` and `MA50 < MA50[t−20]`).
- **Stock:** `close < S`, where `S = min(Low over sr_lookback)` shifted 1.
- **Volume:** `Volume ≥ SR_VOLUME_MULTIPLE × mean20(Volume)` (the same
  multiple Support/Resistance uses).
- **Volatility expanding:** `ATR14 ≥ m × mean60(ATR14)` — the mirror image of
  `atr_calm`, which requires `ATR14 ≤ 1.4 × mean60(ATR14)`. **Grid `m ∈ {1.0,
  1.2, 1.4}`, loosest 1.0** (measured value: `m=1.0`).
- **Relative weakness:** the stock's own 63-bar return is below SPY's
  (`ctx_spy_ret63`) — it is lagging the market it is falling alongside, not
  just falling with it.
- **Filter:** `atr_floor` only — no `atr_calm` (this strategy wants
  expansion), no regime filter (the market-down condition above replaces it).
- **Earnings axis:** same `exit_before` rule as Bull Trap.
- **Without the market-context columns, this strategy returns no signal at
  all** (silent, not an error) — it needs `ctx_spy_down`/`ctx_spy_ret63`
  attached first.

## Plan and exits

- **Stop:** `S + 0.25 × ATR14` — just above the broken support level.
- **TP1 candidates:** the ATR ladder plus every zigzag swing low below entry
  (`_swing_lows_below`, using the horizon's own `max_risk_pct` as the pivot
  sensitivity) — structural targets down the chart, not a fixed base like
  Bull Trap's.
- **Sizing:** same `plan_short` rule as Bull Trap — drop, never cap; a stop
  beyond the horizon's ceiling builds no plan.
- **Exits:** shared across all three shorts — exit model v2, 50% off at TP1,
  trail 2.5 × ATR, TP2 off, TP1 by `select_structural_target`.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| v104 Stage 0, hold, loosest cell (m=1.0) | TRAIN 2010-2025, universe 74 | 3,755 | — | — | signal count only; `results/2026-09-28-v104-stage0.md` |
| v104 Stage 1, m=1.0 (loosest), hold | TRAIN 2010-2025 | 869 | 31.2% | −0.121 | lower bound −0.313, no tier |
| v104 Stage 1, m=1.2, hold | TRAIN 2010-2025 | 413 | 27.8% | −0.222 | lower bound −0.450, no tier |
| v104 Stage 1, m=1.4, hold | TRAIN 2010-2025 | 244 | 23.4% | −0.308 | lower bound −0.629, no tier |
| v104 Stage 1, m=1.0 (loosest), exit_before | TRAIN 2010-2025 | 713 | 34.8% | **−0.037** | lower bound −0.255, no tier |
| v104 Stage 1, m=1.2, exit_before | TRAIN 2010-2025 | 354 | 29.7% | −0.188 | lower bound −0.453, no tier |
| v104 Stage 1, m=1.4, exit_before | TRAIN 2010-2025 | 210 | 22.9% | −0.354 | lower bound −0.685, no tier |

**Every cell's ExpR is negative — no tier clears anywhere.** Unlike Bull
Trap, `exit_before` is *better* than `hold` at the loosest cell (+0.084 ExpR:
−0.121 → −0.037) and at `m=1.2` (+0.034), reversing only at the tightest,
thinnest cell (`m=1.4`). **2013, 2017, 2021 and 2024 have zero signal** at the
loosest cell in both earnings settings — a fold anchored on any of those
years trains on nothing (`docs/superpowers/results/2026-09-28-v104-stage0.md`
flagged this before Stage 1 ran). **NO-LIFT at Stage 1 — no holdout shot
spent, budget intact.** If this mechanism is ever revisited, `exit_before` is
the earnings setting to start from, not `hold`. Full detail:
`results/2026-09-28-v104-partB.md`.

## Pseudocode

```python
if "ctx_spy_down" not in df or "ctx_spy_ret63" not in df: return no_signal

S = rolling_min(Low, sr_lookback).shift(1)
market_down = ctx_spy_down == 1.0
weaker = (Close / Close.shift(63) - 1.0) < ctx_spy_ret63
heavy = Volume >= SR_VOLUME_MULTIPLE * mean20(Volume)
expanding = ATR14 >= m * mean60(ATR14)

fire if (Close < S) and market_down and weaker and heavy and expanding
        and atr_floor and earnings_ok
stop = S + 0.25 * ATR14
```
