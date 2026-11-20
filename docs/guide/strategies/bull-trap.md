---
strategy: "Bull Trap"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/short_entries.py:bull_trap_frame
  - swingbot/core/market/short_entries.py:earnings_ok
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short. A breakout above the range high that fails fast traps the buyers who chased it; their exits push price back down.

**Entry rule.**

- The close broke above the prior range high, then closed back below it within a few bars.
- Volatility is not dead and volume is normal or better; by default an earnings report does not block the entry (earnings handling is a parameter).
- The stop sits a small ATR buffer above the failed high; the targets are the base under the breakout and the range low.

**Where it fires.** Short only, on every horizon. The mask admits no cell, so it is masked: measured in research, never alerted, until its pre-registered holdout test passes.

<details><summary>Under the hood</summary>

`short_entries.bull_trap_frame`; the failure window and earnings handling in `DEFAULT_PARAMS["Bull Trap"]`.

</details>
