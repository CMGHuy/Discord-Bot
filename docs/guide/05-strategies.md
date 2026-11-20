---
title: Strategies
slug: strategies
order: 5
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/strategy.py:STRATEGY_FUNCS
  - swingbot/core/market/strategy_types.py:STRATEGY_GATES
  - swingbot/core/market/strategy_types.py:MASKED_BY_DEFAULT_HORIZONS
  - swingbot/core/market/strategy_types.py:admits
  - swingbot/core/market/strategy_types.py:live_horizons
  - swingbot/core/market/entry_filters.py:ENTRY_FUNCS
  - swingbot/core/market/entry_filters.py:entries_for
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/entry_filters.py:gate_override
  - swingbot/core/scanning/strategy_pass.py:completed_frame
  - swingbot/core/scanning/strategy_pass.py:strategy_signals
  - swingbot/core/scanning/strategy_pass.py:run_strategy_pass
  - swingbot/core/scanning/scan_run.py:_maybe_run_strategy_pass
  - swingbot/core/planning/builders.py:build_strategy_plan
  - swingbot/core/planning/params.py:stamp_badge
  - swingbot/core/planning/stop_scope.py:risk_sizing_ok
  - swingbot/core/backtesting/registry.py:Badge
  - swingbot/core/backtesting/registry.py:get_badge
  - swingbot/admin/guide/live_strategies.py:badge_line
  - swingbot/config.py:STRATEGY_ALERTS_MODE
  - swingbot/config.py:STRATEGY_ALERTS_LIVE_STRATEGIES
---

> **In plain words** A strategy is a fixed entry rule, such as "the fast average crosses above the slow one", checked on the last finished daily bar. Each one has been measured on years of past prices, and its card below shows that record: how often it won, what it made per unit of risk, how many trades the figures rest on and when they were measured. Some strategies are kept for research only and cannot alert; their cards say so.

## Strategies are not level families

The level families of [chapter 4](/insights/guide/levels#level-families) draw prices. A [strategy](/insights/guide/glossary#strategy) decides when to enter: its rule either fires on the last finished bar or it does not, and it has its own measured record, its [badge](/insights/guide/glossary#badge). A few names appear in both lists, such as VWAP, Volume Profile and Fibonacci, because the same idea can draw a level or time an entry; the two uses are measured separately.

The bot has two ways to reach an alert. A level alert starts from support and resistance and is the path the [pipeline](/insights/guide/pipeline) and chapter 4 describe. A strategy alert starts from one of the rules on this page, and it has its own switch, described next.

<details><summary>Under the hood</summary>

The registered strategies are the union of `strategy.STRATEGY_FUNCS` and `strategy_types.STRATEGY_GATES`; `entry_filters.ENTRY_FUNCS` maps each of them to its entry function. `entries_for(strategy, df, horizon_key)` runs that function, then applies the direction and horizon mask (`strategy_types.admits`) and the regime gate of chapter 6.

</details>

## How a strategy alert is sent

One setting decides what a fired rule does. The current setting: {{STRATEGY_ALERTS_MODE}}.

| Mode | What happens when a rule fires |
|---|---|
| off | the strategy pass does not run; every alert comes from the level path |
| shadow | a full trade plan is built and stored, nothing is posted |
| live | the plan is stored, posted as an alert and opened as a [paper trade](/insights/guide/glossary#paper-trade) |

Shadow mode collects evidence without posting ([shadow mode](/insights/guide/glossary#shadow-mode)). In live mode only strategies on the live list post; the current list: {{STRATEGY_ALERTS_LIVE_STRATEGIES}}. A ticker that already has an open trade gets no second one: the new plan is stored, not posted. A manual check from Discord never posts, whatever the mode.

Each scan the pass looks at every watchlist ticker on every live [horizon](/insights/guide/glossary#horizon), on finished daily bars only. During the session today's forming bar is dropped first, so a rule never fires on a bar that may still change (a [completed bar](/insights/guide/glossary#completed-bar)). One signal, meaning one ticker, strategy, horizon and bar, is stored once however many scans see it.

Between the signal and the alert sit a few checks. A short is dropped when the stock is not weak enough against the market (relative strength, chapter 6). Two vetoes, pullback volume and headroom, act only while their settings switch them on (chapter 6). The plan must exist: with no stop or no target that pays for the risk there is no alert (chapter 7). A plan that keeps a stop wider than the usual cap must also size to a fixed dollar risk, or it is not stored.

<details><summary>Under the hood</summary>

`scan_run._maybe_run_strategy_pass` reads `STRATEGY_ALERTS_MODE` and the allow-list `STRATEGY_ALERTS_LIVE_STRATEGIES` (empty means every strategy; the masked compression short must be named), forces shadow for a manual check, and calls `strategy_pass.run_strategy_pass` with `live_horizons()`. There `completed_frame` drops the forming bar, `strategy_signals` asks every entry function about the last bar, and `_emit_signal` runs `already_emitted`, the relative-strength laggard rule, the pullback dry-up veto, the compression-context check, `build_strategy_plan_at` (which calls `build_strategy_plan`), the headroom veto and `stop_scope.risk_sizing_ok`, in that order.

</details>

## Reading a card

Every card has the same parts:

- **Status**: `live`, or `masked — research only` when no direction is allowed on any live horizon.
- **Long / Short**: the horizons the mask allows for each direction: a list, "every live horizon", or "—" for none. Where the rule itself fires can be narrower, and the card body then says so under **Where it fires**.
- **Badge**: the tier (VALIDATED or WEAK), the expectancy in R and the win rate, then where the figures come from: the backtest window that produced them (a TRAIN-window refresh or the later validation window), N, the run date, "costs not recorded" (the registry does not store whether trading costs were in that run) and "before tax". A live strategy without a measured row shows "no registry row" instead of an empty badge.
- **Idea**, **Entry rule** and **Where it fires**: the rule in words, written from the code. A card never types a performance figure; those come only from the badge line.

Many entry rules end with "the shared gates pass". These are five market-condition checks most strategies require on the signal bar. For a short, the first two switch to downtrend versions (price below the long-term and medium-term averages, and the long-term average falling); the other three apply unchanged:

- **Uptrend**: price is above its long-term moving average, and that average is rising.
- **Medium-term trend**: price is above its medium-term moving average.
- **Not dead flat**: the average true range (ATR) is at least a minimum share of the price.
- **Not panicking**: the ATR is not far above its own recent average.
- **Real volume**: the bar's volume is not well below its recent average.

The dip-buying RSI rule uses a looser trend test and skips the medium-term one. Every other gate is in chapter 6.

A badge is a measurement of the past, not a forecast. Read it with its [expectancy (ExpR)](/insights/guide/glossary#expectancy-expr), its window ([TRAIN and validation](/insights/guide/glossary#train-and-validation)) and its [provenance label](/insights/guide/glossary#provenance-label): a high win rate on a small N, or a TRAIN-window figure, says much less than it seems to.

<details><summary>Under the hood</summary>

`live_strategies.badge_line` builds the badge line from `registry.get_badge("strategy", key)`: `Badge.window` decides the window label, and a row with `n == 0` and no run date counts as no row. A strategy plan is stamped with the same badge by `params.stamp_badge`. The shared gates are the `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm` and `vol_ok` series of `entry_filters.compute_shared_gates` (`bear_regime` and `trend50_bear` for shorts); their thresholds are `ATR_FLOOR_PCT`, `ATR_CALM_MULT` and `VOL_OK_MULT` in `entry_filters.py`. The RSI rule reads `bull_regime_slope_only` instead.

</details>

## Masked strategies

A [masked](/insights/guide/glossary#masked) strategy keeps its rule and its research but cannot fire live: its [direction mask](/insights/guide/glossary#direction-mask) allows no direction on any live horizon, so its card reads "masked — research only". The shortest horizon is masked for every strategy by default; [the horizon table](/insights/guide/what-it-is#swing-horizons) shows which horizons are live.

A masked strategy has no row in the badge registry, so its card says "no registry row — masked, research only" and never shows a WEAK badge with no trades behind it. Leaving the mask takes a pre-registered test on prices the strategy was never tuned on; until one passes, it stays research only.

<details><summary>Under the hood</summary>

`admits(strategy, direction, horizon_key)` checks the strategy's named research cells first, then `MASKED_BY_DEFAULT_HORIZONS`, then the `directions` and horizons in `STRATEGY_GATES`. A research measurement opens one cell for one run with `entry_filters.gate_override`; the live scan never does.

</details>

## The cards

One card per registered strategy, in name order. Status, horizons and badge are read live; the text comes from the checked card files.

{{strategies.cards}}
