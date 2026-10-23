#!/usr/bin/env node
/**
 * v179 layout audit -- the pre-merge check for every UI change
 * (docs/claude/ui-design.md § Checklist; spec
 * docs/superpowers/specs/2026-10-19-v179-mobile-layout-consistency-design.md §3.5, §6a.6).
 *
 * Visits every route and tab (layout-audit-lib.mjs ROUTES) at each width,
 * headless, on browse.mjs's persistent profile, and reports seven checks:
 *   overflow   the page (document, body or the shell's <main> pane) is wider than the viewport
 *   offscreen  text past the right edge of the viewport, outside any scroll box
 *   clipped    text cut by its own overflow/ellipsis or by an overflow:hidden ancestor (never sr-only)
 *   tap        an interactive hit area under 44x44px (widths <= 1023 only; counts .sb-hit's ::after
 *              and a checkbox's label)
 *   text       text under 11px (SVG text at its rendered size)
 *   baseline   side-by-side text in one flex/grid row whose baselines differ by more than 2px
 *   vcenter    a table cell's content more than 2px off the middle of its row, or an icon
 *              (svg, img, checkbox/radio) more than 2px off the centre line of the text beside it
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
  CHECKS, FULL_WIDTHS, MAX_BASELINE_OFFSET_PX, MAX_CENTER_OFFSET_PX, MIN_TAP_PX, MIN_TEXT_PX, ROUTES, TOUCH_MAX_WIDTH,
  classify, countByCheck, dedupe, formatFinding, inScope, isVisuallyHidden, parseArgs, pickIds, resolveRoute, slug, validateAllow, vcenterGeometry,
} from './layout-audit-lib.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const ENV_FILE = join(HERE, '..', '..', '.env');
const DEFAULT_ALLOW = join(HERE, 'layout-audit.allow.json');

class CannotRun extends Error {}

/** Runs inside the page (page.evaluate): self-contained, no imports, no closures over module scope. */
function auditPage({ touch, minTap, minText, maxBaseline, maxCenter, hiddenSrc, geometrySrc }) {
  const isVisuallyHidden = new Function(`return ${hiddenSrc}`)();
  const geo = new Function(`return (${geometrySrc})()`)();
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
  /** The element or an ancestor is visually hidden (an sr-only class, or the collapsed rail's inline pattern). */
  function srOnly(el) {
    for (let p = el; p && p !== document.body; p = p.parentElement) {
      if (isVisuallyHidden(getComputedStyle(p), p.getBoundingClientRect())) return true;
    }
    return false;
  }
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

  /** Vertical extent of what a box shows: its text lines plus icons and form marks, never its padding. */
  function inkBox(root, skip) {
    let top = Infinity;
    let bottom = -Infinity;
    const take = (r) => {
      if (r.height > 0) [top, bottom] = [Math.min(top, r.top), Math.max(bottom, r.bottom)];
    };
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.textContent.trim() || skip?.contains(n) || !visible(n.parentElement) || srOnly(n.parentElement)) continue;
      const range = document.createRange();
      range.selectNodeContents(n);
      [...range.getClientRects()].forEach(take);
    }
    root.querySelectorAll('svg, img, input[type="checkbox"], input[type="radio"]').forEach((m) => {
      if (!m.parentElement?.closest('svg') && visible(m) && !skip?.contains(m)) take(m.getBoundingClientRect());
    });
    return top === Infinity ? null : { top, bottom };
  }

  /** A table cell's content sits in the middle of its row (the cell's box minus its padding). */
  function checkCell(td) {
    const ink = inkBox(td);
    if (!ink) return;
    const cs = getComputedStyle(td);
    const box = geo.contentBox(td.getBoundingClientRect(), {
      padTop: parseFloat(cs.paddingTop), padBottom: parseFloat(cs.paddingBottom),
      borderTop: parseFloat(cs.borderTopWidth), borderBottom: parseFloat(cs.borderBottomWidth),
    });
    const offset = geo.centreOffset(ink, box);
    if (Math.abs(offset) > maxCenter) add('vcenter', td, `cell content ${offset > 0 ? 'low' : 'high'} by ${Math.abs(offset).toFixed(1)}px`);
  }

  /** Text on the icon's own line, beside it: the nearest ancestor (3 up) that holds any. */
  function textBeside(icon) {
    const ir = icon.getBoundingClientRect();
    for (let p = icon.parentElement, depth = 0; p && depth < 3; p = p.parentElement, depth += 1) {
      const rects = [];
      const walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (!n.textContent.trim() || icon.contains(n) || !visible(n.parentElement) || srOnly(n.parentElement)) continue;
        const range = document.createRange();
        range.selectNodeContents(n);
        rects.push(...range.getClientRects());
      }
      const beside = geo.nearestBeside(ir, rects);
      if (beside) return beside;
    }
    return null;
  }

  /** An icon (or checkbox/radio mark) and the text beside it share a centre line. */
  function checkIcon(icon) {
    const ir = icon.getBoundingClientRect();
    if (ir.width > 32 || ir.height > 32 || icon.querySelector?.('text')) return; // a chart, not an icon
    const t = textBeside(icon);
    if (!t) return;
    const offset = geo.centreOffset(ir, t);
    if (Math.abs(offset) > maxCenter) add('vcenter', icon, `icon ${offset > 0 ? 'low' : 'high'} by ${Math.abs(offset).toFixed(1)}px against its text`);
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
    if (el.matches('tr > td, tr > th') && el.parentElement.children.length > 1) checkCell(el);
    if (el.matches('svg, img, input[type="checkbox"], input[type="radio"]') && !el.parentElement.closest('svg')) checkIcon(el);
  }
  return findings;
}

/** Same page-ready rule as browse.mjs: never 'networkidle' (the SPA holds an event stream open). */
function ready() {
  const main = document.querySelector('main') ?? document.body;
  return main.innerText.trim().length > 200 && !/Loading/.test(document.body.innerText)
    && document.querySelector('.skeleton') === null;
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

async function getJson(page, url, attempts = 3) {
  try {
    return await page.evaluate(async (target) => {
      const res = await fetch(target, { credentials: 'include' });
      if (!res.ok) throw new Error(`${res.status} ${target}`);
      return res.json();
    }, url);
  } catch (error) {
    // The SPA's own redirect (/ -> /dashboard) can destroy the context mid-call: settle and retry.
    if (attempts <= 1 || !/context was destroyed/.test(String(error))) throw error;
    await page.waitForLoadState('load');
    return getJson(page, url, attempts - 1);
  }
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
    serviceWorkers: 'block', // the app's ngsw would serve the profile's cached build, not the one under test
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
    const limits = { touch: width <= TOUCH_MAX_WIDTH, minTap: MIN_TAP_PX, minText: MIN_TEXT_PX, maxBaseline: MAX_BASELINE_OFFSET_PX, maxCenter: MAX_CENTER_OFFSET_PX };
    const findings = [];
    for (const route of ROUTES) {
      await page.goto(`${opts.base}${resolveRoute(route, opts.ids)}`, { waitUntil: 'load' });
      await page.waitForFunction(ready, null, { timeout: 30_000 })
        .catch(() => console.error(`still loading after 30s: ${route} @${width}`));
      await page.waitForTimeout(opts.settle);
      const raw = await page.evaluate(auditPage, { ...limits, hiddenSrc: isVisuallyHidden.toString(), geometrySrc: vcenterGeometry.toString() });
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
