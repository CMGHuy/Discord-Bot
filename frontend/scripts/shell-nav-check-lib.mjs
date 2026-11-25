/**
 * Pure helpers for shell-nav-check.mjs (v247 V247-16, spec v240 §9, §11):
 * flags, the viewports, the lists the check expects, and its verdicts.
 * No browser here, so `node --test` covers all of it.
 */
export const DEFAULT_BASE = 'http://localhost:1234';
export const MIN_TARGET_PX = 44;
export const RAIL_WIDTH_PX = 64;

/** 320 for the five-tab bar, 390 for the editor, 820 and 1440 for the rail. */
export const VIEWPORTS = Object.freeze([
  { name: 'phone-narrow', width: 320, height: 640 },
  { name: 'phone', width: 390, height: 844 },
  { name: 'tablet', width: 820, height: 1180 },
  { name: 'desktop', width: 1440, height: 900 },
]);

export const RAIL_PATHS = Object.freeze(['/dashboard', '/watchlist', '/trades', '/calendar', '/risk', '/insights', '/system']);
export const DEFAULT_TABS = Object.freeze(['Home', 'Watchlist', 'Trades', 'Calendar', 'More']);
/** After the round-trip's edits: Watchlist removed, Risk added. */
export const EDITED_TABS = Object.freeze(['Home', 'Trades', 'Calendar', 'Risk', 'More']);
export const EDITED_PATHS = Object.freeze(['/dashboard', '/trades', '/calendar', '/risk']);

const FLAGS = new Set(['--base', '--out']);

export function parseArgs(argv) {
  const opts = { base: DEFAULT_BASE, out: null };
  for (let i = 0; i < argv.length; i += 2) {
    const flag = argv[i];
    const value = argv[i + 1];
    if (!FLAGS.has(flag) || value === undefined) throw new Error(`unknown or incomplete flag ${flag}`);
    opts[flag.slice(2)] = flag === '--base' ? value.replace(/\/+$/, '') : value;
  }
  return opts;
}

/** The names of boxes under `min` px on either side; half a pixel is rounding. */
export function smallTargets(boxes, min = MIN_TARGET_PX) {
  return boxes.filter((box) => box.width < min - 0.5 || box.height < min - 0.5).map((box) => box.name);
}

/** null when a rail link's tooltip is shown and reads the link's name; else the first thing wrong. */
export function tooltipVerdict({ name, tooltip, visible }) {
  if (!name) return 'no-name';
  if (tooltip === null) return 'no-tooltip';
  if (!visible) return 'not-shown';
  return tooltip === name ? null : 'tooltip-not-name';
}

export function sameList(actual, expected) {
  return actual.length === expected.length && actual.every((value, index) => value === expected[index]);
}

export function exitCode(results) {
  return results.every((result) => result.ok) ? 0 : 1;
}

export function formatResult({ name, ok, detail }) {
  return `${ok ? 'PASS' : 'FAIL'} ${name}${!ok && detail ? ` -- ${detail}` : ''}`;
}
