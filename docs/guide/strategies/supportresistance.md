---
strategy: "Support/Resistance"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:support_resistance_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A breakout from a tight base through the range high, on heavy volume and with a strong close, often starts a new leg up.

**Entry rule.**

- The close crosses above the prior range high on volume well above its recent average.
- The bars before it formed a tight base, measured against ATR, and the bar closes near its high.
- The open did not gap far above the level, and the shared trend and volatility gates pass.

**Where it fires.** The rule has a short mirror (a breakdown through the range low), but the mask admits only longs, and only on the horizons its measurement supported. The setting `SR_MIN_LEVEL_TOUCHES` can also demand earlier rejections at the level.

<details><summary>Under the hood</summary>

`entry_filters.support_resistance_entries`; the range spans `HORIZONS[h]["sr_lookback"]` bars; base, close and gap limits in `DEFAULT_PARAMS["Support/Resistance"]`.

</details>
