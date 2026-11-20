---
strategy: "Break & Retest"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:break_retest_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A range high that held price back often becomes the floor once it breaks on heavy volume. The trade buys the first pullback that holds the old high.

**Entry rule.**

- Within the last few bars price broke the prior range high on volume well above its recent average.
- Price is back near that level, the bar's low held it, and the close cleared the previous bar's high.
- RSI sits in a middle band, and the shared trend and volatility gates pass.

**Where it fires.** Both sides (shorts mirror it at a broken range low), on the 2m, 3m and 4m horizons only; the mask keeps the horizons its measurement supported.

<details><summary>Under the hood</summary>

`entry_filters.break_retest_entries`. The level is the prior `sr_lookback` high or low (`_break_retest_levels`); how recent the break and how close the retest must be, per horizon: `BRT_RECENT_BARS`, `BRT_RETEST_PCT`.

</details>
