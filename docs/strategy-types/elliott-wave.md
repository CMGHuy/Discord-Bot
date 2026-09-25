# Elliott Wave (wave-3 breakout)

`ENTRY_FUNCS["Elliott Wave"]` = `elliott_wave_entries` · signal
`elliott_wave_signal` · sizing **structural** (`_elliott_plan`) · gate
**none**, but **the rule only fires on 4w**. Shared rules:
[shared-mechanics.md](shared-mechanics.md).

## Idea

Elliott Wave theory says trends move in five waves. Wave 3 is usually the
longest and strongest. The bot mechanises one piece of that:

- **Wave 1:** an impulse up.
- **Wave 2:** a pullback that doesn't erase wave 1.
- **Wave 3:** a close back above wave 1's high, which is the entry.

The code says plainly that this is a simplification: no wave-3/5 length
ratios, no alternation, no higher-degree count.

## Pivots (`indicators.zigzag_pivots`)

A zigzag over **closes**. A new pivot is confirmed when price reverses at
least `threshold_pct` from the last extreme, where the threshold is the
horizon's `max_risk_pct` (7% on 4w). The walk runs forwards only, so each
pivot is fixed from bars up to its confirmation. Crossing wave 1 needs a rise
of more than 7% from wave 2, so the wave-2 pivot is already confirmed on the
entry bar.

## Entry rule (bullish; bearish mirrors)

**Horizon 4w only.** Every other horizon returns no signals: on 2w the pivots
are noise, and from 2m up the approximation degrades.

1. **Structure:** three consecutive pivots low (w0) → high (w1) → low (w2),
   with `w2 > w0`.
2. **Trigger:** the first bar after w2 where `close[t] > w1` and
   `close[t−1] ≤ w1`.
3. **Strict wave-2 validation** (Task 104 rescue):
   - wave-2 retrace `(w1 − w2) / (w1 − w0)` between 0.382 and 0.618;
   - wave 2 lasts ≤ 0.75 × wave 1's duration;
   - no overlap: w2 stays on w1's side of w0.
   There is also a depth check of 0.30–0.80, which the stricter band
   already covers.
4. `RSI14 > 55` and `RSI14 > RSI14[t−2]`.
5. Shared: `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`, `vol_ok`.

Bearish: pivots high → low → high with `w2 < w0`, a close below w1,
`RSI < 45` and falling, and the bear gates.

## Plan

- **Stop:** `w2 − 0.25 × ATR14` (below the wave-2 low), then capped at 2%.
  Wave 2 is at least 7% below wave 1 and entry is above wave 1, so the cap
  **nearly always binds**: the stop is effectively entry − 2%.
- **TP1 candidates** (`elliott_target_candidates`): `w1`, and
  `w2 + k × |w1 − w0|` for k ∈ {1.0, 1.618, 2.618}. These are the classic
  wave-3 projections. `w1` sits below entry, so only the projections can be
  targets.

Exits use the defaults: trail 2.5 × ATR, TP2 on.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Registry (run 2026-07-18) | VALIDATION 2024–25 | 75 | 77.3% | +0.064 | **WEAK**, pre-v31 arithmetic: stale |

- Tasks 104–106 (2026-07): TRAIN chose the strict wave-2 config (N=117,
  WR 83.8%, ExpR +0.094, pre-v31 arithmetic). Its VALIDATION shot FAILED.
- v84: the proposed rescue was withdrawn, because it already shipped.

## Pseudocode

```python
if h != "4w": no signals
for (w0 low, w1 high, w2 low) consecutive zigzag(Close, 7%) pivots with w2 > w0:
    t = first bar after w2 with Close[t-1] <= w1 < Close[t]
    fire if 0.382 <= (w1-w2)/(w1-w0) <= 0.618 and dur(w2) <= 0.75*dur(w1)
            and RSI > 55 and RSI > RSI[t-2] and bull_regime and Close > MA50 and tape_ok
stop = max(w2 - 0.25*ATR, entry*0.98)
tp1 from {w2 + k*(w1-w0) : k in 1, 1.618, 2.618}
```
