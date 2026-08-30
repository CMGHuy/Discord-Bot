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