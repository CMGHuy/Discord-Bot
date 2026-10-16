# v170 — Simple alerts: money beside R, symbol labels, plan buttons

**Version:** ui 1.25.0 · bot 2.5.3 (at writing)
**Bump:** bot minor — every reader of the simple-alerts channel (the v81 execution feed) sees a different message: dollar figures beside every R, symbol labels instead of prose labels, and buttons under each message. ui none — the admin SPA is untouched.
**Edge:** none (integrity) — a clearer view of what each paper trade risks, banks and loses. It changes no signal, threshold, plan, stop, size or badge.
**Screen:** exempt (integrity)
**Panel:** veteran-trader, financial-advisor, senior-engineer
**Status:** spec written 2026-10-16 from a brainstorm with the partner (money scope, interaction set, symbol depth and the design each approved in chat); revised the same day after the three-seat panel (see `## Panel review`).

## Why

The simple-alerts channel (`DISCORD_CHANNEL_TRADES_SIMPLE_ID`) is the v81
execution feed: an order ticket per new setup, then one message per plan
lifecycle event (fill, break-even move, TP1 partial, stop move, close,
cancel, time exit). The partner reads it on a phone. Three gaps:

1. **No money.** A close says `EXITED @ 191.20 — TP2 · +1.65R total`; the
   only dollar figure anywhere in the feed is the ticket's `risk $250`. The
   partner wants to see how much each trade wins or loses **in money and in R**,
   at every moment money moves.
2. **Text-heavy labels.** Lines like `RUNNER 27 sh → TP2 195.00 / trail 2×ATR
   — stop moves are pinged here` are slow to scan on a phone.
3. **No interaction.** The full-alert channel has persistent plan buttons
   (`swingbot/commands/views.py`: Chart, Breakdown, Watch, Dismiss); the feed
   has none, so checking a chart or the live P&L of an open trade means
   switching channel or typing `!pnl`.

## Decisions (approved with the partner)

- **D1 — Money on every money moment.** Ticket, TP1 partial, stop move and
  close all carry a signed dollar figure beside the R.
- **D2 — Symbols replace labels, never broker order words.** Every line a
  reader turns into a broker action keeps its order verb as words: `BUY STOP`,
  `SELL STOP`, `SELL LIMIT`, `BUY LIMIT`, `BUY TO COVER AT MARKET`, `CANCEL`,
  and so on. A misread order type is a real-money error. Everything else that
  labels a value becomes a symbol from one table.
- **D3 — Two kinds of interaction:** the existing plan buttons (📊 Chart,
  🔍 Breakdown, ⭐ Watch) on feed messages, plus a new **💵 P&L now** button
  on messages of a plan that is still open. Every button reply is ephemeral.
  No "I placed it" tracking and no reaction emoji (both considered, not
  chosen).

## Design

### 1. Where each dollar figure comes from

`presentation/instructions.py` stays a pure projection (no I/O, no clock;
its v81 module docstring). Money arrives as data, the way `sizing` already
does.

A new frozen dataclass `Money` in `presentation/instructions.py`:

| field | meaning |
|---|---|
| `currency` | `config.CURRENCY_SYMBOL` |
| `shares` | whole shares of the full position (the existing `_whole_shares` rule), or `None` |
| `realized_amount` | the trade record's settled `realized_pnl_amount`, or `None` |

**Two kinds of figure, never mixed:**

- **Projected ("if hit") $** — always `shares-in-play × price move`, signed
  by direction, computed from the **same whole-share count the message
  prints**. A reader who multiplies the printed shares by the printed move
  gets the printed dollars. There is no separate `r × risk_amount` path that
  could disagree with share rounding. This covers the ticket's stop/TP1/TP2
  lines and a stop move's "if it fills" figure. A stop move adds the already
  banked legs: `shares × fraction × (exit − entry)` per `legs_realized` leg.
- **Realised $** — the TP1 leg banked (`tp1 shares × (fill − entry)`, the
  same arithmetic the trade record's leg uses) and the **close**, whose
  figure is `realized_amount`: the number `account._sum_realized_pnl` adds to
  the balance. The feed and the account balance can never disagree. When the
  record is not settled yet (`realized_amount is None`), the close shows
  **R only**. It never shows an estimate dressed as a realised number.

**Cost basis.** The paper tracker knows no fees, slippage or tax
(`tracking/performance.py:15`). Both the R and the $ are therefore **gross,
on one basis**. The close line and the P&L-now reply say so with
`(paper, gross)`, and the `!help` legend says "paper account, before fees,
slippage and tax".

**Sources, per message:**

- **Ticket:** `execution_embeds.build_ticket_embed` already calls
  `_sizing_snapshot` (`account.compute_position_size`). `Money.shares` comes
  from that snapshot. The paper trade is logged from the same snapshot in the
  same scan, so the source is unchanged.
- **Lifecycle events:** built in `execution_embeds.build_instruction_embed`
  from the **paper-trade record linked to the plan** (`trade["plan_id"]`).
  Today this path calls `_sizing_snapshot` at render time, so a trade opened
  at one balance is sized against a later one. The plan replaces that call
  for money, and also for the share counts the TP1 and time-exit lines
  already print, so quantity and dollars come from one record. When no
  linked record exists (a plan the bot did not log), it falls back to
  today's snapshot behaviour for share counts and shows **no dollar
  figures**.
- **One new accessor**, `trade_for_plan(plan_id)` on the trade log, returns
  the record **in any status**. The existing helpers (`append_leg_by_plan`,
  `close_plan_trade`, `tracking/performance.py:684/797/841`) match only
  `status == "open"`, so a closed trade cannot be found with them. Every
  caller in this spec (the lifecycle money, the closed-plan P&L-now reply)
  uses this one accessor. No ad hoc scans.
- **Settle order.** On the main path, `close_plan_trade` calls
  `_settle_account_balance` (which writes `realized_pnl_amount`,
  `performance.py:909`) before `notify_plan_events` renders the `closed`
  event (`lifecycle_embeds.py:449-479`, from `loops.py:522`). Other settle
  sites exist (`performance.py:1040, 1298, 1444, 1474, 1557, 1738`). The plan
  traces **every close route** and tests each one. A route that emits before
  it settles is fixed by reading `settle_legs` on the record's legs (the
  fallback `account._sum_realized_pnl` already uses), never by shipping a
  close that always says "R only". The unsettled case stays a tested fallback.

All dollar strings go through the existing `plan_table.signed_money`. It moves
into `presentation/tokens.py` as `fmt_money`, and `plan_table.signed_money` is
re-exported as the same object, because `instructions.py` must not import from
`scanning`. A test pins `plan_table.signed_money is tokens.fmt_money`. Every
figure, including the loss side, is signed (`+$181.00` / `-$250.00`).

### 2. Symbol table

One table in `presentation/tokens.py`, `FEED_SYMBOLS`, owns every glyph,
including the direction-dependent comparison glyphs. No glyph literal is
written in `instructions.py`. Each glyph has **one meaning only**.

| key | glyph | replaces |
|---|---|---|
| `entry` | ▶ | the entry line's lead |
| `stop` | 🛑 | the stop line's lead |
| `tp1` | 💰 | `TP1` label |
| `runner` | 🏃 | `RUNNER` label |
| `tp2` | 🎯 | `TP2` label |
| `trail` | 〜 | `trail` |
| `breakeven` | ⚖ | `Stop → entry once price reaches` |
| `expiry` | ⏳ | the time half of `Cancel if:` |
| `invalid` | ⛔ | the price half of `Cancel if:` |
| `if_fills` | 🔒 | a stop move's projected figure |
| `pnl` | 🧾 | a P&L line's lead |
| `win` / `loss` / `flat` | ✅ / ❌ / ➖ | close headline lead, by the same ±0.05R tone bands `_closed` already uses |
| `at_or_above` / `at_or_below` | ≥ / ≤ | price comparisons; `instructions.py` picks by direction |

The money glyphs (💰 a target, 🧾 a P&L line) are deliberately unlike each
other. ⚠ stays reserved for the heat, cluster and kill-switch warnings, so a
warning still reads as exceptional. Risk is shown as the stop line's
"if hit" loss, not with a glyph.

Target layouts (approved shape, revised by the panel). Every order line
carries its broker verb. Long:

```
▶ BUY STOP 182.40 · 54 sh
🛑 SELL STOP 177.80 · if hit -$248.40 · -1.0R
💰 SELL LIMIT 189.10 · 27 sh · if hit +$180.90 · +1.5R
🏃 27 sh: 🎯 SELL LIMIT 195.00 · if hit +$341.10 · +2.8R · 〜 trail 2×ATR, stop moves pinged here
⚖ stop → entry at ≥ 185.00
⏳ CANCEL after Thu 22 Oct (5 sessions) · ⛔ CANCEL if ≤ 177.80 first
```

Short flips the verbs (`SELL STOP` entry, `BUY STOP` stop, `BUY LIMIT`
targets) and the comparison glyphs (`⛔ CANCEL if ≥`, `⚖ at ≤`).

```
✅ EXITED @ 191.20 · 🎯 TP2
🧾 +$412.50 · +1.65R (paper, gross)
```

- **Ticket "if hit" figures** are conditional by wording, and the loss side
  (stop line) is always shown beside the gain side. TP2's figure appears only
  when `plan.tp2` is set. The trail has no fixed price, so it gets no figure.
  The R uses the ticket's `(level − entry) / (entry − stop)`, signed by
  direction.
- **TP1 partial:** `💰 TP1 FILLED 27 sh @ 189.10 · 🧾 +$180.90 · +1.5R`, then
  `🛑 MOVE SELL STOP on the runner → 182.40 now (runner floor)`.
- **Stop move:** `🛑 MOVE SELL STOP → 186.00 now` (`BUY STOP` for a short),
  then `🔒 if it fills: +$X · +R total`. That is a projection (gaps can fill
  worse), worded as one. It never says "locked".
- **Do-not-place ticket, cancels, warnings, extended-hours and time-exit
  text** keep their current wording, apart from the stop/cancel verb rules
  above. They are rare and read carefully. Only their lead label gets a
  symbol where the table has one.
- The phone push-preview line (`kinds.py` registry, v110) is **unchanged**.
- **Legend:** `!help` gains one line generated from `FEED_SYMBOLS` plus the
  cost-basis sentence, so the legend cannot drift from what the feed sends.

The legacy `_legacy_simple_alert` (taken only when `PLAN_ENGINE_V2` is not
`on`) is **out of scope**. Production runs v2.

### 3. Buttons

- A new tuple `FEED_BUTTONS` in `commands/views.py` holds only the new
  `PnlNowButton`. It is registered with the bot's DynamicItems next to
  `PLAN_BUTTONS` (`views.py:393`), but **`PLAN_BUTTONS` is not extended**.
  `PlanActionView` iterates `PLAN_BUTTONS` (`views.py:347`), so extending it
  would leak P&L now into the full-alert channel.
- A factory `feed_view(plan_id, open_)` builds the feed's view:
  - always: the existing `ChartButton`, `BreakdownButton` and `WatchButton`
    DynamicItems, constructed exactly as `PlanActionView` does
    (`author_id=None`), so their handlers, custom_id templates and restart
    persistence are reused unchanged;
  - when `open_` (plan status `ACTIVE` or `PARTIAL`): `PnlNowButton`,
    `custom_id = custom_id_for("pnl", plan_id, None)`.
- **Dismiss is not added.** The feed is an order log, not a board to prune.
- The feed ticket (the simple-channel post in `commands/scanning/alerts.py`)
  and every feed lifecycle message (`lifecycle_embeds.py`'s feed send, plus
  its history-channel copy) attach `feed_view(...)`. A message built before
  this ships has no buttons. Nothing is edited retroactively.
- **`push_kwargs` gains a view.** Verified: `components.py:132`
  `push_kwargs(embed)` returns only `embed` and `content`. It becomes
  `push_kwargs(embed, view=None)` and adds the `view` key **only when a view
  is given** (some discord.py send paths reject `view=None`). A test pins the
  no-view output byte-for-byte unchanged, because nearly every send site
  calls it.

**💵 P&L now** replies **ephemerally**:

- **Open plan:** last price with its **as-of time**, plus `market closed` or
  `delayed` when that applies; unrealised move for the open shares in %, R and
  $; banked legs in R and $; the total, labelled `(paper, gross)`.
- **Price source:** the per-trade body of `scan_run.get_all_unrealized_pnl`
  (`scan_run.py:1249-1285`, the price fallback plus `compute_unrealized_pnl`)
  is extracted into one single-trade function. `get_all_unrealized_pnl`
  calls it in its loop, so `!pnl`'s output is unchanged (refactor, no
  behaviour change, its existing tests stay green). The button uses the same
  function for the open-fraction figure, so `!pnl` and the button cannot
  disagree on it. Banked legs are added by the button from the trade record
  (`trade_for_plan`).
- **Closed or cancelled plan:** its final result from the record, no live
  price.
- **Price fetch failure:** `price unavailable`, never an exception.
- The button never posts in the channel.

### 4. Amendments from the code brief (2026-10-16, override §1–§3 where they differ)

The plan brief (`.superpowers/briefs/2026-10-16-v170-simple-alerts-money-symbols-buttons.md`)
checked §1–§3 against the code. Where a statement above differs, this section wins.

- **A1 — Accessor.** `trades_repo().by_plan_id` (`db/repositories/trades.py:52`)
  already matches any status. `TradeLog.trade_for_plan(plan_id)` is a thin wrapper
  over it, placed beside `get_trade_by_id` (`tracking/performance.py:1239`). It does
  not rescan.
- **A2 — Settle order is already right.** Only plan_manager closes emit a feed
  `closed` event, and every such route (`_persist_terminal`, the `_on_event`
  fallback) calls `close_plan_trade`. That call settles the trade
  (`TradeLog._settle_account_balance`, `performance.py:857`) before
  `notify_plan_events` renders (`loops.py:520-522`). The other settle sites never
  emit a feed message. No reorder is needed. The close-route tests cover each
  `_persist_terminal` route, the `_on_event` fallback, and the unsettled cases
  (no shares, `settle_legs` None, `apply_realized_pnl` raising, no linked open
  trade). An unsettled close shows R only.
- **A3 — Fractional shares.** The record's `shares` is a 2dp float. Messages print
  `floor(shares)`. **Projected "if hit" $** use the printed whole shares, so
  printed shares × printed move = printed $. **Realised $** (TP1 leg, close) come
  from the record's own settle arithmetic, so they reflect the fractional count
  and may differ from printed shares × move by under one share's move. Those
  lines print no share count beside the $, so nothing on screen contradicts them.
- **A4 — P&L now on every plan message** (partner decision, overrides §3's
  ACTIVE/PARTIAL rule). `feed_view` always includes `PnlNowButton`, and the reply
  adapts to the plan's status **at click time**:
  - PENDING: last price vs the trigger, `not filled yet`;
  - ACTIVE/PARTIAL: live unrealised plus banked legs (§3);
  - closed: the final realised result from the record;
  - cancelled or expired: `never filled`.
  `feed_view(plan_id)` therefore drops its `open_` argument.
- **A5 — Live $ and R are computed by the button.** `get_all_unrealized_pnl` and
  `compute_unrealized_pnl` return a percentage only. The extracted single-trade
  function returns the **price** (it keeps the batch price cache, because the
  existing test forbids per-trade daily fetches). The button computes $ and R from
  that price and the trade record.
- **A6 — As-of.** No helper returns a quote timestamp. The reply prints the fetch
  time (`as of HH:MM ET`), adds `daily close <date>` when the price came from the
  daily fallback, and adds `market closed` from `session.is_regular_session()`.
- **A7 — Buttons only on plan-backed feed messages.** The feed mirror also carries
  strategy-signal embeds (`strategy_pass.py:299`) and the legacy mirror. A view is
  attached only where the message has a plan id (the v2 ticket and lifecycle
  events).
- **A8 — Layering.** `core/scanning/lifecycle_embeds.py` gets `feed_view` through a
  function-local import, the pattern that module already uses for its other
  late imports. Core does not import `commands` at module level.
- **A9 — Minus signs.** `tokens.fmt_r` keeps U+2212 and `fmt_money` keeps ASCII
  `-`, both unchanged. Changing either would alter every existing surface that uses
  them, and this spec does not reach those surfaces.
- **A10 — `PLAN_BUTTONS` has five members** (`FollowingButton` too). That changes
  nothing: `FEED_BUTTONS` is separate, and `feed_view` constructs Chart, Breakdown,
  Watch and P&L now.

## Out of scope

- The full-alert channel, closed-trades and retrospective embeds (they
  already show money).
- `_legacy_simple_alert` (non-v2 path).
- Recording whether the reader placed the order (D3: not chosen).
- Total open risk against the account on the feed (panel suggestion,
  deferred: see `## Panel review`).
- Any change to sizing, stops, targets or what gets alerted.

## Testing

- **Projection unit tests**: `Money` for long and short, with win, loss and
  scratch closes, `None` shares, `None` realised (the close shows R only), TP2
  absent, a TP1 leg, and a stop move with and without banked legs. Signs are
  asserted on the rendered string, and every projected $ equals printed
  shares × printed move.
- **Close-route tests:** one per settle site found in §1. Each asserts the
  rendered close carries the record's `realized_pnl_amount`.
- **Symbol-table tests:** every `FEED_SYMBOLS` key is used by at least one
  rendered message; no glyph in the table is shared by two keys; no glyph
  literal sits in `instructions.py` (a grep-style test).
- **Broker-verb guard test:** **every order line** (not every message) of
  every rendered ticket and lifecycle message carries a verb from the long
  set (`BUY STOP`, `SELL STOP`, `SELL LIMIT`, …) or the short set (`SELL
  STOP`, `BUY STOP`, `BUY LIMIT`, `BUY TO COVER …`) for its direction, and
  every cancel line says `CANCEL`. This is D2, enforced.
- **Button tests:** the `PnlNowButton` custom_id round-trip; `feed_view`
  includes P&L now only for `ACTIVE`/`PARTIAL`; `PlanActionView` still renders
  exactly `PLAN_BUTTONS` (no leak); the ephemeral reply for an open, a closed,
  a price-unavailable and a market-closed plan;
  `tests/commands/test_views_persistent.py` extended to cover `FEED_BUTTONS`.
- **`push_kwargs`:** no-view output unchanged; with a view, the key is present.
- **`!pnl` refactor:** the existing tests of `get_all_unrealized_pnl` pass
  unchanged.
- **alert-surface gate:** a rendered before/after for every feed message kind
  (ticket place long and short, ticket do-not-place, filled, be_moved,
  tp1_partial, stop_moved, closed win, closed loss, closed unsettled, close at
  market, cancel, time exit due), committed as a results note in the plan's
  final task. A green suite alone does not pass this gate.
- **Complexity:** the per-kind lead, glyph and verb choices in
  `instructions.py` are table-driven, not added as branches. `radon cc` over
  `instructions.py`, `execution_embeds.py` and `views.py` is an explicit
  plan step; every touched function stays < 15.

## Parallelisation (guidance for the plan)

- §1 Money (dataclass, `fmt_money` move, `trade_for_plan`, the close-route
  trace) is first. §2 symbols rewrite the same `instructions.py` lines, so
  they follow §1 rather than run beside it.
- §3 buttons touch `commands/views.py`, the DynamicItem registration,
  `push_kwargs` and the two send sites. They are independent of §2 and can run
  beside it once `trade_for_plan` exists, because P&L now uses it.
- The before/after render, `!help` legend and full suite come last.

## Panel review

Spec review 2026-10-16, three seats run serially (veteran-trader,
financial-advisor, senior-engineer). Every finding, merged:

**BLOCKING**

- veteran-trader: runner target line carried no order verb, so it could not be placed as written -- applied (`🎯 SELL LIMIT` on the runner line; D2 now says every order line).
- veteran-trader: the expiry/invalidation line lost the word "cancel", and `≤` meant both a date and a price -- applied (`⏳ CANCEL after <date>` · `⛔ CANCEL if ≤ <price> first`).
- financial-advisor: realised $ and R had no stated cost basis -- applied (both verified gross, `tracking/performance.py:15`; labelled `(paper, gross)` and in the legend).
- financial-advisor: projected ticket profits read like expectations, with no loss counterpart in $ -- applied ("if hit" wording; the stop line carries the loss $ beside the gains).

**ADVISORY**

- veteran-trader: the verb guard test checked one verb per message -- applied (every order line, both direction sets, plus `CANCEL`).
- veteran-trader: "locked" reads as guaranteed through a gap -- applied (`🔒 if it fills: …`).
- veteran-trader: `r × risk_amount` dollars can disagree with printed whole shares -- applied (all projected $ = printed shares × printed move; `risk_amount` dropped from `Money`).
- veteran-trader: ❌ meant both "invalid" and "loss"; 💰 and 💵 look alike -- applied (⛔ for invalid; 🧾 for P&L lines; uniqueness test).
- veteran-trader: P&L now showed no as-of time or market-closed state -- applied.
- veteran-trader: the stop-move line had no stop verb -- applied (`MOVE SELL STOP` / `MOVE BUY STOP`).
- financial-advisor: ⚠ as a risk lead blurred the warning cue -- applied (⚠ reserved for warnings).
- financial-advisor: show total open risk against the account -- rejected: outside the scope the partner approved (per-trade money, symbols, buttons); a candidate for its own spec.
- financial-advisor: say "paper" so dollars don't read as real money -- applied (`(paper, gross)` label and legend).
- financial-advisor: unrealised $ in P&L now also needs a basis label -- applied (same label).
- senior-engineer: `push_kwargs` takes no view (`components.py:132`); add the key only when given and pin no-view output -- applied.
- senior-engineer: trade lookups match only open trades -- applied (one `trade_for_plan` accessor, any status).
- senior-engineer: settle order varies by close route -- applied (trace every route, test each).
- senior-engineer: `get_all_unrealized_pnl` is batch-shaped; pin who owns the open-fraction figure -- applied (extracted single-trade function used by both; banked legs from the record).
- senior-engineer: adding to `PLAN_BUTTONS` would leak P&L now into the full-alert channel -- applied (separate `FEED_BUTTONS`, leak test).
- senior-engineer: `signed_money` move needs an identity test; caller count was wrong -- applied (identity test; count claim removed).
- senior-engineer: duplicate glyphs and literal `≤`/`≥` -- applied (unique glyphs, comparisons in the table).
- senior-engineer: the new branches risk complexity ≥ 15 -- applied (table-driven, explicit radon step).
