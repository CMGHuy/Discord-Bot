---
strategy: "Fibonacci Limit"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:fibonacci_limit_entries
  - swingbot/core/market/entry_filters.py:fibonacci_limit_setups
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A long. Rather than waiting for a bounce, rest a buy limit order at the 0.618 retracement of an up-leg and let the pullback come to it.

**Entry rule.**

- An up-leg whose high is a few bars old has started to pull back.
- A buy limit rests at the 0.618 retracement of the leg; each leg arms at most once.
- The order lives a few bars and is cancelled if price trades above the swing high first.

**Where it fires.** Long only. The mask admits no cell, so it is masked: research measures it by lifting the mask for the replay only, and live wiring is a later spec.

<details><summary>Under the hood</summary>

`entry_filters.fibonacci_limit_setups` (arming, order life, cancel); `fibonacci_limit_entries` returns nothing while masked; constants `FIB_LIMIT_MIN_RETRACE`, `FIB_LIMIT_MIN_AGE`; research unmasks it with `gate_override`.

</details>
