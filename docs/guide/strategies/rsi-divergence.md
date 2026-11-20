---
strategy: "RSI Divergence"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:rsi_divergence_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** Hidden divergence: price makes a higher low while RSI makes a lower low. In an uptrend that marks a pullback losing force; the entry waits for RSI to turn back up.

**Entry rule.**

- Over the look-back window price set a higher low and RSI a lower low.
- RSI has reclaimed its reclaim line and is rising, inside a lower-middle band; `RSI_DIV_MIN_CONSECUTIVE_TURN` sets how many rising bars count as a turn.
- The shared gates pass. Shorts mirror it: a lower high in price against a higher high in RSI.

**Where it fires.** Both sides on every live horizon.

<details><summary>Under the hood</summary>

`entry_filters.rsi_divergence_entries`, a rolling formulation without discrete swing points; reclaim line and the optional volume and reclaim-strength filters in `DEFAULT_PARAMS["RSI Divergence"]`.

</details>
