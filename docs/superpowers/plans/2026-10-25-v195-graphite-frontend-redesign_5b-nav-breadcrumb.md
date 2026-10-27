# v195 — Graphite, Part 5b: the nav model and breadcrumb

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below.

**Scope of this part (V195-15):** split from Part 5 for the 1500-line cap, unchanged. V195-15 creates the four-group nav model, the phone tabs, the breadcrumb derivation and the `sb-breadcrumb` component, and gives `RouteTitleService` a `detail` channel for detail routes (§5.1, Phase 3). Nothing here changes what the shell renders yet: V195-16 consumes it. It runs after V195-14 and shares no file with V195-13 or V195-14.

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave.** `frontend/src/app/routing/route-title.service.ts` and its spec are as on `main` when this task starts; Part 5's "The state earlier tasks leave" list covers the tokens and shell files this task's tests read. Re-read each file before editing it; every step names its edit by symbol or exact string, never by line number.

---

# Phase 3 — Shell (building blocks)

### Task V195-15: Nav model (four groups, phone tabs), breadcrumb derivation, `RouteTitleService.detail`, `sb-breadcrumb`
**Model:** sonnet — two new small files of data and pure functions plus a signal on an existing service; the care is in the detail channel surviving the router's title update order.

**Files:**
- Create: `frontend/src/app/shell/nav.ts`
- Create: `frontend/src/app/shell/nav.spec.ts`
- Create: `frontend/src/app/shell/breadcrumb.ts`
- Create: `frontend/src/app/shell/breadcrumb.spec.ts`
- Modify: `frontend/src/app/routing/route-title.service.ts` (`RouteTitleService`: `detail`, `setDetail`, `set`'s optional `path`; `SubtitleTitleStrategy.updateTitle` passes the path; a `pathOf` helper)
- Modify: `frontend/src/app/routing/route-title.service.spec.ts` (one route added to the setup; one new describe)

**Interfaces:**
- Consumes: `IconName`, `ICON_NAMES` (`ui/icon.ts`; `'cancelled'` is the Cancels glyph, as today); `routes` (`app.routes.ts`, read only by the spec, to hold labels to route titles); `RouteTitleService`, `SubtitleTitleStrategy`; `RouterLink`, `NavigationEnd`, `toSignal`.
- Produces (V195-16..V195-20 and Phase 5 consume these):
  - `nav.ts`: `interface NavEntry { path: string; label: string; icon: IconName }`; `interface NavGroup { id: string; label: string; entries: readonly NavEntry[] }`; `NAV_GROUPS: readonly NavGroup[]` = `nav-monitor` "Monitor" (Dashboard, Watchlist, Risk) · `nav-review` "Review" (Trades, Calendar, Cancels) · `nav-insights` "Insights" (Analytics, Research, Reports) · `nav-system` "System" (System, Versions); `PHONE_TABS: readonly NavEntry[]` = the `/dashboard`, `/watchlist`, `/trades`, `/risk` entries in that order (the More tab is `PhoneTabBar`'s own, V195-18); `navEntryFor(url: string): { group: NavGroup; entry: NavEntry } | null` (first path segment, query and fragment ignored; `/plans` reads as `/trades`, `/universe` as `/watchlist`; `/ui` and unknown paths are `null`); `breadcrumbFor(url: string, detail: string | null): string[]` (`[group, page]`, plus `detail` when it is non-empty; `[]` when `navEntryFor` is `null`); `detailCrumb(ticker: string | null, id: string | number | null): string` (`'NVDA #812'`, `'NVDA'`, `'#812'`, or `''`).
  - `RouteTitleService.detail: Signal<string | null>`; `RouteTitleService.setDetail(detail: string | null): void` (an empty string is stored as `null`); `RouteTitleService.set(title: string, subtitle: string | null, path: string | null = null): void` clears `detail` on every title update **except** one that stays on the same path (a query-only navigation, such as a tab switch, keeps its page's detail). `SubtitleTitleStrategy` passes the URL path without query or fragment. A detail route calls `setDetail` from an effect or after its data loads, never from its constructor: the router updates the title after it activates the route.
  - `breadcrumb.ts`: `interface Crumb { label: string; link: string | null }`; `crumbsFor(url: string, detail: string | null, title: string): Crumb[]` (pure; on a detail path with no detail yet, the route title stands in as the third crumb; off the nav, the route title alone); `Breadcrumb` (`sb-breadcrumb`): `nav[aria-label="Breadcrumb"] > ol > li`, the page crumb a `routerLink` (class `sb-hit`) when a detail follows it, the last crumb `aria-current="page"`, separators `aria-hidden`, no heading element; below 640px only the last crumb shows.
- `shell.ts` keeps its own `NavEntry`/`NavGroup`/`navGroups` until V195-16 switches it to `NAV_GROUPS`; nothing renders `sb-breadcrumb` before V195-16.

**What changes, and what is already there.** The shell's three nav groups are a literal inside `shell.ts`, labelled in capitals for a sidebar that showed them. Phase 3 needs the same model in four places (rail, phone tab bar, More sheet, command palette) and §5.1 splits Review into Review and Insights, so the model moves into one file with the four groups in sentence case (the rail shows dividers, not group names; the breadcrumb shows them). The top bar's breadcrumb (`Review / Trades / NVDA #812`) is derived from the URL through the same model, so no route file changes. Its detail segment needs a channel: `RouteTitleService` already publishes the route's title and subtitle from the title strategy, so it gains a `detail` signal that detail routes fill (V195-28, V195-30, V195-31) and that the next title update clears, unless the navigation stayed on the same path. `route-focus.ts` and the shell's `<h1>` are untouched here (correction 9 lands with `sb-page`, V195-16 and V195-21); the breadcrumb is a `nav` list, never a heading.

- [ ] **Step 1: Write the failing nav-model tests**

Create `$WT/frontend/src/app/shell/nav.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { routes } from '../app.routes';
import { ICON_NAMES } from '../ui/icon';
import { NAV_GROUPS, PHONE_TABS, breadcrumbFor, detailCrumb, navEntryFor } from './nav';

const paths = (entries: readonly { path: string }[]) => entries.map((entry) => entry.path);
const allEntries = NAV_GROUPS.flatMap((group) => [...group.entries]);

describe('NAV_GROUPS (v195 §5.1)', () => {
  it('is four groups in rail order, named in sentence case', () => {
    expect(NAV_GROUPS.map((group) => [group.id, group.label])).toEqual([
      ['nav-monitor', 'Monitor'],
      ['nav-review', 'Review'],
      ['nav-insights', 'Insights'],
      ['nav-system', 'System'],
    ]);
  });

  it('puts each workspace in its group, in order', () => {
    expect(NAV_GROUPS.map((group) => paths(group.entries))).toEqual([
      ['/dashboard', '/watchlist', '/risk'],
      ['/trades', '/calendar', '/cancels'],
      ['/analytics', '/research', '/reports'],
      ['/system', '/versions'],
    ]);
  });

  it('lists all eleven workspaces once and leaves the /ui gallery off the rail', () => {
    expect(allEntries).toHaveLength(11);
    expect(new Set(paths(allEntries)).size).toBe(11);
    expect(paths(allEntries)).not.toContain('/ui');
  });

  it('labels each entry with its route title', () => {
    for (const entry of allEntries) {
      const route = routes.find((candidate) => `/${candidate.path}` === entry.path);
      expect(route, `no route for ${entry.path}`).toBeDefined();
      expect(route!.title).toBe(entry.label);
    }
  });

  it('draws each entry with a known icon, no two entries sharing one', () => {
    const icons = allEntries.map((entry) => entry.icon);
    for (const icon of icons) expect(ICON_NAMES).toContain(icon);
    expect(new Set(icons).size).toBe(icons.length);
  });
});

describe('PHONE_TABS (v195 Phase 3)', () => {
  it('is Dashboard, Watchlist, Trades and Risk, taken from the same model', () => {
    expect(paths(PHONE_TABS)).toEqual(['/dashboard', '/watchlist', '/trades', '/risk']);
    for (const tab of PHONE_TABS) expect(allEntries).toContain(tab);
  });
});

describe('navEntryFor', () => {
  const at = (url: string) => {
    const found = navEntryFor(url);
    return found ? [found.group.label, found.entry.label] : null;
  };

  it.each([
    ['/trades', ['Review', 'Trades']],
    ['/trades/812?tab=plan#why', ['Review', 'Trades']],
    ['/plans/5', ['Review', 'Trades']],
    ['/watchlist/NVDA', ['Monitor', 'Watchlist']],
    ['/universe', ['Monitor', 'Watchlist']],
    ['/calendar/2026-10-01', ['Review', 'Calendar']],
    ['/system?tab=providers', ['System', 'System']],
    ['/analytics', ['Insights', 'Analytics']],
  ])('places %s', (url, expected) => {
    expect(at(url)).toEqual(expected);
  });

  it.each(['/ui', '/', '', '/nowhere'])('finds nothing for %j', (url) => {
    expect(navEntryFor(url)).toBeNull();
  });
});

describe('breadcrumbFor', () => {
  it('is group then page on a workspace', () => {
    expect(breadcrumbFor('/risk', null)).toEqual(['Monitor', 'Risk']);
  });

  it('adds the detail segment a detail route supplies', () => {
    expect(breadcrumbFor('/trades/812', 'NVDA #812')).toEqual(['Review', 'Trades', 'NVDA #812']);
  });

  it('treats an empty detail as none', () => {
    expect(breadcrumbFor('/risk', '')).toEqual(['Monitor', 'Risk']);
  });

  it('is empty off the nav, so the caller can fall back to the route title', () => {
    expect(breadcrumbFor('/ui', 'anything')).toEqual([]);
  });
});

describe('detailCrumb', () => {
  it.each([
    ['NVDA', 812, 'NVDA #812'],
    ['NVDA', '812', 'NVDA #812'],
    ['NVDA', null, 'NVDA'],
    [null, 812, '#812'],
    ['  ', 7, '#7'],
    [null, null, ''],
    [null, '', ''],
  ] as const)('(%j, %j) is %j', (ticker, id, expected) => {
    expect(detailCrumb(ticker, id)).toBe(expected);
  });
});
```

- [ ] **Step 2: Write the failing detail-channel tests**

In `$WT/frontend/src/app/routing/route-title.service.spec.ts`:

1. In the `provideRouter([...])` list of the existing `beforeEach`, after the `{ path: 'bare', component: Blank, title: 'Bare' },` entry add:

```ts
          { path: 'trades/:id', component: Blank, title: 'Trade detail',
            data: { subtitle: 'One position, end to end' } },
```

2. Inside `describe('route title service', ...)`, after the last case (`clears the subtitle on a route that has none, rather than keeping the last`), add:

```ts

  describe('the breadcrumb detail segment (v195 Phase 3)', () => {
    it('starts empty', async () => {
      await router.navigateByUrl('/trades/812');
      expect(titles.detail()).toBeNull();
    });

    it('publishes what a detail route sets, and stores an empty string as none', async () => {
      await router.navigateByUrl('/trades/812');
      titles.setDetail('NVDA #812');
      expect(titles.detail()).toBe('NVDA #812');
      titles.setDetail('');
      expect(titles.detail()).toBeNull();
    });

    it('clears it on a move to another page', async () => {
      await router.navigateByUrl('/trades/812');
      titles.setDetail('NVDA #812');
      await router.navigateByUrl('/dashboard');
      expect(titles.detail()).toBeNull();
    });

    it('clears it on a move to another record of the same route', async () => {
      // /trades/812 -> /trades/813: the old ticker must not label the new trade
      // while its data loads.
      await router.navigateByUrl('/trades/812');
      titles.setDetail('NVDA #812');
      await router.navigateByUrl('/trades/813');
      expect(titles.detail()).toBeNull();
    });

    it('keeps it across a query-only navigation on the same page', async () => {
      // A tab switch (?tab=...) re-runs the title strategy; the page, and so
      // its detail, did not change.
      await router.navigateByUrl('/trades/812');
      titles.setDetail('NVDA #812');
      await router.navigateByUrl('/trades/812?tab=plan');
      expect(titles.title()).toBe('Trade detail');
      expect(titles.detail()).toBe('NVDA #812');
    });

    it('clears it on a direct set() that names no path', () => {
      titles.setDetail('NVDA #812');
      titles.set('Somewhere', null);
      expect(titles.detail()).toBeNull();
    });
  });
```

- [ ] **Step 3: Write the failing breadcrumb tests**

Create `$WT/frontend/src/app/shell/breadcrumb.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, TitleStrategy, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { RouteTitleService, SubtitleTitleStrategy } from '../routing/route-title.service';
import { Breadcrumb, crumbsFor } from './breadcrumb';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/shell/breadcrumb.ts'), 'utf8');

class Blank {}

describe('crumbsFor (v195 Phase 3)', () => {
  it('is group and page on a workspace, neither a link', () => {
    expect(crumbsFor('/trades', null, 'Trades')).toEqual([
      { label: 'Review', link: null },
      { label: 'Trades', link: null },
    ]);
  });

  it('links the page crumb back to its list when a detail follows it', () => {
    expect(crumbsFor('/trades/812', 'NVDA #812', 'Trade detail')).toEqual([
      { label: 'Review', link: null },
      { label: 'Trades', link: '/trades' },
      { label: 'NVDA #812', link: null },
    ]);
  });

  it('stands the route title in for a detail that has not loaded yet', () => {
    expect(crumbsFor('/plans/5', null, 'Plan detail').map((crumb) => crumb.label))
      .toEqual(['Review', 'Trades', 'Plan detail']);
  });

  it('is the route title alone off the nav', () => {
    expect(crumbsFor('/ui', null, 'UI gallery')).toEqual([{ label: 'UI gallery', link: null }]);
  });

  it('is empty before any route has a title', () => {
    expect(crumbsFor('/', null, '')).toEqual([]);
  });
});

describe('Breadcrumb (sb-breadcrumb)', () => {
  let fixture: ComponentFixture<Breadcrumb>;
  let router: Router;
  let titles: RouteTitleService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([
          { path: 'trades', component: Blank, title: 'Trades' },
          { path: 'trades/:id', component: Blank, title: 'Trade detail' },
          { path: 'ui', component: Blank, title: 'UI gallery' },
        ]),
        { provide: TitleStrategy, useClass: SubtitleTitleStrategy },
      ],
    });
    router = TestBed.inject(Router);
    titles = TestBed.inject(RouteTitleService);
    fixture = TestBed.createComponent(Breadcrumb);
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const go = async (url: string) => {
    await router.navigateByUrl(url);
    fixture.detectChanges();
    await fixture.whenStable();
  };
  const labels = () => [...el().querySelectorAll('li')]
    .map((li) => li.querySelector('a, span:not(.sep)')!.textContent!.trim());

  it('is a labelled nav list, never a heading', async () => {
    await go('/trades');
    expect(el().querySelector('nav[aria-label="Breadcrumb"] > ol')).not.toBeNull();
    expect(el().querySelector('h1, h2, h3, h4, h5, h6')).toBeNull();
  });

  it('shows group and page on a workspace, the page marked current', async () => {
    await go('/trades');
    expect(labels()).toEqual(['Review', 'Trades']);
    expect(el().querySelector('[aria-current="page"]')!.textContent!.trim()).toBe('Trades');
    expect(el().querySelector('a')).toBeNull();
  });

  it('shows the detail segment once the detail route supplies it, linking back to the list', async () => {
    await go('/trades/812');
    expect(labels()).toEqual(['Review', 'Trades', 'Trade detail']);
    titles.setDetail('NVDA #812');
    fixture.detectChanges();
    expect(labels()).toEqual(['Review', 'Trades', 'NVDA #812']);
    const back = el().querySelector('a')!;
    expect(back.textContent!.trim()).toBe('Trades');
    expect(back.getAttribute('href')).toBe('/trades');
    expect(back.classList).toContain('sb-hit');
    expect(el().querySelector('[aria-current="page"]')!.textContent!.trim()).toBe('NVDA #812');
  });

  it('falls back to the route title off the nav', async () => {
    await go('/ui');
    expect(labels()).toEqual(['UI gallery']);
  });

  it('hides its separators from assistive tech', async () => {
    await go('/trades/812');
    const seps = [...el().querySelectorAll('.sep')];
    expect(seps).toHaveLength(2);
    for (const sep of seps) expect(sep.getAttribute('aria-hidden')).toBe('true');
  });

  it('keeps only the current crumb below 640px', () => {
    expect(SOURCE).toMatch(/@media \(max-width: 639px\) \{\s*li:not\(\.current\) \{ display: none; \}/);
  });

  it('draws the separators in the rule colour and the text in the muted one (correction 13)', () => {
    expect(SOURCE).toMatch(/\.sep \{[^}]*color: var\(--text-faint\)/);
    expect(SOURCE).toMatch(/li \{[^}]*color: var\(--text-muted\)/);
  });
});
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/nav.spec.ts --include src/app/shell/breadcrumb.spec.ts --include src/app/routing/route-title.service.spec.ts
```

Expected: FAIL. `nav.spec.ts` and `breadcrumb.spec.ts` cannot resolve `./nav` / `./breadcrumb`; `route-title.service.spec.ts` does not compile (`detail` and `setDetail` do not exist).

- [ ] **Step 5: Create `nav.ts`**

Create `$WT/frontend/src/app/shell/nav.ts`:

```ts
import type { IconName } from '../ui/icon';

/** One page on the rail. `label` is the route's own title (nav.spec.ts holds
 *  them equal), so the rail, the breadcrumb and the browser tab agree. */
export interface NavEntry {
  path: string;
  label: string;
  icon: IconName;
}

export interface NavGroup {
  id: string;
  label: string;
  entries: readonly NavEntry[];
}

/**
 * The nav model -- v195 §5.1. Four groups, split by question:
 *   Monitor   what is happening right now
 *   Review    the trade book and its history
 *   Insights  what the measurements say (split out of Review, which had six)
 *   System    what the bot itself is doing
 *
 * One model for the rail, the phone tab bar and More sheet, the command
 * palette and the breadcrumb. The rail shows the groups as dividers; the
 * breadcrumb shows their names. The /ui gallery is a developer surface,
 * reachable by URL and the palette, never the rail.
 */
export const NAV_GROUPS: readonly NavGroup[] = [
  {
    id: 'nav-monitor',
    label: 'Monitor',
    entries: [
      { path: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
      { path: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
      { path: '/risk', label: 'Risk', icon: 'risk' },
    ],
  },
  {
    id: 'nav-review',
    label: 'Review',
    entries: [
      { path: '/trades', label: 'Trades', icon: 'trades' },
      { path: '/calendar', label: 'Calendar', icon: 'calendar' },
      { path: '/cancels', label: 'Cancels', icon: 'cancelled' },
    ],
  },
  {
    id: 'nav-insights',
    label: 'Insights',
    entries: [
      { path: '/analytics', label: 'Analytics', icon: 'analytics' },
      { path: '/research', label: 'Research', icon: 'research' },
      { path: '/reports', label: 'Reports', icon: 'reports' },
    ],
  },
  {
    id: 'nav-system',
    label: 'System',
    entries: [
      { path: '/system', label: 'System', icon: 'system' },
      { path: '/versions', label: 'Versions', icon: 'versions' },
    ],
  },
];

/** Paths that belong to another entry: a plan is part of the trade book, and
 *  /universe is the watchlist's old name (app.routes.ts redirects it). */
const ALIASES: Readonly<Record<string, string>> = { '/plans': '/trades', '/universe': '/watchlist' };

/** '/trades/812?tab=plan#why' -> '/trades'; '' and '/' -> '/'. */
function firstSegment(url: string): string {
  const path = url.split(/[?#]/)[0];
  return `/${path.split('/').find((part) => part !== '') ?? ''}`;
}

/** The group and entry a URL belongs to, by its first path segment; null off
 *  the nav (the /ui gallery, the root, an unknown path). */
export function navEntryFor(url: string): { group: NavGroup; entry: NavEntry } | null {
  const first = firstSegment(url);
  const path = ALIASES[first] ?? first;
  for (const group of NAV_GROUPS) {
    const entry = group.entries.find((candidate) => candidate.path === path);
    if (entry) return { group, entry };
  }
  return null;
}

/** The phone bottom bar's four page tabs (Phase 3), in order; PhoneTabBar
 *  adds More as the fifth. */
export const PHONE_TABS: readonly NavEntry[] = ['/dashboard', '/watchlist', '/trades', '/risk']
  .map((path) => navEntryFor(path)!.entry);

/** `Group / Page`, plus the detail segment a detail route supplies
 *  ('Review / Trades / NVDA #812'). Empty off the nav. */
export function breadcrumbFor(url: string, detail: string | null): string[] {
  const found = navEntryFor(url);
  if (!found) return [];
  const crumbs = [found.group.label, found.entry.label];
  return detail ? [...crumbs, detail] : crumbs;
}

/** A trade or plan's detail segment: 'NVDA #812'. Either half may be missing;
 *  both missing is '' (breadcrumbFor treats it as no detail). */
export function detailCrumb(ticker: string | null, id: string | number | null): string {
  const symbol = ticker?.trim() || null;
  const number = id === null || id === '' ? null : `#${id}`;
  return [symbol, number].filter((part): part is string => part !== null).join(' ');
}
```

- [ ] **Step 6: The detail channel in `route-title.service.ts`**

Re-read `$WT/frontend/src/app/routing/route-title.service.ts` first.

1. Replace the `RouteTitleService` class (from its docblock `/**` / ` * The active route's title and subtitle, as signals — v85 D4.` through its closing `}`) with:

```ts
/**
 * The active route's title and subtitle, as signals — v85 D4.
 *
 * The shell's top bar renders these; workspaces no longer render a heading of
 * their own. One page, one title, and it lives where the design puts it.
 *
 * v195 Phase 3: plus the breadcrumb's detail segment ('NVDA #812', a long
 * date), which only a detail route knows. It sets it once its data is loaded
 * -- from an effect, never its constructor: the router updates the title
 * after it activates the route, and every title update that moves to another
 * path clears the detail, so a page never shows the last record's name. A
 * query-only navigation (a tab switch) stays on the path and keeps it.
 */
@Injectable({ providedIn: 'root' })
export class RouteTitleService {
  private readonly _title = signal('');
  private readonly _subtitle = signal<string | null>(null);
  private readonly _detail = signal<string | null>(null);
  /** The path the current title belongs to; null after a path-less set(). */
  private path: string | null = null;

  readonly title: Signal<string> = this._title.asReadonly();
  readonly subtitle: Signal<string | null> = this._subtitle.asReadonly();
  readonly detail: Signal<string | null> = this._detail.asReadonly();

  set(title: string, subtitle: string | null, path: string | null = null): void {
    this._title.set(title);
    this._subtitle.set(subtitle);
    if (path === null || path !== this.path) this._detail.set(null);
    this.path = path;
  }

  /** The breadcrumb detail segment; '' is stored as none. */
  setDetail(detail: string | null): void {
    this._detail.set(detail || null);
  }
}
```

2. In `SubtitleTitleStrategy.updateTitle`, old → new:

```ts
    this.titles.set(title, subtitleOf(snapshot.root));
```

```ts
    this.titles.set(title, subtitleOf(snapshot.root), pathOf(snapshot.url));
```

3. At the end of the file, after `subtitleOf`, add:

```ts

/** The URL without its query or fragment: '/trades/812?tab=plan' ->
 *  '/trades/812'. Two navigations with the same path are the same page. */
function pathOf(url: string): string {
  return url.split(/[?#]/)[0];
}
```

- [ ] **Step 7: Create `breadcrumb.ts`**

Create `$WT/frontend/src/app/shell/breadcrumb.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map } from 'rxjs';

import { RouteTitleService } from '../routing/route-title.service';
import { breadcrumbFor, navEntryFor } from './nav';

export interface Crumb {
  label: string;
  /** Set on the page crumb when a detail follows it: the way back to the list. */
  link: string | null;
}

/** '/trades' is 1 deep, '/trades/812' is 2: anything past the workspace is a detail page. */
function depth(url: string): number {
  return url.split(/[?#]/)[0].split('/').filter((part) => part !== '').length;
}

/**
 * The crumbs for a URL -- v195 Phase 3. `Group / Page`, plus the detail
 * segment on a detail route: the one the route supplied, or its title while
 * the record loads ('Trade detail'). Off the nav (the /ui gallery) the route
 * title alone. Pure, so the spec can hold every case without a router.
 */
export function crumbsFor(url: string, detail: string | null, title: string): Crumb[] {
  const shownDetail = detail || (depth(url) > 1 && title ? title : null);
  const labels = breadcrumbFor(url, shownDetail);
  if (labels.length === 0) return title ? [{ label: title, link: null }] : [];
  const listPath = labels.length === 3 ? navEntryFor(url)!.entry.path : null;
  return labels.map((label, index) => ({ label, link: index === 1 ? listPath : null }));
}

/**
 * The top bar's breadcrumb -- v195 Phase 3, spec correction 9. A labelled
 * list, never a heading: the page's single <h1> belongs to sb-page. On a
 * phone only the current crumb shows (the top bar collapses to the page
 * title there).
 */
@Component({
  selector: 'sb-breadcrumb',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <nav class="crumbs" aria-label="Breadcrumb">
      <ol>
        @for (crumb of crumbs(); track $index; let last = $last) {
          <li [class.current]="last">
            @if (crumb.link) {
              <a class="sb-hit" [routerLink]="crumb.link">{{ crumb.label }}</a>
            } @else {
              <span class="crumb" [attr.aria-current]="last ? 'page' : null">{{ crumb.label }}</span>
            }
            @if (!last) {
              <span class="sep" aria-hidden="true">/</span>
            }
          </li>
        }
      </ol>
    </nav>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    ol {
      display: flex;
      align-items: center;
      gap: var(--space-6);
      min-width: 0;
      margin: 0;
      padding: 0;
      list-style: none;
      font-size: var(--text-table);
    }
    li { display: inline-flex; align-items: center; gap: var(--space-6); min-width: 0; white-space: nowrap; color: var(--text-muted); }
    /* The current page reads as the title: the strongest text in the bar,
       and the one crumb that gives way (ellipsis) when the bar is short. */
    li.current { overflow: hidden; color: var(--text); font-weight: 600; }
    li.current .crumb { overflow: hidden; text-overflow: ellipsis; }
    a { color: inherit; text-decoration: none; border-radius: var(--radius-sm); }
    a:hover { color: var(--text); }
    a:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    /* A divider, not text (correction 13): the rule colour is right here. */
    .sep { color: var(--text-faint); }
    @media (max-width: 639px) {
      li:not(.current) { display: none; }
    }
  `,
})
export class Breadcrumb {
  private readonly router = inject(Router);
  private readonly titles = inject(RouteTitleService);

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map(() => this.router.url),
    ),
    { initialValue: this.router.url },
  );

  protected readonly crumbs = computed(() => crumbsFor(this.url(), this.titles.detail(), this.titles.title()));
}
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/nav.spec.ts --include src/app/shell/breadcrumb.spec.ts --include src/app/routing/route-title.service.spec.ts --include src/app/shell/shell.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/title-usage.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `shell.spec.ts` still renders the three old groups (the shell does not read `NAV_GROUPS` until V195-16) and still finds the title in the top bar (the strategy's two existing arguments are unchanged); `breakpoint-guard.spec.ts` accepts `max-width: 639px`; `spacing.spec.ts` finds `--space-6`, `--radius-sm` and the colour tokens defined. If a breadcrumb case reads the previous URL right after `go(...)`, the `NavigationEnd` signal has not flushed: `go` already awaits `whenStable()`; do not read `router.url` in the template instead.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. Nothing renders `sb-breadcrumb` yet, so no browser pass here; V195-16 mounts it in the 40px top bar and checks it at 390, 768 and 1440.

- [ ] **Step 9: Close**

Close: standard (test: `frontend/src/app/shell/nav.spec.ts`), plus `frontend/src/app/shell/breadcrumb.spec.ts` and `frontend/src/app/routing/route-title.service.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/shell/nav.ts frontend/src/app/shell/nav.spec.ts frontend/src/app/shell/breadcrumb.ts frontend/src/app/shell/breadcrumb.spec.ts frontend/src/app/routing/route-title.service.ts frontend/src/app/routing/route-title.service.spec.ts
git -C "$WT" commit -m "feat(v195): nav model in four groups, phone tabs, breadcrumb and the route detail channel (V195-15)" -m "Spec §5.1 and Phase 3: shell/nav.ts holds NAV_GROUPS (Monitor, Review, Insights, System), PHONE_TABS, navEntryFor, breadcrumbFor and detailCrumb, one model for the rail, phone bar, palette and breadcrumb, with labels held equal to the route titles. RouteTitleService gains a detail signal and setDetail(); a title update that moves to another path clears it, a query-only navigation keeps it. sb-breadcrumb renders Group / Page / Detail as a labelled list (never a heading), linking the page crumb back to its list on a detail route and keeping only the current crumb on a phone. Nothing mounts it yet (V195-16)." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```
