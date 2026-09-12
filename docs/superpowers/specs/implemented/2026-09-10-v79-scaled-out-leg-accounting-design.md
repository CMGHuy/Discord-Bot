Version: ui 1.12.0 · bot 1.6.2
Bump: bot patch, ui patch
Edge: expectancy

# Scaled-out leg accounting

## Problem

A scaled-out (TP1 + runner) position is stored as one `TradeLog` record with
a `legs`/`legs_realized` array. Two consequences of that, both surfaced by a
2026-09-10 trader report:

1. **Display.** The Trades table's status filter reflects the *whole
   position*. A trade that banked 50% at TP1 shows nothing in `Closed` and
   everything in `Partial`/`Active` until the runner finishes too — sometimes
   days later — even though half the position is, in every real sense,
   already a closed, booked trade.
2. **Stats.** `get_stats`/`get_extended_stats` (win rate, expectancy) count
   the whole position as one outcome, blending the TP1 leg's certain win
   together with whatever the runner eventually does. A trade that gave back
   some of its TP1 gain on the runner reads as one middling win rather than
   "one clean win plus one smaller win," which understates both the win
   count and the true per-shot expectancy this strategy is producing.

## Non-goals

- No change to the underlying ledger schema. One `TradeLog` record per
  position stays the unit of truth — same `id`, same `plan_id` linkage, same
  file.
- No change to what gates *real* open-position management: `status` on the
  ledger record continues to mean "is there still live risk on this
  ticker," and every live-monitoring path that reads it
  (`update_open_trades`, `close_if_live_price_hit`,
  `run_manager_tick`/`PlanManager.poll()`'s open-plan filters) is untouched.
  This spec is a derived display/stats layer on top, not a change to
  position tracking.
- No change to the backtest simulator (`plan_engine._scale_out_exit_walk`).
  Its numbers are a separate, closed measurement; re-deriving them is a
  future backtest re-registration, not part of this spec.

## Design

### `expand_trade_legs(trade: dict) -> list[dict]`

New function in `swingbot/core/tracking/performance.py`, the single place
this repo already computes `settle_legs`/`closed_pnl_pct`/`closed_r_multiple`
over a trade's legs.

For a trade with no `legs` (every legacy/v1 trade, every stop-out that never
scaled out), it returns `[trade]` unchanged — this is what makes it a safe
drop-in replacement for "iterate over trades" everywhere, not a special case
callers have to branch on.

For a trade with realized legs, it yields one synthetic row per leg:

- `shares` = the trade's original `shares * leg["fraction"]`.
- `position_value` scaled the same way.
- `entry` = the trade's own entry (unchanged — every leg shares one entry).
- `exit_price` / `r` = the leg's own `exit_price` / `r`.
- `pnl_amount` = `shares * (exit_price - entry) * sign` (matches the
  per-leg summand `settle_legs` already computes).
- `status` = `"win"` if `r >= 0`, `"loss"` if `r < 0` — derived from the
  leg's own R, not the reason string, and kept inside the existing
  open/win/loss/closed vocabulary every `status` filter and consumer
  already expects (no new status value). (In practice this makes the TP1
  leg always a win, since scale-out only happens after TP1 fires, and the
  runner leg a win unless it's stopped below the runner floor, which the
  floor mechanics don't allow once armed — but the rule is the sign of
  `r`, not a hardcoded assumption, so it stays correct if that ever
  changes.) A leg closed at exactly breakeven (`r == 0`) counts as a win,
  same as the existing whole-trade convention of treating a non-loss as a
  win in the coarse `status` field.
- `id` stays the **real** trade id (see "Row identity" below).
- A new `leg_index` field (0-based) and `leg_total` (how many rows this
  trade expanded into), so a consumer can tell a leg-row from a whole trade
  and reconstruct which position it came from.

If the position is not yet fully closed (the ledger `status` is still
`"open"`), one further row represents the still-open remainder: `shares` =
original shares × the unrealized fraction, no `exit_price`/`r` yet, `status`
= `"open"`. This is what makes "the other half sits in Partial with the
correct sizing" true — today the whole (unreduced) share count shows against
the Partial row; after this, the Partial row's size reflects only the
runner.

### Row identity, for the Trades table

Two rows from one trade now share one `id` (per the "one ledger record"
decision — there is exactly one trade-detail page, showing the whole
position's full history including both legs). The Trades table's row `key`
function (currently just `row.id`) needs a synthetic key —
`` `${row.id}:${row.leg_index}` `` — so Angular's `@for` track and pagination
don't collide on the shared id. Clicking either row still navigates to
`/trades/:id` using the real id, landing on the one detail page for the
whole position.

### Consumers

- `TradeLog.get_stats` / `get_extended_stats` (`performance.py`): call
  `expand_trade_legs` over the trade list before computing win rate,
  expectancy, and every other count-based figure. This is the
  `Edge: expectancy` change — win/loss/scratch counts and R-multiple
  contributions become leg-accurate. Because the function is applied at
  read time, this is automatically retroactive over existing trade history
  with no migration.
- Admin API row-builder (`swingbot/admin/api_v1/trades.py`,
  `swingbot/core/presentation/plan_view.py`): expand before applying the
  `status`/`outcome` filter and before pagination, so `?status=CLOSED`
  genuinely returns the closed leg the moment it's banked, and
  `?status=PARTIAL` returns the correctly-sized remainder.
- Dashboard/analytics aggregates that already route through `get_stats` /
  `get_extended_stats` inherit the corrected counts with no separate change.
- CSV export and the journal: **unchanged, out of scope.** They key off the
  real trade id and are about one position's full narrative, not its
  per-leg breakdown — expanding them is a separate call site this spec does
  not touch.

### Frontend

No new component logic. The API already returns whatever rows it returns;
`TradesStore`/`Trades` renders them. The one required change is the row-key
fix above (`ui/data-table` `rowKey` input at the Trades table's call site),
since duplicate keys are a real Angular correctness bug, not a style
question.

## Testing

- `expand_trade_legs`: no-legs passthrough, two-leg fully-closed trade
  (both rows, correct sizing/status), two-leg trade with an open runner
  (closed row + open-remainder row), win/loss leg classification by `r`
  sign including the `r == 0` win case.
- `get_stats`/`get_extended_stats`: a fixture trade set with one scaled-out
  trade, asserting the win count and N reflect 2 outcomes, and that a
  single-leg legacy trade is unaffected.
- Admin API: `?status=CLOSED` and `?status=PARTIAL` against a partially
  realized trade return the expected single row each, with the expected
  `shares`.
- Frontend: a fixture API response with two rows sharing one `id`
  (different `leg_index`) renders as two table rows, not one.

## Parallelisation

- **Sequential throughout.** `expand_trade_legs` is a shared dependency
  every other change consumes — the stats wiring, the admin API row
  builder, and the frontend row-key fix (which depends on knowing the
  final row shape/`leg_index` field) all build on it in that order. No
  group here is safe to parallelize against another.
