import {
  BandCurrent, BandDollars, BandExpR, BandHorizon, BandQuantiles, BandZone, VarianceBandOk,
} from '../../../api/models';
import { ABSENT, rMultiple } from '../../../ui/format';

/* v175 — every word of the "Normal bad luck" panel, and the arithmetic that
 * places its segments and marker. Pure: no Angular, no store, no DOM.
 *
 * The copy is fixed by the spec and reviewed by the financial-advisor seat:
 * it describes and never instructs (no sentence opens with stop, check, skip,
 * size or review), and it never says "edge" -- the band shows the range this
 * book's PAST trades produce by chance, which is not a claim that the book
 * has one. */

export const PANEL_TITLE = 'Normal bad luck';
export const HEADER_COPY = "Whole book, closed trades only. Filters don't apply.";
export const CAVEAT = "This book's past results are not positive. A run within their range is still a losing run.";
export const CAPTION =
  "Simulated from this book's closed trades, resampled by week. It shows the range of losing runs these past "
  + "results produce by chance; it is not a forecast. Checked continuously, so 'beyond 95%' will sometimes "
  + 'appear by chance alone. Paper book, before tax.';

export const ZONE_COPY: Record<BandZone, string> = {
  normal: "Within the range this book's past trades produce",
  rough: 'Deeper than 80% of simulated runs, within 95%',
  outside: 'Beyond 95% of simulated runs',
};

export const BAR_LABELS = {
  run: 'Losing days in a row',
  drawdown: 'Drawdown over the last 50 close days',
} as const;

const ZONE_LABEL: Record<BandZone, string> = { normal: 'Normal', rough: 'Rough', outside: 'Outside' };

export type BandUnit = 'days' | 'R';

/** One labelled segment of a band bar; `width` is its share of the bar in %. */
export interface BandSegment {
  zone: BandZone;
  label: string;
  range: string;
  width: number;
}

type Cuts = { p80: number; p95: number };

const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? '' : 's'}`;

/** A bare number in the unit's precision: integers for days, 1 dp for R. */
const bare = (value: number, unit: BandUnit): string => (unit === 'days' ? String(value) : value.toFixed(1));

/** A number with its unit: `3 days`, `1 day`, `2.4R`. */
const withUnit = (value: number, unit: BandUnit): string =>
  unit === 'days' ? plural(value, 'day') : `${value.toFixed(1)}R`;

/** The bar runs 0 → scaleMax: a quarter past p95 so the outside segment has
 *  room, and at least p95 + 1 so an all-win book (p95 = 0) still draws. */
export function scaleMax(q: Cuts): number {
  return Math.max(q.p95 * 1.25, q.p95 + 1);
}

/** normal ≤ p80 < rough ≤ p95 < outside; rough is omitted on a tie. */
export function bandSegments(q: Cuts, unit: BandUnit): BandSegment[] {
  const max = scaleMax(q);
  const share = (span: number): number => (span / max) * 100;
  const segments: BandSegment[] = [
    { zone: 'normal', label: ZONE_LABEL.normal, range: `≤ ${withUnit(q.p80, unit)}`, width: share(q.p80) },
  ];
  if (q.p95 > q.p80) {
    segments.push({
      zone: 'rough', label: ZONE_LABEL.rough,
      range: `> ${bare(q.p80, unit)} to ≤ ${withUnit(q.p95, unit)}`, width: share(q.p95 - q.p80),
    });
  }
  segments.push({ zone: 'outside', label: ZONE_LABEL.outside, range: `> ${withUnit(q.p95, unit)}`, width: share(max - q.p95) });
  return segments;
}

/** Where `value` sits on the bar, in %, clamped to [0, 100]. */
export function markerPercent(value: number, q: Cuts): number {
  const percent = (value / scaleMax(q)) * 100;
  return Math.min(100, Math.max(0, percent));
}

/** Unsigned, symbol first, grouped: `$1,312.35`. The same text the
 *  book-status message shows (`fmt_money` with its sign stripped). */
export function moneyText(value: number, currency: string): string {
  const digits = Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${currency}${digits}`;
}

export function runMarkerText(cur: BandCurrent): string {
  const age = cur.run_age_days === null ? '' : `, ${plural(cur.run_age_days, 'calendar day')} long`;
  return `now: ${plural(cur.run, 'day')}${age}`;
}

export function drawdownMarkerText(cur: BandCurrent, dollars: BandDollars | undefined, currency: string): string {
  const usd = dollars ? ` (≈ ${moneyText(dollars.drawdown_usd, currency)})` : '';
  const age = cur.drawdown_age_days === null ? '' : `, ${plural(cur.drawdown_age_days, 'calendar day')} since the peak`;
  return `now: ${cur.drawdown.toFixed(1)}R${usd}${age}`;
}

/** "p95 ≈ 7 (6–8)": the band's own uncertainty across outer resamples. */
export function uncertaintyText(q: BandQuantiles, unit: BandUnit = 'days'): string {
  const suffix = unit === 'R' ? 'R' : '';
  return `p95 ≈ ${bare(q.p95, unit)}${suffix} (${bare(q.p95_lo, unit)}–${bare(q.p95_hi, unit)}${suffix})`;
}

export function spanText(h: BandHorizon): string {
  return `${h.horizon} close days ≈ ${h.weeks_span} weeks at this book's pace`;
}

export function secondaryText(h20: BandHorizon): string {
  return `Over ${h20.horizon} close days: p95 ${h20.run.p95} days in a row, ${h20.drawdown.p95.toFixed(1)}R drawdown`;
}

export function exprLine(e: BandExpR): string {
  return `Book: ExpR ${rMultiple(e.value)} over N=${e.n} trades (${e.start ?? ABSENT} to ${e.end ?? ABSENT})`;
}

export function compositionLine(c: VarianceBandOk['composition']): string {
  const trades = Object.entries(c.trades_by_horizon).map(([horizon, n]) => `${horizon} ${n}`).join(', ');
  return `Close days: ${c.days_by_era.v2} v2, ${c.days_by_era.legacy} legacy · Trades: ${trades || ABSENT}`;
}

export function dollarNote(d: BandDollars, currency: string): string {
  return `≈ $ = R × the median per-trade dollar risk (${moneyText(d.median_risk, currency)}), `
    + 'from shares × entry-to-stop distance.';
}

export function insufficientCopy(days: number, weeks: number): string {
  return `Needs 100 close days over 20 weeks (${days} days, ${weeks} weeks so far).`;
}

/** The bar's text equivalent: every segment's range, then where the book is. */
export function barAriaLabel(label: string, segments: BandSegment[], marker: string): string {
  return `${label}: ${segments.map((s) => `${s.label} ${s.range}`).join(', ')}. ${marker}`;
}
