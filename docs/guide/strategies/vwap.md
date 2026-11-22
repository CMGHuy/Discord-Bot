---
strategy: "VWAP"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:vwap_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** VWAP is the average price paid, weighted by volume. Reclaiming a rising VWAP and holding it suggests buyers are back in control.

**Entry rule.**

- The close was below the rolling VWAP and has now held above it for a few bars, while VWAP is rising.
- Price is still close to VWAP (no chasing), and RSI is in a middle band.
- The shared gates pass.

**Where it fires.** The rule has a short mirror, but the mask admits only longs, and only on the horizon its measurement supported.

<details><summary>Under the hood</summary>

`entry_filters.vwap_entries`; window `HORIZONS[h]["vwap_window"]`; hold length (its own value on 2w), stretch limit and RSI band in `DEFAULT_PARAMS["VWAP"]`.

</details>
