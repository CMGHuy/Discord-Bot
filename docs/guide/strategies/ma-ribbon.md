---
strategy: "MA Ribbon"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:ma_ribbon_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** When short, medium and long moving averages stack in order and the short one crosses the medium one, an uptrend is gathering pace.

**Entry rule.**

- The fast EMA crosses above the mid EMA while both sit above the slow SMA, and the slow SMA is rising.
- Price is not stretched far above the slow SMA, RSI is in a healthy band, and MACD is above zero.
- The shared gates pass; the setting `MA_RIBBON_CONFIRM_BARS` can demand that the stack holds for more bars.

**Where it fires.** The rule has a short mirror, but the mask admits only longs.

<details><summary>Under the hood</summary>

`entry_filters.ma_ribbon_entries`; periods per horizon in `RIBBON_PERIODS_BY_HORIZON`, thresholds in `DEFAULT_PARAMS["MA Ribbon"]`.

</details>
