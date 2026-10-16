# v170 — Simple alerts: money beside R, symbol labels, plan buttons

**Version:** ui 1.25.0 · bot 2.5.3 (at writing)
**Bump:** bot minor — every reader of the simple-alerts channel (the v81 execution feed) sees a different message: dollar figures beside every R, symbol labels instead of prose labels, and buttons under each message. ui none — the admin SPA is untouched.
**Edge:** none (integrity) — a clearer view of what each paper trade risks, banks and loses. It changes no signal, threshold, plan, stop, size or badge.
**Screen:** exempt (integrity)
**Panel:** veteran-trader, financial-advisor, senior-engineer
**Status:** spec written 2026-10-16 from a brainstorm with the partner (money scope, interaction set, symbol depth and the design each approved in chat).

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
- **D2 — Symbols replace labels, never broker order verbs.** `BUY STOP`,
  `SELL STOP`, `SELL LIMIT`, `BUY TO COVER AT MARKET` and the like stay as
  words: they are what the reader types at the broker, and a misread order
  type is a real-money error. Everything else that labels a value becomes a
  symbol from one table.
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
| `shares` | whole shares of the position (the existing `_whole_shares` rule), or `None` |
| `risk_amount` | dollars at risk from entry to the initial stop, or `None` |
| `realized_amount` | the trade record's settled `realized_pnl_amount`, or `None` |

The dollar value of any R is **`r × risk_amount`**. That covers the ticket's
TP1 and TP2 projections, a TP1 leg (`leg r × fraction × risk_amount`) and a
stop move's locked-in figure. One formula means one sign convention.

**The close is the exception.** Its figure is `realized_amount`, the number
`account._sum_realized_pnl` adds to the balance, so the feed and the account
balance can never disagree. When the trade record is not settled yet
(`realized_amount is None`), the close shows **R only**. It never shows an
estimate dressed as a realised number.

**Sources, per message:**

- **Ticket:** `execution_embeds.build_ticket_embed` already calls
  `_sizing_snapshot` (`account.compute_position_size`). `Money` is built from
  that snapshot (`shares`, `risk_amount`). This is the same snapshot the paper
  trade is logged with in the same scan, so the source is unchanged.
- **Lifecycle events:** built in `execution_embeds.build_instruction_embed`
  from the **paper-trade record linked to the plan** (its shares, its risk
  amount, its `realized_pnl_amount`). Today this path calls `_sizing_snapshot`
  at render time, so a trade opened at one balance gets sized against a later
  one. The plan replaces that call for money, and also for the share counts the
  TP1 and time-exit lines already print, so quantity and dollars come from one
  record. When no linked record exists (a plan the bot did not log), it falls
  back to today's snapshot behaviour for share counts and shows **no dollar
  figures**.
- The plan brief must confirm (a) how a plan finds its trade record and
  (b) whether `realized_pnl_amount` is written **before** the `closed` feed
  event renders (`lifecycle_embeds.py` around line 460 against the settle path
  in `tracking/performance.py` / `account._settle_account_balance`). If it is
  written after, the plan must reorder delivery or read `settle_legs` on the
  record's legs (the same fallback `account._sum_realized_pnl` uses). Shipping
  a close that always says "R only" does not meet this spec.

All dollar strings go through the existing `plan_table.signed_money`. It moves
into `presentation/tokens.py` (as `fmt_money`, re-exported from `plan_table`
so its three existing callers are unchanged), because `instructions.py` must
not import from `scanning`. Risk is shown unsigned (`$250`); every P&L figure
is signed (`+$181.00` / `-$250.00`).

### 2. Symbol table

One table in `presentation/tokens.py`, `FEED_SYMBOLS`, owns every glyph. No
glyph literal is written in `instructions.py`.

| key | glyph | replaces |
|---|---|---|
| `entry` | ▶ | the entry line's lead |
| `risk` | ⚠ | `(risk $X)` |
| `stop` | 🛑 | the stop line's lead |
| `tp1` | 💰 | `TP1` label |
| `runner` | 🏃 | `RUNNER` label |
| `tp2` | 🎯 | `TP2` label |
| `trail` | 〜 | `trail` |
| `breakeven` | ⚖ | `Stop → entry once price reaches` |
| `expiry` | ⏳ | `Cancel if: not triggered by the close of` |
| `invalid` | ❌ | `or price reaches … first` |
| `locked` | 🔒 | stop-move locked-in figure |
| `pnl` | 💵 | a P&L figure's lead |
| `win` / `loss` / `flat` | ✅ / ❌ / ➖ | close headline lead, by the same ±0.05R tone bands `_closed` already uses |

Target layouts (approved). The broker verbs stay as words:

```
▶ BUY STOP 182.40 · 54 sh · ⚠ $250
🛑 SELL STOP 177.80
💰 SELL LIMIT 189.10 · 27 sh → +$181.00 · +1.5R
🏃 27 sh → 🎯 195.00 / 〜 2×ATR
⚖ stop→entry at ≥ 185.00
⏳ ≤ Thu 22 Oct (5) · ❌ if ≤ 177.80
```

```
✅ EXITED @ 191.20 · 🎯 TP2
💵 +$412.50 · +1.65R
```

- **TP1 partial:** `💰 TP1 FILLED 27 sh @ 189.10 · 💵 +$181.00 · +1.5R`, then
  `🛑 MOVE STOP on the runner → 182.40 now (runner floor)`.
- **Stop move:** `🛑 MOVE STOP → 186.00 now`, then `🔒 +$X · +R locked`. The
  locked figure is the R of the remaining position if the new stop fills,
  plus any banked legs. The plan brief derives it from
  `legs_realized` and the new stop with `total_r`'s arithmetic. It is a
  projection, so it uses `r × risk_amount`, never `realized_amount`.
- **Ticket R projection:** TP1's R is `(tp1 − entry) / (entry − stop)`,
  signed by direction. TP2 shows its R only when `plan.tp2` is set. The
  runner's trail has no fixed price, so it gets no figure.
- Short-side and `≤`/`≥` comparison glyphs flip with `direction` (a short's
  stop is *above*: `❌ if ≥`, `⚖ at ≤`).
- Warnings (heat, cluster, kill switch), cancel reasons, extended-hours and
  time-exit text keep their current wording. They are rare, read carefully,
  and are prose by nature. Only their lead label gets a symbol where the
  table has one.
- The phone push-preview line (`kinds.py` registry, v110) is **unchanged**.
  It already leads with a kind glyph.
- **Legend:** `!help` gains one line listing the table, generated from
  `FEED_SYMBOLS`, so the legend cannot drift from what the feed sends.

The legacy `_legacy_simple_alert` (taken only when `PLAN_ENGINE_V2` is not
`on`) is **out of scope**. Production runs v2. Its 🎯/💰/🛑 one-liner stays
as is.

### 3. Buttons

- The feed ticket (`build_simple_alert` → `alerts.py` simple-channel post)
  and every feed lifecycle message (`lifecycle_embeds.py`'s feed send) attach
  a view built by a new `commands/views.py` factory, `feed_view(plan_id,
  open_)`:
  - always: the existing persistent `ChartButton`, `BreakdownButton` and
    `WatchButton` DynamicItems, constructed exactly as `PlanActionView` does
    (`author_id=None`), so their handlers, custom_id templates and restart
    persistence are reused unchanged;
  - when `open_` (plan status `ACTIVE` or `PARTIAL`): a new `PnlNowButton`
    DynamicItem, `custom_id` = `custom_id_for("pnl", plan_id, None)`,
    registered with the other DynamicItems at bot start.
- **Dismiss is not added.** The feed is an order log, not a board to prune.
- **💵 P&L now** replies **ephemerally** with: last price, unrealised move
  in %, R and $ for the open fraction, banked R and $ from `legs_realized`,
  and their total. The price comes from the same source `!pnl` uses
  (`scan_run.get_all_unrealized_pnl`'s per-trade path, factored into a
  single-trade function rather than duplicated). The money comes from the
  linked trade record (§1). A closed or cancelled plan replies with its
  final result instead of a live price. A price fetch failure replies
  `price unavailable`, never an exception. The button never posts in the
  channel.
- **Sending with a view:** the plan brief checks whether
  `ui.push_kwargs(embed)` accepts or forwards a `view`. If it does not, it is
  extended to (`push_kwargs(embed, view=None)`), so the push-preview
  `content` line survives (known-traps § Legacy shims: a bare
  `send(embed=…)` drops it). The history-channel copy of a lifecycle message
  gets the same view.
- A message built before this ships has no buttons. Nothing is edited
  retroactively.

## Out of scope

- The full-alert channel, closed-trades and retrospective embeds (they
  already show money).
- `_legacy_simple_alert` (non-v2 path).
- Recording whether the reader placed the order (D3: not chosen).
- Any change to sizing, stops, targets or what gets alerted.

## Testing

- **Projection unit tests** (`tests/` beside the existing
  `test_simple_alerts.py` / instructions tests): `Money` with long and short,
  win, loss, scratch, `None` shares, `None` risk, `None` realised (the close
  shows R only), TP2 absent, a TP1 leg, a stop move with and without banked
  legs. Signs are asserted on the rendered string.
- **Symbol-table test:** every `FEED_SYMBOLS` key is used by at least one
  rendered message, and no message carries a symbol glyph literal outside the
  table (grep-style test over `instructions.py`).
- **Broker-verb guard test:** every rendered ticket and lifecycle message
  still contains its order verb as plain text (`BUY STOP`, `SELL LIMIT`, …).
  This is D2's safety rule, enforced.
- **Button tests:** `PnlNowButton` custom_id round-trip through its template;
  `feed_view` includes P&L now only for `ACTIVE`/`PARTIAL`; the ephemeral
  reply for an open, a closed and a price-unavailable plan.
- **alert-surface gate:** a rendered before/after for every feed message kind
  (ticket place, ticket do-not-place, filled, be_moved, tp1_partial,
  stop_moved, closed win, closed loss, closed unsettled, close at market,
  cancel, time exit due), committed as a results note in the plan's final
  task. A green suite alone does not pass this gate.
- Complexity < 15 for every touched function (`radon cc`).

## Parallelisation (guidance for the plan)

- §1 Money (dataclass, `fmt_money` move, record lookup, settle-order fix) is
  first. §2 symbols rewrite the same `instructions.py` lines, so they follow §1
  rather than run beside it.
- §3 buttons touch `commands/views.py`, `bot_core` registration and the two
  send sites. They are independent of §2 and can run beside it once §1's
  record lookup exists, because P&L now reuses it.
- The before/after render, `!help` legend and full suite come last.
