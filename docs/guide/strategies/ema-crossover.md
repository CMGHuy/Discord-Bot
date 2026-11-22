---
strategy: "EMA Crossover"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:ema_cross_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A fast moving average crossing a slow one marks a turn in trend. Waiting for the first pullback to the fast average buys the new trend at a better price than the cross.

**Entry rule.**

- The fast EMA crossed above the slow EMA and stayed above on the next bar.
- Within a set number of bars price dips to the fast EMA and closes back above it; the first such touch is the entry.
- RSI dipped below its threshold at least once in the five bars before entry and is above its midline on the entry bar. The slow EMA is rising at entry, momentum agrees, price stays close enough to the fast EMA, and the shared gates pass.

**Where it fires.** Both sides (shorts mirror it) on every horizon, with the periods of the averages set per horizon.

<details><summary>Under the hood</summary>

`entry_filters.ema_cross_entries` with `DEFAULT_PARAMS["EMA Crossover"]` (`entry_mode` "pullback", the touch window, the re-arm count); periods `HORIZONS[h]["ema_fast"]` and `HORIZONS[h]["ema_slow"]`.

</details>
