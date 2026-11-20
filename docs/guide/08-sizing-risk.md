---
title: Sizing and risk
slug: sizing-risk
order: 8
reviewed_for: 2.19.2
sources:
  - swingbot/core/planning/account.py:compute_position_size
  - swingbot/core/planning/account.py:load_account_config
  - swingbot/core/planning/account.py:_SEED_ENV_KEYS
  - swingbot/core/planning/account.py:_edge_risk_pct
  - swingbot/core/planning/account.py:_sizing_distance
  - swingbot/core/planning/account.py:_apply_size_caps
  - swingbot/core/planning/account.py:_cap_to_risk_ceiling
  - swingbot/core/planning/gap_sizing.py:size_for
  - swingbot/core/planning/gap_sizing.py:size_for_plan
  - swingbot/core/planning/gap_sizing.py:stamp_gap_sizing
  - swingbot/core/planning/gap_sizing.py:LOOKBACK
  - swingbot/core/edge/sizing.py:effective_risk_pct
  - swingbot/core/edge/sizing.py:kelly_risk_pct
  - swingbot/core/edge/sizing.py:vol_target_risk_pct
  - swingbot/core/edge/sizing.py:KELLY_FRACTION_CAP
  - swingbot/core/edge/sizing.py:RISK_FLOOR_PCT
  - swingbot/core/edge/sizing.py:RISK_CEILING_PCT
  - swingbot/core/market/opex.py:size_mult
  - swingbot/core/risk_limits.py:HARD_MAX_PLANNED_LOSS_PCT
  - swingbot/config.py:RISK_PER_TRADE_PCT
  - swingbot/config.py:MAX_RISK_AMOUNT_ABSOLUTE
  - swingbot/config.py:MAX_STOP_LOSS_PCT
  - swingbot/config.py:POSITION_SIZING_MODE
  - swingbot/config.py:MAX_POSITION_SIZE_PCT
  - swingbot/config.py:MAX_POSITION_VALUE_ABSOLUTE
  - swingbot/config.py:SHORT_GAP_SIZING
  - swingbot/config.py:LONG_GAP_SIZING
  - swingbot/config.py:OPEX_CAUTION_ENABLED
  - swingbot/config.py:OPEX_SIZE_REDUCTION_PCT
---

> **In plain words** The suggested size on an alert is the number of shares that loses a set amount of money if the stop is hit, worked out for the account stored in the bot's settings, not for yours. Several separate limits shape it, and the smallest one wins. When the portfolio already carries as much risk as it may, the alert still posts, with a size of zero, so you can see what the limit cost.

Education about a paper-trading tool, not advice: alerts are not tailored to you, a suggested size is a default, and past results do not predict future ones.

## Three limits, not one

Three different numbers limit what one trade can lose, and each acts at a different step:

| Limit | What it measures | Now | Past it |
|---|---|---|---|
| [Stop-distance cap](/insights/guide/glossary#stop-distance-cap) | distance from entry to stop, as a share of the entry price | {{stop.hard_cap}}; the setting, now {{MAX_STOP_LOSS_PCT}}, cannot go above it | the stop is clamped or the plan rejected ([chapter 7](/insights/guide/trade-plan#the-stop-distance-cap-and-the-clamp)) |
| [Risk per trade](/insights/guide/glossary#risk-per-trade) | share of the account lost at the stop | {{RISK_PER_TRADE_PCT}}, never more than {{RISK_PER_TRADE_PCT.max}} | fewer shares |
| [Dollar risk cap](/insights/guide/glossary#dollar-risk-cap) | money lost at the stop | {{MAX_RISK_AMOUNT_ABSOLUTE}} | fewer shares |

The first decides whether a plan exists at all; the other two decide how many shares it gets. Of the two money limits, whichever is less money wins: on a small account the risk per trade usually binds, on a large one the dollar cap does.

The values shown are the stored account's, read when this page is drawn. The `.env` settings only seed a new account; `!account risk` and `!account maxrisk` change the stored values.

<details><summary>Under the hood</summary>

`account.load_account_config()` returns the stored account row; `account._SEED_ENV_KEYS` lists the settings that seed it when it is first created. The stop-distance cap is the constant `risk_limits.HARD_MAX_PLANNED_LOSS_PCT`, not a setting.

</details>

## How the share count is found

1. The risk budget is the balance times the risk per trade.
2. The share count is the budget divided by the distance from entry to stop (or a wider sizing distance, see [gap-aware sizing](#gap-aware-sizing)).
3. Three caps can cut it, and the tightest wins: the position's value may not pass {{MAX_POSITION_SIZE_PCT}} of the balance, nor {{MAX_POSITION_VALUE_ABSOLUTE}}, and its loss at the stop may not pass the dollar risk cap.
4. Last, in every sizing mode, the loss at the stop may never pass {{sizing.risk_ceiling}} of the balance; the share count is rounded down when rounding up would break it.

For example, a balance of $10,000 with a risk budget of $100 and a stop $2.00 below a $50.00 entry gives 50 shares, a $2,500 position; a position cap below $2,500 cuts the shares further. The risk and position value an alert shows are recomputed from the final share count, so they are what a stop-out would really cost.

The balance is the stored starting balance plus everything the paper book has realised since. The paper trade is sized when it is logged and keeps that size, apart from one re-size if a resting order fills at a different price, so a later change of balance or mode never resizes an open trade. On a monthly options-expiration day the size can be cut further.

<details><summary>Under the hood</summary>

Alerts size through `gap_sizing.size_for_plan`, which calls `account.compute_position_size`. Caps 1 to 3 are `account._apply_size_caps`; the ceiling is `account._cap_to_risk_ceiling` with `sizing.RISK_CEILING_PCT`. `opex.size_mult` scales the budget on a monthly expiration while `OPEX_CAUTION_ENABLED` is set, by `OPEX_SIZE_REDUCTION_PCT`.

</details>

## Sizing modes

The stored account's sizing mode is now {{POSITION_SIZING_MODE}}.

| Mode | How the size is set |
|---|---|
| `risk_pct` | the steps above: a stop-out loses the risk per trade |
| `account_pct` | the position's value is a fixed share of the balance, whatever the stop distance; the caps and the ceiling still apply |
| `kelly` | a fraction of the Kelly bet from the strategy's record, capped at {{sizing.kelly_cap}} |
| `vol_target` | a risk that keeps the portfolio's estimated daily swing near a target |
| `min_of_all` | the lowest of the estimates |

The last three pick the lowest estimate, never above the risk per trade, and never below {{sizing.risk_floor}}, even when the risk per trade is set lower. The alert path passes them no strategy record and no volatility reading, so in those modes an alert today is sized on the risk per trade, floored at {{sizing.risk_floor}}.

<details><summary>Under the hood</summary>

`account._edge_risk_pct` resolves the three edge modes through `sizing.effective_risk_pct` (the minimum of the estimates that exist, floored at `RISK_FLOOR_PCT`). `sizing.kelly_risk_pct` runs only with `strategy_stats` and `sizing.vol_target_risk_pct` only with `ticker_atr_pct`; `gap_sizing.size_for_plan` passes neither.

</details>

## Gap-aware sizing

A stop is the price where you intend to get out, but a stock can open beyond it ([gap through the stop](/insights/guide/glossary#gap-through-the-stop)). Gap-aware sizing takes the larger of the stop distance and a bad but routine gap for that ticker as its sizing distance, so such a gap stays inside the money you meant to risk. In the risk-per-trade mode that distance divides the risk budget; in the fixed-share-of-balance mode it only divides the dollar risk cap, so it can cut the position only where that cap binds. It only ever lowers the share count: the stop does not move, and [R](/insights/guide/glossary#r-multiple) is still measured on the stop.

{{sizing.gap}}

The rule in force is stamped on a plan when it is created, so switching it later never resizes an alert already posted.

<details><summary>Under the hood</summary>

`gap_sizing.stamp_gap_sizing` records the rule and the ticker's gaps over `gap_sizing.LOOKBACK` completed bars; `gap_sizing.size_for` passes the gap as `gap_floor_pct` and `account._sizing_distance` takes the larger distance. Settings: `SHORT_GAP_SIZING`, `LONG_GAP_SIZING`.

</details>
