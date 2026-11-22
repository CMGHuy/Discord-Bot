---
title: The scan pipeline, end to end
slug: pipeline
order: 3
reviewed_for: 2.19.2
sources:
  - swingbot/core/scanning/scan_run.py:run_scan
  - swingbot/core/scanning/analyze.py:_scan_one
  - swingbot/core/scanning/fetch.py
  - swingbot/core/market/levels.py:collect_candidate_levels
  - swingbot/core/market/levels.py:_cluster_levels
  - swingbot/core/market/levels.py:build_scenarios
  - swingbot/core/market/levels.py:ALL_STRATEGY_FAMILIES
  - swingbot/core/market/levels.py:CLUSTER_TOLERANCE_PCT
  - swingbot/core/scanning/dedup.py:dedup_scan_items
  - swingbot/core/scanning/strategy_pass.py:run_strategy_pass
  - swingbot/core/scanning/strategy_pass.py:strategy_signals
  - swingbot/core/scanning/regime.py:get_market_regime
  - swingbot/core/scanning/regime.py:get_htf_bias
  - swingbot/core/scanning/analyze.py:veto_bullish_for
  - swingbot/core/scanning/analyze.py:_apply_headroom
  - swingbot/core/scanning/analyze.py:attach_plan_v2
  - swingbot/core/scanning/analyze.py:_reject_plan
  - swingbot/core/scanning/analyze.py:monitor_open_only
  - swingbot/core/scanning/gating.py:passes_confluence
  - swingbot/core/market/strategy_types.py:admits
  - swingbot/core/planning/builders.py:build_confluence_plan
  - swingbot/core/planning/builders.py:build_strategy_plan
  - swingbot/core/planning/account.py
  - swingbot/core/edge/heat.py:heat_check
  - swingbot/core/edge/correlation.py:cluster_check
  - swingbot/core/scanning/alert_embeds.py
  - swingbot/core/tracking/performance.py:TradeLog.update_open_trades
  - swingbot/core/planning/plan_manager.py:PlanManager.poll
  - swingbot/core/planning/plan_engine.py
  - swingbot/config.py:SCAN_UNIVERSE
  - swingbot/config.py:STRATEGY_ALERTS_MODE
  - swingbot/config.py:SIGNAL_CONFIRMATION_SCANS
  - swingbot/config.py:CLAMP_STOP_TO_HARD_CAP
  - frontend/src/app/workspaces/guide/pipeline-diagram.ts:GuidePipelineDiagram
---

> **In plain words** Every few minutes the bot looks at every stock on its list. For each one it draws the price levels that matter, checks whether a trade toward the next level makes sense, runs the idea past a set of filters, works out a size that keeps the possible loss small, and posts the plan. Then it watches the trade until it closes.

<!-- figure:pipeline -->

Each box is one stage below, in order. A box becomes a link to the chapter that explains it in depth once that chapter is written.

## Watchlist

The scan starts from the [watchlist](/insights/guide/glossary#watchlist-and-universe): the tickers you follow, edited on the Watchlist page. A setting can add a wider universe (for example S&P 500 names or ETFs) on top; the watchlist is always included. Scans run on a fixed interval while the bot is up, and every scan does two jobs: it looks for new trades, and it checks every open paper trade.

## Price data

For each ticker the bot loads daily bars (open, high, low, close, volume) from its local store first and fetches only what is missing. Each ticker is loaded once per scan, and every later stage reads that same copy. A ticker that trades too thinly, or whose data look broken, is dropped here, before any analysis.

## Levels from every method

For each horizon the bot asks every [level family](/insights/guide/glossary#level-family) where support and resistance sit:

{{levels.families}}

Each family proposes candidate prices. A method that fails on one ticker is skipped; the others still count.

## Duplicate merge

Candidates closer together than {{CLUSTER_TOLERANCE_PCT}} merge into one [level](/insights/guide/glossary#level). A level's [confluence](/insights/guide/glossary#confluence) is the number of different families behind it, not the number of raw candidates, so one method that draws three lines at the same price counts once. Later in the scan, when one ticker produces near-identical plans in the same direction (for example on two horizons), only the plan with the highest confidence is posted.

## Setups and strategy signals

A setup is found in one of two ways.

### Confluence scenarios

From the current price the bot builds two [scenarios](/insights/guide/glossary#scenario): long toward the next resistance above, and short toward the next support below. A scenario survives only if it clears every hard requirement: a first target far enough away to be worth the trade, a stop neither too tight nor too wide, and enough reward for the risk. The level it trades from needs enough confluence to count at all.

### Strategy signals

Separately, each registered [strategy](/insights/guide/glossary#strategy) checks its own entry rule on the last [completed daily bar](/insights/guide/glossary#completed-bar), with the same functions its backtests are measured with. A setting switches this path between three modes: off; shadow, where plans are built and recorded but never alerted or traded; and live.

## Gates

[Gates](/insights/guide/glossary#gate) are filters a setup must pass. The [market regime](/insights/guide/glossary#market-regime) and each ticker's longer-term trend are read once per scan for the gates that need them. A strategy may be allowed only long, only short, or only on some horizons; a masked cell never alerts. Strategy plans also face a [relative strength](/insights/guide/glossary#relative-strength) check. Two further gates are built but switched off by default (`HEADROOM_SCOPE`, `DEAD_CAT_BOUNCE_VETO`): one would drop confluence scenarios when another level blocks the path to the first target, the other would block longs on a dead-cat bounce. Finally a signal must appear on enough consecutive scans to be confirmed, which filters out intraday flicker.

## Plan construction

A setup that passes becomes a [trade plan](/insights/guide/glossary#trade-plan). For a confluence setup, TP1 is a real level on the chart: the nearest one that pays at least the minimum [reward to risk](/insights/guide/glossary#reward-to-risk-rr). If none does, no plan is built; the bot never invents a target from a fixed multiple of the risk. A strategy plan is built under the same conditions its backtest used, so a live plan and a backtested one follow the same rules. Most plans scale out: part of the position closes at TP1 and the [runner](/insights/guide/glossary#runner) aims for TP2. Some strategies run with TP2 switched off and close the whole position at TP1.

## Sizing and caps

The size comes from the risk: the distance from entry to [stop](/insights/guide/glossary#stop), and how much one trade may lose. Three separate limits apply.

- The stop may sit at most {{MAX_STOP_LOSS_PCT}} from the entry (the [stop-distance cap](/insights/guide/glossary#stop-distance-cap)). A stop further away is clamped to that distance or the plan is dropped; clamping is {{CLAMP_STOP_TO_HARD_CAP}}.
- The sizing mode is {{POSITION_SIZING_MODE}}. In the fixed-risk mode one trade loses at most {{RISK_PER_TRADE_PCT}} of the account at its stop ([risk per trade](/insights/guide/glossary#risk-per-trade)).
- The [dollar risk cap](/insights/guide/glossary#dollar-risk-cap) limits the planned loss at the stop when enabled. Current setting is {{MAX_RISK_AMOUNT_ABSOLUTE}}.

Then the open book is checked. When the new trade would push [portfolio heat](/insights/guide/glossary#portfolio-heat) over {{PORTFOLIO_HEAT_CAP_PCT}}, or put more than {{CORRELATED_HEAT_CAP_PCT}} of risk into one group of stocks that move together ([correlated heat](/insights/guide/glossary#correlated-heat)), the alert still posts, flagged, with a suggested size of zero.

So a plan ends this stage in one of three ways: **rejected** (logged as `plan rejected (` and never posted), **clamped** (posted with the stop moved in to the cap), or posted as a **size-0 alert** ([size-0 alert](/insights/guide/glossary#size-0-alert)) that shows what the cap cost.

## Alert

The plan is posted with its chart, and a paper trade is opened from it. [Where alerts appear](/insights/guide/what-it-is#where-alerts-appear) lists the Discord channels and the admin pages.

## Monitoring

Every scan checks each open paper trade against the newest bars and the live quote, pre-market and after-hours included, so a stop or target hit during the day is caught at once rather than at the next daily close. Trades on tickers not scanned for new entries that day are still checked. When price comes near the stop or a target, a notice goes to Discord.

## Close

A trade closes at its stop, at its targets (part at TP1, the rest at TP2 or on its trailing stop), or when it runs out of time for its horizon. A plan moves from PENDING (waiting for its entry) to ACTIVE, to PARTIAL after TP1, and to CLOSED; one whose entry never fills is CANCELLED. The result is recorded in [R](/insights/guide/glossary#r-multiple), the profit or loss as a multiple of the risk taken. When the price gaps past the stop overnight, the fill is worse than −1R ([gap through the stop](/insights/guide/glossary#gap-through-the-stop)).

<details><summary>Under the hood</summary>

All paths are under `swingbot/core/`.

| Stage | Code |
|---|---|
| Scan run | `run_scan` (`scanning/scan_run.py`) runs the pipeline in a worker thread; per ticker `_scan_one` (`scanning/analyze.py`) |
| Price data | `scanning/fetch.py`, cache first, one crawl per scan |
| Levels | `collect_candidate_levels` (`market/levels.py`) |
| Merge | `_cluster_levels(candidates, tolerance_pct=CLUSTER_TOLERANCE_PCT)`; `dedup_scan_items` (`scanning/dedup.py`) |
| Scenarios | `build_scenarios` (`market/levels.py`); `passes_confluence` (`scanning/gating.py`) |
| Strategy signals | `run_strategy_pass`, `strategy_signals` (`scanning/strategy_pass.py`); setting `STRATEGY_ALERTS_MODE` |
| Gates | `get_market_regime`, `get_htf_bias` (`scanning/regime.py`); `veto_bullish_for`, `_apply_headroom` (`scanning/analyze.py`); `admits` (`market/strategy_types.py`); setting `SIGNAL_CONFIRMATION_SCANS` |
| Plan | `build_confluence_plan`, `build_strategy_plan` (`planning/builders.py`); `attach_plan_v2` (`scanning/analyze.py`) |
| Sizing and caps | `planning/account.py`; `heat_check` (`edge/heat.py`); `cluster_check` (`edge/correlation.py`); rejects through `_reject_plan` |
| Alert | `scanning/alert_embeds.py` |
| Monitoring | `TradeLog.update_open_trades` (`tracking/performance.py`); `monitor_open_only`; `PlanManager.poll` (`planning/plan_manager.py`) |
| Close | plan states in `planning/plan_engine.py` |

</details>
