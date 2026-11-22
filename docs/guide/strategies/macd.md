---
strategy: "MACD"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:macd_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A MACD line turning up through its signal line, with the gap widening, shows momentum returning to an uptrend.

**Entry rule.**

- The MACD line crosses above its signal line, or the histogram turned positive and held.
- The histogram has grown on consecutive bars, the MACD line is above zero and RSI is above its midline.
- Price is not stretched away from the fast average, and the shared gates pass.

**Where it fires.** The rule has a short mirror, but the mask admits only longs, and only on the horizons its measurement supported.

<details><summary>Under the hood</summary>

`entry_filters.macd_entries`; MACD periods per horizon in `strategy_types.MACD_PERIODS_BY_HORIZON`, stretch limit in `DEFAULT_PARAMS["MACD"]`.

</details>
