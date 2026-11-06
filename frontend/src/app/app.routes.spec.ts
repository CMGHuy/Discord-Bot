import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideLocationMocks } from '@angular/common/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, Routes, provideRouter, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { routes } from './app.routes';
import { adminGuard } from './auth/admin.guard';
import { RESOLVER_ROUTE_DATA } from './routing/route-metadata';
import { authGuard } from './shell/auth.guard';
import { SessionStore } from './stores/session.store';
import { installMatchMediaPolyfill } from './testing/match-media-polyfill';
import { TradeDetail } from './workspaces/trades/trade-detail';

// The detail routes render TradeChart, and lightweight-charts asks for
// matchMedia the moment a chart exists. See the polyfill for why.
installMatchMediaPolyfill();

/* NG30 — routing and the guard.
 *
 * SessionStore is replaced with the one member the guard reads. The real
 * store would drag in HttpClient and the boot sequence to answer a question
 * these tests want to set directly.
 */

function configure(authenticated: boolean, isAdmin = authenticated) {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(routes, withComponentInputBinding()),
      provideLocationMocks(),
      { provide: SessionStore, useValue: { isAuthenticated: () => authenticated, isAdmin: () => isAdmin } },
    ],
  });
}

describe('routing, authenticated', () => {
  beforeEach(() => configure(true));

  it('sends / to the dashboard', async () => {
    const harness = await RouterTestingHarness.create('/');
    expect(TestBed.inject(Router).url).toBe('/dashboard');
    // R1-11: the top bar owns the title now, not the workspace's own markup.
    expect(harness.routeNativeElement).not.toBeNull();
  });

  it('sends an unknown path to the dashboard', async () => {
    // Six destinations and no external links in: a dedicated 404 view would
    // be a page nobody ever means to reach.
    await RouterTestingHarness.create('/does-not-exist');
    expect(TestBed.inject(Router).url).toBe('/dashboard');
  });

  it.each([
    ['/dashboard', 'Dashboard'],
    ['/trades', 'Trades'],
    ['/insights/analytics', 'Analytics'],
    ['/watchlist', 'Watchlist'],
    ['/risk', 'Risk'],
    ['/system', 'System'],
  ])('mounts %s', async (path, heading) => {
    // R1-11: the top bar owns the title now -- no workspace renders its own
    // heading, so this asserts the route mounts and its declared title
    // matches, rather than scanning rendered text for a heading that no
    // longer exists in the workspace's own markup.
    const harness = await RouterTestingHarness.create(path);
    expect(harness.routeNativeElement).not.toBeNull();
    expect(routes.find((r) => r.path === path.slice(1))?.title).toBe(heading);
  });

  it('binds a route parameter as an input signal', async () => {
    // withComponentInputBinding(), which is what lets a detail component be
    // tested without standing up a router at all.
    const harness = await RouterTestingHarness.create('/trades/PLAN-123');
    const component = harness.routeDebugElement?.componentInstance as TradeDetail;

    expect(component.id()).toBe('PLAN-123');
  });

  it('does not let the list route shadow the detail route', async () => {
    const harness = await RouterTestingHarness.create('/watchlist/AAPL');
    expect(harness.routeNativeElement?.textContent).toContain('AAPL');
  });

  it('serves the calendar workspace behind the auth guard', async () => {
    const route = routes.find((r) => r.path === 'trades/calendar');
    expect(route).toBeDefined();
    expect(route?.canMatch).toEqual([authGuard]);

    // The lazy route must expose its component through its child config.
    const children = await route!.loadChildren!() as Routes;
    expect(children[1]?.path).toBe(':date');
    expect(children[0]?.loadComponent).toBeTypeOf('function');
    expect(await children[0]!.loadComponent!()).toBeDefined();
  });

  it('serves the plan page behind the auth guard (v151)', async () => {
    const route = routes.find((r) => r.path === 'plans/:id');
    expect(route).toBeDefined();
    expect(route?.canMatch).toEqual([authGuard]);
    expect(route?.title).toBe('Plan detail');
    expect(route?.data?.['subtitle']).toBe('Why this plan, and how it is going');

    const children = await route!.loadChildren!() as Routes;
    expect(children[0]?.loadComponent).toBeTypeOf('function');
    expect(await children[0]!.loadComponent!()).toBeDefined();
  });

  it('serves Research and Reports as real pages, with no placeholder left', async () => {
    for (const path of ['insights/research', 'insights/reports']) {
      const route = routes.find((item) => item.path === path);
      expect(route?.title).toBeTruthy();
      expect(String(route?.data?.['subtitle'])).not.toMatch(/planned/i);
      // The stub routes carried a `planned` blurb in their data.
      const children = await route!.loadChildren!() as Routes;
      expect(children[0].data?.['planned']).toBeUndefined();
      expect(await children[0].loadComponent!()).toBeDefined();
    }
    expect(readFileSync(join(process.cwd(), 'src/app/app.routes.ts'), 'utf8'))
      .not.toContain('workspaces/stubs');
  });
});


describe('route data readiness contract', () => {
  const expected = [
    'dashboard', 'trades', 'trades/:id', 'plans/:id', 'insights/analytics', 'trades/calendar',
    'watchlist', 'watchlist/:symbol', 'risk', 'system', 'system/versions', 'insights/research',
    'insights/reports',
  ] as const;

  it('keeps every authenticated workspace lazy, scoped, and resolver-backed', async () => {
    for (const path of expected) {
      const topLevel = routes.find((route) => route.path === path);
      expect(topLevel?.canMatch).toEqual(path.startsWith('system') ? [authGuard, adminGuard] : [authGuard]);
      expect(topLevel?.loadChildren).toBeTypeOf('function');

      const children = await topLevel!.loadChildren!() as Routes;
      const child = children[0]!;
      expect(child.providers).toBeTruthy();
      // v201: the Dashboard alone has no resolver; its store's onInit effect is the one load.
      if (path === 'dashboard') {
        expect(child.runGuardsAndResolvers).toBeUndefined();
        expect(child.resolve).toBeUndefined();
      } else {
        expect(child.runGuardsAndResolvers).toBe('always');
        expect(child.resolve?.['ready']).toBeTypeOf('function');
      }
      expect(child.data?.[RESOLVER_ROUTE_DATA]?.loadingLabel).toBeTruthy();
    }
  });

  it('refreshes Analytics and System only for their active tabs', async () => {
    const analytics = (await routes.find((route) => route.path === 'insights/analytics')!.loadChildren!() as Routes)[0]!;
    const system = (await routes.find((route) => route.path === 'system')!.loadChildren!() as Routes)[0]!;
    const analyticsRefresh = analytics.data![RESOLVER_ROUTE_DATA].refreshOn;
    const systemRefresh = system.data![RESOLVER_ROUTE_DATA].refreshOn;
    const route = (tab: string) => ({ queryParamMap: { get: () => tab } }) as never;

    expect(analyticsRefresh('analytics', route('performance'))).toBe(true);
    expect(analyticsRefresh('jobs', route('performance'))).toBe(false);
    expect(analyticsRefresh('jobs', route('tuning'))).toBe(true);
    expect(systemRefresh('settings', route('settings'))).toBe(true);
    expect(systemRefresh('bot', route('settings'))).toBe(false);
    expect(systemRefresh('bot', route('scan'))).toBe(true);
    expect(systemRefresh('settings', route('logs'))).toBe(false);
  });
});
describe('routing, unauthenticated', () => {
  beforeEach(() => configure(false));

  it('matches no workspace route at all', async () => {
    // canMatch, not canActivate: the guard runs BEFORE loadComponent, so
    // the workspace chunk is never even fetched. With every route guarded
    // there is nothing left to match, which is the intended outcome --
    // there is no unauthenticated view of this app to fall back to, because
    // the login form replaces the shell rather than living inside it.
    const router = TestBed.inject(Router);

    await expect(router.navigateByUrl('/trades')).rejects.toThrow();
    expect(router.url).not.toContain('trades');
  });
});

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
    void _lazy; void _component;
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
      { provide: SessionStore, useValue: { isAuthenticated: () => true, isAdmin: () => true } },
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
    // v207: the System routes are admin-only; every other section is authGuard alone.
    expect(route?.canMatch).toEqual(path.startsWith('system') ? [authGuard, adminGuard] : [authGuard]);
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

describe('routing, viewer (v207)', () => {
  beforeEach(() => configure(true, false));

  it.each(['/system', '/system?tab=users', '/system?tab=settings', '/system/versions', '/system/anything'])(
    'sends %s to the dashboard', async (url) => {
      await RouterTestingHarness.create(url);
      expect(TestBed.inject(Router).url).toBe('/dashboard');
    },
  );

  it.each(['/dashboard', '/trades', '/trades/calendar', '/watchlist', '/risk', '/insights/analytics'])(
    'still mounts %s', async (url) => {
      const harness = await RouterTestingHarness.create(url);
      expect(TestBed.inject(Router).url).toBe(url);
      expect(harness.routeNativeElement).not.toBeNull();
    },
  );
});

describe('route guards (v207)', () => {
  it('puts adminGuard after authGuard on every system route, and on nothing else', () => {
    const system = routes.filter((route) => route.path?.startsWith('system'));
    expect(system.map((route) => route.path)).toEqual(['system/versions', 'system']);
    expect(routes.filter((route) => route.canMatch?.includes(adminGuard))).toEqual(system);
    for (const route of system) expect(route.canMatch).toEqual([authGuard, adminGuard]);
  });
});
