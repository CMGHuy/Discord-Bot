import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Route, Router, UrlTree, provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { SessionStore } from '../stores/session.store';
import { adminGuard } from './admin.guard';

function run(isAdmin: boolean): boolean | UrlTree {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      { provide: SessionStore, useValue: { isAdmin: signal(isAdmin) } },
    ],
  });
  return TestBed.runInInjectionContext(() => adminGuard({} as Route, [])) as boolean | UrlTree;
}

describe('adminGuard (v207)', () => {
  it('lets the admin match', () => {
    expect(run(true)).toBe(true);
  });

  it('sends anyone else to the dashboard with a UrlTree, not a bare false', () => {
    const result = run(false);
    expect(result).toBeInstanceOf(UrlTree);
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/dashboard');
  });
});
