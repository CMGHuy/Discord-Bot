import type { RowQuoteFields } from '../api/models';
import { ABSENT, num, pct, signed } from './format';
import type { PriceKind } from './position-progress';

/** Spec v248 § 1f: the row fields the position formatters read. */
export type PositionPriceRow = RowQuoteFields & { status: string };

/** Spec v248 § 1e: statuses that hold an open position, so a missing price is a fault. */
export const HELD_STATUSES: ReadonlySet<string> = new Set(['ACTIVE', 'PARTIAL']);

/** Spec v248 § 1d: tag beside a NOW price that is the previous close. */
export const PREV_CLOSE_TAG = 'prev close';
/** Spec v248 § 1d: suffix on a P&L % or R figure computed from the previous close. */
export const PREV_CLOSE_SUFFIX = 'at prev close';
/** Spec v248 § 1e: what a held row with neither a trade nor a close says. */
export const NO_PRICE_TEXT = 'no price yet';
/** Spec v248 § 1e: why there is no price. */
export const NO_PRICE_REASON = 'no trade and no daily close cached';
/** Spec v248 § 1d: the screen-reader text for a prev-close price. */
export const PREV_CLOSE_ARIA = 'price is previous close, not live';

/** Spec v248 § 1f: one figure for P&L % or R, suffixed only when it is a number from a prev close. */
export function positionFigure(
  value: number | null | undefined,
  unit: 'pct' | 'r',
  kind?: PriceKind | null,
): { text: string; suffix: string | null } {
  const text = unit === 'pct' ? pct(value) : signed(value);
  const isNumber = typeof value === 'number' && Number.isFinite(value);
  return { text, suffix: kind === 'prev_close' && isNumber ? PREV_CLOSE_SUFFIX : null };
}

/** Spec v248 § 1f: the figure as one string, for text-only column fallbacks. */
export function figureText(value: number | null | undefined, unit: 'pct' | 'r', kind?: PriceKind | null): string {
  const f = positionFigure(value, unit, kind);
  return f.suffix ? `${f.text} ${f.suffix}` : f.text;
}

/** Spec v248 § 1d: sign colour, muted on a prev-close row (not a live read). */
export function figureTone(value: number | null | undefined, kind?: PriceKind | null): 'pos' | 'neg' | 'muted' | '' {
  if (typeof value !== 'number' || !Number.isFinite(value) || value === 0) return '';
  if (kind === 'prev_close') return 'muted';
  return value > 0 ? 'pos' : 'neg';
}

/** Spec v248 § 1e: '2026-11-24' -> '11-24'. */
export function closeDateTag(date: string | null | undefined): string {
  return date ? date.slice(5) : '';
}

/** Spec v248 § 1e / 1f: the NOW column's text. */
export function positionPriceText(row: PositionPriceRow): string {
  if (row.current_price != null) {
    return row.price_kind === 'prev_close' ? `${num(row.current_price)} ${PREV_CLOSE_TAG}` : num(row.current_price);
  }
  if (row.last_close != null) return `${num(row.last_close)} close ${closeDateTag(row.last_close_date)}`.trim();
  return HELD_STATUSES.has(row.status) ? NO_PRICE_TEXT : ABSENT;
}
