import { EnvironmentInjector, createEnvironmentInjector, inject } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, RouterStateSnapshot, Route } from '@angular/router';
import { NEVER, Observable, Subject, finalize, of, tap, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/api-error';
import { PreferencesStore } from '../stores/preferences.store';
import { SessionStore } from '../stores/session.store';
import { startRoute } from './route-resolver';

const route = {} as ActivatedRouteSnapshot;
const state = { url: '/trades?page=2' } as RouterStateSnapshot;
const routed = (config: Route = {}) => ({ routeConfig: config }) as unknown as ActivatedRouteSnapshot;

function setup(expire = vi.fn()) {
  TestBed.configureTestingModule({ providers: [
    { provide: PreferencesStore, useValue: { resolve: () => of(undefined) } },
    { provide: SessionStore, useValue: { expire } },
  ] });
  return expire;
}

const pending = (onCancel: () => void) => new Subject<void>().pipe(finalize(onCancel));

describe('startRoute (v201: routes never block)', () => {
  it('starts preferences before the feature data', () => {
    const order: string[] = [];
    const preferences = { resolve: vi.fn(() => of(undefined).pipe(tap(() => order.push('preferences')))) };
    TestBed.configureTestingModule({
      providers: [
        { provide: PreferencesStore, useValue: preferences },
        { provide: SessionStore, useValue: { expire: vi.fn() } },
      ],
    });
    const resolver = startRoute(() => of(undefined).pipe(tap(() => order.push('feature'))));
    (TestBed.runInInjectionContext(() => resolver(route, state)) as Observable<boolean>).subscribe();
    expect(order).toEqual(['preferences', 'feature']);
  });

  it('keeps the feature load in an injection context when preferences resolve asynchronously', async () => {
    // Cold-start path: preferences.resolve() is a real async round trip, so the
    // switchMap callback runs outside the router's injection context.
    const preferences = {
      resolve: () => new Observable<void>((subscriber) => {
        setTimeout(() => { subscriber.next(); subscriber.complete(); }, 0);
      }),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: PreferencesStore, useValue: preferences },
        { provide: SessionStore, useValue: { expire: vi.fn() } },
      ],
    });
    let loaded = false;
    const resolver = startRoute(() => {
      inject(SessionStore);
      loaded = true;
      return of(undefined);
    });
    TestBed.runInInjectionContext(() => resolver(route, state));
    await new Promise<void>((resolve) => setTimeout(resolve, 10));
    expect(loaded).toBe(true);
  });

  it('resolves true at once while the feature load is still pending', () => {
    setup();
    let value: boolean | undefined;
    const resolver = startRoute(() => NEVER);
    (TestBed.runInInjectionContext(() => resolver(routed(), state)) as Observable<boolean>)
      .subscribe((v) => { value = v; });
    expect(value).toBe(true);
  });

  it('remembers the requested URL when the background load fails on auth', () => {
    const expire = setup();
    const resolver = startRoute(() => throwError(() => new ApiError('auth', 401, 'expired')));
    let value: boolean | undefined;
    (TestBed.runInInjectionContext(() => resolver(routed(), state)) as Observable<boolean>)
      .subscribe((v) => { value = v; });
    expect(expire).toHaveBeenCalledWith('/trades?page=2');
    expect(value).toBe(true);
  });

  it('drops a non-auth failure without throwing', () => {
    const expire = setup();
    const resolver = startRoute(() => throwError(() => new Error('boom')));
    expect(() => TestBed.runInInjectionContext(() => resolver(routed(), state))).not.toThrow();
    expect(expire).not.toHaveBeenCalled();
  });

  it('a re-run of the same route cancels the previous load', () => {
    setup();
    const config: Route = {};
    let cancelled = 0;
    const resolver = startRoute(() => pending(() => { cancelled += 1; }));
    TestBed.runInInjectionContext(() => resolver(routed(config), state));
    TestBed.runInInjectionContext(() => resolver(routed(config), state));
    expect(cancelled).toBe(1);
  });

  it('loads of two different routes do not cancel each other', () => {
    setup();
    let cancelled = 0;
    const resolver = startRoute(() => pending(() => { cancelled += 1; }));
    TestBed.runInInjectionContext(() => resolver(routed({}), state));
    TestBed.runInInjectionContext(() => resolver(routed({}), state));
    expect(cancelled).toBe(0);
  });

  it('stops the load when the route injector is destroyed', () => {
    setup();
    let cancelled = 0;
    const child = createEnvironmentInjector([], TestBed.inject(EnvironmentInjector));
    const resolver = startRoute(() => pending(() => { cancelled += 1; }));
    child.runInContext(() => resolver(routed(), state));
    child.destroy();
    expect(cancelled).toBe(1);
  });
});
