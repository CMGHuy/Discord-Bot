#!/usr/bin/env node
/**
 * v168 motion evidence (plan MO18). CommonJS so NODE_PATH can point it at
 * frontend/node_modules from outside the frontend tree:
 *
 *   NODE_PATH=<tree>/frontend/node_modules node motion-evidence.cjs motion --base http://localhost:4124 --out <dir>
 *   NODE_PATH=<tree>/frontend/node_modules node motion-evidence.cjs trace --base http://localhost:4123 --out <dir> --label before
 *
 * Reuses browse.mjs's persistent profile, so sign in once with
 * `node frontend/scripts/browse.mjs login --base <base>` first. Never fills a
 * credential. Off is forced through <html data-motion>, never the Motion
 * control, so no preference is written.
 */
const { chromium } = require('playwright');
const { mkdirSync, writeFileSync } = require('node:fs');
const { homedir } = require('node:os');
const { join } = require('node:path');

const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const WIDTHS = [390, 768, 1440];
const LONG_TASK_US = 50_000;
const STEP_PAUSE_MS = 2500;

function parseArgs(args) {
  let argv = args;
  const opts = { cmd: argv[0], base: null, out: null, label: 'after', forceOff: argv.includes('--force-off') };
  argv = argv.filter((arg) => arg !== '--force-off');
  for (let i = 1; i < argv.length; i += 2) {
    const [flag, value] = [argv[i], argv[i + 1]];
    if (flag === '--base') opts.base = value.replace(/\/$/, '').replace(/(?<!\/app)$/, '/app');
    else if (flag === '--out') opts.out = value;
    else if (flag === '--label') opts.label = value;
    else throw new Error(`unknown flag ${flag}`);
  }
  if (!opts.base || !opts.out || !['motion', 'trace'].includes(opts.cmd)) {
    throw new Error('usage: motion-evidence.cjs motion|trace --base URL --out DIR [--label before|after]');
  }
  return opts;
}

/** Every running CSS animation: name, duration, and the element it runs on. */
function running(page) {
  return page.evaluate(() => document.getAnimations()
    .filter((animation) => animation.playState === 'running' && 'animationName' in animation)
    .map((animation) => {
      const target = animation.effect?.target;
      const where = target ? `${target.tagName.toLowerCase()}.${[...target.classList].join('.')}` : '?';
      return { name: animation.animationName, ms: Number(animation.effect.getTiming().duration), on: where };
    }));
}

const names = (samples) => [...new Set(samples.map((sample) => sample.name))].sort();

/** Preferences loaded (data-motion left `pending`) and the page has content. */
async function ready(page, path) {
  await page.waitForFunction(() => {
    const mode = document.documentElement.dataset.motion;
    const main = document.querySelector('main') ?? document.body;
    return mode !== undefined && mode !== 'pending' && main.innerText.trim().length > 200;
  }, null, { timeout: 30_000 }).catch(() => console.error(`not ready after 30s: ${path}`));
  await page.waitForTimeout(1500);
}

async function open(page, base, path, width) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`${base}${path}`, { waitUntil: 'load' });
  await ready(page, path);
}

/** Below 640px the nav is an overlay: summon it first. */
async function clickNav(page, path) {
  const link = page.locator(`.sidebar a[href$="${path}"]`).first();
  const menu = page.locator('.menu-button');
  if ((await menu.isVisible()) && (await page.locator('.shell.overlay-open').count()) === 0) await menu.click();
  await link.click();
}

async function shot(page, out, name) {
  await page.screenshot({ path: join(out, `${name}.png`) });
  console.error(join(out, `${name}.png`));
}

async function routeChange(page, opts, width) {
  await open(page, opts.base, '/dashboard', width);
  await clickNav(page, '/trades');
  await page.waitForURL('**/trades', { timeout: 30_000 });
  await page.waitForTimeout(60);
  const mid = await running(page);
  await shot(page, opts.out, `route@${width}-mid`);
  await page.waitForTimeout(1500);
  const settled = await running(page);
  await shot(page, opts.out, `route@${width}-settled`);
  return { mid: names(mid), settled: names(settled) };
}

async function drawer(page, opts, width) {
  // A cold deep link to /app/calendar falls through to the dashboard; enter through the sidebar.
  await open(page, opts.base, '/dashboard', width);
  await clickNav(page, '/calendar');
  await page.locator('button[aria-label="Previous month"]').waitFor({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  const day = page.locator('button.value, button.agenda-hit').first();
  for (let back = 0; back < 18 && (await day.count()) === 0; back += 1) {
    await page.locator('button[aria-label="Previous month"]').click();
    await page.waitForTimeout(400);
  }
  if ((await day.count()) === 0) return { error: 'no button.value on /calendar (see Step 4)' };
  await day.click();
  await page.waitForTimeout(80);
  const opening = await running(page);
  await shot(page, opts.out, `drawer@${width}-opening`);
  await page.waitForTimeout(800);
  await shot(page, opts.out, `drawer@${width}-open`);
  await page.locator('sb-drawer .close').first().click();
  await page.waitForTimeout(60);
  const closing = await running(page);
  await shot(page, opts.out, `drawer@${width}-closing`);
  await page.waitForTimeout(600);
  return { opening: names(opening), closing: names(closing) };
}

/** Off, with the network slowed so the route spinner shows. */
async function offMode(page, opts, width) {
  await open(page, opts.base, '/dashboard', width);
  await page.evaluate(() => { document.documentElement.dataset.motion = 'off'; });
  // Load the Trades chunk first: the route overlay only shows once the resolver has been pending for
  // ROUTE_LOADING_DELAY_MS, and a slowed network would delay the chunk itself past the sample.
  await clickNav(page, '/trades');
  await page.waitForURL('**/trades', { timeout: 30_000 });
  await page.waitForTimeout(1500);
  await clickNav(page, '/dashboard');
  await page.waitForTimeout(1500);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 8000, downloadThroughput: -1, uploadThroughput: -1 });
  await clickNav(page, '/trades');
  await page.waitForTimeout(2200);
  const loading = await running(page);
  await shot(page, opts.out, `off@${width}-loading`);
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  await page.waitForURL('**/trades', { timeout: 30_000 });
  await page.locator('.route-loading-mark').waitFor({ state: 'detached', timeout: 20_000 }).catch(() => {});
  await page.waitForTimeout(2000);
  const settled = await running(page);
  await shot(page, opts.out, `off@${width}-settled`);
  await cdp.detach();
  return { loading: names(loading), spinDurations: loading.filter((a) => a.name === 'sb-route-spin').map((a) => a.ms), settled: names(settled) };
}

async function motion(page, opts) {
  const result = {};
  for (const width of WIDTHS) {
    result[width] = {
      route: await routeChange(page, opts, width),
      drawer: await drawer(page, opts, width),
      off: await offMode(page, opts, width),
    };
  }
  writeFileSync(join(opts.out, 'animations.json'), `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result, null, 2));
}

/** Metadata plus complete events of 1ms or more: small enough to commit, still loadable. */
function slim(events) {
  return events.filter((event) => event.ph === 'M' || (event.ph === 'X' && event.dur >= 1000));
}

function heaviestChildren(events, task) {
  return events
    .filter((event) => event.ph === 'X' && event.tid === task.tid && event.pid === task.pid && event !== task
      && event.ts >= task.ts && event.ts + event.dur <= task.ts + task.dur && event.name !== 'RunTask')
    .sort((a, b) => b.dur - a.dur)
    .slice(0, 3)
    .map((event) => `${event.name} ${(event.dur / 1000).toFixed(1)}ms ${event.args?.data?.url ?? event.args?.data?.functionName ?? ''}`.trim());
}

function longTasks(events) {
  const start = Math.min(...events.filter((event) => event.ts > 0).map((event) => event.ts));
  return events
    .filter((event) => event.ph === 'X' && event.name === 'RunTask' && event.dur > LONG_TASK_US)
    .map((task) => ({ atMs: Math.round((task.ts - start) / 1000), durMs: Math.round(task.dur / 1000), top: heaviestChildren(events, task) }));
}

async function trace(page, opts) {
  await open(page, opts.base, '/dashboard', 1440);
  if (opts.forceOff) await page.evaluate(() => { document.documentElement.dataset.motion = 'off'; });
  const cdp = await page.context().newCDPSession(page);
  const events = [];
  cdp.on('Tracing.dataCollected', ({ value }) => events.push(...value));
  const done = new Promise((resolve) => cdp.once('Tracing.tracingComplete', resolve));
  await cdp.send('Tracing.start', { categories: 'devtools.timeline,disabled-by-default-devtools.timeline', transferMode: 'ReportEvents' });
  await clickNav(page, '/trades');
  await page.waitForTimeout(STEP_PAUSE_MS);
  await clickNav(page, '/dashboard');
  await page.waitForTimeout(STEP_PAUSE_MS);
  await cdp.send('Tracing.end');
  await done;
  const kept = slim(events);
  writeFileSync(join(opts.out, `trace-${opts.label}.json`), JSON.stringify({ traceEvents: kept }));
  console.log(JSON.stringify({ label: opts.label, events: kept.length, longTasks: longTasks(kept) }, null, 2));
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  mkdirSync(opts.out, { recursive: true });
  const context = await chromium.launchPersistentContext(PROFILE, { headless: false, viewport: { width: 1440, height: 900 } });
  try {
    const page = context.pages()[0] ?? (await context.newPage());
    await (opts.cmd === 'motion' ? motion(page, opts) : trace(page, opts));
  } finally {
    await context.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
