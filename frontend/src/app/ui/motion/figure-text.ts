/**
 * A pre-formatted figure taken apart so it can be counted (spec v168 §3 #3).
 *
 * `StatTile` receives its value already formatted by the page (`'68%'`,
 * `'+$1,240'`, `'+1.23R'`) and deliberately never formats a number itself.
 * Counting it up needs the number back out: the first number in the text is
 * the value, everything before it (sign, currency) the prefix, everything after
 * it the suffix. `formatFigureText(parts, parts.value)` returns the original
 * text exactly.
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

export function formatFigureText(parts: FigureText, value: number): string {
  const body = value.toLocaleString('en-US', {
    minimumFractionDigits: parts.decimals,
    maximumFractionDigits: parts.decimals,
    useGrouping: parts.grouped,
  });
  return `${parts.prefix}${body}${parts.suffix}`;
}
