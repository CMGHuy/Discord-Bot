import { reasonLabel } from './exit-reasons';

/**
 * v194 B3 -- the one name for a scale-out leg, everywhere a leg row renders
 * (Trades table, compact rows and drawer, Dashboard positions, Calendar).
 *
 * "Leg N of M", never "TP1"/"Runner": legs are numbered in the order they
 * realised, so leg 1 may be a stop-out and the last leg may exit at the stop
 * or by timeout. When the leg's own exit reason was recorded it follows the
 * label in the trade page's vocabulary (`reasonLabel`).
 */
export interface LegLike {
  leg_index: number;
  leg_total: number;
  /** A `/trades` leg row's own reason (`TradeRow`). */
  leg_exit_reason?: string | null;
  /** A calendar row's reason (`CalendarTrade`), read when the above is absent. */
  exit_reason?: string | null;
}

/** Calendar's catch-all: not a recorded reason, so the label stands alone. */
const UNRECORDED_REASONS: ReadonlySet<string> = new Set(['other']);

/** v194 A4: what the leg rows are. How win rate and N count them differs by
 *  surface (the Dashboard and the Calendar count each realised leg as a
 *  trade, Analytics counts plans), so each surface appends its own sentence. */
export const LEG_HINT_TEXT =
  'These rows are parts of one plan that scaled out, numbered in the order they closed. '
  + "Each row's P&L is that part's share of the plan's result.";

function recordedReason(row: LegLike): string | null {
  const raw = (row.leg_exit_reason ?? row.exit_reason ?? '').trim();
  if (!raw || UNRECORDED_REASONS.has(raw.toLowerCase())) return null;
  return reasonLabel(raw);
}

/** "Leg 2 of 3 · Stop" for a scale-out leg, "Leg 2 of 3" when no reason was
 *  recorded, null for a trade that never scaled out. 1-based. */
export function legLabel(row: LegLike): string | null {
  if (!(row.leg_total > 1)) return null;
  const base = `Leg ${row.leg_index + 1} of ${row.leg_total}`;
  const reason = recordedReason(row);
  return reason ? `${base} · ${reason}` : base;
}
