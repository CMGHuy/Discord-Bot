#!/usr/bin/env node
/**
 * v247 V247-16: the shell's navigation in a real browser (spec v240 §9, §11 E2E lines).
 * 1440/820: the rail (64px, order, 44px links, tooltip on hover and focus), no phone nav.
 * 320: the five-tab bar fits. 390: the editor round-trip (remove Watchlist, add Risk, Done,
 * reload, Reset) and its 44px targets.
 *   node frontend/scripts/shell-nav-check.mjs [--base http://localhost:1234] [--out DIR]
 * .env ADMIN_USERNAME/ADMIN_PASSWORD stay in this process, never printed. Exit 0 / 1 failed / 2 cannot run.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import {
  DEFAULT_TABS, EDITED_PATHS, EDITED_TABS, RAIL_PATHS, RAIL_WIDTH_PX, VIEWPORTS,
  exitCode, formatResult, parseArgs, sameList, smallTargets, tooltipVerdict,
} from './shell-nav-check-lib.mjs';

const ENV_FILE = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '.env');
const TAB_KEY = 'ui.tabbar';
const HOVER_WAIT_MS = 450; // HINT_HOVER_DELAY_MS (300) plus a frame
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

/** Runs in the page: a box per element, named by its aria-label or text. */
function boxesOf(elements) {
  return elements.map((el) => {
    const rect = el.getBoundingClientRect();
    return { name: el.getAttribute('aria-label') ?? el.textContent.trim(), width: rect.width, height: rect.height };
  });
}

/** Runs in the page: the link's name and the role=tooltip its aria-describedby names. */
function tooltipOf(link) {
  const ids = (link.getAttribute('aria-describedby') ?? '').split(/\s+/).filter(Boolean);
  const tip = ids.map((id) => document.getElementById(id)).find((el) => el?.getAttribute('role') === 'tooltip') ?? null;
  const rect = tip?.getBoundingClientRect();
  return { name: link.getAttribute('aria-label') ?? '', tooltip: tip ? tip.textContent.trim() : null, visible: Boolean(rect && rect.width > 0 && rect.height > 0) };
}

async function checkRail(page, at) {
  const links = page.locator('nav.rail a.rail-link');
  await page.locator('nav.rail').waitFor({ state: 'visible', timeout: 15000 });
  const width = await page.locator('nav.rail').evaluate((nav) => nav.getBoundingClientRect().width);
  check(`rail-width@${at}`, Math.round(width) === RAIL_WIDTH_PX, `${width}px`);
  const hrefs = await links.evaluateAll((all) => all.map((a) => a.getAttribute('href')));
  check(`rail-order@${at}`, sameList(hrefs, RAIL_PATHS), hrefs.join(' '));
  const small = smallTargets(await links.evaluateAll(boxesOf));
  check(`rail-targets@${at}`, small.length === 0, small.join(', '));
  for (const [how, path] of [['hover', '/watchlist'], ['focus', '/calendar']]) {
    const link = page.locator(`nav.rail a.rail-link[href="${path}"]`);
    await (how === 'hover' ? link.hover() : link.focus());
    await page.waitForTimeout(HOVER_WAIT_MS);
    const verdict = tooltipVerdict(await link.evaluate(tooltipOf));
    check(`rail-tooltip-${how}@${at}`, verdict === null, verdict ?? '');
    await page.keyboard.press('Escape');
    await page.mouse.move(0, 0);
  }
  const present = await page.evaluate(() =>
    ['sb-phone-tab-bar', 'sb-more-sheet', 'sb-tab-bar-editor'].filter((tag) => document.querySelector(tag)));
  check(`no-phone-nav@${at}`, present.length === 0, present.join(', '));
}

async function checkNarrowBar(page, at) {
  await page.locator('sb-phone-tab-bar').waitFor({ state: 'visible', timeout: 15000 });
  const fit = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const tabs = [...document.querySelectorAll('sb-phone-tab-bar .tab')].map((tab) => tab.getBoundingClientRect());
    return { count: tabs.length, inside: tabs.every((r) => r.left >= 0 && r.right <= vw + 0.5), noScroll: document.documentElement.scrollWidth <= vw };
  });
  check(`tab-bar-fits@${at}`, fit.count === 5 && fit.inside && fit.noScroll, JSON.stringify(fit));
}

const tabLabels = async (page) => (await page.locator('sb-phone-tab-bar .tab-label').allTextContents()).map((s) => s.trim());

async function openEditor(page) {
  await page.locator('sb-phone-tab-bar button.more').click();
  await page.locator('sb-more-sheet button.edit').click();
  await page.locator('sb-tab-bar-editor dialog[open] .editor').waitFor({ state: 'visible', timeout: 5000 });
}

async function closeEditorAndSheet(page) {
  await page.locator('sb-tab-bar-editor .actions button.done').click();
  await page.locator('sb-tab-bar-editor dialog[open]').waitFor({ state: 'detached', timeout: 5000 });
  const focusOnEdit = await page.evaluate(() => document.activeElement?.matches('sb-more-sheet button.edit') ?? false);
  await page.keyboard.press('Escape'); // the More sheet
  await page.locator('sb-more-sheet [role=dialog]').waitFor({ state: 'detached', timeout: 5000 });
  return focusOnEdit;
}

async function editorRoundTrip(page, at, out) {
  await page.evaluate((key) => localStorage.removeItem(key), TAB_KEY);
  await page.reload({ waitUntil: 'load' });
  await page.locator('sb-phone-tab-bar').waitFor({ state: 'visible', timeout: 15000 });
  check(`tabs-default@${at}`, sameList(await tabLabels(page), DEFAULT_TABS), (await tabLabels(page)).join(' '));
  await openEditor(page);
  const small = smallTargets(await page.locator('sb-tab-bar-editor .act, sb-tab-bar-editor .actions button').evaluateAll(boxesOf));
  check(`editor-targets@${at}`, small.length === 0, small.join(', '));
  const sideways = await page.locator('sb-tab-bar-editor dialog').evaluate((d) => d.scrollWidth > d.clientWidth);
  check(`editor-no-sideways-scroll@${at}`, !sideways);
  await page.screenshot({ path: join(out, `editor@${at}.png`) });
  await page.locator('sb-tab-bar-editor li[data-path="/watchlist"] button.remove').click();
  await page.locator('sb-tab-bar-editor li[data-path="/risk"] button.add').click();
  const said = (await page.locator('sb-tab-bar-editor .announce').textContent()).trim();
  check(`editor-announces@${at}`, said === 'Risk added to the tab bar', said);
  check(`editor-focus-returns@${at}`, await closeEditorAndSheet(page));
  check(`tabs-edited@${at}`, sameList(await tabLabels(page), EDITED_TABS), (await tabLabels(page)).join(' '));
  await page.reload({ waitUntil: 'load' });
  await page.locator('sb-phone-tab-bar').waitFor({ state: 'visible', timeout: 15000 });
  check(`tabs-survive-reload@${at}`, sameList(await tabLabels(page), EDITED_TABS), (await tabLabels(page)).join(' '));
  const stored = await page.evaluate((key) => localStorage.getItem(key), TAB_KEY);
  check(`tabs-stored@${at}`, stored === JSON.stringify(EDITED_PATHS), String(stored));
  await openEditor(page);
  await page.locator('sb-tab-bar-editor .actions button.reset').click();
  check(`reset-offers-undo@${at}`, await page.locator('sb-tab-bar-editor .actions button.undo').isVisible());
  await closeEditorAndSheet(page);
  check(`tabs-reset@${at}`, sameList(await tabLabels(page), DEFAULT_TABS), (await tabLabels(page)).join(' '));
}

async function runViewport(browser, state, viewport, base, out) {
  const { width, height } = viewport;
  const context = await browser.newContext({
    storageState: state, viewport: { width, height }, serviceWorkers: 'block', hasTouch: width < 1024, isMobile: width < 640,
  });
  const page = await context.newPage();
  try {
    await page.goto(`${base}/dashboard`, { waitUntil: 'load' });
    if (width >= 640) await checkRail(page, width);
    else if (width < 390) await checkNarrowBar(page, width);
    else await editorRoundTrip(page, width, out);
    await page.screenshot({ path: join(out, `${viewport.name}@${width}.png`) });
  } finally {
    await context.close();
  }
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const out = opts.out ?? join(tmpdir(), 'swingbot-shell-nav-check');
  mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  try {
    const state = await signedInState(browser, opts.base);
    for (const viewport of VIEWPORTS) await runViewport(browser, state, viewport, opts.base, out);
  } finally {
    await browser.close();
  }
  writeFileSync(join(out, 'results.json'), JSON.stringify(results, null, 2));
  console.log(`${results.filter((r) => r.ok).length}/${results.length} passed; shots and results.json in ${out}`);
  return exitCode(results);
}

main().then((code) => process.exit(code), (error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(2);
});
