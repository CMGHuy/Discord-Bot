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

/** What each recorded leg reason means, keyed by the label `reasonLabel`
 *  gives it (or the raw reason when unmapped, as `giveback` is). */
const REASON_HELP: Readonly<Record<string, string>> = {
  'TP1': 'The first target was reached, so this part of the position was sold to bank profit.',
  'Runner at T2': 'The runner (the part kept after TP1) reached the second target, T2, and was sold. It sells at the price on that check, '
    + 'so if price had already jumped past T2 the fill can equal the TP1 fill.',
  'Runner at breakeven':
    'After TP1 the runner\'s stop moved up to the entry price. Price came back to it, so the runner closed at about zero, keeping the TP1 profit.',
  'giveback':
    'The runner gave back too much of its best price since TP1 (the give-back percentage in Settings), so it was sold to keep most of the gain.',
  'Runner trailed': 'The runner\'s trailing stop followed price up and was hit, locking in the gain so far.',
  'Stop': 'Price fell to the stop-loss, so this part closed at a loss.',
  'Scratch': 'Closed at about the entry price, for roughly no gain or loss.',
  'Time exit': 'The holding-time limit ran out, so this part was closed at the market price.',
  'Stall exit': 'Price stalled just short of the target, so this part was closed early.',
  'Reversed': 'The setup reversed, so this part was closed.',
  'Bulk close': 'Closed by hand together with other positions.',
};

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

function positionHelp(row: LegLike): string {
  const place = row.leg_index === 0 ? 'the first part of the plan to close'
    : row.leg_index === row.leg_total - 1 ? 'the last part of the plan to close'
    : `part ${row.leg_index + 1} of the plan to close`;
  return `Leg ${row.leg_index + 1} of ${row.leg_total} is ${place}.`;
}

/** The tooltip on a leg's name: which part it is, what its exit reason means,
 *  what a leg row's P&L is, and the page's own note on how it counts legs.
 *  Empty for a trade that never scaled out. */
export function legExplanation(row: LegLike, pageNote = ''): string {
  if (!(row.leg_total > 1)) return '';
  const reason = recordedReason(row);
  const reasonHelp = reason ? (REASON_HELP[reason] ?? '') : '';
  return [positionHelp(row), reasonHelp, LEG_HINT_TEXT, pageNote].filter(Boolean).join(' ');
}
