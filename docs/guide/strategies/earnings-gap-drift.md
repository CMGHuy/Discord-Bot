---
strategy: "Earnings Gap Drift"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/short_entries.py:gap_drift_frame
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short. After earnings, a large gap down that fails to recover often keeps drifting lower for days.

**Entry rule.**

- The reaction session to an earnings report opened with a large gap down.
- On the next session the close is still below the close of the reaction day.
- The stop sits a small ATR buffer above the high of the reaction day.

**Where it fires.** Short only; the rule ignores the horizon and needs the earnings calendar. The mask admits no cell, so it is masked: research only until its holdout test passes.

<details><summary>Under the hood</summary>

`short_entries.gap_drift_frame`; minimum gap size in `DEFAULT_PARAMS["Earnings Gap Drift"]`; no signal without the `evt_reaction` column.

</details>
