# v202 UI shell cockpit, part 1b: routes and redirects

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md)
**Index:** [`_0-index.md`](2026-10-29-v202-ui-shell-cockpit_0-index.md): Goal, Global Constraints, Review Focus, Parallelisation and every cross-task contract live there and bind the task below.

Part scope: V202-4 only. It sits in its own file because part 1 (V202-1 … V202-3) would otherwise pass 1500 lines. It covers the new section routes, the redirects from every old path (query string and fragment kept) and the server allow-lists. Links inside the app move in V202-5 (part 2).

`<wt>` is the implementation worktree's absolute path.

# Phase 2: Routes

### Task V202-4: Routes and redirects; `insights` in `spa.WORKSPACES`; smoke lists

**Model:** sonnet — a route table edit with the ordering and redirect rules spelled out, plus two allow-lists; the one subtle behaviour (relative redirects keep query and fragment) is proved by a test.

**Files:**
- Modify: `frontend/src/app/app.routes.ts`, `frontend/src/app/app.routes.spec.ts`
- Modify: `frontend/src/app/shell/nav.spec.ts` (label lookup only; V202-6 rewrites the file)
- Modify: `swingbot/admin/spa.py:33-48` (`WORKSPACES` and its comment)
- Modify: `scripts/dev/smoke_spa.py:51-66` (`WORKSPACES`, `LEGACY_WORKSPACES`, comments)
- Modify: `tests/admin/test_spa_serving.py:34` and the detail-URL parametrize (around line 80)

**Interfaces:**
- Consumes: the existing lazy route modules `calendarRoutes` (children `''` and `':date'`), `cancelsRoutes`, `analyticsRoutes`, `researchRoutes`, `reportsRoutes`, `versionsRoutes`, all unchanged; `authGuard`.
- Produces (index ledger, final): top-level routes `trades/calendar` (its `:date` child gives `/trades/calendar/<date>`), `trades/cancels`, `insights` (redirect to `insights/analytics`), `insights/analytics`, `insights/research`, `insights/reports` and `system/versions`. Their `title`s are `Calendar`, `Cancels`, `Analytics`, `Research`, `Reports` and `Versions`, with subtitles unchanged. The old `calendar`, `calendar/:date`, `cancels`, `analytics`, `research`, `reports` and `versions` are relative redirects that keep query and fragment. V202-6's label invariant reads these `title`s; V202-5 moves links onto these paths. `spa.WORKSPACES` gains `"insights"` and keeps every old name until Phase 4's close-out.

- [ ] **Step 1: Write the failing route tests**

In `frontend/src/app/app.routes.spec.ts`:

1. Add `Component` to the `@angular/core` import.
2. In `it.each([...])('mounts %s', ...)`, replace `['/analytics', 'Analytics']` with `['/insights/analytics', 'Analytics']`. The test's `routes.find((r) => r.path === path.slice(1))` already handles a two-segment path.
3. In `'serves the calendar workspace behind the auth guard'`, change `r.path === 'calendar'` to `r.path === 'trades/calendar'`, and add `expect(children[1]?.path).toBe(':date');` after the `children` line.
4. In `'serves Research and Reports as real pages, ...'`, change the loop list to `['insights/research', 'insights/reports']`.
5. In `describe('route data readiness contract')`, the `expected` list becomes:

```ts
  const expected = [
    'dashboard', 'trades', 'trades/:id', 'plans/:id', 'insights/analytics', 'trades/calendar',
    'watchlist', 'watchlist/:symbol', 'risk', 'system', 'system/versions', 'insights/research',
    'insights/reports',
  ] as const;
```

6. In `'refreshes Analytics and System only for their active tabs'`, change `route.path === 'analytics'` to `route.path === 'insights/analytics'`.

Then append a new describe block at the end of the file:

```ts
/* v202 V202-4: section routes and the old paths' redirects.
 *
 * Every lazy route is swapped for a blank component, so these tests check
 * the matching and redirect rules themselves, not each workspace's resolver.
 * `trades/calendar` keeps its `''` and `:date` children, as calendar.routes
 * declares them.
 */
@Component({ template: '' })
class Blank {}

function stubbed(): Routes {
  return routes.map((route) => {
    if (!route.loadChildren && !route.loadComponent) return route;
    const { loadChildren: _lazy, loadComponent: _component, ...rest } = route;
    return route.path === 'trades/calendar'
      ? { ...rest, children: [{ path: '', component: Blank }, { path: ':date', component: Blank }] }
      : { ...rest, component: Blank };
  });
}

function configureStubbed() {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(stubbed()),
      provideLocationMocks(),
      { provide: SessionStore, useValue: { isAuthenticated: () => true } },
    ],
  });
}

// One harness per test: every test below navigates exactly once.
async function land(url: string): Promise<{ url: string; paths: (string | undefined)[] }> {
  const harness = await RouterTestingHarness.create();
  await harness.navigateByUrl(url);
  const router = TestBed.inject(Router);
  let leaf = router.routerState.snapshot.root;
  while (leaf.firstChild) leaf = leaf.firstChild;
  return { url: router.url, paths: leaf.pathFromRoot.map((s) => s.routeConfig?.path) };
}

describe('v202 section routes and redirects', () => {
  beforeEach(() => configureStubbed());

  it.each([
    ['/calendar', '/trades/calendar'],
    ['/calendar/2026-10-01', '/trades/calendar/2026-10-01'],
    ['/cancels', '/trades/cancels'],
    ['/analytics', '/insights/analytics'],
    ['/research', '/insights/research'],
    ['/reports', '/insights/reports'],
    ['/versions', '/system/versions'],
    ['/insights', '/insights/analytics'],
  ])('redirects %s to %s, keeping the query string and fragment', async (from, to) => {
    expect((await land(`${from}?tab=tuning&page=2#x`)).url).toBe(`${to}?tab=tuning&page=2#x`);
  });

  it('redirects a bare old path without inventing a query', async () => {
    expect((await land('/calendar')).url).toBe('/trades/calendar');
  });

  it.each(['/trades/calendar', '/trades/cancels', '/trades/calendar/2026-10-01'])(
    'matches %s as a section, never as a trade id', async (url) => {
      const { paths } = await land(url);
      expect(paths).not.toContain('trades/:id');
      expect(paths.some((p) => p === 'trades/calendar' || p === 'trades/cancels')).toBe(true);
    });

  it('still reads any other second segment as a trade id', async () => {
    expect((await land('/trades/812')).paths).toContain('trades/:id');
  });

  it('serves Versions as a System section', async () => {
    expect((await land('/system/versions')).paths).toContain('system/versions');
  });

  it('keeps Health on the bare System path with its query tabs', async () => {
    expect((await land('/system?tab=logs')).paths).toContain('system');
  });

  it.each([
    ['trades/calendar', 'Calendar', 'P&L by day'],
    ['trades/cancels', 'Cancels', "Were the bot's own cancels right?"],
    ['insights/analytics', 'Analytics', 'What already happened, measured'],
    ['insights/research', 'Research', 'Every pre-registration and its verdict'],
    ['insights/reports', 'Reports', 'What the measurements say about entries and gates'],
    ['system/versions', 'Versions', "What's deployed, and when it changed"],
  ])('declares %s with its section title and the page subtitle unchanged', (path, title, subtitle) => {
    const route = routes.find((r) => r.path === path);
    expect(route?.title).toBe(title);
    expect(route?.data?.['subtitle']).toBe(subtitle);
    expect(route?.canMatch).toEqual([authGuard]);
  });

  it('declares every section before the route that would swallow it', () => {
    const at = (path: string) => routes.findIndex((r) => r.path === path);
    expect(at('trades/calendar')).toBeLessThan(at('trades/:id'));
    expect(at('trades/cancels')).toBeLessThan(at('trades/:id'));
    expect(at('system/versions')).toBeLessThan(at('system'));
  });

  it('keeps no old path as a real page', () => {
    for (const old of ['calendar', 'cancels', 'analytics', 'research', 'reports', 'versions']) {
      const route = routes.find((r) => r.path === old);
      expect(route?.redirectTo, old).toBeTruthy();
      expect(route?.loadChildren, old).toBeUndefined();
    }
  });
});
```

In `frontend/src/app/shell/nav.spec.ts`, replace the body of `'labels each entry with its route title'`. This keeps the old invariant green until V202-6 replaces it with the section-aware one:

```ts
  it('labels each entry with its route title', () => {
    // v202 V202-4: the old paths are redirects now. Until V202-6 moves the nav
    // model onto the new paths, each entry is looked up at the path it moved to.
    const moved: Record<string, string> = {
      '/calendar': '/trades/calendar', '/cancels': '/trades/cancels',
      '/analytics': '/insights/analytics', '/research': '/insights/research',
      '/reports': '/insights/reports', '/versions': '/system/versions',
    };
    for (const entry of allEntries) {
      const path = moved[entry.path] ?? entry.path;
      const route = routes.find((candidate) => `/${candidate.path}` === path);
      expect(route, `no route for ${path}`).toBeDefined();
      expect(route!.title).toBe(entry.label);
    }
  });
```

- [ ] **Step 2: Write the failing server tests**

In `tests/admin/test_spa_serving.py`, change line 34 to:

```python
SPA_WORKSPACES = ("cockpit", "trades", "analytics", "universe", "system", "plans", "cancels",
                  "insights")
```

Extend the parametrize of `test_a_detail_url_reloads_into_the_spa` (both a new path and an old one must reload into the SPA):

```python
@pytest.mark.parametrize("path", [
    "/universe/AAPL",
    "/plans/44444444-4444-4444-8444-444444444444",
    "/trades/calendar/2026-10-01",
    "/insights/analytics",
    "/system/versions",
    "/calendar/2026-10-01",
])
```

Add below that test:

```python
def test_the_old_names_stay_served_until_phase_4():
    """v202 moved six pages under new destinations. Their old names keep
    serving index.html, so a bookmark still reaches Angular's redirect instead
    of a server 404. Phase 4's close-out removes them with cockpit/universe."""
    for name in ("calendar", "cancels", "analytics", "research", "reports", "versions",
                 "cockpit", "universe"):
        assert name in spa.WORKSPACES, name
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `npm --prefix <wt>/frontend test -- --watch=false --include src/app/app.routes.spec.ts`
Expected: FAIL. `trades/calendar` and the other section routes are not declared, and `/calendar` stays at `/calendar`.

Run: `python <wt>/scripts/dev/testrun.py file tests/admin/test_spa_serving.py`
Expected: FAIL with `/insights` returning 404.

- [ ] **Step 4: Edit `app.routes.ts`**

Insert directly after the `trades` route and before `trades/:id`:

```ts
  // v202: Trades' sections. Declared BEFORE `trades/:id`, so a section word is
  // never read as a trade id (`/trades/calendar` is not trade "calendar").
  {
    path: 'trades/calendar',
    canMatch: [authGuard],
    title: 'Calendar',
    data: { subtitle: 'P&L by day' },
    loadChildren: () => import('./workspaces/calendar/calendar.routes').then((m) => m.calendarRoutes),
  },
  {
    path: 'trades/cancels',
    canMatch: [authGuard],
    title: 'Cancels',
    data: { subtitle: "Were the bot's own cancels right?" },
    loadChildren: () => import('./workspaces/cancels/cancels.routes').then((m) => m.cancelsRoutes),
  },
```

Replace the three route objects `analytics`, `calendar` and `cancels` (between `plans/:id` and `watchlist`) with:

```ts
  // v202: the pre-Phase-1 paths. RELATIVE redirects (no leading slash) keep
  // the query string and fragment, which Analytics' tab state and every old
  // bookmark depend on; an absolute redirect would drop both. These come out
  // at Phase 4's close-out with `cockpit` and `universe`, together with
  // their names in spa.py's WORKSPACES.
  { path: 'calendar', pathMatch: 'full', redirectTo: 'trades/calendar' },
  { path: 'calendar/:date', redirectTo: 'trades/calendar/:date' },
  { path: 'cancels', pathMatch: 'full', redirectTo: 'trades/cancels' },
  { path: 'analytics', pathMatch: 'full', redirectTo: 'insights/analytics' },
  { path: 'research', pathMatch: 'full', redirectTo: 'insights/research' },
  { path: 'reports', pathMatch: 'full', redirectTo: 'insights/reports' },
  { path: 'versions', pathMatch: 'full', redirectTo: 'system/versions' },
```

Replace the `system`, `versions`, `research` and `reports` route objects (between `risk` and `ui`) with:

```ts
  // v202: System's Versions section, before `system` so it is matched first.
  {
    path: 'system/versions',
    canMatch: [authGuard],
    title: 'Versions',
    data: { subtitle: "What's deployed, and when it changed" },
    loadChildren: () => import('./workspaces/versions/versions.routes').then((m) => m.versionsRoutes),
  },
  {
    path: 'system',
    canMatch: [authGuard],
    title: 'System',
    data: { subtitle: 'What the bot itself is doing' },
    loadChildren: () => import('./workspaces/system/system.routes').then((m) => m.systemRoutes),
  },
  // v202: Insights has no page of its own; it opens on its first section.
  { path: 'insights', pathMatch: 'full', redirectTo: 'insights/analytics' },
  {
    path: 'insights/analytics',
    canMatch: [authGuard],
    title: 'Analytics',
    data: { subtitle: 'What already happened, measured' },
    loadChildren: () => import('./workspaces/analytics/analytics.routes').then((m) => m.analyticsRoutes),
  },
  {
    path: 'insights/research', canMatch: [authGuard], title: 'Research',
    data: { subtitle: 'Every pre-registration and its verdict' },
    loadChildren: () => import('./workspaces/research/research.routes').then((m) => m.researchRoutes),
  },
  {
    path: 'insights/reports', canMatch: [authGuard], title: 'Reports',
    data: { subtitle: 'What the measurements say about entries and gates' },
    loadChildren: () => import('./workspaces/reports/reports.routes').then((m) => m.reportsRoutes),
  },
```

In the file's top doc comment, change "Six workspaces, plus the two detail views that hang off them." to "Six destinations (v202), their section routes, and the detail views that hang off them."

If the redirect test shows the query string or fragment lost (it should not: relative string redirects keep both in Angular 21), swap those eight redirects for a `RedirectFunction`. The `/calendar/:date` one would read `redirectTo: ({ params, queryParams, fragment }) => inject(Router).createUrlTree(['/trades/calendar', params['date']], { queryParams, fragment: fragment ?? undefined })`, with `inject` from `@angular/core` and `Router` from `@angular/router`. Record the swap in the task report.

- [ ] **Step 5: Edit the server allow-lists**

In `swingbot/admin/spa.py`, change the `#: The seven workspaces.` comment block's first line to `#: The destinations and their sections (v202).`, and add this paragraph above `#: A route added to ...`:

```python
#: v202: `insights` is the Insights destination (`/insights/analytics` etc.);
#: Trades' and System's sections live under `trades` and `system`. The six
#: pre-v202 names -- calendar, cancels, analytics, research, reports,
#: versions -- stay on purpose, like cockpit/universe above: a reload of an
#: old bookmark must reach Angular's redirect. They come out at Phase 4's
#: close-out, together with cockpit and universe.
```

and the tuple:

```python
WORKSPACES = (
    "dashboard", "trades", "insights", "watchlist", "risk", "system", "ui", "plans",
    # pre-v202 names, redirected client-side; removed at Phase 4's close-out
    "analytics", "calendar", "versions", "research", "reports", "cancels",
    # pre-SR4/SR5 names, redirected client-side; removed at Phase 4's close-out
    "cockpit", "universe",
)
```

In `scripts/dev/smoke_spa.py`:

```python
WORKSPACES = ("dashboard", "trades", "trades/calendar", "trades/cancels", "insights",
              "insights/analytics", "insights/research", "insights/reports",
              "watchlist", "system", "system/versions")

#: The pre-SR4/SR5 URLs and (v202) the six pre-Phase-1 page names, kept
#: server-side so a bookmark or an open tab does not 404 before Angular loads
#: and can redirect it. All eight leave at Phase 4's close-out.
LEGACY_WORKSPACES = ("cockpit", "universe", "calendar", "cancels", "analytics",
                     "research", "reports", "versions")
```

Keep the existing comment above `LEGACY_WORKSPACES` and replace its first sentence with the one shown here. Add one sentence to the `WORKSPACES` comment: "Entries may be multi-segment: a section path is served through its destination's prefix."

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npm --prefix <wt>/frontend test -- --watch=false --include src/app/app.routes.spec.ts`, then `... --include src/app/shell/nav.spec.ts`
Expected: PASS each.

Run: `python <wt>/scripts/dev/testrun.py file tests/admin/test_spa_serving.py`, then `... file tests/admin/test_smoke_spa.py`
Expected: PASS each. `test_every_angular_route_is_served_on_reload` now sees `insights` and finds it in `WORKSPACES`.

Lint: `npm --prefix <wt>/frontend run lint`. Expected: clean (the `_lazy`/`_component` destructuring names are unused on purpose; if the lint config flags them, use `void _lazy; void _component;` rather than adding a suppression).

Layout: no shell markup changes in this task, and pages move under new URLs unchanged. V203-10 audits the new paths at all three widths.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add frontend/src/app/app.routes.ts frontend/src/app/app.routes.spec.ts frontend/src/app/shell/nav.spec.ts swingbot/admin/spa.py scripts/dev/smoke_spa.py tests/admin/test_spa_serving.py
git -C <wt> commit -m "feat(v202): section routes under Trades, Insights and System; old paths redirect

trades/calendar, trades/cancels, insights/{analytics,research,reports} and
system/versions mount the unchanged workspaces; the old paths redirect with
query and fragment kept. spa.py serves insights and keeps every old name
until Phase 4's close-out.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
