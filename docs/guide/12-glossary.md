---
title: Glossary
slug: glossary
order: 12
reviewed_for: 2.19.2
sources:
  - swingbot/core/backtesting/registry.py:Badge
  - swingbot/core/backtesting/registry.py:decay_for
  - swingbot/core/market/strategy_types.py:HORIZONS
  - swingbot/core/market/strategy_types.py:admits
  - swingbot/core/market/levels.py:CLUSTER_TOLERANCE_PCT
  - swingbot/core/planning/plan_engine.py
  - swingbot/core/edge/correlation.py:cluster_check
  - swingbot/core/edge/heat.py:heat_check
  - swingbot/config.py:MAX_STOP_LOSS_PCT
  - swingbot/config.py:CLAMP_STOP_TO_HARD_CAP
  - swingbot/config.py:RISK_PER_TRADE_PCT
  - swingbot/config.py:MAX_RISK_AMOUNT_ABSOLUTE
  - swingbot/config.py:PORTFOLIO_HEAT_CAP_PCT
  - swingbot/config.py:CORRELATED_HEAT_CAP_PCT
  - swingbot/config.py:STRATEGY_ALERTS_MODE
---

> **In plain words** Every word the guide uses, in one place. Each term has its own link, so other chapters point straight at it.

## The bot and its alerts

### Alert

One trade plan for one ticker on one horizon, posted to Discord and shown on the admin site.

### Trade plan

The full instruction behind an alert: direction, entry, stop, TP1, TP2 and a suggested size.

### Paper trade

A trade the bot only records. It follows the plan bar by bar and books the result as if the orders had filled; no money moves.

### Live paper book

Every paper trade opened from a live alert. Figures labelled "live paper book" come from it.

### Horizon

How long a plan is meant to run, from a short swing to several months. Each horizon has its own lookbacks, stop limits and longest hold.

### Masked

A horizon, or a strategy on one side and horizon, that is measured in research but never alerted. Shown as *masked — research only*.

### Long and short

A long profits when the price rises; a short profits when it falls. Every plan is one or the other.

### Confidence

A level and a score on every alert that rank how well a setup lines up. It is a ranking, not the chance of winning.

### Watchlist and universe

The watchlist is the list of tickers you follow, and it is always scanned. The universe is an optional wider set scanned on top.

### Shadow mode

A setting under which strategy plans are built and recorded but never alerted or traded, so they can be measured first.

## Levels and setups

### Support and resistance

Support is a price where falling stocks have tended to stop; resistance is where rising ones have. The bot trades from one toward the next.

### Level

One support or resistance price after nearby candidates from different methods have merged.

### Level family

One method of drawing levels, for example moving averages, Fibonacci retracements or pivots. The level chapter lists them all.

### Level lifecycle

What price has done to a level, read from finished bars: fresh (never touched), tested (touched and held), delivered (price closed through it) or decaying (not touched for a long time). A stop prefers to sit beyond a tested level and never leans on a delivered one.

### Confluence

How many different level families agree on one level. Candidates within {{CLUSTER_TOLERANCE_PCT}} of each other merge, and each family counts once, however many lines it draws.

### Scenario

A possible trade from the current price: long toward the next resistance or short toward the next support. It must clear hard requirements to become a plan.

### Strategy

A named entry rule, such as a breakout or a pullback, measured in backtests and allowed only on the sides and horizons its results support.

### Direction mask

The sides (long, short) and horizons on which a strategy may alert, set from its measured results. A strategy whose mask admits nothing is masked: measured in research, never alerted.

### Completed bar

A daily bar after its session has closed. Signals read completed bars only, so the live bot and a backtest see the same data.

### Gate

A filter a setup must pass before it becomes a plan, kept because a measurement showed it helped.

### Market regime

The state of the broad market, read once per scan. Gates that care about the market use it.

### Relative strength

How a stock has moved against the market or its sector over a window set per horizon.

## Inside a trade plan

### Entry

The price at which the plan opens. Until the price reaches it, the plan waits.

### Stop

The price where the idea is proved wrong. The trade closes there at −1R, and the stop never moves further away after entry.

### TP1 and TP2

The two profit targets. TP1 is a real level on the chart; TP2 lies further out.

### Runner

The part of the position left open after TP1. It aims for TP2 and can also close on its trailing stop, at break-even or on a time limit.

### Scale-out

Closing part of the position at TP1 and leaving the runner to work.

### Reward to risk (R:R)

The distance to TP1 divided by the distance to the stop. A plan needs a minimum before it is built.

### Plan states

PENDING (waiting for the entry), ACTIVE, PARTIAL (after TP1), then CLOSED. A plan whose entry never fills is CANCELLED.

## Risk and sizing

### Stop-distance cap

The furthest a stop may sit from the entry: {{MAX_STOP_LOSS_PCT}} of the price.

### Clamp

What happens to a stop beyond the stop-distance cap when clamping is on: it moves in to the cap. When clamping is off, the plan is dropped instead.

### Risk per trade

The share of the account one trade loses at its stop in the fixed-risk sizing mode: {{RISK_PER_TRADE_PCT}}, never more than {{RISK_PER_TRADE_PCT.max}}.

### Dollar risk cap

The most one trade may lose at its stop in money: {{MAX_RISK_AMOUNT_ABSOLUTE}}.

### Rejected plan

A plan that broke a rule. It is logged as `plan rejected (` with the reason and never posted.

### Portfolio heat

The total risk of every open trade at its stop, as a share of the account. A new trade that would push it over {{PORTFOLIO_HEAT_CAP_PCT}} is posted as a size-0 alert. The Risk page shows the same figure.

### Correlated heat

The risk sitting in one group of stocks whose daily returns correlate above {{correlation.threshold}} over {{correlation.window}}, capped at {{CORRELATED_HEAT_CAP_PCT}} of the account.

### Size-0 alert

An alert a heat cap blocks. It still posts, flagged, with a suggested size of zero, so you see what the cap cost.

### Suggested size

The number of shares that loses the risk per trade at the stop for the account stored in the bot's settings. A default, not advice.

### Gap through the stop

The price opens beyond the stop, so the fill is worse than −1R. Risk and heat are measured to the stop, not to the gap.

### Drawdown throttle

The throttle ladder: as the account falls further from its peak, the size of new entries steps down, and at the bottom of the ladder entries pause until the account has recovered part of the fall. The ladder is computed and shown on the Risk page. The setting reads {{DD_THROTTLE_ENABLED}}. The live scan does not apply it to alert sizes today.

### Kill switch

A pause on new entries that the scan engages on its own after a deep drawdown, a violent market day or a broken data feed, and that only a person can release. While it is on, alerts still post, with a suggested size of zero.

## Measuring results

### R-multiple

A result divided by the risk taken. +2R made twice the risk; −1R lost the risk.

### Expectancy (ExpR)

The average R per closed trade. Positive means the method made money on average in that sample; it says nothing certain about the next trade.

### Win rate

The share of closed trades that made money. It can rise while expectancy falls, when winners get smaller.

### Drawdown and losing streak

A drawdown is a fall from a peak in account value; a losing streak is losses in a row. Both happen even when expectancy is positive.

### Badge

A strategy's backtest grade, VALIDATED or WEAK, always shown with its N, window and run date. It ages to *aging* and then *stale* as the run date gets older. A measurement, not a forecast.

### Provenance label

The note beside every performance figure: its source, N, date, whether costs are included, and "before tax".

### TRAIN and validation

Two separate backtest windows. Rules are tuned on TRAIN and confirmed once on validation, never tuned on it.

### Idea screen

A quick historical test a new entry idea must pass before any work is planned on it.

### Pre-registration

A test whose pass bar is written down before it runs. A failed one is closed and never re-run.

### No-lift

The verdict on a change that did not improve results. The change is not shipped, and the record is kept.

## About this guide

### Reviewed for

The bot version a chapter was last checked against, shown at the top of each chapter.

### Under the hood

The collapsed boxes for developers: the module, setting and algorithm behind a section.
