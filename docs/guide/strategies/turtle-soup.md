---
strategy: "Turtle Soup"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/turtle_soup.py:sweep_frame
  - swingbot/core/market/entry_filters.py:turtle_soup_entries
  - swingbot/core/backtesting/arms/turtle_soup_research.py:RESEARCH_CELL
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A long. A dip below a well-known recent low runs the stops parked under it; when price closes back above that low, the sellers are spent.

**Entry rule.**

- The bar trades below the lowest low of the recent channel, a low set some bars earlier.
- The same bar closes back above that low.
- The signal is read on the close of that bar, so it never uses a later bar.

**Where it fires.** Long only. The mask admits no cell, so it is masked: it is measured only in the long 2w research cell of the arms replay, and promotion is a later spec.

<details><summary>Under the hood</summary>

`turtle_soup.sweep_frame` with the frozen `CHANNEL` and `MIN_AGE`; `entry_filters.turtle_soup_entries` returns nothing while masked; research cell `arms/turtle_soup_research.RESEARCH_CELL`.

</details>
