import { inject } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, RouterStateSnapshot } from '@angular/router';
import { Observable, of, tap, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/api-error';
import { PreferencesStore } from '../stores/preferences.store';
import { SessionStore } from '../stores/session.store';
import { resolveRoute } from './route-resolver';

const route = {} as ActivatedRouteSnapshot;
const state = { url: '/trades?page=2' } as RouterStateSnapshot;

describe('resolveRoute', () => {
  it('waits for preferences before starting feature data', () => {
    const order: string[] = [];
    const preferences = { resolve: vi.fn(() => of(undefined).pipe(tap(() => order.push('preferences')))) };
    TestBed.configureTestingModule({
      providers: [
        { provide: PreferencesStore, useValue: preferences },
        { provide: SessionStore, useValue: { expire: vi.fn() } },
      ],
    });
    const resolver = resolveRoute(() => of(undefined).pipe(tap(() => order.push('feature'))));
    (TestBed.runInInjectionContext(() => resolver(route, state)) as Observable<boolean>).subscribe();
    expect(order).toEqual(['preferences', 'feature']);
  });

  it('keeps the feature load in an injection context when preferences resolve asynchronously', async () => {
    // Reproduces the cold-start path: PreferencesStore has not loaded yet,
    // so preferences.resolve() is a real (async) HTTP round trip rather
    // than the synchronous of(undefined) every other test here uses.
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
    // A feature load that behaves like every real *.routes.ts call site --
    // it calls inject() itself rather than receiving an already-resolved
    // instance -- so this fails exactly the way WatchlistStore/CalendarStore
    // resolution fails after the preferences round trip completes.
    const resolver = resolveRoute(() => {
      inject(SessionStore);
      loaded = true;
      return of(undefined);
    });
    const result$ = TestBed.runInInjectionContext(() => resolver(route, state)) as Observable<boolean>;
    let value: boolean | undefined;
    let error: unknown;
    await new Promise<void>((resolve) => {
      result$.subscribe({
        next: (v) => { value = v; },
        error: (e) => { error = e; resolve(); },
        complete: resolve,
      });
    });
    expect(error).toBeUndefined();
    expect(loaded).toBe(true);
    expect(value).toBe(true);
  });

  it('remembers the requested URL and cancels an auth failure', () => {
    const expire = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        { provide: PreferencesStore, useValue: { resolve: () => of(undefined) } },
        { provide: SessionStore, useValue: { expire } },
      ],
    });
    const resolver = resolveRoute(() => throwError(() => new ApiError('auth', 401, 'expired')));
    let completed = false;
    (TestBed.runInInjectionContext(() => resolver(route, state)) as Observable<boolean>).subscribe({ complete: () => { completed = true; } });
    expect(expire).toHaveBeenCalledWith('/trades?page=2');
    expect(completed).toBe(true);
  });
});