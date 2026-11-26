#!/usr/bin/env node
/**
 * v248 V248-16: the worst-case open-position rows (fixture v248-worst-case-row.json, served by
 * intercepting GET /api/v1/trades and GET /api/v1/market/updates) render on /dashboard and
 * /trades at 390, 768 and 1440 with no NOW, P&L % or R value clipped and no page-level
 * horizontal scroll. With --audit, also fails on any unallowed layout-audit finding on those
 * two routes.
 *   node frontend/scripts/v248-price-rows-check.mjs [--base http://localhost:1234] [--out DIR] [--audit FILE]
 * .env ADMIN_USERNAME/ADMIN_PASSWORD stay in this process, never printed. Exit 0 / 1 failed / 2 cannot run.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import {
  FIXTURE, PAGES, VIEWPORTS, auditVerdict, clipVerdict, exitCode, expectedText, fixtureRows, formatResult,
  isMarketUpdates, isTradesList, marketUpdatesBody, pageOverflowVerdict, parseArgs, tradesBody,
} from './v248-price-rows-check-lib.mjs';

const ENV_FILE = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '.env');
const TICKERS = ['DOCU', 'HOOD', 'CRWV'];
const results = [];

class CannotRun extends Error {}

function check(name, ok, detail = '') {
  const result = { name, ok: Boolean(ok), detail };
  results.push(result);
  console.log(formatResult(result));
}

async function signedInState(browser, base) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const page = await context.newPage();
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  try { process.loadEnvFile(ENV_FILE); } catch { /* no .env: the check below says so */ }
  const { ADMIN_USERNAME: username, ADMIN_PASSWORD: password } = process.env;
  const ok = Boolean(username && password) && await page.evaluate(async ({ url, body }) => (await fetch(url, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })).ok, { url: `${base}/api/v1/session`, body: { username, password } }).catch(() => false);
  const state = ok ? await context.storageState() : null;
  await context.close();
  if (!state) throw new CannotRun(`cannot sign in at ${base}: is the local admin up, and does .env set ADMIN_USERNAME/ADMIN_PASSWORD?`);
  return state;
}

/** Runs in the page: each value element in scope and the nearest ancestor (up to its cell) that clips it. */
function measureClips(scope) {
  const root = document.querySelector(scope);
  const cellTags = new Set(['TD', 'DD']);
  const isCell = (el) => cellTags.has(el.tagName) || el.getAttribute('role') === 'cell';
  const clipperOf = (el) => {
    const box = el.getBoundingClientRect();
    for (let node = el.parentElement; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      const hides = style.overflowX === 'hidden' || style.overflowX === 'clip';
      const outside = rect.left > box.left + 1 || rect.right < box.right - 1;
      const ellipsed = style.textOverflow === 'ellipsis' && node.scrollWidth > node.clientWidth + 1;
      if ((hides && outside) || ellipsed) return `${node.tagName.toLowerCase()}.${node.className} overflow:${style.overflowX}`;
      if (isCell(node)) return null;
    }
    return null;
  };
  const els = root ? [...root.querySelectorAll('.pp-value, .pp-none, .fig, .last-close-value, .pp-tag, .mv-err')] : [];
  return els.filter((el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
    .map((el) => ({ name: `${el.className} ${el.textContent.trim()}`, clippedBy: clipperOf(el) }));
}

async function checkPage(page, spec, width, base, out) {
  const at = `${spec.name}@${width}`;
  const scope = page.locator(spec.scope).first();
  try {
    await page.goto(`${base}${spec.path}`, { waitUntil: 'domcontentloaded' });
    await scope.getByText('DOCU').first().waitFor({ state: 'visible', timeout: 60000 });
  } catch (error) {
    check(`render-${at}`, false, String(error).split(/\r?\n/, 1)[0]);
    return;
  }
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  const shown = await Promise.all(TICKERS.map((t) => scope.getByText(t).first().isVisible()));
  check(`render-${at}`, shown.every(Boolean), `tickers not visible: ${TICKERS.filter((_, i) => !shown[i]).join(', ')}`);
  const text = await scope.innerText();
  const missing = expectedText(spec.name, width).filter((copy) => !text.includes(copy));
  check(`text-${at}`, missing.length === 0, `missing: ${missing.join(' | ')}`);
  const clips = clipVerdict(await page.evaluate(measureClips, spec.scope));
  check(`clip-${at}`, clips.length === 0, clips.join('; '));
  const overflow = pageOverflowVerdict(...await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]));
  check(`page-overflow-${at}`, overflow === null, overflow ?? '');
  await scope.screenshot({ path: join(out, `${at}.png`) });
}

async function runViewport(browser, state, viewport, base, out) {
  const { width, height } = viewport;
  const context = await browser.newContext({
    storageState: state, viewport: { width, height }, serviceWorkers: 'block', hasTouch: width < 1024, isMobile: width < 640,
  });
  const fixture = JSON.parse(readFileSync(FIXTURE, 'utf8'));
  await context.route((url) => isTradesList(url), (route) =>
    route.fulfill({ json: tradesBody(fixtureRows(fixture, Date.now()), new URL(route.request().url())) }));
  await context.route((url) => isMarketUpdates(url), (route) => route.fulfill({ json: marketUpdatesBody(Date.now()) }));
  const page = await context.newPage();
  try {
    for (const spec of PAGES) await checkPage(page, spec, width, base, out);
  } finally {
    await context.close();
  }
}

function checkAudit(file) {
  const { unallowed } = JSON.parse(readFileSync(file, 'utf8'));
  if (!Array.isArray(unallowed)) throw new CannotRun('expected unallowed findings in the layout audit JSON');
  const found = auditVerdict(unallowed);
  check('layout-audit-v248-pages', found.length === 0, found.join('; '));
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const out = opts.out ?? join(tmpdir(), 'swingbot-v248-price-rows');
  mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  try {
    const state = await signedInState(browser, opts.base);
    for (const viewport of VIEWPORTS) await runViewport(browser, state, viewport, opts.base, out);
  } finally {
    await browser.close();
  }
  if (opts.audit) checkAudit(opts.audit);
  else console.log('no --audit file: the layout-audit findings were not checked');
  writeFileSync(join(out, 'results.json'), JSON.stringify(results, null, 2));
  console.log(`${results.filter((r) => r.ok).length}/${results.length} passed; shots and results.json in ${out}`);
  return exitCode(results);
}

main().then((code) => process.exit(code), (error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(2);
});
