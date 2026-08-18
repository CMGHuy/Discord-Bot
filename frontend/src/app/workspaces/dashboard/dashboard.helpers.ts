import { TradeRow } from '../../api/models';

/**
 * Pure logic behind the Dashboard's per-group column lists and the
 * projected P&L/R shown on a row that has not closed yet. Split out of
 * dashboard.ts so it is testable without a TestBed (no store, no router, no
 * HTTP) -- the same reason trades.columns.ts holds its own pure functions
 * rather than living inline in trades.ts.
 */

/** Dropped from every Dashboard group's own column order: Direction folds
 *  into the Confidence cell instead (ConfidenceCell's own `direction` input)
 *  so the two do not both spend a full column on one glyph plus a level. */
const DASHBOARD_OMITS_DIRECTION = (key: string) => key !== 'direction';

/** The Closed group's own column order, derived from the shared picker
 *  list: 'now' (a live price) is dropped, since a closed position no longer
 *  has one, and 'hold' -- the completed hold duration, day/hour/minute
 *  precision (`heldPrecise`) -- is inserted immediately before 'opened_at'.
 *  Falls back to the end of the list if 'opened_at' itself is hidden. */
export function deriveClosedVisible(base: readonly string[]): string[] {
  const filtered = base
    .filter((key) => key !== 'now' && key !== 'hold')
    .filter(DASHBOARD_OMITS_DIRECTION);
  const idx = filtered.indexOf('opened_at');
  return idx === -1
    ? [...filtered, 'hold']
    : [...filtered.slice(0, idx), 'hold', ...filtered.slice(idx)];
}

/** The Active/Pending/Partial groups' own column order: 'closed_at' is
 *  dropped, since none of the three has closed. */
export function deriveOpenVisible(base: readonly string[]): string[] {
  return base.filter((key) => key !== 'closed_at').filter(DASHBOARD_OMITS_DIRECTION);
}

/**
 * Reconstitutes the shared picker list from one group's rendered order.
 *
 * `order` is one group's rendered list (`deriveClosedVisible`/
 * `deriveOpenVisible` above), which differs from the shared list `base` by a
 * per-group insertion ('hold', Closed only) or omission ('now' in Closed;
 * 'closed_at' in the other three; 'direction' in all four). Persisting
 * `order` as-is would leak that difference into the shared list and
 * silently drop the omitted column from the other groups' tables too.
 *
 * Drops 'hold' (never part of the picker) and restores whichever of
 * 'now'/'closed_at'/'direction' `order` is missing, at the END rather than
 * its old position -- a drag in one group's table moving a column that
 * belongs to a DIFFERENT group is a rare cross-table edge case, and losing
 * exact position there is a smaller cost than the reinsertion logic needed
 * to preserve it.
 */
export function reconcileReorder(order: readonly string[], base: readonly string[]): string[] {
  const merged = order.filter((key) => key !== 'hold');
  for (const key of ['now', 'closed_at', 'direction']) {
    if (base.includes(key) && !merged.includes(key)) merged.push(key);
  }
  return merged;
}

/** The entry price to project from: the fill itself once there is one, else
 *  the trigger a stop-entry PENDING plan is still waiting on -- same
 *  fallback PlanCell already uses for its own first-number display
 *  (`showsTrigger`), so a not-yet-triggered PENDING row still gets a
 *  projection instead of falling straight to an em dash. */
function effectiveEntry(row: Pick<TradeRow, 'entry' | 'trigger_price'>): number | null {
  return row.entry ?? row.trigger_price;
}

/** The %-move from `entry` to `price`, signed by direction -- the shared
 *  arithmetic behind `expectedPnlPct`, `expectedSlPct` and `livePnlPct`,
 *  which differ only in which price they project to. Same formula
 *  dashboard.py's `closed_pnl` uses, with `price` standing in for
 *  `exit_price`. */
function pctMoveTo(entry: number, price: number, direction: string): number {
  const raw = ((price - entry) / entry) * 100;
  return direction === 'bullish' ? raw : -raw;
}

/** What `row.pnl_pct` would be if price reaches `target`. Null (renders as
 *  an em dash) once there is no entry price (planned or trigger) or target
 *  to project from at all. */
export function expectedPnlPct(
  row: Pick<TradeRow, 'entry' | 'trigger_price' | 'target' | 'direction'>,
): number | null {
  const entry = effectiveEntry(row);
  const { target, direction } = row;
  if (!entry || target === null) return null;
  return pctMoveTo(entry, target, direction);
}

/** What `row.pnl_pct` would be if price reaches `stop_loss` -- the loss side
 *  of the same projection `expectedPnlPct` makes for the target. Normally
 *  negative (a stop sits on the losing side of entry by construction), but
 *  this does not assume that -- it is the same signed move formula, just
 *  aimed at the other price. */
export function expectedSlPct(
  row: Pick<TradeRow, 'entry' | 'trigger_price' | 'stop_loss' | 'direction'>,
): number | null {
  const entry = effectiveEntry(row);
  const { stop_loss, direction } = row;
  if (!entry || stop_loss === null) return null;
  return pctMoveTo(entry, stop_loss, direction);
}

/** The LIVE P&L% at `current_price` -- not a projection, what the position
 *  is actually doing right now. Sits beside `expectedPnlPct`/`expectedSlPct`
 *  in the Active/Pending/Partial P&L cell so "where it is" and "where it's
 *  headed" read as one line. Null once there is no entry price or no live
 *  price yet (a PENDING plan that has not triggered has neither a fill to
 *  measure from nor a reason to have a current price attached). */
export function livePnlPct(
  row: Pick<TradeRow, 'entry' | 'trigger_price' | 'current_price' | 'direction'>,
): number | null {
  const entry = effectiveEntry(row);
  const { current_price, direction } = row;
  if (!entry || current_price === null) return null;
  return pctMoveTo(entry, current_price, direction);
}

/** The LIVE unrealized dollar P&L at `current_price` -- pairs with
 *  `livePnlPct` the way the Closed table pairs `pnl_pct` with
 *  `realized_pnl_amount`.
 *
 *  Deliberately scaled by `open_shares`, not `shares`: a PARTIAL position
 *  already closed part of itself at TP1, so `shares` (the ORIGINAL size at
 *  open) overstates what is actually still exposed to further price
 *  movement. The percentage is unaffected -- it is priced off one share --
 *  but the dollar figure on a PARTIAL row is smaller than the same price
 *  move would produce on the full original size, and this is what makes
 *  that true instead of silently overstating it. Null (renders as nothing,
 *  not a stray "($0.00)") whenever there is no fill yet -- a PENDING plan
 *  has no shares bought and so no dollar figure to show, even though its
 *  live PERCENTAGE already projects off the trigger. */
export function liveUnrealizedAmount(
  row: Pick<TradeRow, 'entry' | 'current_price' | 'open_shares' | 'direction'>,
): number | null {
  const { entry, current_price, open_shares, direction } = row;
  if (entry === null || current_price === null || open_shares === null) return null;
  const raw = (current_price - entry) * open_shares;
  return direction === 'bullish' ? raw : -raw;
}

/** Same idea for R -- `closed_r`'s formula with `target` standing in for
 *  `exit_price`, which is exactly the reward:risk ratio a hit target
 *  delivers. */
export function expectedR(
  row: Pick<TradeRow, 'entry' | 'trigger_price' | 'target' | 'stop_loss' | 'direction'>,
): number | null {
  const entry = effectiveEntry(row);
  const { target, stop_loss, direction } = row;
  if (entry === null || target === null || !stop_loss) return null;
  const risk = Math.abs(entry - stop_loss);
  if (!risk) return null;
  const reward = direction === 'bullish' ? target - entry : entry - target;
  return reward / risk;
}
