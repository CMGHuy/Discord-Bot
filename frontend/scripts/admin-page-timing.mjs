#!/usr/bin/env node
/**
 * Post-deploy production timing and label check (v201 V201-20).
 *
 * READ-ONLY against production: one login, then every non-GET request to
 * /api/v1 is aborted. Credentials come from the repo's .env, loaded inside
 * this process only -- never printed, logged, put in argv or in the JSONL.
 *
 *   node scripts/admin-page-timing.mjs --out <dir> [--base URL] [--scan-wait-min 20] [--passes cold,warm,scan]
 *
 * Exit 0 done, 2 preflight/login refused, 3 global deadline hit.
 */
import { appendFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const ACTION_TIMEOUT_MS = 20_000;
export const NAV_TIMEOUT_MS = 30_000;
export const PAGE_WAIT_MS = 30_000;
export const SETTLE_MS = 3_000;
export const GLOBAL_DEADLINE_MS = 30 * 60_000;
export const LIMITS = { firstDataMs: 2_000, callMs: 2_000, scanMs: 500 };
/** Out of scope by the index's endpoint sweep: bar-backed charts load behind their own spinner. */
export const EXCLUDED = [/\/api\/v1\/equity\/candles/, /\/chart/, /\/events$/];
export const PNL_BASIS = 'pre-tax, before modelled frictions';
export const PAGES = [
  { name: 'Dashboard', rail: 'Dashboard', selectors: ['sb-portfolio-value sb-market-value'] },
  { name: 'Trades', rail: 'Trades' }, { name: 'Trade detail', path: 'TRADE' }, { name: 'Watchlist', rail: 'Watchlist' },
  { name: 'Risk', rail: 'Risk', phrases: ['FX rates as of', 'daily bars through', PNL_BASIS] },
  { name: 'Analytics', rail: 'Analytics', route: '/insights/analytics', phrases: [PNL_BASIS] },
  { name: 'Calendar', rail: 'Calendar', route: '/trades/calendar', phrases: [PNL_BASIS] },
];
const LABEL = /\bago\b|last close|\bas of\b/;
const ENV_FILE = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '.env');

export const labelOk = ({ age, valueHidden }) => valueHidden || LABEL.test(age ?? '');

/** The spec's phrases not in `text`, then its selectors not `true` in `present`. */
export function missingRequirements(text, present, spec) {
  const phrases = (spec.phrases ?? []).filter((p) => !(text ?? '').includes(p));
  const selectors = (spec.selectors ?? []).filter((s) => present?.[s] !== true);
  return [...phrases, ...selectors];
}

/** null when /market/updates carries the v204 snapshot fields, else the exit-2 message. */
export function preflightSnapshots(body) {
  const ok = Array.isArray(body?.snapshots) && body.status && typeof body.status === 'object'
    && 'stale_snapshot_s' in body.status;
  return ok ? null : 'v204 not deployed: /market/updates has no snapshots';
}

export function visitVerdict(v) {
  const reasons = [];
  if (v.timedOut || v.firstDataMs === null || v.firstDataMs > LIMITS.firstDataMs) reasons.push('first data');
  if (v.calls.some((c) => !c.excluded && (c.ms === null || c.ms > LIMITS.callMs))) reasons.push('call > 2 s');
  if (v.scanMs.some((ms) => ms === null || ms > LIMITS.scanMs)) reasons.push('/system/scan > 0.5 s');
  if (v.unlabelled > 0) reasons.push('unlabelled value');
  if ((v.missing ?? []).length) reasons.push('missing label: ' + v.missing.join(', '));
  return { pass: reasons.length === 0, reasons };
}

export function renderTable(rows) {
  const head = '| Pass | Page | First data | Slowest page-load call | Max /system/scan | Cells / unlabelled | Verdict |\n|---|---|---|---|---|---|---|';
  const sec = (ms) => (ms === null ? 'timeout' : `${(ms / 1000).toFixed(1)} s`);
  return [head, ...rows.map((r) => `| ${r.pass} | ${r.page} | ${sec(r.firstDataMs)} | ${r.slowest} | ${r.scanMaxMs ?? '–'} ms | ${r.cells} / ${r.unlabelled} | ${r.verdict} |`)].join('\n');
}

// ---------------------------------------------------------------- browser side

function parseFlags(argv) {
  const flags = { base: 'https://bomeo-capital.com', scanWaitMin: 20, passes: ['cold', 'warm', 'scan'], out: null };
  for (let i = 0; i < argv.length; i += 2) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (k === '--base') flags.base = v.replace(/\/$/, '');
    else if (k === '--out') flags.out = v;
    else if (k === '--scan-wait-min') flags.scanWaitMin = Number(v);
    else if (k === '--passes') flags.passes = v.split(',');
  }
  if (!flags.out) { console.error('--out <dir> is required'); process.exit(2); }
  return flags;
}

function envCredentials() {
  try { process.loadEnvFile(ENV_FILE); } catch { return null; }
  const { ADMIN_USERNAME: username, ADMIN_PASSWORD: password } = process.env;
  return username && password ? { username, password } : null;
}

/** Abort every non-GET /api/v1 request except the one login; count the aborts. */
async function guardWrites(context, guard) {
  await context.route('**/api/v1/**', (route) => {
    const req = route.request();
    const login = req.method() === 'POST' && new URL(req.url()).pathname === '/api/v1/session';
    if (req.method() === 'GET' || req.method() === 'HEAD' || login) return route.continue();
    guard.aborted += 1;
    return route.abort();
  });
}

/** Record every GET /api/v1 request with its start time and response end. */
function trackRequests(page) {
  const records = [];
  const byReq = new Map();
  page.on('request', (req) => {
    if (req.method() !== 'GET' || !req.url().includes('/api/v1/')) return;
    const url = new URL(req.url());
    const rec = { path: url.pathname, start: Date.now(), ms: null };
    byReq.set(req, rec);
    records.push(rec);
  });
  page.on('requestfinished', (req) => {
    const rec = byReq.get(req);
    if (!rec) return;
    const end = req.timing().responseEnd;
    rec.ms = end >= 0 ? Math.round(end) : null;
  });
  return records;
}

async function getJson(page, path) {
  return page.evaluate(async (p) => {
    const res = await fetch(p, { credentials: 'include' });
    let body = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    return { status: res.status, body };
  }, path);
}

async function login(page, base) {
  const creds = envCredentials();
  if (!creds) return false;
  return page.evaluate(async ({ url, body }) => {
    const res = await fetch(url, { method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return res.ok;
  }, { url: `${base}/api/v1/session`, body: creds }).catch(() => false);
}

async function preflight(page) {
  const health = await getJson(page, '/api/v1/system/health');
  const status = health.body?.refresher?.status;
  if (health.status !== 200 || status !== 'ok') return `v201 not deployed or refresher not ok: ${status ?? health.status}`;
  const updates = await getJson(page, '/api/v1/market/updates');
  if (updates.status !== 200) return `v201 not deployed or refresher not ok: market/updates ${updates.status}`;
  return preflightSnapshots(updates.body);
}

async function labelScan(page, spec) {
  return page.evaluate((selectors) => ({
    cells: [...document.querySelectorAll('main.workspace sb-market-value')].map((el) => ({
      age: el.querySelector('.mv-age')?.textContent?.trim() ?? '',
      valueHidden: el.querySelector('.mv-value')?.hasAttribute('hidden') ?? false,
      error: !!el.querySelector('.mv-err'),
    })),
    text: document.querySelector('main.workspace')?.innerText ?? '',
    present: Object.fromEntries(selectors.map((s) => [s, document.querySelector(s) !== null])),
  }), spec.selectors ?? []);
}

async function navigate(ctx, spec, hardLoad) {
  const { page, base, tradeId } = ctx;
  if (spec.path === 'TRADE') { await page.goto(`${base}/trades/${tradeId}`, { waitUntil: 'domcontentloaded' }); return; }
  if (hardLoad) { await page.goto(`${base}/${spec.rail.toLowerCase()}`, { waitUntil: 'domcontentloaded' }); return; }
  const before = page.url();
  // The deployed rail carries its label as text, not aria-label, and Analytics / Calendar are
  // sub-pages of Insights / Trades rather than rail entries: reach those by an in-app router
  // navigation (history + popstate, no reload), the same path a link click takes.
  const link = page.locator('a.rail-link').filter({ has: page.locator('.rail-label', { hasText: new RegExp(`^\\s*${spec.rail}\\s*$`) }) });
  if (await link.count()) await link.first().click();
  else if (spec.route) await page.evaluate((r) => { history.pushState({}, '', r); dispatchEvent(new PopStateEvent('popstate')); }, spec.route);
  else throw new Error(`no navigation for ${spec.name}`);
  await page.waitForFunction((u) => location.href !== u, before).catch(() => {});
}

function summariseCalls(records, t0) {
  const inWindow = records.filter((r) => r.start >= t0);
  const isScan = (r) => r.path === '/api/v1/system/scan';
  const scanMs = inWindow.filter(isScan).map((r) => r.ms);
  const calls = inWindow.filter((r) => !isScan(r))
    .map((r) => ({ path: r.path, ms: r.ms, excluded: EXCLUDED.some((re) => re.test(r.path)) }));
  return { calls, scanMs };
}

function slowestOf(calls) {
  const inScope = calls.filter((c) => !c.excluded);
  if (!inScope.length) return '–';
  const worst = inScope.reduce((a, b) => ((b.ms ?? Infinity) > (a.ms ?? Infinity) ? b : a));
  return `${worst.path} ${worst.ms === null ? 'pending' : `${worst.ms} ms`}`;
}

async function waitForData(page) {
  try {
    await page.locator('main.workspace sb-async .content').first().waitFor({ state: 'visible', timeout: PAGE_WAIT_MS });
    return false;
  } catch { return true; }
}

function appendLine(out, obj) {
  appendFileSync(join(out, 'page-timing.jsonl'), `${JSON.stringify(obj)}\n`);
}

/** One page visit; appends its JSONL line before returning the table row (null when skipped). */
async function visit(ctx, spec, passName, hardLoad) {
  const { page, out, records, tradeId } = ctx;
  if (spec.path === 'TRADE' && !tradeId) { appendLine(out, { pass: passName, page: spec.name, skipped: 'no open trade' }); return null; }
  const t0 = Date.now();
  await navigate(ctx, spec, hardLoad);
  const timedOut = await waitForData(page);
  const firstDataMs = timedOut ? null : Date.now() - t0;
  await page.waitForTimeout(SETTLE_MS);
  const { cells, text, present } = await labelScan(page, spec);
  const { calls, scanMs } = summariseCalls(records, t0);
  const slug = spec.name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  await page.screenshot({ path: join(out, `${passName}-${slug}.png`), fullPage: true }).catch(() => {});
  const line = { pass: passName, page: spec.name, firstDataMs, timedOut, calls, scanMs,
    cells: cells.length, unlabelled: cells.filter((c) => !labelOk(c)).length, errors: cells.filter((c) => c.error).length,
    missing: missingRequirements(text, present, spec) };
  const verdict = visitVerdict(line);
  const label = verdict.pass ? 'PASS' : `FAIL (${verdict.reasons.join(', ')})`;
  appendLine(out, { ...line, verdict: label });
  return { ...line, slowest: slowestOf(calls), verdict: label,
    scanMaxMs: scanMs.length ? Math.max(...scanMs.map((m) => m ?? 0)) : null };
}

async function openContext(browser, flags, guard, storageState) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState });
  context.setDefaultTimeout(ACTION_TIMEOUT_MS);
  context.setDefaultNavigationTimeout(NAV_TIMEOUT_MS);
  await guardWrites(context, guard);
  const page = await context.newPage();
  const records = trackRequests(page);
  await page.goto(flags.base, { waitUntil: 'domcontentloaded' });
  return { context, page, records, base: flags.base, out: flags.out, tradeId: null };
}

async function pickTrade(ctx) {
  const res = await getJson(ctx.page, '/api/v1/trades?status=open&per_page=1');
  const body = res.body;
  const first = body?.items?.[0] ?? body?.trades?.[0] ?? body?.data?.[0] ?? (Array.isArray(body) ? body[0] : null);
  ctx.tradeId = first?.id ?? first?.trade_id ?? null;
}

async function runPages(ctx, passName, rows, hardFirst) {
  let first = hardFirst;
  for (const spec of PAGES) {
    const row = await visit(ctx, spec, passName, first && spec.rail === 'Dashboard');
    first = false;
    if (row) rows.push({ ...row, pass: passName, page: spec.name });
  }
}

async function scanPass(ctx, flags, rows) {
  const deadline = Date.now() + flags.scanWaitMin * 60_000;
  while (Date.now() < deadline) {
    const res = await getJson(ctx.page, '/api/v1/system/scan');
    if (res.body?.running === true) { await runPages(ctx, 'scan', rows, true); return; }
    await new Promise((r) => setTimeout(r, 10_000));
  }
  appendLine(flags.out, { pass: 'scan', skipped: `no scan observed in ${flags.scanWaitMin} min` });
}

async function signIn(ctx, flags) {
  if (!(await login(ctx.page, flags.base))) { console.error('login refused'); process.exit(2); }
  const problem = await preflight(ctx.page);
  if (problem) { console.error(problem); process.exit(2); }
  return ctx.context.storageState();
}

function versionsOf(body) {
  const v = body?.versions ?? body ?? {};
  return { ui: v.ui ?? null, bot: v.bot ?? null };
}

/** After a pass's visits: GET-only reads of the deployed versions, scan state, risk clocks and snapshots. */
async function recordInputs(ctx, passName) {
  const { page, out } = ctx;
  const [health, scan, risk, updates] = await Promise.all(
    ['/api/v1/health', '/api/v1/system/scan', '/api/v1/risk', '/api/v1/market/updates'].map((p) => getJson(page, p)));
  const meta = risk.body?.bars_meta ?? {};
  appendLine(out, { pass: passName, kind: 'inputs', at: new Date().toISOString(),
    versions: versionsOf(health.body), scanRunning: scan.body?.running ?? null,
    risk: { computed_at: risk.body?.computed_at ?? null, oldest: meta.oldest ?? null,
      newest: meta.newest ?? null, stale_inputs: meta.stale_inputs ?? null },
    snapshots: (updates.body?.snapshots ?? []).map((s) => ({ key: s.key, computed_at: s.computed_at,
      stale_inputs: s.stale_inputs, refreshing: s.refreshing, error: s.error })) });
}

async function runPass(passName, env) {
  await runPassVisits(passName, env);
  if (env.ctx) await recordInputs(env.ctx, passName);
}

async function runPassVisits(passName, env) {
  const { flags, rows } = env;
  if (passName === 'warm' && env.ctx) { await runPages(env.ctx, 'warm', rows, false); return; }
  if (env.ctx) await env.ctx.context.close();
  env.ctx = await openContext(env.browser, flags, env.guard, env.storage);
  if (!env.storage) env.storage = await signIn(env.ctx, flags);
  await pickTrade(env.ctx);
  if (passName === 'scan') await scanPass(env.ctx, flags, rows);
  else await runPages(env.ctx, passName, rows, true);
}

async function main() {
  setTimeout(() => { console.error('global deadline hit'); process.exit(3); }, GLOBAL_DEADLINE_MS).unref();
  const flags = parseFlags(process.argv.slice(2));
  mkdirSync(flags.out, { recursive: true });
  const { chromium } = await import('playwright');
  const env = { flags, rows: [], guard: { aborted: 0 }, storage: undefined, ctx: null,
    browser: await chromium.launch({ headless: true }) };
  try {
    for (const passName of flags.passes) await runPass(passName, env);
  } finally {
    await env.browser.close();
  }
  console.log(renderTable(env.rows));
  console.log(`non-GET requests aborted: ${env.guard.aborted}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((err) => { console.error(`probe failed: ${err.message}`); process.exit(1); });
}
