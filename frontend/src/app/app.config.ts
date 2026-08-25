import {
  ApplicationConfig,
  inject,
  isDevMode,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { APP_BASE_HREF } from '@angular/common';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideServiceWorker } from '@angular/service-worker';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from './api/interceptors';
import { routes } from './app.routes';
import { PwaUpdateService } from './pwa/pwa-update.service';
import { provideRouteFocus } from './shell/route-focus';
import { SessionStore } from './stores/session.store';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // Spec v13 Decision 2. Angular 21 leaves zone.js out of the scaffold
    // rather than requiring this provider, so the app would be zoneless
    // without it -- it is here to make the choice explicit and to fail
    // loudly if someone reintroduces zone.js, which would otherwise
    // silently restore the change detection this design does not want.
    provideZonelessChangeDetection(),
    // The bundle is built with `--base-href=/app/` because spa.py serves its
    // files from /app/ -- deliberately, so they cannot collide with the Jinja
    // UI's /static/. But `<base href>` is read by TWO things: the browser,
    // resolving asset URLs, and the router, deciding what a route path means.
    // Only the first one wants /app/. The workspaces live at /dashboard,
    // /trades and so on, which is what spa.py registers and what a user
    // bookmarks; a router that inherited /app/ would build every link as
    // /app/dashboard and 404 on the first navigation.
    //
    // APP_BASE_HREF is the override for exactly that split. It must stay in
    // step with the --base-href in angular.json: assets under /app/, routes
    // under /. Without it the app loads and then breaks on the first click,
    // which is a worse failure than not loading at all.
    { provide: APP_BASE_HREF, useValue: '/' },
    // withComponentInputBinding: :id and :symbol arrive as input() signals
    // rather than through ActivatedRoute, which keeps a detail component
    // testable without standing up a router.
    provideRouter(routes, withComponentInputBinding()),
    // In an SPA a route change moves nothing on its own: focus stays on the
    // nav link just activated and the new page is never announced. This
    // moves it to the new workspace's <h1> once it has actually rendered.
    provideRouteFocus(),
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
    // Answer "who am I" BEFORE the app bootstraps. Angular waits on the
    // returned promise, so App never renders in the 'unknown' state -- which
    // is what stops an unauthenticated visitor seeing a frame of the real
    // shell, and stops every workspace firing a doomed request on load.
    // It must be registered after provideHttpClient: it makes an HTTP call.
    provideAppInitializer(() => inject(SessionStore).boot()),
    // Registered at an ABSOLUTE root path ('/ngsw-worker.js'), not the
    // relative 'ngsw-worker.js' the schematic defaults to. A relative script
    // URL resolves against the CURRENT PAGE's own URL (not <base href>,
    // which only governs asset/link resolution), so its result depends on
    // which workspace happened to load it -- '/trades/ngsw-worker.js' from
    // one page, '/ngsw-worker.js' from another. An absolute path is
    // unambiguous, and `scope: '/'` is what actually matters: the app's real
    // navigable URLs are root-level (/dashboard, /trades, ... -- see
    // APP_BASE_HREF above), not under /app/ where the rest of the bundle
    // lives, so the default /app/-scoped registration could never control
    // them or the manifest's start_url ("/dashboard"), and the app would
    // never be considered installable. spa.py serves this exact file at the
    // origin root for precisely this (see its ngsw_root() route).
    provideServiceWorker('/ngsw-worker.js', {
      enabled: !isDevMode(),
      scope: '/',
      registrationStrategy: 'registerWhenStable:30000',
    }),
    // Fire-and-forget: init() returns void, so this never delays bootstrap
    // the way SessionStore's does above. Without it, an installed PWA can
    // stay open indefinitely and never notice a new deploy -- see
    // PwaUpdateService's own doc comment for why "the SW downloads it
    // eventually" is not the same as "the app updates".
    provideAppInitializer(() => inject(PwaUpdateService).init()),
  ],
};
