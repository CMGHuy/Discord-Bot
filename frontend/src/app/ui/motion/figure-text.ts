import { MINUS } from '../format';

/**
 * A pre-formatted figure taken apart so it can be counted (spec v168 §3 #3).
 *
 * `StatTile` receives its value already formatted by the page (`'68%'`,
 * `'+$1,240'`, `'+1.23R'`) and deliberately never formats a number itself.
 * Counting it up needs the number back out: the first number in the text is
 * the value, everything before it (sign, currency) the prefix, everything after
 * it the suffix. `formatFigureText(parts, parts.value)` returns the original
 * text with U+2212 for losses and without a sign if it rounds to zero (v240 §1).
 */
export interface FigureText {
  prefix: string;
  value: number;
  decimals: number;
  suffix: string;
  grouped: boolean;
}

/** Lazy non-digit prefix; comma-grouped or plain integer part; optional
 *  fraction; the rest. `s` so a suffix may hold a line break. */
const FIGURE_RE = /^(\D*?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(.*)$/s;

export function parseFigureText(text: string | null): FigureText | null {
  if (text === null) return null;
  const match = FIGURE_RE.exec(text);
  if (!match) return null;
  const [, prefix, whole, fraction = '', suffix] = match;
  const digits = whole.replaceAll(',', '');
  return {
    prefix,
    value: Number(fraction ? `${digits}.${fraction}` : digits),
    decimals: fraction.length,
    suffix,
    grouped: whole.includes(','),
  };
}

/** A sign embedded in the prefix by the page that formatted the figure. */
const LEADING_SIGN = /^(\s*)([+−-])/;

export function formatFigureText(parts: FigureText, value: number): string {
  const body = Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: parts.decimals,
    maximumFractionDigits: parts.decimals,
    useGrouping: parts.grouped,
  });
  // A negative frame keeps a true minus; one that rounds to zero has no sign.
  const zero = Number(body.replaceAll(',', '')) === 0;
  const prefix = parts.prefix.replace(LEADING_SIGN, (_, space: string, sign: string) =>
    space + (zero ? '' : sign === '-' ? MINUS : sign));
  const sign = value < 0 && !zero && !LEADING_SIGN.test(parts.prefix) ? MINUS : '';
  return `${prefix}${sign}${body}${parts.suffix}`;
}
