import { inject } from '@angular/core';
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
    return preferences.resolve().pipe(
      switchMap(() => load(route)),
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