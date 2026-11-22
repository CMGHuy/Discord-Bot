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
  - swingbot/core/edge/heat.py:open_heat
  - swingbot/core/edge/heat.py:heat_check
  - swingbot/core/edge/heat.py:sector_heat
  - swingbot/core/edge/heat.py:sector_check
  - swingbot/core/edge/heat.py:horizon_check
  - swingbot/core/edge/correlation.py:cluster_exposure
  - swingbot/core/edge/correlation.py:cluster_check
  - swingbot/core/edge/portfolio_state.py:open_heat_state
  - swingbot/core/edge/throttle.py:DD_LADDER
  - swingbot/core/edge/throttle.py:current_throttle
  - swingbot/core/edge/throttle.py:streak_multiplier
  - swingbot/core/edge/throttle.py:check_kill_triggers
  - swingbot/core/edge/throttle.py:set_kill
  - swingbot/core/edge/throttle.py:kill_state
  - swingbot/core/edge/frictions.py
  - swingbot/core/backtesting/backtest_wf.py
  - swingbot/core/planning/builders.py:_clamp_stop_to_hard_cap
  - swingbot/core/scanning/analyze.py:attach_plan_v2
  - swingbot/core/scanning/analyze.py:_sizing_reject_reason
  - swingbot/core/scanning/scan_run.py:_skip_rejected_plan
  - swingbot/core/scanning/short_run.py:_stamp_risk_flags
  - swingbot/core/scanning/alert_embeds.py
  - swingbot/config.py:CLAMP_STOP_TO_HARD_CAP
  - swingbot/config.py:PORTFOLIO_HEAT_CAP_PCT
  - swingbot/config.py:CORRELATED_HEAT_CAP_PCT
  - swingbot/config.py:SECTOR_HEAT_CAP_PCT
  - swingbot/config.py:MAX_OPEN_POSITIONS
  - swingbot/config.py:MAX_OPEN_PER_HORIZON
  - swingbot/config.py:DD_THROTTLE_ENABLED
  - swingbot/config.py:KILLSWITCH_DEFAULT_ON
  - swingbot/config.py:SLIPPAGE_BPS
  - swingbot/config.py:COMMISSION_PER_TRADE
---

> **In plain words** The suggested size on an alert is the number of shares that loses a set amount of money if the stop is hit, worked out for the account stored in the bot's settings, not for yours. Several separate limits shape it, and the smallest one wins. When the portfolio already carries as much risk as it may, the alert still posts, with a size of zero, so you can see what the limit cost.

Education about a paper-trading tool, not advice: alerts are not tailored to you, a suggested size is a default, and past results do not predict future ones.

## Three limits, not one

Three different numbers limit what one trade can lose, and each acts at a different step:

| Limit | What it measures | Now | Past it |
|---|---|---|---|
| [Stop-distance cap](/insights/guide/glossary#stop-distance-cap) | distance from entry to stop, as a share of the entry price | standard cap {{stop.hard_cap}} (maximum stop distance setting now {{MAX_STOP_LOSS_PCT}}) | the stop is clamped or the plan rejected ([chapter 7](/insights/guide/trade-plan#the-stop-distance-cap-and-the-clamp)) |
| [Risk per trade](/insights/guide/glossary#risk-per-trade) | share of the account lost at the stop | {{RISK_PER_TRADE_PCT}}, never more than {{RISK_PER_TRADE_PCT.max}} | fewer shares |
| [Dollar risk cap](/insights/guide/glossary#dollar-risk-cap) | money lost at the stop | {{MAX_RISK_AMOUNT_ABSOLUTE}} | fewer shares |

The first decides whether a plan exists at all; the other two decide how many shares it gets. When the dollar risk cap is on, the smaller of that cap and the risk-per-trade budget limits the size.

The values shown are the stored account's, read when this page is drawn. The `.env` settings only seed a new account; `!account risk` and `!account maxrisk` change the stored values.

<details><summary>Under the hood</summary>

`account.load_account_config()` returns the stored account row; `account._SEED_ENV_KEYS` lists the settings that seed it when it is first created. The stop-distance cap is the constant `risk_limits.HARD_MAX_PLANNED_LOSS_PCT`, not a setting.

</details>

## How the share count is found

1. The risk budget is the balance times the risk per trade.
2. The share count is the budget divided by the distance from entry to stop (or a wider sizing distance, see [gap-aware sizing](#gap-aware-sizing)).
3. The position value is capped at {{MAX_POSITION_SIZE_PCT}} of the balance. An enabled absolute position-value cap (current setting {{MAX_POSITION_VALUE_ABSOLUTE}}) or dollar risk cap can cut the share count further.
4. Last, in every sizing mode, the loss at the stop may never pass {{sizing.risk_ceiling}} of the balance; the share count is rounded down when rounding up would break it.

For example, a balance of $10,000 with a risk budget of $100 and a stop $2.00 below a $50.00 entry gives 50 shares, a $2,500 position; a position cap below $2,500 cuts the shares further. The risk and position value an alert shows are recomputed from the final share count, so they are what a stop-out would really cost.

The balance is the stored starting balance plus everything the paper book has realised since. The paper trade is sized when it is logged and keeps that size, apart from one re-size if a resting order fills at a different price, after that one re-size, a later change of balance or mode never resizes an open trade. On a monthly options-expiration day the size can be cut further.

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

## Portfolio and correlated heat

[Portfolio heat](/insights/guide/glossary#portfolio-heat) is what every open paper trade would lose at its original stop, added up, as a share of the account. It is the same figure the Risk page shows. Before an alert posts, the scan adds one more trade at the risk per trade; if the total would pass {{PORTFOLIO_HEAT_CAP_PCT}}, the alert posts as a [size-0 alert](/insights/guide/glossary#size-0-alert).

[Correlated heat](/insights/guide/glossary#correlated-heat) is the same sum over the open trades whose daily returns over the last {{correlation.window}} correlate above {{correlation.threshold}} with the new ticker. With the new trade added it may not pass {{CORRELATED_HEAT_CAP_PCT}}; past it, the alert also posts with size 0. Three trades in stocks that move together are close to one trade at three times the size, which is why this cap is tighter. In the scan, a pair with too little shared price history counts as not correlated.

<details><summary>Under the hood</summary>

Per alert, `scan_run` re-reads the open trades (so trades logged earlier in the same scan count) and calls `heat.heat_check(open_trades, balance, candidate_risk_pct=risk_pct)` and `correlation.cluster_check(correlation.cluster_exposure(...), risk_pct)`. The short lane does the same in `short_run._stamp_risk_flags`, with the same heat, cluster and kill flags. The Risk page reads `portfolio_state.open_heat_state`, built on the same `heat.open_heat`.

</details>

## Drawdown throttle and kill switch

Two account-level brakes exist in the code; only the kill switch acts on alerts today.

The [drawdown throttle](/insights/guide/glossary#drawdown-throttle) is a ladder that sizes new entries down as the account falls from its peak:

{{throttle.ladder}}

Once paused, entries would resume only when the fall is back under {{throttle.resume}}. A losing streak adds its own cut: {{throttle.streak}}. The walk-forward backtest applies the ladder and the Risk page shows where the account stands on it, but the live scan does not apply it to alert sizes, whatever its setting says (now {{DD_THROTTLE_ENABLED}}); the streak cut is applied nowhere yet.

The [kill switch](/insights/guide/glossary#kill-switch) engages on its own when a scan sees a deep drawdown, a violent day in the S&P 500 ETF (SPY) or a broken data feed, and only a person can release it, with `!killswitch off`. After you release it, the scan's own triggers cannot switch it on again; only a manual `!killswitch on` does. While it is on, every alert posts with a suggested size of zero. On a fresh install it starts {{KILLSWITCH_DEFAULT_ON}}; after that its stored state rules.

<details><summary>Under the hood</summary>

`throttle.check_kill_triggers` runs once per scan and `throttle.set_kill` engages the switch; each alert reads `throttle.kill_state()`. `throttle.current_throttle` is called by `backtesting/backtest_wf.py` and `portfolio_state`; `DD_THROTTLE_ENABLED` has no reader outside `config.py`, and `throttle.streak_multiplier` has no caller.

</details>

## Reject, clamp or size 0

A plan that meets a limit ends in one of three ways:

| Outcome | When | What you see |
|---|---|---|
| reject | the plan broke a rule: a stop beyond the cap with clamping off, no target that pays for the risk, or a wide-stop plan that cannot size to its fixed dollar risk | nothing posts; the log reads `plan rejected (<reason>, stop ... from entry) -- not posted` ([rejected plan](/insights/guide/glossary#rejected-plan)) |
| clamp | a confluence plan's stop lies beyond the cap and the clamp setting, now {{CLAMP_STOP_TO_HARD_CAP}}, is on | the alert posts with the stop moved in to {{stop.clamp_level}} from the entry ([clamp](/insights/guide/glossary#clamp)) |
| size 0 | portfolio heat, correlated heat or the kill switch | the alert posts flagged, with a suggested size of zero |

A size-0 alert carries one of these headlines:

- `⛔ ENTRY BLOCKED — portfolio heat cap`
- `⛔ ENTRY BLOCKED — correlated cluster`
- `⛔ ENTRIES PAUSED (kill switch: <reason>)`

It is shown rather than hidden so you see the setup and what the limit cost; free some heat, or release the switch, and the next alert sizes normally. A clamped plan has its target chosen against the clamped stop, so the reward still has to pay for the smaller risk ([chapter 7](/insights/guide/trade-plan#targets-that-pay-for-the-risk)).

<details><summary>Under the hood</summary>

`analyze.attach_plan_v2` sets the reject reason (`risk_cap`, or `risk_sizing` and the band reasons from `analyze._sizing_reject_reason`) and `scan_run._skip_rejected_plan` logs it. The clamp is `builders._clamp_stop_to_hard_cap`, whose only live caller is the confluence stop geometry, which then picks the target with `select_structural_target` against the clamped stop. The headlines come from `alert_embeds` reading `item.heat_blocked`, `item.cluster_blocked` and `item.kill_switch_blocked`.

</details>

## Caps that are not applied

Some limits exist in the settings or the code but do not act on alerts today. They are listed so you do not rely on them:

- **Sector heat cap** ({{SECTOR_HEAT_CAP_PCT}}): the Risk page shows heat per sector, but no sector limit is applied to the live scan.
- **Open trades per horizon** (`MAX_OPEN_PER_HORIZON`): a setting with a check behind it, not applied to the live scan. The help text of both settings describes a block the scan does not make.
- **Sector fallback for correlation**: on the Risk page, {{correlation.sector_fallback}}; the scan passes no sectors, so there such a pair counts as not correlated.
- **Max open positions** ({{MAX_OPEN_POSITIONS}}): never blocks; past it an alert carries a position-limit warning.
- **Drawdown throttle and streak cut**: see [above](#drawdown-throttle-and-kill-switch).
- **Kelly and volatility estimates**: see [sizing modes](#sizing-modes).

<details><summary>Under the hood</summary>

`heat.sector_check` and `heat.horizon_check` have no caller; `scan_run` calls `correlation.cluster_exposure` without `sectors`. The Risk page computes sector heat with `heat.sector_heat` and passes sectors to its own cluster view.

</details>

## Costs, turnover and tax

Swing trading turns an account over often. Alert rate: {{alerts.per_week}}. Each round trip pays a spread and possibly a commission, and a short also pays a fee to borrow the stock; a strategy that earns little per trade can lose all of it to these costs. Paper trades carry none of them, which is why every live figure in this guide says "costs not included".

The backtests behind the strategy badges can charge slippage, a commission and the short borrow fee, but the registry rows do not record whether a run did, so each card says "costs not recorded" ([chapter 5](/insights/guide/strategies#reading-a-card)).

Tax is the other drag. In many countries gains on positions held for days or weeks are taxed differently from gains held for years, and very frequent trading can change how an account is treated. Rules differ by country and by person: this guide gives no tax advice, and every result in it is labelled "before tax". For your own case, ask a tax adviser.

<details><summary>Under the hood</summary>

`edge/frictions.py`: `apply_frictions` (`SLIPPAGE_BPS` per side), `commission_r` (`COMMISSION_PER_TRADE` each way, in R) and `borrow_r` (shorts only). Every figure the guide prints goes through `provenance_label`, which states costs and "before tax".

</details>
