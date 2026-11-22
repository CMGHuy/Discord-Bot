---
strategy: "Volume Profile"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:volume_profile_entries
  - swingbot/core/market/entry_filters.py:_vectorized_hvn
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** Prices where a lot of volume traded act as memory: buyers who defended them before tend to defend them again. The trade buys a bounce just above such a node.

**Entry rule.**

- The busiest price band of the window holds a large enough share of all volume to count as a node.
- The close sits just above that node and is up on the bar.
- RSI is in a middle band, and the shared gates pass.

**Where it fires.** The rule has a short mirror, but the mask admits only longs, and only on the horizon its measurement supported.

<details><summary>Under the hood</summary>

`entry_filters.volume_profile_entries`; the node comes from `_vectorized_hvn` over `HORIZONS[h]["sr_lookback"]` bars; node share and proximity in `DEFAULT_PARAMS["Volume Profile"]`.

</details>
