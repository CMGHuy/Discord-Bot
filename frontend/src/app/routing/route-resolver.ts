import { EnvironmentInjector, inject, runInInjectionContext } from '@angular/core';
import { ActivatedRouteSnapshot, ResolveFn } from '@angular/router';
import { EMPTY, Observable, catchError, map, of, switchMap } from 'rxjs';

import { ApiError } from '../api/api-error';
import { PreferencesStore } from '../stores/preferences.store';
import { SessionStore } from '../stores/session.store';

export function resolveRoute(
  load: (route: ActivatedRouteSnapshot) => Observable<void>,
): ResolveFn<boolean> {
  return (route, state) => {
    const preferences = inject(PreferencesStore);
    const session = inject(SessionStore);
    // Captured here, synchronously, while the router still guarantees an
    // injection context. `preferences.resolve()` is synchronous once
    // preferences are cached, but on the true first navigation (before
    // PreferencesStore has ever loaded) it is a real HTTP round trip --
    // switchMap's callback then runs OUTSIDE that context, and every
    // `load` in every *.routes.ts file calls `inject(...)` itself. Without
    // this, that inject() throws NG0203, the catchError below (which only
    // recognises ApiError) swallows it as a generic error, and the route
    // "resolves" successfully with the store never populated -- a
    // workspace that silently shows nothing on a cold start or hard
    // refresh, with no error banner to explain why.
    const injector = inject(EnvironmentInjector);
    return preferences.resolve().pipe(
      switchMap(() => runInInjectionContext(injector, () => load(route))),
      map(() => true),
      catchError((error: unknown) => {
        if (error instanceof ApiError && error.isAuth) {
          session.expire(state.url);
          return EMPTY;
        }
        return of(true);
      }),
    );
  };
}