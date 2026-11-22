---
strategy: "Downtrend Overbought Fade"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/short_entries.py:fade_frame
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short. In a stock already in a downtrend, a sharp few-day rally to overbought is usually sold into.

**Entry rule.**

- The close is under a falling long moving average.
- A very short RSI spikes to an extreme overbought reading.
- No earnings report is due in the next few bars; a sell limit rests at the close, with a stop a fixed small distance above.

**Where it fires.** Short only; the rule ignores the horizon, and a holdout pass would admit it on the 1w horizon alone. Until then it is masked: research only.

<details><summary>Under the hood</summary>

`short_entries.fade_frame`; the frozen constants `FADE_SMA`, `FADE_RSI_PERIOD`, `FADE_RSI_MIN`, `FADE_STOP_PCT`, `FADE_EARNINGS_BARS`; needs the `evt_bars_to_next` column.

</details>
