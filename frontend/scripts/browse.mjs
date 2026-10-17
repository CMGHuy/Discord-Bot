#!/usr/bin/env node
/**
 * Drive the admin UI (production at bomeo-capital.com by default) with
 * Playwright -- the one browser tool this repo uses (docs/claude/skills-tools.md).
 *
 * Headed, on a persistent profile outside the repo, so the session cookie
 * survives between runs: the partner types the credentials into the window
 * the first time (and whenever the session expires); this script never
 * fills, asks for or stores them.
 *
 *   node scripts/browse.mjs shots --out <dir> --path "/trades/ID?tab=live" [--path ...]
 *                                 [--widths 1440,1024,768,390] [--base URL]
 *   node scripts/browse.mjs api   --path /api/v1/trades?status=CLOSED   # prints JSON
 *   node scripts/browse.mjs login                                        # just sign in
 *
 * Every `shots` capture is a full-page PNG named <slug>@<width>.png, plus
 * <slug>@<width>.txt with the page's visible text.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright';

const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const LOGIN_TIMEOUT_MS = 5 * 60_000;

function parseArgs(argv) {
  const opts = { cmd: argv[0] ?? 'login', paths: [], widths: [1440, 1024, 768, 390], base: 'https://bomeo-capital.com', out: null };
  for (let i = 1; i < argv.length; i += 2) {
    const [flag, value] = [argv[i], argv[i + 1]];
    // Leading slash optional: Git Bash rewrites "/trades/x" into a Windows
    // path unless MSYS_NO_PATHCONV=1, so "trades/x" is the portable form.
    if (flag === '--path') opts.paths.push(value.startsWith('/') ? value : `/${value}`);
    else if (flag === '--widths') opts.widths = value.split(',').map(Number);
    else if (flag === '--base') opts.base = value.replace(/\/$/, '');
    else if (flag === '--out') opts.out = value;
    else throw new Error(`unknown flag ${flag}`);
  }
  return opts;
}

/** GET /api/v1/session always answers 200; `authenticated` is the answer. */
async function signedIn(page, base) {
  return page.evaluate(async (url) => {
    const res = await fetch(url, { credentials: 'include' });
    return res.ok && (await res.json()).authenticated === true;
  }, `${base}/api/v1/session`).catch(() => false);
}

async function ensureLogin(page, base) {
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  if (await signedIn(page, base)) return;
  console.error('Sign in in the browser window -- waiting up to 5 minutes...');
  const deadline = Date.now() + LOGIN_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await page.waitForTimeout(2000);
    if (await signedIn(page, base)) return console.error('Signed in.');
  }
  throw new Error('login timed out');
}

function slug(path) {
  return path.replace(/^\//, '').replace(/[^a-zA-Z0-9]+/g, '_').replace(/_$/, '') || 'root';
}

async function shots(page, opts) {
  if (!opts.out) throw new Error('--out is required for shots');
  mkdirSync(opts.out, { recursive: true });
  for (const width of opts.widths) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of opts.paths) {
      // Not 'networkidle': the SPA holds an event stream open, so the
      // network never idles. A fixed settle lets the stores render.
      // Lazy routes and stores show "Loading…" until they answer; wait them out.
      await page.goto(`${opts.base}${path}`, { waitUntil: 'load' });
      // The bare shell has no "Loading" text either, so also require the page
      // body (main) to have rendered real content.
      await page.waitForFunction(() => {
        const main = document.querySelector('main') ?? document.body;
        return main.innerText.trim().length > 200 && !/Loading/.test(document.body.innerText);
      }, null, { timeout: 30_000 })
        .catch(() => console.error(`still loading after 30s: ${path}`));
      await page.waitForTimeout(1500);
      const name = join(opts.out, `${slug(path)}@${width}`);
      // The shell scrolls an inner pane, not the document, so fullPage alone
      // stops at the fold: grow the viewport to the tallest scroller first.
      const tallest = await page.evaluate(() => Math.max(
        document.documentElement.scrollHeight,
        ...[...document.querySelectorAll('*')].filter((el) => el.scrollHeight > el.clientHeight + 4
          && /(auto|scroll)/.test(getComputedStyle(el).overflowY)).map((el) => el.scrollHeight + el.getBoundingClientRect().top),
      ));
      await page.setViewportSize({ width, height: Math.min(Math.ceil(tallest) + 40, 8000) });
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${name}.png`, fullPage: true });
      await page.setViewportSize({ width, height: 900 });
      writeFileSync(`${name}.txt`, await page.evaluate(() => document.body.innerText));
      console.error(`${name}.png`);
    }
  }
}

async function api(page, opts) {
  for (const path of opts.paths) {
    const body = await page.evaluate(async (url) => (await fetch(url, { credentials: 'include' })).text(), `${opts.base}${path}`);
    console.log(body);
  }
}

const opts = parseArgs(process.argv.slice(2));
const context = await chromium.launchPersistentContext(PROFILE, { headless: false, viewport: { width: 1440, height: 900 } });
try {
  const page = context.pages()[0] ?? (await context.newPage());
  await ensureLogin(page, opts.base);
  if (opts.cmd === 'shots') await shots(page, opts);
  else if (opts.cmd === 'api') await api(page, opts);
} finally {
  await context.close();
}
