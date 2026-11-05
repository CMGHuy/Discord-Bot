import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { ApiError } from '../api/api-error';
import { ToastService } from '../shell/toast.service';

export const FORBIDDEN_TOAST = 'Read-only account';

function shouldToast(error: unknown, url: string, toasts: ToastService): boolean {
  return (
    error instanceof ApiError &&
    error.code === 'forbidden' &&
    !url.endsWith('/system/preferences') &&
    !toasts.toasts().some((t) => t.message === FORBIDDEN_TOAST)
  );
}

/**
 * Says "Read-only account" when the server refuses a viewer's write (v207).
 *
 * A fallback, not a normal path: write controls are hidden from viewers, so
 * this only fires for one that slipped through. `/system/preferences` is
 * exempt -- a viewer's layout tweak never toasts (spec section SPA), and the
 * preferences store never sends it anyway. One toast per burst: a page that
 * fires several refused requests at once shows a single message.
 *
 * Sits outside `errorInterceptor`, so on the way back it already sees the
 * `ApiError`. The error is always rethrown unchanged.
 */
export const forbiddenInterceptor: HttpInterceptorFn = (req, next) => {
  const toasts = inject(ToastService);
  return next(req).pipe(
    catchError((error: unknown) => {
      if (shouldToast(error, req.url, toasts)) toasts.show(FORBIDDEN_TOAST, 'warn');
      return throwError(() => error);
    }),
  );
};
