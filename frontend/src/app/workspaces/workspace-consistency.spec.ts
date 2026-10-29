import { allSources } from '../ui/testing/all-sources';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = join(process.cwd(), 'src/app/workspaces');

/** Every workspace component file, excluding specs and the gallery. */
function workspaceSources(): { name: string; path: string; source: string }[] {
  const out: { name: string; path: string; source: string }[] = [];
  for (const dir of readdirSync(ROOT, { withFileTypes: true })) {
    if (!dir.isDirectory() || dir.name === 'gallery') continue;
    for (const file of readdirSync(join(ROOT, dir.name))) {
      if (!file.endsWith('.ts') || file.endsWith('.spec.ts') || file.endsWith('.routes.ts')) continue;
      const path = join(ROOT, dir.name, file);
      out.push({ name: `${dir.name}/${file}`, path, source: readFileSync(path, 'utf8') });
    }
  }
  return out;
}

const SOURCES = workspaceSources();

describe('workspace consistency (v85)', () => {
  it('finds workspace sources at all', () => {
    expect(SOURCES.length).toBeGreaterThan(0);
  });

  it('writes no h1 of its own — sb-page renders the one heading (D4, v195)', () => {
    const offenders = SOURCES.filter((s) => /<h1[\s>]/.test(s.source)).map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('uses sb-panel rather than a hand-rolled card', () => {
    const offenders = SOURCES
      .filter((s) => /class="panel"/.test(s.source) && !/sb-panel/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('uses the shared control bar wherever a page has filters (D22)', () => {
    // v95 C1 superseded D22's sb-control-bar with sb-toolbar for any page
    // whose filters need to collapse into a sheet rather than wrap -- Trades
    // dropped sb-control-bar entirely in favour of it, keeping sb-filter-bar
    // only for the narrower "N active / Clear all" summary strip. Either
    // shared primitive satisfies the rule this test guards: no page hand-
    // rolls its own filters bar.
    const offenders = SOURCES
      .filter((s) => /sb-filter-bar|class="filters"/.test(s.source) && !/sb-control-bar|sb-toolbar/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('sizes metric grids with auto-fit rather than a fixed column count', () => {
    const offenders = SOURCES
      // Calendar matrices are intentionally seven fixed weekday columns;
      // this rule is about metric grids, where fixed columns strand content
      // at phone width. A calendar's geometry is semantic, not responsive
      // card layout.
      // v166: Trade Detail's `.card-grid` takes its tracks from named
      // grid-template-areas at fixed container widths, and its cards' two-column
      // `dl` only exists at >= 640px; neither is a metric grid.
      .filter((s) => /grid-template-columns:\s*repeat\(\s*\d/.test(s.source)
        && !/\.week, \.weekhead|\.grid \{[\s\S]*weekday/.test(s.source)
        && s.source.split('\n').some((line) => /grid-template-columns:\s*repeat\(\s*\d/.test(line)
          && !/^\s*(\.card-grid|dl) \{/.test(line)))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('never restyles the inside of a shared tile (v179 §3.3)', () => {
    // Calendar's ::ng-deep rules forced sb-stat-tile into an inline,
    // centred variant that read differently from every other page. A page
    // places tiles in a grid; the tile owns its inside. allSources(), not
    // SOURCES: it also reaches nested folders such as calendar/day/.
    const offenders = allSources()
      .filter(({ name }) => name.startsWith('app/workspaces/'))
      .filter(({ source }) => /::ng-deep[^{]*sb-(stat-tile|metric-card)/.test(source))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });

  it('declares a freshness marker on every page that fetches (D30)', () => {
    const offenders = SOURCES
      // `sb-async` owns the per-panel stale timestamp when the page's API
      // response has no independently meaningful source timestamp. Pages
      // with a source timestamp add `sb-freshness`; either contract must be
      // explicit, rather than requiring an unknown-age marker everywhere.
      .filter((s) => /sb-async/.test(s.source)
        && !/sb-freshness|\[staleAsOf\]/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });
});

describe('compact rows are declared, never hand-built (v179 §3.1, §4)', () => {
  it('no workspace builds or restyles the compact row or row drawer itself', () => {
    // sb-data-table owns this DOM. A workspace that writes it (or reaches
    // into it with ::ng-deep) is hand-rolling cards -- the §4 anti-goal.
    const offenders = SOURCES
      .filter((s) => /compact-(?:list|row|hit|footer)|drawer-fields|\.line[12]\b/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it.each([
    'trades/trades.columns.ts',
    'watchlist/watchlist.ts',
    'watchlist/ticker-detail.ts',
    'research/research.ts',
    'risk/risk.ts',
  ])('%s declares its compact row', (name) => {
    expect(SOURCES.find((s) => s.name === name)?.source ?? '').toContain('compact: { line: 1, order: 1 }');
  });
});

/* -- v195 Phase 4, §5.2, § Testing -- every route is an sb-page ------------- */

const APP = join(process.cwd(), 'src/app');

/** Every route entry component, relative to src/app/workspaces. Pinned by
 *  hand so a new route is a deliberate edit here; the first case proves the
 *  list equals what the route files actually load. */
const PAGE_ROUTES = [
  'analytics/analytics.ts',
  'calendar/calendar.ts',
  'calendar/day/calendar-day.ts',
  'cancels/cancels.ts',
  'dashboard/dashboard.ts',
  'gallery/gallery.ts',
  'plans/plan-detail.ts',
  'reports/reports.ts',
  'research/research.ts',
  'risk/risk.ts',
  'system/system.ts',
  'trades/trade-detail.ts',
  'trades/trades.ts',
  'versions/versions.ts',
  'watchlist/ticker-detail.ts',
  'watchlist/watchlist.ts',
] as const;

/** Per-row commands: a destructive button on one row of a list, with its
 *  own confirm, that stays in its row rather than the page header (the
 *  sb-page contract). `danger-icon` (Watchlist's row bin) is the per-row
 *  variant and is never matched; this lists the rows that use a labelled
 *  danger-quiet button instead, each with its reason. */
const ROW_COMMANDS: Record<string, string> = {
  'app/workspaces/analytics/tabs/tuning.ts': "each proposal's own Delete, behind its own confirm",
};

/** The files every `loadComponent` imports, from app.routes.ts and each
 *  *.routes.ts under workspaces/, relative to workspaces/. */
function routeEntries(): string[] {
  const files = [join(APP, 'app.routes.ts')];
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith('.routes.ts')) files.push(full);
    }
  };
  walk(ROOT);
  const out = new Set<string>();
  for (const file of files) {
    const source = readFileSync(file, 'utf8');
    for (const [, target] of source.matchAll(/loadComponent:\s*\(\)\s*=>\s*import\('([^']+)'\)/g)) {
      out.add(relative(ROOT, join(dirname(file), `${target}.ts`)).replace(/\\/g, '/'));
    }
  }
  return [...out].sort();
}

/** The component's inline template (the first `template: \`…\``), with
 *  escapes resolved and HTML comments removed. Only the template is scanned:
 *  TypeScript generics such as `signal<string>` would read as tags. */
function templateOf(source: string): string {
  const open = 'template: `';
  const start = source.indexOf(open);
  if (start < 0) return '';
  let out = '';
  for (let i = start + open.length; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === '`') break;
    if (ch === '\\') { out += source[i + 1] ?? ''; i += 1; continue; }
    out += ch;
  }
  return out.replace(/<!--[\s\S]*?-->/g, '');
}

interface Tag { name: string; attrs: string; close: boolean; selfClosing: boolean; index: number }

/** Opening and closing tags in order. Attribute values are double-quoted in
 *  every template here, so a `>` inside one never ends the tag early. */
const TAG = /<\/([a-z][\w-]*)\s*>|<([a-z][\w-]*)((?:\s+[^\s=>/"']+(?:\s*=\s*"[^"]*")?)*)\s*(\/?)>/g;

function tags(template: string): Tag[] {
  return [...template.matchAll(TAG)].map((m) => (m[1]
    ? { name: m[1], attrs: '', close: true, selfClosing: false, index: m.index! }
    : { name: m[2], attrs: m[3], close: false, selfClosing: m[4] === '/', index: m.index! }));
}

const hasAttr = (attrs: string, name: string): boolean =>
  new RegExp(`(?:^|\\s)${name}(?=\\s|=|$)`).test(attrs);

/** Index of the tag that closes list[i], or -1. */
function closingIndex(list: Tag[], i: number): number {
  let depth = 0;
  for (let j = i + 1; j < list.length; j += 1) {
    const tag = list[j];
    if (tag.name !== list[i].name || tag.selfClosing) continue;
    if (!tag.close) { depth += 1; continue; }
    if (depth === 0) return tag.index;
    depth -= 1;
  }
  return -1;
}

/** [open, close) source offsets of every element carrying page-actions. */
function actionRanges(list: Tag[]): [number, number][] {
  return list.flatMap((tag, i): [number, number][] => {
    if (tag.close || tag.selfClosing || !hasAttr(tag.attrs, 'page-actions')) return [];
    return [[tag.index, closingIndex(list, i)]];
  });
}

/** A danger or danger-quiet button, static or bound; never danger-icon. */
const DESTRUCTIVE = /(?:^|\s)variant="danger(?:-quiet)?"|\[variant\]="[^"]*'danger(?:-quiet)?'/;

/** How many destructive buttons in the source sit outside its page-actions. */
function destructiveOutsideActions(source: string): number {
  const list = tags(templateOf(source));
  const ranges = actionRanges(list);
  return list
    .filter((tag) => !tag.close && DESTRUCTIVE.test(tag.attrs))
    .filter((tag) => !ranges.some(([open, close]) => tag.index > open && tag.index < close))
    .length;
}

/** Elements carrying the slot attribute in the source's template. */
const slotCount = (source: string, slot: string): number =>
  tags(templateOf(source)).filter((tag) => !tag.close && hasAttr(tag.attrs, slot)).length;

const routeSource = (path: string): string => readFileSync(join(ROOT, path), 'utf8');

/** Every workspace .ts (nested tabs and panels included), the gallery aside:
 *  it demos every variant on purpose. */
const WORKSPACE_TS = allSources().filter(({ name }) => name.startsWith('app/workspaces/')
  && name.endsWith('.ts') && !name.startsWith('app/workspaces/gallery/'));

describe('every route is an sb-page (v195 Phase 4, § Testing)', () => {
  it('pins the route list to what the route files load', () => {
    expect(routeEntries()).toEqual([...PAGE_ROUTES]);
  });

  it.each(PAGE_ROUTES)('%s renders sb-page and imports Page', (path) => {
    const source = routeSource(path);
    expect(source).toContain('<sb-page');
    expect(source).toMatch(/import \{ Page \} from '(?:\.\.\/)+ui\/page';/);
    expect(source).toMatch(/imports:\s*\[[^\]]*\bPage\b/);
  });

  it.each(PAGE_ROUTES)('%s fills each slot with one element, and has one primary', (path) => {
    const source = routeSource(path);
    for (const slot of ['page-actions', 'page-scope', 'page-kpis']) {
      expect(slotCount(source, slot), slot).toBeLessThanOrEqual(1);
    }
    expect(slotCount(source, 'page-primary')).toBe(1);
  });

  it('leaves sb-section-head to the gallery: sb-page heads every page', () => {
    const offenders = PAGE_ROUTES
      .filter((path) => path !== 'gallery/gallery.ts')
      .filter((path) => /<sb-section-head[\s>]/.test(routeSource(path)));
    expect(offenders).toEqual([]);
  });
});

describe('destructive actions live in the header (v195 Phase 4, §5.2)', () => {
  it('keeps every danger and danger-quiet button inside [page-actions], per-row commands aside', () => {
    const offenders = WORKSPACE_TS
      .filter(({ name }) => !(name in ROW_COMMANDS))
      .map(({ name, source }) => ({ name, count: destructiveOutsideActions(source) }))
      .filter(({ count }) => count > 0)
      .map(({ name, count }) => `${name} (${count})`);
    expect(offenders).toEqual([]);
  });

  it('lists only per-row commands that still exist', () => {
    for (const name of Object.keys(ROW_COMMANDS)) {
      const file = WORKSPACE_TS.find((s) => s.name === name);
      expect(file, name).toBeDefined();
      expect(destructiveOutsideActions(file!.source), name).toBeGreaterThan(0);
    }
  });

  it('reads a button inside the header actions as placed, and one outside as not', () => {
    const inside = 'template: `<div page-actions class="a"><div><button sb-button variant="danger-quiet">x</button></div></div>`';
    const outside = 'template: `<div page-actions></div><button sb-button [variant]="n > 0 ? \'danger\' : \'ghost\'">x</button>`';
    const rowBin = 'template: `<button sb-button variant="danger-icon">x</button>`';
    expect(destructiveOutsideActions(inside)).toBe(0);
    expect(destructiveOutsideActions(outside)).toBe(1);
    expect(destructiveOutsideActions(rowBin)).toBe(0);
  });
});
