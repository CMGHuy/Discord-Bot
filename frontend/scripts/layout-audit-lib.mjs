/**
 * The pure half of the v179 layout audit (layout-audit.mjs): the routes it
 * visits, the checks it runs, argument parsing, placeholder resolution,
 * de-duplication and the allow-list verdict. No browser and no I/O, so
 * `node --test frontend/scripts/layout-audit-lib.test.mjs` covers all of it.
 * Spec: docs/superpowers/specs/2026-10-19-v179-mobile-layout-consistency-design.md §3.5, §6a.6.
 */

/** Every route and tab (29) on the v202 paths (spec v202 §2): the old names are redirects and are
 *  not visited. `:id` is a trade id, `:plan` an open (else pending) trade's id, `:symbol` a
 *  watchlist symbol with trades, `:date` the day a closed trade closed -- resolved from the API at
 *  run time. A route or tab added to the app is added here in the same commit. */
export const ROUTES = Object.freeze([
  '/dashboard',
  '/trades', '/trades/:id', '/trades/:id?tab=why', '/trades/:id?tab=chart', '/trades/:id?tab=journal',
  '/trades/calendar', '/trades/calendar/:date', '/trades/cancels',
  '/plans/:plan',
  '/insights/analytics', '/insights/analytics?tab=attribution', '/insights/analytics?tab=execution',
  '/insights/analytics?tab=edge', '/insights/analytics?tab=pipeline', '/insights/analytics?tab=tuning',
  '/insights/analytics?tab=partials',
  '/insights/research', '/insights/reports', '/insights/reports?tab=gates',
  '/watchlist', '/watchlist/:symbol',
  '/risk',
  '/system', '/system?tab=logs', '/system?tab=scan', '/system?tab=providers', '/system?tab=users', '/system/versions',
  '/ui',
]);

export const CHECKS = Object.freeze(['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter', 'hint', 'rail-label', 'dock']);

/** Phone, tablet and desktop (docs/claude/ui-design.md § Device classes). */
export const FULL_WIDTHS = Object.freeze([390, 768, 1440]);
/** The tap check runs at or below this width: the 44px rule covers phone
 *  and tablet, `(pointer: coarse), (max-width: 1023px)` (v179 V179-2). */
export const TOUCH_MAX_WIDTH = 1023;
export const MIN_TAP_PX = 44;
export const MIN_TEXT_PX = 11;
export const MAX_BASELINE_OFFSET_PX = 2;
/** A table cell's content, or an icon beside its text, off centre by more than this. */
export const MAX_CENTER_OFFSET_PX = 2;

const DEFAULTS = Object.freeze({ base: 'http://localhost:1234', out: null, allow: null, prune: false, settle: 1500 });

function parseWidths(value) {
  const widths = value.split(',').map(Number);
  if (widths.some((width) => !Number.isInteger(width) || width < 320)) throw new Error(`bad --widths ${value}`);
  return widths;
}

const FLAGS = {
  '--base': (opts, value) => { opts.base = value.replace(/\/$/, ''); },
  '--widths': (opts, value) => { opts.widths = parseWidths(value); },
  '--out': (opts, value) => { opts.out = value; },
  '--allow': (opts, value) => { opts.allow = value; },
  '--settle': (opts, value) => { opts.settle = Number(value); },
};

export function parseArgs(argv) {
  const opts = { ...DEFAULTS, widths: [...FULL_WIDTHS] };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    if (flag === '--prune') {
      opts.prune = true;
      continue;
    }
    const apply = FLAGS[flag];
    if (!apply || i + 1 >= argv.length) throw new Error(`unknown or incomplete flag ${flag}`);
    i += 1;
    apply(opts, argv[i]);
  }
  return opts;
}

const PLACEHOLDER = /:(id|plan|symbol|date)\b/g;

export function resolveRoute(template, ids) {
  return template.replace(PLACEHOLDER, (_, key) => {
    const value = ids[key];
    if (!value) throw new Error(`no ${key} to visit ${template}: the instance has no such data`);
    return encodeURIComponent(value);
  });
}

/** The ids the placeholders need, from four API answers; null where the
 *  instance has no such row (the CLI then refuses to run, never guesses). */
export function pickIds({ closed, open, pending, tickers }) {
  const trade = closed.items?.[0] ?? null;
  const plan = open.items?.[0] ?? pending.items?.[0] ?? null;
  const ticker = tickers.tickers?.find((t) => t.open_trades + t.closed_trades > 0) ?? null;
  return {
    id: trade?.id ?? null,
    date: trade?.closed_at ? trade.closed_at.slice(0, 10) : null,
    plan: plan?.id ?? null,
    symbol: ticker?.symbol ?? null,
  };
}

/**
 * The standard visually-hidden pattern: out of flow, a 1px box, clipped away.
 * Self-contained -- the audit sends its source into the page (no imports, no closures).
 */
export function isVisuallyHidden(style, rect) {
  const outOfFlow = style.position === 'absolute' || style.position === 'fixed';
  const tiny = rect.width <= 1 && rect.height <= 1;
  const clipped = (style.clipPath && style.clipPath !== 'none') || (style.clip && style.clip !== 'auto');
  return Boolean(outOfFlow && tiny && clipped);
}

/** The vcenter check's geometry, on plain {top, bottom, left, right, height}
 *  rects. Self-contained (no closures over module scope) because the audit
 *  ships it into the page as source, as it does isVisuallyHidden. */
export function vcenterGeometry() {
  const gap = (icon, t) => Math.min(Math.abs(t.left - icon.right), Math.abs(icon.left - t.right));
  return {
    /** How far inner's centre sits below outer's: positive is low, negative high. */
    centreOffset: (inner, outer) => (inner.top + inner.bottom) / 2 - (outer.top + outer.bottom) / 2,
    /** A cell's box without its padding and borders: where its content belongs. */
    contentBox: (rect, { padTop, padBottom, borderTop, borderBottom }) => ({
      top: rect.top + padTop + borderTop, bottom: rect.bottom - padBottom - borderBottom,
    }),
    /** The text line beside an icon: on its line and within maxGap px of either side, nearest first. */
    nearestBeside: (icon, rects, maxGap = 24) => rects
      .filter((t) => t.height > 0 && Math.min(t.bottom, icon.bottom) - Math.max(t.top, icon.top) > 0 && gap(icon, t) < maxGap)
      .sort((a, b) => gap(icon, a) - gap(icon, b))[0] ?? null,
  };
}


/**
 * One hint trigger, opened, measured and closed, where any step may throw because a slow page
 * re-rendered and detached the trigger mid-check. Such a trigger is skipped (onSkip gets the
 * step and the error's first line) and the run goes on: one vanished element must never abort
 * a 30-minute audit. Returns measure()'s result, or null when skipped. A close() failure after
 * a good measurement keeps the measurement.
 */
export async function probeHint({ open, measure, close, onSkip }) {
  let geometry;
  for (const [step, run] of [['open', open], ['measure', async () => { geometry = await measure(); }]]) {
    try {
      await run();
    } catch (error) {
      onSkip(step, String(error).split('\n')[0]);
      return null;
    }
  }
  try {
    await close();
  } catch (error) {
    onSkip('close', String(error).split('\n')[0]);
  }
  return geometry;
}

/**
 * probeHint, run a second time when the first measurement needs it (a zero-size popover). A
 * slow tab can re-render as the trigger is tapped, swapping in an identical trigger whose
 * popover is closed; a genuinely broken popover fails both tries, a re-render only the first.
 */
export async function probeHintTwice(steps, needsRetry) {
  const first = await probeHint(steps);
  if (first === null || !needsRetry(first)) return first;
  return probeHint(steps);
}

/** Sub-pixel slack for the hint check's viewport test: a rect at -0.4px is a rounding artefact, not off-screen. */
const HINT_EDGE_SLACK_PX = 0.5;

/**
 * The hint check's verdict (spec v194 A2) on one opened sb-hint popover: its
 * viewport rect, the viewport size, and whether the topmost element at its
 * centre and at its top-left + 8px is inside it (layout-audit.mjs
 * measureHint). The first failing rule is the reason: zero-size (never
 * opened), off-screen (any edge past the viewport), covered-center (an
 * ancestor clips it or something paints over it), covered-corner. Runs in
 * Node on the measured numbers, so unlike vcenterGeometry it is never
 * shipped into the page.
 */
export function hintVerdict(rect, viewport, hits) {
  if (!(rect.width > 0 && rect.height > 0)) return { ok: false, reason: 'zero-size' };
  const inside = rect.left >= -HINT_EDGE_SLACK_PX && rect.top >= -HINT_EDGE_SLACK_PX
    && rect.left + rect.width <= viewport.width + HINT_EDGE_SLACK_PX
    && rect.top + rect.height <= viewport.height + HINT_EDGE_SLACK_PX;
  if (!inside) return { ok: false, reason: 'off-screen' };
  if (!hits.center) return { ok: false, reason: 'covered-center' };
  if (!hits.corner) return { ok: false, reason: 'covered-corner' };
  return { ok: true, reason: null };
}

/** Narrowest width the labelled rail shows at: below it (the shell's 639px phone breakpoint) the bottom
 *  tab bar navigates, and its tabs carry visible labels. */
export const RAIL_MIN_WIDTH = 640;

/**
 * The rail-label check's verdict (spec v202 §3) on one labelled-rail entry: its accessible name, its
 * .rail-label text and whether that label shows (layout-audit.mjs auditRailLabels). No name fails
 * first, then no label, then a hidden one, then a name without the label (WCAG 2.5.3 label-in-name).
 */
export function railLabelVerdict(entry) {
  const name = String(entry.name ?? '').trim();
  const label = String(entry.label ?? '').trim();
  if (!name) return { ok: false, reason: 'no-name' };
  if (!label) return { ok: false, reason: 'no-label' };
  if (!entry.labelVisible) return { ok: false, reason: 'label-hidden' };
  if (!name.toLowerCase().includes(label.toLowerCase())) return { ok: false, reason: 'label-not-in-name' };
  return { ok: true, reason: null };
}

/** The width the Live dock docks from (ui/breakpoints.ts md, DockState.docked). Below it the live
 *  strip opens the dock as a sheet (spec v202 §3). */
export const DOCK_MIN_WIDTH = 1024;
/** Sub-pixel slack: rects meeting at a shared edge, or a sheet at -0.4px, are rounding, not a defect. */
const DOCK_EDGE_SLACK_PX = 0.5;

const overlapPx = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left);
const outsideViewport = (r, v) => r.left < -DOCK_EDGE_SLACK_PX || r.top < -DOCK_EDGE_SLACK_PX
  || r.right > v.width + DOCK_EDGE_SLACK_PX || r.bottom > v.height + DOCK_EDGE_SLACK_PX;
const isDocked = (f) => f.width >= DOCK_MIN_WIDTH;

/** One rule per reason, in the order they are judged; the first that fails is the finding. */
const DOCK_RULES = Object.freeze([
  ['no-column', (f) => isDocked(f) && !f.column],
  ['overlaps-workspace', (f) => isDocked(f) && Boolean(f.workspace) && overlapPx(f.column, f.workspace) > DOCK_EDGE_SLACK_PX],
  ['strip-when-docked', (f) => isDocked(f) && f.strip],
  ['docked-below-1024', (f) => !isDocked(f) && Boolean(f.column)],
  ['no-strip', (f) => !isDocked(f) && !f.strip],
  ['sheet-not-opened', (f) => !isDocked(f) && !f.sheet],
  ['sheet-off-screen', (f) => !isDocked(f) && outsideViewport(f.sheet, f.viewport)],
]);

/** The element each dock finding points at (layout-audit.mjs prints it as the selector). */
export const DOCK_SELECTORS = Object.freeze({
  'no-column': 'aside.live-column',
  'overlaps-workspace': 'aside.live-column',
  'strip-when-docked': 'sb-live-strip',
  'docked-below-1024': 'aside.live-column',
  'no-strip': 'sb-live-strip',
  'sheet-not-opened': 'sb-live-sheet [role=dialog]',
  'sheet-off-screen': 'sb-live-sheet [role=dialog]',
});

/**
 * The dock check's verdict (spec v202 §8 "Layout", v203) on one page's measured facts:
 * `{ width, column, workspace, strip, sheet, viewport }`. `column` is aside.live-column's rect,
 * `workspace` main.workspace's content box, `strip` whether the live strip shows, `sheet` the opened
 * sheet dialog's rect (null when none opened); rects are {left, right, top, bottom} or null. Runs in
 * Node on the measured numbers, never shipped into the page.
 */
export function dockVerdict(facts) {
  const broken = DOCK_RULES.find(([, fails]) => fails(facts));
  return broken ? { ok: false, reason: broken[0] } : { ok: true, reason: null };
}

const findingKey = (f) =>`${f.route} @${f.width} ${f.check} ${f.selector}`;

export function dedupe(findings) {
  const byKey = new Map();
  for (const f of findings) {
    const seen = byKey.get(findingKey(f));
    if (seen) seen.count += 1;
    else byKey.set(findingKey(f), { ...f, count: 1 });
  }
  return [...byKey.values()];
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const ENTRY_RULES = [
  [(e) => ROUTES.includes(e.route), (e) => `unknown route ${e.route}`],
  [(e) => e.width === '*' || Number.isInteger(e.width), () => "width must be '*' or a number"],
  [(e) => CHECKS.includes(e.check), (e) => `unknown check ${e.check}`],
  [(e) => typeof e.selector === 'string' && e.selector.length > 0, () => 'selector is empty'],
  [(e) => typeof e.reason === 'string' && e.reason.trim().length >= 10, () => 'every entry needs a reason (10+ characters)'],
  [(e, today) => DATE.test(e.date ?? '') && e.date <= today, () => 'date must be YYYY-MM-DD and not in the future'],
];

export function validateAllow(entries, today) {
  entries.forEach((entry, index) => {
    const broken = ENTRY_RULES.find(([ok]) => !ok(entry, today));
    if (broken) throw new Error(`allow-list entry ${index} (${entry.selector || '?'}): ${broken[1](entry)}`);
  });
}

const matches = (entry, f) => entry.route === f.route && entry.check === f.check
  && entry.selector === f.selector && (entry.width === '*' || entry.width === f.width);

/** The verdict: findings no entry names, findings an entry names (with its
 *  reason), and entries nothing matched any more (stale). */
export function classify(findings, allow, today) {
  validateAllow(allow, today);
  const used = new Set();
  const unallowed = [];
  const allowed = [];
  for (const f of findings) {
    const index = allow.findIndex((entry) => matches(entry, f));
    if (index < 0) {
      unallowed.push(f);
      continue;
    }
    used.add(index);
    allowed.push({ ...f, reason: allow[index].reason });
  }
  return { unallowed, allowed, stale: allow.filter((_, index) => !used.has(index)) };
}

/** Whether a run at `widths` can judge `entry` stale. */
export const inScope = (entry, widths) => entry.width === '*' || widths.includes(entry.width);

export function formatFinding(f) {
  const text = f.text ? ` "${f.text}"` : '';
  const repeat = f.count > 1 ? ` (x${f.count})` : '';
  return `${f.route} @${f.width} ${f.check} ${f.selector}${text} -- ${f.detail}${repeat}`;
}

export function countByCheck(findings) {
  const counts = Object.fromEntries(CHECKS.map((check) => [check, 0]));
  for (const f of findings) counts[f.check] += 1;
  return counts;
}

/** Same file names as browse.mjs `shots`. */
export function slug(path) {
  return path.replace(/^\//, '').replace(/[^a-zA-Z0-9]+/g, '_').replace(/_$/, '') || 'root';
}
