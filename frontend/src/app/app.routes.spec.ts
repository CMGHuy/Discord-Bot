import { provideLocationMocks } from '@angular/common/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { routes } from './app.routes';
import { SessionStore } from './stores/session.store';
import { TradeDetail } from './workspaces/trades/trade-detail';

/* NG30 — routing and the guard.
 *
 * SessionStore is replaced with the one member the guard reads. The real
 * store would drag in HttpClient and the boot sequence to answer a question
 * these tests want to set directly.
 */

function configure(authenticated: boolean) {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(routes, withComponentInputBinding()),
      provideLocationMocks(),
      { provide: SessionStore, useValue: { isAuthenticated: () => authenticated } },
    ],
  });
}

describe('routing, authenticated', () => {
  beforeEach(() => configure(true));

  it('sends / to the cockpit', async () => {
    const harness = await RouterTestingHarness.create('/');
    expect(TestBed.inject(Router).url).toBe('/cockpit');
    expect(harness.routeNativeElement?.textContent).toContain('Cockpit');
  });

  it('sends an unknown path to the cockpit', async () => {
    // Six destinations and no external links in: a dedicated 404 view would
    // be a page nobody ever means to reach.
    await RouterTestingHarness.create('/does-not-exist');
    expect(TestBed.inject(Router).url).toBe('/cockpit');
  });

  it.each([
    ['/cockpit', 'Cockpit'],
    ['/trades', 'Trades'],
    ['/analytics', 'Analytics'],
    ['/universe', 'Universe'],
    ['/risk', 'Risk'],
    ['/system', 'System'],
  ])('mounts %s', async (path, heading) => {
    const harness = await RouterTestingHarness.create(path);
    expect(harness.routeNativeElement?.textContent).toContain(heading);
  });

  it('binds a route parameter as an input signal', async () => {
    // withComponentInputBinding(), which is what lets a detail component be
    // tested without standing up a router at all.
    const harness = await RouterTestingHarness.create('/trades/PLAN-123');
    const component = harness.routeDebugElement?.componentInstance as TradeDetail;

    expect(component.id()).toBe('PLAN-123');
  });

  it('does not let the list route shadow the detail route', async () => {
    const harness = await RouterTestingHarness.create('/universe/AAPL');
    expect(harness.routeNativeElement?.textContent).toContain('AAPL');
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
