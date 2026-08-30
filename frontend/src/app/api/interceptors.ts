import { HttpContextToken, HttpErrorResponse, HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, finalize, tap, throwError } from 'rxjs';

import { ApiError } from './api-error';
import { LoadingService } from './loading.service';
import { UnauthorizedService } from './unauthorized.service';
import { RouteRefreshService } from '../routing/route-refresh.service';

export const SKIP_ROUTE_REFRESH = new HttpContextToken<boolean>(() => false);

/** Send the session cookie, and report a 401 exactly once per response.
 *
 * **No retry, deliberately.** The instinct on a 401 is to refresh and retry,
 * and there is nothing to refresh: auth here is a signed session cookie
 * (spec v11 Decision 5), so a 401 means the session is gone or the admin
 * password changed. Retrying would turn one failed request into two and
 * still fail -- and on a `pw_hash` change it would do that on every request
 * the app makes, in a loop, while the user watches a spinner.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const unauthorized = inject(UnauthorizedService);

  // EventSource cannot set headers, so the whole API authenticates by
  // cookie; this keeps XHR on the same mechanism rather than a second one.
  const withCookies = req.clone({ withCredentials: true });

  return next(withCookies).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 401) {
        unauthorized.report();
      }
      return throwError(() => error);
    }),
  );
};

/** Normalise every failure into an `ApiError` before it reaches a caller. */
export const errorInterceptor: HttpInterceptorFn = (req, next) =>
  next(req).pipe(
    catchError((error: unknown) => {
      if (error instanceof ApiError) {
        return throwError(() => error);
      }
      if (error instanceof HttpErrorResponse) {
        return throwError(() => toApiError(error));
      }
      return throwError(
        () => new ApiError('unavailable', 0, 'The admin could not be reached.'),
      );
    }),
  );

function toApiError(response: HttpErrorResponse): ApiError {
  const body = response.error as { error?: { code?: string; message?: string } } | null;
  const declared = body?.error;

  if (declared?.code) {
    return new ApiError(declared.code, response.status, declared.message ?? response.message);
  }

  // Nothing that speaks the v1 contract produced this. Status 0 is a dead
  // server, a CORS refusal or an offline browser; anything else with a
  // non-JSON body is a proxy or a framework error page, which from the
  // client's point of view is the same thing -- the API is not answering.
  // Calling it `unavailable` rather than inventing a code per status keeps
  // the "is the backend there" branch in one place.
  return new ApiError(
    'unavailable',
    response.status,
    response.status === 0
      ? 'The admin could not be reached.'
      : `The admin returned an unexpected ${response.status} response.`,
  );
}

/** Count in-flight requests so the shell can show one global indicator. */
export const loadingInterceptor: HttpInterceptorFn = (req, next) => {
  const loading = inject(LoadingService);
  loading.started();
  // finalize, not tap: it runs on success, on error, AND on unsubscribe --
  // and unsubscribe is the common case here, because switchMap cancels the
  // previous request every time a filter changes.
  return next(req).pipe(finalize(() => loading.finished()));
};

/** Reload resolver-backed routes after successful mutations, never after reads. */
export const routeRefreshInterceptor: HttpInterceptorFn = (req, next) => {
  const refresh = inject(RouteRefreshService);
  return next(req).pipe(tap((event) => {
    if (event instanceof HttpResponse && req.method !== 'GET' && !req.context.get(SKIP_ROUTE_REFRESH)) {
      refresh.requestMutationRefresh();
    }
  }));
};
