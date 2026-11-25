/**
 * Pure helpers for v246-bar-alignment-check.mjs (v246 V246-18; spec v246 "Three devices",
 * index Handoff 9): the bars, the widths, the expected control height and the verdicts.
 * No browser here, so `node --test` covers all of it.
 */
export { exitCode, formatResult } from './shell-nav-check-lib.mjs';

export const DEFAULT_BASE = 'http://localhost:1234';
export const BOTTOM_TOLERANCE_PX = 1;

/** Phone, tablet, desktop: 820 (not 768) is the tablet the spec's findings were seen at. */
export const VIEWPORTS = Object.freeze([
  { name: 'phone', width: 390, height: 844 },
  { name: 'tablet', width: 820, height: 1180 },
  { name: 'desktop', width: 1440, height: 900 },
]);

/** `--control-h`: 44px below 1024px, 28px from 1024px (styles/tokens.css). */
export function controlHeightAt(width) {
  return width < 1024 ? 44 : 28;
}

/** Every bar a v246 task wraps in sb-field (V246-7..V246-10), and where it lives. */
export const BARS = Object.freeze([
  { name: 'trades', path: '/trades', bar: 'sb-toolbar' },
  { name: 'calendar', path: '/calendar', bar: 'sb-control-row[align="end"]' },
  { name: 'analytics', path: '/insights/analytics', bar: 'sb-control-bar' },
  { name: 'watchlist', path: '/watchlist', bar: 'sb-toolbar' },
  { name: 'dashboard', path: '/dashboard', bar: 'sb-equity-candles .controls' },
]);

/** The layout-audit checks this plan answers for on the bar pages (index Goal). */
export const AUDIT_CHECKS = Object.freeze(['overflow', 'tap', 'text']);

const FLAGS = new Set(['--base', '--out', '--audit']);

export function parseArgs(argv) {
  const opts = { base: DEFAULT_BASE, out: null, audit: null };
  for (let i = 0; i < argv.length; i += 2) {
    const flag = argv[i];
    const value = argv[i + 1];
    if (!FLAGS.has(flag) || value === undefined) throw new Error(`unknown or incomplete flag ${flag}`);
    opts[flag.slice(2)] = flag === '--base' ? value.replace(/\/+$/, '') : value;
  }
  return opts;
}

/** Boxes `{ name, top, bottom }` as visual rows: a box joins the first row its vertical centre falls in. */
export function groupRows(boxes) {
  const rows = [];
  for (const box of [...boxes].sort((a, b) => a.top - b.top)) {
    const centre = (box.top + box.bottom) / 2;
    const row = rows.find((r) => centre >= r.top && centre <= r.bottom);
    if (row) {
      row.boxes.push(box);
      row.top = Math.min(row.top, box.top);
      row.bottom = Math.max(row.bottom, box.bottom);
    } else {
      rows.push({ top: box.top, bottom: box.bottom, boxes: [box] });
    }
  }
  return rows.map((row) => row.boxes);
}

/** One message per row whose bottoms spread past the tolerance; [] when every row lines up. */
export function bottomVerdict(boxes, tolerance = BOTTOM_TOLERANCE_PX) {
  return groupRows(boxes).flatMap((row, index) => {
    const bottoms = row.map((box) => box.bottom);
    if (Math.max(...bottoms) - Math.min(...bottoms) <= tolerance) return [];
    return [`row ${index + 1}: ${row.map((box) => `${box.name}=${box.bottom.toFixed(1)}`).join(' ')}`];
  });
}

/** Controls `{ name, height }` that are not `expected` px tall; under half a pixel is rounding. */
export function heightVerdict(controls, expected) {
  return controls.filter((c) => Math.abs(c.height - expected) >= 0.5).map((c) => `${c.name}=${c.height.toFixed(1)}`);
}

/** The audit's unallowed findings on the bar pages, for the checks this plan answers for. */
export function auditVerdict(unallowed, routes = BARS.map((b) => b.path), checks = AUDIT_CHECKS) {
  return unallowed
    .filter((f) => routes.includes(f.route) && checks.includes(f.check))
    .map((f) => `${f.route} @${f.width} ${f.check} ${f.selector} -- ${f.detail}`);
}
