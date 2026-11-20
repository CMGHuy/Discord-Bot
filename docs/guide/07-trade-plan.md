---
title: Building the trade plan
slug: trade-plan
order: 7
reviewed_for: 2.19.2
sources:
  - swingbot/core/planning/builders.py:build_confluence_plan
  - swingbot/core/planning/builders.py:build_strategy_plan
  - swingbot/core/planning/builders.py:scenario_is_breakout
  - swingbot/core/planning/builders.py:confluence_stop_geometry
  - swingbot/core/planning/builders.py:_clamp_stop_to_hard_cap
  - swingbot/core/planning/builders.py:CLAMP_HEADROOM_PCT
  - swingbot/core/planning/builders.py:_STRUCTURAL_BRANCHES
  - swingbot/core/planning/builders.py:_atr_branch
  - swingbot/core/planning/builders.py:_bounded_stop
  - swingbot/core/planning/builders.py:_confluence_tp2
  - swingbot/core/risk_limits.py:HARD_MAX_PLANNED_LOSS_PCT
  - swingbot/core/risk_limits.py:capped_planned_loss_pct
  - swingbot/core/scanning/gating.py:scenario_gate_inputs
  - swingbot/core/planning/stop_scope.py:stop_ceiling
  - swingbot/core/planning/stop_scope.py:plan_stop_ceiling
  - swingbot/core/planning/stop_scope.py:risk_sizing_ok
  - swingbot/core/planning/lifecycle.py:apply_level_lifecycle
  - swingbot/core/planning/lifecycle.py:pending_invalidated
  - swingbot/core/planning/targets.py:select_structural_target
  - swingbot/core/planning/targets.py:select_tp2
  - swingbot/core/planning/reward_floor.py:clears
  - swingbot/core/planning/params.py:TP1_FRACTION
  - swingbot/core/planning/params.py:RUNNER_FLOOR_FRACTION
  - swingbot/core/planning/params.py:TRAIL_ATR_MULT
  - swingbot/core/planning/params.py:DEFAULT_EXPIRY_BARS
  - swingbot/core/planning/params.py:PLAN_SHAPES
  - swingbot/core/planning/params.py:exit_params_for
  - swingbot/core/market/strategy_types.py:BREAKEVEN_TRIGGER_FRACTION
  - swingbot/core/planning/exit_sim.py:runner_floor
  - swingbot/core/planning/exit_sim.py:chandelier_stop
  - swingbot/core/planning/exit_sim.py:giveback_stop
  - swingbot/core/planning/exit_sim.py:tighter_stop
  - swingbot/core/planning/exit_sim_v2.py:simulate_exit_v2
  - swingbot/core/planning/plan_manager.py:PlanManager._step_pending
  - swingbot/core/planning/plan_manager.py:PlanManager._fill_pending
  - swingbot/core/planning/plan_manager.py:PlanManager._step_active
  - swingbot/core/planning/plan_manager.py:PlanManager._step_partial
  - swingbot/core/planning/plan_store.py:PlanStore.update
  - swingbot/core/scanning/analyze.py:attach_plan_v2
  - swingbot/core/edge/stops.py
  - swingbot/config.py:MIN_STOP_DISTANCE_PCT
  - swingbot/config.py:MAX_STOP_LOSS_PCT
  - swingbot/config.py:CLAMP_STOP_TO_HARD_CAP
  - swingbot/config.py:MIN_RISK_REWARD_RATIO
  - swingbot/config.py:MAX_RISK_REWARD_RATIO
  - swingbot/config.py:MIN_REWARD_PCT
  - swingbot/config.py:STRUCTURAL_STOP_SCOPE
  - swingbot/config.py:RUNNER_GIVEBACK_ENABLED
  - swingbot/config.py:DATA_DRIVEN_STOPS_ENABLED
  - swingbot/config.py:PLAN_ENGINE_V2
---

> **In plain words** A trade plan is the full set of numbers an alert carries: where to get in, where the idea is wrong (the stop), where to take profit (one or two targets), and how the stop follows the trade once it moves your way. The stop comes from the chart, is never further from the entry than a fixed cap, and never moves against you after entry. A target must pay enough for the risk taken, or there is no trade at all.

## Entry

A plan enters in one of three ways (see [entry](/insights/guide/glossary#entry)):

| Entry | When | Fills |
|---|---|---|
| market | the setup is already in place | at the price the scan saw |
| stop entry | the target lies beyond the recent trading range, so the trade needs a breakout | when price trades through the trigger |
| limit | a few strategies buy a pullback or sell a rally | when price comes back to the limit |

A stop-entry or limit plan waits. A level plan that has not filled within {{plan.expiry_bars}} is cancelled as expired; some strategy plans carry a shorter window. A waiting plan is also cancelled when price trades through its stop before the entry fires (the idea broke before the trade began), and when the fill itself would leave the stop further away than [the stop-distance cap](#the-stop-distance-cap-and-the-clamp) allows.

<details><summary>Under the hood</summary>

`builders.scenario_is_breakout` gives a level plan a stop entry when reaching its target needs a new extreme of the recent range; every other level plan is a market plan. Strategy plans take their entry type and waiting window from `params.PLAN_SHAPES` or its defaults. A waiting plan is stepped by `PlanManager._step_pending` (expiry, then `lifecycle.pending_invalidated`); `PlanManager._fill_pending` cancels with reason `risk_cap` when the planned loss from the fill exceeds `stop_scope.plan_stop_ceiling`. The setting that makes market plans wait for the next open is in [chapter 6](/insights/guide/gates#post-signal-fill-vetoes).

</details>

## The stop

The [stop](/insights/guide/glossary#stop) is where the trade idea is wrong, so it comes from the chart, never from a fixed percentage:

- **Level plans** put it beyond the level the setup leans on: the nearest support under a long, the nearest resistance over a short ([chapter 4](/insights/guide/levels#the-next-level-idea)). A level setup whose stop sits closer than {{MIN_STOP_DISTANCE_PCT}} to the entry is inside ordinary daily noise and is dropped before it is scored.
- **Strategy plans** use the structure the strategy reads (a swing point, a Fibonacci level, a broken range) for Fibonacci, Support/Resistance, Elliott Wave and the research strategies, and a multiple of the average true range (ATR), set per horizon, for every other strategy. Level-lifecycle stops are {{LEVEL_LIFECYCLE_STOPS_ENABLED}}; when on, a strategy plan's stop then moves beyond a tested level ([chapter 4](/insights/guide/levels#touch-break-and-the-four-states)).

Stops sized from how far past winners moved against their entry exist in the code and were not adopted ([chapter 6](/insights/guide/gates#measured-not-used)).

<details><summary>Under the hood</summary>

Level stops come from `levels.build_scenarios(..., min_stop_distance_pct=MIN_STOP_DISTANCE_PCT)`. Strategy stops: `builders._STRUCTURAL_BRANCHES` names the structural strategies, and `builders._atr_branch` serves the rest with the horizon's `atr_stop_multiple`; `lifecycle.apply_level_lifecycle` makes the move while `LEVEL_LIFECYCLE_STOPS_ENABLED` is set. `edge/stops.py` holds the MAE-informed helpers used only with `DATA_DRIVEN_STOPS_ENABLED`; it builds no stop.

</details>

## The stop-distance cap and the clamp

The distance from entry to stop, as a share of the entry price, has a hard cap of {{stop.hard_cap}} ([stop-distance cap](/insights/guide/glossary#stop-distance-cap)). The cap is a constant in the code, not a setting. The settings page caps the maximum stop distance (now {{MAX_STOP_LOSS_PCT}}) at that same value, and whatever the setting reads, the hard cap ({{stop.hard_cap}}) still binds when the plan is built and filled. Setups are first admitted with the horizon's own, wider stop ceiling, so that historical replays see the same candidates; the cap is applied when the plan is built.

A level plan whose stop lies beyond the cap is [clamped](/insights/guide/glossary#clamp) while the clamp setting is {{CLAMP_STOP_TO_HARD_CAP}}: its stop moves in to {{stop.clamp_level}} from the entry, a little inside the cap, so a fill slightly past the trigger is still allowed. The target is then chosen again against the smaller risk, and if no level pays enough the setup is dropped. Without the clamp such a plan is [rejected](/insights/guide/glossary#rejected-plan) with reason `risk_cap` and logged as `plan rejected (risk_cap, stop … from entry) -- not posted`.

A strategy plan whose stop lies beyond its ceiling has the stop moved in to the ceiling. A few research strategies whose stop is the structure itself, the shorts and Turtle Soup, keep their stop up to the horizon's own ceiling or are dropped, and must then size to a fixed dollar risk; their [cards](/insights/guide/strategies#the-cards) say whether they can fire live.

Live, the cap is checked once more at the fill: a fill far enough past the trigger to put the stop beyond the ceiling cancels the plan (`risk_cap`).

<details><summary>Under the hood</summary>

`risk_limits.HARD_MAX_PLANNED_LOSS_PCT` is the cap; `capped_planned_loss_pct` takes the stricter of it and a configured value. Scenario admission uses the larger of `MAX_STOP_LOSS_PCT` and the horizon's `max_risk_pct` (`gating.scenario_gate_inputs`). The clamp is `builders._clamp_stop_to_hard_cap` (cap minus `CLAMP_HEADROOM_PCT`), called through `confluence_stop_geometry`; `analyze.attach_plan_v2` rejects a plan past `stop_scope.plan_stop_ceiling` as `risk_cap`. Strategy stops pass `builders._bounded_stop`, which caps or drops by `stop_scope.stop_ceiling` (`STRUCTURAL_STOP_SCOPE` can add pairs to the drop group); `stop_scope.risk_sizing_ok` enforces the fixed dollar risk.

</details>
