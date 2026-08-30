import { Observable, catchError, defer, map, of, tap, throwError } from 'rxjs';

import { ApiError } from '../api/api-error';

export interface RouteRequestHandlers<T> {
  start(): void;
  next(value: T): void;
  error(error: ApiError): void;
}

export function routeRequest<T>(
  source: Observable<T>,
  handlers: RouteRequestHandlers<T>,
): Observable<void> {
  return defer(() => {
    handlers.start();
    return source.pipe(
      tap({ next: handlers.next, error: handlers.error }),
      map(() => undefined),
      catchError((error: unknown) =>
        error instanceof ApiError && error.isAuth
          ? throwError(() => error)
          : of(undefined),
      ),
    );
  });
}