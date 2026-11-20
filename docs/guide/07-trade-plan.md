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
  - swingbot/core/planning/exit_sim.py:giveback_level
  - swingbot/core/planning/plan_types.py:breakeven_trigger
  - swingbot/core/market/levels.py:MAX_TARGET2_LEG_MULTIPLE
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

## The stop never widens

Once a plan is open, its stop only moves toward profit: to the entry after the break-even trigger, to the runner floor at TP1, then by the trail and the give-back stop. Each move takes the tighter of the old and the new stop, and the plan store refuses any write that would loosen the stop of an open plan.

A stop is not a guaranteed exit price. A gap can open beyond it, and the loss is then worse than one [R](/insights/guide/glossary#r-multiple) ([gap through the stop](/insights/guide/glossary#gap-through-the-stop)). Risk and size are still computed to the stop ([chapter 8](/insights/guide/sizing-risk#how-the-share-count-is-found)).

<details><summary>Under the hood</summary>

`exit_sim.tighter_stop` picks the tighter of two runner stops; a missing term never loosens. `PlanStore.update` takes the plan row lock, refuses a stale write over a closed plan and never loosens the stop of an ACTIVE or PARTIAL plan.

</details>

## Targets that pay for the risk

TP1 is the nearest real level beyond the entry whose [reward-to-risk](/insights/guide/glossary#reward-to-risk-rr) is at least {{MIN_RISK_REWARD_RATIO}}. If the nearest such level's reward-to-risk is above {{MAX_RISK_REWARD_RATIO}}, TP1 is placed at exactly that ratio and the real level stays available as TP2. If no level pays enough there is no plan: there is no fallback target. Before any of this, a level setup's target must be at least {{MIN_REWARD_PCT}} away ([the minimum move](/insights/guide/levels#the-minimum-move)).

Level plans choose from the whole level map. Strategy plans choose from their own levels (Fibonacci levels, the broken range, or a ladder of ATR steps) and must also clear their horizon's reward floor.

[TP2](/insights/guide/glossary#tp1-and-tp2) is the next level beyond TP1, left unset when it lies too far past TP1. A strategy plan has a TP2 only when its strategy's measured exit settings use one, or when the strategy carries its own second-target multiple; the others let the runner ride on its trailing stop alone.

<details><summary>Under the hood</summary>

`targets.select_structural_target(entry, stop, is_bull, candidates, min_rr, max_rr)` serves live and backtest alike; `targets.select_tp2` and `builders._confluence_tp2` pick TP2, bounded by `levels.MAX_TARGET2_LEG_MULTIPLE`. `params.exit_params_for(strategy)["tp2"]` reads the frozen TRAIN-grid table `EXIT_V2_PARAMS`; `reward_floor.clears` is the strategy reward floor.

</details>

## Scale-out and the runner

Before TP1, once price has covered {{plan.breakeven_trigger}} of the way to TP1, the stop moves to the entry; a stop hit after that closes the trade as a scratch.

At TP1 the plan closes {{plan.tp1_share}} of the position ([scale-out](/insights/guide/glossary#scale-out)); a plan whose TP1 share is the whole position closes in full at TP1. The rest is the [runner](/insights/guide/glossary#runner), and its stop moves at once to the runner floor, which locks in {{plan.runner_floor}} of the move from entry to TP1.

After TP1 the runner's stop is the tightest of three: the floor; a chandelier trail {{plan.trail_atr}} behind the best price since TP1 (a strategy plan may use its own measured multiple); and, while the setting `RUNNER_GIVEBACK_ENABLED` is set, a give-back stop a set share below the best price. The runner closes at TP2 when there is one, otherwise when its stop is hit. A stall exit and a runner structure exit were measured and not adopted ([chapter 6](/insights/guide/gates#measured-not-used)).

<details><summary>Under the hood</summary>

`PlanManager._step_active` moves the stop to entry at `breakeven_trigger` (`BREAKEVEN_TRIGGER_FRACTION` unless the plan shape sets its own), closes `tp1_fraction` (`TP1_FRACTION`) at TP1 and sets `working_stop = exit_sim.runner_floor(entry, tp1)` (`RUNNER_FLOOR_FRACTION`). `PlanManager._step_partial` applies the give-back (`exit_sim.giveback_stop`) and ratchets the chandelier (`exit_sim.chandelier_stop`, `TRAIL_ATR_MULT` or the strategy's `exit_params_for` value) through `tighter_stop`.

</details>

## How a plan closes

Most plans end in one of these [plan states](/insights/guide/glossary#plan-states). A limit plan whose cancel level is reached while it waits is also cancelled (`limit_cancelled`).

| Outcome | When |
|---|---|
| expired | a waiting plan did not fill in time |
| invalidated | price closed through the stop before the entry fired |
| cancelled at the cap | the fill would have left the stop beyond the cap (`risk_cap`) |
| gap through the stop | a limit order would have filled at or beyond the stop, so nothing opened |
| loss | the stop was hit before the break-even move |
| scratch | the stop was hit at the entry, after the break-even move |
| TP1, runner at the floor | the runner's stop fired at the runner floor |
| TP1, runner trailed | the trail or the give-back stop closed the runner |
| TP1, then TP2 | the runner reached the second target |

A plan whose TP1 share is the whole position closes in full at TP1; every other plan keeps a runner after it.

<details><summary>Under the hood</summary>

Close reasons as stored: `expired`, `invalidated`, `limit_cancelled`, `risk_cap`, `gap_through_stop`, `loss`, `scratch`, `tp1_runner_be`, `tp1_runner_trail`, `tp1_runner_tp2`. The plan manager steps every open plan on its regular live-price poll.

</details>

## Backtest and live use the same plan

The backtest builds its plan directly from the same shared shape, target and exit helpers that the live plan uses: the stops, the clamp, the targets, the runner floor and the give-back stop. Only the strategy-engine arm and the armed replay call the two plan builders themselves. So a backtest measures the plan an alert would carry. The backtest walk reads daily bars: a gap fills at the open in either direction, on a bar that touches both the stop and a target the stop is taken first, costs are booked once per trade, and a trade still open at the horizon's longest hold is closed there. Live reads a price poll, so live fills can differ: better on a gap toward the target, worse on a gap through the stop.

Everything in this chapter describes the plan engine setting `on`; it is now {{PLAN_ENGINE_V2}}.

<details><summary>Under the hood</summary>

`build_strategy_plan` and `build_confluence_plan` build the plan in the scan and in the strategy-engine and armed-replay arms; the older single-strategy backtest loop assembles the same plan shape with the shared helpers (`plan_shape_for`, `select_structural_target`, `exit_params_for`). The walk is `exit_sim_v2.simulate_exit_v2` (instrument v2: fills and costs from `backtesting/instrument/`), with the horizon's `max_holding_days` as its hold cap.

</details>
