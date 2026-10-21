/**
 * The pure half of the v179 layout audit (layout-audit.mjs): the routes it
 * visits, the checks it runs, argument parsing, placeholder resolution,
 * de-duplication and the allow-list verdict. No browser and no I/O, so
 * `node --test frontend/scripts/layout-audit-lib.test.mjs` covers all of it.
 * Spec: docs/superpowers/specs/2026-10-19-v179-mobile-layout-consistency-design.md §3.5, §6a.6.
 */

/** Every route and tab (27, spec §2). `:id` is a trade id, `:plan` an open
 *  (else pending) trade's id, `:symbol` a watchlist symbol with trades,
 *  `:date` the day a closed trade closed -- resolved from the API at run time.
 *  A route or tab added to the app is added here in the same commit. */
export const ROUTES = Object.freeze([
  '/dashboard',
  '/trades', '/trades/:id', '/trades/:id?tab=why', '/trades/:id?tab=chart', '/trades/:id?tab=journal',
  '/plans/:plan',
  '/analytics', '/analytics?tab=attribution', '/analytics?tab=execution', '/analytics?tab=edge',
  '/analytics?tab=pipeline', '/analytics?tab=tuning', '/analytics?tab=partials',
  '/calendar', '/calendar/:date',
  '/watchlist', '/watchlist/:symbol',
  '/risk',
  '/system', '/system?tab=logs', '/system?tab=scan',
  '/versions', '/research',
  '/reports', '/reports?tab=gates',
  '/ui',
]);

export const CHECKS = Object.freeze(['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline']);

/** Phone, tablet and desktop (docs/claude/ui-design.md § Device classes). */
export const FULL_WIDTHS = Object.freeze([390, 768, 1440]);
/** The tap check runs at or below this width: the 44px rule covers phone
 *  and tablet, `(pointer: coarse), (max-width: 1023px)` (v179 V179-2). */
export const TOUCH_MAX_WIDTH = 1023;
export const MIN_TAP_PX = 44;
export const MIN_TEXT_PX = 11;
export const MAX_BASELINE_OFFSET_PX = 2;

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

const findingKey = (f) => `${f.route} @${f.width} ${f.check} ${f.selector}`;

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
