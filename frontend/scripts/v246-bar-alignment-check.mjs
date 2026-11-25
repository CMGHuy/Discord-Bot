#!/usr/bin/env node
/**
 * v246 V246-18: every bar v246 wraps in sb-field lines its fields up on one bottom edge per
 * visual row, with every control --control-h tall, at 390, 820 and 1440 (spec v246 "Three
 * devices", index Handoff 9). With --audit, also fails on the layout audit's overflow, tap
 * and text findings on those five pages.
 *   node frontend/scripts/v246-bar-alignment-check.mjs [--base http://localhost:1234] [--out DIR] [--audit FILE]
 * .env ADMIN_USERNAME/ADMIN_PASSWORD stay in this process, never printed. Exit 0 / 1 failed / 2 cannot run.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import {
  BARS, VIEWPORTS, auditVerdict, bottomVerdict, controlHeightAt, exitCode, formatResult, heightVerdict, parseArgs,
} from './v246-bar-alignment-check-lib.mjs';

const ENV_FILE = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '.env');
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

/** Runs in the page: each visible sb-field in the bar, and each control inside it (an sb-hint trigger is not one). */
function measure(barSelector) {
  const bar = document.querySelector(barSelector);
  const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const fields = bar ? [...bar.querySelectorAll('sb-field')].filter(shown) : [];
  const nameOf = (field) => field.querySelector('.field-label')?.textContent.trim() || field.textContent.trim().slice(0, 24);
  return {
    fields: fields.map((field) => {
      const r = field.getBoundingClientRect();
      return { name: nameOf(field), top: r.top, bottom: r.bottom };
    }),
    controls: fields.flatMap((field) => [...field.querySelectorAll('select, input:not([type="hidden"]), button')]
      .filter((el) => shown(el) && !el.closest('sb-hint'))
      .map((el) => ({ name: `${nameOf(field)}:${el.getAttribute('aria-label') ?? el.textContent.trim().slice(0, 12)}`,
        height: el.getBoundingClientRect().height }))),
  };
}

async function checkBar(page, spec, width, base, out) {
  const at = `${spec.name}@${width}`;
  const bar = page.locator(spec.bar).first();
  try {
    await page.goto(`${base}${spec.path}`, { waitUntil: 'domcontentloaded' });
    await bar.waitFor({ state: 'visible', timeout: 60000 });
  } catch (error) {
    check(`fields-${at}`, false, `bar at ${page.url()} did not render: ${String(error).split(/\r?\n/, 1)[0]}`);
    return;
  }
  const sheetToggle = bar.locator('.toolbar-sheet-button[aria-expanded="false"]');
  if (await sheetToggle.isVisible()) await sheetToggle.click();
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  const { fields, controls } = await page.evaluate(measure, spec.bar);
  check(`fields-${at}`, fields.length > 0 && controls.length > 0, 'no visible field controls in the bar');
  const rows = bottomVerdict(fields);
  check(`bottom-edge-${at}`, rows.length === 0, rows.join('; '));
  const heights = heightVerdict(controls, controlHeightAt(width));
  check(`control-h-${at}`, heights.length === 0, `expected ${controlHeightAt(width)}px: ${heights.join(', ')}`);
  await bar.screenshot({ path: join(out, `${spec.name}@${width}.png`) });
}

async function runViewport(browser, state, viewport, base, out) {
  const { width, height } = viewport;
  const context = await browser.newContext({
    storageState: state, viewport: { width, height }, serviceWorkers: 'block', hasTouch: width < 1024, isMobile: width < 640,
  });
  const page = await context.newPage();
  try {
    for (const spec of BARS) await checkBar(page, spec, width, base, out);
  } finally {
    await context.close();
  }
}

function checkAudit(file) {
  const { unallowed } = JSON.parse(readFileSync(file, 'utf8'));
  if (!Array.isArray(unallowed)) throw new CannotRun('expected unallowed findings in the layout audit JSON');
  const found = auditVerdict(unallowed);
  check('layout-audit-bar-pages', found.length === 0, found.join('; '));
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const out = opts.out ?? join(tmpdir(), 'swingbot-v246-bar-alignment');
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
