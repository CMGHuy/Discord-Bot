---
strategy: "Fibonacci Continuation"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:fib_continuation_entries
  - swingbot/core/market/entry_filters.py:fib_continuation_frame
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** Instead of buying the bounce at a retracement, wait for the trend to prove itself: buy when price breaks back through the swing high after a held pullback.

**Entry rule.**

- The pullback held between the 0.382 and 0.618 retracement of the swing and lasted a few bars.
- The close breaks back through the swing extreme, with the shared gates passing.
- The stop sits a small ATR buffer back inside the broken swing level and must fit the planned-loss cap, or there is no signal. Shorts mirror it.

**Where it fires.** Both sides, every horizon. The mask admits no cell, so it is masked: research only until a direction passes its pre-registered test.

<details><summary>Under the hood</summary>

`entry_filters.fib_continuation_frame` and `fib_continuation_entries`; depth bounds and pullback length in `DEFAULT_PARAMS["Fibonacci Continuation"]`; stop buffer `FIB_CONTINUATION_STOP_ATR`.

</details>
