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

/** A realised P&L amount, signed like `pct` -- it is the same gain/loss the
 *  percentage names, just in currency rather than relative terms, so the two
 *  read the same way at a glance. `unit` comes from
 *  `ConnectionStore.currency()`, never a literal — see `MetricCard`'s note
 *  on why. */
export function money(value: number | null | undefined, unit: string, decimals = 2): string {
  if (value === null || value === undefined) return ABSENT;
  return `${value > 0 ? '+' : ''}${value.toFixed(decimals)} ${unit}`;
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

/** A COMPLETED hold duration, at day/hour/minute precision -- unlike `held`,
 *  which rounds to the nearest hour because it measures a LIVE position's
 *  continuously-ticking age (minute-level jitter would be noise on a number
 *  that changes every render). A closed trade's hold period is fixed, so the
 *  extra precision is signal rather than noise. */
export function heldPrecise(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return ABSENT;
  const totalMinutes = Math.round(hours * 60);
  const days = Math.floor(totalMinutes / 1440);
  const hrs = Math.floor((totalMinutes % 1440) / 60);
  const mins = totalMinutes % 60;
  const parts: string[] = [];
  if (days) parts.push(`${days}d`);
  if (hrs) parts.push(`${hrs}h`);
  if (mins || parts.length === 0) parts.push(`${mins}m`);
  return parts.join(' ');
}

/**
 * How long ago, coarsely — "4h", "3d", "2mo".
 *
 * For the Age of a plan, which is read as "is this stale?" rather than as a
 * timestamp. `held` is the same idea for a duration that is already computed
 * server-side; this one measures from a point in time to now, so it is a
 * different question and a different unit ladder — past a month, days stop
 * being the useful unit.
 */
export function age(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return ABSENT;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return ABSENT;
  const hours = Math.max(0, (now - then) / 3_600_000);
  if (hours < 1) return '<1h';
  if (hours < 24) return `${Math.floor(hours)}h`;
  const days = Math.floor(hours / 24);
  if (days < 60) return `${days}d`;
  return `${Math.floor(days / 30)}mo`;
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

/** A 24-hour clock time in an EXPLICIT timezone, not the viewer's own --
 *  for the Watchlist Earnings calendar, which shows both UTC and
 *  Europe/Berlin side by side so the two are directly comparable regardless
 *  of what timezone the browser itself is in. `Intl.DateTimeFormat`'s
 *  `timeZone` option handles the DST transition correctly on either side
 *  (Europe/Berlin shifts between CET and CEST; UTC never does), which a
 *  fixed offset could not. */
export function timeInZone(iso: string | null | undefined, timeZone: string): string {
  if (!iso) return ABSENT;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return ABSENT;
  return parsed.toLocaleTimeString('en-GB', { timeZone, hour: '2-digit', minute: '2-digit' });
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

/**
 * A signed figure, with the sign carried by a glyph as well as by colour.
 *
 * Colour is never the only channel: a screenshot pasted into Discord keeps
 * the hue but a colour-blind reader does not, and `--pos`/`--neg` are close
 * enough in lightness that a greyscale print loses them entirely.
 *
 * The minus is U+2212, not a hyphen. A hyphen is narrower than a digit even
 * in a mono face, so a column of hyphen-negatives does not align with a
 * column of positives — which defeats the tabular numerics the whole numeric
 * law rests on. Zero takes no sign, because it has none.
 */
export function signed(value: number | null | undefined, decimals = 2): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return ABSENT;
  if (value === 0) return num(0, decimals);
  return value > 0 ? `+${num(value, decimals)}` : `−${num(Math.abs(value), decimals)}`;
}
