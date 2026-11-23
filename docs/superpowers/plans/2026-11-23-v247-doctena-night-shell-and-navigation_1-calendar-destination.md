# v247 — Doctena night, plan 3 of 5: Shell and navigation — Part 1: Calendar destination

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V247-2" -A 400 <this file>`).

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) §6 (navigation model), §11 (Nav lines).
**Index:** [2026-11-23-v247-doctena-night-shell-and-navigation_0-index.md](2026-11-23-v247-doctena-night-shell-and-navigation_0-index.md) — Goal, Global Constraints, Decisions, Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks: V247-1 (route flip), V247-2 (nav model and its pure specs), V247-2b (component specs that read it), V247-3 (hard-coded links and the old-paths gate), V247-4 (`spa.py`, probe, smoke and audit route lists).

**Run V247-1, V247-2 and V247-2b back to back.** V247-1 changes `app.routes.ts`, which `shell/nav.spec.ts` reads (`titleAt`, the ALIASES/redirect agreement); two `nav.spec.ts` tests are red between the V247-1 and V247-2 commits, and the breadcrumb, section-tabs, dock-state and shell specs are red between V247-2 and V247-2b (V247-2 passed 20 KB and was split). Nothing else imports `app.routes.ts` (`git grep -n "app.routes'" frontend/src` lists only `app.config.ts`, `app.routes.spec.ts`, `shell/nav.spec.ts`).

All frontend commands run from the worktree root; `--include` paths are relative to `frontend/`.

---

# Phase 1 — Calendar becomes a destination

### Task V247-1: Calendar workspace at `/calendar`; `/trades/calendar[/:date]` redirect to it

**Model:** sonnet — a route-table flip with redirect-order traps and a dozen spec rows to rewrite.

**Files:**
- Modify: `frontend/src/app/app.routes.ts` (lines 7-8 header comment, 48-56 `trades/calendar` workspace, 84-85 old redirects, 167-169 `**` comment)
- Test: `frontend/src/app/app.routes.spec.ts` (lines 58-99, 144-148, 203-222, 245-315, 327)

**Interfaces:**
- Consumes: nothing new.
- Produces: top-level route `path: 'calendar'` (`canMatch: [authGuard]`, `title: 'Calendar'`, `data: { subtitle: 'P&L by day' }`, `loadChildren` → `calendarRoutes`, whose children are `''` and `':date'`); string redirects `{ path: 'trades/calendar', pathMatch: 'full', redirectTo: 'calendar' }` and `{ path: 'trades/calendar/:date', redirectTo: 'calendar/:date' }`, both declared before `trades/:id`. The old `calendar` / `calendar/:date` redirects are deleted. V247-2 (nav model), V247-3 (links) and V247-4 (route lists) build on these paths.

**Why relative redirects:** a string `redirectTo` with no leading slash keeps the query string and fragment (`app.routes.ts:79-81` already records this). From a top-level route, `'calendar'` resolves to `/calendar`.

- [ ] **Step 1: Write the failing tests** in `frontend/src/app/app.routes.spec.ts`.

In `describe('routing, authenticated')`, add a row to the `mounts %s` table (after `['/trades', 'Trades'],`):

```ts
    ['/calendar', 'Calendar'],
```

Replace the whole test `'serves the calendar workspace behind the auth guard'` (lines 89-99) with:

```ts
  it('serves the calendar workspace at /calendar behind the auth guard (v247)', async () => {
    const route = routes.find((r) => r.path === 'calendar');
    expect(route).toBeDefined();
    expect(route?.canMatch).toEqual([authGuard]);
    expect(route?.redirectTo).toBeUndefined();

    // The lazy route must expose its component through its child config.
    const children = await route!.loadChildren!() as Routes;
    expect(children[1]?.path).toBe(':date');
    expect(children[0]?.loadComponent).toBeTypeOf('function');
    expect(await children[0]!.loadComponent!()).toBeDefined();
  });
```

In `describe('route data readiness contract')`, replace `'trades/calendar'` in `expected` (line 145) with `'calendar'`:

```ts
  const expected = [
    'dashboard', 'trades', 'trades/:id', 'plans/:id', 'insights/analytics', 'calendar',
    'watchlist', 'watchlist/:symbol', 'risk', 'system', 'system/versions', 'insights/research',
    'insights/reports', 'insights/guide',
  ] as const;
```

Replace the comment above `class Blank` and the `stubbed()` function (lines 203-222) with:

```ts
/* v202 V202-4, v247: section routes and the old paths' redirects.
 *
 * Every lazy route is swapped for a blank component, so these tests check
 * the matching and redirect rules themselves, not each workspace's resolver.
 * `calendar` keeps its `''` and `:date` children, as calendar.routes
 * declares them.
 */
@Component({ template: '' })
class Blank {}

function stubbed(): Routes {
  return routes.map((route) => {
    if (!route.loadChildren && !route.loadComponent) return route;
    const { loadChildren: _lazy, loadComponent: _component, ...rest } = route;
    void _lazy; void _component;
    return route.path === 'calendar'
      ? { ...rest, children: [{ path: '', component: Blank }, { path: ':date', component: Blank }] }
      : { ...rest, component: Blank };
  });
}
```

Replace the body of `describe('v202 section routes and redirects', ...)` from its first `it.each` down to (not including) `it('still reads any other second segment as a trade id'` (lines 248-273) with:

```ts
  it.each([
    ['/trades/calendar', '/calendar'],
    ['/trades/calendar/2026-10-01', '/calendar/2026-10-01'],
    ['/analytics', '/insights/analytics'],
    ['/research', '/insights/research'],
    ['/reports', '/insights/reports'],
    ['/versions', '/system/versions'],
    ['/insights', '/insights/analytics'],
  ])('redirects %s to %s, keeping the query string and fragment', async (from, to) => {
    expect((await land(`${from}?tab=tuning&page=2#x`)).url).toBe(`${to}?tab=tuning&page=2#x`);
  });

  it.each(['/cancels', '/trades/cancels'])('sends %s to the Analytics Cancels tab', async (from) => {
    expect((await land(from)).url).toBe('/insights/analytics?tab=cancels');
  });

  it('redirects a bare old path without inventing a query', async () => {
    expect((await land('/trades/calendar')).url).toBe('/calendar');
  });

  it.each([
    ['/calendar', ''],
    ['/calendar/2026-10-01', ':date'],
    ['/calendar?month=2026-11&strategy=EMA20', ''],
  ])('serves %s on the Calendar workspace itself, no redirect (v247)', async (url, child) => {
    const landed = await land(url);
    expect(landed.url).toBe(url);
    expect(landed.paths).toEqual([undefined, 'calendar', child]);
  });

  it.each(['/trades/calendar', '/trades/calendar/2026-10-01'])(
    'never reads %s as a trade id: it lands on the Calendar workspace', async (url) => {
      const { paths } = await land(url);
      expect(paths).not.toContain('trades/:id');
      expect(paths).toContain('calendar');
    });

  it('keeps no redirect pointing at another redirect, so no pair loops (v247)', () => {
    const redirects = new Map(routes
      .filter((route) => typeof route.redirectTo === 'string')
      .map((route) => [route.path, route.redirectTo as string]));
    for (const [from, to] of redirects) {
      expect(redirects.has(to), `${from} -> ${to}`).toBe(false);
    }
    expect(redirects.get('trades/calendar')).toBe('calendar');
    expect(redirects.get('trades/calendar/:date')).toBe('calendar/:date');
    expect(redirects.has('calendar')).toBe(false);
    expect(redirects.has('calendar/:date')).toBe(false);
  });
```

In the titles table (line 288) replace the first row with:

```ts
    ['calendar', 'Calendar', 'P&L by day'],
```

Replace `'declares every section before the route that would swallow it'` and `'keeps no old path as a real page'` (lines 302-314) with:

```ts
  it('declares every section and the moved Calendar paths before the route that would swallow them', () => {
    const at = (path: string) => routes.findIndex((r) => r.path === path);
    expect(at('trades/calendar')).toBeGreaterThanOrEqual(0);
    expect(at('trades/calendar')).toBeLessThan(at('trades/:id'));
    expect(at('trades/calendar/:date')).toBeLessThan(at('trades/:id'));
    expect(at('system/versions')).toBeLessThan(at('system'));
  });

  it('keeps no old path as a real page', () => {
    const old = ['trades/calendar', 'trades/calendar/:date', 'cancels', 'analytics', 'research', 'reports', 'versions'];
    for (const path of old) {
      const route = routes.find((r) => r.path === path);
      expect(route?.redirectTo, path).toBeTruthy();
      expect(route?.loadChildren, path).toBeUndefined();
    }
  });
```

In `describe('routing, viewer (v207)')` replace `'/trades/calendar'` with `'/calendar'` in the `still mounts %s` list (line 327):

```ts
  it.each(['/dashboard', '/trades', '/calendar', '/watchlist', '/risk', '/insights/analytics'])(
```

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/app.routes.spec.ts`
Expected: FAIL — `serves the calendar workspace at /calendar` (`route` undefined), the `/trades/calendar` redirect rows (the URL stays `/trades/calendar`), `serves /calendar on the Calendar workspace itself` (redirected to `/trades/calendar`) and the redirect-loop test.

- [ ] **Step 3: Flip the routes** in `frontend/src/app/app.routes.ts`.

Header comment, line 8 — replace:

```ts
 * Six destinations (v202), their section routes, and the detail views that hang off them.
```

with:

```ts
 * Seven destinations (v202; Calendar became its own in v247), their section
 * routes, and the detail views that hang off them.
```

Replace lines 48-56 (the `// v202: Trades' sections ...` comment and the `trades/calendar` workspace route) with:

```ts
  // v247 (spec v240 §6): Calendar is a destination of its own, no longer a
  // Trades section.
  {
    path: 'calendar',
    canMatch: [authGuard],
    title: 'Calendar',
    data: { subtitle: 'P&L by day' },
    loadChildren: () => import('./workspaces/calendar/calendar.routes').then((m) => m.calendarRoutes),
  },
  // Its old v202 address, kept so bookmarks and Discord links still land.
  // RELATIVE redirects (no leading slash) keep the query string and fragment.
  // Declared BEFORE `trades/:id`, so "calendar" is never read as a trade id.
  { path: 'trades/calendar', pathMatch: 'full', redirectTo: 'calendar' },
  { path: 'trades/calendar/:date', redirectTo: 'calendar/:date' },
```

Delete the two old redirects (lines 84-85):

```ts
  { path: 'calendar', pathMatch: 'full', redirectTo: 'trades/calendar' },
  { path: 'calendar/:date', redirectTo: 'trades/calendar/:date' },
```

`**` comment, line 168 — replace `with six destinations` with `with seven destinations`.

- [ ] **Step 4: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/app.routes.spec.ts`
Expected: PASS, 0 failed.

Then confirm the expected interim red is only in `nav.spec.ts`:
Run: `cd frontend && npx ng test --watch=false --include src/app/shell/nav.spec.ts`
Expected: exactly two failures — `agrees with the redirects app.routes.ts declares` (`/calendar` has no `redirectTo` now) and `labels every section with its route title` (no route for `/trades/calendar`). V247-2 fixes both; do not touch `nav.ts` here.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/app.routes.ts frontend/src/app/app.routes.spec.ts
git commit -m "feat(v247): Calendar workspace at /calendar, /trades/calendar redirects to it" -m "nav.spec.ts is red on two tests until the nav model follows (V247-2)."
```

### Task V247-2: Nav model: Calendar after Trades, Trades a single page, alias gone, default phone tabs flipped

**Model:** sonnet — the nav model edit plus the pure-model specs that pin its order, labels and phone tabs.

**Files:**
- Modify: `frontend/src/app/shell/nav.ts` (NAV_ENTRIES, overrides, ALIASES, doc comments, the PHONE_TABS block at lines 151-175)
- Modify (comments only): `frontend/src/app/shell/palette/palette-items.ts:93-95`, `frontend/src/app/shell/phone-tab-bar.ts:12`
- Test: `frontend/src/app/shell/nav.spec.ts`, `frontend/src/app/shell/palette/palette-items.spec.ts`, `frontend/src/app/shell/palette/command-palette.spec.ts:130` (not in the index ledger: it pins `'Book'` as the third rail page), `frontend/src/app/shell/more-sheet.spec.ts`, `frontend/src/app/shell/phone-tab-bar.spec.ts`

**Split:** this task passed 20 KB whole, so the component specs that read the model (`breadcrumb.spec.ts`, `section-tabs.spec.ts`, `live/dock-state.spec.ts`, `shell.spec.ts`) and the `breadcrumb.ts` comment move to **V247-2b**. Those four specs are red between the V247-2 and V247-2b commits; run V247-2b straight after.

**Interfaces:**
- Consumes: V247-1's `calendar` route (title `Calendar`); `nav.spec.ts` checks every label against its route title.
- Produces (V247-2b, V247-11 and V247-12 consume):
  - `export const DEFAULT_PHONE_TAB_PATHS: readonly string[] = ['/dashboard', '/watchlist', '/trades', '/calendar']`
  - `export function phoneTabsFor(paths: readonly string[], entries: readonly NavEntry[] = NAV_ENTRIES): NavEntry[]`: entries in the order given, unknown paths dropped, `/dashboard` labelled `Home`, `entries` never mutated.
  - `export const PHONE_TABS: readonly NavEntry[] = phoneTabsFor(DEFAULT_PHONE_TAB_PATHS)` (V247-12 deletes it)
  - `export function phoneTabPathFor(url: string, tabs: readonly NavEntry[] = PHONE_TABS): string | null`
  - `NAV_ENTRIES` gains `{ path: '/calendar', label: 'Calendar', icon: 'calendar' }` after Trades; Trades has no `sections`; `SECTION_LABEL_OVERRIDES` is `{ '/system': 'Health' }`; `ALIASES` has no `'/calendar'` key.

- [ ] **Step 1: Write the failing tests.**

`frontend/src/app/shell/nav.spec.ts` — change the import (line 9-10) to:

```ts
import {
  ALIASES, DEFAULT_PHONE_TAB_PATHS, DESTINATION_LABEL_OVERRIDES, NAV_ENTRIES, PHONE_TABS, SECTION_LABEL_OVERRIDES,
  SECTION_WORDS, breadcrumbFor, destinationFor, detailCrumb, isSectionUrl, navEntriesFor, navEntryFor,
  phoneTabPathFor, phoneTabsFor,
} from './nav';
```

Replace the first two tests of `describe('NAV_ENTRIES (v202 §1)')` (lines 18-36) with:

```ts
  it('is seven destinations in rail order, Calendar after Trades, System alone at the foot (v247)', () => {
    expect(NAV_ENTRIES.map((entry) => [entry.path, entry.label])).toEqual([
      ['/dashboard', 'Dashboard'], ['/watchlist', 'Watchlist'], ['/trades', 'Trades'], ['/calendar', 'Calendar'],
      ['/risk', 'Risk'], ['/insights', 'Insights'], ['/system', 'System'],
    ]);
    expect(NAV_ENTRIES.find((entry) => entry.path === '/calendar')?.icon).toBe('calendar');
    expect(paths(NAV_ENTRIES.filter((entry) => entry.foot))).toEqual(['/system']);
  });

  it('gives Insights and System their sections; Trades and Calendar are single pages (v247)', () => {
    const sections = Object.fromEntries(
      NAV_ENTRIES.map((entry) => [entry.path, entry.sections?.map((s) => [s.path, s.label]) ?? null]),
    );
    expect(sections).toEqual({
      '/dashboard': null, '/watchlist': null, '/trades': null, '/calendar': null, '/risk': null,
      '/insights': [['/insights/analytics', 'Analytics'], ['/insights/research', 'Research'], ['/insights/reports', 'Reports'], ['/insights/guide', 'Guide']],
      '/system': [['/system', 'Health'], ['/system/versions', 'Versions']],
    });
  });
```

In `'records exactly its overrides ...'` replace line 63 with:

```ts
    expect(SECTION_LABEL_OVERRIDES).toEqual({ '/system': 'Health' });
```

Replace line 76 (`SECTION_WORDS`) with:

```ts
    expect([...SECTION_WORDS].sort()).toEqual(['analytics', 'guide', 'reports', 'research', 'versions']);
```

Replace the ALIASES map test body (lines 82-87) with:

```ts
    expect(ALIASES).toEqual({
      '/plans': '/trades', '/universe': '/watchlist', '/cockpit': '/dashboard',
      '/cancels': '/insights/analytics',
      '/analytics': '/insights/analytics', '/research': '/insights/research', '/reports': '/insights/reports',
      '/versions': '/system/versions',
    });
```

Replace `describe('PHONE_TABS', ...)` (lines 106-114) with:

```ts
describe('phone tabs (v240 §6)', () => {
  it('defaults to Home, Watchlist, Trades and Calendar, the rail order, each with its destination icon', () => {
    expect(DEFAULT_PHONE_TAB_PATHS).toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
    expect(paths(PHONE_TABS)).toEqual([...DEFAULT_PHONE_TAB_PATHS]);
    expect(PHONE_TABS.map((tab) => tab.label)).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    for (const tab of PHONE_TABS) {
      expect(NAV_ENTRIES.find((entry) => entry.path === tab.path)?.icon).toBe(tab.icon);
    }
  });

  it('maps paths in the order given, drops unknown ones and labels only the Dashboard Home', () => {
    const tabs = phoneTabsFor(['/risk', '/nowhere', '/dashboard', '/trades/calendar']);
    expect(tabs.map((tab) => [tab.path, tab.label])).toEqual([['/risk', 'Risk'], ['/dashboard', 'Home']]);
    expect(phoneTabsFor([])).toEqual([]);
  });

  it('reads only the entries it is given and never relabels NAV_ENTRIES', () => {
    expect(phoneTabsFor(['/system'], navEntriesFor(false))).toEqual([]);
    expect(paths(phoneTabsFor(['/system'], navEntriesFor(true)))).toEqual(['/system']);
    expect(NAV_ENTRIES[0].label).toBe('Dashboard');
  });
});
```

In `navEntryFor`'s `it.each` table replace the five Trades/Calendar rows (lines 124-130, 134) so the table reads, from `/dashboard` to `/watchlist/NVDA`:

```ts
    ['/dashboard', ['Dashboard', null]],
    ['/trades', ['Trades', null]],
    ['/trades/812?tab=plan#why', ['Trades', null]],
    // Before its redirect lands, the old address is a Trades URL with a detail segment.
    ['/trades/calendar', ['Trades', null]],
    ['/trades/analytics', ['Trades', null]],
    ['/plans/5', ['Trades', null]],
    ['/calendar', ['Calendar', null]],
    ['/calendar/2026-10-01?strategy=EMA20', ['Calendar', null]],
    ['/watchlist/NVDA', ['Watchlist', null]],
```

and delete the old `['/calendar/2026-10-01', ['Trades', 'Calendar']],` row further down.

Replace the `phoneTabPathFor` describe (lines 155-169) with:

```ts
describe('phoneTabPathFor', () => {
  it.each([
    ['/calendar/2026-10-01', '/calendar'],
    ['/calendar?month=2026-11', '/calendar'],
    ['/trades', '/trades'],
    ['/trades/812', '/trades'],
    ['/plans/5', '/trades'],
    ['/dashboard', '/dashboard'],
    ['/risk', '/risk'],
    ['/system/versions', '/system'],
    ['/ui', null],
  ])('lights %s on the %j tab', (url, expected) => {
    expect(phoneTabPathFor(url)).toBe(expected);
  });

  it('reads the tab list it is given', () => {
    expect(phoneTabPathFor('/insights/research', phoneTabsFor(['/dashboard']))).toBe('/insights');
    expect(phoneTabPathFor('/calendar/2026-10-01', phoneTabsFor(['/dashboard', '/calendar']))).toBe('/calendar');
  });
});
```

In `destinationFor`'s table replace `['/trades/calendar/2026-10-01', '/trades'],` with `['/calendar/2026-10-01', '/calendar'],`.

Replace the two `isSectionUrl` tables (lines 186-193) with:

```ts
  it.each(['/insights/analytics', '/insights/guide', '/insights/guide/glossary', '/insights/research?page=2',
    '/system/versions', '/versions'])('is true for %s', (url) => {
    expect(isSectionUrl(url)).toBe(true);
  });

  it.each(['/trades', '/trades/812', '/trades/analytics', '/trades/calendar', '/calendar', '/calendar/2026-10-01',
    '/system', '/system?tab=logs', '/risk', '/watchlist/NVDA', '/plans/5', '/ui', ''])('is false for %j', (url) => {
    expect(isSectionUrl(url)).toBe(false);
  });
```

In `breadcrumbFor`'s table replace the rows for `/trades`, `/trades/calendar`, `/trades/812` and `/trades/calendar/2026-10-01` with:

```ts
    ['/trades', null, ['Trades']],
    ['/calendar', null, ['Calendar']],
    ['/trades/812', 'NVDA #812', ['Trades', 'NVDA #812']],
    ['/calendar/2026-10-01', '23 Nov 2026', ['Calendar', '23 Nov 2026']],
```

Replace line 252 (viewer entries) with:

```ts
    expect(paths(navEntriesFor(false))).toEqual(['/dashboard', '/watchlist', '/trades', '/calendar', '/risk', '/insights']);
```

`frontend/src/app/shell/palette/palette-items.spec.ts` — replace `RAIL` (lines 26-27), lines 36-37, the route list at 41-44 and line 212:

```ts
const RAIL = ['Dashboard', 'Watchlist', 'Trades', 'Calendar', 'Risk',
  'Analytics', 'Research', 'Reports', 'Guide', 'Health', 'Versions'];
```

```ts
    expect(pages.find((item) => item.label === 'Calendar')).toEqual({ key: 'page:/calendar', group: 'pages', label: 'Calendar', route: '/calendar' });
    expect(pages.find((item) => item.label === 'Trades')).toEqual({ key: 'page:/trades', group: 'pages', label: 'Trades', route: '/trades' });
    expect(pages.find((item) => item.label === 'Book')).toBeUndefined();
```

```ts
    expect(pageItems().filter((item) => !item.queryParams).map((item) => item.route)).toEqual([
      '/dashboard', '/watchlist', '/trades', '/calendar', '/risk',
      '/insights/analytics', '/insights/research', '/insights/reports', '/insights/guide', '/system', '/system/versions',
    ]);
```

```ts
    expect(routes).toContain('/calendar');
```

`frontend/src/app/shell/palette/command-palette.spec.ts:130` — replace `['Dashboard', 'Watchlist', 'Book']` with `['Dashboard', 'Watchlist', 'Trades']` (the page count, and so `toHaveLength(13)`, is unchanged: Book + Calendar became Trades + Calendar).

`frontend/src/app/shell/more-sheet.spec.ts` — in `'lists no destination the tab bar holds'` use:

```ts
    for (const id of ['more-dashboard', 'more-watchlist', 'more-trades', 'more-calendar']) expect(ids).not.toContain(id);
```

and replace the body of `'keeps every destination when no tab is given ...'` (lines 33-37) with:

```ts
    const groups = morePageGroups(NAV_ENTRIES, []);
    expect(groups).toHaveLength(7);
    expect(shape(groups)[0]).toEqual(['more-dashboard', 'Dashboard', [['Dashboard', '/dashboard']]]);
    expect(shape(groups)[2]).toEqual(['more-trades', 'Trades', [['Trades', '/trades']]]);
    expect(shape(groups)[3]).toEqual(['more-calendar', 'Calendar', [['Calendar', '/calendar']]]);
```

(The default-groups test stays as is: the default bar still leaves Risk, Insights and System to More.)

`frontend/src/app/shell/phone-tab-bar.spec.ts` — change the import to `import { DEFAULT_PHONE_TAB_PATHS } from './nav';` and replace the first three tests (lines 35-57) with:

```ts
  it('holds Home, Watchlist, Trades, Calendar and More, in that order (v240 §6)', async () => {
    const { el } = await mount('/dashboard');
    expect(el.querySelector('nav')!.getAttribute('aria-label')).toBe('Main pages');
    expect([...el.querySelectorAll('.tab .tab-label')].map((n) => n.textContent!.trim()))
      .toEqual(['Home', 'Watchlist', 'Trades', 'Calendar', 'More']);
    expect([...el.querySelectorAll('a.tab')].map((a) => a.getAttribute('href')))
      .toEqual([...DEFAULT_PHONE_TAB_PATHS]);
  });

  it('marks the current tab, and the list tab for its detail pages', async () => {
    expect(current((await mount('/calendar')).el)).toEqual(['Calendar']);
    expect(current((await mount('/plans/7')).el)).toEqual(['Trades']);
    expect(current((await mount('/watchlist/NVDA')).el)).toEqual(['Watchlist']);
  });

  it('lights Calendar on a calendar day and Trades on the trade book', async () => {
    for (const url of ['/calendar', '/calendar/2026-10-01', '/calendar?month=2026-11']) {
      expect(current((await mount(url)).el), url).toEqual(['Calendar']);
    }
    for (const url of ['/trades', '/trades/812']) {
      expect(current((await mount(url)).el), url).toEqual(['Trades']);
    }
  });
```

- [ ] **Step 2: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/nav.spec.ts --include src/app/shell/palette/palette-items.spec.ts --include src/app/shell/palette/command-palette.spec.ts --include src/app/shell/more-sheet.spec.ts --include src/app/shell/phone-tab-bar.spec.ts`
Expected: FAIL. `DEFAULT_PHONE_TAB_PATHS` and `phoneTabsFor` are not exported, so nav.spec and phone-tab-bar.spec fail to compile; the order, palette and More rows fail.

- [ ] **Step 3: Change the nav model** in `frontend/src/app/shell/nav.ts`.

Line 3 doc: `/** One tab inside a destination (v202 §1): `/insights/research`, 'Research'. */`

NAV_ENTRIES doc (line 25): replace `The nav model -- v202 §1. Six destinations,` with `The nav model -- v202 §1, v247. Seven destinations,`. Replace the Trades entry (lines 35-41) with:

```ts
  { path: '/trades', label: 'Trades', icon: 'trades' },
  // v247 (spec v240 §6): Calendar left Trades' sections for a rail entry of its own.
  { path: '/calendar', label: 'Calendar', icon: 'calendar' },
```

Replace `SECTION_LABEL_OVERRIDES` and its doc (lines 67-73) with:

```ts
/** A section label that is not its route's title. The route keeps the page
 *  name the browser tab shows ('System'); the tab names the view inside the
 *  destination ('Health'). */
export const SECTION_LABEL_OVERRIDES: Readonly<Record<string, string>> = {
  '/system': 'Health',
};
```

`SECTION_WORDS` doc (line 81): replace `('calendar')` with `('analytics')`.

ALIASES doc and map (lines 89-104):

```ts
/** v202: the paths that belong to another destination. A plan is part of
 *  the trade book, /universe and /cockpit are older names, and five
 *  pre-v202 pages moved under a destination (app.routes.ts redirects all
 *  but /plans). Resolving them here keeps a rail highlight from blinking
 *  during a redirect. /calendar is a destination again since v247. */
export const ALIASES: Readonly<Record<string, string>> = {
  '/plans': '/trades',
  '/universe': '/watchlist',
  '/cockpit': '/dashboard',
  '/cancels': '/insights/analytics',
  '/analytics': '/insights/analytics',
  '/research': '/insights/research',
  '/reports': '/insights/reports',
  '/versions': '/system/versions',
};
```

`segments` doc (line 106): `/** '/versions/x?y#z' -> ['system', 'versions', 'x']; '' -> []. */`

`isSectionUrl` doc (lines 143-144): `destination's sections: '/insights/research', not '/insights' or '/trades/812'. */`

Replace lines 151-175 (from the `PHONE_TAB_LABELS` doc through `phoneTabPathFor`) with:

```ts
/** The phone tab bar's own label where it differs from the rail's: the
 *  landing page reads as Home on a 64 px tab (v202 §3). */
const PHONE_TAB_LABELS: Readonly<Record<string, string>> = { '/dashboard': 'Home' };

/** The phone bottom bar's default pages, in rail order (v240 §6); PhoneTabBar
 *  adds More last. Risk, Insights and System live in the More sheet. */
export const DEFAULT_PHONE_TAB_PATHS: readonly string[] = ['/dashboard', '/watchlist', '/trades', '/calendar'];

/** The tab entries for a list of destination paths, in the order given.
 *  Paths not in `entries` are dropped; the Dashboard reads Home. Returns
 *  copies, so NAV_ENTRIES keeps its rail labels. */
export function phoneTabsFor(paths: readonly string[], entries: readonly NavEntry[] = NAV_ENTRIES): NavEntry[] {
  return paths
    .map((path) => entries.find((entry) => entry.path === path))
    .filter((entry): entry is NavEntry => entry !== undefined)
    .map((entry) => ({ ...entry, label: PHONE_TAB_LABELS[entry.path] ?? entry.label }));
}

/** The default bar. V247-12 replaces it with TabBarPrefs.tabs(). */
export const PHONE_TABS: readonly NavEntry[] = phoneTabsFor(DEFAULT_PHONE_TAB_PATHS);

/** The phone tab a URL lights: its section's own tab when a tab holds that
 *  section, else its destination's (a calendar day lights Calendar, a plan
 *  lights Trades); null off the nav. */
export function phoneTabPathFor(url: string, tabs: readonly NavEntry[] = PHONE_TABS): string | null {
  const found = navEntryFor(url);
  if (!found) return null;
  const sectionTab = tabs.find((tab) => tab.path === found.section?.path);
  return sectionTab?.path ?? found.entry.path;
}
```

`breadcrumbFor` doc (lines 177-179):

```ts
/** `Destination / Section` ('Insights / Research'), the destination alone on
 *  a single page ('Risk'), plus the detail segment a detail route supplies
 *  ('Trades / NVDA #812'). Empty off the nav. */
```

- [ ] **Step 4: Update the two stale comments** (no code change).

`frontend/src/app/shell/palette/palette-items.ts:93-95`:

```ts
/** Every page of the nav model, in rail order: each section of a
 *  destination (its `sub` the destination, 'Research · Insights') or the
 *  destination itself on a single page; then the workspace tabs. */
```

`frontend/src/app/shell/phone-tab-bar.ts:12`: replace `Home (the Dashboard) · Watchlist · Calendar · Trades, then More (v202 §3).` with `Home (the Dashboard) · Watchlist · Trades · Calendar, then More (v202 §3, v240 §6).`

- [ ] **Step 5: Run the specs to verify they pass**

Run: the Step 2 command again.
Expected: PASS, 0 failed. Then `cd frontend && npx ng test --watch=false --include src/app/app.routes.spec.ts`: still PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/shell/nav.ts frontend/src/app/shell/nav.spec.ts frontend/src/app/shell/palette/palette-items.ts frontend/src/app/shell/palette/palette-items.spec.ts frontend/src/app/shell/palette/command-palette.spec.ts frontend/src/app/shell/more-sheet.spec.ts frontend/src/app/shell/phone-tab-bar.ts frontend/src/app/shell/phone-tab-bar.spec.ts
git commit -m "feat(v247): nav model -- Calendar after Trades, Trades a single page, default phone tabs Home/Watchlist/Trades/Calendar" -m "breadcrumb, section-tabs, dock-state and shell specs follow in V247-2b."
```

### Task V247-2b: Breadcrumb, section tabs, dock state and shell specs follow the nav model

**Model:** sonnet — component specs across four files, re-pinned to the nav model V247-2 changed, with the dock-key and breadcrumb consequences tested.

**Files:**
- Modify (comment only): `frontend/src/app/shell/breadcrumb.ts:15-16`
- Test: `frontend/src/app/shell/breadcrumb.spec.ts`, `frontend/src/app/shell/section-tabs.spec.ts`, `frontend/src/app/shell/live/dock-state.spec.ts`, `frontend/src/app/shell/shell.spec.ts` (route stubs and nav rows only; the rail markup tests change in V247-8)

**Interfaces:**
- Consumes: V247-2's `NAV_ENTRIES` (Calendar after Trades, Trades without sections) and V247-1's `/calendar` route.
- Produces: nothing new. No production code changes. These are the specs V247-2 left red.

Consequences these specs pin (brief Traps): a trade detail's breadcrumb is `Trades / NVDA #812` (no "Book"); a calendar day is `Calendar / <day>`, with `Calendar` linking `/calendar`; `destinationFor('/calendar')` is `'/calendar'`, so a stored dock choice for `/trades` no longer applies to Calendar (preferences are a map keyed by destination, so there is no schema change); `SectionTabs` draws nothing on Trades.

- [ ] **Step 1: Rewrite the specs.**

`frontend/src/app/shell/breadcrumb.spec.ts` — replace the first test, the `it.each` row `['/trades/calendar', ...]`, and the two detail tests (lines 17-22, 29, 38-48, 58-66) with:

```ts
  it('is destination and section on a sectioned page, neither a link', () => {
    expect(crumbsFor('/insights/research', null, 'Research')).toEqual([
      { label: 'Insights', link: null },
      { label: 'Research', link: null },
    ]);
  });

  it('is the destination alone on a single page, Trades and Calendar included (v247)', () => {
    expect(crumbsFor('/risk', null, 'Risk')).toEqual([{ label: 'Risk', link: null }]);
    expect(crumbsFor('/trades', null, 'Trades')).toEqual([{ label: 'Trades', link: null }]);
    expect(crumbsFor('/calendar?month=2026-11', null, 'Calendar')).toEqual([{ label: 'Calendar', link: null }]);
  });
```

```ts
    ['/insights/reports', 'Reports', ['Insights', 'Reports']],
```

```ts
  it('links the crumb before a detail back to its list', () => {
    expect(crumbsFor('/trades/812', 'NVDA #812', 'Trade detail')).toEqual([
      { label: 'Trades', link: '/trades' },
      { label: 'NVDA #812', link: null },
    ]);
    expect(crumbsFor('/watchlist/NVDA', 'NVDA', 'Ticker detail')).toEqual([
      { label: 'Watchlist', link: '/watchlist' },
      { label: 'NVDA', link: null },
    ]);
  });
```

```ts
  it('stands the route title in for a detail that has not loaded yet', () => {
    expect(crumbsFor('/plans/5', null, 'Plan detail').map((crumb) => crumb.label))
      .toEqual(['Trades', 'Plan detail']);
    expect(crumbsFor('/calendar/2026-10-01', null, 'Calendar day')).toEqual([
      { label: 'Calendar', link: '/calendar' },
      { label: 'Calendar day', link: null },
    ]);
  });
```

In the component describe, replace the route stub `{ path: 'trades/calendar', component: Blank, title: 'Calendar' },` with:

```ts
          { path: 'calendar', component: Blank, title: 'Calendar' },
```

and replace the tests `'shows destination and section ...'`, `'shows the detail segment ...'` and `'shows a section page ...'` (lines 116-140) with:

```ts
  it('shows a single page as one crumb, marked current', async () => {
    await go('/trades');
    expect(labels()).toEqual(['Trades']);
    expect(el().querySelector('[aria-current="page"]')!.textContent!.trim()).toBe('Trades');
    expect(el().querySelector('a')).toBeNull();
  });

  it('shows the detail segment once the detail route supplies it, linking back to the list', async () => {
    await go('/trades/812');
    expect(labels()).toEqual(['Trades', 'Trade detail']);
    titles.setDetail('NVDA #812');
    fixture.detectChanges();
    expect(labels()).toEqual(['Trades', 'NVDA #812']);
    const back = el().querySelector('a')!;
    expect(back.textContent!.trim()).toBe('Trades');
    expect(back.getAttribute('href')).toBe('/trades');
    expect(back.classList).toContain('sb-hit');
    expect(el().querySelector('[aria-current="page"]')!.textContent!.trim()).toBe('NVDA #812');
  });

  it('shows Calendar as a destination of its own (v247)', async () => {
    await go('/calendar');
    expect(labels()).toEqual(['Calendar']);
    expect(el().querySelector('a')).toBeNull();
  });
```

and in `'hides its separators from assistive tech'` replace `toHaveLength(2)` with `toHaveLength(1)`.

`frontend/src/app/shell/section-tabs.spec.ts` — replace the test at lines 46-50 with:

```ts
  it("draws a destination's sections as links, in order, in a labelled nav", () => {
    render(entry('/insights'), section('/insights/analytics'));
    expect(el().querySelector('nav')!.getAttribute('aria-label')).toBe('Insights sections');
    expect(tabs()).toEqual([['Analytics', '/insights/analytics'], ['Research', '/insights/research'],
      ['Reports', '/insights/reports'], ['Guide', '/insights/guide']]);
  });

  it('draws nothing on Trades or Calendar, single pages since v247', () => {
    render(entry('/trades'), null);
    expect(el().querySelector('nav')).toBeNull();
    render(entry('/calendar'), null);
    expect(el().querySelector('nav')).toBeNull();
  });
```

`frontend/src/app/shell/live/dock-state.spec.ts` — replace `ROUTES` (lines 15-18) with:

```ts
const ROUTES: Routes = [
  ...['dashboard', 'risk', 'trades', 'calendar', 'insights/analytics', 'ui'].map((path) => ({ path, component: Blank })),
  { path: 'trades/calendar', redirectTo: 'calendar' },
];
```

Replace the `keys %s by destination %s` table (line 44) with:

```ts
  it.each([['/calendar', '/calendar'], ['/insights/analytics?tab=tuning#x', '/insights'], ['/trades/calendar', '/calendar'], ['/trades', '/trades'], ['/ui', null]])(
```

Replace the test `'remembers a toggle per destination, through PreferencesStore'` (lines 69-81) with:

```ts
  it('remembers a toggle per destination, through PreferencesStore', async () => {
    await go('/calendar');
    dock.toggle();
    expect(dock.open()).toBe(true);
    expect(data()[DOCK_PREF_KEY]).toEqual({ '/calendar': true });
    await go('/risk');
    expect(dock.open()).toBe(true);
    dock.toggle();
    expect(dock.open()).toBe(false);
    await go('/trades/calendar');   // the old address redirects onto the same destination
    expect(dock.open()).toBe(true);
    expect(data()[DOCK_PREF_KEY]).toEqual({ '/calendar': true, '/risk': false });
  });

  it("no longer applies a Trades dock choice to Calendar (v247: its own destination)", async () => {
    data.set({ [DOCK_PREF_KEY]: { '/trades': true } });
    await go('/calendar');
    expect(dock.open()).toBe(false);
    await go('/trades');
    expect(dock.open()).toBe(true);
  });
```

In `'keeps the sheet open when only query params or the fragment change'` replace the three `/trades/calendar` URLs (lines 135-138) with `/calendar`, `/calendar?month=2026-11` and `/calendar?month=2026-11#day`.

`frontend/src/app/shell/shell.spec.ts` (stubs and nav rows only; the rail markup tests change in V247-8):
- `describe('shell labelled rail (v202 §3)')` stubs (line 576): replace `{ path: 'trades/calendar', component: Blank },` with `{ path: 'calendar', component: Blank }, { path: 'calendar/:date', component: Blank },`.
- Lines 602 and 618: the expected work labels become `['Dashboard', 'Watchlist', 'Trades', 'Calendar', 'Risk', 'Insights']`; rename the test at 594 to `'draws seven labelled destinations, six work entries then System at the foot (v247)'`.
- `lights exactly one entry` table (line 671): replace `['/trades/calendar', 'Trades'],` with `['/calendar', 'Calendar'], ['/calendar/2026-10-01', 'Calendar'],`.
- Top-bar test (line 733): `expect(crumbs).toEqual(['Trades']);`.
- Replace the whole `describe('section tabs in the shell (v202 §1)')` block (lines 1263-1320) with:

```ts
describe('section tabs in the shell (v202 §1)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: shellProviders([
        { path: 'trades', component: Blank },
        { path: 'trades/:id', component: Blank },
        { path: 'insights/analytics', component: Blank },
        { path: 'insights/research', component: Blank },
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
    const fixture = createShell();
    fixture.detectChanges();
    await go(fixture, url);
    return fixture.nativeElement as HTMLElement;
  }

  const current = (el: HTMLElement) =>
    [...el.querySelectorAll('sb-section-tabs a[aria-current="page"]')].map((a) => a.textContent!.trim());

  it('draws the tabs at the top of the workspace, before the routed page', async () => {
    const el = await at('/insights/research');
    const content = el.querySelector('main.workspace > .workspace-content')!;
    expect(content.firstElementChild!.tagName.toLowerCase()).toBe('sb-section-tabs');
    expect([...content.querySelectorAll('sb-section-tabs a')].map((a) => a.textContent!.trim()))
      .toEqual(['Analytics', 'Research', 'Reports', 'Guide']);
    expect(current(el)).toEqual(['Research']);
  });

  it('draws no tabs on Trades or a trade detail, a single page since v247', async () => {
    expect((await at('/trades')).querySelectorAll('sb-section-tabs a')).toHaveLength(0);
    expect((await at('/trades/812')).querySelectorAll('sb-section-tabs a')).toHaveLength(0);
  });

  it('draws no tabs on a single page', async () => {
    expect((await at('/risk')).querySelectorAll('sb-section-tabs a')).toHaveLength(0);
  });

  it('moves the current tab when the URL moves to another section, and drops the tabs off it', async () => {
    const fixture = createShell();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    await go(fixture, '/insights/analytics');
    expect(current(el)).toEqual(['Analytics']);
    await go(fixture, '/insights/research');
    expect(current(el)).toEqual(['Research']);
    await go(fixture, '/risk');
    expect(el.querySelectorAll('sb-section-tabs a')).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run the specs. They pass at once, because V247-2 already changed the model. Confirm each rewritten test asserts the new shape:**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/breadcrumb.spec.ts --include src/app/shell/section-tabs.spec.ts --include src/app/shell/live/dock-state.spec.ts --include src/app/shell/shell.spec.ts`
Expected: PASS, 0 failed. Then check that the tests are not vacuous: temporarily put `sections: [{ path: '/trades', label: 'Book' }]` back on the Trades entry in `nav.ts` and re-run. `breadcrumb.spec` (`['Trades']`), `section-tabs.spec` (`draws nothing on Trades`) and `shell.spec` (`draws no tabs on Trades`) must fail. Revert the line.

- [ ] **Step 3: Update the stale comment** in `frontend/src/app/shell/breadcrumb.ts:15-16`:

```ts
/** Path segments past the page itself: 0 on '/trades', '/calendar',
 *  '/insights/research' and '/system'; 1 on '/trades/812', '/calendar/2026-10-01'
 *  and '/insights/guide/glossary'.
```

- [ ] **Step 4: Check that no shell source still names the old address**

Run: `git grep -n "trades/calendar" -- frontend/src/app/shell ':!*.spec.ts'`
Expected: no output. In the specs, the only hits are rows that test the old address, plus the dock-state redirect stub.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/breadcrumb.ts frontend/src/app/shell/breadcrumb.spec.ts frontend/src/app/shell/section-tabs.spec.ts frontend/src/app/shell/live/dock-state.spec.ts frontend/src/app/shell/shell.spec.ts
git commit -m "test(v247): breadcrumb, section tabs, dock state and shell rail follow Calendar as a destination"
```

### Task V247-3: Every production `/trades/calendar` link points at `/calendar`; old-paths gate flipped

**Model:** sonnet — mechanical link repointing plus a regex gate rewrite whose catch/let-through rows must stay exact.

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts:308, 791`
- Modify: `frontend/src/app/workspaces/calendar/day/calendar-day.ts:120, 127, 131, 133`
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts:213`
- Test: `frontend/src/app/workspaces/calendar/calendar.spec.ts` (lines 502, 508, 715, 755, 768, 781, 797, 808, 809)
- Test: `frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts` (lines 332, 333, 342, 343, 355, 361, 381, 397, 406, 414, 427, 433)
- Test: `frontend/src/app/routing/old-paths.spec.ts`

**Interfaces:**
- Consumes: V247-1's `/calendar` and `/calendar/:date` routes.
- Produces: `OLD_PATH_WORDS = ['cancels', 'analytics', 'research', 'reports', 'versions']` (no `'calendar'`); `MOVED_PATHS = ['/trades/calendar']` with `LINK_TO_MOVED_PATH`, a gate that fails on any in-app link to the moved address.

**Why:** each of these links still works through V247-1's redirect. But every hop costs a navigation and lights the wrong rail entry for a frame, which `old-paths.spec.ts` exists to forbid (brief Traps). The calendar store writes its own URL relative to the current route (`calendar.spec.ts:781` reads the result), so moving the specs' router config from `trades/calendar` to `calendar` is enough there.

- [ ] **Step 1: Write the failing tests.**

Repoint both calendar specs in one pass. Every hit is an href assertion, a router config `path` or a navigation URL:

```bash
sed -i "s#'/trades/calendar#'/calendar#g; s#path: 'trades/calendar'#path: 'calendar'#g" \
  frontend/src/app/workspaces/calendar/calendar.spec.ts \
  frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts
git grep -n "trades/calendar" -- frontend/src/app/workspaces/calendar
```

Expected: the grep prints only the four production lines (`calendar.ts:308, 791`, `calendar-day.ts:120, 127, 131, 133`) and no spec line. Spot-check the results. `calendar.spec.ts:502` must read:

```ts
    expect(link?.getAttribute('href')).toBe('/calendar/2026-08-03?strategy=EMA20');
```

`calendar.spec.ts:715`:

```ts
        provideRouter([{ path: 'calendar', children: calendarRoutes }], withComponentInputBinding()),
```

`calendar.spec.ts:781`:

```ts
    expect(url.startsWith('/calendar?')).toBe(true);
```

`calendar-day.spec.ts:355` and `:361`:

```ts
    expect(root.querySelector('nav.steps a.month')?.getAttribute('href')).toBe('/calendar?month=2026-08&strategy=EMA20');
```

```ts
  const ROUTES: Routes = [{ path: 'calendar', children: calendarRoutes }];
```

Rewrite `frontend/src/app/routing/old-paths.spec.ts` whole:

```ts
import { describe, expect, it } from 'vitest';

import { TAB_PAGES } from '../shell/palette/palette-items';
import { allSources } from '../ui/testing/all-sources';

/**
 * v202 §2: the five page names that moved under a destination. Their old
 * paths still redirect (app.routes.ts, until Phase 4's close-out), but no
 * link inside the app may lean on that redirect: a hop through it costs a
 * navigation and lights the wrong rail entry for a frame. `/calendar` left
 * this list in v247, when Calendar became a destination again.
 */
const OLD_PATH_WORDS = ['cancels', 'analytics', 'research', 'reports', 'versions'];

/** v247 (spec v240 §6): whole addresses that moved and redirect, for the same reason. */
const MOVED_PATHS = ['/trades/calendar'];

/**
 * Every way a source names a route: a static or bound routerLink, a router
 * call, a palette tab and a palette item's route. API paths
 * ('/analytics/strategies' in a comment, `${base}/calendar/pnl`) sit in no
 * link context and never match. `\x60` is a backtick (a template-literal route).
 */
const LINK_CONTEXT = String.raw`(?:routerLink="|\[routerLink\]="\['|navigate\(\['|navigateByUrl\(['\x60]|route: ['\x60]|tab\(')`;

/** The path must START at the old word, so '/insights/analytics' never
 *  matches, and the word must end there, so '/reportsX' does not either. */
const LINK_TO_OLD_PATH = new RegExp(String.raw`${LINK_CONTEXT}/(?:${OLD_PATH_WORDS.join('|')})(?![\w-])`);

const LINK_TO_MOVED_PATH = new RegExp(String.raw`${LINK_CONTEXT}(?:${MOVED_PATHS.join('|')})(?![\w-])`);

const isOldPath = (route: string | null): boolean =>
  route !== null && OLD_PATH_WORDS.some((word) => route === `/${word}` || route.startsWith(`/${word}/`));

const isMovedPath = (route: string | null): boolean =>
  route !== null && MOVED_PATHS.some((path) => route === path || route.startsWith(`${path}/`));

const offendersOf = (pattern: RegExp) => allSources()
  .filter((file) => /\.(ts|html)$/.test(file.name))
  .filter((file) => pattern.test(file.source))
  .map((file) => file.name);

describe('no in-app link points at a pre-v202 path', () => {
  it.each([
    'routerLink="/analytics"',
    `[routerLink]="['/versions', id]"`,
    `[routerLink]="['/research']"`,
    `tab('/analytics', 'Analytics', 'edge', 'Edge')`,
    `navigateByUrl('/versions')`,
    `navigate(['/reports'], { queryParams })`,
    `route: '/research'`,
    'route: `/cancels/${id}`',
  ])('the scan catches %s', (markup) => {
    expect(LINK_TO_OLD_PATH.test(markup)).toBe(true);
  });

  it.each([
    'routerLink="/calendar"',
    `[routerLink]="['/calendar', day]"`,
    `tab('/insights/analytics', 'Analytics', 'edge', 'Edge')`,
    `navigate(['/trades', id])`,
    '/** `/analytics/strategies`, for the read-only Strategy tab. */',
    "{ path: 'analytics', pathMatch: 'full', redirectTo: 'insights/analytics' }",
    'routerLink="/reportsX"',
  ])('the scan lets %s through', (markup) => {
    expect(LINK_TO_OLD_PATH.test(markup)).toBe(false);
  });

  it('finds no such link in any source under frontend/src', () => {
    expect(offendersOf(LINK_TO_OLD_PATH)).toEqual([]);
  });

  it('opens no palette tab on an old path', () => {
    expect(TAB_PAGES.filter((item) => isOldPath(item.route)).map((item) => item.key)).toEqual([]);
  });
});

describe('no in-app link points at /trades/calendar (v247)', () => {
  it.each([
    'routerLink="/trades/calendar"',
    `[routerLink]="['/trades/calendar', day]"`,
    `[routerLink]="['/trades/calendar']"`,
    `navigateByUrl('/trades/calendar?month=2026-11')`,
    `route: '/trades/calendar'`,
  ])('the scan catches %s', (markup) => {
    expect(LINK_TO_MOVED_PATH.test(markup)).toBe(true);
  });

  it.each([
    'routerLink="/calendar"',
    `[routerLink]="['/calendar', day]"`,
    `[routerLink]="['/trades', id]"`,
    "{ path: 'trades/calendar', pathMatch: 'full', redirectTo: 'calendar' }",
    'routerLink="/trades/calendarX"',
  ])('the scan lets %s through', (markup) => {
    expect(LINK_TO_MOVED_PATH.test(markup)).toBe(false);
  });

  it('finds no such link in any source under frontend/src', () => {
    expect(offendersOf(LINK_TO_MOVED_PATH)).toEqual([]);
  });

  it('opens no palette tab on the moved address', () => {
    expect(TAB_PAGES.filter((item) => isMovedPath(item.route)).map((item) => item.key)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/routing/old-paths.spec.ts --include src/app/workspaces/calendar/calendar.spec.ts --include src/app/workspaces/calendar/day/calendar-day.spec.ts`
Expected: FAIL. `old-paths.spec` `finds no such link ... (v247)` lists `app/workspaces/analytics/tabs/overview.ts`, `app/workspaces/calendar/calendar.ts` and `app/workspaces/calendar/day/calendar-day.ts`. The calendar href assertions still see `/trades/calendar/...`: the routerLinks are absolute, so the new router config does not change them.

- [ ] **Step 3: Repoint the links.**

`frontend/src/app/workspaces/calendar/calendar.ts:308`:

```html
        <a class="open-day" [routerLink]="['/calendar', day]" [queryParams]="dayLinkParams()">Open full day →</a>
```

`calendar.ts:791`:

```ts
  /** Only the filters that are set, so a bare day links as `/calendar/<date>`. */
```

`frontend/src/app/workspaces/calendar/day/calendar-day.ts:120`: replace `the breadcrumb crumb opens /trades/calendar bare. -->` with `the breadcrumb crumb opens /calendar bare. -->`. Lines 127, 131 and 133:

```html
            <a class="prev" [routerLink]="['/calendar', prev]" [queryParams]="store.filterParams()">‹ prev day</a>
```

```html
          <a class="month" [routerLink]="['/calendar']" [queryParams]="backParams()">{{ monthName() ?? 'Calendar' }}</a>
```

```html
            <a class="next" [routerLink]="['/calendar', next]" [queryParams]="store.filterParams()">next day ›</a>
```

`frontend/src/app/workspaces/analytics/tabs/overview.ts:213`:

```html
        <a class="sb-hit" routerLink="/calendar">Open the calendar</a>
```

- [ ] **Step 4: Run the specs to verify they pass**

Run: the Step 2 command again.
Expected: PASS, 0 failed. Then `git grep -n "trades/calendar" -- frontend/src/app ':!*.spec.ts'` prints only the two redirect lines in `app.routes.ts` and its comment.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts frontend/src/app/workspaces/calendar/day/calendar-day.ts frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts frontend/src/app/workspaces/analytics/tabs/overview.ts frontend/src/app/routing/old-paths.spec.ts
git commit -m "feat(v247): in-app calendar links point at /calendar; old-paths gate forbids /trades/calendar"
```

### Task V247-4: `spa.py` lists `calendar` as a destination; probe, smoke and audit route lists follow

**Model:** haiku — tuple and string-list edits with their pinning tests; no branch added anywhere.

**Files:**
- Modify: `swingbot/admin/spa.py:44-49` (comment), `:54-60` (`WORKSPACES`)
- Test: `tests/admin/test_spa_serving.py` (lines 81-88 detail list, 96-102 old-names test, new test after it)
- Modify: `scripts/dev/smoke_spa.py:61-71`
- Modify: `scripts/ops/admin_browser_probe.py:234-236, 259`
- Test: `tests/scripts/test_admin_browser_probe.py:233-237`
- Modify: `frontend/scripts/layout-audit-lib.mjs:16`
- Test: `frontend/scripts/layout-audit-lib.test.mjs:106-115`
- Modify: `frontend/scripts/admin-page-timing.mjs:31, 165-168`

**Interfaces:**
- Consumes: V247-1's `/calendar` and `/calendar/:date` routes.
- Produces: `spa.WORKSPACES` with `"calendar"` in its first (destinations) row; layout-audit `ROUTES` holding `'/calendar'` and `'/calendar/:date'` in place of the `/trades/calendar` pair (still 35 routes); probe `ROUTES` holding `"calendar"`, `"calendar/{date}"`.

**Why:** `"calendar"` already sits in `WORKSPACES`, but in the group of "pre-v202 names … removed at Phase 4's close-out". Left there, that close-out would delete a live destination's prefix, and every reload of `/calendar` would 404 at the server (spec §6). `"trades"` stays, so `/trades/calendar` still reaches Angular's redirect on a reload. `tests/admin/access_expectations.py:15` (`SPA_WORKSPACES`) already lists `"calendar"`, so it needs no change. This is the plan's `bot patch`. The close-out resolves the bump; no `VERSION.json` edit here.

- [ ] **Step 1: Write the failing tests.**

`tests/admin/test_spa_serving.py`: in the `test_a_detail_url_reloads_into_the_spa` parameter list, keep `"/trades/calendar/2026-10-01"` (an old bookmark must still reach the client-side redirect) and replace `"/calendar/2026-10-01"` with `"/calendar/2026-11-23"`. Replace `test_the_old_names_stay_served_until_phase_4` with these two tests:

```python
def test_the_old_names_stay_served_until_phase_4():
    """v202 moved five pages under new destinations. Their old names keep
    serving index.html, so a bookmark still reaches Angular's redirect instead
    of a server 404. Phase 4's close-out removes them with cockpit/universe."""
    for name in ("cancels", "analytics", "research", "reports", "versions",
                 "cockpit", "universe"):
        assert name in spa.WORKSPACES, name


def test_calendar_is_a_served_destination_not_an_old_name(client, built):
    """v247 (spec v240 §6): Calendar is a destination at /calendar again. It sits
    in the destinations row, ahead of the old names Phase 4's close-out deletes,
    and the removal note does not name it, so that close-out cannot drop the
    prefix of a live page."""
    import inspect

    destinations = spa.WORKSPACES[: spa.WORKSPACES.index("analytics")]
    assert "calendar" in destinations
    assert spa.WORKSPACES.count("calendar") == 1

    source = inspect.getsource(spa)
    removal_note = source[source.index("pre-v202 names --"): source.index("WORKSPACES = (")]
    assert "calendar" not in removal_note

    assert client.get("/calendar").status_code == 200
    assert client.get("/calendar/2026-11-23?strategy=EMA20").status_code == 200
```

`tests/scripts/test_admin_browser_probe.py:233-237`:

```python
def test_routes_are_the_spec_list_in_order_with_the_pinned_date():
    assert probe.routes("2026-11-03") == [
        "dashboard", "trades", "calendar", "calendar/2026-11-03", "trades/cancels",
        "watchlist", "risk", "insights/analytics", "insights/research", "insights/reports",
        "system", "system/versions"]
```

`frontend/scripts/layout-audit-lib.test.mjs`: in the `ROUTES visits every destination ...` test, replace the route list and the old-name check (lines 107-115) with:

```js
  for (const route of ['/dashboard', '/trades', '/trades/:id', '/trades/:id?tab=journal', '/calendar',
    '/calendar/:date', '/trades/cancels', '/plans/:plan', '/insights/analytics', '/insights/research',
    '/insights/reports', '/insights/reports?tab=gates', '/insights/guide', '/insights/guide/pipeline', '/insights/guide/strategies', '/watchlist/:symbol', '/risk', '/system?tab=logs',
    '/system?tab=scan', '/system?tab=providers', '/system/versions', '/ui']) {
    assert.ok(ROUTES.includes(route), route);
  }
  // The five old names and the moved Calendar address redirect (v202 §2, v247): an audit of
  // them would visit the same page twice.
  const old = /^\/(analytics|cancels|research|reports|versions)(\/|\?|$)/;
  assert.deepEqual(ROUTES.filter((route) => old.test(route)), []);
  assert.deepEqual(ROUTES.filter((route) => route.startsWith('/trades/calendar')), []);
```

(Keep any assertions that followed line 115 in that test unchanged.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_spa_serving.py`
Expected: FAIL on `test_calendar_is_a_served_destination_not_an_old_name`. `"calendar"` is not before `"analytics"`. (If the `built` fixture skips because no bundle is built, the test is skipped, not failed. In that case run `cd frontend && npx ng build` once, or accept the skip and rely on the source assertions running in CI.)

Run: `python scripts/dev/testrun.py file tests/scripts/test_admin_browser_probe.py`
Expected: FAIL on the routes list.

Run: `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: FAIL. `/calendar` is not in `ROUTES`.

- [ ] **Step 3: Move the names.**

`swingbot/admin/spa.py`: replace comment lines 44-49 with:

```python
#: v202: `insights` is the Insights destination (`/insights/analytics` etc.);
#: System's sections live under `system`. v247: `calendar` is a destination
#: again (`/calendar`, `/calendar/<date>`); `trades` keeps `/trades/calendar`
#: reachable on a reload, for its client-side redirect. The five pre-v202
#: names -- cancels, analytics, research, reports, versions -- stay on
#: purpose, like cockpit/universe above: a reload of an old bookmark must
#: reach Angular's redirect. They come out at Phase 4's close-out, together
#: with cockpit and universe.
```

and `WORKSPACES` (lines 54-60) with:

```python
WORKSPACES = (
    "dashboard", "trades", "calendar", "insights", "watchlist", "risk", "system", "ui", "plans",
    # pre-v202 names, redirected client-side; removed at Phase 4's close-out
    "analytics", "versions", "research", "reports", "cancels",
    # pre-SR4/SR5 names, redirected client-side; removed at Phase 4's close-out
    "cockpit", "universe",
)
```

`scripts/dev/smoke_spa.py:61-71`:

```python
WORKSPACES = ("dashboard", "trades", "calendar", "trades/cancels", "insights",
              "insights/analytics", "insights/research", "insights/reports",
              "watchlist", "system", "system/versions")

#: The pre-SR4/SR5 URLs and (v202) the five pre-Phase-1 page names, kept
#: server-side so a bookmark or an open tab does not 404 before Angular loads
#: and can redirect it. All seven leave at Phase 4's close-out. Checked because losing
```

(keep the rest of that comment as it is), and:

```python
LEGACY_WORKSPACES = ("cockpit", "universe", "cancels", "analytics",
                     "research", "reports", "versions")
```

`scripts/ops/admin_browser_probe.py:234-236`:

```python
ROUTES = ("dashboard", "trades", "calendar", "calendar/{date}", "trades/cancels",
          "watchlist", "risk", "insights/analytics", "insights/research", "insights/reports",
          "system", "system/versions")
```

and line 259's help text: `help="day for calendar/<date>"`.

`frontend/scripts/layout-audit-lib.mjs:16`:

```js
  '/calendar', '/calendar/:date', '/trades/cancels',
```

`frontend/scripts/admin-page-timing.mjs`. Line 31:

```js
  { name: 'Calendar', rail: 'Calendar', route: '/calendar', phrases: [PNL_BASIS] },
```

Lines 165-168. After V247-8 the rail names a link only by its `aria-label`, so match either form:

```js
  // The rail names each link by its visible label (before v247) or its aria-label (v247 on),
  // and Analytics is a section of Insights rather than a rail entry: reach it by an in-app
  // router navigation (history + popstate, no reload), the same path a link click takes.
  const byText = page.locator('a.rail-link').filter({ has: page.locator('.rail-label', { hasText: new RegExp(`^\\s*${spec.rail}\\s*$`) }) });
  const link = page.locator(`a.rail-link[aria-label="${spec.rail}"]`).or(byText);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_spa_serving.py`
Expected: PASS (including `test_every_angular_route_is_served_on_reload`: `calendar` is in both `app.routes.ts` and `WORKSPACES`).

Run: `python scripts/dev/testrun.py file tests/scripts/test_admin_browser_probe.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/admin/test_smoke_spa.py`
Expected: PASS (it does not pin the tuples).

Run: `node --test frontend/scripts/layout-audit-lib.test.mjs` and `node --test frontend/scripts/admin-page-timing.test.mjs`
Expected: both PASS (`PAGES` names and order are unchanged).

Run: `git grep -n "trades/calendar" -- scripts frontend/scripts tests swingbot`
Expected: only `tests/admin/test_spa_serving.py`'s old-bookmark reload row.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/spa.py tests/admin/test_spa_serving.py scripts/dev/smoke_spa.py scripts/ops/admin_browser_probe.py tests/scripts/test_admin_browser_probe.py
git commit -m "fix(v247): spa.py serves calendar as a destination; probe and smoke route lists follow"
git add frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs frontend/scripts/admin-page-timing.mjs
git commit -m "chore(v247): layout audit and page-timing scripts visit /calendar"
```

