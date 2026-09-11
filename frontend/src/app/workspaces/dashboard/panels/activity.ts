import { TradeRow } from '../../../api/models';

export interface ActivityEvent {
  kind: 'opened' | 'closed' | 'cancelled';
  /** ISO instant. Never synthesised — a row with no timestamp is skipped. */
  at: string;
  ticker: string;
  detail: string;
  /** Stable across refetches, so the list does not re-animate: one row can
   *  produce two events, so the row id alone would not be unique. */
  id: string;
}

const DEFAULT_LIMIT = 6;

/**
 * The activity feed, derived from trade rows already fetched — v85 D15.
 *
 * There is no backend event log, so this is the honest maximum: what the trade
 * records themselves can date. Three kinds, not the mockup's four — no row
 * carries a TP1 timestamp (`banked_at` does not exist), and no "system scan"
 * or "price alert" event exists anywhere in this bot.
 */
export function deriveActivity(
  rows: readonly TradeRow[],
  limit: number = DEFAULT_LIMIT,
): ActivityEvent[] {
  const events: ActivityEvent[] = [];

  for (const row of rows) {
    const ticker = row.ticker;

    if (row.closed_at) {
      const cancelled = row.status?.toUpperCase() === 'CANCELLED';
      events.push({
        kind: cancelled ? 'cancelled' : 'closed',
        at: row.closed_at,
        ticker,
        detail: cancelled
          ? 'Plan cancelled before filling'
          : `Closed${row.r_multiple != null ? ` at ${row.r_multiple > 0 ? '+' : ''}${row.r_multiple.toFixed(2)}R` : ''}`,
        id: `${row.id}:${cancelled ? 'cancelled' : 'closed'}`,
      });
    }

    if (row.opened_at) {
      events.push({
        kind: 'opened',
        at: row.opened_at,
        ticker,
        detail: `${row.direction === 'bearish' ? 'Short' : 'Long'}${row.entry != null ? ` at ${row.entry}` : ''}`,
        id: `${row.id}:opened`,
      });
    }
  }

  return events
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, limit);
}
