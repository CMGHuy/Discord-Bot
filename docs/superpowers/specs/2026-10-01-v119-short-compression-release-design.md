# v119 — First bearish compression release, 3–10-session SHORT plan

**Version:** ui 1.21.0 · bot 1.12.1 (at writing)
**Bump:** bot patch (only if the new alert and exit lifecycle ship)
**Edge:** expectancy

## Correction and status

The initially proposed "support break, later underside retest, failed reclaim"
is already the bearish Break & Retest entry in `entry_filters.py`. Its bearish
v104 structural-stop arm did not advance, and the masked v113 1w cell did not
proceed. A shorter hold or wider universe is not a new entry hypothesis. This
spec does **not** reopen Break & Retest, Bull Trap, Vol Expansion Breakdown,
Earnings Gap Drift or Downtrend Overbought Fade. Their recorded negative
results remain closed.

The new event is **a documented compression state followed by its first
bearish release**. The v104 Vol Expansion Breakdown entry required ATR
expansion at the breakdown but did not require a preceding compression state
or the first release transition. Existing
`volatility.squeeze_breakout_confirmation` already computes this transition
as a confidence component. v119 tests it as a standalone SHORT entry, without
counting that same fact twice in plan quality.

This is a pre-registered research and implementation design. No historical
result, badge, default-on flag, production change or broker fill is claimed.

## Intent and independent scope

The partner wants actionable share-SHORT alerts in broad market weakness and
isolated stock/sector weakness, with a faster expected holding period than the
ten existing live swing horizons. Entry is a resting sell-stop below the
completed release bar; the plan has one lower-support profit target and a hard
time exit at the **10th regular-session closing auction**. Stop or target may
close it earlier than three sessions. The partner checks share borrow at the
broker; the bot never represents borrow availability as verified.

This work is a separate signal, exit and evidence population from v118's
existing-horizon universe expansion. The shared candidate context may supply
symbols and broad/isolated mode tags after v118 ships, but v119 must be
testable on a frozen, point-in-time population even if v118 remains off. A v118
PASS does not admit v119, and a v119 PASS does not change v118's confluence
rules. The existing masked `1w` horizon remains 3–7 days. v119 uses a
strategy-specific 10-session cap on the existing `2w` strategy horizon; it
does not change `HORIZONS["1w"]` or admit any legacy 1w cell.

## Frozen entry hypothesis

Use the current `squeeze_breakout_confirmation` defaults as the initial,
frozen compression definition: 20-bar Bollinger bands (2 standard
deviations) inside a 20-period Keltner channel (ATR period 10, multiplier
1.5) on the preceding completed bar; the current completed bar is the first
outside state, closes below the preceding lower Bollinger band, and has
volume at least 1.5 times the prior 20-bar average. The preceding state and
first release are the causal event. No grid over those existing defaults or
an ATR-expansion `m` from the closed v104 question is permitted here.

The same pure indicator series must feed the existing confidence component,
the new entry filter, live scan and replay. Refactoring it requires a
behavior-preserving witness test before adding the strategy. The entry filter
returns bearish only, `.fillna(False)`, with a truncation test proving the
signal at bar t uses bars no later than t. Today's still-forming daily bar is
excluded. Stock, SPY and sector ETF observations are aligned to the same
completed exchange date.

Broad weakness and isolated weakness are separate registered arms. Broad
uses the existing SPY bearish trend result on the decision bar. Isolated
requires SPY not bearish and the stock's trailing 63-session return below
its mapped sector ETF's return. The two contexts share the compression
event but are reported and selected separately. Existing stock and sector
RS are one related evidence family; the squeeze event is not counted again
as an independent confidence point. Missing or stale benchmark/sector data
fails the relevant arm closed.

Known scheduled earnings within the next 10 regular sessions excludes a
setup. A missing or stale earnings calendar excludes it rather than being
treated as "no earnings". This is a pre-entry rule, not the v104
`exit_before` toggle, and its opportunity cost must be reported. An unknown
future unscheduled event cannot be ruled out by the bot.

## Pending entry and plan geometry

On the first completed release bar, place a bearish `stop_entry` trigger one
minimum stock tick below that bar's low, valid for the next regular session
only. The alert names that trigger and its expiration. At a gap below the
trigger, live and replay fill at the worse observed/open price and recheck the
planned-loss cap before activation; a fill beyond the cap cancels the plan and
sends a cancellation instruction. If the next session does not trigger, the
pending plan expires with an explicit cancel-resting-order message. No
same-bar fill or retroactive signal is permitted.

The protective stop is above the release bar's high with the existing
structural ATR buffer. It is not moved inside that structure to make a plan
pass. A stop beyond the applicable hard risk ceiling rejects the plan. The
single whole-position target is the next confirmed lower swing support that
satisfies the current reward-to-risk band; no synthetic ATR target is
substituted when no lower support exists. Target and risk geometry are
computed from the resting trigger, not the signal close, and rechecked on
the actual gap fill. The plan has no scale-out, break-even move or runner.

The existing `TradePlanV2` `stop_entry`, `trigger_price` and `expiry_bars`
model can represent the pending order. The current strategy builder sets
every trigger to the signal close, so this strategy needs a single explicit
trigger-price source shared by live and replay. The target/stop and risk
calculation must use that same source. The strategy is registered once and
masked until its own evidence and live parity gates clear.

## Hard 10-session exit and broker action

Once filled, stop and target remain active. If neither closes the position,
the 10th regular trading session of the position (fill session is session 1)
ends with a buy-to-cover at the
official closing-auction price. A generic daily OHLCV `Close` is only a
research proxy for that price, never proof of an auction execution. Live paper
closure requires a confirmed close source; if it is unavailable, retain an
unresolved exit and resend an actionable notice rather than invent a fill.
Historical results disclose the proxy and cannot by themselves clear the
broker-workflow or live-price parity gates. Replay already has a bar-based
hold cap; the live plan manager needs the same hard cap for ACTIVE plans. This strategy has
no PARTIAL state by design, but the manager's generic hard-cap helper must
handle a persisted PARTIAL plan safely rather than strand a runner. The
session counter is based on fill time, not signal time, and respects holidays
and early closes.

At 15:30 ET on that session (or at least 20 minutes before an early close),
send one actionable `time_exit_due` notice: position size, buy-to-cover MOC
instruction, broker order check and closing-auction date/time. At the
official close, record the paper fill and send one confirmed time-close
notice. The notice path must queue/retry/ack as other terminal notices do;
an undelivered instruction is a trading divergence, not a cosmetic issue.

MOC order entry deadlines differ by venue and broker. NYSE currently lists
3:50 p.m. ET and Nasdaq 3:55 p.m. ET exchange cutoffs; a broker can require
an earlier time. The 15:30 notice leaves exchange-level headroom, but it does
not prove the partner's broker supports a safe MOC plus protective-order
workflow. If a stop or target fills after a MOC order is staged, the bot must
immediately emit a cancel/verify instruction. **Live enablement is blocked**
until the partner has confirmed at the broker that the MOC and protective
orders can be linked or safely canceled without an unintended reverse
position. If not, this strategy remains shadow-only and a separately approved
time-exit design is required. Paper replay must never be presented as proof
of broker order linkage.

References: [NYSE closing auction](https://www.nyse.com/trade/auctions),
[Nasdaq Closing Cross](https://www.nasdaqtrader.com/trader.aspx?id=openclose).

## Measurement and ship rule

Freeze universe membership, the two regime arms, compression definition,
completed-bar timing, entry/fill/expiry, stop, lower-support target, earnings
exclusion, 10-session close, slippage and commission assumptions, windows,
and the selection rule before measuring outcomes. Use point-in-time universe
membership; the current live S&P list cannot be projected backward. Report
the added/cohort SHORT count, win rate, expectancy, target/stop/time exits,
gap cancellations, earnings exclusions, missing-data exclusions, and the
break-even borrow-fee sensitivity. Historical borrow availability is unknown.

Stage −1 proves both the strategy entry and the tenth-session close are
reachable through the same live constructor and replay path. Run the free MDE
precheck and TRAIN/fold stages before spending any one-shot holdout or
VALIDATION budget. The v104/v113 closed rows are not rerun. The broad and
isolated arms must each stand on their own; no pooled success can mask a
failing arm. A new strategy's badge is earned from the registry's own tier
rules. Default-on admission also requires the standard additive feature gate
for the incremental alert population, including its geometry clause where
applicable. The proposed single-target and time-stop plan is part of that
population; this is not a paired exit-only harvest test. If the standard
instrument cannot represent the additive arm faithfully, freeze an acceptance
amendment before selection runs and keep the live mask closed. A later isolated
exit comparison would need its own paired harvest pre-registration.

The live strategy pass stays globally off by default. The new strategy stays
masked after implementation until all measurement gates, live/replay parity,
Discord notification delivery, and the broker MOC workflow gate pass. Shadow
mode can record non-executable plans without sending trade instructions.
This spec does not authorize production SSH, deploy or config changes.

## Parallelisation

The behavior-preserving squeeze-series refactor is first. The entry signal,
plan geometry and order trigger consume that series and are sequential.
Replay and live hard-cap tests can be prepared in separate files, but their
shared session-count contract must be frozen first. Alert rendering follows
the event contract. Measurement runs are strictly serial by funnel stage;
the single validation/holdout shot never runs concurrently with an edit or a
second candidate. Final full-suite verification is one task at the end.
