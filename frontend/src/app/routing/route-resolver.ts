import { DestroyRef, EnvironmentInjector, inject, runInInjectionContext } from '@angular/core';
import { ActivatedRouteSnapshot, ResolveFn, Route } from '@angular/router';
import { Observable, Subscription, of, switchMap } from 'rxjs';

import { ApiError } from '../api/api-error';
import { PreferencesStore } from '../stores/preferences.store';
import { SessionStore } from '../stores/session.store';

/** The load each route definition has in flight (v201): a re-run of the same
 *  route unsubscribes the previous one so only the newest can land. */
const inFlight = new WeakMap<Route, Subscription>();

/**
 * v201: START the route's data load and resolve at once. The page renders
 * immediately and each store shows its own skeleton while its request runs,
 * so no navigation waits on the network. Errors in the background load:
 * an auth failure expires the session; anything else is dropped because the
 * stores already own their error state through `routeRequest`.
 */
export function startRoute(
  load: (route: ActivatedRouteSnapshot) => Observable<void>,
): ResolveFn<boolean> {
  return (route, state) => {
    const preferences = inject(PreferencesStore);
    const session = inject(SessionStore);
    // Captured here, synchronously, while the router still guarantees an
    // injection context. `preferences.resolve()` is a real HTTP round trip on
    // the true first navigation, so switchMap's callback then runs OUTSIDE
    // that context, and every `load` in every *.routes.ts file calls
    // `inject(...)` itself. Without this that inject() throws NG0203 and the
    // workspace silently shows nothing on a cold start or hard refresh.
    const injector = inject(EnvironmentInjector);
    const key = route.routeConfig;
    if (key) inFlight.get(key)?.unsubscribe();
    const subscription = preferences.resolve()
      .pipe(switchMap(() => runInInjectionContext(injector, () => load(route))))
      .subscribe({
        error: (error: unknown) => {
          if (error instanceof ApiError && error.isAuth) session.expire(state.url);
        },
      });
    if (key) inFlight.set(key, subscription);
    injector.get(DestroyRef).onDestroy(() => subscription.unsubscribe());
    return of(true);
  };
}
