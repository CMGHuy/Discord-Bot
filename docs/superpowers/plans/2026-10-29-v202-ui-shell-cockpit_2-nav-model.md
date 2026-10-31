# v202 UI shell cockpit, part 2: link moves, nav model, More/palette/tab bar, section tabs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md)
**Index:** [`_0-index.md`](2026-10-29-v202-ui-shell-cockpit_0-index.md): Goal, Global Constraints, Review Focus, Parallelisation and every cross-task contract live there and bind the tasks below.

Part scope: V202-5 … V202-8 (spec §1, §2 "In-app links", §3 "More sheet", §8 "Nav model" and "Routes"). V202-4 (part 1b) has already added the section routes and the old paths' redirects; these tasks move every link onto the new paths, replace the four-group nav model with six destinations, move the More sheet, palette and phone tab bar onto it, and add the shell-drawn section tabs. The rail itself stays the old one in v202; v203 (`2026-10-29-v203-ui-shell-cockpit-dock_0-index.md`) rewrites it in V203-1. V202-9 (part 3) is v202's full-suite run.

`<wt>` is the implementation worktree's absolute path. The **Files:** lists give full repo paths; elsewhere a FE path is relative to `<wt>/frontend/src/app/` unless it starts with `frontend/`.

# Phase 3: Navigation

### Task V202-5: Move every in-app link to the new paths; no-old-path spec

**Model:** sonnet — mechanical link and expectation moves across known lines, plus one regex-driven source scan whose self-test is spelled out.

**Files:**
- Create: `frontend/src/app/routing/old-paths.spec.ts`
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts:258` (link) and `:728` (comment)
- Modify: `frontend/src/app/workspaces/calendar/day/calendar-day.ts:119-133` (three links and the comment above them)
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts:175`
- Modify: `frontend/src/app/shell/palette/palette-items.ts:64-71` (`TAB_PAGES` routes only)
- Modify: `frontend/src/app/ui/hit-area.spec.ts:87`, `frontend/src/app/workspaces/calendar/calendar.spec.ts`, `frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts`, `frontend/src/app/routing/route-title.service.spec.ts:21,42`, `frontend/src/app/shell/palette/palette-items.spec.ts:39-45`
- Check only: `frontend/src/app/workspaces/calendar/day/month-context.spec.ts`. Its one `/calendar/pnl?month=` mention (:39) is the API endpoint, not a route, so leave it.

**Interfaces:**
- Consumes: V202-4's routes `trades/calendar` (children `''`, `:date`), `insights/analytics`, `insights/reports`, `system/versions`.
- Produces: no exported symbol. `OLD_PATH_WORDS = ['calendar','cancels','analytics','research','reports','versions']` is local to `old-paths.spec.ts`. V202-7 extends the guarantee to `pageItems()` once the palette reads `NAV_ENTRIES`. `shell/nav.ts`'s deprecated `NAV_GROUPS` keeps its old paths until V203-1 deletes it, which is why the scan below looks only at link contexts, never at `path:` keys.

Out of scope here: `stores/session.store.spec.ts:198-264` holds `'/analytics?tab=tuning'` as a stored return URL (a string the redirect still serves), not a link, so leave it. Every `navigate([], { queryParams })` call (analytics.ts, reports.ts, research.ts, system.ts, calendar.store.ts) is relative to the current URL and moves with the page.

- [ ] **Step 1: Write the failing no-old-path spec**

Create `frontend/src/app/routing/old-paths.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { TAB_PAGES } from '../shell/palette/palette-items';
import { allSources } from '../ui/testing/all-sources';

/**
 * v202 §2: the six page names that moved under a destination. Their old
 * paths still redirect (app.routes.ts, until Phase 4's close-out), but no
 * link inside the app may lean on that redirect: a hop through it costs a
 * navigation and lights the wrong rail entry for a frame.
 */
const OLD_PATH_WORDS = ['calendar', 'cancels', 'analytics', 'research', 'reports', 'versions'];

/**
 * Every way a source names a route: a static or bound routerLink, a router
 * call, a palette tab and a palette item's route. The path must START at the
 * old word, so '/trades/calendar' never matches, and the word must end there,
 * so '/reportsX' does not either. API paths ('/analytics/strategies' in a
 * comment, `${base}/calendar/pnl`) sit in no link context and never match.
 * `\x60` is a backtick (a template-literal route).
 */
const LINK_TO_OLD_PATH = new RegExp(
  String.raw`(?:routerLink="|\[routerLink\]="\['|navigate\(\['|navigateByUrl\(['\x60]|route: ['\x60]|tab\(')/(?:${OLD_PATH_WORDS.join('|')})(?![\w-])`,
);

const isOldPath = (route: string | null): boolean =>
  route !== null && OLD_PATH_WORDS.some((word) => route === `/${word}` || route.startsWith(`/${word}/`));

describe('no in-app link points at a pre-v202 path', () => {
  it.each([
    'routerLink="/calendar"',
    `[routerLink]="['/calendar', day]"`,
    `[routerLink]="['/calendar']"`,
    `tab('/analytics', 'Analytics', 'edge', 'Edge')`,
    `navigateByUrl('/versions')`,
    `navigate(['/reports'], { queryParams })`,
    `route: '/research'`,
    'route: `/cancels/${id}`',
  ])('the scan catches %s', (markup) => {
    expect(LINK_TO_OLD_PATH.test(markup)).toBe(true);
  });

  it.each([
    'routerLink="/trades/calendar"',
    `[routerLink]="['/trades/calendar', day]"`,
    `tab('/insights/analytics', 'Analytics', 'edge', 'Edge')`,
    `navigate(['/trades', id])`,
    '/** `/analytics/strategies`, for the read-only Strategy tab. */',
    "{ path: 'calendar', pathMatch: 'full', redirectTo: 'trades/calendar' }",
    'routerLink="/reportsX"',
  ])('the scan lets %s through', (markup) => {
    expect(LINK_TO_OLD_PATH.test(markup)).toBe(false);
  });

  it('finds no such link in any source under frontend/src', () => {
    const offenders = allSources()
      .filter((file) => /\.(ts|html)$/.test(file.name))
      .filter((file) => LINK_TO_OLD_PATH.test(file.source))
      .map((file) => file.name);
    expect(offenders).toEqual([]);
  });

  it('opens no palette tab on an old path', () => {
    expect(TAB_PAGES.filter((item) => isOldPath(item.route)).map((item) => item.key)).toEqual([]);
  });
});
```

- [ ] **Step 2: Move the expectations in the existing specs**

`ui/hit-area.spec.ts:87` becomes:

```ts
    ['src/app/workspaces/analytics/tabs/overview.ts', /<a class="sb-hit" routerLink="\/trades\/calendar"/],
```

In `shell/palette/palette-items.spec.ts:39-45`, the expected list becomes:

```ts
    expect(TAB_PAGES.map((item) => `${item.route}?tab=${item.queryParams!['tab']}`)).toEqual([
      '/insights/analytics?tab=attribution', '/insights/analytics?tab=execution', '/insights/analytics?tab=edge',
      '/insights/analytics?tab=pipeline', '/insights/analytics?tab=tuning', '/insights/analytics?tab=partials',
      '/insights/reports?tab=gates',
      '/system?tab=scan', '/system?tab=providers', '/system?tab=logs',
      '/watchlist?tab=earnings',
    ]);
```

In `routing/route-title.service.spec.ts`, the fixture route at :21 becomes `{ path: 'system/versions', component: Blank, title: 'Versions',` (its `data` line is unchanged), and :42 becomes `await router.navigateByUrl('/system/versions');`.

The two calendar specs mount the calendar routes at `calendar` and assert hrefs under `/calendar`. Move both onto `trades/calendar`. Single quotes are the only form either file uses:

```bash
sed -i "s#'/calendar#'/trades/calendar#g; s#path: 'calendar'#path: 'trades/calendar'#g" \
  <wt>/frontend/src/app/workspaces/calendar/calendar.spec.ts \
  <wt>/frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts
git -C <wt> grep -nE "'/calendar|path: 'calendar'" -- frontend/src/app/workspaces/calendar/
```

Expected from the grep: no output. The edited lines are calendar.spec.ts:459, 465, 670, 709, 722, 735, 751, 762 and 763, and calendar-day.spec.ts:332, 333, 342, 343, 355, 361, 381, 397, 406, 414, 427 and 433. Check with `git -C <wt> diff --stat` that only those two files changed in this step.

- [ ] **Step 3: Run the specs to verify they fail**

Run: `npm --prefix <wt>/frontend test -- --watch=false --include src/app/routing/old-paths.spec.ts`
Expected: FAIL. `finds no such link` lists `app/shell/palette/palette-items.ts`, `app/workspaces/analytics/tabs/overview.ts`, `app/workspaces/calendar/calendar.ts` and `app/workspaces/calendar/day/calendar-day.ts`. `opens no palette tab` lists the seven Analytics and Reports keys. The 15 pattern self-tests PASS.

Run: `npm --prefix <wt>/frontend test -- --watch=false --include src/app/workspaces/calendar/calendar.spec.ts`
Expected: FAIL on the two href assertions (:459, :465), which now expect `/trades/calendar/...`.

- [ ] **Step 4: Move the links**

`workspaces/calendar/calendar.ts:258`:

```html
        <a class="open-day" [routerLink]="['/trades/calendar', day]" [queryParams]="dayLinkParams()">Open full day →</a>
```

The comment at :728 becomes ``/** Only the filters that are set, so a bare day links as `/trades/calendar/<date>`. */``.

`workspaces/calendar/day/calendar-day.ts`: in the comment above `<div page-actions` (around :119-120), change "the breadcrumb crumb opens /calendar bare" to "the breadcrumb crumb opens /trades/calendar bare". The three links become:

```html
            <a class="prev" [routerLink]="['/trades/calendar', prev]" [queryParams]="store.filterParams()">‹ prev day</a>
```

```html
          <a class="month" [routerLink]="['/trades/calendar']" [queryParams]="backParams()">{{ monthName() ?? 'Calendar' }}</a>
```

```html
            <a class="next" [routerLink]="['/trades/calendar', next]" [queryParams]="store.filterParams()">next day ›</a>
```

`workspaces/analytics/tabs/overview.ts:175`:

```html
        <a class="sb-hit" routerLink="/trades/calendar">Open the calendar</a>
```

In `shell/palette/palette-items.ts:64-71`, the first seven `TAB_PAGES` rows change. The `page` argument (the second one) stays the page's own name, because it is the item's `sub`:

```ts
export const TAB_PAGES: readonly PaletteItem[] = [
  tab('/insights/analytics', 'Analytics', 'attribution', 'Attribution'),
  tab('/insights/analytics', 'Analytics', 'execution', 'Execution'),
  tab('/insights/analytics', 'Analytics', 'edge', 'Edge'),
  tab('/insights/analytics', 'Analytics', 'pipeline', 'Pipeline'),
  tab('/insights/analytics', 'Analytics', 'tuning', 'Tuning'),
  tab('/insights/analytics', 'Analytics', 'partials', 'Partials'),
  tab('/insights/reports', 'Reports', 'gates', 'Gate counterfactual'),
```

The `/system` and `/watchlist` rows below are unchanged. The item keys become `tab:/insights/analytics?attribution` and so on. Nothing stores them (the palette only ranks and navigates), so no migration is needed.

- [ ] **Step 5: Run the specs to verify they pass**

Run each one. Expected: PASS.

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/routing/old-paths.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/workspaces/calendar/calendar.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/workspaces/calendar/day/calendar-day.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/workspaces/calendar/day/month-context.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/routing/route-title.service.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/palette/palette-items.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/ui/hit-area.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include "src/app/workspaces/analytics/**/*.spec.ts"
npm --prefix <wt>/frontend run lint
```

Lint expected: clean.

Layout: no markup changes shape here, only a link's target. The three-width audit of the new paths is V203-10's. Report "no layout change" here.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add frontend/src/app/routing/old-paths.spec.ts \
  frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/day/calendar-day.ts \
  frontend/src/app/workspaces/analytics/tabs/overview.ts frontend/src/app/shell/palette/palette-items.ts \
  frontend/src/app/ui/hit-area.spec.ts frontend/src/app/workspaces/calendar/calendar.spec.ts \
  frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts frontend/src/app/routing/route-title.service.spec.ts \
  frontend/src/app/shell/palette/palette-items.spec.ts
git -C <wt> commit -m "feat(v202): move every in-app link onto the new section paths

Calendar day links, the Analytics overview's calendar link and the seven
Analytics/Reports palette tabs now point at /trades/calendar and
/insights/*. old-paths.spec scans every source for a link to a pre-v202
path, with a self-test of the scan.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V202-6: Nav model data: six destinations, sections, overrides, aliases, label invariant

**Model:** sonnet — new constant data in one model file, held by a fully written invariant spec; nothing that resolves a URL changes yet.

**Files:**
- Modify: `frontend/src/app/shell/nav.ts` (the `NavEntry` interface, the private aliases, new exports after `NAV_GROUPS`)
- Modify: `frontend/src/app/shell/nav.spec.ts` (V202-4's interim label test is retired; new describes are added)

**Interfaces:**
- Consumes: V202-4's route table in `app.routes.ts`. The label invariant reads each section route's `title`, and the alias test reads each old path's `redirectTo`.
- Produces (index "Nav model", final): `NavSection { path; label }`, `NavEntry.sections?: readonly NavSection[]`, `NavEntry.foot?: boolean`, `NAV_ENTRIES`, `SECTION_LABEL_OVERRIDES`, `DESTINATION_LABEL_OVERRIDES`, `SECTION_WORDS` and exported `ALIASES` (the full nine-key map).
- Left for V202-6b: `navEntryFor`, `destinationFor`, `isSectionUrl`, `breadcrumbFor`, `PHONE_TABS` and the `@deprecated` marks on `NAV_GROUPS`/`NavGroup`. Until then `navEntryFor` keeps resolving through `NAV_GROUPS` with the two pre-v202 aliases, renamed `GROUP_ALIASES`. That way `breadcrumb`, `phone-tab-bar`, `more-sheet` and `palette-items` behave exactly as before in this commit.

This task and V202-6b are one ledger task, split to stay under 20 KB. **Retired here, explicitly:** V202-4's interim `'labels each entry with its route title'` (it looked each old entry up at its moved path). The two-part invariant below replaces it: a section label is its route's title, and a destination label is its first section's title, each unless an override is recorded. The other `NAV_GROUPS` tests stay until V202-6b.

- [ ] **Step 1: Write the failing data spec**

In `frontend/src/app/shell/nav.spec.ts`, change the import from `./nav` to:

```ts
import {
  ALIASES, DESTINATION_LABEL_OVERRIDES, NAV_ENTRIES, NAV_GROUPS, PHONE_TABS, SECTION_LABEL_OVERRIDES,
  SECTION_WORDS, breadcrumbFor, detailCrumb, navEntryFor,
} from './nav';
```

Delete the test `'labels each entry with its route title'` (V202-4's interim version) from the `NAV_GROUPS` describe. Then add these two describes directly after it:

```ts
const titleAt = (path: string) => routes.find((route) => `/${route.path}` === path)?.title;

describe('NAV_ENTRIES (v202 §1)', () => {
  it('is six destinations in rail order, System alone at the foot', () => {
    expect(NAV_ENTRIES.map((entry) => [entry.path, entry.label])).toEqual([
      ['/dashboard', 'Dashboard'], ['/watchlist', 'Watchlist'], ['/trades', 'Trades'],
      ['/risk', 'Risk'], ['/insights', 'Insights'], ['/system', 'System'],
    ]);
    expect(paths(NAV_ENTRIES.filter((entry) => entry.foot))).toEqual(['/system']);
  });

  it('gives Trades, Insights and System their sections, the first one the default', () => {
    const sections = Object.fromEntries(
      NAV_ENTRIES.map((entry) => [entry.path, entry.sections?.map((s) => [s.path, s.label]) ?? null]),
    );
    expect(sections).toEqual({
      '/dashboard': null, '/watchlist': null, '/risk': null,
      '/trades': [['/trades', 'Book'], ['/trades/calendar', 'Calendar'], ['/trades/cancels', 'Cancels']],
      '/insights': [['/insights/analytics', 'Analytics'], ['/insights/research', 'Research'], ['/insights/reports', 'Reports']],
      '/system': [['/system', 'Health'], ['/system/versions', 'Versions']],
    });
  });

  it('keeps every section under its destination and leaves the /ui gallery off the rail', () => {
    for (const entry of NAV_ENTRIES) {
      for (const section of entry.sections ?? []) {
        expect(section.path === entry.path || section.path.startsWith(`${entry.path}/`), section.path).toBe(true);
      }
    }
    expect(paths(NAV_ENTRIES)).not.toContain('/ui');
  });

  it('labels every section with its route title, unless an override records why not', () => {
    for (const section of NAV_ENTRIES.flatMap((entry) => entry.sections ?? [])) {
      expect(titleAt(section.path), `no route for ${section.path}`).toBeDefined();
      expect(section.label, section.path).toBe(SECTION_LABEL_OVERRIDES[section.path] ?? titleAt(section.path));
    }
  });

  it("labels every destination with its first section's route title, unless an override records why not", () => {
    for (const entry of NAV_ENTRIES) {
      const first = entry.sections?.[0].path ?? entry.path;
      expect(titleAt(first), `no route for ${first}`).toBeDefined();
      expect(entry.label, entry.path).toBe(DESTINATION_LABEL_OVERRIDES[entry.path] ?? titleAt(first));
    }
  });

  it('records exactly its overrides, each one differing from the title it stands in for', () => {
    expect(SECTION_LABEL_OVERRIDES).toEqual({ '/trades': 'Book', '/system': 'Health' });
    expect(DESTINATION_LABEL_OVERRIDES).toEqual({ '/insights': 'Insights' });
    for (const [path, label] of Object.entries(SECTION_LABEL_OVERRIDES)) expect(titleAt(path)).not.toBe(label);
    expect(titleAt('/insights/analytics')).not.toBe(DESTINATION_LABEL_OVERRIDES['/insights']);
  });

  it('draws each destination with a known icon, no two sharing one', () => {
    const icons = NAV_ENTRIES.map((entry) => entry.icon);
    for (const icon of icons) expect(ICON_NAMES).toContain(icon);
    expect(new Set(icons).size).toBe(icons.length);
  });

  it('names the section words of the second-segment rule', () => {
    expect([...SECTION_WORDS].sort()).toEqual(['analytics', 'calendar', 'cancels', 'reports', 'research', 'versions']);
  });
});

describe('ALIASES (v202 §1)', () => {
  it('maps every moved page and the older renames onto their new home', () => {
    expect(ALIASES).toEqual({
      '/plans': '/trades', '/universe': '/watchlist', '/cockpit': '/dashboard',
      '/calendar': '/trades/calendar', '/cancels': '/trades/cancels',
      '/analytics': '/insights/analytics', '/research': '/insights/research', '/reports': '/insights/reports',
      '/versions': '/system/versions',
    });
  });

  it('agrees with the redirects app.routes.ts declares', () => {
    for (const [from, to] of Object.entries(ALIASES)) {
      if (from === '/plans') continue; // plans/:id is a real detail route of the trade book, not a redirect
      const route = routes.find((candidate) => `/${candidate.path}` === from);
      expect(route?.redirectTo, from).toBe(to.slice(1));
    }
  });

  it('lands every alias on a destination path or one of its sections', () => {
    const known = new Set(NAV_ENTRIES.flatMap((entry) => [entry.path, ...paths(entry.sections ?? [])]));
    for (const to of Object.values(ALIASES)) expect(known.has(to), to).toBe(true);
  });
});
```

(`paths` and `allEntries` are the file's existing helpers at the top. `NAV_GROUPS`, `PHONE_TABS`, `breadcrumbFor`, `detailCrumb` and `navEntryFor` stay imported for the describes that are left.)

- [ ] **Step 2: Run the spec to verify it fails**

Run: `npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/nav.spec.ts`
Expected: FAIL to compile, because `ALIASES`, `NAV_ENTRIES`, `SECTION_WORDS` and the two override maps are not exported.

- [ ] **Step 3: Add the model data to `shell/nav.ts`**

Replace the `NavEntry` interface (lines 3-9) with:

```ts
/** One tab inside a destination (v202 §1): `/trades/calendar`, 'Calendar'. */
export interface NavSection {
  path: string;
  label: string;
}

/** One destination on the rail. `label` is the title of its first section's
 *  route, and each section's `label` its own route's title, except where an
 *  override below records otherwise (nav.spec.ts holds both). The v195
 *  NAV_GROUPS entries use only path, label and icon. */
export interface NavEntry {
  path: string;
  label: string;
  icon: IconName;
  /** The destination's tabs, the first one its default; absent on a single page. */
  sections?: readonly NavSection[];
  /** Drawn at the rail's foot, apart from the work destinations. */
  foot?: boolean;
}
```

Replace the private `ALIASES` constant and its comment (lines 67-69) with the following. `GROUP_ALIASES` is the same two-key map under a new name, and `navEntryFor` reads it until V202-6b:

```ts
/** The v195 lookup's aliases: a plan is part of the trade book, and
 *  /universe is the watchlist's old name. Read only by the NAV_GROUPS
 *  navEntryFor below; V202-6b deletes both. */
const GROUP_ALIASES: Readonly<Record<string, string>> = { '/plans': '/trades', '/universe': '/watchlist' };

/** v202: the paths that belong to another destination. A plan is part of
 *  the trade book, /universe and /cockpit are older names, and the six
 *  pre-v202 pages moved under a destination (app.routes.ts redirects all
 *  but /plans). Resolving them here keeps a rail highlight from blinking
 *  during a redirect. */
export const ALIASES: Readonly<Record<string, string>> = {
  '/plans': '/trades',
  '/universe': '/watchlist',
  '/cockpit': '/dashboard',
  '/calendar': '/trades/calendar',
  '/cancels': '/trades/cancels',
  '/analytics': '/insights/analytics',
  '/research': '/insights/research',
  '/reports': '/insights/reports',
  '/versions': '/system/versions',
};
```

In `navEntryFor`, change `const path = ALIASES[first] ?? first;` to `const path = GROUP_ALIASES[first] ?? first;`.

Insert directly after the `NAV_GROUPS` array (after line 65):

```ts
/**
 * The nav model -- v202 §1. Six destinations, with sub-pages as their
 * sections. One model for the rail, the phone tab bar and More sheet, the
 * command palette, the section tabs and the breadcrumb. The /ui gallery is
 * a developer surface, reachable by URL and the palette, never the rail.
 */
export const NAV_ENTRIES: readonly NavEntry[] = [
  { path: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
  { path: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
  {
    path: '/trades', label: 'Trades', icon: 'trades',
    sections: [
      { path: '/trades', label: 'Book' },
      { path: '/trades/calendar', label: 'Calendar' },
      { path: '/trades/cancels', label: 'Cancels' },
    ],
  },
  { path: '/risk', label: 'Risk', icon: 'risk' },
  {
    path: '/insights', label: 'Insights', icon: 'analytics',
    sections: [
      { path: '/insights/analytics', label: 'Analytics' },
      { path: '/insights/research', label: 'Research' },
      { path: '/insights/reports', label: 'Reports' },
    ],
  },
  {
    path: '/system', label: 'System', icon: 'system', foot: true,
    sections: [
      { path: '/system', label: 'Health' },
      { path: '/system/versions', label: 'Versions' },
    ],
  },
];

/** A section label that is not its route's title. The route keeps the page
 *  name the browser tab shows ('Trades', 'System'); the tab names the view
 *  inside the destination ('Book', 'Health'). */
export const SECTION_LABEL_OVERRIDES: Readonly<Record<string, string>> = {
  '/trades': 'Book',
  '/system': 'Health',
};

/** A destination label that is not its first section's title. Insights has
 *  no page of its own: `/insights` redirects to its Analytics section. */
export const DESTINATION_LABEL_OVERRIDES: Readonly<Record<string, string>> = {
  '/insights': 'Insights',
};

/** Every second-segment word that names a section somewhere ('calendar').
 *  The rule itself is per destination (navEntryFor, V202-6b). */
export const SECTION_WORDS: ReadonlySet<string> = new Set(
  NAV_ENTRIES.flatMap((entry) => entry.sections ?? [])
    .map((section) => section.path.split('/')[2])
    .filter((word): word is string => word !== undefined),
);
```

- [ ] **Step 4: Run the specs to verify they pass**

Run each one. Expected: PASS, with `nav.spec.ts`'s other `NAV_GROUPS`, `navEntryFor` and `breadcrumbFor` tests unchanged and green.

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/nav.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/phone-tab-bar.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/breadcrumb.spec.ts
npm --prefix <wt>/frontend run lint
```

Layout: no rendered change in this task (the new exports have no reader yet).

- [ ] **Step 5: Commit**

```bash
git -C <wt> add frontend/src/app/shell/nav.ts frontend/src/app/shell/nav.spec.ts
git -C <wt> commit -m "feat(v202): nav model data: six destinations, sections, overrides, aliases

NAV_ENTRIES (Dashboard, Watchlist, Trades, Risk, Insights, System) with
Trades/Insights/System sections, the recorded label overrides
(Book, Health, Insights), SECTION_WORDS and the full ALIASES map, held by
a two-part label invariant against app.routes.ts. Nothing reads them yet:
URL resolution moves over in V202-6b.

Retired: V202-4's interim 'labels each entry with its route title'.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V202-6b: Nav resolution: second-segment rule, `destinationFor`, `isSectionUrl`, breadcrumb `Destination / Section`

**Model:** sonnet — pure lookup functions and one breadcrumb rule rewritten against case tables; the transitional aliases from V202-6 are deleted.

**Files:**
- Modify: `frontend/src/app/shell/nav.ts` (resolution functions, `@deprecated` on `NavGroup`/`NAV_GROUPS`), `frontend/src/app/shell/nav.spec.ts`
- Modify: `frontend/src/app/shell/breadcrumb.ts:1-32` (the import, `depth()` → `detailDepth()`, `crumbsFor`), `frontend/src/app/shell/breadcrumb.spec.ts`
- Modify (one line each, read the old shape): `frontend/src/app/shell/shell.spec.ts:612`, `frontend/src/app/shell/phone-tab-bar.spec.ts:51`

**Interfaces:**
- Consumes: V202-6's `NAV_ENTRIES`, `NavSection`, `ALIASES`.
- Produces (index "Nav model", final): `navEntryFor(url) -> { entry: NavEntry; section: NavSection | null } | null`, `destinationFor(url) -> string | null`, `isSectionUrl(url) -> boolean`, `breadcrumbFor(url, detail) -> string[]`, `PHONE_TABS` (taken from `NAV_ENTRIES`; V202-7 relabels Dashboard 'Home'), and `detailCrumb`, unchanged. `crumbsFor(url, detail, title)` keeps its signature. `NAV_GROUPS`/`NavGroup` stay exported, unchanged and `@deprecated`, because `shell.ts` (the rail), `more-sheet.ts` and `palette-items.ts` still read them until V202-7 and V203-1.
- The second-segment rule is per destination: the segment is a section only when it is one of *that* destination's section words. So `/trades/analytics` is a trade detail id, and `isSectionUrl('/trades/analytics')` is false.

The second half of the ledger's V202-6 (split to stay under 20 KB). Why the two one-line spec edits: `navEntryFor` no longer returns a `group`, so the breadcrumb on `/trades` reads `Trades / Book`, not `Review / Trades` (`shell.spec.ts:612`). `/calendar` now resolves to Trades through `ALIASES`, and Trades is a tab, so the "lights More" case needs a page the bar does not hold (`phone-tab-bar.spec.ts:51`). V202-5 touches none of these files.

The breadcrumb bug this fixes: today's `depth(url) > 1` rule reads every two-segment URL as a detail page, so `/trades/calendar` would show `Trades / Calendar / Calendar`, with the route title as a phantom detail.

**Retired in `nav.spec.ts`, explicitly:** the whole `describe('NAV_GROUPS (v195 §5.1)')` block. That is "is four groups in rail order", "puts each workspace in its group", "lists all eleven workspaces once" and "draws each entry with a known icon". V202-6's `NAV_ENTRIES` describe covers each one for the six destinations (the icon test is **moved** there). The `PHONE_TABS`, `navEntryFor` and `breadcrumbFor` describes are rewritten onto the new shape.

- [ ] **Step 1: Write the failing nav resolution spec**

In `frontend/src/app/shell/nav.spec.ts`:

1. Change the import from `./nav` to:

```ts
import {
  ALIASES, DESTINATION_LABEL_OVERRIDES, NAV_ENTRIES, PHONE_TABS, SECTION_LABEL_OVERRIDES, SECTION_WORDS,
  breadcrumbFor, destinationFor, detailCrumb, isSectionUrl, navEntryFor,
} from './nav';
```

2. Delete the `allEntries` constant and the whole `describe('NAV_GROUPS (v195 §5.1)', ...)` block.
3. Replace the `PHONE_TABS`, `navEntryFor` and `breadcrumbFor` describes (keep `detailCrumb` as it is) with:

```ts
describe('PHONE_TABS', () => {
  it('is Dashboard, Watchlist, Trades and Risk, each drawn as its destination', () => {
    expect(paths(PHONE_TABS)).toEqual(['/dashboard', '/watchlist', '/trades', '/risk']);
    for (const tab of PHONE_TABS) {
      expect(NAV_ENTRIES.find((entry) => entry.path === tab.path)?.icon).toBe(tab.icon);
    }
  });
});

describe('navEntryFor (v202 second-segment rule)', () => {
  const at = (url: string) => {
    const found = navEntryFor(url);
    return found ? [found.entry.label, found.section?.label ?? null] : null;
  };

  it.each([
    ['/dashboard', ['Dashboard', null]],
    ['/trades', ['Trades', 'Book']],
    ['/trades/812?tab=plan#why', ['Trades', 'Book']],
    ['/trades/calendar', ['Trades', 'Calendar']],
    ['/trades/calendar/2026-10-01', ['Trades', 'Calendar']],
    ['/trades/cancels?page=2', ['Trades', 'Cancels']],
    // Another destination's word is a detail id here, not a section.
    ['/trades/analytics', ['Trades', 'Book']],
    ['/plans/5', ['Trades', 'Book']],
    ['/watchlist/NVDA', ['Watchlist', null]],
    ['/universe', ['Watchlist', null]],
    ['/cockpit', ['Dashboard', null]],
    ['/calendar/2026-10-01', ['Trades', 'Calendar']],
    ['/cancels', ['Trades', 'Cancels']],
    ['/analytics?tab=tuning#x', ['Insights', 'Analytics']],
    ['/research', ['Insights', 'Research']],
    ['/reports', ['Insights', 'Reports']],
    ['/insights', ['Insights', 'Analytics']],
    ['/insights/reports?tab=gates', ['Insights', 'Reports']],
    ['/system?tab=providers', ['System', 'Health']],
    ['/system/versions', ['System', 'Versions']],
    ['/versions', ['System', 'Versions']],
  ])('places %s', (url, expected) => {
    expect(at(url)).toEqual(expected);
  });

  it.each(['/ui', '/', '', '/nowhere', '/nowhere/calendar'])('finds nothing for %j', (url) => {
    expect(navEntryFor(url)).toBeNull();
  });
});

describe('destinationFor', () => {
  it.each([
    ['/analytics?tab=tuning#x', '/insights'],
    ['/trades/812', '/trades'],
    ['/trades/calendar/2026-10-01', '/trades'],
    ['/system/versions', '/system'],
    ['/risk', '/risk'],
    ['/ui', null],
    ['', null],
  ])('is the destination path of %j', (url, expected) => {
    expect(destinationFor(url)).toBe(expected);
  });
});

describe('isSectionUrl', () => {
  it.each(['/trades/calendar', '/trades/calendar/2026-10-01', '/trades/cancels', '/insights/analytics',
    '/insights/research?page=2', '/system/versions', '/calendar', '/versions'])('is true for %s', (url) => {
    expect(isSectionUrl(url)).toBe(true);
  });

  it.each(['/trades', '/trades/812', '/trades/analytics', '/system', '/system?tab=logs', '/risk',
    '/watchlist/NVDA', '/plans/5', '/ui', ''])('is false for %j', (url) => {
    expect(isSectionUrl(url)).toBe(false);
  });
});

describe('breadcrumbFor (Destination / Section)', () => {
  it.each([
    ['/risk', null, ['Risk']],
    ['/risk', '', ['Risk']],
    ['/trades', null, ['Trades', 'Book']],
    ['/trades/calendar', null, ['Trades', 'Calendar']],
    ['/insights/analytics?tab=edge', null, ['Insights', 'Analytics']],
    ['/system', null, ['System', 'Health']],
    ['/system/versions', null, ['System', 'Versions']],
    ['/trades/812', 'NVDA #812', ['Trades', 'Book', 'NVDA #812']],
    ['/trades/calendar/2026-10-01', 'Calendar day', ['Trades', 'Calendar', 'Calendar day']],
    ['/watchlist/NVDA', 'NVDA', ['Watchlist', 'NVDA']],
  ])('reads %s (detail %j) as %j', (url, detail, expected) => {
    expect(breadcrumbFor(url, detail)).toEqual(expected);
  });

  it('is empty off the nav, so the caller can fall back to the route title', () => {
    expect(breadcrumbFor('/ui', 'anything')).toEqual([]);
  });
});
```

- [ ] **Step 2: Write the failing breadcrumb cases**

In `frontend/src/app/shell/breadcrumb.spec.ts`, rename the first describe to `'crumbsFor (v202: Destination / Section)'` and replace its tests with:

```ts
  it('is destination and section on a sectioned page, neither a link', () => {
    expect(crumbsFor('/trades', null, 'Trades')).toEqual([
      { label: 'Trades', link: null },
      { label: 'Book', link: null },
    ]);
  });

  it('is the destination alone on a single page', () => {
    expect(crumbsFor('/risk', null, 'Risk')).toEqual([{ label: 'Risk', link: null }]);
  });

  it.each([
    ['/trades/calendar', 'Calendar', ['Trades', 'Calendar']],
    ['/trades/cancels', 'Cancels', ['Trades', 'Cancels']],
    ['/insights/analytics', 'Analytics', ['Insights', 'Analytics']],
    ['/system/versions', 'Versions', ['System', 'Versions']],
    ['/system?tab=logs', 'System', ['System', 'Health']],
  ])('never reads the section of %s as a detail page', (url, title, expected) => {
    expect(crumbsFor(url, null, title)).toEqual(expected.map((label) => ({ label, link: null })));
  });

  it('links the crumb before a detail back to its list', () => {
    expect(crumbsFor('/trades/812', 'NVDA #812', 'Trade detail')).toEqual([
      { label: 'Trades', link: null },
      { label: 'Book', link: '/trades' },
      { label: 'NVDA #812', link: null },
    ]);
    expect(crumbsFor('/watchlist/NVDA', 'NVDA', 'Ticker detail')).toEqual([
      { label: 'Watchlist', link: '/watchlist' },
      { label: 'NVDA', link: null },
    ]);
  });

  it("stands the route title in for a detail that has not loaded yet, below a section's list", () => {
    expect(crumbsFor('/plans/5', null, 'Plan detail').map((crumb) => crumb.label))
      .toEqual(['Trades', 'Book', 'Plan detail']);
    expect(crumbsFor('/trades/calendar/2026-10-01', null, 'Calendar day')).toEqual([
      { label: 'Trades', link: null },
      { label: 'Calendar', link: '/trades/calendar' },
      { label: 'Calendar day', link: null },
    ]);
  });

  it('is the route title alone off the nav', () => {
    expect(crumbsFor('/ui', null, 'UI gallery')).toEqual([{ label: 'UI gallery', link: null }]);
  });

  it('is empty before any route has a title', () => {
    expect(crumbsFor('/', null, '')).toEqual([]);
  });
```

In the component describe:
- In `provideRouter([...])`, add `{ path: 'trades/calendar', component: Blank, title: 'Calendar' },` between the `trades` and `trades/:id` routes.
- Rename `'shows group and page on a workspace, the page marked current'` to `'shows destination and section, the section marked current'`. It expects `labels()` to be `['Trades', 'Book']` and the `[aria-current="page"]` text to be `'Book'`.
- In `'shows the detail segment once the detail route supplies it, ...'`, the two `labels()` expectations become `['Trades', 'Book', 'Trade detail']` and `['Trades', 'Book', 'NVDA #812']`, and `back.textContent` is `'Book'`. The href stays `/trades`.
- Add:

```ts
  it('shows a section page as destination and section, with no third crumb', async () => {
    await go('/trades/calendar');
    expect(labels()).toEqual(['Trades', 'Calendar']);
    expect(el().querySelector('a')).toBeNull();
  });
```

Then the two one-line edits:
- `shell/shell.spec.ts:612`: `expect(crumbs).toEqual(['Trades', 'Book']);`
- `shell/phone-tab-bar.spec.ts:51`: `const { el } = await mount('/insights/analytics');`

- [ ] **Step 3: Run the specs to verify they fail**

Run: `npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/nav.spec.ts`
Expected: FAIL to compile, because `destinationFor` and `isSectionUrl` are not exported.

Run: `npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/breadcrumb.spec.ts`
Expected: FAIL. The crumbs read `Review / Trades`, and `/trades/calendar` gets a third crumb.

- [ ] **Step 4: Rewrite the resolution in `shell/nav.ts`**

1. Above `export interface NavGroup`, add `/** @deprecated v202: the four-group model. Read NAV_ENTRIES; V203-1 deletes it. */`.
2. Replace the v195 doc comment above `export const NAV_GROUPS` with:

```ts
/**
 * @deprecated v202: the v195 four-group rail (Monitor, Review, Insights,
 * System), kept unchanged only while shell.ts (the rail), more-sheet.ts and
 * palette-items.ts still read it. V202-7 moves the sheet and the palette
 * onto NAV_ENTRIES; V203-1 rewrites the rail and deletes this block. Its
 * pre-v202 paths still work: app.routes.ts redirects each one.
 */
```

3. Delete `GROUP_ALIASES` and its comment (V202-6's transitional map).
4. Replace `firstSegment()` and `navEntryFor()` with:

```ts
/** '/calendar/2026-10-01?x#y' -> ['trades', 'calendar', '2026-10-01']; '' -> []. */
function segments(url: string): string[] {
  const parts = url.split(/[?#]/)[0].split('/').filter((part) => part !== '');
  if (parts.length === 0) return [];
  const alias = ALIASES[`/${parts[0]}`];
  return alias ? [...alias.split('/').filter((part) => part !== ''), ...parts.slice(1)] : parts;
}

function entryAt(first: string | undefined): NavEntry | undefined {
  return first === undefined ? undefined : NAV_ENTRIES.find((entry) => entry.path === `/${first}`);
}

/** The section a second segment names in this destination, if it names one. */
function namedSection(entry: NavEntry, word: string | undefined): NavSection | undefined {
  if (word === undefined) return undefined;
  return entry.sections?.find((section) => section.path === `${entry.path}/${word}`);
}

/**
 * The destination and section a URL belongs to -- v202 second-segment rule.
 * The second segment is a section exactly when it is one of this
 * destination's section words; anything else there (`/trades/812`) is a
 * detail id and keeps the first section. A single page has no section.
 * Null off the nav (the /ui gallery, the root, an unknown path).
 */
export function navEntryFor(url: string): { entry: NavEntry; section: NavSection | null } | null {
  const [first, second] = segments(url);
  const entry = entryAt(first);
  if (!entry) return null;
  return { entry, section: namedSection(entry, second) ?? entry.sections?.[0] ?? null };
}

/** The destination path a URL belongs to ('/insights'), or null off the nav. */
export function destinationFor(url: string): string | null {
  return navEntryFor(url)?.entry.path ?? null;
}

/** True when the URL's second segment (after ALIASES) names one of its
 *  destination's sections: '/trades/calendar', not '/trades' or '/trades/812'. */
export function isSectionUrl(url: string): boolean {
  const [first, second] = segments(url);
  const entry = entryAt(first);
  return entry !== undefined && namedSection(entry, second) !== undefined;
}
```

5. `PHONE_TABS` keeps its code (`['/dashboard', '/watchlist', '/trades', '/risk'].map((path) => navEntryFor(path)!.entry)`), which now reads `NAV_ENTRIES`. It must sit **below** the new `navEntryFor` and below `NAV_ENTRIES`; move it there if it is not.
6. Replace `breadcrumbFor` with:

```ts
/** `Destination / Section` ('Trades / Calendar'), the destination alone on a
 *  single page ('Risk'), plus the detail segment a detail route supplies
 *  ('Trades / Book / NVDA #812'). Empty off the nav. */
export function breadcrumbFor(url: string, detail: string | null): string[] {
  const found = navEntryFor(url);
  if (!found) return [];
  const crumbs = found.section ? [found.entry.label, found.section.label] : [found.entry.label];
  return detail ? [...crumbs, detail] : crumbs;
}
```

- [ ] **Step 5: Make `crumbsFor` section-aware**

In `frontend/src/app/shell/breadcrumb.ts`, change the import to `import { breadcrumbFor, isSectionUrl, navEntryFor } from './nav';`. Then replace `depth()` and `crumbsFor()` (lines 15-32) with:

```ts
/** Path segments past the page itself: 0 on '/trades', '/trades/calendar'
 *  and '/system'; 1 on '/trades/812' and '/trades/calendar/2026-10-01'.
 *  Reads the router's URL, which is past every redirect by NavigationEnd. */
function detailDepth(url: string): number {
  const depth = url.split(/[?#]/)[0].split('/').filter((part) => part !== '').length;
  return depth - (isSectionUrl(url) ? 2 : 1);
}

/**
 * The crumbs for a URL -- v202 §1. `Destination / Section` (the destination
 * alone on a single page), plus the detail segment on a detail route: the
 * one the route supplied, or its title while the record loads ('Trade
 * detail'). The crumb before a detail links back to its list. Off the nav
 * (the /ui gallery) the route title alone. Pure, so the spec can hold every
 * case without a router.
 */
export function crumbsFor(url: string, detail: string | null, title: string): Crumb[] {
  const shownDetail = detail || (detailDepth(url) > 0 && title ? title : null);
  const labels = breadcrumbFor(url, shownDetail);
  if (labels.length === 0) return title ? [{ label: title, link: null }] : [];
  const found = navEntryFor(url)!;
  const listPath = found.section?.path ?? found.entry.path;
  const linkAt = shownDetail ? labels.length - 2 : -1;
  return labels.map((label, index) => ({ label, link: index === linkAt ? listPath : null }));
}
```

- [ ] **Step 6: Run the specs to verify they pass**

Run each one. Expected: PASS.

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/nav.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/breadcrumb.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/phone-tab-bar.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/more-sheet.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/palette/palette-items.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend run lint
```

`more-sheet.spec.ts`, `palette-items.spec.ts` and the rail tests in `shell.spec.ts` still read the deprecated `NAV_GROUPS`, so they stay green unchanged. If lint flags the `@deprecated` uses (`@typescript-eslint/no-deprecated` or similar) in shell.ts, more-sheet.ts or palette-items.ts, add those file-level entries to `frontend/eslint-suppressions.json` and say so in the report. V202-7 and V203-1 remove the uses, and the suppressions go with them.

Complexity: every new function in `nav.ts` has at most 3 branches, `crumbsFor` has 4 and `detailDepth` has 1.

Layout: the breadcrumb's words change (`Trades / Book`, `Risk`, `Trades / Calendar`). It already ellipsises and shows only the current crumb under 640 px (`breadcrumb.ts` styles, unchanged). Build and serve the SPA locally with the `.env` admin credentials (loaded inside the script, never printed). Then run `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440`, and report that there is no horizontal scroll at the three widths.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add frontend/src/app/shell/nav.ts frontend/src/app/shell/nav.spec.ts \
  frontend/src/app/shell/breadcrumb.ts frontend/src/app/shell/breadcrumb.spec.ts \
  frontend/src/app/shell/shell.spec.ts frontend/src/app/shell/phone-tab-bar.spec.ts
git -C <wt> commit -m "feat(v202): resolve URLs by destination and section; breadcrumb Destination / Section

navEntryFor reads NAV_ENTRIES with a per-destination second-segment
rule: /trades/calendar is a section, /trades/812 a detail of Book. Old
paths resolve through ALIASES. destinationFor and isSectionUrl join it.
The breadcrumb reads Destination / Section, and a section page no longer
gets its title as a phantom detail crumb. NAV_GROUPS stays, deprecated,
until the rail is rewritten.

Retired nav.spec: the NAV_GROUPS describe (four groups, membership,
eleven workspaces, icons), covered by V202-6's NAV_ENTRIES tests.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V202-7: More sheet, palette and phone tab bar on `NAV_ENTRIES`

**Model:** sonnet — three consumers move from the deprecated groups onto the new model; each function is small and its output is pinned in full.

**Files:**
- Modify: `frontend/src/app/shell/more-sheet.ts` (`morePageGroups`, `MoreGroup`, the template's group loop), `frontend/src/app/shell/more-sheet.spec.ts`
- Modify: `frontend/src/app/shell/palette/palette-items.ts` (`pageItems`, its import), `frontend/src/app/shell/palette/palette-items.spec.ts`
- Modify: `frontend/src/app/shell/phone-tab-bar.ts` (doc comment only), `frontend/src/app/shell/phone-tab-bar.spec.ts`
- Modify: `frontend/src/app/shell/nav.ts` (`PHONE_TABS` labels only)
- Modify (expectations only, beyond the ledger row): `frontend/src/app/shell/palette/command-palette.spec.ts:123`, `frontend/src/app/shell/shell.spec.ts:733,801`

**Interfaces:**
- Consumes: V202-6/6b's `NAV_ENTRIES`, `NavEntry` (`sections`), `PHONE_TABS` and `navEntryFor`.
- Produces (index ledger, final): `MoreGroup = { id: string; label: string; links: { label: string; path: string }[] }`, `morePageGroups(entries: readonly NavEntry[] = NAV_ENTRIES, tabs: readonly NavEntry[] = PHONE_TABS) -> MoreGroup[]`, `pageItems(entries: readonly NavEntry[] = NAV_ENTRIES) -> PaletteItem[]`, and `PHONE_TABS` with the Dashboard tab labelled `'Home'` (paths and icons unchanged). After this task, `shell.ts` (the rail) is the last reader of `NAV_GROUPS`. V203-1 deletes it.

Decisions this task fixes:
- **More sheet (spec §3):** one group per destination the tab bar does not hold, with the destination's sections as links. Today that is Insights (Analytics, Research, Reports) and System (Health, Versions). Trades' Calendar and Cancels are not listed: Trades is a tab, and its section tabs (V202-8) reach them. Section links carry no glyph, because the model gives sections no icon (no new styling). A destination with no sections lists itself as its one link. The spec also lists "the profile actions" in the More sheet. The phone top bar already holds `sb-profile-menu` (sign-out, zoom, motion, density), and this task does not duplicate it (see the part's OPEN note).
- **Palette pages:** one item per page in rail order. That is each section of a destination, labelled with the section's name and with the destination as its `sub` (`Calendar · Trades`, `Book · Trades`), or the destination itself on a single page, with no `sub` (the old group names Monitor and Review are gone). Then come the `TAB_PAGES`. It is still eleven pages, so the empty query shows 11 pages and 2 trades as before.
- **Phone tab bar:** spec §3 names the first tab "Home". Only `PHONE_TABS` relabels it, so the rail, breadcrumb and palette keep "Dashboard".

**Retired, explicitly:** in `more-sheet.spec.ts`, "drops a group whose every page is already a tab" (it tested the Monitor group id) and the `a.page sb-icon` glyph loop. They are replaced by "lists no destination the tab bar holds" and "draws no glyph in a section link". In `palette-items.spec.ts`, the `sub: 'Monitor'` expectation is replaced by `Risk` with no `sub`.

- [ ] **Step 1: Write the failing specs**

`shell/more-sheet.spec.ts`: change `import { NAV_GROUPS } from './nav';` to `import { NAV_ENTRIES } from './nav';`, then replace the `morePageGroups` describe with:

```ts
describe('morePageGroups (v202 §3)', () => {
  const shape = (groups: ReturnType<typeof morePageGroups>) =>
    groups.map((group) => [group.id, group.label, group.links.map((link) => [link.label, link.path])]);

  it('lists the destinations the tab bar does not hold, each with its sections, in rail order', () => {
    expect(shape(morePageGroups())).toEqual([
      ['more-insights', 'Insights', [['Analytics', '/insights/analytics'], ['Research', '/insights/research'], ['Reports', '/insights/reports']]],
      ['more-system', 'System', [['Health', '/system'], ['Versions', '/system/versions']]],
    ]);
  });

  it('lists no destination the tab bar holds', () => {
    const ids = morePageGroups().map((group) => group.id);
    for (const id of ['more-dashboard', 'more-watchlist', 'more-trades', 'more-risk']) expect(ids).not.toContain(id);
  });

  it('keeps every destination when no tab is given, a single page linking to itself', () => {
    const groups = morePageGroups(NAV_ENTRIES, []);
    expect(groups).toHaveLength(6);
    expect(shape(groups)[0]).toEqual(['more-dashboard', 'Dashboard', [['Dashboard', '/dashboard']]]);
    expect(shape(groups)[2]).toEqual(['more-trades', 'Trades',
      [['Book', '/trades'], ['Calendar', '/trades/calendar'], ['Cancels', '/trades/cancels']]]);
  });

  it('is empty for an empty model', () => {
    expect(morePageGroups([], [])).toEqual([]);
  });
});
```

In the `MoreSheet` describe, replace the test `'lists the remaining pages under their group names, linking to each'` with:

```ts
  it('lists the remaining destinations under their names, linking to each section', () => {
    open();
    expect([...el.querySelectorAll('.group-label')].map((n) => n.textContent!.trim()))
      .toEqual(['Insights', 'System']);
    expect([...el.querySelectorAll('a.page')].map((a) => [a.textContent!.trim(), a.getAttribute('href')])).toEqual([
      ['Analytics', '/insights/analytics'], ['Research', '/insights/research'], ['Reports', '/insights/reports'],
      ['Health', '/system'], ['Versions', '/system/versions'],
    ]);
    for (const list of el.querySelectorAll('ul.pages')) {
      expect(el.querySelector(`#${list.getAttribute('aria-labelledby')}`)).not.toBeNull();
    }
  });

  it('draws no glyph in a section link', () => {
    open();
    expect(el.querySelectorAll('a.page sb-icon')).toHaveLength(0);
  });
```

`shell/palette/palette-items.spec.ts`: change `import { NAV_GROUPS } from '../nav';` to nothing (delete the line), and replace the `RAIL` constant with:

```ts
/** The nav model's pages in rail order: each section, or a single page. */
const RAIL = ['Dashboard', 'Watchlist', 'Book', 'Calendar', 'Cancels', 'Risk',
  'Analytics', 'Research', 'Reports', 'Health', 'Versions'];
```

In the first test, `'lists every rail entry as a page, ...'`, rename it to `'lists every page of the nav model, in rail order, then the workspace tabs'` and replace its last line with:

```ts
    expect(pages.find((item) => item.label === 'Risk')).toEqual({ key: 'page:/risk', group: 'pages', label: 'Risk', route: '/risk' });
    expect(pages.find((item) => item.label === 'Calendar')).toMatchObject({ route: '/trades/calendar', sub: 'Trades' });
    expect(pages.find((item) => item.label === 'Book')).toMatchObject({ route: '/trades', sub: 'Trades' });
```

Add after it:

```ts
  it('routes every page to a path of the nav model, never a pre-v202 one', () => {
    expect(pageItems().filter((item) => !item.queryParams).map((item) => item.route)).toEqual([
      '/dashboard', '/watchlist', '/trades', '/trades/calendar', '/trades/cancels', '/risk',
      '/insights/analytics', '/insights/research', '/insights/reports', '/system', '/system/versions',
    ]);
  });

  it('is only the tabs for an empty model', () => {
    expect(pageItems([])).toEqual([...TAB_PAGES]);
  });
```

`shell/palette/command-palette.spec.ts:123`: `expect(shown.slice(0, 3)).toEqual(['Dashboard', 'Watchlist', 'Book']);` (the length, 13, is unchanged).

`shell/phone-tab-bar.spec.ts`: the first test's expected labels become `['Home', 'Watchlist', 'Trades', 'Risk', 'More']`, and its name `'holds Home, Watchlist, Trades, Risk and More, in that order'`. Add after `'marks the current tab, ...'`:

```ts
  it('lights Trades on each of its sections, old paths included', async () => {
    for (const url of ['/trades/calendar', '/trades/cancels', '/trades/calendar/2026-10-01', '/calendar/2026-10-01']) {
      expect(current((await mount(url)).el), url).toEqual(['Trades']);
    }
  });

  it('lights More on a System section', async () => {
    const { el } = await mount('/system/versions');
    expect(current(el)).toEqual([]);
    expect(el.querySelector('button.tab.more')!.classList).toContain('active');
  });
```

`shell/shell.spec.ts`, phone describe: at :733 the route list becomes `shellProviders([{ path: 'insights/research', component: Blank }])`, and at :801 the selector becomes `'sb-more-sheet a.page[href="/insights/research"]'`.

- [ ] **Step 2: Run the specs to verify they fail**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/more-sheet.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/palette/palette-items.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/phone-tab-bar.spec.ts
```

Expected: FAIL. `more-sheet.spec` fails to compile (`morePageGroups` takes `NavGroup[]`). `palette-items.spec` shows the old eleven group-labelled pages. `phone-tab-bar.spec` reads `Dashboard`, not `Home`.

- [ ] **Step 3: Move the More sheet onto `NAV_ENTRIES`**

In `shell/more-sheet.ts`, change the nav import to `import { NAV_ENTRIES, NavEntry, PHONE_TABS } from './nav';` and replace `morePageGroups` (lines 9-19) with:

```ts
/** One group of the More sheet: a destination, and the pages it links to. */
export interface MoreGroup {
  id: string;
  label: string;
  links: { label: string; path: string }[];
}

/**
 * The destinations the phone's tab bar does not hold, in rail order (v202
 * §3), each with its sections as links; a single page links to itself.
 * Today: Insights (Analytics, Research, Reports) and System (Health,
 * Versions). Trades' sections are reached from its section tabs.
 */
export function morePageGroups(
  entries: readonly NavEntry[] = NAV_ENTRIES,
  tabs: readonly NavEntry[] = PHONE_TABS,
): MoreGroup[] {
  const onBar = new Set(tabs.map((tab) => tab.path));
  return entries
    .filter((entry) => !onBar.has(entry.path))
    .map((entry) => ({
      id: `more-${entry.path.slice(1)}`,
      label: entry.label,
      links: (entry.sections ?? [entry]).map(({ label, path }) => ({ label, path })),
    }));
}
```

In the template, replace the `@for (group of groups; ...)` block with:

```html
        @for (group of groups; track group.id) {
          <p class="group-label" [id]="group.id">{{ group.label }}</p>
          <ul class="pages" [attr.aria-labelledby]="group.id">
            @for (link of group.links; track link.path) {
              <li>
                <a class="page" [routerLink]="link.path" (click)="closed.emit()">{{ link.label }}</a>
              </li>
            }
          </ul>
        }
```

In the component's doc comment, change "every page the tab bar does not hold, grouped as on the rail" to "every destination the tab bar does not hold, with its sections (v202 §3)". `Icon` stays imported: the search button still draws `sb-icon name="search"`. The `.page` and `.glyph` styles are unchanged.

- [ ] **Step 4: Move the palette's pages onto `NAV_ENTRIES`**

In `shell/palette/palette-items.ts`, change the nav import to `import { NAV_ENTRIES, NavEntry, detailCrumb } from '../nav';` and replace `pageItems` (lines 84-96) with:

```ts
function pageItem(label: string, route: string, sub?: string): PaletteItem {
  return { key: `page:${route}`, group: 'pages', label, ...(sub ? { sub } : {}), route };
}

/** Every page of the nav model, in rail order: each section of a
 *  destination (its `sub` the destination, 'Calendar · Trades') or the
 *  destination itself on a single page; then the workspace tabs. */
export function pageItems(entries: readonly NavEntry[] = NAV_ENTRIES): PaletteItem[] {
  const pages = entries.flatMap((entry) =>
    entry.sections
      ? entry.sections.map((section) => pageItem(section.label, section.path, entry.label))
      : [pageItem(entry.label, entry.path)],
  );
  return [...pages, ...TAB_PAGES];
}
```

- [ ] **Step 5: Label the phone's first tab "Home"**

In `shell/nav.ts`, replace `PHONE_TABS` and its comment with:

```ts
/** The phone tab bar's own label where it differs from the rail's: the
 *  landing page reads as Home on a 64 px tab (v202 §3). */
const PHONE_TAB_LABELS: Readonly<Record<string, string>> = { '/dashboard': 'Home' };

/** The phone bottom bar's four page tabs, in order; PhoneTabBar adds More
 *  as the fifth. Paths and icons are the destinations' own. */
export const PHONE_TABS: readonly NavEntry[] = ['/dashboard', '/watchlist', '/trades', '/risk']
  .map((path) => navEntryFor(path)!.entry)
  .map((entry) => ({ ...entry, label: PHONE_TAB_LABELS[entry.path] ?? entry.label }));
```

In `shell/phone-tab-bar.ts`'s doc comment, change "Dashboard · Watchlist · Trades · Risk, then More." to "Home (the Dashboard) · Watchlist · Trades · Risk, then More (v202 §3)." The code is unchanged: `activePath` already resolves through `navEntryFor`, so every Trades section lights Trades.

- [ ] **Step 6: Run the specs to verify they pass**

Run each one. Expected: PASS.

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/more-sheet.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/palette/palette-items.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/palette/command-palette.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/phone-tab-bar.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/nav.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/routing/old-paths.spec.ts
npm --prefix <wt>/frontend run lint
```

If V202-6b added `eslint-suppressions.json` entries for `NAV_GROUPS` in `more-sheet.ts` or `palette-items.ts`, delete those two now (lint stays clean). Keep any entry for `shell.ts` until V203-1.

Complexity: `morePageGroups`, `pageItems` and `pageItem` each have at most 2 branches.

Layout, at all three widths: build and serve the SPA locally with the `.env` admin credentials (loaded inside the script, never printed). Run `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440`. At 390 px, open the More sheet with Playwright and check that its five links are at least 44 px tall (`.page` is `min-height: var(--control-h)`, 44 px on touch) and that the sheet scrolls rather than overflows. Report no horizontal scroll and the tap-target sizes.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add frontend/src/app/shell/more-sheet.ts frontend/src/app/shell/more-sheet.spec.ts \
  frontend/src/app/shell/palette/palette-items.ts frontend/src/app/shell/palette/palette-items.spec.ts \
  frontend/src/app/shell/palette/command-palette.spec.ts frontend/src/app/shell/phone-tab-bar.ts \
  frontend/src/app/shell/phone-tab-bar.spec.ts frontend/src/app/shell/nav.ts frontend/src/app/shell/shell.spec.ts
git -C <wt> commit -m "feat(v202): More sheet, palette and phone tab bar read the six destinations

The More sheet lists Insights and System with their sections; the
palette offers every section as a page (Calendar · Trades), never a
pre-v202 path; the phone's first tab reads Home. Only the rail still
reads the deprecated NAV_GROUPS.

Retired: the Monitor-group and a.page glyph checks in more-sheet.spec,
the 'Monitor' sub in palette-items.spec.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V202-8: `sb-section-tabs` segmented control, drawn by the shell

**Model:** sonnet — one presentational component built from existing tokens, plus a router-derived signal in the shell; both are pinned by DOM tests.

**Files:**
- Create: `frontend/src/app/shell/section-tabs.ts`, `frontend/src/app/shell/section-tabs.spec.ts`
- Modify: `frontend/src/app/shell/shell.ts` (imports, `navHere`), `frontend/src/app/shell/shell.html:133-134` (the workspace content), `frontend/src/app/shell/shell.spec.ts` (a new describe)
- `frontend/src/app/shell/shell.css` needs no rule: the component styles itself, and the workspace padding already spaces it. Leave the file untouched and say so in the report.

**Interfaces:**
- Consumes: V202-6b's `navEntryFor(url) -> { entry: NavEntry; section: NavSection | null } | null`, `NavEntry.sections`, `NavSection`.
- Produces (index ledger, final): `SectionTabs` (`sb-section-tabs`) with inputs `entry: NavEntry | null` and `active: NavSection | null`. It renders nothing unless `entry` has sections. `Shell.navHere: Signal<{ entry: NavEntry; section: NavSection | null } | null>` is a `protected readonly` computed from the router URL, updated on `NavigationEnd`. V203-1's rail markup reads it, and V203-3's `DockState` derives its own.

Design (spec §1 "Section tabs"): the tabs sit at the top of the workspace, above the page's `sb-page` header. The shell draws them from the nav model, never a workspace. Each segment is a `routerLink`, with `aria-current="page"` on the active one. The look is `sb-segmented`'s track and segment, copied with the same tokens (`--border-strong`, `--accent-soft`, `--control-h`, `--hit-min`). No new colour, size or radius. On a touch device `--control-h` and `--hit-min` are 44 px (`styles/tokens.css:381-384`), so every segment is a 44 px target. On a narrow phone the track scrolls sideways inside itself (`overflow-x: auto`), never the page. They are links in the normal tab order, not a roving-tabindex toggle, because each one is a page.

- [ ] **Step 1: Write the failing component spec**

Create `frontend/src/app/shell/section-tabs.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { allSources } from '../ui/testing/all-sources';
import { NAV_ENTRIES, NavEntry, NavSection } from './nav';
import { SectionTabs } from './section-tabs';

@Component({ template: '' })
class Blank {}

const SOURCE = readFileSync(join(process.cwd(), 'src/app/shell/section-tabs.ts'), 'utf8');
const entry = (path: string) => NAV_ENTRIES.find((candidate) => candidate.path === path)!;
const section = (path: string) => NAV_ENTRIES.flatMap((e) => e.sections ?? []).find((s) => s.path === path)!;

describe('SectionTabs (sb-section-tabs, v202 §1)', () => {
  let fixture: ComponentFixture<SectionTabs>;
  const el = () => fixture.nativeElement as HTMLElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([{ path: '**', component: Blank }])],
    });
    fixture = TestBed.createComponent(SectionTabs);
  });

  function render(navEntry: NavEntry | null, active: NavSection | null): void {
    fixture.componentRef.setInput('entry', navEntry);
    fixture.componentRef.setInput('active', active);
    fixture.detectChanges();
  }

  const tabs = () => [...el().querySelectorAll('a.segment')].map((a) => [a.textContent!.trim(), a.getAttribute('href')]);

  it('renders nothing off the nav and on a single page', () => {
    render(null, null);
    expect(el().querySelector('nav')).toBeNull();
    render(entry('/risk'), null);
    expect(el().querySelector('nav')).toBeNull();
  });

  it("draws a destination's sections as links, in order, in a labelled nav", () => {
    render(entry('/trades'), section('/trades/calendar'));
    expect(el().querySelector('nav')!.getAttribute('aria-label')).toBe('Trades sections');
    expect(tabs()).toEqual([['Book', '/trades'], ['Calendar', '/trades/calendar'], ['Cancels', '/trades/cancels']]);
  });

  it('marks only the active section as the current page', () => {
    render(entry('/insights'), section('/insights/research'));
    const current = [...el().querySelectorAll('a[aria-current="page"]')];
    expect(current.map((a) => a.textContent!.trim())).toEqual(['Research']);
    expect(current[0].classList).toContain('current');
    expect(el().querySelectorAll('a.segment.current')).toHaveLength(1);
  });

  it('marks nothing current when no section is active', () => {
    render(entry('/system'), null);
    expect(tabs()).toEqual([['Health', '/system'], ['Versions', '/system/versions']]);
    expect(el().querySelector('[aria-current]')).toBeNull();
  });

  it("grows each segment to the hit size and reuses sb-segmented's tokens, no literal colour", () => {
    expect(SOURCE).toMatch(/\.segment \{[^}]*min-height: var\(--control-h\)/);
    expect(SOURCE).toMatch(/\.segment \{[^}]*min-width: var\(--hit-min\)/);
    expect(SOURCE).toMatch(/\.current \{[^}]*background: var\(--accent-soft\)/);
    expect(SOURCE).toMatch(/\.track \{[^}]*overflow-x: auto/);
    expect(SOURCE).not.toMatch(/#[0-9a-f]{3,8}\b|rgba?\(/i);
  });

  it('is drawn by the shell alone: no workspace renders it', () => {
    const drawers = allSources()
      .filter((file) => file.name.startsWith('app/workspaces/') && file.source.includes('sb-section-tabs'))
      .map((file) => file.name);
    expect(drawers).toEqual([]);
  });
});
```

- [ ] **Step 2: Write the failing shell spec**

Append to `frontend/src/app/shell/shell.spec.ts` (`shellProviders`, `Blank` and `Router` are already in the file):

```ts
describe('section tabs in the shell (v202 §1)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: shellProviders([
        { path: 'trades', component: Blank },
        { path: 'trades/calendar', component: Blank },
        { path: 'trades/:id', component: Blank },
        { path: 'risk', component: Blank },
      ]),
    });
  });

  async function go(fixture: ComponentFixture<Shell>, url: string): Promise<void> {
    await TestBed.inject(Router).navigateByUrl(url);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function at(url: string): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await go(fixture, url);
    return fixture.nativeElement as HTMLElement;
  }

  const current = (el: HTMLElement) =>
    [...el.querySelectorAll('sb-section-tabs a[aria-current="page"]')].map((a) => a.textContent!.trim());

  it('draws the tabs at the top of the workspace, before the routed page', async () => {
    const el = await at('/trades/calendar');
    const content = el.querySelector('main.workspace > .workspace-content')!;
    expect(content.firstElementChild!.tagName.toLowerCase()).toBe('sb-section-tabs');
    expect([...content.querySelectorAll('sb-section-tabs a')].map((a) => a.textContent!.trim()))
      .toEqual(['Book', 'Calendar', 'Cancels']);
    expect(current(el)).toEqual(['Calendar']);
  });

  it("keeps the destination's first section active on a detail page", async () => {
    expect(current(await at('/trades/812'))).toEqual(['Book']);
  });

  it('draws no tabs on a single page', async () => {
    expect((await at('/risk')).querySelectorAll('sb-section-tabs a')).toHaveLength(0);
  });

  it('moves the current tab when the URL moves to another section, and drops the tabs off it', async () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    await go(fixture, '/trades');
    expect(current(el)).toEqual(['Book']);
    await go(fixture, '/trades/calendar');
    expect(current(el)).toEqual(['Calendar']);
    await go(fixture, '/risk');
    expect(el.querySelectorAll('sb-section-tabs a')).toHaveLength(0);
  });
});
```

If `ComponentFixture` is not yet imported in `shell.spec.ts`, add it to the `@angular/core/testing` import.

- [ ] **Step 3: Run the specs to verify they fail**

Run: `npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/section-tabs.spec.ts`
Expected: FAIL to compile (`./section-tabs` does not exist).

Run: `npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts`
Expected: FAIL in the new describe only (no `sb-section-tabs` in the shell).

- [ ] **Step 4: Create `shell/section-tabs.ts`**

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { NavEntry, NavSection } from './nav';

/**
 * A destination's sections as a segmented row of links -- v202 §1.
 *
 * The shell draws it at the top of the workspace, above the page's sb-page
 * header, from the nav model; a workspace never does (section-tabs.spec
 * holds that). Each segment is a page, so they are plain links in the tab
 * order with `aria-current="page"` on the active one, not sb-segmented's
 * roving toggle. The look is sb-segmented's, with the same tokens: Phase 1
 * adds no styling of its own. Renders nothing on a single page.
 */
@Component({
  selector: 'sb-section-tabs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    @if (sections().length > 0) {
      <nav class="track" [attr.aria-label]="label()">
        @for (section of sections(); track section.path) {
          <a
            class="segment"
            [routerLink]="section.path"
            [class.current]="section.path === active()?.path"
            [attr.aria-current]="section.path === active()?.path ? 'page' : null"
          >{{ section.label }}</a>
        }
      </nav>
    }
  `,
  styles: `
    :host { display: block; min-width: 0; max-width: 100%; }
    .track { display: inline-flex; max-width: 100%; margin: 0 0 var(--space-14); overflow-x: auto; scrollbar-width: thin; border: 1px solid var(--border-strong); border-radius: var(--control-radius); }
    .segment { flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; min-height: var(--control-h); min-width: var(--hit-min); padding: 0 var(--space-10); border-left: 1px solid var(--border); color: var(--text-secondary); font-size: var(--text-table); font-weight: 500; white-space: nowrap; text-decoration: none; transition: color var(--transition), background var(--transition); }
    .segment:first-child { border-left: 0; }
    .segment:not(.current):hover { color: var(--text); background: var(--surface-raised); }
    .segment:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .current { background: var(--accent-soft); color: var(--text); }
  `,
})
export class SectionTabs {
  readonly entry = input<NavEntry | null>(null);
  readonly active = input<NavSection | null>(null);

  protected readonly sections = computed(() => this.entry()?.sections ?? []);
  protected readonly label = computed(() => `${this.entry()?.label ?? ''} sections`);
}
```

- [ ] **Step 5: Draw it from the shell**

In `shell/shell.ts`:
- Change the router import to `import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';`, and add `import { toSignal } from '@angular/core/rxjs-interop';`, `import { filter, map } from 'rxjs';`, `import { SectionTabs } from './section-tabs';`. Change `import { NAV_GROUPS } from './nav';` to `import { NAV_GROUPS, navEntryFor } from './nav';` (`NAV_GROUPS` stays until V203-1).
- Add `SectionTabs` to the component's `imports` array.
- Below `protected readonly navGroups = NAV_GROUPS;`, add:

```ts
  private readonly router = inject(Router);
  private readonly url = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map(() => this.router.url),
    ),
    { initialValue: this.router.url },
  );

  /** The destination and section the current URL belongs to (v202 §1):
   *  the section tabs read it, and the rail (V203-1) lights its entry. */
  protected readonly navHere = computed(() => navEntryFor(this.url()));
```

If `shell.ts` already declares a `router` field by the time this lands, reuse it instead of adding a second one.

In `shell/shell.html`, replace line 134 (`<div class="workspace-content" ...><router-outlet /></div>`) with:

```html
      <!-- v202 §1: the destination's section tabs, drawn here from the nav
           model and never by a workspace, above the page's sb-page header. -->
      <div class="workspace-content" [attr.inert]="routeLoading.visible() ? '' : null">
        <sb-section-tabs [entry]="navHere()?.entry ?? null" [active]="navHere()?.section ?? null" />
        <router-outlet />
      </div>
```

`route-focus.ts` still finds the page's `<h1>` inside `.workspace` (the tabs hold none). The tape-strip test's `.main` children (`header`, `div`, `main`) are unchanged.

- [ ] **Step 6: Run the specs to verify they pass**

Run each one. Expected: PASS.

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/section-tabs.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/ui/hit-area.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include "src/app/workspaces/*.spec.ts"
npm --prefix <wt>/frontend run lint
```

(The `workspaces/*.spec.ts` glob covers `workspace-consistency.spec.ts`, which scans every workspace source; the tabs live in `shell/`, outside its rules.)

Complexity: `SectionTabs` has no branching method, and `navHere` is one call.

Layout, at all three widths: build and serve the SPA locally with the `.env` admin credentials (loaded inside the script, never printed). Run `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440` and, with Playwright, open `/trades`, `/trades/calendar`, `/insights/research` and `/system/versions` at each width. Report: no horizontal page scroll (the track scrolls inside itself if it must), each segment at least 44 px tall and wide at 390 and 768 px, the tabs above the page header with no overlap, and no tabs on `/dashboard` or `/risk`.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add frontend/src/app/shell/section-tabs.ts frontend/src/app/shell/section-tabs.spec.ts \
  frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.spec.ts
git -C <wt> commit -m "feat(v202): sb-section-tabs, drawn by the shell above each sectioned page

Trades (Book, Calendar, Cancels), Insights (Analytics, Research,
Reports) and System (Health, Versions) get a segmented row of links at
the top of the workspace, aria-current on the active section, built from
sb-segmented's tokens. The shell derives navHere from the router URL;
no workspace draws the tabs.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
