---
strategy: "Elliott Wave"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:elliott_wave_entries
  - swingbot/core/market/indicators.py:elliott_wave3_entries
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A mechanical stand-in for the start of an Elliott third wave: after a first impulse and a corrective second wave, price breaks back past the first wave's extreme.

**Entry rule.**

- Three swing pivots mark wave 1 and wave 2, and the bar breaks past the wave-1 extreme.
- Wave 2 retraced a textbook share of wave 1, stayed short of its origin and did not drag on too long.
- RSI is above its midline and rising, and the shared gates pass. Shorts mirror it.

**Where it fires.** The rule fires on the 4w horizon only; on every other horizon it returns no signal, so the wider opening of the mask reduces to 4w in practice.

<details><summary>Under the hood</summary>

`entry_filters.elliott_wave_entries` (returns nothing off `4w`); pivots from `indicators.elliott_wave3_entries` with the horizon's `max_risk_pct` as the pivot threshold; wave-2 depth and duration bounds in `DEFAULT_PARAMS["Elliott Wave"]`.

</details>
