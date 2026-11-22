---
strategy: "First Bearish Compression Release"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/short_entries.py:compression_short_frame
  - swingbot/core/market/volatility.py:squeeze_release_series
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short. After a volatility squeeze, the first release that breaks downward often starts a move lower.

**Entry rule.**

- A squeeze (Bollinger Bands inside the Keltner Channel) releases.
- The release bar closes under the prior lower Bollinger Band on at least 1.5x average volume.
- The stop sits a small ATR buffer above the high of the release bar; the planning layer sets the final stop and target.

**Where it fires.** Short only, on the 2w horizon only. The mask admits no cell, so it is masked: research only until its pre-registered test passes.

<details><summary>Under the hood</summary>

`short_entries.compression_short_frame` reads `volatility.squeeze_release_series` (`bearish_confirmed`) and returns nothing off `2w`.

</details>
