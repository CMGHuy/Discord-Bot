---
title: Finding levels and setups
slug: levels
order: 4
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/levels.py:ALL_STRATEGY_FAMILIES
  - swingbot/core/market/levels.py:CLUSTER_TOLERANCE_PCT
  - swingbot/core/market/levels.py:collect_candidate_levels
  - swingbot/core/market/levels.py:count_confirming_strategies
  - swingbot/core/market/levels.py:build_level_map
  - swingbot/core/market/levels.py:build_scenarios
  - swingbot/core/market/levels_lifecycle.py:classify_levels
  - swingbot/core/market/levels_lifecycle.py:preferred_stop_anchor
  - swingbot/core/market/mtf.py:adjacent_aligned
  - swingbot/core/market/mtf.py:horizon_trend
  - swingbot/core/market/levels.py:atr_floor_pct
  - swingbot/core/scanning/strategy_pass.py:completed_frame
  - swingbot/core/scanning/analyze.py:_horizon_scenarios
  - swingbot/core/scanning/requirements.py:_build_requirement_checks
  - swingbot/core/scanning/confidence.py
  - swingbot/core/scanning/dedup.py:dedup_scan_items
  - swingbot/core/planning/lifecycle.py:apply_level_lifecycle
  - swingbot/config.py:AVWAP_LEVELS_ENABLED
  - swingbot/config.py:MIN_REWARD_PCT
  - swingbot/config.py:MIN_STOP_DISTANCE_PCT
  - swingbot/config.py:MIN_RISK_REWARD_RATIO
  - swingbot/config.py:MAX_STOP_LOSS_PCT
  - swingbot/config.py:CONFLUENCE_DEVIATION_PCT
  - swingbot/config.py:MIN_TARGET_CONFLUENCE_COUNT
  - swingbot/config.py:MIN_ALERT_CONFIDENCE_LEVEL
  - swingbot/config.py:SIGNAL_CONFIRMATION_SCANS
  - swingbot/config.py:DEDUP_TOLERANCE_PCT
  - swingbot/config.py:HTF_CONFLUENCE_ENABLED
  - swingbot/config.py:MTF_ADJACENT_GATE
  - swingbot/config.py:LEVEL_LIFECYCLE_STOPS_ENABLED
---

> **In plain words** The bot looks for prices where a stock has turned before: support below today's price, resistance above it. It plans a trade from today's price toward the next one. A level counts for more when several independent methods agree on it, only finished daily bars decide a signal, and a setup must promise a big enough move before it is considered at all.

## The next-level idea

Every scan starts from today's price, one ticker and one horizon at a time. Below the price sit [support](/insights/guide/glossary#support-and-resistance) levels, above it resistance. A long [scenario](/insights/guide/glossary#scenario) aims at the nearest resistance, with its stop at the nearest support; a short does the reverse. Both directions are tried every time, and either, both or neither may qualify.

The bot never invents a level. With no real support or resistance on one side there is no stop or no target, and the scenario is not built. Quiet days without alerts are the expected result of that rule, not a fault. Where this step sits in the whole scan is shown in [the pipeline](/insights/guide/pipeline).

<details><summary>Under the hood</summary>

`levels.build_level_map` clusters the candidate levels and returns supports below and resistances above the current price, nearest first. `levels.build_scenarios` builds at most one scenario per direction from them. Both run once per ticker and horizon inside `analyze._horizon_scenarios`.

</details>

## Level families

A [level family](/insights/guide/glossary#level-family) is one method of drawing price levels. The live list:

{{levels.families}}

Families are not the strategies of [chapter 5](/insights/guide/strategies#strategies-are-not-level-families). A family only draws prices; a strategy is an entry rule with its own measured record. A few names appear in both lists, such as VWAP, Volume Profile and Fibonacci, because the same idea can be used either way.

<details><summary>Under the hood</summary>

`levels.collect_candidate_levels` runs every family and labels each candidate with its source. `levels.strategy_family` folds the labels back into `ALL_STRATEGY_FAMILIES`, so the several anchors of an anchored VWAP still count as one AVWAP family. AVWAP candidates exist only while `AVWAP_LEVELS_ENABLED` is on.

</details>

## Confluence counts families

Candidates that sit within {{CLUSTER_TOLERANCE_PCT}} of each other merge into one [level](/insights/guide/glossary#level), at their average price. The [confluence](/insights/guide/glossary#confluence) of a target is then measured in a second, looser pass: how many distinct families put their own level within {{CONFLUENCE_DEVIATION_PCT}} of it. Each family counts once, however many lines it draws: several Fibonacci ratios near one price are one vote, not several.

A scenario needs at least {{MIN_TARGET_CONFLUENCE_COUNT}} families on its target to be posted. It is scored either way, and a miss shows up as a failed requirement. The same count, capped, is the starting point of the alert's [confidence](/insights/guide/glossary#confidence) level, so the filter and the score never disagree about how many families agree. Only alerts at confidence level {{MIN_ALERT_CONFIDENCE_LEVEL}} or higher are posted.

<details><summary>Under the hood</summary>

`levels._cluster_levels` merges candidates with `CLUSTER_TOLERANCE_PCT`. `levels.count_confirming_strategies(..., tolerance_pct=CONFLUENCE_DEVIATION_PCT)` runs for the target and again for the stop: the target count feeds the requirement `min_confluence` (`requirements._build_requirement_checks`) and step 1 of `scanning/confidence.py`; the stop count feeds a quality factor.

</details>

## Bonus confirmations

Two signals raise confidence but add no level: a volatility squeeze that breaks out on volume, and a candlestick reversal pattern. Neither can be measured against a target price, so neither counts as a family or moves a level. A squeeze that has not broken out yet earns only half credit. Both signals do add a label to the scenario's list of sources, so you may see them named on an alert.

<details><summary>Under the hood</summary>

Both are scored in `scanning/confidence.py`. `levels._STRATEGY_FAMILY_PREFIXES` maps their labels to "Volatility Squeeze" and "Candlestick Pattern", names deliberately absent from `ALL_STRATEGY_FAMILIES`.

</details>

## Touch, break and the four states

A level is judged by what price has done to it, on finished bars only. That record is the [level lifecycle](/insights/guide/glossary#level-lifecycle):

- **Touch**: a bar reaches the level or comes within {{levels.touch_atr}} of it. Its close may cross the level by at most that same tolerance.
- **Break**: a bar closes beyond the level by more than {{levels.break_atr}}.

| State | Meaning |
|---|---|
| fresh | never touched in the look-back window |
| tested | touched and held, recently |
| delivered | the latest decisive event was a break: price went through |
| decaying | touched and held, but not for a long time |

The most recent event wins, so a level that broke and was later touched and held again is no longer delivered. Level-lifecycle stops are {{LEVEL_LIFECYCLE_STOPS_ENABLED}}: when on, a plan's [stop](/insights/guide/glossary#stop) moves beyond a tested level instead of sitting inside the noise around a fresh one, and the target is chosen again against the wider risk. The stop only ever widens, and never past the plan's stop ceiling. If no target then pays enough, the original stop and target are kept. [Chapter 7](/insights/guide/trade-plan#the-stop) covers stops in full.

<details><summary>Under the hood</summary>

`levels_lifecycle.classify_levels(df, i, levels, horizon_key=...)` slices the frame to bar `i` before reading it. The window is the horizon's `sr_lookback` times `WINDOW_LOOKBACK_MULT` bars; a level decays after `sr_lookback` times `DECAY_LOOKBACK_MULT` bars without a touch. `preferred_stop_anchor` ranks tested over decaying over fresh and never returns a delivered level. The stop move is `planning/lifecycle.apply_level_lifecycle`, which acts only on a tested anchor.

</details>

## Higher-horizon alignment

Each horizon has its own trend, read from its fast and slow moving averages. Two checks compare a setup with a longer view:

- **Higher-timeframe bias** ({{HTF_CONFLUENCE_ENABLED}}): a counter-trend setup is flagged on the alert and in the plan's quality score. It never removes an alert or lowers its confidence.
- **Adjacent-horizon alignment**: drops a scenario when the next horizon up trends against it. The longest horizon is exempt, and so is a setup whose next horizon up has too little history to read a trend; neither is ever counted as agreement. Whether the live scan applies it is listed in [chapter 6](/insights/guide/gates#higher-horizon-alignment), read from its setting.

<details><summary>Under the hood</summary>

`mtf.adjacent_aligned(df, horizon_key, direction)` returns `aligned`, `opposed` or `exempt`; `mtf.horizon_trend` compares the horizon's `ema_fast` with its `ema_slow`. The drop is guarded by `MTF_ADJACENT_GATE`. The bias flag is `HTF_CONFLUENCE_ENABLED`, informational by design.

</details>

## Closed bars only

A daily bar is final only after its session closes. Strategy signals read [completed bars](/insights/guide/glossary#completed-bar) only: during the trading session the still-forming bar is dropped, so the live scan sees the bars a backtest of that day would see. Levels are measured against the current price, so a setup must also appear the same way on {{SIGNAL_CONFIRMATION_SCANS}} consecutive scans before it is confirmed, which filters out intraday flicker.

<details><summary>Under the hood</summary>

`strategy_pass.completed_frame(df, now)` removes only today's bar, and only during the regular session. `SIGNAL_CONFIRMATION_SCANS` drives the confirmation debounce in `scanning/scan_run.py`; in a replay one scan runs per completed bar, so the count is in daily bars there.

</details>

## The minimum move

A scenario is built only when it clears hard requirements, with no "close enough":

- The first target is at least {{MIN_REWARD_PCT}} away from today's price. Longer horizons raise this floor from their own target scale; they never lower it.
- When no ATR band is in force (the band replaces these two checks), the stop is at least {{MIN_STOP_DISTANCE_PCT}} from the entry, so ordinary noise does not reach it, and no further than the horizon's own stop limit. The tighter caps a plan must then meet are in [chapter 7](/insights/guide/trade-plan#the-stop-distance-cap-and-the-clamp).
- The first target pays at least {{MIN_RISK_REWARD_RATIO}} [reward to risk](/insights/guide/glossary#reward-to-risk-rr).

<details><summary>Under the hood</summary>

`analyze._horizon_scenarios` uses the larger of `MIN_REWARD_PCT` and a fixed share of the horizon's `sr_target_min_pct` as the reward floor, and the larger of `MAX_STOP_LOSS_PCT` and the horizon's `max_risk_pct` as the stop limit; `levels.atr_floor_pct` adds a volatility floor under the stop distance. `requirements._build_requirement_checks` records which checks a scenario passed for the requirement table.

</details>

## Duplicate merge

Several horizons can point at almost the same trade. Before alerts post, plans on the same ticker and direction whose entry, stop and target all lie within {{DEDUP_TOLERANCE_PCT}} of each other merge into one alert. The plan with the highest confidence score is kept, and the alert lists what it absorbed.

<details><summary>Under the hood</summary>

`dedup.dedup_scan_items` groups items by ticker and direction, clusters them with `_plans_similar`, keeps the highest `conf.score` and records the others in `combined_from`.

</details>
