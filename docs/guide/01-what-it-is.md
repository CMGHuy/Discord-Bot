---
title: What the bot is (and isn't)
slug: what-it-is
order: 1
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/strategy_types.py:HORIZONS
  - swingbot/core/market/strategy_types.py:live_horizons
  - swingbot/core/scanning/scan_run.py:run_scan
  - swingbot/core/scanning/alert_embeds.py
  - swingbot/core/tracking/performance.py:TradeLog
  - swingbot/config.py:SCAN_UNIVERSE
  - swingbot/config.py:DISCORD_CHANNEL_TRADES_ID
  - swingbot/config.py:DISCORD_CHANNEL_TRADES_SIMPLE_ID
  - swingbot/config.py:DISCORD_CHANNEL_TRADES_HISTORY_ID
  - swingbot/config.py:DISCORD_CHANNEL_NOTIFY_ID
  - swingbot/config.py:ETORO_USER_KEY
---

> **In plain words** The bot reads daily price charts, looks for places where a stock tends to turn, and posts a ready-made trade plan when one lines up. It never buys or sells anything. Every plan it posts is followed as a paper trade, so you can see how it would have done.

## What it does

The bot is a swing-trade alert tool. It watches a list of US stocks and ETFs (the [watchlist](/insights/guide/glossary#watchlist-and-universe)), finds price [levels](/insights/guide/glossary#level) where several independent methods agree, and turns a good setup into a [trade plan](/insights/guide/glossary#trade-plan): where to enter, where the [stop](/insights/guide/glossary#stop) sits, and where to take profit ([TP1 and TP2](/insights/guide/glossary#tp1-and-tp2)).

It holds trades for days to months, not minutes. It is built for [swing horizons](#swing-horizons) and judges setups on completed daily bars.

[The scan pipeline](/insights/guide/pipeline) shows every step from the watchlist to a closed trade.

## What it does not do

- **It never places an order.** The bot sends no orders to any broker. Every plan it posts becomes a [paper trade](/insights/guide/glossary#paper-trade): a record the bot follows bar by bar to see whether the stop or a target would have been hit.
- **It is not a live account.** A planned next step sends the same plans to an eToro *demo* account, which trades practice money. A demo account is not a live account, and nothing is sent to eToro today.
- **It does not know you.** It does not know your account, your other positions, your taxes or your goals. Its suggested size is worked out for the account size stored in its settings, not for yours.
- **It does not predict.** A plan says where the setup is proved wrong (the stop) and where it pays (the targets). It does not say the trade will work.

## Swing horizons

A [horizon](/insights/guide/glossary#horizon) is how long a plan is meant to run. Each horizon has its own settings: how far back levels are drawn from, how far away a stop may sit, and how long a trade may be held. A horizon marked *masked — research only* is measured in backtests but never alerted.

{{horizons.table}}

## What an alert is

An [alert](/insights/guide/glossary#alert) is one trade plan for one ticker on one horizon. It carries:

- the direction, [long or short](/insights/guide/glossary#long-and-short);
- the entry, the stop, TP1 and TP2, and the [reward to risk](/insights/guide/glossary#reward-to-risk-rr) to TP1;
- a [confidence](/insights/guide/glossary#confidence) level and, for a strategy setup, the strategy's [badge](/insights/guide/glossary#badge) with its sample size and date;
- a chart with the levels drawn on it;
- warnings when something needs attention, for example an unusually tight stop, or a position the [portfolio heat](/insights/guide/glossary#portfolio-heat) cap blocks (the alert still posts, with a suggested size of zero).

Most scans post nothing. A quiet day means no setup cleared every check, not that the bot is broken.

## Where alerts appear

- **Discord.** New plans go to the alerts channel, and a short text version to the simple-alerts channel. Wins, losses and near-stop or near-target notices go to the closed-trades channel. Updates on plans people follow (near the stop, TP1, TP2) go to the plan-updates channel.
- **bomeo-capital.com.** The admin site shows the same plans and every paper trade: open ones on Dashboard and Trades, closed ones with their result, and the measurements behind them under Insights.

<details><summary>Under the hood</summary>

The scan entry point is `run_scan` in `swingbot/core/scanning/scan_run.py`; the Discord embed is built in `swingbot/core/scanning/alert_embeds.py`; paper trades live in the trade log (`TradeLog`, `swingbot/core/tracking/performance.py`). The channels are the `DISCORD_CHANNEL_*` settings in `swingbot/config.py`. What is scanned is `SCAN_UNIVERSE`: the watchlist always, plus an optional wider universe. The horizon table is built from `HORIZONS` and `live_horizons()` in `swingbot/core/market/strategy_types.py` each time the chapter is served, so a horizon masked or unmasked in code shows correctly here without editing this text. The eToro keys (`ETORO_USER_KEY`, `ETORO_API_KEY`) exist in the settings, and nothing reads them yet.

</details>

## The notice

Read this before acting on anything the bot posts.

- **This guide is education about a paper-trading tool.** It explains how the tool works. It is not financial, investment or tax advice.
- **Alerts are not recommendations tailored to you.** They come from rules that know nothing about your situation.
- **A suggested size is a default, not advice.** It is sized to the account stored in the bot's settings; choose your own size for your own account.
- **Past results do not predict future ones.** Win rates, expectancy and badges measure what already happened, in backtests or in the paper book. Paper results also differ from real fills: real orders pay costs and can fill worse than the plan, especially across a gap.

If you trade from these alerts, you do so on your own judgement and at your own risk.
