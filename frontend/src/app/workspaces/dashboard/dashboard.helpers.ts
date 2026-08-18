import { TradeRow } from '../../api/models';

/**
 * Pure logic behind the Dashboard's per-group column lists and the
 * projected P&L/R shown on a row that has not closed yet. Split out of
 * dashboard.ts so it is testable without a TestBed (no store, no router, no
 * HTTP) -- the same reason trades.columns.ts holds its own pure functions
 * rather than living inline in trades.ts.
 */

/** The Closed group's own column order, derived from the shared picker
 *  list: 'now' (a live price) is dropped, since a closed position no longer
 *  has one, and 'hold' -- the completed hold duration, day/hour/minute
 *  precision (`heldPrecise`) -- is inserted immediately before 'opened_at'.
 *  Falls back to the end of the list if 'opened_at' itself is hidden. */
export function deriveClosedVisible(base: readonly string[]): string[] {
  const filtered = base.filter((key) => key !== 'now' && key !== 'hold');
  const idx = filtered.indexOf('opened_at');
  return idx === -1
    ? [...filtered, 'hold']
    : [...filtered.slice(0, idx), 'hold', ...filtered.slice(idx)];
}

/** The Active/Pending/Partial groups' own column order: 'closed_at' is
 *  dropped, since none of the three has closed. */
export function deriveOpenVisible(base: readonly string[]): string[] {
  return base.filter((key) => key !== 'closed_at');
}

/**
 * Reconstitutes the shared picker list from one group's rendered order.
 *
 * `order` is one group's rendered list (`deriveClosedVisible`/
 * `deriveOpenVisible` above), which differs from the shared list `base` by a
 * per-group insertion ('hold', Closed only) or omission ('now' in Closed;
 * 'closed_at' in the other three). Persisting `order` as-is would leak that
 * difference into the shared list and silently drop the omitted column from
 * the other groups' tables too.
 *
 * Drops 'hold' (never part of the picker) and restores whichever of
 * 'now'/'closed_at' `order` is missing, at the END rather than its old
 * position -- a drag in one group's table moving a column that belongs to a
 * DIFFERENT group is a rare cross-table edge case, and losing exact position
 * there is a smaller cost than the reinsertion logic needed to preserve it.
 */
export function reconcileReorder(order: readonly string[], base: readonly string[]): string[] {
  const merged = order.filter((key) => key !== 'hold');
  for (const key of ['now', 'closed_at']) {
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

/** What `row.pnl_pct` would be if price reaches `target` -- the same
 *  formula dashboard.py's `closed_pnl` uses, with `target` standing in for
 *  `exit_price`. Null (renders as an em dash) once there is no entry price
 *  (planned or trigger) or target to project from at all. */
export function expectedPnlPct(
  row: Pick<TradeRow, 'entry' | 'trigger_price' | 'target' | 'direction'>,
): number | null {
  const entry = effectiveEntry(row);
  const { target, direction } = row;
  if (!entry || target === null) return null;
  const raw = ((target - entry) / entry) * 100;
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
