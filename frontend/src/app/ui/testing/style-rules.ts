import { CHART_CHROME } from '../chart/chart-frame';
import { SVG_CHART_TOKENS } from '../chart/chart-theme';
import { stripComments } from './all-sources';

/**
 * One CSS rule as written in a source file: its selector and the text
 * between its braces, both trimmed. Test-only (spec v240 §1, §2, §11).
 */
export type StyleRule = { selector: string; body: string };

/** Innermost `selector { body }` pairs: an @media, @container or @keyframes
 *  wrapper is skipped and the rules inside it are read. */
const RULE_RE = /([^{};]+)\{([^{}]*)\}/g;

/** A template-literal interpolation inside a style (`var(${TOKEN})`). Its
 *  braces would split a rule, and no gate can see through it anyway. */
const INTERPOLATION_RE = /\$\{[^}]*\}/g;

/**
 * Every CSS rule in one source file, in order, read only from real style
 * text, so a gate never mistakes `if (x) { y(); }` or a template's
 * `{{ v }}` for a rule:
 * - a `.css` file: the whole file;
 * - a `.ts` file: every template literal under a component's `styles:`,
 *   one literal or an array of them;
 * - anything else (`.html`): nothing.
 *
 * Comments are stripped and interpolations become `__expr__`. The selector
 * is the rule's last line, so a stray line above it never leaks in; a
 * selector list broken over lines with trailing commas is joined back.
 * `name` is the file name as allSources() gives it ('app/ui/button.ts').
 */
export function styleRules(name: string, source: string): StyleRule[] {
  const texts = name.endsWith('.css') ? [source] : name.endsWith('.ts') ? stylesLiterals(source) : [];
  return texts.flatMap((text) => rulesIn(stripComments(text).replace(INTERPOLATION_RE, '__expr__')));
}

function rulesIn(css: string): StyleRule[] {
  return [...css.matchAll(RULE_RE)].map(([, selector, body]) => ({ selector: lastSelector(selector), body: body.trim() }));
}

/** The selector's last line, extended upwards over lines that end in a comma. */
function lastSelector(raw: string): string {
  const lines = raw.split('\n').map((line) => line.trim()).filter(Boolean);
  let start = lines.length - 1;
  while (start > 0 && lines[start - 1].endsWith(',')) start--;
  return lines.slice(start).join(' ');
}

/** The text of every template literal under `styles:`, single or in an array. */
function stylesLiterals(source: string): string[] {
  const out: string[] = [];
  for (const match of source.matchAll(/\bstyles:\s*(\[)?/g)) {
    let literal = literalAt(source, match.index! + match[0].length);
    while (literal) {
      out.push(literal.text);
      literal = match[1] ? literalAt(source, literal.end) : null;
    }
  }
  return out;
}

/** The template literal at the first non-separator (space, comma) from `from`, or null. */
function literalAt(source: string, from: number): { text: string; end: number } | null {
  let at = from;
  while (at < source.length && /[\s,]/.test(source[at])) at++;
  if (source[at] !== '`') return null;
  const close = closingBacktick(source, at + 1);
  return close < 0 ? null : { text: source.slice(at + 1, close), end: close + 1 };
}

/** The next unescaped backtick from `from`, or -1. A comment inside a
 * styles literal may quote code as \`icon\` (button.ts does). */
function closingBacktick(source: string, from: number): number {
  let close = source.indexOf('`', from);
  while (close > 0 && source[close - 1] === '\\') close = source.indexOf('`', close + 1);
  return close;
}

const CHART_TOKEN_RE = /\$\{(CHART_CHROME|SVG_CHART_TOKENS)\.(\w+)\}/g;
const CHART_TOKENS: Record<string, Readonly<Record<string, string | number>>> = {
  CHART_CHROME, SVG_CHART_TOKENS,
};

/** Resolve the shared chart tokens so the CSS gates can inspect their final
 * values. Unknown keys and other expressions stay visible to styleRules(). */
export function withChartTokens(source: string): string {
  return source.replace(CHART_TOKEN_RE, (whole, family: string, key: string) => {
    const tokens = CHART_TOKENS[family];
    return Object.hasOwn(tokens, key) ? String(tokens[key]) : whole;
  });
}
