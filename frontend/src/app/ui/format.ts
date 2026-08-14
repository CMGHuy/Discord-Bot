/* Value formatting shared by every table and detail view.
 *
 * One rule runs through all of it: **a missing value renders as an em dash,
 * never as zero and never as blank.** Most of this data comes from trades that
 * may not have closed, priced or been sized yet, and on a P&L or a balance the
 * difference between "no value" and "zero" is the difference between "we don't
 * know" and "you made nothing".
 */

export const ABSENT = '—';

export function num(value: number | null | undefined, decimals = 2): string {
  return value === null || value === undefined ? ABSENT : value.toFixed(decimals);
}

/** Percentages carry an explicit sign, so a gain and a loss are told apart
 *  without reading the colour — which matters for the ~8% of people who
 *  cannot rely on the green/red pair at all. */
export function pct(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return ABSENT;
  return `${value > 0 ? '+' : ''}${value.toFixed(decimals)}%`;
}

/** An unsigned percentage: a share or a level, not a movement.
 *
 *  Deliberately not `pct`. That one signs its output because it formats a
 *  CHANGE, and a sign is how a gain is told from a loss without reading the
 *  colour. "TP1 closes +50%" reads as a gain of fifty percent; it means half
 *  the position. Same reasoning as `analytics.columns.ts`'s `rate()`. */
export function share(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined) return ABSENT;
  return `${value.toFixed(decimals)}%`;
}

export function rMultiple(value: number | null | undefined): string {
  if (value === null || value === undefined) return ABSENT;
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}R`;
}

/** Holding period, at the precision a swing trader actually reads: hours
 *  under a day, then days. "73.4 hours" is arithmetic; "3d 1h" is an answer. */
export function held(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return ABSENT;
  if (hours < 24) return `${Math.round(hours)}h`;
  const days = Math.floor(hours / 24);
  const rest = Math.round(hours % 24);
  return rest === 0 ? `${days}d` : `${days}d ${rest}h`;
}

/** Dates are rendered in the viewer's locale rather than as the raw ISO
 *  string the API returns. Time is included only where it is meaningful. */
export function dateTime(iso: string | null | undefined): string {
  if (!iso) return ABSENT;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return ABSENT;
  return parsed.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function date(iso: string | null | undefined): string {
  if (!iso) return ABSENT;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return ABSENT;
  return parsed.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

export function text(value: string | null | undefined): string {
  return value === null || value === undefined || value === '' ? ABSENT : value;
}
