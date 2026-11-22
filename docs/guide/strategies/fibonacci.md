---
strategy: "Fibonacci"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:fibonacci_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** In an uptrend, pullbacks often pause at the classic retracement ratios of the last swing. The trade buys the bounce from one of them.

**Entry rule.**

- In the look-back window the swing low came before the swing high, so the swing is an up-move.
- After pulling back for several bars, price sits near the 0.382, 0.5 or 0.618 retracement of that swing.
- The bar bounces and closes in its upper half, RSI is in a lower-middle band, and the shared gates pass.

**Where it fires.** The rule has a short mirror (a bounce down from a retracement of a down-swing), but the mask admits only longs.

<details><summary>Under the hood</summary>

`entry_filters.fibonacci_entries`; ratios and RSI band in `DEFAULT_PARAMS["Fibonacci"]`, window `HORIZONS[h]["fib_lookback"]`. Two optional filters, `FIB_SR_CONFLUENCE_ATR` and `FIB_LEVEL_STOP_ATR`, are settings where `0` turns them off.

</details>
