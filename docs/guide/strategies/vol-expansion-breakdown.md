---
strategy: "Vol Expansion Breakdown"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/short_entries.py:vol_breakdown_frame
  - swingbot/core/market/short_entries.py:earnings_ok
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short. A weak stock breaking support in a falling market, while its daily range is expanding, tends to keep falling.

**Entry rule.**

- The close falls under the prior range low on heavy volume, with ATR expanding above its recent mean.
- The broad market is falling (SPY under a falling medium average) and the stock has lagged SPY.
- The stop sits a small ATR buffer above the broken support; earnings handling is a parameter, not a default gate.

**Where it fires.** Short only, on every horizon, and only when the market context is attached. The mask admits no cell, so it is masked: research only until its holdout test passes.

<details><summary>Under the hood</summary>

`short_entries.vol_breakdown_frame` (no signal without the `ctx_spy_down` / `ctx_spy_ret63` columns).

</details>
