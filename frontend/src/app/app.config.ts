import {
  ApplicationConfig,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from './api/interceptors';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // Spec v13 Decision 2. Angular 21 leaves zone.js out of the scaffold
    // rather than requiring this provider, so the app would be zoneless
    // without it -- it is here to make the choice explicit and to fail
    // loudly if someone reintroduces zone.js, which would otherwise
    // silently restore the change detection this design does not want.
    provideZonelessChangeDetection(),
    provideRouter(routes),
    // Order matters and is not alphabetical. Requests pass through this list
    // front to back; responses and errors unwind back to front. So:
    //   auth      is LAST, which makes it FIRST on the way back -- it sees a
    //             raw HttpErrorResponse and can recognise a 401 before
    //             anything has rewritten it;
    //   error     runs after auth on the way back, so it is the last handler
    //             to touch the failure and the caller always receives an
    //             ApiError, never an HttpErrorResponse;
    //   loading   is FIRST, so its finalize() wraps the entire lifetime,
    //             including the time the other two spend on the way back.
    // Swapping auth and error would silently break 401 detection: auth would
    // be matching `status === 401` against an ApiError that no longer is one.
    provideHttpClient(
      withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
    ),
  ],
};
