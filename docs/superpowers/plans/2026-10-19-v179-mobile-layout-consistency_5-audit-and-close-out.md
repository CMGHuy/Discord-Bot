# v179 — Mobile layout consistency, Part 5: the layout audit, three-width verification and close-out (V179-19..V179-21)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read this part whole**: `grep -n "^### Task V179-20:" -A 260 docs/superpowers/plans/2026-10-19-v179-mobile-layout-consistency_5-audit-and-close-out.md`.

**Spec:** [2026-10-19-v179-mobile-layout-consistency-design.md](../specs/2026-10-19-v179-mobile-layout-consistency-design.md) — this part: §3.5, §6a.6 (the audit, its allow-list and its owner), §7 (every success criterion), §4 (blast radius), the `**Panel:**` line.
**Index:** [2026-10-19-v179-mobile-layout-consistency_0-index.md](2026-10-19-v179-mobile-layout-consistency_0-index.md) — Goal, Architecture, **Global Constraints**, **Contracts**, **Parallelisation** and the task ledger bind every task below.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-19-v179-mobile-layout-consistency` (branch `2026-10-19-v179-mobile-layout-consistency`, created in V179-1). V179-19 and V179-20 edit files **inside `$WT`** (the `Create:`/`Modify:` paths are relative to the worktree root) and commit there; V179-21 merges into `$R` and finishes on `main`.

**What this part relies on from Parts 1–4 (index Contracts).** `--hit-min` and `.sb-hit` (a transparent centred `::after` of `max(100%, var(--hit-min))`, V179-2) — the audit's tap check must measure that pseudo-element, because `getBoundingClientRect()` of the control itself stays small by design; a checkbox's target is its whole `<label class="field">` (V179-2); the compact DOM `ul.compact-list > li.compact-row > button.compact-hit` (V179-9); `sb-positions-table` rows `emit` on every device and the Dashboard opens `sb-trade-drawer` (`span.paper-marker[drawer-header]`, `a.full-trade`) under the pushed query parameter `trade` (V179-14..V179-16); `sb-recent-activity button.event-hit` (V179-14).

**The audit is a pre-merge check, not CI** (spec §6a.6): `node --test` covers its pure library here; the browser half runs against a local replica in V179-20, and `docs/claude/ui-design.md` makes it a step of every UI change from now on.

---

# Phase 5 — The guard, the verification and the ship

### Task V179-19: Layout audit script, allow-list, `ui-design.md` checklist and `AGENTS.md` mirror

**Model:** sonnet — a new Node script with a pure, `node --test`-tested library and a docs edit with its mirror; the browser half is ported from the brief's prototype, not designed from scratch.

**Files:**
- Create: `frontend/scripts/layout-audit-lib.mjs`
- Create: `frontend/scripts/layout-audit-lib.test.mjs`
- Create: `frontend/scripts/layout-audit.allow.json`
- Create: `frontend/scripts/layout-audit.mjs`
- Modify: `docs/claude/ui-design.md` (§ "Checklist for every screen or control")
- Modify: `AGENTS.md` (the `ui-design.md` bullet, ~l.214-216)

**Interfaces:**
- Consumes: nothing from earlier tasks at the code level (disjoint files, index Parallelisation). At run time (V179-20) the audit measures what Parts 1–4 built: `.sb-hit`'s `::after` and `--hit-min` (V179-2), the checkbox `<label class="field">` target (V179-2), the touch condition `(pointer: coarse), (max-width: 1023px)` (V179-2 — the audit treats every width ≤ 1023 as touch). Model for the session and page-ready code: `frontend/scripts/browse.mjs` (`signedIn`, `envCredentials`/`signInFromEnv`, `slug`, the `main.innerText` ready wait, the tallest-scroller screenshot). Its functions are module-private and the file runs its CLI on import, so the few lines needed are repeated here rather than imported.
- Produces (index Contracts, final): in `frontend/scripts/layout-audit-lib.mjs` — `ROUTES: readonly string[]` (27 templates; `:id` a trade id, `:plan` an open or pending trade's id, `:symbol` a watchlist symbol with trades, `:date` the day a closed trade closed, all resolved from the API at run time), `CHECKS = ['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline']`, `classify(findings, allow, today) → { unallowed, allowed, stale }`; plus helpers used by the CLI and its tests: `FULL_WIDTHS`, `TOUCH_MAX_WIDTH`, `MIN_TAP_PX`, `MIN_TEXT_PX`, `MAX_BASELINE_OFFSET_PX`, `parseArgs`, `resolveRoute`, `pickIds`, `dedupe`, `inScope`, `validateAllow`, `formatFinding`, `countByCheck`, `slug`. Finding shape `{ route (template), width, check, selector, text, detail, count }`; allow-list file `{ "$comment": string, "entries": [{ route, width ('*' or number), check, selector, reason, date: 'YYYY-MM-DD' }] }`. CLI: `node frontend/scripts/layout-audit.mjs [--base URL] [--widths 390,768,1440] [--out DIR] [--allow FILE] [--settle MS] [--prune]`; exit 0 clean, 1 on any unallowed finding, 2 when it cannot run; prints stale allow-list entries; writes `<out>/audit.json` and `<out>/<slug>@<width>.png`. V179-20 consumes the CLI.

**Why (spec §3.5, §6a.6).** The defects in spec §2 were found by a one-off Playwright DOM audit (the brief's §8 prototype). This task makes it the repo's repeatable pre-merge check. Differences from the prototype, each from the spec or the brief's notes on it: no hard-coded base or `E:/` require path (the script lives in `frontend/scripts/`, so `import 'playwright'` resolves from `frontend/node_modules`); no `networkidle` (the SPA holds an event stream); the baseline threshold is **2px** (spec), measured from real font metrics (`measureText().fontBoundingBoxAscent`) instead of `bottom − 0.22em`; the tap check runs only at widths ≤ 1023 and measures the `.sb-hit` pseudo-element and the checkbox's label; `sr-only` text is never "clipped"; text cut by an `overflow: hidden` ancestor counts as clipped (the Attribution heat grid "clips after 7m"); the shell's `<main>` pane counts toward page overflow, because the shell scrolls an inner pane, not the document (`browse.mjs`'s screenshot comment); an allow-list with a reason and a date per entry, stale entries printed and `--prune`d; a non-zero exit. The pure half (routes, args, ids, de-duplication, the verdict) is split out so `node --test` covers it without a browser; the page function runs inside Chromium and is exercised by V179-20's real run.

- [ ] **Step 1: Write the failing library tests**

Create `frontend/scripts/layout-audit-lib.test.mjs`:

```js
// node --test frontend/scripts/layout-audit-lib.test.mjs
// The pure half of the v179 layout audit. The browser half (layout-audit.mjs)
// is exercised by a real run against a local replica (plan task V179-20).
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  CHECKS, FULL_WIDTHS, ROUTES, classify, countByCheck, dedupe, formatFinding, inScope, parseArgs, pickIds,
  resolveRoute, slug, validateAllow,
} from './layout-audit-lib.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const TODAY = '2026-10-19';

const finding = (over = {}) => ({
  route: '/analytics?tab=attribution', width: 390, check: 'offscreen', selector: 'sb-heat-grid > div.cell',
  text: '8m', detail: 'right edge at 462px of 390px', ...over,
});
const entry = (over = {}) => ({
  route: '/analytics?tab=attribution', width: 390, check: 'offscreen', selector: 'sb-heat-grid > div.cell',
  reason: 'canvas internals of a third-party chart', date: '2026-10-19', ...over,
});

test('ROUTES visits every route and tab once (spec §2: 27)', () => {
  assert.equal(ROUTES.length, 27);
  assert.equal(new Set(ROUTES).size, ROUTES.length);
  assert.ok(ROUTES.every((route) => route.startsWith('/')));
  for (const tab of ['attribution', 'execution', 'edge', 'pipeline', 'tuning', 'partials']) {
    assert.ok(ROUTES.includes(`/analytics?tab=${tab}`), tab);
  }
  for (const route of ['/dashboard', '/trades', '/trades/:id', '/trades/:id?tab=journal', '/plans/:plan', '/calendar/:date',
    '/watchlist/:symbol', '/risk', '/system?tab=logs', '/system?tab=scan', '/versions', '/research', '/reports?tab=gates', '/ui']) {
    assert.ok(ROUTES.includes(route), route);
  }
});

test('CHECKS are the six the spec names, in order', () => {
  assert.deepEqual([...CHECKS], ['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline']);
});

test('parseArgs: defaults are the local replica at the three widths', () => {
  const opts = parseArgs([]);
  assert.equal(opts.base, 'http://localhost:1234');
  assert.deepEqual(opts.widths, [...FULL_WIDTHS]);
  assert.deepEqual([...FULL_WIDTHS], [390, 768, 1440]);
  assert.equal(opts.out, null);
  assert.equal(opts.allow, null);
  assert.equal(opts.prune, false);
  assert.equal(opts.settle, 1500);
});

test('parseArgs: every flag, a trailing slash on --base, and --prune', () => {
  const opts = parseArgs(['--base', 'https://bomeo-capital.com/', '--widths', '390,1440', '--out', 'o',
    '--allow', 'a.json', '--prune', '--settle', '800']);
  assert.equal(opts.base, 'https://bomeo-capital.com');
  assert.deepEqual(opts.widths, [390, 1440]);
  assert.equal(opts.out, 'o');
  assert.equal(opts.allow, 'a.json');
  assert.equal(opts.prune, true);
  assert.equal(opts.settle, 800);
});

test('parseArgs: unknown flags, missing values and bad widths throw', () => {
  assert.throws(() => parseArgs(['--path', '/x']), /unknown or incomplete flag --path/);
  assert.throws(() => parseArgs(['--base']), /incomplete flag --base/);
  assert.throws(() => parseArgs(['--widths', '390,abc']), /bad --widths/);
  assert.throws(() => parseArgs(['--widths', '200']), /bad --widths/);
});

test('resolveRoute fills every placeholder and encodes it', () => {
  const ids = { id: 'abc 1', plan: 'p1', symbol: 'BRK.B', date: '2026-10-01' };
  assert.equal(resolveRoute('/trades/:id?tab=why', ids), '/trades/abc%201?tab=why');
  assert.equal(resolveRoute('/plans/:plan', ids), '/plans/p1');
  assert.equal(resolveRoute('/watchlist/:symbol', ids), '/watchlist/BRK.B');
  assert.equal(resolveRoute('/calendar/:date', ids), '/calendar/2026-10-01');
  assert.equal(resolveRoute('/analytics?tab=edge', {}), '/analytics?tab=edge');
});

test('resolveRoute refuses a route it cannot fill', () => {
  assert.throws(() => resolveRoute('/plans/:plan', { plan: null }), /no plan to visit \/plans\/:plan/);
});

test('pickIds: a closed trade (id and day), an open plan, a symbol with trades', () => {
  const ids = pickIds({
    closed: { items: [{ id: 't1', closed_at: '2026-10-01T15:30:00Z' }] },
    open: { items: [{ id: 'p9' }] },
    pending: { items: [{ id: 'p0' }] },
    tickers: { tickers: [{ symbol: 'ZZZ', open_trades: 0, closed_trades: 0 }, { symbol: 'AAPL', open_trades: 1, closed_trades: 3 }] },
  });
  assert.deepEqual(ids, { id: 't1', date: '2026-10-01', plan: 'p9', symbol: 'AAPL' });
});

test('pickIds: a pending plan when nothing is open; null for a gap, never a guess', () => {
  const empty = { items: [] };
  assert.equal(pickIds({ closed: empty, open: empty, pending: { items: [{ id: 'p0' }] }, tickers: { tickers: [] } }).plan, 'p0');
  assert.deepEqual(pickIds({ closed: empty, open: empty, pending: empty, tickers: { tickers: [] } }),
    { id: null, date: null, plan: null, symbol: null });
});

test('dedupe keeps one finding per route, width, check and selector, with a count', () => {
  const out = dedupe([finding(), finding({ text: '9m' }), finding({ width: 768 })]);
  assert.equal(out.length, 2);
  assert.equal(out[0].count, 2);
  assert.equal(out[0].text, '8m');
  assert.equal(out[1].count, 1);
});

test('classify: a finding no entry matches is unallowed', () => {
  const { unallowed, allowed, stale } = classify([finding()], [], TODAY);
  assert.equal(unallowed.length, 1);
  assert.equal(allowed.length, 0);
  assert.equal(stale.length, 0);
});

test('classify: an exact entry allows the finding and carries its reason', () => {
  const { unallowed, allowed } = classify([finding()], [entry()], TODAY);
  assert.equal(unallowed.length, 0);
  assert.equal(allowed[0].reason, 'canvas internals of a third-party chart');
});

test("classify: width '*' matches every width, a number only its own", () => {
  assert.equal(classify([finding({ width: 1440 })], [entry({ width: '*' })], TODAY).unallowed.length, 0);
  assert.equal(classify([finding({ width: 1440 })], [entry({ width: 390 })], TODAY).unallowed.length, 1);
});

test('classify: route, check and selector must match exactly', () => {
  for (const over of [{ route: '/analytics' }, { check: 'clipped' }, { selector: 'sb-heat-grid > div' }]) {
    assert.equal(classify([finding(over)], [entry()], TODAY).unallowed.length, 1, JSON.stringify(over));
  }
});

test('classify: an entry no finding matches is stale', () => {
  const kept = entry();
  const gone = entry({ selector: 'sb-waterfall > text.label' });
  assert.deepEqual(classify([finding()], [kept, gone], TODAY).stale, [gone]);
});

test('classify rejects an entry without a reason, with a bad or future date, or naming what does not exist', () => {
  const cases = [
    [{ reason: '' }, /reason/],
    [{ reason: 'ok' }, /reason/],
    [{ date: '19-10-2026' }, /date/],
    [{ date: '2026-10-20' }, /date/],
    [{ route: '/nowhere' }, /unknown route/],
    [{ check: 'colour' }, /unknown check/],
    [{ width: '390' }, /width/],
    [{ selector: '' }, /selector/],
  ];
  for (const [over, message] of cases) {
    assert.throws(() => classify([], [entry(over)], TODAY), message, JSON.stringify(over));
  }
});

test("inScope: '*' always, a number only when that width ran", () => {
  assert.equal(inScope(entry({ width: '*' }), [390]), true);
  assert.equal(inScope(entry({ width: 768 }), [390, 1440]), false);
  assert.equal(inScope(entry({ width: 390 }), [390]), true);
});

test('formatFinding names route, width, check, selector, text, detail and repeats', () => {
  assert.equal(formatFinding({ ...finding(), count: 3 }),
    '/analytics?tab=attribution @390 offscreen sb-heat-grid > div.cell "8m" -- right edge at 462px of 390px (x3)');
  assert.equal(formatFinding({ ...finding({ text: '' }), count: 1 }),
    '/analytics?tab=attribution @390 offscreen sb-heat-grid > div.cell -- right edge at 462px of 390px');
});

test('countByCheck counts every check, zero included', () => {
  assert.deepEqual(countByCheck([finding(), finding({ check: 'tap' }), finding({ check: 'tap' })]),
    { overflow: 0, offscreen: 1, clipped: 0, tap: 2, text: 0, baseline: 0 });
});

test('slug matches browse.mjs file names', () => {
  assert.equal(slug('/analytics?tab=partials'), 'analytics_tab_partials');
  assert.equal(slug('/trades/:id'), 'trades_id');
  assert.equal(slug('/'), 'root');
});

test('the checked-in allow-list is valid today', () => {
  const doc = JSON.parse(readFileSync(join(HERE, 'layout-audit.allow.json'), 'utf8'));
  assert.equal(typeof doc.$comment, 'string');
  assert.ok(Array.isArray(doc.entries));
  assert.doesNotThrow(() => validateAllow(doc.entries, new Date().toISOString().slice(0, 10)));
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `$WT`): `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: FAIL — `Cannot find module '.../frontend/scripts/layout-audit-lib.mjs'` (`ERR_MODULE_NOT_FOUND`).

- [ ] **Step 3: Write the library and the empty allow-list**

Create `frontend/scripts/layout-audit-lib.mjs`:

```js
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
```

Create `frontend/scripts/layout-audit.allow.json`:

```json
{
  "$comment": "v179 layout audit allow-list (frontend/scripts/layout-audit.mjs). One entry per accepted finding: route (a ROUTES template from layout-audit-lib.mjs, e.g. /trades/:id), width ('*' or a number), check (overflow|offscreen|clipped|tap|text|baseline), selector (exactly as the audit prints it), reason (why this is not a defect), date (YYYY-MM-DD it was added). Only canvas or third-party chart internals and browser-native parts belong here (spec v179 §6a.6); an app control, label or row is fixed, not allowed. An entry nothing matches any more is printed as STALE; --prune removes it.",
  "entries": []
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `$WT`): `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: PASS — the summary reads `pass 21`, `fail 0`.

- [ ] **Step 5: Commit the library**

```bash
git -C "$WT" add frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs frontend/scripts/layout-audit.allow.json
git -C "$WT" commit -m "feat(ui-audit): layout audit library, allow-list and node tests (v179 §3.5, §6a.6)"
```

- [ ] **Step 6: Write the browser half**

Create `frontend/scripts/layout-audit.mjs`:

```js
#!/usr/bin/env node
/**
 * v179 layout audit -- the pre-merge check for every UI change
 * (docs/claude/ui-design.md § Checklist; spec
 * docs/superpowers/specs/2026-10-19-v179-mobile-layout-consistency-design.md §3.5, §6a.6).
 *
 * Visits every route and tab (layout-audit-lib.mjs ROUTES) at each width,
 * headless, on browse.mjs's persistent profile, and reports six checks:
 *   overflow   the page (document, body or the shell's <main> pane) is wider than the viewport
 *   offscreen  text past the right edge of the viewport, outside any scroll box
 *   clipped    text cut by its own overflow/ellipsis or by an overflow:hidden ancestor (never sr-only)
 *   tap        an interactive hit area under 44x44px (widths <= 1023 only; counts .sb-hit's ::after
 *              and a checkbox's label)
 *   text       text under 11px (SVG text at its rendered size)
 *   baseline   side-by-side text in one flex/grid row whose baselines differ by more than 2px
 * A finding the allow-list names (with a reason and a date) passes; anything
 * else makes the exit code 1. Entries nothing matches any more print as STALE;
 * --prune removes them (only on a run at 390, 768 and 1440).
 *
 *   node frontend/scripts/layout-audit.mjs [--base http://localhost:1234] [--widths 390,768,1440]
 *        [--out DIR] [--allow FILE] [--settle MS] [--prune]
 *
 * Sign in once with `node frontend/scripts/browse.mjs login --base <base>`
 * (headed; close that window first, the profile allows one browser). When
 * the profile has no session this script tries the .env ADMIN_USERNAME /
 * ADMIN_PASSWORD once -- loaded into this process only, never printed -- and
 * otherwise stops and says so.
 *
 * Writes <out>/audit.json and a full-page <slug>@<width>.png per visit
 * (default out: <tmp>/swingbot-layout-audit). Exit 0 clean, 1 unallowed
 * findings, 2 cannot run (no session, no data for a :placeholder, a bad
 * flag or an invalid allow-list).
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import {
  CHECKS, FULL_WIDTHS, MAX_BASELINE_OFFSET_PX, MIN_TAP_PX, MIN_TEXT_PX, ROUTES, TOUCH_MAX_WIDTH,
  classify, countByCheck, dedupe, formatFinding, inScope, parseArgs, pickIds, resolveRoute, slug, validateAllow,
} from './layout-audit-lib.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const ENV_FILE = join(HERE, '..', '..', '.env');
const DEFAULT_ALLOW = join(HERE, 'layout-audit.allow.json');

class CannotRun extends Error {}

/** Runs inside the page (page.evaluate): self-contained, no imports, no closures over module scope. */
function auditPage({ touch, minTap, minText, maxBaseline }) {
  const vw = document.documentElement.clientWidth;
  const findings = [];
  const INTERACTIVE = 'a[href], button, [role="button"], [role="tab"], input:not([type="hidden"]), select, textarea, summary, [tabindex="0"]';
  const canvas = document.createElement('canvas').getContext('2d');

  function name(el) {
    const tag = el.tagName.toLowerCase();
    const classes = [...el.classList].filter((c) => !/^(ng-|cdk-|is-|active$|selected$)/.test(c)).slice(0, 2);
    const self = tag + classes.map((c) => `.${c}`).join('');
    if (tag.includes('-')) return self;
    for (let p = el.parentElement; p; p = p.parentElement) {
      if (p.tagName.includes('-')) return `${p.tagName.toLowerCase()} > ${self}`;
    }
    return self;
  }
  const label = (el) => (el.innerText || el.textContent || el.getAttribute('aria-label') || '')
    .trim().replace(/\s+/g, ' ').slice(0, 50);
  const add = (check, el, detail) => findings.push({ check, selector: name(el), text: label(el), detail });
  const srOnly = (el) => Boolean(el.closest('.sr-only, .visually-hidden'));
  const ownText = (el) => [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim());

  function visible(el) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || r.right <= 0) return false; // r.right <= 0: the closed off-canvas menu
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && !el.closest('[inert], [aria-hidden="true"]');
  }

  /** The nearest ancestor that scrolls or clips sideways, below <main>. */
  function container(el) {
    for (let p = el.parentElement; p && p !== document.body && p.tagName !== 'MAIN'; p = p.parentElement) {
      const overflowX = getComputedStyle(p).overflowX;
      if (overflowX === 'auto' || overflowX === 'scroll') return { kind: 'scroll', box: p };
      if (overflowX === 'hidden' || overflowX === 'clip') return { kind: 'clip', box: p };
    }
    return null;
  }

  function textPx(el) {
    const px = parseFloat(getComputedStyle(el).fontSize);
    const ctm = el instanceof SVGGraphicsElement ? el.getScreenCTM() : null;
    return ctm ? px * Math.hypot(ctm.a, ctm.b) : px;
  }

  function clipDetail(el, r, box) {
    const cs = getComputedStyle(el);
    const clipsSelf = /hidden|clip/.test(cs.overflowX) || cs.textOverflow === 'ellipsis';
    if (clipsSelf && el.scrollWidth > el.clientWidth + 1) return `needs ${el.scrollWidth}px, has ${el.clientWidth}px`;
    const edge = box?.kind === 'clip' ? box.box.getBoundingClientRect().right : Infinity;
    return r.right > edge + 1 ? `cut by ${name(box.box)} at ${Math.round(edge)}px` : null;
  }

  function checkText(el) {
    const r = el.getBoundingClientRect();
    const box = container(el);
    if (!box && r.right > vw + 1) add('offscreen', el, `right edge at ${Math.round(r.right)}px of ${vw}px`);
    const clipped = clipDetail(el, r, box);
    if (clipped) add('clipped', el, clipped);
    const px = textPx(el);
    if (px < minText - 0.05) add('text', el, `${px.toFixed(1)}px`);
  }

  /** The tappable box: a checkbox's label, and .sb-hit's centred ::after. */
  function hitBox(el) {
    const target = el.matches('input[type="checkbox"], input[type="radio"]') ? (el.closest('label') ?? el) : el;
    const r = target.getBoundingClientRect();
    const after = getComputedStyle(target, '::after');
    const drawn = after.content !== 'none' && after.position === 'absolute';
    const hitMin = target.classList.contains('sb-hit')
      ? parseFloat(getComputedStyle(target).getPropertyValue('--hit-min')) || 0 : 0;
    const w = Math.max(r.width, drawn ? parseFloat(after.width) || 0 : 0, hitMin);
    const h = Math.max(r.height, drawn ? parseFloat(after.height) || 0 : 0, hitMin);
    return { w, h };
  }

  function checkTap(el) {
    const { w, h } = hitBox(el);
    if (w < minTap - 0.5 || h < minTap - 0.5) add('tap', el, `${Math.round(w)}x${Math.round(h)}px`);
  }

  /** First visible text of a row child, with its baseline from the font's own metrics. */
  function baselineOf(child) {
    const accept = (n) => (n.textContent.trim() && !srOnly(n.parentElement) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP);
    const node = document.createTreeWalker(child, NodeFilter.SHOW_TEXT, { acceptNode: accept }).nextNode();
    if (!node) return null;
    const range = document.createRange();
    range.selectNodeContents(node);
    const rect = range.getClientRects()[0];
    if (!rect || rect.height === 0) return null;
    const cs = getComputedStyle(node.parentElement);
    canvas.font = cs.font || `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    const ascent = canvas.measureText(node.textContent.trim()).fontBoundingBoxAscent;
    return { top: rect.top, bottom: rect.bottom, base: rect.top + ascent, text: node.textContent.trim().slice(0, 25), px: parseFloat(cs.fontSize) };
  }

  const isRow = (cs) => (/flex/.test(cs.display) ? cs.flexDirection.startsWith('row') : /grid/.test(cs.display));

  function checkBaselines(el) {
    const marks = [...el.children]
      .filter((k) => visible(k) && getComputedStyle(k).position !== 'absolute')
      .map(baselineOf).filter(Boolean);
    for (let i = 0; i < marks.length; i += 1) {
      for (let j = i + 1; j < marks.length; j += 1) {
        const [a, b] = [marks[i], marks[j]];
        const overlap = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (overlap < 0.5 * Math.min(a.bottom - a.top, b.bottom - b.top)) continue; // not the same visual line
        const offset = Math.abs(a.base - b.base);
        if (offset > maxBaseline) add('baseline', el, `"${a.text}" (${a.px}px) vs "${b.text}" (${b.px}px): ${offset.toFixed(1)}px`);
      }
    }
  }

  const doc = document.documentElement;
  const main = document.querySelector('main');
  const overflowPx = Math.max(doc.scrollWidth - doc.clientWidth, document.body.scrollWidth - document.body.clientWidth,
    main ? main.scrollWidth - main.clientWidth : 0);
  if (overflowPx > 0) findings.push({ check: 'overflow', selector: 'document', text: '', detail: `${overflowPx}px wider than the viewport` });

  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el)) continue;
    if (ownText(el) && !srOnly(el)) checkText(el);
    if (touch && el.matches(INTERACTIVE)) checkTap(el);
    if (!(el instanceof SVGElement) && isRow(getComputedStyle(el))) checkBaselines(el);
  }
  return findings;
}

/** Same page-ready rule as browse.mjs: never 'networkidle' (the SPA holds an event stream open). */
function ready() {
  const main = document.querySelector('main') ?? document.body;
  return main.innerText.trim().length > 200 && !/Loading/.test(document.body.innerText);
}

async function signedIn(page, base) {
  return page.evaluate(async (url) => {
    const res = await fetch(url, { credentials: 'include' });
    return res.ok && (await res.json()).authenticated === true;
  }, `${base}/api/v1/session`).catch(() => false);
}

/** One POST with the .env credentials (the login limiter counts failures); the values stay in this process. */
async function signInFromEnv(page, base) {
  try {
    process.loadEnvFile(ENV_FILE);
  } catch {
    return false;
  }
  const { ADMIN_USERNAME: username, ADMIN_PASSWORD: password } = process.env;
  if (!username || !password) return false;
  return page.evaluate(async ({ url, body }) => (await fetch(url, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })).ok, { url: `${base}/api/v1/session`, body: { username, password } }).catch(() => false);
}

async function requireSession(page, base) {
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  if (await signedIn(page, base)) return;
  if (await signInFromEnv(page, base) && await signedIn(page, base)) return;
  throw new CannotRun(`not signed in at ${base}: run \`node frontend/scripts/browse.mjs login --base ${base}\` once, then re-run`);
}

async function getJson(page, url) {
  return page.evaluate(async (target) => {
    const res = await fetch(target, { credentials: 'include' });
    if (!res.ok) throw new Error(`${res.status} ${target}`);
    return res.json();
  }, url);
}

async function resolveIds(page, base) {
  const api = (path) => getJson(page, `${base}/api/v1/${path}`);
  return pickIds({
    closed: await api('trades?status=CLOSED&per_page=1'),
    open: await api('trades?status=OPEN&per_page=1'),
    pending: await api('trades?status=PENDING&per_page=1'),
    tickers: await api('watchlist/tickers'),
  });
}

async function withContext(width, fn) {
  const context = await chromium.launchPersistentContext(PROFILE, {
    headless: true, viewport: { width, height: 900 }, deviceScaleFactor: 1,
    hasTouch: width <= TOUCH_MAX_WIDTH, isMobile: width < 640,
  });
  try {
    return await fn(context.pages()[0] ?? (await context.newPage()));
  } finally {
    await context.close();
  }
}

/** browse.mjs's full-page shot: the shell scrolls an inner pane, so grow the viewport to the tallest scroller. */
async function screenshot(page, file, width) {
  const tallest = await page.evaluate(() => Math.max(
    document.documentElement.scrollHeight,
    ...[...document.querySelectorAll('*')].filter((el) => el.scrollHeight > el.clientHeight + 4
      && /(auto|scroll)/.test(getComputedStyle(el).overflowY)).map((el) => el.scrollHeight + el.getBoundingClientRect().top),
  ));
  await page.setViewportSize({ width, height: Math.min(Math.ceil(tallest) + 40, 8000) });
  await page.waitForTimeout(500);
  await page.screenshot({ path: file, fullPage: true });
  await page.setViewportSize({ width, height: 900 });
}

async function auditWidth(width, opts) {
  return withContext(width, async (page) => {
    await requireSession(page, opts.base);
    const limits = { touch: width <= TOUCH_MAX_WIDTH, minTap: MIN_TAP_PX, minText: MIN_TEXT_PX, maxBaseline: MAX_BASELINE_OFFSET_PX };
    const findings = [];
    for (const route of ROUTES) {
      await page.goto(`${opts.base}${resolveRoute(route, opts.ids)}`, { waitUntil: 'load' });
      await page.waitForFunction(ready, null, { timeout: 30_000 })
        .catch(() => console.error(`still loading after 30s: ${route} @${width}`));
      await page.waitForTimeout(opts.settle);
      const raw = await page.evaluate(auditPage, limits);
      findings.push(...raw.map((f) => ({ route, width, ...f })));
      await screenshot(page, join(opts.out, `${slug(route)}@${width}.png`), width);
      console.error(`${route} @${width}: ${raw.length} raw finding(s)`);
    }
    return findings;
  });
}

function report(verdict, opts) {
  const counts = countByCheck(verdict.unallowed);
  console.log(`layout audit ${opts.base} @ ${opts.widths.join(',')}: ${verdict.unallowed.length} unallowed, ${verdict.allowed.length} allowed`);
  console.log(CHECKS.map((check) => `${check}=${counts[check]}`).join(' '));
  for (const f of verdict.unallowed) console.log(`  FAIL ${formatFinding(f)}`);
  for (const e of verdict.stale) console.log(`  STALE ${e.route} @${e.width} ${e.check} ${e.selector} (added ${e.date})`);
  console.log(`screenshots and audit.json: ${opts.out}`);
}

function prune(doc, stale, file) {
  const entries = doc.entries.filter((entry) => !stale.includes(entry));
  writeFileSync(file, `${JSON.stringify({ ...doc, entries }, null, 2)}\n`);
  console.log(`pruned ${doc.entries.length - entries.length} stale allow-list entr${stale.length === 1 ? 'y' : 'ies'} from ${file}`);
}

function setUp(argv) {
  let opts;
  try {
    opts = parseArgs(argv);
  } catch (error) {
    throw new CannotRun(error.message);
  }
  opts.allow ??= DEFAULT_ALLOW;
  opts.out ??= join(tmpdir(), 'swingbot-layout-audit');
  if (opts.prune && !FULL_WIDTHS.every((w) => opts.widths.includes(w))) {
    throw new CannotRun(`--prune needs a run at ${FULL_WIDTHS.join(',')}`);
  }
  return opts;
}

function loadAllow(file, today) {
  const doc = JSON.parse(readFileSync(file, 'utf8'));
  try {
    validateAllow(doc.entries, today);
  } catch (error) {
    throw new CannotRun(error.message);
  }
  return doc;
}

async function main() {
  const opts = setUp(process.argv.slice(2));
  const today = new Date().toISOString().slice(0, 10);
  const doc = loadAllow(opts.allow, today);
  mkdirSync(opts.out, { recursive: true });
  opts.ids = await withContext(1440, async (page) => {
    await requireSession(page, opts.base);
    return resolveIds(page, opts.base);
  });
  try {
    ROUTES.forEach((route) => resolveRoute(route, opts.ids));
  } catch (error) {
    throw new CannotRun(error.message);
  }
  const findings = [];
  for (const width of opts.widths) findings.push(...(await auditWidth(width, opts)));
  const verdict = classify(dedupe(findings), doc.entries.filter((entry) => inScope(entry, opts.widths)), today);
  writeFileSync(join(opts.out, 'audit.json'),
    `${JSON.stringify({ base: opts.base, widths: opts.widths, ids: opts.ids, date: today, ...verdict }, null, 1)}\n`);
  report(verdict, opts);
  if (opts.prune && verdict.stale.length) prune(doc, verdict.stale, opts.allow);
  return verdict.unallowed.length ? 1 : 0;
}

main().then((code) => {
  process.exitCode = code;
}, (error) => {
  console.error(error instanceof CannotRun ? `cannot run: ${error.message}` : error);
  process.exitCode = 2;
});
```

- [ ] **Step 7: Smoke-test the CLI without a browser**

Both runs stop in `setUp`, before any browser starts, which proves the script and its imports (including `playwright` from `frontend/node_modules`) load:

```bash
cd "$WT"
node frontend/scripts/layout-audit.mjs --bogus x; echo "exit=$?"
node frontend/scripts/layout-audit.mjs --widths 390 --prune; echo "exit=$?"
node --test frontend/scripts/layout-audit-lib.test.mjs
```

Expected: `cannot run: unknown or incomplete flag --bogus` then `exit=2`; `cannot run: --prune needs a run at 390,768,1440` then `exit=2`; the library tests still `fail 0`. The real run against a replica is V179-20.

- [ ] **Step 8: Commit the CLI**

```bash
git -C "$WT" add frontend/scripts/layout-audit.mjs
git -C "$WT" commit -m "feat(ui-audit): Playwright layout audit over every route at 390/768/1440 (v179 §3.5)"
```

- [ ] **Step 9: Record the check in `ui-design.md`**

In `docs/claude/ui-design.md`, replace the whole `## Checklist for every screen or control` section (its five bullets, up to the blank line before `## Tables and pagers`) with:

```markdown
## Checklist for every screen or control

- Touch targets at least 44px (2.75rem) on phone and tablet; hover is never
  the only affordance. A control whose box may grow takes
  `min-height: var(--control-h)`; one whose look must stay small takes
  `class="sb-hit"` (a transparent hit area of `--hit-min`, 44px under
  `(pointer: coarse), (max-width: 1023px)`).
- Text is never below 11px: size it with the text tokens (they carry the floor
  at every zoom step), never a literal `font-size` under 11px.
- Mixed text sizes on one line align on the baseline (`align-items: baseline`
  or `last baseline`), never `center`. Numbers use the numeric face (`.num`,
  `var(--font-num)`); labels stay in the UI font.
- Layout responds to its **container** where it can sit in a narrow panel
  (`container-type: inline-size` + `@container`), not only the viewport.
- No horizontal page scroll. A wide chart or grid scrolls inside its own box
  with an edge fade; a data table on a phone is **declared, not hand-built**:
  its columns carry a `compact` slot (line 1 or 2, plus an order) and
  `sb-data-table` renders compact rows and the row drawer (v179). Open-position
  tables keep the P&L amount and the stop or risk on the compact row; strategy
  rows keep the badge tier and evidence freshness.
- Controls that have a desktop row layout say how they wrap on narrow widths.
- State what each class defaults to (page size, density, columns) and whether a
  saved choice is per device class.
- **Before merging any UI change, run the layout audit** against a local
  replica (`/replicate-prod-db`, `cd frontend && npm run build`,
  `python admin_ui.py`, then sign in once with
  `node frontend/scripts/browse.mjs login --base http://localhost:1234`):
  `node frontend/scripts/layout-audit.mjs --base http://localhost:1234`
  must exit 0 at 390, 768 and 1440. It checks page overflow, off-screen and
  clipped text, sub-44px targets (phone/tablet), sub-11px text and baseline
  offsets over 2px on every route and tab. A finding is fixed, not allowed;
  only canvas/third-party chart internals and browser-native parts go in
  `frontend/scripts/layout-audit.allow.json`, each entry with a reason and the
  date it was added. Entries nothing matches any more print as `STALE`; a run
  with `--prune` removes them. A route or tab added to the app is added to
  `ROUTES` in `frontend/scripts/layout-audit-lib.mjs` in the same commit. It
  is not in CI (spec v179 §6a.6).
```

- [ ] **Step 10: Mirror it in `AGENTS.md`**

In `AGENTS.md`, replace the `ui-design.md` bullet (~l.214-216):

```markdown
- `ui-design.md`: any screen, table or pager: designed for mobile, tablet and
  desktop together and checked at all three widths; tables page
  5/10/20/50/100/All (10 desktop, 5 tablet/phone).
```

with:

```markdown
- `ui-design.md`: any screen, table or pager: designed for mobile, tablet and
  desktop together and checked at all three widths; tables page
  5/10/20/50/100/All (10 desktop, 5 tablet/phone); text >= 11px, mixed sizes
  on one baseline, 44px hit areas on phone/tablet (`.sb-hit`), phone tables
  declare `compact` rows. Before merging a UI change,
  `node frontend/scripts/layout-audit.mjs --base http://localhost:1234` must
  exit 0 (allow-list entries carry a reason and a date).
```

- [ ] **Step 11: Run the mirror test and commit the docs**

Run (from `$WT`): `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: PASS, `0 failed`.

```bash
git -C "$WT" add docs/claude/ui-design.md AGENTS.md
git -C "$WT" commit -m "docs(ui): the layout audit joins the UI checklist, with its AGENTS.md mirror (v179 §6a.6)"
```

### Task V179-20: Three-width verification: audit to zero, screenshots, Dashboard drawer round trip

**Model:** sonnet — runs the audit over the finished branch and judges each finding (fix in the owning file, or allow with a reason); the fixes follow patterns earlier tasks set, and the round trip is a fixed script.

**Files:**
- Create: `docs/superpowers/results/2026-10-19-v179-layout-audit.md`
- Modify: `frontend/scripts/layout-audit.allow.json` (only for a canvas/third-party/browser-native finding, each entry with a reason and a date)
- Modify: the file each remaining finding traces to, and that file's spec — named per finding in the results doc (the owning task's file list in the index ledger says which part owns it)

**Interfaces:**
- Consumes: the audit CLI and allow-list (V179-19); everything Parts 1–4 shipped. DOM the round trip drives (index Contracts, Part 4): `sb-positions-table tr.row` (tablet/desktop row click → `rowActivate`), `sb-positions-table button.compact-hit` (phone compact row, `phoneTap = 'emit'`), `sb-recent-activity button.event-hit`, `sb-trade-drawer` (mounted only while the Dashboard holds a row) with `.paper-marker` and `a.full-trade`, the pushed query parameter `trade`.
- Produces: the results doc V179-21 cites in the merge commit and hands to `/panel`: final audit summary (zero unallowed at 390, 768 and 1440), the allow-list with reasons, the fix commits, the round-trip output, the screenshot location and the per-route review.

**Why (spec §7.1–§7.3).** Success is measured, not stated: zero unallowed findings on every route and tab at three widths against production data (the replica), screenshots of every route at those widths reviewed, and the Dashboard drawer round trip (open, Back closes, "Open full trade" reaches `/trades/:id`) at 1440 and 390. This is the first run of the audit over the whole branch, so it will find things the part-level browser checks (V179-8, V179-13, V179-18) did not measure — that is its job.

**Rule for a finding (spec §6a.6, §4 anti-goals).** A finding in app markup — a page overflow, off-screen or clipped app text, an app control under 44px, app text under 11px, a misaligned app row — is **fixed**, never allowed. Only these may go in the allow-list, each with a reason naming which: canvas or `lightweight-charts` internals (the candle/equity charts draw their own axes), browser-native parts (a native `<select>`'s own arrow box, a scrollbar), or text the app does not render. If a finding seems to need an app exception anyway, stop and ask the partner with `AskUserQuestion` (recommended option first: fix it) — never allow it to reach zero.

- [ ] **Step 1: Confirm the branch is complete and build the local instance**

```bash
git -C "$WT" log --oneline main..HEAD | head -60     # expect the V179-1..V179-19 commits
git -C "$WT" status --short                          # expect empty
```

Run `/replicate-prod-db` (the audit runs on production data, spec §7.1), then from `$WT`:

```bash
cd frontend && npm run build && cd ..
python admin_ui.py            # serves the SPA at http://localhost:1234 -- start it with run_in_background and leave it running
node frontend/scripts/browse.mjs login --base http://localhost:1234   # headed, once; .env credentials loaded inside the script, never printed; close the window when it says "Signed in"
node --test frontend/scripts/layout-audit-lib.test.mjs                 # fail 0
```

- [ ] **Step 2: First audit run**

```bash
AUDIT="$(mktemp -d)/v179-audit"
node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440 --out "$AUDIT" > "$AUDIT.log"; echo "exit=$?"
head -3 "$AUDIT.log"; grep -c "^  FAIL" "$AUDIT.log"
```

The run visits 81 pages (27 × 3) and takes several minutes: run it with `run_in_background` (or a `timeout` of 600000). Expected: exit `0` or `1`, never `2` (`2` means no session, no replica data for a `:placeholder`, or a bad allow-list — fix that first). Record the first line (`N unallowed, M allowed`) and the per-check counts line for the results doc's "First run" row.

- [ ] **Step 3: Fix each unallowed finding at its source**

Group the `FAIL` lines by selector — one primitive usually explains many routes. For each group, find the owning file (`git -C "$WT" grep -n "<class or selector>" frontend/src/app`) and apply the fix the matching earlier task established:

| Check | Usual cause | Fix (pattern from) | Test in the owning file's spec (pattern from) |
|---|---|---|---|
| `overflow`, `offscreen` | a grid, chart or row wider than its container | `minmax(0, 1fr)` / `min-width: 0` / `overflow-x: auto` with the edge fade (V179-7, V179-8) | source-text `rule(selector)` assertion (V179-7) |
| `clipped` | `text-overflow: ellipsis` on a label that should wrap, or an `overflow: hidden` box narrower than its text | `overflow-wrap: anywhere` + `min-width: 0`, or move into a scroll box (V179-7) | source-text assertion (V179-7) |
| `tap` | a control with no `min-height` and no `.sb-hit` | `min-height: var(--control-h)` where the box may grow, `class="… sb-hit"` where it must stay small (V179-2's rule) | the `hit-area.spec.ts` pattern (V179-2): the template carries `sb-hit` or the rule carries `min-height: var(--control-h)` |
| `text` | a literal `font-size` or a token without the floor | the floored token (`--text-micro`, `--text-chip`, V179-1) | the `text-styles.spec.ts` guard (V179-1) |
| `baseline` | `align-items: center` on a row of mixed sizes | `align-items: baseline` or `last baseline` (V179-3) | `rule(selector)` asserts `align-items: (last )?baseline` (V179-3) |

For each fix: write the failing test first in the owning spec, run it narrow (`(cd "$WT/frontend" && npx ng test --watch=false --include <spec path relative to frontend/>)`, expect FAIL), fix, re-run (expect PASS, `0 failed`), then commit that fix alone:

```bash
git -C "$WT" add <the fixed file> <its spec>
git -C "$WT" commit -m "fix(ui): <what> -- v179 layout audit"
```

A finding that meets the allow-list rule above gets one entry, added to `frontend/scripts/layout-audit.allow.json` `entries` with the selector copied exactly from the `FAIL` line and today's date, for example:

```json
{ "route": "/trades/:id?tab=chart", "width": "*", "check": "text", "selector": "sb-candle-chart > td", "reason": "lightweight-charts draws its own price-scale cells; the app does not size them", "date": "2026-10-20" }
```

(`width` is `"*"` only when the finding repeats at every width; otherwise the number.) Commit allow-list entries together, after the fixes:

```bash
node --test frontend/scripts/layout-audit-lib.test.mjs     # the allow-list still validates
git -C "$WT" add frontend/scripts/layout-audit.allow.json
git -C "$WT" commit -m "chore(ui-audit): allow <n> chart-internal findings, each with its reason (v179 §6a.6)"
```

- [ ] **Step 4: Re-run until zero, and prune**

After the fixes: `cd frontend && npm run build && cd ..` (`admin_ui.py` serves the new `dist/` on the next request; restart it if the page still shows the old build), then:

```bash
node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440 --out "$AUDIT" --prune > "$AUDIT.log"; echo "exit=$?"
head -2 "$AUDIT.log"; grep "STALE\|pruned" "$AUDIT.log"
```

Repeat Steps 3–4 until: `exit=0`, the first line reads `0 unallowed`, and no `STALE` line remains. If `--prune` rewrote the allow-list, commit it: `git -C "$WT" commit -am "chore(ui-audit): prune stale allow-list entries"` (only that file is modified at this point — check `git -C "$WT" status --short` first).

- [ ] **Step 5: Dashboard drawer round trip at 1440 and 390 (spec §7.3)**

Write this script to the scratch directory (it is a one-off check, not checked in) and run it from `$WT/frontend` so `playwright` resolves:

```bash
cat > "$AUDIT/roundtrip.mjs" <<'JS'
// v179 §7.3: open a trade from Open positions and from Recent activity; Back closes; "Open full trade" reaches /trades/:id.
import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { join } from 'node:path';

const require = createRequire(join(process.cwd(), 'package.json'));
const { chromium } = require('playwright');
const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const BASE = process.argv[2] ?? 'http://localhost:1234';
const SOURCES = {
  positions: { 1440: 'sb-positions-table tr.row', 390: 'sb-positions-table button.compact-hit' },
  activity: { 1440: 'sb-recent-activity button.event-hit', 390: 'sb-recent-activity button.event-hit' },
};
const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${what}`);
  if (!ok) failures.push(what);
};
const tradeParam = (page) => new URL(page.url()).searchParams.get('trade');
const path = (page) => new URL(page.url()).pathname;

async function openDashboard(page) {
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'load' });
  await page.waitForFunction(() => (document.querySelector('main')?.innerText.trim().length ?? 0) > 200, null, { timeout: 30_000 })
    .catch(() => {});
  await page.waitForTimeout(1500);
}

async function roundTrip(page, width, source, selector) {
  const what = `${source} @${width}`;
  await openDashboard(page);
  const row = page.locator(selector).first();
  if ((await row.count()) === 0) {
    console.log(`SKIP ${what}: no ${selector} on the replica`);
    return false;
  }
  await row.evaluate((el) => el.click());
  await page.waitForTimeout(800);
  const id = tradeParam(page);
  check(Boolean(id), `${what}: the click pushes ?trade=<id>`);
  check(path(page) === '/dashboard', `${what}: still on /dashboard`);
  check(await page.locator('sb-trade-drawer .paper-marker').isVisible(), `${what}: drawer open with its "Paper trade" marker`);
  await page.goBack();
  await page.waitForTimeout(800);
  check(!tradeParam(page) && path(page) === '/dashboard', `${what}: Back drops ?trade= and stays on /dashboard`);
  check((await page.locator('sb-trade-drawer').count()) === 0, `${what}: Back closes the drawer`);
  await row.evaluate((el) => el.click());
  await page.waitForTimeout(800);
  await page.locator('sb-trade-drawer a.full-trade').evaluate((el) => el.click());
  await page.waitForURL(/\/trades\/[^/?]+/, { timeout: 10_000 }).catch(() => {});
  check(path(page) === `/trades/${encodeURIComponent(id ?? '')}`, `${what}: "Open full trade" reaches /trades/${id}`);
  return true;
}

for (const width of [1440, 390]) {
  const context = await chromium.launchPersistentContext(PROFILE, {
    headless: true, viewport: { width, height: 900 }, hasTouch: width < 1024, isMobile: width < 640,
  });
  try {
    const page = context.pages()[0] ?? (await context.newPage());
    let ran = 0;
    for (const [source, selectors] of Object.entries(SOURCES)) ran += (await roundTrip(page, width, source, selectors[width])) ? 1 : 0;
    check(ran > 0, `@${width}: at least one source had a trade to open`);
  } finally {
    await context.close();
  }
}
console.log(failures.length ? `round trip: ${failures.length} failure(s)` : 'round trip: all passed');
process.exitCode = failures.length ? 1 : 0;
JS
(cd "$WT/frontend" && node "$AUDIT/roundtrip.mjs" http://localhost:1234) | tee "$AUDIT/roundtrip.log"
```

Expected: every line `PASS` (a `SKIP` for one source is acceptable only when the replica has no row of that kind; the `at least one source` line must still pass), last line `round trip: all passed`. A `FAIL` is a Part 4 defect: fix it in the file V179-14..V179-16 owns, test-first in that file's spec as Step 3 describes, commit `fix(dashboard): <what> -- v179 drawer round trip`, rebuild and re-run this step.

- [ ] **Step 6: Review the screenshots at three widths (spec §7.2)**

The final audit run wrote `"$AUDIT"/<slug>@<width>.png` for all 27 routes and tabs at 390, 768 and 1440. Open each set (use the Read tool on the PNGs, a route at a time, three widths together) and check:

| What | Routes | Pass when |
|---|---|---|
| No sideways page, nothing cut | all | the right edge holds at 390; Attribution's heat grid scrolls in its own box with a fade; Partials' tiles, bar list, histogram and share bar stay inside the page |
| Compact rows | Dashboard positions, Trades, Watchlist, ticker page, Research registry, Risk @390 | two-line rows, no table header, Sort above and pager below; money floor (P&L amount, stop or risk) and badge floor (tier on line 1, evidence on line 2) visible |
| One look per primitive | Analytics, Risk, Calendar, Partials | stat tiles stacked and left-aligned everywhere (Calendar's centred/inline variants gone); tiles in a row share a height; filter areas are one row of same-height controls |
| Tab rails | Analytics, Reports, System (and the System settings category rail) @390 | edge fade where tabs continue; the active tab is in view |
| Baselines and numbers | Trade detail title, Calendar totals, Versions "Running now", Dashboard performance header, Analytics population line | mixed sizes on one baseline; numeric values in one face |
| Captions travel | every page with a tile, a cost, tax, paper-trade or `N=` caption | no caption, ⓘ hint or `N=` sample missing compared with the 1440 shot of the same page |
| Desktop unchanged | all @1440 | tables, panels and charts look as before v179, apart from the shared fixes (baseline headers, numeric face, 11px floor) |

A failed row is a defect: fix it as in Step 3 (test-first in the owning spec, its own `fix(ui): … -- v179 screenshot review` commit), rebuild, and re-run Steps 4–6 for that route. A row that cannot be judged from a static shot (a fade, a scrolled-into-view tab) is checked in the headed browser: `node frontend/scripts/browse.mjs shots --base http://localhost:1234 --widths 390 --out "$AUDIT/manual" --path "<route>"`.

- [ ] **Step 7: Write the results document and commit it**

Create `docs/superpowers/results/2026-10-19-v179-layout-audit.md`, filling every `<…>` from Steps 2–6:

````markdown
# v179 layout audit — results

**Spec:** [2026-10-19-v179-mobile-layout-consistency-design.md](../specs/2026-10-19-v179-mobile-layout-consistency-design.md) §7
**Plan:** [2026-10-19-v179-mobile-layout-consistency_0-index.md](../plans/2026-10-19-v179-mobile-layout-consistency_0-index.md) — task V179-20
**Run:** <YYYY-MM-DD HH:MM>, local replica (`/replicate-prod-db` at <time>), branch `2026-10-19-v179-mobile-layout-consistency` at `<short sha>`
**Command:** `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440 --prune`
**Ids the placeholders resolved to:** trade `<id>`, plan `<id>`, symbol `<symbol>`, day `<date>`

## Verdict (§7.1)

| Run | Unallowed | overflow | offscreen | clipped | tap | text | baseline | Allowed |
|---|---|---|---|---|---|---|---|---|
| First (Step 2) | <n> | <n> | <n> | <n> | <n> | <n> | <n> | 0 |
| Final | **0** | 0 | 0 | 0 | 0 | 0 | 0 | <n> |

Exit code of the final run: `0`. Stale allow-list entries after `--prune`: none.

## Fixes made by the audit

| Commit | Check | Selector (routes) | Owning file |
|---|---|---|---|
| `<sha>` | <check> | `<selector>` (<routes>) | `<path>` |

## Allow-list (each entry's reason)

| Route | Width | Check | Selector | Reason | Date |
|---|---|---|---|---|---|
| <route> | <width> | <check> | `<selector>` | <reason> | <date> |

(Write "None — the allow-list is empty." when it is.)

## Dashboard drawer round trip (§7.3)

```text
<the full contents of roundtrip.log>
```

## Screenshots (§7.2)

81 full-page PNGs (27 routes and tabs × 390/768/1440), `<slug>@<width>.png`, in `<the $AUDIT path>` (outside the repo; regenerate with the command above). Reviewed against the V179-20 Step 6 table:

| Check | Result |
|---|---|
| No sideways page, nothing cut | <pass / fixed in sha> |
| Compact rows (money and badge floors) | <…> |
| One look per primitive | <…> |
| Tab rails | <…> |
| Baselines and numbers | <…> |
| Captions travel | <…> |
| Desktop unchanged | <…> |
````

Then:

```bash
git -C "$WT" add docs/superpowers/results/2026-10-19-v179-layout-audit.md
git -C "$WT" commit -m "docs(v179): layout audit results -- zero unallowed findings at 390/768/1440, drawer round trip passes"
```

Stop `admin_ui.py`. Keep `$AUDIT` until V179-21's `/panel` has run (the reviewers may look at the PNGs).

### Task V179-21: Full suite, `npm test`, lint, ui minor bump, merge, `/panel`, `/close-out`

**Model:** sonnet — fixed gates and rituals (the plan's one full run, the merge, the two-commit release, the panel, the move), with judgement only where a gate or a panel finding fails.

**Files:**
- Modify: `VERSION.json` (`ui` minor, by `/close-out`)
- Modify: `swingbot/admin/version_history.json` (regenerated by `scripts/dev/build_version_matrix.py`; the index ledger's `version_history.json`)
- Modify: `docs/superpowers/plans/2026-10-19-v179-mobile-layout-consistency_0-index.md` (`## Panel review` appended; then the index, every part and the spec move to `implemented/`)

**Interfaces:**
- Consumes: every V179-1..V179-20 commit on branch `2026-10-19-v179-mobile-layout-consistency`; `docs/superpowers/results/2026-10-19-v179-layout-audit.md` (V179-20); the spec's `**Panel:** staff-engineer, financial-advisor`.
- Produces: the branch merged on `main`, `release(ui)` and its regenerated history, the closed plan in `docs/superpowers/plans/implemented/`, the worktree removed.

**Why (spec §7.4, index Global Constraints).** `testrun.py full`, `npm test` and `npm run lint` run once for the whole plan, here (CLAUDE.md "Full suite once per plan, as its final task"; spec §7.4 names the frontend gates the CI `frontend-test` job runs). The merge, the panel and the close-out follow `docs/claude/document-lifecycle.md` and the `close-out` skill; the bump level comes from `VERSION.json` on disk and the header's `Bump: ui minor`.

- [ ] **Step 1: Confirm the branch is complete and clean**

```bash
git -C "$WT" log --oneline main..HEAD | head -80     # V179-1..V179-20 commits, the results doc last
git -C "$WT" status --short                          # expect empty
git -C "$WT" log --oneline -1 -- docs/superpowers/results/2026-10-19-v179-layout-audit.md   # present
```

Run `/replicate-prod-db` if it has not run this session (the Python suite reaches the database; CLAUDE.md).

- [ ] **Step 2: The one full Python run**

Dispatch the `test-runner` subagent with: `cd "$WT" && python scripts/dev/testrun.py full` (runs `-n 4` and the complexity gate). Expected: `0 failed`, `0 xfailed`, the complexity gate reports no new offender (no Python file changed in this plan, so it cannot move). A changed pass count is not a failure (`docs/claude/testing-cost.md`); the likely movers are `tests/charts/test_chart_theme.py` (regenerated `resolved_tokens.json`, V179-1/V179-2) and `tests/hooks/test_codex_mirror.py` (V179-19).

- [ ] **Step 3: The frontend gates the CI `frontend-test` job runs**

Dispatch the `test-runner` subagent with these, in order, and have it report each exit code and the vitest totals only:

```bash
cd "$WT/frontend" && npm run lint
cd "$WT/frontend" && npx ng test --watch=false
cd "$WT/frontend" && npm run build
cd "$WT" && node --test frontend/scripts/layout-audit-lib.test.mjs
```

Expected: lint exits 0 with no new violation (a violation is fixed, never added to `frontend/eslint-suppressions.json`); vitest `0 failed`; the production build succeeds with no budget error; the audit library `fail 0`. A whole-suite vitest "Timeout waiting for worker to respond" at 60s is machine load (`frontend/vitest.config.ts` header): re-run `npx ng test --watch=false` once.

- [ ] **Step 4: On a failure, fix and re-run that test alone**

Each failure is fixed in the owning task's files (the index ledger names them) and re-run alone — `(cd "$WT/frontend" && npx ng test --watch=false --include <spec path relative to frontend/>)` or `python scripts/dev/testrun.py file <path>` — never by re-running the whole suite. Commit each fix on the branch as `fix(<area>): <what> -- v179 final gate`. A fix that touches layout (CSS or a template) re-runs the audit for the affected routes before moving on: `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440` must still exit 0 (V179-20 Step 1 for the local instance).

Record for the merge commit: Python `N passed, M skipped, 0 failed, 0 xfailed` and wall time; vitest `N passed, 0 failed`; lint clean; build ok.

**From here on: `main`, in the main tree `$R`.**

- [ ] **Step 5: Check for a concurrent session, then merge (no full suite after it)**

Follow the `worktree-lifecycle` skill before merging. Then:

```bash
git -C "$R" fetch origin
git -C "$R" status -sb                      # on main; clean except files another session owns -- never stage those
git -C "$R" log --oneline -1 origin/main; git -C "$R" log --oneline -1 main
git -C "$R" pull --ff-only                  # only if origin/main is ahead
git -C "$R" merge --no-ff 2026-10-19-v179-mobile-layout-consistency -m "merge(v179): mobile layout consistency -- compact rows and a row drawer on phone, the Dashboard trade drawer, one look per primitive

Python: <N passed, M skipped, 0 failed, 0 xfailed> (<wall time>); vitest: <N passed, 0 failed>; lint clean; build ok.
Layout audit: 0 unallowed findings at 390/768/1440; drawer round trip passed
(docs/superpowers/results/2026-10-19-v179-layout-audit.md).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

A conflict is resolved by hand in `$R` and checked with `python scripts/dev/testrun.py changed` plus the narrow `ng test --include` of each conflicted spec only. Do **not** push: a push to `main` deploys, and pushing is the partner's call.

- [ ] **Step 6: `/close-out` Step 2 — the panel over the merged diff**

Run `/panel staff-engineer,financial-advisor` (the spec's `**Panel:**` line) over `<merge commit>^1...<merge commit>` plus `docs/superpowers/results/2026-10-19-v179-layout-audit.md` (point the reviewers at the V179-20 screenshot directory if it still exists). Each role is dispatched serially. A `BLOCKING` finding stops here and goes to the partner (`AskUserQuestion`, recommended option first). An accepted `ADVISORY` is fixed on `main` test-first in the owning spec (`fix(ui): <what> -- v179 panel`, narrow run only) or answered. Then append to the index:

```markdown
## Panel review

Close-out review, <YYYY-MM-DD>, against <merge commit short sha>. <No BLOCKING findings. | ...>

- <role>: <finding> -- <applied in <sha> | answered: <why>>
```

```bash
git -C "$R" add docs/superpowers/plans/2026-10-19-v179-mobile-layout-consistency_0-index.md
git -C "$R" commit -m "docs(v179): panel review at close-out

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: `/close-out` Steps 3–4 — bump `ui` from disk, then regenerate**

Read `$R/VERSION.json` (never this plan or memory). At writing it is `"ui": "1.31.0"`, so the minor bump gives `1.32.0`; if disk says otherwise, bump the minor of what disk says and use that number below. Set `ui_updated` to now in the existing `YYYY-MM-DD HH-MM-SS` format; leave `bot` and `bot_updated` untouched. Commit `VERSION.json` alone:

```bash
git -C "$R" add VERSION.json
git -C "$R" commit -m "release(ui): 1.32.0 -- phone tables become two-line rows with a drawer; Dashboard trades open in a drawer; one look per primitive

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Then regenerate the history as its own next commit:

```bash
cd "$R" && python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git -C "$R" add swingbot/admin/version_history.json
git -C "$R" commit -m "chore(ui): 1.32.0 -- phone tables become two-line rows with a drawer; Dashboard trades open in a drawer; one look per primitive

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: the matrix test passes; the history's newest `ui` entry is the release commit, not `"commit": "uncommitted"`.

- [ ] **Step 8: `/close-out` Steps 5–7 — check the predictions, move the documents, remove the worktree**

The header predicted `Bump: ui minor` and `Edge: none (integrity)`. Both hold when the merge changed no Python, store, signal, gate, stop, size or badge: `git -C "$R" diff --stat <merge>^1 <merge> -- swingbot/ bot.py admin_ui.py scripts/` must print nothing (the regenerated history lands after the merge, in Step 7). If either did not hold, amend the index header in one clause and say why in the move commit.

```bash
cd "$R"
for f in _0-index _1-tokens-and-panels _2-controls-and-charts _3-tables _3b-research-risk-and-check _4-dashboard-and-pages _4b-page-fixes _5-audit-and-close-out; do
  git mv "docs/superpowers/plans/2026-10-19-v179-mobile-layout-consistency$f.md" docs/superpowers/plans/implemented/
done
git mv docs/superpowers/specs/2026-10-19-v179-mobile-layout-consistency-design.md docs/superpowers/specs/implemented/
git commit -m "docs(v179): close out -- mobile layout consistency implemented

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(`ls docs/superpowers/plans/ | grep v179` must print nothing afterwards; if a part file name differs on disk, move what is there.) Then remove the worktree and its branch — never a `backup` or `stable-*` branch:

```bash
git -C "$R" rev-list --count main..2026-10-19-v179-mobile-layout-consistency   # must print 0; anything else: stop
git -C "$R" worktree remove "$WT"
git -C "$R" branch -d 2026-10-19-v179-mobile-layout-consistency
git -C "$R" worktree list                                                      # v179 gone
```

No full suite after the merge. Delete the V179-20 scratch directory (`$AUDIT`) once the panel is done. The commits on `main` go out with the next push, which the partner asks for; CI's `frontend-test` job then re-runs lint, the vitest suite and the build.

