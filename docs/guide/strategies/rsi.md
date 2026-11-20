---
strategy: "RSI"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:rsi_entries
  - swingbot/core/market/entry_filters.py:adx_series
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short oversold dip inside a healthy long-term uptrend tends to snap back. The trade buys the first strong bar after RSI leaves oversold.

**Entry rule.**

- RSI was oversold on the two previous bars and is now back above the oversold line, still low.
- The long moving average is rising; the close is above where it was a few bars ago and above the previous bar's high.
- The market is ranging rather than trending hard (low ADX), and the volatility and volume gates pass.

**Where it fires.** The rule has a short mirror (an overbought fade under a falling long average), but the mask admits only longs.

<details><summary>Under the hood</summary>

`entry_filters.rsi_entries`; oversold line, confirmation mode and ADX ceiling in `DEFAULT_PARAMS["RSI"]`. It uses only the slope of the long average (`bull_regime_slope_only` in `compute_shared_gates`), not price above it, because a dip trades below the short averages.

</details>
